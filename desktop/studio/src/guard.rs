//! Runtime guard against starting a development build of the Studio on installed data.
//!
//! The identifier compiled into the executable (`tauri::generate_context!`, which only builds a value
//! in memory and writes nothing) tells the two kinds of build apart. The release build, whose identifier
//! is the one of the installed application, skips the guard. Every other build, whatever the profile
//! it was compiled with, enforces it, before Tauri, WebView2 or any other subsystem starts: it starts
//! only when it carries a launch token written by `desktop/studio/tests/studio_launch.py`, and every
//! folder it writes is a folder of that token.
//!
//! The token is the file named by `VVLAB_DEV_LAUNCH`: JSON with a `nonce` (it must equal
//! `VVLAB_DEV_NONCE`), a `token_dir` and the value of each redirected variable. The guard checks that
//! each of `WEBVIEW2_USER_DATA_FOLDER`, `VVLAB_LIBRARY`, `VVLAB_CONFIG`, `VVLAB_MODULES`, `APPDATA` and
//! `LOCALAPPDATA` is set to the value in the file and resolves under `token_dir`; that `token_dir` is not
//! in, and does not contain, the installed application's data (derived from the Windows known folders,
//! not from the environment); and that the WebView2 arguments do not set a user data directory. The token
//! is single use: the file is renamed to `.used` before the start, and a failure to rename refuses it.
//!
//! A refusal exits with [`REFUSED_EXIT`] and writes one line to stderr. It writes nothing else, no log.
//!
//! This protects against accidental misuse, not against someone who builds the release identifier into
//! an executable or forges a token: it has no secret and no signature. `vv-studio --guard-only` prints
//! the decision and exits before Tauri, for the tests.

use std::collections::BTreeMap;

/// Exit code of a refused start (EX_CONFIG): distinct from the 1 and 2 used elsewhere.
pub const REFUSED_EXIT: i32 = 78;
pub const ENV_LAUNCH: &str = "VVLAB_DEV_LAUNCH";
pub const ENV_NONCE: &str = "VVLAB_DEV_NONCE";
pub const BROWSER_ARGUMENTS: &str = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS";
/// The variables that must be redirected into the token directory.
pub const GUARDED: [&str; 6] = [
    "WEBVIEW2_USER_DATA_FOLDER",
    "VVLAB_LIBRARY",
    "VVLAB_CONFIG",
    "VVLAB_MODULES",
    "APPDATA",
    "LOCALAPPDATA",
];
const LIBRARY_FOLDER: &str = "VV Lab Library";
const CINEMATIC_FOLDER: &str = "VV Lab Cinematic";

/// The identifier of the installed application. Built from parts so that a development executable does
/// not carry it as one string: the test tooling reads the embedded identifier from the binary.
pub fn release_identifier() -> String {
    ["org", "vvlab", "studio"].join(".")
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Decision {
    /// The release identifier: the guard does not apply.
    Release,
    /// A development build with a valid token; the token directory.
    Dev(String),
    Refused(String),
}

impl Decision {
    pub fn describe(&self) -> String {
        match self {
            Decision::Release => "allowed: release identifier, the guard does not apply".into(),
            Decision::Dev(dir) => {
                format!("allowed: development identifier with a valid launch token in {dir}")
            }
            Decision::Refused(why) => format!("refused: {why}"),
        }
    }
}

/// The real folders of this user, as the Windows known-folder API reports them (never the environment).
#[derive(Debug, Clone, Default)]
pub struct KnownFolders {
    pub local_app_data: Option<String>,
    pub roaming_app_data: Option<String>,
    pub documents: Option<String>,
    pub profile: Option<String>,
}

/// The launch token file.
#[derive(Debug, Clone)]
pub struct Token {
    pub nonce: String,
    pub token_dir: String,
    pub paths: BTreeMap<String, String>,
}

impl Token {
    pub fn parse(text: &str) -> Result<Token, String> {
        let v: serde_json::Value = serde_json::from_str(text)
            .map_err(|e| format!("the launch token is not JSON ({e})"))?;
        let nonce = v
            .get("nonce")
            .and_then(|x| x.as_str())
            .filter(|s| !s.is_empty())
            .ok_or("the launch token has no nonce")?;
        let token_dir = v
            .get("token_dir")
            .and_then(|x| x.as_str())
            .filter(|s| !s.is_empty())
            .ok_or("the launch token has no token_dir")?;
        let mut paths = BTreeMap::new();
        for name in GUARDED {
            let value = v
                .pointer(&format!("/paths/{name}"))
                .and_then(|x| x.as_str())
                .filter(|s| !s.is_empty());
            let value = value.ok_or_else(|| format!("the launch token has no path for {name}"))?;
            paths.insert(name.to_string(), value.to_string());
        }
        Ok(Token {
            nonce: nonce.into(),
            token_dir: token_dir.into(),
            paths,
        })
    }
}

/// A comparable form of a Windows path: no device prefix, backslashes, lower case, no trailing
/// separator. `None` for a network path, which is never a token folder.
pub fn norm(path: &str) -> Option<String> {
    let mut p = path.replace('/', "\\");
    if let Some(rest) = p
        .strip_prefix("\\\\?\\")
        .or_else(|| p.strip_prefix("\\\\.\\"))
    {
        if rest
            .get(..4)
            .is_some_and(|h| h.eq_ignore_ascii_case("unc\\"))
        {
            return None;
        }
        let bytes = rest.as_bytes();
        let drive = bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':';
        if !drive {
            return None; // Volume{...}, GLOBALROOT, PhysicalDrive: only a drive letter is accepted
        }
        p = rest.to_string();
    } else if p.starts_with("\\\\") {
        return None;
    }
    let p = p.trim_end_matches('\\').to_lowercase();
    if p.is_empty() { None } else { Some(p) }
}

fn is_under(path: &str, root: &str) -> bool {
    path == root || (path.starts_with(root) && path[root.len()..].starts_with('\\'))
}

/// The pure decision. `canon` resolves a path to its real, existing form (the file system in a real
/// start, a fake in the tests); `None` means it does not resolve.
pub fn decide(
    identifier: &str,
    env: &BTreeMap<String, String>,
    token: Result<Token, String>,
    known: &KnownFolders,
    canon: &dyn Fn(&str) -> Option<String>,
) -> Decision {
    if identifier == release_identifier() {
        return Decision::Release;
    }
    let refuse = |why: String| {
        Decision::Refused(format!(
            "{why} (identifier {identifier}, development build)"
        ))
    };
    let token = match token {
        Ok(t) => t,
        Err(e) => return refuse(e),
    };
    match env.get(ENV_NONCE) {
        Some(n) if *n == token.nonce => {}
        Some(_) => return refuse("the launch nonce does not match the token".into()),
        None => return refuse(format!("{ENV_NONCE} is not set")),
    }
    if env
        .get(BROWSER_ARGUMENTS)
        .is_some_and(|a| a.to_lowercase().contains("user-data-dir"))
    {
        return refuse(format!("{BROWSER_ARGUMENTS} sets a user data directory"));
    }
    let Some(dir) = canon(&token.token_dir).and_then(|d| norm(&d)) else {
        return refuse(format!(
            "the token directory {} does not resolve to a local folder",
            token.token_dir
        ));
    };
    // The token directory must not be, contain or lie in the installed application's data.
    let (Some(local), Some(roaming), Some(documents)) = (
        &known.local_app_data,
        &known.roaming_app_data,
        &known.documents,
    ) else {
        return refuse(
            "the real known folders could not be read, so the installed data cannot be excluded"
                .into(),
        );
    };
    let release = release_identifier();
    let protected: Vec<String> = [
        format!("{local}\\{release}"),
        format!("{roaming}\\{release}"),
        format!("{documents}\\{LIBRARY_FOLDER}"),
        format!("{roaming}\\{CINEMATIC_FOLDER}"),
        format!("{local}\\{CINEMATIC_FOLDER}"),
    ]
    .iter()
    .filter_map(|p| norm(p))
    .collect();
    let roots: Vec<String> = [
        Some(local),
        Some(roaming),
        Some(documents),
        known.profile.as_ref(),
    ]
    .into_iter()
    .flatten()
    .filter_map(|p| norm(p))
    .collect();
    for p in &protected {
        if is_under(&dir, p) || is_under(p, &dir) {
            return refuse(format!(
                "the token directory {dir} is, contains or lies in installed data ({p})"
            ));
        }
    }
    for r in &roots {
        if is_under(r, &dir) {
            return refuse(format!(
                "the token directory {dir} is or contains the known folder {r}"
            ));
        }
    }
    for name in GUARDED {
        let Some(value) = env.get(name).filter(|v| !v.is_empty()) else {
            return refuse(format!("{name} is not set"));
        };
        if token.paths.get(name) != Some(value) {
            return refuse(format!("{name} is not the value in the launch token"));
        }
        let Some(real) = canon(value).and_then(|c| norm(&c)) else {
            return refuse(format!(
                "{name} does not resolve to an existing local folder: {value}"
            ));
        };
        if !is_under(&real, &dir) {
            return refuse(format!(
                "{name} resolves to {real}, outside the token directory {dir}"
            ));
        }
    }
    Decision::Dev(dir)
}

fn env_snapshot() -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for name in GUARDED
        .iter()
        .copied()
        .chain([ENV_LAUNCH, ENV_NONCE, BROWSER_ARGUMENTS])
    {
        if let Some(v) = std::env::var_os(name) {
            out.insert(name.to_string(), v.to_string_lossy().into_owned());
        }
    }
    out
}

fn real_canon(p: &str) -> Option<String> {
    std::fs::canonicalize(p)
        .ok()
        .map(|c| c.to_string_lossy().into_owned())
}

/// Reads the token named by the environment, decides, and for a development start consumes the token
/// (renames it to `.used`; a failure to do so refuses the start). Touches nothing else.
pub fn evaluate(
    identifier: &str,
    env: &BTreeMap<String, String>,
    known: &KnownFolders,
) -> Decision {
    if identifier == release_identifier() {
        return Decision::Release;
    }
    let file = env.get(ENV_LAUNCH).cloned();
    let token = match &file {
        None => Err(format!(
            "{ENV_LAUNCH} is not set: this development build was not started by the authorised launcher"
        )),
        Some(f) => std::fs::read_to_string(f)
            .map_err(|e| {
                format!("the launch token {f} cannot be read ({e}): missing or already used")
            })
            .and_then(|t| Token::parse(&t)),
    };
    let decision = decide(identifier, env, token, known, &real_canon);
    if let (Decision::Dev(_), Some(f)) = (&decision, &file) {
        let used = format!("{f}.used");
        if std::fs::rename(f, &used).is_err() {
            return Decision::Refused(format!("the launch token {f} could not be marked as used"));
        }
    }
    decision
}

/// The guard of a real start: reads the environment and the Windows known folders.
pub fn check(identifier: &str) -> Decision {
    if identifier == release_identifier() {
        return Decision::Release;
    }
    evaluate(identifier, &env_snapshot(), &real_known_folders())
}

#[cfg(windows)]
fn known_folder(id: &windows_sys::core::GUID) -> Option<String> {
    use windows_sys::Win32::System::Com::CoTaskMemFree;
    use windows_sys::Win32::UI::Shell::SHGetKnownFolderPath;
    let mut out: *mut u16 = std::ptr::null_mut();
    // SAFETY: `id` is a valid GUID; on success `out` points to a NUL-terminated wide string that this
    // function copies and frees with CoTaskMemFree, as the API requires.
    unsafe {
        let hr = SHGetKnownFolderPath(id, 0, std::ptr::null_mut(), &mut out);
        if hr != 0 || out.is_null() {
            if !out.is_null() {
                CoTaskMemFree(out.cast());
            }
            return None;
        }
        let mut len = 0usize;
        while *out.add(len) != 0 {
            len += 1;
        }
        let s = String::from_utf16_lossy(std::slice::from_raw_parts(out, len));
        CoTaskMemFree(out.cast());
        Some(s)
    }
}

#[cfg(windows)]
pub fn real_known_folders() -> KnownFolders {
    use windows_sys::Win32::UI::Shell::{
        FOLDERID_Documents, FOLDERID_LocalAppData, FOLDERID_Profile, FOLDERID_RoamingAppData,
    };
    KnownFolders {
        local_app_data: known_folder(&FOLDERID_LocalAppData),
        roaming_app_data: known_folder(&FOLDERID_RoamingAppData),
        documents: known_folder(&FOLDERID_Documents),
        profile: known_folder(&FOLDERID_Profile),
    }
}

/// Off Windows the folders are not known: a development build is refused (the Studio is Windows only).
#[cfg(not(windows))]
pub fn real_known_folders() -> KnownFolders {
    KnownFolders::default()
}

/// The decision for the command line: refuses with the distinct exit code and one line on stderr, prints
/// the decision for `--guard-only`, and returns only when the start is allowed.
pub fn enforce(identifier: &str, args: &[String]) {
    let decision = check(identifier);
    let guard_only = args.iter().any(|a| a == "--guard-only");
    if guard_only {
        println!("{}", decision.describe());
        std::process::exit(if matches!(decision, Decision::Refused(_)) {
            REFUSED_EXIT
        } else {
            0
        });
    }
    if let Decision::Refused(why) = decision {
        eprintln!("vv-studio: refused to start: {why}");
        std::process::exit(REFUSED_EXIT);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    const DEV: &str = "org.vvlab.devstudio";
    const TOKEN_DIR: &str = "C:\\Scratch\\vv-launch-1";

    fn known() -> KnownFolders {
        KnownFolders {
            local_app_data: Some("C:\\FakeUser\\AppData\\Local".into()),
            roaming_app_data: Some("C:\\FakeUser\\AppData\\Roaming".into()),
            documents: Some("C:\\FakeUser\\Documents".into()),
            profile: Some("C:\\FakeUser".into()),
        }
    }

    /// Fake resolution: every path exists (but those named "missing") and resolves to itself, with ".."
    /// collapsed, in verbatim form.
    fn fake_canon(p: &str) -> Option<String> {
        if p.contains("missing") {
            return None;
        }
        let mut parts: Vec<&str> = Vec::new();
        for c in p.split(['\\', '/']) {
            match c {
                ".." => {
                    parts.pop();
                }
                "." => {}
                other => parts.push(other),
            }
        }
        Some(format!("\\\\?\\{}", parts.join("\\")))
    }

    fn paths() -> BTreeMap<String, String> {
        GUARDED
            .iter()
            .map(|n| (n.to_string(), format!("{TOKEN_DIR}\\{}", n.to_lowercase())))
            .collect()
    }

    fn token() -> Token {
        Token {
            nonce: "n1".into(),
            token_dir: TOKEN_DIR.into(),
            paths: paths(),
        }
    }

    fn env() -> BTreeMap<String, String> {
        let mut e = paths();
        e.insert(ENV_NONCE.into(), "n1".into());
        e.insert(ENV_LAUNCH.into(), format!("{TOKEN_DIR}\\launch.json"));
        e
    }

    fn run(
        identifier: &str,
        env: &BTreeMap<String, String>,
        token: Result<Token, String>,
    ) -> Decision {
        decide(identifier, env, token, &known(), &fake_canon)
    }

    fn refused(d: &Decision, needle: &str) {
        match d {
            Decision::Refused(w) => assert!(w.contains(needle), "{w} lacks {needle}"),
            other => panic!("expected a refusal containing {needle}, got {other:?}"),
        }
    }

    #[test]
    fn the_release_identifier_matches_the_release_overlay_and_not_the_base_config() {
        let overlay: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.release.conf.json")).unwrap();
        assert_eq!(overlay["identifier"], release_identifier());
        let base: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_ne!(base["identifier"], release_identifier());
        assert_eq!(base["identifier"], DEV);
    }

    #[test]
    fn release_skips_the_guard_even_with_nothing_set() {
        assert_eq!(
            run(
                &release_identifier(),
                &BTreeMap::new(),
                Err("no token".into())
            ),
            Decision::Release
        );
    }

    #[test]
    fn a_direct_launch_without_a_token_is_refused() {
        refused(
            &run(
                DEV,
                &BTreeMap::new(),
                Err("VVLAB_DEV_LAUNCH is not set".into()),
            ),
            "VVLAB_DEV_LAUNCH",
        );
    }

    #[test]
    fn any_identifier_but_the_release_one_is_guarded() {
        for id in [
            DEV,
            "org.vvlab.studio.m191review",
            "ORG.VVLAB.STUDIO",
            "",
            "org.vvlab.studio ",
        ] {
            refused(
                &run(id, &BTreeMap::new(), Err("no token".into())),
                "no token",
            );
        }
    }

    #[test]
    fn a_valid_token_is_accepted() {
        assert_eq!(
            run(DEV, &env(), Ok(token())),
            Decision::Dev("c:\\scratch\\vv-launch-1".into())
        );
    }

    #[test]
    fn a_wrong_or_missing_nonce_is_refused() {
        let mut e = env();
        e.insert(ENV_NONCE.into(), "other".into());
        refused(&run(DEV, &e, Ok(token())), "nonce does not match");
        e.remove(ENV_NONCE);
        refused(&run(DEV, &e, Ok(token())), "VVLAB_DEV_NONCE is not set");
    }

    #[test]
    fn every_guarded_variable_must_be_set_and_equal_to_the_token() {
        for name in GUARDED {
            let mut e = env();
            e.remove(name);
            refused(&run(DEV, &e, Ok(token())), &format!("{name} is not set"));
            let mut e = env();
            e.insert(name.into(), format!("{TOKEN_DIR}\\elsewhere"));
            refused(
                &run(DEV, &e, Ok(token())),
                &format!("{name} is not the value in the launch token"),
            );
            let mut e = env();
            e.insert(name.into(), String::new());
            refused(&run(DEV, &e, Ok(token())), &format!("{name} is not set"));
        }
    }

    #[test]
    fn a_variable_outside_the_token_directory_is_refused_even_if_the_token_says_so() {
        for decoy in [
            "C:\\Decoy\\library",
            "C:\\Scratch\\vv-launch-10\\x",
            "C:\\Scratch\\vv-launch-1\\..\\other\\x",
        ] {
            for name in GUARDED {
                let mut t = token();
                t.paths.insert(name.into(), decoy.into());
                let mut e = env();
                e.insert(name.into(), decoy.into());
                refused(&run(DEV, &e, Ok(t)), "outside the token directory");
            }
        }
    }

    #[test]
    fn a_path_that_does_not_resolve_is_refused() {
        let mut t = token();
        t.paths
            .insert("VVLAB_LIBRARY".into(), format!("{TOKEN_DIR}\\missing"));
        let mut e = env();
        e.insert("VVLAB_LIBRARY".into(), format!("{TOKEN_DIR}\\missing"));
        refused(&run(DEV, &e, Ok(t)), "does not resolve");
    }

    #[test]
    fn a_token_directory_in_installed_data_or_known_roots_is_refused() {
        for dir in [
            "C:\\FakeUser\\AppData\\Local\\org.vvlab.studio",
            "C:\\FakeUser\\AppData\\Local\\ORG.VVLAB.STUDIO\\EBWebView",
            "C:\\FakeUser\\AppData\\Roaming\\org.vvlab.studio\\x",
            "C:\\FakeUser\\Documents\\VV Lab Library\\runs",
            "C:\\FakeUser\\AppData\\Roaming\\VV Lab Cinematic\\logs",
            "C:\\FakeUser\\AppData\\Local\\VV Lab Cinematic",
            "C:\\FakeUser\\AppData\\Local",
            "C:\\FakeUser\\AppData",
            "C:\\FakeUser",
            "C:\\",
            "c:\\fakeuser\\appdata\\local\\org.vvlab.studio\\",
        ] {
            let mut t = token();
            t.token_dir = dir.into();
            let p: BTreeMap<String, String> = GUARDED
                .iter()
                .map(|n| (n.to_string(), format!("{dir}\\{}", n.to_lowercase())))
                .collect();
            t.paths = p.clone();
            let mut e = env();
            e.extend(p);
            let d = run(DEV, &e, Ok(t));
            assert!(matches!(d, Decision::Refused(_)), "{dir}: {d:?}");
        }
    }

    #[test]
    fn a_scratch_folder_next_to_installed_data_with_a_similar_name_is_accepted() {
        let dir = "C:\\FakeUser\\AppData\\Local\\org.vvlab.studio.scratch\\run1";
        let mut t = token();
        t.token_dir = dir.into();
        let p: BTreeMap<String, String> = GUARDED
            .iter()
            .map(|n| (n.to_string(), format!("{dir}\\{}", n.to_lowercase())))
            .collect();
        t.paths = p.clone();
        let mut e = env();
        e.extend(p);
        assert!(matches!(run(DEV, &e, Ok(t)), Decision::Dev(_)));
    }

    #[test]
    fn network_and_device_paths_are_refused() {
        for dir in [
            "\\\\localhost\\c$\\x",
            "//server/share/x",
            "\\\\?\\UNC\\server\\share\\x",
            "\\\\?\\Volume{01234567-89ab-cdef-0123-456789abcdef}\\x",
            "\\\\?\\GLOBALROOT\\Device\\x",
            "\\\\.\\PhysicalDrive0",
        ] {
            assert_eq!(norm(dir), None, "{dir}");
            let mut t = token();
            t.token_dir = dir.into();
            assert!(
                matches!(run(DEV, &env(), Ok(t)), Decision::Refused(_)),
                "{dir}"
            );
        }
        assert_eq!(norm("\\\\?\\C:\\X\\"), Some("c:\\x".into()));
        assert_eq!(norm("c:/X/y/"), Some("c:\\x\\y".into()));
    }

    #[test]
    fn a_user_data_dir_browser_argument_is_refused() {
        for a in [
            "--user-data-dir=C:\\x",
            "--remote-debugging-port=1 --USER-DATA-DIR=C:\\x",
        ] {
            let mut e = env();
            e.insert(BROWSER_ARGUMENTS.into(), a.into());
            refused(&run(DEV, &e, Ok(token())), "user data directory");
        }
        let mut e = env();
        e.insert(
            BROWSER_ARGUMENTS.into(),
            "--remote-debugging-port=9333".into(),
        );
        assert!(matches!(run(DEV, &e, Ok(token())), Decision::Dev(_)));
    }

    #[test]
    fn unknown_real_folders_fail_closed() {
        let d = decide(
            DEV,
            &env(),
            Ok(token()),
            &KnownFolders::default(),
            &fake_canon,
        );
        refused(&d, "known folders could not be read");
    }

    #[test]
    fn token_parsing_requires_every_field() {
        let good = r#"{"nonce":"a","token_dir":"C:\\x","paths":{"WEBVIEW2_USER_DATA_FOLDER":"1","VVLAB_LIBRARY":"2","VVLAB_CONFIG":"3","VVLAB_MODULES":"4","APPDATA":"5","LOCALAPPDATA":"6"}}"#;
        assert!(Token::parse(good).is_ok());
        for bad in [
            "",
            "not json",
            "{}",
            r#"{"nonce":"","token_dir":"x","paths":{}}"#,
            r#"{"nonce":"a","token_dir":"x","paths":{"APPDATA":"1"}}"#,
        ] {
            assert!(Token::parse(bad).is_err(), "{bad}");
        }
    }

    /// Process-independent checks of the file handling, in disposable folders (never the real profile).
    mod files {
        use super::*;
        use std::fs;

        fn scratch(tag: &str) -> PathBuf {
            let d =
                std::env::temp_dir().join(format!("vv-guard-test-{}-{tag}", std::process::id()));
            let _ = fs::remove_dir_all(&d);
            fs::create_dir_all(&d).unwrap();
            fs::canonicalize(&d).unwrap()
        }

        /// A token directory with real subfolders, a token file and the matching environment.
        fn launch(tag: &str) -> (PathBuf, BTreeMap<String, String>, KnownFolders) {
            let dir = scratch(tag);
            let mut paths = serde_json::Map::new();
            let mut env = BTreeMap::new();
            for name in GUARDED {
                let p = dir.join(name.to_lowercase());
                fs::create_dir_all(&p).unwrap();
                paths.insert(name.into(), p.to_string_lossy().into_owned().into());
                env.insert(name.to_string(), p.to_string_lossy().into_owned());
            }
            let file = dir.join("launch.json");
            let body = serde_json::json!({ "nonce": "abc", "token_dir": dir.to_string_lossy(), "paths": paths });
            fs::write(&file, body.to_string()).unwrap();
            env.insert(ENV_NONCE.into(), "abc".into());
            env.insert(ENV_LAUNCH.into(), file.to_string_lossy().into_owned());
            // Fake known folders in a different disposable folder: the decoy "installed profile".
            let fake = scratch(&format!("{tag}-profile"));
            let known = KnownFolders {
                local_app_data: Some(fake.join("Local").to_string_lossy().into_owned()),
                roaming_app_data: Some(fake.join("Roaming").to_string_lossy().into_owned()),
                documents: Some(fake.join("Documents").to_string_lossy().into_owned()),
                profile: Some(fake.to_string_lossy().into_owned()),
            };
            (dir, env, known)
        }

        #[test]
        fn a_valid_token_is_accepted_once_and_then_consumed() {
            let (dir, env, known) = launch("once");
            assert!(matches!(evaluate(DEV, &env, &known), Decision::Dev(_)));
            assert!(!dir.join("launch.json").exists());
            assert!(dir.join("launch.json.used").exists());
            // The same environment again: the token is gone.
            refused(&evaluate(DEV, &env, &known), "missing or already used");
        }

        #[test]
        fn a_missing_token_file_and_a_missing_variable_are_refused() {
            let (_dir, mut env, known) = launch("missing");
            env.insert(ENV_LAUNCH.into(), "C:\\no\\such\\launch.json".into());
            refused(&evaluate(DEV, &env, &known), "cannot be read");
            env.remove(ENV_LAUNCH);
            refused(
                &evaluate(DEV, &env, &known),
                "was not started by the authorised launcher",
            );
        }

        #[test]
        fn an_invalid_nonce_does_not_consume_the_token() {
            let (dir, mut env, known) = launch("nonce");
            env.insert(ENV_NONCE.into(), "wrong".into());
            refused(&evaluate(DEV, &env, &known), "nonce does not match");
            assert!(dir.join("launch.json").exists());
        }

        #[test]
        fn a_decoy_folder_outside_the_token_directory_is_refused() {
            let (_dir, mut env, known) = launch("decoy");
            let decoy = scratch("decoy-elsewhere");
            env.insert("VVLAB_LIBRARY".into(), decoy.to_string_lossy().into_owned());
            refused(
                &evaluate(DEV, &env, &known),
                "VVLAB_LIBRARY is not the value in the launch token",
            );
        }

        #[test]
        fn a_token_that_names_a_decoy_installed_profile_is_refused() {
            let (_dir, env, known) = launch("profile");
            // The same launch, but the "real" Local AppData is the token directory's own parent chain.
            let dir = PathBuf::from(env.get("VVLAB_LIBRARY").unwrap())
                .parent()
                .unwrap()
                .to_path_buf();
            let bad = KnownFolders {
                local_app_data: Some(dir.to_string_lossy().into_owned()),
                ..known
            };
            let d = evaluate(DEV, &env, &bad);
            assert!(matches!(d, Decision::Refused(_)), "{d:?}");
        }

        #[test]
        fn a_symlink_style_escape_is_refused_by_canonicalisation() {
            let (dir, mut env, known) = launch("dots");
            let outside = scratch("dots-outside");
            let tricky = format!(
                "{}\\library\\..\\..\\{}",
                dir.display(),
                outside.file_name().unwrap().to_string_lossy()
            );
            let mut file: serde_json::Value =
                serde_json::from_str(&fs::read_to_string(dir.join("launch.json")).unwrap())
                    .unwrap();
            file["paths"]["VVLAB_LIBRARY"] = tricky.clone().into();
            fs::write(dir.join("launch.json"), file.to_string()).unwrap();
            env.insert("VVLAB_LIBRARY".into(), tricky);
            let d = evaluate(DEV, &env, &known);
            assert!(matches!(d, Decision::Refused(_)), "{d:?}");
        }
    }
}
