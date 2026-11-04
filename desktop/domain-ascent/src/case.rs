//! The ascent case of a request: the bundled vehicle template of the scenario with the request
//! parameters applied. A parameter is written only when it differs from its default, so a default
//! request flies the template exactly; the bytes are the compact serialisation of the case.

use vv_ascent::model::{Case, parse_case, validate};
use vv_platform::contract::RunRequest;

use crate::catalog::{Target, param};

pub fn template(scenario: &str) -> Result<Case, String> {
    let text = vv_ascent::CASES
        .iter()
        .find(|(id, _)| *id == scenario)
        .map(|(_, t)| *t)
        .ok_or_else(|| format!("unknown scenario {scenario}"))?;
    parse_case(text.as_bytes())
}

pub fn case_for(request: &RunRequest) -> Result<Case, String> {
    let mut case = template(&request.scenario)?;
    for (id, value) in &request.parameters {
        let p = param(id).ok_or_else(|| format!("unknown parameter {id}"))?;
        if p.scenario.is_some_and(|s| s != request.scenario) {
            return Err(format!(
                "parameter {id} belongs to scenario {}",
                p.scenario.unwrap_or("")
            ));
        }
        if *value == p.default {
            continue;
        }
        let m = &mut case.mission;
        match p.target {
            Target::TargetAltitudeKm => m.target_altitude_km = *value,
            Target::KickTimeS => m.kick_time_s = *value,
            Target::KickAngleDeg => m.kick_angle_deg = *value,
            Target::GravityTurnStartS => m.gravity_turn_start_s = *value,
            Target::PayloadKg => case.vehicle.payload_kg = *value,
            Target::Dispersions => case.dispersions.enabled = *value >= 0.5,
        }
    }
    // The simulator's own rules (whole ticks, gravity turn after the kick) surface as an invalid request.
    validate(&case)?;
    Ok(case)
}

pub fn case_bytes(request: &RunRequest) -> Result<Vec<u8>, String> {
    let case = case_for(request)?;
    serde_json::to_vec(&case).map_err(|e| e.to_string())
}
