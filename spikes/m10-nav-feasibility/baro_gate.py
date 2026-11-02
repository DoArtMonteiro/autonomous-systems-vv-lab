#!/usr/bin/env python3
"""Porta de decisao M10.0 do barometro: orcamento de erro e margem de isolamento em funcao da altitude.

NAO e a implementacao do M10 e NAO e evidencia para nenhuma hipotese do M10. E um calculo analitico com
os parametros SUPOSTOS de docs/m10-resilient-navigation.md, secao 4.1. Biblioteca padrao apenas.
Determinista: nao usa aleatoriedade.

Termos do barometro (altitude de pressao, secao 4.1):
  ruido de leitura medio numa janela, desvio inicial de calibracao b0 (so prior, sem aprendizagem),
  deriva, escala kappa*h, erro estatico c_p*v^2/(2g), latencia (incerteza DA COMPENSACAO: dtau*v, nao o
  tau bruto), perturbacao do jato -A*u*exp(-h/h_g).

Convencao do RSS (a mesma da revisao independente, para comparabilidade): cada termo limitado entra no
RSS com a sua amplitude maxima, o que e conservador (uma uniforme em +-a tem desvio-padrao a/sqrt(3)).
O pior caso e a soma das amplitudes maximas (b0 e ruido a 3 desvios-padrao).

Criterios de isolamento (um barometro como terceira fonte so isola uma falha de magnitude m se):
  estatistico: m / RSS(h) >= 3
  pior caso:   m >= pior_caso(h)   (margem >= 1 contra a soma das amplitudes maximas)

h_commit (estimativa minha, ignora a latencia do acelerador e a massa): a correccao de altitude m ainda e
absorvivel pelo acelerador se m <= (1 - F_IGN/F_MAX)*h, ou seja h_commit(m) = m / 0,21. A janela util do
barometro para uma falha de m e a banda de isolamento acima de h_commit(m).

Perfis de descida (v em funcao de h):
  toy:    desaceleracao liquida constante de 13,22 m/s^2 a partir de 230 m/s a 2000 m (o do prototipo);
  m9like: integrador 1D local com os parametros do caso M9.1 (massa 30 t, 845 kN, Isp 282 s,
          densidade exponencial, arrasto Cd 0,8 e 10,5 m^2, ignicao a 0,75 da desaceleracao disponivel).
          Nao e o simulador Rust e nao foi comparado com os seus traços.

Uso: python spikes/m10-nav-feasibility/baro_gate.py > porta_barometro.json
"""

import json
import math
import platform

G = 9.80665
VT = 1.5
MAGNITUDES = [5.0, 10.0, 20.0, 30.0]
MARGIN = 3.0
F_IGN, F_MAX = 0.75, 0.95  # fracao da desaceleracao disponivel na ignicao e maximo aceitavel numa correccao
COMMIT_FRAC = 1.0 - F_IGN / F_MAX  # uma correccao de altitude ate COMMIT_FRAC*h ainda e absorvivel pelo acelerador
U_NEAR_GROUND = 0.5  # acelerador tipico junto do solo (o minimo e 0,4)
N_AVG = 25  # 1 s de amostras a 25 Hz
SIG_READ = 0.5
DRIFT = 0.05 * math.sqrt(10.0)  # deriva ao longo de 10 s

# conjuntos de parametros (todos SUPOSTOS; a pessimista alarga c_p para varios % de q porque o veiculo vai
# base primeiro em escoamento separado, onde o coeficiente de pressao nas portas estaticas varia muito)
PARAM_SETS = {
    "legacy_reviewed": {  # o conjunto pessimista do rascunho, com o tau bruto: so para reproduzir a revisao
        "b0_sigma_m": 2.0, "kappa": 0.005, "cp": 0.005, "dtau_s": 0.04, "jet_A_m": 10.0, "jet_hg_m": 30.0},
    "optimistic": {
        "b0_sigma_m": 2.0, "kappa": 0.002, "cp": 0.005, "dtau_s": 0.005, "jet_A_m": 3.0, "jet_hg_m": 15.0},
    "pessimistic": {
        "b0_sigma_m": 2.0, "kappa": 0.005, "cp": 0.03, "dtau_s": 0.02, "jet_A_m": 10.0, "jet_hg_m": 30.0},
    "pessimistic_cp_1pct": {  # sensibilidade
        "b0_sigma_m": 2.0, "kappa": 0.005, "cp": 0.01, "dtau_s": 0.02, "jet_A_m": 10.0, "jet_hg_m": 30.0},
    "pessimistic_cp_5pct": {  # sensibilidade
        "b0_sigma_m": 2.0, "kappa": 0.005, "cp": 0.05, "dtau_s": 0.02, "jet_A_m": 10.0, "jet_hg_m": 30.0},
    "pessimistic_learned_offset": {  # sensibilidade: o desvio b0 foi aprendido antes da falha (arranque a quente)
        "b0_sigma_m": 0.3, "kappa": 0.005, "cp": 0.03, "dtau_s": 0.02, "jet_A_m": 10.0, "jet_hg_m": 30.0},
}


def terms(h, v, p):
    """Amplitudes maximas (m) dos termos sistematicos e desvios-padrao dos termos aleatorios."""
    return {
        "noise": SIG_READ / math.sqrt(N_AVG),
        "b0": p["b0_sigma_m"],
        "drift": DRIFT,
        "scale": p["kappa"] * h,
        "static": p["cp"] * v * v / (2.0 * G),
        "latency": p["dtau_s"] * v,
        "jet": p["jet_A_m"] * U_NEAR_GROUND * math.exp(-h / p["jet_hg_m"]),
    }


def budget(h, v, p):
    t = terms(h, v, p)
    rss = math.sqrt(sum(x * x for x in t.values()))
    worst = 3.0 * (t["noise"] + t["b0"] + t["drift"]) + t["scale"] + t["static"] + t["latency"] + t["jet"]
    return rss, worst, t


def profile_toy():
    a = (230.0**2 - VT**2) / (2.0 * 2000.0)
    return lambda h: math.sqrt(VT**2 + 2.0 * a * h)


def profile_m9like():
    """Integra a descida de 3000 m a -200 m/s: coasting com arrasto, depois queima com desaceleracao
    constante necessaria. Devolve v(h) por interpolacao e a altitude de ignicao."""
    rho0, hs, cd, area = 1.225, 8500.0, 0.8, 10.5
    tmax, isp, m, dt = 845e3, 282.0, 30000.0, 0.01
    h, v = 3000.0, -200.0
    burning, h_ign = False, None
    pts = [(h, abs(v))]
    while h > 0.0 and len(pts) < 2_000_000:
        rho = rho0 * math.exp(-h / hs)
        drag = 0.5 * rho * v * v * cd * area / m  # acelera para cima (v < 0)
        a_avail = tmax / m - G + drag
        a_req = (v * v - VT**2) / (2.0 * max(h, 0.5))
        if not burning and a_req >= 0.75 * a_avail:
            burning, h_ign = True, h
        thrust = 0.0
        if burning:
            u = min(1.0, max(0.4, (a_req + G - drag) * m / tmax))
            thrust = u * tmax
            m -= thrust / (isp * G) * dt
        acc = -G + drag + thrust / m
        v += acc * dt
        h += v * dt
        pts.append((h, abs(v)))
    pts = [(x, y) for x, y in pts if x >= 0.0]
    pts.sort()

    def vf(hq):
        lo, hi = 0, len(pts) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if pts[mid][0] <= hq:
                lo = mid
            else:
                hi = mid
        (h0, v0), (h1, v1) = pts[lo], pts[hi]
        return v0 if h1 == h0 else v0 + (v1 - v0) * (hq - h0) / (h1 - h0)

    return vf, h_ign


def bands(vf, p):
    """Intervalos de altitude (grelha de 1 m de 5 a 3000 m) em que a margem de isolamento satisfaz cada criterio."""
    out = {}
    for m in MAGNITUDES:
        res = {}
        for name in ("statistical_rss_margin_3", "worst_case_margin_1"):
            ok_alt = []
            for hi in range(5, 3001):
                h = float(hi)
                rss, worst, _ = budget(h, vf(h), p)
                ok = (m / rss >= MARGIN) if name.startswith("statistical") else (m >= worst)
                if ok:
                    ok_alt.append(hi)
            intervals, start, prev = [], None, None
            for hi in ok_alt:
                if start is None:
                    start = prev = hi
                elif hi == prev + 1:
                    prev = hi
                else:
                    intervals.append([start, prev])
                    start = prev = hi
            if start is not None:
                intervals.append([start, prev])
            res[name] = intervals
            hc = m / COMMIT_FRAC
            res[name + "_above_h_commit"] = [[max(a, math.ceil(hc)), b] for a, b in intervals if b >= hc]
        res["h_commit_m"] = round(m / COMMIT_FRAC, 1)
        out[str(int(m))] = res
    return out


def main():
    vf_m9, h_ign = profile_m9like()
    profiles = {"toy": profile_toy(), "m9like": vf_m9}
    sample_h = [3000, 2000, 1000, 500, 300, 200, 100, 50, 38, 20, 10, 5]
    out = {
        "label": "porta analitica do barometro, M10.0 (NAO e evidencia do M10; parametros supostos)",
        "command": "python spikes/m10-nav-feasibility/baro_gate.py > porta_barometro.json",
        "machine": {"platform": platform.platform(), "python": platform.python_version()},
        "conventions": {
            "rss": "amplitudes maximas dos termos limitados como 1 sigma (conservador); ruido medio em 1 s",
            "worst_case": "soma das amplitudes maximas; b0, ruido e deriva a 3 sigma",
            "u_near_ground": U_NEAR_GROUND, "margin_required": MARGIN,
        },
        "param_sets": PARAM_SETS,
        "m9like_ignition_altitude_m": h_ign,
        "m9like_speed_at_m_per_s": {str(h): vf_m9(float(h)) for h in sample_h},
        "budget_by_altitude": {},
        "bands_m": {},
    }
    for prof_name, vf in profiles.items():
        out["budget_by_altitude"][prof_name] = {}
        for set_name, p in PARAM_SETS.items():
            rows = []
            for h in sample_h:
                rss, worst, t = budget(float(h), vf(float(h)), p)
                rows.append({"h_m": h, "v_mps": round(vf(float(h)), 1), "rss_m": round(rss, 2), "worst_case_m": round(worst, 2),
                             "terms_m": {k: round(x, 2) for k, x in t.items()}})
            out["budget_by_altitude"][prof_name][set_name] = rows
        out["bands_m"][prof_name] = {set_name: bands(vf, p) for set_name, p in PARAM_SETS.items()}
    json.dump(out, __import__("sys").stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
