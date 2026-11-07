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
/// Multi-entity record (M17): a `vv-run.v1` record plus `entities` and `mission`. Additive: a v1
/// record has neither field and serialises exactly as before.
pub const RECORD_SCHEMA_V2: &str = "vv-run.v2";
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
    /// `vv-run.v2` only: the entities of a multi-entity run, in creation order.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub entities: Option<Vec<Entity>>,
    /// `vv-run.v2` only: mission-level results and the declared event order.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mission: Option<MissionResult>,
}

/// One simulated entity of a `vv-run.v2` record (for example a stack that separates into a booster
/// and an upper stage). Its data stays in the top-level lists, so every v1 view still works; the
/// entity names which of them are its own.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Entity {
    pub id: String,
    pub label: String,
    /// Domain kind, e.g. stack, booster, upper_stage.
    pub kind: String,
    /// Entity this one separated from; `None` for a root entity.
    pub parent: Option<String>,
    /// Timebase of its state samples (a key of `timebases`).
    pub timebase: String,
    /// Instants of its first and last state sample.
    pub t_start: f64,
    pub t_end: f64,
    /// Why its history ends (separated, surface impact, end of simulated time...).
    pub end_reason: String,
    /// Ids of its state channels in `channels`.
    pub channels: Vec<String>,
    /// Indices into `events` of the events of this entity, ascending.
    pub events: Vec<u32>,
    /// Ids of its requirements in `requirements`.
    pub requirements: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MissionResult {
    /// Ids of the mission-level requirements in `requirements` (judged over all entities).
    pub requirements: Vec<String>,
    /// The total order of `events`, stated by the domain.
    pub event_order: String,
    pub explanation: String,
}

impl RunRecord {
    /// Structural rules of `vv-run.v2` on top of those of v1; a v1 record must carry neither
    /// `entities` nor `mission`.
    pub fn check_entities(&self) -> Result<(), String> {
        match self.schema.as_str() {
            RECORD_SCHEMA => {
                if self.entities.is_some() || self.mission.is_some() {
                    return Err(format!("{RECORD_SCHEMA} carries no entities or mission"));
                }
                Ok(())
            }
            RECORD_SCHEMA_V2 => {
                let (Some(entities), Some(mission)) = (&self.entities, &self.mission) else {
                    return Err(format!("{RECORD_SCHEMA_V2} needs entities and mission"));
                };
                if entities.is_empty() {
                    return Err("a multi-entity record needs at least one entity".into());
                }
                let req_ids: Vec<&str> = self.requirements.iter().map(|r| r.id.as_str()).collect();
                let mut owned: Vec<&str> = Vec::new();
                for (i, e) in entities.iter().enumerate() {
                    if entities[..i].iter().any(|x| x.id == e.id) {
                        return Err(format!("entity {} is repeated", e.id));
                    }
                    if let Some(p) = &e.parent
                        && !entities[..i].iter().any(|x| &x.id == p)
                    {
                        return Err(format!(
                            "entity {} names a parent not listed before it",
                            e.id
                        ));
                    }
                    if !self.timebases.contains_key(&e.timebase) {
                        return Err(format!("entity {} names an unknown timebase", e.id));
                    }
                    if !e.t_start.is_finite() || !e.t_end.is_finite() || e.t_start > e.t_end {
                        return Err(format!("entity {} ends before it starts", e.id));
                    }
                    for c in &e.channels {
                        match self.channels.iter().find(|x| &x.id == c) {
                            None => {
                                return Err(format!("entity {} names unknown channel {c}", e.id));
                            }
                            Some(x) if x.timebase != e.timebase => {
                                return Err(format!(
                                    "channel {c} is not on the timebase of entity {}",
                                    e.id
                                ));
                            }
                            Some(_) => {}
                        }
                    }
                    if e.events.windows(2).any(|w| w[0] >= w[1])
                        || e.events.iter().any(|&k| k as usize >= self.events.len())
                    {
                        return Err(format!(
                            "entity {} event indices are not ascending and in range",
                            e.id
                        ));
                    }
                    for r in &e.requirements {
                        if !req_ids.contains(&r.as_str()) {
                            return Err(format!("entity {} names unknown requirement {r}", e.id));
                        }
                        owned.push(r);
                    }
                }
                for r in &mission.requirements {
                    if !req_ids.contains(&r.as_str()) {
                        return Err(format!("mission names unknown requirement {r}"));
                    }
                    owned.push(r);
                }
                owned.sort_unstable();
                let mut all = req_ids.clone();
                all.sort_unstable();
                if owned != all {
                    return Err(
                        "every requirement belongs to exactly one entity or to the mission".into(),
                    );
                }
                Ok(())
            }
            other => Err(format!("unknown record schema {other}")),
        }
    }
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
