//! Planner: the experiment specification and the base case to a total order of runs. Every case
//! the plan will run is built and passed through the canonical validation of its domain here,
//! before any simulation, so a forbidden combination is refused with the parameter that caused it.

use std::path::Path;

use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::domain::{Domain, by_id};
use crate::prng::{SplitMix64, mix};
use crate::spec::{Design, Experiment, Parameter, Scale};

pub const PLAN_SCHEMA: &str = "vv-exec-plan.v1";

/// Position of a design cell in a Saltelli layout.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "matrix", rename_all = "snake_case")]
pub enum Role {
    Point,
    A { row: u64 },
    B { row: u64 },
    Ab { parameter: u32, row: u64 },
}

/// Points of the design in the unit hypercube, one row per cell, and the role of each cell.
pub fn unit_points(design: &Design, d: usize) -> (Vec<Vec<f64>>, Vec<Role>) {
    match design {
        Design::Single => (vec![Vec::new()], vec![Role::Point]),
        Design::Grid { levels } => {
            let l = *levels as usize;
            let n = l.pow(d as u32);
            let mut pts = Vec::with_capacity(n);
            for mut k in 0..n {
                let mut row = vec![0.0; d];
                // Last parameter varies fastest.
                for j in (0..d).rev() {
                    row[j] = (k % l) as f64 / (l - 1) as f64;
                    k /= l;
                }
                pts.push(row);
            }
            (pts, vec![Role::Point; n])
        }
        Design::LatinHypercube { samples, seed } => {
            let n = *samples as usize;
            let mut pts = vec![vec![0.0; d]; n];
            for j in 0..d {
                let mut g = SplitMix64::new(seed ^ mix(j as u64 + 1));
                let mut perm: Vec<usize> = (0..n).collect();
                for i in (1..n).rev() {
                    perm.swap(i, g.below(i as u64 + 1) as usize);
                }
                for (i, row) in pts.iter_mut().enumerate() {
                    row[j] = (perm[i] as f64 + g.next_f64()) / n as f64;
                }
            }
            (pts, vec![Role::Point; n])
        }
        Design::Saltelli { base_samples, seed } => {
            let n = *base_samples as usize;
            let mut g = SplitMix64::new(*seed);
            let mut draw = || -> Vec<Vec<f64>> {
                (0..n)
                    .map(|_| (0..d).map(|_| g.next_f64()).collect())
                    .collect()
            };
            let a = draw();
            let b = draw();
            let mut pts = Vec::with_capacity(n * (d + 2));
            let mut roles = Vec::with_capacity(n * (d + 2));
            for (r, row) in a.iter().enumerate() {
                pts.push(row.clone());
                roles.push(Role::A { row: r as u64 });
            }
            for (r, row) in b.iter().enumerate() {
                pts.push(row.clone());
                roles.push(Role::B { row: r as u64 });
            }
            for i in 0..d {
                for r in 0..n {
                    let mut row = a[r].clone();
                    row[i] = b[r][i];
                    pts.push(row);
                    roles.push(Role::Ab {
                        parameter: i as u32,
                        row: r as u64,
                    });
                }
            }
            (pts, roles)
        }
    }
}

/// Unit coordinate to a parameter value.
pub fn scale(p: &Parameter, u: f64) -> f64 {
    match p.scale {
        Scale::Linear => p.low + (p.high - p.low) * u,
        Scale::Log => (p.low.ln() + (p.high.ln() - p.low.ln()) * u).exp(),
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct Cell {
    pub index: u32,
    pub role: Role,
    /// One value per parameter, in specification order.
    pub values: Vec<f64>,
}

/// One arm applied to one cell: the case that runs, identified by its hash.
#[derive(Clone, Debug, Serialize)]
pub struct Variant {
    pub index: u32,
    pub arm: u32,
    pub cell: u32,
    pub case_sha256: String,
    pub in_envelope: bool,
    /// Envelope bounds the case leaves, as `pointer = value`.
    pub outside: Vec<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct RunRef {
    pub index: u64,
    pub variant: u32,
    pub replicate: u32,
    pub seed: u64,
}

pub struct Plan {
    pub experiment: Experiment,
    pub domain: &'static dyn Domain,
    pub spec_sha256: String,
    pub base_case_sha256: String,
    pub source_sha256: String,
    pub arm_names: Vec<String>,
    pub cells: Vec<Cell>,
    pub variants: Vec<Variant>,
    pub runs: Vec<RunRef>,
    pub plan_sha256: String,
    spec_bytes: Vec<u8>,
    base_bytes: Vec<u8>,
    base_value: Value,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

/// Sets an existing value of `doc`; never creates a field the base case lacks.
/// Which kind of number a parameter writes: none (an arm override), a float or an integer.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Numeric {
    No,
    Float,
    Integer,
}

fn set(doc: &mut Value, pointer: &str, value: Value, numeric: Numeric) -> Result<(), String> {
    let slot = doc
        .pointer_mut(pointer)
        .ok_or(format!("{pointer} does not exist in the base case"))?;
    match (numeric, &*slot) {
        (Numeric::No, _) => {}
        (Numeric::Float, Value::Number(n)) if n.is_f64() => {}
        (Numeric::Integer, Value::Number(n)) if !n.is_f64() => {}
        (Numeric::Float, Value::Number(_)) => {
            return Err(format!(
                "{pointer} is an integer field; declare the parameter integer"
            ));
        }
        (Numeric::Integer, Value::Number(_)) => {
            return Err(format!(
                "{pointer} is a floating-point field; the parameter must not be integer"
            ));
        }
        _ => return Err(format!("{pointer} is not a number in the base case")),
    }
    *slot = value;
    Ok(())
}

/// A parameter value as written into a case: rounded for an integer field, snapped to the
/// declared quantum otherwise.
pub fn snap(p: &Parameter, v: f64) -> f64 {
    if p.integer {
        v.round()
    } else if let Some(q) = p.quantum {
        (v / q).round() * q
    } else {
        v
    }
}

/// Sets each parameter value in `doc` and returns the case bytes as the planner writes them:
/// pretty JSON and a final newline. Integer parameters are rounded to the nearest integer.
pub fn apply_parameters(
    mut doc: Value,
    parameters: &[Parameter],
    values: &[f64],
) -> Result<Vec<u8>, String> {
    for (p, &v) in parameters.iter().zip(values) {
        let v = snap(p, v);
        let (value, kind) = if p.integer {
            (Value::from(v as i64), Numeric::Integer)
        } else {
            let n = serde_json::Number::from_f64(v).ok_or("non-finite parameter value")?;
            (Value::Number(n), Numeric::Float)
        };
        set(&mut doc, &p.pointer, value, kind).map_err(|e| format!("parameter {}: {e}", p.name))?;
    }
    let mut bytes = serde_json::to_vec_pretty(&doc).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}

impl Plan {
    /// Builds and validates the plan. `spec_bytes` are hashed as given; `base_dir` resolves
    /// `base_case`.
    pub fn build(spec_bytes: &[u8], base_dir: &Path) -> Result<Self, String> {
        let experiment = Experiment::parse(spec_bytes)?;
        let base_path = base_dir.join(&experiment.base_case);
        let base_bytes = read_capped(&base_path, 256 * 1024)?;
        Self::from_parts(experiment, spec_bytes, base_bytes)
    }

    pub fn from_parts(
        experiment: Experiment,
        spec_bytes: &[u8],
        base_bytes: Vec<u8>,
    ) -> Result<Self, String> {
        let domain = by_id(&experiment.domain).ok_or("unknown domain")?;
        let base_value: Value = serde_json::from_slice(&base_bytes)
            .map_err(|e| format!("base case is not JSON: {e}"))?;
        let arms = experiment.arms();
        let d = experiment.parameters.len();
        let (points, roles) = unit_points(&experiment.design, d);
        let cells: Vec<Cell> = points
            .iter()
            .zip(roles)
            .enumerate()
            .map(|(i, (u, role))| Cell {
                index: i as u32,
                role,
                values: experiment
                    .parameters
                    .iter()
                    .zip(u)
                    .map(|(p, &x)| scale(p, x))
                    .collect(),
            })
            .collect();
        let key = u64::from_le_bytes(
            Sha256::digest(experiment.id.as_bytes())[..8]
                .try_into()
                .expect("8 bytes"),
        );
        let seeds = experiment.seeds.clone();
        let common: Option<Vec<u64>> = seeds
            .as_ref()
            .filter(|s| s.is_common())
            .map(|s| s.seeds_for(key, 0));
        let mut plan = Plan {
            spec_sha256: sha256_hex(spec_bytes),
            base_case_sha256: sha256_hex(&base_bytes),
            source_sha256: domain.source_sha256(),
            arm_names: arms.iter().map(|a| a.name.clone()).collect(),
            domain,
            cells,
            variants: Vec::new(),
            runs: Vec::with_capacity(experiment.run_count()? as usize),
            plan_sha256: String::new(),
            experiment,
            spec_bytes: spec_bytes.to_vec(),
            base_bytes,
            base_value,
        };
        let mut digest = Sha256::new();
        digest.update(PLAN_SCHEMA.as_bytes());
        for h in [
            &plan.spec_sha256,
            &plan.base_case_sha256,
            &plan.source_sha256,
        ] {
            digest.update(h.as_bytes());
        }
        for a in 0..arms.len() {
            for c in 0..plan.cells.len() {
                let vi = plan.variants.len() as u32;
                let bytes = plan.case_of(a as u32, c as u32)?;
                let cell_seeds = match (&seeds, &common) {
                    (None, _) => vec![0],
                    (Some(_), Some(s)) => s.clone(),
                    (Some(s), None) => s.seeds_for(key, c as u64),
                };
                if seeds.is_some() {
                    for &s in &cell_seeds {
                        crate::seeds::check(domain.protected(), s)?;
                    }
                }
                // Canonical validation of every case before any simulation. The seed matters
                // only for dispersion draws, so the first one stands for all.
                domain.validate(&bytes, cell_seeds[0]).map_err(|e| {
                    format!(
                        "arm {} cell {c} {}: refused by the model: {e}",
                        plan.arm_names[a],
                        plan.describe_cell(c)
                    )
                })?;
                let (in_envelope, outside) = plan.envelope_of(&bytes)?;
                let case_sha256 = sha256_hex(&bytes);
                digest.update(case_sha256.as_bytes());
                digest.update([u8::from(in_envelope)]);
                for (r, &seed) in cell_seeds.iter().enumerate() {
                    digest.update(vi.to_le_bytes());
                    digest.update(seed.to_le_bytes());
                    plan.runs.push(RunRef {
                        index: plan.runs.len() as u64,
                        variant: vi,
                        replicate: r as u32,
                        seed,
                    });
                }
                plan.variants.push(Variant {
                    index: vi,
                    arm: a as u32,
                    cell: c as u32,
                    case_sha256,
                    in_envelope,
                    outside,
                });
            }
        }
        plan.plan_sha256 = hex(&digest.finalize());
        Ok(plan)
    }

    pub fn spec_bytes(&self) -> &[u8] {
        &self.spec_bytes
    }

    pub fn base_bytes(&self) -> &[u8] {
        &self.base_bytes
    }

    fn describe_cell(&self, c: usize) -> String {
        let parts: Vec<String> = self
            .experiment
            .parameters
            .iter()
            .zip(&self.cells[c].values)
            .map(|(p, v)| format!("{} = {v} {} at {}", p.name, p.unit, p.pointer))
            .collect();
        if parts.is_empty() {
            "(base)".into()
        } else {
            format!("({})", parts.join(", "))
        }
    }

    /// Case bytes of an arm on a cell. With no override and no parameter, the base case bytes
    /// exactly as read, so a plain run hashes like the canonical case file.
    pub fn case_of(&self, arm: u32, cell: u32) -> Result<Vec<u8>, String> {
        let arms = self.experiment.arms();
        let a = &arms[arm as usize];
        if a.overrides.is_empty() && self.experiment.parameters.is_empty() {
            return Ok(self.base_bytes.clone());
        }
        let mut doc = self.base_value.clone();
        for o in &a.overrides {
            set(&mut doc, &o.pointer, o.value.clone(), Numeric::No)
                .map_err(|e| format!("arm {}: {e}", a.name))?;
        }
        apply_parameters(
            doc,
            &self.experiment.parameters,
            &self.cells[cell as usize].values,
        )
    }

    pub fn case_of_variant(&self, v: u32) -> Result<Vec<u8>, String> {
        let var = &self.variants[v as usize];
        self.case_of(var.arm, var.cell)
    }

    fn envelope_of(&self, case: &[u8]) -> Result<(bool, Vec<String>), String> {
        if self.experiment.envelope.is_empty() {
            return Ok((true, Vec::new()));
        }
        let doc: Value = serde_json::from_slice(case).map_err(|e| e.to_string())?;
        let mut outside = Vec::new();
        for b in &self.experiment.envelope {
            let v = doc
                .pointer(&b.pointer)
                .and_then(Value::as_f64)
                .ok_or(format!("envelope pointer {} is not a number", b.pointer))?;
            if !(b.low..=b.high).contains(&v) {
                outside.push(format!("{} = {v}", b.pointer));
            }
        }
        Ok((outside.is_empty(), outside))
    }

    /// Plan description written next to the records; enough to check a resume and a report.
    pub fn manifest(&self) -> Value {
        serde_json::json!({
            "schema": PLAN_SCHEMA,
            "engine": concat!("vv-exec ", env!("CARGO_PKG_VERSION")),
            "experiment": self.experiment.id,
            "domain": self.experiment.domain,
            "spec_sha256": self.spec_sha256,
            "base_case_sha256": self.base_case_sha256,
            "source_sha256": self.source_sha256,
            "plan_sha256": self.plan_sha256,
            "arms": self.arm_names,
            "parameters": self.experiment.parameters.iter().map(|p| &p.name).collect::<Vec<_>>(),
            "cells": self.cells.len(),
            "variants": self.variants.len(),
            "runs": self.runs.len(),
            "in_envelope_variants": self.variants.iter().filter(|v| v.in_envelope).count(),
        })
    }
}

pub fn read_capped(path: &Path, cap: u64) -> Result<Vec<u8>, String> {
    let meta = std::fs::metadata(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if meta.len() > cap {
        return Err(format!("{} exceeds {cap} bytes", path.display()));
    }
    std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grid_points_cover_both_ends_in_a_fixed_order() {
        let (p, _) = unit_points(&Design::Grid { levels: 3 }, 2);
        assert_eq!(p.len(), 9);
        assert_eq!(p[0], [0.0, 0.0]);
        assert_eq!(p[1], [0.0, 0.5]);
        assert_eq!(p[8], [1.0, 1.0]);
    }

    #[test]
    fn latin_hypercube_has_one_point_per_stratum_in_each_dimension() {
        let n = 50;
        let (p, _) = unit_points(
            &Design::LatinHypercube {
                samples: n,
                seed: 9,
            },
            3,
        );
        for j in 0..3 {
            let mut strata: Vec<usize> = p.iter().map(|r| (r[j] * n as f64) as usize).collect();
            strata.sort_unstable();
            assert_eq!(strata, (0..n as usize).collect::<Vec<_>>());
        }
    }

    #[test]
    fn saltelli_ab_rows_take_one_column_from_b() {
        let (p, roles) = unit_points(
            &Design::Saltelli {
                base_samples: 4,
                seed: 3,
            },
            3,
        );
        assert_eq!(p.len(), 4 * 5);
        let (a, b) = (&p[0..4], &p[4..8]);
        for i in 0..3 {
            for r in 0..4 {
                let ab = &p[8 + i * 4 + r];
                assert_eq!(
                    roles[8 + i * 4 + r],
                    Role::Ab {
                        parameter: i as u32,
                        row: r as u64
                    }
                );
                for k in 0..3 {
                    assert_eq!(ab[k], if k == i { b[r][k] } else { a[r][k] });
                }
            }
        }
    }

    #[test]
    fn log_scale_maps_the_ends_and_the_midpoint_geometrically() {
        let p = Parameter {
            name: "x".into(),
            pointer: "/x_m".into(),
            unit: "m".into(),
            low: 1.0,
            high: 100.0,
            scale: Scale::Log,
            integer: false,
            quantum: None,
        };
        assert!((scale(&p, 0.0) - 1.0).abs() < 1e-12);
        assert!((scale(&p, 0.5) - 10.0).abs() < 1e-9);
        assert!((scale(&p, 1.0) - 100.0).abs() < 1e-9);
    }
}
