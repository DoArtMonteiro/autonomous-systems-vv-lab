//! Tests of the rocket domain host: parity of the case with the Python adapter, the seed guard, the
//! fault restriction, the record, determinism, replay and tamper detection.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use vv_domain_rocket::case::{M9, M91, case_bytes, template};
use vv_domain_rocket::catalog::{catalog, request};
use vv_domain_rocket::{Host, manifest};
use vv_platform::contract::*;
use vv_platform::host_sdk::{HostError, execute, hash_artifacts, replay, validate_request};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn temp(label: &str) -> PathBuf {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let dir =
        std::env::temp_dir().join(format!("vv-rocket-test-{}-{label}-{n}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn golden_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("golden")
}

fn fault(kind: &str, magnitude: Option<f64>, start: f64, end: f64) -> FaultRequest {
    FaultRequest {
        kind: kind.into(),
        magnitude,
        start,
        end,
    }
}

fn run_into(request: &RunRequest, dir: &Path) -> RunRecord {
    let normal = validate_request(&Host, request).expect("valid request");
    match execute(&Host, &normal, dir) {
        Ok(record) => record,
        Err(HostError::Invalid(e) | HostError::Simulation(e)) => panic!("run failed: {e}"),
    }
}

#[test]
fn manifest_is_the_shipped_file_and_valid() {
    let m = manifest();
    let file =
        fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("domain.json")).unwrap();
    assert_eq!(m, serde_json::from_str::<DomainManifest>(&file).unwrap());
    vv_platform::discovery::check_manifest(&m).unwrap();
    assert_eq!(m.id, "rocket-landing");
    assert_eq!((m.seeds.min, m.seeds.max), (0, u64::from(u32::MAX)));
    let ranges: Vec<(u64, u64)> = m.seeds.protected.iter().map(|r| (r.start, r.end)).collect();
    assert_eq!(ranges, vec![(3000, 3099), (6000, 6099), (44000, 44999)]);
    assert!(m.seeds.protected.iter().all(|r| !r.reason.is_empty()));
}

#[test]
fn catalog_is_consistent() {
    let c = catalog();
    assert_eq!(c.faults.len(), 10);
    assert_eq!(c.max_faults, 2);
    assert_eq!(c.controllers.len(), 4);
    assert_eq!(c.scenarios.len(), 2);
    for s in &c.scenarios {
        assert!(s.controllers.contains(&s.default_controller));
        for ctl in &s.controllers {
            assert!(c.controllers.iter().any(|i| &i.id == ctl), "{ctl}");
        }
        for p in &s.parameters {
            let spec = c
                .parameters
                .iter()
                .find(|x| &x.id == p)
                .expect("parameter exists");
            assert!(spec.min <= spec.default && spec.default <= spec.max);
            // A default is the value the template really holds.
            let case = template(&s.id).unwrap();
            let path = vv_domain_rocket::case::parameter_path(p).expect("known path");
            let value = path
                .iter()
                .fold(&case, |node, key| &node[*key])
                .as_f64()
                .expect("number");
            assert_eq!(value, spec.default, "{} in {}", p, s.id);
        }
    }
    // Every fault is open to every controller of the catalog.
    for f in &c.faults {
        assert!(f.controllers.is_none(), "{}", f.kind);
        assert!(f.default_start < f.default_end);
    }
}

#[test]
fn golden_cases_match_the_python_adapter() {
    let mut names: Vec<String> = fs::read_dir(golden_dir())
        .unwrap()
        .filter_map(|e| e.ok())
        .filter_map(|e| {
            e.file_name()
                .to_str()
                .and_then(|n| n.strip_suffix(".request.json").map(String::from))
        })
        .collect();
    names.sort();
    assert!(
        names.len() >= 8,
        "at least eight golden requests, found {}",
        names.len()
    );
    for name in names {
        let request: RunRequest = serde_json::from_slice(
            &fs::read(golden_dir().join(format!("{name}.request.json"))).unwrap(),
        )
        .unwrap();
        let normal = validate_request(&Host, &request).unwrap_or_else(|e| panic!("{name}: {e}"));
        let ours = case_bytes(&normal).unwrap();
        let python = fs::read(golden_dir().join(format!("{name}.case.json"))).unwrap();
        assert_eq!(
            String::from_utf8_lossy(&ours),
            String::from_utf8_lossy(&python),
            "{name}"
        );
    }
}

#[test]
fn a_parameter_that_differs_from_its_default_is_applied_and_only_then() {
    let base = request(M9, "robust", 5000, vec![]);
    let default_case = case_bytes(&validate_request(&Host, &base).unwrap()).unwrap();
    let mut tuned = base.clone();
    tuned.parameters.insert("ignition_fraction".into(), 0.6);
    let tuned = validate_request(&Host, &tuned).unwrap();
    let case: serde_json::Value = serde_json::from_slice(&case_bytes(&tuned).unwrap()).unwrap();
    assert_eq!(case["controller"]["gains"]["ignition_fraction"], 0.6);
    assert_ne!(case_bytes(&tuned).unwrap(), default_case);
    // An explicit default is the same request as no parameter.
    let mut explicit = base.clone();
    explicit.parameters.insert("ignition_fraction".into(), 0.75);
    assert_eq!(
        case_bytes(&validate_request(&Host, &explicit).unwrap()).unwrap(),
        default_case
    );
    // The catalog range is enforced, and a parameter of another scenario is refused.
    let mut wild = base.clone();
    wild.parameters.insert("ignition_fraction".into(), 5.0);
    assert!(validate_request(&Host, &wild).is_err());
    let mut other = base;
    other.parameters.insert("not_a_parameter".into(), 12.0);
    assert!(validate_request(&Host, &other).is_err());
}

#[test]
fn protected_seeds_are_refused_by_validate_and_run_and_neighbours_accepted() {
    for seed in [3000, 3099, 6000, 6099] {
        let r = request(M9, "robust", seed, vec![]);
        let e = validate_request(&Host, &r).unwrap_err();
        assert!(e.contains("protected"), "{e}");
        // The host's own check refuses it too, without the generic validation before it.
        use vv_platform::host_sdk::DomainHost;
        assert!(Host.check(r.clone()).is_err());
        // And `run` refuses it when a caller skips validation altogether.
        let dir = temp("protected");
        let normal = RunRequest {
            parameters: Default::default(),
            ..r
        };
        assert!(
            matches!(execute(&Host, &normal, &dir), Err(HostError::Invalid(_))),
            "seed {seed}"
        );
        assert!(
            fs::read_dir(&dir).unwrap().next().is_none(),
            "no artifact for a protected seed"
        );
    }
    for seed in [2999, 3100, 5000, 5999, 6100, u64::from(u32::MAX)] {
        validate_request(&Host, &request(M9, "robust", seed, vec![]))
            .unwrap_or_else(|e| panic!("{seed}: {e}"));
    }
    assert!(
        validate_request(
            &Host,
            &request(M9, "robust", u64::from(u32::MAX) + 1, vec![])
        )
        .is_err()
    );
}

#[test]
fn the_command_line_refuses_a_protected_seed_with_exit_3() {
    let dir = temp("cli");
    let file = dir.join("request.json");
    let r = request(M9, "robust", 3000, vec![]);
    fs::write(&file, serde_json::to_vec(&r).unwrap()).unwrap();
    let exe = env!("CARGO_BIN_EXE_vv-domain-rocket");
    let out = dir.join("out");
    let done = Command::new(exe)
        .args([
            "run",
            file.to_str().unwrap(),
            "--output",
            out.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(done.status.code(), Some(EXIT_INVALID_REQUEST));
    assert!(!out.exists() || fs::read_dir(&out).unwrap().next().is_none());
    let done = Command::new(exe)
        .args(["validate", file.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(done.status.code(), Some(EXIT_INVALID_REQUEST));
    let described = Command::new(exe).arg("describe").output().unwrap();
    assert!(serde_json::from_slice::<DomainCatalog>(&described.stdout).is_ok());
    let manifest_out = Command::new(exe).arg("manifest").output().unwrap();
    assert_eq!(
        serde_json::from_slice::<DomainManifest>(&manifest_out.stdout).unwrap(),
        manifest()
    );
}

#[test]
fn a_fault_or_controller_outside_the_catalog_is_refused() {
    let unknown = vec![fault("not_a_fault", None, 8.0, 12.0)];
    assert!(validate_request(&Host, &request(M9, "robust", 5000, unknown)).is_err());
    assert!(validate_request(&Host, &request(M9, "not_a_controller", 5000, vec![])).is_err());
    // A controller of the other scenario is not available here.
    assert!(validate_request(&Host, &request(M9, "guarded", 5000, vec![])).is_err());
    assert!(validate_request(&Host, &request(M91, "robust", 5000, vec![])).is_err());
}

#[test]
fn fault_rules_of_the_python_adapter_hold() {
    let bad = |faults: Vec<FaultRequest>| {
        validate_request(&Host, &request(M9, "robust", 5000, faults)).unwrap_err()
    };
    assert!(bad(vec![fault("gnss_dropout", None, 8.0, 14.005)]).contains("multiple"));
    assert!(bad(vec![fault("altimeter_bias", Some(10.0), 8.0, 40.5)]).contains("0 to 40"));
    assert!(bad(vec![fault("gnss_dropout", None, 8.0, 8.0)]).contains("window"));
    assert!(bad(vec![fault("gnss_dropout", None, 8.0, 9.0)]).contains("window length"));
    assert!(bad(vec![fault("gnss_dropout", Some(1.0), 8.0, 14.0)]).contains("no magnitude"));
    assert!(bad(vec![fault("altimeter_bias", Some(51.0), 0.0, 40.0)]).contains("magnitude"));
    assert!(
        bad(vec![
            fault("altimeter_bias", Some(10.0), 0.0, 40.0),
            fault("altimeter_bias", Some(10.0), 0.0, 40.0)
        ])
        .contains("repeated")
    );
    assert!(
        bad(vec![
            fault("altimeter_bias", Some(10.0), 0.0, 40.0),
            fault("gnss_bias", Some(10.0), 0.0, 40.0),
            fault("gnss_dropout", None, 8.0, 14.0)
        ])
        .contains("at most 2")
    );
}

#[test]
fn nominal_record_has_a_consistent_shape() {
    let dir = temp("shape");
    let record = run_into(&request(M9, "robust", 5000, vec![]), &dir);
    assert_eq!(record.schema, RECORD_SCHEMA);
    let catalog = catalog();
    for channel in &record.channels {
        let base = &record.timebases[&channel.timebase];
        assert_eq!(channel.values.len(), base.len(), "{}", channel.id);
        assert!(
            [
                "truth",
                "observation",
                "estimate",
                "uncertainty",
                "command",
                "metric",
                "limit"
            ]
            .contains(&channel.kind.as_str())
        );
        let spec = catalog
            .channels
            .iter()
            .find(|c| c.id == channel.id)
            .unwrap_or_else(|| panic!("{} not in the catalog", channel.id));
        assert_eq!(
            (&spec.kind, &spec.unit, &spec.label),
            (&channel.kind, &channel.unit, &channel.label)
        );
        assert!(channel.values.iter().flatten().all(|v| v.is_finite()));
    }
    assert!(record.timebases["trace"].windows(2).all(|w| w[0] < w[1]));
    for id in [
        "R1_vertical_speed",
        "R6_propellant_margin",
        "S1_tilt_envelope",
        "S5_no_powered_ascent",
    ] {
        assert!(record.requirements.iter().any(|r| r.id == id), "{id}");
    }
    assert_eq!(record.requirements.len(), 11);
    for r in &record.requirements {
        assert!(
            catalog
                .requirements
                .iter()
                .any(|c| c.id == r.id && c.category == r.category)
        );
    }
    assert_eq!(record.outcome.code, "landed");
    assert_eq!(record.outcome.status, "success");
    assert_eq!(
        (
            record.safety.status.as_str(),
            record.safety.class.as_deref()
        ),
        ("safe", None)
    );
    for kind in ["ignition", "touchdown"] {
        assert!(record.events.iter().any(|e| e.kind == kind), "{kind}");
    }
    assert!(record.events.windows(2).all(|w| w[0].t <= w[1].t));
    for id in [
        "altitude",
        "obs_altimeter",
        "est_z",
        "err_z",
        "altimeter_rejected",
        "thrust_n",
        "tilt_limit_deg",
    ] {
        assert!(record.channels.iter().any(|c| c.id == id), "{id}");
    }
    assert_eq!(record.scene["kind"], "rocket-3d");
    assert_eq!(record.scene["frame"]["up_axis"], "z");
    assert_eq!(record.provenance.source_sha256, vv_rocket::source_sha256());
    let bytes = fs::metadata(dir.join(RECORD_FILE)).unwrap().len();
    println!("record.json of the nominal M9 run: {bytes} bytes");
    assert!(bytes < 4 * 1024 * 1024, "{bytes}");
    // The native files are those of `vv-rocket land` for the same case and seed.
    let other = temp("native");
    let case = dir.join("case.json");
    vv_rocket::landing_run::write_landing(&case, 5000, &other.join("out")).unwrap();
    for name in ["case.json", "trace.json", "verification.json", "run.json"] {
        assert_eq!(
            fs::read(dir.join(name)).unwrap(),
            fs::read(other.join("out").join(name)).unwrap(),
            "{name}"
        );
    }
}

#[test]
fn a_run_without_sensors_has_no_channel_of_a_sensor_that_never_delivers() {
    let dir = temp("m9");
    let record = run_into(
        &request(
            M9,
            "baseline",
            5000,
            vec![fault("gnss_dropout", None, 8.0, 14.0)],
        ),
        &dir,
    );
    let gnss = record
        .channels
        .iter()
        .find(|c| c.id == "obs_gnss_x")
        .unwrap();
    let t = &record.timebases["trace"];
    let inside: Vec<_> = t
        .iter()
        .zip(&gnss.values)
        .filter(|(t, _)| **t >= 8.0 && **t < 14.0)
        .collect();
    assert!(
        !inside.is_empty() && inside.iter().all(|(_, v)| v.is_none()),
        "no GNSS value in the dropout window"
    );
    assert!(
        record
            .events
            .iter()
            .any(|e| e.kind == "fault_start" && e.source == "fault")
    );
    assert!(
        record
            .requirements
            .iter()
            .all(|r| r.category != "declaration")
    );
}

#[test]
fn two_runs_of_a_request_are_byte_identical() {
    let r = request(
        M91,
        "guarded",
        5000,
        vec![
            fault("altimeter_bias_low", Some(27.5), 10.0, 40.0),
            fault("gnss_dropout", None, 8.0, 14.0),
        ],
    );
    let (a, b) = (temp("det-a"), temp("det-b"));
    run_into(&r, &a);
    run_into(&r, &b);
    assert_eq!(hash_artifacts(&a).unwrap(), hash_artifacts(&b).unwrap());
    assert_eq!(
        fs::read(a.join(RECORD_FILE)).unwrap(),
        fs::read(b.join(RECORD_FILE)).unwrap()
    );
}

#[test]
fn replay_verifies_a_stored_run_and_rejects_a_tampered_artifact() {
    let dir = temp("replay");
    run_into(
        &request(
            M9,
            "robust",
            5000,
            vec![fault("thrust_loss", Some(0.15), 5.26, 40.0)],
        ),
        &dir,
    );
    let report = replay(&Host, &dir);
    assert_eq!(report.status, "verified", "{:?}", report.checks);
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.name.starts_with("vv-rocket replay:"))
    );
    // Tamper with a number in the trace: the hashes, the recomputation and the native replay all object.
    let path = dir.join("trace.json");
    let text = fs::read_to_string(&path).unwrap();
    let tampered = text.replacen("\"propellant_kg\":", "\"propellant_kg\":1", 1);
    assert_ne!(text, tampered);
    fs::write(&path, tampered).unwrap();
    let report = replay(&Host, &dir);
    assert_eq!(report.status, "rejected");
    assert!(report.checks.iter().any(|c| !c.pass));
}

#[test]
fn replay_rejects_a_forged_verdict_in_the_verification() {
    let dir = temp("forged");
    run_into(
        &request(
            M9,
            "baseline",
            5000,
            vec![fault("altimeter_bias", Some(50.0), 0.0, 40.0)],
        ),
        &dir,
    );
    let path = dir.join("verification.json");
    let text = fs::read_to_string(&path).unwrap();
    let forged = text.replacen("\"outcome\":\"hard_landing\"", "\"outcome\":\"landed\"", 1);
    assert_ne!(forged, text);
    fs::write(&path, forged).unwrap();
    assert_eq!(replay(&Host, &dir).status, "rejected");
}
