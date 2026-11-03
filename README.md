# Autonomous Systems V&V Lab

A Rust and Python laboratory for repeatable autonomous-mission simulation, fault injection and verification.

**Status:** M9 and M9.1 are integrated in `main`. The M10.0 resilient-navigation design was accepted and merged through [PR #13](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/13). Its implementation is in development in draft [PR #15](https://github.com/DoArtMonteiro/autonomous-systems-vv-lab/pull/15), measured on development seeds only; the final configuration is not frozen and no evaluation seed has been run ([implementation notes](docs/m10-implementation.md)).

The main simulator models a two-dimensional ground vehicle. A separate, idealised six-degree-of-freedom rocket model supports the M8 and M9 research campaigns. Neither model controls real hardware, and the rocket model has no flight-data validation.

[Architecture](docs/architecture.md) · [M9 landing results](docs/m9-powered-landing.md) · [M8 model](docs/m8-rocket-dynamics.md) · [Reproduction](docs/reproducibility.md) · [M9 integration, PR #12](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/12)

## The problem

A mission can look safe to a controller while the true simulated state violates a constraint. Sensor, communication and actuator faults make that gap harder to inspect. This project separates the controller's observations from the simulator's true state, then records enough evidence to replay a failure and inspect the contract that detected it.

## What is implemented

- A deterministic Rust simulator for two-dimensional ground-vehicle missions, including seeded sensor, communication and actuator faults.
- Safety invariants and finite-trace temporal contracts, evaluated by a verifier separate from the mission controller.
- Ordered event logs, deterministic replay and bounded counterexample minimisation.
- Python campaign runners and a local Mission Control interface using versioned simulation adapters.
- A six-degree-of-freedom rocket dynamics package with fixed-step integration and reference cases.
- Closed-loop powered-landing simulations for M9 and the M9.1 safety-guard follow-up.

The controller uses sensor observations, not the true position. The verifier may use the true state to evaluate safety properties. A passing safety result, mission completion and progress are reported separately.

## Architecture

```mermaid
flowchart TB
    A[Scenario and seed] --> B[Deterministic simulation]
    B --> C[True vehicle state]
    C --> D[Sensors, communication and fault models]
    D --> E[Observed state]
    E --> F[Mission controller]
    F --> G[Actuator model]
    G --> B
    B --> H[Independent verifier]
    E --> H
    F --> H
    B --> I[Ordered event log]
    H --> J[Verification report]
    I --> K[Deterministic replay]
    K --> H
    J --> L[Bounded Python campaigns]
    L --> M[Counterexample minimiser]
```

The rocket package uses a separate adapter. Its M9 landing controller sees noisy sensor observations; the verifier checks the simulated state against predeclared contact and flight invariants. The simulation stops at the model's contact condition. It does not model landing-leg dynamics, bounce, tip-over or real vehicle hardware.

## Engineering decisions

- **Separate observation from truth.** The controller cannot read the true state. The verifier can use it to check invariants independently.
- **Make a failure replayable.** Integer coordinates, fixed time steps, an explicit pseudo-random generator and an ordered event stream reduce platform-dependent variation. Replay checks the recorded inputs and reconstructed outputs.
- **Treat hashes as integrity checks, not signatures.** SHA-256 detects changed inputs and logs. It does not prove who created an artefact.
- **Bound campaigns before execution.** Run, case, artefact-size and time limits constrain campaign work. A failed expectation or a safe trajectory does not by itself mean that the mission completed.
- **Keep results tied to a model.** Rocket campaign findings apply to the idealised model and its assumptions, not to flight hardware.

## Evidence and results

The M9 and M9.1 result document reports **780 M9 runs comparing two policies** and **1,050 M9.1 runs**, with replay checks and predeclared campaign conditions. The campaign scripts are published, but the original raw outputs are not stored in public `main`. Treat the totals as project-reported results; the original outputs are unavailable for direct inspection.

[PR #12](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/12) merged M9/M9.1 on 29/10/2026. [Its CI run](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/actions/runs/40852112731) passed Linux and Windows verification, including canonical output checks. The checks are automated CI; they do not establish independent human approval. The M9.1 report also records a failed predeclared hypothesis and a regression, rather than presenting only passing outcomes.

For the M8 model, see the [reference cases and model assumptions](docs/m8-rocket-dynamics.md). For campaign commands and artefacts, see the [reproducibility guide](docs/reproducibility.md).

## Run locally

Requirements: Rust and Cargo as pinned in `rust-toolchain.toml`; Python 3.10 or newer for campaign scripts.

```sh
cargo run -- run scenarios/basic-mission.json --seed 42 --output runs/basic
cargo run -- replay runs/basic/events.json
cargo test
python -m unittest discover -s tests -p "test_*.py"
```

To verify the rocket reference cases and run one landing scenario:

```sh
cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- verify
cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- land crates/vv-rocket/landing/altimeter-bias.json --seed 0 --output runs/m9-bias
cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- replay runs/m9-bias
```

To fly the M10 reference navigation (B+) and a small development campaign (development seeds only):

```sh
cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- land crates/vv-rocket/landing/m10-nominal.json --seed 4000 --output runs/m10-demo
cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- replay runs/m10-demo
python scripts/m10_campaign.py --seeds 5000-5019 --scenarios nominal,altimeter_stuck,gnss_dropout --arms guarded,m10_b_plus --output-root runs/m10-dev
```

The campaign script refuses the evaluation seeds (3000 to 3099) and the reserve seeds (6000 to 6099) unless the owner has frozen the configuration.

### M10 navigation workbench

Mission Control has an engineering workbench for the M10 navigation: pick a fault scenario (none, one or two faults), compare up to four policies on the same seed, scrub a shared time cursor across the trajectory, estimation-error, sensor, CUSUM and mode-timeline charts, read why the run recovered, touched down off the pad or was unsafe, replay it and download a reproducible evidence package. It refuses the evaluation and reserve seeds and shows development results only.

```sh
cargo build --release --manifest-path crates/vv-rocket/Cargo.toml
python scripts/mission_control.py --port 8780   # then open http://127.0.0.1:8780/workbench
```

See [docs/m10-mission-control.md](docs/m10-mission-control.md) for the journeys, routes, security properties and limitations.

### V&V Lab Studio (M11 desktop application, in development)

A Windows 11 application that packages the simulators behind a versioned domain contract (`vv-domain` 1.0): mission preparation, 3D rocket and 2D ground-vehicle scenes, time-synchronised telemetry, requirement and invariant verdicts, controller comparison, replay by recomputation, evidence export and a persistent library. It installs per user, needs no Rust, Python or Node.js at run time, and refuses the protected evaluation, reserve and held-out seeds before any simulation starts. Domains are separate host executables discovered at start; a benign reference domain proves that a new one needs no change to the platform or the interface.

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build.ps1   # builds the NSIS installer in desktop\target\release\bundle\nsis
```

See [docs/m11-desktop.md](docs/m11-desktop.md) for the architecture and how to add a domain, and [docs/m11-acceptance.md](docs/m11-acceptance.md) for installation and acceptance. The developer CLI and the browser Mission Control above remain supported.

### vv-exec experiment engine (M12, in development)

An in-process engine that runs `vv-experiment.v1` specifications (arms, fault grids, Latin hypercube and Saltelli designs) through the canonical `vv-rocket` library, with adaptive scheduling, hashed resumable records, retention by policy, an equivalence gate against the canonical command line and recomputed statistics. On development seeds it ran 14,400 landings in 8.4 s end to end with a 67 MB peak; the records are byte-identical for any worker count.

```sh
cargo build --release --manifest-path exec/Cargo.toml
exec/target/release/vv-exec run exec/examples/m12-dev-throughput.json --output exec/target/m12-dev/throughput
```

See [docs/m12-exec.md](docs/m12-exec.md). Its development-seed verdicts are engine parity evidence, not M10 results.

### M14 evidence robustness (in development)

M14 asks whether the platform's findings hold up: on a second physical domain, on failure mechanisms the method never saw, and under small changes to the assumptions behind a published claim.

- The ground vehicle of M1 to M6 now runs in process in `vv-exec`, byte-identical to `vv-lab run-m4` (38 compared cases, 0 differences). Four rocket-specific assumptions had to leave the shared code to make that possible.
- `vv-exec search` adds a domain-independent falsification search (uniform, Halton, corners-first, robustness-guided adaptive, exhaustive grid) with hashed logs, counterexample minimisation and full recomputation (`vv-exec search-verify`).
- A preregistered benchmark compared the strategies on four held-out problems. The claim that adaptive search generalises to unseen mechanisms is **not supported** (better on 0 of 4, worse on 0 of 4), as the preregistration predicted. Corner-and-centre testing missed every violation in 22 of 30 repetitions where failures were rare.
- An exploratory fragility study found a safety claim with no margin (1 mm of GPS noise drops the zone-corridor scenario from 100 to 61 safe runs in 100) and showed that the published M9.1 criterion G3 holds only when the GNSS bias is present from 0 s.

```sh
python scripts/m14_benchmark.py --split development --output-root exec/out/m14-dev
python scripts/m14_fragility.py --output-root exec/out/m14-fragility
```

See [docs/m14-evidence-robustness.md](docs/m14-evidence-robustness.md) (case study), [docs/m14-preregisto.md](docs/m14-preregisto.md) (preregistration) and [docs/evidence/m14/](docs/evidence/m14/). These are simulation results on development and M14-owned held-out seeds; they do not change the status of M10.

An expected safety violation can make a `run` command exit with code `2`; that is a simulated finding, not a test harness failure. See the scenario's result and report before interpreting the exit code.

## Development timeline

- **08/10/2026:** deterministic mission simulation and replay introduced in [commit `cfadcdb`](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/commit/cfadcdb).
- **12/10/2026:** temporal contracts and actuator fault injection added in [commit `a22db7d`](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/commit/a22db7d).
- **23/10/2026:** adversarial campaigns and deterministic failure replay added in [commit `d491b4a`](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/commit/d491b4a).
- **24/10/2026:** controller-repair findings and the evidence-based replay workbench integrated through [PR #6](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/6) and [PR #7](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/7).
- **25/10/2026:** M7 Mission Control and the simulator-adapter contract integrated through [PR #9](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/9), merged as commit [`ec2a2ab`](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/commit/ec2a2ab8e237d51c65df96aa7ca99b1c465ec624).
- **25/10/2026:** the six-degree-of-freedom rocket model and reference verification added in [commit `8b04960`](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/commit/8b04960).
- **29/10/2026:** M9 and M9.1 integrated through [PR #12](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/12).

Dates above are commit or merge dates, not operational acceptance dates.

## Limits and current status

- The ground-vehicle model is two-dimensional and simulated.
- The rocket model is idealised; no flight data, physical hardware or landing-leg contact model validates it.
- Full M9/M9.1 campaign output is not included in the public repository.
- M10 resilient navigation is implemented on a development branch and measured on development seeds only. It has not been evaluated; do not read its development numbers as M10 results.
- Mission Control runs locally and is not an operational service.
- M14 has no external tool comparison (S-TaLiRo, Breach, Scenic) and no standards adapter; its preregistration was not blinded.

Further model contracts and campaign reports are linked from the [repository documentation](docs/architecture.md).
