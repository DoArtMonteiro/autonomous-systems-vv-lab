//! Pipeline M6: cargas emparelhadas, corpus de contraexemplos, reprodução e
//! procura de classes novas por candidata.
//!
//! Todas as configurações correm as mesmas cargas com as mesmas sementes. As
//! cargas saem de um gerador semeado próprio e da base sem alterações, por isso
//! não dependem dos parâmetros da candidata.

use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

use autonomous_systems_vv_lab::ControllerEvaluationOutcome;
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;

use crate::atoms::Spec;
use crate::campaign::{Inputs, build_ctx};
use crate::eval::{Ctx, Params, Search, policy_name};
use crate::evidence::{
    Body, ConfigInfo, Counterexample, EVIDENCE_SCHEMA, Effective, Reduction, ReplayResult,
    ReplayStatus, Row, Signed, SuiteInfo, SuiteResults, Totals, label,
};
use crate::experiment::{ControllerConfig, Experiment};
use crate::identity;
use crate::io::{pretty_json, sha256_hex};
use crate::minimize::minimize;
use crate::recheck::recheck;
use crate::sampling::Refs;
use crate::workloads::{M6_SEED_DOMAIN, Split, Workload, workloads};

pub struct SuiteInputs {
    pub id: String,
    pub inputs: Inputs,
}

pub struct Loaded {
    pub experiment_bytes: Vec<u8>,
    pub experiment: Experiment,
    pub suites: Vec<SuiteInputs>,
}

pub struct Generated {
    pub files: Vec<(String, Vec<u8>)>,
    pub summary: String,
    /// Tempo de parede por configuração, medido fora da simulação; não entra na evidência.
    pub timing_ms: BTreeMap<String, u128>,
}

/// Resultado de uma suite. `effective` está alinhado com `Experiment::configs()`.
struct SuiteRun {
    info: SuiteInfo,
    loads: Vec<Workload>,
    results: SuiteResults,
    effective: Vec<Effective>,
    corpus: Vec<Counterexample>,
    introduced: Vec<Counterexample>,
}

fn params(config: &ControllerConfig, sim_seed: u64, minimize_budget: u32) -> Params {
    Params {
        search: Search::Uniform,
        campaign_seed: 0,
        sim_seed,
        policies: vec![config.policy],
        budget: 1,
        minimize_budget,
        max_failures: 1,
        mission_policy: MissionPolicy::default(),
    }
}

fn config_ctx(
    inputs: &Inputs,
    config: &ControllerConfig,
    sim_seed: u64,
    minimize_budget: u32,
) -> Result<Ctx, String> {
    let mut ctx = build_ctx(inputs, params(config, sim_seed, minimize_budget))?;
    ctx.base = config
        .overrides
        .apply(&ctx.base)
        .map_err(|error| format!("config '{}': {error}", config.id))?;
    ctx.actuator = config.overrides.apply_actuator(&ctx.actuator);
    Ok(ctx)
}

/// Primeira carga (por semente de simulação e índice) que viola cada classe.
fn first_occurrences<'w>(
    rows: &BTreeMap<String, Vec<Row>>,
    sim_seeds: &[u64],
    loads: &'w [Workload],
    split: Option<Split>,
) -> BTreeMap<String, (u64, &'w Workload)> {
    let mut first = BTreeMap::new();
    for seed in sim_seeds {
        for (workload, row) in loads.iter().zip(&rows[&seed.to_string()]) {
            if split.is_some_and(|wanted| workload.split != wanted) {
                continue;
            }
            for class in &row.violations {
                first.entry(class.clone()).or_insert((*seed, workload));
            }
        }
    }
    first
}

#[derive(Default)]
struct Lab {
    evaluations: u64,
    minimization_evaluations: u64,
    unidentified: u64,
    files: Vec<(String, Vec<u8>)>,
    timing_ms: BTreeMap<String, u128>,
}

impl Lab {
    fn evaluate(&mut self, ctx: &Ctx, spec: &Spec) -> Result<ControllerEvaluationOutcome, String> {
        self.evaluations += 1;
        ctx.run(spec, ctx.params.policies[0])
    }

    fn row(&mut self, ctx: &Ctx, spec: &Spec) -> Result<Row, String> {
        let outcome = self.evaluate(ctx, spec)?;
        let policy = policy_name(ctx.params.policies[0]);
        Ok(Row::from_outcome(&outcome, policy, &mut self.unidentified))
    }

    /// Reduz a falha `class` na configuração `found_on` e reproduz a entrada
    /// reduzida em todas. `contexts` está alinhado com `configs`.
    #[allow(clippy::too_many_arguments)]
    fn counterexample(
        &mut self,
        id: String,
        suite: &str,
        found_on: usize,
        workload: &Workload,
        class: &str,
        configs: &[&ControllerConfig],
        contexts: &[Ctx],
    ) -> Result<Counterexample, String> {
        let ctx = &contexts[found_on];
        let policy = ctx.params.policies[0];
        let find = |outcome: &ControllerEvaluationOutcome| {
            identity::violations(policy_name(policy), outcome)
                .into_iter()
                .find(|identity| label(identity) == class)
        };
        let spec = Spec {
            atoms: workload.atoms.clone(),
            steps: ctx.base.steps,
        };
        let original = self.evaluate(ctx, &spec)?;
        let identity = find(&original).ok_or_else(|| format!("{id}: {class} did not reproduce"))?;
        let reduced = minimize(ctx, policy, &spec, &identity)?;
        self.minimization_evaluations += u64::from(reduced.evaluations);
        let outcome = self.evaluate(ctx, &reduced.spec)?;
        let found = find(&outcome).ok_or_else(|| format!("{id}: reduced input lost {class}"))?;
        let (causal_trace, evidence) = crate::cases::causal_trace(
            &outcome,
            &found.kind,
            &found.property,
            found.violation_tick,
        );
        let check = recheck(
            &outcome.artifact.scenario,
            &outcome.artifact.expected_report,
            &ctx.contracts,
            &found,
        );
        let case_dir = format!("cases/{id}");
        let case = crate::cases::build(&case_dir, &outcome, &ctx.contracts)?;
        self.files.extend(case.files);
        let mut replay = BTreeMap::new();
        for (config, other) in configs.iter().zip(contexts) {
            let row = self.row(other, &reduced.spec)?;
            let result = ReplayResult {
                status: ReplayStatus::of(class, &row),
                violations: row.violations,
                mission: row.mission,
            };
            replay.insert(config.id.clone(), result);
        }
        Ok(Counterexample {
            id,
            suite: suite.to_owned(),
            found_on: configs[found_on].id.clone(),
            class: class.to_owned(),
            sim_seed: ctx.params.sim_seed,
            source_workload: workload.index,
            identity: found,
            atoms: reduced.spec.atoms.clone(),
            steps: reduced.spec.steps,
            reduction: Reduction {
                atoms_before: spec.atoms.len(),
                atoms_after: reduced.spec.atoms.len(),
                steps_before: spec.steps,
                steps_after: reduced.spec.steps,
                evaluations: reduced.evaluations,
                exhausted: reduced.exhausted,
                one_minimal_verified: reduced.one_minimal_verified,
            },
            recheck: check,
            evidence,
            causal_trace,
            case_dir,
            m4_sha256: case.m4_sha256,
            replay,
        })
    }

    /// Avalia todas as configurações nas cargas da suite, reduz o corpus da base
    /// (sementes de afinação) e as classes que só as candidatas mostram.
    fn run_suite(
        &mut self,
        experiment: &Experiment,
        suite: &SuiteInputs,
    ) -> Result<SuiteRun, String> {
        let budget = experiment.minimize_budget;
        let cap = experiment.max_corpus_per_suite as usize;
        let configs: Vec<&ControllerConfig> = experiment.configs().collect();
        let probe = build_ctx(&suite.inputs, params(configs[0], 0, budget))?;
        let mut refs = Refs::build(&probe.base, &probe.contracts, &BTreeSet::new());
        refs.biased = false;
        let loads = workloads(experiment, &refs);

        let mut results = BTreeMap::new();
        let mut effective = Vec::with_capacity(configs.len());
        // Semente de simulação -> contextos alinhados com `configs`.
        let mut contexts: BTreeMap<u64, Vec<Ctx>> = BTreeMap::new();
        for config in &configs {
            let started = Instant::now();
            let mut per_seed = BTreeMap::new();
            for sim_seed in &experiment.sim_seeds {
                let ctx = config_ctx(&suite.inputs, config, *sim_seed, budget)?;
                let mut rows = Vec::with_capacity(loads.len());
                for workload in &loads {
                    let spec = Spec {
                        atoms: workload.atoms.clone(),
                        steps: ctx.base.steps,
                    };
                    rows.push(self.row(&ctx, &spec)?);
                }
                per_seed.insert(sim_seed.to_string(), rows);
                contexts.entry(*sim_seed).or_default().push(ctx);
            }
            let latest = contexts.values().next().and_then(|row| row.last());
            effective.extend(latest.map(|ctx| Effective::of(&ctx.base, &ctx.actuator)));
            results.insert(config.id.clone(), per_seed);
            *self.timing_ms.entry(config.id.clone()).or_default() += started.elapsed().as_millis();
        }

        let seeds = &experiment.sim_seeds;
        let baseline_rows = &results[&experiment.baseline.id];
        let known = first_occurrences(baseline_rows, seeds, &loads, Some(Split::Tuning));
        let declared = experiment.suites.iter().find(|spec| spec.id == suite.id);
        let info = SuiteInfo {
            id: suite.id.clone(),
            description: declared
                .map(|spec| spec.description.clone())
                .unwrap_or_default(),
            scenario_name: probe.base.name.clone(),
            steps: probe.base.steps,
            scenario_sha256: sha256_hex(&suite.inputs.scenario),
            contracts_sha256: sha256_hex(&suite.inputs.contracts),
            actuator_sha256: sha256_hex(&suite.inputs.actuator),
            actuator_source: if suite.inputs.actuator_from_file {
                "file"
            } else {
                "default_identity"
            },
            corpus_classes_found: known.len(),
            corpus_classes_dropped: known.len().saturating_sub(cap),
        };

        let mut corpus = Vec::new();
        for (number, (class, (seed, workload))) in known.into_iter().take(cap).enumerate() {
            let id = format!("corpus/{}/{:02}", suite.id, number + 1);
            corpus.push(self.counterexample(
                id,
                &suite.id,
                0,
                workload,
                &class,
                &configs,
                &contexts[&seed],
            )?);
        }

        // Classes introduzidas: vistas numa candidata e nunca na base, em nenhuma carga.
        let baseline_classes: BTreeSet<String> =
            first_occurrences(baseline_rows, seeds, &loads, None)
                .into_keys()
                .collect();
        let mut introduced = Vec::new();
        for (position, candidate) in configs.iter().enumerate().skip(1) {
            let novel = first_occurrences(&results[&candidate.id], seeds, &loads, None)
                .into_iter()
                .filter(|(class, _)| !baseline_classes.contains(class))
                .take(cap);
            for (number, (class, (seed, workload))) in novel.enumerate() {
                let id = format!("introduced/{}/{}/{:02}", suite.id, candidate.id, number + 1);
                introduced.push(self.counterexample(
                    id,
                    &suite.id,
                    position,
                    workload,
                    &class,
                    &configs,
                    &contexts[&seed],
                )?);
            }
        }
        Ok(SuiteRun {
            info,
            loads,
            results,
            effective,
            corpus,
            introduced,
        })
    }
}

fn input_files(loaded: &Loaded) -> Vec<(String, Vec<u8>)> {
    let mut files = vec![(
        "inputs/experiment.json".to_owned(),
        loaded.experiment_bytes.clone(),
    )];
    for suite in &loaded.suites {
        let prefix = format!("inputs/suites/{}", suite.id);
        let inputs = &suite.inputs;
        files.push((format!("{prefix}/scenario.json"), inputs.scenario.clone()));
        files.push((format!("{prefix}/contracts.json"), inputs.contracts.clone()));
        files.push((format!("{prefix}/actuator.json"), inputs.actuator.clone()));
    }
    files
}

pub fn generate(loaded: &Loaded) -> Result<Generated, String> {
    let experiment = &loaded.experiment;
    experiment.validate()?;
    let configs: Vec<&ControllerConfig> = experiment.configs().collect();
    let mut lab = Lab::default();
    let mut suites = Vec::new();
    let mut all_workloads = BTreeMap::new();
    let mut results = BTreeMap::new();
    let mut corpus = Vec::new();
    let mut introduced = Vec::new();
    let mut effective: Vec<BTreeMap<String, Effective>> =
        configs.iter().map(|_| BTreeMap::new()).collect();
    for suite in &loaded.suites {
        let run = lab.run_suite(experiment, suite)?;
        for (index, value) in run.effective.into_iter().enumerate() {
            effective[index].insert(suite.id.clone(), value);
        }
        all_workloads.insert(suite.id.clone(), run.loads);
        results.insert(suite.id.clone(), run.results);
        corpus.extend(run.corpus);
        introduced.extend(run.introduced);
        suites.push(run.info);
    }

    let mut config_infos = Vec::new();
    for (config, effective) in configs.iter().zip(effective) {
        config_infos.push(ConfigInfo {
            id: &config.id,
            policy: policy_name(config.policy),
            overrides: &config.overrides,
            rationale: &config.rationale,
            role: config.role,
            expect: &config.expect,
            config_sha256: sha256_hex(&pretty_json(config)?),
            changes_oracle: config.overrides.confidence_threshold_permille.is_some()
                || config.overrides.max_observation_age_ticks.is_some(),
            effective,
        });
    }
    let body = Body {
        schema: EVIDENCE_SCHEMA,
        experiment,
        experiment_sha256: sha256_hex(&loaded.experiment_bytes),
        source_sha256: autonomous_systems_vv_lab::source_sha256(),
        seed_domain: format!("{M6_SEED_DOMAIN:#018x}"),
        sampling: "uniform fresh_set per seed; each draw also projected per fault family",
        suites,
        configs: config_infos,
        totals: Totals {
            evaluations: lab.evaluations,
            minimization_evaluations: lab.minimization_evaluations,
            workloads: all_workloads.values().map(Vec::len).sum(),
            corpus: corpus.len(),
            introduced: introduced.len(),
            unidentified_violations: lab.unidentified,
        },
        workloads: all_workloads,
        results,
        corpus,
        introduced,
    };
    let hash = sha256_hex(&pretty_json(&body)?);
    let evidence = pretty_json(&Signed {
        body: &body,
        evidence_sha256: hash.clone(),
    })?;
    let totals = &body.totals;
    let summary = format!(
        "vv-repair run: suites={} configs={} workloads={} evaluations={} minimization_evaluations={} corpus={} introduced={} unidentified_violations={} evidence_sha256={hash}",
        body.suites.len(),
        body.configs.len(),
        totals.workloads,
        totals.evaluations,
        totals.minimization_evaluations,
        totals.corpus,
        totals.introduced,
        totals.unidentified_violations,
    );
    let mut files = vec![("evidence.json".to_owned(), evidence)];
    files.extend(input_files(loaded));
    files.append(&mut lab.files);
    Ok(Generated {
        files,
        summary,
        timing_ms: lab.timing_ms,
    })
}
