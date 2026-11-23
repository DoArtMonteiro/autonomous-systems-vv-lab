# First independent review of the G3 review package (2026-11-18)

Agent role: `sonnet-critical-reviewer`. Not human review.

VERDICT: APPROVE WITH FIXES

No blocker. I found no altered hypothesis, threshold, seed range or decision rule, and nothing described as approved, frozen or confirmed. Package files contain no U+2014, personal names, emails or absolute paths. Findings are below, most severe first.

**Major**
- `reviewer-questions.md:59` (Q2) - MAJOR - "o G3, tal como registado, nunca produz uma aterragem que cumpra todos os requisitos" is generalised from one case. `g3-registered.json` has magnitude 15 m only, and `baseline_violations` R5 30/30 is for that case. G3 spans 5 to 30 m, and at 5 m the horizontal offset is about 7,07 m, inside the 10 m radius. Fix: restrict the sentence to 15 m with onset 0 s.

**Minor**
- `source-commitments.md:64`, `README.md:52` - MINOR - `ascent_abort_vz_mps` at `bec7b3f` is lines 426-430 (`within(` at 426, closing at 431), not "425 a 430". Lines 414-418 now hold the end of the `altimeter_velocity_gain` range and the start of the threshold block. The 0,1 to 1000 limits are at 421-422. Fix: correct both ranges. The drift itself is real (414-418 at `3962482`, +12 now). Line 250 is correct.
- `reviewer-questions.md:96` (Q5) - MINOR - the 0,5 s and 2 s window sensitivity is protocol l.192, not l.194. Fix: change the citation.
- `study-summary.md:11`, `limitations.md:50`, Q3 - MINOR - "contacto nominal 23,3 a 23,6 s" comes from M9 l.241. That line gives `baseline` 23,63 s and `robust` 23,27 s on the nominal M9 case, not `guarded` on the G3 case. Fix: say so.
- `reviewer-questions.md:187` (Q14b) - MINOR - the 12,5 % figure rests on "if all 35 are among the 280". `exec/src/investigate.rs:1165-1172` counts a tradeoff whenever the mitigated arm gains a requirement violation without an R1 regression. That includes pairs in the 744 `neither`. Fix: cite the code and give the range 35/1024 to 35/280.
- No question covers H1's success definition. It is a conjunction (R1 holds at 0 s and fails late). G3 only guarantees at least 0,9 at 0 s, so a G3-compliant 0 s rate of 0,93 sharply lowers H1 power. The power table treats π as a single rate. Fix: add a question and note this beside Verif. 3.

**Confirmed (recomputed independently)**
- Totals: 920 seeds, 5 800 runs, contiguous stage ranges, no overlap with spent or protected seeds.
- Minimum n for an all-success binomial test against 0,9: 69 at 0,01/14 (the protocol's "63" is wrong, 63 is for 0,01/7), 63 at 0,01/7, 55 at 0,01/3, 51 at 0,01/2.
- Rejection thresholds: 154 (H1, H2), 155 (S3), 228 (M1), 79 (M2), 80 (S7).
- Powers: 0,307, 0,793 and 0,9988 for H1/H2; M2 0,809; S7 0,4475.
- Order-statistic positions 20/41 and 19/42, with the same tail values.
- Clopper-Pearson budgets: 0, 13 and 1 events; 35/1024 gives 4,98 %.
- S4/S5 54-of-60 table, including 0,185 at π = 0,85 and 0,031 at 0,80.
- Model: b* = 11,98868, 3,996 / 7,992 / 11,989, onset invariance, peaks, first-rejection times, P2, S7 direction, and the oscillation behind -5,087.
- H3 exact probabilities 1,0 / 0,669 / 1,0.
- The appendix program runs and reproduces the package's numbers.
- 38 pinned blob hashes in `source-commitments.md`, including the protocol and the seeds, test, source and per-file hashes. All match `git cat-file blob bec7b3f:`.
- `source_sha256()` in `lib.rs`: 20 files, name, NUL, content with CRLF turned into LF, NUL. I re-derived the file list from each commit's `lib.rs`: 12b276cb… at `3962482`, `1195c1b` and `8be03e4`; a7d43d25… at `3baa1c1`; 295a45b2… at `04de572` and `bec7b3f`. The stale-hash claim is real and the derivation is correct.
- Only `landing_model.rs` changed in the hashed set since `3962482` (+152/-3). The `v1` path still calls `check_registered`.
- `1195c1b` changed only the output writes in `m14_masking_model.py` (3 added, 2 removed). Commit times are 20:20:38 and 20:25:07.
- 0,01 s and 0,1 s are the same physical condition: start step 1 and 10, active when `start_step <= step`, and the first GNSS sample is at step 10.
- The 44000-44999 overlap with `ROCKET_PROTECTED` is real.

**Not checked**
- Simulator-dependent figures: 30/30, 20/20, the 35 compromises, the 41, b50 = 11,89.
- Whether `v1` outputs are bit-identical across code versions.
- A compiled `source_sha256` (I did not build).
- The 20 000-draw resampling.
- Halton and quantisation behaviour.
- SplitMix independence.
- Time to contact for dispersed seeds.
- R5 at 5 m.

Files are under `<worktree:m19>/docs/review/g3-onset/`; the protocol is `<worktree:m19>/docs/m15-g3-onset-protocol.md`.
