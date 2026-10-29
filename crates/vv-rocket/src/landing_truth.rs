//! Truth-side helpers of the landing: the nozzle-plane contact point, tilt, the contact
//! interpolation and the per-step record the independent verifier reads.

use serde::Serialize;

use crate::dynamics::{State, mass_properties};
use crate::landing_model::FaultKind;
use crate::math::{Quat, Vec3};
use crate::model::Vehicle;

/// `p_base = r + R(q) (-s_cm, 0, 0)` and `v_base = v + R(q) (w x (-s_cm, 0, 0))`.
pub fn base_kinematics(v: &Vehicle, s: &State) -> (Vec3, Vec3) {
    let q = s.q.normalized();
    let r_e = Vec3::new(-mass_properties(v, s.mp).cm_station, 0.0, 0.0);
    (s.r + q.rotate(r_e), s.v + q.rotate(s.w.cross(r_e)))
}

/// Cosine of the angle between `x_B` and `z_N`: the third component of `R(q) (1, 0, 0)`, which is
/// `2 (q_x q_z - q_w q_y)` for a unit quaternion.
pub fn tilt_cos(q: Quat) -> f64 {
    let q = q.normalized();
    2.0 * (q.x * q.z - q.w * q.y)
}

/// Interpolation of two states at fraction `u`: linear in every component, quaternion normalised.
pub fn interpolate(a: &State, b: &State, u: f64) -> State {
    let lerp = |x: f64, y: f64| x + (y - x) * u;
    let lerp3 = |x: Vec3, y: Vec3| x + (y - x) * u;
    State {
        r: lerp3(a.r, b.r),
        v: lerp3(a.v, b.v),
        q: (a.q + (b.q + a.q.scale(-1.0)).scale(u)).normalized(),
        w: lerp3(a.w, b.w),
        mp: lerp(a.mp, b.mp),
    }
}

/// Contact: the first step whose end has the nozzle plane at or below the ground. Returns the
/// fraction of the step at which `p_base,z` of the two end states crosses zero, and the state
/// interpolated there.
pub fn contact(v: &Vehicle, before: &State, after: &State) -> Option<(f64, State)> {
    let z0 = base_kinematics(v, before).0.z;
    let z1 = base_kinematics(v, after).0.z;
    if z1 > 0.0 {
        return None;
    }
    let u = if z0 > z1 {
        (z0 / (z0 - z1)).clamp(0.0, 1.0)
    } else {
        1.0
    };
    Some((u, interpolate(before, after, u)))
}

/// What was true during one step: the state at its start and the actuator output held for it.
#[derive(Clone, Debug)]
pub struct TruthStep {
    pub step: u64,
    pub state: State,
    pub thrust_n: f64,
    /// Unit thrust direction in B (meaningless when `thrust_n` is zero).
    pub direction: Vec3,
    pub active_faults: Vec<FaultKind>,
}

/// The contact as the simulation found it. Only `step` and `after` are inputs of the verifier:
/// it interpolates the contact itself from the state at the start of step `step - 1` (in the log)
/// and `after`, so `fraction`, `t_s` and `state` are the simulation's own result, used for the
/// trace and to stop, and a wrong value there cannot change a verdict.
#[derive(Clone, Debug)]
pub struct Touchdown {
    /// Step boundary `k + 1` at which the nozzle plane was found at or below the ground; the contact
    /// lies inside step `k`, at `fraction` of it.
    pub step: u64,
    pub fraction: f64,
    pub t_s: f64,
    /// The interpolated contact state.
    pub state: State,
    /// The integrated state at the end of step `k`, before any interpolation.
    pub after: State,
}

/// The ignition as the actuator performed it: the step at which it was commanded and the step at
/// which the engine lit (`None`: still waiting at the end of the run).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Ignition {
    pub command_step: u64,
    pub effective_step: Option<u64>,
}

/// All the truth the verifier needs; it holds no sensor or controller data.
#[derive(Clone, Debug)]
pub struct TruthLog {
    pub dt: f64,
    pub steps: Vec<TruthStep>,
    /// Step index and state at the end of the run (the contact state when there is a contact).
    pub end_step: u64,
    pub end_state: State,
    pub touchdown: Option<Touchdown>,
    pub ignition: Option<Ignition>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct TruthExcerpt {
    pub position_m: [f64; 3],
    pub velocity_mps: [f64; 3],
    pub attitude: [f64; 4],
    pub angular_velocity_radps: [f64; 3],
    pub propellant_kg: f64,
    pub mass_kg: f64,
    pub base_position_m: [f64; 3],
    pub base_velocity_mps: [f64; 3],
    pub tilt_cos: f64,
}

pub fn excerpt(v: &Vehicle, s: &State) -> TruthExcerpt {
    let (bp, bv) = base_kinematics(v, s);
    TruthExcerpt {
        position_m: s.r.to_array(),
        velocity_mps: s.v.to_array(),
        attitude: s.q.to_array(),
        angular_velocity_radps: s.w.to_array(),
        propellant_kg: s.mp,
        mass_kg: mass_properties(v, s.mp).mass,
        base_position_m: bp.to_array(),
        base_velocity_mps: bv.to_array(),
        tilt_cos: tilt_cos(s.q),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vehicle() -> Vehicle {
        Vehicle {
            dry_mass_kg: 100.0,
            propellant_mass_kg: 0.0,
            dry_cm_station_m: 4.0,
            propellant_cm_station_m: 0.0,
            dry_inertia_kgm2: [10.0, 100.0, 100.0],
            propellant_inertia_kgm2: [0.0; 3],
            max_thrust_n: 0.0,
            isp_s: 300.0,
            drag_coefficient: 0.0,
            reference_area_m2: 0.0,
        }
    }

    fn state(z: f64, vz: f64) -> State {
        State {
            r: Vec3::new(1.0, 2.0, z),
            v: Vec3::new(0.0, 0.0, vz),
            q: Quat::new(
                std::f64::consts::FRAC_1_SQRT_2,
                0.0,
                -std::f64::consts::FRAC_1_SQRT_2,
                0.0,
            ),
            w: Vec3::ZERO,
            mp: 0.0,
        }
    }

    #[test]
    fn nozzle_plane_is_s_cm_below_the_centre_of_mass_when_upright() {
        // q = rotation of -90 deg about y: x_B = +z_N.
        let (p, v) = base_kinematics(&vehicle(), &state(10.0, -3.0));
        assert!((p.z - 6.0).abs() < 1e-12 && (p.x - 1.0).abs() < 1e-12);
        assert!((v.z + 3.0).abs() < 1e-12);
        assert!((tilt_cos(state(0.0, 0.0).q) - 1.0).abs() < 1e-12);
    }

    #[test]
    fn rotation_rate_moves_the_nozzle_plane() {
        let mut s = state(10.0, -3.0);
        s.w = Vec3::new(0.0, 0.0, 0.5); // yaw rate about z_B (horizontal here)
        let (_, v) = base_kinematics(&vehicle(), &s);
        // w x (-4, 0, 0) = (0, -4 * 0.5, 0) in B; B's y axis is horizontal.
        assert!((Vec3::new(v.x, v.y, 0.0).norm() - 2.0).abs() < 1e-12);
    }

    #[test]
    fn contact_interpolates_on_a_constructed_pair_of_states() {
        let v = vehicle();
        // Nozzle altitudes 0.3 m and -0.1 m: fraction 0.75, state halfway weighted.
        let a = state(4.3, -2.0);
        let b = state(3.9, -2.4);
        let (u, s) = contact(&v, &a, &b).unwrap();
        assert!((u - 0.75).abs() < 1e-12);
        assert!((s.r.z - (4.3 - 0.3)).abs() < 1e-12);
        assert!((s.v.z - (-2.0 - 0.3)).abs() < 1e-12);
        assert!(base_kinematics(&v, &s).0.z.abs() < 1e-12);
        assert!((s.q.norm() - 1.0).abs() < 1e-15);
        assert!(contact(&v, &a, &state(4.2, -2.0)).is_none());
        // Exactly on the ground at the end of the step: fraction 1.
        let (u, _) = contact(&v, &a, &state(4.0, -2.0)).unwrap();
        assert!((u - 1.0).abs() < 1e-12);
    }

    #[test]
    fn interpolated_attitude_is_normalised() {
        let a = state(1.0, 0.0);
        let mut b = state(1.0, 0.0);
        b.q = Quat::new(1.0, 0.0, 0.0, 0.0);
        let mid = interpolate(&a, &b, 0.5);
        assert!((mid.q.norm() - 1.0).abs() < 1e-15);
        let e = excerpt(&vehicle(), &mid);
        assert_eq!(e.attitude, mid.q.to_array());
    }
}
