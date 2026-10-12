use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use autonomous_systems_vv_lab::controller::{
    ControllerInput, ControllerPolicyV1, choose_action, choose_action_v1,
};
use autonomous_systems_vv_lab::actuator::{
    ActuatorConfig, ActuatorFault, ActuatorFaultWindow,
};
use autonomous_systems_vv_lab::contracts::ContractSet;
use autonomous_systems_vv_lab::model::{
    Action, Bounds, Heading, MissionState, ObservedTelemetry, Point, RunStatus, SafetyState,
};
use autonomous_systems_vv_lab::mission_analysis::{MissionOutcome, MissionPolicy};
use autonomous_systems_vv_lab::{
    ArtifactReference, ComparisonPolicyReferences, ControllerEvaluationManifest,
    create_controller_comparison,
    parse_controller_comparison_artifact, parse_controller_evaluation_manifest,
    replay_controller_evaluation, run_controller_evaluation, run_verified_scenario,
};
use sha2::{Digest, Sha256};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct TempDirectory(PathBuf);

impl TempDirectory {
    fn new() -> Self {
        let id = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "vv-lab-m4-{}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create temporary test directory");
        Self(path)
    }
}

impl Drop for TempDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn input<'a>(
    bounds: &'a Bounds,
    observation: Option<&'a ObservedTelemetry>,
    target: Option<Point>,
    mission_state: MissionState,
    safety_state: SafetyState,
) -> ControllerInput<'a> {
    ControllerInput {
        mission_state,
        safety_state,
        observed: observation,
        target,
        step_mm: 10,
        bounds,
        confidence_threshold_permille: 500,
    }
}

fn nominal_observation(position: Point) -> ObservedTelemetry {
    ObservedTelemetry {
        position,
        sample_tick: 1,
        age_ticks: 0,
        base_confidence_permille: 1000,
        confidence_permille: 1000,
        fresh: true,
    }
}

fn broad_bounds() -> Bounds {
    Bounds {
        min_x_mm: -100,
        max_x_mm: 100,
        min_y_mm: -100,
        max_y_mm: 100,
    }
}

#[test]
fn policies_intentionally_choose_different_axes() {
    let bounds = broad_bounds();
    let observation = nominal_observation(Point { x_mm: 0, y_mm: 0 });
    let controller_input = input(
        &bounds,
        Some(&observation),
        Some(Point { x_mm: 40, y_mm: 100 }),
        MissionState::Running,
        SafetyState::Nominal,
    );

    assert_eq!(
        choose_action_v1(ControllerPolicyV1::DominantAxis, &controller_input),
        Action::step(Heading::North, 10)
    );
    assert_eq!(
        choose_action_v1(ControllerPolicyV1::XFirst, &controller_input),
        Action::step(Heading::East, 10)
    );
}

#[test]
fn legacy_controller_is_the_dominant_axis_policy() {
    let bounds = broad_bounds();
    let observation = nominal_observation(Point { x_mm: 0, y_mm: 0 });
    let controller_input = input(
        &bounds,
        Some(&observation),
        Some(Point { x_mm: 40, y_mm: 100 }),
        MissionState::Running,
        SafetyState::Nominal,
    );

    assert_eq!(
        choose_action(&controller_input),
        choose_action_v1(ControllerPolicyV1::DominantAxis, &controller_input)
    );
}

#[test]
fn both_policies_share_completion_confidence_observation_target_and_bounds_guards() {
    let bounds = broad_bounds();
    let position = Point { x_mm: 0, y_mm: 0 };
    let observation = nominal_observation(position);
    let mut stale = observation.clone();
    stale.fresh = false;
    let mut uncertain = observation.clone();
    uncertain.confidence_permille = 499;

    let cases = [
        input(
            &bounds,
            Some(&observation),
            Some(Point { x_mm: 40, y_mm: 100 }),
            MissionState::Completed,
            SafetyState::Nominal,
        ),
        input(
            &bounds,
            Some(&observation),
            Some(Point { x_mm: 40, y_mm: 100 }),
            MissionState::Running,
            SafetyState::Fallback,
        ),
        input(
            &bounds,
            None,
            Some(Point { x_mm: 40, y_mm: 100 }),
            MissionState::Running,
            SafetyState::Nominal,
        ),
        input(
            &bounds,
            Some(&stale),
            Some(Point { x_mm: 40, y_mm: 100 }),
            MissionState::Running,
            SafetyState::Nominal,
        ),
        input(
            &bounds,
            Some(&uncertain),
            Some(Point { x_mm: 40, y_mm: 100 }),
            MissionState::Running,
            SafetyState::Nominal,
        ),
        input(
            &bounds,
            Some(&observation),
            None,
            MissionState::Running,
            SafetyState::Nominal,
        ),
    ];
    for controller_input in &cases {
        assert_eq!(
            choose_action_v1(ControllerPolicyV1::DominantAxis, controller_input),
            Action::hold()
        );
        assert_eq!(
            choose_action_v1(ControllerPolicyV1::XFirst, controller_input),
            Action::hold()
        );
    }

    let tight_bounds = Bounds {
        min_x_mm: 0,
        max_x_mm: 5,
        min_y_mm: 0,
        max_y_mm: 100,
    };
    let edge_observation = nominal_observation(position);
    let controller_input = input(
        &tight_bounds,
        Some(&edge_observation),
        Some(Point { x_mm: 40, y_mm: 100 }),
        MissionState::Running,
        SafetyState::Nominal,
    );
    assert_eq!(
        choose_action_v1(ControllerPolicyV1::DominantAxis, &controller_input),
        Action::hold()
    );
    assert_eq!(
        choose_action_v1(ControllerPolicyV1::XFirst, &controller_input),
        Action::hold()
    );
}

fn evaluation(policy: ControllerPolicyV1) -> autonomous_systems_vv_lab::ControllerEvaluationOutcome {
    let scenario = autonomous_systems_vv_lab::parse_scenario(include_str!(
        "../scenarios/m4/x-first-overshoot.json"
    ))
    .expect("M4 fixture is valid");
    let contracts = ContractSet::from_json(include_str!(
        "../scenarios/m3/contracts-nominal.json"
    ))
    .expect("M3 contract fixture is valid");
    run_controller_evaluation(
        scenario,
        42,
        policy,
        ActuatorConfig::default(),
        contracts,
        MissionPolicy::default(),
    )
    .expect("M4 evaluation runs")
}

#[test]
fn paired_policies_use_equal_external_calendars_and_show_the_axis_overshoot_effect() {
    let dominant = evaluation(ControllerPolicyV1::DominantAxis);
    let x_first = evaluation(ControllerPolicyV1::XFirst);
    let scenario = autonomous_systems_vv_lab::parse_scenario(include_str!(
        "../scenarios/m4/x-first-overshoot.json"
    ))
    .expect("M4 fixture is valid");
    let contracts = ContractSet::from_json(include_str!(
        "../scenarios/m3/contracts-nominal.json"
    ))
    .expect("M3 contract fixture is valid");
    let legacy = run_verified_scenario(
        scenario,
        42,
        ActuatorConfig::default(),
        contracts,
        MissionPolicy::default(),
        "vv-lab replay events.json".into(),
    )
    .expect("legacy M3 run with the default controller");
    assert_eq!(dominant.artifact, legacy.artifact);

    assert_eq!(
        dominant
            .manifest
            .normalized_exogenous_calendar_sha256,
        x_first
            .manifest
            .normalized_exogenous_calendar_sha256
    );
    assert_eq!(
        dominant
            .manifest
            .normalized_exogenous_calendar_version,
        1
    );
    assert_eq!(dominant.manifest.metrics.safety_status, RunStatus::Passed);
    assert_eq!(x_first.manifest.metrics.safety_status, RunStatus::Passed);
    assert_eq!(dominant.mission.outcome, MissionOutcome::Completed);
    assert_ne!(x_first.mission.outcome, MissionOutcome::Completed);
    assert!(dominant.manifest.metrics.waypoints_completed > x_first.manifest.metrics.waypoints_completed);
    assert_ne!(
        dominant.artifact.expected_report.telemetry[0].action,
        x_first.artifact.expected_report.telemetry[0].action
    );
    assert_ne!(
        dominant.artifact.expected_report.telemetry[1]
            .observed
            .as_ref()
            .expect("dominant observation")
            .position,
        x_first.artifact.expected_report.telemetry[1]
            .observed
            .as_ref()
            .expect("X-first observation")
            .position
    );
}

#[test]
fn calendar_hash_includes_ordered_active_actuator_fault_ids() {
    let no_fault = evaluation(ControllerPolicyV1::DominantAxis);
    let scenario = autonomous_systems_vv_lab::parse_scenario(include_str!(
        "../scenarios/m4/x-first-overshoot.json"
    ))
    .expect("M4 fixture is valid");
    let contracts = ContractSet::from_json(include_str!(
        "../scenarios/m3/contracts-nominal.json"
    ))
    .expect("M3 contract fixture is valid");
    let active_fault = ActuatorConfig {
        schema_version: 1,
        seed: 0,
        faults: vec![ActuatorFault::LostMovement {
            id: "calendar_fault".into(),
            windows: vec![ActuatorFaultWindow {
                start_tick: 2,
                end_tick: 2,
            }],
            probability_permille: 1000,
        }],
    };
    let with_fault = run_controller_evaluation(
        scenario.clone(),
        42,
        ControllerPolicyV1::DominantAxis,
        active_fault.clone(),
        contracts.clone(),
        MissionPolicy::default(),
    )
    .expect("M4 run with active actuator fault");
    let x_first_with_fault = run_controller_evaluation(
        scenario,
        42,
        ControllerPolicyV1::XFirst,
        active_fault,
        contracts,
        MissionPolicy::default(),
    )
    .expect("M4 X-first run with the same active actuator fault");

    assert_eq!(
        with_fault
            .manifest
            .normalized_exogenous_calendar_sha256,
        x_first_with_fault
            .manifest
            .normalized_exogenous_calendar_sha256
    );
    assert_ne!(
        no_fault.manifest.normalized_exogenous_calendar_sha256,
        with_fault
            .manifest
            .normalized_exogenous_calendar_sha256
    );
}

#[test]
fn m4_run_is_repeatable_and_explicit_replay_recomputes_every_artifact() {
    let first = evaluation(ControllerPolicyV1::XFirst);
    let repeated = evaluation(ControllerPolicyV1::XFirst);
    assert_eq!(first.artifact, repeated.artifact);
    assert_eq!(first.mission, repeated.mission);
    assert_eq!(first.verification, repeated.verification);
    assert_eq!(first.manifest, repeated.manifest);

    let events = serde_json::to_string(&first.artifact).expect("serialize events");
    let report = serde_json::to_string(&first.artifact.expected_report).expect("serialize report");
    let mission = serde_json::to_string(&first.mission).expect("serialize mission");
    let verification = serde_json::to_string(&first.verification).expect("serialize verification");
    let manifest = serde_json::to_string(&first.manifest).expect("serialize M4 manifest");
    let replay = replay_controller_evaluation(
        &manifest,
        &events,
        &report,
        &mission,
        &verification,
    )
    .expect("policy-aware M4 replay");
    assert_eq!(replay.manifest, first.manifest);
}

#[test]
fn m4_rejects_unknown_policy_versions_and_modified_references() {
    let outcome = evaluation(ControllerPolicyV1::DominantAxis);
    let encoded = serde_json::to_string(&outcome.manifest).expect("serialize M4 manifest");
    let mut value: serde_json::Value = serde_json::from_str(&encoded).expect("parse JSON");
    value["controller_id"] = serde_json::Value::String("future_policy".into());
    assert!(parse_controller_evaluation_manifest(&value.to_string()).is_err());

    let mut value: serde_json::Value = serde_json::from_str(&encoded).expect("parse JSON");
    value["interface_version"] = serde_json::json!(999);
    assert!(parse_controller_evaluation_manifest(&value.to_string()).is_err());

    let mut value: serde_json::Value = serde_json::from_str(&encoded).expect("parse JSON");
    value["event_artifact"]["sha256"] = serde_json::Value::String("0".repeat(64));
    assert!(parse_controller_evaluation_manifest(&value.to_string()).is_err());

    let mut value: serde_json::Value = serde_json::from_str(&encoded).expect("parse JSON");
    value["unexpected"] = serde_json::json!(true);
    assert!(parse_controller_evaluation_manifest(&value.to_string()).is_err());
}

#[test]
fn m4_comparison_is_strictly_versioned_and_binds_both_policy_runs() {
    let dominant = evaluation(ControllerPolicyV1::DominantAxis);
    let x_first = evaluation(ControllerPolicyV1::XFirst);
    let refs = |name: &str, result: &autonomous_systems_vv_lab::ControllerEvaluationOutcome| {
        ComparisonPolicyReferences {
            evaluation_manifest: ArtifactReference {
                path: format!("{name}/m4.json"),
                sha256: result.manifest.manifest_sha256.clone(),
            },
            event_artifact: ArtifactReference {
                path: format!("{name}/events.json"),
                sha256: result.manifest.event_artifact.sha256.clone(),
            },
            verification_artifact: ArtifactReference {
                path: format!("{name}/verification.json"),
                sha256: result.manifest.verification_artifact.sha256.clone(),
            },
        }
    };
    let comparison = create_controller_comparison(
        &dominant,
        &x_first,
        refs("dominant", &dominant),
        refs("xfirst", &x_first),
    )
    .expect("calendar-equivalent comparison");
    let encoded = serde_json::to_string(&comparison).expect("serialize comparison");
    assert_eq!(
        parse_controller_comparison_artifact(&encoded).expect("strict comparison parse"),
        comparison
    );
    assert_eq!(
        comparison.provenance.comparison_method,
        "independent_policy_replays_calendar_hash_v1"
    );
    let mut value: serde_json::Value = serde_json::from_str(&encoded).expect("parse JSON");
    value["external_calendar_equivalent"] = serde_json::json!(false);
    assert!(parse_controller_comparison_artifact(&value.to_string()).is_err());
}

#[test]
fn m4_comparison_rejects_a_consistently_resigned_false_calendar_hash() {
    let mut dominant = evaluation(ControllerPolicyV1::DominantAxis);
    let mut x_first = evaluation(ControllerPolicyV1::XFirst);
    let false_calendar_hash = if dominant
        .manifest
        .normalized_exogenous_calendar_sha256
        == "0".repeat(64)
    {
        "1".repeat(64)
    } else {
        "0".repeat(64)
    };
    for manifest in [&mut dominant.manifest, &mut x_first.manifest] {
        manifest.normalized_exogenous_calendar_sha256 = false_calendar_hash.clone();
        resign_manifest(manifest);
    }
    let refs = |name: &str, result: &autonomous_systems_vv_lab::ControllerEvaluationOutcome| {
        ComparisonPolicyReferences {
            evaluation_manifest: ArtifactReference {
                path: format!("{name}/m4.json"),
                sha256: result.manifest.manifest_sha256.clone(),
            },
            event_artifact: ArtifactReference {
                path: format!("{name}/events.json"),
                sha256: result.manifest.event_artifact.sha256.clone(),
            },
            verification_artifact: ArtifactReference {
                path: format!("{name}/verification.json"),
                sha256: result.manifest.verification_artifact.sha256.clone(),
            },
        }
    };

    assert!(
        create_controller_comparison(
            &dominant,
            &x_first,
            refs("dominant", &dominant),
            refs("xfirst", &x_first),
        )
        .is_err(),
        "comparison accepted two matching but false calendar hashes"
    );
}

fn resign_manifest(manifest: &mut ControllerEvaluationManifest) {
    manifest.manifest_sha256.clear();
    let digest = Sha256::digest(serde_json::to_vec(manifest).expect("serialize manifest"));
    manifest.manifest_sha256 = digest.iter().map(|byte| format!("{byte:02x}")).collect();
}

#[test]
fn m4_cli_runs_replays_compares_and_rejects_tampered_references() {
    let scratch = TempDirectory::new();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let scenario = root.join("scenarios/m4/x-first-overshoot.json");
    let contracts = root.join("scenarios/m3/contracts-nominal.json");
    let actuator = root.join("scenarios/m3/actuator-none.json");
    let binary = env!("CARGO_BIN_EXE_vv-lab");
    let dominant = scratch.0.join("dominant");
    let x_first = scratch.0.join("xfirst");

    for (policy, output) in [("dominant_axis", &dominant), ("x_first", &x_first)] {
        let result = Command::new(binary)
            .args([
                "run-m4",
                scenario.to_str().expect("scenario path"),
                "--seed",
                "42",
                "--controller",
                policy,
                "--contracts",
                contracts.to_str().expect("contract path"),
                "--actuator",
                actuator.to_str().expect("actuator path"),
                "--output",
                output.to_str().expect("output path"),
            ])
            .output()
            .expect("run M4 command");
        assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
    }

    let comparison = scratch.0.join("comparison.json");
    let result = Command::new(binary)
        .args([
            "compare-m4",
            dominant.join("m4.json").to_str().expect("dominant manifest"),
            x_first.join("m4.json").to_str().expect("X-first manifest"),
            "--output",
            comparison.to_str().expect("comparison path"),
        ])
        .output()
        .expect("compare M4 runs");
    assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
    let comparison: serde_json::Value =
        serde_json::from_slice(&fs::read(&comparison).expect("read comparison"))
            .expect("parse comparison");
    assert!(comparison["external_calendar_equivalent"].as_bool().unwrap_or(false));

    let replay = Command::new(binary)
        .arg("replay-m4")
        .arg(dominant.join("m4.json"))
        .output()
        .expect("replay M4 run");
    assert!(replay.status.success(), "{}", String::from_utf8_lossy(&replay.stderr));
    fs::write(dominant.join("report.json"), b"{}").expect("tamper report");
    let tampered = Command::new(binary)
        .arg("replay-m4")
        .arg(dominant.join("m4.json"))
        .output()
        .expect("replay tampered M4 run");
    assert!(!tampered.status.success());
}
