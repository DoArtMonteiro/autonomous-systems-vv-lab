# Classification of the final pass (iteration or correction)

Agent role: `sonnet-critical-reviewer`. Criteria fixed by the orchestrator before the review. Not human review.

**Per-item classification** (diff `3b1b435..b495fc5`, plus `evaluation-record.md`)

| # | Item | Class | Reason and evidence |
|---|---|---|---|
| 1 | approx tags | Correction | Mis-tag fix. `model.js` `approx()` now propagates the flag. No new content. |
| 2 | nowrap numeric cells | Correction | CSS only (`style.css`, +7 lines). |
| 3 | ignition wording | Borderline, leaning substantive | It fixes a misleading "Commanded at" (`app.js` `renderDecisions`). It also adds two new derived quantities, `ign.first_engine_on_t` and `ign.first_command_t`. The garbled "command step" wording is still listed as a defect in the record. |
| 4 | connector break at fault onset | Correction | `breakBefore` in `charts.js`. This is the iteration 1 UX blocker (a connector drawn across the fault start). The same data is shown, but no longer misleading. |
| 5 | strip time labels | Correction | `charts.js` axis labels only. It adds no information, but it does change the layout. |
| 6 | card 4 rewrite | Substantive | The original defect (flag 8.18 s versus cut-off 8.10 s, "nothing guards x/y" untagged) is in the iteration 2 residual list. The fix is a rewrite into three sentences with a new derived fact, `lane.first_over_threshold_t`, and a new source tag, `S_gnss_ungated` (`index.html` card 4). It targets the weakest question (Q4 scored 2.5 in iteration 1), and the explanatory narrative changes. |
| 7 | R2 nozzle-plane velocity and lever arm | Substantive | New quantities (0.612 vs 0.513 m/s, difference 0.109) and a new physical explanation (`app.js` `#req-notes`). The scorer listed this as "not shown", so it is an omission being filled, not a mislabel being fixed. |
| 8 | sample index wording | Correction | Restates the same information (`updateSlider`). |
| 9 | initial propellant beside margin | Substantive (mild) | New quantity `init.propellant_kg`, a new verified check, and the record's own explanation (`app.js` R6 note). The scorer flagged the margin label as unclear, so a wording-only fix was possible. The change goes further than that. |
| 10 | GNSS velocity observations | Substantive | New observation series `err_gnss_vz` on the velocity strip, a new legend entry, and a new row in the cursor readout (`charts.js`, `app.js`). The strip's note was also rewritten. The criteria list a new observation series as substantive. |
| 11 | provenance lead line | Substantive (mild) | New explanatory statement that the verdicts shown are stored, not recomputed, and that the writing build is not the current tree (`renderProvenance`). Iteration 1 named provenance as an under-explained area. |
| 12 | card 1 nozzle plane and window 12.1-15.7 s | Substantive (mild) | "The point R5 judges" is a correction. The new sentence that the true nozzle point was inside R5 from 12.1 s to 15.7 s and then left is new narrative. The windows were already drawn as bars in the distance strip, so the content is not wholly new. |
| 13 | pad-plan label overlap | Correction | Layout only (`drawPlan`, `half <= 40`). |
| 14 | SVG role and aria-label | Correction | Accessibility attributes. The sr-only paragraphs were replaced by `aria-label`, which is a text equivalent. |

Tally: 7 corrections (1, 2, 4, 5, 8, 13, 14), 6 substantive (6, 7, 9, 10, 11, 12), 1 borderline (3).

**Verdict: third substantive iteration.**

- By the fixed criteria, items 6, 7 and 10 each independently meet the substantive test:
  - They add new quantities, a new observation series and new derived facts.
  - They rewrite the narrative of card 4, which targets the Q4 weakness from iteration 1.
- Items 9, 11 and 12 add further new content, and item 3 does so partly.
- Calling the extra items "residual defects" does not change this. Fixing an omission by adding new quantities is added information, not a correction of something iteration 2 presented.
- `docs/m19-2-belief-truth.md` says "só redação, etiquetas, CSS e pequenos dados; sem vistas novas" and `evaluation-record.md` says "non-substantive correction pass". Both are inaccurate for items 6, 7 and 10. The GNSS velocity series is an addition to an existing view, not a new view.
- The final evaluation did not improve on iteration 2 (comprehension 18.5 versus 19.5, strict 15.5 versus 17.0). The same record cites scorer variance and n = 1 for that, so the comparison is inconclusive. It is a reason to avoid claiming the pass helped.
- The record already states "no further iteration allowed", and the iteration 2 evaluation recommended adopting that build as the candidate. Record the final build as iteration 3, a limit overrun that is disclosed.

**Recommended sentence for the project record:**

"The final build is a third substantive iteration, not a correction pass: besides label, CSS, accessibility and connector fixes, it added new information (the GNSS velocity observation series, the R2 nozzle-plane velocity and lever-arm explanation, initial propellant, ignition sample times, the inside-R5 window in card 1, a provenance statement) and rewrote card 4; this exceeds the two-iteration limit, and its evaluation (comprehension 18.5/20, strict 15.5, n = 1, builder aware of the failed questions, no baseline) does not show an improvement over iteration 2 (19.5/20)."

**CHECKED:** the full diff of `index.html`, `app.js`, `charts.js`, `model.js`, `style.css` and the doc; `evaluation-record.md`. `extract.py` and `data.json` were not read in full (the output was too large). I relied on the doc's description of the extractor changes.

**NOT CHECKED:** the test file; the screenshots; the answer key (deliberately not read); whether items 7, 10 and 12 were already partly present in iteration 2 data.
