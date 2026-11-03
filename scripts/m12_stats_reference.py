"""Independent reference values for the statistics of vv-exec (M12).

Python standard library only, and different algorithms from the Rust engine:

- Clopper-Pearson by bisection on exact binomial tail sums in log space (the engine inverts the
  regularised incomplete beta function).
- Wilson with the normal quantile of `statistics.NormalDist` (Wichura AS 241; the engine uses
  Acklam's approximation).
- McNemar exact p-values with integer arithmetic (`fractions.Fraction`); no rounding at all.
- Holm by the textbook step-down definition.
- Ishigami Sobol indices from their closed form.

`python scripts/m12_stats_reference.py` writes exec/tests/fixtures/stats-reference.json; the Rust
test exec/tests/stats_reference.rs compares the engine with it and tests/test_m12_stats_reference.py
checks that the file is exactly what this script produces.
"""

from __future__ import annotations

import json
import math
import sys
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "exec" / "tests" / "fixtures" / "stats-reference.json"
SCHEMA = "vv-exec-stats-reference.v1"

INTERVAL_CASES = [
    (0, 10), (1, 10), (5, 10), (9, 10), (10, 10),
    (7, 20), (0, 20), (50, 100), (99, 100), (100, 100),
    (3, 1000), (500, 1000), (997, 1000),
]
CONFIDENCES = [0.9, 0.95, 0.99]
CDF_CASES = [(0, 10, 0.3), (3, 10, 0.3), (9, 10, 0.3), (12, 40, 0.25), (250, 1000, 0.25), (5, 200, 0.01)]
MCNEMAR_CASES = [(0, 0), (0, 5), (1, 9), (4, 4), (3, 17), (10, 25), (40, 60), (0, 30), (120, 150)]
HOLM_CASES = [
    [0.01, 0.04, 0.03, 0.5],
    [0.6, 0.9],
    [0.001, 0.2, 0.0125, 0.04, 0.03],
    [0.05],
]


def log_pmf(i: int, n: int, p: float) -> float:
    log_choose = math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
    return log_choose + i * math.log(p) + (n - i) * math.log1p(-p)


def log_sum_exp(xs: list[float]) -> float:
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k), by summing the probability mass function."""
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    return min(1.0, math.exp(log_sum_exp([log_pmf(i, n, p) for i in range(k + 1)])))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k)."""
    if k <= 0:
        return 1.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return min(1.0, math.exp(log_sum_exp([log_pmf(i, n, p) for i in range(k, n + 1)])))


def bisect(f, target: float, increasing: bool) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid in (lo, hi):
            break
        above = f(mid) > target
        if above == increasing:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def clopper_pearson(k: int, n: int, confidence: float) -> tuple[float, float]:
    alpha = 1.0 - confidence
    lo = 0.0 if k == 0 else bisect(lambda p: binom_sf(k, n, p), alpha / 2.0, True)
    hi = 1.0 if k == n else bisect(lambda p: binom_cdf(k, n, p), alpha / 2.0, False)
    return lo, hi


def wilson(k: int, n: int, confidence: float) -> tuple[float, float]:
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = Fraction(sum(math.comb(n, i) for i in range(min(b, c) + 1)), 2**n)
    return float(min(Fraction(1), 2 * tail))


def holm(p: list[float]) -> list[float]:
    m = len(p)
    order = sorted(range(m), key=lambda i: (p[i], i))
    out = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out


def ishigami(a: float = 7.0, b: float = 0.1) -> dict:
    pi4, pi8 = math.pi**4, math.pi**8
    v = a * a / 8 + b * pi4 / 5 + b * b * pi8 / 18 + 0.5
    v1 = 0.5 * (1 + b * pi4 / 5) ** 2
    v2 = a * a / 8
    v13 = b * b * pi8 * 8 / 225
    return {
        "a": a,
        "b": b,
        "first_order": [v1 / v, v2 / v, 0.0],
        "total": [(v1 + v13) / v, v2 / v, v13 / v],
    }


def reference() -> dict:
    return {
        "schema": SCHEMA,
        "generator": "scripts/m12_stats_reference.py",
        "wilson": [
            {"k": k, "n": n, "confidence": c, "interval": list(wilson(k, n, c))}
            for k, n in INTERVAL_CASES
            for c in CONFIDENCES
        ],
        "clopper_pearson": [
            {"k": k, "n": n, "confidence": c, "interval": list(clopper_pearson(k, n, c))}
            for k, n in INTERVAL_CASES
            for c in CONFIDENCES
        ],
        "binomial_cdf": [{"k": k, "n": n, "p": p, "value": binom_cdf(k, n, p)} for k, n, p in CDF_CASES],
        "mcnemar": [{"b": b, "c": c, "p": mcnemar_exact(b, c)} for b, c in MCNEMAR_CASES],
        "holm": [{"p": p, "adjusted": holm(p)} for p in HOLM_CASES],
        "ishigami": ishigami(),
    }


def render() -> str:
    return json.dumps(reference(), indent=1) + "\n"


def main() -> int:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
