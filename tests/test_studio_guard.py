"""The Studio's runtime guard (desktop/studio/src/guard.rs), seen from outside: a DEVELOPMENT executable
started directly, with an invalid or reused token, with a missing variable or with an unsafe path must
refuse to start, with the distinct exit code, before WebView2 or anything else touches data.

Needs a built development executable: desktop/target/debug/vv-studio.exe (cargo build -p vv-studio in
desktop/) or the one named by VV_STUDIO_DEV_EXE; without one the tests are skipped. They never start the
installed Studio: the helper refuses an executable that carries the release identifier. Every launch
uses disposable folders under the temporary folder; the decoys of the unsafe-path tests are such folders
too, never the real profile. Most runs use `--guard-only`, which prints the decision and exits before
Tauri. The unit tests of the pure decision, with fake known folders, are in guard.rs (`cargo test`).

The guard protects against accidental misuse, not against someone who forges a token.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop" / "studio" / "tests"))

import studio_launch as sl  # noqa: E402

EXE = Path(os.environ.get("VV_STUDIO_DEV_EXE") or ROOT / "desktop" / "target" / "debug" / "vv-studio.exe")


@unittest.skipUnless(os.name == "nt" and EXE.is_file(), "needs a built development vv-studio.exe (desktop/target/debug)")
class StudioGuard(unittest.TestCase):
    def setUp(self):
        self.made = []

    def tearDown(self):
        for folder in self.made:
            sl.remove_scratch(folder)

    def launch_plan(self):
        """A real plan and token in a disposable token directory, and its environment."""
        plan = sl.plan_launch(str(EXE), dict(os.environ), os.environ["LOCALAPPDATA"], os.environ["APPDATA"], documents=sl.documents_folders())
        sl.write_token(plan)
        self.made.append(plan.token_dir)
        return plan

    def probe(self, env, args=("--guard-only",)):
        return sl.guard_probe(str(EXE), env, args=args)

    def refused(self, result, needle=""):
        self.assertEqual(result.returncode, sl.REFUSED_EXIT, result.stdout + result.stderr)
        self.assertIn("refused", result.stdout + result.stderr)
        self.assertIn(needle, result.stdout + result.stderr)

    def test_the_executable_is_a_development_build_with_only_the_development_identifier(self):
        self.assertEqual(sl.embedded_identifiers(str(EXE)), {sl.DEV_IDENTIFIER})

    def test_a_valid_token_is_allowed_then_consumed_and_cannot_be_reused(self):
        plan = self.launch_plan()
        first = self.probe(plan.env)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("allowed: development identifier", first.stdout)
        token = Path(plan.env[sl.ENV_LAUNCH])
        self.assertFalse(token.exists())
        self.assertTrue(token.with_name(token.name + ".used").exists())
        self.refused(self.probe(plan.env), "missing or already used")

    def test_a_direct_launch_without_a_token_is_refused(self):
        plan = self.launch_plan()
        env = {k: v for k, v in plan.env.items() if k not in (sl.ENV_LAUNCH, sl.ENV_NONCE)}
        self.refused(self.probe(env), "authorised launcher")

    def test_a_direct_launch_in_a_bare_environment_is_refused(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("VVLAB_") and k != "WEBVIEW2_USER_DATA_FOLDER"}
        self.refused(self.probe(env), "VVLAB_DEV_LAUNCH")

    def test_an_invalid_nonce_is_refused_and_does_not_consume_the_token(self):
        plan = self.launch_plan()
        env = dict(plan.env)
        env[sl.ENV_NONCE] = "0" * 32
        self.refused(self.probe(env), "nonce does not match")
        self.assertTrue(Path(plan.env[sl.ENV_LAUNCH]).exists())
        self.assertEqual(self.probe(plan.env).returncode, 0)  # the right environment still works, once

    def test_a_token_with_another_nonce_is_refused(self):
        plan = self.launch_plan()
        token = json.loads(Path(plan.env[sl.ENV_LAUNCH]).read_text(encoding="utf-8"))
        token["nonce"] = "f" * 32
        Path(plan.env[sl.ENV_LAUNCH]).write_text(json.dumps(token), encoding="utf-8")
        self.refused(self.probe(plan.env), "nonce does not match")

    def test_a_missing_or_empty_variable_is_refused(self):
        for name in ("WEBVIEW2_USER_DATA_FOLDER", "VVLAB_LIBRARY", "VVLAB_CONFIG", "VVLAB_MODULES", "APPDATA", "LOCALAPPDATA"):
            for value in (None, ""):
                with self.subTest(variable=name, value=value):
                    plan = self.launch_plan()
                    env = dict(plan.env)
                    if value is None:
                        del env[name]
                    else:
                        env[name] = value
                    self.refused(self.probe(env), f"{name} is not set")

    def test_a_variable_that_differs_from_the_token_is_refused(self):
        plan = self.launch_plan()
        decoy = tempfile.mkdtemp(prefix="vv-guard-decoy-")
        self.made.append(decoy)
        env = dict(plan.env)
        env["VVLAB_LIBRARY"] = decoy
        self.refused(self.probe(env), "VVLAB_LIBRARY is not the value in the launch token")

    def test_a_decoy_folder_outside_the_token_directory_is_refused_even_when_the_token_names_it(self):
        for name in ("WEBVIEW2_USER_DATA_FOLDER", "VVLAB_LIBRARY", "VVLAB_CONFIG", "VVLAB_MODULES", "APPDATA", "LOCALAPPDATA"):
            with self.subTest(variable=name):
                plan = self.launch_plan()
                decoy = tempfile.mkdtemp(prefix="vv-guard-decoy-")
                self.made.append(decoy)
                token_file = Path(plan.env[sl.ENV_LAUNCH])
                token = json.loads(token_file.read_text(encoding="utf-8"))
                token["paths"][name] = decoy
                token_file.write_text(json.dumps(token), encoding="utf-8")
                env = dict(plan.env)
                env[name] = decoy
                self.refused(self.probe(env), "outside the token directory")

    def test_a_path_that_climbs_out_of_the_token_directory_is_refused(self):
        plan = self.launch_plan()
        outside = tempfile.mkdtemp(prefix="vv-guard-decoy-")
        self.made.append(outside)
        tricky = os.path.join(plan.token_dir, "library", "..", "..", os.path.basename(outside))
        token_file = Path(plan.env[sl.ENV_LAUNCH])
        token = json.loads(token_file.read_text(encoding="utf-8"))
        token["paths"]["VVLAB_LIBRARY"] = tricky
        token_file.write_text(json.dumps(token), encoding="utf-8")
        env = dict(plan.env)
        env["VVLAB_LIBRARY"] = tricky
        self.refused(self.probe(env), "outside the token directory")

    def test_a_network_path_is_refused(self):
        plan = self.launch_plan()
        token_file = Path(plan.env[sl.ENV_LAUNCH])
        token = json.loads(token_file.read_text(encoding="utf-8"))
        token["paths"]["VVLAB_CONFIG"] = r"\\localhost\c$\vv-guard-decoy"
        token_file.write_text(json.dumps(token), encoding="utf-8")
        env = dict(plan.env)
        env["VVLAB_CONFIG"] = r"\\localhost\c$\vv-guard-decoy"
        self.refused(self.probe(env), "VVLAB_CONFIG")

    def test_a_user_data_dir_browser_argument_is_refused(self):
        plan = self.launch_plan()
        env = dict(plan.env)
        env[sl.BROWSER_ARGUMENTS] = "--remote-debugging-port=9333 --user-data-dir=" + plan.token_dir
        self.refused(self.probe(env), "user data directory")

    def test_a_token_directory_that_is_a_known_folder_root_is_refused(self):
        # The token directory is the real Local AppData itself: nothing is created or written there, the guard
        # only compares paths and refuses before any file is renamed.
        local = os.environ["LOCALAPPDATA"]
        plan = self.launch_plan()
        env = dict(plan.env)
        token_file = Path(env[sl.ENV_LAUNCH])
        token = json.loads(token_file.read_text(encoding="utf-8"))
        token["token_dir"] = local
        token_file.write_text(json.dumps(token), encoding="utf-8")
        self.refused(self.probe(env))
        self.assertTrue(token_file.exists(), "a refused token is not consumed")

    def test_a_direct_launch_refuses_before_writing_anything(self):
        plan = self.launch_plan()
        env = {k: v for k, v in plan.env.items() if k not in (sl.ENV_LAUNCH, sl.ENV_NONCE)}
        result = self.probe(env, args=())  # no --guard-only: the real start path
        self.refused(result, "refused to start")
        for name in ("VVLAB_CONFIG", "VVLAB_LIBRARY", "VVLAB_MODULES", "WEBVIEW2_USER_DATA_FOLDER"):
            self.assertEqual(os.listdir(env[name]), [], f"{name} was written to by a refused start")
        self.assertFalse(os.path.exists(os.path.join(env["VVLAB_CONFIG"], "studio.log")))

    def test_the_self_test_flag_does_not_bypass_the_guard(self):
        plan = self.launch_plan()
        env = {k: v for k, v in plan.env.items() if k not in (sl.ENV_LAUNCH, sl.ENV_NONCE)}
        report = os.path.join(plan.token_dir, "self-test.json")
        result = self.probe(env, args=("--self-test", report))
        self.refused(result, "refused to start")
        self.assertFalse(os.path.exists(report))

    def test_the_helper_refuses_to_probe_a_release_executable(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "vv-studio.exe"
            fake.write_bytes(b"MZ" + sl.RELEASE_IDENTIFIER.encode() + b"\0")
            with self.assertRaises(sl.IsolationError):
                sl.guard_probe(str(fake), dict(os.environ))


class GuardSources(unittest.TestCase):
    """Facts about the sources that need no executable."""

    def test_the_guard_runs_first_in_main_and_before_the_self_test(self):
        text = (ROOT / "desktop" / "studio" / "src" / "main.rs").read_text(encoding="utf-8").replace("\r\n", "\n")
        body = text[text.index("fn main() {"):]
        context = body.index("tauri::generate_context!()")
        guard = body.index("guard::enforce(")
        self.assertLess(context, guard)
        self.assertLess(guard, body.index('"--self-test"'))
        self.assertLess(guard, body.index("tauri::Builder::default()"))
        self.assertEqual(text.count("tauri::generate_context!()"), 1, "bound once: the guard and the app use the same context")

    def test_modules_honouring_is_keyed_on_the_identity_and_not_on_the_build_profile(self):
        text = (ROOT / "desktop" / "studio" / "src" / "main.rs").read_text(encoding="utf-8")
        self.assertNotIn("cfg!(debug_assertions)", text)
        self.assertIn("development\n                .then(|| std::env::var_os(\"VVLAB_MODULES\"))", text.replace("\r\n", "\n"))

    def test_no_cargo_feature_or_profile_switches_the_guard(self):
        for path in (ROOT / "desktop" / "studio" / "Cargo.toml", ROOT / "desktop" / "Cargo.toml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("guard", text.lower(), str(path))
        rust = (ROOT / "desktop" / "studio" / "src" / "guard.rs").read_text(encoding="utf-8").split("#[cfg(test)]")[0]
        self.assertNotIn("cfg(feature", rust)
        self.assertNotIn("debug_assertions", rust)

    def test_the_refusal_writes_no_log(self):
        rust = (ROOT / "desktop" / "studio" / "src" / "guard.rs").read_text(encoding="utf-8").split("#[cfg(test)]")[0]
        for forbidden in ("log_line", "fs::write", "File::create", "create_dir", "OpenOptions"):
            self.assertNotIn(forbidden, rust)
        self.assertIn("std::process::exit(REFUSED_EXIT)", rust)

    def test_the_exit_code_matches_the_helper(self):
        rust = (ROOT / "desktop" / "studio" / "src" / "guard.rs").read_text(encoding="utf-8")
        self.assertIn(f"pub const REFUSED_EXIT: i32 = {sl.REFUSED_EXIT};", rust)

    def test_the_guarded_variables_match_the_helper(self):
        rust = (ROOT / "desktop" / "studio" / "src" / "guard.rs").read_text(encoding="utf-8")
        block = rust[rust.index("pub const GUARDED"):rust.index("];", rust.index("pub const GUARDED"))]
        self.assertEqual(sorted(__import__("re").findall(r'"([A-Z0-9_]+)"', block)), sorted(sl.TOKEN_SUBFOLDERS))


if __name__ == "__main__":
    unittest.main()
