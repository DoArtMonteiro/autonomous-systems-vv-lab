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
ACC_BIAS_RW = 0.0  # passeio aleatorio do bias no filtro: 0, porque o bias verdadeiro e constante (modelo e verdade concordam)
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
CUSUM_K = 0.5  # CUSUM bilateral sobre inovacoes normalizadas: folga de referencia (em desvios-padrao)
CUSUM_H = 12.0  # limiar do CUSUM; ARL0 gaussiano calculado por Siegmund (constantes pre-calculadas)
PAR_T = 3.0  # limiar de paridade (desvios-padrao) para "consistente" / "inconsistente"
PAR_WINDOW_STEPS = 50  # 1 s depois da deteccao, epocas comuns de 5 Hz (k multiplo de 10)
PAR_SNAP_STEPS = 100  # o desvio estimado do barometro e lido 2 s antes da deteccao
FLOOR_FRAC = 0.5  # variante com piso: sigma_delta >= 0,5 sigma_0 (so para ordenar; nao e usada na deteccao)
AL_MIN, AL_FRAC = 1.0, 0.02  # AL_v(h) = max(1 m, 0,02 h) (proposta do documento)
TG_STEPS = 25  # T_g = 0,5 s
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
PBB = {}


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
    pbb = []
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
        pbb.append(p[3][3])
        if keep_p:
            p_list.append([row[:] for row in p])
    PRIORS[excluded] = (prior_z, prior_b)
    PBB[excluded] = pbb
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
    bbs = [0.0] * (N + 1)
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
        bbs[k] = bb
        if k in want_state_at:
            states[k] = (z, v, ba, bb)
    if keep_innov:
        return zs, nis, cnt, states, innov, bbs
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


def cusum_alarms(innov, k_ref=None, h=None):
    """CUSUM bilateral por fonte sobre inovacoes normalizadas. Devolve [(passo, codigo)]; a fonte que
    alarma volta a zero (reinicio padrao)."""
    k_ref = CUSUM_K if k_ref is None else k_ref
    h = CUSUM_H if h is None else h
    g = {}
    alarms = []
    for k, code, y in innov:
        gp, gn = g.get(code, (0.0, 0.0))
        gp = max(0.0, gp + y - k_ref)
        gn = max(0.0, gn - y - k_ref)
        if gp > h or gn > h:
            alarms.append((k, code))
            gp = gn = 0.0
        g[code] = (gp, gn)
    return alarms


def arl0_siegmund(k_ref, h):
    """ARL0 (amostras) do CUSUM unilateral, aproximacao de Siegmund para ruido gaussiano; bilateral = metade."""
    b = h + 1.166
    one = (math.exp(2.0 * k_ref * b) - 2.0 * k_ref * b - 1.0) / (2.0 * k_ref * k_ref)
    return one, one / 2.0


def irwin_hall4_tail_two_sided(x_sigma):
    """P(|X| > x_sigma * sigma) para X = sigma*sqrt(3)*(u1+u2+u3+u4-2) (Irwin-Hall n=4, sem recorte)."""
    s = 2.0 + x_sigma / math.sqrt(3.0)  # soma u1..u4 acima de s
    if s >= 4.0:
        return 0.0
    m = int(math.floor(4.0 - s))
    tail = sum((-1) ** j * math.comb(4, j) * (4.0 - s - j) ** 4 for j in range(m + 1)) / 24.0
    return 2.0 * tail


def longest_run(flags):
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


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
    """Primeiro passo >= kf com alarme, calculado sobre TODO o historico (os tampoes enchem-se antes do
    inicio da falha, por isso o atraso de janela nao tem o piso artificial de `window` amostras).
    single: inovacao isolada acima de K_FA. window: soma de `window` inovacoes normalizadas
    (posicao ou velocidade) acima de K_FA * sqrt(window). Devolve tambem se houve alarme antes de kf."""
    buf = {1: [], 2: []}
    first = {"single": None, "window": None}
    early = {"single": False, "window": False}
    for k, code, y in innov:
        b = buf[code]
        b.append(y)
        if len(b) > window:
            b.pop(0)
        hit_single = abs(y) > K_FA
        hit_window = len(b) == window and abs(sum(b)) / math.sqrt(window) > K_FA
        for key, hit in (("single", hit_single), ("window", hit_window)):
            if hit:
                if k < kf:
                    early[key] = True
                elif first[key] is None:
                    first[key] = k
    first["early"] = early
    return first


def horizontal_study(sched):
    out = {"nominal": {}, "cells": []}
    nom = {"single": 0, "window": 0, "cusum": 0}
    for seed in SEEDS_NOMINAL:
        d = gen_h(seed)
        _, _, _, _, innov, _ = run_filter(sched, d, keep_innov=True)
        f = horizontal_alarm(innov, 0)
        for key in ("single", "window"):
            nom[key] += 1 if (f[key] is not None or f["early"][key]) else 0
        nom["cusum"] += 1 if cusum_alarms(innov) else 0
    out["nominal"] = {"runs": len(SEEDS_NOMINAL), "false_alarm_runs": nom}
    onset_s = 8.0
    kf = int(round(onset_s / DT))
    cases = [("step", v) for v in (1.0, 3.0, 5.0, 10.0, 30.0)]
    cases += [("ramp", v) for v in (0.03, 0.05, 0.1, 0.3, 1.0, 3.0)]
    cases += [("coherent", v) for v in (0.1, 0.3, 1.0, 3.0)]
    t_end = N * DT
    for kind, val in cases:
        res = {"single": [], "window": [], "cusum": []}
        early_runs = {"single": 0, "window": 0, "cusum": 0}
        err_end = []
        for seed in SEEDS_FAULT:
            d = gen_h(seed, (kind, val), onset_s)
            zs, _, _, _, innov, _ = run_filter(sched, d, keep_innov=True)
            f = horizontal_alarm(innov, kf)
            for key in ("single", "window"):
                res[key].append(None if f[key] is None else (f[key] - kf) * DT)
                early_runs[key] += 1 if f["early"][key] else 0
            al = cusum_alarms(innov)
            if any(k < kf for k, _ in al):
                early_runs["cusum"] += 1
            post = [k for k, _ in al if k >= kf]
            res["cusum"].append(None if not post else (post[0] - kf) * DT)
            err_end.append(abs(zs[N] - (H_P0 + H_V * t_end)))
        row = {"fault": kind, "value": val, "runs": len(SEEDS_FAULT),
               "offset_at_end_if_undetected_m": val if kind == "step" else val * (t_end - onset_s),
               "median_estimate_error_at_end_m": statistics.median(err_end),
               "alarm_before_onset_runs": early_runs}
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

    def pl_at(k):
        """Nivel de protecao vertical por separacao de solucoes (independente dos dados)."""
        pl = K_FF * math.sqrt(p00s[None][k])
        for ex in SOURCES:
            pl = max(pl, K_FA * sig_delta[ex][k] + K_MD * math.sqrt(p00s[ex][k]))
        return pl

    def analyse(data, want_nees=False):
        """Corre os 4 filtros. Para o principal (E1) e para o sem-barometro (E0) guarda as inovacoes
        normalizadas (CUSUM) e, para o principal, a trajetoria do desvio do barometro estimado."""
        zs, nis, cnt, st = {}, {}, {}, {}
        extra = {}
        for ex in names:
            if ex in (None, "B"):
                zs[ex], nis[ex], cnt[ex], st[ex], inn, bbs = run_filter(
                    scheds[ex], data, NEES_STEPS if (want_nees and ex is None) else (), keep_innov=True)
                extra[ex] = (inn, bbs)
            else:
                zs[ex], nis[ex], cnt[ex], st[ex] = run_filter(scheds[ex], data)
        return zs, nis, cnt, st, extra

    def stats_for_run(data, zs, nis, cnt):
        """Estatisticas de separacao normalizadas e alarmes por passo."""
        ratio = {ex: [abs(zs[None][k] - zs[ex][k]) / max(sig_delta[ex][k], thr_floor) for k in range(N + 1)] for ex in SOURCES}
        return ratio

    # --- autoverificacao: filtro de covariancia completa vs ganhos pre-calculados -----------------
    d = gen_run(SEEDS_NOMINAL[0])
    zs_chk = run_filter(scheds[None], d)[0]
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
    pl_gt_al_samples = 0
    cusum_fa_runs = {"E1": 0, "E0": 0}
    cusum_fa_by_source = {0: 0, 1: 0, 2: 0, 3: 0}
    nominal_final_err = []
    for seed in SEEDS_NOMINAL:
        data = gen_run(seed)
        t1 = time.perf_counter()
        zs, nis, cnt, st, extra = analyse(data, want_nees=True)
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
        for key, ex in (("E1", None), ("E0", "B")):
            al = cusum_alarms(extra[ex][0])
            if al:
                cusum_fa_runs[key] += 1
            if ex is None:
                for _, c in al:
                    cusum_fa_by_source[c] += 1
        for k in range(N + 1):
            if pl_at(k) > max(AL_MIN, AL_FRAC * truth(k)[0]):
                pl_gt_al_samples += 1
    nees_mean = {str(round(k * DT, 2)): nees_sum[k] / len(SEEDS_NOMINAL) for k in NEES_STEPS}
    n_nom = len(SEEDS_NOMINAL)
    nees_lo = 4.0 - 1.96 * math.sqrt(2.0 * 4.0 / n_nom)
    nees_hi = 4.0 + 1.96 * math.sqrt(2.0 * 4.0 / n_nom)

    def fault_cells(onsets, mags, cold=False):
        nonlocal t_filter, n_filter_cycles
        cells = []
        pl_arr = [pl_at(k) for k in range(N + 1)]
        floor_arr = {ex: [max(sig_delta[ex][k], FLOOR_FRAC * math.sqrt(p00s[None][k])) for k in range(N + 1)] for ex in SOURCES}
        code_of = {"R": CODE["R"], "G": CODE["Gz"], "B": CODE["B"]}
        for onset_s in onsets:
          kf = int(round(onset_s / DT))
          for src in SOURCES:
            for mag in mags:
                delays, iso_instant_ok, iso_floor_ok, iso_nis_ok, n_det = [], 0, 0, 0, 0
                pre_fa = 0
                missed_samples = 0
                err_full, err_reconf, err_reconf_par = [], [], []
                n_iso_eval = 0
                c1_delays, c0_delays, c1_pre, c0_pre, c1_first_ok = [], [], 0, 0, 0
                par = {"correct": 0, "wrong": 0, "not_isolated": 0}
                par_margin = []
                miss_b_plus = miss_c = 0
                for seed in SEEDS_FAULT:
                    data = gen_run(seed, (src, mag), onset_s)
                    t1 = time.perf_counter()
                    zs, nis, cnt, st, extra = analyse(data)
                    t_filter += time.perf_counter() - t1
                    n_filter_cycles += 4 * (N + 1)
                    ratio = stats_for_run(data, zs, nis, cnt)
                    zt_end = truth(N)[0]
                    # --- CUSUM por fonte (E1 = principal com barometro; E0 = sem barometro) ---
                    al1 = cusum_alarms(extra[None][0])
                    c1_pre += 1 if any(k < kf for k, _ in al1) else 0
                    post1 = [(k, c) for k, c in al1 if k >= kf]
                    first1 = post1[0][0] if post1 else None
                    if post1:
                        c1_delays.append((first1 - kf) * DT)
                        c1_first_ok += 1 if post1[0][1] == code_of[src] else 0
                    if src != "B":
                        al0 = cusum_alarms(extra["B"][0])
                        c0_pre += 1 if any(k < kf for k, _ in al0) else 0
                        post0 = [k for k, _ in al0 if k >= kf]
                        if post0:
                            c0_delays.append((post0[0] - kf) * DT)
                    # --- paridade no dominio das medidas (E1), isolamento depois da deteccao por CUSUM ---
                    pick_par = None
                    if first1 is not None:
                        ks = max(0, first1 - PAR_SNAP_STEPS)
                        if cold:
                            # sem periodo saudavel anterior: o desvio do barometro so tem o prior (a estimativa do
                            # filtro ja esta contaminada pela falha presente desde 0 s)
                            sb2 = BARO_OFFSET_SIGMA**2 + BARO_RW**2 * (first1 + PAR_WINDOW_STEPS) * DT
                            bhat = 0.0
                        else:
                            sb2 = PBB[None][ks] + BARO_RW**2 * (first1 + PAR_WINDOW_STEPS - ks) * DT
                            bhat = extra[None][1][ks]
                        start = first1 + (-first1) % 10
                        eps = [k for k in range(start, min(N, first1 + PAR_WINDOW_STEPS) + 1, 10) if k in data["gz"] and k in data["baro"]]
                        if eps:
                            n_e = len(eps)
                            m1 = sum(data["radar"][k] - data["gz"][k] for k in eps) / n_e
                            m2 = sum(data["radar"][k] - (data["baro"][k] - bhat) for k in eps) / n_e
                            m3 = sum(data["gz"][k] - (data["baro"][k] - bhat) for k in eps) / n_e
                            s1 = math.sqrt((R_VAR["R"] + R_VAR["Gz"]) / n_e)
                            s2 = math.sqrt((R_VAR["R"] + R_VAR["B"]) / n_e + sb2)
                            s3 = math.sqrt((R_VAR["Gz"] + R_VAR["B"]) / n_e + sb2)
                            n1, n2, n3 = abs(m1) / s1, abs(m2) / s2, abs(m3) / s3
                            # hipotese R: n3 pequeno, n1 e n2 grandes; G: n2 pequeno, n1 e n3 grandes; B: n1 pequeno
                            hyp = {"R": (n3, (n1, n2)), "G": (n2, (n1, n3)), "B": (n1, (n2, n3))}
                            cand = [h for h, (opp, others) in hyp.items() if opp < PAR_T and min(others) >= PAR_T]
                            if len(cand) == 1:
                                par["correct" if cand[0] == src else "wrong"] += 1
                                pick_par = cand[0]
                            else:
                                par["not_isolated"] += 1
                            par_margin.append({"R": min(n1, n2), "G": min(n1, n3), "B": min(n2, n3)}[src])
                        else:
                            par["not_isolated"] += 1
                    else:
                        par["not_isolated"] += 1
                    # --- separacao de solucoes (so para o nivel de protecao e para comparacao) ---
                    first = None
                    for k in range(N + 1):
                        if any(ratio[ex][k] > K_FA for ex in SOURCES):
                            if k < kf:
                                pre_fa += 1
                                break
                            first = k
                            break
                    if first is None or first < kf:
                        first = next((k for k in range(kf, N + 1) if any(ratio[ex][k] > K_FA for ex in SOURCES)), None)
                    end_alarm = first if first is not None else N + 1
                    for k in range(kf, end_alarm):
                        if abs(zs[None][k] - truth(k)[0]) > pl_arr[k]:
                            missed_samples += 1
                    # --- falhas de alerta: erro > AL durante >= T_g enquanto declarado Confiavel ---
                    end_c = first1 if first1 is not None else N + 1
                    flags_b = [abs(zs[None][k] - truth(k)[0]) > max(AL_MIN, AL_FRAC * truth(k)[0]) for k in range(kf, end_c)]
                    flags_c = [f and pl_arr[kf + i] <= max(AL_MIN, AL_FRAC * truth(kf + i)[0]) for i, f in enumerate(flags_b)]
                    miss_b_plus += 1 if longest_run(flags_b) >= TG_STEPS else 0
                    miss_c += 1 if longest_run(flags_c) >= TG_STEPS else 0
                    err_full.append(abs(zs[None][N] - zt_end))
                    err_reconf_par.append(abs(zs[pick_par][N] - zt_end) if pick_par else abs(zs[None][N] - zt_end))
                    if first is None:
                        err_reconf.append(abs(zs[None][N] - zt_end))
                        continue
                    n_det += 1
                    delays.append((first - kf) * DT)
                    pick = max(SOURCES, key=lambda ex: ratio[ex][first])
                    iso_instant_ok += 1 if pick == src else 0
                    pick_f = max(SOURCES, key=lambda ex: abs(zs[None][first] - zs[ex][first]) / floor_arr[ex][first])
                    iso_floor_ok += 1 if pick_f == src else 0
                    k_end = min(N, first + kiso)
                    score = {}
                    for ex in SOURCES:
                        tot = sum(nis[ex][k] for k in range(first, k_end + 1))
                        c = sum(cnt[ex][k] for k in range(first, k_end + 1))
                        score[ex] = tot / max(c, 1)
                    pick2 = min(SOURCES, key=lambda ex: score[ex])
                    iso_nis_ok += 1 if pick2 == src else 0
                    n_iso_eval += 1
                    err_reconf.append(abs(zs[pick2][N] - zt_end))

                def dstat(xs):
                    return {"median": percentile(xs, 0.5), "p90": percentile(xs, 0.9), "max": max(xs) if xs else None}

                cell = {
                    "onset_s": onset_s, "source": src, "magnitude_m": mag, "runs": len(SEEDS_FAULT),
                    "cusum_E1": {"detected": len(c1_delays), "delay_s": dstat(c1_delays),
                                 "alarm_before_onset_runs": c1_pre, "first_alarm_on_faulty_source": c1_first_ok},
                    "parity_isolation_E1": dict(par, median_margin_sigma=statistics.median(par_margin) if par_margin else None),
                    "separation_detected": n_det,
                    "separation_delay_s": dstat(delays),
                    "isolation_correct_max_separation": iso_instant_ok,
                    "isolation_correct_max_separation_floored": iso_floor_ok,
                    "isolation_correct_min_nis": iso_nis_ok,
                    "isolation_evaluated": n_iso_eval,
                    "alarm_before_onset_runs_separation": pre_fa,
                    "missed_alert_samples_before_separation_alarm": missed_samples,
                    "missed_alert_runs_Tg_0.5s": {"B_plus_no_PL": miss_b_plus, "C_with_PL": miss_c},
                    "final_abs_error_m": {
                        "full_filter_median": statistics.median(err_full),
                        "full_filter_max": max(err_full),
                        "reconfigured_by_nis_median": statistics.median(err_reconf),
                        "reconfigured_by_nis_max": max(err_reconf),
                        "reconfigured_by_parity_median": statistics.median(err_reconf_par),
                        "reconfigured_by_parity_max": max(err_reconf_par),
                    },
                }
                if src != "B":
                    cell["cusum_E0"] = {"detected": len(c0_delays), "delay_s": dstat(c0_delays), "alarm_before_onset_runs": c0_pre}
                cells.append(cell)
        return cells

    # --- falhas ------------------------------------------------------------------------------------
    cells = fault_cells(ONSETS_S, MAGNITUDES)
    # --- arranque a frio: prior de altitude nao informativo, falha presente desde o instante 0 ----
    saved = (CFG["p0"], CFG["e0"])
    CFG["p0"], CFG["e0"] = COLD_P0, COLD_E0
    scheds_w, p00s_w, sig_w = scheds, p00s, sig_delta
    priors_w, pbb_w = dict(PRIORS), dict(PBB)
    scheds, p00s, n_upd_c = {}, {}, {}
    for ex in names:
        s_, p00_, _, nu_ = build_schedule(ex)
        scheds[ex], p00s[ex] = s_, p00_
    sig_delta = {ex: [math.sqrt(max(p00s[ex][k] - p00s[None][k], 1e-12)) for k in range(N + 1)] for ex in SOURCES}
    cold_cells = fault_cells([0.0], COLD_MAGNITUDES, cold=True)
    CFG["p0"], CFG["e0"] = saved
    scheds, p00s, sig_delta = scheds_w, p00s_w, sig_w
    PRIORS.update(priors_w)
    PBB.update(pbb_w)

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

    # desfasamento de meio ciclo da forca especifica numa rampa do acelerador (analitico)
    thrust_max_n, mass_kg, ramp_rate = 845e3, 26.3e3, 1.0  # valores do documento (secao 8.1 e 3.1)
    da_dt = ramp_rate * thrust_max_n / mass_kg  # m/s^3 por unidade de acelerador/s
    lag_s = 0.5 * DT
    ramp_s = 0.4  # rampa de 0,4 para 0,8 (taxa maxima 1,0/s)
    force_lag = {"dfdt_mps3": da_dt, "half_cycle_lag_s": lag_s, "accel_error_mps2": da_dt * lag_s,
                 "velocity_error_after_ramp_mps": da_dt * lag_s * ramp_s, "ramp_s": ramp_s}
    theory_sample = {str(kk): phi_tail2(kk) for kk in FA_SWEEP}
    emp_sample = {str(kk): sample_exceed[kk] / samples for kk in FA_SWEEP}
    runs_alarm = {str(kk): nominal_sweep_runs[kk] for kk in FA_SWEEP}
    out = {
        "label": "prototipo de viabilidade, canal vertical, sementes de desenvolvimento (NAO e evidencia do M10)",
        "command": "python spikes/m10-nav-feasibility/feasibility.py > resumo.json",
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
        "detector": {"K_fa": K_FA, "K_md": K_MD, "K_ff": K_FF, "isolation_window_s": ISO_WINDOW_S,
                     "cusum_k_ref": CUSUM_K, "cusum_h": CUSUM_H,
                     "cusum_arl0_samples_one_sided_two_sided_siegmund": arl0_siegmund(CUSUM_K, CUSUM_H),
                     "parity_threshold_sigma": PAR_T, "floor_fraction_of_sigma0": FLOOR_FRAC,
                     "AL_v": "max(%.1f m, %.2f h)" % (AL_MIN, AL_FRAC), "T_g_s": TG_STEPS * DT},
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
            "samples_PL_above_AL": pl_gt_al_samples,
            "cusum_false_alarm_runs": cusum_fa_runs,
            "cusum_false_alarm_runs_upper95_clopper_pearson": {k_: clopper_upper(v_, n_nom) for k_, v_ in cusum_fa_runs.items()},
            "cusum_false_alarms_by_source_code_E1": {str(k_): v_ for k_, v_ in cusum_fa_by_source.items()},
            "final_abs_error_m_median_max": [statistics.median(nominal_final_err), max(nominal_final_err)],
        },
        "analytic_mdb_approx": mdb_rows,
        "irwin_hall_tails": {
            "note": "cauda bilateral P(|X|>k sigma): Irwin-Hall n=4 exata (o recorte a 2 sqrt(3) sigma nao atua) contra gaussiana",
            "k": {str(kk): {"irwin_hall_raw": irwin_hall4_tail_two_sided(kk), "gaussian": phi_tail2(kk)} for kk in (2.0, 3.0, 3.4)},
        },
        "force_lag_during_throttle_ramp": force_lag,
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
