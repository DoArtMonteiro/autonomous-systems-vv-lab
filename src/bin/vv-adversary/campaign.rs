//! Orquestra a campanha em memória e devolve todos os ficheiros de saída.

use std::collections::{BTreeMap, BTreeSet};

use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::contracts::ContractSet;
use autonomous_systems_vv_lab::parse_scenario;

use crate::atoms::{self, Spec};
use crate::cases;
use crate::eval::{Ctx, Params, PolicySummary, Search, policy_name, summarize};
use crate::identity::Identity;
use crate::io::{MAX_CAMPAIGN_BYTES, pretty_json, sha256_hex};
use crate::minimize::minimize;
use crate::model::*;
use crate::recheck::recheck;
use crate::sampling::{self, Refs};
use crate::search::{self, ADVERSARY_SEED_DOMAIN, Candidate};
use crate::summary::{
    candidate_rows, control_classes, design, input_info, matrix, metrics, policy_rows,
};

pub struct Inputs {
    pub scenario: Vec<u8>,
    pub contracts: Vec<u8>,
    pub actuator: Vec<u8>,
    pub actuator_from_file: bool,
}

pub struct Generated {
    pub files: Vec<(String, Vec<u8>)>,
    pub summary: String,
}

pub fn default_actuator_bytes() -> Result<Vec<u8>, String> {
    pretty_json(&ActuatorConfig::default())
}

fn text(bytes: &[u8], what: &str) -> Result<String, String> {
    String::from_utf8(bytes.to_vec()).map_err(|_| format!("{what} is not valid UTF-8"))
}

pub fn build_ctx(inputs: &Inputs, params: Params) -> Result<Ctx, String> {
    let base = parse_scenario(&text(&inputs.scenario, "scenario")?)
        .map_err(|error| format!("scenario: {error}"))?;
    let contracts = ContractSet::from_json(&text(&inputs.contracts, "contracts")?)
        .map_err(|error| format!("contracts: {error}"))?;
    let actuator = ActuatorConfig::from_json(&text(&inputs.actuator, "actuator")?)
        .map_err(|error| format!("actuator: {error}"))?;
    actuator
        .validate(base.steps)
        .map_err(|error| format!("actuator: {error}"))?;
    if !atoms::background_ids_are_free(&actuator) {
        return Err(format!(
            "actuator fault ids must not start with '{}'",
            atoms::ID_PREFIX
        ));
    }
    Ok(Ctx {
        base,
        actuator,
        contracts,
        params,
    })
}

struct Kept {
    candidate: usize,
    policy: autonomous_systems_vv_lab::controller::ControllerPolicyV1,
    identity: Identity,
    inherited: bool,
}

pub fn generate(inputs: &Inputs, params: Params) -> Result<Generated, String> {
    let ctx = build_ctx(inputs, params)?;
    let policies: Vec<String> = ctx
        .params
        .policies
        .iter()
        .map(|p| policy_name(*p).to_owned())
        .collect();
    let control = search::control(&ctx)?;
    let mut refs = Refs::build(&ctx.base, &ctx.contracts, &control.ticks);
    refs.biased = ctx.params.search != Search::Uniform;
    let candidates = search::run(&ctx, &refs)?;

    let inherited_keys = control_classes(&control.results);
    let mut seen = BTreeSet::new();
    let mut found: Vec<Kept> = Vec::new();
    for candidate in &candidates {
        for (index, result) in candidate.results.iter().enumerate() {
            for identity in &result.identities {
                let key = identity.class_key();
                if !seen.contains(&key) {
                    found.push(Kept {
                        candidate: candidate.index,
                        policy: ctx.params.policies[index],
                        identity: identity.clone(),
                        inherited: inherited_keys.contains(&key),
                    });
                    seen.insert(key);
                }
            }
        }
    }
    let kept = select_kept(found, ctx.params.max_failures as usize);

    let mut case_file_list = Vec::new();
    let mut failures = Vec::new();
    let (mut minimization_evals, mut artifact_evals) = (0_u32, 0_u32);
    for (number, item) in kept.iter().enumerate() {
        let (row, case_files, minimized_evals, extra) =
            build_failure(&ctx, &candidates[item.candidate], item, number as u32 + 1)?;
        minimization_evals += minimized_evals;
        artifact_evals += extra;
        case_file_list.extend(case_files);
        failures.push(row);
    }

    let search_evals = (candidates.len() * policies.len()) as u32;
    let control_evals = policies.len() as u32;
    let metrics_value = metrics(
        &policies,
        &candidates,
        &control.results,
        &failures,
        kept.len(),
        &seen,
        Evaluations {
            control: control_evals,
            search: search_evals,
            minimization: minimization_evals,
            case_artifacts: artifact_evals,
            total: control_evals + search_evals + minimization_evals + artifact_evals,
        },
    );
    let body = Body {
        schema: SCHEMA,
        prng: PrngInfo {
            algorithm: "xorshift64star",
            domain: format!("0x{ADVERSARY_SEED_DOMAIN:016x}"),
            seed_mixing: "splitmix64(campaign_seed ^ splitmix64(domain))",
            campaign_seed: ctx.params.campaign_seed,
            sim_seed: ctx.params.sim_seed,
        },
        limits: Limits {
            budget: ctx.params.budget,
            minimize_budget: ctx.params.minimize_budget,
            max_failures: ctx.params.max_failures,
            policies: policies.clone(),
            stall_window_ticks: ctx.params.mission_policy.stall_window_ticks,
            min_progress_mm: ctx.params.mission_policy.min_progress_mm,
            search: ctx.params.search.name(),
            phase_a_candidates: search::phase_a_candidates(&ctx),
            top_k: search::TOP_K,
            max_atoms_phase_a: sampling::MAX_ATOMS_PHASE_A,
            max_atoms_phase_b: sampling::MAX_ATOMS_PHASE_B,
        },
        inputs: input_info(inputs, &ctx),
        source_sha256: autonomous_systems_vv_lab::source_sha256(),
        design: design(),
        references: refs,
        control: policy_rows(&policies, &control.results),
        candidates: candidate_rows(&policies, &candidates),
        failures,
        metrics: metrics_value,
        policy_matrix: matrix(&policies, &candidates),
    };
    let unsigned = pretty_json(&Campaign {
        body: &body,
        campaign_sha256: None,
    })?;
    let hash = sha256_hex(&unsigned);
    let campaign = pretty_json(&Campaign {
        body: &body,
        campaign_sha256: Some(hash.clone()),
    })?;
    // `replay` só lê até este limite; uma campanha que o excede não seria reprodutível.
    if campaign.len() > MAX_CAMPAIGN_BYTES {
        return Err(format!(
            "campaign.json of {} bytes exceeds the {MAX_CAMPAIGN_BYTES} byte replay limit",
            campaign.len()
        ));
    }
    let summary = format!(
        "vv-adversary campaign: candidates={} evaluations={} violating_candidates={} classes_found={} novel_classes={} inherited_classes={} cases={} control_violations={} unidentified_violations={} campaign_sha256={hash}",
        body.metrics.candidates,
        body.metrics.evaluations.total,
        body.metrics.violating_candidates,
        body.metrics.unique_classes_found,
        body.metrics.novel_classes_found,
        body.metrics.inherited_classes_found,
        body.failures.len(),
        body.metrics.control_violations,
        body.metrics.unidentified_violations,
    );
    let report = crate::markdown::render(&body, &hash).into_bytes();
    let mut ordered = vec![
        ("inputs/scenario.json".to_owned(), inputs.scenario.clone()),
        ("inputs/contracts.json".to_owned(), inputs.contracts.clone()),
        ("inputs/actuator.json".to_owned(), inputs.actuator.clone()),
        ("campaign.json".to_owned(), campaign),
        ("report.md".to_owned(), report),
    ];
    ordered.extend(case_file_list);
    Ok(Generated {
        files: ordered,
        summary,
    })
}

type FailureBuild = (FailureRow, Vec<(String, Vec<u8>)>, u32, u32);

fn build_failure(
    ctx: &Ctx,
    candidate: &Candidate,
    item: &Kept,
    number: u32,
) -> Result<FailureBuild, String> {
    let policy_text = policy_name(item.policy);
    let case = format!("cases/{number:02}-{policy_text}-{}", item.identity.property);
    let original_spec = candidate.spec.clone();
    let minimized = minimize(ctx, item.policy, &original_spec, &item.identity)?;
    let original_outcome = ctx.run(&original_spec, item.policy)?;
    let minimized_outcome = ctx.run(&minimized.spec, item.policy)?;
    let mut artifact_evals = 2;
    let original_dir = format!("{case}/original");
    let minimized_dir = format!("{case}/minimized");
    let original_files = cases::build(&original_dir, &original_outcome, &ctx.contracts)?;
    let minimized_files = cases::build(&minimized_dir, &minimized_outcome, &ctx.contracts)?;

    let side = |dir: &str, spec: &Spec, outcome: &_, sha: &str| {
        let summary = summarize(item.policy, outcome);
        CaseSide {
            dir: dir.to_owned(),
            atoms: spec.atoms.clone(),
            steps: spec.steps,
            active_fault_ticks: spec.active_fault_ticks(),
            safety: summary.safety,
            temporal: summary.temporal,
            mission: summary.mission,
            violations: summary.violations,
            m4_sha256: sha.to_owned(),
        }
    };
    let original = side(
        &original_dir,
        &original_spec,
        &original_outcome,
        &original_files.m4_sha256,
    );
    let minimized_side = side(
        &minimized_dir,
        &minimized.spec,
        &minimized_outcome,
        &minimized_files.m4_sha256,
    );

    let (causal_trace, evidence) = cases::causal_trace(
        &minimized_outcome,
        &item.identity.kind,
        &item.identity.property,
        item.identity.violation_tick,
    );
    let recheck_result = recheck(
        &minimized_outcome.artifact.scenario,
        &minimized_outcome.artifact.expected_report,
        &ctx.contracts,
        &item.identity,
    );

    let mut comparison = BTreeMap::new();
    for policy in &ctx.params.policies {
        let outcome = ctx.run(&minimized.spec, *policy)?;
        artifact_evals += 1;
        let summary: PolicySummary = summarize(*policy, &outcome);
        comparison.insert(
            policy_name(*policy).to_owned(),
            Comparison {
                failing_policy: *policy == item.policy,
                safety: summary.safety,
                temporal: summary.temporal,
                mission: summary.mission,
                same_property_violated: summary.identities.iter().any(|id| {
                    id.kind == item.identity.kind && id.property == item.identity.property
                }),
                same_class_violated: summary.identities.iter().any(|id| {
                    id.kind == item.identity.kind
                        && id.property == item.identity.property
                        && id.mechanism == item.identity.mechanism
                }),
                violations: summary.violations,
            },
        );
    }

    let row = FailureRow {
        case: number,
        class: item.identity.class_label(),
        identity: item.identity.clone(),
        candidate_index: candidate.index,
        inherited_from_control: item.inherited,
        reduction: Reduction {
            atoms: Pair {
                before: original.atoms.len(),
                after: minimized_side.atoms.len(),
            },
            active_fault_ticks: Pair {
                before: original.active_fault_ticks,
                after: minimized_side.active_fault_ticks,
            },
            steps: Pair {
                before: original.steps,
                after: minimized_side.steps,
            },
            evaluations_used: minimized.evaluations,
            evaluation_budget: ctx.params.minimize_budget,
            budget_exhausted: minimized.exhausted,
            one_minimal_verified: minimized.one_minimal_verified,
        },
        original,
        minimized: minimized_side,
        reduction_log: minimized.log,
        evidence,
        causal_trace,
        recheck: recheck_result,
        policy_comparison: comparison,
    };
    let mut case_files = original_files.files;
    case_files.extend(minimized_files.files);
    Ok((row, case_files, minimized.evaluations, artifact_evals))
}

/// Classes novas antes das herdadas do controlo; em cada grupo, uma classe por
/// propriedade primeiro (ordem de descoberta), depois as restantes. O resultado
/// volta à ordem de descoberta para numerar os casos.
fn select_kept(found: Vec<Kept>, limit: usize) -> Vec<Kept> {
    let mut chosen = vec![false; found.len()];
    let mut count = 0;
    for inherited in [false, true] {
        let mut properties = BTreeSet::new();
        for distinct in [true, false] {
            for (index, item) in found.iter().enumerate() {
                if count < limit
                    && item.inherited == inherited
                    && !chosen[index]
                    && (!distinct || properties.insert(item.identity.property_id()))
                {
                    chosen[index] = true;
                    count += 1;
                }
            }
        }
    }
    found
        .into_iter()
        .zip(chosen)
        .filter_map(|(item, keep)| keep.then_some(item))
        .collect()
}
