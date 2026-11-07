//! Verifier: requirements and invariants per entity and for the mission, judged on the true state
//! of every tick (never on the observations or on the flight software's own estimates). Each
//! failure names the requirement, the tick, the true state, the cause, the expected and the
//! observed condition. The mission outcome (orbit or not) is kept apart from safety (invariants).

use serde::Serialize;

use crate::dynamics::{Aero, Elements, Environment, altitude, density, drag, elements};
use crate::math::Vec2;
use crate::model::{DT, G0, Prepared};
use crate::sim::{BOOSTER, STACK, Sample, SimEvent, Simulation, Source, UPPER, downrange};

pub const VERIFICATION_SCHEMA: &str = "vv-ascent-verification.v1";
pub const DISCLAIMER: &str =
    "exploratory planar point-mass model; not a real vehicle; not validated against flight data";

/// The true state at a tick, as reported with a verdict.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct StateExcerpt {
    pub tick: u64,
    pub t_s: f64,
    pub altitude_m: f64,
    pub downrange_m: f64,
    pub speed_m_s: f64,
    pub radial_velocity_m_s: f64,
    pub mass_kg: f64,
    pub propellant_kg: f64,
    pub throttle: f64,
    pub dynamic_pressure_pa: f64,
    pub sensed_acceleration_g: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Verdict {
    pub id: String,
    pub entity: &'static str,
    pub label: &'static str,
    /// `requirement` (mission) or `invariant` (safety).
    pub category: &'static str,
    /// `pass`, `fail` or `not_evaluated`.
    pub status: &'static str,
    pub expected: String,
    pub observed: String,
    /// Decisive tick: the first violation, else the evaluation instant.
    pub tick: Option<u64>,
    pub state: Option<StateExcerpt>,
    pub cause: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Insertion {
    pub tick: u64,
    pub elements: Elements,
    /// Elements at the end of the coast after SECO; the two-body energy must agree.
    pub end_of_coast: Option<Elements>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Verification {
    pub schema: &'static str,
    /// `orbit`, `off_target_orbit`, `suborbital`, `no_separation` or `scrubbed`.
    pub outcome: &'static str,
    pub requirements_pass: bool,
    pub invariants_pass: bool,
    pub verdicts: Vec<Verdict>,
    pub max_q: Option<StateExcerpt>,
    pub booster_max_q: Option<StateExcerpt>,
    pub insertion: Option<Insertion>,
    pub events: Vec<SimEvent>,
    pub disclaimer: &'static str,
}

fn q_of(s: &Sample) -> f64 {
    0.5 * density(altitude(s.r)) * s.v.dot(s.v)
}

fn sensed_g(s: &Sample, aero: &Aero) -> f64 {
    let d = drag(&Environment::MISSION, aero, s.r, s.v);
    ((s.thrust + d) * (1.0 / s.m)).norm() / G0
}

fn excerpt(s: &Sample, aero: &Aero) -> StateExcerpt {
    StateExcerpt {
        tick: s.tick,
        t_s: s.tick as f64 * DT,
        altitude_m: altitude(s.r),
        downrange_m: downrange(s.r),
        speed_m_s: s.v.norm(),
        radial_velocity_m_s: s.v.dot(s.r.unit()),
        mass_kg: s.m,
        propellant_kg: s.propellant_kg,
        throttle: s.throttle,
        dynamic_pressure_pa: q_of(s),
        sensed_acceleration_g: sensed_g(s, aero),
    }
}

fn event_tick(events: &[SimEvent], entity: usize, kind: &str) -> Option<u64> {
    events
        .iter()
        .find(|e| e.entity == entity && e.kind == kind)
        .map(|e| e.tick)
}

fn sample_at(samples: &[Sample], tick: u64) -> Option<&Sample> {
    samples.iter().find(|s| s.tick == tick)
}

struct Ctx<'a> {
    prep: &'a Prepared,
    sim: &'a Simulation,
    aero: [Aero; 3],
}

fn not_evaluated(
    id: &str,
    entity: &'static str,
    label: &'static str,
    category: &'static str,
    expected: String,
    why: &str,
) -> Verdict {
    Verdict {
        id: id.into(),
        entity,
        label,
        category,
        status: "not_evaluated",
        expected,
        observed: "not reached".into(),
        tick: None,
        state: None,
        cause: vec![why.into()],
    }
}

/// Upper bound over every flown tick of an entity (on-pad ticks excluded).
/// An upper bound checked at every flown tick of one entity.
struct Bound<'a> {
    entity: usize,
    id: &'a str,
    label: &'static str,
    limit: f64,
    unit: &'a str,
}

fn bound_over(
    ctx: &Ctx,
    bound: Bound,
    value: impl Fn(&Sample, &Aero) -> f64,
    cause: impl Fn(&Sample) -> Vec<String>,
) -> Verdict {
    let Bound {
        entity,
        id,
        label,
        limit,
        unit,
    } = bound;
    let run = &ctx.sim.entities[entity];
    let aero = &ctx.aero[entity];
    let flown: Vec<&Sample> = run.samples.iter().filter(|s| !s.on_pad).collect();
    let expected = format!("at most {limit} {unit} at every tick of the {}", run.id);
    if flown.is_empty() {
        return not_evaluated(
            id,
            run.id,
            label,
            "invariant",
            expected,
            "the entity never flew",
        );
    }
    let mut worst = (f64::MIN, flown[0]);
    let mut first = None;
    for s in &flown {
        let x = value(s, aero);
        if x > worst.0 {
            worst = (x, s);
        }
        if x > limit && first.is_none() {
            first = Some(*s);
        }
    }
    let at = first.unwrap_or(worst.1);
    Verdict {
        id: id.into(),
        entity: run.id,
        label,
        category: "invariant",
        status: if first.is_some() { "fail" } else { "pass" },
        expected,
        observed: format!(
            "worst {:.4} {unit} at tick {}{}",
            worst.0,
            worst.1.tick,
            first.map_or(String::new(), |f| format!(
                ", first above the limit at tick {}",
                f.tick
            ))
        ),
        tick: Some(at.tick),
        state: Some(excerpt(at, aero)),
        cause: if first.is_some() {
            cause(at)
        } else {
            Vec::new()
        },
    }
}

fn verdicts(ctx: &Ctx, insertion: &Option<Insertion>) -> Vec<Verdict> {
    let prep = ctx.prep;
    let sim = ctx.sim;
    let l = &prep.limits;
    let ev = &sim.events;
    let s1 = &prep.vehicle.stages[0];
    let s2 = &prep.vehicle.stages[1];
    let mut out = Vec::new();

    // Invariants: dynamic pressure on the stack, sensed acceleration on stack and upper stage.
    let q_limit = l.max_q_pa;
    let q_target = prep.mission.guidance.q_target_pa;
    out.push(bound_over(
        ctx,
        Bound {
            entity: STACK,
            id: "stack.S1_max_dynamic_pressure",
            label: "Maximum dynamic pressure",
            limit: q_limit,
            unit: "Pa",
        },
        |s, _| q_of(s),
        |s| {
            let mut c = vec![format!(
                "true dynamic pressure {:.0} Pa above {q_limit} Pa",
                q_of(s)
            )];
            if s.throttle <= s1.throttle_min + 1e-9 && s.throttle > 0.0 {
                c.push(format!(
                    "throttle already at its minimum {}",
                    s1.throttle_min
                ));
            }
            if q_target >= q_limit {
                c.push(format!(
                    "guidance q target {q_target} Pa is not below the limit"
                ));
            }
            c
        },
    ));
    for (entity, id) in [
        (STACK, "stack.S2_axial_acceleration"),
        (UPPER, "upper.S2_axial_acceleration"),
    ] {
        if entity >= sim.entities.len() {
            out.push(not_evaluated(
                id,
                "upper",
                "Maximum sensed acceleration",
                "invariant",
                format!("at most {} g", l.max_axial_g),
                "no separation",
            ));
            continue;
        }
        let g_target = prep.mission.guidance.axial_g_target;
        out.push(bound_over(
            ctx,
            Bound {
                entity,
                id,
                label: "Maximum sensed acceleration",
                limit: l.max_axial_g,
                unit: "g",
            },
            sensed_g,
            |s| {
                vec![
                    format!("throttle {:.3} with true mass {:.0} kg", s.throttle, s.m),
                    format!("the flight software caps its estimated acceleration at {g_target} g from the nominal vehicle"),
                ]
            },
        ));
    }

    // Separation window, on the stack's true state at the separation tick.
    let sep = event_tick(ev, STACK, "separation");
    let alt_w = l.separation_altitude_km;
    let spd_w = l.separation_speed_m_s;
    let expected = format!(
        "altitude in {} to {} km and speed in {} to {} m/s at separation",
        alt_w[0], alt_w[1], spd_w[0], spd_w[1]
    );
    match sep.and_then(|t| sample_at(&sim.entities[STACK].samples, t)) {
        None => out.push(not_evaluated(
            "stack.R1_separation_window",
            "stack",
            "Separation window",
            "requirement",
            expected,
            "no separation",
        )),
        Some(s) => {
            let alt_km = altitude(s.r) / 1000.0;
            let spd = s.v.norm();
            let mut cause = Vec::new();
            if alt_km < alt_w[0] || alt_km > alt_w[1] {
                cause.push(format!(
                    "altitude {alt_km:.2} km outside {} to {} km",
                    alt_w[0], alt_w[1]
                ));
            }
            if spd < spd_w[0] || spd > spd_w[1] {
                cause.push(format!(
                    "speed {spd:.1} m/s outside {} to {} m/s",
                    spd_w[0], spd_w[1]
                ));
            }
            out.push(Verdict {
                id: "stack.R1_separation_window".into(),
                entity: "stack",
                label: "Separation window",
                category: "requirement",
                status: if cause.is_empty() { "pass" } else { "fail" },
                expected,
                observed: format!("altitude {alt_km:.2} km, speed {spd:.1} m/s"),
                tick: Some(s.tick),
                state: Some(excerpt(s, &ctx.aero[STACK])),
                cause,
            });
        }
    }

    // Booster propellant margin at MECO: true residual minus the declared reserve.
    let reserve1 = s1.propellant_kg * l.min_residual_fraction[0];
    let expected = format!(
        "true residual at MECO at least {reserve1:.1} kg (recovery minimum), no depletion before MECO"
    );
    let meco = event_tick(ev, STACK, "meco");
    let depleted = event_tick(ev, STACK, "propellant_depleted");
    match meco.and_then(|t| sample_at(&sim.entities[STACK].samples, t)) {
        None => out.push(not_evaluated(
            "booster.R2_propellant_margin",
            "booster",
            "Booster propellant margin",
            "requirement",
            expected,
            "no MECO",
        )),
        Some(s) => {
            let margin = s.propellant_kg - reserve1;
            let mut cause = Vec::new();
            if let Some(d) = depleted.filter(|d| *d <= s.tick) {
                cause.push(format!(
                    "first-stage propellant depleted at tick {d}, before the commanded MECO"
                ));
            }
            if margin < 0.0 {
                cause.push(format!("true propellant {:.1} kg below the minimum: dispersions of thrust, Isp or loaded propellant against the nominal flow estimate of the flight software", s.propellant_kg));
            }
            out.push(Verdict {
                id: "booster.R2_propellant_margin".into(),
                entity: "booster",
                label: "Booster propellant margin",
                category: "requirement",
                status: if cause.is_empty() { "pass" } else { "fail" },
                expected,
                observed: format!("residual {:.1} kg, margin {margin:.1} kg", s.propellant_kg),
                tick: Some(s.tick),
                state: Some(excerpt(s, &ctx.aero[STACK])),
                cause,
            });
        }
    }

    // Booster impact inside the declared recovery zone.
    let z = &prep.mission.recovery_zone;
    let expected = format!(
        "impact downrange in {} to {} km",
        z.downrange_min_km, z.downrange_max_km
    );
    match &sim.booster_impact {
        None => out.push(not_evaluated(
            "booster.R3_recovery_zone",
            "booster",
            "Booster impact in the recovery zone",
            "requirement",
            expected,
            if sim.entities.len() > BOOSTER {
                "no impact within the simulated time"
            } else {
                "no separation"
            },
        )),
        Some(imp) => {
            let km = imp.downrange_m / 1000.0;
            let inside = km >= z.downrange_min_km && km <= z.downrange_max_km;
            let s = sample_at(&sim.entities[BOOSTER].samples, imp.tick).expect("impact sample");
            out.push(Verdict {
                id: "booster.R3_recovery_zone".into(),
                entity: "booster",
                label: "Booster impact in the recovery zone",
                category: "requirement",
                status: if inside { "pass" } else { "fail" },
                expected,
                observed: format!("impact at {km:.2} km downrange, {:.1} m/s, t = {:.2} s", imp.speed_m_s, imp.t_s),
                tick: Some(imp.tick),
                state: Some(excerpt(s, &ctx.aero[BOOSTER])),
                cause: if inside {
                    Vec::new()
                } else {
                    vec![
                        format!("ballistic impact {:.1} km {} the zone", if km < z.downrange_min_km { z.downrange_min_km - km } else { km - z.downrange_max_km }, if km < z.downrange_min_km { "short of" } else { "beyond" }),
                        "no boostback or landing burn is modelled: the impact point follows the separation state".into(),
                    ]
                },
            });
        }
    }

    // Upper stage orbit at SECO.
    let target_km = prep.mission.target_altitude_km;
    let reserve2 = s2.propellant_kg * l.min_residual_fraction[1];
    let upper_s = |t: u64| sample_at(&sim.entities[UPPER].samples, t);
    match insertion {
        None => {
            let why = if sim.entities.len() > UPPER {
                "no SECO"
            } else {
                "no separation"
            };
            out.push(not_evaluated(
                "upper.R4_periapsis",
                "upper",
                "Periapsis altitude",
                "requirement",
                format!("periapsis at least {} km", l.min_periapsis_km),
                why,
            ));
            out.push(not_evaluated(
                "upper.R5_apoapsis",
                "upper",
                "Apoapsis on target",
                "requirement",
                format!(
                    "apoapsis within {} km of {target_km} km",
                    l.apoapsis_tolerance_km
                ),
                why,
            ));
            out.push(not_evaluated(
                "upper.R6_propellant_margin",
                "upper",
                "Upper-stage propellant margin",
                "requirement",
                format!(
                    "SECO on the energy criterion with true residual at least {reserve2:.1} kg"
                ),
                why,
            ));
        }
        Some(ins) => {
            let s = upper_s(ins.tick).expect("SECO sample");
            let st = Some(excerpt(s, &ctx.aero[UPPER]));
            let el = &ins.elements;
            let peri_km = el.periapsis_alt_m / 1000.0;
            let ok_p = peri_km >= l.min_periapsis_km;
            out.push(Verdict {
                id: "upper.R4_periapsis".into(),
                entity: "upper",
                label: "Periapsis altitude",
                category: "requirement",
                status: if ok_p { "pass" } else { "fail" },
                expected: format!("periapsis at least {} km at SECO", l.min_periapsis_km),
                observed: format!("periapsis {peri_km:.2} km, eccentricity {:.5}", el.eccentricity),
                tick: Some(ins.tick),
                state: st.clone(),
                cause: if ok_p { Vec::new() } else { vec![format!("true speed {:.1} m/s and radial velocity {:.1} m/s at SECO give a periapsis {:.1} km below the minimum", s.v.norm(), s.v.dot(s.r.unit()), l.min_periapsis_km - peri_km)] },
            });
            let (ok_a, observed, cause) = match el.apoapsis_alt_m {
                None => (
                    false,
                    "unbound trajectory".to_string(),
                    vec!["specific energy not negative".to_string()],
                ),
                Some(a) => {
                    let km = a / 1000.0;
                    let err = km - target_km;
                    let ok = err.abs() <= l.apoapsis_tolerance_km;
                    (
                        ok,
                        format!("apoapsis {km:.2} km, error {err:+.2} km"),
                        if ok {
                            Vec::new()
                        } else {
                            vec![format!(
                                "apoapsis {} the target by {:.2} km",
                                if err > 0.0 { "above" } else { "below" },
                                err.abs()
                            )]
                        },
                    )
                }
            };
            out.push(Verdict {
                id: "upper.R5_apoapsis".into(),
                entity: "upper",
                label: "Apoapsis on target",
                category: "requirement",
                status: if ok_a { "pass" } else { "fail" },
                expected: format!(
                    "apoapsis within {} km of {target_km} km at SECO",
                    l.apoapsis_tolerance_km
                ),
                observed,
                tick: Some(ins.tick),
                state: st.clone(),
                cause,
            });
            let reason = ev
                .iter()
                .find(|e| e.entity == UPPER && e.kind == "seco")
                .and_then(|e| {
                    e.detail
                        .get("reason")
                        .and_then(|r| r.as_str())
                        .map(String::from)
                })
                .unwrap_or_default();
            let margin = s.propellant_kg - reserve2;
            let mut cause = Vec::new();
            if reason != "target energy reached" {
                cause.push(format!("SECO reason: {reason}"));
            }
            if let Some(d) = event_tick(ev, UPPER, "propellant_depleted").filter(|d| *d <= ins.tick)
            {
                cause.push(format!(
                    "upper-stage propellant depleted at tick {d}, before SECO"
                ));
            }
            if margin < 0.0 {
                cause.push(format!(
                    "true residual {:.1} kg below the minimum",
                    s.propellant_kg
                ));
            }
            out.push(Verdict {
                id: "upper.R6_propellant_margin".into(),
                entity: "upper",
                label: "Upper-stage propellant margin",
                category: "requirement",
                status: if cause.is_empty() { "pass" } else { "fail" },
                expected: format!(
                    "SECO on the energy criterion with true residual at least {reserve2:.1} kg"
                ),
                observed: format!(
                    "residual {:.1} kg, margin {margin:.1} kg, SECO reason: {reason}",
                    s.propellant_kg
                ),
                tick: Some(ins.tick),
                state: st,
                cause,
            });
        }
    }

    // Mission: phase sequence, and orbit insertion over the whole flight.
    let order = [
        (STACK, "ignition"),
        (STACK, "liftoff"),
        (STACK, "pitch_kick_start"),
        (STACK, "gravity_turn_start"),
        (STACK, "meco"),
        (STACK, "separation"),
        (UPPER, "upper_ignition"),
        (UPPER, "seco"),
    ];
    let mut prev = 0u64;
    let mut problem = None;
    for (entity, kind) in order {
        match event_tick(ev, entity, kind) {
            None => {
                problem = Some(format!("{kind} did not occur"));
                break;
            }
            Some(t) if t < prev => {
                problem = Some(format!(
                    "{kind} at tick {t} before the previous phase at tick {prev}"
                ));
                break;
            }
            Some(t) => prev = t,
        }
    }
    out.push(Verdict {
        id: "mission.R7_phase_sequence".into(),
        entity: "mission",
        label: "Phase sequence",
        category: "requirement",
        status: if problem.is_none() { "pass" } else { "fail" },
        expected: "ignition, liftoff, pitch kick, gravity turn, MECO, separation, upper ignition, SECO, in this order".into(),
        observed: problem.clone().unwrap_or_else(|| "all phases in order".into()),
        tick: Some(prev),
        state: None,
        cause: problem.into_iter().collect(),
    });
    let upper_ok = |id: &str| out.iter().any(|v| v.id == id && v.status == "pass");
    let reentered = sim.upper_impact.is_some();
    let ok = upper_ok("upper.R4_periapsis") && upper_ok("upper.R5_apoapsis") && !reentered;
    let mut cause = Vec::new();
    for id in ["upper.R4_periapsis", "upper.R5_apoapsis"] {
        if !upper_ok(id) {
            cause.push(format!("{id} not met"));
        }
    }
    if reentered {
        cause.push("the upper stage reached the surface".into());
    }
    out.push(Verdict {
        id: "mission.R8_orbit_insertion".into(),
        entity: "mission",
        label: "Orbit insertion",
        category: "requirement",
        status: if ok { "pass" } else { "fail" },
        expected: format!("upper stage in orbit: periapsis and apoapsis requirements met, no surface contact; target {target_km} km"),
        observed: match insertion {
            Some(i) => format!(
                "periapsis {:.2} km, apoapsis {}",
                i.elements.periapsis_alt_m / 1000.0,
                i.elements.apoapsis_alt_m.map_or("unbound".into(), |a| format!("{:.2} km", a / 1000.0))
            ),
            None => "no SECO".into(),
        },
        tick: insertion.as_ref().map(|i| i.tick),
        state: None,
        cause,
    });
    out
}

fn argmax_q(samples: &[Sample], aero: &Aero) -> Option<StateExcerpt> {
    samples
        .iter()
        .filter(|s| !s.on_pad)
        .max_by(|a, b| q_of(a).total_cmp(&q_of(b)))
        .map(|s| excerpt(s, aero))
}

pub fn verify(prep: &Prepared, sim: &Simulation) -> Verification {
    let aero_of = |i: usize| {
        sim.entities.get(i).map_or(
            Aero {
                area_m2: 1.0,
                cd: 1.0,
            },
            |e| Aero {
                area_m2: e.area_m2,
                cd: e.cd,
            },
        )
    };
    let ctx = Ctx {
        prep,
        sim,
        aero: [aero_of(STACK), aero_of(BOOSTER), aero_of(UPPER)],
    };
    let seco = event_tick(&sim.events, UPPER, "seco");
    let insertion = seco.and_then(|t| {
        let s = sample_at(&sim.entities[UPPER].samples, t)?;
        let last = sim.entities[UPPER].samples.last()?;
        Some(Insertion {
            tick: t,
            elements: elements(s.r, s.v),
            end_of_coast: (last.tick > t && sim.upper_impact.is_none())
                .then(|| elements(last.r, last.v)),
        })
    });
    let verdicts = verdicts(&ctx, &insertion);
    let max_q = argmax_q(&sim.entities[STACK].samples, &ctx.aero[STACK]);
    let booster_max_q = sim
        .entities
        .get(BOOSTER)
        .and_then(|b| argmax_q(&b.samples, &ctx.aero[BOOSTER]));
    let mut events = sim.events.clone();
    let mut seq = events.iter().map(|e| e.seq).max().unwrap_or(0) + 1;
    let mut add = |tick: u64, entity: usize, kind: &str, label: &str, detail: serde_json::Value| {
        events.push(SimEvent {
            tick,
            entity,
            source: Source::Verifier,
            seq,
            kind: kind.into(),
            label: label.into(),
            detail,
        });
        seq += 1;
    };
    if let Some(q) = &max_q {
        add(
            q.tick,
            STACK,
            "max_q",
            "Maximum dynamic pressure (max-Q) of the ascent",
            serde_json::json!({ "q_pa": q.dynamic_pressure_pa, "altitude_m": q.altitude_m }),
        );
    }
    if let Some(i) = &insertion {
        add(
            i.tick,
            UPPER,
            "orbit_insertion_evaluation",
            "Orbit insertion evaluated on the true state at SECO",
            serde_json::json!({
                "periapsis_alt_m": i.elements.periapsis_alt_m,
                "apoapsis_alt_m": i.elements.apoapsis_alt_m,
                "eccentricity": i.elements.eccentricity,
            }),
        );
    }
    for v in verdicts.iter().filter(|v| v.status == "fail") {
        let entity = match v.entity {
            "booster" if sim.entities.len() > BOOSTER => BOOSTER,
            "upper" if sim.entities.len() > UPPER => UPPER,
            _ => STACK,
        };
        add(
            v.tick.unwrap_or(0),
            entity,
            "violation",
            &format!("{} not met", v.label),
            serde_json::json!({ "id": v.id, "category": v.category }),
        );
    }
    events.sort_by(|a, b| {
        (a.tick, a.entity, a.source, a.seq).cmp(&(b.tick, b.entity, b.source, b.seq))
    });
    let req_pass = verdicts
        .iter()
        .filter(|v| v.category == "requirement")
        .all(|v| v.status == "pass");
    let inv_pass = verdicts
        .iter()
        .filter(|v| v.category == "invariant")
        .all(|v| v.status != "fail");
    let status = |id: &str| {
        verdicts
            .iter()
            .find(|v| v.id == id)
            .map(|v| v.status)
            .unwrap_or("not_evaluated")
    };
    let outcome = if event_tick(&sim.events, STACK, "liftoff").is_none() {
        "scrubbed"
    } else if sim.entities.len() <= UPPER {
        "no_separation"
    } else if status("upper.R4_periapsis") != "pass" || sim.upper_impact.is_some() {
        "suborbital"
    } else if status("upper.R5_apoapsis") != "pass" {
        "off_target_orbit"
    } else {
        "orbit"
    };
    Verification {
        schema: VERIFICATION_SCHEMA,
        outcome,
        requirements_pass: req_pass,
        invariants_pass: inv_pass,
        verdicts,
        max_q,
        booster_max_q,
        insertion,
        events,
        disclaimer: DISCLAIMER,
    }
}

/// A position helper the record uses: downrange and altitude of a planar position.
pub fn downrange_altitude(r: Vec2) -> (f64, f64) {
    (downrange(r), altitude(r))
}
