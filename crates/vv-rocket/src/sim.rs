//! Fixed-step simulation of a prepared case into a trace of states, forces and events.

use serde::Serialize;

use crate::dynamics::{State, forces, mass_properties, neglected_jet_ratio, rk4};
use crate::model::Prepared;

pub const TRACE_SCHEMA: &str = "vv-rocket-trace.v2";

#[derive(Clone, Debug, Serialize)]
pub struct Sample {
    pub step: u64,
    pub t_s: f64,
    pub position_m: [f64; 3],
    pub velocity_mps: [f64; 3],
    pub attitude: [f64; 4],
    pub angular_velocity_radps: [f64; 3],
    pub propellant_kg: f64,
    pub mass_kg: f64,
    pub cm_station_m: f64,
    pub inertia_kgm2: [f64; 3],
    pub thrust_n: f64,
    pub thrust_inertial_n: [f64; 3],
    pub drag_inertial_n: [f64; 3],
}

#[derive(Clone, Debug, Serialize)]
pub struct Event {
    pub step: u64,
    pub t_s: f64,
    pub kind: &'static str,
    pub detail: serde_json::Value,
}

#[derive(Clone, Debug, Serialize)]
pub struct Summary {
    pub steps: u64,
    pub end_reason: &'static str,
    pub final_time_s: f64,
    pub max_altitude_m: f64,
    pub max_speed_mps: f64,
    pub propellant_used_kg: f64,
    /// Largest `| |q| - 1 |` after an RK4 step and before the projection.
    pub max_quaternion_drift: f64,
    /// Largest ratio `ε` of the neglected translational jet term to the thrust, at the two ends
    /// of every burning step; the model is adequate only while `ε ≪ 1`. Zero without thrust.
    pub max_neglected_jet_ratio: f64,
    /// Time of that largest ratio; 0 when there is no thrust.
    pub max_neglected_jet_ratio_t_s: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Trace {
    pub schema: &'static str,
    pub samples: Vec<Sample>,
    pub events: Vec<Event>,
    pub summary: Summary,
}

/// Every state reached, at each step boundary, for verification code that needs all steps.
pub struct Run {
    pub trace: Trace,
    pub states: Vec<State>,
}

fn sample(p: &Prepared, step: u64, s: &State) -> Sample {
    let m = mass_properties(&p.vehicle, s.mp);
    let burn = active(p, step);
    let f = forces(p, s, burn);
    Sample {
        step,
        t_s: step as f64 * p.dt,
        position_m: s.r.to_array(),
        velocity_mps: s.v.to_array(),
        attitude: s.q.to_array(),
        angular_velocity_radps: s.w.to_array(),
        propellant_kg: s.mp,
        mass_kg: m.mass,
        cm_station_m: m.cm_station,
        inertia_kgm2: m.inertia.to_array(),
        thrust_n: f.thrust_n,
        thrust_inertial_n: f.thrust.to_array(),
        drag_inertial_n: f.drag.to_array(),
    }
}

fn active(p: &Prepared, step: u64) -> Option<&crate::model::Segment> {
    p.segments
        .iter()
        .find(|s| s.start_step <= step && step < s.end_step)
}

/// Fraction `u ∈ [0, 1]` of the step where the cubic Hermite interpolant of altitude crosses zero.
fn crossing_fraction(z0: f64, vz0: f64, z1: f64, vz1: f64, h: f64) -> f64 {
    let at = |u: f64| {
        let u2 = u * u;
        let u3 = u2 * u;
        (2.0 * u3 - 3.0 * u2 + 1.0) * z0
            + (u3 - 2.0 * u2 + u) * h * vz0
            + (-2.0 * u3 + 3.0 * u2) * z1
            + (u3 - u2) * h * vz1
    };
    let (mut lo, mut hi) = (0.0, 1.0);
    for _ in 0..60 {
        let mid = 0.5 * (lo + hi);
        if at(mid) >= 0.0 { lo = mid } else { hi = mid }
    }
    0.5 * (lo + hi)
}

pub fn simulate(p: &Prepared, keep_states: bool) -> Result<Run, String> {
    let mut s = State {
        r: p.r0,
        v: p.v0,
        q: p.q0,
        w: p.w0,
        mp: p.vehicle.propellant_mass_kg,
    };
    let mut samples = vec![sample(p, 0, &s)];
    let mut events = Vec::new();
    let mut states = if keep_states { vec![s] } else { Vec::new() };
    let mut max_altitude = s.r.z;
    let mut max_speed = s.v.norm();
    let mut max_drift: f64 = 0.0;
    let (mut max_jet, mut max_jet_t) = (0.0_f64, 0.0);
    let mut end_reason = "duration";
    let mut step = 0;
    while step < p.steps {
        for (i, seg) in p.segments.iter().enumerate() {
            if seg.start_step == step {
                events.push(Event {
                    step,
                    t_s: step as f64 * p.dt,
                    kind: "burn_start",
                    detail: serde_json::json!({"burn": i, "thrust_n": seg.thrust_n,
                        "direction_body": seg.direction.to_array()}),
                });
            }
        }
        let before = s;
        let burn = active(p, step);
        let mut next = rk4(p, &s, burn, p.dt);
        max_drift = max_drift.max((next.q.norm() - 1.0).abs());
        next.q = next.q.normalized();
        // Exact consumption can round a few ulp below zero at exhaustion.
        if next.mp < 0.0 && next.mp > -1e-9 * p.vehicle.propellant_mass_kg.max(1.0) {
            next.mp = 0.0;
        }
        if !next.is_finite() || next.mp < 0.0 {
            return Err(format!("non-physical state after step {step}"));
        }
        for (k, x) in [(step, &before), (step + 1, &next)] {
            let ratio = neglected_jet_ratio(p, x, burn);
            if ratio > max_jet {
                (max_jet, max_jet_t) = (ratio, k as f64 * p.dt);
            }
        }
        s = next;
        step += 1;
        if keep_states {
            states.push(s);
        }
        max_altitude = max_altitude.max(s.r.z);
        max_speed = max_speed.max(s.v.norm());
        for (i, seg) in p.segments.iter().enumerate() {
            if seg.end_step == step {
                events.push(Event {
                    step,
                    t_s: step as f64 * p.dt,
                    kind: "burn_end",
                    detail: serde_json::json!({"burn": i, "propellant_kg": s.mp}),
                });
            }
        }
        if before.r.z >= 0.0 && s.r.z < 0.0 {
            let u = crossing_fraction(before.r.z, before.v.z, s.r.z, s.v.z, p.dt);
            let v = before.v + (s.v - before.v) * u;
            events.push(Event {
                step,
                t_s: step as f64 * p.dt,
                kind: "ground_crossing",
                detail: serde_json::json!({
                    "note": "centre-of-mass altitude crossed 0 m; no contact model",
                    "estimated_time_s": (step - 1) as f64 * p.dt + u * p.dt,
                    "estimated_velocity_mps": v.to_array(),
                    "propellant_kg": s.mp,
                }),
            });
            if p.stop_at_ground {
                end_reason = "ground";
            }
        }
        let last = step == p.steps || end_reason == "ground";
        if step % p.record_every == 0 || last {
            samples.push(sample(p, step, &s));
        }
        if end_reason == "ground" {
            break;
        }
    }
    events.push(Event {
        step,
        t_s: step as f64 * p.dt,
        kind: "end",
        detail: serde_json::json!({"reason": end_reason}),
    });
    Ok(Run {
        trace: Trace {
            schema: TRACE_SCHEMA,
            samples,
            events,
            summary: Summary {
                steps: step,
                end_reason,
                final_time_s: step as f64 * p.dt,
                max_altitude_m: max_altitude,
                max_speed_mps: max_speed,
                propellant_used_kg: p.vehicle.propellant_mass_kg - s.mp,
                max_quaternion_drift: max_drift,
                max_neglected_jet_ratio: max_jet,
                max_neglected_jet_ratio_t_s: max_jet_t,
            },
        },
        states,
    })
}
