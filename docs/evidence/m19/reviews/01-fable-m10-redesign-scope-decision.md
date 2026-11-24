# Fable: M10 redesign scope decision

Agent role: `fable-strategic-advisor`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

**Decision.** Whether and how to run the single permitted M10 redesign. The risk is spending the one attempt on a design whose mechanism is unverified, or softening pre-registered criteria after predicting they fail. All three items are owner decisions required in writing before stage 1; this is advice to Opus, not approval.

**Framing problems**
- **Mechanism unverified.** The pre-registration says the 58 U are "compatível, mas não demonstrada" with missing NIS rejection (sections 1.1, 2).
- **Diagnostics dropped.** The strategy orders two diagnostics before the redesign (steps 1 and 2, lines 91-92). The pre-registration folds step 1 into phase 2 and drops step 2, without declaring a deviation.
- **Regression question already answered.** Decision 2 mixes "did the redesign fix isolation?" with "is B+ acceptable against `robust`/`guarded`?". The second is no, whatever the run shows.

**1. Scope**
- **Abstention-only:** matches the letter, but is predicted to fail clause 2, so it wastes the attempt.
- **Abstention + NIS:** defensible as one policy, but only if evidence shows the 58 U are un-isolated runs still assimilating the receiver. Otherwise it is tuning toward a criterion defined relative to B.
- **No run:** legitimate, but leaves the mechanism unknown.

Recommend abstention + NIS, conditional on the diagnostic under "Cheapest next step". If the 58 are mostly late-correct isolations or lateral failures, declare no-go from existing evidence.

Owner option: an abstention-only ablation arm on G1, declared now and report-only. My judgement is that this is not a "second attempt", contrary to section 2.

**2. Regression limits**
- **Keep strict.** Relaxing a limit after predicting its failure is the standard-lowering the owner excluded.
- **Narrow it to one cell.** Strategy line 85 treats `gnss_bias` as an accepted `E0` limit, always shown in U. I cannot tell whether that row is owner-approved or only a recommendation; confirm it.
- **The binding failure.** If the row stands, only `altimeter_bias` + `gnss_dropout` (+19 U) fails in advance. The owner mandate names it, no decision accepted it, and its only fix (bounded chase) is rejected.
- **Consequence.** No V1 result changes any owner decision. Tell the owner the global verdict is no-go in advance and the run is a V1-only closing experiment.
- **Still run it** (judgement). The real cost is implementation and review, not the 13 minutes. It delivers the single-binary rerun, per-seed records, the never-executed test 9, and a closed finding instead of a recorded symptom.

**3. Clause 1 and 1.5x noise**
- **Include M3.** "Alguma" is unqualified, and the pre-registration should not offer the exclusion.
- **Add B to M3.** M3 runs only B+ and B+G, so the "B has `hv`, rule miscalibrated" safeguard cannot be evaluated at 1.5x.
- **Amend the cap first.** That is +2,400 runs, 42,900 total, over the 42,000 cap.

**Methodological flaws, in order**
1. **Clock starts too late.** Section 3.1 requires a gate-on unit test, so gate-on code runs, and may get fixed, before stage 1. Pin the test seed now, outside 5020-5059, and start the clock at the first gate-on execution. The same applies to the 1.5x trial run.
2. **Clause 2 is vacuous at low magnitudes.** `probe-rampbase-summary.txt` shows B at U 80/80 at 0.3 m/s, and 0.2 is likely the same. The real tests are 0.5, 0.8 and the 18-seed stratum; say so.
3. **Clause 2 ignores most of G1.** It binds on 80 of 640 runs per magnitude and skips most ignition-window onsets. Add a proportional full-grid limit (judgement).
4. **S6b is too loose.** It lets `gnss_coherent_ramp` recovery fall to 39 against B+'s 57, an 18-recovery loss, where the general materiality rule is 5. Justify or tighten it.
5. **Clause 3 is weak where the defect lives.** It pools the M1 cells, where B+ had 1 wrong isolation in 2,400 at nominal noise. Consider G1 at 0.3 and 0.5 m/s with 1.5x noise.
6. **Gate has no exit.** It ends only on CUSUM decay or isolation. Report rejection-streak lengths in case S7 misses a lock-out.

Seed handling is otherwise honest: non-independence is declared, and the constants reuse existing values.

**Cheapest next step.** Run strategy step 1 on unmodified B+: `rampbase` at 0.5 m/s, seeds 5000-5019, B and B+, with per-run records (about 160 runs). Decompose the 64 U by isolation verdict and failed requirement. This spends no part of the attempt and settles decision 1.

No leadership proposal.

**Files**
- `<worktree:m10r>/docs/m10-redesign-preregistration.md`
- `<worktree:m19>/docs/m19-programme-strategy.md`
- `<worktree:m10r>/docs/m10-decision-dossier.md`
- `<worktree:m10r>/docs/evidence/m10-dev/independent-review/probe-rampbase-summary.txt`
- `<worktree:m10r>/crates/vv-rocket/src/nav_filter.rs`

CONFIDENCE: medium. The documentary claims are checked against the files; the scope and run-value calls are judgement and depend on the diagnostic and on the owner's reading of line 85.
