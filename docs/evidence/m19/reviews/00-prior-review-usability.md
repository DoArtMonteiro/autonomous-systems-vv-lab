# First independent review of the usability kit (2026-11-18)

Agent role: `sonnet-critical-reviewer`. Not human review.

VERDICT: APPROVE WITH FIXES. There are no kit-breaking blockers apart from F1, which blocks recruitment until it is fixed. Every task route I traced exists in the UI.

**Findings, most severe first**

1. `screener-and-consent.md:111-133` - BLOCKER - Strangers get control of the owner's PC through the remote session, and nothing isolates it. The voice and remote tools are undecided (README:191). The sheet names no processors, no non-EU transfer (the owner is abroad, README:117) and no controller (placeholders at :83). The audio is personal data. Fix: use a dedicated low-privilege account or VM with no personal files; name the tools, recipients and transfer basis; fill in the controller and contact; add an age 18+ criterion; disclose that the moderator may be the product author.
2. `tasks.md:203, 34, 158` - MAJOR - T8 is not reachable as written. If T6 is cut under variant A, no investigation exists ("não tem investigação", :158) yet T8 "usa a variante B". After T7 the screen is the Lab, and the moderator cannot legitimately open the investigation. Opening it also reveals where the "Evidence integrity" tile is. Fix: always prepare the B package, and make the T8 start point a neutral screen.
3. `tasks.md:213, 172, 202`, `moderator-script.md:117, 140` - MAJOR - Q8a quotes «Recomputed, every check passed», Q6b quotes «Not refuted within budget», and the T8 card says "recalculada". All of this breaks the script's own rule against naming unseen labels. The yes/no questions also invite the "no" they are testing for. Fix: ask open questions ("what does this tell you about the engineer's claim?").
4. `tasks.md:58, 70` - MAJOR - The card says one vehicle "aterrou muito mal", and Q2a asks about "segurança". That cues the safety chip and weakens the misreading test. The mission summary already states the cause (`experiences.js:70`). Fix: neutral card; ask "what would you conclude about this vehicle?"
5. `tasks.md:145-148` - MAJOR - The Q5a key assumes a final "0.00 mm". The narrative (`catalog.rs:488-494`) has the vehicle stepping into the zone at tick 21, so the last true position may be 250 mm from the goal. The scoring is written before the rehearsal. Fix: score against the value read at the rehearsal.
6. `severity-and-measures.md:130` vs `:113-123` - MAJOR - Thresholds are counts of 2/3 and 4/5 for the whole phase but are also "per profile". With 1 to 2 people per profile that is impossible. Fix: apply thresholds to the whole phase, and report profiles descriptively.
7. `tasks.md:34` vs README:126, consent - MAJOR - The cut rule allows the task block to end at minute 41. With SUS, closing talk and wrap-up (7 min) that is 48 min, against "cerca de 45". The 31-minute plan (3.9 min per task, including questions) is optimistic for novices on remote latency (T4, T6, T7). Cutting T3, T4, T6 and T7 would drop core-loop steps. Fix: decide 60 min or fewer tasks before Phase 1.
8. `tasks.md:149-150, 195`, `moderator-script.md:84` - MAJOR - Q5d has no confidence rating, and Q7c covers two questions. Severity 4 and M6 need a rating per safety or evidence question. "Seguro/a" in the confidence scale also collides with the safety wording. Fix: add one rating per question and use "certo/a".
9. `tasks.md:180` - MINOR - The T7 card names the diagnosis ("controlo lateral fraco"), and the mission narrative (`demos.rs:160`) gives the route. Fix: drop the diagnosis from the card.
10. `severity-and-measures.md:123` vs `:64`, README:43 vs :11 - MINOR - The Phase 2 severity-4 acceptance rule differs between the table and rule 7. "Sem alteração" (:11) contradicts the altered Phase 2 product (:43). Also: CE-T6-3 and CE-T8-2 are named as critical but described as non-critical; `predictions.md` links H05 and H17 to tasks that `tasks.md` omits; S4 and S8 collect data that README:156 does not list; "Sauro e Lewis" and "Brooke" are personal names.

**CHECKED**
- Read all 8 kit files.
- Confirmed in the UI source and Rust: labels and buttons for T1 to T8 exist, the T6 claim text matches, and demo values (33 m/s, 19 m, 0.1 s, tick 6, tick 21) are present.
- No U+2014, emails or personal paths in the kit.
- The probability table arithmetic.
- Task and CE IDs are consistent.

**NOT CHECKED**
- Any runtime value shown on screen, including "0.00 mm" and the "Refuted" verdict as displayed.
- Challenge and playback durations.
- `charts.js`, and whether the Lab group shows "Listed for this failure".
- SUS item wording and the DOI citation.
