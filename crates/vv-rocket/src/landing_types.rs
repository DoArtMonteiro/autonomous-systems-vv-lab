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
    /// `robust` plus the M9.1 rules: altitude disagreement handling and the rise cutoff.
    Guarded,
    /// `baseline` unchanged plus the M9.1 rise cutoff.
    BaselineGuarded,
    /// M10 arm A: fixed gains with 2-of-3 altitude voting (comparison arm). Schema v2 only.
    #[serde(rename = "m10_a")]
    M10A,
    /// M10 arm B: 7-state LTV Kalman filter with one-epoch NIS rejection. Schema v2 only.
    #[serde(rename = "m10_b")]
    M10B,
    /// M10 arm B+: the same filter without rejection, per-source CUSUM, group health, mode
    /// manager and independent safety monitor (docs/m10-resilient-navigation.md, reference).
    #[serde(rename = "m10_b_plus")]
    M10BPlus,
}

impl Policy {
    pub fn as_str(self) -> &'static str {
        match self {
            Policy::Baseline => "baseline",
            Policy::Robust => "robust",
            Policy::Guarded => "guarded",
            Policy::BaselineGuarded => "baseline_guarded",
            Policy::M10A => "m10_a",
            Policy::M10B => "m10_b",
            Policy::M10BPlus => "m10_b_plus",
        }
    }

    /// An M10 arm: navigates with `nav_filter` and declares mode and integrity.
    pub fn is_m10(self) -> bool {
        matches!(self, Policy::M10A | Policy::M10B | Policy::M10BPlus)
    }

    /// The policy navigates with the fused (IMU, GNSS, gated altimeter) estimator.
    pub fn uses_fused_estimator(self) -> bool {
        matches!(self, Policy::Robust | Policy::Guarded)
    }

    /// M9.1 rule 1: guidance reads the lower of the two disagreeing altitudes.
    pub fn handles_disagreement(self) -> bool {
        self == Policy::Guarded
    }

    /// M9.1 rule 2: cut the engine after a sustained estimated rise.
    pub fn cuts_on_ascent(self) -> bool {
        matches!(self, Policy::Guarded | Policy::BaselineGuarded) || self.is_m10()
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
    /// M9.1 rule 1 is active (the altimeter and the estimator disagree). `None` for the policies
    /// that do not produce the flag, so their traces keep their bytes.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sensor_disagreement: Option<bool>,
    /// M9.1 rule 2 cut the engine (stays true afterwards). `None` for the policies without it.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ascent_abort: Option<bool>,
    /// M10 declaration (mode, group health, channel integrity). `None` for the M9 policies.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nav: Option<NavReport>,
}

/// Health of a group of sources (docs/m10-resilient-navigation.md, section 8.3).
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum GroupHealth {
    Healthy,
    Suspect,
    Excluded,
    Probation,
}

/// Operating mode, ordered from best to worst. `Untrusted` is a declaration about the
/// navigation, not a safe state.
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum NavMode {
    Nominal,
    DegradedNav,
    Untrusted,
}

/// Declared integrity of one channel.
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ChannelStatus {
    Trusted,
    Degraded,
    Untrusted,
}

/// What an M10 controller declares each cycle; serialised in the trace samples.
#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct NavReport {
    pub mode: NavMode,
    pub radar: GroupHealth,
    pub gnss: GroupHealth,
    pub vertical: ChannelStatus,
    pub horizontal_velocity: ChannelStatus,
    /// Never `trusted`: the horizontal position is unverified by construction (`B_h`).
    pub horizontal_position: ChannelStatus,
    /// The two altitude sources disagree and nothing isolates the faulty one.
    pub ambiguous: bool,
    pub sigma_z_m: f64,
    pub sigma_vz_mps: f64,
    pub sigma_h_m: f64,
    pub sigma_vh_mps: f64,
    pub accel_bias_mps2: f64,
    /// Vertical velocity of the independent safety monitor.
    pub monitor_vz_mps: f64,
    /// Largest CUSUM statistic of each group (B+; zero for A and B).
    pub cusum_radar: f64,
    pub cusum_gnss: f64,
    /// The rate parity isolated this group at least once (B+).
    pub isolated_radar: bool,
    pub isolated_gnss: bool,
}

/// Per-cycle record for the verifier: the estimate with its full covariance (position, velocity,
/// accelerometer bias along `x_B`). Kept in memory and compared with the truth by the verifier;
/// never serialised in the trace.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct NavDeclaration {
    pub x: [f64; 7],
    pub p: [[f64; 7]; 7],
    pub report: NavReport,
    /// Estimated nozzle-plane altitude the mode manager used.
    pub h_est_m: f64,
    /// `false` for arm A, which has no covariance (no NEES).
    pub covariance_valid: bool,
    /// Mode transitions so far.
    pub transitions: u32,
}

/// Tunable M10 navigation parameters (case file `controller.nav`, schema v2 only). Defaults are
/// the starting values of docs/m10-resilient-navigation.md; final values come from the
/// development seeds and are frozen by hash before any evaluation.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields, default)]
pub struct NavParams {
    /// Sensor noise (1 sigma) as the filter models it: the datasheet values.
    pub radar_sigma_m: f64,
    pub gnss_position_sigma_m: f64,
    pub gnss_velocity_sigma_mps: f64,
    /// Extra radar uncertainty for the lever arm and the estimated centre of mass (1 sigma).
    pub radar_lever_sigma_m: f64,
    /// Process noise: acceleration per control cycle (1 sigma) and accelerometer bias walk.
    pub accel_process_sigma_mps2: f64,
    pub bias_walk_sigma_mps2_per_sqrt_s: f64,
    pub bias_prior_sigma_mps2: f64,
    /// CUSUM slack `k_ref` and threshold `h` on normalised innovations.
    pub cusum_k: f64,
    pub cusum_h: f64,
    /// Cold-start radar admission: `N_adm` consecutive cycles within `g_adm`.
    pub admission_cycles: u32,
    pub admission_gate_m: f64,
    /// Readmission after an exclusion: consecutive samples with a normalised residual below this.
    pub readmission_samples: u32,
    pub readmission_sigma: f64,
    /// Receiver back after missing data: consecutive self-consistent GNSS epochs.
    pub gnss_readmission_epochs: u32,
    /// Arm B: one-epoch NIS rejection threshold (chi-square, 1 degree of freedom).
    pub nis_reject: f64,
    /// Arm A: voting threshold.
    pub vote_threshold_m: f64,
    /// Integrity: `K_ff`, `AL_v(h) = max(floor, fraction * h)`, `AL_hv`, `AL_h`, `B_h`.
    pub k_ff: f64,
    pub al_v_floor_m: f64,
    pub al_v_fraction: f64,
    pub al_hv_mps: f64,
    pub al_h_m: f64,
    pub b_h_m: f64,
    /// Mode manager: `n_in`, `T_hold`, `T_max`, `T_safe`, `h_commit`.
    pub n_in_cycles: u32,
    pub t_hold_s: f64,
    pub t_max_s: f64,
    pub t_safe_s: f64,
    pub h_commit_m: f64,
    /// Group health: CUSUM level, as a fraction of `h`, that makes a group `suspect`.
    pub suspect_cusum_fraction: f64,
    /// Degraded lateral law: tilt factor of the bias in the dead-reckoning drift bound
    /// (`b_h = bias_prior * factor`, the `tilt_max_tan` of the case).
    pub dead_reckoning_tilt: f64,
    /// Group health: time without data before `suspect` and before `excluded`.
    pub suspect_after_s: f64,
    pub exclude_after_s: f64,
    /// Safety monitor: complementary gains towards the GNSS vertical velocity and the radar slope.
    pub monitor_gnss_gain: f64,
    pub monitor_radar_gain: f64,
    /// Rate parity: anchor the IMU witness at the GNSS epoch before the change point instead of
    /// the 0.5 s window (M10.3 development; `false` keeps the PR 15 behaviour).
    pub anchored_imu_witness: bool,
    /// Exploratory policy, not accepted (owner decision): under `untrusted`, keep chasing the pad
    /// while the horizontal dead-reckoning bound allows it, instead of damping only.
    pub bounded_chase_when_untrusted: bool,
}

impl Default for NavParams {
    fn default() -> Self {
        NavParams {
            radar_sigma_m: 0.1,
            gnss_position_sigma_m: 0.5,
            gnss_velocity_sigma_mps: 0.05,
            radar_lever_sigma_m: 0.05,
            accel_process_sigma_mps2: 0.1,
            bias_walk_sigma_mps2_per_sqrt_s: 0.002,
            bias_prior_sigma_mps2: 0.3,
            cusum_k: 0.5,
            cusum_h: 12.0,
            admission_cycles: 5,
            admission_gate_m: 3.0,
            readmission_samples: 10,
            readmission_sigma: 3.0,
            gnss_readmission_epochs: 10,
            nis_reject: 15.14,
            vote_threshold_m: 3.0,
            k_ff: 5.33,
            al_v_floor_m: 1.0,
            al_v_fraction: 0.02,
            al_hv_mps: 0.5,
            al_h_m: 10.0,
            b_h_m: 30.0,
            n_in_cycles: 3,
            t_hold_s: 2.0,
            t_max_s: 2.0,
            t_safe_s: 5.0,
            h_commit_m: 50.0,
            suspect_cusum_fraction: 0.5,
            dead_reckoning_tilt: 0.2,
            suspect_after_s: 0.2,
            exclude_after_s: 0.5,
            monitor_gnss_gain: 0.25,
            monitor_radar_gain: 0.1,
            anchored_imu_witness: false,
            bounded_chase_when_untrusted: false,
        }
    }
}

/// The step and logical time of a control cycle.
#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct FlagInstant {
    pub step: u64,
    pub t_s: f64,
}

/// First control cycle at which each controller flag was raised. What the controller said, kept
/// next to the verdicts; no verdict reads it.
#[derive(Clone, Copy, Debug, Default, Serialize, PartialEq)]
pub struct ControllerFlags {
    pub sensor_disagreement_first: Option<FlagInstant>,
    pub ascent_abort_first: Option<FlagInstant>,
    pub altimeter_rejected_first: Option<FlagInstant>,
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
    /// M9.1 rule 2 (`guarded`, `baseline_guarded`): the estimated vertical velocity above this
    /// value, held for `ascent_abort_time_s`, cuts the engine. Optional in the case file.
    #[serde(default = "default_ascent_abort_vz_mps")]
    pub ascent_abort_vz_mps: f64,
    #[serde(default = "default_ascent_abort_time_s")]
    pub ascent_abort_time_s: f64,
}

pub const DEFAULT_ASCENT_ABORT_VZ_MPS: f64 = 1.0;
pub const DEFAULT_ASCENT_ABORT_TIME_S: f64 = 1.0;

fn default_ascent_abort_vz_mps() -> f64 {
    DEFAULT_ASCENT_ABORT_VZ_MPS
}

fn default_ascent_abort_time_s() -> f64 {
    DEFAULT_ASCENT_ABORT_TIME_S
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
    /// M10 navigation parameters; the defaults for the M9 policies, which never read them.
    pub nav: NavParams,
}
