#!/usr/bin/env python3
"""M19: reproducible calculations for the corrected G3 onset protocol candidate.

No output word of any protected or confirmatory seed is generated or inspected here: the RNG analysis is
start-state and stream-position arithmetic only. numpy is used, if present, only for the exhaustive scan.

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
BLOCK_FIRST, BLOCK_LAST = 81000, 81919  # the proposed confirmatory block (assigned and unassigned seeds)
RESERVE = (80904, 80983)  # just below the block; 81920-81999 overlap themselves and 80920-80999 meets the M6 seed 83017
OLD_BLOCK = (44000, 44999)  # the earlier candidate block: protected by the repository guard and left unused

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

def layout(first: int = BLOCK_FIRST, a_high_reps: int = 6, e_points: int = 19) -> dict:
    """Stage sizes and first seeds, allocated contiguously from 44000 in the order A, B, C, D, E."""
    stages: dict[str, dict] = {}
    nxt = first

    def add(name: str, size: int, arms: int) -> None:
        nonlocal nxt
        stages[name] = {"first": nxt, "seeds": size, "arms": arms}
        nxt += size

    add("A_low", 7 * 4 * 6, 2)
    add("A_high", 7 * 4 * a_high_reps, 2)
    add("B", 60, 17 * 2)
    add("C", 60, 3 * 4)
    add("D", 7 * 4 * 11, 2 * 3)
    add("E", 8 * e_points, 3)
    return stages


def formulas(st: dict, a_high_reps: int, e_points: int) -> dict:
    return {
        "A_low": f"{st['A_low']['first']} + 24*i + 6*j + r; i = onset index in ONSETS (0..6), j = magnitude index in {{5, 7, 9, 10.5}} (0..3), r = 0..5",
        "A_high": f"{st['A_high']['first']} + {4 * a_high_reps}*i + {a_high_reps}*j + r; i = onset index (0..6), j = magnitude index in {{13.5, 17, 22, 30}} (0..3), r = 0..{a_high_reps - 1}",
        "B": f"{st['B']['first']} + s; s = 0..59; every seed runs all 17 magnitude levels at onsets 5 s and 15 s",
        "C": f"{st['C']['first']} + s; s = 0..59; every seed runs the 3 conditions x 4 arms",
        "D": f"{st['D']['first']} + 44*i + 11*j + r; i = onset index (0..6), j = magnitude index in {{5, 8, 10.5, 15}} (0..3), r = 0..10",
        "E": f"{st['E']['first']} + {e_points}*f + k; f = family in the order of g3-onset.json (0..7), k = Halton point 0..{e_points - 1}",
    }


def seed_map(first: int = BLOCK_FIRST, a_high_reps: int = 6, e_points: int = 19) -> tuple[dict[int, tuple], dict]:
    """seed -> condition for every stage, and a per-stage summary."""
    st = layout(first, a_high_reps, e_points)
    fm = formulas(st, a_high_reps, e_points)
    cond: dict[int, tuple] = {}
    summary: dict[str, dict] = {}

    def put(stage: str, seed: int, c: tuple) -> None:
        assert seed not in cond, f"seed {seed} used twice"
        cond[seed] = (stage, *c)

    f0 = st["A_low"]["first"]
    for i in range(7):
        for j in range(4):
            for r in range(6):
                put("A_low", f0 + 24 * i + 6 * j + r, (ONSETS[i], LOW_BAND[j]))
    f0 = st["A_high"]["first"]
    for i in range(7):
        for j in range(4):
            for r in range(a_high_reps):
                put("A_high", f0 + 4 * a_high_reps * i + a_high_reps * j + r, (ONSETS[i], HIGH_BAND[j]))
    for s_ in range(60):
        put("B", st["B"]["first"] + s_, ("all 17 levels 10.0..14.0 step 0.25", "onsets 5 and 15"))
        put("C", st["C"]["first"] + s_, ("3 conditions x 4 arms",))
    f0 = st["D"]["first"]
    for i in range(7):
        for j in range(4):
            for r in range(11):
                put("D", f0 + 44 * i + 11 * j + r, (ONSETS[i], MITIGATION_MAGNITUDES[j]))
    f0 = st["E"]["first"]
    for f in range(8):
        for k in range(e_points):
            put("E", f0 + e_points * f + k, (f, k))

    for stage in ("A_low", "A_high", "B", "C", "D", "E"):
        seeds = sorted(sd for sd, v in cond.items() if v[0] == stage)
        per_condition: dict[tuple, int] = {}
        for sd in seeds:
            per_condition[cond[sd][1:]] = per_condition.get(cond[sd][1:], 0) + 1
        summary[stage] = {"first": seeds[0], "last": seeds[-1], "seeds": len(seeds),
                          "arms_per_seed": st[stage]["arms"], "runs": len(seeds) * st[stage]["arms"],
                          "contiguous": seeds == list(range(seeds[0], seeds[-1] + 1)),
                          "formula": fm[stage], "distinct_conditions": len(per_condition),
                          "seeds_per_condition_min": min(per_condition.values()),
                          "seeds_per_condition_max": max(per_condition.values())}
    return cond, summary


def seed_checks(cond: dict[int, tuple], summary: dict) -> dict:
    seeds = sorted(cond)
    protected = dict(SPENT_OR_PROTECTED)
    protected["44000-44999 earlier block"] = OLD_BLOCK
    protected["reserve 80920-80999"] = RESERVE
    overlaps = {name: [sd for sd in seeds if lo <= sd <= hi] for name, (lo, hi) in protected.items()}
    used_last = max(seeds)
    return {
        "seeds_used": len(seeds),
        "first_seed": seeds[0],
        "last_seed": used_last,
        "all_within_block": seeds[0] >= BLOCK_FIRST and used_last <= BLOCK_LAST,
        "no_seed_in_reserve": not any(RESERVE[0] <= sd <= RESERVE[1] for sd in seeds),
        "no_seed_in_44000_44999": not any(OLD_BLOCK[0] <= sd <= OLD_BLOCK[1] for sd in seeds),
        "each_seed_one_condition": len(seeds) == len(set(seeds)) == len(cond),
        "overlap_with_spent_or_protected": {k: len(v) for k, v in sorted(overlaps.items())},
        "stage_ranges_disjoint": all(
            summary[a]["last"] < summary[b]["first"]
            for a, b in (("A_low", "A_high"), ("A_high", "B"), ("B", "C"), ("C", "D"), ("D", "E"))
        ),
        "unassigned_first": used_last + 1,
        "unassigned_last": BLOCK_LAST,
        "unassigned_seeds": BLOCK_LAST - used_last,
        "reserve": list(RESERVE),
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
        "H1b_pooled_zero_s_both_bands_0.01": (n_low + n_high, F(1, 100)),
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
# Revision 2: Holm step-down over {H1a, H2, H3}, serial gates, cells, seed independence
# ---------------------------------------------------------------------------------------------

LEVELS = (F(1, 300), F(1, 200), F(1, 100))  # 0.01/3, 0.01/2, 0.01: the Holm ladder for a family of 3
NOT_ACTING_FRACTION = F(1, 20)


def class_probs_binom(n: int, pi) -> dict[int, F]:
    """Class 3: rejects at 0.01/3; 2: at 0.01/2 but not 0.01/3; 1: at 0.01 only; 0: never."""
    pi = frac(pi)
    t = [threshold(n, a) for a in LEVELS]
    tail = [F(0) if k is None else sf(k, n, pi) for k in t]
    return {3: tail[0], 2: tail[1] - tail[0], 1: tail[2] - tail[1], 0: 1 - tail[2]}


def class_probs_h3(dist: dict[F, F], bstar: F, n: int, tol: F, shift: F) -> dict[int, F]:
    pos = [os_positions(n, a) for a in LEVELS]
    q = F(1, 4)
    shifted = {k + shift: v for k, v in dist.items()}
    p_low = sum((v for k, v in shifted.items() if k <= bstar - tol + q), F(0))
    p_up = sum((v for k, v in shifted.items() if k < bstar + tol), F(0))
    terms, den = multinomial_terms(n, p_low, p_up - p_low)
    acc = {3: 0, 2: 0, 1: 0, 0: 0}
    for a, b, t in terms:
        cls = 0
        for rank, (l, u) in zip((3, 2, 1), pos):
            if a <= l - 1 and a + b >= u:
                cls = rank
                break
        acc[cls] += t
    return {c: F(v, den) for c, v in acc.items()}


def holm_ok(classes: tuple[int, int, int]) -> bool:
    """Holm step-down at family level 0.01 rejects all three: p(1) <= a/3, p(2) <= a/2, p(3) <= a."""
    return (sum(c >= 3 for c in classes) >= 1 and sum(c >= 2 for c in classes) >= 2
            and all(c >= 1 for c in classes))


def holm_joint(pa: dict, pb: dict, pc: dict) -> F:
    return sum((pa[x] * pb[y] * pc[z] for x in range(4) for y in range(4) for z in range(4)
                if holm_ok((x, y, z))), F(0))


def holm_rest(pb: dict, pc: dict) -> dict[int, F]:
    """P(Holm rejects all three | class of H1a = c), over the classes of H2 and H3."""
    return {c: sum((pb[y] * pc[z] for y in range(4) for z in range(4) if holm_ok((c, y, z))), F(0))
            for c in range(4)}


def class_of(count: int, thr3, thr2, thr1) -> int:
    if thr3 is not None and count >= thr3:
        return 3
    if thr2 is not None and count >= thr2:
        return 2
    if thr1 is not None and count >= thr1:
        return 1
    return 0


POSTERIOR_SHIFTS = (F(0), F(1, 4), F(1, 2), F(3, 4))  # illustrative prior over the boundary shift of H3
COMMON_P_GRID = ("0.90", "0.93", "0.95", "0.97", "0.98", "0.99", "0.995", "0.999")
S4_S5_ASSUMED_RATE = "0.80"


def pmf_binom(n: int, p) -> list[F]:
    p = frac(p)
    return [comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n + 1)]


def pmf_beta_binom(n: int, a, b) -> list[F]:
    """Exact beta-binomial pmf (the binomial averaged over a Beta(a, b) prior or posterior), rational a, b."""
    a, b = frac(a), frac(b)
    p0 = F(1)
    for i in range(n):
        p0 *= (b + i) / (a + b + i)
    out = [p0]
    for k in range(n):
        out.append(out[-1] * F(n - k, k + 1) * (a + k) / (b + n - k - 1))
    return out


def tail_of(pmf: list[F], k) -> F:
    return F(0) if k is None else sum(pmf[k:], F(0))


def class_probs_pmf(n: int, pmf: list[F]) -> dict[int, F]:
    t = [threshold(n, a) for a in LEVELS]
    tail = [tail_of(pmf, k) for k in t]
    return {3: tail[0], 2: tail[1] - tail[0], 1: tail[2] - tail[1], 0: 1 - tail[2]}


def beta_half_quantile(x: int, q: float, steps: int = 40000) -> float:
    """Quantile q of the Jeffreys posterior Beta(x + 1/2, 1/2) for x successes and no failures.

    With p = 1 - t^2 the density in t is proportional to (1 - t^2)^(x - 1/2), smooth on [0, 1]; the
    quantile is found on a midpoint grid with linear interpolation. Floating point, rounded by the caller."""
    a1 = x + 0.5 - 1.0
    w = [(1.0 - ((i + 0.5) / steps) ** 2) ** a1 for i in range(steps)]
    total = sum(w)
    acc = 0.0
    for i in range(steps - 1, -1, -1):
        wi = w[i] / total
        if acc + wi >= q:
            t = (i + 1) / steps - (q - acc) / wi / steps
            return 1.0 - t * t
        acc += wi
    return 0.0


def design_power(n_low: int, n_high: int, pmf_q, pmf_r_low, pmf_r_high, pmf_pi2, c_h3: dict) -> dict:
    """Holm joint power, gate powers and the power of the licensed word for given distributions of the
    counts: H1a (late fails, n_low), the 0 s arms of both bands (n_low, n_high) and H2 (n_high)."""
    pa, pb = class_probs_pmf(n_low, pmf_q), class_probs_pmf(n_high, pmf_pi2)
    joint = holm_joint(pa, pb, c_h3)
    rest = holm_rest(pb, c_h3)
    t = [threshold(n_low, a) for a in LEVELS]
    n_b = n_low + n_high
    t_b = threshold(n_b, F(1, 100))
    sign = {d: sign_threshold(d, F(1, 100)) for d in range(n_low + 1)}
    tail_x = [tail_of(pmf_r_high, k) for k in range(n_high + 2)]
    holm = mask = chain = F(0)
    for f in range(n_low + 1):
        cf = class_of(f, *t)
        if cf == 0 or rest[cf] == 0 or pmf_q[f] == 0:
            continue
        holm += pmf_q[f] * rest[cf]
        tot_m = tot_c = F(0)
        for r in range(n_low + 1):
            pr = pmf_r_low[r]
            if pr == 0:
                continue
            ok = 0
            for a in range(max(0, f + r - n_low), min(f, r) + 1):
                k = sign[a + n_low - r - f + a]
                if k is not None and a >= k:
                    ok += comb(r, a) * comb(n_low - r, f - a)
            if ok:
                share = pr * F(ok, comb(n_low, f))
                tot_m += share
                need = t_b - r
                if need <= 0:
                    tot_c += share
                elif need <= n_high:
                    tot_c += share * tail_x[need]
        mask += pmf_q[f] * rest[cf] * tot_m
        chain += pmf_q[f] * rest[cf] * tot_c
    p_b = sum((pmf_r_low[r] * (tail_x[max(0, t_b - r)] if t_b - r <= n_high else F(0))
               for r in range(n_low + 1)), F(0))
    s45 = s4_s5_mcnemar()["power_by_predicted_rate"][S4_S5_ASSUMED_RATE]["both_conditions"]
    p_s6 = tail_of(pmf_pi2, threshold(n_high, F(1, 700)))
    word_lo = max(F(0), mask + F(str(s45)) * 2 + p_s6 - 3)
    word_hi = min(mask, F(str(s45)), p_s6)
    return {
        "holm_joint_power": r6(joint),
        "bonferroni_lower_bound_all_at_0.01/3": r6(pa[3] * pb[3] * c_h3[3]),
        "all_at_0.01_upper_bound": r6((1 - pa[0]) * (1 - pb[0]) * (1 - c_h3[0])),
        "classes": {"H1a": {str(k): r6(v) for k, v in pa.items()}, "H2": {str(k): r6(v) for k, v in pb.items()},
                    "H3": {str(k): r6(v) for k, v in c_h3.items()}},
        "headline_R1_fails_late_(Holm)": r6(holm),
        "R1_worse_late_than_0s_(Holm_and_McNemar)": r6(mask),
        "G3_replicado_(Holm_and_McNemar_and_H1b_pooled)": r6(chain),
        "frechet_G3_replicado": [r6(max(F(0), mask + p_b - 1)), r6(min(mask, p_b))],
        "H1b_pooled_alone_0.01": r6(p_b),
        "mascaramento_word": {"S4_S5_power_each_at_rate_" + S4_S5_ASSUMED_RATE: r6(F(str(s45))),
                              "S6_power": r6(p_s6), "frechet_bounds": [r6(word_lo), r6(word_hi)]},
    }


def evidence_posteriors(ev: dict) -> dict:
    """Per-seed (distinct seeds) and per-run Jeffreys posteriors for the three rates, with quantiles."""
    ds = ev["distinct_seed_bounds"]
    rows = {
        "p0_0s_R1_holds": {"per_seed": (ds["p0_all_magnitudes_0s_distinct_seeds"]["x"], ds["p0_all_magnitudes_0s_distinct_seeds"]["n"]),
                           "per_run": (ev["p0_all_magnitudes_0s"]["pooled"]["x"], ev["p0_all_magnitudes_0s"]["pooled"]["n"])},
        "q_late_R1_fails_low_band": {"per_seed": (ds["q_late_fails_low_band_distinct_seeds"]["x"], ds["q_late_fails_low_band_distinct_seeds"]["n"]),
                                     "per_run": (ev["q_late_fails_low_band"]["pooled"]["x"], ev["q_late_fails_low_band"]["pooled"]["n"])},
        "pi2_late_R1_holds_high_band": {"per_seed": (ds["h2_late_holds_high_band_distinct_seeds"]["x"], ds["h2_late_holds_high_band_distinct_seeds"]["n"]),
                                        "per_run": (ev["h2_late_holds_high_band"]["pooled"]["x"], ev["h2_late_holds_high_band"]["pooled"]["n"])},
    }
    out = {}
    for name, d in rows.items():
        out[name] = {}
        for basis, (x, n) in d.items():
            assert x == n, "the quantile routine covers the no-failure case only"
            out[name][basis] = {
                "successes": x, "trials": n, "jeffreys_posterior": f"Beta({x + 0.5}, 0.5)",
                "cp99_lower": r6(cp_lower(x, n)),
                "jeffreys_quantiles": {"1%": round(beta_half_quantile(x, 0.01), 4), "5%": round(beta_half_quantile(x, 0.05), 4),
                                        "25%": round(beta_half_quantile(x, 0.25), 4), "50%": round(beta_half_quantile(x, 0.5), 4)},
            }
    return out


def power_scenarios(n_low: int, n_high: int, ev: dict) -> dict:
    """Power of the proposed design for scenarios grounded in the recorded evidence, not at 100 %."""
    dist, bstar = bs_distribution()
    c_h3 = {s: class_probs_h3(dist, bstar, 60, F(1), s) for s in POSTERIOR_SHIFTS}

    def mix(shifts):
        return {c: sum((c_h3[s][c] for s in shifts), F(0)) / len(shifts) for c in range(4)}

    post = evidence_posteriors(ev)
    out = {"posteriors": post, "assumptions": {
        "H3_shift_grid_m": [float(s) for s in POSTERIOR_SHIFTS],
        "independence": "H1a, H2 and H3 use disjoint seeds; the 0 s arms of the two bands and the posteriors of p0, q and "
                        "pi2 are taken as independent; the two arms of a seed are independent given the rates",
        "labels": "illustrative; the b_s distribution is reconstructed from 20 seeds; no rate is taken as exactly 1"},
        "common_rate_grid": {}, "posterior_averaged": {}, "quantile_scenarios": {}}
    for ps in COMMON_P_GRID:
        pm = pmf_binom
        for s in (F(1, 4), F(3, 4)):
            out["common_rate_grid"][f"p={ps};shift={float(s)}"] = design_power(
                n_low, n_high, pm(n_low, ps), pm(n_low, ps), pm(n_high, ps), pm(n_high, ps), c_h3[s])
    for basis in ("per_seed", "per_run"):
        def bb(n, name):
            x, trials = post[name][basis]["successes"], post[name][basis]["trials"]
            return pmf_beta_binom(n, F(2 * x + 1, 2), F(1, 2))
        for label, h3 in (("shift=0.25", c_h3[F(1, 4)]), ("shift=0.75", c_h3[F(3, 4)]), ("shift_uniform_0_to_0.75", mix(POSTERIOR_SHIFTS))):
            out["posterior_averaged"][f"{basis};{label}"] = design_power(
                n_low, n_high, bb(n_low, "q_late_R1_fails_low_band"), bb(n_low, "p0_0s_R1_holds"),
                bb(n_high, "p0_0s_R1_holds"), bb(n_high, "pi2_late_R1_holds_high_band"), h3)
    for basis in ("per_seed", "per_run"):
        for qlabel in ("5%", "50%", "cp99_lower"):
            def val(name):
                d = post[name][basis]
                return d["cp99_lower"] if qlabel == "cp99_lower" else d["jeffreys_quantiles"][qlabel]
            p0, q, p2 = (F(str(val(n))) for n in ("p0_0s_R1_holds", "q_late_R1_fails_low_band", "pi2_late_R1_holds_high_band"))
            out["quantile_scenarios"][f"{basis};{qlabel};shift=0.25"] = {
                "rates": {"p0": float(p0), "q": float(q), "pi2": float(p2)},
                **design_power(n_low, n_high, pmf_binom(n_low, q), pmf_binom(n_low, p0), pmf_binom(n_high, p0),
                               pmf_binom(n_high, p2), c_h3[F(1, 4)])}
    return out


def b_s_per_seed(levels: list[float], holds: list[bool]) -> tuple[float, str]:
    """b_s of one seed: the smallest level from which R1 holds at that and every higher level.

    Convention for the order statistics (stage B): a seed whose R1 does not hold at the highest level
    gets +infinity (above every finite value, never below b* + tolerance); a seed whose R1 holds at the
    lowest level and at every higher one gets that lowest level and the flag 'at_or_below' (counted at
    or below the lowest level, so below every finite b* - tolerance). Non-monotone seeds keep their
    b_s from this definition and are counted and reported."""
    assert len(levels) == len(holds) and levels == sorted(levels)
    if not holds[-1]:
        return float("inf"), "above_highest"
    k = len(levels) - 1
    while k > 0 and holds[k - 1]:
        k -= 1
    return levels[k], ("at_or_below" if k == 0 else "exact")


MIN_EXPOSED_FIXES = 11  # biased GNSS fixes before contact: the onset fix and ten more, 1.0 s


def first_rejection_times() -> dict:
    """Time from the onset to the first altimeter rejection in the estimator model (no simulator),
    for biases above b*, with the gains of the base case. Used to justify the minimum exposure."""
    case = json.loads(blob(BASE, "exec/cases/m13/g3-registered.json"))
    g = case["controller"]["gains"]
    dt = case["dt_s"] * case["sensors"]["control_period_steps"]
    every = case["sensors"]["gnss_period_cycles"]
    thr, need = g["altimeter_residual_threshold_m"], g["altimeter_rejection_cycles"]
    out = {}
    for bias in (11.99, 12.0, 12.5, 13.5, 15.0, 22.0, 30.0):
        e = v = 0.0
        exceed = 0
        first = None
        onset = 5.0
        for k in range(1, 3000):
            t = k * dt
            b = bias if t >= onset else 0.0
            e += v * dt
            if k % every == 0:
                e += g["gnss_position_gain"] * (b - e)
                v += g["gnss_velocity_gain"] * (0.0 - v)
            r = -e
            if abs(r) > thr:
                exceed += 1
                if exceed >= need and first is None:
                    first = t - onset
            else:
                exceed = 0
                e += g["altimeter_position_gain"] * r
                v += g["altimeter_velocity_gain"] * r / dt
        out[f"{bias}"] = None if first is None else round(first, 2)
    return {"bias_m_to_first_rejection_s_after_onset": out,
            "slowest_s": max(x for x in out.values() if x is not None),
            "minimum_exposure_s": 1.0, "minimum_biased_gnss_fixes": MIN_EXPOSED_FIXES,
            "residual_peak_s_after_onset": 0.3,
            "basis": "model only (scripts/m14_masking_model.py gains, no vehicle, no noise)"}


def sign_min_d(alpha) -> int:
    d = 1
    while F(1, 2**d) >= frac(alpha):
        d += 1
    return d


S4_S5_FLOOR = 10


def s4_s5_mcnemar(n: int = 60) -> dict:
    """Power of the exact one-sided sign test on discordant pairs of S4 or S5 in one condition (0.01/7),
    with a floor of 10 discordant pairs and 1 % pairs in the contrary direction."""
    a = F(1, 700)
    sign = {d: (None if d < S4_S5_FLOOR else sign_threshold(d, a)) for d in range(n + 1)}
    rows = {}
    for pa in ("0.50", "0.70", "0.80", "0.85", "0.90", "0.95", "0.97", "0.99"):
        terms, den = multinomial_terms(n, F(pa), F("0.01"))
        num = sum(x for (p, b, x) in terms if sign[p + b] is not None and p >= sign[p + b])
        one = F(num, den)
        rows[pa] = {"one_condition": r6(one), "both_conditions": r6(one * one)}
    return {"alpha": r6(a), "floor_discordant_pairs": S4_S5_FLOOR,
            "natural_minimum_discordant_pairs_all_predicted": sign_min_d(a),
            "rule": "exact one-sided sign test on the discordant pairs at 0.01/7, at least 10 discordant pairs; "
                    "pairs with R1 not evaluated in either arm count as discordant in the contrary direction",
            "n_pairs": n,
            "opposite_direction_rate_assumed": 0.01, "power_by_predicted_rate": rows,
            "fraction_descriptive_cp99_lower": {"54_of_60": r6(cp_lower(54, 60)), "57_of_60": r6(cp_lower(57, 60)),
                                                "60_of_60": r6(cp_lower(60, 60))}}


def cell_tolerance(n_low: int, n_high: int, high_size: int = 5) -> dict:
    out = {}
    for name, n, size in (("H1a", n_low, 6), ("H2", n_high, high_size)):
        rows = {}
        for label, a in zip(("0.01/3", "0.01/2", "0.01"), LEVELS):
            k = threshold(n, a)
            tol = n - k
            majority = size // 2 + 1
            rows[label] = {"reject_if_at_least": k, "failures_tolerated": tol,
                           "whole_cells_tolerated": tol // size,
                           "majority_contrary_cells_tolerated": tol // majority}
        out[name] = {"n": n, "seeds_per_cell": size, "majority_contrary_means_at_least": size // 2 + 1,
                     "by_level": rows}
    out["not_acting_runs"] = {
        "fraction": float(NOT_ACTING_FRACTION),
        "H1a_max_excluded": int(NOT_ACTING_FRACTION * n_low), "H2_max_excluded": int(NOT_ACTING_FRACTION * n_high),
        "definition": "runs whose verification.json lists the gnss_bias fault with acted = false (no biased GNSS "
                      "fix before the run ended, for instance touchdown before the onset)"}
    return out


GOLDEN = 0x9E3779B97F4A7C15
MASK64 = (1 << 64) - 1
GOLDEN_INV = pow(GOLDEN, -1, 1 << 64)
SOURCES = tuple(range(1, 13))  # crates/vv-rocket/src/prng.rs, `source`
MAX_STEPS = 200_000  # crates/vv-rocket/src/model.rs
CONTROL_PERIOD = 2


def stream_position(seed: int, source: int) -> int:
    """Position of a stream on the single cycle of the SplitMix64 state sequence (state + k * GOLDEN).

    Stream (seed, source) starts at state seed ^ (source * GOLDEN) and its k-th output uses state
    start + k * GOLDEN; position = start * GOLDEN^-1 mod 2^64 makes the k-th output position + k.
    Two streams share an output state (hence an output word, the output map is a bijection) iff their
    position ranges intersect."""
    start = seed ^ ((source * GOLDEN) & MASK64)
    return (start * GOLDEN_INV) & MASK64


def used_draws(cycles: int, fixes: int) -> dict[int, int]:
    """Outputs consumed per stream in one run, from crates/vv-rocket/src/landing_model.rs (sources 1 to 6,
    `centered()` 3, 3, 2 and 1, 1, 1 times; 3 taken as the bound for source 3) and landing_sensors.rs
    (altimeter: one noise, 4 draws, per control cycle; GNSS position and velocity: 3 noises, 12 draws, per
    GNSS fix; IMU attitude, rate and acceleration: 12 draws per control cycle)."""
    return {1: 3, 2: 3, 3: 3, 4: 1, 5: 1, 6: 1, 7: 4 * cycles, 8: 12 * fixes, 9: 12 * fixes,
            10: 12 * cycles, 11: 12 * cycles, 12: 12 * cycles}


def seed_independence(first: int, last: int, cycles: int, fixes: int, used: dict | None = None) -> dict:
    """Overlap of the output ranges [position + 1, position + draws] of every stream of every seed."""
    used = used or used_draws(cycles, fixes)
    uniform = max(used.values())
    pos = sorted((stream_position(s, src), s, src) for s in range(first, last + 1) for src in SOURCES)
    n = len(pos)
    reach = max(used.values())
    used_overlaps = []
    uniform_overlaps = 0
    margin = None
    for i in range(n):
        pi, si, ci = pos[i]
        j = i + 1
        while j < i + n:
            pj, sj, cj = pos[j % n]
            g = (pj - pi) & MASK64
            if g >= reach:
                break
            if g <= uniform - 1:
                uniform_overlaps += 1
            if g <= used[ci] - 1:
                used_overlaps.append([g, [si, ci], [sj, cj]])
            j += 1
        g1 = (pos[(i + 1) % n][0] - pi) & MASK64
        slack = g1 - used[ci]
        margin = slack if margin is None else min(margin, slack)
    return {"seeds": [first, last], "streams": n, "distinct_positions": len({p for p, _, _ in pos}),
            "draws_used_per_source": {str(k): v for k, v in used.items()},
            "pairs_overlapping_if_every_stream_used_the_largest_count": uniform_overlaps,
            "pairs_overlapping_in_the_outputs_actually_used": len(used_overlaps),
            "examples_of_used_overlap": used_overlaps[:3],
            "min_slack_between_next_stream_and_used_range": margin}


EXTRA_PROTECTED = {  # exec/src/seeds.rs GROUND_PROTECTED and the campaign seeds of AGENTS.md
    "100-129 M6 reserved and unguarded M12 loop": (100, 129),
    "201-212 M6 confirmation": (201, 212),
    "7349 M6 final": (7349, 7349), "18265 M6 final": (18265, 18265), "29581 M6 final": (29581, 29581),
    "83017 M6 final": (83017, 83017), "156432 M6 final": (156432, 156432), "241907 M6 final": (241907, 241907),
    "318604 M6 final": (318604, 318604), "407753 M6 final": (407753, 407753), "536218 M6 final": (536218, 536218),
    "672941 M6 final": (672941, 672941), "794306 M6 final": (794306, 794306), "921685 M6 final": (921685, 921685),
    "42 campaign": (42, 42), "1337 campaign": (1337, 1337), "2026 campaign": (2026, 2026),
}


def protocol_seen_ranges() -> dict:
    ranges = dict(SPENT_OR_PROTECTED)
    ranges["2000-2029 M9.1 G3"] = (2000, 2029)
    return ranges


def _seen_index(ranges: dict, used: dict) -> tuple:
    seen = []
    for name, (lo, hi) in ranges.items():
        for sd in range(lo, hi + 1):
            for src in SOURCES:
                seen.append((stream_position(sd, src), used[src], sd, src, name))
    seen.sort()
    span = 1 << 64
    keys = [x[0] - span for x in seen] + [x[0] for x in seen] + [x[0] + span for x in seen]
    return keys, seen * 3, max(used.values())


def _block_vs_index(first: int, last: int, index: tuple, used: dict) -> list:
    import bisect
    keys, meta, reach = index
    found = []
    for sd in range(first, last + 1):
        for src in SOURCES:
            pi, ni = stream_position(sd, src), used[src]
            lo = bisect.bisect_left(keys, pi - reach)
            hi = bisect.bisect_right(keys, pi + reach)
            for idx in range(lo, hi):
                d = keys[idx] - pi
                nj = meta[idx][1]
                if -(nj - 1) <= d <= ni - 1:
                    shared = min(pi + ni, pi + d + nj) - max(pi, pi + d)
                    found.append((sd, src, meta[idx][2], meta[idx][3], meta[idx][4], shared))
    return found


try:  # numpy is used only for the exhaustive partner-seed scan; the scan reports itself skipped without it
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

TEXT_EXT = (".md", ".json", ".rs", ".py", ".toml", ".txt", ".js", ".gd", ".yml", ".html", ".css", ".sh", ".ts", ".cfg")
SCAN_TOP = 1 << 24  # every seed below this bound is scanned


def inventory_scan() -> dict:
    """Over-approximate inventory of the seeds the repository text mentions, from the blobs of BASE.

    Every integer of at most nine digits on a line that contains `seed` or `semente` is a candidate seed;
    ranges are read from `a a b`, `a-b`, `a to b`, `a..b` on such lines and from JSON dictionaries (under a
    key containing `seed`) with first and count, low and high, or start and end. Not found by construction:
    seeds derived in code from other numbers, seeds on lines without the word, binary files, untracked or
    other-branch files."""
    import re
    files = [f for f in git("ls-tree", "-r", "--name-only", BASE).decode().split("\n") if f.endswith(TEXT_EXT)]
    base = full_sha(BASE)
    req = "\n".join(f"{base}:{f}" for f in files).encode() + b"\n"
    raw = subprocess.run(["git", "-C", str(ROOT), "cat-file", "--batch"], input=req, capture_output=True, check=True).stdout
    pos = 0
    contents = {}
    for f in files:
        nl = raw.index(b"\n", pos)
        header = raw[pos:nl].split()
        size = int(header[2])
        contents[f] = raw[nl + 1:nl + 1 + size].decode("utf-8", "ignore")
        pos = nl + 1 + size + 1
    word = re.compile(r"seed|semente", re.I)
    num = re.compile(r"(?<![\w.])(\d{1,9})(?![\w.]*\d)")
    rng = re.compile(r"(?<![\w.])(\d{1,9})\s*(?:a|to|ate|\.\.=?|-)\s*(\d{1,9})(?![\w.]*\d)")
    ints: dict[int, set] = {}
    ranges: dict[tuple, set] = {}
    lines = 0

    def add_range(a, b, f):
        if 0 <= a <= b and b - a <= 10_000_000:
            ranges.setdefault((a, b), set()).add(f)

    def walk(o, f, in_seed=False):
        if isinstance(o, dict):
            keys = {str(k).lower(): v for k, v in o.items()}
            if in_seed or any("seed" in k for k in keys):
                if isinstance(keys.get("first"), int) and isinstance(keys.get("count"), int) and keys["count"] > 0:
                    add_range(keys["first"], keys["first"] + keys["count"] - 1, f)
                if isinstance(keys.get("low"), int) and isinstance(keys.get("high"), int):
                    add_range(keys["low"], keys["high"], f)
                if isinstance(keys.get("start"), int) and isinstance(keys.get("end"), int):
                    add_range(keys["start"], keys["end"], f)
            for k, v in o.items():
                if isinstance(v, int) and not isinstance(v, bool) and "seed" in str(k).lower():
                    ints.setdefault(v, set()).add(f)
                walk(v, f, in_seed or "seed" in str(k).lower())
        elif isinstance(o, list):
            for v in o:
                if in_seed and isinstance(v, int) and not isinstance(v, bool):
                    ints.setdefault(v, set()).add(f)
                walk(v, f, in_seed)

    for f, text in contents.items():
        for ln in text.split("\n"):
            if word.search(ln) and len(ln) < 4000:
                lines += 1
                for mt in num.finditer(ln):
                    ints.setdefault(int(mt.group(1)), set()).add(f)
                for mt in rng.finditer(ln):
                    add_range(int(mt.group(1)), int(mt.group(2)), f)
        if f.endswith(".json"):
            try:
                walk(json.loads(text), f)
            except ValueError:
                pass
    return {"files_scanned": len(files), "seed_lines": lines, "ints": ints, "ranges": ranges}


def _merge(iv: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _target_intervals(targets: dict, used: dict) -> dict[int, list[tuple[int, int]]]:
    """For every partner source: positions p whose used output range meets a target stream's used range."""
    tpos = [(stream_position(sd, src), used[src]) for lo, hi in targets.values() for sd in range(lo, hi + 1) for src in SOURCES]
    out = {}
    for src in SOURCES:
        iv = [(t - used[src] + 1, t + nt - 1) for t, nt in tpos]
        assert all(a >= 0 and b < (1 << 64) for a, b in iv), "interval crosses the end of the cycle"
        out[src] = _merge(iv)
    return out


def partner_mask(seeds, intervals: dict) -> "list[bool]":
    """For each seed: does any of its 12 streams overlap a target stream (used ranges, exact)?"""
    if _np is None:  # pragma: no cover
        import bisect
        res = []
        for sd in seeds:
            hit = False
            for src in SOURCES:
                p = stream_position(int(sd), src)
                iv = intervals[src]
                i = bisect.bisect_right([a for a, _ in iv], p) - 1
                if i >= 0 and p <= iv[i][1]:
                    hit = True
                    break
            res.append(hit)
        return res
    sd = _np.asarray(seeds, dtype=_np.uint64)
    hit = _np.zeros(sd.shape, dtype=bool)
    ginv = _np.uint64(GOLDEN_INV)
    with _np.errstate(over="ignore"):
        for src in SOURCES:
            starts = _np.array([a for a, _ in intervals[src]], dtype=_np.uint64)
            ends = _np.array([b for _, b in intervals[src]], dtype=_np.uint64)
            pos = (sd ^ _np.uint64((src * GOLDEN) & MASK64)) * ginv
            idx = _np.searchsorted(starts, pos, side="right") - 1
            ok = idx >= 0
            hit |= ok & (pos <= ends[_np.clip(idx, 0, len(ends) - 1)])
    return hit


def _compress(seeds: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for s in sorted(seeds):
        if out and s == out[-1][1] + 1:
            out[-1][1] = s
        else:
            out.append([s, s])
    return out


def partner_scan(targets: dict, used: dict, inv: dict, top: int = SCAN_TOP) -> dict:
    """Seeds below `top` (outside the targets) whose streams share used output positions with a target stream."""
    if _np is None:  # pragma: no cover
        return {"skipped": "numpy not available; the exhaustive scan was not run"}
    intervals = _target_intervals(targets, used)
    inside = [(lo, hi) for lo, hi in targets.values()]
    partners: list[int] = []
    chunk = 1 << 20
    for lo in range(0, top, chunk):
        arr = _np.arange(lo, min(top, lo + chunk), dtype=_np.uint64)
        mask = partner_mask(arr, intervals)
        for sd in arr[mask].tolist():
            if not any(a <= sd <= b for a, b in inside):
                partners.append(int(sd))
    comp = _compress(partners)
    flagged_ints = sorted(s for s in inv["ints"] if s < top and any(a <= s <= b for a, b in comp))
    flagged_ranges = sorted([list(r) for r in inv["ranges"]
                             if any(not (r[1] < a or b < r[0]) for a, b in comp)])
    high = sorted(s for s in inv["ints"] if s >= top)
    high_hits = [s for s, h in zip(high, partner_mask(high, intervals)) if h and not any(a <= s <= b for a, b in inside)] if high else []
    return {"scanned_seeds": f"0 to {top - 1}", "partner_seeds": len(partners), "partner_ranges": len(comp),
            "partner_ranges_list": comp, "inventory_integers_in_partner_set": flagged_ints,
            "inventory_ranges_meeting_partner_set": flagged_ranges, "inventory_integers_at_or_above_scan_top": len(high),
            "of_which_partners": high_hits}


def used_overlap_between(a: tuple, b: tuple, cycles: int, fixes: int) -> int:
    """Overlapping stream pairs between two seed blocks (used outputs)."""
    used = used_draws(cycles, fixes)
    return len(_block_vs_index(b[0], b[1], _seen_index({"a": a}, used), used))


def synthetic_overlap_pairs(first: int, last: int, max_gap: int, min_gap: int = 1, limit: int = 3,
                            sources: tuple = SOURCES) -> list:
    """Pairs ((seed, source), (seed', source'), k) of the same XOR relation in a synthetic block, k outputs apart,
    found by position arithmetic only. Used by the tests on non-protected, non-confirmatory seeds."""
    pos = sorted((stream_position(s, src), s, src) for s in range(first, last + 1) for src in sources)
    out = []
    for i in range(len(pos) - 1):
        k = pos[i + 1][0] - pos[i][0]
        if min_gap <= k <= max_gap:
            out.append(((pos[i][1], pos[i][2]), (pos[i + 1][1], pos[i + 1][2]), k))
            if len(out) >= limit:
                break
    return out


def block_verification(inv: dict) -> dict:
    case, code = (2000, 400), (MAX_STEPS // CONTROL_PERIOD, MAX_STEPS // CONTROL_PERIOD // GNSS_PERIOD_CYCLES)
    protocol_ranges = {**protocol_seen_ranges(), **EXTRA_PROTECTED, "44000-44999 earlier block, protected and unused": OLD_BLOCK}
    out = {"block": [BLOCK_FIRST, BLOCK_LAST], "reserve": list(RESERVE),
           "method": "start-state and position arithmetic only (seed ^ source*G, increment G, used draw counts); "
                     "no output word of any stream is generated",
           "declared_ranges_checked": {k: list(v) for k, v in protocol_ranges.items()},
           "declared_seeds_checked": sum(b - a + 1 for a, b in protocol_ranges.values())}
    for label, (cyc, fx) in (("case_40s", case), ("code_limit", code)):
        used = used_draws(cyc, fx)
        idx = _seen_index(protocol_ranges, used)
        out[f"within_block_{label}"] = seed_independence(BLOCK_FIRST, BLOCK_LAST, cyc, fx)
        out[f"within_reserve_{label}"] = seed_independence(RESERVE[0], RESERVE[1], cyc, fx)
        out[f"block_against_declared_ranges_{label}"] = len(_block_vs_index(BLOCK_FIRST, BLOCK_LAST, idx, used))
        out[f"reserve_against_declared_ranges_{label}"] = len(_block_vs_index(RESERVE[0], RESERVE[1], idx, used))
        out[f"reserve_against_block_{label}"] = used_overlap_between((BLOCK_FIRST, BLOCK_LAST), RESERVE, cyc, fx)
    out["same_seed_pairing"] = ("the two or more arms of one seed use the identical streams (same positions): intentional "
                                "pairing inside an experiment; the checks above compare different seeds, and different "
                                "sources of one seed, so they exclude it")
    out["inventory"] = {"files_scanned": inv["files_scanned"], "seed_lines": inv["seed_lines"],
                        "distinct_integers": len(inv["ints"]), "ranges": len(inv["ranges"]),
                        "integers_above_scan_top": sorted(s for s in inv["ints"] if s >= SCAN_TOP)[:50]}
    targets = {"block": (BLOCK_FIRST, BLOCK_LAST), "reserve": RESERVE}
    out["exhaustive_partner_scan_code_limit"] = partner_scan(targets, used_draws(*code), inv)
    out["stress_4000000_draws_per_stream"] = stress_check(inv, protocol_ranges)
    out["not_established"] = [
        "seeds derived in code from other numbers (offsets, hashes, loops) that appear in no text line with the word",
        "seeds in untracked files (for example runs/), in other branches or worktrees, in pull-request text or in notes",
        "binary files",
        "seeds at or above 2^24 that are not integers on a seed line"]
    return out


STRESS_DRAWS = 4_000_000


def min_position_distance(block: tuple, ranges: dict) -> int:
    """Smallest cyclic distance between the position of a block stream and that of a stream of `ranges`."""
    import bisect
    other = sorted(stream_position(sd, src) for lo, hi in ranges.values() for sd in range(lo, hi + 1) for src in SOURCES)
    best = 1 << 64
    for sd in range(block[0], block[1] + 1):
        for src in SOURCES:
            p = stream_position(sd, src)
            i = bisect.bisect_left(other, p)
            for j in (i - 1, i % len(other)):
                d = (p - other[j]) & MASK64
                best = min(best, d, (1 << 64) - d)
    return best


def stress_check(inv: dict, declared: dict) -> dict:
    """Extra check with 4,000,000 draws on every stream (more than any stream of the rocket or the ascent
    simulation can take, see the notes in the protocol), position arithmetic only."""
    used = {src: STRESS_DRAWS for src in SOURCES}
    own = seed_independence(BLOCK_FIRST, BLOCK_LAST, 0, 0, used=used)
    idx = _seen_index(declared, used)
    scan = partner_scan({"block": (BLOCK_FIRST, BLOCK_LAST), "reserve": RESERVE}, used, inv)
    return {"draws_per_stream": STRESS_DRAWS,
            "within_block_overlapping_pairs": own["pairs_overlapping_in_the_outputs_actually_used"],
            "within_block_min_slack": own["min_slack_between_next_stream_and_used_range"],
            "block_against_declared_overlapping_pairs": len(_block_vs_index(BLOCK_FIRST, BLOCK_LAST, idx, used)),
            "block_to_declared_min_position_distance": min_position_distance((BLOCK_FIRST, BLOCK_LAST), declared),
            "partner_seeds_0_to_2^24": scan.get("partner_seeds"),
            "inventory_integers_in_partner_set": scan.get("inventory_integers_in_partner_set"),
            "inventory_ranges_meeting_partner_set": scan.get("inventory_ranges_meeting_partner_set")}


def synthetic_arithmetic_check() -> dict:
    """Validation of the position arithmetic on a synthetic, non-protected block (90000 to 99999); the tests
    generate explicit output words there, never for protected or confirmatory seeds."""
    dispersion = synthetic_overlap_pairs(90000, 99999, max_gap=2, limit=2, sources=(1, 2, 3, 4, 5, 6))
    sensor = synthetic_overlap_pairs(90000, 99999, max_gap=4, limit=2, sources=(7, 8, 9, 10, 11, 12))
    return {"block": [90000, 99999], "dispersion_pairs_found": len(dispersion), "sensor_pairs_found": len(sensor)}


def independence() -> dict:
    inv = inventory_scan()
    return block_verification(inv)


def layout_previous_allocation_a() -> dict:
    """Allocation A (A_high 5 repetitions, E 20 points), superseded; costed on the same block for comparison."""
    cond, summary = seed_map(BLOCK_FIRST, 5, 20)
    n_low, n_high = summary["A_low"]["seeds"], summary["A_high"]["seeds"]
    pairs = summary["D"]["seeds"] + summary["E"]["seeds"]
    t = tests_table(n_low, n_high, 231, 77)
    return {"stages": summary, "checks": seed_checks(cond, summary), "n_high": n_high,
            "tests": {k: t[k] for k in ("H2_late_holds_high_band", "S3_R5_fails_at_0s_high_band", "S6_first_rejection_in_window",
                                        "H1b_pooled_zero_s_both_bands_0.01")},
            "cell_tolerance": cell_tolerance(n_low, n_high, 5),
            "budgets": {"pairs_invariants_and_r2_r6": pairs, "invariants_cp99_upper_at_0": r6(cp_upper(0, pairs))}}


RNG_OPERATIONS_DISCLOSED = [
    {"revision": "1", "operation": "SplitMix64 reference vector (seed 0, public) in a test; Monte Carlo cross-check of the H3 "
                                    "median interval with a generator seeded 20261123 (a sampling seed)", "protected_seeds": False},
    {"revision": "2", "operation": "start-state and stream-position arithmetic for seeds 44000-44919 (and 44000-44999), sources 1 to 12; "
                                    "sorted gaps; no output words", "protected_seeds": True, "output_words": 0},
    {"revision": "2", "operation": "explicit generation of output words for the streams (44000, source 2) and (44128, source 6): "
                                    "8 and 4 words in one interactive check, the first 6 and 2 printed to the console; the test generated "
                                    "the same 6 and 2 words on every run", "protected_seeds": True,
     "words_generated_interactively": 12, "words_printed_interactively": 8, "words_generated_per_test_run": 8,
     "stored_in_files": False, "printed": True},
    {"revision": "3 and 4", "operation": "position arithmetic of the 44000-44919 streams against the seen and protected ranges, "
                                         "against the extended list and inside the seen ranges; no output words", "protected_seeds": True, "output_words": 0},
    {"revision": "4", "operation": "test generating explicit output words for the pairs (44000, 1) and (42016, 3) (3 and 1 words) and "
                                    "(44804, 10) and (41212, 12) (7 and 5 words) on every run; asserted equal, not printed or stored",
     "protected_seeds": True, "words_generated_per_test_run": 16, "stored_in_files": False, "printed": False},
    {"revision": "5 and 6", "operation": "position arithmetic only for 81000-81999, the reserve 80904-80983, the rejected reserve candidates "
                                          "(80920-80999, 80912-80991 and 81920-81999) and the candidate blocks scanned from 60000; no output word "
                                          "of those seeds; tests generate words only on the synthetic block 90000-99999",
     "protected_seeds": False, "output_words": 0},
]


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
    ev = evidence()
    return {
        "schema": "vv-m19-g3-candidate-calculations.v2",
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
        "layout_previous_allocation_A": layout_previous_allocation_a(),
        "evidence": ev,
        "tests": tests_table(n_low, n_high, n_d_low, n_d_pair),
        "s4_s5": s4_s5(),
        "exposure_rule": first_rejection_times(),
        "h1_options": h1_options(n_low),
        "h1_options_pooled_A_and_D_n399": h1_options(3 * 7 * 11 + n_low, with_mcnemar=False),
        "median_tests": median_tests(),
        "budgets": budgets(n_d + n_e, n_d),
        "power_scenarios": power_scenarios(n_low, n_high, ev),
        "s4_s5_mcnemar": s4_s5_mcnemar(),
        "cell_tolerance": cell_tolerance(n_low, n_high, 6),
        "seed_independence": independence(),
        "synthetic_arithmetic_check": synthetic_arithmetic_check(),
        "rng_operations_disclosed": RNG_OPERATIONS_DISCLOSED,
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
