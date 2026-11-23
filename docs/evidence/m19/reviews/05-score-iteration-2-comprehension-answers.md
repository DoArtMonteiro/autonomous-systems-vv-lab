# Score iteration 2 comprehension answers

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

Agent-based evaluation, not a human comprehension study.

Key hash verified: fc9993ef... matches the frozen value. I scored iteration 2 against the rubric before reading the iteration 1 evaluation. I checked the answers against `data.json`, `extract.py`, `index.html` and `js/app.js` of the viewer, and against `trace.json` and `record.json` of the fixture. I did not re-run the replay or hash checks.

## Sub-questions (20)

| Item | Score | Reason |
|---|---|---|
| 1.1 | 1 | Outcome, only R5 failed, all invariants passed. |
| 1.2 | 1 | Nozzle (-12.32, -1.79), 12.45 m; CM values also given. |
| 1.3 | 1 | All values correct. It hedges whether "margin" means propellant remaining. |
| 1.4 | 1 | Dispersed start, ignition at 3.6 s, minimum 7.84 m, inside the radius 12.1 to 15.7 s. |
| 2.1 | 0.5 | Cadence and the altimeter are right. GNSS velocity and the IMU contents are missing ("cannot tell" for the IMU). |
| 2.2 | 1 | Point estimate, fixed gain, no uncertainty. The three flags and the IMU propagation are not described. |
| 2.3 | 1 | CM estimate exact, believed nozzle altitude 14.79, last-cycle caveat given. Believed pad distance given as 3.29 (nozzle point); the key's 3.39 is the CM figure. Reference point is labelled. |
| 2.4 | 1 | GNSS x and z, altimeter within 0.2 m. |
| 3.1 | 1 | No recorded instant, bound 7.9 to 8.0 s, threshold picker named. |
| 3.2 | 1 | Plateau about 15 m, y small, thresholds listed. The velocity-error transient is omitted. |
| 3.3 | 1 | East and up. |
| 3.4 | 1 | No recovery, fault active to the end. |
| 4.1 | 1 | 8.18 s, 5 cycles from 8.10 s, residual -3.10. |
| 4.2 | 1 | Both effects, the min() rule, and "from the source" labelled. |
| 4.3 | 1 | Reasonable given the residual test, wrong sensor in hindsight, could not tell, other arbitration not shown. The horizontal consequence is in 4.1 and X2, not in 4.3 itself. |
| 4.4 | 1 | Ignition, throttle, no cutoff. |
| 5.1 | 1 | All six values. |
| 5.2 | 1 | All five values. |
| 5.3 | 1 | Verdicts from truth, flags unused, causation inferred, `cause` column is not attribution, model idealised. |
| 5.4 | 1 | Exact rule. |

Primary totals: Q1 4, Q2 3.5, Q3 4, Q4 4, Q5 4, **19.5/20**. This passes the 17/20 threshold, with no "wrong" on 3.1, 4.3 or 5.3.

Strict variant: any omitted key element, hedge or unreconciled value is docked 0.5. That means 1.3, 2.2, 2.3, 3.2 and 4.3, giving **17.0**. That is a borderline pass, and it depends on five judgement calls.

## Traps (16)

| Trap | Score | Misled? | Reason |
|---|---|---|---|
| X1 | 1 | No | Min rule, 375.66 m used, estimate about 390.6 m, not recorded. |
| X2 | 1 | No | Consistent with the logic, but it discarded the correct sensor. |
| X3 | 1 | No | Cannot tell; `cause` is not attribution. |
| X4 | 1 | No | The label names no requirement. |
| X5 | 1 | No | Not recorded, bound 7.9 to 8.0 s. |
| X6 | 1 | No | Nozzle and CM both stated with their reference points. |
| X7 | 1 | No | None exists. |
| X8 | 1 | No | Values correct, sourced to the verdicts. It saw the 0.52 against 0.61 gap and only "presumably" explained it. |
| X9 | 1 | No | 8.18 s flag, between samples. |
| X10 | 1 | No | Hash differs, version string insufficient, 6 parameters. |
| X11 | 1 | No | One detection reported twice. |
| X12 | 1 | No | Checked at contact only, equals R5. |
| X13 | 1 | No | x and z, y about 0. Velocity untouched, 3D 21 m and the lag are not stated. |
| X14 | 0.5 | No | Cadence and the touchdown null are right. "Cannot tell what GNSS reported between fixes" is wrong, because it reports nothing. Propagation by the IMU is not stated. |
| X15 | 1 | No | Inside the radius at 14 s, then out; the estimator is 15 m off. |
| X16 | 1 | No | Dispersed start, 40 s is a limit. |

Primary: **15.5/16**, pass. T1, T2, T3, T5 and T6 are all full marks. Core traps misled: 0. Strict (X8, X13 and X14 at 0.5): **14.5/16**, still a pass.

The [VIEW], [SRC] and [NK] items scored as well as the [REC] and [HOST] ones. The viewer explains as well as it shows.

## Comparison with iteration 1

| | Iteration 1 | Iteration 2 |
|---|---|---|
| Sub-questions | 15.5/20 (fail) | 19.5/20 (pass) |
| Traps | 12.5/16 | 15.5/16 |
| Core traps misled | 0 | 0 |

The biggest gains are in Q4 (+1.5) and Q3 (+1.0). That matches the iteration 1 diagnosis of under-explained decisions and divergence thresholds.

## Root cause per miss

- 2.1 (0.5): (a). GNSS velocity and the IMU are not shown. `extract.py` has `gnss_vx..z` in the trace, but the viewer has no GNSS velocity series.
- X14 (0.5): (c) mostly. The viewer says "no fix on this cycle" and mentions IMU propagation in the estimator fact. The answerer mis-framed "reported between fixes".
- Strict-only docks:
  - 1.3 is (b): the host label "Propellant margin" is shown verbatim and the initial 7981.6 kg is absent.
  - 2.2, 2.3, 3.2 and 4.3 are (c).
  - 2.3 is also (d): the key's 3.39 is the CM distance, while the viewer's nozzle-plane 3.29 is a different quantity.
  - X8 is (a): see R2 below.
  - X13 is (c).

## The answerer's 11 confusion points

| # | Verdict |
|---|---|
| 1 | Real, minor (b). The class key sits at the bottom of the page. |
| 2 | Real, minor (b). `app.js:720` prints "sample N of 230", where 230 is the last index and the count is 231. |
| 3 | **Real (a).** R2 0.6120 is the nozzle-plane value; CM `vel_h` is 0.5131. The viewer's `check.R2_nozzle` only confirms R2 equals the nozzle velocity, and nowhere shows nozzle-plane horizontal velocity, so 0.61 against 0.52 cannot be reconciled. I confirmed both numbers in `trace.json`. The viewer's R2 statement is not wrong. |
| 4 | **Real, minor (a).** `index.html:39` "Nothing guards x and y" has no tag and no source button. The statement is true: GNSS is fused unconditionally and only the altimeter is gated. |
| 5 | Real, minor (b). Card 4 says "By 8.18 s the altimeter had stopped being fused". That is true, because fusion stops at 8.10 s, but it blurs the flag instant and the fusion cut-off. `S_rejection_not_fused` is correct. |
| 6 | Real but mitigated (b). The column header and the note both say "not attribution", and the answerer scored X3 correctly. |
| 7 | Answerer error (c). Overlapping windows are not a defect. |
| 8 | Real (a/b), as in 1.3. |
| 9 | Real (a), as in 2.1. |
| 10 | Intended wording tension, not a defect. The answerer handled it correctly. |
| 11 | Coincidence (bias 15 m against nozzle offset 14.85 m). Not a defect. |

## Factual errors

I found no factually wrong viewer statement. Spot-checks that matched the fixture and source:

- Altimeter lower than the estimated nozzle altitude in 149 of 149 flagged samples.
- Nozzle altitude 1301.1 m at 8.0 s.
- `err_h` 0.13, 2.30, 4.15, 5.70 and 10.09 m at 7.9, 8.0, 8.1, 8.2 and 8.6 s.
- The fusion and rejection rule against `landing_controller.rs` at commit 3b056cc.

The key itself has two imprecisions (d):

- Key 3.2 says `err_vz` stays within ±0.04 m/s after 10 s, but the touchdown sample is 0.129 because it is a mixed-time cycle.
- Key 4.2 calls the rejection a "latch" that stops fusion, whereas fusion actually stops at the first over-threshold cycle.

## Not checked

- I did not re-run the replay or the earlier-build test.
- I did not recompute the source hashes.
- I did not render the viewer.
- Most derived "approx." values, such as the believed nozzle point, were not recomputed.

Files are in `<scratchpad>/`:
- `btv-answer-key.md`
- `btv-questions.md`
- `btv-answers-it2-a.md`
- `btv-eval-it1.md`

The viewer is at `<worktree:m192>/spikes/m19-belief-truth/`.
