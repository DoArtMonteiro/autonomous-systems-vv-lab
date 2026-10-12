use std::path::{Component, Path};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::actuator::{ActuationOutcome, ActuatorConfig, ActuatorEventKind};
use crate::artifact::{hash_serializable, verify_artifact_integrity};
use crate::contracts::ContractSet;
use crate::controller::ControllerPolicyV1;
use crate::engine::{CoreOutput, execute_with_controller_policy};
use crate::error::LabError;
use crate::mission_analysis::{MissionAnalysis, MissionOutcome, MissionPolicy, analyze_mission};
use crate::model::{EventPayload, EventsArtifact, Point, RunReport, RunStatus, Scenario};
use crate::temporal::ContractOutcome;

use super::{
    VerificationArtifact, assemble_artifact, build_verification_artifact,
    parse_verification_artifact, verify_verification_integrity,
};

pub const CONTROLLER_INTERFACE_VERSION: u32 = 1;
pub const POLICY_BEHAVIOR_VERSION: u32 = 1;
pub const CONTROLLER_EVALUATION_SCHEMA_VERSION: u32 = 1;
pub const CONTROLLER_COMPARISON_SCHEMA_VERSION: u32 = 1;
pub(super) const EXOGENOUS_CALENDAR_VERSION: u32 = 1;
pub(super) const MAX_M4_ARTIFACT_BYTES: usize = 4 * 1024 * 1024;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct ExogenousCalendar {
    version: u32,
    ticks: Vec<ExogenousCalendarTick>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct ExogenousCalendarTick {
    tick: u32,
    gps_dropout: bool,
    gps_noise_x_mm: i32,
    gps_noise_y_mm: i32,
    communication_delivered: bool,
    communication_delay_ticks: u32,
    active_actuator_fault_ids: Vec<String>,
}

#[derive(Clone, Default)]
struct CalendarTickBuilder {
    gps: Option<(bool, i32, i32)>,
    communication: Option<(bool, u32)>,
    active_fault_ids: Option<Vec<String>>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ArtifactReference {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerEvaluationMetrics {
    pub safety_status: RunStatus,
    pub temporal_status: ContractOutcome,
    pub mission_outcome: MissionOutcome,
    pub ticks: u32,
    pub waypoints_completed: usize,
    pub waypoints_remaining: usize,
    pub fallback_ticks: u32,
    pub failed_safety_invariants: u32,
    pub failed_temporal_contracts: u32,
    pub inconclusive_temporal_contracts: u32,
    pub final_truth: Point,
    pub movement_action_ticks: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerEvaluationProvenance {
    pub scenario_name: String,
    pub seed: u64,
    pub horizon_ticks: u32,
    pub execution_kind: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerEvaluationManifest {
    pub schema_version: u32,
    pub interface_version: u32,
    pub controller_id: String,
    pub policy_behavior_version: u32,
    pub source_sha256: String,
    pub scenario_sha256: String,
    pub actuator_config_sha256: String,
    pub contract_set_sha256: String,
    pub mission_policy_sha256: String,
    pub configuration_sha256: String,
    pub seed: u64,
    pub event_artifact: ArtifactReference,
    pub report_artifact: ArtifactReference,
    pub mission_artifact: ArtifactReference,
    pub verification_artifact: ArtifactReference,
    pub normalized_exogenous_calendar_version: u32,
    pub normalized_exogenous_calendar_sha256: String,
    pub metrics: ControllerEvaluationMetrics,
    pub provenance: ControllerEvaluationProvenance,
    pub manifest_sha256: String,
}

#[derive(Clone, Debug)]
pub struct ControllerEvaluationOutcome {
    pub artifact: EventsArtifact,
    pub mission: MissionAnalysis,
    pub verification: VerificationArtifact,
    pub manifest: ControllerEvaluationManifest,
}

pub fn controller_id(policy: ControllerPolicyV1) -> &'static str {
    match policy {
        ControllerPolicyV1::DominantAxis => "dominant_axis",
        ControllerPolicyV1::XFirst => "x_first",
    }
}

pub fn parse_controller_id(value: &str) -> Result<ControllerPolicyV1, LabError> {
    match value {
        "dominant_axis" => Ok(ControllerPolicyV1::DominantAxis),
        "x_first" => Ok(ControllerPolicyV1::XFirst),
        _ => Err(LabError(format!("unsupported M4 controller_id '{value}'"))),
    }
}

pub fn source_sha256() -> String {
    let sources = [
        ("Cargo.lock", include_str!("../../Cargo.lock")),
        ("Cargo.toml", include_str!("../../Cargo.toml")),
        ("src/actuator.rs", include_str!("../actuator.rs")),
        ("src/artifact.rs", include_str!("../artifact.rs")),
        ("src/contracts.rs", include_str!("../contracts.rs")),
        ("src/controller.rs", include_str!("../controller.rs")),
        ("src/engine.rs", include_str!("../engine.rs")),
        ("src/error.rs", include_str!("../error.rs")),
        ("src/geometry.rs", include_str!("../geometry.rs")),
        ("src/lib.rs", include_str!("../lib.rs")),
        (
            "src/mission_analysis.rs",
            include_str!("../mission_analysis.rs"),
        ),
        ("src/main.rs", include_str!("../main.rs")),
        ("src/model.rs", include_str!("../model.rs")),
        ("src/prng.rs", include_str!("../prng.rs")),
        ("src/simulation.rs", include_str!("../simulation.rs")),
        (
            "src/simulation/controller_evaluation.rs",
            include_str!("controller_evaluation.rs"),
        ),
        (
            "src/simulation/controller_comparison.rs",
            include_str!("controller_comparison.rs"),
        ),
        (
            "src/simulation/provenance.rs",
            include_str!("provenance.rs"),
        ),
        (
            "src/simulation/verification.rs",
            include_str!("verification.rs"),
        ),
        ("src/temporal.rs", include_str!("../temporal.rs")),
        (
            "src/temporal/progress.rs",
            include_str!("../temporal/progress.rs"),
        ),
        (
            "src/temporal/response.rs",
            include_str!("../temporal/response.rs"),
        ),
        ("src/verifier.rs", include_str!("../verifier.rs")),
    ];
    let mut digest = Sha256::new();
    for (path, contents) in sources {
        digest.update(path.as_bytes());
        digest.update([0]);
        digest.update(contents.replace("\r\n", "\n").as_bytes());
        digest.update([0]);
    }
    hex_digest(&digest.finalize())
}

pub fn run_controller_evaluation(
    scenario: Scenario,
    seed: u64,
    policy: ControllerPolicyV1,
    actuator_config: ActuatorConfig,
    contract_set: ContractSet,
    mission_policy: MissionPolicy,
) -> Result<ControllerEvaluationOutcome, LabError> {
    scenario
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    actuator_config.validate(scenario.steps).map_err(LabError)?;
    contract_set
        .validate()
        .map_err(|error| LabError(error.to_string()))?;
    let mission_policy = mission_policy.validate()?;

    let output = execute_with_controller_policy(&scenario, seed, &actuator_config, policy)?;
    assemble_controller_evaluation(
        scenario,
        seed,
        policy,
        actuator_config,
        contract_set,
        mission_policy,
        output,
    )
}

fn assemble_controller_evaluation(
    scenario: Scenario,
    seed: u64,
    policy: ControllerPolicyV1,
    actuator_config: ActuatorConfig,
    contract_set: ContractSet,
    mission_policy: MissionPolicy,
    output: CoreOutput,
) -> Result<ControllerEvaluationOutcome, LabError> {
    let calendar = exogenous_calendar(&output.events, &output.actuation, scenario.steps)?;
    let calendar_sha256 = hash_serializable(&calendar);
    let artifact = assemble_artifact(scenario, seed, output.events, output.report);
    let mission = analyze_mission(
        &artifact.scenario,
        &artifact.expected_report,
        mission_policy,
    )?;
    let reproduction_command = "vv-lab replay-m4 m4.json".to_owned();
    let verification = build_verification_artifact(
        &artifact,
        &output.actuation,
        actuator_config.clone(),
        contract_set.clone(),
        mission_policy,
        mission.outcome,
        reproduction_command,
    )?;
    let report_bytes = serde_json::to_vec(&artifact.expected_report)
        .map_err(|error| LabError(error.to_string()))?;
    let mission_bytes =
        serde_json::to_vec(&mission).map_err(|error| LabError(error.to_string()))?;
    let events_bytes =
        serde_json::to_vec(&artifact).map_err(|error| LabError(error.to_string()))?;
    let verification_bytes =
        serde_json::to_vec(&verification).map_err(|error| LabError(error.to_string()))?;
    let metrics = metrics(&artifact.expected_report, &mission, &verification);
    let scenario_sha256 = hash_serializable(&artifact.scenario);
    let actuator_config_sha256 = hash_serializable(&actuator_config);
    let contract_set_sha256 = hash_serializable(&contract_set);
    let mission_policy_sha256 = hash_serializable(&mission_policy);
    let configuration_sha256 =
        hash_serializable(&(&actuator_config, &contract_set, mission_policy));
    let mut manifest = ControllerEvaluationManifest {
        schema_version: CONTROLLER_EVALUATION_SCHEMA_VERSION,
        interface_version: CONTROLLER_INTERFACE_VERSION,
        controller_id: controller_id(policy).into(),
        policy_behavior_version: POLICY_BEHAVIOR_VERSION,
        source_sha256: source_sha256(),
        scenario_sha256,
        actuator_config_sha256,
        contract_set_sha256,
        mission_policy_sha256,
        configuration_sha256,
        seed,
        event_artifact: reference("events.json", &events_bytes),
        report_artifact: reference("report.json", &report_bytes),
        mission_artifact: reference("mission.json", &mission_bytes),
        verification_artifact: reference("verification.json", &verification_bytes),
        normalized_exogenous_calendar_version: calendar.version,
        normalized_exogenous_calendar_sha256: calendar_sha256,
        metrics,
        provenance: ControllerEvaluationProvenance {
            scenario_name: artifact.scenario.name.clone(),
            seed,
            horizon_ticks: artifact.scenario.steps,
            execution_kind: "fresh_policy_execution".into(),
        },
        manifest_sha256: String::new(),
    };
    manifest.manifest_sha256 = manifest_digest(&manifest);
    validate_controller_evaluation_manifest(&manifest)?;
    Ok(ControllerEvaluationOutcome {
        artifact,
        mission,
        verification,
        manifest,
    })
}

fn exogenous_calendar(
    events: &[crate::model::EventRecord],
    actuation: &[ActuationOutcome],
    steps: u32,
) -> Result<ExogenousCalendar, LabError> {
    let mut ticks = vec![CalendarTickBuilder::default(); steps as usize];
    for record in events {
        if record.tick == 0 || record.tick > steps {
            return Err(LabError(
                "M4 event is outside the configured horizon".into(),
            ));
        }
        let tick = &mut ticks[record.tick as usize - 1];
        match &record.event {
            EventPayload::GpsSample {
                dropped,
                noise_x_mm,
                noise_y_mm,
                ..
            } => {
                if tick
                    .gps
                    .replace((*dropped, *noise_x_mm, *noise_y_mm))
                    .is_some()
                {
                    return Err(LabError(format!(
                        "duplicate M4 GPS sample at tick {}",
                        record.tick
                    )));
                }
            }
            EventPayload::PacketOutcome {
                delivered,
                delay_ticks,
                ..
            } => {
                if tick
                    .communication
                    .replace((*delivered, *delay_ticks))
                    .is_some()
                {
                    return Err(LabError(format!(
                        "duplicate M4 communication outcome at tick {}",
                        record.tick
                    )));
                }
            }
            _ => {}
        }
    }
    if actuation.len() != steps as usize {
        return Err(LabError(
            "M4 actuator outcomes do not cover every tick".into(),
        ));
    }
    for outcome in actuation {
        if outcome.tick == 0 || outcome.tick > steps {
            return Err(LabError(
                "M4 actuator outcome is outside the configured horizon".into(),
            ));
        }
        let tick = &mut ticks[outcome.tick as usize - 1];
        let active_fault_ids = outcome
            .fault_events
            .iter()
            .filter(|event| event.kind == ActuatorEventKind::FaultWindowActive)
            .map(|event| event.fault_id.clone())
            .collect::<Vec<_>>();
        if active_fault_ids.windows(2).any(|pair| pair[0] >= pair[1]) {
            return Err(LabError(
                "M4 active actuator fault identifiers are not ordered".into(),
            ));
        }
        if tick.active_fault_ids.replace(active_fault_ids).is_some() {
            return Err(LabError(format!(
                "duplicate M4 actuator outcome at tick {}",
                outcome.tick
            )));
        }
    }
    let ticks = ticks
        .into_iter()
        .enumerate()
        .map(|(index, tick)| {
            let (gps_dropout, gps_noise_x_mm, gps_noise_y_mm) = tick
                .gps
                .ok_or_else(|| LabError(format!("missing M4 GPS sample at tick {}", index + 1)))?;
            let (communication_delivered, communication_delay_ticks) =
                tick.communication.ok_or_else(|| {
                    LabError(format!(
                        "missing M4 communication outcome at tick {}",
                        index + 1
                    ))
                })?;
            let active_actuator_fault_ids = tick.active_fault_ids.ok_or_else(|| {
                LabError(format!("missing M4 actuator outcome at tick {}", index + 1))
            })?;
            Ok(ExogenousCalendarTick {
                tick: index as u32 + 1,
                gps_dropout,
                gps_noise_x_mm,
                gps_noise_y_mm,
                communication_delivered,
                communication_delay_ticks,
                active_actuator_fault_ids,
            })
        })
        .collect::<Result<Vec<_>, LabError>>()?;
    Ok(ExogenousCalendar {
        version: EXOGENOUS_CALENDAR_VERSION,
        ticks,
    })
}

pub fn parse_controller_evaluation_manifest(
    text: &str,
) -> Result<ControllerEvaluationManifest, LabError> {
    if text.len() > MAX_M4_ARTIFACT_BYTES {
        return Err(LabError("M4 manifest exceeds the 4 MiB limit".into()));
    }
    let manifest: ControllerEvaluationManifest =
        serde_json::from_str(text).map_err(|error| LabError(error.to_string()))?;
    validate_controller_evaluation_manifest(&manifest)?;
    Ok(manifest)
}

pub fn replay_controller_evaluation(
    manifest_text: &str,
    events_text: &str,
    report_text: &str,
    mission_text: &str,
    verification_text: &str,
) -> Result<ControllerEvaluationOutcome, LabError> {
    let loaded = validate_controller_evaluation_files(
        manifest_text,
        events_text,
        report_text,
        mission_text,
        verification_text,
    )?;
    verify_controller_evaluation(&loaded)?;
    Ok(loaded)
}

pub(super) fn verify_controller_evaluation(
    outcome: &ControllerEvaluationOutcome,
) -> Result<(), LabError> {
    validate_controller_evaluation_manifest(&outcome.manifest)?;
    let policy = parse_controller_id(&outcome.manifest.controller_id)?;
    let output = execute_with_controller_policy(
        &outcome.artifact.scenario,
        outcome.artifact.seed,
        &outcome.verification.actuator_config,
        policy,
    )?;
    if output.events != outcome.artifact.events || output.report != outcome.artifact.expected_report
    {
        return Err(LabError(
            "M4 replay differs from events.json or report.json".into(),
        ));
    }
    let replayed = assemble_controller_evaluation(
        outcome.artifact.scenario.clone(),
        outcome.artifact.seed,
        policy,
        outcome.verification.actuator_config.clone(),
        outcome.verification.contract_set.clone(),
        outcome.verification.mission_policy,
        output,
    )?;
    if replayed.mission != outcome.mission
        || replayed.verification != outcome.verification
        || replayed.manifest != outcome.manifest
    {
        return Err(LabError(
            "M4 replay differs from mission, verification or manifest artifacts".into(),
        ));
    }
    Ok(())
}

pub fn validate_controller_evaluation_files(
    manifest_text: &str,
    events_text: &str,
    report_text: &str,
    mission_text: &str,
    verification_text: &str,
) -> Result<ControllerEvaluationOutcome, LabError> {
    let manifest = parse_controller_evaluation_manifest(manifest_text)?;
    validate_reference(
        &manifest.event_artifact,
        "events.json",
        events_text.as_bytes(),
    )?;
    validate_reference(
        &manifest.report_artifact,
        "report.json",
        report_text.as_bytes(),
    )?;
    validate_reference(
        &manifest.mission_artifact,
        "mission.json",
        mission_text.as_bytes(),
    )?;
    validate_reference(
        &manifest.verification_artifact,
        "verification.json",
        verification_text.as_bytes(),
    )?;
    if manifest.source_sha256 != source_sha256() {
        return Err(LabError(
            "M4 source_sha256 does not match this build".into(),
        ));
    }
    let artifact: EventsArtifact =
        serde_json::from_str(events_text).map_err(|error| LabError(error.to_string()))?;
    let report: RunReport =
        serde_json::from_str(report_text).map_err(|error| LabError(error.to_string()))?;
    let mission: MissionAnalysis =
        serde_json::from_str(mission_text).map_err(|error| LabError(error.to_string()))?;
    let verification = parse_verification_artifact(verification_text)?;
    verify_artifact_integrity(&artifact)?;
    verify_verification_integrity(&verification, &artifact)?;
    mission.validate()?;
    let actuator_config_sha256 = hash_serializable(&verification.actuator_config);
    let contract_set_sha256 = hash_serializable(&verification.contract_set);
    let mission_policy_sha256 = hash_serializable(&verification.mission_policy);
    let configuration_sha256 = hash_serializable(&(
        &verification.actuator_config,
        &verification.contract_set,
        verification.mission_policy,
    ));
    if report != artifact.expected_report
        || hash_serializable(&artifact.scenario) != manifest.scenario_sha256
        || artifact.seed != manifest.seed
        || artifact.scenario.name != manifest.provenance.scenario_name
        || artifact.scenario.steps != manifest.provenance.horizon_ticks
        || artifact.seed != manifest.provenance.seed
        || actuator_config_sha256 != manifest.actuator_config_sha256
        || contract_set_sha256 != manifest.contract_set_sha256
        || mission_policy_sha256 != manifest.mission_policy_sha256
        || configuration_sha256 != manifest.configuration_sha256
        || verification.summary.mission_outcome != mission.outcome
        || verification.summary.safety_status != report.status
        || metrics(&report, &mission, &verification) != manifest.metrics
    {
        return Err(LabError(
            "M4 manifest provenance does not match its artifacts".into(),
        ));
    }
    Ok(ControllerEvaluationOutcome {
        artifact,
        mission,
        verification,
        manifest,
    })
}

fn metrics(
    report: &RunReport,
    mission: &MissionAnalysis,
    verification: &VerificationArtifact,
) -> ControllerEvaluationMetrics {
    ControllerEvaluationMetrics {
        safety_status: report.status,
        temporal_status: verification.summary.temporal_status,
        mission_outcome: mission.outcome,
        ticks: report.ticks,
        waypoints_completed: mission.waypoints_completed,
        waypoints_remaining: mission.waypoints_remaining,
        fallback_ticks: mission.fallback_ticks,
        failed_safety_invariants: report
            .invariants
            .iter()
            .filter(|result| !result.passed)
            .count() as u32,
        failed_temporal_contracts: verification.summary.contracts_failed,
        inconclusive_temporal_contracts: verification.summary.contracts_inconclusive,
        final_truth: report.final_truth,
        movement_action_ticks: report
            .telemetry
            .iter()
            .filter(|tick| tick.action.heading.is_some())
            .count() as u32,
    }
}

pub(super) fn validate_controller_evaluation_manifest(
    manifest: &ControllerEvaluationManifest,
) -> Result<(), LabError> {
    if manifest.schema_version != CONTROLLER_EVALUATION_SCHEMA_VERSION
        || manifest.interface_version != CONTROLLER_INTERFACE_VERSION
        || manifest.policy_behavior_version != POLICY_BEHAVIOR_VERSION
        || manifest.normalized_exogenous_calendar_version != EXOGENOUS_CALENDAR_VERSION
    {
        return Err(LabError("unsupported M4 manifest version".into()));
    }
    parse_controller_id(&manifest.controller_id)?;
    for (digest, name) in [
        (&manifest.source_sha256, "source_sha256"),
        (&manifest.scenario_sha256, "scenario_sha256"),
        (&manifest.actuator_config_sha256, "actuator_config_sha256"),
        (&manifest.contract_set_sha256, "contract_set_sha256"),
        (&manifest.mission_policy_sha256, "mission_policy_sha256"),
        (&manifest.configuration_sha256, "configuration_sha256"),
        (
            &manifest.normalized_exogenous_calendar_sha256,
            "normalized_exogenous_calendar_sha256",
        ),
        (&manifest.manifest_sha256, "manifest_sha256"),
    ] {
        validate_sha256(digest, name)?;
    }
    validate_fixed_reference(&manifest.event_artifact, "events.json")?;
    validate_fixed_reference(&manifest.report_artifact, "report.json")?;
    validate_fixed_reference(&manifest.mission_artifact, "mission.json")?;
    validate_fixed_reference(&manifest.verification_artifact, "verification.json")?;
    if manifest.provenance.execution_kind != "fresh_policy_execution"
        || manifest.seed != manifest.provenance.seed
        || manifest.metrics.ticks != manifest.provenance.horizon_ticks
        || manifest.provenance.horizon_ticks == 0
        || manifest.provenance.scenario_name.is_empty()
    {
        return Err(LabError(
            "M4 manifest provenance or metrics are malformed".into(),
        ));
    }
    if manifest.manifest_sha256 != manifest_digest(manifest) {
        return Err(LabError("M4 manifest_sha256 mismatch".into()));
    }
    Ok(())
}

fn manifest_digest(manifest: &ControllerEvaluationManifest) -> String {
    let mut unsigned = manifest.clone();
    unsigned.manifest_sha256.clear();
    hash_serializable(&unsigned)
}

fn reference(path: &str, bytes: &[u8]) -> ArtifactReference {
    ArtifactReference {
        path: path.into(),
        sha256: sha256(bytes),
    }
}

fn validate_fixed_reference(
    reference: &ArtifactReference,
    expected_path: &str,
) -> Result<(), LabError> {
    if reference.path != expected_path {
        return Err(LabError(format!(
            "M4 reference path must be {expected_path}"
        )));
    }
    validate_sha256(&reference.sha256, "artifact reference sha256")
}

fn validate_reference(
    reference: &ArtifactReference,
    expected_path: &str,
    bytes: &[u8],
) -> Result<(), LabError> {
    validate_fixed_reference(reference, expected_path)?;
    if reference.sha256 != sha256(bytes) {
        return Err(LabError(format!("M4 {} hash mismatch", reference.path)));
    }
    Ok(())
}

pub fn validate_relative_reference(path: &str) -> Result<(), LabError> {
    let parsed = Path::new(path);
    let bytes = path.as_bytes();
    let has_windows_drive_prefix =
        bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':';
    if path.is_empty()
        || parsed.is_absolute()
        || has_windows_drive_prefix
        || parsed
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
        || path.contains('\\')
    {
        return Err(LabError(
            "M4 comparison reference path is not a safe relative path".into(),
        ));
    }
    Ok(())
}

pub(super) fn validate_sha256(value: &str, label: &str) -> Result<(), LabError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(LabError(format!(
            "{label} must be a lowercase SHA-256 digest"
        )));
    }
    Ok(())
}

fn sha256(bytes: &[u8]) -> String {
    hex_digest(&Sha256::digest(bytes))
}

fn hex_digest(digest: &[u8]) -> String {
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}
