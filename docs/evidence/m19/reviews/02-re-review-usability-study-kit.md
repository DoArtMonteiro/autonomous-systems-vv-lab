# Re-review usability study kit

Agent role: `sonnet-critical-reviewer`. Agent-based review or consultation, not human review. Final report recorded verbatim, with paths anonymised and backslashes shown as forward slashes.

VERDICT: ACCEPT WITH FIXES

All ten prior findings were applied, except the personal-name part of #10 and the timing discrepancy in #7. No kit-breaking defect remains. The audience and privacy-ordering findings below need action before any recruitment.

## Prior findings

| # | Status | Evidence |
|---|---|---|
| 1 Consent and remote-PC blocker | FIXED | The study runs on a dedicated machine and account: `README.md:72,84`, `moderator-script.md:3`, `screener-and-consent.md:93,145`. Recruitment is blocked by placeholders for controller, processors, transfer basis, moderator and author declaration, and retention (`screener:5,89,121-129,152`; `observation-form.md:355-368`). Age 18+ is covered by S0 and the consent table. |
| 2 T8 reachable | FIXED | The prepared package always exists (`tasks.md:165,207`). T8 starts from Mission Control, a neutral screen. The route is real: `home.js:170`. |
| 3 Quoted unseen labels | FIXED | Q8a (`tasks.md:217`) and Q6b (`:178`) are open questions. The T8 card (`:206`) no longer says "recalculada". No label is quoted to participants. |
| 4 T2 cueing | FIXED | The T2 card (`tasks.md:67`) is neutral. Q2a is open and comes before Q2b (`:79-80`). |
| 5 Q5a key | FIXED | The key is the value read at rehearsal, not an assumed 0.00 mm (`tasks.md:154`). |
| 6 Thresholds | FIXED | Thresholds apply to the whole phase. Profiles are descriptive only (`severity-and-measures.md:111,130`; `analysis-template.md:48`). |
| 7 Timing | PARTLY | The 39-minute arithmetic checks out. The cut limit of minute 53 plus 11 minutes of SUS, closing talk and wrap-up gives 64 minutes. That contradicts the "60 minutos" in the invite and consent (`screener:11,93`) and the "60 a 70" in S1 (`:31`). See finding 3. |
| 8 Confidence per question | FIXED | One rating per † question (`tasks.md:15`, Q5d `:157`, Q7b `:199`). Wording is "certo/a" (`moderator-script.md:84`). |
| 9 T7 diagnosis | FIXED | The card (`tasks.md:185`) no longer names the diagnosis. |
| 10 Misc | PARTLY | Fixed: the Phase 2 rule matches `severity-and-measures.md:64` and `:123`. README:15 and :47 now agree on Phase 2 being altered. CE-T6-3 and CE-T8-2 became non-critical occurrences. S4 and S8 are listed (`README:161`). Not fixed: "Sauro e Lewis" (`severity-and-measures.md:91`) and "Brooke" (`:95`, `observation-form.md:297`) are still personal names. H09 appears on T6 and H17 on T5 in `tasks.md` but not in `predictions.md`. |

## New findings, most severe first

1. `README.md:21,56-68`; `screener-and-consent.md:11,71-73` - MAJOR - The kit targets novices as a co-primary profile (PI1, mix 2N+1E and 3N+2E, invite "Não precisa de ter qualquer conhecimento prévio"). The owner's primary audience is technical engineers and independent technical reviewers. Fix: make E (including V&V auditors and technical reviewers) the primary profile and reduce or drop the N quotas. Rewrite the invite and PI1 accordingly, or label N as a secondary study.

2. `screener-and-consent.md:23-25,51,65` vs `:85-89` - MAJOR - The screener collects personal data (S4 free text, S8 adaptation needs) from candidates before they receive the information sheet. Retention for excluded candidates is not stated. Fix: send the sheet, or a short privacy notice, before the screener. Set a deletion time for the screener data of non-participants.

3. `README.md:123-135`; `screener:11,93` - MINOR - The cut rule allows a 64-minute session, and the T6 and T8 waits of up to 5 minutes each are outside the counts. T1, T2, T6 and T8 are never cut, but the 70-minute hard stop has no rule for what yields. Fix: lower the cut limit to minute 49, or say "60 a 70 minutos" in the invite and consent. Define what is dropped at minute 70 (for example SUS before T8).

4. `README.md:5-11` - MINOR - It does not say that human sessions are deferred. Fix: add a line that recruitment starts only when the owner authorises it and participants are available.

5. `README.md:199`; `screener:35` - MINOR - "Como os participantes lhe acedem" and "forma de acesso à máquina" are ambiguous. Remote access would clash with "nunca usa a sessão remota". Fix: state in-person access to the study machine only, or a remote tool whose endpoint is only the study machine and never the owner's session.

6. `moderator-script.md:35,51,61` vs `:16-20` - MINOR - The section headings (0 to 3, 3 to 5, 5 to 7 min) differ from the plan table (0 to 5, 5 to 8, 8 to 10). Fix: align the headings to the table.

7. `tasks.md:141,157` - MINOR - The T5 card says "zona onde não pode entrar". Q5d then asks "problema de segurança?" as a yes/no. CE-T5-2 is therefore only measured after being prompted. Fix: drop the zone cue from the card. Add an open question before Q5d ("o que mais lhe diz o ecrã sobre este resultado?").

8. `tasks.md:165-168` - MINOR - T6 route (ii) opens the prepared package. That satisfies "obtém um veredicto" without any challenge, and T8 reuses the same package. PI6 and H08 are then weakly tested. Fix: say how many participants must take route (i). Alternatively give T8 a fresh package.

9. `tasks.md:62,159,180,220` vs `predictions.md:60,74,132` - MINOR - H17 on T5 and H09 on T6 have no match in `predictions.md`. Fix: add the tasks to the predictions or remove the links.

10. `screener:141-143` - MINOR - It lacks the standard statement that withdrawing consent does not affect earlier lawful processing. Fix: add the sentence.

11. `severity-and-measures.md:91,95`; `observation-form.md:297` - MINOR - See the #10 row above. Replace the surnames with a neutral citation ("autores do SUS", "referência de SUS na literatura"), or accept them as academic citations by owner decision.

12. SUS - note, no fix needed beyond the unverified-wording disclosure. The ten English items in `observation-form.md:301-310` match the standard Brooke 1996 wording as I know it. The text is disclosed as unchecked against the source (`observation-form.md:297`, `severity-and-measures.md:95`), and the PT-PT validated text is not included. "Sistema" glossed as "o programa" (`observation-form.md:295`) is a mild adaptation and is disclosed. The scoring formula is correct.

## Other checks

- Nothing in the kit is presented as validation. `README.md:7` and `analysis-template.md:233-235` say so explicitly. There are no invented participants, consent records or rates.
- The 0e37bbcf… installer hash matches `docs/evidence/m18/installed-0.18.1/SHA256SUMS.txt`.
- The probability table arithmetic is right.

## CHECKED

- All 8 kit files, read in full.
- The prior review file.
- UI strings and routes in `desktop/studio/ui/js`, with greps and reads of `home.js`, `experiences.js`, `discover.js`, `session.js`, `player.js`, `lab.js` and `missions.js`. These cover T1 to T8: Land a rocket, A sensor that lies, Soft but off the pad, One millimetre, A late command, Compare in detail, Largest change, Altitude error, the Believed readouts, Open in Experiment Lab, Run experiment, the 8/16/32 seeds buttons, Listed for this failure, Challenge this claim, Evidence integrity, Recompute now and Recompute from scratch.
- Rust strings "Landed", "Mission incomplete", "Reached the ground, requirements not met" and "Truth stays outside the restricted zone".
- The installer hash in the evidence files.
- A grep for U+2014, emails and personal paths in `docs/usability`: no matches. Apart from the SUS citation authors and the `[nome]` placeholders, no personal names.

## NOT CHECKED

- Runtime values, timings and durations, which depend on the rehearsal.
- Whether the scene dashed line and Analyse charts show belief against truth (`charts.js` not read).
- The DOI and the Procedia citation, and the SUS items against the source.
- Whether "Landed" appears on screen as the Result card.
- European Portuguese AO1990 spelling in depth, beyond a read-through that found no obvious breaches.
