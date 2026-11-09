//! Catalog of the ascent domain: one scenario per exploratory vehicle, the single flight-software
//! policy, the mission parameters that have a real meaning in the model (with ranges the simulator
//! validates again), the requirements, the channels and the demonstrations. A parameter default is
//! the value its vehicle template really holds (a test checks it), so each vehicle has its own ids.

use std::collections::BTreeMap;

use vv_platform::contract::*;

pub const DOMAIN: &str = "launch-ascent";
pub const SMALL: &str = "small-leo";
pub const MEDIUM: &str = "medium-leo";
pub const CONTROLLER: &str = "explicit-guidance";

fn item(id: &str, label: &str, description: &str) -> Item {
    Item {
        id: id.into(),
        label: label.into(),
        description: description.into(),
        facts: Vec::new(),
    }
}

/// What a parameter sets in the case.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Target {
    TargetAltitudeKm,
    KickTimeS,
    KickAngleDeg,
    GravityTurnStartS,
    PayloadKg,
    Dispersions,
}

pub struct Param {
    pub id: &'static str,
    pub scenario: Option<&'static str>,
    pub target: Target,
    pub label: &'static str,
    pub description: &'static str,
    pub unit: &'static str,
    pub group: &'static str,
    pub min: f64,
    pub max: f64,
    pub step: f64,
    pub default: f64,
    pub integer: bool,
}

const TARGET: &str = "Altitude of the circular target orbit. The upper-stage guidance steers to it and cuts the engine when the orbital energy of that orbit is reached; the apoapsis requirement is judged against it.";
const KICK_T: &str = "Time after ignition at which the first stage starts tilting from the vertical. Must be a multiple of the 20 ms step.";
const KICK_A: &str = "Tilt from the vertical reached at the end of the pitch kick, downrange. It sets how lofted or flat the gravity turn is: too little and the stage climbs steeply and stages slowly, too much and it stays low in dense air.";
const TURN: &str = "Time after ignition at which the thrust starts following the observed velocity (gravity turn). Not before the end of the pitch kick (kick time plus its fixed duration).";
const PAYLOAD: &str = "Payload mass carried by the upper stage. It changes the stack mass, the liftoff thrust-to-weight and the upper-stage performance.";
const DISP: &str = "1 draws the seeded dispersions of thrust, Isp, loaded propellant and dry mass of each stage (the flight software still assumes the nominal vehicle); 0 flies the nominal vehicle. Navigation noise is always seeded.";

#[rustfmt::skip]
pub const PARAMS: [Param; 11] = [
    Param { id: "small_target_altitude_km", scenario: Some(SMALL), target: Target::TargetAltitudeKm, label: "Target orbit altitude", description: TARGET, unit: "km", group: "Mission", min: 250.0, max: 450.0, step: 10.0, default: 300.0, integer: false },
    Param { id: "small_kick_time_s", scenario: Some(SMALL), target: Target::KickTimeS, label: "Pitch kick time", description: KICK_T, unit: "s", group: "Pitch programme", min: 4.0, max: 20.0, step: 0.5, default: 8.0, integer: false },
    Param { id: "small_kick_angle_deg", scenario: Some(SMALL), target: Target::KickAngleDeg, label: "Pitch kick angle", description: KICK_A, unit: "deg", group: "Pitch programme", min: 0.5, max: 8.0, step: 0.25, default: 2.5, integer: false },
    Param { id: "small_gravity_turn_start_s", scenario: Some(SMALL), target: Target::GravityTurnStartS, label: "Gravity turn start", description: TURN, unit: "s", group: "Pitch programme", min: 8.5, max: 40.0, step: 0.5, default: 14.0, integer: false },
    Param { id: "small_payload_kg", scenario: Some(SMALL), target: Target::PayloadKg, label: "Payload mass", description: PAYLOAD, unit: "kg", group: "Vehicle", min: 0.0, max: 1500.0, step: 10.0, default: 250.0, integer: false },
    Param { id: "medium_target_altitude_km", scenario: Some(MEDIUM), target: Target::TargetAltitudeKm, label: "Target orbit altitude", description: TARGET, unit: "km", group: "Mission", min: 300.0, max: 600.0, step: 10.0, default: 400.0, integer: false },
    Param { id: "medium_kick_time_s", scenario: Some(MEDIUM), target: Target::KickTimeS, label: "Pitch kick time", description: KICK_T, unit: "s", group: "Pitch programme", min: 4.0, max: 20.0, step: 0.5, default: 10.0, integer: false },
    Param { id: "medium_kick_angle_deg", scenario: Some(MEDIUM), target: Target::KickAngleDeg, label: "Pitch kick angle", description: KICK_A, unit: "deg", group: "Pitch programme", min: 0.5, max: 8.0, step: 0.25, default: 3.0, integer: false },
    Param { id: "medium_gravity_turn_start_s", scenario: Some(MEDIUM), target: Target::GravityTurnStartS, label: "Gravity turn start", description: TURN, unit: "s", group: "Pitch programme", min: 9.5, max: 40.0, step: 0.5, default: 18.0, integer: false },
    Param { id: "medium_payload_kg", scenario: Some(MEDIUM), target: Target::PayloadKg, label: "Payload mass", description: PAYLOAD, unit: "kg", group: "Vehicle", min: 0.0, max: 10000.0, step: 100.0, default: 3000.0, integer: false },
    Param { id: "dispersions", scenario: None, target: Target::Dispersions, label: "Dispersions on", description: DISP, unit: "", group: "Dispersions", min: 0.0, max: 1.0, step: 1.0, default: 1.0, integer: true },
];

/// The vehicle's measured attributes, read from the template it is simulated with.
fn with_facts(mut v: Item, scenario: &str) -> Item {
    let case = crate::case::template(scenario).expect("bundled template");
    let veh = &case.vehicle;
    let fact = |label: &str, value: f64, unit: &str| Fact {
        label: label.into(),
        value,
        unit: unit.into(),
    };
    let liftoff: f64 = veh
        .stages
        .iter()
        .map(|s| s.dry_mass_kg + s.propellant_kg)
        .sum::<f64>()
        + veh.payload_kg;
    let mut facts = vec![
        fact("Liftoff mass", liftoff / 1000.0, "t"),
        fact("Payload", veh.payload_kg, "kg"),
    ];
    for (i, s) in veh.stages.iter().enumerate() {
        let n = i + 1;
        facts.push(fact(
            &format!("Stage {n} thrust (vacuum)"),
            s.thrust_vac_n / 1000.0,
            "kN",
        ));
        facts.push(fact(&format!("Stage {n} Isp (vacuum)"), s.isp_vac_s, "s"));
        facts.push(fact(
            &format!("Stage {n} propellant"),
            s.propellant_kg / 1000.0,
            "t",
        ));
    }
    facts.push(fact(
        "Liftoff thrust over weight",
        veh.stages[0].thrust_vac_n * veh.stages[0].isp_sl_s
            / veh.stages[0].isp_vac_s
            / (liftoff * 9.80665),
        "",
    ));
    v.facts = facts;
    v
}

pub fn param(id: &str) -> Option<&'static Param> {
    PARAMS.iter().find(|p| p.id == id)
}

pub fn parameters() -> Vec<ParameterSpec> {
    PARAMS
        .iter()
        .map(|p| ParameterSpec {
            id: p.id.into(),
            label: p.label.into(),
            description: p.description.into(),
            unit: p.unit.into(),
            group: p.group.into(),
            advanced: matches!(p.target, Target::GravityTurnStartS | Target::KickTimeS),
            min: p.min,
            max: p.max,
            step: p.step,
            default: p.default,
            integer: p.integer,
            influences: Vec::new(),
        })
        .collect()
}

fn scenario_params(scenario: &str) -> Vec<String> {
    PARAMS
        .iter()
        .filter(|p| p.scenario.is_none_or(|s| s == scenario))
        .map(|p| p.id.to_string())
        .collect()
}

fn requirement(id: &str, label: &str, category: &str, description: &str) -> RequirementSpec {
    RequirementSpec {
        id: id.into(),
        label: label.into(),
        category: category.into(),
        description: description.into(),
    }
}

pub fn requirements() -> Vec<RequirementSpec> {
    vec![
        requirement(
            "stack.S1_max_dynamic_pressure",
            "Maximum dynamic pressure",
            "invariant",
            "True dynamic pressure of the stack at most the declared limit at every flown tick.",
        ),
        requirement(
            "stack.S2_axial_acceleration",
            "Maximum sensed acceleration (stack)",
            "invariant",
            "True non-gravitational acceleration of the stack at most the declared limit at every flown tick.",
        ),
        requirement(
            "upper.S2_axial_acceleration",
            "Maximum sensed acceleration (upper stage)",
            "invariant",
            "True non-gravitational acceleration of the upper stage at most the declared limit at every tick.",
        ),
        requirement(
            "stack.R1_separation_window",
            "Separation window",
            "requirement",
            "True altitude and speed of the stack inside the declared window at separation.",
        ),
        requirement(
            "booster.R2_propellant_margin",
            "Booster propellant margin",
            "requirement",
            "True first-stage residual at MECO at least the declared recovery minimum, and no depletion before MECO.",
        ),
        requirement(
            "booster.R3_recovery_zone",
            "Booster impact in the recovery zone",
            "requirement",
            "Interpolated ballistic impact point of the booster inside the declared downrange zone.",
        ),
        requirement(
            "upper.R4_periapsis",
            "Periapsis altitude",
            "requirement",
            "Periapsis of the true osculating orbit at SECO at least the declared minimum.",
        ),
        requirement(
            "upper.R5_apoapsis",
            "Apoapsis on target",
            "requirement",
            "Apoapsis of the true osculating orbit at SECO within the declared tolerance of the target altitude.",
        ),
        requirement(
            "upper.R6_propellant_margin",
            "Upper-stage propellant margin",
            "requirement",
            "SECO on the energy criterion, no depletion, true residual at least the declared minimum.",
        ),
        requirement(
            "mission.R7_phase_sequence",
            "Phase sequence",
            "requirement",
            "Ignition, liftoff, pitch kick, gravity turn, MECO, separation, upper ignition and SECO all occur, in this order.",
        ),
        requirement(
            "mission.R8_orbit_insertion",
            "Orbit insertion",
            "requirement",
            "Periapsis and apoapsis requirements met and the upper stage never reaches the surface.",
        ),
    ]
}

fn channel_spec(id: &str, label: &str, unit: &str, group: &str, kind: &str) -> ChannelSpec {
    ChannelSpec {
        id: id.into(),
        label: label.into(),
        unit: unit.into(),
        group: group.into(),
        kind: kind.into(),
    }
}

pub fn request(scenario: &str, seed: u64, parameters: &[(&str, f64)]) -> RunRequest {
    RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: DOMAIN.into(),
        scenario: scenario.into(),
        controller: CONTROLLER.into(),
        seed,
        faults: Vec::new(),
        parameters: parameters
            .iter()
            .map(|(k, v)| (k.to_string(), *v))
            .collect::<BTreeMap<_, _>>(),
    }
}

pub fn catalog() -> DomainCatalog {
    DomainCatalog {
        schema: CATALOG_SCHEMA.into(),
        domain: DOMAIN.into(),
        time: TimeSpec {
            unit: "s".into(),
            label: "s of logical time (ticks of 20 ms from the start of the prelaunch hold)".into(),
        },
        vehicles: vec![
            with_facts(item("small", "Small launcher (exploratory)", "About 35 t at liftoff, two stages, 250 kg nominal payload; not a real vehicle."), SMALL),
            with_facts(item("medium", "Medium launcher (exploratory)", "About 304 t at liftoff, two stages, 3 t nominal payload, a 6 % first-stage reserve kept for recovery; not a real vehicle."), MEDIUM),
        ],
        scenarios: vec![
            ScenarioSpec {
                id: SMALL.into(),
                label: "Small launcher to a low orbit".into(),
                description: "Ascent of the small exploratory launcher to a 300 km circular orbit; the booster falls ballistically towards a declared zone 850 to 1150 km downrange.".into(),
                vehicle: "small".into(),
                controllers: vec![CONTROLLER.into()],
                parameters: scenario_params(SMALL),
                default_controller: CONTROLLER.into(),
            },
            ScenarioSpec {
                id: MEDIUM.into(),
                label: "Medium launcher to a low orbit".into(),
                description: "Ascent of the medium exploratory launcher to a 400 km circular orbit; the booster falls ballistically towards a declared zone 650 to 900 km downrange.".into(),
                vehicle: "medium".into(),
                controllers: vec![CONTROLLER.into()],
                parameters: scenario_params(MEDIUM),
                default_controller: CONTROLLER.into(),
            },
        ],
        controllers: vec![item(
            CONTROLLER,
            "Pitch programme and explicit radial guidance",
            "First stage: vertical rise, pitch kick, gravity turn along the observed velocity, throttle cut for dynamic pressure and acceleration, MECO on its own propellant estimate. Upper stage: explicit radial guidance to the target radius with zero radial rate, SECO on the observed orbital energy. Sees only the noisy navigation solution and the nominal vehicle.",
        )],
        parameters: parameters(),
        faults: Vec::new(),
        max_faults: 0,
        channels: vec![
            channel_spec("<entity>_altitude_km", "Altitude", "km", "Trajectory", "truth"),
            channel_spec("<entity>_downrange_km", "Downrange distance over the surface", "km", "Trajectory", "truth"),
            channel_spec("<entity>_speed_m_s", "Inertial speed", "m/s", "Trajectory", "truth"),
            channel_spec("<entity>_dynamic_pressure_kpa", "Dynamic pressure", "kPa", "Loads", "truth"),
            channel_spec("<entity>_sensed_acceleration_g", "Sensed acceleration", "g", "Loads", "truth"),
            channel_spec("<entity>_observed_altitude_km", "Navigation altitude", "km", "Trajectory", "observation"),
            channel_spec("<entity>_throttle", "Throttle", "", "Propulsion", "command"),
        ],
        requirements: requirements(),
        demos: crate::demos::demos(),
    }
}
