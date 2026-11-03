//! `vv-exec plan <spec.json>` | `vv-exec run <spec.json> --output <dir> [--threads <n>]` |
//! `vv-exec equiv <dir> --cli <vv-rocket> [--sample <n>]` | `vv-exec report <dir>` |
//! `vv-exec verify <dir> [--threads <n>]` |
//! `vv-exec converge <case.json> [--levels <n>] [--tolerance-m <m>]` |
//! `vv-exec search <search.json> --output <dir> [--threads <n>]` | `vv-exec search-verify <dir>` |
//! `vv-exec claim <claim.json>` | `vv-exec investigate <claim.json> --output <dir> [--threads <n>]
//! [--progress]` | `vv-exec investigate-verify <dir> [--threads <n>] [--progress]`
//!
//! Exit status: 0 done; 1 a gate or check failed; 3 usage or rejected input; 5 run interrupted
//! (resume with the same command). The first Ctrl+C stops `run` after the runs in flight, which
//! are logged; a second one ends the process at once.

use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};

use vv_exec::plan::{Plan, read_capped};
use vv_exec::sched::SystemProbe;
use vv_exec::spec::MAX_SPEC_BYTES;
use vv_exec::{converge, engine, equiv, investigate, report};

const USAGE: &str = "usage: vv-exec plan <spec.json> | run <spec.json> --output <dir> [--threads <n>] | equiv <dir> --cli <vv-rocket> [--sample <n>] | report <dir> | verify <dir> [--threads <n>] | converge <case.json> [--levels <n>] [--tolerance-m <m>] | search <search.json> --output <dir> [--threads <n>] | search-check <search.json> | search-verify <dir> [--threads <n>] | claim <claim.json> | investigate <claim.json> --output <dir> [--threads <n>] [--progress] | investigate-verify <dir> [--threads <n>] [--progress]";

/// Set by the console interrupt handler; read by the workers of `run`.
static CANCEL: AtomicBool = AtomicBool::new(false);

/// Installs a Ctrl+C handler that sets `CANCEL`. The second interrupt is left to the default
/// handler, which ends the process.
#[cfg(windows)]
fn install_interrupt_handler() {
    unsafe extern "system" {
        fn SetConsoleCtrlHandler(
            handler: Option<unsafe extern "system" fn(u32) -> i32>,
            add: i32,
        ) -> i32;
    }
    unsafe extern "system" fn on_ctrl(kind: u32) -> i32 {
        // CTRL_C_EVENT = 0, CTRL_BREAK_EVENT = 1.
        if kind <= 1 && !CANCEL.swap(true, Ordering::SeqCst) {
            return 1;
        }
        0
    }
    // SAFETY: registers a handler that only touches an atomic; the function lives forever.
    unsafe {
        SetConsoleCtrlHandler(Some(on_ctrl), 1);
    }
}

#[cfg(unix)]
fn install_interrupt_handler() {
    const SIGINT: i32 = 2;
    const SIG_DFL: usize = 0;
    unsafe extern "C" {
        fn signal(sig: i32, handler: usize) -> usize;
    }
    extern "C" fn on_sigint(_: i32) {
        CANCEL.store(true, Ordering::SeqCst);
        // SAFETY: signal() is async-signal-safe; the next SIGINT gets the default action.
        unsafe {
            signal(SIGINT, SIG_DFL);
        }
    }
    // SAFETY: the handler only stores to an atomic and resets the disposition.
    unsafe {
        signal(SIGINT, on_sigint as extern "C" fn(i32) as usize);
    }
}

#[cfg(not(any(windows, unix)))]
fn install_interrupt_handler() {}

fn json<T: serde::Serialize>(v: &T) -> String {
    serde_json::to_string_pretty(v).expect("serialisable")
}

fn plan_from_spec(spec: &Path) -> Result<Plan, String> {
    let bytes = read_capped(spec, MAX_SPEC_BYTES)?;
    let dir = spec.parent().unwrap_or(Path::new("."));
    Plan::build(&bytes, dir)
}

/// The plan of an output directory, rebuilt from its own inputs and checked against `plan.json`.
fn plan_from_output(out: &Path) -> Result<Plan, String> {
    let spec = read_capped(&out.join("spec.json"), MAX_SPEC_BYTES)?;
    let base = read_capped(&out.join("base-case.json"), 256 * 1024)?;
    let e = vv_exec::spec::Experiment::parse(&spec)?;
    let plan = Plan::from_parts(e, &spec, base)?;
    let stored: serde_json::Value =
        serde_json::from_slice(&read_capped(&out.join("plan.json"), MAX_SPEC_BYTES)?)
            .map_err(|e| format!("plan.json: {e}"))?;
    if stored["plan_sha256"] != plan.plan_sha256.as_str() {
        return Err("plan.json does not match the plan rebuilt from spec.json and base-case.json (another source hash or engine?)".into());
    }
    Ok(plan)
}

fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].as_str())
}

type Outcome = Result<(String, u8), (String, u8)>;

fn usage() -> (String, u8) {
    (USAGE.to_string(), 3)
}

fn input(e: String) -> (String, u8) {
    (e, 3)
}

fn threads_of(args: &[String]) -> Result<usize, (String, u8)> {
    match flag(args, "--threads") {
        Some(t) => t.parse::<usize>().map_err(|_| usage()),
        None => Ok(std::thread::available_parallelism().map_or(1, |n| n.get())),
    }
}

fn dispatch(args: &[String]) -> Outcome {
    match args.first().map(String::as_str) {
        Some("plan") => {
            let spec = args.get(1).ok_or_else(usage)?;
            let plan = plan_from_spec(Path::new(spec)).map_err(input)?;
            Ok((json(&plan.manifest()), 0))
        }
        Some("run") => {
            let spec = args.get(1).ok_or_else(usage)?;
            let out = PathBuf::from(flag(args, "--output").ok_or_else(usage)?);
            engine::guard_output(&out).map_err(input)?;
            let threads = match flag(args, "--threads") {
                Some(t) => Some(t.parse::<usize>().map_err(|_| usage())?),
                None => None,
            };
            let plan = plan_from_spec(Path::new(spec)).map_err(input)?;
            install_interrupt_handler();
            let opt = engine::Options {
                probe: &SystemProbe,
                max_threads: threads,
                cancel: &CANCEL,
                stop_after: None,
                probe_every: 256,
            };
            let summary = engine::execute(&plan, &out, &opt).map_err(input)?;
            if !summary.complete {
                return Ok((json(&summary), 5));
            }
            let records = engine::read_records(&plan, &out).map_err(input)?;
            let retained = engine::retain(&plan, &out, &records).map_err(input)?;
            Ok((
                json(&serde_json::json!({
                    "run": summary,
                    "retained": retained.retained.len(),
                    "retention_truncated_by": retained.truncated_by,
                })),
                0,
            ))
        }
        Some("equiv") => {
            let out = PathBuf::from(args.get(1).ok_or_else(usage)?);
            let cli = PathBuf::from(flag(args, "--cli").ok_or_else(usage)?);
            let k = match flag(args, "--sample") {
                Some(s) => s.parse::<usize>().map_err(|_| usage())?,
                None => 8,
            };
            engine::guard_output(&out).map_err(input)?;
            let plan = plan_from_output(&out).map_err(input)?;
            let records = engine::read_records(&plan, &out).map_err(input)?;
            let r = equiv::run(&plan, &out, &records, &cli, k).map_err(input)?;
            Ok((json(&r), if r.pass { 0 } else { 1 }))
        }
        Some("report") => {
            let out = PathBuf::from(args.get(1).ok_or_else(usage)?);
            engine::guard_output(&out).map_err(input)?;
            let plan = plan_from_output(&out).map_err(input)?;
            let records = engine::read_records(&plan, &out).map_err(input)?;
            let r = report::build(&plan, &records, &out).map_err(input)?;
            let text = json(&r);
            engine::write_new(&out.join("report.json"), format!("{text}\n").as_bytes())
                .map_err(input)?;
            Ok((
                text,
                if r.equivalence_status == "verified" {
                    0
                } else {
                    1
                },
            ))
        }
        Some("verify") => {
            let out = PathBuf::from(args.get(1).ok_or_else(usage)?);
            let threads = match flag(args, "--threads") {
                Some(t) => t.parse::<usize>().map_err(|_| usage())?,
                None => std::thread::available_parallelism().map_or(1, |n| n.get()),
            };
            let plan = plan_from_output(&out).map_err(input)?;
            let records = engine::read_records(&plan, &out).map_err(input)?;
            let v = engine::verify_all(&plan, &records, threads);
            Ok((json(&v), if v.pass { 0 } else { 1 }))
        }
        Some("search") => {
            let spec = args.get(1).ok_or_else(usage)?;
            let out = PathBuf::from(flag(args, "--output").ok_or_else(usage)?);
            let threads = match flag(args, "--threads") {
                Some(t) => t.parse::<usize>().map_err(|_| usage())?,
                None => std::thread::available_parallelism().map_or(1, |n| n.get()),
            };
            let (spec_bytes, base_bytes) =
                vv_exec::search::read_inputs(Path::new(spec)).map_err(input)?;
            let r =
                vv_exec::search::execute(&spec_bytes, &base_bytes, &out, threads).map_err(input)?;
            let found = r
                .repetitions
                .iter()
                .filter(|x| x.first_violation.is_some())
                .count();
            Ok((
                json(&serde_json::json!({
                    "id": r.id,
                    "repetitions": r.repetitions.len(),
                    "repetitions_with_a_violation": found,
                    "evaluations": r.total_evaluations,
                    "log_sha256": r.log_sha256,
                    "wall_s": r.wall_s,
                })),
                0,
            ))
        }
        Some("search-check") => {
            let spec = args.get(1).ok_or_else(usage)?;
            let (spec_bytes, base_bytes) =
                vv_exec::search::read_inputs(Path::new(spec)).map_err(input)?;
            let (s, _) = vv_exec::search::load(&spec_bytes, &base_bytes).map_err(input)?;
            Ok((
                json(
                    &serde_json::json!({"id": s.id, "valid": true, "parameters": s.parameters.len()}),
                ),
                0,
            ))
        }
        Some("search-verify") => {
            let out = PathBuf::from(args.get(1).ok_or_else(usage)?);
            let threads = match flag(args, "--threads") {
                Some(t) => t.parse::<usize>().map_err(|_| usage())?,
                None => std::thread::available_parallelism().map_or(1, |n| n.get()),
            };
            let v = vv_exec::search::verify(&out, threads).map_err(input)?;
            Ok((json(&v), if v.pass { 0 } else { 1 }))
        }
        Some("claim") => {
            let claim = args.get(1).ok_or_else(usage)?;
            let inputs = investigate::read_inputs(Path::new(claim)).map_err(input)?;
            let d = investigate::describe(&inputs).map_err(input)?;
            Ok((json(&d), 0))
        }
        Some("investigate") => {
            let claim = args.get(1).ok_or_else(usage)?;
            let out = PathBuf::from(flag(args, "--output").ok_or_else(usage)?);
            let threads = threads_of(args)?;
            let inputs = investigate::read_inputs(Path::new(claim)).map_err(input)?;
            let progress = |stage: &str, done: u64, total: u64| {
                eprintln!(
                    "{}",
                    serde_json::json!({"progress": stage, "done": done, "total": total})
                );
            };
            let p: investigate::Progress = if args.iter().any(|a| a == "--progress") {
                Some(&progress)
            } else {
                None
            };
            let r = investigate::execute(&inputs, &out, threads, p).map_err(input)?;
            Ok((
                json(&serde_json::json!({
                    "claim": r.claim_id,
                    "verdict": r.findings.verdict,
                    "probes": r.probes,
                    "package": out.display().to_string(),
                })),
                0,
            ))
        }
        Some("investigate-verify") => {
            let out = PathBuf::from(args.get(1).ok_or_else(usage)?);
            let threads = threads_of(args)?;
            let progress = |stage: &str, done: u64, total: u64| {
                eprintln!(
                    "{}",
                    serde_json::json!({"progress": stage, "done": done, "total": total})
                );
            };
            let p: investigate::Progress = if args.iter().any(|a| a == "--progress") {
                Some(&progress)
            } else {
                None
            };
            let v = investigate::verify(&out, threads, p).map_err(input)?;
            Ok((json(&v), if v.pass { 0 } else { 1 }))
        }
        Some("converge") => {
            let case = args.get(1).ok_or_else(usage)?;
            let levels = match flag(args, "--levels") {
                Some(s) => s.parse::<u32>().map_err(|_| usage())?,
                None => 4,
            };
            let tol = match flag(args, "--tolerance-m") {
                Some(s) => s.parse::<f64>().map_err(|_| usage())?,
                None => 1e-3,
            };
            let bytes = read_capped(Path::new(case), 256 * 1024).map_err(input)?;
            let c = converge::rigid_body(&bytes, levels, tol).map_err(input)?;
            Ok((json(&c), if c.pass { 0 } else { 1 }))
        }
        _ => Err(usage()),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match dispatch(&args) {
        Ok((text, code)) => {
            println!("{text}");
            ExitCode::from(code)
        }
        Err((msg, code)) => {
            eprintln!("vv-exec: {msg}");
            ExitCode::from(code)
        }
    }
}
