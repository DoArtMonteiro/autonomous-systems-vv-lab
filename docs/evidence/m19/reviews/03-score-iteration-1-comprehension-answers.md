# Score iteration 1 comprehension answers

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

Agent-based evaluation: one LLM answerer used the viewer, so this is not a human comprehension study. Key sha256 verified (fc9993ef…828e).

## Scores (1 / 0.5 / 0)

**Sub-questions**
- 1.1 **1**: outcome, `hard_landing`, R5 failed only.
- 1.2 **1**: nozzle (-12.32, -1.79), centre of mass (CM) (-12.27, -1.88).
- 1.3 **1**: all values correct.
- 1.4 **0.5**: ignition 3.6 s and minimum 7.84 m at 13.8 s are right. The 12.1–15.7 s inside-radius window, the initial velocity and "never cut or relit" are missing.
- 2.1 **0.5**: sensors listed. The GNSS 0.1 s cadence and per-cycle altimeter are missing, and the answer says GNSS velocity values are not shown.
- 2.2 **1**.
- 2.3 **0.5**: CM estimate correct. The answer gives believed nozzle distance 3.29 m against the key's 3.39 m, and omits the believed nozzle altitude (about 14.8 m) and the altimeter reading (0.10 m).
- 2.4 **1**.
- 3.1 **0.5**: gives 8.0 s with the 0.04 m (7.9 s) and 2.27 m (8.0 s) bound. It does not say no divergence instant is recorded, and states no threshold.
- 3.2 **0.5**: position correct. The velocity-error transient is missing.
- 3.3 **1**.
- 3.4 **1**.
- 4.1 **1**.
- 4.2 **0.5**: only the guidance min rule. "Stops fusing the altimeter" is missing; the answerer is unsure (confusion point 1).
- 4.3 **0.5**: part (b) is right and labelled as hindsight. Part (a), the trigger being reasonable, is dodged ("cannot tell"). Part (c) appears only under 4.4 and X2.
- 4.4 **0.5**: headline "cannot tell", but it gives ignition at 3.6 s. Strictly this is 0; the rubric scores "cannot tell" on a determinate item as 0.
- 5.1 **1**.
- 5.2 **1**.
- 5.3 **0.5**: verdict versus view-derived is separated and the `cause` column is flagged. The controller-claim class and "causation is inferred" are not stated in this item.
- 5.4 **1**.

**Per question:** Q1 3.5, Q2 3.0, Q3 3.0, Q4 2.5, Q5 3.5. Total **15.5/20**, against a threshold of 17: **FAIL**. No "wrong" grade on 3.1, 4.3 or 5.3, so that condition holds.

**Traps** (fell into the misleading answer?)
- T1 **1**: 375.7 m, min rule, not recorded. Not misled.
- T2 **0.5**: hindsight is right, but the answer hedges "cannot tell" and the indistinguishability reason sits in 4.3. Not misled.
- T3 **1**.
- T4 **1**.
- T5 **0.5**: gives 8.0 s plus the bound, with no threshold dependence. Not misled (not 8.18 s).
- T6 **1**: nozzle versus CM, GNSS marker flagged as CM.
- T7 **1**.
- T8 **0.5**: values and source right. Nozzle-plane reference and interpolation are not stated.
- T9 **1**.
- T10 **0.5**: "earlier host, not current build" is right. It names neither `source_sha256` nor the insufficiency of the version string. Strictly 0 because it says "cannot tell".
- T11 **1**: "one" matches the key. The viewer lists only the altimeter event.
- T12 **1**.
- T13 **1**.
- T14 **0**: cannot-tell on a determinate item. Not misled, since it did not claim an outage.
- T15 **1**.
- T16 **0.5**: fault window right. Nominal versus dispersed start is "cannot tell", though the dispersed start is displayed.

Traps total **12.5/16**: **PASS**. T1, T2, T3, T5 and T6 are all at least partial. Zero of T1-T7 were misled, so the viewer does not mislead on the core thesis. Strict scoring of 4.4 and T10 gives 15 and 12.0, with the same pass/fail outcome.

**By evidence class:** [REC]/[HOST] items are near full marks. The misses are in [SRC]/[NK] and in cadence or controller-decision items. The viewer shows data well but under-explains the controller's mechanics.

## Root causes
- 1.4: (a). There is no time-series chart, and inside-radius crossings are not marked.
- 2.1 and T14: (a). The GNSS cadence (`gnss_period_cycles`) is not in `data.json`. `grep` finds 0 hits for `gnss_period` and for GNSS velocity series.
- 2.3: (d)/(a). The key's 3.39 m is CM-based and labelled a pad distance. The viewer's nozzle-based 3.29 m is arguably the more consistent number. Separately, the viewer does not surface a believed-altitude readout or the altimeter reading.
- 3.1 and T5: (b)/(c). The answerer anchors on the event time without a stated threshold.
- 3.2: (a). `err_vz`, `err_vh` and the velocity estimate are absent from the series.
- 4.2: (b). The source fact S_guidance_min says "the estimator state is untouched" and never says the altimeter is no longer fused.
- 4.3: (c) and (b). The viewer gives no (a) statement, and the answerer was over-cautious.
- 4.4: (a). Throttle, command and ignition rule are not shown (0 hits for `throttle`, `cmd_`).
- 5.3: (c). The viewer shows the classes, and the answerer did not itemise them.
- T2: (c).
- T8: (b). The nozzle-plane reference for R1/R2 is not stated beside the figures.
- T10: (b)/(d). The viewer says "earlier 0.15.0 host ... still verifies (see evidence document)", pointing outside itself. It lists the hash buttons, but the viewer never says the current source hash differs. The key's own T10 answer also concedes replay was not executed, so X10's wording is debatable.
- T16: (a). The nominal initial state in `case.json` is not shown.
- T11: (a). The `sensor_disagreement` event is not in the viewer's four events (ignition, fault start, altimeter rejection, touchdown). The viewer therefore neither shows nor explains the duplicate flag.

## Ten confusion points
Real defects:
- 1 (rejected altimeter and fusion): real, (b).
- 2 (error 2.27 m at the 8.0 s sample): real. Needs a "last cycle, not sample instant" note at that spot.
- 3 (the fault chip's 40 s end versus the run end): real.
- 4 (S2 repeats R5's value): real. The viewer states it is evaluated at contact, but not that it is the same number.
- 6 (+-20 m plan window hides the earlier track): real.
- 7 (cursor starts at 8.2 s): real.
- 9 (approximate tag on the believed point only in parentheses): real.
- 10 (GNSS "none" at touchdown): real.

Minor or mostly fine:
- 5 (mixed classes in one row): explained by a note.
- 8 (`hard_landing` at 2.07 m/s): already handled in the outcome box.

## Ranked viewer changes
1. Show sensor cadence (GNSS 0.1 s, altimeter and IMU per control cycle). Mark GNSS "none" at touchdown as "no fix on this cycle". This fixes 2.1, T14 and confusion point 10.
2. Add a controller decisions section: ignition rule, throttle command versus applied, no cutoff or abort. State that rejection also stops altimeter fusion. This fixes 4.2 and 4.4.
3. Add a divergence panel with an explicit threshold selector and the line "no divergence instant is recorded; fault onset 8.0 s; error 0.16 m at 7.9 s and 3.0 m at 8.0 s". This fixes 3.1 and T5.
4. Add a provenance block comparing `source_sha256` to the current build, with "version string does not identify the build". This fixes T10.
5. Show initial nominal versus dispersed state, and a fault-active-to-end banner. This fixes T16 and confusion point 3.
6. Add velocity-error strips (`err_vz`, `err_vh`). This fixes 3.2.
7. Add an altitude and pad-distance time chart with the 10 m radius crossings. This fixes 1.4 and T15.
8. Label the nozzle-plane reference next to R1, R2 and R5, and tag the believed-nozzle and distance values as derived at the point of use. This fixes T8 and confusion point 9.
9. Show the two controller flags as one boolean ("sensor_disagreement = altimeter_rejected"). This fixes T11.

Files: scoring inputs under `<scratchpad>/`. Viewer at `<worktree:m192>/spikes/m19-belief-truth/` (`data.json`, `index.html`, `extract.py`).

CHECKED: key hash, all three files, viewer `index.html`, `extract.py` source facts, `data.json` keys and series, and the fixture `record.json` (`vel_z`, the err_x sequence, believed pad distance 14.00 m at 14 s and 11.69 m at 15 s, events).
NOT CHECKED: rendered DOM and screenshots; I could not confirm which text the answerer actually saw beyond `data.json` and the HTML.
