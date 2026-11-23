# Answers, iteration 2, agent A

Method: served the viewer on port 8302, rendered it with headless Edge (`--dump-dom`) at `?sample=N` for N = 36, 79, 80, 81, 82, 140, 150, 229, 230 and at the default load, and read the rendered text. I also read `data.json` and `js/*.js` to see what the page displays. Screenshots were not needed. No other repository file was used.

Evidence class tags are the viewer's: C configured, T truth recorded, E estimate recorded, O observation recorded, K command recorded, S from source code (not recorded), D-host derived by the host and stored, D-view derived by the viewer's extractor (some marked "approx."). Where I add my own arithmetic I say "my arithmetic".

"Section" names below are the page headings (Story cards 1 to 4, Controller decisions, Events, Divergence, Initial state and fault window, Verdicts, Provenance, Uncertainty, "At the cursor" readout).

---

## Q1. True trajectory and outcome

**1.1 Outcome and failed verdicts.**
Answer: outcome label "Touched down, requirements not met" (code `hard_landing`). Contact at 22.955 s (step 2296). The only failed verdict is R5, distance from pad centre 12.45 m against a limit of <= 10.00 m. R1, R2, R3, R4 and R6 passed. All safety invariants S1 to S5 passed.
Where: Verdicts section (requirements table, outcome line below the tables); Story card 1.
Class: D-host (verifier verdicts; the outcome label is D-host).
Confidence: high.

**1.2 Where the stage touched down.**
Answer: nozzle plane at x = -12.32 m (east positive), y = -1.79 m (north positive), which is 12.45 m from the pad centre (pad centre at x = 0, y = 0), outside the 10 m R5 radius. The true centre of mass at that instant was at x = -12.27 m, y = -1.88 m.
Where: Story card 1; "At the cursor" at the touchdown sample (`?sample=230`); pad plan (the true nozzle point is drawn at touchdown).
Class: D-host (interpolated contact state; the pad position is C).
Confidence: high.

**1.3 Contact speeds, attitude, rate and propellant.**
Answer (all judged at contact, 22.955 s):
- vertical speed 2.07 m/s (limit <= 3.00), passed;
- horizontal speed 0.61 m/s (limit <= 1.00), passed;
- tilt 0.99997 as a cosine (limit >= 0.99619), passed; I computed the angle as roughly 0.42 degrees and the limit as 5 degrees (my arithmetic, not displayed);
- angular rate 0.0073 rad/s (limit <= 0.1000), passed;
- propellant margin 4312.3 kg (limit >= 79.8 kg), passed. The viewer labels the row "Propellant margin" and does not say outright whether this is propellant remaining or remaining above a reserve. It matches the stored propellant series at the last sample (read in `data.json`, which the page does not show), so it appears to be the propellant left, but the page does not say so.
Where: Verdicts section, requirements table. The readout at `?sample=230` shows centre-of-mass vertical velocity -2.07 m/s, horizontal about (-0.48, 0.19) m/s.
Class: D-host.
Confidence: high for the numbers, medium for the propellant interpretation.

**1.4 True trajectory shape.**
Answer (all from truth rows, class T or D-host):
- Start (dispersed from nominal): centre of mass at x = 87.4, y = -21.3, z = 2956.4 m, velocity (-13.5, -0.5, -207.7) m/s, nozzle distance from the pad centre 90.0 m.
- Engine ignition at 3.6 s (T), at about 2182 m, vertical speed about -221.8 m/s, throttle command 0.415, then about 0.51. One ignition, no cutoff, no flameout, no relight.
- The descent is powered. Nozzle altitude is about 1301 m at 8.0 s, 474 m at 14.0 s, 55 m at 20.0 s. Vertical speed falls from about -222 m/s to -2.07 m/s at contact.
- Horizontally the true nozzle distance from the pad centre falls from 90 m to 46.9 m (3.6 s), 22.85 m (7.9 s), reaches its minimum of 7.84 m near 13.8 s, then rises again: 8.91 m (15 s), 11.7 m (18 s), 12.2 m (22.5 s), 12.45 m at contact. The true nozzle was inside the 10 m R5 circle from the 12.1 s sample to the 15.7 s sample, then drifted out to the west (negative x) and ended outside.
- The ground track in x goes 87 m to about 0 m (around 10 to 12 s), then slides to -12 m; y goes -21 to -2 m.
Where: strips "Distance of the nozzle plane from the pad centre" and "True nozzle altitude", pad plan (use "Whole track"), "At the cursor" at the samples listed, Events list, Initial state section.
Class: T and D-host; distance strip window values are D-view.
Confidence: high.

---

## Q2. What the controller believed and from which sensors

**2.1 What the controller received.**
Answer: observations plus the mission configuration. Sensors seen in the viewer: GNSS position (x, y, z of the centre of mass), one fix every 0.1 s (every 5 control cycles); altimeter (nozzle-plane height) and IMU every 0.02 s control cycle. The viewer shows the GNSS and altimeter values in the readout (class O). The IMU values are not shown anywhere I could find, so what the IMU delivered I cannot tell from what is shown. Configuration the page shows: GNSS position gain 0.15, altimeter rejection threshold 3.0 m held for 5 cycles, control period 0.02 s, ignition fraction 0.75 (the last in the Ignition decision text).
Where: "Sensor cadence" under Controller decisions; "At the cursor" readout; Story card 4; strip notes.
Class: O for readings, C for configuration, D-view for cadence.
Confidence: high for GNSS and altimeter, low for the IMU contents (cannot tell).

**2.2 Form of the belief.**
Answer: a single point estimate (position and velocity, recorded as E), with no uncertainty. The Uncertainty section says "U: none": the estimator is a fixed-gain blend, no covariance, so no envelope can be drawn. The viewer also derives a believed nozzle-plane altitude and believed nozzle point from the centre-of-mass estimate (D-view, approx.).
Where: Uncertainty section; "At the cursor" (Estimate E rows).
Class: E, with S for "fixed gain, no covariance".
Confidence: high.

**2.3 Belief at the end versus the truth.**
Answer (last estimate before contact at the touchdown sample, from the last control cycle, not the touchdown instant):
- centre-of-mass position: believed (2.88, -1.78, 29.64) m; true (-12.27, -1.88, 14.85) m. Error +15.15 m east, +0.11 m north, +14.79 m up.
- velocity: believed (-0.46, 0.20, -2.20) m/s; true (-0.48, 0.19, -2.07) m/s. Vertical velocity error -0.13 m/s.
- believed nozzle altitude 14.79 m (approx., D-view) against a true value of about 0 m; the altimeter itself read 0.10 m.
- believed nozzle point 3.29 m from the pad centre, inside R5; true nozzle point 12.45 m, outside R5.
Where: Story cards 1 and 2; "At the cursor" at `?sample=230`.
Class: E and D-view (believed nozzle point, approx.), T and D-host (truth).
Confidence: high.

**2.4 Which sensor carried the wrong information.**
Answer: GNSS, in x and z. The configured fault is a 15 m `gnss_bias` on GNSS x and z (C), and the GNSS minus truth error is about 14.3 to 15.2 m in x and z (about 0 in y) while the fault is active. The altimeter stayed within about 0.2 m of the true nozzle altitude (0.19 m at 22.9 s, 0.17 m at 15 s, 0.10 m at the last cycle).
Where: strips East (x) and Vertical (z); "At the cursor"; Initial state and fault window; "Could the controller tell which sensor was wrong?".
Class: C (configuration), O and D-view (errors).
Confidence: high.

---

## Q3. When and how much did belief diverge

**3.1 When did the divergence start.**
Answer: cannot tell the exact instant. No divergence instant is recorded (the page says so, in bold). What is recorded: the x error is 0.04 m at the 7.900 s sample (largest pre-fault |x error| is 0.40 m) and 2.27 m at the 8.000 s sample, which is also the first sample with the fault active (fault start event 8.0 s, T). The viewer infers the error jump equals gain x bias = 0.15 x 15 = 2.25 m for one biased GNSS fix (S, inference). So the divergence started at the first biased GNSS fix, at or just after 8.0 s, and the exact moment lies between samples.
Where: Story card 3; Divergence section (table and threshold picker); `?sample=79` and `?sample=80`.
Class: D-view (errors), T (fault start), S (gain inference).
Confidence: high for "at the fault onset, 8.0 s sample", low for any finer instant.

**3.2 By how much.**
Answer: grows from 2.3 m (horizontal, host) at 8.0 s to 4.15 m (8.1 s), 5.70 m in x (8.2 s), 10.09 m in x (8.6 s), and settles near 15 m: 15.12 m in x and 14.76 m in z at 14.0 s, 15.16 / 15.10 at 15.0 s, 15.15 m in x and 14.79 m in z at touchdown. y error stays small (0.11 m at touchdown). Using the threshold picker: first sample over 3 m horizontal is 8.1 s; over 5 m, 8.2 s; over 10 m, 8.6 s; vertical over 10 m, 8.7 s (the viewer's thresholds, D-view).
Where: Divergence section; Story card 2; readout at the samples above; the x and z strips.
Class: D-view and D-host.
Confidence: high.

**3.3 Direction.**
Answer: the estimate was east (+x) and above (+z) of the truth. So the controller believed it was about 15 m further east and about 15 m higher than it was. The true vehicle was west and lower.
Where: Story card 2; "At the cursor" (Estimate - truth rows positive).
Class: D-view, D-host.
Confidence: high.

**3.4 Did it recover.**
Answer: no. The error stays near 15 m to touchdown (15.14 m x, 14.76 m z at 22.9 s). The fault window is 8.0 to 40.0 s and the run ended at 22.955 s, so the fault was active until the end.
Where: x and z strips; Initial state and fault window section.
Class: D-view, C.
Confidence: high.

---

## Q4. Decisions

**4.1 When and how the controller reacted.**
Answer: the controller raised its altimeter-rejected flag at 8.18 s (step 818), 0.18 s after the fault start, between the 8.1 s and 8.2 s samples. The view-derived altimeter minus estimate residual passes the 3.0 m threshold at the 8.1 s sample (-3.10 m, approx.). I also note, from the numbers on the page (my arithmetic), that 5 cycles of 0.02 s ending at 8.18 s begin at 8.10 s, which fits. How: from the first cycle over the threshold the altimeter stops being fused into the estimate; after 5 consecutive cycles the guidance reads the lower of the estimated nozzle altitude and the altimeter (both statements are source code, S). No reaction to the x or y error is recorded; the page says nothing guards x and y.
Where: Events list; "Detection: one condition" and "What the rejection does" under Controller decisions; Story card 4; `?sample=81` and `?sample=82`.
Class: E (flag time), S (mechanism), D-view approx. (residual).
Confidence: high for the flag time, medium for the exact mechanism timing.

**4.2 What "altimeter rejected" changed.**
Answer: two things, both from source code, not recorded: (a) the altimeter was no longer fused into the estimate (this began before the flag); (b) guidance's altitude rule switched from "estimator" to min(estimator, altimeter), shown in the readout (rule S: "estimator" at 8.1 s, "min(estimator, altimeter)" from 8.2 s). From 8.2 s the altimeter was the lower altitude at every flagged sample (149 of 149, approx.), so guidance used the altimeter reading from then on.
Where: Controller decisions; "At the cursor" at `?sample=81` against `?sample=82`; Guidance altitude source strip; Story card 4.
Class: S, E, D-view approx.
Confidence: high.

**4.3 Was rejecting the altimeter reasonable?**
Answer: reasonable given what the controller could observe, but in hindsight the sensor rejected was the correct one. The controller's only test is the residual between the altimeter and its own estimate (source code). It cannot tell which sensor is wrong, and the page says this is a statement about the code, not a hindsight grade. The truth shows the altimeter within 0.19 m of the true nozzle altitude and GNSS z 14.30 m off. Effect on the vertical: because guidance reads the lower of the two altitudes, and the altimeter was the lower, the vertical guidance still used the correct altitude and R1 passed (2.07 m/s). Whether a better arbitration rule existed (for example weighing the sensors' noise) is not shown; the case-file noise values are the simulator's noise, not the controller's belief, so cannot tell.
Where: "Could the controller tell which sensor was wrong?" under Controller decisions; Story card 4; Altimeter against the estimator strip.
Class: S plus D-view.
Confidence: medium.

**4.4 Other decisions of note.**
Answer: ignition commanded at 3.6 s (T), before the fault starts at 8.0 s, by a rule (S) that lights the engine when descending faster than target and the needed deceleration reaches 0.75 of available thrust-to-mass. Throttle and gimbal commands are recorded every sample (K); throttle was 0.415 at ignition, about 0.58 at 8 s, 0.632 at 14 s, 0.639 at 15 s, 0.405 at the last control cycle; gimbal commands stay under about 0.07 in either axis in the samples I read. No engine cutoff, flameout, ascent abort or relight; one ignition. Only one detection exists, not two.
Where: Controller decisions (Ignition, Commands, "No cutoff, abort or relight", "Detection: one condition"); readout.
Class: T, K, E, S.
Confidence: high.

---

## Q5. Requirement and invariant outcomes

**5.1 Requirement results.**
Answer: R1 vertical speed 2.07 m/s <= 3.00, passed; R2 horizontal speed 0.61 m/s <= 1.00, passed; R3 tilt 0.99997 cos >= 0.99619, passed; R4 angular rate 0.0073 rad/s <= 0.1000, passed; R5 distance 12.45 m <= 10.00, failed; R6 propellant margin 4312.3 kg >= 79.8, passed. All are evaluated at touchdown. R1, R2 and R5 are judged at the true nozzle plane.
Where: Verdicts, requirements table.
Class: D-host.
Confidence: high.

**5.2 Invariant results.**
Answer: S1 tilt envelope while thrusting, worst 0.98389 cos >= 0.86603, passed; S2 keep-out radius at contact, 12.45 m <= 50.00, passed; S3 axial load 2.27 g0 <= 3.00, passed; S4 no relight, 1 ignition <= 1, passed; S5 climb under power 0.00 m <= 5.00, passed. No first failure for any.
Where: Verdicts, safety invariants table.
Class: D-host.
Confidence: high.

**5.3 Measured versus inferred.**
Answer: every verdict number is computed by the host on every step from the true simulator state and stored (D-host). That is a simulator's computed truth, not a measurement of a real vehicle: the Limitations say the model is idealised and nothing is validated against flight data. The controller's flags are not used for any verdict. Inferred or view-derived: believed nozzle point and believed distance (D-view, approx.), the "S2 equals R5" check (D-view), and any claim that the bias caused R5 (inference, "no counterfactual run"). The "faults active" column on each requirement row is the stored `cause` field, filled in for every row whatever its verdict, and is not an attribution. Invariants have only a worst value and a first-failure field, with no recorded time.
Where: Verdicts section notes; Limitations; Story card 4.
Class: D-host, D-view, S.
Confidence: high.

**5.4 Why `hard_landing` while `invariants_pass` is true.**
Answer: the code is assigned when contact happened and the mission requirements, or S5, are not all satisfied. It does not say the impact was hard. Here R5 failed (a mission requirement) while all five safety invariants passed (the invariants are separate from the requirements; S2 keep-out is 50 m, R5 is 10 m).
Where: Verdicts section, outcome line and its explanation.
Class: D-host.
Confidence: high.

---

## Extra questions

**X1. Altitude used by vertical guidance at about 15 s; did the controller ignore the altimeter?**
Answer: no, it did not ignore the altimeter in guidance. At 15.0 s the flag was set and the rule was min(estimator, altimeter) (S); the altimeter read 375.66 m against an estimated nozzle altitude of about 390.59 m (approx.), so the altimeter was the lower and guidance used about 375.7 m (true nozzle altitude 375.49 m). What changed is that the altimeter was no longer fused into the estimate; it was still used by guidance through the min rule. The viewer marks the "lower altitude" row as derived and approximate, and which altitude was used in each cycle is not recorded.
Where: `?sample=150` readout; Guidance altitude source strip; Story card 4.
Class: S for the rule, D-view approx. for the lower altitude.
Confidence: medium (the rule is from source code, the per-cycle choice is not recorded).

**X2. Was rejecting the altimeter "correct"?**
Answer: it was a consistent decision for the logic implemented (only the residual is tested) but it discarded the sensor that was right. See 4.3. Net effect: the estimate kept the GNSS bias, but guidance still saw the correct altitude via min().
Where/Class/Confidence: as 4.3; medium.

**X3. Did `gnss_bias` cause R5 (or R1 to R4, R6)?**
Answer: cannot tell from what is shown. Only R5 failed, and R1 to R4 and R6 passed, so nothing needs a cause for them. For R5 the page offers an inference ("consistent with the bias driving the miss") and states that there is no counterfactual run. The `cause` field lists `gnss_bias` for every requirement row, passed or failed; the page says it is not an attribution.
Where: Story cards 1 and 4; note under the requirements table; Limitations.
Class: inference (not recorded).
Confidence: high that the viewer does not establish causation; the underlying causal question is cannot tell.

**X4. What does `hard_landing` tell you about which requirement failed?**
Answer: nothing. The code does not name the requirement or say the impact was hard. The requirement results (here R5 only) and the outcome explanation (distance 12.452 m against <= 10 m) carry that.
Where: Verdicts section outcome line.
Class: D-host.
Confidence: high.

**X5. At what instant did belief start to diverge from truth?**
Answer: not recorded; cannot tell exactly. Bound: between the 7.9 s sample (x error 0.04 m) and the 8.0 s sample (2.27 m), consistent with the first biased GNSS fix at the fault start (8.0 s). See 3.1.
Class: D-view, T. Confidence: high for the bound, low for any exact value.

**X6. Believed versus true landing point, and the reference point of each.**
Answer: believed nozzle point (2.83, -1.68) m, 3.29 m from the pad centre; true nozzle point (-12.32, -1.79) m, 12.45 m from the pad centre; the gap between them is 15.15 m (D-view, approx.). The true point is the nozzle plane, which is what R5 judges. The believed point is the last estimate before contact (a centre-of-mass estimate) moved to the nozzle plane by the view, approximate. The GNSS marker on the plan is a centre-of-mass reading and sits at a different reference point. For reference the centre-of-mass values are believed (2.88, -1.78) and true (-12.27, -1.88).
Where: Story cards 1, 2 and 4; pad plan and its note; readout.
Class: D-host (true), D-view approx. (believed).
Confidence: high.

**X7. How confident was the controller in its estimate during the descent?**
Answer: cannot tell. The estimator holds no uncertainty (fixed gain, no covariance), so no confidence or envelope exists in the record, and the page deliberately draws none. The case-file sensor noise values are not the controller's belief about its error.
Where: Uncertainty section.
Class: S, not recorded.
Confidence: high that the page offers nothing here.

**X8. Vertical and horizontal speed at touchdown, and where they come from.**
Answer: vertical 2.07 m/s and horizontal 0.61 m/s, from the requirement rows R1 and R2: host verdicts computed from the true state at the nozzle plane at the contact step (22.955 s), D-host. The touchdown sample's truth is host-interpolated. Cross-check: the readout's centre-of-mass truth velocity at touchdown is (-0.48, 0.19, -2.07) m/s, so its horizontal speed is about 0.52 m/s (my arithmetic), not 0.61 m/s. The vertical value matches. The page says R2 is judged at the nozzle plane, which presumably accounts for the difference (nozzle plane versus centre of mass); the page does not show the reconciliation.
Where: Verdicts section; `?sample=230` readout.
Class: D-host.
Confidence: high for the numbers; low for the explanation of 0.61 versus 0.52.

**X9. Exactly when did the controller first reject the altimeter?**
Answer: the controller's altimeter-rejected flag was first raised at 8.18 s (step 818), E, recorded, between the 8.1 s and 8.2 s samples. The exact time the altimeter stopped being fused into the estimate is earlier than the flag by the source-code logic (the flag needs 5 consecutive cycles over the threshold) and is not recorded; cannot tell it exactly. The view-derived residual (approx.) first exceeds 3.0 m at the 8.1 s sample.
Where: Events list; "What the rejection does"; Story card 4; Altimeter against the estimator strip.
Class: E for the flag; S for the earlier fusion cut-off.
Confidence: high for the flag, low for the fusion cut-off.

**X10. Would the current simulator reproduce this run exactly?**
Answer: not shown, and probably not exactly. The run's recorded source hash (12b276cb...) is different to the current tree's (295a45b2...); the differing source is `src/landing_model.rs`. The version string is the same (0.15.0) but the page says it does not identify the build; the stored request has 6 parameters, fewer than the current catalogue. A strict replay under the current host is rejected (stored request not canonical under the current catalogue). An "earlier-build replay" with current defaults agrees on outcome, safety, requirement verdicts, telemetry channels, events and metrics; texts, the scene and native files are not compared. So agreement on those compared fields is the strongest thing established; exact (bit-for-bit) reproduction by the current simulator is not established. The recording commit reproduces the recorded hash (proved by a test with git).
Where: Provenance section; header chip "Run source hash ... is different to the current tree's".
Class: D-host (recorded hash), D-view (current hash, test result).
Confidence: medium for "not established"; low for "would or would not match numerically", which is cannot tell.

**X11. How many independent detections of a fault, and when?**
Answer: one. The altimeter-rejected flag and the sensor-disagreement flag are the same condition and are identical at every sample; first flagged at 8.18 s (step 818). The readout labels it "Altimeter rejected (one detection)".
Where: "Detection: one condition" under Controller decisions; Events list.
Class: E (flags), D-view (identical check).
Confidence: high.

**X12. When was S2 checked, did it hold?**
Answer: at contact only (22.955 s, step 2296). It held: worst value 12.45 m <= 50.00 m, no failure. Its worst value equals the R5 value (D-view check). Because it is evaluated only at contact, the record says nothing about keep-out during the descent (the true distance strip shows 90 m at the start, so a full-time check would not have been meaningful).
Where: Verdicts, invariants table and note.
Class: D-host.
Confidence: high.

**X13. How wrong was GNSS position while the fault was active?**
Answer: about 15 m in x and z, near 0 in y. Over the 150 GNSS samples with the fault active (8.0 to 22.9 s) the GNSS minus truth error has a mean of about 15.06 m in x (range 13.8 to 16.3) and 15.04 m in z (range 14.1 to 16.2), y mean about -0.05 m (range -1.3 to 1.4). The statistics are my arithmetic on the viewer's values; individual values are in the readout, for example (14.94, 1.40, 14.68) m at 8.0 s and (14.93, 0.85, 14.30) m at 22.9 s. Scatter is consistent with the 0.5 m GNSS noise setting and a 15 m configured bias.
Where: x, y and z strips; readout; Initial state and fault window.
Class: D-view, C.
Confidence: high.

**X14. How often did GNSS provide a measurement, and what did it report between measurements?**
Answer: one fix every 0.1 s (every 5 control cycles of 0.02 s). The trace stores one sample every 0.1 s, so 230 samples carry a fix and the off-grid touchdown sample does not ("no fix on this cycle"). What GNSS reported between fixes: cannot tell. The page shows null at the touchdown cycle and no held value, and nothing is recorded between samples.
Where: "Sensor cadence" under Controller decisions; `?sample=230` readout.
Class: D-view for cadence, S (cadence note), O for readings.
Confidence: high for the cadence, low for the between-fix behaviour (cannot tell).

**X15. At about 14 s, on course for the pad, and was the estimator working well?**
Answer: at 14.0 s the true nozzle was 7.88 m from the pad centre, inside the 10 m R5 radius (true inside from 12.1 to 15.7 s, minimum 7.84 m in the recorded samples), at true x -3.30, y -7.53 m, true horizontal velocity (-2.51, 0.99) m/s. So it was near the pad but, with vx negative, still sliding west, and the distance rose again afterwards (8.91 m at 15 s, 12.45 m at contact). "On course" in the sense of a forecast cannot be read from the page. The estimator was not working well in position: it was off by 15.12 m in x and 14.76 m in z, so the controller believed the nozzle was 14.07 m from the pad centre (outside R5; believed inside only from 15.6 s). Its velocity estimate was good (host velocity error -0.00 vertical and 0.01 horizontal m/s).
Where: `?sample=140` readout; distance strip; velocity strip.
Class: D-host (true distance), D-view (believed distance, approx.).
Confidence: high for the numbers, medium for the "on course" judgement.

**X16. Nominal initial state, and how long could the fault have lasted?**
Answer: not nominal; dispersed by the seed (5002). Dispersed against nominal: x 87.4 against 80 m (half-width 30), y -21.3 against 0 (30), z 2956.4 against 3000 (50), vx -13.5 against -12 m/s (3), vy -0.5 against 0 (3), vz -207.7 against -200 m/s (10). The fault is configured from 8.0 s to 40.0 s (up to 32 s), but the run ended at touchdown at 22.955 s, so it was active for about 14.96 s (my arithmetic, 22.955 - 8.0) and until the end of the run.
Where: Initial state and fault window section.
Class: C and D-host.
Confidence: high.

---

## Moments where the viewer confused me, felt ambiguous or seemed inconsistent

1. Header chips and Story card 4, "Cadence" and the story text use "D-view" and "approx." tags on nearly every number, including ones that are plainly recorded sums. It takes effort to separate "recorded" from "derived" because the chip abbreviations (T, E, O, K, S, C, D-host, D-view) only get explained at the very bottom ("Evidence classes"). It would help to have the key near the top.
2. "At the cursor", cursor status: "recorded sample 0 of 230" while the page elsewhere says 230 samples carry a fix plus 1 without. So there are 231 samples (0 to 230). "Of 230" is the last index, not the count. Mild but I had to work it out.
3. R2 horizontal speed 0.61 m/s (Verdicts) versus the readout's centre-of-mass truth velocity at the touchdown sample, which gives about 0.52 m/s. The page says R2 is judged at the nozzle plane but never reconciles it, so it looks like a contradiction at first.
4. Story card 4: "Nothing guards x and y, so the biased belief was followed there." This is a statement about source code but it is not tagged with an evidence class (the nearby clauses are tagged). I could not find a source link for it in the Controller decisions section.
5. Story card 4 says "By 8.18 s the altimeter had stopped being fused". Decisions says the fusion stops before the flag, and "8.18 s" is the flag. The sentence mixes the two, so "first reject" has two meanings (flag versus fusion cut-off) and the exact fusion cut-off is not recorded. It also says "rejected" in the event, the flag, and the controller logic.
6. "Faults active (not attribution)" column lists `gnss_bias` on every requirement row, including the five that passed. The caption warns it is not attribution, but the column is next to the verdicts and invites the reading "the fault caused this".
7. Believed versus true distance strip: true inside R5 from 12.1 to 15.7 s, believed inside from 15.6 s to the end, and the true distance minimum (7.84 m) is recorded on a sample, not interpolated. Slightly confusing that the "windows" for true and believed overlap in 15.6 to 15.7 s while the controller was at the time already outside in truth by the next sample; readable only with the strip zoomed.
8. Propellant margin: labelled "margin" with a limit of 79.8 kg, value 4312.3 kg. The page does not say whether this is propellant remaining or a margin over a reserve. The initial propellant is not displayed anywhere, so I could not state how much was used.
9. The IMU is mentioned (cadence, "observes the altimeter and the IMU each time") but no IMU value or its role in the estimate appears anywhere, so a reader cannot tell whether it carried wrong information.
10. Divergence section, "Estimate error around the fault start" table: the x error at the 8.000 s sample is called "the state after the fault took effect in that control cycle, not a gradual rise". The estimate error at 8.0 s is 2.27 m while the page also says the first biased fix moves the estimate by 2.25 m. Consistent, but the sentence "no divergence instant is recorded" next to a visible jump at one sample makes the reader unsure whether "8.0 s" is an answer or not.
11. The estimator z error is 14.79 m at touchdown and the centre of mass is 14.85 m above the nozzle plane at contact (truth z 14.85, nozzle altitude 0): the two numbers are very close, which looks like a coincidence that a reader could mistake for a relation. The page does not discuss it.

(Stopped the local server started on port 8302.)
