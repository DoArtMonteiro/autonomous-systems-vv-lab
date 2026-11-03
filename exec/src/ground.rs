//! The ground vehicle of M1 to M6 as an in-process domain: the M4 controller evaluation that
//! `vv-lab run-m4` writes. It calls the public library of the root crate, the same functions the
//! command line calls, and serialises every artifact the way the command line does, so the bytes
//! match. The root crate is not changed.
//!
//! A case is one JSON document, `vv-ground-case.v1`, that bundles the files the command line takes
//! separately: the scenario, the contract set, the optional actuator configuration, the controller
//! and the optional mission policy. The equivalence gate splits it back into those files.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use autonomous_systems_vv_lab::actuator::ActuatorConfig;
use autonomous_systems_vv_lab::contracts::ContractSet;
use autonomous_systems_vv_lab::controller::ControllerPolicyV1;
use autonomous_systems_vv_lab::geometry::{point_in_or_on_polygon, segment_hits_polygon};
use autonomous_systems_vv_lab::mission_analysis::MissionPolicy;
use autonomous_systems_vv_lab::model::{Bounds, Point, RunStatus, Scenario};
use autonomous_systems_vv_lab::{
    ContractOutcome, ControllerEvaluationOutcome, MissionOutcome, parse_controller_id,
    parse_scenario, run_controller_evaluation,
};
use serde::Deserialize;
use serde_json::Value;

use crate::domain::{Domain, RunError, RunOutput, json_source_sha256};
use crate::plan::sha256_hex;
use crate::seeds::{GROUND_PROTECTED, Protected};

pub const CASE_SCHEMA: &str = "vv-ground-case.v1";
/// Same input caps as `vv-lab run-m4`.
const MAX_SCENARIO_BYTES: usize = 2 * 1024 * 1024;
const MAX_CONFIG_BYTES: usize = 1024 * 1024;
const MAX_CASE_BYTES: u64 = 4 * 1024 * 1024;
/// The output cap `vv-lab run-m4` is called with by the domain host and the Python adapter.
const MAX_ARTIFACT_BYTES: u64 = 16 * 1024 * 1024;
const FILES: &[&str] = &[
    "events.json",
    "report.json",
    "mission.json",
    "verification.json",
    "m4.json",
];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Policy {
    #[serde(default)]
    stall_window_ticks: Option<u32>,
    #[serde(default)]
    min_progress_mm: Option<u32>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroundCase {
    schema: String,
    controller: String,
    scenario: Value,
    contracts: Value,
    #[serde(default)]
    actuator: Option<Value>,
    #[serde(default)]
    mission_policy: Option<Policy>,
}

/// The inputs of one run, parsed and validated exactly as `vv-lab run-m4` parses its files.
struct Prepared {
    scenario: Scenario,
    contracts: ContractSet,
    actuator: ActuatorConfig,
    controller: ControllerPolicyV1,
    policy: MissionPolicy,
    /// The texts the command line would read: scenario, contracts and actuator.
    texts: [String; 3],
    has_actuator: bool,
}

fn text(v: &Value, cap: usize, what: &str) -> Result<String, String> {
    let s = serde_json::to_string(v).map_err(|e| e.to_string())?;
    if s.len() > cap {
        return Err(format!("{what} exceeds {cap} bytes"));
    }
    Ok(s)
}

fn prepare(case: &[u8]) -> Result<Prepared, String> {
    let c: GroundCase =
        serde_json::from_slice(case).map_err(|e| format!("invalid ground case: {e}"))?;
    if c.schema != CASE_SCHEMA {
        return Err(format!("schema must be {CASE_SCHEMA}"));
    }
    let scenario_text = text(&c.scenario, MAX_SCENARIO_BYTES, "scenario")?;
    let scenario = parse_scenario(&scenario_text).map_err(|e| e.to_string())?;
    let contracts_text = text(&c.contracts, MAX_CONFIG_BYTES, "contracts")?;
    let contracts = ContractSet::from_json(&contracts_text).map_err(|e| e.to_string())?;
    let (actuator, actuator_text) = match &c.actuator {
        Some(v) => {
            let t = text(v, MAX_CONFIG_BYTES, "actuator")?;
            (ActuatorConfig::from_json(&t)?, t)
        }
        None => (ActuatorConfig::default(), String::new()),
    };
    let controller = parse_controller_id(&c.controller).map_err(|e| e.to_string())?;
    let mut policy = MissionPolicy::default();
    if let Some(p) = &c.mission_policy {
        if let Some(n) = p.stall_window_ticks {
            policy.stall_window_ticks = n;
        }
        if let Some(n) = p.min_progress_mm {
            policy.min_progress_mm = n;
        }
    }
    let policy = policy.validate().map_err(|e| e.to_string())?;
    Ok(Prepared {
        scenario,
        contracts,
        actuator,
        controller,
        policy,
        texts: [scenario_text, contracts_text, actuator_text],
        has_actuator: c.actuator.is_some(),
    })
}

type Artifacts = (ControllerEvaluationOutcome, Vec<Vec<u8>>);

/// The five artifacts, serialised as `vv-lab run-m4` serialises them.
fn artifacts(p: Prepared, seed: u64) -> Result<Artifacts, RunError> {
    let outcome = run_controller_evaluation(
        p.scenario,
        seed,
        p.controller,
        p.actuator,
        p.contracts,
        p.policy,
    )
    .map_err(|e| RunError::Simulation(e.to_string()))?;
    let ser = |r: serde_json::Result<Vec<u8>>| r.map_err(|e| RunError::Simulation(e.to_string()));
    let bytes = vec![
        ser(serde_json::to_vec(&outcome.artifact))?,
        ser(serde_json::to_vec(&outcome.artifact.expected_report))?,
        ser(serde_json::to_vec(&outcome.mission))?,
        ser(serde_json::to_vec(&outcome.verification))?,
        ser(serde_json::to_vec(&outcome.manifest))?,
    ];
    let total: u64 = bytes.iter().map(|b| b.len() as u64).sum();
    if total > MAX_ARTIFACT_BYTES {
        return Err(RunError::Simulation(format!(
            "artifacts exceed {MAX_ARTIFACT_BYTES} bytes"
        )));
    }
    Ok((outcome, bytes))
}

/// Euclidean distance in millimetres from `p` to the segment `a`-`b`.
fn point_segment_mm(p: Point, a: Point, b: Point) -> f64 {
    let (px, py) = (f64::from(p.x_mm), f64::from(p.y_mm));
    let (ax, ay) = (f64::from(a.x_mm), f64::from(a.y_mm));
    let (bx, by) = (f64::from(b.x_mm), f64::from(b.y_mm));
    let (dx, dy) = (bx - ax, by - ay);
    let len2 = dx * dx + dy * dy;
    let t = if len2 == 0.0 {
        0.0
    } else {
        (((px - ax) * dx + (py - ay) * dy) / len2).clamp(0.0, 1.0)
    };
    (px - ax - t * dx).hypot(py - ay - t * dy)
}

/// Signed clearance of the path segment `a`-`b` from the polygon. Outside, the smallest distance
/// to the boundary; two segments that do not cross are separated by an endpoint-to-segment
/// distance, so four endpoint distances per edge are enough. A segment that crosses the polygon
/// scores zero, and one with an endpoint inside scores minus that endpoint's depth.
fn segment_clearance_mm(a: Point, b: Point, polygon: &[Point]) -> f64 {
    let n = polygon.len();
    let mut d = f64::INFINITY;
    let mut depth = 0.0f64;
    for i in 0..n {
        let (c, e) = (polygon[i], polygon[(i + 1) % n]);
        d = d
            .min(point_segment_mm(a, c, e))
            .min(point_segment_mm(b, c, e))
            .min(point_segment_mm(c, a, b))
            .min(point_segment_mm(e, a, b));
    }
    for q in [a, b] {
        if point_in_or_on_polygon(q, polygon) {
            let inner = (0..n)
                .map(|i| point_segment_mm(q, polygon[i], polygon[(i + 1) % n]))
                .fold(f64::INFINITY, f64::min);
            depth = depth.max(inner);
        }
    }
    if depth > 0.0 {
        -depth
    } else if segment_hits_polygon(a, b, polygon) {
        0.0
    } else {
        d
    }
}

/// Signed distance of a point to the world bounds: positive inside.
fn bounds_clearance_mm(p: Point, b: &Bounds) -> f64 {
    let m = (i64::from(p.x_mm) - i64::from(b.min_x_mm))
        .min(i64::from(b.max_x_mm) - i64::from(p.x_mm))
        .min(i64::from(p.y_mm) - i64::from(b.min_y_mm))
        .min(i64::from(b.max_y_mm) - i64::from(p.y_mm));
    m as f64
}

fn metrics_of(o: &ControllerEvaluationOutcome) -> BTreeMap<String, f64> {
    let m = &o.manifest.metrics;
    let mut out = BTreeMap::new();
    for (k, v) in [
        ("summary.ticks", m.ticks),
        ("summary.fallback_ticks", m.fallback_ticks),
        (
            "summary.failed_safety_invariants",
            m.failed_safety_invariants,
        ),
        (
            "summary.failed_temporal_contracts",
            m.failed_temporal_contracts,
        ),
        (
            "summary.inconclusive_temporal_contracts",
            m.inconclusive_temporal_contracts,
        ),
        ("summary.movement_action_ticks", m.movement_action_ticks),
    ] {
        out.insert(k.to_string(), f64::from(v));
    }
    out.insert(
        "summary.waypoints_completed".into(),
        m.waypoints_completed as f64,
    );
    out.insert(
        "summary.waypoints_remaining".into(),
        m.waypoints_remaining as f64,
    );
    let scenario = &o.artifact.scenario;
    let path: Vec<Point> = std::iter::once(scenario.vehicle.start)
        .chain(
            o.artifact
                .expected_report
                .telemetry
                .iter()
                .map(|t| t.truth_position),
        )
        .collect();
    let zone = &scenario.restricted_zone.vertices;
    if zone.len() >= 3 {
        let clearance = path
            .windows(2)
            .map(|w| segment_clearance_mm(w[0], w[1], zone))
            .fold(f64::INFINITY, f64::min);
        if clearance.is_finite() {
            out.insert("margin.restricted_zone_mm".into(), clearance);
        }
    }
    let bounds = path
        .iter()
        .map(|&p| bounds_clearance_mm(p, &scenario.bounds))
        .fold(f64::INFINITY, f64::min);
    if bounds.is_finite() {
        out.insert("margin.world_bounds_mm".into(), bounds);
    }
    out
}

fn violations_of(o: &ControllerEvaluationOutcome) -> Vec<String> {
    let mut v: Vec<String> = o
        .artifact
        .expected_report
        .invariants
        .iter()
        .filter(|i| !i.passed)
        .map(|i| format!("invariant:{}", i.name))
        .chain(
            o.verification
                .contract_results
                .iter()
                .filter(|c| c.outcome == ContractOutcome::Fail)
                .map(|c| format!("contract:{}", c.contract_id)),
        )
        .collect();
    v.sort();
    v.dedup();
    v
}

fn outcome_name(m: MissionOutcome) -> &'static str {
    match m {
        MissionOutcome::Completed => "completed",
        MissionOutcome::Incomplete => "incomplete",
        MissionOutcome::Stalled => "stalled",
        MissionOutcome::InvalidTerminated => "invalid_terminated",
    }
}

fn read_case(case_path: &Path) -> Result<Prepared, String> {
    prepare(&crate::plan::read_capped(case_path, MAX_CASE_BYTES)?)
}

/// Ground vehicle, M4 controller evaluation: `vv-lab run-m4`.
pub struct GroundM4;

impl Domain for GroundM4 {
    fn id(&self) -> &'static str {
        "ground-m4"
    }
    fn seeded(&self) -> bool {
        true
    }
    fn protected(&self) -> &'static [Protected] {
        GROUND_PROTECTED
    }
    fn validate(&self, case: &[u8], _seed: u64) -> Result<(), String> {
        let p = prepare(case)?;
        p.scenario.validate().map_err(|e| e.to_string())?;
        p.actuator.validate(p.scenario.steps)?;
        p.contracts.validate().map_err(|e| e.to_string())?;
        Ok(())
    }
    fn run(&self, case: &[u8], seed: u64) -> Result<RunOutput, RunError> {
        let p = prepare(case).map_err(RunError::Input)?;
        let (o, bytes) = artifacts(p, seed)?;
        let m = &o.manifest.metrics;
        // Safety is the invariant verdict plus every temporal contract; a failed contract is a
        // safety failure. The mission outcome stays separate, as in the root crate.
        let invariants_pass =
            m.safety_status == RunStatus::Passed && m.temporal_status != ContractOutcome::Fail;
        let completed = m.mission_outcome == MissionOutcome::Completed;
        Ok(RunOutput {
            trace_sha256: sha256_hex(&bytes[0]),
            verification_sha256: Some(sha256_hex(&bytes[3])),
            outcome: outcome_name(m.mission_outcome).to_string(),
            mission_success: Some(completed),
            requirements_pass: Some(completed),
            invariants_pass: Some(invariants_pass),
            metrics: metrics_of(&o),
            violations: violations_of(&o),
        })
    }
    fn write(&self, case_path: &Path, seed: u64, out: &Path) -> Result<(), String> {
        let p = read_case(case_path)?;
        let (_, bytes) = artifacts(p, seed).map_err(|e| e.to_string())?;
        if out.exists() {
            return Err(format!("{} already exists", out.display()));
        }
        fs::create_dir_all(out).map_err(|e| format!("{}: {e}", out.display()))?;
        for (name, b) in FILES.iter().zip(bytes) {
            crate::engine::write_new(&out.join(name), &b)?;
        }
        Ok(())
    }
    fn cli_args(
        &self,
        case_path: &Path,
        seed: u64,
        out: &Path,
        staging: &Path,
    ) -> Result<Vec<String>, String> {
        let p = read_case(case_path)?;
        fs::create_dir_all(staging).map_err(|e| format!("{}: {e}", staging.display()))?;
        let path = |name: &str| staging.join(name).display().to_string();
        crate::engine::write_new(&staging.join("scenario.json"), p.texts[0].as_bytes())?;
        crate::engine::write_new(&staging.join("contracts.json"), p.texts[1].as_bytes())?;
        let controller = match p.controller {
            ControllerPolicyV1::DominantAxis => "dominant_axis",
            ControllerPolicyV1::XFirst => "x_first",
        };
        let mut args = vec![
            "run-m4".to_string(),
            path("scenario.json"),
            "--seed".into(),
            seed.to_string(),
            "--controller".into(),
            controller.into(),
            "--contracts".into(),
            path("contracts.json"),
        ];
        if p.has_actuator {
            crate::engine::write_new(&staging.join("actuator.json"), p.texts[2].as_bytes())?;
            args.extend(["--actuator".into(), path("actuator.json")]);
        }
        args.extend([
            "--output".into(),
            out.display().to_string(),
            "--max-output-bytes".into(),
            MAX_ARTIFACT_BYTES.to_string(),
            "--stall-window-ticks".into(),
            p.policy.stall_window_ticks.to_string(),
            "--min-progress-mm".into(),
            p.policy.min_progress_mm.to_string(),
        ]);
        Ok(args)
    }
    fn files(&self) -> &'static [&'static str] {
        FILES
    }
    fn source_sha256(&self) -> String {
        autonomous_systems_vv_lab::source_sha256()
    }
    fn has_verdicts(&self) -> bool {
        true
    }
    fn trace_file(&self) -> &'static str {
        "events.json"
    }
    fn verification_file(&self) -> Option<&'static str> {
        Some("verification.json")
    }
    fn case_copy_file(&self) -> Option<&'static str> {
        None
    }
    fn cli_replay_args(&self, dir: &Path) -> Vec<String> {
        vec![
            "replay-m4".into(),
            dir.join("m4.json").display().to_string(),
        ]
    }
    fn written_source_sha256(&self, dir: &Path) -> Option<String> {
        json_source_sha256(&dir.join("m4.json"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(x: i32, y: i32) -> Point {
        Point { x_mm: x, y_mm: y }
    }

    #[test]
    fn segment_clearance_is_signed() {
        let square = [p(0, 0), p(100, 0), p(100, 100), p(0, 100)];
        assert_eq!(segment_clearance_mm(p(-50, 50), p(-10, 50), &square), 10.0);
        // The nearest point of this diagonal to the corner (100, 100) is its midpoint (140, 140).
        let diag = segment_clearance_mm(p(150, 130), p(130, 150), &square);
        assert!((diag - 40.0 * 2f64.sqrt()).abs() < 1e-9);
        // Crossing the polygon without an endpoint inside scores zero.
        assert_eq!(segment_clearance_mm(p(-50, 50), p(150, 50), &square), 0.0);
        // An endpoint inside scores minus its depth.
        assert_eq!(segment_clearance_mm(p(-50, 50), p(20, 50), &square), -20.0);
    }

    #[test]
    fn bounds_clearance_is_positive_inside() {
        let b = Bounds {
            min_x_mm: 0,
            max_x_mm: 1000,
            min_y_mm: 0,
            max_y_mm: 1000,
        };
        assert_eq!(bounds_clearance_mm(p(100, 500), &b), 100.0);
        assert_eq!(bounds_clearance_mm(p(-5, 500), &b), -5.0);
    }
}
