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
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "desktop" / "studio"
STUDIO_TESTS = STUDIO / "tests"
sys.path.insert(0, str(STUDIO_TESTS))

import godot_launch as gl  # noqa: E402
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
            # Test modules (`#[cfg(test)]`) are compiled into test executables only, never into vv-studio.exe.
            text = path.read_text(encoding="utf-8").split("#[cfg(test)]")[0]
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
        self.assertEqual(self.text.count("$releaseConfig"), 4)  # definition, identifier and productName checks, --config argument
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
    def test_a_clean_launch_gets_one_token_directory_with_every_folder_the_studio_writes(self):
        p = plan({"PATH": r"C:\Windows"}, port=9333)
        root = fake_scratch("TOKEN_DIR")
        self.assertEqual(p.token_dir, root)
        for name in sl.SCRATCH_VARIABLES:
            self.assertEqual(p.env[name], os.path.join(root, sl.TOKEN_SUBFOLDERS[name]))
        self.assertEqual(set(p.scratch), set(sl.SCRATCH_VARIABLES))
        self.assertEqual(p.env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"], "--remote-debugging-port=9333")
        self.assertEqual(p.env["PATH"], r"C:\Windows")
        # The launch token: a nonce the child also gets in its environment, the directory and every path.
        self.assertEqual(p.env[sl.ENV_NONCE], p.token["nonce"])
        self.assertGreaterEqual(len(p.token["nonce"]), 32)
        self.assertEqual(p.env[sl.ENV_LAUNCH], os.path.join(root, sl.TOKEN_FILE))
        self.assertEqual(p.token["token_dir"], root)
        self.assertEqual(set(p.token["paths"]), set(sl.TOKEN_SUBFOLDERS))
        for name, value in p.token["paths"].items():
            self.assertEqual(p.env[name], value)
            self.assertTrue(sl.is_under(value, root))

    def test_the_caller_environment_is_not_modified(self):
        environ = {"PATH": "x"}
        plan(environ)
        self.assertEqual(environ, {"PATH": "x"})

    def test_caller_folders_are_replaced_by_folders_in_the_token_directory(self):
        p = plan({"VVLAB_LIBRARY": r"C:\Scratch\lib", "VVLAB_CONFIG": r"C:\Scratch\cfg"})
        self.assertEqual(p.env["VVLAB_LIBRARY"], os.path.join(fake_scratch("TOKEN_DIR"), "library"))
        self.assertEqual(p.env["VVLAB_CONFIG"], os.path.join(fake_scratch("TOKEN_DIR"), "config"))

    def test_every_launch_has_its_own_nonce(self):
        self.assertNotEqual(plan().token["nonce"], plan().token["nonce"])

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
        self.assertTrue(sl.is_under(p.env["VVLAB_CONFIG"], fake_scratch("TOKEN_DIR")))

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
        self.assertEqual(p.env["WEBVIEW2_USER_DATA_FOLDER"], os.path.join(fake_scratch("TOKEN_DIR"), "webview2"))
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


GODOT = r"D:\tools\Godot_v4.7.2-stable_win64_console.exe"
CINEMATIC_USER = rf"{ROAM}\VV Lab Cinematic"


def fake_godot_scratch(name: str) -> str:
    return rf"C:\FakeScratch\godot-{name.lower()}"


def godot_plan(environ=None, appdata=ROAM, local=LOCAL, **kw):
    return gl.plan_godot([GODOT, "--headless", "--path", "x"], environ if environ is not None else {"PATH": "p"}, appdata, local,
                         make_scratch=fake_godot_scratch, **kw)


class GodotLaunch(unittest.TestCase):
    def test_the_child_gets_scratch_user_data_and_cache_folders_and_a_token(self):
        p = godot_plan({"PATH": "p", "APPDATA": ROAM, "LOCALAPPDATA": LOCAL})
        root = fake_godot_scratch("TOKEN_DIR")
        self.assertEqual(p.root, root)
        self.assertEqual(p.env["APPDATA"], os.path.join(root, "appdata"))
        self.assertEqual(p.env["LOCALAPPDATA"], os.path.join(root, "localappdata"))
        self.assertEqual(p.user_dir, rf"{p.env['APPDATA']}\VV Lab Cinematic")
        self.assertEqual(p.dev_user_dir, rf"{p.env['APPDATA']}\VV Lab Cinematic Dev")
        self.assertEqual(p.env["PATH"], "p")
        self.assertEqual(p.argv[0], GODOT)
        self.assertFalse(sl.is_under(p.user_dir, CINEMATIC_USER))
        self.assertEqual(p.env[sl.ENV_NONCE], p.token["nonce"])
        self.assertEqual(p.token["token_dir"], root)
        self.assertEqual(p.token["protected"], [CINEMATIC_USER, rf"{LOCAL}\VV Lab Cinematic", rf"{ROAM}\VV Lab Cinematic Dev", rf"{LOCAL}\VV Lab Cinematic Dev"])

    def test_the_caller_environment_is_not_modified(self):
        environ = {"APPDATA": ROAM, "LOCALAPPDATA": LOCAL}
        godot_plan(environ)
        self.assertEqual(environ, {"APPDATA": ROAM, "LOCALAPPDATA": LOCAL})

    def test_a_scratch_folder_in_the_installed_module_data_is_refused(self):
        hostile = [
            CINEMATIC_USER, CINEMATIC_USER + "\\", CINEMATIC_USER.lower(), CINEMATIC_USER.replace("\\", "/"),
            rf"{ROAM}\Temp\..\VV Lab Cinematic", rf"{LOCAL}\VV Lab Cinematic", rf"{LOCAL}\VV Lab Cinematic\cache",
        ]
        for value in hostile:
            with self.subTest(scratch=value):
                with self.assertRaises(sl.IsolationError):
                    gl.plan_godot([GODOT], {}, ROAM, LOCAL, make_scratch=lambda name, v=value: v)

    def test_the_real_profile_roots_are_refused_as_scratch(self):
        # A token directory that is the real profile root, or whose children would be, is refused.
        for root in (ROAM, LOCAL):
            with self.subTest(root=root):
                with self.assertRaises(sl.IsolationError):
                    gl.plan_godot([GODOT], {}, ROAM, LOCAL, make_scratch=lambda name, r=root: r)
        with self.assertRaises(sl.IsolationError):  # a root whose appdata child is the real APPDATA
            gl.plan_godot([GODOT], {}, rf"{fake_godot_scratch('TOKEN_DIR')}\appdata", LOCAL, make_scratch=fake_godot_scratch)

    def test_a_token_directory_nested_in_the_installed_data_is_refused(self):
        with self.assertRaises(sl.IsolationError):
            gl.plan_godot([GODOT], {}, ROAM, LOCAL, make_scratch=lambda name: rf"{ROAM}\VV Lab Cinematic\x")

    def test_neighbouring_scratch_names_are_accepted(self):
        p = gl.plan_godot([GODOT], {}, ROAM, LOCAL, make_scratch=lambda name: rf"{ROAM}\VV Lab Cinematic.scratch\{name}")
        self.assertTrue(p.user_dir.endswith("VV Lab Cinematic"))

    def test_missing_or_empty_inputs_refuse(self):
        with self.assertRaises(sl.IsolationError):
            gl.plan_godot([GODOT], {}, "", LOCAL, make_scratch=fake_godot_scratch)
        with self.assertRaises(sl.IsolationError):
            gl.plan_godot([], {}, ROAM, LOCAL, make_scratch=fake_godot_scratch)

    def test_the_run_and_popen_wrappers_use_only_the_plan(self):
        tree = ast.parse((STUDIO_TESTS / "godot_launch.py").read_text(encoding="utf-8"))
        names = {}
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for c in _calls(fn):
                    if _dotted(c.func) in ("subprocess.run", "subprocess.Popen"):
                        names[fn.name] = c
        self.assertEqual(sorted(names), ["popen", "run"])
        for fn_name, call in names.items():
            self.assertEqual(_dotted(call.args[0]), "plan.argv", fn_name)
            self.assertEqual([k.arg for k in call.keywords if k.arg == "env"], ["env"], fn_name)
            self.assertEqual(_dotted([k for k in call.keywords if k.arg == "env"][0].value), "plan.env", fn_name)
            fn = next(f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == fn_name)
            plan_line = min(c.lineno for c in _calls(fn) if _dotted(c.func) == "_plan")
            self.assertLess(plan_line, call.lineno)

    def test_the_studio_child_is_redirected_the_same_way(self):
        p = plan({"APPDATA": ROAM, "LOCALAPPDATA": LOCAL})
        root = fake_scratch("TOKEN_DIR")
        self.assertEqual(p.env["APPDATA"], os.path.join(root, "appdata"))
        self.assertEqual(p.env["LOCALAPPDATA"], os.path.join(root, "localappdata"))
        self.assertEqual(set(p.redirects), {"APPDATA", "LOCALAPPDATA"})
        for hostile_root in (CINEMATIC_USER, rf"{LOCAL}\VV Lab Cinematic", rf"{LOCAL}\{RELEASE}\x", rf"{ROAM}\{RELEASE}"):
            with self.subTest(root=hostile_root):
                with self.assertRaises(sl.IsolationError):
                    sl.plan_launch(EXE, {}, LOCAL, ROAM, identifier_reader=lambda _e: {DEV}, make_scratch=lambda name, h=hostile_root: h)

    def test_godot_is_started_only_through_the_helper(self):
        bad = [
            "import subprocess\nsubprocess.run([godot, '--headless'])\n",
            "import subprocess\nsubprocess.run([self.godot, '--headless', '--path', P])\n",
            "import subprocess\nsubprocess.Popen(cmd_godot)\n",
            "import subprocess\nsubprocess.run([console] + args)\n",
            "import subprocess as sp\n# godot\nsp.run(['x'])\n",
            "from subprocess import run\n# godot\nrun(['x'])\n",
            "import subprocess\n# VV_GODOT\ncmd = [g, '--headless']\nsubprocess.run(cmd)\n",
            "import os\n# godot\nos.spawnv(os.P_WAIT, g, [g])\n",
            "import subprocess\n# godot\nsubprocess.Popen(cmd)\n",
            "import subprocess\nsubprocess.check_output(['Godot_v4.7.2.exe'])\n",
        ]
        for src in bad:
            with self.subTest(src=src):
                self.assertTrue(godot_violations(src), src)
        for src in ("import godot_launch\ngodot_launch.run([godot, '--headless'])\n", "import subprocess\nsubprocess.run(['git', 'status'])\n"):
            self.assertEqual(godot_violations(src), [], src)
        files = (sorted(p for p in (ROOT / "tests").glob("*.py") if p.name != "test_studio_isolation.py")
                 + tree_files([ROOT / "scripts", ROOT / "docs" / "evidence", STUDIO_TESTS], (".py",)))
        files = [p for p in files if p.name not in ("godot_launch.py", "studio_launch.py")]
        self.assertTrue(any(p.name == "test_cinematic_cli.py" for p in files))
        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertEqual(godot_violations(path.read_text(encoding="utf-8")), [])

    def test_every_script_that_uses_godot_imports_the_helper(self):
        for path in sorted((ROOT / "tests").glob("test_cinematic_*.py")) + [ROOT / "scripts" / "cinematic" / "bench.py", ROOT / "scripts" / "cinematic" / "package_module.py"]:
            text = path.read_text(encoding="utf-8")
            if "VV_GODOT" in text or "--headless" in text or "godot_launch" in text:
                with self.subTest(file=path.name):
                    if "--headless" in text or "Popen" in text or "godot_launch.run" in text:
                        self.assertIn("import godot_launch", text)


def _signatures(tree):
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            a = node.args
            pos = [x.arg for x in a.posonlyargs + a.args]
            required = pos[:len(pos) - len(a.defaults)]
            kwonly = [x.arg for x in a.kwonlyargs]
            kw_required = [x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is None]
            out[node.name] = {"pos": pos, "required": required, "varargs": a.vararg is not None, "kwonly": kwonly,
                              "kw_required": kw_required, "kwargs": a.kwarg is not None}
    return out


def _fits(sig, call):
    if any(isinstance(x, ast.Starred) for x in call.args) or any(k.arg is None for k in call.keywords):
        return True  # arguments unpacked at run time: not decidable here
    n = len(call.args)
    names = {k.arg for k in call.keywords}
    if n > len(sig["pos"]) and not sig["varargs"]:
        return False
    if not sig["kwargs"] and not names <= set(sig["pos"][n:]) | set(sig["kwonly"]):
        return False
    given = set(sig["pos"][:n]) | names
    return set(sig["required"]) <= given and set(sig["kw_required"]) <= names


def arity_errors(source: str, modules: dict) -> list[str]:
    """Calls whose arguments do not fit the signature of the function they name, for functions defined in
    this file, imported with `from module import name` or called as `module.name` from the helper modules
    (`modules`: module name -> signatures). py_compile cannot see these: a changed signature that leaves a
    caller behind fails only when that caller runs."""
    tree = ast.parse(source)
    local = _signatures(tree)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in modules:
            for alias in node.names:
                if alias.name in modules[node.module]:
                    imported[alias.asname or alias.name] = modules[node.module][alias.name]
    found = []
    for call in _calls(tree):
        sig = None
        if isinstance(call.func, ast.Name):
            sig = local.get(call.func.id) or imported.get(call.func.id)
        elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id in modules:
            sig = modules[call.func.value.id].get(call.func.attr)
        if sig is not None and not _fits(sig, call):
            found.append(f"line {call.lineno}: {ast.unparse(call.func)}({len(call.args)} positional, {sorted(k.arg for k in call.keywords if k.arg)}) does not fit its signature")
    return found


class HelperArity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {p.stem: _signatures(ast.parse(p.read_text(encoding="utf-8"))) for p in STUDIO_TESTS.glob("*.py")}

    def test_the_checker_catches_a_stale_call(self):
        modules = {"helper": _signatures(ast.parse("def newest_log(proc):\n    pass\ndef launch(exe, env, port, *, allow_release=False):\n    pass\n"))}
        for src in ("from helper import newest_log\nnewest_log()\n", "from helper import newest_log\nnewest_log(1, 2)\n",
                    "from helper import launch\nlaunch(1, 2)\n", "from helper import launch\nlaunch(1, 2, 3, 4)\n",
                    "from helper import launch\nlaunch(1, 2, 3, other=True)\n", "import helper\nhelper.launch(1)\n",
                    "def f(a):\n    pass\nf()\n"):
            with self.subTest(src=src):
                self.assertTrue(arity_errors(src, modules), src)
        for src in ("from helper import newest_log\nnewest_log(p)\n", "from helper import launch\nlaunch(1, 2, 3, allow_release=True)\n",
                    "from helper import launch\nlaunch(*a)\n", "import helper\nhelper.launch(1, 2, port=3)\n"):
            with self.subTest(src=src):
                self.assertEqual(arity_errors(src, modules), [], src)

    def test_every_call_of_a_helper_function_fits_its_signature(self):
        files = (sorted(STUDIO_TESTS.glob("*.py")) + sorted((ROOT / "tests").glob("test_cinematic_*.py"))
                 + sorted((ROOT / "scripts" / "cinematic").glob("*.py")))
        self.assertGreater(len(files), 15)
        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertEqual(arity_errors(path.read_text(encoding="utf-8"), self.modules), [])

    def test_newest_log_takes_the_studio_process(self):
        self.assertEqual(self.modules["installed_spotcheck"]["newest_log"]["required"], ["proc"])
        for name in ("ux_journeys", "installed_spotcheck"):
            text = (STUDIO_TESTS / f"{name}.py").read_text(encoding="utf-8")
            for call in _calls(ast.parse(text)):
                if _dotted(call.func) == "newest_log":
                    self.assertEqual([_dotted(a) for a in call.args], ["proc"], name)


class ScratchRemoval(unittest.TestCase):
    def test_only_vv_folders_directly_under_the_temp_folder_are_removed(self):
        temp = tempfile.gettempdir()
        with tempfile.TemporaryDirectory() as outside:
            mine = tempfile.mkdtemp(prefix="vv-test-removal-")
            nested = os.path.join(tempfile.mkdtemp(prefix="vv-test-removal-"), "inner")
            os.makedirs(nested)
            other = tempfile.mkdtemp(prefix="other-")
            try:
                self.assertTrue(sl.remove_scratch(mine))
                self.assertFalse(os.path.exists(mine))
                self.assertTrue(sl.remove_scratch(nested))  # a folder inside a vv- folder is removed too
                self.assertFalse(os.path.exists(nested))
                self.assertFalse(sl.remove_scratch(other), "no vv- prefix")
                self.assertTrue(os.path.isdir(other))
                self.assertFalse(sl.remove_scratch(outside), "not under the temporary folder")
                self.assertTrue(os.path.isdir(outside))
                self.assertFalse(sl.remove_scratch(temp), "the temporary folder itself")
                self.assertTrue(os.path.isdir(temp))
                for refused in (os.path.dirname(temp), os.path.abspath(os.sep), os.path.expanduser("~"), "", "relative-vv-x"):
                    with self.subTest(path=refused):
                        self.assertFalse(sl.remove_scratch(refused))
                self.assertTrue(os.path.isdir(os.path.expanduser("~")))
            finally:
                for d in (mine, os.path.dirname(nested), other):
                    shutil.rmtree(d, ignore_errors=True)

    def test_a_profile_root_under_a_vv_name_is_not_removed(self):
        from unittest import mock

        folder = tempfile.mkdtemp(prefix="vv-test-profile-")
        try:
            with mock.patch.dict("os.environ", {"USERPROFILE": folder}):
                self.assertFalse(sl.remove_scratch(folder))
            self.assertTrue(os.path.isdir(folder))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_refused_studio_plan_removes_the_folders_it_made(self):
        root = tempfile.mkdtemp(prefix="vv-test-plan-")
        try:
            # The token directory is real and then refused: the child's APPDATA would be the "real" one.
            with self.assertRaises(sl.IsolationError):
                sl.plan_launch(EXE, {}, LOCAL, os.path.join(root, "appdata"), identifier_reader=lambda _e: {DEV}, make_scratch=lambda name: root)
            self.assertFalse(os.path.exists(root))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_refused_godot_plan_removes_the_folders_it_made(self):
        root = tempfile.mkdtemp(prefix="vv-test-godot-")
        try:
            with self.assertRaises(sl.IsolationError):
                gl.plan_godot([GODOT], {}, os.path.join(root, "appdata"), LOCAL, make_scratch=lambda name: root)
            self.assertFalse(os.path.exists(root))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_godot_run_removes_its_token_directory_and_gives_the_child_a_valid_token(self):
        import sys

        code = "import json, os; t = json.load(open(os.environ['VVLAB_DEV_LAUNCH'])); print(json.dumps([os.environ['APPDATA'], t['nonce'] == os.environ['VVLAB_DEV_NONCE'], t['token_dir']]))"
        result = gl.run([sys.executable, "-c", code], capture_output=True, text=True)
        appdata, nonce_ok, token_dir = json.loads(result.stdout)
        self.assertTrue(nonce_ok)
        self.assertTrue(os.path.basename(token_dir).startswith("vv-godot-"), token_dir)
        self.assertTrue(sl.is_under(appdata, token_dir))
        self.assertFalse(os.path.exists(token_dir))
        self.assertEqual(result.godot_plan.root, token_dir)

    def test_stop_removes_the_child_redirect_folders_and_only_those(self):
        from types import SimpleNamespace

        mine = tempfile.mkdtemp(prefix="vv-test-stop-")
        other = tempfile.mkdtemp(prefix="notmine-")
        try:
            proc = SimpleNamespace(poll=lambda: 0, redirect_dirs=[mine, other, os.path.expanduser("~")])
            sl.stop(proc)
            self.assertFalse(os.path.exists(mine))
            self.assertTrue(os.path.isdir(other))
            self.assertTrue(os.path.isdir(os.path.expanduser("~")))
        finally:
            shutil.rmtree(mine, ignore_errors=True)
            shutil.rmtree(other, ignore_errors=True)


class StopRemovesEveryScratchFolder(unittest.TestCase):
    def test_launch_hands_stop_the_token_directory(self):
        tree = ast.parse((STUDIO_TESTS / "studio_launch.py").read_text(encoding="utf-8"))
        launch = next(f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == "launch")
        assigned = [ast.unparse(n.value) for n in ast.walk(launch) if isinstance(n, ast.Assign)
                    and any(ast.unparse(t) == "proc.redirect_dirs" for t in n.targets)]
        self.assertEqual(assigned, ["[plan.token_dir]"])

    def test_stop_removes_a_real_plan_s_token_directory_and_nothing_else(self):
        from types import SimpleNamespace

        keep = tempfile.mkdtemp(prefix="notvv-")
        plan_ = sl.plan_launch(EXE, {"VVLAB_LIBRARY": keep}, LOCAL, ROAM, identifier_reader=lambda _e: {DEV})
        try:
            self.assertTrue(os.path.basename(plan_.token_dir).startswith("vv-launch-"))
            sl.write_token(plan_)
            self.assertTrue(all(os.path.isdir(f) for f in plan_.token["paths"].values()))
            self.assertTrue(os.path.isfile(plan_.env[sl.ENV_LAUNCH]))
            sl.stop(SimpleNamespace(poll=lambda: 0, redirect_dirs=[plan_.token_dir]))
            self.assertFalse(os.path.exists(plan_.token_dir))
            self.assertTrue(os.path.isdir(keep))  # the caller's own folder is not the plan's to remove
        finally:
            for f in (plan_.token_dir, keep):
                shutil.rmtree(f, ignore_errors=True)

class GodotOffWindows(unittest.TestCase):
    def shim(self, environ):
        from types import SimpleNamespace

        return SimpleNamespace(name="posix", environ=environ, path=os.path)

    def test_real_roots_use_the_xdg_folders_or_the_home_defaults(self):
        from unittest import mock

        with mock.patch.object(gl, "os", self.shim({})):
            home = os.path.expanduser("~")
            self.assertEqual(gl.real_roots(), (os.path.join(home, ".local", "share"), os.path.join(home, ".cache")))
        with mock.patch.object(gl, "os", self.shim({"XDG_DATA_HOME": "/x/data", "XDG_CACHE_HOME": "/x/cache"})):
            self.assertEqual(gl.real_roots(), ("/x/data", "/x/cache"))

    def test_the_plan_redirects_the_xdg_folders_and_refuses_the_real_installed_one(self):
        from unittest import mock

        with mock.patch.object(gl, "os", self.shim({})):
            p = gl.plan_godot([GODOT], {}, "/home/u/.local/share", "/home/u/.cache", make_scratch=lambda name: "/scratch/token")
            self.assertEqual(set(p.scratch), {"APPDATA", "LOCALAPPDATA", *gl.POSIX_REDIRECTS})
            self.assertEqual(sl.normalise(p.env["XDG_DATA_HOME"]), sl.normalise("/scratch/token/xdg_data_home"))
            self.assertEqual(sl.normalise(p.user_dir), sl.normalise("/scratch/token/xdg_data_home/VV Lab Cinematic"))
            for hostile in ("/home/u/.local/share/VV Lab Cinematic", "/home/u/.local/share", "/home/u/.cache"):
                with self.assertRaises(sl.IsolationError):
                    gl.plan_godot([GODOT], {}, "/home/u/.local/share", "/home/u/.cache", make_scratch=lambda name, h=hostile: h)

class NetworkPathsAndDocuments(unittest.TestCase):
    def test_network_paths_are_refused_in_every_spelling(self):
        for value in (
            rf"\\localhost\c$\FakeUser\AppData\Local\{RELEASE}\EBWebView",
            rf"//localhost/c$/FakeUser/AppData/Local/{RELEASE}/EBWebView",
            r"\\server\share\scratch",
            rf"\\?\UNC\localhost\c$\FakeUser\AppData\Local\{RELEASE}",
            rf"\\?\unc\server\share",
        ):
            with self.subTest(value=value):
                with self.assertRaises(sl.IsolationError):
                    sl.normalise(value)
                for name in sl.SCRATCH_VARIABLES:
                    with self.assertRaises(sl.IsolationError):
                        plan({name: value})

    def test_a_network_executable_is_refused(self):
        with self.assertRaises(sl.IsolationError):
            plan(exe=r"\\server\share\vv-studio.exe")

    def test_device_prefixes_on_a_drive_are_accepted(self):
        self.assertEqual(sl.normalise(r"\\?\C:\Scratch\x"), sl.normalise(r"C:\Scratch\x"))
        self.assertEqual(sl.normalise(r"\\.\C:\Scratch\x"), sl.normalise(r"C:\Scratch\x"))
        with self.assertRaises(sl.IsolationError):
            plan({"VVLAB_CONFIG": rf"\\?\{LOCAL}\{RELEASE}\x"})

    def test_device_paths_that_do_not_continue_with_a_drive_letter_are_refused(self):
        for value in (
            r"\\?\Volume{01234567-89ab-cdef-0123-456789abcdef}\FakeUser\AppData\Local\org.vvlab.studio",
            r"\\?\GLOBALROOT\Device\HarddiskVolume3\FakeUser",
            r"\\.\PhysicalDrive0",
            r"\\.\GLOBALROOT\Device\x",
            r"\\?\Global\C:\x",
        ):
            with self.subTest(value=value):
                with self.assertRaises(sl.IsolationError):
                    sl.normalise(value)
                with self.assertRaises(sl.IsolationError):
                    plan({"VVLAB_LIBRARY": value})
        self.assertEqual(sl.normalise("\\\\?\\C:"), "c:")

    @unittest.skipUnless(os.name == "nt", "the Windows known folder exists only on Windows")
    def test_documents_folders_include_the_real_known_folder(self):
        import subprocess

        real = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('MyDocuments')"],
                              capture_output=True, text=True).stdout.strip()
        self.assertTrue(real, "PowerShell reports the Documents folder")
        self.assertEqual(sl.known_documents_folder(), real)
        self.assertIn(sl.normalise(real), [sl.normalise(d) for d in sl.documents_folders()])
        self.assertIn(sl.normalise(os.path.join(real, sl.LIBRARY_FOLDER)), [sl.normalise(r) for r in sl.protected_roots(LOCAL, ROAM, sl.documents_folders())])

    def test_the_known_folder_guid_is_encoded_as_a_windows_guid(self):
        import uuid

        self.assertEqual(sl.FOLDERID_DOCUMENTS, "FDD39AD0-238F-46AF-ADB4-6C85480369C7")
        self.assertEqual(uuid.UUID(sl.FOLDERID_DOCUMENTS).bytes_le.hex().upper(), "D09AD3FD8F23AF46ADB46C85480369C7")

    @unittest.skipUnless(os.name == "nt", "the Windows known folder exists only on Windows")
    def test_a_failed_known_folder_call_is_visible(self):
        import warnings
        from unittest import mock

        with mock.patch("ctypes.windll") as windll:
            windll.shell32.SHGetKnownFolderPath.return_value = -2147024809  # E_INVALIDARG
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.assertIsNone(sl.known_documents_folder())
        self.assertTrue([w for w in caught if issubclass(w.category, RuntimeWarning) and "Documents" in str(w.message)])

    def test_no_known_documents_folder_at_all_refuses(self):
        from unittest import mock

        with mock.patch.object(sl, "known_documents_folder", return_value=None), mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(sl.IsolationError):
                sl.documents_folders()

    def test_every_given_documents_folder_protects_its_library(self):
        redirected = r"D:\Redirected\Documents"
        for documents in ([DOCS, redirected], (DOCS, redirected)):
            for folder in (DOCS, redirected):
                with self.subTest(documents=documents, folder=folder):
                    with self.assertRaises(sl.IsolationError):
                        sl.plan_launch(EXE, {"VVLAB_LIBRARY": rf"{folder}\VV Lab Library\runs"}, LOCAL, ROAM, documents=documents,
                                       identifier_reader=lambda _e: {DEV}, make_scratch=fake_scratch)
        self.assertEqual(len(sl.protected_roots(LOCAL, ROAM, [DOCS, redirected, ""])), 4)
        self.assertEqual(len(sl.protected_roots(LOCAL, ROAM, DOCS)), 3)
        self.assertEqual(len(sl.protected_roots(LOCAL, ROAM)), 2)

    def test_the_documents_guess_from_the_user_profile_is_always_included(self):
        from unittest import mock

        with mock.patch.dict("os.environ", {"USERPROFILE": r"C:\FakeUser"}):
            self.assertIn(r"C:\FakeUser\Documents", sl.documents_folders())
        self.assertEqual(len(sl.documents_folders()), len(set(sl.documents_folders())))

    def test_the_default_launch_uses_the_known_folder_helper(self):
        text = (STUDIO_TESTS / "studio_launch.py").read_text(encoding="utf-8")
        self.assertIn("documents=documents_folders()", text)
        self.assertIn("SHGetKnownFolderPath", text)


class BuildScriptProductName(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "desktop" / "build.ps1").read_text(encoding="utf-8")

    def test_product_names_match_the_configuration_files(self):
        self.assertIn(f'$DevProductName = "{read_json(STUDIO / "tauri.conf.json")["productName"]}"', self.text)
        self.assertIn(f'$ReleaseProductName = "{read_json(STUDIO / "tauri.release.conf.json")["productName"]}"', self.text)

    def test_the_product_name_is_asserted_before_and_after_the_build(self):
        self.assertIn("$wantedProduct = if ($Release) { $ReleaseProductName } else { $DevProductName }", self.text)
        before = self.text.index("$mergedProduct -cne $wantedProduct")
        build = self.text.index('Run "node"')
        after = self.text.index("$hasReleaseName")
        self.assertLess(before, build)
        self.assertLess(build, after)
        self.assertRegex(self.text, r"if \(\$Release -and \(\$hasDevName -or -not \$hasReleaseName\)\) \{ throw")
        self.assertRegex(self.text, r"if \(-not \$Release -and -not \$hasDevName\) \{ throw")


def _calls(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _dotted(node) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


SPAWNERS = {"subprocess.Popen", "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output",
            "subprocess.getoutput", "subprocess.getstatusoutput",
            "os.system", "os.startfile", "os.popen", "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell"}
ALWAYS_FORBIDDEN = {"subprocess.Popen", "subprocess.getoutput", "subprocess.getstatusoutput", "os.system", "os.startfile", "os.popen",
                    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
                    "importlib.import_module", "exec", "eval", "compile"}
NATIVE_LAUNCHERS = re.compile(r"ShellExecute|CreateProcess|WinExec")
# PowerShell text that could start or run something else: the command must be a literal without these.
POWERSHELL_FORBIDDEN = ("&", "Invoke-Item", "Start-Process", "Invoke-Expression", "iex ", "Invoke-Command", "Stop-Process")


# This lint guards against accidents (a script, or an agent writing one, that launches the wrong
# executable by habit), not against an adversary: code can always be written that no syntax check sees.


def _module_facts(tree):
    """Assignments and function bodies of a script, to resolve the name of a PowerShell command."""
    assigns, defs = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns.setdefault(t.id, []).append(node.value)
        elif isinstance(node, ast.FunctionDef):
            defs[node.name] = [r.value for r in ast.walk(node) if isinstance(r, ast.Return) and r.value is not None]
    return assigns, defs


def _literal_text(node, facts, depth=0):
    """The literal text pieces of a command expression, or None when any part is not a literal:
    string constants, f-strings (their fixed parts), concatenations, names assigned only such values,
    and calls to local functions that return such values."""
    assigns, defs = facts
    if depth > 5:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.Constant)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_text(node.left, facts, depth + 1), _literal_text(node.right, facts, depth + 1)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.Name) and node.id in assigns:
        out = []
        for value in assigns[node.id]:
            part = _literal_text(value, facts, depth + 1)
            if part is None:
                return None
            out += part
        return out
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in defs and defs[node.func.id]:
        out = []
        for value in defs[node.func.id]:
            part = _literal_text(value, facts, depth + 1)
            if part is None:
                return None
            out += part
        return out
    return None


def _allowed_spawn(call, facts) -> str | None:
    """The reason a subprocess call in a UI test script is allowed, or None. The allowlist is closed:
    a call that is not one of these three shapes is a violation, whatever it runs.
      1. taskkill /F /PID <pid>: ends one process by its PID.
      2. powershell with a literal command (-Command) containing none of POWERSHELL_FORBIDDEN, or -File
         with a script named *.ps1 (the file itself is covered by the text rules).
      3. tasklist, a read-only listing.
    Godot is never started here: godot_launch.run/popen only (see godot_violations).
    """
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.List) and first.elts and isinstance(first.elts[0], ast.Constant):
        head = str(first.elts[0].value).lower()
        consts = [e.value for e in first.elts if isinstance(e, ast.Constant)]
        if head == "taskkill" and consts[1:3] == ["/F", "/PID"]:
            return "taskkill by PID"
        if head == "powershell" and consts[1:2] == ["-NoProfile"]:
            flags = [i for i, e in enumerate(first.elts) if isinstance(e, ast.Constant) and e.value in ("-Command", "-File")]
            if len(flags) == 1 and flags[0] + 1 < len(first.elts):
                target = first.elts[flags[0] + 1]
                if first.elts[flags[0]].value == "-Command":
                    pieces = _literal_text(target, facts)
                    if pieces is not None and not any(bad.lower() in "".join(pieces).lower() for bad in POWERSHELL_FORBIDDEN):
                        return "powershell, literal command"
                else:
                    script = [ast.unparse(v) for v in facts[0].get(target.id, [])] if isinstance(target, ast.Name) else [ast.unparse(target)]
                    if script and all(".ps1" in x for x in script):
                        return "powershell, script file"
        if head == "tasklist":
            return "read-only listing"
    return None


def launch_violations(source: str) -> list[str]:
    """Ways a UI test script could start a Studio, or end a process, outside the helper."""
    tree = ast.parse(source)
    facts = _module_facts(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "os", "asyncio", "importlib", "ctypes"):
            for alias in node.names:
                if f"{node.module}.{alias.name}" in SPAWNERS | ALWAYS_FORBIDDEN or alias.name.startswith(("spawn", "exec")) or NATIVE_LAUNCHERS.search(alias.name):
                    found.append(f"line {node.lineno}: imports {node.module}.{alias.name} by name")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "os", "asyncio", "importlib", "ctypes") and alias.asname:
                    found.append(f"line {node.lineno}: aliases {alias.name}")
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            value = _dotted(node.value)
            if value in SPAWNERS or value.endswith("Popen") or re.match(r"os\.(spawn|exec)", value) or NATIVE_LAUNCHERS.search(value):
                found.append(f"line {node.lineno}: {value} bound to a name")
        if isinstance(node, ast.Attribute) and NATIVE_LAUNCHERS.search(node.attr):
            found.append(f"line {node.lineno}: native launcher {node.attr}")
    for call in _calls(tree):
        name = _dotted(call.func)
        if name == "getattr" and call.args and _dotted(call.args[0]) in ("subprocess", "os", "asyncio", "importlib", "ctypes"):
            found.append(f"line {call.lineno}: getattr on {_dotted(call.args[0])}")
        if name == "__import__":
            found.append(f"line {call.lineno}: __import__")
        for k in call.keywords:
            if k.arg == "allow_release" and isinstance(k.value, ast.Constant) and k.value.value is True:
                found.append(f"line {call.lineno}: literal allow_release=True")
            if k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True:
                found.append(f"line {call.lineno}: shell=True")
        if name in ALWAYS_FORBIDDEN or name.endswith("Popen") or re.match(r"os\.(spawn|exec)", name):
            found.append(f"line {call.lineno}: {name} outside the helper")
        elif name in SPAWNERS and _allowed_spawn(call, facts) is None:
            found.append(f"line {call.lineno}: {name}({ast.unparse(call.args[0])[:60] if call.args else ''}) is not on the allowlist")
    return found


def godot_violations(source: str) -> list[str]:
    """A process start whose command mentions Godot (or a variable called console, the Godot console
    executable) outside godot_launch: Godot started that way keeps its user data in the real profile.
    A file that mentions Godot at all is also held to launch_violations: no Popen, no aliases or
    from-imports of subprocess/os spawners, no os.spawn*, and every other subprocess call must be on
    the closed allowlist (so a command held in a variable cannot start Godot unseen)."""
    tree = ast.parse(source)
    found = []
    if "godot" in source.lower():
        found += [f"mentions Godot: {v}" for v in launch_violations(source)]
    for call in _calls(tree):
        name = _dotted(call.func)
        if name in SPAWNERS or name.endswith("Popen"):
            first = ast.unparse(call.args[0]).lower() if call.args else ""
            if "godot" in first or re.search(r"\bconsole\b", first):
                found.append(f"line {call.lineno}: {name}({first[:50]}) starts Godot outside godot_launch")
    return found


def studio_launch_violations(source: str) -> list[str]:
    """For code outside the UI test folder (scripts/, evidence programs), where subprocess has many
    legitimate uses: a spawn whose arguments mention a Studio executable, or a literal allow_release=True."""
    tree = ast.parse(source)
    found = []
    for call in _calls(tree):
        name = _dotted(call.func)
        if name in SPAWNERS or name.endswith("Popen"):
            args = " ".join(ast.unparse(a) for a in call.args).lower()
            query = call.args and ast.unparse(call.args[0]).lower().startswith("['powershell', '-noprofile'")
            if "studio" in args and not query:
                found.append(f"line {call.lineno}: {name} of {ast.unparse(call.args[0])[:60]}")
        for k in call.keywords:
            if k.arg == "allow_release" and isinstance(k.value, ast.Constant) and k.value.value is True:
                found.append(f"line {call.lineno}: literal allow_release=True")
    return found


# Text rules over scripts, workflows and build tooling. Killing by name can end the owner's installed Studio.
KILL_PATTERNS = [
    (re.compile(r"(?<![\w.])/IM(?![\w])", re.I), "taskkill /IM"),
    (re.compile(r"Stop-Process", re.I), "Stop-Process"),
    (re.compile(r"(?<![\w-])(spps|saps)(?![\w-])", re.I), "Stop-Process/Start-Process alias"),
    (re.compile(r"\|\s*kill\b", re.I), "piped kill alias"),
    (re.compile(r"Get-Process[^\n]*\.Kill\s*\(", re.I), "Get-Process .Kill()"),
    (re.compile(r"\.Terminate\s*\(|Invoke-CimMethod[^\n]*Terminate", re.I), "CIM Terminate"),
    (re.compile(r"wmic[^\n]*\b(delete|terminate)\b", re.I), "wmic delete"),
    (re.compile(r"psutil\.process_iter|psutil[^\n]*\.name\(\)", re.I), "psutil name matching"),
    (re.compile(r"\b(pkill|killall)\b"), "pkill/killall"),
    (re.compile(r"taskkill[^\n]*/FI", re.I), "taskkill /FI"),
]
START_PATTERN = re.compile(r"Start-Process", re.I)


def tree_files(bases, suffixes):
    files = []
    for base in bases:
        for folder, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ("target", "node_modules", ".git", "__pycache__")]
            files += [Path(folder) / n for n in names if n.endswith(suffixes)]
    return sorted(files)


class LaunchDiscipline(unittest.TestCase):
    def scripts(self):
        return sorted(p for p in STUDIO_TESTS.glob("*.py") if p.name not in ("studio_launch.py", "godot_launch.py"))

    def test_the_lint_catches_what_it_is_meant_to(self):
        bad = [
            "import subprocess\nsubprocess.Popen([exe], env=env)\n",
            "import subprocess\nsubprocess.Popen([a.exe])\n",
            "import subprocess\nsubprocess.run([a.exe, '--self-test'])\n",
            "import subprocess\nsubprocess.check_output([os.path.abspath(exe)])\n",
            "import subprocess\nsubprocess.run(cmd)\n",
            "import subprocess\nsubprocess.run(['cmd', '/c', 'x'])\n",
            "import subprocess\nsubprocess.run(['taskkill', '/F', '/IM', 'x'])\n",
            "import subprocess\nsubprocess.run('x', shell=True)\n",
            "import subprocess\nrunner = subprocess.Popen\nrunner([exe])\n",
            "import subprocess\nrun = subprocess.run\nrun([exe])\n",
            "import subprocess\ngetattr(subprocess, 'Pop' + 'en')([exe])\n",
            "from subprocess import Popen\nPopen(['x'])\n",
            "import subprocess as sp\nsp.run(['x'])\n",
            "import os\nos.startfile(exe)\n",
            "import studio_launch\nstudio_launch.launch(exe, env, 1, allow_release=True)\n",
            "import subprocess\nsubprocess.run([console] + args + ['--shot', 'x'])\n",
            "import subprocess\nsubprocess.run([godot, '--headless'])\n",
            "import subprocess\nsubprocess.getoutput(cmd)\n",
            "import subprocess\nsubprocess.getstatusoutput('x')\n",
            "import importlib\nimportlib.import_module('subprocess').run(['x'])\n",
            "exec(code)\n",
            "eval(code)\n",
            "import ctypes\nctypes.windll.shell32.ShellExecuteW(0, 'open', exe, None, None, 1)\n",
            "from ctypes import windll\nwindll.shell32.ShellExecuteW\n",
            "import subprocess\nsubprocess.run(['powershell', '-NoProfile', '-Command', cmd])\n",
            "import subprocess\nsubprocess.run(['powershell', '-NoProfile', '-Command', 'Start-Process vv-studio.exe'])\n",
            "import subprocess\nsubprocess.run(['powershell', '-NoProfile', '-Command', '& $exe'])\n",
            "import subprocess\nsubprocess.run(['powershell', '-NoProfile', '-Command', 'Invoke-Item x'])\n",
            "import subprocess\nps = 'ok'\nps = ps + '; & x'\nsubprocess.run(['powershell', '-NoProfile', '-Command', ps])\n",
            "import subprocess\nsubprocess.run(['powershell', '-NoProfile', '-File', script])\n",
        ]
        for src in bad:
            with self.subTest(src=src):
                self.assertTrue(launch_violations(src), src)
        good = [
            "import subprocess\nsubprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)\n",
            "import subprocess\nps = 'Get-Date'\nsubprocess.run(['powershell', '-NoProfile', '-Command', ps])\n",
            "import subprocess\npid = 1\nsubprocess.run(['powershell', '-NoProfile', '-Command', f\"Get-Process -Id {pid}\"])\n",
            "import subprocess\ndef tree(x):\n    return 'Get-CimInstance Win32_Process'\nsubprocess.run(['powershell', '-NoProfile', '-Command', tree(1) + '; 1'])\n",
            "import subprocess\nscript = os.path.join(d, 'x.ps1')\nsubprocess.run(['powershell', '-NoProfile', '-File', script])\n",
            "import subprocess\nsubprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True)\n",
            "import studio_launch\nproc = studio_launch.launch(exe, env, 1, allow_release=a.owner_allow_release_exe)\n",
        ]
        for src in good:
            with self.subTest(src=src):
                self.assertEqual(launch_violations(src), [], src)

    def test_the_lint_for_code_outside_the_ui_tests(self):
        for src in ("import subprocess\nsubprocess.Popen([studio_exe])\n", "import subprocess\nsubprocess.run([studio.exe])\n",
                    "import subprocess\nsubprocess.run(['vv-studio.exe'])\n", "x(allow_release=True)\n"):
            with self.subTest(src=src):
                self.assertTrue(studio_launch_violations(src), src)
        self.assertEqual(studio_launch_violations("import subprocess\nsubprocess.run(['cargo', 'build'])\n"), [])

    def test_no_script_starts_a_studio_outside_the_helper(self):
        for path in self.scripts():
            with self.subTest(script=path.name):
                self.assertEqual(launch_violations(path.read_text(encoding="utf-8")), [])

    def test_no_other_program_in_the_repository_starts_a_studio(self):
        files = tree_files([ROOT / "scripts", ROOT / "docs" / "evidence"], (".py",))
        self.assertTrue(files)
        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertEqual(studio_launch_violations(path.read_text(encoding="utf-8")), [])

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

    def test_the_module_lifecycle_suite_refuses_the_installed_exe_without_a_second_flag(self):
        text = (STUDIO_TESTS / "m17_cinematic_journey.py").read_text(encoding="utf-8")
        self.assertIn("--i-accept-installed-module-uninstall", text)
        refuse = text.index("if a.owner_allow_release_exe:")
        self.assertIn("sys.exit(", text[refuse:refuse + 400])
        self.assertLess(refuse, text.index("launch(os.path.abspath"))

    def test_docstrings_show_the_development_build_and_keep_the_installed_form_for_audited_suites_only(self):
        audited = {"ui_smoke", "m15_journeys", "m16_journeys", "m17_lab_journeys", "perf_probe", "m16_compare_shots", "m17_tech_shots"}
        for path in self.scripts():
            doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
            flagged = [ln.strip() for ln in doc.splitlines() if ln.strip().startswith("python ") and "owner-allow-release-exe" in ln]
            if flagged:
                with self.subTest(script=path.name):
                    self.assertIn(path.stem, audited)
                    self.assertIn("Owner only", doc)
                    self.assertLess(doc.index("Owner only"), doc.index(flagged[0]))
                    dev = re.search(r"--exe (desktop[/\\]target|PATH)", doc)
                    self.assertIsNotNone(dev, "a development form is documented")
                    self.assertLess(dev.start(), doc.index("Owner only"), "the development form comes first")
        for name in ("m17_cinematic_journey", "m18_journeys", "ux_journeys", "ux2_journeys", "review_captures", "installed_spotcheck"):
            doc = ast.get_docstring(ast.parse((STUDIO_TESTS / f"{name}.py").read_text(encoding="utf-8"))) or ""
            with self.subTest(script=name):
                self.assertNotIn("VV Lab Studio" + chr(92) + "vv-studio.exe", doc)

    def test_no_kill_by_name_anywhere_in_the_test_scripts_or_build_tooling(self):
        files = tree_files([STUDIO_TESTS, ROOT / "scripts", ROOT / ".github" / "workflows", ROOT / "desktop"],
                           (".py", ".ps1", ".yml", ".sh", ".cmd", ".bat"))
        self.assertTrue(files)
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern, what in KILL_PATTERNS:
                with self.subTest(file=str(path.relative_to(ROOT)), rule=what):
                    self.assertIsNone(pattern.search(text))

    def test_the_kill_patterns_catch_the_spellings_they_are_meant_to(self):
        for text in (
            "taskkill /F /IM vv-studio.exe", "Stop-Process -Name vv-studio", "spps -n vv-studio", "Get-Process vv-studio | kill",
            "(Get-Process vv-studio).Kill()", "wmic process where name='vv-studio.exe' delete", "psutil.process_iter(['name'])",
            "p = psutil.Process(1); p.name() == 'vv-studio.exe'", "taskkill /FI \"IMAGENAME eq vv-studio.exe\"", "pkill vv-studio",
            "Invoke-CimMethod -MethodName Terminate",
        ):
            with self.subTest(text=text):
                self.assertTrue(any(p.search(text) for p, _ in KILL_PATTERNS), text)
        for text in ("taskkill /F /PID 123", "proc.kill()", "docs/images/x.png", "psutil.Process(proc.pid)"):
            with self.subTest(text=text):
                self.assertFalse(any(p.search(text) for p, _ in KILL_PATTERNS), text)

    def test_no_start_process_in_the_ui_test_scripts(self):
        for path in self.scripts() + sorted(STUDIO_TESTS.glob("*.ps1")):
            with self.subTest(file=path.name):
                self.assertIsNone(START_PATTERN.search(path.read_text(encoding="utf-8")))

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
