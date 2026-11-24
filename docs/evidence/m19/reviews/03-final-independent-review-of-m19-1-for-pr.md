# Final independent review of M19.1 for PR

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised.

VERDICT: READY WITH FIXES

I found no BLOCKER or MAJOR issue. The fixes are all minor documentation items to fix before opening the PR.

**Findings, most severe first**

1. `docs/m19-1-honesty.md:78` - MINOR - It says the Node file has "41 testes depois". The file now has 42 `test(` cases (`node tests/ui_requirements.test.mjs` prints "42 tests passed"). The count went up when 776e19d added the gloss test. Fix: change it to 42.
2. `docs/evidence/m19/reviews/01-independent-review-of-m19-1-honesty-branch.md:41` - MINOR - The text says "paths anonymised" but still names the local worktree root `D:/vvwt` inside a grep description. AGENTS.md forbids publishing personal paths. Fix: replace it with `<worktree>`. The same file's "41 test cases" statement is stale (see finding 1) and could be noted as written before 776e19d.
3. `docs/m19-1-honesty.md` ("Revisões independentes por agentes") - MINOR - It correctly says the third review report is not in `docs/evidence/m19/reviews/`. The "Quebra do passo 4" section is an honest disclosure of the profile breach. Fix: repeat that disclosure in the PR body so a reviewer does not miss it.
4. `desktop/studio/ui/js/views/{compare,prepare,run}.js` - MINOR (maintainability) - `expectationGloss(...)` is called twice per site. Fix: bind it to a local variable.

**Verified, no issue**
- **Scope and protected evidence:** `git diff bec7b3f..HEAD --name-only` shows no `.rs`, `crates/`, `src/`, `exec/` or `scenarios/` changes. It also shows no change to any existing `docs/evidence` file outside the new `m19` folders.
- **Hash comparison:** I read `hashes-before.json` for the 413 per-file entries (`evidence_files` + `m1_and_test_fixtures`) and fetched each file with `git show bec7b3f:<path>` and `git show HEAD:<path>`.
  - The blobs are identical at `bec7b3f` and `HEAD` for all 413.
  - 380 match the recorded hash directly. The other 33 differ only because `hash_set.py` hashes the working tree (`w/crlf`, autocrlf). Hashing the same blob with CRLF applied reproduces the recorded value (3 sampled).
  - `demonstration_runs`, `m1_basic_mission_seed42`, `source_sha256` and `staged_binaries` are equal in before and after. `hash-comparison.json` states 542 compared, 542 identical, 0 different.
  - `after_head` is 776e19d. The commits after it change only docs and evidence, so the UI code is unchanged since then.
- **Proposals doc against the code:**
  - **Run id:** `run_id` is at `desktop/platform/src/service.rs:271-279` and `host_sha256` is read at 153-155. The brief said `desktop/studio/src/service.rs`; the doc's path is the correct one.
  - **Quoted texts:** every `expectation` and `look_at` line it quotes matches `demos.rs` and `catalog.rs` (lines 91 to 167 and 439 to 515).
  - **Record and incomplete runs:** the incomplete branch and requirement in `record.rs` match the doc. `mission_analysis.rs:349-366` gives `Incomplete` when no waypoints remain. The three ground runs with outcome `incomplete` match the catalog text.
  - **Run counts and tests:** 13 rocket and 8 ground demonstration runs are in `hashes-after.json`. The host tests only assert that the text is non-empty.
  - **Migration:** the `service.rs` replay-fallback and "different host build" behaviour matches what the doc describes.
  - Neither proposal is implemented in this branch.
- **776e19d:** `expectationGloss` shows only for `/b(safe|unsafe|safety)/b`. The Node test covers hit, miss, "unsafely" and `undefined`. The row 15 wording matches `Go to ${timeText(...)}` in `player.js:836`, and no "Go there" remains.
- **Journey reruns (9e813bc):** the counts in `journeys-rerun/README.md` match the final line of each file in `suites/` (80, 48, 78, 34, 71, 90, 67). There are no FAIL lines, and `surfaces-results.txt` shows 14/14. The `m18` difference of 71 against 72 is explained by the Cinematic module not being installed in that build.
- **Docs hygiene:** my sweep for U+2014 found none in the added lines. The `D:`, `C:/Users` and `AppData` check found only `%USERPROFILE%` forms and finding 2. No Brazilian-Portuguese spellings turned up. Commit messages follow `tipo: descrição`.
- **Cinematic module (open point):** `docs/m19-1-honesty.md:47` says the module package was not rebuilt and the version must be raised for any release. I checked the repository: `project.godot` still says `0.2.8` and there is no committed manifest. That is consistent with the doc.
- **Tests:** `python -m unittest discover -s tests -p "test_*.py"` ran 468 tests, OK, with 92 skipped. `node --test tests/ui_requirements.test.mjs` passed.

**CHECKED:** the diffs of 776e19d, 87d9ddf, dde0620 and 9e813bc; the whole-branch diff of `requirements.js`, `model.js`, `player.js`, `rocket.js`, `provenance.js`, the `hud.gd`, `record.gd` and `main.gd` changes, and the CSS selectors for `held`; the hash cross-check above; the two test commands.

**NOT CHECKED:**
- No app launched and no screenshots viewed; the PNG evidence was not opened.
- Rust, `cargo`, the campaign and the Godot-gated tests were not run, and I did not rebuild the staged binaries.
- I did not reread the full `lab.js`, `discover.js` or `control.js` diffs, which earlier rounds covered.
- I did not confirm that every ground-vehicle demonstration whose `look_at` mentions "safe" also has a safety word in its `expectation` (the gloss is keyed on `expectation` only).

**PR summary suggestion**
1. UI-only M19.1: requirements and safety rules are separate verdicts. "Held" is neutral, never green, and unevaluated rows are never counted as met.
2. Failed mission completion states what the record says and does not say. Pills keep the run identity on short windows.
3. Model limits are stated: no plume after the last sample, booster impact not modelled, and contact speeds named as the verifier's.
4. No change to Rust, `crates/`, `src/`, `exec/`, `scenarios/` or protected evidence; 542 of 542 must-not-change hashes are identical. Two host-hash-changing proposals are documented in `docs/m19-1-hash-changing-proposals.md` and not implemented.
5. Evidence: 468 Python tests and 42 Node tests pass; seven journey suites and a surfaces run were repeated with profile isolation. The WebView2 profile breach and the three agent review rounds (not human review) are disclosed in `docs/m19-1-honesty.md`.
