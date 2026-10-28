//! M9 powered landing: determinism, nominal landing for both policies, verdicts, input validation,
//! stored-run replay with tamper detection, the controller's isolation from the truth and the
//! cross-platform trace pins (docs/m9-powered-landing.md).

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::{Value, json};
use vv_rocket::landing_model::{LandingCase, prepare_landing};
use vv_rocket::landing_run::{artifacts, write_landing};
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
        // The controller keeps the nominal values.
        assert_eq!(p.controller.max_thrust_n, 845_000.0);
        assert_eq!(p.controller.propellant_mass_kg, 8000.0);
        moved |= r.x != 80.0;
    }
    assert!(moved);
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
    assert_eq!(v["schema"], "vv-rocket-landing-verification.v1");
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
fn running_out_of_propellant_is_a_flameout_and_a_hard_landing() {
    let mut case = value_of("nominal.json");
    case["vehicle"]["propellant_mass_kg"] = json!(500.0);
    let (trace, v) = run_value(&case, 0).unwrap();
    let kinds = event_kinds(&trace);
    assert!(kinds.contains(&"flameout"), "{kinds:?}");
    assert_ne!(v["outcome"], "landed");
    assert!(trace["summary"]["flameout_t_s"].as_f64().unwrap() > 0.0);
    assert!(
        trace["summary"]["propellant_remaining_kg"]
            .as_f64()
            .unwrap()
            < 5.0
    );
    // The truth mass never goes negative and the last samples show the engine out.
    let last = trace["samples"].as_array().unwrap().last().unwrap();
    assert_eq!(last["applied"]["engine"], "flameout");
}

#[test]
fn a_rising_vehicle_near_the_ground_is_cut_and_cannot_relight() {
    let mut case = value_of("nominal.json");
    case["initial"]["position_m"] = json!([0.0, 0.0, 100.0]);
    case["initial"]["velocity_mps"] = json!([0.0, 0.0, -10.0]);
    case["controller"]["gains"]["ignition_fraction"] = json!(0.1);
    case["controller"]["gains"]["cutoff_altitude_m"] = json!(1000.0);
    let (trace, v) = run_value(&case, 0).unwrap();
    let kinds = event_kinds(&trace);
    assert_eq!(kinds, ["ignition", "cutoff", "touchdown", "end"]);
    assert_eq!(v["outcome"], "hard_landing");
    assert_eq!(invariant(&v, "S4_no_relight")["pass"], true);
    assert_eq!(invariant(&v, "S4_no_relight")["worst_value"], 1.0);
    let last = trace["samples"].as_array().unwrap().last().unwrap();
    assert_eq!(last["applied"]["engine"], "cut");
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
    assert!(
        reject(&|c| c["initial"]["position_m"] = json!([0.0, 0.0, 5.0]))
            .contains("above the ground")
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
        reject(&|c| c["faults"] = Value::Array(vec![fault("gnss_bias", 1.0, 5.0, 10.0); 9]))
            .contains("more than")
    );
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
        }
    }
}
