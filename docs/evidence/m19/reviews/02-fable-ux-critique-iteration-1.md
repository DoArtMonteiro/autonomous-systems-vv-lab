# Fable UX critique, iteration 1

Agent role: `fable-ux-critic`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

## Scores

| Dimension | Score | Evidence |
|---|---|---|
| Visual clarity, hierarchy | 3 | `view-1440x900.png`: the first viewport is all prose and tags, with no chart above the fold. `view-1024x640.png`: card 4 is orphaned on its own row. |
| Scientific fidelity | 4 | Per-value pointers and named derivations are strong. Two defects: the estimate line and a class tag (fixes 1, 2). |
| Sensor/estimator interpretation | 4 | Nozzle vs centre of mass and the healthy-sensor rejection are handled correctly. Sign wording is weak. |
| Interaction | 3 | Cursor, zoom and drawer work. Verdict rows barely link to moments. |
| Accessibility | 3 | Non-colour encoding and the slider keys are good. Touch and keyboard gaps remain (fix 7). |
| Performance | 4 | `renderAll` rebuilds every SVG on each pointermove. Fine at 231 samples. |
| Maintainability | 4 | Clean extractor/view split. Verdict words are hard-coded and events are bound by array position. |
| Answers the five questions | 4 | What, believed and when are clear. Decisions-to-outcomes is the weakest. |

It is coherent and technically credible, and plain rather than attractive.

## 30-second read

GNSS was biased 15 m from 8.0 s and the estimate followed it. The healthy altimeter was rejected at 8.18 s. The nozzle touched down 12.45 m from the pad against a 10 m limit, so R5 failed while the safety invariants held. What slowed me: card 4's density, tag clutter, and "−12.32 m east".

## Journey (reviewer)

1. Reads the evidence bar: seed, fault, recording build 0.15.0.
2. Reads the four cards and clicks "Show the fault onset".
3. Sees the dashed estimate line rise from 7.9 s, before the 8.0 s fault marker, and doubts the timing.
4. Steps the cursor to 8.2 s and reads the residual strip and the lane.
5. Jumps to touchdown, then reads the pad plan, verdicts and the drawer.

## Cross-checks

- **Match:** R5 12.452456 and limit 10 (`verification.json`); touchdown nozzle −12.3232, −1.7896; step 820 truth x 1.1768 and z 1281.012, estimate x 6.8756 and z 1285.878 (`trace.json`); rejection at 8.18 s, step 818; all four hashes (`run.json`).
- **Not checked against raw:** GNSS 15.67, altimeter 1266.97, 0.40 and 2.27.
- **390 px:** the full-page capture is unreadable at the supplied size, so my 390 px claims rest on the CSS.

## Ranked fixes

1. **BLOCKER, estimate line draws divergence before the fault** (recorded data). `<worktree:m192>/spikes/m19-belief-truth/js/charts.js` `drawStrip` joins the 7.9 s sample to the 8.0 s sample (2.27 m). `full-1440-fault-zoom.png` shows the rise starting before the fault marker. The page says "no value is interpolated" and "one every control cycle", but only one cycle in five is recorded. The design doc line 88 admits the joining; the page does not.
   - Draw a marker at every recorded estimate sample and thin the connector.
   - Add a legend item: "connector between recorded samples, not data".
   - Replace the strip intro with: "Estimates are recorded every 0.1 s (one control cycle in five). Markers are recorded values; the thin connector is a reading aid."
   - Add the same sentence to Limitations.

2. **FIX, touchdown class tag** (derived from recorded data). `extract.py` lines 523-525 apply `cls_by_index=td_override` to the view-derived `err_est_x/y`. The touchdown readout then shows 15.15 and 0.11 as D-host, while the note below and card 2 say D-view. Remove the override. The drawer should read: "D-view, computed against the host-interpolated truth".

3. **FIX, provenance wording** (recorded data). `index.html` Limitations item 3 says "still verifies". `earlier_build.rs` shows strict replay is rejected and the earlier-build replay passes. Replace with: "Strict byte-for-byte replay is rejected under the current host. The earlier-build replay re-simulates with current defaults and agrees on the fields it compares; texts and the native simulator replay are not compared."
   - Source facts are read from the current tree, while the run declares `source_sha256` 12b276cb. I did not check equality and the page does not state it. Check it in `extract.py`, or add to `openFact`: "read from the current source, not verified equal to the recording build".

4. **FIX, link decisions to outcomes** (derived from recorded data).
   - Add to card 4: "In z the last estimate was 14.79 m above truth, yet R1 passed at 2.07 m/s; after the rejection the altimeter was the lower altitude at every recorded sample (approximate)."
   - Give each verdict row its own "show at touchdown" button, and give R5 a link to the pad plan.

5. **FIX, sign convention** (recorded data). Replace card 1 with: "at x = −12.32 m (east positive) and y = −1.79 m (north positive)". Add one consistent-with sentence: a +15 m x bias steered to the pad puts the vehicle on the −x side.

6. **FIX, hard-coded verdict words.** "R5 failed", "inside the R5 circle" and "Here only R5 failed" are literals in `index.html` and `app.js` `renderVerdicts`. Render them from `req.*.pass` and from believed distance against the limit. The numbers-only test will not catch drift here.

7. **FIX, accessibility.**
   - `css/style.css` line 107 sets `touch-action: none` on every strip, which blocks page scroll on touch. Use `pan-y`.
   - Legend buttons carry a fixed `data-i=0`, so the drawer shows the sample-0 value. Pass the cursor index.
   - Sample-table `td[data-ref]` cells are click-only. Make them buttons.

8. **FIX, hierarchy.** Cut each card to two sentences, lay the cards out 2x2 at 1024, and bring the x strip and pad plan into the first viewport.

9. **NIT.**
   - The touchdown event says "on a sample tick"; write "on the off-grid touchdown sample".
   - "stayed within 0.40 m" should add "at recorded samples".
   - `extract.py` binds `events/0..2` by position; assert `kind`.
   - Coalesce pointermove redraws with `requestAnimationFrame`.

## Blockers to adoption

- Fix 1: the view answers "when" with a drawn slope that the record does not contain.
- The narrative is fixed prose for one run, so it cannot be pointed at a second run.
- It is untested with users, a screen reader or a real 390 px device.
- Whether the source facts match the recording build is unverified.

## Renderer

Three.js gives no material advantage. A 15 m error on a 3000 m descent is invisible at true scale, perspective distorts the distances being compared, and the DOM accessibility would be lost. Canvas or uPlot is only worth it if traces move to 0.02 s cadence or multi-run overlays, which would need new data.

Self-reported model identity: Fable 5.2 (claude-fable-5-2)
