# Round-3 review of isolation incl. Godot helper

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised. Its findings were applied afterwards; the fixes were not re-reviewed.

VERDICT: ACCEPT WITH FIXES

I found one real regression and a few smaller gaps. The round-2 items are correct.

**Findings, most severe first**

1. `desktop/studio/tests/ux_journeys.py:276` - MAJOR - `newest_log()` is still called with no argument, but 3bbb05c changed it to `newest_log(proc)`. This raises `TypeError` in the "experiment" Cinematic check. Nothing catches it: `py_compile` passes and the unit tests never run that journey. Fix: call `newest_log(proc)`. `proc` should be the Studio process in scope there, but I did not confirm that. Then add a lint or test that every call site of `newest_log` passes an argument.

2. `tests/test_studio_isolation.py:679-690` (`godot_violations`) - MINOR - the lint only sees the literal `subprocess.run`, `subprocess.Popen` and similar spellings, and only when the first argument contains "godot" or `console`. I ran it on these cases and none was flagged:
   - `import subprocess as sp; sp.run([godot, ...])`
   - `from subprocess import run; run([godot, ...])`
   - `cmd=[g, ...]; subprocess.run(cmd)`
   - `subprocess.run([GD, ...])`
   - `os.spawnv`

   `launch_violations` catches the alias and from-import forms, but only for `desktop/studio/tests/`, not for `tests/`, `scripts/` or `docs/evidence/`. The docs do say the lint guards against accidents only. Fix: apply the alias and from-import checks to every scanned folder, or flag any `subprocess` start in files that mention `VV_GODOT` and are not on an allowlist.

3. `desktop/studio/tests/studio_launch.py` `stop()` - MINOR - `shutil.rmtree` runs on `proc.redirect_dirs` with no check beforehand. In practice those folders always come from `mkdtemp`, but `make_scratch` can be injected. Fix: before deleting, require the folder to sit under `tempfile.gettempdir()` and carry the `vv-` prefix, and refuse a drive root or a profile root. Separately, `plan_launch` and `plan_godot` leave empty scratch folders behind when they raise after `mkdtemp`. `bench.py` leaks its scratch if `wait` raises, because the cleanup is not in a `finally`.

4. `desktop/studio/tests/godot_launch.py:82` - MINOR - `_plan` reads `APPDATA` and `LOCALAPPDATA` from `os.environ` and raises when they are empty. On Linux or macOS with `VV_GODOT` set, every Godot test errors, even though `plan_godot` has POSIX handling. Fix: fall back to the home-based paths, or skip the profile check off Windows.

5. `scripts/cinematic/bench.py` - MINOR - every run now starts with an empty shader and Vulkan pipeline cache. Existing benchmark numbers may not be comparable with new ones. Fix: state this in the benchmark documentation, or warm the cache first.

6. `docs/incidents/2026-11-23-webview2-profile.md` - MINOR, documentation accuracy:
   - It says "377 files" in the facts section and "528 entries" in the verification section. State that these are two different counts, files versus files plus folders.
   - It cites `docs/m19-1-honesty.md`, which is not in this worktree.
   - "O responsável decidiu deixá-la" is asserted with no source in the repo.
   - `docs/evidence/m19/isolation/build-e2e.md` (from the earlier commit aae4214) contains `<worktree:safe>` paths, which breaks the rule against personal paths.

**Answers to your questions**

- **Round-2 items:** the Documents GUID is correct. `uuid.UUID('FDD39AD0-238F-46AF-ADB4-6C85480369C7').bytes_le` gives `d09ad3fd8f23af46adb46c85480369c7`, which matches the Windows struct layout. The device-path refusals work: `//?/Volume`, `GLOBALROOT`, `PhysicalDrive`, `UNC` and `Harddisk0` are refused. `/??/UNC/...` is not refused, only resolved against the current drive, which is harmless. I did not review the lint additions beyond reading the code.
- **Studio child with scratch `APPDATA`/`LOCALAPPDATA`:** the Rust code in `main.rs` takes only `USERPROFILE` and the `VVLAB_*` variables from the environment. Tauri's `app_config_dir` and `app_local_data_dir` come from known-folder calls, so they should not move into scratch, and the module folder stays in `org.vvlab.devstudio`. This is consistent with the other redirects. The Godot child that Studio spawns inherits the scratch environment, which is the intent. The claim that WebView2 uses the known-folder API was not verified. The incident doc says the live run left the installed profile untouched, but it did not show where the dev Studio's own data went.
- **Godot start paths:**
  - All the tests and scripts you listed go through `godot_launch.run` or `popen`.
  - The `--shot` calls in `ux_journeys.py`, `review_captures.py` and `installed_spotcheck.py` go through the helper.
  - Studio-spawned Godot gets scratch via `plan_launch`.
  - `m18_journeys.py` has no Godot start of its own.
  - The only remaining way back to the real folder is a Godot started by hand, as the doc says, plus the lint gaps in finding 2.
- **Docs:** no U+2014 in the changed docs or `godot_launch.py`.

**CHECKED:**
- `git show` for 3bbb05c.
- `godot_launch.py`.
- The lint and `stop()` code.
- The Rust env usage.
- A bypass probe against `godot_violations`.
- The GUID in Python.
- Device-path refusals.
- `python -m unittest tests.test_studio_isolation`: 67 tests OK.
- Full discover: 510 tests OK, 89 skipped. `VV_GODOT` was unset, so no Godot ran and no app launched.

**NOT CHECKED:**
- A live Godot run.
- Any Studio launch.
- Whether Godot honours `APPDATA` (I relied on the doc's probe).
- The listings of the real `%APPDATA%` folder.
- Whether Tauri and WebView2 read the environment variables.
- Commit 4365682's review records.
