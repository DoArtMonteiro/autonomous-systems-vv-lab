# Belief vs Truth viewer: pre-registered answer key and trap questions

Written 2026-11-23, before the viewer exists. Keep hidden from the viewer's builder.
Language: English. No U+2014 anywhere.

## 0. Scope, sources and conventions

Run under test: `D:\vvwt\m192\desktop\domain-rocket\tests\fixtures\stored-by-0.15.0\`
(Studio 0.15.0 host, seed 5002, policy `guarded`, fault `gnss_bias` 15 m from 8 s to 40 s, run ended at touchdown 22.955 s).

Fixture integrity (checked with sha256 in this session): case.json `dc1301dd...`, trace.json `97783cfc...`, verification.json `3d6f543e...`, run.json `b2d81073...`. All equal the hashes in run.json and record.json `provenance.artifacts`.

Short names for files:
- REC = record.json. TR = trace.json (231 samples at 0.1 s; sample index i = t/0.1; i=82 is 8.2 s, i=150 is 15.0 s, i=230 is the touchdown sample). VER = verification.json. RUN = run.json. CASE = case.json.
- REC channels are lists keyed by `channels[].id`; every channel has 231 values on `timebases.trace`. Values equal TR to 5e-13.
- Source (all under `D:\vvwt\m192\crates\vv-rocket\src\`, line numbers are of the checked-out HEAD bec7b3f): CTL = landing_controller.rs, SEN = landing_sensors.rs, SIM = landing_sim.rs, VRF = landing_verify.rs, TYP = landing_types.rs, TRU = landing_truth.rs. Host record builder: `desktop/domain-rocket/src/record.rs` at commit 3b056cc (HOST).
- Provenance check done: the source hash recomputed from the 20 files listed in `lib.rs:25-58` at commit 3b056cc equals RUN `source_sha256` (`12b276cb...`). At HEAD the hash is `295a45b2...` (different). `git diff --stat 3b056cc HEAD -- crates/vv-rocket` shows only `landing_model.rs` and `tests/landing.rs` changed. So every line cited from CTL, SEN, SIM, VRF, TYP, TRU is byte-identical to what produced this record. Not executed: replay, cargo, any simulator.

Evidence classes used in every row:
- **[REC]** recorded value in the files.
- **[HOST]** derived by the host or verifier from truth and stored in REC/VER (verdicts, metric channels, scene block).
- **[VIEW]** derived by the viewer from recorded values (needs arithmetic or a defined threshold).
- **[SRC]** from source code, not recorded.
- **[NK]** not knowable from this record.

Frame: local flat, x east, y north, z up, origin at pad centre (REC `scene.frame`). Estimate and `pos_*` are centre of mass (CM); `base_*`, `altitude`, `pad_distance`, altimeter are the nozzle exit plane (REC `scene.vehicle.position_is`; host comment "The controller's own estimate of the centre of mass").

---

## 1. Comprehension questions

### Q1. What was the true trajectory and outcome?

**1.1 What was the outcome, and which verdicts failed?**
- Answer: touched down at t = 22.955 s (22.96 s rounded), outcome `hard_landing`, `requirements_pass` false, `invariants_pass` true. Exactly one requirement failed: R5 position (12.452 m, limit 10 m). Safety status "safe".
- Evidence: VER `outcome`, `requirements_pass`, `invariants_pass`, `requirements[4]`; RUN `outcome`, `summary.touchdown_t_s`; REC `outcome.code/status`, `safety.status`. Rule: VRF:501-507.
- Tolerance: time within 0.005 s; strings exact.
- Class: [HOST]. Cannot-tell: not acceptable.

**1.2 Where did the stage actually touch down?**
- Answer: nozzle plane at (-12.323, -1.790) m (east, north), i.e. 12.452 m from the pad centre, west-south-west of it. CM was at (-12.268, -1.884, 14.852) at that instant.
- Evidence: VER `touchdown.truth.base_position_m`, `requirements[4].value` = 12.452456; REC `scene.touchdown.nozzle_position_m`, `channels[pad_distance].values[230]`.
- Tolerance: 0.01 m. Reference point must be the nozzle plane (see trap T6).
- Class: [HOST]/[REC].

**1.3 What were the contact speeds, attitude, rate and propellant?**
- Answer: vertical 2.067 m/s down, horizontal 0.612 m/s (both of the nozzle plane), tilt 0.42 deg (cos 0.99997), angular rate 0.00735 rad/s, propellant left 4312.3 kg of 7981.6 kg.
- Evidence: VER `requirements[0..3,5].value`; REC `metrics[touchdown_*]`, `propellant_remaining_kg`. Formulas VRF:193-202.
- Tolerance: 0.001 m/s, 0.01 deg, 1 kg.
- Class: [HOST].

**1.4 Describe the true trajectory shape.**
- Answer: starts with CM at (87.4, -21.3, 2956.4) m, velocity (-13.5, -0.5, -207.7) m/s (dispersed by seed, not the nominal 80, 0, 3000). Free fall; engine lit once at 3.6 s (throttle jumps to the 0.4 minimum, then 0.50 to 0.68); peak descent speed 221.8 m/s at 3.6 s; descent decelerates to 2.07 m/s at contact. Horizontal distance of the nozzle plane from the pad: 90.0 m at 0 s, 22.6 m at 8.0 s, inside the 10 m landing radius from about 12.1 s to about 15.7 s (minimum 7.84 m at the 13.8 s sample), then back out to 12.45 m at contact. Never cut, never relit.
- Evidence: REC `scene.initial`, `channels[pad_distance]`, `channels[vel_z]`, `channels[engine_state]` (0 until 3.6 s, then 1), `events[ignition]`; VER `controller_flags`, S4.
- Tolerance: crossing times within 0.1 s (sample grid, linear interpolation between samples gives 12.07 s and 15.72 s); minimum 7.84 m +-0.05.
- Class: [REC]/[HOST] for channels, [VIEW] for crossing times.

### Q2. What did the controller believe, and from which sensors?

**2.1 What did the controller receive?**
- Answer: only observations and its configuration. Observations: radar altimeter (nozzle-plane altitude) every control cycle (0.02 s, never dropped out in this run, present in all 231 samples), GNSS position and velocity every 5th cycle (0.1 s, at steps that are multiples of 10), IMU (attitude, angular rate, specific force) every cycle. No truth.
- Evidence: CTL:1-4; TYP:53-60, 161-183 (config has no sensor sigmas); CASE `sensors.control_period_steps`=2, `gnss_period_cycles`=5, `dt_s`=0.01; SIM:211; SEN:66-103.
- Tolerance: exact cadence.
- Class: [SRC]+[REC] (`obs_*` channels, all non-null except `obs_gnss_*` at i=230).

**2.2 What form does the belief take?**
- Answer: an estimate of CM position and velocity (est_x..est_vz) plus three flags. Built by inertial propagation with the measured specific force and gravity, corrected at each GNSS fix with fixed gains (0.15 position, 0.25 velocity) and, while not rejected, by the altimeter (position gain 0.1 on z). Fixed-gain, no covariance, no uncertainty output.
- Evidence: CTL:107-133, gains in CASE `controller.gains`; TYP:77-88 (Estimate has only position, velocity, flags); REC channels `est_*`, `altimeter_rejected`, `sensor_disagreement`, `ascent_abort`.
- Tolerance: qualitative; must say CM, not nozzle.
- Class: [SRC]+[REC].

**2.3 What did it believe at the end, versus the truth?**
- Answer: believed CM at (2.88, -1.78, 29.64) m and therefore a horizontal distance of about 3.39 m from the pad and a nozzle altitude of about 14.8 m. Truth: CM at (-12.27, -1.88, 14.85), nozzle 12.45 m from the pad and at 0 m. The altimeter itself read 0.10 m. Caveat: the estimate in the touchdown sample is from the cycle at step 2294 (22.94 s), not 22.955 s (T8).
- Evidence: TR `samples[230].estimate.position_m`, `samples[230].truth`, `samples[230].observation.altimeter_m`; REC `channels[est_x,est_y,est_z]` last value. Est nozzle altitude = est_z - s_cm*nz, s_cm 14.85 (from truth propellant; the controller's own `propellant_est` is not recorded, so +-0.3 m).
- Tolerance: 0.05 m for est values; believed nozzle altitude 14.8 +-0.3; believed pad distance 3.39 +-0.05.
- Class: [REC] for est values, [VIEW] for believed distance and nozzle altitude.

**2.4 Which sensor carried the wrong information?**
- Answer: GNSS position only, biased +15 m in x (east) and +15 m in z (up), none in y, none in GNSS velocity. The altimeter stayed healthy: its reading minus true nozzle altitude stayed within -0.27 to +0.25 m over all 231 samples (bound of the noise model is +-0.346 m for sigma 0.1). Evidence of the bias: at 8.0 s GNSS-minus-truth is +14.94 (x), +14.68 (z), +1.40 (y, noise); at 12.0 s +15.34, +14.11, +0.60.
- Evidence: SEN:79-81 (`Vec3::new(bias, 0, bias)` added to position only); REC `channels[obs_gnss_*]` minus `channels[pos_*]`; `channels[obs_altimeter]` minus `channels[altitude]`; `prng.rs:58-71` (bounded noise).
- Tolerance: bias 15 +-1.0 m per axis (GNSS noise sigma 0.5, bounded +-1.73 m).
- Class: [VIEW]+[SRC]. Cannot-tell: not acceptable.

### Q3. When did belief diverge from truth, and by how much?

**3.1 When did the divergence start?**
- Answer: there is no recorded divergence instant. The recorded events give the truth-side fault onset (8.0 s) and the controller's own detection (8.18 s). By source, the first biased GNSS fix is at step 800 (8.00 s): fault active from step 800 (SIM:189), GNSS cycles at multiples of 10 steps (SIM:211). By samples: 3D estimate error is 0.16 m at 7.9 s and 3.01 m at 8.0 s (err_h 2.30, err_z 1.94), so onset lies in (7.9, 8.0] s and equals 8.00 s by source. Any viewer-defined instant needs a stated threshold: >1 m first at 8.0 s; err_h >= 10 m at 8.6 s; 90 % of the plateau (13.5 m) at 9.5 s.
- Evidence: REC `events[fault_start]` t=8.0; `channels[err_h]`, `channels[err_z]` at i=79, 80; SIM:189, 211; CASE `faults[0].start_s`.
- Tolerance: 8.0 s +-0.1 s with the threshold stated.
- Class: [VIEW] for the instant, [SRC] for 8.00 exactly, [NK] for "the controller's divergence instant" (does not exist).
- Cannot-tell: correct only if the answer says "no recorded divergence instant, depends on threshold" and still gives the 7.9-8.0 s bound.

**3.2 By how much did they diverge?**
- Answer: the position estimate converged to the biased value. Plateau from 10 s to touchdown: error (estimate minus truth, CM) x +15.06 m (range 14.59 to 15.33), z +15.04 m (14.76 to 15.37), y within -0.38 to +0.23 m, horizontal err_h about 15 m, 3D about 21.2 m (not 15). Velocity error is a transient: peak err_vz -1.23 m/s at 8.1 s, then within +-0.04 m/s (err_vh at most 0.06) after 10 s. Before the fault the error is noise: err_h <= 0.60 m at t=0 and <= 0.40 m for t >= 1 s; |err_z| <= 0.22 m.
- Evidence: REC `channels[err_z]`, `channels[err_h]`, `channels[err_vz]`, `channels[err_vh]`; x and y components = `est_x - pos_x`, `est_y - pos_y`.
- Tolerance: 0.3 m on the plateau, 0.05 m/s on velocity.
- Class: [HOST] for err_* channels, [VIEW] for components and 3D.

**3.3 In which direction was the belief wrong?**
- Answer: the controller believed itself 15 m too far east and 15 m too high relative to truth (sign: estimate minus truth positive). Therefore its lateral law steered the stage about 15 m west of where it thought it was heading, and it ended 12.4 m west of the pad.
- Evidence: SEN:79; REC est vs pos channels; VER `touchdown.truth.base_position_m[0]` = -12.32. Lateral law uses estimated x,y: CTL:248-264.
- Tolerance: sign must be right.
- Class: [VIEW]+[SRC].

**3.4 Did the divergence recover?**
- Answer: no. It persisted to touchdown (err_h 15.15 m, err_z 14.79 m in the last sample). The altimeter flag stays 1 in every sample from 8.2 s to the end, so the estimator never re-accepted the altimeter; the horizontal error has no corrective sensor in this controller (GNSS is the only horizontal position source, and it is the faulty one).
- Evidence: REC `channels[altimeter_rejected]` (1 for i=82..230); CTL:119-133; REC `channels[err_h]`.
- Tolerance: qualitative.
- Class: [REC]+[SRC].

### Q4. What decisions followed, and were they reasonable given what the controller could observe?

**4.1 When and how did the controller react?**
- Answer: at step 818 (8.18 s) it first raised `altimeter_rejected` and `sensor_disagreement` (same boolean, T11). Mechanism: |altimeter - estimated nozzle altitude| above 3.0 m for 5 consecutive 0.02 s cycles. The counter reaches 5 for the first time at step 818, so the streak began at the cycle of step 810 (8.10 s); the 8.1 s sample implies a residual of about -3.1 m. 0.18 s after fault onset. The exact 8.18 s is in the events and VER only; the 8.1 s sample shows flag 0 and the 8.2 s sample shows flag 1.
- Evidence: REC `events[altimeter_rejected].t`=8.18, `events[sensor_disagreement]`; VER `controller_flags.*_first`; CASE `controller.gains.altimeter_residual_threshold_m`=3.0, `altimeter_rejection_cycles`=5; CTL:119-127; REC `channels[altimeter_rejected]` at i=81, 82.
- Tolerance: 8.18 s exactly (within one control cycle, 0.02 s); 5 cycles; 3 m.
- Class: [REC] for the instant, [SRC] for the mechanism, [VIEW] for the 8.10 s start. The cycle-level residual is [NK] (not recorded).

**4.2 What did "altimeter rejected" change?**
- Answer: two things. (1) The estimator stops fusing the altimeter; the latch clears only if a residual <= 3 m is accepted, which never happens here. (2) Because the policy is `guarded`, vertical guidance (and tilt cap, time-to-go, cutoff test) reads the lower of the estimated nozzle altitude and the altimeter reading. It does not "ignore" the altimeter. The estimator state itself is untouched by rule 1. No ascent abort, no engine cut: `ascent_abort_first` null, engine on from 3.6 s to contact.
- Evidence: CTL:119-133, 192-200, 219; VER `controller_flags.ascent_abort_first` null; REC `events` (no cutoff event).
- Tolerance: must mention both effects.
- Class: [SRC]. What guidance actually used is not recorded (T1).

**4.3 Was rejecting the altimeter reasonable?**
- Answer (composite, score each part):
  - (a) Detecting a persistent 3 m+ disagreement is a reasonable trigger.
  - (b) Choosing which source to distrust: the rule only ever gates the altimeter against the fused estimate; GNSS is never gated (CTL:113-118 vs 119-133). The altimeter was in fact the healthy sensor, so in hindsight the wrong sensor was rejected. From a two-source residual alone the controller could not tell which was wrong: "could not tell" is correct. Nuance (also scored correct): the onset was detectable in principle because GNSS z moved only 2.07 m between 7.9 s and 8.0 s while truth moved about 17.3 m and GNSS velocity said about -172 m/s (REC `obs_gnss_z`, `pos_z`, `obs_gnss_vz`); this controller has no such test.
  - (c) The consequence was split: vertical guidance was protected by rule 1; horizontal guidance used the biased x estimate and nothing observable to this controller contradicts it (no other horizontal position sensor). The lateral law did what it was built to do: believed pad distance falls from 21.8 m at 10 s to 3.39 m at contact (REC `est_x`, `est_y`).
- Not knowable: whether another policy would have met R5 or R1 (no counterfactual run in the record). Inference from source only: altimeter handling cannot change the x bias, since the altimeter corrects z only (CTL:130-131).
- Evidence: as cited; SEN:79.
- Tolerance: all three parts; hindsight claims must be labelled as hindsight.
- Class: [SRC]+[VIEW]; counterfactuals [NK].
- Cannot-tell: correct for "was a different policy better", wrong for "was the altimeter actually faulty" (it was not: within 0.27 m of truth).

**4.4 Were there other controller decisions of note?**
- Answer: engine ignition at 3.6 s when required deceleration exceeded 75 % of nominal thrust over mass (CASE `ignition_fraction` 0.75); throttle stayed 0.50 to 0.68 after ignition; no cutoff, no abort. At the touchdown sample the command was 0.405 while the applied throttle was 0.504 (rate limit 1/s).
- Evidence: CTL:211-217; REC `events[ignition]`; `channels[cmd_throttle]`, `channels[act_throttle]`; TR `samples[230].command/applied`.
- Tolerance: 3.6 s exact; throttle range +-0.01.
- Class: [REC]/[SRC].

### Q5. Which requirement and safety invariant outcomes resulted, and which are measured versus inferred?

**5.1 Requirement results.**
- Answer: R1 2.0672 m/s <= 3 pass; R2 0.6120 m/s <= 1 pass; R3 cos 0.999973 >= 0.9962 pass; R4 0.00735 rad/s <= 0.1 pass; R5 12.4525 m <= 10 FAIL (2.45 m over); R6 4312.3 kg >= 79.82 kg pass (limit = 1 % of the 7981.6 kg initial propellant).
- Evidence: VER `requirements[0..5]`; REC `requirements[0..5]`.
- Tolerance: 4 significant figures.
- Class: [HOST].

**5.2 Invariant results.**
- Answer: all five hold on the true state, failure_count 0: S1 worst cos 0.98389 (10.30 deg tilt, limit cos 0.866 = 30 deg), S2 12.45 m vs 50 m (evaluated once, at contact), S3 peak 2.2686 g0 vs 3, S4 1 ignition vs 1, S5 0.0 m climb vs 5 m.
- Evidence: VER `invariants[*]`; REC `requirements[6..10]`, `safety`. S2 only at contact: VRF:455-471.
- Tolerance: 4 significant figures. Per-step peak tilt 10.2996 deg (VER) vs 10.2985 deg on the 0.1 s samples (REC `metrics[max_tilt_*]`): both acceptable, must name the source.
- Class: [HOST].

**5.3 Which of these are measured and which inferred?**
- Answer: every R and S value is computed by the independent verifier from the true simulated state (not from sensors, not from the controller) at the interpolated contact state (R, S2) or per step (S1, S3, S4, S5): "measured on the simulation truth". The controller flags are controller-reported and used in no verdict. The link "gnss_bias caused R5" is inferred, not measured: `cause` lists faults active at the contact step and `faults[0].acted: true` only says a biased fix occurred. Rule 1 "protected R1" is inference too. Idealised model, no contact dynamics, not validated against flight data.
- Evidence: VRF:1-3, 116-137, 193-210, 352-479, 541-543; VER `controller_flags.source`, `disclaimer`, `faults`; REC `model_validity`.
- Tolerance: must separate verdict (truth-based), controller claim, and causal inference.
- Class: [SRC]+[HOST]; causation [NK].

**5.4 Why is the outcome `hard_landing` while `invariants_pass` is true?**
- Answer: mission outcome and safety invariants are kept apart. Outcome is `landed` only if all six requirements pass and S5 passes; otherwise `hard_landing`. Here R5 alone failed. Name is the code, not a description of the impact (R1 passed with 2.07 m/s).
- Evidence: VRF:496-507; VER; REC `outcome.explanation`, `safety.explanation`.
- Tolerance: exact rule.
- Class: [SRC]+[HOST].

---

## 2. Trap questions (a plausible visual misleads)

Each trap: the question, the correct answer with evidence, the misleading answer, and why a visual would produce it.

**T1. What altitude did vertical guidance use at about 15 s, and did the controller "ignore" the altimeter?**
- Correct: with `guarded` and the altimeter rejected, guidance reads h_base = min(estimated nozzle altitude, altimeter reading) (CTL:195-200). At 15.0 s (step 1500, a control cycle) that is the altimeter reading, 375.66 m (TR `samples[150].observation.altimeter_m`), because the estimated nozzle altitude is about 390.6 m (est_z 405.10 minus s_cm*nz about 14.5; approximate because the controller's propellant estimate is not recorded). Truth nozzle altitude is 375.49 m. Over all samples from 8.2 s to 22.9 s the estimated nozzle altitude exceeds the altimeter by 4.8 m (at 8.2 s, still growing) and by 14.5 to 15.6 m from 10 s on, so the min is always the altimeter reading. The estimator ignores the altimeter; guidance does not.
- Misleading: 405.1 m (plotted `est_z`, which is CM and 15 m biased), 390.0 or 390.6 m ("what the controller thought"), or "it ignored the altimeter after 8.18 s".
- Class: [SRC]+[VIEW]. The value actually used is NOT recorded (no channel for h_base). Tolerance: 375.66 +-0.35 m; must name the rule and say it is not recorded. "Cannot tell, not recorded" alone is partial (record plus source determines it).

**T2. Was rejecting the altimeter "correct"?**
- Correct: it rejected the healthy sensor (altimeter error within +-0.27 m of truth throughout). With only an altimeter and a GNSS-fused estimate in disagreement and a rule that gates only the altimeter, the controller could not tell which was wrong (see 4.3 for the nuance that the GNSS step was detectable in principle). "Correct" is wrong, "wrong sensor in hindsight, indistinguishable by the residual rule" is right.
- Misleading: the "Controller first rejects the altimeter" event in green/detection style reads as a successful detection of a fault; or the opposite, "the controller blindly distrusted a good sensor and that caused the failure".
- Class: [VIEW]+[SRC]. Cannot-tell: correct for "was it a good policy" counterfactuals.

**T3. Did `gnss_bias` cause R5 (or R1, R2, R3, R4, R6)?**
- Correct: not established by the record. `cause: ["gnss_bias"]` appears on all six requirements, including the five that pass, because `cause` is the list of faults active at the contact step (VRF:203-208, attached at 238). `acted: true` means a biased fix was delivered (VRF:541-543). That the bias produced the R5 miss is a plausible inference from the 15 m horizontal belief error (steady, east) versus the 12.45 m miss, with no fault-free run to compare. No requirement other than R5 failed, so nothing else can be "caused".
- Misleading: "gnss_bias caused R2/R6 as well" or "R5 failed because of gnss_bias" stated as measured fact.
- Class: [SRC]; causation [NK]. Cannot-tell is correct for "caused".

**T4. Does `hard_landing` mean R1 (vertical speed) failed or the stage crashed?**
- Correct: no. R1 passed (2.067 m/s <= 3). `hard_landing` is the code for "touched down but at least one requirement or S5 failed" (VRF:501-507). Here only R5 (position) failed; invariants all pass; safety "safe".
- Misleading: a red "hard landing" banner suggesting a hard impact.
- Class: [SRC]+[HOST].

**T5. What is the recorded divergence instant?**
- Correct: none is recorded. Events carry only the fault start (8.0 s, source "fault") and the controller's detection (8.18 s, source "controller", "not used for any verdict"). Neither is a divergence measurement. Actual divergence: error already 3.0 m (3D) at the 8.0 s sample, 0.16 m at 7.9 s, onset 8.00 s by source; larger thresholds give later instants (err_h >= 10 m at 8.6 s). The 8.18 s event is a controller claim 0.18 s after onset, and the error by then was about 6 to 7 m (between the 8.1 s and 8.2 s samples: 5.2 and 7.5 m 3D).
- Misleading: placing "divergence" at 8.18 s (the detection marker), or at the first sample with the flag (8.2 s).
- Class: [VIEW]. Cannot-tell is correct if followed by the bound and the threshold dependence.

**T6. Reference points: centre of mass versus nozzle plane.**
- Correct: R1, R2 (speeds), R5 and S2 (distance) are evaluated on the nozzle exit plane (VRF:194-200); the altimeter measures the nozzle plane (SEN:67-71); GNSS, `est_*`, `pos_*`, `vel_*`, `vel_h` are CM. Consequences visible in the record: at contact `pos_z` is 14.85 m while the nozzle is at 0 (the model has no vehicle length, so do not draw a body that "hovers" 14.85 m up); `vel_h` ends at 0.513 m/s but R2 is 0.612 m/s; CM pad distance 12.412 m vs R5 12.452 m; `est_z` minus `altitude` is about 14.0 to 14.4 m even before the fault (7.9 s: 13.97 m) and about 29 m after it.
- Misleading: overlaying `est_z` on `altitude`/altimeter and reading a 14 m (pre-fault) or 29 m (post-fault) error; comparing the plotted `vel_h` with the R2 limit and R2 value; drawing the CM as the contact point.
- Class: [REC]+[SRC]. Tolerance: values +-0.001.

**T7. Is there uncertainty or covariance in the controller's belief?**
- Correct: none. The estimator is fixed-gain (CTL:113-118, gains in CASE); `Estimate` has only position, velocity and three flags (TYP:77-88); no record or trace key contains covariance, sigma, variance or confidence (searched REC and TR). `sensors.*_sigma` in CASE are the simulator's noise parameters on the truth side; the controller config has no sigma (TYP:163-183). The 3 m gate is a rejection threshold, not an uncertainty. A band around `est_*` would be invented.
- Misleading: +-sigma bands from CASE `sensors`, or a shaded "confidence" around the estimate.
- Class: [SRC]+[REC]. Cannot-tell is correct for "what uncertainty did it assign".

**T8. The interpolated touchdown sample versus the verdict values.**
- Correct: sample `i=230` (kind "touchdown", step label 2296, t = 22.9552 s = step 2295.52) has truth linearly interpolated within one 0.01 s step (TRU:26-53); its truth block equals `verification.touchdown.truth` exactly, and R1 (2.0672196) is its nozzle `base_velocity_mps[2]`, not the CM `velocity_mps[2]` (-2.0675466). Its estimate, observation and command are the last control cycle at or before the contact step, i.e. step 2294 (22.94 s), 0.0152 s older than the truth (SIM:244, 346-354); the 0.0996 m altimeter reading and `err_z` 14.79 m mix times. `obs_gnss_*` is null there because no GNSS fix falls on step 2294, not a dropout (T14). The host `pad_distance` metric 12.452455892488263 differs from the verdict 12.452455892488265 in the last digit only.
- Misleading: "step 2296 = 22.96 s", pairing the touchdown estimate with the contact truth as simultaneous, "GNSS lost at touchdown", or using the CM speed as the R1 value.
- Class: [REC]+[SRC].

**T9. The exact 8.18 s flag versus the 0.1 s sample grid.**
- Correct: the flag instant is 8.18 s (step 818), only in REC `events` and VER `controller_flags`. Samples are every 10 steps: 8.1 s has flag 0, 8.2 s has flag 1. A step drawn at the first flagged sample is 0.02 s late; interpolating the flag between samples is wrong. Likewise per-step peaks (S1 10.2996 deg, 7.2 s sample 10.2985 deg) and verdicts are not read from the grid: "Verdicts are computed on every step, not on the samples" (REC `notes[2]`).
- Misleading: a marker at 8.2 s, or a ramp between 8.1 and 8.2.
- Class: [REC]. Tolerance: 8.18 +-0.01 s.

**T10. 0.15.0 provenance versus the current source.**
- Correct: REC `domain.version` is "0.15.0" and the current catalogue still says 0.15.0, so the version string does not identify the build. RUN `source_sha256` (`12b276cb...`) is what discriminates: it equals the hash of the vv-rocket sources at commit 3b056cc and differs from the HEAD hash (`295a45b2...`; `landing_model.rs` changed with the v2 exploratory schema and parameters). The five files cited here are unchanged since. The record has 6 request parameters; the current catalogue has 13 more, other texts and other metrics (`earlier_build.rs:252-256` doc comment and test at 267+, test described as real drift; its assertions that strict replay under the current host is rejected and the earlier-build replay verifies were not executed here). Host text and channel definitions come from the 0.15.0 host.
- Misleading: assuming the viewer's or current Studio's wording, metrics and defaults describe this record; or presenting it as produced by the current build.
- Class: [REC]+[SRC]. Tolerance: must name `source_sha256` or state that the version string is insufficient.

**T11. Two flags at 8.18 s: independent detections?**
- Correct: no. `sensor_disagreement` is `Some(rejected)` for the policies that handle disagreement (CTL:74-77): the same condition as `altimeter_rejected`. Identical values in every sample. Neither identifies GNSS as the faulty sensor.
- Misleading: two detection markers read as two independent sensors or checks agreeing, or as "the controller identified the GNSS fault".
- Class: [SRC]+[REC].

**T12. "S2 keep-out held at every step".**
- Correct: S2 was evaluated once, at the contact state (VRF:455-471); its worst value equals the R5 value (12.452 m). The REC text "it held at every step" is the host template used for all invariants. S2 is not an in-flight check and not independent of R5. Pad distance was 90 m at t = 0, outside the 50 m keep-out, and nothing flags that.
- Misleading: a green in-flight S2 bar over the whole descent.
- Class: [SRC]+[HOST].

**T13. "gnss_bias 15 m" means GNSS was 15 m off.**
- Correct: 15 m on each of two axes: +15 east and +15 up, y untouched, velocity untouched (SEN:79-81). 3D position error is about 21.2 m; horizontal error 15 m; vertical 15 m. The estimate follows it with a lag of about 1.5 s (90 % at 9.5 s) because of the 0.15 fusion gain.
- Misleading: a single "15 m" radial offset, or an offset in the direction of the pad, or a bias also on GNSS velocity.
- Class: [SRC]+[VIEW].

**T14. GNSS cadence: continuous line through GNSS samples.**
- Correct: GNSS is at 10 Hz (every 5th control cycle); every 0.1 s sample lands exactly on a GNSS cycle, which hides the four of five control cycles without a fix. Between fixes the controller propagates with the IMU. A GNSS trace drawn as a continuous curve, or the touchdown null as a dropout, misrepresents what the controller received. Note REC `notes[3]`: sensor channels show the latest observation of the control cycle, empty while a sensor delivers nothing.
- Misleading: "GNSS outage at touchdown", or a 50 Hz GNSS line.
- Class: [SRC]+[REC].

**T15. "Inside the landing radius at 14 s" and "estimate error is stable, so the estimator is fine".**
- Correct: R5 is judged at contact only (VRF:200). The stage was inside the 10 m radius from about 12.1 s to 15.7 s (minimum 7.84 m) and left it again; at 15 s the controller believed it was 11.7 m from the pad, truth 8.9 m. A flat 15 m error line means the filter converged to the biased value; belief ended 3.39 m from the pad, a plausible-looking good landing that was not.
- Misleading: R5 "passed at 14 s"; a smooth, converged estimate read as accurate.
- Class: [REC]+[VIEW].

**T16. Nominal versus dispersed initial state, and the 40 s horizon.**
- Correct: CASE `initial` is nominal (80, 0, 3000; velocity -12, 0, -200). The run began at the seed-dispersed state (87.44, -21.27, 2956.38; velocity -13.50, -0.50, -207.67), in REC `scene.initial` and TR sample 0 (initial pad distance 90.0 m, nozzle altitude 2942.25 m). CASE `duration_s` 40 and the fault window end 40 s are limits, not what happened: the run ended at 22.955 s by touchdown, so the fault was still active at contact.
- Misleading: starting the replay from the nominal state, or showing the fault "ending" at 40 s on a 23 s timeline.
- Class: [REC].

---

## 3. Scoring rubric

Unit: each sub-question in section 1 (20 items) and each trap in section 2 (16 items). One point each.

| Grade | Points | Rule |
|---|---|---|
| Correct | 1 | Gives the answer within the stated tolerance, uses the right reference point (CM vs nozzle), the right instant (exact event time vs sample), and the right evidence class (does not present derived or inferred values as recorded or measured). |
| Partially correct | 0.5 | Right direction or right number but one defect: no threshold stated for a divergence time, wrong reference point within tolerance (T6), right value with wrong evidence class, one of several composite parts missing (4.3, 5.3), or the trap's correct answer given without the reason. |
| Wrong | 0 | Contradicts the key, gives the misleading answer of a trap, invents data (covariance, recorded h_base, recorded divergence instant), or states causation as measured. |
| "Cannot tell" | 1 or 0 | Counts as correct only where the key marks [NK] and the answer names the missing quantity: T1 (value not recorded; must still give the altimeter-reading bound to be full marks, otherwise 0.5), T3 (causation), T5 (needs threshold plus the 7.9-8.0 s bound, else 0.5), T7 (uncertainty), 3.1 (as T5), 4.3 counterfactual parts, 5.3 causation. On any item the key gives a determinate answer ("cannot tell" for 1.1-1.4, 2.1, 2.4, 3.4, 4.1, 5.1, 5.2, 5.4, T4, T6, T8-T14) the grade is 0. |

Pass criteria for the viewer (a person using only the viewer):
- Sub-questions: at least 85 % of the 20 points (17/20), and no wrong on 3.1, 4.3, 5.3.
- Traps: at least 12/16, and T1, T2, T3, T5, T6 must each be correct or partially correct (these are the viewer's core thesis: belief vs truth, reference points, causal restraint).
- Any trap answered with its misleading answer in 4 or more of T1-T7 means the viewer misleads and fails regardless of total.
- Score separately by evidence class: if viewers score well on [REC]/[HOST] items but badly on [VIEW]/[SRC]/[NK] items, the viewer shows data but does not explain it.

---

## 4. What this key could not verify

- Per-cycle quantities inside the 0.1 s grid (residual, exceed counter, h_base, the controller's `propellant_est`, s_cm) are not recorded. The 8.10 s streak start is derived from source plus the recorded flag instant; the residual -3.1 m at 8.1 s and the estimated nozzle altitude (about 390.6 m at 15 s, margin 4.8 to 15.6 m over the altimeter) use the true propellant for s_cm, approximate to about 0.3 m.
- Replay and re-simulation were not run (no cargo, no simulator). The upgrade-path claim in T10 relies on the test comments and code in `desktop/domain-rocket/tests/earlier_build.rs`, not on an execution.
- Counterfactuals (other policy, no fault, altimeter accepted) are not in the record.
- `record.rs` claims (channel definitions, "held at every step" template) were read at commit 3b056cc, which is the host that wrote this record; later hosts differ by 9 lines in `record.rs`.
- Noise bound (+-2*sqrt(3)*sigma) was read from `prng.rs:58-71`; the distribution beyond that was not examined.

## Orchestrator ruling (2026-11-23, before any evaluation)

"Could the controller tell which sensor was wrong?" Intended reading: with the implemented logic (residual threshold between altimeter and estimate, no GNSS self-consistency test), the controller had no mechanism to tell, so it rejected the healthy altimeter. The record also shows the GNSS position step at 8.0 s was inconsistent with the GNSS velocity, so a position-versus-velocity consistency test (not implemented) could in principle have flagged GNSS. Full credit requires the first part; the second part is a bonus and must be labelled as an inference about an alternative design, not a recorded fact.
