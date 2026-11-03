"""Generates the golden case files of the rocket domain host from the Python landing adapter.

The Rust test `golden_cases_match_the_python_adapter` builds the case of each request with the host
and asserts byte equality with the file written here by `LandingAdapter.case_for` and the canonical
writer of `LandingAdapter._execute` (sorted keys, compact separators).

Usage, from the repository root:  python desktop/domain-rocket/tests/make_golden.py
Rerun it only when the templates or the Python adapter change on purpose; the files are fixtures.

The adapter takes at most one fault per request. `m9-two-faults` is a fixture kept from a two-fault
adapter: the host and `vv-rocket` accept two faults, and the host test checks those bytes, but this
script cannot regenerate them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from landing_adapter import LandingAdapter, request_for  # noqa: E402
from sim_adapter import _canonical  # noqa: E402

OUT = Path(__file__).resolve().parent / "golden"

SCENARIO = {"baseline": "m9-landing", "robust": "m9-landing", "guarded": "m91-landing",
            "baseline_guarded": "m91-landing"}


def fault(kind, start, end, magnitude=None):
    return {"kind": kind, "magnitude": magnitude, "start": start, "end": end}


# id, policy, seed, faults (desktop form: magnitude None when the fault takes none)
REQUESTS = [
    ("m9-nominal-baseline", "baseline", 42, []),
    ("m9-nominal-seed0", "robust", 0, []),
    ("m9-thrust-loss-robust", "robust", 5000, [fault("thrust_loss", 5.26, 40.0, 0.15)]),
    ("m9-gimbal-stuck-baseline", "baseline", 1000, [fault("gimbal_stuck", 10.0, 12.0)]),
    ("m9-odd-numbers", "robust", 4294967295, [fault("altimeter_bias", 3.07, 7.31, 12.3456)]),
    ("m91-guarded-bias-low", "guarded", 7, [fault("altimeter_bias_low", 10.0, 40.0, 27.5)]),
    ("m91-baseline-guarded-dropout", "baseline_guarded", 5002, [fault("gnss_dropout", 8.0, 14.0)]),
]


def main() -> None:
    adapter = LandingAdapter(binary=None, root=ROOT)
    OUT.mkdir(exist_ok=True)
    for name, policy, seed, faults in REQUESTS:
        python_faults = [{"kind": f["kind"], "magnitude": f["magnitude"] if f["magnitude"] is not None else 0,
                          "start_s": f["start"], "end_s": f["end"]} for f in faults]
        validated = adapter.validate(request_for(policy, seed, python_faults[0] if python_faults else None))
        case = adapter.case_for(validated)
        request = {"schema": "vv-run-request.v1", "domain": "rocket-landing", "scenario": SCENARIO[policy],
                   "controller": policy, "seed": seed, "faults": faults, "parameters": {}}
        (OUT / f"{name}.request.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        (OUT / f"{name}.case.json").write_bytes(_canonical(case))
        print(name, len(_canonical(case)), "bytes")


if __name__ == "__main__":
    main()
