//! Landing case schema `vv-rocket-landing.v1`: strict validation and dispersion by seed.
//!
//! The pre-registered requirements, dispersions, sensor rates and fault ranges of
//! docs/m9-powered-landing.md are fixed: a file that states other values is rejected, so the
//! evidence stays self-describing and a threshold cannot be moved to make a case pass.

use serde::{Deserialize, Serialize};

use crate::landing_types::{ControllerConfig, Gains, Policy};
use crate::math::Vec3;
use crate::model::{
    CASE_SCHEMA, Case, Environment, Initial, Prepared, Vehicle, finite, prepare, steps_of, within,
};
use crate::prng::{SplitMix64, source};

pub const LANDING_SCHEMA: &str = "vv-rocket-landing.v1";
pub const CONTROL_PERIOD_STEPS: u64 = 2;
pub const GNSS_PERIOD_CYCLES: u64 = 5;
pub const MAX_FAULTS: usize = 8;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LandingCase {
    pub schema: String,
    pub name: String,
    pub dt_s: f64,
    pub duration_s: f64,
    /// In steps; a multiple of the control period.
    pub record_every: u64,
    pub environment: Environment,
    pub vehicle: LandingVehicle,
    pub initial: Initial,
    pub dispersion: Dispersion,
    pub sensors: Sensors,
    pub controller: ControllerSpec,
    pub requirements: Requirements,
    pub faults: Vec<FaultSpec>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LandingVehicle {
    pub dry_mass_kg: f64,
    pub propellant_mass_kg: f64,
    pub dry_cm_station_m: f64,
    pub propellant_cm_station_m: f64,
    pub dry_inertia_kgm2: [f64; 3],
    pub propellant_inertia_kgm2: [f64; 3],
    pub max_thrust_n: f64,
    pub isp_s: f64,
    pub drag_coefficient: f64,
    pub reference_area_m2: f64,
    pub throttle_min: f64,
    pub throttle_rate_per_s: f64,
    pub gimbal_max_tan: f64,
    pub gimbal_rate_tan_per_s: f64,
}

/// Half-widths of the uniform dispersions; fixed by the specification.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Dispersion {
    pub position_m: [f64; 3],
    pub velocity_mps: [f64; 3],
    pub angular_velocity_radps: [f64; 3],
    pub propellant_fraction: f64,
    pub thrust_fraction: f64,
    pub isp_fraction: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Sensors {
    pub altimeter_sigma_m: f64,
    pub gnss_position_sigma_m: f64,
    pub gnss_velocity_sigma_mps: f64,
    pub imu_attitude_sigma_rad: f64,
    pub imu_rate_sigma_radps: f64,
    pub imu_accel_sigma_mps2: f64,
    pub control_period_steps: u64,
    pub gnss_period_cycles: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerSpec {
    pub policy: Policy,
    pub target_vertical_speed_mps: f64,
    pub gains: Gains,
}

/// Limits of the requirements and invariants; fixed by the specification.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Requirements {
    pub pad_position_m: [f64; 2],
    pub r1_vertical_speed_mps: f64,
    pub r2_horizontal_speed_mps: f64,
    pub r3_tilt_cos_min: f64,
    pub r4_angular_rate_radps: f64,
    pub r5_position_m: f64,
    pub r6_propellant_margin_fraction: f64,
    pub s1_tilt_cos_min: f64,
    pub s2_keep_out_m: f64,
    pub s3_axial_load_g0: f64,
    pub s4_max_ignitions: u32,
}

impl Requirements {
    /// The pre-registered values.
    pub fn registered() -> Self {
        Requirements {
            pad_position_m: [0.0, 0.0],
            r1_vertical_speed_mps: 3.0,
            r2_horizontal_speed_mps: 1.0,
            r3_tilt_cos_min: 0.996_194_698_1,
            r4_angular_rate_radps: 0.1,
            r5_position_m: 10.0,
            r6_propellant_margin_fraction: 0.01,
            s1_tilt_cos_min: 0.866_025_403_8,
            s2_keep_out_m: 50.0,
            s3_axial_load_g0: 3.0,
            s4_max_ignitions: 1,
        }
    }
}

impl Dispersion {
    pub fn registered() -> Self {
        Dispersion {
            position_m: [30.0, 30.0, 50.0],
            velocity_mps: [3.0, 3.0, 10.0],
            angular_velocity_radps: [0.0, 0.004, 0.004],
            propellant_fraction: 0.02,
            thrust_fraction: 0.02,
            isp_fraction: 0.01,
        }
    }
}

impl Sensors {
    pub fn registered() -> Self {
        Sensors {
            altimeter_sigma_m: 0.1,
            gnss_position_sigma_m: 0.5,
            gnss_velocity_sigma_mps: 0.05,
            imu_attitude_sigma_rad: 1e-4,
            imu_rate_sigma_radps: 1e-4,
            imu_accel_sigma_mps2: 0.02,
            control_period_steps: CONTROL_PERIOD_STEPS,
            gnss_period_cycles: GNSS_PERIOD_CYCLES,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FaultKind {
    ThrustLoss,
    IgnitionDelay,
    GimbalStuck,
    AltimeterBias,
    AltimeterDropout,
    GnssDropout,
    GnssBias,
    ImuAccelBias,
}

impl FaultKind {
    pub fn as_str(self) -> &'static str {
        match self {
            FaultKind::ThrustLoss => "thrust_loss",
            FaultKind::IgnitionDelay => "ignition_delay",
            FaultKind::GimbalStuck => "gimbal_stuck",
            FaultKind::AltimeterBias => "altimeter_bias",
            FaultKind::AltimeterDropout => "altimeter_dropout",
            FaultKind::GnssDropout => "gnss_dropout",
            FaultKind::GnssBias => "gnss_bias",
            FaultKind::ImuAccelBias => "imu_accel_bias",
        }
    }

    /// Pre-registered magnitude range, or `None` for faults without magnitude.
    fn magnitude_range(self) -> Option<(f64, f64)> {
        match self {
            FaultKind::ThrustLoss => Some((0.05, 0.30)),
            FaultKind::IgnitionDelay => Some((0.1, 1.0)),
            FaultKind::AltimeterBias => Some((5.0, 50.0)),
            FaultKind::GnssBias => Some((5.0, 30.0)),
            FaultKind::ImuAccelBias => Some((0.05, 0.5)),
            FaultKind::GimbalStuck | FaultKind::AltimeterDropout | FaultKind::GnssDropout => None,
        }
    }

    /// Pre-registered window length range in seconds, for faults defined by their duration.
    fn window_range(self) -> Option<(f64, f64)> {
        match self {
            FaultKind::GimbalStuck => Some((0.5, 3.0)),
            FaultKind::AltimeterDropout | FaultKind::GnssDropout => Some((2.0, 10.0)),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FaultSpec {
    pub kind: FaultKind,
    pub start_s: f64,
    pub end_s: f64,
    pub magnitude: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct Fault {
    pub spec: FaultSpec,
    pub start_step: u64,
    pub end_step: u64,
}

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub throttle_min: f64,
    pub throttle_max: f64,
    pub throttle_rate_per_s: f64,
    pub gimbal_max_tan: f64,
    pub gimbal_rate_tan_per_s: f64,
}

#[derive(Clone, Debug)]
pub struct PreparedLanding {
    pub name: String,
    pub seed: u64,
    pub dt: f64,
    pub steps: u64,
    pub record_every: u64,
    /// Truth model: dispersed vehicle and initial state, no scheduled burns.
    pub truth: Prepared,
    pub nominal_vehicle: Vehicle,
    pub limits: Limits,
    pub sensors: Sensors,
    pub controller: ControllerConfig,
    pub requirements: Requirements,
    pub faults: Vec<Fault>,
    pub dispersed: bool,
}

fn vehicle_of(v: &LandingVehicle) -> Vehicle {
    Vehicle {
        dry_mass_kg: v.dry_mass_kg,
        propellant_mass_kg: v.propellant_mass_kg,
        dry_cm_station_m: v.dry_cm_station_m,
        propellant_cm_station_m: v.propellant_cm_station_m,
        dry_inertia_kgm2: v.dry_inertia_kgm2,
        propellant_inertia_kgm2: v.propellant_inertia_kgm2,
        max_thrust_n: v.max_thrust_n,
        isp_s: v.isp_s,
        drag_coefficient: v.drag_coefficient,
        reference_area_m2: v.reference_area_m2,
    }
}

fn validate_gains(g: &Gains) -> Result<(), String> {
    within(
        g.ignition_fraction,
        "controller.gains.ignition_fraction",
        0.05,
        1.5,
    )?;
    within(g.throttle_gain, "controller.gains.throttle_gain", 0.0, 1.0)?;
    within(
        g.axial_load_margin_g,
        "controller.gains.axial_load_margin_g",
        0.0,
        2.0,
    )?;
    within(
        g.altitude_floor_m,
        "controller.gains.altitude_floor_m",
        0.01,
        100.0,
    )?;
    within(g.attitude_kp, "controller.gains.attitude_kp", 0.0, 100.0)?;
    within(g.attitude_kd, "controller.gains.attitude_kd", 0.0, 100.0)?;
    within(
        g.attitude_reference_throttle,
        "controller.gains.attitude_reference_throttle",
        0.1,
        1.0,
    )?;
    within(g.tilt_max_tan, "controller.gains.tilt_max_tan", 0.0, 0.2)?;
    within(
        g.tilt_floor_tan,
        "controller.gains.tilt_floor_tan",
        0.0,
        0.2,
    )?;
    within(g.tilt_per_m, "controller.gains.tilt_per_m", 0.0, 1.0)?;
    within(
        g.lateral_velocity_gain,
        "controller.gains.lateral_velocity_gain",
        0.0,
        10.0,
    )?;
    within(
        g.lateral_position_gain,
        "controller.gains.lateral_position_gain",
        0.0,
        10.0,
    )?;
    within(
        g.lateral_braking_mps2,
        "controller.gains.lateral_braking_mps2",
        0.0,
        100.0,
    )?;
    within(
        g.lateral_fade_time_s,
        "controller.gains.lateral_fade_time_s",
        0.1,
        60.0,
    )?;
    within(
        g.cutoff_altitude_m,
        "controller.gains.cutoff_altitude_m",
        0.0,
        1000.0,
    )?;
    within(
        g.gnss_position_gain,
        "controller.gains.gnss_position_gain",
        0.0,
        1.0,
    )?;
    within(
        g.gnss_velocity_gain,
        "controller.gains.gnss_velocity_gain",
        0.0,
        1.0,
    )?;
    within(
        g.altimeter_position_gain,
        "controller.gains.altimeter_position_gain",
        0.0,
        1.0,
    )?;
    within(
        g.altimeter_velocity_gain,
        "controller.gains.altimeter_velocity_gain",
        0.0,
        1.0,
    )?;
    within(
        g.altimeter_residual_threshold_m,
        "controller.gains.altimeter_residual_threshold_m",
        0.1,
        1000.0,
    )?;
    if g.altimeter_rejection_cycles == 0 || g.altimeter_rejection_cycles > 1000 {
        return Err("controller.gains.altimeter_rejection_cycles must be in [1, 1000]".into());
    }
    Ok(())
}

fn validate_faults(case: &LandingCase, dt: f64) -> Result<Vec<Fault>, String> {
    if case.faults.len() > MAX_FAULTS {
        return Err(format!("faults has more than {MAX_FAULTS} entries"));
    }
    let mut out: Vec<Fault> = Vec::new();
    for (i, f) in case.faults.iter().enumerate() {
        let name = format!("faults[{i}]");
        if out.iter().any(|o| o.spec.kind == f.kind) {
            return Err(format!("{name}.kind {} appears twice", f.kind.as_str()));
        }
        within(f.start_s, &format!("{name}.start_s"), 0.0, case.duration_s)?;
        within(f.end_s, &format!("{name}.end_s"), 0.0, case.duration_s)?;
        let start_step = steps_of(f.start_s, dt, &format!("{name}.start_s"))?;
        let end_step = steps_of(f.end_s, dt, &format!("{name}.end_s"))?;
        if end_step <= start_step {
            return Err(format!("{name}.end_s must be after start_s"));
        }
        finite(f.magnitude, &format!("{name}.magnitude"))?;
        match f.kind.magnitude_range() {
            Some((low, high)) => {
                if f.magnitude < low || f.magnitude > high {
                    return Err(format!(
                        "{name}.magnitude must be in the registered range [{low}, {high}] for {}",
                        f.kind.as_str()
                    ));
                }
            }
            None => {
                if f.magnitude != 0.0 {
                    return Err(format!(
                        "{name}.magnitude must be 0 for {}",
                        f.kind.as_str()
                    ));
                }
            }
        }
        if let Some((low, high)) = f.kind.window_range() {
            let length = (end_step - start_step) as f64 * dt;
            // Half a step of slack on a window given in whole steps.
            if length < low - 0.5 * dt || length > high + 0.5 * dt {
                return Err(format!(
                    "{name} window must last [{low}, {high}] s for {}",
                    f.kind.as_str()
                ));
            }
        }
        out.push(Fault {
            spec: *f,
            start_step,
            end_step,
        });
    }
    Ok(out)
}

fn require_equal<T: PartialEq + std::fmt::Debug>(
    got: &T,
    want: &T,
    what: &str,
) -> Result<(), String> {
    if got == want {
        Ok(())
    } else {
        Err(format!(
            "{what} must equal the pre-registered value {want:?} (docs/m9-powered-landing.md), got {got:?}"
        ))
    }
}

/// Validates a landing case and applies the dispersions of `seed`. Seed 0 is the nominal case:
/// no dispersion draws are made (sensor noise, in `landing_sensors`, stays on and is seeded by 0).
pub fn prepare_landing(case: &LandingCase, seed: u64) -> Result<PreparedLanding, String> {
    if case.schema != LANDING_SCHEMA {
        return Err(format!("schema must be {LANDING_SCHEMA}"));
    }
    if case.record_every == 0 || !case.record_every.is_multiple_of(CONTROL_PERIOD_STEPS) {
        return Err(format!(
            "record_every must be a positive multiple of the control period ({CONTROL_PERIOD_STEPS} steps)"
        ));
    }
    require_equal(&case.dispersion, &Dispersion::registered(), "dispersion")?;
    require_equal(
        &case.requirements,
        &Requirements::registered(),
        "requirements",
    )?;
    let s = &case.sensors;
    require_equal(
        &s.control_period_steps,
        &CONTROL_PERIOD_STEPS,
        "sensors.control_period_steps",
    )?;
    require_equal(
        &s.gnss_period_cycles,
        &GNSS_PERIOD_CYCLES,
        "sensors.gnss_period_cycles",
    )?;
    for (v, name) in [
        (s.altimeter_sigma_m, "sensors.altimeter_sigma_m"),
        (s.gnss_position_sigma_m, "sensors.gnss_position_sigma_m"),
        (s.gnss_velocity_sigma_mps, "sensors.gnss_velocity_sigma_mps"),
        (s.imu_attitude_sigma_rad, "sensors.imu_attitude_sigma_rad"),
        (s.imu_rate_sigma_radps, "sensors.imu_rate_sigma_radps"),
        (s.imu_accel_sigma_mps2, "sensors.imu_accel_sigma_mps2"),
    ] {
        within(v, name, 0.0, 100.0)?;
    }

    let lv = &case.vehicle;
    within(lv.throttle_min, "vehicle.throttle_min", 0.0, 1.0)?;
    within(
        lv.throttle_rate_per_s,
        "vehicle.throttle_rate_per_s",
        1e-3,
        1e3,
    )?;
    within(lv.gimbal_max_tan, "vehicle.gimbal_max_tan", 0.0, 1.0)?;
    within(
        lv.gimbal_rate_tan_per_s,
        "vehicle.gimbal_rate_tan_per_s",
        1e-3,
        1e3,
    )?;
    let ctl = &case.controller;
    within(
        ctl.target_vertical_speed_mps,
        "controller.target_vertical_speed_mps",
        -3.0,
        -0.1,
    )?;
    validate_gains(&ctl.gains)?;

    // The truth model reuses the M8 validation for the environment, vehicle, state, step and
    // sample limits; the landing has no scheduled burns.
    let m8 = Case {
        schema: CASE_SCHEMA.into(),
        name: case.name.clone(),
        dt_s: case.dt_s,
        duration_s: case.duration_s,
        record_every: case.record_every,
        stop_at_ground: false,
        environment: case.environment.clone(),
        vehicle: vehicle_of(lv),
        initial: case.initial.clone(),
        burns: Vec::new(),
    };
    let mut truth = prepare(&m8)?;
    let faults = validate_faults(case, truth.dt)?;

    let nominal_vehicle = truth.vehicle.clone();
    let dispersed = seed != 0;
    if dispersed {
        let d = &case.dispersion;
        let mut g = SplitMix64::stream(seed, source::INITIAL_POSITION);
        truth.r0 = truth.r0
            + Vec3::new(
                d.position_m[0] * g.centered(),
                d.position_m[1] * g.centered(),
                d.position_m[2] * g.centered(),
            );
        let mut g = SplitMix64::stream(seed, source::INITIAL_VELOCITY);
        truth.v0 = truth.v0
            + Vec3::new(
                d.velocity_mps[0] * g.centered(),
                d.velocity_mps[1] * g.centered(),
                d.velocity_mps[2] * g.centered(),
            );
        let mut g = SplitMix64::stream(seed, source::INITIAL_ANGULAR_VELOCITY);
        truth.w0 = truth.w0
            + Vec3::new(
                0.0,
                d.angular_velocity_radps[1] * g.centered(),
                d.angular_velocity_radps[2] * g.centered(),
            );
        let scale = |source: u64, fraction: f64| {
            1.0 + fraction * SplitMix64::stream(seed, source).centered()
        };
        let k_prop = scale(source::PROPELLANT, d.propellant_fraction);
        let v = &mut truth.vehicle;
        v.propellant_mass_kg *= k_prop;
        // The propellant inertia per kilogram does not change with the dispersed load.
        for x in &mut v.propellant_inertia_kgm2 {
            *x *= k_prop;
        }
        v.max_thrust_n *= scale(source::THRUST, d.thrust_fraction);
        v.isp_s *= scale(source::ISP, d.isp_fraction);
    }

    // The nozzle plane must start above the ground.
    let mp0 = crate::dynamics::mass_properties(&truth.vehicle, truth.vehicle.propellant_mass_kg);
    let base_z = truth.r0.z + truth.q0.rotate(Vec3::new(-mp0.cm_station, 0.0, 0.0)).z;
    if base_z <= 0.0 {
        return Err("the nozzle plane must start above the ground".into());
    }

    let controller = ControllerConfig {
        policy: ctl.policy,
        dt_s: truth.dt,
        control_period_steps: CONTROL_PERIOD_STEPS,
        gravity_mps2: truth.gravity,
        dry_mass_kg: nominal_vehicle.dry_mass_kg,
        propellant_mass_kg: nominal_vehicle.propellant_mass_kg,
        dry_cm_station_m: nominal_vehicle.dry_cm_station_m,
        propellant_cm_station_m: nominal_vehicle.propellant_cm_station_m,
        isp_s: nominal_vehicle.isp_s,
        max_thrust_n: nominal_vehicle.max_thrust_n,
        throttle_min: lv.throttle_min,
        throttle_max: 1.0,
        throttle_rate_per_s: lv.throttle_rate_per_s,
        gimbal_max_tan: lv.gimbal_max_tan,
        gimbal_rate_tan_per_s: lv.gimbal_rate_tan_per_s,
        pad_position_m: case.requirements.pad_position_m,
        target_vertical_speed_mps: ctl.target_vertical_speed_mps,
        axial_load_limit_mps2: case.requirements.s3_axial_load_g0 * crate::model::G0,
        gains: ctl.gains.clone(),
    };
    Ok(PreparedLanding {
        name: case.name.clone(),
        seed,
        dt: truth.dt,
        steps: truth.steps,
        record_every: case.record_every,
        limits: Limits {
            throttle_min: lv.throttle_min,
            throttle_max: 1.0,
            throttle_rate_per_s: lv.throttle_rate_per_s,
            gimbal_max_tan: lv.gimbal_max_tan,
            gimbal_rate_tan_per_s: lv.gimbal_rate_tan_per_s,
        },
        sensors: case.sensors.clone(),
        controller,
        requirements: case.requirements.clone(),
        faults,
        dispersed,
        truth,
        nominal_vehicle,
    })
}
