"""Campanha M10 de navegação resiliente (desenvolvimento; avaliação só com congelação).

Executa células (cenário de falha) por braço (`baseline`, `robust`, `guarded`, `m10_a`, `m10_b`,
`m10_b_plus`) e semente com `vv-rocket land`, lê o verificador (`v2` para as políticas do M9,
`v3` com o bloco `navigation` para os braços do M10) e resume as quatro dimensões da secção 9.1
de `docs/m10-resilient-navigation.md`: recuperação, contenção, declaração e classe física R, T, U.

Proteção da avaliação (secção 10.1): as sementes 3000 a 3099 e 6000 a 6099 são recusadas antes de
qualquer chamada ao simulador, a menos que a opção `--evaluation` seja dada **e** o manifesto
`crates/vv-rocket/landing/m10-freeze.json` exista e todos os seus hashes coincidam. A CI, os testes
e as demonstrações nunca passam `--evaluation`.

Guarda por execução `case.json`, `run.json`, `verification.json` e o SHA-256 do traço; o traço
completo fica só para a amostra (as primeiras `--keep-sample` sementes) e para as execuções com
falha de requisito, invariante ou integridade, até `--keep-failures` por célula e braço. Uma
execução retida por célula e braço é reproduzida com `vv-rocket replay`. Só usa a biblioteca padrão.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import m9_campaign as m9
import m91_campaign as m91

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "crates" / "vv-rocket" / "landing"
TEMPLATE = LANDING / "m10-nominal.json"
FREEZE = LANDING / "m10-freeze.json"
SCHEMA = "vv-m10-campaign.v1"
CASE_SCHEMA = "vv-rocket-landing.v2"

EVALUATION_SEEDS = range(3000, 3100)
RESERVE_SEEDS = range(6000, 6100)
DEV_SEEDS = tuple(range(5000, 5100))
TEST_SEEDS = tuple(range(4000, 4010))

M9_ARMS = ("baseline", "robust", "guarded")
M10_ARMS = ("m10_a", "m10_b", "m10_b_plus")
ARMS = M9_ARMS + M10_ARMS
NOMINAL = "nominal"
M9_FAULTS = m91.FAULTS
# Falhas novas do esquema v2 (secção "Esquema v2" do documento): gama da magnitude e regra da janela.
NEW_FAULTS: dict[str, dict[str, Any]] = {
    "altimeter_stuck": {"kind": "altimeter_stuck", "magnitude": None, "window": "dropout_like"},
    "altimeter_delay": {"kind": "altimeter_delay", "magnitude": (0.02, 0.2), "window": "onset"},
    "altimeter_outliers": {"kind": "altimeter_outliers", "magnitude": (0.001, 0.01), "window": "all"},
    "altimeter_drift": {"kind": "altimeter_drift", "magnitude": (0.03, 0.3), "window": "onset"},
    "gnss_horizontal_bias_t0": {"kind": "gnss_horizontal_bias", "magnitude": (5.0, 30.0), "window": "all"},
    "gnss_horizontal_bias": {"kind": "gnss_horizontal_bias", "magnitude": (5.0, 30.0), "window": "late_onset"},
    "gnss_coherent_ramp": {"kind": "gnss_coherent_ramp", "magnitude": (0.1, 3.0), "window": "late_onset"},
    "imu_accel_drift": {"kind": "imu_accel_drift", "magnitude": (0.01, 0.1), "window": "onset"},
}
# Pares pré-registados (secção 10.3). `±` marca um viés cujo sinal é sorteado pela semente.
PAIRS: dict[str, tuple[str, str]] = {
    "pair_altimeter_bias+gnss_dropout": ("altimeter_bias", "gnss_dropout"),
    "pair_altimeter_bias_low+gnss_dropout": ("altimeter_bias_low", "gnss_dropout"),
    "pair_gnss_bias+altimeter_dropout": ("gnss_bias", "altimeter_dropout"),
    "pair_altimeter_bias±+imu_accel_bias": ("altimeter_bias±", "imu_accel_bias"),
    "pair_gnss_bias_low+imu_accel_bias": ("gnss_bias_low", "imu_accel_bias"),
    "pair_altimeter_bias±+gnss_bias±": ("altimeter_bias±", "gnss_bias±"),
}
SCENARIOS = (NOMINAL,) + M9_FAULTS + tuple(NEW_FAULTS) + tuple(PAIRS)
FAMILIES = {
    "F1": (NOMINAL,) + M9_FAULTS,
    "F2": tuple(n for n in NEW_FAULTS if n != "altimeter_drift"),
    "F3": tuple(PAIRS),
}

MAX_RUNS = 2500
DEFAULT_MAX_RUNS = 2500
# Cada execução é um processo curto de `vv-rocket`; a criação do processo domina o tempo, por isso
# mais tarefas do que núcleos ainda ajudam. Com 16 na máquina da auditoria: 1,44 vezes mais rápido
# do que com 8 e resultados iguais (docs/m12-performance-audit.md).
MAX_JOBS = 16
DEFAULT_JOBS = 4
MAX_TIME_BUDGET_SECONDS = 3600
DEFAULT_TIME_BUDGET_SECONDS = 1800
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_ARTIFACT_BYTES = 1024 * 1024 * 1024
DEFAULT_KEEP_SAMPLE = 2
DEFAULT_KEEP_FAILURES = 5
REPLAY_PER_CELL = 1
NEW_FAULT_INDEX_BASE = 50


class M10CampaignError(ValueError):
    pass


@dataclass(frozen=True)
class RunSpec:
    scenario: str
    arm: str
    seed: int

    @property
    def directory(self) -> str:
        return f"{self.scenario}/{self.arm}/seed-{self.seed}"


# ---------------------------------------------------------------------------
# Sementes e congelação
# ---------------------------------------------------------------------------


def protected(seed: int) -> bool:
    return seed in EVALUATION_SEEDS or seed in RESERVE_SEEDS


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_freeze() -> dict[str, Any]:
    """O manifesto existe, tem a forma esperada e todos os hashes coincidem; senão, erro."""
    if not FREEZE.is_file():
        raise M10CampaignError(
            f"evaluation refused: no freeze manifest at {FREEZE.relative_to(ROOT).as_posix()} "
            "(the owner freezes the configuration before any evaluation)"
        )
    try:
        manifest = json.loads(FREEZE.read_text(encoding="utf-8"))
        files = manifest["files"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise M10CampaignError(f"evaluation refused: unreadable freeze manifest: {error}") from error
    if not isinstance(files, dict) or not files:
        raise M10CampaignError("evaluation refused: the freeze manifest lists no files")
    for rel, digest in files.items():
        path = (ROOT / rel).resolve()
        if ROOT not in path.parents or not path.is_file():
            raise M10CampaignError(f"evaluation refused: frozen file {rel} is missing")
        if sha256_file(path) != digest:
            raise M10CampaignError(f"evaluation refused: {rel} differs from the freeze manifest")
    return manifest


def guard_seeds(seeds: tuple[int, ...], evaluation: bool) -> dict[str, Any] | None:
    """Recusa as sementes de avaliação e de reserva antes de qualquer execução."""
    blocked = [s for s in seeds if protected(s)]
    if blocked and not evaluation:
        raise M10CampaignError(
            f"evaluation seeds refused without --evaluation and a matching freeze: {blocked[:5]}"
        )
    if evaluation:
        return check_freeze()
    return None


# ---------------------------------------------------------------------------
# Sorteio e casos
# ---------------------------------------------------------------------------


def _uniform_cs(rng: random.Random, low_s: float, high_s: float) -> float:
    low, high = round(low_s * 100), round(high_s * 100)
    return round(low + (high - low) * rng.random()) / 100


def sample_new_fault(name: str, seed: int) -> dict[str, Any]:
    """Sorteio de uma falha nova: magnitude, depois a janela, com um gerador próprio por falha."""
    spec = NEW_FAULTS[name]
    rng = random.Random(seed * 100 + NEW_FAULT_INDEX_BASE + list(NEW_FAULTS).index(name))
    bounds = spec["magnitude"]
    magnitude = 0.0 if bounds is None else bounds[0] + (bounds[1] - bounds[0]) * rng.random()
    window = spec["window"]
    if window == "all":
        start, end = 0.0, 40.0
    elif window == "onset":
        start, end = _uniform_cs(rng, 2.0, 12.0), 40.0
    elif window == "late_onset":
        start, end = _uniform_cs(rng, 4.0, 12.0), 40.0
    else:  # dropout_like: 1 a 10 s, dentro de [5, 23] s como as perdas de dados do M9.
        duration = _uniform_cs(rng, 1.0, 10.0)
        start = _uniform_cs(rng, 5.0, 23.0 - duration)
        end = round((start + duration) * 100) / 100
    return {"kind": spec["kind"], "start_s": start, "end_s": end, "magnitude": magnitude}


def _signed(kind: str, seed: int) -> str:
    if not kind.endswith("±"):
        return kind
    base = kind[:-1]
    rng = random.Random(seed * 100 + 90 + (0 if base.startswith("alt") else 1))
    return base if rng.random() < 0.5 else f"{base}_low"


def faults_for(scenario: str, seed: int) -> list[dict[str, Any]]:
    if scenario == NOMINAL:
        return []
    if scenario in M9_FAULTS:
        return [m91.sample_fault(scenario, seed)]
    if scenario in NEW_FAULTS:
        return [sample_new_fault(scenario, seed)]
    if scenario in PAIRS:
        return [m91.sample_fault(_signed(k, seed), seed) for k in PAIRS[scenario]]
    raise M10CampaignError(f"unknown scenario {scenario!r}")


def load_template(path: Path = TEMPLATE) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    template = json.loads(raw.decode("utf-8"))
    if template.get("schema") != CASE_SCHEMA or template.get("faults") != []:
        raise M10CampaignError(f"{path.name} must be a nominal {CASE_SCHEMA} case")
    return template, hashlib.sha256(raw).hexdigest()


def build_case(template: dict[str, Any], run: RunSpec) -> dict[str, Any]:
    """O mesmo caso para todos os braços: só `name` e `controller.policy` mudam."""
    case = copy.deepcopy(template)
    case["name"] = f"m10 {run.scenario} seed {run.seed} {run.arm}"
    case["controller"]["policy"] = run.arm
    case["faults"] = faults_for(run.scenario, run.seed)
    return case


def plan_runs(seeds, scenarios, arms) -> list[RunSpec]:
    return [RunSpec(sc, arm, seed) for sc in scenarios for arm in arms for seed in seeds]


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


class Runner:
    def __init__(self, binary: Path, root: Path, template: dict[str, Any], args: argparse.Namespace):
        self.binary = binary
        self.root = root
        self.template = template
        self.args = args
        self.deadline = time.monotonic() + args.time_budget_seconds
        self.bytes = 0

    def execute(self, run: RunSpec) -> dict[str, Any]:
        if time.monotonic() > self.deadline:
            raise M10CampaignError("time budget exhausted")
        out = self.root / run.directory
        out.parent.mkdir(parents=True, exist_ok=True)
        case_path = out.parent / f"seed-{run.seed}.case.json"
        case_path.write_text(json.dumps(build_case(self.template, run), indent=2) + "\n",
                             encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [str(self.binary), "land", str(case_path), "--seed", str(run.seed), "--output", str(out)],
            capture_output=True, text=True, timeout=120, check=False,
        )
        case_path.unlink()
        if proc.returncode not in (0, 2):
            raise M10CampaignError(f"{run.directory}: vv-rocket land exited {proc.returncode}: "
                                   f"{proc.stderr.strip()[:300]}")
        verification = json.loads((out / "verification.json").read_text(encoding="utf-8"))
        trace = out / "trace.json"
        record = score(run, verification)
        record["trace_sha256"] = sha256_file(trace)
        record["trace_bytes"] = trace.stat().st_size
        return record


CHANNELS = ("vertical", "horizontal_velocity", "horizontal_position")


def score(run: RunSpec, v: dict[str, Any]) -> dict[str, Any]:
    reqs = {r["id"].split("_")[0]: r["pass"] for r in v["requirements"]}
    invs = {i["id"].split("_")[0]: i["pass"] for i in v["invariants"]}
    nav = v.get("navigation")
    record: dict[str, Any] = {
        "scenario": run.scenario,
        "arm": run.arm,
        "seed": run.seed,
        "schema": v["schema"],
        "outcome": v["outcome"],
        "requirements": reqs,
        "invariants": invs,
        "faults": [{k: f[k] for k in ("kind", "start_s", "end_s", "magnitude", "acted")} for f in v["faults"]],
        "acted": all(f["acted"] for f in v["faults"]),
        "recovery": v["outcome"] == "landed" and v["requirements_pass"] and v["invariants_pass"],
        "containment": v["invariants_pass"] and v["outcome"] != "no_contact",
    }
    record["physical_class"] = physical_class(record)
    if nav is not None:
        if nav["physical_class"] != record["physical_class"]:
            raise M10CampaignError(f"{run.directory}: physical class differs between verifier and script")
        record["nav"] = {
            "alert_failure": {ch: nav[ch]["alert_failure"] for ch in CHANNELS},
            "applicable": {ch: nav[ch]["declaration_applicable"] for ch in CHANNELS},
            "vertical_max_error_m": nav["vertical"]["max_error"],
            "vertical_trusted_fraction": nav["vertical"]["trusted_fraction"],
            "unnecessary_vertical": nav["vertical"]["unnecessary_declaration_fraction"],
            "nees_mean": nav["nees_mean"],
            "final_vertical_error_m": nav["final_vertical_error_m"],
            "transitions": len(nav["transitions"]),
            "final_mode": nav["transitions"][-1]["to"] if nav["transitions"] else "degraded_nav",
            "unsafe_transitions": nav["unsafe_transitions"],
            "transitions_within_bound": nav["transitions_within_bound"],
            "spurious_degradations": nav["degradations_outside_fault_windows"],
            "detections": [d["first_declaration_delay_s"] for d in nav["detections"]],
            "isolation": nav["isolation"],
        }
    return record


def physical_class(r: dict[str, Any]) -> str:
    if r["outcome"] == "no_contact" or not all(r["invariants"].values()):
        return "U"
    others = all(r["requirements"][k] for k in ("R1", "R2", "R3", "R4", "R6"))
    if others and r["requirements"]["R5"]:
        return "R"
    return "T" if others else "U"


def failed(record: dict[str, Any]) -> bool:
    nav = record.get("nav")
    integrity = nav is not None and any(nav["alert_failure"].values())
    return record["physical_class"] != "R" or integrity


def retain(runner: Runner, records: list[dict[str, Any]], seeds: tuple[int, ...]) -> dict[str, Any]:
    """Apaga os traços fora da amostra e das falhas retidas; reproduz uma parte dos retidos."""
    sample = set(seeds[: runner.args.keep_sample])
    kept_failures: dict[tuple[str, str], int] = {}
    replayed_cells: set[tuple[str, str]] = set()
    replays: dict[str, Any] = {"replayed": 0, "verified": 0, "failed": []}
    for r in records:
        key = (r["scenario"], r["arm"])
        out = runner.root / RunSpec(r["scenario"], r["arm"], r["seed"]).directory
        keep = r["seed"] in sample
        if not keep and failed(r) and kept_failures.get(key, 0) < runner.args.keep_failures:
            kept_failures[key] = kept_failures.get(key, 0) + 1
            keep = True
        if keep and key not in replayed_cells:
            replayed_cells.add(key)
            proc = subprocess.run([str(runner.binary), "replay", str(out)], capture_output=True,
                                  text=True, timeout=120, check=False)
            replays["replayed"] += 1
            if proc.returncode == 0:
                replays["verified"] += 1
            else:
                replays["failed"].append(RunSpec(r["scenario"], r["arm"], r["seed"]).directory)
        r["trace_kept"] = keep
        if keep:
            runner.bytes += r["trace_bytes"]
            if runner.bytes > runner.args.max_artifact_bytes:
                raise M10CampaignError("artifact budget exceeded while keeping traces")
        else:
            (out / "trace.json").unlink()
    return replays


# ---------------------------------------------------------------------------
# Estatística e resumo
# ---------------------------------------------------------------------------


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) para X ~ Binomial(n, p), por soma direta em logaritmos."""
    if k < 0:
        return 0.0
    if k >= n or p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    total = 0.0
    for i in range(k + 1):
        total += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                          + i * log_p + (n - i) * log_q)
    return min(total, 1.0)


def _bisect(f, target: float) -> float:
    """Raiz de `f(p) = target` em [0, 1] para `f` decrescente."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Intervalo exato bilateral de Clopper-Pearson."""
    if n == 0:
        return (0.0, 1.0)
    # Inferior: P(X >= k | p) = alpha/2, isto é P(X <= k - 1 | p) = 1 - alpha/2.
    lower = 0.0 if k == 0 else _bisect(lambda p: binom_cdf(k - 1, n, p), 1.0 - alpha / 2)
    upper = 1.0 if k == n else _bisect(lambda p: binom_cdf(k, n, p), alpha / 2)
    return (round(lower, 4), round(upper, 4))


def _median(values: list[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    m = len(values) // 2
    return values[m] if len(values) % 2 else (values[m - 1] + values[m]) / 2


def build_cells(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in records:
        groups.setdefault((r["scenario"], r["arm"]), []).append(r)
    cells = []
    for (scenario, arm), rs in groups.items():
        n = len(rs)
        recovered = sum(1 for r in rs if r["recovery"])
        cell: dict[str, Any] = {
            "scenario": scenario,
            "arm": arm,
            "runs": n,
            "not_acted": sum(1 for r in rs if not r["acted"]),
            "recovered": recovered,
            "recovered_ci95": clopper_pearson(recovered, n),
            "contained": sum(1 for r in rs if r["containment"]),
            "classes": {c: sum(1 for r in rs if r["physical_class"] == c) for c in "RTU"},
            "hard_landings": sum(1 for r in rs if r["outcome"] == "hard_landing"),
            "no_contact": sum(1 for r in rs if r["outcome"] == "no_contact"),
        }
        navs = [r["nav"] for r in rs if "nav" in r]
        if navs:
            v_fail = sum(1 for x in navs if x["alert_failure"]["vertical"])
            delays = [d for x in navs for d in x["detections"] if d is not None]
            nees = [x["nees_mean"] for x in navs if x["nees_mean"] is not None]
            cell["navigation"] = {
                "vertical_alert_failures": v_fail,
                "vertical_alert_failures_ci95": clopper_pearson(v_fail, n),
                "hv_alert_failures": sum(1 for x in navs if x["alert_failure"]["horizontal_velocity"]),
                "hp_alert_failures": sum(1 for x in navs if x["alert_failure"]["horizontal_position"]),
                "vertical_declaration_applicable": sum(1 for x in navs if x["applicable"]["vertical"]),
                "runs_declared_in_every_window": sum(
                    1 for x in navs if x["detections"] and all(d is not None for d in x["detections"])),
                "median_declaration_delay_s": _median(delays),
                "spurious_degradation_runs": sum(1 for x in navs if x["spurious_degradations"] > 0),
                "unsafe_transitions": sum(x["unsafe_transitions"] for x in navs),
                "transition_bound_violations": sum(1 for x in navs if not x["transitions_within_bound"]),
                "nees_mean_of_runs": (sum(nees) / len(nees)) if nees else None,
                "final_mode_untrusted": sum(1 for x in navs if x["final_mode"] == "untrusted"),
                "median_vertical_trusted_fraction": _median([x["vertical_trusted_fraction"] for x in navs]),
                "isolation": {k: sum(1 for x in navs if x["isolation"] == k) for k in ("correct", "wrong", "none")},
            }
        cells.append(cell)
    order = {s: i for i, s in enumerate(SCENARIOS)}
    arm_order = {a: i for i, a in enumerate(ARMS)}
    cells.sort(key=lambda c: (order.get(c["scenario"], 999), arm_order[c["arm"]]))
    return cells


def build_pairs(records: list[dict[str, Any]], reference: str = "guarded") -> list[dict[str, Any]]:
    """Diferenças emparelhadas por semente: `b` só a referência recupera, `c` só o braço."""
    index = {(r["scenario"], r["arm"], r["seed"]): r for r in records}
    out = []
    for scenario, arm in sorted({(r["scenario"], r["arm"]) for r in records}):
        if arm == reference:
            continue
        b = c = n = 0
        for (sc, a, seed), r in index.items():
            ref = index.get((sc, reference, seed))
            if sc != scenario or a != arm or ref is None:
                continue
            n += 1
            b += ref["recovery"] and not r["recovery"]
            c += r["recovery"] and not ref["recovery"]
        if n:
            out.append({"scenario": scenario, "arm": arm, "reference": reference, "pairs": n,
                        "only_reference": b, "only_arm": c, "difference": round((c - b) / n, 4)})
    return out


def global_table(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Avaliação global de segurança (9.1, regra 2): todas as células, por braço."""
    table: dict[str, dict[str, int]] = {}
    for c in cells:
        t = table.setdefault(c["arm"], {"runs": 0, "R": 0, "T": 0, "U": 0})
        t["runs"] += c["runs"]
        for k in "RTU":
            t[k] += c["classes"][k]
    return [{"arm": a, **t, "U_ci95": clopper_pearson(t["U"], t["runs"])} for a, t in table.items()]


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Campanha M10 (resumo gerado)",
        "",
        f"Comando: `{summary['command']}`",
        f"Máquina: {summary['machine']}; duração {summary['duration_s']} s; execuções {summary['total_runs']}.",
        f"Sementes: {summary['seed_block']}. Avaliação: {'sim' if summary['evaluation'] else 'não'}.",
        f"Reprodução: {summary['replay']['verified']} de {summary['replay']['replayed']} verificadas.",
        "",
        "| Célula | Braço | n | Recuperou (IC 95%) | R / T / U | I1v | Declaração aplicável | "
        "Atraso mediano (s) | Degradações espúrias | NEES |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in summary["cells"]:
        nav = c.get("navigation") or {}
        ci = c["recovered_ci95"]
        nees = nav.get("nees_mean_of_runs")
        delay = nav.get("median_declaration_delay_s")
        lines.append(
            f"| {c['scenario']} | {c['arm']} | {c['runs']} | {c['recovered']} ({ci[0]:.2f} a {ci[1]:.2f}) | "
            f"{c['classes']['R']} / {c['classes']['T']} / {c['classes']['U']} | "
            f"{nav.get('vertical_alert_failures', 'n/a')} | {nav.get('vertical_declaration_applicable', 'n/a')} | "
            f"{'n/a' if delay is None else f'{delay:.2f}'} | {nav.get('spurious_degradation_runs', 'n/a')} | "
            f"{'n/a' if nees is None else f'{nees:.2f}'} |"
        )
    lines += ["", "## Avaliação global de segurança", "", "| Braço | n | R | T | U | U (IC 95%) |",
              "| --- | --- | --- | --- | --- | --- |"]
    for g in summary["global"]:
        lines.append(f"| {g['arm']} | {g['runs']} | {g['R']} | {g['T']} | {g['U']} | "
                     f"{g['U_ci95'][0]:.3f} a {g['U_ci95'][1]:.3f} |")
    lines += ["", "## Pares emparelhados contra `guarded`", "",
              "| Célula | Braço | pares | só guarded | só braço | diferença |",
              "| --- | --- | --- | --- | --- | --- |"]
    for p in summary["pairs"]:
        lines.append(f"| {p['scenario']} | {p['arm']} | {p['pairs']} | {p['only_reference']} | "
                     f"{p['only_arm']} | {p['difference']:+.2f} |")
    lines += ["", "Resultados condicionais às dispersões e às gamas assumidas, num modelo idealizado. "
              "Com sementes de desenvolvimento ou de teste, não são uma avaliação do M10."]
    return "\n".join(lines) + "\n"


def seed_block(seeds: tuple[int, ...]) -> str:
    if all(s in DEV_SEEDS for s in seeds):
        return "desenvolvimento (5000 a 5099)"
    if all(s in TEST_SEEDS for s in seeds):
        return "teste e CI (4000 a 4009)"
    if all(protected(s) for s in seeds):
        return "avaliação ou reserva"
    return "mista ou já publicada (não é avaliação)"


def machine_description() -> str:
    return f"{platform.platform()}; {platform.processor() or platform.machine()}; Python {platform.python_version()}"


# ---------------------------------------------------------------------------
# Linha de comandos
# ---------------------------------------------------------------------------


def parse_seeds(value: str) -> tuple[int, ...]:
    seeds: list[int] = []
    try:
        for part in value.split(","):
            part = part.strip()
            if "-" in part:
                low, high = part.split("-", 1)
                seeds.extend(range(int(low), int(high) + 1))
            elif part:
                seeds.append(int(part))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid seeds: {error}") from error
    if not seeds or len(set(seeds)) != len(seeds) or any(s < 0 for s in seeds):
        raise argparse.ArgumentTypeError("seeds must be unique non-negative integers (a,b or a-b)")
    return tuple(seeds)


def parse_names(allowed: tuple[str, ...], label: str):
    def parse(value: str) -> tuple[str, ...]:
        names: list[str] = []
        for part in value.split(","):
            part = part.strip()
            if part in FAMILIES and label == "scenario":
                names.extend(FAMILIES[part])
            elif part in allowed:
                names.append(part)
            else:
                raise argparse.ArgumentTypeError(f"unknown {label} {part!r}")
        if len(set(names)) != len(names):
            raise argparse.ArgumentTypeError(f"repeated {label}")
        return tuple(names)
    return parse


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--binary", type=Path, default=m9.binary_default())
    p.add_argument("--seeds", type=parse_seeds, default=TEST_SEEDS[:2])
    p.add_argument("--scenarios", type=parse_names(SCENARIOS, "scenario"), default=(NOMINAL,))
    p.add_argument("--arms", type=parse_names(ARMS, "arm"), default=ARMS)
    p.add_argument("--template", type=Path, default=TEMPLATE,
                   help="development only: another nominal v2 case (an evaluation uses the frozen template)")
    p.add_argument("--evaluation", action="store_true",
                   help="allow the evaluation seeds; needs a matching freeze manifest")
    p.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    p.add_argument("--max-artifact-bytes", type=int, default=DEFAULT_ARTIFACT_BYTES)
    p.add_argument("--time-budget-seconds", type=float, default=DEFAULT_TIME_BUDGET_SECONDS)
    p.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    p.add_argument("--keep-sample", type=int, default=DEFAULT_KEEP_SAMPLE)
    p.add_argument("--keep-failures", type=int, default=DEFAULT_KEEP_FAILURES)
    p.add_argument("--output-root", type=Path, default=ROOT / "runs" / "m10-campaign")
    return p


def validate(args: argparse.Namespace, runs: int) -> None:
    if not 1 <= args.max_runs <= MAX_RUNS:
        raise M10CampaignError(f"--max-runs must be in [1, {MAX_RUNS}]")
    if runs > args.max_runs:
        raise M10CampaignError(f"the plan has {runs} runs, above --max-runs {args.max_runs}; split it in chunks")
    if not 1 <= args.jobs <= MAX_JOBS:
        raise M10CampaignError(f"--jobs must be in [1, {MAX_JOBS}]")
    if not 1 <= args.time_budget_seconds <= MAX_TIME_BUDGET_SECONDS:
        raise M10CampaignError(f"--time-budget-seconds must be in [1, {MAX_TIME_BUDGET_SECONDS}]")
    if not 65_536 <= args.max_artifact_bytes <= MAX_ARTIFACT_BYTES:
        raise M10CampaignError(f"--max-artifact-bytes must be in [65536, {MAX_ARTIFACT_BYTES}]")
    if args.keep_sample < 0 or args.keep_failures < 0:
        raise M10CampaignError("--keep-sample and --keep-failures must not be negative")


def execute(args: argparse.Namespace, argv: list[str]) -> Path:
    # A recusa das sementes protegidas vem antes de qualquer leitura do binário ou execução.
    freeze = guard_seeds(args.seeds, args.evaluation)
    runs = plan_runs(args.seeds, args.scenarios, args.arms)
    if not runs:
        raise M10CampaignError("empty plan")
    validate(args, len(runs))
    binary = args.binary.resolve()
    if not binary.is_file():
        raise M10CampaignError(f"vv-rocket binary does not exist: {binary}")
    root = args.output_root.resolve()
    if root.exists() and any(root.iterdir()):
        raise M10CampaignError(f"output root {root} is not empty; choose a new one")
    root.mkdir(parents=True, exist_ok=True)
    if args.evaluation and args.template.resolve() != TEMPLATE.resolve():
        raise M10CampaignError("an evaluation uses the frozen template only")
    template, template_sha = load_template(args.template)
    runner = Runner(binary, root, template, args)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        records = list(pool.map(runner.execute, runs))
    replay = retain(runner, records, args.seeds)
    if replay["failed"]:
        raise M10CampaignError(f"replay failed for {replay['failed'][:3]}")
    cells = build_cells(records)
    summary = {
        "schema": SCHEMA,
        "command": "python scripts/m10_campaign.py " + " ".join(argv),
        "machine": machine_description(),
        "duration_s": round(time.monotonic() - started, 1),
        "binary_sha256": sha256_file(binary),
        "template_sha256": template_sha,
        "evaluation": bool(args.evaluation),
        "freeze": freeze,
        "seed_block": seed_block(args.seeds),
        "seeds": list(args.seeds),
        "total_runs": len(records),
        "mean_trace_bytes": round(sum(r["trace_bytes"] for r in records) / len(records)),
        "replay": replay,
        "cells": cells,
        "pairs": build_pairs(records),
        "global": global_table(cells),
    }
    (root / "records.json").write_text(json.dumps(records, indent=1) + "\n", encoding="utf-8", newline="\n")
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "summary.md").write_text(render_markdown(summary), encoding="utf-8", newline="\n")
    return root


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = make_parser().parse_args(argv)
    try:
        root = execute(args, argv)
    except (M10CampaignError, OSError, subprocess.TimeoutExpired) as error:
        print(f"M10 campaign failed: {error}", file=sys.stderr)
        return 1
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    rel = root.relative_to(ROOT).as_posix() if ROOT in root.parents else str(root)
    print(json.dumps({"status": "passed", "root": rel, "runs": summary["total_runs"],
                      "replay": summary["replay"], "seed_block": summary["seed_block"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
