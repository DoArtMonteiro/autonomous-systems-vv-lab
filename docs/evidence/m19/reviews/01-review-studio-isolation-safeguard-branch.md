# Review Studio isolation safeguard branch

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised.

VERDICT: ACCEPT WITH FIXES

I found no blocker for the incident itself. A development build can no longer share the installed profile, and no UI test launch can reach it without the owner flag. One destructive path remains behind the owner flag (finding 1). I read the Studio sources, the config files, the scripts and the evidence read-only.

Findings, most severe first:

1. `desktop/studio/tests/m17_cinematic_journey.py:6,107,177` - MAJOR - The documented invocation runs against the installed exe with `--owner-allow-release-exe`. In that mode `VVLAB_MODULES` is ignored (debug builds only), so the Studio uses `%LOCALAPPDATA%/org.vvlab.studio/modules/cinematic`. The script then calls `cinematic_uninstall` at line 107 if the module is present, and again at line 177. This deletes the owner's installed Cinematic module and reinstalls from a zip, which is a write to the installed profile that the guard does not block. The incident doc mentions only "can still write" in Godot's profile and the Cinematic module resolving to the installed profile, not this uninstall. Fix: have this script refuse `owner_allow_release_exe` outright, or require a second explicit flag (for example `--i-accept-module-uninstall`). Remove the installed-exe example from its docstring, and add the destructive behaviour to the incident doc's "Riscos que ficam".

2. The docstrings of 12 scripts and the `README.md` presentation advertise `--exe "%LOCALAPPDATA%/VV Lab Studio/vv-studio.exe" --owner-allow-release-exe` as the normal command (for example `ui_smoke.py:16`, `m15_journeys.py:7`). Q1 answer: the flag is never passed by default. Every call site takes `a.owner_allow_release_exe` from the CLI, and the only default is `allow_release=False` in `m16_journeys.launch`. But a person or agent who copies these lines is opting in, for suites whose modules or preferences they have not audited. This is not a safe default. Severity MAJOR (same root cause as finding 1). Fix: keep the owner-flag installed-exe examples only for suites known to be safe (CI uses it on a disposable runner), or add a one-line "owner only, installed profile modules are touched" note.

3. `tests/test_studio_isolation.py:312-335` - MINOR - The AST lint is bypassable.
   - It misses `subprocess.run(cmd)` when the argument is a variable other than `exe`, `studio_exe` or `studio`.
   - It misses `x = subprocess.Popen; x(...)`.
   - It misses `subprocess.run(["powershell","-Command", "Start-Process ..."])`.
   - It only scans `desktop/studio/tests/*.py`, not `scripts/` or `docs/evidence/.../live_check.py`. `live_check.py` goes through `sl.launch`, so it is fine today.
   - `test_every_launch_passes_the_owner_flag_explicitly` only checks that the keyword is present, so `allow_release=True` as a literal would pass. Fix: add a test that rejects a literal `allow_release=True` in any script, and forbid `Start-Process` and bare `Popen` aliases. The incident doc already admits the scan has limits.

4. The image-name kill regex does not cover the PowerShell aliases `kill` and `spps`, `Get-Process ... | % Kill()`, `wmic ... delete` or psutil name matching. Q2 answer: no `/IM`, no `Stop-Process`, and no name-based Godot kill remains. I grepped `desktop/studio/tests`, `scripts` and `.github`. The only remaining `Popen` calls outside the helper are `scripts/cinematic/bench.py` and `scripts/process_limits.py`, which start Godot and the simulators, not the Studio. Severity MINOR.

5. `desktop/studio/tests/m18_journeys.py` (`finally` block) - MINOR - `studio_launch.stop(proc)` runs before `kill_godot()`. It works because orphans keep their `ParentProcessId`, but the PID could in theory be reused. Fix: kill the Godot children first, then the Studio.

6. `desktop/studio/tests/studio_launch.py:90-95,208` - MINOR - The research library root is guessed as `%USERPROFILE%/Documents/VV Lab Library`. On a machine with Documents redirected (OneDrive), the real library is not protected against a hostile pre-set `VVLAB_LIBRARY`. Scratch is the default, so this only matters for a hostile caller. Fix: resolve the Documents known folder, or document it.

7. `desktop/studio/tests/studio_launch.py:normalise` (Q3) - MINOR - I ran edge cases against the real `LOCALAPPDATA`.
   - Refused: 8.3 short name (`ORGVVL~1.STU`), `//./` device path, forward slashes, `%VAR%`, case, trailing separators and dots, `..`, `//?/`, and a `--user-data-dir` with spaces.
   - Missing `LOCALAPPDATA`/`APPDATA`: fails closed.
   - Allowed (gap): the UNC loopback form `//localhost/C$/.../org.vvlab.studio/EBWebView`. Fix: reject any path starting with `//` unless it is `//?/` or `//./`.
   - Junctions: `os.path.realpath` is applied on `nt` to the scratch variables, so they are covered. Only the `_mentions` text scan of other variables uses the unresolved string.

8. `docs/m11-acceptance.md:9,41` - MINOR - It still says a local build with `desktop/build.ps1` gives the installer. That is now `-Release`. Fix: update both lines.

9. `docs/evidence/m19/isolation/README.md` (Q6) - MINOR - The disclosure is honest. It states three launches and the empty `%LOCALAPPDATA%/org.vvlab.devstudio` folder. The explanation of the first run's differing hashes (27 empty directories changing from size 0 to 4096) is unverifiable, because the first listing was discarded. It is also odd that Windows `lstat` would report a directory size of 4096. Fix: say it is unverified, or drop the causal claim.

Q4 (identifier and release path):
- The only code paths I found that derive paths from the identifier are Tauri's `app_config_dir` and `app_local_data_dir`, plus the single-instance mutex. No Rust or other JSON file hardcodes it (a test enforces this).
- No updater or deep link is configured, and there are no golden files or evidence tied to `productName`.
- The release overlay restores exactly `org.vvlab.studio` and `VV Lab Studio`. The NSIS folder and uninstall key come from `productName`, so a `-Release` build keeps upgrading the 0.18.1 install.
- The `-Release` assertions are sound: the identifier is checked before the build, the compiled exe is checked after (exactly one identifier, case-sensitive), and an ambient `TAURI_CONFIG` is refused.
- The CI edit is correct: `-Release` on the installer job, and the owner flag on the three suites that run against the installed exe on the disposable runner.
- Gap: the release path never asserts `productName`.
- Caveat the authors disclose: `build.ps1` was never run end to end.

Q5 (`embedded_identifiers`): reading UTF-8 and UTF-16 substrings is reliable. `devstudio` does not contain the release string, and "neither identifier" fails closed. A dev exe that happened to embed the release string for another reason would be refused, which is the safe direction.

Q7 (docs): no U+2014 and no personal paths in the added lines. The incident doc matches the base tree (five direct `Popen` sites, four `/IM` launchers, Godot killed by name in `m18`). The Portuguese looks European. I did not check Acordo Ortográfico spelling exhaustively.

CHECKED:
- `python -m unittest tests.test_studio_isolation -v`: 37 tests OK.
- Full `python -m unittest discover -s tests -p "test_*.py"`: 480 tests OK, 89 skipped. Neither run launches an app, as the isolation test is pure and reads files only.
- The full diff of `studio_launch.py`, `build.ps1`, the two Tauri configs, `ci.yml`, every suite call site, and `main.rs` lines 640-670.
- My own edge-case probe of `plan_launch`, with a scratch script outside the repo.

NOT CHECKED:
- `build.ps1` end to end, and the NSIS packaging.
- Any launch of a Studio.
- The Linux CI run of `tests/test_studio_isolation.py`. The `ntpath` code on POSIX looks fine, but I did not run it.
- The claims in the live evidence (listing hashes), which I cannot reproduce without launching.
