//! M9 powered landing: determinism, nominal landing for both policies, verdicts, input validation,
//! stored-run replay with tamper detection, the controller's isolation from the truth and the
//! cross-platform trace pins (docs/m9-powered-landing.md).

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::{Value, json};
use vv_rocket::dynamics::State;
use vv_rocket::landing_model::{LandingCase, prepare_landing};
use vv_rocket::landing_run::{artifacts, write_landing};
use vv_rocket::landing_sim::simulate_landing;
use vv_rocket::landing_verify::verify;
use vv_rocket::math::Vec3;
use vv_rocket::run::replay;
use vv_rocket::sha256_hex;

fn landing_path(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("landing")
        .join(name)
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("vv-rocket-landing-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    dir
}

fn bytes_of(name: &str) -> Vec<u8> {
    fs::read(landing_path(name)).unwrap()
}

fn value_of(name: &str) -> Value {
    serde_json::from_slice(&bytes_of(name)).unwrap()
}

fn json_of(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).unwrap()
}

fn run_value(case: &Value, seed: u64) -> Result<(Value, Value), String> {
    let art = artifacts(&serde_json::to_vec(case).unwrap(), seed)?;
    Ok((json_of(&art.trace), json_of(&art.verification)))
}

fn event_kinds(trace: &Value) -> Vec<&str> {
    trace["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap())
        .collect()
}

fn requirement<'a>(v: &'a Value, id: &str) -> &'a Value {
    v["requirements"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["id"] == id)
        .unwrap()
}

fn invariant<'a>(v: &'a Value, id: &str) -> &'a Value {
    v["invariants"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["id"] == id)
        .unwrap()
}

#[test]
fn nominal_seed_zero_lands_with_both_policies_and_meets_every_requirement_and_invariant() {
    for name in ["nominal.json", "nominal-robust.json"] {
        let (trace, v) = run_value(&value_of(name), 0).unwrap();
        assert_eq!(v["outcome"], "landed", "{name}");
        assert_eq!(v["requirements_pass"], true);
        assert_eq!(v["invariants_pass"], true);
        for r in v["requirements"].as_array().unwrap() {
            assert_eq!(r["pass"], true, "{name} {}", r["id"]);
            assert_eq!(r["evaluated"], true);
        }
        for i in v["invariants"].as_array().unwrap() {
            assert_eq!(i["pass"], true, "{name} {}", i["id"]);
            assert_eq!(i["failure_count"], 0);
        }
        assert_eq!(
            event_kinds(&trace),
            ["ignition", "touchdown", "end"],
            "{name}"
        );
        // The nominal touchdown: slow, upright, on the pad, with propellant left.
        let td = &v["touchdown"]["truth"];
        let vz = td["base_velocity_mps"][2].as_f64().unwrap();
        assert!((-3.0..=-1.0).contains(&vz), "{name} vertical speed {vz}");
        assert!(td["tilt_cos"].as_f64().unwrap() > 0.9996);
        assert!(td["propellant_kg"].as_f64().unwrap() > 4000.0);
        let summary = &trace["summary"];
        assert_eq!(summary["end_reason"], "touchdown");
        assert!(summary["max_neglected_jet_ratio"].as_f64().unwrap() > 0.0);
        assert!(summary["max_neglected_jet_ratio"].as_f64().unwrap() < 0.01);
        assert_eq!(
            v["policy"],
            if name.contains("robust") {
                "robust"
            } else {
                "baseline"
            }
        );
    }
}

#[test]
fn the_same_seed_gives_identical_bytes_and_other_seeds_differ() {
    let bytes = bytes_of("nominal.json");
    let a = artifacts(&bytes, 7).unwrap();
    let b = artifacts(&bytes, 7).unwrap();
    assert_eq!(a.trace, b.trace);
    assert_eq!(a.verification, b.verification);
    let c = artifacts(&bytes, 8).unwrap();
    assert_ne!(a.trace, c.trace);
    let zero = artifacts(&bytes, 0).unwrap();
    assert_ne!(zero.trace, a.trace);
    // Seed 0 keeps the sensor noise on: it is not a noiseless run.
    let trace = json_of(&zero.trace);
    let s = &trace["samples"][5];
    let truth_alt = s["truth"]["base_position_m"][2].as_f64().unwrap();
    let measured = s["observation"]["altimeter_m"].as_f64().unwrap();
    assert!(measured != truth_alt && (measured - truth_alt).abs() < 0.4);
}

#[test]
fn dispersions_follow_the_registered_ranges_and_seed_zero_has_none() {
    let case: LandingCase = serde_json::from_slice(&bytes_of("nominal.json")).unwrap();
    let nominal = prepare_landing(&case, 0).unwrap();
    assert!(!nominal.dispersed);
    assert_eq!(nominal.truth.r0.to_array(), [80.0, 0.0, 3000.0]);
    assert_eq!(nominal.truth.vehicle.max_thrust_n, 845_000.0);
    let mut moved = false;
    let (mut thrust_moved, mut isp_moved, mut propellant_moved) = (false, false, false);
    for seed in 1..=40 {
        let p = prepare_landing(&case, seed).unwrap();
        assert!(p.dispersed);
        let (r, v, w) = (p.truth.r0, p.truth.v0, p.truth.w0);
        assert!((r.x - 80.0).abs() <= 30.0 && r.y.abs() <= 30.0 && (r.z - 3000.0).abs() <= 50.0);
        assert!((v.x + 12.0).abs() <= 3.0 && v.y.abs() <= 3.0 && (v.z + 200.0).abs() <= 10.0);
        assert!(w.x == 0.0 && (w.y - 0.004).abs() <= 0.004 && w.z.abs() <= 0.004);
        let veh = &p.truth.vehicle;
        assert!((veh.propellant_mass_kg / 8000.0 - 1.0).abs() <= 0.02);
        assert!((veh.max_thrust_n / 845_000.0 - 1.0).abs() <= 0.02);
        assert!((veh.isp_s / 282.0 - 1.0).abs() <= 0.01);
        // The propellant inertia per kilogram is that of the nominal tank.
        assert!(
            (veh.propellant_inertia_kgm2[1] / veh.propellant_mass_kg - 250_000.0 / 8000.0).abs()
                < 1e-9
        );
        // The controller keeps the nominal values of everything it is given, whatever the draw.
        let c = &p.controller;
        assert_eq!(c.max_thrust_n, 845_000.0);
        assert_eq!(c.propellant_mass_kg, 8000.0);
        assert_eq!(c.isp_s, 282.0);
        assert_eq!(c.dry_mass_kg, 22_000.0);
        assert_eq!(c.dry_cm_station_m, 16.0);
        assert_eq!(c.propellant_cm_station_m, 9.0);
        assert_eq!(c.gravity_mps2, 9.80665);
        // The nominal vehicle kept for reference is untouched, inertias included; the controller
        // has no inertia at all (checked against its type below).
        let nominal = &p.nominal_vehicle;
        assert_eq!(
            nominal.dry_inertia_kgm2,
            [40_000.0, 1_800_000.0, 1_800_000.0]
        );
        assert_eq!(
            nominal.propellant_inertia_kgm2,
            [12_000.0, 250_000.0, 250_000.0]
        );
        assert_eq!(nominal.max_thrust_n, 845_000.0);
        assert_eq!(nominal.isp_s, 282.0);
        assert_eq!(nominal.propellant_mass_kg, 8000.0);
        // The truth vehicle keeps what is not dispersed: geometry, dry inertia, drag.
        assert_eq!(veh.dry_cm_station_m, 16.0);
        assert_eq!(veh.propellant_cm_station_m, 9.0);
        assert_eq!(veh.dry_inertia_kgm2, nominal.dry_inertia_kgm2);
        assert_eq!(veh.drag_coefficient, nominal.drag_coefficient);
        // The guard only means something if the truth really differs from the controller's values.
        thrust_moved |= veh.max_thrust_n != c.max_thrust_n;
        isp_moved |= veh.isp_s != c.isp_s;
        propellant_moved |= veh.propellant_mass_kg != c.propellant_mass_kg;
        moved |= r.x != 80.0;
    }
    assert!(moved && thrust_moved && isp_moved && propellant_moved);
    assert!(
        !include_str!("../src/landing_types.rs").contains("inertia"),
        "the controller configuration must not carry an inertia"
    );
}

#[test]
fn the_controller_sees_only_observations_and_its_configuration() {
    // The unit tests at the end of the controller module may import more; the code above them may not.
    let controller = include_str!("../src/landing_controller.rs")
        .split("#[cfg(test)]")
        .next()
        .unwrap();
    let types = include_str!("../src/landing_types.rs");
    // Exactly these crate imports: no truth state, vehicle, simulation or sensor internals.
    let imports = |src: &str| -> Vec<String> {
        src.lines()
            .filter(|l| l.trim_start().starts_with("use "))
            .map(|l| l.trim().to_string())
            .collect()
    };
    assert_eq!(
        imports(controller),
        [
            "use crate::landing_types::{Command, ControllerConfig, Estimate, Observation, Policy};",
            "use crate::math::{Quat, Vec3};",
            "use crate::model::G0;",
        ]
    );
    assert_eq!(imports(types), ["use serde::{Deserialize, Serialize};"]);
    for forbidden in [
        "dynamics",
        "State",
        "Prepared",
        "Vehicle",
        "landing_truth",
        "landing_sim",
    ] {
        assert!(
            !controller.contains(forbidden),
            "controller mentions {forbidden}"
        );
        assert!(!types.contains(forbidden), "types mention {forbidden}");
    }
    // Its entry point takes an observation and returns a command.
    assert!(
        controller.contains("pub fn step(&mut self, obs: &Observation) -> (Command, Estimate)")
    );
}

#[test]
fn artifact_paths_use_only_correctly_rounded_arithmetic() {
    // docs/m9-powered-landing.md: only + - * /, sqrt and the crate's exp in the code that decides
    // the artifacts. Test modules are exempt.
    let sources = [
        ("prng", include_str!("../src/prng.rs")),
        (
            "landing_actuator",
            include_str!("../src/landing_actuator.rs"),
        ),
        (
            "landing_controller",
            include_str!("../src/landing_controller.rs"),
        ),
        ("landing_model", include_str!("../src/landing_model.rs")),
        ("landing_run", include_str!("../src/landing_run.rs")),
        ("landing_sensors", include_str!("../src/landing_sensors.rs")),
        ("landing_sim", include_str!("../src/landing_sim.rs")),
        ("landing_truth", include_str!("../src/landing_truth.rs")),
        ("landing_types", include_str!("../src/landing_types.rs")),
        ("landing_verify", include_str!("../src/landing_verify.rs")),
    ];
    for (name, src) in sources {
        let code = src.split("#[cfg(test)]").next().unwrap();
        for banned in [
            ".sin(",
            ".cos(",
            ".tan(",
            ".atan2(",
            ".atan(",
            ".acos(",
            ".asin(",
            ".ln(",
            ".log(",
            ".log2(",
            ".powf(",
            ".powi(",
            ".mul_add(",
            ".hypot(",
            ".exp(",
            ".cbrt(",
            ".tanh(",
        ] {
            assert!(!code.contains(banned), "{name} uses {banned}");
        }
    }
}

fn tamper_dir(name: &str, case: &str, seed: u64) -> PathBuf {
    let dir = scratch(name);
    write_landing(&landing_path(case), seed, &dir).unwrap();
    dir
}

fn replay_failures(dir: &Path) -> Vec<&'static str> {
    replay(dir)
        .checks
        .iter()
        .filter(|c| !c.pass)
        .map(|c| c.name)
        .collect()
}

#[test]
fn stored_landings_replay_and_any_edit_is_rejected() {
    let dir = tamper_dir("replay", "nominal.json", 3);
    for name in ["case.json", "trace.json", "verification.json", "run.json"] {
        assert!(dir.join(name).exists());
    }
    assert!(
        write_landing(&landing_path("nominal.json"), 3, &dir).is_err(),
        "never overwrites"
    );
    let report = replay(&dir);
    assert_eq!(report.status, "verified", "{:?}", report.checks);
    assert!(report.checks.len() >= 9);
    let manifest = json_of(&fs::read(dir.join("run.json")).unwrap());
    assert_eq!(manifest["schema"], "vv-rocket-landing-run.v1");
    assert_eq!(manifest["seed"], 3);
    assert_eq!(manifest["outcome"], "landed");

    // An edited trace with a re-forged manifest hash still differs from the recomputation.
    let trace = fs::read_to_string(dir.join("trace.json")).unwrap();
    let edited = trace.replacen("\"propellant_kg\":", "\"propellant_kg\":1", 1);
    assert_ne!(edited, trace);
    fs::write(dir.join("trace.json"), &edited).unwrap();
    let run = fs::read_to_string(dir.join("run.json")).unwrap();
    fs::write(
        dir.join("run.json"),
        run.replace(
            &sha256_hex(trace.as_bytes()),
            &sha256_hex(edited.as_bytes()),
        ),
    )
    .unwrap();
    let failed = replay_failures(&dir);
    assert!(failed.contains(&"recomputed trace equals the stored trace byte for byte"));
    assert!(failed.contains(&"run.json equals the regenerated manifest byte for byte"));
    assert!(
        !failed.contains(&"trace.json hash"),
        "the forged hash matches the edited file"
    );

    // An edit without the forged hash fails the hash check too.
    let dir2 = tamper_dir("replay-hash", "nominal.json", 3);
    let trace = fs::read_to_string(dir2.join("trace.json")).unwrap();
    fs::write(
        dir2.join("trace.json"),
        trace.replacen("\"step\":0", "\"step\":1", 1),
    )
    .unwrap();
    assert!(replay_failures(&dir2).contains(&"trace.json hash"));

    // A verification that claims another outcome, with its hash re-forged, is rejected.
    let dir3 = tamper_dir("replay-verification", "altimeter-bias.json", 0);
    let v = fs::read_to_string(dir3.join("verification.json")).unwrap();
    assert!(v.contains("\"outcome\":\"hard_landing\""));
    let forged = v.replace("\"outcome\":\"hard_landing\"", "\"outcome\":\"landed\"");
    fs::write(dir3.join("verification.json"), &forged).unwrap();
    let run = fs::read_to_string(dir3.join("run.json")).unwrap();
    fs::write(
        dir3.join("run.json"),
        run.replace(&sha256_hex(v.as_bytes()), &sha256_hex(forged.as_bytes()))
            .replace("\"hard_landing\"", "\"landed\""),
    )
    .unwrap();
    let failed = replay_failures(&dir3);
    assert!(
        failed.contains(&"recomputed verification equals the stored verification byte for byte")
    );
    assert!(failed.contains(&"run.json equals the regenerated manifest byte for byte"));

    // A manifest that claims another seed or outcome with intact hashes is rejected.
    let dir4 = tamper_dir("replay-manifest", "nominal.json", 3);
    let run = fs::read_to_string(dir4.join("run.json")).unwrap();
    fs::write(
        dir4.join("run.json"),
        run.replace("\"seed\": 3", "\"seed\": 4"),
    )
    .unwrap();
    let failed = replay_failures(&dir4);
    assert!(failed.contains(&"recomputed trace equals the stored trace byte for byte"));
    let dir5 = tamper_dir("replay-outcome", "altimeter-bias.json", 0);
    let run = fs::read_to_string(dir5.join("run.json")).unwrap();
    fs::write(
        dir5.join("run.json"),
        run.replace("\"hard_landing\"", "\"landed\""),
    )
    .unwrap();
    assert!(
        replay_failures(&dir5).contains(&"run.json equals the regenerated manifest byte for byte")
    );

    // An edited case fails its hash; a missing or foreign directory fails.
    let dir6 = tamper_dir("replay-case", "nominal.json", 3);
    let case = fs::read_to_string(dir6.join("case.json")).unwrap();
    fs::write(dir6.join("case.json"), case.replace("80.0", "81.0")).unwrap();
    assert_eq!(replay(&dir6).status, "failed");
    assert_eq!(replay(&scratch("missing")).status, "failed");
    fs::write(
        dir6.join("run.json"),
        "{\"schema\":\"vv-rocket-landing-run.v1\"}",
    )
    .unwrap();
    assert_eq!(replay(&dir6).status, "failed");
    for d in [dir, dir2, dir3, dir4, dir5, dir6] {
        let _ = fs::remove_dir_all(d);
    }
}

#[test]
fn m8_runs_are_still_replayed_by_the_m8_replay() {
    let dir = scratch("m8");
    vv_rocket::run::write_run(
        &Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("cases")
            .join("ballistic.json"),
        &dir,
    )
    .unwrap();
    let report = replay(&dir);
    assert_eq!(report.status, "verified");
    assert!(report.checks.iter().any(|c| c.name == "case.json hash"));
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn nominal_landing_traces_are_bit_identical_on_every_platform() {
    // Hashes of the trace bytes of seed 0, pinned on Windows and checked on Linux by CI, as for
    // the M8 traces. A change here means the controller, sensors, actuators or dynamics changed.
    for (name, want) in [
        (
            "nominal.json",
            "58035467c03016594951a311142f594e19559565619f54d1671b8497524cf780",
        ),
        (
            "nominal-robust.json",
            "ffa6b96916380de6ab7bdec36c2551e5f9a12282e99e062f8e182533487dddfd",
        ),
    ] {
        let art = artifacts(&bytes_of(name), 0).unwrap();
        assert_eq!(sha256_hex(&art.trace), want, "{name}");
    }
}

#[test]
fn trace_and_verification_have_the_documented_shape() {
    let (trace, v) = run_value(&value_of("altimeter-bias.json"), 0).unwrap();
    assert_eq!(trace["schema"], "vv-rocket-landing-trace.v1");
    let sample = &trace["samples"][0];
    for k in [
        "step",
        "t_s",
        "kind",
        "truth",
        "observation",
        "estimate",
        "command",
        "applied",
        "active_faults",
    ] {
        assert!(sample.get(k).is_some(), "sample.{k}");
    }
    for k in [
        "position_m",
        "velocity_mps",
        "attitude",
        "angular_velocity_radps",
        "propellant_kg",
        "mass_kg",
        "base_position_m",
        "base_velocity_mps",
        "tilt_cos",
    ] {
        assert!(sample["truth"].get(k).is_some(), "truth.{k}");
    }
    for k in ["altimeter_m", "gnss_position_m", "gnss_velocity_mps", "imu"] {
        assert!(sample["observation"].get(k).is_some(), "observation.{k}");
    }
    for k in ["attitude", "angular_velocity_radps", "specific_force_mps2"] {
        assert!(sample["observation"]["imu"].get(k).is_some(), "imu.{k}");
    }
    for k in ["position_m", "velocity_mps", "altimeter_rejected"] {
        assert!(sample["estimate"].get(k).is_some(), "estimate.{k}");
    }
    assert!(
        sample["command"].get("throttle").is_some() && sample["command"]["gimbal_tan"].is_array()
    );
    for k in ["engine", "throttle", "gimbal_tan", "thrust_n"] {
        assert!(sample["applied"].get(k).is_some(), "applied.{k}");
    }
    assert_eq!(sample["kind"], "periodic");
    assert_eq!(sample["applied"]["engine"], "off");
    let samples = trace["samples"].as_array().unwrap();
    assert_eq!(samples.last().unwrap()["kind"], "touchdown");
    assert_eq!(samples[1]["step"], 10, "record_every steps");
    for k in [
        "steps",
        "end_reason",
        "touchdown_t_s",
        "propellant_used_kg",
        "ignition_t_s",
        "max_neglected_jet_ratio",
    ] {
        assert!(trace["summary"].get(k).is_some(), "summary.{k}");
    }
    for k in [
        "outcome",
        "requirements",
        "invariants",
        "touchdown",
        "seed",
        "policy",
        "faults",
        "disclaimer",
    ] {
        assert!(v.get(k).is_some(), "verification.{k}");
    }
    assert_eq!(v["schema"], "vv-rocket-landing-verification.v2");
    assert!(
        v["disclaimer"]
            .as_str()
            .unwrap()
            .contains("not validated against flight data")
    );
    for k in [
        "id", "pass", "limit", "value", "unit", "expected", "observed", "step", "t_s", "cause",
    ] {
        assert!(v["requirements"][0].get(k).is_some(), "requirement.{k}");
    }
    for k in [
        "id",
        "pass",
        "limit",
        "worst_value",
        "unit",
        "failure_count",
        "first_failure",
    ] {
        assert!(v["invariants"][0].get(k).is_some(), "invariant.{k}");
    }
    assert!(v["touchdown"]["truth"]["base_velocity_mps"].is_array());
    assert_eq!(v["faults"][0]["kind"], "altimeter_bias");
    assert_eq!(v["faults"][0]["acted"], true);
}

#[test]
fn a_fault_is_recorded_as_events_and_named_as_the_cause_of_a_failure() {
    let (trace, v) = run_value(&value_of("altimeter-bias.json"), 0).unwrap();
    assert_eq!(
        event_kinds(&trace),
        ["ignition", "fault_start", "touchdown", "end"]
    );
    let start = &trace["events"][1];
    assert_eq!(
        (start["step"].as_u64(), start["t_s"].as_f64()),
        (Some(1000), Some(10.0))
    );
    assert_eq!(start["detail"]["fault"], "altimeter_bias");
    // Samples list the faults active at their step.
    let active: Vec<&Value> = trace["samples"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| s["active_faults"].as_array().unwrap().len() == 1)
        .collect();
    assert!(!active.is_empty() && active[0]["t_s"].as_f64().unwrap() >= 10.0);
    // The baseline trusts the biased altimeter and lands about 20 m too early, hard.
    assert_eq!(v["outcome"], "hard_landing");
    let r1 = requirement(&v, "R1_vertical_speed");
    assert_eq!(r1["pass"], false);
    assert!(r1["value"].as_f64().unwrap() > 15.0);
    assert_eq!(r1["cause"], json!(["altimeter_bias"]));
    assert_eq!(r1["expected"], "<= 3 m/s");
    // Safety is judged apart from the mission outcome: no invariant failed.
    assert_eq!(v["invariants_pass"], true);
    assert_eq!(v["requirements_pass"], false);

    // The robust estimator rejects the biased altimeter and lands.
    let (trace, v) = run_value(&value_of("altimeter-bias-robust.json"), 0).unwrap();
    assert_eq!(v["outcome"], "landed");
    let rejected = trace["samples"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| s["estimate"]["altimeter_rejected"] == true)
        .count();
    assert!(rejected > 100, "rejected in {rejected} samples");
    let (trace, _) = run_value(&value_of("nominal-robust.json"), 0).unwrap();
    assert!(
        trace["samples"]
            .as_array()
            .unwrap()
            .iter()
            .all(|s| s["estimate"]["altimeter_rejected"] == false)
    );
}

#[test]
fn robust_can_reject_a_correct_altimeter_when_the_gnss_is_biased() {
    // Hypothesis H3 of the specification: the known failure mode of the robust policy.
    let (trace, v) = run_value(&value_of("gnss-bias-robust.json"), 0).unwrap();
    let rejected = trace["samples"]
        .as_array()
        .unwrap()
        .iter()
        .any(|s| s["estimate"]["altimeter_rejected"] == true);
    assert!(rejected);
    assert_eq!(v["outcome"], "hard_landing");
    assert_eq!(requirement(&v, "R1_vertical_speed")["pass"], false);
}

#[test]
fn the_baseline_holds_the_last_altimeter_value_during_a_dropout() {
    let (trace, _) = run_value(&value_of("altimeter-dropout.json"), 0).unwrap();
    let in_window: Vec<&Value> = trace["samples"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| {
            let t = s["t_s"].as_f64().unwrap();
            (18.5..21.0).contains(&t)
        })
        .collect();
    assert!(in_window.len() > 20);
    assert!(
        in_window
            .iter()
            .all(|s| s["observation"]["altimeter_m"].is_null())
    );
    let z = |s: &Value| s["estimate"]["position_m"][2].as_f64().unwrap();
    let truth = |s: &Value| s["truth"]["position_m"][2].as_f64().unwrap();
    assert!((z(in_window[0]) - z(in_window[in_window.len() - 1])).abs() < 1.0);
    assert!(truth(in_window[0]) - truth(in_window[in_window.len() - 1]) > 100.0);
    // The window opens at 18 s, after the ignition, and is still open at the touchdown.
    assert_eq!(
        event_kinds(&trace),
        ["ignition", "fault_start", "touchdown", "end"]
    );
}

#[test]
fn a_short_run_without_contact_reports_no_contact() {
    let mut case = value_of("nominal.json");
    case["duration_s"] = json!(10.0);
    let (trace, v) = run_value(&case, 0).unwrap();
    assert_eq!(v["outcome"], "no_contact");
    assert!(v["touchdown"].is_null());
    for r in v["requirements"].as_array().unwrap() {
        assert_eq!(
            (r["pass"].clone(), r["evaluated"].clone()),
            (json!(false), json!(false))
        );
        assert!(r["value"].is_null());
    }
    assert_eq!(invariant(&v, "S2_keep_out")["evaluated"], false);
    assert_eq!(invariant(&v, "S2_keep_out")["pass"], true);
    assert_eq!(
        trace["samples"].as_array().unwrap().last().unwrap()["kind"],
        "final"
    );
    assert_eq!(trace["summary"]["end_reason"], "duration");
    assert!(trace["summary"]["touchdown_t_s"].is_null());
    assert_eq!(event_kinds(&trace), ["ignition", "end"]);
}

#[test]
fn invalid_inputs_are_rejected_with_a_reason() {
    let reject = |edit: &dyn Fn(&mut Value)| -> String {
        let mut case = value_of("nominal.json");
        edit(&mut case);
        run_value(&case, 0).expect_err("must be rejected")
    };
    assert!(reject(&|c| c["schema"] = json!("other")).contains("schema"));
    assert!(reject(&|c| c["surprise"] = json!(1)).contains("invalid case"));
    assert!(reject(&|c| c["record_every"] = json!(5)).contains("multiple of the control period"));
    assert!(reject(&|c| c["record_every"] = json!(0)).contains("record_every"));
    assert!(reject(&|c| c["dt_s"] = json!(2.0)).contains("dt_s"));
    assert!(
        reject(&|c| c["requirements"]["r1_vertical_speed_mps"] = json!(4.0))
            .contains("pre-registered")
    );
    assert!(reject(&|c| c["requirements"]["s2_keep_out_m"] = json!(80.0)).contains("requirements"));
    assert!(
        reject(&|c| c["dispersion"]["position_m"] = json!([60.0, 30.0, 50.0]))
            .contains("dispersion")
    );
    assert!(
        reject(&|c| c["sensors"]["control_period_steps"] = json!(4)).contains("control_period")
    );
    assert!(
        reject(&|c| c["sensors"]["altimeter_sigma_m"] = json!(-1.0)).contains("altimeter_sigma")
    );
    assert!(reject(&|c| c["vehicle"]["throttle_min"] = json!(1.5)).contains("throttle_min"));
    assert!(reject(&|c| c["vehicle"]["dry_mass_kg"] = json!(0.0)).contains("dry_mass_kg"));
    assert!(
        reject(&|c| c["controller"]["target_vertical_speed_mps"] = json!(1.0))
            .contains("target_vertical_speed")
    );
    assert!(reject(&|c| c["controller"]["policy"] = json!("clever")).contains("invalid case"));
    assert!(
        reject(&|c| c["controller"]["gains"]["throttle_gain"] = json!(2.0))
            .contains("throttle_gain")
    );
    assert!(
        reject(&|c| c["controller"]["gains"]["altimeter_rejection_cycles"] = json!(0))
            .contains("altimeter_rejection_cycles")
    );

    let fault = |kind: &str, start: f64, end: f64, magnitude: f64| json!({"kind": kind, "start_s": start, "end_s": end, "magnitude": magnitude});
    let with = |f: Vec<Value>| move |c: &mut Value| c["faults"] = Value::Array(f.clone());
    assert!(
        reject(&with(vec![fault("altimeter_bias", 1.0, 5.0, 60.0)])).contains("registered range")
    );
    assert!(reject(&with(vec![fault("thrust_loss", 1.0, 5.0, 0.4)])).contains("registered range"));
    assert!(reject(&with(vec![fault("gnss_dropout", 1.0, 2.0, 0.0)])).contains("window"));
    assert!(reject(&with(vec![fault("gimbal_stuck", 1.0, 6.0, 0.0)])).contains("window"));
    assert!(reject(&with(vec![fault("gnss_dropout", 1.0, 5.0, 3.0)])).contains("must be 0"));
    assert!(reject(&with(vec![fault("gnss_bias", 5.0, 3.0, 10.0)])).contains("after start_s"));
    assert!(reject(&with(vec![fault("gnss_bias", 1.005, 5.0, 10.0)])).contains("whole number"));
    assert!(reject(&with(vec![fault("gnss_bias", 1.0, 99.0, 10.0)])).contains("end_s"));
    assert!(
        reject(&with(vec![
            fault("gnss_bias", 1.0, 5.0, 10.0),
            fault("gnss_bias", 6.0, 9.0, 10.0)
        ]))
        .contains("appears twice")
    );
    assert!(reject(&with(vec![fault("meteor", 1.0, 5.0, 10.0)])).contains("invalid case"));
    assert!(
        reject(&|c| c["faults"] = Value::Array(vec![fault("gnss_bias", 1.0, 5.0, 10.0); 11]))
            .contains("more than")
    );
}

#[test]
fn every_pre_registered_value_is_pinned_and_rejects_a_change() {
    // (pointer into the case, a different value, the field the error must name)
    let changes: Vec<(&str, Value, &str)> = vec![
        ("/dt_s", json!(0.02), "dt_s"),
        (
            "/vehicle/dry_mass_kg",
            json!(23_000.0),
            "vehicle.dry_mass_kg",
        ),
        (
            "/vehicle/propellant_mass_kg",
            json!(9_000.0),
            "vehicle.propellant_mass_kg",
        ),
        (
            "/vehicle/dry_cm_station_m",
            json!(15.0),
            "vehicle.dry_cm_station_m",
        ),
        (
            "/vehicle/propellant_cm_station_m",
            json!(8.0),
            "vehicle.propellant_cm_station_m",
        ),
        (
            "/vehicle/dry_inertia_kgm2",
            json!([40_000.0, 1_800_000.0, 1_800_001.0]),
            "vehicle.dry_inertia_kgm2",
        ),
        (
            "/vehicle/propellant_inertia_kgm2",
            json!([12_000.0, 250_001.0, 250_000.0]),
            "vehicle.propellant_inertia_kgm2",
        ),
        (
            "/vehicle/max_thrust_n",
            json!(900_000.0),
            "vehicle.max_thrust_n",
        ),
        ("/vehicle/isp_s", json!(300.0), "vehicle.isp_s"),
        (
            "/vehicle/drag_coefficient",
            json!(0.9),
            "vehicle.drag_coefficient",
        ),
        (
            "/vehicle/reference_area_m2",
            json!(11.0),
            "vehicle.reference_area_m2",
        ),
        ("/vehicle/throttle_min", json!(0.5), "vehicle.throttle_min"),
        (
            "/vehicle/throttle_rate_per_s",
            json!(2.0),
            "vehicle.throttle_rate_per_s",
        ),
        (
            "/vehicle/gimbal_max_tan",
            json!(0.15),
            "vehicle.gimbal_max_tan",
        ),
        (
            "/vehicle/gimbal_rate_tan_per_s",
            json!(0.4),
            "vehicle.gimbal_rate_tan_per_s",
        ),
        (
            "/sensors/altimeter_sigma_m",
            json!(0.2),
            "sensors.altimeter_sigma_m",
        ),
        (
            "/sensors/gnss_position_sigma_m",
            json!(1.0),
            "sensors.gnss_position_sigma_m",
        ),
        (
            "/sensors/gnss_velocity_sigma_mps",
            json!(0.1),
            "sensors.gnss_velocity_sigma_mps",
        ),
        (
            "/sensors/imu_attitude_sigma_rad",
            json!(2e-4),
            "sensors.imu_attitude_sigma_rad",
        ),
        (
            "/sensors/imu_rate_sigma_radps",
            json!(2e-4),
            "sensors.imu_rate_sigma_radps",
        ),
        (
            "/sensors/imu_accel_sigma_mps2",
            json!(0.04),
            "sensors.imu_accel_sigma_mps2",
        ),
        (
            "/sensors/control_period_steps",
            json!(4),
            "sensors.control_period_steps",
        ),
        (
            "/sensors/gnss_period_cycles",
            json!(10),
            "sensors.gnss_period_cycles",
        ),
        (
            "/environment/gravity_mps2",
            json!(3.7),
            "environment.gravity_mps2",
        ),
        (
            "/environment/atmosphere",
            Value::Null,
            "environment.atmosphere",
        ),
        (
            "/environment/atmosphere/density_kgpm3",
            json!(1.0),
            "environment.atmosphere",
        ),
        (
            "/environment/atmosphere/scale_height_m",
            json!(7_000.0),
            "environment.atmosphere",
        ),
        (
            "/initial/position_m",
            json!([80.0, 0.0, 2_999.0]),
            "initial.position_m",
        ),
        (
            "/initial/velocity_mps",
            json!([-12.0, 0.0, -199.0]),
            "initial.velocity_mps",
        ),
        (
            "/initial/attitude",
            json!([1.0, 0.0, 0.0, 0.0]),
            "initial.attitude",
        ),
        (
            "/initial/angular_velocity_radps",
            json!([0.0, 0.005, 0.0]),
            "initial.angular_velocity_radps",
        ),
        (
            "/controller/target_vertical_speed_mps",
            json!(-1.0),
            "controller.target_vertical_speed_mps",
        ),
        ("/dispersion/thrust_fraction", json!(0.05), "dispersion"),
        (
            "/requirements/r1_vertical_speed_mps",
            json!(4.0),
            "requirements",
        ),
    ];
    for name in ["nominal.json", "gimbal-stuck-robust.json"] {
        for (pointer, value, field) in &changes {
            let mut case = value_of(name);
            *case.pointer_mut(pointer).unwrap() = value.clone();
            let err = run_value(&case, 0).expect_err(pointer);
            assert!(
                err.contains(field) && err.contains("pre-registered"),
                "{pointer}: {err}"
            );
        }
    }
    // What is not pinned stays free: the policy, the gains, the duration and the sampling.
    let mut case = value_of("nominal.json");
    case["duration_s"] = json!(5.0);
    case["record_every"] = json!(20);
    case["controller"]["policy"] = json!("robust");
    case["controller"]["gains"]["throttle_gain"] = json!(0.7);
    run_value(&case, 0).expect("controller choices and the duration are free");
}

fn fault(kind: &str, start: f64, end: f64, magnitude: f64) -> Value {
    json!({"kind": kind, "start_s": start, "end_s": end, "magnitude": magnitude})
}

/// `(kind, acted)` for each fault of a nominal baseline run (seed 0) with these faults.
fn acted_of(faults: Vec<Value>) -> Vec<(String, bool)> {
    let mut case = value_of("nominal.json");
    case["faults"] = Value::Array(faults);
    let (_, v) = run_value(&case, 0).unwrap();
    v["faults"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| {
            (
                f["kind"].as_str().unwrap().to_string(),
                f["acted"].as_bool().unwrap(),
            )
        })
        .collect()
}

fn acted_alone(f: Value) -> bool {
    let kind = f["kind"].as_str().unwrap().to_string();
    let got = acted_of(vec![f]);
    assert_eq!(got[0].0, kind);
    got[0].1
}

#[test]
fn a_fault_window_that_changes_nothing_is_reported_as_not_acted() {
    // Nominal baseline: the ignition is commanded at about 4.3 s and the contact is at 23.6 s.
    for f in [
        // No thrusting step inside the window.
        fault("thrust_loss", 1.0, 2.0, 0.15),
        fault("gimbal_stuck", 1.0, 2.5, 0.0),
        // The ignition is commanded outside the window, so it is not delayed.
        fault("ignition_delay", 10.0, 20.0, 0.5),
        // The run ends at the contact before the window opens: nothing was biased or masked.
        fault("altimeter_bias", 30.0, 40.0, 10.0),
        fault("altimeter_dropout", 30.0, 38.0, 0.0),
        fault("gnss_dropout", 30.0, 38.0, 0.0),
        fault("gnss_bias", 30.0, 40.0, 10.0),
        fault("imu_accel_bias", 30.0, 40.0, 0.2),
        // One step, 101, which is not a control cycle (the control cycles are the even steps).
        fault("altimeter_bias", 1.01, 1.02, 10.0),
        fault("imu_accel_bias", 1.01, 1.02, 0.2),
        // Step 102 is a control cycle but not a GNSS cycle (those are steps 0, 10, 20, ...).
        fault("gnss_bias", 1.02, 1.03, 10.0),
    ] {
        assert!(!acted_alone(f.clone()), "{f}");
    }

    // The same faults, with a window that does reach an effect, act.
    for f in [
        fault("thrust_loss", 5.26, 40.0, 0.15),
        fault("gimbal_stuck", 10.0, 12.0, 0.0),
        fault("ignition_delay", 2.0, 8.0, 0.5),
        fault("altimeter_bias", 0.0, 40.0, 10.0),
        fault("altimeter_dropout", 18.0, 24.0, 0.0),
        fault("gnss_dropout", 10.0, 16.0, 0.0),
        fault("gnss_bias", 0.0, 40.0, 10.0),
        fault("imu_accel_bias", 0.0, 40.0, 0.2),
        // A single GNSS cycle (step 100) and a single control cycle.
        fault("gnss_bias", 1.0, 1.01, 10.0),
        fault("altimeter_bias", 1.0, 1.01, 10.0),
        fault("imu_accel_bias", 1.0, 1.01, 0.2),
    ] {
        assert!(acted_alone(f.clone()), "{f}");
    }
}

#[test]
fn a_bias_hidden_by_a_dropout_of_the_same_sensor_did_not_act() {
    // Biased samples exist only where the sensor still reports: here the bias window lies
    // inside the dropout window.
    assert_eq!(
        acted_of(vec![
            fault("altimeter_bias", 6.0, 7.0, 10.0),
            fault("altimeter_dropout", 5.0, 8.0, 0.0)
        ]),
        [
            ("altimeter_bias".to_string(), false),
            ("altimeter_dropout".to_string(), true)
        ]
    );
    assert_eq!(
        acted_of(vec![
            fault("gnss_bias", 6.0, 7.0, 10.0),
            fault("gnss_dropout", 5.0, 8.0, 0.0)
        ]),
        [
            ("gnss_bias".to_string(), false),
            ("gnss_dropout".to_string(), true)
        ]
    );
    // A bias window that sticks out of the dropout window does act.
    assert_eq!(
        acted_of(vec![
            fault("altimeter_bias", 6.0, 9.0, 10.0),
            fault("altimeter_dropout", 5.0, 8.0, 0.0)
        ])[0],
        ("altimeter_bias".to_string(), true)
    );
}

#[test]
fn the_verifier_recomputes_the_contact_and_ignores_the_stored_interpolation() {
    let case: LandingCase = serde_json::from_slice(&bytes_of("altimeter-bias.json")).unwrap();
    let prep = prepare_landing(&case, 0).unwrap();
    let run = simulate_landing(&prep).unwrap();
    let honest = serde_json::to_vec(&verify(&prep, &run.log)).unwrap();
    assert_eq!(json_of(&honest)["outcome"], "hard_landing");

    // Replace the simulation's interpolated contact by a perfect soft landing with another
    // fraction and instant: the verdicts, the touchdown report and every number stay the same.
    let mut log = run.log.clone();
    let td = log.touchdown.as_mut().unwrap();
    let soft = State {
        v: Vec3::ZERO,
        w: Vec3::ZERO,
        ..td.state
    };
    (td.state, td.fraction, td.t_s) = (soft, 0.25, 1.0);
    log.end_state = soft;
    assert_eq!(serde_json::to_vec(&verify(&prep, &log)).unwrap(), honest);

    // A contact that the states around the step do not support is no contact.
    let mut log = run.log.clone();
    log.touchdown.as_mut().unwrap().after = log.steps[0].state;
    let v = json_of(&serde_json::to_vec(&verify(&prep, &log)).unwrap());
    assert_eq!(v["outcome"], "no_contact");
}

fn vv_rocket(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_vv-rocket"))
        .args(args)
        .output()
        .unwrap()
}

#[test]
fn the_land_command_uses_the_documented_exit_codes() {
    let case = landing_path("nominal.json");
    let case = case.to_str().unwrap();
    let bad = landing_path("altimeter-bias.json");
    let bad = bad.to_str().unwrap();
    let out = scratch("cli-ok");
    let ok = vv_rocket(&[
        "land",
        case,
        "--seed",
        "0",
        "--output",
        out.to_str().unwrap(),
    ]);
    assert_eq!(
        ok.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&ok.stderr)
    );
    let printed = json_of(&ok.stdout);
    assert_eq!(printed["outcome"], "landed");
    let replayed = vv_rocket(&["replay", out.to_str().unwrap()]);
    assert_eq!(replayed.status.code(), Some(0));
    assert_eq!(json_of(&replayed.stdout)["status"], "verified");
    // Never overwrites: a second run into the same directory is an input error.
    let again = vv_rocket(&[
        "land",
        case,
        "--seed",
        "0",
        "--output",
        out.to_str().unwrap(),
    ]);
    assert_eq!(again.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&again.stderr).contains("already exists"));

    // A hard landing exits 2 and still writes the artifacts, which replay.
    let out2 = scratch("cli-fail");
    let failed = vv_rocket(&[
        "land",
        bad,
        "--seed",
        "0",
        "--output",
        out2.to_str().unwrap(),
    ]);
    assert_eq!(failed.status.code(), Some(2));
    assert_eq!(json_of(&failed.stdout)["outcome"], "hard_landing");
    assert!(out2.join("verification.json").exists());
    assert_eq!(
        vv_rocket(&["replay", out2.to_str().unwrap()]).status.code(),
        Some(0)
    );
    fs::write(out2.join("trace.json"), "{}").unwrap();
    assert_eq!(
        vv_rocket(&["replay", out2.to_str().unwrap()]).status.code(),
        Some(1)
    );

    // Usage and input errors.
    let out3 = scratch("cli-usage");
    let o3 = out3.to_str().unwrap();
    assert_eq!(
        vv_rocket(&["land", case, "--seed", "x", "--output", o3])
            .status
            .code(),
        Some(3)
    );
    assert_eq!(vv_rocket(&["land", case]).status.code(), Some(3));
    assert_eq!(
        vv_rocket(&["land", "missing.json", "--seed", "0", "--output", o3])
            .status
            .code(),
        Some(3)
    );
    for d in [out, out2, out3] {
        let _ = fs::remove_dir_all(d);
    }
}

#[test]
fn every_demo_case_is_valid_and_runs_for_seeds_zero_and_one() {
    let mut names: Vec<String> = fs::read_dir(landing_path(""))
        .unwrap()
        .map(|e| e.unwrap().file_name().into_string().unwrap())
        .filter(|n| n.ends_with(".json"))
        .collect();
    names.sort();
    assert!(names.len() >= 6, "{names:?}");
    for name in names {
        for seed in [0, 1] {
            let art = artifacts(&bytes_of(&name), seed).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert!(["landed", "hard_landing", "no_contact"].contains(&art.outcome));
            // A demonstration fault that changed nothing would be a case that proves nothing.
            for f in json_of(&art.verification)["faults"].as_array().unwrap() {
                assert_eq!(f["acted"], true, "{name} seed {seed}: {f}");
            }
        }
    }
}

#[test]
fn m9_demo_traces_are_byte_identical_after_m91() {
    // SHA-256 of `trace.json` of every case that existed before the M9.1 changes (18 cases, seeds 0
    // and 1), recorded with the build that preceded them. The new policies, flags, fault kinds and
    // the invariant `S5` must not change any byte of a trace of `baseline` or `robust`.
    for (name, seed, want) in [
        (
            "altimeter-bias.json",
            0,
            "f6e1fa7ae1f26b78b8146a9a242fbbaa1656e8153b15ad071a401f0aec965d7e",
        ),
        (
            "altimeter-bias.json",
            1,
            "3b30677cc5be826da8a56d871c6bd46bcf90e54c1e5905485112d7a60a108213",
        ),
        (
            "altimeter-bias-robust.json",
            0,
            "2321c82f522e727984cd10b04f4f15840eb4c90f1ca84c74b5a0b6b6db254159",
        ),
        (
            "altimeter-bias-robust.json",
            1,
            "bdfe179c3d0ffca12d304b4b0de59c9f411eed8b59a25bc15304d5a0e54279ae",
        ),
        (
            "altimeter-dropout.json",
            0,
            "eefd91c7fde6278454823fad75d8ad36c742920cf537447a8a435fe5b7f0032e",
        ),
        (
            "altimeter-dropout.json",
            1,
            "8d9280d08baa30c668bb9b6c987ca31277608134b12de47cd2bcef61e717876d",
        ),
        (
            "altimeter-dropout-robust.json",
            0,
            "fd8e5da562cc6cae8dcb844f226a81de36f7e9b6405b72bbe1231f5045fbb8a2",
        ),
        (
            "altimeter-dropout-robust.json",
            1,
            "1359b803b5c76777f82eab1ff59ea1ace2ad640e987266439ccab5143c96129b",
        ),
        (
            "gimbal-stuck.json",
            0,
            "f73abfe499faeeafb1cd752e7a40f2e59cda15430e9f848cb4102aa79f534b43",
        ),
        (
            "gimbal-stuck.json",
            1,
            "3d56c63b334b4e759890ff1b1cb880bdfa4ee5682ab232a1cb3f0f1109d8dd90",
        ),
        (
            "gimbal-stuck-robust.json",
            0,
            "6b10f2cfbd446e9c9907f7b54a30ed4804a3bb1eb7fa5b677012ce634dde411a",
        ),
        (
            "gimbal-stuck-robust.json",
            1,
            "1390ae2c0f717e2e8f9444d23d0236e8340df68423210c8cfd922eae71457a20",
        ),
        (
            "gnss-bias.json",
            0,
            "18f20b90d7961669e5f0d404d28a754b52724d6135117668ef0178734013c956",
        ),
        (
            "gnss-bias.json",
            1,
            "0eb5db9eae7460290968994eb678a2ac1c7e2a699302866ee96b2de2990181d5",
        ),
        (
            "gnss-bias-robust.json",
            0,
            "2b31bb418ee9ec1e671017a4663f4c95c2df97d498eb41a041bb632c7d4f8103",
        ),
        (
            "gnss-bias-robust.json",
            1,
            "396a14bdf9b31a206865ea3015e7063f4babb9794c29a79064e4f2673a2f64c4",
        ),
        (
            "gnss-dropout.json",
            0,
            "c603b317f4ed165c6d84988495c39fbc6ae9abfb236c2e3d2b9dab294ea2b2b7",
        ),
        (
            "gnss-dropout.json",
            1,
            "90e5ba8bd79fa8c7913101a979d67b34f7ed1a4c9415ff89485dd63bb1849ed0",
        ),
        (
            "gnss-dropout-robust.json",
            0,
            "9ea039cf05bda6ee6e66fa54c68a7233f201d0fca6caf773815ea1a60b1430e6",
        ),
        (
            "gnss-dropout-robust.json",
            1,
            "1ee22eb06ccce913c5f2742f253b80f2bf41a896c04ff6f346fe58f9dad76587",
        ),
        (
            "ignition-delay.json",
            0,
            "0d8ffa6a52efe39f8b1bb8f3adbed2499fb3e4904867790876646ef72b415437",
        ),
        (
            "ignition-delay.json",
            1,
            "856dd6f0ea11166d5871ac85d22549df1622488b34f2e953f56e384126716b72",
        ),
        (
            "ignition-delay-robust.json",
            0,
            "aa9413c18f51cab5e9143d963f6bff577f4e781468cafd55cc72eeb03eac83c1",
        ),
        (
            "ignition-delay-robust.json",
            1,
            "a452ff7ae5417016d315417bdb72c14a697348ed1be50ee0679a51b79dd5c318",
        ),
        (
            "imu-accel-bias.json",
            0,
            "c5f4df1eb004b20cf8573321b133a26ac4ced9311257a0424fe2a11287118c86",
        ),
        (
            "imu-accel-bias.json",
            1,
            "0c497f851c5376034b164695bcb0b33899cc97a8859c0ea2608d66d052f71359",
        ),
        (
            "imu-accel-bias-robust.json",
            0,
            "b1e1aa8c4c3deadc90d1cd7723c3fd7a6ae821e7ca6c1420868916b10d3dd0e9",
        ),
        (
            "imu-accel-bias-robust.json",
            1,
            "4d5f1faba3f046c3fe14738861616efe9756f31afa591711ce27343e310e3733",
        ),
        (
            "nominal.json",
            0,
            "58035467c03016594951a311142f594e19559565619f54d1671b8497524cf780",
        ),
        (
            "nominal.json",
            1,
            "64263c6c86bde9d1fbb24aea9265475ca653226a6065e4c8547f2b949a2f5a59",
        ),
        (
            "nominal-robust.json",
            0,
            "ffa6b96916380de6ab7bdec36c2551e5f9a12282e99e062f8e182533487dddfd",
        ),
        (
            "nominal-robust.json",
            1,
            "2c3fbf481662da09e0c19dc0b5a6f003db64c97935e8b4703cd3f1b3bb3c37bf",
        ),
        (
            "thrust-loss.json",
            0,
            "87fec24a6c97af84ba50567eaa4d9a2035573b013b8b719cef8f2190de5c9687",
        ),
        (
            "thrust-loss.json",
            1,
            "6d8ed9a544acd527501f175857d517152308a47c3f819e0d62d2331308025eb5",
        ),
        (
            "thrust-loss-robust.json",
            0,
            "cd71ede285dee7e3801bb0bbc04cb51f489bf66127b476dfa40cec30535e716b",
        ),
        (
            "thrust-loss-robust.json",
            1,
            "ad659ea943243aa4ea848c95838ef13c9115a4cd74a96f044ceee130de643e2a",
        ),
    ] {
        let art = artifacts(&bytes_of(name), seed).unwrap();
        assert_eq!(sha256_hex(&art.trace), want, "{name} seed {seed}");
    }
}

#[test]
fn m91_demo_traces_are_pinned() {
    // SHA-256 of `trace.json` of the four M9.1 cases (seeds 0 and 1), recorded on Windows. CI runs
    // this test on Linux too, which is the cross-platform evidence for `guarded`, `baseline_guarded`
    // and the low-reading faults.
    for (name, seed, want) in [
        (
            "m91-nominal.json",
            0,
            "bd906bfa1ce893d4b0a156c99232d18a4808a566793e59b39523f1c4f4d7d381",
        ),
        (
            "m91-nominal.json",
            1,
            "7255fb9152daf34bff4aa2ba4da1ed15bf9d7655b5b90df0fd0a0fcfd532a241",
        ),
        (
            "gnss-bias-guarded.json",
            0,
            "91a21b24d4f2169a338729901f160e3cd37de5b65edacfc4d00d4671fa81dc04",
        ),
        (
            "gnss-bias-guarded.json",
            1,
            "fe55f8ffea89e05b6e5946496a644e7716baa977bd9650520a5b3a028bdcf9e4",
        ),
        (
            "gnss-dropout-baseline-guarded.json",
            0,
            "aa92dbc1d6c52a04eec5eabad6d76ba17d2ed0ffd11ccc89e8fa98cec5ae0e1a",
        ),
        (
            "gnss-dropout-baseline-guarded.json",
            1,
            "2052494de738c84bee9e34d892270265e5fa1f2be165d0a85ed8da6ba1f61db1",
        ),
        (
            "altimeter-bias-low-guarded.json",
            0,
            "8a8b5109024b2b4f00e380d89f7cd8c94fa73915a98c66bb9789c4c1fdfc93e6",
        ),
        (
            "altimeter-bias-low-guarded.json",
            1,
            "696b6657f1ae76aaf08d185b103cff6d16de805c470f6a3a5fead948662573b8",
        ),
    ] {
        let art = artifacts(&bytes_of(name), seed).unwrap();
        assert_eq!(sha256_hex(&art.trace), want, "{name} seed {seed}");
    }
}

fn first_flag(v: &Value, key: &str) -> Option<u64> {
    v["controller_flags"][key]["step"].as_u64()
}

fn samples_with(trace: &Value, flag: &str, value: bool) -> usize {
    trace["samples"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| s["estimate"][flag] == value)
        .count()
}

#[test]
fn verification_v2_has_s5_and_a_labelled_controller_flags_block() {
    let (_, v) = run_value(&value_of("nominal.json"), 0).unwrap();
    let ids: Vec<&str> = v["invariants"]
        .as_array()
        .unwrap()
        .iter()
        .map(|i| i["id"].as_str().unwrap())
        .collect();
    assert_eq!(
        ids,
        [
            "S1_tilt_envelope",
            "S2_keep_out",
            "S3_axial_load",
            "S4_no_relight",
            "S5_no_powered_ascent"
        ]
    );
    let s5 = invariant(&v, "S5_no_powered_ascent");
    assert_eq!(
        (s5["limit"].as_f64(), s5["unit"].as_str()),
        (Some(5.0), Some("m"))
    );
    assert_eq!(s5["evaluated"], true);
    assert_eq!(s5["pass"], true);
    let flags = &v["controller_flags"];
    assert_eq!(
        flags["source"],
        "controller-reported; not used for any verdict"
    );
    for k in [
        "sensor_disagreement_first",
        "ascent_abort_first",
        "altimeter_rejected_first",
    ] {
        assert!(flags.get(k).is_some_and(Value::is_null), "{k}: {flags}");
    }
}

#[test]
fn the_m91_demo_cases_report_what_the_controller_said_apart_from_the_verdicts() {
    // Guarded, nominal: no flag, lands, and its trace carries the new estimate fields.
    for seed in [0, 1] {
        let (trace, v) = run_value(&value_of("m91-nominal.json"), seed).unwrap();
        assert_eq!(v["policy"], "guarded");
        assert_eq!(v["outcome"], "landed");
        assert_eq!(v["invariants_pass"], true);
        assert_eq!(first_flag(&v, "sensor_disagreement_first"), None);
        assert_eq!(first_flag(&v, "ascent_abort_first"), None);
        assert!(
            trace["samples"][0]["estimate"]
                .get("ascent_abort")
                .is_some()
        );
        assert_eq!(samples_with(&trace, "sensor_disagreement", true), 0);
    }

    // Guarded with a GNSS bias from 8 s: the disagreement is declared after the 5 cycles that
    // follow the start of the bias, and the vehicle touches down softly (`R1` met), which `robust`
    // does not (docs/m9-powered-landing.md).
    let (trace, v) = run_value(&value_of("gnss-bias-guarded.json"), 0).unwrap();
    let first = first_flag(&v, "sensor_disagreement_first").unwrap();
    assert!((800..900).contains(&first), "{first}");
    assert_eq!(first_flag(&v, "altimeter_rejected_first"), Some(first));
    assert!(samples_with(&trace, "sensor_disagreement", true) > 100);
    assert_eq!(requirement(&v, "R1_vertical_speed")["pass"], true);
    assert_eq!(v["invariants_pass"], true);

    // The same case with `robust` reports its rejection, which is the same detection, and has no
    // M9.1 field in its estimates.
    let (trace, v) = run_value(&value_of("gnss-bias-robust.json"), 0).unwrap();
    assert!(first_flag(&v, "altimeter_rejected_first").is_some());
    assert_eq!(first_flag(&v, "sensor_disagreement_first"), None);
    let est = &trace["samples"][0]["estimate"];
    assert!(est.get("sensor_disagreement").is_none() && est.get("ascent_abort").is_none());

    // `baseline` raises nothing.
    let (_, v) = run_value(&value_of("gnss-bias.json"), 0).unwrap();
    for k in [
        "sensor_disagreement_first",
        "ascent_abort_first",
        "altimeter_rejected_first",
    ] {
        assert_eq!(first_flag(&v, k), None, "{k}");
    }

    // Guarded with a low-reading altimeter: detected; the verdicts stay the verifier's.
    let (_, v) = run_value(&value_of("altimeter-bias-low-guarded.json"), 0).unwrap();
    assert!(first_flag(&v, "sensor_disagreement_first").is_some());
    assert_eq!(v["faults"][0]["kind"], "altimeter_bias_low");
    assert_eq!(v["faults"][0]["acted"], true);
}

#[test]
fn the_rise_cutoff_contains_the_m9_gnss_dropout_failure_but_s5_still_sees_it() {
    // The 20 `no_contact` executions of the M9 campaign: `baseline` keeps the last, large and
    // negative, GNSS velocity during the loss, brakes too hard and climbs with the engine lit.
    // This is the window of seed 1000 of the campaign.
    let mut case = value_of("nominal.json");
    case["faults"] = json!([fault("gnss_dropout", 14.9, 21.99, 0.0)]);
    let m9 = |policy: &str| {
        let mut c = case.clone();
        c["controller"]["policy"] = json!(policy);
        run_value(&c, 1000).unwrap()
    };

    let (trace, v) = m9("baseline");
    assert_eq!(v["outcome"], "no_contact");
    let s5 = invariant(&v, "S5_no_powered_ascent");
    assert_eq!(s5["pass"], false);
    assert!(s5["worst_value"].as_f64().unwrap() > 100.0);
    assert_eq!(s5["first_failure"]["cause"], json!(["gnss_dropout"]));
    assert!(!event_kinds(&trace).contains(&"ascent_abort"));

    // `baseline_guarded`: rule 2 cuts after the GNSS returns; no longer `no_contact`, but not a
    // recovery either: the climb is still over the S5 limit and the contact is hard.
    let (trace, v) = m9("baseline_guarded");
    assert_eq!(v["outcome"], "hard_landing");
    assert_eq!(invariant(&v, "S5_no_powered_ascent")["pass"], false);
    assert_eq!(requirement(&v, "R1_vertical_speed")["pass"], false);
    let kinds = event_kinds(&trace);
    let abort = kinds.iter().position(|k| *k == "ascent_abort").unwrap();
    assert_eq!(kinds[abort + 1], "cutoff", "{kinds:?}");
    let step = first_flag(&v, "ascent_abort_first").unwrap();
    assert_eq!(trace["events"][abort]["step"].as_u64(), Some(step));
    assert!(trace["events"][abort]["detail"]["estimated_vertical_velocity_mps"].is_number());
    // The flag is false before the cut and true after it.
    assert!(samples_with(&trace, "ascent_abort", false) > 100);
    assert!(samples_with(&trace, "ascent_abort", true) >= 1);
    assert_eq!(first_flag(&v, "sensor_disagreement_first"), None);

    // `guarded` inherits the estimator of `robust`, which did not climb: S5 holds, no flag.
    let (_, v) = m9("guarded");
    assert_eq!(v["outcome"], "landed");
    assert_eq!(invariant(&v, "S5_no_powered_ascent")["pass"], true);
    assert_eq!(first_flag(&v, "ascent_abort_first"), None);
}

fn trace_fault_names(trace: &Value) -> Vec<String> {
    trace["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["kind"] == "fault_start")
        .map(|e| e["detail"]["fault"].as_str().unwrap().to_string())
        .collect()
}

#[test]
fn the_low_bias_faults_subtract_their_magnitude_and_are_validated_like_the_other_biases() {
    // Observations of the same seed with and without the fault differ by exactly the magnitude,
    // before the controller can have changed the flight (the noise streams are always drawn).
    let clean = run_value(&value_of("nominal.json"), 0).unwrap().0;
    let mut case = value_of("nominal.json");
    case["faults"] = json!([
        fault("altimeter_bias_low", 0.0, 40.0, 27.5),
        fault("gnss_bias_low", 0.0, 40.0, 15.0)
    ]);
    let (faulty, v) = run_value(&case, 0).unwrap();
    for k in 0..10 {
        let (a, b) = (
            &clean["samples"][k]["observation"],
            &faulty["samples"][k]["observation"],
        );
        let d = |x: &Value, y: &Value| x.as_f64().unwrap() - y.as_f64().unwrap();
        assert!(
            (d(&b["altimeter_m"], &a["altimeter_m"]) + 27.5).abs() < 1e-9,
            "{k}"
        );
        for axis in [0, 2] {
            let diff = d(&b["gnss_position_m"][axis], &a["gnss_position_m"][axis]);
            assert!((diff + 15.0).abs() < 1e-9, "{k} axis {axis}: {diff}");
        }
        assert_eq!(a["gnss_position_m"][1], b["gnss_position_m"][1]);
    }
    assert_eq!(v["faults"][0]["kind"], "altimeter_bias_low");
    assert_eq!(v["faults"][1]["kind"], "gnss_bias_low");
    assert!(
        v["faults"]
            .as_array()
            .unwrap()
            .iter()
            .all(|f| f["acted"] == true)
    );
    assert_eq!(
        trace_fault_names(&faulty),
        ["altimeter_bias_low", "gnss_bias_low"]
    );

    // A positive and a negative bias of the same sensor are different kinds and may coexist; the
    // same kind twice may not.
    let reject = |faults: Vec<Value>| {
        let mut c = value_of("nominal.json");
        c["faults"] = Value::Array(faults);
        run_value(&c, 0)
    };
    assert!(
        reject(vec![
            fault("altimeter_bias", 0.0, 40.0, 10.0),
            fault("altimeter_bias_low", 0.0, 40.0, 10.0)
        ])
        .is_ok()
    );
    for kind in ["altimeter_bias_low", "gnss_bias_low"] {
        let err = reject(vec![
            fault(kind, 0.0, 10.0, 6.0),
            fault(kind, 12.0, 20.0, 6.0),
        ])
        .unwrap_err();
        assert!(err.contains("appears twice"), "{err}");
    }
    // Ranges: 5 to 50 m for the altimeter, 5 to 30 m for the GNSS, ends included.
    for (kind, low, high) in [
        ("altimeter_bias_low", 5.0, 50.0),
        ("gnss_bias_low", 5.0, 30.0),
    ] {
        assert!(
            reject(vec![fault(kind, 0.0, 40.0, low)]).is_ok(),
            "{kind} {low}"
        );
        assert!(
            reject(vec![fault(kind, 0.0, 40.0, high)]).is_ok(),
            "{kind} {high}"
        );
        for bad in [low - 0.1, high + 0.1, 0.0, -low] {
            let err = reject(vec![fault(kind, 0.0, 40.0, bad)]).unwrap_err();
            assert!(err.contains("registered range"), "{kind} {bad}: {err}");
        }
    }
    // `acted` follows the rule of the other sensor biases.
    assert!(!acted_alone(fault("altimeter_bias_low", 30.0, 40.0, 10.0)));
    assert!(!acted_alone(fault("gnss_bias_low", 30.0, 40.0, 10.0)));
    assert!(!acted_alone(fault("gnss_bias_low", 1.02, 1.03, 10.0)));
    assert!(acted_alone(fault("gnss_bias_low", 1.0, 1.01, 10.0)));
    assert!(acted_alone(fault("altimeter_bias_low", 1.0, 1.01, 10.0)));
    assert_eq!(
        acted_of(vec![
            fault("altimeter_bias_low", 6.0, 7.0, 10.0),
            fault("altimeter_dropout", 5.0, 8.0, 0.0)
        ])[0],
        ("altimeter_bias_low".to_string(), false)
    );
    assert_eq!(
        acted_of(vec![
            fault("gnss_bias_low", 6.0, 7.0, 10.0),
            fault("gnss_dropout", 5.0, 8.0, 0.0)
        ])[0],
        ("gnss_bias_low".to_string(), false)
    );
}

#[test]
fn the_new_policies_and_gains_are_optional_in_the_schema_and_validated() {
    // Existing case files carry no `ascent_abort_*` gains and still validate (defaults 1 m/s, 1 s).
    let case = value_of("nominal.json");
    assert!(
        case["controller"]["gains"]
            .get("ascent_abort_vz_mps")
            .is_none()
    );
    run_value(&case, 0).unwrap();
    for policy in ["guarded", "baseline_guarded"] {
        let mut c = case.clone();
        c["controller"]["policy"] = json!(policy);
        let (_, v) = run_value(&c, 0).unwrap();
        assert_eq!(v["policy"], policy);
    }
    // Explicit defaults give the same bytes as the omitted ones.
    let mut explicit = case.clone();
    explicit["controller"]["policy"] = json!("guarded");
    let mut omitted = explicit.clone();
    explicit["controller"]["gains"]["ascent_abort_vz_mps"] = json!(1.0);
    explicit["controller"]["gains"]["ascent_abort_time_s"] = json!(1.0);
    let a = artifacts(&serde_json::to_vec(&explicit).unwrap(), 5).unwrap();
    let b = artifacts(&serde_json::to_vec(&omitted).unwrap(), 5).unwrap();
    assert_eq!(a.trace, b.trace);
    // Out-of-range values are rejected with the field name.
    for (key, bad) in [
        ("ascent_abort_vz_mps", -1.0),
        ("ascent_abort_vz_mps", 1000.0),
        ("ascent_abort_time_s", 0.0),
        ("ascent_abort_time_s", 61.0),
    ] {
        omitted["controller"]["gains"][key] = json!(bad);
        let err = run_value(&omitted, 0).unwrap_err();
        assert!(err.contains(key), "{key} {bad}: {err}");
        omitted["controller"]["gains"]
            .as_object_mut()
            .unwrap()
            .remove(key);
    }
}

#[test]
fn m91_runs_replay_and_a_forged_controller_flag_is_rejected() {
    for (case, seed) in [
        ("gnss-bias-guarded.json", 0),
        ("gnss-dropout-baseline-guarded.json", 0),
        ("altimeter-bias-low-guarded.json", 1),
    ] {
        let dir = tamper_dir(&format!("m91-{seed}-{case}"), case, seed);
        let report = replay(&dir);
        assert_eq!(report.status, "verified", "{case}: {:?}", report.checks);
        // The flags block is part of the recomputed verification: forging it, with the manifest
        // hash forged to match, still differs from the recomputation.
        let v = fs::read_to_string(dir.join("verification.json")).unwrap();
        let forged = v.replacen(
            "\"sensor_disagreement_first\":",
            "\"sensor_disagreement_first_forged\":",
            1,
        );
        assert_ne!(forged, v);
        fs::write(dir.join("verification.json"), &forged).unwrap();
        let run = fs::read_to_string(dir.join("run.json")).unwrap();
        fs::write(
            dir.join("run.json"),
            run.replace(&sha256_hex(v.as_bytes()), &sha256_hex(forged.as_bytes())),
        )
        .unwrap();
        assert_eq!(
            replay_failures(&dir),
            [
                "recomputed verification equals the stored verification byte for byte",
                "run.json equals the regenerated manifest byte for byte"
            ]
        );
        let _ = fs::remove_dir_all(dir);
    }
}

#[test]
fn the_gnss_dropout_of_the_campaign_fails_end_to_end_under_baseline_guarded() {
    // Seed 1000, GNSS lost from 14.9 s to 21.99 s, run through the real simulator and verifier:
    // rule 2 contains the climb but does not recover the landing.
    let mut case = value_of("nominal.json");
    case["faults"] = json!([fault("gnss_dropout", 14.9, 21.99, 0.0)]);
    case["controller"]["policy"] = json!("baseline_guarded");
    let (_, v) = run_value(&case, 1000).unwrap();
    assert_eq!(v["outcome"], "hard_landing");
    assert_eq!(v["requirements_pass"], false);
    assert_eq!(v["invariants_pass"], false);
    let failed = |items: &str| -> Vec<&str> {
        v[items]
            .as_array()
            .unwrap()
            .iter()
            .filter(|r| r["pass"] == false)
            .map(|r| r["id"].as_str().unwrap())
            .collect()
    };
    assert_eq!(
        failed("requirements"),
        [
            "R1_vertical_speed",
            "R2_horizontal_speed",
            "R3_tilt",
            "R5_position"
        ]
    );
    assert_eq!(
        failed("invariants"),
        ["S2_keep_out", "S5_no_powered_ascent"]
    );
    let value = |r: &Value| r.as_f64().unwrap();
    assert!((value(&requirement(&v, "R1_vertical_speed")["value"]) - 68.24).abs() < 0.01);
    assert!((value(&requirement(&v, "R5_position")["value"]) - 51.08).abs() < 0.01);
    assert!((value(&invariant(&v, "S2_keep_out")["worst_value"]) - 51.08).abs() < 0.01);
    let s5 = invariant(&v, "S5_no_powered_ascent");
    assert!((value(&s5["worst_value"]) - 59.16).abs() < 0.01);
    // Each failing state counted once.
    assert_eq!(s5["failure_count"], 189);
}

#[test]
fn replay_refuses_stored_artifacts_over_the_size_cap() {
    for name in ["trace.json", "verification.json", "run.json"] {
        let dir = tamper_dir(&format!("oversize-{name}"), "nominal.json", 3);
        assert_eq!(replay(&dir).status, "verified");
        // A sparse file one byte over the cap: the check fails without reading it.
        let file = fs::OpenOptions::new()
            .write(true)
            .open(dir.join(name))
            .unwrap();
        file.set_len(vv_rocket::run::MAX_ARTIFACT_BYTES + 1)
            .unwrap();
        drop(file);
        let report = replay(&dir);
        assert_ne!(report.status, "verified", "{name}");
        let detail = format!("{:?}", report.checks);
        assert!(detail.contains("exceeds"), "{name}: {detail}");
    }
}
