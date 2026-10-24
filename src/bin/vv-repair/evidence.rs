//! Esquema de `evidence.json` (`vv-repair.evidence.v1`): ordem fixa de campos e só `BTreeMap`.

use std::collections::BTreeMap;

use autonomous_systems_vv_lab::ControllerEvaluationOutcome;
use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::contracts::PropertyType;
use autonomous_systems_vv_lab::mission_analysis::MissionOutcome;
use autonomous_systems_vv_lab::model::Scenario;
use autonomous_systems_vv_lab::temporal::{ContractOutcome, ContractResult};
use serde::Serialize;

use crate::atoms::Atom;
use crate::experiment::{Expect, Experiment, Overrides, Role};
use crate::identity::{self, Identity};
use crate::model::{Evidence, TraceRow};
use crate::recheck::Recheck;
use crate::workloads::Workload;

pub const EVIDENCE_SCHEMA: &str = "vv-repair.evidence.v1";

/// Classe de falha sem política nem ticks: `tipo/propriedade/mecanismo`.
pub fn label(identity: &Identity) -> String {
    let mechanism = if identity.mechanism.is_empty() {
        "none".to_owned()
    } else {
        identity.mechanism.join("+")
    };
    format!("{}/{}/{mechanism}", identity.kind, identity.property)
}

/// `tipo/propriedade` de uma classe.
fn property_of(class: &str) -> &str {
    class.rsplit_once('/').map_or(class, |(head, _)| head)
}

#[derive(Clone, Serialize)]
pub struct Row {
    /// Classes violadas (ver `label`); as violações sem identidade entram como `tipo:propriedade:unidentified`.
    pub violations: Vec<String>,
    pub first_violation_tick: Option<u32>,
    /// Contratos `INCONCLUSIVE`: nunca contam como violação nem como resolução.
    pub inconclusive: Vec<String>,
    /// Contratos com gatilho (`bounded_response`, `bounded_progress`) que nunca foi
    /// ativado: o seu `PASS` é vazio. `always`, `never` e `ordered_transition` não têm gatilho.
    pub untriggered: Vec<String>,
    pub mission: MissionOutcome,
    pub completion_tick: Option<u32>,
    pub waypoints_completed: usize,
    pub fallback_ticks: u32,
    pub movement_ticks: u32,
    pub actuator_fault_events: u64,
    pub distance_remaining_mm: Option<u64>,
}

impl Row {
    /// Resume uma avaliação; `unidentified` acumula as violações sem identidade.
    pub fn from_outcome(
        outcome: &ControllerEvaluationOutcome,
        policy: &str,
        unidentified: &mut u64,
    ) -> Row {
        let scan = identity::scan(policy, outcome);
        *unidentified += scan.unidentified.len() as u64;
        let mut violations: Vec<String> = scan.identities.iter().map(label).collect();
        violations.extend(scan.unidentified.iter().cloned());
        violations.sort();
        violations.dedup();
        let metrics = &outcome.manifest.metrics;
        let contracts = &outcome.verification.contract_results;
        let ids = |keep: &dyn Fn(&ContractResult) -> bool| -> Vec<String> {
            contracts
                .iter()
                .filter(|result| keep(result))
                .map(|result| result.contract_id.clone())
                .collect()
        };
        Row {
            violations,
            first_violation_tick: scan.identities.iter().map(|i| i.violation_tick).min(),
            inconclusive: ids(&|result| result.outcome == ContractOutcome::Inconclusive),
            untriggered: ids(&|result| {
                matches!(
                    result.property_type,
                    PropertyType::BoundedResponse | PropertyType::BoundedProgress
                ) && result.first_trigger_tick.is_none()
            }),
            mission: metrics.mission_outcome,
            completion_tick: outcome.mission.completion_tick,
            waypoints_completed: metrics.waypoints_completed,
            fallback_ticks: metrics.fallback_ticks,
            movement_ticks: metrics.movement_action_ticks,
            actuator_fault_events: outcome.verification.actuator_fault_event_count,
            distance_remaining_mm: outcome.mission.distance_to_next_waypoint_mm,
        }
    }
}

/// Estado de uma classe conhecida numa configuração.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ReplayStatus {
    Persisted,
    /// Mesma propriedade, outro mecanismo.
    Shifted,
    Inconclusive,
    /// O contrato nunca foi ativado: um `PASS` vazio.
    Untriggered,
    /// A propriedade passa, com o gatilho ativo se for um contrato.
    Resolved,
}

impl ReplayStatus {
    pub fn of(class: &str, row: &Row) -> ReplayStatus {
        let property = property_of(class);
        let (kind, name) = property.split_once('/').unwrap_or(("", property));
        let temporal = kind == "temporal";
        if row.violations.iter().any(|v| v == class) {
            ReplayStatus::Persisted
        } else if row.violations.iter().any(|v| property_of(v) == property) {
            ReplayStatus::Shifted
        } else if temporal && row.inconclusive.iter().any(|id| id == name) {
            ReplayStatus::Inconclusive
        } else if temporal && row.untriggered.iter().any(|id| id == name) {
            ReplayStatus::Untriggered
        } else {
            ReplayStatus::Resolved
        }
    }
}

#[derive(Serialize)]
pub struct ConfigInfo<'a> {
    pub id: &'a str,
    pub policy: &'static str,
    pub overrides: &'a Overrides,
    pub rationale: &'a str,
    pub role: Role,
    pub expect: &'a Expect,
    pub config_sha256: String,
    /// O limiar de confiança e a idade máxima também definem o gatilho
    /// `localization_unreliable` dos contratos: mudar estes parâmetros muda o oráculo.
    pub changes_oracle: bool,
    /// Parâmetros efetivos por suite, depois das substituições.
    pub effective: BTreeMap<String, Effective>,
}

#[derive(Serialize)]
pub struct Effective {
    pub fallback_after_ticks: u32,
    pub recovery_after_ticks: u32,
    pub confidence_threshold_permille: u16,
    pub max_observation_age_ticks: u32,
    pub step_mm: i32,
    pub cancel_pending_on_fallback: bool,
}

impl Effective {
    pub fn of(scenario: &Scenario, actuator: &ActuatorConfig) -> Effective {
        Effective {
            fallback_after_ticks: scenario.safety.fallback_after_ticks,
            recovery_after_ticks: scenario.safety.recovery_after_ticks,
            confidence_threshold_permille: scenario.safety.confidence_threshold_permille,
            max_observation_age_ticks: scenario.sensors.max_observation_age_ticks,
            step_mm: scenario.vehicle.step_mm,
            cancel_pending_on_fallback: actuator.cancel_pending_on_fallback,
        }
    }
}

#[derive(Serialize)]
pub struct SuiteInfo {
    pub id: String,
    pub description: String,
    pub scenario_name: String,
    pub steps: u32,
    pub scenario_sha256: String,
    pub contracts_sha256: String,
    pub actuator_sha256: String,
    pub actuator_source: &'static str,
    /// Classes da base nas sementes de afinação; acima de `max_corpus_per_suite`
    /// as últimas por ordem alfabética ficam fora do corpus.
    pub corpus_classes_found: usize,
    pub corpus_classes_dropped: usize,
}

#[derive(Serialize)]
pub struct Reduction {
    pub atoms_before: usize,
    pub atoms_after: usize,
    pub steps_before: u32,
    pub steps_after: u32,
    pub evaluations: u32,
    pub exhausted: bool,
    pub one_minimal_verified: bool,
}

#[derive(Serialize)]
pub struct ReplayResult {
    pub status: ReplayStatus,
    pub violations: Vec<String>,
    pub mission: MissionOutcome,
}

#[derive(Serialize)]
pub struct Counterexample {
    pub id: String,
    pub suite: String,
    /// Configuração onde a falha foi encontrada e reduzida.
    pub found_on: String,
    pub class: String,
    pub sim_seed: u64,
    pub source_workload: usize,
    pub identity: Identity,
    pub atoms: Vec<Atom>,
    pub steps: u32,
    pub reduction: Reduction,
    pub recheck: Recheck,
    pub evidence: Evidence,
    pub causal_trace: Vec<TraceRow>,
    pub case_dir: String,
    pub m4_sha256: String,
    /// Resultado da mesma entrada reduzida em cada configuração.
    pub replay: BTreeMap<String, ReplayResult>,
}

#[derive(Serialize)]
pub struct Totals {
    pub evaluations: u64,
    pub minimization_evaluations: u64,
    pub workloads: usize,
    pub corpus: usize,
    pub introduced: usize,
    pub unidentified_violations: u64,
}

/// Configuração -> semente de simulação -> uma linha por carga.
pub type SuiteResults = BTreeMap<String, BTreeMap<String, Vec<Row>>>;

#[derive(Serialize)]
pub struct Body<'a> {
    pub schema: &'static str,
    pub experiment: &'a Experiment,
    pub experiment_sha256: String,
    pub source_sha256: String,
    pub seed_domain: String,
    pub sampling: &'static str,
    pub suites: Vec<SuiteInfo>,
    pub configs: Vec<ConfigInfo<'a>>,
    pub workloads: BTreeMap<String, Vec<Workload>>,
    pub results: BTreeMap<String, SuiteResults>,
    pub corpus: Vec<Counterexample>,
    pub introduced: Vec<Counterexample>,
    pub totals: Totals,
}

#[derive(Serialize)]
pub struct Signed<'a> {
    #[serde(flatten)]
    pub body: &'a Body<'a>,
    pub evidence_sha256: String,
}
