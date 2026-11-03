//! `vv-experiment.v1`: one file that defines an experiment. Everything is validated here, at the
//! boundary, before any planning or simulation: schema, names, units, ranges, seeds and limits.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::seeds::SeedSpec;

pub const SCHEMA: &str = "vv-experiment.v1";
pub const MAX_SPEC_BYTES: u64 = 1024 * 1024;
/// Hard ceilings. A specification may declare lower limits, never higher ones.
pub const MAX_RUNS: u64 = 2_000_000;
pub const MAX_CELLS: u64 = 200_000;
pub const MAX_ARMS: usize = 32;
pub const MAX_PARAMETERS: usize = 32;
pub const MAX_RETAINED: u64 = 20_000;
pub const MAX_ARTIFACT_BYTES: u64 = 16 * 1024 * 1024 * 1024;
pub const MAX_WALL_S: u64 = 86_400;
pub const MAX_THREADS: usize = 64;
pub const MAX_BOOTSTRAP: u32 = 10_000;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Experiment {
    pub schema: String,
    pub id: String,
    #[serde(default)]
    pub description: String,
    pub domain: String,
    /// Path of the base case, relative to the specification file.
    pub base_case: String,
    /// Named variants of the base case; one implicit arm `base` when empty.
    #[serde(default)]
    pub arms: Vec<Arm>,
    #[serde(default)]
    pub parameters: Vec<Parameter>,
    pub design: Design,
    /// Required for a seeded domain, refused for one without seeds.
    #[serde(default)]
    pub seeds: Option<SeedSpec>,
    /// Declared validity envelope. A run whose case leaves it is reported as extrapolation.
    #[serde(default)]
    pub envelope: Vec<Bound>,
    pub retention: Retention,
    pub limits: Limits,
    #[serde(default)]
    pub analysis: Analysis,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Arm {
    pub name: String,
    #[serde(default)]
    pub overrides: Vec<Override>,
}

/// Replaces the value at an existing JSON pointer of the base case.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Override {
    pub pointer: String,
    pub value: Value,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Scale {
    #[default]
    Linear,
    Log,
}

/// A numeric field of the case varied by the design between `low` and `high`.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Parameter {
    pub name: String,
    pub pointer: String,
    /// Must match the unit implied by the field name; `model` for a field whose unit and range
    /// the model itself defines (fault magnitudes, gains).
    pub unit: String,
    pub low: f64,
    pub high: f64,
    #[serde(default)]
    pub scale: Scale,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Design {
    /// The base case of each arm, without parameters.
    Single,
    /// Full factorial with `levels` evenly spaced values per parameter, ends included.
    Grid { levels: u32 },
    /// Latin hypercube with `samples` points.
    LatinHypercube { samples: u64, seed: u64 },
    /// Saltelli sampling for Sobol indices: matrices A and B of `base_samples` rows and one AB
    /// matrix per parameter, `base_samples x (parameters + 2)` cells.
    Saltelli { base_samples: u64, seed: u64 },
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Bound {
    pub pointer: String,
    pub low: f64,
    pub high: f64,
    /// Where the range comes from, for example a reference case or a document section.
    pub basis: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RetentionPolicy {
    None,
    Failures,
    Sample,
    FailuresAndSample,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Retention {
    pub policy: RetentionPolicy,
    /// For `sample`: retain the runs whose plan index is a multiple of this number.
    #[serde(default)]
    pub sample_every: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Limits {
    pub max_runs: u64,
    pub max_retained: u64,
    pub max_artifact_bytes: u64,
    pub max_wall_s: u64,
    #[serde(default)]
    pub max_threads: Option<usize>,
    /// Memory the scheduler may plan for, in MB. Default: what the machine reports as available.
    #[serde(default)]
    pub memory_budget_mb: Option<u64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Analysis {
    /// Metric for summaries and Sobol indices, for example `summary.propellant_used_kg`.
    #[serde(default)]
    pub metric: Option<String>,
    #[serde(default = "default_confidence")]
    pub confidence: f64,
    /// Bootstrap resamples for Sobol intervals; 0 disables them.
    #[serde(default)]
    pub bootstrap: u32,
}

impl Default for Analysis {
    fn default() -> Self {
        Self {
            metric: None,
            confidence: default_confidence(),
            bootstrap: 0,
        }
    }
}

fn default_confidence() -> f64 {
    0.95
}

fn valid_name(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.len() <= 64
        && (b[0].is_ascii_lowercase() || b[0].is_ascii_digit())
        && b.iter()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"._-".contains(c))
}

fn valid_pointer(p: &str) -> bool {
    p.starts_with('/') && p.len() > 1 && p.len() <= 256
}

/// Unit implied by the last named segment of a pointer, from the suffix convention of the case
/// files (`max_thrust_n`, `dry_mass_kg`, `position_m/2`). `None` when the name carries no unit.
pub fn unit_of(pointer: &str) -> Option<&'static str> {
    let name = pointer
        .rsplit('/')
        .find(|s| !s.is_empty() && !s.bytes().all(|c| c.is_ascii_digit()))?;
    // Longest suffix first, so `_mps2` is not read as `_s`.
    const SUFFIXES: &[(&str, &str)] = &[
        ("_fraction", "1"),
        ("_samples", "samples"),
        ("_epochs", "epochs"),
        ("_cycles", "cycles"),
        ("_kgpm3", "kg/m^3"),
        ("_radps", "rad/s"),
        ("_steps", "steps"),
        ("_kgm2", "kg*m^2"),
        ("_mps2", "m/s^2"),
        ("_mps", "m/s"),
        ("_rad", "rad"),
        ("_tan", "1"),
        ("_kg", "kg"),
        ("_m2", "m^2"),
        ("_m", "m"),
        ("_n", "N"),
        ("_s", "s"),
        ("_g", "g"),
    ];
    SUFFIXES
        .iter()
        .find(|(suffix, _)| name.ends_with(suffix))
        .map(|(_, unit)| *unit)
}

impl Experiment {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() as u64 > MAX_SPEC_BYTES {
            return Err(format!("specification exceeds {MAX_SPEC_BYTES} bytes"));
        }
        let e: Experiment =
            serde_json::from_slice(bytes).map_err(|e| format!("invalid specification: {e}"))?;
        e.validate()?;
        Ok(e)
    }

    /// Arms in plan order; one arm `base` when the specification declares none.
    pub fn arms(&self) -> Vec<Arm> {
        if self.arms.is_empty() {
            vec![Arm {
                name: "base".into(),
                overrides: Vec::new(),
            }]
        } else {
            self.arms.clone()
        }
    }

    /// Number of design cells, or an error when it exceeds the ceiling.
    pub fn cell_count(&self) -> Result<u64, String> {
        let d = self.parameters.len() as u64;
        let n = match &self.design {
            Design::Single => 1,
            Design::Grid { levels } => {
                let mut n: u64 = 1;
                for _ in 0..d {
                    n = n
                        .checked_mul(u64::from(*levels))
                        .filter(|n| *n <= MAX_CELLS)
                        .ok_or(format!("design: grid exceeds {MAX_CELLS} cells"))?;
                }
                n
            }
            Design::LatinHypercube { samples, .. } => *samples,
            Design::Saltelli { base_samples, .. } => base_samples
                .checked_mul(d + 2)
                .ok_or("design: Saltelli cell count overflows")?,
        };
        if n > MAX_CELLS {
            return Err(format!("design: {n} cells exceed {MAX_CELLS}"));
        }
        Ok(n)
    }

    /// Total runs: arms x cells x replicates.
    pub fn run_count(&self) -> Result<u64, String> {
        let reps = self.seeds.as_ref().map_or(1, SeedSpec::count);
        (self.arms().len() as u64)
            .checked_mul(self.cell_count()?)
            .and_then(|n| n.checked_mul(reps))
            .filter(|n| *n <= MAX_RUNS)
            .ok_or(format!("experiment exceeds {MAX_RUNS} runs"))
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.schema != SCHEMA {
            return Err(format!("schema must be {SCHEMA}"));
        }
        if !valid_name(&self.id) {
            return Err("id must be 1 to 64 characters of a-z, 0-9, '.', '_' or '-'".into());
        }
        let domain = crate::domain::by_id(&self.domain)
            .ok_or(format!("domain {:?} is not known", self.domain))?;
        if self.base_case.is_empty() || self.base_case.len() > 512 {
            return Err("base_case must be a path of 1 to 512 characters".into());
        }
        if self.arms.len() > MAX_ARMS {
            return Err(format!("arms: at most {MAX_ARMS}"));
        }
        let mut names: Vec<&str> = Vec::new();
        for (i, arm) in self.arms.iter().enumerate() {
            if !valid_name(&arm.name) {
                return Err(format!("arms[{i}].name is not a valid name"));
            }
            if names.contains(&arm.name.as_str()) {
                return Err(format!("arms[{i}].name {} appears twice", arm.name));
            }
            names.push(&arm.name);
            for (j, o) in arm.overrides.iter().enumerate() {
                if !valid_pointer(&o.pointer) {
                    return Err(format!("arms[{i}].overrides[{j}].pointer is not a pointer"));
                }
            }
        }
        if self.parameters.len() > MAX_PARAMETERS {
            return Err(format!("parameters: at most {MAX_PARAMETERS}"));
        }
        let mut pnames: Vec<&str> = Vec::new();
        for (i, p) in self.parameters.iter().enumerate() {
            let at = format!("parameters[{i}] ({})", p.name);
            if !valid_name(&p.name) || pnames.contains(&p.name.as_str()) {
                return Err(format!("{at}: name is invalid or repeated"));
            }
            pnames.push(&p.name);
            if !valid_pointer(&p.pointer) {
                return Err(format!("{at}: pointer is not a JSON pointer"));
            }
            if self.parameters[..i].iter().any(|q| q.pointer == p.pointer) {
                return Err(format!("{at}: pointer {} is varied twice", p.pointer));
            }
            if !(p.low.is_finite() && p.high.is_finite() && p.low < p.high) {
                return Err(format!("{at}: low and high must be finite with low < high"));
            }
            if p.scale == Scale::Log && p.low <= 0.0 {
                return Err(format!("{at}: a log scale needs low > 0"));
            }
            match unit_of(&p.pointer) {
                Some(u) if p.unit != u => {
                    return Err(format!(
                        "{at}: unit {:?} does not match {u:?}, the unit of {}",
                        p.unit, p.pointer
                    ));
                }
                None if p.unit != "model" => {
                    return Err(format!(
                        "{at}: {} carries no unit in its name; declare unit \"model\"",
                        p.pointer
                    ));
                }
                _ => {}
            }
        }
        match (&self.design, self.parameters.is_empty()) {
            (Design::Single, false) => {
                return Err("design single takes no parameters".into());
            }
            (Design::Single, true) => {}
            (_, true) => return Err("this design needs at least one parameter".into()),
            (Design::Grid { levels }, false) if !(2..=1000).contains(levels) => {
                return Err("design.levels must be in [2, 1000]".into());
            }
            (Design::LatinHypercube { samples: n, .. }, false)
            | (
                Design::Saltelli {
                    base_samples: n, ..
                },
                false,
            ) if *n < 2 => {
                return Err("design needs at least 2 samples".into());
            }
            _ => {}
        }
        match (&self.seeds, domain.seeded()) {
            (None, true) => return Err(format!("domain {} needs seeds", self.domain)),
            (Some(_), false) => {
                return Err(format!("domain {} takes no seeds", self.domain));
            }
            (Some(s), true) => s.validate(domain.protected())?,
            (None, false) => {}
        }
        for (i, b) in self.envelope.iter().enumerate() {
            if !valid_pointer(&b.pointer) {
                return Err(format!("envelope[{i}].pointer is not a JSON pointer"));
            }
            if !(b.low.is_finite() && b.high.is_finite() && b.low <= b.high) {
                return Err(format!(
                    "envelope[{i}]: low and high must be finite, low <= high"
                ));
            }
            if b.basis.trim().is_empty() {
                return Err(format!(
                    "envelope[{i}].basis must say where the range comes from"
                ));
            }
        }
        let r = &self.retention;
        let sampled = matches!(
            r.policy,
            RetentionPolicy::Sample | RetentionPolicy::FailuresAndSample
        );
        if sampled != (r.sample_every > 0) {
            return Err(
                "retention.sample_every must be positive exactly for a sample policy".into(),
            );
        }
        let l = &self.limits;
        let within = |v: u64, max: u64, name: &str| {
            if v == 0 || v > max {
                Err(format!("limits.{name} must be in [1, {max}], got {v}"))
            } else {
                Ok(())
            }
        };
        within(l.max_runs, MAX_RUNS, "max_runs")?;
        within(l.max_retained, MAX_RETAINED, "max_retained")?;
        within(
            l.max_artifact_bytes,
            MAX_ARTIFACT_BYTES,
            "max_artifact_bytes",
        )?;
        within(l.max_wall_s, MAX_WALL_S, "max_wall_s")?;
        if let Some(t) = l.max_threads {
            within(t as u64, MAX_THREADS as u64, "max_threads")?;
        }
        if let Some(m) = l.memory_budget_mb {
            within(m, 1 << 20, "memory_budget_mb")?;
        }
        let runs = self.run_count()?;
        if runs > l.max_runs {
            return Err(format!(
                "the design has {runs} runs, more than limits.max_runs = {}",
                l.max_runs
            ));
        }
        let a = &self.analysis;
        if !(a.confidence > 0.5 && a.confidence < 1.0) {
            return Err("analysis.confidence must be in (0.5, 1)".into());
        }
        if a.bootstrap > MAX_BOOTSTRAP {
            return Err(format!(
                "analysis.bootstrap must be at most {MAX_BOOTSTRAP}"
            ));
        }
        if matches!(self.design, Design::Saltelli { .. }) && a.metric.is_none() {
            return Err("a Saltelli design needs analysis.metric".into());
        }
        Ok(())
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub fn minimal() -> Value {
        serde_json::json!({
            "schema": "vv-experiment.v1",
            "id": "unit-test",
            "domain": "rocket-landing",
            "base_case": "case.json",
            "design": {"kind": "single"},
            "seeds": {"mode": "range", "first": 5000, "count": 4},
            "retention": {"policy": "none"},
            "limits": {"max_runs": 100, "max_retained": 10, "max_artifact_bytes": 1000000, "max_wall_s": 60}
        })
    }

    fn parse(v: &Value) -> Result<Experiment, String> {
        Experiment::parse(&serde_json::to_vec(v).unwrap())
    }

    #[test]
    fn a_minimal_specification_is_accepted() {
        let e = parse(&minimal()).unwrap();
        assert_eq!(e.run_count().unwrap(), 4);
        assert_eq!(e.arms()[0].name, "base");
    }

    #[test]
    fn unknown_fields_and_wrong_schema_are_refused() {
        let mut v = minimal();
        v["colour"] = "red".into();
        assert!(parse(&v).unwrap_err().contains("unknown field"));
        let mut v = minimal();
        v["schema"] = "vv-experiment.v0".into();
        assert!(parse(&v).is_err());
    }

    #[test]
    fn protected_seeds_refuse_the_specification() {
        let mut v = minimal();
        v["seeds"] = serde_json::json!({"mode": "list", "values": [5000, 3050]});
        assert!(parse(&v).unwrap_err().contains("protected"));
    }

    #[test]
    fn unit_must_match_the_field_name() {
        assert_eq!(unit_of("/vehicle/max_thrust_n"), Some("N"));
        assert_eq!(unit_of("/initial/position_m/2"), Some("m"));
        assert_eq!(unit_of("/environment/gravity_mps2"), Some("m/s^2"));
        assert_eq!(
            unit_of("/environment/atmosphere/density_kgpm3"),
            Some("kg/m^3")
        );
        assert_eq!(unit_of("/faults/0/magnitude"), None);
        let mut v = minimal();
        v["design"] = serde_json::json!({"kind": "grid", "levels": 3});
        v["parameters"] = serde_json::json!([
            {"name": "start", "pointer": "/faults/0/start_s", "unit": "m", "low": 1.0, "high": 2.0}
        ]);
        assert!(parse(&v).unwrap_err().contains("does not match"));
        v["parameters"][0]["unit"] = "s".into();
        parse(&v).unwrap();
        v["parameters"][0]["pointer"] = "/faults/0/magnitude".into();
        assert!(parse(&v).unwrap_err().contains("model"));
        v["parameters"][0]["unit"] = "model".into();
        parse(&v).unwrap();
    }

    #[test]
    fn run_count_above_the_declared_limit_is_refused() {
        let mut v = minimal();
        v["seeds"] = serde_json::json!({"mode": "range", "first": 10000, "count": 101});
        assert!(parse(&v).unwrap_err().contains("max_runs"));
    }

    #[test]
    fn limits_above_the_hard_ceilings_are_refused() {
        let mut v = minimal();
        v["limits"]["max_wall_s"] = (MAX_WALL_S + 1).into();
        assert!(parse(&v).is_err());
        let mut v = minimal();
        v["limits"]["max_retained"] = 0.into();
        assert!(parse(&v).is_err());
    }

    #[test]
    fn a_grid_cell_count_that_overflows_is_refused() {
        let mut v = minimal();
        v["design"] = serde_json::json!({"kind": "grid", "levels": 1000});
        let p: Vec<Value> = (0..4)
            .map(|i| serde_json::json!({"name": format!("p{i}"), "pointer": format!("/x{i}_m"), "unit": "m", "low": 0.0, "high": 1.0}))
            .collect();
        v["parameters"] = Value::Array(p);
        assert!(parse(&v).unwrap_err().contains("cells"));
    }

    #[test]
    fn saltelli_needs_a_metric_and_unseeded_domains_refuse_seeds() {
        let mut v = minimal();
        v["design"] = serde_json::json!({"kind": "saltelli", "base_samples": 4, "seed": 1});
        v["parameters"] = serde_json::json!([
            {"name": "a", "pointer": "/a_m", "unit": "m", "low": 0.0, "high": 1.0}
        ]);
        assert!(parse(&v).unwrap_err().contains("metric"));
        let mut v = minimal();
        v["domain"] = "rocket-rigid-body".into();
        assert!(parse(&v).unwrap_err().contains("takes no seeds"));
    }
}
