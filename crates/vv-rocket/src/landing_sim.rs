//! Closed-loop landing: fixed steps, zero-order hold of the command, the per-step order of
//! docs/m9-powered-landing.md and the M8 RK4 for the dynamics.
//!
//! Order inside step `k`: (1) fault windows, (2) on control cycles observations, estimator and
//! command, (3) actuator, (4) RK4, (5) contact, (6) sample. The sample of step `k` records the true
//! state at `k` with the observation, command and actuator output applied from `k` to `k + 1`.

use serde::Serialize;

use crate::dynamics::{State, neglected_jet_ratio, rk4};
use crate::landing_actuator::{Actuator, ActuatorEvent, ActuatorFaults, ActuatorParams, Applied};
use crate::landing_controller::Controller;
use crate::landing_model::{FaultKind, PreparedLanding};
use crate::landing_sensors::{SensorFaults, SensorStreams};
use crate::landing_truth::{
    Ignition, Touchdown, TruthExcerpt, TruthLog, TruthStep, contact, excerpt,
};
use crate::landing_types::{Command, Estimate, Observation};
use crate::model::Segment;

pub const TRACE_SCHEMA: &str = "vv-rocket-landing-trace.v1";

#[derive(Clone, Debug, Serialize)]
pub struct AppliedSample {
    pub engine: &'static str,
    pub throttle: f64,
    pub gimbal_tan: [f64; 2],
    pub thrust_n: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Sample {
    pub step: u64,
    pub t_s: f64,
    /// `periodic`, `touchdown` (interpolated contact state) or `final` (duration reached).
    pub kind: &'static str,
    pub truth: TruthExcerpt,
    /// Latest observation, estimate and command of the control cycle at or before this step.
    pub observation: Observation,
    pub estimate: Estimate,
    pub command: Command,
    pub applied: AppliedSample,
    pub active_faults: Vec<&'static str>,
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
    /// `touchdown` or `duration`.
    pub end_reason: &'static str,
    pub final_time_s: f64,
    pub touchdown_t_s: Option<f64>,
    pub ignition_t_s: Option<f64>,
    pub cutoff_t_s: Option<f64>,
    pub flameout_t_s: Option<f64>,
    pub propellant_used_kg: f64,
    pub propellant_remaining_kg: f64,
    /// Ratio of the neglected jet term to the thrust (docs/m8-rocket-dynamics.md), sampled at the
    /// two ends of every thrusting step. Reported only; it carries no limit.
    pub max_neglected_jet_ratio: f64,
    pub max_neglected_jet_ratio_t_s: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Trace {
    pub schema: &'static str,
    pub samples: Vec<Sample>,
    pub events: Vec<Event>,
    pub summary: Summary,
}

pub struct LandingRun {
    pub trace: Trace,
    pub log: TruthLog,
}

fn kinds_of(active: &[FaultKind]) -> Vec<&'static str> {
    active.iter().map(|k| k.as_str()).collect()
}

struct Cycle {
    observation: Observation,
    estimate: Estimate,
    command: Command,
}

pub fn simulate_landing(prep: &PreparedLanding) -> Result<LandingRun, String> {
    let truth = &prep.truth;
    let dt = prep.dt;
    let period = prep.controller.control_period_steps;
    let mut s = State {
        r: truth.r0,
        v: truth.v0,
        q: truth.q0,
        w: truth.w0,
        mp: truth.vehicle.propellant_mass_kg,
    };
    let initial_propellant = s.mp;
    let mut controller = Controller::new(prep.controller.clone());
    let mut actuator = Actuator::new(ActuatorParams {
        dt,
        throttle_min: prep.limits.throttle_min,
        throttle_max: prep.limits.throttle_max,
        throttle_rate_per_s: prep.limits.throttle_rate_per_s,
        gimbal_max_tan: prep.limits.gimbal_max_tan,
        gimbal_rate_tan_per_s: prep.limits.gimbal_rate_tan_per_s,
        max_thrust_n: truth.vehicle.max_thrust_n,
        isp_s: truth.vehicle.isp_s,
    });
    let mut streams = SensorStreams::new(prep.seed);

    let mut samples = Vec::new();
    let mut events: Vec<Event> = Vec::new();
    let mut log_steps: Vec<TruthStep> = Vec::new();
    let mut held: Option<Segment> = None;
    let mut cycle: Option<Cycle> = None;
    let mut applied = Applied {
        engine: actuator.engine(),
        throttle: 0.0,
        gimbal_tan: [0.0, 0.0],
        thrust_n: 0.0,
    };
    let (mut ignition_t, mut cutoff_t, mut flameout_t) = (None, None, None);
    let (mut max_jet, mut max_jet_t) = (0.0_f64, 0.0);
    let mut touchdown: Option<Touchdown> = None;
    let mut ignition: Option<Ignition> = None;
    let mut last_active: Vec<FaultKind> = Vec::new();
    let mut end_state = s;
    let mut step = 0;

    let make_sample = |kind: &'static str,
                       step: u64,
                       t_s: f64,
                       state: &State,
                       cycle: &Cycle,
                       applied: &Applied,
                       active: &[FaultKind]| Sample {
        step,
        t_s,
        kind,
        truth: excerpt(&truth.vehicle, state),
        observation: cycle.observation,
        estimate: cycle.estimate,
        command: cycle.command,
        applied: AppliedSample {
            engine: applied.engine.as_str(),
            throttle: applied.throttle,
            gimbal_tan: applied.gimbal_tan,
            thrust_n: applied.thrust_n,
        },
        active_faults: kinds_of(active),
    };

    while step < prep.steps {
        let t_s = step as f64 * dt;
        // 1. Fault windows.
        let mut active: Vec<FaultKind> = Vec::new();
        let mut sensor_faults = SensorFaults::default();
        let mut actuator_faults = ActuatorFaults::default();
        for f in &prep.faults {
            if f.start_step == step {
                events.push(Event {
                    step,
                    t_s,
                    kind: "fault_start",
                    detail: serde_json::json!({"fault": f.spec.kind.as_str(),
                        "magnitude": f.spec.magnitude, "end_s": f.spec.end_s}),
                });
            }
            if f.end_step == step {
                events.push(Event {
                    step,
                    t_s,
                    kind: "fault_end",
                    detail: serde_json::json!({"fault": f.spec.kind.as_str()}),
                });
            }
            if f.start_step <= step && step < f.end_step {
                active.push(f.spec.kind);
                let m = f.spec.magnitude;
                match f.spec.kind {
                    FaultKind::ThrustLoss => actuator_faults.thrust_loss = m,
                    FaultKind::IgnitionDelay => {
                        actuator_faults.ignition_delay_steps = Some((m / dt).round() as u64)
                    }
                    FaultKind::GimbalStuck => actuator_faults.gimbal_stuck = true,
                    FaultKind::AltimeterBias => sensor_faults.altimeter_bias_m = m,
                    FaultKind::AltimeterDropout => sensor_faults.altimeter_dropout = true,
                    FaultKind::GnssDropout => sensor_faults.gnss_dropout = true,
                    FaultKind::GnssBias => sensor_faults.gnss_bias_m = m,
                    FaultKind::ImuAccelBias => sensor_faults.imu_accel_bias_mps2 = m,
                }
            }
        }

        // 2. Control cycle.
        if step % period == 0 {
            let gnss_cycle = (step / period).is_multiple_of(prep.sensors.gnss_period_cycles);
            let observation = streams.observe(
                truth,
                &prep.sensors,
                &s,
                held.as_ref(),
                &sensor_faults,
                gnss_cycle,
            );
            let (command, estimate) = controller.step(&observation);
            cycle = Some(Cycle {
                observation,
                estimate,
                command,
            });
        }
        let current = cycle.as_ref().ok_or("no control cycle at step 0")?;

        // 3. Actuator.
        let (new_applied, actuator_events) =
            actuator.apply(step, &current.command, &actuator_faults, s.mp);
        applied = new_applied;
        if ignition.is_none()
            && let Some(command_step) = actuator.pending_command_step()
        {
            ignition = Some(Ignition {
                command_step,
                effective_step: None,
            });
        }
        for e in actuator_events {
            match e {
                ActuatorEvent::Ignition { command_step } => {
                    ignition_t = Some(t_s);
                    ignition = Some(Ignition {
                        command_step,
                        effective_step: Some(step),
                    });
                    events.push(Event {
                        step,
                        t_s,
                        kind: "ignition",
                        detail: serde_json::json!({"command_step": command_step,
                            "command_t_s": command_step as f64 * dt}),
                    });
                }
                ActuatorEvent::Cutoff => {
                    cutoff_t = Some(t_s);
                    events.push(Event {
                        step,
                        t_s,
                        kind: "cutoff",
                        detail: serde_json::json!({"propellant_kg": s.mp}),
                    });
                }
                ActuatorEvent::Flameout {
                    needed_kg,
                    available_kg,
                } => {
                    flameout_t = Some(t_s);
                    events.push(Event {
                        step,
                        t_s,
                        kind: "flameout",
                        detail: serde_json::json!({"needed_kg": needed_kg,
                            "available_kg": available_kg}),
                    });
                }
            }
        }
        let seg = (applied.thrust_n > 0.0).then(|| Segment {
            start_step: step,
            end_step: step + 1,
            thrust_n: applied.thrust_n,
            direction: applied.direction(),
        });
        if step % prep.record_every == 0 {
            samples.push(make_sample(
                "periodic", step, t_s, &s, current, &applied, &active,
            ));
        }
        log_steps.push(TruthStep {
            step,
            state: s,
            thrust_n: applied.thrust_n,
            direction: applied.direction(),
            active_faults: active.clone(),
        });
        held = seg;
        last_active = active.clone();

        // 4. Integrate.
        let mut next = rk4(truth, &s, seg.as_ref(), dt);
        next.q = next.q.normalized();
        if next.mp < 0.0 && next.mp > -1e-9 * truth.vehicle.propellant_mass_kg.max(1.0) {
            next.mp = 0.0;
        }
        if !next.is_finite() || next.mp < 0.0 {
            return Err(format!("non-physical state after step {step}"));
        }
        for (k, x) in [(step, &s), (step + 1, &next)] {
            let ratio = neglected_jet_ratio(truth, x, seg.as_ref());
            if ratio > max_jet {
                (max_jet, max_jet_t) = (ratio, k as f64 * dt);
            }
        }

        // 5. Contact.
        step += 1;
        if let Some((u, state)) = contact(&truth.vehicle, &s, &next) {
            let t_touch = ((step - 1) as f64 + u) * dt;
            events.push(Event {
                step,
                t_s: t_touch,
                kind: "touchdown",
                detail: serde_json::json!({"fraction": u,
                    "note": "nozzle plane reached z = 0; no contact dynamics"}),
            });
            samples.push(make_sample(
                "touchdown",
                step,
                t_touch,
                &state,
                current,
                &applied,
                &active,
            ));
            touchdown = Some(Touchdown {
                step,
                fraction: u,
                t_s: t_touch,
                state,
                after: next,
            });
            end_state = state;
            break;
        }
        s = next;
        end_state = s;
    }

    let end_reason = if touchdown.is_some() {
        "touchdown"
    } else {
        "duration"
    };
    if touchdown.is_none()
        && let Some(current) = cycle.as_ref()
    {
        samples.push(make_sample(
            "final",
            step,
            step as f64 * dt,
            &s,
            current,
            &applied,
            &last_active,
        ));
    }
    let final_time_s = touchdown.as_ref().map_or(step as f64 * dt, |t| t.t_s);
    events.push(Event {
        step,
        t_s: final_time_s,
        kind: "end",
        detail: serde_json::json!({"reason": end_reason}),
    });
    let remaining = end_state.mp;
    let summary = Summary {
        steps: step,
        end_reason,
        final_time_s,
        touchdown_t_s: touchdown.as_ref().map(|t| t.t_s),
        ignition_t_s: ignition_t,
        cutoff_t_s: cutoff_t,
        flameout_t_s: flameout_t,
        propellant_used_kg: initial_propellant - remaining,
        propellant_remaining_kg: remaining,
        max_neglected_jet_ratio: max_jet,
        max_neglected_jet_ratio_t_s: max_jet_t,
    };
    Ok(LandingRun {
        trace: Trace {
            schema: TRACE_SCHEMA,
            samples,
            events,
            summary,
        },
        log: TruthLog {
            dt,
            steps: log_steps,
            end_step: step,
            end_state,
            touchdown,
            ignition,
        },
    })
}

#[cfg(test)]
mod tests {
    //! Scenarios the pre-registered case cannot express (an empty tank, a start near the ground)
    //! run through `prepare_unpinned`, which skips the pins but keeps every other check.

    use serde_json::{Value, json};

    use super::*;
    use crate::landing_model::{LandingCase, prepare_unpinned};
    use crate::landing_verify::verify;

    fn run_unpinned(edit: impl Fn(&mut Value)) -> Result<(Value, Value), String> {
        let mut case: Value =
            serde_json::from_str(include_str!("../landing/nominal.json")).unwrap();
        edit(&mut case);
        let case: LandingCase = serde_json::from_value(case).unwrap();
        let prep = prepare_unpinned(&case, 0)?;
        let run = simulate_landing(&prep)?;
        let v = verify(&prep, &run.log);
        Ok((
            serde_json::to_value(&run.trace).unwrap(),
            serde_json::to_value(&v).unwrap(),
        ))
    }

    fn event_kinds(trace: &Value) -> Vec<&str> {
        trace["events"]
            .as_array()
            .unwrap()
            .iter()
            .map(|e| e["kind"].as_str().unwrap())
            .collect()
    }

    fn invariant<'a>(v: &'a Value, id: &str) -> &'a Value {
        v["invariants"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["id"] == id)
            .unwrap()
    }

    #[test]
    fn running_out_of_propellant_is_a_flameout_and_a_hard_landing() {
        let (trace, v) =
            run_unpinned(|c| c["vehicle"]["propellant_mass_kg"] = json!(500.0)).unwrap();
        let kinds = event_kinds(&trace);
        assert!(kinds.contains(&"flameout"), "{kinds:?}");
        assert_ne!(v["outcome"], "landed");
        assert!(trace["summary"]["flameout_t_s"].as_f64().unwrap() > 0.0);
        assert!(
            trace["summary"]["propellant_remaining_kg"]
                .as_f64()
                .unwrap()
                < 5.0
        );
        // The truth mass never goes negative and the last samples show the engine out.
        let last = trace["samples"].as_array().unwrap().last().unwrap();
        assert_eq!(last["applied"]["engine"], "flameout");
    }

    #[test]
    fn a_rising_vehicle_near_the_ground_is_cut_and_cannot_relight() {
        let (trace, v) = run_unpinned(|c| {
            c["initial"]["position_m"] = json!([0.0, 0.0, 100.0]);
            c["initial"]["velocity_mps"] = json!([0.0, 0.0, -10.0]);
            c["controller"]["gains"]["ignition_fraction"] = json!(0.1);
            c["controller"]["gains"]["cutoff_altitude_m"] = json!(1000.0);
        })
        .unwrap();
        assert_eq!(
            event_kinds(&trace),
            ["ignition", "cutoff", "touchdown", "end"]
        );
        assert_eq!(v["outcome"], "hard_landing");
        assert_eq!(invariant(&v, "S4_no_relight")["pass"], true);
        assert_eq!(invariant(&v, "S4_no_relight")["worst_value"], 1.0);
        let last = trace["samples"].as_array().unwrap().last().unwrap();
        assert_eq!(last["applied"]["engine"], "cut");
    }

    #[test]
    fn the_nozzle_plane_must_start_above_the_ground() {
        let err =
            run_unpinned(|c| c["initial"]["position_m"] = json!([0.0, 0.0, 5.0])).unwrap_err();
        assert!(err.contains("above the ground"), "{err}");
    }
}
