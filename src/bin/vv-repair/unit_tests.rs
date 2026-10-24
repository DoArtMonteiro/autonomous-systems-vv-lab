use autonomous_systems_vv_lab::controller::ControllerPolicyV1;

use crate::evidence::{ReplayStatus, Row};
use crate::experiment::{
    Acceptance, ControllerConfig, Decision, Expect, Experiment, Overrides, Role, SCHEMA, Safety,
    SuiteSpec,
};
use crate::sampling::Refs;
use crate::workloads::{Family, Split, workloads};

/// Hash da biblioteca com a opção `cancel_pending_on_fallback` (decisão do responsável).
/// O valor dos manifestos M4 e M5 era `38039c255f6f60c8…`; mudanças futuras exigem nova decisão.
const CANONICAL_SOURCE_SHA256: &str =
    "620f76031548075a66a2e4117956a29d1b63d846263b4aed224b74e2e2501f6b";

const SCENARIO: &str = include_str!("../../../scenarios/m3/nominal-stop.json");
const CONTRACTS: &str = include_str!("../../../scenarios/m3/contracts-nominal.json");

fn config(id: &str, overrides: Overrides) -> ControllerConfig {
    ControllerConfig {
        id: id.into(),
        policy: ControllerPolicyV1::DominantAxis,
        overrides,
        rationale: "test".into(),
        role: Role::Candidate,
        expect: Expect::default(),
    }
}

fn experiment() -> Experiment {
    Experiment {
        schema: SCHEMA.into(),
        name: "unit".into(),
        sim_seeds: vec![42],
        tuning_seeds: vec![1, 2],
        heldout_seeds: vec![3],
        workloads_per_seed: 4,
        minimize_budget: 8,
        max_corpus_per_suite: 2,
        suites: vec![SuiteSpec {
            id: "nominal".into(),
            scenario: "s.json".into(),
            contracts: "c.json".into(),
            actuator: None,
            description: String::new(),
        }],
        acceptance: Acceptance {
            alpha_permille: 50,
            max_completion_loss_permille: 10,
            max_mean_distance_increase_mm: 100,
            min_heldout_pairs: 10,
        },
        baseline: config("baseline", Overrides::default()),
        candidates: vec![config(
            "watchdog_2",
            Overrides {
                fallback_after_ticks: Some(2),
                ..Overrides::default()
            },
        )],
    }
}

fn refs() -> Refs {
    let scenario = autonomous_systems_vv_lab::parse_scenario(SCENARIO).unwrap();
    let contracts =
        autonomous_systems_vv_lab::contracts::ContractSet::from_json(CONTRACTS).unwrap();
    let mut refs = Refs::build(&scenario, &contracts, &Default::default());
    refs.biased = false;
    refs
}

#[test]
fn library_source_hash_is_unchanged() {
    assert_eq!(
        autonomous_systems_vv_lab::source_sha256(),
        CANONICAL_SOURCE_SHA256
    );
}

#[test]
fn valid_experiment_passes_and_bad_ones_fail() {
    assert!(experiment().validate().is_ok());
    let mut overlap = experiment();
    overlap.heldout_seeds = vec![2];
    assert!(overlap.validate().is_err());
    let mut duplicate = experiment();
    duplicate.candidates[0].id = "baseline".into();
    assert!(duplicate.validate().is_err());
    let mut bad_alpha = experiment();
    bad_alpha.acceptance.alpha_permille = 7;
    assert!(bad_alpha.validate().is_err());
    let mut expect_on_candidate = experiment();
    expect_on_candidate.candidates[0].expect.decision = Some(Decision::Reject);
    assert!(expect_on_candidate.validate().is_err());
    let mut control = experiment();
    control.candidates[0].role = Role::Control;
    control.candidates[0].expect.safety = Some(Safety::Regressed);
    assert!(control.validate().is_ok());
    assert!(serde_json::from_str::<Expect>(r#"{"safety":"worse"}"#).is_err());
    assert!(serde_json::from_str::<Expect>(r#"{"safety":"no_effect"}"#).is_ok());
    for path in [
        "/etc/passwd",
        r"\\host\share\s.json",
        "//host/c$/s.json",
        "C:/s.json",
    ] {
        let mut absolute = experiment();
        absolute.suites[0].scenario = path.into();
        assert!(absolute.validate().is_err(), "{path}");
    }
    let mut parent = experiment();
    parent.suites[0].scenario = "../m3/nominal-stop.json".into();
    assert!(parent.validate().is_ok());
    let mut bad_schema = experiment();
    bad_schema.schema = "other".into();
    assert!(bad_schema.validate().is_err());
    let mut huge = experiment();
    huge.workloads_per_seed = 64;
    huge.tuning_seeds = (0..64).collect();
    huge.heldout_seeds = (100..164).collect();
    huge.sim_seeds = vec![1, 2, 3, 4];
    assert!(huge.validate().is_err());
}

#[test]
fn cancellation_override_only_touches_the_actuator_flag() {
    use autonomous_systems_vv_lab::actuator::ActuatorConfig;
    let base = ActuatorConfig::default();
    let on = Overrides {
        cancel_pending_on_fallback: Some(true),
        ..Overrides::default()
    };
    let changed = on.apply_actuator(&base);
    assert!(changed.cancel_pending_on_fallback);
    assert_eq!(changed.faults, base.faults);
    assert!(
        !Overrides::default()
            .apply_actuator(&base)
            .cancel_pending_on_fallback
    );
    let text = r#"{"cancel_pending_on_fallback":true}"#;
    let parsed: Overrides = serde_json::from_str(text).unwrap();
    assert_eq!(parsed.cancel_pending_on_fallback, Some(true));
}

#[test]
fn unknown_override_fields_are_rejected() {
    let text = r#"{"fallback_after_ticks":2,"geometry":1}"#;
    assert!(serde_json::from_str::<Overrides>(text).is_err());
}

#[test]
fn overrides_change_only_the_named_parameters() {
    let base = autonomous_systems_vv_lab::parse_scenario(SCENARIO).unwrap();
    let changed = Overrides {
        fallback_after_ticks: Some(2),
        stride_permille: Some(500),
        ..Overrides::default()
    }
    .apply(&base)
    .unwrap();
    assert_eq!(changed.safety.fallback_after_ticks, 2);
    assert_eq!(changed.vehicle.step_mm, base.vehicle.step_mm / 2);
    assert_eq!(changed.steps, base.steps);
    assert_eq!(
        changed.safety.recovery_after_ticks,
        base.safety.recovery_after_ticks
    );
    let invalid = Overrides {
        stride_permille: Some(0),
        ..Overrides::default()
    };
    assert!(invalid.apply(&base).is_err());
}

#[test]
fn workloads_are_deterministic_unique_and_family_pure() {
    let experiment = experiment();
    let first = workloads(&experiment, &refs());
    let second = workloads(&experiment, &refs());
    assert_eq!(
        serde_json::to_string(&first).unwrap(),
        serde_json::to_string(&second).unwrap()
    );
    assert_eq!(first[0].family, Family::Nominal);
    assert!(first[0].atoms.is_empty());
    let mut keys = std::collections::BTreeSet::new();
    for (index, workload) in first.iter().enumerate() {
        assert_eq!(workload.index, index);
        assert!(keys.insert(serde_json::to_string(&workload.atoms).unwrap()));
        if Family::PURE.contains(&workload.family) {
            assert!(
                workload
                    .atoms
                    .iter()
                    .all(|atom| Family::of(&atom.fault) == workload.family)
            );
        }
    }
    assert!(first.iter().any(|w| w.split == Split::Heldout));
    assert_eq!(
        serde_json::to_string(&Family::Actuator).unwrap(),
        "\"actuator\""
    );
    assert_eq!(
        serde_json::to_string(&Split::Heldout).unwrap(),
        "\"heldout\""
    );
}

#[test]
fn replay_status_never_counts_inconclusive_or_untriggered_as_resolved() {
    use autonomous_systems_vv_lab::mission_analysis::MissionOutcome;
    let row = |violations: &[&str], inconclusive: &[&str], untriggered: &[&str]| Row {
        violations: violations.iter().map(|v| v.to_string()).collect(),
        first_violation_tick: None,
        inconclusive: inconclusive.iter().map(|v| v.to_string()).collect(),
        untriggered: untriggered.iter().map(|v| v.to_string()).collect(),
        mission: MissionOutcome::Completed,
        completion_tick: None,
        waypoints_completed: 0,
        fallback_ticks: 0,
        movement_ticks: 0,
        actuator_fault_events: 0,
        distance_remaining_mm: None,
    };
    let class = "temporal/fallback_response/delayed_actuation";
    assert_eq!(
        ReplayStatus::of(class, &row(&[class], &[], &[])),
        ReplayStatus::Persisted
    );
    let other = "temporal/fallback_response/none";
    assert_eq!(
        ReplayStatus::of(class, &row(&[other], &[], &[])),
        ReplayStatus::Shifted
    );
    let pending = row(&[], &["fallback_response"], &[]);
    assert_eq!(
        ReplayStatus::of(class, &pending),
        ReplayStatus::Inconclusive
    );
    assert_eq!(
        ReplayStatus::of(class, &row(&[], &[], &["fallback_response"])),
        ReplayStatus::Untriggered
    );
    let fixed = row(&[], &[], &[]);
    assert_eq!(ReplayStatus::of(class, &fixed), ReplayStatus::Resolved);
    // A `never` contract has no trigger: passing it is a real resolution.
    let never = "temporal/no_motion_in_fallback/delayed_actuation";
    assert_eq!(
        ReplayStatus::of(never, &row(&[], &[], &[])),
        ReplayStatus::Resolved
    );
    let safety = "safety/safe_fallback/none";
    assert_eq!(
        ReplayStatus::of(safety, &row(&[], &[], &[])),
        ReplayStatus::Resolved
    );
}
