//! Contrato tipado da experiência: suites, sementes, orçamentos e configurações.
//!
//! Uma configuração do controlador é a política V1 e um conjunto fechado de
//! parâmetros do sistema sob teste. Nenhuma alteração toca nos ficheiros da
//! biblioteca, exceto a opção do atuador `cancel_pending_on_fallback`, desativada por omissão.

use std::collections::BTreeSet;

use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::model::Scenario;
use serde::{Deserialize, Serialize};

pub const SCHEMA: &str = "vv-repair.experiment.v1";
const MAX_SUITES: usize = 6;
const MAX_CANDIDATES: usize = 8;
const MAX_SEEDS: usize = 64;
const MAX_WORKLOADS_PER_SEED: u32 = 64;
const MAX_SIM_SEEDS: usize = 4;
/// Limite de avaliações planeadas, antes da redução.
pub const MAX_PLANNED_EVALUATIONS: u64 = 250_000;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Experiment {
    pub schema: String,
    pub name: String,
    pub sim_seeds: Vec<u64>,
    /// Sementes de onde sai o corpus de contraexemplos conhecidos.
    pub tuning_seeds: Vec<u64>,
    /// Sementes reservadas para procurar falhas novas e detetar sobreajuste.
    pub heldout_seeds: Vec<u64>,
    pub workloads_per_seed: u32,
    pub minimize_budget: u32,
    pub max_corpus_per_suite: u32,
    pub suites: Vec<SuiteSpec>,
    pub acceptance: Acceptance,
    pub baseline: ControllerConfig,
    pub candidates: Vec<ControllerConfig>,
}

/// Critérios de aceitação registados antes da execução. A análise Python
/// aplica-os aos pares (carga, semente) das sementes reservadas.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Acceptance {
    /// Nível bilateral dos intervalos e testes, em permilagem (50 = 95%).
    pub alpha_permille: u32,
    /// Máximo de pares em que a base conclui a missão e a candidata não,
    /// em permilagem dos pares em que a base conclui.
    pub max_completion_loss_permille: u32,
    /// Margem de não inferioridade da distância restante média, em mm.
    pub max_mean_distance_increase_mm: u32,
    /// Mínimo de pares reservados por suite para emitir um veredicto.
    pub min_heldout_pairs: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SuiteSpec {
    pub id: String,
    pub scenario: String,
    pub contracts: String,
    #[serde(default)]
    pub actuator: Option<String>,
    /// Para que serve a suite no relatório (opcional, até 300 caracteres).
    #[serde(default)]
    pub description: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerConfig {
    pub id: String,
    pub policy: ControllerPolicyV1,
    #[serde(default)]
    pub overrides: Overrides,
    pub rationale: String,
    /// `control` marca uma configuração que testa o laboratório, não o controlador.
    #[serde(default)]
    pub role: Role,
    /// Resultado previsto antes da execução, só para controlos.
    #[serde(default)]
    pub expect: Expect,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    #[default]
    Candidate,
    Control,
}

/// Eixos do veredicto calculado por `scripts/m6_analysis.py`.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Safety {
    Improved,
    Mixed,
    Regressed,
    NoEffect,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Progress {
    Pass,
    Fail,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Decision {
    Accept,
    Reject,
}

/// Veredicto previsto de um controlo, eixo a eixo.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Expect {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub safety: Option<Safety>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub progress: Option<Progress>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decision: Option<Decision>,
}

/// Parâmetros do controlador que uma candidata pode alterar. Campos ausentes
/// mantêm o valor do cenário.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Overrides {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_after_ticks: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery_after_ticks: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub confidence_threshold_permille: Option<u16>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_observation_age_ticks: Option<u32>,
    /// Escala do passo comandado (`vehicle.step_mm`), em permilagem.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stride_permille: Option<u32>,
    /// Cancela os comandos atrasados pendentes quando o controlador entra em *fallback*.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cancel_pending_on_fallback: Option<bool>,
}

impl Overrides {
    /// Devolve o cenário com os parâmetros substituídos e validados.
    pub fn apply(&self, base: &Scenario) -> Result<Scenario, String> {
        let mut scenario = base.clone();
        if let Some(value) = self.fallback_after_ticks {
            scenario.safety.fallback_after_ticks = value;
        }
        if let Some(value) = self.recovery_after_ticks {
            scenario.safety.recovery_after_ticks = value;
        }
        if let Some(value) = self.confidence_threshold_permille {
            scenario.safety.confidence_threshold_permille = value;
        }
        if let Some(value) = self.max_observation_age_ticks {
            scenario.sensors.max_observation_age_ticks = value;
        }
        if let Some(permille) = self.stride_permille {
            let scaled = i64::from(scenario.vehicle.step_mm) * i64::from(permille) / 1000;
            scenario.vehicle.step_mm =
                i32::try_from(scaled).map_err(|_| "stride_permille overflows step_mm")?;
        }
        scenario
            .validate()
            .map_err(|error| format!("override produces an invalid scenario: {error}"))?;
        Ok(scenario)
    }

    /// Devolve a configuração do atuador com a opção de cancelamento substituída.
    pub fn apply_actuator(&self, base: &ActuatorConfig) -> ActuatorConfig {
        let mut config = base.clone();
        if let Some(value) = self.cancel_pending_on_fallback {
            config.cancel_pending_on_fallback = value;
        }
        config
    }
}

fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

/// Caminho relativo ao ficheiro da experiência: sem unidade, raiz nem UNC.
fn valid_path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && !value.contains(['\0', ':'])
        && !value.starts_with(['/', '\\'])
}

impl Experiment {
    pub fn configs(&self) -> impl Iterator<Item = &ControllerConfig> {
        std::iter::once(&self.baseline).chain(&self.candidates)
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.schema != SCHEMA {
            return Err(format!("experiment schema must be {SCHEMA}"));
        }
        if !valid_id(&self.name) {
            return Err("name must match [a-z0-9_]{1,32}".into());
        }
        if self.sim_seeds.is_empty() || self.sim_seeds.len() > MAX_SIM_SEEDS {
            return Err(format!("sim_seeds needs 1 to {MAX_SIM_SEEDS} seeds"));
        }
        for (field, seeds) in [
            ("tuning_seeds", &self.tuning_seeds),
            ("heldout_seeds", &self.heldout_seeds),
        ] {
            if seeds.is_empty() || seeds.len() > MAX_SEEDS {
                return Err(format!("{field} needs 1 to {MAX_SEEDS} seeds"));
            }
        }
        let mut seen = BTreeSet::new();
        if self.sim_seeds.iter().collect::<BTreeSet<_>>().len() != self.sim_seeds.len()
            || self
                .tuning_seeds
                .iter()
                .chain(&self.heldout_seeds)
                .any(|seed| !seen.insert(*seed))
        {
            return Err("seeds must not repeat and tuning/heldout must be disjoint".into());
        }
        if !(1..=MAX_WORKLOADS_PER_SEED).contains(&self.workloads_per_seed) {
            return Err(format!(
                "workloads_per_seed must be between 1 and {MAX_WORKLOADS_PER_SEED}"
            ));
        }
        if !(1..=256).contains(&self.minimize_budget) {
            return Err("minimize_budget must be between 1 and 256".into());
        }
        if !(1..=16).contains(&self.max_corpus_per_suite) {
            return Err("max_corpus_per_suite must be between 1 and 16".into());
        }
        let gate = &self.acceptance;
        if ![10, 50, 100].contains(&gate.alpha_permille)
            || gate.max_completion_loss_permille > 1000
            || gate.max_mean_distance_increase_mm > 100_000
            || !(1..=100_000).contains(&gate.min_heldout_pairs)
        {
            return Err(
                "acceptance values are out of range (alpha_permille: 10, 50 or 100)".into(),
            );
        }
        if self.suites.is_empty() || self.suites.len() > MAX_SUITES {
            return Err(format!("suites needs 1 to {MAX_SUITES} entries"));
        }
        let mut suite_ids = BTreeSet::new();
        for suite in &self.suites {
            if !valid_id(&suite.id) || !suite_ids.insert(suite.id.as_str()) {
                return Err(format!("suite id '{}' is invalid or repeated", suite.id));
            }
            let paths = [
                Some(&suite.scenario),
                Some(&suite.contracts),
                suite.actuator.as_ref(),
            ];
            if paths.into_iter().flatten().any(|path| !valid_path(path)) {
                return Err(format!("suite '{}' has an invalid path", suite.id));
            }
            if suite.description.len() > 300 {
                return Err(format!("suite '{}' description is too long", suite.id));
            }
        }
        if self.baseline.role != Role::Candidate {
            return Err("the baseline cannot be a control".into());
        }
        if self.candidates.is_empty() || self.candidates.len() > MAX_CANDIDATES {
            return Err(format!("candidates needs 1 to {MAX_CANDIDATES} entries"));
        }
        let mut config_ids = BTreeSet::new();
        for config in self.configs() {
            if !valid_id(&config.id) || !config_ids.insert(config.id.as_str()) {
                return Err(format!("config id '{}' is invalid or repeated", config.id));
            }
            if config.rationale.trim().is_empty() || config.rationale.len() > 1000 {
                return Err(format!("config '{}' needs a rationale", config.id));
            }
            if config.role != Role::Control && config.expect != Expect::default() {
                return Err(format!(
                    "config '{}': expect is only for controls",
                    config.id
                ));
            }
        }
        if self.planned_evaluations() > MAX_PLANNED_EVALUATIONS {
            return Err(format!(
                "experiment plans more than {MAX_PLANNED_EVALUATIONS} evaluations"
            ));
        }
        Ok(())
    }

    /// Majorante: quatro projeções por conjunto amostrado, mais o controlo.
    pub fn planned_evaluations(&self) -> u64 {
        let seeds = (self.tuning_seeds.len() + self.heldout_seeds.len()) as u64;
        let workloads = seeds * u64::from(self.workloads_per_seed) * 4 + 1;
        workloads
            * self.suites.len() as u64
            * self.sim_seeds.len() as u64
            * (self.candidates.len() as u64 + 1)
    }
}
