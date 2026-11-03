# Autonomous Systems V&V Lab

A Rust and Python laboratory for repeatable autonomous-mission simulation, fault injection and verification.

**Status:** M9 and M9.1 are integrated in `main`. The M10.0 resilient-navigation design was merged through [PR #13](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/13). The M10 implementation is in draft [PR #15](https://github.com/WhiteBlindness/autonomous-systems-vv-lab/pull/15) and has not been accepted. The M11 desktop application and the M12 experiment engine are proposed for integration by this branch, without M10, pending review.

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

An expected safety violation can make a `run` command exit with code `2`; that is a simulated finding, not a test harness failure. See the scenario's result and report before interpreting the exit code.

### V&V Lab Studio (M11 desktop application)

A Windows 11 application that packages the simulators behind a versioned domain contract (`vv-domain` 1.0): mission preparation, a 3D rocket scene and a 2D ground-vehicle scene, time-synchronised telemetry, requirement and invariant verdicts, controller comparison, replay by recomputation, evidence export and a persistent library. It installs per user and needs no Rust, Python or Node.js at run time. The rocket domain offers the M9 and M9.1 policies and faults only; it refuses the protected rocket seeds (3000 to 3099 and 6000 to 6099) and the M6 held-out ground seeds (101 to 112) before any simulation starts. Domains are separate host executables discovered at start; a benign reference domain shows that a new domain needs no change to the platform or the interface.

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build.ps1   # builds the NSIS installer in desktop\target\release\bundle\nsis
```

See [docs/m11-desktop.md](docs/m11-desktop.md) for the architecture and how to add a domain, and [docs/m11-acceptance.md](docs/m11-acceptance.md) for installation and acceptance. The UI smoke test has not yet been run on this branch. The developer CLI and the local Mission Control remain supported.

### vv-exec experiment engine (M12)

An in-process engine that runs `vv-experiment.v1` specifications (arms, fault grids, Latin hypercube and Saltelli designs) through the canonical `vv-rocket` library, with adaptive scheduling, hashed resumable records, retention by policy, an equivalence gate against the canonical command line and statistics recomputed from the records. On development seeds 7000 to 9399, the example experiment (the M9.1 guarded controller under six conditions) ran 14,400 landings in 7.5 to 10.4 s end to end on 16 threads, over three runs on a shared AMD Ryzen 7 7800X3D machine; full recomputation with `vv-exec verify` took 11.2 s. Peak memory was not re-measured on this branch. Tests check that the records are byte-identical for any worker count.

```sh
cargo build --release --manifest-path exec/Cargo.toml
exec/target/release/vv-exec run exec/examples/m12-dev-throughput.json --output exec/target/m12-dev/throughput --threads 16
exec/target/release/vv-exec verify exec/target/m12-dev/throughput --threads 16
```

See [docs/m12-exec.md](docs/m12-exec.md). Its development-seed verdicts are engine evidence, not evaluation results.

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
- M10 resilient navigation is not in `main`: its design (M10.0) is merged, and its implementation stays in draft PR #15, which has not been accepted. Do not treat its resilience work as an integrated or evaluated result.
- Mission Control runs locally and is not an operational service.

Further model contracts and campaign reports are linked from the [repository documentation](docs/architecture.md).
