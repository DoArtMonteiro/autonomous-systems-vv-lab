use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use super::{enforce_output_limit, parse_seed, parse_u32, parse_u64, read_text_file};
use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::contracts::ContractSet;
use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;
use autonomous_systems_vv_lab::{
    ArtifactReference, ComparisonPolicyReferences, create_controller_comparison,
    parse_controller_evaluation_manifest, parse_controller_id, parse_scenario,
    replay_controller_evaluation, run_controller_evaluation,
    status_exit_code, validate_controller_evaluation_files,
};

pub(super) fn run_m4_command(args: &[String]) -> Result<u8, String> {
    let arguments = parse_m4_run_arguments(args)?;
    let scenario_text = read_text_file(&arguments.scenario_path, 2 * 1024 * 1024)?;
    let scenario = parse_scenario(&scenario_text).map_err(|error| error.to_string())?;
    let contracts_text = read_text_file(&arguments.contracts_path, 1024 * 1024)?;
    let contract_set =
        ContractSet::from_json(&contracts_text).map_err(|error| error.to_string())?;
    let actuator_config = match &arguments.actuator_path {
        Some(path) => ActuatorConfig::from_json(&read_text_file(path, 1024 * 1024)?)?,
        None => ActuatorConfig::default(),
    };
    let outcome = run_controller_evaluation(
        scenario,
        arguments.seed,
        arguments.controller,
        actuator_config,
        contract_set,
        arguments.mission_policy,
    )
    .map_err(|error| error.to_string())?;
    let events_bytes = serde_json::to_vec(&outcome.artifact).map_err(|error| error.to_string())?;
    let report_bytes =
        serde_json::to_vec(&outcome.artifact.expected_report).map_err(|error| error.to_string())?;
    let mission_bytes = serde_json::to_vec(&outcome.mission).map_err(|error| error.to_string())?;
    let verification_bytes =
        serde_json::to_vec(&outcome.verification).map_err(|error| error.to_string())?;
    let manifest_bytes =
        serde_json::to_vec(&outcome.manifest).map_err(|error| error.to_string())?;
    enforce_output_limit(
        &[
            &events_bytes,
            &report_bytes,
            &mission_bytes,
            &verification_bytes,
            &manifest_bytes,
        ],
        arguments.max_output_bytes,
    )?;
    fs::create_dir_all(&arguments.output_directory)
        .map_err(|error| format!("could not create output directory: {error}"))?;
    for (name, bytes) in [
        ("events.json", events_bytes),
        ("report.json", report_bytes),
        ("mission.json", mission_bytes),
        ("verification.json", verification_bytes),
        ("m4.json", manifest_bytes),
    ] {
        fs::write(arguments.output_directory.join(name), bytes)
            .map_err(|error| format!("could not write {name}: {error}"))?;
    }
    println!(
        "M4 run: controller={}, safety={:?}, temporal={:?}, mission={:?}",
        outcome.manifest.controller_id,
        outcome.manifest.metrics.safety_status,
        outcome.manifest.metrics.temporal_status,
        outcome.manifest.metrics.mission_outcome,
    );
    Ok(status_exit_code(outcome.manifest.metrics.safety_status))
}

pub(super) fn replay_m4_command(args: &[String]) -> Result<u8, String> {
    if args.len() != 1 {
        return Err("replay-m4 requires exactly one m4.json path".into());
    }
    let manifest_path = PathBuf::from(&args[0]);
    let manifest_text = read_text_file(&manifest_path, 4 * 1024 * 1024)?;
    let manifest =
        parse_controller_evaluation_manifest(&manifest_text).map_err(|error| error.to_string())?;
    let parent = manifest_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let events_text = read_text_file(
        &parent.join(&manifest.event_artifact.path),
        128 * 1024 * 1024,
    )?;
    let report_text = read_text_file(
        &parent.join(&manifest.report_artifact.path),
        32 * 1024 * 1024,
    )?;
    let mission_text = read_text_file(
        &parent.join(&manifest.mission_artifact.path),
        4 * 1024 * 1024,
    )?;
    let verification_text = read_text_file(
        &parent.join(&manifest.verification_artifact.path),
        32 * 1024 * 1024,
    )?;
    let replayed = replay_controller_evaluation(
        &manifest_text,
        &events_text,
        &report_text,
        &mission_text,
        &verification_text,
    )
    .map_err(|error| error.to_string())?;
    println!(
        "M4 replay verified: controller={}, safety={:?}, temporal={:?}, mission={:?}",
        replayed.manifest.controller_id,
        replayed.manifest.metrics.safety_status,
        replayed.manifest.metrics.temporal_status,
        replayed.manifest.metrics.mission_outcome,
    );
    Ok(0)
}

pub(super) fn compare_m4_command(args: &[String]) -> Result<u8, String> {
    if args.len() != 4 || args[2] != "--output" {
        return Err("compare-m4 requires two m4.json paths and --output <comparison.json>".into());
    }
    let dominant_path = PathBuf::from(&args[0]);
    let x_first_path = PathBuf::from(&args[1]);
    let comparison_path = PathBuf::from(&args[3]);
    let comparison_parent = comparison_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(comparison_parent)
        .map_err(|error| format!("could not create comparison directory: {error}"))?;
    let dominant = load_m4_evaluation(&dominant_path)?;
    let x_first = load_m4_evaluation(&x_first_path)?;
    let dominant_references = comparison_references(&dominant_path, &dominant, comparison_parent)?;
    let x_first_references = comparison_references(&x_first_path, &x_first, comparison_parent)?;
    let comparison =
        create_controller_comparison(&dominant, &x_first, dominant_references, x_first_references)
            .map_err(|error| error.to_string())?;
    let bytes = serde_json::to_vec(&comparison).map_err(|error| error.to_string())?;
    fs::write(&comparison_path, bytes)
        .map_err(|error| format!("could not write M4 comparison: {error}"))?;
    println!(
        "M4 comparison verified: calendar={}, action_differences={}",
        comparison.normalized_exogenous_calendar_sha256, comparison.action_difference_ticks,
    );
    Ok(0)
}

fn load_m4_evaluation(
    manifest_path: &Path,
) -> Result<autonomous_systems_vv_lab::ControllerEvaluationOutcome, String> {
    let manifest_text = read_text_file(&manifest_path.to_path_buf(), 4 * 1024 * 1024)?;
    let manifest =
        parse_controller_evaluation_manifest(&manifest_text).map_err(|error| error.to_string())?;
    let parent = manifest_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let events_text = read_text_file(
        &parent.join(&manifest.event_artifact.path),
        128 * 1024 * 1024,
    )?;
    let report_text = read_text_file(
        &parent.join(&manifest.report_artifact.path),
        32 * 1024 * 1024,
    )?;
    let mission_text = read_text_file(
        &parent.join(&manifest.mission_artifact.path),
        4 * 1024 * 1024,
    )?;
    let verification_text = read_text_file(
        &parent.join(&manifest.verification_artifact.path),
        32 * 1024 * 1024,
    )?;
    validate_controller_evaluation_files(
        &manifest_text,
        &events_text,
        &report_text,
        &mission_text,
        &verification_text,
    )
    .map_err(|error| error.to_string())
}

fn comparison_references(
    manifest_path: &Path,
    outcome: &autonomous_systems_vv_lab::ControllerEvaluationOutcome,
    comparison_parent: &Path,
) -> Result<ComparisonPolicyReferences, String> {
    let run_directory = manifest_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let event_path = run_directory.join(&outcome.manifest.event_artifact.path);
    let verification_path = run_directory.join(&outcome.manifest.verification_artifact.path);
    Ok(ComparisonPolicyReferences {
        evaluation_manifest: reference_relative_to(
            comparison_parent,
            manifest_path,
            &outcome.manifest.manifest_sha256,
        )?,
        event_artifact: reference_relative_to(
            comparison_parent,
            &event_path,
            &outcome.manifest.event_artifact.sha256,
        )?,
        verification_artifact: reference_relative_to(
            comparison_parent,
            &verification_path,
            &outcome.manifest.verification_artifact.sha256,
        )?,
    })
}

fn reference_relative_to(
    parent: &Path,
    file: &Path,
    digest: &str,
) -> Result<ArtifactReference, String> {
    let parent = parent
        .canonicalize()
        .map_err(|error| format!("could not resolve comparison directory: {error}"))?;
    let file = file
        .canonicalize()
        .map_err(|error| format!("could not resolve M4 artifact: {error}"))?;
    let relative = file
        .strip_prefix(parent)
        .map_err(|_| "M4 artifacts must be below the comparison directory")?;
    let path = relative.to_string_lossy().replace('\\', "/");
    autonomous_systems_vv_lab::validate_relative_reference(&path)
        .map_err(|error| error.to_string())?;
    Ok(ArtifactReference {
        path,
        sha256: digest.to_owned(),
    })
}

struct M4RunArguments {
    scenario_path: PathBuf,
    seed: u64,
    controller: ControllerPolicyV1,
    output_directory: PathBuf,
    mission_policy: MissionPolicy,
    max_output_bytes: Option<u64>,
    contracts_path: PathBuf,
    actuator_path: Option<PathBuf>,
}

fn parse_m4_run_arguments(args: &[String]) -> Result<M4RunArguments, String> {
    if args.is_empty() {
        return Err("run-m4 requires a scenario path".into());
    }
    let scenario_path = PathBuf::from(&args[0]);
    let mut seed = None;
    let mut controller = None;
    let mut output = None;
    let mut contracts = None;
    let mut actuator = None;
    let mut mission_policy = MissionPolicy::default();
    let mut max_output_bytes = None;
    let mut seen = BTreeSet::new();
    let mut index = 1;
    while index < args.len() {
        let flag = args[index].as_str();
        if !seen.insert(flag) {
            return Err(format!("{flag} may be specified only once"));
        }
        let value = args
            .get(index + 1)
            .ok_or_else(|| format!("missing value after {flag}"))?;
        match flag {
            "--seed" => seed = Some(parse_seed(value)?),
            "--controller" => {
                controller = Some(parse_controller_id(value).map_err(|error| error.to_string())?)
            }
            "--output" => output = Some(PathBuf::from(value)),
            "--contracts" => contracts = Some(PathBuf::from(value)),
            "--actuator" => actuator = Some(PathBuf::from(value)),
            "--stall-window-ticks" => mission_policy.stall_window_ticks = parse_u32(value, flag)?,
            "--min-progress-mm" => mission_policy.min_progress_mm = parse_u32(value, flag)?,
            "--max-output-bytes" => max_output_bytes = Some(parse_u64(value, flag)?),
            _ => return Err(format!("unknown run-m4 option: {flag}")),
        }
        index += 2;
    }
    mission_policy
        .validate()
        .map_err(|error| error.to_string())?;
    Ok(M4RunArguments {
        scenario_path,
        seed: seed.ok_or_else(|| "--seed is required".to_owned())?,
        controller: controller.ok_or_else(|| "--controller is required".to_owned())?,
        output_directory: output.ok_or_else(|| "--output is required".to_owned())?,
        contracts_path: contracts.ok_or_else(|| "--contracts is required".to_owned())?,
        actuator_path: actuator,
        mission_policy,
        max_output_bytes,
    })
}
