//! Navigation estimator and guidance, throttle and TVC control of the powered landing.
//!
//! Isolation: this module sees observations, its own configuration and its own memory, nothing
//! else. It imports no truth type; `tests/landing.rs` checks this source for such imports.
//! Guidance is shared by the policies; `baseline` and `robust` differ only in the estimator, and
//! `guarded` and `baseline_guarded` add the M9.1 rules (docs/m9-powered-landing.md).
//! Arithmetic: `+ - * /` and `sqrt` only.

use crate::landing_types::{Command, ControllerConfig, Estimate, Observation, Policy};
use crate::math::{Quat, Vec3};
use crate::model::G0;

const X_B: Vec3 = Vec3::new(1.0, 0.0, 0.0);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    Coast,
    Burn,
    Cut,
}

/// Navigation: holds the last values (`baseline`, `baseline_guarded`) or fuses IMU, GNSS and a
/// gated altimeter (`robust`, `guarded`).
#[derive(Clone, Debug)]
struct Navigator {
    p: Vec3,
    v: Vec3,
    ready: bool,
    last_altimeter: Option<f64>,
    last_gnss_p: Option<Vec3>,
    last_gnss_v: Option<Vec3>,
    exceed_cycles: u32,
    rejected: bool,
}

impl Navigator {
    fn new() -> Self {
        Navigator {
            p: Vec3::ZERO,
            v: Vec3::ZERO,
            ready: false,
            last_altimeter: None,
            last_gnss_p: None,
            last_gnss_v: None,
            exceed_cycles: 0,
            rejected: false,
        }
    }

    fn update(
        &mut self,
        cfg: &ControllerConfig,
        obs: &Observation,
        q: Quat,
        s_cm: f64,
    ) -> Estimate {
        if let Some(a) = obs.altimeter_m {
            self.last_altimeter = Some(a);
        }
        if let Some(p) = obs.gnss_position_m {
            self.last_gnss_p = Some(Vec3::from_array(p));
        }
        if let Some(v) = obs.gnss_velocity_mps {
            self.last_gnss_v = Some(Vec3::from_array(v));
        }
        let nz = q.rotate(X_B).z;
        match cfg.policy {
            Policy::Baseline | Policy::BaselineGuarded => self.update_baseline(nz, s_cm),
            Policy::Robust | Policy::Guarded => self.update_robust(cfg, obs, q, s_cm),
        }
        Estimate {
            position_m: self.p.to_array(),
            velocity_mps: self.v.to_array(),
            altimeter_rejected: self.rejected,
            // The altimeter has been rejected for the registered number of consecutive cycles
            // (and no residual has been accepted since): the same condition as rule 1.
            sensor_disagreement: cfg.policy.handles_disagreement().then_some(self.rejected),
            ascent_abort: None,
        }
    }

    fn update_baseline(&mut self, nz: f64, s_cm: f64) {
        let (Some(gp), Some(gv)) = (self.last_gnss_p, self.last_gnss_v) else {
            return;
        };
        // The altimeter measures the nozzle plane `p_z - s_cm * x_B,z`; hold its last value.
        let z = match self.last_altimeter {
            Some(alt) => alt + s_cm * nz,
            None => gp.z,
        };
        self.p = Vec3::new(gp.x, gp.y, z);
        self.v = gv;
        self.ready = true;
    }

    fn update_robust(&mut self, cfg: &ControllerConfig, obs: &Observation, q: Quat, s_cm: f64) {
        let g = &cfg.gains;
        if !self.ready {
            // Initialise on the first GNSS fix.
            if let (Some(gp), Some(gv)) = (obs.gnss_position_m, obs.gnss_velocity_mps) {
                self.p = Vec3::from_array(gp);
                self.v = Vec3::from_array(gv);
                self.ready = true;
            }
            return;
        }
        let dt = cfg.dt_s * cfg.control_period_steps as f64;
        // Propagate with the measured specific force and the known gravity.
        let f_n = q.rotate(Vec3::from_array(obs.imu.specific_force_mps2));
        let a = f_n + Vec3::new(0.0, 0.0, -cfg.gravity_mps2);
        self.p = self.p + self.v * dt + a * (0.5 * dt * dt);
        self.v = self.v + a * dt;
        if let (Some(gp), Some(gv)) = (obs.gnss_position_m, obs.gnss_velocity_mps) {
            let gp = Vec3::from_array(gp);
            let gv = Vec3::from_array(gv);
            self.p = self.p + (gp - self.p) * g.gnss_position_gain;
            self.v = self.v + (gv - self.v) * g.gnss_velocity_gain;
        }
        if let Some(alt) = obs.altimeter_m {
            let nz = q.rotate(X_B).z;
            let residual = alt - (self.p.z - s_cm * nz);
            if residual.abs() > g.altimeter_residual_threshold_m {
                self.exceed_cycles = self.exceed_cycles.saturating_add(1);
                if self.exceed_cycles >= g.altimeter_rejection_cycles {
                    self.rejected = true;
                }
            } else {
                self.exceed_cycles = 0;
                self.rejected = false;
                self.p.z += g.altimeter_position_gain * residual;
                self.v.z += g.altimeter_velocity_gain * residual / dt;
            }
        }
    }
}

#[derive(Clone, Debug)]
pub struct Controller {
    cfg: ControllerConfig,
    nav: Navigator,
    phase: Phase,
    /// The controller's own model of the applied throttle (0 before ignition and after cutoff).
    u_model: f64,
    /// Nominal propellant mass left, integrated from the modelled throttle.
    propellant_est: f64,
    /// Consecutive control cycles with the estimated vertical velocity above the rule 2 limit.
    rising_cycles: u32,
    /// Rule 2 cut the engine.
    ascent_abort: bool,
}

impl Controller {
    pub fn new(cfg: ControllerConfig) -> Self {
        let propellant_est = cfg.propellant_mass_kg;
        Controller {
            cfg,
            nav: Navigator::new(),
            phase: Phase::Coast,
            u_model: 0.0,
            propellant_est,
            rising_cycles: 0,
            ascent_abort: false,
        }
    }

    pub fn config(&self) -> &ControllerConfig {
        &self.cfg
    }

    /// One control cycle: observations in, command and navigation estimate out.
    pub fn step(&mut self, obs: &Observation) -> (Command, Estimate) {
        let cfg = &self.cfg;
        let g = &cfg.gains;
        let q = Quat::from_array(obs.imu.attitude).normalized();
        let prop = self.propellant_est.max(0.0);
        let m_hat = cfg.dry_mass_kg + prop;
        let s_cm =
            (cfg.dry_mass_kg * cfg.dry_cm_station_m + prop * cfg.propellant_cm_station_m) / m_hat;
        let mut est = self.nav.update(cfg, obs, q, s_cm);
        est.ascent_abort = cfg.policy.cuts_on_ascent().then_some(self.ascent_abort);
        if !self.nav.ready || self.phase == Phase::Cut {
            return (Command::OFF, est);
        }

        let w = Vec3::from_array(obs.imu.angular_velocity_radps);
        let n = q.rotate(X_B);
        let p = self.nav.p;
        let r_e = Vec3::new(-s_cm, 0.0, 0.0);
        // Guidance acts on the nozzle plane, the point whose contact is judged.
        let p_base = p + q.rotate(r_e);
        let v_base = self.nav.v + q.rotate(w.cross(r_e));
        // Rule 1 (`guarded`): while the altimeter and the estimator disagree, guidance (and only
        // guidance: the estimator state is untouched) reads the lower of the two altitudes. A
        // cycle without an altimeter sample uses the estimator's altitude.
        let h_base = match obs.altimeter_m {
            Some(alt) if cfg.policy.handles_disagreement() && self.nav.rejected => {
                p_base.z.min(alt)
            }
            _ => p_base.z,
        };
        let vz = v_base.z;
        let vt = -cfg.target_vertical_speed_mps; // positive descent speed at contact
        let h_eff = h_base.max(g.altitude_floor_m);
        let descent = -vz;
        let a_req = if descent > vt {
            (vz * vz - vt * vt) / (2.0 * h_eff)
        } else {
            0.0
        };

        if self.phase == Phase::Coast {
            let f_req = cfg.gravity_mps2 + a_req;
            let f_ign = g.ignition_fraction * cfg.max_thrust_n / m_hat;
            if descent > vt && f_req >= f_ign {
                self.phase = Phase::Burn;
            } else {
                return (Command::OFF, est);
            }
        } else if vz > 0.0 && h_base < g.cutoff_altitude_m {
            self.phase = Phase::Cut;
            self.u_model = 0.0;
            return (Command::OFF, est);
        }

        // Rule 2: a sustained estimated rise with the engine lit cuts it, irreversibly.
        if cfg.policy.cuts_on_ascent() {
            if self.nav.v.z > g.ascent_abort_vz_mps {
                self.rising_cycles = self.rising_cycles.saturating_add(1);
            } else {
                self.rising_cycles = 0;
            }
            let period_s = cfg.dt_s * cfg.control_period_steps as f64;
            let needed = (g.ascent_abort_time_s / period_s).round().max(1.0) as u32;
            if self.rising_cycles >= needed {
                self.phase = Phase::Cut;
                self.u_model = 0.0;
                self.ascent_abort = true;
                est.ascent_abort = Some(true);
                return (Command::OFF, est);
            }
        }

        // Vertical specific force wanted from thrust plus drag, limited well inside S3.
        let f_cap = cfg.axial_load_limit_mps2 - g.axial_load_margin_g * G0;
        let f_des = (cfg.gravity_mps2 + a_req).min(f_cap);

        // Lateral law: zero position and velocity error at the end of the descent.
        let rel = Vec3::new(
            p_base.x - cfg.pad_position_m[0],
            p_base.y - cfg.pad_position_m[1],
            0.0,
        );
        let vel = Vec3::new(v_base.x, v_base.y, 0.0);
        let t_raw = 2.0 * h_base.max(0.0) / (descent.max(0.0) + vt);
        // Close to the ground the position term fades out: only the lateral velocity is damped.
        let fade = (t_raw / g.lateral_fade_time_s).min(1.0);
        // Velocity wanted at this offset: proportional to it, never above the braking curve.
        let want = |offset: f64| {
            let limit = (2.0 * g.lateral_braking_mps2 * offset.abs()).sqrt();
            let v = g.lateral_position_gain * fade * offset;
            -v.clamp(-limit, limit)
        };
        let v_des = Vec3::new(want(rel.x), want(rel.y), 0.0);
        let a_lat = (v_des - vel) * g.lateral_velocity_gain;
        // Guard the division when gravity is zero and no deceleration is needed.
        let mut tilt = a_lat * (1.0 / f_des.max(1.0));
        let cap = g
            .tilt_max_tan
            .min(g.tilt_floor_tan + g.tilt_per_m * h_base.max(0.0));
        let tilt_norm = tilt.norm();
        if tilt_norm > cap {
            tilt = tilt * (cap / tilt_norm);
        }
        let x_des = Vec3::new(tilt.x, tilt.y, 1.0);
        let x_des = x_des * (1.0 / x_des.norm());

        // Throttle: correct the modelled throttle by the measured vertical specific force error.
        let f_meas_z = q.rotate(Vec3::from_array(obs.imu.specific_force_mps2)).z;
        let cos_tilt = n.z.max(0.5);
        let u_prev = self.u_model;
        let u_cmd =
            u_prev + g.throttle_gain * (m_hat / cfg.max_thrust_n) * (f_des - f_meas_z) / cos_tilt;
        let u_cmd = u_cmd.clamp(cfg.throttle_min, cfg.throttle_max);

        // The engine jumps to the minimum throttle at ignition, then follows the rate limit.
        let start = if u_prev == 0.0 {
            cfg.throttle_min
        } else {
            u_prev
        };
        let step = cfg.throttle_rate_per_s * cfg.dt_s * cfg.control_period_steps as f64;
        self.u_model = u_cmd
            .clamp(start - step, start + step)
            .max(cfg.throttle_min);
        let dt_c = cfg.dt_s * cfg.control_period_steps as f64;
        self.propellant_est -= self.u_model * cfg.max_thrust_n / (cfg.isp_s * G0) * dt_c;

        // Attitude: tilt `x_B` towards `x_des` with a PD law on `x_B x x_des` and the gyros.
        let b = q.rotate_inverse(x_des);
        let (e_y, e_z) = (-b.z, b.y);
        let schedule = g.attitude_reference_throttle / start.max(cfg.throttle_min);
        let g_z = (g.attitude_kp * e_y - g.attitude_kd * w.y) * schedule;
        let g_y = -(g.attitude_kp * e_z - g.attitude_kd * w.z) * schedule;
        let mag = (g_y * g_y + g_z * g_z).sqrt();
        let (g_y, g_z) = if mag > cfg.gimbal_max_tan {
            (
                g_y * cfg.gimbal_max_tan / mag,
                g_z * cfg.gimbal_max_tan / mag,
            )
        } else {
            (g_y, g_z)
        };
        (
            Command {
                throttle: u_cmd,
                gimbal_tan: [g_y, g_z],
            },
            est,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::landing_types::{Gains, Imu};

    fn gains() -> Gains {
        Gains {
            ignition_fraction: 0.75,
            throttle_gain: 0.8,
            axial_load_margin_g: 0.1,
            altitude_floor_m: 0.5,
            attitude_kp: 0.3,
            attitude_kd: 0.5,
            attitude_reference_throttle: 0.6,
            tilt_max_tan: 0.12,
            tilt_floor_tan: 0.02,
            tilt_per_m: 0.004,
            lateral_velocity_gain: 0.3,
            lateral_position_gain: 0.1,
            lateral_braking_mps2: 0.5,
            lateral_fade_time_s: 3.0,
            cutoff_altitude_m: 15.0,
            gnss_position_gain: 0.15,
            gnss_velocity_gain: 0.25,
            altimeter_position_gain: 0.1,
            altimeter_velocity_gain: 0.004,
            altimeter_residual_threshold_m: 3.0,
            altimeter_rejection_cycles: 3,
            ascent_abort_vz_mps: 1.0,
            ascent_abort_time_s: 1.0,
        }
    }

    fn config(policy: Policy) -> ControllerConfig {
        ControllerConfig {
            policy,
            dt_s: 0.01,
            control_period_steps: 2,
            gravity_mps2: 9.80665,
            dry_mass_kg: 22_000.0,
            propellant_mass_kg: 8_000.0,
            dry_cm_station_m: 16.0,
            propellant_cm_station_m: 9.0,
            isp_s: 282.0,
            max_thrust_n: 845_000.0,
            throttle_min: 0.4,
            throttle_max: 1.0,
            throttle_rate_per_s: 1.0,
            gimbal_max_tan: 0.140_540_834_7,
            gimbal_rate_tan_per_s: 0.35,
            pad_position_m: [0.0, 0.0],
            target_vertical_speed_mps: -1.5,
            axial_load_limit_mps2: 3.0 * G0,
            gains: gains(),
        }
    }

    /// Upright vehicle: x_B along +z_N.
    fn upright_imu(specific_force_x: f64) -> Imu {
        let h = std::f64::consts::FRAC_1_SQRT_2;
        Imu {
            attitude: [h, 0.0, -h, 0.0],
            angular_velocity_radps: [0.0; 3],
            specific_force_mps2: [specific_force_x, 0.0, 0.0],
        }
    }

    /// Nozzle altitude `h` (s_cm is 14.13 m with the full load) and vertical speed `vz`.
    fn obs(h: f64, vz: f64, x: f64, fx: f64) -> Observation {
        Observation {
            altimeter_m: Some(h),
            gnss_position_m: Some([x, 0.0, h + 14.133_333_333_333_333]),
            gnss_velocity_mps: Some([0.0, 0.0, vz]),
            imu: upright_imu(fx),
        }
    }

    #[test]
    fn it_stays_off_until_it_has_a_fix_and_until_the_deceleration_is_needed() {
        for policy in [Policy::Baseline, Policy::Robust] {
            let mut c = Controller::new(config(policy));
            let no_fix = Observation {
                altimeter_m: Some(3000.0),
                gnss_position_m: None,
                gnss_velocity_mps: None,
                imu: upright_imu(0.0),
            };
            assert_eq!(c.step(&no_fix).0, Command::OFF);
            // 3000 m up at 200 m/s: far from the point where the burn is needed.
            assert_eq!(c.step(&obs(3000.0, -200.0, 0.0, 0.0)).0, Command::OFF);
            // 1000 m at 200 m/s needs about 20 m/s^2 of deceleration: ignite.
            let mut c = Controller::new(config(policy));
            let (cmd, est) = c.step(&obs(1000.0, -200.0, 0.0, 0.0));
            assert!(cmd.throttle >= 0.4, "{cmd:?}");
            assert!((est.velocity_mps[2] + 200.0).abs() < 1.0);
        }
    }

    #[test]
    fn it_cuts_the_engine_when_rising_near_the_ground_and_stays_off() {
        let mut c = Controller::new(config(Policy::Baseline));
        let (cmd, _) = c.step(&obs(300.0, -100.0, 0.0, 0.0));
        assert!(cmd.throttle >= 0.4);
        let (cmd, _) = c.step(&obs(10.0, 0.5, 0.0, 15.0));
        assert_eq!(cmd, Command::OFF);
        let (cmd, _) = c.step(&obs(10.0, -5.0, 0.0, 15.0));
        assert_eq!(cmd, Command::OFF, "no relight");
    }

    #[test]
    fn the_throttle_corrects_the_measured_specific_force_error() {
        let mut low = Controller::new(config(Policy::Baseline));
        let mut high = Controller::new(config(Policy::Baseline));
        // Same situation; one vehicle measures less specific force than wanted, the other more.
        let a = low.step(&obs(300.0, -100.0, 0.0, 0.0)).0.throttle;
        let b = high.step(&obs(300.0, -100.0, 0.0, 0.0)).0.throttle;
        assert_eq!(a, b);
        let a = low.step(&obs(290.0, -99.0, 0.0, 15.0)).0.throttle;
        let b = high.step(&obs(290.0, -99.0, 0.0, 35.0)).0.throttle;
        assert!(a > b, "{a} {b}");
    }

    #[test]
    fn lateral_offset_tilts_the_thrust_towards_the_pad() {
        let mut c = Controller::new(config(Policy::Baseline));
        c.step(&obs(300.0, -100.0, 0.0, 0.0));
        // 20 m east of the pad: the gimbal must push the nose west, i.e. towards -x_N.
        let (cmd, _) = c.step(&obs(290.0, -99.0, 20.0, 20.0));
        assert!(cmd.gimbal_tan[1].abs() > 1e-4 || cmd.gimbal_tan[0].abs() > 1e-4);
        let mag = (cmd.gimbal_tan[0].powi(2) + cmd.gimbal_tan[1].powi(2)).sqrt();
        assert!(mag <= 0.140_540_834_7 + 1e-12);
    }

    #[test]
    fn the_robust_estimator_gates_the_altimeter_after_consecutive_outliers() {
        let mut c = Controller::new(config(Policy::Robust));
        let free_fall = |h: f64, bias: f64| Observation {
            altimeter_m: Some(h + bias),
            gnss_position_m: None,
            gnss_velocity_mps: None,
            imu: upright_imu(0.0),
        };
        c.step(&obs(2000.0, 0.0, 0.0, 0.0)); // initialise from the GNSS fix
        let mut flags = Vec::new();
        for _ in 0..4 {
            // The IMU says "free fall": the estimate falls with it; the altimeter reads 30 m high.
            flags.push(c.step(&free_fall(2000.0 - 0.0, 30.0)).1.altimeter_rejected);
        }
        assert_eq!(flags, [false, false, true, true], "N = 3 cycles");
        // A good measurement clears the flag.
        let est = c.step(&free_fall(2000.0, 0.0)).1;
        assert!(!est.altimeter_rejected);
    }

    #[test]
    fn the_baseline_holds_the_last_measurements() {
        let mut c = Controller::new(config(Policy::Baseline));
        let first = c.step(&obs(2000.0, -100.0, 5.0, 0.0)).1;
        let held = c
            .step(&Observation {
                altimeter_m: None,
                gnss_position_m: None,
                gnss_velocity_mps: None,
                imu: upright_imu(0.0),
            })
            .1;
        assert_eq!(first.position_m, held.position_m);
        assert_eq!(first.velocity_mps, held.velocity_mps);
    }

    /// Specific force along `x_B` that holds the vehicle at constant velocity (thrust cancels g).
    const HOVER_FX: f64 = 9.806_65;
    /// Offset between the centre of mass and the nozzle plane with the full load.
    const S_CM: f64 = 14.133_333_333_333_333;

    fn ignited(policy: Policy) -> Controller {
        let mut c = Controller::new(config(policy));
        assert!(c.step(&obs(1000.0, -200.0, 0.0, 0.0)).0.throttle >= 0.4);
        c
    }

    #[test]
    fn rule_2_cuts_a_sustained_rise_above_15_m_and_only_with_the_guarded_policies() {
        for policy in [Policy::BaselineGuarded, Policy::Guarded] {
            let mut c = ignited(policy);
            let (mut first_above, mut cut_at) = (None, None);
            for cycle in 0..150 {
                // 1000 m up and rising at 3 m/s with the specific force of a hover: the 15 m rule
                // cannot act.
                let (cmd, est) = c.step(&obs(1000.0, 3.0, 0.0, HOVER_FX));
                if est.velocity_mps[2] > 1.0 {
                    first_above.get_or_insert(cycle);
                }
                if cmd == Command::OFF {
                    cut_at.get_or_insert(cycle);
                    assert_eq!(est.ascent_abort, Some(true), "{policy:?} cycle {cycle}");
                } else {
                    assert_eq!(est.ascent_abort, Some(false), "{policy:?} cycle {cycle}");
                    assert!(cut_at.is_none(), "no relight");
                }
            }
            // 1 s is 50 control cycles above +1 m/s: the cut is at the 50th of them.
            let first = first_above.unwrap();
            assert_eq!(cut_at, Some(first + 49), "{policy:?}");
        }
        // `baseline` has neither the rule nor the flags: it keeps burning, and its estimate has no
        // `ascent_abort` or `sensor_disagreement`.
        let mut c = ignited(Policy::Baseline);
        for _ in 0..150 {
            let (cmd, est) = c.step(&obs(1000.0, 3.0, 0.0, HOVER_FX));
            assert!(cmd.throttle >= 0.4);
            assert_eq!((est.ascent_abort, est.sensor_disagreement), (None, None));
        }
    }

    #[test]
    fn rule_2_needs_the_rise_to_be_continuous_and_above_the_limit() {
        let mut c = ignited(Policy::BaselineGuarded);
        // 49 cycles rising, one cycle at +0.5 m/s resets the count, 49 more: still burning.
        for vz in std::iter::repeat_n(3.0, 49)
            .chain([0.5])
            .chain(std::iter::repeat_n(3.0, 49))
        {
            let (cmd, est) = c.step(&obs(1000.0, vz, 0.0, HOVER_FX));
            assert!(cmd.throttle >= 0.4);
            assert_eq!(est.ascent_abort, Some(false));
        }
        // The 50th consecutive cycle cuts it.
        let (cmd, est) = c.step(&obs(1000.0, 3.0, 0.0, HOVER_FX));
        assert_eq!((cmd, est.ascent_abort), (Command::OFF, Some(true)));
        // Exactly +1 m/s is not above the limit.
        let mut c = ignited(Policy::BaselineGuarded);
        for _ in 0..200 {
            assert!(
                c.step(&obs(1000.0, 1.0, 0.0, HOVER_FX)).0.throttle >= 0.4,
                "+1 m/s is not above +1 m/s"
            );
        }
    }

    #[test]
    fn rule_2_does_not_count_before_the_ignition() {
        let mut c = Controller::new(config(Policy::BaselineGuarded));
        // Rising and high: no ignition, so there is no burn to abort.
        for _ in 0..200 {
            let (cmd, est) = c.step(&obs(3000.0, 5.0, 0.0, 0.0));
            assert_eq!((cmd, est.ascent_abort), (Command::OFF, Some(false)));
        }
    }

    /// A `guarded` and a `robust` controller (altimeter rejection after 5 cycles, as registered)
    /// fed the same observations, in free fall from a GNSS fix at `start_m` and -100 m/s. The altimeter
    /// reads `bias` metres away from the estimator's own nozzle altitude (both estimators are the
    /// same, so the two policies see the same disagreement), or nothing.
    struct Lockstep {
        guarded: Controller,
        robust: Controller,
        last: Estimate,
    }

    type Pair = (Command, Estimate, Command, Estimate);

    impl Lockstep {
        fn new(start_m: f64) -> (Self, Pair) {
            let mut cfg = config(Policy::Guarded);
            cfg.gains.altimeter_rejection_cycles = 5;
            let mut robust_cfg = cfg.clone();
            robust_cfg.policy = Policy::Robust;
            let mut pair = Lockstep {
                guarded: Controller::new(cfg),
                robust: Controller::new(robust_cfg),
                last: Estimate {
                    position_m: [0.0; 3],
                    velocity_mps: [0.0; 3],
                    altimeter_rejected: false,
                    sensor_disagreement: None,
                    ascent_abort: None,
                },
            };
            let start = obs(start_m, -100.0, 0.0, 0.0);
            let (g, ge) = pair.guarded.step(&start);
            let (r, re) = pair.robust.step(&start);
            pair.last = re;
            (pair, (g, ge, r, re))
        }

        fn feed(&mut self, bias: Option<f64>) -> Pair {
            let base = self.last.position_m[2] - S_CM + self.last.velocity_mps[2] * 0.02;
            let o = Observation {
                altimeter_m: bias.map(|b| base + b),
                gnss_position_m: None,
                gnss_velocity_mps: None,
                imu: upright_imu(0.0),
            };
            let (g, ge) = self.guarded.step(&o);
            let (r, re) = self.robust.step(&o);
            self.last = re;
            (g, ge, r, re)
        }
    }

    #[test]
    fn rule_1_declares_the_disagreement_after_5_cycles_and_guidance_reads_the_lower_altitude() {
        // The altimeter reads 40 m below the estimator. After 5 consecutive cycles the lower
        // altitude (the altimeter's) drives the guidance: `guarded` lights the engine where
        // `robust`, which keeps the estimator's altitude, does not yet.
        let (mut pair, first) = Lockstep::new(470.0);
        let mut run = vec![first];
        for _ in 0..8 {
            run.push(pair.feed(Some(-40.0)));
        }
        // Cycle 0 is the fix; cycles 1 to 5 are the five consecutive outliers.
        let flags: Vec<_> = run.iter().map(|r| r.1.sensor_disagreement).collect();
        assert_eq!(flags[..5], [Some(false); 5]);
        assert_eq!(flags[5..], [Some(true); 4]);
        // Before the declaration both policies command the same thing.
        for r in &run[..5] {
            assert_eq!(r.0, r.2);
        }
        let r = &run[5];
        assert!(r.0.throttle >= 0.4, "guarded lights the engine: {:?}", r.0);
        assert_eq!(r.2, Command::OFF, "robust keeps the estimator altitude");
        // Selecting an altitude for the guidance never changes the estimator.
        for r in &run {
            assert_eq!(r.1.position_m, r.3.position_m);
            assert_eq!(r.1.velocity_mps, r.3.velocity_mps);
            assert_eq!(r.1.altimeter_rejected, r.3.altimeter_rejected);
            assert_eq!((r.3.sensor_disagreement, r.3.ascent_abort), (None, None));
            assert_eq!(r.1.ascent_abort, Some(false));
        }
    }

    #[test]
    fn rule_1_keeps_the_estimator_altitude_when_the_altimeter_reads_high() {
        // The altimeter 40 m above: the lower altitude is the estimator's, so `guarded`
        // commands exactly what `robust` does, although the disagreement is declared.
        let (mut pair, first) = Lockstep::new(470.0);
        let mut run = vec![first];
        for _ in 0..12 {
            run.push(pair.feed(Some(40.0)));
        }
        assert!(run.iter().any(|r| r.1.sensor_disagreement == Some(true)));
        for r in &run {
            assert_eq!(r.0, r.2);
        }
    }

    #[test]
    fn rule_1_uses_the_estimator_altitude_without_a_sample_and_exits_like_robust() {
        let (mut pair, _) = Lockstep::new(520.0);
        // 8 outlying samples (the altimeter 40 m below the estimator): the disagreement is
        // declared from the 5th; the engine is still off.
        for _ in 0..8 {
            pair.feed(Some(-40.0));
        }
        // No altimeter sample for 15 cycles: the guidance reads the estimator's altitude, so
        // `guarded` and `robust` command exactly the same (they ignite on the same cycle) while
        // the disagreement stays declared.
        for _ in 0..15 {
            let (g, ge, r, _) = pair.feed(None);
            assert_eq!(ge.sensor_disagreement, Some(true));
            assert_eq!(g, r);
        }
        // A consistent altimeter sample ends the disagreement, as it ends the robust rejection.
        let (g, ge, r, re) = pair.feed(Some(0.0));
        assert_eq!(
            (ge.sensor_disagreement, re.altimeter_rejected),
            (Some(false), false)
        );
        assert_eq!(g, r);
        // The same history with the altimeter sample kept: the lower altitude lights the engine.
        let (mut sampled, _) = Lockstep::new(520.0);
        let lit = (0..23)
            .map(|_| sampled.feed(Some(-40.0)))
            .position(|(g, ..)| g != Command::OFF);
        assert!(
            lit.is_some(),
            "the lower altitude lights the engine within 23 cycles"
        );
    }

    #[test]
    fn the_new_estimate_flags_are_serialised_only_for_the_policies_that_produce_them() {
        let est = |policy| {
            let mut c = Controller::new(config(policy));
            let v = serde_json::to_value(c.step(&obs(1000.0, -200.0, 0.0, 0.0)).1).unwrap();
            let mut keys: Vec<String> = v.as_object().unwrap().keys().cloned().collect();
            keys.sort();
            keys
        };
        let old = ["altimeter_rejected", "position_m", "velocity_mps"];
        assert_eq!(est(Policy::Baseline), old);
        assert_eq!(est(Policy::Robust), old);
        let mut guarded = old.to_vec();
        guarded.extend(["ascent_abort", "sensor_disagreement"]);
        guarded.sort_unstable();
        assert_eq!(est(Policy::Guarded), guarded);
        let mut partial = old.to_vec();
        partial.push("ascent_abort");
        partial.sort_unstable();
        assert_eq!(est(Policy::BaselineGuarded), partial);
    }
}
