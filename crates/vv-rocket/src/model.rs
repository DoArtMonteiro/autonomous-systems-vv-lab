//! Case file schema and strict validation into a prepared, step-indexed model.

use serde::{Deserialize, Serialize};

use crate::math::{Quat, Vec3};

pub const CASE_SCHEMA: &str = "vv-rocket-case.v1";
/// Standard gravity in the definition of specific impulse; independent of the local gravity.
pub const G0: f64 = 9.80665;
pub const MAX_STEPS: u64 = 200_000;
pub const MAX_SAMPLES: u64 = 2_000;
pub const MIN_DT: f64 = 1e-4;
pub const MAX_DT: f64 = 1.0;
const ALIGN_TOLERANCE: f64 = 1e-9;
const QUAT_NORM_TOLERANCE: f64 = 1e-6;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Case {
    pub schema: String,
    pub name: String,
    pub dt_s: f64,
    pub duration_s: f64,
    pub record_every: u64,
    pub stop_at_ground: bool,
    pub environment: Environment,
    pub vehicle: Vehicle,
    pub initial: Initial,
    pub burns: Vec<Burn>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Environment {
    pub gravity_mps2: f64,
    /// `None`: vacuum.
    pub atmosphere: Option<Atmosphere>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Atmosphere {
    pub density_kgpm3: f64,
    /// `None`: constant density.
    pub scale_height_m: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Vehicle {
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
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Initial {
    pub position_m: [f64; 3],
    pub velocity_mps: [f64; 3],
    pub attitude: [f64; 4],
    pub angular_velocity_radps: [f64; 3],
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Burn {
    pub start_s: f64,
    pub end_s: f64,
    pub throttle: f64,
    pub direction_body: [f64; 3],
}

/// A burn as step indices `[start_step, end_step)` with a unit direction.
#[derive(Clone, Copy, Debug)]
pub struct Segment {
    pub start_step: u64,
    pub end_step: u64,
    pub thrust_n: f64,
    pub direction: Vec3,
}

#[derive(Clone, Debug)]
pub struct Prepared {
    pub dt: f64,
    pub steps: u64,
    pub record_every: u64,
    pub stop_at_ground: bool,
    pub gravity: f64,
    pub atmosphere: Option<(f64, Option<f64>)>,
    pub vehicle: Vehicle,
    pub r0: Vec3,
    pub v0: Vec3,
    pub q0: Quat,
    pub w0: Vec3,
    pub segments: Vec<Segment>,
}

fn finite(value: f64, name: &str) -> Result<f64, String> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(format!("{name} must be a finite number"))
    }
}

fn within(value: f64, name: &str, low: f64, high: f64) -> Result<f64, String> {
    finite(value, name)?;
    if value < low || value > high {
        return Err(format!("{name} must be in [{low}, {high}]"));
    }
    Ok(value)
}

fn steps_of(seconds: f64, dt: f64, name: &str) -> Result<u64, String> {
    let ratio = seconds / dt;
    let steps = ratio.round();
    if (ratio - steps).abs() > ALIGN_TOLERANCE * steps.max(1.0) {
        return Err(format!("{name} must be a whole number of steps of dt"));
    }
    Ok(steps as u64)
}

fn inertia(values: [f64; 3], name: &str, allow_zero: bool) -> Result<Vec3, String> {
    for (i, v) in values.iter().enumerate() {
        within(*v, &format!("{name}[{i}]"), 0.0, 1e12)?;
        if !allow_zero && *v == 0.0 {
            return Err(format!("{name}[{i}] must be positive"));
        }
    }
    let [a, b, c] = values;
    if a + b < c || b + c < a || a + c < b {
        return Err(format!(
            "{name} violates the triangle inequality of principal moments"
        ));
    }
    Ok(Vec3::from_array(values))
}

pub fn prepare(case: &Case) -> Result<Prepared, String> {
    if case.schema != CASE_SCHEMA {
        return Err(format!("schema must be {CASE_SCHEMA}"));
    }
    if case.name.is_empty() || case.name.len() > 80 {
        return Err("name must have 1 to 80 characters".into());
    }
    let dt = within(case.dt_s, "dt_s", MIN_DT, MAX_DT)?;
    within(case.duration_s, "duration_s", dt, 1e6)?;
    let steps = steps_of(case.duration_s, dt, "duration_s")?;
    if steps > MAX_STEPS {
        return Err(format!("duration_s / dt_s exceeds {MAX_STEPS} steps"));
    }
    if case.record_every == 0 || case.record_every > steps {
        return Err("record_every must be in [1, steps]".into());
    }
    if steps / case.record_every + 2 > MAX_SAMPLES {
        return Err(format!(
            "trace would exceed {MAX_SAMPLES} samples; raise record_every"
        ));
    }

    let env = &case.environment;
    let gravity = within(env.gravity_mps2, "environment.gravity_mps2", 0.0, 100.0)?;
    let atmosphere = match &env.atmosphere {
        None => None,
        Some(a) => {
            let rho = within(a.density_kgpm3, "atmosphere.density_kgpm3", 0.0, 100.0)?;
            let h = match a.scale_height_m {
                None => None,
                Some(h) => Some(within(h, "atmosphere.scale_height_m", 100.0, 1e6)?),
            };
            Some((rho, h))
        }
    };

    let v = &case.vehicle;
    within(v.dry_mass_kg, "vehicle.dry_mass_kg", 1e-3, 1e9)?;
    within(v.propellant_mass_kg, "vehicle.propellant_mass_kg", 0.0, 1e9)?;
    within(v.dry_cm_station_m, "vehicle.dry_cm_station_m", -1e4, 1e4)?;
    within(
        v.propellant_cm_station_m,
        "vehicle.propellant_cm_station_m",
        -1e4,
        1e4,
    )?;
    inertia(v.dry_inertia_kgm2, "vehicle.dry_inertia_kgm2", false)?;
    inertia(
        v.propellant_inertia_kgm2,
        "vehicle.propellant_inertia_kgm2",
        true,
    )?;
    if v.propellant_mass_kg == 0.0 && v.propellant_inertia_kgm2 != [0.0; 3] {
        return Err("vehicle.propellant_inertia_kgm2 must be zero without propellant".into());
    }
    within(v.max_thrust_n, "vehicle.max_thrust_n", 0.0, 1e9)?;
    within(v.isp_s, "vehicle.isp_s", 1.0, 1e4)?;
    within(v.drag_coefficient, "vehicle.drag_coefficient", 0.0, 10.0)?;
    within(v.reference_area_m2, "vehicle.reference_area_m2", 0.0, 1e4)?;

    let i = &case.initial;
    for (k, x) in i.position_m.iter().enumerate() {
        within(*x, &format!("initial.position_m[{k}]"), -1e7, 1e7)?;
    }
    for (k, x) in i.velocity_mps.iter().enumerate() {
        within(*x, &format!("initial.velocity_mps[{k}]"), -1e5, 1e5)?;
    }
    for (k, x) in i.angular_velocity_radps.iter().enumerate() {
        within(
            *x,
            &format!("initial.angular_velocity_radps[{k}]"),
            -100.0,
            100.0,
        )?;
    }
    for (k, x) in i.attitude.iter().enumerate() {
        finite(*x, &format!("initial.attitude[{k}]"))?;
    }
    let q = Quat::from_array(i.attitude);
    if (q.norm() - 1.0).abs() > QUAT_NORM_TOLERANCE {
        return Err("initial.attitude must be a unit quaternion (w, x, y, z)".into());
    }

    let mut segments = Vec::new();
    let mut consumed = 0.0;
    for (k, b) in case.burns.iter().enumerate() {
        let name = format!("burns[{k}]");
        within(b.start_s, &format!("{name}.start_s"), 0.0, case.duration_s)?;
        within(b.end_s, &format!("{name}.end_s"), 0.0, case.duration_s)?;
        let start_step = steps_of(b.start_s, dt, &format!("{name}.start_s"))?;
        let end_step = steps_of(b.end_s, dt, &format!("{name}.end_s"))?;
        if end_step <= start_step {
            return Err(format!("{name}.end_s must be after start_s"));
        }
        if segments
            .last()
            .is_some_and(|s: &Segment| start_step < s.end_step)
        {
            return Err(format!("{name} overlaps or precedes the previous burn"));
        }
        let throttle = within(b.throttle, &format!("{name}.throttle"), 0.0, 1.0)?;
        let d = Vec3::from_array(b.direction_body);
        // A finite vector can still overflow its norm (1e200), which would silently zero the thrust.
        if !d.is_finite() || d.norm() == 0.0 || !d.norm().is_finite() {
            return Err(format!(
                "{name}.direction_body must be a finite non-zero vector"
            ));
        }
        let thrust_n = throttle * v.max_thrust_n;
        consumed += thrust_n / (v.isp_s * G0) * ((end_step - start_step) as f64 * dt);
        segments.push(Segment {
            start_step,
            end_step,
            thrust_n,
            direction: d * (1.0 / d.norm()),
        });
    }
    if consumed > v.propellant_mass_kg {
        return Err(format!(
            "burns need {consumed} kg of propellant but the vehicle carries {} kg",
            v.propellant_mass_kg
        ));
    }

    Ok(Prepared {
        dt,
        steps,
        record_every: case.record_every,
        stop_at_ground: case.stop_at_ground,
        gravity,
        atmosphere,
        vehicle: v.clone(),
        r0: Vec3::from_array(i.position_m),
        v0: Vec3::from_array(i.velocity_mps),
        q0: q.normalized(),
        w0: Vec3::from_array(i.angular_velocity_radps),
        segments,
    })
}
