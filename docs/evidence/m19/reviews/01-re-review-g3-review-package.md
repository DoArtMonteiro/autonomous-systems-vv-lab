# Re-review G3 review package

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

The package works for an external reviewer. Everything I could recompute without simulating matches, and all six prior findings are fixed or nearly so. The remaining problems are small citation and wording errors. The worktree has an uncommitted change to `docs/m19-programme-strategy.md`, outside the package. The six `g3-onset` files match the commit.

## Prior findings

| Prior finding | Status | Evidence |
| --- | --- | --- |
| Q2 generalised from the 15 m case | FIXED | `reviewer-questions.md:60` now limits the claim to "início 0 s e 15 m". It says the result "não se generaliza ao G3 inteiro". It notes that the horizontal bias is x only, so the offset at 5 m is inside the 10 m radius. A grep finds no remaining "nunca produz". |
| `ascent_abort_vz_mps` line range (425-430 should be 426-431) | PARTLY FIXED | `source-commitments.md:64` and `independent-checks.md:196` now say 426-431. `landing_model.rs` confirms `within(` at 426 and the close at 431. `README.md:52` still says lines 414-418 "mostram hoje os limites 0,1 a 1000". That is wrong. Lines 414-416 are the end of the `altimeter_velocity_gain` range and 417-418 start the `within(` call. The 0,1 and 1000 values are at 420-421. |
| Q5 window citation (l. 194 should be l. 192) | FIXED | `reviewer-questions.md:97` cites l. 192, which is the protocol sentence on 0,5 s and 2 s. |
| Nominal contact time of 23,3 to 23,6 s | FIXED | `study-summary.md:11` and `:181`, `limitations.md:50` and Q3 (`reviewer-questions.md:71`) now cite `m9` l. 241. They say 23,63 s for `baseline`, 23,27 s for `robust`, nominal case, seed 0, not `guarded`. |
| Q14b 12,5 % figure | FIXED | `reviewer-questions.md:188` and `independent-checks.md:179` cite `investigate.rs:1165-1172` and give the range 3,4 % to 12,5 %. I checked the code. With `broken` = 0 and `both` = 0, the call must use the claim property, so `tradeoff` can include `neither` pairs. `investigation.json` gives fixed 280, neither 744, tradeoff 35, with 26 in R2 and 9 in R5. |
| No question on H1 being a conjunction | FIXED | Q25 (`reviewer-questions.md:195`) and the note in `independent-checks.md:74-83` were added. The powers 0,0639 (the file prints 0,064), 0,155 and 0,549 recompute. |

## New findings

- `README.md:52` - MINOR - wrong line description, as above. Fix: say lines 414-416 close the `altimeter_velocity_gain` range, 417-422 hold the threshold `within(` call, and the limits are at 420-421.
- `limitations.md:37` - MINOR - says M13 and M14 state that the "independent" reviews were done by agents, not people, citing `m14-evidence-robustness.md` l. 130. That line only says the same agent designed the strategies. I found no "pessoas" or "humana" in the M14 document. M13 l. 120 does say it. Fix: cite only M13 l. 120 for that claim, or find a real M14 line.
- `source-commitments.md:60` - MINOR - says the lines "mudaram com o mesmo commit `3baa1c1`". They moved in two steps. `ascent_abort_vz_mps` was at 415 in `3962482`, 424 in `3baa1c1` and 427 in `04de572`. The 5 m altimeter-bias minimum was at 238, then 247, then 250. Fix: name both commits.
- `reviewer-questions.md:60` (Q2), `study-summary.md:48` - MINOR - Q2 says R5 at 5 m "não foi verificado". `docs/m9-powered-landing.md:627` already gives evidence. It reports that `guarded` with `gnss_bias` recovered 6 of 30 runs at 5,7 to 12,6 m. In those runs R5 was 4,18 to 9,92 m, which is 0,73 to 0,97 times the magnitude. That supports the Q2 caveat and also bears on S3 at 13,5 m. Fix: cite it in Q2 and in the S3 caveat.
- `study-summary.md:11`, `reviewer-questions.md:49` - MINOR - the sensor noise is called "truncada". In `prng.rs:58-71` the clamp equals the natural support of the four-uniform sum, so it never binds. Fix: say "limitada (suporte finito)".
- `reviewer-questions.md:188` - MINOR - the cite `1165-1172` covers only the end of the classification. Fix: cite 1159-1172.
- `study-summary.md:46-48` - MINOR - says the horizontal channel is not corrected by rule 1. That is true for position. But `landing_controller.rs:254` computes the time-to-go from `h_base`, which rule 1 changes. Q6 asks about other differences between G0 and `robust` and could name this path. Fix: add it to Q6.

No violation of the style rules. I found no U+2014 (or U+2013), personal names, emails or absolute paths in the six files. Nothing is described as approved, frozen, confirmed or human-reviewed. The package says the opposite in `README.md:11-13`, `study-summary.md:3` and `:150`.

## Recomputed

- **Hashes.** 41 of 41 blob hashes in `source-commitments.md` match `git cat-file blob 4777160:<path> | sha256sum`. This includes the protocol (also git id `cb6b792d…`), the claim, the case, the 8 families, `sources.json`, `prediction.json`, the model, `test.json`, `seeds.rs`, `investigate.rs`, the context documents and the 20 per-file crate hashes. The `case_sha256` values in `sources.json` match the family blobs, and `prediction.json` matches the base case.
- **`vv-rocket` `source_sha256`.** It is computed in `crates/vv-rocket/src/lib.rs:25-62`: 20 files, name, NUL, content with CRLF turned to LF, NUL. My recomputation gives `12b276cb…` at `3962482`, `1195c1b` and `8be03e4`. It gives `a7d43d25…` at `3baa1c1` and `295a45b2…` at `04de572`, `bec7b3f` and `4777160`. The stale-hash claim holds.
- **Code change since `3962482`.** Only `landing_model.rs` changed in the hashed set, +152 and -3. The `v1` path still calls `check_registered`, and only the schema check in `prepare_unpinned` was widened.
- **Arithmetic.** I recomputed these exactly and they match:
  - Totals: 920 seeds, 5 800 runs, contiguous stage ranges, no overlap with the spent or protected ranges.
  - Thresholds: 154, 155, 228, 79 and 80.
  - Powers: 0,3071, 0,7934, 0,9988, M2 0,8092 and S7 0,4475.
  - Minimum n: 51, 55, 63 and 69. The "63" error in protocol l. 115 is real.
  - S4/S5: the McNemar minimum of 11 discordant pairs, 4,86×10⁻¹¹, and the 54/60 table.
  - Clopper-Pearson: bounds, the 0/13/1 event budgets, and 35/1024 giving 4,98 %.
  - Order-statistic positions 20/41 and 19/42.
- **Model and H3.** I ran the appendix program as written, with no simulator, from the repository root. It reproduced b* = 11,98868, the 3,996, 7,992 and 11,989 thresholds, onset invariance, the peaks and first-rejection times, P2, and the oscillating -5,087. It also gave the H3 exact probabilities 1,0 / 0,6692 / 1,0.
- **Facts against source and evidence.**
  - Case parameters, bias in x and z, 5-cycle GNSS period, protected-seed lists and the 8-family order.
  - `test.json` counts and b50 = 11,889, commit times and ancestry, and the 3-added/2-removed diff of the model script.
  - The `m13`, `m9`, `m14` citations other than `limitations.md:37`, the protocol line citations used by the questions, and the Halton and `to_q` locations.

## Not checked

- Simulator-dependent figures: 30/30, 20/20, the 35 and 6 compromises, b50 as an outcome.
- Whether `v1` outputs are bit-identical across code versions. I only read the diff.
- The 20 000-draw resampling in the protocol, which the package replaces with an exact calculation.
- Halton and quantisation behaviour, seed independence of SplitMix, and time to contact on dispersed seeds.
- Which pairs carry the 35 tradeoffs; `investigation.json` does not say.
- A compiled `source_sha256`.

Files are in `<worktree:m19>/docs/review/g3-onset/`. The protocol is `<worktree:m19>/docs/m15-g3-onset-protocol.md`.
