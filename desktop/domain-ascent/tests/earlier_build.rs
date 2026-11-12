//! Upgrade path with the real ascent host: two runs stored by the build at b69cc8e (domain version
//! 0.15.0, before the outcome codes, the upper-stage propellant minimum and the orbit-insertion
//! instant changed) replay under the current host as verified against their own record, with the
//! verdict re-evaluations listed; telemetry tampering, and anything the declared table does not cover,
//! is still rejected.
//!
//! The fixtures are real: each was written by the `vv-domain-ascent run` of that build, for the
//! request in the name (seed 5005 of medium-leo, seed 5035 of small-leo, defaults).

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use vv_domain_ascent::Host;
use vv_platform::contract::*;
use vv_platform::host_sdk::{
    EARLIER_BUILD_AGREEMENT_CHECK, VERDICT_REEVALUATION_CHECK, replay, replay_earlier_build,
};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn copy_fixture(name: &str) -> PathBuf {
    let from = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name);
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("vv-ascent-eb-{}-{n}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        fs::copy(entry.path(), dir.join(entry.file_name())).unwrap();
    }
    dir
}

fn edit_record(dir: &Path, f: impl FnOnce(&mut Value)) {
    let path = dir.join("record.json");
    let mut v: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    f(&mut v);
    fs::write(path, serde_json::to_vec_pretty(&v).unwrap()).unwrap();
}

fn failed(r: &ReplayReport) -> Vec<String> {
    r.checks
        .iter()
        .filter(|c| !c.pass)
        .map(|c| format!("{}: {}", c.name, c.detail))
        .collect()
}

fn re_evaluation(r: &ReplayReport) -> String {
    r.checks
        .iter()
        .find(|c| c.name == VERDICT_REEVALUATION_CHECK)
        .map(|c| c.detail.clone())
        .unwrap_or_default()
}

const MEDIUM: &str = "stored-by-0.15.0-medium-leo-5005";
const SMALL: &str = "stored-by-0.15.0-small-leo-5035";

#[test]
fn an_orbit_judged_success_by_the_older_build_verifies_as_partial_with_the_changes_listed() {
    let dir = copy_fixture(MEDIUM);
    let record: RunRecord =
        serde_json::from_slice(&fs::read(dir.join("record.json")).unwrap()).unwrap();
    assert_eq!(record.domain.version, "0.15.0");
    assert_eq!(
        (record.outcome.code.as_str(), record.outcome.status.as_str()),
        ("orbit", "success")
    );
    // The strict replay cannot hold across the change: this is what showed the run as rejected.
    assert_eq!(replay(&Host, &dir).status, "rejected");

    let report = replay_earlier_build(&Host, &dir);
    assert_eq!(report.status, "verified", "{:?}", failed(&report));
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.name == EARLIER_BUILD_AGREEMENT_CHECK && c.pass)
    );
    let text = re_evaluation(&report);
    for part in [
        "recorded by domain version 0.15.0",
        "outcome orbit (success) is now orbit (partial)",
        "upper.R6_propellant_margin pass is now fail",
        "the minimum residual propellant is 1 % of the upper-stage load",
    ] {
        assert!(text.contains(part), "{part} in {text}");
    }
    // The native verdict flags changed with it and were accepted for the same reason.
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.pass
                && c.name == "native verification.json flags agree with the recomputation")
    );

    // Tampering with what the table does not cover is rejected: a channel, a timebase.
    let tampered = copy_fixture(MEDIUM);
    edit_record(&tampered, |v| {
        let values = v["channels"][0]["values"].as_array_mut().unwrap();
        let first = values.iter_mut().find(|x| x.is_number()).unwrap();
        *first = Value::from(first.as_f64().unwrap() + 1.0);
    });
    let r = replay_earlier_build(&Host, &tampered);
    assert_eq!(r.status, "rejected");
    assert!(
        failed(&r).iter().any(|f| f.contains("channel")),
        "{:?}",
        failed(&r)
    );
    let tampered_tb = copy_fixture(MEDIUM);
    edit_record(&tampered_tb, |v| {
        let tb = v["timebases"].as_object_mut().unwrap();
        let first = tb.values_mut().next().unwrap();
        first[0] = Value::from(first[0].as_f64().unwrap() + 1.0);
    });
    let r = replay_earlier_build(&Host, &tampered_tb);
    assert_eq!(r.status, "rejected");
    assert!(failed(&r).iter().any(|f| f.contains("timebase")));

    // An outcome the table does not declare is rejected, and so is a stored run claiming the
    // current version: the table is for older versions only.
    let other = copy_fixture(MEDIUM);
    edit_record(&other, |v| v["outcome"]["status"] = Value::from("failure"));
    let r = replay_earlier_build(&Host, &other);
    assert_eq!(r.status, "rejected");
    assert!(failed(&r).iter().any(|f| f.contains("outcome orbit")));
    let current = copy_fixture(MEDIUM);
    edit_record(&current, |v| {
        v["domain"]["version"] = Value::from(env!("CARGO_PKG_VERSION"));
    });
    assert_eq!(replay_earlier_build(&Host, &current).status, "rejected");

    // A flipped stored requirement that the table does not allow is rejected: R4 failing.
    let flipped = copy_fixture(MEDIUM);
    edit_record(&flipped, |v| {
        for q in v["requirements"].as_array_mut().unwrap() {
            if q["id"] == "upper.R4_periapsis" {
                q["status"] = Value::from("fail");
            }
        }
    });
    let r = replay_earlier_build(&Host, &flipped);
    assert_eq!(r.status, "rejected");
    assert!(failed(&r).iter().any(|f| f.contains("upper.R4_periapsis")));
    for d in [dir, tampered, tampered_tb, other, current, flipped] {
        let _ = fs::remove_dir_all(d);
    }
}

#[test]
fn a_suborbital_run_of_the_older_build_verifies_as_the_orbit_below_the_minimum_periapsis() {
    let dir = copy_fixture(SMALL);
    let record: RunRecord =
        serde_json::from_slice(&fs::read(dir.join("record.json")).unwrap()).unwrap();
    assert_eq!(
        (record.outcome.code.as_str(), record.outcome.status.as_str()),
        ("suborbital", "failure")
    );
    let report = replay_earlier_build(&Host, &dir);
    assert_eq!(report.status, "verified", "{:?}", failed(&report));
    let text = re_evaluation(&report);
    assert!(
        text.contains("outcome suborbital (failure) is now low_periapsis_orbit (failure)"),
        "{text}"
    );
    // A different new outcome than the one this run now has is not what the stored one becomes.
    let wrong = copy_fixture(SMALL);
    edit_record(&wrong, |v| {
        v["outcome"]["code"] = Value::from("orbit");
        v["outcome"]["status"] = Value::from("success");
    });
    assert_eq!(replay_earlier_build(&Host, &wrong).status, "rejected");
    for d in [dir, wrong] {
        let _ = fs::remove_dir_all(d);
    }
}
