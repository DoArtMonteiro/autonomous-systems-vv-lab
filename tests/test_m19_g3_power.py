"""Tests of the M19 G3 power calculations and of the corrected candidate that cites them.

No simulator is run and no simulator seed is used: the checks read committed blobs, recorded
evidence and the output of `scripts/m19_g3_power.py`, which is exact arithmetic.
"""

import hashlib
import json
import subprocess
import sys
import unittest
from fractions import Fraction as F
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
        # The reported ~0.064: pi = 0.93 (a hypothetical 0 s rate with perfect late masking), n = 160.
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
        # 60 seeds are not enough at either level; 63 is the minimum at 0.01/7.
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
        self.assertEqual(s["rule_54_of_60_acceptance_probability"]["0.85"], 0.184841)

    def test_order_statistic_positions(self):
        self.assertEqual(m.os_positions(60, F(1, 300)), (20, 41))
        self.assertEqual(m.os_positions(60, F(1, 700)), (19, 42))

    def test_clopper_pearson_and_budgets(self):
        self.assertAlmostEqual(m.cp_upper(0, 480), 0.009548, places=5)
        self.assertAlmostEqual(m.cp_upper(13, 480), 0.04971, places=4)
        b = built()["budgets"]
        self.assertEqual(b["min_pairs_for_zero_events_within_1pct"], 459)
        self.assertFalse(b["if_D_kept_at_7_onsets_x_10_reps"]["feasible_within_1pct"])
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
        # First outputs of SplitMix64 with state 0 (public reference values).
        g = m.SplitMix64(0)
        self.assertEqual(g.next(), 0xE220A8397B1DCDAF)
        self.assertEqual(g.next(), 0x6E789E6AA1B965F4)


class OnsetGeometry(unittest.TestCase):
    def test_late_onsets_in_a_gnss_interval_are_one_condition(self):
        g = m.groups_for([0.0, 0.01, 0.02, 0.05, 0.1, 0.11, 1.0])
        self.assertEqual(g[1], g[2])
        self.assertEqual(g[1], g[3])
        self.assertEqual(g[1], g[4])
        self.assertNotEqual(g[0], g[1])  # 0 s initialises the estimator on a biased fix
        self.assertNotEqual(g[4], g[5])  # 0.11 s waits for the 0.2 s fix
        self.assertNotEqual(g[4], g[6])

    def test_corrected_onsets_are_distinct_fixes_and_m15_had_a_duplicate(self):
        every = m.CONTROL_PERIOD_STEPS * m.GNSS_PERIOD_CYCLES
        starts = [round(t / m.DT_S) for t in m.ONSETS]
        self.assertTrue(all(s % every == 0 for s in starts))
        self.assertEqual(len(set(starts)), len(m.ONSETS))
        self.assertEqual(len(m.ONSETS_M15), 8)
        self.assertEqual(len(set(m.groups_for(m.ONSETS_M15))), 7)
        self.assertEqual(built()["onset_geometry"]["m15_onsets_sharing_a_sensor_history"], [[0.01, 0.1]])


class SeedMaps(unittest.TestCase):
    def test_every_seed_has_one_condition_inside_the_range(self):
        cond, summary = m.seed_map()
        checks = m.seed_checks(cond, summary)
        self.assertTrue(checks["each_seed_one_condition"])
        self.assertTrue(checks["all_within_44000_44919"])
        self.assertTrue(checks["no_seed_in_reserve_44920_44999"])
        self.assertTrue(checks["stage_ranges_disjoint"])
        self.assertTrue(all(v == 0 for v in checks["overlap_with_spent_or_protected"].values()))
        self.assertEqual(checks["seeds_used"], 896)
        self.assertEqual(checks["total_runs"], 5704)
        self.assertEqual((checks["unassigned_first"], checks["unassigned_last"]), (44896, 44919))
        self.assertTrue(all(44000 <= s <= 44919 for s in cond))

    def test_cells_are_balanced(self):
        _, summary = m.seed_map()
        for stage, per in (("A_low", 6), ("A_high", 5), ("D", 11)):
            self.assertEqual(summary[stage]["distinct_conditions"], 28)
            self.assertEqual((summary[stage]["seeds_per_condition_min"], summary[stage]["seeds_per_condition_max"]), (per, per))
        self.assertEqual(summary["E"]["distinct_conditions"], 160)

    def test_the_m15_layout_totals(self):
        t = m.m15_layout_totals()
        self.assertEqual((t["seeds"], t["runs"]), (920, 5800))

    def test_no_simulator_seed_is_a_script_seed(self):
        self.assertFalse(44000 <= m.MC_SEED <= 44999)
        self.assertFalse(50000 <= m.MC_SEED <= 59999)


class Provenance(unittest.TestCase):
    def test_source_hash_and_what_changed(self):
        sim = built()["provenance"]["simulator"]
        self.assertEqual(sim["source_sha256_base"][:8], "295a45b2")
        self.assertEqual(sim["source_sha256_m13_commit"][:8], "12b276cb")
        self.assertEqual(sim["source_sha256_m13_commit"], sim["source_sha256_m13_recorded"])
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
    def test_json_is_deterministic_and_matches_the_committed_file(self):
        data = m.render(built())
        self.assertEqual(data, m.render(m.build()), "two runs differ")
        self.assertNotIn(b"\r", data)
        self.assertNotIn(EM_DASH.encode("utf-8"), data)
        text = data.decode("ascii")
        self.assertNotIn(str(ROOT).replace("\\", "/"), text)
        self.assertEqual(CALC.read_bytes(), data, "regenerate with scripts/m19_g3_power.py --output")

    def test_script_has_no_forbidden_dash(self):
        self.assertNotIn(EM_DASH, SCRIPT.read_text(encoding="utf-8"))


class Candidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_label_first_and_only_dashes(self):
        first = next(line for line in self.text.splitlines() if line.strip())
        self.assertEqual(first.strip(), LABEL)
        self.assertEqual(self.text.count(EM_DASH), 2)  # the two inside the label

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
            f"{t['M1_threshold_1m']['reject_if_successes_at_least']} de {t['M1_threshold_1m']['n']}",
            f"{t['M2_threshold_2m']['reject_if_successes_at_least']} de {t['M2_threshold_2m']['n']}",
            f"{t['S7_each_proportion']['reject_if_successes_at_least']} de {t['S7_each_proportion']['n']}",
            pt(d["h1_options"]["scenarios"]["p0=0.93 q=1.00"]["alpha_0.01/3"]["O0_conjunction"], 3),
            pt(d["evidence"]["p0_all_magnitudes_0s"]["pooled"]["cp99_lower"], 3),
            pt(d["budgets"]["invariants_1pct"]["cp99_upper_at_0"] * 100, 2) + " %",
            str(d["budgets"]["min_pairs_for_zero_events_within_1pct"]),
            str(d["layout"]["checks"]["total_runs"]),
        ]
        for w in want:
            self.assertIn(w, self.text, w)

    def test_required_sections_exist(self):
        for heading in ("## Diferenças face ao candidato M15", "## Opções de desenho para H1",
                        "## Hipóteses", "## Sementes"):
            self.assertIn(heading, self.text)

    def test_every_stage_range_in_the_text_matches_the_layout(self):
        stages = built()["layout"]["stages"]
        for stage in stages.values():
            self.assertIn(f"{stage['first']} a {stage['last']}", self.text)

class HolmAndGates(unittest.TestCase):
    def test_holm_rule(self):
        self.assertTrue(m.holm_ok((3, 3, 3)))
        self.assertTrue(m.holm_ok((3, 2, 1)))
        self.assertTrue(m.holm_ok((3, 3, 1)))
        self.assertFalse(m.holm_ok((2, 2, 2)))  # nobody passes 0.01/3
        self.assertFalse(m.holm_ok((3, 1, 1)))  # second smallest p fails 0.01/2
        self.assertFalse(m.holm_ok((3, 3, 0)))

    def test_class_based_holm_matches_direct_p_values(self):
        sizes, pis = (60, 66, 72), (F("0.99"), F("0.985"), F("0.995"))
        classes = [m.class_probs_binom(n, p) for n, p in zip(sizes, pis)]
        fast = m.holm_joint(*classes)
        pmfs = [[comb_pmf(n, k, p) for k in range(n + 1)] for n, p in zip(sizes, pis)]
        tails = [[m.sf(k, n, F(9, 10)) for k in range(n + 1)] for n in sizes]
        direct = F(0)
        for a in range(sizes[0] + 1):
            for b in range(sizes[1] + 1):
                for c in range(sizes[2] + 1):
                    ps = sorted((tails[0][a], tails[1][b], tails[2][c]))
                    if ps[0] <= F(1, 300) and ps[1] <= F(1, 200) and ps[2] <= F(1, 100):
                        direct += pmfs[0][a] * pmfs[1][b] * pmfs[2][c]
        self.assertEqual(fast, direct)

    def test_ladder_thresholds_and_ordering_of_the_bounds(self):
        h = built()["holm_design"]
        self.assertEqual(h["thresholds"]["H1a_n168"], [162, 161, 161])
        self.assertEqual(h["thresholds"]["H1b_pooled_n308_0.01"], 290)
        self.assertEqual(h["thresholds"]["S6_n140_0.01/7"], 136)
        self.assertEqual(h["thresholds"]["H2_n140"], [136, 135, 135])
        self.assertEqual(h["thresholds"]["H3_order_statistic_positions_n60"], [[20, 41], [20, 41], [21, 40]])
        self.assertEqual(h["thresholds"]["mcnemar_gate_min_discordant_0.01"], 7)
        for name, v in h["scenarios"].items():
            g = v["gates"]
            self.assertLessEqual(v["bonferroni_lower_bound_all_at_0.01/3"], v["holm_joint_power"] + 1e-6, name)
            self.assertLessEqual(v["holm_joint_power"], v["all_at_0.01_upper_bound"] + 1e-6, name)
            self.assertLessEqual(g["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], g["R1_worse_late_than_0s_(Holm_and_McNemar)"] + 1e-6)
            self.assertLessEqual(g["R1_worse_late_than_0s_(Holm_and_McNemar)"], g["headline_R1_fails_late_(Holm)"] + 1e-6)
            lo, hi = g["frechet_G3_replicado"]
            self.assertLessEqual(lo - 1e-6, g["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"])
            self.assertLessEqual(g["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], hi + 1e-6)
            self.assertAlmostEqual(sum(v["classes_H1a"].values()), 1.0, places=5)

    def test_gates_agree_with_a_direct_enumeration_in_a_small_case(self):
        # n = 12, alpha ladder replaced by the real ladder; no Holm family (rest = 1 for every class):
        # the gate sums must equal a direct sum over the four-cell multinomial.
        n, p0, q = 12, F("0.9"), F("0.8")
        rest = {c: F(1) for c in range(4)}
        got = m.gates_power(n, p0, q, rest)
        # with n = 12 no binomial threshold exists, so H1a never rejects and every gate is zero
        self.assertEqual(got["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], 0.0)
        self.assertEqual(got["headline_R1_fails_late_(Holm)"], 0.0)

    def test_cells_and_non_acting_rule(self):
        c = built()["cell_tolerance"]
        self.assertEqual(c["H1a"]["by_level"]["0.01/3"]["whole_cells_tolerated"], 1)
        self.assertEqual(c["H2"]["by_level"]["0.01/3"]["whole_cells_tolerated"], 0)
        self.assertEqual(c["H2"]["by_level"]["0.01/3"]["majority_contrary_cells_tolerated"], 1)
        self.assertEqual((c["not_acting_runs"]["H1a_max_excluded"], c["not_acting_runs"]["H2_max_excluded"]), (8, 7))

    def test_s4_s5_direction_test(self):
        s = built()["s4_s5_mcnemar"]
        self.assertEqual(s["floor_discordant_pairs"], 10)
        self.assertEqual(s["natural_minimum_discordant_pairs_all_predicted"], 10)
        self.assertGreaterEqual(s["power_by_predicted_rate"]["0.50"]["both_conditions"], 0.9999)
        self.assertAlmostEqual(s["fraction_descriptive_cp99_lower"]["54_of_60"], 0.774088, places=5)


def comb_pmf(n, k, p):
    from math import comb
    return comb(n, k) * p**k * (1 - p) ** (n - k)


class SeedIndependence(unittest.TestCase):
    def test_positions_reproduce_the_generator(self):
        g = m.SplitMix64(44000 ^ ((2 * m.GOLDEN) & m.MASK64))
        h = m.SplitMix64(44128 ^ ((6 * m.GOLDEN) & m.MASK64))
        a = [g.next() for _ in range(6)]
        b = [h.next() for _ in range(2)]
        self.assertEqual(b, a[4:6])  # the near collision noted in the document
        d = (m.stream_position(44128, 6) - m.stream_position(44000, 2)) & m.MASK64
        self.assertEqual(d, 4)

    def test_no_overlap_in_the_outputs_actually_used(self):
        ind = built()["seed_independence"]
        for key in ("seeds_44000_44919_case_40s", "seeds_44000_44919_code_limit", "seeds_44000_44999_code_limit"):
            r = ind[key]
            self.assertEqual(r["pairs_overlapping_in_the_outputs_actually_used"], 0, key)
            self.assertEqual(r["distinct_positions"], r["streams"], key)
            self.assertGreaterEqual(r["min_slack_between_next_stream_and_used_range"], 1, key)
        self.assertEqual(ind["seeds_44000_44919_case_40s"]["streams"], 920 * 12)
        self.assertEqual(ind["seeds_44000_44919_case_40s"]["pairs_overlapping_if_every_stream_used_the_largest_count"], 3180)

    def test_used_draws_follow_the_code(self):
        u = m.used_draws(2000, 400)
        self.assertEqual((u[7], u[8], u[10]), (8000, 4800, 24000))


class RevisionTwoText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_decisions_are_in_the_text(self):
        for needle in ("Holm de passo descendente", "Portas em série", "interseção-união",
                       "161 de 168", "135 de 140", "290 de 308",
                       "teste de sinais exato unilateral sobre os pares discordantes",
                       "R1 pior com início tardio do que com início 0 s, na mesma semente",
                       "nenhuma simulação correu com essas sementes; a aritmética do PRNG e um teste leem os seus estados iniciais",
                       "fecha todas as portas a jusante", "Por decidir pelo responsável",
                       "Hoeffding", "novo confirmatório"):
            self.assertIn(needle, self.text, needle)
        self.assertNotIn("padrão provisório", self.text.lower())
        self.assertNotIn("todos no sentido previsto", self.text)
        self.assertNotIn("revisão 2", self.text.lower())
        self.assertNotIn("(tomadas)", self.text)

    def test_holm_numbers_in_the_text(self):
        h = built()["holm_design"]["scenarios"]
        for name in ("development-like", "moderate", "pessimistic"):
            self.assertIn(pt(h[name]["holm_joint_power"], 3), self.text, name)
        g = h["moderate"]["gates"]
        self.assertIn(pt(g["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], 3), self.text)
        self.assertIn(pt(h["pessimistic"]["gates"]["G3_replicado_(Holm_and_McNemar_and_H1b_pooled)"], 3), self.text)
        fb = built()["layout_option_B_E19_Ahigh168"]["budgets"]
        self.assertIn(str(fb["pairs_invariants_and_r2_r6"]), self.text)
        self.assertIn(pt(fb["invariants_cp99_upper_at_0"] * 100, 3) + " %", self.text)



class RevisionThree(unittest.TestCase):
    def test_b_s_convention(self):
        lv = [10.0, 10.25, 10.5, 10.75]
        self.assertEqual(m.b_s_per_seed(lv, [False, False, True, True]), (10.5, "exact"))
        self.assertEqual(m.b_s_per_seed(lv, [True, True, True, True]), (10.0, "at_or_below"))
        self.assertEqual(m.b_s_per_seed(lv, [True, True, True, False]), (float("inf"), "above_highest"))
        self.assertEqual(m.b_s_per_seed(lv, [True, False, True, True]), (10.5, "exact"))  # non-monotone

    def test_exposure_rule_is_above_the_model_transient(self):
        e = built()["exposure_rule"]
        self.assertEqual(e["minimum_biased_gnss_fixes"], 11)
        self.assertLess(e["slowest_s"], e["minimum_exposure_s"])
        self.assertAlmostEqual(e["slowest_s"], 0.58)

    def test_hoeffding_condition_for_the_pooled_binomials(self):
        # thresholds must exceed n * 0.9 + 1 for the binomial tail to bound the heterogeneous one
        for n, k in ((168, 162), (140, 136), (308, 290), (231, 220), (77, 76)):
            self.assertGreater(k, n * 0.9 + 1, (n, k))

    def test_layout_option_b(self):
        b = built()["layout_option_B_E19_Ahigh168"]
        self.assertTrue(b["checks"]["each_seed_one_condition"])
        self.assertTrue(b["checks"]["no_seed_in_reserve_44920_44999"])
        self.assertEqual((b["checks"]["seeds_used"], b["checks"]["unassigned_seeds"], b["checks"]["total_runs"]), (916, 4, 5736))
        self.assertEqual(b["budgets"]["pairs_invariants_and_r2_r6"], 460)
        self.assertTrue(b["budgets"]["invariants_feasible_within_1pct"])
        self.assertEqual(b["holm_design"]["thresholds"]["H2_n168"], [162, 161, 161])

    def test_cross_range_overlap_is_recorded_not_hidden(self):
        r = built()["seed_independence"]["against_seen_and_protected_ranges_case_40s"]
        self.assertEqual(r["pairs_overlapping_in_the_outputs_actually_used"], 288)
        self.assertEqual(r["distinct_new_seeds_affected"], 258)
        self.assertEqual(r["seen_seeds"], 15382)
        for key in r["pairs_by_source_pair_and_seen_range"]:
            a, b = key.split(" x seen source ")
            self.assertNotEqual(a.split()[-1], b.split()[0], key)  # never the same source on both sides

    def test_no_literal_dash_in_the_tests(self):
        self.assertNotIn(EM_DASH, Path(__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
