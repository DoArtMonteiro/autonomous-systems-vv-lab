# Round-3 review of run-budget final code

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised. Its findings were applied afterwards; the fixes were not re-reviewed.

VERDICT: ACCEPT WITH FIXES

Both round-2 MAJOR holes are closed. The new closure feature has one real bypass, and the docs leave out the deployment gap.

**Round-2 holes, reproduced in scratch repos**
- **Rename or new id:** I reserved 10/10 on `a`, then `git mv` to `b` with a new id, same prereg and seeds. It was refused ("histórico apaga ou renomeia"). A new id with a different prereg path and the same seeds was refused for the same reason.
- **Fresh orphan, same ledger dir:** a new id with a different prereg path but the same seeds was refused by the ledger scan. An orphan with a new id and disjoint seeds is allowed. That is a legitimately new campaign, and the unverifiable-approval limit is documented.
- **Orphan, same id, higher `max_runs`:** refused with no amendment. With one amendment against a recorded `n_amendments` of 0 it is allowed (11 reserved), as designed. After that, the same id with 1 amendment at a higher `max_runs` was refused.
- **Invented amendments:** a fresh orphan with two invented amendments (against a recorded 1) would be allowed. This is the documented residual, since approval cannot be verified.

**Findings, most severe first**
1. `scripts/run_budget.py:531-537` and `:241-255` - **MAJOR** - A closed campaign can be reopened before any reservation attempt, and an orphan is not needed.
   - Closure is read only from HEAD's manifest, its HEAD-reachable history, and a ledger event written only on an attempted reservation.
   - I reserved 3 on `main`, branched `old`, committed the closing amendment on `main`, and made no attempt on the closed state. On `old` (a stale worktree) the reservation was allowed (total 4).
   - An orphan with an open manifest was also allowed (total 5).
   - After one attempt on the closed state wrote the `closed` event, `old` was refused.
   - Fix: on every reservation, scan all refs for any version of the manifest with `status: closed`, for example `git log --all --full-history -- rel`, plus `git for-each-ref`. Refuse if any version is closed and HEAD is not. This does not cover a rewritten history that was already garbage-collected.
   - Also write the `closed` event from `guard_report` and any other state read, and say this in the docs.
2. `docs/run-budget.md` and `docs/incidents/2026-11-23-m10-run-cap.md` - **MAJOR (honesty)** - Neither states that no `budgets/*.json` manifest exists and no script calls `run_budgeted`.
   - `ls budgets` fails. The incident's "Salvaguarda" section reads as if the safeguard were deployed.
   - Only "Os scripts anteriores continuam limitados só por invocação" hints at it.
   - Fix: add a "Estado atual" paragraph saying the safeguard protects nothing until a manifest is committed and a script is migrated.
3. `scripts/run_budget.py:269-273` - **MINOR** - The deletion scan uses the pathspec `budgets/`, so deleting any file there, such as a README, permanently blocks every campaign. I confirmed this with `budgets/README.md`.
   - The docs say "`budgets/*.json`". The same happens when a mistaken manifest-add commit is reverted.
   - Fix: restrict the pathspec to `budgets/*.json`, or document that any deletion under `budgets/` blocks every campaign.
4. `scripts/run_budget.py:295-298` - **MINOR** - `read_bytes()` on a neighbour ledger that is unreadable or a directory raises an uncaught `PermissionError` instead of `BudgetError`. Fail-closed still holds, but a caller catching `BudgetError` misses it.
   - A neighbour ledger read while another process appends to it (no lock taken) can show a torn tail and cause a transient refusal. I confirmed the torn-tail refusal. Fix: catch `OSError`, and skip or retry a final line without `/n`.
5. `scripts/run_budget.py:244-263` - **MINOR (unverified)** - `_check_history` assumes a linear order of `--full-history` output. A legitimately merged manifest history with conflicting amendment edits could be refused. It fails closed. I did not test it.

**Neighbour-ledger scan**
- Cost is linear in the number of ledger lines and is fine.
- An empty neighbour and a corrupt neighbour behaved correctly (allowed and refused respectively).

**Determinism**
- `utc`, `pid` and `head` appear only in the ledger entry, never in a hashed artefact. No other script imports the module.

**Race test**
- In a scratch copy with the lock removed (keeping the directory creation), `test_multi_process_race_never_exceeds_the_cap` failed with 8 != 3. The test does detect a missing lock.

CHECKED: `scripts/run_budget.py` in full and `docs/run-budget.md` in full. I read only the tail of the incident doc, `tests/test_run_budget.py` partially, and the `RaceTests` class by running it.
- `python -m unittest tests.test_run_budget`: 59 tests, OK.
- `python -m unittest discover -s tests -p "test_*.py"`: 502 tests, OK (89 skipped).
- Scratch-repo scripts: `exp.py` and `exp2.py` in the scratchpad directory.

NOT CHECKED: Linux/`flock` behaviour, merge-history ordering (finding 5), cross-clone behaviour, and the `desktop/` launch paths.
