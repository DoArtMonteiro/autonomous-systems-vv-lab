"""Paired statistics and pre-registered verdicts for `vv-repair` evidence.

A pair is (suite, workload, simulation seed): the baseline and the candidate ran
the same fault atoms on the same seed. Pairing holds at the level of the
exogenous calendar (GPS, communication and actuator draws), not of the
trajectory, which depends on the controller.

Verdict gates come from `experiment.acceptance` in the evidence, written before
the run. They are applied to the held-out seeds (plus the shared no-fault control):

* `safety`: pooled risk difference of "any violation" has its upper confidence
  bound below zero, counting vacuous fixes (the candidate leaves an obligation
  pending or never moves where the baseline moved) as unchanged.
* `no_suite_regression`: no suite has its lower bound above zero.
* `no_new_class`: the candidate shows no failure class the baseline never showed.
* `completion`: pairs where the baseline completes and the candidate does not stay
  within `max_completion_loss_permille` of the baseline completions.
* `distance`: the upper bound of the mean paired increase in distance remaining
  stays within `max_mean_distance_increase_mm`.
* `corpus`: at least one known counterexample is `resolved` (not `inconclusive`,
  `untriggered` or `shifted`).
* `power`: every suite has at least `min_heldout_pairs` held-out pairs.

`verdict` reports the safety and progress axes separately; the decision is
`accept` only when safety is `improved`, progress passes, power holds and the
candidate does not change the oracle (confidence or age limits): a fix that
only holds still, or that moves the trigger the contracts use, is not a repair.

Per-pair class gains (`pairs_with_new_class`) and per-class frequency changes are
reported, not gated: `no_new_class` is suite-level.

Pairs on two simulation seeds share a workload, so they are not independent; the
intervals treat them as independent and are therefore somewhat narrow.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterator

ANALYSIS_SCHEMA = "vv-repair.analysis.v1"
Z = {10: 2.5758293035489, 50: 1.959963984540054, 100: 1.6448536269514722}
SPLITS = ("all", "tuning", "heldout")

Pair = tuple[dict, dict]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def wilson(successes: int, total: int, z: float) -> dict[str, float | None]:
    if total == 0:
        return {"rate": None, "low": None, "high": None}
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"rate": _round(p), "low": _round(max(0.0, centre - half)), "high": _round(min(1.0, centre + half))}


def mcnemar_exact(fixed: int, broken: int) -> float:
    """Two-sided exact binomial test on the discordant pairs."""
    n = fixed + broken
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(fixed, broken) + 1))
    return min(1.0, 2 * tail / 2**n)


def paired_risk_difference(fixed: int, broken: int, n: int, z: float) -> dict[str, float | None]:
    """Candidate minus baseline violation rate; negative is better (Wald interval)."""
    if n == 0:
        return {"estimate": None, "low": None, "high": None}
    difference = (broken - fixed) / n
    variance = ((fixed + broken) - (broken - fixed) ** 2 / n) / (n * n)
    half = z * math.sqrt(max(variance, 0.0))
    return {"estimate": _round(difference), "low": _round(difference - half), "high": _round(difference + half)}


def mean_ci(values: list[float], z: float) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "low": None, "high": None, "n": 0}
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return {"mean": _round(mean), "low": None, "high": None, "n": 1}
    variance = sum((value - mean) ** 2 for value in values) / (n - 1)
    half = z * math.sqrt(variance / n)
    return {"mean": _round(mean), "low": _round(mean - half), "high": _round(mean + half), "n": n}


def distance(row: dict[str, Any]) -> int:
    """Distance to the next waypoint; zero once every waypoint is done."""
    value = row.get("distance_remaining_mm")
    return 0 if value is None else int(value)


def _done(row: dict) -> bool:
    return row["mission"] == "completed"


def compare(pairs: list[Pair], z: float) -> dict[str, Any]:
    """Paired comparison of baseline and candidate rows."""
    n = len(pairs)
    base_viol = sum(1 for base, _ in pairs if base["violations"])
    cand_viol = sum(1 for _, cand in pairs if cand["violations"])
    fixed_pairs = [(b, c) for b, c in pairs if b["violations"] and not c["violations"]]
    fixed = len(fixed_pairs)
    broken = sum(1 for base, cand in pairs if cand["violations"] and not base["violations"])
    # A fix is vacuous when the candidate only stops moving or leaves an obligation pending.
    vacuous = sum(
        1
        for b, c in fixed_pairs
        if len(c["inconclusive"]) > len(b["inconclusive"]) or (c["movement_ticks"] == 0 < b["movement_ticks"])
    )
    both_done = [
        cand["completion_tick"] - base["completion_tick"]
        for base, cand in pairs
        if base["completion_tick"] is not None and cand["completion_tick"] is not None
    ]

    def delta(field: str) -> dict[str, float | None]:
        return mean_ci([cand[field] - base[field] for base, cand in pairs], z)

    lost = [(b, c) for b, c in pairs if _done(b) and not _done(c)]
    lost_outcomes: dict[str, int] = {}
    for _, cand in lost:
        lost_outcomes[cand["mission"]] = lost_outcomes.get(cand["mission"], 0) + 1

    return {
        "pairs": n,
        "baseline_violation": wilson(base_viol, n, z) | {"count": base_viol},
        "candidate_violation": wilson(cand_viol, n, z) | {"count": cand_viol},
        "fixed": fixed,
        "broken": broken,
        "unchanged": n - fixed - broken,
        "mcnemar_p": _round(mcnemar_exact(fixed, broken)),
        "risk_difference": paired_risk_difference(fixed, broken, n, z),
        "fixed_vacuous": vacuous,
        "risk_difference_strict": paired_risk_difference(fixed - vacuous, broken, n, z),
        "pairs_with_new_class": sum(1 for b, c in pairs if set(c["violations"]) - set(b["violations"])),
        "pairs_with_removed_class": sum(1 for b, c in pairs if set(b["violations"]) - set(c["violations"])),
        "pairs_more_inconclusive": sum(1 for b, c in pairs if len(c["inconclusive"]) > len(b["inconclusive"])),
        "baseline_completed": sum(1 for base, _ in pairs if _done(base)),
        "candidate_completed": sum(1 for _, cand in pairs if _done(cand)),
        "completion_lost": len(lost),
        "completion_lost_outcomes": dict(sorted(lost_outcomes.items())),
        "completion_lost_fallback_delta": mean_ci([c["fallback_ticks"] - b["fallback_ticks"] for b, c in lost], z),
        "completion_gained": sum(1 for b, c in pairs if _done(c) and not _done(b)),
        "distance_increase_mm": mean_ci([distance(c) - distance(b) for b, c in pairs], z),
        "completion_tick_delta": mean_ci(both_done, z),
        "fallback_ticks_delta": delta("fallback_ticks"),
        "movement_ticks_delta": delta("movement_ticks"),
        "actuator_fault_events_delta": delta("actuator_fault_events"),
    }


def class_rates(pairs: list[Pair]) -> dict[str, dict[str, int]]:
    """Per failure class: pairs violated under the baseline and under the candidate."""
    rates: dict[str, dict[str, int]] = {}
    for base, cand in pairs:
        for side, row in (("baseline", base), ("candidate", cand)):
            for label in row["violations"]:
                rates.setdefault(label, {"baseline": 0, "candidate": 0})[side] += 1
    return dict(sorted(rates.items()))


def paired(evidence: dict, suite: str, candidate: str) -> Iterator[tuple[dict, dict, dict]]:
    """(workload, baseline row, candidate row) for every simulation seed."""
    results = evidence["results"][suite]
    workloads = evidence["workloads"][suite]
    for seed, base_rows in results[evidence["experiment"]["baseline"]["id"]].items():
        cand_rows = results[candidate][seed]
        if len(base_rows) != len(workloads) or len(cand_rows) != len(workloads):
            raise ValueError(f"{suite}/{candidate}/{seed}: rows do not match workloads")
        yield from zip(workloads, base_rows, cand_rows)


def in_split(split: str) -> Callable[[dict], bool]:
    """The no-fault control belongs to every split."""
    if split == "all":
        return lambda workload: True
    return lambda workload: workload["split"] in (split, "control")


def verdict(
    gates: dict[str, bool], heldout: dict[str, Any], tuning: dict[str, Any], changes_oracle: bool = False
) -> dict[str, Any]:
    """Two axes: safety (violations and classes) and progress (completion and distance).

    A candidate is accepted only when safety is `improved`, progress passes, the
    held-out sample is large enough and the candidate leaves the oracle unchanged.
    The axes are reported separately so that a real safety gain with an
    availability cost stays visible.
    """
    notes = []
    tune, held = tuning["risk_difference"], heldout["risk_difference"]
    if tune["high"] is not None and tune["high"] < 0 and not (held["high"] is not None and held["high"] < 0):
        notes.append("overfit: the improvement on tuning seeds does not hold on held-out seeds")
    if not gates["no_suite_regression"] or (held["low"] is not None and held["low"] > 0):
        safety = "regressed"
    elif gates["safety"] and gates["no_new_class"] and gates["corpus"]:
        safety = "improved"
    elif gates["safety"]:
        safety = "mixed"
    else:
        safety = "no_effect"
    progress = "pass" if gates["completion"] and gates["distance"] else "fail"
    accepted = safety == "improved" and progress == "pass" and gates["power"] and not changes_oracle
    return {"decision": "accept" if accepted else "reject", "safety": safety, "progress": progress, "notes": notes}


def suite_block(evidence: dict, suite: str, candidate: str, z: float) -> tuple[dict[str, Any], dict[str, list[Pair]]]:
    """Comparisons for one suite, and its pairs per split for pooling."""
    rows = list(paired(evidence, suite, candidate))
    block: dict[str, Any] = {}
    pairs_by_split: dict[str, list[Pair]] = {}
    for split in SPLITS:
        keep = in_split(split)
        pairs_by_split[split] = [(b, c) for w, b, c in rows if keep(w)]
        block[split] = compare(pairs_by_split[split], z)
    heldout = [(w, b, c) for w, b, c in rows if w["split"] == "heldout"]
    families = sorted({w["family"] for w, _, _ in heldout})
    block["families"] = {
        family: compare([(b, c) for w, b, c in heldout if w["family"] == family], z) for family in families
    }
    block["classes"] = class_rates([(b, c) for _, b, c in heldout])
    block["introduced"] = [
        item["id"] for item in evidence["introduced"] if item["suite"] == suite and item["found_on"] == candidate
    ]
    block["corpus"] = {item["id"]: item["replay"][candidate]["status"] for item in evidence["corpus"] if item["suite"] == suite}
    return block, pairs_by_split


def gates(acceptance: dict, held: dict[str, Any], per_suite: dict[str, Any], statuses: list[str]) -> dict[str, bool]:
    distance_high = held["distance_increase_mm"]["high"]
    strict_high = held["risk_difference_strict"]["high"]
    return {
        # Vacuous fixes count as unchanged: holding still is not a repair.
        "safety": strict_high is not None and strict_high < 0,
        "no_suite_regression": all((block["heldout"]["risk_difference"]["low"] or 0) <= 0 for block in per_suite.values()),
        "no_new_class": not any(block["introduced"] for block in per_suite.values()),
        "completion": held["completion_lost"] * 1000 <= acceptance["max_completion_loss_permille"] * held["baseline_completed"],
        "distance": distance_high is None or distance_high <= acceptance["max_mean_distance_increase_mm"],
        "corpus": "resolved" in statuses,
        "power": all(block["heldout"]["pairs"] >= acceptance["min_heldout_pairs"] for block in per_suite.values()),
    }


def notes(config: dict, baseline: dict, per_suite: dict[str, Any]) -> list[str]:
    """Context a reader needs to interpret the verdict of one candidate."""
    out = []
    for suite, block in per_suite.items():
        rd = block["heldout"]["risk_difference"]
        if rd["low"] is not None and rd["low"] > 0:
            p = block["heldout"]["mcnemar_p"]
            note = (
                f"fails no_suite_regression on {suite}: lower bound {100 * rd['low']:+.3f} pp, "
                f"{block['heldout']['fixed']} fixed / {block['heldout']['broken']} broken, exact p {'<1e-6' if p < 1e-6 else f'{p:.3g}'}"
            )
            if p >= 0.05:
                note += "; the registered Wald bound and the exact test disagree, so this regression is weak evidence"
            out.append(note)
        if config["policy"] == baseline["policy"] and config["effective"].get(suite) == baseline["effective"].get(suite):
            out.append(f"identical to the baseline on {suite}: its pairs are unchanged by construction")
    if config["changes_oracle"]:
        out.append("changes the oracle: the confidence limit also defines the localization_unreliable trigger")
    return out


def analyze_candidate(evidence: dict, candidate: str, z: float) -> dict[str, Any]:
    experiment = evidence["experiment"]
    configs = {c["id"]: c for c in evidence["configs"]}
    config, baseline = configs[candidate], configs[experiment["baseline"]["id"]]
    per_suite: dict[str, Any] = {}
    pooled: dict[str, list[Pair]] = {split: [] for split in SPLITS}
    for suite in [s["id"] for s in experiment["suites"]]:
        per_suite[suite], pairs_by_split = suite_block(evidence, suite, candidate, z)
        for split, pairs in pairs_by_split.items():
            pooled[split].extend(pairs)
    summary = {split: compare(pooled[split], z) for split in SPLITS}
    statuses = [status for block in per_suite.values() for status in block["corpus"].values()]
    gate = gates(experiment["acceptance"], summary["heldout"], per_suite, statuses)
    outcome = verdict(gate, summary["heldout"], summary["tuning"], config["changes_oracle"])
    outcome["notes"].extend(notes(config, baseline, per_suite))
    return {
        "id": candidate,
        "policy": config["policy"],
        "overrides": config["overrides"],
        "rationale": config["rationale"],
        "config_sha256": config["config_sha256"],
        "changes_oracle": config["changes_oracle"],
        "role": config["role"],
        "expect": config["expect"],
        "as_predicted": all(outcome[axis] == value for axis, value in config["expect"].items()),
        "verdict": outcome,
        "gates": gate,
        "corpus_status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
        "summary": summary,
        "suites": per_suite,
    }


def analyze(evidence: dict) -> dict[str, Any]:
    experiment = evidence["experiment"]
    z = Z[experiment["acceptance"]["alpha_permille"]]
    return {
        "schema": ANALYSIS_SCHEMA,
        "evidence_sha256": evidence["evidence_sha256"],
        "source_sha256": evidence["source_sha256"],
        "baseline": experiment["baseline"]["id"],
        "acceptance": experiment["acceptance"],
        "z": _round(z),
        "candidates": [analyze_candidate(evidence, c["id"], z) for c in experiment["candidates"]],
    }
