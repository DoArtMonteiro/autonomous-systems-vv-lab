use std::collections::VecDeque;

use super::{
    ContractEvidence, ContractOutcome, EvidenceDraft, EvidenceReason, ExpectedCondition,
    ObservationState, ObservedCondition, TraceTick, evidence_row, observe,
};
use crate::contracts::{Predicate, TraceFact};

#[derive(Clone, Debug)]
struct PendingProgress {
    trigger_tick: u32,
    deadline_tick: u64,
    trigger_index: usize,
    baseline_mm: u64,
    target_mm: u64,
    missing_measurement_count_at_trigger: u64,
}

pub(super) fn evaluate_bounded_progress(
    within_ticks: u32,
    minimum_increase_mm: u64,
    trace: &[TraceTick],
) -> Vec<ContractEvidence> {
    let mut evidence = Vec::new();
    let mut pending = VecDeque::<PendingProgress>::new();
    let mut missing_measurement_count = 0_u64;

    for (index, tick) in trace.iter().enumerate() {
        let progress = tick.facts.iter().find_map(|fact| match fact {
            TraceFact::MissionProgress { progress_mm } => Some(*progress_mm),
            _ => None,
        });
        let active = observe(Predicate::MissionActive, tick);

        if progress.is_none() {
            missing_measurement_count += 1;
        }

        // Progress and each obligation's target are monotonic, so resolving the
        // queue head first keeps overlapping windows linear in trace length.
        if let Some(value) = progress {
            while pending.front().is_some_and(|obligation| {
                value.saturating_sub(obligation.baseline_mm) >= minimum_increase_mm
            }) {
                let obligation = pending.pop_front().expect("front was checked");
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Pass,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: None,
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::MissionProgressAtLeast {
                        baseline_mm: obligation.baseline_mm,
                        minimum_increase_mm,
                        required_total_mm: obligation.target_mm,
                    },
                    observed_fact: Some(TraceFact::MissionProgress { progress_mm: value }),
                    observed_transition: None,
                    observation: ObservationState::KnownTrue,
                    reason: EvidenceReason::ProgressAchieved,
                    detail: None,
                }));
            }
        }

        // Progress obligations apply only while the mission remains active. If
        // it completes first, unfinished windows are inconclusive rather than
        // failures caused by the completed mission no longer advancing.
        if !matches!(active, ObservedCondition::True(_)) {
            while let Some(obligation) = pending.pop_front() {
                let (observation, reason) = if active == ObservedCondition::Unknown {
                    (
                        ObservationState::Unknown,
                        EvidenceReason::MissingObservation,
                    )
                } else {
                    (
                        ObservationState::Unknown,
                        EvidenceReason::MissionTerminatedBeforeDeadline,
                    )
                };
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Inconclusive,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: None,
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::MissionProgressAtLeast {
                        baseline_mm: obligation.baseline_mm,
                        minimum_increase_mm,
                        required_total_mm: obligation.target_mm,
                    },
                    observed_fact: progress
                        .map(|progress_mm| TraceFact::MissionProgress { progress_mm }),
                    observed_transition: None,
                    observation,
                    reason,
                    detail: Some(format!("mission is not known active at tick {}", tick.tick)),
                }));
            }
        }

        while pending
            .front()
            .is_some_and(|obligation| u64::from(tick.tick) == obligation.deadline_tick)
        {
            let obligation = pending.pop_front().expect("front was checked");
            let unknown =
                missing_measurement_count > obligation.missing_measurement_count_at_trigger;
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
                expected: ExpectedCondition::MissionProgressAtLeast {
                    baseline_mm: obligation.baseline_mm,
                    minimum_increase_mm,
                    required_total_mm: obligation.target_mm,
                },
                observed_fact: progress
                    .map(|progress_mm| TraceFact::MissionProgress { progress_mm }),
                observed_transition: None,
                observation: if unknown {
                    ObservationState::Unknown
                } else {
                    ObservationState::KnownFalse
                },
                reason: if unknown {
                    EvidenceReason::MissingProgressMeasurement
                } else {
                    EvidenceReason::ProgressNotReached
                },
                detail: None,
            }));
        }

        if tick.facts.contains(&TraceFact::MissionCompleted)
            || tick.facts.contains(&TraceFact::MissionTerminated)
        {
            while let Some(obligation) = pending.pop_front() {
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Inconclusive,
                    trigger_tick: Some(obligation.trigger_tick),
                    deadline_tick: Some(obligation.deadline_tick),
                    violation_tick: None,
                    trigger_trace_index: Some(obligation.trigger_index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::MissionProgressAtLeast {
                        baseline_mm: obligation.baseline_mm,
                        minimum_increase_mm,
                        required_total_mm: obligation.target_mm,
                    },
                    observed_fact: progress
                        .map(|progress_mm| TraceFact::MissionProgress { progress_mm }),
                    observed_transition: None,
                    observation: ObservationState::Unknown,
                    reason: EvidenceReason::MissionTerminatedBeforeDeadline,
                    detail: None,
                }));
            }
        }

        if matches!(active, ObservedCondition::True(_)) {
            match progress {
                Some(baseline_mm) => {
                    let target_mm = baseline_mm.saturating_add(minimum_increase_mm);
                    let deadline_tick = u64::from(tick.tick) + u64::from(within_ticks);
                    if within_ticks == 0 {
                        evidence.push(evidence_row(EvidenceDraft {
                            outcome: ContractOutcome::Fail,
                            trigger_tick: Some(tick.tick),
                            deadline_tick: Some(deadline_tick),
                            violation_tick: Some(tick.tick),
                            trigger_trace_index: Some(index),
                            violation_trace_index: Some(index),
                            expected: ExpectedCondition::MissionProgressAtLeast {
                                baseline_mm,
                                minimum_increase_mm,
                                required_total_mm: target_mm,
                            },
                            observed_fact: Some(TraceFact::MissionProgress {
                                progress_mm: baseline_mm,
                            }),
                            observed_transition: None,
                            observation: ObservationState::KnownFalse,
                            reason: EvidenceReason::ProgressNotReached,
                            detail: Some(
                                "a zero-tick window cannot increase from its trigger baseline"
                                    .into(),
                            ),
                        }));
                    } else {
                        pending.push_back(PendingProgress {
                            trigger_tick: tick.tick,
                            deadline_tick,
                            trigger_index: index,
                            baseline_mm,
                            target_mm,
                            missing_measurement_count_at_trigger: missing_measurement_count,
                        });
                    }
                }
                None => evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Inconclusive,
                    trigger_tick: Some(tick.tick),
                    deadline_tick: Some(u64::from(tick.tick) + u64::from(within_ticks)),
                    violation_tick: None,
                    trigger_trace_index: Some(index),
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::MissionProgressAtLeast {
                        baseline_mm: 0,
                        minimum_increase_mm,
                        required_total_mm: minimum_increase_mm,
                    },
                    observed_fact: None,
                    observed_transition: None,
                    observation: ObservationState::Unknown,
                    reason: EvidenceReason::MissingProgressMeasurement,
                    detail: Some("active mission has no progress measurement on this tick".into()),
                })),
            }
        } else if active == ObservedCondition::Unknown {
            evidence.push(evidence_row(EvidenceDraft {
                outcome: ContractOutcome::Inconclusive,
                trigger_tick: None,
                deadline_tick: None,
                violation_tick: None,
                trigger_trace_index: None,
                violation_trace_index: Some(index),
                expected: ExpectedCondition::Predicate {
                    predicate: Predicate::MissionActive,
                },
                observed_fact: None,
                observed_transition: None,
                observation: ObservationState::Unknown,
                reason: EvidenceReason::MissingObservation,
                detail: None,
            }));
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
                expected: ExpectedCondition::MissionProgressAtLeast {
                    baseline_mm: obligation.baseline_mm,
                    minimum_increase_mm,
                    required_total_mm: obligation.target_mm,
                },
                observed_fact: None,
                observed_transition: None,
                observation: ObservationState::Unknown,
                reason: EvidenceReason::TraceEndedBeforeDeadline,
                detail: Some(format!("trace ended at tick {}", last_tick.tick)),
            }));
        }
    }
    evidence
}
