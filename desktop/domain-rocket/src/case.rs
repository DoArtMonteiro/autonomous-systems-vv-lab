//! The landing case of a request. With every parameter at its default the bytes are those the Python
//! `LandingAdapter` writes (`case_for` and the canonical writer: sorted keys, compact separators), so
//! a desktop run and an adapter run of the same policy, seed and fault share one `case.json`. The
//! adapter takes at most one fault; a two-fault case follows the same rules and is checked against
//! a fixture (`tests/golden/m9-two-faults`).

use serde_json::{Map, Value, json};
use vv_platform::contract::RunRequest;

pub const DT_S: f64 = 0.01;
pub const DURATION_S: f64 = 40.0;

const TEMPLATE_M9: &str = include_str!("../../../crates/vv-rocket/landing/nominal.json");
const TEMPLATE_M91: &str = include_str!("../../../crates/vv-rocket/landing/m91-nominal.json");
// M17 vehicle presets: exploratory (case schema v2) templates with the M9 initial state, sensors,
// requirements and gains and another vehicle. See docs/m17-experiment-lab.md.
const TEMPLATE_HEAVY: &str = include_str!("../cases/heavy-return.json");
const TEMPLATE_LIGHT: &str = include_str!("../cases/light-lander.json");

pub const M9: &str = "m9-landing";
pub const M91: &str = "m91-landing";
pub const HEAVY: &str = "heavy-return-landing";
pub const LIGHT: &str = "light-lander-landing";

/// Case schema of an exploratory case (vv-rocket `LANDING_SCHEMA_V2`).
pub const EXPLORATORY_SCHEMA: &str = "vv-rocket-landing.v2";

/// A parameter that sets a value the pre-registered (v1) case pins: changing one makes the case
/// exploratory (schema v2), which the simulator accepts only within its bounded ranges.
pub fn pins_registered_value(id: &str) -> bool {
    matches!(
        id,
        "initial_altitude_m"
            | "initial_downrange_m"
            | "initial_crossrange_m"
            | "initial_vertical_velocity_mps"
            | "initial_horizontal_velocity_mps"
            | "altimeter_sigma_m"
            | "gnss_position_sigma_m"
            | "landing_zone_radius_m"
            | "contact_vertical_speed_limit_mps"
    )
}

pub fn template(scenario: &str) -> Result<Value, String> {
    let text = match scenario {
        M9 => TEMPLATE_M9,
        M91 => TEMPLATE_M91,
        HEAVY => TEMPLATE_HEAVY,
        LIGHT => TEMPLATE_LIGHT,
        other => return Err(format!("unknown scenario {other}")),
    };
    serde_json::from_str(text).map_err(|e| format!("template of {scenario}: {e}"))
}

/// Where a parameter lives in the case. A numeric key indexes an array.
pub fn parameter_path(id: &str) -> Option<&'static [&'static str]> {
    Some(match id {
        "ignition_fraction" => &["controller", "gains", "ignition_fraction"],
        "throttle_gain" => &["controller", "gains", "throttle_gain"],
        "cutoff_altitude_m" => &["controller", "gains", "cutoff_altitude_m"],
        "lateral_position_gain" => &["controller", "gains", "lateral_position_gain"],
        "tilt_max_tan" => &["controller", "gains", "tilt_max_tan"],
        "altimeter_residual_threshold_m" => {
            &["controller", "gains", "altimeter_residual_threshold_m"]
        }
        "initial_altitude_m" => &["initial", "position_m", "2"],
        "initial_downrange_m" => &["initial", "position_m", "0"],
        "initial_crossrange_m" => &["initial", "position_m", "1"],
        "initial_vertical_velocity_mps" => &["initial", "velocity_mps", "2"],
        "initial_horizontal_velocity_mps" => &["initial", "velocity_mps", "0"],
        "altimeter_sigma_m" => &["sensors", "altimeter_sigma_m"],
        "gnss_position_sigma_m" => &["sensors", "gnss_position_sigma_m"],
        "landing_zone_radius_m" => &["requirements", "r5_position_m"],
        "contact_vertical_speed_limit_mps" => &["requirements", "r1_vertical_speed_mps"],
        _ => return None,
    })
}

/// A time that is a multiple of the 0.01 s step, as whole steps (the Python `_seconds`).
pub fn whole_steps(value: f64, name: &str) -> Result<i64, String> {
    if !value.is_finite() || !(0.0..=DURATION_S).contains(&value) {
        return Err(format!("{name} must be in 0 to {DURATION_S} s"));
    }
    let steps = (value / DT_S).round();
    if (value / DT_S - steps).abs() > 1e-9 {
        return Err(format!("{name} must be a multiple of {DT_S} s"));
    }
    Ok(steps as i64)
}

/// Python's `format(value, "g")`: six significant digits, no trailing zeros.
pub fn fmt_g(value: f64) -> String {
    if value == 0.0 {
        return "0".into();
    }
    let sci = format!("{value:.5e}");
    let (mantissa, exp) = sci.split_once('e').expect("exponent form");
    let exp: i32 = exp.parse().expect("exponent");
    if !(-4..6).contains(&exp) {
        let mantissa = strip_zeros(mantissa);
        let sign = if exp < 0 { '-' } else { '+' };
        return format!("{mantissa}e{sign}{:02}", exp.abs());
    }
    strip_zeros(&format!("{value:.*}", (5 - exp).max(0) as usize))
}

fn strip_zeros(text: &str) -> String {
    if text.contains('.') {
        text.trim_end_matches('0').trim_end_matches('.').to_string()
    } else {
        text.to_string()
    }
}

fn number(value: f64) -> Value {
    // A request value is finite after validation, so the conversion cannot fail.
    Value::Number(serde_json::Number::from_f64(value).expect("finite number"))
}

/// The case bytes of a normalised request, or the reason the request cannot be a case.
pub fn case_bytes(request: &RunRequest) -> Result<Vec<u8>, String> {
    let mut case = template(&request.scenario)?;
    case["controller"]["policy"] = json!(request.controller);
    let mut faults = Vec::new();
    let mut parts = Vec::new();
    let mut kinds = Vec::new();
    for (index, fault) in request.faults.iter().enumerate() {
        let name = format!("faults[{index}]");
        let start = whole_steps(fault.start, &format!("{name}.start"))?;
        let end = whole_steps(fault.end, &format!("{name}.end"))?;
        if end <= start {
            return Err(format!("{name}: the window must end after it starts"));
        }
        let magnitude = fault.magnitude.unwrap_or(0.0) + 0.0;
        let (start_s, end_s) = (start as f64 / 100.0, end as f64 / 100.0);
        parts.push(format!(
            "{} {} from {} s to {} s",
            fault.kind,
            fmt_g(magnitude),
            fmt_g(start_s),
            fmt_g(end_s)
        ));
        kinds.push(fault.kind.clone());
        let mut entry = Map::new();
        entry.insert("kind".into(), json!(fault.kind));
        entry.insert("magnitude".into(), number(magnitude));
        entry.insert("start_s".into(), number(start_s));
        entry.insert("end_s".into(), number(end_s));
        faults.push(Value::Object(entry));
    }
    case["faults"] = Value::Array(faults);
    let text = if parts.is_empty() {
        "nominal".to_string()
    } else {
        parts.join(" + ")
    };
    let mut name = format!(
        "Mission Control landing: {text}, {} policy",
        request.controller
    );
    if name.len() > 80 {
        name = format!("Landing: {text}, {}", request.controller);
    }
    if name.len() > 80 {
        name = format!("Landing: {}, {}", kinds.join(" + "), request.controller);
    }
    name.truncate(80);
    case["name"] = json!(name);
    // A parameter is written only when it differs from its default, so the default case stays the
    // pre-registered template byte for byte.
    for (id, value) in &request.parameters {
        let path = parameter_path(id).ok_or_else(|| format!("unknown parameter {id}"))?;
        if crate::catalog::parameter_default(id) == Some(*value) {
            continue;
        }
        let mut node = &mut case;
        for key in path {
            let next = match key.parse::<usize>() {
                Ok(index) => node.get_mut(index),
                Err(_) => node.get_mut(*key),
            };
            node = next.ok_or_else(|| {
                format!(
                    "parameter {id} does not exist in the case of {}",
                    request.scenario
                )
            })?;
        }
        *node = number(*value);
        if pins_registered_value(id) {
            case["schema"] = json!(EXPLORATORY_SCHEMA);
        }
    }
    serde_json::to_vec(&case).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fmt_g_matches_python() {
        assert_eq!(fmt_g(0.0), "0");
        assert_eq!(fmt_g(5.26), "5.26");
        assert_eq!(fmt_g(40.0), "40");
        assert_eq!(fmt_g(27.5), "27.5");
        assert_eq!(fmt_g(0.001), "0.001");
        assert_eq!(fmt_g(12.3456), "12.3456");
        assert_eq!(fmt_g(0.0001), "0.0001");
        assert_eq!(fmt_g(0.00001), "1e-05");
        assert_eq!(fmt_g(1234567.0), "1.23457e+06");
        assert_eq!(fmt_g(123456.0), "123456");
        assert_eq!(fmt_g(0.1234567), "0.123457");
    }

    #[test]
    fn times_must_be_whole_steps() {
        assert_eq!(whole_steps(5.26, "t"), Ok(526));
        assert!(whole_steps(5.261, "t").is_err());
        assert!(whole_steps(40.01, "t").is_err());
        assert!(whole_steps(-0.01, "t").is_err());
    }
}
