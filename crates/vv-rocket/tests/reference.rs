//! Reference verification outcome, input validation, stored-run replay and cross-platform traces.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use vv_rocket::model::{Case, prepare};
use vv_rocket::run::{replay, trace_bytes, write_run};
use vv_rocket::sha256_hex;
use vv_rocket::sim::simulate;
use vv_rocket::verify::{base_case, run_all};

fn case_path(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("cases")
        .join(name)
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("vv-rocket-test-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    dir
}

#[test]
fn reference_cases_meet_their_active_criteria_and_keep_the_replaced_ones() {
    let report = run_all();
    let by_status = |status: &str| -> BTreeSet<(String, String)> {
        report
            .cases
            .iter()
            .flat_map(|c| {
                c.metrics
                    .iter()
                    .filter(move |m| m.status == status)
                    .map(move |m| (c.id.to_string(), m.name.clone()))
            })
            .collect()
    };
    let pair = |c: &str, m: &str| (c.to_string(), m.to_string());
    // The two first-run criteria that were not met stay in the report (docs/m8-rocket-dynamics.md):
    // case 4 as a failure superseded by the same limit at dt = 0.005 s, case 8 as invalid. If one
    // disappears or another failure appears, this test fails so that the change is examined.
    assert_eq!(
        by_status("fail"),
        BTreeSet::from([pair(
            "4-quaternions-and-frames",
            "max attitude error against q(t) at dt = 0.01 s (first run)"
        )]),
        "{}",
        serde_json::to_string_pretty(&report).unwrap()
    );
    assert_eq!(
        by_status("invalid"),
        BTreeSet::from([pair(
            "8-gimbal-torque",
            "final nose y_N component (must not be positive)"
        )])
    );
    for c in &report.cases {
        for m in &c.metrics {
            if m.status == "fail" {
                assert!(m.superseded_by.is_some(), "{} {}", c.id, m.name);
            }
            if m.status == "invalid" {
                assert!(
                    !m.pass && m.note.is_some(),
                    "an invalid criterion is never a pass"
                );
            }
        }
        assert_eq!(c.status, "PASS", "{}", c.id);
    }
    let case4 = report
        .cases
        .iter()
        .find(|c| c.id == "4-quaternions-and-frames")
        .unwrap();
    let superseded = case4
        .metrics
        .iter()
        .find(|m| m.superseded_by.is_some())
        .unwrap();
    assert_eq!(
        superseded.tolerance,
        Some(1e-12),
        "the limit is not loosened"
    );
    assert!(superseded.value > 1.6e-12 && superseded.value < 1.65e-12);
    for id in ["4-quaternions-and-frames", "8-gimbal-torque"] {
        let case = report.cases.iter().find(|c| c.id == id).unwrap();
        assert!(case.diagnosis.is_some(), "{id}");
    }
    assert_eq!(report.cases.len(), 12);
    assert_eq!(
        (report.cases_pass, report.cases_fail, report.cases_invalid),
        (12, 0, 0)
    );
    assert!(report.all_pass);
    assert_eq!(
        report.gaps.iter().map(|g| g.id).collect::<Vec<_>>(),
        ["flight-data-validation", "nasa-nesc-6dof"]
    );
}

#[test]
fn demo_traces_are_bit_identical_on_every_platform() {
    // Hashes of the trace bytes, pinned on Windows and checked on Linux by CI. They changed
    // with trace schema v2, which adds the measured validity ratio to the summary; the next test
    // shows that the samples and events are those of v1.
    for (name, want) in [
        (
            "ballistic.json",
            "4ab07bff1531a8231db467db00d58b5137554d78186e35ba6c65ae64eb48e0ba",
        ),
        (
            "propulsive_descent.json",
            "ab02afd3dedea329ddea7e176ef306f4891cbb73e035adfd3b560543eb45e665",
        ),
        (
            "attitude_dynamics.json",
            "8ff992f291627a398936418c6a708c2a723abc42880f480d1e5a46a181904f4b",
        ),
    ] {
        let (_, trace, _) = trace_bytes(&fs::read(case_path(name)).unwrap()).unwrap();
        assert_eq!(sha256_hex(&trace), want, "{name}");
    }
}

#[test]
fn measuring_the_validity_ratio_leaves_samples_and_events_unchanged() {
    // Hashes of the serialized (samples, events) pair, computed with the v1 simulator at 8b04960
    // before the measurement was added. A change here means the dynamics changed.
    for (name, want, ratio) in [
        (
            "ballistic.json",
            "fc13277b613dcf400e80da1fe8b3cb82f6f0705f0d9ded5939b767a1c0b6f585",
            (0.0, 0.0),
        ),
        (
            "propulsive_descent.json",
            "cf5e4e7ec63ba09b086514e5ecfde40ba0c390e7d2a115ee180977aa1a298767",
            (5.0e-5, 5.2e-5),
        ),
        (
            "attitude_dynamics.json",
            "247c2f4397dec1d2d0f7bbfa0242e444af92bcde1621526f9bc85088d0597ae7",
            (2.6e-3, 2.8e-3),
        ),
    ] {
        let case: Case = serde_json::from_slice(&fs::read(case_path(name)).unwrap()).unwrap();
        let run = simulate(&prepare(&case).unwrap(), false).unwrap();
        let bytes = serde_json::to_vec(&(&run.trace.samples, &run.trace.events)).unwrap();
        assert_eq!(sha256_hex(&bytes), want, "{name}");
        let eps = run.trace.summary.max_neglected_jet_ratio;
        assert!(ratio.0 <= eps && eps <= ratio.1, "{name}: {eps}");
    }
}

#[test]
fn demo_events_are_ordered_and_a_ground_crossing_is_not_a_landing() {
    let (_, trace, _) =
        trace_bytes(&fs::read(case_path("propulsive_descent.json")).unwrap()).unwrap();
    let trace: serde_json::Value = serde_json::from_slice(&trace).unwrap();
    let kinds: Vec<&str> = trace["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["kind"].as_str().unwrap())
        .collect();
    assert_eq!(kinds, ["burn_start", "ground_crossing", "end"]);
    let crossing = &trace["events"][1]["detail"];
    assert!(
        crossing["note"]
            .as_str()
            .unwrap()
            .contains("no contact model")
    );
    let steps: Vec<u64> = trace["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["step"].as_u64().unwrap())
        .collect();
    assert!(steps.windows(2).all(|w| w[0] <= w[1]));
    assert_eq!(trace["summary"]["end_reason"], "ground");
}

#[test]
fn stored_runs_replay_and_any_edit_is_rejected() {
    let dir = scratch("replay");
    write_run(&case_path("attitude_dynamics.json"), &dir).unwrap();
    assert_eq!(replay(&dir).status, "verified");
    assert!(
        write_run(&case_path("attitude_dynamics.json"), &dir).is_err(),
        "never overwrites"
    );

    // An edited trace whose manifest hash is re-forged still differs from the recomputation.
    let trace = fs::read_to_string(dir.join("trace.json")).unwrap();
    let edited = trace.replacen("\"propellant_kg\":300.0", "\"propellant_kg\":299.0", 1);
    assert_ne!(edited, trace);
    fs::write(dir.join("trace.json"), &edited).unwrap();
    let manifest = fs::read_to_string(dir.join("run.json")).unwrap();
    let old = sha256_hex(trace.as_bytes());
    fs::write(
        dir.join("run.json"),
        manifest.replace(&old, &sha256_hex(edited.as_bytes())),
    )
    .unwrap();
    let report = replay(&dir);
    assert_eq!(report.status, "failed");
    let failed: Vec<&str> = report
        .checks
        .iter()
        .filter(|c| !c.pass)
        .map(|c| c.name)
        .collect();
    // The re-forged trace hash in run.json also differs from the regenerated manifest.
    assert_eq!(
        failed,
        [
            "recomputed trace equals the stored trace byte for byte",
            "run.json equals the regenerated manifest byte for byte"
        ]
    );

    // A manifest that claims another outcome is rejected although its hashes are intact.
    let dir3 = scratch("replay-manifest");
    write_run(&case_path("ballistic.json"), &dir3).unwrap();
    let manifest = fs::read_to_string(dir3.join("run.json")).unwrap();
    let forged = manifest.replace("\"end_reason\": \"ground\"", "\"end_reason\": \"landed\"");
    assert_ne!(forged, manifest);
    fs::write(dir3.join("run.json"), forged).unwrap();
    let report = replay(&dir3);
    assert_eq!(report.status, "failed");
    assert!(
        report
            .checks
            .iter()
            .any(|c| !c.pass && c.name == "run.json equals the regenerated manifest byte for byte")
    );
    let _ = fs::remove_dir_all(dir3);

    // An edited case fails its hash.
    let dir2 = scratch("replay-case");
    write_run(&case_path("ballistic.json"), &dir2).unwrap();
    let case = fs::read_to_string(dir2.join("case.json")).unwrap();
    fs::write(dir2.join("case.json"), case.replace("0.3", "0.31")).unwrap();
    assert_eq!(replay(&dir2).status, "failed");
    assert_eq!(replay(&scratch("missing")).status, "failed");
    let _ = fs::remove_dir_all(dir);
    let _ = fs::remove_dir_all(dir2);
}

fn rejected(mutate: impl FnOnce(&mut Case)) -> String {
    let mut c = base_case(0.01, 1.0);
    c.vehicle.propellant_mass_kg = 1.0;
    c.vehicle.propellant_inertia_kgm2 = [0.1, 0.1, 0.1];
    c.vehicle.max_thrust_n = 100.0;
    assert!(prepare(&c).is_ok());
    mutate(&mut c);
    prepare(&c).expect_err("must be rejected")
}

#[test]
fn invalid_inputs_are_rejected_with_a_reason() {
    use vv_rocket::model::Burn;
    let burn = |start, end, throttle| Burn {
        start_s: start,
        end_s: end,
        throttle,
        direction_body: [1.0, 0.0, 0.0],
    };
    assert!(rejected(|c| c.dt_s = 2.0).contains("dt_s"));
    assert!(rejected(|c| c.duration_s = 0.015).contains("whole number"));
    assert!(rejected(|c| c.duration_s = 5000.0).contains("steps"));
    assert!(rejected(|c| c.record_every = 0).contains("record_every"));
    assert!(rejected(|c| c.vehicle.dry_mass_kg = 0.0).contains("dry_mass_kg"));
    assert!(rejected(|c| c.vehicle.dry_inertia_kgm2 = [1.0, 1.0, 3.0]).contains("triangle"));
    assert!(rejected(|c| c.vehicle.dry_inertia_kgm2 = [0.0, 1.0, 1.0]).contains("positive"));
    assert!(rejected(|c| c.initial.attitude = [1.0, 0.1, 0.0, 0.0]).contains("unit quaternion"));
    assert!(rejected(|c| c.burns = vec![burn(0.0, 0.505, 1.0)]).contains("whole number"));
    assert!(rejected(|c| c.burns = vec![burn(0.5, 0.2, 1.0)]).contains("after start_s"));
    assert!(
        rejected(|c| c.burns = vec![burn(0.0, 0.5, 1.0), burn(0.4, 0.8, 1.0)]).contains("overlaps")
    );
    assert!(rejected(|c| c.burns = vec![burn(0.0, 0.5, 1.5)]).contains("throttle"));
    assert!(
        rejected(|c| {
            c.vehicle.max_thrust_n = 1e6;
            c.burns = vec![burn(0.0, 1.0, 1.0)];
        })
        .contains("propellant")
    );
    assert!(
        rejected(|c| {
            c.burns = vec![burn(0.0, 0.5, 1.0)];
            c.burns[0].direction_body = [0.0, 0.0, 0.0];
        })
        .contains("non-zero")
    );
    assert!(rejected(|c| c.vehicle.propellant_mass_kg = 0.0).contains("zero without propellant"));
    assert!(rejected(|c| c.schema = "other".into()).contains("schema"));

    let unknown = r#"{"schema":"vv-rocket-case.v1","surprise":1}"#;
    assert!(
        trace_bytes(unknown.as_bytes())
            .unwrap_err()
            .contains("invalid case")
    );
}

#[test]
fn propellant_can_be_used_exactly_to_zero() {
    let mut c = base_case(0.01, 1.0);
    c.vehicle.propellant_mass_kg = 100.0 / (300.0 * vv_rocket::model::G0);
    c.vehicle.propellant_inertia_kgm2 = [0.1, 0.1, 0.1];
    c.vehicle.max_thrust_n = 100.0;
    c.burns = vec![vv_rocket::model::Burn {
        start_s: 0.0,
        end_s: 1.0,
        throttle: 1.0,
        direction_body: [1.0, 0.0, 0.0],
    }];
    let bytes = serde_json::to_vec(&c).unwrap();
    let (_, trace, summary) = trace_bytes(&bytes).unwrap();
    assert!(!trace.is_empty());
    assert!(summary["propellant_used_kg"].as_f64().unwrap() > 0.0);
}
