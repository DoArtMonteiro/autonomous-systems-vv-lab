"""Runs the Node unit tests of the Studio's requirement and safety wording.

The tests are in tests/ui_requirements.test.mjs; they need Node (the Studio's build already does).
Without Node the test is skipped and says so.
"""

import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class UiRequirements(unittest.TestCase):
    def test_node_unit_tests(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        out = subprocess.run([node, os.path.join(HERE, "ui_requirements.test.mjs")], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-1500:])
        self.assertIn("tests passed", out.stdout)


if __name__ == "__main__":
    unittest.main()
