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

/// (demo id, per request: controller, outcome code, safety status, physical class, failed requirement ids)
type Row = (
    &'static str,
    &'static str,
    &'static str,
    Option<&'static str>,
    &'static [&'static str],
);

#[test]
fn demos_show_what_their_expectation_says() {
    let expected: &[(&str, &[Row])] = &[
        (
            "nominal-landing",
            &[
                ("robust", "landed", "safe", None, &[]),
                ("m10_b_plus", "landed", "safe", Some("R"), &[]),
            ],
        ),
        (
            "altimeter-stuck",
            &[
                ("m10_b_plus", "landed", "safe", Some("R"), &[]),
                ("m10_b", "landed", "safe", Some("R"), &[]),
                (
                    "m10_a",
                    "hard_landing",
                    "safe",
                    Some("U"),
                    &["R2_horizontal_speed", "R5_position"],
                ),
            ],
        ),
        (
            "bias-and-outage-unsafe",
            &[
                (
                    "baseline",
                    "no_contact",
                    "unsafe",
                    None,
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
                ("robust", "landed", "safe", None, &[]),
                ("guarded", "landed", "safe", None, &[]),
                (
                    "m10_b_plus",
                    "hard_landing",
                    "safe",
                    Some("T"),
                    &["R5_position"],
                ),
            ],
        ),
        (
            "bias-and-outage-lateral",
            &[
                (
                    "m10_b_plus",
                    "hard_landing",
                    "safe",
                    Some("U"),
                    &["R2_horizontal_speed", "R5_position"],
                ),
                ("robust", "landed", "safe", None, &[]),
                ("guarded", "landed", "safe", None, &[]),
            ],
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
        for (r, (controller, outcome, safety, class, failed)) in demo.requests.iter().zip(*rows) {
            assert_eq!(&r.controller, controller, "{demo_id}");
            let record = run(r, &format!("{demo_id}-{controller}"));
            let label = format!("{demo_id} / {controller}");
            assert_eq!(&record.outcome.code, outcome, "{label}");
            assert_eq!(&record.safety.status, safety, "{label}");
            assert_eq!(record.safety.class.as_deref(), *class, "{label}");
            let mut got: Vec<&str> = record
                .requirements
                .iter()
                .filter(|q| q.category != "declaration" && q.status != "pass")
                .map(|q| q.id.as_str())
                .collect();
            got.sort();
            let mut want: Vec<&str> = failed.to_vec();
            want.sort();
            assert_eq!(got, want, "{label}");
        }
    }
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
    assert!(
        record
            .outcome
            .explanation
            .contains("did not reach the ground")
    );
}
