"""Statistics for the M14 benchmark and fragility study. Standard library only.

- Mann-Whitney U, two-sided, normal approximation with tie correction and no continuity
  correction; an exact permutation version for small samples, used by the tests as a reference.
- Holm step-down adjustment (same definition as `vv_exec::stats::holm`).
- Percentile bootstrap of a difference in medians, with an explicit Mersenne Twister seed.
- Clopper-Pearson interval by bisection on the exact binomial distribution.
"""

from __future__ import annotations

import itertools
import math
import random
from statistics import median


def ranks(values: list[float]) -> list[float]:
    """Mid-ranks, 1-based."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mid = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = mid
        i = j + 1
    return out


def mann_whitney_u(x: list[float], y: list[float]) -> float:
    """U of the first sample: pairs (a, b) with a > b, plus half the ties."""
    r = ranks(list(x) + list(y))
    n1 = len(x)
    return sum(r[:n1]) - n1 * (n1 + 1) / 2


def mann_whitney(x: list[float], y: list[float]) -> dict:
    """Two-sided test of equal distributions. Normal approximation with tie correction."""
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        raise ValueError("both samples must be non-empty")
    u = mann_whitney_u(x, y)
    n = n1 + n2
    counts: dict[float, int] = {}
    for v in list(x) + list(y):
        counts[v] = counts.get(v, 0) + 1
    tie = sum(t**3 - t for t in counts.values())
    var = n1 * n2 / 12 * ((n + 1) - tie / (n * (n - 1)))
    mean = n1 * n2 / 2
    if var <= 0:
        return {"u": u, "z": 0.0, "p": 1.0}
    z = (u - mean) / math.sqrt(var)
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"u": u, "z": z, "p": min(1.0, p)}


def mann_whitney_exact(x: list[float], y: list[float]) -> float:
    """Two-sided exact permutation p-value: all splits of the pooled sample (small samples only)."""
    pooled = list(x) + list(y)
    n1 = len(x)
    if math.comb(len(pooled), n1) > 500_000:
        raise ValueError("too many permutations for the exact test")
    mean = n1 * len(y) / 2
    observed = abs(mann_whitney_u(x, y) - mean)
    r = ranks(pooled)
    base = n1 * (n1 + 1) / 2
    hits = total = 0
    for idx in itertools.combinations(range(len(pooled)), n1):
        u = sum(r[i] for i in idx) - base
        total += 1
        if abs(u - mean) >= observed - 1e-12:
            hits += 1
    return hits / total


def holm(p: list[float]) -> list[float]:
    """Holm-adjusted p-values, monotone and capped at 1, in the input order."""
    m = len(p)
    order = sorted(range(m), key=lambda i: p[i])
    out = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out


def bootstrap_median_difference(
    x: list[float], y: list[float], resamples: int, seed: int, confidence: float = 0.95
) -> dict:
    """median(x) - median(y) with a percentile bootstrap interval, resampling each group."""
    rng = random.Random(seed)
    diffs = []
    for _ in range(resamples):
        bx = [x[rng.randrange(len(x))] for _ in x]
        by = [y[rng.randrange(len(y))] for _ in y]
        diffs.append(median(bx) - median(by))
    diffs.sort()
    a = (1 - confidence) / 2
    lo = diffs[int(math.floor(a * resamples))]
    hi = diffs[min(resamples - 1, int(math.ceil((1 - a) * resamples)) - 1)]
    return {"difference": median(x) - median(y), "low": lo, "high": hi}


def binomial_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
        for i in range(k + 1)
    ]
    top = max(terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in terms))


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided exact interval for a binomial proportion."""
    if not 0 <= k <= n or n == 0:
        raise ValueError("need 0 <= k <= n and n > 0")
    a = (1 - confidence) / 2

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    low = 0.0 if k == 0 else solve(lambda p: 1 - binomial_cdf(k - 1, n, p) >= a)
    high = 1.0 if k == n else solve(lambda p: binomial_cdf(k, n, p) <= a)
    return low, high


def one_sided_lower(k: int, n: int, confidence: float = 0.95) -> float:
    """One-sided lower Clopper-Pearson bound: the two-sided bound at 2 * confidence - 1."""
    return clopper_pearson(k, n, 2 * confidence - 1)[0] if k > 0 else 0.0


def one_sided_upper(k: int, n: int, confidence: float = 0.95) -> float:
    return clopper_pearson(k, n, 2 * confidence - 1)[1] if k < n else 1.0
