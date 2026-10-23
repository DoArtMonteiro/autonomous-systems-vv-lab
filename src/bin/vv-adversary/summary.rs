//! Linhas agregadas de `campaign.json`: entradas, candidatos, métricas e matriz.

use std::collections::{BTreeMap, BTreeSet};

use autonomous_systems_vv_lab::temporal::ContractOutcome;

use crate::campaign::Inputs;
use crate::eval::{Ctx, PolicySummary};
use crate::identity::ClassKey;
use crate::io::sha256_hex;
use crate::model::*;
use crate::search::Candidate;

pub fn input_info(inputs: &Inputs, ctx: &Ctx) -> InputInfo {
    let sensors = &ctx.base.sensors;
    InputInfo {
        scenario_name: ctx.base.name.clone(),
        scenario_steps: ctx.base.steps,
        scenario_sha256: sha256_hex(&inputs.scenario),
        contracts_sha256: sha256_hex(&inputs.contracts),
        actuator_sha256: sha256_hex(&inputs.actuator),
        actuator_source: if inputs.actuator_from_file {
            "file"
        } else {
            "default"
        },
        background: Background {
            gps_dropout_windows: sensors.gps.dropout_windows.len(),
            packet_loss_windows: sensors.communication.packet_loss_windows.len(),
            gps_dropout_permille: sensors.gps.dropout_permille,
            packet_loss_permille: sensors.communication.packet_loss_permille,
            gps_noise_max_mm: sensors.gps.noise_max_mm,
            delay_min_ticks: sensors.communication.delay_min_ticks,
            delay_max_ticks: sensors.communication.delay_max_ticks,
            actuator_faults: ctx.actuator.faults.len(),
        },
    }
}

pub fn design() -> Design {
    Design {
        violation: "safety invariant passed=false OR temporal contract FAIL; INCONCLUSIVE is not a violation",
        risk_formula: "1000*(failed_safety+failed_temporal) + 100*inconclusive + 20*fallback_ticks + 10*waypoints_remaining + 50*[mission!=completed] + min(actuator_fault_events,100); candidate risk = sum over policies",
        identity: "temporal: policy, contract_id, schema_version, property_type, trigger_tick, deadline_tick, first violation_tick, mechanism set; safety: policy, invariant, first failure tick, trigger_event_kind",
        class_key: "policy, kind, property, mechanism",
        minimization: "ddmin over atoms, per-atom simplification, horizon truncation (binary search with window clipping), final 1-minimality pass; a step is accepted only if the full identity (including ticks) is reproduced with the same sim seed",
        recheck: "first violation recomputed from RunReport.telemetry with public geometry; applies to restricted_zone, world_bounds and telemetry-derivable always/never/bounded_response contracts",
        conflicting_inputs: "proxy only: gps_noise (observation disagrees with truth) combined with delayed or lost delivery; the model has a single sensor",
        background_policy: "faults already present in the base scenario/actuator stay fixed (clipped to the horizon on truncation); atoms are added on top",
        fault_kinds: vec![
            "gps_dropout",
            "packet_loss",
            "gps_dropout_rate",
            "packet_loss_rate",
            "comm_delay",
            "gps_noise",
            "actuator_delay",
            "actuator_lost",
            "actuator_continued",
        ],
    }
}

pub fn policy_rows(policies: &[String], results: &[PolicySummary]) -> Vec<PolicyRow> {
    policies
        .iter()
        .zip(results)
        .map(|(policy, summary)| PolicyRow {
            policy: policy.clone(),
            summary: summary.clone(),
        })
        .collect()
}

pub fn candidate_rows(policies: &[String], candidates: &[Candidate]) -> Vec<CandidateRow> {
    candidates
        .iter()
        .map(|candidate| CandidateRow {
            index: candidate.index,
            phase: candidate.phase,
            parent: candidate.parent,
            atoms: candidate.spec.atoms.clone(),
            active_fault_ticks: candidate.spec.active_fault_ticks(),
            results: policies
                .iter()
                .cloned()
                .zip(candidate.results.iter().cloned())
                .collect(),
        })
        .collect()
}

/// Classes de falha já presentes no controlo (base sem átomos).
pub fn control_classes(control: &[PolicySummary]) -> BTreeSet<ClassKey> {
    control
        .iter()
        .flat_map(|summary| summary.identities.iter().map(|id| id.class_key()))
        .collect()
}

pub fn metrics(
    policies: &[String],
    candidates: &[Candidate],
    control: &[PolicySummary],
    failures: &[FailureRow],
    kept: usize,
    found: &BTreeSet<ClassKey>,
    evaluations: Evaluations,
) -> Metrics {
    let mut by_policy: BTreeMap<String, BTreeMap<String, u32>> = BTreeMap::new();
    let mut inconclusive = 0;
    for candidate in candidates {
        for (policy, result) in policies.iter().zip(&candidate.results) {
            let entry = by_policy.entry(policy.clone()).or_default();
            for property in &result.violations {
                *entry.entry(property.clone()).or_default() += 1;
            }
            if result.temporal == ContractOutcome::Inconclusive || !result.inconclusive.is_empty() {
                inconclusive += 1;
            }
        }
    }
    let inherited = control_classes(control);
    let inherited_found = found.iter().filter(|key| inherited.contains(*key)).count();
    let unidentified = control
        .iter()
        .chain(candidates.iter().flat_map(|c| &c.results))
        .map(|result| result.unidentified_violations)
        .sum();
    let mut recheck_counts: BTreeMap<String, u32> = BTreeMap::new();
    for failure in failures {
        *recheck_counts
            .entry(failure.recheck.result.to_owned())
            .or_default() += 1;
    }
    Metrics {
        candidates: candidates.len(),
        phase_a: candidates.iter().filter(|c| c.phase == "A").count(),
        phase_b: candidates.iter().filter(|c| c.phase == "B").count(),
        evaluations,
        violating_candidates: candidates.iter().filter(|c| c.failing()).count(),
        violations_by_policy: by_policy,
        unique_classes_found: found.len(),
        novel_classes_found: found.len() - inherited_found,
        inherited_classes_found: inherited_found,
        unique_classes_kept: kept,
        inconclusive_evaluations: inconclusive,
        control_violations: control.iter().map(|r| r.violations.len()).sum(),
        unidentified_violations: unidentified,
        recheck: recheck_counts,
    }
}

/// Por propriedade: candidatos que falham só numa política, em ambas ou em nenhuma.
pub fn matrix(
    policies: &[String],
    candidates: &[Candidate],
) -> BTreeMap<String, BTreeMap<String, u32>> {
    let mut properties = BTreeSet::new();
    for candidate in candidates {
        for result in &candidate.results {
            properties.extend(result.violations.iter().cloned());
        }
    }
    let mut table = BTreeMap::new();
    for property in properties {
        let mut row: BTreeMap<String, u32> = BTreeMap::new();
        for candidate in candidates {
            let failing: Vec<&String> = policies
                .iter()
                .zip(&candidate.results)
                .filter(|(_, result)| result.violations.contains(&property))
                .map(|(policy, _)| policy)
                .collect();
            let key = match (failing.len(), policies.len()) {
                (0, _) => "neither".to_owned(),
                (n, total) if n == total && total > 1 => "both".to_owned(),
                (_, 1) => "fail".to_owned(),
                _ => format!("only:{}", failing[0]),
            };
            *row.entry(key).or_default() += 1;
        }
        table.insert(property, row);
    }
    table
}
