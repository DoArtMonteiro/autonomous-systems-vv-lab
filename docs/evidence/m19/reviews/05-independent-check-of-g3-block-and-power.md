# Independent check of G3 block and power

Agent role: `sonnet-critical-reviewer`. Agent-based review, not human review. Final report, paths anonymised.

VERDICT: ACCEPT WITH FIXES

No blocker. I reproduced the seed map, the overlap results and the power numbers. The remaining problems are one stale record, one contradiction, and caveats that need stating.

**Findings, most severe first**

1. `scripts/m19_g3_power.py:1658` (`RNG_OPERATIONS_DISCLOSED`, revision "5") - MINOR - The committed, hash-pinned JSON disclosure is stale against the document table. The JSON says "81000-81999, 80920-80999" and "synthetic block 90000-91999". The document says 80904-80983, and the code uses 90000-99999. Both are position arithmetic only, so there is no safety impact. But a disclosure record that disagrees with itself weakens the disclosure. Fix: align the entry, regenerate `calculations.json`, and update the two pinned hashes in the document (lines 13 and 14).

2. `docs/m19-g3-onset-protocol-candidate.md:521` vs `:525` - MINOR - Line 521 says "não pede aprovação de execução". Line 525 asks the owner to approve or reject, and that approval authorises use of the seeds. Fix: say that approval is requested only after human review, and that none is requested now.

3. Document lines 432-438 (draw bounds) - MINOR - The rocket bounds are correct and conservative. The "declared ranges" are not all SplitMix streams, and the document does not say so.
   - The ground-vehicle seeds (M6 finals, 100-129, 201-212, 42/1337/2026) use `XorShift64Star` in `src/prng.rs`. The rocket stream analysis is vacuous for them, which is conservative.
   - `vv-ascent` uses the same stream scheme with 8 draws per observation up to `MAX_TICKS`. Its sources 9 and 10 can exceed the rocket bound for source 9 (240 000).
   - I stress-tested with 4 000 000 draws on every stream. The block-to-declared minimum distance is 8.7e12 and the within-block slack is 5.1e13, so nothing overlaps. Under that stress the partner set grows to 59 961 seeds. Against the inventory at `4777160` it still gives 0 hits. The only hits at `HEAD` are the synthetic 90000 and 91999, which appear in the docs.
   - Fix: state both caveats and the stress result.

4. Document lines 245-256 and 358 - MINOR - The H3, S1 and S2 power uses the empirical `b_s` distribution of 20 seeds as exact, and that distribution comes from a `test.json` I did not reconstruct. So "1,000" and "0,999999" are artefacts of that choice. Only S1 is labelled illustrative. Also:
   - The per-seed posterior treats the 54 seeds as exchangeable draws at the grid rate. By the document's own table the q evidence is at 10 m or less, but the grid includes 10.5 m. I did not open `investigation.json`.
   - Line 289 lists the scenario (1,00; 1,00), but no table column shows it.
   - Fix: label the H3, S1 and S2 power table as illustrative. Add "evidence transported to untested conditions" to the assumptions. Drop or show the (1,00; 1,00) scenario.

5. Document line 421 - MINOR - The reserve start 80904 is not justified. Reserve windows free of overlap against the block and the declared ranges start at 80895-80907. 80904 is the highest multiple of 8 in that range, but the document does not say so. Seeds 80984-80999 are not mentioned. Fix: state the rule, and state that those seeds are outside the protocol.

6. `exec/src/seeds.rs` - MINOR - The guard does not yet protect 81000-81999 or the reserve. They are protected only by prose (line 423), and the document defers this as decision (2). Suggest doing the "protect first" commit before anything else.

**Item 2, overlap method:** the derivation of the stream-start and position relation, and the interval-overlap condition, are correct. The scan logic is also correct. The inventory method is a declared majorant with declared gaps. Per-source draw counts match the code: sources 1-3 use 3, 3 and 2 (3 is a conservative bound); sources 4-6 use 1; the altimeter 4 per control cycle; GNSS 12 per fix; IMU 12 per cycle. The registered case pins control period 2 and GNSS period 5, so the 200 000-step limit is a valid bound.

**Item 3, power:** nothing still implies p=1. The "nenhuma taxa é 1" text, the grid and the posterior averages are explicit and labelled illustrative. Per-run rows are flagged optimistic.

**Item 4, disclosure:** the disclosure is precise and matches git history. The generating tests are in `dc1f18c` and `031edb9`. Word counts match the code: 6+2 per run, 3+1 and 7+5 as stated. Printed words (8) are separated from stored words (none). The "12 interactive" figure and the console-only printing cannot be checked. The implication assessment is sound: no simulation, no outcome and no outcome-based selection, and the exposed seeds 44000, 44128 and 44804 stay out of the confirmatory set.

**Item 5:** the label, the Estado section and the freeze language are consistent, apart from finding 2. Human review is pending.

**Independently reproduced**

- **Seed map.** I enumerated it from the formulas: 916 seeds, each with exactly one condition. Stage ranges are contiguous and disjoint: A_low 81000-81167, A_high 81168-81335, B 81336-81395, C 81396-81455, D 81456-81763, E 81764-81915. Unassigned are 81916-81919. Cells have 6/6/11 seeds, and the runs total 5736. There is no overlap with the reserve, 44000-44999, 3000-3099, 6000-6099 or 50000-59999.
- **Within-block overlap.** None. The minimum slack is 51 441 355 995 046 at the code limit and 51 441 357 171 046 for the 40 s case, which matches the JSON. Block plus reserve is also clear.
- **Declared ranges.** There are 16 439 seeds, matching the document and the guard lists. The minimum position distance to block plus reserve is 8.7e12, so no overlap.
- **Exhaustive scan.** My own numpy scan over 0..2^24 with the code-limit bounds gives 25 160 partner seeds in 237 ranges, exactly the JSON's numbers. Source-0 partners: none.
- **Scan validation.** Output words generated only for seeds ≥ 90000, on a synthetic 90000-90999 target: all 10 720 synthetic partners share a word, and 364 sampled non-partners share none.
- **Inventory.** My independent regex over all local refs (a wider context window than the script's) gives 0 hits against the partner set.
- **Rejected blocks.** 81920-81999 has 405 self-overlaps. 80920-80999 overlaps 83017.
- **Thresholds and powers** (exact binomials):

| Test | Alpha | Threshold | Powers at 0.95 / 0.97 / 0.99 |
|---|---|---|---|
| H1a, H2 | 0.01/3 | 162 of 168 | 0.260 / 0.758 / 0.998 |
| H1a, H2 | 0.01/2 and 0.01 | 161 of 168 | not computed |
| S3, S6 | 0.01/7 | 163 of 168 | 0.150 / 0.609 / 0.993 |
| H1b | 0.01 | 316 of 336 | 0.825 / 0.999 / 1.000 |

  I also reproduced M1 220/231, M2 76/77 and S7 77/77, and the pooled thresholds 375/399 and 233/245. The MDEs of 0.972, 0.949 and 0.977 match. The option 0 and option 1 power rows match.
- **Holm joint power**, with H3 taken as certain: 0.0085, 0.155, 0.749 and 0.9994 at p = 0.93, 0.95, 0.97 and 0.99. These match the document's 0.009, 0.155, 0.749 and 0.999.
- **Posterior-averaged power.** Per seed (Jeffreys 54/54) it is 0.9304. With per-run counts it is about 1. A shared-rate posterior gives 0.947, higher than the independent-posterior 0.930.
- **Clopper-Pearson lower bounds.** 84/84 gives 0.9467, 54/54 gives 0.9183 and 294/294 gives 0.9845.
- **Budgets.** 0/460 gives 0.996 % and 12/460 gives 4.903 %. 1/308 gives 2.136 % and 2/308 gives 2.70 %. 0/458 is just above 1 %, so 459 is the minimum.
- **Sign test and minimum n.** S4/S5 power at 0.5 is 0.99996. 54/60 at true rate 0.85 is accepted with probability 0.185. The minimum discordant count is 10. The minimum n for n-in-n successes is 44, 51, 55, 63 and 69.
- **Test and check commands.** `python -m unittest tests.test_m19_g3_power` ran 51 tests, OK. The `--check` command printed "identical", rc 0. The two pinned sha256 values (script and JSON) match the committed blobs.
- **Hex and decimal scan.** No long hex or decimal output-word tokens in the four files or in the added lines of `4777160..HEAD`. The only 16-hex tokens are the public SplitMix constants and the state-0 reference vector.

**NOT CHECKED**

- H3, S1 and S2 power: it needs `test.json`, and the Monte Carlo cross-check was not rerun.
- The "mascaramento" Fréchet bounds.
- The Hoeffding condition beyond a hand check of each threshold.
- The evidence-count provenance (distinct seeds 84 and 54).
- Seeds in untracked files, in `runs/`, in PR text, and in other worktrees' untracked files.
- The inventory range logic, beyond the zero overlap result.
- The v2 exploratory path.
