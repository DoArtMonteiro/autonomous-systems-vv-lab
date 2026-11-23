# Adversarial review of M10 no-go result

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: STANDS WITH CORRECTIONS

The verdict (V1 fail on S1, S2 and S5; V2 fail as predicted; global no-go) reproduces from the committed records. I found no change made after seeing results, and nothing outside 5000-5099. The corrections below are to the report text and to missing documentation, not to the result.

**What I recomputed from `docs/evidence/m10-redesign/results/records.jsonl.gz`**
- **Clause 1:** B+G has 6 horizontal-velocity alert failures (4 in G1, 2 in G1 with 1.5x noise), all with `iso == wrong`. B has 0. B+ has 60 + 5 + 1.
- **Clause 3:** B+G has 26 wrong isolations in 2400 (M3) and 23 in 640 (G1 with noise). B+ has 46 and 71. B has 0.
- **S2:** B+G 33 vs B+ 110 at 0.3 and 0.5 m/s, so a 70% reduction against the 90% required. The 60-run validity premise holds.
- **U at 0.5 m/s:** B+ 544 (473 with no isolation, 71 wrong), B+G 47 (41 and 6), B 54. The 80-run units are 67 / 1 / 0.
- **S6, S7:** correct isolations 281 vs 282. Per-cell B+G against B+, `robust` and `guarded` matches the V2 claim: only `gnss_bias`, `pair_gnss_bias+altimeter_dropout` and `pair_altimeter_bias+gnss_dropout` regress.
- **Gate streaks:** 820 of 2560 open at touchdown in G1, 349 of 640 with noise, 5 of 1900 in M4.

**Question 1: ordering and amendments**
- The commit order is sound. Pre-registration 41a91c5/e4944e1, diagnostic d350177, adenda 1 (26ff91d, 19:02:10), flag code 91c9981 (19:04:51), adenda 2 (1ce8d60, 19:06:02), simulator change 6419587 (19:06:45).
- The binary (19:06:33) postdates all Rust sources. The `Rust` files have no later diff.
- The first gate-on run is the stage-1 B+G probe at about 19:08:46. Stage 0 ran gate-off at 19:07:51.
- Adenda 1's threshold changes (S6b, S6c, clause 2 proportional limit, no exclusion of M3) are stricter, were made after gate-off diagnostics only, and came before any gate-on run.
- The `gate` field edit in `scripts/m10_campaign.py` is a pure addition and cannot change classification. The analysis script found 0 differences in 4800 re-runs, but only on class, isolation and hv.
- Adenda 2 changes the simulator only when schema is v2 and all four sigmas are exactly 1.5x. Registered values and every other case are still pinned. Gate off is a no-op in the diff (`gate_active` is false, streak fields are `None` and not serialised).
- Stage 0 reproduces exactly in `runs/m10-run/stage0-*/records.json`: B+ 41/32/27, 57/29/14, 91/3/6 and so on, and B 20/69/11 and so on. Stage 0 and stage 2 agree seed by seed (0 differences in 1400).

**Questions 3 and 4: binary, seeds, run cap**
- One binary, `918479ef…`, across all summaries. All seeds are 5000-5099 and there is no `m10-freeze.json`. The `--seeds` arguments in `stages.log` are only 5000-5099, 5020-5039 and 5020-5059.
- The overrun is a budget deviation. The 4800 re-runs were all B+G, were not outcome-selected, and reproduce the originals. The discarded stage-0 runs were gate-off.

**Findings**
1. `docs/m10-redesign-results.md:61` - MINOR - It says `m10_campaign.py` was edited "after stage 2 started". The file mtime is 19:13:16, after stage 5 ended (19:12:21) and just before stage 2g. - State "after stages 1 to 5".
2. `docs/m10-redesign-results.md:85` - MINOR - "About 58 runs per second" contradicts `runs/m10-run/stages.log`: 2560 runs in 16.2 s and 1000 in 4.6 s, about 160 to 215 per second. `AGENTS.md` requires measured performance claims. - Replace it with the logged figures.
3. `docs/m10-redesign-results.md:62` - MINOR - The two discarded stage-0 runs (2800 runs, old binary `8b6a259c…` and an explicit-flag model) are given no reason and no outcome, so a reader cannot rule out selective discarding. - Say why they were discarded and that they were gate-off.
4. `docs/m10-redesign-results.md:31`, results files - MINOR - The pre-registration (section 4) requires recording the commit and `source_sha256`. Only the binary hash is recorded, and there is no statement that fmt, clippy, `cargo test` or the Python tests passed. - Add the commit hash 6419587 and the check results.
5. `docs/m10-redesign-preregistration.md:3` - MINOR - The status line still says "no experiment was run and there are no code changes". - Add a pointer to the results document.
6. `docs/m10-redesign-results.md:31` - MINOR - The 0 differences in the re-run check cover class, isolation and hv only. - Say so, or extend the comparison to invariants.
7. `docs/m10-redesign-results.md:26` - MINOR (no change to the verdict) - S3 and S4 are "yes", but at 0.3 m/s the clause is vacuous and B+G keeps 27 wrong isolations in 640. - Add this to section 3.

**Question 5: wording**
It is honest. The text says H.2 is "compatible, not proven", with no ablation, development seeds only, and no generalisation. Section 7 lists what remains untested. The mechanism behind the 1.5x-noise wrong isolations is explicitly not analysed. In the noise runs B+G still has 2 wrong isolations per cell, including nominal, so the problem is outside the gate's reach. The report notes the estimator does not model the 1.5x noise.

**Question 6: language**
There is no U+2014 and no personal paths in the four docs or in `records.jsonl.gz`. I saw no pre-AO1990 spellings.

CHECKED: git log and reflog order, the diffs of 91c9981 and 6419587, file mtimes in `runs/m10-run`, `stages.log`, the stage-0 raw records, the full committed records (all counts above), the analysis script thresholds, the pre-registration sections 5 to 14 and both result documents.

NOT CHECKED: I did not run `cargo` or the Python tests, so the gate-off trace-hash tests and the cargo fmt/clippy/test results are unverified. I did not replay retained traces. The commit timestamps are as recorded in git and the filesystem and cannot be independently authenticated. I did not check the invariant equality of the re-runs or the `gnss_horizontal_bias` invariant ids (5084, 5086, 5093).
