"""Estatística do M10: dimensão exata da P3 por enumeração e comparações emparelhadas por semente.

Subcomandos:

- `size`: dimensão exata do teste de score emparelhado de Tango e Nam usado na P3
  (docs/m10-resilient-navigation.md, secção 10.5), por enumeração completa do modelo
  multinomial (b, c, n - b - c) na fronteira de H0 `p_b = p_c + margem`, com n = 800 e a grelha
  `p_c` de 0,5% a 8% em passos de 0,5 pontos. Para cada `c`, a região de rejeição em `b` é um
  intervalo `b <= b_max(c)` porque o valor-p cresce com `b`; a monotonia é verificada ponto a
  ponto numa grelha de `c`. Critério pré-registado: se a dimensão exceder o alfa nominal em mais
  de 10% (relativo) em algum ponto, a P3 passa à construção de Clopper-Pearson.
- `compare`: comparações emparelhadas por semente entre dois braços a partir dos `records.json`
  de campanhas M10 (o mesmo caso por semente: dispersões, magnitude e janela). Por célula: pares,
  recuperações de cada braço, `b` (só o primeiro recupera), `c` (só o segundo recupera) e um
  intervalo da diferença com cobertura de pelo menos 95% (Clopper-Pearson com Bonferroni). Com sementes de
  desenvolvimento o resultado é exploratório: não há valores-p fora da família primária (10.6).

Só usa a biblioteca padrão; sem aleatoriedade. Código de análise, fora da simulação.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

P3_MARGIN = 0.03
P3_N = 800
P3_GRID = tuple(round(0.005 * k, 3) for k in range(1, 17))  # 0,5% a 8%
HOLM_ALPHAS = (0.0125, 0.0167, 0.025, 0.05)
SIZE_TOLERANCE = 0.10
PROTECTED = (range(3000, 3100), range(6000, 6100))


def _log_choose(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def _binom_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n or p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    return min(1.0, sum(math.exp(_log_choose(n, i) + i * lp + (n - i) * lq) for i in range(k + 1)))


def cp_upper(k: int, n: int, tail: float) -> float:
    """Limite superior de Clopper-Pearson com cauda `tail`."""
    if k >= n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _binom_cdf(k, n, mid) > tail:
            lo = mid
        else:
            hi = mid
    return hi


def cp_lower(k: int, n: int, tail: float) -> float:
    if k <= 0:
        return 0.0
    return 1.0 - cp_upper(n - k, n, tail)


def tango_p(b: int, c: int, n: int, margin: float = P3_MARGIN) -> float:
    """Valor-p unilateral do teste de score de Tango e Nam para H0: (p_b - p_c) >= margem.

    `b`: pares em que só o braço de referência (`guarded`) recupera; `c`: só B+. MLE restrito de
    `p_c` sob `p_b = p_c + margem`: raiz de `b/(q+d) + c/q - 2(n-b-c)/(1-2q-d) = 0`, por bisseção;
    aproximação normal com `erf`. A mesma aritmética de `spikes/m10-nav-feasibility/power_thresholds.py`.
    """
    d = margin
    lo, hi = 1e-12, (1.0 - d) / 2.0 - 1e-12
    for _ in range(100):
        q = 0.5 * (lo + hi)
        g = b / (q + d) + (c / q if c else 0.0) - 2.0 * (n - b - c) / (1.0 - 2.0 * q - d)
        if g > 0.0:
            lo = q
        else:
            hi = q
    var = n * (2.0 * q + d - d * d)
    z = (b - c - n * d) / math.sqrt(var)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar exato bilateral: teste binomial sobre os pares discordantes."""
    m = b + c
    if m == 0:
        return 1.0
    return min(1.0, 2.0 * _binom_cdf(min(b, c), m, 0.5))


def rejection_boundary(n: int, alpha: float, margin: float = P3_MARGIN) -> list[int]:
    """Para cada c, o maior b com valor-p < alfa (-1 se nenhum), por bisseção em b."""
    bounds = []
    for c in range(n + 1):
        top = n - c
        if tango_p(0, c, n, margin) >= alpha:
            bounds.append(-1)
            continue
        if tango_p(top, c, n, margin) < alpha:
            bounds.append(top)
            continue
        lo, hi = 0, top  # p(lo) < alfa <= p(hi)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if tango_p(mid, c, n, margin) < alpha:
                lo = mid
            else:
                hi = mid
        bounds.append(lo)
    return bounds


def check_monotone(n: int, alpha: float, bounds: list[int], margin: float = P3_MARGIN, step: int = 1) -> bool:
    """A região de rejeição é exatamente {b <= b_max(c)}: verificado em todos os b, de `step` em `step` em c."""
    for c in range(0, n + 1, step):
        for b in range(0, n - c + 1):
            if (tango_p(b, c, n, margin) < alpha) != (b <= bounds[c]):
                return False
    return True


def exact_size(n: int, p_c: float, bounds: list[int], margin: float = P3_MARGIN) -> float:
    """P(rejeitar H0) na fronteira p_b = p_c + margem: soma do multinomial na região de rejeição."""
    p_b = p_c + margin
    p_0 = 1.0 - p_b - p_c
    lb, lc, l0 = math.log(p_b), math.log(p_c), math.log(p_0)
    log_n = math.lgamma(n + 1)
    total = 0.0
    for c in range(n + 1):
        base = log_n - math.lgamma(c + 1) + c * lc
        for b in range(bounds[c] + 1):
            r = n - b - c
            lp = base - math.lgamma(b + 1) - math.lgamma(r + 1) + b * lb + r * l0
            if lp > -60.0:
                total += math.exp(lp)
    return total


def size_report(n: int = P3_N, grid: tuple[float, ...] = P3_GRID, alphas: tuple[float, ...] = HOLM_ALPHAS,
                monotone_step: int = 25) -> dict[str, Any]:
    rows = []
    worst = 0.0
    monotone = {}
    for alpha in alphas:
        bounds = rejection_boundary(n, alpha)
        monotone[str(alpha)] = check_monotone(n, alpha, bounds, step=monotone_step)
        for p_c in grid:
            size = exact_size(n, p_c, bounds)
            worst = max(worst, size / alpha)
            rows.append({"alpha": alpha, "p_c": p_c, "p_b": round(p_c + P3_MARGIN, 3), "size": size,
                         "size_over_alpha": size / alpha})
    return {
        "schema": "vv-m10-p3-size.v1",
        "test": "Tango-Nam paired score test, one-sided, H0: (p_b - p_c) >= margin",
        "n_pairs": n,
        "margin": P3_MARGIN,
        "grid_p_c": list(grid),
        "alphas": list(alphas),
        "monotone_rejection_region": monotone,
        "monotone_check_every_c": monotone_step,
        "rows": rows,
        "worst_size_over_alpha": worst,
        "criterion": f"size <= alpha * (1 + {SIZE_TOLERANCE}) at every grid point",
        "criterion_met": worst <= 1.0 + SIZE_TOLERANCE and all(monotone.values()),
    }


# ---------------------------------------------------------------------------
# Comparações emparelhadas
# ---------------------------------------------------------------------------


def load_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        file = path / "records.json" if path.is_dir() else path
        records.extend(json.loads(file.read_text(encoding="utf-8")))
    for r in records:
        if any(r["seed"] in block for block in PROTECTED):
            raise ValueError(f"record with protected seed {r['seed']}: refused outside an authorised evaluation")
    return records


def paired(records: list[dict[str, Any]], first: str, second: str, metric: str = "recovery") -> dict[str, Any]:
    """Pares por (célula, semente); `metric` é um campo booleano dos registos."""
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for r in records:
        key = (r["scenario"], r["arm"], r["seed"])
        if key in index:
            raise ValueError(f"duplicate record {key}")
        index[key] = r
    rows = []
    for cell in sorted({r["scenario"] for r in records}):
        seeds = sorted({s for (sc, a, s) in index if sc == cell and a == first}
                       & {s for (sc, a, s) in index if sc == cell and a == second})
        if not seeds:
            continue
        x = [bool(index[(cell, first, s)][metric]) for s in seeds]
        y = [bool(index[(cell, second, s)][metric]) for s in seeds]
        n = len(seeds)
        b = sum(1 for i in range(n) if x[i] and not y[i])
        c = sum(1 for i in range(n) if y[i] and not x[i])
        rows.append({
            "cell": cell, "pairs": n, "first": sum(x), "second": sum(y), "b_only_first": b, "c_only_second": c,
            "difference_pp": 100.0 * (c - b) / n,
            # Quatro limites unilaterais de Clopper-Pearson com cauda 0,0125: pela desigualdade de
            # Bonferroni, a cobertura conjunta é de pelo menos 95%, qualquer que seja a correlação.
            "difference_ci95_pp": [100.0 * (cp_lower(c, n, 0.0125) - cp_upper(b, n, 0.0125)),
                                   100.0 * (cp_upper(c, n, 0.0125) - cp_lower(b, n, 0.0125))],
        })
    return {"first": first, "second": second, "metric": metric, "rows": rows,
            "note": "paired by seed; development seeds are exploratory: no p-values outside the primary family"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M10 statistics: exact P3 size and paired comparisons")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("size", help="exact size of the P3 score test by enumeration")
    s.add_argument("--n", type=int, default=P3_N)
    s.add_argument("--monotone-step", type=int, default=25)
    c = sub.add_parser("compare", help="paired comparison of two arms from campaign records")
    c.add_argument("records", type=Path, nargs="+")
    c.add_argument("--first", required=True)
    c.add_argument("--second", required=True)
    c.add_argument("--metric", default="recovery")
    args = parser.parse_args(argv)
    if args.command == "size":
        if not 10 <= args.n <= 2000:
            parser.error("--n must be in [10, 2000]")
        result = size_report(args.n, monotone_step=max(1, args.monotone_step))
        result["command"] = "python scripts/m10_stats.py size" + ("" if args.n == P3_N else f" --n {args.n}")
    else:
        result = paired(load_records(args.records), args.first, args.second, args.metric)
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
