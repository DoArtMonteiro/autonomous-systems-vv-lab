# Answers: Belief vs Truth viewer (final), investigator A

Sources used: rendered viewer at `D:\vvwt\m192\spikes\m19-belief-truth\` (served locally, headless Edge DOM dumps at ?sample=0, 100, 150, 230), its data.json for series values the viewer renders, and the screenshots in `final\`. Evidence class tags as labelled in the viewer: C config, T truth (recorded), E estimate (recorded), O observation, K command, S source code, D-host (host-computed, stored), D-view (computed by this view, some "approx.").
Samples are every 0.1 s (231 samples, last is the off-grid touchdown sample at 22.955 s). Times below are sample times unless stated.

## Q1. True trajectory and outcome

**1.1 Outcome, failed verdicts.** Outcome label "Touched down, requirements not met" (code `hard_landing`, D-host). Only R5 failed (12.45 m against <= 10.00 m). R1, R2, R3, R4, R6 passed. All safety invariants S1 to S5 passed. Where: Verdicts section, requirement table and "Outcome label" line; card 1. Confidence: high.

**1.2 Touchdown point.** The nozzle plane (the point R5 judges) touched down at x = -12.32 m (east positive), y = -1.79 m (north positive), 12.45 m from the pad centre, outside the 10 m R5 radius (D-host). Centre of mass truth at the touchdown sample: x -12.27, y -1.88, z 14.85 m (T/D-host, interpolated by the host). Where: card 1; "At the cursor" at touchdown sample 230; Pad plan. Confidence: high. Pad centre is the origin as far as I can tell (distance 12.45 equals sqrt(12.32^2+1.79^2)); the viewer does not state the origin explicitly.

**1.3 Contact speeds, attitude, rate, propellant.** Nozzle-plane vertical speed 2.07 m/s (R1, limit 3.00, passed, D-host). Nozzle-plane horizontal speed 0.61 m/s (R2, limit 1.00, passed, D-host). Centre-of-mass horizontal speed 0.513 m/s (D-view); CoM truth velocity at touchdown vx -0.48, vy 0.19, vz -2.07 m/s. Tilt cosine 0.99997 (R3, limit >= 0.99619, passed); my own arithmetic: about 0.44 degrees, not shown by the viewer. Angular rate 0.0073 rad/s (R4, limit 0.1). Propellant left 4312.3 kg of 7981.6 kg initial (R6, limit 79.8 kg, passed). Where: requirement table, R2/R6 notes. Confidence: high.

**1.4 True trajectory shape.** Start (t=0) dispersed from nominal: x 87.4, y -21.3, z 2956.4 m, velocity (-13.5, -0.5, -207.7) m/s. Engine ignites at 3.6 s (before the fault), throttle command about 0.5 to 0.66, no cutoff, abort or relight. True x falls to about 0 by 9.0 s (altitude about 1150 m), stays near 0 (about +0.3 at 12 s), then drifts to -5.8 m at 15.0 s and -12.3 m at touchdown. True y goes from -24 m (6 s) to -6.7 m (15 s) to -1.9 m. True nozzle distance from pad centre: 90.0 m at 0 s, 22.6 m at 8.0 s, within R5 from 12.1 s to 15.7 s (8.91 m at 15.0 s), then leaves and ends at 12.45 m. Vertical speed decreases from about -217 m/s (4 s) to -92 m/s (15 s) to -2.07 m/s. Touchdown at 22.955 s. Where: pad plan (whole track), distance strip, sample table, readout. Confidence: high for recorded numbers; the verbal shape is my summary of the recorded samples.

## Q2. What the controller believed

**2.1 What it received.** Observations: GNSS position and velocity (one fix every 0.1 s, every 5 control cycles), altimeter and IMU every 0.02 s (chip bar; "Sensor cadence"). It does not receive truth ("the controller does not have the truth"). Configuration (policy `guarded`) is shown only as chips and case parameters. IMU contents are "recorded in the trace but not shown here". Confidence: medium (what exact config fields the controller gets is not shown).

**2.2 Form of the belief.** A single point estimate (position, velocity) from a fixed-gain blend with no covariance. "U: none", so no uncertainty exists to display. Where: Uncertainty section (S class). Confidence: high.

**2.3 End belief versus truth.** Last estimate before contact (E, last control cycle, no GNSS fix on that cycle): CoM x 2.88, y -1.78, z 29.64 m. Truth: x -12.27, y -1.88, z 14.85 m. Error: x +15.15, y +0.11, z +14.79 m. Believed vertical speed -2.20 vs true -2.07 m/s. Believed nozzle distance from pad 3.29 m (inside R5, D-view approx.) against true 12.45 m (outside). Where: readout at sample 230; card 2. Confidence: high.

**2.4 Which sensor was wrong.** GNSS, carrying a 15 m `gnss_bias` fault on x and z (C). GNSS minus truth is about +14 to +16 m in x and z from 8.0 s on; y is not faulted. Altimeter minus true nozzle altitude stays about 0.1 to 0.2 m (D-view). Where: header fault chip, x and z strips, "Could the controller tell which sensor was wrong?". Confidence: high.

## Q3. Divergence

**3.1 When it started.** Cannot tell the exact instant: "No divergence instant is recorded." Bracket: x error 0.04 m at the 7.9 s sample, 2.27 m at the 8.0 s sample; the fault starts at 8.0 s (recorded event, T). GNSS minus truth is already 14.94 m at 8.0 s. Resolution is 0.1 s. Where: card 3, Divergence section. Confidence: high for the bracket.

**3.2 How much.** Estimate-truth x: 2.27 m at 8.0 s, 4.15 at 8.1, 5.70 at 8.2, 10.09 at 8.6, 14.54 at 10.0 s, then 15.0 to 15.3 m to the end (15.15 at touchdown). Vertical (z) similar: 1.94 m at 8.0 s, 15.10 at 15.0 s, 14.79 at touchdown. Horizontal error (host) 2.30 m at 8.0 s. One biased fix moves the estimate by gain times bias, 2.25 m (D-view approx., inference). Confidence: high.

**3.3 Direction.** The belief was east (+x) and above (+z) of the truth by about 15 m each. Truth ended on the negative x side. Confidence: high for belief offset; the viewer labels the link to the true negative-x drift as inference.

**3.4 Recovery.** No. The error stays about 15 m until touchdown. The fault was active until the end of the run. Confidence: high.

## Q4. Decisions

**4.1 Reaction.** The controller flagged the altimeter rejected (and the "sensor disagreement", the same condition, one detection) at 8.18 s (E, step 818), between samples 8.1 and 8.2 s. First recorded sample with residual over 3 m threshold: 8.1 s (D-view approx.); flag follows 5 consecutive cycles. Confidence: high for 8.18 s, medium for the 8.1 s item (approx.).

**4.2 What the rejection changed.** Source code, not recorded (S): the altimeter stops being fused into the estimate from the first over-threshold cycle (before the flag), and after the flag guarded guidance reads the lower of estimated nozzle altitude and altimeter. In the derived lane the altimeter was lower in 149 of 149 flagged samples (D-view approx.). The run does not record which altitude guidance used in each cycle. Example at 15.0 s: estimated nozzle altitude 390.59, altimeter 375.66 (true 375.49). Confidence: medium (source-code and derived, not recorded).

**4.3 Reasonable?** From observables only: the altimeter disagreed with the estimator by about -14.9 m, beyond the 3 m threshold, and the only test is that residual, so the controller could not tell which sensor was wrong (viewer states this about the code, not with hindsight). In truth the altimeter was right and GNSS wrong, so flagging the altimeter was the wrong sensor in hindsight, yet the min rule made guidance use the correct altitude and R1 passed. Whether it was reasonable is a judgement the viewer does not make. Cannot tell from what is shown whether the IMU (contents not shown) could have arbitrated. Confidence: medium.

**4.4 Other decisions.** Ignition at 3.6 s, before the fault, by a source rule (descending faster than target, needed deceleration reaches 0.75 of available thrust-to-mass). No cutoff, flameout, abort or relight. Throttle command about 0.64 at 15 s, 0.405 at touchdown; gimbal commands tiny. Nothing checks GNSS x or y against another sensor (S), so the biased horizontal belief was followed. No flag was raised on GNSS. Confidence: high.

## Q5. Requirements and invariants

**5.1 Requirements** (D-host, at touchdown): R1 vertical speed 2.07 m/s <= 3.00 passed; R2 horizontal speed 0.61 <= 1.00 passed; R3 tilt 0.99997 >= 0.99619 passed; R4 angular rate 0.0073 <= 0.1000 rad/s passed; R5 distance 12.45 m <= 10.00 failed; R6 propellant margin 4312.3 kg >= 79.8 kg passed.

**5.2 Invariants:** S1 tilt envelope while thrusting 0.98389 >= 0.86603 passed; S2 keep-out radius at contact 12.45 m <= 50.00 passed; S3 axial load 2.27 g0 <= 3.00 passed; S4 ignitions 1 <= 1 passed; S5 climb under power 0.00 m <= 5.00 passed. None has a first failure.

**5.3 Measured versus inferred.** Verdicts are computed by the host each step from the true state and stored (D-host); this view does not recompute them. All values are simulation records, not physical measurements. Inferred or derived: everything tagged D-view (believed nozzle point, residual, lane, divergence thresholds, 15.15 m gap), and source-code claims (S). "Faults active" in the requirement table is the stored `cause` field, not an attribution. Confidence: high.

**5.4 `hard_landing` with `invariants_pass` true.** The code is assigned when contact happened and the requirements (or S5) are not all satisfied; it does not say the impact was hard (R1 passed at 2.07 m/s). Mission requirements and safety invariants are separate: R5 (10 m) failed while S2 (keep-out 50 m, same 12.45 m value) passed. Confidence: high.

## Extra questions

**X1.** At 15.0 s the guidance rule was min(estimator, altimeter) (S class, flag E true). Estimated nozzle altitude 390.59 m, altimeter 375.66 m, true 375.49 m; the altimeter was the lower (D-view approx.), so guidance by that rule used about 375.7 m. The controller did not ignore the altimeter in guidance; it stopped fusing it into the estimate (source code, not recorded). The per-cycle altitude actually used is not recorded. Confidence: medium.

**X2.** Wrong sensor in hindsight (altimeter error about 0.1 to 0.2 m, GNSS about 15 m), but not detectable by the controller's own test. Effects: the altimeter-lower rule kept vertical guidance close to truth (R1 passed). The viewer declines to grade it. Confidence: medium.

**X3.** The viewer does not attribute R5 (or any requirement) to the fault. It says the true/believed gap is "consistent with the bias driving the miss (no counterfactual run)". The `cause` column lists gnss_bias on all six rows, including passing ones, and is explicitly "not attribution". Only R5 failed. Cannot establish causation from this record. Confidence: high.

**X4.** Nothing about which requirement failed; the code is generic ("requirements not met"). The requirement table shows R5 only. R1 vertical speed passed. Confidence: high.

**X5.** Not recorded; between the 7.9 s and 8.0 s samples, with the fault event at 8.0 s (see 3.1). Cannot tell finer than that.

**X6.** True point: nozzle plane at touchdown, x -12.32, y -1.79, 12.45 m from pad centre (D-host). Believed point: last estimate before contact (last control cycle, not the touchdown instant) moved to the nozzle plane, 3.29 m from pad centre (D-view approx.). They end 15.15 m apart (D-view approx.). GNSS marker is a centre-of-mass reading, a different reference point. Confidence: medium-high.

**X7.** Cannot tell. The estimator has no covariance or uncertainty ("U: none"); noise settings are simulator noise, not controller belief. Only the point error (about 15 m) is shown, which the controller did not know.

**X8.** Vertical 2.07 m/s and horizontal 0.61 m/s at the nozzle plane, from the host's stored R1 and R2 values (D-host, at the interpolated contact state). Centre of mass: vz -2.07, horizontal 0.513 m/s (D-view); the 0.109 m/s difference is about angular rate times lever arm (approx.). Confidence: high.

**X9.** 8.18 s (E, step 818), a recorded event, between samples 8.1 and 8.2. The residual first exceeded the threshold in the 8.1 s sample (D-view approx.), 5 consecutive cycles earlier in control terms.

**X10.** No, not as stored. The recorded source hash (12b276cb18...) differs from the current tree (295a45b263...; src/landing_model.rs differs). Strict replay is rejected (stored request not canonical under the current catalogue). An earlier-build replay re-simulates with current defaults and agrees on outcome, safety, requirement verdicts, telemetry channels, events and metrics (not texts, scene, native files); that test result is shown. A commit is cited that reproduces the hash. Confidence: high for "not guaranteed exactly"; the exact current output cannot be known from the viewer.

**X11.** One. The altimeter rejection and sensor disagreement flags are the same condition, identical at every sample, first at 8.18 s. Nothing flags GNSS. Confidence: high.

**X12.** S2 is evaluated at contact only (no recorded time, not drawn on the time axis). It held: worst value 12.45 m against <= 50.00 m, passed; equals the R5 value. Confidence: high.

**X13.** About +15 m in x and z (configured 15 m). GNSS minus truth x: 14.94 at 8.0 s, 14.35 to 15.9 m over the run; z 14.1 to 15.6 m. Samples are noisy by about +/-1 m; y about 0 to -0.8 m. Confidence: high.

**X14.** One fix every 0.1 s (every 5 control cycles); 230 of 231 trace samples carry a fix, the off-grid touchdown sample reports "no fix on this cycle". What GNSS or the estimator reported between fixes: cannot tell; the trace has only 0.1 s samples and nothing is recorded in between. Confidence: high for cadence.

**X15.** At 14.0 s true nozzle distance was inside R5 (about 9 m; 8.91 m at 15.0 s; within R5 from 12.1 s to 15.7 s) but moving away: true x -3.30 and -5.8 at 15 s, drifting negative, ending outside. The estimator: velocity good (host velocity error 0.00 to 0.02 m/s) but position wrong by +15.1 m in x and +14.8 m in z; believed distance 11.48 m at 15 s (outside), believed inside R5 only from 15.6 s. So: not on course to end in R5, and the estimator was accurate in velocity but about 15 m biased in position. Confidence: medium-high.

**X16.** No. The initial state is dispersed by the seed (5002) from nominal: x 87.4 vs 80, y -21.3 vs 0, z 2956.4 vs 3000, vx -13.5 vs -12, vy -0.5 vs 0, vz -207.7 vs -200, within the half-widths. Fault configured 8.0 s to 40.0 s (32 s), but the run ended at touchdown 22.955 s with the fault still active, so it lasted 14.955 s in this run and could have lasted up to the configured end at 40 s. Confidence: high.

## Confusing or contradictory moments

1. "At the cursor" velocity table: the row "Host error, vertical and horizontal" sits under columns x, y, z but holds vertical and horizontal values (-0.13, 0.02), so reads as x and y errors.
2. "Detection: one condition" versus the event "disagreement and rejects the altimeter": two names for one flag; easy to count two detections (decisions section, events).
3. Rejection timing appears three ways: not fused from the first over-threshold cycle (about 8.1 s, approx.), flag at 8.18 s (recorded), rule changed "after the flag". The 8.1 s figure is approximate and sits between 8.0 and 8.18 s (card 4, "What the rejection does", residual strip).
4. 15.15 m appears twice with different meanings: estimate minus true CoM in x (card 2) and gap between believed and true nozzle points (card 4, "approx."). Coincident only because the two reference points shift together (card 2 versus pad plan note).
5. Believed distance bar "within R5 from 15.6 s to 22.955 s" while the true bar ends at 15.7 s: believed and true are inside and outside at opposite times; the touchdown estimate is from the previous control cycle, not the touchdown instant.
6. The requirement table's "Faults active" column shows gnss_bias on all six rows, including passing ones, despite the caution note below the table.
7. Outcome label "hard_landing" next to R1 passed at 2.07 m/s; the viewer has to explain the label does not mean a hard impact (Verdicts section).
8. "Guidance altitude rule" (S), "Lower altitude" (D-view approx.) and "Altimeter rejected" (E) mix three evidence classes in one table; the actual guidance altitude is not recorded, so "guidance used 375.7 m at 15 s" is an inference.
9. Chip bar says run source hash "is different" from the current tree, yet version 0.15.0 is the same in both; needs the Provenance section to make sense.
10. Ignition text: "event detail records command step 3.6 s as its command time", odd wording (step versus seconds).
11. True nozzle altitude shows "-0.00" at touchdown while CoM z is 14.85 m; correct (nozzle is 14.85 m below CoM) but not obvious without the fig-note.
12. Touchdown-sample GNSS cells all read "no fix on this cycle", including the error rows, which can look like an error value.
