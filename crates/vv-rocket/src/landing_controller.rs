//! Navigation estimator and guidance, throttle and TVC control of the powered landing.
//!
//! Isolation: this module sees observations, its own configuration and its own memory, nothing
//! else. It imports no truth type; `tests/landing.rs` checks this source for such imports.
//! Guidance is shared by the two policies; they differ only in the estimator.
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

/// Navigation: holds the last values (`baseline`) or fuses IMU, GNSS and a gated altimeter
/// (`robust`).
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
            Policy::Baseline => self.update_baseline(nz, s_cm),
            Policy::Robust => self.update_robust(cfg, obs, q, s_cm),
        }
        Estimate {
            position_m: self.p.to_array(),
            velocity_mps: self.v.to_array(),
            altimeter_rejected: self.rejected,
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
        let est = self.nav.update(cfg, obs, q, s_cm);
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
        let h_base = p_base.z;
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
}
