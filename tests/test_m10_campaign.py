"""M10 campaign script: evaluation-seed refusal, freeze check, fault draws and statistics."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import m10_campaign as m10  # noqa: E402


def run_main(argv: list[str]) -> tuple[int, str]:
    err = io.StringIO()
    with redirect_stderr(err):
        code = m10.main(argv)
    return code, err.getvalue()


class SeedProtection(unittest.TestCase):
    def test_evaluation_and_reserve_seeds_are_refused_before_any_simulator_call(self) -> None:
        # The binary does not exist: a refusal that came after the simulator would say so instead.
        missing = str(Path(__file__).parent / "no-such-binary")
        for seeds in ("3000", "3099", "6000", "5098-5099,3050"):
            code, err = run_main(["--seeds", seeds, "--binary", missing])
            self.assertEqual(code, 1, seeds)
            self.assertIn("evaluation seeds refused", err)
            self.assertNotIn("binary does not exist", err)

    def test_evaluation_flag_without_a_freeze_manifest_is_refused(self) -> None:
        self.assertFalse(m10.FREEZE.exists(), "the freeze manifest belongs to the owner gate")
        code, err = run_main(["--seeds", "3000", "--evaluation", "--binary", "nothing"])
        self.assertEqual(code, 1)
        self.assertIn("no freeze manifest", err)

    def test_development_and_test_seeds_pass_the_guard(self) -> None:
        self.assertIsNone(m10.guard_seeds(m10.DEV_SEEDS, evaluation=False))
        self.assertIsNone(m10.guard_seeds(m10.TEST_SEEDS, evaluation=False))


class Draws(unittest.TestCase):
    def test_new_faults_are_deterministic_and_inside_their_ranges(self) -> None:
        for name, spec in m10.NEW_FAULTS.items():
            for seed in range(5000, 5040):
                a = m10.sample_new_fault(name, seed)
                self.assertEqual(a, m10.sample_new_fault(name, seed))
                bounds = spec["magnitude"]
                if bounds is None:
                    self.assertEqual(a["magnitude"], 0.0)
                    self.assertTrue(1.0 - 1e-9 <= a["end_s"] - a["start_s"] <= 10.0 + 1e-9)
                else:
                    self.assertTrue(bounds[0] <= a["magnitude"] <= bounds[1])
                self.assertTrue(0.0 <= a["start_s"] < a["end_s"] <= 40.0)

    def test_pairs_overlap_and_signed_biases_take_both_signs(self) -> None:
        kinds = set()
        for seed in range(5000, 5100):
            faults = m10.faults_for("pair_altimeter_bias±+gnss_bias±", seed)
            self.assertEqual(len(faults), 2)
            kinds.add(faults[0]["kind"])
            start = max(f["start_s"] for f in faults)
            end = min(f["end_s"] for f in faults)
            self.assertGreaterEqual(end - start, 1.0)
        self.assertEqual(kinds, {"altimeter_bias", "altimeter_bias_low"})

    def test_every_arm_gets_the_same_case_except_the_policy(self) -> None:
        template, _ = m10.load_template()
        a = m10.build_case(template, m10.RunSpec("altimeter_bias", "guarded", 5001))
        b = m10.build_case(template, m10.RunSpec("altimeter_bias", "m10_b_plus", 5001))
        self.assertEqual(a["faults"], b["faults"])
        a["controller"]["policy"] = b["controller"]["policy"]
        a["name"] = b["name"]
        self.assertEqual(a, b)


class Statistics(unittest.TestCase):
    def test_clopper_pearson_matches_known_values(self) -> None:
        self.assertEqual(m10.clopper_pearson(0, 100)[0], 0.0)
        self.assertAlmostEqual(m10.clopper_pearson(0, 100)[1], 0.0362, places=4)
        low, _ = m10.clopper_pearson(88, 100)
        self.assertAlmostEqual(low, 0.7998, places=3)
        self.assertEqual(m10.clopper_pearson(100, 100)[1], 1.0)

    def test_physical_class_follows_the_true_requirements_only(self) -> None:
        base = {"outcome": "landed", "invariants": {"S1": True},
                "requirements": {k: True for k in ("R1", "R2", "R3", "R4", "R5", "R6")}}
        self.assertEqual(m10.physical_class(base), "R")
        off_pad = dict(base, requirements=dict(base["requirements"], R5=False))
        self.assertEqual(m10.physical_class(off_pad), "T")
        hard = dict(base, requirements=dict(base["requirements"], R1=False))
        self.assertEqual(m10.physical_class(hard), "U")
        self.assertEqual(m10.physical_class(dict(base, outcome="no_contact")), "U")


if __name__ == "__main__":
    unittest.main()
