"""Campanha de aceitação M9.1 de aterragem propulsiva.

Executa a matriz pré-registada na secção M9.1 de `docs/m9-powered-landing.md` com `vv-rocket land`,
reproduz cada execução com `vv-rocket replay` e resume os resultados, separando deteção, contenção e
recuperação. Reutiliza o sorteio, o executor, a reprodução e os limites de `m9_campaign.py`. Só usa a
biblioteca padrão. Uma execução não verificada pela reprodução é um erro da campanha.

Os critérios das hipóteses G1 a G5 estão fixados no documento e são aplicados mecanicamente por
`evaluate_hypotheses`; nenhum limiar é lido de argumentos.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import m9_campaign as m9
from m9_campaign import M9CampaignError, RunSpec
from process_limits import ProcessLimitError
from run_campaign import parse_seeds

ROOT = m9.ROOT
TEMPLATE = ROOT / "crates" / "vv-rocket" / "landing" / "m91-nominal.json"
SCHEMA = "vv-m91-campaign.v1"
VERIFICATION_SCHEMA = "vv-rocket-landing-verification.v2"
# SHA-256 do modelo de caso M9.1 congelado, pré-registado no documento.
TEMPLATE_SHA256 = "69ecad65e9ec4329ffc74a3b985dbb7dc60d5cdaa1e4a9a380f296a76f68114b"

NOMINAL = m9.NOMINAL
NEW_FAULTS = ("altimeter_bias_low", "gnss_bias_low")
# Índices 0 a 7 como no M9; 8 e 9 para as falhas novas (entram na semente do sorteio).
FAULTS = m9.FAULTS + NEW_FAULTS
SCENARIOS = (NOMINAL,) + FAULTS
M9_SCENARIOS = (NOMINAL,) + m9.FAULTS
MAGNITUDE_RANGES: dict[str, tuple[float, float] | None] = {
    **m9.MAGNITUDE_RANGES,
    "altimeter_bias_low": (5.0, 50.0),
    "gnss_bias_low": (5.0, 30.0),
}
NEW_FAULT_WINDOW = (0.0, 40.0)

MAIN_POLICIES = ("baseline", "robust", "guarded")
EXTRA_POLICY = "baseline_guarded"
EXTRA_SCENARIOS = (NOMINAL, "gnss_dropout")
POLICIES = MAIN_POLICIES + (EXTRA_POLICY,)
DEFAULT_SEEDS = tuple(range(2000, 2030))

FLAGS = ("sensor_disagreement", "altimeter_rejected", "ascent_abort")
INVARIANT_KEYS = ("S1", "S2", "S3", "S4", "S5")
REQUIREMENT_KEYS = m9.REQUIREMENT_KEYS

# Critérios pré-registados (docs/m9-powered-landing.md, secção M9.1 e emenda).
DETECTION_SCENARIOS = ("altimeter_bias", "gnss_bias", "altimeter_bias_low", "gnss_bias_low")
FALSE_ALARM_SCENARIOS = (
    NOMINAL,
    "thrust_loss",
    "ignition_delay",
    "gimbal_stuck",
    "altimeter_dropout",
    "gnss_dropout",
    "imu_accel_bias",
)
FALSE_ALARM_MAX = 1
G3_MIN_R1 = 27
G3_SMALL_DRAW_M = 10.0
G4_TOLERANCE = 2

MAX_RUNS = 1200
DEFAULT_MAX_RUNS = 1100
DEFAULT_ARTIFACT_BYTES = 768 * 1024 * 1024


# ---------------------------------------------------------------------------
# Sorteio e casos
# ---------------------------------------------------------------------------


def sample_fault(fault: str, seed: int) -> dict[str, Any]:
    """Falha sorteada pela regra do M9; as duas falhas novas seguem o mesmo esquema de semente."""
    if fault in m9.FAULTS:
        return m9.sample_fault(fault, seed)
    if fault not in NEW_FAULTS:
        raise M9CampaignError(f"unknown fault {fault!r}")
    rng = random.Random(seed * 100 + FAULTS.index(fault))
    bounds = MAGNITUDE_RANGES[fault]
    assert bounds is not None
    low, high = bounds
    start, end = NEW_FAULT_WINDOW
    return {"kind": fault, "start_s": start, "end_s": end, "magnitude": low + (high - low) * rng.random()}


def case_name(run: RunSpec) -> str:
    return f"m91 campaign {run.fault} seed {run.seed} {run.policy}"


def build_case(template: dict[str, Any], run: RunSpec) -> dict[str, Any]:
    """O mesmo caso para todas as políticas: só `name` e `controller.policy` mudam."""
    case = copy.deepcopy(template)
    case["name"] = case_name(run)
    case["controller"]["policy"] = run.policy
    case["faults"] = [] if run.fault == NOMINAL else [sample_fault(run.fault, run.seed)]
    return case


def load_template() -> dict[str, Any]:
    try:
        raw = TEMPLATE.read_bytes()
        template = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise M9CampaignError(f"cannot read the case template: {error}") from error
    if hashlib.sha256(raw).hexdigest() != TEMPLATE_SHA256:
        raise M9CampaignError(
            f"{TEMPLATE.name} differs from the frozen pre-registered template "
            f"(expected SHA-256 {TEMPLATE_SHA256}); the controller must not change during the campaign"
        )
    if template.get("faults") != []:
        raise M9CampaignError("the case template must be the nominal case")
    return template


# ---------------------------------------------------------------------------
# Plano
# ---------------------------------------------------------------------------


def plan_runs(
    seeds: tuple[int, ...],
    scenarios: tuple[str, ...] = SCENARIOS,
    policies: tuple[str, ...] = POLICIES,
) -> list[RunSpec]:
    """Três políticas em todos os cenários; `baseline_guarded` só no nominal e em `gnss_dropout`."""
    return [
        RunSpec("matrix", scenario, policy, seed)
        for scenario in SCENARIOS
        if scenario in scenarios
        for policy in POLICIES
        if policy in policies and (policy in MAIN_POLICIES or scenario in EXTRA_SCENARIOS)
        for seed in seeds
    ]


def full_plan_keys() -> set[tuple[str, str, str, int, int | None]]:
    return {run.key for run in plan_runs(DEFAULT_SEEDS)}


# ---------------------------------------------------------------------------
# Pontuação de uma execução
# ---------------------------------------------------------------------------


def _short(identifier: str) -> str:
    return identifier.split("_", 1)[0]


def score_verification(verification: dict[str, Any]) -> dict[str, Any]:
    """Deteção, contenção e recuperação a partir de um `verification.json` v2, sem outra fonte.

    Contenção: nenhum invariante avaliado falhou (sem contacto, `S2` não é avaliado). Recuperação:
    resultado `landed` com todos os invariantes cumpridos. Deteção: a bandeira do controlador aparece
    em pelo menos um ciclo; é o que o controlador afirma e nunca entra num veredicto.
    """
    if verification.get("schema") != VERIFICATION_SCHEMA:
        raise M9CampaignError(f"verification schema must be {VERIFICATION_SCHEMA}")
    invariants, requirements = verification.get("invariants"), verification.get("requirements")
    if not isinstance(invariants, list) or [_short(str(i.get("id", ""))) for i in invariants] != list(
        INVARIANT_KEYS
    ):
        raise M9CampaignError("verification must carry the invariants S1 to S5 in order")
    if not isinstance(requirements, list):
        raise M9CampaignError("verification has no requirements")
    block = verification.get("controller_flags")
    if not isinstance(block, dict) or any(f"{name}_first" not in block for name in FLAGS):
        raise M9CampaignError("verification has no controller_flags with the three flags")
    outcome = verification.get("outcome")
    failed_invariants = [
        _short(i["id"]) for i in invariants if i.get("evaluated") and not i.get("pass")
    ]
    r1 = next((r for r in requirements if _short(str(r.get("id", ""))) == "R1"), None)
    return {
        "outcome": outcome,
        "invariant_ids_failed": failed_invariants,
        "requirement_ids_failed": [
            _short(r["id"]) for r in requirements if r.get("evaluated") and not r.get("pass")
        ],
        "contained": not failed_invariants,
        "recovered": outcome == "landed" and not failed_invariants,
        "r1_met": bool(r1 and r1.get("evaluated") and r1.get("pass")),
        "flags": {name: block[f"{name}_first"] is not None for name in FLAGS},
    }


def inspect_run(
    run: RunSpec, directory: Path, template: dict[str, Any], exit_code: int | None
) -> dict[str, Any]:
    record = m9.inspect_run(run, directory, template, exit_code, build=build_case)
    score = score_verification(m9.read_json(directory / "verification.json"))
    if score["outcome"] != record["outcome"]:
        raise M9CampaignError(f"{run.rel}: inconsistent outcome")
    record.update({k: score[k] for k in ("invariant_ids_failed", "contained", "recovered", "r1_met", "flags")})
    return record


class Runner(m9.Runner):
    """O executor do M9 com o modelo de caso e a inspeção do M9.1."""

    def load_template(self) -> dict[str, Any]:
        return load_template()

    def case_bytes_for(self, run: RunSpec) -> bytes:
        return m9.case_bytes(build_case(self.template, run))

    def inspect(self, run: RunSpec, directory: Path, exit_code: int | None) -> dict[str, Any]:
        return inspect_run(run, directory, self.template, exit_code)


# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------


def build_cells(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells = []
    for scenario in SCENARIOS:
        for policy in POLICIES:
            group = [r for r in records if r["fault"] == scenario and r["policy"] == policy]
            if not group:
                continue
            cells.append(
                {
                    "scenario": scenario,
                    "policy": policy,
                    "runs": len(group),
                    "outcome_landed": sum(r["outcome"] == "landed" for r in group),
                    "recovered": sum(r["recovered"] for r in group),
                    "hard_landing": sum(r["outcome"] == "hard_landing" for r in group),
                    "no_contact": sum(r["outcome"] == "no_contact" for r in group),
                    "detection": {name: sum(r["flags"][name] for r in group) for name in FLAGS},
                    "containment": sum(r["contained"] for r in group),
                    "r1_met": sum(r["r1_met"] for r in group),
                    "invariant_failures": {
                        key: sum(key in r["invariant_ids_failed"] for r in group) for key in INVARIANT_KEYS
                    },
                    "requirement_failures": {
                        key: sum(key in r["requirements_failed"] for r in group) for key in REQUIREMENT_KEYS
                    },
                }
            )
    return cells


def _cell_index(cells: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(c["scenario"], c["policy"]): c for c in cells}


def build_false_alarms(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bandeiras de `guarded` nas células sem enviesamento de sensor, contra o limite de 1."""
    index = _cell_index(cells)
    rows = []
    for scenario in FALSE_ALARM_SCENARIOS:
        cell = index.get((scenario, "guarded"))
        if cell is None:
            continue
        rows.append(
            {
                "scenario": scenario,
                "runs": cell["runs"],
                "flags": dict(cell["detection"]),
                "within_limit": all(n <= FALSE_ALARM_MAX for n in cell["detection"].values()),
            }
        )
    return rows


def build_regressions(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Todas as células em que `guarded` recupera menos execuções do que `robust`."""
    index = _cell_index(cells)
    rows = []
    for scenario in SCENARIOS:
        guarded, robust = index.get((scenario, "guarded")), index.get((scenario, "robust"))
        if guarded and robust and guarded["recovered"] < robust["recovered"]:
            rows.append(
                {
                    "scenario": scenario,
                    "robust_recovered": robust["recovered"],
                    "guarded_recovered": guarded["recovered"],
                    "difference": guarded["recovered"] - robust["recovered"],
                    "within_g4_tolerance": guarded["recovered"] >= robust["recovered"] - G4_TOLERANCE,
                }
            )
    return rows


def command_identity(root: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Verificação forte de G4: sem bandeiras de `guarded`, a sequência de comandos é a do `robust`.

    Compara os comandos das amostras gravadas (uma em cada 10 passos de 0,01 s) de `trace.json`,
    emparelhando cenário e semente. Só entram os pares em que nenhuma das três bandeiras de `guarded` apareceu.
    """
    by_key = {(r["fault"], r["policy"], r["seed"]): r for r in records}
    compared, different = 0, []
    for (scenario, policy, seed), guarded in sorted(by_key.items()):
        if policy != "guarded" or any(guarded["flags"].values()):
            continue
        robust = by_key.get((scenario, "robust", seed))
        if robust is None:
            continue
        samples = []
        for record in (guarded, robust):
            trace = m9.read_json(root / record["dir"] / "trace.json")
            samples.append([(s["step"], s["command"]) for s in trace.get("samples", [])])
        compared += 1
        if samples[0] != samples[1]:
            different.append(guarded["dir"])
    return {
        "pairs_compared": compared,
        "identical": compared - len(different),
        "different": different,
        "resolution": "samples recorded every 10 simulation steps (0.1 s), not every 0.02 s control cycle",
    }


def _hypothesis(hid: str, statement: str, criterion: str, observed: Any, verdict: str, evidence: str, complete: bool):
    return {
        "id": hid,
        "statement": statement,
        "criterion": criterion,
        "observed": observed,
        "complete": complete,
        "verdict": verdict,
        "evidence": evidence or "sem execuções das células desta hipótese",
    }


def evaluate_hypotheses(
    cells: list[dict[str, Any]], extras: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Critérios pré-registados G1 a G5. Sem as células da hipótese, o veredicto é `not_evaluated`."""
    index = _cell_index(cells)
    extras = extras or {}
    out = []

    # G1: deteção em 30 de 30 nos quatro enviesamentos e no máximo 1 falso alarme por bandeira nas outras células.
    det = {s: index[(s, "guarded")] for s in DETECTION_SCENARIOS if (s, "guarded") in index}
    alarms = build_false_alarms(cells)
    det_ok = {s: c["detection"]["sensor_disagreement"] == c["runs"] for s, c in det.items()}
    alarm_ok = {a["scenario"]: a["within_limit"] for a in alarms}
    held = all(det_ok.values()) and all(alarm_ok.values())
    out.append(
        _hypothesis(
            "G1",
            "guarded declara sensor_disagreement em todas as execuções com enviesamento de sensor, com poucos falsos alarmes.",
            f"sensor_disagreement em todas as execuções de cada uma de {', '.join(DETECTION_SCENARIOS)} (30 de 30); "
            f"nas células {', '.join(FALSE_ALARM_SCENARIOS)}, cada bandeira em no máximo {FALSE_ALARM_MAX} execução de guarded.",
            {"detection": {s: [c["detection"]["sensor_disagreement"], c["runs"]] for s, c in det.items()},
             "false_alarms": {a["scenario"]: a["flags"] for a in alarms}},
            "not_evaluated" if not det and not alarms else ("supported" if held else "not_supported"),
            "; ".join(
                [f"{s}: {c['detection']['sensor_disagreement']}/{c['runs']} ({'cumpre' if det_ok[s] else 'não cumpre'})" for s, c in det.items()]
                + [f"falsos alarmes {a['scenario']}: " + ", ".join(f"{k} {v}" for k, v in a["flags"].items())
                   + f" ({'cumpre' if a['within_limit'] else 'não cumpre'})" for a in alarms]
            ),
            len(det) == len(DETECTION_SCENARIOS) and len(alarms) == len(FALSE_ALARM_SCENARIOS),
        )
    )

    # G2: guarded não viola S5 em gnss_dropout. G2b: baseline_guarded não tem no_contact.
    cell = index.get(("gnss_dropout", "guarded"))
    s5 = None if cell is None else cell["invariant_failures"]["S5"]
    out.append(
        _hypothesis(
            "G2",
            "guarded não viola S5 com gnss_dropout.",
            "nenhuma execução de guarded com gnss_dropout falha S5 (0 de 30).",
            {"s5_failures": s5, "runs": None if cell is None else cell["runs"]},
            "not_evaluated" if cell is None else ("supported" if s5 == 0 else "not_supported"),
            "" if cell is None else f"gnss_dropout, guarded: S5 falhou em {s5} de {cell['runs']}",
            cell is not None,
        )
    )
    cell = index.get(("gnss_dropout", "baseline_guarded"))
    out.append(
        _hypothesis(
            "G2b",
            "baseline_guarded elimina o afastamento (no_contact) com gnss_dropout.",
            "0 execuções no_contact de baseline_guarded com gnss_dropout; a previsão de que S5 e R1 continuam a falhar fica registada, sem critério.",
            None if cell is None else {
                "no_contact": cell["no_contact"], "runs": cell["runs"], "s5_failures": cell["invariant_failures"]["S5"],
                "r1_failures": cell["requirement_failures"]["R1"], "hard_landing": cell["hard_landing"],
                "recovered": cell["recovered"]},
            "not_evaluated" if cell is None else ("supported" if cell["no_contact"] == 0 else "not_supported"),
            "" if cell is None else (
                f"gnss_dropout, baseline_guarded: no_contact {cell['no_contact']}/{cell['runs']}, hard_landing {cell['hard_landing']}, "
                f"recuperou {cell['recovered']}, S5 falhou {cell['invariant_failures']['S5']}, R1 falhou {cell['requirement_failures']['R1']}"),
            cell is not None,
        )
    )

    # G3: contacto suave (R1) com gnss_bias em pelo menos 27 de 30.
    cell = index.get(("gnss_bias", "guarded"))
    small = extras.get("small_gnss_bias_draws")
    out.append(
        _hypothesis(
            "G3",
            "guarded toca no solo com velocidade vertical aceitável (R1) com gnss_bias.",
            f"R1 cumprido em pelo menos {G3_MIN_R1} de 30 execuções de guarded com gnss_bias. O número de execuções recuperadas "
            f"(landed) é registado contra o teto previsto de cerca de 3 ± 1, sem critério.",
            None if cell is None else {"r1_met": cell["r1_met"], "runs": cell["runs"], "recovered": cell["recovered"],
                                      "draws_below_10_m": small},
            "not_evaluated" if cell is None else ("supported" if cell["r1_met"] >= G3_MIN_R1 else "not_supported"),
            "" if cell is None else (
                f"gnss_bias, guarded: R1 cumprido em {cell['r1_met']} de {cell['runs']}; recuperou {cell['recovered']}, "
                f"hard_landing {cell['hard_landing']}, sorteios com magnitude abaixo de {G3_SMALL_DRAW_M:g} m: {small}"),
            cell is not None,
        )
    )

    # G4: em cada cenário do M9, guarded recupera pelo menos robust - 2.
    rows = {}
    for scenario in M9_SCENARIOS:
        guarded, robust = index.get((scenario, "guarded")), index.get((scenario, "robust"))
        if guarded and robust:
            rows[scenario] = {
                "guarded": guarded["recovered"], "robust": robust["recovered"],
                "holds": guarded["recovered"] >= robust["recovered"] - G4_TOLERANCE,
                "informative": robust["recovered"] > 0,
            }
    identity = extras.get("command_identity")
    strong = None if identity is None else (identity["pairs_compared"] > 0 and not identity["different"])
    out.append(
        _hypothesis(
            "G4",
            "guarded não regride em relação a robust nos cenários do M9.",
            f"em cada um dos 9 cenários do M9, guarded recupera (landed com S1 a S5) pelo menos robust menos {G4_TOLERANCE} execuções. "
            "Verificação mais forte, registada à parte: sem bandeiras de guarded, a sequência de comandos é a do robust.",
            {"scenarios": rows, "command_identity": identity},
            "not_evaluated" if not rows else ("supported" if all(r["holds"] for r in rows.values()) else "not_supported"),
            "; ".join(
                f"{s}: guarded {r['guarded']}, robust {r['robust']} ({'cumpre' if r['holds'] else 'não cumpre'}"
                f"{'' if r['informative'] else '; não informativa, robust recuperou 0'})" for s, r in rows.items()
            ) + ("" if identity is None else (
                f". Verificação forte: {identity['identical']} de {identity['pairs_compared']} pares com comandos idênticos"
                f" ({'cumpre' if strong else 'não cumpre'})")),
            len(rows) == len(M9_SCENARIOS),
        )
    )

    # G5: sem critério de sucesso; regista-se o resultado de guarded nas duas falhas novas.
    rows = {s: index[(s, p)] for s in NEW_FAULTS for p in ("guarded",) if (s, p) in index}
    out.append(
        _hypothesis(
            "G5",
            "O custo da regra conservadora: nas falhas que leem baixo, guarded não recupera.",
            "sem critério de sucesso; regista-se o resultado de guarded.",
            {s: {"runs": c["runs"], "recovered": c["recovered"], "hard_landing": c["hard_landing"], "no_contact": c["no_contact"],
                 "r1_failures": c["requirement_failures"]["R1"], "sensor_disagreement": c["detection"]["sensor_disagreement"],
                 "ascent_abort": c["detection"]["ascent_abort"]} for s, c in rows.items()},
            "not_evaluated" if not rows else "recorded",
            "; ".join(
                f"{s}, guarded: recuperou {c['recovered']}/{c['runs']}, hard_landing {c['hard_landing']}, no_contact {c['no_contact']}, "
                f"R1 falhou {c['requirement_failures']['R1']}, ascent_abort {c['detection']['ascent_abort']}" for s, c in rows.items()),
            len(rows) == len(NEW_FAULTS),
        )
    )
    return out


LIMITATIONS = [
    "As dispersões e as gamas das falhas são assumidas; não foram medidas num veículo real.",
    "Cada célula tem 30 sementes: não se calculam valores-p nem intervalos de confiança, e uma contagem não estima a fiabilidade de um veículo.",
    "O modelo é idealizado: sem dinâmica de contacto, sem RCS e sem terceira fonte de altitude nem de posição horizontal.",
    "Os limiares de guarded foram afinados com as sementes 0 a 40 e as 780 execuções do M9; a aceitação usa sementes novas (2000 a 2029), mas o conjunto de falhas e as gamas foram escolhidos antes e não foram variados.",
    "A deteção é o que o controlador afirma; só a contenção e a recuperação são verificadas no estado real. Uma bandeira não prova segurança e a sua ausência não prova perigo.",
    "A verificação forte de G4 compara os comandos das amostras gravadas a cada 0,1 s, não cada ciclo de 0,02 s.",
    "Magnitudes e janelas são sorteadas uniformemente dentro das gamas; falhas combinadas e fora das gamas não foram avaliadas.",
]


def build_composition(records: list[dict[str, Any]]) -> dict[str, Any]:
    main = [r for r in records if r["policy"] in MAIN_POLICIES]
    extra = [r for r in records if r["policy"] == EXTRA_POLICY]
    seeds = len({r["seed"] for r in records})
    return {
        "main": {"scenarios": len({r["fault"] for r in main}), "policies": len({r["policy"] for r in main}),
                 "seeds": seeds, "runs": len(main)},
        "baseline_guarded": {"scenarios": len({r["fault"] for r in extra}), "policies": 1,
                             "seeds": seeds, "runs": len(extra)},
        "total": len(records),
        "repeat_runs_not_counted": m9.REPEAT_RUNS,
    }


def composition_text(c: dict[str, Any]) -> str:
    m, e = c["main"], c["baseline_guarded"]
    text = f"{m['scenarios']} cenários × {m['policies']} políticas × {m['seeds']} sementes = {m['runs']} execuções"
    if e["runs"]:
        text += f"; baseline_guarded em {e['scenarios']} cenários × {e['seeds']} sementes = {e['runs']} execuções"
    return text + f"; {m['runs']} + {e['runs']} = {c['total']}. As {c['repeat_runs_not_counted']} repetições deterministas não entram nesta contagem."


def build_summary(records: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    if not records:
        raise M9CampaignError("no runs to summarize")
    keys = {(r["group"], r["fault"], r["policy"], r["seed"], r["grid_index"]) for r in records}
    sources = {r["source_sha256"] for r in records}
    if len(sources) != 1:
        raise M9CampaignError(f"runs were built from different sources: {sorted(sources)}")
    cells = build_cells(records)
    gnss_bias = [r for r in records if r["fault"] == "gnss_bias" and r["policy"] == "guarded"]
    extras = {
        "command_identity": meta.get("command_identity"),
        "small_gnss_bias_draws": sum(r["magnitude"] < G3_SMALL_DRAW_M for r in gnss_bias),
    }
    return {
        "schema": SCHEMA,
        "preregistered": keys == full_plan_keys(),
        "seeds": sorted({r["seed"] for r in records}),
        "binary_sha256": meta.get("binary_sha256"),
        "source_sha256": sources.pop(),
        "template_sha256": meta.get("template_sha256"),
        "command": meta.get("command"),
        "machine": meta.get("machine"),
        "duration_s": meta.get("duration_s"),
        "total_runs": len(records),
        "composition": build_composition(records),
        "draw_errors": 0,
        "determinism_check": meta.get("determinism_check"),
        "cells": cells,
        "false_alarms": build_false_alarms(cells),
        "regressions": build_regressions(cells),
        "hypotheses": evaluate_hypotheses(cells, extras),
        "command_identity": meta.get("command_identity"),
        "runs": [
            {
                "scenario": r["fault"], "policy": r["policy"], "seed": r["seed"], "magnitude": r["magnitude"],
                "window": r["window"], "outcome": r["outcome"], "failed": r["failed"], "recovered": r["recovered"],
                "contained": r["contained"], "flags": r["flags"], "exit_code": r["exit_code"],
                "replay": r["replay"], "dir": r["dir"],
            }
            for r in records
        ],
        "limitations": LIMITATIONS,
    }


def _pt(value: Any) -> str:
    return m9._pt(value)


def render_markdown(summary: dict[str, Any]) -> str:
    seeds = summary["seeds"]
    lines = [
        "# Campanha de aceitação M9.1 de aterragem propulsiva",
        "",
        f"- Matriz pré-registada completa: {'sim' if summary['preregistered'] else 'não (subconjunto, sem valor de teste das hipóteses pré-registadas)'}.",
        f"- Sementes: {seeds[0]} a {seeds[-1]} ({len(seeds)})." if seeds else "- Sem execuções.",
        f"- Execuções: {summary['total_runs']}, todas reproduzidas e verificadas.",
        f"- Composição: {composition_text(summary['composition'])}",
        f"- Comando: `{summary['command']}`",
        f"- Máquina: {summary['machine']}",
        f"- Duração (relógio, fora da simulação): {_pt(summary['duration_s'])} s",
        f"- SHA-256 do binário: `{summary['binary_sha256']}`",
        f"- SHA-256 do código (`source_sha256`): `{summary['source_sha256']}`",
        f"- SHA-256 do modelo de caso: `{summary['template_sha256']}`",
        "",
        "## Resultados por célula",
        "",
        "Deteção, contenção e recuperação são três contagens separadas. `Recuperou` conta o resultado `landed` com `S1` a `S5` cumpridos. "
        "`Contenção` conta execuções em que nenhum invariante avaliado falhou. As colunas de deteção contam execuções em que a bandeira do "
        "controlador apareceu em pelo menos um ciclo (o que o controlador afirma, não um veredicto); `0` também quer dizer que a política não produz a bandeira.",
        "",
        "| Cenário | Política | Execuções | Recuperou | `hard_landing` | `no_contact` | Contenção | `sensor_disagreement` | `altimeter_rejected` | `ascent_abort` | S1 | S2 | S3 | S4 | S5 | R1 | R2 | R3 | R4 | R5 | R6 |",
        "| " + " | ".join(["---"] * 21) + " |",
    ]
    for c in summary["cells"]:
        d, i, r = c["detection"], c["invariant_failures"], c["requirement_failures"]
        lines.append(
            f"| `{c['scenario']}` | `{c['policy']}` | {c['runs']} | {c['recovered']} | {c['hard_landing']} | {c['no_contact']} | "
            f"{c['containment']} | {d['sensor_disagreement']} | {d['altimeter_rejected']} | {d['ascent_abort']} | "
            + " | ".join(str(i[k]) for k in INVARIANT_KEYS) + " | " + " | ".join(str(r[k]) for k in REQUIREMENT_KEYS) + " |"
        )
    lines += ["", "Colunas `S1` a `S5` e `R1` a `R6`: execuções em que o invariante ou o requisito falhou.", "",
              "## Falsos alarmes de `guarded`", "",
              f"Células sem enviesamento de sensor; limite pré-registado: cada bandeira em no máximo {FALSE_ALARM_MAX} execução.", "",
              "| Cenário | Execuções | `sensor_disagreement` | `altimeter_rejected` | `ascent_abort` | Dentro do limite |", "| --- | --- | --- | --- | --- | --- |"]
    for a in summary["false_alarms"]:
        f = a["flags"]
        lines.append(f"| `{a['scenario']}` | {a['runs']} | {f['sensor_disagreement']} | {f['altimeter_rejected']} | {f['ascent_abort']} | {'sim' if a['within_limit'] else 'não'} |")
    lines += ["", "## Regressões (`guarded` recupera menos do que `robust`)", ""]
    if summary["regressions"]:
        lines += ["| Cenário | `robust` | `guarded` | Diferença | Dentro da tolerância de G4 |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| `{g['scenario']}` | {g['robust_recovered']} | {g['guarded_recovered']} | {g['difference']} | {'sim' if g['within_g4_tolerance'] else 'não'} |"
                  for g in summary["regressions"]]
    else:
        lines.append("Nenhuma célula.")
    lines += ["", "## Hipóteses", ""]
    for h in summary["hypotheses"]:
        lines += [f"- **{h['id']}** ({h['verdict']}): {h['statement']}", f"  - Critério: {h['criterion']}", f"  - Observado: {h['evidence']}"]
    determinism = summary.get("determinism_check")
    if determinism:
        lines += ["", "## Repetição determinista", "",
                  f"Repetidas {len(determinism['runs'])} execuções para uma segunda pasta; ficheiros idênticos byte a byte: "
                  f"{'sim' if determinism['identical'] else 'não'} ({', '.join(determinism['files'])})."]
    lines += ["", "## Limitações", ""] + [f"- {text}" for text in summary["limitations"]]
    return "\n".join(lines) + "\n"


def write_summary(root: Path, summary: dict[str, Any]) -> None:
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (root / "summary.md").write_text(render_markdown(summary), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def parse_names(allowed: tuple[str, ...], label: str):
    def parse(value: str) -> tuple[str, ...]:
        names = [part.strip() for part in value.split(",")]
        if not names or any(n not in allowed for n in names) or len(set(names)) != len(names):
            raise argparse.ArgumentTypeError(f"{label} must be unique names among {', '.join(allowed)}")
        return tuple(n for n in allowed if n in names)

    return parse


def command_text(arguments: argparse.Namespace) -> str:
    return " ".join(
        [
            "python scripts/m91_campaign.py",
            f"--seeds {','.join(map(str, arguments.seeds))}",
            f"--scenarios {','.join(arguments.scenarios)}",
            f"--policies {','.join(arguments.policies)}",
            f"--output-root {m9.relative_text(arguments.output_root)}",
            f"--max-runs {arguments.max_runs}",
            f"--max-artifact-bytes {arguments.max_artifact_bytes}",
            f"--time-budget-seconds {arguments.time_budget_seconds:g}",
            f"--jobs {arguments.jobs}",
        ]
    )


def execute_campaign(arguments: argparse.Namespace) -> Path:
    runs = plan_runs(arguments.seeds, arguments.scenarios, arguments.policies)
    if not runs:
        raise M9CampaignError("the selected seeds, scenarios and policies produce no runs")
    m9.validate_limits(
        len(runs),
        max_runs=arguments.max_runs,
        max_artifact_bytes=arguments.max_artifact_bytes,
        time_budget_seconds=arguments.time_budget_seconds,
        jobs=arguments.jobs,
        runs_ceiling=MAX_RUNS,
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
    records = m9.run_parallel(runner, runner.execute, runs, arguments.jobs)
    determinism = m9.check_repeat(runner, runs)
    identity = command_identity(root, records)
    meta = {
        "binary_sha256": m9.sha256_file(binary),
        "template_sha256": m9.sha256_file(TEMPLATE),
        "command": command_text(arguments),
        "machine": m9.machine_description(),
        "duration_s": round(time.monotonic() - started, 1),
        "determinism_check": determinism,
        "command_identity": identity,
    }
    (root / "campaign.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    write_summary(root, build_summary(records, meta))
    return root


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=m9.binary_default())
    parser.add_argument("--seeds", type=parse_seeds, default=DEFAULT_SEEDS)
    parser.add_argument("--scenarios", type=parse_names(SCENARIOS, "scenarios"), default=SCENARIOS)
    parser.add_argument("--policies", type=parse_names(POLICIES, "policies"), default=POLICIES)
    parser.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    parser.add_argument("--max-artifact-bytes", type=int, default=DEFAULT_ARTIFACT_BYTES)
    parser.add_argument("--time-budget-seconds", type=float, default=m9.DEFAULT_TIME_BUDGET_SECONDS)
    parser.add_argument("--jobs", type=int, default=m9.DEFAULT_JOBS)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs" / "m91-campaign")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = make_parser().parse_args(argv)
    try:
        root = execute_campaign(arguments)
    except (M9CampaignError, ProcessLimitError, OSError) as error:
        print(f"M9.1 campaign failed: {error}", file=sys.stderr)
        return 1
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "passed",
                "root": m9.relative_text(root),
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
