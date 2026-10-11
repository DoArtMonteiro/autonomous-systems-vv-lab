use super::*;

fn set(json: &str) -> ContractSet {
    ContractSet::from_json(json).unwrap()
}

fn tick(tick: u32, telemetry_present: bool, facts: Vec<TraceFact>) -> TraceTick {
    TraceTick {
        tick,
        telemetry_present,
        facts,
        transitions: Vec::new(),
    }
}

fn result(contracts: &ContractSet, trace: &[TraceTick], index: usize) -> ContractResult {
    evaluate(contracts, trace).remove(index)
}

#[test]
fn always_never_and_missing_sensor_telemetry_have_three_valued_results() {
    let contracts = set(r#"{"schema_version":1,"contracts":[
          {"type":"always","id":"zone_clear","predicate":"restricted_zone_clear"},
          {"type":"never","id":"fallback_motion","predicate":"movement_while_fallback"},
          {"type":"always","id":"localization_known","predicate":"localization_unreliable"}
        ]}"#);
    let trace = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::RestrictedZoneClear,
                TraceFact::LocalizationUnreliable,
            ],
        ),
        tick(2, false, vec![TraceFact::RestrictedZoneClear]),
    ];
    let results = evaluate(&contracts, &trace);
    assert_eq!(results[0].outcome, ContractOutcome::Pass);
    assert_eq!(results[1].outcome, ContractOutcome::Pass);
    assert_eq!(results[2].outcome, ContractOutcome::Inconclusive);
    assert_eq!(
        results[2].evidence[0].reason,
        EvidenceReason::MissingObservation
    );

    let violation = vec![
        tick(1, true, vec![TraceFact::RestrictedZoneClear]),
        tick(2, true, vec![TraceFact::MovementWhileFallback]),
    ];
    assert_eq!(
        result(&contracts, &violation, 1).first_violation_tick,
        Some(2)
    );
}

#[test]
fn bounded_response_includes_trigger_and_exact_deadline_ticks() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"stop","trigger":"stop_commanded","required":"vehicle_stationary","within_ticks":2}]}"#,
    );
    let on_trigger = vec![tick(
        1,
        true,
        vec![TraceFact::StopCommanded, TraceFact::VehicleStationary],
    )];
    assert_eq!(
        result(&contracts, &on_trigger, 0).outcome,
        ContractOutcome::Pass
    );

    let exact_deadline = vec![
        tick(1, true, vec![TraceFact::StopCommanded]),
        tick(2, true, vec![]),
        tick(3, true, vec![TraceFact::VehicleStationary]),
    ];
    let passed = result(&contracts, &exact_deadline, 0);
    assert_eq!(passed.outcome, ContractOutcome::Pass);
    assert_eq!(passed.evidence[0].deadline_tick, Some(3));

    let late = vec![
        tick(1, true, vec![TraceFact::StopCommanded]),
        tick(2, true, vec![]),
        tick(3, true, vec![]),
        tick(4, true, vec![TraceFact::VehicleStationary]),
    ];
    let failed = result(&contracts, &late, 0);
    assert_eq!(failed.outcome, ContractOutcome::Fail);
    assert_eq!(failed.first_trigger_tick, Some(1));
    assert_eq!(failed.deadline_tick, Some(3));
    assert_eq!(failed.first_violation_tick, Some(3));
    assert_eq!(failed.evidence[0].violation_trace_index, Some(2));
}

#[test]
fn zero_bound_and_response_obligations_continue_after_mission_completion() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"fallback","trigger":"localization_unreliable","required":"safety_fallback","within_ticks":0}]}"#,
    );
    let same_tick = vec![tick(
        1,
        true,
        vec![TraceFact::LocalizationUnreliable, TraceFact::SafetyFallback],
    )];
    assert_eq!(
        result(&contracts, &same_tick, 0).outcome,
        ContractOutcome::Pass
    );

    let mission_completion_then_deadline = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::LocalizationUnreliable,
                TraceFact::MissionCompleted,
            ],
        ),
        tick(2, true, vec![]),
        tick(3, true, vec![TraceFact::MissionTerminated]),
    ];
    let pending_contract = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"fallback","trigger":"localization_unreliable","required":"safety_fallback","within_ticks":2}]}"#,
    );
    let completed_result = result(&pending_contract, &mission_completion_then_deadline, 0);
    assert_eq!(completed_result.outcome, ContractOutcome::Fail);
    assert_eq!(completed_result.first_violation_tick, Some(3));

    let pending_at_trace_end = vec![tick(1, true, vec![TraceFact::LocalizationUnreliable])];
    let pending_result = result(&pending_contract, &pending_at_trace_end, 0);
    assert_eq!(pending_result.outcome, ContractOutcome::Inconclusive);
    assert_eq!(
        pending_result.evidence[0].reason,
        EvidenceReason::TraceEndedBeforeDeadline
    );
}

#[test]
fn repeated_triggers_create_overlapping_obligations_and_unknown_trigger_resets_streak() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"fallback","trigger":"localization_unreliable","required":"safety_fallback","within_ticks":2,"trigger_for_ticks":2}]}"#,
    );
    let trace = vec![
        tick(1, true, vec![TraceFact::LocalizationUnreliable]),
        tick(2, false, vec![]),
        tick(3, true, vec![TraceFact::LocalizationUnreliable]),
        tick(4, true, vec![TraceFact::LocalizationUnreliable]),
        tick(5, true, vec![TraceFact::LocalizationUnreliable]),
        tick(6, true, vec![TraceFact::SafetyFallback]),
    ];
    let streak_result = result(&contracts, &trace, 0);
    assert_eq!(streak_result.first_trigger_tick, Some(4));
    assert_eq!(streak_result.outcome, ContractOutcome::Inconclusive);
    assert_eq!(
        streak_result
            .evidence
            .iter()
            .filter(|row| row.outcome == ContractOutcome::Pass)
            .count(),
        1
    );
    assert!(streak_result.evidence.iter().any(|row| {
        row.outcome == ContractOutcome::Inconclusive
            && row.reason == EvidenceReason::MissingObservation
    }));

    let overlapping = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"fallback","trigger":"stop_commanded","required":"safety_fallback","within_ticks":3}]}"#,
    );
    let trace = vec![
        tick(1, true, vec![TraceFact::StopCommanded]),
        tick(2, true, vec![]),
        tick(3, true, vec![TraceFact::StopCommanded]),
        tick(4, true, vec![TraceFact::SafetyFallback]),
    ];
    let overlapping_result = result(&overlapping, &trace, 0);
    assert_eq!(overlapping_result.outcome, ContractOutcome::Pass);
    assert_eq!(
        overlapping_result
            .evidence
            .iter()
            .map(|row| row.trigger_tick)
            .collect::<Vec<_>>(),
        vec![Some(1), Some(3)]
    );
}

#[test]
fn correlated_command_response_does_not_accept_another_commands_outcome() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"command_resolves","trigger":"movement_commanded","required":"command_resolved","within_ticks":1,"correlation":"command_id"}]}"#,
    );
    let trace = vec![
        tick(
            1,
            true,
            vec![TraceFact::MovementCommanded { command_id: 10 }],
        ),
        tick(
            2,
            true,
            vec![
                TraceFact::MovementCommanded { command_id: 11 },
                TraceFact::CommandResolved {
                    command_id: 10,
                    outcome: CommandOutcome::ExplicitFailure,
                },
            ],
        ),
        tick(3, true, vec![]),
    ];
    let command_result = result(&contracts, &trace, 0);
    assert_eq!(command_result.outcome, ContractOutcome::Fail);
    assert_eq!(command_result.evidence.len(), 2);
    assert!(
        command_result.evidence[0]
            .detail
            .as_deref()
            .unwrap()
            .contains("command_id=10")
    );
    assert_eq!(
        command_result.evidence[0].monitor_derived_command_outcome,
        None
    );
    assert_eq!(
        command_result.evidence[1].monitor_derived_command_outcome,
        Some(CommandOutcome::Timeout)
    );
    assert_eq!(
        command_result.evidence[1].observation,
        ObservationState::MonitorDerived
    );
    assert_eq!(
        command_result.evidence[1].reason,
        EvidenceReason::CommandTimedOutDerived
    );
    assert_eq!(command_result.evidence[1].violation_tick, Some(3));

    let strict_apply = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"command_applies","trigger":"movement_commanded","required":"command_applied","within_ticks":1,"correlation":"command_id"}]}"#,
    );
    let ignored = vec![
        tick(
            1,
            true,
            vec![TraceFact::MovementCommanded { command_id: 20 }],
        ),
        tick(2, true, vec![]),
    ];
    let failed = result(&strict_apply, &ignored, 0);
    assert_eq!(failed.outcome, ContractOutcome::Fail);
    assert_eq!(failed.first_violation_tick, Some(2));
    assert_eq!(
        failed.evidence[0].monitor_derived_command_outcome,
        Some(CommandOutcome::Timeout)
    );

    let late_apply = vec![
        tick(
            1,
            true,
            vec![TraceFact::MovementCommanded { command_id: 30 }],
        ),
        tick(2, true, vec![]),
        tick(3, true, vec![TraceFact::CommandApplied { command_id: 30 }]),
    ];
    assert_eq!(
        result(&strict_apply, &late_apply, 0).outcome,
        ContractOutcome::Fail
    );

    let explicit_resolution_only = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_response","id":"explicit_resolution","trigger":"movement_commanded","required":"command_resolved","within_ticks":1,"correlation":"command_id"}]}"#,
    );
    let missing_resolution = vec![
        tick(
            1,
            true,
            vec![TraceFact::MovementCommanded { command_id: 41 }],
        ),
        tick(2, true, vec![]),
    ];
    let unresolved = result(&explicit_resolution_only, &missing_resolution, 0);
    assert_eq!(unresolved.outcome, ContractOutcome::Fail);
    assert_eq!(
        unresolved.evidence[0].reason,
        EvidenceReason::CommandTimedOutDerived
    );
    assert_eq!(
        unresolved.evidence[0].monitor_derived_command_outcome,
        Some(CommandOutcome::Timeout)
    );

    let ended_early = vec![tick(
        1,
        true,
        vec![TraceFact::MovementCommanded { command_id: 42 }],
    )];
    let pending = result(&explicit_resolution_only, &ended_early, 0);
    assert_eq!(pending.outcome, ContractOutcome::Inconclusive);
    assert_eq!(pending.evidence[0].monitor_derived_command_outcome, None);
}

#[test]
fn ordered_transition_requires_exact_sequence_and_reports_wrong_event_order() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"ordered_transition","id":"mission","domain":"mission","sequence":[{"from":"pending","to":"running"},{"from":"running","to":"completed"}]}]}"#,
    );
    let pass = vec![
        TraceTick {
            transitions: vec![TraceTransition {
                source_sequence: 2,
                domain: TransitionDomain::Mission,
                from: TransitionState::Pending,
                to: TransitionState::Running,
            }],
            ..tick(1, true, vec![])
        },
        TraceTick {
            transitions: vec![TraceTransition {
                source_sequence: 9,
                domain: TransitionDomain::Mission,
                from: TransitionState::Running,
                to: TransitionState::Completed,
            }],
            ..tick(2, true, vec![])
        },
    ];
    assert_eq!(result(&contracts, &pass, 0).outcome, ContractOutcome::Pass);

    let incomplete = vec![TraceTick {
        transitions: vec![TraceTransition {
            source_sequence: 1,
            domain: TransitionDomain::Mission,
            from: TransitionState::Pending,
            to: TransitionState::Running,
        }],
        ..tick(1, true, vec![])
    }];
    assert_eq!(
        result(&contracts, &incomplete, 0).outcome,
        ContractOutcome::Inconclusive
    );

    let wrong_order = vec![TraceTick {
        transitions: vec![TraceTransition {
            source_sequence: 1,
            domain: TransitionDomain::Mission,
            from: TransitionState::Pending,
            to: TransitionState::Completed,
        }],
        ..tick(1, true, vec![])
    }];
    let failed = result(&contracts, &wrong_order, 0);
    assert_eq!(failed.outcome, ContractOutcome::Fail);
    assert_eq!(failed.first_violation_tick, Some(1));
}

#[test]
fn bounded_progress_uses_cumulative_millimetres_and_separates_incomplete_end() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_progress","id":"mission_progress","within_ticks":2,"minimum_increase_mm":10}]}"#,
    );
    let passed = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 100 },
            ],
        ),
        tick(
            2,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 105 },
            ],
        ),
        tick(
            3,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 110 },
            ],
        ),
        tick(
            4,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 115 },
            ],
        ),
        tick(
            5,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 120 },
            ],
        ),
        tick(
            6,
            true,
            vec![
                TraceFact::MissionTerminated,
                TraceFact::MissionProgress { progress_mm: 130 },
            ],
        ),
    ];
    assert_eq!(
        result(&contracts, &passed, 0).outcome,
        ContractOutcome::Pass
    );

    let stalled = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 20 },
            ],
        ),
        tick(
            2,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 20 },
            ],
        ),
        tick(
            3,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 20 },
            ],
        ),
    ];
    let failed = result(&contracts, &stalled, 0);
    assert_eq!(failed.outcome, ContractOutcome::Fail);
    assert_eq!(failed.first_violation_tick, Some(3));
    assert_eq!(failed.deadline_tick, Some(3));

    let incomplete = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 20 },
            ],
        ),
        tick(
            2,
            true,
            vec![
                TraceFact::MissionTerminated,
                TraceFact::MissionProgress { progress_mm: 24 },
            ],
        ),
    ];
    assert_eq!(
        result(&contracts, &incomplete, 0).outcome,
        ContractOutcome::Inconclusive
    );
}

#[test]
fn bounded_progress_is_inconclusive_when_measurements_or_active_window_end_early() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"bounded_progress","id":"mission_progress","within_ticks":2,"minimum_increase_mm":10}]}"#,
    );
    let missing_measurement = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 100 },
            ],
        ),
        tick(2, true, vec![TraceFact::MissionActive]),
        tick(
            3,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 100 },
            ],
        ),
    ];
    let missing_result = result(&contracts, &missing_measurement, 0);
    assert_eq!(missing_result.outcome, ContractOutcome::Inconclusive);
    assert!(missing_result.evidence.iter().any(|row| {
        row.trigger_tick == Some(1)
            && row.reason == EvidenceReason::MissingProgressMeasurement
            && row.outcome == ContractOutcome::Inconclusive
    }));

    let completed_early = vec![
        tick(
            1,
            true,
            vec![
                TraceFact::MissionActive,
                TraceFact::MissionProgress { progress_mm: 100 },
            ],
        ),
        tick(
            2,
            true,
            vec![TraceFact::MissionProgress { progress_mm: 104 }],
        ),
    ];
    let completed_result = result(&contracts, &completed_early, 0);
    assert_eq!(completed_result.outcome, ContractOutcome::Inconclusive);
    assert_eq!(
        completed_result.evidence[0].reason,
        EvidenceReason::MissionTerminatedBeforeDeadline
    );
}

#[test]
fn final_trace_marker_can_coexist_with_active_state_on_that_tick() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"always","id":"active_on_last_tick","predicate":"mission_active"}]}"#,
    );
    let trace = vec![tick(
        1,
        true,
        vec![TraceFact::MissionActive, TraceFact::MissionTerminated],
    )];
    assert_eq!(result(&contracts, &trace, 0).outcome, ContractOutcome::Pass);
}

#[test]
fn rejects_missing_ticks_corrupt_command_refs_and_transition_order() {
    let contracts = set(
        r#"{"schema_version":1,"contracts":[{"type":"always","id":"clear","predicate":"restricted_zone_clear"}]}"#,
    );
    for invalid in [
        vec![tick(2, true, vec![TraceFact::RestrictedZoneClear])],
        vec![
            tick(1, true, vec![TraceFact::RestrictedZoneClear]),
            tick(3, true, vec![TraceFact::RestrictedZoneClear]),
        ],
        vec![tick(
            1,
            true,
            vec![TraceFact::CommandApplied { command_id: 7 }],
        )],
        vec![
            tick(1, true, vec![TraceFact::MissionTerminated]),
            tick(2, true, vec![TraceFact::RestrictedZoneClear]),
        ],
        vec![TraceTick {
            transitions: vec![
                TraceTransition {
                    source_sequence: 8,
                    domain: TransitionDomain::Safety,
                    from: TransitionState::Nominal,
                    to: TransitionState::Fallback,
                },
                TraceTransition {
                    source_sequence: 7,
                    domain: TransitionDomain::Safety,
                    from: TransitionState::Fallback,
                    to: TransitionState::Nominal,
                },
            ],
            ..tick(1, true, vec![TraceFact::RestrictedZoneClear])
        }],
    ] {
        let result = result(&contracts, &invalid, 0);
        assert_eq!(result.outcome, ContractOutcome::Inconclusive);
        assert_eq!(result.evidence[0].reason, EvidenceReason::InvalidTrace);
    }
}
