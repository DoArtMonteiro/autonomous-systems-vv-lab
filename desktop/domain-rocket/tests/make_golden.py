"""Generates the golden case files of the rocket domain host from the Python landing adapter.

The Rust test `golden_cases_match_the_python_adapter` builds the case of each request with the host
and asserts byte equality with the file written here by `LandingAdapter.case_for` and the canonical
writer of `LandingAdapter._execute` (sorted keys, compact separators).

Usage, from the repository root:  python desktop/domain-rocket/tests/make_golden.py
Rerun it only when the templates or the Python adapter change on purpose; the files are fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from landing_adapter import LandingAdapter, request_for_faults  # noqa: E402
from sim_adapter import _canonical  # noqa: E402

OUT = Path(__file__).resolve().parent / "golden"

SCENARIO = {"baseline": "m9-landing", "robust": "m9-landing", "guarded": "m91-landing",
            "baseline_guarded": "m91-landing", "m10_a": "m10-landing", "m10_b": "m10-landing",
            "m10_b_plus": "m10-landing"}


def fault(kind, start, end, magnitude=None):
    return {"kind": kind, "magnitude": magnitude, "start": start, "end": end}


# id, policy, seed, faults (desktop form: magnitude None when the fault takes none)
REQUESTS = [
    ("m9-nominal-baseline", "baseline", 42, []),
    ("m9-nominal-seed0", "robust", 0, []),
    ("m9-thrust-loss-robust", "robust", 5000, [fault("thrust_loss", 5.26, 40.0, 0.15)]),
    ("m9-gimbal-stuck-baseline", "baseline", 1000, [fault("gimbal_stuck", 10.0, 12.0)]),
    ("m9-two-faults", "baseline", 5001, [fault("altimeter_dropout", 18.0, 24.0), fault("gnss_bias", 8.0, 40.0, 15.0)]),
    ("m9-odd-numbers", "robust", 4294967295, [fault("altimeter_bias", 3.07, 7.31, 12.3456)]),
    ("m91-guarded-bias-low", "guarded", 7, [fault("altimeter_bias_low", 10.0, 40.0, 27.5)]),
    ("m91-baseline-guarded-dropout", "baseline_guarded", 5002, [fault("gnss_dropout", 8.0, 14.0)]),
    ("m10-nominal-b-plus", "m10_b_plus", 5000, []),
    ("m10-altimeter-stuck-b-plus", "m10_b_plus", 5000, [fault("altimeter_stuck", 8.0, 12.0)]),
    ("m10-bias-plus-dropout-a", "m10_a", 5000,
     [fault("altimeter_bias", 0.0, 40.0, 20.0), fault("gnss_dropout", 8.0, 14.0)]),
    ("m10-ramp-plus-drift-b", "m10_b", 5003,
     [fault("gnss_coherent_ramp", 8.0, 40.0, 1.0), fault("imu_accel_drift", 6.0, 40.0, 0.05)]),
    ("m10-outliers-b-plus", "m10_b_plus", 5004, [fault("altimeter_outliers", 0.0, 40.0, 0.005)]),
]


def main() -> None:
    adapter = LandingAdapter(binary=None, root=ROOT)
    OUT.mkdir(exist_ok=True)
    for name, policy, seed, faults in REQUESTS:
        python_faults = [{"kind": f["kind"], "magnitude": f["magnitude"] if f["magnitude"] is not None else 0,
                          "start_s": f["start"], "end_s": f["end"]} for f in faults]
        validated = adapter.validate(request_for_faults(policy, seed, python_faults))
        case = adapter.case_for(validated)
        request = {"schema": "vv-run-request.v1", "domain": "rocket-landing", "scenario": SCENARIO[policy],
                   "controller": policy, "seed": seed, "faults": faults, "parameters": {}}
        (OUT / f"{name}.request.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        (OUT / f"{name}.case.json").write_bytes(_canonical(case))
        print(name, len(_canonical(case)), "bytes")


if __name__ == "__main__":
    main()
