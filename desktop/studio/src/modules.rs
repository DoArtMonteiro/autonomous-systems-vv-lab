//! Optional modules (M17): the Cinematic View, a separately installed high-fidelity replay renderer
//! built on Godot 4.7.2. The Studio never downloads it. The user picks a module zip; the Studio
//! copies it once into a staging folder, hashes that copy and compares the hash with the `.sha256`
//! file beside the zip, shows the SHA-256 to the user for confirmation, reads the manifest
//! (`vv-cinematic-module.v1`) from the same copy, checks the free disk space, extracts into the
//! staging folder while hashing every file against the manifest, and swaps the staging tree into
//! place: `<app local data>/modules/cinematic/<version>/`. Nothing is installed if any check fails;
//! a replaced version is moved aside first and restored if the swap fails.
//!
//! What the checks prove. The `.sha256` file travels with the zip, so a match shows the zip is
//! intact (not damaged, not altered after that file was written). It does not show who built the
//! module: an attacker who can replace the zip can replace the sidecar too. Provenance is the
//! user's decision, which is why the computed SHA-256 is shown before anything is installed, to be
//! compared with a value from a source the user trusts. The manifest likewise proves that the files
//! match the manifest of the same zip, nothing more.
//!
//! Launching re-hashes every file of the installed module, refuses any file the manifest does not
//! list, then starts only the module's own executable with fixed arguments: the project folder, a
//! run folder of the library (by run id) and a validated environment pack (by id). No shell, no
//! paths from the web view. The renderer only reads the record and the pack; it never writes to
//! the library. The executable is hashed once more, through a handle that denies writers, right
//! before it is started. Only the executable is write-locked between that hash and the start: the
//! other files were verified moments earlier under the same lock that stops an install, and a
//! process that can rewrite files in the user's own data folder can already run code as the user.
//!
//! The one place the renderer may write inside the module is `<project>/.godot/`, Godot's own
//! script and shader cache, regenerated from the project files. The integrity check exempts that
//! single directory and the launch deletes it before the process starts, so a cache that was
//! planted or left over is never read.
//!
//! One Studio instance is supported (the single-instance plugin enforces it): the `.staging-*` and
//! `.old-*` folders are named after the process id and cleaned without coordinating with another
//! process, so two Studios sharing one modules folder could remove each other's work.
//!
//! Zip extraction uses the `zip` crate already in the lock file (the platform's evidence export
//! uses it), with the same version and features, so no new dependency is added.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::SystemTime;

use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use tauri::State;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
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
/// Largest zip the Studio copies: the module's size cap plus room for zip headers.
const MAX_ZIP_BYTES: u64 = MAX_TOTAL_BYTES + 16 * 1024 * 1024;
/// Folder under the modules root where an install is staged (the zip copy and the extracted tree).
const STAGING_PREFIX: &str = ".staging-";
/// Folder under the modules root where a replaced version waits until the new one is in place.
const OLD_PREFIX: &str = ".old-";
/// Godot's own cache inside the project folder (see the module header).
const GODOT_CACHE: &str = ".godot";

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
    /// Every file matched the manifest at the last check (see `Modules::status`); the launch
    /// checks again.
    pub verified: bool,
    pub version: Option<String>,
    pub godot: Option<String>,
    pub disk_bytes: Option<u64>,
    pub min_vram_bytes: Option<u64>,
    pub location: Option<String>,
    /// Why the module is not usable, in words for the interface.
    pub reason: Option<String>,
}

/// Cache key of a full check: the folder and the manifest's modification time and size.
type CacheKey = (PathBuf, SystemTime, u64);

/// The shared state of the module; `Modules` is a cheap handle to it, so a blocking job can own one.
pub struct ModulesInner {
    /// `<app local data>/modules/cinematic`
    pub root: PathBuf,
    /// The launched Cinematic View, if any. Install, uninstall and launch take this lock first.
    child: Mutex<Option<Child>>,
    /// The last successful full check, so the player does not hash the whole module each time it
    /// is built. A change of the manifest or the folder invalidates it; the launch always checks
    /// every file again.
    checked: Mutex<Option<(CacheKey, Status)>>,
}

#[derive(Clone)]
pub struct Modules(Arc<ModulesInner>);

impl std::ops::Deref for Modules {
    type Target = ModulesInner;
    fn deref(&self) -> &ModulesInner {
        &self.0
    }
}

impl Modules {
    pub fn new(root: PathBuf) -> Self {
        Self(Arc::new(ModulesInner {
            root,
            child: Mutex::new(None),
            checked: Mutex::new(None),
        }))
    }
}

impl ModulesInner {
    /// The module status, hashing the files only when the manifest changed since the last
    /// successful check.
    pub fn status(&self) -> Status {
        // Not while an install or launch holds the lock: a swap in progress looks like a lost module.
        if let Ok(_idle) = self.child.try_lock() {
            recover_aside(&self.root);
        }
        let key = installed_dir(&self.root).and_then(|d| {
            let m = fs::metadata(d.join(MANIFEST)).ok()?;
            Some((d, m.modified().ok()?, m.len()))
        });
        if let (Some(key), Ok(cache)) = (&key, self.checked.lock())
            && let Some((k, s)) = cache.as_ref()
            && k == key
        {
            return s.clone();
        }
        let s = status_of(&self.root);
        if let Ok(mut cache) = self.checked.lock() {
            *cache = match key {
                Some(k) if s.verified => Some((k, s.clone())),
                _ => None,
            };
        }
        s
    }

    /// Removes the module unless the Cinematic View runs. The lock is held through the removal, so
    /// no launch can start on a half-removed module.
    fn uninstall_guarded(&self) -> Result<Status, PlatformError> {
        let mut slot = self.child.lock().map_err(err)?;
        ensure_not_running(
            &mut slot,
            "the Cinematic View is open; close it before uninstalling the module",
        )?;
        self.forget();
        uninstall(&self.root)
    }

    fn forget(&self) {
        if let Ok(mut cache) = self.checked.lock() {
            *cache = None;
        }
    }
}

fn invalid(m: impl Into<String>) -> PlatformError {
    PlatformError::Invalid(m.into())
}

/// One path component Windows can create as written: no device name (`nul`, `con.txt`, `com1`),
/// no trailing dot or space (Windows drops them, so two names would collide), no reserved or
/// control character.
fn plain_component(c: &str) -> bool {
    !c.is_empty()
        && c != "."
        && c != ".."
        && !c.ends_with('.')
        && !c.ends_with(' ')
        && !crate::packages::windows_reserved(c)
        && !c
            .chars()
            .any(|ch| ch.is_control() || "<>\"|?*".contains(ch))
}

/// A relative path of plain components only (no root, no `..`, no drive, no backslash, no
/// Windows device names, no trailing dots or spaces).
fn safe_relative(p: &str) -> bool {
    if p.is_empty() || p.len() > 260 || p.contains('\\') || p.contains(':') {
        return false;
    }
    p.split('/').all(plain_component)
        && Path::new(p)
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
    // Shown in the install dialog: plain version characters only.
    let godot = v
        .pointer("/godot/version")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    if !(1..=32).contains(&godot.len())
        || !godot
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
    {
        return Err(invalid(
            "the module's Godot version is missing or malformed",
        ));
    }
    // Godot's own cache folder: never part of the module (the launch deletes it).
    let cache = format!("{project}/{GODOT_CACHE}").to_lowercase();
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
        let lower = path.to_lowercase();
        if lower == cache || lower.starts_with(&format!("{cache}/")) {
            return Err(invalid(format!(
                "manifest lists {path:?}, inside the Godot cache folder"
            )));
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
        godot,
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

/// A version as numbers, so `0.10.0` sorts after `0.9.0`.
fn version_key(v: &str) -> Option<(u64, u64, u64)> {
    if !version_ok(v) {
        return None;
    }
    let mut parts = v.split('.').map(|p| p.parse::<u64>().ok());
    Some((parts.next()??, parts.next()??, parts.next()??))
}

/// The installed version folders (`<root>/<x.y.z>`), oldest first.
fn version_dirs(root: &Path) -> Vec<(PathBuf, (u64, u64, u64))> {
    let mut found: Vec<_> = fs::read_dir(root)
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.path().is_dir())
        .filter_map(|e| {
            let key = version_key(&e.file_name().to_string_lossy())?;
            Some((e.path(), key))
        })
        .collect();
    found.sort_by_key(|(_, k)| *k);
    found
}

/// The newest installed version folder, if any.
fn installed_dir(root: &Path) -> Option<PathBuf> {
    version_dirs(root).pop().map(|(p, _)| p)
}

/// Fails on any file in the installed tree that the manifest does not list (a DLL beside the
/// executable, an `override.cfg`, a replaced helper), on any link, and on a tree too large to be
/// the module. Only `<project>/.godot/` is exempt; the launch deletes it.
fn check_no_extra_files(dir: &Path, m: &Manifest) -> Result<(), String> {
    let mut listed: BTreeSet<String> = m.files.iter().map(|f| f.path.to_lowercase()).collect();
    listed.insert(MANIFEST.to_lowercase());
    let cache = format!("{}/{GODOT_CACHE}", m.project).to_lowercase();
    let unreadable = |p: &str| format!("{p} cannot be listed");
    let mut stack = vec![(dir.to_path_buf(), String::new())];
    let mut files = 0usize;
    while let Some((d, rel)) = stack.pop() {
        for e in fs::read_dir(&d).map_err(|_| unreadable(&rel))? {
            let e = e.map_err(|_| unreadable(&rel))?;
            let name = e.file_name().to_string_lossy().to_string();
            let path = if rel.is_empty() {
                name
            } else {
                format!("{rel}/{name}")
            };
            let kind = e.file_type().map_err(|_| unreadable(&path))?;
            if kind.is_symlink() {
                return Err(format!("{path} is a link, which a module never holds"));
            }
            if kind.is_dir() {
                if path.to_lowercase() != cache {
                    stack.push((e.path(), path));
                }
                continue;
            }
            files += 1;
            if files > MAX_FILES + 1 {
                return Err("the module folder holds too many files".into());
            }
            if !listed.contains(&path.to_lowercase()) {
                return Err(format!(
                    "{path} is not part of the module (it is not in the manifest)"
                ));
            }
        }
    }
    Ok(())
}

/// Reads and checks the installed module: manifest, every listed file's size and SHA-256, and
/// that nothing else is in the folder.
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
    check_no_extra_files(dir, &m)?;
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
                "The installed module failed its integrity check: {e}. Reinstall or uninstall it."
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

/// What an install would put on the disk, shown to the user before anything is installed.
#[derive(Clone, Debug)]
pub struct Plan {
    /// SHA-256 of the copy of the zip that is being installed.
    pub sha256: String,
    pub version: String,
    pub godot: String,
    pub disk_bytes: u64,
}

fn remove_path(p: &Path) {
    if p.is_dir() {
        let _ = fs::remove_dir_all(p);
    } else {
        let _ = fs::remove_file(p);
    }
}

/// Removes staging folders left by an install that did not finish.
fn clear_staging(root: &Path) {
    for e in fs::read_dir(root).into_iter().flatten().flatten() {
        if e.file_name().to_string_lossy().starts_with(STAGING_PREFIX) {
            remove_path(&e.path());
        }
    }
}

/// Puts back a module that a crash (or a failed put-back) left in `.old-*` when no version is
/// installed, so an interrupted replacement never costs the user the module.
fn recover_aside(root: &Path) {
    if !version_dirs(root).is_empty() {
        return;
    }
    for e in fs::read_dir(root).into_iter().flatten().flatten() {
        if !e.file_name().to_string_lossy().starts_with(OLD_PREFIX) || !e.path().is_dir() {
            continue;
        }
        for v in fs::read_dir(e.path()).into_iter().flatten().flatten() {
            let name = v.file_name();
            if version_key(&name.to_string_lossy()).is_some() && !root.join(&name).exists() {
                let _ = fs::rename(v.path(), root.join(&name));
            }
        }
        let _ = fs::remove_dir(e.path()); // only when nothing is left in it
    }
}

/// Moves the installed versions aside, moves `new_tree` to `<root>/<version>` and deletes the old
/// copies. If anything fails the old versions are put back and the error is returned, so a failed
/// replacement (for instance a running Cinematic View that locks its executable) never leaves the
/// user without a module.
fn swap_in(root: &Path, new_tree: &Path, version: &str) -> Result<(), PlatformError> {
    // Not cleared first: after a failed put-back it may hold the only copy of the old module.
    let aside = root.join(format!("{OLD_PREFIX}{}", std::process::id()));
    let mut moved: Vec<(PathBuf, PathBuf)> = Vec::new();
    let put_back = |moved: &[(PathBuf, PathBuf)]| {
        let lost = moved
            .iter()
            .rev()
            .filter(|(from, to)| fs::rename(to, from).is_err())
            .count();
        if lost == 0 {
            let _ = fs::remove_dir_all(&aside);
            String::new()
        } else {
            format!(
                "; the previous module could not be put back and is in {}",
                display_path(&aside)
            )
        }
    };
    let attempt = (|| -> std::io::Result<()> {
        let olds = version_dirs(root);
        if !olds.is_empty() {
            fs::create_dir_all(&aside)?;
        }
        for (dir, _) in olds {
            let Some(name) = dir.file_name() else {
                continue;
            };
            let to = aside.join(name);
            fs::rename(&dir, &to)?;
            moved.push((dir, to));
        }
        fs::rename(new_tree, root.join(version))
    })();
    if let Err(e) = attempt {
        let note = put_back(&moved);
        return Err(invalid(format!(
            "the module could not be replaced ({e}); the previous module is kept{note}. Close the Cinematic View and try again"
        )));
    }
    // The new version is in place. Leftovers of this or an earlier replacement are now garbage.
    for e in fs::read_dir(root).into_iter().flatten().flatten() {
        if e.file_name().to_string_lossy().starts_with(OLD_PREFIX) {
            remove_path(&e.path());
        }
    }
    Ok(())
}

/// Installs the module zip at `zip_path` under `root`. The zip is copied once into a staging
/// folder and everything (hash, manifest, files) is read from that copy, so the file the user
/// picked cannot change between the check and the install. `confirm` sees the zip's SHA-256 and
/// the module's identity after every check passed and before anything is extracted; returning
/// `false` cancels (`Ok(None)`) and an error stops the install. The confirmation is also where a
/// caller takes the lock that keeps the Cinematic View from running during the swap.
pub fn install_zip(
    root: &Path,
    zip_path: &Path,
    confirm: &dyn Fn(&Plan) -> Result<bool, PlatformError>,
) -> Result<Option<Status>, PlatformError> {
    let side = PathBuf::from(format!("{}.sha256", zip_path.display()));
    let declared = fs::read_to_string(&side)
        .map_err(|_| invalid("the .sha256 file beside the module zip is missing"))?;
    let declared = declared
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_lowercase();
    if declared.len() != 64 || !declared.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(invalid("the .sha256 file does not hold a SHA-256"));
    }
    let zip_len = fs::metadata(zip_path).map_err(err)?.len();
    if zip_len > MAX_ZIP_BYTES {
        return Err(invalid("the module zip is too large"));
    }
    fs::create_dir_all(root).map_err(err)?;
    recover_aside(root);
    clear_staging(root);
    let staging = root.join(format!("{STAGING_PREFIX}{}", std::process::id()));
    let result = stage_and_swap(root, zip_path, zip_len, &declared, &staging, confirm);
    remove_path(&staging);
    result
}

fn stage_and_swap(
    root: &Path,
    zip_path: &Path,
    zip_len: u64,
    declared: &str,
    staging: &Path,
    confirm: &dyn Fn(&Plan) -> Result<bool, PlatformError>,
) -> Result<Option<Status>, PlatformError> {
    let low_disk = |need: u64| -> Result<(), PlatformError> {
        match free_bytes(root) {
            Some(free) if free < need => Err(invalid(format!(
                "not enough free disk space: the install needs {} MB and {} MB are free",
                need / 1_048_576,
                free / 1_048_576
            ))),
            _ => Ok(()),
        }
    };
    low_disk(zip_len + DISK_MARGIN_BYTES)?;
    fs::create_dir_all(staging).map_err(err)?;
    let copy = staging.join("archive.zip");
    fs::copy(zip_path, &copy).map_err(err)?;
    if fs::metadata(&copy).map_err(err)?.len() != zip_len {
        return Err(invalid("the module zip changed while it was being copied"));
    }
    // One handle that denies writers: hashed here, then read as the archive.
    let mut file = open_read_locked(&copy).map_err(err)?;
    let (actual, _) = sha256_reader(&mut file).map_err(err)?;
    if declared != actual {
        return Err(invalid(format!(
            "the module zip (SHA-256 {actual}) does not match its .sha256 file, which states {declared}"
        )));
    }
    file.seek(SeekFrom::Start(0)).map_err(err)?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| invalid(format!("not a zip: {e}")))?;
    if zip.len() > MAX_FILES + 1 {
        return Err(invalid(format!(
            "the zip holds {} entries; a module holds at most {MAX_FILES} files and its manifest",
            zip.len()
        )));
    }
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
    low_disk(m.disk_bytes + DISK_MARGIN_BYTES)?;
    let plan = Plan {
        sha256: actual,
        version: m.version.clone(),
        godot: m.godot.clone(),
        disk_bytes: m.disk_bytes,
    };
    if !confirm(&plan)? {
        return Ok(None);
    }
    // Named after the version so the same integrity check as at launch can run on it.
    let tree = staging.join(&m.version);
    for f in &m.files {
        let mut e = zip
            .by_name(&f.path)
            .map_err(|_| invalid(format!("{} is listed but not in the zip", f.path)))?;
        if e.size() != f.bytes {
            return Err(invalid(format!("{} has the wrong size in the zip", f.path)));
        }
        let dst = tree.join(&f.path);
        if let Some(d) = dst.parent() {
            fs::create_dir_all(d).map_err(err)?;
        }
        let mut out = fs::File::create_new(&dst).map_err(err)?;
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
    fs::write(tree.join(MANIFEST), &manifest_bytes).map_err(err)?;
    // Nothing is replaced unless the new tree passes the check the launch will run.
    verify_installed(&tree).map_err(|e| {
        invalid(format!(
            "the extracted module failed its integrity check: {e}"
        ))
    })?;
    swap_in(root, &tree, &m.version)?;
    Ok(Some(status_of(root)))
}

/// Removes every installed version and any staging folder.
pub fn uninstall(root: &Path) -> Result<Status, PlatformError> {
    if root.exists() {
        fs::remove_dir_all(root).map_err(err)?;
    }
    Ok(status_of(root))
}

/// A checked launch: the executable, the fixed arguments and the hash the executable must still
/// have when it is started.
pub struct Launch {
    pub exe: PathBuf,
    pub args: Vec<String>,
    exe_bytes: u64,
    exe_sha256: String,
}

/// Verifies the installed module and returns the executable and the fixed arguments for a run
/// folder and a pack folder (both resolved by the Studio). Godot's cache folder is deleted so the
/// process starts from the verified files only.
pub fn launch_command(
    root: &Path,
    run_dir: &Path,
    env_dir: &Path,
) -> Result<Launch, PlatformError> {
    let dir =
        installed_dir(root).ok_or_else(|| invalid("the Cinematic View module is not installed"))?;
    let m = verify_installed(&dir).map_err(|e| {
        invalid(format!(
            "the installed module failed its integrity check: {e}"
        ))
    })?;
    let cache = dir.join(&m.project).join(GODOT_CACHE);
    if cache.symlink_metadata().is_ok() {
        fs::remove_dir_all(&cache).map_err(|e| {
            invalid(format!(
                "the module's Godot cache could not be cleared: {e}"
            ))
        })?;
    }
    let exe = dir.join(&m.exe);
    let exe_entry = m
        .files
        .iter()
        .find(|f| f.path == m.exe)
        .ok_or_else(|| invalid("the module executable is not in the file list"))?;
    let mut args = Vec::new();
    // On this Windows machine (RX 7700 XT, driver 32.0.31041) Godot's Vulkan swap chain fails on
    // every frame ("Couldn't get Vulkan surface capabilities", VkResult -13) and the window stays
    // black; Direct3D 12 renders the same scene without an error. Windows therefore uses D3D12.
    if cfg!(windows) {
        args.extend(["--rendering-driver".to_string(), "d3d12".to_string()]);
    }
    args.extend([
        "--path".to_string(),
        dir.join(&m.project).display().to_string(),
        "--".to_string(),
        "--run".to_string(),
        run_dir.display().to_string(),
        "--env".to_string(),
        env_dir.display().to_string(),
        "--profile".to_string(),
        "auto".to_string(),
    ]);
    Ok(Launch {
        exe,
        args,
        exe_bytes: exe_entry.bytes,
        exe_sha256: exe_entry.sha256.clone(),
    })
}

/// Opens a file so that nobody can write to it while the handle is held.
fn open_read_locked(exe: &Path) -> std::io::Result<fs::File> {
    let mut o = fs::OpenOptions::new();
    o.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        o.share_mode(1); // FILE_SHARE_READ: no writers, no deleters
    }
    o.open(exe)
}

/// Hashes the executable once more, through a handle that denies writers, and starts it while that
/// handle is still open.
pub fn spawn_checked(l: &Launch) -> Result<Child, PlatformError> {
    let mut f = open_read_locked(&l.exe).map_err(err)?;
    let (sha, n) = sha256_reader(&mut f).map_err(err)?;
    if n != l.exe_bytes || sha != l.exe_sha256 {
        return Err(invalid(
            "the module executable changed after it was checked; it was not started",
        ));
    }
    let child = Command::new(&l.exe)
        .args(&l.args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(err)?;
    drop(f);
    Ok(child)
}

/// Refuses (with `why`) while the launched Cinematic View is still running.
fn ensure_not_running(slot: &mut Option<Child>, why: &str) -> Result<(), PlatformError> {
    if child_alive(slot) {
        Err(invalid(why))
    } else {
        Ok(())
    }
}

fn child_alive(slot: &mut Option<Child>) -> bool {
    slot.as_mut()
        .is_some_and(|c| matches!(c.try_wait(), Ok(None)))
}

// ---------------------------------------------------------------------------------- commands

#[tauri::command]
pub async fn cinematic_status(state: State<'_, AppState>) -> Result<Status, PlatformError> {
    let modules = state.modules.clone();
    blocking(move || Ok(modules.status())).await
}

#[tauri::command]
pub async fn cinematic_install_from_file(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<Status>, PlatformError> {
    let modules = state.modules.clone();
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
        // The user confirms first, without any lock; then the lock is taken and the Cinematic
        // View is checked again. The guard stays in `held` until the install ends, so no launch
        // can start while the module is being replaced.
        let held = std::cell::RefCell::new(None);
        let ask = |p: &Plan| -> Result<bool, PlatformError> {
            let yes = app
                .dialog()
                .message(format!(
                    "Install Cinematic View {} (Godot {}, {} MB on disk)?\n\nSHA-256 of the zip:\n{}\n\nThe .sha256 file beside the zip matches, so the zip is intact. That does not show who built it: compare the SHA-256 above with a value from a source you trust. Studio then checks every extracted file against the module manifest.",
                    p.version,
                    p.godot,
                    p.disk_bytes / 1_048_576,
                    p.sha256
                ))
                .title("Install the Cinematic View module")
                .kind(MessageDialogKind::Info)
                .buttons(MessageDialogButtons::OkCancelCustom(
                    "Install".into(),
                    "Cancel".into(),
                ))
                .blocking_show();
            if !yes {
                return Ok(false);
            }
            let mut slot = modules.child.lock().map_err(err)?;
            ensure_not_running(
                &mut slot,
                "the Cinematic View is open; close it before installing or replacing the module",
            )?;
            *held.borrow_mut() = Some(slot);
            Ok(true)
        };
        modules.forget();
        let s = install_zip(&modules.root, &zip_path, &ask).inspect_err(|e| {
            log_line(&log, &format!("cinematic module install refused: {e}"));
        })?;
        match &s {
            Some(s) => log_line(&log, &format!("cinematic module installed {:?}", s.version)),
            None => log_line(&log, "cinematic module install cancelled"),
        }
        Ok(s)
    })
    .await
}

#[tauri::command]
pub async fn cinematic_uninstall(state: State<'_, AppState>) -> Result<Status, PlatformError> {
    let modules = state.modules.clone();
    let log = state.paths.log.clone();
    blocking(move || {
        let s = modules.uninstall_guarded()?;
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
    let modules = state.modules.clone();
    blocking(move || {
        // The lock is held from the check to the spawn: an install cannot swap the module between
        // the verification and the start, and a second window cannot be opened meanwhile.
        let mut slot = modules.child.lock().map_err(err)?;
        ensure_not_running(
            &mut slot,
            "the Cinematic View is already open; close it first",
        )?;
        // A refused launch means the cached "files matched" status is out of date.
        let started = launch_command(&modules.root, &run_dir, &env_dir)
            .and_then(|launch| spawn_checked(&launch))
            .inspect_err(|_| modules.forget())?;
        *slot = Some(started);
        Ok(())
    })
    .await?;
    log_line(
        &state.paths.log,
        &format!("cinematic view started for run {run_id} on {env_id}"),
    );
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

    fn install(root: &Path, zp: &Path) -> Result<Status, PlatformError> {
        install_zip(root, zp, &|_| Ok(true)).map(|s| s.expect("not cancelled"))
    }

    /// The module zip of `build_zip` with another version, as `<dir>/<version>.zip`.
    fn build_version(dir: &Path, version: &str, exe: &[u8]) -> PathBuf {
        let sub = dir.join(version);
        fs::create_dir_all(&sub).unwrap();
        let files: Vec<(&str, &[u8])> = vec![
            ("godot/g.exe", exe),
            ("project/project.godot", b"config_version=5\n"),
        ];
        let v = version.to_string();
        build_zip(&sub, &files, None, |m| m["version"] = v.clone().into())
    }

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
        let s = install(&root, &zp).unwrap();
        assert!(s.installed && s.verified, "{s:?}");
        assert_eq!(s.version.as_deref(), Some("0.1.0"));
        // Nothing but the module is left beside it.
        let names: Vec<_> = fs::read_dir(&root)
            .unwrap()
            .flatten()
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        assert_eq!(names, ["0.1.0"]);
        let Launch { exe, args, .. } =
            launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        assert!(exe.ends_with("0.1.0/godot/g.exe") || exe.ends_with("0.1.0\\godot\\g.exe"));
        let at = args.iter().position(|a| a == "--path").unwrap();
        assert_eq!(
            args[at + 2..],
            ["--", "--run", "R", "--env", "E", "--profile", "auto"]
        );
        // Windows uses Direct3D 12 (see launch_command).
        assert_eq!(cfg!(windows), args[..at] == ["--rendering-driver", "d3d12"]);
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
            (
                "reserved",
                Box::new(|d| {
                    build_zip(d, &[FILES[0], FILES[1], ("godot/nul", b"x")], None, |_| {})
                }),
            ),
            (
                "reserved-extension",
                Box::new(|d| {
                    build_zip(
                        d,
                        &[FILES[0], FILES[1], ("project/con.txt", b"x")],
                        None,
                        |_| {},
                    )
                }),
            ),
            (
                "godot-cache-entry",
                Box::new(|d| {
                    build_zip(
                        d,
                        &[FILES[0], FILES[1], ("project/.godot/cache.cfg", b"x")],
                        None,
                        |_| {},
                    )
                }),
            ),
            (
                "godot-version-markup",
                Box::new(|d| {
                    build_zip(d, FILES, None, |m| {
                        m["godot"]["version"] = "4.7 <b>x</b>".into()
                    })
                }),
            ),
            (
                "godot-version-missing",
                Box::new(|d| build_zip(d, FILES, None, |m| m["godot"]["version"] = "".into())),
            ),
            (
                "trailing-dot",
                Box::new(|d| {
                    build_zip(d, &[FILES[0], FILES[1], ("project/a.", b"x")], None, |_| {})
                }),
            ),
        ];
        for (name, make) in cases {
            let d = tmp(name);
            let zp = make(&d);
            let root = d.join("modules").join("cinematic");
            assert!(install(&root, &zp).is_err(), "{name} was accepted");
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
        let s = install(&root, &zp).unwrap();
        assert!(s.installed && s.verified, "{s:?}");
        let Launch { exe, args, .. } =
            launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        assert!(exe.is_file());
        let at = args.iter().position(|a| a == "--path").unwrap();
        assert!(Path::new(&args[at + 1]).join("project.godot").is_file());
        assert!(!uninstall(&root).unwrap().installed);
        let _ = fs::remove_dir_all(&d);
        // Opt-in for acceptance runs: install the same zip, through the same code, into a real
        // Studio module folder (VV_CINEMATIC_INSTALL_TO, e.g. <app local data>/modules/cinematic)
        // and keep it, so the installed Studio can be driven without its native file dialog.
        if let Some(real) = std::env::var_os("VV_CINEMATIC_INSTALL_TO").map(PathBuf::from) {
            let s = install(&real, &zp).unwrap();
            assert!(s.installed && s.verified, "{s:?}");
        }
    }

    #[test]
    fn a_file_the_manifest_does_not_list_fails_the_check() {
        let d = tmp("extra");
        let zp = build_zip(&d, FILES, None, |_| {});
        let root = d.join("modules").join("cinematic");
        install(&root, &zp).unwrap();
        let v = root.join("0.1.0");
        assert!(verify_installed(&v).is_ok());
        for (rel, why) in [
            ("godot/override.cfg", "beside the executable"),
            ("godot/evil.dll", "a library beside the executable"),
            ("project/reg.exe", "a helper in the project"),
            ("new/deep/file.txt", "a new folder"),
            ("project/.godot2/x", "only .godot itself is exempt"),
            (".godot/cache", ".godot outside the project is not exempt"),
        ] {
            let p = v.join(rel);
            fs::create_dir_all(p.parent().unwrap()).unwrap();
            fs::write(&p, b"x").unwrap();
            let e = verify_installed(&v).unwrap_err();
            assert!(e.contains("not part of the module"), "{why}: {e}");
            assert!(!status_of(&root).verified, "{why}");
            fs::remove_file(&p).ok();
            // Removing the file again restores a clean tree (empty folders are harmless).
            assert!(verify_installed(&v).is_ok(), "{why}: still failing");
        }
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn godot_cache_is_tolerated_by_the_check_and_deleted_before_launch() {
        let d = tmp("cache");
        let zp = build_zip(&d, FILES, None, |_| {});
        let root = d.join("modules").join("cinematic");
        install(&root, &zp).unwrap();
        let cache = root.join("0.1.0").join("project").join(".godot");
        fs::create_dir_all(cache.join("imported")).unwrap();
        fs::write(cache.join("extension_list.cfg"), b"res://evil.gdextension").unwrap();
        assert!(
            status_of(&root).verified,
            "the cache is exempt from the check"
        );
        launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        assert!(!cache.exists(), "the launch deletes the cache");
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn versions_sort_numerically() {
        let d = tmp("order");
        for v in ["0.9.0", "0.10.0", "0.2.11", "1.0.0-x", ".staging-1"] {
            fs::create_dir_all(d.join(v)).unwrap();
        }
        assert_eq!(installed_dir(&d).unwrap().file_name().unwrap(), "0.10.0");
        assert_eq!(version_key("0.10.0"), Some((0, 10, 0)));
        assert_eq!(version_key("1.0.0-x"), None);
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn replacing_installs_the_new_version_and_leaves_no_leftovers() {
        let d = tmp("replace");
        let root = d.join("modules").join("cinematic");
        install(&root, &build_version(&d, "0.1.0", b"MZ one")).unwrap();
        // Stale staging folders of an interrupted install are removed at the start of the next one.
        fs::create_dir_all(root.join(".staging-99999")).unwrap();
        fs::write(root.join(".staging-99999.zip"), b"x").unwrap();
        let s = install(&root, &build_version(&d, "0.2.0", b"MZ two")).unwrap();
        assert_eq!(s.version.as_deref(), Some("0.2.0"));
        assert!(s.verified, "{s:?}");
        let mut names: Vec<_> = fs::read_dir(&root)
            .unwrap()
            .flatten()
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        names.sort();
        assert_eq!(names, ["0.2.0"]);
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn a_failed_swap_keeps_the_installed_module() {
        let d = tmp("swap");
        let root = d.join("modules").join("cinematic");
        install(&root, &build_version(&d, "0.1.0", b"MZ one")).unwrap();
        // The new tree does not exist, so the final rename fails after the old one was moved aside.
        let e = swap_in(&root, &d.join("missing"), "0.2.0").unwrap_err();
        assert!(e.to_string().contains("previous module is kept"), "{e}");
        let s = status_of(&root);
        assert!(s.verified, "{s:?}");
        assert_eq!(s.version.as_deref(), Some("0.1.0"));
        assert!(!root.join("0.2.0").exists());
        assert!(
            fs::read_dir(&root)
                .unwrap()
                .flatten()
                .all(|e| !e.file_name().to_string_lossy().starts_with(OLD_PREFIX)),
            "the aside folder is gone once the old module is back"
        );
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn cancelling_installs_nothing_and_the_plan_carries_the_zip_hash() {
        let d = tmp("cancel");
        let zp = build_zip(&d, FILES, None, |_| {});
        let root = d.join("modules").join("cinematic");
        let want = sha256_file(&zp).unwrap().0;
        let seen = std::cell::RefCell::new(None);
        let r = install_zip(&root, &zp, &|p| {
            *seen.borrow_mut() = Some(p.clone());
            Ok(false)
        })
        .unwrap();
        assert!(r.is_none());
        let p = seen.borrow().clone().unwrap();
        assert_eq!(p.sha256, want);
        assert_eq!((p.version.as_str(), p.disk_bytes), ("0.1.0", 24));
        assert!(installed_dir(&root).is_none());
        assert_eq!(
            fs::read_dir(&root).unwrap().count(),
            0,
            "staging is removed"
        );
        // A sidecar mismatch names the computed hash.
        fs::write(d.join("m.zip.sha256"), "1".repeat(64)).unwrap();
        let e = install(&root, &zp).unwrap_err().to_string();
        assert!(e.contains(&want), "{e}");
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn a_zip_with_too_many_entries_is_refused_before_it_is_read() {
        let d = tmp("many");
        let zp = d.join("m.zip");
        let mut z = zip::ZipWriter::new(fs::File::create(&zp).unwrap());
        let o = zip::write::SimpleFileOptions::default();
        for i in 0..MAX_FILES + 2 {
            z.start_file(format!("f{i}"), o).unwrap();
        }
        z.finish().unwrap();
        let (sha, _) = sha256_file(&zp).unwrap();
        fs::write(d.join("m.zip.sha256"), sha).unwrap();
        let e = install(&d.join("modules"), &zp).unwrap_err().to_string();
        assert!(e.contains("entries"), "{e}");
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn the_status_is_cached_until_the_manifest_changes_and_the_launch_still_checks() {
        let d = tmp("cached");
        let zp = build_zip(&d, FILES, None, |_| {});
        let root = d.join("modules").join("cinematic");
        let m = Modules::new(root.clone());
        install(&root, &zp).unwrap();
        assert!(m.status().verified);
        // Same size, so only hashing can tell: the cached status does not rehash...
        fs::write(root.join("0.1.0").join("godot").join("g.exe"), b"MZ evil").unwrap();
        assert!(m.status().verified, "served from the cache");
        // ...but the launch always does.
        assert!(launch_command(&root, Path::new("R"), Path::new("E")).is_err());
        m.forget();
        assert!(!m.status().verified);
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn an_executable_changed_after_the_check_is_not_started() {
        let d = tmp("toctou");
        let zp = build_zip(&d, FILES, None, |_| {});
        let root = d.join("modules").join("cinematic");
        install(&root, &zp).unwrap();
        let l = launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        fs::write(&l.exe, b"MZ evil").unwrap();
        let e = spawn_checked(&l).expect_err("refused").to_string();
        assert!(e.contains("changed after it was checked"), "{e}");
        let _ = fs::remove_dir_all(&d);
    }

    /// The handle that denies writers must not stop the process from starting: the module here is
    /// a copy of this test program, which exits at once on the module's arguments.
    #[cfg(windows)]
    #[test]
    fn the_locked_executable_still_starts() {
        let d = tmp("spawn");
        let bytes = fs::read(std::env::current_exe().unwrap()).unwrap();
        let zp = build_zip(
            &d,
            &[
                ("godot/g.exe", &bytes),
                ("project/project.godot", b"config_version=5\n"),
            ],
            None,
            |_| {},
        );
        let root = d.join("modules").join("cinematic");
        install(&root, &zp).unwrap();
        let l = launch_command(&root, Path::new("R"), Path::new("E")).unwrap();
        let mut child = spawn_checked(&l).unwrap();
        let _ = child.wait();
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn a_bad_replacement_leaves_the_installed_module_alone() {
        let d = tmp("badrepl");
        let root = d.join("modules").join("cinematic");
        install(&root, &build_version(&d, "0.1.0", b"MZ one")).unwrap();
        let sub = d.join("0.2.0");
        fs::create_dir_all(&sub).unwrap();
        let bad = build_zip(
            &sub,
            &[FILES[0], FILES[1], ("godot/nul", b"x")],
            None,
            |m| m["version"] = "0.2.0".into(),
        );
        assert!(install(&root, &bad).is_err());
        let s = status_of(&root);
        assert!(s.verified, "{s:?}");
        assert_eq!(s.version.as_deref(), Some("0.1.0"));
        assert_eq!(fs::read_dir(&root).unwrap().count(), 1, "no leftovers");
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn a_failed_swap_puts_every_version_back() {
        let d = tmp("several");
        for v in ["0.1.0", "0.2.0", "0.10.0"] {
            fs::create_dir_all(d.join(v)).unwrap();
            fs::write(d.join(v).join("marker"), v).unwrap();
        }
        let e = swap_in(&d, &d.join("missing"), "0.11.0").unwrap_err();
        assert!(e.to_string().contains("previous module is kept"), "{e}");
        for v in ["0.1.0", "0.2.0", "0.10.0"] {
            assert_eq!(fs::read_to_string(d.join(v).join("marker")).unwrap(), v);
        }
        assert!(
            fs::read_dir(&d)
                .unwrap()
                .flatten()
                .all(|e| !e.file_name().to_string_lossy().starts_with(OLD_PREFIX))
        );
        let _ = fs::remove_dir_all(&d);
    }

    /// A file held open without delete sharing (a running executable does the same) makes the
    /// rename of its folder fail: the install must fail and keep the module.
    #[cfg(windows)]
    #[test]
    fn a_locked_old_version_fails_the_replacement_and_keeps_the_module() {
        use std::os::windows::fs::OpenOptionsExt;
        let d = tmp("locked");
        let root = d.join("modules").join("cinematic");
        install(&root, &build_version(&d, "0.1.0", b"MZ one")).unwrap();
        let held = fs::OpenOptions::new()
            .read(true)
            .share_mode(1)
            .open(root.join("0.1.0").join("godot").join("g.exe"))
            .unwrap();
        let e = install(&root, &build_version(&d, "0.2.0", b"MZ two")).unwrap_err();
        assert!(e.to_string().contains("previous module is kept"), "{e}");
        drop(held);
        let s = status_of(&root);
        assert!(s.verified && s.version.as_deref() == Some("0.1.0"), "{s:?}");
        assert_eq!(
            fs::read_dir(&root)
                .unwrap()
                .flatten()
                .filter(|e| e.file_name().to_string_lossy().starts_with('.'))
                .count(),
            0,
            "no staging or aside folder is left"
        );
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn a_module_left_aside_by_an_interrupted_replacement_is_recovered() {
        let d = tmp("recover");
        let root = d.join("modules").join("cinematic");
        let m = Modules::new(root.clone());
        install(&root, &build_version(&d, "0.1.0", b"MZ one")).unwrap();
        let aside = root.join(".old-4242");
        fs::create_dir_all(&aside).unwrap();
        fs::rename(root.join("0.1.0"), aside.join("0.1.0")).unwrap();
        assert!(installed_dir(&root).is_none());
        let s = m.status();
        assert!(s.verified, "{s:?}");
        assert!(!aside.exists());
        // With a module installed, an aside folder is garbage and is not moved back over it.
        fs::create_dir_all(root.join(".old-1").join("0.0.1")).unwrap();
        recover_aside(&root);
        assert!(!root.join("0.0.1").exists());
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn uninstall_is_refused_while_the_view_runs() {
        let d = tmp("uninst");
        let root = d.join("modules").join("cinematic");
        let m = Modules::new(root.clone());
        install(&root, &build_version(&d, "0.1.0", b"MZ one")).unwrap();
        *m.child.lock().unwrap() = Some(sleeper());
        let e = m.uninstall_guarded().unwrap_err().to_string();
        assert!(e.contains("close it before uninstalling"), "{e}");
        assert!(status_of(&root).verified, "the module is untouched");
        let mut c = m.child.lock().unwrap().take().unwrap();
        c.kill().unwrap();
        let _ = c.wait();
        *m.child.lock().unwrap() = Some(c);
        assert!(!m.uninstall_guarded().unwrap().installed);
        let _ = fs::remove_dir_all(&d);
    }

    fn sleeper() -> Child {
        #[cfg(windows)]
        let mut c = Command::new("ping");
        #[cfg(windows)]
        c.args(["-n", "30", "127.0.0.1"]);
        #[cfg(not(windows))]
        let mut c = Command::new("sleep");
        #[cfg(not(windows))]
        c.arg("30");
        c.stdout(Stdio::null()).spawn().unwrap()
    }

    #[test]
    fn install_and_launch_are_refused_while_the_view_runs() {
        let mut slot = None;
        assert!(
            ensure_not_running(&mut slot, "busy").is_ok(),
            "nothing launched"
        );
        slot = Some(sleeper());
        let e = ensure_not_running(&mut slot, "busy").unwrap_err();
        assert!(e.to_string().contains("busy"));
        let mut c = slot.take().unwrap();
        c.kill().unwrap();
        let _ = c.wait();
        let mut exited = Some(c);
        assert!(
            ensure_not_running(&mut exited, "busy").is_ok(),
            "a closed view does not block"
        );
    }

    #[test]
    fn paths_must_be_plain_relative() {
        for bad in [
            "",
            "../a",
            "/a",
            "C:/a",
            "a\\b",
            "a/../b",
            "nul",
            "godot/NUL",
            "con.txt",
            "a/com1.dat",
            "lpt9",
            "godot/nul .txt",
            "x/com\u{b9}",
            "x/CONIN$",
            "aux.tar.gz",
            "a.",
            "dir./x",
            "a /b",
            "a/./b",
            "a//b",
            "a<b",
            "x?",
            "p/q*",
        ] {
            assert!(!safe_relative(bad), "{bad}");
        }
        assert!(safe_relative("project/scripts/main.gd"));
        assert!(safe_relative("godot/Godot_v4.7.2-stable_win64.exe"));
        assert!(safe_relative("LICENSES/godot-LICENSE.txt"));
        assert!(safe_relative("com10.txt") && safe_relative("console/x"));
    }
}
