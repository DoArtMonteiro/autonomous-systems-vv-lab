//! Escrita de um caso: entradas aplicadas e o conjunto M4 completo.
//!
//! Os cinco artefactos M4 são serializados como em `src/m4_cli.rs`, para que
//! `vv-lab replay-m4 <caso>/m4.json` funcione.

use autonomous_systems_vv_lab::ControllerEvaluationOutcome;
use autonomous_systems_vv_lab::model::{Action, Heading, Point};

use crate::io::{pretty_json, sha256_hex};
use crate::model::{Evidence, TraceRow};

pub struct CaseFiles {
    pub files: Vec<(String, Vec<u8>)>,
    pub m4_sha256: String,
}

pub fn build(
    directory: &str,
    outcome: &ControllerEvaluationOutcome,
    contracts: &autonomous_systems_vv_lab::contracts::ContractSet,
) -> Result<CaseFiles, String> {
    let json = |value: Result<Vec<u8>, serde_json::Error>| value.map_err(|e| e.to_string());
    let m4 = json(serde_json::to_vec(&outcome.manifest))?;
    let named: Vec<(&str, Vec<u8>)> = vec![
        ("scenario.json", pretty_json(&outcome.artifact.scenario)?),
        (
            "actuator.json",
            pretty_json(&outcome.verification.actuator_config)?,
        ),
        ("contracts.json", pretty_json(contracts)?),
        ("events.json", json(serde_json::to_vec(&outcome.artifact))?),
        (
            "report.json",
            json(serde_json::to_vec(&outcome.artifact.expected_report))?,
        ),
        ("mission.json", json(serde_json::to_vec(&outcome.mission))?),
        (
            "verification.json",
            json(serde_json::to_vec(&outcome.verification))?,
        ),
        ("m4.json", m4.clone()),
    ];
    Ok(CaseFiles {
        files: named
            .into_iter()
            .map(|(name, bytes)| (format!("{directory}/{name}"), bytes))
            .collect(),
        m4_sha256: sha256_hex(&m4),
    })
}

/// Rastro causal e evidência da propriedade violada no caso minimizado.
pub fn causal_trace(
    outcome: &ControllerEvaluationOutcome,
    kind: &str,
    property: &str,
    violation_tick: u32,
) -> (Vec<TraceRow>, Evidence) {
    if kind == "temporal"
        && let Some(failure) = outcome
            .verification
            .failures
            .iter()
            .find(|failure| failure.contract_id == property)
    {
        let rows = failure
            .counterexample_ticks
            .iter()
            .map(|tick| TraceRow {
                tick: tick.tick,
                truth_from: tick.truth_from,
                truth_position: tick.truth_position,
                safety_state: tick.safety_state,
                mission_state: tick.mission_state,
                requested_action: tick.requested_action,
                realized_action: Some(tick.realized_action),
                actuator_behavior: Some(tick.actuator_behavior),
                fault_events: tick
                    .fault_events
                    .iter()
                    .map(|linked| linked.event.clone())
                    .collect(),
            })
            .collect();
        return (
            rows,
            Evidence {
                expected: failure.expected_condition.clone(),
                observed: failure.actual_condition.clone(),
            },
        );
    }
    let report = &outcome.artifact.expected_report;
    let evidence = report
        .invariants
        .iter()
        .find(|invariant| invariant.name == property)
        .and_then(|invariant| invariant.failures.first())
        .map(|failure| Evidence {
            expected: failure.expected.clone(),
            observed: failure.observed_result.clone(),
        })
        .unwrap_or(Evidence {
            expected: String::new(),
            observed: String::new(),
        });
    let low = violation_tick.saturating_sub(2).max(1);
    let rows = report
        .telemetry
        .iter()
        .enumerate()
        .filter(|(_, tick)| tick.tick >= low && tick.tick <= violation_tick + 1)
        .map(|(index, tick)| {
            let from = if index == 0 {
                outcome.artifact.scenario.vehicle.start
            } else {
                report.telemetry[index - 1].truth_position
            };
            TraceRow {
                tick: tick.tick,
                truth_from: from,
                truth_position: tick.truth_position,
                safety_state: tick.safety_state,
                mission_state: tick.mission_state,
                requested_action: tick.action,
                realized_action: Some(moved(from, tick.truth_position)),
                actuator_behavior: None,
                fault_events: Vec::new(),
            }
        })
        .collect();
    (rows, evidence)
}

/// Ação física inferida do deslocamento da verdade (um eixo por passo).
fn moved(from: Point, to: Point) -> Action {
    let (dx, dy) = (to.x_mm - from.x_mm, to.y_mm - from.y_mm);
    let heading = match (dx.signum(), dy.signum()) {
        (1, _) => Heading::East,
        (-1, _) => Heading::West,
        (_, 1) => Heading::North,
        (_, -1) => Heading::South,
        _ => return Action::hold(),
    };
    Action::step(heading, dx.abs().max(dy.abs()))
}
