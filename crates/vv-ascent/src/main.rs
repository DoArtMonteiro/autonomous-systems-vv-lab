//! `vv-ascent run <case.json> --seed <n> --output <dir>` | `vv-ascent replay <dir>`
//! | `vv-ascent summary <case.json> --seed <n>` (no files written).

use std::path::Path;
use std::process::ExitCode;

use vv_ascent::run::{compute, pretty, replay, write_run};

fn usage() -> ExitCode {
    eprintln!(
        "usage: vv-ascent run <case.json> --seed <n> --output <dir> | replay <dir> | summary <case.json> --seed <n>"
    );
    ExitCode::from(2)
}

fn summary(outputs: &vv_ascent::run::Outputs) -> serde_json::Value {
    let v = &outputs.verification;
    serde_json::json!({
        "outcome": v.outcome,
        "requirements_pass": v.requirements_pass,
        "invariants_pass": v.invariants_pass,
        "invariants_evaluated": v.invariants_evaluated,
        "invariants_not_evaluated": v.invariants_not_evaluated,
        "verdicts": v.verdicts.iter().map(|x| serde_json::json!({
            "id": x.id, "status": x.status, "observed": x.observed, "cause": x.cause,
        })).collect::<Vec<_>>(),
        "events": v.events.iter().filter(|e| e.kind != "throttle_up").map(|e| format!("{:>8.2} s  {:<8} {}", e.tick as f64 * 0.02, outputs.simulation.entities.get(e.entity).map_or("?", |x| x.id), e.kind)).collect::<Vec<_>>(),
    })
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    match args.as_slice() {
        ["run", case, "--seed", seed, "--output", out] => {
            let Ok(seed) = seed.parse::<u64>() else {
                return usage();
            };
            let out = Path::new(out);
            if std::fs::create_dir_all(out).is_err() {
                eprintln!("cannot create the output directory");
                return ExitCode::from(2);
            }
            match write_run(Path::new(case), seed, out) {
                Ok(o) => {
                    println!(
                        "{}",
                        String::from_utf8_lossy(&pretty(&summary(&o))).trim_end()
                    );
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    eprintln!("{e}");
                    ExitCode::from(3)
                }
            }
        }
        ["summary", case, "--seed", seed] => {
            let Ok(seed) = seed.parse::<u64>() else {
                return usage();
            };
            let bytes = match std::fs::read(case) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("{e}");
                    return ExitCode::from(3);
                }
            };
            match compute(&bytes, seed) {
                Ok(o) => {
                    println!(
                        "{}",
                        String::from_utf8_lossy(&pretty(&summary(&o))).trim_end()
                    );
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    eprintln!("{e}");
                    ExitCode::from(3)
                }
            }
        }
        ["replay", dir] => {
            let report = replay(Path::new(dir));
            println!("{}", String::from_utf8_lossy(&pretty(&report)).trim_end());
            if report.status == "verified" {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        _ => usage(),
    }
}
