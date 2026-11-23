# Fable: Belief vs Truth design direction

Agent role: `fable-strategic-advisor`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

**1. Decision**

Which renderer and interaction to use for a two-iteration "Belief vs Truth" prototype on one 0.15.0 recording. If it goes wrong, the view tells a confident, partly false story to the audience best placed to spot it, and uses up the last two visual iterations the programme allows.

**2. Framing: weak assumptions**

- **Rendering is not the gap.** Studio already draws truth and estimate in 3D with an error segment at the cursor (`rocket.js:157`, `geo.js:470`, `player.js:364`), plus Navigation readouts (`session.js:171-174`). That is the baseline to beat; what is missing is the explanatory chain.
- **"Belief" is two things.** Under `guarded` while the altimeter is rejected, guidance reads `min(estimator nozzle altitude, altimeter)` and the estimator is untouched (`landing_controller.rs:192-200`). Recorded `est_z` (about 15 m high) is not what vertical guidance flew on. Neither that altitude nor the residual is recorded.
- **Scale decides the renderer.** The bias is 15 m and the limit 10 m, in a 3000 m, 23 s descent. At true scale, truth and belief coincide in any trajectory view.
- **There is no covariance to miss.** The estimator is fixed-gain with no covariance state (`landing_controller.rs:96-134`). Its only self-assessment is the binary flag.
- **One run only.** "Why it mattered" is inference from source plus a single recording; no counterfactual or ghost run exists.
- **Owner constraints.** The strategy doc names Three.js (line 142), freezes Godot (138) and bans new dependencies (74).

**3. Options (Q1)**

| Option | Benefit | Cost | Risk |
|---|---|---|---|
| 2D: uPlot strips + true-scale SVG pad plan | Reads in metres; DOM-accessible; reuses `charts.js`, `cursor.js`, `timeline.js` | Less "distinctive" | Departs from the letter of line 142 |
| Hybrid: same strips, pad plan in Three.js with a locked orthographic camera | Honours line 142 | Canvas accessibility; WebGL upkeep for a 2D plot | Pressure to add perspective or orbit |
| Three.js perspective 3D | Familiar | Duplicates the baseline | The 15 m offset is unreadable; exaggerating it would be illustrative |
| Godot | None | Frozen | Violates line 138 |

**4. Recommendation**

**Rendering.** Build the 2D instrument with an SVG pad plan, and ask the owner to confirm that reading of line 142. If the owner holds to Three.js, use the hybrid with the camera locked orthographic and no free orbit. Never use perspective for anything measured. Credibility here comes from every pixel tracing to a record path (my judgement).

**Iteration 1 layout (Q2).**
- **Evidence bar.** Seed, policy, fault, "recorded by 0.15.0", both replay statuses (strict replay rejected, earlier-build replay verified, per `earlier_build.rs:282-304`), 0.1 s sampling, and "verdicts computed per step".
- **Time axis.** Visible sample ticks, with events at their exact times: fault window from 8.0 (input), flag at 8.18 drawn between the 8.1 and 8.2 ticks, touchdown at 22.955. The cursor snaps to samples and readouts never interpolate.
- **Horizontal strip, in error space.** `est_x − truth` as a line and `GNSS x − truth` as points.
- **Vertical strip.** Altimeter minus estimated nozzle altitude against the ±3 m threshold from `case.json`. Tag it "computed by this view, approximate": the controller's own residual uses its internal `s_cm`, which is not recorded.
- **Guidance-source lane.** "Estimator" before 8.18, then "min(estimator, altimeter)", tagged "from source, not recorded".
- **Pad plan (±20 m, true scale).** The R5 10 m circle, the true nozzle at 12.45 m (outside), and the believed centre of mass at about 3.4 m (inside). The believed distance is derived from final `est_x`/`est_y` of (2.88, −1.78). This is the headline.
- **Tags.** Reuse T/E/O/D/U from `session.js:130-131`. Split D into "computed by the 0.15.0 host" and "computed by this view", add S for "from source code", and show "U: none; this estimator holds no uncertainty". The sigmas in `case.json` are noise inputs and must not be drawn as envelopes.
- **Requirements.** Show R1–R6 from `verification.json`, all linked to touchdown. S1–S5 have a worst value but no recorded time, so say so and do not invent a moment.

**Misleading risks (Q3), ranked.**
1. Plotting `est_z` as the altitude the controller acted on.
2. Mixing reference points. The estimate is centre of mass, while the altimeter and R5 use the nozzle plane. The offset at touchdown is 14.85 m, which coincides with the 15 m bias and the 15 m `cutoff_altitude_m`.
3. Reading `cause: ["gnss_bias"]` as attribution. It sits on every requirement, including the passing ones. Likewise the code `hard_landing`, when R1 passes and R5 fails.
4. Implying a divergence instant. None is recorded: `err_h` is already 2.3 m at the 8.0 sample, and the flag needs five consecutive cycles, so correction was probably suspended from about 8.10 (inferred from source).
5. Grading the rejection with hindsight. The controller rejected the healthy sensor. With two sensors it could not tell which was wrong, and horizontally it had no redundancy at all.
6. Drawing lines through observations, or reading the interpolated touchdown sample as a verdict value.
7. Explaining a 0.15.0 record with current source. The earlier-build agreement check (`host_sdk.rs:325`) is what supports this; I did not run it.

**Evidence after iteration 2 (Q4).** "Adopt" can only mean "keep as candidate for the human gate, not installed" (lines 142, 144).
- **Adopt:** all of the following hold.
  - Fresh agents score higher with the prototype than with the baseline player on Q3–Q5, and no worse on Q1–Q2, against an answer key written before building.
  - They make no errors on trap questions (guidance altitude at 15 s; whether the rejection was correct; whether `gnss_bias` "caused" R2).
  - An automated check maps every displayed number to a record path or a named derivation.
  - A critical review finds no untagged inference.
  - Hashes are unchanged.
- **Revise later:** the view is correct and honest but shows no measurable advantage, or the advantage is perceptual and agents cannot judge it.
- **Reject:** a trap error survives iteration 2, or the central point depends on unrecorded quantities. In the second case the next step is a record change, not a view.

What would change my mind: a fresh-agent baseline that already answers Q4 from the existing player, or a spatial question that genuinely needs three dimensions.

**5. Cheapest next step**

Write the answer key and trap questions from the record now. Then run the baseline condition: one fresh agent, existing player and charts, this fixture. In parallel, run the test `a_run_written_by_the_0_15_0_host_verifies_against_its_record_under_the_current_host` in `<worktree:m192>/desktop/domain-rocket/tests/earlier_build.rs` to confirm the provenance claim.

CONFIDENCE: medium. The data and mechanism claims are read from the fixture and source; the rendering choice and the adoption thresholds are judgement, and agent review cannot measure human comprehension.
