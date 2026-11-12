"""Two rules of the Cinematic View that are otherwise only visible on screen, read headless with --policy-dump:

- the automatic graphics profile for a given video memory (--vram-bytes): Performance below 4 GB,
  Balanced from 4 GB, High from 8 GB and never Ultra, whatever the capacity (Ultra measured above the
  16.7 ms frame budget; it is chosen by hand only);
- the line that presentation mode keeps on screen: it says the picture is an illustration and carries
  the record's own outcome label ("Recorded outcome: <label>").

Needs Godot 4.7.2: set VV_GODOT to the console executable; without it the tests are skipped.
"""

import json
import os
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")
FIXTURES = os.path.join(REPO, "tests", "fixtures", "cinematic")


class Policy(unittest.TestCase):
    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")

    def dump(self, run, *extra):
        out = subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", os.path.join(FIXTURES, run), "--policy-dump", *extra],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        lines = [x for x in out.stdout.splitlines() if x.startswith("POLICY ")]
        self.assertEqual(len(lines), 1, out.stdout[-500:])
        return json.loads(lines[0][len("POLICY "):])

    def test_automatic_profile_by_video_memory(self):
        cases = [(3_000_000_000, "performance"), (4_000_000_000, "balanced"), (6_000_000_000, "balanced"),
                 (8_000_000_000, "high"), (12_868_124_672, "high"), (24_000_000_000, "high"), (64_000_000_000, "high")]
        for vram, want in cases:
            p = self.dump("landing-run", "--vram-bytes", str(vram))
            self.assertEqual(p["vram_bytes"], vram)
            self.assertEqual(p["auto"]["profile"], want, f"{vram} bytes: {p['auto']}")
            self.assertNotEqual(p["auto"]["profile"], "ultra")

    def test_the_capacity_read_from_the_machine_never_gives_ultra(self):
        # Without --vram-bytes the capacity comes from the machine; whatever it is, never Ultra.
        p = self.dump("landing-run")
        self.assertIn(p["auto"]["profile"], ("performance", "balanced", "high"))

    def test_presentation_line_carries_the_recorded_outcome(self):
        for run in ("landing-run", "ascent-run"):
            with open(os.path.join(FIXTURES, run, "record.json"), encoding="utf-8") as f:
                label = json.load(f)["outcome"]["label"]
            line = self.dump(run)["presentation_line"]
            self.assertIn("Illustrative replay of a recorded run", line)
            self.assertIn(f"Recorded outcome: {label}", line)


if __name__ == "__main__":
    unittest.main()
