# G3 candidate second review after corrections

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

No blockers. All 15 corrections are applied. The remaining findings are wording, scope and disclosure gaps.

**Correction table** (line numbers refer to `docs/m19-g3-onset-protocol-candidate.md`)

| # | Result | Evidence |
|---|---|---|
| 1 | PARTLY | H1a, the licensed phrases and the S3 requirement for the R5 claim are correct (164, 170, 357-360). The FWER argument (168) is correct. But line 360 says "nenhuma hipótese, tabela ou título a usa" ("mascaramento"), and the word is still used in the history tables at lines 126 and 128. |
| 2 | FIXED | Allocation is in "Por decidir" (444-467), both options costed. I recomputed A and B. |
| 3 | FIXED | One exact sign-test rule with floor 10 at 0.01/7 (28, 179, 353). The script uses `S4_S5_FLOOR`. A minimum of 10 discordant pairs (2^-10 < 0.01/7 < 2^-9) and power ≥ 0.9999 at rate 0.5 (0.99996) both reproduce. |
| 4 | FIXED | The exclusion list in (c) covers every A-derived test and the D/E pairs. The caps 8, 7, 15, 15 and 8 are correct. no_contact and evaluated=false are treated per test in (d). The justification is from the model; the test confirms slowest = 0.58 s. |
| 5 | FIXED | H1b n = 308 with threshold 290 at 0.01 (confirmed). Power at p0 0.95/0.97/0.99 is 0.795/0.997/1.000 (confirmed). The wording is consistent, but see finding 3. |
| 6 | FIXED | b_s convention at line 216, implemented in `b_s_per_seed` and tested. |
| 7 | FIXED | Threats are at lines 434-435. The Hoeffding condition k > 0.9n+1 holds numerically: 162>152.2, 136>127, 290>278.2, 220>208.9, 76>70.3, 316>303.4. The theorem is stated correctly. |
| 8 | FIXED | Freeze requires the written approval (407-408). The executor refuses 44000-44919 unless the guard is changed by an approved commit (405). There is no private list. |
| 9 | FIXED | Exact wording at line 11. |
| 10 | FIXED | Line 390. |
| 11 | FIXED | The differences table (23-52) is concise with no drafting history. |
| 12 | FIXED | The test uses `"/u2014"`. The only literal dash in the four files is line 1 of the doc. |
| 13 | PARTLY | The computation is right (see below). Disclosure and implication are incomplete (finding 2). |
| 14 | FIXED | Lines 82 and 438. |
| 15 | FIXED | Line 17. |

The label is at line 1 and the Estado section is at lines 5-19. `docs/m15-g3-onset-protocol.md` and `docs/review/g3-onset/` are byte-identical to 4777160, and only the four expected files changed. The sha256 values at lines 13-14 match the HEAD blobs.

**Independent recomputation** (exact fractions, my own code)
- H1b: thresholds 290/308 and 316/336 at 0.01 are correct.
- Thresholds: H1a and H2 at (0.01/3, 0.01/2, 0.01) give 162, 161, 161 and 136, 135, 135. Option B H2 at 0.01/3 is 162/168. S3 is 163/168 in B.
- Holm joint power: 0.7549 (A) and 0.8653 (B) in the moderate scenario, using H3 class 3 (shift 0.25, power ≈ 1.000). The pessimistic and development-like Holm values depend on the H3 distribution and the repo's reconstructed b_s, so I did not recompute them independently.
- "Mascaramento" point values: 0.755×0.5892 = 0.445 (A), 0.865×0.6088 = 0.527 (B), and 0.339 and 0.402 for the pessimistic scenario. All consistent.
- Also confirmed: the 63 versus 69 minimum n, the 54/60 acceptance probability of 0.185 at rate 0.85, S7, M1 and M2 powers, and the budget limits 0.979/0.996/1.041 % (468/460/440 pairs) and 12 events (4.82 % / 4.90 %).
- Script run: `python -m unittest tests.test_m19_g3_power` ran 41 tests, OK. `--check` printed "identical".

**Finding 13 (cross-range overlap)**
- Independent recount, coded separately from the repo's version: 288 overlapping stream pairs, 258 seeds, no pair with the same source on both sides.
- A brute-force hash of the dispersion sources reproduces the 126 dispersion pairs exactly.
- Explicit generator outputs confirmed 8 sampled pairs, for example (44885, altimeter) with (59645, IMU rate) share 7996 words.
- Intra-block overlap within 44000-44919 is 0.

**New findings, most severe first**
1. Finding 2 (the overlap finding is incompletely handled), at lines 400, 7-19 and 444-467 - MINOR to MAJOR.
   - The overlap is structural: the stream start is `seed ^ source×G`, so for each source pair the partner seed is fixed by a constant XOR.
   - It is not specific to this block. By the same arithmetic, 41000-41999 against 42000-43999 gives 214 dispersion-word pairs in 146 seeds. 42000-43999 against 45000-46999 gives 42 in 42 seeds.
   - The doc does not say this, so "unseen" has never been strictly true in this repository.
   - Impact on validity is small. The shared words feed different physical roles, for example a new altimeter noise stream against a seen IMU-rate stream, so no outcome dependence is evident. The loss is the literal claim of unseen realisations, not the type-I control.
   - A_low is the most affected: 116 of its 168 seeds.
   - The finding is not in the Estado section or in "Por decidir". Flagging it in the final request (473) is useful but not enough.
   - Fix: add it to "Por decidir" with options: (a) accept and disclose as a repository-wide property; (b) move to a block with zero overlap, found with `cross_independence`; (c) exclude the 258 seeds. State that the per-stage counts apply to option A only. Also state that only the listed ranges were checked, not other seeds used in the repo (42, 1337, 2026, the 100-129 range).
   - Add a test that confirms one cross pair against explicit generator outputs. The current test only reads JSON.
2. Lines 126 and 128 against 360 - MINOR. The doc says no hypothesis, table or title uses "mascaramento", yet two tables do. Reword them ("R1 falha", "recuperação") or qualify line 360.
3. Lines 165 and 359 - MINOR. The pooled H1b (n = 308) tolerates 18 failures, which could all sit in the low band, yet the licensed phrase is "G3 replicado nas bandas testadas". Say "no conjunto das bandas" and report the per-band rates descriptively.
4. Line 181 - MINOR (inherited from M15, but it now gates a licensed word). S6 takes only seeds "com rejeição", so seeds with no rejection drop out of the denominator. Count them as non-successes or report them.
5. Lines 388 and 405 - MINOR. An approved guard change could unlock the whole range 44000-44999 in `ROCKET_PROTECTED`, which would also unlock the reserve. State that the change must be narrowed to 44000-44919.
6. Line 180 - MINOR. "Os valores de π dependem das duas taxas" is left over from the binomial framing, but S4 and S5 are now sign tests.
7. Line 434 - MINOR. The Hoeffding list omits S3 in option B (163/168), S7 (77/77) and S6. The test hardcodes the pairs instead of reading the computed thresholds.
8. Line 367 - MINOR. The 1.0 s exposure justification covers the rejection time only for biases above b*. For the low band, no rejection is expected. The rule is not stated for stages B and C, nor for non-GNSS faults in E.
9. Line 11 - negligible. The test also generates explicit generator outputs for (44000, 2) and (44128, 6), which "leem os estados iniciais" slightly understates. Line 395 does disclose it.

CHECKED: all four candidate files, the full `git diff dc1f18c e3ffbef` for tests, `prng.rs`, `seeds.rs`, the unit tests and `--check` (run), the independent arithmetic listed above, and byte-identity of the protected files.

NOT CHECKED: H3 class probabilities and the reconstructed b_s distribution (pessimistic Holm values); the sha256 of the 34 pinned sources; the M13/M14 evidence numbers (not re-derived from the JSON blobs); no simulator or cargo run, as instructed.
