"""Command-line refusals of the Cinematic View (exit code 2) for the presentation and camera-pose options.

Needs Godot 4.7.2: set VV_GODOT to the console executable; without it the tests are skipped.
"""

import json
import os
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")
RUN = os.path.join(REPO, "tests", "fixtures", "cinematic", "landing-run")


class CameraPoseArguments(unittest.TestCase):
    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")

    def refused(self, *extra):
        out = subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--pose-dump", "1", *extra],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 2, out.stderr[-500:])

    def test_wrong_count(self):
        self.refused("--camera-pose", "1,2,3")

    def test_not_numbers(self):
        self.refused("--camera-pose", "1,2,3,4,5,6,x")

    def test_fov_out_of_range(self):
        self.refused("--camera-pose", "1,2,3,4,5,6,300")

    def test_values_that_are_not_finite_or_are_unbounded(self):
        self.refused("--camera-pose", "inf,2,3,4,5,6,40")
        self.refused("--camera-pose", "nan,2,3,4,5,6,40")
        self.refused("--camera-pose", "1,2,3,4,5,1e9,40")
        self.refused("--camera-pose", "1,2,3,4,5,-1e8,40")

    def test_eye_equal_to_target(self):
        self.refused("--camera-pose", "1,2,3,1,2,3,40")

    def test_a_later_bad_occurrence_is_refused_after_a_good_one(self):
        self.refused("--camera-pose", "1,2,3,4,5,6,40", "--camera-pose", "1,2,3,1,2,3,40")

    def test_usage_names_the_low_camera(self):
        out = subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--bogus"],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 2)
        self.assertIn("lowwide", out.stderr + out.stdout)


class DisplayArguments(unittest.TestCase):
    """--run-label, --vehicle, --exploratory and --seed are text for the screen; bad values are refused."""

    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")

    def run_with(self, *extra):
        return subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--pose-dump", "1", *extra],
                              capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")

    def test_good_values_are_accepted(self):
        out = self.run_with("--run-label", "Engine thrust 0.7 ×", "--vehicle", "Heavy return stage", "--exploratory", "--seed", "5000")
        self.assertEqual(out.returncode, 0, out.stderr[-500:])

    def test_a_value_that_looks_like_an_option_is_text_not_an_option(self):
        out = self.run_with("--run-label", "--shot", "--vehicle", "--bench")
        self.assertEqual(out.returncode, 0, out.stderr[-500:])

    def test_too_long_text_is_refused(self):
        self.assertEqual(self.run_with("--run-label", "x" * 101).returncode, 2)
        self.assertEqual(self.run_with("--vehicle", "").returncode, 2)

    def test_control_characters_are_refused(self):
        self.assertEqual(self.run_with("--vehicle", "a	b").returncode, 2)

    def test_the_largest_seed_is_accepted_and_bidi_overrides_are_removed_not_refused(self):
        self.assertEqual(self.run_with("--seed", "9" * 18).returncode, 0)
        out = subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--policy-dump", "--run-label", "a\u202eb\u2066c", "--vehicle", "x\u202ey", "--conditions", "GPS noise 1 mm \u202e\u00b7 radius", "--seed", "42"],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        line = next(ln for ln in out.stdout.splitlines() if ln.startswith("POLICY "))
        shown = json.loads(line[len("POLICY "):])["display"]
        self.assertEqual(shown["run_label"], "abc")
        self.assertEqual(shown["vehicle"], "xy")
        self.assertEqual(shown["seed"], 42)
        self.assertEqual(shown["conditions"], "GPS noise 1 mm \u00b7 radius")

    def test_conditions_are_text_up_to_200_characters(self):
        self.assertEqual(self.run_with("--conditions", "x" * 200).returncode, 0)
        self.assertEqual(self.run_with("--conditions", "x" * 201).returncode, 2)
        self.assertEqual(self.run_with("--conditions", "a	b").returncode, 2)

    def policy(self, *extra):
        out = subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--policy-dump", *extra],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        line = next(ln for ln in out.stdout.splitlines() if ln.startswith("POLICY "))
        return json.loads(line[len("POLICY "):])

    def test_every_run_line_carries_the_exploratory_qualifier_and_the_conditions(self):
        qualifier = "idealised model, not a real vehicle"
        # Whatever the vehicle and whether or not the Studio says the case is exploratory (no --exploratory here).
        shown = self.policy("--run-label", "Engine thrust 0.7 x", "--vehicle", "22 t landing stage", "--conditions", "GNSS bias 9.72 m", "--seed", "5017")["run_line"]
        self.assertIn("22 t landing stage (" + qualifier + ")", shown)
        self.assertIn("  |  exploratory", shown)
        self.assertIn("conditions: GNSS bias 9.72 m", shown)
        self.assertIn("seed 5017", shown)
        bare = self.policy()["run_line"]
        self.assertIn(qualifier, bare)
        self.assertTrue(bare.endswith("exploratory") or "  |  exploratory" in bare, bare)
        self.assertNotIn("conditions:", bare)
        # With the flag too, the qualifier is the same single one.
        flagged = self.policy("--vehicle", "x", "--exploratory")["run_line"]
        self.assertEqual(flagged.count("exploratory"), 1 + flagged.count("exploratory,"), flagged)

    def test_the_result_panel_says_exploratory_and_that_the_impact_is_not_modelled(self):
        d = self.policy()
        self.assertIn("Exploratory: an idealised model, not a real vehicle, not validated against flight data.", d["verdict"])
        self.assertIn("Impact is not modelled: the stage is drawn intact whatever the contact speed.", d["verdict"])
        self.assertIn("Safety rules:", d["verdict"])
        self.assertNotIn("Safety: ", d["verdict"])

    def test_the_place_is_a_backdrop_and_the_pack_terrain_is_not_recorded_data(self):
        d = self.policy()
        self.assertTrue(d["title"].endswith("Place name (backdrop only)"), d["title"])
        self.assertNotIn("terrain", d["legend_data"].lower())
        self.assertNotIn("environment pack", d["legend_data"])
        self.assertIn("Backdrop only", d["legend_illustrative"])
        self.assertIn("terrain", d["legend_illustrative"])

    def test_the_seed_is_a_non_negative_integer(self):
        self.assertEqual(self.run_with("--seed", "-1").returncode, 2)
        self.assertEqual(self.run_with("--seed", "five").returncode, 2)
        self.assertEqual(self.run_with("--seed", "1" * 19).returncode, 2)


if __name__ == "__main__":
    unittest.main()
