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
        // The coast keeps the two-body energy because the model has almost no drag at this altitude
        // (the isothermal atmosphere is a model artefact there). This is an integrator check, not
        // evidence of an orbital lifetime.
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
    // The heavy payload leaves the true orbit at SECO with a periapsis below the surface.
    assert_eq!(o.verification.outcome, "suborbital");
    assert!(!o.verification.requirements_pass);
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
    // No invariant was judged: "no invariant failed" must not read as "safe" without the flag.
    let v = &o.verification;
    assert!(v.invariants_pass && !v.invariants_evaluated);
    assert_eq!(
        v.invariants_not_evaluated,
        [
            "stack.S1_max_dynamic_pressure",
            "stack.S2_axial_acceleration",
            "upper.S2_axial_acceleration"
        ]
    );
}

#[test]
fn a_nominal_flight_judges_every_invariant() {
    let o = run(&case("small-leo"), 5000);
    assert!(o.verification.invariants_pass && o.verification.invariants_evaluated);
    assert!(o.verification.invariants_not_evaluated.is_empty());
}

fn elements_with(energy: f64, periapsis_alt_m: f64) -> vv_ascent::dynamics::Elements {
    vv_ascent::dynamics::Elements {
        energy_j_kg: energy,
        angular_momentum_m2_s: 5.0e10,
        semi_major_axis_m: (energy < 0.0).then_some(7.0e6),
        eccentricity: 0.1,
        periapsis_alt_m,
        apoapsis_alt_m: (energy < 0.0).then_some(400e3),
    }
}

#[test]
fn the_outcome_is_decided_in_a_fixed_order_and_each_code_means_one_thing() {
    use vv_ascent::dynamics::Elements;
    use vv_ascent::verify::{OUTCOMES, OutcomeInput, classify_outcome};
    fn flying(seco: Option<&Elements>, surface: bool, on_target: bool) -> OutcomeInput<'_> {
        OutcomeInput {
            lifted_off: true,
            separated: true,
            upper_reached_surface: surface,
            seco,
            min_periapsis_km: 180.0,
            apoapsis_on_target: on_target,
        }
    }
    let (below_surface, low, off, good) = (
        elements_with(-2.9e7, -859e3),
        elements_with(-2.9e7, 100e3),
        elements_with(-2.9e7, 298e3),
        elements_with(-2.9e7, 298e3),
    );
    let (hyperbolic, parabolic) = (elements_with(1.0e6, 300e3), elements_with(0.0, -200e3));
    let cases: [(OutcomeInput, &str); 11] = [
        (
            OutcomeInput {
                lifted_off: false,
                separated: false,
                upper_reached_surface: false,
                seco: None,
                min_periapsis_km: 180.0,
                apoapsis_on_target: false,
            },
            "scrubbed",
        ),
        (
            OutcomeInput {
                lifted_off: true,
                separated: false,
                upper_reached_surface: false,
                seco: None,
                min_periapsis_km: 180.0,
                apoapsis_on_target: false,
            },
            "no_separation",
        ),
        (flying(None, false, false), "seco_not_reached"),
        (flying(None, true, false), "suborbital"),
        (flying(Some(&below_surface), false, false), "suborbital"),
        (flying(Some(&low), false, true), "low_periapsis_orbit"),
        (flying(Some(&off), false, false), "off_target_orbit"),
        (flying(Some(&good), false, true), "orbit"),
        // Reaching the surface after SECO outranks a good orbit at SECO.
        (flying(Some(&good), true, true), "suborbital"),
        // Unbound: hyperbolic, and exactly parabolic (energy zero), whatever the periapsis.
        (flying(Some(&hyperbolic), false, false), "unbound"),
        (flying(Some(&parabolic), false, false), "unbound"),
    ];
    let mut seen = Vec::new();
    for (input, want) in &cases {
        let got = classify_outcome(input);
        assert_eq!(got, *want);
        seen.push(got);
    }
    for code in OUTCOMES {
        assert!(seen.contains(&code), "no case produces {code}");
    }
}

#[test]
fn a_bound_orbit_below_the_minimum_periapsis_is_not_called_suborbital() {
    let mut c = case("small-leo");
    // The nominal true periapsis is about 298 km: ask for more than the orbit has.
    c.limits.min_periapsis_km = 350.0;
    let o = run(&c, 5000);
    assert_eq!(o.verification.outcome, "low_periapsis_orbit");
    assert_eq!(status(&o, "upper.R4_periapsis"), "fail");
    let p = o.verification.insertion.as_ref().unwrap().elements;
    assert!(p.periapsis_alt_m > 0.0 && p.energy_j_kg < 0.0);
}

#[test]
fn a_run_that_ends_before_seco_is_named_so_and_not_suborbital() {
    let nominal = run(&case("small-leo"), 5000);
    let tick_of = |k: &str| {
        nominal
            .verification
            .events
            .iter()
            .find(|e| e.kind == k)
            .unwrap()
            .tick
    };
    // End the simulated time 5 s after the upper-stage ignition: separated, burning, no SECO.
    let end_s = (tick_of("upper_ignition") as f64 * 0.02).ceil() + 5.0;
    let mut c = case("small-leo");
    c.mission.max_duration_s = end_s;
    let o = run(&c, 5000);
    assert_eq!(o.verification.outcome, "seco_not_reached");
    assert!(o.verification.insertion.is_none());
    assert_eq!(status(&o, "mission.R8_orbit_insertion"), "fail");
    // The failing requirement is judged at the end of the simulated time, and its event is the
    // mission's, never one at tick 0.
    let r8 = o
        .verification
        .verdicts
        .iter()
        .find(|v| v.id == "mission.R8_orbit_insertion")
        .unwrap();
    assert_eq!(r8.tick, Some(o.simulation.last_tick));
    let violation = o
        .verification
        .events
        .iter()
        .find(|e| e.kind == "violation" && e.detail["id"] == "mission.R8_orbit_insertion")
        .unwrap();
    assert_eq!(violation.tick, o.simulation.last_tick);
    assert_eq!(violation.entity, vv_ascent::sim::MISSION);
}

#[test]
fn an_orbit_with_another_requirement_failing_carries_requirements_pass_false() {
    // Seed 42 reaches the orbit and misses only the booster recovery zone.
    let o = run(&case("small-leo"), 42);
    assert_eq!(o.verification.outcome, "orbit");
    assert!(!o.verification.requirements_pass);
    assert_eq!(status(&o, "booster.R3_recovery_zone"), "fail");
    let nominal = run(&case("small-leo"), 5000);
    assert_eq!(nominal.verification.outcome, "orbit");
    assert!(nominal.verification.requirements_pass);
}

#[test]
fn the_upper_stage_margin_requirement_has_a_real_minimum() {
    let c = case("small-leo");
    let min = c.limits.min_residual_fraction[1];
    assert!(min > 0.0, "a zero minimum cannot fail");
    // The nominal residual is above it, and raising the minimum above the residual fails R6 with
    // the cause named.
    let o = run(&c, 5000);
    assert_eq!(status(&o, "upper.R6_propellant_margin"), "pass");
    let mut strict = c.clone();
    strict.limits.min_residual_fraction[1] = 0.05;
    let o = run(&strict, 5000);
    let v = o
        .verification
        .verdicts
        .iter()
        .find(|v| v.id == "upper.R6_propellant_margin")
        .unwrap();
    assert_eq!(v.status, "fail");
    assert!(
        v.cause.iter().any(|c| c.contains("below the minimum")),
        "{:?}",
        v.cause
    );
}

/// An event never precedes the start of the entity it is attached to, nor follows its last sample.
fn assert_events_inside_their_entity(o: &Outputs, what: &str) {
    for e in &o.verification.events {
        if let Some(run) = o.simulation.entities.get(e.entity) {
            let (a, b) = (
                run.samples.first().unwrap().tick,
                run.samples.last().unwrap().tick,
            );
            assert!(
                a <= e.tick && e.tick <= b,
                "{what}: {} of the {} at tick {} outside {a}..{b}",
                e.kind,
                run.id,
                e.tick
            );
        } else {
            assert_eq!(e.entity, vv_ascent::sim::MISSION, "{what}: {}", e.kind);
        }
    }
}

#[test]
fn verdict_events_are_attached_inside_the_span_of_their_entity() {
    // Seed 7 fails the booster margin at MECO, which is before the booster exists; seed 42 fails
    // the zone; the heavy payload fails the upper-stage margin and the insertion.
    let mut heavy = case("small-leo");
    heavy.vehicle.payload_kg = 600.0;
    let runs = [
        ("small-leo 7", run(&case("small-leo"), 7)),
        ("small-leo 42", run(&case("small-leo"), 42)),
        ("heavy payload", run(&heavy, 5000)),
        ("medium-leo", run(&case("medium-leo"), 5000)),
    ];
    for (what, o) in &runs {
        assert_events_inside_their_entity(o, what);
    }
    let margin = runs[0]
        .1
        .verification
        .events
        .iter()
        .find(|e| e.kind == "violation" && e.detail["id"] == "booster.R2_propellant_margin");
    let margin = margin.expect("seed 7 fails the booster margin");
    assert_eq!(
        margin.entity,
        vv_ascent::sim::STACK,
        "before the booster existed"
    );
}

#[test]
fn controller_events_carry_the_observation_never_the_true_state() {
    let o = run(&case("small-leo"), 5000);
    let truth = |tick: u64| {
        let s = o.simulation.entities[0]
            .samples
            .iter()
            .find(|s| s.tick == tick)
            .unwrap();
        vv_ascent::dynamics::altitude(s.r)
    };
    let mut checked = 0;
    for e in o
        .verification
        .events
        .iter()
        .filter(|e| e.source == vv_ascent::sim::Source::Controller)
    {
        let d = e.detail.as_object().unwrap();
        for key in ["altitude_m", "downrange_m", "speed_m_s", "mass_kg"] {
            assert!(!d.contains_key(key), "{}: true-state field {key}", e.kind);
        }
        if let Some(obs) = d.get("observed_altitude_m") {
            checked += 1;
            if e.entity == vv_ascent::sim::STACK && e.tick > 0 {
                // The navigation noise (10 m per axis) makes the observation differ from the truth.
                assert_ne!(obs.as_f64().unwrap(), truth(e.tick), "{}", e.kind);
            }
        }
    }
    assert!(
        checked > 5,
        "controller events with an observation: {checked}"
    );
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
            // The states and observations of every entity, apart from the events: a verifier or
            // labelling change must leave this hash alone, so it separates a physics change from one.
            "entities_sha256": sha256_hex(&serde_json::to_vec(&o.trace.entities).unwrap()),
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

/// Not run by default (about a minute in debug): the 200-seed scan behind the residual and
/// non-orbit rates in docs/m17-ascent.md. Run with
/// `cargo test --release --test ascent seed_scan -- --ignored --nocapture`.
#[test]
#[ignore = "documentation scan over 200 seeds per vehicle"]
fn seed_scan_of_the_upper_stage_residual_and_the_outcomes() {
    for (id, text) in vv_ascent::CASES {
        let load = case(id).vehicle.stages[1].propellant_kg;
        let mut residual = Vec::new();
        let mut not_orbit: Vec<(u64, &str)> = Vec::new();
        for seed in 5000..5200u64 {
            let o = compute(text.as_bytes(), seed).unwrap();
            let v = o
                .verification
                .verdicts
                .iter()
                .find(|v| v.id == "upper.R6_propellant_margin")
                .unwrap();
            if let Some(s) = &v.state {
                residual.push(s.propellant_kg / load);
            }
            if o.verification.outcome != "orbit" {
                not_orbit.push((seed, o.verification.outcome));
            }
        }
        residual.sort_by(|a, b| a.total_cmp(b));
        let count = |code: &str| not_orbit.iter().filter(|(_, c)| *c == code).count();
        println!(
            "{id}: residual fraction at SECO over {} seeds: min {:.4}, p5 {:.4}, median {:.4}, max {:.4}; not orbit {} (suborbital {}, low_periapsis_orbit {})",
            residual.len(),
            residual[0],
            residual[residual.len() / 20],
            residual[residual.len() / 2],
            residual[residual.len() - 1],
            not_orbit.len(),
            count("suborbital"),
            count("low_periapsis_orbit"),
        );
    }
}
