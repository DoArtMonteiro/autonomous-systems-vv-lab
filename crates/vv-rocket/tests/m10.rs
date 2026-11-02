//! M10 resilient navigation: schema v2 boundary, the new sensor faults, the M10 arms end to end,
//! the navigation verifier (v3) and replay (docs/m10-resilient-navigation.md).

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Value, json};
use vv_rocket::landing_run::{LandError, artifacts, write_landing};
use vv_rocket::run::replay;

fn landing_path(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("landing")
        .join(name)
}

fn m10_case() -> Value {
    serde_json::from_slice(&fs::read(landing_path("m10-nominal.json")).unwrap()).unwrap()
}

fn bytes(v: &Value) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}

fn with(policy: &str, faults: Value) -> Value {
    let mut c = m10_case();
    c["controller"]["policy"] = json!(policy);
    c["faults"] = faults;
    c
}

fn verification(case: &Value, seed: u64) -> Value {
    let art = artifacts(&bytes(case), seed).unwrap();
    serde_json::from_slice(&art.verification).unwrap()
}

fn input_error(case: &Value) -> String {
    match artifacts(&bytes(case), 4000) {
        Err(LandError::Input(m)) => m,
        Err(e) => panic!("expected an input error, got {e}"),
        Ok(_) => panic!("expected an input error, the case was accepted"),
    }
}

#[test]
fn a_v1_case_keeps_its_meaning_and_rejects_every_m10_addition() {
    let mut v1: Value =
        serde_json::from_slice(&fs::read(landing_path("m91-nominal.json")).unwrap()).unwrap();
    assert_eq!(v1["schema"], "vv-rocket-landing.v1");
    let mut c = v1.clone();
    c["controller"]["policy"] = json!("m10_b_plus");
    assert!(input_error(&c).contains("needs schema vv-rocket-landing.v2"));
    let mut c = v1.clone();
    c["controller"]["nav"] = json!({});
    assert!(input_error(&c).contains("controller.nav needs schema"));
    let mut c = v1.clone();
    c["faults"] =
        json!([{"kind": "altimeter_stuck", "start_s": 6.0, "end_s": 8.0, "magnitude": 0.0}]);
    assert!(input_error(&c).contains("fault altimeter_stuck needs schema"));
    // The same M9 policy under v2 gives the same trace and verification as under v1.
    let a = artifacts(&bytes(&v1), 4000).unwrap();
    v1["schema"] = json!("vv-rocket-landing.v2");
    let b = artifacts(&bytes(&v1), 4000).unwrap();
    assert_eq!(a.trace, b.trace);
    assert_eq!(a.verification, b.verification);
    let mut c = v1;
    c["schema"] = json!("vv-rocket-landing.v3");
    assert!(input_error(&c).contains("schema must be"));
}

#[test]
fn every_new_fault_has_a_registered_range_and_rejects_values_outside_it() {
    let cases = [
        ("altimeter_delay", 0.02, 0.2),
        ("altimeter_outliers", 0.001, 0.01),
        ("altimeter_drift", 0.03, 0.3),
        ("gnss_horizontal_bias", 5.0, 30.0),
        ("gnss_coherent_ramp", 0.1, 3.0),
        ("imu_accel_drift", 0.01, 0.1),
    ];
    for (kind, low, high) in cases {
        let fault = |m: f64| json!([{"kind": kind, "start_s": 6.0, "end_s": 40.0, "magnitude": m}]);
        for bad in [low * 0.5, high * 2.0] {
            let msg = input_error(&with("m10_b_plus", fault(bad)));
            assert!(msg.contains("registered range"), "{kind} {bad}: {msg}");
        }
        assert!(artifacts(&bytes(&with("m10_b_plus", fault(low))), 4000).is_ok());
    }
    // A stuck altimeter has no magnitude and lasts 1 to 10 s.
    let stuck = |m: f64, end: f64| json!([{"kind": "altimeter_stuck", "start_s": 6.0, "end_s": end, "magnitude": m}]);
    assert!(input_error(&with("m10_b_plus", stuck(1.0, 8.0))).contains("magnitude must be 0"));
    assert!(input_error(&with("m10_b_plus", stuck(0.0, 6.5))).contains("window must last"));
    assert!(input_error(&with("m10_b_plus", stuck(0.0, 17.0))).contains("window must last"));
}

#[test]
fn hostile_navigation_parameters_are_rejected_by_name() {
    for (field, value) in [
        ("cusum_h", json!(0.0)),
        ("cusum_h", json!(-1.0)),
        ("k_ff", json!(1e9)),
        ("admission_cycles", json!(0)),
        ("monitor_gnss_gain", json!(1.5)),
        ("suspect_cusum_fraction", json!(-0.1)),
    ] {
        let mut c = m10_case();
        c["controller"]["nav"][field] = value;
        let msg = input_error(&c);
        assert!(msg.contains(field), "{field}: {msg}");
    }
    let mut c = m10_case();
    c["controller"]["nav"]["exclude_after_s"] = json!(0.1);
    assert!(input_error(&c).contains("exclude_after_s"));
    let mut c = m10_case();
    c["controller"]["nav"]["unknown_knob"] = json!(1.0);
    assert!(input_error(&c).contains("unknown"));
}

#[test]
fn the_m10_arms_land_the_nominal_case_and_declare_with_a_v3_verification() {
    for arm in ["m10_a", "m10_b", "m10_b_plus"] {
        let v = verification(&with(arm, json!([])), 4000);
        assert_eq!(v["schema"], "vv-rocket-landing-verification.v3", "{arm}");
        assert_eq!(v["outcome"], "landed", "{arm}");
        let nav = &v["navigation"];
        assert_eq!(nav["physical_class"], "R", "{arm}");
        assert_eq!(nav["unsafe_transitions"], 0, "{arm}");
        assert_eq!(nav["transitions_within_bound"], true, "{arm}");
        assert_eq!(nav["vertical"]["alert_failure"], false, "{arm}");
        // The horizontal position is never trusted (B_h = 30 m > AL_h = 10 m).
        assert_eq!(nav["horizontal_position"]["trusted_fraction"], 0.0, "{arm}");
        if arm == "m10_a" {
            assert!(nav["nees_mean"].is_null());
        } else {
            // 7 states: a consistent filter has a mean NEES near 7 (reported, not a pass mark).
            let nees = nav["nees_mean"].as_f64().unwrap();
            assert!((2.0..20.0).contains(&nees), "{arm} NEES {nees}");
        }
    }
}

#[test]
fn the_cold_start_rule_never_admits_a_radar_biased_from_the_start_and_declares_it() {
    for kind in ["altimeter_bias", "altimeter_bias_low"] {
        let faults = json!([{"kind": kind, "start_s": 0.0, "end_s": 40.0, "magnitude": 20.0}]);
        let art = artifacts(&bytes(&with("m10_b_plus", faults)), 4000).unwrap();
        let trace: Value = serde_json::from_slice(&art.trace).unwrap();
        let navs: Vec<&Value> = trace["samples"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|s| s["estimate"].get("nav"))
            .collect();
        assert!(!navs.is_empty());
        assert!(navs.iter().all(|n| n["radar"] != "healthy"), "{kind}");
        assert!(navs.iter().all(|n| n["mode"] != "nominal"), "{kind}");
        assert!(navs.iter().all(|n| n["vertical"] != "trusted"), "{kind}");
        assert!(
            navs.iter().skip(10).all(|n| n["ambiguous"] == true),
            "{kind}"
        );
        assert_eq!(art.outcome, "landed", "{kind}: GNSS + IMU, as robust");
    }
}

#[test]
fn a_gnss_bias_from_the_start_is_declared_and_not_recovered_as_pre_registered() {
    let faults = json!([{"kind": "gnss_bias", "start_s": 0.0, "end_s": 40.0, "magnitude": 20.0}]);
    let v = verification(&with("m10_b_plus", faults), 4000);
    let nav = &v["navigation"];
    assert_ne!(v["outcome"], "landed");
    assert_eq!(nav["vertical"]["declaration_applicable"], true);
    assert_eq!(nav["vertical"]["alert_failure"], false);
}

#[test]
fn a_gnss_dropout_is_dead_reckoned_and_the_receiver_is_readmitted() {
    let faults = json!([{"kind": "gnss_dropout", "start_s": 6.0, "end_s": 14.0, "magnitude": 0.0}]);
    let art = artifacts(&bytes(&with("m10_b_plus", faults)), 4000).unwrap();
    let trace: Value = serde_json::from_slice(&art.trace).unwrap();
    let at = |t: f64| {
        trace["samples"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["t_s"].as_f64().unwrap() >= t)
            .unwrap()["estimate"]["nav"]
            .clone()
    };
    assert_eq!(at(5.0)["gnss"], "healthy");
    assert_eq!(at(10.0)["gnss"], "excluded");
    assert_eq!(at(18.0)["gnss"], "healthy", "readmitted after the window");
    assert_eq!(art.outcome, "landed");
}

#[test]
fn m10_runs_replay_byte_for_byte_with_the_navigation_report() {
    let dir = std::env::temp_dir().join(format!("vv-rocket-m10-{}-replay", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    let case = dir.with_extension("case.json");
    let faults =
        json!([{"kind": "altimeter_stuck", "start_s": 8.0, "end_s": 12.0, "magnitude": 0.0}]);
    fs::write(&case, bytes(&with("m10_b_plus", faults))).unwrap();
    write_landing(&case, 4001, &dir).unwrap();
    let report = replay(&dir);
    assert_eq!(report.status, "verified", "{report:?}");
    let v: Value =
        serde_json::from_slice(&fs::read(dir.join("verification.json")).unwrap()).unwrap();
    assert!(v["navigation"]["detections"][0]["first_declaration_delay_s"].is_number());
    let _ = fs::remove_dir_all(&dir);
    let _ = fs::remove_file(&case);
}

fn final_nav(case: &Value, seed: u64) -> (Value, Value) {
    let art = artifacts(&bytes(case), seed).unwrap();
    let trace: Value = serde_json::from_slice(&art.trace).unwrap();
    let last = trace["samples"]
        .as_array()
        .unwrap()
        .iter()
        .rev()
        .find_map(|s| s["estimate"].get("nav").cloned())
        .unwrap();
    let v: Value = serde_json::from_slice(&art.verification).unwrap();
    (last, v)
}

#[test]
fn the_rate_parity_isolates_a_stuck_radar_and_the_run_lands() {
    let faults =
        json!([{"kind": "altimeter_stuck", "start_s": 9.0, "end_s": 15.0, "magnitude": 0.0}]);
    let (nav, v) = final_nav(&with("m10_b_plus", faults), 4000);
    assert_eq!(nav["isolated_radar"], true);
    assert_eq!(nav["isolated_gnss"], false);
    assert_eq!(v["navigation"]["isolation"], "correct");
    assert_eq!(v["navigation"]["vertical"]["alert_failure"], false);
    assert_eq!(v["outcome"], "landed");
}

#[test]
fn a_coherent_receiver_ramp_is_isolated_as_the_receiver() {
    let faults =
        json!([{"kind": "gnss_coherent_ramp", "start_s": 8.0, "end_s": 40.0, "magnitude": 2.0}]);
    let (nav, v) = final_nav(&with("m10_b_plus", faults), 4000);
    assert_eq!(nav["isolated_gnss"], true);
    assert_eq!(nav["isolated_radar"], false);
    assert_eq!(v["navigation"]["isolation"], "correct");
}

#[test]
fn constant_biases_and_accelerometer_drift_are_never_isolated() {
    // A constant offset changes no rate (sections 3.3 and 3.4); an accelerometer drift is not a
    // group: the parity must say "not isolated" rather than blame the radar or the receiver.
    for faults in [
        json!([{"kind": "gnss_horizontal_bias", "start_s": 0.0, "end_s": 40.0, "magnitude": 20.0}]),
        json!([{"kind": "altimeter_bias", "start_s": 0.0, "end_s": 40.0, "magnitude": 20.0}]),
        json!([{"kind": "imu_accel_drift", "start_s": 4.0, "end_s": 40.0, "magnitude": 0.05}]),
    ] {
        for seed in [4000, 4001, 4002] {
            let (nav, v) = final_nav(&with("m10_b_plus", faults.clone()), seed);
            assert_eq!(nav["isolated_radar"], false, "{faults} {seed}");
            assert_eq!(nav["isolated_gnss"], false, "{faults} {seed}");
            assert_eq!(v["navigation"]["isolation"], "none");
        }
    }
}

#[test]
fn the_specific_force_lag_is_measured_and_bounded_by_the_actuator() {
    // M10.1 exit item (docs/m10-resilient-navigation.md, 3.1): the IMU measures the thrust of the
    // previous step, the filter propagates over the next control period with it. Error of the
    // propagated acceleration: |T(k) + T(k+1) - 2 T(k-1)| / (2 m), from the truth log.
    use vv_rocket::dynamics::mass_properties;
    use vv_rocket::landing_model::{LandingCase, prepare_landing};
    use vv_rocket::landing_sim::simulate_landing;
    let case: LandingCase = serde_json::from_value(m10_case()).unwrap();
    let prep = prepare_landing(&case, 4000).unwrap();
    let run = simulate_landing(&prep).unwrap();
    let steps = &run.log.steps;
    let (mut ramp, mut ignition) = (0.0_f64, 0.0_f64);
    for k in (2..steps.len() - 1).step_by(2) {
        let m = mass_properties(&prep.truth.vehicle, steps[k].state.mp).mass;
        let t = |i: usize| steps[i].thrust_n;
        let err = (t(k) + t(k + 1) - 2.0 * t(k - 1)).abs() / (2.0 * m);
        if t(k - 1) == 0.0 && t(k) > 0.0 {
            ignition = ignition.max(err);
        } else {
            ramp = ramp.max(err);
        }
    }
    eprintln!("specific-force lag: ignition {ignition:.3} m/s^2, ramps {ramp:.3} m/s^2");
    // Ignition: the full minimum thrust for one period (338 kN over about 26 t, about 13 m/s^2).
    assert!(ignition > 10.0 && ignition < 15.0, "{ignition}");
    // Ramps: bounded by the throttle rate limit (1/s, 845 kN): 1.5 steps of 8.45 kN over m.
    assert!(ramp < 0.6, "{ramp}");
}
