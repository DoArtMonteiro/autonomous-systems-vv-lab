//! Testes de integração do binário `vv-adversary` (orçamentos pequenos).

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const ADVERSARY: &str = env!("CARGO_BIN_EXE_vv-adversary");
const VV_LAB: &str = env!("CARGO_BIN_EXE_vv-lab");
const BASE: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/scenarios/m3/nominal-stop.json"
);
const CONTRACTS: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/scenarios/m3/contracts-nominal.json"
);

/// Diretório temporário único, apagado no fim.
struct Scratch(PathBuf);

impl Scratch {
    fn new(name: &str) -> Self {
        let path =
            std::env::temp_dir().join(format!("vv-adversary-it-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
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

fn adversary(args: &[&str]) -> Output {
    Command::new(ADVERSARY).args(args).output().unwrap()
}

fn campaign(output: &Path, seed: &str, extra: &[&str]) -> Output {
    let mut args = vec![
        "campaign",
        "--base",
        BASE,
        "--contracts",
        CONTRACTS,
        "--campaign-seed",
        seed,
        "--sim-seed",
        "42",
        "--budget",
        "24",
        "--minimize-budget",
        "48",
        "--max-failures",
        "4",
        "--output",
        output.to_str().unwrap(),
    ];
    for pair in extra.chunks(2) {
        if let Some(index) = args.iter().position(|arg| *arg == pair[0]) {
            args.drain(index..index + 2);
        }
    }
    args.extend_from_slice(extra);
    adversary(&args)
}

fn tree(root: &Path) -> BTreeMap<String, Vec<u8>> {
    fn walk(root: &Path, directory: &Path, files: &mut BTreeMap<String, Vec<u8>>) {
        for entry in fs::read_dir(directory).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                walk(root, &path, files);
            } else {
                let relative = path.strip_prefix(root).unwrap().to_string_lossy();
                files.insert(relative.replace('\\', "/"), fs::read(&path).unwrap());
            }
        }
    }
    let mut files = BTreeMap::new();
    walk(root, root, &mut files);
    files
}

fn campaign_json(root: &Path) -> serde_json::Value {
    serde_json::from_slice(&fs::read(root.join("campaign.json")).unwrap()).unwrap()
}

#[test]
fn same_arguments_give_identical_bytes_and_other_seed_other_candidates() {
    let scratch = Scratch::new("determinism");
    let (first, second, other) = (scratch.join("a"), scratch.join("b"), scratch.join("other"));
    for output in [&first, &second] {
        let result = campaign(output, "42", &[]);
        assert!(result.status.success(), "{result:?}");
    }
    assert!(campaign(&other, "43", &[]).status.success());
    assert_eq!(tree(&first), tree(&second), "same args, same bytes");
    let candidates = |root: &Path| campaign_json(root)["candidates"].clone();
    assert_ne!(candidates(&first), candidates(&other));
}

#[test]
fn clean_control_then_search_finds_replayable_minimized_violations() {
    let scratch = Scratch::new("search");
    let output = scratch.join("out");
    let result = campaign(&output, "42", &[]);
    assert!(result.status.success(), "{result:?}");
    let campaign = campaign_json(&output);
    assert_eq!(campaign["schema"], "vv-adversary.campaign.v1");
    for row in campaign["control"].as_array().unwrap() {
        assert_eq!(row["safety"], "passed");
        assert_eq!(row["temporal"], "PASS");
        assert!(row["violations"].as_array().unwrap().is_empty());
    }
    assert_eq!(campaign["metrics"]["control_violations"], 0);
    let failures = campaign["failures"].as_array().unwrap();
    assert!(!failures.is_empty(), "search must discover violations");
    for failure in failures {
        let reduction = &failure["reduction"];
        for key in ["atoms", "active_fault_ticks", "steps"] {
            assert!(reduction[key]["after"].as_u64() <= reduction[key]["before"].as_u64());
        }
        assert_ne!(failure["recheck"]["result"], "disagree", "{failure}");
        for side in ["original", "minimized"] {
            let directory = failure[side]["dir"].as_str().unwrap();
            let manifest = output.join(directory).join("m4.json");
            let replay = Command::new(VV_LAB)
                .arg("replay-m4")
                .arg(&manifest)
                .output()
                .unwrap();
            assert!(replay.status.success(), "{directory}: {replay:?}");
        }
    }
    let replayed = adversary(&["replay", output.join("campaign.json").to_str().unwrap()]);
    assert!(replayed.status.success(), "{replayed:?}");
}

fn replay_fails(output: &Path, needle: &str) {
    let result = adversary(&["replay", output.join("campaign.json").to_str().unwrap()]);
    assert_eq!(result.status.code(), Some(1), "{result:?}");
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.contains(needle), "{stderr}");
}

#[test]
fn replay_detects_tampered_input_campaign_and_case_bytes() {
    let scratch = Scratch::new("tamper");
    let output = scratch.join("out");
    assert!(campaign(&output, "42", &[]).status.success());

    let input = output.join("inputs/scenario.json");
    let original = fs::read(&input).unwrap();
    let mut changed = original.clone();
    let position = changed.iter().position(|b| *b == b'm').unwrap();
    changed[position] = b'n';
    fs::write(&input, &changed).unwrap();
    replay_fails(&output, "input hash mismatch");
    fs::write(&input, &original).unwrap();

    let path = output.join("campaign.json");
    let original = fs::read(&path).unwrap();
    let text = String::from_utf8(original.clone()).unwrap();
    let marker = "\"risk\": ";
    let at = text.find(marker).unwrap() + marker.len();
    let mut bumped = text.clone();
    bumped.insert(at, '9');
    fs::write(&path, bumped).unwrap();
    replay_fails(&output, "campaign.json differs");
    fs::write(&path, &original).unwrap();

    let events = tree(&output)
        .keys()
        .find(|name| name.ends_with("minimized/events.json"))
        .cloned()
        .expect("a minimized case exists");
    let target = output.join(&events);
    let original = fs::read(&target).unwrap();
    let mut changed = original.clone();
    changed[10] = if changed[10] == b'7' { b'8' } else { b'7' };
    fs::write(&target, &changed).unwrap();
    replay_fails(&output, "differs");
    fs::write(&target, &original).unwrap();

    let ok = adversary(&["replay", path.to_str().unwrap()]);
    assert!(ok.status.success(), "{ok:?}");
}

#[test]
fn usage_and_input_errors_exit_two_and_output_must_be_empty() {
    let scratch = Scratch::new("usage");
    let output = scratch.join("out");
    assert!(campaign(&output, "1", &[]).status.success());
    let occupied = campaign(&output, "1", &[]);
    assert_eq!(occupied.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&occupied.stderr).contains("must be empty or absent"));

    let fresh = scratch.join("fresh");
    assert_eq!(
        campaign(&fresh, "1", &["--budget", "0"]).status.code(),
        Some(2)
    );
    assert_eq!(
        campaign(&fresh, "1", &["--policies", "bogus"])
            .status
            .code(),
        Some(2)
    );
    assert_eq!(adversary(&["campaign"]).status.code(), Some(2));
    assert_eq!(adversary(&[]).status.code(), Some(2));
    assert!(!fresh.exists(), "usage errors must not create output");
}

#[test]
fn single_policy_campaign_works() {
    let scratch = Scratch::new("single");
    let output = scratch.join("out");
    let result = campaign(&output, "42", &["--policies", "x_first"]);
    assert!(result.status.success(), "{result:?}");
    let campaign = campaign_json(&output);
    assert_eq!(
        campaign["limits"]["policies"],
        serde_json::json!(["x_first"])
    );
    assert!(
        adversary(&["replay", output.join("campaign.json").to_str().unwrap()])
            .status
            .success()
    );
}

#[test]
fn every_search_strategy_is_recorded_and_replays() {
    let scratch = Scratch::new("strategies");
    for strategy in ["uniform", "biased", "guided"] {
        let output = scratch.join(strategy);
        let result = campaign(&output, "7", &["--search", strategy, "--budget", "8"]);
        assert!(result.status.success(), "{result:?}");
        assert_eq!(campaign_json(&output)["limits"]["search"], strategy);
        let replay = adversary(&["replay", output.join("campaign.json").to_str().unwrap()]);
        assert!(replay.status.success(), "{strategy}: {replay:?}");
    }
    let rejected = campaign(&scratch.join("bad"), "7", &["--search", "greedy"]);
    assert_eq!(rejected.status.code(), Some(2));
}

#[test]
fn replay_rejects_files_outside_the_generated_set() {
    let scratch = Scratch::new("stray");
    let output = scratch.join("out");
    assert!(campaign(&output, "42", &[]).status.success());
    let case_dir = tree(&output)
        .keys()
        .find(|name| name.ends_with("minimized/events.json"))
        .map(|name| name.trim_end_matches("events.json").to_owned())
        .expect("a minimized case exists");
    for stray in [format!("{case_dir}stray.txt"), "stray.txt".to_owned()] {
        let path = output.join(&stray);
        fs::write(&path, b"x").unwrap();
        replay_fails(&output, &format!("unexpected file {stray}"));
        fs::remove_file(&path).unwrap();
    }
    let ok = adversary(&["replay", output.join("campaign.json").to_str().unwrap()]);
    assert!(ok.status.success(), "{ok:?}");
}

#[cfg(unix)]
#[test]
fn replay_rejects_symlinks() {
    let scratch = Scratch::new("symlink");
    let output = scratch.join("out");
    assert!(campaign(&output, "42", &[]).status.success());
    std::os::unix::fs::symlink(output.join("report.md"), output.join("link")).unwrap();
    replay_fails(&output, "symlink or special file");
}

#[test]
fn invalid_base_exits_two_without_creating_output() {
    let scratch = Scratch::new("badbase");
    let output = scratch.join("out");
    let missing = scratch.join("missing.json");
    let result = campaign(&output, "1", &["--base", missing.to_str().unwrap()]);
    assert_eq!(result.status.code(), Some(2), "{result:?}");
    assert!(!output.exists(), "invalid inputs must not create output");
    let garbage = scratch.join("garbage.json");
    fs::create_dir_all(&scratch.0).unwrap();
    fs::write(&garbage, b"{").unwrap();
    let result = campaign(&output, "1", &["--base", garbage.to_str().unwrap()]);
    assert_eq!(result.status.code(), Some(2), "{result:?}");
    assert!(!output.exists(), "invalid inputs must not create output");
}

#[test]
fn known_faulty_base_reports_inherited_classes_and_replays() {
    let scratch = Scratch::new("inherited");
    let output = scratch.join("out");
    let root = env!("CARGO_MANIFEST_DIR");
    let base = format!("{root}/scenarios/m3/delayed-after-fallback.json");
    let actuator = format!("{root}/scenarios/m3/actuator-delayed.json");
    let result = campaign(
        &output,
        "42",
        &[
            "--base",
            &base,
            "--actuator",
            &actuator,
            "--policies",
            "dominant_axis",
        ],
    );
    assert!(result.status.success(), "{result:?}");
    let stdout = String::from_utf8_lossy(&result.stdout);
    assert!(stdout.contains("inherited_classes="), "{stdout}");
    assert!(stdout.contains("unidentified_violations=0"), "{stdout}");
    let metrics = &campaign_json(&output)["metrics"];
    assert!(metrics["inherited_classes_found"].as_u64().unwrap() > 0);
    assert!(metrics["control_violations"].as_u64().unwrap() > 0);
    assert_eq!(metrics["unidentified_violations"], 0);
    let replay = adversary(&["replay", output.join("campaign.json").to_str().unwrap()]);
    assert!(replay.status.success(), "{replay:?}");
}

#[test]
fn replay_hardening_rejects_noncanonical_paths_and_oversized_campaigns() {
    let scratch = Scratch::new("hardening");
    let output = scratch.join("out");
    assert!(campaign(&output, "42", &[]).status.success());
    // Só o nome exato `campaign.json`; um fluxo alternativo ou outro nome é recusado antes de ler.
    for argument in ["campaign.json:alt", "campaign.json::$DATA", "CAMPAIGN.JSON"] {
        let result = adversary(&["replay", output.join(argument).to_str().unwrap()]);
        assert!(!result.status.success(), "{argument}: {result:?}");
        let stderr = String::from_utf8_lossy(&result.stderr);
        assert!(
            stderr.contains("exactly campaign.json"),
            "{argument}: {stderr}"
        );
    }
    // Um nome terminado em ponto esconde conteúdo em Windows; é recusado em todos os sistemas.
    let dotted = output.join("ex.");
    #[cfg(windows)]
    let dotted = std::path::PathBuf::from(format!(r"\\?\{}", dotted.display()));
    fs::create_dir(&dotted).unwrap();
    fs::write(dotted.join("hidden.txt"), b"x").unwrap();
    replay_fails(&output, "non-canonical name");
    fs::remove_file(dotted.join("hidden.txt")).unwrap();
    fs::remove_dir(&dotted).unwrap();
    // `campaign.json` acima do limite é recusado antes de ser analisado.
    let campaign_path = output.join("campaign.json");
    let original = fs::read(&campaign_path).unwrap();
    fs::write(&campaign_path, vec![b' '; 32 * 1024 * 1024 + 1]).unwrap();
    replay_fails(&output, "exceeds the 33554432 byte input limit");
    fs::write(&campaign_path, original).unwrap();
    let ok = adversary(&["replay", campaign_path.to_str().unwrap()]);
    assert!(ok.status.success(), "{ok:?}");
}
