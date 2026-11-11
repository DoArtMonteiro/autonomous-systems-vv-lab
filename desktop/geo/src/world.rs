//! The world layer of an environment pack (schema `vv-geo-environment.v3`): what stands on the
//! terrain. Two optional files, both untrusted until validated here:
//!
//! - `features.json` (`vv-geo-features.v1`): building footprints extruded to a height, raised
//!   structures outlined from lidar cells, and point structures (towers, masts, lighthouses). Every
//!   record names the source of its height: `lidar` (surveyed), `osm-height` or `osm-levels`
//!   (mapped tags), `default` (an estimate);
//! - `vegetation.bin`: fixed 12-byte records (position, height, crown radius, kind, image colour)
//!   of lidar crowns and shrub clumps.
//!
//! The layer is geographic context for the drawn scene. It never reaches the simulation, the
//! records or the verdicts.

use std::collections::BTreeMap;
use std::path::Path;

use serde::Deserialize;
use serde_json::{Value, json};

use crate::environment::{GeoError, invalid_err, read_bounded, sha256_hex};

pub const FEATURES_FILE: &str = "features.json";
pub const VEGETATION_FILE: &str = "vegetation.bin";
pub const FEATURES_SCHEMA: &str = "vv-geo-features.v1";
pub(crate) const MAX_FEATURES_BYTES: u64 = 16 * 1024 * 1024;
pub(crate) const MAX_VEGETATION_BYTES: u64 = 8 * 1024 * 1024;
const MAX_BUILDINGS: usize = 60_000;
const MAX_STRUCTURES: usize = 10_000;
const MAX_RING_VERTICES: usize = 2_048;
/// The tallest feature accepted, in decimetres (300 m).
const MAX_HEIGHT_DM: i64 = 3_000;
pub const VEGETATION_RECORD: usize = 12;
const HEIGHT_SOURCES: [&str; 4] = ["lidar", "osm-height", "osm-levels", "default"];

/// Manifest block of one world file.
#[derive(Deserialize, Clone)]
pub(crate) struct WorldFile {
    pub file: String,
    pub bytes: u64,
    pub sha256: String,
    #[serde(default)]
    pub count: Option<usize>,
    #[serde(default)]
    pub buildings: Option<usize>,
    #[serde(default)]
    pub lidar_structures: Option<usize>,
    #[serde(default)]
    pub structures: Option<usize>,
    /// Declared counts by source of height (buildings only). Checked against `features.json`.
    #[serde(default)]
    pub height_sources: Option<BTreeMap<String, usize>>,
    /// Declared plant counts. Checked against `vegetation.bin`.
    #[serde(default)]
    pub trees: Option<usize>,
    #[serde(default)]
    pub shrubs: Option<usize>,
    /// Descriptive facts shown as text or numbers; typed here so the interface never gets another
    /// kind of value.
    #[serde(default)]
    pub osm_radius_m: Option<f64>,
    #[serde(default)]
    pub osm_timestamp: Option<String>,
    #[serde(default)]
    pub osm_skipped: Option<usize>,
    #[serde(default)]
    pub licence: Option<String>,
    #[serde(default)]
    pub accuracy: Option<String>,
    #[serde(default)]
    pub record: Option<String>,
}

/// Manifest `world` block.
#[derive(Deserialize, Clone, Default)]
pub(crate) struct WorldManifest {
    #[serde(default)]
    pub features: Option<WorldFile>,
    #[serde(default)]
    pub vegetation: Option<WorldFile>,
}

/// The validated world layer: hashes of its files, for re-checking on every hand-over.
#[derive(Debug, Clone, Default)]
pub struct World {
    pub features_sha: Option<String>,
    pub vegetation_sha: Option<String>,
    pub buildings: usize,
    pub vegetation: usize,
    pub bytes: u64,
    /// What the interface shows about the layer, built from the validated files and the typed
    /// descriptive fields of the manifest, never from the manifest's raw JSON. Counts are
    /// recomputed from `features.json` and `vegetation.bin`.
    pub summary: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Features {
    schema: String,
    #[allow(dead_code)]
    units: String,
    #[allow(dead_code)]
    osm_timestamp: Option<String>,
    buildings: Vec<Footprint>,
    lidar_structures: Vec<Footprint>,
    structures: Vec<Structure>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Footprint {
    id: String,
    kind: String,
    h_dm: i64,
    hs: String,
    #[allow(dead_code)]
    roof: [u8; 3],
    ring_dm: Vec<i64>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Structure {
    id: String,
    kind: String,
    x_dm: i64,
    y_dm: i64,
    h_dm: i64,
    r_dm: i64,
    hs: String,
    name: Option<String>,
}

fn check_file(dir: &Path, wf: &WorldFile, name: &str, max: u64) -> Result<Vec<u8>, GeoError> {
    if wf.file != name {
        return invalid_err(format!("the world file must be named {name}"));
    }
    let b = read_bounded(&dir.join(name), max)?;
    if b.len() as u64 != wf.bytes || sha256_hex(&b) != wf.sha256 {
        return invalid_err(format!("{name} does not match its SHA-256 in the manifest"));
    }
    Ok(b)
}

pub(crate) fn text_ok(s: &str, max: usize) -> bool {
    !s.is_empty() && s.len() <= max && s.chars().all(|c| !c.is_control())
}

fn footprint_ok(f: &Footprint, limit_dm: i64) -> Result<(), String> {
    if !text_ok(&f.id, 40) || !text_ok(&f.kind, 40) {
        return Err("a footprint has an invalid id or kind".into());
    }
    if !HEIGHT_SOURCES.contains(&f.hs.as_str()) {
        return Err(format!(
            "height source {:?} is not one of {HEIGHT_SOURCES:?}",
            f.hs
        ));
    }
    if !(1..=MAX_HEIGHT_DM).contains(&f.h_dm) {
        return Err(format!(
            "footprint {} has a height outside (0, 300] m",
            f.id
        ));
    }
    let n = f.ring_dm.len();
    if !n.is_multiple_of(2) || !(6..=2 * MAX_RING_VERTICES).contains(&n) {
        return Err(format!(
            "footprint {} must have 3 to {MAX_RING_VERTICES} vertices",
            f.id
        ));
    }
    if f.ring_dm.iter().any(|v| v.abs() > limit_dm) {
        return Err(format!("footprint {} lies outside the pack", f.id));
    }
    // Counter-clockwise (positive shoelace area), as the renderer triangulates it.
    let pts: Vec<(i64, i64)> = f.ring_dm.chunks(2).map(|c| (c[0], c[1])).collect();
    let twice: i64 = (0..pts.len())
        .map(|i| {
            let (a, b) = (pts[i], pts[(i + 1) % pts.len()]);
            a.0 * b.1 - b.0 * a.1
        })
        .sum();
    if twice <= 0 {
        return Err(format!("footprint {} is not counter-clockwise", f.id));
    }
    // A repeated vertex (including a ring closed by repeating its first point) is a zero-length
    // edge: the renderer would extrude a degenerate wall.
    if (0..pts.len()).any(|i| pts[i] == pts[(i + 1) % pts.len()]) {
        return Err(format!("footprint {} has a zero-length edge", f.id));
    }
    Ok(())
}

/// Validates the world layer declared by `wm` in `dir`. `extent_m` is the base half-extent and
/// `veg_half_m` the half-extent vegetation must lie within.
pub(crate) fn open(
    dir: &Path,
    wm: &WorldManifest,
    extent_m: f64,
    veg_half_m: f64,
) -> Result<World, GeoError> {
    let mut w = World::default();
    let (mut sf, mut sv) = (Value::Null, Value::Null);
    let limit_dm = (extent_m * 10.0).round() as i64;
    if let Some(ff) = &wm.features {
        let b = check_file(dir, ff, FEATURES_FILE, MAX_FEATURES_BYTES)?;
        let f: Features = serde_json::from_slice(&b)
            .map_err(|e| GeoError::Invalid(format!("{FEATURES_FILE}: {e}")))?;
        if f.schema != FEATURES_SCHEMA {
            return invalid_err(format!("{FEATURES_FILE}: schema is not {FEATURES_SCHEMA}"));
        }
        if f.buildings.len() + f.lidar_structures.len() > MAX_BUILDINGS
            || f.structures.len() > MAX_STRUCTURES
        {
            return invalid_err(format!("{FEATURES_FILE}: too many features"));
        }
        if ff.buildings != Some(f.buildings.len())
            || ff.lidar_structures != Some(f.lidar_structures.len())
            || ff.structures != Some(f.structures.len())
        {
            return invalid_err(format!(
                "{FEATURES_FILE}: the counts do not match the manifest"
            ));
        }
        for fp in f.buildings.iter().chain(f.lidar_structures.iter()) {
            footprint_ok(fp, limit_dm)
                .map_err(|m| GeoError::Invalid(format!("{FEATURES_FILE}: {m}")))?;
        }
        if f.lidar_structures.iter().any(|s| s.hs != "lidar") {
            return invalid_err(format!(
                "{FEATURES_FILE}: a lidar structure must have a lidar height"
            ));
        }
        for s in &f.structures {
            if !text_ok(&s.id, 40)
                || !text_ok(&s.kind, 40)
                || !HEIGHT_SOURCES.contains(&s.hs.as_str())
                || !(1..=MAX_HEIGHT_DM).contains(&s.h_dm)
                || !(1..=500).contains(&s.r_dm)
                || s.x_dm.abs() > limit_dm
                || s.y_dm.abs() > limit_dm
                || s.name.as_deref().is_some_and(|n| !text_ok(n, 120))
            {
                return invalid_err(format!("{FEATURES_FILE}: structure {} is not valid", s.id));
            }
        }
        // The source of every building height is counted from the hashed file; a manifest that
        // claims other counts (for instance more surveyed heights) is refused.
        let mut height_sources: BTreeMap<String, usize> = BTreeMap::new();
        for fp in &f.buildings {
            *height_sources.entry(fp.hs.clone()).or_default() += 1;
        }
        if ff
            .height_sources
            .as_ref()
            .is_some_and(|d| d.iter().filter(|(_, n)| **n > 0).ne(height_sources.iter()))
        {
            return invalid_err(format!(
                "{FEATURES_FILE}: the declared sources of height do not match the file"
            ));
        }
        sf = json!({
            "file": FEATURES_FILE,
            "bytes": ff.bytes,
            "sha256": ff.sha256,
            "buildings": f.buildings.len(),
            "lidar_structures": f.lidar_structures.len(),
            "structures": f.structures.len(),
            "height_sources": height_sources,
            "osm_radius_m": finite_opt(ff.osm_radius_m, "osm_radius_m")?,
            "osm_timestamp": text_opt(&ff.osm_timestamp, 40, "osm_timestamp")?,
            "osm_skipped": ff.osm_skipped,
            "licence": text_opt(&ff.licence, 400, "licence")?,
            "accuracy": text_opt(&ff.accuracy, 2_000, "accuracy")?,
        });
        w.buildings = f.buildings.len() + f.lidar_structures.len();
        w.features_sha = Some(ff.sha256.clone());
        w.bytes += b.len() as u64;
    }
    if let Some(vf) = &wm.vegetation {
        let b = check_file(dir, vf, VEGETATION_FILE, MAX_VEGETATION_BYTES)?;
        if !b.len().is_multiple_of(VEGETATION_RECORD)
            || vf.count != Some(b.len() / VEGETATION_RECORD)
        {
            return invalid_err(format!("{VEGETATION_FILE}: size and count do not match"));
        }
        let lim = (veg_half_m * 10.0).round() as i32;
        let (mut trees, mut shrubs) = (0usize, 0usize);
        for r in b.as_chunks::<VEGETATION_RECORD>().0 {
            let x = i16::from_le_bytes([r[0], r[1]]) as i32;
            let y = i16::from_le_bytes([r[2], r[3]]) as i32;
            let h = u16::from_le_bytes([r[4], r[5]]);
            let (crown, kind, pad) = (r[6], r[7], r[11]);
            if x.abs() > lim
                || y.abs() > lim
                || h == 0
                || h > 6_000
                || crown == 0
                || kind > 1
                || pad != 0
            {
                return invalid_err(format!("{VEGETATION_FILE}: a record is out of range"));
            }
            if kind == 1 {
                trees += 1;
            } else {
                shrubs += 1;
            }
        }
        // Plant counts come from the records; a manifest claiming others is refused.
        if vf.trees.is_some_and(|n| n != trees) || vf.shrubs.is_some_and(|n| n != shrubs) {
            return invalid_err(format!(
                "{VEGETATION_FILE}: the declared tree and shrub counts do not match the file"
            ));
        }
        sv = json!({
            "file": VEGETATION_FILE,
            "bytes": vf.bytes,
            "sha256": vf.sha256,
            "count": b.len() / VEGETATION_RECORD,
            "trees": trees,
            "shrubs": shrubs,
            "record": text_opt(&vf.record, 400, "record")?,
            "accuracy": text_opt(&vf.accuracy, 2_000, "accuracy")?,
        });
        w.vegetation = b.len() / VEGETATION_RECORD;
        w.vegetation_sha = Some(vf.sha256.clone());
        w.bytes += b.len() as u64;
    }
    if !(sf.is_null() && sv.is_null()) {
        w.summary = json!({"features": sf, "vegetation": sv});
    }
    Ok(w)
}

fn finite_opt(v: Option<f64>, what: &str) -> Result<Option<f64>, GeoError> {
    match v {
        Some(x) if !x.is_finite() => invalid_err(format!("world {what} is not a finite number")),
        other => Ok(other),
    }
}

fn text_opt(v: &Option<String>, max: usize, what: &str) -> Result<Option<String>, GeoError> {
    match v {
        Some(s) if !text_ok(s, max) => invalid_err(format!(
            "world {what} must be text of 1 to {max} bytes without control characters"
        )),
        other => Ok(other.clone()),
    }
}

/// Manifest block of the world layer, or the default when absent.
pub(crate) fn manifest_of(full: &Value) -> Result<WorldManifest, GeoError> {
    match full.get("world") {
        None | Some(Value::Null) => Ok(WorldManifest::default()),
        Some(v) => {
            serde_json::from_value(v.clone()).map_err(|e| GeoError::Invalid(format!("world: {e}")))
        }
    }
}
