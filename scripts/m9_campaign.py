"""Campanha M9 limitada e reproduzível de aterragem propulsiva.

Executa a matriz pré-registada em `docs/m9-powered-landing.md` com `vv-rocket land`,
reproduz cada execução com `vv-rocket replay` e resume os resultados. Só usa a
biblioteca padrão. Uma execução não verificada pela reprodução é um erro da campanha.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import random
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from process_limits import CampaignArtifactBudget, ProcessLimitError, run_bounded_process
from run_campaign import parse_seeds

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "crates" / "vv-rocket" / "landing" / "nominal.json"

SCHEMA = "vv-m9-campaign.v1"
POLICIES = ("baseline", "robust")
# Ordem da tabela de falhas do documento; o índice entra na semente do sorteio.
FAULTS = (
    "thrust_loss",
    "ignition_delay",
    "gimbal_stuck",
    "altimeter_bias",
    "altimeter_dropout",
    "gnss_dropout",
    "gnss_bias",
    "imu_accel_bias",
)
NOMINAL = "nominal"
CONDITIONS = (NOMINAL,) + FAULTS
DEFAULT_SEEDS = tuple(range(1000, 1030))
BOUNDARY_SEEDS = tuple(range(1000, 1010))
BOUNDARY_FAULTS = ("thrust_loss", "ignition_delay")
BOUNDARY_POINTS = 6
REQUIREMENT_KEYS = ("R1", "R2", "R3", "R4", "R5", "R6")

# Magnitudes pré-registadas; `None` quando a falha não tem magnitude.
MAGNITUDE_RANGES: dict[str, tuple[float, float] | None] = {
    "thrust_loss": (0.05, 0.30),
    "ignition_delay": (0.1, 1.0),
    "gimbal_stuck": None,
    "altimeter_bias": (5.0, 50.0),
    "altimeter_dropout": None,
    "gnss_dropout": None,
    "gnss_bias": (5.0, 30.0),
    "imu_accel_bias": (0.05, 0.5),
}
# Janelas fixas pré-registadas (início, fim) em segundos.
FIXED_WINDOWS: dict[str, tuple[float, float]] = {
    "thrust_loss": (5.26, 40.0),
    "ignition_delay": (2.0, 8.0),
    "altimeter_bias": (0.0, 40.0),
    "gnss_bias": (0.0, 40.0),
    "imu_accel_bias": (0.0, 40.0),
}
# Duração sorteada (s), em centésimos de segundo, e gama do início sorteado.
DURATION_RANGES_CS = {
    "gimbal_stuck": (50, 300),
    "altimeter_dropout": (200, 1000),
    "gnss_dropout": (200, 1000),
}
GIMBAL_START_RANGE_CS = (500, 2000)
DROPOUT_LATEST_END_CS = 2300

HYPOTHESIS_FAMILIES = {
    "H1": ("altimeter_bias", "altimeter_dropout", "gnss_dropout"),
    "H2": ("thrust_loss", "ignition_delay", "gimbal_stuck"),
    "H3": ("gnss_bias",),
}
H2_MAX_DISCORDANT = 3

MAX_RUNS = 1000
DEFAULT_MAX_RUNS = 800
MIN_ARTIFACT_BYTES = 65_536
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
DEFAULT_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_TIME_BUDGET_SECONDS = 3600
DEFAULT_TIME_BUDGET_SECONDS = 1800
MAX_JOBS = 8
DEFAULT_JOBS = 4
OUTPUT_LIMIT_BYTES = 1024 * 1024
REPEAT_RUNS = 2


class M9CampaignError(ValueError):
    """Erro da campanha: um resultado que não pode ser aceite como evidência."""


@dataclass(frozen=True)
class RunSpec:
    group: str  # "matrix" ou "boundary"
    fault: str  # "nominal" ou o tipo da falha
    policy: str
    seed: int
    grid_index: int | None = None

    @property
    def rel(self) -> str:
        if self.group == "boundary":
            return f"boundary/{self.fault}/m{self.grid_index}/{self.policy}/seed-{self.seed}"
        return f"runs/{self.fault}/{self.policy}/seed-{self.seed}"

    @property
    def key(self) -> tuple[str, str, str, int, int | None]:
        return (self.group, self.fault, self.policy, self.seed, self.grid_index)


# ---------------------------------------------------------------------------
# Sorteio dos casos
# ---------------------------------------------------------------------------


def boundary_magnitudes(fault: str) -> list[float]:
    """Seis magnitudes igualmente espaçadas, com os extremos incluídos."""
    bounds = MAGNITUDE_RANGES.get(fault)
    if fault not in BOUNDARY_FAULTS or bounds is None:
        raise M9CampaignError(f"{fault} has no boundary sweep")
    low, high = bounds
    last = BOUNDARY_POINTS - 1
    values = [round(low + i * (high - low) / last, 6) for i in range(BOUNDARY_POINTS)]
    values[-1] = high
    return values


def _window_for(fault: str, rng: random.Random | None) -> tuple[float, float]:
    if fault in FIXED_WINDOWS:
        return FIXED_WINDOWS[fault]
    if rng is None:
        raise M9CampaignError(f"{fault} needs a random generator for its window")
    low_cs, high_cs = DURATION_RANGES_CS[fault]
    duration_cs = round((low_cs + (high_cs - low_cs) * rng.random()))
    if fault == "gimbal_stuck":
        first, last = GIMBAL_START_RANGE_CS
    else:
        first, last = 0, DROPOUT_LATEST_END_CS - duration_cs
    start_cs = round(first + (last - first) * rng.random())
    return start_cs / 100, (start_cs + duration_cs) / 100


def sample_fault(fault: str, seed: int, magnitude: float | None = None) -> dict[str, Any]:
    """Sorteia magnitude e janela de uma falha, pela regra pré-registada.

    Ordem dos sorteios com `random.Random(seed * 100 + índice)`: magnitude, duração
    e início. Com `magnitude` dada (varrimento de fronteira) não há sorteio dela.
    """
    if fault not in FAULTS:
        raise M9CampaignError(f"unknown fault {fault!r}")
    rng = random.Random(seed * 100 + FAULTS.index(fault))
    bounds = MAGNITUDE_RANGES[fault]
    if bounds is None:
        value = 0.0
    else:
        low, high = bounds
        drawn = low + (high - low) * rng.random()
        value = drawn if magnitude is None else magnitude
    start, end = _window_for(fault, rng)
    return {"kind": fault, "start_s": start, "end_s": end, "magnitude": value}


def case_name(run: RunSpec) -> str:
    if run.group == "boundary":
        return f"m9 boundary {run.fault} point {run.grid_index} seed {run.seed} {run.policy}"
    return f"m9 campaign {run.fault} seed {run.seed} {run.policy}"


def fault_for(run: RunSpec) -> dict[str, Any] | None:
    if run.fault == NOMINAL:
        return None
    if run.group == "boundary":
        assert run.grid_index is not None
        return sample_fault(
            run.fault, run.seed, boundary_magnitudes(run.fault)[run.grid_index]
        )
    return sample_fault(run.fault, run.seed)


def build_case(template: dict[str, Any], run: RunSpec) -> dict[str, Any]:
    """O mesmo caso para as duas políticas: só `name` e `controller.policy` mudam."""
    case = copy.deepcopy(template)
    case["name"] = case_name(run)
    case["controller"]["policy"] = run.policy
    fault = fault_for(run)
    case["faults"] = [] if fault is None else [fault]
    return case


def case_bytes(case: dict[str, Any]) -> bytes:
    return (json.dumps(case, indent=2) + "\n").encode("utf-8")


def load_template() -> dict[str, Any]:
    try:
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M9CampaignError(f"cannot read the case template: {error}") from error
    if template.get("faults") != [] or template.get("controller", {}).get("policy") != "baseline":
        raise M9CampaignError("the case template must be the nominal baseline case")
    return template


# ---------------------------------------------------------------------------
# Plano
# ---------------------------------------------------------------------------


def plan_runs(
    seeds: tuple[int, ...],
    conditions: tuple[str, ...] = CONDITIONS,
    boundary_seeds: tuple[int, ...] = BOUNDARY_SEEDS,
    include_boundary: bool = True,
) -> list[RunSpec]:
    runs = [
        RunSpec("matrix", condition, policy, seed)
        for condition in CONDITIONS
        if condition in conditions
        for policy in POLICIES
        for seed in seeds
    ]
    if include_boundary:
        for fault in BOUNDARY_FAULTS:
            if fault not in conditions:
                continue
            for index in range(BOUNDARY_POINTS):
                for policy in POLICIES:
                    for seed in boundary_seeds:
                        if seed in seeds:
                            runs.append(RunSpec("boundary", fault, policy, seed, index))
    return runs


def plan_order(run: RunSpec) -> tuple[int, ...]:
    """Ordem do plano: matriz por condição, política e semente; fronteira por falha, ponto, política e semente."""
    policy = POLICIES.index(run.policy)
    if run.group == "boundary":
        assert run.grid_index is not None
        return (1, BOUNDARY_FAULTS.index(run.fault), run.grid_index, policy, run.seed)
    return (0, CONDITIONS.index(run.fault), policy, run.seed)


def full_plan_keys() -> set[tuple[str, str, str, int, int | None]]:
    return {run.key for run in plan_runs(DEFAULT_SEEDS)}


def validate_limits(
    planned: int,
    *,
    max_runs: int,
    max_artifact_bytes: int,
    time_budget_seconds: float,
    jobs: int,
) -> None:
    if type(max_runs) is not int or not 1 <= max_runs <= MAX_RUNS:
        raise M9CampaignError(f"max_runs must be between 1 and {MAX_RUNS}")
    if planned + REPEAT_RUNS > max_runs:
        raise M9CampaignError(
            f"planned matrix needs {planned + REPEAT_RUNS} simulator runs "
            f"({planned} plus {REPEAT_RUNS} for the repeat check), above max_runs {max_runs}"
        )
    if (
        type(max_artifact_bytes) is not int
        or not MIN_ARTIFACT_BYTES <= max_artifact_bytes <= MAX_ARTIFACT_BYTES
    ):
        raise M9CampaignError(
            f"max_artifact_bytes must be between {MIN_ARTIFACT_BYTES} and {MAX_ARTIFACT_BYTES}"
        )
    if (
        isinstance(time_budget_seconds, bool)
        or not isinstance(time_budget_seconds, (int, float))
        or not math.isfinite(time_budget_seconds)
        or not 0 < time_budget_seconds <= MAX_TIME_BUDGET_SECONDS
    ):
        raise M9CampaignError(
            f"time_budget_seconds must be above zero and at most {MAX_TIME_BUDGET_SECONDS}"
        )
    if type(jobs) is not int or not 1 <= jobs <= MAX_JOBS:
        raise M9CampaignError(f"jobs must be between 1 and {MAX_JOBS}")


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M9CampaignError(f"cannot read {path.name} in {path.parent.name}: {error}") from error
    if not isinstance(value, dict):
        raise M9CampaignError(f"{path.name} must be a JSON object")
    return value


def machine_description() -> str:
    parts = [
        platform.platform(),
        platform.processor() or platform.machine(),
        f"{os.cpu_count()} logical CPUs",
        f"Python {platform.python_version()}",
    ]
    return "; ".join(parts)


class Runner:
    """Executa `land` e `replay` com limites de execução, de artefactos e de tempo."""

    def __init__(
        self,
        binary: Path,
        root: Path,
        *,
        max_runs: int,
        max_artifact_bytes: int,
        time_budget_seconds: float,
    ) -> None:
        self.binary = binary.resolve()
        self.root = root.resolve()
        self.max_runs = max_runs
        self.deadline = time.monotonic() + float(time_budget_seconds)
        self.budget = CampaignArtifactBudget(self.root, max_artifact_bytes)
        self.lock = threading.Lock()
        self.simulator_runs = 0
        self.stop = threading.Event()
        self.first_error: BaseException | None = None
        self.template = load_template()

    def fail(self, error: BaseException) -> None:
        with self.lock:
            if self.first_error is None:
                self.first_error = error
        self.stop.set()

    def _process(self, command: list[str], label: str):
        if self.stop.is_set():
            raise M9CampaignError("campaign stopped after an earlier error")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise M9CampaignError("campaign exceeded its time budget")
        try:
            return run_bounded_process(
                command,
                cwd=ROOT,
                timeout_seconds=remaining,
                max_output_bytes=OUTPUT_LIMIT_BYTES,
                description=label,
            )
        except ProcessLimitError as error:
            raise M9CampaignError(str(error)) from error

    def land(self, run: RunSpec, directory: Path) -> int:
        with self.lock:
            if self.simulator_runs >= self.max_runs:
                raise M9CampaignError("campaign would exceed max_runs")
            self.simulator_runs += 1
        directory.parent.mkdir(parents=True, exist_ok=True)
        data = case_bytes(build_case(self.template, run))
        with tempfile.TemporaryDirectory() as temporary:
            case_path = Path(temporary) / "case.json"
            case_path.write_bytes(data)
            result = self._process(
                [
                    str(self.binary),
                    "land",
                    str(case_path),
                    "--seed",
                    str(run.seed),
                    "--output",
                    str(directory),
                ],
                f"land {run.rel}",
            )
        if result.returncode not in (0, 2):
            raise M9CampaignError(
                f"land {run.rel} returned {result.returncode}: {result.stderr.strip()[:300]}"
            )
        with self.lock:
            self.budget.refresh(directory)
        return result.returncode

    def replay(self, run: RunSpec, directory: Path) -> None:
        result = self._process([str(self.binary), "replay", str(directory)], f"replay {run.rel}")
        if result.returncode != 0:
            raise M9CampaignError(
                f"replay of {run.rel} was not verified (exit {result.returncode}): "
                f"{result.stdout.strip()[-300:]}"
            )
        try:
            status = json.loads(result.stdout).get("status")
        except json.JSONDecodeError as error:
            raise M9CampaignError(f"replay of {run.rel} printed no JSON") from error
        if status != "verified":
            raise M9CampaignError(f"replay of {run.rel} reported status {status!r}")

    def record(self, run: RunSpec, directory: Path, exit_code: int | None) -> dict[str, Any]:
        """Reproduz a execução e constrói o registo só a partir dos ficheiros recalculados."""
        self.replay(run, directory)
        return inspect_run(run, directory, self.template, exit_code)

    def execute(self, run: RunSpec) -> dict[str, Any]:
        directory = self.root / run.rel
        try:
            exit_code = self.land(run, directory)
            return self.record(run, directory, exit_code)
        except BaseException as error:
            self.fail(error)
            raise

    def check_stored(self, run: RunSpec) -> dict[str, Any]:
        try:
            return self.record(run, self.root / run.rel, None)
        except BaseException as error:
            self.fail(error)
            raise


def inspect_run(
    run: RunSpec, directory: Path, template: dict[str, Any], exit_code: int | None
) -> dict[str, Any]:
    """Lê uma execução já reproduzida e valida a sua identidade contra o plano."""
    expected_case = case_bytes(build_case(template, run))
    if (directory / "case.json").read_bytes() != expected_case:
        raise M9CampaignError(
            f"{run.rel}: case.json differs from the case generated by the pre-registered rule"
        )
    manifest = read_json(directory / "run.json")
    verification = read_json(directory / "verification.json")
    if manifest.get("seed") != run.seed or manifest.get("policy") != run.policy:
        raise M9CampaignError(f"{run.rel}: run.json seed or policy differs from the plan")
    outcome = verification.get("outcome")
    if outcome not in ("landed", "hard_landing", "no_contact") or outcome != manifest.get("outcome"):
        raise M9CampaignError(f"{run.rel}: unexpected or inconsistent outcome {outcome!r}")
    requirements = verification.get("requirements")
    invariants = verification.get("invariants")
    if not isinstance(requirements, list) or not isinstance(invariants, list):
        raise M9CampaignError(f"{run.rel}: verification.json has no requirements or invariants")
    requirements_failed = [
        r["id"].split("_", 1)[0] for r in requirements if r.get("evaluated") and not r.get("pass")
    ]
    invariants_failed = [i["id"] for i in invariants if not i.get("pass")]
    derived_exit = 0 if outcome == "landed" and not invariants_failed else 2
    if exit_code is not None and exit_code != derived_exit:
        raise M9CampaignError(
            f"{run.rel}: exit code {exit_code} does not match the verification (expected {derived_exit})"
        )
    fault = None
    cases = read_json(directory / "case.json").get("faults", [])
    if cases:
        fault = cases[0]
    return {
        "group": run.group,
        "fault": run.fault,
        "policy": run.policy,
        "seed": run.seed,
        "grid_index": run.grid_index,
        "magnitude": None if fault is None else fault["magnitude"],
        "window": None if fault is None else [fault["start_s"], fault["end_s"]],
        "outcome": outcome,
        "failed": requirements_failed + invariants_failed,
        "requirements_failed": requirements_failed,
        "invariants_failed": invariants_failed,
        "exit_code": derived_exit,
        "replay": "verified",
        "dir": run.rel,
        "source_sha256": manifest.get("source_sha256"),
    }


# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------


def landed_safe(record: dict[str, Any]) -> bool:
    return record["outcome"] == "landed" and not record["invariants_failed"]


def build_cells(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells = []
    for fault in CONDITIONS:
        for policy in POLICIES:
            group = [
                r for r in records if r["group"] == "matrix" and r["fault"] == fault and r["policy"] == policy
            ]
            if not group:
                continue
            failures = {key: 0 for key in REQUIREMENT_KEYS}
            for r in group:
                for key in r["requirements_failed"]:
                    failures[key] += 1
            cells.append(
                {
                    "fault": fault,
                    "policy": policy,
                    "runs": len(group),
                    "landed": sum(landed_safe(r) for r in group),
                    "landed_with_invariant_failure": sum(
                        r["outcome"] == "landed" and bool(r["invariants_failed"]) for r in group
                    ),
                    "hard_landing": sum(r["outcome"] == "hard_landing" for r in group),
                    "no_contact": sum(r["outcome"] == "no_contact" for r in group),
                    "invariant_failure_runs": sum(bool(r["invariants_failed"]) for r in group),
                    "requirement_failures": failures,
                }
            )
    return cells


def build_pairs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = []
    for fault in CONDITIONS:
        by_seed: dict[int, dict[str, bool]] = {}
        for r in records:
            if r["group"] == "matrix" and r["fault"] == fault:
                by_seed.setdefault(r["seed"], {})[r["policy"]] = landed_safe(r)
        complete = [v for v in by_seed.values() if set(v) == set(POLICIES)]
        if not complete:
            continue
        pairs.append(
            {
                "fault": fault,
                "pairs": len(complete),
                "both_land": sum(v["baseline"] and v["robust"] for v in complete),
                "only_baseline": sum(v["baseline"] and not v["robust"] for v in complete),
                "only_robust": sum(v["robust"] and not v["baseline"] for v in complete),
                "neither": sum(not v["baseline"] and not v["robust"] for v in complete),
            }
        )
    return pairs


def _cell_index(cells: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(c["fault"], c["policy"]): c for c in cells}


def evaluate_hypotheses(
    cells: list[dict[str, Any]], pairs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Critérios pré-registados. Sem falhas da família, o veredicto é `not_evaluated`."""
    index = _cell_index(cells)
    pair_index = {p["fault"]: p for p in pairs}

    def available(family: tuple[str, ...]) -> list[str]:
        return [f for f in family if (f, "baseline") in index and (f, "robust") in index]

    results = []

    family = HYPOTHESIS_FAMILIES["H1"]
    present = available(family)
    evidence = {
        f: {
            "baseline_landed": index[(f, "baseline")]["landed"],
            "robust_landed": index[(f, "robust")]["landed"],
            "runs": index[(f, "baseline")]["runs"],
        }
        for f in present
    }
    held = {f: e["robust_landed"] >= e["baseline_landed"] for f, e in evidence.items()}
    results.append(
        {
            "id": "H1",
            "statement": "Em falhas do altímetro e perda do GNSS, robust cumpre os requisitos em pelo menos tantos casos como baseline.",
            "criterion": "robust aterra (landed com todos os invariantes) em pelo menos tantas execuções como baseline em cada uma das três falhas.",
            "observed": evidence,
            "complete": len(present) == len(family),
            "verdict": "not_evaluated" if not present else ("supported" if all(held.values()) else "not_supported"),
            "evidence": "; ".join(
                f"{f}: baseline {e['baseline_landed']}/{e['runs']}, robust {e['robust_landed']}/{e['runs']}"
                f" ({'cumpre' if held[f] else 'não cumpre'})"
                for f, e in evidence.items()
            ),
        }
    )

    family = HYPOTHESIS_FAMILIES["H2"]
    present = [f for f in available(family) if f in pair_index]
    evidence = {}
    for f in present:
        p = pair_index[f]
        evidence[f] = {
            "pairs": p["pairs"],
            "discordant": p["only_baseline"] + p["only_robust"],
            "only_baseline": p["only_baseline"],
            "only_robust": p["only_robust"],
            "baseline_landed": index[(f, "baseline")]["landed"],
            "robust_landed": index[(f, "robust")]["landed"],
        }
    held = {f: e["discordant"] <= H2_MAX_DISCORDANT for f, e in evidence.items()}
    results.append(
        {
            "id": "H2",
            "statement": "Em falhas de atuador, as duas políticas têm resultados semelhantes, porque partilham o guiamento.",
            "criterion": f"pares discordantes (uma política aterra, a outra não) no máximo {H2_MAX_DISCORDANT} em cada uma das três falhas de atuador (em 30 sementes).",
            "observed": evidence,
            "complete": len(present) == len(family),
            "verdict": "not_evaluated" if not present else ("supported" if all(held.values()) else "not_supported"),
            "evidence": "; ".join(
                f"{f}: {e['discordant']} discordantes em {e['pairs']} pares"
                f" (só baseline {e['only_baseline']}, só robust {e['only_robust']};"
                f" {'cumpre' if held[f] else 'não cumpre'})"
                for f, e in evidence.items()
            ),
        }
    )

    present = [f for f in HYPOTHESIS_FAMILIES["H3"] if f in pair_index]
    only_baseline = sum(pair_index[f]["only_baseline"] for f in present)
    pairs_total = sum(pair_index[f]["pairs"] for f in present)
    results.append(
        {
            "id": "H3",
            "statement": "Com gnss_bias, robust pode rejeitar um altímetro correto e falhar onde baseline aterra.",
            "criterion": "pelo menos um par de gnss_bias em que baseline aterra e robust não.",
            "observed": {"only_baseline": only_baseline, "pairs": pairs_total},
            "complete": bool(present),
            "verdict": "not_evaluated" if not present else ("observed" if only_baseline >= 1 else "not_observed"),
            "evidence": f"gnss_bias: {only_baseline} de {pairs_total} pares em que só baseline aterra",
        }
    )
    for h in results:
        if not h["evidence"]:
            h["evidence"] = "sem execuções das falhas desta hipótese"
    return results


def build_boundaries(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for r in records:
        if r["group"] != "boundary":
            continue
        key = (r["fault"], r["policy"], r["grid_index"])
        row = rows.setdefault(
            key,
            {
                "fault": r["fault"],
                "policy": r["policy"],
                "magnitude": r["magnitude"],
                "runs": 0,
                "landed": 0,
            },
        )
        row["runs"] += 1
        row["landed"] += landed_safe(r)
    ordered = [rows[key] for key in sorted(rows, key=lambda k: (BOUNDARY_FAULTS.index(k[0]), k[1], k[2]))]
    findings = []
    for fault in BOUNDARY_FAULTS:
        for policy in POLICIES:
            row_list = [r for r in ordered if r["fault"] == fault and r["policy"] == policy]
            if not row_list:
                continue
            failing = [r for r in row_list if r["landed"] < r["runs"]]
            findings.append(
                {
                    "fault": fault,
                    "policy": policy,
                    "first_magnitude_with_failures": failing[0]["magnitude"] if failing else None,
                    "finding": (
                        f"primeira magnitude com falhas: {failing[0]['magnitude']}"
                        if failing
                        else "nenhuma fronteira dentro da gama pré-registada"
                    ),
                }
            )
    return ordered, findings


LIMITATIONS = [
    "As dispersões e as gamas das falhas são assumidas; não foram medidas num veículo real.",
    "Cada célula tem 30 sementes (10 no varrimento de fronteira): não se calculam valores-p nem intervalos de confiança, e uma taxa de sucesso não estima a fiabilidade de um veículo.",
    "O modelo é idealizado: sem dinâmica de contacto, sem RCS, sem atrito dos atuadores além das taxas e dos limites descritos.",
    "As sementes da campanha (1000 a 1029) são disjuntas das sementes 0 a 40 usadas para afinar os ganhos, mas o controlador foi afinado no caso nominal e não nas falhas.",
    "As magnitudes e as janelas são sorteadas uniformemente dentro das gamas pré-registadas; falhas combinadas e fora das gamas não foram avaliadas.",
    "A verificação dos requisitos usa o estado real do simulador; o resultado não prova nada sobre sensores ou atuadores físicos.",
]


def build_summary(records: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    if not records:
        raise M9CampaignError("no runs to summarize")
    keys = {
        (r["group"], r["fault"], r["policy"], r["seed"], r["grid_index"]) for r in records
    }
    sources = {r["source_sha256"] for r in records}
    if len(sources) != 1:
        raise M9CampaignError(f"runs were built from different sources: {sorted(sources)}")
    cells = build_cells(records)
    pairs = build_pairs(records)
    boundaries, boundary_findings = build_boundaries(records)
    matrix_seeds = sorted({r["seed"] for r in records if r["group"] == "matrix"})
    runs = [
        {
            "fault": r["fault"],
            "policy": r["policy"],
            "seed": r["seed"],
            "group": r["group"],
            "magnitude": r["magnitude"],
            "window": r["window"],
            "outcome": r["outcome"],
            "failed": r["failed"],
            "exit_code": r["exit_code"],
            "replay": r["replay"],
            "dir": r["dir"],
        }
        for r in records
    ]
    return {
        "schema": SCHEMA,
        "preregistered": keys == full_plan_keys(),
        "seeds": matrix_seeds,
        "boundary_seeds": sorted({r["seed"] for r in records if r["group"] == "boundary"}),
        "binary_sha256": meta.get("binary_sha256"),
        "source_sha256": sources.pop(),
        "template_sha256": meta.get("template_sha256"),
        "command": meta.get("command"),
        "machine": meta.get("machine"),
        "duration_s": meta.get("duration_s"),
        "resummarized": bool(meta.get("resummarized", False)),
        "total_runs": len(records),
        "determinism_check": meta.get("determinism_check"),
        "cells": cells,
        "pairs": pairs,
        "hypotheses": evaluate_hypotheses(cells, pairs),
        "boundaries": boundaries,
        "boundary_findings": boundary_findings,
        "runs": runs,
        "limitations": LIMITATIONS,
    }


def _pt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}".replace(".", ",")
    return str(value)


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Campanha M9 de aterragem propulsiva",
        "",
        f"- Matriz pré-registada completa: {'sim' if summary['preregistered'] else 'não (subconjunto, sem valor de teste das hipóteses pré-registadas)'}.",
        f"- Sementes da matriz: {summary['seeds'][0]} a {summary['seeds'][-1]} ({len(summary['seeds'])})."
        if summary["seeds"]
        else "- Sem execuções da matriz.",
        f"- Execuções: {summary['total_runs']}, todas reproduzidas e verificadas.",
        f"- Comando: `{summary['command']}`",
        f"- Máquina: {summary['machine']}",
        f"- Duração (relógio, fora da simulação): {_pt(summary['duration_s'])} s",
        f"- SHA-256 do binário: `{summary['binary_sha256']}`",
        f"- SHA-256 do código (`source_sha256`): `{summary['source_sha256']}`",
        "",
        "## Resultados por célula",
        "",
        "`aterrou` conta execuções com resultado `landed` e todos os invariantes cumpridos.",
        "",
        "| Falha | Política | Execuções | Aterrou | `hard_landing` | `no_contact` | Falhas de invariante | R1 | R2 | R3 | R4 | R5 | R6 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in summary["cells"]:
        failures = c["requirement_failures"]
        lines.append(
            f"| `{c['fault']}` | `{c['policy']}` | {c['runs']} | {c['landed']} | {c['hard_landing']} | "
            f"{c['no_contact']} | {c['invariant_failure_runs']} | "
            + " | ".join(str(failures[k]) for k in REQUIREMENT_KEYS)
            + " |"
        )
    lines += [
        "",
        "## Pares emparelhados",
        "",
        "| Falha | Pares | Ambas aterram | Só `baseline` | Só `robust` | Nenhuma |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for p in summary["pairs"]:
        lines.append(
            f"| `{p['fault']}` | {p['pairs']} | {p['both_land']} | {p['only_baseline']} | {p['only_robust']} | {p['neither']} |"
        )
    lines += ["", "## Hipóteses", ""]
    for h in summary["hypotheses"]:
        lines += [
            f"- **{h['id']}** ({h['verdict']}): {h['statement']}",
            f"  - Critério: {h['criterion']}",
            f"  - Observado: {h['evidence']}",
        ]
    if summary["boundaries"]:
        lines += [
            "",
            "## Varrimento de fronteira",
            "",
            "| Falha | Política | Magnitude | Execuções | Aterrou |",
            "| --- | --- | --- | --- | --- |",
        ]
        for b in summary["boundaries"]:
            lines.append(
                f"| `{b['fault']}` | `{b['policy']}` | {_pt(b['magnitude'])} | {b['runs']} | {b['landed']} |"
            )
        lines += [""]
        for f in summary["boundary_findings"]:
            lines.append(f"- `{f['fault']}`, `{f['policy']}`: {f['finding']}.")
    determinism = summary.get("determinism_check")
    if determinism:
        lines += [
            "",
            "## Repetição determinista",
            "",
            f"Repetidas {len(determinism['runs'])} execuções para uma segunda pasta; "
            f"ficheiros idênticos byte a byte: {'sim' if determinism['identical'] else 'não'} "
            f"({', '.join(determinism['files'])}).",
        ]
    lines += ["", "## Limitações", ""]
    lines += [f"- {text}" for text in summary["limitations"]]
    return "\n".join(lines) + "\n"


def write_summary(root: Path, summary: dict[str, Any]) -> None:
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (root / "summary.md").write_text(render_markdown(summary), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def binary_default() -> Path:
    configured = os.environ.get("VV_ROCKET_BINARY")
    if configured:
        return Path(configured)
    suffix = ".exe" if os.name == "nt" else ""
    return ROOT / "crates" / "vv-rocket" / "target" / "release" / f"vv-rocket{suffix}"


def parse_conditions(value: str) -> tuple[str, ...]:
    names = [part.strip() for part in value.split(",")]
    if not names or any(name not in CONDITIONS for name in names) or len(set(names)) != len(names):
        raise argparse.ArgumentTypeError(
            f"faults must be unique names among {', '.join(CONDITIONS)}"
        )
    return tuple(name for name in CONDITIONS if name in names)


def relative_text(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def command_text(arguments: argparse.Namespace) -> str:
    parts = ["python scripts/m9_campaign.py"]
    if arguments.summarize_only is not None:
        parts.append(f"--summarize-only {relative_text(arguments.summarize_only)}")
    else:
        parts.append(f"--seeds {','.join(map(str, arguments.seeds))}")
        parts.append(f"--faults {','.join(arguments.faults)}")
        if arguments.no_boundary:
            parts.append("--no-boundary")
        parts.append(f"--output-root {relative_text(arguments.output_root)}")
    parts += [
        f"--max-runs {arguments.max_runs}",
        f"--max-artifact-bytes {arguments.max_artifact_bytes}",
        f"--time-budget-seconds {arguments.time_budget_seconds:g}",
        f"--jobs {arguments.jobs}",
    ]
    return " ".join(parts)


def run_parallel(runner: Runner, action, runs: list[RunSpec], jobs: int) -> list[dict[str, Any]]:
    """Executa em paralelo, mas devolve os registos pela ordem do plano."""
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(action, run) for run in runs]
        results: list[dict[str, Any]] = []
        for future in futures:
            try:
                results.append(future.result())
            except BaseException:  # noqa: BLE001 - the first real error is raised below
                pass
    if runner.first_error is not None:
        raise runner.first_error
    return results


def repeat_subset(runs: list[RunSpec]) -> list[RunSpec]:
    matrix = [r for r in runs if r.group == "matrix"] or runs
    if len(matrix) == 1:
        return matrix[:1]
    return [matrix[0], matrix[-1]]


REPEAT_FILES = ("case.json", "trace.json", "verification.json", "run.json")


def check_repeat(runner: Runner, runs: list[RunSpec]) -> dict[str, Any]:
    subset = repeat_subset(runs)
    for run in subset:
        runner.land(run, runner.root / "repeat" / run.rel)
    for run in subset:
        for name in REPEAT_FILES:
            first = (runner.root / run.rel / name).read_bytes()
            second = (runner.root / "repeat" / run.rel / name).read_bytes()
            if first != second:
                raise M9CampaignError(f"repeat of {run.rel} differs in {name}")
    return {"runs": [r.rel for r in subset], "files": list(REPEAT_FILES), "identical": True}


def execute_campaign(arguments: argparse.Namespace) -> Path:
    runs = plan_runs(
        arguments.seeds, arguments.faults, BOUNDARY_SEEDS, include_boundary=not arguments.no_boundary
    )
    if not runs:
        raise M9CampaignError("the selected seeds and faults produce no runs")
    validate_limits(
        len(runs),
        max_runs=arguments.max_runs,
        max_artifact_bytes=arguments.max_artifact_bytes,
        time_budget_seconds=arguments.time_budget_seconds,
        jobs=arguments.jobs,
    )
    binary = arguments.binary.resolve()
    if not binary.is_file():
        raise M9CampaignError(f"vv-rocket binary does not exist: {binary}")
    root = arguments.output_root.resolve()
    if root.exists() and any(root.iterdir()):
        raise M9CampaignError(f"output root {root} is not empty; choose a new one")
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    runner = Runner(
        binary,
        root,
        max_runs=arguments.max_runs,
        max_artifact_bytes=arguments.max_artifact_bytes,
        time_budget_seconds=arguments.time_budget_seconds,
    )
    records = run_parallel(runner, runner.execute, runs, arguments.jobs)
    determinism = check_repeat(runner, runs)
    meta = {
        "binary_sha256": sha256_file(binary),
        "template_sha256": sha256_file(TEMPLATE),
        "command": command_text(arguments),
        "machine": machine_description(),
        "duration_s": round(time.monotonic() - started, 1),
        "determinism_check": determinism,
    }
    (root / "campaign.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    write_summary(root, build_summary(records, meta))
    return root


def discover_runs(root: Path) -> list[RunSpec]:
    """Reconstrói o plano executado a partir da estrutura de pastas."""
    found: list[RunSpec] = []

    def seed_of(name: str) -> int:
        if not name.startswith("seed-") or not name[5:].isdigit():
            raise M9CampaignError(f"unexpected directory {name!r}")
        return int(name[5:])

    base = root / "runs"
    for fault_dir in sorted(base.iterdir()) if base.is_dir() else []:
        if fault_dir.name not in CONDITIONS:
            raise M9CampaignError(f"unknown fault directory {fault_dir.name!r}")
        for policy_dir in sorted(fault_dir.iterdir()):
            if policy_dir.name not in POLICIES:
                raise M9CampaignError(f"unknown policy directory {policy_dir.name!r}")
            for seed_dir in sorted(policy_dir.iterdir()):
                found.append(RunSpec("matrix", fault_dir.name, policy_dir.name, seed_of(seed_dir.name)))
    base = root / "boundary"
    for fault_dir in sorted(base.iterdir()) if base.is_dir() else []:
        if fault_dir.name not in BOUNDARY_FAULTS:
            raise M9CampaignError(f"unknown boundary fault directory {fault_dir.name!r}")
        for point_dir in sorted(fault_dir.iterdir()):
            name = point_dir.name
            if not name.startswith("m") or not name[1:].isdigit() or int(name[1:]) >= BOUNDARY_POINTS:
                raise M9CampaignError(f"unexpected boundary directory {name!r}")
            for policy_dir in sorted(point_dir.iterdir()):
                if policy_dir.name not in POLICIES:
                    raise M9CampaignError(f"unknown policy directory {policy_dir.name!r}")
                for seed_dir in sorted(policy_dir.iterdir()):
                    found.append(
                        RunSpec(
                            "boundary",
                            fault_dir.name,
                            policy_dir.name,
                            seed_of(seed_dir.name),
                            int(name[1:]),
                        )
                    )
    return sorted(found, key=plan_order)


def summarize_only(arguments: argparse.Namespace) -> Path:
    root = arguments.summarize_only.resolve()
    if not root.is_dir():
        raise M9CampaignError(f"{root} is not a campaign directory")
    binary = arguments.binary.resolve()
    if not binary.is_file():
        raise M9CampaignError(f"vv-rocket binary does not exist: {binary}")
    runs = discover_runs(root)
    if not runs:
        raise M9CampaignError(f"no runs found in {root}")
    validate_limits(
        0,
        max_runs=arguments.max_runs,
        max_artifact_bytes=arguments.max_artifact_bytes,
        time_budget_seconds=arguments.time_budget_seconds,
        jobs=arguments.jobs,
    )
    stored: dict[str, Any] = {}
    if (root / "campaign.json").is_file():
        stored = read_json(root / "campaign.json")
    started = time.monotonic()
    runner = Runner(
        binary,
        root,
        max_runs=arguments.max_runs,
        max_artifact_bytes=arguments.max_artifact_bytes,
        time_budget_seconds=arguments.time_budget_seconds,
    )

    records = run_parallel(runner, runner.check_stored, runs, arguments.jobs)
    meta = dict(stored)
    meta["binary_sha256"] = sha256_file(binary)
    meta["template_sha256"] = sha256_file(TEMPLATE)
    meta["resummarized"] = True
    meta["resummarize_command"] = command_text(arguments)
    meta["resummarize_duration_s"] = round(time.monotonic() - started, 1)
    write_summary(root, build_summary(records, meta))
    return root


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=binary_default())
    parser.add_argument("--seeds", type=parse_seeds, default=DEFAULT_SEEDS)
    parser.add_argument("--faults", type=parse_conditions, default=CONDITIONS)
    parser.add_argument("--no-boundary", action="store_true", help="skip the boundary sweep")
    parser.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    parser.add_argument("--max-artifact-bytes", type=int, default=DEFAULT_ARTIFACT_BYTES)
    parser.add_argument("--time-budget-seconds", type=float, default=DEFAULT_TIME_BUDGET_SECONDS)
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs" / "m9-campaign")
    parser.add_argument(
        "--summarize-only",
        type=Path,
        metavar="ROOT",
        help="replay every stored run in ROOT and recompute summary.json and summary.md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = make_parser().parse_args(argv)
    try:
        if arguments.summarize_only is not None:
            root = summarize_only(arguments)
        else:
            root = execute_campaign(arguments)
    except (M9CampaignError, ProcessLimitError, OSError) as error:
        print(f"M9 campaign failed: {error}", file=sys.stderr)
        return 1
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "passed",
                "root": str(root),
                "preregistered": summary["preregistered"],
                "runs": summary["total_runs"],
                "hypotheses": {h["id"]: h["verdict"] for h in summary["hypotheses"]},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
