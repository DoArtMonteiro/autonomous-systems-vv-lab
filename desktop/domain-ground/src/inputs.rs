//! Mission inputs of the three ground missions, embedded in the host, and the fault overrides that
//! turn them into the inputs of one run.
//!
//! The overrides follow `GroundVehicleAdapter._inputs` in `scripts/sim_adapter.py`: the embedded
//! scenario and actuator files are parsed, modified in memory and written in canonical form (sorted
//! keys, no whitespace). The contract file is written byte for byte. A request without faults on a
//! mission without built-in faults therefore writes the same bytes as the Python adapter.

use serde_json::{Value, json};

pub const CONTRACTS: &str = include_str!("../../../scenarios/m3/contracts-nominal.json");

/// Actuator seed and probability used by the Python adapter for a mission without an actuator file.
const DEFAULT_ACTUATOR: &str = r#"{"schema_version":1,"seed":42,"faults":[]}"#;
/// Fault id the Python adapter gives to the actuator fault it injects.
const OVERRIDE_FAULT_ID: &str = "mission_control_override";
/// Injected actuator faults always apply: no random draw decides whether they fire.
pub const PROBABILITY_PERMILLE: u64 = 1000;

pub struct Mission {
    pub id: &'static str,
    pub label: &'static str,
    pub description: &'static str,
    scenario: &'static str,
    actuator: Option<&'static str>,
}

pub const MISSIONS: [Mission; 3] = [
    Mission {
        id: "nominal_stop",
        label: "Nominal stop",
        description: "Straight drive of 1500 mm east at 250 mm per tick in a 16-tick horizon, with no faults. \
                      The clean base case: the vehicle reaches the waypoint and stops.",
        scenario: include_str!("../../../scenarios/m3/nominal-stop.json"),
        actuator: None,
    },
    Mission {
        id: "x_first_overshoot",
        label: "Axis policy overshoot",
        description: "2D drive to a waypoint 250 mm east and 2000 mm north of the start at 500 mm per tick in a \
                      12-tick horizon, with no faults. The two controllers handle the small x error differently.",
        scenario: include_str!("../../../scenarios/m4/x-first-overshoot.json"),
        actuator: None,
    },
    Mission {
        id: "delayed_after_fallback",
        label: "Delayed command after fallback",
        description: "Drive of 5000 mm east in a 14-tick horizon that cannot finish in time. The mission has a \
                      built-in GPS dropout at ticks 4 to 10 and a built-in movement command delayed by 3 ticks, \
                      with fallback after 2 low-confidence ticks. Faults added to a request replace the built-in \
                      fault of the same target; the parameter clear_builtin_faults removes both.",
        scenario: include_str!("../../../scenarios/m3/delayed-after-fallback.json"),
        actuator: Some(include_str!("../../../scenarios/m3/actuator-delayed.json")),
    },
];

pub fn mission(id: &str) -> Option<&'static Mission> {
    MISSIONS.iter().find(|m| m.id == id)
}

impl Mission {
    pub fn steps(&self) -> u32 {
        serde_json::from_str::<Value>(self.scenario)
            .ok()
            .and_then(|v| v["steps"].as_u64())
            .and_then(|s| u32::try_from(s).ok())
            .expect("embedded scenario has steps")
    }

    pub fn has_builtin_faults(&self) -> bool {
        self.id == "delayed_after_fallback"
    }
}

#[derive(Debug, Default, PartialEq)]
pub struct ActuatorOverride {
    pub kind: String,
    pub start: u32,
    pub end: u32,
    pub delay_ticks: Option<u32>,
}

#[derive(Debug, Default, PartialEq)]
pub struct Overrides {
    pub gps: Option<(u32, u32)>,
    pub actuator: Option<ActuatorOverride>,
    /// Python "none": remove the built-in fault of a target that the request does not override.
    pub clear_builtin: bool,
}

pub struct Inputs {
    pub scenario: Vec<u8>,
    pub actuator: Vec<u8>,
    pub contracts: Vec<u8>,
}

fn canonical(value: &Value) -> Result<Vec<u8>, String> {
    // Sorted keys and no whitespace, like json.dumps(sort_keys=True, separators=(",", ":")).
    let text = serde_json::to_string(value).map_err(|e| e.to_string())?;
    if !text.is_ascii() {
        return Err("embedded input is not ASCII".into());
    }
    Ok(text.into_bytes())
}

pub fn build(mission: &Mission, overrides: &Overrides) -> Result<Inputs, String> {
    let mut scenario: Value = serde_json::from_str(mission.scenario).map_err(|e| e.to_string())?;
    let mut actuator: Value = serde_json::from_str(mission.actuator.unwrap_or(DEFAULT_ACTUATOR))
        .map_err(|e| e.to_string())?;
    let windows = scenario
        .pointer_mut("/sensors/gps/dropout_windows")
        .ok_or("embedded scenario has no GPS dropout windows")?;
    match overrides.gps {
        Some((start, end)) => *windows = json!([{"start_tick": start, "end_tick": end}]),
        None if overrides.clear_builtin => *windows = json!([]),
        None => {}
    }
    match &overrides.actuator {
        Some(fault) => {
            let mut spec = json!({
                "kind": fault.kind,
                "id": OVERRIDE_FAULT_ID,
                "windows": [{"start_tick": fault.start, "end_tick": fault.end}],
                "probability_permille": PROBABILITY_PERMILLE,
            });
            if let Some(delay) = fault.delay_ticks {
                spec["delay_ticks"] = json!(delay);
            }
            actuator["faults"] = json!([spec]);
        }
        None if overrides.clear_builtin => actuator["faults"] = json!([]),
        None => {}
    }
    Ok(Inputs {
        scenario: canonical(&scenario)?,
        actuator: canonical(&actuator)?,
        contracts: CONTRACTS.as_bytes().to_vec(),
    })
}
