from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from process_limits import CampaignArtifactBudget, ProcessLimitError, run_bounded_process
from m3_campaign_model import (
    MAX_ARTIFACT_BYTES, MAX_CASES, MAX_SIMULATOR_RUNS, MAX_TIME_BUDGET_SECONDS,
    M3_ROOT, PROGRESS_OUTCOMES, ROOT, SAFETY_STATUSES, TEMPORAL_STATUSES,
    CampaignPlan, ExpectedOutcome, M3CampaignError, M3Classification, PlannedCase,
    _sha256, classify_outputs, load_m3_manifest, m3_fixture_checksums, parse_name_list,
    parse_seeds, plan_matrix, validate_m3_manifest,
)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M3CampaignError(f"cannot read {label}: {error}") from error
    if not isinstance(result, dict):
        raise M3CampaignError(f"{label} must be a JSON object")
    return result


def _unique_campaign_dir(base: Path) -> Path:
    root = base.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for suffix in range(10_000):
        name = f"campaign-m3-{timestamp}" if suffix == 0 else f"campaign-m3-{timestamp}-{suffix}"
        destination = root / name
        try:
            destination.mkdir()
            return destination
        except FileExistsError:
            continue
    raise M3CampaignError("cannot choose a unique M3 campaign output directory")


def _portable_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _remaining_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise ProcessLimitError("M3 campaign exceeded its global time budget")
    return min(30.0, remaining)


def _counted_process(
    command: list[str],
    *,
    deadline: float,
    operation: str,
    command_counts: dict[str, dict[str, int]],
) -> Any:
    command_counts[operation]["attempted"] += 1
    result = run_bounded_process(
        command,
        cwd=ROOT,
        timeout_seconds=_remaining_time(deadline),
        max_output_bytes=64 * 1024,
        description=f"M3 {operation}",
    )
    command_counts[operation]["completed"] += 1
    return result


def _read_run_artifacts(output_dir: Path, max_output_bytes: int) -> tuple[dict[str, bytes], dict[str, Any]]:
    names = ("events.json", "report.json", "mission.json", "verification.json")
    artifacts: dict[str, bytes] = {}
    for name in names:
        try:
            artifacts[name] = (output_dir / name).read_bytes()
        except OSError as error:
            raise M3CampaignError(f"run did not produce {name}: {error}") from error
    if sum(map(len, artifacts.values())) > max_output_bytes:
        raise M3CampaignError("run artifacts exceed the requested output limit")
    try:
        parsed = {
            name.removesuffix(".json"): json.loads(contents)
            for name, contents in artifacts.items()
        }
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M3CampaignError(f"run produced invalid JSON artifacts: {error}") from error
    if any(not isinstance(value, dict) for value in parsed.values()):
        raise M3CampaignError("run artifacts must contain JSON objects")
    return artifacts, parsed


def _check_artifact_consistency(parsed: dict[str, dict[str, Any]]) -> None:
    artifact = parsed["events"]
    report = parsed["report"]
    verification = parsed["verification"]
    events = artifact.get("events")
    if not isinstance(events, list) or artifact.get("event_count") != len(events):
        raise M3CampaignError("events.json has an inconsistent event count")
    if artifact.get("expected_report") != report:
        raise M3CampaignError("events.json expected_report differs from report.json")
    if artifact.get("final_hash") != report.get("final_hash"):
        raise M3CampaignError("events.json final hash differs from report.json")
    source_hash = verification.get("source_artifact_sha256")
    if source_hash != artifact.get("artifact_sha256"):
        raise M3CampaignError("verification.json references a different source artifact")


def _check_counterexample_reference(
    reference: dict[str, str] | None, repository_root: Path = ROOT
) -> tuple[dict[str, str] | None, bool]:
    if reference is None:
        return None, False
    resolved_paths: dict[str, str] = {}
    all_exist = True
    for kind, relative in reference.items():
        path = (repository_root / relative).resolve()
        try:
            path.relative_to(repository_root.resolve())
        except ValueError as error:
            raise M3CampaignError("minimized counterexample reference escapes the repository") from error
        all_exist = all_exist and path.is_file()
        resolved_paths[kind] = path.relative_to(repository_root.resolve()).as_posix()
    return (resolved_paths if all_exist else None), all_exist


def _execute_case(
    *,
    binary: Path,
    manifest_root: Path,
    case: PlannedCase,
    case_dir: Path,
    artifact_budget: CampaignArtifactBudget,
    deadline: float,
    command_counts: dict[str, dict[str, int]],
) -> dict[str, Any]:
    file_inputs = {
        "scenario": case.scenario_path,
        "properties": case.properties_path,
        "actuator_config": case.actuator_config_path,
    }
    resolved_inputs: dict[str, Path] = {}
    input_hashes: dict[str, str] = {}
    for label, relative in file_inputs.items():
        path = (manifest_root / relative).resolve()
        try:
            path.relative_to(manifest_root.resolve())
        except ValueError as error:
            raise M3CampaignError(f"{label} input escapes the M3 manifest directory") from error
        if not path.is_file():
            raise M3CampaignError(f"M3 {label} file does not exist: {relative}")
        resolved_inputs[label] = path
        input_hashes[f"{label}_sha256"] = _sha256(path.read_bytes())

    case_dir.mkdir(parents=True, exist_ok=False)
    first_dir = case_dir / "run"
    repeat_dir = case_dir / "repeat"
    first_dir.mkdir()
    repeat_dir.mkdir()
    outputs: list[dict[str, Any]] = []
    artifact_sets: list[dict[str, bytes]] = []
    for label, output_dir in (("run", first_dir), ("repeat", repeat_dir)):
        remaining_bytes = artifact_budget.remaining(case_dir.parent)
        run_output_limit = min(16 * 1024 * 1024, remaining_bytes // 2)
        if run_output_limit < 1:
            raise M3CampaignError("M3 campaign artifact budget is exhausted")
        command = [
            str(binary),
            "run",
            str(resolved_inputs["scenario"]),
            "--seed",
            str(case.seed),
            "--output",
            str(output_dir),
            "--contracts",
            str(resolved_inputs["properties"]),
            "--actuator",
            str(resolved_inputs["actuator_config"]),
            "--max-output-bytes",
            str(run_output_limit),
        ]
        run = _counted_process(
            command,
            deadline=deadline,
            operation="run",
            command_counts=command_counts,
        )
        artifacts, parsed = _read_run_artifacts(output_dir, run_output_limit)
        _check_artifact_consistency(parsed)
        expected_exit = 0 if parsed["report"].get("status") == "passed" else 2
        if run.returncode != expected_exit:
            raise M3CampaignError(
                f"{label} returned {run.returncode}, inconsistent with safety status"
            )
        artifact_sets.append(artifacts)
        outputs.append(parsed)
        artifact_budget.refresh(case_dir.parent)

    repeated = artifact_sets[0] == artifact_sets[1]
    if not repeated:
        raise M3CampaignError("deterministic repeat differs byte-for-byte from the first M3 run")

    replay_started = time.monotonic()
    replay = _counted_process(
        [str(binary), "replay", str(first_dir / "events.json")],
        deadline=deadline,
        operation="replay",
        command_counts=command_counts,
    )
    replay_elapsed_seconds = round(time.monotonic() - replay_started, 4)
    if replay.returncode != 0:
        raise M3CampaignError(f"replay returned {replay.returncode}")

    classification = classify_outputs(
        case.expected,
        outputs[0]["report"],
        outputs[0]["mission"],
        outputs[0]["verification"],
    )
    errors = list(classification.errors)
    reference, reference_available = _check_counterexample_reference(
        case.minimized_counterexample
    )
    if case.minimized_counterexample and reference_available:
        counterexample_reference = reference
    else:
        counterexample_reference = None

    first_artifacts = artifact_sets[0]
    temporal_failures = [
        result
        for result in outputs[0]["verification"].get("contract_results", [])
        if isinstance(result, dict) and result.get("outcome") == "FAIL"
    ]
    return {
        "suite": "m3",
        "case_id": case.case_id,
        "scenario": case.scenario_path,
        "contract_set": case.contract_set,
        "fault_combination": case.fault_combination,
        "seed": case.seed,
        "expected": {
            "temporal": case.expected.temporal,
            "safety": case.expected.safety,
            "progress": case.expected.progress,
            "contracts": case.expected.contracts,
        },
        "actual": {
            "temporal": classification.temporal,
            "safety": classification.safety,
            "progress": classification.progress,
            "contracts": classification.contracts,
        },
        "result": "passed" if not errors else "failed",
        "errors": errors,
        "deterministic": repeated,
        "replay_exit_code": replay.returncode,
        "replay_elapsed_seconds": replay_elapsed_seconds,
        "temporal_failures": temporal_failures,
        "temporal_failure_count": len(temporal_failures),
        "minimized_counterexample": counterexample_reference,
        "minimized_counterexample_available": reference_available,
        "output_paths": {
            "events": _portable_path(first_dir / "events.json", ROOT),
            "report": _portable_path(first_dir / "report.json", ROOT),
            "mission": _portable_path(first_dir / "mission.json", ROOT),
            "verification": _portable_path(first_dir / "verification.json", ROOT),
        },
        "sha256": {
            **input_hashes,
            **{
                name.removesuffix(".json") + "_sha256": _sha256(contents)
                for name, contents in first_artifacts.items()
            },
        },
    }


def _campaign_summary(
    *,
    cases: list[dict[str, Any]],
    plan: CampaignPlan,
    campaign_dir: Path,
    started: float,
    command_counts: dict[str, dict[str, int]],
    fixture_checksums: dict[str, str],
    seeds: tuple[int, ...],
    manifest_path: Path,
) -> dict[str, Any]:
    temporal_counts = {outcome: 0 for outcome in sorted(TEMPORAL_STATUSES)}
    safety_counts = {outcome: 0 for outcome in sorted(SAFETY_STATUSES)}
    progress_counts = {outcome: 0 for outcome in sorted(PROGRESS_OUTCOMES)}
    contracts: dict[str, dict[str, int]] = {}
    for case in cases:
        actual = case.get("actual", {})
        if actual.get("temporal") in temporal_counts:
            temporal_counts[actual["temporal"]] += 1
        if actual.get("safety") in safety_counts:
            safety_counts[actual["safety"]] += 1
        if actual.get("progress") in progress_counts:
            progress_counts[actual["progress"]] += 1
        for contract_id, outcome in actual.get("contracts", {}).items():
            counts = contracts.setdefault(
                contract_id,
                {status: 0 for status in (*sorted(TEMPORAL_STATUSES), "expected_failures", "unexpected_failures")},
            )
            counts[outcome] += 1
            expected = case.get("expected", {}).get("contracts", {}).get(contract_id)
            if outcome == "FAIL":
                counts["expected_failures" if expected == "FAIL" else "unexpected_failures"] += 1

    failed = sum(case.get("result") != "passed" for case in cases)
    return {
        "schema_version": 1,
        "suite": "m3",
        "status": "passed" if failed == 0 and len(cases) == len(plan.cases) else "failed",
        "case_count": len(cases),
        "planned_case_count": len(plan.cases),
        "passed_cases": len(cases) - failed,
        "failed_cases": failed,
        "seeds": list(seeds),
        "manifest_path": _portable_path(manifest_path, ROOT),
        "campaign_directory": _portable_path(campaign_dir, ROOT),
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "budgets": {
            "max_cases": plan.max_cases,
            "max_runs": plan.max_runs,
            "max_artifact_bytes": plan.max_artifact_bytes,
            "time_budget_seconds": plan.time_budget_seconds,
        },
        "execution_counts": {
            "simulator_invocations": sum(item["attempted"] for item in command_counts.values()),
            "run": command_counts["run"],
            "replay": command_counts["replay"],
        },
        "deterministic_repeats": {
            "checked": sum("deterministic" in case for case in cases),
            "passed": sum(case.get("deterministic") is True for case in cases),
        },
        "replays": {
            "checked": sum("replay_exit_code" in case for case in cases),
            "passed": sum(case.get("replay_exit_code") == 0 for case in cases),
        },
        "replay_elapsed_seconds": round(
            sum(case.get("replay_elapsed_seconds", 0.0) for case in cases), 4
        ),
        "temporal_outcome_counts": temporal_counts,
        "safety_outcome_counts": safety_counts,
        "progress_outcome_counts": progress_counts,
        "contract_outcome_counts": contracts,
        "temporal_failure_counts": {
            contract_id: counts["FAIL"] for contract_id, counts in contracts.items() if counts["FAIL"]
        },
        "cases": cases,
        "fixture_checksums_sha256": fixture_checksums,
    }


def _write_campaign_outputs(
    campaign_dir: Path, summary: dict[str, Any], max_artifact_bytes: int
) -> None:
    fingerprints = {
        "schema_version": 1,
        "suite": "m3",
        "suites": ["m3"],
        "m3_scenarios": sorted({case["case_id"] for case in summary["cases"]}),
        "m3_contract_sets": sorted({case["contract_set"] for case in summary["cases"]}),
        "m3_fault_combinations": sorted({case["fault_combination"] for case in summary["cases"]}),
        "fixture_checksums_sha256": summary["fixture_checksums_sha256"],
        "outputs": [
            {
                "suite": "m3",
                "scenario": case["case_id"],
                "variant": f"{case['contract_set']}+{case['fault_combination']}",
                "contract_set": case["contract_set"],
                "fault_combination": case["fault_combination"],
                "seed": case["seed"],
                **case["sha256"],
            }
            for case in summary["cases"]
            if "sha256" in case
        ],
    }
    report = [
        "# Resumo da campanha M3",
        "",
        f"Estado: **{summary['status']}**.",
        f"Casos: {summary['passed_cases']} aprovados e {summary['failed_cases']} divergentes, de {summary['planned_case_count']} planeados.",
        f"Passagens do monitor temporal: {summary['temporal_outcome_counts']}.",
        f"Resultados de segurança: {summary['safety_outcome_counts']}.",
        f"Resultados de progresso: {summary['progress_outcome_counts']}.",
        f"Execuções: {summary['execution_counts']['simulator_invocations']} chamadas, incluindo repetição determinística e reprodução.",
        "",
        "Os resultados por caso estão em `summary.json`; os hashes comparáveis estão em `fingerprints.json`.",
        "",
    ]
    files = {
        "summary.json": json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        "campaign-report.md": "\n".join(report).encode("utf-8"),
        "fingerprints.json": json.dumps(fingerprints, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    }
    for name, contents in files.items():
        (campaign_dir / name).write_bytes(contents)
    total = sum(path.stat().st_size for path in campaign_dir.rglob("*") if path.is_file())
    if total > max_artifact_bytes:
        raise M3CampaignError(
            f"M3 campaign artifacts used {total} bytes, above {max_artifact_bytes} bytes"
        )


def run_campaign(args: Any) -> int:
    """Execute the M3 case/seed matrix with bounded runs, artifacts and time."""
    started = time.monotonic()
    manifest_path = Path(getattr(args, "m3_manifest", None) or M3_ROOT / "expectations.json")
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest_path = manifest_path.resolve()
    manifest = load_m3_manifest(manifest_path)
    plan = plan_matrix(
        manifest,
        contract_sets=getattr(args, "m3_contract_sets", None),
        scenario_names=getattr(args, "m3_scenarios", None),
        fault_combinations=getattr(args, "m3_fault_combinations", None),
        seeds=tuple(args.seeds) if getattr(args, "seeds", None) is not None else None,
        max_cases=min(args.max_cases, MAX_CASES),
        max_runs=min(args.max_runs, MAX_SIMULATOR_RUNS),
        max_artifact_bytes=min(args.max_artifact_bytes, MAX_ARTIFACT_BYTES),
        time_budget_seconds=args.time_budget_seconds,
    )
    binary = Path(args.binary)
    if not binary.is_absolute():
        binary = ROOT / binary
    binary = binary.resolve()
    if not binary.is_file():
        raise M3CampaignError(f"compiled vv-lab binary not found: {binary.name}")

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    campaign_dir = _unique_campaign_dir(output_root)
    summary_reserve = min(
        plan.max_artifact_bytes // 4,
        max(65_536, len(plan.cases) * 8192),
    )
    case_artifact_limit = plan.max_artifact_bytes - summary_reserve
    if case_artifact_limit < 1:
        raise M3CampaignError("artifact limit leaves no room for M3 run outputs")
    artifact_budget = CampaignArtifactBudget(campaign_dir, case_artifact_limit)
    command_counts = {name: {"attempted": 0, "completed": 0} for name in ("run", "replay")}
    fixture_checksums = m3_fixture_checksums(manifest, manifest_path)
    deadline = started + plan.time_budget_seconds
    cases: list[dict[str, Any]] = []
    for selected in plan.cases:
        case_started = time.monotonic()
        case_dir = campaign_dir / selected.case_id / f"seed-{selected.seed}"
        try:
            result = _execute_case(
                binary=binary,
                manifest_root=manifest_path.parent,
                case=selected,
                case_dir=case_dir,
                artifact_budget=artifact_budget,
                deadline=deadline,
                command_counts=command_counts,
            )
        except (M3CampaignError, ProcessLimitError, OSError) as error:
            result = {
                "suite": "m3",
                "case_id": selected.case_id,
                "scenario": selected.scenario_path,
                "contract_set": selected.contract_set,
                "fault_combination": selected.fault_combination,
                "seed": selected.seed,
                "expected": {
                    "temporal": selected.expected.temporal,
                    "safety": selected.expected.safety,
                    "progress": selected.expected.progress,
                    "contracts": selected.expected.contracts,
                },
                "result": "failed",
                "errors": [str(error)],
                "elapsed_seconds": round(time.monotonic() - case_started, 4),
            }
            if case_dir.exists():
                artifact_budget.refresh(case_dir.parent)
        result["elapsed_seconds"] = round(time.monotonic() - case_started, 4)
        cases.append(result)
        if time.monotonic() >= deadline:
            break

    summary = _campaign_summary(
        cases=cases,
        plan=plan,
        campaign_dir=campaign_dir,
        started=started,
        command_counts=command_counts,
        fixture_checksums=fixture_checksums,
        seeds=tuple(args.seeds) if getattr(args, "seeds", None) is not None else tuple(manifest["default_seeds"]),
        manifest_path=manifest_path,
    )
    _write_campaign_outputs(campaign_dir, summary, plan.max_artifact_bytes)
    print(
        f"Campanha M3 {summary['status']}: {summary['passed_cases']}/{summary['planned_case_count']} casos, "
        f"{summary['execution_counts']['simulator_invocations']} chamadas."
    )
    return 0 if summary["status"] == "passed" else 1
