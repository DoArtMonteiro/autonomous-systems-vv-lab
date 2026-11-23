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
EM_DASH = "—"
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


if __name__ == "__main__":
    unittest.main()
