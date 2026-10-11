use serde::{Deserialize, Serialize};

use crate::actuator::{ActuatorBehavior, ActuatorConfig, ActuatorFaultEvent};
use crate::artifact::hash_serializable;
use crate::contracts::{CommandOutcome, ContractSet, PropertyType, TraceFact};
use crate::error::LabError;
use crate::mission_analysis::{MissionOutcome, MissionPolicy};
use crate::model::{
    Action, EventsArtifact, MissionState, ObservedTelemetry, Point, RunStatus, SafetyState,
};
use crate::temporal::{
    ContractOutcome, ContractResult, EvidenceReason, ExpectedCondition, ObservationState,
    TraceTransition,
};

const MAX_VERIFICATION_BYTES: usize = 32 * 1024 * 1024;
pub const VERIFICATION_SCHEMA_VERSION: u32 = 1;

/// M3-only verification sidecar. It binds declarative contracts and actuator
/// outcomes to the unchanged v1 events artifact.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct VerificationArtifact {
    pub schema_version: u32,
    pub source_artifact_sha256: String,
    pub source_final_hash: String,
    pub contract_set: ContractSet,
    pub actuator_config: ActuatorConfig,
    pub actuator_trace_sha256: String,
    pub actuator_fault_event_count: u64,
    pub mission_policy: MissionPolicy,
    pub summary: VerificationSummary,
    pub contract_results: Vec<ContractResult>,
    pub failures: Vec<ContractFailureEvidence>,
    pub reproduction_command: String,
    pub verification_sha256: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct VerificationSummary {
    pub temporal_status: ContractOutcome,
    pub safety_status: RunStatus,
    pub mission_outcome: MissionOutcome,
    pub contracts_passed: u32,
    pub contracts_failed: u32,
    pub contracts_inconclusive: u32,
}

/// A concise, source-linked report for the first counterexample of a contract.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContractFailureEvidence {
    pub contract_id: String,
    pub contract_version: u32,
    pub property_type: PropertyType,
    pub first_trigger_tick: Option<u32>,
    pub applicable_deadline_tick: Option<u64>,
    pub first_violation_tick: u32,
    pub expected: ExpectedCondition,
    pub expected_condition: String,
    pub actual_condition: String,
    pub actual_fact: Option<TraceFact>,
    pub actual_transition: Option<TraceTransition>,
    pub observation: ObservationState,
    pub evidence_reason: EvidenceReason,
    pub monitor_derived_command_outcome: Option<CommandOutcome>,
    pub detail: Option<String>,
    pub trigger_command: Option<CommandAtTick>,
    pub violation_command: Option<CommandAtTick>,
    pub actuator_behavior_at_trigger: Option<ActuatorBehavior>,
    pub actuator_behavior_at_violation: Option<ActuatorBehavior>,
    pub truth_from: Option<Point>,
    pub truth_position: Option<Point>,
    pub fault_events: Vec<LinkedActuatorFaultEvent>,
    pub source_event_sequences: Vec<u64>,
    pub counterexample_ticks: Vec<CounterexampleTick>,
    pub source_artifact_sha256: String,
    pub reproduction_command: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CommandAtTick {
    pub tick: u32,
    pub event_sequence: u64,
    pub action: Action,
}

/// An actuator event linked to the legacy event records that establish its
/// requested command, observation tick and optional execution tick.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LinkedActuatorFaultEvent {
    pub event: ActuatorFaultEvent,
    pub observed_event_sequence: u64,
    pub source_command_event_sequence: u64,
    pub execution_event_sequence: Option<u64>,
}

/// Tick-level source material retained only around a temporal counterexample.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CounterexampleTick {
    pub tick: u32,
    pub truth_from: Point,
    pub truth_position: Point,
    pub observed: Option<ObservedTelemetry>,
    pub mission_state: MissionState,
    pub safety_state: SafetyState,
    pub requested_action: Action,
    pub realized_action: Action,
    pub actuator_behavior: ActuatorBehavior,
    pub fault_events: Vec<LinkedActuatorFaultEvent>,
    pub source_event_sequences: Vec<u64>,
}

pub(super) fn verification_digest(verification: &VerificationArtifact) -> String {
    hash_serializable(&UnsignedVerificationArtifact {
        schema_version: verification.schema_version,
        source_artifact_sha256: &verification.source_artifact_sha256,
        source_final_hash: &verification.source_final_hash,
        contract_set: &verification.contract_set,
        actuator_config: &verification.actuator_config,
        actuator_trace_sha256: &verification.actuator_trace_sha256,
        actuator_fault_event_count: verification.actuator_fault_event_count,
        mission_policy: verification.mission_policy,
        summary: verification.summary,
        contract_results: &verification.contract_results,
        failures: &verification.failures,
        reproduction_command: &verification.reproduction_command,
    })
}

#[derive(Serialize)]
struct UnsignedVerificationArtifact<'a> {
    schema_version: u32,
    source_artifact_sha256: &'a str,
    source_final_hash: &'a str,
    contract_set: &'a ContractSet,
    actuator_config: &'a ActuatorConfig,
    actuator_trace_sha256: &'a str,
    actuator_fault_event_count: u64,
    mission_policy: MissionPolicy,
    summary: VerificationSummary,
    contract_results: &'a [ContractResult],
    failures: &'a [ContractFailureEvidence],
    reproduction_command: &'a str,
}

pub fn parse_verification_artifact(text: &str) -> Result<VerificationArtifact, LabError> {
    if text.len() > MAX_VERIFICATION_BYTES {
        return Err(LabError(
            "verification artifact exceeds the 32 MiB limit".into(),
        ));
    }
    let verification: VerificationArtifact =
        serde_json::from_str(text).map_err(|error| LabError(error.to_string()))?;
    validate_verification_shape(&verification)?;
    Ok(verification)
}

fn validate_verification_shape(verification: &VerificationArtifact) -> Result<(), LabError> {
    if verification.schema_version != VERIFICATION_SCHEMA_VERSION {
        return Err(LabError(
            "unsupported verification artifact schema_version".into(),
        ));
    }
    validate_sha256(
        &verification.source_artifact_sha256,
        "source_artifact_sha256",
    )?;
    validate_sha256(&verification.source_final_hash, "source_final_hash")?;
    validate_sha256(&verification.actuator_trace_sha256, "actuator_trace_sha256")?;
    validate_sha256(&verification.verification_sha256, "verification_sha256")?;
    verification
        .contract_set
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    verification.mission_policy.validate()?;
    verification
        .actuator_config
        .validate(10_000)
        .map_err(LabError)?;
    if verification.reproduction_command.trim().is_empty()
        || verification.reproduction_command.len() > 4096
    {
        return Err(LabError(
            "reproduction_command must contain 1 to 4096 bytes".into(),
        ));
    }
    if verification.contract_results.len() != verification.contract_set.contracts.len() {
        return Err(LabError(
            "contract_results count does not match the contract set".into(),
        ));
    }
    let mut counts = (0_u32, 0_u32, 0_u32);
    for (contract, result) in verification
        .contract_set
        .contracts
        .iter()
        .zip(&verification.contract_results)
    {
        if result.contract_id != contract.id()
            || result.schema_version != verification.contract_set.schema_version
            || result.property_type != contract.property_type()
        {
            return Err(LabError(
                "contract result identity differs from the declared contract".into(),
            ));
        }
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
    if verification.summary.contracts_passed != counts.0
        || verification.summary.contracts_failed != counts.1
        || verification.summary.contracts_inconclusive != counts.2
        || verification.summary.temporal_status != temporal_status
        || verification.failures.len() != counts.1 as usize
    {
        return Err(LabError(
            "verification summary does not match contract results".into(),
        ));
    }
    if verification
        .failures
        .iter()
        .any(|failure| failure.source_artifact_sha256 != verification.source_artifact_sha256)
    {
        return Err(LabError(
            "contract failure evidence references a different source artifact".into(),
        ));
    }
    if verification.verification_sha256 != verification_digest(verification) {
        return Err(LabError(
            "verification_sha256 does not match the verification artifact".into(),
        ));
    }
    Ok(())
}

pub(super) fn verify_verification_integrity(
    verification: &VerificationArtifact,
    artifact: &EventsArtifact,
) -> Result<(), LabError> {
    validate_verification_shape(verification)?;
    if verification.source_artifact_sha256 != artifact.artifact_sha256
        || verification.source_final_hash != artifact.final_hash
    {
        return Err(LabError(
            "verification artifact does not reference the supplied events artifact".into(),
        ));
    }
    verification
        .actuator_config
        .validate(artifact.scenario.steps)
        .map_err(LabError)?;
    Ok(())
}

fn validate_sha256(value: &str, field: &str) -> Result<(), LabError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(LabError(format!(
            "{field} must be a lowercase SHA-256 digest"
        )));
    }
    Ok(())
}
