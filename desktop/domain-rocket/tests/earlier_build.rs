//! Upgrade path through the platform, with the real rocket host: a run stored by an earlier build
//! must replay as verified against its own record, not as tampered, while a run of the current
//! build keeps the strict byte-for-byte replay and tampering is still rejected in both cases.
//!
//! The earlier build is constructed, not assumed. The run is made by the host as installed, then
//! stored the way an older Studio stored it (a request without the parameter that later builds
//! added, under the run id that request and that host build give), and the host executable is
//! replaced by another build before the platform starts again.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use vv_domain_rocket::catalog::{catalog, request};
use vv_platform::canonical::{canonical_bytes, sha256_hex};
use vv_platform::{Platform, REPLAY_VERIFIED_EARLIER_BUILD, RunRecord, RunRequest};

/// Parameter added after M15; an older run was stored without it.
const ADDED: &str = "altimeter_residual_threshold_m";

static N: AtomicU64 = AtomicU64::new(0);

fn temp(label: &str) -> PathBuf {
    let n = N.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!(
        "vv-rocket-upgrade-{}-{label}-{n}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn install(domains: &Path) -> PathBuf {
    let dir = domains.join("rocket-landing");
    fs::create_dir_all(&dir).unwrap();
    let exe = dir.join("vv-domain-rocket.exe");
    fs::copy(env!("CARGO_BIN_EXE_vv-domain-rocket"), &exe).unwrap();
    fs::write(dir.join("domain.json"), include_str!("../domain.json")).unwrap();
    exe
}

/// Edits a stored file as text, so no number is re-printed: a changed last digit anywhere would
/// make the fixture differ from a real stored run for a reason that is not the one under test.
fn replace_once(path: &Path, from: &str, to: &str) {
    let text = fs::read_to_string(path).unwrap();
    assert!(text.contains(from), "{from} not in {}", path.display());
    fs::write(path, text.replacen(from, to, 1)).unwrap();
}

fn without_line(path: &Path, containing: &str) {
    let text = fs::read_to_string(path).unwrap();
    let line = text
        .lines()
        .find(|l| l.contains(containing))
        .unwrap_or_else(|| panic!("{containing} in {}", path.display()));
    assert!(line.trim_end().ends_with(','), "{line}");
    fs::write(
        path,
        text.replacen(
            &format!(
                "{line}
"
            ),
            "",
            1,
        ),
    )
    .unwrap();
}

fn demo_request() -> RunRequest {
    let cat = catalog();
    let scenario = &cat.scenarios[0];
    request(&scenario.id, &scenario.default_controller, 5000, Vec::new())
}

/// Re-stores run `id` as an older Studio would have: the request has no `ADDED` parameter, and the
/// run id is the identity of that request under the host build that wrote the run. Returns the new id.
fn store_as_older(p: &Platform, id: &str) -> String {
    let dir = p.library().run_dir(id).unwrap();
    for file in ["record.json", "request.json"] {
        without_line(&dir.join(file), ADDED);
    }
    let record: RunRecord =
        serde_json::from_slice(&fs::read(dir.join("record.json")).unwrap()).unwrap();
    assert!(!record.request.parameters.contains_key(ADDED));
    let meta = p.library().read_meta(id).unwrap();
    let identity = serde_json::json!({
        "domain": record.request.domain,
        "host_sha256": meta.host_sha256,
        "request": record.request,
    });
    let new_id = sha256_hex(&canonical_bytes(&identity))[..16].to_owned();
    replace_once(
        &dir.join("meta.json"),
        &format!("\"run_id\": \"{id}\""),
        &format!("\"run_id\": \"{new_id}\""),
    );
    fs::rename(&dir, p.library().run_dir(&new_id).unwrap()).unwrap();
    new_id
}

fn failed(r: &vv_platform::ReplayReport) -> Vec<String> {
    r.checks
        .iter()
        .filter(|c| !c.pass)
        .map(|c| format!("{}: {}", c.name, c.detail))
        .collect()
}

#[test]
fn a_run_stored_by_an_earlier_build_replays_as_verified_earlier_build_and_tampering_is_still_rejected()
 {
    let root = temp("upgrade");
    let domains = root.join("domains");
    let library = root.join("library");
    let exe = install(&domains);
    let (p, _) = Platform::start(std::slice::from_ref(&domains), &library, "test").unwrap();
    let made = p.run(&demo_request()).unwrap();
    assert_eq!(p.replay(&made.run_id).unwrap().status, "verified");
    // A second run is left exactly as the host wrote it.
    let mut unchanged_request = demo_request();
    unchanged_request.seed = 5001;
    let unchanged = p.run(&unchanged_request).unwrap().run_id;
    let old_id = store_as_older(&p, &made.run_id);
    drop(p);

    // The build that stored the run is replaced by another one (a byte of overlay differs).
    let mut bytes = fs::read(&exe).unwrap();
    bytes.push(0);
    fs::write(&exe, bytes).unwrap();
    let (p, _) = Platform::start(std::slice::from_ref(&domains), &library, "test").unwrap();

    // The replay is strict first: a run that still reproduces byte for byte under another build
    // is plain `verified`, with the byte comparison and the native replay intact.
    let report = p.replay(&unchanged).unwrap();
    assert_eq!(report.status, "verified", "{:?}", failed(&report));
    assert!(report.checks.iter().any(|c| c.name
        == "recomputed artifacts equal the stored artifacts byte for byte"
        && c.pass));
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.name.starts_with("vv-rocket replay:") && c.pass)
    );

    let report = p.replay(&old_id).unwrap();
    assert_eq!(
        report.status,
        REPLAY_VERIFIED_EARLIER_BUILD,
        "{:?}",
        failed(&report)
    );
    assert!(
        report.checks.iter().all(|c| c.pass),
        "{:?}",
        failed(&report)
    );
    let note = report
        .checks
        .iter()
        .find(|c| c.name == "stored request is valid and canonical")
        .unwrap();
    assert!(
        note.detail.starts_with("recorded by domain version ")
            && note.detail.contains("re-simulated with current defaults")
            && note.detail.contains(ADDED),
        "{}",
        note.detail
    );
    // An earlier-build run still exports as a normal package, not as a rejected one.
    let zip = p.export_evidence(&old_id, None).unwrap();
    assert!(
        zip.to_string_lossy().ends_with("-evidence.zip"),
        "{}",
        zip.display()
    );

    // A changed number in the stored telemetry is rejected, and the check says what disagrees.
    // (A flipped verdict would be caught earlier still, by the summary in meta.json.)
    let run_dir = p.library().run_dir(&old_id).unwrap();
    let original = fs::read(run_dir.join("record.json")).unwrap();
    perturb_first_timebase_value(&run_dir.join("record.json"));
    let report = p.replay(&old_id).unwrap();
    assert_eq!(report.status, "rejected");
    assert!(
        failed(&report)
            .iter()
            .any(|f| f.contains("recomputed result agrees") && f.contains("timebase")),
        "{:?}",
        failed(&report)
    );
    fs::write(run_dir.join("record.json"), original).unwrap();

    // A changed native file is rejected.
    let trace = run_dir.join("trace.json");
    let text = fs::read_to_string(&trace).unwrap();
    fs::write(&trace, text.replacen('1', "2", 1)).unwrap();
    assert_eq!(p.replay(&old_id).unwrap().status, "rejected");
    fs::write(&trace, text).unwrap();
    assert_eq!(
        p.replay(&old_id).unwrap().status,
        REPLAY_VERIFIED_EARLIER_BUILD
    );

    // A run of the running build keeps the strict replay: text the earlier-build replay ignores
    // is caught, and an unedited run verifies byte for byte.
    let fresh = p.run(&demo_request()).unwrap();
    assert_ne!(fresh.run_id, old_id);
    assert_eq!(p.replay(&fresh.run_id).unwrap().status, "verified");
    let dir = p.library().run_dir(&fresh.run_id).unwrap();
    let label = read_label(&dir.join("record.json"));
    replace_once(
        &dir.join("record.json"),
        &label,
        "\"label\": \"Landed, edited\"",
    );
    assert_eq!(p.replay(&fresh.run_id).unwrap().status, "rejected");
    let _ = fs::remove_dir_all(root);
}

/// The first `"label": ...` line of the outcome, which follows `"outcome": {` in the file.
fn read_label(path: &Path) -> String {
    let text = fs::read_to_string(path).unwrap();
    let from = text.find("\"outcome\": {").unwrap();
    let rest = &text[from..];
    let start = rest.find("\"label\": ").unwrap();
    let end = start + rest[start..].find('\n').unwrap();
    rest[start..end].trim_end_matches(',').to_string()
}

/// Replaces the second sample of the first timebase with another number, as text.
fn perturb_first_timebase_value(path: &Path) {
    let text = fs::read_to_string(path).unwrap();
    let from = text.find("\"timebases\": {").unwrap();
    let open = from + text[from..].find('[').unwrap();
    // The array is pretty-printed with one number per line: skip the bracket line and the first
    // number, then rewrite the line of the second.
    let line_starts: Vec<usize> = text[open..]
        .match_indices('\n')
        .map(|(i, _)| open + i + 1)
        .collect();
    let (begin, end) = (line_starts[1], line_starts[2]);
    let indent: String = text[begin..end].chars().take_while(|c| *c == ' ').collect();
    let edited = format!("{}{indent}123456.5,\n{}", &text[..begin], &text[end..]);
    fs::write(path, edited).unwrap();
}

/// A run written by the host of commit 3b056cc (Studio 0.15.0, domain version 0.15.0, six
/// parameters), copied here unchanged: `gnss_bias` 15 m from 8 s on `m91-landing` with the guarded
/// controller, seed 5002. It is real drift, not a construction: the current catalogue has thirteen
/// more parameters, other texts and other metrics, and the domain version string is the same.
fn copy_fixture(label: &str) -> PathBuf {
    let from = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/stored-by-0.15.0");
    let dir = temp(label);
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        fs::copy(entry.path(), dir.join(entry.file_name())).unwrap();
    }
    dir
}

#[test]
fn a_run_written_by_the_0_15_0_host_verifies_against_its_record_under_the_current_host() {
    use vv_domain_rocket::Host;
    use vv_platform::host_sdk::{EARLIER_BUILD_AGREEMENT_CHECK, replay, replay_earlier_build};

    let dir = copy_fixture("fixture");
    let record: RunRecord =
        serde_json::from_slice(&fs::read(dir.join("record.json")).unwrap()).unwrap();
    assert_eq!(record.domain.version, "0.15.0");
    assert_eq!(
        record.request.parameters.len(),
        6,
        "the stored request predates later parameters"
    );
    assert_eq!(record.outcome.code, "hard_landing");

    // The strict replay cannot hold across the drift: this is what showed old runs as rejected.
    let strict = replay(&Host, &dir);
    assert_eq!(strict.status, "rejected");
    assert!(
        strict
            .checks
            .iter()
            .any(|c| !c.pass && c.name == "stored request is valid and canonical")
    );

    let report = replay_earlier_build(&Host, &dir);
    assert_eq!(report.status, "verified", "{:?}", failed(&report));
    let note = report
        .checks
        .iter()
        .find(|c| c.name == "stored request is valid and canonical")
        .unwrap();
    assert!(note.detail.starts_with("recorded by domain version 0.15.0; re-simulated with current defaults (parameters added: "), "{}", note.detail);
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.name == EARLIER_BUILD_AGREEMENT_CHECK && c.pass)
    );

    // Tampering with the stored run is still rejected: a telemetry sample, and a native file.
    perturb_first_timebase_value(&dir.join("record.json"));
    let tampered = replay_earlier_build(&Host, &dir);
    assert_eq!(tampered.status, "rejected");
    assert!(
        failed(&tampered).iter().any(|f| f.contains("timebase")),
        "{:?}",
        failed(&tampered)
    );
    let fresh = copy_fixture("fixture-native");
    replace_once(
        &fresh.join("verification.json"),
        "\"requirements_pass\":false",
        "\"requirements_pass\":true",
    );
    let native = replay_earlier_build(&Host, &fresh);
    assert_eq!(native.status, "rejected");
    assert!(
        native
            .checks
            .iter()
            .any(|c| !c.pass && c.name == "stored artifacts match the hashes in record.json")
    );
    for d in [dir, fresh] {
        let _ = fs::remove_dir_all(d);
    }
}
