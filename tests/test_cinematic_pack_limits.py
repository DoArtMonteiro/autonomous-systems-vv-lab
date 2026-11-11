"""Malformed environment packs are refused by the Cinematic View with exit code 4, never a script error.

Each case edits a copy of a real pack (and, where needed, keeps the manifest's size and SHA-256 of
the edited file consistent so that the check under test is the one that fires). Needs Godot 4.7.2:
set VV_GODOT to the console executable; without it the tests are skipped.
"""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT = os.path.join(REPO, "desktop", "cinematic")
RUN = os.path.join(REPO, "tests", "fixtures", "cinematic", "landing-run")
PACK = os.path.join(REPO, "desktop", "environments", "spaceport-america")


def sof_jpeg(width, height):
    """A JPEG that is only a header declaring width x height (no scan data)."""
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + bytes([1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
    return b"\xff\xd8" + sof + b"\xff\xd9"


class PackLimits(unittest.TestCase):
    def setUp(self):
        self.godot = os.environ.get("VV_GODOT", "")
        if not self.godot or not os.path.isfile(self.godot):
            self.skipTest("VV_GODOT is not set to a Godot 4.7.2 console executable")

    def run_pack(self, edit):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "pack")
            shutil.copytree(PACK, dst)
            mp = os.path.join(dst, "environment.json")
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            edit(m, dst)
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(m, f)
            return subprocess.run([self.godot, "--headless", "--path", PROJECT, "--", "--run", RUN, "--env", dst],
                                  capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace")

    def refused(self, out, needle):
        self.assertEqual(out.returncode, 4, out.stderr[-1500:])
        self.assertIn(needle, out.stderr)
        self.assertNotIn("SCRIPT ERROR", out.stderr)

    def test_height_field_of_the_wrong_type(self):
        out = self.run_pack(lambda m, d: m.update({"height": "x"}))
        self.refused(out, "field height is not an object")

    def test_first_node_of_the_wrong_type(self):
        out = self.run_pack(lambda m, d: m["height"].update({"first_node_m": "x"}))
        self.refused(out, "first_node_m")

    def test_non_numeric_columns(self):
        out = self.run_pack(lambda m, d: m["height"].update({"columns": {"a": 1}}))
        self.refused(out, "declared size")

    def test_image_larger_than_the_limit(self):
        def edit(m, d):
            data = sof_jpeg(20000, 20000)
            with open(os.path.join(d, "image.jpg"), "wb") as f:
                f.write(data)
            m["image"].update({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        self.refused(self.run_pack(edit), "pixels (accepted: 1 to 16384 per side)")


if __name__ == "__main__":
    unittest.main()
