//! Reference domain of the `vv-domain` contract: a benign, deliberately small simulation that exists
//! to prove the extension mechanism, not to study anything. A mass on a spring and damper is held
//! at zero by a proportional-derivative controller that only sees a noisy position sensor. Integer
//! arithmetic (millimetres, ticks of 10 ms) and an explicit SplitMix64 generator keep it
//! deterministic on every platform. It is discovered like any other domain and hidden from the
//! product UI (`user_facing: false`).

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::process::ExitCode;

use serde::{Deserialize, Serialize};
use serde_json::json;
use vv_platform::canonical::{pretty_bytes, sha256_hex};
use vv_platform::host_sdk::{DomainHost, HostError, host_main, read_bounded};
use vv_platform::*;

const MANIFEST: &str = include_str!("../domain.json");
const SOURCE: &str = include_str!("main.rs");
const TICKS: i64 = 500;
const DT_MS: i64 = 10;
const BOUND_MM: i64 = 120;
const SETTLE_MM: i64 = 5;
const SETTLE_TICKS: i64 = 100;

struct Reference;

#[derive(Serialize, Deserialize, PartialEq, Debug)]
struct Trace {
    schema: String,
    seed: u64,
    tick_ms: i64,
    x_mm: Vec<i64>,
    v_mm_s: Vec<i64>,
    observed_mm: Vec<Option<i64>>,
    command: Vec<i64>,
}

/// SplitMix64, the explicit generator of this domain.
struct SplitMix(u64);

impl SplitMix {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn uniform(&mut self, half_width: i64) -> i64 {
        if half_width == 0 {
            return 0;
        }
        (self.next() % (2 * half_width as u64 + 1)) as i64 - half_width
    }
}

fn param(request: &RunRequest, id: &str) -> i64 {
    request.parameters.get(id).copied().unwrap_or(0.0) as i64
}

fn simulate(request: &RunRequest) -> Trace {
    let mut rng = SplitMix(request.seed);
    let kp = param(request, "kp");
    // State in micrometres so integer steps do not truncate small motions; the trace is in mm.
    let noise = param(request, "noise_mm") * 1000;
    let mut x = param(request, "x0_mm") * 1000;
    let mut v = 0i64;
    let mut held = x;
    let mut last_obs = x;
    let mut trace = Trace {
        schema: "vv-reference-trace.v1".into(),
        seed: request.seed,
        tick_ms: DT_MS,
        x_mm: Vec::new(),
        v_mm_s: Vec::new(),
        observed_mm: Vec::new(),
        command: Vec::new(),
    };
    for tick in 0..=TICKS {
        let t = tick as f64;
        let active = |kind: &str| {
            request
                .faults
                .iter()
                .find(|f| f.kind == kind && f.start <= t && t <= f.end)
        };
        let noise_sample = rng.uniform(noise);
        let observed = if active("sensor_dropout").is_some() {
            None
        } else {
            let bias = active("sensor_bias")
                .and_then(|f| f.magnitude)
                .unwrap_or(0.0) as i64
                * 1000;
            Some(x + noise_sample + bias)
        };
        if let Some(o) = observed {
            held = o;
        }
        // PD on the held observation; the rate is the difference of held observations.
        let rate = (held - last_obs) * 1000 / DT_MS;
        last_obs = held;
        let u = -(kp * held) / 10 - rate * 3 / 2;
        trace.x_mm.push(x / 1000);
        trace.v_mm_s.push(v / 1000);
        trace.observed_mm.push(observed.map(|o| o / 1000));
        trace.command.push(u / 1000);
        // Spring k = 4, damper c = 1 (per second), unit mass; explicit Euler on integers.
        let a = -4 * x - v + u;
        v += a * DT_MS / 1000;
        x += v * DT_MS / 1000;
    }
    trace
}

fn record_for(request: &RunRequest, trace: &Trace) -> RunRecord {
    let ticks: Vec<f64> = (0..=TICKS).map(|t| t as f64).collect();
    let as_f = |v: &[i64]| v.iter().map(|x| Some(*x as f64)).collect::<Vec<_>>();
    let channel = |id: &str, label: &str, unit: &str, kind: &str, values| Channel {
        id: id.into(),
        label: label.into(),
        unit: unit.into(),
        group: "state".into(),
        kind: kind.into(),
        timebase: "tick".into(),
        values,
    };
    let breach = trace.x_mm.iter().position(|x| x.abs() > BOUND_MM);
    let tail_start = (TICKS - SETTLE_TICKS) as usize;
    let unsettled = trace.x_mm[tail_start..]
        .iter()
        .position(|x| x.abs() > SETTLE_MM)
        .map(|i| i + tail_start);
    let worst = trace.x_mm.iter().map(|x| x.abs()).max().unwrap_or(0);
    let mut events = Vec::new();
    for f in &request.faults {
        events.push(Event {
            t: f.start,
            kind: "fault_start".into(),
            label: format!("{} begins", f.kind),
            severity: "fault".into(),
            source: "fault".into(),
            detail: json!({ "magnitude": f.magnitude }),
        });
        events.push(Event {
            t: f.end,
            kind: "fault_end".into(),
            label: format!("{} ends", f.kind),
            severity: "info".into(),
            source: "fault".into(),
            detail: json!({}),
        });
    }
    if let Some(i) = breach {
        events.push(Event {
            t: i as f64,
            kind: "violation".into(),
            label: "position bound exceeded".into(),
            severity: "violation".into(),
            source: "verifier".into(),
            detail: json!({ "x_mm": trace.x_mm[i] }),
        });
    }
    events.sort_by(|a, b| a.t.total_cmp(&b.t).then(a.kind.cmp(&b.kind)));
    let settled = unsettled.is_none();
    let trace_bytes = pretty_bytes(trace);
    RunRecord {
        schema: RECORD_SCHEMA.into(),
        domain: DomainRef {
            id: "reference-oscillator".into(),
            version: env!("CARGO_PKG_VERSION").into(),
            contract: format!("{CONTRACT_NAME}/{CONTRACT_MAJOR}.{CONTRACT_MINOR}"),
        },
        request: request.clone(),
        provenance: Provenance {
            source_sha256: sha256_hex(SOURCE.replace("\r\n", "\n").as_bytes()),
            simulator: "vv-domain-reference".into(),
            artifacts: Vec::new(),
            reproduce: vec![format!(
                "cargo run --manifest-path desktop/Cargo.toml -p vv-domain-reference -- run request.json --output out (trace sha256 {})",
                sha256_hex(&trace_bytes)
            )],
        },
        model_validity:
            "Reference domain for the extension contract; a toy model with no physical claim."
                .into(),
        outcome: Outcome {
            code: if settled { "settled" } else { "not_settled" }.into(),
            label: if settled { "Settled" } else { "Not settled" }.into(),
            status: if settled { "success" } else { "failure" }.into(),
            explanation: match unsettled {
                None => format!(
                    "The true position stayed within {SETTLE_MM} mm over the last {SETTLE_TICKS} ticks."
                ),
                Some(i) => format!(
                    "At tick {i} the true position was {} mm, outside the {SETTLE_MM} mm settling band.",
                    trace.x_mm[i]
                ),
            },
        },
        safety: Safety {
            status: if breach.is_some() { "unsafe" } else { "safe" }.into(),
            class: None,
            explanation: match breach {
                None => format!("The true position never left the {BOUND_MM} mm bound."),
                Some(i) => format!("The true position left the {BOUND_MM} mm bound at tick {i}."),
            },
        },
        timebases: BTreeMap::from([("tick".to_owned(), ticks)]),
        channels: vec![
            channel("x_true", "True position", "mm", "truth", as_f(&trace.x_mm)),
            channel(
                "x_observed",
                "Observed position",
                "mm",
                "observation",
                trace
                    .observed_mm
                    .iter()
                    .map(|o| o.map(|x| x as f64))
                    .collect(),
            ),
            channel(
                "command",
                "Controller command",
                "mm/s2",
                "command",
                as_f(&trace.command),
            ),
            channel(
                "bound",
                "Position bound",
                "mm",
                "limit",
                vec![Some(BOUND_MM as f64); trace.x_mm.len()],
            ),
        ],
        events,
        requirements: vec![
            RequirementResult {
                id: "S_bound".into(),
                label: "Position bound".into(),
                category: "invariant".into(),
                status: if breach.is_some() { "fail" } else { "pass" }.into(),
                expected: format!("|x| <= {BOUND_MM} mm at every tick"),
                observed: format!("worst |x| = {worst} mm"),
                t: breach.map(|i| i as f64),
                explanation: "Judged on the true position, never on the observation.".into(),
            },
            RequirementResult {
                id: "R_settle".into(),
                label: "Settling".into(),
                category: "requirement".into(),
                status: if settled { "pass" } else { "fail" }.into(),
                expected: format!("|x| <= {SETTLE_MM} mm over the last {SETTLE_TICKS} ticks"),
                observed: match unsettled {
                    None => "inside the band".into(),
                    Some(i) => format!("{} mm at tick {i}", trace.x_mm[i]),
                },
                t: Some(unsettled.unwrap_or(TICKS as usize) as f64),
                explanation: "Mission requirement, reported separately from the safety invariant."
                    .into(),
            },
        ],
        metrics: vec![Metric {
            id: "worst_abs_x".into(),
            label: "Worst absolute position".into(),
            value: Some(worst as f64),
            unit: "mm".into(),
            group: "safety".into(),
        }],
        scene: json!({ "kind": "none" }),
        notes: vec!["Reference domain: proves the contract, makes no physical claim.".into()],
        entities: None,
        mission: None,
    }
}

fn item(id: &str, label: &str, description: &str) -> Item {
    Item {
        id: id.into(),
        label: label.into(),
        description: description.into(),
    }
}

fn int_param(id: &str, label: &str, unit: &str, range: (f64, f64), default: f64) -> ParameterSpec {
    ParameterSpec {
        id: id.into(),
        label: label.into(),
        description: format!("{label} of the reference oscillator."),
        unit: unit.into(),
        group: "controller".into(),
        advanced: false,
        min: range.0,
        max: range.1,
        step: 1.0,
        default,
        integer: true,
        influences: Vec::new(),
    }
}

impl DomainHost for Reference {
    fn manifest(&self) -> DomainManifest {
        serde_json::from_str(MANIFEST).expect("embedded domain.json is valid")
    }

    fn catalog(&self) -> DomainCatalog {
        DomainCatalog {
            schema: CATALOG_SCHEMA.into(),
            domain: "reference-oscillator".into(),
            time: TimeSpec {
                unit: "tick".into(),
                label: "tick (10 ms)".into(),
            },
            vehicles: vec![item(
                "mass",
                "Unit mass",
                "A unit mass on a spring and damper.",
            )],
            scenarios: vec![ScenarioSpec {
                id: "hold-zero".into(),
                label: "Hold at zero".into(),
                description: "Start displaced and return to zero.".into(),
                vehicle: "mass".into(),
                controllers: vec!["pd".into()],
                parameters: vec!["x0_mm".into(), "kp".into(), "noise_mm".into()],
                default_controller: "pd".into(),
            }],
            controllers: vec![item(
                "pd",
                "PD",
                "Proportional-derivative on the held observation.",
            )],
            parameters: vec![
                int_param("x0_mm", "Initial position", "mm", (-100.0, 100.0), 80.0),
                int_param("kp", "Proportional gain", "1/10 per s2", (0.0, 400.0), 60.0),
                int_param(
                    "noise_mm",
                    "Sensor noise half-width",
                    "mm",
                    (0.0, 10.0),
                    1.0,
                ),
            ],
            faults: vec![
                FaultSpec {
                    kind: "sensor_bias".into(),
                    label: "Sensor bias".into(),
                    description: "The position sensor reads high by the magnitude.".into(),
                    target: "sensor".into(),
                    magnitude: Some(MagnitudeSpec {
                        min: 1.0,
                        max: 100.0,
                        unit: "mm".into(),
                        default: 40.0,
                    }),
                    window: None,
                    default_start: 100.0,
                    default_end: 500.0,
                    controllers: None,
                },
                FaultSpec {
                    kind: "sensor_dropout".into(),
                    label: "Sensor dropout".into(),
                    description: "No measurement; the controller holds the last one.".into(),
                    target: "sensor".into(),
                    magnitude: None,
                    window: Some(WindowSpec {
                        min_length: 1.0,
                        max_length: 200.0,
                    }),
                    default_start: 50.0,
                    default_end: 150.0,
                    controllers: None,
                },
            ],
            max_faults: 2,
            channels: vec![],
            requirements: vec![],
            demos: vec![],
        }
    }

    fn check(&self, request: RunRequest) -> Result<RunRequest, String> {
        for f in &request.faults {
            if f.start.fract() != 0.0 || f.end.fract() != 0.0 || f.end > TICKS as f64 {
                return Err(format!("fault windows are whole ticks in 0 to {TICKS}"));
            }
        }
        Ok(request)
    }

    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError> {
        let trace = simulate(request);
        fs::write(out.join("trace.json"), pretty_bytes(&trace))
            .map_err(|e| HostError::Simulation(e.to_string()))?;
        Ok(record_for(request, &trace))
    }

    fn native_replay(&self, dir: &Path) -> Vec<ReplayCheck> {
        let stored: Option<Trace> = read_bounded(&dir.join("trace.json"), 8 * 1024 * 1024)
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok());
        let record: Option<RunRecord> = read_bounded(&dir.join(RECORD_FILE), 64 * 1024 * 1024)
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok());
        let same = match (&stored, &record) {
            (Some(t), Some(r)) => &simulate(&r.request) == t,
            _ => false,
        };
        vec![ReplayCheck {
            name: "native trace recomputed from the seed".into(),
            pass: same,
            detail: String::new(),
        }]
    }
}

fn main() -> ExitCode {
    if let Ok(log) = std::env::var("VV_REFERENCE_CALL_LOG") {
        // Test hook: records each invocation so tests can prove what the platform never started.
        let args: Vec<String> = std::env::args().skip(1).collect();
        let command = args.first().cloned().unwrap_or_default();
        let seed = args
            .get(1)
            .and_then(|f| fs::read(f).ok())
            .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
            .and_then(|v| v.get("seed").and_then(|s| s.as_u64()));
        let entry = format!(
            "{command} {}\n",
            seed.map(|s| s.to_string()).unwrap_or_default()
        );
        let _ = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(log)
            .and_then(|mut f| std::io::Write::write_all(&mut f, entry.as_bytes()));
    }
    host_main(&Reference)
}
