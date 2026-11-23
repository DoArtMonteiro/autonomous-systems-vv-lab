# Second re-review of M19 doc packages

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

The G3 package and the usability kit hold up against the source. The strategy file records the decisions but still contradicts them in several places.

**Strategy (`docs/m19-programme-strategy.md`)**

- **Line 142 - MAJOR.** The Three.js decision drops the owner's condition. The owner said to use Three.js only if it offers meaningful advantages, and not to assume it beats SVG, Canvas or Godot. The text says only "investigada como protótipo em Three.js". Fix: quote the condition and add that SVG, Canvas and Godot are compared. Define "vantagem material" before the first iteration.
- **Line 66 - MAJOR.** The options table still recommends "Linguagem instrumental em Three.js ... Sim, com portão", with "um só renderizador" as the cost. That presumes Three.js is the answer. Rename the row to "Linguagem instrumental (renderizador a decidir)" and add SVG and Canvas rows, or mark the recommendation as superseded by line 142.
- **Line 74 - MAJOR.** "Nenhuma dependência nova" contradicts a Three.js prototype. I did not find Three.js in the Studio `package.json` files I looked at, so it would be new. Fix: state that the prototype is isolated and its dependency is allowed only for the prototype. State that adoption needs an explicit owner decision.
- **Lines 35 and 33 - MAJOR.** The priorities table is stale. Row 4 (belief vs truth) still depends on "Percurso da investigação", while line 144 makes that view M19.2 and the journey M19.3, deferred. Row 2 and the line 72 refutation criterion still assume a pilot. Fix: remove the dependency on row 3, and drop "Piloto" from the row 2 dependency.
- **Lines 49-50 - MINOR.** M19.3 is listed before M19.2, and the "(antes M19.x)" notes are awkward. The M19.2 gate "Teste cego de compreensão" cannot be met without humans. Fix: swap the order, and replace the gate with "duas iterações, depois adotar, rever mais tarde ou rejeitar". Keep the human test as an open condition for adoption.
- **Lines 78, 89-95 - MAJOR.** The M10 decision requires one dev-seed redesign with predefined success and stop criteria. Only a stop rule is written (line 95), and its heading says "fixada antes". There is no success criterion, such as "melhora materialmente X sem regressões Y". The plan still has three steps, where steps 1-2 are probes and diagnostics, not the single redesign. Line 78 still says "até o responsável decidir". Fix: add explicit success criteria and the "não avançar" outcome. Restate that exactly one redesign is allowed, and that the step 1-2 probes are bounded diagnostics.
- **Lines 52, 37, 128 - MINOR.** These still read as pending: "Decisão do responsável" on R10, "Decisão do responsável" on priority 6, and "Adotada, à espera da decisão do responsável". Line 124 also says "Sequência: Evidência humana ... Adotada" although human evidence is unavailable. Fix: update each to reflect the 2026-11-23 outcome.
- **Positives.** Decisions 1, 2, 3, 6, 7 and 8 are recorded accurately. The point that missing reviewers does not lower the standards is present (line 144).

**G3 package (`docs/review/g3-onset/`)**

I checked these against source at `bec7b3f` and all hold.
- `landing_model.rs` lines 414-416 close `altimeter_velocity_gain`.
- Lines 417-422 are the altimeter-threshold `within(` call, with limits on lines 420 and 421.
- `ascent_abort_vz_mps` moved 415 to 424 in `3baa1c1`, then to 427 in `04de572`.
- The 5 m altimeter-bias minimum moved 238 to 247 to 250 across the same two commits.
- `m9-powered-landing.md:627` matches the quoted figures (6 of 30; R5 from 4,18 to 9,92 m; 0,73 to 0,97 times).
- The `prng.rs` clamp cannot bind: the Irwin-Hall sum minus 2 is at most ±2, so the bound is the support itself.
- `landing_controller.rs` lines 219, 254 and 269 use `h_base` as stated.
- `investigate.rs` lines 1159-1172 match the description of how commitments are counted.
- No pinned hash list includes package files. The hashes cover repository files at `bec7b3f`, and this diff touches none of them.

Findings:
- **`limitations.md:37` - MINOR.** "O M14 não o afirma" is slightly too strong. `m14-evidence-robustness.md:130` says "O mesmo agente desenhou as estratégias". Fix: say M14 attributes the design to an agent and does not state who the independent reviewers were.
- **`README.md` Estado section (lines 7-13) - MINOR.** It does not say the external human reviewer is currently unavailable, or that the candidate is "não revisto por pessoas e não aprovado para execução". Line 13 says "primeira leitura humana pedida", which reads as imminent. Fix: add one line stating that the reviewer is unavailable as of 2026-11-23.

**Usability kit (`docs/usability/`)**

Consistent. All of these hold across the files:
- The only profile is E, with the counts 3 and 5.
- Session length is 60 to 70 minutes, with the cut at minute 53, an end at minute 64, and a hard stop at 70.
- Tasks sum to 39 minutes (22 for actions, 17 for questions). The moderator headings match the time plan.
- The privacy notice comes before the screener, with a deletion placeholder.
- The withdrawal-of-consent sentence is present.
- Human sessions are deferred until written owner authorisation.
- The T5 card no longer mentions the zone, and Q5c2 sits before Q5d in `tasks.md`, `observation-form.md` and `analysis-template.md`.
- H17 is removed from T5, and H09 is tied to T6 via (ii) and to T8, matching `predictions.md`.
- Nothing is presented as empirical validation.

Findings:
- **`README.md:80-82`, `screener-and-consent.md:102` - MINOR.** The kit allows a moderator who is not in the room (voice channel and screen share), while the consent says "presencialmente com um moderador". Fix: state that participant access is always in person, that any off-site moderator only views the screen and gets no control, and align the consent wording.
- **`tasks.md:157`, `severity-and-measures.md` M3 - MINOR.** Q5c2 adds a question but T5's 2,5 minutes is unchanged, and M3 does not list the exclusion. Fix: cite the exclusion in M3, and let the rehearsal re-measure.

**Rules (D)**

- No U+2014 anywhere.
- No emails or personal paths.
- The only personal names are the SUS citation (Brooke, 1996) in `observation-form.md:298` and the bibliographic SUS reference in `severity-and-measures.md`.
- No AO1990 violations found in a pattern scan.

CHECKED: `git diff 4777160 277df8b`; full strategy and usability README; the T5, T6 and T8 sections of `tasks.md`; the moderator timing table and headings; source lines in `landing_model.rs`, `landing_controller.rs`, `investigate.rs`, `prng.rs`, `m9-powered-landing.md`, `m13-discovery-lab.md` and `m14-evidence-robustness.md`; `git show` of landing_model.rs at `3962482`, `3baa1c1`, `04de572` and `bec7b3f`; grep scans for U+2014, emails, paths, names and AO1990 words. No simulator, test or build run.

NOT CHECKED: the pinned hash values themselves; the full text of `independent-checks.md` and the rest of `reviewer-questions.md` beyond the changed hunks; whether M9 G3 `gnss_bias` started at 0 s; UI labels against the installed Studio; whether the Studio has a Three.js dependency anywhere outside the files I read.
