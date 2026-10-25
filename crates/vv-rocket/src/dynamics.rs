//! Mass properties and the state derivative of the variable-mass rigid body.
//! Equations and hypotheses: docs/m8-rocket-dynamics.md.

use crate::math::{Quat, Vec3, exp};
use crate::model::{G0, Prepared, Segment, Vehicle};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct State {
    pub r: Vec3,
    pub v: Vec3,
    pub q: Quat,
    pub w: Vec3,
    pub mp: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct Derivative {
    pub r: Vec3,
    pub v: Vec3,
    pub q: Quat,
    pub w: Vec3,
    pub mp: f64,
}

impl State {
    pub fn advanced(&self, d: &Derivative, h: f64) -> State {
        State {
            r: self.r + d.r * h,
            v: self.v + d.v * h,
            q: self.q + d.q.scale(h),
            w: self.w + d.w * h,
            mp: self.mp + d.mp * h,
        }
    }

    pub fn is_finite(&self) -> bool {
        self.r.is_finite()
            && self.v.is_finite()
            && self.w.is_finite()
            && self.mp.is_finite()
            && [self.q.w, self.q.x, self.q.y, self.q.z]
                .iter()
                .all(|c| c.is_finite())
    }
}

/// Mass, centre-of-mass station, diagonal inertia about the centre of mass and its derivative
/// with respect to propellant mass.
#[derive(Clone, Copy, Debug)]
pub struct MassProperties {
    pub mass: f64,
    pub cm_station: f64,
    pub inertia: Vec3,
    pub inertia_per_propellant: Vec3,
}

pub fn mass_properties(v: &Vehicle, mp: f64) -> MassProperties {
    let md = v.dry_mass_kg;
    let mass = md + mp;
    let cm = (md * v.dry_cm_station_m + mp * v.propellant_cm_station_m) / mass;
    let d_dry = v.dry_cm_station_m - cm;
    let d_p = v.propellant_cm_station_m - cm;
    // Propellant inertia about its own centre scales with its mass (hypothesis 2).
    let (ip, dip) = if v.propellant_mass_kg > 0.0 {
        let per_kg = Vec3::from_array(v.propellant_inertia_kgm2) * (1.0 / v.propellant_mass_kg);
        (per_kg * mp, per_kg)
    } else {
        (Vec3::ZERO, Vec3::ZERO)
    };
    let id = Vec3::from_array(v.dry_inertia_kgm2);
    let transverse = md * d_dry * d_dry + mp * d_p * d_p;
    let inertia = Vec3::new(
        id.x + ip.x,
        id.y + ip.y + transverse,
        id.z + ip.z + transverse,
    );
    // d(cm)/d(mp) = d_p / mass, so d(d)/d(mp) = -d_p / mass for both offsets.
    let dcm = d_p / mass;
    let dtransverse = -2.0 * md * d_dry * dcm + d_p * d_p - 2.0 * mp * d_p * dcm;
    let inertia_per_propellant = Vec3::new(dip.x, dip.y + dtransverse, dip.z + dtransverse);
    MassProperties {
        mass,
        cm_station: cm,
        inertia,
        inertia_per_propellant,
    }
}

pub fn density(p: &Prepared, altitude: f64) -> f64 {
    match p.atmosphere {
        None => 0.0,
        Some((rho0, None)) => rho0,
        Some((rho0, Some(h))) => rho0 * exp(-altitude / h),
    }
}

/// Forces in inertial components, for the trace.
#[derive(Clone, Copy, Debug)]
pub struct Forces {
    pub thrust: Vec3,
    pub drag: Vec3,
    pub thrust_n: f64,
}

pub fn forces(p: &Prepared, s: &State, burn: Option<&Segment>) -> Forces {
    let q = s.q.normalized();
    let (thrust_n, thrust) = match burn {
        Some(b) => (b.thrust_n, q.rotate(b.direction * b.thrust_n)),
        None => (0.0, Vec3::ZERO),
    };
    let v = &p.vehicle;
    let k = 0.5 * density(p, s.r.z) * v.drag_coefficient * v.reference_area_m2;
    let drag = s.v * (-k * s.v.norm());
    Forces {
        thrust,
        drag,
        thrust_n,
    }
}

pub fn derivative(p: &Prepared, s: &State, burn: Option<&Segment>) -> Derivative {
    let mp = mass_properties(&p.vehicle, s.mp);
    let f = forces(p, s, burn);
    let gravity = Vec3::new(0.0, 0.0, -p.gravity);
    let accel = gravity + (f.thrust + f.drag) * (1.0 / mp.mass);

    let q_dot = s.q.hamilton(Quat::new(0.0, s.w.x, s.w.y, s.w.z)).scale(0.5);

    let (thrust_body, mdot_e) = match burn {
        Some(b) => (
            b.direction * b.thrust_n,
            b.thrust_n / (p.vehicle.isp_s * G0),
        ),
        None => (Vec3::ZERO, 0.0),
    };
    let mp_dot = -mdot_e;
    let r_e = Vec3::new(-mp.cm_station, 0.0, 0.0);
    let i = mp.inertia;
    let i_dot = mp.inertia_per_propellant * mp_dot;
    let moment = r_e.cross(thrust_body);
    let gyroscopic = s.w.cross(i.hadamard(s.w));
    let mass_flow = i_dot.hadamard(s.w);
    let jet_damping = r_e.cross(s.w.cross(r_e)) * mdot_e;
    let rhs = moment - gyroscopic - mass_flow - jet_damping;
    let w_dot = Vec3::new(rhs.x / i.x, rhs.y / i.y, rhs.z / i.z);

    Derivative {
        r: s.v,
        v: accel,
        q: q_dot,
        w: w_dot,
        mp: mp_dot,
    }
}

/// One classical RK4 step with the burn held for the whole step; returns the state before the
/// quaternion projection.
pub fn rk4(p: &Prepared, s: &State, burn: Option<&Segment>, h: f64) -> State {
    let k1 = derivative(p, s, burn);
    let k2 = derivative(p, &s.advanced(&k1, h / 2.0), burn);
    let k3 = derivative(p, &s.advanced(&k2, h / 2.0), burn);
    let k4 = derivative(p, &s.advanced(&k3, h), burn);
    let c = h / 6.0;
    State {
        r: s.r + (k1.r + k2.r * 2.0 + k3.r * 2.0 + k4.r) * c,
        v: s.v + (k1.v + k2.v * 2.0 + k3.v * 2.0 + k4.v) * c,
        q: s.q + (k1.q + k2.q.scale(2.0) + k3.q.scale(2.0) + k4.q).scale(c),
        w: s.w + (k1.w + k2.w * 2.0 + k3.w * 2.0 + k4.w) * c,
        mp: s.mp + (k1.mp + 2.0 * k2.mp + 2.0 * k3.mp + k4.mp) * c,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vehicle() -> Vehicle {
        Vehicle {
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
        }
    }

    #[test]
    fn inertia_derivative_matches_a_central_difference() {
        let v = vehicle();
        let h = 1e-4;
        for mp in [1.0, 20.0, 49.0] {
            let analytic = mass_properties(&v, mp).inertia_per_propellant;
            let numeric = (mass_properties(&v, mp + h).inertia
                - mass_properties(&v, mp - h).inertia)
                * (1.0 / (2.0 * h));
            assert!(
                (analytic - numeric).norm() <= 1e-6 * analytic.norm(),
                "mp {mp}"
            );
        }
    }

    #[test]
    fn centre_of_mass_and_parallel_axis_terms() {
        let m = mass_properties(&vehicle(), 50.0);
        let cm = (100.0 * 2.0 + 50.0 * 1.5) / 150.0;
        assert!((m.cm_station - cm).abs() < 1e-15);
        // Independent decomposition: moments about station 0, then one shift to the centre of mass.
        let about_station_0 = (100.0 + 100.0 * 4.0) + (40.0 + 50.0 * 2.25);
        let iyy = about_station_0 - 150.0 * cm * cm;
        assert!((m.inertia.y - iyy).abs() < 1e-12);
        assert_eq!(m.inertia.x, 15.0);
    }
}
