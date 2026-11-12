//! A run stored by an earlier build of a domain host must not be reported as tampered after an
//! upgrade, and tamper detection must not weaken. The fixture is built, not assumed: a host of
//! version 1.0.0 (one parameter, one outcome text) writes a run; a host of version 2.0.0 (a second
//! parameter with a default, another outcome text, an extra metric) then replays it.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use vv_platform::canonical::pretty_bytes;
use vv_platform::contract::*;
use vv_platform::host_sdk::{
    DomainHost, EARLIER_BUILD_AGREEMENT_CHECK, HostError, execute, replay, replay_earlier_build,
    validate_request,
};

const TRIMMED: &str = include_str!("../../studio/tests/fixtures/rocket-record-trimmed.json");

struct Mock {
    version: &'static str,
    /// Version 2 adds the parameter `threshold` (default 3) and writes another outcome text.
    newer: bool,
}

const OLD: Mock = Mock {
    version: "1.0.0",
    newer: false,
};
const NEW: Mock = Mock {
    version: "2.0.0",
    newer: true,
};

fn parameter(id: &str, default: f64) -> ParameterSpec {
    ParameterSpec {
        id: id.into(),
        label: id.into(),
        description: String::new(),
        unit: "m".into(),
        group: "Test".into(),
        advanced: false,
        min: 0.0,
        max: 10.0,
        step: 0.1,
        default,
        integer: false,
        influences: Vec::new(),
    }
}

impl DomainHost for Mock {
    fn manifest(&self) -> DomainManifest {
        DomainManifest {
            schema: MANIFEST_SCHEMA.into(),
            id: "mock".into(),
            name: "Mock".into(),
            version: self.version.into(),
            description: String::new(),
            contract: ContractVersion {
                name: CONTRACT_NAME.into(),
                major: 1,
                minor: 0,
            },
            host: HostSpec {
                executable: "mock".into(),
                timeout_s: 10,
                max_output_bytes: 1 << 20,
            },
            capabilities: vec!["run".into(), "replay".into()],
            visualisations: Vec::new(),
            seeds: SeedPolicy {
                min: 0,
                max: 10_000,
                protected: Vec::new(),
            },
            model_validity: String::new(),
            user_facing: false,
        }
    }

    fn catalog(&self) -> DomainCatalog {
        let mut parameters = vec![parameter("gain", 2.0)];
        if self.newer {
            parameters.push(parameter("threshold", 3.0));
        }
        DomainCatalog {
            schema: CATALOG_SCHEMA.into(),
            domain: "mock".into(),
            time: TimeSpec {
                unit: "s".into(),
                label: "time".into(),
            },
            vehicles: Vec::new(),
            scenarios: vec![ScenarioSpec {
                id: "s".into(),
                label: "S".into(),
                description: String::new(),
                vehicle: String::new(),
                controllers: vec!["c".into()],
                parameters: parameters.iter().map(|p| p.id.clone()).collect(),
                default_controller: "c".into(),
            }],
            controllers: Vec::new(),
            parameters,
            faults: Vec::new(),
            max_faults: 0,
            channels: Vec::new(),
            requirements: Vec::new(),
            demos: Vec::new(),
        }
    }

    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError> {
        let gain = request.parameters["gain"];
        // The native artifact depends on the request, like a real simulator's trace.
        fs::write(
            out.join("native.json"),
            format!("{{\"seed\":{},\"gain\":{gain}}}", request.seed),
        )
        .map_err(|e| HostError::Simulation(e.to_string()))?;
        let mut r: RunRecord = serde_json::from_str(TRIMMED).unwrap();
        r.domain = DomainRef {
            id: "mock".into(),
            version: self.version.into(),
            contract: "vv-domain/1.0".into(),
        };
        r.request = request.clone();
        r.channels.truncate(1);
        r.channels[0].values = vec![Some(gain * request.seed as f64), Some(1.5)];
        r.timebases.retain(|k, _| *k == r.channels[0].timebase);
        for v in r.timebases.values_mut() {
            *v = vec![0.0, 1.0];
        }
        // A native verification file with verdict flags, like the real simulators write.
        fs::write(
            out.join("verification.json"),
            "{\"requirements_pass\":false,\"invariants_pass\":true,\"requirements\":[{\"id\":\"R1\",\"pass\":false},{\"id\":\"R2\",\"pass\":true}]}",
        )
        .map_err(|e| HostError::Simulation(e.to_string()))?;
        // Two violations of one kind: the stored record keeps knowing the kind when one is deleted.
        r.events = [1.0, 2.0]
            .into_iter()
            .map(|t| Event {
                t,
                kind: "limit_exceeded".into(),
                label: "Limit exceeded".into(),
                severity: "violation".into(),
                source: "verifier".into(),
                detail: Value::Null,
            })
            .collect();
        let requirement = |id: &str, status: &str| RequirementResult {
            id: id.into(),
            label: id.into(),
            category: "requirement".into(),
            status: status.into(),
            expected: "<= 3 m/s".into(),
            observed: "7 m/s".into(),
            t: Some(1.0),
            explanation: String::new(),
        };
        r.requirements = vec![requirement("R1", "fail"), requirement("R2", "pass")];
        r.outcome.label = if self.newer {
            "Reached the ground, requirements not met"
        } else {
            "Touched down, requirements not met"
        }
        .into();
        if self.newer {
            r.metrics.push(Metric {
                id: "extra".into(),
                label: "Extra".into(),
                value: Some(1.0),
                unit: String::new(),
                group: "g".into(),
            });
        }
        Ok(r)
    }
}

static N: AtomicU64 = AtomicU64::new(0);

fn temp(label: &str) -> PathBuf {
    let n = N.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("vv-earlier-{}-{label}-{n}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn request(parameters: &[(&str, f64)]) -> RunRequest {
    RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: "mock".into(),
        scenario: "s".into(),
        controller: "c".into(),
        seed: 7,
        faults: Vec::new(),
        parameters: parameters
            .iter()
            .map(|(k, v)| ((*k).to_string(), *v))
            .collect(),
    }
}

/// A run written by `host`, in a fresh directory.
fn stored_by(host: &Mock, parameters: &[(&str, f64)], label: &str) -> PathBuf {
    let normal = validate_request(host, &request(parameters)).unwrap();
    let dir = temp(label);
    assert!(execute(host, &normal, &dir).is_ok());
    dir
}

fn edit_record(dir: &Path, f: impl FnOnce(&mut Value)) {
    let path = dir.join(RECORD_FILE);
    let mut v: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    f(&mut v);
    fs::write(path, pretty_bytes(&v)).unwrap();
}

fn failed(report: &ReplayReport) -> Vec<&str> {
    report
        .checks
        .iter()
        .filter(|c| !c.pass)
        .map(|c| c.name.as_str())
        .collect()
}

#[test]
fn an_older_run_fails_the_strict_replay_and_passes_the_earlier_build_replay() {
    let dir = stored_by(&OLD, &[("gain", 2.5)], "old");
    // The strict replay cannot hold: the stored request lacks the parameter the new build adds.
    let strict = replay(&NEW, &dir);
    assert_eq!(strict.status, "rejected");
    assert!(failed(&strict).contains(&"stored request is valid and canonical"));
    // The earlier-build replay verifies it and says what it did.
    let report = replay_earlier_build(&NEW, &dir);
    assert_eq!(report.status, "verified", "{:?}", failed(&report));
    let request_check = report
        .checks
        .iter()
        .find(|c| c.name == "stored request is valid and canonical")
        .unwrap();
    assert_eq!(
        request_check.detail,
        "recorded by domain version 1.0.0; re-simulated with current defaults (parameters added: threshold)"
    );
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.name == EARLIER_BUILD_AGREEMENT_CHECK && c.pass)
    );
    // The same build strictly verifies its own run.
    let own = stored_by(&NEW, &[("gain", 2.5)], "new");
    assert_eq!(replay(&NEW, &own).status, "verified");
    for d in [dir, own] {
        let _ = fs::remove_dir_all(d);
    }
}

#[test]
fn an_earlier_build_run_is_still_rejected_when_a_number_a_verdict_or_a_file_changes() {
    let dir = stored_by(&OLD, &[("gain", 2.5)], "tamper");
    let report = replay_earlier_build(&NEW, &dir);
    assert_eq!(report.status, "verified", "{:?}", failed(&report));
    let original = fs::read(dir.join(RECORD_FILE)).unwrap();

    // A telemetry value.
    edit_record(&dir, |v| v["channels"][0]["values"][1] = Value::from(99.0));
    let r = replay_earlier_build(&NEW, &dir);
    assert_eq!(r.status, "rejected");
    assert_eq!(failed(&r), [EARLIER_BUILD_AGREEMENT_CHECK]);
    assert!(
        r.checks.last().unwrap().detail.contains("channel"),
        "{:?}",
        r.checks.last()
    );
    fs::write(dir.join(RECORD_FILE), &original).unwrap();

    // A verdict.
    edit_record(&dir, |v| {
        let status = &mut v["requirements"][0]["status"];
        *status = Value::from(if status == "pass" { "fail" } else { "pass" });
    });
    assert_eq!(replay_earlier_build(&NEW, &dir).status, "rejected");
    fs::write(dir.join(RECORD_FILE), &original).unwrap();

    // The outcome code.
    edit_record(&dir, |v| v["outcome"]["code"] = Value::from("changed_code"));
    assert_eq!(replay_earlier_build(&NEW, &dir).status, "rejected");
    fs::write(dir.join(RECORD_FILE), &original).unwrap();

    // A native artifact.
    fs::write(dir.join("native.json"), "{\"seed\":7,\"gain\":9}").unwrap();
    let r = replay_earlier_build(&NEW, &dir);
    assert_eq!(r.status, "rejected");
    assert!(failed(&r).contains(&"stored artifacts match the hashes in record.json"));
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn a_stored_request_the_current_catalogue_refuses_is_rejected_with_the_reason() {
    // Stored by the newer build with `threshold`; the older catalogue no longer accepts it.
    let dir = stored_by(&NEW, &[("gain", 2.5), ("threshold", 1.0)], "removed");
    let report = replay_earlier_build(&OLD, &dir);
    assert_eq!(report.status, "rejected");
    let check = report.checks.iter().find(|c| !c.pass).unwrap();
    assert!(
        check.detail.contains("refuses the stored request"),
        "{check:?}"
    );
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn same_build_tamper_detection_is_unchanged() {
    let dir = stored_by(&NEW, &[("gain", 2.5)], "same");
    assert_eq!(replay(&NEW, &dir).status, "verified");
    let original = fs::read(dir.join(RECORD_FILE)).unwrap();
    // Text the earlier-build replay ignores is still caught by the strict byte comparison.
    edit_record(&dir, |v| v["outcome"]["label"] = Value::from("Landed"));
    let r = replay(&NEW, &dir);
    assert_eq!(r.status, "rejected");
    assert!(failed(&r).contains(
        &"recomputed record (outcome, requirements, telemetry) equals the stored record"
    ));
    fs::write(dir.join(RECORD_FILE), &original).unwrap();
    edit_record(&dir, |v| v["channels"][0]["values"][1] = Value::from(99.0));
    assert_eq!(replay(&NEW, &dir).status, "rejected");
    let _ = fs::remove_dir_all(dir);
}

fn without_array_item(v: &mut Value, array: &str, index: usize) {
    v[array].as_array_mut().unwrap().remove(index);
}

/// Rewrites a stored native file and the hash that record.json holds for it, as a person editing
/// both would: the integrity check alone then passes.
fn edit_native_and_hash(dir: &Path, file: &str, from: &str, to: &str) {
    let path = dir.join(file);
    let text = fs::read_to_string(&path).unwrap();
    assert!(text.contains(from));
    let edited = text.replace(from, to);
    fs::write(&path, &edited).unwrap();
    edit_record(dir, |v| {
        for a in v["provenance"]["artifacts"].as_array_mut().unwrap() {
            if a["path"] == file {
                a["sha256"] = Value::from(vv_platform::canonical::sha256_hex(edited.as_bytes()));
                a["bytes"] = Value::from(edited.len() as u64);
            }
        }
    });
}

#[test]
fn deleting_a_failed_requirement_or_a_violation_from_an_older_record_is_rejected() {
    let dir = stored_by(&OLD, &[("gain", 2.5)], "delete");
    assert_eq!(replay_earlier_build(&NEW, &dir).status, "verified");
    let original = fs::read(dir.join(RECORD_FILE)).unwrap();

    edit_record(&dir, |v| without_array_item(v, "requirements", 0)); // R1, failed
    let r = replay_earlier_build(&NEW, &dir);
    assert_eq!(r.status, "rejected");
    let detail = &r
        .checks
        .iter()
        .find(|c| c.name == EARLIER_BUILD_AGREEMENT_CHECK)
        .unwrap()
        .detail;
    assert!(
        detail.contains("R1 (fail) is missing from the stored record"),
        "{detail}"
    );
    fs::write(dir.join(RECORD_FILE), &original).unwrap();

    edit_record(&dir, |v| without_array_item(v, "events", 0)); // the violation
    let r = replay_earlier_build(&NEW, &dir);
    assert_eq!(r.status, "rejected");
    let detail = &r
        .checks
        .iter()
        .find(|c| c.name == EARLIER_BUILD_AGREEMENT_CHECK)
        .unwrap()
        .detail;
    assert!(
        detail.contains("violation event limit_exceeded"),
        "{detail}"
    );
    fs::write(dir.join(RECORD_FILE), &original).unwrap();

    // A passing requirement the older build lacked is fine (the current build knows more), but not
    // when the domain version is the same: nothing explains its absence.
    edit_record(&dir, |v| without_array_item(v, "requirements", 1)); // R2, passing
    assert_eq!(
        replay_earlier_build(&NEW, &dir).status,
        "verified",
        "another version may add requirements"
    );
    let _ = fs::remove_dir_all(dir);

    let same = stored_by(&NEW, &[("gain", 2.5)], "delete-same");
    edit_record(&same, |v| without_array_item(v, "requirements", 1));
    let r = replay_earlier_build(&NEW, &same);
    assert_eq!(r.status, "rejected");
    assert!(failed(&r).contains(&EARLIER_BUILD_AGREEMENT_CHECK));
    let _ = fs::remove_dir_all(same);
}

#[test]
fn an_edited_native_verdict_flag_with_its_hash_updated_is_rejected_and_the_limits_are_listed() {
    let dir = stored_by(&OLD, &[("gain", 2.5)], "native-flag");
    let report = replay_earlier_build(&NEW, &dir);
    assert_eq!(report.status, "verified");
    assert!(report.checks.iter().any(|c| c.name
        == "native verification.json flags agree with the recomputation"
        && c.pass));
    let limits = report
        .checks
        .iter()
        .find(|c| c.name == "not compared by the earlier-build replay")
        .unwrap();
    assert!(
        limits.pass
            && limits.detail.contains("texts")
            && limits.detail.contains("native simulator replay")
    );

    edit_native_and_hash(
        &dir,
        "verification.json",
        "\"requirements_pass\":false",
        "\"requirements_pass\":true",
    );
    let r = replay_earlier_build(&NEW, &dir);
    assert_eq!(r.status, "rejected");
    // The hash check passes, as the record was edited too; the recomputation catches the flag.
    assert!(
        r.checks
            .iter()
            .any(|c| c.name == "stored artifacts match the hashes in record.json" && c.pass)
    );
    let flag = r.checks.iter().find(|c| !c.pass).unwrap();
    assert!(flag.detail.contains("requirements_pass"), "{flag:?}");
    let _ = fs::remove_dir_all(dir);
}
