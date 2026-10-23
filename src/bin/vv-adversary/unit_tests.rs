//! Testes unitários: recorte de janelas, identidade, minimização e semente.

use autonomous_systems_vv_lab::actuator::{ActuatorConfig, ActuatorFault, ActuatorFaultWindow};
use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;
use autonomous_systems_vv_lab::model::{Scenario, TickWindow};

use crate::atoms::{Atom, Fault, Spec};
use crate::campaign::{Inputs, build_ctx};
use crate::eval::{Ctx, Params, Search, summarize};
use crate::identity;
use crate::minimize::minimize;
use crate::sampling::Refs;
use crate::search;
use crate::summary::control_classes;

const SCENARIO: &str = include_str!("../../../scenarios/m3/nominal-stop.json");
const CONTRACTS: &str = include_str!("../../../scenarios/m3/contracts-nominal.json");
const DELAYED_SCENARIO: &str = include_str!("../../../scenarios/m3/delayed-after-fallback.json");
const DELAYED_ACTUATOR: &str = include_str!("../../../scenarios/m3/actuator-delayed.json");

fn params(budget: u32, seed: u64) -> Params {
    Params {
        search: Search::Guided,
        campaign_seed: seed,
        sim_seed: 42,
        policies: vec![ControllerPolicyV1::DominantAxis],
        budget,
        minimize_budget: 96,
        max_failures: 4,
        mission_policy: MissionPolicy::default(),
    }
}

fn ctx(scenario: &str, actuator: &str, budget: u32, seed: u64) -> Ctx {
    let inputs = Inputs {
        scenario: scenario.as_bytes().to_vec(),
        contracts: CONTRACTS.as_bytes().to_vec(),
        actuator: actuator.as_bytes().to_vec(),
        actuator_from_file: true,
    };
    build_ctx(&inputs, params(budget, seed)).expect("valid inputs")
}

const EMPTY_ACTUATOR: &str = r#"{"schema_version":1,"seed":0,"faults":[]}"#;

fn atom(uid: u32, fault: Fault) -> Atom {
    Atom { uid, fault }
}

#[test]
fn truncation_clips_atoms_and_background_and_stays_valid() {
    let mut base = Scenario::from_json(SCENARIO).unwrap();
    base.sensors.gps.dropout_windows = vec![TickWindow {
        start_tick: 10,
        end_tick: 16,
    }];
    base.sensors.communication.packet_loss_windows = vec![TickWindow {
        start_tick: 1,
        end_tick: 16,
    }];
    let mut actuator = ActuatorConfig::default();
    actuator.faults.push(ActuatorFault::LostMovement {
        id: "background".into(),
        windows: vec![
            ActuatorFaultWindow {
                start_tick: 12,
                end_tick: 16,
            },
            ActuatorFaultWindow {
                start_tick: 2,
                end_tick: 3,
            },
        ],
        probability_permille: 1000,
    });
    let spec = Spec {
        atoms: vec![
            atom(1, Fault::GpsDropout { start: 14, end: 16 }),
            atom(
                2,
                Fault::ActuatorDelay {
                    start: 3,
                    end: 5,
                    delay_ticks: 40,
                    permille: 1000,
                },
            ),
            atom(3, Fault::GpsNoise { max_mm: 10 }),
        ],
        steps: 16,
    };
    for steps in 1..=16 {
        let cut = spec.truncate(steps);
        for atom in &cut.atoms {
            if let Some((start, end)) = atom.fault.window() {
                assert!(1 <= start && start <= end && end <= steps);
            }
        }
        let (scenario, config) = cut.apply(&base, &actuator).expect("valid after clip");
        assert_eq!(scenario.steps, steps);
        assert!(config.validate(steps).is_ok());
    }
    // Janela inteiramente fora do horizonte desaparece.
    assert_eq!(spec.truncate(10).atoms.len(), 2);
}

#[test]
fn identity_reports_delayed_actuation_mechanism_on_known_faulty_base() {
    let context = ctx(DELAYED_SCENARIO, DELAYED_ACTUATOR, 1, 1);
    let spec = Spec {
        atoms: Vec::new(),
        steps: context.base.steps,
    };
    let outcome = context
        .run(&spec, ControllerPolicyV1::DominantAxis)
        .unwrap();
    let found = identity::violations("dominant_axis", &outcome);
    let motion = found
        .iter()
        .find(|id| id.property == "no_motion_in_fallback")
        .expect("no_motion_in_fallback fails on the known faulty base");
    assert_eq!(motion.mechanism, vec!["delayed_actuation".to_owned()]);
    assert!(found.iter().any(|id| id.kind == "safety"));
}

#[test]
fn campaign_seed_is_reproducible_and_changes_candidates() {
    let keys = |seed: u64| {
        let context = ctx(SCENARIO, EMPTY_ACTUATOR, 12, seed);
        let control = search::control(&context).unwrap();
        let refs = Refs::build(&context.base, &context.contracts, &control.ticks);
        search::run(&context, &refs)
            .unwrap()
            .iter()
            .map(|c| c.spec.key())
            .collect::<Vec<_>>()
    };
    assert_eq!(keys(7), keys(7));
    assert_ne!(keys(7), keys(8));
}

#[test]
fn minimizer_preserves_full_identity_and_is_one_minimal() {
    let context = ctx(SCENARIO, EMPTY_ACTUATOR, 32, 42);
    let control = search::control(&context).unwrap();
    assert!(control.results.iter().all(|r| r.identities.is_empty()));
    let refs = Refs::build(&context.base, &context.contracts, &control.ticks);
    let candidates = search::run(&context, &refs).unwrap();
    let mut checked = 0;
    for candidate in candidates.iter().filter(|c| c.failing()).take(4) {
        let target = candidate.results[0].identities[0].clone();
        let result = minimize(
            &context,
            ControllerPolicyV1::DominantAxis,
            &candidate.spec,
            &target,
        )
        .unwrap();
        let reproduces = |spec: &Spec| {
            context
                .run(spec, ControllerPolicyV1::DominantAxis)
                .map(|outcome| identity::violations("dominant_axis", &outcome).contains(&target))
                .unwrap_or(false)
        };
        assert!(
            reproduces(&result.spec),
            "minimized spec keeps the identity"
        );
        assert!(result.spec.atoms.len() <= candidate.spec.atoms.len());
        assert!(result.spec.steps <= candidate.spec.steps);
        assert!(result.evaluations <= context.params.minimize_budget);
        if result.one_minimal_verified {
            for skipped in 0..result.spec.atoms.len() {
                let mut reduced = result.spec.clone();
                reduced.atoms.remove(skipped);
                assert!(
                    !reproduces(&reduced),
                    "removing atom {skipped} must change the identity"
                );
            }
        }
        checked += 1;
    }
    assert!(checked > 0, "the search must find a violation to minimize");
}

fn generated_campaign(scenario: &str, actuator: &str, max_failures: u32) -> serde_json::Value {
    let inputs = Inputs {
        scenario: scenario.as_bytes().to_vec(),
        contracts: CONTRACTS.as_bytes().to_vec(),
        actuator: actuator.as_bytes().to_vec(),
        actuator_from_file: true,
    };
    let mut parameters = params(24, 42);
    parameters.max_failures = max_failures;
    parameters.policies = vec![ControllerPolicyV1::DominantAxis, ControllerPolicyV1::XFirst];
    let generated = crate::campaign::generate(&inputs, parameters).expect("valid campaign");
    let (_, bytes) = generated
        .files
        .iter()
        .find(|(name, _)| name == "campaign.json")
        .expect("campaign.json is generated");
    serde_json::from_slice(bytes).unwrap()
}

#[test]
fn classes_present_in_the_control_are_inherited_and_rank_after_novel_ones() {
    let campaign = generated_campaign(DELAYED_SCENARIO, DELAYED_ACTUATOR, 4);
    let mut context = ctx(DELAYED_SCENARIO, DELAYED_ACTUATOR, 1, 1);
    context.params.policies = vec![ControllerPolicyV1::DominantAxis, ControllerPolicyV1::XFirst];
    let control = search::control(&context).unwrap();
    let control_keys = control_classes(&control.results);
    let metrics = &campaign["metrics"];
    let inherited_found = metrics["inherited_classes_found"].as_u64().unwrap();
    assert!(inherited_found > 0, "the faulty base already fails");
    assert_eq!(
        metrics["unique_classes_found"].as_u64().unwrap(),
        inherited_found + metrics["novel_classes_found"].as_u64().unwrap()
    );
    let (mut novel_kept, mut inherited_kept) = (0_u64, 0_u64);
    for failure in campaign["failures"].as_array().unwrap() {
        let text = |key: &str| failure["identity"][key].as_str().unwrap().to_owned();
        let mechanism = failure["identity"]["mechanism"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item.as_str().unwrap().to_owned())
            .collect();
        let key = (text("policy"), text("kind"), text("property"), mechanism);
        let inherited = failure["inherited_from_control"].as_bool().unwrap();
        assert_eq!(inherited, control_keys.contains(&key), "{key:?}");
        if inherited {
            inherited_kept += 1;
        } else {
            novel_kept += 1;
        }
    }
    // Só sobram lugares às herdadas depois de todas as novas terem entrado.
    let novel_found = metrics["novel_classes_found"].as_u64().unwrap();
    if inherited_kept > 0 {
        assert_eq!(novel_kept, novel_found);
    }
}

#[test]
fn clean_base_has_no_inherited_classes() {
    let campaign = generated_campaign(SCENARIO, EMPTY_ACTUATOR, 4);
    assert_eq!(campaign["metrics"]["inherited_classes_found"], 0);
    assert_eq!(campaign["metrics"]["unidentified_violations"], 0);
    assert!(
        campaign["failures"]
            .as_array()
            .unwrap()
            .iter()
            .all(|failure| failure["inherited_from_control"] == false)
    );
}

#[test]
fn violations_without_identity_are_reported_not_dropped() {
    let context = ctx(DELAYED_SCENARIO, DELAYED_ACTUATOR, 1, 1);
    let spec = Spec {
        atoms: Vec::new(),
        steps: context.base.steps,
    };
    let mut outcome = context
        .run(&spec, ControllerPolicyV1::DominantAxis)
        .unwrap();
    let before = identity::scan("dominant_axis", &outcome);
    assert!(before.unidentified.is_empty());
    // Evidência corrompida: invariante falhado sem falhas e contrato FAIL sem tick.
    let invariant = outcome
        .artifact
        .expected_report
        .invariants
        .iter_mut()
        .find(|invariant| !invariant.passed)
        .expect("a failed invariant on the known faulty base");
    invariant.failures.clear();
    let name = invariant.name.clone();
    let contract = outcome
        .verification
        .contract_results
        .iter_mut()
        .find(|result| result.contract_id == "no_motion_in_fallback")
        .expect("no_motion_in_fallback result");
    contract.first_violation_tick = None;
    let after = identity::scan("dominant_axis", &outcome);
    assert_eq!(after.identities.len() + 2, before.identities.len());
    assert!(
        after
            .unidentified
            .contains(&format!("safety:{name}:unidentified"))
    );
    assert!(
        after
            .unidentified
            .contains(&"temporal:no_motion_in_fallback:unidentified".to_owned())
    );
    // O resumo usado pela pesquisa e pelas métricas também as conta.
    let summary = summarize(ControllerPolicyV1::DominantAxis, &outcome);
    assert_eq!(summary.unidentified_violations, 2);
    assert!(
        summary
            .violations
            .contains(&"temporal:no_motion_in_fallback:unidentified".to_owned())
    );
}

#[test]
fn replay_case_reads_only_verified_bytes_and_rejects_unknown_paths() {
    let verified = std::collections::BTreeMap::from([("cases/01/original/m4.json", &b"{}"[..])]);
    for dir in ["../../outside", "cases/02/original", "C:/Windows"] {
        let error = crate::replay::replay_case(&verified, dir, "00")
            .expect_err("unknown case paths are refused");
        assert!(
            error.contains("is not part of the verified campaign"),
            "{error}"
        );
    }
    let error = crate::replay::replay_case(&verified, "cases/01/original", "00")
        .expect_err("hash mismatch");
    assert!(error.contains("hash differs"), "{error}");
}
