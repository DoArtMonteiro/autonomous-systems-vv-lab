//! Integration tests of the engine on development seeds only (5000 and up, 7000 and up). Every
//! output goes under Cargo's per-target temporary directory, inside `exec/target`.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::AtomicBool;

use serde_json::{Value, json};
use vv_exec::engine::{self, Options};
use vv_exec::equiv;
use vv_exec::plan::Plan;
use vv_exec::report;
use vv_exec::sched::ScriptedProbe;

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}

fn landing(name: &str) -> PathBuf {
    repo().join("crates/vv-rocket/landing").join(name)
}

/// A fresh, empty directory for one test.
fn scratch(name: &str) -> PathBuf {
    let d = Path::new(env!("CARGO_TARGET_TMPDIR")).join(name);
    if d.exists() {
        fs::remove_dir_all(&d).unwrap();
    }
    fs::create_dir_all(&d).unwrap();
    d
}

fn spec(base: &Path, extra: Value) -> Vec<u8> {
    let mut v = json!({
        "schema": "vv-experiment.v1",
        "id": "integration",
        "domain": "rocket-landing",
        "base_case": base.display().to_string(),
        "design": {"kind": "single"},
        "seeds": {"mode": "range", "first": 5000, "count": 6},
        "retention": {"policy": "sample", "sample_every": 3},
        "limits": {"max_runs": 10000, "max_retained": 50, "max_artifact_bytes": 100000000, "max_wall_s": 600}
    });
    if let (Value::Object(m), Value::Object(e)) = (&mut v, extra) {
        m.extend(e);
    }
    serde_json::to_vec_pretty(&v).unwrap()
}

fn plan(bytes: &[u8]) -> Result<Plan, String> {
    Plan::build(bytes, Path::new("."))
}

fn opts<'a>(
    probe: &'a ScriptedProbe,
    cancel: &'a AtomicBool,
    threads: usize,
    stop_after: Option<u64>,
) -> Options<'a> {
    Options {
        probe,
        max_threads: Some(threads),
        cancel,
        stop_after,
        probe_every: 1,
    }
}

fn plenty() -> ScriptedProbe {
    ScriptedProbe::new(vec![Some(64_000)])
}

fn records_bytes(dir: &Path) -> Vec<u8> {
    fs::read(dir.join("records.jsonl")).unwrap()
}

#[test]
fn records_are_identical_for_any_worker_count_and_match_the_canonical_library() {
    let s = spec(&landing("m10-nominal.json"), json!({}));
    let p = plan(&s).unwrap();
    let cancel = AtomicBool::new(false);
    let probe = plenty();
    let one = scratch("workers-1");
    let eight = scratch("workers-8");
    let a = engine::execute(&p, &one, &opts(&probe, &cancel, 1, None)).unwrap();
    let b = engine::execute(&p, &eight, &opts(&probe, &cancel, 8, None)).unwrap();
    assert!(a.complete && b.complete);
    assert_eq!(records_bytes(&one), records_bytes(&eight));
    let recs = engine::read_records(&p, &one).unwrap();
    let case = fs::read(landing("m10-nominal.json")).unwrap();
    for r in &recs {
        let art = vv_rocket::landing_run::artifacts(&case, r.seed).unwrap();
        assert_eq!(
            r.trace_sha256.as_deref(),
            Some(vv_rocket::sha256_hex(&art.trace).as_str())
        );
        assert_eq!(r.case_sha256, vv_rocket::sha256_hex(&case));
        engine::recompute(&p, r).unwrap();
    }
    // Retention writes the canonical files: same bytes as write_landing called directly.
    let kept = engine::retain(&p, &one, &recs).unwrap();
    assert_eq!(kept.retained.len(), 2);
    let direct = scratch("direct-write");
    vv_rocket::landing_run::write_landing(&landing("m10-nominal.json"), 5003, &direct).unwrap();
    for f in ["case.json", "trace.json", "verification.json", "run.json"] {
        assert_eq!(
            fs::read(one.join("retained/00000003-s5003").join(f)).unwrap(),
            fs::read(direct.join(f)).unwrap(),
            "{f}"
        );
    }
}

#[test]
fn an_interrupted_run_resumes_to_the_same_records() {
    let s = spec(&landing("m10-nominal.json"), json!({}));
    let p = plan(&s).unwrap();
    let cancel = AtomicBool::new(false);
    let probe = plenty();
    let full = scratch("resume-full");
    engine::execute(&p, &full, &opts(&probe, &cancel, 4, None)).unwrap();

    let part = scratch("resume-part");
    let first = engine::execute(&p, &part, &opts(&probe, &cancel, 1, Some(2))).unwrap();
    assert!(!first.complete);
    assert_eq!(first.executed, 2);
    assert!(!part.join("records.jsonl").exists());
    // A torn last line, as a crash mid-write leaves it, is dropped and re-run.
    let mut log = fs::read(part.join("log.jsonl")).unwrap();
    log.extend_from_slice(b"0123abc {\"index\":");
    fs::write(part.join("log.jsonl"), log).unwrap();
    let second = engine::execute(&p, &part, &opts(&probe, &cancel, 3, None)).unwrap();
    assert!(second.complete);
    assert_eq!(second.already_logged, 2);
    assert_eq!(second.executed, 4);
    assert_eq!(records_bytes(&part), records_bytes(&full));
}

#[test]
fn a_tampered_log_or_a_different_plan_is_refused() {
    let s = spec(&landing("m10-nominal.json"), json!({}));
    let p = plan(&s).unwrap();
    let cancel = AtomicBool::new(false);
    let probe = plenty();
    let dir = scratch("tamper");
    engine::execute(&p, &dir, &opts(&probe, &cancel, 1, Some(2))).unwrap();
    let log = fs::read_to_string(dir.join("log.jsonl")).unwrap();
    assert!(log.contains("\"landed\""));
    fs::write(
        dir.join("log.jsonl"),
        log.replacen("\"landed\"", "\"hard_landing\"", 1),
    )
    .unwrap();
    let err = engine::execute(&p, &dir, &opts(&probe, &cancel, 1, None)).unwrap_err();
    assert!(err.contains("hash"), "{err}");

    let other = plan(&spec(
        &landing("m10-nominal.json"),
        json!({"seeds": {"mode": "range", "first": 5100, "count": 6}}),
    ))
    .unwrap();
    let err = engine::execute(&other, &dir, &opts(&probe, &cancel, 1, None)).unwrap_err();
    assert!(err.contains("different plan"), "{err}");
}

#[test]
fn memory_pressure_parks_workers_without_changing_records() {
    let s = spec(
        &landing("m10-nominal.json"),
        json!({"seeds": {"mode": "range", "first": 7000, "count": 16}}),
    );
    let p = plan(&s).unwrap();
    let cancel = AtomicBool::new(false);
    let roomy = plenty();
    let calm = scratch("pressure-calm");
    engine::execute(&p, &calm, &opts(&roomy, &cancel, 8, None)).unwrap();
    // Plenty at the start, then just above the reserve: the scheduler drops to one worker.
    let tight = ScriptedProbe::new(vec![Some(64_000), Some(64_000), Some(1_050)]);
    let squeezed = scratch("pressure-squeezed");
    let sum = engine::execute(&p, &squeezed, &opts(&tight, &cancel, 8, None)).unwrap();
    assert!(sum.complete);
    assert_eq!(sum.workers_min, 1);
    assert!(sum.workers_start > 1);
    assert_eq!(records_bytes(&calm), records_bytes(&squeezed));
}

#[test]
fn protected_seeds_pinned_parameters_and_out_of_range_faults_are_refused_before_running() {
    let base = landing("m10-nominal.json");
    let err = plan(&spec(
        &base,
        json!({"seeds": {"mode": "range", "first": 2995, "count": 10}}),
    ))
    .err()
    .unwrap();
    assert!(err.contains("protected"), "{err}");
    let err = plan(&spec(
        &base,
        json!({"seeds": {"mode": "derived", "low": 5000, "high": 7000, "count": 10, "common": true}}),
    ))
    .err()
    .unwrap();
    assert!(err.contains("protected"), "{err}");

    // The landing model pins the vehicle: a thrust sweep names the field it refuses.
    let err = plan(&spec(
        &base,
        json!({
            "design": {"kind": "grid", "levels": 2},
            "parameters": [{"name": "thrust", "pointer": "/vehicle/max_thrust_n", "unit": "N", "low": 800000.0, "high": 900000.0}]
        }),
    ))
    .err()
    .unwrap();
    assert!(err.contains("vehicle.max_thrust_n"), "{err}");

    // Fault magnitudes outside the registered range are refused by the model.
    let gnss = landing("gnss-bias-guarded.json");
    let ok = plan(&spec(
        &gnss,
        json!({
            "design": {"kind": "grid", "levels": 3},
            "parameters": [{"name": "bias", "pointer": "/faults/0/magnitude", "unit": "model", "low": 5.0, "high": 15.0}]
        }),
    ));
    assert!(ok.is_ok(), "{:?}", ok.err());
    let err = plan(&spec(
        &gnss,
        json!({
            "design": {"kind": "grid", "levels": 3},
            "parameters": [{"name": "bias", "pointer": "/faults/0/magnitude", "unit": "model", "low": 5.0, "high": 5000.0}]
        }),
    ))
    .err()
    .unwrap();
    assert!(
        err.contains("magnitude") && err.contains("refused by the model"),
        "{err}"
    );
}

#[test]
fn a_fault_grid_with_arms_reports_paired_comparisons_and_the_envelope_fraction() {
    let gnss = landing("gnss-bias-guarded.json");
    let s = spec(
        &gnss,
        json!({
            "arms": [
                {"name": "guarded"},
                {"name": "baseline", "overrides": [{"pointer": "/controller/policy", "value": "baseline"}]}
            ],
            "design": {"kind": "grid", "levels": 3},
            "parameters": [{"name": "bias", "pointer": "/faults/0/magnitude", "unit": "model", "low": 5.0, "high": 15.0}],
            "seeds": {"mode": "range", "first": 5200, "count": 4},
            "envelope": [{"pointer": "/faults/0/magnitude", "low": 5.0, "high": 12.0, "basis": "synthetic test bound"}],
            "retention": {"policy": "failures"},
            "analysis": {"metric": "summary.propellant_used_kg"}
        }),
    );
    let p = plan(&s).unwrap();
    assert_eq!(p.runs.len(), 2 * 3 * 4);
    let cancel = AtomicBool::new(false);
    let probe = plenty();
    let dir = scratch("fault-grid");
    assert!(
        engine::execute(&p, &dir, &opts(&probe, &cancel, 8, None))
            .unwrap()
            .complete
    );
    let recs = engine::read_records(&p, &dir).unwrap();
    let r = report::build(&p, &recs, &dir).unwrap();
    assert_eq!(r.status, "unverified");
    assert_eq!(r.comparisons.len(), 1);
    assert_eq!(r.comparisons[0].pairs, 12);
    // Magnitude 15 lies outside [5, 12]: one cell of three in each arm.
    assert_eq!(r.extrapolated_runs, 8);
    assert!((r.in_envelope_fraction - 16.0 / 24.0).abs() < 1e-12);
    let cells = r.cells.unwrap();
    assert_eq!(cells.len(), 6);
    assert!(cells.iter().all(|c| c.all_pass.is_some()));
}

#[test]
fn rigid_body_sensitivity_and_convergence_run_through_the_report() {
    let case = repo().join("crates/vv-rocket/cases/propulsive_descent.json");
    let v = json!({
        "schema": "vv-experiment.v1",
        "id": "rigid-sobol",
        "domain": "rocket-rigid-body",
        "base_case": case.display().to_string(),
        "parameters": [
            {"name": "drag", "pointer": "/vehicle/drag_coefficient", "unit": "model", "low": 0.6, "high": 1.0},
            {"name": "isp", "pointer": "/vehicle/isp_s", "unit": "s", "low": 270.0, "high": 295.0}
        ],
        "design": {"kind": "saltelli", "base_samples": 64, "seed": 11},
        "retention": {"policy": "none"},
        "limits": {"max_runs": 1000, "max_retained": 1, "max_artifact_bytes": 1000000, "max_wall_s": 600},
        "analysis": {"metric": "summary.propellant_used_kg", "bootstrap": 50, "convergence_tolerance_m": 0.001}
    });
    let s = serde_json::to_vec(&v).unwrap();
    let p = plan(&s).unwrap();
    assert_eq!(p.runs.len(), 64 * 4);
    let cancel = AtomicBool::new(false);
    let probe = plenty();
    let dir = scratch("rigid-sobol");
    assert!(
        engine::execute(&p, &dir, &opts(&probe, &cancel, 8, None))
            .unwrap()
            .complete
    );
    let recs = engine::read_records(&p, &dir).unwrap();
    let r = report::build(&p, &recs, &dir).unwrap();
    let sens = &r.sensitivity[0];
    let idx = sens.indices.as_ref().expect("indices");
    assert_eq!(idx.len(), 2);
    for i in idx {
        assert!(i.total >= -0.05 && i.total <= 1.2, "{i:?}");
    }
    assert!(!r.convergence.is_empty());
    assert!(
        r.convergence.iter().all(|(_, c)| c.applicable && c.pass),
        "{:#?}",
        r.convergence
    );
}

#[test]
fn the_equivalence_gate_finds_identical_bytes_through_the_canonical_command_line() {
    let cli_target = Path::new(env!("CARGO_TARGET_TMPDIR")).join("vv-rocket-cli");
    let status = Command::new(env!("CARGO"))
        .args(["build", "--release", "-q", "-j", "4", "--manifest-path"])
        .arg(repo().join("crates/vv-rocket/Cargo.toml"))
        .arg("--target-dir")
        .arg(&cli_target)
        .status()
        .unwrap();
    assert!(status.success());
    let cli = cli_target
        .join("release")
        .join(format!("vv-rocket{}", std::env::consts::EXE_SUFFIX));

    let gnss = landing("gnss-bias-guarded.json");
    let s = spec(
        &gnss,
        json!({
            "design": {"kind": "grid", "levels": 2},
            "parameters": [{"name": "bias", "pointer": "/faults/0/magnitude", "unit": "model", "low": 5.0, "high": 15.0}],
            "seeds": {"mode": "range", "first": 5300, "count": 5}
        }),
    );
    let p = plan(&s).unwrap();
    let cancel = AtomicBool::new(false);
    let probe = plenty();
    let dir = scratch("equivalence");
    engine::execute(&p, &dir, &opts(&probe, &cancel, 8, None)).unwrap();
    let recs = engine::read_records(&p, &dir).unwrap();
    let eq = equiv::run(&p, &dir, &recs, &cli, 4).unwrap();
    assert!(eq.source_sha256_match);
    assert_eq!(eq.differences, 0, "{eq:#?}");
    assert!(eq.pass);
    let r = report::build(&p, &recs, &dir).unwrap();
    assert_eq!(r.status, "valid");

    // A record that disagrees with its artifacts fails the gate.
    let dir2 = scratch("equivalence-tampered");
    engine::execute(&p, &dir2, &opts(&probe, &cancel, 8, None)).unwrap();
    let mut recs2 = engine::read_records(&p, &dir2).unwrap();
    recs2[0].trace_sha256 = Some("0".repeat(64));
    let eq2 = equiv::run(&p, &dir2, &recs2, &cli, 2).unwrap();
    assert!(!eq2.pass);
    assert!(eq2.differences >= 1);
}

#[test]
fn the_command_line_refuses_outputs_under_a_runs_directory() {
    let dir = scratch("cli-guard");
    let spec_path = dir.join("spec.json");
    fs::write(&spec_path, spec(&landing("m10-nominal.json"), json!({}))).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vv-exec"))
        .arg("run")
        .arg(&spec_path)
        .arg("--output")
        .arg(dir.join("runs").join("x"))
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&out.stderr).contains("runs"));
    assert!(!dir.join("runs").exists());
}
