"""Tests of the M19 G3 power calculations and of the corrected candidate that cites them.

No simulator is run and no simulator seed is used. The checks read committed blobs, recorded evidence
and the output of `scripts/m19_g3_power.py`, which is exact arithmetic plus start-state and position
arithmetic of the PRNG. No test here generates output words of a protected or confirmatory seed: the
position arithmetic is validated on synthetic seeds 90000 to 99999 only.
"""

import hashlib
import re
import subprocess
import sys
import unittest
from fractions import Fraction as F
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import m19_g3_power as m  # noqa: E402

DOC = ROOT / "docs" / "m19-g3-onset-protocol-candidate.md"
CALC = ROOT / "docs" / "evidence" / "m19" / "g3-candidate" / "calculations.json"
SCRIPT = ROOT / "scripts" / "m19_g3_power.py"
EM_DASH = "\u2014"
LABEL = (
    "**CORRECTED CANDIDATE " + EM_DASH + " NOT HUMAN-REVIEWED " + EM_DASH
    + " NOT APPROVED FOR EXECUTION**"
)

_BUILT = None


def built() -> dict:
    global _BUILT
    if _BUILT is None:
        _BUILT = m.build()
    return _BUILT


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def pt(x: float, digits: int) -> str:
    """Portuguese decimal comma, fixed digits."""
    return f"{x:.{digits}f}".replace(".", ",")


def words(seed: int, source: int, n: int) -> list:
    """Explicit output words. Only ever called with synthetic seeds."""
    g = m.SplitMix64(seed ^ ((source * m.GOLDEN) & m.MASK64))
    return [g.next() for _ in range(n)]


class ExactBinomials(unittest.TestCase):
    def test_reproduces_the_m15_thresholds_and_powers(self):
        a3, a7, a2 = F(1, 300), F(1, 700), F(1, 200)
        self.assertEqual(m.threshold(160, a3), 154)
        self.assertEqual(m.threshold(160, a7), 155)
        self.assertEqual(m.threshold(240, a2), 228)
        self.assertEqual(m.threshold(80, a2), 79)
        self.assertEqual(m.threshold(80, a7), 80)
        self.assertEqual(round(float(m.power(160, F("0.95"), a3)), 4), 0.3071)
        self.assertEqual(round(float(m.power(160, F("0.97"), a3)), 4), 0.7934)
        self.assertEqual(round(float(m.power(160, F("0.99"), a3)), 4), 0.9988)
        self.assertEqual(round(float(m.power(160, F("0.93"), a3)), 3), 0.064)

    def test_size_never_exceeds_alpha_and_threshold_is_minimal(self):
        for n, a in ((60, F(1, 300)), (77, F(1, 700)), (168, F(1, 300)), (231, F(1, 200))):
            k = m.threshold(n, a)
            if k is None:
                self.assertGreater(F(9, 10) ** n, a)
                continue
            self.assertLessEqual(m.sf(k, n, F(9, 10)), a)
            if k > 0:
                self.assertGreater(m.sf(k - 1, n, F(9, 10)), a)

    def test_63_and_69(self):
        self.assertEqual(m.min_n_all_success(F(1, 700)), 63)
        self.assertEqual(m.min_n_all_success(F(1, 1400)), 69)
        self.assertEqual(m.min_n_all_success(F(1, 300)), 55)
        self.assertEqual(m.min_n_all_success(F(1, 200)), 51)
        self.assertEqual(m.min_n_all_success(F(1, 100)), 44)
        self.assertIsNone(m.threshold(60, F(1, 700)))
        self.assertIsNone(m.threshold(62, F(1, 700)))
        self.assertEqual(m.threshold(63, F(1, 700)), 63)
        self.assertIsNone(m.threshold(68, F(1, 1400)))
        self.assertEqual(m.threshold(69, F(1, 1400)), 69)
        t = built()["alpha_and_minimum_n"]
        self.assertEqual(t["mcnemar_min_discordant_all_predicted"], {"0.01/14": 11, "0.01/7": 10})
        self.assertTrue(all(r["alpha_inside_interval"] for r in t["binomial_all_success"].values()))

    def test_fraction_rule_is_stronger_than_mcnemar(self):
        s = built()["s4_s5"]
        self.assertTrue(s["mcnemar_p_is_always_below_alpha_when_fraction_rule_passes"])
        self.assertAlmostEqual(s["rule_54_of_60_acceptance_probability"]["0.9"], 0.606451, places=6)

    def test_order_statistic_positions(self):
        self.assertEqual(m.os_positions(60, F(1, 300)), (20, 41))
        self.assertEqual(m.os_positions(60, F(1, 700)), (19, 42))

    def test_clopper_pearson_and_budgets(self):
        self.assertAlmostEqual(m.cp_upper(0, 480), 0.009548, places=5)
        self.assertAlmostEqual(m.cp_upper(13, 480), 0.04971, places=4)
        b = built()["budgets"]
        self.assertEqual(b["min_pairs_for_zero_events_within_1pct"], 459)
        self.assertEqual(b["pairs_invariants_and_r2_r6"], 460)
        self.assertEqual(b["invariants_1pct"]["max_events"], 0)
        self.assertEqual(b["r2_r6_5pct"]["max_events"], 12)
        self.assertEqual(b["r1_at_0s_2.5pct"]["max_events"], 1)

    def test_median_interval_reproduces_the_review_values(self):
        h3 = built()["median_tests"]["H3_tol_1.0"]
        self.assertEqual(h3["0.00"]["confirm"], 1.0)
        self.assertAlmostEqual(h3["0.75"]["confirm"], 0.6692, places=3)
        mc = built()["median_tests"]["monte_carlo_crosscheck_H3"]["shift_0.75"]
        self.assertLess(abs(mc["estimate"] - h3["0.75"]["confirm"]), 4 * mc["std_error"])


class SplitMix(unittest.TestCase):
    def test_reference_vector(self):
        g = m.SplitMix64(0)  # public reference values for state 0
        self.assertEqual(g.next(), 0xE220A8397B1DCDAF)
        self.assertEqual(g.next(), 0x6E789E6AA1B965F4)


class OnsetGeometry(unittest.TestCase):
    def test_late_onsets_in_a_gnss_interval_are_one_condition(self):
        g = m.groups_for([0.0, 0.01, 0.02, 0.05, 0.1, 0.11, 1.0])
        self.assertEqual(g[1], g[2])
        self.assertEqual(g[1], g[3])
        self.assertEqual(g[1], g[4])
        self.assertNotEqual(g[0], g[1])
        self.assertNotEqual(g[4], g[5])
        self.assertNotEqual(g[4], g[6])

    def test_corrected_onsets_are_distinct_fixes_and_m15_had_a_duplicate(self):
        every = m.CONTROL_PERIOD_STEPS * m.GNSS_PERIOD_CYCLES
        starts = [round(t / m.DT_S) for t in m.ONSETS]
        self.assertTrue(all(s % every == 0 for s in starts))
        self.assertEqual(len(set(starts)), len(m.ONSETS))
        self.assertEqual(len(set(m.groups_for(m.ONSETS_M15))), 7)
        self.assertEqual(built()["onset_geometry"]["m15_onsets_sharing_a_sensor_history"], [[0.01, 0.1]])


class SeedMaps(unittest.TestCase):
    def test_every_seed_has_one_condition_inside_the_block(self):
        cond, summary = m.seed_map()
        checks = m.seed_checks(cond, summary)
        self.assertTrue(checks["each_seed_one_condition"])
        self.assertTrue(checks["all_within_block"])
        self.assertTrue(checks["no_seed_in_reserve"])
        self.assertTrue(checks["no_seed_in_44000_44999"])
        self.assertTrue(checks["stage_ranges_disjoint"])
        self.assertTrue(all(v == 0 for v in checks["overlap_with_spent_or_protected"].values()))
        self.assertEqual((checks["seeds_used"], checks["total_runs"]), (916, 5736))
        self.assertEqual((checks["first_seed"], checks["last_seed"]), (81000, 81915))
        self.assertEqual((checks["unassigned_first"], checks["unassigned_last"]), (81916, 81919))
        self.assertEqual(checks["reserve"], [80904, 80983])
        self.assertTrue(all(81000 <= s <= 81919 for s in cond))

    def test_cells_are_balanced(self):
        _, summary = m.seed_map()
        for stage, per in (("A_low", 6), ("A_high", 6), ("D", 11)):
            self.assertEqual(summary[stage]["distinct_conditions"], 28)
            self.assertEqual((summary[stage]["seeds_per_condition_min"], summary[stage]["seeds_per_condition_max"]), (per, per))
        self.assertEqual(summary["E"]["distinct_conditions"], 152)

    def test_previous_allocation_a_is_costed_on_the_same_block(self):
        a = built()["layout_previous_allocation_A"]
        self.assertEqual((a["checks"]["seeds_used"], a["checks"]["unassigned_seeds"]), (896, 24))
        self.assertEqual(a["tests"]["H2_late_holds_high_band"]["reject_if_successes_at_least"], 136)

    def test_the_m15_layout_totals(self):
        t = m.m15_layout_totals()
        self.assertEqual((t["seeds"], t["runs"]), (920, 5800))

    def test_script_sampling_seed_is_not_in_a_protected_or_proposed_range(self):
        for lo, hi in ((44000, 44999), (50000, 59999), (80904, 81999), (3000, 3099), (6000, 6099)):
            self.assertFalse(lo <= m.MC_SEED <= hi)


class Provenance(unittest.TestCase):
    def test_source_hash_and_what_changed(self):
        sim = built()["provenance"]["simulator"]
        self.assertEqual(sim["source_sha256_base"][:8], "295a45b2")
        self.assertEqual(sim["source_sha256_m13_commit"][:8], "12b276cb")
        self.assertEqual(sim["files_differing_m13_to_base"], ["src/landing_model.rs"])
        self.assertEqual(sim["files_differing_reference_to_base"], [])

    def test_m15_protocol_and_review_package_are_untouched(self):
        self.assertTrue(built()["provenance"]["m15_protocol_identical_to_review_reference"])
        r = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", m.BASE, "--",
             "docs/m15-g3-onset-protocol.md", "docs/review/g3-onset"],
        )
        self.assertEqual(r.returncode, 0, "the M15 candidate or the review package changed")


class OutputFile(unittest.TestCase):
    def test_json_matches_the_committed_file_and_is_ascii_lf(self):
        data = m.render(built())
        self.assertNotIn(b"\r", data)
        self.assertNotIn(EM_DASH.encode("utf-8"), data)
        text = data.decode("ascii")
        self.assertNotIn(str(ROOT).replace("\\", "/"), text)
        self.assertEqual(CALC.read_bytes(), data, "regenerate with scripts/m19_g3_power.py --output")

    def test_json_stores_no_output_words(self):
        text = CALC.read_text(encoding="ascii")
        self.assertIsNone(re.search(r"0x[0-9a-fA-F]{8,}", text))
        for tok in re.findall(r"(?<![0-9a-f])(?=[0-9a-f]*[a-f])[0-9a-f]{16,39}(?![0-9a-f])", text):
            self.fail(f"hexadecimal token that could be an output word: {tok}")

    def test_script_has_no_forbidden_dash(self):
        self.assertNotIn(EM_DASH, SCRIPT.read_text(encoding="utf-8"))

    def test_no_test_generates_words_for_protected_or_proposed_seeds(self):
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn(EM_DASH, src)
        for call in re.findall(r"SplitMix64\(([^)]*)\)", src):
            self.assertIsNone(re.search(r"\b(44\d{3}|81\d{3}|809\d{2}|[3-6]\d{3}|5\d{4})\b", call), call)
        for call in re.findall(r"words\(([^)]*)\)", src):
            self.assertIsNone(re.search(r"\b(44\d{3}|81\d{3}|809\d{2}|5\d{4})\b", call), call)


class HolmAndGates(unittest.TestCase):
    def test_holm_rule(self):
        self.assertTrue(m.holm_ok((3, 3, 3)))
        self.assertTrue(m.holm_ok((3, 2, 1)))
        self.assertFalse(m.holm_ok((2, 2, 2)))
        self.assertFalse(m.holm_ok((3, 1, 1)))
        self.assertFalse(m.holm_ok((3, 3, 0)))

    def test_class_based_holm_matches_direct_p_values(self):
        sizes, pis = (60, 66, 72), (F("0.99"), F("0.985"), F("0.995"))
        classes = [m.class_probs_pmf(n, m.pmf_binom(n, p)) for n, p in zip(sizes, pis)]
        fast = m.holm_joint(*classes)
        pmfs = [m.pmf_binom(n, p) for n, p in zip(sizes, pis)]
        tails = [[m.sf(k, n, F(9, 10)) for k in range(n + 1)] for n in sizes]
        direct = F(0)
        for a in range(sizes[0] + 1):
            for b in range(sizes[1] + 1):
                for c in range(sizes[2] + 1):
                    ps = sorted((tails[0][a], tails[1][b], tails[2][c]))
                    if ps[0] <= F(1, 300) and ps[1] <= F(1, 200) and ps[2] <= F(1, 100):
                        direct += pmfs[0][a] * pmfs[1][b] * pmfs[2][c]
        self.assertEqual(fast, direct)

    def test_cells_and_non_acting_rule(self):
        c = built()["cell_tolerance"]
        for h in ("H1a", "H2"):
            self.assertEqual(c[h]["by_level"]["0.01/3"]["whole_cells_tolerated"], 1)
            self.assertEqual(c[h]["by_level"]["0.01/3"]["majority_contrary_cells_tolerated"], 1)
        self.assertEqual((c["not_acting_runs"]["H1a_max_excluded"], c["not_acting_runs"]["H2_max_excluded"]), (8, 8))

    def test_s4_s5_direction_test(self):
        s = built()["s4_s5_mcnemar"]
        self.assertEqual(s["floor_discordant_pairs"], 10)
        self.assertGreaterEqual(s["power_by_predicted_rate"]["0.50"]["both_conditions"], 0.9999)
        self.assertAlmostEqual(s["fraction_descriptive_cp99_lower"]["54_of_60"], 0.774088, places=5)

    def test_b_s_convention(self):
        lv = [10.0, 10.25, 10.5, 10.75]
        self.assertEqual(m.b_s_per_seed(lv, [False, False, True, True]), (10.5, "exact"))
        self.assertEqual(m.b_s_per_seed(lv, [True, True, True, True]), (10.0, "at_or_below"))
        self.assertEqual(m.b_s_per_seed(lv, [True, True, True, False]), (float("inf"), "above_highest"))
        self.assertEqual(m.b_s_per_seed(lv, [True, False, True, True]), (10.5, "exact"))

    def test_exposure_rule_is_above_the_model_transient(self):
        e = built()["exposure_rule"]
        self.assertEqual(e["minimum_biased_gnss_fixes"], 11)
        self.assertLess(e["slowest_s"], e["minimum_exposure_s"])
        self.assertAlmostEqual(e["slowest_s"], 0.58)

    def test_hoeffding_condition_for_every_computed_confirmatory_threshold(self):
        d = built()
        checked = 0
        for name, t in d["tests"].items():
            if name.startswith("M15_") or name.startswith("H2_if") or "A_and_D" in name:
                continue
            self.assertGreater(t["reject_if_successes_at_least"], t["n"] * 0.9 + 1, name)
            checked += 1
        self.assertGreaterEqual(checked, 8)
        self.assertEqual(d["tests"]["S7_each_proportion"]["reject_if_successes_at_least"], 77)
        self.assertEqual(d["tests"]["H1b_pooled_zero_s_both_bands_0.01"]["reject_if_successes_at_least"], 316)
        self.assertEqual(d["tests"]["S3_R5_fails_at_0s_high_band"]["reject_if_successes_at_least"], 163)


class UncertaintyGroundedPower(unittest.TestCase):
    def test_beta_binomial_is_exact(self):
        pmf = m.pmf_beta_binom(10, F(1, 2), F(1, 2))
        self.assertEqual(sum(pmf), 1)
        uniform = m.pmf_beta_binom(10, 1, 1)
        self.assertEqual(uniform, [F(1, 11)] * 11)
        # the posterior average of the binomial power equals the beta-binomial tail
        n, k = 20, 18
        self.assertEqual(m.tail_of(m.pmf_beta_binom(n, 3, 2), k), sum(m.pmf_beta_binom(n, 3, 2)[k:], F(0)))

    def test_jeffreys_quantiles(self):
        q = {x: m.beta_half_quantile(84, x) for x in (0.01, 0.05, 0.5)}
        self.assertLess(q[0.01], q[0.05])
        self.assertLess(q[0.05], q[0.5])
        self.assertGreater(q[0.01], m.cp_lower(84, 84))  # Jeffreys is less conservative than Clopper-Pearson
        self.assertAlmostEqual(q[0.5], 0.9973, places=3)

    def test_no_scenario_takes_a_rate_of_one(self):
        ps = built()["power_scenarios"]
        for v in ps["quantile_scenarios"].values():
            self.assertTrue(all(r < 1 for r in v["rates"].values()))
        self.assertLess(max(float(k.split(";")[0][2:]) for k in ps["common_rate_grid"]), 1.0)
        self.assertEqual(sorted(ps), ["assumptions", "common_rate_grid", "posterior_averaged", "posteriors", "quantile_scenarios"])

    def test_power_is_small_where_the_evidence_cannot_exclude(self):
        ps = built()["power_scenarios"]
        self.assertLess(ps["quantile_scenarios"]["per_seed;cp99_lower;shift=0.25"]["holm_joint_power"], 0.01)
        grid = ps["common_rate_grid"]
        self.assertLess(grid["p=0.93;shift=0.25"]["holm_joint_power"], 0.05)
        self.assertGreater(grid["p=0.99;shift=0.25"]["holm_joint_power"], 0.99)
        self.assertAlmostEqual(grid["p=0.99;shift=0.25"]["holm_joint_power"], 0.999354, places=6)
        mono = [grid[f"p={p};shift=0.25"]["holm_joint_power"] for p in m.COMMON_P_GRID]
        self.assertEqual(mono, sorted(mono))

    def test_posterior_averaged_power_is_between_the_low_and_high_scenarios(self):
        ps = built()["power_scenarios"]
        a = ps["posterior_averaged"]["per_seed;shift=0.25"]["holm_joint_power"]
        self.assertGreater(a, ps["quantile_scenarios"]["per_seed;5%;shift=0.25"]["holm_joint_power"])
        self.assertLess(a, ps["posterior_averaged"]["per_run;shift=0.25"]["holm_joint_power"])
        for v in ps["posterior_averaged"].values():
            self.assertLessEqual(v["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], v["R1_worse_late_than_0s_(Holm_and_McNemar)"] + 1e-6)
            self.assertLessEqual(v["R1_worse_late_than_0s_(Holm_and_McNemar)"], v["headline_R1_fails_late_(Holm)"] + 1e-6)
            lo, hi = v["frechet_G3_replicado"]
            self.assertLessEqual(lo - 1e-6, v["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"])
            self.assertLessEqual(v["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], hi + 1e-6)


class SeedIndependence(unittest.TestCase):
    def test_position_arithmetic_on_synthetic_seeds(self):
        for sources in ((1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12)):
            pairs = m.synthetic_overlap_pairs(90000, 99999, max_gap=4, limit=2, sources=sources)
            self.assertTrue(pairs)
            for a, b, k in pairs:
                self.assertTrue(90000 <= a[0] <= 99999 and 90000 <= b[0] <= 99999)
                wa, wb = words(a[0], a[1], k + 4), words(b[0], b[1], 4)
                self.assertEqual(wa[k:k + 4], wb, (a, b, k))  # the later stream replays the earlier one, k outputs on
                self.assertNotEqual(wa[:4], wb)
        a, b, k = m.synthetic_overlap_pairs(90000, 99999, max_gap=1, limit=1)[0]
        self.assertEqual(k, 1)

    def test_partner_mask_matches_a_brute_force_check_on_synthetic_seeds(self):
        if m._np is None:
            self.skipTest("numpy not available")
        used = m.used_draws(2000, 400)
        targets = {"t": (90000, 90600)}
        intervals = m._target_intervals(targets, used)
        seeds = list(range(90601, 94601))
        mask = m.partner_mask(seeds, intervals)
        idx = m._seen_index(targets, used)
        brute = [bool(m._block_vs_index(s, s, idx, used)) for s in seeds]
        self.assertEqual(list(mask), brute)
        self.assertTrue(any(brute), "the synthetic check must contain at least one overlapping seed")

    def test_used_draws_follow_the_code(self):
        u = m.used_draws(2000, 400)
        self.assertEqual((u[7], u[8], u[10]), (8000, 4800, 24000))

    def test_the_proposed_block_and_reserve_are_clear(self):
        ind = built()["seed_independence"]
        self.assertEqual(ind["block"], [81000, 81919])
        self.assertEqual(ind["reserve"], [80904, 80983])
        for label in ("case_40s", "code_limit"):
            self.assertEqual(ind[f"within_block_{label}"]["pairs_overlapping_in_the_outputs_actually_used"], 0)
            self.assertEqual(ind[f"within_block_{label}"]["streams"], 920 * 12)
            self.assertGreater(ind[f"within_block_{label}"]["min_slack_between_next_stream_and_used_range"], 10**12)
            self.assertEqual(ind[f"within_reserve_{label}"]["pairs_overlapping_in_the_outputs_actually_used"], 0)
            self.assertEqual(ind[f"block_against_declared_ranges_{label}"], 0)
            self.assertEqual(ind[f"reserve_against_declared_ranges_{label}"], 0)
            self.assertEqual(ind[f"reserve_against_block_{label}"], 0)

    def test_exhaustive_scan_finds_no_inventoried_partner(self):
        e = built()["seed_independence"]["exhaustive_partner_scan_code_limit"]
        if "skipped" in e:
            self.skipTest(e["skipped"])
        self.assertEqual(e["scanned_seeds"], "0 to 16777215")
        self.assertGreater(e["partner_seeds"], 0)  # the structure exists: partners are simply not inventoried
        self.assertEqual(e["inventory_integers_in_partner_set"], [])
        self.assertEqual(e["inventory_ranges_meeting_partner_set"], [])
        self.assertEqual(e["of_which_partners"], [])
        inv = built()["seed_independence"]["inventory"]
        self.assertGreater(inv["files_scanned"], 500)
        self.assertGreater(inv["distinct_integers"], 100)

    def test_known_cases_are_in_the_inventory_and_rejected_blocks_are_rejected(self):
        # 81920-81999 overlap themselves; 80920-80999 meet the M6 final seed 83017 (position arithmetic only)
        code = (m.MAX_STEPS // m.CONTROL_PERIOD, m.MAX_STEPS // m.CONTROL_PERIOD // m.GNSS_PERIOD_CYCLES)
        self.assertGreater(m.seed_independence(81920, 81999, *code)["pairs_overlapping_in_the_outputs_actually_used"], 0)
        used = m.used_draws(*code)
        idx = m._seen_index({"m6": (83017, 83017)}, used)
        self.assertGreater(len(m._block_vs_index(80920, 80999, idx, used)), 0)
        self.assertEqual(len(m._block_vs_index(80904, 80983, idx, used)), 0)

    def test_stress_check_with_four_million_draws(self):
        e = built()["seed_independence"]["stress_4000000_draws_per_stream"]
        self.assertEqual(e["within_block_overlapping_pairs"], 0)
        self.assertEqual(e["block_against_declared_overlapping_pairs"], 0)
        self.assertGreater(e["block_to_declared_min_position_distance"], 4_000_000)
        self.assertEqual(e["inventory_integers_in_partner_set"], [])
        self.assertEqual(e["partner_seeds_0_to_2^24"], 59961)

    def test_synthetic_check_is_recorded(self):
        s = built()["synthetic_arithmetic_check"]
        self.assertEqual(s["block"], [90000, 99999])
        self.assertGreaterEqual(s["dispersion_pairs_found"], 1)
        self.assertGreaterEqual(s["sensor_pairs_found"], 1)

    def test_rng_operations_are_disclosed(self):
        ops = built()["rng_operations_disclosed"]
        self.assertTrue(any("44000" in o["operation"] and "44128" in o["operation"] for o in ops))
        self.assertTrue(any(o.get("printed") for o in ops))


class Candidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_label_first_and_only_dashes(self):
        first = next(line for line in self.text.splitlines() if line.strip())
        self.assertEqual(first.strip(), LABEL)
        self.assertEqual(self.text.count(EM_DASH), 2)

    def test_cited_hashes_of_script_and_calculations(self):
        self.assertIn(lf_sha256(SCRIPT), self.text)
        self.assertIn(lf_sha256(CALC), self.text)

    def test_base_hashes_are_cited(self):
        sim = built()["provenance"]["simulator"]
        self.assertIn(sim["source_sha256_base"], self.text)
        self.assertIn(sim["source_sha256_m13_commit"], self.text)
        pins = built()["provenance"]["pinned_blob_sha256"]
        for path in ("docs/m15-g3-onset-protocol.md", "exec/claims/m13/g3-onset.json",
                     "exec/cases/m13/g3-registered.json", "docs/evidence/m14/masking/prediction.json"):
            self.assertIn(pins[path], self.text, path)

    def test_numbers_in_the_text_come_from_the_calculations(self):
        d = built()
        t = d["tests"]
        want = [
            f"{t['H2_late_holds_high_band']['reject_if_successes_at_least']} de {t['H2_late_holds_high_band']['n']}",
            f"{t['H1a_late_fails_low_band']['reject_if_successes_at_least']} de {t['H1a_late_fails_low_band']['n']}",
            f"{t['S3_R5_fails_at_0s_high_band']['reject_if_successes_at_least']} de {t['S3_R5_fails_at_0s_high_band']['n']}",
            f"{t['H1b_pooled_zero_s_both_bands_0.01']['reject_if_successes_at_least']} de {t['H1b_pooled_zero_s_both_bands_0.01']['n']}",
            f"{t['M1_threshold_1m']['reject_if_successes_at_least']} de {t['M1_threshold_1m']['n']}",
            f"{t['M2_threshold_2m']['reject_if_successes_at_least']} de {t['M2_threshold_2m']['n']}",
            f"{t['S7_each_proportion']['reject_if_successes_at_least']} de {t['S7_each_proportion']['n']}",
            pt(d["h1_options"]["scenarios"]["p0=0.93 q=1.00"]["alpha_0.01/3"]["O0_conjunction"], 3),
            pt(d["evidence"]["p0_all_magnitudes_0s"]["pooled"]["cp99_lower"], 3),
            pt(d["budgets"]["invariants_1pct"]["cp99_upper_at_0"] * 100, 3) + " %",
            str(d["budgets"]["min_pairs_for_zero_events_within_1pct"]),
            str(d["layout"]["checks"]["total_runs"]),
        ]
        for w in want:
            self.assertIn(w, self.text, w)

    def test_power_numbers_in_the_text_come_from_the_scenarios(self):
        ps = built()["power_scenarios"]
        for key in ("p=0.95;shift=0.25", "p=0.97;shift=0.25", "p=0.99;shift=0.25", "p=0.97;shift=0.75"):
            self.assertIn(pt(ps["common_rate_grid"][key]["holm_joint_power"], 3), self.text, key)
        for key in ("per_seed;shift=0.25", "per_seed;shift=0.75", "per_seed;shift_uniform_0_to_0.75"):
            self.assertIn(pt(ps["posterior_averaged"][key]["holm_joint_power"], 3), self.text, key)
        for key in ("per_seed;5%;shift=0.25", "per_seed;cp99_lower;shift=0.25"):
            self.assertIn(pt(ps["quantile_scenarios"][key]["holm_joint_power"], 3), self.text, key)
        post = ps["posteriors"]["p0_0s_R1_holds"]["per_seed"]
        self.assertIn(pt(post["cp99_lower"], 3), self.text)

    def test_required_sections_exist(self):
        for heading in ("## Diferenças face ao candidato M15", "## Opções de desenho para H1", "## Hipóteses",
                        "## Sementes", "## Operações de RNG já realizadas", "## Por decidir pelo responsável",
                        "### Independência entre sementes"):
            self.assertIn(heading, self.text)

    def test_every_stage_range_in_the_text_matches_the_layout(self):
        stages = built()["layout"]["stages"]
        for stage in stages.values():
            self.assertIn(f"{stage['first']} a {stage['last']}", self.text)
        for needle in ("81000 a 81919", "81916 a 81919", "80904 a 80983"):
            self.assertIn(needle, self.text)

    def test_decisions_and_rules_are_in_the_text(self):
        for needle in ("Holm de passo descendente", "Portas em série", "interseção-união",
                       "161 de 168", "316 de 336",
                       "teste de sinais exato unilateral sobre os pares discordantes",
                       "R1 pior com início tardio do que com início 0 s, na mesma semente",
                       "G3 replicado no conjunto das bandas testadas",
                       "nenhuma palavra de saída de nenhuma semente protegida ou confirmatória é gerada",
                       "Nenhuma taxa se toma como exatamente 100 %",
                       "fecha todas as portas a jusante", "Hoeffding", "novo confirmatório",
                       "estreitar a guarda a 81000 a 81919", "XorShift64Star", "nenhuma aprovação é pedida agora",
                       "ainda não protege", "evidência transportada para condições não testadas", "pendentes de verificação metodológica e de revisão humana"):
            self.assertIn(needle, self.text, needle)
        self.assertNotIn("padrão provisório", self.text.lower())
        self.assertNotIn("todos no sentido previsto", self.text)
        self.assertNotIn("(tomadas)", self.text)
        self.assertNotIn("optimista", self.text.lower())

    def test_rng_disclosure_lists_the_protected_streams(self):
        for needle in ("(44000, fonte 2) e (44128, fonte 6)", "(44804, fonte 10) e (41212, fonte 12)",
                       "6 e 2 palavras foram impressas", "git mantém"):
            self.assertIn(needle, self.text, needle)

    def test_mascaramento_is_not_a_hypothesis_label(self):
        for line in self.text.splitlines():
            if line.startswith(("- **H1", "- **H2", "- **H3", "| H1", "| H2")):
                self.assertNotIn("ascaramento", line, line)


if __name__ == "__main__":
    unittest.main()
