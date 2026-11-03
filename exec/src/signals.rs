//! M13: time series of a written run for the Discovery Lab views, read from the canonical
//! artifacts after they are written. Truth, what the controller believed, what the sensors
//! reported, the flags it raised and the commands it gave are kept apart by `role`, so a view
//! never mixes the real state with an observation. The series are derived data: the canonical
//! trace stays the evidence, and `verify` rewrites both.

use std::path::Path;

use serde::Serialize;
use serde_json::{Value, json};

use crate::plan::read_capped;

pub const SCHEMA: &str = "vv-signals.v1";
const MAX_TRACE_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Series {
    pub id: String,
    pub label: String,
    pub unit: String,
    pub group: String,
    /// `truth`, `belief`, `observation`, `error`, `flag` or `command`.
    pub role: String,
    pub t: Vec<f64>,
    pub v: Vec<Option<f64>>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Event {
    pub t: f64,
    pub kind: String,
    pub label: String,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Signals {
    pub schema: String,
    pub domain: String,
    pub time_unit: String,
    pub series: Vec<Series>,
    pub events: Vec<Event>,
    /// Domain geometry for a plan view, when there is one.
    pub geometry: Value,
}

fn read_json(dir: &Path, name: &str) -> Result<Value, String> {
    let bytes = read_capped(&dir.join(name), MAX_TRACE_BYTES)?;
    serde_json::from_slice(&bytes).map_err(|e| format!("{name}: {e}"))
}

fn num(v: &Value, p: &str) -> Option<f64> {
    match v.pointer(p)? {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        _ => None,
    }
}

struct Builder {
    series: Vec<Series>,
}

impl Builder {
    fn add(&mut self, id: &str, label: &str, unit: &str, group: &str, role: &str) {
        self.series.push(Series {
            id: id.into(),
            label: label.into(),
            unit: unit.into(),
            group: group.into(),
            role: role.into(),
            t: Vec::new(),
            v: Vec::new(),
        });
    }
    fn push(&mut self, id: &str, t: f64, v: Option<f64>) {
        if let Some(s) = self.series.iter_mut().find(|s| s.id == id) {
            s.t.push(t);
            s.v.push(v.filter(|x| x.is_finite()));
        }
    }
}

pub fn extract(domain: &str, dir: &Path) -> Result<Signals, String> {
    match domain {
        "rocket-landing" => rocket(dir),
        "ground-m4" => ground(dir),
        other => Err(format!("no signal reader for domain {other}")),
    }
}

fn rocket(dir: &Path) -> Result<Signals, String> {
    let trace = read_json(dir, "trace.json")?;
    let samples = trace["samples"].as_array().ok_or("trace has no samples")?;
    let mut b = Builder { series: Vec::new() };
    b.add(
        "z_true",
        "Altitude of the centre of mass, true",
        "m",
        "Altitude",
        "truth",
    );
    b.add(
        "z_est",
        "Altitude of the centre of mass, believed",
        "m",
        "Altitude",
        "belief",
    );
    b.add(
        "z_gnss",
        "GNSS altitude, reported",
        "m",
        "Altitude",
        "observation",
    );
    b.add(
        "h_true",
        "Height of the nozzle plane, true",
        "m",
        "Height above the pad",
        "truth",
    );
    b.add(
        "h_alt",
        "Radar altimeter, reported",
        "m",
        "Height above the pad",
        "observation",
    );
    b.add(
        "vz_true",
        "Vertical velocity, true",
        "m/s",
        "Vertical velocity",
        "truth",
    );
    b.add(
        "vz_est",
        "Vertical velocity, believed",
        "m/s",
        "Vertical velocity",
        "belief",
    );
    b.add(
        "ez",
        "Altitude belief error (believed minus true)",
        "m",
        "Belief error",
        "error",
    );
    b.add(
        "evz",
        "Vertical velocity belief error (believed minus true)",
        "m/s",
        "Belief error",
        "error",
    );
    b.add(
        "alt_rejected",
        "Altimeter rejected by the estimator",
        "",
        "Monitors",
        "flag",
    );
    b.add(
        "disagreement",
        "Sensor disagreement declared",
        "",
        "Monitors",
        "flag",
    );
    b.add("throttle", "Throttle applied", "", "Engine", "command");
    for s in samples {
        let Some(t) = num(s, "/t_s") else { continue };
        let z = num(s, "/truth/position_m/2");
        let ze = num(s, "/estimate/position_m/2");
        let vz = num(s, "/truth/velocity_mps/2");
        let vze = num(s, "/estimate/velocity_mps/2");
        b.push("z_true", t, z);
        b.push("z_est", t, ze);
        b.push("z_gnss", t, num(s, "/observation/gnss_position_m/2"));
        b.push("h_true", t, num(s, "/truth/base_position_m/2"));
        b.push("h_alt", t, num(s, "/observation/altimeter_m"));
        b.push("vz_true", t, vz);
        b.push("vz_est", t, vze);
        b.push("ez", t, ze.zip(z).map(|(a, b)| a - b));
        b.push("evz", t, vze.zip(vz).map(|(a, b)| a - b));
        b.push("alt_rejected", t, num(s, "/estimate/altimeter_rejected"));
        b.push("disagreement", t, num(s, "/estimate/sensor_disagreement"));
        b.push("throttle", t, num(s, "/applied/throttle"));
    }
    let mut events = Vec::new();
    for e in trace["events"].as_array().into_iter().flatten() {
        let (Some(t), Some(kind)) = (num(e, "/t_s"), e["kind"].as_str()) else {
            continue;
        };
        let label = match kind {
            "fault_start" => format!(
                "{} starts{}",
                e["detail"]["fault"].as_str().unwrap_or("fault"),
                num(e, "/detail/magnitude")
                    .map(|m| format!(", magnitude {m}"))
                    .unwrap_or_default()
            ),
            "fault_end" => format!("{} ends", e["detail"]["fault"].as_str().unwrap_or("fault")),
            other => other.replace('_', " "),
        };
        events.push(Event {
            t,
            kind: kind.into(),
            label,
        });
    }
    let verification = read_json(dir, "verification.json")?;
    for r in verification["requirements"]
        .as_array()
        .into_iter()
        .flatten()
    {
        if r["pass"] == Value::Bool(false)
            && let Some(t) = num(r, "/t_s")
        {
            events.push(Event {
                t,
                kind: "violation".into(),
                label: format!(
                    "{} violated: {} (expected {})",
                    r["id"].as_str().unwrap_or("requirement"),
                    r["observed"].as_str().unwrap_or(""),
                    r["expected"].as_str().unwrap_or("")
                ),
            });
        }
    }
    for i in verification["invariants"].as_array().into_iter().flatten() {
        if i["pass"] == Value::Bool(false) {
            events.push(Event {
                t: num(i, "/t_s")
                    .or(num(i, "/first_violation_t_s"))
                    .unwrap_or(0.0),
                kind: "violation".into(),
                label: format!("{} violated", i["id"].as_str().unwrap_or("invariant")),
            });
        }
    }
    events.sort_by(|a, b| a.t.total_cmp(&b.t));
    Ok(Signals {
        schema: SCHEMA.into(),
        domain: "rocket-landing".into(),
        time_unit: "s".into(),
        series: b.series,
        events,
        geometry: json!({}),
    })
}

fn ground(dir: &Path) -> Result<Signals, String> {
    let trace = read_json(dir, "events.json")?;
    let tick_s = num(&trace, "/scenario/tick_ms").unwrap_or(100.0) / 1000.0;
    let mut b = Builder { series: Vec::new() };
    b.add("x_true", "Position x, true", "mm", "Position x", "truth");
    b.add(
        "x_obs",
        "Position x, believed (last accepted GPS)",
        "mm",
        "Position x",
        "belief",
    );
    b.add("y_true", "Position y, true", "mm", "Position y", "truth");
    b.add(
        "y_obs",
        "Position y, believed (last accepted GPS)",
        "mm",
        "Position y",
        "belief",
    );
    b.add(
        "e_xy",
        "Position belief error (distance)",
        "mm",
        "Belief error",
        "error",
    );
    b.add(
        "confidence",
        "Confidence of the believed position",
        "permille",
        "Monitors",
        "flag",
    );
    b.add(
        "fallback",
        "Safety state not nominal",
        "",
        "Monitors",
        "flag",
    );
    let mut events = Vec::new();
    for e in trace["events"].as_array().into_iter().flatten() {
        let Some(tick) = num(e, "/tick") else {
            continue;
        };
        let t = tick * tick_s;
        let ev = &e["event"];
        match ev["kind"].as_str() {
            Some("tick_result") => {
                let xt = num(ev, "/truth_position/x_mm");
                let yt = num(ev, "/truth_position/y_mm");
                let xo = num(ev, "/observed/position/x_mm");
                let yo = num(ev, "/observed/position/y_mm");
                b.push("x_true", t, xt);
                b.push("y_true", t, yt);
                b.push("x_obs", t, xo);
                b.push("y_obs", t, yo);
                let err = match (xt, yt, xo, yo) {
                    (Some(a), Some(b2), Some(c), Some(d)) => Some((a - c).hypot(b2 - d)),
                    _ => None,
                };
                b.push("e_xy", t, err);
                b.push("confidence", t, num(ev, "/observed/confidence_permille"));
                b.push(
                    "fallback",
                    t,
                    ev["safety_state"]
                        .as_str()
                        .map(|s| if s == "nominal" { 0.0 } else { 1.0 }),
                );
            }
            Some("invariant_check") if ev["passed"] == Value::Bool(false) => {
                events.push(Event {
                    t,
                    kind: "violation".into(),
                    label: format!(
                        "{} violated: {}",
                        ev["name"].as_str().unwrap_or("invariant"),
                        ev["detail"].as_str().unwrap_or("")
                    ),
                });
            }
            Some("transition") => {
                events.push(Event {
                    t,
                    kind: "transition".into(),
                    label: format!(
                        "{}: {} to {}",
                        ev["subsystem"].as_str().unwrap_or(""),
                        ev["from"].as_str().unwrap_or(""),
                        ev["to"].as_str().unwrap_or("")
                    ),
                });
            }
            _ => {}
        }
    }
    let scenario = &trace["scenario"];
    Ok(Signals {
        schema: SCHEMA.into(),
        domain: "ground-m4".into(),
        time_unit: "s".into(),
        series: b.series,
        events,
        geometry: json!({
            "bounds": scenario["bounds"],
            "restricted_zone": scenario["restricted_zone"],
            "waypoints": scenario["mission"]["waypoints"],
            "arrival_radius_mm": scenario["mission"]["arrival_radius_mm"],
            "start": scenario["vehicle"]["start"],
        }),
    })
}
