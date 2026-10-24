//! Cancelamento opcional de comandos pendentes em *fallback* (M6), pela API pública.

use autonomous_systems_vv_lab::ControllerEvaluationOutcome;
use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::contracts::ContractSet;
use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;
use autonomous_systems_vv_lab::model::SafetyState;
use autonomous_systems_vv_lab::{replay_controller_evaluation, run_controller_evaluation};

/// Base M3 conhecida: perda de GPS nos ticks 4 a 10 e um comando atrasado 3 ticks no tick 4.
fn evaluate(cancel: bool) -> ControllerEvaluationOutcome {
    let scenario = autonomous_systems_vv_lab::parse_scenario(include_str!(
        "../scenarios/m3/delayed-after-fallback.json"
    ))
    .unwrap();
    let mut actuator =
        ActuatorConfig::from_json(include_str!("../scenarios/m3/actuator-delayed.json")).unwrap();
    actuator.cancel_pending_on_fallback = cancel;
    let contracts =
        ContractSet::from_json(include_str!("../scenarios/m3/contracts-nominal.json")).unwrap();
    run_controller_evaluation(
        scenario,
        42,
        ControllerPolicyV1::DominantAxis,
        actuator,
        contracts,
        MissionPolicy::default(),
    )
    .unwrap()
}

/// Ticks em que o veículo se deslocou com o controlador em *fallback*.
fn moved_in_fallback(outcome: &ControllerEvaluationOutcome) -> Vec<u32> {
    let mut previous = outcome.artifact.scenario.vehicle.start;
    let mut moved = Vec::new();
    for tick in &outcome.artifact.expected_report.telemetry {
        if tick.safety_state == SafetyState::Fallback && tick.truth_position != previous {
            moved.push(tick.tick);
        }
        previous = tick.truth_position;
    }
    moved
}

fn failed(outcome: &ControllerEvaluationOutcome, name: &str) -> bool {
    let invariant = outcome
        .artifact
        .expected_report
        .invariants
        .iter()
        .any(|invariant| invariant.name == name && !invariant.passed);
    let contract = outcome
        .verification
        .failures
        .iter()
        .any(|failure| failure.contract_id == name);
    invariant || contract
}

#[test]
fn default_behaviour_still_moves_during_fallback() {
    let outcome = evaluate(false);
    assert!(!moved_in_fallback(&outcome).is_empty());
    assert!(failed(&outcome, "safe_fallback") || failed(&outcome, "no_motion_in_fallback"));
}

#[test]
fn cancellation_prevents_motion_during_fallback() {
    let outcome = evaluate(true);
    assert_eq!(moved_in_fallback(&outcome), Vec::<u32>::new());
    assert!(!failed(&outcome, "safe_fallback"));
    assert!(!failed(&outcome, "no_motion_in_fallback"));
    assert!(
        outcome
            .verification
            .actuator_config
            .cancel_pending_on_fallback
    );
}

#[test]
fn cancellation_is_deterministic_and_replayable() {
    let first = evaluate(true);
    assert_eq!(first.manifest, evaluate(true).manifest);
    let replayed = replay_controller_evaluation(
        &text(&first.manifest),
        &text(&first.artifact),
        &text(&first.artifact.expected_report),
        &text(&first.mission),
        &text(&first.verification),
    )
    .unwrap();
    assert_eq!(replayed.manifest, first.manifest);
}

fn text<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_string(value).unwrap()
}
