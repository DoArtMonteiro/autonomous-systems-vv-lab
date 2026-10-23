//! Contexto da campanha e avaliação de um candidato com uma política.

use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::contracts::ContractSet;
use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::mission_analysis::{MissionOutcome, MissionPolicy};
use autonomous_systems_vv_lab::model::{RunStatus, Scenario};
use autonomous_systems_vv_lab::temporal::ContractOutcome;
use autonomous_systems_vv_lab::{
    ControllerEvaluationOutcome, controller_id, run_controller_evaluation,
};
use serde::Serialize;

use crate::atoms::Spec;
use crate::identity::{self, Identity};

/// Estratégia de pesquisa. `guided`: fronteiras e fase B; `biased`: só fronteiras;
/// `uniform`: nenhuma das duas (a predefinição, ver `scripts/adversarial_ablation.py`).
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Search {
    Guided,
    Biased,
    Uniform,
}

impl Search {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "guided" => Ok(Self::Guided),
            "biased" => Ok(Self::Biased),
            "uniform" => Ok(Self::Uniform),
            _ => Err(format!("unsupported search strategy '{value}'")),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Guided => "guided",
            Self::Biased => "biased",
            Self::Uniform => "uniform",
        }
    }
}

pub struct Params {
    pub search: Search,
    pub campaign_seed: u64,
    pub sim_seed: u64,
    pub policies: Vec<ControllerPolicyV1>,
    pub budget: u32,
    pub minimize_budget: u32,
    pub max_failures: u32,
    pub mission_policy: MissionPolicy,
}

impl Params {
    pub fn validate(&self) -> Result<(), String> {
        if self.policies.is_empty() || self.policies.len() > 2 {
            return Err("--policies needs one or two distinct policies".into());
        }
        if self.policies.len() == 2 && self.policies[0] == self.policies[1] {
            return Err("--policies must not repeat a policy".into());
        }
        if !(1..=512).contains(&self.budget) {
            return Err("--budget must be between 1 and 512".into());
        }
        if !(1..=256).contains(&self.minimize_budget) {
            return Err("--minimize-budget must be between 1 and 256".into());
        }
        if !(1..=16).contains(&self.max_failures) {
            return Err("--max-failures must be between 1 and 16".into());
        }
        self.mission_policy
            .validate()
            .map(|_| ())
            .map_err(|error| error.to_string())
    }
}

pub struct Ctx {
    pub base: Scenario,
    pub actuator: ActuatorConfig,
    pub contracts: ContractSet,
    pub params: Params,
}

pub fn policy_name(policy: ControllerPolicyV1) -> &'static str {
    controller_id(policy)
}

impl Ctx {
    /// Executa o M4 completo para o candidato; `Err` só em entradas inválidas.
    pub fn run(
        &self,
        spec: &Spec,
        policy: ControllerPolicyV1,
    ) -> Result<ControllerEvaluationOutcome, String> {
        let (scenario, actuator) = spec.apply(&self.base, &self.actuator)?;
        self.evaluate(scenario, actuator, policy)
    }

    /// Executa o M4 sobre um cenário já montado; `Err` é erro do motor.
    pub fn evaluate(
        &self,
        scenario: Scenario,
        actuator: ActuatorConfig,
        policy: ControllerPolicyV1,
    ) -> Result<ControllerEvaluationOutcome, String> {
        run_controller_evaluation(
            scenario,
            self.params.sim_seed,
            policy,
            actuator,
            self.contracts.clone(),
            self.params.mission_policy,
        )
        .map_err(|error| error.to_string())
    }
}

/// Resumo de um candidato com uma política (linha de `campaign.json`).
#[derive(Clone, Debug, Serialize)]
pub struct PolicySummary {
    pub safety: RunStatus,
    pub temporal: ContractOutcome,
    pub mission: MissionOutcome,
    pub violations: Vec<String>,
    pub inconclusive: Vec<String>,
    /// Violações sem identidade extraível: contam como violação, nunca desaparecem.
    pub unidentified_violations: usize,
    pub risk: u64,
    #[serde(skip)]
    pub identities: Vec<Identity>,
}

/// Risco inteiro: quanto mais perto de uma violação (ou já em violação), maior.
///
/// `1000*(invariantes falhados + contratos falhados) + 100*inconclusivos
///  + 20*fallback_ticks + 10*waypoints_em_falta + 50*[missão != concluída]
///  + min(eventos de falha do atuador, 100)`.
pub fn risk(outcome: &ControllerEvaluationOutcome) -> u64 {
    let metrics = &outcome.manifest.metrics;
    let mut score = 1000
        * (u64::from(metrics.failed_safety_invariants)
            + u64::from(metrics.failed_temporal_contracts));
    score += 100 * u64::from(metrics.inconclusive_temporal_contracts);
    score += 20 * u64::from(metrics.fallback_ticks);
    score += 10 * metrics.waypoints_remaining as u64;
    if metrics.mission_outcome != MissionOutcome::Completed {
        score += 50;
    }
    score + outcome.verification.actuator_fault_event_count.min(100)
}

pub fn summarize(
    policy: ControllerPolicyV1,
    outcome: &ControllerEvaluationOutcome,
) -> PolicySummary {
    let scan = identity::scan(policy_name(policy), outcome);
    let identities = scan.identities;
    let inconclusive = outcome
        .verification
        .contract_results
        .iter()
        .filter(|result| result.outcome == ContractOutcome::Inconclusive)
        .map(|result| format!("temporal:{}", result.contract_id))
        .collect();
    let metrics = &outcome.manifest.metrics;
    PolicySummary {
        safety: metrics.safety_status,
        temporal: metrics.temporal_status,
        mission: metrics.mission_outcome,
        violations: identities
            .iter()
            .map(Identity::property_id)
            .chain(scan.unidentified.iter().cloned())
            .collect(),
        inconclusive,
        unidentified_violations: scan.unidentified.len(),
        risk: risk(outcome),
        identities,
    }
}
