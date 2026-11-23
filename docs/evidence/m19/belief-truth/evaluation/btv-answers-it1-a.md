# Answers, iteration 1, reader A

Sources used: the served viewer (rendered DOM at 1440 px, plus its data.json for the numbers it displays) and the screenshots in the iteration-1 evidence folder. Nothing else was read. Evidence classes are the viewer's tags: T truth, E estimate, O observation, C configuration, D-host (host-derived, stored), D-view (derived by the view), S (source code, not recorded). "Mine" means I derived it from displayed numbers.

## Q1. True trajectory and outcome

**1.1 Outcome and failed verdicts.** Outcome label "Touched down, requirements not met", code `hard_landing` (D-host). Only R5 failed (distance from pad centre 12.45 m against limit <= 10.00 m). R1, R2, R3, R4, R6 passed. S1 to S5 all passed. Where: Verdicts section and outcome box. Class D-host. Confidence high.

**1.2 True touchdown point.** The nozzle plane touched down at x = -12.32 m (east) and y = -1.79 m (north) of the pad centre, 12.45 m from it, at t = 22.955 s (step 2296). Centre-of-mass at that instant: (-12.27, -1.88) m. Where: "What really happened" step 1, "At the cursor" at the touchdown sample, Pad plan. Class D-host (nozzle point) and T/D-host (CM). Confidence high.

**1.3 Contact speeds, attitude, rate, propellant.** Vertical speed 2.07 m/s (limit <= 3.00). Horizontal speed 0.61 m/s (limit <= 1.00). Tilt cos 0.99997 (limit >= 0.99619); by my arithmetic about 0.4 degrees, limit about 5 degrees. Angular rate 0.0073 rad/s (limit <= 0.1). Propellant margin 4312.3 kg (limit >= 79.8 kg); the true propellant series reads 4312.3 kg at touchdown. Where: Requirements table; sample table. Class D-host (the verdict fields, evaluated at step 2296, per step by the host). Confidence high. The viewer shows attitude only as tilt cosine, not as an angle or quaternion.

**1.4 Trajectory shape.** Starts at t = 0 with the centre of mass at about x 87 m, y -21 m, altitude 2956 m, about 90 m from the pad horizontally. Ignition at 3.6 s (propellant 7981.6 kg falling to 4312.3 kg). Descent rate by my finite difference of the displayed truth altitude: about 215 m/s early, about 150 m/s at 10 s, 92 m/s at 15 s, 35 m/s at 20 s, 2 m/s at contact. Horizontally the true x runs from 87 m to about 0 by 9 s, then drifts slowly negative to -12.3 m; y goes from -21 m to -1.9 m. The distance of the nozzle plane from the pad is smallest at about 13.8 s (7.84 m by the view's own series), then grows back to 12.45 m. The plan view shows the curved ground track coming up from the south to the touchdown point west of the pad circle. Where: sample table (truth x, truth z), pad-distance row, Pad plan, touchdown readout. Class T plus mine for rates. Confidence medium. Gap: there is no altitude-against-time or ground-track chart other than the pad window of +-20 m, so the shape has to be assembled from the sample table.

## Q2. What the controller believed, and from which sensors

**2.1 What it received.** From the viewer: GNSS position (a centre-of-mass reading, x/y/z), an altimeter (measures the nozzle plane height), and IMU attitude and propagation, plus mission configuration. A source-code note says GNSS velocity exists and carries no bias. Where: the "S_estimator_fixed_gain" and "S_gnss_bias" source buttons, strips, readout. Class O for GNSS and altimeter, S for the IMU and velocity statements. Confidence medium. Cannot tell from what is shown: the IMU values or the GNSS velocity values; the IMU attitude is stored in the data but not drawn.

**2.2 Form of the belief.** A single point estimate of position (centre of mass) and velocity, from a fixed-gain blend of IMU propagation, GNSS and a gated altimeter. No covariance, so no uncertainty. Where: Uncertainty section ("U: none") and the source drawer. Class S. Confidence high.

**2.3 Belief at the end versus truth.** Last estimate before contact: centre of mass (2.88, -1.78) m, z 29.64 m. Truth: (-12.27, -1.88) m, z 14.85 m. So the estimate is +15.15 m east, +0.11 m north, +14.79 m above. Converted to the nozzle plane the believed touchdown point is (2.83, -1.68) m, 3.29 m from the pad centre (inside the R5 circle), against the true 12.45 m. Where: touchdown readout, steps 2 and 4, Pad plan. Class E for the estimate, T truth, D-view (approximate) for the believed nozzle point. Confidence high on the numbers, medium on the believed-nozzle conversion because it uses a proxy for the centre-of-mass station.

**2.4 Which sensor carried wrong information.** GNSS. The fault is `gnss_bias`, +15 m, on GNSS x and z, not y, active from 8.0 s. During the fault GNSS minus truth is about 15 m in x (13.8 to 16.3, mean 15.06) and in z (14.1 to 16.2, mean 15.04), and about 0 in y. The altimeter stayed within about +-0.27 m of the true nozzle altitude. Where: Fault chip, strips x, y, z. Class C for the fault, D-view for the errors. Confidence high.

## Q3. When and how far belief diverged

**3.1 Start.** At the fault start, 8.0 s (recorded event, T). The estimate error in x is 0.04 m at the 7.9 s sample and already 2.27 m at the 8.0 s sample. Before the fault it stayed within 0.40 m of truth in x. Where: step 3, event list, Fault onset zoom. Class D-view. Confidence high.

**3.2 Size.** The x error rises 2.27 m (8.0 s), 5.70 m (8.2 s), 12.36 m (9.0 s), 14.54 m (10.0 s) and then stays about 14.9 to 15.3 m to the end (15.15 m at the last estimate). The z error follows the same path (about 14.8 to 15.4 m). The y error stays within about +-0.4 m. Class D-view for x, D-host for z. Confidence high.

**3.3 Direction.** The estimate sits east of truth in x and above it in z (estimate minus truth is positive). The truth was therefore west and lower than believed. Confidence high.

**3.4 Recovery.** No. The error plateaus at about 15 m until contact; the fault never ended in this run (configured end 40.0 s, touchdown at 22.96 s). Class D-view. Confidence high.

## Q4. Decisions

**4.1 Reaction.** The only controller reaction shown is the altimeter rejection, first flagged at 8.18 s (step 818), between the 8.1 s and 8.2 s samples. The first sample with the flag true is 8.2 s. After it, guidance used min(estimator, altimeter). Class E (flag, recorded) and S (rule). Confidence high on the timing. The viewer shows no other controller reaction to the faulted GNSS in x or y.

**4.2 What the rejection changed.** According to the source note, with the guarded policy, while the altimeter is rejected guidance (only guidance) reads the lower of the estimated nozzle altitude and the altimeter altitude. The estimator state itself is untouched. At 15 s, for example, that is the altimeter, about 375.7 m, rather than the estimator's about 390.6 m (derived, approximate). Class S plus D-view. Confidence medium. Which of the two guidance used in each cycle is not recorded.

**4.3 Was it reasonable?** The viewer gives no verdict. What it shows: the rule is 5 consecutive cycles with a residual beyond +-3.0 m; the residual crossed -3 at the 8.1 s sample (-3.10), consistent with a rejection at 8.18 s. The sensor rejected was the accurate one (hindsight, using truth); the estimator is biased by GNSS. The controller has only two disagreeing sources and no uncertainty, so from its own observations it could not say which one was wrong. Cannot tell from what is shown whether this was "reasonable" in the sense of a design standard. Confidence low.

**4.4 Other decisions.** Cannot tell from what is shown. The viewer only says nothing similar to the altimeter check guards x and y, so the biased belief was followed there. Ignition at 3.6 s is shown as an event, but with no detail on the decision. Confidence low.

## Q5. Requirements and invariants

**5.1 Requirements.** R1 2.07 m/s pass; R2 0.61 m/s pass; R3 cos 0.99997 pass; R4 0.0073 rad/s pass; R5 12.45 m against <= 10.00 m FAIL; R6 4312.3 kg pass. Class D-host.

**5.2 Invariants.** S1 tilt envelope worst cos 0.98389 (>= 0.86603) pass; S2 keep-out 12.45 m (<= 50.00) pass; S3 axial load 2.27 g0 (<= 3.00) pass; S4 1 ignition (<= 1) pass; S5 climb under power 0.00 m (<= 5.00) pass. No failures; `invariants_pass` is true. Class D-host.

**5.3 Measured versus inferred.** The verdict fields are computed by the host per step from the true state and stored (D-host); nothing was re-derived by the view. Inferred or derived by the view: the believed nozzle point and pad distance (approximate), the altimeter residual (approximate), the lower-altitude source, and all the "estimate minus truth" x and y values. The "faults active" column lists the fault on every row and is not attribution. Confidence high.

**5.4 Why `hard_landing` with invariants passing.** The code is assigned whenever contact occurred and any requirement failed or S5 failed, and it does not say the impact was hard. Here only R5 failed; the impact was soft (2.07 m/s against 3.00 m/s). The invariants S1 to S5 are separate from the mission requirements. Where: outcome box and Verdicts. Class D-host plus S. Confidence high.

## Cross-check questions

**X1.** At about 15 s (sample 150) the true nozzle altitude is 375.49 m, the altimeter 375.66 m, and the estimated nozzle altitude about 390.59 m (approximate). The guidance rule is min(estimator, altimeter) and the lower source is the altimeter, so guidance used about 375.7 m, close to the truth (derived, approximate; the lower source per cycle is not recorded). The controller did not ignore the altimeter in guidance; it rejected it only in the estimator's check. Class S/D-view. Confidence medium. There is a small ambiguity about whether the rejected altimeter is also left out of the estimator's fusion; see the confusion list.

**X2.** Cannot tell whether it was "correct" by the viewer's standard. In hindsight the rejected sensor was the one close to the truth (0.19 m versus GNSS z 14.30 m at the last periodic sample). The viewer also shows that the guidance rule compensated in z. Confidence low.

**X3.** Not shown to be the cause. The viewer says the pattern is "consistent with the bias driving the miss" but there is no counterfactual run, so it does not prove it. The "faults active: gnss_bias" column appears on passing and failing rows equally. R1 to R4 and R6 passed, so none of those were caused by anything failing. Confidence high.

**X4.** Nothing about which requirement. `hard_landing` only says contact occurred and some requirement or S5 failed. It does not say the impact was hard (R1 passed at 2.07 m/s). Which one failed is read from the table: R5. Confidence high.

**X5.** At 8.0 s, the fault start; the estimate error is 2.27 m at the 8.0 s sample and 0.04 m at 7.9 s. The altimeter flag follows at 8.18 s. Confidence high. (The viewer's 0.1 s sample grid limits the precision of "exactly".)

**X6.** True nozzle point (-12.32, -1.79) m; believed nozzle point (2.83, -1.68) m; 15.15 m apart (D-view, approximate). Both refer to the nozzle plane (the point R5 judges). The GNSS marker in the plan is a centre-of-mass reading and sits at a different reference point. Class D-host and D-view. Confidence high on the numbers, medium on the believed point.

**X7.** There was none. The estimator has no covariance, so no confidence was held or reported ("U: none"). The case file's noise settings (GNSS sigma 0.5 m) are the simulator's noise, not the controller's belief. Confidence high.

**X8.** Vertical 2.07 m/s and horizontal 0.61 m/s at touchdown (step 2296, 22.955 s). They come from the host's stored verdict records (D-host, per-step evaluation from the true state), not from the sampled trace. Confidence high.

**X9.** At 8.18 s (step 818), a recorded controller flag (E). It lies between the 8.100 s and 8.200 s samples; the first sample where the flag is true is 8.200 s. Confidence high.

**X10.** Cannot tell exactly. The viewer says the run was recorded by the earlier 0.15.0 host and "still verifies under the current host (see the evidence document)", and a build log in the screenshot folder shows a test passing that a 0.15.0-written run verifies against its record under the current host. That is verification of the stored record, not a statement that the current simulator would regenerate an identical trace. The evidence document itself is not in my allowed sources. Confidence low to medium.

**X11.** One: the altimeter rejection at 8.18 s. The viewer shows no other detection, and says nothing similar guards x and y. The source note says the estimator checks only the altimeter. Class E/S. Confidence medium. Cannot tell whether other detectors exist that did not fire.

**X12.** S2 is evaluated at contact only, so at 22.955 s. It held: worst value 12.45 m against a keep-out limit of 50.00 m (the same distance as R5). The invariants have no recorded times, so none is drawn on the time axis. Class D-host plus S. Confidence high.

**X13.** About 15 m. During the fault (8.0 s to the end) GNSS minus truth is 13.80 to 16.25 m in x (mean 15.06 m) and 14.07 to 16.16 m in z (mean 15.04 m), including noise (sigma 0.5 m); about 0 (-1.3 to +1.4 m) in y. Configured bias 15 m. Class D-view/C. Confidence high.

**X14.** A GNSS value is present at every one of the 230 periodic samples (every 0.1 s) and absent ("none") at the touchdown sample. Cannot tell the actual GNSS measurement rate against the 0.02 s control cycle, or what the controller used between measurements (held value versus nothing). The viewer only says each stored sample carries the latest control cycle's observation, and that a missing sensor vector reads as none. Confidence low.

**X15.** At 14 s the true nozzle was at its closest approach to the pad, about 7.9 m (inside R5's 10 m at that instant), but moving away afterward (10.4 m at 16 s, 12.45 m at contact). The controller believed it was 14.07 m from the pad (approximate) and was steering to close it. The estimator was not working well: error about +15.1 m in x and +14.8 m in z, residual about -14.8 m against a 3 m threshold. So not clearly "on course for the pad" in a lasting sense. Class D-host/D-view. Confidence medium.

**X16.** Cannot tell whether the initial state was nominal. The viewer shows the starting position (about 87, -21, 2956 m) but nothing about a nominal initial state, and mentions that dispersions are assumed values. The fault was configured 8.0 s to 40.0 s. Because touchdown was at 22.955 s, the fault was active from 8.0 s to the end of the run, about 14.96 s of the run, and had it continued longer it was configured to last until 40.0 s. Confidence medium.

## Moments where the viewer confused me, felt ambiguous, or seemed inconsistent

1. Step 4 says "the estimator checks only the altimeter ... rejected", and the source note says the min rule affects "only guidance; the estimator state is untouched", while elsewhere the estimator is a "gated altimeter" blend. Unclear whether a rejected altimeter is still fused into the estimator. Location: "Why it mattered" and the S_guidance_min and S_estimator_fixed_gain drawers.
2. The x error is already 2.27 m at the 8.0 s sample, the same sample as the fault start. Reads as an instant effect; only the "last control cycle" limitation explains it. Location: step 3 and the Fault onset zoom.
3. The fault chip says "from 8.0 s to 40.0 s" but the run ends at 22.96 s; the viewer never says in plain words that the fault never ended during the run.
4. S2 repeats R5's distance (12.45 m), so it looks like an independent check but is the same number, with a different limit (50 m).
5. Mixed classes in one row ("Estimate minus truth": z is D-host, x and y D-view); explained by a note but easy to misread.
6. The plan window (+-20 m) hides the true nozzle plane at earlier cursor positions ("outside this window"); the trajectory is only visible as a track at touchdown.
7. Cursor starts at the first flagged sample (8.2 s), so the "At the cursor" readout opens at a mid-run state before the touchdown values the story mentions.
8. The outcome code `hard_landing` next to a 2.07 m/s landing; clarified in the outcome box, but the first sight is contradictory.
9. Believed nozzle point is derived with a proxy for the centre-of-mass station, yet the story presents "3.29 m, inside the R5 circle" in prose; the "approximate" tag is only in parentheses.
10. Several values show "none" for GNSS at touchdown without saying whether that means no measurement or no data.
