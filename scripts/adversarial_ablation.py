"""Ablação limitada das estratégias de pesquisa do `vv-adversary`.

Para cada base, semente de campanha e estratégia (`guided`, `biased`,
`uniform`) executa uma campanha com o mesmo orçamento e a mesma semente de
simulação, e resume `metrics.unique_classes_found` e
`metrics.violating_candidates`. O tempo é medido fora da simulação e fica
num bloco separado.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

from process_limits import ProcessLimitError, run_bounded_process

ROOT = Path(__file__).resolve().parents[1]
BASES = (
    ("nominal-stop", "scenarios/m3/nominal-stop.json"),
    ("x-first-overshoot", "scenarios/m4/x-first-overshoot.json"),
)
CONTRACTS = "scenarios/m3/contracts-nominal.json"
STRATEGIES = ("guided", "biased", "uniform")
SIM_SEED = 42
BUDGET = 32
MAX_FAILURES = 16
MAX_SEEDS = 20
MAX_TIME_SECONDS = 600
MAX_CAMPAIGN_JSON_BYTES = 16 * 1024 * 1024


def default_binary() -> Path:
    name = "vv-adversary.exe" if os.name == "nt" else "vv-adversary"
    return ROOT / "target" / "release" / name


def campaign_metrics(path: Path) -> tuple[int, int]:
    if path.stat().st_size > MAX_CAMPAIGN_JSON_BYTES:
        raise ValueError(f"{path} is too large")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "vv-adversary.campaign.v1":
        raise ValueError(f"{path} has an unexpected schema")
    metrics = document["metrics"]
    classes, violating = metrics["unique_classes_found"], metrics["violating_candidates"]
    if type(classes) is not int or type(violating) is not int:
        raise ValueError(f"{path} has invalid metrics")
    return classes, violating


def summarize(values: list[int]) -> dict[str, float | int]:
    return {"mean": round(statistics.mean(values), 3), "min": min(values), "max": max(values)}


def run(binary: Path, output_root: Path, seeds: int) -> dict:
    deadline = time.monotonic() + MAX_TIME_SECONDS
    rows: dict[str, dict[str, list[tuple[int, int]]]] = {}
    seconds: list[float] = []
    for base_name, base_path in BASES:
        for strategy in STRATEGIES:
            for seed in range(1, seeds + 1):
                output = output_root / base_name / strategy / f"seed-{seed}"
                command = [
                    str(binary), "campaign", "--base", base_path, "--contracts", CONTRACTS,
                    "--campaign-seed", str(seed), "--sim-seed", str(SIM_SEED),
                    "--budget", str(BUDGET), "--max-failures", str(MAX_FAILURES),
                    "--search", strategy, "--output", str(output),
                ]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProcessLimitError("ablation exceeded its time budget")
                started = time.perf_counter()
                process = run_bounded_process(
                    command, cwd=ROOT, timeout_seconds=remaining,
                    max_output_bytes=1024 * 1024, description=f"{base_name}/{strategy}/{seed}",
                )
                seconds.append(time.perf_counter() - started)
                if process.returncode != 0:
                    raise ProcessLimitError(f"campaign failed: {' '.join(command)}")
                rows.setdefault(base_name, {}).setdefault(strategy, []).append(
                    campaign_metrics(output / "campaign.json")
                )
    results = {
        base: {
            strategy: {
                "unique_classes_found": summarize([classes for classes, _ in values]),
                "violating_candidates": summarize([violating for _, violating in values]),
            }
            for strategy, values in strategies.items()
        }
        for base, strategies in rows.items()
    }
    return {
        "deterministic": {
            "seeds": list(range(1, seeds + 1)), "sim_seed": SIM_SEED, "budget": BUDGET,
            "max_failures": MAX_FAILURES, "contracts": CONTRACTS, "results": results,
        },
        "timing": {
            "machine": f"{platform.platform()}, Python {platform.python_version()}, {os.cpu_count()} CPUs",
            "campaigns": len(seconds), "total_seconds": round(sum(seconds), 3),
            "mean_seconds_per_campaign": round(statistics.mean(seconds), 4),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=default_binary())
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=MAX_SEEDS)
    args = parser.parse_args()
    if not 1 <= args.seeds <= MAX_SEEDS:
        parser.error(f"--seeds must be between 1 and {MAX_SEEDS}")
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        parser.error("--output-root must be empty or absent")
    if not args.binary.is_file():
        parser.error(f"binary not found: {args.binary}")
    try:
        summary = run(args.binary.resolve(), output_root, args.seeds)
    except (ProcessLimitError, ValueError, KeyError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    (output_root / "ablation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["deterministic"]["results"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
