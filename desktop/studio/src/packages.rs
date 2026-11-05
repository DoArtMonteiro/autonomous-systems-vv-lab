//! Environment packages (M17): a pack shipped as one `.vvenv.zip` archive, built by
//! `scripts/geo/package_environment.py`. The archive holds `environment.json` and the files it
//! names at its root and nothing else. Installing one never touches the network: the user picks
//! a local file, the Studio checks the archive against the SHA-256 in the sidecar `.sha256` file
//! when there is one, refuses entries that are not plain file names, checks the uncompressed size
//! against a cap and the free disk space, extracts into a staging folder and lets `vv-geo`
//! validate the result (every file against the hash in the manifest) before the pack appears.
//! An interrupted or refused install leaves no pack behind.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use serde_json::Value;
use sha2::{Digest, Sha256};
use tauri::State;
use tauri_plugin_dialog::DialogExt;
use vv_geo::environment::Environment;
use vv_platform::PlatformError;

use crate::geo::{geo_err, listing};
use crate::{AppState, blocking, err, log_line};

/// Largest uncompressed package the Studio installs (a pack is tens of MB; this leaves room).
pub const MAX_UNPACKED_BYTES: u64 = 2 * 1024 * 1024 * 1024;
/// Most entries an archive may hold.
const MAX_ENTRIES: usize = 64;
/// Free space kept on the disk after an install.
const DISK_RESERVE_BYTES: u64 = 1024 * 1024 * 1024;

fn sha256_file(path: &Path) -> Result<String, PlatformError> {
    let mut f = fs::File::open(path).map_err(err)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = f.read(&mut buf).map_err(err)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(h.finalize().iter().map(|b| format!("{b:02x}")).collect())
}

/// The hash a sidecar file states: the first word of `<archive>.sha256`, if the file exists.
fn sidecar_hash(archive: &Path) -> Result<Option<String>, PlatformError> {
    let mut side = archive.as_os_str().to_owned();
    side.push(".sha256");
    let side = PathBuf::from(side);
    if !side.exists() {
        return Ok(None);
    }
    let text = fs::read_to_string(&side).map_err(err)?;
    let word = text
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    if word.len() != 64 || !word.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(PlatformError::Invalid(format!(
            "{} does not hold a SHA-256",
            side.display()
        )));
    }
    Ok(Some(word))
}

/// A plain file name: no directory part, no parent reference, no drive or stream syntax.
fn plain_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name != "."
        && name != ".."
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_' || b == b'.')
}

#[cfg(windows)]
fn free_bytes(dir: &Path) -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;
    let wide: Vec<u16> = dir
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    let mut free = 0u64;
    // SAFETY: `wide` is a NUL-terminated UTF-16 path that outlives the call; the out pointers are
    // valid or null as the API allows.
    let ok = unsafe {
        GetDiskFreeSpaceExW(
            wide.as_ptr(),
            &mut free,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    (ok != 0).then_some(free)
}

#[cfg(not(windows))]
fn free_bytes(_dir: &Path) -> Option<u64> {
    None
}

/// What an archive would install, checked before anything is written.
#[derive(Debug)]
pub struct Plan {
    pub sha256: String,
    pub unpacked_bytes: u64,
    pub names: Vec<String>,
}

/// Checks an archive without extracting it: hash against the sidecar, entry names, entry count
/// and total size.
pub fn inspect(archive: &Path) -> Result<Plan, PlatformError> {
    let sha256 = sha256_file(archive)?;
    if let Some(want) = sidecar_hash(archive)? {
        if want != sha256 {
            return Err(PlatformError::Invalid(format!(
                "the archive's SHA-256 {sha256} differs from the {want} its .sha256 file states; it may be incomplete or altered"
            )));
        }
    }
    let f = fs::File::open(archive).map_err(err)?;
    let mut zip = zip::ZipArchive::new(f)
        .map_err(|e| PlatformError::Invalid(format!("not a readable zip archive: {e}")))?;
    if zip.len() > MAX_ENTRIES {
        return Err(PlatformError::Invalid(format!(
            "the archive holds {} entries; a package holds at most {MAX_ENTRIES}",
            zip.len()
        )));
    }
    let mut names = Vec::new();
    let mut total = 0u64;
    for i in 0..zip.len() {
        let e = zip
            .by_index(i)
            .map_err(|e| PlatformError::Invalid(format!("entry {i}: {e}")))?;
        let name = e.name().to_string();
        if e.is_dir() || !plain_name(&name) {
            return Err(PlatformError::Invalid(format!(
                "the archive entry {name:?} is not a plain file name at the root; a package holds environment.json and its files only"
            )));
        }
        if names.contains(&name) {
            return Err(PlatformError::Invalid(format!(
                "the archive holds {name} twice"
            )));
        }
        total = total.saturating_add(e.size());
        names.push(name);
    }
    if !names.iter().any(|n| n == "environment.json") {
        return Err(PlatformError::Invalid(
            "the archive has no environment.json at its root".into(),
        ));
    }
    if total > MAX_UNPACKED_BYTES {
        return Err(PlatformError::Invalid(format!(
            "the archive unpacks to {total} bytes, above the {MAX_UNPACKED_BYTES} a package may hold"
        )));
    }
    Ok(Plan {
        sha256,
        unpacked_bytes: total,
        names,
    })
}

/// Extracts a checked archive into `staging` (created empty), refusing any entry that unpacks to
/// more bytes than it declared.
fn extract(archive: &Path, plan: &Plan, staging: &Path) -> Result<(), PlatformError> {
    fs::create_dir_all(staging).map_err(err)?;
    let f = fs::File::open(archive).map_err(err)?;
    let mut zip = zip::ZipArchive::new(f).map_err(|e| PlatformError::Invalid(e.to_string()))?;
    for name in &plan.names {
        let mut e = zip
            .by_name(name)
            .map_err(|e| PlatformError::Invalid(format!("{name}: {e}")))?;
        let declared = e.size();
        let mut out = fs::File::create(staging.join(name)).map_err(err)?;
        let copied = std::io::copy(&mut (&mut e).take(declared + 1), &mut out).map_err(err)?;
        if copied != declared {
            return Err(PlatformError::Invalid(format!(
                "{name} unpacks to {copied} bytes, not the {declared} it declares"
            )));
        }
    }
    Ok(())
}

/// The `id` of the archive's environment.json, which must be a plain name.
fn manifest_id(archive: &Path) -> Result<String, PlatformError> {
    let f = fs::File::open(archive).map_err(err)?;
    let mut zip = zip::ZipArchive::new(f).map_err(|e| PlatformError::Invalid(e.to_string()))?;
    let e = zip
        .by_name("environment.json")
        .map_err(|e| PlatformError::Invalid(format!("environment.json: {e}")))?;
    let mut text = String::new();
    e.take(4 * 1024 * 1024)
        .read_to_string(&mut text)
        .map_err(err)?;
    let v: Value = serde_json::from_str(&text)
        .map_err(|e| PlatformError::Invalid(format!("environment.json: {e}")))?;
    let id = v["id"].as_str().unwrap_or("").to_string();
    if !plain_name(&id) || id.starts_with('.') {
        return Err(PlatformError::Invalid(format!(
            "environment.json has no usable id ({id:?})"
        )));
    }
    Ok(id)
}

/// Installs a checked archive into `library` (the imported-packs folder). Returns the pack id.
pub fn install(
    archive: &Path,
    library: &Path,
    exists: impl Fn(&str) -> bool,
) -> Result<String, PlatformError> {
    let plan = inspect(archive)?;
    fs::create_dir_all(library).map_err(err)?;
    if let Some(free) = free_bytes(library) {
        if free < plan.unpacked_bytes.saturating_add(DISK_RESERVE_BYTES) {
            return Err(PlatformError::Invalid(format!(
                "the disk has {free} bytes free; the package needs {} plus a 1 GiB reserve",
                plan.unpacked_bytes
            )));
        }
    }
    // vv-geo wants the folder named after the pack id, so the id is read first and the pack is
    // staged as `<library>/.package-<hash>/<id>`.
    let id = manifest_id(archive)?;
    let root = library.join(format!(".package-{}", &plan.sha256[..16]));
    let _ = fs::remove_dir_all(&root);
    let staging = root.join(&id);
    let staged = extract(archive, &plan, &staging)
        .and_then(|()| Environment::open(&staging).map_err(geo_err));
    let env = match staged {
        Ok(env) => env,
        Err(e) => {
            let _ = fs::remove_dir_all(&root);
            return Err(e);
        }
    };
    // Every file of the archive must be a file the manifest names: nothing unvalidated stays.
    let named: Vec<&str> = env.files();
    if let Some(extra) = plan.names.iter().find(|n| !named.contains(&n.as_str())) {
        let _ = fs::remove_dir_all(&root);
        return Err(PlatformError::Invalid(format!(
            "the archive holds {extra}, which environment.json does not name"
        )));
    }
    drop(env);
    if exists(&id) || library.join(&id).exists() {
        let _ = fs::remove_dir_all(&root);
        return Err(PlatformError::Invalid(format!(
            "an environment with the id {id:?} is already installed; remove it first"
        )));
    }
    let dst = library.join(&id);
    let moved = fs::rename(&staging, &dst);
    let _ = fs::remove_dir_all(&root);
    if let Err(e) = moved {
        return Err(err(e));
    }
    // The pack is validated again where it now lives.
    if let Err(e) = Environment::open(&dst) {
        let _ = fs::remove_dir_all(&dst);
        return Err(geo_err(e));
    }
    Ok(id)
}

/// Asks for a `.vvenv.zip` package and installs it. Returns the new listing, or `None` when the
/// dialog was cancelled.
#[tauri::command]
pub async fn import_environment_package(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<Value>, PlatformError> {
    let geo = state.geo.clone();
    let log = state.paths.log.clone();
    blocking(move || {
        let picked = app
            .dialog()
            .file()
            .set_title("Choose an environment package (.vvenv.zip)")
            .add_filter("Environment package", &["zip"])
            .blocking_pick_file();
        let Some(src) = picked.and_then(|f| f.into_path().ok()) else {
            return Ok(None);
        };
        let id = install(&src, &geo.paths.imported, |id| geo.get(id).is_ok())?;
        log_line(
            &log,
            &format!("environment package installed {id} from {}", src.display()),
        );
        Ok(Some(listing(&geo, true)))
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn temp(label: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("vv-pkg-{}-{label}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn pack_dir() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../environments/santa-maria-azores")
    }

    fn zip_of(dir: &Path, names: &[&str], out: &Path, extra: &[(&str, &[u8])]) {
        let f = fs::File::create(out).unwrap();
        let mut z = zip::ZipWriter::new(f);
        let opt: zip::write::SimpleFileOptions = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);
        for n in names {
            z.start_file(*n, opt).unwrap();
            z.write_all(&fs::read(dir.join(n)).unwrap()).unwrap();
        }
        for (n, b) in extra {
            z.start_file(*n, opt).unwrap();
            z.write_all(b).unwrap();
        }
        z.finish().unwrap();
    }

    fn files_of(dir: &Path) -> Vec<String> {
        let env = Environment::open(dir).unwrap();
        env.files().iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn a_package_installs_validates_and_refuses_a_second_copy() {
        let dir = pack_dir();
        let names = files_of(&dir);
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        let t = temp("ok");
        let archive = t.join("pack.vvenv.zip");
        zip_of(&dir, &refs, &archive, &[]);
        let lib = t.join("lib");
        let id = install(&archive, &lib, |_| false).unwrap();
        assert_eq!(id, "santa-maria-azores");
        assert!(Environment::open(&lib.join(&id)).is_ok());
        assert!(
            install(&archive, &lib, |_| false)
                .unwrap_err()
                .to_string()
                .contains("already installed")
        );
        // No staging folder is left behind.
        assert_eq!(fs::read_dir(&lib).unwrap().count(), 1);
    }

    #[test]
    fn a_wrong_sidecar_hash_a_path_entry_an_extra_file_or_a_flipped_byte_is_refused() {
        let dir = pack_dir();
        let names = files_of(&dir);
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        let t = temp("bad");
        let lib = t.join("lib");

        let a = t.join("a.vvenv.zip");
        zip_of(&dir, &refs, &a, &[]);
        fs::write(
            t.join("a.vvenv.zip.sha256"),
            format!("{}  a.vvenv.zip\n", "0".repeat(64)),
        )
        .unwrap();
        assert!(
            install(&a, &lib, |_| false)
                .unwrap_err()
                .to_string()
                .contains("differs")
        );

        let b = t.join("b.vvenv.zip");
        zip_of(&dir, &refs, &b, &[("../evil.txt", b"x")]);
        assert!(
            install(&b, &lib, |_| false)
                .unwrap_err()
                .to_string()
                .contains("plain file name")
        );

        let c = t.join("c.vvenv.zip");
        zip_of(&dir, &refs, &c, &[("notes.txt", b"x")]);
        assert!(
            install(&c, &lib, |_| false)
                .unwrap_err()
                .to_string()
                .contains("does not name")
        );

        // A pack whose file no longer matches its manifest hash is refused by vv-geo.
        let src = t.join("src");
        fs::create_dir_all(&src).unwrap();
        for n in &names {
            fs::copy(dir.join(n), src.join(n)).unwrap();
        }
        let img = src.join("image.jpg");
        let mut bytes = fs::read(&img).unwrap();
        bytes[1000] ^= 1;
        fs::write(&img, bytes).unwrap();
        let d = t.join("d.vvenv.zip");
        zip_of(&src, &refs, &d, &[]);
        assert!(install(&d, &lib, |_| false).is_err());
        assert!(!lib.exists() || fs::read_dir(&lib).unwrap().count() == 0);
    }
}
