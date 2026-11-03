//! Evidence report, recomputed from the plan and the hashed records every time; no stored
//! conclusion is copied. The report keeps mission outcome and safety invariants apart, states the
//! fraction of runs inside the declared validity envelope and refuses the status `valid` unless
//! the equivalence gate passed for this exact plan.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use serde::Serialize;
use serde_json::Value;

use crate::converge::{self, Convergence};
use crate::engine::Record;
use crate::plan::{Plan, Role};
use crate::spec::Design;
use crate::stats::{self, Moments, SobolIndex};

pub const SCHEMA: &str = "vv-exec-report.v1";
/// Largest number of cells listed one by one in the report.
pub const MAX_CELL_ROWS: usize = 10_000;
/// Variants checked for convergence when the analysis asks for it.
pub const CONVERGENCE_SAMPLE: usize = 4;

#[derive(Clone, Debug, Serialize)]
pub struct Rate {
    pub successes: u64,
    pub trials: u64,
    pub rate: f64,
    pub wilson: (f64, f64),
    pub clopper_pearson: (f64, f64),
}

fn rate(k: u64, n: u64, confidence: f64) -> Rate {
    Rate {
        successes: k,
        trials: n,
        rate: if n == 0 { 0.0 } else { k as f64 / n as f64 },
        wilson: stats::wilson(k, n, confidence),
        clopper_pearson: stats::clopper_pearson(k, n, confidence),
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ArmSummary {
    pub name: String,
    pub runs: u64,
    pub errors: u64,
    pub in_envelope_runs: u64,
    pub outcomes: BTreeMap<String, u64>,
    /// Landed with requirements and invariants met; absent for a domain without verdicts.
    pub all_pass: Option<Rate>,
    /// Safety invariants alone, separate from mission outcome.
    pub invariants_pass: Option<Rate>,
    pub metric: Option<Moments>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Comparison {
    pub baseline: String,
    pub arm: String,
    pub pairs: u64,
    pub both_pass: u64,
    pub baseline_only: u64,
    pub arm_only: u64,
    pub neither: u64,
    /// Exact McNemar test on the discordant pairs, two-sided.
    pub p_value: f64,
    /// Holm-adjusted over all comparisons in this report.
    pub p_holm: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct CellRow {
    pub cell: u32,
    pub values: Vec<f64>,
    pub arm: String,
    pub in_envelope: bool,
    pub all_pass: Option<Rate>,
    pub metric_mean: Option<f64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Sensitivity {
    pub arm: String,
    pub metric: String,
    pub parameters: Vec<String>,
    pub indices: Option<Vec<SobolIndex>>,
    pub note: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Report {
    pub schema: &'static str,
    pub status: &'static str,
    pub status_reason: String,
    pub experiment: String,
    pub domain: String,
    pub plan_sha256: String,
    pub source_sha256: String,
    pub confidence: f64,
    pub runs: u64,
    pub errors: u64,
    pub in_envelope_fraction: f64,
    pub extrapolated_runs: u64,
    pub metric: Option<String>,
    pub arms: Vec<ArmSummary>,
    pub comparisons: Vec<Comparison>,
    pub cells: Option<Vec<CellRow>>,
    pub sensitivity: Vec<Sensitivity>,
    pub convergence: Vec<(u32, Convergence)>,
    pub equivalence: Value,
}

fn metric_of(r: &Record, metric: Option<&str>) -> Option<f64> {
    metric.and_then(|m| r.metrics.get(m).copied())
}

/// Builds the report from the plan and its records; `out` supplies the equivalence result.
pub fn build(plan: &Plan, records: &[Record], out: &Path) -> Result<Report, String> {
    let e = &plan.experiment;
    let conf = e.analysis.confidence;
    let metric = e.analysis.metric.as_deref();
    // Only a domain with a verification artifact has verdicts.
    let verdicts = plan.domain.files().contains(&"verification.json");
    let arms_n = plan.arm_names.len();
    let mut arms: Vec<ArmSummary> = plan
        .arm_names
        .iter()
        .map(|n| ArmSummary {
            name: n.clone(),
            runs: 0,
            errors: 0,
            in_envelope_runs: 0,
            outcomes: BTreeMap::new(),
            all_pass: None,
            invariants_pass: None,
            metric: None,
        })
        .collect();
    let mut pass_counts = vec![(0u64, 0u64); arms_n];
    let mut metric_values: Vec<Vec<f64>> = vec![Vec::new(); arms_n];
    for r in records {
        let a = &mut arms[r.arm as usize];
        a.runs += 1;
        a.in_envelope_runs += u64::from(r.in_envelope);
        if r.error.is_some() {
            a.errors += 1;
            *a.outcomes.entry("error".into()).or_default() += 1;
            continue;
        }
        if let Some(o) = &r.outcome {
            *a.outcomes.entry(o.clone()).or_default() += 1;
        }
        let c = &mut pass_counts[r.arm as usize];
        c.0 += u64::from(r.all_pass == Some(true));
        c.1 += u64::from(r.invariants_pass == Some(true));
        if let Some(v) = metric_of(r, metric) {
            metric_values[r.arm as usize].push(v);
        }
    }
    for (i, a) in arms.iter_mut().enumerate() {
        // A run that produced no artifacts met nothing: errors count as failures of both.
        if verdicts && a.runs > 0 {
            a.all_pass = Some(rate(pass_counts[i].0, a.runs, conf));
            a.invariants_pass = Some(rate(pass_counts[i].1, a.runs, conf));
        }
        a.metric = stats::moments(&metric_values[i]);
    }

    // Paired comparisons: same cell, same replicate, hence the same seed, in two arms.
    let reps = e.seeds.as_ref().map_or(1, |s| s.count() as usize);
    let per_arm = plan.cells.len() * reps;
    let mut comparisons = Vec::new();
    if verdicts && arms_n > 1 {
        for a in 1..arms_n {
            let (mut both, mut base_only, mut arm_only, mut neither) = (0, 0, 0, 0);
            for j in 0..per_arm {
                let (x, y) = (&records[j], &records[a * per_arm + j]);
                if x.seed != y.seed || x.cell != y.cell {
                    return Err(format!(
                        "records {j} and {} are not paired",
                        a * per_arm + j
                    ));
                }
                let px = x.error.is_none() && x.all_pass == Some(true);
                let py = y.error.is_none() && y.all_pass == Some(true);
                match (px, py) {
                    (true, true) => both += 1,
                    (true, false) => base_only += 1,
                    (false, true) => arm_only += 1,
                    (false, false) => neither += 1,
                }
            }
            comparisons.push(Comparison {
                baseline: plan.arm_names[0].clone(),
                arm: plan.arm_names[a].clone(),
                pairs: per_arm as u64,
                both_pass: both,
                baseline_only: base_only,
                arm_only,
                neither,
                p_value: stats::mcnemar_exact(base_only, arm_only),
                p_holm: 0.0,
            });
        }
        let adj = stats::holm(&comparisons.iter().map(|c| c.p_value).collect::<Vec<_>>());
        for (c, p) in comparisons.iter_mut().zip(adj) {
            c.p_holm = p;
        }
    }

    // Per-variant aggregates: the failure map over the design and the Sobol inputs.
    let mut variant_mean: Vec<Option<f64>> = vec![None; plan.variants.len()];
    let mut variant_rate: Vec<Option<Rate>> = vec![None; plan.variants.len()];
    for v in &plan.variants {
        let i = v.index as usize;
        let recs = &records[i * reps..(i + 1) * reps];
        let vals: Vec<f64> = recs.iter().filter_map(|r| metric_of(r, metric)).collect();
        if vals.len() == reps {
            variant_mean[i] = Some(vals.iter().sum::<f64>() / reps as f64);
        }
        if verdicts {
            let k = recs
                .iter()
                .filter(|r| r.error.is_none() && r.all_pass == Some(true))
                .count() as u64;
            variant_rate[i] = Some(rate(k, reps as u64, conf));
        }
    }
    let cells =
        (!matches!(e.design, Design::Single) && plan.variants.len() <= MAX_CELL_ROWS).then(|| {
            plan.variants
                .iter()
                .map(|v| CellRow {
                    cell: v.cell,
                    values: plan.cells[v.cell as usize].values.clone(),
                    arm: plan.arm_names[v.arm as usize].clone(),
                    in_envelope: v.in_envelope,
                    all_pass: variant_rate[v.index as usize].clone(),
                    metric_mean: variant_mean[v.index as usize],
                })
                .collect()
        });

    let mut sensitivity = Vec::new();
    if let (Design::Saltelli { base_samples, seed }, Some(m)) = (&e.design, metric) {
        let n = *base_samples as usize;
        let d = e.parameters.len();
        for a in 0..arms_n {
            let base = a * plan.cells.len();
            let mut fa = vec![0.0; n];
            let mut fb = vec![0.0; n];
            let mut fab = vec![vec![0.0; n]; d];
            let mut missing = 0;
            for c in &plan.cells {
                let Some(y) = variant_mean[base + c.index as usize] else {
                    missing += 1;
                    continue;
                };
                match c.role {
                    Role::A { row } => fa[row as usize] = y,
                    Role::B { row } => fb[row as usize] = y,
                    Role::Ab { parameter, row } => fab[parameter as usize][row as usize] = y,
                    Role::Point => {}
                }
            }
            let (indices, note) = if missing > 0 {
                (
                    None,
                    Some(format!(
                        "{missing} cells lack the metric (a run failed or the metric is absent); indices not computed"
                    )),
                )
            } else {
                let i = stats::sobol(&fa, &fb, &fab, e.analysis.bootstrap, conf, *seed);
                let note = i
                    .is_none()
                    .then(|| "the metric has no variance".to_string());
                (i, note)
            };
            sensitivity.push(Sensitivity {
                arm: plan.arm_names[a].clone(),
                metric: m.to_string(),
                parameters: e.parameters.iter().map(|p| p.name.clone()).collect(),
                indices,
                note,
            });
        }
    }

    let mut convergence = Vec::new();
    if let Some(tol) = e.analysis.convergence_tolerance_m {
        let n = plan.variants.len();
        let k = CONVERGENCE_SAMPLE.min(n);
        let mut picks: Vec<u32> = (0..k)
            .map(|i| {
                if k == 1 {
                    0
                } else {
                    (i * (n - 1) / (k - 1)) as u32
                }
            })
            .collect();
        picks.dedup();
        for v in picks {
            let c = if plan.domain.id() == "rocket-rigid-body" {
                converge::rigid_body(&plan.case_of_variant(v)?, 4, tol)?
            } else {
                converge::not_applicable(converge::LANDING_FIXED_STEP, tol)
            };
            convergence.push((v, c));
        }
    }

    let equivalence: Value = fs::read(out.join("equivalence.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or(Value::Null);
    let (status, status_reason) = if equivalence.is_null() {
        ("unverified", "the equivalence gate has not run".to_string())
    } else if equivalence["plan_sha256"] != plan.plan_sha256.as_str() {
        (
            "unverified",
            "equivalence.json belongs to another plan".to_string(),
        )
    } else if equivalence["pass"] != true {
        (
            "invalid",
            "the equivalence gate found differences".to_string(),
        )
    } else {
        (
            "valid",
            format!(
                "equivalence gate passed on {} sampled runs",
                equivalence["cases"].as_array().map_or(0, Vec::len)
            ),
        )
    };
    let runs = records.len() as u64;
    let inside = records.iter().filter(|r| r.in_envelope).count() as u64;
    Ok(Report {
        schema: SCHEMA,
        status,
        status_reason,
        experiment: e.id.clone(),
        domain: e.domain.clone(),
        plan_sha256: plan.plan_sha256.clone(),
        source_sha256: plan.source_sha256.clone(),
        confidence: conf,
        runs,
        errors: records.iter().filter(|r| r.error.is_some()).count() as u64,
        in_envelope_fraction: if runs == 0 {
            0.0
        } else {
            inside as f64 / runs as f64
        },
        extrapolated_runs: runs - inside,
        metric: metric.map(String::from),
        arms,
        comparisons,
        cells,
        sensitivity,
        convergence,
        equivalence,
    })
}
