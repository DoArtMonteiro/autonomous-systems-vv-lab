//! Flight software model: sequencing, first-stage pitch programme and upper-stage closed-loop
//! guidance. It sees only the noisy navigation solution (`Observation`) and the mission
//! configuration (nominal vehicle, mission and guidance settings): never the true state, the true
//! (dispersed) vehicle or the verifier. Its propellant and mass are its own estimates from the
//! nominal mass flow and the throttle it commanded.
//!
//! Laws, all explainable in one line each:
//! - prelaunch: hold `hold_s`; checks on the observation (at rest, on the pad) and on the nominal
//!   configuration (liftoff thrust-to-weight, first-stage burn longer than the pitch programme);
//! - vertical rise until `kick_time_s` after ignition;
//! - pitch kick: the thrust tilts linearly from the local vertical to `kick_angle_deg` downrange over
//!   `kick_duration_s` and holds that tilt until `gravity_turn_start_s`;
//! - gravity turn: thrust along the observed velocity;
//! - first-stage throttle: proportional cut while the estimated dynamic pressure exceeds
//!   `q_target_pa`, and a cap so the estimated thrust acceleration stays below `axial_g_target`;
//! - MECO when the estimated first-stage propellant reaches its reserve; separation
//!   `separation_delay_s` later; upper-stage ignition `ignition_delay_s` after separation;
//! - upper stage, explicit radial guidance (the linear-acceleration law of classic lunar-module
//!   ascent guidance): time to go `T` from the rocket equation for the speed still missing to the
//!   target energy (floored at `min_time_to_go_s`); the net radial acceleration `A + B t` that brings
//!   the radius to `r_t` with zero radial rate at `T` gives
//!   `B = -12 (r_t - r - vr T + vr T / 2) / T^3`, `A = -(vr + B T^2 / 2) / T`; the thrust supplies
//!   `A + g(r) - vt^2 / r` radially, so its elevation is `sin e = clamp(that / a_thrust,
//!   +-max_sin_elevation)` and the rest of the thrust is horizontal;
//! - SECO on energy: when the observed specific orbital energy reaches that of the circular orbit at
//!   the target altitude (throttle at its minimum once the velocity to go is below `terminal_dv_m_s`),
//!   or when the estimated upper-stage propellant reaches its reserve.

use serde::Serialize;

use crate::dynamics::density;
use crate::math::{Vec2, exp, sin_cos};
use crate::model::{
    DT, G0, MU, MissionDef, R_EARTH, SCALE_HEIGHT, StageDef, TICKS_PER_S, VehicleDef,
};

/// What the flight software receives each tick: a navigation solution with seeded noise.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Observation {
    pub r: Vec2,
    pub v: Vec2,
}

/// Engine command held over the next step. `throttle == 0` means the engine is off.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Command {
    pub throttle: f64,
    pub direction: Vec2,
}

impl Command {
    pub const OFF: Command = Command {
        throttle: 0.0,
        direction: Vec2::ZERO,
    };
}

/// Discrete decisions of the flight software; the simulation turns them into events and acts.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub enum Directive {
    ChecksPassed,
    Scrub(String),
    Ignition,
    PitchKickStart,
    PitchKickEnd,
    GravityTurnStart,
    ThrottleDown {
        q_est_pa: f64,
    },
    ThrottleUp,
    Meco {
        propellant_est_kg: f64,
    },
    Separate,
    UpperIgnition,
    Seco {
        reason: &'static str,
        energy_obs_j_kg: f64,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Mode {
    Hold,
    Scrubbed,
    FirstStage,
    StackCoast,
    UpperCoast,
    UpperBurn,
    Orbit,
}

pub struct Guidance {
    vehicle: VehicleDef,
    mission: MissionDef,
    pub mode: Mode,
    ignition_tick: u64,
    meco_tick: u64,
    separation_tick: u64,
    propellant_est: [f64; 2],
    throttled: bool,
    kick_started: bool,
    kick_ended: bool,
    turn_started: bool,
}

/// After this time from ignition the flight software cuts the engine if the navigation speed is
/// still below `NO_LIFTOFF_SPEED_M_S` (the vehicle has not left the pad).
pub const NO_LIFTOFF_S: f64 = 3.0;
pub const NO_LIFTOFF_SPEED_M_S: f64 = 2.0;

fn ticks(s: f64) -> u64 {
    (s * TICKS_PER_S as f64).round() as u64
}

fn mdot_max(s: &StageDef) -> f64 {
    s.thrust_vac_n / (s.isp_vac_s * G0)
}

/// Unit vector along the local horizontal, downrange, at `r`.
pub fn horizontal(r: Vec2) -> Vec2 {
    let u = r.unit();
    Vec2::new(u.z, -u.x)
}

impl Guidance {
    pub fn new(vehicle: &VehicleDef, mission: &MissionDef) -> Self {
        Guidance {
            vehicle: vehicle.clone(),
            mission: mission.clone(),
            mode: Mode::Hold,
            ignition_tick: 0,
            meco_tick: 0,
            separation_tick: 0,
            propellant_est: [
                vehicle.stages[0].propellant_kg,
                vehicle.stages[1].propellant_kg,
            ],
            throttled: false,
            kick_started: false,
            kick_ended: false,
            turn_started: false,
        }
    }

    fn stage(&self, i: usize) -> &StageDef {
        &self.vehicle.stages[i]
    }

    fn upper_mass_est(&self) -> f64 {
        self.stage(1).dry_mass_kg + self.propellant_est[1] + self.vehicle.payload_kg
    }

    fn stack_mass_est(&self) -> f64 {
        self.stage(0).dry_mass_kg + self.propellant_est[0] + self.upper_mass_est()
    }

    /// Nominal checks of the configuration, independent of the observation.
    fn configuration_checks(&self) -> Result<(), String> {
        let s = self.stage(0);
        let thrust_sl = mdot_max(s) * s.throttle_max * G0 * s.isp_sl_s;
        let twr = thrust_sl / (self.stack_mass_est() * G0);
        if twr < 1.1 {
            return Err(format!(
                "nominal liftoff thrust-to-weight {twr:.3} below 1.1"
            ));
        }
        let usable = s.propellant_kg * (1.0 - s.reserve_fraction);
        let burn_s = usable / (mdot_max(s) * s.throttle_max);
        if burn_s <= self.mission.gravity_turn_start_s {
            return Err(format!(
                "nominal first-stage burn {burn_s:.1} s ends before the gravity turn starts"
            ));
        }
        Ok(())
    }

    /// One guidance cycle at `tick` on the observation of the guided entity (the stack, then the
    /// upper stage). Returns the engine command held over the next step and the decisions taken.
    pub fn step(&mut self, tick: u64, obs: &Observation) -> (Command, Vec<Directive>) {
        let mut out = Vec::new();
        let cmd = match self.mode {
            Mode::Hold => {
                if tick == 0 {
                    let at_rest = obs.v.norm() < 1.0;
                    let on_pad = (obs.r.norm() - R_EARTH).abs() < 100.0;
                    match self.configuration_checks() {
                        Ok(()) if at_rest && on_pad => out.push(Directive::ChecksPassed),
                        Ok(()) => {
                            out.push(Directive::Scrub(
                                "navigation does not show the vehicle at rest on the pad".into(),
                            ));
                            self.mode = Mode::Scrubbed;
                        }
                        Err(e) => {
                            out.push(Directive::Scrub(e));
                            self.mode = Mode::Scrubbed;
                        }
                    }
                }
                if self.mode == Mode::Hold && tick >= ticks(self.mission.hold_s) {
                    self.mode = Mode::FirstStage;
                    self.ignition_tick = tick;
                    out.push(Directive::Ignition);
                    self.first_stage(tick, obs, &mut out)
                } else {
                    Command::OFF
                }
            }
            Mode::Scrubbed => Command::OFF,
            Mode::FirstStage => self.first_stage(tick, obs, &mut out),
            Mode::StackCoast => {
                if tick >= self.meco_tick + ticks(self.mission.separation_delay_s) {
                    self.mode = Mode::UpperCoast;
                    self.separation_tick = tick;
                    out.push(Directive::Separate);
                }
                Command::OFF
            }
            Mode::UpperCoast => {
                if tick >= self.separation_tick + ticks(self.mission.ignition_delay_s) {
                    self.mode = Mode::UpperBurn;
                    out.push(Directive::UpperIgnition);
                    self.upper_stage(obs, &mut out)
                } else {
                    Command::OFF
                }
            }
            Mode::UpperBurn => self.upper_stage(obs, &mut out),
            Mode::Orbit => Command::OFF,
        };
        (cmd, out)
    }

    fn first_stage(&mut self, tick: u64, obs: &Observation, out: &mut Vec<Directive>) -> Command {
        let s = self.stage(0).clone();
        let reserve = s.propellant_kg * s.reserve_fraction;
        if self.propellant_est[0] <= reserve {
            self.mode = Mode::StackCoast;
            self.meco_tick = tick;
            out.push(Directive::Meco {
                propellant_est_kg: self.propellant_est[0],
            });
            return Command::OFF;
        }
        let m = &self.mission;
        let t = (tick - self.ignition_tick) as f64 * DT;
        if t >= NO_LIFTOFF_S && obs.v.norm() < NO_LIFTOFF_SPEED_M_S {
            self.mode = Mode::Scrubbed;
            out.push(Directive::Scrub(format!(
                "navigation speed below {NO_LIFTOFF_SPEED_M_S} m/s {NO_LIFTOFF_S} s after ignition: no liftoff, engine cut"
            )));
            return Command::OFF;
        }
        let up = obs.r.unit();
        let east = horizontal(obs.r);
        let kick_end = m.kick_time_s + m.kick_duration_s;
        let direction = if t < m.kick_time_s {
            up
        } else if t < m.gravity_turn_start_s {
            if !self.kick_started {
                self.kick_started = true;
                out.push(Directive::PitchKickStart);
            }
            let frac = ((t - m.kick_time_s) / m.kick_duration_s).min(1.0);
            if frac >= 1.0 && !self.kick_ended {
                self.kick_ended = true;
                out.push(Directive::PitchKickEnd);
            }
            let tilt = frac * m.kick_angle_deg * std::f64::consts::PI / 180.0;
            let (sn, cs) = sin_cos(tilt);
            up * cs + east * sn
        } else {
            if !self.kick_ended && t >= kick_end {
                self.kick_ended = true;
                out.push(Directive::PitchKickEnd);
            }
            if !self.turn_started {
                self.turn_started = true;
                out.push(Directive::GravityTurnStart);
            }
            obs.v.unit()
        };
        let alt = obs.r.norm() - R_EARTH;
        let q_est = 0.5 * density(alt) * obs.v.dot(obs.v);
        let g = &m.guidance;
        let mut throttle = s.throttle_max;
        if q_est > g.q_target_pa {
            throttle -= 4.0 * (q_est - g.q_target_pa) / g.q_target_pa;
        }
        let pr = exp(-alt.max(0.0) / SCALE_HEIGHT);
        let full = mdot_max(&s) * G0 * (s.isp_vac_s - (s.isp_vac_s - s.isp_sl_s) * pr);
        let cap = g.axial_g_target * G0 * self.stack_mass_est() / full;
        throttle = throttle.min(cap).clamp(s.throttle_min, s.throttle_max);
        let bucket = throttle < s.throttle_max - 1e-9 && q_est > g.q_target_pa;
        if bucket && !self.throttled {
            self.throttled = true;
            out.push(Directive::ThrottleDown { q_est_pa: q_est });
        } else if !bucket && self.throttled {
            self.throttled = false;
            out.push(Directive::ThrottleUp);
        }
        self.propellant_est[0] -= throttle * mdot_max(&s) * DT;
        Command {
            throttle,
            direction,
        }
    }

    fn upper_stage(&mut self, obs: &Observation, out: &mut Vec<Directive>) -> Command {
        let s = self.stage(1).clone();
        let g = self.mission.guidance.clone();
        let reserve = s.propellant_kg * s.reserve_fraction;
        let r = obs.r.norm();
        let energy = 0.5 * obs.v.dot(obs.v) - MU / r;
        let r_target = R_EARTH + self.mission.target_altitude_km * 1000.0;
        let energy_target = -MU / (2.0 * r_target);
        let mass = self.upper_mass_est();
        // Speed increase that gives the target energy at the current radius.
        let speed = obs.v.norm();
        let v_need = (2.0 * (energy_target + MU / r)).max(0.0).sqrt();
        let dv_to_go = v_need - speed;
        // Time to go at full throttle from the rocket equation (nominal vehicle).
        let ve = s.isp_vac_s * G0;
        let t_go = mass / (s.throttle_max * mdot_max(&s)) * (1.0 - exp(-dv_to_go.max(0.0) / ve));
        let mut throttle = s.throttle_max;
        if dv_to_go < g.terminal_dv_m_s {
            throttle = s.throttle_min;
        }
        let cap = g.axial_g_target * G0 * mass / s.thrust_vac_n;
        throttle = throttle.min(cap).clamp(s.throttle_min, s.throttle_max);
        let a_thrust = throttle * s.thrust_vac_n / mass;
        // Cut when the energy is reached, or when half a step of thrust would overshoot it.
        if dv_to_go <= 0.5 * a_thrust * DT {
            self.mode = Mode::Orbit;
            out.push(Directive::Seco {
                reason: "target energy reached",
                energy_obs_j_kg: energy,
            });
            return Command::OFF;
        }
        if self.propellant_est[1] <= reserve {
            self.mode = Mode::Orbit;
            out.push(Directive::Seco {
                reason: "estimated propellant reserve reached before the target energy",
                energy_obs_j_kg: energy,
            });
            return Command::OFF;
        }
        let up = obs.r.unit();
        let east = horizontal(obs.r);
        let vr = obs.v.dot(up);
        let vt = obs.v.dot(east);
        // Linear net radial acceleration A + B t reaching r_t with zero radial rate at T.
        let t = t_go.max(g.min_time_to_go_s);
        let b = -12.0 * (r_target - r - vr * t + vr * t / 2.0) / (t * t * t);
        let a = -(vr + b * t * t / 2.0) / t;
        let a_radial = a + MU / (r * r) - vt * vt / r;
        let sin_e = (a_radial / a_thrust).clamp(-g.max_sin_elevation, g.max_sin_elevation);
        let cos_e = (1.0 - sin_e * sin_e).sqrt();
        self.propellant_est[1] -= throttle * mdot_max(&s) * DT;
        Command {
            throttle,
            direction: up * sin_e + east * cos_e,
        }
    }
}
