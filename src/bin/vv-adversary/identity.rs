//! Identidade de falha, portada de `scripts/m3_failure_signature.py`.
//!
//! Temporal: (política, contrato, versão, tipo, gatilho, prazo, primeira
//! violação, mecanismo). Segurança: (política, invariante, primeiro tick de
//! falha, tipo do evento gatilho). O mecanismo vem só do comportamento do
//! atuador registado nos `counterexample_ticks`, entre o gatilho (ou 1) e a
//! violação. As validações de consistência do Python sobre evidência malformada
//! não são replicadas: a evidência vem do monitor da biblioteca.

use autonomous_systems_vv_lab::ControllerEvaluationOutcome;
use autonomous_systems_vv_lab::actuator::ActuatorBehavior;
use autonomous_systems_vv_lab::temporal::{ContractOutcome, ContractResult};
use serde::Serialize;

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub struct Identity {
    pub policy: String,
    /// `temporal` ou `safety`.
    pub kind: String,
    /// Identificador do contrato ou nome do invariante.
    pub property: String,
    pub contract_schema_version: Option<u32>,
    pub property_type: Option<String>,
    pub trigger_tick: Option<u32>,
    pub deadline_tick: Option<u64>,
    pub violation_tick: u32,
    pub trigger_event_kind: Option<String>,
    pub mechanism: Vec<String>,
}

impl Identity {
    /// Identificador usado nas listas de violações: `kind:property`.
    pub fn property_id(&self) -> String {
        format!("{}:{}", self.kind, self.property)
    }

    /// Identidade sem ticks: (política, tipo, propriedade, mecanismo).
    pub fn class_key(&self) -> ClassKey {
        (
            self.policy.clone(),
            self.kind.clone(),
            self.property.clone(),
            self.mechanism.clone(),
        )
    }

    pub fn class_label(&self) -> String {
        format!(
            "{}/{}/{}/{}",
            self.policy,
            self.kind,
            self.property,
            if self.mechanism.is_empty() {
                "none".to_owned()
            } else {
                self.mechanism.join("+")
            }
        )
    }
}

fn mechanism_of(behavior: ActuatorBehavior) -> Option<&'static str> {
    match behavior {
        ActuatorBehavior::Identity => None,
        ActuatorBehavior::Lost => Some("command_not_applied"),
        ActuatorBehavior::Delayed | ActuatorBehavior::DelayedExecution => Some("delayed_actuation"),
        ActuatorBehavior::ContinuedMovement => Some("continuing_actuation"),
    }
}

/// Chave de classe: (política, tipo, propriedade, mecanismo).
pub type ClassKey = (String, String, String, Vec<String>);

/// Violações do resultado: identificadas e as que não deram identidade.
pub struct Scan {
    pub identities: Vec<Identity>,
    /// `kind:property:unidentified`, uma por violação sem identidade.
    pub unidentified: Vec<String>,
}

/// Todas as violações do resultado: invariantes de segurança e depois contratos.
pub fn violations(policy: &str, outcome: &ControllerEvaluationOutcome) -> Vec<Identity> {
    scan(policy, outcome).identities
}

/// Como `violations`, mas sem perder em silêncio as falhas sem identidade.
pub fn scan(policy: &str, outcome: &ControllerEvaluationOutcome) -> Scan {
    let mut found = Vec::new();
    let mut unidentified = Vec::new();
    for invariant in &outcome.artifact.expected_report.invariants {
        if invariant.passed {
            continue;
        }
        let Some(first) = invariant.failures.first() else {
            unidentified.push(format!("safety:{}:unidentified", invariant.name));
            continue;
        };
        found.push(Identity {
            policy: policy.to_owned(),
            kind: "safety".into(),
            property: invariant.name.clone(),
            contract_schema_version: None,
            property_type: None,
            trigger_tick: None,
            deadline_tick: None,
            violation_tick: first.tick,
            trigger_event_kind: Some(first.trigger_event_kind.clone()),
            mechanism: Vec::new(),
        });
    }
    for result in &outcome.verification.contract_results {
        if result.outcome != ContractOutcome::Fail {
            continue;
        }
        match temporal_identity(policy, result, outcome) {
            Some(identity) => found.push(identity),
            None => unidentified.push(format!("temporal:{}:unidentified", result.contract_id)),
        }
    }
    Scan {
        identities: found,
        unidentified,
    }
}

fn temporal_identity(
    policy: &str,
    result: &ContractResult,
    outcome: &ControllerEvaluationOutcome,
) -> Option<Identity> {
    let violation_tick = result.first_violation_tick?;
    let evidence = result.evidence.iter().find(|item| {
        item.outcome == ContractOutcome::Fail && item.violation_tick == Some(violation_tick)
    })?;
    let property_type = serde_json::to_value(result.property_type)
        .ok()?
        .as_str()?
        .to_owned();
    let bounded = matches!(
        property_type.as_str(),
        "bounded_response" | "bounded_progress"
    );
    let (trigger_tick, deadline_tick) = if bounded {
        (evidence.trigger_tick, evidence.deadline_tick)
    } else {
        (
            evidence.trigger_tick.or(result.first_trigger_tick),
            result.deadline_tick,
        )
    };
    let mut mechanism = std::collections::BTreeSet::new();
    let mut overlap = false;
    if let Some(failure) = outcome
        .verification
        .failures
        .iter()
        .find(|failure| failure.contract_id == result.contract_id)
    {
        let first = trigger_tick.unwrap_or(1);
        for tick in &failure.counterexample_ticks {
            if (first..=violation_tick).contains(&tick.tick) {
                overlap = true;
                if let Some(label) = mechanism_of(tick.actuator_behavior) {
                    mechanism.insert(label.to_owned());
                }
            }
        }
    }
    if mechanism.is_empty() {
        mechanism.insert(
            if overlap {
                "no_actuator_fault_observed"
            } else {
                "no_actuator_window_recorded"
            }
            .to_owned(),
        );
    }
    Some(Identity {
        policy: policy.to_owned(),
        kind: "temporal".into(),
        property: result.contract_id.clone(),
        contract_schema_version: Some(result.schema_version),
        property_type: Some(property_type),
        trigger_tick,
        deadline_tick,
        violation_tick,
        trigger_event_kind: None,
        mechanism: mechanism.into_iter().collect(),
    })
}
