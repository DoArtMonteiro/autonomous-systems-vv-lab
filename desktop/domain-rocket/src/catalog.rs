//! The catalog of the rocket domain: the policies and the fault table with its pre-registered ranges
//! of the Python `landing_adapter`, two faults at most (the adapter takes one; the simulator accepts
//! two), plus a few controller tuning parameters and the demonstrations. Scenarios are split by case template so that a default is the value its
//! template really holds.

use std::collections::BTreeMap;

use vv_platform::contract::*;

use crate::case::{HEAVY, LIGHT, M9, M91};

pub const DOMAIN: &str = "rocket-landing";

fn item(id: &str, label: &str, description: &str) -> Item {
    Item {
        id: id.into(),
        label: label.into(),
        description: description.into(),
        facts: Vec::new(),
    }
}

fn strings(ids: &[&str]) -> Vec<String> {
    ids.iter().map(|s| s.to_string()).collect()
}

pub fn controllers() -> Vec<Item> {
    vec![
        item(
            "baseline",
            "Baseline",
            "Uses the latest reading of each sensor and trusts the radar altimeter for height.",
        ),
        item(
            "robust",
            "Robust",
            "Runs its own navigation filter and rejects an altimeter that disagrees with the GNSS and inertial estimate.",
        ),
        item(
            "guarded",
            "Guarded",
            "The robust estimator plus two rules: when altimeter and estimate disagree it guides on the lower altitude and reports sensor_disagreement, and it cuts the engine when it climbs under power (ascent_abort).",
        ),
        item(
            "baseline_guarded",
            "Baseline guarded",
            "The baseline policy unchanged plus the ascent-abort rule only (M9.1 test of that rule).",
        ),
    ]
}

struct Param {
    id: &'static str,
    label: &'static str,
    description: &'static str,
    unit: &'static str,
    min: f64,
    max: f64,
    step: f64,
    default: f64,
    group: &'static str,
    advanced: bool,
    /// Requirements this parameter is known to act on: a static, hand-written hint for the
    /// Experiment Lab, never computed from a run.
    influences: &'static [&'static str],
}

// Defaults equal the values of the two templates (a test checks it). The initial state, the vehicle
// and the atmosphere are not parameters: the simulator pins them to the pre-registered case and the
// seed disperses the initial state.
const PARAMS: [Param; 19] = [
    Param {
        id: "ignition_fraction",
        label: "Ignition point",
        unit: "",
        description: "The engine is lit when the thrust needed to brake over the remaining altitude reaches this fraction of the maximum thrust. Lower lights later and closer to the ground. Not part of the pre-registered tuning when changed.",
        min: 0.3,
        max: 1.2,
        step: 0.05,
        default: 0.75,
        group: "Controller tuning",
        advanced: true,
        influences: &["R1_vertical_speed", "R6_propellant_margin", "S3_axial_load"],
    },
    Param {
        id: "throttle_gain",
        label: "Throttle gain",
        unit: "",
        description: "Gain with which the throttle is corrected by the measured vertical specific force error. Higher tracks the descent profile harder. Not part of the pre-registered tuning when changed.",
        min: 0.2,
        max: 1.0,
        step: 0.05,
        default: 0.8,
        group: "Controller tuning",
        advanced: true,
        influences: &["R1_vertical_speed", "S5_no_powered_ascent"],
    },
    Param {
        id: "cutoff_altitude_m",
        label: "Engine cutoff altitude",
        unit: "m",
        description: "Below this estimated altitude of the nozzle plane the controller cuts the engine if the stage is moving upward (it never cuts a descending stage). Not part of the pre-registered tuning when changed.",
        min: 0.0,
        max: 100.0,
        step: 1.0,
        default: 15.0,
        group: "Controller tuning",
        advanced: true,
        influences: &["R1_vertical_speed", "S5_no_powered_ascent"],
    },
    Param {
        id: "lateral_position_gain",
        label: "Lateral position gain",
        unit: "1/s",
        description: "Wanted horizontal speed per metre of offset from the pad centre (before the braking curve and the fade near the ground). Higher chases the pad harder. Not part of the pre-registered tuning when changed.",
        min: 0.0,
        max: 1.0,
        step: 0.01,
        default: 0.12,
        group: "Controller tuning",
        advanced: true,
        influences: &["R5_position", "R2_horizontal_speed", "S2_keep_out"],
    },
    Param {
        id: "tilt_max_tan",
        label: "Largest commanded tilt",
        unit: "tan",
        description: "Upper cap on the tangent of the tilt the lateral guidance may command (the cap also shrinks near the ground). Lower keeps the stage more upright and limits its lateral authority. Not part of the pre-registered tuning when changed.",
        min: 0.02,
        max: 0.2,
        step: 0.01,
        default: 0.2,
        group: "Controller tuning",
        advanced: true,
        influences: &["R5_position", "R3_tilt", "S1_tilt_envelope"],
    },
    Param {
        id: "altimeter_residual_threshold_m",
        label: "Altimeter rejection threshold",
        unit: "m",
        description: "The robust and guarded estimators reject the radar altimeter after its reading disagrees with their own altitude by more than this for several control cycles in a row. Lower rejects a biased altimeter sooner and also rejects a healthy one more easily. The baseline policy ignores it. Not part of the pre-registered tuning when changed.",
        min: 0.5,
        max: 10.0,
        step: 0.5,
        default: 3.0,
        group: "Controller tuning",
        advanced: true,
        influences: &["R1_vertical_speed", "R6_propellant_margin"],
    },
    // M17 Experiment Lab. Initial state, sensor noise and two requirement limits: each maps to one
    // field of the case (case::parameter_path) and is written only when changed, so a default case
    // stays the pre-registered template byte for byte. The seed still disperses the initial state
    // around the value set here.
    Param {
        id: "initial_altitude_m",
        label: "Initial altitude",
        unit: "m",
        description: "Height of the centre of mass above the pad when the simulation starts, before the dispersion of the seed (about 50 m). Higher gives the controller more time and costs more propellant. Not part of the pre-registered case when changed.",
        min: 1500.0,
        max: 4000.0,
        step: 50.0,
        default: 3000.0,
        group: "Initial conditions",
        advanced: false,
        influences: &["R6_propellant_margin", "R1_vertical_speed"],
    },
    Param {
        id: "initial_downrange_m",
        label: "Initial offset east of the pad",
        unit: "m",
        description: "Horizontal offset from the pad centre along x when the simulation starts, before the dispersion of the seed (about 30 m). The lateral guidance has to remove it. Not part of the pre-registered case when changed.",
        min: -300.0,
        max: 300.0,
        step: 5.0,
        default: 80.0,
        group: "Initial conditions",
        advanced: false,
        influences: &["R5_position", "R2_horizontal_speed", "S2_keep_out"],
    },
    Param {
        id: "initial_crossrange_m",
        label: "Initial offset north of the pad",
        unit: "m",
        description: "Horizontal offset from the pad centre along y when the simulation starts, before the dispersion of the seed (about 30 m). Not part of the pre-registered case when changed.",
        min: -300.0,
        max: 300.0,
        step: 5.0,
        default: 0.0,
        group: "Initial conditions",
        advanced: false,
        influences: &["R5_position", "R2_horizontal_speed", "S2_keep_out"],
    },
    Param {
        id: "initial_vertical_velocity_mps",
        label: "Initial vertical velocity",
        unit: "m/s",
        description: "Vertical velocity when the simulation starts, negative downward, before the dispersion of the seed (about 10 m/s). A faster fall needs an earlier, harder burn and more propellant. Not part of the pre-registered case when changed.",
        min: -260.0,
        max: -150.0,
        step: 5.0,
        default: -200.0,
        group: "Initial conditions",
        advanced: false,
        influences: &["R1_vertical_speed", "R6_propellant_margin", "S3_axial_load"],
    },
    Param {
        id: "initial_horizontal_velocity_mps",
        label: "Initial horizontal velocity east",
        unit: "m/s",
        description: "Horizontal velocity along x when the simulation starts, before the dispersion of the seed (about 3 m/s). Negative moves the stage west, toward the pad when it starts east of it. Not part of the pre-registered case when changed.",
        min: -30.0,
        max: 30.0,
        step: 1.0,
        default: -12.0,
        group: "Initial conditions",
        advanced: false,
        influences: &["R5_position", "R2_horizontal_speed"],
    },
    Param {
        id: "altimeter_sigma_m",
        label: "Radar altimeter noise",
        unit: "m",
        description: "Standard deviation of the white noise on each radar altimeter reading. Not part of the pre-registered case when changed.",
        min: 0.02,
        max: 3.0,
        step: 0.02,
        default: 0.1,
        group: "Sensors",
        advanced: true,
        influences: &["R1_vertical_speed"],
    },
    Param {
        id: "gnss_position_sigma_m",
        label: "GNSS position noise",
        unit: "m",
        description: "Standard deviation of the white noise on each GNSS position component. The lateral guidance steers on the estimate it feeds. Not part of the pre-registered case when changed.",
        min: 0.1,
        max: 5.0,
        step: 0.1,
        default: 0.5,
        group: "Sensors",
        advanced: true,
        influences: &["R5_position", "R2_horizontal_speed"],
    },
    Param {
        id: "landing_zone_radius_m",
        label: "Landing-zone radius (R5)",
        unit: "m",
        description: "Largest distance of the touchdown point from the pad centre that R5 accepts. It changes only how the run is judged: the flight, the controller and every other verdict are unchanged. Not part of the pre-registered requirements when changed.",
        min: 2.0,
        max: 50.0,
        step: 1.0,
        default: 10.0,
        group: "Requirements",
        advanced: false,
        influences: &["R5_position"],
    },
    Param {
        id: "contact_vertical_speed_limit_mps",
        label: "Contact vertical speed limit (R1)",
        unit: "m/s",
        description: "Largest vertical speed at contact that R1 accepts. It changes only how the run is judged: the flight, the controller and every other verdict are unchanged. Not part of the pre-registered requirements when changed.",
        min: 1.0,
        max: 6.0,
        step: 0.5,
        default: 3.0,
        group: "Requirements",
        advanced: false,
        influences: &["R1_vertical_speed"],
    },
    // M18 vehicle design: factors on the scenario's own vehicle (case::vehicle_scale_fields), so
    // they mean the same change on every vehicle. The controller is told the changed vehicle, as it
    // is told each preset; its gains stay those of the template.
    Param {
        id: "vehicle_dry_mass_scale",
        label: "Dry mass",
        unit: "×",
        description: "Factor on the stage's dry (empty) mass and its inertia, same geometry. Heavier needs more thrust and more propellant to brake; the simulator refuses a stage whose full-load thrust-to-weight falls outside 1.2 to 6. Not part of the pre-registered case when changed.",
        min: 0.6,
        max: 1.6,
        step: 0.05,
        default: 1.0,
        group: "Vehicle design",
        advanced: false,
        influences: &["R6_propellant_margin", "R1_vertical_speed", "S3_axial_load"],
    },
    Param {
        id: "vehicle_propellant_scale",
        label: "Propellant load",
        unit: "×",
        description: "Factor on the propellant loaded for the landing and its inertia. Less propellant leaves less margin for the braking burn; more adds mass that has to be braked. Not part of the pre-registered case when changed.",
        min: 0.3,
        max: 2.0,
        step: 0.05,
        default: 1.0,
        group: "Vehicle design",
        advanced: false,
        influences: &["R6_propellant_margin", "R1_vertical_speed"],
    },
    Param {
        id: "vehicle_thrust_scale",
        label: "Engine thrust",
        unit: "×",
        description: "Factor on the engine's maximum thrust (the throttle floor stays the same fraction, so the lowest thrust scales too). Less thrust brakes later and harder; more makes the lowest throttle stronger and hovering harder. Not part of the pre-registered case when changed.",
        min: 0.5,
        max: 1.6,
        step: 0.05,
        default: 1.0,
        group: "Vehicle design",
        advanced: false,
        influences: &[
            "R1_vertical_speed",
            "R6_propellant_margin",
            "S5_no_powered_ascent",
        ],
    },
    Param {
        id: "vehicle_isp_scale",
        label: "Engine efficiency (Isp)",
        unit: "×",
        description: "Factor on the specific impulse: the same thrust for less propellant flow. The simulator accepts 150 to 450 s. Not part of the pre-registered case when changed.",
        min: 0.7,
        max: 1.3,
        step: 0.05,
        default: 1.0,
        group: "Vehicle design",
        advanced: false,
        influences: &["R6_propellant_margin"],
    },
];

pub fn parameters() -> Vec<ParameterSpec> {
    PARAMS
        .iter()
        .map(|p| ParameterSpec {
            id: p.id.into(),
            label: p.label.into(),
            description: p.description.into(),
            unit: p.unit.into(),
            group: p.group.into(),
            advanced: p.advanced,
            min: p.min,
            max: p.max,
            step: p.step,
            default: p.default,
            integer: false,
            influences: strings(p.influences),
        })
        .collect()
}

pub fn parameter_default(id: &str) -> Option<f64> {
    PARAMS.iter().find(|p| p.id == id).map(|p| p.default)
}

struct FaultRow {
    kind: &'static str,
    label: &'static str,
    description: &'static str,
    target: &'static str,
    magnitude: Option<(f64, f64, &'static str)>,
    window: Option<(f64, f64)>,
    default_magnitude: f64,
    start: f64,
    end: f64,
}

#[rustfmt::skip]
const FAULTS: [FaultRow; 10] = [
    FaultRow { kind: "thrust_loss", label: "Thrust loss", description: "The engine delivers less thrust than commanded: real thrust is multiplied by 1 minus the magnitude.", target: "actuator", magnitude: Some((0.05, 0.30, "fraction")), window: None, default_magnitude: 0.15, start: 5.26, end: 40.0 },
    FaultRow { kind: "ignition_delay", label: "Ignition delay", description: "The engine lights later than commanded. The window must be open when the controller commands ignition (about 4.2 s).", target: "actuator", magnitude: Some((0.1, 1.0, "s")), window: None, default_magnitude: 0.5, start: 3.0, end: 8.0 },
    FaultRow { kind: "gimbal_stuck", label: "Stuck gimbal", description: "The thrust-vector nozzle freezes at the deflection it had when the window starts (zero before ignition). There is no other attitude actuator.", target: "actuator", magnitude: None, window: Some((0.5, 3.0)), default_magnitude: 0.0, start: 10.0, end: 12.0 },
    FaultRow { kind: "altimeter_bias", label: "Altimeter bias", description: "The radar altimeter reads too high by the magnitude.", target: "sensor", magnitude: Some((5.0, 50.0, "m")), window: None, default_magnitude: 20.0, start: 10.0, end: 40.0 },
    FaultRow { kind: "altimeter_dropout", label: "Altimeter dropout", description: "The radar altimeter delivers no measurement during the window.", target: "sensor", magnitude: None, window: Some((2.0, 10.0)), default_magnitude: 0.0, start: 18.0, end: 24.0 },
    FaultRow { kind: "gnss_dropout", label: "GNSS dropout", description: "The GNSS delivers no position or velocity during the window.", target: "sensor", magnitude: None, window: Some((2.0, 10.0)), default_magnitude: 0.0, start: 8.0, end: 14.0 },
    FaultRow { kind: "gnss_bias", label: "GNSS bias", description: "The GNSS position is shifted by the magnitude along x and z.", target: "sensor", magnitude: Some((5.0, 30.0, "m")), window: None, default_magnitude: 15.0, start: 8.0, end: 40.0 },
    FaultRow { kind: "imu_accel_bias", label: "IMU acceleration bias", description: "The IMU adds the magnitude to the specific force along the body axis x_B.", target: "sensor", magnitude: Some((0.05, 0.5, "m/s²")), window: None, default_magnitude: 0.25, start: 5.0, end: 40.0 },
    FaultRow { kind: "altimeter_bias_low", label: "Altimeter bias, low reading", description: "The radar altimeter reads too low by the magnitude (M9.1).", target: "sensor", magnitude: Some((5.0, 50.0, "m")), window: None, default_magnitude: 27.5, start: 10.0, end: 40.0 },
    FaultRow { kind: "gnss_bias_low", label: "GNSS bias, low reading", description: "The GNSS position is shifted down by the magnitude along x and z (M9.1).", target: "sensor", magnitude: Some((5.0, 30.0, "m")), window: None, default_magnitude: 17.5, start: 8.0, end: 40.0 },
];

pub fn faults() -> Vec<FaultSpec> {
    FAULTS
        .iter()
        .map(|f| FaultSpec {
            kind: f.kind.into(),
            label: f.label.into(),
            description: f.description.into(),
            target: f.target.into(),
            magnitude: f.magnitude.map(|(min, max, unit)| MagnitudeSpec {
                min,
                max,
                unit: unit.into(),
                default: f.default_magnitude,
            }),
            window: f.window.map(|(min_length, max_length)| WindowSpec {
                min_length,
                max_length,
            }),
            default_start: f.start,
            default_end: f.end,
            controllers: None,
        })
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
    let r = "requirement";
    let s = "invariant";
    vec![
        requirement(
            "R1_vertical_speed",
            "Vertical speed at contact",
            r,
            "The vertical speed of the nozzle plane at contact is at most 3 m/s.",
        ),
        requirement(
            "R2_horizontal_speed",
            "Horizontal speed at contact",
            r,
            "The horizontal speed at contact is at most 1 m/s.",
        ),
        requirement(
            "R3_tilt",
            "Tilt at contact",
            r,
            "The tilt at contact is at most 5 degrees (cosine at least 0.9962).",
        ),
        requirement(
            "R4_angular_rate",
            "Angular rate at contact",
            r,
            "The angular rate at contact is at most 0.1 rad/s.",
        ),
        requirement(
            "R5_position",
            "Distance from pad centre",
            r,
            "The nozzle plane touches down within 10 m of the pad centre (the Landing-zone radius parameter can change the limit).",
        ),
        requirement(
            "R6_propellant_margin",
            "Propellant margin",
            r,
            "At least 1 % of the initial propellant is left at contact.",
        ),
        requirement(
            "S1_tilt_envelope",
            "Tilt envelope while thrusting",
            s,
            "While the engine is on the tilt stays within 30 degrees at every step.",
        ),
        requirement(
            "S2_keep_out",
            "Keep-out radius at contact",
            s,
            "The stage touches down within 50 m of the pad centre, the keep-out radius.",
        ),
        requirement(
            "S3_axial_load",
            "Axial load",
            s,
            "The axial load stays at or below 3 g0 at every step.",
        ),
        requirement(
            "S4_no_relight",
            "No relight",
            s,
            "The engine is lit at most once.",
        ),
        requirement(
            "S5_no_powered_ascent",
            "Climb under power",
            s,
            "The centre of mass never rises more than 5 m above its running minimum since ignition.",
        ),
    ]
}

pub fn catalog() -> DomainCatalog {
    // Every parameter applies to both templates: they share the initial state, sensors and
    // requirements, and differ only in the policies they hold.
    let gains: Vec<&str> = PARAMS.iter().map(|p| p.id).collect();
    let scenario = |id: &str,
                    label: &str,
                    description: &str,
                    controllers: &[&str],
                    parameters: Vec<String>,
                    default: &str| {
        let vehicle = match id {
            HEAVY => "heavy-return-stage",
            LIGHT => "light-demonstrator",
            _ => "landing-stage",
        };
        ScenarioSpec {
            id: id.into(),
            label: label.into(),
            description: description.into(),
            vehicle: vehicle.into(),
            controllers: strings(controllers),
            parameters,
            default_controller: default.into(),
        }
    };
    let channels = crate::record::channel_specs();
    DomainCatalog {
        schema: CATALOG_SCHEMA.into(),
        domain: DOMAIN.into(),
        time: TimeSpec {
            unit: "s".into(),
            label: "Time since the start of the simulation".into(),
        },
        vehicles: vec![
            with_facts(
                item(
                    "landing-stage",
                    "22 t landing stage",
                    "A rocket stage of 22 t dry mass and 8 t of propellant that falls from about 3 km at 200 m/s and brakes with one gimballed engine to a 1.5 m/s descent over the pad. The initial state is dispersed by the seed.",
                ),
                M9,
            ),
            with_facts(
                item(
                    "heavy-return-stage",
                    "41 t heavy return stage (exploratory)",
                    "A heavier stage, 30 t dry and 11 t of propellant, with a 760 kN engine (thrust over full-load weight 1.89, against 2.87 for the 22 t stage), Isp 300 s and a throttle floor of 55 %. Less braking margin and less throttle range. Illustrative values of the order of a reusable first stage near landing, not a real vehicle.",
                ),
                HEAVY,
            ),
            with_facts(
                item(
                    "light-demonstrator",
                    "7.7 t light demonstrator stage (exploratory)",
                    "A small stage, 5.5 t dry and 2.2 t of propellant, with a 230 kN engine (thrust over full-load weight 3.05), Isp 265 s, a 30 % throttle floor and a faster throttle. Illustrative values of the order of a suborbital test vehicle, not a real vehicle.",
                ),
                LIGHT,
            ),
        ],
        scenarios: vec![
            scenario(
                M9,
                "Powered landing (M9)",
                "The frozen M9 case: the baseline and robust controllers on the pre-registered template (case schema v1).",
                &["baseline", "robust"],
                strings(&gains),
                "robust",
            ),
            scenario(
                M91,
                "Powered landing with ascent abort (M9.1)",
                "The M9.1 case: the guarded controllers, which add the ascent-abort rule with its two gains at their defaults (case schema v1).",
                &["guarded", "baseline_guarded"],
                strings(&gains),
                "guarded",
            ),
            scenario(
                HEAVY,
                "Heavy return stage (exploratory)",
                "The M9 mission, initial state, sensors, requirements and gains with the 41 t heavy return stage (case schema v2, exploratory). The controller is told the new vehicle; its gains stay those tuned for the 22 t stage.",
                &["baseline", "robust", "guarded", "baseline_guarded"],
                strings(&gains),
                "robust",
            ),
            scenario(
                LIGHT,
                "Light demonstrator stage (exploratory)",
                "The M9 mission, initial state, sensors, requirements and gains with the 7.7 t light demonstrator stage (case schema v2, exploratory). The controller is told the new vehicle; its gains stay those tuned for the 22 t stage.",
                &["baseline", "robust", "guarded", "baseline_guarded"],
                strings(&gains),
                "robust",
            ),
        ],
        controllers: controllers(),
        parameters: parameters(),
        faults: faults(),
        max_faults: 2,
        channels,
        requirements: requirements(),
        demos: crate::demos::demos(),
    }
}

/// The vehicle's measured attributes, read from the template it is simulated with.
fn with_facts(mut v: Item, scenario: &str) -> Item {
    let case = crate::case::template(scenario).expect("bundled template");
    let veh = &case["vehicle"];
    let num = |k: &str| veh[k].as_f64().expect("vehicle number");
    let dry = num("dry_mass_kg");
    let prop = num("propellant_mass_kg");
    let thrust = num("max_thrust_n");
    let fact = |label: &str, value: f64, unit: &str| Fact {
        label: label.into(),
        value,
        unit: unit.into(),
    };
    v.facts = vec![
        fact("Dry mass", dry / 1000.0, "t"),
        fact("Propellant", prop / 1000.0, "t"),
        fact("Engine thrust", thrust / 1000.0, "kN"),
        fact("Specific impulse", num("isp_s"), "s"),
        fact(
            "Thrust over full-load weight",
            thrust / ((dry + prop) * 9.80665),
            "",
        ),
        fact("Throttle floor", num("throttle_min") * 100.0, "%"),
    ];
    v
}

/// A request in the canonical shape, for demonstrations and tests.
pub fn request(
    scenario: &str,
    controller: &str,
    seed: u64,
    faults: Vec<FaultRequest>,
) -> RunRequest {
    RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: DOMAIN.into(),
        scenario: scenario.into(),
        controller: controller.into(),
        seed,
        faults,
        parameters: BTreeMap::new(),
    }
}
