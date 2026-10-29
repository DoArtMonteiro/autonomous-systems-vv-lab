#!/usr/bin/env python3
"""Prototipo de viabilidade M10: canal vertical 1D, sementes de desenvolvimento.

NAO e a implementacao do M10 e NAO e evidencia para nenhuma hipotese do M10. Serve para verificar
ordens de grandeza do documento docs/m10-resilient-navigation.md (observabilidade, atrasos de
deteccao, consistencia). Apenas biblioteca padrao. Determinista: todas as sementes sao explicitas
e pertencem ao bloco de DESENVOLVIMENTO 9000-9099 (nao sao sementes de avaliacao).

Modelo: descida vertical com desaceleracao constante (perfil de brinquedo, nao o do M9), sensores com
os desvios do repositorio (radar 0,1 m a 50 Hz; GNSS z 0,5 m e vz 0,05 m/s a 10 Hz; IMU 0,02 m/s^2
a 50 Hz), baro proposto (25 Hz, 0,5 m, desvio inicial e deriva) e bias do acelerometro.
Ruido: Irwin-Hall como o repositorio, sigma*sqrt(3)*(u1+u2+u3+u4-2), limitado a +-2*sqrt(3)*sigma.
`random.Random` (Mersenne Twister) NAO e o SplitMix64 do repositorio.

Filtro: Kalman linear de 4 estados [z, v, b_acel, b_baro], forma de Joseph. Sem rejeicao em malha
fechada, por isso a covariancia nao depende dos dados: calcula-se uma vez por filtro (principal e um
subfiltro por fonte de altitude excluida: radar R, GNSS G, baro B) e os ganhos sao reutilizados em
cada semente. A igualdade com o filtro de covariancia completa e verificada numa semente.

Uso: python spikes/m10-nav-feasibility/feasibility.py > resumo.json
"""

import json
import math
import platform
import random
import statistics
import sys
import time

# --- perfil e sensores -------------------------------------------------------------------------
DT = 0.02  # ciclo de controlo (50 Hz)
G = 9.80665
Z0, V0, VT = 2000.0, -230.0, -1.5
A_NET = (V0 * V0 - VT * VT) / (2.0 * Z0)  # desaceleracao liquida constante (m/s^2)
N = int(round((VT - V0) / A_NET / DT))  # passos de controlo
F_TRUE = A_NET + G  # forca especifica verdadeira (m/s^2)

SIG_RADAR, SIG_GZ, SIG_GV, SIG_ACC = 0.1, 0.5, 0.05, 0.02
GNSS_EVERY = 5  # 10 Hz
BARO_EVERY = 2  # 25 Hz (proposto)
SIG_BARO = 0.5
BARO_OFFSET_SIGMA = 2.0  # desvio inicial do baro relativo ao referencial do solo (proposto)
BARO_RW = 0.05  # deriva do baro em m/sqrt(s) (proposto)
ACC_BIAS_SIGMA = 0.05  # bias do acelerometro nominal, m/s^2 (a gama de falha do M9 e 0,05 a 0,5)
ACC_BIAS_RW = 1e-3  # passeio aleatorio do bias no filtro, m/s^2/sqrt(s)
P0 = [1.0**2, 0.2**2, ACC_BIAS_SIGMA**2, BARO_OFFSET_SIGMA**2]
COLD_P0 = [50.0**2, 2.0**2, ACC_BIAS_SIGMA**2, BARO_OFFSET_SIGMA**2]
COLD_E0 = (50.0, 2.0)
COLD_MAGNITUDES = [5.0, 10.0, 30.0]
CFG = {"p0": P0, "e0": (1.0, 0.2)}

# --- parametros do detetor -----------------------------------------------------------------------
K_FA = 4.0  # limiar de separacao (em desvios-padrao da separacao)
K_MD = 3.0  # fator de deteccao falhada para o nivel de protecao
K_FF = 5.33  # fator sem falha para o nivel de protecao
ISO_WINDOW_S = 1.0  # atraso/janela do isolamento por NIS
MAGNITUDES = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0]
ONSETS_S = [8.0, 15.0]  # 8 s: cerca de 580 m; 15 s: cerca de 38 m (perfil de brinquedo)
SOURCES = ["R", "G", "B"]
SEEDS_NOMINAL = list(range(9000, 9100))
SEEDS_FAULT = list(range(9000, 9100))
FA_SWEEP = [2.0, 2.5, 3.0, 3.5, 4.0]
NEES_STEPS = [100, 400, 600, 800]  # passos onde se avalia o NEES (2, 8, 12, 16 s)


def noise(rng, sigma):
    """Ruido do repositorio: Irwin-Hall com desvio-padrao sigma, limitado a +-2*sqrt(3)*sigma."""
    s = math.sqrt(3.0) * sigma * (rng.random() + rng.random() + rng.random() + rng.random() - 2.0)
    bound = 2.0 * math.sqrt(3.0) * sigma
    return max(-bound, min(bound, s))


def phi_tail2(k):
    """P(|Z| > k) para N(0,1)."""
    return math.erfc(k / math.sqrt(2.0))


# --- algebra 4x4 minima --------------------------------------------------------------------------
def matmul(a, b):
    n = len(a)
    return [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]


def transpose(a):
    return [list(r) for r in zip(*a)]


def inverse(a):
    n = len(a)
    m = [list(a[i]) + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        d = m[c][c]
        m[c] = [x / d for x in m[c]]
        for r in range(n):
            if r != c:
                f = m[r][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [row[n:] for row in m]


F_MAT = [
    [1.0, DT, -0.5 * DT * DT, 0.0],
    [0.0, 1.0, -DT, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]
G_VEC = [0.5 * DT * DT, DT, 0.0, 0.0]
Q_MAT = [[SIG_ACC**2 * G_VEC[i] * G_VEC[j] for j in range(4)] for i in range(4)]
Q_MAT[2][2] += ACC_BIAS_RW**2 * DT
Q_MAT[3][3] += BARO_RW**2 * DT

H_ROWS = {
    "R": [1.0, 0.0, 0.0, 0.0],
    "Gz": [1.0, 0.0, 0.0, 0.0],
    "Gv": [0.0, 1.0, 0.0, 0.0],
    "B": [1.0, 0.0, 0.0, 1.0],
}
R_VAR = {"R": SIG_RADAR**2, "Gz": SIG_GZ**2, "Gv": SIG_GV**2, "B": SIG_BARO**2}
CODE = {"R": 0, "Gz": 1, "Gv": 2, "B": 3}


def joseph_update(p, h, r):
    """Atualizacao escalar na forma de Joseph. Devolve (P novo, ganho K, variancia da inovacao S)."""
    ph = [sum(p[i][j] * h[j] for j in range(4)) for i in range(4)]
    s = sum(h[i] * ph[i] for i in range(4)) + r
    k = [x / s for x in ph]
    a = [[(1.0 if i == j else 0.0) - k[i] * h[j] for j in range(4)] for i in range(4)]
    pn = matmul(matmul(a, p), transpose(a))
    pn = [[pn[i][j] + r * k[i] * k[j] for j in range(4)] for i in range(4)]
    pn = [[0.5 * (pn[i][j] + pn[j][i]) for j in range(4)] for i in range(4)]
    return pn, k, s


PRIORS = {}


def updates_at(step, excluded):
    """Atualizacoes escalares do passo (ordem fixa), sem o grupo excluido."""
    out = []
    if excluded == "H":  # canal horizontal so com GNSS
        return ["Gz", "Gv"] if step % GNSS_EVERY == 0 else []
    if excluded != "R":
        out.append("R")
    if excluded != "G" and step % GNSS_EVERY == 0:
        out += ["Gz", "Gv"]
    if excluded != "B" and step % BARO_EVERY == 0:
        out.append("B")
    return out


def build_schedule(excluded, keep_p=False):
    """Covariancia e ganhos de um filtro ao longo do perfil. Independente dos dados."""
    p = [[CFG["p0"][i] if i == j else 0.0 for j in range(4)] for i in range(4)]
    sched, p00, p_list = [], [], []
    prior_z, prior_b = [], []
    n_updates = 0
    for k in range(N + 1):
        if k > 0:
            p = matmul(matmul(F_MAT, p), transpose(F_MAT))
            p = [[p[i][j] + Q_MAT[i][j] for j in range(4)] for i in range(4)]
        prior_z.append(p[0][0])
        prior_b.append(p[0][0] + 2.0 * p[0][3] + p[3][3])
        ups = []
        for name in updates_at(k, excluded):
            p, gain, s = joseph_update(p, H_ROWS[name], R_VAR[name])
            ups.append((CODE[name], gain[0], gain[1], gain[2], gain[3], s))
            n_updates += 1
        sched.append(ups)
        p00.append(p[0][0])
        if keep_p:
            p_list.append([row[:] for row in p])
    PRIORS[excluded] = (prior_z, prior_b)
    return sched, p00, p_list, n_updates


# --- simulacao -----------------------------------------------------------------------------------
def truth(k):
    t = k * DT
    return Z0 + V0 * t + 0.5 * A_NET * t * t, V0 + A_NET * t


def gen_run(seed, fault=None, onset_s=8.0):
    """Medidas de uma semente. fault = (fonte, magnitude) aplica um degrau em onset_s."""
    rng = random.Random(seed)
    ba = noise(rng, ACC_BIAS_SIGMA)
    bb0 = noise(rng, BARO_OFFSET_SIGMA)
    e0 = (noise(rng, CFG["e0"][0]), noise(rng, CFG["e0"][1]))
    kf = int(round(onset_s / DT))
    radar, gz, gv, baro, fm, bb = [], {}, {}, {}, [], []
    drift = 0.0
    for k in range(N + 1):
        z, v = truth(k)
        if k > 0:
            drift += noise(rng, BARO_RW * math.sqrt(DT))
        bb.append(bb0 + drift)
        dr = dg = db = 0.0
        if fault and k >= kf:
            src, mag = fault
            dr = mag if src == "R" else 0.0
            dg = mag if src == "G" else 0.0
            db = mag if src == "B" else 0.0
        radar.append(z + noise(rng, SIG_RADAR) + dr)
        if k % GNSS_EVERY == 0:
            gz[k] = z + noise(rng, SIG_GZ) + dg
            gv[k] = v + noise(rng, SIG_GV)
        if k % BARO_EVERY == 0:
            baro[k] = z + bb[k] + noise(rng, SIG_BARO) + db
        fm.append(F_TRUE + ba + noise(rng, SIG_ACC))
    return {"radar": radar, "gz": gz, "gv": gv, "baro": baro, "fm": fm, "ba": ba, "bb": bb, "e0": e0, "x0": (Z0 + e0[0], V0 + e0[1])}


def run_filter(sched, data, want_state_at=(), keep_innov=False):
    """Atualiza o estado com os ganhos pre-calculados. Devolve z estimado, NIS por passo, estados."""
    z, v = data["x0"]
    ba, bb = 0.0, 0.0
    grav = data.get("g", G)
    innov = []
    radar, gz, gv, baro, fm = data["radar"], data["gz"], data["gv"], data["baro"], data["fm"]
    zs = [0.0] * (N + 1)
    nis = [0.0] * (N + 1)
    cnt = [0] * (N + 1)
    states = {}
    half_dt2 = 0.5 * DT * DT
    for k in range(N + 1):
        if k > 0:
            a = fm[k - 1] - ba - grav
            z = z + v * DT + a * half_dt2
            v = v + a * DT
        for code, k0, k1, k2, k3, s in sched[k]:
            if code == 0:
                y = radar[k] - z
            elif code == 1:
                y = gz[k] - z
            elif code == 2:
                y = gv[k] - v
            else:
                y = baro[k] - z - bb
            if keep_innov:
                innov.append((k, code, y / math.sqrt(s)))
            z += k0 * y
            v += k1 * y
            ba += k2 * y
            bb += k3 * y
            nis[k] += y * y / s
            cnt[k] += 1
        zs[k] = z
        if k in want_state_at:
            states[k] = (z, v, ba, bb)
    if keep_innov:
        return zs, nis, cnt, states, innov
    return zs, nis, cnt, states


def percentile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = min(len(xs) - 1, max(0, int(math.ceil(q * len(xs))) - 1))
    return xs[i]


def clopper_upper(k, n, alpha=0.05):
    """Limite superior unilateral de Clopper-Pearson (bisseccao sobre a binomial)."""
    if k >= n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        cdf = sum(math.comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(k + 1))
        if cdf > alpha:
            lo = mid
        else:
            hi = mid
    return hi


# --- canal horizontal so com GNSS (brinquedo adicional) -------------------------------------------
H_P0, H_V = 80.0, -12.0


def gen_h(seed, fault=None, onset_s=8.0):
    """Posicao horizontal com velocidade constante. fault = (tipo, valor): step (m), ramp (m/s, so
    posicao), coherent (m/s, posicao e velocidade coerentes)."""
    rng = random.Random(seed)
    ba = noise(rng, ACC_BIAS_SIGMA)
    e0 = (noise(rng, 1.0), noise(rng, 0.2))
    kf = int(round(onset_s / DT))
    gz, gv, fm = {}, {}, []
    for k in range(N + 1):
        t = k * DT
        bp = bv = 0.0
        if fault and k >= kf:
            kind, val = fault
            if kind == "step":
                bp = val
            elif kind == "ramp":
                bp = val * (t - onset_s)
            else:
                bp, bv = val * (t - onset_s), val
        if k % GNSS_EVERY == 0:
            gz[k] = H_P0 + H_V * t + noise(rng, SIG_GZ) + bp
            gv[k] = H_V + noise(rng, SIG_GV) + bv
        fm.append(ba + noise(rng, SIG_ACC))
    return {"gz": gz, "gv": gv, "fm": fm, "radar": None, "baro": {}, "g": 0.0,
            "x0": (H_P0 + e0[0], H_V + e0[1])}


def horizontal_alarm(innov, kf, window=20):
    """Primeiro instante (passo) com alarme: inovacao de posicao ou velocidade isolada acima de K_FA,
    ou media de `window` inovacoes de posicao (ou de velocidade) acima de K_FA/sqrt(window)."""
    buf = {1: [], 2: []}
    first = {"single": None, "window": None}
    for k, code, y in innov:
        b = buf[code]
        b.append(y)
        if len(b) > window:
            b.pop(0)
        if first["single"] is None and abs(y) > K_FA:
            first["single"] = k
        if first["window"] is None and len(b) == window and abs(sum(b)) / math.sqrt(window) > K_FA:
            first["window"] = k
    return first


def horizontal_study(sched):
    out = {"nominal": {}, "cells": []}
    nom = {"single": 0, "window": 0}
    for seed in SEEDS_NOMINAL:
        d = gen_h(seed)
        _, _, _, _, innov = run_filter(sched, d, keep_innov=True)
        f = horizontal_alarm(innov, 0)
        for key in nom:
            nom[key] += 1 if f[key] is not None else 0
    out["nominal"] = {"runs": len(SEEDS_NOMINAL), "false_alarm_runs": nom}
    onset_s = 8.0
    kf = int(round(onset_s / DT))
    cases = [("step", v) for v in (1.0, 3.0, 5.0, 10.0, 30.0)]
    cases += [("ramp", v) for v in (0.03, 0.05, 0.1, 0.3, 1.0, 3.0)]
    cases += [("coherent", v) for v in (0.1, 0.3, 1.0, 3.0)]
    t_end = N * DT
    for kind, val in cases:
        res = {"single": [], "window": []}
        err_end = []
        for seed in SEEDS_FAULT:
            d = gen_h(seed, (kind, val), onset_s)
            zs, _, _, _, innov = run_filter(sched, d, keep_innov=True)
            f = horizontal_alarm(innov, kf)
            for key in res:
                # so alarmes depois do inicio contam como deteccao (alarmes antes sao falsos alarmes)
                innov_after = [x for x in innov if x[0] >= kf]
                fa = horizontal_alarm(innov_after, kf)
                res[key].append(None if fa[key] is None else (fa[key] - kf) * DT)
            err_end.append(abs(zs[N] - (H_P0 + H_V * t_end)))
        row = {"fault": kind, "value": val, "runs": len(SEEDS_FAULT),
               "offset_at_end_if_undetected_m": val if kind == "step" else val * (t_end - onset_s),
               "median_estimate_error_at_end_m": statistics.median(err_end)}
        for key in res:
            det = [x for x in res[key] if x is not None]
            row[key] = {"detected": len(det), "median_delay_s": statistics.median(det) if det else None,
                        "p90_delay_s": percentile(det, 0.9)}
        out["cells"].append(row)
    return out


def main():
    t_total = time.perf_counter()
    names = [None, "R", "G", "B"]  # indice 0 = filtro principal; 1..3 = subfiltros
    scheds, p00s, n_upd = {}, {}, {}
    t0 = time.perf_counter()
    for ex in names:
        s, p00, plist, nu = build_schedule(ex, keep_p=(ex in (None, "G")))
        scheds[ex], p00s[ex], n_upd[ex] = s, p00, nu
        if ex is None:
            p_full = plist
        if ex == "G":
            p_noG = plist
    t_sched = time.perf_counter() - t0
    sig_delta = {ex: [math.sqrt(max(p00s[ex][k] - p00s[None][k], 1e-12)) for k in range(N + 1)] for ex in SOURCES}
    thr_floor = 1e-9
    nees_inv = {k: inverse(p_full[k]) for k in NEES_STEPS}
    kiso = int(round(ISO_WINDOW_S / DT))

    def analyse(data, want_nees=False):
        zs, nis, cnt, st = {}, {}, {}, {}
        for ex in names:
            zs[ex], nis[ex], cnt[ex], st[ex] = run_filter(scheds[ex], data, NEES_STEPS if (want_nees and ex is None) else ())
        return zs, nis, cnt, st

    def stats_for_run(data, zs, nis, cnt):
        """Estatisticas de separacao normalizadas e alarmes por passo."""
        ratio = {ex: [abs(zs[None][k] - zs[ex][k]) / max(sig_delta[ex][k], thr_floor) for k in range(N + 1)] for ex in SOURCES}
        return ratio

    # --- autoverificacao: filtro de covariancia completa vs ganhos pre-calculados -----------------
    d = gen_run(SEEDS_NOMINAL[0])
    zs_chk, _, _, _ = run_filter(scheds[None], d)
    x = [d["x0"][0], d["x0"][1], 0.0, 0.0]
    p = [[CFG["p0"][i] if i == j else 0.0 for j in range(4)] for i in range(4)]
    worst_diff = 0.0
    for k in range(N + 1):
        if k > 0:
            a = d["fm"][k - 1] - x[2] - G
            x = [x[0] + x[1] * DT + 0.5 * a * DT * DT, x[1] + a * DT, x[2], x[3]]
            p = matmul(matmul(F_MAT, p), transpose(F_MAT))
            p = [[p[i][j] + Q_MAT[i][j] for j in range(4)] for i in range(4)]
        for name in updates_at(k, None):
            h = H_ROWS[name]
            meas = {"R": d["radar"][k], "Gz": d["gz"].get(k), "Gv": d["gv"].get(k), "B": d["baro"].get(k)}[name]
            innov = meas - sum(h[i] * x[i] for i in range(4))
            p, gain, _ = joseph_update(p, h, R_VAR[name])
            x = [x[i] + gain[i] * innov for i in range(4)]
        worst_diff = max(worst_diff, abs(x[0] - zs_chk[k]))

    # --- nominal -------------------------------------------------------------------------------------
    t_filter = 0.0
    n_filter_cycles = 0
    nominal_sweep_runs = {kk: 0 for kk in FA_SWEEP}
    sample_exceed = {kk: 0 for kk in FA_SWEEP}
    samples = 0
    nees_sum = {k: 0.0 for k in NEES_STEPS}
    nis_radar, nis_radar_n = 0.0, 0
    radar_exceed = {2.0: 0, 3.0: 0, 4.0: 0}
    pl_exceed_samples = 0
    nominal_final_err = []
    for seed in SEEDS_NOMINAL:
        data = gen_run(seed)
        t1 = time.perf_counter()
        zs, nis, cnt, st = analyse(data, want_nees=True)
        t_filter += time.perf_counter() - t1
        n_filter_cycles += 4 * (N + 1)
        ratio = stats_for_run(data, zs, nis, cnt)
        for kk in FA_SWEEP:
            hit = False
            for ex in SOURCES:
                r = ratio[ex]
                c = sum(1 for x in r if x > kk)
                sample_exceed[kk] += c
                if c:
                    hit = True
            if hit:
                nominal_sweep_runs[kk] += 1
        samples += 3 * (N + 1)
        for k in NEES_STEPS:
            z_, v_, ba_, bb_ = st[None][k]
            zt, vt = truth(k)
            e = [z_ - zt, v_ - vt, ba_ - data["ba"], bb_ - data["bb"][k]]
            ie = nees_inv[k]
            nees_sum[k] += sum(e[i] * ie[i][j] * e[j] for i in range(4) for j in range(4))
        # NIS do radar no filtro principal (graus de liberdade 1)
        # recalcula as inovacoes normalizadas do radar para as fracoes de excedencia
        for k in range(N + 1):
            s_r = scheds[None][k][0][5]
            # o NIS total do passo inclui todas as atualizacoes; separa o do radar a partir do passo
            # sem GNSS/baro (so radar): nesse caso nis[k] e o NIS do radar
            if len(scheds[None][k]) == 1:
                nis_radar += nis[None][k]
                nis_radar_n += 1
                for kk in radar_exceed:
                    if nis[None][k] > kk * kk:
                        radar_exceed[kk] += 1
        # nivel de protecao fora de falha
        for k in range(N + 1):
            sig_full = math.sqrt(p00s[None][k])
            pl = K_FF * sig_full
            for ex in SOURCES:
                t_i = K_FA * sig_delta[ex][k]
                pl = max(pl, t_i + K_MD * math.sqrt(p00s[ex][k]))
            if abs(zs[None][k] - truth(k)[0]) > pl:
                pl_exceed_samples += 1
        nominal_final_err.append(abs(zs[None][N] - truth(N)[0]))
    nees_mean = {str(round(k * DT, 2)): nees_sum[k] / len(SEEDS_NOMINAL) for k in NEES_STEPS}
    n_nom = len(SEEDS_NOMINAL)
    nees_lo = 4.0 - 1.96 * math.sqrt(2.0 * 4.0 / n_nom)
    nees_hi = 4.0 + 1.96 * math.sqrt(2.0 * 4.0 / n_nom)

    def fault_cells(onsets, mags):
        nonlocal t_filter, n_filter_cycles
        cells = []
        for onset_s in onsets:
          kf = int(round(onset_s / DT))
          for src in SOURCES:
            for mag in mags:
                delays, iso_instant_ok, iso_nis_ok, n_det = [], 0, 0, 0
                pre_fa = 0
                missed_samples = 0
                err_full, err_reconf = [], []
                n_iso_eval = 0
                for seed in SEEDS_FAULT:
                    data = gen_run(seed, (src, mag), onset_s)
                    t1 = time.perf_counter()
                    zs, nis, cnt, st = analyse(data)
                    t_filter += time.perf_counter() - t1
                    n_filter_cycles += 4 * (N + 1)
                    ratio = stats_for_run(data, zs, nis, cnt)
                    first = None
                    for k in range(N + 1):
                        if any(ratio[ex][k] > K_FA for ex in SOURCES):
                            if k < kf:
                                pre_fa += 1
                                break
                            first = k
                            break
                    # pre-onset alarm does not hide post-onset detection: find first exceedance after onset
                    if first is None or first < kf:
                        first = next((k for k in range(kf, N + 1) if any(ratio[ex][k] > K_FA for ex in SOURCES)), None)
                    # integridade: erro acima do PL antes do primeiro alarme pos-inicio
                    end_alarm = first if first is not None else N + 1
                    for k in range(kf, end_alarm):
                        pl = K_FF * math.sqrt(p00s[None][k])
                        for ex in SOURCES:
                            pl = max(pl, K_FA * sig_delta[ex][k] + K_MD * math.sqrt(p00s[ex][k]))
                        if abs(zs[None][k] - truth(k)[0]) > pl:
                            missed_samples += 1
                    zt_end = truth(N)[0]
                    err_full.append(abs(zs[None][N] - zt_end))
                    if first is None:
                        err_reconf.append(abs(zs[None][N] - zt_end))
                        continue
                    n_det += 1
                    delays.append((first - kf) * DT)
                    # isolamento instantaneo: maior separacao normalizada
                    pick = max(SOURCES, key=lambda ex: ratio[ex][first])
                    iso_instant_ok += 1 if pick == src else 0
                    # isolamento por NIS na janela [first, first+kiso]: subfiltro mais consistente
                    k_end = min(N, first + kiso)
                    score = {}
                    for ex in SOURCES:
                        tot = sum(nis[ex][k] for k in range(first, k_end + 1))
                        c = sum(cnt[ex][k] for k in range(first, k_end + 1))
                        score[ex] = tot / max(c, 1)
                    pick2 = min(SOURCES, key=lambda ex: score[ex])
                    iso_nis_ok += 1 if pick2 == src else 0
                    n_iso_eval += 1
                    # reconfiguracao: usa o subfiltro escolhido depois de first+kiso
                    err_reconf.append(abs(zs[pick2][N] - zt_end))
                cells.append({
                    "onset_s": onset_s, "source": src, "magnitude_m": mag, "runs": len(SEEDS_FAULT),
                    "detected": n_det,
                    "detection_delay_s": {
                        "median": percentile(delays, 0.5), "p90": percentile(delays, 0.9), "max": max(delays) if delays else None,
                    },
                    "isolation_correct_max_separation": iso_instant_ok,
                    "isolation_correct_min_nis": iso_nis_ok,
                    "isolation_evaluated": n_iso_eval,
                    "alarm_before_onset_runs": pre_fa,
                    "missed_alert_samples_before_alarm": missed_samples,
                    "final_abs_error_m": {
                        "full_filter_median": statistics.median(err_full),
                        "full_filter_max": max(err_full),
                        "reconfigured_median": statistics.median(err_reconf),
                        "reconfigured_max": max(err_reconf),
                    },
                })
        return cells

    # --- falhas ------------------------------------------------------------------------------------
    cells = fault_cells(ONSETS_S, MAGNITUDES)
    # --- arranque a frio: prior de altitude nao informativo, falha presente desde o instante 0 ----
    saved = (CFG["p0"], CFG["e0"])
    CFG["p0"], CFG["e0"] = COLD_P0, COLD_E0
    scheds_w, p00s_w, sig_w = scheds, p00s, sig_delta
    scheds, p00s, n_upd_c = {}, {}, {}
    for ex in names:
        s_, p00_, _, nu_ = build_schedule(ex)
        scheds[ex], p00s[ex] = s_, p00_
    sig_delta = {ex: [math.sqrt(max(p00s[ex][k] - p00s[None][k], 1e-12)) for k in range(N + 1)] for ex in SOURCES}
    cold_cells = fault_cells([0.0], COLD_MAGNITUDES)
    CFG["p0"], CFG["e0"] = saved
    scheds, p00s, sig_delta = scheds_w, p00s_w, sig_w

    # --- sigma e MDB analitico aproximado por instante ---------------------------------------------
    z_beta = 1.2816  # potencia 0,90 (unilateral)
    sched_h, p00_h, _, _ = build_schedule("H")
    mdb_rows = []
    for t_s in (4.0, 8.0, 12.0, 15.0):
        k = int(round(t_s / DT))
        s_r = PRIORS["R"][0][k] + R_VAR["R"]
        s_g = PRIORS["G"][0][k] + R_VAR["Gz"]
        mdb_rows.append({
            "t_s": t_s, "z_m": round(truth(k)[0], 1),
            "sigma_z_full_m": math.sqrt(p00s[None][k]),
            "sigma_z_without_R_m": math.sqrt(p00s["R"][k]),
            "sigma_z_without_G_m": math.sqrt(p00s["G"][k]),
            "sigma_z_without_B_m": math.sqrt(p00s["B"][k]),
            "sigma_bias_acc_full_mps2": math.sqrt(p_full[k][2][2]),
            "sigma_bias_acc_without_G_mps2": math.sqrt(p_noG[k][2][2]),
            "sigma_baro_offset_full_m": math.sqrt(p_full[k][3][3]),
            "sigma_separation_R_m": sig_delta["R"][k], "sigma_separation_G_m": sig_delta["G"][k],
            "sigma_separation_B_m": sig_delta["B"][k],
            "mdb_single_sample_R_m": (K_FA + z_beta) * math.sqrt(s_r),
            "mdb_single_sample_G_m": (K_FA + z_beta) * math.sqrt(s_g),
        })
    horizontal = horizontal_study(sched_h)

    # --- custo por atualizacao -----------------------------------------------------------------------
    # (a) caminho de estado com ganhos pre-calculados: tempo medido em volta de cada execucao de 4 filtros
    per_cycle_state_us = t_filter / n_filter_cycles * 1e6
    # (b) filtro de covariancia completa (Joseph): reconstrucao do calendario do filtro principal
    reps = 5
    t1 = time.perf_counter()
    for _ in range(reps):
        build_schedule(None)
    t_cov = time.perf_counter() - t1
    per_cycle_cov_us = t_cov / (reps * (N + 1)) * 1e6
    per_update_cov_us = t_cov / (reps * n_upd[None]) * 1e6

    theory_sample = {str(kk): phi_tail2(kk) for kk in FA_SWEEP}
    emp_sample = {str(kk): sample_exceed[kk] / samples for kk in FA_SWEEP}
    runs_alarm = {str(kk): nominal_sweep_runs[kk] for kk in FA_SWEEP}
    out = {
        "label": "prototipo de viabilidade, canal vertical, sementes de desenvolvimento (NAO e evidencia do M10)",
        "command": "python spikes/m10-nav-feasibility/feasibility.py",
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "profile": {
            "z0_m": Z0, "v0_mps": V0, "v_end_mps": VT, "net_decel_mps2": round(A_NET, 4),
            "specific_force_mps2": round(F_TRUE, 4), "cycles": N + 1, "dt_s": DT, "fault_onsets_s": ONSETS_S,
        },
        "seeds": {"nominal": [SEEDS_NOMINAL[0], SEEDS_NOMINAL[-1]], "fault": [SEEDS_FAULT[0], SEEDS_FAULT[-1]],
                  "note": "bloco de desenvolvimento; nao sao sementes de avaliacao"},
        "detector": {"K_fa": K_FA, "K_md": K_MD, "K_ff": K_FF, "isolation_window_s": ISO_WINDOW_S},
        "self_check_max_abs_diff_z_m": worst_diff,
        "nominal": {
            "runs": n_nom,
            "false_alarm_runs_by_threshold_k": runs_alarm,
            "false_alarm_runs_chosen_k": nominal_sweep_runs[K_FA],
            "false_alarm_rate_upper95_clopper_pearson_chosen_k": clopper_upper(nominal_sweep_runs[K_FA], n_nom),
            "per_sample_exceedance_empirical": emp_sample,
            "per_sample_exceedance_gaussian_theory": theory_sample,
            "radar_nis_mean_radar_only_steps": nis_radar / max(nis_radar_n, 1),
            "radar_nis_exceed_fraction_k2_k3_k4": {str(kk): radar_exceed[kk] / max(nis_radar_n, 1) for kk in radar_exceed},
            "nees_mean_dim4_by_time_s": nees_mean,
            "nees_95_interval_for_mean_of_runs": [nees_lo, nees_hi],
            "samples_error_above_protection_level": pl_exceed_samples,
            "final_abs_error_m_median_max": [statistics.median(nominal_final_err), max(nominal_final_err)],
        },
        "analytic_mdb_approx": mdb_rows,
        "faults": cells,
        "faults_cold_start": cold_cells,
        "horizontal_gnss_only_channel": horizontal,
        "cost": {
            "state_path_us_per_filter_cycle": per_cycle_state_us,
            "covariance_joseph_us_per_filter_cycle": per_cycle_cov_us,
            "covariance_joseph_us_per_scalar_update": per_update_cov_us,
            "note": "Python, medido em volta de execucoes completas; ordem de grandeza, nao o custo em Rust",
        },
        "timing_s": {"schedules": t_sched, "total": time.perf_counter() - t_total},
    }
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
