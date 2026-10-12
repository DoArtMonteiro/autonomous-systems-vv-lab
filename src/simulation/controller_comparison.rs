use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::artifact::hash_serializable;
use crate::error::LabError;

use super::controller_evaluation::{
    ArtifactReference, CONTROLLER_COMPARISON_SCHEMA_VERSION, CONTROLLER_INTERFACE_VERSION,
    ControllerEvaluationManifest, ControllerEvaluationMetrics, ControllerEvaluationOutcome,
    EXOGENOUS_CALENDAR_VERSION, MAX_M4_ARTIFACT_BYTES, POLICY_BEHAVIOR_VERSION,
    validate_relative_reference, validate_sha256, verify_controller_evaluation,
};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ComparedController {
    pub controller_id: String,
    pub evaluation_manifest: ArtifactReference,
    pub event_artifact: ArtifactReference,
    pub verification_artifact: ArtifactReference,
    pub metrics: ControllerEvaluationMetrics,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComparisonPolicyReferences {
    pub evaluation_manifest: ArtifactReference,
    pub event_artifact: ArtifactReference,
    pub verification_artifact: ArtifactReference,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ComparisonProvenance {
    pub comparison_method: String,
    pub compared_execution_count: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerComparisonArtifact {
    pub schema_version: u32,
    pub interface_version: u32,
    pub policy_behavior_version: u32,
    pub source_sha256: String,
    pub scenario_sha256: String,
    pub configuration_sha256: String,
    pub scenario_name: String,
    pub seed: u64,
    pub horizon_ticks: u32,
    pub normalized_exogenous_calendar_version: u32,
    pub normalized_exogenous_calendar_sha256: String,
    pub external_calendar_equivalent: bool,
    pub controllers: Vec<ComparedController>,
    pub action_difference_ticks: u32,
    pub first_action_difference_tick: Option<u32>,
    pub safety_outcomes_differ: bool,
    pub temporal_outcomes_differ: bool,
    pub mission_outcomes_differ: bool,
    pub provenance: ComparisonProvenance,
    pub comparison_sha256: String,
}

pub fn parse_controller_comparison_artifact(
    text: &str,
) -> Result<ControllerComparisonArtifact, LabError> {
    if text.len() > MAX_M4_ARTIFACT_BYTES {
        return Err(LabError("M4 comparison exceeds the 4 MiB limit".into()));
    }
    let artifact: ControllerComparisonArtifact =
        serde_json::from_str(text).map_err(|error| LabError(error.to_string()))?;
    validate_controller_comparison_artifact(&artifact)?;
    Ok(artifact)
}

pub fn validate_controller_comparison_artifact(
    artifact: &ControllerComparisonArtifact,
) -> Result<(), LabError> {
    if artifact.schema_version != CONTROLLER_COMPARISON_SCHEMA_VERSION
        || artifact.interface_version != CONTROLLER_INTERFACE_VERSION
        || artifact.policy_behavior_version != POLICY_BEHAVIOR_VERSION
        || artifact.normalized_exogenous_calendar_version != EXOGENOUS_CALENDAR_VERSION
        || !artifact.external_calendar_equivalent
    {
        return Err(LabError("unsupported or non-equivalent M4 comparison".into()));
    }
    for (digest, name) in [
        (&artifact.source_sha256, "source_sha256"),
        (&artifact.scenario_sha256, "scenario_sha256"),
        (&artifact.configuration_sha256, "configuration_sha256"),
        (
            &artifact.normalized_exogenous_calendar_sha256,
            "normalized_exogenous_calendar_sha256",
        ),
        (&artifact.comparison_sha256, "comparison_sha256"),
    ] {
        validate_sha256(digest, name)?;
    }
    if artifact.controllers.len() != 2
        || artifact.controllers[0].controller_id != "dominant_axis"
        || artifact.controllers[1].controller_id != "x_first"
        || artifact.provenance.comparison_method
            != "independent_policy_replays_calendar_hash_v1"
        || artifact.provenance.compared_execution_count != 2
        || artifact.scenario_name.is_empty()
        || artifact.horizon_ticks == 0
        || artifact.controllers.iter().any(|controller| {
            controller.metrics.ticks != artifact.horizon_ticks
                || !comparison_paths_are_siblings(controller)
        })
        || (artifact.action_difference_ticks == 0) != artifact.first_action_difference_tick.is_none()
        || artifact
            .first_action_difference_tick
            .is_some_and(|tick| tick == 0 || tick > artifact.horizon_ticks)
        || artifact.safety_outcomes_differ
            != (artifact.controllers[0].metrics.safety_status
                != artifact.controllers[1].metrics.safety_status)
        || artifact.temporal_outcomes_differ
            != (artifact.controllers[0].metrics.temporal_status
                != artifact.controllers[1].metrics.temporal_status)
        || artifact.mission_outcomes_differ
            != (artifact.controllers[0].metrics.mission_outcome
                != artifact.controllers[1].metrics.mission_outcome)
    {
        return Err(LabError("M4 comparison provenance is malformed".into()));
    }
    for controller in &artifact.controllers {
        validate_comparison_reference(&controller.evaluation_manifest)?;
        validate_comparison_reference(&controller.event_artifact)?;
        validate_comparison_reference(&controller.verification_artifact)?;
    }
    if artifact.comparison_sha256 != comparison_digest(artifact) {
        return Err(LabError("M4 comparison_sha256 mismatch".into()));
    }
    Ok(())
}

pub fn create_controller_comparison(
    dominant_outcome: &ControllerEvaluationOutcome,
    x_first_outcome: &ControllerEvaluationOutcome,
    dominant_references: ComparisonPolicyReferences,
    x_first_references: ComparisonPolicyReferences,
) -> Result<ControllerComparisonArtifact, LabError> {
    verify_controller_evaluation(dominant_outcome)?;
    verify_controller_evaluation(x_first_outcome)?;
    let dominant = &dominant_outcome.manifest;
    let x_first = &x_first_outcome.manifest;
    let dominant_report = &dominant_outcome.artifact.expected_report;
    let x_first_report = &x_first_outcome.artifact.expected_report;
    validate_comparison_references(dominant, &dominant_references)?;
    validate_comparison_references(x_first, &x_first_references)?;
    if dominant.controller_id != "dominant_axis"
        || x_first.controller_id != "x_first"
        || dominant.interface_version != x_first.interface_version
        || dominant.policy_behavior_version != x_first.policy_behavior_version
        || dominant.source_sha256 != x_first.source_sha256
        || dominant.scenario_sha256 != x_first.scenario_sha256
        || dominant.actuator_config_sha256 != x_first.actuator_config_sha256
        || dominant.contract_set_sha256 != x_first.contract_set_sha256
        || dominant.mission_policy_sha256 != x_first.mission_policy_sha256
        || dominant.configuration_sha256 != x_first.configuration_sha256
        || dominant.seed != x_first.seed
        || dominant.provenance != x_first.provenance
        || dominant.normalized_exogenous_calendar_version
            != x_first.normalized_exogenous_calendar_version
    {
        return Err(LabError("M4 controller pair provenance does not match".into()));
    }
    if dominant.normalized_exogenous_calendar_sha256
        != x_first.normalized_exogenous_calendar_sha256
    {
        return Err(LabError(
            "M4 controller pair has different external disturbance calendars".into(),
        ));
    }
    let horizon = dominant.provenance.horizon_ticks as usize;
    if dominant_report.telemetry.len() != horizon
        || x_first_report.telemetry.len() != horizon
        || dominant_report.ticks != x_first_report.ticks
        || dominant_report.scenario_name != x_first_report.scenario_name
        || dominant_report.seed != x_first_report.seed
    {
        return Err(LabError("M4 controller reports have different horizons".into()));
    }
    for (manifest, report) in [(dominant, dominant_report), (x_first, x_first_report)] {
        if report.status != manifest.metrics.safety_status
            || report.scenario_name != manifest.provenance.scenario_name
            || report.seed != manifest.seed
            || report.ticks != manifest.metrics.ticks
            || report.final_truth != manifest.metrics.final_truth
            || report.telemetry
                .iter()
                .filter(|tick| tick.action.heading.is_some())
                .count() as u32
                != manifest.metrics.movement_action_ticks
        {
            return Err(LabError("M4 metrics do not match the recorded report".into()));
        }
    }
    let differences = dominant_report
        .telemetry
        .iter()
        .zip(&x_first_report.telemetry)
        .filter(|(left, right)| left.action != right.action)
        .map(|(left, _)| left.tick)
        .collect::<Vec<_>>();
    let mut artifact = ControllerComparisonArtifact {
        schema_version: CONTROLLER_COMPARISON_SCHEMA_VERSION,
        interface_version: CONTROLLER_INTERFACE_VERSION,
        policy_behavior_version: POLICY_BEHAVIOR_VERSION,
        source_sha256: dominant.source_sha256.clone(),
        scenario_sha256: dominant.scenario_sha256.clone(),
        configuration_sha256: dominant.configuration_sha256.clone(),
        scenario_name: dominant.provenance.scenario_name.clone(),
        seed: dominant.seed,
        horizon_ticks: dominant.provenance.horizon_ticks,
        normalized_exogenous_calendar_version: dominant
            .normalized_exogenous_calendar_version,
        normalized_exogenous_calendar_sha256: dominant
            .normalized_exogenous_calendar_sha256
            .clone(),
        external_calendar_equivalent: true,
        controllers: vec![
            compared_controller("dominant_axis", dominant, dominant_references),
            compared_controller("x_first", x_first, x_first_references),
        ],
        action_difference_ticks: differences.len() as u32,
        first_action_difference_tick: differences.first().copied(),
        safety_outcomes_differ: dominant.metrics.safety_status != x_first.metrics.safety_status,
        temporal_outcomes_differ: dominant.metrics.temporal_status != x_first.metrics.temporal_status,
        mission_outcomes_differ: dominant.metrics.mission_outcome != x_first.metrics.mission_outcome,
        provenance: ComparisonProvenance {
            comparison_method: "independent_policy_replays_calendar_hash_v1".into(),
            compared_execution_count: 2,
        },
        comparison_sha256: String::new(),
    };
    artifact.comparison_sha256 = comparison_digest(&artifact);
    validate_controller_comparison_artifact(&artifact)?;
    Ok(artifact)
}

fn validate_comparison_references(
    manifest: &ControllerEvaluationManifest,
    references: &ComparisonPolicyReferences,
) -> Result<(), LabError> {
    if references.evaluation_manifest.sha256 != manifest.manifest_sha256
        || references.event_artifact.sha256 != manifest.event_artifact.sha256
        || references.verification_artifact.sha256 != manifest.verification_artifact.sha256
    {
        return Err(LabError("M4 comparison artifact references do not match the manifest".into()));
    }
    let manifest_parent = Path::new(&references.evaluation_manifest.path)
        .parent()
        .ok_or_else(|| LabError("M4 evaluation manifest reference has no parent".into()))?;
    let expected_event = manifest_parent.join("events.json").to_string_lossy().replace('\\', "/");
    let expected_verification = manifest_parent
        .join("verification.json")
        .to_string_lossy()
        .replace('\\', "/");
    if references.event_artifact.path != expected_event
        || references.verification_artifact.path != expected_verification
    {
        return Err(LabError("M4 comparison references are not sibling run artifacts".into()));
    }
    validate_comparison_reference(&references.evaluation_manifest)?;
    validate_comparison_reference(&references.event_artifact)?;
    validate_comparison_reference(&references.verification_artifact)
}

fn comparison_paths_are_siblings(controller: &ComparedController) -> bool {
    let parent = Path::new(&controller.evaluation_manifest.path).parent();
    let Some(parent) = parent else {
        return false;
    };
    let events = parent.join("events.json").to_string_lossy().replace('\\', "/");
    let verification = parent
        .join("verification.json")
        .to_string_lossy()
        .replace('\\', "/");
    controller.event_artifact.path == events
        && controller.verification_artifact.path == verification
}

fn compared_controller(
    controller_id: &str,
    manifest: &ControllerEvaluationManifest,
    references: ComparisonPolicyReferences,
) -> ComparedController {
    ComparedController {
        controller_id: controller_id.into(),
        evaluation_manifest: references.evaluation_manifest,
        event_artifact: references.event_artifact,
        verification_artifact: references.verification_artifact,
        metrics: manifest.metrics.clone(),
    }
}

fn validate_comparison_reference(reference: &ArtifactReference) -> Result<(), LabError> {
    validate_relative_reference(&reference.path)?;
    validate_sha256(&reference.sha256, "comparison artifact reference sha256")
}

fn comparison_digest(artifact: &ControllerComparisonArtifact) -> String {
    let mut unsigned = artifact.clone();
    unsigned.comparison_sha256.clear();
    hash_serializable(&unsigned)
}
