//! The ascent case: vehicle (simulated attributes), visual block (never read by the simulation),
//! mission and guidance settings, verification limits, dispersions and sensors. Readers refuse
//! unknown fields; `validate` checks every range before a run, and `prepare` applies the seeded
//! dispersions to produce the true vehicle, which only the truth model ever sees.

use serde::{Deserialize, Serialize};

use crate::prng::{SplitMix64, source};

pub const CASE_SCHEMA: &str = "vv-ascent-case.v1";
/// Label every case must carry: the vehicles are exploratory, not real vehicles.
pub const EXPLORATORY: &str = "exploratory, not a real vehicle";
pub const SIMULATED_ROLE: &str = "simulated";
pub const VISUAL_ROLE: &str = "visual-only, never read by the simulation";

/// Standard gravitational parameter of the Earth, m^3/s^2.
pub const MU: f64 = 3.986_004_418e14;
/// Mean radius of the spherical, non-rotating Earth, m.
pub const R_EARTH: f64 = 6_371_000.0;
/// Standard gravity for Isp, m/s^2.
pub const G0: f64 = 9.806_65;
/// Exponential atmosphere: sea-level density and scale height.
pub const RHO0: f64 = 1.225;
pub const SCALE_HEIGHT: f64 = 8_500.0;
/// Fixed integration step: one logical tick is 20 ms.
pub const DT: f64 = 0.02;
pub const TICKS_PER_S: u64 = 50;
/// Hard bound on a run, whatever the case says.
pub const MAX_TICKS: u64 = 4_000 * TICKS_PER_S;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct StageDef {
    pub id: String,
    pub label: String,
    pub dry_mass_kg: f64,
    pub propellant_kg: f64,
    pub thrust_vac_n: f64,
    pub isp_vac_s: f64,
    pub isp_sl_s: f64,
    pub reference_area_m2: f64,
    pub drag_coefficient: f64,
    pub throttle_min: f64,
    pub throttle_max: f64,
    /// Fraction of the loaded propellant the guidance keeps unburned (booster recovery reserve,
    /// upper-stage residual reserve).
    pub reserve_fraction: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct VehicleDef {
    /// Must be `simulated`: every field below is read by the physics.
    pub role: String,
    pub label: String,
    /// Stage 1 (booster) then stage 2 (upper stage).
    pub stages: Vec<StageDef>,
    pub payload_kg: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct VisualStage {
    pub length_m: f64,
    pub diameter_m: f64,
    pub colour: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct VisualDef {
    /// Must be `visual-only, never read by the simulation`.
    pub role: String,
    pub stages: Vec<VisualStage>,
    pub fairing_colour: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Zone {
    pub downrange_min_km: f64,
    pub downrange_max_km: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct GuidanceDef {
    /// The first stage throttles down while its estimated dynamic pressure exceeds this.
    pub q_target_pa: f64,
    /// Throttle cap so the estimated thrust acceleration stays below this, in g.
    pub axial_g_target: f64,
    /// Upper stage: floor on the time to go used by the explicit radial guidance, s.
    pub min_time_to_go_s: f64,
    /// Upper stage: limit on the sine of the thrust elevation above the local horizontal.
    pub max_sin_elevation: f64,
    /// Upper stage: below this estimated velocity to go the throttle goes to its minimum, m/s.
    pub terminal_dv_m_s: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MissionDef {
    pub hold_s: f64,
    /// Times after liftoff.
    pub kick_time_s: f64,
    pub kick_duration_s: f64,
    pub kick_angle_deg: f64,
    pub gravity_turn_start_s: f64,
    pub separation_delay_s: f64,
    pub ignition_delay_s: f64,
    pub target_altitude_km: f64,
    pub coast_after_seco_s: f64,
    pub max_duration_s: f64,
    pub recovery_zone: Zone,
    pub guidance: GuidanceDef,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Limits {
    pub max_q_pa: f64,
    pub max_axial_g: f64,
    pub separation_altitude_km: [f64; 2],
    pub separation_speed_m_s: [f64; 2],
    pub apoapsis_tolerance_km: f64,
    pub min_periapsis_km: f64,
    /// Per stage, the smallest true residual propellant at cutoff, as a fraction of the nominal
    /// load (stage 1: the recovery reserve the mission must keep).
    pub min_residual_fraction: [f64; 2],
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Dispersions {
    pub enabled: bool,
    /// One-sigma relative dispersions per stage (Irwin-Hall, bounded at 2 sqrt 3 sigma).
    pub thrust_sigma: f64,
    pub isp_sigma: f64,
    pub propellant_sigma: f64,
    pub dry_mass_sigma: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Sensors {
    /// Navigation solution noise per axis, one sigma.
    pub position_sigma_m: f64,
    pub velocity_sigma_m_s: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Case {
    pub schema: String,
    pub name: String,
    /// Must be `exploratory, not a real vehicle`.
    pub status: String,
    pub provenance: Vec<String>,
    pub vehicle: VehicleDef,
    pub visual: VisualDef,
    pub mission: MissionDef,
    pub limits: Limits,
    pub dispersions: Dispersions,
    pub sensors: Sensors,
}

/// True parameters of one stage after dispersion; only the truth model reads them.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct TrueStage {
    pub dry_mass_kg: f64,
    pub propellant_kg: f64,
    pub thrust_vac_n: f64,
    pub isp_vac_s: f64,
    pub isp_sl_s: f64,
    pub reference_area_m2: f64,
    pub drag_coefficient: f64,
    pub throttle_min: f64,
    pub throttle_max: f64,
}

/// Simulated attributes only: the visual block is not part of it, so it cannot reach the physics.
#[derive(Clone, Debug, PartialEq)]
pub struct Prepared {
    pub seed: u64,
    pub vehicle: VehicleDef,
    pub mission: MissionDef,
    pub limits: Limits,
    pub sensors: Sensors,
    pub dispersions_enabled: bool,
    pub truth: [TrueStage; 2],
    /// Dispersion factors applied (thrust, isp, propellant, dry mass) per stage, for the record.
    pub factors: [[f64; 4]; 2],
}

fn range(value: f64, lo: f64, hi: f64, name: &str) -> Result<(), String> {
    if !value.is_finite() || value < lo || value > hi {
        return Err(format!("{name} must be in {lo} to {hi}, got {value}"));
    }
    Ok(())
}

fn whole_ticks(value: f64, name: &str) -> Result<(), String> {
    let ticks = value * TICKS_PER_S as f64;
    if (ticks - ticks.round()).abs() > 1e-9 {
        return Err(format!("{name} must be a multiple of {DT} s"));
    }
    Ok(())
}

pub fn validate(case: &Case) -> Result<(), String> {
    if case.schema != CASE_SCHEMA {
        return Err(format!("schema must be {CASE_SCHEMA}"));
    }
    if case.status != EXPLORATORY {
        return Err(format!("status must be \"{EXPLORATORY}\""));
    }
    if case.vehicle.role != SIMULATED_ROLE {
        return Err(format!("vehicle.role must be \"{SIMULATED_ROLE}\""));
    }
    if case.visual.role != VISUAL_ROLE {
        return Err(format!("visual.role must be \"{VISUAL_ROLE}\""));
    }
    if case.vehicle.stages.len() != 2 || case.visual.stages.len() != 2 {
        return Err("a vehicle has exactly two stages, in vehicle and in visual".into());
    }
    for (i, s) in case.vehicle.stages.iter().enumerate() {
        let n = |f: &str| format!("vehicle.stages[{i}].{f}");
        range(s.dry_mass_kg, 50.0, 1e6, &n("dry_mass_kg"))?;
        range(s.propellant_kg, 100.0, 5e6, &n("propellant_kg"))?;
        range(s.thrust_vac_n, 1e3, 1e8, &n("thrust_vac_n"))?;
        range(s.isp_vac_s, 100.0, 500.0, &n("isp_vac_s"))?;
        range(s.isp_sl_s, 50.0, s.isp_vac_s, &n("isp_sl_s"))?;
        range(s.reference_area_m2, 0.05, 100.0, &n("reference_area_m2"))?;
        range(s.drag_coefficient, 0.05, 3.0, &n("drag_coefficient"))?;
        range(s.throttle_min, 0.1, 1.0, &n("throttle_min"))?;
        range(s.throttle_max, s.throttle_min, 1.0, &n("throttle_max"))?;
        range(s.reserve_fraction, 0.0, 0.3, &n("reserve_fraction"))?;
    }
    for (i, v) in case.visual.stages.iter().enumerate() {
        range(
            v.length_m,
            0.1,
            200.0,
            &format!("visual.stages[{i}].length_m"),
        )?;
        range(
            v.diameter_m,
            0.1,
            20.0,
            &format!("visual.stages[{i}].diameter_m"),
        )?;
    }
    range(case.vehicle.payload_kg, 0.0, 1e6, "vehicle.payload_kg")?;
    let m = &case.mission;
    range(m.hold_s, 0.0, 60.0, "mission.hold_s")?;
    range(m.kick_time_s, 1.0, 60.0, "mission.kick_time_s")?;
    range(m.kick_duration_s, 0.5, 30.0, "mission.kick_duration_s")?;
    range(m.kick_angle_deg, 0.0, 20.0, "mission.kick_angle_deg")?;
    range(
        m.gravity_turn_start_s,
        m.kick_time_s + m.kick_duration_s,
        200.0,
        "mission.gravity_turn_start_s (not before the end of the pitch kick)",
    )?;
    range(
        m.separation_delay_s,
        0.5,
        30.0,
        "mission.separation_delay_s",
    )?;
    range(m.ignition_delay_s, 0.5, 30.0, "mission.ignition_delay_s")?;
    range(
        m.target_altitude_km,
        150.0,
        2000.0,
        "mission.target_altitude_km",
    )?;
    range(
        m.coast_after_seco_s,
        0.0,
        3000.0,
        "mission.coast_after_seco_s",
    )?;
    range(m.max_duration_s, 60.0, 4000.0, "mission.max_duration_s")?;
    for (v, name) in [
        (m.hold_s, "mission.hold_s"),
        (m.kick_time_s, "mission.kick_time_s"),
        (m.kick_duration_s, "mission.kick_duration_s"),
        (m.gravity_turn_start_s, "mission.gravity_turn_start_s"),
        (m.separation_delay_s, "mission.separation_delay_s"),
        (m.ignition_delay_s, "mission.ignition_delay_s"),
        (m.coast_after_seco_s, "mission.coast_after_seco_s"),
        (m.max_duration_s, "mission.max_duration_s"),
    ] {
        whole_ticks(v, name)?;
    }
    let z = &m.recovery_zone;
    range(
        z.downrange_min_km,
        0.0,
        5000.0,
        "recovery_zone.downrange_min_km",
    )?;
    range(
        z.downrange_max_km,
        z.downrange_min_km,
        5000.0,
        "recovery_zone.downrange_max_km",
    )?;
    let g = &m.guidance;
    range(g.q_target_pa, 1e3, 1e5, "guidance.q_target_pa")?;
    range(g.axial_g_target, 1.0, 15.0, "guidance.axial_g_target")?;
    range(g.min_time_to_go_s, 5.0, 1000.0, "guidance.min_time_to_go_s")?;
    range(g.max_sin_elevation, 0.1, 1.0, "guidance.max_sin_elevation")?;
    range(g.terminal_dv_m_s, 0.0, 500.0, "guidance.terminal_dv_m_s")?;
    let l = &case.limits;
    range(l.max_q_pa, 1e3, 2e5, "limits.max_q_pa")?;
    range(l.max_axial_g, 1.0, 20.0, "limits.max_axial_g")?;
    range(
        l.separation_altitude_km[0],
        0.0,
        500.0,
        "limits.separation_altitude_km[0]",
    )?;
    range(
        l.separation_altitude_km[1],
        l.separation_altitude_km[0],
        500.0,
        "limits.separation_altitude_km[1]",
    )?;
    range(
        l.separation_speed_m_s[0],
        0.0,
        8000.0,
        "limits.separation_speed_m_s[0]",
    )?;
    range(
        l.separation_speed_m_s[1],
        l.separation_speed_m_s[0],
        8000.0,
        "limits.separation_speed_m_s[1]",
    )?;
    range(
        l.apoapsis_tolerance_km,
        0.1,
        500.0,
        "limits.apoapsis_tolerance_km",
    )?;
    range(l.min_periapsis_km, 50.0, 2000.0, "limits.min_periapsis_km")?;
    for (i, f) in l.min_residual_fraction.iter().enumerate() {
        range(*f, 0.0, 0.3, &format!("limits.min_residual_fraction[{i}]"))?;
    }
    let d = &case.dispersions;
    for (v, name) in [
        (d.thrust_sigma, "dispersions.thrust_sigma"),
        (d.isp_sigma, "dispersions.isp_sigma"),
        (d.propellant_sigma, "dispersions.propellant_sigma"),
        (d.dry_mass_sigma, "dispersions.dry_mass_sigma"),
    ] {
        range(v, 0.0, 0.05, name)?;
    }
    range(
        case.sensors.position_sigma_m,
        0.0,
        1000.0,
        "sensors.position_sigma_m",
    )?;
    range(
        case.sensors.velocity_sigma_m_s,
        0.0,
        10.0,
        "sensors.velocity_sigma_m_s",
    )?;
    Ok(())
}

const STREAMS: [[u64; 4]; 2] = [
    [
        source::STAGE1_THRUST,
        source::STAGE1_ISP,
        source::STAGE1_PROPELLANT,
        source::STAGE1_DRY_MASS,
    ],
    [
        source::STAGE2_THRUST,
        source::STAGE2_ISP,
        source::STAGE2_PROPELLANT,
        source::STAGE2_DRY_MASS,
    ],
];

/// Validates the case and applies the seeded dispersions. One draw per factor from its own stream,
/// so turning one dispersion off never shifts another. Disabled dispersions draw nothing.
pub fn prepare(case: &Case, seed: u64) -> Result<Prepared, String> {
    validate(case)?;
    let d = &case.dispersions;
    let sigmas = [
        d.thrust_sigma,
        d.isp_sigma,
        d.propellant_sigma,
        d.dry_mass_sigma,
    ];
    let mut factors = [[1.0; 4]; 2];
    let mut truth = Vec::with_capacity(2);
    for (i, s) in case.vehicle.stages.iter().enumerate() {
        if d.enabled {
            for k in 0..4 {
                factors[i][k] = 1.0 + SplitMix64::stream(seed, STREAMS[i][k]).noise(sigmas[k]);
            }
        }
        let f = factors[i];
        truth.push(TrueStage {
            dry_mass_kg: s.dry_mass_kg * f[3],
            propellant_kg: s.propellant_kg * f[2],
            thrust_vac_n: s.thrust_vac_n * f[0],
            // Sea-level and vacuum Isp share one factor: the nozzle is the same, the engine differs.
            isp_vac_s: s.isp_vac_s * f[1],
            isp_sl_s: s.isp_sl_s * f[1],
            reference_area_m2: s.reference_area_m2,
            drag_coefficient: s.drag_coefficient,
            throttle_min: s.throttle_min,
            throttle_max: s.throttle_max,
        });
    }
    let truth: [TrueStage; 2] = truth.try_into().expect("two stages");
    Ok(Prepared {
        seed,
        vehicle: case.vehicle.clone(),
        mission: case.mission.clone(),
        limits: case.limits.clone(),
        sensors: case.sensors.clone(),
        dispersions_enabled: d.enabled,
        truth,
        factors,
    })
}

/// Parses case bytes, refusing unknown fields.
pub fn parse_case(bytes: &[u8]) -> Result<Case, String> {
    serde_json::from_slice(bytes).map_err(|e| format!("invalid case: {e}"))
}
