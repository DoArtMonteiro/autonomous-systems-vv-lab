//! `vv-rocket run <case.json> --output <dir>` | `vv-rocket land <landing.json> --seed <u64> --output <dir>` |
//! `vv-rocket replay <dir>` | `vv-rocket verify [--output <file>]`
//!
//! Exit codes: 0 success or verified, 1 replay or verification failed, 2 (`land` only) the landing
//! did not land or an invariant failed (artifacts are still written), 3 usage or input error.

use std::path::PathBuf;
use std::process::ExitCode;

use vv_rocket::{landing_run, run, verify};

fn usage() -> ExitCode {
    eprintln!(
        "usage: vv-rocket run <case.json> --output <dir> | land <landing.json> --seed <u64> --output <dir> | replay <dir> | verify [--output <file>]"
    );
    ExitCode::from(3)
}

fn print_json<T: serde::Serialize>(value: &T) -> Result<String, String> {
    serde_json::to_string_pretty(value).map_err(|e| e.to_string())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    let outcome = match args.as_slice() {
        ["run", case, "--output", out] => run::write_run(&PathBuf::from(case), &PathBuf::from(out))
            .and_then(|m| print_json(&m))
            .map(|text| (text, true)),
        ["land", case, "--seed", seed, "--output", out] => {
            let Ok(seed) = seed.parse::<u64>() else {
                return usage();
            };
            let landed =
                landing_run::write_landing(&PathBuf::from(case), seed, &PathBuf::from(out))
                    .and_then(|m| print_json(&m).map(|text| (text, m.all_pass())));
            return match landed {
                Ok((text, ok)) => {
                    println!("{text}");
                    ExitCode::from(if ok { 0 } else { 2 })
                }
                Err(e) => {
                    eprintln!("vv-rocket: {e}");
                    ExitCode::from(3)
                }
            };
        }
        ["replay", dir] => {
            let report = run::replay(&PathBuf::from(dir));
            print_json(&report).map(|text| (text, report.status == "verified"))
        }
        ["verify"] | ["verify", "--output", _] => {
            let report = verify::run_all();
            print_json(&report).and_then(|text| {
                if let ["verify", "--output", file] = args.as_slice() {
                    std::fs::write(file, format!("{text}\n"))
                        .map_err(|e| format!("{file}: {e}"))?;
                }
                Ok((text, report.all_pass))
            })
        }
        _ => return usage(),
    };
    match outcome {
        Ok((text, ok)) => {
            println!("{text}");
            if ok {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        Err(e) => {
            eprintln!("vv-rocket: {e}");
            ExitCode::from(3)
        }
    }
}
