//! Maps the native artifacts of `vv-rocket` (trace.json, verification.json, run.json, case.json) to
//! the normalised run record. Nothing is invented here: every channel is a field of the trace, a
//! difference of two of them, or a constant of the case; every verdict is one of the verifier.

use std::fs;
use std::path::Path;

use serde_json::{Value, json};
use vv_platform::contract::*;

use crate::catalog::{DOMAIN, requirements};

type Get = fn(&Value) -> Option<f64>;

struct Def {
    id: &'static str,
    label: &'static str,
    unit: &'static str,
    group: &'static str,
    kind: &'static str,
    get: Get,
}

const TIMEBASE: &str = "trace";

fn num(s: &Value, path: &str) -> Option<f64> {
    s.pointer(path).and_then(Value::as_f64)
}

fn flag(s: &Value, path: &str) -> Option<f64> {
    s.pointer(path)
        .and_then(Value::as_bool)
        .map(|b| if b { 1.0 } else { 0.0 })
}

fn code(s: &Value, path: &str, names: &[&str]) -> Option<f64> {
    let text = s.pointer(path)?.as_str()?;
    names.iter().position(|n| *n == text).map(|i| i as f64)
}

fn diff(s: &Value, a: &str, b: &str) -> Option<f64> {
    Some(num(s, a)? - num(s, b)?)
}

fn hypot2(s: &Value, ax: &str, ay: &str, bx: &str, by: &str) -> Option<f64> {
    Some(diff(s, ax, bx)?.hypot(diff(s, ay, by)?))
}

const ENGINE: [&str; 4] = ["off", "on", "cut", "flameout"];

#[rustfmt::skip]
fn defs() -> Vec<Def> {
    let mut v: Vec<Def> = Vec::new();
    macro_rules! d {
        ($id:expr, $label:expr, $unit:expr, $group:expr, $kind:expr, $get:expr) => {
            v.push(Def { id: $id, label: $label, unit: $unit, group: $group, kind: $kind, get: $get })
        };
    }
    // Truth: the state of the simulation, never given to the controller.
    d!("pos_x", "Centre of mass x (east)", "m", "Position", "truth", |s| num(s, "/truth/position_m/0"));
    d!("pos_y", "Centre of mass y (north)", "m", "Position", "truth", |s| num(s, "/truth/position_m/1"));
    d!("pos_z", "Centre of mass z (up)", "m", "Position", "truth", |s| num(s, "/truth/position_m/2"));
    d!("base_x", "Nozzle plane x (east)", "m", "Position", "truth", |s| num(s, "/truth/base_position_m/0"));
    d!("base_y", "Nozzle plane y (north)", "m", "Position", "truth", |s| num(s, "/truth/base_position_m/1"));
    d!("altitude", "Altitude of the nozzle plane", "m", "Position", "truth", |s| num(s, "/truth/base_position_m/2"));
    d!("pad_distance", "Distance of the nozzle plane from the pad centre", "m", "Position", "metric", |s| {
        Some(num(s, "/truth/base_position_m/0")?.hypot(num(s, "/truth/base_position_m/1")?))
    });
    d!("vel_x", "Velocity x (east)", "m/s", "Velocity", "truth", |s| num(s, "/truth/velocity_mps/0"));
    d!("vel_y", "Velocity y (north)", "m/s", "Velocity", "truth", |s| num(s, "/truth/velocity_mps/1"));
    d!("vel_z", "Velocity z (up)", "m/s", "Velocity", "truth", |s| num(s, "/truth/velocity_mps/2"));
    d!("vel_h", "Horizontal speed", "m/s", "Velocity", "truth", |s| {
        Some(num(s, "/truth/velocity_mps/0")?.hypot(num(s, "/truth/velocity_mps/1")?))
    });
    d!("speed", "Speed", "m/s", "Velocity", "truth", |s| {
        let (x, y, z) = (num(s, "/truth/velocity_mps/0")?, num(s, "/truth/velocity_mps/1")?, num(s, "/truth/velocity_mps/2")?);
        Some((x * x + y * y + z * z).sqrt())
    });
    d!("q_w", "Attitude quaternion w", "", "Attitude", "truth", |s| num(s, "/truth/attitude/0"));
    d!("q_x", "Attitude quaternion x", "", "Attitude", "truth", |s| num(s, "/truth/attitude/1"));
    d!("q_y", "Attitude quaternion y", "", "Attitude", "truth", |s| num(s, "/truth/attitude/2"));
    d!("q_z", "Attitude quaternion z", "", "Attitude", "truth", |s| num(s, "/truth/attitude/3"));
    d!("tilt_deg", "Tilt of the body axis from vertical", "deg", "Attitude", "truth", |s| {
        Some(num(s, "/truth/tilt_cos")?.clamp(-1.0, 1.0).acos().to_degrees())
    });
    d!("rate_x", "Angular rate x_B (roll)", "rad/s", "Attitude", "truth", |s| num(s, "/truth/angular_velocity_radps/0"));
    d!("rate_y", "Angular rate y_B", "rad/s", "Attitude", "truth", |s| num(s, "/truth/angular_velocity_radps/1"));
    d!("rate_z", "Angular rate z_B", "rad/s", "Attitude", "truth", |s| num(s, "/truth/angular_velocity_radps/2"));
    d!("propellant_kg", "Propellant mass", "kg", "Mass", "truth", |s| num(s, "/truth/propellant_kg"));
    d!("mass_kg", "Total mass", "kg", "Mass", "truth", |s| num(s, "/truth/mass_kg"));
    // Controller output and what the actuator really did.
    d!("cmd_throttle", "Throttle command", "", "Propulsion", "command", |s| num(s, "/command/throttle"));
    d!("cmd_gimbal_y", "Gimbal command, tangent about y_B", "tan", "Propulsion", "command", |s| num(s, "/command/gimbal_tan/0"));
    d!("cmd_gimbal_z", "Gimbal command, tangent about z_B", "tan", "Propulsion", "command", |s| num(s, "/command/gimbal_tan/1"));
    d!("act_throttle", "Throttle applied", "", "Propulsion", "truth", |s| num(s, "/applied/throttle"));
    d!("act_gimbal_y", "Gimbal applied, tangent about y_B", "tan", "Propulsion", "truth", |s| num(s, "/applied/gimbal_tan/0"));
    d!("act_gimbal_z", "Gimbal applied, tangent about z_B", "tan", "Propulsion", "truth", |s| num(s, "/applied/gimbal_tan/1"));
    d!("thrust_n", "Thrust", "N", "Propulsion", "truth", |s| num(s, "/applied/thrust_n"));
    d!("engine_state", "Engine state (0 off, 1 on, 2 cut, 3 flameout)", "", "Propulsion", "truth", |s| code(s, "/applied/engine", &ENGINE));
    // Sensor observations of the latest control cycle; empty where the sensor delivers nothing.
    d!("obs_altimeter", "Radar altimeter reading", "m", "Radar altimeter", "observation", |s| num(s, "/observation/altimeter_m"));
    d!("obs_gnss_x", "GNSS position x", "m", "GNSS", "observation", |s| num(s, "/observation/gnss_position_m/0"));
    d!("obs_gnss_y", "GNSS position y", "m", "GNSS", "observation", |s| num(s, "/observation/gnss_position_m/1"));
    d!("obs_gnss_z", "GNSS position z", "m", "GNSS", "observation", |s| num(s, "/observation/gnss_position_m/2"));
    d!("obs_gnss_vx", "GNSS velocity x", "m/s", "GNSS", "observation", |s| num(s, "/observation/gnss_velocity_mps/0"));
    d!("obs_gnss_vy", "GNSS velocity y", "m/s", "GNSS", "observation", |s| num(s, "/observation/gnss_velocity_mps/1"));
    d!("obs_gnss_vz", "GNSS velocity z", "m/s", "GNSS", "observation", |s| num(s, "/observation/gnss_velocity_mps/2"));
    d!("obs_imu_fx", "IMU specific force along x_B", "m/s²", "IMU", "observation", |s| num(s, "/observation/imu/specific_force_mps2/0"));
    // The controller's own estimate of the centre of mass.
    d!("est_x", "Estimated position x", "m", "Estimate", "estimate", |s| num(s, "/estimate/position_m/0"));
    d!("est_y", "Estimated position y", "m", "Estimate", "estimate", |s| num(s, "/estimate/position_m/1"));
    d!("est_z", "Estimated position z", "m", "Estimate", "estimate", |s| num(s, "/estimate/position_m/2"));
    d!("est_vx", "Estimated velocity x", "m/s", "Estimate", "estimate", |s| num(s, "/estimate/velocity_mps/0"));
    d!("est_vy", "Estimated velocity y", "m/s", "Estimate", "estimate", |s| num(s, "/estimate/velocity_mps/1"));
    d!("est_vz", "Estimated velocity z", "m/s", "Estimate", "estimate", |s| num(s, "/estimate/velocity_mps/2"));
    d!("altimeter_rejected", "Controller rejects the altimeter (1 yes)", "", "Estimate", "estimate", |s| flag(s, "/estimate/altimeter_rejected"));
    d!("sensor_disagreement", "Controller reports sensor disagreement (1 yes)", "", "Estimate", "estimate", |s| flag(s, "/estimate/sensor_disagreement"));
    d!("ascent_abort", "Controller reports ascent abort (1 yes)", "", "Estimate", "estimate", |s| flag(s, "/estimate/ascent_abort"));
    // Estimation error against the truth.
    d!("err_z", "Vertical position error (estimate minus truth)", "m", "Estimation error", "metric", |s| diff(s, "/estimate/position_m/2", "/truth/position_m/2"));
    d!("err_h", "Horizontal position error", "m", "Estimation error", "metric", |s| {
        hypot2(s, "/estimate/position_m/0", "/estimate/position_m/1", "/truth/position_m/0", "/truth/position_m/1")
    });
    d!("err_vz", "Vertical velocity error (estimate minus truth)", "m/s", "Estimation error", "metric", |s| diff(s, "/estimate/velocity_mps/2", "/truth/velocity_mps/2"));
    d!("err_vh", "Horizontal velocity error", "m/s", "Estimation error", "metric", |s| {
        hypot2(s, "/estimate/velocity_mps/0", "/estimate/velocity_mps/1", "/truth/velocity_mps/0", "/truth/velocity_mps/1")
    });
    d!("active_faults", "Injected faults active", "", "Faults", "metric", |s| s.pointer("/active_faults").and_then(Value::as_array).map(|a| a.len() as f64));
    v
}

/// Limits drawn as constants over the run; they come from the case, not from the trace.
const LIMITS: [(&str, &str, &str, &str); 1] = [(
    "tilt_limit_deg",
    "Tilt envelope limit while thrusting (S1)",
    "deg",
    "Attitude",
)];

/// Every channel the host can produce, for the catalog. A record carries the subset that has values.
pub fn channel_specs() -> Vec<ChannelSpec> {
    let spec = |id: &str, label: &str, unit: &str, group: &str, kind: &str| ChannelSpec {
        id: id.into(),
        label: label.into(),
        unit: unit.into(),
        group: group.into(),
        kind: kind.into(),
    };
    let mut out: Vec<ChannelSpec> = defs()
        .iter()
        .map(|d| spec(d.id, d.label, d.unit, d.group, d.kind))
        .collect();
    out.extend(
        LIMITS
            .iter()
            .map(|(id, label, unit, group)| spec(id, label, unit, group, "limit")),
    );
    out
}

fn text<'a>(v: &'a Value, path: &str) -> &'a str {
    v.pointer(path).and_then(Value::as_str).unwrap_or("")
}

fn fmt(value: f64) -> String {
    format!("{value:.2}")
}

fn label_of(id: &str) -> String {
    requirements()
        .into_iter()
        .find(|r| r.id == id)
        .map(|r| r.label)
        .unwrap_or_else(|| id.to_string())
}

fn read_json(dir: &Path, name: &str) -> Result<Value, String> {
    let bytes = fs::read(dir.join(name)).map_err(|e| format!("{name}: {e}"))?;
    serde_json::from_slice(&bytes).map_err(|e| format!("{name}: {e}"))
}

fn causes(item: &Value) -> Vec<String> {
    item.get("cause")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(|c| c.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default()
}

fn with_cause(sentence: String, cause: &[String]) -> String {
    if cause.is_empty() {
        sentence
    } else {
        format!(
            "{sentence} Injected faults active then: {}.",
            cause.join(", ")
        )
    }
}

fn event(t: f64, kind: &str, label: String, severity: &str, source: &str, detail: Value) -> Event {
    Event {
        t,
        kind: kind.into(),
        label,
        severity: severity.into(),
        source: source.into(),
        detail,
    }
}

struct Results {
    requirements: Vec<RequirementResult>,
    failed_invariants: Vec<String>,
}

fn requirement_results(verification: &Value) -> Results {
    let mut out = Vec::new();
    let mut failed_invariants = Vec::new();
    for r in verification["requirements"]
        .as_array()
        .into_iter()
        .flatten()
    {
        let id = text(r, "/id").to_string();
        let label = label_of(&id);
        let evaluated = r["evaluated"].as_bool().unwrap_or(false);
        let pass = r["pass"].as_bool().unwrap_or(false);
        let (expected, observed) = (
            text(r, "/expected").to_string(),
            text(r, "/observed").to_string(),
        );
        let cause = causes(r);
        let (status, explanation) = if !evaluated {
            ("not_evaluated", "The stage never touched the ground, so this requirement could not be evaluated and counts as not met.".to_string())
        } else if pass {
            (
                "pass",
                format!("{label}: {observed} against a requirement of {expected}."),
            )
        } else {
            (
                "fail",
                with_cause(
                    format!("{label} failed: {observed} where {expected} was required."),
                    &cause,
                ),
            )
        };
        out.push(RequirementResult {
            id,
            label,
            category: "requirement".into(),
            status: status.into(),
            expected,
            observed,
            t: r["t_s"].as_f64(),
            explanation,
        });
    }
    for i in verification["invariants"].as_array().into_iter().flatten() {
        let id = text(i, "/id").to_string();
        let label = label_of(&id);
        let evaluated = i["evaluated"].as_bool().unwrap_or(false);
        let pass = i["pass"].as_bool().unwrap_or(false);
        let unit = text(i, "/unit");
        let limit = i["limit"].as_f64().unwrap_or(f64::NAN);
        let relation = if id.starts_with("S1") { ">=" } else { "<=" };
        let first = i.get("first_failure").filter(|f| f.is_object());
        let (status, expected, observed, t, explanation) = match (evaluated, pass, first) {
            (false, _, _) => (
                "not_evaluated",
                format!("{relation} {limit} {unit}"),
                "not evaluated".to_string(),
                None,
                "The stage never touched the ground, so this invariant could not be evaluated."
                    .to_string(),
            ),
            (true, true, _) => {
                let worst = i["worst_value"]
                    .as_f64()
                    .map(|w| format!("{w:.6} {unit}"))
                    .unwrap_or_else(|| "no sample".into());
                (
                    "pass",
                    format!("{relation} {limit} {unit}"),
                    worst.clone(),
                    None,
                    format!(
                        "{label}: the worst value was {worst} against a limit of {relation} {limit} {unit}; it held at every step."
                    ),
                )
            }
            (true, false, first) => {
                let expected = first
                    .map(|f| text(f, "/expected").to_string())
                    .unwrap_or_else(|| format!("{relation} {limit} {unit}"));
                let observed = first
                    .map(|f| text(f, "/observed").to_string())
                    .unwrap_or_default();
                let t = first.and_then(|f| f["t_s"].as_f64());
                let cause = first.map(causes).unwrap_or_default();
                let when = t
                    .map(|t| format!(" first at {} s", fmt(t)))
                    .unwrap_or_default();
                let count = i["failure_count"].as_u64().unwrap_or(0);
                (
                    "fail",
                    expected.clone(),
                    observed.clone(),
                    t,
                    with_cause(
                        format!(
                            "{label} failed{when}: {observed} where {expected} was required; {count} steps failed in total."
                        ),
                        &cause,
                    ),
                )
            }
        };
        if evaluated && !pass {
            failed_invariants.push(id.clone());
        }
        out.push(RequirementResult {
            id,
            label,
            category: "invariant".into(),
            status: status.into(),
            expected,
            observed,
            t,
            explanation,
        });
    }
    Results {
        requirements: out,
        failed_invariants,
    }
}

fn metric(id: &str, label: &str, value: Option<f64>, unit: &str, group: &str) -> Metric {
    Metric {
        id: id.into(),
        label: label.into(),
        value,
        unit: unit.into(),
        group: group.into(),
    }
}

fn find<'a>(items: &'a Value, id_prefix: &str) -> Option<&'a Value> {
    items
        .as_array()?
        .iter()
        .find(|i| text(i, "/id").starts_with(id_prefix))
}

fn metrics(verification: &Value, summary: &Value, max_sampled_tilt: Option<f64>) -> Vec<Metric> {
    let req = |p: &str| find(&verification["requirements"], p).and_then(|r| r["value"].as_f64());
    let inv =
        |p: &str| find(&verification["invariants"], p).and_then(|r| r["worst_value"].as_f64());
    vec![
        metric(
            "touchdown_t_s",
            "Time of touchdown",
            summary["touchdown_t_s"].as_f64(),
            "s",
            "Touchdown",
        ),
        metric(
            "touchdown_vertical_speed",
            "Vertical speed at contact",
            req("R1"),
            "m/s",
            "Touchdown",
        ),
        metric(
            "touchdown_horizontal_speed",
            "Horizontal speed at contact",
            req("R2"),
            "m/s",
            "Touchdown",
        ),
        metric(
            "touchdown_tilt_deg",
            "Tilt at contact",
            req("R3").map(|c| c.clamp(-1.0, 1.0).acos().to_degrees()),
            "deg",
            "Touchdown",
        ),
        metric(
            "touchdown_angular_rate",
            "Angular rate at contact",
            req("R4"),
            "rad/s",
            "Touchdown",
        ),
        metric(
            "touchdown_pad_distance",
            "Distance from the pad centre at contact",
            req("R5"),
            "m",
            "Touchdown",
        ),
        metric(
            "propellant_used_kg",
            "Propellant used",
            summary["propellant_used_kg"].as_f64(),
            "kg",
            "Propellant",
        ),
        metric(
            "propellant_remaining_kg",
            "Propellant remaining",
            summary["propellant_remaining_kg"].as_f64(),
            "kg",
            "Propellant",
        ),
        metric(
            "ignition_t_s",
            "Time of ignition",
            summary["ignition_t_s"].as_f64(),
            "s",
            "Flight",
        ),
        metric(
            "max_tilt_thrusting_deg",
            "Largest tilt while thrusting",
            inv("S1").map(|c| c.clamp(-1.0, 1.0).acos().to_degrees()),
            "deg",
            "Flight",
        ),
        metric(
            "max_tilt_sampled_deg",
            "Largest tilt over the recorded samples",
            max_sampled_tilt,
            "deg",
            "Flight",
        ),
        metric(
            "peak_axial_load_g0",
            "Peak axial load",
            inv("S3"),
            "g0",
            "Flight",
        ),
        metric(
            "climb_under_power_m",
            "Largest climb under power",
            inv("S5"),
            "m",
            "Flight",
        ),
    ]
}

fn events(trace: &Value, verification: &Value) -> Vec<Event> {
    let mut out = Vec::new();
    let controller_event = |t: f64, kind: &str, label: String, severity: &str, detail: Value| {
        event(t, kind, label, severity, "controller", detail)
    };
    for e in trace["events"].as_array().into_iter().flatten() {
        let t = e["t_s"].as_f64().unwrap_or(0.0);
        let detail = e["detail"].clone();
        match text(e, "/kind") {
            "ignition" => out.push(event(
                t,
                "ignition",
                "Engine ignition".into(),
                "info",
                "truth",
                detail,
            )),
            "cutoff" => out.push(event(
                t,
                "cutoff",
                "Engine cutoff".into(),
                "info",
                "truth",
                detail,
            )),
            "flameout" => out.push(event(
                t,
                "flameout",
                "Flameout: the propellant ran out".into(),
                "warning",
                "truth",
                detail,
            )),
            "touchdown" => out.push(event(
                t,
                "touchdown",
                "Touchdown: the nozzle plane reached the ground".into(),
                "info",
                "truth",
                detail,
            )),
            "fault_start" => out.push(event(
                t,
                "fault_start",
                format!("Fault starts: {}", text(e, "/detail/fault")),
                "fault",
                "fault",
                detail,
            )),
            "fault_end" => out.push(event(
                t,
                "fault_end",
                format!("Fault ends: {}", text(e, "/detail/fault")),
                "fault",
                "fault",
                detail,
            )),
            "ascent_abort" => out.push(controller_event(
                t,
                "ascent_abort",
                "Controller aborts: the stage climbs under power".into(),
                "warning",
                detail,
            )),
            _ => {}
        }
    }
    let flags = &verification["controller_flags"];
    for (key, kind, label) in [
        (
            "sensor_disagreement_first",
            "sensor_disagreement",
            "Controller first reports sensor disagreement",
        ),
        (
            "altimeter_rejected_first",
            "altimeter_rejected",
            "Controller first rejects the altimeter",
        ),
    ] {
        if let Some(t) = flags[key]["t_s"].as_f64() {
            out.push(controller_event(
                t,
                kind,
                label.into(),
                "detection",
                json!({"note": "controller-reported; not used for any verdict"}),
            ));
        }
    }
    let final_t = trace["summary"]["final_time_s"].as_f64().unwrap_or(0.0);
    for i in verification["invariants"].as_array().into_iter().flatten() {
        if let Some(first) = i.get("first_failure").filter(|f| f.is_object()) {
            let id = text(i, "/id");
            out.push(event(
                first["t_s"].as_f64().unwrap_or(0.0),
                "invariant_violation",
                format!(
                    "{} first violated: {} where {} was required",
                    label_of(id),
                    text(first, "/observed"),
                    text(first, "/expected")
                ),
                "violation",
                "verifier",
                json!({"id": id, "failure_count": i["failure_count"], "cause": first["cause"]}),
            ));
        }
    }
    for r in verification["requirements"]
        .as_array()
        .into_iter()
        .flatten()
    {
        if r["pass"].as_bool() == Some(false) {
            let id = text(r, "/id");
            match r["t_s"].as_f64() {
                Some(t) => out.push(event(
                    t,
                    "requirement_violation",
                    format!(
                        "{} failed at contact: {} where {} was required",
                        label_of(id),
                        text(r, "/observed"),
                        text(r, "/expected")
                    ),
                    "violation",
                    "verifier",
                    json!({"id": id, "cause": r["cause"]}),
                )),
                None => {
                    if id.starts_with("R1") {
                        out.push(event(final_t, "no_contact", format!("The stage never reached the ground in {} s; no requirement could be evaluated", fmt(final_t)), "violation", "verifier", json!({"id": id})));
                    }
                }
            }
        }
    }
    out.sort_by(|a, b| a.t.total_cmp(&b.t));
    out
}

fn outcome_of(
    verification: &Value,
    summary: &Value,
    results: &Results,
    last_altitude: Option<f64>,
) -> Outcome {
    let code = text(verification, "/outcome").to_string();
    let value = |p: &str| {
        find(&verification["requirements"], p)
            .and_then(|r| r["value"].as_f64())
            .unwrap_or(f64::NAN)
    };
    match code.as_str() {
        "landed" => Outcome {
            label: "Landed".into(),
            status: "success".into(),
            explanation: format!(
                "The stage touched down at {} s, {} m from the pad centre, descending at {} m/s with {} m/s sideways. All six mission requirements were met.",
                fmt(summary["touchdown_t_s"].as_f64().unwrap_or(f64::NAN)),
                fmt(value("R5")),
                fmt(value("R1")),
                fmt(value("R2")),
            ),
            code,
        },
        "hard_landing" => {
            let failed: Vec<String> = verification["requirements"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|r| r["pass"].as_bool() == Some(false))
                .map(|r| {
                    format!(
                        "{} {} (required {})",
                        label_of(text(r, "/id")),
                        text(r, "/observed"),
                        text(r, "/expected")
                    )
                })
                .collect();
            let s5 = results
                .failed_invariants
                .iter()
                .any(|i| i.starts_with("S5"));
            Outcome {
                label: "Touched down, requirements not met".into(),
                status: "failure".into(),
                explanation: format!(
                    "The stage reached the ground at {} s but did not meet the mission requirements: {}.{}",
                    fmt(summary["touchdown_t_s"].as_f64().unwrap_or(f64::NAN)),
                    if failed.is_empty() {
                        "none of the requirements failed, but the landing is not counted"
                            .to_string()
                    } else {
                        failed.join("; ")
                    },
                    if s5 && failed.is_empty() {
                        " It reached contact by climbing under power (S5), which is not a landing."
                    } else {
                        ""
                    },
                ),
                code,
            }
        }
        _ => Outcome {
            label: "No contact".into(),
            status: "failure".into(),
            explanation: format!(
                "The stage did not reach the ground within the {} s of the simulation, so no mission requirement could be evaluated. The nozzle plane was {} m above the ground at the end.",
                fmt(summary["final_time_s"].as_f64().unwrap_or(f64::NAN)),
                last_altitude.map(fmt).unwrap_or_else(|| "?".into()),
            ),
            code,
        },
    }
}

fn safety_of(verification: &Value, results: &Results) -> Safety {
    let unsafe_run = !results.failed_invariants.is_empty();
    let explanation = if unsafe_run {
        let first: Vec<String> = verification["invariants"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|i| {
                i["pass"].as_bool() == Some(false) && i["evaluated"].as_bool() == Some(true)
            })
            .map(|i| {
                let f = &i["first_failure"];
                format!(
                    "{} first at {} s ({} where {} was required)",
                    label_of(text(i, "/id")),
                    fmt(f["t_s"].as_f64().unwrap_or(f64::NAN)),
                    text(f, "/observed"),
                    text(f, "/expected")
                )
            })
            .collect();
        format!("Safety invariants failed: {}.", first.join("; "))
    } else {
        "All five safety invariants (S1 to S5) held on the true state.".to_string()
    };
    Safety {
        status: if unsafe_run { "unsafe" } else { "safe" }.into(),
        class: None,
        explanation,
    }
}

fn scene(
    case: &Value,
    samples: &[Value],
    summary: &Value,
    request: &RunRequest,
    verification: &Value,
) -> Value {
    let first = samples.first();
    let vec3 =
        |v: Option<&Value>, p: &str| v.and_then(|s| s.pointer(p)).cloned().unwrap_or(Value::Null);
    let touchdown = verification["touchdown"].as_object().map(|_| {
        json!({
            "t": verification["touchdown"]["t_s"],
            "nozzle_position_m": verification["touchdown"]["truth"]["base_position_m"],
            "centre_of_mass_position_m": verification["touchdown"]["truth"]["position_m"],
        })
    });
    json!({
        "kind": "rocket-3d",
        "units": "m",
        "frame": {
            "description": "Local flat non-rotating frame with the origin at the centre of the pad on the ground.",
            "up_axis": "z",
            "axes": {"x": "east", "y": "north", "z": "up"},
        },
        "pad": {
            "centre_m": case["requirements"]["pad_position_m"],
            "landing_radius_m": case["requirements"]["r5_position_m"],
            "keep_out_radius_m": case["requirements"]["s2_keep_out_m"],
        },
        "initial": {
            "position_m": vec3(first, "/truth/position_m"),
            "velocity_mps": vec3(first, "/truth/velocity_mps"),
            "nozzle_altitude_m": vec3(first, "/truth/base_position_m/2"),
            "nominal_position_m": case["initial"]["position_m"],
            "note": "The seed disperses the nominal initial state.",
        },
        "touchdown": touchdown,
        "vehicle": {
            "dry_mass_kg": case["vehicle"]["dry_mass_kg"],
            "propellant_mass_kg": case["vehicle"]["propellant_mass_kg"],
            "dry_cm_station_m": case["vehicle"]["dry_cm_station_m"],
            "propellant_cm_station_m": case["vehicle"]["propellant_cm_station_m"],
            "body_axis": "x_B points from the nozzle to the nose; it points up at the start. Stations are measured from the nozzle exit plane along x_B. The model has no vehicle length.",
            "attitude": "Unit quaternion [w, x, y, z], scalar first, mapping body components to inertial ones.",
            "position_is": "pos_x, pos_y and pos_z are the centre of mass; base_x, base_y and altitude are the nozzle exit plane, which touches the ground.",
        },
        "channels": {
            "timebase": TIMEBASE,
            "position": ["pos_x", "pos_y", "pos_z"],
            "nozzle_position": ["base_x", "base_y", "altitude"],
            "attitude": ["q_w", "q_x", "q_y", "q_z"],
            "thrust": "thrust_n",
            "engine_state": "engine_state",
            "gimbal": ["act_gimbal_y", "act_gimbal_z"],
        },
        "fault_windows": request.faults.iter().map(|f| json!({"kind": f.kind, "start": f.start, "end": f.end, "magnitude": f.magnitude})).collect::<Vec<_>>(),
        "end_reason": summary["end_reason"],
        "sample_interval_s": 0.1,
    })
}

pub fn build(request: &RunRequest, out: &Path) -> Result<RunRecord, String> {
    let trace = read_json(out, "trace.json")?;
    let verification = read_json(out, "verification.json")?;
    let case = read_json(out, "case.json")?;
    let samples: Vec<Value> = trace["samples"].as_array().cloned().unwrap_or_default();
    if samples.is_empty() {
        return Err("the trace has no samples".into());
    }
    let summary = trace["summary"].clone();

    let times: Vec<f64> = samples.iter().filter_map(|s| s["t_s"].as_f64()).collect();
    if times.len() != samples.len() {
        return Err("a trace sample has no time".into());
    }
    let mut channels = Vec::new();
    for d in defs() {
        let values: Vec<Option<f64>> = samples.iter().map(d.get).collect();
        if values.iter().any(Option::is_some) {
            channels.push(Channel {
                id: d.id.into(),
                label: d.label.into(),
                unit: d.unit.into(),
                group: d.group.into(),
                kind: d.kind.into(),
                timebase: TIMEBASE.into(),
                values,
            });
        }
    }
    let mut constant = |id: &str, value: Option<f64>| {
        if let (Some(value), Some((_, label, unit, group))) =
            (value, LIMITS.iter().find(|l| l.0 == id))
        {
            channels.push(Channel {
                id: id.into(),
                label: (*label).into(),
                unit: (*unit).into(),
                group: (*group).into(),
                kind: "limit".into(),
                timebase: TIMEBASE.into(),
                values: vec![Some(value); times.len()],
            });
        }
    };
    constant(
        "tilt_limit_deg",
        num(&case, "/requirements/s1_tilt_cos_min").map(|c| c.clamp(-1.0, 1.0).acos().to_degrees()),
    );

    let results = requirement_results(&verification);
    let max_sampled_tilt = channels
        .iter()
        .find(|c| c.id == "tilt_deg")
        .and_then(|c| c.values.iter().flatten().copied().reduce(f64::max));
    let last_altitude = channels
        .iter()
        .find(|c| c.id == "altitude")
        .and_then(|c| c.values.last().copied().flatten());
    let outcome = outcome_of(&verification, &summary, &results, last_altitude);
    let safety = safety_of(&verification, &results);

    let mut notes = vec![
        "Idealised demonstrator: not flight software and not validated against flight data. Requirements, dispersions and sensor noise are assumed values.".to_string(),
        "No contact dynamics: touchdown is the instant the nozzle exit plane reaches the ground, so speeds at contact are those of that instant and not of a landing-gear model.".to_string(),
        "The trace is sampled every 0.1 s (10 steps of 0.01 s); the touchdown sample is interpolated to the instant of contact. Verdicts are computed on every step, not on the samples.".to_string(),
        "Sensor channels show the latest observation of the control cycle; they are empty while a sensor delivers nothing.".to_string(),
    ];
    if !request.parameters.is_empty() {
        let changed: Vec<String> = request
            .parameters
            .iter()
            .filter(|(id, v)| crate::catalog::parameter_default(id) != Some(**v))
            .map(|(id, v)| format!("{id} = {v}"))
            .collect();
        if !changed.is_empty() {
            notes.push(format!("Controller tuning differs from the pre-registered configuration: {}. The results are exploratory.", changed.join(", ")));
        }
    }

    let reproduce = vec![
        format!(
            "cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- land case.json --seed {} --output <dir>",
            request.seed
        ),
        "cargo run --release --manifest-path crates/vv-rocket/Cargo.toml -- replay <dir>"
            .to_string(),
    ];
    let record = RunRecord {
        schema: RECORD_SCHEMA.into(),
        domain: DomainRef {
            id: DOMAIN.into(),
            version: env!("CARGO_PKG_VERSION").into(),
            contract: format!("{CONTRACT_NAME}/{CONTRACT_MAJOR}.{CONTRACT_MINOR}"),
        },
        request: request.clone(),
        provenance: Provenance {
            source_sha256: vv_rocket::source_sha256(),
            simulator: "vv-rocket".into(),
            artifacts: Vec::new(),
            reproduce,
        },
        model_validity: crate::manifest().model_validity,
        outcome,
        safety,
        timebases: [(TIMEBASE.to_string(), times)].into_iter().collect(),
        events: events(&trace, &verification),
        metrics: metrics(&verification, &summary, max_sampled_tilt),
        scene: scene(&case, &samples, &summary, request, &verification),
        requirements: results.requirements,
        channels,
        notes,
        entities: None,
        mission: None,
    };
    Ok(record)
}
