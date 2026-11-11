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

/// The radar altimeter reads 50 m high for the whole flight.
fn altimeter_high() -> Vec<FaultRequest> {
    vec![fault("altimeter_bias", Some(50.0), 0.0, 40.0)]
}

/// GNSS bias of the M9.1 G3 registration: 15 m from the first instant.
fn gnss_bias_registered() -> Vec<FaultRequest> {
    vec![fault("gnss_bias", Some(15.0), 0.0, 40.0)]
}

/// A smaller GNSS bias that starts 0.02 s later: the counterexample region of the M13 investigation.
fn gnss_bias_late() -> Vec<FaultRequest> {
    vec![fault("gnss_bias", Some(9.72), 0.02, 40.0)]
}

fn with_lateral_gain(mut r: RunRequest, gain: f64) -> RunRequest {
    r.parameters.insert("lateral_position_gain".into(), gain);
    r
}

fn with_threshold(mut r: RunRequest, threshold_m: f64) -> RunRequest {
    r.parameters
        .insert("altimeter_residual_threshold_m".into(), threshold_m);
    r
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
        Demo {
            id: "altimeter-reads-high".into(),
            title: "A sensor that lies: the altimeter reads 50 m high".into(),
            narrative: "The radar altimeter reports 50 m more height than the stage really has, for the whole flight. The baseline controller believes it, brakes for a ground that is further away than it is and reaches the surface at about 33 m/s. The robust controller compares the altimeter with its own GNSS and inertial estimate, rejects it after 0.1 s and lands normally. Same stage, same seed, same fault: only the way the controller treats the sensor differs.".into(),
            requests: vec![
                request(M9, "baseline", 5000, altimeter_high()),
                request(M9, "robust", 5000, altimeter_high()),
            ],
            look_at: look(&[
                "Altitude: the baseline run keeps falling fast after the robust run has slowed down",
                "Events: the robust controller rejects the altimeter at 0.1 s; the baseline run never does",
                "Vertical speed at contact: about 33 m/s for baseline against the 3 m/s limit of R1; its sideways speed also exceeds the 1 m/s of R2",
                "Safety stays safe in both runs: a hard landing breaks a mission requirement, not a safety invariant",
            ]),
            expectation: "Baseline: hard landing, safe, R1 vertical speed and R2 horizontal speed fail. Robust: landed with every requirement and every safety invariant met.".into(),
        },
        Demo {
            id: "late-gnss-bias".into(),
            title: "When a fault starts matters: a smaller, later GNSS bias".into(),
            narrative: "Both runs fly the guarded M9.1 controller with a GNSS position bias. In the first the bias is the registered G3 condition, 15 m from the first instant: the estimator starts on the biased fix, the altimeter disagrees at once and is rejected at 0.1 s, and the stage lands softly but about 14 m from the pad centre, outside the 10 m of R5. In the second the bias is smaller, 9.72 m, and starts 0.02 s later: the altimeter is never rejected, the estimator blends two inconsistent sensors and the stage reaches the ground at about 17 m/s, breaking R1. Neither run meets every requirement; they fail different ones. This is one development seed; the M13 investigation measured the pattern on 30 fresh seeds and it remains an exploratory finding.".into(),
            requests: vec![
                request(M91, "guarded", 5000, gnss_bias_registered()),
                request(M91, "guarded", 5000, gnss_bias_late()),
            ],
            look_at: look(&[
                "Events: the first run rejects the altimeter at 0.1 s; the second has no rejection",
                "Top view: the first touchdown is outside the 10 m circle, the second inside it",
                "Vertical speed at contact: about 2 m/s against about 17 m/s",
            ]),
            expectation: "Registered bias: hard landing, safe, only R5 position fails. Smaller later bias: hard landing, safe, only R1 vertical speed fails.".into(),
        },
        Demo {
            id: "threshold-trade-off".into(),
            title: "A fix with a price: lowering the rejection threshold".into(),
            narrative: "The late, smaller GNSS bias again, on another development seed. With the default 3 m altimeter rejection threshold the guarded controller never rejects the altimeter, climbs under power near the ground (safety invariant S5) and lands at about 24 m/s. With a 1 m threshold it rejects the altimeter at 0.18 s and touches down softly, but about 13 m from the pad centre, outside R5. The change removes the hard landing and moves the failure to another requirement. In the M13 investigation the same mitigation removed the R1 violation on 30 of 30 counterexample seeds and introduced an R5 violation on 6 of them; across the envelope it added R2 violations in 26 paired runs and R5 violations in 9, and it did not remove the violation in the two regression families with a low-reading bias.".into(),
            requests: vec![
                request(M91, "guarded", 5017, gnss_bias_late()),
                with_threshold(request(M91, "guarded", 5017, gnss_bias_late()), 1.0),
            ],
            look_at: look(&[
                "Safety: unsafe with the default threshold (S5, powered ascent), safe with 1 m",
                "Requirements: R1 fails with 3 m; R5 fails with 1 m",
                "Events: the altimeter is rejected only with the 1 m threshold",
            ]),
            expectation: "Threshold 3 m: hard landing, unsafe, R1 vertical speed and S5 no powered ascent fail. Threshold 1 m: hard landing, safe, only R5 position fails.".into(),
        },
        Demo {
            id: "soft-but-off-pad".into(),
            title: "Soft, but off the pad: a lateral guidance tuned too gently".into(),
            narrative: "The robust controller with its lateral position gain lowered from 0.12 to 0.04 per second, no fault. The stage brakes as it should and touches down at about 1.7 m/s, well inside the 3 m/s of R1, but its guidance pulls it toward the pad centre too slowly: it lands about 19 m away, outside the 10 m of R5. Open it in the Experiment Lab to change the gain or the tilt cap, run a new simulation and check whether the setting that lands on the pad holds on other seeds.".into(),
            requests: vec![with_lateral_gain(request(M9, "robust", 5000, vec![]), 0.04)],
            look_at: look(&[
                "Vertical speed at contact: about 1.7 m/s against the 3 m/s limit of R1",
                "Distance from pad centre at contact: about 19 m against the 10 m of R5",
                "Safety stays safe: missing the pad is a mission requirement, not a safety invariant, while the stage stays inside the 50 m keep-out radius",
            ]),
            expectation: "Hard landing, safe, only R5 position fails.".into(),
        },
    ]
}
