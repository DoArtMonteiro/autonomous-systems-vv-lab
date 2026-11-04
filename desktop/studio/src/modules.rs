//! Optional modules (M17): the Cinematic View, a separately installed high-fidelity replay renderer
//! built on Godot 4.7.2. The Studio never downloads it. The user picks a module zip; the Studio
//! checks the zip's SHA-256 against the `.sha256` file beside it, reads the manifest
//! (`vv-cinematic-module.v1`), checks the free disk space, extracts into a staging folder while
//! hashing every file against the manifest, and renames the staging folder into place:
//! `<app local data>/modules/cinematic/<version>/`. Nothing is installed if any check fails.
//!
//! Launching re-verifies every file of the installed module, then starts only the module's own
//! executable with fixed arguments: the project folder, a run folder of the library (by run id) and
//! a validated environment pack (by id). No shell, no paths from the web view. The renderer only
//! reads the record and the pack; it never writes to the library.
//!
//! Zip extraction uses the `zip` crate already in the lock file (the platform's evidence export
//! uses it), with the same version and features, so no new dependency is added.

use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use tauri::State;
use tauri_plugin_dialog::DialogExt;
use vv_platform::PlatformError;

use crate::{AppState, blocking, display_path, err, log_line};

pub const MANIFEST: &str = "vv-cinematic-module.json";
pub const SCHEMA: &str = "vv-cinematic-module.v1";
pub const INTERFACE: &str = "vv-cinematic-launch.v1";
const MAX_MANIFEST_BYTES: u64 = 1024 * 1024;
const MAX_FILE_BYTES: u64 = 512 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 1024 * 1024 * 1024;
const MAX_FILES: usize = 512;
/// Space kept free beyond the module itself during installation.
const DISK_MARGIN_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Clone, Debug)]
struct FileEntry {
    path: String,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug)]
struct Manifest {
    version: String,
    exe: String,
    project: String,
    godot: String,
    disk_bytes: u64,
    min_vram_bytes: u64,
    files: Vec<FileEntry>,
}

#[derive(Serialize, Clone, Debug, Default)]
pub struct Status {
    pub installed: bool,
    pub verified: bool,
    pub version: Option<String>,
    pub godot: Option<String>,
    pub disk_bytes: Option<u64>,
    pub min_vram_bytes: Option<u64>,
    pub location: Option<String>,
    /// Why the module is not usable, in words for the interface.
    pub reason: Option<String>,
}

pub struct Modules {
    /// `<app local data>/modules/cinematic`
    pub root: PathBuf,
    child: Mutex<Option<Child>>,
}

impl Modules {
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            child: Mutex::new(None),
        }
    }
}

fn invalid(m: impl Into<String>) -> PlatformError {
    PlatformError::Invalid(m.into())
}

/// A relative path of plain components only (no root, no `..`, no drive, no backslash).
fn safe_relative(p: &str) -> bool {
    if p.is_empty() || p.len() > 260 || p.contains('\\') || p.contains(':') {
        return false;
    }
    Path::new(p)
        .components()
        .all(|c| matches!(c, Component::Normal(_)))
}

fn version_ok(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 20
        && v.split('.').count() == 3
        && v.split('.')
            .all(|p| !p.is_empty() && p.chars().all(|c| c.is_ascii_digit()))
}

fn parse_manifest(bytes: &[u8]) -> Result<Manifest, PlatformError> {
    let v: Value = serde_json::from_slice(bytes).map_err(|e| invalid(format!("manifest: {e}")))?;
    let s = |k: &str| v.get(k).and_then(Value::as_str).unwrap_or("");
    if s("schema") != SCHEMA || s("module") != "cinematic" {
        return Err(invalid("this is not a Cinematic View module"));
    }
    let version = s("version").to_string();
    if !version_ok(&version) {
        return Err(invalid("the module version is not of the form x.y.z"));
    }
    if v.pointer("/studio_contract/interface")
        .and_then(Value::as_str)
        != Some(INTERFACE)
    {
        return Err(invalid(format!(
            "the module does not implement the Studio interface {INTERFACE}"
        )));
    }
    let exe = v
        .pointer("/entry/exe")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let project = v
        .pointer("/entry/project")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    if !safe_relative(&exe) || !exe.ends_with(".exe") || !safe_relative(&project) {
        return Err(invalid(
            "the module entry point is not a plain relative path",
        ));
    }
    let mut files = Vec::new();
    let mut seen = BTreeMap::new();
    let mut total = 0u64;
    for f in v
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("manifest has no file list"))?
    {
        let path = f
            .get("path")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let bytes = f.get("bytes").and_then(Value::as_u64).unwrap_or(u64::MAX);
        let sha = f
            .get("sha256")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_lowercase();
        if !safe_relative(&path) || path == MANIFEST {
            return Err(invalid(format!("manifest lists an unsafe path {path:?}")));
        }
        if bytes > MAX_FILE_BYTES || sha.len() != 64 || !sha.chars().all(|c| c.is_ascii_hexdigit())
        {
            return Err(invalid(format!("manifest entry {path:?} is malformed")));
        }
        if seen.insert(path.to_lowercase(), ()).is_some() {
            return Err(invalid(format!("manifest lists {path:?} twice")));
        }
        total += bytes;
        files.push(FileEntry {
            path,
            bytes,
            sha256: sha,
        });
    }
    if files.is_empty() || files.len() > MAX_FILES || total > MAX_TOTAL_BYTES {
        return Err(invalid("the module file list is empty or too large"));
    }
    let disk_bytes = v.get("disk_bytes").and_then(Value::as_u64).unwrap_or(0);
    if disk_bytes != total {
        return Err(invalid("the declared size does not match the file list"));
    }
    if !files.iter().any(|f| f.path == exe) {
        return Err(invalid("the module executable is not in the file list"));
    }
    let project_file = format!("{project}/project.godot");
    if !files.iter().any(|f| f.path == project_file) {
        return Err(invalid("the module project is not in the file list"));
    }
    Ok(Manifest {
        version,
        exe,
        project,
        godot: v
            .pointer("/godot/version")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        disk_bytes,
        min_vram_bytes: v.get("min_vram_bytes").and_then(Value::as_u64).unwrap_or(0),
        files,
    })
}

fn sha256_reader(mut r: impl Read) -> std::io::Result<(String, u64)> {
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut n = 0u64;
    loop {
        let k = r.read(&mut buf)?;
        if k == 0 {
            break;
        }
        n += k as u64;
        h.update(&buf[..k]);
    }
    Ok((format!("{:x}", h.finalize()), n))
}

fn sha256_file(p: &Path) -> std::io::Result<(String, u64)> {
    sha256_reader(fs::File::open(p)?)
}

/// The single installed version folder, if any (`<root>/<x.y.z>`).
fn installed_dir(root: &Path) -> Option<PathBuf> {
    let mut found: Vec<PathBuf> = fs::read_dir(root)
        .ok()?
        .flatten()
        .filter(|e| e.path().is_dir())
        .filter(|e| version_ok(&e.file_name().to_string_lossy()))
        .map(|e| e.path())
        .collect();
    found.sort();
    found.pop()
}

/// Reads and checks the installed module: manifest, then every listed file's size and SHA-256.
fn verify_installed(dir: &Path) -> Result<Manifest, String> {
    let mp = dir.join(MANIFEST);
    let meta = fs::metadata(&mp).map_err(|_| "the module manifest is missing".to_string())?;
    if meta.len() > MAX_MANIFEST_BYTES {
        return Err("the module manifest is too large".into());
    }
    let m =
        parse_manifest(&fs::read(&mp).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    if dir.file_name().map(|n| n.to_string_lossy().to_string()) != Some(m.version.clone()) {
        return Err("the module folder does not match its manifest version".into());
    }
    for f in &m.files {
        let (sha, n) = sha256_file(&dir.join(&f.path))
            .map_err(|_| format!("{} is missing or unreadable", f.path))?;
        if n != f.bytes || sha != f.sha256 {
            return Err(format!(
                "{} does not match the manifest (modified or damaged)",
                f.path
            ));
        }
    }
    Ok(m)
}

fn status_of(root: &Path) -> Status {
    let Some(dir) = installed_dir(root) else {
        return Status {
            reason: Some("The Cinematic View module is not installed. Install it from Settings with a module zip and its .sha256 file.".into()),
            ..Status::default()
        };
    };
    match verify_installed(&dir) {
        Ok(m) => Status {
            installed: true,
            verified: true,
            version: Some(m.version),
            godot: Some(m.godot),
            disk_bytes: Some(m.disk_bytes),
            min_vram_bytes: Some(m.min_vram_bytes),
            location: Some(display_path(&dir)),
            reason: None,
        },
        Err(e) => Status {
            installed: true,
            verified: false,
            location: Some(display_path(&dir)),
            reason: Some(format!(
                "The installed module failed verification: {e}. Reinstall or uninstall it."
            )),
            ..Status::default()
        },
    }
}

/// Free bytes on the volume holding `path` (Windows); None where it cannot be read.
#[cfg(windows)]
fn free_bytes(path: &Path) -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetDiskFreeSpaceExW(
            dir: *const u16,
            avail: *mut u64,
            total: *mut u64,
            free: *mut u64,
        ) -> i32;
    }
    let wide: Vec<u16> = path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    let mut avail = 0u64;
    // SAFETY: `wide` is a NUL-terminated UTF-16 path that outlives the call; the out pointer refers
    // to a live u64 and the two optional out pointers are null, as the Win32 contract allows.
    let ok = unsafe {
        GetDiskFreeSpaceExW(
            wide.as_ptr(),
            &mut avail,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    (ok != 0).then_some(avail)
}

#[cfg(not(windows))]
fn free_bytes(_path: &Path) -> Option<u64> {
    None
}

/// Verifies `zip_path` against its `.sha256` sidecar and installs it under `root`.
pub fn install_zip(root: &Path, zip_path: &Path) -> Result<Status, PlatformError> {
    let side = PathBuf::from(format!("{}.sha256", zip_path.display()));
    let declared = fs::read_to_string(&side)
        .map_err(|_| invalid("the .sha256 file beside the module zip is missing"))?;
    let declared = declared
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_lowercase();
    let (actual, _) = sha256_file(zip_path).map_err(err)?;
    if declared.len() != 64 || declared != actual {
        return Err(invalid("the module zip does not match its .sha256 file"));
    }
    let file = fs::File::open(zip_path).map_err(err)?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| invalid(format!("not a zip: {e}")))?;
    let manifest_bytes = {
        let mut e = zip
            .by_name(MANIFEST)
            .map_err(|_| invalid("the zip has no module manifest"))?;
        if e.size() > MAX_MANIFEST_BYTES {
            return Err(invalid("the module manifest is too large"));
        }
        let mut b = Vec::new();
        e.read_to_end(&mut b).map_err(err)?;
        b
    };
    let m = parse_manifest(&manifest_bytes)?;
    // Every entry of the zip is the manifest or a listed file; nothing else is extracted.
    let listed: BTreeMap<&str, &FileEntry> = m.files.iter().map(|f| (f.path.as_str(), f)).collect();
    for i in 0..zip.len() {
        let e = zip.by_index(i).map_err(err)?;
        let name = e.name().to_string();
        if e.is_dir() {
            continue;
        }
        if e.enclosed_name().is_none() || (name != MANIFEST && !listed.contains_key(name.as_str()))
        {
            return Err(invalid(format!(
                "the zip holds a file the manifest does not list: {name:?}"
            )));
        }
        if e.is_symlink() {
            return Err(invalid(format!("the zip holds a link: {name:?}")));
        }
    }
    fs::create_dir_all(root).map_err(err)?;
    if let Some(free) = free_bytes(root)
        && free < m.disk_bytes + DISK_MARGIN_BYTES
    {
        return Err(invalid(format!(
            "not enough free disk space: the module needs {} MB and {} MB are free",
            (m.disk_bytes + DISK_MARGIN_BYTES) / 1_048_576,
            free / 1_048_576
        )));
    }
    let staging = root.join(format!(".staging-{}", std::process::id()));
    let _ = fs::remove_dir_all(&staging);
    let result = (|| -> Result<(), PlatformError> {
        for f in &m.files {
            let mut e = zip
                .by_name(&f.path)
                .map_err(|_| invalid(format!("{} is listed but not in the zip", f.path)))?;
            if e.size() != f.bytes {
                return Err(invalid(format!("{} has the wrong size in the zip", f.path)));
            }
            let dst = staging.join(&f.path);
            if let Some(d) = dst.parent() {
                fs::create_dir_all(d).map_err(err)?;
            }
            let mut out = fs::File::create(&dst).map_err(err)?;
            let mut h = Sha256::new();
            let mut buf = vec![0u8; 1 << 20];
            let mut n = 0u64;
            loop {
                let k = e.read(&mut buf).map_err(err)?;
                if k == 0 {
                    break;
                }
                n += k as u64;
                if n > f.bytes {
                    return Err(invalid(format!("{} is larger than declared", f.path)));
                }
                h.update(&buf[..k]);
                out.write_all(&buf[..k]).map_err(err)?;
            }
            if n != f.bytes || format!("{:x}", h.finalize()) != f.sha256 {
                return Err(invalid(format!(
                    "{} does not match its SHA-256 in the manifest",
                    f.path
                )));
            }
        }
        fs::write(staging.join(MANIFEST), &manifest_bytes).map_err(err)?;
        Ok(())
    })();
    if let Err(e) = result {
        let _ = fs::remove_dir_all(&staging);
        return Err(e);
    }
    // One installed version: earlier versions (and a damaged copy of this one) are removed first.
    if let Ok(entries) = fs::read_dir(root) {
        for e in entries.flatten() {
            let n = e.file_name().to_string_lossy().to_string();
            if e.path().is_dir() && version_ok(&n) {
                let _ = fs::remove_dir_all(e.path());
            }
        }
    }
    let target = root.join(&m.version);
    if let Err(e) = fs::rename(&staging, &target) {
        let _ = fs::remove_dir_all(&staging);
        return Err(err(e));
    }
    Ok(status_of(root))
}

/// Removes every installed version and any staging folder.
pub fn uninstall(root: &Path) -> Result<Status, PlatformError> {
    if root.exists() {
        fs::remove_dir_all(root).map_err(err)?;
    }
    Ok(status_of(root))
}

/// Verifies the installed module and returns the executable and the fixed arguments for a run
/// folder and a pack folder (both resolved by the Studio).
pub fn launch_command(
    root: &Path,
    run_dir: &Path,
    env_dir: &Path,
) -> Result<(PathBuf, Vec<String>), PlatformError> {
    let dir =
        installed_dir(root).ok_or_else(|| invalid("the Cinematic View module is not installed"))?;
    let m = verify_installed(&dir)
        .map_err(|e| invalid(format!("the installed module failed verification: {e}")))?;
    let exe = dir.join(&m.exe);
    let args = vec![
        "--path".to_string(),
        dir.join(&m.project).display().to_string(),
        "--".to_string(),
        "--run".to_string(),
        run_dir.display().to_string(),
        "--env".to_string(),
        env_dir.display().to_string(),
        "--profile".to_string(),
        "auto".to_string(),
    ];
    Ok((exe, args))
}

// ---------------------------------------------------------------------------------- commands

#[tauri::command]
pub async fn cinematic_status(state: State<'_, AppState>) -> Result<Status, PlatformError> {
    let root = state.modules.root.clone();
    blocking(move || Ok(status_of(&root))).await
}

#[tauri::command]
pub async fn cinematic_install_from_file(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<Status>, PlatformError> {
    let root = state.modules.root.clone();
    let log = state.paths.log.clone();
    blocking(move || {
        let picked = app
            .dialog()
            .file()
            .set_title("Choose a Cinematic View module (vv-cinematic-x.y.z.zip, with its .sha256 beside it)")
            .add_filter("Cinematic View module", &["zip"])
            .blocking_pick_file();
        let Some(zip_path) = picked.and_then(|f| f.into_path().ok()) else {
            return Ok(None);
        };
        let s = install_zip(&root, &zip_path).inspect_err(|e| {
            log_line(&log, &format!("cinematic module install refused: {e}"));
        })?;
        log_line(&log, &format!("cinematic module installed {:?}", s.version));
        Ok(Some(s))
    })
    .await
}

#[tauri::command]
pub async fn cinematic_uninstall(state: State<'_, AppState>) -> Result<Status, PlatformError> {
    let root = state.modules.root.clone();
    let log = state.paths.log.clone();
    if let Ok(mut c) = state.modules.child.lock()
        && let Some(mut child) = c.take()
    {
        let _ = child.kill();
        let _ = child.wait();
    }
    blocking(move || {
        let s = uninstall(&root)?;
        log_line(&log, "cinematic module uninstalled");
        Ok(s)
    })
    .await
}

#[tauri::command]
pub async fn cinematic_launch(
    state: State<'_, AppState>,
    run_id: String,
    env_id: String,
) -> Result<(), PlatformError> {
    let p = state.platform()?;
    let run_dir = p.library().run_dir(&run_id).map_err(invalid)?;
    if !p.library().has_run(&run_id) {
        return Err(PlatformError::NotFound(format!("no stored run {run_id}")));
    }
    let (_, env) = state.geo.get(&env_id)?;
    let env_dir = env.dir.clone();
    let root = state.modules.root.clone();
    let (exe, args) = blocking(move || launch_command(&root, &run_dir, &env_dir)).await?;
    let mut slot = state.modules.child.lock().map_err(err)?;
    if let Some(c) = slot.as_mut()
        && matches!(c.try_wait(), Ok(None))
    {
        return Err(invalid(
            "the Cinematic View is already open; close it first",
        ));
    }
    let child = Command::new(&exe)
        .args(&args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(err)?;
    log_line(
        &state.paths.log,
        &format!("cinematic view started for run {run_id} on {env_id}"),
    );
    *slot = Some(child);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn hex(b: &[u8]) -> String {
        format!("{:x}", Sha256::digest(b))
    }

    fn build_zip(
        dir: &Path,
        files: &[(&str, &[u8])],
        extra: Option<(&str, &[u8])>,
        tweak: impl Fn(&mut Value),
    ) -> PathBuf {
        let mut list = Vec::new();
        let mut total = 0u64;
        for (p, b) in files {
            list.push(serde_json::json!({"path": p, "bytes": b.len(), "sha256": hex(b)}));
            total += b.len() as u64;
        }
        let mut m = serde_json::json!({
            "schema": SCHEMA, "module": "cinematic", "version": "0.1.0",
            "studio_contract": {"interface": INTERFACE},
            "godot": {"version": "4.7.2-stable"},
            "entry": {"exe": "godot/g.exe", "project": "project"},
            "disk_bytes": total, "min_vram_bytes": 1, "files": list,
        });
        tweak(&mut m);
        let zp = dir.join("m.zip");
        let mut z = zip::ZipWriter::new(fs::File::create(&zp).unwrap());
        let o = zip::write::SimpleFileOptions::default();
        z.start_file(MANIFEST, o).unwrap();
        z.write_all(serde_json::to_string(&m).unwrap().as_bytes())
            .unwrap();
        for (p, b) in files {
            z.start_file(*p, o).unwrap();
            z.write_all(b).unwrap();
        }
        if let Some((p, b)) = extra {
            z.start_file(p, o).unwrap();
            z.write_all(b).unwrap();
        }
        z.finish().unwrap();
        let (sha, _) = sha256_file(&zp).unwrap();
        fs::write(dir.join("m.zip.sha256"), format!("{sha}  m.zip\n")).unwrap();
        zp
    }

    const FILES: &[(&str, &[u8])] = &[
        ("godot/g.exe", b"MZ fake"),
        ("project/project.godot", b"config_version=5\n"),
    ];

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("vv-modules-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn installs_verifies_and_uninstalls() {
        let d = tmp("ok");
        let zp = build_zip(&d, FILES, None, |_| {});
        let root = d.join("modules").join("cinematic");
        let s = install_zip(&root, &zp).unwrap();
        assert!(s.installed && s.verified, "{s:?}");
        assert_eq!(s.version.as_deref(), Some("0.1.0"));
        let (exe, args) = launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        assert!(exe.ends_with("0.1.0/godot/g.exe") || exe.ends_with("0.1.0\\godot\\g.exe"));
        assert_eq!(
            args[2..],
            ["--", "--run", "R", "--env", "E", "--profile", "auto"]
        );
        // A modified installed file fails verification and blocks the launch.
        fs::write(root.join("0.1.0").join("godot").join("g.exe"), b"MZ evil").unwrap();
        let s = status_of(&root);
        assert!(s.installed && !s.verified);
        assert!(launch_command(&root, Path::new("R"), Path::new("E")).is_err());
        let s = uninstall(&root).unwrap();
        assert!(!s.installed && !root.exists());
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn refuses_bad_zips() {
        type Make = Box<dyn Fn(&Path) -> PathBuf>;
        let cases: Vec<(&str, Make)> = vec![
            (
                "sidecar",
                Box::new(|d| {
                    let z = build_zip(d, FILES, None, |_| {});
                    fs::write(d.join("m.zip.sha256"), "0".repeat(64)).unwrap();
                    z
                }),
            ),
            (
                "unlisted",
                Box::new(|d| build_zip(d, FILES, Some(("extra.dll", b"x")), |_| {})),
            ),
            (
                "traversal",
                Box::new(|d| {
                    build_zip(d, FILES, None, |m| {
                        m["files"][0]["path"] = "../g.exe".into()
                    })
                }),
            ),
            (
                "hash",
                Box::new(|d| {
                    build_zip(d, FILES, None, |m| {
                        m["files"][1]["sha256"] = "0".repeat(64).into()
                    })
                }),
            ),
            (
                "schema",
                Box::new(|d| build_zip(d, FILES, None, |m| m["schema"] = "other".into())),
            ),
            (
                "interface",
                Box::new(|d| {
                    build_zip(d, FILES, None, |m| {
                        m["studio_contract"]["interface"] = "x".into()
                    })
                }),
            ),
            (
                "size",
                Box::new(|d| build_zip(d, FILES, None, |m| m["disk_bytes"] = 1.into())),
            ),
        ];
        for (name, make) in cases {
            let d = tmp(name);
            let zp = make(&d);
            let root = d.join("modules").join("cinematic");
            assert!(install_zip(&root, &zp).is_err(), "{name} was accepted");
            assert!(
                installed_dir(&root).is_none(),
                "{name} left an installation"
            );
            let _ = fs::remove_dir_all(&d);
        }
    }

    /// The real module zip, when VV_CINEMATIC_ZIP names one (built by
    /// scripts/cinematic/package_module.py): it installs, verifies and uninstalls.
    #[test]
    fn real_module_zip_installs_when_given() {
        let Some(zp) = std::env::var_os("VV_CINEMATIC_ZIP").map(PathBuf::from) else {
            return;
        };
        let d = tmp("real");
        let root = d.join("modules").join("cinematic");
        let s = install_zip(&root, &zp).unwrap();
        assert!(s.installed && s.verified, "{s:?}");
        let (exe, args) = launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        assert!(exe.is_file());
        assert!(Path::new(&args[1]).join("project.godot").is_file());
        assert!(!uninstall(&root).unwrap().installed);
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn paths_must_be_plain_relative() {
        for bad in ["", "../a", "/a", "C:/a", "a\\b", "a/../b"] {
            assert!(!safe_relative(bad), "{bad}");
        }
        assert!(safe_relative("project/scripts/main.gd"));
    }
}
