//! Demonstrations. Every expectation was observed with real runs at the commit that added this file
//! and is checked by `tests/host.rs`. Development seeds only (5000 to 5099).

use vv_platform::contract::Demo;

use crate::catalog::{MEDIUM, SMALL, request};

fn look(items: &[&str]) -> Vec<String> {
    items.iter().map(|s| s.to_string()).collect()
}

pub fn demos() -> Vec<Demo> {
    vec![
        Demo {
            id: "small-to-orbit".into(),
            title: "Small launcher to a 300 km orbit".into(),
            narrative: "The nominal ascent of the small exploratory launcher with seeded dispersions: the stack rises, kicks and turns, throttles through max-Q, separates, and from then on the booster and the upper stage are two entities with their own histories.".into(),
            requests: vec![request(SMALL, 5000, &[])],
            look_at: look(&["upper.R5_apoapsis", "booster.R3_recovery_zone", "stack.S1_max_dynamic_pressure"]),
            expectation: "Orbit: every requirement and invariant passes; the booster falls inside its zone.".into(),
        },
        Demo {
            id: "medium-to-orbit".into(),
            title: "Medium launcher to a 400 km orbit".into(),
            narrative: "The nominal ascent of the medium exploratory launcher, which keeps 6 % of its first-stage propellant for recovery.".into(),
            requests: vec![request(MEDIUM, 5000, &[])],
            look_at: look(&["upper.R4_periapsis", "upper.R5_apoapsis"]),
            expectation: "Orbit: periapsis and apoapsis within 1 km of 400 km; every requirement passes.".into(),
        },
        Demo {
            id: "payload-too-heavy".into(),
            title: "Payload beyond the upper-stage performance".into(),
            narrative: "The same small launcher with 600 kg of payload. The upper stage reaches its propellant reserve before the target energy, so the guidance cuts off short of orbit.".into(),
            requests: vec![request(SMALL, 5000, &[("small_payload_kg", 600.0)])],
            look_at: look(&["upper.R6_propellant_margin", "upper.R4_periapsis", "mission.R8_orbit_insertion"]),
            expectation: "No orbit: upper.R6_propellant_margin fails because SECO came from the propellant reserve, and orbit insertion fails.".into(),
        },
        Demo {
            id: "kick-too-steep".into(),
            title: "A pitch kick that keeps the stack in dense air".into(),
            narrative: "A 6 degree kick turns the small launcher over too early: the trajectory flattens low in the atmosphere and the dynamic pressure exceeds its limit even with the throttle at its minimum.".into(),
            requests: vec![request(SMALL, 5000, &[("small_kick_angle_deg", 6.0)])],
            look_at: look(&["stack.S1_max_dynamic_pressure"]),
            expectation: "Unsafe: stack.S1_max_dynamic_pressure fails, with the throttle at its minimum among the causes.".into(),
        },
    ]
}
