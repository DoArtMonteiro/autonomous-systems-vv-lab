//! Tests of the ascent domain host: catalog defaults against the templates, the seed guard, request
//! validation, the vv-run.v2 record and its entities, determinism, replay and tamper detection, and
//! the demonstrations.

use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

use vv_domain_ascent::case::template;
use vv_domain_ascent::catalog::{MEDIUM, PARAMS, SMALL, Target, catalog, request};
use vv_domain_ascent::{Host, manifest};
use vv_platform::canonical::pretty_bytes;
use vv_platform::contract::*;
use vv_platform::host_sdk::{execute, replay, validate_request};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn temp(label: &str) -> PathBuf {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let dir =
        std::env::temp_dir().join(format!("vv-ascent-host-{}-{label}-{n}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(request: &RunRequest, label: &str) -> (RunRecord, PathBuf) {
    let normal = validate_request(&Host, request).unwrap();
    let dir = temp(label);
    let record = execute(&Host, &normal, &dir).unwrap_or_else(|_| panic!("run {label}"));
    (record, dir)
}

fn status<'a>(r: &'a RunRecord, id: &str) -> &'a str {
    &r.requirements.iter().find(|q| q.id == id).unwrap().status
}

#[test]
fn every_parameter_default_is_the_value_of_its_template() {
    for p in &PARAMS {
        for scenario in [SMALL, MEDIUM] {
            if p.scenario.is_some_and(|s| s != scenario) {
                continue;
            }
            let c = template(scenario).unwrap();
            let actual = match p.target {
                Target::TargetAltitudeKm => c.mission.target_altitude_km,
                Target::KickTimeS => c.mission.kick_time_s,
                Target::KickAngleDeg => c.mission.kick_angle_deg,
                Target::GravityTurnStartS => c.mission.gravity_turn_start_s,
                Target::PayloadKg => c.vehicle.payload_kg,
                Target::Dispersions => f64::from(u8::from(c.dispersions.enabled)),
            };
            assert_eq!(actual, p.default, "{} in {scenario}", p.id);
            assert!(p.min <= p.default && p.default <= p.max, "{}", p.id);
        }
    }
    let cat = catalog();
    assert_eq!(cat.max_faults, 0);
    assert!(cat.faults.is_empty());
    let m = manifest();
    assert!(m.visualisations.contains(&"scene.ascent".to_string()));
}

#[test]
fn protected_seeds_are_refused_at_both_ends_of_every_range() {
    for seed in [3000, 3099, 6000, 6099, 44000, 44999] {
        assert!(
            validate_request(&Host, &request(SMALL, seed, &[])).is_err(),
            "{seed}"
        );
    }
    for seed in [2999, 3100, 5999, 6100, 43999, 45000, 5000] {
        assert!(
            validate_request(&Host, &request(SMALL, seed, &[])).is_ok(),
            "{seed}"
        );
    }
}

#[test]
fn invalid_parameters_are_refused_before_any_run() {
    // Gravity turn before the end of the pitch kick (kick time + 4 s).
    let r = request(
        SMALL,
        5000,
        &[
            ("small_kick_time_s", 12.0),
            ("small_gravity_turn_start_s", 14.0),
        ],
    );
    assert!(
        validate_request(&Host, &r)
            .unwrap_err()
            .contains("gravity_turn_start_s")
    );
    // Not a multiple of the 20 ms step.
    let r = request(SMALL, 5000, &[("small_kick_time_s", 8.01)]);
    assert!(validate_request(&Host, &r).is_err());
    // A parameter of the other vehicle.
    let r = request(SMALL, 5000, &[("medium_payload_kg", 1000.0)]);
    assert!(validate_request(&Host, &r).is_err());
    // Out of range.
    let r = request(MEDIUM, 5000, &[("medium_payload_kg", 20000.0)]);
    assert!(validate_request(&Host, &r).is_err());
}

#[test]
fn the_record_is_v2_with_three_entities_and_consistent_ownership() {
    let (r, dir) = run(&request(SMALL, 5000, &[]), "v2");
    assert_eq!(r.schema, RECORD_SCHEMA_V2);
    r.check_entities().unwrap();
    assert_eq!(r.outcome.code, "orbit");
    assert_eq!(r.safety.status, "safe");
    let e = r.entities.as_ref().unwrap();
    let ids: Vec<(&str, Option<&str>)> = e
        .iter()
        .map(|x| (x.id.as_str(), x.parent.as_deref()))
        .collect();
    assert_eq!(
        ids,
        [
            ("stack", None),
            ("booster", Some("stack")),
            ("upper", Some("stack"))
        ]
    );
    assert_eq!(e[1].t_start, e[0].t_end);
    assert_eq!(e[2].t_start, e[0].t_end);
    assert!(
        e[1].events
            .iter()
            .any(|&i| r.events[i as usize].kind == "impact")
    );
    assert!(
        r.requirements.iter().all(|q| q.status == "pass"),
        "{:?}",
        r.requirements
            .iter()
            .filter(|q| q.status != "pass")
            .collect::<Vec<_>>()
    );
    assert_eq!(r.scene["kind"], "ascent");
    // The mission clock spans the whole flight for the time cursor.
    let clock = &r.timebases["mission"];
    let last_end = e.iter().map(|x| x.t_end).fold(0.0, f64::max);
    assert_eq!(*clock.last().unwrap(), last_end);
    assert_eq!(r.scene["channels"]["timebase"], "mission");
    // The visual block reaches the scene only.
    assert_eq!(r.scene["visual"]["role"], vv_ascent::model::VISUAL_ROLE);
    for f in [
        "case.json",
        "trace.json",
        "verification.json",
        "run.json",
        "record.json",
    ] {
        assert!(dir.join(f).exists(), "{f}");
    }
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn runs_are_deterministic_and_seeds_matter() {
    let (a, da) = run(&request(MEDIUM, 5000, &[]), "det-a");
    let (b, db) = run(&request(MEDIUM, 5000, &[]), "det-b");
    assert_eq!(pretty_bytes(&a), pretty_bytes(&b));
    let (c, dc) = run(&request(MEDIUM, 5001, &[]), "det-c");
    assert_ne!(a.channels, c.channels);
    for d in [da, db, dc] {
        let _ = fs::remove_dir_all(d);
    }
}

#[test]
fn replay_recomputes_and_rejects_tampering() {
    let (_, dir) = run(&request(SMALL, 5001, &[]), "replay");
    let ok = replay(&Host, &dir);
    assert_eq!(ok.status, "verified", "{:?}", ok.checks);
    assert!(
        ok.checks
            .iter()
            .any(|c| c.name.starts_with("vv-ascent replay:") && c.pass)
    );
    let rec = dir.join("record.json");
    let text = fs::read_to_string(&rec).unwrap();
    fs::write(&rec, text.replacen("\"pass\"", "\"fail\"", 1)).unwrap();
    assert_eq!(replay(&Host, &dir).status, "rejected");
    fs::write(&rec, &text).unwrap();
    let tr = dir.join("trace.json");
    let t = fs::read_to_string(&tr).unwrap();
    fs::write(
        &tr,
        t.replacen("\"altitude_m\": 0.0", "\"altitude_m\": 1.0", 1),
    )
    .unwrap();
    assert_eq!(replay(&Host, &dir).status, "rejected");
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn demonstrations_show_what_they_claim() {
    for demo in catalog().demos {
        let (r, dir) = run(&demo.requests[0], &demo.id);
        match demo.id.as_str() {
            "small-to-orbit" | "medium-to-orbit" => {
                assert_eq!(r.outcome.code, "orbit", "{}", demo.id);
                assert!(
                    r.requirements.iter().all(|q| q.status == "pass"),
                    "{}",
                    demo.id
                );
            }
            "payload-too-heavy" => {
                assert_ne!(r.outcome.code, "orbit");
                assert_eq!(status(&r, "upper.R6_propellant_margin"), "fail");
                assert_eq!(status(&r, "mission.R8_orbit_insertion"), "fail");
                let q = r
                    .requirements
                    .iter()
                    .find(|q| q.id == "upper.R6_propellant_margin")
                    .unwrap();
                assert!(
                    q.explanation.contains("propellant reserve"),
                    "{}",
                    q.explanation
                );
            }
            "kick-too-steep" => {
                assert_eq!(r.safety.status, "unsafe");
                let q = r
                    .requirements
                    .iter()
                    .find(|q| q.id == "stack.S1_max_dynamic_pressure")
                    .unwrap();
                assert_eq!(q.status, "fail");
                assert!(q.explanation.contains("minimum"), "{}", q.explanation);
            }
            other => panic!("demo {other} has no test"),
        }
        for id in &demo.look_at {
            assert!(r.requirements.iter().any(|q| &q.id == id), "{id}");
        }
        let _ = fs::remove_dir_all(&dir);
    }
}
