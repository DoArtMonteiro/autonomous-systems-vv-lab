use std::collections::{BTreeMap, BTreeSet};

use super::{
    CommandAtTick, ContractFailureEvidence, CounterexampleTick, LinkedActuatorFaultEvent,
};
use crate::actuator::{ActuationOutcome, ActuatorBehavior};
use crate::contracts::{CommandOutcome, TraceFact, TransitionDomain, TransitionState};
use crate::error::LabError;
use crate::model::{
    Action, EventPayload, EventRecord, EventsArtifact, MissionState, ObservedTelemetry, Point,
    SafetyState, Scenario,
};
use crate::temporal::{
    ContractOutcome, ContractResult, EvidenceReason, ExpectedCondition, ObservationState, TraceTick,
    TraceTransition,
};

pub(super) fn build_temporal_trace(
    artifact: &EventsArtifact,
    actuation: &[ActuationOutcome],
) -> Result<Vec<TraceTick>, LabError> {
    let scenario = &artifact.scenario;
    let mut ticks = BTreeMap::new();
    let mut restricted_zone = BTreeMap::new();
    let mut transitions = BTreeMap::<u32, Vec<TraceTransition>>::new();
    for record in &artifact.events {
        match &record.event {
            EventPayload::TickResult {
                truth_from,
                truth_position,
                observed,
                mission_state,
                safety_state,
                action,
                ..
            } => {
                if ticks
                    .insert(
                        record.tick,
                        SourceTick {
                            event_sequence: record.sequence,
                            truth_from: *truth_from,
                            truth_position: *truth_position,
                            observed: observed.clone(),
                            mission_state: *mission_state,
                            safety_state: *safety_state,
                            action: *action,
                        },
                    )
                    .is_some()
                {
                    return Err(LabError(format!(
                        "duplicate tick result at tick {}",
                        record.tick
                    )));
                }
            }
            EventPayload::InvariantCheck { name, passed, .. } if name == "restricted_zone" => {
                if restricted_zone.insert(record.tick, *passed).is_some() {
                    return Err(LabError(format!(
                        "duplicate restricted_zone invariant at tick {}",
                        record.tick
                    )));
                }
            }
            EventPayload::Transition {
                subsystem,
                from,
                to,
                ..
            } => {
                let Some(domain) = transition_domain(subsystem) else {
                    continue;
                };
                transitions
                    .entry(record.tick)
                    .or_default()
                    .push(TraceTransition {
                        source_sequence: record.sequence,
                        domain,
                        from: transition_state(from)?,
                        to: transition_state(to)?,
                    });
            }
            _ => {}
        }
    }

    if ticks.len() != scenario.steps as usize || actuation.len() != scenario.steps as usize {
        return Err(LabError(
            "M3 temporal trace requires one tick result and actuator outcome per configured tick"
                .into(),
        ));
    }
    let mut progress = MissionProgressTracker::new();
    progress.sample(scenario.vehicle.start, scenario);
    let mut result = Vec::with_capacity(scenario.steps as usize);
    let mut previous_sequence = 0_u64;
    let mut outcomes_by_tick = BTreeMap::new();
    for outcome in actuation {
        if outcomes_by_tick.insert(outcome.tick, outcome).is_some() {
            return Err(LabError(format!(
                "duplicate actuator outcome at tick {}",
                outcome.tick
            )));
        }
    }

    for tick in 1..=scenario.steps {
        let source = ticks
            .get(&tick)
            .ok_or_else(|| LabError(format!("missing tick result at tick {tick}")))?;
        let outcome = outcomes_by_tick
            .get(&tick)
            .ok_or_else(|| LabError(format!("missing actuator outcome at tick {tick}")))?;
        if source.event_sequence <= previous_sequence {
            return Err(LabError("tick result source order is invalid".into()));
        }
        previous_sequence = source.event_sequence;
        progress.sample(source.truth_position, scenario);

        let mut facts = Vec::new();
        // The event stream records an absent GPS observation as a known
        // localization failure. Missing monitor telemetry without this fact
        // remains unknown inside the temporal monitor.
        let localization_unreliable = source.observed.as_ref().is_none_or(|observation| {
            !observation.fresh
                || observation.confidence_permille < scenario.safety.confidence_threshold_permille
        });
        if localization_unreliable {
            facts.push(TraceFact::LocalizationUnreliable);
        }
        if source.safety_state == SafetyState::Fallback {
            facts.push(TraceFact::SafetyFallback);
        }
        if is_stop(source.action) {
            facts.push(TraceFact::StopCommanded);
        }
        let stationary = source.truth_from == source.truth_position;
        if stationary {
            facts.push(TraceFact::VehicleStationary);
        }
        if *restricted_zone
            .get(&tick)
            .ok_or_else(|| LabError(format!("missing restricted_zone result at tick {tick}")))?
        {
            facts.push(TraceFact::RestrictedZoneClear);
        }
        if source.mission_state == MissionState::Running {
            facts.push(TraceFact::MissionActive);
        }
        let mission_completed = transitions.get(&tick).is_some_and(|tick_transitions| {
            tick_transitions.iter().any(|transition| {
                transition.domain == TransitionDomain::Mission
                    && transition.to == TransitionState::Completed
            })
        });
        if mission_completed {
            facts.push(TraceFact::MissionCompleted);
        }
        if tick == scenario.steps {
            facts.push(TraceFact::MissionTerminated);
        }
        facts.push(TraceFact::MissionProgress {
            progress_mm: progress.total_mm,
        });

        let requested_movement = is_movement(source.action);
        if requested_movement {
            facts.push(TraceFact::MovementCommanded {
                command_id: source.event_sequence,
            });
        }
        let actual_movement = is_movement(outcome.realized_action);
        if source.safety_state == SafetyState::Fallback
            && source.truth_from != source.truth_position
        {
            facts.push(TraceFact::MovementWhileFallback);
        }
        if requested_movement {
            let delayed_this_command = outcome.fault_events.iter().any(|event| {
                event.source_command_tick == tick
                    && event.kind == crate::actuator::ActuatorEventKind::CommandDelayed
            });
            let failure_was_observed = outcome.fault_events.iter().any(|event| {
                event.source_command_tick == tick
                    && (event.kind == crate::actuator::ActuatorEventKind::CommandLost
                        || (event.kind
                            == crate::actuator::ActuatorEventKind::CurrentCommandIgnoredByDelayedCommand
                            && !delayed_this_command))
            });
            if failure_was_observed {
                facts.push(TraceFact::CommandResolved {
                    command_id: source.event_sequence,
                    outcome: CommandOutcome::ExplicitFailure,
                });
            }
        }
        if actual_movement && outcome.behavior != ActuatorBehavior::ContinuedMovement {
            let source_command = ticks.get(&outcome.source_command_tick).ok_or_else(|| {
                LabError(format!(
                    "actuator outcome at tick {tick} references unknown source command tick {}",
                    outcome.source_command_tick
                ))
            })?;
            if is_movement(source_command.action) {
                facts.push(TraceFact::CommandApplied {
                    command_id: source_command.event_sequence,
                });
                facts.push(TraceFact::CommandResolved {
                    command_id: source_command.event_sequence,
                    outcome: CommandOutcome::Applied,
                });
            }
        }
        let tick_transitions = transitions.remove(&tick).unwrap_or_default();
        result.push(TraceTick {
            tick,
            telemetry_present: source.observed.is_some(),
            facts,
            transitions: tick_transitions,
        });
    }
    if !restricted_zone.is_empty() && restricted_zone.keys().any(|tick| *tick > scenario.steps) {
        return Err(LabError(
            "restricted_zone results exist outside the configured trace".into(),
        ));
    }
    Ok(result)
}

pub(super) fn build_failure_evidence(
    artifact: &EventsArtifact,
    actuation: &[ActuationOutcome],
    trace: &[TraceTick],
    results: &[ContractResult],
    reproduction_command: &str,
) -> Result<Vec<ContractFailureEvidence>, LabError> {
    let tick_sequences = tick_result_sequences(&artifact.events)?;
    let outcomes_by_tick: BTreeMap<_, _> = actuation
        .iter()
        .map(|outcome| (outcome.tick, outcome))
        .collect();
    let mut failures = Vec::new();
    for result in results
        .iter()
        .filter(|result| result.outcome == ContractOutcome::Fail)
    {
        let evidence = result
            .evidence
            .iter()
            .find(|evidence| evidence.outcome == ContractOutcome::Fail)
            .ok_or_else(|| {
                LabError(format!(
                    "failed contract {} has no failure evidence",
                    result.contract_id
                ))
            })?;
        let violation_tick = evidence
            .violation_tick
            .or(result.first_violation_tick)
            .ok_or_else(|| {
                LabError(format!(
                    "failed contract {} has no violation tick",
                    result.contract_id
                ))
            })?;
        let trigger_tick = evidence.trigger_tick.or(result.first_trigger_tick);
        let relevant_ticks = counterexample_tick_set(
            trigger_tick,
            evidence.deadline_tick,
            violation_tick,
            artifact.scenario.steps,
        );
        let source_commands = trigger_tick.into_iter().collect::<BTreeSet<_>>();
        let linked_events = link_fault_events(
            actuation,
            &tick_sequences,
            &relevant_ticks,
            &source_commands,
        )?;
        let counterexample_ticks = build_counterexample_ticks(
            artifact,
            actuation,
            &tick_sequences,
            &relevant_ticks,
            &linked_events,
        )?;
        let mut source_event_sequences = BTreeSet::new();
        for tick in &relevant_ticks {
            source_event_sequences.extend(
                artifact
                    .events
                    .iter()
                    .filter(|event| event.tick == *tick)
                    .map(|event| event.sequence),
            );
        }
        for event in &linked_events {
            source_event_sequences.insert(event.observed_event_sequence);
            source_event_sequences.insert(event.source_command_event_sequence);
            source_event_sequences.extend(event.execution_event_sequence);
        }
        let trigger_command = trigger_tick
            .map(|tick| command_at_tick(artifact, &tick_sequences, tick))
            .transpose()?;
        let violation_command = Some(command_at_tick(artifact, &tick_sequences, violation_tick)?);
        let trigger_source = trigger_tick.and_then(|tick| outcomes_by_tick.get(&tick).copied());
        let violation_source = outcomes_by_tick.get(&violation_tick).copied();
        let violation_event = artifact
            .events
            .iter()
            .find(|event| {
                event.tick == violation_tick
                    && matches!(event.event, EventPayload::TickResult { .. })
            })
            .ok_or_else(|| {
                LabError(format!(
                    "missing tick result at violation tick {violation_tick}"
                ))
            })?;
        let (truth_from, truth_position) = match &violation_event.event {
            EventPayload::TickResult {
                truth_from,
                truth_position,
                ..
            } => (*truth_from, *truth_position),
            _ => unreachable!("filtered to tick result"),
        };
        let actual_trace_tick = trace
            .get(violation_tick.saturating_sub(1) as usize)
            .ok_or_else(|| {
                LabError(format!(
                    "missing temporal observation at violation tick {violation_tick}"
                ))
            })?;
        let actual_source = artifact
            .expected_report
            .telemetry
            .iter()
            .find(|telemetry| telemetry.tick == violation_tick)
            .ok_or_else(|| {
                LabError(format!(
                    "missing telemetry at violation tick {violation_tick}"
                ))
            })?;
        let actual_outcome = outcomes_by_tick.get(&violation_tick).copied();
        let actual_condition = format!(
            "trace_facts={:?}; mission_state={}; safety_state={}; truth_from=({},{}); truth_position=({},{}); controller_action={:?}; realized_action={:?}; actuator_behavior={:?}",
            actual_trace_tick.facts,
            actual_source.mission_state,
            actual_source.safety_state,
            truth_from.x_mm,
            truth_from.y_mm,
            truth_position.x_mm,
            truth_position.y_mm,
            actual_source.action,
            actual_outcome.map(|outcome| outcome.realized_action),
            actual_outcome.map(|outcome| outcome.behavior),
        );
        failures.push(ContractFailureEvidence {
            contract_id: result.contract_id.clone(),
            contract_version: result.schema_version,
            property_type: result.property_type,
            first_trigger_tick: trigger_tick,
            applicable_deadline_tick: evidence.deadline_tick.or(result.deadline_tick),
            first_violation_tick: violation_tick,
            expected: evidence.expected.clone(),
            expected_condition: format!("{:?}", evidence.expected),
            actual_condition,
            actual_fact: evidence.observed_fact,
            actual_transition: evidence.observed_transition,
            observation: evidence.observation,
            evidence_reason: evidence.reason,
            monitor_derived_command_outcome: evidence.monitor_derived_command_outcome,
            detail: evidence.detail.clone(),
            trigger_command,
            violation_command,
            actuator_behavior_at_trigger: trigger_source.map(|outcome| outcome.behavior),
            actuator_behavior_at_violation: violation_source.map(|outcome| outcome.behavior),
            truth_from: Some(truth_from),
            truth_position: Some(truth_position),
            fault_events: linked_events,
            source_event_sequences: source_event_sequences.into_iter().collect(),
            counterexample_ticks,
            source_artifact_sha256: artifact.artifact_sha256.clone(),
            reproduction_command: reproduction_command.to_owned(),
        });
    }
    Ok(failures)
}

fn tick_result_sequences(events: &[EventRecord]) -> Result<BTreeMap<u32, u64>, LabError> {
    let mut sequences = BTreeMap::new();
    for event in events {
        if matches!(event.event, EventPayload::TickResult { .. })
            && sequences.insert(event.tick, event.sequence).is_some()
        {
            return Err(LabError(format!(
                "duplicate tick result event at tick {}",
                event.tick
            )));
        }
    }
    Ok(sequences)
}

fn command_at_tick(
    artifact: &EventsArtifact,
    tick_sequences: &BTreeMap<u32, u64>,
    tick: u32,
) -> Result<CommandAtTick, LabError> {
    let telemetry = artifact
        .expected_report
        .telemetry
        .iter()
        .find(|telemetry| telemetry.tick == tick)
        .ok_or_else(|| LabError(format!("missing telemetry at tick {tick}")))?;
    let event_sequence = tick_sequences
        .get(&tick)
        .copied()
        .ok_or_else(|| LabError(format!("missing tick result event at tick {tick}")))?;
    Ok(CommandAtTick {
        tick,
        event_sequence,
        action: telemetry.action,
    })
}

fn counterexample_tick_set(
    trigger_tick: Option<u32>,
    deadline_tick: Option<u64>,
    violation_tick: u32,
    total_ticks: u32,
) -> BTreeSet<u32> {
    let mut ticks = BTreeSet::new();
    let first = trigger_tick
        .unwrap_or(violation_tick)
        .saturating_sub(1)
        .max(1);
    let last_obligation_tick = deadline_tick
        .and_then(|tick| u32::try_from(tick).ok())
        .unwrap_or(violation_tick)
        .max(violation_tick);
    let last = last_obligation_tick.saturating_add(1).min(total_ticks);
    for tick in first..=last {
        ticks.insert(tick);
    }
    ticks
}

fn link_fault_events(
    actuation: &[ActuationOutcome],
    tick_sequences: &BTreeMap<u32, u64>,
    relevant_ticks: &BTreeSet<u32>,
    source_command_ticks: &BTreeSet<u32>,
) -> Result<Vec<LinkedActuatorFaultEvent>, LabError> {
    let mut result = Vec::new();
    for outcome in actuation {
        for event in &outcome.fault_events {
            if !relevant_ticks.contains(&event.tick)
                && !source_command_ticks.contains(&event.source_command_tick)
            {
                continue;
            }
            let observed_event_sequence = sequence_for_tick(tick_sequences, event.tick)?;
            let source_command_event_sequence =
                sequence_for_tick(tick_sequences, event.source_command_tick)?;
            let execution_event_sequence = event
                .execution_tick
                .map(|tick| sequence_for_tick(tick_sequences, tick))
                .transpose()?;
            result.push(LinkedActuatorFaultEvent {
                event: event.clone(),
                observed_event_sequence,
                source_command_event_sequence,
                execution_event_sequence,
            });
        }
    }
    Ok(result)
}

fn sequence_for_tick(tick_sequences: &BTreeMap<u32, u64>, tick: u32) -> Result<u64, LabError> {
    tick_sequences
        .get(&tick)
        .copied()
        .ok_or_else(|| LabError(format!("event references missing tick result {tick}")))
}

fn build_counterexample_ticks(
    artifact: &EventsArtifact,
    actuation: &[ActuationOutcome],
    tick_sequences: &BTreeMap<u32, u64>,
    selected_ticks: &BTreeSet<u32>,
    linked_events: &[LinkedActuatorFaultEvent],
) -> Result<Vec<CounterexampleTick>, LabError> {
    let outcomes_by_tick: BTreeMap<_, _> = actuation
        .iter()
        .map(|outcome| (outcome.tick, outcome))
        .collect();
    let mut result = Vec::with_capacity(selected_ticks.len());
    for tick in selected_ticks {
        let event = artifact
            .events
            .iter()
            .find(|event| {
                event.tick == *tick && matches!(event.event, EventPayload::TickResult { .. })
            })
            .ok_or_else(|| LabError(format!("missing tick result at tick {tick}")))?;
        let (truth_from, truth_position) = match event.event {
            EventPayload::TickResult {
                truth_from,
                truth_position,
                ..
            } => (truth_from, truth_position),
            _ => unreachable!("filtered to tick result"),
        };
        let telemetry = artifact
            .expected_report
            .telemetry
            .iter()
            .find(|telemetry| telemetry.tick == *tick)
            .ok_or_else(|| LabError(format!("missing telemetry at tick {tick}")))?;
        let outcome = outcomes_by_tick
            .get(tick)
            .copied()
            .ok_or_else(|| LabError(format!("missing actuator outcome at tick {tick}")))?;
        let fault_events = linked_events
            .iter()
            .filter(|linked| linked.event.tick == *tick)
            .cloned()
            .collect();
        let source_event_sequences = artifact
            .events
            .iter()
            .filter(|source| source.tick == *tick)
            .map(|source| source.sequence)
            .chain(std::iter::once(sequence_for_tick(tick_sequences, *tick)?))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        result.push(CounterexampleTick {
            tick: *tick,
            truth_from,
            truth_position,
            observed: telemetry.observed.clone(),
            mission_state: telemetry.mission_state,
            safety_state: telemetry.safety_state,
            requested_action: telemetry.action,
            realized_action: outcome.realized_action,
            actuator_behavior: outcome.behavior,
            fault_events,
            source_event_sequences,
        });
    }
    Ok(result)
}

fn is_stop(action: Action) -> bool {
    action.heading.is_none() && action.distance_mm == 0
}

fn is_movement(action: Action) -> bool {
    action.heading.is_some() && action.distance_mm > 0
}

fn transition_domain(subsystem: &str) -> Option<TransitionDomain> {
    match subsystem {
        "mission" => Some(TransitionDomain::Mission),
        "safety" => Some(TransitionDomain::Safety),
        _ => None,
    }
}

fn transition_state(state: &str) -> Result<TransitionState, LabError> {
    match state {
        "pending" => Ok(TransitionState::Pending),
        "running" => Ok(TransitionState::Running),
        "completed" => Ok(TransitionState::Completed),
        "nominal" => Ok(TransitionState::Nominal),
        "fallback" => Ok(TransitionState::Fallback),
        _ => Err(LabError(format!("unknown transition state '{state}'"))),
    }
}

#[derive(Clone)]
struct SourceTick {
    event_sequence: u64,
    truth_from: Point,
    truth_position: Point,
    observed: Option<ObservedTelemetry>,
    mission_state: MissionState,
    safety_state: SafetyState,
    action: Action,
}

struct MissionProgressTracker {
    waypoint_index: usize,
    best_distance_mm: Option<i64>,
    total_mm: u64,
}

impl MissionProgressTracker {
    fn new() -> Self {
        Self {
            waypoint_index: 0,
            best_distance_mm: None,
            total_mm: 0,
        }
    }

    fn sample(&mut self, position: Point, scenario: &Scenario) {
        while let Some(target) = scenario.mission.waypoints.get(self.waypoint_index).copied() {
            let distance = position.manhattan_distance(target);
            if let Some(best) = self.best_distance_mm {
                if distance < best {
                    self.total_mm = self.total_mm.saturating_add((best - distance) as u64);
                    self.best_distance_mm = Some(distance);
                }
            } else {
                self.best_distance_mm = Some(distance);
            }
            if !position.within_radius(target, scenario.mission.arrival_radius_mm) {
                break;
            }
            self.waypoint_index += 1;
            self.best_distance_mm = None;
        }
    }
}
