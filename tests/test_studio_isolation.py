"""Isolation of the Studio's development builds and UI tests from the installed application's profile.

Nothing here starts the Studio. The launch rules are tested with invented profile folders (never the
real ones), the build rules by reading the configuration files and `desktop/build.ps1`, and the
launch discipline of the UI test scripts by reading their syntax trees.

Background: docs/incidents/2026-11-23-webview2-profile.md.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "desktop" / "studio"
STUDIO_TESTS = STUDIO / "tests"
sys.path.insert(0, str(STUDIO_TESTS))

import studio_launch as sl  # noqa: E402

RELEASE = "org.vvlab.studio"
DEV = "org.vvlab.devstudio"

# Invented folders. Nothing below creates or touches them.
LOCAL = r"C:\FakeUser\AppData\Local"
ROAM = r"C:\FakeUser\AppData\Roaming"
DOCS = r"C:\FakeUser\Documents"
EXE = r"D:\build\desktop\target\debug\vv-studio.exe"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fake_scratch(name: str) -> str:
    return rf"C:\FakeScratch\{name.lower()}"


def plan(environ=None, exe=EXE, ids=(DEV,), **kw):
    return sl.plan_launch(
        exe, environ if environ is not None else {}, LOCAL, ROAM,
        documents=DOCS, identifier_reader=lambda _exe: set(ids), make_scratch=fake_scratch, **kw,
    )


class IdentityConfig(unittest.TestCase):
    def test_base_identifier_is_the_development_one(self):
        base = read_json(STUDIO / "tauri.conf.json")
        self.assertEqual(base["identifier"], DEV)
        self.assertEqual(sl.DEV_IDENTIFIER, DEV)

    def test_base_identifier_is_not_the_release_one_nor_an_extension_of_it(self):
        ident = read_json(STUDIO / "tauri.conf.json")["identifier"]
        self.assertNotEqual(ident, RELEASE)
        self.assertFalse(ident.startswith(RELEASE), "a dev identifier that extends the release one contains it")
        self.assertNotIn(RELEASE, ident)
        self.assertFalse(RELEASE.startswith(ident))

    def test_overlay_is_the_release_identity(self):
        overlay = read_json(STUDIO / "tauri.release.conf.json")
        self.assertEqual(overlay["identifier"], RELEASE)
        self.assertEqual(sl.RELEASE_IDENTIFIER, RELEASE)
        self.assertEqual(overlay["productName"], "VV Lab Studio")
        self.assertNotEqual(read_json(STUDIO / "tauri.conf.json")["productName"], overlay["productName"])

    def test_overlay_changes_nothing_else(self):
        overlay = read_json(STUDIO / "tauri.release.conf.json")
        self.assertEqual(set(overlay) - {"$schema"}, {"identifier", "productName"})

    def test_no_rust_source_hardcodes_either_identifier(self):
        # The compiled-in identifier must come from the configuration only; a literal in the code would
        # make every executable carry both identifiers and defeat the check on the executable.
        for path in list((STUDIO / "src").rglob("*.rs")) + [STUDIO / "build.rs"]:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("org.vvlab", text, str(path))

    def test_no_other_config_in_the_studio_folder_names_the_release_identifier(self):
        for path in STUDIO.glob("*.json"):
            if path.name in ("tauri.release.conf.json", "package-lock.json"):
                continue
            self.assertNotIn(RELEASE, path.read_text(encoding="utf-8").replace(DEV, ""), path.name)


class BuildScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "desktop" / "build.ps1").read_text(encoding="utf-8")

    def test_identifiers_match_the_helper(self):
        self.assertIn(f'$DevIdentifier = "{DEV}"', self.text)
        self.assertIn(f'$ReleaseIdentifier = "{RELEASE}"', self.text)

    def test_overlay_is_applied_only_under_release(self):
        self.assertIn("[switch]$Release", self.text)
        self.assertEqual(self.text.count('Join-Path $studio "tauri.release.conf.json"'), 1)
        self.assertEqual(self.text.count("$releaseConfig"), 3)  # the definition, the identity check, the --config argument
        self.assertEqual(len(re.findall(r'"--config"', self.text)), 1)
        m = re.search(r"if \(\$Release\) \{(?P<yes>.*?)\n\} else \{(?P<no>.*?)\n\}", self.text, re.S)
        self.assertIsNotNone(m, "the tauri invocation must be split on $Release")
        self.assertIn('"--config", $releaseConfig', m["yes"])
        self.assertNotIn("--config", m["no"])
        self.assertNotIn("$releaseConfig", m["no"])
        self.assertIn("--no-bundle", m["no"], "a development build must not produce an installer")

    def test_identifier_is_asserted_before_and_after_the_build(self):
        self.assertIn("$wanted = if ($Release) { $ReleaseIdentifier } else { $DevIdentifier }", self.text)
        self.assertRegex(self.text, r"\$mergedIdentifier -cne \$wanted\) \{ throw")
        self.assertRegex(self.text, r"\$embedded\[0\] -cne \$wanted\) \{ throw")
        first = self.text.index("$mergedIdentifier -cne $wanted")
        build = self.text.index('Run "node"')
        after = self.text.index("$embedded[0] -cne $wanted")
        self.assertLess(first, build)
        self.assertLess(build, after)

    def test_ambient_tauri_config_is_refused(self):
        self.assertRegex(self.text, r"if \(\$env:TAURI_CONFIG\) \{ throw")

    def test_the_ci_installer_job_builds_with_release_and_declares_the_owner_flag_on_the_installed_exe(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("desktop/build.ps1 -Release", ci)
        for line in ci.splitlines():
            if "desktop/studio/tests/" in line and r"VV Lab Studio\vv-studio.exe" in line:
                self.assertIn(sl.OWNER_FLAG, line)


class NormalisationAndEmbeddedIdentifier(unittest.TestCase):
    def test_variants_of_one_path_compare_equal(self):
        base = sl.normalise(rf"{LOCAL}\{RELEASE}\EBWebView")
        for variant in (
            rf"{LOCAL.lower()}\{RELEASE.upper()}\ebwebview\\",
            rf"{LOCAL}/{RELEASE}/EBWebView/",
            rf"{LOCAL}\Temp\..\{RELEASE}\EBWebView",
            rf"\\?\{LOCAL}\{RELEASE}\EBWebView",
            rf"{LOCAL}\{RELEASE}. \EBWebView",
        ):
            self.assertEqual(sl.normalise(variant), base, variant)

    def test_is_under_respects_component_boundaries(self):
        root = rf"{LOCAL}\{RELEASE}"
        self.assertTrue(sl.is_under(root, root))
        self.assertTrue(sl.is_under(root + "\\", root))
        self.assertTrue(sl.is_under(root + r"\EBWebView\Default", root))
        self.assertFalse(sl.is_under(rf"{LOCAL}\{RELEASE}.m191review", root))
        self.assertFalse(sl.is_under(rf"{LOCAL}\{DEV}", root))
        self.assertFalse(sl.is_under(LOCAL, root))

    def test_embedded_identifier_reader(self):
        with tempfile.TemporaryDirectory() as d:
            def read(data: bytes):
                p = Path(d) / "x.exe"
                p.write_bytes(data)
                return sl.embedded_identifiers(str(p))

            self.assertEqual(read(b"MZ\0\0" + DEV.encode() + b"\0padding"), {DEV})
            self.assertEqual(read(b"MZ\0\0" + RELEASE.encode() + b"\0"), {RELEASE})
            self.assertEqual(read(b"MZ" + RELEASE.encode("utf-16-le")), {RELEASE})
            self.assertEqual(read(b"MZ" + DEV.encode() + b"\0" + RELEASE.encode()), {DEV, RELEASE})
            self.assertEqual(read(b"MZ nothing here"), set())
        # The development identifier does not contain the release one: the reader never confuses them.
        self.assertNotIn(RELEASE, DEV)


class PlanLaunch(unittest.TestCase):
    def test_a_clean_launch_gets_scratch_for_every_folder_the_studio_writes(self):
        p = plan({"PATH": r"C:\Windows"}, port=9333)
        for name in sl.SCRATCH_VARIABLES:
            self.assertEqual(p.env[name], fake_scratch(name))
        self.assertEqual(set(p.scratch), set(sl.SCRATCH_VARIABLES))
        self.assertEqual(p.env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"], "--remote-debugging-port=9333")
        self.assertEqual(p.env["PATH"], r"C:\Windows")

    def test_the_caller_environment_is_not_modified(self):
        environ = {"PATH": "x"}
        plan(environ)
        self.assertEqual(environ, {"PATH": "x"})

    def test_safe_caller_values_are_kept(self):
        p = plan({"VVLAB_LIBRARY": r"C:\Scratch\lib", "VVLAB_CONFIG": r"C:\Scratch\cfg"})
        self.assertEqual(p.env["VVLAB_LIBRARY"], r"C:\Scratch\lib")
        self.assertEqual(p.env["VVLAB_CONFIG"], r"C:\Scratch\cfg")
        self.assertNotIn("VVLAB_LIBRARY", p.scratch)

    def test_hostile_values_are_refused_for_every_redirected_folder(self):
        hostile = [
            rf"{LOCAL}\{RELEASE}",
            rf"{LOCAL}\{RELEASE}\EBWebView",
            rf"{LOCAL}\{RELEASE}" + "\\",
            rf"{LOCAL}\{RELEASE}" + "/",
            rf"{LOCAL.lower()}\{RELEASE.upper()}\ebwebview",
            rf"{LOCAL.replace(chr(92), '/')}/{RELEASE}/EBWebView/",
            rf"{LOCAL}\Temp\..\{RELEASE}\EBWebView",
            rf"\\?\{LOCAL}\{RELEASE}\EBWebView",
            rf"{LOCAL}\{RELEASE}. \EBWebView",
            rf"{ROAM}\{RELEASE}",
            rf"{ROAM.upper()}\{RELEASE}\\",
            rf"{DOCS}\VV Lab Library",
            rf"{DOCS}\VV Lab Library\runs",
            rf"%LOCALAPPDATA%\{RELEASE}\EBWebView",
        ]
        for name in sl.SCRATCH_VARIABLES:
            for value in hostile:
                with self.subTest(variable=name, value=value):
                    with self.assertRaises(sl.IsolationError):
                        plan({name: value, "LOCALAPPDATA": LOCAL})

    def test_a_hostile_value_is_refused_even_with_the_owner_flag(self):
        with self.assertRaises(sl.IsolationError):
            plan({"WEBVIEW2_USER_DATA_FOLDER": rf"{LOCAL}\{RELEASE}\EBWebView"}, ids=(RELEASE,), allow_release=True)

    def test_any_variable_that_names_the_installed_profile_is_refused(self):
        for name, value in (
            ("TEMP", rf"{LOCAL}\{RELEASE}\tmp"),
            ("SOMETHING_ELSE", rf"C:\a;{ROAM}\{RELEASE};C:\b"),
            ("PATH", rf'"{LOCAL}\{RELEASE}\bin"'),
        ):
            with self.subTest(name=name):
                with self.assertRaises(sl.IsolationError):
                    plan({name: value})

    def test_neighbouring_names_are_not_refused(self):
        p = plan({
            "WEBVIEW2_USER_DATA_FOLDER": rf"{LOCAL}\{RELEASE}.m191review\EBWebView",
            "VVLAB_CONFIG": rf"{ROAM}\{DEV}",
            "VVLAB_LIBRARY": rf"{DOCS}\VV Lab Library2",
        })
        self.assertTrue(p.env["VVLAB_CONFIG"].endswith(DEV))

    def test_a_user_data_dir_browser_argument_is_refused(self):
        for args in (
            rf"--user-data-dir={LOCAL}\{RELEASE}\EBWebView",
            r"--remote-debugging-port=9333 --user-data-dir=C:\Scratch",
            "--USER-DATA-DIR=C:\\Scratch",
        ):
            with self.subTest(args=args):
                with self.assertRaises(sl.IsolationError):
                    plan({"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": args}, port=9333)

    def test_missing_known_folders_refuse_the_launch(self):
        with self.assertRaises(sl.IsolationError):
            sl.plan_launch(EXE, {}, "", ROAM, identifier_reader=lambda _e: {DEV}, make_scratch=fake_scratch)

    def test_the_installed_executable_is_refused_in_every_spelling(self):
        for exe in (
            rf"{LOCAL}\VV Lab Studio\vv-studio.exe",
            rf"{LOCAL.upper()}\vv lab studio\VV-STUDIO.EXE",
            rf"{LOCAL}/VV Lab Studio/vv-studio.exe",
            rf"{LOCAL}\VV Lab Studio\sub\..\vv-studio.exe",
        ):
            with self.subTest(exe=exe):
                with self.assertRaises(sl.IsolationError):
                    plan(exe=exe)

    def test_a_release_identifier_is_refused_wherever_the_executable_lives(self):
        for ids in ((RELEASE,), (RELEASE, DEV)):
            with self.subTest(ids=ids):
                with self.assertRaises(sl.IsolationError):
                    plan(ids=ids)

    def test_an_executable_of_unknown_provenance_is_refused(self):
        with self.assertRaises(sl.IsolationError):
            plan(ids=())

    def test_an_unreadable_executable_is_refused(self):
        def reader(_exe):
            raise FileNotFoundError("no such file")

        with self.assertRaises(sl.IsolationError):
            sl.plan_launch(EXE, {}, LOCAL, ROAM, identifier_reader=reader, make_scratch=fake_scratch)

    def test_the_owner_flag_lifts_only_the_executable_refusals(self):
        installed = rf"{LOCAL}\VV Lab Studio\vv-studio.exe"
        p = plan(exe=installed, ids=(RELEASE,), allow_release=True)
        self.assertEqual(p.env["WEBVIEW2_USER_DATA_FOLDER"], fake_scratch("WEBVIEW2_USER_DATA_FOLDER"))
        self.assertIsNone(p.identifiers)

    def test_a_development_executable_outside_the_install_folder_is_accepted(self):
        self.assertEqual(plan(ids=(DEV,)).identifiers, {DEV})

    def test_the_default_reader_is_the_embedded_identifier_reader(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "vv-studio.exe"
            exe.write_bytes(b"MZ" + RELEASE.encode() + b"\0")
            with self.assertRaises(sl.IsolationError):
                sl.plan_launch(str(exe), {}, LOCAL, ROAM, make_scratch=fake_scratch)
            exe.write_bytes(b"MZ" + DEV.encode() + b"\0")
            self.assertEqual(sl.plan_launch(str(exe), {}, LOCAL, ROAM, make_scratch=fake_scratch).identifiers, {DEV})


def _calls(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _dotted(node) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


SPAWNERS = {"subprocess.Popen", "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output",
            "os.system", "os.startfile", "os.popen", "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell"}


def launch_violations(source: str) -> list[str]:
    """Ways a script could start a Studio without the helper: any Popen; a spawn whose first argument
    mentions an executable variable; spawners imported under another name."""
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "os", "asyncio"):
            for alias in node.names:
                if f"{node.module}.{alias.name}" in SPAWNERS or alias.name.startswith(("spawn", "exec")):
                    found.append(f"line {node.lineno}: imports {node.module}.{alias.name} by name")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "os", "asyncio") and alias.asname:
                    found.append(f"line {node.lineno}: aliases {alias.name}")
    for call in _calls(tree):
        name = _dotted(call.func)
        if name.endswith("Popen"):
            found.append(f"line {call.lineno}: Popen outside the helper")
        elif name in SPAWNERS or re.match(r"os\.(spawn|exec)", name):
            first = call.args[0] if call.args else None
            idents = {_dotted(n).split(".")[-1].lower() for n in ast.walk(first)} if first is not None else set()
            if idents & {"exe", "studio_exe", "studio"} or name.startswith(("os.spawn", "os.exec", "os.startfile", "os.system")):
                found.append(f"line {call.lineno}: {name} of an executable outside the helper")
    return found


class LaunchDiscipline(unittest.TestCase):
    def scripts(self):
        return sorted(p for p in STUDIO_TESTS.glob("*.py") if p.name != "studio_launch.py")

    def test_the_lint_catches_what_it_is_meant_to(self):
        bad = [
            "import subprocess\nsubprocess.Popen([exe], env=env)\n",
            "import subprocess\nsubprocess.Popen([a.exe])\n",
            "import subprocess\nsubprocess.run([a.exe, '--self-test'])\n",
            "import subprocess\nsubprocess.check_output([os.path.abspath(exe)])\n",
            "from subprocess import Popen\nPopen(['x'])\n",
            "import subprocess as sp\nsp.run(['x'])\n",
            "import os\nos.startfile(exe)\n",
        ]
        for src in bad:
            with self.subTest(src=src):
                self.assertTrue(launch_violations(src), src)
        good = [
            "import subprocess\nsubprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)\n",
            "import subprocess\nsubprocess.run(['powershell', '-NoProfile', '-Command', ps])\n",
            "import subprocess\nsubprocess.run([console] + args + ['--t', '1'])\n",
            "import studio_launch\nproc = studio_launch.launch(exe, env, 1, allow_release=False)\n",
        ]
        for src in good:
            with self.subTest(src=src):
                self.assertEqual(launch_violations(src), [], src)

    def test_no_script_starts_a_studio_outside_the_helper(self):
        for path in self.scripts():
            with self.subTest(script=path.name):
                self.assertEqual(launch_violations(path.read_text(encoding="utf-8")), [])

    def test_the_helper_starts_a_process_in_one_place_and_only_after_the_plan(self):
        tree = ast.parse((STUDIO_TESTS / "studio_launch.py").read_text(encoding="utf-8"))
        spawns = [(fn, c) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
                  for c in _calls(fn) if _dotted(c.func) in SPAWNERS and _dotted(c.func) != "subprocess.run"]
        self.assertEqual([fn.name for fn, c in spawns if _dotted(c.func).endswith("Popen")], ["launch"])
        launch = next(fn for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name == "launch")
        plan_line = min(c.lineno for c in _calls(launch) if _dotted(c.func) == "plan_launch")
        popen_line = min(c.lineno for c in _calls(launch) if _dotted(c.func).endswith("Popen"))
        self.assertLess(plan_line, popen_line)
        used = [c for c in _calls(launch) if _dotted(c.func).endswith("Popen")][0]
        self.assertEqual(_dotted(used.args[0].elts[0]), "plan.exe")
        self.assertEqual([k.arg for k in used.keywords], ["env"])
        self.assertEqual(_dotted(used.keywords[0].value), "plan.env")

    def test_every_launch_passes_the_owner_flag_explicitly(self):
        count = 0
        for path in self.scripts():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in _calls(tree):
                if _dotted(call.func).split(".")[-1] == "launch" and not (
                        isinstance(call.func, ast.Attribute) and _dotted(call.func.value) not in ("studio_launch",)):
                    count += 1
                    with self.subTest(script=path.name, line=call.lineno):
                        self.assertIn("allow_release", [k.arg for k in call.keywords])
        self.assertGreaterEqual(count, 10)

    def test_every_script_that_launches_accepts_the_owner_flag(self):
        for path in self.scripts():
            text = path.read_text(encoding="utf-8")
            if re.search(r"\blaunch\(", text) and "def launch(" not in text:
                with self.subTest(script=path.name):
                    self.assertIn("studio_launch.add_arguments(ap)", text)
                    self.assertIn("a.owner_allow_release_exe", text)

    def test_no_image_name_kill_anywhere_in_the_test_scripts_or_build_tooling(self):
        files = []
        for base in (STUDIO_TESTS, ROOT / "scripts", ROOT / ".github" / "workflows", ROOT / "desktop"):
            for folder, dirs, names in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("target", "node_modules", ".git", "__pycache__")]
                files += [Path(folder) / n for n in names if n.endswith((".py", ".ps1", ".yml", ".sh", ".cmd", ".bat"))]
        self.assertTrue(files)
        forbidden = [
            (re.compile(r"(?<![\w.])/IM(?![\w])", re.I), "taskkill /IM"),
            (re.compile(r"Stop-Process", re.I), "Stop-Process"),
            (re.compile(r"\b(pkill|killall)\b"), "pkill/killall"),
            (re.compile(r"taskkill[^\n]*/FI", re.I), "taskkill /FI"),
        ]
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern, what in forbidden:
                with self.subTest(file=str(path.relative_to(ROOT)), rule=what):
                    self.assertIsNone(pattern.search(text))

    def test_every_taskkill_names_a_pid(self):
        for path in self.scripts():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in _calls(tree):
                if _dotted(call.func) == "subprocess.run" and call.args and isinstance(call.args[0], ast.List):
                    elts = call.args[0].elts
                    if elts and isinstance(elts[0], ast.Constant) and str(elts[0].value).lower() == "taskkill":
                        with self.subTest(script=path.name, line=call.lineno):
                            self.assertEqual([e.value for e in elts[1:3] if isinstance(e, ast.Constant)], ["/F", "/PID"])


if __name__ == "__main__":
    unittest.main()
