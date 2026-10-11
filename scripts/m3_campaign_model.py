from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
M3_ROOT = ROOT / "scenarios" / "m3"
DEFAULT_SEEDS = (42, 1337, 2026)
TEMPORAL_STATUSES = frozenset({"PASS", "FAIL", "INCONCLUSIVE"})
SAFETY_STATUSES = frozenset({"passed", "invariant_failed"})
PROGRESS_OUTCOMES = frozenset({"completed", "incomplete", "stalled", "invalid_terminated"})
MAX_SEEDS = 32
MAX_CASES = 80
MAX_SIMULATOR_RUNS = 256
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TIME_BUDGET_SECONDS = 120
PROCESS_INVOCATIONS_PER_CASE = 3

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
_CONTRACT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_SEED_TEXT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_ROOT_FIELDS = {
    "schema_version",
    "default_seeds",
    "contract_sets",
    "fault_combinations",
    "cases",
    "budgets",
}
_CASE_FIELDS = {
    "id",
    "scenario",
    "contract_set",
    "fault_combination",
    "expected_by_seed",
    "minimized_counterexample",
}
_EXPECTATION_FIELDS = {"temporal", "safety", "progress", "contracts"}
_BUDGET_FIELDS = {
    "max_cases",
    "max_runs",
    "max_artifact_bytes",
    "time_budget_seconds",
}


class M3CampaignError(ValueError):
    """Invalid M3 campaign configuration or resource plan."""


@dataclass(frozen=True)
class ExpectedOutcome:
    temporal: str
    safety: str
    progress: str
    contracts: dict[str, str]


@dataclass(frozen=True)
class PlannedCase:
    case_id: str
    scenario_path: str
    contract_set: str
    properties_path: str
    fault_combination: str
    actuator_config_path: str
    seed: int
    expected: ExpectedOutcome
    minimized_counterexample: dict[str, str] | None


@dataclass(frozen=True)
class CampaignPlan:
    cases: tuple[PlannedCase, ...]
    simulator_invocations: int
    max_cases: int
    max_runs: int
    max_artifact_bytes: int
    time_budget_seconds: float


@dataclass(frozen=True)
class M3Classification:
    temporal: str
    safety: str
    progress: str
    contracts: dict[str, str]
    errors: tuple[str, ...]


def _is_plain_int(value: Any) -> bool:
    return type(value) is int


def _require_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if not _is_plain_int(value) or not minimum <= value <= maximum:
        raise M3CampaignError(f"{label} must be an integer from {minimum} through {maximum}")
    return value


def _require_identifier(value: Any, label: str, *, contract: bool = False) -> str:
    pattern = _CONTRACT_ID if contract else _IDENTIFIER
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise M3CampaignError(f"{label} is missing or invalid")
    return value


def _require_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise M3CampaignError(f"{label} must be a non-empty relative path")
    if "\\" in value:
        raise M3CampaignError(f"{label} must use portable forward-slash separators")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    parts = value.replace("\\", "/").split("/")
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise M3CampaignError(f"{label} must stay inside the M3 campaign directory")
    return value


def _validate_seeds(value: Any, label: str) -> list[int]:
    if not isinstance(value, list) or not value or len(value) > MAX_SEEDS:
        raise M3CampaignError(f"{label} must contain 1 through {MAX_SEEDS} seeds")
    result = []
    for seed in value:
        result.append(_require_int(seed, label, 0, 2**64 - 1))
    if len(set(result)) != len(result):
        raise M3CampaignError(f"{label} must not contain duplicate seeds")
    return result


def _validate_named_paths(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise M3CampaignError(f"{label} must be a non-empty object")
    return {
        _require_identifier(name, f"{label} name"): _require_relative_path(path, f"{label} path")
        for name, path in value.items()
    }


def _validate_outcome(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _EXPECTATION_FIELDS:
        raise M3CampaignError(f"{label} must define temporal, safety, progress and contracts")
    temporal = value["temporal"]
    safety = value["safety"]
    progress = value["progress"]
    contracts = value["contracts"]
    if not isinstance(temporal, str) or temporal not in TEMPORAL_STATUSES:
        raise M3CampaignError(f"{label} has an unknown temporal outcome")
    if not isinstance(safety, str) or safety not in SAFETY_STATUSES:
        raise M3CampaignError(f"{label} has an unknown safety outcome")
    if not isinstance(progress, str) or progress not in PROGRESS_OUTCOMES:
        raise M3CampaignError(f"{label} has an unknown progress outcome")
    if not isinstance(contracts, dict) or not contracts:
        raise M3CampaignError(f"{label} must list expected outcomes for its contracts")
    checked_contracts: dict[str, str] = {}
    for contract_id, status in contracts.items():
        checked_id = _require_identifier(contract_id, f"{label} contract id", contract=True)
        if not isinstance(status, str) or status not in TEMPORAL_STATUSES:
            raise M3CampaignError(f"{label} has an unknown result for contract {checked_id}")
        checked_contracts[checked_id] = status
    contract_statuses = set(checked_contracts.values())
    aggregate = (
        "FAIL"
        if "FAIL" in contract_statuses
        else "INCONCLUSIVE"
        if "INCONCLUSIVE" in contract_statuses
        else "PASS"
    )
    if temporal != aggregate:
        raise M3CampaignError(f"{label} temporal summary disagrees with contract outcomes")
    return {
        "temporal": temporal,
        "safety": safety,
        "progress": progress,
        "contracts": checked_contracts,
    }


def _validate_counterexample(value: Any, label: str) -> dict[str, str] | None:
    if value is None:
        return None
    fields = {"original", "reduced", "summary"}
    if not isinstance(value, dict) or set(value) != fields:
        raise M3CampaignError(f"{label} must identify original, reduced and summary artifacts")
    return {
        key: _require_relative_path(value[key], f"{label}.{key}")
        for key in ("original", "reduced", "summary")
    }


def _validate_budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != _BUDGET_FIELDS:
        raise M3CampaignError("budgets must define max_cases, max_runs, max_artifact_bytes and time_budget_seconds")
    return {
        "max_cases": _require_int(value["max_cases"], "max_cases", 1, MAX_CASES),
        "max_runs": _require_int(value["max_runs"], "max_runs", 1, MAX_SIMULATOR_RUNS),
        "max_artifact_bytes": _require_int(
            value["max_artifact_bytes"], "max_artifact_bytes", 65_536, MAX_ARTIFACT_BYTES
        ),
        "time_budget_seconds": _require_int(
            value["time_budget_seconds"], "time_budget_seconds", 1, MAX_TIME_BUDGET_SECONDS
        ),
    }


def validate_m3_manifest(value: Any) -> dict[str, Any]:
    """Validate manifest shape and expectations without reading scenario files."""
    if not isinstance(value, dict) or set(value) != _ROOT_FIELDS:
        raise M3CampaignError("M3 manifest has missing or unknown fields")
    if value["schema_version"] != 1 or type(value["schema_version"]) is not int:
        raise M3CampaignError("unsupported M3 manifest schema version")
    seeds = _validate_seeds(value["default_seeds"], "default_seeds")
    contract_sets = _validate_named_paths(value["contract_sets"], "contract_sets")
    fault_combinations = _validate_named_paths(value["fault_combinations"], "fault_combinations")
    raw_cases = value["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise M3CampaignError("M3 manifest must contain at least one case")

    case_ids: set[str] = set()
    cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(raw_cases):
        label = f"cases[{index}]"
        if not isinstance(raw_case, dict) or set(raw_case) - _CASE_FIELDS or not {
            "id",
            "scenario",
            "contract_set",
            "fault_combination",
            "expected_by_seed",
        } <= set(raw_case):
            raise M3CampaignError(f"{label} has missing or unknown fields")
        case_id = _require_identifier(raw_case["id"], f"{label}.id")
        if case_id in case_ids:
            raise M3CampaignError(f"duplicate M3 case id: {case_id}")
        case_ids.add(case_id)
        scenario_path = _require_relative_path(raw_case["scenario"], f"{label}.scenario")
        contract_set = _require_identifier(raw_case["contract_set"], f"{label}.contract_set")
        fault_combination = _require_identifier(
            raw_case["fault_combination"], f"{label}.fault_combination"
        )
        if contract_set not in contract_sets:
            raise M3CampaignError(f"{label} references an unknown contract set")
        if fault_combination not in fault_combinations:
            raise M3CampaignError(f"{label} references an unknown fault combination")

        raw_expected = raw_case["expected_by_seed"]
        if not isinstance(raw_expected, dict) or not raw_expected:
            raise M3CampaignError(f"{label}.expected_by_seed must be a non-empty object")
        expected_by_seed: dict[str, ExpectedOutcome] = {}
        contract_ids: set[str] | None = None
        for seed_text, outcome in raw_expected.items():
            if not isinstance(seed_text, str) or not _SEED_TEXT.fullmatch(seed_text):
                raise M3CampaignError(f"{label} contains a malformed expected seed")
            seed = int(seed_text)
            if seed > 2**64 - 1:
                raise M3CampaignError(f"{label} expected seed exceeds u64")
            checked_outcome = _validate_outcome(outcome, f"{label}, seed {seed}")
            current_contract_ids = set(checked_outcome["contracts"])
            if contract_ids is None:
                contract_ids = current_contract_ids
            elif contract_ids != current_contract_ids:
                raise M3CampaignError(f"{label} contract outcomes list differs between seeds")
            expected_by_seed[seed_text] = checked_outcome
        if not set(map(str, seeds)) <= set(expected_by_seed):
            raise M3CampaignError(f"{label} is missing an expected outcome for a default seed")
        cases.append(
            {
                "id": case_id,
                "scenario": scenario_path,
                "contract_set": contract_set,
                "fault_combination": fault_combination,
                "expected_by_seed": expected_by_seed,
                "minimized_counterexample": _validate_counterexample(
                    raw_case.get("minimized_counterexample"), f"{label}.minimized_counterexample"
                ),
            }
        )
    budgets = _validate_budgets(value["budgets"])
    return {
        "schema_version": 1,
        "default_seeds": seeds,
        "contract_sets": contract_sets,
        "fault_combinations": fault_combinations,
        "cases": cases,
        "budgets": budgets,
    }


def load_m3_manifest(path: Path | None = None) -> dict[str, Any]:
    """Load and validate a standalone M3 campaign manifest."""
    manifest_path = path or M3_ROOT / "expectations.json"
    try:
        value = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise M3CampaignError(f"cannot read M3 campaign manifest: {error}") from error
    return validate_m3_manifest(value)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M3CampaignError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_seeds(value: str) -> tuple[int, ...]:
    """Parse a bounded, unique comma-separated list of unsigned 64-bit seeds."""
    try:
        seeds = tuple(int(part.strip(), 10) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from error
    if not seeds or len(seeds) > MAX_SEEDS or any(seed < 0 or seed > 2**64 - 1 for seed in seeds):
        raise argparse.ArgumentTypeError(f"seeds must contain 1 through {MAX_SEEDS} u64 values")
    if len(set(seeds)) != len(seeds):
        raise argparse.ArgumentTypeError("seeds must not contain duplicates")
    return seeds


def _selection(value: tuple[str, ...] | None, available: set[str], label: str) -> set[str]:
    if value is None:
        return set(available)
    if not value or len(set(value)) != len(value):
        raise M3CampaignError(f"{label} selection must be non-empty and contain no duplicates")
    missing = set(value) - available
    if missing:
        raise M3CampaignError(f"unknown {label}: {', '.join(sorted(missing))}")
    return set(value)


def _selected_seeds(value: tuple[int, ...] | None, defaults: list[int]) -> tuple[int, ...]:
    seeds = tuple(defaults) if value is None else value
    if (
        not seeds
        or len(seeds) > MAX_SEEDS
        or len(set(seeds)) != len(seeds)
        or any(not _is_plain_int(seed) or seed < 0 or seed > 2**64 - 1 for seed in seeds)
    ):
        raise M3CampaignError(f"seeds must contain 1 through {MAX_SEEDS} unique u64 values")
    return seeds


def plan_matrix(
    manifest: dict[str, Any],
    *,
    contract_sets: tuple[str, ...] | None = None,
    scenario_names: tuple[str, ...] | None = None,
    fault_combinations: tuple[str, ...] | None = None,
    seeds: tuple[int, ...] | None = None,
    max_cases: int | None = None,
    max_runs: int | None = None,
    max_artifact_bytes: int | None = None,
    time_budget_seconds: float | None = None,
) -> CampaignPlan:
    """Expand selected manifest cases and seeds before any process is started."""
    checked = validate_m3_manifest(manifest)
    selected_contract_sets = _selection(
        contract_sets, set(checked["contract_sets"]), "contract set"
    )
    selected_scenarios = _selection(
        scenario_names, {case["id"] for case in checked["cases"]}, "scenario"
    )
    selected_faults = _selection(
        fault_combinations, set(checked["fault_combinations"]), "fault combination"
    )
    selected_seeds = _selected_seeds(seeds, checked["default_seeds"])
    budgets = checked["budgets"]
    effective_cases = budgets["max_cases"] if max_cases is None else _require_int(
        max_cases, "max_cases", 1, MAX_CASES
    )
    effective_runs = budgets["max_runs"] if max_runs is None else _require_int(
        max_runs, "max_runs", 1, MAX_SIMULATOR_RUNS
    )
    effective_artifacts = budgets["max_artifact_bytes"] if max_artifact_bytes is None else _require_int(
        max_artifact_bytes, "max_artifact_bytes", 65_536, MAX_ARTIFACT_BYTES
    )
    if time_budget_seconds is None:
        effective_time = float(budgets["time_budget_seconds"])
    elif (
        isinstance(time_budget_seconds, bool)
        or not isinstance(time_budget_seconds, (int, float))
        or not math.isfinite(time_budget_seconds)
        or time_budget_seconds <= 0
    ):
        raise M3CampaignError("time_budget_seconds must be finite and greater than zero")
    else:
        effective_time = min(float(time_budget_seconds), float(MAX_TIME_BUDGET_SECONDS))
    effective_cases = min(effective_cases, budgets["max_cases"])
    effective_runs = min(effective_runs, budgets["max_runs"])
    effective_artifacts = min(effective_artifacts, budgets["max_artifact_bytes"])
    effective_time = min(effective_time, float(budgets["time_budget_seconds"]))

    cases: list[PlannedCase] = []
    for entry in checked["cases"]:
        if (
            entry["id"] not in selected_scenarios
            or entry["contract_set"] not in selected_contract_sets
            or entry["fault_combination"] not in selected_faults
        ):
            continue
        for seed in selected_seeds:
            outcome = entry["expected_by_seed"].get(str(seed))
            if outcome is None:
                raise M3CampaignError(
                    f"no expected result for {entry['id']} and seed {seed}"
                )
            cases.append(
                PlannedCase(
                    case_id=entry["id"],
                    scenario_path=entry["scenario"],
                    contract_set=entry["contract_set"],
                    properties_path=checked["contract_sets"][entry["contract_set"]],
                    fault_combination=entry["fault_combination"],
                    actuator_config_path=checked["fault_combinations"][entry["fault_combination"]],
                    seed=seed,
                    expected=ExpectedOutcome(**outcome),
                    minimized_counterexample=entry["minimized_counterexample"],
                )
            )
    if not cases:
        raise M3CampaignError("selected M3 campaign matrix contains no cases")
    invocation_count = len(cases) * PROCESS_INVOCATIONS_PER_CASE
    if len(cases) > effective_cases:
        raise M3CampaignError(
            f"planned matrix has {len(cases)} cases, above max_cases {effective_cases}"
        )
    if invocation_count > effective_runs:
        raise M3CampaignError(
            f"planned matrix needs {invocation_count} simulator invocations, above max_runs {effective_runs}"
        )
    return CampaignPlan(
        cases=tuple(cases),
        simulator_invocations=invocation_count,
        max_cases=effective_cases,
        max_runs=effective_runs,
        max_artifact_bytes=effective_artifacts,
        time_budget_seconds=effective_time,
    )


def classify_outputs(
    expected: ExpectedOutcome,
    report: dict[str, Any],
    mission: dict[str, Any],
    verification: dict[str, Any],
) -> M3Classification:
    """Classify Rust output without conflating temporal, safety or progress results."""
    if not isinstance(report, dict) or not isinstance(mission, dict) or not isinstance(
        verification, dict
    ):
        raise M3CampaignError("run outputs must be JSON objects")

    raw_results = verification.get("contract_results")
    if not isinstance(raw_results, list) or not raw_results:
        raise M3CampaignError("verification.json has no contract_results")
    contract_results: dict[str, str] = {}
    for index, result in enumerate(raw_results):
        if not isinstance(result, dict):
            raise M3CampaignError(f"contract_results[{index}] must be an object")
        contract_id = _require_identifier(
            result.get("contract_id"), f"contract_results[{index}].contract_id", contract=True
        )
        outcome = result.get("outcome")
        if not isinstance(outcome, str) or outcome not in TEMPORAL_STATUSES:
            raise M3CampaignError(f"contract_results[{index}] has an unknown outcome")
        if contract_id in contract_results:
            raise M3CampaignError(f"verification.json repeats contract {contract_id}")
        contract_results[contract_id] = outcome

    temporal = (
        "FAIL"
        if "FAIL" in contract_results.values()
        else "INCONCLUSIVE"
        if "INCONCLUSIVE" in contract_results.values()
        else "PASS"
    )
    safety = report.get("status")
    progress = mission.get("outcome")
    if not isinstance(safety, str) or safety not in SAFETY_STATUSES:
        raise M3CampaignError("report.json has an unknown safety status")
    if not isinstance(progress, str) or progress not in PROGRESS_OUTCOMES:
        raise M3CampaignError("mission.json has an unknown progress outcome")

    errors: list[str] = []
    if temporal != expected.temporal:
        errors.append(f"temporal outcome expected {expected.temporal}, received {temporal}")
    if safety != expected.safety:
        errors.append(f"safety outcome expected {expected.safety}, received {safety}")
    if progress != expected.progress:
        errors.append(f"progress outcome expected {expected.progress}, received {progress}")
    if contract_results != expected.contracts:
        errors.append("per-contract outcomes differ from expectations")
    return M3Classification(
        temporal=temporal,
        safety=safety,
        progress=progress,
        contracts=contract_results,
        errors=tuple(errors),
    )


def m3_fixture_checksums(
    manifest: dict[str, Any], manifest_path: Path | None = None
) -> dict[str, str]:
    """Hash every scenario, contract set, actuator config and manifest input."""
    checked = validate_m3_manifest(manifest)
    source = (manifest_path or M3_ROOT / "expectations.json").resolve()
    base = source.parent.resolve()
    paths = {
        source.name,
        *[case["scenario"] for case in checked["cases"]],
        *checked["contract_sets"].values(),
        *checked["fault_combinations"].values(),
    }
    checksums: dict[str, str] = {}
    for relative in sorted(paths):
        path = (base / relative).resolve()
        try:
            path.relative_to(base)
        except ValueError as error:
            raise M3CampaignError(f"M3 fixture escapes its manifest directory: {relative}") from error
        try:
            contents = path.read_bytes()
        except OSError as error:
            raise M3CampaignError(f"cannot read M3 fixture {relative}: {error}") from error
        checksums[f"m3/{relative}"] = hashlib.sha256(contents).hexdigest()
    return checksums


def parse_name_list(value: str) -> tuple[str, ...]:
    names = tuple(part.strip() for part in value.split(","))
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise argparse.ArgumentTypeError("names must be comma-separated, non-empty and unique")
    return names


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()
