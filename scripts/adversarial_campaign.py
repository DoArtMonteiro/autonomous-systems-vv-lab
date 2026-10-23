"""Drive the `vv-adversary` engine over a bounded case matrix and summarise it.

Matrix (constant `CASES`, every case is run for every campaign seed):

* `clean-nominal`: CLEAN base `scenarios/m3/nominal-stop.json`. This is the
  search target. The unmodified control must have zero violations.
* `known-faulty-delayed-after-fallback`: BOUNDARY control. The base
  `delayed-after-fallback.json` with `actuator-delayed.json` is recorded in
  `scenarios/m3/expectations.json` as FAIL. The control must show a violation.
* `m4-x-first-overshoot`: M4 base for policy divergence, no control expectation.

Per (case, seed) the script runs `vv-adversary campaign` twice (`first/`,
`repeat/`), compares the sha256 of every file in both trees, runs
`vv-adversary replay first/campaign.json`, and `vv-lab replay-m4` on every
`cases/*/{original,minimized}/m4.json`. Wall time is measured with
`time.perf_counter` around each subprocess, outside the simulation, and only
appears in the `timing` block of `summary.json` and in `summary.md`.

`campaign.json` (schema `vv-adversary.campaign.v1`) is untrusted: `aggregate_campaign`
reads it with a size cap and typed checks and records `problems` instead of raising.
A pair fails on any problem, any recheck `disagree`, `metrics.unidentified_violations`
above zero, or a failed control expectation (fail-closed when the count is missing).
`metrics.{novel,inherited}_classes_found` must add up to `unique_classes_found`.

Exit status: 0 all checks passed, 1 a check failed or the run aborted,
2 usage or plan error (nothing was started).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from process_limits import CampaignArtifactBudget, ProcessLimitError, run_bounded_process
from run_campaign import parse_seeds

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (42, 1337, 2026)
CAMPAIGN_SCHEMA = "vv-adversary.campaign.v1"
SUMMARY_SCHEMA = "vv-adversary.campaign-summary.v1"

MAX_PAIRS = 30
MAX_INVOCATIONS = 400
MIN_ARTIFACT_BYTES = 65_536
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_TIME_BUDGET_SECONDS = 300
DEFAULT_BUDGET = 32
DEFAULT_MINIMIZE_BUDGET = 96
DEFAULT_MAX_FAILURES = 4
BUDGET_RANGE = (1, 512)
MINIMIZE_BUDGET_RANGE = (1, 256)
MAX_FAILURES_RANGE = (1, 16)
OUTPUT_LIMIT_BYTES = 1024 * 1024
MAX_CAMPAIGN_JSON_BYTES = 32 * 1024 * 1024  # same pre-parse limit as `vv-adversary replay`
HASH_CHUNK_BYTES = 1024 * 1024
MAX_LISTED_DIFFERENCES = 50

ROLE_CLEAN = "clean"
ROLE_KNOWN_FAULTY = "known_faulty"
ROLE_DIVERGENCE = "policy_divergence"

REDUCTION_FIELDS = ("atoms", "active_fault_ticks", "steps")
RECHECK_VALUES = ("agree", "disagree", "not_applicable")
CLASS_METRICS = ("novel_classes_found", "inherited_classes_found", "unidentified_violations")


@dataclass(frozen=True)
class Case:
    case_id: str
    role: str
    scenario: str
    contracts: str
    actuator: str | None


CASES = (
    Case("clean-nominal", ROLE_CLEAN, "scenarios/m3/nominal-stop.json", "scenarios/m3/contracts-nominal.json", None),
    Case(
        "known-faulty-delayed-after-fallback",
        ROLE_KNOWN_FAULTY,
        "scenarios/m3/delayed-after-fallback.json",
        "scenarios/m3/contracts-nominal.json",
        "scenarios/m3/actuator-delayed.json",
    ),
    Case("m4-x-first-overshoot", ROLE_DIVERGENCE, "scenarios/m4/x-first-overshoot.json", "scenarios/m3/contracts-nominal.json", None),
)


class AdversarialCampaignError(ValueError):
    """Plan, usage or budget error."""


class CampaignAbort(AdversarialCampaignError):
    """A budget or process limit stopped the run part way."""


class CampaignDocError(ValueError):
    """campaign.json could not be read as a JSON object."""


# Plan


def _in_range(value: Any, bounds: tuple[int, int]) -> bool:
    return type(value) is int and bounds[0] <= value <= bounds[1]


def plan_campaign(
    seeds: tuple[int, ...],
    *,
    cases: tuple[Case, ...] = CASES,
    budget: int = DEFAULT_BUDGET,
    minimize_budget: int = DEFAULT_MINIMIZE_BUDGET,
    max_failures: int = DEFAULT_MAX_FAILURES,
    max_invocations: int = MAX_INVOCATIONS,
    max_pairs: int = MAX_PAIRS,
    max_artifact_bytes: int = MAX_ARTIFACT_BYTES,
    time_budget_seconds: float = 300,
) -> dict[str, int | float]:
    """Validate every budget before any process starts."""
    if not seeds or len(set(seeds)) != len(seeds):
        raise AdversarialCampaignError("seeds must be non-empty and unique")
    if any(type(seed) is not int or not 0 <= seed <= 2**64 - 1 for seed in seeds):
        raise AdversarialCampaignError("seeds must be u64 values")
    if not cases:
        raise AdversarialCampaignError("the case matrix is empty")
    for name, value, bounds in (
        ("budget", budget, BUDGET_RANGE),
        ("minimize_budget", minimize_budget, MINIMIZE_BUDGET_RANGE),
        ("max_failures", max_failures, MAX_FAILURES_RANGE),
        ("max_pairs", max_pairs, (1, MAX_PAIRS)),
        ("max_invocations", max_invocations, (1, MAX_INVOCATIONS)),
        ("max_artifact_bytes", max_artifact_bytes, (MIN_ARTIFACT_BYTES, MAX_ARTIFACT_BYTES)),
    ):
        if not _in_range(value, bounds):
            raise AdversarialCampaignError(f"{name} must be between {bounds[0]} and {bounds[1]}")
    if (
        type(time_budget_seconds) not in (int, float)
        or not math.isfinite(time_budget_seconds)
        or not 0 < time_budget_seconds <= MAX_TIME_BUDGET_SECONDS
    ):
        raise AdversarialCampaignError(f"time_budget_seconds must be above zero and at most {MAX_TIME_BUDGET_SECONDS}")
    pairs = len(cases) * len(seeds)
    if pairs > max_pairs:
        raise AdversarialCampaignError(f"planned matrix has {pairs} pairs, above max_pairs {max_pairs}")
    # Per pair: 2 campaign runs, 1 replay, and at most original+minimized
    # replay-m4 for each kept failure.
    replay_m4_max = pairs * 2 * max_failures
    total_max = pairs * 3 + replay_m4_max
    if total_max > max_invocations:
        raise AdversarialCampaignError(
            f"planned matrix needs up to {total_max} invocations, above max_invocations {max_invocations}"
        )
    return {
        "planned_pairs": pairs,
        "max_replay_m4_invocations": replay_m4_max,
        "max_total_invocations": total_max,
        "max_invocations": max_invocations,
        "max_pairs": max_pairs,
        "budget": budget,
        "minimize_budget": minimize_budget,
        "max_failures": max_failures,
        "max_artifact_bytes": max_artifact_bytes,
        "time_budget_seconds": float(time_budget_seconds),
    }


def check_case_inputs(cases: tuple[Case, ...], root: Path = ROOT) -> None:
    for case in cases:
        for relative in (case.scenario, case.contracts, case.actuator):
            if relative is not None and not (root / relative).is_file():
                raise AdversarialCampaignError(f"case {case.case_id}: missing input {relative}")


# Tree comparison


def hash_tree(root: Path) -> dict[str, str]:
    """sha256 of every regular file below root, keyed by posix relative path."""
    result: dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_symlink() and path.is_file():
            result[path.relative_to(root).as_posix()] = file_sha256(path)
    return result


def file_sha256(path: Path) -> str:
    """Streaming SHA-256 in fixed chunks (hashlib.file_digest needs Python 3.11; CI runs 3.10)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_trees(first: Path, repeat: Path) -> dict[str, Any]:
    left, right = hash_tree(first), hash_tree(repeat)
    differences: list[dict[str, str]] = []
    for name in sorted(set(left) | set(right)):
        if name not in right:
            differences.append({"path": name, "kind": "missing_in_repeat"})
        elif name not in left:
            differences.append({"path": name, "kind": "missing_in_first"})
        elif left[name] != right[name]:
            differences.append({"path": name, "kind": "content_differs"})
    total = len(set(left) | set(right))
    return {
        "files_total": total,
        "files_identical": total - len(differences),
        "difference_count": len(differences),
        "differences": differences[:MAX_LISTED_DIFFERENCES],
    }


# campaign.json validation (untrusted input)


def percent_reduction(before: int, after: int) -> float | None:
    if before <= 0 or after > before:
        return None
    return round(100 * (before - after) / before, 2)


def load_campaign_json(path: Path) -> dict[str, Any]:
    try:
        # Bounded read before parsing: the size is checked on the bytes read, not a prior stat.
        with path.open("rb") as handle:
            raw = handle.read(MAX_CAMPAIGN_JSON_BYTES + 1)
        if len(raw) > MAX_CAMPAIGN_JSON_BYTES:
            raise CampaignDocError(f"{path.name} is larger than {MAX_CAMPAIGN_JSON_BYTES} bytes")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError) as error:  # ValueError covers JSON, Unicode and int-digit limits
        raise CampaignDocError(f"cannot read {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise CampaignDocError(f"{path.name} must be a JSON object")
    return value


def _field(parent: Any, key: str, kind: type, label: str, problems: list[str]) -> Any:
    """Typed read of parent[key]. `int` means a non-negative int (bool excluded)."""
    value = parent.get(key) if isinstance(parent, dict) else None
    ok = (type(value) is int and value >= 0) if kind is int else isinstance(value, kind)
    if not ok:
        problems.append(f"missing or invalid {label}")
        return None
    return value


def _nested_counts(value: Any, label: str, problems: list[str]) -> dict[str, dict[str, int]] | None:
    """{outer: {inner: count}} with sorted keys, or None plus a problem on any bad entry."""
    ok = isinstance(value, dict) and all(
        isinstance(row, dict) and all(type(n) is int and n >= 0 for n in row.values())
        for row in value.values()
    )
    if not ok:
        problems.append(f"missing or invalid {label}")
        return None
    return {str(k): {str(i): value[k][i] for i in sorted(value[k])} for k in sorted(value)}


def _column_totals(rows: dict[str, dict[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows.values():
        for key, n in row.items():
            totals[key] = totals.get(key, 0) + n
    return {key: totals[key] for key in sorted(totals)}


def _reduction(failure: dict[str, Any], index: int, problems: list[str]) -> dict[str, tuple[int, int]] | None:
    block = failure.get("reduction")
    result: dict[str, tuple[int, int]] = {}
    for name in REDUCTION_FIELDS:
        sides = block.get(name) if isinstance(block, dict) else None
        before, after = (sides.get("before"), sides.get("after")) if isinstance(sides, dict) else (None, None)
        if any(type(n) is not int or n < 0 for n in (before, after)):
            problems.append(f"failures[{index}]: missing or invalid reduction.{name}")
            return None
        result[name] = (before, after)
    return result


def aggregate_campaign(doc: dict[str, Any]) -> dict[str, Any]:
    """Validate and summarise one untrusted campaign.json. Never raises on odd
    content; every deviation from the expected shape is recorded in `problems`."""
    problems: list[str] = []
    if doc.get("schema") != CAMPAIGN_SCHEMA:
        problems.append(f"unexpected schema {str(doc.get('schema'))[:80]!r}")
    digest = doc.get("campaign_sha256")
    if not (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
        problems.append("missing or invalid campaign_sha256")
        digest = None

    metrics = _field(doc, "metrics", dict, "metrics", problems) or {}
    evaluations = _field(metrics, "evaluations", dict, "metrics.evaluations", problems) or {}
    counts = {
        key: _field(metrics, key, int, f"metrics.{key}", problems)
        for key in ("candidates", "unique_classes_found", "inconclusive_evaluations", "control_violations")
    }
    counts["evaluations"] = _field(evaluations, "total", int, "metrics.evaluations.total", problems)
    extra = {key: _field(metrics, key, int, f"metrics.{key}", problems) for key in CLASS_METRICS}
    split = (extra["novel_classes_found"], extra["inherited_classes_found"], counts["unique_classes_found"])
    if None not in split and split[0] + split[1] != split[2]:
        problems.append("metrics: novel_classes_found + inherited_classes_found != unique_classes_found")
    by_cell = _nested_counts(metrics.get("violations_by_policy"), "metrics.violations_by_policy", problems)
    by_policy = {policy: sum(row.values()) for policy, row in by_cell.items()} if by_cell is not None else None
    by_property = _column_totals(by_cell) if by_cell is not None else None

    _field(doc, "control", list, "control", problems)
    failures = _field(doc, "failures", list, "failures", problems) or []
    if len(failures) > MAX_FAILURES_RANGE[1]:
        problems.append(f"failures has {len(failures)} entries, above the engine cap {MAX_FAILURES_RANGE[1]}")
        failures = failures[: MAX_FAILURES_RANGE[1]]
    recheck = dict.fromkeys(RECHECK_VALUES, 0)
    disagreements: list[dict[str, Any]] = []
    reduced = 0
    totals = {name: [0, 0] for name in REDUCTION_FIELDS}
    for index, failure in enumerate(failures):
        if not isinstance(failure, dict):
            problems.append(f"failures[{index}] is not an object")
            continue
        outcome = _field(failure.get("recheck"), "result", str, f"failures[{index}].recheck.result", problems)
        if outcome in RECHECK_VALUES:
            recheck[outcome] += 1
        elif outcome is not None:
            problems.append(f"failures[{index}]: unknown recheck result {outcome[:40]!r}")
        if outcome == "disagree":
            identity = failure.get("identity")
            disagreements.append({"failure_index": index, "identity": identity if isinstance(identity, dict) else None})
        _field(failure, "inherited_from_control", bool, f"failures[{index}].inherited_from_control", problems)
        reduction = _reduction(failure, index, problems)
        if reduction is not None:
            reduced += 1
            for name, (before, after) in reduction.items():
                totals[name][0] += before
                totals[name][1] += after

    matrix = _nested_counts(doc.get("policy_matrix"), "policy_matrix", problems)
    return {
        "problems": problems,
        "campaign_sha256": digest,
        "candidates": counts["candidates"],
        "evaluations": counts["evaluations"],
        "violations_by_policy": by_policy,
        "violations_by_property": by_property,
        "unique_failure_classes": counts["unique_classes_found"],
        "novel_classes": extra["novel_classes_found"],
        "inherited_classes": extra["inherited_classes_found"],
        "unidentified_violations": extra["unidentified_violations"],
        "inconclusive": counts["inconclusive_evaluations"],
        "control_violations": counts["control_violations"],
        "recheck": recheck,
        "recheck_disagreements": disagreements,
        "reduction": {
            "failures_with_metrics": reduced,
            "totals": {
                name: {"before": b, "after": a, "percent": percent_reduction(b, a)}
                for name, (b, a) in totals.items()
            },
        },
        "policy_matrix": matrix,
        "policy_matrix_totals": _column_totals(matrix or {}),
    }


def evaluate_control(role: str, control_violations: int | None) -> tuple[bool, str]:
    """Control expectation for a case role; fails closed on missing data."""
    if role == ROLE_DIVERGENCE:
        return True, "no control expectation"
    if control_violations is None:
        return False, "control violation count unavailable"
    if role == ROLE_CLEAN:
        if control_violations == 0:
            return True, "clean control has no violations"
        return False, f"clean control reported {control_violations} violation(s): possible false positive"
    if role == ROLE_KNOWN_FAULTY:
        if control_violations > 0:
            return True, f"known-faulty control detected {control_violations} violation(s)"
        return False, "known-faulty control reported no violation: pre-existing fault missed"
    return False, f"unknown role {role!r}"


def document_failures(aggregate: dict[str, Any]) -> list[str]:
    """Reasons an aggregated campaign.json fails its pair (control expectation excluded)."""
    reasons = []
    if aggregate["problems"]:
        shown = "; ".join(aggregate["problems"][:5])
        reasons.append(f"campaign.json invalid ({len(aggregate['problems'])} problem(s)): {shown}")
    disagreements = aggregate["recheck_disagreements"]
    if disagreements:
        indexes = ", ".join(str(item["failure_index"]) for item in disagreements[:5])
        reasons.append(f"recheck disagreed for {len(disagreements)} failure(s) (failures[{indexes}]): possible false positive")
    if aggregate["unidentified_violations"]:
        reasons.append(f"{aggregate['unidentified_violations']} violation(s) without an identified class")
    return reasons


# Execution


def default_binary(name: str) -> Path:
    return ROOT / "target" / "release" / (name + (".exe" if os.name == "nt" else ""))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


class Campaign:
    def __init__(
        self,
        binary: Path,
        lab_binary: Path,
        output_root: Path,
        seeds: tuple[int, ...],
        plan: dict[str, int | float],
        *,
        sim_seed: int | None = None,
        cases: tuple[Case, ...] = CASES,
    ) -> None:
        self.binary, self.lab_binary = binary.resolve(), lab_binary.resolve()
        self.seeds, self.sim_seed, self.plan, self.cases = seeds, sim_seed, plan, cases
        self.root = output_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.budget = CampaignArtifactBudget(self.root, int(plan["max_artifact_bytes"]))
        self.start = time.monotonic()
        self.deadline = self.start + float(plan["time_budget_seconds"])
        self.invocations = 0
        self.records: list[dict[str, Any]] = []
        self.pairs: list[dict[str, Any]] = []
        self.pair_timing: list[dict[str, Any]] = []
        self.abort_reason: str | None = None

    def display(self, command: list[str]) -> list[str]:
        """Command with paths shortened to repo-relative form; binaries by name."""
        shown = []
        for part in command:
            try:
                base = self.root if Path(part).is_relative_to(self.root) else ROOT
                shown.append(Path(part).relative_to(base).as_posix())
            except (ValueError, OSError):
                shown.append(Path(part).name if part in (str(self.binary), str(self.lab_binary)) else part)
        return shown

    def invoke(self, command: list[str], label: str) -> dict[str, Any]:
        if self.invocations + 1 > int(self.plan["max_invocations"]):
            raise CampaignAbort("campaign would exceed its invocation budget")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CampaignAbort("campaign exceeded its time budget")
        started = time.perf_counter()
        try:
            process = run_bounded_process(
                command, cwd=ROOT, timeout_seconds=remaining, max_output_bytes=OUTPUT_LIMIT_BYTES, description=label
            )
        except ProcessLimitError as error:
            raise CampaignAbort(str(error)) from error
        seconds = time.perf_counter() - started
        self.invocations += 1
        log_path = self.root / "commands" / f"{self.invocations:03d}.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"label={label}\nexit_code={process.returncode}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}",
            encoding="utf-8",
            newline="\n",
        )
        try:
            self.budget.refresh(self.root)
        except ProcessLimitError as error:
            raise CampaignAbort(str(error)) from error
        record = {"label": label, "command": self.display(command), "exit_code": process.returncode, "seconds": round(seconds, 6)}
        self.records.append(record)
        return record

    def campaign_command(self, case: Case, seed: int, output: Path) -> list[str]:
        command = [
            str(self.binary), "campaign",
            "--base", str(ROOT / case.scenario),
            "--contracts", str(ROOT / case.contracts),
        ]
        if case.actuator is not None:
            command += ["--actuator", str(ROOT / case.actuator)]
        return command + [
            "--campaign-seed", str(seed),
            "--sim-seed", str(seed if self.sim_seed is None else self.sim_seed),
            "--budget", str(self.plan["budget"]),
            "--minimize-budget", str(self.plan["minimize_budget"]),
            "--max-failures", str(self.plan["max_failures"]),
            "--output", str(output),
        ]

    def check_cases(self, first: Path, tag: str, pair: dict[str, Any], timing: dict[str, Any]) -> None:
        """Run `vv-lab replay-m4` on every kept case, original and minimized."""
        fails: list[str] = pair["failures"]
        case_dirs = sorted(path for path in (first / "cases").glob("*") if path.is_dir())
        limit = int(self.plan["max_failures"])
        if len(case_dirs) > limit:
            fails.append(f"campaign wrote {len(case_dirs)} cases, above max_failures {limit}")
            case_dirs = case_dirs[:limit]
        artifacts = []
        for case_dir in case_dirs:
            for side in ("original", "minimized"):
                if (case_dir / side / "m4.json").is_file():
                    artifacts.append(case_dir / side / "m4.json")
                else:
                    fails.append(f"case {case_dir.name} has no {side}/m4.json")
        failed: list[str] = []
        seconds = 0.0
        for path in artifacts:
            relative = path.relative_to(first).as_posix()
            record = self.invoke(
                [str(self.lab_binary), "replay-m4", str(path)], f"replay-m4-{tag}-{relative.replace('/', '-')}"
            )
            seconds += record["seconds"]
            if record["exit_code"] != 0:
                failed.append(relative)
        timing["replay_m4_seconds"] = round(seconds, 6)
        pair["replay_m4"] = {"checked": len(artifacts), "passed": len(artifacts) - len(failed), "failed": failed}
        if failed:
            fails.append(f"vv-lab replay-m4 failed for {len(failed)} artifact(s)")

    def check_document(self, case: Case, first: Path, pair: dict[str, Any], timing: dict[str, Any]) -> None:
        fails: list[str] = pair["failures"]
        try:
            aggregate = aggregate_campaign(load_campaign_json(first / "campaign.json"))
        except CampaignDocError as error:
            fails.append(f"campaign.json unreadable: {error}")
            return
        pair["aggregate"] = aggregate
        ok, message = evaluate_control(case.role, aggregate["control_violations"])
        pair["control_expectation"] = {"ok": ok, "message": message}
        fails += document_failures(aggregate)
        if not ok:
            fails.append(f"control expectation: {message}")
        evaluations = aggregate["evaluations"]
        timing["evaluations"] = evaluations
        timing["seconds_per_evaluation"] = round(timing["first_seconds"] / evaluations, 6) if evaluations else None
        pair["campaign_json_sha256"] = hash_tree(first).get("campaign.json")

    def run_pair(self, case: Case, seed: int) -> None:
        pair_dir = self.root / case.case_id / f"seed-{seed}"
        pair_dir.mkdir(parents=True)
        first, repeat = pair_dir / "first", pair_dir / "repeat"
        tag = f"{case.case_id}-seed-{seed}"
        pair: dict[str, Any] = {
            "case_id": case.case_id, "role": case.role, "seed": seed,
            "sim_seed": seed if self.sim_seed is None else self.sim_seed, "failures": [],
            "determinism": None, "replay": None, "replay_m4": None, "aggregate": None, "control_expectation": None,
        }
        timing: dict[str, Any] = {"case_id": case.case_id, "seed": seed}
        self.pairs.append(pair)
        self.pair_timing.append(timing)
        fails: list[str] = pair["failures"]

        for name, output in (("first", first), ("repeat", repeat)):
            record = self.invoke(self.campaign_command(case, seed, output), f"campaign-{name}-{tag}")
            timing[f"{name}_seconds"] = record["seconds"]
            if record["exit_code"] != 0:
                fails.append(f"campaign ({name}) exited {record['exit_code']}")
                return

        determinism = compare_trees(first, repeat)
        pair["determinism"] = determinism
        if determinism["files_total"] == 0:
            fails.append("determinism: campaign produced no files")
        elif determinism["difference_count"]:
            listed = ", ".join(item["path"] for item in determinism["differences"][:5])
            fails.append(f"determinism: {determinism['difference_count']} file(s) differ ({listed})")

        replay = self.invoke([str(self.binary), "replay", str(first / "campaign.json")], f"replay-{tag}")
        pair["replay"] = {"exit_code": replay["exit_code"], "passed": replay["exit_code"] == 0}
        timing["replay_seconds"] = replay["seconds"]
        if replay["exit_code"] != 0:
            fails.append(f"vv-adversary replay exited {replay['exit_code']}")

        self.check_cases(first, tag, pair, timing)
        self.check_document(case, first, pair, timing)

    def run(self) -> dict[str, Any]:
        try:
            for case in self.cases:
                for seed in self.seeds:
                    self.run_pair(case, seed)
        except CampaignAbort as error:
            self.abort_reason = str(error)
        return self.build_summary(time.monotonic() - self.start)

    def build_summary(self, elapsed: float) -> dict[str, Any]:
        failed_pairs = [f"{pair['case_id']}/seed-{pair['seed']}" for pair in self.pairs if pair["failures"]]
        complete = self.abort_reason is None and len(self.pairs) == int(self.plan["planned_pairs"])
        disagreements = sum(len(pair["aggregate"]["recheck_disagreements"]) for pair in self.pairs if pair["aggregate"])
        try:
            retained = self.budget.refresh(self.root)
        except ProcessLimitError:
            retained = self.budget.total_bytes
        return {
            "schema": SUMMARY_SCHEMA,
            "deterministic": {
                "status": "passed" if complete and not failed_pairs else "failed",
                "abort_reason": self.abort_reason,
                "plan": self.plan,
                "seeds": list(self.seeds),
                "cases": [asdict(case) for case in self.cases],
                "executed_pairs": len(self.pairs),
                "failed_pairs": failed_pairs,
                "recheck_disagreements_total": disagreements,
                "pairs": self.pairs,
            },
            "timing": {
                "note": "wall-clock measurements taken outside the simulation; not reproducible",
                "machine": {"platform": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count()},
                "total_seconds": round(elapsed, 4),
                "invocations": self.invocations,
                "retained_artifact_bytes": retained,
                "campaigns": self.pair_timing,
                "commands": self.records,
            },
        }


# Reports


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    cell = lambda value: "n/a" if value is None else str(value)  # noqa: E731
    return (
        ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
        + ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    )


def render_markdown(summary: dict[str, Any]) -> str:
    det, timing = summary["deterministic"], summary["timing"]
    pairs = det["pairs"]
    lines = [
        "# Adversarial campaign summary",
        "",
        f"Status: **{det['status']}**. Pairs executed: {det['executed_pairs']} of {det['plan']['planned_pairs']}.",
    ]
    if det["abort_reason"]:
        lines.append(f"Aborted: {det['abort_reason']}")
    if det["failed_pairs"]:
        lines.append("Failed pairs: " + ", ".join(det["failed_pairs"]))
    lines.append(f"Recheck disagreements (possible false positives): {det['recheck_disagreements_total']}")

    rows = []
    for pair in pairs:
        agg, determinism, m4 = pair["aggregate"] or {}, pair["determinism"], pair["replay_m4"]
        rows.append([
            pair["case_id"], pair["seed"], "ok" if not pair["failures"] else "FAIL",
            agg.get("candidates"), agg.get("evaluations"), agg.get("unique_failure_classes"),
            agg.get("novel_classes"), agg.get("inherited_classes"), agg.get("unidentified_violations"),
            agg.get("inconclusive"), agg.get("control_violations"),
            (pair["control_expectation"] or {}).get("ok"),
            len(agg["recheck_disagreements"]) if agg else None,
            f"{determinism['files_identical']}/{determinism['files_total']}" if determinism else None,
            (pair["replay"] or {}).get("passed"),
            f"{m4['passed']}/{m4['checked']}" if m4 else None,
        ])
    lines += ["", "## Results", ""] + _table(
        ["case", "seed", "result", "candidates", "evaluations", "failure classes", "novel", "inherited",
         "unidentified", "inconclusive", "control violations", "control ok", "recheck disagree",
         "identical files", "replay", "replay-m4"],
        rows,
    )
    with_agg = [pair for pair in pairs if pair["aggregate"]]
    dump = lambda value: json.dumps(value, sort_keys=True)  # noqa: E731
    lines += ["", "## Violations and policy comparison", ""] + _table(
        ["case", "seed", "by policy", "by property", "policy matrix totals"],
        [[p["case_id"], p["seed"], dump(p["aggregate"]["violations_by_policy"]),
          dump(p["aggregate"]["violations_by_property"]), dump(p["aggregate"]["policy_matrix_totals"])]
         for p in with_agg],
    )
    lines += ["", "## Reduction (before to after, total over kept failures)", ""] + _table(
        ["case", "seed", "failures", "atoms", "active fault ticks", "steps"],
        [
            [p["case_id"], p["seed"], p["aggregate"]["reduction"]["failures_with_metrics"]]
            + [
                f"{t['before']} to {t['after']} ({'n/a' if t['percent'] is None else t['percent']}%)"
                for t in (p["aggregate"]["reduction"]["totals"][name] for name in REDUCTION_FIELDS)
            ]
            for p in with_agg
        ],
    )
    machine = timing["machine"]
    lines += [
        "",
        "## Execution cost (measured, not reproducible)",
        "",
        f"Machine: {machine['platform']}, Python {machine['python']}, {machine['cpu_count']} CPUs. "
        f"Total {timing['total_seconds']} s, {timing['invocations']} invocations, "
        f"{timing['retained_artifact_bytes']} artifact bytes.",
        "",
    ]
    lines += _table(
        ["case", "seed", "campaign s", "repeat s", "replay s", "replay-m4 s", "evaluations", "s per evaluation"],
        [
            [t["case_id"], t["seed"], t.get("first_seconds"), t.get("repeat_seconds"), t.get("replay_seconds"),
             t.get("replay_m4_seconds"), t.get("evaluations"), t.get("seconds_per_evaluation")]
            for t in timing["campaigns"]
        ],
    )
    lines += ["", "## Commands", ""] + _table(
        ["label", "exit", "seconds", "command"],
        [[r["label"], r["exit_code"], r["seconds"], "`" + " ".join(r["command"]) + "`"] for r in timing["commands"]],
    )
    problems = [f"{p['case_id']}/seed-{p['seed']}: {m}" for p in pairs for m in p["failures"]]
    if problems:
        lines += ["", "## Failed checks", ""] + [f"- {item}" for item in problems]
    return "\n".join(lines) + "\n"


def write_reports(root: Path, summary: dict[str, Any]) -> None:
    write_json(root / "summary.json", summary)
    (root / "summary.md").write_text(render_markdown(summary), encoding="utf-8", newline="\n")


# CLI


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", type=Path, default=default_binary("vv-adversary"))
    parser.add_argument("--lab-binary", type=Path, default=default_binary("vv-lab"))
    parser.add_argument("--seeds", type=parse_seeds, default=DEFAULT_SEEDS)
    parser.add_argument("--sim-seed", type=int, default=None, help="default: same as each campaign seed")
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs" / "adversarial")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--minimize-budget", type=int, default=DEFAULT_MINIMIZE_BUDGET)
    parser.add_argument("--max-failures", type=int, default=DEFAULT_MAX_FAILURES)
    parser.add_argument("--max-invocations", type=int, default=MAX_INVOCATIONS)
    parser.add_argument("--time-budget-seconds", type=float, default=MAX_TIME_BUDGET_SECONDS)
    parser.add_argument("--max-artifact-bytes", type=int, default=MAX_ARTIFACT_BYTES)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = make_parser().parse_args(argv)
    try:
        if arguments.sim_seed is not None and not 0 <= arguments.sim_seed <= 2**64 - 1:
            raise AdversarialCampaignError("sim-seed must be a u64 value")
        plan = plan_campaign(
            arguments.seeds,
            budget=arguments.budget,
            minimize_budget=arguments.minimize_budget,
            max_failures=arguments.max_failures,
            max_invocations=arguments.max_invocations,
            max_artifact_bytes=arguments.max_artifact_bytes,
            time_budget_seconds=arguments.time_budget_seconds,
        )
        check_case_inputs(CASES)
        for label, binary in (("vv-adversary", arguments.binary), ("vv-lab", arguments.lab_binary)):
            if not binary.is_file():
                raise AdversarialCampaignError(f"{label} binary does not exist: {binary}")
        output_root = arguments.output_root
        if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
            raise AdversarialCampaignError(f"output root must be empty or absent: {output_root}")
        campaign = Campaign(
            arguments.binary, arguments.lab_binary, output_root, arguments.seeds, plan, sim_seed=arguments.sim_seed
        )
    except (AdversarialCampaignError, ProcessLimitError, OSError) as error:
        print(f"adversarial campaign not started: {error}", file=sys.stderr)
        return 2
    summary = campaign.run()
    write_reports(campaign.root, summary)
    det = summary["deterministic"]
    brief = {key: det[key] for key in ("status", "failed_pairs", "abort_reason")}
    print(json.dumps(brief | {"pairs": det["executed_pairs"], "summary": str(campaign.root / "summary.json")}, sort_keys=True))
    return 0 if det["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
