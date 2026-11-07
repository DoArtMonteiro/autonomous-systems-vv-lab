//! Geographic environments in the Studio (M16): discovery and validation of environment packs,
//! their files for the web view, import and removal of user packs, and the placement of a stored
//! run on a pack for display.
//!
//! Locations: packs shipped with the installer under `<install dir>/environments/` (read-only) and
//! packs the user imports under `Documents/VV Lab Library/environments/`. The Studio never
//! downloads anything: packs are built on purpose with `scripts/geo/build_environment.py` and
//! imported from a folder. Every pack is validated by `vv-geo` before anything of it is shown, and
//! every file is re-hashed when the web view asks for it. Files reach the web view through a
//! command (bytes over IPC), so the content security policy is unchanged.
//!
//! Placing a run never touches the run: the record is read, its position channels are converted,
//! and the result is returned. Records, verdicts and run ids do not depend on any environment.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};

use serde_json::{Value, json};
use tauri::State;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use vv_geo::environment::{self, Environment};
use vv_platform::{PlatformError, RunRecord};

use crate::{AppState, blocking, display_path, err, log_line};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Kind {
    Bundled,
    Imported,
}

impl Kind {
    fn word(self) -> &'static str {
        match self {
            Kind::Bundled => "bundled",
            Kind::Imported => "imported",
        }
    }
}

#[derive(Clone)]
pub struct GeoPaths {
    pub bundled: Vec<PathBuf>,
    pub imported: PathBuf,
}

pub struct Loaded {
    envs: Vec<(Kind, Arc<Environment>)>,
    rejected: Vec<Value>,
}

pub struct Geo {
    pub paths: GeoPaths,
    loaded: RwLock<Option<Arc<Loaded>>>,
}

impl Geo {
    pub fn new(paths: GeoPaths) -> Self {
        Self {
            paths,
            loaded: RwLock::new(None),
        }
    }

    /// Validates every pack once; `reload` forces a new scan (after import or removal).
    fn load(&self, reload: bool) -> Arc<Loaded> {
        if !reload
            && let Ok(g) = self.loaded.read()
            && let Some(l) = g.as_ref()
        {
            return l.clone();
        }
        let mut envs: Vec<(Kind, Arc<Environment>)> = Vec::new();
        let mut rejected = Vec::new();
        let roots = self
            .paths
            .bundled
            .iter()
            .map(|p| (Kind::Bundled, p.clone()))
            .chain(std::iter::once((
                Kind::Imported,
                self.paths.imported.clone(),
            )));
        for (kind, root) in roots {
            let (ok, bad) = environment::discover(&root);
            for e in ok {
                if envs.iter().any(|(_, x)| x.id == e.id) {
                    rejected.push(json!({"folder": e.id, "kind": kind.word(), "reason": "an environment with this id is already installed"}));
                    continue;
                }
                envs.push((kind, Arc::new(e)));
            }
            for (folder, reason) in bad {
                rejected.push(json!({"folder": folder, "kind": kind.word(), "reason": reason}));
            }
        }
        let l = Arc::new(Loaded { envs, rejected });
        if let Ok(mut g) = self.loaded.write() {
            *g = Some(l.clone());
        }
        l
    }

    pub(crate) fn get(&self, id: &str) -> Result<(Kind, Arc<Environment>), PlatformError> {
        self.load(false)
            .envs
            .iter()
            .find(|(_, e)| e.id == id)
            .map(|(k, e)| (*k, e.clone()))
            .ok_or_else(|| {
                PlatformError::Invalid(format!("no installed environment has the id {id:?}"))
            })
    }
}

pub(crate) fn geo_err(e: vv_geo::GeoError) -> PlatformError {
    match e {
        vv_geo::GeoError::Io(m) => PlatformError::Io(m),
        vv_geo::GeoError::Invalid(m) => PlatformError::Invalid(m),
    }
}

pub(crate) fn listing(geo: &Geo, reload: bool) -> Value {
    let l = geo.load(reload);
    json!({
        "environments": l.envs.iter().map(|(k, e)| {
            let mut s = e.summary().clone();
            s["kind"] = json!(k.word());
            s
        }).collect::<Vec<_>>(),
        "rejected": l.rejected,
        "imported_dir": display_path(&geo.paths.imported),
        "network": "none: the Studio makes no network request; packs are built outside it and imported from a folder",
    })
}

#[tauri::command]
pub async fn list_environments(state: State<'_, AppState>) -> Result<Value, PlatformError> {
    let geo = state.geo.clone();
    blocking(move || Ok(listing(&geo, false))).await
}

/// The bytes of one pack file (`height.u16`, `image.jpg` or a detail layer file), re-checked against its hash.
#[tauri::command]
pub async fn environment_file(
    state: State<'_, AppState>,
    id: String,
    file: String,
) -> Result<tauri::ipc::Response, PlatformError> {
    let geo = state.geo.clone();
    let bytes = blocking(move || {
        let (_, e) = geo.get(&id)?;
        e.file(&file).map_err(geo_err)
    })
    .await?;
    Ok(tauri::ipc::Response::new(bytes))
}

/// Channels of a record as model points, or `None` where a sample is missing.
fn points(record: &RunRecord, ids: &[&str]) -> Option<Vec<Option<[f64; 3]>>> {
    let ch: Vec<_> = ids
        .iter()
        .map(|id| record.channels.iter().find(|c| c.id == *id))
        .collect::<Option<Vec<_>>>()?;
    let n = ch[0].values.len();
    // The channels must be on the scene's timebase, which the warning and the interface index by.
    let tb = record.scene["channels"]["timebase"]
        .as_str()
        .unwrap_or(&ch[0].timebase);
    let times = record.timebases.get(tb).map(Vec::len);
    if times != Some(n) || ch.iter().any(|c| c.values.len() != n || c.timebase != tb) {
        return None;
    }
    Some(
        (0..n)
            .map(
                |i| match (ch[0].values[i], ch[1].values[i], ch[2].values[i]) {
                    (Some(x), Some(y), Some(z)) => Some([x, y, z]),
                    _ => None,
                },
            )
            .collect(),
    )
}

/// The stored run placed on an environment: geodetic coordinates and terrain clearance of the
/// true centre of mass, the true nozzle plane and the controller's estimate, sample by sample.
pub fn track_of(record: &RunRecord, env: &Environment) -> Result<Value, PlatformError> {
    let scene = &record.scene;
    if scene["kind"] != "rocket-3d"
        || scene["units"] != "m"
        || scene["frame"]["axes"]["x"] != "east"
        || scene["frame"]["axes"]["y"] != "north"
        || scene["frame"]["up_axis"] != "z"
    {
        return Err(PlatformError::Invalid(
            "this run has no local east-north-up frame in metres, so it cannot be placed on a landscape".into(),
        ));
    }
    let ids = |k: &str, d: [&'static str; 3]| -> Vec<String> {
        scene["channels"][k]
            .as_array()
            .filter(|a| a.len() == 3)
            .map(|a| {
                a.iter()
                    .map(|v| v.as_str().unwrap_or_default().to_string())
                    .collect()
            })
            .unwrap_or_else(|| d.iter().map(|s| s.to_string()).collect())
    };
    let place = |names: Vec<String>| -> Option<Value> {
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        let pts = points(record, &refs)?;
        let present: Vec<[f64; 3]> = pts.iter().flatten().copied().collect();
        let placed = env.track(&present);
        let mut it = placed.into_iter();
        let out: Vec<Value> = pts
            .iter()
            .map(|p| match p {
                Some(_) => serde_json::to_value(it.next()).unwrap_or(Value::Null),
                None => Value::Null,
            })
            .collect();
        Some(json!({"channels": names, "points": out}))
    };
    let truth = place(ids("position", ["pos_x", "pos_y", "pos_z"]))
        .ok_or_else(|| PlatformError::Invalid("the run has no position channels".into()))?;
    let nozzle = place(ids("nozzle_position", ["base_x", "base_y", "altitude"]));
    let estimate = place(vec!["est_x".into(), "est_y".into(), "est_z".into()]);
    // Where the drawn true nozzle path passes below the terrain of the pack (display only: the
    // simulation assumes flat ground and computes no interaction with this terrain).
    let below: Option<f64> = nozzle.as_ref().and_then(|n| {
        let tb = scene["channels"]["timebase"].as_str().unwrap_or_default();
        let times = record.timebases.get(tb)?;
        n["points"]
            .as_array()?
            .iter()
            .zip(times)
            .find_map(|(p, t)| {
                let a = p["above_terrain_m"].as_f64()?;
                // Ignore the contact sample itself: the nozzle reaches z = 0 at the pad by definition.
                (a < -0.5).then_some(*t)
            })
    });
    Ok(json!({
        "schema": "vv-geo-track.v1",
        "environment": env.id,
        "origin": env.frame.origin,
        "heading_deg": env.frame.heading_deg(),
        "geoid_undulation_m": env.geoid_undulation_m,
        "timebase": scene["channels"]["timebase"],
        "truth": truth,
        "nozzle": nozzle,
        "estimate": estimate,
        "first_below_terrain_t": below,
        "derived": "Derived for display: model positions converted from the run's local flat frame to WGS84 with the pack origin. The run, its verdicts and its hashes are unchanged.",
    }))
}

#[tauri::command]
pub async fn geo_track(
    state: State<'_, AppState>,
    id: String,
    run_id: String,
) -> Result<Value, PlatformError> {
    let p = state.platform()?;
    let geo = state.geo.clone();
    blocking(move || {
        let (_, env) = geo.get(&id)?;
        let record = p.record(&run_id)?;
        track_of(&record, &env)
    })
    .await
}

fn copy_pack(src: &Path, dst: &Path, files: &[&str]) -> Result<(), PlatformError> {
    fs::create_dir_all(dst).map_err(err)?;
    for f in files {
        fs::copy(src.join(f), dst.join(f)).map_err(err)?;
    }
    Ok(())
}

/// Asks for a pack folder, validates it where it is, copies its files into the library and
/// validates the copy. Returns the new listing, or `None` when the dialog was cancelled.
#[tauri::command]
pub async fn import_environment(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<Value>, PlatformError> {
    let geo = state.geo.clone();
    let log = state.paths.log.clone();
    blocking(move || {
        let picked = app
            .dialog()
            .file()
            .set_title("Choose an environment pack folder (it contains environment.json)")
            .blocking_pick_folder();
        let Some(src) = picked.and_then(|f| f.into_path().ok()) else {
            return Ok(None);
        };
        let env = Environment::open(&src).map_err(geo_err)?;
        if geo.get(&env.id).is_ok() {
            return Err(PlatformError::Invalid(format!(
                "an environment with the id {:?} is already installed; remove it first",
                env.id
            )));
        }
        let dst = geo.paths.imported.join(&env.id);
        if dst.exists() {
            return Err(PlatformError::Invalid(format!(
                "{} already exists in the library",
                env.id
            )));
        }
        let staged = geo.paths.imported.join(format!(".import-{}", env.id));
        let _ = fs::remove_dir_all(&staged);
        if let Err(e) = copy_pack(&src, &staged, &env.files()) {
            let _ = fs::remove_dir_all(&staged);
            return Err(e);
        }
        let check = staged.with_file_name(&env.id);
        if let Err(e) = fs::rename(&staged, &check) {
            let _ = fs::remove_dir_all(&staged);
            return Err(err(e));
        }
        if let Err(e) = Environment::open(&check) {
            let _ = fs::remove_dir_all(&check);
            return Err(geo_err(e));
        }
        log_line(&log, &format!("environment imported {}", env.id));
        Ok(Some(listing(&geo, true)))
    })
    .await
}

/// Removes an imported pack (bundled packs are part of the installation and cannot be removed).
#[tauri::command]
pub async fn remove_environment(
    state: State<'_, AppState>,
    id: String,
) -> Result<Value, PlatformError> {
    let geo = state.geo.clone();
    let log = state.paths.log.clone();
    blocking(move || {
        let (kind, env) = geo.get(&id)?;
        if kind != Kind::Imported {
            return Err(PlatformError::Invalid(
                "bundled environments are part of the installation and cannot be removed".into(),
            ));
        }
        if env.dir.parent() != Some(geo.paths.imported.as_path()) {
            return Err(PlatformError::Invalid(
                "the pack is not in the library folder".into(),
            ));
        }
        fs::remove_dir_all(&env.dir).map_err(err)?;
        log_line(&log, &format!("environment removed {id}"));
        Ok(listing(&geo, true))
    })
    .await
}

/// Shows the folder of imported packs in Explorer (created if missing).
#[tauri::command]
pub fn reveal_environments(
    app: tauri::AppHandle,
    state: State<AppState>,
) -> Result<(), PlatformError> {
    let dir = state.geo.paths.imported.clone();
    fs::create_dir_all(&dir).map_err(err)?;
    app.opener().reveal_item_in_dir(dir).map_err(err)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env() -> Environment {
        Environment::open(
            &Path::new(env!("CARGO_MANIFEST_DIR")).join("../environments/cape-canaveral"),
        )
        .unwrap()
    }

    /// A real rocket record (the nominal demonstration, seed 5000) trimmed to three samples of
    /// the position, nozzle and estimate channels; the nozzle of the third sample is put 50 m
    /// under the ground and one estimate sample is removed, to exercise both paths.
    fn record() -> RunRecord {
        let mut v: Value =
            serde_json::from_str(include_str!("../tests/fixtures/rocket-record-trimmed.json"))
                .expect("fixture");
        for c in v["channels"].as_array_mut().unwrap() {
            if c["id"] == "altitude" {
                c["values"][2] = json!(-50.0);
            }
            if c["id"] == "est_x" {
                c["values"][1] = Value::Null;
            }
        }
        serde_json::from_value(v).expect("test record")
    }

    #[test]
    fn a_track_places_every_sample_and_keeps_gaps() {
        let r = record();
        let before = serde_json::to_vec(&r).unwrap();
        let t = track_of(&r, &env()).unwrap();
        assert_eq!(
            serde_json::to_vec(&r).unwrap(),
            before,
            "the record must not change"
        );
        let truth = t["truth"]["points"].as_array().unwrap();
        assert_eq!(truth.len(), 3);
        let o = env().frame.origin;
        // The first sample is 64.4 m east, 29.7 m north and 3030.5 m up of the pad centre.
        let lat = truth[0]["lat_deg"].as_f64().unwrap();
        let lon = truth[0]["lon_deg"].as_f64().unwrap();
        assert!(lat > o.lat_deg && lon > o.lon_deg);
        let up = env().frame.enu_of(
            vv_geo::Geodetic::new(lat, lon, truth[0]["h_ellipsoid_m"].as_f64().unwrap()).to_ecef(),
        );
        let m = r.channels.iter().find(|c| c.id == "pos_x").unwrap().values[0].unwrap();
        assert!((up[0] - m).abs() < 1e-6, "{up:?}");
        assert!(
            t["estimate"]["points"][1].is_null(),
            "a missing estimate sample stays missing"
        );
        // The nozzle at -50 m is below the terrain at t = 2.
        assert_eq!(t["first_below_terrain_t"], json!(2.0));
    }

    #[test]
    fn importing_a_layered_pack_copies_its_detail_files() {
        let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../environments/cape-canaveral");
        let e = Environment::open(&src).unwrap();
        assert!(e.files().contains(&environment::DETAIL_IMAGE_FILE));
        let root = std::env::temp_dir().join(format!("vv-import-test-{}", std::process::id()));
        let dst = root.join("cape-canaveral");
        let _ = fs::remove_dir_all(&root);
        copy_pack(&src, &dst, &e.files()).unwrap();
        let copy = Environment::open(&dst).unwrap();
        assert_eq!(copy.files(), e.files());
        assert!(copy.file(environment::DETAIL_IMAGE_FILE).is_ok());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn a_run_without_an_enu_scene_is_refused() {
        let mut r = record();
        r.scene = json!({"kind": "ground-2d", "units": "mm"});
        assert!(track_of(&r, &env()).is_err());
    }
}
