"""Varrimento do instante de início das falhas do M10 (desenvolvimento): onde o tempo da falha dói mais.

A campanha sorteia as janelas; aqui o início é fixado numa grelha, para cada falha e semente de
desenvolvimento, e o resultado é a recuperação e a classe física por instante de início. É um
teste de tempo adverso limitado: o pior instante de cada falha, não uma estimativa de taxa.

Falhas e parâmetros fixos (dentro das gamas registadas em `docs/m10-implementation.md`):
`altimeter_stuck` 3 s, `altimeter_delay` 0,1 s, `gnss_coherent_ramp` 1 m/s, `gnss_dropout` 5 s,
`imu_accel_drift` 0,05 m/s² por s. Início de 2 a 20 s em passos de 1 s (o fim de uma falha com
duração fica limitado a 23 s, o limite das janelas da campanha).

Só sementes de desenvolvimento; as protegidas são recusadas antes de qualquer execução. Só usa a
biblioteca padrão.

Uso: python scripts/m10_onset_sweep.py --arms m10_b_plus --seeds 5000-5019 --output runs/m10-onset.json
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import m10_campaign as camp

FAULTS: dict[str, dict[str, Any]] = {
    "altimeter_stuck": {"duration_s": 3.0, "magnitude": 0.0},
    "altimeter_delay": {"duration_s": None, "magnitude": 0.1},
    "gnss_coherent_ramp": {"duration_s": None, "magnitude": 1.0},
    "gnss_dropout": {"duration_s": 5.0, "magnitude": 0.0},
    "imu_accel_drift": {"duration_s": None, "magnitude": 0.05},
}
ONSETS = tuple(float(t) for t in range(2, 21))
LATEST_END_S = 23.0
OPEN_END_S = 40.0
MAX_RUNS = 6000


def fault_at(kind: str, onset: float) -> dict[str, Any]:
    spec = FAULTS[kind]
    end = OPEN_END_S if spec["duration_s"] is None else min(onset + spec["duration_s"], LATEST_END_S)
    return {"kind": kind, "start_s": onset, "end_s": end, "magnitude": spec["magnitude"]}


def run_one(binary: Path, template: dict[str, Any], arm: str, kind: str, onset: float, seed: int,
            work: Path) -> dict[str, Any]:
    case = copy.deepcopy(template)
    case["name"] = f"m10 onset sweep {kind} {onset} {arm} {seed}"
    case["controller"]["policy"] = arm
    case["faults"] = [fault_at(kind, onset)]
    out = work / f"{arm}-{kind}-{onset}-{seed}"
    case_path = work / f"{arm}-{kind}-{onset}-{seed}.json"
    case_path.write_text(json.dumps(case), encoding="utf-8")
    proc = subprocess.run([str(binary), "land", str(case_path), "--seed", str(seed), "--output", str(out)],
                          capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode not in (0, 2):
        raise camp.M10CampaignError(f"{out.name}: vv-rocket land exited {proc.returncode}: {proc.stderr[:300]}")
    v = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    nav = v.get("navigation") or {}
    return {"arm": arm, "fault": kind, "onset_s": onset, "seed": seed,
            "recovery": v["outcome"] == "landed" and v["requirements_pass"] and v["invariants_pass"],
            "physical_class": nav.get("physical_class"), "isolation": nav.get("isolation"),
            "vertical_alert_failure": (nav.get("vertical") or {}).get("alert_failure")}


def summarise(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for arm in sorted({r["arm"] for r in records}):
        for kind in FAULTS:
            for onset in ONSETS:
                cell = [r for r in records if r["arm"] == arm and r["fault"] == kind and r["onset_s"] == onset]
                if not cell:
                    continue
                rows.append({"arm": arm, "fault": kind, "onset_s": onset, "runs": len(cell),
                             "recovered": sum(r["recovery"] for r in cell),
                             "R": sum(r["physical_class"] == "R" for r in cell),
                             "T": sum(r["physical_class"] == "T" for r in cell),
                             "U": sum(r["physical_class"] == "U" for r in cell),
                             "isolation_wrong": sum(r["isolation"] == "wrong" for r in cell),
                             "vertical_alert_failures": sum(bool(r["vertical_alert_failure"]) for r in cell)})
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="M10 fault-onset sweep on development seeds")
    p.add_argument("--arms", default="m10_b_plus")
    p.add_argument("--faults", default=",".join(FAULTS))
    p.add_argument("--seeds", default="5000-5019")
    p.add_argument("--template", type=Path, default=camp.TEMPLATE)
    p.add_argument("--binary", type=Path, default=camp.m9.binary_default())
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        seeds = camp.parse_seeds(args.seeds)
        if any(camp.protected(s) for s in seeds):
            raise camp.M10CampaignError("the onset sweep uses development seeds only; protected seeds refused")
        arms = [a for a in args.arms.split(",") if a]
        if any(a not in camp.M10_ARMS for a in arms):
            raise camp.M10CampaignError(f"arms must be M10 arms {camp.M10_ARMS} (the new faults need schema v2)")
        kinds = [k for k in args.faults.split(",") if k]
        if any(k not in FAULTS for k in kinds):
            raise camp.M10CampaignError(f"faults must be among {sorted(FAULTS)}")
        if not 1 <= args.jobs <= camp.MAX_JOBS:
            raise camp.M10CampaignError(f"--jobs must be in [1, {camp.MAX_JOBS}]")
        plan = [(a, k, t, s) for a in arms for k in kinds for t in ONSETS for s in seeds]
        if len(plan) > MAX_RUNS:
            raise camp.M10CampaignError(f"{len(plan)} runs above the limit {MAX_RUNS}")
        binary = args.binary.resolve()
        template, template_sha = camp.load_template(args.template)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="m10-onset-") as tmp:
            work = Path(tmp)
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                records = list(pool.map(lambda r: run_one(binary, template, *r, work), plan))
        result = {"schema": "vv-m10-onset-sweep.v1", "label": "development seeds; exploratory, not evaluation",
                  "command": "python scripts/m10_onset_sweep.py " + " ".join(argv),
                  "machine": camp.machine_description(), "duration_s": round(time.monotonic() - started, 1),
                  "binary_sha256": camp.sha256_file(binary), "template_sha256": template_sha,
                  "faults": {k: FAULTS[k] for k in kinds}, "onsets_s": list(ONSETS), "seeds": args.seeds,
                  "rows": summarise(records)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    except (camp.M10CampaignError, OSError, subprocess.TimeoutExpired) as error:
        print(f"M10 onset sweep failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"runs": len(records), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
