"""The M10 adversarial probe refuses every non-development seed and keeps its registered plans."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m10_adversarial_probe as probe  # noqa: E402


class AdversarialProbeTest(unittest.TestCase):
    def test_only_development_seeds_5000_to_5099_are_accepted(self) -> None:
        probe.guard([5000, 5050, 5099])
        for bad in ([3000], [6000], [100], [129], [4999], [5100], [5000, 3050]):
            with self.assertRaises(SystemExit, msg=bad):
                probe.guard(bad)

    def test_plan_sizes_match_the_review(self) -> None:
        sizes = {p: len(probe.jobs_for(p)) * 20 for p in probe.PLANS}
        self.assertEqual(sizes, {"ignition": 5100, "ramp": 500, "rampbase": 640, "steps": 1680, "chase": 1680})
        self.assertTrue(all(n <= probe.MAX_PLAN for n in sizes.values()))


if __name__ == "__main__":
    unittest.main()
