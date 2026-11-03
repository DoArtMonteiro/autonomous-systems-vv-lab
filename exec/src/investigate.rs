//! M13 Discovery Lab: the investigation of one bounded safety claim.
//!
//! A claim (`vv-claim.v1`) names a domain, a base case at the registered conditions, one property
//! (a violation name such as `requirement:R1_vertical_speed`), the assumptions that may vary and
//! their envelope, three disjoint seed pools, a budget, and optional mechanism hypotheses,
//! candidate mitigations and regression families. The investigation runs, in order:
//!
//! 1. baseline: the property at the registered conditions;
//! 2. challenge: a `vv-search.v1` falsification search over the envelope (`search.rs`, unchanged);
//! 3. replication: the closest counterexample written by the canonical writer and rerun on fresh
//!    evaluation seeds;
//! 4. attribution: paired counterfactuals that revert or isolate each assumption;
//! 5. envelope: a grid over the first two assumptions;
//! 6. mechanism: the declared interventions and trace checks of each hypothesis, paired with the
//!    unmodified counterexample;
//! 7. mitigations: each candidate on the counterexample, the envelope, the registered conditions
//!    and fresh regression families, always paired with the unmitigated system.
//!
//! Every simulation is a logged probe. Every number in `investigation.json` is a pure function of
//! the claim, the base cases and the probes, and `verify` recomputes all of them from scratch:
//! nothing stored is trusted. The verdict rules are constants of this file, not of the claim.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::domain::{Domain, by_id};
use crate::plan::{apply_parameters, read_capped, scale, sha256_hex, snap};
use crate::search::{self, Objective, Q, SearchLimits, SeedPool, Strategy};
use crate::seeds::{Protected, check_span};
use crate::spec::{MAX_THREADS, Parameter, validate_parameters};
use crate::stats::{clopper_pearson, mcnemar_exact};

pub const CLAIM_SCHEMA: &str = "vv-claim.v1";
pub const PACKAGE_SCHEMA: &str = "vv-investigation.v1";
pub const VERIFICATION_SCHEMA: &str = "vv-investigation-verification.v1";
const MAX_CLAIM_BYTES: u64 = 1024 * 1024;
const MAX_CASE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_PROBES: u64 = 200_000;

/// A factor is necessary when reverting it alone removes the violation in at least this fraction
/// of the paired seeds on which the counterexample violates; sufficient when applying it alone to
/// the registered conditions violates in at least this fraction of the seeds.
pub const ROLE_THRESHOLD: f64 = 0.9;
/// An intervention prediction is supported when the predicted result occurs in at least
/// `ROLE_THRESHOLD` of the seeds and the paired change against the control has an exact McNemar
/// p below `ALPHA`; contradicted when it occurs in at most `1 - ROLE_THRESHOLD`.
pub const ALPHA: f64 = 0.01;
/// A mitigation is effective when it removes the violation in at least this fraction of the
/// counterexample seeds that violated without it.
pub const EFFECTIVE: f64 = 0.9;

/// Seeds no investigation may run, beyond the guard of each domain.
pub const INVESTIGATION_PROTECTED: &[Protected] = &[
    Protected {
        start: 44_000,
        end: 44_999,
        reason: "M13 reserve for a future preregistered confirmation; needs owner approval",
    },
    Protected {
        start: 50_000,
        end: 59_999,
        reason: "M14 held-out split, already used: not reusable for development or as fresh evidence",
    },
];

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Override {
    pub pointer: String,
    pub value: Value,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Assumption {
    pub parameter: Parameter,
    pub description: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ClaimSeeds {
    /// Seeds of the challenge search only.
    pub discovery: SeedPool,
    /// Baseline, replication, attribution, envelope, mechanism and mitigation probes. The same
    /// consecutive seeds are reused by every stage, so stage comparisons are paired.
    pub evaluation: SeedPool,
    /// Regression families of the mitigations: seeds never used to find or explain the failure.
    pub regression: SeedPool,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Budget {
    pub baseline_seeds: u32,
    pub challenge: u32,
    pub minimise: u32,
    pub replication_seeds: u32,
    pub envelope_levels: u32,
    pub envelope_seeds: u32,
    pub mechanism_seeds: u32,
    pub regression_points: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Expect {
    Holds,
    Violated,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum At {
    /// The minimised counterexample.
    Counterexample,
    /// The registered conditions (the base case).
    Registered,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Intervention {
    pub id: String,
    pub description: String,
    pub at: At,
    pub overrides: Vec<Override>,
    pub predicts: Expect,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Predicate {
    /// The signal is never true (never non-zero) over the run.
    NeverTrue,
    /// The signal is true (non-zero) at least once.
    EverTrue,
    /// The largest absolute value of the signal is below `threshold`.
    MaxAbsBelow,
    /// The largest absolute value of the signal is at least `threshold`.
    MaxAbsAtLeast,
}

/// A prediction about the trace of the counterexample runs: a signal read from every sample that
/// has it (`pointer`, minus `minus` when given) and a predicate over the whole run.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TraceCheck {
    pub id: String,
    pub description: String,
    /// Pointer to the list of samples in the trace file, for example `/samples`.
    pub samples: String,
    pub pointer: String,
    #[serde(default)]
    pub minus: Option<String>,
    pub predicate: Predicate,
    #[serde(default)]
    pub threshold: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Hypothesis {
    pub id: String,
    pub statement: String,
    #[serde(default)]
    pub interventions: Vec<Intervention>,
    #[serde(default)]
    pub trace_checks: Vec<TraceCheck>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Mitigation {
    pub id: String,
    pub title: String,
    pub rationale: String,
    pub overrides: Vec<Override>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Family {
    pub id: String,
    pub title: String,
    /// Path of the family base case, relative to the claim file.
    pub base_case: String,
    pub parameters: Vec<Parameter>,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Grade {
    #[default]
    Exploratory,
    Confirmatory,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Preregistration {
    /// Path of the frozen protocol, relative to the claim file.
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Claim {
    pub schema: String,
    pub id: String,
    pub title: String,
    pub statement: String,
    /// Where and how the claim was registered, in words.
    pub origin: String,
    pub domain: String,
    /// Path of the base case at the registered conditions, relative to the claim file.
    pub base_case: String,
    /// The violation name the claim is about.
    pub property: String,
    /// Fraction of runs at one condition the claim allows to violate (0 for "never").
    pub tolerance: f64,
    /// Metric that grows (or falls) towards a violation of the property; guides the search.
    pub objective: Objective,
    pub assumptions: Vec<Assumption>,
    pub seeds: ClaimSeeds,
    pub budget: Budget,
    pub search_seed: u64,
    #[serde(default = "halton")]
    pub strategy: Strategy,
    #[serde(default)]
    pub hypotheses: Vec<Hypothesis>,
    #[serde(default)]
    pub mitigations: Vec<Mitigation>,
    #[serde(default)]
    pub regression: Vec<Family>,
    /// Requested grade. `confirmatory` is refused unless `preregistration` freezes this claim.
    #[serde(default)]
    pub evidence_grade: Grade,
    #[serde(default)]
    pub preregistration: Option<Preregistration>,
    pub limits: SearchLimits,
}

fn halton() -> Strategy {
    Strategy::Halton
}

fn valid_id(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && s.bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
}

fn pool_size(p: &SeedPool) -> u64 {
    p.high - p.low + 1
}

impl Claim {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() as u64 > MAX_CLAIM_BYTES {
            return Err(format!("claim exceeds {MAX_CLAIM_BYTES} bytes"));
        }
        let c: Claim = serde_json::from_slice(bytes).map_err(|e| format!("invalid claim: {e}"))?;
        c.validate()?;
        Ok(c)
    }

    pub fn domain(&self) -> Result<&'static dyn Domain, String> {
        by_id(&self.domain).ok_or(format!("unknown domain {}", self.domain))
    }

    pub fn parameters(&self) -> Vec<Parameter> {
        self.assumptions
            .iter()
            .map(|a| a.parameter.clone())
            .collect()
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema != CLAIM_SCHEMA {
            return Err(format!("schema must be {CLAIM_SCHEMA}"));
        }
        if !valid_id(&self.id) {
            return Err("id must be 1 to 64 letters, digits, '-' or '_'".into());
        }
        let domain = self.domain()?;
        if !domain.seeded() || !domain.has_verdicts() {
            return Err("a claim needs a seeded domain with verdicts".into());
        }
        if !(self.property.starts_with("requirement:")
            || self.property.starts_with("invariant:")
            || self.property.starts_with("contract:"))
        {
            return Err("property must be a requirement:, invariant: or contract: name".into());
        }
        if !(0.0..1.0).contains(&self.tolerance) {
            return Err("tolerance must be in [0, 1)".into());
        }
        if self.assumptions.is_empty() || self.assumptions.len() > 8 {
            return Err("a claim needs 1 to 8 assumptions".into());
        }
        validate_parameters(&self.parameters())?;
        let pools = [
            ("discovery", self.seeds.discovery),
            ("evaluation", self.seeds.evaluation),
            ("regression", self.seeds.regression),
        ];
        for (name, p) in pools {
            if p.low > p.high {
                return Err(format!("seeds.{name}: low exceeds high"));
            }
            check_span(domain.protected(), p.low, p.high)?;
            check_span(INVESTIGATION_PROTECTED, p.low, p.high)?;
        }
        for (i, (na, a)) in pools.iter().enumerate() {
            for (nb, b) in &pools[i + 1..] {
                if a.low <= b.high && b.low <= a.high {
                    return Err(format!("seed pools {na} and {nb} overlap"));
                }
            }
        }
        let b = &self.budget;
        let eval_needed = [
            b.baseline_seeds,
            b.replication_seeds,
            b.envelope_seeds,
            b.mechanism_seeds,
        ]
        .into_iter()
        .max()
        .unwrap_or(0);
        if b.baseline_seeds == 0 || b.replication_seeds == 0 || b.envelope_seeds == 0 {
            return Err("baseline, replication and envelope need at least one seed".into());
        }
        if u64::from(eval_needed) > pool_size(&self.seeds.evaluation) {
            return Err("the evaluation pool must hold every evaluation seed".into());
        }
        if u64::from(b.regression_points) > pool_size(&self.seeds.regression) {
            return Err("the regression pool must hold one seed per regression point".into());
        }
        if b.challenge == 0 || b.envelope_levels < 2 || b.envelope_levels > 64 {
            return Err("budget needs challenge > 0 and envelope_levels in [2, 64]".into());
        }
        let id_sets: [(&str, Vec<&String>); 3] = [
            (
                "hypotheses",
                self.hypotheses.iter().map(|h| &h.id).collect(),
            ),
            (
                "mitigations",
                self.mitigations.iter().map(|m| &m.id).collect(),
            ),
            (
                "regression",
                self.regression.iter().map(|f| &f.id).collect(),
            ),
        ];
        for (name, set) in id_sets {
            let mut seen = BTreeSet::new();
            for id in set {
                if !valid_id(id) || !seen.insert(id) || id == "claim" {
                    return Err(format!("{name}: ids must be valid, unique and not 'claim'"));
                }
            }
        }
        if self.hypotheses.len() > 8 || self.mitigations.len() > 8 || self.regression.len() > 8 {
            return Err("at most 8 hypotheses, 8 mitigations and 8 regression families".into());
        }
        let pointers: BTreeSet<&str> = self
            .assumptions
            .iter()
            .map(|a| a.parameter.pointer.as_str())
            .collect();
        let check_overrides = |o: &[Override]| -> Result<(), String> {
            if o.is_empty() {
                return Err("an intervention or mitigation needs at least one override".into());
            }
            for x in o {
                if pointers.contains(x.pointer.as_str()) {
                    return Err(format!(
                        "override {} is an assumption; an intervention may not move the counterexample",
                        x.pointer
                    ));
                }
            }
            Ok(())
        };
        for h in &self.hypotheses {
            let mut seen = BTreeSet::new();
            for i in &h.interventions {
                if !valid_id(&i.id) || !seen.insert(&i.id) {
                    return Err(format!(
                        "hypothesis {}: invalid or repeated intervention id",
                        h.id
                    ));
                }
                check_overrides(&i.overrides)?;
            }
            for t in &h.trace_checks {
                if !valid_id(&t.id) || !seen.insert(&t.id) {
                    return Err(format!(
                        "hypothesis {}: invalid or repeated trace check id",
                        h.id
                    ));
                }
                let needs = matches!(
                    t.predicate,
                    Predicate::MaxAbsBelow | Predicate::MaxAbsAtLeast
                );
                if needs != t.threshold.is_some_and(f64::is_finite) {
                    return Err(format!(
                        "trace check {}: a threshold is needed exactly for the max_abs predicates",
                        t.id
                    ));
                }
            }
        }
        for m in &self.mitigations {
            check_overrides(&m.overrides)?;
        }
        for f in &self.regression {
            validate_parameters(&f.parameters)?;
        }
        if self.evidence_grade == Grade::Confirmatory && self.preregistration.is_none() {
            return Err("a confirmatory investigation needs a preregistration".into());
        }
        Ok(())
    }
}

/// Inputs of an investigation, read once: the claim and every base case.
#[derive(Clone, Debug)]
pub struct Inputs {
    pub claim_bytes: Vec<u8>,
    pub base_bytes: Vec<u8>,
    pub families: Vec<Vec<u8>>,
    pub preregistration: Option<Vec<u8>>,
}

pub fn read_inputs(claim_path: &Path) -> Result<Inputs, String> {
    let claim_bytes = read_capped(claim_path, MAX_CLAIM_BYTES)?;
    let claim = Claim::parse(&claim_bytes)?;
    let dir = claim_path.parent().unwrap_or(Path::new("."));
    let base_bytes = read_capped(&dir.join(&claim.base_case), MAX_CASE_BYTES)?;
    let families = claim
        .regression
        .iter()
        .map(|f| read_capped(&dir.join(&f.base_case), MAX_CASE_BYTES))
        .collect::<Result<_, _>>()?;
    let preregistration = match &claim.preregistration {
        Some(p) => Some(read_capped(&dir.join(&p.path), MAX_CLAIM_BYTES)?),
        None => None,
    };
    Ok(Inputs {
        claim_bytes,
        base_bytes,
        families,
        preregistration,
    })
}

/// One simulation. Recomputable from the claim, the base cases and the fields before
/// `case_sha256`.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Probe {
    pub stage: String,
    pub key: String,
    /// `claim` or a regression family id.
    pub family: String,
    /// Lattice coordinates, one per parameter of the family.
    pub q: Vec<u64>,
    /// Ids of the interventions or mitigations applied, in order.
    pub applied: Vec<String>,
    pub seed: u64,
    pub case_sha256: String,
    pub error: Option<String>,
    pub trace_sha256: Option<String>,
    pub outcome: Option<String>,
    pub violations: Vec<String>,
    pub property_violated: Option<bool>,
    pub metric: Option<f64>,
}

impl Probe {
    fn violated(&self) -> bool {
        self.property_violated == Some(true)
    }
}

#[derive(Clone, Debug)]
struct Request {
    stage: &'static str,
    key: String,
    family: String,
    q: Vec<u64>,
    applied: Vec<String>,
    seed: u64,
}

fn set_existing(doc: &mut Value, pointer: &str, value: Value) -> Result<(), String> {
    let slot = doc
        .pointer_mut(pointer)
        .ok_or(format!("{pointer} does not exist in the base case"))?;
    *slot = value;
    Ok(())
}

pub fn values_of(parameters: &[Parameter], q: &[u64]) -> Vec<f64> {
    parameters
        .iter()
        .zip(search::to_u(q))
        .map(|(p, u)| snap(p, scale(p, u)))
        .collect()
}

/// What a probe runs on: the claim, its base, the families and the named override sets.
struct Session {
    claim: Claim,
    base: Value,
    params: Vec<Parameter>,
    families: BTreeMap<String, (Value, Vec<Parameter>)>,
    overrides: BTreeMap<String, Vec<Override>>,
    domain: &'static dyn Domain,
}

impl Session {
    fn new(inputs: &Inputs) -> Result<Self, String> {
        let claim = Claim::parse(&inputs.claim_bytes)?;
        let domain = claim.domain()?;
        let base: Value = serde_json::from_slice(&inputs.base_bytes)
            .map_err(|e| format!("base case is not JSON: {e}"))?;
        if inputs.families.len() != claim.regression.len() {
            return Err("one base case per regression family is needed".into());
        }
        let mut families = BTreeMap::new();
        for (f, bytes) in claim.regression.iter().zip(&inputs.families) {
            let v: Value = serde_json::from_slice(bytes)
                .map_err(|e| format!("family {} base case is not JSON: {e}", f.id))?;
            families.insert(f.id.clone(), (v, f.parameters.clone()));
        }
        let mut overrides = BTreeMap::new();
        for h in &claim.hypotheses {
            for i in &h.interventions {
                overrides.insert(
                    format!("intervention:{}:{}", h.id, i.id),
                    i.overrides.clone(),
                );
            }
        }
        for m in &claim.mitigations {
            overrides.insert(format!("mitigation:{}", m.id), m.overrides.clone());
        }
        if claim.evidence_grade == Grade::Confirmatory {
            let p = claim.preregistration.as_ref().ok_or("no preregistration")?;
            let bytes = inputs
                .preregistration
                .as_ref()
                .ok_or("the preregistration file was not read")?;
            if sha256_hex(bytes) != p.sha256 {
                return Err("the preregistration file does not match its declared hash".into());
            }
            // The protocol must name the claim it freezes. The claim itself names the protocol,
            // so the protocol freezes the claim without its `preregistration` field.
            let mut unbound = claim.clone();
            unbound.preregistration = None;
            unbound.evidence_grade = Grade::Exploratory;
            let frozen = sha256_hex(&serde_json::to_vec(&unbound).map_err(|e| e.to_string())?);
            if !String::from_utf8_lossy(bytes).contains(&frozen) {
                return Err(format!(
                    "the preregistration does not freeze this claim (canonical sha256 {frozen})"
                ));
            }
        }
        let params = claim.parameters();
        let s = Session {
            claim,
            base,
            params,
            families,
            overrides,
            domain,
        };
        s.check_cases()?;
        Ok(s)
    }

    fn case(&self, r: &Request) -> Result<Vec<u8>, String> {
        let (base, params) = if r.family == "claim" {
            (&self.base, &self.params)
        } else {
            let (b, p) = self
                .families
                .get(&r.family)
                .ok_or(format!("unknown family {}", r.family))?;
            (b, p)
        };
        let mut doc = base.clone();
        for id in &r.applied {
            for o in self
                .overrides
                .get(id)
                .ok_or(format!("unknown override set {id}"))?
            {
                set_existing(&mut doc, &o.pointer, o.value.clone())?;
            }
        }
        apply_parameters(doc, params, &values_of(params, &r.q))
    }

    fn run(&self, r: &Request) -> Probe {
        let mut p = Probe {
            stage: r.stage.to_string(),
            key: r.key.clone(),
            family: r.family.clone(),
            q: r.q.clone(),
            applied: r.applied.clone(),
            seed: r.seed,
            case_sha256: String::new(),
            error: None,
            trace_sha256: None,
            outcome: None,
            violations: Vec::new(),
            property_violated: None,
            metric: None,
        };
        let case = match self.case(r) {
            Ok(c) => c,
            Err(m) => {
                p.error = Some(m);
                return p;
            }
        };
        p.case_sha256 = sha256_hex(&case);
        match self.domain.run(&case, r.seed) {
            Ok(o) => {
                p.property_violated = Some(o.violations.contains(&self.claim.property));
                p.metric = o.metrics.get(&self.claim.objective.metric).copied();
                p.trace_sha256 = Some(o.trace_sha256);
                p.outcome = Some(o.outcome);
                p.violations = o.violations;
            }
            Err(e) => p.error = Some(e.to_string()),
        }
        p
    }

    fn run_all(&self, requests: &[Request], threads: usize) -> Vec<Probe> {
        let next = AtomicUsize::new(0);
        let slots: Mutex<Vec<Option<Probe>>> = Mutex::new(vec![None; requests.len()]);
        let logical = std::thread::available_parallelism().map_or(1, |n| n.get());
        std::thread::scope(|scope| {
            for _ in 0..threads.clamp(1, logical.min(MAX_THREADS)) {
                scope.spawn(|| {
                    loop {
                        let i = next.fetch_add(1, Ordering::Relaxed);
                        let Some(r) = requests.get(i) else { return };
                        let p = self.run(r);
                        slots.lock().unwrap_or_else(|e| e.into_inner())[i] = Some(p);
                    }
                });
            }
        });
        slots
            .into_inner()
            .unwrap_or_else(|e| e.into_inner())
            .into_iter()
            .map(|p| p.expect("every request ran"))
            .collect()
    }

    /// Every override set and both ends of every box are accepted by the model before any run.
    fn check_cases(&self) -> Result<(), String> {
        let d = self.params.len();
        let registered = search::nominal(&self.base, &self.params)?;
        let mut sets: Vec<Vec<String>> = vec![vec![]];
        sets.extend(self.overrides.keys().map(|k| vec![k.clone()]));
        for q in [registered, vec![0; d], vec![Q; d]] {
            for applied in &sets {
                let r = req(
                    "check",
                    String::new(),
                    &q,
                    applied,
                    self.claim.seeds.evaluation.low,
                );
                let case = self.case(&r)?;
                self.domain
                    .validate(&case, r.seed)
                    .map_err(|e| format!("refused by the model with {applied:?}: {e}"))?;
            }
        }
        let mitigation_sets: Vec<Vec<String>> = std::iter::once(vec![])
            .chain(
                self.claim
                    .mitigations
                    .iter()
                    .map(|m| vec![format!("mitigation:{}", m.id)]),
            )
            .collect();
        for f in &self.claim.regression {
            let (base, params) = &self.families[&f.id];
            let fam_nominal = search::nominal(base, params)?;
            for q in [fam_nominal, vec![0; params.len()], vec![Q; params.len()]] {
                for applied in &mitigation_sets {
                    let r = Request {
                        stage: "check",
                        key: String::new(),
                        family: f.id.clone(),
                        q: q.clone(),
                        applied: applied.clone(),
                        seed: self.claim.seeds.regression.low,
                    };
                    let case = self.case(&r)?;
                    self.domain
                        .validate(&case, r.seed)
                        .map_err(|e| format!("family {} refused by the model: {e}", f.id))?;
                }
            }
        }
        Ok(())
    }

    /// The challenge search, derived from the claim alone.
    fn challenge_spec(&self) -> Vec<u8> {
        let c = &self.claim;
        let spec = json!({
            "schema": search::SCHEMA,
            "id": format!("{}-challenge", &c.id[..c.id.len().min(54)]),
            "description": format!("Challenge of claim {}", c.id),
            "domain": c.domain,
            "base_case": "base-case.json",
            "parameters": c.parameters(),
            "seed_pool": c.seeds.discovery,
            "target": "any",
            "objective": c.objective,
            "strategy": c.strategy,
            "budget": c.budget.challenge,
            "repetitions": 1,
            "search_seed": c.search_seed,
            "minimise_budget": c.budget.minimise,
            "limits": c.limits,
        });
        pretty(&spec)
    }

    /// The re-challenge of a mitigation: the same search over the same envelope, on the regression
    /// seeds, with the base case of the claim plus the mitigation.
    fn rechallenge_inputs(&self, m: &Mitigation) -> Result<(Vec<u8>, Vec<u8>), String> {
        let c = &self.claim;
        let mut base = self.base.clone();
        for o in &m.overrides {
            set_existing(&mut base, &o.pointer, o.value.clone())?;
        }
        let spec = json!({
            "schema": search::SCHEMA,
            "id": format!("re-{}", &m.id[..m.id.len().min(60)]),
            "description": format!("Re-challenge of claim {} with mitigation {}", c.id, m.id),
            "domain": c.domain,
            "base_case": "base-case.json",
            "parameters": c.parameters(),
            "seed_pool": c.seeds.regression,
            "target": "any",
            "objective": c.objective,
            "strategy": c.strategy,
            "budget": c.budget.challenge,
            "repetitions": 1,
            "search_seed": c.search_seed,
            "minimise_budget": 0,
            "limits": c.limits,
        });
        Ok((pretty(&spec), pretty(&base)))
    }
}

/// A finished search, read back: result, log and the hash of `search.json`.
struct SearchRun {
    result: search::SearchResult,
    log: Vec<search::Evaluation>,
    sha256: String,
}

fn read_search(dir: &Path) -> Result<SearchRun, String> {
    let bytes = read_capped(&dir.join("search.json"), 256 * 1024 * 1024)?;
    let result: search::SearchResult =
        serde_json::from_slice(&bytes).map_err(|e| format!("search.json: {e}"))?;
    // `search.json` carries the wall time of the run; the package cites the hash of the log,
    // which is deterministic and which `search::verify` checks against the log itself.
    let text = String::from_utf8(read_capped(
        &dir.join("evaluations.jsonl"),
        512 * 1024 * 1024,
    )?)
    .map_err(|_| "the search log is not UTF-8")?;
    Ok(SearchRun {
        sha256: result.log_sha256.clone(),
        result,
        log: search::parse_log(&text)?,
    })
}

fn rechallenge_of(property: &str, run: &SearchRun) -> Rechallenge {
    let evals: Vec<&search::Evaluation> = run
        .log
        .iter()
        .filter(|e| e.phase == search::Phase::Search)
        .collect();
    let hit = |e: &search::Evaluation| e.violations.iter().any(|v| v == property);
    let n_ok = evals.iter().filter(|e| e.error.is_none()).count() as u64;
    let k = evals.iter().filter(|e| hit(e)).count() as u64;
    Rechallenge {
        search_log_sha256: run.sha256.clone(),
        evaluations: evals.len() as u64,
        property_violations: k,
        first_property_violation: evals.iter().position(|e| hit(e)).map(|i| i as u32 + 1),
        classes: run
            .result
            .repetitions
            .iter()
            .flat_map(|r| r.classes.iter().map(|c| c.class.clone()))
            .collect(),
        upper_bound_if_none: (k == 0).then(|| clopper_pearson(0, n_ok, 0.95).1),
    }
}

pub fn probe_line(p: &Probe) -> String {
    let json = serde_json::to_string(p).expect("a probe always serialises");
    format!("{} {json}\n", sha256_hex(json.as_bytes()))
}

pub fn parse_probes(text: &str) -> Result<Vec<Probe>, String> {
    text.lines()
        .enumerate()
        .map(|(i, line)| {
            let (hash, json) = line
                .split_once(' ')
                .ok_or(format!("probe line {} has no hash", i + 1))?;
            if sha256_hex(json.as_bytes()) != hash {
                return Err(format!("probe line {} does not match its hash", i + 1));
            }
            serde_json::from_str(json).map_err(|e| format!("probe line {}: {e}", i + 1))
        })
        .collect()
}

// ---------------------------------------------------------------------------------------------
// Findings: pure functions of the claim and the probes.

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Rate {
    pub n: u64,
    pub violated: u64,
    pub errors: u64,
    pub rate: f64,
    /// Clopper-Pearson 95 % interval of the violation rate.
    pub ci95: (f64, f64),
}

fn rate(probes: &[&Probe]) -> Rate {
    let errors = probes.iter().filter(|p| p.error.is_some()).count() as u64;
    let n = probes.len() as u64 - errors;
    let violated = probes.iter().filter(|p| p.violated()).count() as u64;
    Rate {
        n,
        violated,
        errors,
        rate: if n == 0 {
            0.0
        } else {
            violated as f64 / n as f64
        },
        ci95: clopper_pearson(violated, n, 0.95),
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Point {
    pub q: Vec<u64>,
    pub values: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Challenge {
    /// `log_sha256` of the search: the hash of its evaluation log.
    pub search_log_sha256: String,
    pub strategy: String,
    pub evaluations: u64,
    pub errors: u64,
    /// Search evaluations whose run violated the property.
    pub property_violations: u64,
    /// 1-based search evaluation of the first property violation.
    pub first_property_violation: Option<u32>,
    /// Classes found by the search that contain the property.
    pub property_classes: Vec<String>,
    /// Other classes the search found, reported and not investigated.
    pub other_classes: Vec<String>,
    /// Clopper-Pearson 95 % upper bound of the property violation rate under uniform sampling of
    /// the envelope, when the search found no violation.
    pub upper_bound_if_none: Option<f64>,
    /// Every search evaluation as (unit coordinates, violated property), for the scatter view.
    pub samples: Vec<(Vec<f64>, bool)>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Counterexample {
    pub class: String,
    pub seed: u64,
    /// 1-based search evaluation that found the class.
    pub found_at: u32,
    pub found: Point,
    pub minimised: Point,
    pub registered: Point,
    pub active: Vec<String>,
    /// The search log, an in-process rerun and the canonical writer gave the same trace bytes.
    pub byte_reproduced: bool,
    pub trace_sha256: String,
    /// The minimised point on the evaluation seeds.
    pub replication: Rate,
    /// The lower 95 % bound of the violation rate at the counterexample exceeds the tolerance.
    pub refutes: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Factor {
    pub name: String,
    pub unit: String,
    pub registered: f64,
    pub counterexample: f64,
    /// Seeds where the counterexample violates and reverting this factor alone removes the
    /// violation, of the seeds where the counterexample violates.
    pub necessity: (u64, u64),
    /// Seeds where this factor alone, at the registered conditions, violates.
    pub sufficiency: (u64, u64),
    pub role: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Axis {
    pub name: String,
    pub unit: String,
    pub values: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Envelope {
    pub axes: Vec<Axis>,
    /// The other assumptions, held at the counterexample.
    pub fixed: Vec<(String, f64)>,
    pub seeds: u64,
    /// Property violations per cell, `cells[i][j]` for the first axis at i and the second at j
    /// (j = 0 with one axis), without any mitigation.
    pub cells: Vec<Vec<u64>>,
    pub errors: u64,
    /// Cells with no violation and no error over every seed, of all cells.
    pub clean_cells: (u64, u64),
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct InterventionResult {
    pub id: String,
    pub description: String,
    pub at: At,
    pub predicts: Expect,
    pub control: Rate,
    pub treated: Rate,
    /// Paired seeds: control violated and treated held; control held and treated violated.
    pub discordant: (u64, u64),
    pub mcnemar_p: f64,
    /// The intervention over the envelope, paired with the unmodified envelope on the property.
    pub region: Paired,
    /// `general` when the predicted change happens in at least `ROLE_THRESHOLD` of the envelope
    /// pairs it could change, `local` otherwise, `untested` when no pair could change.
    pub region_status: String,
    pub status: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct TraceCheckResult {
    pub id: String,
    pub description: String,
    /// Runs where the predicate held, of the runs read.
    pub held: (u64, u64),
    /// Largest absolute value of the signal per run.
    pub max_abs: Vec<f64>,
    pub status: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct HypothesisResult {
    pub id: String,
    pub statement: String,
    pub interventions: Vec<InterventionResult>,
    pub trace_checks: Vec<TraceCheckResult>,
    pub status: String,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
pub struct Paired {
    pub n: u64,
    /// Violated without the mitigation, held with it.
    pub fixed: u64,
    /// Held without the mitigation, violated with it.
    pub broken: u64,
    pub both: u64,
    pub neither: u64,
    /// Violation names present with the mitigation and absent without it, counted per pair.
    pub new_violations: BTreeMap<String, u64>,
    /// Up to 8 pairs that broke or gained a violation: probe key and seed.
    pub examples: Vec<(String, u64)>,
}

/// Pairs `before[i]` with `after[i]`. With `any`, a pair violates when it has any violation;
/// otherwise when it violates the claim property.
fn paired(before: &[&Probe], after: &[&Probe], any: bool) -> Paired {
    let mut out = Paired::default();
    for (b, a) in before.iter().zip(after) {
        if b.error.is_some() || a.error.is_some() {
            continue;
        }
        out.n += 1;
        let (vb, va) = if any {
            (!b.violations.is_empty(), !a.violations.is_empty())
        } else {
            (b.violated(), a.violated())
        };
        match (vb, va) {
            (true, false) => out.fixed += 1,
            (false, true) => out.broken += 1,
            (true, true) => out.both += 1,
            (false, false) => out.neither += 1,
        }
        let had: BTreeSet<&String> = b.violations.iter().collect();
        let mut new = false;
        for v in &a.violations {
            if !had.contains(v) {
                *out.new_violations.entry(v.clone()).or_default() += 1;
                new = true;
            }
        }
        if (new || (!vb && va)) && out.examples.len() < 8 {
            out.examples.push((a.key.clone(), a.seed));
        }
    }
    out
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct FamilyResult {
    pub id: String,
    pub title: String,
    /// Any violation, mitigated against unmitigated, on the same points and seeds.
    pub paired: Paired,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct MitigationResult {
    pub id: String,
    pub title: String,
    pub rationale: String,
    /// The claim property on the counterexample, paired by seed.
    pub counterexample: Paired,
    /// The claim property over the envelope cells and seeds, paired.
    pub envelope: Paired,
    /// The same pairing per cell, laid out as `Envelope::cells`: (fixed, broken, still violated).
    pub envelope_cells: Vec<Vec<(u64, u64, u64)>>,
    /// Every property at the registered conditions, paired.
    pub registered: Paired,
    pub families: Vec<FamilyResult>,
    /// A fresh falsification search of the claim with the mitigation applied, on the regression
    /// seeds: residual counterexamples the mitigation leaves inside the envelope.
    pub rechallenge: Rechallenge,
    /// Clopper-Pearson 95 % upper bound of the rate of regressing pairs over the envelope, the
    /// registered conditions and the families.
    pub regression_upper_bound: f64,
    /// Envelope cells the mitigation made violate the claim property, plus pairs at the
    /// registered conditions or in a family where it added a safety (non-requirement) violation
    /// or a violation of the claim property.
    pub regressions: u64,
    pub status: String,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
pub struct Rechallenge {
    /// `log_sha256` of the search: the hash of its evaluation log.
    pub search_log_sha256: String,
    pub evaluations: u64,
    pub property_violations: u64,
    pub first_property_violation: Option<u32>,
    pub classes: Vec<String>,
    /// Upper 95 % bound of the property violation rate under uniform sampling, when none found.
    pub upper_bound_if_none: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Verdict {
    pub claim: String,
    pub mechanism: Vec<(String, String)>,
    pub mitigations: Vec<(String, String)>,
    pub evidence_grade: Grade,
    pub open_risks: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Findings {
    pub baseline: Rate,
    pub baseline_within_tolerance: bool,
    pub challenge: Challenge,
    pub counterexample: Option<Counterexample>,
    pub attribution: Vec<Factor>,
    pub envelope: Option<Envelope>,
    pub mechanism: Vec<HypothesisResult>,
    pub mitigations: Vec<MitigationResult>,
    pub verdict: Verdict,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct ArtifactRef {
    pub family: String,
    pub q: Vec<u64>,
    pub applied: Vec<String>,
    pub seed: u64,
    pub description: String,
    /// Written file name to sha256.
    pub files: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Package {
    pub schema: String,
    pub engine: String,
    pub claim_id: String,
    pub title: String,
    pub statement: String,
    pub origin: String,
    pub property: String,
    pub tolerance: f64,
    pub domain: String,
    pub assumptions: Vec<Value>,
    pub claim_sha256: String,
    pub base_case_sha256: String,
    pub family_case_sha256: BTreeMap<String, String>,
    pub source_sha256: String,
    pub probes: u64,
    pub probes_sha256: String,
    pub rules: Value,
    pub artifacts: BTreeMap<String, ArtifactRef>,
    pub findings: Findings,
}

fn rules() -> Value {
    json!({
        "role_threshold": ROLE_THRESHOLD,
        "alpha": ALPHA,
        "effective": EFFECTIVE,
        "refutation": "lower Clopper-Pearson 95 % bound of the violation rate at the counterexample above the claim tolerance, with byte reproduction",
        "intervention": "predicted result in at least role_threshold of the seeds and exact McNemar p below alpha in the predicted direction",
    })
}

// ---------------------------------------------------------------------------------------------
// Planning.

fn eval_seeds(claim: &Claim, n: u32) -> Vec<u64> {
    (0..u64::from(n))
        .map(|i| claim.seeds.evaluation.low + i)
        .collect()
}

fn lattice(levels: u32) -> Vec<u64> {
    (0..levels)
        .map(|i| ((u128::from(i) * u128::from(Q)) / u128::from(levels - 1)) as u64)
        .collect()
}

fn req(stage: &'static str, key: String, q: &[u64], applied: &[String], seed: u64) -> Request {
    Request {
        stage,
        key,
        family: "claim".into(),
        q: q.to_vec(),
        applied: applied.to_vec(),
        seed,
    }
}

fn envelope_points(claim: &Claim, cx: &[u64]) -> (Vec<usize>, Vec<Vec<u64>>) {
    let dims: Vec<usize> = (0..claim.assumptions.len().min(2)).collect();
    let grid = lattice(claim.budget.envelope_levels);
    let mut points = Vec::new();
    for &a in &grid {
        if dims.len() == 1 {
            let mut q = cx.to_vec();
            q[0] = a;
            points.push(q);
        } else {
            for &b in &grid {
                let mut q = cx.to_vec();
                q[0] = a;
                q[1] = b;
                points.push(q);
            }
        }
    }
    (dims, points)
}

fn mitigation_tags(claim: &Claim) -> Vec<Vec<String>> {
    std::iter::once(vec![])
        .chain(
            claim
                .mitigations
                .iter()
                .map(|m| vec![format!("mitigation:{}", m.id)]),
        )
        .collect()
}

fn tag_of(applied: &[String]) -> String {
    applied.first().cloned().unwrap_or_else(|| "none".into())
}

/// Stages planned from the counterexample.
fn plan_dependent(claim: &Claim, registered: &[u64], cx: &[u64], cx_seed: u64) -> Vec<Request> {
    let b = &claim.budget;
    let mut out = Vec::new();
    let rep = eval_seeds(claim, b.replication_seeds);
    out.push(req(
        "replication",
        format!("discovery/{cx_seed}"),
        cx,
        &[],
        cx_seed,
    ));
    for &s in &rep {
        out.push(req("replication", format!("evaluation/{s}"), cx, &[], s));
    }
    for (i, a) in claim.assumptions.iter().enumerate() {
        if cx[i] == registered[i] {
            continue;
        }
        let name = &a.parameter.name;
        let mut revert = cx.to_vec();
        revert[i] = registered[i];
        let mut isolate = registered.to_vec();
        isolate[i] = cx[i];
        for &s in &rep {
            out.push(req(
                "attribution",
                format!("revert:{name}/{s}"),
                &revert,
                &[],
                s,
            ));
        }
        for &s in &rep {
            out.push(req(
                "attribution",
                format!("isolate:{name}/{s}"),
                &isolate,
                &[],
                s,
            ));
        }
    }
    let (_, points) = envelope_points(claim, cx);
    let env = eval_seeds(claim, b.envelope_seeds);
    for applied in mitigation_tags(claim) {
        let tag = tag_of(&applied);
        for (c, q) in points.iter().enumerate() {
            for &s in &env {
                out.push(req("envelope", format!("{tag}/{c}/{s}"), q, &applied, s));
            }
        }
    }
    let mech = eval_seeds(claim, b.mechanism_seeds);
    for h in &claim.hypotheses {
        for i in &h.interventions {
            let at = match i.at {
                At::Counterexample => cx,
                At::Registered => registered,
            };
            let applied = vec![format!("intervention:{}:{}", h.id, i.id)];
            for &s in &mech {
                out.push(req(
                    "mechanism",
                    format!("{}/{}/control/{s}", h.id, i.id),
                    at,
                    &[],
                    s,
                ));
            }
            for &s in &mech {
                out.push(req(
                    "mechanism",
                    format!("{}/{}/treated/{s}", h.id, i.id),
                    at,
                    &applied,
                    s,
                ));
            }
            // The same intervention over every envelope cell and seed, paired with the
            // unmodified envelope: does it act on the whole failure region or at one point only?
            for (c, q) in points.iter().enumerate() {
                for &s in &env {
                    out.push(req(
                        "mechanism",
                        format!("{}/{}/region/{c}/{s}", h.id, i.id),
                        q,
                        &applied,
                        s,
                    ));
                }
            }
        }
    }
    for m in &claim.mitigations {
        let applied = vec![format!("mitigation:{}", m.id)];
        for &s in &rep {
            out.push(req(
                "mitigation",
                format!("{}/counterexample/{s}", m.id),
                cx,
                &applied,
                s,
            ));
        }
        for &s in &eval_seeds(claim, b.baseline_seeds) {
            out.push(req(
                "mitigation",
                format!("{}/registered/{s}", m.id),
                registered,
                &applied,
                s,
            ));
        }
    }
    out
}

const PRIMES: [u64; 8] = [2, 3, 5, 7, 11, 13, 17, 19];

fn radical_inverse(mut i: u64, base: u64) -> f64 {
    let mut f = 1.0;
    let mut r = 0.0;
    while i > 0 {
        f /= base as f64;
        r += f * (i % base) as f64;
        i /= base;
    }
    r
}

/// Regression families: the same Halton points and fresh seeds, with and without each mitigation.
fn plan_regression(claim: &Claim) -> Vec<Request> {
    let mut out = Vec::new();
    if claim.mitigations.is_empty() {
        return out;
    }
    for f in &claim.regression {
        for k in 0..claim.budget.regression_points {
            let q: Vec<u64> = (0..f.parameters.len())
                .map(|j| search::to_q(radical_inverse(u64::from(k) + 1, PRIMES[j % PRIMES.len()])))
                .collect();
            let seed = claim.seeds.regression.low + u64::from(k);
            for applied in mitigation_tags(claim) {
                out.push(Request {
                    stage: "regression",
                    key: format!("{}/{}/{k}", f.id, tag_of(&applied)),
                    family: f.id.clone(),
                    q: q.clone(),
                    applied,
                    seed,
                });
            }
        }
    }
    out
}

// ---------------------------------------------------------------------------------------------
// Execution.

/// Progress reporting: stage, done, total.
pub type Progress<'a> = Option<&'a (dyn Fn(&str, u64, u64) + Sync)>;

fn report(progress: Progress, stage: &str, done: u64, total: u64) {
    if let Some(f) = progress {
        f(stage, done, total);
    }
}

/// Everything recomputed from the claim, the search and the probes, before artifacts are written.
struct Computed {
    probes: Vec<Probe>,
    findings: Findings,
    artifacts: BTreeMap<String, ArtifactRef>,
}

fn frac((k, n): (u64, u64)) -> f64 {
    if n == 0 { 0.0 } else { k as f64 / n as f64 }
}

fn strategy_name(s: &Strategy) -> &'static str {
    match s {
        Strategy::Random => "random",
        Strategy::Halton => "halton",
        Strategy::Extremes => "extremes",
        Strategy::Grid { .. } => "grid",
        Strategy::Adaptive { .. } => "adaptive",
    }
}

fn compute(
    s: &Session,
    search_result: &search::SearchResult,
    search_log: &[search::Evaluation],
    search_log_sha256: String,
    rechallenges: &BTreeMap<String, SearchRun>,
    threads: usize,
    progress: Progress,
) -> Result<Computed, String> {
    let claim = &s.claim;
    let params = &s.params;
    let registered = search::nominal(&s.base, params)?;
    let mut probes = Vec::new();

    // 1. Baseline.
    report(
        progress,
        "baseline",
        0,
        u64::from(claim.budget.baseline_seeds),
    );
    let base_req: Vec<Request> = eval_seeds(claim, claim.budget.baseline_seeds)
        .into_iter()
        .map(|sd| req("baseline", format!("registered/{sd}"), &registered, &[], sd))
        .collect();
    probes.extend(s.run_all(&base_req, threads));
    let baseline = rate(&probes.iter().collect::<Vec<_>>());
    let baseline_probes: Vec<Probe> = probes.clone();

    // 2. Challenge, read through the claim property.
    let search_evals: Vec<&search::Evaluation> = search_log
        .iter()
        .filter(|e| e.phase == search::Phase::Search)
        .collect();
    let has_property = |v: &[String]| v.contains(&claim.property);
    let first_hit = search_evals
        .iter()
        .position(|e| has_property(&e.violations));
    let rep = search_result
        .repetitions
        .first()
        .ok_or("the search has no repetition")?;
    let in_class = |c: &search::Counterexample| c.class.split('+').any(|x| x == claim.property);
    let errors = search_evals.iter().filter(|e| e.error.is_some()).count() as u64;
    let n_ok = search_evals.len() as u64 - errors;
    let challenge = Challenge {
        search_log_sha256,
        strategy: strategy_name(&claim.strategy).into(),
        evaluations: search_evals.len() as u64,
        errors,
        property_violations: search_evals
            .iter()
            .filter(|e| has_property(&e.violations))
            .count() as u64,
        first_property_violation: first_hit.map(|i| i as u32 + 1),
        property_classes: rep
            .classes
            .iter()
            .filter(|c| in_class(c))
            .map(|c| c.class.clone())
            .collect(),
        other_classes: rep
            .classes
            .iter()
            .filter(|c| !in_class(c))
            .map(|c| c.class.clone())
            .collect(),
        upper_bound_if_none: first_hit
            .is_none()
            .then(|| clopper_pearson(0, n_ok, 0.95).1),
        samples: search_evals
            .iter()
            .map(|e| (search::to_u(&e.q), has_property(&e.violations)))
            .collect(),
    };

    // The counterexample: the property class whose minimised point is closest to the registered
    // conditions; ties go to the class found first.
    let chosen = rep.classes.iter().filter(|c| in_class(c)).min_by(|a, b| {
        a.deviation_after
            .total_cmp(&b.deviation_after)
            .then(a.found_at.cmp(&b.found_at))
    });
    let mut counterexample = None;
    let mut attribution = Vec::new();
    let mut envelope = None;
    let mut mechanism = Vec::new();
    let mut mitigations = Vec::new();
    let mut artifacts = BTreeMap::new();
    let mut open_risks = Vec::new();
    if let Some(c) = chosen {
        let cx = c.minimised_q.clone();
        let plan = plan_dependent(claim, &registered, &cx, c.seed);
        let total = plan.len() as u64;
        report(progress, "investigation", 0, total);
        let got = s.run_all(&plan, threads);
        report(progress, "investigation", total, total);
        let by = |stage: &str, prefix: &str| -> Vec<&Probe> {
            got.iter()
                .filter(|p| p.stage == stage && p.key.starts_with(prefix))
                .collect()
        };
        // 3. Replication.
        let discovery_run = by("replication", "discovery/");
        let replication_probes = by("replication", "evaluation/");
        let replication = rate(&replication_probes);
        let refutes = replication.n > 0 && replication.ci95.0 > claim.tolerance;
        let trace = discovery_run
            .first()
            .and_then(|p| p.trace_sha256.clone())
            .unwrap_or_default();
        let logged_trace = search_log
            .iter()
            .find(|e| e.q == cx && e.seed == c.seed && e.trace_sha256.is_some())
            .and_then(|e| e.trace_sha256.clone());
        counterexample = Some(Counterexample {
            class: c.class.clone(),
            seed: c.seed,
            found_at: c.found_at,
            found: Point {
                q: c.q.clone(),
                values: values_of(params, &c.q),
            },
            minimised: Point {
                q: cx.clone(),
                values: values_of(params, &cx),
            },
            registered: Point {
                q: registered.clone(),
                values: values_of(params, &registered),
            },
            active: c.active_parameters.clone(),
            // Completed once the canonical writer has run.
            byte_reproduced: discovery_run.first().is_some_and(|p| p.violated())
                && logged_trace.as_deref() == Some(trace.as_str()),
            trace_sha256: trace,
            replication,
            refutes,
        });
        // 4. Attribution, paired by seed with the replication probes.
        let cx_viol: BTreeMap<u64, bool> = replication_probes
            .iter()
            .filter(|p| p.error.is_none())
            .map(|p| (p.seed, p.violated()))
            .collect();
        let reg_v = values_of(params, &registered);
        let cx_v = values_of(params, &cx);
        for (i, a) in claim.assumptions.iter().enumerate() {
            let name = &a.parameter.name;
            let mut f = Factor {
                name: name.clone(),
                unit: a.parameter.unit.clone(),
                registered: reg_v[i],
                counterexample: cx_v[i],
                necessity: (0, 0),
                sufficiency: (0, 0),
                role: "not_required".into(),
            };
            if cx[i] != registered[i] {
                for p in by("attribution", &format!("revert:{name}/")) {
                    if p.error.is_none() && cx_viol.get(&p.seed) == Some(&true) {
                        f.necessity.1 += 1;
                        f.necessity.0 += u64::from(!p.violated());
                    }
                }
                let iso: Vec<&Probe> = by("attribution", &format!("isolate:{name}/"))
                    .into_iter()
                    .filter(|p| p.error.is_none())
                    .collect();
                f.sufficiency = (
                    iso.iter().filter(|p| p.violated()).count() as u64,
                    iso.len() as u64,
                );
                let necessary = f.necessity.1 > 0 && frac(f.necessity) >= ROLE_THRESHOLD;
                let sufficient = f.sufficiency.1 > 0 && frac(f.sufficiency) >= ROLE_THRESHOLD;
                f.role = match (necessary, sufficient) {
                    (true, true) => "necessary_and_sufficient",
                    (true, false) => "necessary",
                    (false, true) => "sufficient",
                    (false, false) => "contributing",
                }
                .into();
            }
            attribution.push(f);
        }
        // 5. Envelope.
        let (dims, points) = envelope_points(claim, &cx);
        let grid = lattice(claim.budget.envelope_levels);
        let axes: Vec<Axis> = dims
            .iter()
            .map(|&d| {
                let p = &params[d];
                Axis {
                    name: p.name.clone(),
                    unit: p.unit.clone(),
                    values: grid
                        .iter()
                        .map(|&g| snap(p, scale(p, g as f64 / Q as f64)))
                        .collect(),
                }
            })
            .collect();
        let fixed = params
            .iter()
            .enumerate()
            .filter(|(i, _)| !dims.contains(i))
            .map(|(i, p)| (p.name.clone(), cx_v[i]))
            .collect();
        let env_of = |tag: &str| -> Vec<&Probe> { by("envelope", &format!("{tag}/")) };
        let none = env_of("none");
        let levels = claim.budget.envelope_levels as usize;
        let per_cell = claim.budget.envelope_seeds as usize;
        let width = if dims.len() == 1 { 1 } else { levels };
        let mut cells = vec![vec![0u64; width]; levels];
        let mut clean = 0u64;
        for (ci, chunk) in none.chunks(per_cell).enumerate() {
            let k = chunk.iter().filter(|p| p.violated()).count() as u64;
            cells[ci / width][ci % width] = k;
            if k == 0 && chunk.iter().all(|p| p.error.is_none()) {
                clean += 1;
            }
        }
        envelope = Some(Envelope {
            axes,
            fixed,
            seeds: per_cell as u64,
            cells,
            errors: none.iter().filter(|p| p.error.is_some()).count() as u64,
            clean_cells: (clean, points.len() as u64),
        });
        // 6. Mechanism interventions.
        for h in &claim.hypotheses {
            let mut results = Vec::new();
            for i in &h.interventions {
                let control = by("mechanism", &format!("{}/{}/control/", h.id, i.id));
                let treated = by("mechanism", &format!("{}/{}/treated/", h.id, i.id));
                let (mut b, mut c2) = (0u64, 0u64);
                for (x, y) in control.iter().zip(&treated) {
                    if x.error.is_some() || y.error.is_some() {
                        continue;
                    }
                    match (x.violated(), y.violated()) {
                        (true, false) => b += 1,
                        (false, true) => c2 += 1,
                        _ => {}
                    }
                }
                let tr = rate(&treated);
                let predicted = match i.predicts {
                    Expect::Holds => 1.0 - tr.rate,
                    Expect::Violated => tr.rate,
                };
                let p = mcnemar_exact(b, c2);
                let direction = match i.predicts {
                    Expect::Holds => b > c2,
                    Expect::Violated => c2 > b,
                };
                let region = paired(
                    &none,
                    &by("mechanism", &format!("{}/{}/region/", h.id, i.id)),
                    false,
                );
                let (moved, could) = match i.predicts {
                    Expect::Holds => (region.fixed, region.fixed + region.both),
                    Expect::Violated => (region.broken, region.broken + region.neither),
                };
                let region_status = if could == 0 {
                    "untested"
                } else if frac((moved, could)) >= ROLE_THRESHOLD {
                    "general"
                } else {
                    "local"
                };
                let at_point = predicted >= ROLE_THRESHOLD && p < ALPHA && direction;
                let status = if tr.n == 0 {
                    "not_run"
                } else if at_point && region_status != "local" {
                    "supported"
                } else if at_point {
                    "supported_locally"
                } else if predicted <= 1.0 - ROLE_THRESHOLD {
                    "contradicted"
                } else {
                    "inconclusive"
                };
                results.push(InterventionResult {
                    id: i.id.clone(),
                    description: i.description.clone(),
                    at: i.at,
                    predicts: i.predicts,
                    control: rate(&control),
                    treated: tr,
                    discordant: (b, c2),
                    mcnemar_p: p,
                    region,
                    region_status: region_status.into(),
                    status: status.into(),
                });
            }
            mechanism.push(HypothesisResult {
                id: h.id.clone(),
                statement: h.statement.clone(),
                interventions: results,
                trace_checks: Vec::new(),
                status: String::new(),
            });
        }
        // 7. Mitigations on the claim side, paired with the unmitigated probes.
        let base_refs: Vec<&Probe> = baseline_probes.iter().collect();
        for m in &claim.mitigations {
            let tag = format!("mitigation:{}", m.id);
            let with = env_of(&tag);
            let mut envelope_cells = vec![vec![(0u64, 0u64, 0u64); width]; levels];
            for (ci, (b, a)) in none.chunks(per_cell).zip(with.chunks(per_cell)).enumerate() {
                let pr = paired(b, a, false);
                envelope_cells[ci / width][ci % width] = (pr.fixed, pr.broken, pr.both);
            }
            mitigations.push(MitigationResult {
                envelope_cells,
                id: m.id.clone(),
                title: m.title.clone(),
                rationale: m.rationale.clone(),
                counterexample: paired(
                    &replication_probes,
                    &by("mitigation", &format!("{}/counterexample/", m.id)),
                    false,
                ),
                envelope: paired(&none, &env_of(&tag), false),
                registered: paired(
                    &base_refs,
                    &by("mitigation", &format!("{}/registered/", m.id)),
                    true,
                ),
                families: Vec::new(),
                rechallenge: Rechallenge::default(),
                regression_upper_bound: 1.0,
                regressions: 0,
                status: String::new(),
            });
        }
        // Runs whose full artifacts the package keeps.
        let mut keep = |name: String, q: &[u64], applied: Vec<String>, description: String| {
            artifacts.insert(
                name,
                ArtifactRef {
                    family: "claim".into(),
                    q: q.to_vec(),
                    applied,
                    seed: c.seed,
                    description,
                    files: BTreeMap::new(),
                },
            );
        };
        keep(
            "counterexample".into(),
            &cx,
            vec![],
            "The minimised counterexample on its discovery seed.".into(),
        );
        keep(
            "registered".into(),
            &registered,
            vec![],
            "The registered conditions on the same seed.".into(),
        );
        let most_necessary = attribution
            .iter()
            .enumerate()
            .filter(|(_, f)| f.necessity.1 > 0)
            .max_by(|(ia, a), (ib, b)| {
                frac(a.necessity)
                    .total_cmp(&frac(b.necessity))
                    .then(ib.cmp(ia))
            });
        if let Some((i, f)) = most_necessary {
            let mut twin = cx.clone();
            twin[i] = registered[i];
            keep(
                "twin".into(),
                &twin,
                vec![],
                format!(
                    "Counterfactual twin: the counterexample with {} at its registered value.",
                    f.name
                ),
            );
        }
        for m in &claim.mitigations {
            keep(
                format!("mitigation-{}", m.id),
                &cx,
                vec![format!("mitigation:{}", m.id)],
                format!("The counterexample with the mitigation {}.", m.title),
            );
        }
        probes.extend(got);
    } else {
        open_risks.push(format!(
            "No counterexample of {} in {} challenge evaluations. That bounds the violation rate under uniform sampling of the envelope; it does not show that the claim holds.",
            claim.property, challenge.evaluations
        ));
    }

    // Regression families, independent of the counterexample.
    let reg_plan = plan_regression(claim);
    let total = reg_plan.len() as u64;
    report(progress, "regression", 0, total);
    let reg_probes = s.run_all(&reg_plan, threads);
    report(progress, "regression", total, total);
    for m in &mut mitigations {
        let tag = format!("mitigation:{}", m.id);
        for f in &claim.regression {
            let before: Vec<&Probe> = reg_probes
                .iter()
                .filter(|p| p.family == f.id && p.applied.is_empty())
                .collect();
            let after: Vec<&Probe> = reg_probes
                .iter()
                .filter(|p| p.family == f.id && p.applied.first() == Some(&tag))
                .collect();
            m.families.push(FamilyResult {
                id: f.id.clone(),
                title: f.title.clone(),
                paired: paired(&before, &after, true),
            });
        }
    }
    probes.extend(reg_probes);

    // Trace checks read the counterexample runs through the canonical writer.
    if let Some(cx) = &counterexample {
        let seeds = eval_seeds(claim, claim.budget.mechanism_seeds);
        for (h, r) in claim.hypotheses.iter().zip(mechanism.iter_mut()) {
            for t in &h.trace_checks {
                r.trace_checks
                    .push(trace_check(s, &cx.minimised.q, &seeds, t)?);
            }
        }
    }
    for r in &mut mechanism {
        let st: Vec<&str> = r
            .interventions
            .iter()
            .map(|i| i.status.as_str())
            .chain(r.trace_checks.iter().map(|t| t.status.as_str()))
            .collect();
        r.status = if st.is_empty() {
            "untested"
        } else if st.contains(&"contradicted") {
            "contradicted"
        } else if st.iter().all(|x| *x == "supported") {
            "experimentally_supported"
        } else if st
            .iter()
            .all(|x| *x == "supported" || *x == "supported_locally")
        {
            "supported_only_locally"
        } else {
            "unresolved"
        }
        .into();
    }
    for m in &mut mitigations {
        let run = rechallenges.get(&m.id).ok_or(format!(
            "the re-challenge of mitigation {} is missing",
            m.id
        ))?;
        m.rechallenge = rechallenge_of(&claim.property, run);
        let regress = |p: &Paired| -> u64 {
            p.new_violations
                .iter()
                .filter(|(k, _)| !k.starts_with("requirement:") || **k == claim.property)
                .map(|(_, v)| *v)
                .sum()
        };
        m.regressions = m.envelope.broken
            + regress(&m.registered)
            + m.families.iter().map(|f| regress(&f.paired)).sum::<u64>();
        let pairs =
            m.envelope.n + m.registered.n + m.families.iter().map(|f| f.paired.n).sum::<u64>();
        m.regression_upper_bound = clopper_pearson(m.regressions.min(pairs), pairs, 0.95).1;
        let violated = m.counterexample.fixed + m.counterexample.both;
        let effective = violated > 0 && frac((m.counterexample.fixed, violated)) >= EFFECTIVE;
        m.status = match (effective, m.regressions, m.rechallenge.property_violations) {
            (false, _, _) => "ineffective",
            (true, 0, 0) => "effective_no_regression_observed",
            (true, 0, _) => "effective_with_residual_counterexamples",
            (true, _, _) => "effective_with_regressions",
        }
        .into();
    }

    // Verdict.
    let claim_status = match &counterexample {
        Some(c) if c.refutes && c.byte_reproduced => "refuted",
        Some(c) if c.refutes => "refuted_without_byte_reproduction",
        Some(_) => "counterexample_within_tolerance",
        None => "not_refuted_within_budget",
    };
    if let Some(e) = &envelope
        && e.clean_cells.0 < e.clean_cells.1
    {
        open_risks.push(format!(
            "The property is violated or untested in {} of {} envelope cells; the claim can hold at most on the rest, at this resolution and with {} seeds per cell.",
            e.clean_cells.1 - e.clean_cells.0,
            e.clean_cells.1,
            e.seeds
        ));
    }
    for h in &mechanism {
        if h.status != "experimentally_supported" {
            open_risks.push(format!("Mechanism {} is {}.", h.id, h.status));
        }
    }
    for m in &mitigations {
        if m.status != "effective_no_regression_observed" {
            open_risks.push(format!("Mitigation {} is {}.", m.id, m.status));
        }
    }
    if !challenge.other_classes.is_empty() {
        open_risks.push(format!(
            "The challenge also found {} failure classes without the claim property; they are listed, not investigated.",
            challenge.other_classes.len()
        ));
    }
    if baseline.errors > 0 {
        open_risks.push(format!(
            "{} baseline runs failed with an error.",
            baseline.errors
        ));
    }
    open_risks.push(match claim.evidence_grade {
        Grade::Exploratory => "Exploratory simulation evidence on development seeds. It is not a confirmation and says nothing about a real vehicle.".into(),
        Grade::Confirmatory => "Confirmatory grade under the frozen preregistration, still simulation evidence only.".into(),
    });
    if probes.len() as u64 > MAX_PROBES {
        return Err(format!(
            "the investigation needs more than {MAX_PROBES} probes"
        ));
    }
    let verdict = Verdict {
        claim: claim_status.into(),
        mechanism: mechanism
            .iter()
            .map(|h| (h.id.clone(), h.status.clone()))
            .collect(),
        mitigations: mitigations
            .iter()
            .map(|m| (m.id.clone(), m.status.clone()))
            .collect(),
        evidence_grade: claim.evidence_grade,
        open_risks,
    };
    Ok(Computed {
        probes,
        findings: Findings {
            baseline_within_tolerance: baseline.n > 0 && baseline.rate <= claim.tolerance,
            baseline,
            challenge,
            counterexample,
            attribution,
            envelope,
            mechanism,
            mitigations,
            verdict,
        },
        artifacts,
    })
}

fn signal_of(sample: &Value, t: &TraceCheck) -> Option<f64> {
    let num = |v: &Value| match v {
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Value::Number(n) => n.as_f64(),
        _ => None,
    };
    let a = num(sample.pointer(&t.pointer)?)?;
    match &t.minus {
        Some(m) => Some(a - num(sample.pointer(m)?)?),
        None => Some(a),
    }
}

fn trace_check(
    s: &Session,
    q: &[u64],
    seeds: &[u64],
    t: &TraceCheck,
) -> Result<TraceCheckResult, String> {
    let scratch = tempdir("trace-check")?;
    let result = (|| {
        let mut held = 0u64;
        let mut max_abs = Vec::new();
        for &seed in seeds {
            let case = s.case(&req("trace", String::new(), q, &[], seed))?;
            let case_path = scratch.join(format!("case-{seed}.json"));
            fs::write(&case_path, &case).map_err(|e| e.to_string())?;
            let out = scratch.join(format!("out-{seed}"));
            s.domain.write(&case_path, seed, &out)?;
            let bytes = read_capped(&out.join(s.domain.trace_file()), 256 * 1024 * 1024)?;
            let trace: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
            let samples = trace
                .pointer(&t.samples)
                .and_then(Value::as_array)
                .ok_or(format!("trace check {}: {} is not a list", t.id, t.samples))?;
            let vals: Vec<f64> = samples.iter().filter_map(|x| signal_of(x, t)).collect();
            if vals.is_empty() {
                return Err(format!("trace check {}: no sample has {}", t.id, t.pointer));
            }
            let m = vals.iter().fold(0.0f64, |a, &b| a.max(b.abs()));
            let ok = match t.predicate {
                Predicate::NeverTrue => vals.iter().all(|&v| v == 0.0),
                Predicate::EverTrue => vals.iter().any(|&v| v != 0.0),
                Predicate::MaxAbsBelow => m < t.threshold.unwrap_or(0.0),
                Predicate::MaxAbsAtLeast => m >= t.threshold.unwrap_or(0.0),
            };
            held += u64::from(ok);
            max_abs.push(m);
        }
        Ok((held, max_abs))
    })();
    let _ = fs::remove_dir_all(&scratch);
    let (held, max_abs) = result?;
    let n = seeds.len() as u64;
    let status = if n == 0 {
        "not_run"
    } else if frac((held, n)) >= ROLE_THRESHOLD {
        "supported"
    } else if frac((held, n)) <= 1.0 - ROLE_THRESHOLD {
        "contradicted"
    } else {
        "inconclusive"
    };
    Ok(TraceCheckResult {
        id: t.id.clone(),
        description: t.description.clone(),
        held: (held, n),
        max_abs,
        status: status.into(),
    })
}

fn tempdir(tag: &str) -> Result<PathBuf, String> {
    use std::sync::atomic::AtomicU64;
    static N: AtomicU64 = AtomicU64::new(0);
    let d = std::env::temp_dir().join(format!(
        "vv-investigate-{tag}-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed)
    ));
    if d.exists() {
        fs::remove_dir_all(&d).map_err(|e| e.to_string())?;
    }
    fs::create_dir_all(&d).map_err(|e| format!("{}: {e}", d.display()))?;
    Ok(d)
}

fn write_artifacts(
    s: &Session,
    root: &Path,
    artifacts: &mut BTreeMap<String, ArtifactRef>,
) -> Result<(), String> {
    let base = root.join("artifacts");
    fs::create_dir_all(&base).map_err(|e| format!("{}: {e}", base.display()))?;
    for (name, a) in artifacts.iter_mut() {
        let r = Request {
            stage: "artifact",
            key: name.clone(),
            family: a.family.clone(),
            q: a.q.clone(),
            applied: a.applied.clone(),
            seed: a.seed,
        };
        let case = s.case(&r)?;
        let dir = base.join(name);
        let staging = base.join(format!("{name}.input.json"));
        crate::engine::write_new(&staging, &case)?;
        let written = s.domain.write(&staging, a.seed, &dir);
        fs::remove_file(&staging).map_err(|e| e.to_string())?;
        written?;
        let signals = crate::signals::extract(s.domain.id(), &dir)?;
        crate::engine::write_new(&dir.join("signals.json"), &pretty(&signals))?;
        let mut files = BTreeMap::new();
        walk(&dir, &dir, &mut files)?;
        a.files = files;
    }
    Ok(())
}

fn pretty<T: Serialize>(v: &T) -> Vec<u8> {
    let mut b = serde_json::to_vec_pretty(v).expect("serialisable");
    b.push(b'\n');
    b
}

fn assumptions_view(s: &Session) -> Result<Vec<Value>, String> {
    let registered = search::nominal(&s.base, &s.params)?;
    Ok(s.claim
        .assumptions
        .iter()
        .zip(values_of(&s.params, &registered))
        .map(|(a, v)| {
            json!({
                "name": a.parameter.name, "pointer": a.parameter.pointer,
                "unit": a.parameter.unit, "low": a.parameter.low, "high": a.parameter.high,
                "registered": v, "description": a.description,
            })
        })
        .collect())
}

/// Runs an investigation into `out`, which must not exist. The package is assembled in a sibling
/// `.partial` directory and renamed into place only when complete, so an interrupted run never
/// leaves a package that looks finished.
pub fn execute(
    inputs: &Inputs,
    out: &Path,
    threads: usize,
    progress: Progress,
) -> Result<Package, String> {
    crate::engine::guard_output(out)?;
    if out.exists() {
        return Err(format!("{} already exists", out.display()));
    }
    let s = Session::new(inputs)?;
    let start = Instant::now();
    let partial = out.with_extension("partial");
    if partial.exists() {
        return Err(format!(
            "{} exists: an earlier investigation was interrupted; remove it to start again",
            partial.display()
        ));
    }
    fs::create_dir_all(&partial).map_err(|e| format!("{}: {e}", partial.display()))?;
    let lock = crate::engine::lock_output(&partial)?;
    report(
        progress,
        "challenge",
        0,
        u64::from(s.claim.budget.challenge),
    );
    let search_dir = partial.join("challenge");
    let search_result = search::execute(
        &s.challenge_spec(),
        &inputs.base_bytes,
        &search_dir,
        threads,
    )?;
    report(
        progress,
        "challenge",
        search_result.total_evaluations,
        search_result.total_evaluations,
    );
    let log_text =
        fs::read_to_string(search_dir.join("evaluations.jsonl")).map_err(|e| e.to_string())?;
    let log = search::parse_log(&log_text)?;
    let search_sha = search_result.log_sha256.clone();
    let mut rechallenges = BTreeMap::new();
    for m in &s.claim.mitigations {
        report(progress, &format!("re-challenge {}", m.id), 0, 1);
        let (spec, base) = s.rechallenge_inputs(m)?;
        let dir = partial.join("rechallenge").join(&m.id);
        if let Some(parent) = dir.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        search::execute(&spec, &base, &dir, threads)?;
        rechallenges.insert(m.id.clone(), read_search(&dir)?);
        report(progress, &format!("re-challenge {}", m.id), 1, 1);
    }
    let mut c = compute(
        &s,
        &search_result,
        &log,
        search_sha,
        &rechallenges,
        threads,
        progress,
    )?;
    report(progress, "artifacts", 0, c.artifacts.len() as u64);
    write_artifacts(&s, &partial, &mut c.artifacts)?;
    finish_reproduction(&s, &mut c);
    let mut probe_log = String::new();
    for p in &c.probes {
        probe_log.push_str(&probe_line(p));
    }
    let package = Package {
        schema: PACKAGE_SCHEMA.into(),
        engine: concat!("vv-exec ", env!("CARGO_PKG_VERSION")).into(),
        claim_id: s.claim.id.clone(),
        title: s.claim.title.clone(),
        statement: s.claim.statement.clone(),
        origin: s.claim.origin.clone(),
        property: s.claim.property.clone(),
        tolerance: s.claim.tolerance,
        domain: s.claim.domain.clone(),
        assumptions: assumptions_view(&s)?,
        claim_sha256: sha256_hex(&inputs.claim_bytes),
        base_case_sha256: sha256_hex(&inputs.base_bytes),
        family_case_sha256: s
            .claim
            .regression
            .iter()
            .zip(&inputs.families)
            .map(|(f, b)| (f.id.clone(), sha256_hex(b)))
            .collect(),
        source_sha256: s.domain.source_sha256(),
        probes: c.probes.len() as u64,
        probes_sha256: sha256_hex(probe_log.as_bytes()),
        rules: rules(),
        artifacts: c.artifacts,
        findings: c.findings,
    };
    let w = |name: &str, b: &[u8]| crate::engine::write_new(&partial.join(name), b);
    w("claim.json", &inputs.claim_bytes)?;
    w("base-case.json", &inputs.base_bytes)?;
    if !s.claim.regression.is_empty() {
        fs::create_dir_all(partial.join("families")).map_err(|e| e.to_string())?;
    }
    for (f, b) in s.claim.regression.iter().zip(&inputs.families) {
        w(&format!("families/{}.json", f.id), b)?;
    }
    if let Some(b) = &inputs.preregistration {
        w("preregistration.txt", b)?;
    }
    w("probes.jsonl", probe_log.as_bytes())?;
    w("investigation.json", &pretty(&package))?;
    w(
        "timing.json",
        &pretty(&json!({
            "wall_s": start.elapsed().as_secs_f64(),
            "threads": threads,
            "note": "Measured outside the simulation. Not evidence; excluded from verification."
        })),
    )?;
    drop(lock);
    let _ = fs::remove_file(partial.join(".lock"));
    let mut manifest = manifest_of(&partial)?;
    manifest.remove("timing.json");
    w("manifest.json", &pretty(&manifest))?;
    fs::rename(&partial, out)
        .map_err(|e| format!("{} -> {}: {e}", partial.display(), out.display()))?;
    Ok(package)
}

/// Byte reproduction holds only when the search log, the in-process rerun and the canonical
/// writer agree on the counterexample trace.
fn finish_reproduction(s: &Session, c: &mut Computed) {
    if let Some(cx) = &mut c.findings.counterexample {
        let written = c
            .artifacts
            .get("counterexample")
            .and_then(|a| a.files.get(s.domain.trace_file()))
            .cloned()
            .unwrap_or_default();
        cx.byte_reproduced = cx.byte_reproduced && written == cx.trace_sha256;
        if !cx.byte_reproduced && c.findings.verdict.claim == "refuted" {
            c.findings.verdict.claim = "refuted_without_byte_reproduction".into();
        }
    }
}

fn walk(dir: &Path, root: &Path, out: &mut BTreeMap<String, String>) -> Result<(), String> {
    let mut entries: Vec<_> = fs::read_dir(dir)
        .map_err(|e| format!("{}: {e}", dir.display()))?
        .filter_map(Result::ok)
        .collect();
    entries.sort_by_key(|e| e.file_name());
    for e in entries {
        let p = e.path();
        let ft = e.file_type().map_err(|e| e.to_string())?;
        if ft.is_symlink() {
            return Err(format!(
                "{} is a link; a package holds plain files only",
                p.display()
            ));
        }
        if ft.is_dir() {
            walk(&p, root, out)?;
        } else {
            let rel = p
                .strip_prefix(root)
                .map_err(|e| e.to_string())?
                .to_string_lossy()
                .replace('\\', "/");
            let b = fs::read(&p).map_err(|e| format!("{}: {e}", p.display()))?;
            out.insert(rel, sha256_hex(&b));
        }
    }
    Ok(())
}

fn manifest_of(dir: &Path) -> Result<BTreeMap<String, String>, String> {
    let mut m = BTreeMap::new();
    walk(dir, dir, &mut m)?;
    Ok(m)
}

// ---------------------------------------------------------------------------------------------
// Verification: recompute everything, trust nothing stored.

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Check {
    pub id: String,
    pub pass: bool,
    pub detail: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct Verification {
    pub schema: String,
    pub claim_id: String,
    pub probes_recomputed: u64,
    pub checks: Vec<Check>,
    pub pass: bool,
}

fn same_probe(a: &Probe, b: &Probe) -> bool {
    let mut x = a.clone();
    let mut y = b.clone();
    x.metric = None;
    y.metric = None;
    x == y
        && match (a.metric, b.metric) {
            (None, None) => true,
            (Some(u), Some(v)) => u == v || (u - v).abs() <= 1e-15 * u.abs().max(v.abs()),
            _ => false,
        }
}

fn same_value(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(x), Value::Number(y)) => match (x.as_f64(), y.as_f64()) {
            (Some(u), Some(v)) => u == v || (u - v).abs() <= 1e-12 * u.abs().max(v.abs()),
            _ => x == y,
        },
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(a, b)| same_value(a, b))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len()
                && x.iter()
                    .zip(y)
                    .all(|((ka, va), (kb, vb))| ka == kb && same_value(va, vb))
        }
        _ => a == b,
    }
}

fn differing_keys(a: &Value, b: &Value) -> Vec<String> {
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            let keys: BTreeSet<&String> = x.keys().chain(y.keys()).collect();
            keys.into_iter()
                .filter(|k| match (x.get(*k), y.get(*k)) {
                    (Some(u), Some(v)) => !same_value(u, v),
                    _ => true,
                })
                .cloned()
                .collect()
        }
        _ => vec!["(root)".into()],
    }
}

/// Recomputes a package. Every check is reported; `pass` is their conjunction.
pub fn verify(dir: &Path, threads: usize, progress: Progress) -> Result<Verification, String> {
    let mut checks: Vec<Check> = Vec::new();
    let mut check = |id: &str, pass: bool, detail: String| {
        checks.push(Check {
            id: id.into(),
            pass,
            detail,
        });
    };
    let read = |name: &str| read_capped(&dir.join(name), 512 * 1024 * 1024);
    // 1. Manifest: no file missing, unlisted or changed.
    let stored_manifest: BTreeMap<String, String> = serde_json::from_slice(&read("manifest.json")?)
        .map_err(|e| format!("manifest.json: {e}"))?;
    let mut actual = manifest_of(dir)?;
    actual.remove("manifest.json");
    actual.remove("timing.json");
    let missing: Vec<&String> = stored_manifest
        .keys()
        .filter(|k| !actual.contains_key(*k))
        .collect();
    let extra: Vec<&String> = actual
        .keys()
        .filter(|k| !stored_manifest.contains_key(*k))
        .collect();
    let changed: Vec<&String> = stored_manifest
        .iter()
        .filter(|(k, v)| actual.get(*k).is_some_and(|a| a != *v))
        .map(|(k, _)| k)
        .collect();
    check(
        "manifest",
        missing.is_empty() && extra.is_empty() && changed.is_empty(),
        format!(
            "{} files; missing {missing:?}, unlisted {extra:?}, changed {changed:?}",
            stored_manifest.len()
        ),
    );
    let package: Package = serde_json::from_slice(&read("investigation.json")?)
        .map_err(|e| format!("investigation.json: {e}"))?;
    let claim_bytes = read("claim.json")?;
    let claim = Claim::parse(&claim_bytes)?;
    let families = claim
        .regression
        .iter()
        .map(|f| read(&format!("families/{}.json", f.id)))
        .collect::<Result<Vec<_>, _>>()?;
    let preregistration = match claim.preregistration {
        Some(_) => Some(read("preregistration.txt")?),
        None => None,
    };
    let inputs = Inputs {
        claim_bytes,
        base_bytes: read("base-case.json")?,
        families,
        preregistration,
    };
    // 2. Inputs, grade and build.
    let fam_ok = claim
        .regression
        .iter()
        .zip(&inputs.families)
        .all(|(f, b)| package.family_case_sha256.get(&f.id) == Some(&sha256_hex(b)))
        && package.family_case_sha256.len() == claim.regression.len();
    check(
        "inputs",
        package.claim_sha256 == sha256_hex(&inputs.claim_bytes)
            && package.base_case_sha256 == sha256_hex(&inputs.base_bytes)
            && fam_ok,
        "claim, base case and family cases match the hashes the package states".into(),
    );
    let s = match Session::new(&inputs) {
        Ok(s) => s,
        Err(e) => {
            check("claim", false, e);
            return Ok(conclude(&claim.id, 0, checks));
        }
    };
    check(
        "evidence_grade",
        package.findings.verdict.evidence_grade == s.claim.evidence_grade,
        format!(
            "stated {:?}; the claim and its preregistration allow {:?}",
            package.findings.verdict.evidence_grade, s.claim.evidence_grade
        ),
    );
    let source = s.domain.source_sha256();
    check(
        "source",
        package.source_sha256 == source,
        format!("package {}, this build {source}", package.source_sha256),
    );
    // 3. The challenge search, recomputed by search::verify, and derived from the claim alone.
    let search_dir = dir.join("challenge");
    let sv = search::verify(&search_dir, threads)?;
    let spec_ok = read("challenge/spec.json")? == s.challenge_spec()
        && read("challenge/base-case.json")? == inputs.base_bytes;
    check(
        "challenge",
        sv.pass && spec_ok,
        format!(
            "{} search evaluations recomputed; log reproduced {}; specification derived from the claim {spec_ok}",
            sv.evaluations, sv.log_reproduced
        ),
    );
    let search_bytes = read("challenge/search.json")?;
    let search_result: search::SearchResult =
        serde_json::from_slice(&search_bytes).map_err(|e| format!("search.json: {e}"))?;
    let log = search::parse_log(
        &String::from_utf8(read("challenge/evaluations.jsonl")?)
            .map_err(|_| "the search log is not UTF-8")?,
    )?;
    // 3b. Each re-challenge, recomputed, and derived from the claim and its mitigation alone.
    let mut rechallenges = BTreeMap::new();
    for m in &s.claim.mitigations {
        let sub = dir.join("rechallenge").join(&m.id);
        let (spec, base) = s.rechallenge_inputs(m)?;
        let rv = search::verify(&sub, threads)?;
        let derived = read(&format!("rechallenge/{}/spec.json", m.id))? == spec
            && read(&format!("rechallenge/{}/base-case.json", m.id))? == base;
        check(
            &format!("rechallenge:{}", m.id),
            rv.pass && derived,
            format!(
                "{} search evaluations recomputed; derived from the claim and the mitigation {derived}",
                rv.evaluations
            ),
        );
        rechallenges.insert(m.id.clone(), read_search(&sub)?);
    }
    // 4. Every probe recomputed from the plan; the stored log must equal the recomputed one.
    report(progress, "verify", 0, package.probes);
    let mut c = compute(
        &s,
        &search_result,
        &log,
        search_result.log_sha256.clone(),
        &rechallenges,
        threads,
        progress,
    )?;
    let text = String::from_utf8(read("probes.jsonl")?).map_err(|_| "probes.jsonl is not UTF-8")?;
    let (log_ok, detail) = match parse_probes(&text) {
        Err(e) => (false, e),
        Ok(l) => {
            let differ = l
                .iter()
                .zip(&c.probes)
                .filter(|(a, b)| !same_probe(a, b))
                .count();
            let keys: BTreeSet<(&str, &str, &str)> = l
                .iter()
                .map(|p| (p.stage.as_str(), p.family.as_str(), p.key.as_str()))
                .collect();
            (
                l.len() == c.probes.len() && differ == 0 && keys.len() == l.len(),
                format!(
                    "{} logged, {} recomputed, {differ} differ, {} repeated keys",
                    l.len(),
                    c.probes.len(),
                    l.len() - keys.len()
                ),
            )
        }
    };
    check("probes", log_ok, detail);
    check(
        "probe_count",
        package.probes == c.probes.len() as u64
            && package.probes_sha256 == sha256_hex(text.as_bytes()),
        format!(
            "stated {} probes, recomputed {}; log hash as stated {}",
            package.probes,
            c.probes.len(),
            package.probes_sha256 == sha256_hex(text.as_bytes())
        ),
    );
    // 5. Artifacts rewritten by the canonical writer, compared byte for byte.
    let scratch = tempdir("verify")?;
    let written = write_artifacts(&s, &scratch, &mut c.artifacts);
    let _ = fs::remove_dir_all(&scratch);
    written?;
    finish_reproduction(&s, &mut c);
    let art_ok = c.artifacts == package.artifacts
        && c.artifacts.iter().all(|(name, a)| {
            a.files
                .iter()
                .all(|(f, h)| stored_manifest.get(&format!("artifacts/{name}/{f}")) == Some(h))
        });
    check(
        "artifacts",
        art_ok,
        format!(
            "{} runs rewritten by the canonical writer and compared with the package",
            c.artifacts.len()
        ),
    );
    // 6. Findings and verdict recomputed and compared with what the package states.
    let stated = serde_json::to_value(&package.findings).map_err(|e| e.to_string())?;
    let recomputed = serde_json::to_value(&c.findings).map_err(|e| e.to_string())?;
    let diff = differing_keys(&stated, &recomputed);
    check(
        "findings",
        diff.is_empty(),
        if diff.is_empty() {
            "every number and verdict recomputed from the probes".into()
        } else {
            format!("the stated findings differ from the recomputation in {diff:?}")
        },
    );
    let header_ok = package.schema == PACKAGE_SCHEMA
        && package.claim_id == s.claim.id
        && package.property == s.claim.property
        && package.statement == s.claim.statement
        && package.title == s.claim.title
        && package.origin == s.claim.origin
        && package.domain == s.claim.domain
        && package.tolerance == s.claim.tolerance
        && package.rules == rules()
        && package.assumptions == assumptions_view(&s)?;
    check(
        "statement",
        header_ok,
        "the claim, envelope and rules the package states are those of claim.json and this engine"
            .into(),
    );
    Ok(conclude(&s.claim.id, c.probes.len() as u64, checks))
}

fn conclude(claim_id: &str, n: u64, checks: Vec<Check>) -> Verification {
    let pass = checks.iter().all(|c| c.pass);
    Verification {
        schema: VERIFICATION_SCHEMA.into(),
        claim_id: claim_id.into(),
        probes_recomputed: n,
        checks,
        pass,
    }
}

/// A claim as Studio lists it, without running anything.
pub fn describe(inputs: &Inputs) -> Result<Value, String> {
    let s = Session::new(inputs)?;
    let c = &s.claim;
    Ok(json!({
        "id": c.id,
        "title": c.title,
        "statement": c.statement,
        "origin": c.origin,
        "domain": c.domain,
        "property": c.property,
        "tolerance": c.tolerance,
        "objective": c.objective,
        "assumptions": assumptions_view(&s)?,
        "seeds": c.seeds,
        "budget": c.budget,
        "strategy": strategy_name(&c.strategy),
        "hypotheses": c.hypotheses.iter().map(|h| json!({
            "id": h.id, "statement": h.statement,
            "interventions": h.interventions.iter().map(|i| json!({"id": i.id, "description": i.description, "predicts": i.predicts})).collect::<Vec<_>>(),
            "trace_checks": h.trace_checks.iter().map(|t| json!({"id": t.id, "description": t.description})).collect::<Vec<_>>(),
        })).collect::<Vec<_>>(),
        "mitigations": c.mitigations.iter().map(|m| json!({"id": m.id, "title": m.title, "rationale": m.rationale})).collect::<Vec<_>>(),
        "regression": c.regression.iter().map(|f| json!({"id": f.id, "title": f.title})).collect::<Vec<_>>(),
        "evidence_grade": c.evidence_grade,
        "claim_sha256": sha256_hex(&inputs.claim_bytes),
        "source_sha256": s.domain.source_sha256(),
        "rules": rules(),
    }))
}
