//! Sensors: noisy observations of the true state, with the registered faults.
//!
//! Every stream is drawn whether or not a fault hides the measurement, so a fault never shifts
//! the noise of the other samples. The specific force is that of the actuator output held from the
//! previous step (the observation precedes the actuator update in the step order) with the drag
//! at the current state.

use crate::dynamics::{State, forces, mass_properties};
use crate::landing_model::Sensors;
use crate::landing_truth::base_kinematics;
use crate::landing_types::{Imu, Observation};
use crate::math::{Quat, Vec3};
use crate::model::{Prepared, Segment};
use crate::prng::{SplitMix64, source};

/// Fault effects on the observations in the current step.
#[derive(Clone, Copy, Debug, Default)]
pub struct SensorFaults {
    pub altimeter_bias_m: f64,
    pub altimeter_dropout: bool,
    pub gnss_dropout: bool,
    pub gnss_bias_m: f64,
    pub imu_accel_bias_mps2: f64,
    /// M10 (schema v2) effects; all zero or false for an M9 case.
    pub altimeter_stuck: bool,
    /// Delay of the altimeter in control cycles.
    pub altimeter_delay_cycles: u64,
    pub altimeter_outlier_probability: f64,
    pub gnss_horizontal_bias_m: f64,
    /// Coherent receiver fault: position offset (x and z) and velocity offset (x and z).
    pub gnss_ramp_position_m: f64,
    pub gnss_ramp_velocity_mps: f64,
}

/// Longest altimeter delay in control cycles (0.2 s at 0.02 s).
pub const MAX_DELAY_CYCLES: usize = 10;

#[derive(Clone, Debug)]
pub struct SensorStreams {
    altimeter: SplitMix64,
    gnss_position: SplitMix64,
    gnss_velocity: SplitMix64,
    imu_attitude: SplitMix64,
    imu_rate: SplitMix64,
    imu_acceleration: SplitMix64,
    /// M10: outlier draws, a stream of its own so that no other stream moves.
    altimeter_outlier: SplitMix64,
    /// M10: true nozzle-plane altitude of the last control cycles (newest last), for the delay.
    base_history: [f64; MAX_DELAY_CYCLES + 1],
    history_len: usize,
    /// M10: last value the altimeter delivered, and the value held while it is stuck.
    last_altimeter: Option<f64>,
    stuck_value: Option<f64>,
}

impl SensorStreams {
    pub fn new(seed: u64) -> Self {
        SensorStreams {
            altimeter: SplitMix64::stream(seed, source::ALTIMETER),
            gnss_position: SplitMix64::stream(seed, source::GNSS_POSITION),
            gnss_velocity: SplitMix64::stream(seed, source::GNSS_VELOCITY),
            imu_attitude: SplitMix64::stream(seed, source::IMU_ATTITUDE),
            imu_rate: SplitMix64::stream(seed, source::IMU_RATE),
            imu_acceleration: SplitMix64::stream(seed, source::IMU_ACCELERATION),
            altimeter_outlier: SplitMix64::stream(seed, source::ALTIMETER_OUTLIER),
            base_history: [0.0; MAX_DELAY_CYCLES + 1],
            history_len: 0,
            last_altimeter: None,
            stuck_value: None,
        }
    }

    fn vec3(g: &mut SplitMix64, sigma: f64) -> Vec3 {
        let x = g.noise(sigma);
        let y = g.noise(sigma);
        let z = g.noise(sigma);
        Vec3::new(x, y, z)
    }

    /// Observation of the true state `s`. `held` is the thrust applied in the previous step.
    pub fn observe(
        &mut self,
        truth: &Prepared,
        sensors: &Sensors,
        s: &State,
        held: Option<&Segment>,
        faults: &SensorFaults,
        gnss_cycle: bool,
    ) -> Observation {
        let q = s.q.normalized();
        let alt_noise = self.altimeter.noise(sensors.altimeter_sigma_m);
        let (base, _) = base_kinematics(&truth.vehicle, s);
        // History of the true altitude, shifted every control cycle whatever the faults.
        if self.history_len == self.base_history.len() {
            self.base_history.rotate_left(1);
            self.history_len -= 1;
        }
        self.base_history[self.history_len] = base.z;
        self.history_len += 1;
        let mut outlier = 0.0;
        if faults.altimeter_outlier_probability > 0.0 {
            // Always three draws while the fault is open: occurrence, amplitude, sign.
            let (u, a, sign) = (
                self.altimeter_outlier.uniform(),
                self.altimeter_outlier.uniform(),
                self.altimeter_outlier.uniform(),
            );
            if u < faults.altimeter_outlier_probability {
                let amplitude = (5.0 + 45.0 * a) * sensors.altimeter_sigma_m;
                outlier = if sign < 0.5 { -amplitude } else { amplitude };
            }
        }
        let altimeter_m = if faults.altimeter_dropout {
            None
        } else if faults.altimeter_stuck {
            if self.stuck_value.is_none() {
                self.stuck_value = self.last_altimeter;
            }
            self.stuck_value
        } else {
            let lag = (faults.altimeter_delay_cycles as usize).min(self.history_len - 1);
            let z = self.base_history[self.history_len - 1 - lag];
            Some(z + alt_noise + faults.altimeter_bias_m + outlier)
        };
        if !faults.altimeter_stuck {
            self.stuck_value = None;
        }
        if altimeter_m.is_some() {
            self.last_altimeter = altimeter_m;
        }

        let (mut gnss_position_m, mut gnss_velocity_mps) = (None, None);
        if gnss_cycle {
            let np = Self::vec3(&mut self.gnss_position, sensors.gnss_position_sigma_m);
            let nv = Self::vec3(&mut self.gnss_velocity, sensors.gnss_velocity_sigma_mps);
            if !faults.gnss_dropout {
                let ramp = faults.gnss_ramp_position_m;
                let bias = Vec3::new(
                    faults.gnss_bias_m + faults.gnss_horizontal_bias_m + ramp,
                    faults.gnss_horizontal_bias_m,
                    faults.gnss_bias_m + ramp,
                );
                let dv = faults.gnss_ramp_velocity_mps;
                gnss_position_m = Some((s.r + np + bias).to_array());
                let mut v = s.v + nv;
                if dv != 0.0 {
                    v = v + Vec3::new(dv, 0.0, dv);
                }
                gnss_velocity_mps = Some(v.to_array());
            }
        }

        let d_theta = Self::vec3(&mut self.imu_attitude, sensors.imu_attitude_sigma_rad);
        let dq = Quat::new(1.0, d_theta.x / 2.0, d_theta.y / 2.0, d_theta.z / 2.0).normalized();
        let attitude = q.hamilton(dq);
        let n_rate = Self::vec3(&mut self.imu_rate, sensors.imu_rate_sigma_radps);
        let n_accel = Self::vec3(&mut self.imu_acceleration, sensors.imu_accel_sigma_mps2);
        let f = forces(truth, s, held);
        let mass = mass_properties(&truth.vehicle, s.mp).mass;
        let f_body = q.rotate_inverse((f.thrust + f.drag) * (1.0 / mass));
        let bias = Vec3::new(faults.imu_accel_bias_mps2, 0.0, 0.0);
        Observation {
            altimeter_m,
            gnss_position_m,
            gnss_velocity_mps,
            imu: Imu {
                attitude: attitude.to_array(),
                angular_velocity_radps: (s.w + n_rate).to_array(),
                specific_force_mps2: (f_body + n_accel + bias).to_array(),
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Vehicle;

    fn truth() -> Prepared {
        Prepared {
            dt: 0.01,
            steps: 10,
            record_every: 2,
            stop_at_ground: false,
            gravity: 9.80665,
            atmosphere: None,
            vehicle: Vehicle {
                dry_mass_kg: 1000.0,
                propellant_mass_kg: 0.0,
                dry_cm_station_m: 5.0,
                propellant_cm_station_m: 0.0,
                dry_inertia_kgm2: [100.0, 1000.0, 1000.0],
                propellant_inertia_kgm2: [0.0; 3],
                max_thrust_n: 0.0,
                isp_s: 300.0,
                drag_coefficient: 0.0,
                reference_area_m2: 0.0,
            },
            r0: Vec3::ZERO,
            v0: Vec3::ZERO,
            q0: Quat::IDENTITY,
            w0: Vec3::ZERO,
            segments: Vec::new(),
        }
    }

    fn state() -> State {
        let h = std::f64::consts::FRAC_1_SQRT_2;
        State {
            r: Vec3::new(1.0, 2.0, 100.0),
            v: Vec3::new(0.0, 0.0, -20.0),
            q: Quat::new(h, 0.0, -h, 0.0),
            w: Vec3::ZERO,
            mp: 0.0,
        }
    }

    fn sensors() -> Sensors {
        Sensors::registered()
    }

    #[test]
    fn noise_is_bounded_and_streams_ignore_faults() {
        let t = truth();
        let s = state();
        let mut a = SensorStreams::new(3);
        let mut b = SensorStreams::new(3);
        let clean = SensorFaults::default();
        let faulty = SensorFaults {
            altimeter_dropout: true,
            gnss_dropout: true,
            ..SensorFaults::default()
        };
        let mut worst: f64 = 0.0;
        for k in 0..200 {
            let gnss = k % 5 == 0;
            let o1 = a.observe(&t, &sensors(), &s, None, &clean, gnss);
            let o2 = b.observe(&t, &sensors(), &s, None, &faulty, gnss);
            assert!(o2.altimeter_m.is_none() && o2.gnss_position_m.is_none());
            // The IMU is untouched by the dropout faults: same noise, same values.
            assert_eq!(o1.imu, o2.imu);
            worst = worst.max((o1.altimeter_m.unwrap() - 95.0).abs());
            assert_eq!(o1.gnss_position_m.is_some(), gnss);
        }
        assert!(worst <= 2.0 * 3.0_f64.sqrt() * 0.1 + 1e-12, "{worst}");
    }

    #[test]
    fn faults_add_their_magnitudes() {
        let t = truth();
        let s = state();
        let mut zero = sensors();
        zero.altimeter_sigma_m = 0.0;
        zero.gnss_position_sigma_m = 0.0;
        zero.gnss_velocity_sigma_mps = 0.0;
        zero.imu_accel_sigma_mps2 = 0.0;
        zero.imu_attitude_sigma_rad = 0.0;
        zero.imu_rate_sigma_radps = 0.0;
        let mut g = SensorStreams::new(1);
        let f = SensorFaults {
            altimeter_bias_m: 20.0,
            gnss_bias_m: 7.0,
            imu_accel_bias_mps2: 0.3,
            ..SensorFaults::default()
        };
        let o = g.observe(&t, &zero, &s, None, &f, true);
        assert!((o.altimeter_m.unwrap() - 115.0).abs() < 1e-9);
        let p = o.gnss_position_m.unwrap();
        assert!((p[0] - 8.0).abs() < 1e-12 && p[1] == 2.0 && (p[2] - 107.0).abs() < 1e-12);
        // Free fall with no drag: no specific force except the bias along x_B.
        let sf = o.imu.specific_force_mps2;
        assert!((sf[0] - 0.3).abs() < 1e-12 && sf[1] == 0.0 && sf[2] == 0.0);
        assert!((Quat::from_array(o.imu.attitude).norm() - 1.0).abs() < 1e-15);
    }

    #[test]
    fn specific_force_includes_the_held_thrust() {
        let t = truth();
        let s = state();
        let mut zero = sensors();
        zero.imu_accel_sigma_mps2 = 0.0;
        let seg = Segment {
            start_step: 0,
            end_step: 1,
            thrust_n: 20_000.0,
            direction: Vec3::new(1.0, 0.0, 0.0),
        };
        let mut g = SensorStreams::new(1);
        let o = g.observe(&t, &zero, &s, Some(&seg), &SensorFaults::default(), false);
        assert!((o.imu.specific_force_mps2[0] - 20.0).abs() < 1e-9);
        assert!(o.gnss_position_m.is_none());
    }

    fn quiet() -> Sensors {
        let mut zero = sensors();
        zero.altimeter_sigma_m = 0.0;
        zero.gnss_position_sigma_m = 0.0;
        zero.gnss_velocity_sigma_mps = 0.0;
        zero.imu_accel_sigma_mps2 = 0.0;
        zero.imu_attitude_sigma_rad = 0.0;
        zero.imu_rate_sigma_radps = 0.0;
        zero
    }

    #[test]
    fn m10_stuck_altimeter_repeats_its_last_value_and_releases_after_the_window() {
        let t = truth();
        let mut s = state();
        let mut g = SensorStreams::new(2);
        let clean = SensorFaults::default();
        let stuck = SensorFaults {
            altimeter_stuck: true,
            ..SensorFaults::default()
        };
        let before = g
            .observe(&t, &quiet(), &s, None, &clean, false)
            .altimeter_m
            .unwrap();
        s.r.z -= 10.0;
        let held = g
            .observe(&t, &quiet(), &s, None, &stuck, false)
            .altimeter_m
            .unwrap();
        assert_eq!(held, before, "stuck at the last delivered value");
        s.r.z -= 10.0;
        let after = g
            .observe(&t, &quiet(), &s, None, &clean, false)
            .altimeter_m
            .unwrap();
        assert!(
            (before - after - 20.0).abs() < 1e-9,
            "the window closed: true value again"
        );
    }

    #[test]
    fn m10_delay_reports_an_older_altitude_and_zero_delay_is_the_present() {
        let t = truth();
        let mut s = state();
        let mut g = SensorStreams::new(2);
        let delayed = SensorFaults {
            altimeter_delay_cycles: 3,
            ..SensorFaults::default()
        };
        let mut seen = Vec::new();
        for _ in 0..5 {
            seen.push(
                g.observe(&t, &quiet(), &s, None, &delayed, false)
                    .altimeter_m
                    .unwrap(),
            );
            s.r.z -= 1.0;
        }
        // Cycle 4 reports the altitude of cycle 1; the history is shorter at the start.
        assert!((seen[4] - seen[0] + 1.0).abs() < 1e-9, "{seen:?}");
        let now = g.observe(&t, &quiet(), &s, None, &SensorFaults::default(), false);
        assert!((now.altimeter_m.unwrap() - (seen[0] - 5.0)).abs() < 1e-9);
    }

    #[test]
    fn m10_outliers_draw_from_their_own_stream_and_stay_in_their_amplitude_range() {
        let t = truth();
        let s = state();
        let always = SensorFaults {
            altimeter_outlier_probability: 1.0,
            ..SensorFaults::default()
        };
        let mut a = SensorStreams::new(9);
        let mut b = SensorStreams::new(9);
        for _ in 0..200 {
            let o = a.observe(&t, &sensors(), &s, None, &always, true);
            let c = b.observe(&t, &sensors(), &s, None, &SensorFaults::default(), true);
            let jump = (o.altimeter_m.unwrap() - c.altimeter_m.unwrap()).abs();
            assert!((0.5 - 1e-9..=5.0 + 1e-9).contains(&jump), "{jump}");
            // Every other stream is untouched.
            assert_eq!((o.gnss_position_m, o.imu), (c.gnss_position_m, c.imu));
        }
        let mut c = SensorStreams::new(9);
        let never = SensorFaults {
            altimeter_outlier_probability: 0.0,
            ..SensorFaults::default()
        };
        let mut d = SensorStreams::new(9);
        for _ in 0..20 {
            assert_eq!(
                c.observe(&t, &sensors(), &s, None, &never, false),
                d.observe(&t, &sensors(), &s, None, &SensorFaults::default(), false)
            );
        }
    }

    #[test]
    fn m10_horizontal_bias_and_coherent_ramp_move_only_their_axes() {
        let t = truth();
        let s = state();
        let mut g = SensorStreams::new(1);
        let f = SensorFaults {
            gnss_horizontal_bias_m: 7.0,
            gnss_ramp_position_m: 2.0,
            gnss_ramp_velocity_mps: 0.5,
            ..SensorFaults::default()
        };
        let o = g.observe(&t, &quiet(), &s, None, &f, true);
        let p = o.gnss_position_m.unwrap();
        let v = o.gnss_velocity_mps.unwrap();
        assert_eq!(p, [1.0 + 7.0 + 2.0, 2.0 + 7.0, 100.0 + 2.0]);
        assert_eq!(v, [0.5, 0.0, -20.0 + 0.5]);
    }
}
