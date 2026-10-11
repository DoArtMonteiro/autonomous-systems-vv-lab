//! Deterministic finite-trace monitoring for declarative verification contracts.
//!
//! Tick numbers start at 1 and must be contiguous. A bounded response with
//! `within_ticks = N` accepts a response on the trigger tick or through
//! `trigger_tick + N`, inclusive. Thus a bound of zero permits only a same-tick
//! response. Facts on the tick are simultaneous: triggers are registered before
//! responses are matched, so a same-tick response can satisfy its new obligation.
//! For an uncorrelated response contract, one observed response discharges every
//! obligation for that contract that is still open on the tick. Command-scoped
//! responses instead discharge only the obligation with the matching command id.
//!
//! A known positive fact is usable even when sensor telemetry is missing. An
//! absent `localization_unreliable` fact is unknown on a telemetry-missing tick;
//! other supported conditions are reconstructed from controller, actuator, and
//! ground-truth event data, so their absence on a recorded tick is false. A trace
//! that ends with an unresolved obligation is INCONCLUSIVE. A failure is reported
//! only when all observations needed to disprove the obligation are present.
//! Mission completion does not end bounded-response monitoring: stop and command
//! obligations remain observable through the configured trace horizon. Bounded
//! progress applies only while `mission_active` is true; completion before its
//! deadline closes the window as INCONCLUSIVE unless the required increase was
//! already observed.
//! `mission_terminated` marks the final configured trace tick and may coexist
//! with `mission_active`, which describes that tick's state. The distinct
//! `mission_completed` event records logical mission completion; it does not
//! end response monitoring.
//! An unknown response observation does not count as a response. If it occurs
//! during an obligation's window and no known response arrives by the deadline,
//! that obligation is INCONCLUSIVE rather than FAIL.
//!
//! PASS means the property held over the supplied finite observation interval. It
//! does not establish a mathematical guarantee over every possible future run.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

use crate::contracts::{
    CommandOutcome, Contract, ContractSet, Predicate, PropertyType, TraceFact, TraceFactIdentity,
    TransitionDomain, TransitionEdge, TransitionState,
};

mod progress;
mod response;

const MAX_TRACE_TICKS: usize = 10_000;

/// One recorded observation step presented to the finite-trace monitor.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TraceTick {
    /// Logical tick number, starting at 1.
    pub tick: u32,
    /// Whether sensor telemetry was available for this tick.
    pub telemetry_present: bool,
    /// Positive typed facts; their source remains the simulator or event stream.
    pub facts: Vec<TraceFact>,
    /// Transition events in source-event order for this tick.
    pub transitions: Vec<TraceTransition>,
}

/// One typed state-machine transition with its source event sequence number.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TraceTransition {
    pub source_sequence: u64,
    pub domain: TransitionDomain,
    pub from: TransitionState,
    pub to: TransitionState,
}

impl TraceTransition {
    fn edge(self) -> TransitionEdge {
        TransitionEdge {
            from: self.from,
            to: self.to,
        }
    }
}

/// Stable three-way result of finite-trace evaluation.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ContractOutcome {
    Pass,
    Fail,
    Inconclusive,
}

/// One report row for a declared contract.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContractResult {
    /// Contract document version used during evaluation.
    pub schema_version: u32,
    pub contract_id: String,
    pub property_type: PropertyType,
    pub outcome: ContractOutcome,
    /// Earliest known trigger associated with this result, when applicable.
    pub first_trigger_tick: Option<u32>,
    /// Deadline corresponding to the earliest failure, or first unresolved trigger.
    pub deadline_tick: Option<u64>,
    /// Earliest tick with sufficient evidence of a violation.
    pub first_violation_tick: Option<u32>,
    /// Per-obligation or per-violation evidence, in deterministic trace order.
    pub evidence: Vec<ContractEvidence>,
}

/// Typed evidence for one obligation, violation, or unknown observation.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContractEvidence {
    pub outcome: ContractOutcome,
    pub trigger_tick: Option<u32>,
    pub deadline_tick: Option<u64>,
    pub violation_tick: Option<u32>,
    /// Index into the input trace for the qualifying trigger observation.
    pub trigger_trace_index: Option<usize>,
    /// Index into the input trace for the failure or observation that closed it.
    pub violation_trace_index: Option<usize>,
    pub expected: ExpectedCondition,
    pub observed_fact: Option<TraceFact>,
    pub observed_transition: Option<TraceTransition>,
    /// A terminal outcome inferred for this obligation only. It is not an
    /// actuator event and cannot satisfy another contract.
    pub monitor_derived_command_outcome: Option<CommandOutcome>,
    pub observation: ObservationState,
    pub reason: EvidenceReason,
    /// Stable diagnostic context, such as the correlated command id.
    pub detail: Option<String>,
}

/// Typed condition or transition that the evidence is about.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ExpectedCondition {
    Predicate {
        predicate: Predicate,
    },
    Transition {
        edge: TransitionEdge,
    },
    NoTransition {
        domain: TransitionDomain,
    },
    MissionProgressAtLeast {
        baseline_mm: u64,
        minimum_increase_mm: u64,
        required_total_mm: u64,
    },
    TraceIntegrity,
}

/// What the monitor could establish at the cited trace index.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ObservationState {
    KnownTrue,
    KnownFalse,
    Unknown,
    MonitorDerived,
    TransitionObserved,
    Invalid,
}

/// Reason an evidence row was produced.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceReason {
    ConditionObserved,
    PredicateFalse,
    ProhibitedPredicateObserved,
    DeadlineExpired,
    MissingObservation,
    MissingProgressMeasurement,
    TraceEndedBeforeDeadline,
    MissionTerminatedBeforeDeadline,
    ProgressAchieved,
    ProgressNotReached,
    TransitionOrderMismatch,
    TransitionSequenceIncomplete,
    CommandTimedOutDerived,
    InvalidTrace,
    InvalidContractSet,
}

/// Evaluate all contracts against the supplied finite trace.
///
/// The function is deterministic and does not mutate either input. A malformed
/// trace or invalid in-memory contract set yields INCONCLUSIVE results with a
/// typed integrity reason instead of panicking or silently treating missing data
/// as false.
pub fn evaluate(contracts: &ContractSet, trace: &[TraceTick]) -> Vec<ContractResult> {
    if let Err(error) = contracts.validate() {
        return contracts
            .contracts
            .iter()
            .map(|contract| {
                invalid_result(
                    contracts.schema_version,
                    contract,
                    EvidenceReason::InvalidContractSet,
                    error.to_string(),
                )
            })
            .collect();
    }
    if let Err(error) = validate_trace(trace) {
        return contracts
            .contracts
            .iter()
            .map(|contract| {
                invalid_result(
                    contracts.schema_version,
                    contract,
                    EvidenceReason::InvalidTrace,
                    error.clone(),
                )
            })
            .collect();
    }

    contracts
        .contracts
        .iter()
        .map(|contract| {
            let evidence = match contract {
                Contract::Always { predicate, .. } => evaluate_always(*predicate, trace),
                Contract::Never { predicate, .. } => evaluate_never(*predicate, trace),
                Contract::BoundedResponse {
                    trigger,
                    required,
                    within_ticks,
                    correlation,
                    trigger_for_ticks,
                    ..
                } => response::evaluate_bounded_response(
                    *trigger,
                    *required,
                    *within_ticks,
                    *correlation,
                    *trigger_for_ticks,
                    trace,
                ),
                Contract::OrderedTransition {
                    domain, sequence, ..
                } => evaluate_ordered_transition(*domain, sequence, trace),
                Contract::BoundedProgress {
                    within_ticks,
                    minimum_increase_mm,
                    ..
                } => {
                    progress::evaluate_bounded_progress(*within_ticks, *minimum_increase_mm, trace)
                }
            };
            build_result(contracts.schema_version, contract, evidence)
        })
        .collect()
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ObservedCondition {
    True(Option<TraceFact>),
    False,
    Unknown,
}

fn observe(predicate: Predicate, tick: &TraceTick) -> ObservedCondition {
    if let Some(fact) = tick
        .facts
        .iter()
        .copied()
        .find(|fact| fact.matches(predicate))
    {
        return ObservedCondition::True(Some(fact));
    }
    if predicate == Predicate::LocalizationUnreliable && !tick.telemetry_present {
        ObservedCondition::Unknown
    } else {
        ObservedCondition::False
    }
}

fn evaluate_always(predicate: Predicate, trace: &[TraceTick]) -> Vec<ContractEvidence> {
    let mut evidence = Vec::new();
    for (index, tick) in trace.iter().enumerate() {
        match observe(predicate, tick) {
            ObservedCondition::True(_) => {}
            ObservedCondition::False => evidence.push(evidence_row(EvidenceDraft {
                outcome: ContractOutcome::Fail,
                trigger_tick: None,
                deadline_tick: None,
                violation_tick: Some(tick.tick),
                trigger_trace_index: None,
                violation_trace_index: Some(index),
                expected: ExpectedCondition::Predicate { predicate },
                observed_fact: None,
                observed_transition: None,
                observation: ObservationState::KnownFalse,
                reason: EvidenceReason::PredicateFalse,
                detail: None,
            })),
            ObservedCondition::Unknown => evidence.push(evidence_row(EvidenceDraft {
                outcome: ContractOutcome::Inconclusive,
                trigger_tick: None,
                deadline_tick: None,
                violation_tick: None,
                trigger_trace_index: None,
                violation_trace_index: Some(index),
                expected: ExpectedCondition::Predicate { predicate },
                observed_fact: None,
                observed_transition: None,
                observation: ObservationState::Unknown,
                reason: EvidenceReason::MissingObservation,
                detail: None,
            })),
        }
    }
    evidence
}

fn evaluate_never(predicate: Predicate, trace: &[TraceTick]) -> Vec<ContractEvidence> {
    let mut evidence = Vec::new();
    for (index, tick) in trace.iter().enumerate() {
        match observe(predicate, tick) {
            ObservedCondition::True(fact) => evidence.push(evidence_row(EvidenceDraft {
                outcome: ContractOutcome::Fail,
                trigger_tick: None,
                deadline_tick: None,
                violation_tick: Some(tick.tick),
                trigger_trace_index: None,
                violation_trace_index: Some(index),
                expected: ExpectedCondition::Predicate { predicate },
                observed_fact: fact,
                observed_transition: None,
                observation: ObservationState::KnownTrue,
                reason: EvidenceReason::ProhibitedPredicateObserved,
                detail: None,
            })),
            ObservedCondition::False => {}
            ObservedCondition::Unknown => evidence.push(evidence_row(EvidenceDraft {
                outcome: ContractOutcome::Inconclusive,
                trigger_tick: None,
                deadline_tick: None,
                violation_tick: None,
                trigger_trace_index: None,
                violation_trace_index: Some(index),
                expected: ExpectedCondition::Predicate { predicate },
                observed_fact: None,
                observed_transition: None,
                observation: ObservationState::Unknown,
                reason: EvidenceReason::MissingObservation,
                detail: None,
            })),
        }
    }
    evidence
}

fn evaluate_ordered_transition(
    domain: TransitionDomain,
    sequence: &[TransitionEdge],
    trace: &[TraceTick],
) -> Vec<ContractEvidence> {
    let mut evidence = Vec::new();
    let mut next_edge = 0;
    let mut first_edge_tick = None;
    let mut first_edge_index = None;

    'ticks: for (index, tick) in trace.iter().enumerate() {
        for transition in tick
            .transitions
            .iter()
            .copied()
            .filter(|item| item.domain == domain)
        {
            if next_edge >= sequence.len() {
                evidence.push(evidence_row(EvidenceDraft {
            outcome: ContractOutcome::Fail,
            trigger_tick: first_edge_tick,
            deadline_tick: None,
            violation_tick: Some(tick.tick),
            trigger_trace_index: first_edge_index,
            violation_trace_index: Some(index),
            expected: ExpectedCondition::NoTransition { domain },
            observed_fact: None,
            observed_transition: Some(transition),
            observation: ObservationState::TransitionObserved,
            reason: EvidenceReason::TransitionOrderMismatch,
            detail: Some(format!(
                        "additional transition {:?}->{:?} at source sequence {} follows the declared sequence",
                        transition.from, transition.to, transition.source_sequence
                    )),
        }));
                break 'ticks;
            }
            let expected = sequence[next_edge];
            if transition.edge() != expected {
                evidence.push(evidence_row(EvidenceDraft {
                    outcome: ContractOutcome::Fail,
                    trigger_tick: first_edge_tick,
                    deadline_tick: None,
                    violation_tick: Some(tick.tick),
                    trigger_trace_index: first_edge_index,
                    violation_trace_index: Some(index),
                    expected: ExpectedCondition::Transition { edge: expected },
                    observed_fact: None,
                    observed_transition: Some(transition),
                    observation: ObservationState::TransitionObserved,
                    reason: EvidenceReason::TransitionOrderMismatch,
                    detail: Some(format!(
                        "observed {:?}->{:?} at source sequence {}",
                        transition.from, transition.to, transition.source_sequence
                    )),
                }));
                break 'ticks;
            }
            first_edge_tick.get_or_insert(tick.tick);
            first_edge_index.get_or_insert(index);
            next_edge += 1;
            if next_edge == sequence.len() {
                // The declared sequence is exact. An additional transition in
                // this domain is also outside the declared path.
                continue;
            }
        }
    }

    if evidence.is_empty() && next_edge < sequence.len() {
        let last = trace.len() - 1;
        evidence.push(evidence_row(EvidenceDraft {
            outcome: ContractOutcome::Inconclusive,
            trigger_tick: first_edge_tick,
            deadline_tick: None,
            violation_tick: None,
            trigger_trace_index: first_edge_index,
            violation_trace_index: Some(last),
            expected: ExpectedCondition::Transition {
                edge: sequence[next_edge],
            },
            observed_fact: None,
            observed_transition: None,
            observation: ObservationState::Unknown,
            reason: EvidenceReason::TransitionSequenceIncomplete,
            detail: Some(format!(
                "observed {next_edge} of {} declared edges",
                sequence.len()
            )),
        }));
    }
    evidence
}

struct EvidenceDraft {
    outcome: ContractOutcome,
    trigger_tick: Option<u32>,
    deadline_tick: Option<u64>,
    violation_tick: Option<u32>,
    trigger_trace_index: Option<usize>,
    violation_trace_index: Option<usize>,
    expected: ExpectedCondition,
    observed_fact: Option<TraceFact>,
    observed_transition: Option<TraceTransition>,
    observation: ObservationState,
    reason: EvidenceReason,
    detail: Option<String>,
}

fn evidence_row(draft: EvidenceDraft) -> ContractEvidence {
    ContractEvidence {
        outcome: draft.outcome,
        trigger_tick: draft.trigger_tick,
        deadline_tick: draft.deadline_tick,
        violation_tick: draft.violation_tick,
        trigger_trace_index: draft.trigger_trace_index,
        violation_trace_index: draft.violation_trace_index,
        expected: draft.expected,
        observed_fact: draft.observed_fact,
        observed_transition: draft.observed_transition,
        monitor_derived_command_outcome: None,
        observation: draft.observation,
        reason: draft.reason,
        detail: draft.detail,
    }
}

fn build_result(
    schema_version: u32,
    contract: &Contract,
    evidence: Vec<ContractEvidence>,
) -> ContractResult {
    let outcome = if evidence
        .iter()
        .any(|row| row.outcome == ContractOutcome::Fail)
    {
        ContractOutcome::Fail
    } else if evidence
        .iter()
        .any(|row| row.outcome == ContractOutcome::Inconclusive)
    {
        ContractOutcome::Inconclusive
    } else {
        ContractOutcome::Pass
    };
    let first_trigger_tick = evidence.iter().filter_map(|row| row.trigger_tick).min();
    let first_violation = evidence
        .iter()
        .filter(|row| row.outcome == ContractOutcome::Fail)
        .min_by_key(|row| row.violation_tick.unwrap_or(u32::MAX));
    let first_violation_tick = first_violation.and_then(|row| row.violation_tick);
    let deadline_tick = first_violation
        .and_then(|row| row.deadline_tick)
        .or_else(|| {
            evidence
                .iter()
                .find(|row| row.trigger_tick.is_some())
                .and_then(|row| row.deadline_tick)
        });
    ContractResult {
        schema_version,
        contract_id: contract.id().to_owned(),
        property_type: contract.property_type(),
        outcome,
        first_trigger_tick,
        deadline_tick,
        first_violation_tick,
        evidence,
    }
}

fn invalid_result(
    schema_version: u32,
    contract: &Contract,
    reason: EvidenceReason,
    detail: String,
) -> ContractResult {
    build_result(
        schema_version,
        contract,
        vec![evidence_row(EvidenceDraft {
            outcome: ContractOutcome::Inconclusive,
            trigger_tick: None,
            deadline_tick: None,
            violation_tick: None,
            trigger_trace_index: None,
            violation_trace_index: None,
            expected: ExpectedCondition::TraceIntegrity,
            observed_fact: None,
            observed_transition: None,
            observation: ObservationState::Invalid,
            reason,
            detail: Some(detail),
        })],
    )
}

fn validate_trace(trace: &[TraceTick]) -> Result<(), String> {
    if trace.is_empty() {
        return Err("trace is empty".into());
    }
    if trace.len() > MAX_TRACE_TICKS {
        return Err(format!("trace exceeds {MAX_TRACE_TICKS} ticks"));
    }
    let mut mission_completed = false;
    for (index, tick) in trace.iter().enumerate() {
        let expected = u32::try_from(index + 1).map_err(|_| "trace tick index overflows")?;
        if tick.tick != expected {
            return Err(format!(
                "ticks must start at 1 and be contiguous: index {index} has tick {}",
                tick.tick
            ));
        }
        validate_tick_facts(tick)?;
        if tick.facts.contains(&TraceFact::MissionTerminated) && index + 1 != trace.len() {
            return Err(format!(
                "mission_terminated may appear only on the final trace tick, found at tick {}",
                tick.tick
            ));
        }
        if tick.facts.contains(&TraceFact::MissionCompleted) {
            if mission_completed {
                return Err("mission_completed may appear only once in a trace".into());
            }
            mission_completed = true;
        } else if mission_completed && tick.facts.contains(&TraceFact::MissionActive) {
            return Err(format!(
                "mission_active observed after mission_completed at tick {}",
                tick.tick
            ));
        }
    }
    validate_transition_order(trace)?;
    validate_command_facts(trace)?;
    validate_progress_monotonicity(trace)?;
    Ok(())
}

fn validate_tick_facts(tick: &TraceTick) -> Result<(), String> {
    let mut singletons = BTreeSet::<TraceFactIdentity>::new();
    let mut command_facts = BTreeSet::new();
    for fact in &tick.facts {
        if let Some(command_id) = fact.command_id() {
            let identity = fact.identity();
            if !command_facts.insert((identity, command_id)) {
                return Err(format!(
                    "duplicate {:?} fact for command_id {command_id} at tick {}",
                    identity, tick.tick
                ));
            }
        } else if !singletons.insert(fact.identity()) {
            return Err(format!(
                "duplicate {:?} fact at tick {}",
                fact.identity(),
                tick.tick
            ));
        }
    }
    Ok(())
}

fn validate_transition_order(trace: &[TraceTick]) -> Result<(), String> {
    let mut previous_sequence = 0_u64;
    for tick in trace {
        for transition in &tick.transitions {
            if transition.source_sequence == 0 || transition.source_sequence <= previous_sequence {
                return Err(format!(
                    "transition source sequences must increase: {} at tick {}",
                    transition.source_sequence, tick.tick
                ));
            }
            if transition.from == transition.to
                || !transition_state_matches(transition.domain, transition.from)
                || !transition_state_matches(transition.domain, transition.to)
            {
                return Err(format!(
                    "invalid {:?} transition {:?}->{:?} at tick {}",
                    transition.domain, transition.from, transition.to, tick.tick
                ));
            }
            previous_sequence = transition.source_sequence;
        }
    }
    Ok(())
}

fn transition_state_matches(domain: TransitionDomain, state: TransitionState) -> bool {
    match domain {
        TransitionDomain::Mission => matches!(
            state,
            TransitionState::Pending | TransitionState::Running | TransitionState::Completed
        ),
        TransitionDomain::Safety => {
            matches!(state, TransitionState::Nominal | TransitionState::Fallback)
        }
    }
}

fn validate_command_facts(trace: &[TraceTick]) -> Result<(), String> {
    let mut commanded = BTreeMap::<u64, u32>::new();
    let mut resolutions = BTreeSet::new();
    let mut applications = BTreeSet::new();
    for tick in trace {
        for fact in &tick.facts {
            match fact {
                TraceFact::MovementCommanded { command_id } => {
                    if *command_id == 0 || commanded.insert(*command_id, tick.tick).is_some() {
                        return Err(format!(
                            "command_id {command_id} is zero or reused at tick {}",
                            tick.tick
                        ));
                    }
                }
                TraceFact::CommandApplied { command_id } => {
                    if !applications.insert(*command_id) {
                        return Err(format!("command_id {command_id} applied more than once"));
                    }
                }
                TraceFact::CommandResolved { command_id, .. }
                    if !resolutions.insert(*command_id) =>
                {
                    return Err(format!("command_id {command_id} resolved more than once"));
                }
                _ => {}
            }
        }
    }
    for tick in trace {
        for fact in &tick.facts {
            match fact {
                TraceFact::CommandApplied { command_id }
                | TraceFact::CommandResolved { command_id, .. } => {
                    let Some(command_tick) = commanded.get(command_id) else {
                        return Err(format!(
                            "command outcome references unknown command_id {command_id}"
                        ));
                    };
                    if *command_tick > tick.tick {
                        return Err(format!(
                            "command_id {command_id} resolves before it was issued"
                        ));
                    }
                }
                _ => {}
            }
        }
    }
    Ok(())
}

fn validate_progress_monotonicity(trace: &[TraceTick]) -> Result<(), String> {
    let mut previous = None;
    for tick in trace {
        let progress = tick.facts.iter().find_map(|fact| match fact {
            TraceFact::MissionProgress { progress_mm } => Some(*progress_mm),
            _ => None,
        });
        if let Some(current) = progress {
            if previous.is_some_and(|last| current < last) {
                return Err(format!(
                    "cumulative mission progress decreased at tick {}",
                    tick.tick
                ));
            }
            previous = Some(current);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests;
