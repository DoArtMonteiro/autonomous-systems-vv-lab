//! Testes de integração do binário `vv-repair` (experiência pequena).

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const REPAIR: &str = env!("CARGO_BIN_EXE_vv-repair");
const VV_LAB: &str = env!("CARGO_BIN_EXE_vv-lab");
const SCENARIO: &str = include_str!("../scenarios/m3/nominal-stop.json");
const CONTRACTS: &str = include_str!("../scenarios/m3/contracts-nominal.json");

const EXPERIMENT: &str = r#"{
  "schema": "vv-repair.experiment.v1",
  "name": "it_small",
  "sim_seeds": [42],
  "tuning_seeds": [1, 2],
  "heldout_seeds": [3],
  "workloads_per_seed": 4,
  "minimize_budget": 24,
  "max_corpus_per_suite": 2,
  "suites": [{ "id": "nominal", "scenario": "scenario.json", "contracts": "contracts.json" }],
  "acceptance": {
    "alpha_permille": 50,
    "max_completion_loss_permille": 10,
    "max_mean_distance_increase_mm": 100,
    "min_heldout_pairs": 1
  },
  "baseline": { "id": "baseline", "policy": "dominant_axis", "rationale": "canonical" },
  "candidates": [
    { "id": "watchdog_2", "policy": "dominant_axis", "overrides": { "fallback_after_ticks": 2 }, "rationale": "deadline" }
  ]
}"#;

/// Diretório temporário único, apagado no fim.
struct Scratch(PathBuf);

impl Scratch {
    fn new(name: &str, experiment: &str) -> Self {
        let path = std::env::temp_dir().join(format!("vv-repair-it-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        fs::write(path.join("scenario.json"), SCENARIO).unwrap();
        fs::write(path.join("contracts.json"), CONTRACTS).unwrap();
        fs::write(path.join("experiment.json"), experiment).unwrap();
        Scratch(path)
    }

    fn join(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn run(scratch: &Scratch, output: &str) -> Output {
    Command::new(REPAIR)
        .arg("run")
        .arg("--experiment")
        .arg(scratch.join("experiment.json"))
        .arg("--output")
        .arg(scratch.join(output))
        .output()
        .unwrap()
}

fn replay(scratch: &Scratch, output: &str) -> Output {
    Command::new(REPAIR)
        .arg("replay")
        .arg(scratch.join(output))
        .output()
        .unwrap()
}

fn tree(root: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut files = BTreeMap::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                stack.push(path);
            } else {
                let name = path.strip_prefix(root).unwrap().to_string_lossy();
                files.insert(name.replace('\\', "/"), fs::read(&path).unwrap());
            }
        }
    }
    files
}

fn evidence(root: &Path) -> serde_json::Value {
    serde_json::from_slice(&fs::read(root.join("evidence.json")).unwrap()).unwrap()
}

#[test]
fn run_is_deterministic_and_replays() {
    let scratch = Scratch::new("deterministic", EXPERIMENT);
    let first = run(&scratch, "a");
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    assert!(run(&scratch, "b").status.success());
    assert_eq!(tree(&scratch.join("a")), tree(&scratch.join("b")));
    let replayed = replay(&scratch, "a");
    assert!(
        replayed.status.success(),
        "{}",
        String::from_utf8_lossy(&replayed.stderr)
    );
    assert!(String::from_utf8_lossy(&replayed.stdout).contains("vv-repair replay: OK"));
}

#[test]
fn evidence_pairs_every_config_on_the_same_workloads() {
    let scratch = Scratch::new("pairs", EXPERIMENT);
    assert!(run(&scratch, "out").status.success());
    let doc = evidence(&scratch.join("out"));
    assert_eq!(doc["schema"], "vv-repair.evidence.v1");
    assert_eq!(
        doc["source_sha256"],
        "620f76031548075a66a2e4117956a29d1b63d846263b4aed224b74e2e2501f6b"
    );
    let workloads = doc["workloads"]["nominal"].as_array().unwrap().len();
    assert!(workloads > 1);
    for config in ["baseline", "watchdog_2"] {
        let rows = doc["results"]["nominal"][config]["42"].as_array().unwrap();
        assert_eq!(rows.len(), workloads, "{config}");
    }
    let configs = doc["configs"].as_array().unwrap();
    assert_eq!(
        configs[0]["effective"]["nominal"]["fallback_after_ticks"],
        3
    );
    assert_eq!(
        configs[1]["effective"]["nominal"]["fallback_after_ticks"],
        2
    );
    assert_eq!(configs[1]["changes_oracle"], false);
    let corpus = doc["corpus"].as_array().unwrap();
    assert!(!corpus.is_empty());
    for item in corpus {
        assert_eq!(item["found_on"], "baseline");
        assert_eq!(item["replay"]["baseline"]["status"], "persisted");
        assert!(item["replay"]["watchdog_2"]["status"].is_string());
        let case = scratch
            .join("out")
            .join(item["case_dir"].as_str().unwrap())
            .join("m4.json");
        let output = Command::new(VV_LAB)
            .arg("replay-m4")
            .arg(&case)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
}

fn replay_fails(scratch: &Scratch, output: &str, needle: &str) {
    let result = replay(scratch, output);
    assert!(!result.status.success());
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.contains(needle), "expected '{needle}' in: {stderr}");
}

#[test]
fn replay_detects_tampering_and_extra_files() {
    let scratch = Scratch::new("tamper", EXPERIMENT);
    assert!(run(&scratch, "out").status.success());
    let out = scratch.join("out");

    let evidence_path = out.join("evidence.json");
    let original = fs::read(&evidence_path).unwrap();
    let mut changed = original.clone();
    let index = changed.iter().position(|byte| *byte == b'0').unwrap();
    changed[index] = b'1';
    fs::write(&evidence_path, &changed).unwrap();
    replay_fails(&scratch, "out", "evidence.json differs");
    fs::write(&evidence_path, &original).unwrap();

    let scenario = out.join("inputs/suites/nominal/scenario.json");
    let saved = fs::read_to_string(&scenario).unwrap();
    fs::write(&scenario, saved.replace("\"steps\": 16", "\"steps\": 15")).unwrap();
    // Outra base gera outras cargas: a recusa pode vir de bytes ou de ficheiros diferentes.
    replay_fails(&scratch, "out", "replay FAILED");
    fs::write(&scenario, &saved).unwrap();

    fs::write(out.join("extra.json"), b"{}").unwrap();
    replay_fails(&scratch, "out", "unexpected file extra.json");
    fs::remove_file(out.join("extra.json")).unwrap();
    assert!(replay(&scratch, "out").status.success());
}

#[test]
fn replay_rejects_directories_that_run_did_not_create() {
    let scratch = Scratch::new("empty_dir", EXPERIMENT);
    assert!(run(&scratch, "out").status.success());
    fs::create_dir_all(scratch.join("out").join("extra_dir").join("sub")).unwrap();
    replay_fails(&scratch, "out", "unexpected directory extra_dir");
    fs::remove_dir_all(scratch.join("out").join("extra_dir")).unwrap();
    fs::create_dir_all(scratch.join("out").join("cases").join("stray")).unwrap();
    replay_fails(&scratch, "out", "unexpected directory cases/stray");
    fs::remove_dir_all(scratch.join("out").join("cases").join("stray")).unwrap();
    assert!(replay(&scratch, "out").status.success());
}

#[test]
fn invalid_experiments_exit_two_without_output() {
    let cases = [
        ("unknown_field", "\"name\"", "\"surprise\": 1, \"name\""),
        (
            "overlap",
            "\"heldout_seeds\": [3]",
            "\"heldout_seeds\": [2]",
        ),
        (
            "bad_override",
            "\"fallback_after_ticks\": 2",
            "\"geometry\": 2",
        ),
        (
            "zero_stride",
            "\"fallback_after_ticks\": 2",
            "\"stride_permille\": 0",
        ),
    ];
    for (name, from, to) in cases {
        let scratch = Scratch::new(name, &EXPERIMENT.replace(from, to));
        let output = run(&scratch, "out");
        assert_eq!(output.status.code(), Some(2), "{name}");
        assert!(!scratch.join("out").exists(), "{name}");
    }
}

#[test]
fn output_must_be_empty_and_usage_errors_exit_two() {
    let scratch = Scratch::new("usage", EXPERIMENT);
    fs::create_dir_all(scratch.join("out")).unwrap();
    fs::write(scratch.join("out/keep.txt"), b"x").unwrap();
    assert_eq!(run(&scratch, "out").status.code(), Some(2));
    let bare = Command::new(REPAIR).arg("run").output().unwrap();
    assert_eq!(bare.status.code(), Some(2));
    let none = Command::new(REPAIR).output().unwrap();
    assert_eq!(none.status.code(), Some(2));
}
