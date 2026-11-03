//! M14: the ground vehicle as an in-process domain. Determinism, the seed guard, integer
//! parameters and the separation of mission outcome from safety.

use std::path::Path;

use serde_json::{Value, json};
use vv_exec::domain::{Domain, by_id};
use vv_exec::plan::Plan;

fn case(name: &str) -> Vec<u8> {
    std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("cases/m14/{name}.json")))
        .expect("case file")
}

fn ground() -> &'static dyn Domain {
    by_id("ground-m4").expect("ground domain")
}

#[test]
fn a_ground_run_is_deterministic_and_reports_signed_margins() {
    let c = case("ground-zone-corridor");
    let a = ground().run(&c, 10_000).expect("run");
    let b = ground().run(&c, 10_000).expect("run");
    assert_eq!(a, b);
    assert_eq!(a.outcome, "completed");
    assert_eq!(a.all_pass(), Some(true));
    assert!(a.violations.is_empty());
    // The corridor runs 250 mm above the zone.
    assert_eq!(a.metrics["margin.restricted_zone_mm"], 250.0);
    assert!(a.metrics["margin.world_bounds_mm"] > 0.0);
}

#[test]
fn gps_noise_can_drive_the_vehicle_into_the_zone() {
    let mut v: Value = serde_json::from_slice(&case("ground-zone-corridor")).unwrap();
    v["scenario"]["sensors"]["gps"]["noise_max_mm"] = json!(600);
    let bytes = serde_json::to_vec(&v).unwrap();
    let unsafe_runs: Vec<_> = (10_000..10_020)
        .map(|s| ground().run(&bytes, s).expect("run"))
        .filter(|o| o.invariants_pass == Some(false))
        .collect();
    assert!(!unsafe_runs.is_empty());
    for o in &unsafe_runs {
        assert!(!o.violations.is_empty());
        assert!(
            o.violations
                .iter()
                .all(|x| x.starts_with("invariant:") || x.starts_with("contract:"))
        );
    }
    assert!(
        unsafe_runs
            .iter()
            .any(|o| o.metrics["margin.restricted_zone_mm"] <= 0.0)
    );
}

#[test]
fn the_ground_seed_guard_refuses_the_m6_reserves() {
    for s in [101, 112, 129, 201, 7349, 921_685] {
        assert!(
            vv_exec::seeds::check(ground().protected(), s).is_err(),
            "{s}"
        );
    }
    for s in [42, 1337, 2026, 10_000, 130, 213] {
        assert!(
            vv_exec::seeds::check(ground().protected(), s).is_ok(),
            "{s}"
        );
    }
}

fn spec(parameters: Value, seeds: Value) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema": "vv-experiment.v1",
        "id": "ground-test",
        "domain": "ground-m4",
        "base_case": "unused",
        "parameters": parameters,
        "design": {"kind": "grid", "levels": 3},
        "seeds": seeds,
        "retention": {"policy": "none", "sample_every": 0},
        "limits": {"max_runs": 100, "max_retained": 1, "max_artifact_bytes": 1000000, "max_wall_s": 60}
    }))
    .unwrap()
}

fn plan(spec_bytes: &[u8]) -> Result<Plan, String> {
    let e = vv_exec::spec::Experiment::parse(spec_bytes)?;
    Plan::from_parts(e, spec_bytes, case("ground-zone-corridor"))
}

#[test]
fn integer_fields_need_integer_parameters() {
    let p = json!([{"name": "noise", "pointer": "/scenario/sensors/gps/noise_max_mm", "unit": "mm", "low": 0, "high": 400, "integer": true}]);
    let seeds = json!({"mode": "list", "values": [10000]});
    let ok = plan(&spec(p.clone(), seeds.clone())).expect("plan");
    let values: Vec<f64> = ok.cells.iter().map(|c| c.values[0]).collect();
    assert_eq!(values, vec![0.0, 200.0, 400.0]);
    let case1: Value = serde_json::from_slice(&ok.case_of(0, 1).unwrap()).unwrap();
    assert_eq!(
        case1["scenario"]["sensors"]["gps"]["noise_max_mm"],
        json!(200)
    );

    let mut float = p.clone();
    float[0]["integer"] = json!(false);
    let err = plan(&spec(float, seeds.clone())).err().expect("refused");
    assert!(err.contains("integer field"), "{err}");

    let mut fractional = p;
    fractional[0]["high"] = json!(400.5);
    let err = plan(&spec(fractional, seeds)).err().expect("refused");
    assert!(err.contains("integer low and high"), "{err}");
}

#[test]
fn a_ground_plan_with_a_reserved_seed_is_refused() {
    let p = json!([{"name": "noise", "pointer": "/scenario/sensors/gps/noise_max_mm", "unit": "mm", "low": 0, "high": 400, "integer": true}]);
    let err = plan(&spec(p, json!({"mode": "range", "first": 95, "count": 10})))
        .err()
        .expect("refused");
    assert!(err.contains("M6"), "{err}");
}
