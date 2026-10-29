//! Stored runs: execution into a directory and replay that recomputes and compares every byte.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::model::{Case, prepare};
use crate::sim::simulate;
use crate::{sha256_hex, source_sha256};

pub const RUN_SCHEMA: &str = "vv-rocket-run.v1";
pub const REPLAY_SCHEMA: &str = "vv-rocket-replay.v1";
pub const MAX_CASE_BYTES: u64 = 256 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FileRef {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: String,
    pub source_sha256: String,
    pub name: String,
    pub case: FileRef,
    pub trace: FileRef,
    pub summary: serde_json::Value,
}

/// Validated case bytes to canonical trace bytes.
pub fn trace_bytes(case_bytes: &[u8]) -> Result<(Case, Vec<u8>, serde_json::Value), String> {
    let case: Case =
        serde_json::from_slice(case_bytes).map_err(|e| format!("invalid case: {e}"))?;
    let prepared = prepare(&case)?;
    let run = simulate(&prepared, false)?;
    let mut bytes = serde_json::to_vec(&run.trace).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    let summary = serde_json::to_value(&run.trace.summary).map_err(|e| e.to_string())?;
    Ok((case, bytes, summary))
}

/// Largest stored artifact (`run.json`, `trace.json`, `verification.json`) that replay reads. A
/// trace holds at most `MAX_SAMPLES` samples; the largest ones of the M9 and M9.1 campaigns are
/// about 0,6 MB, so 8 MiB leaves more than a tenfold margin and still bounds memory use.
pub const MAX_ARTIFACT_BYTES: u64 = 8 * 1024 * 1024;

pub(crate) fn read_bounded(path: &Path) -> Result<Vec<u8>, String> {
    read_capped(path, MAX_CASE_BYTES)
}

pub(crate) fn read_capped(path: &Path, cap: u64) -> Result<Vec<u8>, String> {
    let meta = fs::metadata(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if meta.len() > cap {
        return Err(format!("{} exceeds {cap} bytes", path.display()));
    }
    fs::read(path).map_err(|e| format!("{}: {e}", path.display()))
}

/// The manifest this build writes for a case and its trace; replay regenerates it byte for byte.
fn manifest_for(
    case: &Case,
    case_bytes: &[u8],
    trace: &[u8],
    summary: serde_json::Value,
) -> Result<(Manifest, Vec<u8>), String> {
    let manifest = Manifest {
        schema: RUN_SCHEMA.into(),
        source_sha256: source_sha256(),
        name: case.name.clone(),
        case: FileRef {
            path: "case.json".into(),
            sha256: sha256_hex(case_bytes),
        },
        trace: FileRef {
            path: "trace.json".into(),
            sha256: sha256_hex(trace),
        },
        summary,
    };
    let mut bytes = serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    Ok((manifest, bytes))
}

/// Runs a case and writes `case.json`, `trace.json` and `run.json` into `out`, never overwriting.
pub fn write_run(case_path: &Path, out: &Path) -> Result<Manifest, String> {
    let case_bytes = read_bounded(case_path)?;
    let (case, trace, summary) = trace_bytes(&case_bytes)?;
    fs::create_dir_all(out).map_err(|e| format!("{}: {e}", out.display()))?;
    for name in ["case.json", "trace.json", "run.json"] {
        if out.join(name).exists() {
            return Err(format!("{name} already exists in the output directory"));
        }
    }
    let (manifest, manifest_bytes) = manifest_for(&case, &case_bytes, &trace, summary)?;
    let write = |name: &str, bytes: &[u8]| {
        fs::write(out.join(name), bytes).map_err(|e| format!("{name}: {e}"))
    };
    write("case.json", &case_bytes)?;
    write("trace.json", &trace)?;
    write("run.json", &manifest_bytes)?;
    Ok(manifest)
}

#[derive(Clone, Debug, Serialize)]
pub struct Check {
    pub name: &'static str,
    pub pass: bool,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReplayReport {
    pub schema: &'static str,
    pub status: &'static str,
    pub source_sha256: String,
    pub checks: Vec<Check>,
}

pub(crate) fn check(name: &'static str, pass: bool, detail: impl Into<String>) -> Check {
    Check {
        name,
        pass,
        detail: detail.into(),
    }
}

pub(crate) fn report_of(checks: Vec<Check>) -> ReplayReport {
    let pass = !checks.is_empty() && checks.iter().all(|c: &Check| c.pass);
    ReplayReport {
        schema: REPLAY_SCHEMA,
        status: if pass { "verified" } else { "failed" },
        source_sha256: source_sha256(),
        checks,
    }
}

/// Recomputes the stored run from its case with this build and compares the trace byte for byte.
/// Stored conclusions are never returned without recomputation.
pub fn replay(dir: &Path) -> ReplayReport {
    // Landing runs (M9) carry their own manifest schema and are replayed by their own module.
    if let Ok(bytes) = read_capped(&dir.join("run.json"), MAX_ARTIFACT_BYTES)
        && let Ok(value) = serde_json::from_slice::<serde_json::Value>(&bytes)
        && value["schema"] == crate::landing_run::RUN_SCHEMA
    {
        return crate::landing_run::replay(dir);
    }
    let mut checks = Vec::new();
    let report = report_of;
    let manifest: Manifest = match read_capped(&dir.join("run.json"), MAX_ARTIFACT_BYTES)
        .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()))
    {
        Ok(m) => m,
        Err(e) => {
            checks.push(check("run.json is a valid manifest", false, e));
            return report(checks);
        }
    };
    checks.push(check(
        "manifest schema",
        manifest.schema == RUN_SCHEMA,
        manifest.schema.clone(),
    ));
    let names_ok = manifest.case.path == "case.json" && manifest.trace.path == "trace.json";
    checks.push(check(
        "manifest file names",
        names_ok,
        format!("{} {}", manifest.case.path, manifest.trace.path),
    ));
    if !names_ok {
        return report(checks);
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
    let (case_bytes, stored_trace) = match (
        read_bounded(&dir.join("case.json")),
        fs::read(dir.join("trace.json")),
    ) {
        (Ok(c), Ok(t)) => (c, t),
        (c, t) => {
            let detail = format!("{:?} {:?}", c.err(), t.err().map(|e| e.to_string()));
            checks.push(check("case.json and trace.json readable", false, detail));
            return report(checks);
        }
    };
    let case_sha = sha256_hex(&case_bytes);
    checks.push(check(
        "case.json hash",
        case_sha == manifest.case.sha256,
        case_sha,
    ));
    let trace_sha = sha256_hex(&stored_trace);
    checks.push(check(
        "trace.json hash",
        trace_sha == manifest.trace.sha256,
        trace_sha,
    ));
    match trace_bytes(&case_bytes) {
        Ok((case, fresh, summary)) => {
            // The manifest's own claims (name, summary) are regenerated, never taken from the stored file.
            let stored_manifest = fs::read(dir.join("run.json")).unwrap_or_default();
            let regenerated = manifest_for(&case, &case_bytes, &fresh, summary).map(|m| m.1);
            let same = fresh == stored_trace;
            checks.push(check(
                "recomputed trace equals the stored trace byte for byte",
                same,
                format!("recomputed {}", sha256_hex(&fresh)),
            ));
            checks.push(check(
                "run.json equals the regenerated manifest byte for byte",
                regenerated.as_ref() == Ok(&stored_manifest),
                format!("recomputed name {}", case.name),
            ));
        }
        Err(e) => checks.push(check("case replays", false, e)),
    }
    report(checks)
}
