"""Build the M13 Discovery Lab base cases from the canonical M9.1 landing case.

Each case is `crates/vv-rocket/landing/m91-nominal.json` (policy `guarded`) with a name and one
fault. The source is read, never changed; its sha256 and the fault of every case are recorded in
`exec/cases/m13/sources.json`. The claim base case `g3-registered` reproduces the registered G3
condition of M9.1 (docs/m9-powered-landing.md: `gnss_bias` over the whole flight, from 0 s); its
magnitude, 15 m, is the centre of the registered range [5, 30] m, which the claim varies.

    python scripts/m13_cases.py            # writes exec/cases/m13/*.json
    python scripts/m13_cases.py --check    # fails if a written case differs from its source
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exec" / "cases" / "m13"
SOURCE = "crates/vv-rocket/landing/m91-nominal.json"

# name: (case name, fault kind, magnitude, start_s, end_s)
CASES: dict[str, tuple[str, str, float, float, float]] = {
    "g3-registered": ("M13 G3 registered condition: gnss_bias from 0 s, guarded", "gnss_bias", 15.0, 0.0, 40.0),
    "family-gnss-bias-low": ("M13 regression family: gnss_bias_low, guarded", "gnss_bias_low", 15.0, 5.0, 40.0),
    "family-altimeter-bias": ("M13 regression family: altimeter_bias, guarded", "altimeter_bias", 20.0, 5.0, 40.0),
    "family-altimeter-bias-low": ("M13 regression family: altimeter_bias_low, guarded", "altimeter_bias_low", 20.0, 5.0, 40.0),
    "family-gnss-dropout": ("M13 regression family: gnss_dropout, guarded", "gnss_dropout", 0.0, 10.0, 16.0),
    "family-altimeter-dropout": ("M13 regression family: altimeter_dropout, guarded", "altimeter_dropout", 0.0, 10.0, 16.0),
    "family-imu-accel-bias": ("M13 regression family: imu_accel_bias, guarded", "imu_accel_bias", 0.2, 0.0, 40.0),
    "family-thrust-loss": ("M13 regression family: thrust_loss, guarded", "thrust_loss", 0.15, 5.26, 40.0),
}

# Cases with more than one fault: name to (case name, [(kind, magnitude, start_s, end_s), ...]).
# The small net GNSS bias family adds gnss_bias and gnss_bias_low (5 m each) from 5 s, so the
# net bias is (gnss_bias - 5) m and can go below the 5 m floor of a single gnss_bias.
MULTI: dict[str, tuple[str, list[tuple[str, float, float, float]]]] = {
    "family-small-net-gnss-bias": (
        "M13 regression family: small net GNSS bias, guarded",
        [("gnss_bias", 7.0, 5.0, 40.0), ("gnss_bias_low", 5.0, 5.0, 40.0)],
    ),
}


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")


def build() -> tuple[dict[str, bytes], dict[str, object]]:
    raw = (ROOT / SOURCE).read_bytes()
    source = json.loads(raw)
    cases: dict[str, bytes] = {}
    record: dict[str, object] = {"source": SOURCE, "source_sha256": hashlib.sha256(raw).hexdigest(), "cases": {}}
    for name, (title, kind, magnitude, start, end) in CASES.items():
        case = copy.deepcopy(source)
        case["name"] = title
        case["faults"] = [{"kind": kind, "start_s": start, "end_s": end, "magnitude": magnitude}]
        data = canonical(case)
        cases[name] = data
        record["cases"][name] = {
            "fault": case["faults"][0],
            "case_sha256": hashlib.sha256(data).hexdigest(),
        }
    for name, (title, faults) in MULTI.items():
        case = copy.deepcopy(source)
        case["name"] = title
        case["faults"] = [{"kind": k, "start_s": a, "end_s": b, "magnitude": m} for k, m, a, b in faults]
        data = canonical(case)
        cases[name] = data
        record["cases"][name] = {"faults": case["faults"], "case_sha256": hashlib.sha256(data).hexdigest()}
    return cases, record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    cases, record = build()
    files = {f"{name}.json": data for name, data in cases.items()}
    files["sources.json"] = canonical(record)
    if args.check:
        bad = [n for n, d in files.items() if not (OUT / n).exists() or (OUT / n).read_bytes() != d]
        if bad:
            print("m13 cases differ from their source: " + ", ".join(sorted(bad)), file=sys.stderr)
            return 1
        print(f"m13 cases: {len(files)} files match their source")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
    print(f"wrote {len(files)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
