//! Geographic environment packs: a terrain height grid and a true-colour image on a regular grid of
//! the ENU tangent plane at an origin, with a manifest (`environment.json`, schema
//! `vv-geo-environment.v1`) naming the origin, datums, sources, licences and file hashes.
//!
//! A pack is untrusted input until [`Environment::open`] accepts it: fixed file names, bounded
//! sizes, matching SHA-256, a consistent grid, attributed sources, and the pack's check points
//! recomputed with this crate's geodesy within 1 mm. A pack that fails any rule is not shown.
//! Packs are built by `scripts/geo/build_environment.py` with PROJ; recomputing their check points
//! here is a test of two independent implementations against each other.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use crate::wgs84::{Enu, Geodetic};

pub const SCHEMA: &str = "vv-geo-environment.v1";
pub const MANIFEST: &str = "environment.json";
pub const HEIGHT_FILE: &str = "height.u16";
pub const IMAGE_FILE: &str = "image.jpg";
const MAX_MANIFEST_BYTES: u64 = 256 * 1024;
const MAX_HEIGHT_BYTES: u64 = 64 * 1024 * 1024;
const MAX_IMAGE_BYTES: u64 = 32 * 1024 * 1024;
const MAX_EXTENT_M: f64 = 50_000.0;
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
    sources: Vec<Source>,
    checks: Vec<Check>,
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
    bytes: u64,
    sha256: String,
}

#[derive(Deserialize)]
struct Source {
    provider: String,
    product: String,
    licence: String,
    attribution: String,
}

#[derive(Deserialize)]
struct Check {
    lat_deg: f64,
    lon_deg: f64,
    h_ellipsoid_m: f64,
    enu_m: [f64; 3],
}

/// A validated environment pack.
#[derive(Debug, Clone)]
pub struct Environment {
    pub id: String,
    pub dir: PathBuf,
    pub frame: Enu,
    /// Geoid undulation at the origin (EGM2008 minus WGS84 ellipsoid), metres.
    pub geoid_undulation_m: f64,
    heights: Vec<f32>,
    cols: usize,
    rows: usize,
    spacing: f64,
    x0: f64,
    y0: f64,
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

fn read_bounded(path: &Path, max: u64) -> Result<Vec<u8>, GeoError> {
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

impl Environment {
    /// Reads and validates the pack in `dir`. Nothing of a pack is used before this returns `Ok`.
    pub fn open(dir: &Path) -> Result<Self, GeoError> {
        let folder = file_name(dir);
        let raw = read_bounded(&dir.join(MANIFEST), MAX_MANIFEST_BYTES)?;
        let full: Value = serde_json::from_slice(&raw)
            .map_err(|e| GeoError::Invalid(format!("{MANIFEST}: {e}")))?;
        let m: Manifest = serde_json::from_value(full.clone())
            .map_err(|e| GeoError::Invalid(format!("{MANIFEST}: {e}")))?;
        if m.schema != SCHEMA {
            return invalid(format!("schema {} is not {SCHEMA}", m.schema));
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
        if !(-360.0..=360.0).contains(&heading) {
            return invalid("heading outside [-360, 360] degrees");
        }
        let extent = finite(m.extent_m, "extent")?;
        if !(extent > 0.0 && extent <= MAX_EXTENT_M) {
            return invalid(format!("extent must be in (0, {MAX_EXTENT_M}] m"));
        }

        // Height grid.
        let h = &m.height;
        if h.file != HEIGHT_FILE || h.encoding != "uint16-le" {
            return invalid(format!("the height grid must be {HEIGHT_FILE}, uint16-le"));
        }
        if !(2..=4097).contains(&h.columns) || !(2..=4097).contains(&h.rows) {
            return invalid("height grid size outside 2..4097");
        }
        let s = finite(h.spacing_m, "height spacing")?;
        if !(1.0..=1000.0).contains(&s) || finite(h.scale_m, "height scale")? <= 0.0 {
            return invalid("height spacing or scale out of range");
        }
        finite(h.offset_m, "height offset")?;
        let want_x0 = -((h.columns - 1) as f64) * s / 2.0;
        let want_y0 = ((h.rows - 1) as f64) * s / 2.0;
        if (h.first_node_m[0] - want_x0).abs() > 1e-6 || (h.first_node_m[1] - want_y0).abs() > 1e-6
        {
            return invalid("the height grid is not centred on the origin");
        }
        if (want_y0 - extent).abs() > s {
            return invalid("the height grid does not cover the declared extent");
        }
        if h.bytes != (h.columns * h.rows * 2) as u64 {
            return invalid("height grid byte count does not match its size");
        }
        let hb = read_bounded(&dir.join(HEIGHT_FILE), MAX_HEIGHT_BYTES)?;
        if hb.len() as u64 != h.bytes || sha256_hex(&hb) != h.sha256 {
            return invalid(format!(
                "{HEIGHT_FILE} does not match its SHA-256 in the manifest"
            ));
        }
        let heights: Vec<f32> = hb
            .as_chunks::<2>()
            .0
            .iter()
            .map(|c| (u16::from_le_bytes(*c) as f64 * h.scale_m + h.offset_m) as f32)
            .collect();

        // Image.
        let im = &m.image;
        if im.file != IMAGE_FILE
            || !(16..=16384).contains(&im.columns)
            || !(16..=16384).contains(&im.rows)
        {
            return invalid(format!(
                "the image must be {IMAGE_FILE}, 16 to 16384 texels a side"
            ));
        }
        if ((im.columns as f64) * finite(im.spacing_m, "image spacing")? - 2.0 * extent).abs()
            > im.spacing_m
        {
            return invalid("the image does not cover the declared extent");
        }
        let ib = read_bounded(&dir.join(IMAGE_FILE), MAX_IMAGE_BYTES)?;
        if ib.len() as u64 != im.bytes || sha256_hex(&ib) != im.sha256 {
            return invalid(format!(
                "{IMAGE_FILE} does not match its SHA-256 in the manifest"
            ));
        }
        if !ib.starts_with(&[0xFF, 0xD8, 0xFF]) {
            return invalid(format!("{IMAGE_FILE} is not a JPEG file"));
        }
        // The decoded size is what the web view allocates: it must be the declared one.
        match jpeg_size(&ib) {
            Some((w, hh)) if w == im.columns && hh == im.rows => {}
            other => {
                return invalid(format!(
                    "{IMAGE_FILE} is {other:?} pixels, the manifest declares {}x{}",
                    im.columns, im.rows
                ));
            }
        }

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

        let frame = Enu::new(
            Geodetic::new(o.lat_deg, o.lon_deg, o.h_ellipsoid_m),
            heading,
        );
        let mut env = Environment {
            id: m.id.clone(),
            dir: dir.to_path_buf(),
            frame,
            geoid_undulation_m: n0,
            heights,
            cols: h.columns,
            rows: h.rows,
            spacing: s,
            x0: want_x0,
            y0: want_y0,
            summary: Value::Null,
            bytes: (raw.len() + hb.len() + ib.len()) as u64,
            image_sha: im.sha256.clone(),
            worst_check_m: 0.0,
        };

        // The origin is on the terrain, and every check point recomputes within tolerance.
        match env.terrain_up(0.0, 0.0) {
            Some(u) if u.abs() <= h.scale_m => {}
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
            match env.terrain_up(c.enu_m[0], c.enu_m[1]) {
                Some(u) if (u - c.enu_m[2]).abs() <= h.scale_m => {}
                other => {
                    return invalid(format!(
                        "the height grid at a check point is {other:?}, the manifest says {:.3}",
                        c.enu_m[2]
                    ));
                }
            }
        }
        env.worst_check_m = worst;
        env.summary = summary_of(&full, &env);
        Ok(env)
    }

    /// Terrain ENU up at (east, north), bilinear between grid nodes; `None` outside the grid.
    pub fn terrain_up(&self, e: f64, n: f64) -> Option<f64> {
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
        Some(
            at(r, c) * (1.0 - tx) * (1.0 - ty)
                + at(r, c + 1) * tx * (1.0 - ty)
                + at(r + 1, c) * (1.0 - tx) * ty
                + at(r + 1, c + 1) * tx * ty,
        )
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
            _ => return invalid(format!("{name:?} is not a file of an environment pack")),
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

fn summary_of(full: &Value, env: &Environment) -> Value {
    let pick = |k: &str| full.get(k).cloned().unwrap_or(Value::Null);
    json!({
        "schema": SCHEMA,
        "id": env.id,
        "name": pick("name"),
        "summary": pick("summary"),
        "origin": pick("origin"),
        "frame": pick("frame"),
        "extent_m": pick("extent_m"),
        "height": pick("height"),
        "image": pick("image"),
        "relief": pick("relief"),
        "accuracy": pick("accuracy"),
        "sources": pick("sources"),
        "built": pick("built"),
        "bytes": env.bytes,
        "checks": full.get("checks").and_then(Value::as_array).map(|a| a.len()).unwrap_or(0),
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
        for f in [MANIFEST, HEIGHT_FILE, IMAGE_FILE] {
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
        assert!((t[0].h_msl_m - (o.h_m - e.geoid_undulation_m)).abs() < 1e-9);
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
}
