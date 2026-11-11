//! Planar 3-DOF point-mass dynamics of one body: position and velocity in the inertial plane and
//! mass. Forces: gravity (inverse-square for the mission, uniform or none for reference cases),
//! drag in an exponential atmosphere fixed to a non-rotating Earth, and thrust whose magnitude
//! follows the ambient pressure at a fixed mass flow. One fixed-step classical RK4 step per tick;
//! the thrust direction and the mass flow are held over the step (zero-order hold of the command).

use crate::math::{Vec2, exp};
use crate::model::{G0, MU, R_EARTH, RHO0, SCALE_HEIGHT};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Body {
    pub r: Vec2,
    pub v: Vec2,
    pub m: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Gravity {
    /// `-mu r / |r|^3`, the mission model.
    InverseSquare,
    /// A constant vector, for the closed-form vertical-ascent reference.
    Uniform(Vec2),
    /// No gravity, for the ideal rocket-equation reference.
    None,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Environment {
    pub gravity: Gravity,
    pub atmosphere: bool,
}

impl Environment {
    pub const MISSION: Environment = Environment {
        gravity: Gravity::InverseSquare,
        atmosphere: true,
    };
}

/// Aerodynamic properties of a body: drag `0.5 rho |v|^2 Cd A` opposite to the velocity (the
/// atmosphere does not rotate, so the air-relative velocity is the inertial velocity).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Aero {
    pub area_m2: f64,
    pub cd: f64,
}

/// Engine state over one step: unit direction, mass flow and the Isp pair that sets the thrust
/// `mdot g0 Isp(p)`, with `Isp(p) = Isp_vac - (Isp_vac - Isp_sl) p / p0`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Burn {
    pub direction: Vec2,
    pub mdot: f64,
    pub isp_vac_s: f64,
    pub isp_sl_s: f64,
}

pub fn altitude(r: Vec2) -> f64 {
    r.norm() - R_EARTH
}

/// Density of the isothermal exponential atmosphere; zero below no altitude cap (it simply decays).
pub fn density(alt_m: f64) -> f64 {
    RHO0 * exp(-alt_m.max(0.0) / SCALE_HEIGHT)
}

/// Ambient pressure ratio p / p0: equal to the density ratio in an isothermal atmosphere.
pub fn pressure_ratio(alt_m: f64) -> f64 {
    exp(-alt_m.max(0.0) / SCALE_HEIGHT)
}

pub fn gravity(env: &Environment, r: Vec2) -> Vec2 {
    match env.gravity {
        Gravity::InverseSquare => {
            let rn = r.norm();
            r * (-MU / (rn * rn * rn))
        }
        Gravity::Uniform(g) => g,
        Gravity::None => Vec2::ZERO,
    }
}

pub fn drag(env: &Environment, aero: &Aero, r: Vec2, v: Vec2) -> Vec2 {
    if !env.atmosphere {
        return Vec2::ZERO;
    }
    let rho = density(altitude(r));
    v * (-0.5 * rho * v.norm() * aero.cd * aero.area_m2)
}

pub fn thrust(env: &Environment, burn: Option<&Burn>, r: Vec2) -> Vec2 {
    let Some(b) = burn else {
        return Vec2::ZERO;
    };
    let pr = if env.atmosphere {
        pressure_ratio(altitude(r))
    } else {
        0.0
    };
    let isp = b.isp_vac_s - (b.isp_vac_s - b.isp_sl_s) * pr;
    b.direction * (b.mdot * G0 * isp)
}

/// Non-gravitational acceleration (thrust plus drag over mass): what an accelerometer senses.
pub fn sensed_acceleration(
    env: &Environment,
    aero: &Aero,
    burn: Option<&Burn>,
    body: &Body,
) -> Vec2 {
    (thrust(env, burn, body.r) + drag(env, aero, body.r, body.v)) * (1.0 / body.m)
}

fn derivative(env: &Environment, aero: &Aero, burn: Option<&Burn>, b: &Body) -> (Vec2, Vec2, f64) {
    let a = gravity(env, b.r) + sensed_acceleration(env, aero, burn, b);
    (b.v, a, -burn.map_or(0.0, |x| x.mdot))
}

/// One classical RK4 step of length `dt`.
pub fn rk4_step(env: &Environment, aero: &Aero, burn: Option<&Burn>, b: &Body, dt: f64) -> Body {
    let at = |b0: &Body, k: (Vec2, Vec2, f64), h: f64| Body {
        r: b0.r + k.0 * h,
        v: b0.v + k.1 * h,
        m: b0.m + k.2 * h,
    };
    let k1 = derivative(env, aero, burn, b);
    let k2 = derivative(env, aero, burn, &at(b, k1, dt / 2.0));
    let k3 = derivative(env, aero, burn, &at(b, k2, dt / 2.0));
    let k4 = derivative(env, aero, burn, &at(b, k3, dt));
    let w = dt / 6.0;
    Body {
        r: b.r + (k1.0 + k2.0 * 2.0 + k3.0 * 2.0 + k4.0) * w,
        v: b.v + (k1.1 + k2.1 * 2.0 + k3.1 * 2.0 + k4.1) * w,
        m: b.m + (k1.2 + 2.0 * k2.2 + 2.0 * k3.2 + k4.2) * w,
    }
}

/// Osculating two-body elements from a state: specific energy, specific angular momentum and the
/// apsis radii, with arithmetic and square roots only.
#[derive(Clone, Copy, Debug, PartialEq, serde::Serialize)]
pub struct Elements {
    pub energy_j_kg: f64,
    pub angular_momentum_m2_s: f64,
    pub semi_major_axis_m: Option<f64>,
    pub eccentricity: f64,
    pub periapsis_alt_m: f64,
    /// None for an unbound (parabolic or hyperbolic) trajectory.
    pub apoapsis_alt_m: Option<f64>,
}

pub fn elements(r: Vec2, v: Vec2) -> Elements {
    let rn = r.norm();
    let energy = 0.5 * v.dot(v) - MU / rn;
    let h = r.cross(v).abs();
    let e = (1.0 + 2.0 * energy * h * h / (MU * MU)).max(0.0).sqrt();
    // r_p = h^2 / (mu (1 + e)) holds for every conic.
    let rp = h * h / (MU * (1.0 + e));
    let (a, ra) = if energy < 0.0 {
        let a = -MU / (2.0 * energy);
        (Some(a), Some(a * (1.0 + e)))
    } else {
        (None, None)
    };
    Elements {
        energy_j_kg: energy,
        angular_momentum_m2_s: h,
        semi_major_axis_m: a,
        eccentricity: e,
        periapsis_alt_m: rp - R_EARTH,
        apoapsis_alt_m: ra.map(|x| x - R_EARTH),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn circular_orbit_elements_are_circular() {
        let r = R_EARTH + 300e3;
        let v = (MU / r).sqrt();
        let e = elements(Vec2::new(0.0, r), Vec2::new(v, 0.0));
        assert!(e.eccentricity < 1e-7, "{}", e.eccentricity);
        assert!((e.periapsis_alt_m - 300e3).abs() < 1e-3);
        assert!((e.apoapsis_alt_m.unwrap() - 300e3).abs() < 1e-3);
    }

    #[test]
    fn thrust_follows_ambient_pressure_at_fixed_mass_flow() {
        let b = Burn {
            direction: Vec2::new(0.0, 1.0),
            mdot: 100.0,
            isp_vac_s: 320.0,
            isp_sl_s: 280.0,
        };
        let sl = thrust(&Environment::MISSION, Some(&b), Vec2::new(0.0, R_EARTH));
        let vac = thrust(
            &Environment::MISSION,
            Some(&b),
            Vec2::new(0.0, R_EARTH + 400e3),
        );
        assert!((sl.z - 100.0 * G0 * 280.0).abs() < 1e-6);
        assert!((vac.z - 100.0 * G0 * 320.0).abs() < 1e-3);
    }
}
