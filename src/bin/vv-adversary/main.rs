//! `vv-adversary`: pesquisa adversarial determinística sobre o laboratório V&V.

mod atoms;
mod campaign;
mod cases;
mod eval;
mod identity;
mod io;
mod markdown;
mod minimize;
mod model;
mod recheck;
mod replay;
mod sampling;
mod search;
mod simplify;
mod summary;
#[cfg(test)]
mod unit_tests;

use std::collections::BTreeSet;
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;
use autonomous_systems_vv_lab::parse_controller_id;

use campaign::{Inputs, default_actuator_bytes, generate};
use eval::{Params, Search};

const USAGE: &str = "usage:
  vv-adversary campaign --base <scenario.json> --contracts <contracts.json> [--actuator <actuator.json>]
      --campaign-seed <u64> --sim-seed <u64> [--policies dominant_axis,x_first]
      [--budget <1..=512, default 64>] [--minimize-budget <1..=256, default 96>]
      [--max-failures <1..=16, default 8>] [--stall-window-ticks <n>] [--min-progress-mm <n>]
      [--search <uniform|biased|guided, default uniform>]
      --output <dir>
  vv-adversary replay <campaign.json>";

struct CampaignArgs {
    base: PathBuf,
    contracts: PathBuf,
    actuator: Option<PathBuf>,
    output: PathBuf,
    params: Params,
}

fn number<T: std::str::FromStr>(flag: &str, value: &str) -> Result<T, String> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(format!("{flag} expects a non-negative decimal integer"));
    }
    value
        .parse()
        .map_err(|_| format!("{flag} value is out of range"))
}

fn parse_campaign(args: &[String]) -> Result<CampaignArgs, String> {
    let mut seen = BTreeSet::new();
    let (mut base, mut contracts, mut actuator, mut output) = (None, None, None, None);
    let (mut campaign_seed, mut sim_seed) = (None, None);
    let mut policies = vec![ControllerPolicyV1::DominantAxis, ControllerPolicyV1::XFirst];
    let (mut budget, mut minimize_budget, mut max_failures) = (64_u32, 96_u32, 8_u32);
    let mut mission_policy = MissionPolicy::default();
    // Por omissão: a estratégia com mais classes na ablação medida (scripts/adversarial_ablation.py).
    let mut search = Search::Uniform;
    let mut index = 0;
    while index < args.len() {
        let flag = args[index].as_str();
        if !seen.insert(flag.to_owned()) {
            return Err(format!("{flag} may be specified only once"));
        }
        let value = args
            .get(index + 1)
            .ok_or_else(|| format!("missing value after {flag}"))?;
        match flag {
            "--base" => base = Some(PathBuf::from(value)),
            "--contracts" => contracts = Some(PathBuf::from(value)),
            "--actuator" => actuator = Some(PathBuf::from(value)),
            "--output" => output = Some(PathBuf::from(value)),
            "--campaign-seed" => campaign_seed = Some(number(flag, value)?),
            "--sim-seed" => sim_seed = Some(number(flag, value)?),
            "--budget" => budget = number(flag, value)?,
            "--minimize-budget" => minimize_budget = number(flag, value)?,
            "--max-failures" => max_failures = number(flag, value)?,
            "--stall-window-ticks" => mission_policy.stall_window_ticks = number(flag, value)?,
            "--min-progress-mm" => mission_policy.min_progress_mm = number(flag, value)?,
            "--search" => search = Search::parse(value)?,
            "--policies" => {
                policies = value
                    .split(',')
                    .map(|name| parse_controller_id(name).map_err(|error| error.to_string()))
                    .collect::<Result<_, _>>()?
            }
            _ => return Err(format!("unknown option {flag}")),
        }
        index += 2;
    }
    let params = Params {
        search,
        campaign_seed: campaign_seed.ok_or("--campaign-seed is required")?,
        sim_seed: sim_seed.ok_or("--sim-seed is required")?,
        policies,
        budget,
        minimize_budget,
        max_failures,
        mission_policy,
    };
    params.validate()?;
    Ok(CampaignArgs {
        base: base.ok_or("--base is required")?,
        contracts: contracts.ok_or("--contracts is required")?,
        actuator,
        output: output.ok_or("--output is required")?,
        params,
    })
}

fn run_campaign(args: &[String]) -> Result<(), String> {
    let parsed = parse_campaign(args)?;
    let started = Instant::now();
    let scenario = io::read_bounded(&parsed.base, io::MAX_SCENARIO_BYTES)?;
    let contracts = io::read_bounded(&parsed.contracts, io::MAX_SMALL_JSON_BYTES)?;
    let (actuator, from_file) = match &parsed.actuator {
        Some(path) => (io::read_bounded(path, io::MAX_SMALL_JSON_BYTES)?, true),
        None => (default_actuator_bytes()?, false),
    };
    let inputs = Inputs {
        scenario,
        contracts,
        actuator,
        actuator_from_file: from_file,
    };
    io::check_output(&parsed.output)?;
    let generated = generate(&inputs, parsed.params)?;
    io::prepare_output(&parsed.output)?;
    io::write_files(&parsed.output, &generated.files)?;
    println!("{}", generated.summary);
    eprintln!("elapsed_ms={}", started.elapsed().as_millis());
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("campaign") => match run_campaign(&args[1..]) {
            Ok(()) => ExitCode::SUCCESS,
            Err(message) => {
                eprintln!("error: {message}");
                ExitCode::from(2)
            }
        },
        Some("replay") if args.len() == 2 => {
            let started = Instant::now();
            match replay::run(&PathBuf::from(&args[1])) {
                Ok(lines) => {
                    for line in lines {
                        println!("{line}");
                    }
                    println!("vv-adversary replay: OK");
                    eprintln!("elapsed_ms={}", started.elapsed().as_millis());
                    ExitCode::SUCCESS
                }
                Err(message) => {
                    eprintln!("replay FAILED: {message}");
                    ExitCode::from(1)
                }
            }
        }
        _ => {
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}
