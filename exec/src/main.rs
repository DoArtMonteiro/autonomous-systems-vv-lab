//! `vv-exec plan <spec.json>` | `vv-exec run <spec.json> --output <dir> [--threads <n>]` |
//! `vv-exec equiv <dir> --cli <vv-rocket> [--sample <n>]` | `vv-exec report <dir>` |
//! `vv-exec converge <case.json> [--levels <n>] [--tolerance-m <m>]`
//!
//! Exit status: 0 done; 1 a gate or check failed; 3 usage or rejected input; 5 run interrupted
//! (resume with the same command).

use std::path::{Component, Path, PathBuf};
use std::process::ExitCode;
use std::sync::atomic::AtomicBool;

use vv_exec::plan::{Plan, read_capped};
use vv_exec::sched::SystemProbe;
use vv_exec::spec::MAX_SPEC_BYTES;
use vv_exec::{converge, engine, equiv, report};

const USAGE: &str = "usage: vv-exec plan <spec.json> | run <spec.json> --output <dir> [--threads <n>] | equiv <dir> --cli <vv-rocket> [--sample <n>] | report <dir> | converge <case.json> [--levels <n>] [--tolerance-m <m>]";

fn json<T: serde::Serialize>(v: &T) -> String {
    serde_json::to_string_pretty(v).expect("serialisable")
}

/// Outputs never go under a directory named `runs`: the historical runs of the lab live there and
/// are being restored separately; this engine writes only to new, separate locations.
fn guard_output(out: &Path) -> Result<(), String> {
    if out
        .components()
        .any(|c| matches!(c, Component::Normal(n) if n.eq_ignore_ascii_case("runs")))
    {
        return Err(format!(
            "{}: vv-exec does not write under a directory named runs (historical evidence)",
            out.display()
        ));
    }
    Ok(())
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
            guard_output(&out).map_err(input)?;
            let threads = match flag(args, "--threads") {
                Some(t) => Some(t.parse::<usize>().map_err(|_| usage())?),
                None => None,
            };
            let plan = plan_from_spec(Path::new(spec)).map_err(input)?;
            let cancel = AtomicBool::new(false);
            let opt = engine::Options {
                probe: &SystemProbe,
                max_threads: threads,
                cancel: &cancel,
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
            guard_output(&out).map_err(input)?;
            let plan = plan_from_output(&out).map_err(input)?;
            let records = engine::read_records(&plan, &out).map_err(input)?;
            let r = equiv::run(&plan, &out, &records, &cli, k).map_err(input)?;
            Ok((json(&r), if r.pass { 0 } else { 1 }))
        }
        Some("report") => {
            let out = PathBuf::from(args.get(1).ok_or_else(usage)?);
            guard_output(&out).map_err(input)?;
            let plan = plan_from_output(&out).map_err(input)?;
            let records = engine::read_records(&plan, &out).map_err(input)?;
            let r = report::build(&plan, &records, &out).map_err(input)?;
            let text = json(&r);
            std::fs::write(out.join("report.json"), format!("{text}\n"))
                .map_err(|e| input(e.to_string()))?;
            Ok((text, if r.status == "valid" { 0 } else { 1 }))
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
