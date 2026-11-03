"""M14: a falsifiable quantitative test of the masking mechanism found by the M13 investigation.

The M13 investigation of claim g3-onset supported this mechanism: after a late GNSS bias onset,
the guarded estimator blends the biased GNSS with an altimeter it still accepts, the residual stays
under the 3 m rejection threshold, the altimeter is never rejected and rule 1 never engages.

If that is the mechanism, a much simpler system must predict where it stops. This script models
only the vertical error of the estimator (estimate minus truth), with the gains of the M9.1 case
and nothing else: no vehicle, no noise, no guidance. It predicts

- P1, the critical bias b*: the smallest bias whose blended residual exceeds the rejection
  threshold, so that the altimeter is rejected and R1 should hold again;
- P2, the onset boundary: the altimeter is rejected only when the bias is already present at the
  first GNSS fix, which initialises the estimator; any later onset below b* is masked.

`predict` writes the prediction before any simulator run; `test` then runs the canonical simulator
on fresh development seeds and applies the criteria fixed in the prediction file.

    python scripts/m14_masking_model.py predict --output docs/evidence/m14/masking/prediction.json
    python scripts/m14_masking_model.py test --prediction docs/evidence/m14/masking/prediction.json \
        --vv-rocket crates/vv-rocket/target/release/vv-rocket --output-root <dir outside runs/>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "exec" / "cases" / "m13" / "g3-registered.json"
SEEDS = list(range(47000, 47020))  # M14 mechanism-prediction test: fresh development seeds.
MAGNITUDES = [10.0 + 0.25 * i for i in range(21)]  # 10 to 15 m
ONSETS = [0.0, 0.01, 0.02, 0.1, 1.0, 5.0, 10.0, 20.0]
LATE_ONSET = 5.0
ONSET_MAGNITUDE = 8.0
TOLERANCE_M = 1.0
FRACTION = 0.9


def model(bias: float, onset_s: float, g: dict, dt: float, gnss_every: int, cycles: int = 3000) -> dict:
    """Vertical error of the robust/guarded navigator (landing_controller.rs `update_robust`).

    e: position error, v: velocity error. The IMU is taken as perfect, so propagation only moves e
    by v * dt. A GNSS fix every `gnss_every` cycles pulls e towards the bias by the position gain
    and v towards 0 by the velocity gain. The altimeter residual is -e; while |residual| is within
    the threshold it corrects e and v, and after `altimeter_rejection_cycles` consecutive cycles
    outside it the altimeter is rejected (and readmitted when the residual returns inside)."""
    thr = g["altimeter_residual_threshold_m"]
    need = g["altimeter_rejection_cycles"]
    # Cycle 0 initialises the estimator on the first GNSS fix.
    e = bias if onset_s <= 0.0 else 0.0
    v = 0.0
    exceed = 0
    rejected_cycles = 0
    max_r = 0.0
    for k in range(1, cycles):
        t = k * dt
        b = bias if t >= onset_s else 0.0
        e += v * dt
        if k % gnss_every == 0:
            e += g["gnss_position_gain"] * (b - e)
            v += g["gnss_velocity_gain"] * (0.0 - v)
        r = -e
        max_r = max(max_r, abs(r))
        if abs(r) > thr:
            exceed += 1
            if exceed >= need:
                rejected_cycles += 1
        else:
            exceed = 0
            e += g["altimeter_position_gain"] * r
            v += g["altimeter_velocity_gain"] * r / dt
    return {"max_residual_m": max_r, "rejected_cycles": rejected_cycles, "final_e_m": e, "final_v_mps": v}


def case_parameters() -> tuple[dict, float, int]:
    c = json.loads(CASE.read_text(encoding="utf-8"))
    s = c["sensors"]
    dt = c["dt_s"] * s["control_period_steps"]
    return c["controller"]["gains"], dt, s["gnss_period_cycles"]


def predict(out: Path) -> dict:
    g, dt, every = case_parameters()
    # P1: bisection on the bias for a late onset.
    lo, hi = 0.0, 60.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if model(mid, LATE_ONSET, g, dt, every)["rejected_cycles"] > 0:
            hi = mid
        else:
            lo = mid
    b_star = hi
    p2 = {str(o): model(ONSET_MAGNITUDE, o, g, dt, every)["rejected_cycles"] > 0 for o in ONSETS}
    steady = model(ONSET_MAGNITUDE, LATE_ONSET, g, dt, every)
    pred = {
        "schema": "vv-m14-masking-prediction.v1",
        "case": str(CASE.relative_to(ROOT)).replace("\\", "/"),
        "case_sha256": hashlib.sha256(CASE.read_bytes()).hexdigest(),
        "model": "vertical estimator error only; perfect IMU; no noise, vehicle or guidance (see model())",
        "gains": {k: g[k] for k in ("gnss_position_gain", "gnss_velocity_gain", "altimeter_position_gain",
                                     "altimeter_velocity_gain", "altimeter_residual_threshold_m", "altimeter_rejection_cycles")},
        "control_cycle_s": dt,
        "gnss_every_cycles": every,
        "P1": {
            "statement": f"With the bias starting at {LATE_ONSET} s, the altimeter is rejected, and R1 holds again, only above b* m.",
            "b_star_m": b_star,
            "criterion": f"the simulator magnitude b50 at which R1 holds in half the runs lies within {TOLERANCE_M} m of b*",
        },
        "P2": {
            "statement": "With a bias of %.1f m, the altimeter is rejected only when the bias is present at the first GNSS fix (onset 0 s)." % ONSET_MAGNITUDE,
            "rejected_by_onset": p2,
            "criterion": f"R1 holds in at least {FRACTION:.0%} of runs where the model predicts rejection and fails in at least {FRACTION:.0%} where it predicts masking",
        },
        "steady_state_at_8m": steady,
        "test": {"seeds": [SEEDS[0], SEEDS[-1]], "magnitudes_m": MAGNITUDES, "late_onset_s": LATE_ONSET,
                 "onsets_s": ONSETS, "onset_magnitude_m": ONSET_MAGNITUDE},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pred, indent=2) + "\n", encoding="utf-8")
    return pred


def land(exe: Path, case: dict, seed: int, work: Path) -> dict:
    d = Path(tempfile.mkdtemp(dir=work))
    p = d / "case.json"
    p.write_text(json.dumps(case), encoding="utf-8")
    subprocess.run([str(exe), "land", str(p), "--seed", str(seed), "--output", str(d / "o")], capture_output=True, check=False)
    v = json.loads((d / "o" / "verification.json").read_text(encoding="utf-8"))
    t = json.loads((d / "o" / "trace.json").read_text(encoding="utf-8"))
    r1 = next(r for r in v["requirements"] if r["id"] == "R1_vertical_speed")
    rejected = any(s.get("estimate", {}).get("altimeter_rejected") for s in t["samples"])
    return {"r1_pass": r1["pass"] is True, "r1_mps": r1["value"], "rejected": rejected}


def test(pred_path: Path, exe: Path, root: Path) -> dict:
    if any(part.lower() == "runs" for part in root.resolve().parts):
        raise SystemExit("refusing an output under a runs directory")
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    base = json.loads(CASE.read_text(encoding="utf-8"))
    if hashlib.sha256(CASE.read_bytes()).hexdigest() != pred["case_sha256"]:
        raise SystemExit("the case changed since the prediction")
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=root))

    def cell(onset: float, mag: float) -> dict:
        c = json.loads(json.dumps(base))
        c["faults"][0]["start_s"] = onset
        c["faults"][0]["magnitude"] = mag
        runs = [land(exe, c, s, work) for s in SEEDS]
        return {"onset_s": onset, "magnitude_m": mag, "n": len(runs),
                "r1_holds": sum(r["r1_pass"] for r in runs), "rejected": sum(r["rejected"] for r in runs)}

    sweep = [cell(LATE_ONSET, m) for m in MAGNITUDES]
    # b50 by linear interpolation of the R1-holds fraction between grid points.
    b50 = None
    for a, b in zip(sweep, sweep[1:]):
        fa, fb = a["r1_holds"] / a["n"], b["r1_holds"] / b["n"]
        if fa < 0.5 <= fb:
            b50 = a["magnitude_m"] + (0.5 - fa) / (fb - fa) * (b["magnitude_m"] - a["magnitude_m"])
            break
    onsets = [cell(o, ONSET_MAGNITUDE) for o in ONSETS]
    p2_ok = []
    for o in onsets:
        rejected_pred = pred["P2"]["rejected_by_onset"][str(o["onset_s"])]
        frac_hold = o["r1_holds"] / o["n"]
        p2_ok.append(frac_hold >= FRACTION if rejected_pred else (1 - frac_hold) >= FRACTION)
    b_star = pred["P1"]["b_star_m"]
    result = {
        "schema": "vv-m14-masking-test.v1",
        "prediction_sha256": hashlib.sha256(pred_path.read_bytes()).hexdigest(),
        "simulator": str(exe.name),
        "seeds": [SEEDS[0], SEEDS[-1]],
        "magnitude_sweep": sweep,
        "onset_sweep": onsets,
        "P1": {"b_star_m": b_star, "b50_m": b50,
               "supported": b50 is not None and abs(b50 - b_star) <= TOLERANCE_M},
        "P2": {"per_onset": [dict(o, prediction_ok=ok) for o, ok in zip(onsets, p2_ok)],
               "supported": all(p2_ok)},
    }
    (root / "masking-test.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("predict")
    a.add_argument("--output", type=Path, required=True)
    b = sub.add_parser("test")
    b.add_argument("--prediction", type=Path, required=True)
    b.add_argument("--vv-rocket", type=Path, required=True)
    b.add_argument("--output-root", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "predict":
        p = predict(args.output)
        print(json.dumps({"b_star_m": p["P1"]["b_star_m"], "P2": p["P2"]["rejected_by_onset"],
                          "steady_state_at_8m": p["steady_state_at_8m"]}, indent=2))
    else:
        r = test(args.prediction, args.vv_rocket, args.output_root)
        print(json.dumps({"P1": r["P1"], "P2_supported": r["P2"]["supported"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
