# G3 candidate adversarial review

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

I found no BLOCKER. The code facts, hash pins, evidence counts and exact statistics all reproduce. The weaknesses are in the protocol's gates and wording, not in the arithmetic.

Findings, most severe first:

1. `docs/m19-g3-onset-protocol-candidate.md:391,406` - MAJOR - The executor is told not to import `ROCKET_PROTECTED` and to keep its own list. It would accept 44000-44999 given a `--freeze <commit>` that is only self-consistent (ancestor of HEAD, clean tree, matching hashes). The repo guard says these seeds "need owner approval" (`exec/src/seeds.rs`, `exec/src/investigate.rs`, and both `desktop/domain-*/domain.json`). Nothing in the freeze records that approval, so whoever writes the freeze commit can unlock the seeds. Fix: require the freeze commit or a signed tag to cite the owner's approval, and have the owner change the guard lists in an approved commit rather than keep a private list.

2. `:177` (also `:161`, `:329`) - MAJOR - H1a is titled "mascaramento" in the primary family. Lines 185 and 373 say only the McNemar gate licenses that word. A line such as "H1a, mascaramento: confirmada" would leak it through the Holm result alone. Fix: rename H1a "R1 falha com início tardio" everywhere, and remove "mascaramento" from the hypothesis labels and the power-table header.

3. `:7,437` - MAJOR - "Incorpora as decisões de desenho desta revisão" and "Decisões desta revisão (tomadas)" sit under the heading "Decisão do responsável". This reads as owner decisions. The project memory lists five owner decisions as pending. Fix: write "escolhas de desenho propostas pelo autor do candidato, não decididas pelo responsável", and move the "tomadas" list out of that section.

4. `:11` and `tests/test_m19_g3_power.py:329-334` - MINOR - The text says "nenhuma semente de 44000 a 44999 foi usada". The test instantiates SplitMix64 states for seeds 44000 and 44128, and the script computes stream positions for every seed in that range. No simulation ran, but the claim is overstated to a literal reader. Fix: "nenhuma simulação correu com essas sementes; a aritmética do PRNG e um teste leem os seus estados iniciais".

5. `:382` (rule b) and `:185` - MINOR - A late-onset run in which the bias never acts leaves H1a and H2. At a 20 s onset, contact before the first biased fix would make R1 pass trivially, so that cell may not test masking at all. The 5 % cap covers this, but the McNemar gate is silent on these seeds and on `no_contact` or `evaluated=false` runs. Fix: state their treatment in the gate. Also state that H1a counts `no_contact` as "not failed".

6. `:232,256` - MINOR - b_s is undefined for a seed where R1 never holds up to 14.0 m, or already holds at 10.0 m. Fix: set b_s to 14.25 and 9.75 (or +inf and -inf) so that it is still counted in the median.

7. `:226,390` - MINOR - A new candidate written after seeing the results could reuse the reserve (44920-44999) and the 24 unassigned seeds. That is a forking-path risk. Fix: say that any later use is a new confirmation with its own alpha and counts the first run as seen.

8. `:31-73` - MINOR - The 39-row "Diferenças face ao candidato M15" table, with "revisão 2" and "pergunta N do pacote de revisão", is drafting history, which `AGENTS.md` says not to publish. Fix: keep it as an internal note, or reduce it to a short list of technical differences.

9. `tests/test_m19_g3_power.py:22` - MINOR - The literal U+2014 is in a test constant. The brief allows it only in the doc label. Fix: use `"/u2014"`.

10. `:397-402` - MINOR - The independence check covers 44000-44919 among themselves. It does not cover overlap with the seen ranges (41000-47019 and others). Fix: extend `seed_independence`, or list it as unchecked.

11. `:103` - MINOR - Contact time on dispersed seeds is unmeasured. My bounds assumed uniform dispersion (vz ±10 m/s, z ±50 m) and a nominal 23.5 s contact. These suggest the 20 s onset leaves at least 2 s. It is an inference, not a measurement. Fix: label it as such; the doc already admits the gap.

Scope was clean: only 4 files changed (the doc, the power script, `calculations.json` and its test), and `m15` and `docs/review/g3-onset` are untouched. Language is fine. I found no Portuguese pre-AO spellings (contacto and exceção are valid under AO1990).

What I could not break:

- **0.01 s vs 0.1 s onsets:** `landing_sim.rs:189` has `f.start_step <= step`. The GNSS fix is at `step % 10 == 0` (`:210-211`). Faults feed only `observe`. GNSS and IMU noise is drawn whether or not a bias is present. So 0.01 s and 0.1 s have the same sensor and state history, and 0, 1, 2, 5, 10, 15 and 20 s are distinct. `acted` is computed identically for both. `active_faults` differ only in event metadata.
- **Fault ranges:** `validate_faults` accepts every planned start and magnitude. The `gnss_bias` range is 5-30 and there is no window constraint.
- **`source_sha256`:** I recomputed it over the git blobs. It gives `295a45b2...` at HEAD, 4777160 and bec7b3f, and `12b276cb...` at 3962482. Only `landing_model.rs` differs (+152/-3), and `run.json` embeds the hash.
- **Pinned blobs:** all 10 pinned blob hashes in the doc match, as do the script and `calculations.json` hashes.
- **Evidence counts:** "0.93 not recorded" holds: the only 0.93 matches are the hypothetical in the review package and the unrelated 0.9334 magnitude in `investigation.json`. 294/294 matches the fragility rows (180) plus M9.1 (30), M13 (64) and the masking test (20). The commit times 17:07 to 17:43 and 20:20 to 20:25 match git.
- **Exact statistics:** I recomputed all binomial thresholds (162/161/135/136, S3 136, S7 77, M1 220, M2 76) and the Clopper-Pearson bounds (0.98 %, 4.82 %, 2.14 %, 459 pairs). The McNemar minima of 7 and 10 pairs also match. The (20,41), (21,40) and (19,42) intervals have per-side error within the stated alpha.
- **Seed maps:** I confirmed the stage ranges and the 5704 runs.
- **Independence:** an independent integer-arithmetic check found no overlap of used outputs (minimum gap 2) for 44000-44919 and for 44000-44999, at the 40 s usage and at the code limit.
- **Seed protection:** the script runs only `git` via subprocess. Nothing in the diff invokes, dry-runs or reclassifies 44000-44999, 3000-3099, 6000-6099 or 50000-59999.
- **Label and status:** the top label and "Estado" say not frozen, not executed, not approved and not human-reviewed. Only finding 3 implies otherwise.
- **Tests:** the 35 unit tests in `tests/test_m19_g3_power.py` pass, and `--check` prints "identical". The working tree stayed clean.

CHECKED: the full candidate doc, `landing_sim.rs`, `landing_sensors.rs`, `landing_verify.rs` (acted and cause), `landing_model.rs` (fault validation and the v2 diff), `prng.rs`, `lib.rs`, `exec/src/seeds.rs`, `exec/src/investigate.rs`, the M13 claim and case, the M14 `test.json`, `fragility.json` and `calculations.json`, `scripts/m19_g3_power.py`, its test, the branch diff and git timestamps.

NOT CHECKED: any simulator behaviour (contact time per seed, R1 outcomes), the 0.01 s vs 0.1 s equivalence by execution, the Monte Carlo cross-check for H3, the Fréchet bounds and power tables beyond those the tests cover, the `docs/review/g3-onset/` contents, and the rest of the M15 text kept by reference.
