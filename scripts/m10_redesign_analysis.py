"""Análise do pré-registo da reformulação do M10 (`docs/m10-redesign-preregistration.md`, secções 6 a 8 e adendas).

Lê as saídas de `scripts/m10_redesign_run.py`, verifica a integridade (um só binário, sementes de
desenvolvimento, contagens da matriz), calcula os critérios S1 a S7, as cláusulas de paragem e os
limites de regressão V2, e escreve `analysis.json`, `analysis.md` e `records.jsonl.gz`. Só biblioteca
padrão; sem aleatoriedade. Análise fora da simulação.

    python scripts/m10_redesign_analysis.py --root runs/m10-run --output docs/evidence/m10-redesign
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m10_adversarial_probe as probe  # noqa: E402
import m10_campaign as camp  # noqa: E402

LABELS = ("B", "B+", "B+G", "robust", "guarded")
POLICY = {"B": "m10_b", "B+": "m10_b_plus", "B+G": "m10_b_plus", "robust": "robust", "guarded": "guarded"}
UNIT_ONSETS = (4.5, 6.0, 8.0, 10.0)
UNIT_SEEDS = range(5020, 5040)
STRATUM = (5001, 5004, 5011, 5012, 5027, 5029, 5031, 5033, 5041, 5042, 5048, 5056, 5062, 5063, 5074, 5076, 5078, 5081)
DISTINCT_SKIP = "pair_altimeter_bias_low+gnss_dropout"  # the same experiment as the +gnss_dropout pair
ISO_CELLS = ("altimeter_stuck", "altimeter_delay", "altimeter_outliers", "gnss_coherent_ramp")
TRUE_CELLS = ("altimeter_stuck", "altimeter_delay", "gnss_coherent_ramp")


def cp_upper(k: int, n: int, alpha: float = 0.05) -> float:
    return camp.clopper_pearson(k, n, alpha)[1]


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------


def load_probe(path: Path) -> list[dict]:
    recs = json.loads(path.read_text(encoding="utf-8"))["records"]
    out = []
    for r in recs:
        tpl, label, spec = r["tag"].split("~", 2)
        head, onset = spec.rsplit("@", 1)
        r = dict(r, label=label, onset=float(onset), cls2=probe.physical_class(r))
        r["mag"] = float(head[4:]) if head.startswith("ramp") else None
        r["kind"] = head if r["mag"] is None else "gnss_coherent_ramp"
        r["hv"] = bool(r["af"]["horizontal_velocity"])
        r["av"] = bool(r["af"]["vertical"])
        r["ap"] = bool(r["af"]["horizontal_position"])
        r["wrong"] = r["iso"] == "wrong"
        out.append(r)
    return out


def load_campaign(path: Path, label: str) -> tuple[list[dict], dict]:
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    recs = json.loads((path / "records.json").read_text(encoding="utf-8"))
    out = []
    for r in recs:
        nav = r.get("nav") or {}
        af = nav.get("alert_failure") or {}
        out.append({
            "label": label, "scenario": r["scenario"], "seed": r["seed"], "cls": r["physical_class"],
            "fail": sorted(k for k, ok in r["requirements"].items() if not ok),
            "inv": sorted(k for k, ok in r["invariants"].items() if not ok),
            "iso": nav.get("isolation"), "hv": bool(af.get("horizontal_velocity")),
            "av": bool(af.get("vertical")), "ap": bool(af.get("horizontal_position")),
            "wrong": nav.get("isolation") == "wrong", "gate": r.get("gate"),
        })
    return out, summary


def count(rs: list[dict], key: str = "cls") -> dict:
    c = collections.Counter(r[key] for r in rs)
    return {k: c.get(k, 0) for k in "RTU"}


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------


def analyse(root: Path) -> dict:
    out: dict = {"checks": {}, "criteria": {}, "tables": {}}
    shas: set[str] = set()
    seeds_seen: set[int] = set()
    n_runs = 0

    g1: dict[str, list[dict]] = {}
    for label, stage in (("B", "stage1"), ("B+", "stage1"), ("B+G", "stage1"), ("robust", "stage5"), ("guarded", "stage5")):
        g1[label] = load_probe(root / f"{stage}-ramps-{label}.json")
    g15 = {label: load_probe(root / f"stage3b-ramps15-{label}.json") for label in ("B", "B+", "B+G")}
    onset = {label: load_probe(root / f"stage4-onset-{label}.json") for label in LABELS}
    camp2: dict[str, list[dict]] = {}
    camp3: dict[str, list[dict]] = {}
    summaries = {}
    for label in ("B", "B+", "B+G", "robust", "guarded"):
        camp2[label], summaries[f"stage2-{label}"] = load_campaign(root / f"stage2-{label}", label)
    for label in ("B", "B+", "B+G"):
        camp3[label], summaries[f"stage3-{label}"] = load_campaign(root / f"stage3-{label}", label)
    s0 = {}
    for d in ("stage0-bplus", "stage0-b"):
        s0[d], summaries[d] = load_campaign(root / d, "x")

    # B+G again with the gate streaks in the records (stages 2g and 3g): the classes must be identical
    gate_same = {}
    for stage, store in (("stage2", camp2), ("stage3", camp3)):
        again, summ = load_campaign(root / f"{stage}-B+G-gate", "B+G")
        summaries[f"{stage}-B+G-gate"] = summ
        ref = {(r["scenario"], r["seed"]): (r["cls"], r["iso"], r["hv"]) for r in store["B+G"]}
        gate_same[stage] = {"runs": len(again), "differences": sum(ref.get((r["scenario"], r["seed"])) != (r["cls"], r["iso"], r["hv"]) for r in again)}
        store["B+G"] = again
    for name, s in summaries.items():
        shas.add(s["binary_sha256"])
    for group in (*g1.values(), *g15.values(), *onset.values(), *camp2.values(), *camp3.values()):
        n_runs += len(group)
        seeds_seen |= {r["seed"] for r in group}
    n_runs += sum(len(v) for v in s0.values())
    out["checks"] = {
        "binary_sha256_in_campaign_summaries": sorted(shas),
        "single_binary": len(shas) == 1,
        "seeds_min_max": [min(seeds_seen), max(seeds_seen)],
        "only_development_seeds": all(5000 <= s <= 5099 for s in seeds_seen),
        "runs_analysed_including_stage0": n_runs,
        "template_sha256": {k: v["template_sha256"] for k, v in summaries.items()},
    }
    expected = {"G1": 5 * 2560, "G1_noise": 3 * 640, "onset": 5 * 1900, "stage2": 5 * 2400, "stage3": 3 * 2400, "stage0": 1400}
    got = {"G1": sum(map(len, g1.values())), "G1_noise": sum(map(len, g15.values())), "onset": sum(map(len, onset.values())),
           "stage2": sum(map(len, camp2.values())), "stage3": sum(map(len, camp3.values())), "stage0": sum(map(len, s0.values()))}
    out["checks"]["gate_rerun_identical_to_original_runs"] = gate_same
    out["checks"]["run_counts"] = {"expected": expected, "got": got, "ok": expected == got}

    # --- etapa 0 contra etapa 2: determinismo semente a semente --------------------------------
    det = []
    for d, label_map in (("stage0-bplus", "B+"), ("stage0-b", "B")):
        ref = {(r["scenario"], r["seed"]): r["cls"] for r in camp2[label_map]}
        diffs = [(r["scenario"], r["seed"]) for r in s0[d] if ref.get((r["scenario"], r["seed"])) != r["cls"]]
        det.append({"arm": label_map, "runs": len(s0[d]), "differences": len(diffs)})
    out["checks"]["stage0_vs_stage2_determinism"] = det

    # --- G1 -------------------------------------------------------------------------------------
    t: dict = {}
    for label in LABELS:
        rs = g1[label]
        for m in probe.RAMP_MAGS:
            sub = [r for r in rs if r["mag"] == m]
            unit = [r for r in sub if r["onset"] in UNIT_ONSETS and r["seed"] in UNIT_SEEDS]
            t[(label, m)] = {"full": count(sub, "cls2"), "unit80": count(unit, "cls2"), "n_full": len(sub), "n_unit": len(unit),
                             "wrong": sum(r["wrong"] for r in sub), "hv": sum(r["hv"] for r in sub),
                             "av": sum(r["av"] for r in sub), "ap": sum(r["ap"] for r in sub),
                             "iso": dict(collections.Counter(r["iso"] or "n/a" for r in sub)),
                             "inv_fail_runs": sum(bool(r["inv_fail"]) for r in sub)}
    out["tables"]["G1"] = {f"{k[0]}|{k[1]}": v for k, v in t.items()}

    crit: dict = {}
    # cláusula 2 (unidades de 80 e grelha completa)
    c2 = {}
    for m in probe.RAMP_MAGS:
        ub, ug = t[("B", m)]["unit80"]["U"], t[("B+G", m)]["unit80"]["U"]
        fb, fg = t[("B", m)]["full"]["U"], t[("B+G", m)]["full"]["U"]
        c2[str(m)] = {"unit80": {"U_B": ub, "U_B+": t[("B+", m)]["unit80"]["U"], "U_B+G": ug, "vacuous": ub == t[("B", m)]["n_unit"],
                                 "ok": ub == t[("B", m)]["n_unit"] or ug - ub <= 2},
                      "full": {"U_B": fb, "U_B+": t[("B+", m)]["full"]["U"], "U_B+G": fg, "limit": 16,
                               "vacuous": fb == t[("B", m)]["n_full"], "ok": fb == t[("B", m)]["n_full"] or fg - fb <= 16}}
    strat = {}
    for label in ("B", "B+", "B+G"):
        rs = [r for r in camp2[label] if r["scenario"] == "gnss_coherent_ramp" and r["seed"] in STRATUM]
        strat[label] = count(rs)
    c2["stratum18"] = {"classes": strat, "ok": strat["B+G"]["U"] - strat["B"]["U"] <= 2}
    crit["clause2"] = c2

    # S2: isolamento errado em 0,3 e 0,5
    pool = lambda label: [r for r in g1[label] if r["mag"] in (0.3, 0.5)]  # noqa: E731
    wb, wg = sum(r["wrong"] for r in pool("B+")), sum(r["wrong"] for r in pool("B+G"))
    n_pool = len(pool("B+G"))
    crit["S2"] = {"n": n_pool, "wrong_B+": wb, "wrong_B+G": wg, "cp_upper_B+G": cp_upper(wg, n_pool),
                  "reduction": None if wb == 0 else 1 - wg / wb, "validity_B+_at_least_60": wb >= 60,
                  "ok": wg <= 5 and wb >= 60 and wg <= 0.1 * wb}
    # S4: janela da ignição
    win = {}
    for label in ("B+", "B+G"):
        ins = [r for r in g1[label] if r["ign"] is not None and abs(r["onset"] - r["ign"]) <= 0.5]
        outs = [r for r in g1[label] if r["ign"] is not None and abs(r["onset"] - r["ign"]) > 0.5]
        win[label] = {"inside_n": len(ins), "inside_wrong": sum(r["wrong"] for r in ins), "outside_n": len(outs),
                      "outside_wrong": sum(r["wrong"] for r in outs),
                      "no_ignition_runs": sum(r["ign"] is None for r in g1[label])}
        win[label]["rate_inside"] = win[label]["inside_wrong"] / max(1, len(ins))
        win[label]["rate_outside"] = win[label]["outside_wrong"] / max(1, len(outs))
    crit["S4"] = {"windows": win, "ok": win["B+G"]["rate_inside"] <= win["B+G"]["rate_outside"]}
    # S6c: 0,8 m/s
    rb, rp, rg = (t[(x, 0.8)]["full"]["R"] for x in ("B", "B+", "B+G"))
    crit["S6c"] = {"R_B": rb, "R_B+": rp, "R_B+G": rg, "ok": rg >= rb and rg >= rp - 31}

    # --- M1 (etapa 2) -----------------------------------------------------------------------------
    cells = [c for c in camp.SCENARIOS if c != "altimeter_drift"]
    m1: dict = {}
    for sc in cells:
        row = {}
        for label in LABELS:
            rs = [r for r in camp2[label] if r["scenario"] == sc]
            row[label] = {"classes": count(rs), "wrong": sum(r["wrong"] for r in rs), "hv": sum(r["hv"] for r in rs),
                          "av": sum(r["av"] for r in rs), "inv_fail_runs": sum(bool(r["inv"]) for r in rs),
                          "iso": dict(collections.Counter(r["iso"] or "n/a" for r in rs))}
        m1[sc] = row
    out["tables"]["M1"] = m1
    distinct = [sc for sc in cells if sc != DISTINCT_SKIP and sc != "altimeter_drift"]
    # S6a, S6b, S6d, S7
    s6 = {}
    for sc in ("altimeter_stuck", "altimeter_delay", "gnss_coherent_ramp"):
        s6[sc] = {"R_B+": m1[sc]["B+"]["classes"]["R"], "R_B+G": m1[sc]["B+G"]["classes"]["R"],
                  "ok": m1[sc]["B+G"]["classes"]["R"] >= m1[sc]["B+"]["classes"]["R"] - 4}
    corr = lambda label: sum(m1[sc][label]["iso"].get("correct", 0) for sc in TRUE_CELLS)  # noqa: E731
    s6["correct_isolations"] = {"B+": corr("B+"), "B+G": corr("B+G"), "ok": corr("B+G") >= 0.7 * corr("B+")}
    crit["S6"] = s6
    s7 = {}
    for sc in distinct:
        a, b = m1[sc]["B+"], m1[sc]["B+G"]
        s7[sc] = {"U_B+": a["classes"]["U"], "U_B+G": b["classes"]["U"], "R_B+": a["classes"]["R"], "R_B+G": b["classes"]["R"],
                  "inv_B+": a["inv_fail_runs"], "inv_B+G": b["inv_fail_runs"],
                  "ok": b["classes"]["U"] <= a["classes"]["U"] + 2 and b["classes"]["R"] >= a["classes"]["R"] - 4
                  and b["inv_fail_runs"] <= a["inv_fail_runs"]}
    crit["S7"] = s7
    # identidade semente a semente prevista
    same = {}
    pred = [sc for sc in camp.FAMILIES["F3"]] + ["altimeter_bias", "altimeter_bias_low", "gnss_bias", "gnss_bias_low"]
    for sc in pred:
        a = {r["seed"]: (r["cls"], r["iso"]) for r in camp2["B+"] if r["scenario"] == sc}
        b = {r["seed"]: (r["cls"], r["iso"]) for r in camp2["B+G"] if r["scenario"] == sc}
        same[sc] = sum(a[s] != b.get(s) for s in a)
    crit["predicted_identical_cells_differences"] = same
    # V2
    v2 = {}
    for sc in distinct:
        g = m1[sc]["B+G"]["classes"]
        row = {}
        for base in ("robust", "guarded"):
            bc = m1[sc][base]["classes"]
            row[base] = {"U_base": bc["U"], "R_base": bc["R"], "U_B+G": g["U"], "R_B+G": g["R"],
                         "material": g["U"] > bc["U"] + 2 or bc["R"] - g["R"] >= 5}
        v2[sc] = row
    crit["V2"] = {"cells": v2, "violations": sorted(f"{sc}|{b}" for sc, row in v2.items() for b, x in row.items() if x["material"]),
                  "ok": not any(x["material"] for row in v2.values() for x in row.values())}

    # --- M3 e G1 com ruído ------------------------------------------------------------------------
    m3 = {label: {"n": len(camp3[label]), "classes": count(camp3[label]), "wrong": sum(r["wrong"] for r in camp3[label]),
                  "hv": sum(r["hv"] for r in camp3[label]), "av": sum(r["av"] for r in camp3[label]),
                  "ap": sum(r["ap"] for r in camp3[label])} for label in ("B", "B+", "B+G")}
    m3b = {label: {"n": len(g15[label]), "classes": count(g15[label], "cls2"), "wrong": sum(r["wrong"] for r in g15[label]),
                   "hv": sum(r["hv"] for r in g15[label]), "av": sum(r["av"] for r in g15[label])} for label in g15}
    out["tables"]["M3"] = m3
    out["tables"]["G1_noise"] = m3b
    c3 = {"M3_B+G_wrong": m3["B+G"]["wrong"], "M3_n": m3["B+G"]["n"], "M3_cp_upper": cp_upper(m3["B+G"]["wrong"], m3["B+G"]["n"]),
          "G1noise_B+G_wrong": m3b["B+G"]["wrong"], "G1noise_n": m3b["B+G"]["n"],
          "G1noise_cp_upper": cp_upper(m3b["B+G"]["wrong"], m3b["B+G"]["n"])}
    c3["ok"] = c3["M3_B+G_wrong"] == 0 and c3["G1noise_B+G_wrong"] == 0
    crit["clause3"] = c3

    # --- M4 --------------------------------------------------------------------------------------
    m4 = {}
    for label in LABELS:
        for kind in osw_kinds(onset[label]):
            sub = [r for r in onset[label] if r["kind"] == kind]
            m4[f"{label}|{kind}"] = {"classes": count(sub, "cls2"), "wrong": sum(r["wrong"] for r in sub),
                                     "hv": sum(r["hv"] for r in sub), "av": sum(r["av"] for r in sub),
                                     "worst_onset_R": min(((sum(r["cls2"] == "R" for r in sub if r["onset"] == o), o)
                                                           for o in sorted({r["onset"] for r in sub})))}
    out["tables"]["M4"] = m4

    # --- cláusula 1 e salvaguarda -----------------------------------------------------------------
    hv = {"G1": sum(r["hv"] for r in g1["B+G"]), "M1": sum(r["hv"] for r in camp2["B+G"]), "M3": m3["B+G"]["hv"],
          "G1_noise": m3b["B+G"]["hv"], "M4": sum(r["hv"] for r in onset["B+G"])}
    hv_b = {"G1": sum(r["hv"] for r in g1["B"]), "M1": sum(r["hv"] for r in camp2["B"]), "M3": m3["B"]["hv"],
            "G1_noise": m3b["B"]["hv"], "M4": sum(r["hv"] for r in onset["B"])}
    hv_bp = {"G1": sum(r["hv"] for r in g1["B+"]), "M1": sum(r["hv"] for r in camp2["B+"]), "M3": m3["B+"]["hv"],
             "G1_noise": m3b["B+"]["hv"], "M4": sum(r["hv"] for r in onset["B+"])}
    crit["clause1"] = {"B+G": hv, "B": hv_b, "B+": hv_bp, "ok": sum(hv.values()) == 0, "B_has_hv_rule_miscalibrated": sum(hv_b.values()) > 0}

    # --- invariantes de gnss_horizontal_bias -------------------------------------------------------
    inv = {}
    for label in ("B+", "B+G", "robust", "guarded", "B"):
        inv[label] = sorted((r["seed"], ",".join(r["inv"])) for r in camp2[label] if r["scenario"] == "gnss_horizontal_bias" and r["inv"])
    out["tables"]["gnss_horizontal_bias_invariants"] = inv

    # --- decomposição dos U de B+ e B+G a 0,5 m/s ------------------------------------------------
    dec = {}
    for label in ("B+", "B+G"):
        us = [r for r in g1[label] if r["mag"] == 0.5 and r["cls2"] == "U"]
        dec[label] = {"U": len(us), "iso": dict(collections.Counter(r["iso"] or "n/a" for r in us)),
                      "fail": dict(collections.Counter(",".join(sorted(r["fail"])) for r in us))}
    out["tables"]["U_decomposition_0.5"] = dec

    # --- sequências de rejeição ---------------------------------------------------------------------
    st = {}
    for name, group in (("G1", g1["B+G"]), ("G1_noise", g15["B+G"]), ("M4", onset["B+G"])):
        gs = [r["gate"] for r in group if r.get("gate")]
        ms = sorted(g["max_streak_cycles"] for g in gs)
        ac = sorted(g["max_active_cycles"] for g in gs)
        st[name] = {"runs": len(gs), "max_streak_max": ms[-1] if ms else None, "max_streak_median": ms[len(ms) // 2] if ms else None,
                    "max_active_max": ac[-1] if ac else None, "max_active_median": ac[len(ac) // 2] if ac else None,
                    "runs_with_rejections": sum(g["rejecting_cycles"] > 0 for g in gs),
                    "runs_streak_open_at_end": sum(g["streak_open_at_end"] for g in gs)}
    out["tables"]["gate_streaks"] = st

    wr = {}
    for label in ("B+", "B+G"):
        wr[label] = dict(collections.Counter(r["scenario"] for r in camp3[label] if r["wrong"]))
    out["tables"]["M3_wrong_by_cell"] = wr
    gs = {}
    for name, group in (("M1", camp2["B+G"]), ("M3", camp3["B+G"])):
        by = collections.defaultdict(list)
        for r in group:
            if r.get("gate"):
                by[r["scenario"]].append(r["gate"])
        gs[name] = {sc: {"max_streak_max": max(g["max_streak_cycles"] for g in gl),
                         "max_streak_median": sorted(g["max_streak_cycles"] for g in gl)[len(gl) // 2],
                         "runs_with_rejections": sum(g["rejecting_cycles"] > 0 for g in gl),
                         "runs_streak_open_at_end": sum(g["streak_open_at_end"] for g in gl), "runs": len(gl)} for sc, gl in by.items()}
    out["tables"]["gate_streaks_campaign"] = gs

    # --- veredictos ---------------------------------------------------------------------------------
    s = {
        "S1": crit["clause1"]["ok"],
        "S2": crit["S2"]["ok"],
        "S3": all(v["unit80"]["ok"] and v["full"]["ok"] for k, v in c2.items() if k != "stratum18") and c2["stratum18"]["ok"],
        "S4": crit["S4"]["ok"],
        "S5": c3["ok"],
        "S6": all(s6[sc]["ok"] for sc in TRUE_CELLS) and s6["correct_isolations"]["ok"] and crit["S6c"]["ok"],
        "S7": all(v["ok"] for v in s7.values()),
    }
    stop = {"clause1_hv": not crit["clause1"]["ok"],
            "clause2_U": not (all(v["unit80"]["ok"] and v["full"]["ok"] for k, v in c2.items() if k != "stratum18") and c2["stratum18"]["ok"]),
            "clause3_noise": not c3["ok"]}
    out["criteria"] = crit
    out["verdict"] = {"S": s, "stop_clauses_fired": stop, "V1": all(s.values()) and not any(stop.values()),
                      "V2": crit["V2"]["ok"], "advance": all(s.values()) and not any(stop.values()) and crit["V2"]["ok"]}
    out["_records"] = {"g1": g1, "g15": g15, "onset": onset, "camp2": camp2, "camp3": camp3}
    return out


def osw_kinds(rs: list[dict]) -> list[str]:
    return sorted({r["kind"] for r in rs})


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


def write_records(out: dict, path: Path) -> int:
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for stage, groups in out["_records"].items():
            for label, rs in groups.items():
                for r in rs:
                    if "scenario" in r:
                        row = [stage, r["scenario"], label, r["seed"], r["cls"], r["fail"], r["inv"], r["iso"], int(r["av"]), int(r["hv"]), int(r["ap"]), r.get("gate")]
                    else:
                        row = [stage, r["tag"].split("~", 2)[2], label, r["seed"], r["cls2"], r["fail"], r["inv_fail"], r["iso"],
                               int(r["av"]), int(r["hv"]), int(r["ap"]), r.get("gate"), r.get("ign")]
                    f.write(json.dumps(row, separators=(",", ":")) + "\n")
                    n += 1
    return n


def md_tables(out: dict) -> str:
    c, v = out["criteria"], out["verdict"]
    L: list[str] = ["# Resultados da reformulação do M10 (gerado por `scripts/m10_redesign_analysis.py`)", ""]
    L.append(f"Binário: `{out['checks']['binary_sha256_in_campaign_summaries']}`; um só binário: {out['checks']['single_binary']}; "
             f"sementes de desenvolvimento apenas: {out['checks']['only_development_seeds']}; contagens da matriz: {out['checks']['run_counts']['ok']}.")
    L.append("")
    L.append(f"**V1 (S1 a S7, sem cláusula de paragem disparada): {v['V1']}. V2 (limites contra `robust` e `guarded`): {v['V2']}. Avançar: {v['advance']}.**")
    L.append("")
    L.append("| Critério | Cumprido |")
    L.append("| --- | --- |")
    for k, ok in v["S"].items():
        L.append(f"| {k} | {ok} |")
    L.append("")
    L.append("Cláusulas de paragem disparadas: " + json.dumps(v["stop_clauses_fired"]))
    L.append("")
    L.append("## Cláusula 1 (falhas hv)")
    L.append("`" + json.dumps(c["clause1"]) + "`")
    L.append("")
    L.append("## Cláusula 2 (U de B+G contra U de B)")
    L.append("| Magnitude | unidade de 80: U B / B+ / B+G | vácua | ok | grelha: U B / B+ / B+G (limite 16) | vácua | ok |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for m, x in c["clause2"].items():
        if m == "stratum18":
            continue
        u, f = x["unit80"], x["full"]
        L.append(f"| {m} | {u['U_B']} / {u['U_B+']} / {u['U_B+G']} | {u['vacuous']} | {u['ok']} | {f['U_B']} / {f['U_B+']} / {f['U_B+G']} | {f['vacuous']} | {f['ok']} |")
    L.append(f"\nEstrato de 18 sementes: `{json.dumps(c['clause2']['stratum18'])}`")
    L.append("")
    L.append("## S2, S4, S6c, cláusula 3")
    for k in ("S2", "S4", "S6c", "clause3"):
        L.append(f"- {k}: `{json.dumps(c[k])}`")
    L.append("")
    L.append("## S6 (M1) e S7 por célula")
    L.append("`" + json.dumps(c["S6"]) + "`")
    L.append("")
    L.append("| Célula | U B+ | U B+G | R B+ | R B+G | inv B+ | inv B+G | S7 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for sc, x in c["S7"].items():
        L.append(f"| {sc} | {x['U_B+']} | {x['U_B+G']} | {x['R_B+']} | {x['R_B+G']} | {x['inv_B+']} | {x['inv_B+G']} | {x['ok']} |")
    L.append("")
    L.append("Diferenças semente a semente (B+G contra B+) nas células previstas idênticas: `" + json.dumps(c["predicted_identical_cells_differences"]) + "`")
    L.append("")
    L.append("## V2: regressões materiais contra `robust` e `guarded` (U acima em mais de 2, ou 5 ou mais R perdidas)")
    L.append("| Célula | base | U base | U B+G | R base | R B+G | material |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for sc, row in c["V2"]["cells"].items():
        for b, x in row.items():
            L.append(f"| {sc} | {b} | {x['U_base']} | {x['U_B+G']} | {x['R_base']} | {x['R_B+G']} | {x['material']} |")
    L.append("")
    L.append("## Tabelas")
    for name in ("U_decomposition_0.5", "gate_streaks", "gate_streaks_campaign", "M3", "M3_wrong_by_cell", "G1_noise", "gnss_horizontal_bias_invariants"):
        L.append(f"- {name}: `{json.dumps(out['tables'][name])}`")
    L.append("")
    L.append("### G1 por braço e magnitude (completa e unidade de 80)")
    L.append("| Braço | m/s | R/T/U grelha | R/T/U unidade | isolamento errado | hv | av | ap |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for k, x in out["tables"]["G1"].items():
        f, u = x["full"], x["unit80"]
        L.append(f"| {k.split('|')[0]} | {k.split('|')[1]} | {f['R']}/{f['T']}/{f['U']} | {u['R']}/{u['T']}/{u['U']} | {x['wrong']} | {x['hv']} | {x['av']} | {x['ap']} |")
    L.append("")
    L.append("### M4 (varrimento de início)")
    L.append("| Braço e falha | R/T/U | errado | hv | av | pior início (R, início) |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for k, x in out["tables"]["M4"].items():
        c3_ = x["classes"]
        L.append(f"| {k} | {c3_['R']}/{c3_['T']}/{c3_['U']} | {x['wrong']} | {x['hv']} | {x['av']} | {x['worst_onset_R']} |")
    L.append("")
    L.append("### M1 por célula (R/T/U; isolamento errado; hv)")
    L.append("| Célula | " + " | ".join(LABELS) + " |")
    L.append("| --- | " + " | ".join("---" for _ in LABELS) + " |")
    for sc, row in out["tables"]["M1"].items():
        cells = []
        for lb in LABELS:
            x = row[lb]
            cl = x["classes"]
            cells.append(f"{cl['R']}/{cl['T']}/{cl['U']} w{x['wrong']} h{x['hv']}")
        L.append(f"| {sc} | " + " | ".join(cells) + " |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    out = analyse(a.root)
    a.output.mkdir(parents=True, exist_ok=True)
    n = write_records(out, a.output / "records.jsonl.gz")
    records = out.pop("_records")
    del records
    (a.output / "analysis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    (a.output / "analysis.md").write_text(md_tables(out), encoding="utf-8")
    print("records", n, "V1", out["verdict"]["V1"], "V2", out["verdict"]["V2"], "advance", out["verdict"]["advance"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
