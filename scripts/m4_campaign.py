"""Run the bounded M4 paired-controller evaluation matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from process_limits import CampaignArtifactBudget, ProcessLimitError, run_bounded_process
from run_campaign import parse_seeds

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (42, 1337, 2026)
MAX_PAIRS = 30
MAX_INVOCATIONS = 90
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TIME_BUDGET_SECONDS = 120
SIMULATOR_INVOCATIONS_PER_PAIR = 6
COMPARISON_INVOCATIONS_PER_PAIR = 1
OUTPUT_LIMIT_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Case:
    scenario_id: str
    scenario: str
    contracts: str
    actuator: str


CASES = (
    Case(
        "nominal",
        "scenarios/m3/nominal-stop.json",
        "scenarios/m3/contracts-nominal.json",
        "scenarios/m3/actuator-none.json",
    ),
    Case(
        "x-first-overshoot",
        "scenarios/m4/x-first-overshoot.json",
        "scenarios/m3/contracts-nominal.json",
        "scenarios/m3/actuator-none.json",
    ),
    Case(
        "gps-fallback",
        "scenarios/m3/gps-fallback-timely.json",
        "scenarios/m3/contracts-fallback-delayed.json",
        "scenarios/m3/actuator-none.json",
    ),
    Case(
        "intermittent-actuation",
        "scenarios/m3/intermittent-actuation.json",
        "scenarios/m3/contracts-progress.json",
        "scenarios/m3/actuator-intermittent.json",
    ),
)


class M4CampaignError(ValueError):
    """Invalid M4 plan or failed paired-controller evaluation."""


def plan_campaign(
    seeds: tuple[int, ...],
    *,
    max_invocations: int = MAX_INVOCATIONS,
    max_pairs: int = MAX_PAIRS,
    max_artifact_bytes: int = MAX_ARTIFACT_BYTES,
    time_budget_seconds: float = MAX_TIME_BUDGET_SECONDS,
) -> dict[str, int | float]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise M4CampaignError("seeds must be non-empty and unique")
    pairs = len(CASES) * len(seeds)
    simulator_invocations = pairs * SIMULATOR_INVOCATIONS_PER_PAIR
    comparison_invocations = pairs * COMPARISON_INVOCATIONS_PER_PAIR
    total_invocations = simulator_invocations + comparison_invocations
    if type(max_pairs) is not int or not 1 <= max_pairs <= MAX_PAIRS:
        raise M4CampaignError(f"max_pairs must be between 1 and {MAX_PAIRS}")
    if pairs > max_pairs:
        raise M4CampaignError(
            f"planned matrix has {pairs} pairs, above max_pairs {max_pairs}"
        )
    if type(max_invocations) is not int or not 1 <= max_invocations <= MAX_INVOCATIONS:
        raise M4CampaignError(
            f"max_invocations must be between 1 and {MAX_INVOCATIONS}"
        )
    if total_invocations > max_invocations:
        raise M4CampaignError(
            f"planned matrix needs {total_invocations} invocations, above max_invocations {max_invocations}"
        )
    if (
        type(max_artifact_bytes) is not int
        or not 65_536 <= max_artifact_bytes <= MAX_ARTIFACT_BYTES
    ):
        raise M4CampaignError(
            f"max_artifact_bytes must be between 65536 and {MAX_ARTIFACT_BYTES}"
        )
    if (
        isinstance(time_budget_seconds, bool)
        or not isinstance(time_budget_seconds, (int, float))
        or not math.isfinite(time_budget_seconds)
        or not 0 < time_budget_seconds <= MAX_TIME_BUDGET_SECONDS
    ):
        raise M4CampaignError(
            f"time_budget_seconds must be above zero and at most {MAX_TIME_BUDGET_SECONDS}"
        )
    return {
        "planned_pairs": pairs,
        "planned_simulator_invocations": simulator_invocations,
        "planned_comparison_invocations": comparison_invocations,
        "planned_total_invocations": total_invocations,
        "max_pairs": max_pairs,
        "max_invocations": max_invocations,
        "max_artifact_bytes": max_artifact_bytes,
        "time_budget_seconds": float(time_budget_seconds),
    }


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M4CampaignError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise M4CampaignError(f"{label} must be a JSON object")
    return value


class Campaign:
    def __init__(
        self,
        binary: Path,
        output_root: Path,
        seeds: tuple[int, ...],
        plan: dict[str, int | float],
    ) -> None:
        self.binary = binary.resolve()
        self.seeds = seeds
        self.plan = plan
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        campaign_root = output_root.resolve()
        campaign_root.mkdir(parents=True, exist_ok=True)
        suffix = 0
        while True:
            name = f"campaign-m4-{timestamp}" if suffix == 0 else f"campaign-m4-{timestamp}-{suffix}"
            candidate = campaign_root / name
            try:
                candidate.mkdir()
                self.root = candidate
                break
            except FileExistsError:
                suffix += 1
        self.budget = CampaignArtifactBudget(
            self.root, int(plan["max_artifact_bytes"])
        )
        self.deadline = time.monotonic() + float(plan["time_budget_seconds"])
        self.simulator_invocations = 0
        self.comparison_invocations = 0
        self.command_invocations = 0
        self.results: list[dict[str, Any]] = []

    def invoke(
        self,
        command: list[str],
        label: str,
        *,
        simulator_invocations: int = 0,
        comparison: bool = False,
    ) -> Path:
        next_total = (
            self.simulator_invocations
            + self.comparison_invocations
            + simulator_invocations
            + int(comparison)
        )
        if next_total > int(self.plan["max_invocations"]):
            raise M4CampaignError("campaign would exceed its invocation budget")
        remaining_seconds = self.deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise M4CampaignError("campaign exceeded its time budget")
        process = run_bounded_process(
            command,
            cwd=ROOT,
            timeout_seconds=remaining_seconds,
            max_output_bytes=OUTPUT_LIMIT_BYTES,
            description=label,
        )
        self.simulator_invocations += simulator_invocations
        self.comparison_invocations += int(comparison)
        self.command_invocations += 1
        log_path = self.root / "commands" / f"{self.command_invocations:03d}-{label}.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"exit_code={process.returncode}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}",
            encoding="utf-8",
            newline="\n",
        )
        self.budget.refresh(self.root)
        if process.returncode != 0:
            raise M4CampaignError(
                f"{label} returned {process.returncode}: {process.stderr.strip()}"
            )
        return log_path

    def run_case(self, case: Case, seed: int) -> None:
        pair_root = self.root / case.scenario_id / f"seed-{seed}"
        pair_root.mkdir(parents=True)
        scenario_copy = pair_root / "scenario.json"
        contracts_copy = pair_root / "contracts.json"
        actuator_copy = pair_root / "actuator.json"
        for source, target in (
            (ROOT / case.scenario, scenario_copy),
            (ROOT / case.contracts, contracts_copy),
            (ROOT / case.actuator, actuator_copy),
        ):
            target.write_bytes(source.read_bytes())
        self.budget.refresh(self.root)

        initial: dict[str, Path] = {}
        repeated: dict[str, Path] = {}
        for controller in ("dominant_axis", "x_first"):
            run_dir = pair_root / controller / "initial"
            run_dir.mkdir(parents=True)
            self.invoke(
                [
                    str(self.binary),
                    "run-m4",
                    str(scenario_copy),
                    "--seed",
                    str(seed),
                    "--controller",
                    controller,
                    "--contracts",
                    str(contracts_copy),
                    "--actuator",
                    str(actuator_copy),
                    "--output",
                    str(run_dir),
                    "--max-output-bytes",
                    str(self.budget.remaining(self.root)),
                ],
                f"run-{controller}-{case.scenario_id}-seed-{seed}",
                simulator_invocations=1,
            )
            initial[controller] = run_dir
        for controller in ("dominant_axis", "x_first"):
            run_dir = pair_root / controller / "repeat"
            run_dir.mkdir(parents=True)
            self.invoke(
                [
                    str(self.binary),
                    "run-m4",
                    str(scenario_copy),
                    "--seed",
                    str(seed),
                    "--controller",
                    controller,
                    "--contracts",
                    str(contracts_copy),
                    "--actuator",
                    str(actuator_copy),
                    "--output",
                    str(run_dir),
                    "--max-output-bytes",
                    str(self.budget.remaining(self.root)),
                ],
                f"repeat-{controller}-{case.scenario_id}-seed-{seed}",
                simulator_invocations=1,
            )
            repeated[controller] = run_dir

        files = ("events.json", "report.json", "mission.json", "verification.json", "m4.json")
        repeat_hashes: dict[str, dict[str, str]] = {}
        for controller in ("dominant_axis", "x_first"):
            hashes = {}
            for name in files:
                first = (initial[controller] / name).read_bytes()
                repeat = (repeated[controller] / name).read_bytes()
                if first != repeat:
                    raise M4CampaignError(
                        f"{controller} repeat differs for {case.scenario_id}, seed {seed}, {name}"
                    )
                hashes[name] = hashlib.sha256(first).hexdigest()
            repeat_hashes[controller] = hashes
        self.budget.refresh(self.root)

        comparison_path = pair_root / "comparison.json"
        comparison_log = self.invoke(
            [
                str(self.binary),
                "compare-m4",
                str(initial["dominant_axis"] / "m4.json"),
                str(initial["x_first"] / "m4.json"),
                "--output",
                str(comparison_path),
            ],
            f"compare-{case.scenario_id}-seed-{seed}",
            simulator_invocations=2,
            comparison=True,
        )
        comparison = load_json(comparison_path, "M4 comparison artifact")
        if comparison.get("external_calendar_equivalent") is not True:
            raise M4CampaignError("M4 comparison did not confirm calendar equivalence")
        if comparison.get("normalized_exogenous_calendar_version") != 1:
            raise M4CampaignError("unsupported normalized exogenous calendar version")
        controllers = comparison.get("controllers")
        if not isinstance(controllers, list) or [
            entry.get("controller_id") for entry in controllers if isinstance(entry, dict)
        ] != ["dominant_axis", "x_first"]:
            raise M4CampaignError("M4 comparison does not contain the expected policy pair")
        if len(controllers) != 2 or controllers[0].get("metrics") is None or controllers[1].get("metrics") is None:
            raise M4CampaignError("M4 comparison metrics are incomplete")
        if case.scenario_id == "x-first-overshoot":
            metrics = {entry["controller_id"]: entry["metrics"] for entry in controllers}
            if (
                metrics["dominant_axis"].get("mission_outcome") != "completed"
                or metrics["x_first"].get("mission_outcome") == "completed"
                or metrics["dominant_axis"].get("safety_status") != "passed"
                or metrics["x_first"].get("safety_status") != "passed"
                or comparison.get("action_difference_ticks", 0) < 1
            ):
                raise M4CampaignError("the X-first overshoot case did not produce its expected safe progress difference")

        self.budget.refresh(self.root)
        self.results.append(
            {
                "scenario_id": case.scenario_id,
                "seed": seed,
                "input_sha256": {
                    "scenario": digest_file(scenario_copy),
                    "contracts": digest_file(contracts_copy),
                    "actuator": digest_file(actuator_copy),
                },
                "external_calendar_sha256": comparison[
                    "normalized_exogenous_calendar_sha256"
                ],
                "action_difference_ticks": comparison["action_difference_ticks"],
                "first_action_difference_tick": comparison["first_action_difference_tick"],
                "safety_outcomes_differ": comparison["safety_outcomes_differ"],
                "temporal_outcomes_differ": comparison["temporal_outcomes_differ"],
                "mission_outcomes_differ": comparison["mission_outcomes_differ"],
                "metrics": {
                    entry["controller_id"]: entry["metrics"] for entry in controllers
                },
                "repeat_identical": True,
                "replay_verified": {"dominant_axis": True, "x_first": True},
                "simulator_invocations": 6,
                "comparison_invocations": 1,
                "output_paths": {
                    "dominant_axis_initial": (initial["dominant_axis"] / "m4.json").relative_to(self.root).as_posix(),
                    "x_first_initial": (initial["x_first"] / "m4.json").relative_to(self.root).as_posix(),
                    "dominant_axis_repeat": (repeated["dominant_axis"] / "m4.json").relative_to(self.root).as_posix(),
                    "x_first_repeat": (repeated["x_first"] / "m4.json").relative_to(self.root).as_posix(),
                    "comparison": comparison_path.relative_to(self.root).as_posix(),
                    "comparison_log": comparison_log.relative_to(self.root).as_posix(),
                },
                "repeat_output_sha256": repeat_hashes,
                "comparison_sha256": digest_file(comparison_path),
            }
        )

    def run(self) -> Path:
        if not self.binary.is_file():
            raise M4CampaignError(f"M4 binary does not exist: {self.binary}")
        for case in CASES:
            for seed in self.seeds:
                self.run_case(case, seed)
        if (
            self.simulator_invocations != int(self.plan["planned_simulator_invocations"])
            or self.comparison_invocations != int(self.plan["planned_comparison_invocations"])
        ):
            raise M4CampaignError("campaign did not execute its validated invocation plan")
        elapsed = time.monotonic() - (self.deadline - float(self.plan["time_budget_seconds"]))
        if elapsed > float(self.plan["time_budget_seconds"]):
            raise M4CampaignError("campaign exceeded its total time budget")
        summary = {
            "schema_version": 1,
            "suite": "m4_controller_evaluation",
            **self.plan,
            "actual_pairs": len(self.results),
            "actual_simulator_invocations": self.simulator_invocations,
            "actual_comparison_invocations": self.comparison_invocations,
            "actual_command_invocations": self.command_invocations,
            "actual_total_invocations": self.simulator_invocations + self.comparison_invocations,
            "retained_artifact_bytes_before_summary": self.budget.refresh(self.root),
            "elapsed_seconds": round(elapsed, 4),
            "cases": self.results,
        }
        (self.root / "results.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        fingerprints = {
            "schema_version": 1,
            "suite": "m4",
            "outputs": [
                {
                    "scenario": result["scenario_id"],
                    "seed": result["seed"],
                    "input_sha256": result["input_sha256"],
                    "calendar_sha256": result["external_calendar_sha256"],
                    "comparison_sha256": result["comparison_sha256"],
                    "repeat_output_sha256": result["repeat_output_sha256"],
                    "policy_metrics": result["metrics"],
                }
                for result in self.results
            ],
        }
        (self.root / "m4-fingerprints.json").write_text(
            json.dumps(fingerprints, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        retained = self.budget.refresh(self.root)
        if retained > int(self.plan["max_artifact_bytes"]):
            raise M4CampaignError("campaign exceeded its retained-artifact budget")
        summary["retained_artifact_bytes"] = retained
        (self.root / "results.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.budget.refresh(self.root)
        elapsed = time.monotonic() - (self.deadline - float(self.plan["time_budget_seconds"]))
        if elapsed > float(self.plan["time_budget_seconds"]):
            raise M4CampaignError("campaign exceeded its total time budget")
        print(json.dumps({"status": "passed", "campaign": str(self.root), "summary": summary}, indent=2))
        return self.root


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "target" / "release" / "vv-lab")
    parser.add_argument("--seeds", type=parse_seeds, default=DEFAULT_SEEDS)
    parser.add_argument("--max-pairs", type=int, default=MAX_PAIRS)
    parser.add_argument("--max-invocations", type=int, default=MAX_INVOCATIONS)
    parser.add_argument("--max-artifact-bytes", type=int, default=MAX_ARTIFACT_BYTES)
    parser.add_argument("--time-budget-seconds", type=float, default=MAX_TIME_BUDGET_SECONDS)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs")
    return parser


def main() -> int:
    arguments = make_parser().parse_args()
    try:
        plan = plan_campaign(
            arguments.seeds,
            max_invocations=arguments.max_invocations,
            max_pairs=arguments.max_pairs,
            max_artifact_bytes=arguments.max_artifact_bytes,
            time_budget_seconds=arguments.time_budget_seconds,
        )
        campaign = Campaign(arguments.binary, arguments.output_root, arguments.seeds, plan)
        campaign.run()
        return 0
    except (M4CampaignError, ProcessLimitError, OSError, ValueError) as error:
        print(f"M4 campaign failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
