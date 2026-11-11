//! V&V Lab Studio, the Windows desktop shell. It owns the application lifecycle: it locates the
//! installed domain hosts and the research library, starts the platform (discovery, catalogs,
//! interrupted-run recovery) off the UI thread, exposes the platform to the interface through a
//! small set of commands, and stops cleanly. Simulations run in domain host processes, never in
//! this process and never in the web view; the web view only receives results.
//!
//! Locations (Windows):
//! - domain hosts: `<install dir>/domains/<id>/` (read-only, replaced by updates);
//! - research library: `Documents/VV Lab Library/` (runs, scenarios, comparisons, exports and
//!   M13 investigations), kept by uninstall;
//! - Discovery Lab (M13): the investigation engine `<install dir>/engines/vv-exec.exe` and the
//!   claims under `<install dir>/discovery/claims/`, run as child processes (see `discovery.rs`);
//! - geographic environments (M16): packs shipped under `<install dir>/environments/` and packs the
//!   user imports under `Documents/VV Lab Library/environments/` (see `geo.rs`); no network;
//! - preferences and log: the per-user application config and log directories.
//!
//! `vv-studio --self-test <report.json>` runs headless: it starts the platform, runs and replays the
//! first demonstration of every user-facing domain, writes a JSON report and exits 0 when all pass.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod discovery;
mod geo;

use std::collections::BTreeSet;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};

use serde::Serialize;
use serde_json::{Value, json};
use tauri::{Manager, State, webview::PageLoadEvent};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use vv_platform::discovery::Rejected;
use vv_platform::library::{RunMeta, SavedComparison, SavedScenario};
use vv_platform::service::{DomainInfo, RunOutcome, StartReport};
use vv_platform::{
    CONTRACT_MAJOR, CONTRACT_MINOR, Platform, PlatformError, ReplayReport, RunRecord, RunRequest,
};

const VERSION: &str = env!("CARGO_PKG_VERSION");
const MAX_PREFS_BYTES: usize = 64 * 1024;

#[derive(Clone)]
struct Paths {
    domains: Vec<PathBuf>,
    library: PathBuf,
    prefs: PathBuf,
    log: PathBuf,
}

struct AppState {
    paths: Paths,
    geo: Arc<geo::Geo>,
    discovery: discovery::Discovery,
    platform: RwLock<Option<Arc<Platform>>>,
    start: Mutex<Option<Result<StartReport, String>>>,
    exports: Mutex<BTreeSet<PathBuf>>,
}

#[derive(Serialize)]
struct AppInfo {
    version: String,
    contract: String,
    library: String,
    ready: bool,
    start: Option<StartReport>,
    start_error: Option<String>,
}

#[derive(Serialize)]
struct DomainList {
    domains: Vec<DomainInfo>,
    rejected: Vec<Rejected>,
}

#[derive(Serialize)]
#[serde(tag = "status", rename_all = "snake_case")]
enum CompareItem {
    Ok { outcome: Box<RunOutcome> },
    Error { error: PlatformError },
}

fn err(e: impl std::fmt::Display) -> PlatformError {
    PlatformError::Io(e.to_string())
}

fn log_line(path: &Path, message: &str) {
    if let Some(dir) = path.parent() {
        let _ = fs::create_dir_all(dir);
    }
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{} {message}", vv_platform::library::now_utc());
    }
}

/// A path for display: the user profile folder becomes %USERPROFILE%, so screenshots and shared
/// screens do not carry the account name. Commands keep using the real path.
fn display_path(path: &Path) -> String {
    let text = path.display().to_string();
    match std::env::var("USERPROFILE") {
        Ok(home) if !home.is_empty() && text.to_lowercase().starts_with(&home.to_lowercase()) => {
            format!("%USERPROFILE%{}", &text[home.len()..])
        }
        _ => text,
    }
}

fn start_platform(paths: &Paths, first: bool) -> Result<(Platform, StartReport), String> {
    // Only the first start clears staging: on a restart, runs of the old instance may still be
    // executing there.
    Platform::start_with(&paths.domains, &paths.library, VERSION, first)
}

impl AppState {
    fn platform(&self) -> Result<Arc<Platform>, PlatformError> {
        self.platform
            .read()
            .map_err(err)?
            .clone()
            .ok_or_else(|| PlatformError::Io("the platform is still starting".into()))
    }

    fn install(&self, outcome: Result<(Platform, StartReport), String>) {
        let report = match outcome {
            Ok((platform, report)) => {
                if let Ok(mut slot) = self.platform.write() {
                    *slot = Some(Arc::new(platform));
                }
                for r in &report.rejected {
                    log_line(
                        &self.paths.log,
                        &format!("domain {} rejected: {}", r.dir, r.reason),
                    );
                }
                Ok(report)
            }
            Err(e) => {
                log_line(&self.paths.log, &format!("platform start failed: {e}"));
                Err(e)
            }
        };
        if let Ok(mut slot) = self.start.lock() {
            *slot = Some(report);
        }
    }
}

async fn blocking<T: Send + 'static>(
    job: impl FnOnce() -> Result<T, PlatformError> + Send + 'static,
) -> Result<T, PlatformError> {
    tauri::async_runtime::spawn_blocking(job)
        .await
        .map_err(err)?
}

// ---------------------------------------------------------------------------------- commands

#[tauri::command]
fn app_info(state: State<AppState>) -> AppInfo {
    let start = state.start.lock().ok().and_then(|s| s.clone());
    AppInfo {
        version: VERSION.into(),
        contract: format!("vv-domain {CONTRACT_MAJOR}.{CONTRACT_MINOR}"),
        library: display_path(&state.paths.library),
        ready: matches!(start, Some(Ok(_))),
        start_error: start.as_ref().and_then(|s| s.as_ref().err().cloned()),
        start: start.and_then(Result::ok),
    }
}

#[tauri::command]
fn list_domains(state: State<AppState>) -> Result<DomainList, PlatformError> {
    let p = state.platform()?;
    Ok(DomainList {
        domains: p.domains(),
        rejected: p.rejected().to_vec(),
    })
}

#[tauri::command]
async fn restart_platform(state: State<'_, AppState>) -> Result<AppInfo, PlatformError> {
    let paths = state.paths.clone();
    let outcome = tauri::async_runtime::spawn_blocking(move || start_platform(&paths, false))
        .await
        .map_err(err)?;
    state.install(outcome);
    Ok(app_info(state))
}

#[tauri::command]
async fn validate(
    state: State<'_, AppState>,
    request: RunRequest,
) -> Result<RunRequest, PlatformError> {
    let p = state.platform()?;
    blocking(move || p.validate(&request)).await
}

#[tauri::command]
async fn run(state: State<'_, AppState>, request: RunRequest) -> Result<RunOutcome, PlatformError> {
    let p = state.platform()?;
    let log = state.paths.log.clone();
    blocking(move || {
        p.run(&request).inspect_err(|e| {
            if matches!(e, PlatformError::Host(_) | PlatformError::Io(_)) {
                log_line(&log, &format!("run failed: {e}"));
            }
        })
    })
    .await
}

#[tauri::command]
async fn compare(
    state: State<'_, AppState>,
    requests: Vec<RunRequest>,
) -> Result<Vec<CompareItem>, PlatformError> {
    let p = state.platform()?;
    let results = blocking(move || p.compare(&requests)).await?;
    Ok(results
        .into_iter()
        .map(|r| match r {
            Ok(outcome) => CompareItem::Ok {
                outcome: Box::new(outcome),
            },
            Err(error) => CompareItem::Error { error },
        })
        .collect())
}

#[tauri::command]
async fn record(state: State<'_, AppState>, run_id: String) -> Result<RunRecord, PlatformError> {
    let p = state.platform()?;
    blocking(move || p.record(&run_id)).await
}

#[tauri::command]
async fn list_runs(state: State<'_, AppState>) -> Result<Vec<RunMeta>, PlatformError> {
    let p = state.platform()?;
    blocking(move || Ok(p.library().list_runs())).await
}

#[tauri::command]
async fn update_notes(
    state: State<'_, AppState>,
    run_id: String,
    label: String,
    notes: String,
    tags: Vec<String>,
) -> Result<RunMeta, PlatformError> {
    let p = state.platform()?;
    blocking(move || {
        p.library()
            .update_notes(&run_id, &label, &notes, &tags)
            .map_err(err)
    })
    .await
}

#[tauri::command]
async fn replay(state: State<'_, AppState>, run_id: String) -> Result<ReplayReport, PlatformError> {
    let p = state.platform()?;
    blocking(move || p.replay(&run_id)).await
}

/// Exports an evidence package. With `choose`, asks where to save it; returns None if cancelled.
#[tauri::command]
async fn export_evidence(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    run_id: String,
    choose: bool,
) -> Result<Option<String>, PlatformError> {
    let p = state.platform()?;
    let dest = if choose {
        let name = format!("{run_id}-evidence.zip");
        let picked = app
            .dialog()
            .file()
            .set_title("Save evidence package")
            .set_file_name(&name)
            .add_filter("Evidence package", &["zip"])
            .blocking_save_file();
        match picked.and_then(|f| f.into_path().ok()) {
            Some(path) => Some(path),
            None => return Ok(None),
        }
    } else {
        None
    };
    let path = blocking(move || p.export_evidence(&run_id, dest)).await?;
    if let Ok(mut set) = state.exports.lock() {
        set.insert(path.clone());
    }
    Ok(Some(path.display().to_string()))
}

/// Shows an exported package or the library folder in Explorer. Only paths this session exported,
/// or the library root itself, can be revealed.
#[tauri::command]
fn reveal(
    app: tauri::AppHandle,
    state: State<AppState>,
    path: Option<String>,
) -> Result<(), PlatformError> {
    let target = match path {
        None => state.paths.library.clone(),
        Some(p) => {
            let p = PathBuf::from(p);
            let known = state
                .exports
                .lock()
                .map(|s| s.contains(&p))
                .unwrap_or(false);
            if !known {
                return Err(PlatformError::Invalid(
                    "only exported packages can be revealed".into(),
                ));
            }
            p
        }
    };
    app.opener().reveal_item_in_dir(target).map_err(err)
}

#[tauri::command]
async fn save_scenario(
    state: State<'_, AppState>,
    name: String,
    notes: String,
    requests: Vec<RunRequest>,
) -> Result<SavedScenario, PlatformError> {
    let p = state.platform()?;
    blocking(move || {
        // Only requests the platform accepts are saved, so a saved scenario always reopens.
        for r in &requests {
            p.validate(r)?;
        }
        p.library()
            .save_scenario(&name, &notes, requests)
            .map_err(err)
    })
    .await
}

#[tauri::command]
fn list_scenarios(state: State<AppState>) -> Result<Vec<SavedScenario>, PlatformError> {
    Ok(state.platform()?.library().list_scenarios())
}

#[tauri::command]
fn delete_scenario(state: State<AppState>, id: String) -> Result<(), PlatformError> {
    state
        .platform()?
        .library()
        .delete_scenario(&id)
        .map_err(err)
}

#[tauri::command]
fn save_comparison(
    state: State<AppState>,
    name: String,
    notes: String,
    run_ids: Vec<String>,
) -> Result<SavedComparison, PlatformError> {
    state
        .platform()?
        .library()
        .save_comparison(&name, &notes, run_ids)
        .map_err(err)
}

#[tauri::command]
fn list_comparisons(state: State<AppState>) -> Result<Vec<SavedComparison>, PlatformError> {
    Ok(state.platform()?.library().list_comparisons())
}

#[tauri::command]
fn delete_comparison(state: State<AppState>, id: String) -> Result<(), PlatformError> {
    state
        .platform()?
        .library()
        .delete_comparison(&id)
        .map_err(err)
}

#[tauri::command]
fn get_prefs(state: State<AppState>) -> Value {
    fs::read(&state.paths.prefs)
        .ok()
        .filter(|b| b.len() <= MAX_PREFS_BYTES)
        .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}))
}

#[tauri::command]
fn set_prefs(state: State<AppState>, prefs: Value) -> Result<(), PlatformError> {
    if !prefs.is_object() {
        return Err(PlatformError::Invalid(
            "preferences must be an object".into(),
        ));
    }
    let bytes = serde_json::to_vec_pretty(&prefs).map_err(err)?;
    if bytes.len() > MAX_PREFS_BYTES {
        return Err(PlatformError::Invalid("preferences are too large".into()));
    }
    if let Some(dir) = state.paths.prefs.parent() {
        fs::create_dir_all(dir).map_err(err)?;
    }
    vv_platform::library::write_atomic(&state.paths.prefs, &bytes).map_err(err)
}

#[tauri::command]
fn log_ui_error(state: State<AppState>, message: String) {
    let message: String = message.chars().take(2000).collect();
    log_line(&state.paths.log, &format!("ui: {message}"));
}

// ---------------------------------------------------------------------------------- startup

fn env_dirs(name: &str) -> Vec<PathBuf> {
    std::env::var_os(name)
        .map(|v| std::env::split_paths(&v).collect())
        .unwrap_or_default()
}

fn discovery_paths(app: &tauri::App, library: &Path) -> discovery::DiscoveryPaths {
    let res = app.path().resource_dir().unwrap_or_default();
    discovery::DiscoveryPaths {
        engine: std::env::var_os("VVLAB_EXEC")
            .map(PathBuf::from)
            .unwrap_or_else(|| res.join("engines").join("vv-exec.exe")),
        claims: std::env::var_os("VVLAB_CLAIMS")
            .map(PathBuf::from)
            .unwrap_or_else(|| res.join("discovery").join("claims")),
        investigations: library.join("investigations"),
    }
}

fn resolve_paths(app: &tauri::App) -> Paths {
    let resolver = app.path();
    let mut domains = env_dirs("VVLAB_DOMAINS");
    if domains.is_empty()
        && let Ok(res) = resolver.resource_dir()
    {
        domains.push(res.join("domains"));
    }
    domains.extend(env_dirs("VVLAB_EXTRA_DOMAINS"));
    let library = std::env::var_os("VVLAB_LIBRARY")
        .map(PathBuf::from)
        .or_else(|| {
            resolver
                .document_dir()
                .ok()
                .map(|d| d.join("VV Lab Library"))
        })
        .unwrap_or_else(|| PathBuf::from("VV Lab Library"));
    // VVLAB_CONFIG puts preferences and the log in one folder, so tests never touch a real profile.
    let override_config = std::env::var_os("VVLAB_CONFIG").map(PathBuf::from);
    let config = override_config.clone().unwrap_or_else(|| {
        resolver
            .app_config_dir()
            .unwrap_or_else(|_| library.join(".config"))
    });
    let log = override_config
        .or_else(|| resolver.app_log_dir().ok())
        .unwrap_or_else(|| config.clone())
        .join("studio.log");
    Paths {
        domains,
        library,
        prefs: config.join("preferences.json"),
        log,
    }
}

/// Environment packs: `VVLAB_ENVIRONMENTS` (one or more folders) replaces the bundled folder, for
/// tests and development; imported packs live in the library.
fn geo_paths(app: &tauri::App, library: &Path) -> geo::GeoPaths {
    let mut bundled = env_dirs("VVLAB_ENVIRONMENTS");
    if bundled.is_empty()
        && let Ok(res) = app.path().resource_dir()
    {
        bundled.push(res.join("environments"));
    }
    geo::GeoPaths {
        bundled,
        imported: library.join("environments"),
    }
}

fn check(name: impl Into<String>, pass: bool, detail: Value) -> Value {
    json!({ "check": name.into(), "pass": pass, "detail": detail })
}

/// Headless acceptance check used on clean machines: no window, a JSON report, an exit status.
fn self_test(report_path: &Path) -> i32 {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_default();
    let mut domains = env_dirs("VVLAB_DOMAINS");
    if domains.is_empty() {
        domains.push(exe_dir.join("domains"));
    }
    let library = std::env::var_os("VVLAB_LIBRARY")
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::temp_dir().join("vv-lab-self-test-library"));
    let mut checks: Vec<Value> = Vec::new();
    let mut ok = true;
    match Platform::start(&domains, &library, VERSION) {
        Err(e) => {
            ok = false;
            checks.push(check("platform start", false, json!(e)));
        }
        Ok((p, start)) => {
            checks.push(check("platform start", true, json!(start)));
            for info in p.domains() {
                let id = info.manifest.id.clone();
                let Some(catalog) = info.catalog else {
                    ok = false;
                    checks.push(check(format!("{id} catalog"), false, json!(info.error)));
                    continue;
                };
                let first = catalog
                    .demos
                    .iter()
                    .flat_map(|d| d.requests.first())
                    .next()
                    .cloned();
                let Some(request) = first else {
                    let pass = !info.manifest.user_facing;
                    ok &= pass;
                    checks.push(check(
                        format!("{id} has a demonstration"),
                        pass,
                        json!("none"),
                    ));
                    continue;
                };
                let name = format!("{id} demonstration runs and replays");
                match p
                    .run(&request)
                    .and_then(|o| p.replay(&o.run_id).map(|r| (o, r)))
                {
                    Ok((o, r)) => {
                        let pass = r.status == "verified";
                        ok &= pass;
                        checks.push(check(
                            name,
                            pass,
                            json!({ "run_id": o.run_id, "outcome": o.meta.summary.outcome_code,
                                    "safety": o.meta.summary.safety_status, "replay": r.status }),
                        ));
                    }
                    Err(e) => {
                        ok = false;
                        checks.push(check(name, false, json!(e.to_string())));
                    }
                }
            }
        }
    }
    // Discovery Lab: the bundled engine reads and validates every bundled claim. A full
    // investigation is left to the UI test; it would take the self-test from seconds to minutes.
    let engine = std::env::var_os("VVLAB_EXEC")
        .map(PathBuf::from)
        .unwrap_or_else(|| exe_dir.join("engines").join("vv-exec.exe"));
    let claims = std::env::var_os("VVLAB_CLAIMS")
        .map(PathBuf::from)
        .unwrap_or_else(|| exe_dir.join("discovery").join("claims"));
    let found = discovery::self_check(&engine, &claims);
    for (name, pass, detail) in found {
        ok &= pass;
        checks.push(check(name, pass, detail));
    }
    // Geographic environments (M16): every bundled pack validates, check points included.
    let mut env_roots = env_dirs("VVLAB_ENVIRONMENTS");
    if env_roots.is_empty() {
        env_roots.push(exe_dir.join("environments"));
    }
    for root in env_roots {
        let (good, bad) = vv_geo::environment::discover(&root);
        let pass = !good.is_empty() && bad.is_empty();
        ok &= pass;
        checks.push(check(
            "environment packs",
            pass,
            json!({
                "accepted": good.iter().map(|e| json!({"id": e.id, "bytes": e.bytes(), "worst_check_m": e.worst_check_m()})).collect::<Vec<_>>(),
                "rejected": bad.iter().map(|(f, r)| json!({"folder": f, "reason": r})).collect::<Vec<_>>(),
            }),
        ));
    }
    let report = json!({ "schema": "vv-studio-self-test.v1", "version": VERSION, "pass": ok, "checks": checks });
    let _ = fs::write(
        report_path,
        serde_json::to_vec_pretty(&report).unwrap_or_default(),
    );
    if ok { 0 } else { 1 }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("--self-test") {
        let path = args
            .get(2)
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("self-test.json"));
        std::process::exit(self_test(&path));
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let paths = resolve_paths(app);
            log_line(&paths.log, &format!("start {VERSION}"));
            let disc = discovery::Discovery::new(discovery_paths(app, &paths.library));
            log_line(
                &paths.log,
                &format!("engine {}", disc.paths.engine.display()),
            );
            let geo = Arc::new(geo::Geo::new(geo_paths(app, &paths.library)));
            app.manage(AppState {
                geo,
                discovery: disc,
                paths: paths.clone(),
                platform: RwLock::new(None),
                start: Mutex::new(None),
                exports: Mutex::new(BTreeSet::new()),
            });
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let outcome = start_platform(&paths, true);
                handle.state::<AppState>().install(outcome);
            });
            Ok(())
        })
        .on_page_load(|webview, payload| {
            if payload.event() == PageLoadEvent::Finished {
                let _ = webview.window().show();
            }
        })
        .invoke_handler(tauri::generate_handler![
            app_info,
            list_domains,
            restart_platform,
            validate,
            run,
            compare,
            record,
            list_runs,
            update_notes,
            replay,
            export_evidence,
            reveal,
            save_scenario,
            list_scenarios,
            delete_scenario,
            save_comparison,
            list_comparisons,
            delete_comparison,
            get_prefs,
            set_prefs,
            log_ui_error,
            discovery::list_claims,
            discovery::list_investigations,
            discovery::investigation,
            discovery::investigate,
            discovery::verify_investigation,
            discovery::cancel_investigation,
            discovery::reveal_investigation,
            geo::list_environments,
            geo::environment_file,
            geo::geo_track,
            geo::import_environment,
            geo::remove_environment,
            geo::reveal_environments,
        ])
        .build(tauri::generate_context!())
        .expect("the studio could not start")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event
                && let Some(state) = app.try_state::<AppState>()
            {
                log_line(&state.paths.log, "exit");
            }
        });
}
