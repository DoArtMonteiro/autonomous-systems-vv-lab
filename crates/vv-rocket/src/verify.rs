//! Reference verification cases with the tolerances fixed in docs/m8-rocket-dynamics.md.

use serde::Serialize;

use crate::dynamics::{State, derivative, mass_properties};
use crate::math::{Quat, Vec3, exp};
use crate::model::{
    Atmosphere, Burn, CASE_SCHEMA, Case, Environment, G0, Initial, Prepared, Vehicle, prepare,
};
use crate::sim::simulate;

pub const REPORT_SCHEMA: &str = "vv-rocket-verification.v1";
const G: f64 = 9.80665;

#[derive(Clone, Debug, Serialize)]
pub struct Metric {
    pub name: String,
    pub value: f64,
    pub tolerance: Option<f64>,
    pub unit: &'static str,
    /// True only for a criterion that is met or a reported value; never for an invalid criterion.
    pub pass: bool,
    /// `pass`, `fail`, `invalid` (the criterion does not measure what it intends) or `reported`.
    pub status: &'static str,
    /// A criterion replaced by a later one keeps its status here and no longer decides the case.
    pub superseded_by: Option<&'static str>,
    pub note: Option<&'static str>,
}

#[derive(Clone, Debug, Serialize)]
pub struct CaseResult {
    pub id: &'static str,
    /// `PASS` if every active criterion passes, `FAIL` if one fails, `INVALID` if none is active.
    pub status: &'static str,
    pub title: &'static str,
    pub conditions: &'static str,
    pub reference: &'static str,
    pub metrics: Vec<Metric>,
    pub pass: bool,
    /// History of a pre-registered criterion that was not met or was invalid; the criterion is kept.
    pub diagnosis: Option<&'static str>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Gap {
    pub id: &'static str,
    pub status: &'static str,
    pub reason: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct Report {
    pub schema: &'static str,
    pub source_sha256: String,
    pub cases: Vec<CaseResult>,
    pub gaps: Vec<Gap>,
    pub cases_pass: usize,
    pub cases_fail: usize,
    pub cases_invalid: usize,
    pub all_pass: bool,
}

fn criterion(name: String, value: f64, tolerance: f64, unit: &'static str, pass: bool) -> Metric {
    Metric {
        name,
        value,
        tolerance: Some(tolerance),
        unit,
        pass,
        status: if pass { "pass" } else { "fail" },
        superseded_by: None,
        note: None,
    }
}

fn metric(name: &str, value: f64, tolerance: f64, unit: &'static str) -> Metric {
    criterion(name.into(), value, tolerance, unit, value <= tolerance)
}

/// Passes only for a strictly negative value.
fn negative(name: &str, value: f64, unit: &'static str) -> Metric {
    criterion(name.into(), value, 0.0, unit, value < 0.0)
}

/// Order-of-accuracy metrics pass inside a closed interval instead of below a bound.
fn order_metric(name: &str, value: f64, low: f64, high: f64) -> Metric {
    criterion(
        format!("{name} (accepted range [{low}, {high}])"),
        value,
        high,
        "1",
        (low..=high).contains(&value),
    )
}

/// Reported for evidence only; no criterion.
fn reported(name: String, value: f64, unit: &'static str) -> Metric {
    Metric {
        name: format!("{name} (reported)"),
        value,
        tolerance: None,
        unit,
        pass: true,
        status: "reported",
        superseded_by: None,
        note: None,
    }
}

fn superseded(mut m: Metric, by: &'static str) -> Metric {
    m.pass = false;
    m.superseded_by = Some(by);
    m
}

/// A criterion that does not measure what it intends: kept with its value, never counted.
fn invalid(mut m: Metric, note: &'static str) -> Metric {
    m.pass = false;
    m.status = "invalid";
    m.note = Some(note);
    m
}

fn result(
    id: &'static str,
    title: &'static str,
    conditions: &'static str,
    reference: &'static str,
    metrics: Vec<Metric>,
) -> CaseResult {
    let active: Vec<&Metric> = metrics
        .iter()
        .filter(|m| m.superseded_by.is_none() && matches!(m.status, "pass" | "fail"))
        .collect();
    let status = if active.iter().any(|m| m.status == "fail") {
        "FAIL"
    } else if active.is_empty() {
        "INVALID"
    } else {
        "PASS"
    };
    // A superseded criterion must name an active criterion of the same case, so a typo cannot retire it.
    for m in &metrics {
        if let Some(by) = m.superseded_by {
            assert!(
                active.iter().any(|a| a.name == by),
                "{id}: '{}' is superseded by '{by}', which is not an active criterion",
                m.name
            );
        }
    }
    let pass = status == "PASS";
    CaseResult {
        id,
        status,
        title,
        conditions,
        reference,
        metrics,
        pass,
        diagnosis: None,
    }
}

/// A rigid body with no propellant, no thrust, no atmosphere and no gravity.
pub fn base_case(dt: f64, duration: f64) -> Case {
    Case {
        schema: CASE_SCHEMA.into(),
        name: "reference".into(),
        dt_s: dt,
        duration_s: duration,
        record_every: (duration / dt).round() as u64,
        stop_at_ground: false,
        environment: Environment {
            gravity_mps2: 0.0,
            atmosphere: None,
        },
        vehicle: Vehicle {
            dry_mass_kg: 1.0,
            propellant_mass_kg: 0.0,
            dry_cm_station_m: 0.0,
            propellant_cm_station_m: 0.0,
            dry_inertia_kgm2: [1.0, 1.0, 1.0],
            propellant_inertia_kgm2: [0.0, 0.0, 0.0],
            max_thrust_n: 0.0,
            isp_s: 300.0,
            drag_coefficient: 0.0,
            reference_area_m2: 0.0,
        },
        initial: Initial {
            position_m: [0.0; 3],
            velocity_mps: [0.0; 3],
            attitude: [1.0, 0.0, 0.0, 0.0],
            angular_velocity_radps: [0.0; 3],
        },
        burns: Vec::new(),
    }
}

fn states(case: &Case) -> (Prepared, Vec<State>, f64) {
    let p = prepare(case).expect("reference case is valid");
    let run = simulate(&p, true).expect("reference case runs");
    (p, run.states, run.trace.summary.max_quaternion_drift)
}

fn ballistic() -> CaseResult {
    let mut c = base_case(0.01, 8.0);
    c.environment.gravity_mps2 = G;
    c.initial.position_m = [0.0, 0.0, 100.0];
    c.initial.velocity_mps = [30.0, -10.0, 40.0];
    let (p, xs, _) = states(&c);
    let g = Vec3::new(0.0, 0.0, -G);
    let (mut er, mut ev): (f64, f64) = (0.0, 0.0);
    for (k, s) in xs.iter().enumerate() {
        let t = k as f64 * p.dt;
        er = er.max((s.r - (p.r0 + p.v0 * t + g * (0.5 * t * t))).norm());
        ev = ev.max((s.v - (p.v0 + g * t)).norm());
    }
    result(
        "1-ballistic-vacuum",
        "Vacuum ballistic trajectory",
        "r0 = (0, 0, 100) m, v0 = (30, -10, 40) m/s, g = 9.80665 m/s², dt = 0.01 s, 8 s",
        "r = r0 + v0 t + g t²/2, v = v0 + g t",
        vec![
            metric("max position error", er, 1e-9, "m"),
            metric("max velocity error", ev, 1e-10, "m/s"),
        ],
    )
}

fn tsiolkovsky() -> CaseResult {
    let mut c = base_case(0.01, 50.0);
    c.vehicle.dry_mass_kg = 1000.0;
    c.vehicle.propellant_mass_kg = 500.0;
    c.vehicle.dry_cm_station_m = 3.0;
    c.vehicle.propellant_cm_station_m = 2.0;
    c.vehicle.dry_inertia_kgm2 = [100.0, 1000.0, 1000.0];
    c.vehicle.propellant_inertia_kgm2 = [50.0, 300.0, 300.0];
    c.vehicle.max_thrust_n = 20_000.0;
    c.vehicle.isp_s = 300.0;
    c.burns = vec![Burn {
        start_s: 0.0,
        end_s: 50.0,
        throttle: 1.0,
        direction_body: [1.0, 0.0, 0.0],
    }];
    let (_, xs, _) = states(&c);
    let end = xs.last().unwrap();
    let c_e = 300.0 * G0;
    let mdot = 20_000.0 / c_e;
    let (m0, t) = (1500.0, 50.0);
    let mf = m0 - mdot * t;
    let dv = c_e * (m0 / mf).ln();
    let x = c_e * (t + mf / mdot * (mf / m0).ln());
    let m_end = mass_properties(&c.vehicle, end.mp).mass;
    result(
        "2-tsiolkovsky",
        "Ideal rocket equation",
        "g = 0, m_dry = 1000 kg, m_p0 = 500 kg, T = 20 000 N along x_B, Isp = 300 s, 0 to 50 s, dt = 0.01 s",
        "Δv = Isp g0 ln(m0/mf), mf = m0 - ṁ t, x = c (t + (mf/ṁ) ln(mf/m0))",
        vec![
            metric("relative Δv error", ((end.v.x - dv) / dv).abs(), 1e-9, "1"),
            metric("final mass error", (m_end - mf).abs(), 1e-9, "kg"),
            metric(
                "relative position error",
                ((end.r.x - x) / x).abs(),
                1e-9,
                "1",
            ),
            metric(
                "transverse velocity",
                Vec3::new(0.0, end.v.y, end.v.z).norm(),
                1e-12,
                "m/s",
            ),
        ],
    )
}

/// Case 2 with the body yawed so that x_B points along (0.6, 0.8, 0): checks that thrust is
/// rotated by R(q) and not by its transpose. Added after the independent review.
fn tsiolkovsky_rotated() -> CaseResult {
    let mut c = base_case(0.01, 50.0);
    c.vehicle.dry_mass_kg = 1000.0;
    c.vehicle.propellant_mass_kg = 500.0;
    c.vehicle.dry_cm_station_m = 3.0;
    c.vehicle.propellant_cm_station_m = 2.0;
    c.vehicle.dry_inertia_kgm2 = [100.0, 1000.0, 1000.0];
    c.vehicle.propellant_inertia_kgm2 = [50.0, 300.0, 300.0];
    c.vehicle.max_thrust_n = 20_000.0;
    c.vehicle.isp_s = 300.0;
    // Rotation about z by θ with cos θ = 0.6: q = (cos θ/2, 0, 0, sin θ/2).
    c.initial.attitude = [0.8_f64.sqrt(), 0.0, 0.0, 0.2_f64.sqrt()];
    c.burns = vec![Burn {
        start_s: 0.0,
        end_s: 50.0,
        throttle: 1.0,
        direction_body: [1.0, 0.0, 0.0],
    }];
    let (_, xs, _) = states(&c);
    let end = xs.last().unwrap();
    let c_e = 300.0 * G0;
    let mdot = 20_000.0 / c_e;
    let (m0, t) = (1500.0, 50.0);
    let mf = m0 - mdot * t;
    let dv = c_e * (m0 / mf).ln();
    let x = c_e * (t + mf / mdot * (mf / m0).ln());
    let u = Vec3::new(0.6, 0.8, 0.0);
    result(
        "2b-tsiolkovsky-rotated",
        "Ideal rocket equation with a yawed attitude",
        "as case 2 with q = (√0.8, 0, 0, √0.2), so x_B points along (0.6, 0.8, 0) in N",
        "v = Δv (0.6, 0.8, 0), r = x (0.6, 0.8, 0)",
        vec![
            metric(
                "relative velocity vector error",
                (end.v - u * dv).norm() / dv,
                1e-9,
                "1",
            ),
            metric(
                "relative position vector error",
                (end.r - u * x).norm() / x,
                1e-9,
                "1",
            ),
        ],
    )
}

/// A gimballed burn that turns the stage about one principal axis: checks the sign and size of
/// the thrust moment with İω and jet damping, the attitude it produces and the thrust it turns,
/// against a planar model written from the geometry, not from dynamics.rs. Added after the first
/// independent review; criteria revised in the second round (docs/m8-rocket-dynamics.md).
fn gimbal_torque() -> CaseResult {
    let mut c = burning_case([0.0, 0.0, 0.0]);
    c.burns[0].direction_body = [1.0, 0.05, 0.0];
    let (p, xs, _) = states(&c);
    let thrust = 2000.0;
    let mdot = thrust / (200.0 * G0);
    let delta = 0.05_f64.atan();
    let sin_d = 0.05 / (1.0_f64 + 0.05 * 0.05).sqrt();
    let cm = |mp: f64| (100.0 * 2.0 + mp * 1.5) / (100.0 + mp);
    let izz = |mp: f64| {
        let x = cm(mp);
        100.0 + 100.0 * (2.0 - x) * (2.0 - x) + 40.0 * mp / 50.0 + mp * (1.5 - x) * (1.5 - x)
    };
    // A sideways force +y at the tail, a distance cm behind the centre of mass, yaws the nose to -y:
    // M_z = -cm T sin δ. With ω on z only, d(I_zz ω)/dt = M_z - ṁ cm² ω; the nose is at ψ from x_N and
    // the thrust at ψ + δ. State: (I_zz ω_z, ψ, v_x, v_y).
    let rate = |t: f64, y: [f64; 4]| {
        let mp = 50.0 - mdot * t;
        let (s, i) = (cm(mp), izz(mp));
        let a = thrust / (100.0 + mp);
        [
            -s * thrust * sin_d - mdot * s * s * y[0] / i,
            y[0] / i,
            a * (y[1] + delta).cos(),
            a * (y[1] + delta).sin(),
        ]
    };
    let add =
        |y: [f64; 4], k: [f64; 4], h: f64| -> [f64; 4] { std::array::from_fn(|n| y[n] + h * k[n]) };
    let fine = p.dt / 100.0;
    let mut y = [0.0; 4];
    let mut reference = vec![y];
    for k in 1..xs.len() {
        for j in 0..100 {
            let t = (k - 1) as f64 * p.dt + j as f64 * fine;
            let k1 = rate(t, y);
            let k2 = rate(t + fine / 2.0, add(y, k1, fine / 2.0));
            let k3 = rate(t + fine / 2.0, add(y, k2, fine / 2.0));
            let k4 = rate(t + fine, add(y, k3, fine));
            y = std::array::from_fn(|n| {
                y[n] + fine / 6.0 * (k1[n] + 2.0 * k2[n] + 2.0 * k3[n] + k4[n])
            });
        }
        reference.push(y);
    }

    let mut momentum: f64 = 0.0;
    for (s, r) in xs.iter().zip(&reference).skip(1) {
        let sim = mass_properties(&c.vehicle, s.mp).inertia.z * s.w.z;
        momentum = momentum.max((sim - r[0]).abs() / r[0].abs());
    }
    let nose = |s: &State| s.q.rotate(Vec3::new(1.0, 0.0, 0.0));
    let end = xs.last().unwrap();

    // Criterion 1: the initial angular acceleration, from the model's derivative at t = 0.
    let accel = derivative(&p, &xs[0], p.segments.first()).w.z;
    let expected = -cm(50.0) * thrust * sin_d / izz(50.0);

    // Criteria 2a and 2b: the window [0, 1] s, where the planar model turns less than π/2.
    let window = (1.0 / p.dt).round() as usize;
    let max_turn = reference[..=window]
        .iter()
        .map(|r| r[1].abs())
        .fold(0.0, f64::max);
    let nose_y = xs[1..=window]
        .iter()
        .map(|s| nose(s).y)
        .fold(f64::NEG_INFINITY, f64::max);
    let nose_err = xs[..=window]
        .iter()
        .zip(&reference)
        .map(|(s, r)| (nose(s) - Vec3::new(r[1].cos(), r[1].sin(), 0.0)).norm())
        .fold(0.0, f64::max);
    let mut window_metrics = vec![
        negative(
            "largest nose y_N component on (0, 1] s (must be negative)",
            nose_y,
            "1",
        ),
        metric(
            "max nose direction error against the planar model on [0, 1] s",
            nose_err,
            1e-9,
            "1",
        ),
    ];
    if max_turn > std::f64::consts::FRAC_PI_2 {
        window_metrics = window_metrics
            .into_iter()
            .map(|m| {
                invalid(
                    m,
                    "precondition failed: the planar model turns more than π/2 in [0, 1] s",
                )
            })
            .collect();
    }

    // Criterion 3: the thrust turned by the attitude over the whole burn.
    let speed = reference
        .iter()
        .map(|r| r[2].hypot(r[3]))
        .fold(0.0, f64::max);
    let velocity_err = xs
        .iter()
        .zip(&reference)
        .map(|(s, r)| (s.v - Vec3::new(r[2], r[3], 0.0)).norm())
        .fold(0.0, f64::max)
        / speed;

    let yaw: f64 = xs
        .windows(2)
        .map(|w| 0.5 * (w[0].w.z + w[1].w.z) * p.dt)
        .sum();
    let mut metrics = vec![
        metric("max relative error of I_zz ω_z", momentum, 1e-8, "1"),
        metric(
            "final ω_x and ω_y magnitude",
            Vec3::new(end.w.x, end.w.y, 0.0).norm(),
            1e-15,
            "rad/s",
        ),
        invalid(
            metric(
                "final nose y_N component (must not be positive)",
                nose(end).y,
                0.0,
                "1",
            ),
            "the stage turns about 9.5 times in 10 s, so the final nose direction carries no sign information",
        ),
        metric(
            "relative error of the initial angular acceleration ω̇_z(0) against -s_cm T sin δ / I_zz",
            ((accel - expected) / expected).abs(),
            1e-12,
            "1",
        ),
    ];
    metrics.extend(window_metrics);
    metrics.extend([
        metric(
            "max velocity error against the planar model over 10 s, relative to its largest speed",
            velocity_err,
            1e-5,
            "1",
        ),
        reported(
            "initial angular acceleration ω̇_z(0)".into(),
            accel,
            "rad/s²",
        ),
        reported(
            "largest |ψ| of the planar model on [0, 1] s".into(),
            max_turn,
            "rad",
        ),
        reported("final yaw rate ω_z".into(), end.w.z, "rad/s"),
        reported(
            "yaw angle turned in 10 s (trapezoid of ω_z)".into(),
            yaw,
            "rad",
        ),
        reported(
            "nose y_N component at t = 0.5 s".into(),
            nose(&xs[50]).y,
            "1",
        ),
    ]);
    let mut case = result(
        "8-gimbal-torque",
        "Gimballed thrust moment about one principal axis",
        "as 7a with ω0 = 0 and direction_body = (1, 0.05, 0), 10 s",
        "planar model from the geometry, RK4 with dt/100: d(I_zz ω_z)/dt = -s_cm T sin δ - ṁ_e s_cm² ω_z, dψ/dt = ω_z, dv/dt = (T/m)(cos(ψ+δ), sin(ψ+δ)); the nose turns towards -y_N; verifies the implementation of the stated hypothesis, not the hypothesis",
        metrics,
    );
    case.diagnosis = Some(
        "First run: the criterion 'final nose y_N component must not be positive' was not met (0.094) and is \
         kept here as invalid, not as a pass: after about 9.5 turns the final nose direction carries no sign \
         information. Second round: criteria on the initial angular acceleration, the nose direction in [0, 1] s \
         (less than π/2 of turn) and the turned thrust over 10 s were registered before they were run.",
    );
    case
}

fn torque_free_asymmetric() -> (CaseResult, f64) {
    let mut c = base_case(0.001, 20.0);
    c.vehicle.dry_inertia_kgm2 = [2.0, 3.0, 4.0];
    c.initial.angular_velocity_radps = [1.0, 0.2, 0.5];
    let (_, xs, drift) = states(&c);
    let i = Vec3::new(2.0, 3.0, 4.0);
    let energy = |s: &State| 0.5 * s.w.dot(i.hadamard(s.w));
    let momentum = |s: &State| s.q.rotate(i.hadamard(s.w));
    let (e0, h0) = (energy(&xs[0]), momentum(&xs[0]));
    let (mut de, mut dh): (f64, f64) = (0.0, 0.0);
    let mut norm: f64 = 0.0;
    for s in &xs {
        de = de.max(((energy(s) - e0) / e0).abs());
        dh = dh.max((momentum(s) - h0).norm() / h0.norm());
        norm = norm.max((s.q.norm() - 1.0).abs());
    }
    let case = result(
        "3a-torque-free-asymmetric",
        "Torque-free asymmetric rigid body",
        "I = diag(2, 3, 4) kg m², ω0 = (1.0, 0.2, 0.5) rad/s, no propellant, dt = 0.001 s, 20 s",
        "rotational energy and inertial angular momentum H_N = R(q) I ω are constant",
        vec![
            metric("max relative energy drift", de, 1e-9, "1"),
            metric("max relative angular momentum drift", dh, 1e-9, "1"),
        ],
    );
    (case, drift.max(norm))
}

fn precession() -> CaseResult {
    let mut c = base_case(0.001, 10.0);
    c.vehicle.dry_inertia_kgm2 = [2.0, 1.0, 1.0];
    c.initial.angular_velocity_radps = [2.0, 0.3, 0.0];
    let (p, xs, _) = states(&c);
    let mut err: f64 = 0.0;
    for (k, s) in xs.iter().enumerate() {
        let t = k as f64 * p.dt;
        let want = Vec3::new(2.0, 0.3 * (2.0 * t).cos(), 0.3 * (2.0 * t).sin());
        err = err.max((s.w - want).norm());
    }
    result(
        "3b-axisymmetric-precession",
        "Torque-free precession of an axisymmetric body",
        "I = diag(2, 1, 1) kg m², ω0 = (2, 0.3, 0) rad/s, dt = 0.001 s, 10 s",
        "ω_y = 0.3 cos 2t, ω_z = 0.3 sin 2t, ω_x = 2",
        vec![metric("max angular velocity error", err, 1e-10, "rad/s")],
    )
}

fn quaternions(projected_norm_and_drift: f64) -> CaseResult {
    let quats = [
        Quat::new(1.0, 0.0, 0.0, 0.0),
        Quat::new(0.3, -0.5, 0.7, 0.2).normalized(),
        Quat::new(-0.9, 0.1, 0.4, -0.2).normalized(),
        Quat::new(0.0, 0.0, 0.0, 1.0),
    ];
    let vs = [
        Vec3::new(1.0, 0.0, 0.0),
        Vec3::new(-3.0, 2.5, 0.75),
        Vec3::new(1e3, -2e3, 5e2),
    ];
    let (mut roundtrip, mut ortho, mut compose): (f64, f64, f64) = (0.0, 0.0, 0.0);
    for q in quats {
        for v in vs {
            roundtrip = roundtrip.max((q.rotate_inverse(q.rotate(v)) - v).norm() / v.norm());
            for q2 in quats {
                let lhs = q.hamilton(q2).rotate(v);
                compose = compose.max((lhs - q.rotate(q2.rotate(v))).norm() / v.norm());
            }
        }
        let e = [
            q.rotate(Vec3::new(1.0, 0.0, 0.0)),
            q.rotate(Vec3::new(0.0, 1.0, 0.0)),
            q.rotate(Vec3::new(0.0, 0.0, 1.0)),
        ];
        for a in 0..3 {
            for b in 0..3 {
                let want = if a == b { 1.0 } else { 0.0 };
                ortho = ortho.max((e[a].dot(e[b]) - want).abs());
            }
        }
        // A right-handed frame stays right-handed.
        ortho = ortho.max((e[0].cross(e[1]) - e[2]).norm());
    }
    let h = 0.5_f64.sqrt();
    let known = (Quat::new(h, 0.0, 0.0, h).rotate(Vec3::new(1.0, 0.0, 0.0))
        - Vec3::new(0.0, 1.0, 0.0))
    .norm()
    .max(
        (Quat::new(h, 0.0, -h, 0.0).rotate(Vec3::new(1.0, 0.0, 0.0)) - Vec3::new(0.0, 0.0, 1.0))
            .norm(),
    );

    let (dq, norm, drift) = constant_rotation(0.01);
    let dq_half = constant_rotation(0.005).0;
    // Evidence: the error at other step sizes, its observed order and the truncation estimate.
    let series: Vec<(f64, f64)> = [
        (0.02, constant_rotation(0.02).0),
        (0.01, dq),
        (0.005, dq_half),
        (0.0025, constant_rotation(0.0025).0),
    ]
    .to_vec();
    let mut evidence: Vec<Metric> = [series[0], series[3]]
        .iter()
        .map(|(dt, e)| {
            reported(
                format!("max attitude error against q(t) at dt = {dt} s"),
                *e,
                "1",
            )
        })
        .collect();
    for pair in [[series[0], series[1]], [series[2], series[3]]] {
        evidence.push(reported(
            format!("observed order {}/{}", pair[0].0, pair[1].0),
            (pair[0].1 / pair[1].1).log2(),
            "1",
        ));
    }
    // One RK4 step of the linear q̇ = ½ q ⊗ (0, ω) leaves a phase error θ⁵/120 with θ = ω h / 2.
    for h in [0.01_f64, 0.005] {
        evidence.push(reported(
            format!("truncation estimate T (ω/2)⁵ h⁴ / 120 at dt = {h} s"),
            20.0 * 0.25_f64.powi(5) * h.powi(4) / 120.0,
            "1",
        ));
    }
    const REVISED: &str = "max attitude error against q(t) at dt = 0.005 s";
    let mut case = result(
        "4-quaternions-and-frames",
        "Quaternion algebra, frame transforms and attitude kinematics",
        "fixed quaternions and vectors; constant ω = (0, 0, 0.5) rad/s about a principal axis, 20 s, dt = 0.005 s (first run dt = 0.01 s); norm drift at dt = 0.01 s and over case 3a",
        "R(q)ᵀR(q)v = v, R(q1⊗q2) = R(q1)R(q2), q(t) = (cos(ωt/2), 0, 0, sin(ωt/2))",
        vec![
            metric("max relative round-trip error", roundtrip, 1e-14, "1"),
            metric("max orthonormality and handedness error", ortho, 1e-14, "1"),
            metric("max relative composition error", compose, 1e-14, "1"),
            metric("known 90° rotations error", known, 1e-15, "1"),
            superseded(
                metric(
                    "max attitude error against q(t) at dt = 0.01 s (first run)",
                    dq,
                    1e-12,
                    "1",
                ),
                REVISED,
            ),
            metric(REVISED, dq_half, 1e-12, "1"),
            order_metric("observed order 0.01/0.005", (dq / dq_half).log2(), 3.6, 4.4),
            metric("max norm error after projection", norm, 1e-14, "1"),
            metric(
                "max norm drift per step before projection",
                drift.max(projected_norm_and_drift),
                1e-12,
                "1",
            ),
        ]
        .into_iter()
        .chain(evidence)
        .collect(),
    );
    case.diagnosis = Some(
        "First run: the limit of 1e-12 on the attitude error against q(t) at dt = 0.01 s was not met (fail, kept \
         and superseded). The error falls by about 16 for each halving of dt and matches the RK4 truncation \
         estimate (reported), so it is truncation of order 4, not a model error. Second round, by owner decision: \
         the same limit at dt = 0.005 s. That value and the 0.01/0.005 order were already in the first run's \
         evidence, so the revised criterion is not blind; only the step was chosen again, not the limit.",
    );
    case
}

/// Max attitude error against the closed form, max norm error after projection and max drift
/// before projection, for a constant rotation about a principal axis.
fn constant_rotation(dt: f64) -> (f64, f64, f64) {
    let mut c = base_case(dt, 20.0);
    c.vehicle.dry_inertia_kgm2 = [2.0, 3.0, 4.0];
    c.initial.angular_velocity_radps = [0.0, 0.0, 0.5];
    let (p, xs, drift) = states(&c);
    let mut dq: f64 = 0.0;
    let mut norm: f64 = 0.0;
    for (k, s) in xs.iter().enumerate() {
        let a = 0.25 * k as f64 * p.dt;
        let want = Quat::new(a.cos(), 0.0, 0.0, a.sin());
        dq = dq.max(
            [
                s.q.w - want.w,
                s.q.x - want.x,
                s.q.y - want.y,
                s.q.z - want.z,
            ]
            .iter()
            .map(|d| d * d)
            .sum::<f64>()
            .sqrt(),
        );
        norm = norm.max((s.q.norm() - 1.0).abs());
    }
    (dq, norm, drift)
}

/// The coupled case of the convergence study: gravity, exponential atmosphere, a gimballed burn
/// with torque, variable mass and initial rotation; no event inside the window.
pub fn coupled_case(dt: f64) -> Case {
    let mut c = base_case(dt, 4.0);
    c.environment.gravity_mps2 = G;
    c.environment.atmosphere = Some(Atmosphere {
        density_kgpm3: 1.225,
        scale_height_m: Some(8500.0),
    });
    c.vehicle = Vehicle {
        dry_mass_kg: 500.0,
        propellant_mass_kg: 200.0,
        dry_cm_station_m: 4.0,
        propellant_cm_station_m: 3.0,
        dry_inertia_kgm2: [50.0, 400.0, 400.0],
        propellant_inertia_kgm2: [20.0, 100.0, 100.0],
        max_thrust_n: 15_000.0,
        isp_s: 250.0,
        drag_coefficient: 0.5,
        reference_area_m2: 1.0,
    };
    let h = 0.5_f64.sqrt();
    c.initial = Initial {
        position_m: [0.0, 0.0, 1000.0],
        velocity_mps: [50.0, 0.0, 100.0],
        attitude: [h, 0.0, -h, 0.0],
        angular_velocity_radps: [0.1, 0.0, 0.05],
    };
    c.burns = vec![Burn {
        start_s: 0.0,
        end_s: 4.0,
        throttle: 1.0,
        direction_body: [1.0, 0.02, -0.01],
    }];
    c
}

fn convergence() -> CaseResult {
    let final_state = |dt: f64| *states(&coupled_case(dt)).1.last().unwrap();
    let reference = final_state(0.000_625);
    let dts = [0.04, 0.02, 0.01, 0.005];
    let errors: Vec<f64> = dts
        .iter()
        .map(|&dt| (final_state(dt).r - reference.r).norm())
        .collect();
    let order = |a: f64, b: f64| (a / b).log2();
    let mut metrics = vec![
        order_metric(
            "observed order 0.04/0.02",
            order(errors[0], errors[1]),
            3.6,
            4.4,
        ),
        order_metric(
            "observed order 0.02/0.01",
            order(errors[1], errors[2]),
            3.6,
            4.4,
        ),
    ];
    for (dt, e) in dts.iter().zip(&errors) {
        metrics.push(reported(
            format!("final position error at dt = {dt} s"),
            *e,
            "m",
        ));
    }
    metrics.push(reported(
        "observed order 0.01/0.005".into(),
        order(errors[2], errors[3]),
        "1",
    ));
    // Size of the translational term the model neglects, -ṁ_e ω × r_e, along the dt = 0.01 s run:
    // its ratio to the thrust is |ω × r_e| / c_e (docs/m8-rocket-dynamics.md).
    let c = coupled_case(0.01);
    let mdot = c.vehicle.max_thrust_n / (c.vehicle.isp_s * G0);
    let neglected = states(&c)
        .1
        .iter()
        .map(|s| {
            let r_e = Vec3::new(-mass_properties(&c.vehicle, s.mp).cm_station, 0.0, 0.0);
            s.w.cross(r_e).norm() * mdot
        })
        .fold(0.0, f64::max);
    metrics.push(reported(
        "largest neglected rigid-content jet term |ṁ_e ω × r_e|; the internal flow adds a Coriolis term of the same size".into(),
        neglected,
        "N",
    ));
    metrics.push(reported(
        "largest ratio of that term to the thrust (the total neglected term is about twice this)"
            .into(),
        neglected / c.vehicle.max_thrust_n,
        "1",
    ));
    result(
        "5-convergence",
        "RK4 convergence on a coupled 6-DOF case",
        "gravity, exponential atmosphere, gimballed thrust with torque, variable mass, ω0 ≠ 0, 4 s, no events inside",
        "solution with dt = 0.000625 s",
        metrics,
    )
}

fn terminal_velocity() -> CaseResult {
    let mut c = base_case(0.01, 30.0);
    c.environment.gravity_mps2 = G;
    c.environment.atmosphere = Some(Atmosphere {
        density_kgpm3: 1.2,
        scale_height_m: None,
    });
    c.vehicle.dry_mass_kg = 10.0;
    c.vehicle.drag_coefficient = 1.0;
    c.vehicle.reference_area_m2 = 0.5;
    c.initial.position_m = [0.0, 0.0, 2000.0];
    let (p, xs, _) = states(&c);
    let vt = (2.0 * 10.0 * G / (1.2 * 1.0 * 0.5)).sqrt();
    let (mut ev, mut ez): (f64, f64) = (0.0, 0.0);
    for (k, s) in xs.iter().enumerate() {
        let t = k as f64 * p.dt;
        let v = -vt * (G * t / vt).tanh();
        let z = 2000.0 - vt * vt / G * (G * t / vt).cosh().ln();
        ev = ev.max((s.v.z - v).abs() / vt);
        ez = ez.max((s.r.z - z).abs());
    }
    result(
        "6a-terminal-velocity",
        "Fall with quadratic drag at constant density",
        "ρ = 1.2 kg/m³, C_D = 1, A = 0.5 m², m = 10 kg, from rest at 2000 m, dt = 0.01 s, 30 s",
        "v = -v_t tanh(g t / v_t), z = z0 - (v_t²/g) ln cosh(g t / v_t), v_t = √(2mg/(ρ C_D A))",
        vec![
            metric("max velocity error relative to v_t", ev, 1e-8, "1"),
            metric("max altitude error", ez, 1e-6, "m"),
        ],
    )
}

fn deterministic_exp() -> CaseResult {
    let mut worst: f64 = 0.0;
    let mut k = 0;
    loop {
        let x = -12.0 + k as f64 * 0.000_7;
        if x > 2.0 {
            break;
        }
        let want = x.exp();
        worst = worst.max(((exp(x) - want) / want).abs());
        k += 1;
    }
    result(
        "6b-deterministic-exp",
        "Arithmetic-only exp used by the atmosphere",
        "x from -12 to 2 in steps of 0.0007",
        "platform f64::exp",
        vec![metric("max relative error", worst, 1e-15, "1")],
    )
}

fn burning_case(w0: [f64; 3]) -> Case {
    let mut c = base_case(0.01, 10.0);
    c.vehicle = Vehicle {
        dry_mass_kg: 100.0,
        propellant_mass_kg: 50.0,
        dry_cm_station_m: 2.0,
        propellant_cm_station_m: 1.5,
        dry_inertia_kgm2: [10.0, 100.0, 100.0],
        propellant_inertia_kgm2: [5.0, 40.0, 40.0],
        max_thrust_n: 2000.0,
        isp_s: 200.0,
        drag_coefficient: 0.0,
        reference_area_m2: 0.0,
    };
    c.initial.angular_velocity_radps = w0;
    c.burns = vec![Burn {
        start_s: 0.0,
        end_s: 10.0,
        throttle: 1.0,
        direction_body: [1.0, 0.0, 0.0],
    }];
    c
}

fn variable_mass_roll() -> CaseResult {
    let c = burning_case([1.0, 0.0, 0.0]);
    let (_, xs, _) = states(&c);
    let h = |s: &State| mass_properties(&c.vehicle, s.mp).inertia.x * s.w.x;
    let h0 = h(&xs[0]);
    let drift = xs
        .iter()
        .map(|s| ((h(s) - h0) / h0).abs())
        .fold(0.0, f64::max);
    let spin_up = xs.last().unwrap().w.x;
    result(
        "7a-variable-mass-roll",
        "Roll with propellant depletion and no torque",
        "g = 0, m_dry = 100 kg, m_p0 = 50 kg, I_dry = diag(10, 100, 100), I_p0 = diag(5, 40, 40), s_dry = 2 m, s_p = 1.5 m, T = 2000 N, Isp = 200 s, ω0 = (1, 0, 0) rad/s, 10 s",
        "I_xx ω_x is constant (exhaust leaves on the axis)",
        vec![
            metric("max relative drift of I_xx ω_x", drift, 1e-9, "1"),
            reported(
                "final roll rate, rising as I_xx falls".into(),
                spin_up,
                "rad/s",
            ),
        ],
    )
}

fn jet_damping() -> CaseResult {
    let c = burning_case([0.0, 0.2, 0.0]);
    let (p, xs, _) = states(&c);
    // Independent scalar model written from the hypotheses, not from dynamics.rs.
    let mdot = 2000.0 / (200.0 * G0);
    let cm = |mp: f64| (100.0 * 2.0 + mp * 1.5) / (100.0 + mp);
    let iyy = |mp: f64| {
        let x = cm(mp);
        100.0 + 100.0 * (2.0 - x) * (2.0 - x) + 40.0 * mp / 50.0 + mp * (1.5 - x) * (1.5 - x)
    };
    let rate = |t: f64, h: f64| {
        let mp = 50.0 - mdot * t;
        let re = cm(mp);
        -mdot * re * re * h / iyy(mp)
    };
    let fine = p.dt / 100.0;
    let mut h = iyy(50.0) * 0.2;
    let mut worst: f64 = 0.0;
    for (k, s) in xs.iter().enumerate().skip(1) {
        for j in 0..100 {
            let t = (k - 1) as f64 * p.dt + j as f64 * fine;
            let k1 = rate(t, h);
            let k2 = rate(t + fine / 2.0, h + fine / 2.0 * k1);
            let k3 = rate(t + fine / 2.0, h + fine / 2.0 * k2);
            let k4 = rate(t + fine, h + fine * k3);
            h += fine / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
        }
        let sim = mass_properties(&c.vehicle, s.mp).inertia.y * s.w.y;
        worst = worst.max(((sim - h) / h).abs());
    }
    result(
        "7b-jet-damping",
        "Pitch rate with propellant depletion: İω and jet damping terms",
        "as 7a with ω0 = (0, 0.2, 0) rad/s",
        "scalar RK4 of d(I_yy ω)/dt = -ṁ_e r_e² ω with dt/100 and independently written mass properties; checks the implementation of the İω and jet-damping terms against the stated hypothesis, not the hypothesis itself",
        vec![metric("max relative error of I_yy ω_y", worst, 1e-8, "1")],
    )
}

pub fn run_all() -> Report {
    let (asym, drift) = torque_free_asymmetric();
    let cases = vec![
        ballistic(),
        tsiolkovsky(),
        asym,
        precession(),
        quaternions(drift),
        convergence(),
        terminal_velocity(),
        deterministic_exp(),
        variable_mass_roll(),
        jet_damping(),
        tsiolkovsky_rotated(),
        gimbal_torque(),
    ];
    let count = |status: &str| cases.iter().filter(|c| c.status == status).count();
    let (cases_pass, cases_fail, cases_invalid) = (count("PASS"), count("FAIL"), count("INVALID"));
    let all_pass = cases_pass == cases.len();
    Report {
        schema: REPORT_SCHEMA,
        source_sha256: crate::source_sha256(),
        cases,
        gaps: vec![
            Gap {
                id: "flight-data-validation",
                status: "not validated",
                reason: "No comparison with measured flight data. The cases verify the implementation of the stated equations against analytic or independently written references; they do not show that the equations describe a real vehicle.",
            },
            Gap {
                id: "nasa-nesc-6dof",
                status: "not verified",
                reason: "No NASA/TM-2015-218675 check case is compared: the published reference trajectories are not in the repository and cannot be downloaded in this milestone. Most of those cases also need an environment this model does not have (WGS-84 Earth, J2 gravity, US 1976 atmosphere); cases that may be compatible, such as the tumbling-brick cases, still need their reference data. Cases 3a and 3b cover the torque-free rotational equivalent with analytic references.",
            },
        ],
        cases_pass,
        cases_fail,
        cases_invalid,
        all_pass,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn status(metrics: Vec<Metric>) -> &'static str {
        result("t", "t", "t", "t", metrics).status
    }

    #[test]
    fn invalid_and_superseded_criteria_never_decide_a_case() {
        let pass = || metric("a", 0.5, 1.0, "1");
        let fail = || metric("b", 2.0, 1.0, "1");
        assert_eq!(status(vec![pass()]), "PASS");
        assert_eq!(status(vec![pass(), fail()]), "FAIL");
        assert_eq!(status(vec![pass(), superseded(fail(), "a")]), "PASS");
        assert_eq!(status(vec![invalid(pass(), "n")]), "INVALID");
        assert_eq!(
            status(vec![invalid(fail(), "n"), reported("r".into(), 1.0, "1")]),
            "INVALID"
        );
        assert!(!invalid(pass(), "n").pass);
        assert!(negative("n", -1e-300, "1").pass && !negative("n", 0.0, "1").pass);
    }

    #[test]
    #[should_panic(expected = "not an active criterion")]
    fn a_superseded_criterion_must_name_an_active_one() {
        status(vec![superseded(metric("b", 2.0, 1.0, "1"), "missing")]);
    }
}
