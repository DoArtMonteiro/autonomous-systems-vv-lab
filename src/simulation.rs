use std::time::Instant;

use crate::actuator::{ActuationOutcome, ActuatorConfig};
use crate::artifact::{
    artifact_digest, extract_exogenous, hash_serializable, verify_artifact_integrity,
};
use crate::contracts::ContractSet;
use crate::engine::{CoreOutput, execute, execute_with_actuator};
use crate::error::LabError;
use crate::mission_analysis::{MissionAnalysis, MissionOutcome, MissionPolicy, analyze_mission};
use crate::model::{EventRecord, EventsArtifact, RunReport, RunStatus, SCHEMA_VERSION, Scenario};
use crate::temporal::{ContractOutcome, evaluate};

mod provenance;
mod controller_evaluation;
mod controller_comparison;
mod verification;

use provenance::{build_failure_evidence, build_temporal_trace};
pub use controller_evaluation::{
    ArtifactReference, CONTROLLER_COMPARISON_SCHEMA_VERSION,
    CONTROLLER_EVALUATION_SCHEMA_VERSION, CONTROLLER_INTERFACE_VERSION,
    ControllerEvaluationManifest, ControllerEvaluationMetrics, ControllerEvaluationOutcome,
    ControllerEvaluationProvenance, POLICY_BEHAVIOR_VERSION, controller_id,
    parse_controller_evaluation_manifest, parse_controller_id, replay_controller_evaluation,
    run_controller_evaluation, source_sha256, validate_controller_evaluation_files,
    validate_relative_reference,
};
pub use controller_comparison::{
    ComparisonPolicyReferences, ComparisonProvenance, ControllerComparisonArtifact,
    ComparedController, create_controller_comparison, parse_controller_comparison_artifact,
};
pub use verification::{
    CommandAtTick, ContractFailureEvidence, CounterexampleTick, LinkedActuatorFaultEvent,
    VERIFICATION_SCHEMA_VERSION, VerificationArtifact, VerificationSummary,
    parse_verification_artifact,
};
use verification::{
    validate_reproduction_command, verification_digest, verify_verification_integrity,
};

const MAX_SCENARIO_BYTES: usize = 2 * 1024 * 1024;
const MAX_ARTIFACT_BYTES: usize = 128 * 1024 * 1024;

#[derive(Clone, Debug)]
pub struct ReplayOutcome {
    pub report: crate::model::RunReport,
}

#[derive(Clone, Debug)]
pub struct VerifiedRunOutcome {
    pub artifact: EventsArtifact,
    pub mission: MissionAnalysis,
    pub verification: VerificationArtifact,
}

#[derive(Clone, Debug)]
pub struct VerifiedReplayOutcome {
    pub report: RunReport,
    pub mission: MissionAnalysis,
    pub verification: VerificationArtifact,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct VerifiedBenchmarkResult {
    pub iterations: u32,
    pub simulated_ticks: u64,
    pub simulation_elapsed_micros: u64,
    pub artifact_elapsed_micros: u64,
    pub temporal_monitor_elapsed_micros: u64,
    pub final_hash: [u8; 32],
}

pub fn run_scenario(scenario: Scenario, seed: u64) -> Result<EventsArtifact, LabError> {
    scenario
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    let output = execute(&scenario, seed, None)?;
    Ok(assemble_artifact(
        scenario,
        seed,
        output.events,
        output.report,
    ))
}

/// Run M3 verification with the supplied actuator and declarative contracts.
/// The returned events/report artifacts retain their existing v1 schemas.
pub fn run_verified_scenario(
    scenario: Scenario,
    seed: u64,
    actuator_config: ActuatorConfig,
    contract_set: ContractSet,
    mission_policy: MissionPolicy,
    reproduction_command: String,
) -> Result<VerifiedRunOutcome, LabError> {
    validate_reproduction_command(&reproduction_command)?;
    scenario
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    actuator_config.validate(scenario.steps).map_err(LabError)?;
    contract_set
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    let mission_policy = mission_policy.validate()?;

    let output = execute_with_actuator(&scenario, seed, None, &actuator_config)?;
    let artifact = assemble_artifact(scenario, seed, output.events, output.report);
    let mission = analyze_mission(
        &artifact.scenario,
        &artifact.expected_report,
        mission_policy,
    )?;
    let verification = build_verification_artifact(
        &artifact,
        &output.actuation,
        actuator_config,
        contract_set,
        mission_policy,
        mission.outcome,
        reproduction_command,
    )?;
    Ok(VerifiedRunOutcome {
        artifact,
        mission,
        verification,
    })
}

pub fn replay_artifact(artifact: EventsArtifact) -> Result<ReplayOutcome, LabError> {
    let report = recompute_artifact(&artifact)?;
    Ok(ReplayOutcome { report })
}

/// Recompute the v1 artifact with its M3 actuator configuration and monitor,
/// then compare the complete regenerated sidecar.
pub fn replay_verified_artifact(
    artifact: EventsArtifact,
    verification: VerificationArtifact,
) -> Result<VerifiedReplayOutcome, LabError> {
    verify_verification_integrity(&verification, &artifact)?;
    let output = recompute_core(&artifact, Some(&verification.actuator_config))?;
    let mission = analyze_mission(
        &artifact.scenario,
        &output.report,
        verification.mission_policy,
    )?;
    if mission.outcome != verification.summary.mission_outcome {
        return Err(LabError(
            "recomputed mission outcome differs from verification.json".into(),
        ));
    }
    let recomputed = build_verification_artifact(
        &artifact,
        &output.actuation,
        verification.actuator_config.clone(),
        verification.contract_set.clone(),
        verification.mission_policy,
        mission.outcome,
        verification.reproduction_command.clone(),
    )?;
    if recomputed != verification {
        return Err(LabError(
            "recomputed temporal verification differs from verification.json".into(),
        ));
    }
    Ok(VerifiedReplayOutcome {
        report: output.report,
        mission,
        verification,
    })
}

/// Measure actuator-enabled simulation, artifact binding, and temporal
/// evaluation separately. JSON file I/O and Python orchestration are excluded.
pub fn benchmark_verified_scenario(
    scenario: &Scenario,
    seed: u64,
    actuator_config: &ActuatorConfig,
    contract_set: &ContractSet,
    mission_policy: MissionPolicy,
    iterations: u32,
) -> Result<VerifiedBenchmarkResult, LabError> {
    if !(1..=10_000).contains(&iterations) {
        return Err(LabError("iterations must be between 1 and 10000".into()));
    }
    scenario
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    actuator_config.validate(scenario.steps).map_err(LabError)?;
    contract_set
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    mission_policy.validate()?;

    let warmup = execute_with_actuator(scenario, seed, None, actuator_config)?;
    let warmup_artifact = assemble_artifact(scenario.clone(), seed, warmup.events, warmup.report);
    let warmup_trace = build_temporal_trace(&warmup_artifact, &warmup.actuation)?;
    std::hint::black_box(evaluate(contract_set, &warmup_trace));

    let mut simulation_elapsed_micros = 0_u64;
    let mut artifact_elapsed_micros = 0_u64;
    let mut temporal_monitor_elapsed_micros = 0_u64;
    let mut final_hash = [0_u8; 32];
    for _ in 0..iterations {
        let started = Instant::now();
        let output = execute_with_actuator(scenario, seed, None, actuator_config)?;
        simulation_elapsed_micros =
            simulation_elapsed_micros.saturating_add(elapsed_micros(started));

        let started = Instant::now();
        let artifact = assemble_artifact(scenario.clone(), seed, output.events, output.report);
        artifact_elapsed_micros = artifact_elapsed_micros.saturating_add(elapsed_micros(started));
        final_hash = parse_hash(&artifact.final_hash)?;

        let started = Instant::now();
        let trace = build_temporal_trace(&artifact, &output.actuation)?;
        let _results = evaluate(contract_set, &trace);
        temporal_monitor_elapsed_micros =
            temporal_monitor_elapsed_micros.saturating_add(elapsed_micros(started));
    }

    Ok(VerifiedBenchmarkResult {
        iterations,
        simulated_ticks: u64::from(scenario.steps) * u64::from(iterations),
        simulation_elapsed_micros,
        artifact_elapsed_micros,
        temporal_monitor_elapsed_micros,
        final_hash,
    })
}

fn elapsed_micros(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_micros()).unwrap_or(u64::MAX)
}

fn parse_hash(value: &str) -> Result<[u8; 32], LabError> {
    if value.len() != 64 {
        return Err(LabError("final hash is not a SHA-256 digest".into()));
    }
    let mut digest = [0_u8; 32];
    for (index, byte) in digest.iter_mut().enumerate() {
        let offset = index * 2;
        *byte = u8::from_str_radix(&value[offset..offset + 2], 16)
            .map_err(|_| LabError("final hash is not a SHA-256 digest".into()))?;
    }
    Ok(digest)
}

pub fn analyze_artifact(
    artifact: EventsArtifact,
    policy: MissionPolicy,
) -> Result<MissionAnalysis, LabError> {
    let report = recompute_artifact(&artifact)?;
    analyze_mission(&artifact.scenario, &report, policy)
}

fn assemble_artifact(
    scenario: Scenario,
    seed: u64,
    events: Vec<EventRecord>,
    report: RunReport,
) -> EventsArtifact {
    let event_count = events.len() as u64;
    let final_hash = events
        .last()
        .map(|event| event.hash.clone())
        .unwrap_or_else(|| crate::artifact::GENESIS_HASH.to_owned());
    let artifact_sha256 =
        artifact_digest(&scenario, seed, &events, event_count, &final_hash, &report);
    EventsArtifact {
        schema_version: SCHEMA_VERSION,
        scenario,
        seed,
        events,
        event_count,
        final_hash,
        expected_report: report,
        artifact_sha256,
    }
}

fn build_verification_artifact(
    artifact: &EventsArtifact,
    actuation: &[ActuationOutcome],
    actuator_config: ActuatorConfig,
    contract_set: ContractSet,
    mission_policy: MissionPolicy,
    mission_outcome: MissionOutcome,
    reproduction_command: String,
) -> Result<VerificationArtifact, LabError> {
    let trace = build_temporal_trace(artifact, actuation)?;
    let contract_results = evaluate(&contract_set, &trace);
    let failures = build_failure_evidence(
        artifact,
        actuation,
        &trace,
        &contract_results,
        &reproduction_command,
    )?;
    let mut counts = (0_u32, 0_u32, 0_u32);
    for result in &contract_results {
        match result.outcome {
            ContractOutcome::Pass => counts.0 = counts.0.saturating_add(1),
            ContractOutcome::Fail => counts.1 = counts.1.saturating_add(1),
            ContractOutcome::Inconclusive => counts.2 = counts.2.saturating_add(1),
        }
    }
    let temporal_status = if counts.1 > 0 {
        ContractOutcome::Fail
    } else if counts.2 > 0 {
        ContractOutcome::Inconclusive
    } else {
        ContractOutcome::Pass
    };
    let actuator_fault_event_count = actuation
        .iter()
        .map(|outcome| outcome.fault_events.len() as u64)
        .sum();
    let mut verification = VerificationArtifact {
        schema_version: VERIFICATION_SCHEMA_VERSION,
        source_artifact_sha256: artifact.artifact_sha256.clone(),
        source_final_hash: artifact.final_hash.clone(),
        contract_set,
        actuator_config,
        actuator_trace_sha256: hash_serializable(actuation),
        actuator_fault_event_count,
        mission_policy,
        summary: VerificationSummary {
            temporal_status,
            safety_status: artifact.expected_report.status,
            mission_outcome,
            contracts_passed: counts.0,
            contracts_failed: counts.1,
            contracts_inconclusive: counts.2,
        },
        contract_results,
        failures,
        reproduction_command,
        verification_sha256: String::new(),
    };
    verification.verification_sha256 = verification_digest(&verification);
    Ok(verification)
}

fn recompute_artifact(artifact: &EventsArtifact) -> Result<crate::model::RunReport, LabError> {
    Ok(recompute_core(artifact, None)?.report)
}

fn recompute_core(
    artifact: &EventsArtifact,
    actuator_config: Option<&ActuatorConfig>,
) -> Result<CoreOutput, LabError> {
    artifact
        .scenario
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    verify_artifact_integrity(artifact)?;
    if let Some(config) = actuator_config {
        config.validate(artifact.scenario.steps).map_err(LabError)?;
    }
    let exogenous = extract_exogenous(artifact)?;
    let replay = if let Some(config) = actuator_config {
        execute_with_actuator(&artifact.scenario, artifact.seed, Some(&exogenous), config)?
    } else {
        execute(&artifact.scenario, artifact.seed, Some(&exogenous))?
    };
    if replay.events != artifact.events {
        return Err(LabError(
            "replay event stream differs from the recorded event stream".into(),
        ));
    }
    if replay.report != artifact.expected_report {
        return Err(LabError(
            "recomputed report differs from expected_report".into(),
        ));
    }
    Ok(replay)
}

pub fn parse_scenario(text: &str) -> Result<Scenario, LabError> {
    if text.len() > MAX_SCENARIO_BYTES {
        return Err(LabError("scenario file exceeds the 2 MiB limit".into()));
    }
    Scenario::from_json(text).map_err(LabError)
}

pub fn parse_artifact(text: &str) -> Result<EventsArtifact, LabError> {
    if text.len() > MAX_ARTIFACT_BYTES {
        return Err(LabError("events artifact exceeds the 128 MiB limit".into()));
    }
    serde_json::from_str(text).map_err(|error| LabError(error.to_string()))
}

pub fn status_exit_code(status: RunStatus) -> u8 {
    if status == RunStatus::Passed { 0 } else { 2 }
}
