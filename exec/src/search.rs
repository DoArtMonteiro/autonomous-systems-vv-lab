//! M14 falsification search: domain-independent strategies that look for inputs violating the
//! properties of a domain, under a fixed evaluation budget. The search knows parameters, seeds,
//! violation names and, optionally, one numeric metric. It knows no physics.
//!
//! Strategies:
//! - `random`: uniform points and seeds;
//! - `halton`: a Halton sequence with a random shift per repetition (Cranley and Patterson);
//! - `extremes`: every corner of the box and the centre first, then uniform points, the classic
//!   worst-case testing heuristic;
//! - `adaptive`: robustness-guided local search with restarts, a (1+1) evolution strategy on the
//!   objective metric, in the family of S-TaLiRo and Breach falsification.
//!
//! Points live on an integer lattice, `q / 2^32` per unit coordinate, so a logged point is read
//! back exactly: `serde_json` here runs without `float_roundtrip` and may round a float by one unit
//! in the last place. Every evaluation is logged with its point, seed, case hash and result, and
//! `verify` recomputes every one of them. A counterexample is a point and a seed whose run violates the target; its
//! class is the exact set of violated properties. Minimisation moves each coordinate back towards
//! the nominal case while the class and the seed stay the same.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::domain::{Domain, by_id};
use crate::plan::{apply_parameters, read_capped, scale, sha256_hex};
use crate::prng::{SplitMix64, mix};
use crate::spec::{MAX_THREADS, Parameter, validate_parameters};

pub const SCHEMA: &str = "vv-search.v1";
pub const RESULT_SCHEMA: &str = "vv-search-result.v1";
pub const MAX_BUDGET: u32 = 100_000;
pub const MAX_REPETITIONS: u32 = 1_000;
pub const MAX_TOTAL: u64 = 2_000_000;
pub const MAX_MINIMISE: u32 = 1_000;
/// Counterexample classes minimised per repetition.
pub const MAX_MINIMISED: usize = 8;
const MAX_SPEC_BYTES: u64 = 1024 * 1024;
const MAX_CASE_BYTES: u64 = 4 * 1024 * 1024;
/// Lattice resolution: a unit coordinate is `q / Q` with `q` in `[0, Q]`.
pub const Q: u64 = 1 << 32;
/// The first 32 primes: one Halton base per parameter.
const PRIMES: [u32; 32] = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97,
    101, 103, 107, 109, 113, 127, 131,
];

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Target {
    /// A failed safety invariant or contract (`invariants_pass == false`).
    Safety,
    /// Any failed verdict, mission outcome included (`all_pass == false`).
    Any,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    /// Smaller values are closer to a violation.
    Minimise,
    Maximise,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Objective {
    pub metric: String,
    pub direction: Direction,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Strategy {
    Random,
    Halton,
    Extremes,
    Adaptive {
        /// Uniform points drawn at the start of each episode.
        initial: u32,
        /// Initial step, in unit coordinates.
        sigma: f64,
        /// Steps without improvement before a restart.
        patience: u32,
    },
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SeedPool {
    pub low: u64,
    pub high: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SearchLimits {
    pub max_evaluations: u64,
    pub max_wall_s: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SearchSpec {
    pub schema: String,
    pub id: String,
    #[serde(default)]
    pub description: String,
    pub domain: String,
    /// Path of the base case, relative to the specification file.
    pub base_case: String,
    pub parameters: Vec<Parameter>,
    pub seed_pool: SeedPool,
    pub target: Target,
    #[serde(default)]
    pub objective: Option<Objective>,
    pub strategy: Strategy,
    pub budget: u32,
    pub repetitions: u32,
    pub search_seed: u64,
    pub minimise_budget: u32,
    pub limits: SearchLimits,
}

impl SearchSpec {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() as u64 > MAX_SPEC_BYTES {
            return Err(format!("specification exceeds {MAX_SPEC_BYTES} bytes"));
        }
        let s: SearchSpec =
            serde_json::from_slice(bytes).map_err(|e| format!("invalid search: {e}"))?;
        s.validate()?;
        Ok(s)
    }

    pub fn domain(&self) -> Result<&'static dyn Domain, String> {
        by_id(&self.domain).ok_or(format!("unknown domain {}", self.domain))
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema != SCHEMA {
            return Err(format!("schema must be {SCHEMA}"));
        }
        if self.id.is_empty()
            || self.id.len() > 64
            || !self
                .id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
        {
            return Err("id must be 1 to 64 letters, digits, '-' or '_'".into());
        }
        let domain = self.domain()?;
        if !domain.seeded() || !domain.has_verdicts() {
            return Err("a search needs a seeded domain with verdicts".into());
        }
        if self.parameters.is_empty() {
            return Err("a search needs at least one parameter".into());
        }
        validate_parameters(&self.parameters)?;
        if self.seed_pool.low > self.seed_pool.high {
            return Err("seed_pool.low must not exceed seed_pool.high".into());
        }
        crate::seeds::check_span(domain.protected(), self.seed_pool.low, self.seed_pool.high)?;
        if !(1..=MAX_BUDGET).contains(&self.budget) {
            return Err(format!("budget must be in [1, {MAX_BUDGET}]"));
        }
        if !(1..=MAX_REPETITIONS).contains(&self.repetitions) {
            return Err(format!("repetitions must be in [1, {MAX_REPETITIONS}]"));
        }
        if self.minimise_budget > MAX_MINIMISE {
            return Err(format!("minimise_budget must be at most {MAX_MINIMISE}"));
        }
        let worst = u64::from(self.repetitions)
            * (u64::from(self.budget) + MAX_MINIMISED as u64 * u64::from(self.minimise_budget));
        if worst > self.limits.max_evaluations || self.limits.max_evaluations > MAX_TOTAL {
            return Err(format!(
                "limits.max_evaluations must cover repetitions x (budget + {MAX_MINIMISED} x minimise_budget) = {worst} and stay at most {MAX_TOTAL}"
            ));
        }
        if !(1..=crate::spec::MAX_WALL_S).contains(&self.limits.max_wall_s) {
            return Err("limits.max_wall_s is out of range".into());
        }
        if let Some(o) = &self.objective
            && (o.metric.is_empty() || o.metric.len() > 128)
        {
            return Err("objective.metric must be 1 to 128 characters".into());
        }
        if let Strategy::Adaptive {
            initial,
            sigma,
            patience,
        } = self.strategy
        {
            if self.objective.is_none() {
                return Err("the adaptive strategy needs an objective".into());
            }
            if initial == 0 || patience == 0 || !(sigma > 0.0 && sigma <= 1.0) {
                return Err("adaptive needs initial > 0, patience > 0 and sigma in (0, 1]".into());
            }
        }
        if let Strategy::Extremes = self.strategy
            && self.parameters.len() > 16
        {
            return Err("extremes enumerates 2^d corners; at most 16 parameters".into());
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Search,
    Minimise,
}

/// One logged evaluation. Recomputable from the specification, the base case, `u` and `seed`.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Evaluation {
    pub repetition: u32,
    pub index: u32,
    pub phase: Phase,
    /// Lattice coordinates of the point, one per parameter: `u = q / Q`.
    pub q: Vec<u64>,
    pub seed: u64,
    pub case_sha256: String,
    pub error: Option<String>,
    pub trace_sha256: Option<String>,
    pub outcome: Option<String>,
    pub violated: bool,
    pub violations: Vec<String>,
    pub objective: Option<f64>,
}

impl Evaluation {
    pub fn class(&self) -> String {
        self.violations.join("+")
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Counterexample {
    pub class: String,
    /// Search evaluation (1-based) that first found the class.
    pub found_at: u32,
    pub seed: u64,
    pub q: Vec<u64>,
    pub values: Vec<f64>,
    /// After minimisation towards the nominal case, with the same class and seed.
    pub minimised_q: Vec<u64>,
    pub minimised_values: Vec<f64>,
    /// Largest distance from the nominal case over the coordinates, in unit coordinates.
    pub deviation_before: f64,
    pub deviation_after: f64,
    /// Coordinates that still differ from the nominal case after minimisation.
    pub active_parameters: Vec<String>,
    pub minimise_evaluations: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct RepetitionResult {
    pub repetition: u32,
    pub evaluations: u32,
    pub errors: u32,
    /// Search evaluation (1-based) of the first violation; `None` when the budget found none.
    pub first_violation: Option<u32>,
    pub classes: Vec<Counterexample>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct SearchResult {
    pub schema: String,
    pub engine: String,
    pub id: String,
    pub domain: String,
    pub spec_sha256: String,
    pub base_case_sha256: String,
    pub source_sha256: String,
    pub log_sha256: String,
    pub nominal_q: Vec<u64>,
    pub repetitions: Vec<RepetitionResult>,
    pub total_evaluations: u64,
    pub wall_s: f64,
}

/// Unit coordinate of a value, clamped to the box.
fn unit_of_value(p: &Parameter, v: f64) -> f64 {
    let u = match p.scale {
        crate::spec::Scale::Linear => (v - p.low) / (p.high - p.low),
        crate::spec::Scale::Log => (v.ln() - p.low.ln()) / (p.high.ln() - p.low.ln()),
    };
    if u.is_finite() {
        u.clamp(0.0, 1.0)
    } else {
        0.0
    }
}

/// The nominal point: the base case values on the lattice, clamped to the box.
pub fn nominal(base: &Value, parameters: &[Parameter]) -> Result<Vec<u64>, String> {
    parameters
        .iter()
        .map(|p| {
            base.pointer(&p.pointer)
                .and_then(Value::as_f64)
                .map(|v| to_q(unit_of_value(p, v)))
                .ok_or(format!("{} is not a number in the base case", p.pointer))
        })
        .collect()
}

pub fn to_q(u: f64) -> u64 {
    (u.clamp(0.0, 1.0) * Q as f64).round() as u64
}

pub fn to_u(q: &[u64]) -> Vec<f64> {
    // Exact: Q is a power of two.
    q.iter().map(|&x| x as f64 / Q as f64).collect()
}

/// Radical inverse of `i` in base `b`: the Halton coordinate.
fn radical_inverse(mut i: u64, b: u32) -> f64 {
    let b = u64::from(b);
    let (mut f, mut r) = (1.0, 0.0);
    while i > 0 {
        f /= b as f64;
        r += f * (i % b) as f64;
        i /= b;
    }
    r
}

fn normal(g: &mut SplitMix64) -> f64 {
    // Box-Muller; 1 - u keeps the logarithm finite.
    let u1 = 1.0 - g.next_f64();
    let u2 = g.next_f64();
    (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
}

/// Everything one evaluation needs, shared by the search and the verification.
pub struct Context<'a> {
    pub spec: &'a SearchSpec,
    pub domain: &'static dyn Domain,
    pub base: Value,
}

impl Context<'_> {
    pub fn values(&self, q: &[u64]) -> Vec<f64> {
        self.spec
            .parameters
            .iter()
            .zip(to_u(q))
            .map(|(p, x)| {
                let v = scale(p, x);
                if p.integer { v.round() } else { v }
            })
            .collect()
    }

    pub fn evaluate(
        &self,
        rep: u32,
        index: u32,
        phase: Phase,
        q: Vec<u64>,
        seed: u64,
    ) -> Evaluation {
        let mut e = Evaluation {
            repetition: rep,
            index,
            phase,
            q,
            seed,
            case_sha256: String::new(),
            error: None,
            trace_sha256: None,
            outcome: None,
            violated: false,
            violations: Vec::new(),
            objective: None,
        };
        let case =
            match apply_parameters(self.base.clone(), &self.spec.parameters, &self.values(&e.q)) {
                Ok(c) => c,
                Err(m) => {
                    e.error = Some(m);
                    return e;
                }
            };
        e.case_sha256 = sha256_hex(&case);
        match self.domain.run(&case, seed) {
            Ok(o) => {
                e.violated = match self.spec.target {
                    Target::Safety => o.invariants_pass == Some(false),
                    Target::Any => o.all_pass() == Some(false),
                };
                if e.violated {
                    e.violations = match self.spec.target {
                        Target::Safety => o
                            .violations
                            .iter()
                            .filter(|v| !v.starts_with("requirement:"))
                            .cloned()
                            .collect(),
                        Target::Any => {
                            let mut v = o.violations.clone();
                            if o.mission_success == Some(false) {
                                v.push(format!("outcome:{}", o.outcome));
                            }
                            v.sort();
                            v.dedup();
                            v
                        }
                    };
                    if e.violations.is_empty() {
                        e.violations.push("unidentified".into());
                    }
                }
                e.objective = self.spec.objective.as_ref().and_then(|ob| {
                    o.metrics.get(&ob.metric).map(|&v| match ob.direction {
                        Direction::Minimise => v,
                        Direction::Maximise => -v,
                    })
                });
                e.trace_sha256 = Some(o.trace_sha256);
                e.outcome = Some(o.outcome);
            }
            Err(m) => e.error = Some(m.to_string()),
        }
        e
    }
}

/// First search evaluation (1-based), point and seed of a class.
type Found = (u32, Vec<u64>, u64);

struct Rep<'a> {
    ctx: &'a Context<'a>,
    rep: u32,
    g: SplitMix64,
    log: Vec<Evaluation>,
    classes: BTreeMap<String, Found>,
    first: Option<u32>,
}

impl Rep<'_> {
    fn seed(&mut self) -> u64 {
        let pool = self.ctx.spec.seed_pool;
        pool.low + self.g.below(pool.high - pool.low + 1)
    }

    fn uniform(&mut self) -> Vec<u64> {
        (0..self.ctx.spec.parameters.len())
            .map(|_| self.g.below(Q + 1))
            .collect()
    }

    fn eval(&mut self, q: Vec<u64>, seed: u64) -> Evaluation {
        let index = self.log.len() as u32;
        let e = self.ctx.evaluate(self.rep, index, Phase::Search, q, seed);
        if e.violated {
            self.first.get_or_insert(index + 1);
            self.classes
                .entry(e.class())
                .or_insert((index + 1, e.q.clone(), seed));
        }
        self.log.push(e.clone());
        e
    }

    fn budget_left(&self) -> bool {
        (self.log.len() as u32) < self.ctx.spec.budget
    }

    fn run(&mut self) {
        let d = self.ctx.spec.parameters.len();
        match self.ctx.spec.strategy.clone() {
            Strategy::Random => {
                while self.budget_left() {
                    let (u, s) = (self.uniform(), self.seed());
                    self.eval(u, s);
                }
            }
            Strategy::Halton => {
                let shift = self.uniform();
                let mut i = 1u64;
                while self.budget_left() {
                    let u = (0..d)
                        .map(|k| {
                            to_q(
                                (radical_inverse(i, PRIMES[k]) + shift[k] as f64 / Q as f64)
                                    .fract(),
                            )
                        })
                        .collect();
                    let s = self.seed();
                    self.eval(u, s);
                    i += 1;
                }
            }
            Strategy::Extremes => {
                let mut fixed: Vec<Vec<u64>> = (0..1u64 << d)
                    .map(|m| (0..d).map(|k| ((m >> k) & 1) * Q).collect())
                    .collect();
                fixed.push(vec![Q / 2; d]);
                for u in fixed {
                    if !self.budget_left() {
                        return;
                    }
                    let s = self.seed();
                    self.eval(u, s);
                }
                while self.budget_left() {
                    let (u, s) = (self.uniform(), self.seed());
                    self.eval(u, s);
                }
            }
            Strategy::Adaptive {
                initial,
                sigma,
                patience,
            } => self.adaptive(initial, sigma, patience),
        }
    }

    /// Episodes of uniform sampling followed by a (1+1) evolution strategy from the best point,
    /// with the one-fifth success rule on the step. An episode ends on a new class or after
    /// `patience` steps without improvement; the next one starts from fresh uniform points.
    fn adaptive(&mut self, initial: u32, sigma0: f64, patience: u32) {
        let d = self.ctx.spec.parameters.len();
        while self.budget_left() {
            let mut best: Option<Evaluation> = None;
            let known = self.classes.len();
            for _ in 0..initial {
                if !self.budget_left() {
                    return;
                }
                let (u, s) = (self.uniform(), self.seed());
                let e = self.eval(u, s);
                if !e.violated
                    && e.error.is_none()
                    && let Some(v) = e.objective
                    && best
                        .as_ref()
                        .is_none_or(|b| v < b.objective.unwrap_or(f64::INFINITY))
                {
                    best = Some(e);
                }
            }
            if self.classes.len() > known {
                continue;
            }
            let Some(mut best) = best else { continue };
            let mut step = sigma0;
            let mut stall = 0;
            while self.budget_left() && stall < patience {
                let u: Vec<u64> = (0..d)
                    .map(|k| to_q(best.q[k] as f64 / Q as f64 + step * normal(&mut self.g)))
                    .collect();
                let known = self.classes.len();
                let e = self.eval(u, best.seed);
                if self.classes.len() > known {
                    break;
                }
                match e.objective {
                    Some(v) if !e.violated && v < best.objective.unwrap_or(f64::INFINITY) => {
                        best = e;
                        step = (step * 1.5).min(1.0);
                        stall = 0;
                    }
                    _ => {
                        step = (step * 0.87).max(1e-4);
                        stall += 1;
                    }
                }
            }
        }
    }

    /// Moves each coordinate of a counterexample towards the nominal point by bisection, keeping
    /// the class and the seed. Coordinates are visited in parameter order; each one is first tried
    /// at its nominal value.
    fn minimise(&mut self, class: &str, q: &[u64], seed: u64, nominal: &[u64]) -> (Vec<u64>, u32) {
        let budget = self.ctx.spec.minimise_budget;
        let mut cur = q.to_vec();
        let mut used = 0u32;
        let keeps = |me: &mut Self, cand: &[u64], used: &mut u32| -> bool {
            *used += 1;
            let index = me.log.len() as u32;
            let e = me
                .ctx
                .evaluate(me.rep, index, Phase::Minimise, cand.to_vec(), seed);
            let ok = e.violated && e.class() == class;
            me.log.push(e);
            ok
        };
        for k in 0..cur.len() {
            if used >= budget {
                break;
            }
            if cur[k] == nominal[k] {
                continue;
            }
            let mut cand = cur.clone();
            cand[k] = nominal[k];
            if keeps(self, &cand, &mut used) {
                cur = cand;
                continue;
            }
            // Bisection on t = j / 256 in [0, 1]: t = 1 keeps the class, t = 0 (nominal) does not.
            let (mut lo, mut hi) = (0i128, 256i128);
            let (near, far) = (i128::from(nominal[k]), i128::from(cur[k]));
            let at = |j: i128| (near + (far - near) * j / 256) as u64;
            while hi - lo > 1 && used < budget {
                let mid = (lo + hi) / 2;
                let mut cand = cur.clone();
                cand[k] = at(mid);
                if keeps(self, &cand, &mut used) {
                    hi = mid;
                } else {
                    lo = mid;
                }
            }
            cur[k] = at(hi);
        }
        (cur, used)
    }
}

/// Largest coordinate distance between two lattice points, in unit coordinates.
fn deviation(q: &[u64], nominal: &[u64]) -> f64 {
    q.iter()
        .zip(nominal)
        .map(|(&a, &b)| a.abs_diff(b) as f64 / Q as f64)
        .fold(0.0, f64::max)
}

pub fn run_repetition(
    ctx: &Context,
    rep: u32,
    nominal: &[u64],
) -> (RepetitionResult, Vec<Evaluation>) {
    use sha2::Digest;
    let key = u64::from_le_bytes(
        sha2::Sha256::digest(ctx.spec.id.as_bytes())[..8]
            .try_into()
            .expect("8 bytes"),
    );
    let mut r = Rep {
        ctx,
        rep,
        g: SplitMix64::new(mix(ctx.spec.search_seed ^ mix(key ^ u64::from(rep)))),
        log: Vec::new(),
        classes: BTreeMap::new(),
        first: None,
    };
    r.run();
    let search_evals = r.log.len() as u32;
    let mut found: Vec<(String, Found)> = r.classes.clone().into_iter().collect();
    found.sort_by_key(|(_, (at, _, _))| *at);
    let mut classes = Vec::new();
    for (i, (class, (at, q, seed))) in found.into_iter().enumerate() {
        let (mq, used) = if i < MAX_MINIMISED && ctx.spec.minimise_budget > 0 {
            r.minimise(&class, &q, seed, nominal)
        } else {
            (q.clone(), 0)
        };
        let active = ctx
            .spec
            .parameters
            .iter()
            .zip(mq.iter().zip(nominal))
            .filter(|(_, (a, b))| a != b)
            .map(|(p, _)| p.name.clone())
            .collect();
        classes.push(Counterexample {
            values: ctx.values(&q),
            minimised_values: ctx.values(&mq),
            deviation_before: deviation(&q, nominal),
            deviation_after: deviation(&mq, nominal),
            class,
            found_at: at,
            seed,
            q,
            minimised_q: mq,
            active_parameters: active,
            minimise_evaluations: used,
        });
    }
    let errors = r.log.iter().filter(|e| e.error.is_some()).count() as u32;
    (
        RepetitionResult {
            repetition: rep,
            evaluations: search_evals,
            errors,
            first_violation: r.first,
            classes,
        },
        r.log,
    )
}

pub fn log_line(e: &Evaluation) -> String {
    let json = serde_json::to_string(e).expect("an evaluation always serialises");
    format!("{} {json}\n", sha256_hex(json.as_bytes()))
}

pub fn parse_log(text: &str) -> Result<Vec<Evaluation>, String> {
    text.lines()
        .enumerate()
        .map(|(i, line)| {
            let (hash, json) = line
                .split_once(' ')
                .ok_or(format!("log line {} has no hash", i + 1))?;
            if sha256_hex(json.as_bytes()) != hash {
                return Err(format!("log line {} does not match its hash", i + 1));
            }
            serde_json::from_str(json).map_err(|e| format!("log line {}: {e}", i + 1))
        })
        .collect()
}

/// Parses a specification and its base case and checks the nominal case and the upper corner
/// with the canonical validation, before any search.
pub fn load(spec_bytes: &[u8], base_bytes: &[u8]) -> Result<(SearchSpec, Value), String> {
    let spec = SearchSpec::parse(spec_bytes)?;
    let base: Value =
        serde_json::from_slice(base_bytes).map_err(|e| format!("base case is not JSON: {e}"))?;
    let domain = spec.domain()?;
    let ctx = Context {
        spec: &spec,
        domain,
        base: base.clone(),
    };
    for u in [
        nominal(&base, &spec.parameters)?,
        vec![Q; spec.parameters.len()],
    ] {
        let case = apply_parameters(base.clone(), &spec.parameters, &ctx.values(&u))?;
        domain
            .validate(&case, spec.seed_pool.low)
            .map_err(|e| format!("refused by the model: {e}"))?;
    }
    Ok((spec, base))
}

pub fn read_inputs(spec_path: &Path) -> Result<(Vec<u8>, Vec<u8>), String> {
    let spec_bytes = read_capped(spec_path, MAX_SPEC_BYTES)?;
    let spec = SearchSpec::parse(&spec_bytes)?;
    let dir = spec_path.parent().unwrap_or(Path::new("."));
    let base_bytes = read_capped(&dir.join(&spec.base_case), MAX_CASE_BYTES)?;
    Ok((spec_bytes, base_bytes))
}

/// Runs every repetition, in parallel across repetitions, and writes `spec.json`,
/// `base-case.json`, `evaluations.jsonl` and `search.json` into a new directory.
pub fn execute(
    spec_bytes: &[u8],
    base_bytes: &[u8],
    out: &Path,
    threads: usize,
) -> Result<SearchResult, String> {
    crate::engine::guard_output(out)?;
    if out.exists() {
        return Err(format!("{} already exists", out.display()));
    }
    let (spec, base) = load(spec_bytes, base_bytes)?;
    let domain = spec.domain()?;
    let nominal_q = nominal(&base, &spec.parameters)?;
    let ctx = Context {
        spec: &spec,
        domain,
        base,
    };
    let start = Instant::now();
    let next = AtomicUsize::new(0);
    type Slot = Option<(RepetitionResult, Vec<Evaluation>)>;
    let slots: Mutex<Vec<Slot>> = Mutex::new(vec![None; spec.repetitions as usize]);
    let failed: Mutex<Option<String>> = Mutex::new(None);
    let logical = std::thread::available_parallelism().map_or(1, |n| n.get());
    std::thread::scope(|scope| {
        for _ in 0..threads.clamp(1, logical.min(MAX_THREADS)) {
            scope.spawn(|| {
                loop {
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    if i >= spec.repetitions as usize {
                        return;
                    }
                    if start.elapsed().as_secs() >= spec.limits.max_wall_s {
                        *failed.lock().unwrap_or_else(|p| p.into_inner()) =
                            Some("limits.max_wall_s reached before every repetition ran".into());
                        return;
                    }
                    let r = run_repetition(&ctx, i as u32, &nominal_q);
                    slots.lock().unwrap_or_else(|p| p.into_inner())[i] = Some(r);
                }
            });
        }
    });
    if let Some(e) = failed.into_inner().unwrap_or_else(|p| p.into_inner()) {
        return Err(e);
    }
    let mut log = String::new();
    let mut reps = Vec::new();
    let mut total = 0u64;
    for slot in slots.into_inner().unwrap_or_else(|p| p.into_inner()) {
        let (r, evals) = slot.ok_or("a repetition did not run")?;
        total += evals.len() as u64;
        for e in &evals {
            log.push_str(&log_line(e));
        }
        reps.push(r);
    }
    if total > spec.limits.max_evaluations {
        return Err("limits.max_evaluations exceeded".into());
    }
    let result = SearchResult {
        schema: RESULT_SCHEMA.into(),
        engine: concat!("vv-exec ", env!("CARGO_PKG_VERSION")).into(),
        id: spec.id.clone(),
        domain: spec.domain.clone(),
        spec_sha256: sha256_hex(spec_bytes),
        base_case_sha256: sha256_hex(base_bytes),
        source_sha256: domain.source_sha256(),
        log_sha256: sha256_hex(log.as_bytes()),
        nominal_q,
        repetitions: reps,
        total_evaluations: total,
        wall_s: start.elapsed().as_secs_f64(),
    };
    fs::create_dir_all(out).map_err(|e| format!("{}: {e}", out.display()))?;
    crate::engine::write_new(&out.join("spec.json"), spec_bytes)?;
    crate::engine::write_new(&out.join("base-case.json"), base_bytes)?;
    crate::engine::write_new(&out.join("evaluations.jsonl"), log.as_bytes())?;
    let mut bytes = serde_json::to_vec_pretty(&result).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    crate::engine::write_new(&out.join("search.json"), &bytes)?;
    Ok(result)
}

#[derive(Clone, Debug, Serialize)]
pub struct SearchVerification {
    pub evaluations: u64,
    /// `repetition:index` of each logged evaluation that differs when recomputed.
    pub mismatches: Vec<String>,
    /// Repetitions whose summary differs from the one rebuilt by a fresh search.
    pub summary_mismatches: Vec<u32>,
    pub hashes_match: bool,
    pub source_sha256_match: bool,
    pub pass: bool,
}

fn same_eval(a: &Evaluation, b: &Evaluation) -> bool {
    let mut a2 = a.clone();
    let mut b2 = b.clone();
    a2.objective = None;
    b2.objective = None;
    a2 == b2
        && match (a.objective, b.objective) {
            (None, None) => true,
            (Some(x), Some(y)) => (x - y).abs() <= 1e-15 * x.abs().max(y.abs()),
            _ => false,
        }
}

fn to_value<T: Serialize>(v: &T) -> Value {
    serde_json::to_value(v).expect("serialisable")
}

/// Equal JSON values, floats to one part in 10^15 (a stored float may be read back one unit in the
/// last place away), everything else exactly.
fn same_json(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(x), Value::Number(y)) if x.is_f64() || y.is_f64() => {
            match (x.as_f64(), y.as_f64()) {
                (Some(x), Some(y)) => x == y || (x - y).abs() <= 1e-15 * x.abs().max(y.abs()),
                _ => false,
            }
        }
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(a, b)| same_json(a, b))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len()
                && x.iter()
                    .zip(y)
                    .all(|((ka, va), (kb, vb))| ka == kb && same_json(va, vb))
        }
        _ => a == b,
    }
}

/// Recomputes a search directory: every logged evaluation is re-run in process from its point and
/// seed, and every repetition is searched again from scratch; both must match the stored log and
/// summary. Nothing stored is trusted.
pub fn verify(out: &Path, threads: usize) -> Result<SearchVerification, String> {
    let spec_bytes = read_capped(&out.join("spec.json"), MAX_SPEC_BYTES)?;
    let base_bytes = read_capped(&out.join("base-case.json"), MAX_CASE_BYTES)?;
    let log_bytes = fs::read(out.join("evaluations.jsonl")).map_err(|e| e.to_string())?;
    let stored: SearchResult =
        serde_json::from_slice(&read_capped(&out.join("search.json"), 256 * 1024 * 1024)?)
            .map_err(|e| format!("search.json: {e}"))?;
    let (spec, base) = load(&spec_bytes, &base_bytes)?;
    let domain = spec.domain()?;
    let text = String::from_utf8(log_bytes.clone()).map_err(|_| "log is not UTF-8")?;
    let logged = parse_log(&text)?;
    let nominal_q = nominal(&base, &spec.parameters)?;
    let ctx = Context {
        spec: &spec,
        domain,
        base,
    };
    let next = AtomicUsize::new(0);
    let bad = Mutex::new(Vec::new());
    let logical = std::thread::available_parallelism().map_or(1, |n| n.get());
    std::thread::scope(|scope| {
        for _ in 0..threads.clamp(1, logical.min(MAX_THREADS)) {
            scope.spawn(|| {
                loop {
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    let Some(e) = logged.get(i) else { return };
                    let again = ctx.evaluate(e.repetition, e.index, e.phase, e.q.clone(), e.seed);
                    if !same_eval(&again, e) {
                        bad.lock()
                            .unwrap_or_else(|p| p.into_inner())
                            .push(format!("{}:{}", e.repetition, e.index));
                    }
                }
            });
        }
    });
    let mut mismatches = bad.into_inner().unwrap_or_else(|p| p.into_inner());
    mismatches.sort();
    let next = AtomicUsize::new(0);
    let bad = Mutex::new(Vec::new());
    std::thread::scope(|scope| {
        for _ in 0..threads.clamp(1, logical.min(MAX_THREADS)) {
            scope.spawn(|| {
                loop {
                    let rep = next.fetch_add(1, Ordering::Relaxed) as u32;
                    if rep >= spec.repetitions {
                        return;
                    }
                    let (r, _) = run_repetition(&ctx, rep, &nominal_q);
                    let same = stored
                        .repetitions
                        .get(rep as usize)
                        .is_some_and(|s| same_json(&to_value(s), &to_value(&r)));
                    if !same {
                        bad.lock().unwrap_or_else(|p| p.into_inner()).push(rep);
                    }
                }
            });
        }
    });
    let mut summary_mismatches = bad.into_inner().unwrap_or_else(|p| p.into_inner());
    summary_mismatches.sort_unstable();
    let hashes_match = stored.log_sha256 == sha256_hex(&log_bytes)
        && stored.spec_sha256 == sha256_hex(&spec_bytes)
        && stored.base_case_sha256 == sha256_hex(&base_bytes)
        && stored.nominal_q == nominal_q
        && stored.repetitions.len() == spec.repetitions as usize;
    let source_sha256_match = stored.source_sha256 == domain.source_sha256();
    Ok(SearchVerification {
        evaluations: logged.len() as u64,
        pass: mismatches.is_empty()
            && summary_mismatches.is_empty()
            && hashes_match
            && source_sha256_match
            && logged.len() as u64 == stored.total_evaluations,
        mismatches,
        summary_mismatches,
        hashes_match,
        source_sha256_match,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn radical_inverse_matches_the_halton_definition() {
        assert_eq!(radical_inverse(1, 2), 0.5);
        assert_eq!(radical_inverse(3, 2), 0.75);
        assert!((radical_inverse(5, 3) - (2.0 / 3.0 + 1.0 / 9.0)).abs() < 1e-15);
    }

    #[test]
    fn deviation_is_the_largest_coordinate_distance() {
        assert_eq!(deviation(&[Q / 4, Q], &[0, Q / 2]), 0.5);
    }

    #[test]
    fn the_lattice_round_trips_through_json_exactly() {
        let q = vec![0, 1, Q / 3, Q - 1, Q];
        let text = serde_json::to_string(&q).unwrap();
        let back: Vec<u64> = serde_json::from_str(&text).unwrap();
        assert_eq!(back, q);
        assert_eq!(to_u(&[Q / 2]), vec![0.5]);
        assert_eq!(to_q(1.5), Q);
    }

    #[test]
    fn json_comparison_tolerates_one_ulp_only_in_floats() {
        let a = serde_json::json!({"x": 0.1, "n": 3});
        let b = serde_json::json!({"x": f64::from_bits(0.1f64.to_bits() + 1), "n": 3});
        assert!(same_json(&a, &b));
        assert!(!same_json(&a, &serde_json::json!({"x": 0.1, "n": 4})));
        assert!(!same_json(&a, &serde_json::json!({"x": 0.1000001, "n": 3})));
    }
}
