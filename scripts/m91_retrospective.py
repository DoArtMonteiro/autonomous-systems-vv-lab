"""M9.1 retrospective check P1 (docs/m9-powered-landing.md).

Re-runs every stored M9 campaign execution with the current `vv-rocket` binary, from the stored
`case.json` and the seed in `run.json`, into a temporary directory. For each run it compares the new
`trace.json` with the stored one byte for byte and reads `S5_no_powered_ascent` from the new
`verification.json`. The stored campaign is never modified.

Prediction P1: all traces identical, and S5 fails exactly in the `no_contact` executions of the
`baseline` policy with `gnss_dropout`.

    python scripts/m91_retrospective.py [--campaign runs/m9-campaign] \
        [--binary crates/vv-rocket/target/release/vv-rocket] \
        [--output runs/m91-retrospective/retrospective.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import m9_campaign as m9
from process_limits import ProcessLimitError, run_bounded_process

SUBDIRS = ("runs", "boundary")
SCHEMA = "vv-m91-retrospective.v2"


def stored_runs(campaign: Path) -> list[Path]:
    found: list[Path] = []
    for sub in SUBDIRS:
        found.extend(p.parent for p in (campaign / sub).rglob("run.json"))
    return sorted(found)


def check_one(
    binary: Path, campaign: Path, run_dir: Path, scratch: Path, index: int, deadline: float
) -> dict:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    stored_verification = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    case = json.loads((run_dir / "case.json").read_text(encoding="utf-8"))
    out = scratch / f"r{index:04d}"
    entry = {
        "run": run_dir.relative_to(campaign).as_posix(),
        "seed": manifest["seed"],
        "policy": manifest["policy"],
        "faults": [f["kind"] for f in case["faults"]],
        "stored_outcome": stored_verification["outcome"],
    }
    try:
        proc = run_bounded_process(
            [str(binary), "land", str(run_dir / "case.json"), "--seed", str(manifest["seed"]),
             "--output", str(out)],
            cwd=m9.ROOT,
            timeout_seconds=deadline - time.monotonic(),
            max_output_bytes=m9.OUTPUT_LIMIT_BYTES,
            description=f"land {entry['run']}",
        )
    except ProcessLimitError as error:
        entry.update(exit_code=None, error=str(error)[:300], trace_identical=False, s5_pass=None)
        return entry
    entry["exit_code"] = proc.returncode
    if proc.returncode not in (0, 2):
        entry.update(error=proc.stderr.strip()[:300], trace_identical=False, s5_pass=None)
        return entry
    entry["trace_identical"] = (
        (out / "trace.json").read_bytes() == (run_dir / "trace.json").read_bytes()
    )
    new = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    s5 = next(i for i in new["invariants"] if i["id"] == "S5_no_powered_ascent")
    entry["source_sha256"] = json.loads((out / "run.json").read_text(encoding="utf-8")).get(
        "source_sha256")
    entry.update(s5_pass=s5["pass"], s5_worst_m=s5["worst_value"], new_outcome=new["outcome"])
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--campaign", type=Path, default=Path("runs/m9-campaign"))
    ap.add_argument("--binary", type=Path, default=m9.binary_default())
    ap.add_argument("--output", type=Path,
                    default=Path("runs/m91-retrospective/retrospective.json"))
    ap.add_argument("--jobs", type=int, default=m9.DEFAULT_JOBS)
    ap.add_argument("--max-runs", type=int, default=m9.DEFAULT_MAX_RUNS)
    ap.add_argument("--time-budget-seconds", type=float, default=m9.DEFAULT_TIME_BUDGET_SECONDS)
    args = ap.parse_args()
    if not 1 <= args.jobs <= m9.MAX_JOBS:
        ap.error(f"--jobs must be between 1 and {m9.MAX_JOBS}")
    if not 1 <= args.max_runs <= m9.MAX_RUNS:
        ap.error(f"--max-runs must be between 1 and {m9.MAX_RUNS}")
    if not 0 < args.time_budget_seconds <= m9.MAX_TIME_BUDGET_SECONDS:
        ap.error(f"--time-budget-seconds must be above zero and at most {m9.MAX_TIME_BUDGET_SECONDS}")
    if not args.binary.is_file() and args.binary.with_name(args.binary.name + ".exe").is_file():
        # The documented command names the binary without the Windows suffix.
        args.binary = args.binary.with_name(args.binary.name + ".exe")
    if not args.binary.is_file():
        print(f"vv-rocket binary does not exist: {args.binary}", file=sys.stderr)
        return 3

    runs = stored_runs(args.campaign)
    if not runs:
        print(f"no stored runs under {args.campaign}", file=sys.stderr)
        return 3
    if len(runs) > args.max_runs:
        print(f"{len(runs)} stored runs exceed --max-runs {args.max_runs}", file=sys.stderr)
        return 3
    started = time.monotonic()
    deadline = started + args.time_budget_seconds
    with tempfile.TemporaryDirectory(prefix="m91-retro-") as tmp:
        scratch = Path(tmp)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            entries = list(pool.map(
                lambda a: check_one(args.binary, args.campaign, a[1], scratch, a[0], deadline),
                enumerate(runs)))

    identical = sum(1 for e in entries if e["trace_identical"])
    s5_failures = [e for e in entries if e["s5_pass"] is False]
    predicted = {
        e["run"] for e in entries
        if e["policy"] == "baseline" and "gnss_dropout" in e["faults"]
        and e["stored_outcome"] == "no_contact"
    }
    failed_set = {e["run"] for e in s5_failures}
    result = {
        "schema": SCHEMA,
        "binary_sha256": m9.sha256_file(args.binary),
        "source_sha256": sorted({e["source_sha256"] for e in entries if "source_sha256" in e}),
        "machine": m9.machine_description(),
        "command": "python scripts/m91_retrospective.py " + " ".join([
            f"--campaign {m9.relative_text(args.campaign)}",
            f"--binary {m9.relative_text(args.binary)}",
            f"--output {m9.relative_text(args.output)}",
            f"--jobs {args.jobs}", f"--max-runs {args.max_runs}",
            f"--time-budget-seconds {args.time_budget_seconds:g}"]),
        "duration_s": round(time.monotonic() - started, 1),
        "campaign": args.campaign.as_posix(),
        "runs_checked": len(entries),
        "traces_identical": identical,
        "traces_different": [e["run"] for e in entries if not e["trace_identical"]],
        "s5_failures": sorted(failed_set),
        "s5_failure_count": len(failed_set),
        "predicted_s5_failures": sorted(predicted),
        "prediction_holds": (
            failed_set == predicted and identical == len(entries)
            and not any("error" in e for e in entries)),
        "s5_failures_detail": [
            {k: e[k] for k in ("run", "policy", "faults", "stored_outcome", "new_outcome",
                               "s5_worst_m")}
            for e in s5_failures
        ],
        "errors": [e for e in entries if "error" in e],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"runs {result['runs_checked']}, identical traces {identical}, "
          f"S5 failures {len(failed_set)}, prediction holds: {result['prediction_holds']}")
    return 0 if result["prediction_holds"] else 1


if __name__ == "__main__":
    sys.exit(main())
