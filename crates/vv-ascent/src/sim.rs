//! The mission simulation: entities, the tick loop, the observation path and the events.
//!
//! Entities: `stack` (both stages and the payload, from the pad to separation), then `booster`
//! (stage 1 after separation, ballistic with drag to impact; no boostback burn is modelled) and
//! `upper` (stage 2 and the payload, to SECO and a coast). The children start from the stack state
//! of the separation tick and are integrated independently from then on.
//!
//! Per tick `k`, entities are processed in index order. For the guided entity (stack, then upper)
//! the navigation solution is drawn and the flight software produces the command held over
//! `[k, k+1]`; then every live entity records its true sample at `k` and takes one RK4 step.
//! Truth events found by a step are stamped `k+1`. Total event order: (tick, entity index, source
//! rank truth < controller < verifier, sequence number of emission).

use serde::Serialize;
use serde_json::{Value, json};

use crate::dynamics::{Aero, Body, Burn, Environment, altitude, rk4_step, thrust};
use crate::guidance::{Command, Directive, Guidance, Mode, Observation};
use crate::math::{Vec2, atan2};
use crate::model::{DT, G0, MAX_TICKS, Prepared, R_EARTH, TICKS_PER_S, TrueStage};
use crate::prng::{SplitMix64, source};

pub const STACK: usize = 0;
pub const BOOSTER: usize = 1;
pub const UPPER: usize = 2;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    Truth,
    Controller,
    Verifier,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct SimEvent {
    pub tick: u64,
    pub entity: usize,
    pub source: Source,
    pub seq: u32,
    pub kind: String,
    pub label: String,
    pub detail: Value,
}

/// True state at a tick and the engine state applied over the following step.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Sample {
    pub tick: u64,
    pub r: Vec2,
    pub v: Vec2,
    pub m: f64,
    pub propellant_kg: f64,
    pub throttle: f64,
    /// Thrust force vector at this state for the applied burn (zero when the engine is off).
    pub thrust: Vec2,
    pub on_pad: bool,
    /// Navigation solution given to the flight software at this tick, if this entity is guided.
    pub observation: Option<Observation>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct EntityRun {
    pub id: &'static str,
    pub label: &'static str,
    pub kind: &'static str,
    pub parent: Option<&'static str>,
    pub area_m2: f64,
    pub cd: f64,
    pub samples: Vec<Sample>,
    pub end_reason: String,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Impact {
    pub tick: u64,
    /// Linear interpolation of the crossing of zero altitude inside the last step.
    pub t_s: f64,
    pub downrange_m: f64,
    pub speed_m_s: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Simulation {
    pub entities: Vec<EntityRun>,
    pub events: Vec<SimEvent>,
    pub booster_impact: Option<Impact>,
    pub upper_impact: Option<Impact>,
    pub last_tick: u64,
}

pub fn downrange(r: Vec2) -> f64 {
    R_EARTH * atan2(r.x, r.z)
}

/// The surface contact inside the step from `prev` (tick `tick`, at or above the surface) to `next`
/// (tick `tick + 1`, below it): the crossing of zero altitude, by linear interpolation of the
/// altitude, the downrange distance and the speed over the step.
pub fn impact_between(tick: u64, prev: &Body, next: &Body) -> Impact {
    let a0 = altitude(prev.r);
    let f = a0 / (a0 - altitude(next.r));
    Impact {
        tick: tick + 1,
        t_s: (tick as f64 + f) * DT,
        downrange_m: downrange(prev.r) + f * (downrange(next.r) - downrange(prev.r)),
        speed_m_s: prev.v.norm() + f * (next.v.norm() - prev.v.norm()),
    }
}

struct Live {
    body: Body,
    fixed_mass: f64,
    propellant: f64,
    engine: Option<TrueStage>,
    aero: Aero,
    cmd: Command,
    on_pad: bool,
    alive: bool,
    depleted: bool,
    prev_vr: f64,
    end_tick: Option<u64>,
}

struct Events {
    list: Vec<SimEvent>,
    seq: u32,
}

impl Events {
    fn push(
        &mut self,
        tick: u64,
        entity: usize,
        source: Source,
        kind: &str,
        label: &str,
        detail: Value,
    ) {
        self.list.push(SimEvent {
            tick,
            entity,
            source,
            seq: self.seq,
            kind: kind.into(),
            label: label.into(),
            detail,
        });
        self.seq += 1;
    }
}

fn burn_of(live: &Live) -> Option<Burn> {
    let e = live.engine.as_ref()?;
    if live.cmd.throttle <= 0.0 || live.propellant <= 0.0 {
        return None;
    }
    let throttle = live.cmd.throttle.clamp(e.throttle_min, e.throttle_max);
    let mdot = (throttle * e.thrust_vac_n / (e.isp_vac_s * G0)).min(live.propellant / DT);
    Some(Burn {
        direction: live.cmd.direction.unit(),
        mdot,
        isp_vac_s: e.isp_vac_s,
        isp_sl_s: e.isp_sl_s,
    })
}

fn applied_throttle(live: &Live, burn: Option<&Burn>) -> f64 {
    match (burn, live.engine.as_ref()) {
        (Some(b), Some(e)) => b.mdot * e.isp_vac_s * G0 / e.thrust_vac_n,
        _ => 0.0,
    }
}

fn state_detail(b: &Body) -> Value {
    json!({
        "altitude_m": altitude(b.r),
        "downrange_m": downrange(b.r),
        "speed_m_s": b.v.norm(),
        "mass_kg": b.m,
    })
}

fn directive_event(ev: &mut Events, tick: u64, entity: usize, d: &Directive, body: &Body) {
    let (kind, label, extra) = match d {
        Directive::ChecksPassed => (
            "prelaunch_checks_passed",
            "Prelaunch checks passed; hold continues",
            json!({}),
        ),
        Directive::Scrub(why) => (
            "scrub",
            "Mission scrubbed by the flight software",
            json!({ "reason": why }),
        ),
        Directive::Ignition => ("ignition", "First-stage ignition commanded", json!({})),
        Directive::PitchKickStart => ("pitch_kick_start", "Pitch kick starts", json!({})),
        Directive::PitchKickEnd => (
            "pitch_kick_end",
            "Pitch kick complete; tilt held",
            json!({}),
        ),
        Directive::GravityTurnStart => (
            "gravity_turn_start",
            "Gravity turn: thrust along the observed velocity",
            json!({}),
        ),
        Directive::ThrottleDown { q_est_pa } => (
            "throttle_down",
            "Throttle down for dynamic pressure",
            json!({ "q_est_pa": q_est_pa }),
        ),
        Directive::ThrottleUp => ("throttle_up", "Throttle back up", json!({})),
        Directive::Meco { propellant_est_kg } => (
            "meco",
            "Main engine cutoff (MECO) commanded",
            json!({ "propellant_est_kg": propellant_est_kg }),
        ),
        Directive::Separate => ("separation", "Stage separation commanded", json!({})),
        Directive::UpperIgnition => (
            "upper_ignition",
            "Upper-stage ignition commanded",
            json!({}),
        ),
        Directive::Seco {
            reason,
            energy_obs_j_kg,
        } => (
            "seco",
            "Second engine cutoff (SECO) commanded",
            json!({ "reason": reason, "energy_obs_j_kg": energy_obs_j_kg }),
        ),
    };
    let mut detail = state_detail(body);
    if let (Value::Object(m), Value::Object(x)) = (&mut detail, extra) {
        m.extend(x);
    }
    ev.push(tick, entity, Source::Controller, kind, label, detail);
}

fn observe(
    body: &Body,
    prep: &Prepared,
    pos: &mut SplitMix64,
    vel: &mut SplitMix64,
) -> Observation {
    let sp = prep.sensors.position_sigma_m;
    let sv = prep.sensors.velocity_sigma_m_s;
    let r = Vec2::new(body.r.x + pos.noise(sp), body.r.z + pos.noise(sp));
    let v = Vec2::new(body.v.x + vel.noise(sv), body.v.z + vel.noise(sv));
    Observation { r, v }
}

fn ticks(s: f64) -> u64 {
    (s * TICKS_PER_S as f64).round() as u64
}

pub fn simulate(prep: &Prepared) -> Simulation {
    let t = &prep.truth;
    let pad = Body {
        r: Vec2::new(0.0, R_EARTH),
        v: Vec2::ZERO,
        m: t[0].dry_mass_kg
            + t[0].propellant_kg
            + t[1].dry_mass_kg
            + t[1].propellant_kg
            + prep.vehicle.payload_kg,
    };
    let mut lives = vec![Live {
        body: pad,
        fixed_mass: pad.m - t[0].propellant_kg,
        propellant: t[0].propellant_kg,
        engine: Some(t[0].clone()),
        aero: Aero {
            area_m2: t[0].reference_area_m2,
            cd: t[0].drag_coefficient,
        },
        cmd: Command::OFF,
        on_pad: true,
        alive: true,
        depleted: false,
        prev_vr: 0.0,
        end_tick: None,
    }];
    let mut runs = vec![EntityRun {
        id: "stack",
        label: "Stack (both stages and payload)",
        kind: "stack",
        parent: None,
        area_m2: t[0].reference_area_m2,
        cd: t[0].drag_coefficient,
        samples: Vec::new(),
        end_reason: String::new(),
    }];
    let env = Environment::MISSION;
    let mut guidance = Guidance::new(&prep.vehicle, &prep.mission);
    let mut guided = STACK;
    let mut guided_tick: Option<u64> = None;
    let mut pos_rng = SplitMix64::stream(prep.seed, source::NAV_POSITION);
    let mut vel_rng = SplitMix64::stream(prep.seed, source::NAV_VELOCITY);
    let mut ev = Events {
        list: Vec::new(),
        seq: 0,
    };
    let mut seco_tick: Option<u64> = None;
    let mut booster_impact = None;
    let mut upper_impact = None;
    let last = ticks(prep.mission.max_duration_s).min(MAX_TICKS);
    ev.push(
        0,
        STACK,
        Source::Controller,
        "prelaunch_hold",
        "Prelaunch hold and checks",
        json!({ "hold_s": prep.mission.hold_s }),
    );
    let mut tick = 0;
    loop {
        let mut i = 0;
        while i < lives.len() {
            if !lives[i].alive {
                i += 1;
                continue;
            }
            let mut observation = None;
            if i == guided && guided_tick != Some(tick) {
                guided_tick = Some(tick);
                let obs = observe(&lives[i].body, prep, &mut pos_rng, &mut vel_rng);
                observation = Some(obs);
                let (cmd, directives) = guidance.step(tick, &obs);
                lives[i].cmd = cmd;
                for d in &directives {
                    directive_event(&mut ev, tick, i, d, &lives[i].body);
                    match d {
                        Directive::Separate => {
                            let s = lives[STACK].body;
                            let booster_mass = t[0].dry_mass_kg + lives[STACK].propellant;
                            lives.push(Live {
                                body: Body {
                                    m: booster_mass,
                                    ..s
                                },
                                fixed_mass: t[0].dry_mass_kg,
                                propellant: lives[STACK].propellant,
                                engine: None,
                                aero: lives[STACK].aero,
                                cmd: Command::OFF,
                                on_pad: false,
                                alive: true,
                                depleted: false,
                                prev_vr: s.v.dot(s.r.unit()),
                                end_tick: None,
                            });
                            let upper_fixed = t[1].dry_mass_kg + prep.vehicle.payload_kg;
                            lives.push(Live {
                                body: Body {
                                    m: upper_fixed + t[1].propellant_kg,
                                    ..s
                                },
                                fixed_mass: upper_fixed,
                                propellant: t[1].propellant_kg,
                                engine: Some(t[1].clone()),
                                aero: Aero {
                                    area_m2: t[1].reference_area_m2,
                                    cd: t[1].drag_coefficient,
                                },
                                cmd: Command::OFF,
                                on_pad: false,
                                alive: true,
                                depleted: false,
                                prev_vr: s.v.dot(s.r.unit()),
                                end_tick: None,
                            });
                            runs.push(EntityRun {
                                id: "booster",
                                label: "Booster (stage 1)",
                                kind: "booster",
                                parent: Some("stack"),
                                area_m2: t[0].reference_area_m2,
                                cd: t[0].drag_coefficient,
                                samples: Vec::new(),
                                end_reason: String::new(),
                            });
                            runs.push(EntityRun {
                                id: "upper",
                                label: "Upper stage and payload",
                                kind: "upper_stage",
                                parent: Some("stack"),
                                area_m2: t[1].reference_area_m2,
                                cd: t[1].drag_coefficient,
                                samples: Vec::new(),
                                end_reason: String::new(),
                            });
                            ev.push(
                                tick,
                                BOOSTER,
                                Source::Truth,
                                "entity_start",
                                "Booster flies on its own",
                                state_detail(&lives[BOOSTER].body),
                            );
                            ev.push(
                                tick,
                                UPPER,
                                Source::Truth,
                                "entity_start",
                                "Upper stage flies on its own",
                                state_detail(&lives[UPPER].body),
                            );
                            guided = UPPER;
                            lives[STACK].alive = false;
                            lives[STACK].end_tick = Some(tick);
                            runs[STACK].end_reason = "separated".into();
                        }
                        Directive::Seco { .. } => seco_tick = Some(tick),
                        Directive::Scrub(_) => {
                            lives[i].alive = false;
                            lives[i].end_tick = Some(tick);
                            runs[i].end_reason = "scrubbed".into();
                        }
                        _ => {}
                    }
                }
            }
            let live = &mut lives[i];
            let burn = burn_of(live);
            let force = thrust(&env, burn.as_ref(), live.body.r);
            runs[i].samples.push(Sample {
                tick,
                r: live.body.r,
                v: live.body.v,
                m: live.body.m,
                propellant_kg: live.propellant,
                throttle: applied_throttle(live, burn.as_ref()),
                thrust: if live.alive { force } else { Vec2::ZERO },
                on_pad: live.on_pad,
                observation,
            });
            if !live.alive {
                i += 1;
                continue;
            }
            if i == UPPER
                && seco_tick.is_some_and(|s| tick >= s + ticks(prep.mission.coast_after_seco_s))
            {
                live.alive = false;
                live.end_tick = Some(tick);
                runs[i].end_reason = "end of coast after SECO".into();
                i += 1;
                continue;
            }
            if tick >= last {
                live.alive = false;
                live.end_tick = Some(tick);
                runs[i].end_reason = "end of simulated time".into();
                i += 1;
                continue;
            }
            // Pad: the vehicle stays clamped while the thrust does not exceed the weight.
            if live.on_pad {
                let weight = live.body.m * crate::model::MU / (R_EARTH * R_EARTH);
                if force.norm() > weight && burn.is_some() {
                    live.on_pad = false;
                    ev.push(
                        tick + 1,
                        i,
                        Source::Truth,
                        "liftoff",
                        "Liftoff: thrust exceeds weight",
                        json!({ "thrust_n": force.norm(), "weight_n": weight }),
                    );
                } else {
                    if let Some(b) = burn {
                        live.propellant = (live.propellant - b.mdot * DT).max(0.0);
                        live.body.m = live.fixed_mass + live.propellant;
                    }
                    i += 1;
                    continue;
                }
            }
            let mut next = rk4_step(&env, &live.aero, burn.as_ref(), &live.body, DT);
            if let Some(b) = burn {
                live.propellant = (live.propellant - b.mdot * DT).max(0.0);
            }
            next.m = live.fixed_mass + live.propellant;
            let prev = live.body;
            live.body = next;
            if live.engine.is_some() && live.propellant <= 0.0 && !live.depleted {
                live.depleted = true;
                ev.push(
                    tick + 1,
                    i,
                    Source::Truth,
                    "propellant_depleted",
                    "Propellant depleted: the engine stops",
                    state_detail(&next),
                );
            }
            let vr = next.v.dot(next.r.unit());
            if live.prev_vr > 0.0 && vr <= 0.0 {
                ev.push(
                    tick + 1,
                    i,
                    Source::Truth,
                    "apogee",
                    "Apogee of the trajectory",
                    state_detail(&next),
                );
            }
            live.prev_vr = vr;
            let alt = altitude(next.r);
            if alt < 0.0 {
                let impact = impact_between(tick, &prev, &next);
                ev.push(tick + 1, i, Source::Truth, "impact", "Surface impact", json!({ "t_s": impact.t_s, "downrange_m": impact.downrange_m, "speed_m_s": impact.speed_m_s }));
                if i == BOOSTER {
                    booster_impact = Some(impact);
                } else if i == UPPER {
                    upper_impact = Some(impact);
                }
                // The entity records its first sub-surface sample, then ends.
                live.alive = false;
                live.end_tick = Some(tick + 1);
                let body = live.body;
                runs[i].samples.push(Sample {
                    tick: tick + 1,
                    r: body.r,
                    v: body.v,
                    m: body.m,
                    propellant_kg: live.propellant,
                    throttle: 0.0,
                    thrust: Vec2::ZERO,
                    on_pad: false,
                    observation: None,
                });
                runs[i].end_reason = "surface impact".into();
            }
            i += 1;
        }
        if lives.iter().all(|l| !l.alive) || tick >= last {
            break;
        }
        tick += 1;
    }
    if guidance.mode == Mode::UpperBurn {
        ev.push(
            tick,
            UPPER,
            Source::Controller,
            "guidance_still_burning",
            "Simulation ended before SECO",
            json!({}),
        );
    }
    let mut events = ev.list;
    events.sort_by(|a, b| {
        (a.tick, a.entity, a.source, a.seq).cmp(&(b.tick, b.entity, b.source, b.seq))
    });
    Simulation {
        entities: runs,
        events,
        booster_impact,
        upper_impact,
        last_tick: tick,
    }
}
