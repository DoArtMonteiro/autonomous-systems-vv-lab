//! Manifest, catalog and demos of the ground-vehicle domain. Channel and requirement tables are
//! shared with the record mapping so the catalog never lists something a run does not produce.

use std::collections::BTreeMap;

use vv_platform::contract::*;

use crate::inputs::{MISSIONS, Mission};

pub const DOMAIN_ID: &str = "ground-vehicle";
pub const TIMEBASE: &str = "tick";

pub const GPS_DROPOUT: &str = "gps_dropout";
pub const ACTUATOR_FAULTS: [&str; 3] = ["continued_movement", "delayed_movement", "lost_movement"];

pub const PARAM_STALL_WINDOW: &str = "stall_window_ticks";
pub const PARAM_MIN_PROGRESS: &str = "min_progress_mm";
pub const PARAM_CLEAR_BUILTIN: &str = "clear_builtin_faults";
pub const PARAM_GPS_NOISE: &str = "gps_noise_mm";
pub const PARAM_ARRIVAL_RADIUS: &str = "arrival_radius_mm";
pub const DEFAULT_STALL_WINDOW: f64 = 8.0;
pub const DEFAULT_MIN_PROGRESS: f64 = 1.0;
pub const MAX_STEPS: f64 = 200.0;

pub const CONTROLLERS: [(&str, &str, &str); 2] = [
    (
        "dominant_axis",
        "Dominant axis",
        "Canonical M4 controller. Moves along the axis with the larger remaining error, holds when the last \
         fix is not confident, enters safety fallback after a run of low-confidence ticks and recovers after \
         a run of reliable ones (thresholds come from the scenario).",
    ),
    (
        "x_first",
        "X first",
        "Known weaker M4 policy kept for comparison. Settles the x axis before the y axis, ignoring which \
         error is larger. Same watchdog and fallback behaviour as dominant_axis.",
    ),
];

/// id, label, unit, group, kind. The ids are the channel ids of every record.
pub const CHANNELS: [(&str, &str, &str, &str, &str); 13] = [
    ("truth_x_mm", "True x position", "mm", "Position", "truth"),
    ("truth_y_mm", "True y position", "mm", "Position", "truth"),
    ("gps_x_mm", "GPS x sample", "mm", "Position", "observation"),
    ("gps_y_mm", "GPS y sample", "mm", "Position", "observation"),
    (
        "held_x_mm",
        "Last accepted fix, x",
        "mm",
        "Position",
        "estimate",
    ),
    (
        "held_y_mm",
        "Last accepted fix, y",
        "mm",
        "Position",
        "estimate",
    ),
    (
        "confidence_permille",
        "Confidence in the last fix",
        "permille",
        "Perception",
        "estimate",
    ),
    (
        "fix_age_ticks",
        "Age of the last fix",
        "tick",
        "Perception",
        "observation",
    ),
    (
        "gps_dropped",
        "GPS dropout (1 = no sample)",
        "flag",
        "Perception",
        "observation",
    ),
    (
        "command_mm",
        "Commanded movement",
        "mm",
        "Control",
        "command",
    ),
    ("moved_mm", "Actual movement", "mm", "Control", "truth"),
    (
        "fallback",
        "Safety fallback active (1 = yes)",
        "flag",
        "Control",
        "metric",
    ),
    (
        "goal_distance_mm",
        "Manhattan distance to the goal",
        "mm",
        "Mission",
        "metric",
    ),
];

/// id, label, category, description. Safety invariants first, then the temporal contracts of the
/// shared contract set, then the mission result.
pub const REQUIREMENTS: [(&str, &str, &str, &str); 12] = [
    (
        "restricted_zone",
        "Truth stays outside the restricted zone",
        "invariant",
        "The true position never enters the restricted polygon.",
    ),
    (
        "world_bounds",
        "Truth stays inside the world bounds",
        "invariant",
        "The true position never leaves the world rectangle.",
    ),
    (
        "safe_fallback",
        "Safe fallback on low confidence",
        "invariant",
        "After the configured low-confidence interval the vehicle is in fallback, and it does not move on \
         truth while confidence is low or fallback is active.",
    ),
    (
        "valid_state_transitions",
        "Valid state transitions",
        "invariant",
        "Mission and safety states change only along the declared transitions.",
    ),
    (
        "restricted_zone_clear",
        "Restricted zone stays clear (contract)",
        "requirement",
        "Temporal contract: the predicate restricted_zone_clear holds at every tick.",
    ),
    (
        "fallback_response",
        "Fallback follows unreliable localization",
        "requirement",
        "Temporal contract: within 2 ticks of 2 consecutive ticks of localization_unreliable, safety_fallback holds.",
    ),
    (
        "stop_response",
        "Vehicle stops after a stop command",
        "requirement",
        "Temporal contract: within 2 ticks of stop_commanded, vehicle_stationary holds.",
    ),
    (
        "command_resolution",
        "Every movement command is resolved",
        "requirement",
        "Temporal contract: within 2 ticks of each movement_commanded, the same command is resolved by the actuator.",
    ),
    (
        "command_applied",
        "Every movement command is applied",
        "requirement",
        "Temporal contract: within 2 ticks of each movement_commanded, the same command is applied.",
    ),
    (
        "no_motion_in_fallback",
        "No motion in fallback",
        "requirement",
        "Temporal contract: movement_while_fallback never holds.",
    ),
    (
        "mission_lifecycle",
        "Mission starts and completes",
        "requirement",
        "Temporal contract: the mission goes from pending to running to completed, in that order.",
    ),
    (
        "mission_completion",
        "Mission completion",
        "requirement",
        "The vehicle reaches every waypoint inside the horizon without a stall.",
    ),
];

pub fn requirement(
    id: &str,
) -> Option<&'static (&'static str, &'static str, &'static str, &'static str)> {
    REQUIREMENTS.iter().find(|r| r.0 == id)
}

pub fn manifest() -> DomainManifest {
    serde_json::from_str(include_str!("../domain.json")).expect("domain.json is a valid manifest")
}

fn item(id: &str, label: &str, description: &str) -> Item {
    Item {
        id: id.into(),
        label: label.into(),
        description: description.into(),
        facts: Vec::new(),
        evidence: String::new(),
    }
}

fn scenario(mission: &Mission) -> ScenarioSpec {
    let mut parameters = vec![PARAM_STALL_WINDOW.to_owned(), PARAM_MIN_PROGRESS.to_owned()];
    if mission.has_builtin_faults() {
        parameters.push(PARAM_CLEAR_BUILTIN.to_owned());
    }
    if mission.has_sensor_parameters() {
        parameters.push(PARAM_GPS_NOISE.to_owned());
        parameters.push(PARAM_ARRIVAL_RADIUS.to_owned());
    }
    ScenarioSpec {
        id: mission.id.into(),
        label: mission.label.into(),
        description: mission.description.into(),
        vehicle: "ground-2d".into(),
        controllers: CONTROLLERS.iter().map(|c| c.0.to_owned()).collect(),
        parameters,
        default_controller: "dominant_axis".into(),
    }
}

#[allow(clippy::too_many_arguments)]
fn parameter(
    id: &str,
    label: &str,
    description: &str,
    unit: &str,
    group: &str,
    max: f64,
    default: f64,
    integer: bool,
) -> ParameterSpec {
    ParameterSpec {
        id: id.into(),
        label: label.into(),
        description: description.into(),
        unit: unit.into(),
        group: group.into(),
        advanced: true,
        min: if [PARAM_CLEAR_BUILTIN, PARAM_GPS_NOISE, PARAM_ARRIVAL_RADIUS].contains(&id) {
            0.0
        } else {
            1.0
        },
        max,
        step: 1.0,
        default,
        integer,
        influences: Vec::new(),
    }
}

fn parameters() -> Vec<ParameterSpec> {
    vec![
        parameter(
            PARAM_STALL_WINDOW,
            "Stall window",
            "Ticks without meaningful progress after which the mission is judged stalled (mission policy of run-m4).",
            "tick",
            "Mission policy",
            MAX_STEPS,
            DEFAULT_STALL_WINDOW,
            true,
        ),
        parameter(
            PARAM_MIN_PROGRESS,
            "Minimum progress",
            "Reduction of the distance to the next waypoint that counts as meaningful progress (mission policy of run-m4).",
            "mm",
            "Mission policy",
            10_000.0,
            DEFAULT_MIN_PROGRESS,
            true,
        ),
        parameter(
            PARAM_CLEAR_BUILTIN,
            "Remove built-in faults",
            "1 removes the mission's built-in GPS dropout and delayed command before the faults of the request \
             are applied; 0 keeps the built-in fault of every target the request does not override.",
            "flag",
            "Faults",
            1.0,
            0.0,
            true,
        ),
        parameter(
            PARAM_GPS_NOISE,
            "GPS noise",
            "Largest error of each GPS sample per axis, drawn uniformly by the seed. The corridor mission is \
             registered with ideal sensors (0 mm).",
            "mm",
            "Sensors",
            20.0,
            0.0,
            true,
        ),
        parameter(
            PARAM_ARRIVAL_RADIUS,
            "Arrival radius",
            "Distance from the waypoint at which the mission counts it as reached. The corridor mission is \
             registered with 0 mm, so the vehicle must hit the waypoint exactly.",
            "mm",
            "Mission policy",
            1000.0,
            0.0,
            true,
        ),
    ]
}

fn fault(
    kind: &str,
    label: &str,
    description: &str,
    target: &str,
    magnitude: Option<MagnitudeSpec>,
    start: f64,
    end: f64,
) -> FaultSpec {
    FaultSpec {
        kind: kind.into(),
        label: label.into(),
        description: description.into(),
        target: target.into(),
        magnitude,
        window: Some(WindowSpec {
            min_length: 0.0,
            max_length: MAX_STEPS - 1.0,
        }),
        default_start: start,
        default_end: end,
        controllers: None,
    }
}

fn faults() -> Vec<FaultSpec> {
    vec![
        fault(
            GPS_DROPOUT,
            "GPS dropout",
            "The GPS delivers no sample during the window (first and last tick inclusive). The controller keeps \
             its last fix, whose age grows and confidence falls.",
            "sensor",
            None,
            4.0,
            8.0,
        ),
        fault(
            "continued_movement",
            "Continued movement",
            "A stop command issued inside the window is ignored and the previous movement is repeated. It has no \
             effect before the vehicle has moved or while the controller is not commanding a stop.",
            "actuator",
            None,
            4.0,
            8.0,
        ),
        fault(
            "delayed_movement",
            "Delayed movement",
            "A movement command issued inside the window is held back and executed after the delay, replacing \
             whatever is commanded at that later tick, including a stop.",
            "actuator",
            Some(MagnitudeSpec {
                min: 1.0,
                max: MAX_STEPS,
                unit: "tick".into(),
                default: 3.0,
            }),
            4.0,
            4.0,
        ),
        fault(
            "lost_movement",
            "Lost movement",
            "A movement command issued inside the window is dropped by the actuator and the vehicle holds.",
            "actuator",
            None,
            4.0,
            6.0,
        ),
    ]
}

fn channels() -> Vec<ChannelSpec> {
    CHANNELS
        .iter()
        .map(|c| ChannelSpec {
            id: c.0.into(),
            label: c.1.into(),
            unit: c.2.into(),
            group: c.3.into(),
            kind: c.4.into(),
        })
        .collect()
}

fn requirements() -> Vec<RequirementSpec> {
    REQUIREMENTS
        .iter()
        .map(|r| RequirementSpec {
            id: r.0.into(),
            label: r.1.into(),
            category: r.2.into(),
            description: r.3.into(),
        })
        .collect()
}

pub fn request(
    scenario: &str,
    controller: &str,
    seed: u64,
    faults: Vec<FaultRequest>,
) -> RunRequest {
    RunRequest {
        schema: REQUEST_SCHEMA.into(),
        domain: DOMAIN_ID.into(),
        scenario: scenario.into(),
        controller: controller.into(),
        seed,
        faults,
        parameters: BTreeMap::new(),
    }
}

fn demos() -> Vec<Demo> {
    vec![
        Demo {
            id: "nominal-drive".into(),
            title: "Nominal drive".into(),
            narrative: "The vehicle drives 1500 mm east to its waypoint and stops, with no faults. Every contract and \
              invariant holds. This is the reference to compare any faulted run against."
                .into(),
            requests: vec![request("nominal_stop", "dominant_axis", 42, vec![])],
            look_at: vec!["requirements".into(), "scene".into(), "goal_distance_mm".into()],
            expectation: "Mission completed (success) at tick 7, safety safe, all 7 temporal contracts and all 4 \
              safety invariants pass."
                .into(),
        },
        Demo {
            id: "axis-policy-comparison".into(),
            title: "Same mission, two controllers".into(),
            narrative: "The waypoint is 250 mm east and 2000 mm north of the start, and each move is 500 mm. \
              dominant_axis drives north and arrives. x_first settles x before y: every 500 mm step jumps \
              over the 250 mm x error, so it shuttles between two x positions and never turns north. The \
              mission stalls although no safety invariant is violated: a stalled mission and an unsafe run \
              are different results."
                .into(),
            requests: vec![
                request("x_first_overshoot", "dominant_axis", 42, vec![]),
                request("x_first_overshoot", "x_first", 42, vec![]),
            ],
            look_at: vec!["truth_x_mm".into(), "goal_distance_mm".into(), "scene".into()],
            expectation: "dominant_axis: completed at tick 5, safe, all contracts pass. x_first: stalled (detected at \
              tick 8), it moves 500 mm every tick but ends 2250 mm from the goal, safety stays safe, \
              mission_lifecycle is not evaluated and mission_completion fails."
                .into(),
        },
        Demo {
            id: "delayed-command-after-fallback".into(),
            title: "A delayed command moves the vehicle in fallback".into(),
            narrative: "First request: the mission as built, with a GPS dropout from tick 4 and a movement command \
              issued at tick 4 that the actuator holds back for 3 ticks. The vehicle stops at tick 5 and \
              enters fallback at tick 6, then the old command runs at tick 7 and moves it 250 mm while it \
              should be holding. Second request: the same mission with both built-in faults removed. It \
              is safe but cannot reach the waypoint in 14 ticks, so the unsafe motion comes from the faults, \
              not from the mission."
                .into(),
            requests: vec![
                request("delayed_after_fallback", "dominant_axis", 42, vec![]),
                RunRequest {
                    parameters: BTreeMap::from([(PARAM_CLEAR_BUILTIN.to_owned(), 1.0)]),
                    ..request("delayed_after_fallback", "dominant_axis", 42, vec![])
                },
            ],
            look_at: vec!["fallback".into(), "command_mm".into(), "moved_mm".into(), "events".into()],
            expectation: "With the built-in faults: mission incomplete, safety unsafe. The invariant safe_fallback \
              fails at tick 7, the contracts command_resolution and command_applied fail at tick 6 and \
              no_motion_in_fallback fails at tick 7; fallback_response and stop_response pass. Without \
              them: mission incomplete (1500 mm from the goal), safety safe, no fallback, only \
              mission_completion fails and mission_lifecycle is not evaluated."
                .into(),
        },
        Demo {
            id: "corridor-gps-noise".into(),
            title: "One millimetre of GPS noise and a restricted zone".into(),
            narrative: "The vehicle drives east along a corridor to a waypoint 250 mm above the corner of a restricted \
              zone, in steps of 250 mm. With exact GPS it stops on the waypoint. With 1 mm of noise it \
              never reads the waypoint exactly; the arrival radius of 0 mm makes it keep correcting by \
              whole steps, it oscillates around the waypoint and at tick 21 steps south onto the edge of \
              the zone. An arrival radius of one step, 250 mm, lets it stop. Same seed in all three runs. \
              The scenario variant is a candidate fix studied in the M13 investigation, not a validated \
              design change."
                .into(),
            requests: vec![
                request("zone_corridor", "dominant_axis", 5002, vec![]),
                RunRequest {
                    parameters: BTreeMap::from([(PARAM_GPS_NOISE.to_owned(), 1.0)]),
                    ..request("zone_corridor", "dominant_axis", 5002, vec![])
                },
                RunRequest {
                    parameters: BTreeMap::from([
                        (PARAM_GPS_NOISE.to_owned(), 1.0),
                        (PARAM_ARRIVAL_RADIUS.to_owned(), 250.0),
                    ]),
                    ..request("zone_corridor", "dominant_axis", 5002, vec![])
                },
            ],
            look_at: vec!["scene".into(), "truth_y_mm".into(), "requirements".into(), "events".into()],
            expectation: "Exact GPS: mission completed at tick 17, safe. 1 mm of noise: mission incomplete, unsafe, \
              the invariant restricted_zone fails at tick 21. 1 mm of noise with a 250 mm arrival \
              radius: completed at tick 16, safe."
                .into(),
        },
    ]
}

pub fn catalog() -> DomainCatalog {
    DomainCatalog {
        schema: CATALOG_SCHEMA.into(),
        domain: DOMAIN_ID.into(),
        time: TimeSpec {
            unit: "tick".into(),
            label: "Logical tick (100 ms of simulated time)".into(),
        },
        vehicles: vec![
            item(
                "ground-2d",
                "Ground vehicle, 2D kinematic",
                "A generic unarmed ground vehicle that moves a fixed step along one axis per movement command. \
                 Integer millimetre positions, no dynamics.",
            )
            .with_evidence("reference"),
        ],
        scenarios: MISSIONS.iter().map(scenario).collect(),
        controllers: CONTROLLERS.iter().map(|c| item(c.0, c.1, c.2)).collect(),
        parameters: parameters(),
        faults: faults(),
        max_faults: 2,
        channels: channels(),
        requirements: requirements(),
        demos: demos(),
    }
}
