pub mod actuator;
mod artifact;
pub mod contracts;
pub mod controller;
mod engine;
mod error;
pub mod geometry;
pub mod mission_analysis;
pub mod model;
pub mod prng;
pub mod simulation;
pub mod temporal;
mod verifier;

pub use error::LabError;
pub use mission_analysis::{
    MissionAnalysis, MissionOutcome, MissionPolicy, MissionReason, parse_mission_analysis,
};
pub use model::{EventsArtifact, RunReport, Scenario};
pub use simulation::{
    ArtifactReference, CONTROLLER_COMPARISON_SCHEMA_VERSION, CONTROLLER_EVALUATION_SCHEMA_VERSION,
    CONTROLLER_INTERFACE_VERSION, ComparedController, ComparisonPolicyReferences,
    ComparisonProvenance, ContractFailureEvidence, ControllerComparisonArtifact,
    ControllerEvaluationManifest, ControllerEvaluationMetrics, ControllerEvaluationOutcome,
    ControllerEvaluationProvenance, POLICY_BEHAVIOR_VERSION, ReplayOutcome, VerificationArtifact,
    VerificationSummary, VerifiedBenchmarkResult, VerifiedReplayOutcome, VerifiedRunOutcome,
    analyze_artifact, benchmark_verified_scenario, controller_id, create_controller_comparison,
    parse_artifact, parse_controller_comparison_artifact, parse_controller_evaluation_manifest,
    parse_controller_id, parse_scenario, parse_verification_artifact, replay_artifact,
    replay_controller_evaluation, replay_verified_artifact, run_controller_evaluation,
    run_scenario, run_verified_scenario, source_sha256, status_exit_code,
    validate_controller_evaluation_files, validate_relative_reference,
};
pub use temporal::{
    ContractEvidence, ContractOutcome, ContractResult, EvidenceReason, ExpectedCondition,
    ObservationState, TraceTick, TraceTransition, evaluate,
};
