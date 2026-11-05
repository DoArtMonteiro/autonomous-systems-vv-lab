//! Mission-level tests: determinism, visual-only attributes, entities and event order, replay and
//! tampering, failing requirements with their causes, and golden fixtures.

use std::fs;
use std::path::PathBuf;

use serde_json::Value;
use vv_ascent::model::{Case, parse_case};
use vv_ascent::run::{Outputs, compute, replay, write_run};
use vv_ascent::sha256_hex;

fn case_text(id: &str) -> &'static str {
    vv_ascent::CASES.iter().find(|(c, _)| *c == id).unwrap().1
}

fn case(id: &str) -> Case {
    parse_case(case_text(id).as_bytes()).unwrap()
}

fn run(c: &Case, seed: u64) -> Outputs {
    compute(&serde_json::to_vec(c).unwrap(), seed).unwrap()
}

fn status(o: &Outputs, id: &str) -> &'static str {
    o.verification
        .verdicts
        .iter()
        .find(|v| v.id == id)
        .unwrap()
        .status
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("vv-ascent-test-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn same_seed_gives_identical_bytes_and_another_seed_with_dispersions_differs() {
    for id in ["small-leo", "medium-leo"] {
        let c = case(id);
        let a = run(&c, 5000);
        let b = run(&c, 5000);
        assert_eq!(a.trace_bytes, b.trace_bytes);
        assert_eq!(a.verification_bytes, b.verification_bytes);
        let other = run(&c, 5001);
        assert_ne!(a.trace_bytes, other.trace_bytes);
        assert_ne!(a.prepared.factors, other.prepared.factors);
    }
}

#[test]
fn without_dispersions_the_true_vehicle_is_the_nominal_one_and_only_sensor_noise_depends_on_the_seed()
 {
    let mut c = case("small-leo");
    c.dispersions.enabled = false;
    let a = run(&c, 1);
    let b = run(&c, 2);
    assert_eq!(a.prepared.factors, [[1.0; 4]; 2]);
    assert_eq!(a.prepared.truth, b.prepared.truth);
    // The navigation noise still differs, so the closed loop flies slightly differently.
    assert_ne!(a.trace_bytes, b.trace_bytes);
    c.sensors.position_sigma_m = 0.0;
    c.sensors.velocity_sigma_m_s = 0.0;
    let (a, b) = (run(&c, 1), run(&c, 2));
    assert_eq!(a.trace.entities, b.trace.entities);
    assert_eq!(a.verification_bytes, b.verification_bytes);
}

#[test]
fn visual_attributes_change_no_state_byte_and_no_verdict() {
    let base = case("medium-leo");
    let mut painted = base.clone();
    painted.visual.stages[0].length_m = 99.0;
    painted.visual.stages[1].diameter_m = 9.0;
    painted.visual.stages[0].colour = "#ff0000".into();
    painted.visual.fairing_colour = "#00ff00".into();
    let a = run(&base, 5000);
    let b = run(&painted, 5000);
    assert_ne!(
        serde_json::to_vec(&base).unwrap(),
        serde_json::to_vec(&painted).unwrap()
    );
    assert_eq!(a.trace_bytes, b.trace_bytes);
    assert_eq!(a.verification_bytes, b.verification_bytes);
    // A simulated attribute does change the state.
    let mut heavier = base.clone();
    heavier.vehicle.stages[0].dry_mass_kg += 100.0;
    assert_ne!(run(&heavier, 5000).trace_bytes, a.trace_bytes);
}

#[test]
fn nominal_cases_reach_orbit_with_two_independent_entities_after_separation() {
    for id in ["small-leo", "medium-leo"] {
        let o = run(&case(id), 5000);
        let v = &o.verification;
        assert_eq!(v.outcome, "orbit", "{id}");
        assert!(v.invariants_pass, "{id}");
        let ids: Vec<&str> = o.simulation.entities.iter().map(|e| e.id).collect();
        assert_eq!(ids, ["stack", "booster", "upper"]);
        let stack = o.simulation.entities[0].samples.last().unwrap();
        for child in &o.simulation.entities[1..] {
            let first = child.samples.first().unwrap();
            assert_eq!(first.tick, stack.tick, "{id}: children start at separation");
            assert_eq!((first.r, first.v), (stack.r, stack.v));
        }
        // Mass splits exactly at separation: booster plus upper stage is the stack.
        let (b, u) = (
            &o.simulation.entities[1].samples[0],
            &o.simulation.entities[2].samples[0],
        );
        assert!((b.m + u.m - stack.m).abs() < 1e-6, "{id}");
        // After separation the two histories diverge.
        let bl = o.simulation.entities[1].samples.last().unwrap();
        assert!(
            bl.r.norm() < vv_ascent::model::R_EARTH,
            "{id}: booster ends at impact"
        );
        assert_eq!(
            o.simulation.entities[2].end_reason,
            "end of coast after SECO"
        );
        // Coast after SECO keeps the two-body energy (drag above 300 km is negligible).
        let ins = v.insertion.as_ref().unwrap();
        let end = ins.end_of_coast.unwrap();
        let rel = ((end.energy_j_kg - ins.elements.energy_j_kg) / ins.elements.energy_j_kg).abs();
        assert!(rel < 1e-6, "{id}: coast energy drift {rel}");
    }
}

#[test]
fn events_are_in_total_order_and_phases_follow_the_mission_sequence() {
    let o = run(&case("small-leo"), 5000);
    let ev = &o.verification.events;
    for w in ev.windows(2) {
        assert!(
            (w[0].tick, w[0].entity, w[0].source, w[0].seq)
                < (w[1].tick, w[1].entity, w[1].source, w[1].seq),
            "{:?} then {:?}",
            w[0].kind,
            w[1].kind
        );
    }
    let first = |k: &str| {
        ev.iter()
            .position(|e| e.kind == k)
            .unwrap_or_else(|| panic!("{k}"))
    };
    let order = [
        "prelaunch_hold",
        "prelaunch_checks_passed",
        "ignition",
        "liftoff",
        "pitch_kick_start",
        "gravity_turn_start",
        "max_q",
        "meco",
        "separation",
        "upper_ignition",
        "seco",
        "orbit_insertion_evaluation",
    ];
    for w in order.windows(2) {
        assert!(first(w[0]) < first(w[1]), "{} before {}", w[0], w[1]);
    }
    assert!(ev.iter().any(|e| e.kind == "impact" && e.entity == 1));
}

#[test]
fn replay_recomputes_and_refuses_tampered_records() {
    let dir = scratch("replay");
    let case_path = dir.join("input.json");
    fs::write(&case_path, case_text("small-leo")).unwrap();
    let out = dir.join("run");
    fs::create_dir_all(&out).unwrap();
    write_run(&case_path, 5000, &out).unwrap();
    let ok = replay(&out);
    assert_eq!(ok.status, "verified", "{:?}", ok.checks);

    // A changed verdict in verification.json, with run.json hashes left as they were.
    let vpath = out.join("verification.json");
    let original = fs::read_to_string(&vpath).unwrap();
    fs::write(
        &vpath,
        original
            .replacen("\"fail\"", "\"pass\"", 1)
            .replacen("\"orbit\"", "\"suborbital\"", 1),
    )
    .unwrap();
    assert_eq!(replay(&out).status, "rejected");
    fs::write(&vpath, &original).unwrap();
    assert_eq!(replay(&out).status, "verified");

    // A tampered state sample, with the hash in run.json updated to match: recomputation catches it.
    let tpath = out.join("trace.json");
    let trace = fs::read_to_string(&tpath).unwrap();
    let mut t: Value = serde_json::from_str(&trace).unwrap();
    t["entities"][1]["samples"][3]["altitude_m"] = Value::from(1.0);
    let forged = vv_ascent::run::pretty(&t);
    let rpath = out.join("run.json");
    let run_text = fs::read_to_string(&rpath).unwrap();
    fs::write(
        &rpath,
        run_text.replace(&sha256_hex(trace.as_bytes()), &sha256_hex(&forged)),
    )
    .unwrap();
    fs::write(&tpath, &forged).unwrap();
    let r = replay(&out);
    assert_eq!(r.status, "rejected");
    assert!(
        r.checks
            .iter()
            .any(|c| !c.pass && c.name.contains("states"))
    );
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn a_heavy_payload_fails_insertion_with_the_cause_named() {
    let mut c = case("small-leo");
    c.vehicle.payload_kg = 600.0;
    let o = run(&c, 5000);
    assert_ne!(o.verification.outcome, "orbit");
    let v = o
        .verification
        .verdicts
        .iter()
        .find(|v| v.id == "upper.R6_propellant_margin")
        .unwrap();
    assert_eq!(v.status, "fail");
    assert!(v.tick.is_some() && v.state.is_some());
    assert!(
        v.cause.iter().any(|c| c.contains("SECO reason")),
        "{:?}",
        v.cause
    );
    assert_eq!(status(&o, "mission.R8_orbit_insertion"), "fail");
}

#[test]
fn an_excessive_pitch_kick_breaks_the_dynamic_pressure_invariant() {
    let mut c = case("small-leo");
    c.mission.kick_angle_deg = 6.0;
    let o = run(&c, 5000);
    assert_eq!(status(&o, "stack.S1_max_dynamic_pressure"), "fail");
    assert!(!o.verification.invariants_pass);
    let v = o
        .verification
        .verdicts
        .iter()
        .find(|v| v.id == "stack.S1_max_dynamic_pressure")
        .unwrap();
    let s = v.state.as_ref().unwrap();
    assert!(s.dynamic_pressure_pa > c.limits.max_q_pa);
}

#[test]
fn a_vehicle_that_cannot_lift_off_is_scrubbed_by_the_prelaunch_checks() {
    let mut c = case("small-leo");
    c.vehicle.payload_kg = 20_000.0;
    let o = run(&c, 5000);
    assert_eq!(o.verification.outcome, "scrubbed");
    assert!(o.verification.events.iter().any(|e| e.kind == "scrub"));
    assert_eq!(o.simulation.entities.len(), 1);
    assert_eq!(status(&o, "upper.R4_periapsis"), "not_evaluated");
}

#[test]
fn invalid_cases_are_refused_before_any_run() {
    let mut c = case("small-leo");
    c.status = "a real launcher".into();
    assert!(compute(&serde_json::to_vec(&c).unwrap(), 1).is_err());
    let mut c = case("small-leo");
    c.mission.gravity_turn_start_s = c.mission.kick_time_s;
    assert!(compute(&serde_json::to_vec(&c).unwrap(), 1).is_err());
    let mut c = case("small-leo");
    c.mission.kick_time_s = 8.01;
    assert!(compute(&serde_json::to_vec(&c).unwrap(), 1).is_err());
    let mut v: Value = serde_json::from_str(case_text("small-leo")).unwrap();
    v["vehicle"]["stages"][0]["length_m"] = Value::from(13.0);
    assert!(
        compute(&serde_json::to_vec(&v).unwrap(), 1).is_err(),
        "visual field in the simulated block"
    );
}

/// Golden fixtures: outcome, verdicts and the hashes of the native artifacts for both vehicles.
/// Regenerate with `VV_ASCENT_BLESS=1 cargo test --test ascent golden` after a deliberate change.
#[test]
fn golden_fixtures() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/golden");
    for (id, seed) in [
        ("small-leo", 5000u64),
        ("medium-leo", 5000),
        ("small-leo", 42),
    ] {
        let o = run(&case(id), seed);
        let got = serde_json::json!({
            "case": id,
            "seed": seed,
            "outcome": o.verification.outcome,
            "verdicts": o.verification.verdicts.iter().map(|v| serde_json::json!({
                "id": v.id, "status": v.status, "observed": v.observed,
            })).collect::<Vec<_>>(),
            "trace_sha256": sha256_hex(&o.trace_bytes),
            "verification_sha256": sha256_hex(&o.verification_bytes),
        });
        let path = dir.join(format!("{id}-{seed}.json"));
        let text = vv_ascent::run::pretty(&got);
        if std::env::var("VV_ASCENT_BLESS").is_ok() {
            fs::create_dir_all(&dir).unwrap();
            fs::write(&path, &text).unwrap();
        }
        let want =
            fs::read_to_string(&path).unwrap_or_else(|_| panic!("missing {}", path.display()));
        assert_eq!(
            want.replace("\r\n", "\n"),
            String::from_utf8(text).unwrap(),
            "{id} {seed}"
        );
    }
}
