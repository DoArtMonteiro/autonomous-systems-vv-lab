//! Independent verifier of the landing: requirements R1 to R6 at the interpolated contact state
//! and invariants S1 to S4 per step, from the true state only. Formulas and limits are those of
//! docs/m9-powered-landing.md; the mission outcome is kept apart from the safety invariants.

use serde::Serialize;

use crate::dynamics::{State, forces, mass_properties};
use crate::landing_model::{FaultKind, FaultSpec, PreparedLanding, Requirements};
use crate::landing_truth::{TruthExcerpt, TruthLog, TruthStep, base_kinematics, excerpt, tilt_cos};
use crate::math::Vec3;
use crate::model::{G0, Prepared, Segment, Vehicle};

pub const VERIFICATION_SCHEMA: &str = "vv-rocket-landing-verification.v1";
pub const DISCLAIMER: &str = "idealized model; contact = nozzle plane reaching z=0; no contact dynamics; not validated against flight data";

#[derive(Clone, Debug, Serialize)]
pub struct RequirementResult {
    pub id: &'static str,
    pub pass: bool,
    /// False when there was no contact, so the requirement could not be evaluated (and is not met).
    pub evaluated: bool,
    pub limit: f64,
    pub value: Option<f64>,
    pub unit: &'static str,
    pub expected: String,
    pub observed: String,
    pub step: Option<u64>,
    pub t_s: Option<f64>,
    pub cause: Vec<&'static str>,
}

#[derive(Clone, Debug, Serialize)]
pub struct FirstFailure {
    pub step: u64,
    pub t_s: f64,
    pub expected: String,
    pub observed: String,
    pub cause: Vec<&'static str>,
    pub truth: TruthExcerpt,
}

#[derive(Clone, Debug, Serialize)]
pub struct InvariantResult {
    pub id: &'static str,
    pub pass: bool,
    pub evaluated: bool,
    pub limit: f64,
    /// The most adverse value seen: the minimum for lower bounds, the maximum for upper bounds.
    pub worst_value: Option<f64>,
    pub unit: &'static str,
    pub failure_count: u64,
    pub first_failure: Option<FirstFailure>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TouchdownReport {
    pub step: u64,
    pub fraction: f64,
    pub t_s: f64,
    pub truth: TruthExcerpt,
}

#[derive(Clone, Debug, Serialize)]
pub struct Verification {
    pub schema: &'static str,
    /// `landed`, `hard_landing` or `no_contact`.
    pub outcome: &'static str,
    pub requirements_pass: bool,
    pub invariants_pass: bool,
    pub requirements: Vec<RequirementResult>,
    pub invariants: Vec<InvariantResult>,
    pub touchdown: Option<TouchdownReport>,
    pub seed: u64,
    pub policy: &'static str,
    pub faults: Vec<FaultSpec>,
    pub disclaimer: &'static str,
}

fn kinds(faults: &[FaultKind]) -> Vec<&'static str> {
    faults.iter().map(|k| k.as_str()).collect()
}

fn le(limit: f64, unit: &str) -> String {
    format!("<= {limit} {unit}")
}

fn ge(limit: f64, unit: &str) -> String {
    format!(">= {limit} {unit}")
}

fn horizontal(v: Vec3, origin: [f64; 2]) -> f64 {
    let (x, y) = (v.x - origin[0], v.y - origin[1]);
    (x * x + y * y).sqrt()
}

/// Requirements R1 to R6 at the contact state, or "not evaluated" entries without contact.
fn requirements(
    req: &Requirements,
    vehicle: &Vehicle,
    initial_propellant_kg: f64,
    log: &TruthLog,
) -> Vec<RequirementResult> {
    let spec: [(&'static str, f64, &'static str, bool); 6] = [
        ("R1_vertical_speed", req.r1_vertical_speed_mps, "m/s", false),
        (
            "R2_horizontal_speed",
            req.r2_horizontal_speed_mps,
            "m/s",
            false,
        ),
        ("R3_tilt", req.r3_tilt_cos_min, "cos", true),
        ("R4_angular_rate", req.r4_angular_rate_radps, "rad/s", false),
        ("R5_position", req.r5_position_m, "m", false),
        (
            "R6_propellant_margin",
            req.r6_propellant_margin_fraction * initial_propellant_kg,
            "kg",
            true,
        ),
    ];
    let contact = log.touchdown.as_ref().map(|t| {
        let (bp, bv) = base_kinematics(vehicle, &t.state);
        let values = [
            bv.z.abs(),
            horizontal(bv, [0.0, 0.0]),
            tilt_cos(t.state.q),
            t.state.w.norm(),
            horizontal(bp, req.pad_position_m),
            t.state.mp,
        ];
        let cause = log
            .steps
            .iter()
            .find(|s| s.step + 1 == t.step)
            .map(|s| kinds(&s.active_faults))
            .unwrap_or_default();
        (values, t.step, t.t_s, cause)
    });
    spec.iter()
        .enumerate()
        .map(|(i, &(id, limit, unit, lower_bound))| {
            let expected = if lower_bound {
                ge(limit, unit)
            } else {
                le(limit, unit)
            };
            match &contact {
                Some((values, step, t_s, cause)) => {
                    let value = values[i];
                    let pass = if lower_bound {
                        value >= limit
                    } else {
                        value <= limit
                    };
                    RequirementResult {
                        id,
                        pass,
                        evaluated: true,
                        limit,
                        value: Some(value),
                        unit,
                        expected,
                        observed: format!("{value:.6} {unit}"),
                        step: Some(*step),
                        t_s: Some(*t_s),
                        cause: cause.clone(),
                    }
                }
                None => RequirementResult {
                    id,
                    pass: false,
                    evaluated: false,
                    limit,
                    value: None,
                    unit,
                    expected,
                    observed: "no contact".into(),
                    step: None,
                    t_s: None,
                    cause: Vec::new(),
                },
            }
        })
        .collect()
}

struct Tally {
    id: &'static str,
    limit: f64,
    unit: &'static str,
    lower_bound: bool,
    evaluated: bool,
    worst: Option<f64>,
    failures: u64,
    first: Option<FirstFailure>,
}

impl Tally {
    fn new(id: &'static str, limit: f64, unit: &'static str, lower_bound: bool) -> Self {
        Tally {
            id,
            limit,
            unit,
            lower_bound,
            evaluated: false,
            worst: None,
            failures: 0,
            first: None,
        }
    }

    fn check(
        &mut self,
        value: f64,
        step: u64,
        t_s: f64,
        cause: &[FaultKind],
        vehicle: &Vehicle,
        state: &State,
    ) {
        self.evaluated = true;
        let worse = |a: f64, b: f64| if self.lower_bound { a < b } else { a > b };
        if self.worst.is_none_or(|w| worse(value, w)) {
            self.worst = Some(value);
        }
        let ok = if self.lower_bound {
            value >= self.limit
        } else {
            value <= self.limit
        };
        if ok {
            return;
        }
        self.failures += 1;
        if self.first.is_none() {
            let expected = if self.lower_bound {
                ge(self.limit, self.unit)
            } else {
                le(self.limit, self.unit)
            };
            self.first = Some(FirstFailure {
                step,
                t_s,
                expected,
                observed: format!("{value:.6} {}", self.unit),
                cause: kinds(cause),
                truth: excerpt(vehicle, state),
            });
        }
    }

    fn finish(self) -> InvariantResult {
        InvariantResult {
            id: self.id,
            pass: self.failures == 0,
            evaluated: self.evaluated,
            limit: self.limit,
            worst_value: self.worst,
            unit: self.unit,
            failure_count: self.failures,
            first_failure: self.first,
        }
    }
}

fn segment_of(s: &TruthStep) -> Option<Segment> {
    (s.thrust_n > 0.0).then_some(Segment {
        start_step: s.step,
        end_step: s.step + 1,
        thrust_n: s.thrust_n,
        direction: s.direction,
    })
}

/// Invariants S1 to S4. S1 is checked at the state each thrusting step starts from and at the
/// state it reaches; S3 at the start of every step with that step's thrust; S4 over the thrust
/// history; S2 at the contact only.
fn invariants(req: &Requirements, truth: &Prepared, log: &TruthLog) -> Vec<InvariantResult> {
    let vehicle = &truth.vehicle;
    let mut s1 = Tally::new("S1_tilt_envelope", req.s1_tilt_cos_min, "cos", true);
    let mut s2 = Tally::new("S2_keep_out", req.s2_keep_out_m, "m", false);
    let mut s3 = Tally::new("S3_axial_load", req.s3_axial_load_g0, "g0", false);
    let mut s4 = Tally::new(
        "S4_no_relight",
        f64::from(req.s4_max_ignitions),
        "ignitions",
        false,
    );
    let mut ignitions = 0_u32;
    let mut last_s1: Option<u64> = None;
    let mut prev_thrusting = false;
    let n = log.steps.len();
    for (i, st) in log.steps.iter().enumerate() {
        let thrusting = st.thrust_n > 0.0;
        let t_s = st.step as f64 * log.dt;
        if thrusting && last_s1 != Some(st.step) {
            s1.check(
                tilt_cos(st.state.q),
                st.step,
                t_s,
                &st.active_faults,
                vehicle,
                &st.state,
            );
        }
        if thrusting {
            let (end_step, end_state, end_t) = match log.steps.get(i + 1) {
                Some(next) => (next.step, next.state, next.step as f64 * log.dt),
                None => (
                    log.end_step,
                    log.end_state,
                    log.touchdown
                        .as_ref()
                        .map_or(log.end_step as f64 * log.dt, |t| t.t_s),
                ),
            };
            s1.check(
                tilt_cos(end_state.q),
                end_step,
                end_t,
                &st.active_faults,
                vehicle,
                &end_state,
            );
            last_s1 = Some(st.step + 1);
        }
        let seg = segment_of(st);
        let f = forces(truth, &st.state, seg.as_ref());
        let load = (f.thrust + f.drag).norm() / mass_properties(vehicle, st.state.mp).mass / G0;
        s3.check(load, st.step, t_s, &st.active_faults, vehicle, &st.state);
        if thrusting && !prev_thrusting {
            ignitions += 1;
            s4.check(
                f64::from(ignitions),
                st.step,
                t_s,
                &st.active_faults,
                vehicle,
                &st.state,
            );
        }
        prev_thrusting = thrusting;
    }
    if n == 0 || s4.worst.is_none() {
        // No ignition: the count is zero and the invariant held.
        s4.evaluated = true;
        s4.worst = Some(0.0);
    }
    if let Some(t) = &log.touchdown {
        let (bp, _) = base_kinematics(vehicle, &t.state);
        let cause = log
            .steps
            .iter()
            .find(|s| s.step + 1 == t.step)
            .map(|s| s.active_faults.clone())
            .unwrap_or_default();
        s2.check(
            horizontal(bp, req.pad_position_m),
            t.step,
            t.t_s,
            &cause,
            vehicle,
            &t.state,
        );
    }
    vec![s1.finish(), s2.finish(), s3.finish(), s4.finish()]
}

/// Verdicts from the true state only.
pub fn evaluate(
    req: &Requirements,
    truth: &Prepared,
    log: &TruthLog,
) -> (&'static str, Vec<RequirementResult>, Vec<InvariantResult>) {
    let reqs = requirements(req, &truth.vehicle, truth.vehicle.propellant_mass_kg, log);
    let invs = invariants(req, truth, log);
    let outcome = if log.touchdown.is_none() {
        "no_contact"
    } else if reqs.iter().all(|r| r.pass) {
        "landed"
    } else {
        "hard_landing"
    };
    (outcome, reqs, invs)
}

pub fn verify(prep: &PreparedLanding, log: &TruthLog) -> Verification {
    let (outcome, requirements, invariants) = evaluate(&prep.requirements, &prep.truth, log);
    let touchdown = log.touchdown.as_ref().map(|t| TouchdownReport {
        step: t.step,
        fraction: t.fraction,
        t_s: t.t_s,
        truth: excerpt(&prep.truth.vehicle, &t.state),
    });
    Verification {
        schema: VERIFICATION_SCHEMA,
        outcome,
        requirements_pass: requirements.iter().all(|r| r.pass),
        invariants_pass: invariants.iter().all(|i| i.pass),
        requirements,
        invariants,
        touchdown,
        seed: prep.seed,
        policy: prep.controller.policy.as_str(),
        faults: prep.faults.iter().map(|f| f.spec).collect(),
        disclaimer: DISCLAIMER,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::landing_truth::Touchdown;
    use crate::math::Quat;

    fn vehicle() -> Vehicle {
        Vehicle {
            dry_mass_kg: 1000.0,
            propellant_mass_kg: 100.0,
            dry_cm_station_m: 5.0,
            propellant_cm_station_m: 5.0,
            dry_inertia_kgm2: [100.0, 1000.0, 1000.0],
            propellant_inertia_kgm2: [10.0, 100.0, 100.0],
            max_thrust_n: 40_000.0,
            isp_s: 300.0,
            drag_coefficient: 0.0,
            reference_area_m2: 0.0,
        }
    }

    fn prepared() -> Prepared {
        Prepared {
            dt: 0.01,
            steps: 100,
            record_every: 2,
            stop_at_ground: false,
            gravity: 9.80665,
            atmosphere: None,
            vehicle: vehicle(),
            r0: Vec3::ZERO,
            v0: Vec3::ZERO,
            q0: Quat::IDENTITY,
            w0: Vec3::ZERO,
            segments: Vec::new(),
        }
    }

    /// Upright state with nozzle plane at `z_base`.
    fn upright(z_base: f64) -> State {
        let h = std::f64::consts::FRAC_1_SQRT_2;
        State {
            r: Vec3::new(0.0, 0.0, z_base + 5.0),
            v: Vec3::new(0.0, 0.0, -1.5),
            q: Quat::new(h, 0.0, -h, 0.0),
            w: Vec3::ZERO,
            mp: 50.0,
        }
    }

    fn log_with(state: State) -> TruthLog {
        let step = TruthStep {
            step: 0,
            state: upright(1.0),
            thrust_n: 0.0,
            direction: Vec3::new(1.0, 0.0, 0.0),
            active_faults: vec![FaultKind::GnssBias],
        };
        TruthLog {
            dt: 0.01,
            steps: vec![step],
            end_step: 1,
            end_state: state,
            touchdown: Some(Touchdown {
                step: 1,
                fraction: 0.5,
                t_s: 0.005,
                state,
            }),
        }
    }

    fn run(state: State) -> (&'static str, Vec<RequirementResult>, Vec<InvariantResult>) {
        evaluate(&Requirements::registered(), &prepared(), &log_with(state))
    }

    fn failed(reqs: &[RequirementResult]) -> Vec<&'static str> {
        reqs.iter().filter(|r| !r.pass).map(|r| r.id).collect()
    }

    #[test]
    fn a_soft_upright_contact_lands() {
        let (outcome, reqs, invs) = run(upright(0.0));
        assert_eq!(outcome, "landed");
        assert!(failed(&reqs).is_empty());
        assert!(invs.iter().all(|i| i.pass));
        assert_eq!(reqs[0].value, Some(1.5));
        assert_eq!(reqs[0].cause, ["gnss_bias"]);
        assert_eq!(reqs[0].expected, "<= 3 m/s");
        assert_eq!(reqs[5].value, Some(50.0));
    }

    #[test]
    fn each_requirement_fails_on_its_own_violation() {
        let mut s = upright(0.0);
        s.v.z = -3.5;
        let (outcome, reqs, _) = run(s);
        assert_eq!(
            (outcome, failed(&reqs)),
            ("hard_landing", vec!["R1_vertical_speed"])
        );

        let mut s = upright(0.0);
        s.v.x = 1.2;
        assert_eq!(failed(&run(s).1), ["R2_horizontal_speed"]);

        // 6 degrees: cos = 0.99452 < 0.99619. Rotation about y by -90 - 6 deg: use the tilt directly.
        let mut s = upright(0.0);
        let (c, sn) = (0.994_521_895_368_273_4_f64, 0.104_528_463_267_653_47_f64);
        // Half angles of 6 degrees about y composed with the upright attitude.
        let tilt = Quat::new(
            ((1.0 + c) / 2.0).sqrt(),
            0.0,
            (sn / 2.0) / ((1.0 + c) / 2.0).sqrt(),
            0.0,
        );
        s.q = tilt.hamilton(s.q).normalized();
        assert!((tilt_cos(s.q) - c).abs() < 1e-9);
        assert_eq!(failed(&run(s).1), ["R3_tilt"]);

        let mut s = upright(0.0);
        s.w = Vec3::new(0.0, 0.0, 0.2);
        assert_eq!(failed(&run(s).1), ["R4_angular_rate"]);

        let mut s = upright(0.0);
        s.r.x = 12.0;
        assert_eq!(failed(&run(s).1), ["R5_position"]);

        let mut s = upright(0.0);
        s.mp = 0.5; // limit is 1% of 100 kg = 1 kg
        assert_eq!(failed(&run(s).1), ["R6_propellant_margin"]);
    }

    #[test]
    fn the_keep_out_zone_fails_together_with_r5() {
        let mut s = upright(0.0);
        s.r.x = 60.0;
        let (outcome, reqs, invs) = run(s);
        assert_eq!(outcome, "hard_landing");
        assert!(failed(&reqs).contains(&"R5_position"));
        let s2 = invs.iter().find(|i| i.id == "S2_keep_out").unwrap();
        assert!(!s2.pass && s2.failure_count == 1);
        let f = s2.first_failure.as_ref().unwrap();
        assert_eq!((f.step, f.cause.clone()), (1, vec!["gnss_bias"]));
        assert!((f.truth.base_position_m[0] - 60.0).abs() < 1e-9);
        // The mission outcome is separate: invariants S1, S3, S4 are unaffected.
        assert!(
            invs.iter()
                .filter(|i| i.id != "S2_keep_out")
                .all(|i| i.pass)
        );
    }

    #[test]
    fn without_contact_nothing_is_met_and_the_outcome_says_so() {
        let mut log = log_with(upright(10.0));
        log.touchdown = None;
        let (outcome, reqs, invs) = evaluate(&Requirements::registered(), &prepared(), &log);
        assert_eq!(outcome, "no_contact");
        assert!(
            reqs.iter()
                .all(|r| !r.pass && !r.evaluated && r.value.is_none())
        );
        let s2 = invs.iter().find(|i| i.id == "S2_keep_out").unwrap();
        assert!(s2.pass && !s2.evaluated);
    }

    fn thrusting_log(tilt_state: State, thrust_n: f64, steps: usize) -> TruthLog {
        let mk = |k: u64, thrust_n: f64| TruthStep {
            step: k,
            state: if k == 1 { tilt_state } else { upright(100.0) },
            thrust_n,
            direction: Vec3::new(1.0, 0.0, 0.0),
            active_faults: Vec::new(),
        };
        let steps: Vec<TruthStep> = (0..steps as u64).map(|k| mk(k, thrust_n)).collect();
        TruthLog {
            dt: 0.01,
            end_step: steps.len() as u64,
            end_state: upright(100.0),
            steps,
            touchdown: None,
        }
    }

    #[test]
    fn s1_s3_and_s4_detect_their_violations() {
        let req = Requirements::registered();
        // S3: 40 kN on 1050 kg is 38.1 m/s^2 = 3.88 g0 > 3 g0.
        let (_, _, invs) = evaluate(
            &req,
            &prepared(),
            &thrusting_log(upright(100.0), 40_000.0, 3),
        );
        let s3 = invs.iter().find(|i| i.id == "S3_axial_load").unwrap();
        assert!(!s3.pass && s3.failure_count == 3);
        assert!(s3.worst_value.unwrap() > 3.8);
        // 25 kN is 2.43 g0: fine, and one ignition.
        let (_, _, invs) = evaluate(
            &req,
            &prepared(),
            &thrusting_log(upright(100.0), 25_000.0, 3),
        );
        assert!(invs.iter().all(|i| i.pass), "{invs:?}");
        let s4 = invs.iter().find(|i| i.id == "S4_no_relight").unwrap();
        assert_eq!(s4.worst_value, Some(1.0));

        // S1: tilt the state of step 1 by 40 degrees about y (cos 0.766 < 0.866).
        let mut tilted = upright(100.0);
        let (c, sn) = (0.939_692_620_785_908_4_f64, 0.342_020_143_325_668_7_f64);
        let half = Quat::new(c, 0.0, sn, 0.0); // 40 degrees about y
        tilted.q = half.hamilton(tilted.q).normalized();
        assert!(tilt_cos(tilted.q) < 0.866);
        let (_, _, invs) = evaluate(&req, &prepared(), &thrusting_log(tilted, 25_000.0, 3));
        let s1 = invs.iter().find(|i| i.id == "S1_tilt_envelope").unwrap();
        assert!(!s1.pass, "{s1:?}");
        assert_eq!(s1.first_failure.as_ref().unwrap().step, 1);
        assert!(s1.worst_value.unwrap() < 0.8);
    }

    #[test]
    fn a_second_ignition_violates_s4() {
        let mut log = thrusting_log(upright(100.0), 25_000.0, 6);
        log.steps[2].thrust_n = 0.0;
        log.steps[3].thrust_n = 0.0;
        let (_, _, invs) = evaluate(&Requirements::registered(), &prepared(), &log);
        let s4 = invs.iter().find(|i| i.id == "S4_no_relight").unwrap();
        assert!(!s4.pass);
        assert_eq!((s4.worst_value, s4.failure_count), (Some(2.0), 1));
        assert_eq!(s4.first_failure.as_ref().unwrap().step, 4);
    }
}
