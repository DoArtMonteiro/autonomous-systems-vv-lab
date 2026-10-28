//! Types shared by the sensors, the controller and the simulation (docs/m9-powered-landing.md).
//!
//! This module imports nothing from the truth side of the simulation: it is what the controller
//! is allowed to see, namely observations, its commands and its known configuration.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Policy {
    Baseline,
    Robust,
}

impl Policy {
    pub fn as_str(self) -> &'static str {
        match self {
            Policy::Baseline => "baseline",
            Policy::Robust => "robust",
        }
    }
}

/// IMU sample: attitude quaternion (w, x, y, z), angular velocity and specific force in B.
#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct Imu {
    pub attitude: [f64; 4],
    pub angular_velocity_radps: [f64; 3],
    pub specific_force_mps2: [f64; 3],
}

/// What the sensors delivered in one control cycle. A missing measurement is `None`, never zero.
#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct Observation {
    pub altimeter_m: Option<f64>,
    pub gnss_position_m: Option<[f64; 3]>,
    pub gnss_velocity_mps: Option<[f64; 3]>,
    pub imu: Imu,
}

/// Controller output: throttle (0 means "off" or "cut") and gimbal tangents (y, z).
#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct Command {
    pub throttle: f64,
    pub gimbal_tan: [f64; 2],
}

impl Command {
    pub const OFF: Command = Command {
        throttle: 0.0,
        gimbal_tan: [0.0, 0.0],
    };
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct Estimate {
    pub position_m: [f64; 3],
    pub velocity_mps: [f64; 3],
    pub altimeter_rejected: bool,
}

/// Design parameters of the controller and of the `robust` estimator. These are decisions of the
/// controller design and may change; the requirements may not.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Gains {
    /// Ignition when the required specific force exceeds this fraction of nominal `T_max / m`.
    pub ignition_fraction: f64,
    /// Fraction of the specific-force error corrected in one control cycle.
    pub throttle_gain: f64,
    /// Margin below the axial load limit, in multiples of `g0`.
    pub axial_load_margin_g: f64,
    /// Floor of the altitude in `a_req = (v^2 - v_t^2) / (2 h)`, in metres.
    pub altitude_floor_m: f64,
    /// Attitude loop, in tangent of gimbal per rad and per rad/s at the reference throttle.
    pub attitude_kp: f64,
    pub attitude_kd: f64,
    pub attitude_reference_throttle: f64,
    /// Tangent of the commanded tilt: cap far from the ground and its taper near the ground.
    pub tilt_max_tan: f64,
    pub tilt_floor_tan: f64,
    pub tilt_per_m: f64,
    /// Lateral law: velocity gain (1/s), position gain (1/s) of the wanted lateral velocity, the
    /// braking deceleration that bounds it, and the time to go below which the position term fades.
    pub lateral_velocity_gain: f64,
    pub lateral_position_gain: f64,
    pub lateral_braking_mps2: f64,
    pub lateral_fade_time_s: f64,
    /// Cut the engine if the estimated vertical velocity is positive below this altitude.
    pub cutoff_altitude_m: f64,
    /// `robust` estimator.
    pub gnss_position_gain: f64,
    pub gnss_velocity_gain: f64,
    pub altimeter_position_gain: f64,
    pub altimeter_velocity_gain: f64,
    pub altimeter_residual_threshold_m: f64,
    pub altimeter_rejection_cycles: u32,
}

/// The only information the controller has besides observations (docs/m9-powered-landing.md).
#[derive(Clone, Debug, PartialEq)]
pub struct ControllerConfig {
    pub policy: Policy,
    pub dt_s: f64,
    pub control_period_steps: u64,
    pub gravity_mps2: f64,
    pub dry_mass_kg: f64,
    pub propellant_mass_kg: f64,
    pub dry_cm_station_m: f64,
    pub propellant_cm_station_m: f64,
    pub isp_s: f64,
    pub max_thrust_n: f64,
    pub throttle_min: f64,
    pub throttle_max: f64,
    pub throttle_rate_per_s: f64,
    pub gimbal_max_tan: f64,
    pub gimbal_rate_tan_per_s: f64,
    pub pad_position_m: [f64; 2],
    pub target_vertical_speed_mps: f64,
    pub axial_load_limit_mps2: f64,
    pub gains: Gains,
}
