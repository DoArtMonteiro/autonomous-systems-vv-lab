//! Stored landing runs: execution into a directory and replay that recomputes the trace, the
//! verification and the manifest from the case and the seed and compares every byte.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::landing_model::{LandingCase, prepare_landing};
use crate::landing_sim::simulate_landing;
use crate::landing_verify::verify;
use crate::run::{Check, FileRef, ReplayReport, check, read_bounded, report_of};
use crate::{sha256_hex, source_sha256};

pub const RUN_SCHEMA: &str = "vv-rocket-landing-run.v1";

/// Why a landing could not be produced. The command line tells them apart: a rejected input is a
/// usage error (exit status 3), a failed simulation (a non-finite or non-physical state) is not
/// (exit status 4).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LandError {
    Input(String),
    Simulation(String),
}

impl LandError {
    /// Exit status of `vv-rocket land` for this error.
    pub fn exit_code(&self) -> u8 {
        match self {
            LandError::Input(_) => 3,
            LandError::Simulation(_) => 4,
        }
    }
}

impl std::fmt::Display for LandError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LandError::Input(m) | LandError::Simulation(m) => f.write_str(m),
        }
    }
}

impl From<LandError> for String {
    fn from(e: LandError) -> String {
        e.to_string()
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LandingManifest {
    pub schema: String,
    pub source_sha256: String,
    pub name: String,
    pub seed: u64,
    pub policy: String,
    pub case: FileRef,
    pub trace: FileRef,
    pub verification: FileRef,
    pub summary: serde_json::Value,
    /// `landed`, `hard_landing` or `no_contact`.
    pub outcome: String,
    pub requirements_pass: bool,
    pub invariants_pass: bool,
}

impl LandingManifest {
    /// Exit status 0 of `vv-rocket land`: landed with every invariant met.
    pub fn all_pass(&self) -> bool {
        self.outcome == "landed" && self.requirements_pass && self.invariants_pass
    }
}

pub struct LandingArtifacts {
    pub case: LandingCase,
    pub trace: Vec<u8>,
    pub verification: Vec<u8>,
    pub summary: serde_json::Value,
    pub outcome: &'static str,
    pub policy: &'static str,
    pub requirements_pass: bool,
    pub invariants_pass: bool,
}

fn json_line<T: Serialize>(value: &T) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}

/// Case bytes and seed to the canonical trace and verification bytes.
pub fn artifacts(case_bytes: &[u8], seed: u64) -> Result<LandingArtifacts, LandError> {
    let case: LandingCase = serde_json::from_slice(case_bytes)
        .map_err(|e| LandError::Input(format!("invalid case: {e}")))?;
    let prepared = prepare_landing(&case, seed).map_err(LandError::Input)?;
    let run = simulate_landing(&prepared).map_err(LandError::Simulation)?;
    let verification = verify(&prepared, &run.log);
    Ok(LandingArtifacts {
        trace: json_line(&run.trace).map_err(LandError::Simulation)?,
        verification: json_line(&verification).map_err(LandError::Simulation)?,
        summary: serde_json::to_value(&run.trace.summary)
            .map_err(|e| LandError::Simulation(e.to_string()))?,
        outcome: verification.outcome,
        policy: verification.policy,
        requirements_pass: verification.requirements_pass,
        invariants_pass: verification.invariants_pass,
        case,
    })
}

fn manifest_for(
    art: &LandingArtifacts,
    case_bytes: &[u8],
    seed: u64,
) -> Result<(LandingManifest, Vec<u8>), String> {
    let manifest = LandingManifest {
        schema: RUN_SCHEMA.into(),
        source_sha256: source_sha256(),
        name: art.case.name.clone(),
        seed,
        policy: art.policy.into(),
        case: FileRef {
            path: "case.json".into(),
            sha256: sha256_hex(case_bytes),
        },
        trace: FileRef {
            path: "trace.json".into(),
            sha256: sha256_hex(&art.trace),
        },
        verification: FileRef {
            path: "verification.json".into(),
            sha256: sha256_hex(&art.verification),
        },
        summary: art.summary.clone(),
        outcome: art.outcome.into(),
        requirements_pass: art.requirements_pass,
        invariants_pass: art.invariants_pass,
    };
    let mut bytes = serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    Ok((manifest, bytes))
}

const FILES: [&str; 4] = ["case.json", "trace.json", "verification.json", "run.json"];

/// Runs a landing and writes the four artifacts into `out`, never overwriting.
pub fn write_landing(
    case_path: &Path,
    seed: u64,
    out: &Path,
) -> Result<LandingManifest, LandError> {
    let case_bytes = read_bounded(case_path).map_err(LandError::Input)?;
    let art = artifacts(&case_bytes, seed)?;
    fs::create_dir_all(out).map_err(|e| LandError::Input(format!("{}: {e}", out.display())))?;
    for name in FILES {
        if out.join(name).exists() {
            return Err(LandError::Input(format!(
                "{name} already exists in the output directory"
            )));
        }
    }
    let (manifest, manifest_bytes) =
        manifest_for(&art, &case_bytes, seed).map_err(LandError::Input)?;
    let write = |name: &str, bytes: &[u8]| {
        fs::write(out.join(name), bytes).map_err(|e| LandError::Input(format!("{name}: {e}")))
    };
    write("case.json", &case_bytes)?;
    write("trace.json", &art.trace)?;
    write("verification.json", &art.verification)?;
    write("run.json", &manifest_bytes)?;
    Ok(manifest)
}

/// Recomputes the stored landing from its case and seed with this build and compares the trace,
/// the verification and the manifest byte for byte. Stored verdicts are never returned unchecked.
pub fn replay(dir: &Path) -> ReplayReport {
    let mut checks: Vec<Check> = Vec::new();
    let stored_manifest = fs::read(dir.join("run.json")).unwrap_or_default();
    let manifest: LandingManifest = match serde_json::from_slice(&stored_manifest) {
        Ok(m) => m,
        Err(e) => {
            checks.push(check(
                "run.json is a valid landing manifest",
                false,
                e.to_string(),
            ));
            return report_of(checks);
        }
    };
    checks.push(check(
        "manifest schema",
        manifest.schema == RUN_SCHEMA,
        manifest.schema.clone(),
    ));
    let names_ok = manifest.case.path == "case.json"
        && manifest.trace.path == "trace.json"
        && manifest.verification.path == "verification.json";
    checks.push(check(
        "manifest file names",
        names_ok,
        format!(
            "{} {} {}",
            manifest.case.path, manifest.trace.path, manifest.verification.path
        ),
    ));
    if !names_ok {
        return report_of(checks);
    }
    checks.push(check(
        "built from the same sources",
        manifest.source_sha256 == source_sha256(),
        format!(
            "stored {} this build {}",
            manifest.source_sha256,
            source_sha256()
        ),
    ));
    let (case_bytes, stored_trace, stored_verification) = match (
        read_bounded(&dir.join("case.json")),
        fs::read(dir.join("trace.json")),
        fs::read(dir.join("verification.json")),
    ) {
        (Ok(c), Ok(t), Ok(v)) => (c, t, v),
        (c, t, v) => {
            let detail = format!(
                "{:?} {:?} {:?}",
                c.err(),
                t.err().map(|e| e.to_string()),
                v.err().map(|e| e.to_string())
            );
            checks.push(check(
                "case.json, trace.json and verification.json readable",
                false,
                detail,
            ));
            return report_of(checks);
        }
    };
    for (name, bytes, want) in [
        ("case.json hash", &case_bytes, &manifest.case.sha256),
        ("trace.json hash", &stored_trace, &manifest.trace.sha256),
        (
            "verification.json hash",
            &stored_verification,
            &manifest.verification.sha256,
        ),
    ] {
        let got = sha256_hex(bytes);
        checks.push(check(name, &got == want, got));
    }
    match artifacts(&case_bytes, manifest.seed) {
        Ok(fresh) => {
            let regenerated = manifest_for(&fresh, &case_bytes, manifest.seed).map(|m| m.1);
            checks.push(check(
                "recomputed trace equals the stored trace byte for byte",
                fresh.trace == stored_trace,
                format!("recomputed {}", sha256_hex(&fresh.trace)),
            ));
            checks.push(check(
                "recomputed verification equals the stored verification byte for byte",
                fresh.verification == stored_verification,
                format!("recomputed {}", sha256_hex(&fresh.verification)),
            ));
            checks.push(check(
                "run.json equals the regenerated manifest byte for byte",
                regenerated.as_ref() == Ok(&stored_manifest),
                format!(
                    "recomputed outcome {} seed {} policy {}",
                    fresh.outcome, manifest.seed, fresh.policy
                ),
            ));
        }
        Err(e) => checks.push(check("case replays", false, e.to_string())),
    }
    report_of(checks)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn input_and_simulation_errors_have_distinct_exit_codes() {
        assert_eq!(LandError::Input("x".into()).exit_code(), 3);
        assert_eq!(LandError::Simulation("x".into()).exit_code(), 4);
        // A rejected case is an input error, whatever the field.
        let bad = br#"{"schema": "other"}"#;
        assert!(matches!(artifacts(bad, 0), Err(LandError::Input(_))));
        assert_eq!(
            String::from(LandError::Simulation("boom".into())),
            "boom".to_string()
        );
    }
}
