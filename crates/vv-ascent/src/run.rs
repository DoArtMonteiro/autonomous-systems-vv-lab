//! Native artifacts of a run and their replay. `write_run` writes `case.json` (the exact case
//! bytes), `trace.json` (per-entity true samples every second, the observations given to the flight
//! software and the events in their total order), `verification.json` and `run.json` (seed, hashes).
//! `replay` recomputes the states and every verdict from `case.json` and the seed and compares
//! them byte for byte; it never returns a stored conclusion.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::dynamics::{Aero, Environment, altitude, density, drag};
use crate::model::{DT, G0, Prepared, TICKS_PER_S, parse_case, prepare};
use crate::sim::{EntityRun, Sample, SimEvent, Simulation, downrange, simulate};
use crate::verify::{Verification, verify};
use crate::{sha256_hex, source_sha256};

pub const TRACE_SCHEMA: &str = "vv-ascent-trace.v1";
pub const RUN_SCHEMA: &str = "vv-ascent-run.v1";
/// Samples written to the trace: one per second of logical time, plus the last of each entity and
/// every tick that carries an event of that entity.
pub const SAMPLE_EVERY_TICKS: u64 = TICKS_PER_S;
const MAX_CASE_BYTES: u64 = 256 * 1024;
const MAX_ARTIFACT_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TraceSample {
    pub tick: u64,
    pub t_s: f64,
    pub x_m: f64,
    pub z_m: f64,
    pub vx_m_s: f64,
    pub vz_m_s: f64,
    pub altitude_m: f64,
    pub downrange_m: f64,
    pub speed_m_s: f64,
    pub radial_velocity_m_s: f64,
    pub mass_kg: f64,
    pub propellant_kg: f64,
    pub throttle: f64,
    pub dynamic_pressure_pa: f64,
    pub sensed_acceleration_g: f64,
    /// Altitude and speed of the navigation solution at this tick, when this entity was guided.
    pub observed_altitude_m: Option<f64>,
    pub observed_speed_m_s: Option<f64>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TraceEntity {
    pub id: String,
    pub label: String,
    pub kind: String,
    pub parent: Option<String>,
    pub start_tick: u64,
    pub end_tick: u64,
    pub end_reason: String,
    pub samples: Vec<TraceSample>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TraceEvent {
    pub tick: u64,
    pub t_s: f64,
    pub entity: String,
    pub source: String,
    pub kind: String,
    pub label: String,
    pub detail: Value,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Trace {
    pub schema: String,
    pub seed: u64,
    pub dt_s: f64,
    pub dispersions_enabled: bool,
    /// Per stage: thrust, Isp, loaded propellant and dry-mass factors applied to the true vehicle.
    pub dispersion_factors: [[f64; 4]; 2],
    pub event_order: String,
    pub entities: Vec<TraceEntity>,
    pub events: Vec<TraceEvent>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RunInfo {
    pub schema: String,
    pub seed: u64,
    pub simulator: String,
    pub source_sha256: String,
    pub case_sha256: String,
    pub trace_sha256: String,
    pub verification_sha256: String,
    pub outcome: String,
}

pub const EVENT_ORDER: &str = "tick, then entity (stack, booster, upper, then the mission), then source (truth, controller, verifier), then emission order";

fn trace_sample(s: &Sample, aero: &Aero) -> TraceSample {
    let d = drag(&Environment::MISSION, aero, s.r, s.v);
    TraceSample {
        tick: s.tick,
        t_s: s.tick as f64 * DT,
        x_m: s.r.x,
        z_m: s.r.z,
        vx_m_s: s.v.x,
        vz_m_s: s.v.z,
        altitude_m: altitude(s.r),
        downrange_m: downrange(s.r),
        speed_m_s: s.v.norm(),
        radial_velocity_m_s: s.v.dot(s.r.unit()),
        mass_kg: s.m,
        propellant_kg: s.propellant_kg,
        throttle: s.throttle,
        dynamic_pressure_pa: 0.5 * density(altitude(s.r)) * s.v.dot(s.v),
        sensed_acceleration_g: ((s.thrust + d) * (1.0 / s.m)).norm() / G0,
        observed_altitude_m: s.observation.map(|o| altitude(o.r)),
        observed_speed_m_s: s.observation.map(|o| o.v.norm()),
    }
}

fn entity_trace(index: usize, e: &EntityRun, events: &[SimEvent]) -> TraceEntity {
    let aero = Aero {
        area_m2: e.area_m2,
        cd: e.cd,
    };
    let first = e.samples.first().map_or(0, |s| s.tick);
    let last = e.samples.last().map_or(0, |s| s.tick);
    let marked: Vec<u64> = events
        .iter()
        .filter(|x| x.entity == index)
        .map(|x| x.tick)
        .collect();
    let samples = e
        .samples
        .iter()
        .filter(|s| {
            (s.tick - first).is_multiple_of(SAMPLE_EVERY_TICKS)
                || s.tick == last
                || marked.contains(&s.tick)
        })
        .map(|s| trace_sample(s, &aero))
        .collect();
    TraceEntity {
        id: e.id.into(),
        label: e.label.into(),
        kind: e.kind.into(),
        parent: e.parent.map(String::from),
        start_tick: first,
        end_tick: last,
        end_reason: e.end_reason.clone(),
        samples,
    }
}

pub fn trace_of(prep: &Prepared, sim: &Simulation, verification: &Verification) -> Trace {
    let names: Vec<&str> = sim.entities.iter().map(|e| e.id).collect();
    Trace {
        schema: TRACE_SCHEMA.into(),
        seed: prep.seed,
        dt_s: DT,
        dispersions_enabled: prep.dispersions_enabled,
        dispersion_factors: prep.factors,
        event_order: EVENT_ORDER.into(),
        entities: sim
            .entities
            .iter()
            .enumerate()
            .map(|(i, e)| entity_trace(i, e, &verification.events))
            .collect(),
        events: verification
            .events
            .iter()
            .map(|e| TraceEvent {
                tick: e.tick,
                t_s: e.tick as f64 * DT,
                entity: names.get(e.entity).copied().unwrap_or("mission").into(),
                source: match e.source {
                    crate::sim::Source::Truth => "truth",
                    crate::sim::Source::Controller => "controller",
                    crate::sim::Source::Verifier => "verifier",
                }
                .into(),
                kind: e.kind.clone(),
                label: e.label.clone(),
                detail: e.detail.clone(),
            })
            .collect(),
    }
}

pub fn pretty<T: Serialize>(value: &T) -> Vec<u8> {
    let mut bytes = serde_json::to_vec_pretty(value).expect("serialisable");
    bytes.push(b'\n');
    bytes
}

/// Everything a run produces, in memory.
pub struct Outputs {
    pub prepared: Prepared,
    pub simulation: Simulation,
    pub verification: Verification,
    pub trace: Trace,
    pub trace_bytes: Vec<u8>,
    pub verification_bytes: Vec<u8>,
}

pub fn compute(case_bytes: &[u8], seed: u64) -> Result<Outputs, String> {
    let case = parse_case(case_bytes)?;
    let prepared = prepare(&case, seed)?;
    let simulation = simulate(&prepared);
    let verification = verify(&prepared, &simulation);
    let trace = trace_of(&prepared, &simulation, &verification);
    let trace_bytes = pretty(&trace);
    let verification_bytes = pretty(&verification);
    Ok(Outputs {
        prepared,
        simulation,
        verification,
        trace,
        trace_bytes,
        verification_bytes,
    })
}

fn read_bounded(path: &Path, cap: u64) -> Result<Vec<u8>, String> {
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let meta = fs::metadata(path).map_err(|e| format!("{name}: {e}"))?;
    if meta.len() > cap {
        return Err(format!("{name} is larger than {cap} bytes"));
    }
    fs::read(path).map_err(|e| format!("{name}: {e}"))
}

/// Runs a case into `out` (which must exist) and writes the four native artifacts.
pub fn write_run(case_path: &Path, seed: u64, out: &Path) -> Result<Outputs, String> {
    let case_bytes = read_bounded(case_path, MAX_CASE_BYTES)?;
    let outputs = compute(&case_bytes, seed)?;
    let info = RunInfo {
        schema: RUN_SCHEMA.into(),
        seed,
        simulator: format!("vv-ascent {}", env!("CARGO_PKG_VERSION")),
        source_sha256: source_sha256(),
        case_sha256: sha256_hex(&case_bytes),
        trace_sha256: sha256_hex(&outputs.trace_bytes),
        verification_sha256: sha256_hex(&outputs.verification_bytes),
        outcome: outputs.verification.outcome.into(),
    };
    let write = |name: &str, bytes: &[u8]| {
        fs::write(out.join(name), bytes).map_err(|e| format!("{name}: {e}"))
    };
    write("case.json", &case_bytes)?;
    write("trace.json", &outputs.trace_bytes)?;
    write("verification.json", &outputs.verification_bytes)?;
    write("run.json", &pretty(&info))?;
    Ok(outputs)
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Check {
    pub name: String,
    pub pass: bool,
    pub detail: String,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct ReplayReport {
    pub status: &'static str,
    pub checks: Vec<Check>,
}

fn check(name: &str, pass: bool, detail: impl Into<String>) -> Check {
    Check {
        name: name.into(),
        pass,
        detail: detail.into(),
    }
}

/// Recomputes a stored run from `case.json` and the seed of `run.json`.
pub fn replay(dir: &Path) -> ReplayReport {
    let mut checks = Vec::new();
    let mut go = || -> Result<(), String> {
        let info: RunInfo =
            serde_json::from_slice(&read_bounded(&dir.join("run.json"), MAX_CASE_BYTES)?)
                .map_err(|e| format!("run.json: {e}"))?;
        checks.push(check(
            "run.json is a valid run file",
            info.schema == RUN_SCHEMA,
            &info.schema,
        ));
        let same_source = info.source_sha256 == source_sha256();
        checks.push(check(
            "the run was produced by these simulator sources",
            same_source,
            if same_source {
                String::new()
            } else {
                "source hash differs".into()
            },
        ));
        let case_bytes = read_bounded(&dir.join("case.json"), MAX_CASE_BYTES)?;
        let trace = read_bounded(&dir.join("trace.json"), MAX_ARTIFACT_BYTES)?;
        let verification = read_bounded(&dir.join("verification.json"), MAX_ARTIFACT_BYTES)?;
        let hashes = sha256_hex(&case_bytes) == info.case_sha256
            && sha256_hex(&trace) == info.trace_sha256
            && sha256_hex(&verification) == info.verification_sha256;
        checks.push(check(
            "stored files match the hashes in run.json",
            hashes,
            "",
        ));
        let fresh = compute(&case_bytes, info.seed)?;
        checks.push(check(
            "the case is valid and the run is recomputed",
            true,
            "",
        ));
        checks.push(check(
            "recomputed states, observations and events equal trace.json byte for byte",
            fresh.trace_bytes == trace,
            "",
        ));
        checks.push(check(
            "recomputed requirements and invariants equal verification.json byte for byte",
            fresh.verification_bytes == verification,
            "",
        ));
        checks.push(check(
            "recomputed outcome equals the stored outcome",
            fresh.verification.outcome == info.outcome,
            format!("{} vs {}", fresh.verification.outcome, info.outcome),
        ));
        Ok(())
    };
    if let Err(e) = go() {
        checks.push(check("the stored run can be read and recomputed", false, e));
    }
    let ok = !checks.is_empty() && checks.iter().all(|c| c.pass);
    ReplayReport {
        status: if ok { "verified" } else { "rejected" },
        checks,
    }
}
