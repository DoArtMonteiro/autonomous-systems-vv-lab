//! Demonstrations. Every expectation was observed with real runs at the commit that added this file
//! and is checked by `tests/demos.rs`. Development seeds only (5000 to 5099); nothing here is an
//! evaluation result.

use vv_platform::contract::*;

use crate::case::{M9, M10, M91};
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

pub fn demos() -> Vec<Demo> {
    vec![
        Demo {
            id: "nominal-landing".into(),
            title: "Nominal powered landing".into(),
            narrative: "A 22 t stage falls from about 3 km at 200 m/s, lights its engine at about 4.2 s and brakes to a 1.5 m/s descent over the pad. No fault is injected. The M9 robust controller and the M10 B+ controller see the same dispersed initial state and the same sensor noise, so this is the reference picture of what a healthy landing looks like in every plot.".into(),
            requests: vec![
                request(M9, "robust", 5000, vec![]),
                request(M10, "m10_b_plus", 5000, vec![]),
            ],
            look_at: look(&[
                "Top view: both touchdowns inside the 10 m pad circle",
                "Vertical speed: the descent slows from 200 m/s to about 2 m/s at contact, below the 3 m/s limit of R1",
                "Estimation error against truth: a few decimetres vertically, inside the declared uncertainty band (M10 only)",
                "CUSUM statistics far below their threshold (M10 only); the M10 arm declares degraded navigation only during the cold start",
            ]),
            expectation: "Both runs land with every requirement and every safety invariant met; the M10 run is physical class R.".into(),
        },
        Demo {
            id: "altimeter-stuck".into(),
            title: "Sensor fault with successful fault management".into(),
            narrative: "From 8 s to 12 s the radar altimeter repeats the value it delivered just before the window, while the vehicle keeps descending at more than 100 m/s. B+ compares the vertical-rate witnesses (radar slope, GNSS vertical velocity, IMU integration), finds that only the radar is inconsistent, isolates the radar group and carries on without it. Arm B rejects measurements epoch by epoch and never isolates. Arm A votes on altitudes and has no rate witness.".into(),
            requests: vec![
                request(M10, "m10_b_plus", 5000, vec![fault("altimeter_stuck", None, 8.0, 12.0)]),
                request(M10, "m10_b", 5000, vec![fault("altimeter_stuck", None, 8.0, 12.0)]),
                request(M10, "m10_a", 5000, vec![fault("altimeter_stuck", None, 8.0, 12.0)]),
            ],
            look_at: look(&[
                "Radar altimeter observation against truth: the observation goes flat from 8 s while the true altitude keeps falling",
                "Events: the radar group going suspect, then excluded, then readmitted in the B+ run, and the isolation verdict",
                "Declared uncertainty (sigma_z): it grows while the radar is excluded and falls when it is readmitted",
                "Requirements of arm A: R2 and R5 fail at contact",
            ]),
            expectation: "B+ lands (class R) with one correct radar isolation; B lands (class R) without isolating; A touches down hard and off the pad (class U, R2 and R5 failed). No safety invariant fails in any of the three.".into(),
        },
        Demo {
            id: "bias-and-outage-unsafe".into(),
            title: "Two faults and an unsafe outcome".into(),
            narrative: "The radar altimeter reads 50 m high for the whole flight and the GNSS delivers nothing from 8 s to 18 s. The baseline controller trusts the altimeter. In the run recorded here the stage stops descending at about 400 m, climbs under power and does not touch down within 40 s, which breaks invariant S5. The cause is the pair of faults acting on a controller that cannot tell which sensor to believe; the run does not isolate a single mechanism. The robust and guarded controllers reject the altimeter and land. The M10 B+ controller declares its navigation degraded and touches down intact but off the pad.".into(),
            requests: vec![
                request(M9, "baseline", 5000, bias_and_outage()),
                request(M9, "robust", 5000, bias_and_outage()),
                request(M91, "guarded", 5000, bias_and_outage()),
                request(M10, "m10_b_plus", 5000, bias_and_outage()),
            ],
            look_at: look(&[
                "Altitude of the baseline run: the stage stops descending and climbs again with the engine on",
                "Events: the first S5 violation of the baseline run and the end of the run without contact",
                "Outcome and safety are separate verdicts: the M10 run misses the pad (R5) but breaks no invariant",
                "Altimeter observation against truth: a constant 50 m offset in every run",
            ]),
            expectation: "The baseline run has no contact and is unsafe (S5_no_powered_ascent fails); robust and guarded land; B+ makes a hard landing off the pad (class T, only R5 failed) and stays safe.".into(),
        },
        Demo {
            id: "bias-and-outage-lateral".into(),
            title: "Two faults: biased altimeter and a GNSS outage (open M10 regression)".into(),
            narrative: "The radar altimeter reads 20 m high for the whole flight and the GNSS delivers nothing from 8 s to 14 s. With both altitude sources out, B+ declares untrusted navigation and by design stops chasing the pad laterally. The vehicle keeps braking, but untrusted is a declaration, not a safe state: it drifts off the pad and touches down too fast sideways while the vertical estimate stays good. robust keeps chasing the pad with its dead-reckoned position and lands. This is an open development regression of the M10 arms, shown as it is.".into(),
            requests: vec![
                request(M10, "m10_b_plus", 5000, vec![fault("altimeter_bias", Some(20.0), 0.0, 40.0), fault("gnss_dropout", None, 8.0, 14.0)]),
                request(M9, "robust", 5000, vec![fault("altimeter_bias", Some(20.0), 0.0, 40.0), fault("gnss_dropout", None, 8.0, 14.0)]),
                request(M91, "guarded", 5000, vec![fault("altimeter_bias", Some(20.0), 0.0, 40.0), fault("gnss_dropout", None, 8.0, 14.0)]),
            ],
            look_at: look(&[
                "Navigation mode of the B+ run: untrusted from about 8.5 s, then degraded again when the GNSS returns",
                "Top view: B+ touches down outside the 10 m circle while robust and guarded reach the pad",
                "Requirements: B+ fails R2 and R5 at contact with no vertical alert failure; the loss is lateral",
            ]),
            expectation: "B+ touches down hard and off the pad (class U, R2 and R5 failed) without breaking an invariant; robust and guarded land.".into(),
        },
    ]
}
