//! Estruturas de `campaign.json` (ordem fixa de campos, só `BTreeMap`).

use std::collections::BTreeMap;

use autonomous_systems_vv_lab::actuator::{ActuatorBehavior, ActuatorFaultEvent};
use autonomous_systems_vv_lab::mission_analysis::MissionOutcome;
use autonomous_systems_vv_lab::model::{Action, MissionState, Point, RunStatus, SafetyState};
use autonomous_systems_vv_lab::temporal::ContractOutcome;
use serde::Serialize;

use crate::atoms::Atom;
use crate::eval::PolicySummary;
use crate::identity::Identity;
use crate::minimize::Step;
use crate::recheck::Recheck;
use crate::sampling::Refs;

pub const SCHEMA: &str = "vv-adversary.campaign.v1";

#[derive(Serialize)]
pub struct Body {
    pub schema: &'static str,
    pub prng: PrngInfo,
    pub limits: Limits,
    pub inputs: InputInfo,
    pub source_sha256: String,
    pub design: Design,
    pub references: Refs,
    pub control: Vec<PolicyRow>,
    pub candidates: Vec<CandidateRow>,
    pub failures: Vec<FailureRow>,
    pub metrics: Metrics,
    pub policy_matrix: BTreeMap<String, BTreeMap<String, u32>>,
}

#[derive(Serialize)]
pub struct Campaign<'a> {
    #[serde(flatten)]
    pub body: &'a Body,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub campaign_sha256: Option<String>,
}

#[derive(Serialize)]
pub struct PrngInfo {
    pub algorithm: &'static str,
    pub domain: String,
    pub seed_mixing: &'static str,
    pub campaign_seed: u64,
    pub sim_seed: u64,
}

#[derive(Serialize)]
pub struct Limits {
    pub budget: u32,
    pub minimize_budget: u32,
    pub max_failures: u32,
    pub policies: Vec<String>,
    pub stall_window_ticks: u32,
    pub min_progress_mm: u32,
    pub search: &'static str,
    pub phase_a_candidates: u32,
    pub top_k: usize,
    pub max_atoms_phase_a: u32,
    pub max_atoms_phase_b: usize,
}

#[derive(Serialize)]
pub struct InputInfo {
    pub scenario_name: String,
    pub scenario_steps: u32,
    pub scenario_sha256: String,
    pub contracts_sha256: String,
    pub actuator_sha256: String,
    pub actuator_source: &'static str,
    pub background: Background,
}

/// Falhas da base mantidas como fundo fixo (não são átomos).
#[derive(Serialize)]
pub struct Background {
    pub gps_dropout_windows: usize,
    pub packet_loss_windows: usize,
    pub gps_dropout_permille: u16,
    pub packet_loss_permille: u16,
    pub gps_noise_max_mm: i32,
    pub delay_min_ticks: u32,
    pub delay_max_ticks: u32,
    pub actuator_faults: usize,
}

#[derive(Serialize)]
pub struct Design {
    pub violation: &'static str,
    pub risk_formula: &'static str,
    pub identity: &'static str,
    pub class_key: &'static str,
    pub minimization: &'static str,
    pub recheck: &'static str,
    pub conflicting_inputs: &'static str,
    pub background_policy: &'static str,
    pub fault_kinds: Vec<&'static str>,
}

#[derive(Serialize)]
pub struct PolicyRow {
    pub policy: String,
    #[serde(flatten)]
    pub summary: PolicySummary,
}

#[derive(Serialize)]
pub struct CandidateRow {
    pub index: usize,
    pub phase: &'static str,
    pub parent: Option<usize>,
    pub atoms: Vec<Atom>,
    pub active_fault_ticks: u64,
    pub results: BTreeMap<String, PolicySummary>,
}

#[derive(Serialize)]
pub struct Pair<T> {
    pub before: T,
    pub after: T,
}

#[derive(Serialize)]
pub struct Reduction {
    pub atoms: Pair<usize>,
    pub active_fault_ticks: Pair<u64>,
    pub steps: Pair<u32>,
    pub evaluations_used: u32,
    pub evaluation_budget: u32,
    pub budget_exhausted: bool,
    pub one_minimal_verified: bool,
}

#[derive(Serialize)]
pub struct CaseSide {
    pub dir: String,
    pub atoms: Vec<Atom>,
    pub steps: u32,
    pub active_fault_ticks: u64,
    pub safety: RunStatus,
    pub temporal: ContractOutcome,
    pub mission: MissionOutcome,
    pub violations: Vec<String>,
    pub m4_sha256: String,
}

#[derive(Serialize)]
pub struct TraceRow {
    pub tick: u32,
    pub truth_from: Point,
    pub truth_position: Point,
    pub safety_state: SafetyState,
    pub mission_state: MissionState,
    pub requested_action: Action,
    pub realized_action: Option<Action>,
    pub actuator_behavior: Option<ActuatorBehavior>,
    pub fault_events: Vec<ActuatorFaultEvent>,
}

#[derive(Serialize)]
pub struct Evidence {
    pub expected: String,
    pub observed: String,
}

#[derive(Serialize)]
pub struct Comparison {
    pub failing_policy: bool,
    pub safety: RunStatus,
    pub temporal: ContractOutcome,
    pub mission: MissionOutcome,
    pub violations: Vec<String>,
    pub same_property_violated: bool,
    pub same_class_violated: bool,
}

#[derive(Serialize)]
pub struct FailureRow {
    pub case: u32,
    pub class: String,
    pub identity: Identity,
    pub candidate_index: usize,
    /// A classe já existe no controlo (base sem átomos): não foi descoberta pela pesquisa.
    pub inherited_from_control: bool,
    pub original: CaseSide,
    pub minimized: CaseSide,
    pub reduction_log: Vec<Step>,
    pub reduction: Reduction,
    pub evidence: Evidence,
    pub causal_trace: Vec<TraceRow>,
    pub recheck: Recheck,
    pub policy_comparison: BTreeMap<String, Comparison>,
}

#[derive(Serialize)]
pub struct Evaluations {
    pub control: u32,
    pub search: u32,
    pub minimization: u32,
    pub case_artifacts: u32,
    pub total: u32,
}

#[derive(Serialize)]
pub struct Metrics {
    pub candidates: usize,
    pub phase_a: usize,
    pub phase_b: usize,
    pub evaluations: Evaluations,
    pub violating_candidates: usize,
    pub violations_by_policy: BTreeMap<String, BTreeMap<String, u32>>,
    /// Todas as classes vistas (novas e herdadas do controlo).
    pub unique_classes_found: usize,
    pub novel_classes_found: usize,
    pub inherited_classes_found: usize,
    pub unique_classes_kept: usize,
    pub inconclusive_evaluations: usize,
    pub control_violations: usize,
    /// Violações sem identidade extraível (controlo e candidatos).
    pub unidentified_violations: usize,
    pub recheck: BTreeMap<String, u32>,
}
