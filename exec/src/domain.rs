//! In-process domains. Each one calls the public functions of a canonical crate, the same ones its
//! command line calls, so a run here produces the bytes the command line would write. Nothing in
//! the canonical crates changes.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use serde_json::Value;
use vv_rocket::landing_model::{LandingCase, prepare_landing};
use vv_rocket::landing_run;
use vv_rocket::model;
use vv_rocket::run as rigid_run;
use vv_rocket::sha256_hex;

use crate::converge::{self, Convergence};
use crate::seeds::{Protected, ROCKET_PROTECTED};

/// The result of one in-process run: hashes of the canonical artifacts, the verdict and metrics.
#[derive(Clone, Debug, PartialEq)]
pub struct RunOutput {
    pub trace_sha256: String,
    /// `None` for a domain without a verification artifact.
    pub verification_sha256: Option<String>,
    /// Domain outcome, for example `landed`, `hard_landing`, `no_contact` or an end reason.
    pub outcome: String,
    /// Whether the outcome is the mission success of the domain (`landed` for the rocket,
    /// `completed` for the ground vehicle). `None` for a domain without a mission.
    pub mission_success: Option<bool>,
    /// `None` when the domain has no requirements or invariants.
    pub requirements_pass: Option<bool>,
    pub invariants_pass: Option<bool>,
    /// Numeric observables, by name. Every value is finite.
    pub metrics: BTreeMap<String, f64>,
    /// Identity of each violated property, sorted and without repeats: `invariant:<id>` for a
    /// safety invariant, `requirement:<id>` or `contract:<id>` for the others. Empty when every
    /// property holds. The search and the benchmark compare failures by these names only.
    pub violations: Vec<String>,
}

impl RunOutput {
    /// Mission success with every requirement and safety invariant met. `None` without a verdict.
    pub fn all_pass(&self) -> Option<bool> {
        match (
            self.mission_success,
            self.requirements_pass,
            self.invariants_pass,
        ) {
            (Some(m), Some(r), Some(i)) => Some(m && r && i),
            _ => None,
        }
    }
}

/// Why a run produced no artifacts. `Input` is a rejected case; `Simulation` is a failed run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RunError {
    Input(String),
    Simulation(String),
}

impl std::fmt::Display for RunError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RunError::Input(m) => write!(f, "input: {m}"),
            RunError::Simulation(m) => write!(f, "simulation: {m}"),
        }
    }
}

pub trait Domain: Sync {
    fn id(&self) -> &'static str;
    /// Whether runs take a seed. A domain without one runs each cell once.
    fn seeded(&self) -> bool;
    fn protected(&self) -> &'static [Protected];
    /// Checks a case with the canonical validation, without simulating.
    fn validate(&self, case: &[u8], seed: u64) -> Result<(), String>;
    fn run(&self, case: &[u8], seed: u64) -> Result<RunOutput, RunError>;
    /// Writes the canonical artifacts with the canonical writer, never overwriting.
    fn write(&self, case_path: &Path, seed: u64, out: &Path) -> Result<(), String>;
    /// File names the canonical writer produces.
    fn files(&self) -> &'static [&'static str];
    /// Hash of the sources that determine the canonical behaviour.
    fn source_sha256(&self) -> String;
    /// Whether runs carry requirement and invariant verdicts.
    fn has_verdicts(&self) -> bool;
    /// The written file whose hash is `RunOutput::trace_sha256`.
    fn trace_file(&self) -> &'static str;
    /// The written file whose hash is `RunOutput::verification_sha256`, if any.
    fn verification_file(&self) -> Option<&'static str>;
    /// The written copy of the case, if the canonical writer keeps one.
    fn case_copy_file(&self) -> Option<&'static str>;
    /// Arguments of the canonical command line that writes the same artifacts into `out`. A domain
    /// whose command line takes several input files writes them under `staging` first.
    fn cli_args(
        &self,
        case_path: &Path,
        seed: u64,
        out: &Path,
        staging: &Path,
    ) -> Result<Vec<String>, String>;
    /// Arguments of the canonical command line that replays a written directory.
    fn cli_replay_args(&self, dir: &Path) -> Vec<String>;
    /// The source hash the canonical command line recorded in a written directory.
    fn written_source_sha256(&self, dir: &Path) -> Option<String>;
    /// Step-size convergence of a case. A domain without a numerical step study says why.
    fn convergence(&self, _case: &[u8], tolerance_m: f64) -> Result<Convergence, String> {
        Ok(converge::not_applicable(
            "this domain has no step-size study",
            tolerance_m,
        ))
    }
}

pub fn by_id(id: &str) -> Option<&'static dyn Domain> {
    match id {
        "rocket-landing" => Some(&RocketLanding),
        "rocket-rigid-body" => Some(&RocketRigidBody),
        "ground-m4" => Some(&crate::ground::GroundM4),
        _ => None,
    }
}

/// `source_sha256` of a JSON file written by a canonical command line.
pub fn json_source_sha256(path: &Path) -> Option<String> {
    let bytes = fs::read(path).ok()?;
    let v: Value = serde_json::from_slice(&bytes).ok()?;
    v["source_sha256"].as_str().map(String::from)
}

/// Closed-loop powered landing (M9, M10): `vv-rocket land`.
pub struct RocketLanding;

/// Open-loop 6-DOF rigid body (M8): `vv-rocket run`. No seed, no verdict.
pub struct RocketRigidBody;

fn insert_numbers(metrics: &mut BTreeMap<String, f64>, prefix: &str, v: &Value) {
    if let Value::Object(map) = v {
        for (k, x) in map {
            if let Some(f) = x.as_f64().filter(|f| f.is_finite()) {
                metrics.insert(format!("{prefix}{k}"), f);
            }
        }
    }
}

/// Requirement values and invariant worst values of a landing verification, by id.
fn verification_metrics(metrics: &mut BTreeMap<String, f64>, verification: &[u8]) {
    let Ok(v) = serde_json::from_slice::<Value>(verification) else {
        return;
    };
    for (list, field, prefix) in [
        ("requirements", "value", "requirement."),
        ("invariants", "worst_value", "invariant."),
    ] {
        for item in v[list].as_array().into_iter().flatten() {
            if let (Some(id), Some(x)) = (item["id"].as_str(), item[field].as_f64())
                && x.is_finite()
            {
                metrics.insert(format!("{prefix}{id}"), x);
            }
        }
    }
}

/// Failed requirements and invariants of a landing verification, by id.
fn verification_violations(verification: &[u8]) -> Vec<String> {
    let Ok(v) = serde_json::from_slice::<Value>(verification) else {
        return vec!["verification:unreadable".into()];
    };
    let mut out = Vec::new();
    for (list, prefix) in [
        ("requirements", "requirement:"),
        ("invariants", "invariant:"),
    ] {
        for item in v[list].as_array().into_iter().flatten() {
            if item["pass"] == Value::Bool(false)
                && let Some(id) = item["id"].as_str()
            {
                out.push(format!("{prefix}{id}"));
            }
        }
    }
    out.sort();
    out.dedup();
    out
}

impl Domain for RocketLanding {
    fn id(&self) -> &'static str {
        "rocket-landing"
    }
    fn seeded(&self) -> bool {
        true
    }
    fn protected(&self) -> &'static [Protected] {
        ROCKET_PROTECTED
    }
    fn validate(&self, case: &[u8], seed: u64) -> Result<(), String> {
        let c: LandingCase =
            serde_json::from_slice(case).map_err(|e| format!("invalid case: {e}"))?;
        prepare_landing(&c, seed).map(|_| ())
    }
    fn run(&self, case: &[u8], seed: u64) -> Result<RunOutput, RunError> {
        let art = landing_run::artifacts(case, seed).map_err(|e| match e {
            landing_run::LandError::Input(m) => RunError::Input(m),
            landing_run::LandError::Simulation(m) => RunError::Simulation(m),
        })?;
        let mut metrics = BTreeMap::new();
        insert_numbers(&mut metrics, "summary.", &art.summary);
        verification_metrics(&mut metrics, &art.verification);
        let outcome = art.outcome.to_string();
        Ok(RunOutput {
            trace_sha256: sha256_hex(&art.trace),
            verification_sha256: Some(sha256_hex(&art.verification)),
            mission_success: Some(outcome == "landed"),
            outcome,
            requirements_pass: Some(art.requirements_pass),
            invariants_pass: Some(art.invariants_pass),
            metrics,
            violations: verification_violations(&art.verification),
        })
    }
    fn write(&self, case_path: &Path, seed: u64, out: &Path) -> Result<(), String> {
        landing_run::write_landing(case_path, seed, out)
            .map(|_| ())
            .map_err(|e| e.to_string())
    }
    fn cli_args(
        &self,
        case_path: &Path,
        seed: u64,
        out: &Path,
        _staging: &Path,
    ) -> Result<Vec<String>, String> {
        Ok(vec![
            "land".into(),
            case_path.display().to_string(),
            "--seed".into(),
            seed.to_string(),
            "--output".into(),
            out.display().to_string(),
        ])
    }
    fn files(&self) -> &'static [&'static str] {
        &["case.json", "trace.json", "verification.json", "run.json"]
    }
    fn source_sha256(&self) -> String {
        vv_rocket::source_sha256()
    }
    fn has_verdicts(&self) -> bool {
        true
    }
    fn trace_file(&self) -> &'static str {
        "trace.json"
    }
    fn verification_file(&self) -> Option<&'static str> {
        Some("verification.json")
    }
    fn case_copy_file(&self) -> Option<&'static str> {
        Some("case.json")
    }
    fn cli_replay_args(&self, dir: &Path) -> Vec<String> {
        vec!["replay".into(), dir.display().to_string()]
    }
    fn written_source_sha256(&self, dir: &Path) -> Option<String> {
        json_source_sha256(&dir.join("run.json"))
    }
    fn convergence(&self, _case: &[u8], tolerance_m: f64) -> Result<Convergence, String> {
        Ok(converge::not_applicable(
            converge::LANDING_FIXED_STEP,
            tolerance_m,
        ))
    }
}

impl Domain for RocketRigidBody {
    fn id(&self) -> &'static str {
        "rocket-rigid-body"
    }
    fn seeded(&self) -> bool {
        false
    }
    fn protected(&self) -> &'static [Protected] {
        ROCKET_PROTECTED
    }
    fn validate(&self, case: &[u8], _seed: u64) -> Result<(), String> {
        let c: model::Case =
            serde_json::from_slice(case).map_err(|e| format!("invalid case: {e}"))?;
        model::prepare(&c).map(|_| ())
    }
    fn run(&self, case: &[u8], _seed: u64) -> Result<RunOutput, RunError> {
        // `trace_bytes` reports a rejected input and a failed simulation in one message; validate
        // first so the two stay apart.
        self.validate(case, 0).map_err(RunError::Input)?;
        let (_, trace, summary) = rigid_run::trace_bytes(case).map_err(RunError::Simulation)?;
        let mut metrics = BTreeMap::new();
        insert_numbers(&mut metrics, "summary.", &summary);
        Ok(RunOutput {
            trace_sha256: sha256_hex(&trace),
            verification_sha256: None,
            outcome: summary["end_reason"]
                .as_str()
                .unwrap_or("unknown")
                .to_string(),
            mission_success: None,
            requirements_pass: None,
            invariants_pass: None,
            metrics,
            violations: Vec::new(),
        })
    }
    fn write(&self, case_path: &Path, _seed: u64, out: &Path) -> Result<(), String> {
        rigid_run::write_run(case_path, out).map(|_| ())
    }
    fn cli_args(
        &self,
        case_path: &Path,
        _seed: u64,
        out: &Path,
        _staging: &Path,
    ) -> Result<Vec<String>, String> {
        Ok(vec![
            "run".into(),
            case_path.display().to_string(),
            "--output".into(),
            out.display().to_string(),
        ])
    }
    fn files(&self) -> &'static [&'static str] {
        &["case.json", "trace.json", "run.json"]
    }
    fn source_sha256(&self) -> String {
        vv_rocket::source_sha256()
    }
    fn has_verdicts(&self) -> bool {
        false
    }
    fn trace_file(&self) -> &'static str {
        "trace.json"
    }
    fn verification_file(&self) -> Option<&'static str> {
        None
    }
    fn case_copy_file(&self) -> Option<&'static str> {
        Some("case.json")
    }
    fn cli_replay_args(&self, dir: &Path) -> Vec<String> {
        vec!["replay".into(), dir.display().to_string()]
    }
    fn written_source_sha256(&self, dir: &Path) -> Option<String> {
        json_source_sha256(&dir.join("run.json"))
    }
    fn convergence(&self, case: &[u8], tolerance_m: f64) -> Result<Convergence, String> {
        converge::rigid_body(case, 4, tolerance_m)
    }
}
