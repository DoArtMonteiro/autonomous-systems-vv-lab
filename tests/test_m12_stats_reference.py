"""The vv-exec statistics fixture is exactly what the independent reference script produces, and
the reference agrees with the separately written M10 statistics (scripts/m10_stats.py)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m10_stats  # noqa: E402
import m12_stats_reference as ref  # noqa: E402


class StatsReferenceTest(unittest.TestCase):
    def test_fixture_is_the_output_of_the_reference_script(self) -> None:
        stored = ref.FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(stored, ref.render(), "run: python scripts/m12_stats_reference.py")

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
