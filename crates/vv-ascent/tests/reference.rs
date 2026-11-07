//! Independent numerical references of the integrator (docs/m17-ascent.md, "Casos de referência").
//! Each compares the production RK4 step at the production `DT` with a closed form. The tolerances
//! are about ten times the errors measured on this code; the measured values are printed with
//! `cargo test -- --nocapture` and recorded in the document.

use vv_ascent::dynamics::{Aero, Body, Burn, Environment, Gravity, rk4_step};
use vv_ascent::math::Vec2;
use vv_ascent::model::{DT, G0, MU, R_EARTH, parse_case};

const NO_AERO: Aero = Aero {
    area_m2: 0.0,
    cd: 0.0,
};

/// (a) Vertical ascent without drag, constant thrust and mass flow, uniform gravity:
/// `v = ve ln(m0/m) - g t`, `h = ve (t - (m/mdot) ln(m0/m)) - g t^2/2`.
#[test]
fn vertical_ascent_matches_tsiolkovsky_with_gravity_loss() {
    let (m0, mdot, isp, g) = (10_000.0, 50.0, 300.0, G0);
    let ve = isp * G0;
    let env = Environment {
        gravity: Gravity::Uniform(Vec2::new(0.0, -g)),
        atmosphere: false,
    };
    let burn = Burn {
        direction: Vec2::new(0.0, 1.0),
        mdot,
        isp_vac_s: isp,
        isp_sl_s: isp,
    };
    let mut b = Body {
        r: Vec2::new(0.0, R_EARTH),
        v: Vec2::ZERO,
        m: m0,
    };
    let (mut worst_v, mut worst_h) = (0.0f64, 0.0f64);
    for step in 1..=7_500u32 {
        b = rk4_step(&env, &NO_AERO, Some(&burn), &b, DT);
        let t = f64::from(step) * DT;
        let m = m0 - mdot * t;
        let v = ve * (m0 / m).ln() - g * t;
        let h = ve * (t - (m / mdot) * (m0 / m).ln()) - 0.5 * g * t * t;
        worst_v = worst_v.max((b.v.z - v).abs());
        worst_h = worst_h.max((b.r.z - R_EARTH - h).abs());
        assert!((b.m - m).abs() < 1e-6, "mass {} vs {m}", b.m);
    }
    println!(
        "vertical ascent over 150 s: worst |dv| = {worst_v:.3e} m/s, worst |dh| = {worst_h:.3e} m"
    );
    assert!(worst_v < 1e-10, "velocity error {worst_v}");
    // Altitude reaches about 84 km; the error is dominated by the rounding of R_EARTH + h.
    assert!(worst_h < 5e-7, "altitude error {worst_h}");
}

/// (b) Vacuum Kepler coast over one orbit: specific energy and angular momentum conserved, period
/// against `2 pi sqrt(a^3 / mu)`.
#[test]
fn kepler_coast_conserves_energy_and_momentum_and_keeps_the_period() {
    let env = Environment {
        gravity: Gravity::InverseSquare,
        atmosphere: false,
    };
    let r0 = R_EARTH + 400e3;
    let v0 = 1.05 * (MU / r0).sqrt();
    let mut b = Body {
        r: Vec2::new(0.0, r0),
        v: Vec2::new(v0, 0.0),
        m: 1000.0,
    };
    let energy = |b: &Body| 0.5 * b.v.dot(b.v) - MU / b.r.norm();
    let e0 = energy(&b);
    let h0 = b.r.cross(b.v);
    let a = -MU / (2.0 * e0);
    let period = 2.0 * std::f64::consts::PI * (a * a * a / MU).sqrt();
    let (mut de, mut dh) = (0.0f64, 0.0f64);
    let mut crossing = None;
    let mut step = 0u64;
    let mut half = false;
    while step < (1.2 * period / DT) as u64 {
        let prev = b;
        b = rk4_step(&env, &NO_AERO, None, &b, DT);
        step += 1;
        de = de.max(((energy(&b) - e0) / e0).abs());
        dh = dh.max(((b.r.cross(b.v) - h0) / h0).abs());
        if b.r.z < 0.0 {
            half = true;
        }
        // Back through the +z axis, moving towards +x.
        if half && prev.r.x < 0.0 && b.r.x >= 0.0 && b.r.z > 0.0 {
            let f = -prev.r.x / (b.r.x - prev.r.x);
            crossing = Some((step as f64 - 1.0 + f) * DT);
            break;
        }
    }
    let t = crossing.expect("one full orbit");
    let dp = (t - period).abs();
    println!(
        "Kepler coast, a = {:.1} km, period {period:.3} s: |dE/E| = {de:.3e}, |dh/h| = {dh:.3e}, |dT| = {dp:.3e} s",
        a / 1000.0
    );
    assert!(de < 1e-12, "energy drift {de}");
    assert!(dh < 1e-12, "angular momentum drift {dh}");
    // The crossing time is a linear interpolation inside one 20 ms step.
    assert!(dp < 1e-6, "period error {dp} s");
}

/// (c) Ideal rocket equation per stage of both bundled vehicles: a full vacuum burn without
/// gravity gives `Isp g0 ln(m0 / mf)`.
#[test]
fn vacuum_burn_of_each_stage_matches_the_ideal_rocket_equation() {
    let env = Environment {
        gravity: Gravity::None,
        atmosphere: false,
    };
    for (id, text) in vv_ascent::CASES {
        let case = parse_case(text.as_bytes()).unwrap();
        let s = &case.vehicle.stages;
        let upper = s[1].dry_mass_kg + s[1].propellant_kg + case.vehicle.payload_kg;
        let stacks = [
            (s[0].clone(), upper),
            (s[1].clone(), case.vehicle.payload_kg),
        ];
        for (stage, above) in stacks {
            let m0 = stage.dry_mass_kg + stage.propellant_kg + above;
            let mf = m0 - stage.propellant_kg;
            let mdot = stage.thrust_vac_n / (stage.isp_vac_s * G0);
            let burn = Burn {
                direction: Vec2::new(1.0, 0.0),
                mdot,
                isp_vac_s: stage.isp_vac_s,
                isp_sl_s: stage.isp_sl_s,
            };
            let mut b = Body {
                r: Vec2::new(0.0, R_EARTH),
                v: Vec2::ZERO,
                m: m0,
            };
            let tb = stage.propellant_kg / mdot;
            let full = (tb / DT).floor() as u64;
            for _ in 0..full {
                b = rk4_step(&env, &NO_AERO, Some(&burn), &b, DT);
            }
            b = rk4_step(&env, &NO_AERO, Some(&burn), &b, tb - full as f64 * DT);
            let ideal = stage.isp_vac_s * G0 * (m0 / mf).ln();
            let err = (b.v.norm() - ideal).abs() / ideal;
            println!(
                "{id} {}: ideal {ideal:.4} m/s, integrated {:.4} m/s, relative error {err:.3e}",
                stage.id,
                b.v.norm()
            );
            assert!((b.m - mf).abs() < 1e-6 * mf);
            assert!(err < 1e-11, "{id} {}: {err}", stage.id);
        }
    }
}
