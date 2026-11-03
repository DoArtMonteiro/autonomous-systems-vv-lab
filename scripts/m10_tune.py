"""Afinação do M10 com o mesmo protocolo para todos os braços (docs/m10-resilient-navigation.md, 10.4).

Protocolo, igual para A, B e B+ (e C, se existir):

- sementes de desenvolvimento 5000 a 5099 e as 11 células de F1;
- métrica: média, sobre as células de F1, da taxa de recuperação (`landed` com `S1` a `S5`), sob a
  restrição de no máximo 2 de 100 execuções nominais com degradação espúria;
- orçamento: 30 avaliações por braço. A avaliação 0 é a configuração de partida (o modelo de caso
  atual); as restantes são sorteadas sem repetição, por pesquisa aleatória com o gerador
  `random.Random(search_seed * 1000 + índice do braço)`, sobre os espaços de `SPACES`;
- a melhor avaliação admissível ganha; em empate fica a de índice menor (a de partida primeiro).

Cada avaliação corre `scripts/m10_campaign.py --scenarios F1 --arms <braço> --template <variante>`
numa pasta própria e guarda só `summary.json`; o manifesto `tuning.json` regista os espaços, o
gerador, cada avaliação, o SHA-256 do binário e do modelo de partida, o comando e a máquina. As
sementes protegidas são recusadas antes de qualquer execução.

Uso: python scripts/m10_tune.py --arm m10_b --output-root runs/m10-tune-b
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import m10_campaign as camp

ROOT = Path(__file__).resolve().parents[1]
BUDGET = 30
MAX_SPURIOUS_NOMINAL = 2
ARM_INDEX = {"m10_a": 0, "m10_b": 1, "m10_b_plus": 2}
# Espaços de pesquisa por braço (parâmetros de `controller.nav`). Os partilhados aparecem em todos
# os braços que os usam; A não tem estado de viés nem CUSUM, B não tem CUSUM.
SHARED = {
    "gnss_readmission_epochs": [2, 3, 5, 10],
    "readmission_samples": [5, 10, 20],
    "t_hold_s": [1.0, 2.0, 3.0],
}
FILTER = {
    "bias_walk_sigma_mps2_per_sqrt_s": [0.002, 0.01, 0.03, 0.1],
    "accel_process_sigma_mps2": [0.05, 0.1, 0.2],
}
SPACES: dict[str, dict[str, list[Any]]] = {
    "m10_a": {**SHARED, "vote_threshold_m": [2.0, 3.0, 5.0, 8.0], "readmission_sigma": [2.0, 3.0, 4.0]},
    "m10_b": {**SHARED, **FILTER, "nis_reject": [10.83, 15.14, 19.51, 23.93]},
    "m10_b_plus": {**SHARED, **FILTER, "cusum_h": [8.0, 10.0, 12.0, 15.0], "cusum_k": [0.25, 0.5, 0.75],
                   "suspect_cusum_fraction": [0.75, 1.0]},
}


class TuneError(ValueError):
    pass


def draws(arm: str, start: dict[str, Any], search_seed: int, budget: int = BUDGET) -> list[dict[str, Any]]:
    """Avaliação 0: a configuração de partida; depois `budget - 1` pontos distintos sorteados da grelha."""
    space = SPACES[arm]
    names = sorted(space)
    first = {n: start[n] for n in names}
    grid = [dict(zip(names, values)) for values in itertools.product(*(space[n] for n in names))]
    rest = [g for g in grid if g != first]
    rng = random.Random(search_seed * 1000 + ARM_INDEX[arm])
    return [first] + rng.sample(rest, min(budget - 1, len(rest)))


def metric(summary: dict[str, Any]) -> tuple[float, int, dict[str, int]]:
    cells = {c["scenario"]: c for c in summary["cells"]}
    missing = [s for s in camp.FAMILIES["F1"] if s not in cells]
    if missing:
        raise TuneError(f"campaign summary misses F1 cells {missing}")
    per_cell = {s: cells[s]["recovered"] for s in camp.FAMILIES["F1"]}
    mean = sum(per_cell[s] / cells[s]["runs"] for s in per_cell) / len(per_cell)
    spurious = cells[camp.NOMINAL]["navigation"]["spurious_degradation_runs"]
    return mean, spurious, per_cell


def run_eval(args: argparse.Namespace, template: dict[str, Any], params: dict[str, Any], k: int) -> dict[str, Any]:
    out = args.output_root / f"eval-{k:02d}"
    out.mkdir(parents=True)
    variant = json.loads(json.dumps(template))
    variant["controller"]["nav"].update(params)
    tpl = out / "template.json"
    tpl.write_text(json.dumps(variant, indent=2) + "\n", encoding="utf-8", newline="\n")
    campaign_root = out / "campaign"
    cmd = [sys.executable, str(ROOT / "scripts" / "m10_campaign.py"), "--binary", str(args.binary),
           "--seeds", args.seeds, "--scenarios", "F1", "--arms", args.arm, "--template", str(tpl),
           "--jobs", str(args.jobs), "--keep-sample", "1", "--keep-failures", "0",
           "--output-root", str(campaign_root)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, check=False)
    if proc.returncode != 0:
        raise TuneError(f"evaluation {k} failed: {proc.stderr.strip()[:400]}")
    summary = json.loads((campaign_root / "summary.json").read_text(encoding="utf-8"))
    shutil.copyfile(campaign_root / "summary.json", out / "summary.json")
    shutil.rmtree(campaign_root)
    mean, spurious, per_cell = metric(summary)
    return {"index": k, "params": params, "mean_recovery": mean, "nominal_spurious_runs": spurious,
            "feasible": spurious <= MAX_SPURIOUS_NOMINAL, "recovered_per_cell": per_cell,
            "template_sha256": hashlib.sha256(tpl.read_bytes()).hexdigest(), "replay": summary["replay"]}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="M10 tuning with the same protocol for every arm (10.4)")
    p.add_argument("--arm", required=True, choices=sorted(SPACES))
    p.add_argument("--search-seed", type=int, default=10)
    p.add_argument("--budget", type=int, default=BUDGET)
    p.add_argument("--seeds", default="5000-5099")
    p.add_argument("--template", type=Path, default=camp.TEMPLATE)
    p.add_argument("--binary", type=Path, default=camp.m9.binary_default())
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--output-root", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        seeds = camp.parse_seeds(args.seeds)
        if any(camp.protected(s) for s in seeds):
            raise TuneError("tuning uses development seeds only; protected seeds refused")
        if not 1 <= args.budget <= BUDGET:
            raise TuneError(f"--budget must be in [1, {BUDGET}]")
        args.binary = args.binary.resolve()
        args.output_root = args.output_root.resolve()
        if args.output_root.exists() and any(args.output_root.iterdir()):
            raise TuneError(f"output root {args.output_root} is not empty")
        args.output_root.mkdir(parents=True, exist_ok=True)
        template, template_sha = camp.load_template(args.template)
        started = time.monotonic()
        evals = []
        for k, params in enumerate(draws(args.arm, template["controller"]["nav"], args.search_seed, args.budget)):
            evals.append(run_eval(args, template, params, k))
            e = evals[-1]
            print(f"{args.arm} eval {k:2d}: mean {e['mean_recovery']:.4f} spurious {e['nominal_spurious_runs']} "
                  f"{json.dumps(params, sort_keys=True)}", flush=True)
        feasible = [e for e in evals if e["feasible"]]
        best = max(feasible, key=lambda e: (e["mean_recovery"], -e["index"])) if feasible else None
        manifest = {
            "schema": "vv-m10-tuning.v1",
            "protocol": "docs/m10-resilient-navigation.md 10.4: F1 dev cells, mean recovery, nominal spurious <= 2/100",
            "arm": args.arm, "budget": args.budget, "search_seed": args.search_seed,
            "generator": f"random.Random({args.search_seed} * 1000 + {ARM_INDEX[args.arm]}).sample over the grid",
            "space": SPACES[args.arm], "parameters_tuned": len(SPACES[args.arm]),
            "seeds": args.seeds, "binary_sha256": camp.sha256_file(args.binary),
            "start_template_sha256": template_sha, "machine": camp.machine_description(),
            "duration_s": round(time.monotonic() - started, 1),
            "command": "python scripts/m10_tune.py " + " ".join(argv),
            "evaluations": evals, "best": best, "start": evals[0],
        }
        (args.output_root / "tuning.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
                                                      newline="\n")
    except (TuneError, camp.M10CampaignError, OSError, subprocess.TimeoutExpired) as error:
        print(f"M10 tuning failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"arm": args.arm, "best": best and {k: best[k] for k in ("index", "params", "mean_recovery")},
                      "start_mean": evals[0]["mean_recovery"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
