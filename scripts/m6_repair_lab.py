"""Run the M6 controller repair experiment end to end and write the report.

Steps, all bounded by time, invocation count and retained bytes:

1. `vv-repair run` into `<root>/run` and again into `<root>/repeat`; every file
   must have the same sha256 in both trees.
2. `vv-repair replay <root>/run`: regenerates the evidence from the stored inputs
   and requires the same bytes.
3. `vv-lab replay-m4` on every reduced case (`cases/**/m4.json`).
4. `m6_analysis.analyze` writes `analysis.json` (deterministic for a given
   Python version); `m6_report.render` writes `report.html`.
5. `summary.json` holds the checks and the wall times, which are measured with
   `time.perf_counter` outside the simulation and never enter the evidence.

Exit status: 0 all checks passed, 1 a check failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any

from adversarial_campaign import compare_trees, default_binary, write_json
from m6_analysis import analyze
from m6_report import render
from process_limits import ProcessLimitError, ensure_tree_size, run_bounded_process

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPERIMENT = ROOT / "scenarios" / "m6" / "experiment.json"
SUMMARY_SCHEMA = "vv-repair.lab-summary.v1"
EVIDENCE_SCHEMA = "vv-repair.evidence.v1"
MAX_INVOCATIONS = 200
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
OUTPUT_LIMIT_BYTES = 1024 * 1024
TIMING = re.compile(r"^config_elapsed_ms (\w+)=(\d+)\s*$", re.MULTILINE)


class LabError(RuntimeError):
    """A check failed or a limit was exceeded."""


def display_path(path: Path) -> str:
    """Repository-relative path for the report; never a personal absolute path."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "<output-root>/" + path.name


def check_evidence(evidence: dict[str, Any]) -> None:
    """Fail closed on the properties the report relies on."""
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise LabError("evidence.json has an unexpected schema")
    if evidence["totals"]["unidentified_violations"]:
        raise LabError("the run produced violations without an identity")
    disagree = [i["id"] for i in evidence["corpus"] + evidence["introduced"] if i["recheck"]["result"] == "disagree"]
    if disagree:
        raise LabError(f"independent recheck disagrees with the monitor on {disagree}")


class Lab:
    def __init__(self, args: argparse.Namespace) -> None:
        self.binary = Path(args.binary).resolve()
        self.lab_binary = Path(args.lab_binary).resolve()
        self.experiment = Path(args.experiment).resolve()
        self.root = Path(args.output_root).resolve()
        self.deadline = time.monotonic() + args.time_budget_seconds
        self.max_bytes = args.max_artifact_bytes
        self.invocations = 0
        self.seconds: dict[str, float] = {}

    def invoke(self, command: list[str], label: str) -> str:
        if self.invocations >= MAX_INVOCATIONS:
            raise LabError("the lab would exceed its invocation budget")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise LabError("the lab exceeded its time budget")
        started = time.perf_counter()
        try:
            process = run_bounded_process(
                command, cwd=ROOT, timeout_seconds=remaining, max_output_bytes=OUTPUT_LIMIT_BYTES, description=label
            )
        except ProcessLimitError as error:
            raise LabError(str(error)) from error
        self.invocations += 1
        self.seconds[label] = round(self.seconds.get(label, 0.0) + time.perf_counter() - started, 3)
        if process.returncode != 0:
            raise LabError(f"{label} failed with {process.returncode}: {process.stderr.strip()[-400:]}")
        return process.stdout + process.stderr

    def generate(self, output: Path, label: str) -> str:
        command = [str(self.binary), "run", "--experiment", str(self.experiment), "--output", str(output)]
        log = self.invoke(command, label)
        ensure_tree_size(self.root, self.max_bytes, "M6 artifacts")
        return log

    def run(self) -> dict[str, Any]:
        if self.root.exists() and any(self.root.iterdir()):
            raise LabError(f"output root {self.root} must be empty or absent")
        self.root.mkdir(parents=True, exist_ok=True)
        run_dir, repeat_dir = self.root / "run", self.root / "repeat"
        first = self.generate(run_dir, "vv-repair run")
        self.generate(repeat_dir, "vv-repair repeat")
        determinism = compare_trees(run_dir, repeat_dir)
        if determinism["difference_count"]:
            raise LabError(f"run and repeat differ: {determinism['differences'][:3]}")
        replay_log = self.invoke([str(self.binary), "replay", str(run_dir)], "vv-repair replay")
        replayed = replay_log.split(" vv-repair run:")[0].strip().removeprefix("vv-repair replay: ")
        cases = sorted((run_dir / "cases").rglob("m4.json"))
        for case in cases:
            self.invoke([str(self.lab_binary), "replay-m4", str(case)], "vv-lab replay-m4")

        evidence_path = run_dir / "evidence.json"
        if evidence_path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise LabError("evidence.json exceeds the read limit")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        check_evidence(evidence)
        analysis = analyze(evidence)
        write_json(self.root / "analysis.json", analysis)

        timing = {name: int(ms) for name, ms in TIMING.findall(first)}
        checks = {
            "run and repeat byte-identical": f"{determinism['files_identical']} of {determinism['files_total']} files",
            "vv-repair replay": replayed,
            "vv-lab replay-m4 on reduced cases": f"{len(cases)} of {len(cases)} OK",
            "independent recheck disagreements": 0,
            "unidentified violations": 0,
        }
        machine = f"{platform.system()} {platform.release()}, Python {platform.python_version()}, {os.cpu_count()} CPUs"
        run_block = {
            "run_dir": display_path(run_dir),
            "output_root": display_path(self.root),
            "experiment": display_path(self.experiment),
            "timing_ms": timing,
            "checks": checks,
            "machine": machine,
        }
        (self.root / "report.html").write_text(render(evidence, analysis, run_block), encoding="utf-8", newline="\n")
        summary = {
            "schema": SUMMARY_SCHEMA,
            "evidence_sha256": evidence["evidence_sha256"],
            "source_sha256": evidence["source_sha256"],
            "checks": checks,
            "determinism": determinism,
            "decisions": {c["id"]: c["verdict"] for c in analysis["candidates"]},
            "timing": {"machine": machine, "config_elapsed_ms": timing, "subprocess_seconds": self.seconds},
            "invocations": self.invocations,
        }
        write_json(self.root / "summary.json", summary)
        ensure_tree_size(self.root, self.max_bytes, "M6 artifacts")
        return summary


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--binary", default=str(default_binary("vv-repair")))
    parser.add_argument("--lab-binary", default=str(default_binary("vv-lab")))
    parser.add_argument("--experiment", default=str(DEFAULT_EXPERIMENT))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--time-budget-seconds", type=float, default=300.0)
    parser.add_argument("--max-artifact-bytes", type=int, default=256 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if not 0 < args.time_budget_seconds <= 900 or not 65_536 <= args.max_artifact_bytes <= 1024**3:
        print("error: time budget must be in (0, 900] s and the byte limit in [64 KiB, 1 GiB]", file=sys.stderr)
        return 2
    try:
        summary = Lab(args).run()
    except (LabError, ProcessLimitError, OSError, ValueError, KeyError) as error:
        print(f"M6 lab FAILED: {error}", file=sys.stderr)
        return 1
    for name, verdict in summary["decisions"].items():
        print(f"{name}: {verdict['decision']} (safety {verdict['safety']}, progress {verdict['progress']})")
    print(f"evidence_sha256={summary['evidence_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
