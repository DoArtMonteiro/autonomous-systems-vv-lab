//! `vv-repair`: compara configurações do controlador em cargas emparelhadas,
//! reproduz contraexemplos conhecidos e procura classes de falha novas.
//!
//! Reutiliza os módulos do `vv-adversary` sem os alterar, e só a API pública da
//! biblioteca.

#[path = "../vv-adversary/atoms.rs"]
mod atoms;
#[path = "../vv-adversary/campaign.rs"]
#[allow(dead_code)]
mod campaign;
#[path = "../vv-adversary/cases.rs"]
mod cases;
#[path = "../vv-adversary/eval.rs"]
#[allow(dead_code)]
mod eval;
mod evidence;
mod experiment;
#[path = "../vv-adversary/identity.rs"]
#[allow(dead_code)]
mod identity;
#[path = "../vv-adversary/io.rs"]
#[allow(dead_code)]
mod io;
mod lab;
#[path = "../vv-adversary/markdown.rs"]
#[allow(dead_code)]
mod markdown;
#[path = "../vv-adversary/minimize.rs"]
mod minimize;
#[path = "../vv-adversary/model.rs"]
#[allow(dead_code)]
mod model;
#[path = "../vv-adversary/recheck.rs"]
mod recheck;
#[path = "../vv-adversary/replay.rs"]
#[allow(dead_code)]
mod replay;
#[path = "../vv-adversary/sampling.rs"]
#[allow(dead_code)]
mod sampling;
#[path = "../vv-adversary/search.rs"]
#[allow(dead_code)]
mod search;
#[path = "../vv-adversary/simplify.rs"]
mod simplify;
#[path = "../vv-adversary/summary.rs"]
#[allow(dead_code)]
mod summary;
#[cfg(test)]
mod unit_tests;
mod workloads;

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

use campaign::{Inputs, default_actuator_bytes};
use experiment::{Experiment, SuiteSpec};
use lab::{Loaded, SuiteInputs, generate};

const USAGE: &str = "usage:
  vv-repair run --experiment <experiment.json> --output <dir>
  vv-repair replay <dir>";
/// Limite de leitura de `evidence.json` e de cada ficheiro reproduzido.
const MAX_EVIDENCE_BYTES: usize = 64 * 1024 * 1024;

fn parse_experiment(bytes: &[u8]) -> Result<Experiment, String> {
    let text = std::str::from_utf8(bytes).map_err(|_| "experiment is not valid UTF-8")?;
    let experiment: Experiment =
        serde_json::from_str(text).map_err(|error| format!("experiment: {error}"))?;
    experiment.validate()?;
    Ok(experiment)
}

/// Origem das entradas das suites.
enum Source {
    /// Caminhos declarados na experiência, relativos ao seu diretório (`run`).
    Declared(PathBuf),
    /// Cópias em `inputs/suites/<id>/` de uma execução gravada (`replay`).
    Stored(PathBuf),
}

impl Source {
    fn path(&self, suite: &SuiteSpec, name: &str, declared: &str) -> PathBuf {
        match self {
            Source::Declared(directory) => directory.join(declared),
            Source::Stored(inputs) => inputs.join("suites").join(&suite.id).join(name),
        }
    }

    /// `None` quando a experiência não declara atuador: usa-se o atuador por omissão.
    fn actuator(&self, suite: &SuiteSpec) -> Option<PathBuf> {
        match self {
            Source::Declared(_) => suite
                .actuator
                .as_deref()
                .map(|declared| self.path(suite, "actuator.json", declared)),
            Source::Stored(_) => Some(self.path(suite, "actuator.json", "")),
        }
    }
}

/// Lê as entradas de cada suite a partir de `source`.
fn load(experiment_bytes: Vec<u8>, source: &Source) -> Result<Loaded, String> {
    let experiment = parse_experiment(&experiment_bytes)?;
    let mut suites = Vec::new();
    for suite in &experiment.suites {
        let scenario_path = source.path(suite, "scenario.json", &suite.scenario);
        let contracts_path = source.path(suite, "contracts.json", &suite.contracts);
        let actuator = match source.actuator(suite) {
            Some(path) => io::read_bounded(&path, io::MAX_SMALL_JSON_BYTES)?,
            None => default_actuator_bytes()?,
        };
        suites.push(SuiteInputs {
            id: suite.id.clone(),
            inputs: Inputs {
                scenario: io::read_bounded(&scenario_path, io::MAX_SCENARIO_BYTES)?,
                contracts: io::read_bounded(&contracts_path, io::MAX_SMALL_JSON_BYTES)?,
                actuator,
                actuator_from_file: suite.actuator.is_some(),
            },
        });
    }
    Ok(Loaded {
        experiment_bytes,
        experiment,
        suites,
    })
}

fn run(args: &[String]) -> Result<(), String> {
    let [flag_a, value_a, flag_b, value_b] = args else {
        return Err(USAGE.into());
    };
    let (experiment_path, output) = match (flag_a.as_str(), flag_b.as_str()) {
        ("--experiment", "--output") => (PathBuf::from(value_a), PathBuf::from(value_b)),
        ("--output", "--experiment") => (PathBuf::from(value_b), PathBuf::from(value_a)),
        _ => return Err(USAGE.into()),
    };
    let started = Instant::now();
    let bytes = io::read_bounded(&experiment_path, io::MAX_SMALL_JSON_BYTES)?;
    let directory = experiment_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_default();
    let loaded = load(bytes, &Source::Declared(directory))?;
    io::check_output(&output)?;
    let generated = generate(&loaded)?;
    write_checked(&output, &generated.files)?;
    println!("{}", generated.summary);
    for (config, millis) in &generated.timing_ms {
        eprintln!("config_elapsed_ms {config}={millis}");
    }
    eprintln!("elapsed_ms={}", started.elapsed().as_millis());
    Ok(())
}

fn write_checked(output: &Path, files: &[(String, Vec<u8>)]) -> Result<(), String> {
    if let Some((name, bytes)) = files.iter().find(|(_, b)| b.len() > MAX_EVIDENCE_BYTES) {
        return Err(format!(
            "{name} of {} bytes exceeds the {MAX_EVIDENCE_BYTES} byte replay limit",
            bytes.len()
        ));
    }
    io::prepare_output(output)?;
    io::write_files(output, files)
}

/// Pastas sob `root` (caminhos relativos com `/`). `io::list_files` já recusou
/// ligações simbólicas e nomes não canónicos na mesma árvore.
fn list_dirs(root: &Path) -> Result<Vec<String>, String> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(directory) = stack.pop() {
        let listing = std::fs::read_dir(&directory)
            .map_err(|error| format!("could not list {}: {error}", directory.display()))?;
        for entry in listing {
            let path = entry.map_err(|error| error.to_string())?.path();
            if std::fs::symlink_metadata(&path).is_ok_and(|meta| meta.is_dir()) {
                let relative = path.strip_prefix(root).map_err(|error| error.to_string())?;
                out.push(relative.to_string_lossy().replace('\\', "/"));
                stack.push(path);
            }
        }
    }
    out.sort();
    Ok(out)
}

/// Regenera tudo a partir das entradas guardadas e exige os mesmos ficheiros e bytes.
fn replay(directory: &Path) -> Result<String, String> {
    let inputs = directory.join("inputs");
    let bytes = io::read_bounded(&inputs.join("experiment.json"), io::MAX_SMALL_JSON_BYTES)?;
    let loaded = load(bytes, &Source::Stored(inputs))?;
    let generated = generate(&loaded)?;
    let expected: BTreeSet<String> = generated.files.iter().map(|(n, _)| n.clone()).collect();
    let actual = io::list_files(directory)?;
    if let Some(extra) = actual.difference(&expected).next() {
        return Err(format!("unexpected file {extra}"));
    }
    if let Some(missing) = expected.difference(&actual).next() {
        return Err(format!("missing file {missing}"));
    }
    // `list_files` só vê ficheiros: uma pasta que nenhum ficheiro gerado usa também é recusada.
    let parents: BTreeSet<&str> = expected
        .iter()
        .flat_map(|name| name.match_indices('/').map(move |(end, _)| &name[..end]))
        .collect();
    if let Some(extra) = list_dirs(directory)?
        .iter()
        .find(|dir| !parents.contains(dir.as_str()))
    {
        return Err(format!("unexpected directory {extra}"));
    }
    for (name, bytes) in &generated.files {
        let stored = io::read_bounded(&directory.join(name), MAX_EVIDENCE_BYTES)?;
        if &stored != bytes {
            return Err(format!("{name} differs from the regenerated bytes"));
        }
    }
    Ok(format!(
        "vv-repair replay: OK files={} {}",
        generated.files.len(),
        generated.summary
    ))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("run") => match run(&args[1..]) {
            Ok(()) => ExitCode::SUCCESS,
            Err(message) => {
                eprintln!("error: {message}");
                ExitCode::from(2)
            }
        },
        Some("replay") if args.len() == 2 => {
            let started = Instant::now();
            match replay(Path::new(&args[1])) {
                Ok(line) => {
                    println!("{line}");
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
