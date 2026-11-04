//! End-to-end tests of the ground-vehicle domain host. They start the compiled host like the
//! platform does and need the real simulator:
//!
//!     cargo build --release                   (repository root; writes target/release/vv-lab[.exe])
//!     cargo test -p vv-domain-ground          (from desktop/)
//!
//! The simulator is found at ../../target/release/vv-lab[.exe] relative to this crate and handed to the
//! host through VV_LAB_BINARY. The golden fixtures come from the Python adapter
//! (tests/golden_ground.py); regenerate them after a change of the simulator sources.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use vv_platform::canonical::sha256_hex;
use vv_platform::contract::*;

const HOST: &str = env!("CARGO_BIN_EXE_vv-domain-ground");
const NATIVE: [&str; 5] = [
    "events.json",
    "report.json",
    "mission.json",
    "verification.json",
    "m4.json",
];

fn crate_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn lab_binary() -> PathBuf {
    let name = if cfg!(windows) {
        "vv-lab.exe"
    } else {
        "vv-lab"
    };
    let path = crate_dir().join("../../target/release").join(name);
    assert!(
        path.is_file(),
        "{} is missing: run `cargo build --release` at the repository root first",
        path.display()
    );
    path
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

struct Scratch(PathBuf);

impl Scratch {
    fn new() -> Self {
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!("vv-ground-test-{}-{n}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        Scratch(dir)
    }

    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn host(args: &[&Path]) -> Output {
    Command::new(HOST)
        .args(args)
        .env("VV_LAB_BINARY", lab_binary())
        .output()
        .expect("host starts")
}

fn arg(s: &str) -> PathBuf {
    PathBuf::from(s)
}

fn code(out: &Output) -> i32 {
    out.status.code().expect("exit code")
}

fn stderr(out: &Output) -> String {
    String::from_utf8_lossy(&out.stderr).into_owned()
}

fn write_request(dir: &Scratch, name: &str, request: &RunRequest) -> PathBuf {
    let path = dir.path(name);
    fs::write(&path, serde_json::to_vec(request).unwrap()).unwrap();
    path
}

fn validate(request: &RunRequest) -> Output {
    let dir = Scratch::new();
    let file = write_request(&dir, "request.json", request);
    host(&[&arg("validate"), &file])
}

/// Runs a request into `<scratch>/<name>` and returns its directory and record.
fn run(dir: &Scratch, name: &str, request: &RunRequest) -> (PathBuf, RunRecord) {
    let file = write_request(dir, &format!("{name}.request.json"), request);
    let out = dir.path(name);
    let done = host(&[&arg("run"), &file, &arg("--output"), &out]);
    assert_eq!(code(&done), 0, "run failed: {}", stderr(&done));
    let record =
        serde_json::from_slice(&fs::read(out.join("record.json")).unwrap()).expect("record parses");
    (out, record)
}

fn request(scenario: &str, controller: &str, seed: u64, faults: Vec<FaultRequest>) -> RunRequest {
    RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: "ground-vehicle".into(),
        scenario: scenario.into(),
        controller: controller.into(),
        seed,
        faults,
        parameters: Default::default(),
    }
}

fn fault(kind: &str, magnitude: Option<f64>, start: f64, end: f64) -> FaultRequest {
    FaultRequest {
        kind: kind.into(),
        magnitude,
        start,
        end,
    }
}

fn catalog() -> DomainCatalog {
    let done = host(&[&arg("describe")]);
    assert_eq!(code(&done), 0);
    serde_json::from_slice(&done.stdout).expect("catalog parses")
}

fn status(record: &RunRecord, id: &str) -> (String, Option<f64>) {
    let r = record
        .requirements
        .iter()
        .find(|r| r.id == id)
        .unwrap_or_else(|| panic!("no requirement {id}"));
    (r.status.clone(), r.t)
}

// ------------------------------------------------------------------ golden parity with the Python adapter

#[test]
fn inputs_and_native_outputs_equal_the_python_adapter() {
    let golden = crate_dir().join("tests/golden");
    let names: Vec<String> =
        serde_json::from_slice(&fs::read(golden.join("cases.json")).unwrap()).unwrap();
    assert!(names.len() >= 6, "at least 6 golden cases");
    let mut covered = std::collections::BTreeSet::new();
    let dir = Scratch::new();
    for name in &names {
        let case = golden.join(name);
        let req: RunRequest =
            serde_json::from_slice(&fs::read(case.join("request.json")).unwrap()).unwrap();
        covered.insert(req.scenario.clone());
        covered.insert(req.controller.clone());
        covered.extend(req.faults.iter().map(|f| f.kind.clone()));
        let (out, _) = run(&dir, name, &req);
        for file in ["scenario.json", "actuator.json", "contracts.json"] {
            let want = fs::read(case.join("inputs").join(file)).unwrap();
            let got = fs::read(out.join("inputs").join(file)).unwrap();
            assert_eq!(
                got, want,
                "{name}: inputs/{file} differs from the Python adapter"
            );
        }
        let native: Value =
            serde_json::from_slice(&fs::read(case.join("native.json")).unwrap()).unwrap();
        for file in NATIVE {
            let got = sha256_hex(&fs::read(out.join("native").join(file)).unwrap());
            assert_eq!(
                Some(got.as_str()),
                native[file].as_str(),
                "{name}: native/{file} differs from the Python adapter run with the same vv-lab"
            );
        }
    }
    for needed in [
        "nominal_stop",
        "x_first_overshoot",
        "delayed_after_fallback",
        "dominant_axis",
        "x_first",
        "gps_dropout",
        "continued_movement",
        "delayed_movement",
        "lost_movement",
    ] {
        assert!(
            covered.contains(needed),
            "golden cases do not cover {needed}"
        );
    }
}

// ------------------------------------------------------------------ determinism, replay, tampering

fn files_of(dir: &Path) -> Vec<(String, Vec<u8>)> {
    fn walk(root: &Path, dir: &Path, out: &mut Vec<(String, Vec<u8>)>) {
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                walk(root, &path, out);
            } else {
                let rel = path
                    .strip_prefix(root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                out.push((rel, fs::read(&path).unwrap()));
            }
        }
    }
    let mut out = Vec::new();
    walk(dir, dir, &mut out);
    out.sort();
    out
}

#[test]
fn equal_requests_give_equal_runs() {
    let dir = Scratch::new();
    let req = request(
        "delayed_after_fallback",
        "dominant_axis",
        42,
        vec![fault("gps_dropout", None, 2.0, 5.0)],
    );
    let (a, _) = run(&dir, "a", &req);
    let (b, _) = run(&dir, "b", &req);
    assert_eq!(files_of(&a), files_of(&b));
}

fn replay(dir: &Path) -> (i32, ReplayReport) {
    let done = host(&[&arg("replay"), dir]);
    let report = serde_json::from_slice(&done.stdout).expect("replay report parses");
    (code(&done), report)
}

#[test]
fn replay_recomputes_and_verifies_a_stored_run() {
    let dir = Scratch::new();
    let req = request("delayed_after_fallback", "dominant_axis", 42, vec![]);
    let (out, _) = run(&dir, "run", &req);
    let (exit, report) = replay(&out);
    assert_eq!(
        (exit, report.status.as_str()),
        (0, "verified"),
        "{report:?}"
    );
    assert!(report.checks.iter().all(|c| c.pass));
    assert!(
        report
            .checks
            .iter()
            .any(|c| c.name.contains("replay-m4") && c.detail.contains("M4 replay verified")),
        "the simulator's own replay is part of the report"
    );
}

#[test]
fn a_tampered_artifact_is_rejected() {
    for file in [
        "native/mission.json",
        "native/events.json",
        "inputs/scenario.json",
    ] {
        let dir = Scratch::new();
        let (out, _) = run(
            &dir,
            "run",
            &request("nominal_stop", "dominant_axis", 42, vec![]),
        );
        let path = out.join(file);
        let mut bytes = fs::read(&path).unwrap();
        bytes.push(b' ');
        fs::write(&path, bytes).unwrap();
        let (exit, report) = replay(&out);
        assert_eq!((exit, report.status.as_str()), (1, "rejected"), "{file}");
        assert!(report.checks.iter().any(|c| !c.pass), "{file}");
    }
}

#[test]
fn a_tampered_native_manifest_is_rejected_by_the_simulator_replay() {
    let dir = Scratch::new();
    let (out, _) = run(
        &dir,
        "run",
        &request("nominal_stop", "dominant_axis", 42, vec![]),
    );
    let path = out.join("native/mission.json");
    let text = fs::read_to_string(&path)
        .unwrap()
        .replace("\"completed\"", "\"incomplete\"");
    fs::write(&path, text).unwrap();
    let (exit, report) = replay(&out);
    assert_eq!(exit, 1);
    let native = report
        .checks
        .iter()
        .find(|c| c.name.contains("replay-m4"))
        .unwrap();
    assert!(!native.pass, "{native:?}");
}

#[test]
fn the_host_refuses_to_run_without_the_simulator() {
    let dir = Scratch::new();
    let file = write_request(
        &dir,
        "r.json",
        &request("nominal_stop", "dominant_axis", 42, vec![]),
    );
    let done = Command::new(HOST)
        .args([arg("run"), file, arg("--output"), dir.path("o")])
        .env_remove("VV_LAB_BINARY")
        .output()
        .unwrap();
    assert_eq!(code(&done), EXIT_SIMULATION_ERROR);
    assert!(stderr(&done).contains("vv-lab"), "{}", stderr(&done));
}

// ------------------------------------------------------------------ requests

#[test]
fn invalid_requests_are_refused_with_a_reason() {
    let base = || request("nominal_stop", "dominant_axis", 42, vec![]);
    let with = |faults: Vec<FaultRequest>| RunRequest { faults, ..base() };
    let cases: Vec<(&str, RunRequest, &str)> = vec![
        (
            "unknown mission",
            request("moon_walk", "dominant_axis", 42, vec![]),
            "unknown scenario",
        ),
        (
            "unknown controller",
            request("nominal_stop", "wander", 42, vec![]),
            "controller",
        ),
        (
            "two actuator faults",
            with(vec![
                fault("lost_movement", None, 2.0, 3.0),
                fault("continued_movement", None, 5.0, 6.0),
            ]),
            "at most one actuator fault",
        ),
        (
            "window past the horizon",
            with(vec![fault("gps_dropout", None, 10.0, 17.0)]),
            "ticks 1 to 16",
        ),
        (
            "window starting at tick 0",
            with(vec![fault("gps_dropout", None, 0.0, 3.0)]),
            "ticks 1 to 16",
        ),
        (
            "window ending before it starts",
            with(vec![fault("lost_movement", None, 5.0, 3.0)]),
            "window",
        ),
        (
            "fractional tick",
            with(vec![fault("gps_dropout", None, 2.5, 4.0)]),
            "whole number",
        ),
        (
            "delay longer than the mission",
            with(vec![fault("delayed_movement", Some(17.0), 2.0, 2.0)]),
            "delay",
        ),
        (
            "magnitude on a fault without one",
            with(vec![fault("lost_movement", Some(2.0), 2.0, 3.0)]),
            "no magnitude",
        ),
        (
            "a fault of another domain",
            with(vec![fault("thruster_out", None, 2.0, 3.0)]),
            "unknown fault kind",
        ),
        (
            "repeated fault kind",
            with(vec![
                fault("gps_dropout", None, 2.0, 3.0),
                fault("gps_dropout", None, 5.0, 6.0),
            ]),
            "repeated",
        ),
        (
            "seed above the range",
            RunRequest {
                seed: 1 << 63,
                ..base()
            },
            "outside the range",
        ),
        (
            "unknown parameter",
            RunRequest {
                parameters: [("thrust".to_owned(), 1.0)].into(),
                ..base()
            },
            "not accepted",
        ),
        (
            "clear_builtin_faults on a mission without built-in faults",
            RunRequest {
                parameters: [("clear_builtin_faults".to_owned(), 1.0)].into(),
                ..base()
            },
            "not accepted",
        ),
        (
            "stall window out of range",
            RunRequest {
                parameters: [("stall_window_ticks".to_owned(), 0.0)].into(),
                ..base()
            },
            "stall_window_ticks",
        ),
    ];
    for (name, req, reason) in cases {
        let done = validate(&req);
        assert_eq!(code(&done), EXIT_INVALID_REQUEST, "{name} must be refused");
        assert!(stderr(&done).contains(reason), "{name}: {}", stderr(&done));
    }
}

#[test]
fn held_out_seeds_of_the_m6_experiment_are_protected() {
    let accepted = |seed| {
        code(&validate(&request(
            "nominal_stop",
            "dominant_axis",
            seed,
            vec![],
        )))
    };
    for seed in [101, 105, 112] {
        assert_eq!(accepted(seed), EXIT_INVALID_REQUEST, "seed {seed}");
    }
    for seed in [0, 42, 100, 113, 1337, 2026, (1u64 << 63) - 1] {
        assert_eq!(accepted(seed), 0, "seed {seed}");
    }
    // The protected range is the held-out list of the experiment file, not a guess.
    let experiment: Value = serde_json::from_slice(
        &fs::read(crate_dir().join("../../scenarios/m6/experiment.json")).unwrap(),
    )
    .unwrap();
    let held: Vec<u64> = experiment["heldout_seeds"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap())
        .collect();
    let manifest: DomainManifest =
        serde_json::from_slice(&fs::read(crate_dir().join("domain.json")).unwrap()).unwrap();
    let range = &manifest.seeds.protected[0];
    // The second range is the confirmation reserve, checked by the_confirmation_reserve_is_refused.
    assert_eq!(manifest.seeds.protected.len(), 2);
    assert_eq!(
        (
            manifest.seeds.protected[1].start,
            manifest.seeds.protected[1].end
        ),
        (44_000, 44_999)
    );
    assert_eq!(held, (range.start..=range.end).collect::<Vec<_>>());
}

#[test]
fn faults_are_put_in_catalog_order() {
    let req = request(
        "nominal_stop",
        "dominant_axis",
        42,
        vec![
            fault("lost_movement", None, 2.0, 3.0),
            fault("gps_dropout", None, 5.0, 6.0),
        ],
    );
    let dir = Scratch::new();
    let file = write_request(&dir, "r.json", &req);
    let done = host(&[&arg("validate"), &file]);
    assert_eq!(code(&done), 0, "{}", stderr(&done));
    let normal: RunRequest = serde_json::from_slice(&done.stdout).unwrap();
    let kinds: Vec<&str> = normal.faults.iter().map(|f| f.kind.as_str()).collect();
    assert_eq!(kinds, ["gps_dropout", "lost_movement"]);
    assert_eq!(normal.parameters["stall_window_ticks"], 8.0);
}

// ------------------------------------------------------------------ catalog and record shape

#[test]
fn the_manifest_and_catalog_are_consistent() {
    let done = host(&[&arg("manifest")]);
    let manifest: DomainManifest = serde_json::from_slice(&done.stdout).unwrap();
    let on_disk: DomainManifest =
        serde_json::from_slice(&fs::read(crate_dir().join("domain.json")).unwrap()).unwrap();
    assert_eq!(manifest, on_disk);
    assert_eq!(manifest.id, "ground-vehicle");
    assert_eq!(manifest.seeds.max, (1u64 << 63) - 1);

    let c = catalog();
    assert_eq!(c.time.unit, "tick");
    assert_eq!(c.max_faults, 2);
    assert_eq!(c.scenarios.len(), 4);
    for s in &c.scenarios {
        assert!(s.controllers.contains(&s.default_controller));
        for p in &s.parameters {
            assert!(c.parameters.iter().any(|spec| &spec.id == p), "{p}");
        }
    }
    let kinds: Vec<&str> = c.faults.iter().map(|f| f.kind.as_str()).collect();
    assert_eq!(
        kinds,
        [
            "gps_dropout",
            "continued_movement",
            "delayed_movement",
            "lost_movement"
        ]
    );
    for f in &c.faults {
        assert_eq!(
            f.target,
            if f.kind == "gps_dropout" {
                "sensor"
            } else {
                "actuator"
            }
        );
        assert_eq!(f.magnitude.is_some(), f.kind == "delayed_movement");
    }
    // Defaults must be accepted by the host and equal the simulator defaults.
    for p in &c.parameters {
        assert!(p.min <= p.default && p.default <= p.max, "{}", p.id);
    }
}

#[test]
fn a_record_matches_the_catalog() {
    let c = catalog();
    let dir = Scratch::new();
    let (_, record) = run(
        &dir,
        "run",
        &request("delayed_after_fallback", "dominant_axis", 42, vec![]),
    );
    assert_eq!(record.domain.id, "ground-vehicle");
    let channel_ids: Vec<&str> = record.channels.iter().map(|ch| ch.id.as_str()).collect();
    let catalog_ids: Vec<&str> = c.channels.iter().map(|ch| ch.id.as_str()).collect();
    assert_eq!(channel_ids, catalog_ids);
    let ticks = record.timebases["tick"].len();
    assert_eq!(ticks, 15);
    assert!(
        record
            .channels
            .iter()
            .all(|ch| ch.values.len() == ticks && ch.timebase == "tick")
    );
    let requirement_ids: Vec<&str> = record.requirements.iter().map(|r| r.id.as_str()).collect();
    let catalog_requirements: Vec<&str> = c.requirements.iter().map(|r| r.id.as_str()).collect();
    assert_eq!(requirement_ids, catalog_requirements);
    for r in &record.requirements {
        let spec = c.requirements.iter().find(|s| s.id == r.id).unwrap();
        assert_eq!(r.category, spec.category);
    }
    assert_eq!(record.scene["kind"], "ground-2d");
    assert_eq!(record.scene["units"], "mm");
    // GPS dropout is a gap in the observation, not a zero.
    let gps = record
        .channels
        .iter()
        .find(|ch| ch.id == "gps_x_mm")
        .unwrap();
    assert_eq!(gps.values[4..=10], [None; 7]);
    assert!(gps.values[3].is_some() && gps.values[11].is_some());
    assert!(record.events.windows(2).all(|w| w[0].t <= w[1].t));
    assert_eq!(record.provenance.simulator, "vv-lab");
    assert_eq!(record.provenance.source_sha256.len(), 64);
    assert!(
        record
            .provenance
            .artifacts
            .iter()
            .any(|a| a.path == "native/m4.json")
    );
    println!(
        "record.json is {} bytes",
        serde_json::to_vec_pretty(&record).unwrap().len()
    );
}

#[test]
fn the_seed_does_not_change_these_missions() {
    let dir = Scratch::new();
    let (_, a) = run(
        &dir,
        "a",
        &request("nominal_stop", "dominant_axis", 42, vec![]),
    );
    let (_, b) = run(
        &dir,
        "b",
        &request("nominal_stop", "dominant_axis", 4242, vec![]),
    );
    assert_eq!(a.channels, b.channels);
    assert_eq!(a.requirements, b.requirements);
    assert_eq!(a.outcome, b.outcome);
    assert_ne!(a.request, b.request);
}

#[test]
fn mission_policy_parameters_reach_the_simulator() {
    let dir = Scratch::new();
    let mut req = request("x_first_overshoot", "x_first", 42, vec![]);
    let (_, default) = run(&dir, "default", &req);
    assert_eq!(default.outcome.code, "stalled");
    req.parameters.insert("stall_window_ticks".into(), 20.0);
    let (out, patient) = run(&dir, "patient", &req);
    assert_eq!(patient.outcome.code, "incomplete");
    assert_eq!(patient.outcome.status, "partial");
    let mission: Value =
        serde_json::from_slice(&fs::read(out.join("native/mission.json")).unwrap()).unwrap();
    assert_eq!(mission["policy"]["stall_window_ticks"], 20);
    assert!(patient.provenance.reproduce[0].contains("--stall-window-ticks 20"));
    assert!(!default.provenance.reproduce[0].contains("--stall-window-ticks"));
}

// ------------------------------------------------------------------ demos

fn demo(id: &str) -> Demo {
    catalog()
        .demos
        .into_iter()
        .find(|d| d.id == id)
        .unwrap_or_else(|| panic!("no demo {id}"))
}

fn run_demo(id: &str) -> Vec<RunRecord> {
    let dir = Scratch::new();
    let d = demo(id);
    assert!(!d.expectation.is_empty() && !d.narrative.is_empty());
    d.requests
        .iter()
        .enumerate()
        .map(|(i, req)| {
            let done = validate(req);
            assert_eq!(code(&done), 0, "{id}: {}", stderr(&done));
            let normal: RunRequest = serde_json::from_slice(&done.stdout).unwrap();
            assert_eq!(&normal.faults, &req.faults);
            let (out, record) = run(&dir, &format!("r{i}"), &normal);
            let (exit, report) = replay(&out);
            assert_eq!(
                (exit, report.status.as_str()),
                (0, "verified"),
                "{id} request {i}"
            );
            record
        })
        .collect()
}

#[test]
fn every_demo_validates_and_replays() {
    for d in catalog().demos {
        run_demo(&d.id);
    }
}

#[test]
fn demo_nominal_drive_completes_and_everything_passes() {
    let r = &run_demo("nominal-drive")[0];
    assert_eq!(
        (r.outcome.code.as_str(), r.outcome.status.as_str()),
        ("completed", "success")
    );
    assert_eq!(r.safety.status, "safe");
    assert_eq!(r.requirements.len(), 12);
    assert!(
        r.requirements.iter().all(|q| q.status == "pass"),
        "{:?}",
        r.requirements
    );
    assert!(
        r.events
            .iter()
            .any(|e| e.kind == "goal_reached" && e.t == 7.0)
    );
}

#[test]
fn demo_axis_policy_comparison_separates_mission_result_from_safety() {
    let runs = run_demo("axis-policy-comparison");
    let (dominant, x_first) = (&runs[0], &runs[1]);
    assert_eq!(dominant.request.controller, "dominant_axis");
    assert_eq!(dominant.outcome.code, "completed");
    assert_eq!(dominant.safety.status, "safe");
    assert!(dominant.requirements.iter().all(|q| q.status == "pass"));
    assert_eq!(
        (
            x_first.outcome.code.as_str(),
            x_first.outcome.status.as_str()
        ),
        ("stalled", "failure")
    );
    assert_eq!(
        x_first.safety.status, "safe",
        "a stalled mission is not an unsafe one"
    );
    assert_eq!(
        status(x_first, "mission_completion"),
        ("fail".into(), Some(8.0))
    );
    assert_eq!(status(x_first, "mission_lifecycle").0, "not_evaluated");
    assert!(
        x_first
            .requirements
            .iter()
            .filter(|q| q.category == "invariant")
            .all(|q| q.status == "pass")
    );
    assert!(
        x_first
            .events
            .iter()
            .any(|e| e.kind == "mission_stalled" && e.t == 8.0)
    );
    let goal = x_first
        .channels
        .iter()
        .find(|c| c.id == "goal_distance_mm")
        .unwrap();
    assert!(
        goal.values.iter().all(|v| *v == Some(2250.0)),
        "x_first never gets closer"
    );
}

#[test]
fn demo_delayed_command_after_fallback_violates_and_the_clean_run_does_not() {
    let runs = run_demo("delayed-command-after-fallback");
    let (faulty, clean) = (&runs[0], &runs[1]);
    assert_eq!(faulty.outcome.code, "incomplete");
    assert_eq!(faulty.safety.status, "unsafe");
    assert_eq!(status(faulty, "safe_fallback"), ("fail".into(), Some(7.0)));
    assert_eq!(
        status(faulty, "command_resolution"),
        ("fail".into(), Some(6.0))
    );
    assert_eq!(
        status(faulty, "command_applied"),
        ("fail".into(), Some(6.0))
    );
    assert_eq!(
        status(faulty, "no_motion_in_fallback"),
        ("fail".into(), Some(7.0))
    );
    assert_eq!(status(faulty, "fallback_response").0, "pass");
    assert_eq!(status(faulty, "stop_response").0, "pass");
    let failures = faulty
        .requirements
        .iter()
        .filter(|q| q.status == "fail")
        .count();
    assert_eq!(
        failures, 5,
        "four violations plus the mission that did not complete"
    );
    // The explanation is in the data: the delayed command, the fallback entry and the motion at tick 7.
    let kinds: Vec<(f64, &str)> = faulty
        .events
        .iter()
        .map(|e| (e.t, e.kind.as_str()))
        .collect();
    assert!(kinds.contains(&(4.0, "actuator_command_delayed")));
    assert!(kinds.contains(&(6.0, "safety_transition")));
    assert!(kinds.contains(&(7.0, "actuator_delayed_command_executed")));
    let moved = faulty.channels.iter().find(|c| c.id == "moved_mm").unwrap();
    let fallback = faulty.channels.iter().find(|c| c.id == "fallback").unwrap();
    assert_eq!(
        (moved.values[7], fallback.values[7]),
        (Some(250.0), Some(1.0))
    );

    assert_eq!(clean.outcome.code, "incomplete");
    assert_eq!(clean.safety.status, "safe");
    let failed: Vec<&str> = clean
        .requirements
        .iter()
        .filter(|q| q.status == "fail")
        .map(|q| q.id.as_str())
        .collect();
    assert_eq!(failed, ["mission_completion"]);
    assert_eq!(status(clean, "mission_lifecycle").0, "not_evaluated");
    let fallback = clean.channels.iter().find(|c| c.id == "fallback").unwrap();
    assert!(fallback.values[1..].iter().all(|v| *v == Some(0.0)));
}

#[test]
fn a_native_manifest_with_a_protected_seed_never_reaches_the_simulator() {
    let dir = Scratch::new();
    let (out, _) = run(
        &dir,
        "run",
        &request("nominal_stop", "dominant_axis", 42, vec![]),
    );
    let path = out.join("native/m4.json");
    let text = fs::read_to_string(&path)
        .unwrap()
        .replace("\"seed\":42", "\"seed\":101");
    assert!(text.contains("\"seed\":101"));
    fs::write(&path, text).unwrap();
    let (exit, report) = replay(&out);
    assert_eq!((exit, report.status.as_str()), (1, "rejected"));
    let seed = report
        .checks
        .iter()
        .find(|c| c.name == "the native run uses the seed of the stored request")
        .unwrap();
    assert!(!seed.pass && seed.detail.contains("101"), "{seed:?}");
    assert!(
        !report.checks.iter().any(|c| c.name.contains("replay-m4")),
        "the simulator replay must not run"
    );
}

#[test]
fn demo_corridor_gps_noise_enters_the_zone_only_without_an_arrival_radius() {
    let runs = run_demo("corridor-gps-noise");
    let failed = |r: &RunRecord| -> Vec<String> {
        r.requirements
            .iter()
            .filter(|q| q.status == "fail")
            .map(|q| q.id.clone())
            .collect()
    };
    assert_eq!(
        (
            runs[0].outcome.code.as_str(),
            runs[0].safety.status.as_str()
        ),
        ("completed", "safe")
    );
    assert!(failed(&runs[0]).is_empty());
    assert_eq!(
        (
            runs[1].outcome.code.as_str(),
            runs[1].safety.status.as_str()
        ),
        ("incomplete", "unsafe")
    );
    assert_eq!(
        status(&runs[1], "restricted_zone"),
        ("fail".into(), Some(21.0))
    );
    assert_eq!(
        (
            runs[2].outcome.code.as_str(),
            runs[2].safety.status.as_str()
        ),
        ("completed", "safe")
    );
    assert!(failed(&runs[2]).is_empty());
}

#[test]
fn the_confirmation_reserve_is_refused() {
    for seed in [44_000u64, 44_500, 44_999] {
        let r = request("nominal_stop", "dominant_axis", seed, vec![]);
        assert_eq!(code(&validate(&r)), EXIT_INVALID_REQUEST, "seed {seed}");
    }
    for seed in [43_999u64, 45_000] {
        let r = request("nominal_stop", "dominant_axis", seed, vec![]);
        assert_eq!(code(&validate(&r)), 0, "seed {seed}");
    }
}
