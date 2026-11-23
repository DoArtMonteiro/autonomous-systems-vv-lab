# Independent review of M19.1 honesty branch

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

I found no blocker. The only fixes are the inconsistent green on per-row safety passes and the weakness of the Python tests. I ran only the two test commands you allowed, plus a base-file comparison of the Node tests, and read all of the diff except the PNG evidence files.

**Findings, most severe first**

1. `desktop/studio/ui/js/model.js:90` (`verdictOfRequirement`), used by `verification.js:72`, `views/compare.js:213`, `views/lab.js:560` and `scenes/ascent.js:141` - MINOR/MAJOR - A passing invariant row still gets the green `pass` class. The Safety rules section of the player, the Compare matrix and the Lab cells therefore show a green check and "Pass" beside a neutral `held` aggregate chip. This undercuts requirement 1 (consistent distinction between requirements and invariants). Fix: in `verdictOfRequirement`, return `held` when `r.category === 'invariant' && r.status === 'pass'`. Add a regression test.

2. `tests/test_m191_honesty.py` (all 13 tests) - MINOR - These are source-text greps for regexes, not behavioural tests.
   - The plume cut-off, the pill behaviour and the held styles are only checked by pattern.
   - The real checks are in `capture.py` and the journeys, which are not part of the repository's test commands.
   - Against base, `ui_requirements.test.mjs` fails at module import because `completionFacts`, `noFailureSentence` and `conditionsBrief` are not exported. That proves the tests need the new code, not that the old behaviour is wrong. The doc's claim of `actual: 'pass', expected: 'held'` is not what I reproduced.
   - Fix: add a node test of `rocket.js` plume length for t beyond the last sample, or state in the doc that these are structural checks.

3. `desktop/studio/ui/js/views/player.js:816` - MINOR - The Mission chip tone depends on `/not evaluated/.test(missionText)`, which couples colour to wording. Fix: compute from `missionReqs` (any status that is neither `pass` nor `fail`).

4. `desktop/studio/ui/js/requirements.js:197` (`noFailureSentence`) - MINOR - With both categories the sentence reads "No requirement and safety rule failed, but 1 was not evaluated: X." The grammar is clumsy and does not say which category the unevaluated row belongs to. Fix: name the category per row, or use "No requirement or safety rule failed".

5. `desktop/studio/ui/css/mission.css:347-352` - MINOR - `.pl-runs` now has `overflow-y: hidden; overflow-x: auto`, which can clip focus rings on 30px pills. The visually hidden `.pl-run-c` is positioned against `.pl-runs`, which is the nearest positioned ancestor, so `.pl-run` is not one. The accessible name is preserved, but I did not verify this with a screen reader (the doc admits none was done). Fix: add `position: relative` to `.pl-run` and a small `padding-block` to the row.

6. `desktop/studio/ui/js/requirements.js:211` (`completionFacts`) - MINOR - I compared the regex with the strings written in `desktop/domain-ground/src/record.rs:622-624` and it matches the format. If the host wording changes, it returns `null` silently and the explanation disappears. That is acceptable, and the Python test ties it to `record.rs`, but the doc should say so.

7. `docs/m19-1-honesty.md`, section "Quebra do passo 4" - MINOR (process) - The test run wrote to the installed Studio's WebView2 cache. The doc declares this and does not clean it up. Honest, but it touches the installed 0.18.1 profile. Fix: the owner decides on cleanup, and future runs must set `WEBVIEW2_USER_DATA_FOLDER`.

8. `docs/m19-1-honesty.md`, "Limitações" - MINOR - The doc says `held` is applied in the Flight console, Compare and Lab, but none of these were checked visually, only by CSS classes and code tests. The doc states this itself, so it is honest. Finding 1 means Compare and Lab are in fact still partly green on invariant rows.

9. `desktop/cinematic/scripts/hud.gd:70` - MINOR - The text "the booster is not drawn after its last sample" relies on `ascent.gd:301` (`node.visible = en["active"]`). I did not verify that `active` is false past `t_end`. This is a precise model-limitation claim, so it needs a check. Fix: confirm in `ascent.gd` or test it via the `--shot` capture. The Cinematic module zip and manifest version were not rebuilt (the doc says so).

**Requirements checked**

- **Req 2:** The "Every requirement ... met" sentences now come from `noFailureSentence`. The Mission chip is neutral when there are no mission rows. `requirementWording` and `failureSentence` were already correct.
- **Req 3:** Run identity is better. Pills keep the full name and an exact count of conditions, and the tooltip and accessible name carry the full list. The after-1024x640 screenshot shows no cut text. The selected pill takes four lines.
- **Req 4:** The Cinematic launch panel now says the booster impact is not modelled. The wording is precise and not overclaimed.
- **Req 5:** `rocket.js` no longer draws a plume after the last sample. The landing readout at the contact names its speed source, with a "record has no contact speed" branch.
- **Req 6:** `git diff --name-status` shows only M and A entries. The only modified files are Studio JS/CSS, Cinematic `.gd` and two test files. There are no edits in `crates/`, `src/`, `exec/`, `scenarios/` or `docs/evidence/` outside `m19/`, and no `.rs` file changed. `hash-comparison.json` reports 542 identical values, which is consistent with that.
- **Req 8:** There is no U+2014 in the changed text files. The prose is European Portuguese in AO1990 spelling, as far as I can judge. The unverified items are stated honestly.
- **Req 9:** The only hit for personal-path patterns is `%LOCALAPPDATA%` and `%APPDATA%` as environment-variable forms in the doc. There is no `C:/Users`, `D:/vvwt` or user name in committed text files.

**CHECKED:**
- Ran `python -m unittest tests.test_m191_honesty -v`: 13 OK.
- Ran `node --test tests/ui_requirements.test.mjs`: 37 passed.
- Ran the HEAD Node test against the base `desktop/studio/ui/js` (via `git archive` into the scratchpad): it fails.
- Read the diff of the Studio JS/CSS and the Cinematic `.gd` and tests, `docs/m19-1-honesty.md`, `hash-comparison.json`, `evaluate-after.txt` and the 1024x640 after screenshot.
- Ran name-status, em-dash and personal-path greps.
- Read the `record.rs` observed-text format.

**NOT CHECKED:**
- The Python tests against base, which I did not run.
- Any simulator, Godot or Studio run.
- The before/after evidence PNGs other than the 1024x640 pill screenshot.
- Independent recomputation of the hashes (I relied on the unchanged file list).
- `HonestPanels`, which needs `VV_GODOT`.
- Contrast and screen-reader behaviour.
