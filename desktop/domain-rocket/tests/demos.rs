//! Every demonstration of the catalog validates, uses a development seed and shows what its
//! expectation says (observed with real runs; a change of the simulator that moves an outcome fails here).

use std::fs;
use std::path::PathBuf;

use vv_domain_rocket::Host;
use vv_domain_rocket::catalog::catalog;
use vv_platform::contract::*;
use vv_platform::host_sdk::{HostError, execute, replay, validate_request};

fn run(request: &RunRequest, label: &str) -> RunRecord {
    let normal = validate_request(&Host, request).expect("valid demo request");
    let dir: PathBuf =
        std::env::temp_dir().join(format!("vv-rocket-demo-{}-{label}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let record = match execute(&Host, &normal, &dir) {
        Ok(r) => r,
        Err(HostError::Invalid(e) | HostError::Simulation(e)) => panic!("{e}"),
    };
    let report = replay(&Host, &dir);
    assert_eq!(report.status, "verified", "{label}: {:?}", report.checks);
    let _ = fs::remove_dir_all(&dir);
    record
}

#[test]
fn every_demo_request_validates_with_a_development_seed() {
    let c = catalog();
    assert!(c.demos.len() >= 3);
    for demo in &c.demos {
        assert!(
            !demo.requests.is_empty() && !demo.look_at.is_empty() && !demo.expectation.is_empty()
        );
        for r in &demo.requests {
            assert!(
                (5000..=5099).contains(&r.seed),
                "{}: seed {}",
                demo.id,
                r.seed
            );
            let normal = validate_request(&Host, r).unwrap_or_else(|e| panic!("{}: {e}", demo.id));
            assert_eq!(normal.faults.len(), r.faults.len());
        }
    }
}

/// (demo id, per request: controller, outcome code, safety status, failed requirement ids)
type Row = (
    &'static str,
    &'static str,
    &'static str,
    &'static [&'static str],
);

#[test]
fn demos_show_what_their_expectation_says() {
    let expected: &[(&str, &[Row])] = &[
        ("nominal-landing", &[("robust", "landed", "safe", &[])]),
        (
            "bias-and-outage-unsafe",
            &[
                (
                    "baseline",
                    "no_contact",
                    "unsafe",
                    &[
                        "R1_vertical_speed",
                        "R2_horizontal_speed",
                        "R3_tilt",
                        "R4_angular_rate",
                        "R5_position",
                        "R6_propellant_margin",
                        "S2_keep_out",
                        "S5_no_powered_ascent",
                    ],
                ),
                ("robust", "landed", "safe", &[]),
                ("guarded", "landed", "safe", &[]),
            ],
        ),
        (
            "bias-and-short-outage",
            &[
                ("robust", "landed", "safe", &[]),
                ("guarded", "landed", "safe", &[]),
            ],
        ),
        (
            "altimeter-reads-high",
            &[
                (
                    "baseline",
                    "hard_landing",
                    "safe",
                    &["R1_vertical_speed", "R2_horizontal_speed"],
                ),
                ("robust", "landed", "safe", &[]),
            ],
        ),
        (
            "late-gnss-bias",
            &[
                ("guarded", "hard_landing", "safe", &["R5_position"]),
                ("guarded", "hard_landing", "safe", &["R1_vertical_speed"]),
            ],
        ),
        (
            "threshold-trade-off",
            &[
                (
                    "guarded",
                    "hard_landing",
                    "unsafe",
                    &["R1_vertical_speed", "S5_no_powered_ascent"],
                ),
                ("guarded", "hard_landing", "safe", &["R5_position"]),
            ],
        ),
        (
            "soft-but-off-pad",
            &[("robust", "hard_landing", "safe", &["R5_position"])],
        ),
    ];
    let c = catalog();
    assert_eq!(c.demos.len(), expected.len());
    for (demo_id, rows) in expected {
        let demo = c
            .demos
            .iter()
            .find(|d| d.id == *demo_id)
            .unwrap_or_else(|| panic!("{demo_id}"));
        assert_eq!(demo.requests.len(), rows.len(), "{demo_id}");
        for (r, (controller, outcome, safety, failed)) in demo.requests.iter().zip(*rows) {
            assert_eq!(&r.controller, controller, "{demo_id}");
            let record = run(r, &format!("{demo_id}-{controller}"));
            let label = format!("{demo_id} / {controller}");
            assert_eq!(&record.outcome.code, outcome, "{label}");
            assert_eq!(&record.safety.status, safety, "{label}");
            assert_eq!(record.safety.class, None, "{label}");
            let mut got: Vec<&str> = record
                .requirements
                .iter()
                .filter(|q| q.status != "pass")
                .map(|q| q.id.as_str())
                .collect();
            got.sort();
            let mut want: Vec<&str> = failed.to_vec();
            want.sort();
            assert_eq!(got, want, "{label}");
        }
    }
}

fn metric(record: &RunRecord, id: &str) -> Option<f64> {
    record.metrics.iter().find(|m| m.id == id)?.value
}

fn first_event(record: &RunRecord, kind: &str) -> Option<f64> {
    record.events.iter().find(|e| e.kind == kind).map(|e| e.t)
}

#[test]
fn the_nominal_demo_shows_its_look_at_values() {
    let c = catalog();
    let demo = c.demos.iter().find(|d| d.id == "nominal-landing").unwrap();
    let record = run(&demo.requests[0], "nominal-look");
    let vz = metric(&record, "touchdown_vertical_speed").unwrap();
    let pad = metric(&record, "touchdown_pad_distance").unwrap();
    assert!((1.6..1.8).contains(&vz), "{vz}");
    assert!((2.5..3.5).contains(&pad), "{pad}");
    let err_z = record.channels.iter().find(|c| c.id == "err_z").unwrap();
    let worst = err_z
        .values
        .iter()
        .flatten()
        .fold(0.0_f64, |a, b| a.max(b.abs()));
    assert!(worst < 0.35, "{worst}");
}

#[test]
fn the_short_outage_demo_flies_one_trajectory_with_both_controllers() {
    let c = catalog();
    let demo = c
        .demos
        .iter()
        .find(|d| d.id == "bias-and-short-outage")
        .unwrap();
    let robust = run(&demo.requests[0], "short-robust");
    let guarded = run(&demo.requests[1], "short-guarded");
    for id in [
        "touchdown_t_s",
        "touchdown_vertical_speed",
        "touchdown_horizontal_speed",
        "touchdown_pad_distance",
        "propellant_remaining_kg",
    ] {
        assert_eq!(metric(&robust, id), metric(&guarded, id), "{id}");
    }
    let pad = metric(&robust, "touchdown_pad_distance").unwrap();
    assert!((2.5..3.5).contains(&pad), "{pad}");
    assert_eq!(first_event(&robust, "altimeter_rejected"), Some(0.1));
    assert_eq!(first_event(&guarded, "altimeter_rejected"), Some(0.1));
    assert_eq!(first_event(&guarded, "sensor_disagreement"), Some(0.1));
    assert_eq!(first_event(&robust, "sensor_disagreement"), None);
}

#[test]
fn the_unsafe_demo_explains_the_violation_in_plain_terms() {
    let c = catalog();
    let demo = c
        .demos
        .iter()
        .find(|d| d.id == "bias-and-outage-unsafe")
        .unwrap();
    let record = run(&demo.requests[0], "unsafe-explain");
    let s5 = record
        .requirements
        .iter()
        .find(|r| r.id == "S5_no_powered_ascent")
        .unwrap();
    assert_eq!(s5.status, "fail");
    assert!(
        s5.t.is_some() && s5.explanation.contains("altimeter_bias"),
        "{}",
        s5.explanation
    );
    assert!(
        record.safety.explanation.contains("S5")
            || record.safety.explanation.contains("Climb under power")
    );
    assert!(record.events.iter().any(|e| e.kind == "invariant_violation"
        && e.severity == "violation"
        && e.source == "verifier"));
    assert!(record.events.iter().any(|e| e.kind == "no_contact"));
    // The narrative says the stage stops descending at about 380 m.
    let altitude = record.channels.iter().find(|c| c.id == "altitude").unwrap();
    let lowest = altitude
        .values
        .iter()
        .flatten()
        .fold(f64::MAX, |a, b| a.min(*b));
    assert!((370.0..390.0).contains(&lowest), "{lowest}");
    assert!(
        record
            .outcome
            .explanation
            .contains("did not reach the ground")
    );
}

#[test]
fn the_showcase_demos_show_their_look_at_values() {
    let c = catalog();
    let demo = |id: &str| c.demos.iter().find(|d| d.id == id).unwrap().clone();
    let d = demo("altimeter-reads-high");
    let baseline = run(&d.requests[0], "high-baseline");
    let robust = run(&d.requests[1], "high-robust");
    assert_eq!(first_event(&baseline, "altimeter_rejected"), None);
    assert_eq!(first_event(&robust, "altimeter_rejected"), Some(0.1));
    let vz = metric(&baseline, "touchdown_vertical_speed").unwrap();
    assert!((32.0..34.0).contains(&vz), "{vz}");
    let d = demo("late-gnss-bias");
    let registered = run(&d.requests[0], "late-registered");
    let late = run(&d.requests[1], "late-late");
    assert_eq!(first_event(&registered, "altimeter_rejected"), Some(0.1));
    assert_eq!(first_event(&late, "altimeter_rejected"), None);
    let (a, b) = (
        metric(&registered, "touchdown_vertical_speed").unwrap(),
        metric(&late, "touchdown_vertical_speed").unwrap(),
    );
    assert!(
        (1.8..2.3).contains(&a) && (16.0..18.0).contains(&b),
        "{a} {b}"
    );
    let pad = metric(&registered, "touchdown_pad_distance").unwrap();
    assert!((13.0..16.0).contains(&pad), "{pad}");
    let d = demo("threshold-trade-off");
    let default = run(&d.requests[0], "trade-default");
    let lowered = run(&d.requests[1], "trade-lowered");
    assert_eq!(first_event(&default, "altimeter_rejected"), None);
    assert_eq!(first_event(&lowered, "altimeter_rejected"), Some(0.18));
    let vz = metric(&default, "touchdown_vertical_speed").unwrap();
    assert!((23.0..25.5).contains(&vz), "{vz}");
    let pad = metric(&lowered, "touchdown_pad_distance").unwrap();
    assert!((12.0..14.0).contains(&pad), "{pad}");
}

#[test]
fn the_confirmation_reserve_is_refused() {
    for seed in [44_000, 44_500, 44_999] {
        let r = vv_domain_rocket::catalog::request("m91-landing", "guarded", seed, vec![]);
        assert!(validate_request(&Host, &r).is_err(), "seed {seed}");
    }
}
