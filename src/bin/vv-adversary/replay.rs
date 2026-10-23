//! `vv-adversary replay`: refaz a campanha em memória e compara byte a byte.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;
use autonomous_systems_vv_lab::replay_controller_evaluation;
use serde::Deserialize;

use crate::campaign::{Inputs, generate};
use crate::eval::{Params, Search};
use crate::identity;
use crate::io::{
    MAX_CAMPAIGN_BYTES, MAX_CASE_FILE_BYTES, MAX_SCENARIO_BYTES, MAX_SMALL_JSON_BYTES, list_files,
    read_bounded, sha256_hex,
};

/// Campos lidos antes da verificação. O resto do documento é saltado pelo
/// serde sem alocação, por isso um `campaign.json` hostil não é materializado.
#[derive(Deserialize)]
struct Recorded {
    prng: RecordedPrng,
    limits: RecordedLimits,
    inputs: RecordedInputs,
}

/// Lido só dos bytes regenerados, depois de serem iguais aos do disco.
#[derive(Deserialize)]
struct VerifiedFailures {
    failures: Vec<RecordedFailure>,
}

#[derive(Deserialize)]
struct RecordedPrng {
    campaign_seed: u64,
    sim_seed: u64,
}

#[derive(Deserialize)]
struct RecordedLimits {
    budget: u32,
    minimize_budget: u32,
    max_failures: u32,
    policies: Vec<ControllerPolicyV1>,
    stall_window_ticks: u32,
    min_progress_mm: u32,
    search: String,
}

#[derive(Deserialize)]
struct RecordedInputs {
    scenario_sha256: String,
    contracts_sha256: String,
    actuator_sha256: String,
    actuator_source: String,
}

#[derive(Deserialize)]
struct RecordedFailure {
    case: u32,
    identity: serde_json::Value,
    original: RecordedSide,
    minimized: RecordedSide,
}

#[derive(Deserialize)]
struct RecordedSide {
    dir: String,
    m4_sha256: String,
}

fn load_input(
    directory: &Path,
    name: &str,
    maximum: usize,
    expected: &str,
) -> Result<Vec<u8>, String> {
    let bytes = read_bounded(&directory.join("inputs").join(name), maximum)?;
    if sha256_hex(&bytes) != expected {
        return Err(format!("input hash mismatch: inputs/{name} was modified"));
    }
    Ok(bytes)
}

pub fn run(campaign_path: &Path) -> Result<Vec<String>, String> {
    // Só o ficheiro principal comparado abaixo; recusa `campaign.json:fluxo` e outros nomes.
    if campaign_path.file_name().and_then(|name| name.to_str()) != Some("campaign.json") {
        return Err("replay expects a path whose file name is exactly campaign.json".into());
    }
    let directory = campaign_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let campaign_bytes = read_bounded(campaign_path, MAX_CAMPAIGN_BYTES)?;
    let recorded: Recorded = serde_json::from_slice(&campaign_bytes)
        .map_err(|error| format!("campaign.json is not a valid campaign: {error}"))?;
    let params = Params {
        search: Search::parse(&recorded.limits.search)?,
        campaign_seed: recorded.prng.campaign_seed,
        sim_seed: recorded.prng.sim_seed,
        policies: recorded.limits.policies,
        budget: recorded.limits.budget,
        minimize_budget: recorded.limits.minimize_budget,
        max_failures: recorded.limits.max_failures,
        mission_policy: MissionPolicy {
            stall_window_ticks: recorded.limits.stall_window_ticks,
            min_progress_mm: recorded.limits.min_progress_mm,
        },
    };
    params.validate()?;
    let inputs = Inputs {
        scenario: load_input(
            directory,
            "scenario.json",
            MAX_SCENARIO_BYTES,
            &recorded.inputs.scenario_sha256,
        )?,
        contracts: load_input(
            directory,
            "contracts.json",
            MAX_SMALL_JSON_BYTES,
            &recorded.inputs.contracts_sha256,
        )?,
        actuator: load_input(
            directory,
            "actuator.json",
            MAX_SMALL_JSON_BYTES,
            &recorded.inputs.actuator_sha256,
        )?,
        actuator_from_file: recorded.inputs.actuator_source == "file",
    };
    let generated = generate(&inputs, params)?;
    let mut lines = vec!["inputs: sha256 verified for 3 files".to_owned()];
    for (relative, expected) in &generated.files {
        let found = read_bounded(&directory.join(relative), MAX_CASE_FILE_BYTES)
            .map_err(|error| format!("{relative}: {error}"))?;
        if &found != expected {
            return Err(format!(
                "{relative} differs from the regenerated campaign (tampered or non-deterministic)"
            ));
        }
    }
    let expected: BTreeSet<&str> = generated
        .files
        .iter()
        .map(|(name, _)| name.as_str())
        .collect();
    if let Some(extra) = list_files(directory)?
        .iter()
        .find(|name| !expected.contains(name.as_str()))
    {
        return Err(format!("unexpected file {extra}"));
    }
    lines.push(format!(
        "regenerated {} files byte-identical (campaign.json, report.md, inputs, cases)",
        generated.files.len()
    ));
    // Os casos reproduzem-se a partir dos bytes já verificados, sem reler o disco.
    let verified: BTreeMap<&str, &[u8]> = generated
        .files
        .iter()
        .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
        .collect();
    let campaign = verified
        .get("campaign.json")
        .ok_or("regenerated campaign has no campaign.json")?;
    let VerifiedFailures { failures } = serde_json::from_slice(campaign)
        .map_err(|error| format!("regenerated campaign.json is not readable: {error}"))?;
    for failure in &failures {
        for (label, side) in [
            ("original", &failure.original),
            ("minimized", &failure.minimized),
        ] {
            let outcome = replay_case(&verified, &side.dir, &side.m4_sha256)?;
            if label == "minimized" {
                let policy = failure
                    .identity
                    .get("policy")
                    .and_then(|value| value.as_str())
                    .unwrap_or_default();
                let found = identity::violations(policy, &outcome).iter().any(|id| {
                    serde_json::to_value(id).is_ok_and(|value| value == failure.identity)
                });
                if !found {
                    return Err(format!(
                        "case {:02}: minimized failure identity not reproduced",
                        failure.case
                    ));
                }
            }
            lines.push(format!(
                "case {:02} {label}: m4 replay verified{}",
                failure.case,
                if label == "minimized" {
                    ", failure identity reproduced"
                } else {
                    ""
                }
            ));
        }
    }
    Ok(lines)
}

pub(crate) fn replay_case(
    verified: &BTreeMap<&str, &[u8]>,
    case_dir: &str,
    expected_m4_sha256: &str,
) -> Result<autonomous_systems_vv_lab::ControllerEvaluationOutcome, String> {
    let read = |name: &str| -> Result<&str, String> {
        let path = format!("{case_dir}/{name}");
        let bytes = verified
            .get(path.as_str())
            .ok_or_else(|| format!("{path} is not part of the verified campaign"))?;
        std::str::from_utf8(bytes).map_err(|_| format!("{path} is not valid UTF-8"))
    };
    let manifest = read("m4.json")?;
    if sha256_hex(manifest.as_bytes()) != expected_m4_sha256 {
        return Err(format!(
            "{case_dir}/m4.json hash differs from campaign.json"
        ));
    }
    let (events, report, mission, verification) = (
        read("events.json")?,
        read("report.json")?,
        read("mission.json")?,
        read("verification.json")?,
    );
    replay_controller_evaluation(manifest, events, report, mission, verification)
        .map_err(|error| format!("{case_dir}: {error}"))
}
