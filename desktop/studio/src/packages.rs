//! Environment packages (M17): a pack shipped as one `.vvenv.zip` archive, built by
//! `scripts/geo/package_environment.py`. The archive holds `environment.json` and the files it
//! names at its root and nothing else. Installing one never touches the network: the user picks
//! a local file and the Studio copies it once into a staging folder; everything after that (the
//! SHA-256, the entry list, the manifest, the extraction) reads that copy, so the file the user
//! picked cannot change between the check and the install.
//!
//! What the checks prove. The Studio computes the archive's SHA-256 and shows it to the user
//! before installing. When a sidecar `.sha256` file sits beside the archive, the hash must match
//! it: that shows the archive is intact, not who made it (whoever can replace the archive can
//! replace the sidecar). Without a sidecar nothing is compared and the dialog says so. Either way
//! the hash is for the user to compare with a value from a source they trust. Entries that are
//! not plain file names, an entry count and an uncompressed size cap, and the free disk space are
//! checked; the archive is extracted to a staging folder and `vv-geo` validates the result (every
//! file against the hash in the pack's own manifest) before the pack appears. An interrupted or
//! refused install leaves no pack behind.

use std::fs;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use serde_json::Value;
use sha2::{Digest, Sha256};
use tauri::State;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use vv_geo::environment::Environment;
use vv_platform::PlatformError;

use crate::geo::{geo_err, listing};
use crate::{AppState, blocking, err, log_line};

/// Largest uncompressed package the Studio installs (a pack is tens of MB; this leaves room).
pub const MAX_UNPACKED_BYTES: u64 = 2 * 1024 * 1024 * 1024;
/// Most entries an archive may hold.
const MAX_ENTRIES: usize = 64;
/// The licence notice a package may carry besides the files its manifest names.
pub const NOTICE: &str = "NOTICE.md";
/// Free space kept on the disk after an install.
const DISK_RESERVE_BYTES: u64 = 1024 * 1024 * 1024;
/// Prefix of the folder under the library where an install is staged.
const STAGING_PREFIX: &str = ".package-";

fn sha256_reader(mut f: impl Read) -> Result<String, PlatformError> {
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

/// Names Windows treats as devices, with or without an extension (`nul.json` is the null device).
fn windows_reserved(name: &str) -> bool {
    let stem = name.split('.').next().unwrap_or("").to_ascii_lowercase();
    matches!(stem.as_str(), "con" | "prn" | "aux" | "nul")
        || ["com", "lpt"].iter().any(|p| {
            stem.strip_prefix(p)
                .is_some_and(|n| matches!(n.as_bytes(), [b'0'..=b'9']))
        })
}

/// A plain file name: no directory part, no parent reference, no drive or stream syntax, no
/// Windows device name and no trailing dot (Windows drops it, so two names would collide).
fn plain_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name != "."
        && name != ".."
        && !name.ends_with('.')
        && !windows_reserved(name)
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
    /// SHA-256 of the copy of the archive that is being installed.
    pub sha256: String,
    /// Whether a `.sha256` file beside the archive stated this hash. `false` means there was none.
    pub sidecar_matched: bool,
    pub unpacked_bytes: u64,
    pub names: Vec<String>,
}

type Archive = zip::ZipArchive<fs::File>;

/// Checks an archive without extracting it: entry names, entry count and total size.
fn inspect(
    zip: &mut Archive,
    sha256: String,
    sidecar_matched: bool,
) -> Result<Plan, PlatformError> {
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
        sidecar_matched,
        unpacked_bytes: total,
        names,
    })
}

/// Extracts a checked archive into `staging` (created empty), refusing any entry that unpacks to
/// more bytes than it declared.
fn extract(zip: &mut Archive, plan: &Plan, staging: &Path) -> Result<(), PlatformError> {
    fs::create_dir_all(staging).map_err(err)?;
    for name in &plan.names {
        let mut e = zip
            .by_name(name)
            .map_err(|e| PlatformError::Invalid(format!("{name}: {e}")))?;
        let declared = e.size();
        let mut out = fs::File::create_new(staging.join(name)).map_err(err)?;
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
fn manifest_id(zip: &mut Archive) -> Result<String, PlatformError> {
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

/// Installs a checked archive into `library` (the imported-packs folder). `confirm` sees the
/// archive's SHA-256 and the pack id after the archive passed every check and before anything is
/// extracted; returning `false` cancels (`Ok(None)`). Returns the pack id.
pub fn install(
    archive: &Path,
    library: &Path,
    exists: impl Fn(&str) -> bool,
    confirm: &dyn Fn(&Plan, &str) -> bool,
) -> Result<Option<String>, PlatformError> {
    let sidecar = sidecar_hash(archive)?;
    let len = fs::metadata(archive).map_err(err)?.len();
    if len > MAX_UNPACKED_BYTES {
        return Err(PlatformError::Invalid(format!(
            "the archive is {len} bytes, above the {MAX_UNPACKED_BYTES} a package may hold"
        )));
    }
    fs::create_dir_all(library).map_err(err)?;
    // A staging folder of an earlier run of this program that did not finish.
    for e in fs::read_dir(library).into_iter().flatten().flatten() {
        if e.file_name().to_string_lossy().starts_with(STAGING_PREFIX) {
            let _ = fs::remove_dir_all(e.path());
        }
    }
    let root = library.join(format!("{STAGING_PREFIX}{}", std::process::id()));
    let result = stage_and_move(archive, sidecar, len, library, &root, &exists, confirm);
    let _ = fs::remove_dir_all(&root);
    result
}

fn stage_and_move(
    archive: &Path,
    sidecar: Option<String>,
    len: u64,
    library: &Path,
    root: &Path,
    exists: &dyn Fn(&str) -> bool,
    confirm: &dyn Fn(&Plan, &str) -> bool,
) -> Result<Option<String>, PlatformError> {
    let low_disk = |need: u64| -> Result<(), PlatformError> {
        match free_bytes(library) {
            Some(free) if free < need => Err(PlatformError::Invalid(format!(
                "the disk has {free} bytes free; the package needs {need} including a 1 GiB reserve"
            ))),
            _ => Ok(()),
        }
    };
    low_disk(len.saturating_add(DISK_RESERVE_BYTES))?;
    fs::create_dir_all(root).map_err(err)?;
    // One copy, one handle: hashed here, then read as the archive.
    let copy = root.join("archive.zip");
    fs::copy(archive, &copy).map_err(err)?;
    let mut file = fs::File::open(&copy).map_err(err)?;
    let sha256 = sha256_reader(&mut file)?;
    if let Some(want) = &sidecar
        && *want != sha256
    {
        return Err(PlatformError::Invalid(format!(
            "the archive's SHA-256 {sha256} differs from the {want} its .sha256 file states; it may be incomplete or altered"
        )));
    }
    file.seek(SeekFrom::Start(0)).map_err(err)?;
    let mut zip = zip::ZipArchive::new(file)
        .map_err(|e| PlatformError::Invalid(format!("not a readable zip archive: {e}")))?;
    let plan = inspect(&mut zip, sha256, sidecar.is_some())?;
    let id = manifest_id(&mut zip)?;
    low_disk(plan.unpacked_bytes.saturating_add(DISK_RESERVE_BYTES))?;
    if !confirm(&plan, &id) {
        return Ok(None);
    }
    // vv-geo wants the folder named after the pack id, so the pack is staged as `<root>/tree/<id>`.
    let staging = root.join("tree").join(&id);
    let env = extract(&mut zip, &plan, &staging)
        .and_then(|()| Environment::open(&staging).map_err(geo_err))?;
    // Every file of the archive must be a file the manifest names: nothing unvalidated stays.
    // NOTICE.md is the one extra file a package may carry: some licences (the Norwegian Polar
    // Institute's) require their text to travel with the data, so it is kept beside the pack.
    let named: Vec<&str> = env.files();
    if let Some(extra) = plan
        .names
        .iter()
        .find(|n| !named.contains(&n.as_str()) && n.as_str() != NOTICE)
    {
        return Err(PlatformError::Invalid(format!(
            "the archive holds {extra}, which environment.json does not name"
        )));
    }
    drop(env);
    if exists(&id) || library.join(&id).exists() {
        return Err(PlatformError::Invalid(format!(
            "an environment with the id {id:?} is already installed; remove it first"
        )));
    }
    let dst = library.join(&id);
    fs::rename(&staging, &dst).map_err(err)?;
    // The pack is validated again where it now lives.
    if let Err(e) = Environment::open(&dst) {
        let _ = fs::remove_dir_all(&dst);
        return Err(geo_err(e));
    }
    Ok(Some(id))
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
        let ask = |p: &Plan, id: &str| {
            let check = if p.sidecar_matched {
                "The .sha256 file beside the archive matches, so the archive is intact. That does not show who made it."
            } else {
                "No .sha256 file sits beside the archive, so nothing was compared with a published value."
            };
            app.dialog()
                .message(format!(
                    "Install the environment package {id}?\n\nSHA-256 of the archive:\n{}\n\n{check} Compare the SHA-256 with a value from a source you trust. Studio then validates every file against the pack's own manifest.",
                    p.sha256
                ))
                .title("Install an environment package")
                .kind(MessageDialogKind::Info)
                .buttons(MessageDialogButtons::OkCancelCustom(
                    "Install".into(),
                    "Cancel".into(),
                ))
                .blocking_show()
        };
        let Some(id) = install(&src, &geo.paths.imported, |id| geo.get(id).is_ok(), &ask)? else {
            return Ok(None);
        };
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

    fn put(archive: &Path, lib: &Path) -> Result<String, PlatformError> {
        install(archive, lib, |_| false, &|_, _| true).map(|id| id.expect("not cancelled"))
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
        let id = put(&archive, &lib).unwrap();
        assert_eq!(id, "santa-maria-azores");
        assert!(Environment::open(&lib.join(&id)).is_ok());
        assert!(
            put(&archive, &lib)
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
        assert!(put(&a, &lib).unwrap_err().to_string().contains("differs"));

        let b = t.join("b.vvenv.zip");
        zip_of(&dir, &refs, &b, &[("../evil.txt", b"x")]);
        assert!(
            put(&b, &lib)
                .unwrap_err()
                .to_string()
                .contains("plain file name")
        );

        let c = t.join("c.vvenv.zip");
        zip_of(&dir, &refs, &c, &[("notes.txt", b"x")]);
        assert!(
            put(&c, &lib)
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
        assert!(put(&d, &lib).is_err());
        assert!(!lib.exists() || fs::read_dir(&lib).unwrap().count() == 0);
    }

    #[test]
    fn windows_device_names_and_trailing_dots_are_not_plain_names() {
        for bad in [
            "con",
            "CON",
            "nul.json",
            "aux.tar.gz",
            "Prn",
            "com1",
            "COM9.txt",
            "lpt3.dat",
            "a.",
            "environment.json.",
            "..",
            ".",
        ] {
            assert!(!plain_name(bad), "{bad}");
        }
        for ok in [
            "environment.json",
            "image.jpg",
            "console.json",
            "com10.json",
            "com.json",
            "santa-maria_1",
            "NOTICE.md",
        ] {
            assert!(plain_name(ok), "{ok}");
        }
    }

    #[test]
    fn a_reserved_name_inside_an_archive_is_refused() {
        let dir = pack_dir();
        let names = files_of(&dir);
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        let t = temp("reserved");
        let lib = t.join("lib");
        let a = t.join("a.vvenv.zip");
        zip_of(&dir, &refs, &a, &[("nul.json", b"{}")]);
        assert!(
            put(&a, &lib)
                .unwrap_err()
                .to_string()
                .contains("plain file name")
        );
    }

    #[test]
    fn cancelling_installs_nothing_and_the_plan_states_whether_a_sidecar_matched() {
        let dir = pack_dir();
        let names = files_of(&dir);
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        let t = temp("cancel");
        let lib = t.join("lib");
        let a = t.join("a.vvenv.zip");
        zip_of(&dir, &refs, &a, &[]);
        let want = sha256_reader(fs::File::open(&a).unwrap()).unwrap();
        let seen = std::cell::RefCell::new(None);
        let ask = |p: &Plan, id: &str| {
            *seen.borrow_mut() = Some((p.sha256.clone(), p.sidecar_matched, id.to_string()));
            false
        };
        assert!(install(&a, &lib, |_| false, &ask).unwrap().is_none());
        assert_eq!(
            seen.borrow().clone().unwrap(),
            (want.clone(), false, "santa-maria-azores".to_string())
        );
        assert_eq!(fs::read_dir(&lib).unwrap().count(), 0);
        fs::write(
            t.join("a.vvenv.zip.sha256"),
            format!("{want}  a.vvenv.zip\n"),
        )
        .unwrap();
        assert!(install(&a, &lib, |_| false, &ask).unwrap().is_none());
        assert!(seen.borrow().clone().unwrap().1);
    }

    /// Optional: installs real packages built by scripts/geo/package_environment.py, named in
    /// VV_ENV_ZIPS (separated by ';'). Skipped when the variable is not set.
    #[test]
    fn real_packages_install_when_given() {
        let Ok(list) = std::env::var("VV_ENV_ZIPS") else {
            return;
        };
        let lib = temp("real");
        for z in list.split(';').filter(|s| !s.is_empty()) {
            let id = put(Path::new(z), &lib).unwrap_or_else(|e| panic!("{z}: {e}"));
            assert!(Environment::open(&lib.join(&id)).is_ok(), "{id}");
            println!("installed {id}");
        }
    }
}
