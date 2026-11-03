"""Adversarial probes of M10 B+ on development seeds 5000-5099 only (independent review, 03/11/2026).

Each plan builds fault scenarios that the registered campaign grids do not cover (slow coherent
ramps near ignition, late GNSS dropouts with the bounded-chase variant, drift, mid-flight steps)
and records, per run, the physical class, the failed requirements and invariants, the isolation
verdict and the alert failures of the three navigation channels.

    python scripts/m10_adversarial_probe.py ignition --binary <vv-rocket> --output <file.json>
    python scripts/m10_adversarial_probe.py summary <file.json>

Plans: ignition, ramp, rampbase, steps, chase. Seeds default to 5000-5019. Any seed outside
5000-5099, any protected seed (scripts/m10_campaign.py) and 100-129 are refused before running.
The bounded-chase arm is the approved template with controller.nav.bounded_chase_when_untrusted
= true.
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m10_campaign as camp  # noqa: E402

DEV = range(5000, 5100)
MAX_PLAN = 6000
PLANS = ("ignition", "ramp", "rampbase", "steps", "chase")


def guard(seeds: list[int]) -> None:
    bad = [s for s in seeds if s not in DEV or camp.protected(s) or 100 <= s <= 129]
    if bad:
        raise SystemExit(f"refused non-development seeds {bad[:5]}")


def fault(kind: str, start: float, end: float, mag: float = 0.0) -> dict:
    return {"kind": kind, "start_s": float(start), "end_s": float(end), "magnitude": float(mag)}


def run(binary: Path, template: dict, arm: str, faults: list, seed: int, work: Path, tag: str) -> dict:
    case = copy.deepcopy(template)
    case["name"] = f"probe {tag} {arm} {seed}"
    case["controller"]["policy"] = arm
    case["faults"] = faults
    safe = tag.replace("~", "-").replace("@", "-").replace("+", "p")
    out = work / f"{safe}-{arm}-{seed}"
    path = work / f"{safe}-{arm}-{seed}.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    p = subprocess.run([str(binary), "land", str(path), "--seed", str(seed), "--output", str(out)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode not in (0, 2):
        raise RuntimeError(p.stderr[:300])
    v = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    nav = v.get("navigation") or {}
    reqs = {r["id"].split("_")[0]: r["pass"] for r in v["requirements"]}
    return {
        "tag": tag, "arm": arm, "seed": seed, "cls": nav.get("physical_class"),
        "outcome": v["outcome"], "fail": [k for k, ok in reqs.items() if not ok],
        "inv_fail": [i["id"] for i in v["invariants"] if not i["pass"]],
        "iso": nav.get("isolation"), "iso_ev": nav.get("isolation_events"),
        "af": {c: (nav.get(c) or {}).get("alert_failure")
               for c in ("vertical", "horizontal_velocity", "horizontal_position")},
        "vmax": (nav.get("vertical") or {}).get("max_error"),
        "hpmax": (nav.get("horizontal_position") or {}).get("max_error"),
        "unsafe_tr": nav.get("unsafe_transitions"),
    }


def jobs_for(plan: str) -> list[tuple[str, str, list, str]]:
    F = fault
    jobs: list[tuple[str, str, list, str]] = []
    if plan == "ignition":
        for k in range(0, 51):
            t = round(3.0 + 0.05 * k, 2)
            jobs += [("approved", "m10_b_plus", [F("altimeter_stuck", t, t + 3.0)], f"stuck@{t}"),
                     ("approved", "m10_b_plus", [F("altimeter_delay", t, 40, 0.1)], f"delay0.1@{t}"),
                     ("approved", "m10_b_plus", [F("altimeter_delay", t, 40, 0.2)], f"delay0.2@{t}"),
                     ("approved", "m10_b_plus", [F("gnss_coherent_ramp", t, 40, 0.5)], f"ramp0.5@{t}"),
                     ("approved", "m10_b_plus", [F("gnss_coherent_ramp", t, 40, 2.0)], f"ramp2@{t}")]
    elif plan == "ramp":
        for t in (6.0, 7.0, 8.0, 10.0, 12.0):
            for m in (0.1, 0.2, 0.3, 0.5, 0.8):
                jobs.append(("approved", "m10_b_plus", [F("gnss_coherent_ramp", t, 40, m)], f"ramp{m}@{t}"))
    elif plan == "rampbase":
        for arm in ("robust", "guarded", "m10_b", "m10_b_plus"):
            for t in (4.5, 6.0, 8.0, 10.0):
                for m in (0.3, 0.5):
                    jobs.append(("approved", arm, [F("gnss_coherent_ramp", t, 40, m)], f"ramp{m}@{t}"))
    elif plan == "steps":
        for arm in ("m10_b_plus", "m10_b", "guarded", "robust"):
            for t in (6.0, 10.0, 14.0):
                for m in (0.03, 0.1, 0.3):
                    jobs.append(("approved", arm, [F("altimeter_drift", t, 40, m)], f"drift{m}@{t}"))
                for m in (5.0, 15.0):
                    jobs.append(("approved", arm, [F("altimeter_bias", t, 40, m)], f"altstep{m}@{t}"))
                    jobs.append(("approved", arm, [F("gnss_bias", t, 40, m)], f"gnssstep{m}@{t}"))
    elif plan == "chase":
        for tpl in ("approved", "bounded"):
            for t in (8.0, 12.0, 14.0, 16.0, 18.0, 20.0):
                for d in (3.0, 6.0):
                    jobs.append((tpl, "m10_b_plus", [F("altimeter_bias", 0, 40, 10.0), F("gnss_dropout", t, t + d)], f"late_drop{t}+{d}"))
                    jobs.append((tpl, "m10_b_plus", [F("altimeter_dropout", t - 1, t + d + 1), F("gnss_dropout", t, t + d)], f"both_drop{t}+{d}"))
            for hb in (10.0, 25.0):
                jobs.append((tpl, "m10_b_plus", [F("altimeter_bias", 0, 40, 10.0), F("gnss_horizontal_bias", 8.0, 40, hb), F("gnss_dropout", 10.0, 16.0)], f"hbias{hb}+drop"))
            for m in (0.03, 0.1):
                jobs.append((tpl, "m10_b_plus", [F("altimeter_bias", 0, 40, 10.0), F("imu_accel_drift", 6.0, 40, m), F("gnss_dropout", 10.0, 18.0)], f"imudrift{m}+drop"))
            jobs.append((tpl, "m10_b_plus", [F("altimeter_stuck", 8.0, 12.0), F("gnss_dropout", 10.0, 16.0)], "stuck+drop"))
            jobs.append((tpl, "m10_b_plus", [F("gnss_coherent_ramp", 6.0, 40, 1.0), F("gnss_dropout", 12.0, 17.0)], "ramp+drop"))
        for t in (8.0, 12.0, 14.0, 16.0, 18.0, 20.0):
            for d in (3.0, 6.0):
                for arm in ("robust", "guarded"):
                    jobs.append(("approved", arm, [F("altimeter_bias", 0, 40, 10.0), F("gnss_dropout", t, t + d)], f"late_drop{t}+{d}"))
    return jobs


def physical_class(r: dict) -> str:
    if r["cls"]:
        return r["cls"]
    if r["outcome"] == "no_contact" or r["inv_fail"]:
        return "U"
    others = not any(k in r["fail"] for k in ("R1", "R2", "R3", "R4", "R6"))
    return ("R" if "R5" not in r["fail"] else "T") if others else "U"


def summary(path: Path) -> None:
    recs = json.loads(path.read_text(encoding="utf-8"))["records"]
    cells: dict = collections.defaultdict(collections.Counter)
    for r in recs:
        key = (r.get("tpl", ""), r["arm"], r["tag"].split("~")[-1].split("@")[0])
        c = cells[key]
        c["n"] += 1
        c[physical_class(r)] += 1
        c["wrong_isolation"] += r["iso"] == "wrong"
        for ch, name in (("vertical", "af_v"), ("horizontal_velocity", "af_hv"), ("horizontal_position", "af_hp")):
            c[name] += bool(r["af"][ch])
        c["invariant_failures"] += bool(r["inv_fail"])
    for key in sorted(cells):
        print(key, {k: v for k, v in cells[key].items() if v})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan", choices=PLANS + ("summary",))
    ap.add_argument("path", nargs="?", help="summary: the probe output to summarise")
    ap.add_argument("--binary", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--seeds", default="5000-5019")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    if a.plan == "summary":
        summary(Path(a.path))
        return 0
    if a.binary is None or a.output is None:
        ap.error("--binary and --output are required")
    seeds = camp.parse_seeds(a.seeds)
    guard(seeds)
    approved, _ = camp.load_template(ROOT / "crates/vv-rocket/landing/m10-nominal.json")
    bounded = copy.deepcopy(approved)
    bounded["controller"]["nav"]["bounded_chase_when_untrusted"] = True
    templates = {"approved": approved, "bounded": bounded}
    plan = [(j, s) for j in jobs_for(a.plan) for s in seeds]
    if len(plan) > MAX_PLAN:
        raise SystemExit(f"plan has {len(plan)} runs; the limit is {MAX_PLAN}")
    started = time.monotonic()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m10-probe-") as tmp:
        work = Path(tmp)

        def one(js):
            (tpl, arm, faults, tag), seed = js
            rec = run(a.binary, templates[tpl], arm, faults, seed, work, f"{tpl}~{tag}")
            rec["tpl"] = tpl
            return rec

        with ThreadPoolExecutor(max_workers=max(1, min(a.jobs, 16))) as pool:
            recs = list(pool.map(one, plan))
    a.output.write_text(json.dumps({"plan": a.plan, "seeds": a.seeds, "records": recs}, indent=0), encoding="utf-8")
    print(len(recs), "runs", round(time.monotonic() - started, 1), "s ->", a.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
