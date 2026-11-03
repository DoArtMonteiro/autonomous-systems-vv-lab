//! Rocket powered-landing domain host (`vv-domain` v1). It wraps the `vv-rocket` simulator library of
//! this repository: the request becomes the landing case of `scripts/landing_adapter.py` (byte for
//! byte at default parameters and at most one fault), the native artifacts are those of `vv-rocket land`, and the run
//! record is derived from them. Replay recomputes the run; it never returns a stored verdict.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use vv_platform::contract::*;
use vv_platform::host_sdk::{DomainHost, HostError};
use vv_platform::seeds::check_seed;
use vv_rocket::landing_model::{LandingCase, prepare_landing};
use vv_rocket::landing_run::{LandError, replay, write_landing};

pub mod case;
pub mod catalog;
pub mod demos;
pub mod record;

const MANIFEST_JSON: &str = include_str!("../domain.json");

/// The manifest, parsed from the file the host ships next to its executable.
pub fn manifest() -> DomainManifest {
    serde_json::from_str(MANIFEST_JSON).expect("domain.json is a valid manifest")
}

pub struct Host;

static SCRATCH: AtomicU64 = AtomicU64::new(0);

fn scratch_dir() -> PathBuf {
    let n = SCRATCH.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!("vv-rocket-case-{}-{n}", std::process::id()))
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
        let bytes = case::case_bytes(&request)?;
        let landing: LandingCase =
            serde_json::from_slice(&bytes).map_err(|e| format!("invalid case: {e}"))?;
        // The simulator's own range checks (gains, windows, magnitudes) surface as an invalid request.
        prepare_landing(&landing, request.seed)?;
        Ok(request)
    }

    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError> {
        check_seed(&manifest().seeds, request.seed).map_err(HostError::Invalid)?;
        let bytes = case::case_bytes(request).map_err(HostError::Invalid)?;
        let scratch = scratch_dir();
        fs::create_dir_all(&scratch).map_err(|e| HostError::Simulation(e.to_string()))?;
        let case_path = scratch.join("case.json");
        let written = fs::write(&case_path, &bytes)
            .map_err(|e| HostError::Simulation(e.to_string()))
            .and_then(|_| {
                // The same library call as `vv-rocket land`, so case.json, trace.json,
                // verification.json and run.json are byte-identical to the command line's.
                write_landing(&case_path, request.seed, out).map_err(|e| match e {
                    LandError::Input(m) => HostError::Invalid(m),
                    LandError::Simulation(m) => HostError::Simulation(m),
                })
            });
        let _ = fs::remove_dir_all(&scratch);
        written?;
        record::build(request, out).map_err(HostError::Simulation)
    }

    fn native_seed_file(&self) -> Option<&'static str> {
        Some("run.json")
    }

    fn native_replay(&self, dir: &Path) -> Vec<ReplayCheck> {
        replay(dir)
            .checks
            .into_iter()
            .map(|c| ReplayCheck {
                name: format!("vv-rocket replay: {}", c.name),
                pass: c.pass,
                detail: c.detail,
            })
            .collect()
    }
}
