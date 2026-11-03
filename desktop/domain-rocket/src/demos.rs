//! Demonstrations. Every expectation was observed with real runs at the commit that added this file
//! and is checked by `tests/demos.rs`. Development seeds only (5000 to 5099); nothing here is an
//! evaluation result.

use vv_platform::contract::*;

use crate::case::{M9, M91};
use crate::catalog::request;

fn fault(kind: &str, magnitude: Option<f64>, start: f64, end: f64) -> FaultRequest {
    FaultRequest {
        kind: kind.into(),
        magnitude,
        start,
        end,
    }
}

fn look(items: &[&str]) -> Vec<String> {
    items.iter().map(|s| s.to_string()).collect()
}

/// Altimeter bias of 50 m for the whole flight plus a 10 s GNSS outage: the hardest pair of the demos.
pub fn bias_and_outage() -> Vec<FaultRequest> {
    vec![
        fault("altimeter_bias", Some(50.0), 0.0, 40.0),
        fault("gnss_dropout", None, 8.0, 18.0),
    ]
}

/// Altimeter bias of 20 m for the whole flight plus a 6 s GNSS outage.
fn bias_and_short_outage() -> Vec<FaultRequest> {
    vec![
        fault("altimeter_bias", Some(20.0), 0.0, 40.0),
        fault("gnss_dropout", None, 8.0, 14.0),
    ]
}

pub fn demos() -> Vec<Demo> {
    vec![
        Demo {
            id: "nominal-landing".into(),
            title: "Nominal powered landing".into(),
            narrative: "A 22 t stage falls from about 3 km at 200 m/s, lights its engine at about 4.2 s and brakes to a slow descent over the pad. No fault is injected. The M9 robust controller sees a dispersed initial state and noisy sensors, so this is the reference picture of what a healthy landing looks like in every plot.".into(),
            requests: vec![request(M9, "robust", 5000, vec![])],
            look_at: look(&[
                "Top view: the touchdown is about 3 m from the pad centre, inside the 10 m circle",
                "Vertical speed: the descent slows from 200 m/s to about 1.7 m/s at contact, below the 3 m/s limit of R1",
                "Estimation error against truth: the vertical error stays within about 0.3 m",
            ]),
            expectation: "The run lands with every requirement and every safety invariant met.".into(),
        },
        Demo {
            id: "bias-and-outage-unsafe".into(),
            title: "Two faults and an unsafe outcome".into(),
            narrative: "The radar altimeter reads 50 m high for the whole flight and the GNSS delivers nothing from 8 s to 18 s. The baseline controller trusts the altimeter. In the run recorded here the stage stops descending at about 380 m, climbs under power and does not touch down within 40 s, which breaks invariant S5. The cause is the pair of faults acting on a controller that cannot tell which sensor to believe; the run does not isolate a single mechanism. The robust and guarded controllers reject the altimeter and land.".into(),
            requests: vec![
                request(M9, "baseline", 5000, bias_and_outage()),
                request(M9, "robust", 5000, bias_and_outage()),
                request(M91, "guarded", 5000, bias_and_outage()),
            ],
            look_at: look(&[
                "Altitude of the baseline run: the stage stops descending and climbs again with the engine on",
                "Events: the first S5 violation of the baseline run and the end of the run without contact",
                "Outcome and safety are separate verdicts: the baseline run has no contact and is also unsafe",
                "Altimeter observation against truth: a constant 50 m offset in every run",
            ]),
            expectation: "The baseline run has no contact and is unsafe (S5_no_powered_ascent fails); robust and guarded land with every requirement and every safety invariant met.".into(),
        },
        Demo {
            id: "bias-and-short-outage".into(),
            title: "Two faults: biased altimeter and a GNSS outage".into(),
            narrative: "The radar altimeter reads 20 m high for the whole flight and the GNSS delivers nothing from 8 s to 14 s. The robust controller rejects the altimeter from the first control cycles and carries its own estimate through the outage. The guarded controller also reports sensor_disagreement; because the altimeter reads high, the lower altitude it guides on is the same estimate, and in this run it flies the robust trajectory.".into(),
            requests: vec![
                request(M9, "robust", 5000, bias_and_short_outage()),
                request(M91, "guarded", 5000, bias_and_short_outage()),
            ],
            look_at: look(&[
                "Events: the controller first rejects the altimeter at 0.1 s in both runs; guarded also reports sensor disagreement",
                "Top view: both touchdowns about 3 m from the pad centre, inside the 10 m circle",
                "Comparison: the two runs reach the same touchdown values",
            ]),
            expectation: "Robust and guarded both land with every requirement and every safety invariant met.".into(),
        },
    ]
}
