//! Calls to the `vv-lab` simulator. The binary is looked up next to this host executable; the
//! `VV_LAB_BINARY` environment variable is a fallback for tests. PATH is never searched. One call is
//! one process with closed stdin, capped output, a timeout and no console window (see `vv_platform::host`).

use std::ffi::{OsStr, OsString};
use std::path::{Path, PathBuf};

use vv_platform::host::call;

pub const BINARY_ENV: &str = "VV_LAB_BINARY";
const TIMEOUT_S: u32 = 30;
const MAX_STDOUT_BYTES: u64 = 64 * 1024;
/// Same artifact cap as the Python adapter.
const MAX_ARTIFACT_BYTES: u64 = 16 * 1024 * 1024;
/// run-m4 exits 2 when the mission violates a safety invariant: that is a result, not an error.
const OK_EXIT_CODES: [i32; 2] = [0, 2];

fn binary_name() -> &'static str {
    if cfg!(windows) {
        "vv-lab.exe"
    } else {
        "vv-lab"
    }
}

pub fn locate() -> Result<PathBuf, String> {
    let sibling = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|dir| dir.join(binary_name())))
        .filter(|path| path.is_file());
    if let Some(path) = sibling {
        return Ok(path);
    }
    match std::env::var_os(BINARY_ENV) {
        Some(value) if Path::new(&value).is_file() => Ok(PathBuf::from(value)),
        Some(_) => Err(format!("{BINARY_ENV} does not name a file")),
        None => Err(format!(
            "{} was not found next to the domain host and {BINARY_ENV} is not set",
            binary_name()
        )),
    }
}

fn absolute(path: &Path) -> Result<OsString, String> {
    std::path::absolute(path)
        .map(PathBuf::into_os_string)
        .map_err(|e| e.to_string())
}

fn tail(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    chars[chars.len().saturating_sub(400)..].iter().collect()
}

/// Mission policy flags of run-m4; `None` keeps the simulator default.
#[derive(Clone, Copy)]
pub struct Policy {
    pub stall_window_ticks: Option<u32>,
    pub min_progress_mm: Option<u32>,
}

pub struct RunArgs<'a> {
    pub inputs: &'a Path,
    pub output: &'a Path,
    pub seed: u64,
    pub controller: &'a str,
    pub policy: Policy,
}

/// Arguments of `vv-lab run-m4` as the Python adapter passes them, plus the policy flags when they
/// differ from the defaults. Paths are given by the caller, so the same list also serves the
/// reproduction commands recorded in the run.
pub fn run_args(
    a: &RunArgs,
    scenario: &OsStr,
    contracts: &OsStr,
    actuator: &OsStr,
    output: &OsStr,
) -> Vec<OsString> {
    let mut args: Vec<OsString> = vec![
        "run-m4".into(),
        scenario.into(),
        "--seed".into(),
        a.seed.to_string().into(),
        "--controller".into(),
        a.controller.into(),
        "--contracts".into(),
        contracts.into(),
        "--actuator".into(),
        actuator.into(),
        "--output".into(),
        output.into(),
        "--max-output-bytes".into(),
        MAX_ARTIFACT_BYTES.to_string().into(),
    ];
    if let Some(n) = a.policy.stall_window_ticks {
        args.extend(["--stall-window-ticks".into(), n.to_string().into()]);
    }
    if let Some(n) = a.policy.min_progress_mm {
        args.extend(["--min-progress-mm".into(), n.to_string().into()]);
    }
    args
}

pub fn run_m4(a: &RunArgs) -> Result<(), String> {
    let exe = locate()?;
    let path = |name: &str| absolute(&a.inputs.join(name));
    let args = run_args(
        a,
        &path("scenario.json")?,
        &path("contracts.json")?,
        &path("actuator.json")?,
        &absolute(a.output)?,
    );
    let done = call(&exe, &args, TIMEOUT_S, MAX_STDOUT_BYTES).map_err(|e| e.to_string())?;
    if !OK_EXIT_CODES.contains(&done.code) {
        return Err(format!(
            "vv-lab run-m4 failed (exit {}): {}",
            done.code,
            tail(&done.stderr)
        ));
    }
    Ok(())
}

/// `vv-lab replay-m4`: the simulator recomputes the stored run and compares every artifact.
pub fn replay_m4(manifest: &Path) -> Result<String, String> {
    let exe = locate()?;
    let args = vec![OsString::from("replay-m4"), absolute(manifest)?];
    let done = call(&exe, &args, TIMEOUT_S, MAX_STDOUT_BYTES).map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&done.stdout).trim().to_owned();
    if done.code == 0 {
        Ok(stdout)
    } else {
        Err(format!("exit {}: {}", done.code, tail(&done.stderr)))
    }
}
