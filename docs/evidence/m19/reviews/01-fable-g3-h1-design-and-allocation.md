# Fable: G3 H1 design and allocation

Agent role: `fable-strategic-advisor`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

**Decision.** Which H1 design, alpha structure and seed allocation go into the corrected candidate. If it goes wrong, the single run on 44000-44919 either ends inconclusive on a true effect, or licenses the word "mascaramento" on a test that never compared 0 s with late onset.

## Framing challenges

- **Option 4 and "masking".** The joint sentence (candidate line 353) asserts only late-onset behaviour. The contrast lives in the label "mascaramento" (line 167) and the headline. H1a alone would also reject if R1 failed at 0 s too. The missing test is therefore the paired contrast, not H1b's absolute level.
- **H1b is not the novel claim.** Per question 25, the registered G3 only guarantees 27 of 30 at 0 s. Demanding an inferential π > 0.9 is stricter than G3 itself.
- **"Is 0.59 adequate" is not a standards question.** Low power risks an inconclusive run, not a false claim. The moderate scenario's 0.97 for H2 has as little recorded basis as 0.93 did (1160/1160, per-seed bound 0.918). Development-like joint power is 0.985.
- **Bonferroni versus intersection-union is a false binary.** Holm step-down is a third option.

## H1 options

| Option | Benefit | Cost | Risk |
|---|---|---|---|
| 1, both required | Literal conjunction | Power 0.260 at p0 = 0.95 | Novel finding sunk by a registered property |
| 4 alone | Power 0.998, independent of p0 | "Masking" has no test behind it | Wording outruns evidence |
| 4 plus gated paired contrast and gated H1b | Each word has its test; contrast power 1.000 in every tabulated scenario | More decision rules | Alpha spent twice if gating is mixed |
| 6, pool A and D | Joint power 0.935 | Couples masking and mitigation verdicts; changes grid weights | Shared noise across families |

## Recommendations

1. **H1: option 4 plus serial gatekeeping.** Only after H1a, H2 and H3 all reject, test the exact paired McNemar, then H1b, in fixed order.
   - The McNemar licenses "mascaramento" and the contrast wording; without it the headline says "falha com início tardio".
   - H1b licenses "G3 replicado". Also report G3's own point rule descriptively.
   - Option 6 only as a descriptive pooled estimate.

2. **Alpha: Holm step-down over {H1a, H2, H3} at family 0.01.**
   - Individual verdicts keep family error 0.01, which 0.01 per test does not.
   - The all-reject region lies between the two listed rules, so joint power is bounded by 0.588 to 0.755 (moderate) and 0.394 to 0.575 (pessimistic). Exact values are to compute.
   - The gated add-ons run at 0.01 in sequence, so 0.01/4 is unnecessary.
   - Never combine Holm with a separate 0.01/3 chain.
   - **No reallocation.** Keep A_high 140, E at 20 points and the 24 seeds unassigned. E at 19 leaves 460 pairs against a minimum of 459, the R2 to R6 limit is uncomputed there, and H2's tolerance would rise to 6, a whole cell.

3. **S4/S5: neither enlarge nor accept the relabel as written.** Keep 60 seeds.
   - "Sem inferência" is too blunt: direction is inferable at n = 60 (exact paired test at 0.01/7, 10 discordant pairs). Only the 0.9 level is not.
   - Verdict wording: "direção confirmada; nível 0,9 descritivo, com limite de Clopper-Pearson".
   - Enlarging to 63-84 buys a zero-failure-tolerance test (line 177), which is significance in name only.

4. **Onsets: keep 7.** An eighth returns to the M15 layout (920 seeds, 5 repetitions) and removes all slack. Neither 0.2 s nor 3 s has a hypothesis attached, both would be chosen after seeing data, and the removed onset was a duplicate.

5. **Flaws.**
   - **Estimand versus wording (question 9, untreated).** The tests are valid for the grid average even with unequal cell rates (Hoeffding 1956, my judgement). The sentence is universal, though, and H1a tolerates one whole cell. Add a pre-stated rule: any cell with a majority of contrary seeds is named and removes "qualquer início".
   - **Onset 20 s.** Time to contact is unmeasured on dispersed seeds (line 93). A run touching down before onset passes H2 vacuously. Pre-state how such runs are counted.
   - **Seed independence (question 15) is assumed.** All streams share one SplitMix64 cycle (`prng.rs`: state `seed ^ source*G`, increment `G`), so overlap is decidable by integer enumeration. This computes on the values 44000-44919 without running them; the owner decides whether line 11 still reads true.
   - **H3.** The only genuine prediction confirms with probability 1.000 for shifts up to 0.5 m. Say so in the verdict; S2 carries the discrimination.
   - **Power figures only.** The 20-seed b_s reconstruction and the Fréchet bounds affect power, not validity. Label them illustrative.
   - **Gates.** State that an invalid stage closes downstream gates.

## What would change my mind

- The owner wants "holds at 0 s" asserted with equal standing: then option 1, and accept its power.
- Holm shows no material gain once computed: then Bonferroni with a 0.01/3 fixed-sequence chain inside the H1 slot.
- The enumeration finds stream overlap: then fix seeding before anything else.

## Cheapest next step

Extend `<worktree:g3c>/scripts/m19_g3_power.py`, with no simulator run, to compute:

- Holm joint power for the four scenarios, with thresholds and H3 positions at 0.01/2 and 0.01;
- a whole-cell-failure table;
- the 460-pair budgets, as the costed fallback;
- the stream-overlap enumeration, pending the owner's view.

Files read: `<worktree:g3c>/docs/m19-g3-onset-protocol-candidate.md`, `<worktree:g3c>/scripts/m19_g3_power.py`, `<worktree:g3c>/docs/review/g3-onset/reviewer-questions.md`, `<worktree:g3c>/crates/vv-rocket/src/prng.rs`.

CONFIDENCE: medium. The gatekeeping and multiplicity logic is standard and grounded in the candidate's own tables, but Holm power, the 0.01-level thresholds and stream overlap are uncomputed (I have no execution tool), and this is not human review.
