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
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SUBDIRS = ("runs", "boundary")
SCHEMA = "vv-m91-retrospective.v1"


def stored_runs(campaign: Path) -> list[Path]:
    found: list[Path] = []
    for sub in SUBDIRS:
        found.extend(p.parent for p in (campaign / sub).rglob("run.json"))
    return sorted(found)


def check_one(binary: Path, campaign: Path, run_dir: Path, scratch: Path, index: int) -> dict:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    stored_verification = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    case = json.loads((run_dir / "case.json").read_text(encoding="utf-8"))
    out = scratch / f"r{index:04d}"
    proc = subprocess.run(
        [str(binary), "land", str(run_dir / "case.json"), "--seed", str(manifest["seed"]),
         "--output", str(out)],
        capture_output=True, text=True, check=False,
    )
    entry = {
        "run": run_dir.relative_to(campaign).as_posix(),
        "seed": manifest["seed"],
        "policy": manifest["policy"],
        "faults": [f["kind"] for f in case["faults"]],
        "stored_outcome": stored_verification["outcome"],
        "exit_code": proc.returncode,
    }
    if proc.returncode not in (0, 2):
        entry.update(error=proc.stderr.strip()[:300], trace_identical=False, s5_pass=None)
        return entry
    entry["trace_identical"] = (
        (out / "trace.json").read_bytes() == (run_dir / "trace.json").read_bytes()
    )
    new = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    s5 = next(i for i in new["invariants"] if i["id"] == "S5_no_powered_ascent")
    entry.update(s5_pass=s5["pass"], s5_worst_m=s5["worst_value"], new_outcome=new["outcome"])
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--campaign", type=Path, default=Path("runs/m9-campaign"))
    ap.add_argument("--binary", type=Path, default=Path("crates/vv-rocket/target/release/vv-rocket"))
    ap.add_argument("--output", type=Path,
                    default=Path("runs/m91-retrospective/retrospective.json"))
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    runs = stored_runs(args.campaign)
    if not runs:
        print(f"no stored runs under {args.campaign}", file=sys.stderr)
        return 3
    with tempfile.TemporaryDirectory(prefix="m91-retro-") as tmp:
        scratch = Path(tmp)
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            entries = list(pool.map(
                lambda a: check_one(args.binary, args.campaign, a[1], scratch, a[0]),
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
        "campaign": args.campaign.as_posix(),
        "runs_checked": len(entries),
        "traces_identical": identical,
        "traces_different": [e["run"] for e in entries if not e["trace_identical"]],
        "s5_failures": sorted(failed_set),
        "s5_failure_count": len(failed_set),
        "predicted_s5_failures": sorted(predicted),
        "prediction_holds": failed_set == predicted and identical == len(entries),
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
