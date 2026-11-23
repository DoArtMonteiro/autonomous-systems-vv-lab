# Review M19.1 follow-up commits

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

I ran both test commands. `python -m unittest tests.test_m191_honesty` ran 22 tests, all OK. `node --test tests/ui_requirements.test.mjs` passed, and the file has 41 `test(` cases, matching the docs. The diff touches no `.rs` file and nothing under `crates/`, `src/`, `exec/` or `scenarios/`. The two evidence-JSON changes are head stamps under `docs/evidence/m19/`. The `expectation` strings in `demos.rs` and `catalog.rs` are unedited, and `docs/m19-1-honesty.md` contains no U+2014.

Findings:

- `docs/m19-1-honesty.md:~27` (row 15) - MINOR - The doc says the button reads «Go to T+12.3 s». The code uses `timeText(d.t, pl.unit)`, which renders «Go to 4.70 s» (confirmed in `after-facts.json`) or «Go to tick 5» for ground runs. The time is derived from the divergence data (`d.t`), not hard-coded, so requirement 6 holds. Only the documented wording is wrong. Fix: write «Go to 4.70 s» (or «tick N» for ground runs) in the table, or add the "T+" prefix in code if that wording is wanted.

- `docs/m19-1-honesty.md:~21` (rows 10 to 15) - MINOR - A blank line separates row 9 from row 10, so the new rows render outside the table, without a header. Fix: remove the blank line.

- `desktop/studio/ui/js/requirements.js` (`EXPECTATION_GLOSS`) - MINOR - The gloss says «Words about safety in this text mean only that no safety rule was broken». That is accurate for "safe" and "every safety invariant met". It is backwards for "Unsafe" or "safety unsafe" in demos such as the ascent S1 demo and the ground fault demos, where a rule was broken. It also appears under every demo, including ones that never mention safety. It does not overclaim, but it can mislead on the unsafe texts. Fix: reword to «"safe" here means only that no safety rule was broken, and "unsafe" that one was; requirements are separate verdicts». The Node test asserts `doesNotMatch(/safe/i)` on the sentence, so it would need updating.

- `docs/evidence/m19/honesty/hashes-after.json`, `hash-comparison.json` - MINOR - `git_head` and `after_head` are stamped d35a38b, but HEAD is 124a1e4. `git diff 7243549..HEAD --name-only` shows no `.rs` or other canonical file changed in the second commit, so the hashes should still hold. The stamp is stale. Fix: restamp, or state that 124a1e4 changed no hashed file.

- `desktop/studio/ui/js/views/lab.js` (caveat) - MINOR - The caveat now sits above the figure, at 13.5 px and weight 600, but the `k/n seeds` numeral is 26 px. This is much better than the old dim small text and is acceptable. It is still not the same visual weight as the figure, though the docs say "ao nível do texto corrente". Lab caveat is covered only by structural tests, with no screenshot.

- `docs/evidence/m19/honesty/app-data-isolation.txt` - MINOR - It is internally consistent: identifier `org.vvlab.studio.m191review`, 1302 lines before and after, second run matching the first. I could not verify the listings themselves. The wording «Embedded identifier ... once» is unverifiable from the file. The `%LOCALAPPDATA%` paths are generic, so there are no personal paths.

Requirement notes:

- **(1) Safety scope:** `SAFETY_SCOPE` renders per run, directly under the verdict chips, only when `sw.verdict === 'held'` and `missionTone === 'fail'`. This is correct. The old footer note was removed, so a multi-run result states the scope per run.
- **(3) HUD:** `is-minor` applies only to rocket rows 3 and 4 (the old `nth-child(4,5)`), and ground rows stay visible. The evidence at 1024x640 shows To goal and Confidence present.
- **(4) Evidence integrity:** it uses the neutral `held` styling (`.dl-chip.held`, `.dl-tile.held`, `.replay-verdict.v-held`). It is labelled «Evidence integrity: ...», and failures stay red. Nothing in it uses green.
- **(5) Seed caveat:** see the Lab finding above.

CHECKED: the full diff of `desktop/studio/ui`, `tests/` and the docs; the two test commands; the `.rs` and forbidden-path scan; the U+2014 and personal-path grep; `timeText`; `safetyWording` and `missionTone`; the `after-facts.json` go_to_buttons entry; the CSS `held` rules; the evaluate-before and evaluate-after counts (20 lines each, 17 failing before).

NOT CHECKED: screenshots (PNGs not opened); the runtime HUD and layout (apps not launched); the correctness of the app-data listings; the cargo and campaign commands.
