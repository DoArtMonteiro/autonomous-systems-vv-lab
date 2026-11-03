//! Installs the reference host into a temporary domains directory, exactly as an installer would:
//! a directory with domain.json and the host executable. Nothing in the platform is edited.

#![allow(dead_code)]

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use vv_platform::{REQUEST_SCHEMA, RunRequest};

static N: AtomicU64 = AtomicU64::new(0);

pub fn temp(name: &str) -> PathBuf {
    let n = N.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("vv-ext-{name}-{}-{n}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

pub fn manifest() -> Value {
    serde_json::from_str(include_str!("../domain.json")).unwrap()
}

pub fn install(domains: &Path, dir_name: &str, manifest: &Value) -> PathBuf {
    let dir = domains.join(dir_name);
    fs::create_dir_all(&dir).unwrap();
    let exe = manifest["host"]["executable"].as_str().unwrap();
    fs::copy(env!("CARGO_BIN_EXE_vv-domain-reference"), dir.join(exe)).unwrap();
    fs::write(
        dir.join("domain.json"),
        serde_json::to_vec_pretty(manifest).unwrap(),
    )
    .unwrap();
    dir
}

pub fn request(seed: u64) -> RunRequest {
    RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: "reference-oscillator".into(),
        scenario: "hold-zero".into(),
        controller: "pd".into(),
        seed,
        faults: vec![],
        parameters: Default::default(),
    }
}
