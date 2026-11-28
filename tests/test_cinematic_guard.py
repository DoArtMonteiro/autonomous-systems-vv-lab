"""The Cinematic View's development guard: the repository project has the development name, only packaging
stamps the release name (and leaves the guard out), and the first autoload refuses a development project
that has no valid launch token or whose user data folder is unsafe.

The structural development name is the real protection: Godot may create its log and caches before any
script runs. The autoload is defence in depth, and protects against accidental misuse only.

The decision of guard.gd is exercised with Godot when VV_GODOT names a Godot 4.7.2 console executable,
always through godot_launch (scratch user data); without it those tests are skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop" / "studio" / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "cinematic"))

import godot_launch as gl  # noqa: E402
import package_module as pm  # noqa: E402
import studio_launch as sl  # noqa: E402

PROJECT = ROOT / "desktop" / "cinematic"
# SHA-256 of desktop/cinematic/project.godot as released up to 0.2.8 (before the development name), in its
# repository form (LF line endings). The packaged project.godot must be byte-identical to it.
RELEASE_PROJECT_GODOT_SHA256 = "cee77b2e4d7b002c0bdce8b8dbccde332f3a48a9d6f95b522bfa6b2e73a3a0e8"
HARNESS = ROOT / "tests" / "fixtures" / "cinematic" / "guard_cases.gd"


def setting(text: str, key: str) -> str:
    m = re.search(rf'^{re.escape(key)}="([^"]*)"$', text, re.M)
    assert m, key
    return m.group(1)


class DevelopmentProject(unittest.TestCase):
    def setUp(self):
        self.text = (PROJECT / "project.godot").read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_the_repository_project_has_the_development_name(self):
        self.assertEqual(setting(self.text, "config/custom_user_dir_name"), "VV Lab Cinematic Dev")
        self.assertEqual(setting(self.text, "config/name"), "VV Lab Cinematic Dev")
        self.assertNotEqual(setting(self.text, "config/custom_user_dir_name"), pm.RELEASE_USER_DIR)
        self.assertEqual(pm.DEV_NAME, "VV Lab Cinematic Dev")
        self.assertEqual(gl.CINEMATIC_DEV_NAME, pm.DEV_NAME)
        self.assertEqual(gl.CINEMATIC_APP_NAME, pm.RELEASE_USER_DIR)

    def test_the_development_folder_is_not_inside_the_release_folder(self):
        # "VV Lab Cinematic Dev" starts with the release name as text: the checks compare whole path components.
        self.assertTrue(pm.DEV_NAME.startswith(pm.RELEASE_USER_DIR))
        self.assertFalse(sl.is_under(rf"C:\u\AppData\Roaming\{pm.DEV_NAME}", rf"C:\u\AppData\Roaming\{pm.RELEASE_USER_DIR}"))

    def test_the_guard_is_the_first_autoload(self):
        section = self.text[self.text.index("[autoload]"):]
        entries = re.findall(r'^(\w+)="([^"]+)"$', section.split("\n\n")[1], re.M)
        self.assertEqual(entries, [("RuntimeGuard", "*res://scripts/guard.gd")])
        self.assertLess(self.text.index("[autoload]"), self.text.index("[display]"))
        self.assertTrue((PROJECT / "scripts" / "guard.gd").is_file())

    def test_guard_gd_names_the_release_folder_the_package_stamps(self):
        gd = (PROJECT / "scripts" / "guard.gd").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'const RELEASE_NAME := "([^"]*)"', gd).group(1), pm.RELEASE_USER_DIR)
        self.assertIn("const REFUSED_EXIT := 78", gd)
        self.assertIn("get_tree().quit(REFUSED_EXIT)", gd)


class Packaging(unittest.TestCase):
    def test_the_packaged_project_godot_is_byte_identical_to_the_release_one(self):
        data = (PROJECT / "project.godot").read_bytes()
        out = pm.release_project_godot(data)
        self.assertEqual(hashlib.sha256(out.replace(b"\r\n", b"\n")).hexdigest(), RELEASE_PROJECT_GODOT_SHA256)
        self.assertNotIn(b"Dev", out)
        self.assertNotIn(b"RuntimeGuard", out)
        # Line endings are the working tree's: stamping does not change them.
        self.assertEqual(b"\r\n" in out, b"\r\n" in data)

    def test_stage_project_ships_release_names_and_no_guard(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pm, "PROJECT_DIRS", ("scripts", "shaders")):
            proj = Path(d) / "project"
            pm.stage_project(str(proj))
            shipped = (proj / "project.godot").read_bytes()
            self.assertEqual(hashlib.sha256(shipped.replace(b"\r\n", b"\n")).hexdigest(), RELEASE_PROJECT_GODOT_SHA256)
            self.assertFalse((proj / "scripts" / "guard.gd").exists())
            repo_scripts = sorted(p.name for p in (PROJECT / "scripts").glob("*.gd") if p.name != "guard.gd")
            self.assertEqual(sorted(p.name for p in (proj / "scripts").glob("*.gd")), repo_scripts)
            for name in repo_scripts:
                self.assertEqual((proj / "scripts" / name).read_bytes(), (PROJECT / "scripts" / name).read_bytes(), name)
            self.assertEqual((proj / "main.tscn").read_bytes(), (PROJECT / "main.tscn").read_bytes())

    def test_a_project_that_is_not_the_expected_development_one_is_refused(self):
        good = (PROJECT / "project.godot").read_bytes().replace(b"\r\n", b"\n")
        for bad in (
            good.replace(b'config/custom_user_dir_name="VV Lab Cinematic Dev"', b'config/custom_user_dir_name="Other"'),
            good.replace(b'RuntimeGuard="*res://scripts/guard.gd"\n\n', b""),
            good.replace(b"[autoload]", b"[autoload]\n\nExtra=\"*res://x.gd\""),
            good + b'config/name="VV Lab Cinematic Dev"\n',
            good.replace(b'config/name="VV Lab Cinematic Dev"', b'config/name="VV Lab Cinematic View"'),
        ):
            with self.subTest(bad=bad[:0]):
                with self.assertRaises(SystemExit):
                    pm.release_project_godot(bad)

    def test_only_packaging_stamps_the_release_name(self):
        # No other script in the repository writes the release folder name into a project.godot.
        hits = []
        for folder in ("scripts", "tests", "desktop/studio/tests"):
            for path in (ROOT / folder).rglob("*.py"):
                if path.name in ("package_module.py", "test_cinematic_guard.py", "test_studio_isolation.py", "godot_launch.py", "studio_launch.py"):
                    continue
                if "custom_user_dir_name" in path.read_text(encoding="utf-8", errors="replace"):
                    hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_the_licence_dump_during_packaging_runs_through_the_helper(self):
        text = (ROOT / "scripts" / "cinematic" / "package_module.py").read_text(encoding="utf-8")
        self.assertIn("godot_launch.run(", text)
        self.assertNotIn("subprocess.run(", text)


@unittest.skipUnless(os.environ.get("VV_GODOT") and os.path.isfile(os.environ.get("VV_GODOT", "")), "VV_GODOT is not set to a Godot 4.7.2 console executable")
class GuardDecisionInGodot(unittest.TestCase):
    """guard.gd's pure decision, run by Godot (headless) with scratch user data."""

    def decide(self, cases):
        with tempfile.TemporaryDirectory(prefix="vv-guard-cases-") as d:
            cases_file = Path(d) / "cases.json"
            cases_file.write_text(json.dumps(cases), encoding="utf-8")
            out = gl.run([os.environ["VV_GODOT"], "--headless", "--path", str(PROJECT), "-s", str(HARNESS), "--", str(cases_file)],
                         capture_output=True, text=True, timeout=180, encoding="utf-8", errors="replace")
        line = next((x for x in out.stdout.splitlines() if x.startswith("GUARD_RESULTS=")), None)
        self.assertIsNotNone(line, out.stdout[-500:] + out.stderr[-500:])
        return json.loads(line.split("=", 1)[1])

    def test_decisions(self):
        with tempfile.TemporaryDirectory(prefix="vv-guard-tokens-") as d:
            token_dir = Path(d) / "launch"
            user = token_dir / "appdata" / "VV Lab Cinematic Dev"
            user.mkdir(parents=True)
            decoy = Path(d) / "elsewhere" / "VV Lab Cinematic Dev"
            decoy.mkdir(parents=True)

            def token(**over):
                body = {"nonce": "abc", "token_dir": str(token_dir), "paths": {}, "protected": [r"C:\FakeUser\AppData\Roaming\VV Lab Cinematic"]}
                body.update(over)
                path = Path(d) / f"t{len(list(Path(d).glob('t*.json')))}.json"
                path.write_text(json.dumps(body), encoding="utf-8")
                return str(path)

            good = token()
            bad_json = Path(d) / "broken.json"
            bad_json.write_text("not json", encoding="utf-8")
            dev, rel = "VV Lab Cinematic Dev", "VV Lab Cinematic"
            cases = [
                {"name": rel, "token": "", "nonce": "", "user": "C:/anything"},  # 0: the release name skips the guard
                {"name": dev, "token": good, "nonce": "abc", "user": str(user)},  # 1: valid
                {"name": dev, "token": "", "nonce": "", "user": str(user)},  # 2: no token
                {"name": dev, "token": good, "nonce": "", "user": str(user)},  # 3: no nonce
                {"name": dev, "token": good, "nonce": "wrong", "user": str(user)},  # 4: wrong nonce
                {"name": dev, "token": str(Path(d) / "missing.json"), "nonce": "abc", "user": str(user)},  # 5: no file
                {"name": dev, "token": str(bad_json), "nonce": "abc", "user": str(user)},  # 6: not JSON
                {"name": dev, "token": good, "nonce": "abc", "user": str(decoy)},  # 7: user dir outside the token directory
                {"name": dev, "token": token(protected=[str(token_dir / "appdata")]), "nonce": "abc", "user": str(user)},  # 8: inside installed data
                {"name": dev, "token": token(protected=[str(user / "deeper")]), "nonce": "abc", "user": str(user)},  # 9: contains installed data
                {"name": dev, "token": token(token_dir="//localhost/c$/x"), "nonce": "abc", "user": str(user)},  # 10: network token dir
                {"name": dev, "token": token(token_dir=""), "nonce": "abc", "user": str(user)},  # 11: no token dir
                {"name": dev, "token": good, "nonce": "abc", "user": str(user).upper()},  # 12: case differences are not an escape
                {"name": dev, "token": good, "nonce": "abc", "user": str(token_dir) + "-other"},  # 13: sibling with the same prefix
                {"name": dev, "token": token(protected="x"), "nonce": "abc", "user": str(user)},  # 14: protected list malformed
            ]
            out = self.decide(cases)
        self.assertEqual(out[0], "")
        self.assertEqual(out[1], "")
        for i in range(2, 12):
            self.assertNotEqual(out[i], "", f"case {i} was allowed")
        self.assertEqual(out[12], "")
        self.assertNotEqual(out[13], "")
        self.assertNotEqual(out[14], "")


if __name__ == "__main__":
    unittest.main()
