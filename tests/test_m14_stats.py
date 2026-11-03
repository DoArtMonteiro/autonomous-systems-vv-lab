"""Reference checks for scripts/m14_stats.py: hand-computable cases, the exact permutation test,
and the Holm cases of the vv-exec fixture that `exec/tests/stats_reference.rs` also checks."""

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m14_stats as s  # noqa: E402


class MannWhitney(unittest.TestCase):
    def test_u_counts_pairs_and_half_ties(self):
        # Pairs (a, b) with a > b: 3 > 1, 3 > 2, 5 > 1, 5 > 2, 5 > 3 (b = 3 ties a = 3 by half).
        self.assertEqual(s.mann_whitney_u([3, 5], [1, 2, 3]), 5.5)

    def test_exact_test_on_a_hand_computable_case(self):
        # Complete separation of 3 vs 3: only 2 of the 20 splits are as extreme.
        self.assertAlmostEqual(s.mann_whitney_exact([1, 2, 3], [4, 5, 6]), 2 / 20)

    def test_normal_approximation_tracks_the_exact_test(self):
        x = [3, 7, 9, 12, 15, 201]
        y = [1, 2, 4, 5, 6, 8]
        exact = s.mann_whitney_exact(x, y)
        approx = s.mann_whitney(x, y)["p"]
        self.assertLess(abs(exact - approx), 0.02)

    def test_ties_lower_the_variance(self):
        # All censored at the same value: no evidence, p = 1.
        self.assertEqual(s.mann_whitney([201] * 5, [201] * 5)["p"], 1.0)


class Holm(unittest.TestCase):
    def test_matches_the_rust_unit_test(self):
        got = s.holm([0.01, 0.04, 0.03, 0.5])
        for g, w in zip(got, [0.04, 0.09, 0.09, 0.5]):
            self.assertAlmostEqual(g, w, places=15)
        self.assertEqual(s.holm([0.6, 0.9]), [1.0, 1.0])

    def test_matches_the_vv_exec_fixture(self):
        fixture = json.loads((ROOT / "exec/tests/fixtures/stats-reference.json").read_text())
        for case in fixture["holm"]:
            p = [float(x) for x in case["p"]]
            want = [float(x) for x in case["adjusted"]]
            for g, w in zip(s.holm(p), want):
                self.assertLess(abs(g - w), 1e-15)


class ClopperPearson(unittest.TestCase):
    def test_known_values(self):
        # Exact values at the ends: 1 - 0.025 ** (1/10) and 0.025 ** (1/10).
        lo, hi = s.clopper_pearson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 1 - 0.025 ** (1 / 10), places=9)
        lo, hi = s.clopper_pearson(10, 10)
        self.assertAlmostEqual(lo, 0.025 ** (1 / 10), places=9)
        self.assertEqual(hi, 1.0)
        lo, hi = s.clopper_pearson(5, 10)
        self.assertAlmostEqual(lo, 0.18708602, places=6)
        self.assertAlmostEqual(hi, 0.81291398, places=6)

    def test_one_sided_bounds(self):
        # 100 of 100: the one-sided 95 % lower bound is 0.05 ** (1/100).
        self.assertAlmostEqual(s.one_sided_lower(100, 100), 0.05 ** (1 / 100), places=9)
        self.assertEqual(s.one_sided_lower(0, 100), 0.0)


class Bootstrap(unittest.TestCase):
    def test_is_reproducible_and_brackets_the_estimate(self):
        x = [10, 12, 14, 30, 31, 35]
        y = [1, 2, 3, 4, 5, 6]
        a = s.bootstrap_median_difference(x, y, 2000, 7)
        b = s.bootstrap_median_difference(x, y, 2000, 7)
        self.assertEqual(a, b)
        self.assertLessEqual(a["low"], a["difference"])
        self.assertGreaterEqual(a["high"], a["difference"])
        self.assertGreater(a["low"], 0)
        self.assertTrue(math.isfinite(a["high"]))


if __name__ == "__main__":
    unittest.main()
