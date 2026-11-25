# Review run-budget safeguard branch

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised.

VERDICT: ACCEPT WITH FIXES

Both suites pass. `tests.test_run_budget` ran 29 tests with no failures. The full discovery ran 472 tests, 89 skipped, with no failures. I also checked that the race test is meaningful: in a scratch copy I disabled the lock, and the race test then failed with `8 != 3`, so it does catch a missing lock. Nothing here is a blocker. The core design is sound: it reserves before spawning, takes the lock before reading and appending, and fails closed.

Findings, most severe first:

1. `scripts/run_budget.py:107-114` (`_git`) - MAJOR - Git runs with the inherited environment. `GIT_COMMON_DIR` and `GIT_DIR` redirect `rev-parse --git-common-dir` to another ledger location. `GIT_DIR` can also redirect the `HEAD:` manifest blob. I confirmed git honours `GIT_COMMON_DIR` here (a bogus value changed the result). This contradicts the claim of "no environment override", and `test_no_environment_or_cli_override_of_the_location` only looks for `os.environ` in the Python source. Fix: pass `env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")}` to the subprocess, and add a test that sets `GIT_COMMON_DIR` to a valid directory and checks the location does not move.

2. `scripts/run_budget.py:208-219` (`protected_ranges`) - MAJOR - The parse is not fully fail-closed. It only fails if zero ranges match. A range written in hex, as an expression, or with `end` before `start` is silently skipped. A comment containing "start: 1, end: 2" would over-match. The file is read from the working tree, not from the HEAD blob, so an uncommitted edit to `seeds.rs` weakens the guard. The manifest is held to HEAD but this file is not. Fix: read `seeds.rs` through `git cat-file blob HEAD:exec/src/seeds.rs`, and require the number of matches to equal the number of `Protected {` literals minus the struct definition (currently 18 against 19, so tolerate the definition explicitly). Add a test that removes one entry or uses an unsupported format and expects refusal.

3. `scripts/run_budget.py:319-320, 362-363` - MAJOR - `ledger_dir` and `repo` are public parameters of `reserve`, `run_budgeted`, `recount` and `guard_report`. Passing `ledger_dir=tmp` gives a fresh empty ledger, and passing `repo=` gives another manifest. A caller error therefore resets the budget, the exact failure mode in the incident. The docs say "só os testes a indicam", but nothing enforces it. Fix: keep the public API without these parameters and expose the test hooks through an underscore-prefixed internal entry point. At minimum, list this under "O que não protege".

4. `docs/run-budget.md:50` and `scripts/run_budget.py:285-308` - MAJOR (honesty) - The docs say a "truncada" ledger fails closed. That is true only for a partial final line. Deleting whole trailing lines, or the whole file, is undetected: the chain still validates and the total drops. Only the artefact recount would catch it, and only if someone calls `guard_report`. Fix: say so in the docs. Optionally record the ledger tip hash plus `seq` in a second append-only file, or in a commit-visible place.

5. `scripts/run_budget.py:421-426` (`guard_report`) - MINOR - Compensating errors pass. 5 unreserved runs plus 5 reserved runs with no artefact give `runs == ledger_total` with `declared_unrecorded=0`. `declared_unrecorded` is self-declared and unverified, so it can hide deleted artefacts. It cannot hide extra runs, so it is not a cap bypass. Fix: document it as a detective control that only detects a net excess, and have the caller list the `run_id`s of the failed runs.

6. `tests/test_run_budget.py:335-366, 411` (AST allowlist) - MINOR - It gives a false sense of security.
   - A script that imports `run_budget` and also spawns directly is accepted (`<uses run_budget>`).
   - `concurrent.futures.ProcessPoolExecutor`, `importlib`/`__import__`, and `getattr(os, ...)` are not detected.
   - `tests/`, `desktop/` and shell commands are not scanned.
   - About 25 scripts are allowlisted, including the real `vv-rocket` callers, and the allowlist lives in a file the agent can edit.
   The docs are honest about the scope. Fix: tighten the rule so a script that uses `run_budget` must have every spawn go through `spawn=`. At least add `ProcessPoolExecutor` and `concurrent.futures`.

7. `scripts/run_budget.py:337-339` and `docs/run-budget.md:54-63` - MINOR - The amendment check does not require the amendments list to be append-only, and it does not check them against the ledger. `max_runs` can go straight from 10 to 1,000,000 with any non-blank reason. By design this is a commit-level control, and the docs say so. Also, registering a new `campaign_id` with the same preregistration, or overlapping seeds, starts a new empty ledger. This is not mentioned in "O que não protege". Fix: list it as residual, or refuse a manifest whose `preregistration.path` or seeds overlap another one in `budgets/`.

8. `scripts/run_budget.py:355-358` - MINOR - A torn final line makes the campaign unusable and there is no sanctioned recovery path. The message says only "investigar". The first creation of the ledger file is not followed by an fsync of the directory. Fix: document the manual recovery, since it is a real crash path.

9. `scripts/run_budget.py:330-334` - MINOR - The manifest is read before the lock. Two worktrees on different HEADs can race on the `seen_max` check. It fails safe in practice (the lower cap wins), so this is theoretical. Fix: none needed, or move `load_manifest` inside the lock.

Not findings:

- CRLF and `autocrlf`: `.gitattributes` sets `*.json text eol=lf`, so the working file matches the blob even though system `core.autocrlf=true`. The tests force `autocrlf=false`, which hides this dependency. Add a `.gitattributes` assertion, or a test with `autocrlf=true`.
- Detached HEAD works. `git cat-file HEAD:path` is root-relative.
- Linked worktrees share the ledger, covered by `test_ledger_is_shared_by_linked_worktrees`. Running outside a git repo fails closed.
- No U+2014 in the diff. The diff text follows the Portuguese style on the points I checked, but I did not check it for AO1990 spelling.
- Nothing in the ledger or in `utc` and `pid` reaches hashed artefacts. Nothing outside the four added files changed.

CHECKED: the full diff (four files); `python -m unittest tests.test_run_budget -v` and full discovery (472 tests, OK); a scratch mutant with the lock disabled, which failed the race test as it should; `GIT_COMMON_DIR` influence on `rev-parse`; `.gitattributes` and `core.autocrlf`; the `seeds.rs` regex against the file's 18 entries; U+2014 count in the diff.

NOT CHECKED: Linux `flock` behaviour; real power-loss and `fsync` durability; the M10 campaign scripts on `research/m10-redesign`; whether `verification.json` is exactly one per run in real artefact trees; nothing was run with `vv-rocket` or the simulator.
