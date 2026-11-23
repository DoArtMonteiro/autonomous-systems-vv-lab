# G3 candidate methodological review

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

The statistics hold up. I found no error in the thresholds, bounds, power numbers, seed map or independence analysis, and no way for the analyst to choose after seeing data. The findings below are wording and specification gaps, plus one design question for the owner.

Both required commands pass. `python -m unittest tests.test_m19_g3_power` ran 35 tests, OK. `python scripts/m19_g3_power.py --check ...calculations.json` printed "identical". `docs/review/g3-onset/` has an empty diff against 4777160. The sha256 of the script and `calculations.json` at HEAD match lines 13 and 14 of the candidate.

I recomputed the following independently with exact fractions, without the project script:
- **Binomial thresholds.** At the stated levels: H1a 162/161/161 of 168, H2 136/135 of 140, S3 and S6 136 of 140 at 0,01/7, M1 220 of 231, M2 76 of 77, S7 77 of 77.
- **Minimum sizes.** 44, 51, 55, 63 and 69 seeds for n successes in n.
- **McNemar minimum discordant pairs.** 7, 10 and 11.
- **Order-statistic positions.** (20;41), (21;40) and (19;42) are exactly the (1−2α) TOST intervals. The "−0,25" lower shift is conservative.
- **Clopper-Pearson, 99%.** The upper limits are 0,979% for 0 of 468, 1,04% for 0 of 440, 4,82% for 12 of 468, 2,14% for 1 of 308 and 2,70% for 2 of 308. The minimum is 459 pairs. The lower limits are 0,774, 0,842 and 0,926.
- **Power.** The H1a, H2, S7, M1 and M2 rows match, as do the option-0, option-1, option-5 and option-6 H1 figures. The moderate Holm joint is 0,7549. If all three nulls sit at their boundaries, P(any rejection) is 0,0061, under 0,01.
- **Seed map.** I enumerated the stated formulas. There are 896 distinct seeds, with cells of 6, 5 and 11, ranges exactly as stated, and no overlap. Executions total 5704.
- **SplitMix64 overlap.** There are no overlaps in the used outputs, for 44000–44919 or 44000–44999, at the 40 s case or the code limit. The uniform-bound count is 3180, as stated. The minimum slack is 1 draw, so the margin is very thin.

**Family-wise error.** Holm over {H1a, H2, H3} with the McNemar gate and then H1b in fixed sequence controls the error at 0,01 for the joint "confirmed" sentence and for each gated word. Classes at 0,01/3, 0,01/2 and 0,01 are nested, so they are valid step-down p-values. The secondary and mitigation families are controlled within each family, and the 0,03 cross-family bound is disclosed.

Findings, most severe first:

1. `docs/m19-g3-onset-protocol-candidate.md:185,373` - MAJOR - The McNemar gate, a paired comparison of R1 outcomes, licenses the word "mascaramento". Masking is a mechanism claim. The mechanism evidence (S4, S5, S6) sits in the secondary family and is not a gate. The title sentence at line 372 also demands "o perfil de R5", which is S3 (secondary), without S3 being a condition. Fix: say "R1 pior do que a 0 s" for the McNemar gate and reserve "mascaramento" for when S4, S5 and S6 pass. Alternatively make S3 to S6 gates. Either way, state whether the R5 phrase depends on S3.

2. `docs/m19-g3-onset-protocol-candidate.md:278,437` - MAJOR - H2 is the binding test: power 0,589 at π = 0,97 and MDE 0,978. The joint power is 0,575 in the pessimistic scenario and 0,227 for "G3 replicado". The design leaves 24 seeds unassigned and rejects the custom alternative (E at 19 points, A_high at 168), which raises H2 to 0,758. Line 437 records this as "decisão tomada", although the owner has approved nothing. Fix: move the allocation choice to "Por decidir", or justify rejecting a gain of about 0,17 in H2 power.

3. `docs/m19-g3-onset-protocol-candidate.md:195,185` - MINOR - S4 and S5 require "todos os pares no sentido previsto", but the power code (`sign_threshold`) is an exact sign test that tolerates contrary pairs. The gate says "ou o equivalente exato". Fix: use one rule everywhere, an exact one-sided sign test with a floor of 10 (or 7) discordant pairs, and recompute S4/S5 power under it.

4. `docs/m19-g3-onset-protocol-candidate.md:382` - MINOR - The `acted = false` rule covers only the numerator and denominator of H1a and H2. It says nothing about the McNemar gate, H1b, S3, S6 or the mitigation pairs. A run where the bias acts for one or two measurements still counts as an H2 "recovery", although R1 passes trivially. Fix: apply the exclusion to the whole seed pair in every A-derived test, and set a minimum exposure, for example at least N biased fixes before contact.

5. `docs/m19-g3-onset-protocol-candidate.md:186,374` - MINOR - H1b tests the 0 s arm only in the low band, 5 to 10,5 m. The registered G3 range is 5 to 30 m. "G3 replicado" overclaims. Fix: pool the 0 s arms of both bands (n = 308), or word it as "replicado em 5 a 10,5 m".

6. `docs/m19-g3-onset-protocol-candidate.md:232` - MINOR - The candidate drops the M15 convention "b_s = +∞ se não existir" (M15 line 104). It does not say how seeds that pass at every level, or never pass, enter the order statistics. Fix: restate the convention, with +∞ above 14,0 and 10,0 at or below the lowest level.

7. `docs/m19-g3-onset-protocol-candidate.md:238,351` - MINOR - The pooled binomial and Clopper-Pearson tests are applied to heterogeneous cells, and to Halton points in E. Validity rests on Hoeffding's comparison, which holds for thresholds above the mean plus 1, and on treating the Halton design as random sampling. Neither is stated. Fix: add one sentence to "Ameaças à validade".

8. `docs/m19-g3-onset-protocol-candidate.md:1` - MINOR - The mandated label contains U+2014, which `AGENTS.md` forbids. Fix: record the exception explicitly, since the test only whitelists it.

NOT CHECKED:
- Any simulator, cargo or protected-seed run, as instructed.
- The `source_sha256` recomputation and the other base-file hashes in the table, beyond the passing tests.
- The reconstruction of the b_s distribution from `test.json`, and the Monte Carlo cross-check of H3.
- The Fréchet bounds, the McNemar gate power, and the fallback budgets for E at 19 points.
- The `acted` and onset-geometry claims in the Rust code, and the count of draws used per stream. I took those from the document.
- Whether the actual 40 s case uses exactly the stated number of draws.
