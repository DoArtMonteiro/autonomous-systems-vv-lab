//! Geographic environment packs: a terrain height grid and a true-colour image on a regular grid of
//! the ENU tangent plane at an origin, with a manifest (`environment.json`, schema
//! `vv-geo-environment.v1` or `.v2`) naming the origin, datums, sources, licences and file hashes.
//! Schema v2 adds an optional detail layer: a smaller square around the origin with a finer
//! height grid and image (`detail-height.u16`, `detail-image.jpg`). Where a detail layer covers a
//! point it is the terrain there; within `blend_m` of its edge its heights blend linearly into the
//! base grid so the drawn surfaces meet. The origin (z = 0) is on the finest layer.
//! Schema v3 adds an optional world layer (see [`crate::world`]): building footprints, lidar
//! structures, point structures and lidar vegetation, each with the source of its height.
//!
//! A pack is untrusted input until [`Environment::open`] accepts it: fixed file names, bounded
//! sizes, matching SHA-256, a consistent grid, attributed sources, and the pack's check points
//! recomputed with this crate's geodesy within 1 mm. A pack that fails any rule is not shown.
//! Packs are built by `scripts/geo/build_environment.py` with PROJ; recomputing their check points
//! here is a test of two independent implementations against each other.

use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use crate::wgs84::{Enu, Geodetic};
use crate::world::{self, FEATURES_FILE, VEGETATION_FILE, World};

pub const SCHEMA: &str = "vv-geo-environment.v1";
pub const SCHEMA_V2: &str = "vv-geo-environment.v2";
pub const SCHEMA_V3: &str = "vv-geo-environment.v3";
pub const MANIFEST: &str = "environment.json";
pub const HEIGHT_FILE: &str = "height.u16";
pub const IMAGE_FILE: &str = "image.jpg";
pub const DETAIL_HEIGHT_FILE: &str = "detail-height.u16";
pub const DETAIL_IMAGE_FILE: &str = "detail-image.jpg";
const MAX_MANIFEST_BYTES: u64 = 256 * 1024;
const MAX_HEIGHT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_IMAGE_BYTES: u64 = 32 * 1024 * 1024;
const MAX_EXTENT_M: f64 = 50_000.0;
/// Most texels of one decoded image (8192 x 8192): the web view allocates four bytes each.
const MAX_IMAGE_PIXELS: usize = 8192 * 8192;
/// Most vertices of one height grid (about 2049 x 2049): the web view keeps four bytes each.
const MAX_GRID_VERTICES: usize = 4_200_000;
/// Limits of the descriptive text the interface shows from a manifest.
const MAX_SOURCES: usize = 32;
const MAX_SOURCE_TEXT: usize = 2_000;
const MAX_CREDIT: usize = 300;
const MAX_ACCURACY_NOTES: usize = 32;
const MAX_NOTE: usize = 2_000;
/// Tolerance for the recomputed check points (m).
pub const CHECK_TOLERANCE_M: f64 = 1e-3;

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "kind", content = "message", rename_all = "snake_case")]
pub enum GeoError {
    Io(String),
    Invalid(String),
}

impl std::fmt::Display for GeoError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            GeoError::Io(m) | GeoError::Invalid(m) => f.write_str(m),
        }
    }
}

fn invalid<T>(m: impl Into<String>) -> Result<T, GeoError> {
    Err(GeoError::Invalid(m.into()))
}

pub(crate) fn invalid_err<T>(m: impl Into<String>) -> Result<T, GeoError> {
    invalid(m)
}

#[derive(Deserialize)]
struct Manifest {
    schema: String,
    id: String,
    name: String,
    summary: String,
    origin: Origin,
    frame: Frame,
    extent_m: f64,
    height: Height,
    image: Image,
    #[serde(default)]
    layers: Vec<Layer>,
    sources: Vec<Source>,
    checks: Vec<Check>,
    // Descriptive facts the interface shows. Typed here so a manifest with another kind of value
    // is rejected, and re-emitted from these fields only (see `summary_of`).
    #[serde(default)]
    site_note: Option<String>,
    #[serde(default)]
    relief: Option<Vec<Relief>>,
    #[serde(default)]
    accuracy: Option<Vec<String>>,
    #[serde(default)]
    built: Option<BTreeMap<String, Value>>,
}

#[derive(Deserialize, Serialize)]
struct Relief {
    radius_m: f64,
    min_up_m: f64,
    max_up_m: f64,
}

#[derive(Deserialize)]
struct Layer {
    role: String,
    extent_m: f64,
    blend_m: f64,
    height: Height,
    image: Image,
}

#[derive(Deserialize)]
struct Origin {
    lat_deg: f64,
    lon_deg: f64,
    h_ellipsoid_m: f64,
    orthometric_height_m: f64,
    geoid_undulation_m: f64,
}

#[derive(Deserialize)]
struct Frame {
    kind: String,
    ellipsoid: String,
    heading_deg: f64,
}

#[derive(Deserialize)]
struct Height {
    file: String,
    encoding: String,
    scale_m: f64,
    offset_m: f64,
    columns: usize,
    rows: usize,
    spacing_m: f64,
    first_node_m: [f64; 2],
    bytes: u64,
    sha256: String,
}

#[derive(Deserialize)]
struct Image {
    file: String,
    columns: usize,
    rows: usize,
    spacing_m: f64,
    first_texel_centre_m: [f64; 2],
    bytes: u64,
    sha256: String,
}

#[derive(Deserialize)]
struct Source {
    provider: String,
    product: String,
    licence: String,
    attribution: String,
    /// Short credit shown on the map; falls back to the attribution.
    #[serde(default)]
    credit: Option<String>,
    #[serde(default)]
    access: Option<String>,
    #[serde(default)]
    layer: Option<String>,
}

#[derive(Deserialize)]
struct Check {
    lat_deg: f64,
    lon_deg: f64,
    h_ellipsoid_m: f64,
    enu_m: [f64; 3],
    /// The grid the check's height belongs to: "base" (default) or "detail".
    #[serde(default)]
    layer: Option<String>,
}

/// A validated, square height grid centred on the origin.
#[derive(Debug, Clone)]
struct Grid {
    heights: Vec<f32>,
    cols: usize,
    rows: usize,
    spacing: f64,
    x0: f64,
    y0: f64,
}

impl Grid {
    /// Linear on the two triangles the Studio draws for each cell (split along the north-east to
    /// south-west diagonal), so clearances refer to the surface on screen.
    fn at(&self, e: f64, n: f64) -> Option<f64> {
        let fx = (e - self.x0) / self.spacing;
        let fy = (self.y0 - n) / self.spacing;
        if !(fx >= 0.0 && fy >= 0.0 && fx <= (self.cols - 1) as f64 && fy <= (self.rows - 1) as f64)
        {
            return None;
        }
        let c = (fx.floor() as usize).min(self.cols - 2);
        let r = (fy.floor() as usize).min(self.rows - 2);
        let tx = fx - c as f64;
        let ty = fy - r as f64;
        let at = |rr: usize, cc: usize| self.heights[rr * self.cols + cc] as f64;
        let (a, b, d, e) = (at(r, c), at(r, c + 1), at(r + 1, c), at(r + 1, c + 1));
        Some(if tx + ty <= 1.0 {
            a + (b - a) * tx + (d - a) * ty
        } else {
            e + (d - e) * (1.0 - tx) + (b - e) * (1.0 - ty)
        })
    }

    fn half(&self) -> f64 {
        -self.x0
    }
}

/// A validated detail layer.
#[derive(Debug, Clone)]
struct Detail {
    grid: Grid,
    blend_m: f64,
    height_sha: String,
    image_sha: String,
}

/// A validated environment pack.
#[derive(Debug, Clone)]
pub struct Environment {
    pub id: String,
    pub dir: PathBuf,
    pub frame: Enu,
    /// Geoid undulation at the origin (EGM2008 minus WGS84 ellipsoid), metres.
    pub geoid_undulation_m: f64,
    base: Grid,
    detail: Option<Detail>,
    world: World,
    summary: Value,
    bytes: u64,
    image_sha: String,
    worst_check_m: f64,
}

/// A model point placed on the Earth (derived for display).
#[derive(Debug, Clone, Copy, Serialize)]
pub struct TrackPoint {
    pub lat_deg: f64,
    pub lon_deg: f64,
    /// Height above the WGS84 ellipsoid.
    pub h_ellipsoid_m: f64,
    /// Height above the EGM2008 geoid (approximately mean sea level), with the undulation of the
    /// origin.
    pub h_msl_m: f64,
    /// ENU up of the terrain under the point, when the point is inside the pack.
    pub terrain_up_m: Option<f64>,
    /// ENU up of the point minus the terrain under it.
    pub above_terrain_m: Option<f64>,
}

fn finite(v: f64, what: &str) -> Result<f64, GeoError> {
    if v.is_finite() {
        Ok(v)
    } else {
        invalid(format!("{what} is not a finite number"))
    }
}

pub(crate) fn read_bounded(path: &Path, max: u64) -> Result<Vec<u8>, GeoError> {
    let meta = fs::symlink_metadata(path)
        .map_err(|e| GeoError::Io(format!("{}: {e}", file_name(path))))?;
    if !meta.is_file() {
        return invalid(format!("{} is not a regular file", file_name(path)));
    }
    if meta.len() > max {
        return invalid(format!("{} is larger than {max} bytes", file_name(path)));
    }
    let mut buf = Vec::with_capacity(meta.len() as usize);
    fs::File::open(path)
        .and_then(|f| f.take(max + 1).read_to_end(&mut buf))
        .map_err(|e| GeoError::Io(format!("{}: {e}", file_name(path))))?;
    if buf.len() as u64 > max {
        return invalid(format!(
            "{} grew past {max} bytes while it was read",
            file_name(path)
        ));
    }
    Ok(buf)
}

fn file_name(p: &Path) -> String {
    p.file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default()
}

pub fn sha256_hex(b: &[u8]) -> String {
    let d = Sha256::digest(b);
    d.iter().map(|x| format!("{x:02x}")).collect()
}

/// Environment ids are folder names: lower-case letters, digits and hyphens, 1 to 48 characters,
/// and never a Windows device name.
pub fn valid_id(id: &str) -> bool {
    const RESERVED: [&str; 4] = ["con", "prn", "aux", "nul"];
    let device = RESERVED.contains(&id)
        || ((id.starts_with("com") || id.starts_with("lpt"))
            && id.len() == 4
            && id.as_bytes()[3].is_ascii_digit());
    (1..=48).contains(&id.len())
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        && !id.starts_with('-')
        && !device
}

/// Width and height from the first start-of-frame marker of a JPEG (baseline, extended or
/// progressive), or `None` when the stream has none before the image data.
pub fn jpeg_size(b: &[u8]) -> Option<(usize, usize)> {
    let mut i = 2;
    while i + 4 <= b.len() {
        if b[i] != 0xFF {
            return None;
        }
        let marker = b[i + 1];
        if marker == 0xFF {
            i += 1;
            continue;
        }
        let len = u16::from_be_bytes([b[i + 2], b[i + 3]]) as usize;
        if (0xC0..=0xC2).contains(&marker) {
            if i + 9 > b.len() {
                return None;
            }
            let h = u16::from_be_bytes([b[i + 5], b[i + 6]]) as usize;
            let w = u16::from_be_bytes([b[i + 7], b[i + 8]]) as usize;
            return Some((w, h));
        }
        if marker == 0xDA || len < 2 {
            return None;
        }
        i += 2 + len;
    }
    None
}

/// Reads and validates a square height grid centred on the origin spanning `extent` each way.
fn read_grid(dir: &Path, h: &Height, extent: f64, name: &str) -> Result<(Grid, Vec<u8>), GeoError> {
    if h.file != name || h.encoding != "uint16-le" {
        return invalid(format!("the height grid must be {name}, uint16-le"));
    }
    if !(2..=4097).contains(&h.columns) || !(2..=4097).contains(&h.rows) {
        return invalid(format!("{name}: grid size outside 2..4097"));
    }
    if h.columns * h.rows > MAX_GRID_VERTICES {
        return invalid(format!(
            "{name}: {}x{} vertices is more than {MAX_GRID_VERTICES}",
            h.columns, h.rows
        ));
    }
    let s = finite(h.spacing_m, "height spacing")?;
    if !(0.25..=1000.0).contains(&s) || finite(h.scale_m, "height scale")? <= 0.0 {
        return invalid(format!("{name}: spacing or scale out of range"));
    }
    finite(h.offset_m, "height offset")?;
    let want_x0 = -((h.columns - 1) as f64) * s / 2.0;
    let want_y0 = ((h.rows - 1) as f64) * s / 2.0;
    if (h.first_node_m[0] - want_x0).abs() > 1e-6 || (h.first_node_m[1] - want_y0).abs() > 1e-6 {
        return invalid(format!("{name}: the grid is not centred on the origin"));
    }
    // Square grid, exactly the declared extent: the image UVs assume it.
    if h.rows != h.columns || (2.0 * want_y0 - 2.0 * extent).abs() > 1e-6 {
        return invalid(format!(
            "{name}: the grid must be square and span exactly the declared extent"
        ));
    }
    if h.bytes != (h.columns * h.rows * 2) as u64 {
        return invalid(format!("{name}: byte count does not match its size"));
    }
    let hb = read_bounded(&dir.join(name), MAX_HEIGHT_BYTES)?;
    if hb.len() as u64 != h.bytes || sha256_hex(&hb) != h.sha256 {
        return invalid(format!("{name} does not match its SHA-256 in the manifest"));
    }
    let heights: Vec<f32> = hb
        .as_chunks::<2>()
        .0
        .iter()
        .map(|c| (u16::from_le_bytes(*c) as f64 * h.scale_m + h.offset_m) as f32)
        .collect();
    let g = Grid {
        heights,
        cols: h.columns,
        rows: h.rows,
        spacing: s,
        x0: want_x0,
        y0: want_y0,
    };
    Ok((g, hb))
}

/// Reads and validates a square JPEG image spanning `extent` each way, half a texel inside it.
fn read_image(dir: &Path, im: &Image, extent: f64, name: &str) -> Result<Vec<u8>, GeoError> {
    if im.file != name || !(16..=16384).contains(&im.columns) || !(16..=16384).contains(&im.rows) {
        return invalid(format!(
            "the image must be {name}, 16 to 16384 texels a side and at most 8192 x 8192 in all"
        ));
    }
    if im.columns * im.rows > MAX_IMAGE_PIXELS {
        return invalid(format!(
            "{name}: {}x{} texels is more than {MAX_IMAGE_PIXELS}",
            im.columns, im.rows
        ));
    }
    let sp = finite(im.spacing_m, "image spacing")?;
    let first = [-extent + sp / 2.0, extent - sp / 2.0];
    if im.rows != im.columns
        || ((im.columns as f64) * sp - 2.0 * extent).abs() > 1e-6
        || (im.first_texel_centre_m[0] - first[0]).abs() > 1e-6
        || (im.first_texel_centre_m[1] - first[1]).abs() > 1e-6
    {
        return invalid(format!(
            "{name}: the image must be square, span exactly the declared extent and start half a texel inside it"
        ));
    }
    let ib = read_bounded(&dir.join(name), MAX_IMAGE_BYTES)?;
    if ib.len() as u64 != im.bytes || sha256_hex(&ib) != im.sha256 {
        return invalid(format!("{name} does not match its SHA-256 in the manifest"));
    }
    if !ib.starts_with(&[0xFF, 0xD8, 0xFF]) {
        return invalid(format!("{name} is not a JPEG file"));
    }
    // The decoded size is what the web view allocates: it must be the declared one.
    match jpeg_size(&ib) {
        Some((w, hh)) if w == im.columns && hh == im.rows => Ok(ib),
        other => invalid(format!(
            "{name} is {other:?} pixels, the manifest declares {}x{}",
            im.columns, im.rows
        )),
    }
}

impl Environment {
    /// Reads and validates the pack in `dir`. Nothing of a pack is used before this returns `Ok`.
    pub fn open(dir: &Path) -> Result<Self, GeoError> {
        let folder = file_name(dir);
        let raw = read_bounded(&dir.join(MANIFEST), MAX_MANIFEST_BYTES)?;
        let full: Value = serde_json::from_slice(&raw)
            .map_err(|e| GeoError::Invalid(format!("{MANIFEST}: {e}")))?;
        let m: Manifest = serde_json::from_value(full.clone())
            .map_err(|e| GeoError::Invalid(format!("{MANIFEST}: {e}")))?;
        if m.schema != SCHEMA && m.schema != SCHEMA_V2 && m.schema != SCHEMA_V3 {
            return invalid(format!(
                "schema {} is not {SCHEMA}, {SCHEMA_V2} or {SCHEMA_V3}",
                m.schema
            ));
        }
        if !valid_id(&m.id) || m.id != folder {
            return invalid(format!(
                "id {:?} must be a valid id equal to the folder name {folder:?}",
                m.id
            ));
        }
        if m.name.trim().is_empty() || m.name.len() > 120 || m.summary.len() > 600 {
            return invalid("name or summary missing or too long");
        }
        let o = &m.origin;
        if !(-85.0..=85.0).contains(&finite(o.lat_deg, "origin latitude")?)
            || !(-180.0..=180.0).contains(&finite(o.lon_deg, "origin longitude")?)
            || !(-1000.0..=9000.0).contains(&finite(o.h_ellipsoid_m, "origin height")?)
        {
            return invalid("origin outside the accepted range");
        }
        let n0 = finite(o.geoid_undulation_m, "geoid undulation")?;
        if (o.orthometric_height_m + n0 - o.h_ellipsoid_m).abs() > 0.01 {
            return invalid(
                "origin heights are inconsistent: orthometric + undulation must equal ellipsoidal",
            );
        }
        if m.frame.kind != "enu-tangent-plane" || m.frame.ellipsoid != "WGS84" {
            return invalid("only WGS84 ENU tangent-plane packs are supported");
        }
        let heading = finite(m.frame.heading_deg, "heading")?;
        // The renderer draws model x, y as east, north: a rotated pack would put the drawn path
        // off its own geodetic readouts. Only heading 0 is accepted until the renderer rotates.
        if heading != 0.0 {
            return invalid("only packs with heading 0 are supported");
        }
        let extent = finite(m.extent_m, "extent")?;
        if !(extent > 0.0 && extent <= MAX_EXTENT_M) {
            return invalid(format!("extent must be in (0, {MAX_EXTENT_M}] m"));
        }

        let (base, hb) = read_grid(dir, &m.height, extent, HEIGHT_FILE)?;
        let ib = read_image(dir, &m.image, extent, IMAGE_FILE)?;
        let mut bytes = (raw.len() + hb.len() + ib.len()) as u64;

        // Optional layers (schema v2): at most one detail layer, nested inside the base.
        let v2 = m.schema == SCHEMA_V2 || m.schema == SCHEMA_V3;
        if !v2 && !m.layers.is_empty() {
            return invalid(format!("layers need schema {SCHEMA_V2} or later"));
        }
        let mut detail = None;
        for l in &m.layers {
            if l.role != "detail" || detail.is_some() {
                return invalid("only one layer, with the role \"detail\", is supported");
            }
            let ext = finite(l.extent_m, "detail extent")?;
            if !(ext > 0.0 && ext < extent) {
                return invalid("the detail layer must be smaller than the base extent");
            }
            let blend = finite(l.blend_m, "detail blend")?;
            if !(0.0..=ext / 4.0).contains(&blend) {
                return invalid("the detail blend must be in [0, extent / 4]");
            }
            if l.height.spacing_m > m.height.spacing_m || l.image.spacing_m > m.image.spacing_m {
                return invalid("the detail layer must not be coarser than the base");
            }
            let (g, dh) = read_grid(dir, &l.height, ext, DETAIL_HEIGHT_FILE)?;
            let di = read_image(dir, &l.image, ext, DETAIL_IMAGE_FILE)?;
            bytes += (dh.len() + di.len()) as u64;
            detail = Some(Detail {
                grid: g,
                blend_m: blend,
                height_sha: l.height.sha256.clone(),
                image_sha: l.image.sha256.clone(),
            });
        }

        // Optional world layer (schema v3). Vegetation lies within the detail layer when there is
        // one (it comes from the lidar there), else within the base.
        let wm = world::manifest_of(&full)?;
        if m.schema != SCHEMA_V3 && (wm.features.is_some() || wm.vegetation.is_some()) {
            return invalid(format!("a world layer needs schema {SCHEMA_V3}"));
        }
        let veg_half = detail.as_ref().map(|d| d.grid.half()).unwrap_or(extent);
        let world = world::open(dir, &wm, extent, veg_half)?;
        bytes += world.bytes;

        if m.sources.is_empty()
            || m.sources.iter().any(|x| {
                x.provider.trim().is_empty()
                    || x.product.trim().is_empty()
                    || x.licence.trim().is_empty()
                    || x.attribution.trim().is_empty()
            })
        {
            return invalid(
                "every source must name its provider, product, licence and attribution",
            );
        }
        check_descriptive(&m)?;
        // Building footprints are derived from OpenStreetMap: the ODbL requires that the database
        // keep its attribution and licence, so the pack must carry a source that says so, and the
        // credit the Studio puts on the map must name OpenStreetMap.
        if wm.features.is_some()
            && !m.sources.iter().any(|x| {
                x.licence.contains("ODbL")
                    && x.attribution.contains("OpenStreetMap")
                    && x.credit
                        .as_deref()
                        .unwrap_or(&x.attribution)
                        .contains("OpenStreetMap")
            })
        {
            return invalid(
                "a pack with building footprints needs a source whose licence names the ODbL and whose attribution and credit name OpenStreetMap",
            );
        }

        let frame = Enu::new(
            Geodetic::new(o.lat_deg, o.lon_deg, o.h_ellipsoid_m),
            heading,
        );
        let scale = m.height.scale_m;
        let mut env = Environment {
            id: m.id.clone(),
            dir: dir.to_path_buf(),
            frame,
            geoid_undulation_m: n0,
            base,
            detail,
            world,
            summary: Value::Null,
            bytes,
            image_sha: m.image.sha256.clone(),
            worst_check_m: 0.0,
        };

        // The origin is on the terrain, and every check point recomputes within tolerance.
        // The origin is on the finest layer.
        match env.terrain_up(0.0, 0.0) {
            Some(u) if u.abs() <= scale => {}
            other => return invalid(format!("the terrain at the origin is {other:?} m, not 0")),
        }
        if m.checks.is_empty() {
            return invalid("the manifest has no check points");
        }
        let mut worst: f64 = 0.0;
        for c in &m.checks {
            let enu = env
                .frame
                .enu_of(Geodetic::new(c.lat_deg, c.lon_deg, c.h_ellipsoid_m).to_ecef());
            let d = (0..3)
                .map(|k| (enu[k] - c.enu_m[k]).powi(2))
                .sum::<f64>()
                .sqrt();
            worst = worst.max(d);
            if d > CHECK_TOLERANCE_M {
                return invalid(format!(
                    "a check point recomputes {d:.4} m away from the manifest (tolerance {CHECK_TOLERANCE_M} m)"
                ));
            }
            let grid = match c.layer.as_deref() {
                None | Some("base") => Some(&env.base),
                Some("detail") => env.detail.as_ref().map(|d| &d.grid),
                Some(_) => None,
            };
            let Some(grid) = grid else {
                return invalid("a check point names a layer the pack does not have");
            };
            match grid.at(c.enu_m[0], c.enu_m[1]) {
                Some(u) if (u - c.enu_m[2]).abs() <= scale => {}
                other => {
                    return invalid(format!(
                        "the height grid at a check point is {other:?}, the manifest says {:.3}",
                        c.enu_m[2]
                    ));
                }
            }
        }
        env.worst_check_m = worst;
        env.summary = summary_of(&m, &full, &env);
        Ok(env)
    }

    /// Terrain ENU up at (east, north) on the drawn surface; `None` outside the pack. The detail
    /// layer wins where it covers the point; within `blend_m` of its edge it blends linearly into
    /// the base grid (as the Studio draws it).
    pub fn terrain_up(&self, e: f64, n: f64) -> Option<f64> {
        if let Some((d, u)) = self
            .detail
            .as_ref()
            .and_then(|d| d.grid.at(e, n).map(|u| (d, u)))
        {
            let inside = d.grid.half() - e.abs().max(n.abs());
            if d.blend_m <= 0.0 || inside >= d.blend_m {
                return Some(u);
            }
            let w = (inside / d.blend_m).clamp(0.0, 1.0);
            return Some(match self.base.at(e, n) {
                Some(b) => b + (u - b) * w,
                None => u,
            });
        }
        self.base.at(e, n)
    }

    /// The files of this pack, the manifest first.
    pub fn files(&self) -> Vec<&'static str> {
        let mut v = vec![MANIFEST, HEIGHT_FILE, IMAGE_FILE];
        if self.detail.is_some() {
            v.extend([DETAIL_HEIGHT_FILE, DETAIL_IMAGE_FILE]);
        }
        if self.world.features_sha.is_some() {
            v.push(FEATURES_FILE);
        }
        if self.world.vegetation_sha.is_some() {
            v.push(VEGETATION_FILE);
        }
        v
    }

    /// Places model points (x, y, z in the run's local frame) on the Earth.
    pub fn track(&self, points: &[[f64; 3]]) -> Vec<TrackPoint> {
        points
            .iter()
            .map(|p| {
                let enu = self.frame.enu_of_model(*p);
                let g = self.frame.ecef_of(enu).to_geodetic();
                let t = self.terrain_up(enu[0], enu[1]);
                TrackPoint {
                    lat_deg: g.lat_deg,
                    lon_deg: g.lon_deg,
                    h_ellipsoid_m: g.h_m,
                    h_msl_m: g.h_m - self.geoid_undulation_m,
                    terrain_up_m: t,
                    above_terrain_m: t.map(|u| enu[2] - u),
                }
            })
            .collect()
    }

    /// The manifest facts the interface shows (no file paths).
    pub fn summary(&self) -> &Value {
        &self.summary
    }

    /// Bytes of a pack file, re-read and re-checked against the manifest hash.
    pub fn file(&self, name: &str) -> Result<Vec<u8>, GeoError> {
        let (max, sha) = match name {
            HEIGHT_FILE => (
                MAX_HEIGHT_BYTES,
                self.summary["height"]["sha256"]
                    .as_str()
                    .unwrap_or("")
                    .to_string(),
            ),
            IMAGE_FILE => (MAX_IMAGE_BYTES, self.image_sha.clone()),
            DETAIL_HEIGHT_FILE if self.detail.is_some() => (
                MAX_HEIGHT_BYTES,
                self.detail
                    .as_ref()
                    .map(|d| d.height_sha.clone())
                    .unwrap_or_default(),
            ),
            DETAIL_IMAGE_FILE if self.detail.is_some() => (
                MAX_IMAGE_BYTES,
                self.detail
                    .as_ref()
                    .map(|d| d.image_sha.clone())
                    .unwrap_or_default(),
            ),
            FEATURES_FILE if self.world.features_sha.is_some() => (
                world::MAX_FEATURES_BYTES,
                self.world.features_sha.clone().unwrap_or_default(),
            ),
            VEGETATION_FILE if self.world.vegetation_sha.is_some() => (
                world::MAX_VEGETATION_BYTES,
                self.world.vegetation_sha.clone().unwrap_or_default(),
            ),
            _ => return invalid(format!("{name:?} is not a file of this environment pack")),
        };
        let b = read_bounded(&self.dir.join(name), max)?;
        if sha256_hex(&b) != sha {
            return invalid(format!(
                "{name} changed on disk since the pack was validated"
            ));
        }
        Ok(b)
    }

    pub fn bytes(&self) -> u64 {
        self.bytes
    }

    pub fn worst_check_m(&self) -> f64 {
        self.worst_check_m
    }
}

/// Bounds on the descriptive text the interface shows: sources, accuracy notes, relief and build
/// facts. Types are enforced by deserialisation; this bounds sizes and refuses control characters.
fn check_descriptive(m: &Manifest) -> Result<(), GeoError> {
    let bad = |what: &str| invalid_err(format!("{what} is not valid text of bounded size"));
    if m.sources.len() > MAX_SOURCES {
        return invalid(format!("more than {MAX_SOURCES} sources"));
    }
    for s in &m.sources {
        let credit_ok = s
            .credit
            .as_deref()
            .is_none_or(|c| world::text_ok(c, MAX_CREDIT));
        let more_ok = [s.access.as_deref(), s.layer.as_deref()]
            .into_iter()
            .flatten()
            .all(|t| world::text_ok(t, MAX_SOURCE_TEXT));
        if ![&s.provider, &s.product, &s.licence, &s.attribution]
            .into_iter()
            .all(|t| world::text_ok(t, MAX_SOURCE_TEXT))
            || !credit_ok
            || !more_ok
        {
            return bad("a source field");
        }
    }
    if let Some(n) = &m.site_note
        && !world::text_ok(n, 600)
    {
        return bad("site_note");
    }
    if let Some(a) = &m.accuracy
        && (a.len() > MAX_ACCURACY_NOTES || a.iter().any(|t| !world::text_ok(t, MAX_NOTE)))
    {
        return bad("accuracy");
    }
    if let Some(r) = &m.relief
        && (r.len() > 16
            || r.iter().any(|x| {
                ![x.radius_m, x.min_up_m, x.max_up_m]
                    .iter()
                    .all(|v| v.is_finite())
            }))
    {
        return bad("relief");
    }
    if let Some(b) = &m.built
        && (b.len() > 32
            || b.iter().any(|(k, v)| {
                !world::text_ok(k, 64)
                    || match v {
                        Value::String(t) => !world::text_ok(t, 200),
                        Value::Number(_) | Value::Bool(_) => false,
                        _ => true,
                    }
            }))
    {
        return bad("built");
    }
    Ok(())
}

/// The manifest facts the interface shows (no file paths), built from validated, typed fields and
/// from the world layer's recomputed counts, never from the manifest's raw JSON.
fn summary_of(m: &Manifest, full: &Value, env: &Environment) -> Value {
    let pick = |k: &str| full.get(k).cloned().unwrap_or(Value::Null);
    let sources: Vec<Value> = m
        .sources
        .iter()
        .map(|s| {
            json!({
                "provider": s.provider,
                "product": s.product,
                "licence": s.licence,
                "attribution": s.attribution,
                "credit": s.credit,
                "access": s.access,
                "layer": s.layer,
            })
        })
        .collect();
    json!({
        "schema": m.schema,
        "id": env.id,
        "name": m.name,
        "summary": m.summary,
        "site_note": m.site_note,
        "origin": pick("origin"),
        "frame": pick("frame"),
        "extent_m": m.extent_m,
        "height": pick("height"),
        "image": pick("image"),
        "layers": full.get("layers").cloned().unwrap_or_else(|| json!([])),
        "relief": m.relief,
        "accuracy": m.accuracy,
        "sources": sources,
        "built": m.built,
        "world": env.world.summary,
        "bytes": env.bytes,
        "checks": m.checks.len(),
        "worst_check_m": env.worst_check_m,
    })
}

/// Validates every pack folder under `root`. Returns the accepted packs and, for each rejected
/// folder, its name and the reason. Missing roots are empty.
pub fn discover(root: &Path) -> (Vec<Environment>, Vec<(String, String)>) {
    let mut ok = Vec::new();
    let mut bad = Vec::new();
    let Ok(rd) = fs::read_dir(root) else {
        return (ok, bad);
    };
    let mut dirs: Vec<PathBuf> = rd
        .flatten()
        .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
        .map(|e| e.path())
        .collect();
    dirs.sort();
    for d in dirs {
        let name = file_name(&d);
        if name.starts_with('.') {
            continue;
        }
        match Environment::open(&d) {
            Ok(e) => ok.push(e),
            Err(e) => bad.push((name, e.to_string())),
        }
    }
    (ok, bad)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn packs() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../environments")
    }

    fn copy_pack(id: &str, to: &Path) -> PathBuf {
        let dst = to.join(id);
        fs::create_dir_all(&dst).unwrap();
        let src = Environment::open(&packs().join(id)).unwrap();
        for f in src.files() {
            fs::copy(packs().join(id).join(f), dst.join(f)).unwrap();
        }
        dst
    }

    fn scratch(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("vv-geo-test-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn shipped_packs_validate_and_recompute_their_checks() {
        for id in ["cape-canaveral", "santa-maria-azores"] {
            let e = Environment::open(&packs().join(id)).unwrap_or_else(|e| panic!("{id}: {e}"));
            assert!(
                e.worst_check_m() < CHECK_TOLERANCE_M,
                "{id}: {}",
                e.worst_check_m()
            );
            assert_eq!(e.terrain_up(0.0, 0.0).map(|u| u.abs() < 0.011), Some(true));
            assert!(e.summary()["sources"].as_array().unwrap().len() >= 2);
        }
    }

    #[test]
    fn shipped_packs_carry_a_valid_world_layer() {
        // Cape Canaveral and Spaceport America have lidar vegetation; Santa Maria has OSM
        // buildings and, without lidar, no vegetation at all.
        for (id, veg) in [
            ("cape-canaveral", true),
            ("spaceport-america", true),
            ("santa-maria-azores", false),
        ] {
            let e = Environment::open(&packs().join(id)).unwrap_or_else(|e| panic!("{id}: {e}"));
            let w = &e.summary()["world"];
            assert_eq!(e.summary()["schema"], json!(SCHEMA_V3), "{id}");
            assert!(w["features"]["buildings"].as_u64().unwrap() > 0, "{id}");
            assert_eq!(w["vegetation"].is_object(), veg, "{id}");
            assert!(e.files().contains(&FEATURES_FILE));
            assert_eq!(e.files().contains(&VEGETATION_FILE), veg);
            assert!(e.file(FEATURES_FILE).is_ok(), "{id}");
        }
    }

    /// Every pack of the package index (scripts/geo/environment-index.json) validates, with the
    /// schema and the file list the index records. Bundled packs are in the repository; catalogue
    /// packs are not, so they are checked from the unpacked zips in the folder named by
    /// `VV_GEO_PACK_ROOT` (one sub-folder per id). When that variable is set, a missing pack fails.
    #[test]
    fn indexed_packs_validate_with_the_indexed_schema_and_files() {
        let index_path =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../scripts/geo/environment-index.json");
        let index: Value = serde_json::from_slice(&fs::read(&index_path).unwrap()).unwrap();
        assert_eq!(index["schema"], json!("vv-geo-environment-index.v1"));
        let root = std::env::var_os("VV_GEO_PACK_ROOT").map(PathBuf::from);
        let (mut bundled, mut catalogue, mut unchecked) = (0, 0, Vec::new());
        for e in index["environments"].as_array().unwrap() {
            let id = e["id"].as_str().unwrap();
            let dir = if e["bundled"] == json!(true) {
                packs().join(id)
            } else if let Some(r) = &root {
                r.join(id)
            } else {
                unchecked.push(id.to_string());
                continue;
            };
            let env = Environment::open(&dir).unwrap_or_else(|err| panic!("{id}: {err}"));
            assert_eq!(env.summary()["schema"], e["schema"], "{id}");
            let mut want: Vec<&str> = e["files"]
                .as_array()
                .unwrap()
                .iter()
                .map(|f| f.as_str().unwrap())
                .collect();
            assert_eq!(want.pop(), Some("NOTICE.md"), "{id}");
            assert_eq!(env.files(), want, "{id}");
            assert!(env.worst_check_m() < CHECK_TOLERANCE_M, "{id}");
            if e["bundled"] == json!(true) {
                bundled += 1;
            } else {
                catalogue += 1;
            }
        }
        assert_eq!(bundled, 8, "all eight packs are bundled and indexed");
        if !unchecked.is_empty() {
            eprintln!(
                "catalogue packs not checked (set VV_GEO_PACK_ROOT to the unpacked zips): {unchecked:?}"
            );
        }
        eprintln!("indexed packs validated: {bundled} bundled, {catalogue} from the catalogue");
    }

    #[test]
    fn the_origin_of_a_track_is_the_pack_origin() {
        let e = Environment::open(&packs().join("cape-canaveral")).unwrap();
        let t = e.track(&[[0.0, 0.0, 0.0], [0.0, 0.0, 3000.0]]);
        let o = e.frame.origin;
        assert!(
            (t[0].lat_deg - o.lat_deg).abs() < 1e-12 && (t[0].lon_deg - o.lon_deg).abs() < 1e-12
        );
        assert!((t[0].h_ellipsoid_m - o.h_m).abs() < 1e-6);
        assert!((t[1].h_ellipsoid_m - o.h_m - 3000.0).abs() < 1e-6);
        assert!((t[0].above_terrain_m.unwrap()).abs() < 0.011);
        // Orthometric height of the origin is the DEM height there.
        assert!((t[0].h_msl_m - (o.h_m - e.geoid_undulation_m)).abs() < 1e-6);
    }

    #[test]
    fn a_point_outside_the_pack_has_no_terrain() {
        let e = Environment::open(&packs().join("cape-canaveral")).unwrap();
        let t = e.track(&[[60_000.0, 0.0, 10.0]]);
        assert!(t[0].terrain_up_m.is_none() && t[0].above_terrain_m.is_none());
    }

    #[test]
    fn a_tampered_height_grid_is_rejected() {
        let d = scratch("tamper-height");
        let p = copy_pack("cape-canaveral", &d);
        let mut b = fs::read(p.join(HEIGHT_FILE)).unwrap();
        b[1000] ^= 1;
        fs::write(p.join(HEIGHT_FILE), b).unwrap();
        let e = Environment::open(&p).unwrap_err();
        assert!(e.to_string().contains("SHA-256"), "{e}");
        let _ = fs::remove_dir_all(d);
    }

    #[test]
    fn a_moved_origin_is_rejected_by_the_check_points() {
        let d = scratch("moved-origin");
        let p = copy_pack("cape-canaveral", &d);
        let mut m: Value = serde_json::from_slice(&fs::read(p.join(MANIFEST)).unwrap()).unwrap();
        // Ten metres north: hashes still match, but the recomputed check points do not.
        let lat = m["origin"]["lat_deg"].as_f64().unwrap();
        m["origin"]["lat_deg"] = json!(lat + 10.0 / 111_000.0);
        fs::write(p.join(MANIFEST), serde_json::to_vec(&m).unwrap()).unwrap();
        let e = Environment::open(&p).unwrap_err();
        assert!(e.to_string().contains("check point"), "{e}");
        let _ = fs::remove_dir_all(d);
    }

    #[test]
    fn unknown_files_ids_and_schemas_are_rejected() {
        let d = scratch("names");
        let p = copy_pack("cape-canaveral", &d);
        let e = Environment::open(&p).unwrap();
        assert!(e.file("../environment.json").is_err());
        assert!(e.file("environment.json").is_err());
        assert!(e.file(IMAGE_FILE).is_ok());
        let renamed = d.join("Cape");
        fs::rename(&p, &renamed).unwrap();
        assert!(
            Environment::open(&renamed)
                .unwrap_err()
                .to_string()
                .contains("folder name")
        );
        fs::rename(&renamed, &p).unwrap();
        let mut m: Value = serde_json::from_slice(&fs::read(p.join(MANIFEST)).unwrap()).unwrap();
        m["schema"] = json!("vv-geo-environment.v0");
        fs::write(p.join(MANIFEST), serde_json::to_vec(&m).unwrap()).unwrap();
        assert!(
            Environment::open(&p)
                .unwrap_err()
                .to_string()
                .contains("schema")
        );
        assert!(!valid_id("-x") && !valid_id("a/b") && !valid_id("") && valid_id("cape-canaveral"));
        assert!(
            !valid_id("con")
                && !valid_id("nul")
                && !valid_id("com1")
                && !valid_id("lpt9")
                && valid_id("console")
        );
        let _ = fs::remove_dir_all(d);
    }

    #[test]
    fn an_image_whose_real_size_differs_from_the_manifest_is_rejected() {
        let d = scratch("jpeg-size");
        let p = copy_pack("cape-canaveral", &d);
        let mut b = fs::read(p.join(IMAGE_FILE)).unwrap();
        assert_eq!(jpeg_size(&b), Some((1800, 1800)));
        // Forge the start-of-frame height to 65535 and update the manifest hash to match.
        let i = (2..b.len() - 9)
            .find(|&i| b[i] == 0xFF && (0xC0..=0xC2).contains(&b[i + 1]))
            .unwrap();
        b[i + 5] = 0xFF;
        b[i + 6] = 0xFF;
        fs::write(p.join(IMAGE_FILE), &b).unwrap();
        let mut m: Value = serde_json::from_slice(&fs::read(p.join(MANIFEST)).unwrap()).unwrap();
        m["image"]["sha256"] = json!(sha256_hex(&b));
        fs::write(p.join(MANIFEST), serde_json::to_vec(&m).unwrap()).unwrap();
        let e = Environment::open(&p).unwrap_err();
        assert!(e.to_string().contains("pixels"), "{e}");
        let _ = fs::remove_dir_all(d);
    }

    #[test]
    fn a_file_changed_after_validation_is_refused() {
        let d = scratch("changed");
        let p = copy_pack("cape-canaveral", &d);
        let e = Environment::open(&p).unwrap();
        let mut b = fs::read(p.join(IMAGE_FILE)).unwrap();
        let last = b.len() - 3;
        b[last] ^= 0x55;
        fs::write(p.join(IMAGE_FILE), b).unwrap();
        assert!(
            e.file(IMAGE_FILE)
                .unwrap_err()
                .to_string()
                .contains("changed on disk")
        );
        let _ = fs::remove_dir_all(d);
    }

    #[test]
    fn discover_lists_good_and_rejected_packs() {
        let d = scratch("discover");
        copy_pack("cape-canaveral", &d);
        fs::create_dir_all(d.join("broken")).unwrap();
        fs::write(d.join("broken").join(MANIFEST), b"{}").unwrap();
        let (ok, bad) = discover(&d);
        assert_eq!(ok.len(), 1);
        assert_eq!(bad.len(), 1);
        assert_eq!(bad[0].0, "broken");
        let (none, none_bad) = discover(&d.join("missing"));
        assert!(none.is_empty() && none_bad.is_empty());
        let _ = fs::remove_dir_all(d);
    }

    // ------------------------------------------------------------------ synthetic packs (v1, v2)

    const TINY_JPEG: &[u8] = include_bytes!("../tests/fixtures/tiny16.jpg");

    /// Writes a square height grid with heights `f(e, n)` and returns its manifest block.
    fn grid(dir: &Path, name: &str, half: f64, spacing: f64, f: &dyn Fn(f64, f64) -> f64) -> Value {
        let k = (half / spacing).round() as i64;
        let n = (2 * k + 1) as usize;
        let (scale, offset) = (0.01, -100.0);
        let mut b = Vec::with_capacity(n * n * 2);
        for r in 0..n {
            for c in 0..n {
                let e = (c as i64 - k) as f64 * spacing;
                let nn = (k - r as i64) as f64 * spacing;
                let q = ((f(e, nn) - offset) / scale).round() as u16;
                b.extend_from_slice(&q.to_le_bytes());
            }
        }
        fs::write(dir.join(name), &b).unwrap();
        json!({"file": name, "encoding": "uint16-le", "scale_m": scale, "offset_m": offset, "columns": n, "rows": n,
               "spacing_m": spacing, "first_node_m": [-(k as f64) * spacing, k as f64 * spacing], "bytes": b.len(), "sha256": sha256_hex(&b)})
    }

    fn image(dir: &Path, name: &str, half: f64) -> Value {
        fs::write(dir.join(name), TINY_JPEG).unwrap();
        let sp = 2.0 * half / 16.0;
        json!({"file": name, "columns": 16, "rows": 16, "spacing_m": sp, "first_texel_centre_m": [-half + sp / 2.0, half - sp / 2.0],
               "bytes": TINY_JPEG.len(), "sha256": sha256_hex(TINY_JPEG)})
    }

    /// A pack with a 300 m base and, when `detail`, a 100 m detail layer at 0 m over a base at
    /// 10 m, blending over its outer 20 m. Check points come from this crate's own geodesy.
    fn synthetic(id: &str, detail: bool) -> (PathBuf, PathBuf) {
        let root = scratch(id);
        let dir = root.join(id);
        fs::create_dir_all(&dir).unwrap();
        let base_up = if detail { 10.0 } else { 0.0 };
        let frame = Enu::new(Geodetic::new(28.5, -80.5, 0.0), 0.0);
        let check = |e: f64, n: f64, u: f64, layer: &str| {
            let g = frame.ecef_of([e, n, u]).to_geodetic();
            json!({"lat_deg": g.lat_deg, "lon_deg": g.lon_deg, "h_ellipsoid_m": g.h_m, "enu_m": [e, n, u], "layer": layer})
        };
        let mut m = json!({
            "schema": if detail { SCHEMA_V2 } else { SCHEMA },
            "id": id, "name": "Synthetic", "summary": "Test pack.",
            "origin": {"lat_deg": 28.5, "lon_deg": -80.5, "h_ellipsoid_m": 0.0, "orthometric_height_m": 0.0, "geoid_undulation_m": 0.0},
            "frame": {"kind": "enu-tangent-plane", "ellipsoid": "WGS84", "heading_deg": 0.0},
            "extent_m": 300.0,
            "height": grid(&dir, HEIGHT_FILE, 300.0, 100.0, &|_, _| base_up),
            "image": image(&dir, IMAGE_FILE, 300.0),
            "sources": [{"provider": "test", "product": "test", "licence": "test", "attribution": "test"}],
            "checks": [check(200.0, 200.0, base_up, "base")],
        });
        if detail {
            m["layers"] = json!([{"role": "detail", "extent_m": 100.0, "blend_m": 20.0,
                "height": grid(&dir, DETAIL_HEIGHT_FILE, 100.0, 25.0, &|_, _| 0.0),
                "image": image(&dir, DETAIL_IMAGE_FILE, 100.0)}]);
            m["checks"]
                .as_array_mut()
                .unwrap()
                .push(check(50.0, 50.0, 0.0, "detail"));
        }
        fs::write(dir.join(MANIFEST), serde_json::to_vec(&m).unwrap()).unwrap();
        (root, dir)
    }

    fn edit(dir: &Path, f: impl FnOnce(&mut Value)) {
        let mut m: Value = serde_json::from_slice(&fs::read(dir.join(MANIFEST)).unwrap()).unwrap();
        f(&mut m);
        fs::write(dir.join(MANIFEST), serde_json::to_vec(&m).unwrap()).unwrap();
    }

    #[test]
    fn a_v1_pack_without_layers_still_opens() {
        let (root, dir) = synthetic("syn-v1", false);
        let e = Environment::open(&dir).unwrap_or_else(|e| panic!("{e}"));
        assert_eq!(e.files(), vec![MANIFEST, HEIGHT_FILE, IMAGE_FILE]);
        assert!(e.file(DETAIL_HEIGHT_FILE).is_err());
        assert_eq!(e.summary()["layers"], json!([]));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn the_detail_layer_is_the_terrain_and_blends_into_the_base_at_its_edge() {
        let (root, dir) = synthetic("syn-v2", true);
        let e = Environment::open(&dir).unwrap_or_else(|e| panic!("{e}"));
        let near = |a: Option<f64>, b: f64| (a.unwrap() - b).abs() < 0.011;
        assert!(
            near(e.terrain_up(0.0, 0.0), 0.0),
            "the origin is on the detail layer"
        );
        assert!(
            near(e.terrain_up(50.0, -50.0), 0.0),
            "inside the detail interior"
        );
        assert!(
            near(e.terrain_up(90.0, 0.0), 5.0),
            "half way through the 20 m blend"
        );
        assert!(
            near(e.terrain_up(0.0, 100.0), 10.0),
            "at the detail edge the base takes over"
        );
        assert!(
            near(e.terrain_up(200.0, 0.0), 10.0),
            "outside the detail layer"
        );
        assert!(e.terrain_up(400.0, 0.0).is_none());
        assert_eq!(e.files().len(), 5);
        assert!(e.file(DETAIL_IMAGE_FILE).is_ok() && e.file(DETAIL_HEIGHT_FILE).is_ok());
        assert!(e.file("horizon-image.jpg").is_err());
        assert_eq!(e.summary()["layers"][0]["role"], json!("detail"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn layers_need_schema_v2_and_must_nest_inside_the_base() {
        let (root, dir) = synthetic("syn-rules", true);
        let reason = |d: &Path| Environment::open(d).unwrap_err().to_string();
        edit(&dir, |m| m["schema"] = json!(SCHEMA));
        assert!(reason(&dir).contains("schema"));
        edit(&dir, |m| {
            m["schema"] = json!(SCHEMA_V2);
            m["layers"][0]["extent_m"] = json!(400.0);
        });
        assert!(reason(&dir).contains("smaller"));
        edit(&dir, |m| {
            m["layers"][0]["extent_m"] = json!(100.0);
            m["layers"][0]["blend_m"] = json!(30.0);
        });
        assert!(reason(&dir).contains("blend"));
        edit(&dir, |m| {
            m["layers"][0]["blend_m"] = json!(20.0);
            m["layers"][0]["role"] = json!("horizon");
        });
        assert!(reason(&dir).contains("detail"));
        edit(&dir, |m| {
            m["layers"][0]["role"] = json!("detail");
            m["checks"][1]["layer"] = json!("other");
        });
        assert!(reason(&dir).contains("layer"));
        edit(&dir, |m| m["checks"][1]["layer"] = json!("detail"));
        assert!(Environment::open(&dir).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn a_tampered_detail_file_is_rejected_by_name() {
        let (root, dir) = synthetic("syn-tamper", true);
        let mut b = fs::read(dir.join(DETAIL_HEIGHT_FILE)).unwrap();
        b[10] ^= 1;
        fs::write(dir.join(DETAIL_HEIGHT_FILE), b).unwrap();
        let e = Environment::open(&dir).unwrap_err().to_string();
        assert!(
            e.contains(DETAIL_HEIGHT_FILE) && e.contains("SHA-256"),
            "{e}"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn the_origin_must_be_on_the_finest_layer() {
        let (root, dir) = synthetic("syn-origin", true);
        // A detail grid 3 m above the origin: the base would put z = 0 elsewhere.
        let h = grid(&dir, DETAIL_HEIGHT_FILE, 100.0, 25.0, &|_, _| 3.0);
        edit(&dir, |m| m["layers"][0]["height"] = h);
        let e = Environment::open(&dir).unwrap_err().to_string();
        assert!(e.contains("origin"), "{e}");
        let _ = fs::remove_dir_all(root);
    }

    // ------------------------------------------------------------------ world layer (v3)

    fn veg_record(x: i16, y: i16, h_cm: u16, crown: u8, kind: u8) -> Vec<u8> {
        let mut r = Vec::with_capacity(12);
        r.extend_from_slice(&x.to_le_bytes());
        r.extend_from_slice(&y.to_le_bytes());
        r.extend_from_slice(&h_cm.to_le_bytes());
        r.extend_from_slice(&[crown, kind, 90, 110, 70, 0]);
        r
    }

    /// Writes a world layer (one building, one lidar structure, one tower, two plants) and
    /// declares it in the manifest as schema v3.
    fn add_world(dir: &Path, features: Value, veg: &[u8]) {
        let fb = serde_json::to_vec(&features).unwrap();
        fs::write(dir.join(FEATURES_FILE), &fb).unwrap();
        fs::write(dir.join(VEGETATION_FILE), veg).unwrap();
        let n = |k: &str| features[k].as_array().map(|a| a.len()).unwrap_or(0);
        let (b, l, s) = (n("buildings"), n("lidar_structures"), n("structures"));
        edit(dir, |m| {
            m["schema"] = json!(SCHEMA_V3);
            m["sources"] = json!([
                {"provider": "test", "product": "test", "licence": "test", "attribution": "test"},
                {"provider": "OpenStreetMap contributors", "product": "building footprints",
                 "licence": "Open Data Commons Open Database License (ODbL) 1.0",
                 "attribution": "Buildings: (c) OpenStreetMap contributors, ODbL 1.0",
                 "credit": "(c) OpenStreetMap contributors"},
            ]);
            m["world"] = json!({
                "features": {"file": FEATURES_FILE, "bytes": fb.len(), "sha256": sha256_hex(&fb),
                             "buildings": b, "lidar_structures": l, "structures": s},
                "vegetation": {"file": VEGETATION_FILE, "bytes": veg.len(), "sha256": sha256_hex(veg), "count": veg.len() / 12},
            });
        });
    }

    fn features() -> Value {
        json!({
            "schema": world::FEATURES_SCHEMA, "units": "dm", "osm_timestamp": "2026-11-04T00:00:00Z",
            "buildings": [{"id": "w1", "kind": "yes", "h_dm": 60, "hs": "lidar", "roof": [120, 118, 110], "ring_dm": [100, 100, 300, 100, 300, 300, 100, 300]}],
            "lidar_structures": [{"id": "lidar-1", "kind": "lidar-structure", "h_dm": 40, "hs": "lidar", "roof": [90, 90, 90], "ring_dm": [-300, -300, -200, -300, -200, -200]}],
            "structures": [{"id": "n1", "kind": "tower", "x_dm": 500, "y_dm": -500, "h_dm": 300, "r_dm": 15, "hs": "default", "name": null}],
        })
    }

    #[test]
    fn a_v3_world_layer_opens_and_its_files_are_served_by_hash() {
        let (root, dir) = synthetic("syn-v3", true);
        let veg = [
            veg_record(100, -100, 450, 25, 1),
            veg_record(-200, 50, 150, 12, 0),
        ]
        .concat();
        add_world(&dir, features(), &veg);
        let e = Environment::open(&dir).unwrap_or_else(|e| panic!("{e}"));
        assert_eq!(e.files().len(), 7);
        assert!(e.file(FEATURES_FILE).is_ok() && e.file(VEGETATION_FILE).is_ok());
        assert_eq!(e.summary()["world"]["vegetation"]["count"], json!(2));
        // Changed after validation: refused when handed over.
        fs::write(
            dir.join(VEGETATION_FILE),
            [veg.clone(), veg_record(0, 0, 100, 10, 0)].concat(),
        )
        .unwrap();
        assert!(
            e.file(VEGETATION_FILE)
                .unwrap_err()
                .to_string()
                .contains("changed on disk")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn world_layer_rules_are_enforced() {
        let (root, dir) = synthetic("syn-v3-rules", true);
        let reason = |d: &Path| Environment::open(d).unwrap_err().to_string();
        let ok_veg = veg_record(100, -100, 450, 25, 1);
        // A world layer needs schema v3.
        add_world(&dir, features(), &ok_veg);
        edit(&dir, |m| m["schema"] = json!(SCHEMA_V2));
        assert!(reason(&dir).contains("v3"));
        // Clockwise footprint.
        let mut f = features();
        f["buildings"][0]["ring_dm"] = json!([100, 100, 100, 300, 300, 300, 300, 100]);
        add_world(&dir, f, &ok_veg);
        assert!(reason(&dir).contains("counter-clockwise"));
        // Unknown height source.
        let mut f = features();
        f["buildings"][0]["hs"] = json!("guess");
        add_world(&dir, f, &ok_veg);
        assert!(reason(&dir).contains("height source"));
        // A lidar structure must carry a lidar height.
        let mut f = features();
        f["lidar_structures"][0]["hs"] = json!("default");
        add_world(&dir, f, &ok_veg);
        assert!(reason(&dir).contains("lidar height"));
        // Unknown fields are refused.
        let mut f = features();
        f["buildings"][0]["script"] = json!("x");
        add_world(&dir, f, &ok_veg);
        assert!(reason(&dir).contains("features.json"));
        // Vegetation outside the detail layer (100 m), or with an unknown kind.
        add_world(&dir, features(), &veg_record(1500, 0, 450, 25, 1));
        assert!(reason(&dir).contains("out of range"));
        add_world(&dir, features(), &veg_record(10, 0, 450, 25, 7));
        assert!(reason(&dir).contains("out of range"));
        // Count mismatch.
        add_world(&dir, features(), &ok_veg);
        edit(&dir, |m| m["world"]["features"]["buildings"] = json!(5));
        assert!(reason(&dir).contains("counts"));
        // Tampered file.
        add_world(&dir, features(), &ok_veg);
        let mut b = fs::read(dir.join(FEATURES_FILE)).unwrap();
        b[5] ^= 1;
        fs::write(dir.join(FEATURES_FILE), b).unwrap();
        assert!(reason(&dir).contains("SHA-256"));
        add_world(&dir, features(), &ok_veg);
        assert!(Environment::open(&dir).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    // ------------------------------------------------------- tampered manifests and limits

    fn open_world(id: &str) -> (PathBuf, PathBuf) {
        let (root, dir) = synthetic(id, true);
        let veg = [
            veg_record(100, -100, 450, 25, 1),
            veg_record(-200, 50, 150, 12, 0),
        ]
        .concat();
        add_world(&dir, features(), &veg);
        (root, dir)
    }

    fn reason(d: &Path) -> String {
        Environment::open(d).unwrap_err().to_string()
    }

    #[test]
    fn the_summary_recomputes_world_counts_from_the_hashed_files() {
        let (root, dir) = open_world("syn-w-recompute");
        // Counts left out of the manifest are still reported, from the files.
        let w = Environment::open(&dir).unwrap().summary()["world"].clone();
        assert_eq!(w["features"]["height_sources"], json!({"lidar": 1}));
        assert_eq!(w["features"]["buildings"], json!(1));
        assert_eq!(w["vegetation"]["trees"], json!(1));
        assert_eq!(w["vegetation"]["shrubs"], json!(1));
        // Declared correctly (zero counts allowed), the same.
        edit(&dir, |m| {
            m["world"]["features"]["height_sources"] = json!({"lidar": 1, "default": 0});
            m["world"]["vegetation"]["trees"] = json!(1);
            m["world"]["vegetation"]["shrubs"] = json!(1);
        });
        assert!(Environment::open(&dir).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn a_manifest_claiming_other_heights_or_plants_than_its_files_is_rejected() {
        let (root, dir) = open_world("syn-w-claims");
        // The file says the one building height is lidar. Claim two, then a default one.
        edit(&dir, |m| {
            m["world"]["features"]["height_sources"] = json!({"lidar": 2});
        });
        assert!(
            reason(&dir).contains("sources of height"),
            "{}",
            reason(&dir)
        );
        edit(&dir, |m| {
            m["world"]["features"]["height_sources"] = json!({"default": 1});
        });
        assert!(reason(&dir).contains("sources of height"));
        edit(&dir, |m| {
            m["world"]["features"]["height_sources"] = json!({"lidar": "many"});
        });
        assert!(reason(&dir).contains("world"));
        edit(&dir, |m| {
            m["world"]["features"]["height_sources"] = json!({"lidar": 1});
            m["world"]["vegetation"]["trees"] = json!(500);
        });
        assert!(reason(&dir).contains("tree and shrub"));
        edit(&dir, |m| {
            m["world"]["vegetation"]["trees"] = json!(1);
            m["world"]["vegetation"]["shrubs"] = json!(9);
        });
        assert!(reason(&dir).contains("tree and shrub"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn descriptive_manifest_fields_of_another_type_are_rejected() {
        let (root, dir) = open_world("syn-w-types");
        let ok_source =
            json!({"provider": "p", "product": "p", "licence": "l", "attribution": "a"});
        let mut bad_credit = ok_source.clone();
        bad_credit["credit"] = json!({"x": 1});
        let cases: [(&str, Value); 9] = [
            ("site_note", json!({"x": 1})),
            ("accuracy", json!("a string, not a list")),
            ("accuracy", json!([1, 2])),
            (
                "relief",
                json!([{"radius_m": "ten", "min_up_m": 0, "max_up_m": 1}]),
            ),
            ("relief", json!({"a": 1})),
            ("built", json!({"by": ["x"]})),
            ("built", json!("script")),
            ("sources", json!([bad_credit])),
            ("name", json!(["x"])),
        ];
        for (k, v) in cases {
            let keep = {
                let m: Value =
                    serde_json::from_slice(&fs::read(dir.join(MANIFEST)).unwrap()).unwrap();
                m[k].clone()
            };
            edit(&dir, |m| m[k] = v);
            assert!(Environment::open(&dir).is_err(), "{k} accepted");
            edit(&dir, |m| m[k] = keep);
        }
        // Unbounded or control-character text is refused as well.
        edit(&dir, |m| m["site_note"] = json!("x".repeat(601)));
        assert!(reason(&dir).contains("site_note"));
        edit(&dir, |m| m["site_note"] = json!("bad\u{7}note"));
        assert!(reason(&dir).contains("site_note"));
        edit(&dir, |m| m["site_note"] = Value::Null);
        edit(&dir, |m| m["world"]["features"]["accuracy"] = json!(42));
        assert!(reason(&dir).contains("world"));
        edit(&dir, |m| m["world"]["features"]["accuracy"] = json!("fine"));
        assert!(Environment::open(&dir).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn the_summary_carries_only_typed_descriptive_fields() {
        let (root, dir) = open_world("syn-w-typed-summary");
        edit(&dir, |m| {
            m["site_note"] = json!("A note.");
            m["accuracy"] = json!(["one", "two"]);
            m["relief"] = json!([{"radius_m": 10.0, "min_up_m": -1.0, "max_up_m": 1.0}]);
            m["built"] = json!({"by": "script", "date": "2026-11-04"});
            m["world"]["lidar"] = json!({"anything": {"nested": [1, 2, 3]}});
            m["sources"][0]["items"] = json!({"unchecked": true});
        });
        let e = Environment::open(&dir).unwrap();
        let s = e.summary();
        assert_eq!(s["accuracy"], json!(["one", "two"]));
        assert_eq!(s["relief"][0]["radius_m"], json!(10.0));
        assert_eq!(s["built"]["by"], json!("script"));
        assert!(s["world"].get("lidar").is_none());
        assert!(s["sources"][0].get("items").is_none());
        assert_eq!(
            s["sources"][1]["credit"],
            json!("(c) OpenStreetMap contributors")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn building_footprints_need_an_odbl_openstreetmap_source() {
        let (root, dir) = open_world("syn-w-odbl");
        let plain = json!([{"provider": "t", "product": "t", "licence": "t", "attribution": "t"}]);
        edit(&dir, |m| m["sources"] = plain.clone());
        assert!(reason(&dir).contains("ODbL") && reason(&dir).contains("OpenStreetMap"));
        // The licence alone, or the attribution alone, is not enough.
        edit(&dir, |m| {
            m["sources"] = json!([{"provider": "t", "product": "t", "licence": "ODbL 1.0", "attribution": "somebody"}]);
        });
        assert!(reason(&dir).contains("OpenStreetMap"));
        edit(&dir, |m| {
            m["sources"] = json!([{"provider": "t", "product": "t", "licence": "CC0", "attribution": "OpenStreetMap contributors"}]);
        });
        assert!(reason(&dir).contains("ODbL"));
        // A credit that does not name OpenStreetMap would replace it on the map.
        edit(&dir, |m| {
            m["sources"] = json!([{"provider": "t", "product": "t", "licence": "ODbL 1.0", "attribution": "OpenStreetMap contributors", "credit": "Nothing to see"}]);
        });
        assert!(reason(&dir).contains("credit name OpenStreetMap"));
        edit(&dir, |m| {
            m["sources"] = json!([{"provider": "t", "product": "t", "licence": "ODbL 1.0", "attribution": "OpenStreetMap contributors"}]);
        });
        assert!(Environment::open(&dir).is_ok());
        // Lidar vegetation alone does not need it.
        edit(&dir, |m| {
            m["world"]["features"] = Value::Null;
            m["sources"] = plain.clone();
        });
        assert!(Environment::open(&dir).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn huge_images_and_grids_are_refused_before_their_files_are_read() {
        let (root, dir) = synthetic("syn-caps", false);
        // 9000 x 9000 is inside 16..16384 a side but is 81 million texels (8192 x 8192 is the cap).
        edit(&dir, |m| {
            m["image"]["columns"] = json!(9000);
            m["image"]["rows"] = json!(9000);
        });
        assert!(
            reason(&dir).contains("texels is more than"),
            "{}",
            reason(&dir)
        );
        edit(&dir, |m| {
            m["image"]["columns"] = json!(16);
            m["image"]["rows"] = json!(16);
            m["height"]["columns"] = json!(2500);
            m["height"]["rows"] = json!(2500);
        });
        assert!(
            reason(&dir).contains("vertices is more than"),
            "{}",
            reason(&dir)
        );
        edit(&dir, |m| {
            m["height"]["columns"] = json!(7);
            m["height"]["rows"] = json!(7);
        });
        assert!(Environment::open(&dir).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn structure_names_and_degenerate_footprints_are_validated() {
        let (root, dir) = synthetic("syn-v3-text", true);
        let veg = veg_record(100, -100, 450, 25, 1);
        for name in [json!("x".repeat(121)), json!("bell\u{7}"), json!("")] {
            let mut f = features();
            f["structures"][0]["name"] = name;
            add_world(&dir, f, &veg);
            assert!(reason(&dir).contains("structure n1"), "{}", reason(&dir));
        }
        let mut f = features();
        f["structures"][0]["name"] = json!("Launch tower");
        add_world(&dir, f, &veg);
        assert!(Environment::open(&dir).is_ok());
        // A ring closed by repeating its first point, or with a repeated vertex.
        let mut f = features();
        f["buildings"][0]["ring_dm"] = json!([100, 100, 300, 100, 300, 300, 100, 300, 100, 100]);
        add_world(&dir, f, &veg);
        assert!(reason(&dir).contains("zero-length"), "{}", reason(&dir));
        let mut f = features();
        f["buildings"][0]["ring_dm"] = json!([100, 100, 300, 100, 300, 100, 300, 300, 100, 300]);
        add_world(&dir, f, &veg);
        assert!(reason(&dir).contains("zero-length"));
        let _ = fs::remove_dir_all(root);
    }
}
