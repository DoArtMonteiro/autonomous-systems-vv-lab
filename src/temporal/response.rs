use std::collections::{BTreeMap, VecDeque};

use super::{
    ContractEvidence, ContractOutcome, EvidenceDraft, EvidenceReason, ExpectedCondition,
    ObservationState, ObservedCondition, TraceTick, evidence_row, observe,
};
use crate::contracts::{CommandOutcome, Correlation, Predicate, TraceFact};

#[derive(Clone, Debug)]
struct PendingResponse {
    trigger_tick: u32,
    deadline_tick: u64,
    trigger_index: usize,
    command_id: Option<u64>,
    unknown_count_at_trigger: u64,
}

pub(super) fn evaluate_bounded_response(
    trigger: Predicate,
    required: Predicate,
    within_ticks: u32,
    correlation: Option<Correlation>,
    trigger_for_ticks: u32,
    trace: &[TraceTick],
) -> Vec<ContractEvidence> {
    if correlation == Some(Correlation::CommandId) {
        return evaluate_correlated_response(required, within_ticks, trace);
    }
    let mut evidence = Vec::new();
    let mut pending = VecDeque::<PendingResponse>::new();
    let mut trigger_streak = 0_u32;
    let mut qualified_run = false;
    let mut unknown_response_count = 0_u64;

    for (index, tick) in trace.iter().enumerate() {
        match observe(trigger, tick) {
            ObservedCondition::True(_) => {
                trigger_streak = trigger_streak.saturating_add(1);
                if !qualified_run && trigger_streak >= trigger_for_ticks {
                    pending.push_back(PendingResponse {
                        trigger_tick: tick.tick,
                        deadline_tick: u64::from(tick.tick) + u64::from(within_ticks),
                        trigger_index: index,
                        command_id: None,
                        unknown_count_at_trigger: unknown_response_count,
                    });
                    qualified_run = true;
                }
            }
            ObservedCondition::False => {
                trigger_streak = 0;
                qualified_run = false;
            }
            ObservedCondition::Unknown => {
                trigger_streak = 0;
                qualified_run = false;
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Inconclusive,
                    trigger_tick: None,
                    deadline_tick: None,
                    violation_tick: None,
                    trigger_trace_index: None,
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::Predicate { predicate: trigger },
                    observed_fact: None,
                    observed_transition: None,
                    observation: ObservationState::Unknown,
                    reason: EvidenceReason::MissingObservation,
                    detail: Some("trigger could not be determined at this tick".into()),
                }));
            }
        }

        let response = observe(required, tick);
        if response == ObservedCondition::Unknown {
            unknown_response_count += 1;
        }
        if let ObservedCondition::True(fact) = response {
            while let Some(obligation) = pending.pop_front() {
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Pass,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: None,
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::Predicate {
                        predicate: required,
                    },
                    observed_fact: fact,
                    observed_transition: None,
                    observation: ObservationState::KnownTrue,
                    reason: EvidenceReason::ConditionObserved,
                    detail: None,
                }));
            }
        } else {
            while pending
                .front()
                .is_some_and(|obligation| u64::from(tick.tick) == obligation.deadline_tick)
            {
                let obligation = pending.pop_front().expect("front was checked");
                let unknown = unknown_response_count > obligation.unknown_count_at_trigger;
                let outcome = if unknown {
                    ContractOutcome::Inconclusive
                } else {
                    ContractOutcome::Fail
                };
                evidence.push(evidence_row(EvidenceDraft {
                    outcome,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: (outcome == ContractOutcome::Fail).then_some(tick.tick),
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::Predicate {
                        predicate: required,
                    },
                    observed_fact: None,
                    observed_transition: None,
                    observation: if unknown {
                        ObservationState::Unknown
                    } else {
                        ObservationState::KnownFalse
                    },
                    reason: if unknown {
                        EvidenceReason::MissingObservation
                    } else {
                        EvidenceReason::DeadlineExpired
                    },
                    detail: None,
                }));
            }
        }
    }

    if let Some(last_tick) = trace.last() {
        while let Some(obligation) = pending.pop_front() {
            evidence.push(evidence_row(EvidenceDraft {
                outcome: ContractOutcome::Inconclusive,
                trigger_tick: Some(obligation.trigger_tick),
                deadline_tick: Some(obligation.deadline_tick),
                violation_tick: None,
                trigger_trace_index: Some(obligation.trigger_index),
                violation_trace_index: Some(trace.len() - 1),
                expected: ExpectedCondition::Predicate {
                    predicate: required,
                },
                observed_fact: None,
                observed_transition: None,
                observation: ObservationState::Unknown,
                reason: EvidenceReason::TraceEndedBeforeDeadline,
                detail: Some(format!(
                    "trace ended at tick {}; command_id={:?}",
                    last_tick.tick, obligation.command_id
                )),
            }));
        }
    }

    evidence
}

/// Use keyed maps for per-command obligations so one command response cannot
/// satisfy another command and monitoring remains linear in the trace length.
fn evaluate_correlated_response(
    required: Predicate,
    within_ticks: u32,
    trace: &[TraceTick],
) -> Vec<ContractEvidence> {
    let mut evidence = Vec::new();
    let mut pending = BTreeMap::<u64, PendingResponse>::new();
    let mut deadlines = BTreeMap::<u64, Vec<u64>>::new();

    for (index, tick) in trace.iter().enumerate() {
        for fact in &tick.facts {
            if let TraceFact::MovementCommanded { command_id } = fact {
                let deadline_tick = u64::from(tick.tick) + u64::from(within_ticks);
                pending.insert(
                    *command_id,
                    PendingResponse {
                        trigger_tick: tick.tick,
                        deadline_tick,
                        trigger_index: index,
                        command_id: Some(*command_id),
                        unknown_count_at_trigger: 0,
                    },
                );
                deadlines
                    .entry(deadline_tick)
                    .or_default()
                    .push(*command_id);
            }
        }

        for fact in &tick.facts {
            let Some(command_id) = fact.command_id() else {
                continue;
            };
            if !fact.matches(required) {
                continue;
            }
            if let Some(obligation) = pending.remove(&command_id) {
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Pass,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: None,
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::Predicate {
                        predicate: required,
                    },
                    observed_fact: Some(*fact),
                    observed_transition: None,
                    observation: ObservationState::KnownTrue,
                    reason: EvidenceReason::ConditionObserved,
                    detail: Some(format!("command_id={command_id}")),
                }));
            }
        }

        if let Some(command_ids) = deadlines.remove(&u64::from(tick.tick)) {
            for command_id in command_ids {
                let Some(obligation) = pending.remove(&command_id) else {
                    continue;
                };
                let mut row = evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Fail,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: Some(tick.tick),
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::Predicate {
                        predicate: required,
                    },
                    observed_fact: None,
                    observed_transition: None,
                    observation: ObservationState::MonitorDerived,
                    reason: EvidenceReason::CommandTimedOutDerived,
                    detail: Some(format!(
                        "command_id={command_id}; required {} absent at deadline",
                        if required == Predicate::CommandApplied {
                            "command application"
                        } else {
                            "actuator resolution"
                        }
                    )),
                });
                row.monitor_derived_command_outcome = Some(CommandOutcome::Timeout);
                evidence.push(row);
            }
        }
    }

    for (command_id, obligation) in pending {
        evidence.push(evidence_row(EvidenceDraft {
            outcome: ContractOutcome::Inconclusive,
            trigger_tick: Some(obligation.trigger_tick),
            deadline_tick: Some(obligation.deadline_tick),
            violation_tick: None,
            trigger_trace_index: Some(obligation.trigger_index),
            violation_trace_index: Some(trace.len() - 1),
            expected: ExpectedCondition::Predicate {
                predicate: required,
            },
            observed_fact: None,
            observed_transition: None,
            observation: ObservationState::Unknown,
            reason: EvidenceReason::TraceEndedBeforeDeadline,
            detail: Some(format!("command_id={command_id}")),
        }));
    }
    evidence
}
