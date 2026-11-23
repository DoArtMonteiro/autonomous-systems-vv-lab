# Fable UX critique, iteration 2

Agent role: `fable-ux-critic`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

**Verdict: ADOPT as a candidate for the human gate (not installed).** No blockers. The fixes below are wording and CSS, not a substantive iteration.

Not verified: 1024 px screenshots (not opened), 390 px full page (unreadable at thumbnail size; only the first screen was read), performance (unmeasured), touch behaviour, and SVG labelling.

## Cross-checks against raw files
All match:
- **R5:** 12.45 m, limit 10, failed. `verification.json` R5_position value 12.452455…, `pass:false`.
- **R2 and S2:** 0.61 m/s (0.61195…); S2 worst 12.45 against limit 50, passed.
- **Run identity:** seed 5002, policy guarded, hash `12b276cb18…` (`run.json`).
- **Fault:** gnss_bias 15.0, 8.0 s to 40.0 s (`case.json`).
- **Events:** rejection and disagreement both at 8.18 s (`record.json:12814, 12824`), shown as one detection.
- **Config:** 5 rejection cycles, GNSS gain 0.15 (so 2.25 m expected jump), `gnss_period_cycles` 5.
- **Source claims:** guarded runs `update_robust` (`landing_controller.rs:69`); guidance takes `p_base.z.min(alt)` (line 197); GNSS x/y fusion is ungated (line 116).
- **Not confirmed:** R1 2.07 m/s; my search did not hit it.

## User journey (reviewer)
1. Header: one stored run, source hash differs from the current tree.
2. Cards 1 to 4: missed the pad by 12.45 m; controller believed 3.29 m; no divergence instant recorded; x and y unguarded.
3. "Fault onset": 0.04 m at 7.9 s, 2.27 m at 8.0 s, rejection at 8.18 s.
4. Distance strip: truth inside R5 from 12.1 s to 15.7 s, then leaves; belief inside from 15.6 s.
5. Verdicts, then Provenance.

Slowed by tag density in the cards, the single 80-word sentence in card 4, and strips with no time labels.

## (1) Iteration-1 issues
| Issue | Status | Evidence |
|---|---|---|
| Connector before fault | PARTLY | Markers and legend now carry the truth, but in `fault-zoom-1440.png` the thin segment still rises from 7.9 s to the 8.0 s fault line. |
| Touchdown class tags | FIXED | Estimate − truth x/y show D-view at sample 230. |
| Provenance wording | FIXED | Header says "is different"; strict replay rejection is stated. |
| Decisions to outcomes | FIXED | Decisions section and card 4, softened to "consistent with". |
| Sign convention | FIXED | "east positive", "north positive". |
| Hard-coded verdict words | FIXED | `WORDS` map in `model.js`. |
| Touch-action, legend, table | PARTLY | CSS present (`style.css:116`); no device or screen-reader test. |
| Hierarchy | PARTLY | Chart above the fold at 1440 only; the doc itself concedes 1024, and at 390 the first screen is header plus cards. |

## (2) Scores (iteration 1 → 2)
| Dimension | Score | Reason |
|---|---|---|
| Clarity | 3 → 3 | Better hierarchy, offset by density (about 5600 px at 1440, 9000 px at 390). |
| Fidelity | 4 → 4 | Three small labelling gaps, listed below. |
| Interpretation | 4 → 5 | Rejection mechanics, "could not know which sensor", R5 in/out bars. |
| Interaction | 3 → 4 | Presets, event jumps, threshold selector. |
| Accessibility | 3 → 3 | Shapes plus words, reduced-motion and forced-colors rules exist; new colours unmeasured. |
| Performance | 4 → 4 | Unmeasured; carried over. |
| Maintainability | 4 → 4 | 57 tests; card sentences are run-specific and the source-line pins are brittle. |
| Five questions | 4 → 4 | Answerable; not re-measured. |

## (3) Defects, ranked
BLOCKER: none.

FIX:
1. **Missing "approx." on a favourable claim.** Card 2 reads "3.29 m D-view … inside D-view". The same quantity is tagged "approx." in the strip legend and cursor panel. Add "approx." after 3.29 m, after "inside", and on the "believed within R5 from 15.600 s to 22.955 s" bounds.
2. **Numbers wrap mid-digit.** In the cursor panel velocity table (`fault-zoom-1440.png`), "−2.54" renders as "−2.5 / 4" and "−169.71" as "−169. / 71". Set `white-space: nowrap; font-variant-numeric: tabular-nums` on value cells and let the table scroll.
3. **Ignition wording.** `app.js:256` says "Commanded at" using `run.ignition_command_t_s`. The record's ignition event is `source: "truth"`, "Engine ignition", t 3.6 (`record.json:12788-12792`). I did not see how the command scalar is derived. Unless it is a recorded command time, replace with: "Engine ignition recorded (truth event) at 3.6 s; first recorded sample with the engine commanded on: …".
4. **Connector at fault onset.** Break the connector between the last pre-fault and first faulted sample, or dash that one segment.
5. **No time labels on strips.** They have ticks only, so the time axis is lost once the timeline scrolls away. Label each strip's ticks or make the timeline sticky.
6. **Card 4 is one sentence.** Replace with three: "At 8.18 s the controller flagged the altimeter. From then guidance read the lower of two altitudes (source code, not recorded). Nothing guards x and y, so guidance followed the biased belief: true and believed nozzle points end 15.15 m (approx.) apart."

NIT:
- **Hash-only verification.** The page does not overclaim. Verdicts are stored host values, and the only replay is by a different build; both are stated. Lead Provenance with: "Verdicts shown are stored, not recomputed by this view; the build that wrote the run is not the current tree."
- **Pad plan.** "true" and "believed" labels overlap the track in "Whole track".
- **Card 1.** x = −12.32 (nozzle) sits beside cursor truth −12.27 (centre of mass); add "(nozzle plane)" inline.
- **Chart labelling.** `charts.js` contains no `aria-`, `role` or `<title>` strings; confirm each SVG gets a label elsewhere.

## (4) Coherent, attractive, credible?
Coherent and credible: it refuses a divergence instant, separates source-code claims from recorded values, and admits the hash mismatch. It is dense rather than attractive. Engineers will trust it; a first-time reader needs more than 30 seconds.

## (5) Recommendation
ADOPT as candidate. Fidelity is traceable and tested, and the source claims hold for the guarded path. The gate must be told that comprehension was never re-measured, accessibility was not tool-tested, and the card prose fits only this run.

## (6) Renderer
No material advantage from Three.js. The data is 231 samples of 1D series plus a true-scale plan; perspective would harm scale reading and accessibility. Consider Canvas only for multi-run overlays.

## Top five improvements
1. "approx." on card 2 and the believed-R5 bars (derived from recorded data).
2. Non-wrapping numeric cells (recorded data).
3. State "truth was inside R5 from 12.1 s to 15.7 s, then left" in card 1 (derived from recorded data).
4. Time labels on strips and a broken connector at the fault (recorded data).
5. Residual strip against the controller's internal residual, replacing the proxy (would need new data).

Files:
- `<worktree:m192>/spikes/m19-belief-truth/js/app.js`
- `<worktree:m192>/spikes/m19-belief-truth/js/charts.js`
- `<worktree:m192>/spikes/m19-belief-truth/css/style.css`
- `<worktree:m192>/spikes/m19-belief-truth/extract.py`
- `<worktree:m192>/docs/evidence/m19/belief-truth/iteration-2/fault-zoom-1440.png`
- `<worktree:m192>/docs/evidence/m19/belief-truth/iteration-2/view-1440x900.png`

Model identity (self-reported): Fable 5.2, claude-fable-5-2.
