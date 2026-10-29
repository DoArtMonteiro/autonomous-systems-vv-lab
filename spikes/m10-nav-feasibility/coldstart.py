#!/usr/bin/env python3
"""Regra de arranque a frio da secao 8.4 do M10 no brinquedo vertical 1D (sementes 9000-9099).

NAO e evidencia para nenhuma hipotese do M10: e um brinquedo 1D com perfil e ruido do prototipo
feasibility.py (nao o do M9), sem barometro (conjunto E0). Serve para ver se a previsao da secao 8.4
tem sentido de ordem de grandeza. Apenas biblioteca padrao, determinista.

Regra: inicializa na primeira medida GNSS (z, vz) com a covariancia do ruido do GNSS; o radar comeca em
Probation e e admitido apos N_ADM ciclos seguidos com |radar - z previsto| <= G_ADM; depois entra no
filtro sem rejeicao. A sinalizacao de discordancia (escolha deste prototipo, a secao 8.4 nao a define):
radar ainda nao admitido ao fim de T_FLAG_S segundos com GNSS presente.
Os ganhos dependem so do passo de admissao, por isso guardam-se por passo de admissao.

Uso: python spikes/m10-nav-feasibility/coldstart.py > arranque.json
"""

import json
import math
import sys

import feasibility as f

N_ADM = 5
G_ADM = 3.0
T_FLAG_S = 1.0
TOL_HI, TOL_LO = 1.1, 0.36  # tolerancia de altitude de R1 (secao 8.1): acelerador minimo / de referencia
SEEDS = list(range(9000, 9100))

_SCHED = {}


def schedule(ka):
    """Ganhos do filtro com radar a partir do passo ka (None: so GNSS). Inicializa em k = 0 com o GNSS."""
    if ka in _SCHED:
        return _SCHED[ka]
    p = [[0.0] * 4 for _ in range(4)]
    p[0][0], p[1][1], p[2][2] = f.SIG_GZ**2, f.SIG_GV**2, f.ACC_BIAS_SIGMA**2
    p[3][3] = 1.0  # estado do barometro sem atualizacoes em E0: nao influencia z
    sched = [[]]
    for k in range(1, f.N + 1):
        p = f.matmul(f.matmul(f.F_MAT, p), f.transpose(f.F_MAT))
        p = [[p[i][j] + f.Q_MAT[i][j] for j in range(4)] for i in range(4)]
        names = []
        if ka is not None and k >= ka:
            names.append("R")
        if k % f.GNSS_EVERY == 0:
            names += ["Gz", "Gv"]
        ups = []
        for nm in names:
            p, g, s = f.joseph_update(p, f.H_ROWS[nm], f.R_VAR[nm])
            ups.append((f.CODE[nm], g[0], g[1], g[2], g[3], s))
        sched.append(ups)
    _SCHED[ka] = sched
    return sched


def track(sched, d):
    """Filtro com os ganhos dados. Devolve z estimado e z previsto (antes das atualizacoes) por passo."""
    z, v, ba = d["gz"][0], d["gv"][0], 0.0
    zs, zp = [z], [z]
    for k in range(1, f.N + 1):
        a = d["fm"][k - 1] - ba - f.G
        z += v * f.DT + a * 0.5 * f.DT * f.DT
        v += a * f.DT
        zp.append(z)
        for code, k0, k1, k2, _k3, _s in sched[k]:
            y = (d["radar"][k] - z) if code == 0 else (d["gz"][k] - z) if code == 1 else (d["gv"][k] - v)
            z += k0 * y
            v += k1 * y
            ba += k2 * y
        zs.append(z)
    return zs, zp


def run(seed, fault):
    d = f.gen_run(seed, fault=fault, onset_s=0.0)
    zs, zp = track(schedule(None), d)
    # radar e consultado a partir de k = 1 (k = 0 e a inicializacao); a previsao ate ka nao depende do radar
    ka, run_len = None, 0
    for k in range(1, f.N + 1):
        run_len = run_len + 1 if abs(d["radar"][k] - zp[k]) <= G_ADM else 0
        if run_len >= N_ADM:
            ka = k
            break
    if ka is not None:
        zs, _ = track(schedule(ka), d)
    err = zs[-1] - f.truth(f.N)[0]
    return ka, err


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def cell(fault):
    kas, errs = [], []
    for s in SEEDS:
        ka, e = run(s, fault)
        kas.append(ka)
        errs.append(e)
    adm = [k for k in kas if k is not None]
    n = len(SEEDS)
    out = {
        "fault": None if fault is None else "%s%+g" % fault,
        "admitted_fraction": len(adm) / n,
        "admission_time_s_min_median_max": [min(adm) * f.DT, pct(adm, 0.5) * f.DT, max(adm) * f.DT] if adm else None,
        "final_error_m_mean": sum(errs) / n,
        "final_error_m_abs_p50_p95_max": [pct([abs(e) for e in errs], q) for q in (0.5, 0.95, 1.0)],
        "frac_abs_err_le_1.1m": sum(abs(e) <= TOL_HI for e in errs) / n,
        "frac_abs_err_le_0.36m": sum(abs(e) <= TOL_LO for e in errs) / n,
    }
    # sinalizacao: radar nao admitido ao fim de T_FLAG_S (GNSS sempre presente neste brinquedo)
    flag_k = round(T_FLAG_S / f.DT)
    flagged = [k is None or k > flag_k for k in kas]
    out["disagreement_flag_fraction"] = sum(flagged) / n
    out["disagreement_flag_time_s"] = T_FLAG_S if any(flagged) else None
    return out


def main():
    cells = [("nominal", None)]
    for m in (5, 10, 20, 30):
        cells += [("radar_bias+%d" % m, ("R", float(m))), ("radar_bias-%d" % m, ("R", -float(m)))]
    for m in (5, 10, 30):
        cells += [("gnss_z_bias+%d" % m, ("G", float(m))), ("gnss_z_bias-%d" % m, ("G", -float(m)))]
    out = {"label": "BRINQUEDO 1D, sementes de desenvolvimento 9000-9099; NAO e evidencia do M10",
           "command": "python spikes/m10-nav-feasibility/coldstart.py",
           "params": {"N_adm": N_ADM, "g_adm_m": G_ADM, "flag_after_s": T_FLAG_S, "steps": f.N, "descent_s": f.N * f.DT},
           "cells": {}}
    for name, flt in cells:
        out["cells"][name] = cell(flt)
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
