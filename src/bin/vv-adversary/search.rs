//! Controlo e pesquisa em duas fases (A: aleatória enviesada; B: mutação).

use std::collections::BTreeSet;

use autonomous_systems_vv_lab::prng::XorShift64Star;

use crate::atoms::Spec;
use crate::eval::{Ctx, PolicySummary, Search, summarize};
use crate::sampling::{self, Refs};

pub const ADVERSARY_SEED_DOMAIN: u64 = 0x4144_5652_2d4d_3501;
pub const TOP_K: usize = 4;
const UNIQUE_RETRIES: usize = 20;

pub fn splitmix64(mut value: u64) -> u64 {
    value = value.wrapping_add(0x9e37_79b9_7f4a_7c15);
    value = (value ^ (value >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    value = (value ^ (value >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    value ^ (value >> 31)
}

pub fn rng_for(campaign_seed: u64) -> XorShift64Star {
    XorShift64Star::new(splitmix64(
        campaign_seed ^ splitmix64(ADVERSARY_SEED_DOMAIN),
    ))
}

pub struct Candidate {
    pub index: usize,
    pub phase: &'static str,
    pub parent: Option<usize>,
    pub spec: Spec,
    /// Um resumo por política, pela ordem de `params.policies`.
    pub results: Vec<PolicySummary>,
}

impl Candidate {
    pub fn failing(&self) -> bool {
        self.results
            .iter()
            .any(|r| !r.identities.is_empty() || r.unidentified_violations > 0)
    }

    pub fn risk(&self) -> u64 {
        self.results.iter().map(|r| r.risk).sum()
    }
}

pub struct Control {
    pub results: Vec<PolicySummary>,
    /// Ticks onde a ação ou o estado mudam no controlo (âncoras de fronteira).
    pub ticks: BTreeSet<u32>,
}

pub fn control(ctx: &Ctx) -> Result<Control, String> {
    let spec = Spec {
        atoms: Vec::new(),
        steps: ctx.base.steps,
    };
    let mut results = Vec::new();
    let mut ticks = BTreeSet::new();
    for policy in &ctx.params.policies {
        let outcome = ctx.run(&spec, *policy)?;
        let telemetry = &outcome.artifact.expected_report.telemetry;
        for pair in telemetry.windows(2) {
            if pair[0].action.heading.is_some() != pair[1].action.heading.is_some() {
                ticks.insert(pair[1].tick);
            }
        }
        if let Some(tick) = outcome.mission.completion_tick {
            ticks.insert(tick);
            ticks.insert(tick + 1);
        }
        for transition in &outcome.artifact.expected_report.transitions {
            ticks.insert(transition.tick);
        }
        results.push(summarize(*policy, &outcome));
    }
    Ok(Control { results, ticks })
}

pub fn evaluate_all(ctx: &Ctx, spec: &Spec) -> Result<Vec<PolicySummary>, String> {
    ctx.params
        .policies
        .iter()
        .map(|policy| Ok(summarize(*policy, &ctx.run(spec, *policy)?)))
        .collect()
}

/// Os `TOP_K` candidatos sem violações com maior risco (empates: índice menor).
fn parents(candidates: &[Candidate]) -> Vec<usize> {
    let mut pool: Vec<&Candidate> = candidates.iter().filter(|c| !c.failing()).collect();
    pool.sort_by(|a, b| b.risk().cmp(&a.risk()).then(a.index.cmp(&b.index)));
    pool.into_iter().take(TOP_K).map(|c| c.index).collect()
}

/// `biased` e `uniform` usam só candidatos novos, sem mutação guiada pelo risco.
pub fn phase_a_candidates(ctx: &Ctx) -> u32 {
    match ctx.params.search {
        Search::Guided => ctx.params.budget.div_ceil(2),
        Search::Biased | Search::Uniform => ctx.params.budget,
    }
}

pub fn run(ctx: &Ctx, refs: &Refs) -> Result<Vec<Candidate>, String> {
    let budget = ctx.params.budget as usize;
    let phase_a_count = phase_a_candidates(ctx) as usize;
    let mut rng = rng_for(ctx.params.campaign_seed);
    let mut candidates: Vec<Candidate> = Vec::with_capacity(budget);
    let mut seen = BTreeSet::new();
    for index in 0..budget {
        let mut parent = None;
        if index >= phase_a_count {
            let top = parents(&candidates);
            if !top.is_empty() {
                parent = Some(top[rng.inclusive_u32(0, top.len() as u32 - 1) as usize]);
            }
        }
        let mut spec = None;
        for attempt in 0..=UNIQUE_RETRIES {
            let atoms = match parent {
                Some(p) => sampling::mutate(&mut rng, refs, &candidates[p].spec.atoms),
                None => sampling::fresh_set(&mut rng, refs),
            };
            let candidate = Spec {
                atoms,
                steps: ctx.base.steps,
            };
            if seen.insert(candidate.key()) || attempt == UNIQUE_RETRIES {
                spec = Some(candidate);
                break;
            }
        }
        let spec = spec.expect("loop always assigns on the last attempt");
        let results = evaluate_all(ctx, &spec)?;
        candidates.push(Candidate {
            index,
            phase: if parent.is_some() { "B" } else { "A" },
            parent,
            spec,
            results,
        });
    }
    Ok(candidates)
}
