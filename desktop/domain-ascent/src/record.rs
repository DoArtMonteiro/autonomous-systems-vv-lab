//! The `vv-run.v2` record of an ascent run, derived from the native outputs of `vv-ascent`.
//! Channels, events and requirements of every entity are in the top-level lists (so every v1 view
//! works); `entities` and `mission` say which belong to whom. The visual block of the case reaches
//! only the scene, never the simulation.

use std::collections::BTreeMap;

use serde_json::{Value, json};
use vv_ascent::model::{Case, TICKS_PER_S};
use vv_ascent::run::{Outputs, TraceEntity, TraceSample};
use vv_platform::contract::*;

use crate::catalog::DOMAIN;

fn channel(
    id: String,
    label: &str,
    unit: &str,
    group: String,
    kind: &str,
    timebase: &str,
    values: Vec<Option<f64>>,
) -> Channel {
    Channel {
        id,
        label: label.into(),
        unit: unit.into(),
        group,
        kind: kind.into(),
        timebase: timebase.into(),
        values,
    }
}

type Pick = fn(&TraceSample) -> Option<f64>;

/// Per-entity channels: (suffix, label, unit, group, kind, value).
const CHANNELS: [(&str, &str, &str, &str, &str, Pick); 11] = [
    (
        "altitude_km",
        "Altitude",
        "km",
        "trajectory",
        "truth",
        |s| Some(s.altitude_m / 1000.0),
    ),
    (
        "downrange_km",
        "Downrange distance over the surface",
        "km",
        "trajectory",
        "truth",
        |s| Some(s.downrange_m / 1000.0),
    ),
    (
        "speed_m_s",
        "Inertial speed",
        "m/s",
        "trajectory",
        "truth",
        |s| Some(s.speed_m_s),
    ),
    (
        "radial_velocity_m_s",
        "Radial (vertical) velocity",
        "m/s",
        "trajectory",
        "truth",
        |s| Some(s.radial_velocity_m_s),
    ),
    (
        "observed_altitude_km",
        "Navigation altitude given to the flight software",
        "km",
        "trajectory",
        "observation",
        |s| s.observed_altitude_m.map(|a| a / 1000.0),
    ),
    (
        "dynamic_pressure_kpa",
        "Dynamic pressure",
        "kPa",
        "loads",
        "truth",
        |s| Some(s.dynamic_pressure_pa / 1000.0),
    ),
    (
        "sensed_acceleration_g",
        "Sensed acceleration",
        "g",
        "loads",
        "truth",
        |s| Some(s.sensed_acceleration_g),
    ),
    ("mass_t", "Mass", "t", "propulsion", "truth", |s| {
        Some(s.mass_kg / 1000.0)
    }),
    (
        "propellant_kg",
        "Propellant on board",
        "kg",
        "propulsion",
        "truth",
        |s| Some(s.propellant_kg),
    ),
    (
        "throttle",
        "Throttle applied",
        "",
        "propulsion",
        "command",
        |s| Some(s.throttle),
    ),
    (
        "t_since_start_s",
        "Time since the start of the hold",
        "s",
        "trajectory",
        "metric",
        |s| Some(s.t_s),
    ),
];

fn severity(kind: &str, source: &str) -> &'static str {
    match kind {
        "violation" => "violation",
        "scrub" | "propellant_depleted" | "guidance_still_burning" => "warning",
        "impact" => "warning",
        "throttle_down" | "throttle_up" => "mode",
        _ if source == "controller" => "mode",
        _ => "info",
    }
}

fn outcome(code: &str) -> Outcome {
    let (label, status, explanation) = match code {
        "orbit" => (
            "Orbit",
            "success",
            "The upper stage reached an orbit with periapsis and apoapsis inside the requirements, judged on the true state at SECO.",
        ),
        "off_target_orbit" => (
            "Orbit off target",
            "partial",
            "The upper stage is in orbit but its apoapsis is outside the tolerance of the target.",
        ),
        "suborbital" => (
            "Suborbital",
            "failure",
            "The periapsis of the true orbit at SECO is below the minimum, or the upper stage reached the surface.",
        ),
        "no_separation" => (
            "No separation",
            "failure",
            "The stack never separated: the upper stage never flew.",
        ),
        _ => (
            "Scrubbed",
            "failure",
            "The flight software scrubbed the mission before or at liftoff.",
        ),
    };
    Outcome {
        code: code.into(),
        label: label.into(),
        status: status.into(),
        explanation: explanation.into(),
    }
}

fn entity_channels(e: &TraceEntity, channels: &mut Vec<Channel>) -> Vec<String> {
    let mut ids = Vec::new();
    for (suffix, label, unit, group, kind, pick) in CHANNELS {
        if suffix == "t_since_start_s" {
            continue;
        }
        let values: Vec<Option<f64>> = e.samples.iter().map(pick).collect();
        if kind == "observation" && values.iter().all(Option::is_none) {
            continue;
        }
        let id = format!("{}_{suffix}", e.id);
        channels.push(channel(
            id.clone(),
            label,
            unit,
            format!("{}: {group}", e.label),
            kind,
            &e.id,
            values,
        ));
        ids.push(id);
    }
    ids
}

fn metric(id: &str, label: &str, value: Option<f64>, unit: &str, group: &str) -> Metric {
    Metric {
        id: id.into(),
        label: label.into(),
        value,
        unit: unit.into(),
        group: group.into(),
    }
}

/// Numeric reading of one requirement for the Experiment Lab: the value the verifier measured, the
/// limit that binds and the margin to it, in one unit, positive when the requirement is met. The
/// text in `requirements` stays the human statement; these numbers let a reader compute margins
/// without parsing it. Only requirements that are one quantity against one bound have numbers:
/// the separation window (two quantities), the phase order and the orbit insertion summary have
/// none, and a requirement whose status disagrees with the sign of its margin (the upper-stage
/// propellant requirement also judges the cutoff reason) is left out rather than shown wrongly.
/// For the two invariants the value is the true state at the decisive tick: the worst tick when the
/// invariant holds, the first tick over the limit when it fails.
struct Reading {
    observed: f64,
    limit: f64,
    margin: f64,
    unit: &'static str,
}

fn reading(verdict: &vv_ascent::verify::Verdict, case: &Case, out: &Outputs) -> Option<Reading> {
    let l = &case.limits;
    let state = verdict.state.as_ref();
    let upper_bound = |observed: f64, limit: f64, unit| Reading {
        observed,
        limit,
        margin: limit - observed,
        unit,
    };
    let lower_bound = |observed: f64, limit: f64, unit| Reading {
        observed,
        limit,
        margin: observed - limit,
        unit,
    };
    let r = match verdict.id.as_str() {
        "stack.S1_max_dynamic_pressure" => {
            upper_bound(state?.dynamic_pressure_pa, l.max_q_pa, "Pa")
        }
        "stack.S2_axial_acceleration" | "upper.S2_axial_acceleration" => {
            upper_bound(state?.sensed_acceleration_g, l.max_axial_g, "g")
        }
        "booster.R2_propellant_margin" => lower_bound(
            state?.propellant_kg,
            case.vehicle.stages.first()?.propellant_kg * l.min_residual_fraction[0],
            "kg",
        ),
        "booster.R3_recovery_zone" => {
            let km = out.simulation.booster_impact.as_ref()?.downrange_m / 1000.0;
            let zone = &case.mission.recovery_zone;
            let (lo, hi) = (km - zone.downrange_min_km, zone.downrange_max_km - km);
            Reading {
                observed: km,
                limit: if lo <= hi {
                    zone.downrange_min_km
                } else {
                    zone.downrange_max_km
                },
                margin: lo.min(hi),
                unit: "km",
            }
        }
        "upper.R4_periapsis" => lower_bound(
            out.verification
                .insertion
                .as_ref()?
                .elements
                .periapsis_alt_m
                / 1000.0,
            l.min_periapsis_km,
            "km",
        ),
        "upper.R5_apoapsis" => {
            let km = out
                .verification
                .insertion
                .as_ref()?
                .elements
                .apoapsis_alt_m?
                / 1000.0;
            upper_bound(
                (km - case.mission.target_altitude_km).abs(),
                l.apoapsis_tolerance_km,
                "km",
            )
        }
        "upper.R6_propellant_margin" => lower_bound(
            state?.propellant_kg,
            case.vehicle.stages.get(1)?.propellant_kg * l.min_residual_fraction[1],
            "kg",
        ),
        _ => return None,
    };
    let agrees = match verdict.status {
        "pass" => r.margin >= 0.0,
        "fail" => r.margin < 0.0,
        _ => false,
    };
    (agrees && r.observed.is_finite() && r.limit.is_finite()).then_some(r)
}

/// The numeric readings as metrics: `requirement_observed.<id>`, `requirement_limit.<id>` and
/// `requirement_margin.<id>`, all in the group `requirement margins`.
fn requirement_metrics(case: &Case, out: &Outputs) -> Vec<Metric> {
    let mut metrics = Vec::new();
    for verdict in &out.verification.verdicts {
        let Some(r) = reading(verdict, case, out) else {
            continue;
        };
        for (kind, word, value) in [
            ("observed", "observed", r.observed),
            ("limit", "limit", r.limit),
            ("margin", "margin to the limit, positive when met", r.margin),
        ] {
            metrics.push(metric(
                &format!("requirement_{kind}.{}", verdict.id),
                &format!("{}: {word}", verdict.label),
                Some(value),
                r.unit,
                "requirement margins",
            ));
        }
    }
    metrics
}

pub fn build(request: &RunRequest, case: &Case, out: &Outputs) -> RunRecord {
    let v = &out.verification;
    let trace = &out.trace;
    let mut timebases = BTreeMap::new();
    let mut channels = Vec::new();
    let mut entity_ids = Vec::new();
    for e in &trace.entities {
        timebases.insert(
            e.id.clone(),
            e.samples.iter().map(|s| s.t_s).collect::<Vec<_>>(),
        );
        entity_ids.push(entity_channels(e, &mut channels));
    }
    // Mission clock: one instant per second from the hold to the end of the last entity, so the
    // time cursor of the Studio can step through the whole flight, not only the stack's history.
    let end_tick = trace.entities.iter().map(|e| e.end_tick).max().unwrap_or(0);
    let mut clock: Vec<f64> = (0..=end_tick / TICKS_PER_S)
        .map(|s| (s * TICKS_PER_S) as f64 * trace.dt_s)
        .collect();
    if !end_tick.is_multiple_of(TICKS_PER_S) {
        clock.push(end_tick as f64 * trace.dt_s);
    }
    timebases.insert("mission".into(), clock);
    // Declared limits as flat channels on the timebase of the entity they bound.
    let limit = |id: &str, label: &str, unit: &str, tb: &str, value: f64| {
        let n = timebases.get(tb).map_or(0, Vec::len);
        channel(
            id.into(),
            label,
            unit,
            "limits".into(),
            "limit",
            tb,
            vec![Some(value); n],
        )
    };
    channels.push(limit(
        "stack_max_q_limit_kpa",
        "Dynamic pressure limit",
        "kPa",
        "stack",
        case.limits.max_q_pa / 1000.0,
    ));
    channels.push(limit(
        "stack_axial_limit_g",
        "Sensed acceleration limit",
        "g",
        "stack",
        case.limits.max_axial_g,
    ));
    if timebases.contains_key("upper") {
        channels.push(limit(
            "upper_axial_limit_g",
            "Sensed acceleration limit",
            "g",
            "upper",
            case.limits.max_axial_g,
        ));
    }
    let events: Vec<Event> = trace
        .events
        .iter()
        .map(|e| {
            let mut detail = e.detail.clone();
            if let Value::Object(m) = &mut detail {
                m.insert("entity".into(), json!(e.entity));
                m.insert("tick".into(), json!(e.tick));
            }
            Event {
                t: e.t_s,
                kind: e.kind.clone(),
                label: e.label.clone(),
                severity: severity(&e.kind, &e.source).into(),
                source: e.source.clone(),
                detail,
            }
        })
        .collect();
    let requirements: Vec<RequirementResult> = v
        .verdicts
        .iter()
        .map(|x| {
            let mut explanation = if x.cause.is_empty() {
                "Judged on the true state.".to_string()
            } else {
                format!("Cause: {}.", x.cause.join("; "))
            };
            if let Some(s) = &x.state {
                explanation.push_str(&format!(
                    " True state at tick {}: altitude {:.2} km, downrange {:.1} km, speed {:.1} m/s, mass {:.0} kg, throttle {:.2}, q {:.0} Pa, {:.2} g.",
                    s.tick, s.altitude_m / 1000.0, s.downrange_m / 1000.0, s.speed_m_s, s.mass_kg, s.throttle, s.dynamic_pressure_pa, s.sensed_acceleration_g
                ));
            }
            RequirementResult {
                id: x.id.clone(),
                label: x.label.into(),
                category: x.category.into(),
                status: x.status.into(),
                expected: x.expected.clone(),
                observed: x.observed.clone(),
                t: x.tick.map(|t| t as f64 * trace.dt_s),
                explanation,
            }
        })
        .collect();
    let entities: Vec<Entity> = trace
        .entities
        .iter()
        .zip(entity_ids)
        .map(|(e, ids)| Entity {
            id: e.id.clone(),
            label: e.label.clone(),
            kind: e.kind.clone(),
            parent: e.parent.clone(),
            timebase: e.id.clone(),
            t_start: e.start_tick as f64 * trace.dt_s,
            t_end: e.end_tick as f64 * trace.dt_s,
            end_reason: e.end_reason.clone(),
            channels: ids,
            events: trace
                .events
                .iter()
                .enumerate()
                .filter(|(_, x)| x.entity == e.id)
                .map(|(i, _)| i as u32)
                .collect(),
            requirements: v
                .verdicts
                .iter()
                .filter(|x| x.entity == e.id)
                .map(|x| x.id.clone())
                .collect(),
        })
        .collect();
    // A requirement of an entity that never existed (no separation) belongs to the mission.
    let listed: Vec<&str> = trace.entities.iter().map(|e| e.id.as_str()).collect();
    let mission_reqs: Vec<String> = v
        .verdicts
        .iter()
        .filter(|x| !listed.contains(&x.entity))
        .map(|x| x.id.clone())
        .collect();
    let ins = v.insertion.as_ref();
    let impact = out.simulation.booster_impact.as_ref();
    let sep = v
        .verdicts
        .iter()
        .find(|x| x.id == "stack.R1_separation_window")
        .and_then(|x| x.state.as_ref());
    let upper_seco = v
        .verdicts
        .iter()
        .find(|x| x.id == "upper.R6_propellant_margin")
        .and_then(|x| x.state.as_ref());
    let mut metrics = vec![
        metric(
            "max_q_kpa",
            "Maximum dynamic pressure of the ascent",
            v.max_q.as_ref().map(|q| q.dynamic_pressure_pa / 1000.0),
            "kPa",
            "stack",
        ),
        metric(
            "max_q_altitude_km",
            "Altitude of max-Q",
            v.max_q.as_ref().map(|q| q.altitude_m / 1000.0),
            "km",
            "stack",
        ),
        metric(
            "separation_altitude_km",
            "Separation altitude",
            sep.map(|s| s.altitude_m / 1000.0),
            "km",
            "stack",
        ),
        metric(
            "separation_speed_m_s",
            "Separation speed",
            sep.map(|s| s.speed_m_s),
            "m/s",
            "stack",
        ),
        metric(
            "booster_impact_downrange_km",
            "Booster impact downrange",
            impact.map(|i| i.downrange_m / 1000.0),
            "km",
            "booster",
        ),
        metric(
            "booster_impact_speed_m_s",
            "Booster impact speed (no landing burn modelled)",
            impact.map(|i| i.speed_m_s),
            "m/s",
            "booster",
        ),
        metric(
            "booster_entry_max_q_kpa",
            "Booster maximum dynamic pressure (descent included)",
            v.booster_max_q
                .as_ref()
                .map(|q| q.dynamic_pressure_pa / 1000.0),
            "kPa",
            "booster",
        ),
        metric(
            "periapsis_km",
            "Periapsis altitude at SECO",
            ins.map(|i| i.elements.periapsis_alt_m / 1000.0),
            "km",
            "upper",
        ),
        metric(
            "apoapsis_km",
            "Apoapsis altitude at SECO",
            ins.and_then(|i| i.elements.apoapsis_alt_m)
                .map(|a| a / 1000.0),
            "km",
            "upper",
        ),
        metric(
            "eccentricity",
            "Eccentricity at SECO",
            ins.map(|i| i.elements.eccentricity),
            "",
            "upper",
        ),
        metric(
            "upper_residual_kg",
            "Upper-stage propellant at SECO",
            upper_seco.map(|s| s.propellant_kg),
            "kg",
            "upper",
        ),
        metric(
            "coast_energy_drift",
            "Relative energy change over the coast after SECO",
            ins.and_then(|i| {
                i.end_of_coast.map(|e| {
                    ((e.energy_j_kg - i.elements.energy_j_kg) / i.elements.energy_j_kg).abs()
                })
            }),
            "",
            "upper",
        ),
    ];
    metrics.extend(requirement_metrics(case, out));
    let scene = json!({
        "kind": "ascent",
        "channels": { "timebase": "mission" },
        "earth_radius_km": vv_ascent::model::R_EARTH / 1000.0,
        "target_altitude_km": case.mission.target_altitude_km,
        "recovery_zone_km": [case.mission.recovery_zone.downrange_min_km, case.mission.recovery_zone.downrange_max_km],
        "limits": { "max_q_kpa": case.limits.max_q_pa / 1000.0, "max_axial_g": case.limits.max_axial_g },
        "entities": trace.entities.iter().map(|e| json!({
            "id": e.id, "label": e.label, "kind": e.kind, "parent": e.parent, "timebase": e.id,
            "altitude": format!("{}_altitude_km", e.id), "downrange": format!("{}_downrange_km", e.id),
        })).collect::<Vec<_>>(),
        "visual": serde_json::to_value(&case.visual).unwrap_or(Value::Null),
        "vehicle_label": case.vehicle.label,
    });
    let n_req = v
        .verdicts
        .iter()
        .filter(|x| x.category == "requirement")
        .count();
    let n_req_pass = v
        .verdicts
        .iter()
        .filter(|x| x.category == "requirement" && x.status == "pass")
        .count();
    RunRecord {
        schema: RECORD_SCHEMA_V2.into(),
        domain: DomainRef {
            id: DOMAIN.into(),
            version: env!("CARGO_PKG_VERSION").into(),
            contract: format!("{CONTRACT_NAME}/{CONTRACT_MAJOR}.{CONTRACT_MINOR}"),
        },
        request: request.clone(),
        provenance: Provenance {
            source_sha256: vv_ascent::source_sha256(),
            simulator: "vv-ascent".into(),
            artifacts: Vec::new(),
            reproduce: vec![format!(
                "cargo run --release --manifest-path crates/vv-ascent/Cargo.toml -- run case.json --seed {} --output out",
                request.seed
            )],
        },
        model_validity: crate::manifest().model_validity,
        outcome: outcome(v.outcome),
        safety: Safety {
            status: if v.invariants_pass { "safe" } else { "unsafe" }.into(),
            class: None,
            explanation: if v.invariants_pass {
                "Dynamic pressure and sensed acceleration stayed within their limits on the true state of every flown tick.".into()
            } else {
                "At least one invariant (dynamic pressure or sensed acceleration) was exceeded on the true state; see the requirements.".into()
            },
        },
        timebases,
        channels,
        events,
        requirements,
        metrics,
        scene,
        notes: vec![
            format!("{}: exploratory, not a real vehicle; order-of-magnitude values only.", case.vehicle.label),
            "Planar 3-DOF point mass over a spherical, non-rotating Earth with inverse-square gravity and an isothermal exponential atmosphere; constant drag coefficient; no winds, attitude dynamics, structural loads or engine transients.".into(),
            "After separation the booster and the upper stage are integrated independently from the same state. The booster is ballistic to impact: no boostback or landing burn is modelled.".into(),
            "The flight software sees only a noisy navigation solution and the nominal vehicle; every requirement is judged on the true state. Mission result and safety invariants are reported separately.".into(),
            format!("{n_req_pass} of {n_req} mission requirements pass."),
            format!("Event order: {}.", trace.event_order),
        ],
        entities: Some(entities),
        mission: Some(MissionResult {
            requirements: mission_reqs,
            event_order: trace.event_order.clone(),
            explanation: outcome(v.outcome).explanation,
        }),
    }
}
