#!/usr/bin/env python3
"""M19: reproducible calculations for the corrected G3 onset protocol candidate.

Nothing here runs a simulator, `cargo`, `vv-exec` or `vv-rocket`, and no simulator seed is used.
The inputs are committed blobs (read with `git cat-file blob <commit>:<path>`), recorded evidence
files at the same commit, and arithmetic. All binomial and multinomial quantities are exact
(integer arithmetic over a common denominator). The only random number generator is the
SplitMix64 cross-check of the median-interval power, with algorithm and seed declared below; its
seed is a sampling seed for this script and is unrelated to any simulator seed.

    python scripts/m19_g3_power.py --output docs/evidence/m19/g3-candidate/calculations.json
    python scripts/m19_g3_power.py --check docs/evidence/m19/g3-candidate/calculations.json

The output is deterministic: sorted keys, LF line endings, no timestamps, no absolute paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from fractions import Fraction as F
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The commit every hash and every recorded number is read from.
BASE = "4777160"
OLD_SIM = "3962482"  # simulator commit that the M13 development evidence refers to
M15_REF = "bec7b3f"  # reference commit of the review package

FAMILY_ALPHA = F(1, 100)
PRIMARY, SECONDARY, MITIGATION = 3, 7, 2

ONSETS_M15 = [0.01, 0.1, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0]
ONSETS = [0.1, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0]
LOW_BAND = [5.0, 7.0, 9.0, 10.5]
HIGH_BAND = [13.5, 17.0, 22.0, 30.0]
MITIGATION_MAGNITUDES = [5.0, 8.0, 10.5, 15.0]
DT_S = 0.01
CONTROL_PERIOD_STEPS = 2
GNSS_PERIOD_CYCLES = 5

# Seeds the protocol must not touch (transcribed from the M15 candidate and `exec/src/seeds.rs`).
SPENT_OR_PROTECTED = {
    "41000-41999 development": (41000, 41999),
    "42000-43999 M13 investigation": (42000, 43999),
    "45000-46999 development": (45000, 46999),
    "47000-47019 P1 and P2 test": (47000, 47019),
    "32000-32099 M14 fragility": (32000, 32099),
    "33500-33529 M14 review": (33500, 33529),
    "30001 M14 equivalence": (30001, 30001),
    "30017 M14 equivalence": (30017, 30017),
    "3000-3099 M10": (3000, 3099),
    "6000-6099 M10": (6000, 6099),
    "50000-59999 M14 split": (50000, 59999),
}
SEED_FIRST, SEED_LAST, RESERVE_FIRST, SEED_RANGE_LAST = 44000, 44919, 44920, 44999

# SplitMix64 cross-check parameters (sampling seed of this script, not a simulator seed).
MC_SEED = 20261123
MC_REPS = 5000


# ---------------------------------------------------------------------------------------------
# Git access
# ---------------------------------------------------------------------------------------------


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def full_sha(rev: str) -> str:
    return git("rev-parse", rev).decode().strip()


def blob(commit: str, path: str) -> bytes:
    return git("cat-file", "blob", f"{commit}:{path}")


def blob_sha256(commit: str, path: str) -> str:
    return hashlib.sha256(blob(commit, path)).hexdigest()


SIM_FILES = [
    "Cargo.lock", "Cargo.toml", "src/dynamics.rs", "src/landing_actuator.rs",
    "src/landing_controller.rs", "src/landing_model.rs", "src/landing_run.rs",
    "src/landing_sensors.rs", "src/landing_sim.rs", "src/landing_truth.rs",
    "src/landing_types.rs", "src/landing_verify.rs", "src/lib.rs", "src/main.rs", "src/math.rs",
    "src/model.rs", "src/prng.rs", "src/run.rs", "src/sim.rs", "src/verify.rs",
]  # same list and order as `source_sha256()` in crates/vv-rocket/src/lib.rs


def source_sha256(commit: str) -> str:
    """`source_sha256()` of crates/vv-rocket, recomputed over blobs without compiling."""
    digest = hashlib.sha256()
    for name in SIM_FILES:
        text = blob(commit, f"crates/vv-rocket/{name}").decode()
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(text.replace("\r\n", "\n").encode())
        digest.update(b"\0")
    return digest.hexdigest()


PINNED = [
    "docs/m15-g3-onset-protocol.md",
    "docs/m14-g3-onset-protocol-draft.md",
    "docs/review/g3-onset/README.md",
    "docs/review/g3-onset/independent-checks.md",
    "docs/review/g3-onset/limitations.md",
    "docs/review/g3-onset/reviewer-questions.md",
    "docs/review/g3-onset/source-commitments.md",
    "docs/review/g3-onset/study-summary.md",
    "exec/claims/m13/g3-onset.json",
    "exec/cases/m13/g3-registered.json",
    "exec/cases/m13/family-altimeter-bias-low.json",
    "exec/cases/m13/family-altimeter-bias.json",
    "exec/cases/m13/family-altimeter-dropout.json",
    "exec/cases/m13/family-gnss-bias-low.json",
    "exec/cases/m13/family-gnss-dropout.json",
    "exec/cases/m13/family-imu-accel-bias.json",
    "exec/cases/m13/family-small-net-gnss-bias.json",
    "exec/cases/m13/family-thrust-loss.json",
    "exec/cases/m13/sources.json",
    "docs/evidence/m14/masking/prediction.json",
    "docs/evidence/m14/masking/test.json",
    "docs/evidence/m13/g3-onset/investigation.json",
    "docs/evidence/m14/fragility/fragility.json",
    "scripts/m14_masking_model.py",
    "scripts/m14_stats.py",
    "scripts/m12_stats_reference.py",
    "exec/src/seeds.rs",
    "exec/src/investigate.rs",
    "exec/src/search.rs",
    "crates/vv-rocket/src/landing_sensors.rs",
    "crates/vv-rocket/src/landing_sim.rs",
    "crates/vv-rocket/src/landing_controller.rs",
    "crates/vv-rocket/src/landing_model.rs",
    "crates/vv-rocket/src/landing_types.rs",
]


def provenance() -> dict:
    base = full_sha(BASE)
    old = full_sha(OLD_SIM)
    ref = full_sha(M15_REF)
    files = {p: blob_sha256(base, p) for p in PINNED}
    sim_now = {f: blob_sha256(base, f"crates/vv-rocket/{f}") for f in SIM_FILES}
    sim_old = {f: blob_sha256(old, f"crates/vv-rocket/{f}") for f in SIM_FILES}
    sim_ref = {f: blob_sha256(ref, f"crates/vv-rocket/{f}") for f in SIM_FILES}
    return {
        "base_commit": base,
        "m15_reference_commit": ref,
        "m13_simulator_commit": old,
        "pinned_blob_sha256": files,
        "m15_protocol_identical_to_review_reference": (
            blob_sha256(base, "docs/m15-g3-onset-protocol.md")
            == blob_sha256(ref, "docs/m15-g3-onset-protocol.md")
        ),
        "simulator": {
            "source_sha256_base": source_sha256(base),
            "source_sha256_m15_reference": source_sha256(ref),
            "source_sha256_m13_commit": source_sha256(old),
            "source_sha256_m13_recorded": json.loads(
                blob(base, "docs/evidence/m13/g3-onset/investigation.json")
            )["source_sha256"],
            "files_differing_m13_to_base": sorted(f for f in SIM_FILES if sim_now[f] != sim_old[f]),
            "files_differing_reference_to_base": sorted(
                f for f in SIM_FILES if sim_now[f] != sim_ref[f]
            ),
            "per_file_sha256_base": sim_now,
        },
    }


# ---------------------------------------------------------------------------------------------
# Exact binomial machinery
# ---------------------------------------------------------------------------------------------


def frac(x) -> F:
    return x if isinstance(x, F) else F(str(x))


def sf(k: int, n: int, p) -> F:
    """P(X >= k), X ~ Bin(n, p), exact."""
    p = frac(p)
    num, den = p.numerator, p.denominator
    if k <= 0:
        return F(1)
    if k > n:
        return F(0)
    total = sum(comb(n, i) * num**i * (den - num) ** (n - i) for i in range(k, n + 1))
    return F(total, den**n)


def threshold(n: int, alpha, p0=F(9, 10)):
    """Smallest k such that P(X >= k | n, p0) <= alpha, or None when even k = n is not enough."""
    alpha, p0 = frac(alpha), frac(p0)
    num, den = p0.numerator, p0.denominator
    bound = alpha.numerator * den**n
    tail = 0
    for i in range(n, -1, -1):
        tail += comb(n, i) * num**i * (den - num) ** (n - i)
        if tail * alpha.denominator > bound:
            return i + 1 if i + 1 <= n else None
    return 0


def min_n_all_success(alpha, p0=F(9, 10)) -> int:
    """Smallest n for which n successes out of n reject H0: pi <= p0 (p0**n <= alpha)."""
    alpha, p0 = frac(alpha), frac(p0)
    n = 1
    while p0**n > alpha:
        n += 1
    return n


def min_n_interval(n: int, p0=F(9, 10)) -> tuple[float, float]:
    """The alpha interval [p0**n, p0**(n-1)) for which n is the minimum all-success size."""
    p0 = frac(p0)
    return float(p0**n), float(p0 ** (n - 1))


def power(n: int, pi, alpha, p0=F(9, 10)) -> F:
    k = threshold(n, alpha, p0)
    return F(0) if k is None else sf(k, n, pi)


def r6(x) -> float:
    return round(float(x), 6)


def mde(n: int, alpha, target=F(4, 5), p0=F(9, 10)):
    """Smallest pi on a 0.001 grid whose power reaches `target` (None if never)."""
    start = int(frac(p0) * 1000) + 1
    for i in range(start, 1001):
        if power(n, F(i, 1000), alpha, p0) >= target:
            return i / 1000
    return None


def cp_upper(x: int, n: int, conf: float = 0.99) -> float:
    """One-sided Clopper-Pearson upper bound: the p with P(X <= x | n, p) = 1 - conf."""
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        cdf = sum(comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(x + 1))
        lo, hi = (mid, hi) if cdf > 1 - conf else (lo, mid)
    return hi


def cp_lower(x: int, n: int, conf: float = 0.99) -> float:
    """One-sided Clopper-Pearson lower bound: the p with P(X >= x | n, p) = 1 - conf."""
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        sfv = sum(comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(x, n + 1))
        lo, hi = (lo, mid) if sfv > 1 - conf else (mid, hi)
    return lo


def max_events(n: int, budget: float) -> int | None:
    """Largest number of events whose 99 % upper bound stays within the budget."""
    best = None
    for x in range(0, n + 1):
        if cp_upper(x, n) <= budget:
            best = x
        else:
            break
    return best


def multinomial_terms(n: int, pa, pb):
    """Yield (a, b, numerator) and the denominator of the trinomial (pa, pb, 1 - pa - pb)."""
    pa, pb = frac(pa), frac(pb)
    pc = 1 - pa - pb
    assert pc >= 0
    d = 1
    for q in (pa, pb, pc):
        d = d * q.denominator // _gcd(d, q.denominator)
    a_, b_, c_ = int(pa * d), int(pb * d), int(pc * d)
    pw_a = [a_**i for i in range(n + 1)]
    pw_b = [b_**i for i in range(n + 1)]
    pw_c = [c_**i for i in range(n + 1)]
    out = []
    for a in range(n + 1):
        for b in range(n - a + 1):
            out.append((a, b, comb(n, a) * comb(n - a, b) * pw_a[a] * pw_b[b] * pw_c[n - a - b]))
    return out, d**n


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


# ---------------------------------------------------------------------------------------------
# Onset geometry: which onsets give the same sensor history
# ---------------------------------------------------------------------------------------------


def onset_geometry() -> dict:
    gnss_every = CONTROL_PERIOD_STEPS * GNSS_PERIOD_CYCLES  # steps between GNSS fixes
    rows = []
    groups: dict[int, list[float]] = {}
    for t in ONSETS_M15 + [0.0, 0.02, 0.05]:
        start_step = round(t / DT_S)
        # The fault is active when start_step <= step (inclusive) and step < end_step. A GNSS fix
        # is taken at steps that are multiples of gnss_every, so the first biased fix is the first
        # such step at or after start_step.
        first_fix = -(-start_step // gnss_every) * gnss_every
        rows.append({"onset_s": t, "start_step": start_step, "first_biased_gnss_step": first_fix,
                     "first_biased_gnss_s": r6(first_fix * DT_S), "on_gnss_fix": start_step == first_fix})
        groups.setdefault(first_fix, []).append(t)
    return {
        "dt_s": DT_S,
        "control_period_steps": CONTROL_PERIOD_STEPS,
        "gnss_period_cycles": GNSS_PERIOD_CYCLES,
        "steps_between_gnss_fixes": gnss_every,
        "rows": rows,
        "groups_by_first_biased_gnss_step": {str(k): v for k, v in sorted(groups.items())},
        "m15_onset_list": ONSETS_M15,
        "corrected_onset_list": ONSETS,
        "m15_onsets_sharing_a_sensor_history": [g for g in groups_by_onset(ONSETS_M15) if len(g) > 1],
        "m15_onsets_distinct_conditions": len({g for g in groups_for(ONSETS_M15)}),
        "corrected_onsets_distinct_conditions": len({g for g in groups_for(ONSETS)}),
    }


def groups_by_onset(onsets: list[float]) -> list[list[float]]:
    out: dict[int, list[float]] = {}
    for t, g in zip(onsets, groups_for(onsets)):
        out.setdefault(g, []).append(t)
    return [out[k] for k in sorted(out)]


def groups_for(onsets: list[float]) -> list[int]:
    gnss_every = CONTROL_PERIOD_STEPS * GNSS_PERIOD_CYCLES
    return [-(-round(t / DT_S) // gnss_every) * gnss_every for t in onsets]


# ---------------------------------------------------------------------------------------------
# Seed maps (default layout) and their checks
# ---------------------------------------------------------------------------------------------

LAYOUT = {
    "A_low": {"first": 44000, "onsets": 7, "magnitudes": 4, "reps": 6, "arms": 2},
    "A_high": {"first": 44168, "onsets": 7, "magnitudes": 4, "reps": 5, "arms": 2},
    "B": {"first": 44308, "seeds": 60, "arms": 17 * 2},
    "C": {"first": 44368, "seeds": 60, "arms": 3 * 4},
    "D": {"first": 44428, "onsets": 7, "magnitudes": 4, "reps": 11, "arms": 2 * 3},
    "E": {"first": 44736, "families": 8, "points": 20, "arms": 3},
}


FORMULAS = {
    "A_low": "44000 + 24*i + 6*j + r; i = onset index in ONSETS (0..6), j = magnitude index in {5, 7, 9, 10.5} (0..3), r = 0..5",
    "A_high": "44168 + 20*i + 5*j + r; i = onset index (0..6), j = magnitude index in {13.5, 17, 22, 30} (0..3), r = 0..4",
    "B": "44308 + s; s = 0..59; every seed runs all 17 magnitude levels at onsets 5 s and 15 s",
    "C": "44368 + s; s = 0..59; every seed runs the 3 conditions x 4 arms",
    "D": "44428 + 44*i + 11*j + r; i = onset index (0..6), j = magnitude index in {5, 8, 10.5, 15} (0..3), r = 0..10",
    "E": "44736 + 20*f + k; f = family in the order of g3-onset.json (0..7), k = Halton point 0..19",
}


def seed_map() -> tuple[dict[int, tuple], dict]:
    """seed -> condition for every stage, and a per-stage summary."""
    cond: dict[int, tuple] = {}
    summary: dict[str, dict] = {}

    def put(stage: str, seed: int, c: tuple) -> None:
        assert seed not in cond, f"seed {seed} used twice"
        cond[seed] = (stage, *c)

    a = LAYOUT["A_low"]
    for i in range(a["onsets"]):
        for j in range(a["magnitudes"]):
            for r in range(a["reps"]):
                put("A_low", a["first"] + 24 * i + 6 * j + r, (ONSETS[i], LOW_BAND[j]))
    a = LAYOUT["A_high"]
    for i in range(a["onsets"]):
        for j in range(a["magnitudes"]):
            for r in range(a["reps"]):
                put("A_high", a["first"] + 20 * i + 5 * j + r, (ONSETS[i], HIGH_BAND[j]))
    b = LAYOUT["B"]
    for s in range(b["seeds"]):
        put("B", b["first"] + s, ("all 17 levels 10.0..14.0 step 0.25", "onsets 5 and 15"))
    c = LAYOUT["C"]
    for s in range(c["seeds"]):
        put("C", c["first"] + s, ("3 conditions x 4 arms",))
    d = LAYOUT["D"]
    for i in range(d["onsets"]):
        for j in range(d["magnitudes"]):
            for r in range(d["reps"]):
                put("D", d["first"] + 44 * i + 11 * j + r, (ONSETS[i], MITIGATION_MAGNITUDES[j]))
    e = LAYOUT["E"]
    for f in range(e["families"]):
        for k in range(e["points"]):
            put("E", e["first"] + 20 * f + k, (f, k))

    for stage in ("A_low", "A_high", "B", "C", "D", "E"):
        seeds = sorted(s for s, v in cond.items() if v[0] == stage)
        arms = LAYOUT[stage]["arms"]
        per_condition: dict[tuple, int] = {}
        for sd in seeds:
            per_condition[cond[sd][1:]] = per_condition.get(cond[sd][1:], 0) + 1
        summary[stage] = {"first": seeds[0], "last": seeds[-1], "seeds": len(seeds),
                          "arms_per_seed": arms, "runs": len(seeds) * arms,
                          "contiguous": seeds == list(range(seeds[0], seeds[-1] + 1)),
                          "formula": FORMULAS[stage],
                          "distinct_conditions": len(per_condition),
                          "seeds_per_condition_min": min(per_condition.values()),
                          "seeds_per_condition_max": max(per_condition.values())}
    return cond, summary


def seed_checks(cond: dict[int, tuple], summary: dict) -> dict:
    seeds = sorted(cond)
    overlaps = {name: [s for s in seeds if lo <= s <= hi] for name, (lo, hi) in SPENT_OR_PROTECTED.items()}
    used_last = max(seeds)
    return {
        "seeds_used": len(seeds),
        "first_seed": seeds[0],
        "last_seed": used_last,
        "all_within_44000_44919": seeds[0] >= SEED_FIRST and used_last <= SEED_LAST,
        "no_seed_in_reserve_44920_44999": not any(RESERVE_FIRST <= s <= SEED_RANGE_LAST for s in seeds),
        "each_seed_one_condition": len(seeds) == len(set(seeds)) == len(cond),
        "overlap_with_spent_or_protected": {k: len(v) for k, v in sorted(overlaps.items())},
        "stage_ranges_disjoint": all(
            summary[a]["last"] < summary[b]["first"]
            for a, b in (("A_low", "A_high"), ("A_high", "B"), ("B", "C"), ("C", "D"), ("D", "E"))
        ),
        "unassigned_first": used_last + 1,
        "unassigned_last": SEED_LAST,
        "unassigned_seeds": SEED_LAST - used_last,
        "reserve": [RESERVE_FIRST, SEED_RANGE_LAST],
        "total_runs": sum(v["runs"] for v in summary.values()),
    }


def m15_layout_totals() -> dict:
    """The M15 candidate's own totals, recomputed (8 onsets)."""
    stages = {"A": (44000, 44319, 2), "B": (44320, 44379, 34), "C": (44380, 44439, 12),
              "D": (44440, 44759, 6), "E": (44760, 44919, 3)}
    mapa = {44000 + 40 * i + 5 * j + r for i in range(8) for j in range(8) for r in range(5)}
    mapd = {44440 + 40 * i + 10 * j + r for i in range(8) for j in range(4) for r in range(10)}
    return {
        "seeds": sum(b - a + 1 for a, b, _ in stages.values()),
        "runs": sum((b - a + 1) * k for a, b, k in stages.values()),
        "map_A_distinct": len(mapa), "map_D_distinct": len(mapd),
    }


# ---------------------------------------------------------------------------------------------
# Recorded evidence (read from the base commit)
# ---------------------------------------------------------------------------------------------


def evidence() -> dict:
    frag = json.loads(blob(BASE, "docs/evidence/m14/fragility/fragility.json"))
    test = json.loads(blob(BASE, "docs/evidence/m14/masking/test.json"))
    inv = json.loads(blob(BASE, "docs/evidence/m13/g3-onset/investigation.json"))
    rows = {(r["arm"], r["magnitude_m"]): r for r in frag["onset"]["rows"]}
    zero = [rows[("onset-0s", m)] for m in (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)]
    env = inv["findings"]["envelope"]
    cells = env["cells"]  # cells[onset index][magnitude index] = seeds (of 4) with R1 violated
    mags = env["axes"][1]["values"]
    low_cols = [j for j, m in enumerate(mags) if m <= 10.0]
    high_cols = [j for j, m in enumerate(mags) if m >= 13.0]
    env_zero_all = sum(4 - cells[0][j] for j in range(len(mags)))
    env_zero_low = sum(4 - cells[0][j] for j in low_cols)
    env_late_low_fail = sum(cells[i][j] for i in range(1, len(cells)) for j in low_cols)
    env_late_low_n = 4 * (len(cells) - 1) * len(low_cols)
    env_late_high_hold = sum(4 - cells[i][j] for i in range(1, len(cells)) for j in high_cols)
    env_late_high_n = 4 * (len(cells) - 1) * len(high_cols)
    sweep = {r["onset_s"]: r for r in test["onset_sweep"]}
    levels = {r["magnitude_m"]: r for r in test["magnitude_sweep"] if r["onset_s"] == 5.0}

    p0_sources = [
        {"source": "M9.1 G3 (docs/m9-powered-landing.md l. 619), seeds 2000-2029, magnitudes 5.7-30 m",
         "read_from": "transcribed", "success": 30, "n": 30},
        {"source": "M14 fragility, onset 0 s, six magnitudes 5-30 m (fragility.json onset.rows)",
         "read_from": "fragility.json", "success": sum(r["r1_pass"] for r in zero), "n": sum(r["n"] for r in zero)},
        {"source": "M13 envelope row onset 0 s, 16 magnitudes 5-30 m, 4 seeds (investigation.json)",
         "read_from": "investigation.json", "success": env_zero_all, "n": 4 * len(mags)},
        {"source": "M14 masking test, onset 0 s, 8 m, seeds 47000-47019 (test.json)",
         "read_from": "test.json", "success": sweep[0.0]["r1_holds"], "n": sweep[0.0]["n"]},
    ]
    p0_low_sources = [
        {"source": "M14 fragility, onset 0 s, 5 and 10 m",
         "success": zero[0]["r1_pass"] + zero[1]["r1_pass"], "n": zero[0]["n"] + zero[1]["n"]},
        {"source": "M13 envelope row onset 0 s, magnitudes <= 10 m", "success": env_zero_low, "n": 4 * len(low_cols)},
        {"source": "M14 masking test, onset 0 s, 8 m", "success": sweep[0.0]["r1_holds"], "n": sweep[0.0]["n"]},
    ]
    # Late onsets in the low band: one run set per distinct condition (0.01, 0.02 and 0.1 s are one
    # condition on the same seeds, so they are counted once).
    q_sources = [
        {"source": "M14 fragility, onsets 2, 5, 10 s at 5 and 10 m (R1 fails)", "failures": 180, "n": 180,
         "read_from": "fragility.json",
         "check": sum(30 - r["r1_pass"] for r in frag["onset"]["rows"]
                      if r["arm"] != "onset-0s" and r["magnitude_m"] in (5.0, 10.0))},
        {"source": "M13 envelope, 15 late onsets, magnitudes <= 10 m, 4 seeds (R1 violated)",
         "failures": env_late_low_fail, "n": env_late_low_n, "read_from": "investigation.json"},
        {"source": "M14 masking test, 8 m at onsets 0.1 (=0.01=0.02), 1, 5, 10, 20 s: 5 distinct conditions",
         "failures": 5 * 20 - sum(sweep[t]["r1_holds"] for t in (0.1, 1.0, 5.0, 10.0, 20.0)),
         "n": 5 * 20, "read_from": "test.json"},
    ]
    h2_sources = [
        {"source": "M14 fragility, onsets 2, 5, 10 s, magnitudes 15-30 m (R1 holds)",
         "success": sum(r["r1_pass"] for r in frag["onset"]["rows"] if r["arm"] != "onset-0s" and r["magnitude_m"] >= 15.0),
         "n": sum(r["n"] for r in frag["onset"]["rows"] if r["arm"] != "onset-0s" and r["magnitude_m"] >= 15.0),
         "read_from": "fragility.json"},
        {"source": "M13 envelope, 15 late onsets, magnitudes >= 13.3 m, 4 seeds (R1 holds)",
         "success": env_late_high_hold, "n": env_late_high_n, "read_from": "investigation.json"},
        {"source": "M14 masking test, onset 5 s, 13.5-15 m (R1 holds)",
         "success": sum(levels[m]["r1_holds"] for m in levels if m >= 13.5),
         "n": sum(levels[m]["n"] for m in levels if m >= 13.5), "read_from": "test.json"},
    ]

    def pool(rows: list[dict], key: str) -> dict:
        x = sum(r[key] for r in rows)
        n = sum(r["n"] for r in rows)
        return {"x": x, "n": n, "cp99_lower": r6(cp_lower(x, n)) if x else 0.0,
                "cp99_upper": r6(cp_upper(x, n)) if x < n else 1.0}

    return {
        "p0_all_magnitudes_0s": {"sources": p0_sources, "pooled": pool(p0_sources, "success")},
        "p0_low_band_0s": {"sources": p0_low_sources, "pooled": pool(p0_low_sources, "success")},
        "q_late_fails_low_band": {"sources": q_sources, "pooled": pool(q_sources, "failures")},
        "h2_late_holds_high_band": {"sources": h2_sources, "pooled": pool(h2_sources, "success")},
        "the_value_0_93": {
            "recorded_in_evidence": False,
            "where_it_appears": ["docs/review/g3-onset/independent-checks.md (section 3, as a hypothetical)",
                                 "docs/review/g3-onset/reviewer-questions.md (question 25, 'por exemplo')"],
            "meaning": "a rate above the G3 floor of 27/30 = 0.9, used as an illustration; no recorded run "
                       "set measures a 0 s R1 rate of 0.93",
        },
        "distinct_seed_bounds": distinct_seed_bounds(),
        "note": "The pooled counts are runs, not independent seeds: the fragility arms reuse the same 30 "
                "seeds at every magnitude and onset, and the M13 envelope reuses 4 seeds in every cell, so "
                "the run-level Clopper-Pearson bounds are optimistic; distinct_seed_bounds counts each seed "
                "once under the assumption (taken from the experiment specs) that arms share seeds. The M13 "
                "baseline (30/30 at 15 m) is not pooled because its seeds were not compared with the others.",
    }


def distinct_seed_bounds() -> dict:
    """The same evidence counted once per distinct seed (30 fragility + 4 envelope + 20 test + 30 M9.1)."""
    def bound(x: int, n: int) -> dict:
        return {"x": x, "n": n, "cp99_lower": r6(cp_lower(x, n)) if x else 0.0}
    return {
        "p0_all_magnitudes_0s_distinct_seeds": bound(84, 84),
        "p0_low_band_0s_distinct_seeds": bound(54, 54),
        "q_late_fails_low_band_distinct_seeds": bound(54, 54),
        "h2_late_holds_high_band_distinct_seeds": bound(54, 54),
        "assumption": "every seed passed in every cell it was used in, so each distinct seed counts as a success",
    }


# ---------------------------------------------------------------------------------------------
# Thresholds and the 63 versus 69 question
# ---------------------------------------------------------------------------------------------


def alpha_table() -> dict:
    rows = {}
    for label, a in (("0.01/2", F(1, 200)), ("0.01/3", F(1, 300)), ("0.01/7", F(1, 700)),
                     ("0.01/14", F(1, 1400)), ("0.01", F(1, 100))):
        n = min_n_all_success(a)
        lo, hi = min_n_interval(n)
        rows[label] = {"alpha": r6(a), "min_n_all_success": n,
                       "alpha_interval_for_this_n": [round(lo, 7), round(hi, 7)],
                       "alpha_inside_interval": lo <= float(a) < hi}
    mcnemar = {}
    for label, a in (("0.01/7", F(1, 700)), ("0.01/14", F(1, 1400))):
        d = 1
        while F(1, 2**d) >= a:
            d += 1
        mcnemar[label] = d
    return {"binomial_all_success": rows, "mcnemar_min_discordant_all_predicted": mcnemar,
            "answer": {
                "63": "minimum n at alpha 0.01/7",
                "69": "minimum n at alpha 0.01/14",
                "level_needed_by_S4_S5": "0.01/7: S4 (and S5) is one of the SECONDARY family tests; it is confirmed "
                                         "only if both conditions reject, an intersection-union rule, so each "
                                         "condition is tested at the full per-test level 0.01/7 with no further "
                                         "halving",
                "minimum_n_for_a_binomial_test_of_S4_S5": 63}}


def tests_table(n_low: int, n_high: int, n_d_low: int, n_d_pair: int) -> dict:
    """Thresholds, exact size and power for every proportion test of the default layout."""
    a3, a7, a2 = F(1, 300), F(1, 700), F(1, 200)
    grid = [F("0.9"), F("0.93"), F("0.95"), F("0.97"), F("0.99"), F(1)]
    spec = {
        "H2_late_holds_high_band": (n_high, a3),
        "H1a_late_fails_low_band": (n_low, a3),
        "H1b_zero_s_holds_low_band": (n_low, a3),
        "S3_R5_fails_at_0s_high_band": (n_high, a7),
        "S6_first_rejection_in_window": (n_high, a7),
        "S7_each_proportion": (n_d_pair, a7),
        "M1_threshold_1m": (n_d_low, a2),
        "M2_threshold_2m": (n_d_pair, a2),
        "H2_if_E_has_19_points_and_n_high_168": (168, a3),
        "H1_and_H2_if_A_and_D_arms_are_pooled_n_low_399": (399, a3),
        "H2_if_A_and_D_arms_are_pooled_n_high_217": (217, a3),
        "S3_if_A_and_D_arms_are_pooled_n_high_217": (217, a7),
        "M15_H1_H2_n160": (160, a3),
        "M15_S3_n160": (160, a7),
        "M15_M1_n240": (240, a2),
        "M15_M2_n80": (80, a2),
        "M15_S7_n80": (80, a7),
    }
    out = {}
    for name, (n, a) in spec.items():
        k = threshold(n, a)
        out[name] = {
            "n": n, "alpha": r6(a), "reject_if_successes_at_least": k,
            "failures_tolerated": None if k is None else n - k,
            "size": None if k is None else r6(sf(k, n, F(9, 10))),
            "power_at_pi": {f"{float(p):.2f}": r6(power(n, p, a)) for p in grid},
            "mde_pi_power_0.8": mde(n, a), "mde_pi_power_0.9": mde(n, a, F(9, 10)),
        }
    return out


# ---------------------------------------------------------------------------------------------
# S4 and S5: pairs, 60 seeds
# ---------------------------------------------------------------------------------------------


def s4_s5() -> dict:
    a7 = F(1, 700)
    rows = {}
    for n in (60, 63, 70, 77, 84, 100, 150):
        k = threshold(n, a7)
        rows[str(n)] = {
            "binomial_threshold_alpha_0.01/7": k,
            "failures_tolerated": None if k is None else n - k,
            "power_pi_0.95": None if k is None else r6(sf(k, n, F("0.95"))),
            "power_pi_0.97": None if k is None else r6(sf(k, n, F("0.97"))),
            "power_pi_0.99": None if k is None else r6(sf(k, n, F("0.99"))),
        }
    # The M15 rule on 60 pairs: a point rule (>= 54 of 60 in the predicted direction) plus an exact
    # McNemar test; with >= 54 predicted the McNemar p is already below 5e-11.
    rule = {str(p): r6(sf(54, 60, p)) for p in ("0.75", "0.8", "0.85", "0.9", "0.95", "0.97", "0.99")}
    return {"binomial_by_n": rows, "rule_54_of_60_acceptance_probability": rule,
            "mcnemar_p_with_54_predicted_and_6_opposite": float(f"{float(sf(54, 60, F(1, 2))):.3e}"),
            "mcnemar_p_is_always_below_alpha_when_fraction_rule_passes": float(sf(54, 60, F(1, 2))) < 1 / 700,
            "success_definition": "S4: guarded without rule 2 meets R1 AND robust fails R1 on the same seed; "
                                  "S5: registered guarded meets R1 AND the 1000 m threshold arm fails R1 on the "
                                  "same seed. Both are conjunctions over two arms, like H1."}


# ---------------------------------------------------------------------------------------------
# H1 design options
# ---------------------------------------------------------------------------------------------

SCENARIOS = [
    ("p0=1.00 q=1.00", F(1), F(1)),
    ("p0=0.99 q=0.99", F("0.99"), F("0.99")),
    ("p0=0.98 q=0.99", F("0.98"), F("0.99")),
    ("p0=0.97 q=0.99", F("0.97"), F("0.99")),
    ("p0=0.95 q=0.99", F("0.95"), F("0.99")),
    ("p0=0.93 q=0.99", F("0.93"), F("0.99")),
    ("p0=0.93 q=1.00", F("0.93"), F(1)),
    ("p0=0.90 q=1.00 (G3 floor)", F("0.9"), F(1)),
    ("p0=1.00 q=0.93 (one onset in seven fails half the time)", F(1), F("0.93")),
]


def sign_threshold(d: int, alpha) -> int | None:
    """Smallest k with P(Bin(d, 1/2) >= k) <= alpha, or None."""
    alpha = frac(alpha)
    tail = 0
    for i in range(d, -1, -1):
        tail += comb(d, i)
        if F(tail, 2**d) > alpha:
            return i + 1 if i + 1 <= d else None
    return 0


def option_powers(n: int, alpha, p0, q, with_mcnemar: bool = True) -> dict:
    a = frac(alpha)
    p0, q = frac(p0), frac(q)
    pi = p0 * q
    # O0: the M15 conjunction as one proportion, pi = p0 * q (arms independent given the seed).
    o0 = power(n, pi, a)
    # O1: two proportions on the same seeds, both must reject (intersection-union).
    pa, pb = power(n, q, a), power(n, p0, a)
    o1_indep = pa * pb
    # O2: H1b as in O1, plus the late-onset test conditional on the seeds that meet R1 at 0 s.
    kb = threshold(n, a)
    o2 = F(0)
    o2_cond_only = F(0)
    for x in range(0, n + 1):
        px = comb(n, x) * p0**x * (1 - p0) ** (n - x)
        cond = power(x, q, a) if x > 0 else F(0)
        o2_cond_only += px * cond
        if kb is not None and x >= kb:
            o2 += px * cond
    # O3: exact sign (McNemar) test on discordant seeds: A0 and fails-late vs not-A0 and not-fails-late.
    o3 = None
    if with_mcnemar:
        pa_d, pb_d = p0 * q, (1 - p0) * (1 - q)
        terms, den = multinomial_terms(n, pa_d, pb_d)
        sign_k = {d: sign_threshold(d, a) for d in range(n + 1)}
        num = sum(t for (x, y, t) in terms if sign_k[x + y] is not None and x >= sign_k[x + y])
        o3 = F(num, den)
    return {
        "O0_conjunction": r6(o0),
        "O1_split_independent": r6(o1_indep), "O1_split_frechet_low": r6(max(F(0), pa + pb - 1)),
        "O1_split_frechet_high": r6(min(pa, pb)), "O1_each": {"late_fails": r6(pa), "zero_s_holds": r6(pb)},
        "O2_conditional_with_H1b": r6(o2), "O2_conditional_only": r6(o2_cond_only),
        "O3_mcnemar_sign_test": None if o3 is None else r6(o3),
        "O5_null_0.8_for_H1b_with_O1": r6(pa * power(n, p0, a, F(4, 5))),
    }


def n_needed(pi, alpha, target=F(4, 5), limit=3000, step=10):
    """Smallest n (a multiple of `step`) whose exact power reaches `target`; None above `limit`.

    The power of an exact test is not monotone in n (it follows the size of the rejection region),
    so the answer is a grid value, not a sharp minimum."""
    n = step
    while n <= limit:
        if power(n, pi, alpha) >= target:
            return n
        n += step
    return None


def h1_options(n: int, with_mcnemar: bool = True) -> dict:
    out = {"n_low_band": n, "alpha_bonferroni": "0.01/3", "alpha_full": "0.01", "scenarios": {}}
    for label, p0, q in SCENARIOS:
        out["scenarios"][label] = {
            "alpha_0.01/3": option_powers(n, F(1, 300), p0, q, with_mcnemar),
            "alpha_0.01": option_powers(n, F(1, 100), p0, q, with_mcnemar),
        }
    out["thresholds"] = {"alpha_0.01/3": threshold(n, F(1, 300)), "alpha_0.01": threshold(n, F(1, 100)),
                         "null_0.8_alpha_0.01/3": threshold(n, F(1, 300), F(4, 5))}
    # MDE for symmetric p = p0 = q, joint power >= 0.8.
    sym = {}
    for name, fn in (("O0_conjunction", lambda p: option_powers(n, F(1, 300), p, p, False)["O0_conjunction"]),
                     ("O1_split_independent", lambda p: option_powers(n, F(1, 300), p, p, False)["O1_split_independent"])):
        found = None
        for i in range(901, 1001):
            if fn(F(i, 1000)) >= 0.8:
                found = i / 1000
                break
        sym[name] = found
    out["mde_symmetric_p0_eq_q_power_0.8_alpha_0.01/3"] = sym
    # Reallocation: the n that the single conjunction needs.
    out["reallocation_n_needed_O0_power_0.8"] = {
        label: {"alpha_0.01/3": n_needed(p0 * q, F(1, 300)), "alpha_0.01": n_needed(p0 * q, F(1, 100))}
        for label, p0, q in SCENARIOS if p0 * q > F(9, 10)
    }
    out["reallocation_n_needed_O1_each_proportion_power_0.8_alpha_0.01/3"] = {
        f"{float(p):.2f}": n_needed(p, F(1, 300)) for p in (F("0.93"), F("0.95"), F("0.97"), F("0.99"))
    }
    return out


# ---------------------------------------------------------------------------------------------
# Median intervals (H3, S1, S2) by order statistics, exact
# ---------------------------------------------------------------------------------------------


def os_positions(n: int, alpha) -> tuple[int, int]:
    """Positions (l, u) of the distribution-free interval [X(l), X(u)] for the median: each tail <= alpha."""
    alpha = frac(alpha)
    best = 1
    for l in range(1, n // 2 + 1):
        if F(sum(comb(n, i) for i in range(l)), 2**n) <= alpha:
            best = l
    return best, n + 1 - best


def bs_distribution() -> tuple[dict[F, F], F]:
    test = json.loads(blob(BASE, "docs/evidence/m14/masking/test.json"))
    pred = json.loads(blob(BASE, "docs/evidence/m14/masking/prediction.json"))
    holds = {F(str(r["magnitude_m"])): r["r1_holds"] for r in test["magnitude_sweep"] if r["onset_s"] == 5.0}
    seeds = {r["n"] for r in test["magnitude_sweep"] if r["onset_s"] == 5.0}
    assert seeds == {20}
    levels = sorted(holds)
    prev, dist = 0, {}
    for lev in levels:
        c = holds[lev]
        assert c >= prev, "R1-hold counts must be monotone for the b_s reconstruction"
        if c > prev:
            dist[lev] = F(c - prev, 20)
            prev = c
    assert prev == 20
    return dist, F(pred["P1"]["b_star_m"])


def median_interval_power(dist: dict[F, F], bstar: F, n: int, l: int, u: int, tol: F, shift: F) -> dict:
    """Exact P(confirm) and P(refute) of the equivalence test on the median of b_s.

    The interval for the median is [X(l) - 0.25, X(u)]. Confirm: the interval lies inside
    (b* - tol, b* + tol). Refute: it lies entirely outside. `shift` moves the whole distribution.
    """
    q = F(1, 4)
    shifted = {k + shift: v for k, v in dist.items()}

    def mass(pred) -> F:
        return sum((v for k, v in shifted.items() if pred(k)), F(0))

    # classes for the lower end: count of b_s <= b* - tol + q must be <= l - 1
    p_low = mass(lambda k: k <= bstar - tol + q)
    # upper end: count of b_s < b* + tol must be >= u
    p_up = mass(lambda k: k < bstar + tol)
    p_b = p_up - p_low
    assert p_b >= 0
    terms, den = multinomial_terms(n, p_low, p_b)
    confirm = F(sum(t for (a, b, t) in terms if a <= l - 1 and a + b >= u), den)
    # refute high: X(l) - q >= b* + tol  <=>  count of b_s < b* + tol + q is <= l - 1
    p_hi = mass(lambda k: k < bstar + tol + q)
    refute_hi = sum(comb(n, i) * p_hi**i * (1 - p_hi) ** (n - i) for i in range(0, l))
    # refute low: X(u) <= b* - tol  <=>  count of b_s <= b* - tol is >= u
    p_lo2 = mass(lambda k: k <= bstar - tol)
    refute_lo = sum(comb(n, i) * p_lo2**i * (1 - p_lo2) ** (n - i) for i in range(u, n + 1))
    return {"confirm": r6(confirm), "refute": r6(refute_hi + refute_lo)}


class SplitMix64:
    """SplitMix64 (Steele, Lea and Flood 2014): state += 0x9E3779B97F4A7C15, then two xor-shift-multiply."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)


def mc_confirm(dist: dict[F, F], bstar: F, n: int, l: int, u: int, tol: F, shift: F) -> dict:
    """Monte Carlo cross-check of the exact confirm probability (sampling, explicit generator and seed)."""
    rng = SplitMix64(MC_SEED)
    levels = sorted(dist)
    cum, acc = [], F(0)
    for k in levels:
        acc += dist[k]
        cum.append(int(acc * 20))  # cumulative mass in twentieths
    hits = 0
    for _ in range(MC_REPS):
        sample = []
        for _ in range(n):
            r = rng.next() % 20
            idx = next(i for i, c in enumerate(cum) if r < c)
            sample.append(levels[idx] + shift)
        sample.sort()
        lower, upper = sample[l - 1] - F(1, 4), sample[u - 1]
        if lower > bstar - tol and upper < bstar + tol:
            hits += 1
    p = hits / MC_REPS
    return {"estimate": r6(p), "reps": MC_REPS, "std_error": r6((p * (1 - p) / MC_REPS) ** 0.5)}


def median_tests() -> dict:
    dist, bstar = bs_distribution()
    n = 60
    l3, u3 = os_positions(n, F(1, 300))
    l7, u7 = os_positions(n, F(1, 700))
    shifts = [F(i, 4) for i in range(0, 7)]
    res = {
        "b_s_distribution_from_test_json": {str(float(k)): r6(v) for k, v in sorted(dist.items())},
        "b_star_m": float(bstar), "n_seeds": n,
        "positions": {"H3_alpha_0.01/3": [l3, u3], "S1_S2_alpha_0.01/7": [l7, u7]},
        "assumption": "b_s distribution reconstructed from per-level R1 counts assuming R1 is monotone in "
                      "magnitude within each seed (test.json does not allow checking this); shifts move the "
                      "whole distribution",
        "H3_tol_1.0": {}, "S1_tol_1.0": {}, "S2_tol_0.5": {},
    }
    for s in shifts:
        key = f"{float(s):.2f}"
        res["H3_tol_1.0"][key] = median_interval_power(dist, bstar, n, l3, u3, F(1), s)
        res["S1_tol_1.0"][key] = median_interval_power(dist, bstar, n, l7, u7, F(1), s)
        res["S2_tol_0.5"][key] = median_interval_power(dist, bstar, n, l7, u7, F(1, 2), s)
    res["monte_carlo_crosscheck_H3"] = {
        "generator": "SplitMix64", "seed": MC_SEED,
        "shift_0.00": mc_confirm(dist, bstar, n, l3, u3, F(1), F(0)),
        "shift_0.75": mc_confirm(dist, bstar, n, l3, u3, F(1), F(3, 4)),
    }
    return res


# ---------------------------------------------------------------------------------------------
# Joint rule and budgets
# ---------------------------------------------------------------------------------------------

JOINT_SCENARIOS = [
    ("optimistic", F(1), F(1), F(1), F(0)),
    ("development-like", F("0.99"), F("0.99"), F("0.99"), F(0)),
    ("moderate", F("0.97"), F("0.99"), F("0.97"), F(1, 4)),
    ("pessimistic", F("0.95"), F("0.99"), F("0.97"), F(3, 4)),
]


def joint_rule(n_low: int, n_high: int, with_mcnemar: bool = True) -> dict:
    dist, bstar = bs_distribution()
    out = {"n_low_band": n_low, "n_high_band": n_high}
    for alpha_label, a in (("0.01/3", F(1, 300)), ("0.01/4", F(1, 400)), ("0.01", F(1, 100))):
        l, u = os_positions(60, a)
        rows = {}
        for name, p0, q, h2, shift in JOINT_SCENARIOS:
            h3 = F(str(median_interval_power(dist, bstar, 60, l, u, F(1), shift)["confirm"]))
            h2p = power(n_high, h2, a)
            opts = option_powers(n_low, a, p0, q, with_mcnemar)
            h1a = F(str(opts["O1_each"]["late_fails"]))
            row = {
                "assumptions": {"p0": float(p0), "q": float(q), "H2_pi": float(h2), "boundary_shift_m": float(shift)},
                "H2": r6(h2p), "H3": r6(h3),
                "H1_O0": opts["O0_conjunction"], "H1_O1": opts["O1_split_independent"],
                "H1_O2": opts["O2_conditional_with_H1b"], "H1_O5": opts["O5_null_0.8_for_H1b_with_O1"],
                "H1a_alone": opts["O1_each"]["late_fails"],
                "joint_O0": r6(F(str(opts["O0_conjunction"])) * h2p * h3),
                "joint_O1_H1a_and_H1b_and_H2_and_H3": r6(F(str(opts["O1_split_independent"])) * h2p * h3),
                "joint_O1_H1a_only_with_H1b_as_positive_control": r6(h1a * h2p * h3),
                "joint_O2": r6(F(str(opts["O2_conditional_with_H1b"])) * h2p * h3),
                "joint_O5": r6(F(str(opts["O5_null_0.8_for_H1b_with_O1"])) * h2p * h3),
            }
            if opts["O3_mcnemar_sign_test"] is not None:
                row["joint_O3"] = r6(F(str(opts["O3_mcnemar_sign_test"])) * h2p * h3)
            rows[name] = row
        out[f"alpha_{alpha_label}"] = {"H3_positions": [l, u], "scenarios": rows}
    out["independence"] = ("H1 (low band), H2 (high band) and H3 (stage B) use disjoint seeds, so the joint "
                           "power is the product; inside H1 the two arms share seeds, and the split options "
                           "are reported under independence and as Frechet bounds")
    return out


def family_of_four(n_low: int, n_high: int) -> dict:
    """Thresholds if H1b is counted as a fourth claim-bearing test (Bonferroni 0.01/4)."""
    a = F(1, 400)
    dist, bstar = bs_distribution()
    l, u = os_positions(60, a)
    out = {
        "alpha": r6(a),
        "worst_case_family_error_if_H1b_is_outside_the_family_at_0.01/3": r6(4 * F(1, 300)),
        "H1a_and_H1b_n": n_low, "H1a_and_H1b_reject_if_at_least": threshold(n_low, a),
        "H2_n": n_high, "H2_reject_if_at_least": threshold(n_high, a),
        "H3_positions": [l, u],
        "power_H1a_or_H1b_pi": {f"{p}": r6(power(n_low, F(p), a)) for p in ("0.95", "0.97", "0.99")},
        "power_H2_pi": {f"{p}": r6(power(n_high, F(p), a)) for p in ("0.95", "0.97", "0.99")},
        "H3_confirm_by_shift": {f"{float(s):.2f}": median_interval_power(dist, bstar, 60, l, u, F(1), s)["confirm"]
                                for s in (F(0), F(1, 4), F(1, 2), F(3, 4))},
    }
    return out


def budgets(pairs_all: int, pairs_zero: int) -> dict:
    return {
        "pairs_invariants_and_r2_r6": pairs_all,
        "pairs_r1_at_0s": pairs_zero,
        "min_pairs_for_zero_events_within_1pct": next(n for n in range(1, 2000) if cp_upper(0, n) <= 0.01),
        "invariants_1pct": {"n": pairs_all, "cp99_upper_at_0": r6(cp_upper(0, pairs_all)),
                            "cp99_upper_at_1": r6(cp_upper(1, pairs_all)),
                            "max_events": max_events(pairs_all, 0.01)},
        "r2_r6_5pct": {"n": pairs_all, "max_events": max_events(pairs_all, 0.05),
                       "cp99_upper_at_max": r6(cp_upper(max_events(pairs_all, 0.05), pairs_all))},
        "r1_at_0s_2.5pct": {"n": pairs_zero, "max_events": max_events(pairs_zero, 0.025),
                            "cp99_upper_at_1": r6(cp_upper(1, pairs_zero)),
                            "cp99_upper_at_2": r6(cp_upper(2, pairs_zero))},
        "m15_480_pairs": {"cp99_upper_at_0": r6(cp_upper(0, 480)), "max_events_5pct": max_events(480, 0.05)},
        "m15_320_pairs": {"max_events_2.5pct": max_events(320, 0.025)},
        "if_D_kept_at_7_onsets_x_10_reps": {
            "pairs_invariants": 280 + 160, "cp99_upper_at_0": r6(cp_upper(0, 440)),
            "feasible_within_1pct": cp_upper(0, 440) <= 0.01},
    }


# ---------------------------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------------------------


def build() -> dict:
    cond, summary = seed_map()
    checks = seed_checks(cond, summary)
    n_low = summary["A_low"]["seeds"]
    n_high = summary["A_high"]["seeds"]
    n_d = summary["D"]["seeds"]
    n_d_low = 3 * 7 * 11
    n_d_pair = 7 * 11
    n_e = summary["E"]["seeds"]
    assert (n_d_low, n_d_pair) == (231, 77) and n_d == 4 * n_d_pair
    return {
        "schema": "vv-m19-g3-candidate-calculations.v1",
        "no_simulator_run": True,
        "base_commit": full_sha(BASE),
        "provenance": provenance(),
        "onset_geometry": onset_geometry(),
        "alpha_and_minimum_n": alpha_table(),
        "families": {"primary": PRIMARY, "secondary": SECONDARY, "mitigation": MITIGATION,
                     "alpha": {"primary": r6(F(1, 300)), "secondary": r6(F(1, 700)), "mitigation": r6(F(1, 200))}},
        "layout": {"stages": summary, "checks": checks, "m15_for_comparison": m15_layout_totals(),
                   "band_sizes": {"A_low": n_low, "A_high": n_high, "D_late_per_mitigation": n_d,
                                  "E_per_mitigation": n_e, "M1": n_d_low, "M2": n_d_pair, "S7_each": n_d_pair}},
        "evidence": evidence(),
        "tests": tests_table(n_low, n_high, n_d_low, n_d_pair),
        "s4_s5": s4_s5(),
        "h1_options": h1_options(n_low),
        "h1_options_pooled_A_and_D_n399": h1_options(3 * 7 * 11 + n_low, with_mcnemar=False),
        "h1_options_m15_n160_for_comparison": {
            label: option_powers(160, F(1, 300), p0, q) for label, p0, q in SCENARIOS
            if label in ("p0=0.93 q=1.00", "p0=0.99 q=0.99")},
        "median_tests": median_tests(),
        "joint_rule": joint_rule(n_low, n_high),
        "family_of_four_if_H1b_counts": family_of_four(n_low, n_high),
        "joint_rule_pooled_A_and_D": joint_rule(3 * 7 * 11 + n_low, 77 + n_high, with_mcnemar=False),
        "budgets": budgets(n_d + n_e, n_d),
    }


def render(data: dict) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", help="write the calculations to this path (LF line endings)")
    ap.add_argument("--check", help="recompute and compare the bytes with this file")
    args = ap.parse_args(argv)
    data = render(build())
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"wrote {out} ({len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()})")
    if args.check:
        same = Path(args.check).read_bytes() == data
        print("identical" if same else "DIFFERENT")
        return 0 if same else 1
    if not args.output and not args.check:
        sys.stdout.write(data.decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
