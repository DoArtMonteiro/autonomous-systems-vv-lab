//! Independent references for three quantities the verifier and the integrator report. The
//! reference side of each test uses only the standard library and literal constants: it never calls
//! `elements`, `density`, `drag`, `downrange` or any other function of the simulator that it checks.
//! The function under test is called once and compared with a closed form obtained by another route.
//! Measured differences are printed with `cargo test -- --nocapture` and recorded in docs/m17-ascent.md.

use vv_ascent::dynamics::{Aero, Body, Environment, Gravity, elements, rk4_step};
use vv_ascent::math::Vec2;
use vv_ascent::model::DT;
use vv_ascent::sim::impact_between;

/// Literal constants, not imported: standard gravitational parameter and mean radius of the Earth,
/// and the standard gravity used as the uniform field of the drag test.
const MU: f64 = 3.986_004_418e14;
const R: f64 = 6_371_000.0;
const RHO0: f64 = 1.225;

struct Conic {
    energy: f64,
    e: f64,
    periapsis_alt: f64,
    apoapsis_alt: Option<f64>,
    semi_major: f64,
}

/// Elements by vis-viva and the eccentricity vector: `a = 1 / (2/r - v^2/mu)`, `e = ((v^2 - mu/r) r
/// - (r.v) v) / mu`, `r_p = a (1 - e)` for every conic (negative `a` for a hyperbola) and
/// `r_a = a (1 + e)` for an ellipse. The simulator takes energy and angular momentum instead.
fn conic(r: [f64; 2], v: [f64; 2]) -> Conic {
    let rn = r[0].hypot(r[1]);
    let v2 = v[0] * v[0] + v[1] * v[1];
    let rv = r[0] * v[0] + r[1] * v[1];
    let k = v2 - MU / rn;
    let evec = [(k * r[0] - rv * v[0]) / MU, (k * r[1] - rv * v[1]) / MU];
    let e = evec[0].hypot(evec[1]);
    let inv_a = 2.0 / rn - v2 / MU;
    let a = 1.0 / inv_a;
    Conic {
        energy: -MU * inv_a / 2.0,
        e,
        periapsis_alt: a * (1.0 - e) - R,
        apoapsis_alt: (a > 0.0).then(|| a * (1.0 + e) - R),
        semi_major: a,
    }
}

fn states() -> Vec<(&'static str, [f64; 2], [f64; 2])> {
    let circular = (MU / (R + 300e3)).sqrt();
    let escape = (2.0 * MU / (R + 200e3)).sqrt();
    vec![
        (
            "eccentric ellipse, climbing",
            [0.0, R + 300e3],
            [8500.0, 600.0],
        ),
        (
            "eccentric ellipse, descending, retrograde",
            [3.0e6, 5.9e6],
            [-6500.0, -900.0],
        ),
        (
            "ellipse whose periapsis is below the surface",
            [0.0, R + 100e3],
            [5000.0, 800.0],
        ),
        (
            "just bound, 0.9999 of escape speed",
            [0.0, R + 200e3],
            [0.9999 * escape, 0.0],
        ),
        (
            "just unbound, 1.0001 of escape speed",
            [0.0, R + 200e3],
            [1.0001 * escape, 0.0],
        ),
        (
            "hyperbola, climbing",
            [0.0, R + 200e3],
            [11_500.0, 1000.0],
        ),
        (
            "hyperbola, descending",
            [4.0e6, 5.5e6],
            [-8000.0, -9000.0],
        ),
        (
            "slightly eccentric, 1.02 of circular speed",
            [0.0, R + 300e3],
            [1.02 * circular, 0.0],
        ),
    ]
}

#[test]
fn elements_agree_with_vis_viva_and_the_eccentricity_vector_on_bound_and_unbound_states() {
    let (mut worst_e, mut worst_alt, mut worst_energy) = (0.0f64, 0.0f64, 0.0f64);
    for (name, r, v) in states() {
        let want = conic(r, v);
        let got = elements(Vec2::new(r[0], r[1]), Vec2::new(v[0], v[1]));
        let de = (got.eccentricity - want.e).abs();
        let dp = (got.periapsis_alt_m - want.periapsis_alt).abs();
        let den = ((got.energy_j_kg - want.energy) / want.energy).abs();
        worst_e = worst_e.max(de);
        worst_alt = worst_alt.max(dp);
        worst_energy = worst_energy.max(den);
        assert!(de < 1e-9, "{name}: eccentricity {} vs {}", got.eccentricity, want.e);
        assert!(
            dp < 1e-3,
            "{name}: periapsis {} vs {}",
            got.periapsis_alt_m,
            want.periapsis_alt
        );
        assert!(den < 1e-9, "{name}: energy {} vs {}", got.energy_j_kg, want.energy);
        match (got.apoapsis_alt_m, want.apoapsis_alt) {
            (Some(g), Some(w)) => {
                let da = (g - w).abs();
                worst_alt = worst_alt.max(da);
                assert!(da < 1e-3 + 1e-11 * w.abs(), "{name}: apoapsis {g} vs {w}");
                let dsm = (got.semi_major_axis_m.unwrap() - want.semi_major).abs();
                assert!(dsm < 1e-3 + 1e-11 * want.semi_major, "{name}: semi-major axis");
            }
            (None, None) => assert!(got.semi_major_axis_m.is_none(), "{name}"),
            (g, w) => panic!("{name}: apoapsis {g:?} vs {w:?}: bound and unbound disagree"),
        }
        // The sign of the energy decides bound or unbound, in agreement with the reference.
        assert_eq!(got.energy_j_kg < 0.0, want.energy < 0.0, "{name}");
    }
    println!(
        "elements vs vis-viva: worst |de| = {worst_e:.2e}, worst altitude difference = {worst_alt:.2e} m, worst relative energy difference = {worst_energy:.2e}"
    );
}

#[test]
fn bound_and_unbound_classification_is_the_sign_of_the_energy() {
    let states = states();
    let unbound: Vec<&str> = states
        .iter()
        .filter(|(_, r, v)| conic(*r, *v).energy >= 0.0)
        .map(|(n, _, _)| *n)
        .collect();
    assert_eq!(
        unbound,
        [
            "just unbound, 1.0001 of escape speed",
            "hyperbola, climbing",
            "hyperbola, descending"
        ]
    );
    for (name, r, v) in states {
        let got = elements(Vec2::new(r[0], r[1]), Vec2::new(v[0], v[1]));
        assert_eq!(
            got.apoapsis_alt_m.is_none(),
            unbound.contains(&name),
            "{name}"
        );
    }
}

/// A body falling from rest under a uniform field with a constant air density (below the surface
/// the simulator's density is exactly the sea-level one) has the closed-form velocity
/// `v = vt tanh(g t / vt)` and drop `(vt^2 / g) ln cosh(g t / vt)`, with `vt = sqrt(2 m g / (rho Cd A))`.
#[test]
fn a_body_in_constant_density_air_follows_the_tanh_fall_to_its_terminal_velocity() {
    let g = 9.806_65;
    let (mass, cd, area) = (1000.0, 0.5, 2.0);
    let vt = (2.0 * mass * g / (RHO0 * cd * area)).sqrt();
    let env = Environment {
        gravity: Gravity::Uniform(Vec2::new(0.0, -g)),
        atmosphere: true,
    };
    let aero = Aero {
        area_m2: area,
        cd,
    };
    let z0 = R - 1.0e5;
    let mut b = Body {
        r: Vec2::new(0.0, z0),
        v: Vec2::ZERO,
        m: mass,
    };
    let (mut worst_v, mut worst_z) = (0.0f64, 0.0f64);
    for step in 1..=6000u32 {
        b = rk4_step(&env, &aero, None, &b, DT);
        let t = f64::from(step) * DT;
        let x = g * t / vt;
        let v = vt * x.tanh();
        let drop = vt * vt / g * x.cosh().ln();
        worst_v = worst_v.max((-b.v.z - v).abs());
        worst_z = worst_z.max((b.r.z - (z0 - drop)).abs());
        assert!(b.r.z < R, "the body must stay below the surface so the density is constant");
        assert_eq!(b.v.x, 0.0);
    }
    println!(
        "terminal velocity {vt:.4} m/s, reached {:.6} m/s after 120 s: worst |dv| = {worst_v:.2e} m/s, worst |dz| = {worst_z:.2e} m",
        -b.v.z
    );
    assert!(worst_v < 1e-7, "velocity difference {worst_v}");
    assert!(worst_z < 1e-5, "position difference {worst_z}");
    assert!((-b.v.z - vt).abs() < 1e-6 * vt, "terminal velocity not reached");
}

/// The interpolated impact point of `impact_between` against the analytic Kepler arc of a vacuum
/// fall: the swept true anomaly gives the downrange distance, Kepler's equation the time, and
/// vis-viva the speed, all at the radius of the surface.
#[test]
fn the_interpolated_impact_point_agrees_with_the_analytic_vacuum_arc() {
    let env = Environment {
        gravity: Gravity::InverseSquare,
        atmosphere: false,
    };
    let none = Aero {
        area_m2: 0.0,
        cd: 0.0,
    };
    for (r0, v0) in [
        ([0.0, R + 100e3], [5000.0, 800.0]),
        ([0.0, R + 100e3], [3000.0, 1500.0]),
    ] {
        let c = conic(r0, v0);
        let a = c.semi_major;
        let p = a * (1.0 - c.e * c.e);
        let nu_at = |radius: f64| ((p / radius - 1.0) / c.e).acos();
        // Climbing at the start: true anomaly in (0, pi); the impact is on the descending branch.
        let nu0 = nu_at(r0[1]);
        let nu1 = 2.0 * std::f64::consts::PI - nu_at(R);
        let mean = |nu: f64| {
            let ecc = 2.0 * ((1.0 - c.e).sqrt() * (nu / 2.0).sin())
                .atan2((1.0 + c.e).sqrt() * (nu / 2.0).cos());
            ecc - c.e * ecc.sin()
        };
        let n = (MU / (a * a * a)).sqrt();
        let mut dm = mean(nu1) - mean(nu0);
        if dm < 0.0 {
            dm += 2.0 * std::f64::consts::PI;
        }
        let want_t = dm / n;
        let want_downrange = R * (nu1 - nu0);
        let want_speed = (MU * (2.0 / R - 1.0 / a)).sqrt();

        let mut b = Body {
            r: Vec2::new(r0[0], r0[1]),
            v: Vec2::new(v0[0], v0[1]),
            m: 1000.0,
        };
        let mut tick = 0u64;
        let impact = loop {
            let next = rk4_step(&env, &none, None, &b, DT);
            if next.r.norm() < R {
                break impact_between(tick, &b, &next);
            }
            b = next;
            tick += 1;
            assert!(tick < 1_000_000, "no impact");
        };
        let (dt, dd, ds) = (
            (impact.t_s - want_t).abs(),
            (impact.downrange_m - want_downrange).abs(),
            (impact.speed_m_s - want_speed).abs(),
        );
        println!(
            "vacuum arc from {v0:?}: impact at {:.4} s, {:.3} km downrange, {:.3} m/s; |dt| = {dt:.2e} s, |d downrange| = {dd:.2e} m, |dv| = {ds:.2e} m/s",
            want_t,
            want_downrange / 1000.0,
            want_speed
        );
        assert_eq!(impact.tick, tick + 1);
        assert!(dt < 1e-6, "impact time {dt}");
        assert!(dd < 1e-3, "downrange {dd}");
        assert!(ds < 1e-6, "speed {ds}");
    }
}
