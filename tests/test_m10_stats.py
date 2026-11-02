"""Testes da estatística do M10 (`scripts/m10_stats.py`) e do protocolo de afinação (`scripts/m10_tune.py`)."""

import itertools
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import m10_campaign as camp  # noqa: E402
import m10_stats as st  # noqa: E402
import m10_tune as tune  # noqa: E402


class ScoreTest(unittest.TestCase):
    def test_tango_values_match_the_preregistered_examples(self):
        # docs/m10-resilient-navigation.md 10.5, exemplos com n = 800.
        self.assertAlmostEqual(st.tango_p(15, 15, 800), 0.00011, delta=0.00002)
        self.assertLess(st.tango_p(10, 25, 800), 1e-7)
        self.assertAlmostEqual(st.tango_p(30, 5, 800), 0.57, delta=0.01)
        self.assertAlmostEqual(st.tango_p(40, 40, 800), 0.0047, delta=0.0003)

    def test_the_p_value_grows_with_b(self):
        for c in (0, 5, 30):
            values = [st.tango_p(b, c, 200) for b in range(0, 60)]
            self.assertEqual(values, sorted(values))

    def test_the_enumerated_size_equals_brute_force_on_a_small_n(self):
        n, alpha = 40, 0.05
        bounds = st.rejection_boundary(n, alpha)
        self.assertTrue(st.check_monotone(n, alpha, bounds))
        for p_c in (0.02, 0.08):
            p_b, p_0 = p_c + st.P3_MARGIN, 1.0 - 2 * p_c - st.P3_MARGIN
            brute = 0.0
            for b, c in itertools.product(range(n + 1), repeat=2):
                if b + c <= n and st.tango_p(b, c, n) < alpha:
                    r = n - b - c
                    brute += math.exp(math.lgamma(n + 1) - math.lgamma(b + 1) - math.lgamma(c + 1)
                                      - math.lgamma(r + 1) + b * math.log(p_b) + c * math.log(p_c)
                                      + r * math.log(p_0))
            self.assertAlmostEqual(st.exact_size(n, p_c, bounds), brute, places=12)

    def test_the_size_report_is_deterministic_and_states_its_criterion(self):
        a = st.size_report(60, grid=(0.01, 0.05), alphas=(0.05,), monotone_step=10)
        self.assertEqual(a, st.size_report(60, grid=(0.01, 0.05), alphas=(0.05,), monotone_step=10))
        self.assertEqual(len(a["rows"]), 2)
        self.assertIn("criterion_met", a)

    def test_mcnemar_is_two_sided_and_symmetric(self):
        self.assertEqual(st.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(st.mcnemar_exact(0, 6), 2 * 0.5 ** 6)
        self.assertEqual(st.mcnemar_exact(3, 9), st.mcnemar_exact(9, 3))


class PairedTest(unittest.TestCase):
    def records(self, seeds=range(5000, 5004)):
        out = []
        for s in seeds:
            out.append({"scenario": "x", "arm": "guarded", "seed": s, "recovery": s % 2 == 0})
            out.append({"scenario": "x", "arm": "m10_b_plus", "seed": s, "recovery": s != 5002})
        return out

    def test_pairs_are_counted_by_seed(self):
        row = st.paired(self.records(), "guarded", "m10_b_plus")["rows"][0]
        self.assertEqual((row["pairs"], row["first"], row["second"]), (4, 2, 3))
        self.assertEqual((row["b_only_first"], row["c_only_second"]), (1, 2))
        lo, hi = row["difference_ci95_pp"]
        self.assertLess(lo, row["difference_pp"])
        self.assertGreater(hi, row["difference_pp"])

    def test_protected_seeds_and_duplicates_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "records.json"
            path.write_text(json.dumps(self.records([3001])), encoding="utf-8")
            with self.assertRaises(ValueError):
                st.load_records([path])
        with self.assertRaises(ValueError):
            st.paired(self.records() + self.records(), "guarded", "m10_b_plus")


class TuningProtocolTest(unittest.TestCase):
    def test_every_arm_gets_the_same_budget_and_a_seeded_draw(self):
        start = camp.load_template(camp.TEMPLATE)[0]["controller"]["nav"]
        for arm in tune.SPACES:
            a = tune.draws(arm, start, 10)
            self.assertEqual(a, tune.draws(arm, start, 10))
            self.assertEqual(len(a), tune.BUDGET)
            self.assertEqual(a[0], {k: start[k] for k in tune.SPACES[arm]})
            self.assertEqual(len({tuple(sorted(d.items())) for d in a}), tune.BUDGET)
            for d in a[1:]:
                for k, v in d.items():
                    self.assertIn(v, tune.SPACES[arm][k])
            self.assertNotEqual(a, tune.draws(arm, start, 11))

    def test_the_metric_is_the_mean_f1_recovery_with_the_nominal_constraint(self):
        cells = [{"scenario": s, "runs": 100, "recovered": 94 if s == camp.NOMINAL else 90,
                  "navigation": {"spurious_degradation_runs": 3}} for s in camp.FAMILIES["F1"]]
        mean, spurious, _ = tune.metric({"cells": cells})
        self.assertAlmostEqual(mean, (94 + 90 * 10) / 1100)
        self.assertEqual(spurious, 3)
        with self.assertRaises(tune.TuneError):
            tune.metric({"cells": cells[1:]})

    def test_protected_seeds_are_refused_before_any_run(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            self.assertEqual(tune.main(["--arm", "m10_b", "--seeds", "2999-3001", "--output-root", str(out)]), 1)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
