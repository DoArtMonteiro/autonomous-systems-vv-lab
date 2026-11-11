//! Two-stage launch ascent domain host (`vv-domain` v1, records `vv-run.v2`). It wraps the
//! `vv-ascent` simulator library of this repository: the request becomes a case (the vehicle
//! template of the scenario with the request parameters), the native artifacts are those of
//! `vv-ascent run`, and the multi-entity record is derived from them. Replay recomputes the run; it
//! never returns a stored verdict.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use vv_platform::contract::*;
use vv_platform::host_sdk::{DomainHost, HostError};
use vv_platform::seeds::check_seed;

pub mod case;
pub mod catalog;
pub mod demos;
pub mod record;

const MANIFEST_JSON: &str = include_str!("../domain.json");

pub fn manifest() -> DomainManifest {
    serde_json::from_str(MANIFEST_JSON).expect("domain.json is a valid manifest")
}

pub struct Host;

static SCRATCH: AtomicU64 = AtomicU64::new(0);

fn scratch_dir() -> PathBuf {
    let n = SCRATCH.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!("vv-ascent-case-{}-{n}", std::process::id()))
}

impl DomainHost for Host {
    fn manifest(&self) -> DomainManifest {
        manifest()
    }

    fn catalog(&self) -> DomainCatalog {
        catalog::catalog()
    }

    fn check(&self, request: RunRequest) -> Result<RunRequest, String> {
        // The platform and the SDK refuse a protected seed already; this is the host's own barrier.
        check_seed(&manifest().seeds, request.seed)?;
        case::case_for(&request)?;
        Ok(request)
    }

    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError> {
        check_seed(&manifest().seeds, request.seed).map_err(HostError::Invalid)?;
        let case = case::case_for(request).map_err(HostError::Invalid)?;
        let bytes = serde_json::to_vec(&case).map_err(|e| HostError::Simulation(e.to_string()))?;
        let scratch = scratch_dir();
        fs::create_dir_all(&scratch).map_err(|e| HostError::Simulation(e.to_string()))?;
        let case_path = scratch.join("case.json");
        let written = fs::write(&case_path, &bytes)
            .map_err(|e| HostError::Simulation(e.to_string()))
            .and_then(|_| {
                // The same library call as `vv-ascent run`, so the native files are those of the CLI.
                vv_ascent::run::write_run(&case_path, request.seed, out)
                    .map_err(HostError::Simulation)
            });
        let _ = fs::remove_dir_all(&scratch);
        let outputs = written?;
        Ok(record::build(request, &case, &outputs))
    }

    fn native_seed_file(&self) -> Option<&'static str> {
        Some("run.json")
    }

    fn native_replay(&self, dir: &Path) -> Vec<ReplayCheck> {
        vv_ascent::run::replay(dir)
            .checks
            .into_iter()
            .map(|c| ReplayCheck {
                name: format!("vv-ascent replay: {}", c.name),
                pass: c.pass,
                detail: c.detail,
            })
            .collect()
    }
}
