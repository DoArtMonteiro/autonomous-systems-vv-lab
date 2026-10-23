//! Reverificação independente a partir de `RunReport.telemetry`.
//!
//! Não usa o monitor temporal nem os invariantes da biblioteca: recalcula a
//! primeira violação com a geometria pública e a telemetria por tick. Aplica-se
//! a `restricted_zone`, `world_bounds` e a contratos `always`/`never`/
//! `bounded_response` (sem correlação por comando) cujos predicados se
//! derivam da telemetria. Discordância = possível falso positivo ou defeito.

use autonomous_systems_vv_lab::contracts::{Contract, ContractSet, Predicate};
use autonomous_systems_vv_lab::geometry::{point_in_or_on_polygon, segment_hits_polygon};
use autonomous_systems_vv_lab::model::{MissionState, Point, RunReport, SafetyState, Scenario};
use serde::Serialize;

use crate::identity::Identity;

#[derive(Clone, Debug, Serialize)]
pub struct Recheck {
    /// `agree`, `disagree` ou `not_applicable`.
    pub result: &'static str,
    pub method: String,
    pub reported_violation_tick: u32,
    pub recomputed_first_violation_tick: Option<u32>,
}

struct View<'a> {
    scenario: &'a Scenario,
    report: &'a RunReport,
}

impl View<'_> {
    fn from(&self, index: usize) -> Point {
        if index == 0 {
            self.scenario.vehicle.start
        } else {
            self.report.telemetry[index - 1].truth_position
        }
    }

    fn holds(&self, predicate: Predicate, index: usize) -> Option<bool> {
        let tick = &self.report.telemetry[index];
        let (from, to) = (self.from(index), tick.truth_position);
        let polygon = &self.scenario.restricted_zone.vertices;
        let fallback = tick.safety_state == SafetyState::Fallback;
        Some(match predicate {
            Predicate::LocalizationUnreliable => tick.observed.as_ref().is_none_or(|sample| {
                !sample.fresh
                    || sample.confidence_permille
                        < self.scenario.safety.confidence_threshold_permille
            }),
            Predicate::SafetyFallback => fallback,
            Predicate::StopCommanded => {
                tick.action.heading.is_none() && tick.action.distance_mm == 0
            }
            Predicate::VehicleStationary => from == to,
            Predicate::RestrictedZoneClear => {
                !point_in_or_on_polygon(from, polygon) && !segment_hits_polygon(from, to, polygon)
            }
            Predicate::MovementWhileFallback => fallback && from != to,
            Predicate::MissionActive => tick.mission_state == MissionState::Running,
            _ => return None,
        })
    }

    fn first<F: Fn(usize) -> Option<bool>>(&self, violated: F) -> Option<u32> {
        (0..self.report.telemetry.len())
            .find(|index| violated(*index) == Some(true))
            .map(|index| self.report.telemetry[index].tick)
    }
}

pub fn recheck(
    scenario: &Scenario,
    report: &RunReport,
    contracts: &ContractSet,
    identity: &Identity,
) -> Recheck {
    let view = View { scenario, report };
    let reported = identity.violation_tick;
    let finish = |method: &str, recomputed: Option<u32>| Recheck {
        result: if recomputed == Some(reported) {
            "agree"
        } else {
            "disagree"
        },
        method: method.to_owned(),
        reported_violation_tick: reported,
        recomputed_first_violation_tick: recomputed,
    };
    let not_applicable = |why: &str| Recheck {
        result: "not_applicable",
        method: why.to_owned(),
        reported_violation_tick: reported,
        recomputed_first_violation_tick: None,
    };
    if identity.kind == "safety" {
        return match identity.property.as_str() {
            "restricted_zone" => finish(
                "truth start inside/on polygon or swept segment hits polygon",
                view.first(|i| view.holds(Predicate::RestrictedZoneClear, i).map(|ok| !ok)),
            ),
            "world_bounds" => finish(
                "truth segment endpoints outside Bounds::contains",
                view.first(|i| {
                    let (from, to) = (view.from(i), report.telemetry[i].truth_position);
                    Some(!scenario.bounds.contains(from) || !scenario.bounds.contains(to))
                }),
            ),
            other => not_applicable(&format!("no telemetry recomputation for invariant {other}")),
        };
    }
    let Some(contract) = contracts
        .contracts
        .iter()
        .find(|contract| contract.id() == identity.property)
    else {
        return not_applicable("contract not found in contract set");
    };
    let derivable = |predicate: Predicate| view.holds(predicate, 0).is_some();
    match contract {
        Contract::Always { predicate, .. } if derivable(*predicate) => finish(
            "predicate recomputed per tick from telemetry",
            view.first(|i| view.holds(*predicate, i).map(|ok| !ok)),
        ),
        Contract::Never { predicate, .. } if derivable(*predicate) => finish(
            "predicate recomputed per tick from telemetry",
            view.first(|i| view.holds(*predicate, i)),
        ),
        Contract::BoundedResponse {
            trigger,
            required,
            within_ticks,
            correlation: None,
            trigger_for_ticks,
            ..
        } if derivable(*trigger) && derivable(*required) => finish(
            "bounded response recomputed from telemetry facts",
            response_violation(
                &view,
                *trigger,
                *required,
                *within_ticks,
                *trigger_for_ticks,
            ),
        ),
        _ => not_applicable("operator or predicate needs command or transition events"),
    }
}

/// Violação mais cedo (tick do prazo) de uma resposta limitada sem correlação.
fn response_violation(
    view: &View<'_>,
    trigger: Predicate,
    required: Predicate,
    within: u32,
    trigger_for: u32,
) -> Option<u32> {
    let mut pending: Vec<u64> = Vec::new();
    let mut streak = 0_u32;
    let mut qualified = false;
    for (index, tick) in view.report.telemetry.iter().enumerate() {
        if view.holds(trigger, index) == Some(true) {
            streak = streak.saturating_add(1);
            if !qualified && streak >= trigger_for {
                pending.push(u64::from(tick.tick) + u64::from(within));
                qualified = true;
            }
        } else {
            streak = 0;
            qualified = false;
        }
        if view.holds(required, index) == Some(true) {
            pending.clear();
        } else if pending.first() == Some(&u64::from(tick.tick)) {
            return Some(tick.tick);
        }
    }
    None
}
