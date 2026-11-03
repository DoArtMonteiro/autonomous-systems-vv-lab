//! M13 Discovery Lab: the Studio side of claim investigations.
//!
//! Studio never computes a verdict. It lists the bundled claims, starts `vv-exec investigate` as a
//! child process (the engine that also runs from the command line), relays its progress, reads the
//! finished package, and starts `vv-exec investigate-verify` to recompute a package from scratch.
//! The web view only receives what the engine wrote.
//!
//! Locations: the engine at `<resources>/engines/vv-exec.exe` (or `VVLAB_EXEC`), the claims under
//! `<resources>/discovery/claims/` (or `VVLAB_CLAIMS`), packages under
//! `<library>/investigations/<name>/` and verification reports under
//! `<library>/investigations/.verifications/<name>.json`, outside the package so verifying never
//! changes the evidence it checks.

use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use serde_json::{Value, json};
use tauri::{Emitter, Manager, State};
use vv_platform::PlatformError;

use crate::{AppState, blocking, err};

/// Headless check for `--self-test`: the engine is installed and validates every bundled claim.
pub fn self_check(engine: &Path, claims: &Path) -> Vec<(String, bool, Value)> {
    let paths = DiscoveryPaths {
        engine: engine.to_path_buf(),
        claims: claims.to_path_buf(),
        investigations: PathBuf::new(),
    };
    if check_engine(&paths).is_err() {
        return vec![(
            "investigation engine installed".into(),
            false,
            json!(engine.display().to_string()),
        )];
    }
    let files = claim_files(claims);
    let mut out = vec![(
        "bundled claims found".into(),
        !files.is_empty(),
        json!(files.len()),
    )];
    for f in files {
        let name = format!(
            "claim {} validates",
            f.file_stem().unwrap_or_default().to_string_lossy()
        );
        match describe(&paths, &f) {
            Ok(v) => out.push((
                name,
                true,
                json!({ "id": v["id"], "property": v["property"] }),
            )),
            Err(e) => out.push((name, false, json!(e))),
        }
    }
    out
}

const MAX_JSON_BYTES: u64 = 64 * 1024 * 1024;
const MAX_CLAIMS: usize = 64;
const MAX_PACKAGES: usize = 500;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Clone, Debug)]
pub struct DiscoveryPaths {
    pub engine: PathBuf,
    pub claims: PathBuf,
    pub investigations: PathBuf,
}

/// The one investigation or verification that may run at a time.
#[derive(Default)]
pub struct Running {
    child: Option<Arc<Mutex<Child>>>,
    partial: Option<PathBuf>,
    cancelled: bool,
}

pub struct Discovery {
    pub paths: DiscoveryPaths,
    pub running: Mutex<Running>,
}

impl Discovery {
    pub fn new(paths: DiscoveryPaths) -> Self {
        Discovery {
            paths,
            running: Mutex::new(Running::default()),
        }
    }
}

fn invalid(m: impl Into<String>) -> PlatformError {
    PlatformError::Invalid(m.into())
}

fn safe_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 128
        && name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
}

fn read_json(path: &Path) -> Result<Value, PlatformError> {
    let meta = fs::metadata(path).map_err(|e| err(format!("{}: {e}", path.display())))?;
    if meta.len() > MAX_JSON_BYTES {
        return Err(err(format!("{} is too large", path.display())));
    }
    let bytes = fs::read(path).map_err(|e| err(format!("{}: {e}", path.display())))?;
    serde_json::from_slice(&bytes).map_err(|e| err(format!("{}: {e}", path.display())))
}

fn command(engine: &Path) -> Command {
    let mut c = Command::new(engine);
    c.stdin(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(CREATE_NO_WINDOW);
    }
    c
}

fn check_engine(paths: &DiscoveryPaths) -> Result<(), PlatformError> {
    if !paths.engine.is_file() {
        return Err(err(format!(
            "the investigation engine is not installed at {}",
            paths.engine.display()
        )));
    }
    Ok(())
}

/// Bundled claim files, one level of folders deep: `claims/<group>/<id>.json`.
fn claim_files(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let Ok(groups) = fs::read_dir(root) else {
        return out;
    };
    let mut groups: Vec<PathBuf> = groups.filter_map(|e| e.ok().map(|e| e.path())).collect();
    groups.sort();
    for g in groups.into_iter().filter(|p| p.is_dir()) {
        let Ok(files) = fs::read_dir(&g) else {
            continue;
        };
        let mut files: Vec<PathBuf> = files
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().is_some_and(|x| x == "json"))
            .collect();
        files.sort();
        out.extend(files);
    }
    out.truncate(MAX_CLAIMS);
    out
}

#[derive(Serialize)]
pub struct ClaimEntry {
    file: String,
    claim: Option<Value>,
    error: Option<String>,
}

fn describe(paths: &DiscoveryPaths, file: &Path) -> Result<Value, String> {
    let out = command(&paths.engine)
        .arg("claim")
        .arg(file)
        .stderr(Stdio::piped())
        .stdout(Stdio::piped())
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    serde_json::from_slice(&out.stdout).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn list_claims(state: State<'_, AppState>) -> Result<Vec<ClaimEntry>, PlatformError> {
    let paths = state.discovery.paths.clone();
    blocking(move || {
        check_engine(&paths)?;
        Ok(claim_files(&paths.claims)
            .into_iter()
            .map(|f| {
                let rel = f
                    .strip_prefix(&paths.claims)
                    .unwrap_or(&f)
                    .to_string_lossy()
                    .replace('\\', "/");
                match describe(&paths, &f) {
                    Ok(v) => ClaimEntry {
                        file: rel,
                        claim: Some(v),
                        error: None,
                    },
                    Err(e) => ClaimEntry {
                        file: rel,
                        claim: None,
                        error: Some(e),
                    },
                }
            })
            .collect())
    })
    .await
}

#[derive(Serialize)]
pub struct PackageEntry {
    name: String,
    claim_id: String,
    title: String,
    verdict: Value,
    probes: u64,
    created: String,
    verification: Option<Value>,
}

/// Hash of the package files a verification report is bound to. A report whose binding no longer
/// matches is stale: the package changed after it was recomputed.
fn binding(dir: &Path) -> String {
    let mut all = Vec::new();
    for f in ["manifest.json", "investigation.json", "probes.jsonl"] {
        let b = fs::read(dir.join(f)).unwrap_or_default();
        all.extend_from_slice(vv_platform::canonical::sha256_hex(&b).as_bytes());
    }
    vv_platform::canonical::sha256_hex(&all)
}

/// The stored report of a package, marked stale when the package changed since.
fn stored_verification(paths: &DiscoveryPaths, dir: &Path, name: &str) -> Option<Value> {
    let mut v = read_json(&verification_path(paths, name)).ok()?;
    let stale = v["binding"].as_str() != Some(binding(dir).as_str());
    v["stale"] = json!(stale);
    Some(v)
}

fn verification_path(paths: &DiscoveryPaths, name: &str) -> PathBuf {
    paths
        .investigations
        .join(".verifications")
        .join(format!("{name}.json"))
}

fn entry(paths: &DiscoveryPaths, dir: &Path) -> Option<PackageEntry> {
    let name = dir.file_name()?.to_string_lossy().into_owned();
    if !safe_name(&name) {
        return None;
    }
    let v = read_json(&dir.join("investigation.json")).ok()?;
    let verification = stored_verification(paths, dir, &name);
    Some(PackageEntry {
        created: name.rsplit('-').next().unwrap_or("").to_string(),
        claim_id: v["claim_id"].as_str().unwrap_or("").into(),
        title: v["title"].as_str().unwrap_or("").into(),
        verdict: v["findings"]["verdict"].clone(),
        probes: v["probes"].as_u64().unwrap_or(0),
        verification,
        name,
    })
}

#[tauri::command]
pub async fn list_investigations(
    state: State<'_, AppState>,
) -> Result<Vec<PackageEntry>, PlatformError> {
    let paths = state.discovery.paths.clone();
    blocking(move || {
        let Ok(rd) = fs::read_dir(&paths.investigations) else {
            return Ok(Vec::new());
        };
        let mut dirs: Vec<PathBuf> = rd
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.is_dir() && p.join("manifest.json").is_file())
            .collect();
        dirs.sort();
        dirs.reverse();
        dirs.truncate(MAX_PACKAGES);
        Ok(dirs.iter().filter_map(|d| entry(&paths, d)).collect())
    })
    .await
}

fn package_dir(paths: &DiscoveryPaths, name: &str) -> Result<PathBuf, PlatformError> {
    if !safe_name(name) {
        return Err(invalid("invalid package name"));
    }
    let dir = paths.investigations.join(name);
    if !dir.join("manifest.json").is_file() {
        return Err(PlatformError::NotFound(format!("investigation {name}")));
    }
    Ok(dir)
}

/// The package summary and the signals of every kept run.
#[tauri::command]
pub async fn investigation(
    state: State<'_, AppState>,
    name: String,
) -> Result<Value, PlatformError> {
    let paths = state.discovery.paths.clone();
    blocking(move || {
        let dir = package_dir(&paths, &name)?;
        let package = read_json(&dir.join("investigation.json"))?;
        let mut signals = serde_json::Map::new();
        if let Some(arts) = package["artifacts"].as_object() {
            for k in arts.keys() {
                if !safe_name(k) {
                    continue;
                }
                if let Ok(v) = read_json(&dir.join("artifacts").join(k).join("signals.json")) {
                    signals.insert(k.clone(), v);
                }
            }
        }
        let claim = read_json(&dir.join("claim.json")).ok();
        let timing = read_json(&dir.join("timing.json")).ok();
        let verification = stored_verification(&paths, &dir, &name);
        Ok(json!({
            "name": name,
            "package": package,
            "claim": claim,
            "signals": signals,
            "timing": timing,
            "verification": verification,
        }))
    })
    .await
}

fn now_stamp() -> String {
    vv_platform::library::now_utc()
        .chars()
        .filter(char::is_ascii_alphanumeric)
        .collect()
}

#[derive(Clone, Serialize)]
struct ProgressEvent {
    kind: String,
    stage: String,
    done: u64,
    total: u64,
}

fn spawn_tracked(
    app: &tauri::AppHandle,
    disc: &Discovery,
    mut cmd: Command,
    kind: &str,
    partial: Option<PathBuf>,
) -> Result<(Arc<Mutex<Child>>, std::thread::JoinHandle<String>), PlatformError> {
    let mut running = disc.running.lock().map_err(err)?;
    if running.child.is_some() {
        return Err(PlatformError::Invalid(
            "an investigation or a verification is already running".into(),
        ));
    }
    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| err(format!("the engine could not start: {e}")))?;
    let stderr = child.stderr.take().ok_or_else(|| err("no stderr"))?;
    let child = Arc::new(Mutex::new(child));
    running.child = Some(child.clone());
    running.partial = partial;
    running.cancelled = false;
    let handle = app.clone();
    let kind = kind.to_string();
    // Progress lines are JSON; anything else is an error message, kept for the report.
    let reader = std::thread::spawn(move || {
        let mut messages = String::new();
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            match serde_json::from_str::<Value>(&line) {
                Ok(v) if v.get("progress").is_some() => {
                    let _ = handle.emit(
                        "discovery-progress",
                        ProgressEvent {
                            kind: kind.clone(),
                            stage: v["progress"].as_str().unwrap_or("").into(),
                            done: v["done"].as_u64().unwrap_or(0),
                            total: v["total"].as_u64().unwrap_or(0),
                        },
                    );
                }
                _ => {
                    if messages.len() < 8192 {
                        messages.push_str(&line);
                        messages.push('\n');
                    }
                }
            }
        }
        messages
    });
    Ok((child, reader))
}

fn finish(disc: &Discovery) -> (bool, Option<PathBuf>) {
    match disc.running.lock() {
        Ok(mut r) => {
            r.child = None;
            (r.cancelled, r.partial.take())
        }
        Err(_) => (false, None),
    }
}

fn wait_output(child: &Arc<Mutex<Child>>) -> Result<(bool, Vec<u8>), PlatformError> {
    let mut stdout = child
        .lock()
        .map_err(err)?
        .stdout
        .take()
        .ok_or_else(|| err("no stdout"))?;
    let mut out = Vec::new();
    std::io::Read::read_to_end(&mut stdout, &mut out).map_err(err)?;
    let status = child.lock().map_err(err)?.wait().map_err(err)?;
    Ok((status.success(), out))
}

/// Runs a bundled claim. Returns the package name.
#[tauri::command]
pub async fn investigate(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    file: String,
) -> Result<String, PlatformError> {
    let paths = state.discovery.paths.clone();
    let rel = PathBuf::from(&file);
    if file.contains("..") || rel.is_absolute() {
        return Err(invalid("invalid claim file"));
    }
    let claim_path = paths.claims.join(&rel);
    if !claim_files(&paths.claims).contains(&claim_path) {
        return Err(invalid("unknown claim file"));
    }
    check_engine(&paths)?;
    let id = claim_path
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .filter(|s| safe_name(s))
        .ok_or_else(|| invalid("invalid claim file name"))?;
    fs::create_dir_all(&paths.investigations).map_err(err)?;
    let name = format!("{id}-{}", now_stamp());
    let out = paths.investigations.join(&name);
    let mut cmd = command(&paths.engine);
    cmd.arg("investigate")
        .arg(&claim_path)
        .arg("--output")
        .arg(&out)
        .arg("--progress");
    let (child, reader) = spawn_tracked(
        &app,
        &state.discovery,
        cmd,
        "investigate",
        Some(out.with_extension("partial")),
    )?;
    let app2 = app.clone();
    let result = blocking(move || {
        let (ok, stdout) = wait_output(&child)?;
        let messages = reader.join().unwrap_or_default();
        Ok((ok, stdout, messages))
    })
    .await;
    let state2 = app2.state::<AppState>();
    let (cancelled, partial) = finish(&state2.discovery);
    let (ok, _stdout, messages) = result?;
    if cancelled || !ok {
        // The engine assembles the package in `<name>.partial` and renames it only when complete;
        // a cancelled or failed run leaves that folder, which Studio created and now removes.
        if let Some(p) = partial
            && p.starts_with(&paths.investigations)
            && p.exists()
        {
            let _ = fs::remove_dir_all(&p);
        }
        return Err(if cancelled {
            PlatformError::Host("the investigation was cancelled".into())
        } else {
            err(format!("the investigation failed: {}", messages.trim()))
        });
    }
    Ok(name)
}

/// Recomputes a package with `vv-exec investigate-verify` and stores the report outside it.
#[tauri::command]
pub async fn verify_investigation(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    name: String,
) -> Result<Value, PlatformError> {
    let paths = state.discovery.paths.clone();
    let dir = package_dir(&paths, &name)?;
    check_engine(&paths)?;
    // Bound before the engine reads the package: a change during verification makes it stale.
    let bound = binding(&dir);
    let mut cmd = command(&paths.engine);
    cmd.arg("investigate-verify").arg(&dir).arg("--progress");
    let (child, reader) = spawn_tracked(&app, &state.discovery, cmd, "verify", None)?;
    let result = blocking(move || {
        let (_ok, stdout) = wait_output(&child)?;
        let messages = reader.join().unwrap_or_default();
        Ok((stdout, messages))
    })
    .await;
    let (cancelled, _) = finish(&app.state::<AppState>().discovery);
    let (stdout, messages) = result?;
    if cancelled {
        return Err(PlatformError::Host("the verification was cancelled".into()));
    }
    let report: Value = serde_json::from_slice(&stdout).map_err(|_| {
        err(format!(
            "the verification could not complete: {}",
            messages.trim()
        ))
    })?;
    let stamped = json!({
        "binding": bound,
        "verified_at_utc": vv_platform::library::now_utc(),
        "engine": paths.engine.file_name().map(|n| n.to_string_lossy().into_owned()),
        "report": report,
    });
    let target = verification_path(&paths, &name);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(err)?;
    }
    let tmp = target.with_extension("tmp");
    fs::write(&tmp, serde_json::to_vec_pretty(&stamped).map_err(err)?).map_err(err)?;
    fs::rename(&tmp, &target).map_err(err)?;
    Ok(stamped)
}

#[tauri::command]
pub fn cancel_investigation(state: State<AppState>) -> Result<bool, PlatformError> {
    let mut r = state.discovery.running.lock().map_err(err)?;
    match r.child.clone() {
        Some(c) => {
            r.cancelled = true;
            let _ = c.lock().map_err(err)?.kill();
            Ok(true)
        }
        None => Ok(false),
    }
}

/// Shows a package folder in Explorer. Only packages of the library can be revealed.
#[tauri::command]
pub fn reveal_investigation(
    app: tauri::AppHandle,
    state: State<AppState>,
    name: String,
) -> Result<(), PlatformError> {
    use tauri_plugin_opener::OpenerExt;
    let dir = package_dir(&state.discovery.paths, &name)?;
    app.opener()
        .reveal_item_in_dir(dir.join("investigation.json"))
        .map_err(err)
}
