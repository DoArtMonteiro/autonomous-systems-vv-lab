//! Types of the `vv-domain` contract, version 1. Every document carries a `schema` string; readers
//! refuse unknown fields so a typo or a newer, incompatible document never passes silently.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const CONTRACT_NAME: &str = "vv-domain";
pub const CONTRACT_MAJOR: u32 = 1;
pub const CONTRACT_MINOR: u32 = 0;

pub const MANIFEST_SCHEMA: &str = "vv-domain-manifest.v1";
pub const CATALOG_SCHEMA: &str = "vv-domain-catalog.v1";
pub const REQUEST_SCHEMA: &str = "vv-run-request.v1";
pub const RECORD_SCHEMA: &str = "vv-run.v1";
pub const REPLAY_SCHEMA: &str = "vv-run-replay.v1";

/// File a domain host writes into its run directory, next to its native artifacts.
pub const RECORD_FILE: &str = "record.json";
/// File the platform writes into a stored run directory; never produced or read by a host.
pub const META_FILE: &str = "meta.json";
/// Normalised request the platform stores next to the run; never produced or read by a host.
pub const REQUEST_FILE: &str = "request.json";

/// Host exit codes. A run that violates a requirement still exits 0: that is a result.
pub const EXIT_OK: i32 = 0;
pub const EXIT_REPLAY_REJECTED: i32 = 1;
pub const EXIT_INVALID_REQUEST: i32 = 3;
pub const EXIT_SIMULATION_ERROR: i32 = 4;

// ------------------------------------------------------------------ manifest (static domain.json)

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ContractVersion {
    pub name: String,
    pub major: u32,
    pub minor: u32,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct HostSpec {
    /// Plain file name of the host executable, in the directory of domain.json.
    pub executable: String,
    /// Wall-clock limit of one host call, measured outside the simulation.
    pub timeout_s: u32,
    /// Largest stdout the platform accepts from one host call.
    pub max_output_bytes: u64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ProtectedRange {
    pub start: u64,
    pub end: u64,
    pub reason: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SeedPolicy {
    pub min: u64,
    pub max: u64,
    /// Seeds no desktop run may use, refused before any process starts (inclusive ranges).
    pub protected: Vec<ProtectedRange>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DomainManifest {
    pub schema: String,
    pub id: String,
    pub name: String,
    pub version: String,
    pub description: String,
    pub contract: ContractVersion,
    pub host: HostSpec,
    /// Subset of: run, replay, compare, evidence, faults.
    pub capabilities: Vec<String>,
    /// Views the UI may offer: scene.<kind>, plots, requirements, timeline, events.
    pub visualisations: Vec<String>,
    pub seeds: SeedPolicy,
    pub model_validity: String,
    /// false for reference and test domains: discovered and runnable, hidden from the product UI.
    pub user_facing: bool,
}

// ------------------------------------------------------------------ catalog (host `describe`)

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Item {
    pub id: String,
    pub label: String,
    pub description: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ScenarioSpec {
    pub id: String,
    pub label: String,
    pub description: String,
    pub vehicle: String,
    /// Controller ids this scenario accepts.
    pub controllers: Vec<String>,
    /// Parameter ids this scenario accepts.
    pub parameters: Vec<String>,
    pub default_controller: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ParameterSpec {
    pub id: String,
    pub label: String,
    pub description: String,
    pub unit: String,
    pub group: String,
    pub advanced: bool,
    pub min: f64,
    pub max: f64,
    pub step: f64,
    pub default: f64,
    pub integer: bool,
    /// Requirement ids this parameter is known to act on, a hand-written hint of the domain (M17).
    /// Absent in older catalogs.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub influences: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MagnitudeSpec {
    pub min: f64,
    pub max: f64,
    pub unit: String,
    pub default: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct WindowSpec {
    pub min_length: f64,
    pub max_length: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FaultSpec {
    pub kind: String,
    pub label: String,
    pub description: String,
    /// sensor, actuator, communication or environment.
    pub target: String,
    pub magnitude: Option<MagnitudeSpec>,
    pub window: Option<WindowSpec>,
    pub default_start: f64,
    pub default_end: f64,
    /// When present, only these controllers accept the fault.
    pub controllers: Option<Vec<String>>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ChannelSpec {
    pub id: String,
    pub label: String,
    pub unit: String,
    pub group: String,
    /// truth, observation, estimate, uncertainty, command, metric, limit.
    pub kind: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RequirementSpec {
    pub id: String,
    pub label: String,
    /// requirement (mission), invariant (safety), declaration (controller self-report judged on truth).
    pub category: String,
    pub description: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Demo {
    pub id: String,
    pub title: String,
    pub narrative: String,
    pub requests: Vec<RunRequest>,
    pub look_at: Vec<String>,
    /// What the run is expected to show, stated by the domain and checked by its tests.
    pub expectation: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TimeSpec {
    /// Unit of fault windows and of every timebase: "s" or "tick".
    pub unit: String,
    pub label: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DomainCatalog {
    pub schema: String,
    pub domain: String,
    pub time: TimeSpec,
    pub vehicles: Vec<Item>,
    pub scenarios: Vec<ScenarioSpec>,
    pub controllers: Vec<Item>,
    pub parameters: Vec<ParameterSpec>,
    pub faults: Vec<FaultSpec>,
    pub max_faults: u32,
    pub channels: Vec<ChannelSpec>,
    pub requirements: Vec<RequirementSpec>,
    pub demos: Vec<Demo>,
}

// ------------------------------------------------------------------ request

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FaultRequest {
    pub kind: String,
    pub magnitude: Option<f64>,
    pub start: f64,
    pub end: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RunRequest {
    pub schema: String,
    pub domain: String,
    pub scenario: String,
    pub controller: String,
    pub seed: u64,
    pub faults: Vec<FaultRequest>,
    pub parameters: BTreeMap<String, f64>,
}

// ------------------------------------------------------------------ record (host `run`)

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DomainRef {
    pub id: String,
    pub version: String,
    pub contract: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FileHash {
    pub path: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    /// Hash of the simulator sources that produced the native artifacts.
    pub source_sha256: String,
    pub simulator: String,
    /// Native artifacts in the run directory, excluding record.json, request.json and meta.json.
    pub artifacts: Vec<FileHash>,
    /// Developer CLI commands, relative to a repository checkout, that reproduce the native run.
    pub reproduce: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Outcome {
    /// Domain outcome code, e.g. landed, hard_landing, reached_goal.
    pub code: String,
    pub label: String,
    /// success, partial or failure: the mission result, separate from safety.
    pub status: String,
    pub explanation: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Safety {
    /// safe or unsafe, from the safety invariants judged on the true state.
    pub status: String,
    /// Optional domain classification of the run; `None` when the domain defines none.
    pub class: Option<String>,
    pub explanation: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Channel {
    pub id: String,
    pub label: String,
    pub unit: String,
    pub group: String,
    pub kind: String,
    pub timebase: String,
    /// None where the signal does not exist at that sample (e.g. no measurement in a dropout).
    pub values: Vec<Option<f64>>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Event {
    pub t: f64,
    pub kind: String,
    pub label: String,
    /// info, fault, detection, mode, warning, violation.
    pub severity: String,
    /// truth, fault, controller, verifier.
    pub source: String,
    pub detail: Value,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RequirementResult {
    pub id: String,
    pub label: String,
    pub category: String,
    /// pass, fail, not_evaluated.
    pub status: String,
    pub expected: String,
    pub observed: String,
    /// Instant of the decisive sample (first failure, or the evaluation instant).
    pub t: Option<f64>,
    pub explanation: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Metric {
    pub id: String,
    pub label: String,
    pub value: Option<f64>,
    pub unit: String,
    pub group: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RunRecord {
    pub schema: String,
    pub domain: DomainRef,
    pub request: RunRequest,
    pub provenance: Provenance,
    pub model_validity: String,
    pub outcome: Outcome,
    pub safety: Safety,
    pub timebases: BTreeMap<String, Vec<f64>>,
    pub channels: Vec<Channel>,
    pub events: Vec<Event>,
    pub requirements: Vec<RequirementResult>,
    pub metrics: Vec<Metric>,
    /// Static scene for the domain visualisation: `kind` plus geometry (pad, zones, goal).
    pub scene: Value,
    /// Caveats the UI must show next to the run.
    pub notes: Vec<String>,
}

// ------------------------------------------------------------------ replay (host `replay`)

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ReplayCheck {
    pub name: String,
    pub pass: bool,
    pub detail: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ReplayReport {
    pub schema: String,
    /// verified or rejected; a host must recompute from the stored inputs to say verified.
    pub status: String,
    pub checks: Vec<ReplayCheck>,
}
