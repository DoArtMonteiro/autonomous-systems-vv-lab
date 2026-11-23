# Belief vs Truth iteration 1: agent-based evaluation record (not a human study)

Answer key sha256 fc9993ef27b32ad962cce150389527050d1a2a2365845a4d19ac159f995d828e (frozen before build).
Questions file sha256 0da342b159be7e0f46c32f34a38073be868bc6ad618740cd6a821b790c134632.
Answerer: one fresh Sonnet agent, viewer only. Scorer: fresh sonnet-critical-reviewer.

Comprehension: Q1 3.5, Q2 3.0, Q3 3.0, Q4 2.5, Q5 3.5 = 15.5/20 (threshold 17): FAIL. Strict: 15.
Traps: 12.5/16: PASS. Misled on core traps T1-T7: 0.
Root cause: viewer shows recorded data well, under-explains controller mechanics (cadence, decisions, divergence threshold, provenance, velocity errors).

UX critic (Fable 5.2, fable-ux-critic): clarity 3, fidelity 4, interpretation 4, interaction 3, accessibility 3, performance 4, maintainability 4, five questions 4.
Blocker: estimate connector drew divergence before the fault. Renderer: Three.js no material advantage.

# Iteration 2 (agent-based, not a human study)
Fresh answerer and fresh scorer. Comprehension 19.5/20 PASS (strict 17.0 borderline pass). Traps 15.5/16 PASS (strict 14.5). Core traps misled: 0. No factually wrong viewer statement found.
Caveat: one answerer per iteration (n = 1 each); part of the gain may be answerer variance.
Real residual defects: R2 nozzle-plane horizontal velocity not shown (0.61 vs CM 0.51); "Nothing guards x and y" untagged; card 4 blurs flag 8.18 s vs fusion cut-off 8.10 s; "sample N of 230" count; propellant margin label; GNSS velocity and IMU not shown.
Key imprecisions found by scorer: 3.2 err_vz touchdown sample 0.129; 4.2 "latch" wording.
UX critic (Fable 5.2) iteration 2: clarity 3, fidelity 4, interpretation 5, interaction 4, accessibility 3, performance 4, maintainability 4, five questions 4. Recommendation: ADOPT as candidate for the human gate, not installed. Renderer: Three.js no material advantage.
