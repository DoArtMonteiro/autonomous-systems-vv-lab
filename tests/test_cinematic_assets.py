"""The authored stage of the Cinematic View sits where the record's pose puts it.

The pose-parity test exits before the stage is built, so a flipped or offset model would pass it.
This one builds the stage as the renderer does (headless, tools/stage_probe.gd) and checks the
bounding box of its solid meshes in the vehicle's local frame: the body axis is +x, the nozzle exit
plane is x = 0 and the top of the interstage is at x = 42 m (stage-model.js), centred on the axis.

Also checks that the shipped assets are loadable raw files (no import cache is needed or shipped) and
that the module's install limits (desktop/studio/src/modules.rs: 512 files, 512 MiB per file, 1 GiB)
hold for the project directory. Needs Godot 4.7.2: set VV_GODOT; without it the Godot tests are skipped.
"""

import json
import os
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")


class StageAssets(unittest.TestCase):
    def test_install_limits_for_the_project_directory(self):
        files = 0
        total = 0
        biggest = 0
        for dirpath, _, names in os.walk(PROJECT):
            if ".godot" in dirpath.split(os.sep) or "assets-src" in dirpath.split(os.sep):
                continue
            for n in names:
                if n.endswith(".import") or n.endswith(".uid"):
                    continue
                size = os.path.getsize(os.path.join(dirpath, n))
                files += 1
                total += size
                biggest = max(biggest, size)
        # The module adds the Godot binaries (about 181 MB, 4 files) and licences (about 4 files).
        self.assertLess(files + 10, 512)
        self.assertLess(biggest, 512 * 2 ** 20)
        self.assertLess(total + 200 * 10 ** 6, 2 ** 30)

    def test_stage_bounding_box(self):
        godot = os.environ.get("VV_GODOT", "")
        if not godot or not os.path.isfile(godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")
        out = subprocess.run([godot, "--headless", "--path", PROJECT, "-s", "res://tools/stage_probe.gd"],
                             capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace")
        line = [l for l in out.stdout.splitlines() if l.startswith("STAGE ")]
        self.assertTrue(line, out.stdout[-1000:] + out.stderr[-1000:])
        d = json.loads(line[0][6:])
        self.assertTrue(d["model"], "assets/stage.glb did not load")
        self.assertGreaterEqual(d["meshes"], 5)
        lo, hi = d["min"], d["max"]
        # Body axis +x from the exit plane: nothing below x = 0, top at 42 m (tolerance 0.2 m for the cap detail).
        self.assertAlmostEqual(lo[0], 0.0, delta=0.05)
        self.assertAlmostEqual(hi[0], 42.0, delta=0.2)
        # Centred on the axis: radius 1.85 m plus fins (about 2.6 m) and legs (about 2.4 m), no offset.
        for k in (1, 2):
            self.assertLess(abs(lo[k] + hi[k]), 0.1)
            self.assertLess(hi[k], 2.8)
            self.assertGreater(hi[k], 1.8)


if __name__ == "__main__":
    unittest.main()
