# Re-review Studio isolation fixes

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised.

VERDICT: ACCEPT WITH FIXES

Both test commands pass: `tests.test_studio_isolation` ran 51 tests OK, and the full discover run ran 494 tests OK (89 skipped). Finding 1 below means the Documents fix (item 6) is not actually delivered.

**Fix table**

| # | Item | Status |
|---|---|---|
| 1 | Cinematic uninstall guard | Done. The suite exits before any launch unless `--i-accept-installed-module-uninstall` is given. The installed example is gone, a warning is printed, and the residual risk is in the incident doc. |
| 2 | Docstrings | Done. The seven suites (`ui_smoke`, `m15`, `m16`, `m17_lab`, `perf_probe`, `m16_compare_shots`, `m17_tech_shots`) set preferences through scratch `VVLAB_CONFIG`. The only invokes they make are `set_prefs`, `get_prefs`, `record`, `replay`, `list_investigations`, `export_evidence` and `app_info`. They have no module install or uninstall calls. Not checked: whether Studio itself reads or writes the module folder at startup. |
| 3 | AST lint | Partly done. See findings 2 and 3 below. |
| 4 | Kill patterns | Done. The tests include both positive and negative cases. |
| 5 | m18 kills Godot before Studio | Done. |
| 6 | Documents known folder | **Not done.** See finding 1. |
| 7 | UNC / network paths | Done for UNC. `//?/C:/x` and `//./C:/x` normalise to `c:/x`, and `//?/UNC/...` and `//server/share` raise `IsolationError`. See finding 4 for non-drive device paths. |
| 8 | `docs/m11-acceptance.md` needs `-Release` | Done. |
| 9 | Directory-size explanation marked unverified | Done. |
| 10 | `build.ps1` productName assertions | Done. I read it statically and did not run it. The merged productName is checked before the build and the exe text is checked afterwards, in UTF-8 and UTF-16. |

**New findings**

1. `desktop/studio/tests/studio_launch.py` (`documents_folders`) - **MAJOR** - The `FOLDERID_Documents` GUID bytes are wrong. The code has `D039DDFD…`, but the correct little-endian bytes for `{FDD39AD0-238F-46AF-ADB4-6C85480369C7}` are `D09AD3FD…`. I called `SHGetKnownFolderPath` with the code's bytes and got `0x80070002`, so the lookup fails. The bare `except` hides this, and only the `%USERPROFILE%/Documents` guess is used. With the correct bytes the call returns 0 and the folder path. The redirected-Documents protection (for example OneDrive) therefore does nothing, and `test_the_default_launch_uses_the_known_folder_helper` only checks that the strings appear in the source. Fix: use `uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7").bytes_le`. Add a Windows-only test that `documents_folders()` includes the real known folder, and make a failed call visible instead of silent.

2. `tests/test_studio_isolation.py` (`SPAWNERS`) - **MINOR/MAJOR** - `subprocess.getoutput` and `getstatusoutput` are not in `SPAWNERS`. `subprocess.getoutput(exe)` runs through a shell and `launch_violations` returns `[]` for it. Fix: add both to `ALWAYS_FORBIDDEN`.

3. `tests/test_studio_isolation.py` (`_allowed_spawn`) - **MINOR** - The `['powershell','-NoProfile',…]` entry on the allowlist accepts any command text. `& $exe` and `Invoke-Item` pass, and `START_PATTERN` only matches `Start-Process`. Other bypasses are `importlib.import_module('subprocess')`, `exec`, `ctypes…ShellExecuteW`, and a Studio launch from `scripts/` such as `subprocess.run(cmd)`, which `studio_launch_violations` misses because it matches on the literal word "studio" in the arguments. Fix: allow PowerShell only with a literal string command containing no `&`, `Invoke-Item` or `Start-Process`. Accept that the lint guards against accidents and say so in the docs.

4. `desktop/studio/tests/studio_launch.py` (`normalise`) - **MINOR** - `//?/Volume{guid}/…` and `//?/GLOBALROOT/Device/…` are neither refused nor mapped to a drive. `//?/Volume{abc}/x` normalised to `volume{abc}/x`. Both can name the profile by another route and slip past `is_under`. Fix: after a device prefix, require `^[A-Za-z]://` or refuse.

5. `docs/incidents/2026-11-23-webview2-profile.md` - **MINOR** - The limitations text says the lint covers only `desktop/studio/tests/*.py`, but it now also scans `scripts/` and `docs/evidence`. Fix: update that sentence.

**Regressions**

- The documented dev-build forms are intact, and CI still uses `--owner-allow-release-exe` only with `ui_smoke`, `m15` and `m16`, which are on the audited list.
- The closed allowlist covers every call shape in the current scripts, since `test_no_script_starts_a_studio_outside_the_helper` passes on all of them.
- The Portuguese text I read has no U+2014 and reads as AO1990 Portuguese.

**CHECKED:** the full diff, both test runs, a live `SHGetKnownFolderPath` call with both GUIDs, lint probes against `launch_violations` and `studio_launch_violations`, `normalise` on UNC and device paths, and a grep of the audited suites for module and preference calls.

**NOT CHECKED:** `build.ps1` execution, anything that launches an app, and Studio's own startup behaviour on the module folder.
