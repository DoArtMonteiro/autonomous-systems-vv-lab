# Re-review run-budget fixes

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised.

VERDICT: ACCEPT WITH FIXES

49 budget tests pass (about 42 s). The full suite passes: 492 tests, 89 skipped, OK.

| # | Status | Evidence |
|---|---|---|
| 1 GIT_* env | FIXED | `scripts/run_budget.py:123` strips every `GIT_*` variable. The test at `tests/test_run_budget.py:303` sets valid bogus GIT_DIR, GIT_COMMON_DIR and GIT_WORK_TREE. |
| 2 seeds.rs | FIXED | `scripts/run_budget.py:276-300` reads the HEAD blob. Strings and comments are stripped first. Parsing is strict decimal, with the `start <= end` check and the required ranges. The real `seeds.rs` parses. |
| 3 public API | FIXED | `scripts/run_budget.py:556-591` takes no location parameters. The `_` hooks are separate, and a signature test exists. |
| 4 tip file | FIXED | `scripts/run_budget.py:424-443`. Truncation or deletion of one of the two files is detected. The docs state that deleting both is not prevented (`docs/run-budget.md:95`), and a test covers it. |
| 5 declared_unrecorded | FIXED | `scripts/run_budget.py:536-542` requires distinct run_ids whose count equals `declared_unrecorded`. |
| 6 AST lint | FIXED | The tests cover ProcessPoolExecutor (including via an attribute), multiprocessing, os.system, `__import__` and importlib. Blind spots are documented at `docs/run-budget.md:98`. |
| 7 manifests and amendments | PARTLY | See new findings 1 and 2. Overlap checks and the git-log history check work only against manifests and history on the current HEAD. |
| 8 torn line and dir fsync | FIXED | `scripts/run_budget.py:386-393`; the recovery procedure is at `docs/run-budget.md:88`. The directory fsync is a no-op on Windows, which the docs word as "onde o sistema o permite". |
| 9 manifest in lock | FIXED | `scripts/run_budget.py:452-453`. |
| 10 autocrlf | FIXED | `.gitattributes` has `*.json text eol=lf`, and the autocrlf test passes. |

**New findings**

1. MAJOR, `scripts/run_budget.py:254-273` and `docs/run-budget.md:31` (new campaign id restores the budget). I reproduced this in a scratch repo, and it is a plausible agent mistake.
   - Reserve 10 of 10 on campaign `a`, then `git mv budgets/a.json budgets/b.json` with `campaign_id` changed and commit.
   - Campaign `b` is then granted a fresh 10 runs, with the same preregistration path and the same seeds.
   - `_check_other_manifests` only looks at manifests present in HEAD, and `_check_history` follows a single path with no rename tracking.
   - The doc sentence "Um identificador novo não repõe o registo de outra campanha" is false in this case.
   - Fix: record `preregistration.path` in each ledger entry. On every reservation, scan the other `*.jsonl` files in the ledger directory and refuse an id whose preregistration path or seed range overlaps an existing ledger. Also refuse HEAD histories in which a `budgets/*.json` file was deleted (`git log --diff-filter=D -- budgets/`). Add a rename test.

2. MAJOR, `scripts/run_budget.py:232-251` (rise without amendment on a branch without history).
   - I committed the same id on an orphan branch with `max_runs` 99999 and no amendments, and the reservation was accepted.
   - `git log` shows a single commit, so the "only rises with a new amendment" rule is never applied.
   - The ledger already holds `max_runs` in every entry, but it is not cross-checked.
   - Fix: refuse when `manifest.max_runs` is greater than `entries[-1].max_runs` and the manifest's amendments are not strictly longer than the amendment count recorded in the ledger. This needs `n_amendments` in the ledger entry. It closes the orphan, shallow-clone and force-push cases.

3. MINOR, `docs/run-budget.md:95`. The doc says deleting only trailing lines is detected. Truncating the same trailing lines of both the ledger and the tip is not detected. Deleting just the tip is accepted (that is the crash-recovery rule), so truncating the ledger afterwards also goes unseen. State this explicitly.

4. MINOR, `scripts/run_budget.py:234`. `git log HEAD -- rel` uses default history simplification, so merge histories may omit versions. Add `--full-history`.

**Other questions**

- Lowered `max_runs` via amendment: this is not a bypass. `before + n > manifest.max_runs` is stricter, the total carries over, and `_validate_manifest` plus `_check_history` refuse decreases.
- Tip file: it is always read and written inside the same lock, so there is no TOCTOU. Reset by a fresh campaign id is the same hole as finding 1, because each id has its own tip.
- Reserve before spawn and no refunds: still atomic, in `_run_budgeted` at `scripts/run_budget.py:493`.
- Race test: I disabled `_lock` in a scratch copy and `RaceTests` failed 3 out of 3 times, so the test is meaningful.

CHECKED: `scripts/run_budget.py` in full, `docs/run-budget.md` in full, the relevant parts of `tests/test_run_budget.py`, both test runs above, and scratch experiments in `<scratchpad>/exp.py` and `.../nolock2`.

NOT CHECKED: Linux/macOS `flock` behaviour, the directory fsync on POSIX, every AST-lint evasion form, and the worktree test beyond the fact that it passes.
