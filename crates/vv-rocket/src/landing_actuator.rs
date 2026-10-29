//! Throttle and TVC actuators: ignition with delay, limits and rates, stuck gimbal, thrust loss,
//! irreversible cutoff and flameout (docs/m9-powered-landing.md). Rates act on every step while
//! the command is held constant over the control cycle.

use crate::landing_types::Command;
use crate::math::Vec3;
use crate::model::G0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Engine {
    Off,
    On,
    Cut,
    Flameout,
}

impl Engine {
    pub fn as_str(self) -> &'static str {
        match self {
            Engine::Off => "off",
            Engine::On => "on",
            Engine::Cut => "cut",
            Engine::Flameout => "flameout",
        }
    }
}

/// Actuator limits and the true engine parameters.
#[derive(Clone, Copy, Debug)]
pub struct ActuatorParams {
    pub dt: f64,
    pub throttle_min: f64,
    pub throttle_max: f64,
    pub throttle_rate_per_s: f64,
    pub gimbal_max_tan: f64,
    pub gimbal_rate_tan_per_s: f64,
    pub max_thrust_n: f64,
    pub isp_s: f64,
}

/// Fault effects active in the step being applied.
#[derive(Clone, Copy, Debug, Default)]
pub struct ActuatorFaults {
    /// Fraction of the thrust lost, in `[0, 1)`.
    pub thrust_loss: f64,
    /// Delay of an ignition commanded now, in steps.
    pub ignition_delay_steps: Option<u64>,
    pub gimbal_stuck: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum ActuatorEvent {
    Ignition { command_step: u64 },
    Cutoff,
    Flameout { needed_kg: f64, available_kg: f64 },
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Applied {
    pub engine: Engine,
    pub throttle: f64,
    pub gimbal_tan: [f64; 2],
    pub thrust_n: f64,
}

impl Applied {
    /// Unit thrust direction in B for a gimbal of tangents `(y, z)`.
    pub fn direction(&self) -> Vec3 {
        let [gy, gz] = self.gimbal_tan;
        let v = Vec3::new(1.0, gy, gz);
        v * (1.0 / v.norm())
    }
}

#[derive(Clone, Debug)]
pub struct Actuator {
    params: ActuatorParams,
    engine: Engine,
    throttle: f64,
    gimbal: [f64; 2],
    pending: Option<(u64, u64)>,
}

impl Actuator {
    pub fn new(params: ActuatorParams) -> Self {
        Actuator {
            params,
            engine: Engine::Off,
            throttle: 0.0,
            gimbal: [0.0, 0.0],
            pending: None,
        }
    }

    pub fn engine(&self) -> Engine {
        self.engine
    }

    /// Step at which the ignition now waiting for its delay was commanded.
    pub fn pending_command_step(&self) -> Option<u64> {
        self.pending.map(|(_, commanded)| commanded)
    }

    /// Applies `cmd` for step `step`, with `propellant_kg` left at its start.
    pub fn apply(
        &mut self,
        step: u64,
        cmd: &Command,
        faults: &ActuatorFaults,
        propellant_kg: f64,
    ) -> (Applied, Vec<ActuatorEvent>) {
        let p = self.params;
        let mut events = Vec::new();
        let mut just_ignited = false;

        if self.engine == Engine::Off {
            if self.pending.is_none() && cmd.throttle > 0.0 {
                match faults.ignition_delay_steps {
                    Some(d) if d > 0 => self.pending = Some((step + d, step)),
                    _ => self.pending = Some((step, step)),
                }
            }
            if let Some((effective, commanded)) = self.pending
                && step >= effective
            {
                self.engine = Engine::On;
                self.throttle = p.throttle_min;
                self.pending = None;
                just_ignited = true;
                events.push(ActuatorEvent::Ignition {
                    command_step: commanded,
                });
            }
        }

        if self.engine == Engine::On {
            if !just_ignited && cmd.throttle <= 0.0 {
                self.engine = Engine::Cut;
                self.throttle = 0.0;
                events.push(ActuatorEvent::Cutoff);
            } else {
                if !just_ignited {
                    let target = cmd.throttle.clamp(p.throttle_min, p.throttle_max);
                    let max_move = p.throttle_rate_per_s * p.dt;
                    self.throttle += (target - self.throttle).clamp(-max_move, max_move);
                }
                if !faults.gimbal_stuck {
                    self.move_gimbal(cmd.gimbal_tan);
                }
            }
        }

        let mut thrust_n = 0.0;
        if self.engine == Engine::On {
            thrust_n = self.throttle * p.max_thrust_n * (1.0 - faults.thrust_loss);
            let needed = thrust_n * p.dt / (p.isp_s * G0);
            if needed > propellant_kg {
                self.engine = Engine::Flameout;
                self.throttle = 0.0;
                thrust_n = 0.0;
                events.push(ActuatorEvent::Flameout {
                    needed_kg: needed,
                    available_kg: propellant_kg,
                });
            }
        }
        let applied = Applied {
            engine: self.engine,
            throttle: if self.engine == Engine::On {
                self.throttle
            } else {
                0.0
            },
            gimbal_tan: self.gimbal,
            thrust_n,
        };
        (applied, events)
    }

    /// Saturates the demand to the deflection limit and moves towards it at the rate limit.
    fn move_gimbal(&mut self, demand: [f64; 2]) {
        let p = &self.params;
        let mag = (demand[0] * demand[0] + demand[1] * demand[1]).sqrt();
        let target = if mag > p.gimbal_max_tan {
            [
                demand[0] * p.gimbal_max_tan / mag,
                demand[1] * p.gimbal_max_tan / mag,
            ]
        } else {
            demand
        };
        let (dy, dz) = (target[0] - self.gimbal[0], target[1] - self.gimbal[1]);
        let dist = (dy * dy + dz * dz).sqrt();
        let max_move = p.gimbal_rate_tan_per_s * p.dt;
        if dist <= max_move {
            self.gimbal = target;
        } else {
            self.gimbal[0] += dy * max_move / dist;
            self.gimbal[1] += dz * max_move / dist;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn params() -> ActuatorParams {
        ActuatorParams {
            dt: 0.01,
            throttle_min: 0.4,
            throttle_max: 1.0,
            throttle_rate_per_s: 1.0,
            gimbal_max_tan: 0.14,
            gimbal_rate_tan_per_s: 0.35,
            max_thrust_n: 1000.0,
            isp_s: 300.0,
        }
    }

    fn cmd(throttle: f64, gy: f64, gz: f64) -> Command {
        Command {
            throttle,
            gimbal_tan: [gy, gz],
        }
    }

    #[test]
    fn ignition_jumps_to_the_minimum_throttle_then_follows_the_rate_limit() {
        let mut a = Actuator::new(params());
        let none = ActuatorFaults::default();
        let (off, ev) = a.apply(0, &cmd(0.0, 0.0, 0.0), &none, 10.0);
        assert_eq!((off.engine, off.thrust_n, ev.len()), (Engine::Off, 0.0, 0));
        let (on, ev) = a.apply(1, &cmd(1.0, 0.0, 0.0), &none, 10.0);
        assert_eq!(ev, [ActuatorEvent::Ignition { command_step: 1 }]);
        assert_eq!(
            (on.engine, on.throttle, on.thrust_n),
            (Engine::On, 0.4, 400.0)
        );
        let (next, ev) = a.apply(2, &cmd(1.0, 0.0, 0.0), &none, 10.0);
        assert!(ev.is_empty());
        assert!((next.throttle - 0.41).abs() < 1e-15);
        // 60 more steps reach the maximum, never faster than 0.01 per step.
        let mut last = next.throttle;
        for k in 3..80 {
            let (x, _) = a.apply(k, &cmd(1.0, 0.0, 0.0), &none, 10.0);
            assert!(x.throttle - last <= 0.01 + 1e-15);
            last = x.throttle;
        }
        assert_eq!(last, 1.0);
        // A demand below the minimum is held at the minimum, not below it.
        let (down, _) = a.apply(80, &cmd(0.05, 0.0, 0.0), &none, 10.0);
        assert!((down.throttle - 0.99).abs() < 1e-12);
    }

    #[test]
    fn gimbal_saturates_and_is_rate_limited() {
        let mut a = Actuator::new(params());
        let none = ActuatorFaults::default();
        a.apply(0, &cmd(1.0, 0.0, 0.0), &none, 10.0);
        let (x, _) = a.apply(1, &cmd(1.0, 1.0, 0.0), &none, 10.0);
        assert!((x.gimbal_tan[0] - 0.0035).abs() < 1e-15, "rate 0.35 per s");
        let mut applied = x;
        for k in 2..60 {
            applied = a.apply(k, &cmd(1.0, 1.0, 1.0), &none, 10.0).0;
        }
        let mag = (applied.gimbal_tan[0].powi(2) + applied.gimbal_tan[1].powi(2)).sqrt();
        assert!((mag - 0.14).abs() < 1e-12, "saturated at {mag}");
        assert!((applied.gimbal_tan[0] - applied.gimbal_tan[1]).abs() < 1e-9);
        let d = applied.direction();
        assert!((d.norm() - 1.0).abs() < 1e-15 && d.x > 0.98);
    }

    #[test]
    fn cutoff_is_irreversible() {
        let mut a = Actuator::new(params());
        let none = ActuatorFaults::default();
        a.apply(0, &cmd(0.8, 0.0, 0.0), &none, 10.0);
        let (cut, ev) = a.apply(1, &cmd(0.0, 0.0, 0.0), &none, 10.0);
        assert_eq!(ev, [ActuatorEvent::Cutoff]);
        assert_eq!(
            (cut.engine, cut.thrust_n, cut.throttle),
            (Engine::Cut, 0.0, 0.0)
        );
        let (again, ev) = a.apply(2, &cmd(1.0, 0.0, 0.0), &none, 10.0);
        assert!(ev.is_empty());
        assert_eq!((again.engine, again.thrust_n), (Engine::Cut, 0.0));
        assert_eq!(a.engine(), Engine::Cut);
    }

    #[test]
    fn flameout_when_the_propellant_does_not_cover_the_step() {
        let mut a = Actuator::new(params());
        let none = ActuatorFaults::default();
        // 400 N at 300 s: 400 * 0.01 / (300 g0) kg per step.
        let per_step = 400.0 * 0.01 / (300.0 * G0);
        let (ok, _) = a.apply(0, &cmd(1.0, 0.0, 0.0), &none, per_step * 1.0001);
        assert_eq!(ok.engine, Engine::On);
        let (out, ev) = a.apply(1, &cmd(1.0, 0.0, 0.0), &none, per_step * 0.5);
        assert!(matches!(ev[..], [ActuatorEvent::Flameout { .. }]));
        assert_eq!((out.engine, out.thrust_n), (Engine::Flameout, 0.0));
        let (still, ev) = a.apply(2, &cmd(1.0, 0.0, 0.0), &none, 10.0);
        assert!(ev.is_empty() && still.thrust_n == 0.0);
    }

    #[test]
    fn faults_delay_ignition_stick_the_gimbal_and_cut_thrust() {
        let mut a = Actuator::new(params());
        let delay = ActuatorFaults {
            ignition_delay_steps: Some(3),
            ..ActuatorFaults::default()
        };
        assert_eq!(
            a.apply(10, &cmd(1.0, 0.0, 0.0), &delay, 10.0).0.engine,
            Engine::Off
        );
        assert_eq!(
            a.apply(11, &cmd(1.0, 0.0, 0.0), &ActuatorFaults::default(), 10.0)
                .0
                .engine,
            Engine::Off,
            "the delay is fixed when the ignition is commanded"
        );
        assert_eq!(
            a.apply(12, &cmd(1.0, 0.0, 0.0), &delay, 10.0).0.engine,
            Engine::Off
        );
        let (on, ev) = a.apply(13, &cmd(1.0, 0.0, 0.0), &delay, 10.0);
        assert_eq!(ev, [ActuatorEvent::Ignition { command_step: 10 }]);
        assert_eq!(on.engine, Engine::On);

        let stuck = ActuatorFaults {
            gimbal_stuck: true,
            thrust_loss: 0.25,
            ..ActuatorFaults::default()
        };
        let before = a
            .apply(14, &cmd(1.0, 0.1, 0.0), &ActuatorFaults::default(), 10.0)
            .0;
        assert!(before.gimbal_tan[0] > 0.0);
        let held = a.apply(15, &cmd(1.0, -0.1, 0.1), &stuck, 10.0).0;
        assert_eq!(
            held.gimbal_tan, before.gimbal_tan,
            "stuck at the start deflection"
        );
        assert!((held.thrust_n - held.throttle * 1000.0 * 0.75).abs() < 1e-9);

        // Stuck before the ignition: the deflection stays at zero.
        let mut b = Actuator::new(params());
        let s = b.apply(0, &cmd(1.0, 0.1, 0.1), &stuck, 10.0).0;
        assert_eq!(s.gimbal_tan, [0.0, 0.0]);
    }
}
