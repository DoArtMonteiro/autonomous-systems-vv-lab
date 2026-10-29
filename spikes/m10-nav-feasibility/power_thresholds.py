#!/usr/bin/env python3
"""Limiares efetivos de Clopper-Pearson e potencia dos testes do pre-registo do M10 (secao 10.5).

NAO e evidencia do M10: e aritmetica exata sobre binomiais, para fixar o texto do pre-registo antes de
qualquer execucao. Biblioteca padrao apenas, sem aleatoriedade.

Calcula:
  1. contagens efetivas em n execucoes: o menor k com limite inferior bilateral de 95% >= theta
     ("suportado acima de theta") e o maior k com limite superior bilateral de 95% <= theta;
  2. o maior numero de falhas de alerta em N execucoes agrupadas com limite superior unilateral de 95% <= 5%;
  3. potencia do McNemar exato (pares discordantes) para H-C, por celula (n = 100) e agrupado (n = 600),
     a alfa 0,05 e a 0,0125 (pior caso de Holm sobre 4 testes);
  4. potencia de duas proporcoes independentes (Fisher exato, nao emparelhado) a alfa 0,0056, para
     reproduzir a objecao da revisao (90 contra 80 por cento com n = 100 por celula);
  5. exemplos de nao inferioridade agrupada contra `guarded` (limites exatos conservadores).

Uso: python spikes/m10-nav-feasibility/power_thresholds.py > potencia.json
"""

import json
import math


def logpmf(k, n, p):
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def cdf(k, n, p):
    """P(X <= k), X ~ Bin(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(math.exp(logpmf(i, n, p)) for i in range(k + 1)))


def cp_upper(k, n, alpha):
    """Limite superior de Clopper-Pearson com cauda alpha (unilateral)."""
    if k >= n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def cp_lower(k, n, alpha):
    if k <= 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if 1.0 - cdf(k - 1, n, mid) < alpha:
            lo = mid
        else:
            hi = mid
    return lo


def mcnemar_p(b, c):
    """p bilateral exato sobre os pares discordantes (teste binomial com p = 0,5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * cdf(k, n, 0.5))


def mcnemar_power(n_pairs, p_b, p_c, alpha):
    """Potencia: b ~ discordantes (so o 1.o ganha), c ~ (so o 2.o ganha), multinomial de n_pairs pares."""
    pd = p_b + p_c
    power = 0.0
    for nd in range(n_pairs + 1):
        w = math.exp(logpmf(nd, n_pairs, pd))
        if w < 1e-14:
            continue
        rej = 0.0
        for b in range(nd + 1):
            if mcnemar_p(b, nd - b) <= alpha and b > nd - b:
                rej += math.exp(logpmf(b, nd, p_b / pd))
        power += w * rej
    return power


def fisher_p(a, n1, c, n2):
    """p bilateral de Fisher: tabela [a, n1-a; c, n2-c] (soma das probabilidades <= a observada)."""
    tot = a + c
    n = n1 + n2

    def hyp(x):
        return math.exp(math.lgamma(n1 + 1) - math.lgamma(x + 1) - math.lgamma(n1 - x + 1)
                        + math.lgamma(n2 + 1) - math.lgamma(tot - x + 1) - math.lgamma(n2 - tot + x + 1)
                        - (math.lgamma(n + 1) - math.lgamma(tot + 1) - math.lgamma(n - tot + 1)))

    lo, hi = max(0, tot - n2), min(n1, tot)
    pobs = hyp(a)
    return sum(hyp(x) for x in range(lo, hi + 1) if hyp(x) <= pobs * (1 + 1e-9))


def fisher_power(n, p1, p2, alpha):
    pm1 = [math.exp(logpmf(a, n, p1)) for a in range(n + 1)]
    pm2 = [math.exp(logpmf(c, n, p2)) for c in range(n + 1)]
    power = 0.0
    for a in range(n + 1):
        if pm1[a] < 1e-12:
            continue
        for c in range(n + 1):
            if pm2[c] < 1e-12:
                continue
            if fisher_p(a, n, c, n) <= alpha:
                power += pm1[a] * pm2[c]
    return power


def main():
    out = {"label": "limiares efetivos e potencia (aritmetica exata; NAO e evidencia do M10)",
           "command": "python spikes/m10-nav-feasibility/power_thresholds.py > potencia.json"}
    # 1. contagens efetivas, n = 100, intervalo bilateral de 95% (cauda 0,025)
    n = 100
    eff = {}
    for theta in (0.80, 0.90, 0.95):
        k = next(k for k in range(n + 1) if cp_lower(k, n, 0.025) >= theta)
        eff[f"lower_bound_ge_{theta}"] = {"min_k_of_100": k, "lower_bound": cp_lower(k, n, 0.025),
                                          "previous_k_lower_bound": cp_lower(k - 1, n, 0.025)}
    for theta in (0.02, 0.05, 0.10, 0.20):
        k = max(k for k in range(n + 1) if cp_upper(k, n, 0.025) <= theta) if cp_upper(0, n, 0.025) <= theta else None
        eff[f"upper_bound_le_{theta}"] = {"max_k_of_100": k, "upper_bound": cp_upper(k, n, 0.025) if k is not None else None}
    out["effective_counts_n100_two_sided_95"] = eff
    # 2. P1: N execucoes agrupadas, limite superior unilateral de 95% (cauda 0,05) <= 5%
    p1 = {}
    for big_n in (700, 1000):
        k = max(k for k in range(big_n + 1) if cp_upper(k, big_n, 0.05) <= 0.05)
        p1[str(big_n)] = {"max_missed_alerts": k, "upper_bound": cp_upper(k, big_n, 0.05),
                          "upper_bound_if_zero": cp_upper(0, big_n, 0.05)}
    out["P1_pooled_one_sided_95_upper_le_5pct"] = p1
    # 3. potencia do McNemar
    scen = [("B+ falha 8%, C falha 2% (diferenca 6 pp)", 0.07, 0.01),
            ("B+ falha 6%, C falha 1% (diferenca 5 pp)", 0.055, 0.005),
            ("B+ falha 4%, C falha 1% (diferenca 3 pp)", 0.035, 0.005),
            ("B+ falha 20%, C falha 10% (diferenca 10 pp)", 0.105, 0.005)]
    mc = []
    for label, pb, pc in scen:
        row = {"scenario": label, "p_only_Bplus_misses": pb, "p_only_C_misses": pc}
        for n_pairs in (100, 600):
            for alpha in (0.05, 0.0125):
                row[f"power_n{n_pairs}_alpha{alpha}"] = mcnemar_power(n_pairs, pb, pc, alpha)
        mc.append(row)
    out["H_C_mcnemar_power"] = mc
    # 4. reproduz a objecao: 90 contra 80 por cento, n = 100 por celula, alfa 0,0056, nao emparelhado
    out["unpaired_fisher_power_n100"] = {
        "90_vs_80_alpha_0.0056": fisher_power(100, 0.90, 0.80, 0.0056),
        "90_vs_70_alpha_0.0056": fisher_power(100, 0.90, 0.70, 0.0056),
        "note": "a objecao da revisao dava 0,15 a 0,52 conforme o desenho; aqui o desenho nao emparelhado"}
    # 5. nao inferioridade agrupada (N = 900 pares, 9 celulas): limite superior conservador de b/N - c/N,
    #    b = so `guarded` recupera, c = so C recupera; cada limite com cauda 0,0125 (Bonferroni sobre 0,025)
    ni = []
    big_n = 900
    for b, c in ((15, 15), (40, 40), (30, 20), (45, 25), (60, 30)):
        d_hat = (b - c) / big_n
        d_up = cp_upper(b, big_n, 0.0125) - cp_lower(c, big_n, 0.0125)
        ni.append({"b_only_guarded": b, "c_only_C": c, "diff_pp": 100 * d_hat, "upper_limit_pp": 100 * d_up,
                   "non_inferior_margin_3pp": d_up <= 0.03})
    out["P3_noninferiority_examples_N900"] = ni
    json.dump(out, __import__("sys").stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
