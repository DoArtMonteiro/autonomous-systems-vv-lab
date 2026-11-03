"""The vv-exec statistics fixture is exactly what the independent reference script produces, and
the reference agrees with the separately written M10 statistics (scripts/m10_stats.py)."""

from __future__ import annotations

import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m10_stats  # noqa: E402
import m12_stats_reference as ref  # noqa: E402


class StatsReferenceTest(unittest.TestCase):
    def test_fixture_is_the_output_of_the_reference_script(self) -> None:
        stored = ref.FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(stored, ref.render(), "run: python scripts/m12_stats_reference.py")

    def test_render_does_not_depend_on_the_float_summation_algorithm(self) -> None:
        # Python 3.12 made sum() of floats compensated; CI runs 3.10. The binomial tails must not
        # use float summation, so a naive left-to-right sum must give the same bytes.
        def naive_sum(values, start=0):
            total = start
            for v in values:
                total = total + v
            return total

        with mock.patch.object(ref, "sum", naive_sum, create=True):
            self.assertEqual(ref.render(), ref.FIXTURE.read_text(encoding="utf-8"))

    def test_binomial_tails_do_not_call_libm(self) -> None:
        # glibc and the Windows CRT round log/exp/lgamma differently in the last bit.
        def refuse(*_args):
            raise AssertionError("libm function called")

        with mock.patch.multiple(ref.math, lgamma=refuse, log=refuse, log1p=refuse, exp=refuse):
            ref.binom_cdf(250, 1000, 0.25)
            ref.clopper_pearson(3, 1000, 0.95)

    def test_binomial_cdf_is_the_correctly_rounded_exact_value(self) -> None:
        for k, n, p in ref.CDF_CASES:
            fp = Fraction(p)
            exact = sum(math.comb(n, i) * fp**i * (1 - fp) ** (n - i) for i in range(k + 1))
            self.assertEqual(ref.binom_cdf(k, n, p), float(exact), (k, n, p))

    def test_clopper_pearson_agrees_with_the_m10_implementation(self) -> None:
        for k, n in ref.INTERVAL_CASES:
            for c in ref.CONFIDENCES:
                lo, hi = ref.clopper_pearson(k, n, c)
                tail = (1 - c) / 2
                if k < n:
                    self.assertAlmostEqual(hi, m10_stats.cp_upper(k, n, tail), delta=1e-9)
                if k > 0:
                    self.assertAlmostEqual(lo, m10_stats.cp_lower(k, n, tail), delta=1e-9)

    def test_mcnemar_agrees_with_the_m10_implementation(self) -> None:
        for b, c in ref.MCNEMAR_CASES:
            self.assertAlmostEqual(ref.mcnemar_exact(b, c), m10_stats.mcnemar_exact(b, c), delta=1e-12)

    def test_interval_definitions_hold(self) -> None:
        # Each end of the exact interval puts alpha/2 in its tail.
        for k, n in [(7, 20), (3, 1000)]:
            lo, hi = ref.clopper_pearson(k, n, 0.95)
            self.assertAlmostEqual(ref.binom_sf(k, n, lo), 0.025, delta=1e-10)
            self.assertAlmostEqual(ref.binom_cdf(k, n, hi), 0.025, delta=1e-10)
        # The Wilson interval of 0/n starts at 0 and that of n/n ends at 1, up to rounding.
        self.assertAlmostEqual(ref.wilson(0, 20, 0.95)[0], 0.0, delta=1e-15)
        self.assertAlmostEqual(ref.wilson(20, 20, 0.95)[1], 1.0, delta=1e-15)

    def test_ishigami_indices_sum_as_the_variance_decomposition_requires(self) -> None:
        i = ref.ishigami()
        # Only the (1, 3) interaction exists: S1 + S2 + S3 + S13 = 1 with S13 = ST3.
        self.assertAlmostEqual(sum(i["first_order"]) + i["total"][2], 1.0, delta=1e-12)
        self.assertAlmostEqual(i["total"][0] - i["first_order"][0], i["total"][2], delta=1e-12)


if __name__ == "__main__":
    unittest.main()
