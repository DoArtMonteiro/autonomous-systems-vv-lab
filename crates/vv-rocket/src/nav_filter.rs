//! M10 navigation: estimator, fault detection, group health, integrity, modes and the
//! independent safety monitor (docs/m10-resilient-navigation.md, sections 6 to 8).
//!
//! Isolation: like `landing_controller`, this module sees observations, its configuration and
//! its own memory only; `tests/landing.rs` checks its imports and identifiers.
//! Arithmetic: `+ - * /` and `sqrt` only; the chi-square limits are constants.
//!
//! Arms (section 6.1):
//! - A: fixed gains (those of `robust`) with a 2-of-3 altitude vote (radar, GNSS z, prediction);
//! - B: 7-state linear time-varying Kalman filter, one-epoch NIS rejection per scalar;
//! - B+: the same filter without any per-sample rejection, a two-sided CUSUM per source on the
//!   normalised innovations and the group health machine of section 8.3.
//!
//! All arms share the cold-start rule (8.4), the mode manager (8.3) and the safety monitor (8.6),
//! so the comparison isolates the estimator and its detector. With two altitude sources (`E0`)
//! nothing isolates a disagreement between two admitted sources: B+ declares it and keeps the
//! main solution (8.5, option b) unless the rate parity isolates a rate fault: the radar slope,
//! the GNSS vertical velocity and the IMU are three witnesses of the vertical velocity, so a
//! stuck, delayed, drifting or stepping source is isolable while a constant bias is not. An
//! isolation excludes the group and reprocesses the estimate from a certified snapshot (6.4).

use crate::landing_types::{
    ChannelStatus, GroupHealth, NavDeclaration, NavMode, NavParams, NavReport, Observation, Policy,
};
use crate::math::{Mat, Quat, Vec3};

const X_B: Vec3 = Vec3::new(1.0, 0.0, 0.0);
/// Filter dimension: position (3), velocity (3), accelerometer bias along `x_B` (1).
const N: usize = 7;
const BIAS: usize = 6;
/// Sources: radar, GNSS position x y z, GNSS velocity x y z.
const SOURCES: usize = 7;
const RADAR: usize = 0;
const GNSS_Z: usize = 3;
const GNSS_VZ: usize = 6;
/// Radar slope window of the safety monitor: 25 cycles, 0.5 s.
const SLOPE_WINDOW: usize = 25;
/// Time after which a radar not yet admitted at cold start is declared excluded.
const COLD_FLAG_S: f64 = 1.0;
/// Hold of the clean condition before a suspect group returns to healthy.
const SUSPECT_CLEAR_S: f64 = 1.0;
/// Input ring for the reprocessing of section 6.4: 6 s of control cycles.
const RING: usize = 300;
/// Snapshots of the estimate every 0.5 s, twelve of them.
const SNAP_EVERY: u64 = 25;
const SNAPS: usize = 12;
/// Rate parity: a pairwise rate residual above `RATE_BAD` sigma is inconsistent, below `RATE_OK`
/// consistent; isolation is only attempted within this time of the first detector alarm.
const RATE_BAD: f64 = 4.0;
const RATE_OK: f64 = 3.0;
const ISOLATION_WINDOW_S: f64 = 1.0;
/// Receiver self-consistency gate after missing data (sigma of the position increment).
const CONSISTENCY_SIGMA: f64 = 4.0;
/// GNSS epochs in the rate window (0.5 s at 10 Hz).
const GNSS_WINDOW: usize = 5;
/// Validation: an altimeter sample outside this range is treated as missing.
const ALTIMETER_RANGE_M: (f64, f64) = (-100.0, 100_000.0);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Arm {
    A,
    B,
    BPlus,
}

/// Health machine of one group, kept by the cycle counter.
#[derive(Clone, Copy, Debug)]
struct Group {
    health: GroupHealth,
    admitted_once: bool,
    last_data: Option<u64>,
    good_run: u32,
    clean_cycles: u32,
    /// Arms A and B: last cycle with a rejected sample or a lost vote.
    last_reject: Option<u64>,
    /// The detector (not missing data) made the group suspect since it was last healthy.
    detector_flag: bool,
}

impl Group {
    fn new(health: GroupHealth) -> Self {
        Group {
            health,
            admitted_once: false,
            last_data: None,
            good_run: 0,
            clean_cycles: 0,
            last_reject: None,
            detector_flag: false,
        }
    }

    /// Used by the estimator.
    fn usable(&self) -> bool {
        matches!(self.health, GroupHealth::Healthy | GroupHealth::Suspect)
    }
}

/// Independent vertical velocity of the safety monitor (8.6): IMU integration corrected by the
/// sources that are in use, never by the estimator's velocity.
#[derive(Clone, Copy, Debug)]
struct Monitor {
    vz: f64,
    ready: bool,
    slope_t: [f64; SLOPE_WINDOW],
    slope_z: [f64; SLOPE_WINDOW],
    slope_len: usize,
    since_correction_s: f64,
}

impl Monitor {
    fn new() -> Self {
        Monitor {
            vz: 0.0,
            ready: false,
            slope_t: [0.0; SLOPE_WINDOW],
            slope_z: [0.0; SLOPE_WINDOW],
            slope_len: 0,
            since_correction_s: 0.0,
        }
    }

    fn push_radar(&mut self, t: f64, z: Option<f64>) {
        match z {
            Some(z) => {
                if self.slope_len == SLOPE_WINDOW {
                    self.slope_t.rotate_left(1);
                    self.slope_z.rotate_left(1);
                    self.slope_len -= 1;
                }
                self.slope_t[self.slope_len] = t;
                self.slope_z[self.slope_len] = z;
                self.slope_len += 1;
            }
            None => self.slope_len = 0,
        }
    }

    /// Least-squares slope of the radar window, once it is full.
    fn radar_slope(&self) -> Option<f64> {
        if self.slope_len < SLOPE_WINDOW {
            return None;
        }
        let n = SLOPE_WINDOW as f64;
        let tm = self.slope_t.iter().sum::<f64>() / n;
        let zm = self.slope_z.iter().sum::<f64>() / n;
        let (mut num, mut den) = (0.0, 0.0);
        for i in 0..SLOPE_WINDOW {
            let dt = self.slope_t[i] - tm;
            num += dt * (self.slope_z[i] - zm);
            den += dt * dt;
        }
        (den > 0.0).then(|| num / den)
    }
}

/// What one control cycle fed the estimator, for the reprocessing.
#[derive(Clone, Copy, Debug)]
struct CycleInput {
    cycle: u64,
    u: Vec3,
    n: Vec3,
    imu_ok: bool,
    z_radar: Option<f64>,
    gnss: Option<([f64; 3], [f64; 3])>,
}

/// Estimate and covariance at a cycle; `certified` when every CUSUM was below `h/2`.
#[derive(Clone, Copy, Debug)]
struct Snapshot {
    cycle: u64,
    x: [f64; N],
    p: Mat<N>,
    certified: bool,
    radar_used: bool,
    gnss_used: bool,
}

/// The source the rate parity found inconsistent with the two others.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Odd {
    Radar,
    Gnss,
}

/// Rate witnesses of the vertical channel over 0.5 s: the radar altitudes, the GNSS epochs and
/// the IMU vertical velocity integral at each epoch.
#[derive(Clone, Copy, Debug)]
struct RateWindow {
    radar_t: [f64; SLOPE_WINDOW],
    radar_z: [f64; SLOPE_WINDOW],
    radar_len: usize,
    /// (time, z, vz, IMU vertical velocity integral) of the last GNSS epochs.
    gnss: [(f64, f64, f64, f64); GNSS_WINDOW],
    gnss_len: usize,
    imu_dv: f64,
    imu_cycles: [u32; GNSS_WINDOW],
    since_epoch: u32,
}

impl RateWindow {
    fn new() -> Self {
        RateWindow {
            radar_t: [0.0; SLOPE_WINDOW],
            radar_z: [0.0; SLOPE_WINDOW],
            radar_len: 0,
            gnss: [(0.0, 0.0, 0.0, 0.0); GNSS_WINDOW],
            gnss_len: 0,
            imu_dv: 0.0,
            imu_cycles: [0; GNSS_WINDOW],
            since_epoch: 0,
        }
    }
}

/// Least-squares slope of `(t, z)` and the sum of squared time deviations.
fn slope(t: &[f64], z: &[f64]) -> Option<(f64, f64)> {
    if t.len() < 3 {
        return None;
    }
    let n = t.len() as f64;
    let tm = t.iter().sum::<f64>() / n;
    let zm = z.iter().sum::<f64>() / n;
    let (mut num, mut den) = (0.0, 0.0);
    for (ti, zi) in t.iter().zip(z) {
        num += (ti - tm) * (zi - zm);
        den += (ti - tm) * (ti - tm);
    }
    (den > 0.0).then(|| (num / den, den))
}

/// The M10 navigation system of one controller.
#[derive(Clone, Debug)]
pub struct NavSystem {
    arm: Arm,
    prm: NavParams,
    dt: f64,
    gravity: f64,
    /// Arm A: GNSS position, GNSS velocity, altimeter position and velocity gains of `robust`.
    gains_a: [f64; 4],
    ready: bool,
    cycle: u64,
    x: [f64; N],
    p: Mat<N>,
    cusum_pos: [f64; SOURCES],
    cusum_neg: [f64; SOURCES],
    radar: Group,
    gnss: Group,
    mode: NavMode,
    mode_cycles: u32,
    ambiguous_cycles: u32,
    unusable_cycles: u32,
    transitions: u32,
    monitor: Monitor,
    h_est: f64,
    report: Option<NavReport>,
    /// GNSS z of the current cycle, for the vote of arm A.
    gnss_z_now: Option<f64>,
    /// Last GNSS fix (cycle, position, velocity), for the readmission consistency test.
    last_fix: Option<(u64, [f64; 3], [f64; 3])>,
    /// Section 6.4: input ring, snapshots and the rate window of the parity.
    inputs: [Option<CycleInput>; RING],
    snaps: [Option<Snapshot>; SNAPS],
    rates: RateWindow,
    /// Last cycle at which each source's CUSUM was zero (change-point estimate).
    cusum_zero: [u64; SOURCES],
    alarm_since: Option<u64>,
    episode_isolated: bool,
    isolated_radar: bool,
    isolated_gnss: bool,
    /// Dead reckoning after an isolation: the cycle of the restored snapshot.
    gnss_reckoned_from: Option<u64>,
}

// Index loops mirror the filter equations (state indices 0 to 6).
#[allow(clippy::needless_range_loop)]
impl NavSystem {
    pub fn new(policy: Policy, prm: NavParams, dt: f64, gravity: f64, gains_a: [f64; 4]) -> Self {
        let arm = match policy {
            Policy::M10A => Arm::A,
            Policy::M10B => Arm::B,
            _ => Arm::BPlus,
        };
        NavSystem {
            arm,
            prm,
            dt,
            gravity,
            gains_a,
            ready: false,
            cycle: 0,
            x: [0.0; N],
            p: Mat::ZERO,
            cusum_pos: [0.0; SOURCES],
            cusum_neg: [0.0; SOURCES],
            radar: Group::new(GroupHealth::Probation),
            gnss: Group::new(GroupHealth::Excluded),
            mode: NavMode::DegradedNav,
            mode_cycles: 0,
            ambiguous_cycles: 0,
            unusable_cycles: 0,
            transitions: 0,
            monitor: Monitor::new(),
            h_est: 0.0,
            report: None,
            gnss_z_now: None,
            last_fix: None,
            inputs: [None; RING],
            snaps: [None; SNAPS],
            rates: RateWindow::new(),
            cusum_zero: [0; SOURCES],
            alarm_since: None,
            episode_isolated: false,
            isolated_radar: false,
            isolated_gnss: false,
            gnss_reckoned_from: None,
        }
    }

    pub fn ready(&self) -> bool {
        self.ready
    }

    pub fn position(&self) -> Vec3 {
        Vec3::new(self.x[0], self.x[1], self.x[2])
    }

    pub fn velocity(&self) -> Vec3 {
        Vec3::new(self.x[3], self.x[4], self.x[5])
    }

    pub fn report(&self) -> Option<NavReport> {
        self.report
    }

    pub fn mode(&self) -> NavMode {
        self.mode
    }

    pub fn transitions(&self) -> u32 {
        self.transitions
    }

    /// The radar is not in use by the estimator (the `altimeter_rejected` flag of the estimate).
    pub fn radar_out(&self) -> bool {
        !self.radar.usable()
    }

    /// Guidance may chase the pad (8.2, 8.3) when the navigation is not declared untrusted and
    /// either the receiver is healthy, or it is out only for missing data and the dead-reckoned
    /// position is still good: its drift bound `sigma_h + b_h t^2 / 2` is below a quarter of the
    /// distance to the pad. A receiver suspected by its detector never steers the vehicle. In `E0`
    /// there is no vertical canary of the receiver (it needs a third altitude source), so the
    /// receiver health decides alone.
    pub fn chase_pad(&self, distance_m: f64) -> bool {
        if self.mode == NavMode::Untrusted {
            return false;
        }
        match self.gnss.health {
            GroupHealth::Healthy => true,
            GroupHealth::Suspect => false,
            GroupHealth::Excluded | GroupHealth::Probation => {
                // Missing data: reckoned since the last fix. Isolated: since the restored
                // certified snapshot; without one there is no trustworthy position.
                let t = if self.gnss.detector_flag {
                    match self.gnss_reckoned_from {
                        Some(c) => (self.cycle - c) as f64 * self.dt,
                        None => return false,
                    }
                } else {
                    self.stale_s(&self.gnss)
                };
                let b_h = self.prm.bias_prior_sigma_mps2 * self.prm.dead_reckoning_tilt;
                let sigma_h = self.p.0[0][0].max(self.p.0[1][1]).max(0.0).sqrt();
                sigma_h + 0.5 * b_h * t * t < 0.25 * distance_m
            }
        }
    }

    /// Safety monitor vertical velocity and the rise limit to compare it with: the limit grows by
    /// the bias bound times the time since the last correction when no source corrects it.
    pub fn monitor_vz(&self, base_limit: f64) -> (f64, f64) {
        let drift = self.prm.bias_prior_sigma_mps2 * self.monitor.since_correction_s;
        (self.monitor.vz, base_limit + drift)
    }

    pub fn declaration(&self) -> Option<NavDeclaration> {
        let report = self.report?;
        Some(NavDeclaration {
            x: self.x,
            p: self.p.0,
            report,
            h_est_m: self.h_est,
            covariance_valid: self.arm != Arm::A,
            transitions: self.transitions,
        })
    }

    fn cycles_of(&self, seconds: f64) -> u32 {
        ((seconds / self.dt).round() as u32).max(1)
    }

    fn stale_s(&self, g: &Group) -> f64 {
        match g.last_data {
            Some(c) => (self.cycle - c) as f64 * self.dt,
            None => f64::INFINITY,
        }
    }

    /// One control cycle. `s_cm` is the estimated station of the centre of mass.
    pub fn update(&mut self, obs: &Observation, q: Quat, s_cm: f64) {
        self.cycle += 1;
        let n = q.rotate(X_B);
        let finite3 = |a: [f64; 3]| a.iter().all(|x| x.is_finite());
        // 1. Validation: a non-finite or out-of-range sample is missing.
        let altimeter = obs
            .altimeter_m
            .filter(|a| a.is_finite() && *a >= ALTIMETER_RANGE_M.0 && *a <= ALTIMETER_RANGE_M.1);
        let gnss = match (obs.gnss_position_m, obs.gnss_velocity_mps) {
            (Some(p), Some(v)) if finite3(p) && finite3(v) => Some((p, v)),
            _ => None,
        };
        let f_b = obs.imu.specific_force_mps2;
        // A specific force beyond 1e4 m/s^2 is not physical for this vehicle: treated as missing.
        let imu_ok = finite3(f_b) && f_b.iter().all(|x| x.abs() < 1e4) && n.is_finite();
        let z_radar = altimeter.filter(|_| n.is_finite()).map(|a| a + s_cm * n.z);
        if !self.ready {
            if let Some((gp, gv)) = gnss
                && imu_ok
            {
                self.initialise(gp, gv);
                self.gnss.last_data = Some(self.cycle);
                self.monitor.vz = gv[2];
                self.monitor.ready = true;
                self.finish(n, s_cm, z_radar, Some(gv[2]));
            }
            return;
        }
        let u = if imu_ok {
            q.rotate(Vec3::from_array(f_b)) + Vec3::new(0.0, 0.0, -self.gravity)
        } else {
            Vec3::ZERO
        };
        self.record(CycleInput {
            cycle: self.cycle,
            u,
            n,
            imu_ok,
            z_radar,
            gnss,
        });
        if imu_ok {
            // 2. Time update with the measured specific force and attitude.
            match self.arm {
                Arm::A => self.propagate_fixed(u),
                Arm::B | Arm::BPlus => self.propagate(u, n),
            }
            let b = self.x[BIAS];
            self.monitor.vz += self.dt * (u.z - b * n.z);
            self.rates.imu_dv += self.dt * (u.z - b * n.z);
        }
        self.rates.since_epoch += 1;
        self.push_rates(z_radar, gnss);
        // 3. Measurements in a fixed order: radar, GNSS position x y z, GNSS velocity x y z.
        if let Some(z) = z_radar {
            self.radar.last_data = Some(self.cycle);
            self.radar_sample(z);
        }
        self.gnss_z_now = None;
        if let Some((gp, gv)) = gnss {
            self.gnss.last_data = Some(self.cycle);
            self.gnss_z_now = Some(gp[2]);
            self.gnss_sample(gp, gv);
        }
        if self.arm == Arm::A {
            self.vote(z_radar);
        }
        // 4. Health and isolation; 5. integrity; 6. modes; 8. safety monitor (in `finish`).
        self.update_health();
        if self.arm == Arm::BPlus {
            self.isolate();
        }
        if self.cycle.is_multiple_of(SNAP_EVERY) {
            self.snapshot();
        }
        let nz = if n.is_finite() {
            n
        } else {
            Vec3::new(0.0, 0.0, 1.0)
        };
        self.finish(nz, s_cm, z_radar, gnss.map(|g| g.1[2]));
    }

    fn initialise(&mut self, gp: [f64; 3], gv: [f64; 3]) {
        let sp = self.prm.gnss_position_sigma_m * self.prm.gnss_position_sigma_m;
        let sv = self.prm.gnss_velocity_sigma_mps * self.prm.gnss_velocity_sigma_mps;
        let sb = self.prm.bias_prior_sigma_mps2 * self.prm.bias_prior_sigma_mps2;
        self.x = [gp[0], gp[1], gp[2], gv[0], gv[1], gv[2], 0.0];
        self.p = Mat::diag([sp, sp, sp, sv, sv, sv, sb]);
        self.gnss.health = GroupHealth::Healthy;
        self.gnss.admitted_once = true;
        self.ready = true;
    }

    /// `x = F x + B u`, `P = F P F^T + Q`, with `n = R(q) x_B` and the bias along `x_B`.
    fn propagate(&mut self, u: Vec3, n: Vec3) {
        let t = self.dt;
        let b = self.x[BIAS];
        let a = [u.x - b * n.x, u.y - b * n.y, u.z - b * n.z];
        let nn = [n.x, n.y, n.z];
        for i in 0..3 {
            self.x[i] += self.x[3 + i] * t + 0.5 * t * t * a[i];
            self.x[3 + i] += t * a[i];
        }
        let mut f = Mat::<N>::identity();
        for i in 0..3 {
            f.0[i][3 + i] = t;
            f.0[i][BIAS] = -0.5 * t * t * nn[i];
            f.0[3 + i][BIAS] = -t * nn[i];
        }
        let s2 = self.prm.accel_process_sigma_mps2 * self.prm.accel_process_sigma_mps2;
        let mut qm = Mat::<N>::ZERO;
        for i in 0..3 {
            qm.0[i][i] = 0.25 * t * t * t * t * s2;
            qm.0[i][3 + i] = 0.5 * t * t * t * s2;
            qm.0[3 + i][i] = 0.5 * t * t * t * s2;
            qm.0[3 + i][3 + i] = t * t * s2;
        }
        let w = self.prm.bias_walk_sigma_mps2_per_sqrt_s;
        qm.0[BIAS][BIAS] = w * w * t;
        self.p = f.congruence(&self.p).add(&qm).symmetrized();
        self.guard_covariance();
    }

    /// Arm A: the `robust` propagation (no bias state, no covariance).
    fn propagate_fixed(&mut self, u: Vec3) {
        let t = self.dt;
        for (i, ai) in [u.x, u.y, u.z].iter().enumerate() {
            self.x[i] += self.x[3 + i] * t + 0.5 * t * t * ai;
            self.x[3 + i] += t * ai;
        }
    }

    /// A covariance that lost its finiteness or a positive diagonal is reset, inflated.
    fn guard_covariance(&mut self) {
        let bad = !self.p.is_finite() || (0..N).any(|i| self.p.0[i][i] <= 0.0);
        if bad {
            let s = 10.0 * self.prm.gnss_position_sigma_m;
            let sv = 10.0 * self.prm.gnss_velocity_sigma_mps;
            let sb = self.prm.bias_prior_sigma_mps2;
            self.p = Mat::diag([s * s, s * s, s * s, sv * sv, sv * sv, sv * sv, sb * sb]);
        }
    }

    /// Innovation and its variance for a direct measurement of state `i` with noise variance `r`.
    fn innovation(&self, i: usize, z: f64, r: f64) -> (f64, f64) {
        (z - self.x[i], self.p.0[i][i] + r)
    }

    /// Scalar Joseph-form update of state `i`: `P = (I - K H) P (I - K H)^T + K r K^T`.
    fn apply(&mut self, i: usize, y: f64, s: f64, r: f64) {
        let mut k = [0.0; N];
        for (j, kj) in k.iter_mut().enumerate() {
            *kj = self.p.0[j][i] / s;
        }
        for (j, kj) in k.iter().enumerate() {
            self.x[j] += kj * y;
        }
        let mut a = Mat::<N>::identity();
        for (j, kj) in k.iter().enumerate() {
            a.0[j][i] -= kj;
        }
        let mut p = a.congruence(&self.p);
        for (j, kj) in k.iter().enumerate() {
            for (l, kl) in k.iter().enumerate() {
                p.0[j][l] += kj * kl * r;
            }
        }
        self.p = p.symmetrized();
        self.guard_covariance();
    }

    fn cusum(&mut self, src: usize, y: f64, s: f64) {
        let z = y / s.sqrt();
        let cap = 2.0 * self.prm.cusum_h;
        let k = self.prm.cusum_k;
        self.cusum_pos[src] = (self.cusum_pos[src] + z - k).clamp(0.0, cap);
        self.cusum_neg[src] = (self.cusum_neg[src] - z - k).clamp(0.0, cap);
        if self.cusum_pos[src] == 0.0 && self.cusum_neg[src] == 0.0 {
            self.cusum_zero[src] = self.cycle;
        }
    }

    fn cusum_max(&self, sources: std::ops::Range<usize>) -> f64 {
        sources
            .map(|i| self.cusum_pos[i].max(self.cusum_neg[i]))
            .fold(0.0, f64::max)
    }

    fn reset_cusum(&mut self, sources: std::ops::Range<usize>) {
        for i in sources {
            self.cusum_pos[i] = 0.0;
            self.cusum_neg[i] = 0.0;
            self.cusum_zero[i] = self.cycle;
        }
    }

    fn radar_r(&self) -> f64 {
        let (a, b) = (self.prm.radar_sigma_m, self.prm.radar_lever_sigma_m);
        a * a + b * b
    }

    fn radar_sample(&mut self, z: f64) {
        let r = self.radar_r();
        let (y, s) = self.innovation(2, z, r);
        if !self.radar.usable() {
            // Admission (cold start, the absolute gate of `robust`) or readmission (normalised).
            let good = if self.radar.admitted_once {
                y * y <= self.prm.readmission_sigma * self.prm.readmission_sigma * s
            } else {
                y.abs() <= self.prm.admission_gate_m
            };
            self.radar.good_run = if good { self.radar.good_run + 1 } else { 0 };
            let needed = if self.radar.detector_flag {
                // Excluded by the detector: clean for `T_hold` before it is trusted again.
                self.prm
                    .readmission_samples
                    .max(self.cycles_of(self.prm.t_hold_s))
            } else if self.radar.admitted_once {
                self.prm.readmission_samples
            } else {
                self.prm.admission_cycles
            };
            let early = !self.radar.admitted_once && (self.cycle as f64) * self.dt < COLD_FLAG_S;
            if self.radar.good_run >= needed {
                self.radar.health = GroupHealth::Healthy;
                self.radar.detector_flag = false;
                self.radar.admitted_once = true;
                self.radar.good_run = 0;
                self.radar.clean_cycles = 0;
                self.reset_cusum(RADAR..RADAR + 1);
            } else if self.radar.good_run > 0 || early {
                self.radar.health = GroupHealth::Probation;
            } else {
                self.radar.health = GroupHealth::Excluded;
            }
            return;
        }
        match self.arm {
            Arm::A => {}
            Arm::B => {
                if y * y > self.prm.nis_reject * s {
                    self.radar.last_reject = Some(self.cycle);
                } else {
                    self.apply(2, y, s, r);
                }
            }
            Arm::BPlus => {
                self.cusum(RADAR, y, s);
                self.apply(2, y, s, r);
            }
        }
    }

    fn gnss_sample(&mut self, gp: [f64; 3], gv: [f64; 3]) {
        let rp = self.prm.gnss_position_sigma_m * self.prm.gnss_position_sigma_m;
        let rv = self.prm.gnss_velocity_sigma_mps * self.prm.gnss_velocity_sigma_mps;
        let z = [gp[0], gp[1], gp[2], gv[0], gv[1], gv[2]];
        let r = [rp, rp, rp, rv, rv, rv];
        if !self.gnss.usable() {
            // Readmission after missing data: the receiver must be consistent with itself (the
            // position increment matches the mean velocity), not with a dead-reckoned estimate
            // whose covariance does not cover the unmodelled drift.
            let good = if self.gnss.detector_flag {
                // Excluded by the detector: back only when consistent with the solution.
                let k2 = self.prm.readmission_sigma * self.prm.readmission_sigma;
                self.last_fix = Some((self.cycle, gp, gv));
                (0..6).all(|i| {
                    let (y, s) = self.innovation(i, z[i], r[i]);
                    y * y <= k2 * s
                })
            } else {
                self.gnss_consistent(gp, gv)
            };
            self.gnss.good_run = if good { self.gnss.good_run + 1 } else { 0 };
            // GNSS epochs: after a detector exclusion, clean for `T_hold` (10 Hz receiver).
            let needed = if self.gnss.detector_flag {
                let epochs = (self.prm.t_hold_s / (5.0 * self.dt)).round() as u32;
                self.prm.readmission_samples.max(epochs)
            } else {
                self.prm.gnss_readmission_epochs
            };
            if self.gnss.good_run >= needed {
                self.gnss.health = GroupHealth::Healthy;
                self.gnss.good_run = 0;
                self.gnss.clean_cycles = 0;
                self.reset_cusum(1..SOURCES);
                if !self.gnss.detector_flag {
                    self.inflate_for_readmission();
                }
                self.gnss.detector_flag = false;
                self.gnss_reckoned_from = None;
            } else if self.gnss.good_run > 0 {
                self.gnss.health = GroupHealth::Probation;
            } else {
                self.gnss.health = GroupHealth::Excluded;
            }
            return;
        }
        self.last_fix = Some((self.cycle, gp, gv));
        if self.arm == Arm::A {
            let [kp, kv, ..] = self.gains_a;
            for i in 0..2 {
                self.x[i] += (z[i] - self.x[i]) * kp;
            }
            for i in 3..6 {
                self.x[i] += (z[i] - self.x[i]) * kv;
            }
            return;
        }
        for i in 0..6 {
            let (y, s) = self.innovation(i, z[i], r[i]);
            if self.arm == Arm::B && y * y > self.prm.nis_reject * s {
                self.gnss.last_reject = Some(self.cycle);
                continue;
            }
            if self.arm == Arm::BPlus {
                self.cusum(1 + i, y, s);
            }
            self.apply(i, y, s, r[i]);
        }
    }

    /// Consecutive GNSS epochs agree: `|dp - (v_k + v_{k-1}) / 2 * dt| <= k sigma` per axis.
    fn gnss_consistent(&mut self, gp: [f64; 3], gv: [f64; 3]) -> bool {
        let previous = self.last_fix.replace((self.cycle, gp, gv));
        let Some((c, p0, v0)) = previous else {
            return false;
        };
        let dt = (self.cycle - c) as f64 * self.dt;
        if dt > 0.5 {
            return false;
        }
        let sp = self.prm.gnss_position_sigma_m;
        let limit = CONSISTENCY_SIGMA * (2.0 * sp * sp).sqrt();
        (0..3).all(|i| (gp[i] - p0[i] - 0.5 * (gv[i] + v0[i]) * dt).abs() <= limit)
    }

    /// The position and velocity covariance grows back to the receiver level before the first
    /// update after a readmission, so the filter trusts the returning receiver again.
    fn inflate_for_readmission(&mut self) {
        let sp = self.prm.gnss_position_sigma_m * self.prm.gnss_position_sigma_m;
        let sv = self.prm.gnss_velocity_sigma_mps * self.prm.gnss_velocity_sigma_mps;
        for i in 0..6 {
            let floor = if i < 3 { sp } else { sv };
            for j in 0..N {
                if j != i {
                    self.p.0[i][j] = 0.0;
                    self.p.0[j][i] = 0.0;
                }
            }
            self.p.0[i][i] = self.p.0[i][i].max(floor);
        }
    }

    fn record(&mut self, input: CycleInput) {
        let slot = (input.cycle as usize) % RING;
        self.inputs[slot] = Some(input);
    }

    fn snapshot(&mut self) {
        let half = 0.5 * self.prm.cusum_h;
        let certified = (0..SOURCES).all(|i| self.cusum_pos[i].max(self.cusum_neg[i]) < half);
        let slot = ((self.cycle / SNAP_EVERY) as usize) % SNAPS;
        self.snaps[slot] = Some(Snapshot {
            cycle: self.cycle,
            x: self.x,
            p: self.p,
            certified,
            radar_used: self.radar.usable(),
            gnss_used: self.gnss.usable(),
        });
    }

    fn push_rates(&mut self, z_radar: Option<f64>, gnss: Option<([f64; 3], [f64; 3])>) {
        let t = self.cycle as f64 * self.dt;
        let w = &mut self.rates;
        match z_radar {
            Some(z) => {
                if w.radar_len == SLOPE_WINDOW {
                    w.radar_t.rotate_left(1);
                    w.radar_z.rotate_left(1);
                    w.radar_len -= 1;
                }
                w.radar_t[w.radar_len] = t;
                w.radar_z[w.radar_len] = z;
                w.radar_len += 1;
            }
            None => w.radar_len = 0,
        }
        if let Some((gp, gv)) = gnss {
            if w.gnss_len == GNSS_WINDOW {
                w.gnss.rotate_left(1);
                w.imu_cycles.rotate_left(1);
                w.gnss_len -= 1;
            }
            w.gnss[w.gnss_len] = (t, gp[2], gv[2], w.imu_dv);
            w.imu_cycles[w.gnss_len] = w.since_epoch;
            w.gnss_len += 1;
            w.since_epoch = 0;
        } else if w.since_epoch > 10 {
            w.gnss_len = 0;
        }
    }

    /// Rate parity (vertical channel): the radar slope against the mean GNSS vertical velocity,
    /// the GNSS altitude slope against the same velocity, and the IMU velocity change against the
    /// GNSS velocity change over the window. Under the single-fault hypothesis the faulty source is
    /// the one inconsistent with both others; every other pattern is "not isolated". A constant
    /// bias changes no rate, so it is never isolated here (sections 3.3 and 3.4).
    fn rate_pattern(&self) -> Option<Odd> {
        let w = &self.rates;
        if w.radar_len < SLOPE_WINDOW || w.gnss_len < GNSS_WINDOW {
            return None;
        }
        let g = &w.gnss;
        // The radar samples over the same span as the GNSS epochs, so both rates refer to the same
        // instant (the span centre); a misalignment of 0.05 s is 3 sigma at 10 m/s^2.
        let (t0, t1) = (g[0].0 - 1e-9, g[GNSS_WINDOW - 1].0 + 1e-9);
        let mut rt = [0.0; SLOPE_WINDOW];
        let mut rz = [0.0; SLOPE_WINDOW];
        let mut nr = 0;
        for i in 0..w.radar_len {
            if w.radar_t[i] >= t0 && w.radar_t[i] <= t1 {
                rt[nr] = w.radar_t[i];
                rz[nr] = w.radar_z[i];
                nr += 1;
            }
        }
        let (s_r, den_r) = slope(&rt[..nr], &rz[..nr])?;
        let gt = [g[0].0, g[1].0, g[2].0, g[3].0, g[4].0];
        let gz = [g[0].1, g[1].1, g[2].1, g[3].1, g[4].1];
        let m = GNSS_WINDOW as f64;
        let v_g = g.iter().map(|e| e.2).sum::<f64>() / m;
        let (s_g, den_g) = slope(&gt, &gz)?;
        let (sp, sv) = (
            self.prm.gnss_position_sigma_m,
            self.prm.gnss_velocity_sigma_mps,
        );
        let var_v = sv * sv / m;
        let d_rg = (s_r - v_g).abs() / (self.radar_r() / den_r + var_v).sqrt();
        let d_gg = (s_g - v_g).abs() / (sp * sp / den_g + var_v).sqrt();
        let (first, last) = (g[0], g[GNSS_WINDOW - 1]);
        let k: u32 = w.imu_cycles[1..].iter().sum();
        let sa = self.prm.accel_process_sigma_mps2 * self.dt;
        let var_i = 2.0 * sv * sv + sa * sa * f64::from(k);
        let d_ig = ((last.3 - first.3) - (last.2 - first.2)).abs() / var_i.sqrt();
        let bad = |d: f64| d > RATE_BAD;
        let ok = |d: f64| d < RATE_OK;
        if bad(d_rg) && ok(d_gg) && ok(d_ig) {
            Some(Odd::Radar)
        } else if (bad(d_rg) && bad(d_ig) && ok(d_gg)) || (bad(d_gg) && ok(d_rg) && ok(d_ig)) {
            Some(Odd::Gnss)
        } else {
            None
        }
    }

    /// Sections 6.3 and 6.4: within `ISOLATION_WINDOW_S` of the first alarm with both altitude
    /// groups in use, a clear rate-parity pattern excludes the odd group and reprocesses the
    /// estimate without it from the last certified snapshot.
    fn isolate(&mut self) {
        let h = self.prm.cusum_h;
        // Vertical-channel alarms only (radar, GNSS z, GNSS vz): the parity is vertical.
        let alarm = [RADAR, GNSS_Z, GNSS_VZ]
            .iter()
            .any(|&i| self.cusum_pos[i].max(self.cusum_neg[i]) > h);
        if !alarm {
            self.alarm_since = None;
            self.episode_isolated = false;
            return;
        }
        if self.episode_isolated || !(self.radar.usable() && self.gnss.usable()) {
            return;
        }
        let since = *self.alarm_since.get_or_insert(self.cycle);
        if (self.cycle - since) as f64 * self.dt > ISOLATION_WINDOW_S {
            return;
        }
        let Some(odd) = self.rate_pattern() else {
            return;
        };
        let sources = match odd {
            Odd::Radar => RADAR..RADAR + 1,
            Odd::Gnss => 1..SOURCES,
        };
        // Change point: the earliest last-zero cycle among the sources of the group that moved.
        let quarter = h / 4.0;
        let onset = sources
            .clone()
            .filter(|&i| self.cusum_pos[i].max(self.cusum_neg[i]) > quarter)
            .map(|i| self.cusum_zero[i])
            .min()
            .unwrap_or(since);
        let g = match odd {
            Odd::Radar => {
                self.isolated_radar = true;
                &mut self.radar
            }
            Odd::Gnss => {
                self.isolated_gnss = true;
                &mut self.gnss
            }
        };
        g.health = GroupHealth::Excluded;
        g.detector_flag = true;
        g.good_run = 0;
        g.clean_cycles = 0;
        self.reset_cusum(sources);
        // One isolation per alarm episode: the episode ends when every vertical alarm clears.
        self.episode_isolated = true;
        let restored = self.reprocess(onset, odd);
        if odd == Odd::Gnss {
            self.gnss_reckoned_from = restored;
        }
    }

    /// Restores the newest certified snapshot older than `onset - 1 s` and replays the input ring
    /// without the excluded group. The work is bounded by the ring (300 cycles), a constant.
    /// Returns the snapshot cycle, or `None` (and inflates the vertical covariance) without one.
    fn reprocess(&mut self, onset: u64, excluded: Odd) -> Option<u64> {
        let target = onset.saturating_sub(u64::from(self.cycles_of(1.0)));
        let oldest = self.cycle.saturating_sub(RING as u64 - 1);
        let snap = self
            .snaps
            .iter()
            .flatten()
            .filter(|s| s.certified && s.cycle <= target && s.cycle >= oldest)
            .max_by_key(|s| s.cycle)
            .copied();
        let Some(snap) = snap else {
            let sp = self.prm.gnss_position_sigma_m * self.prm.gnss_position_sigma_m;
            self.p.0[2][2] = self.p.0[2][2].max(sp);
            self.p.0[5][5] = self.p.0[5][5].max(0.25);
            return None;
        };
        self.x = snap.x;
        self.p = snap.p;
        let use_radar = snap.radar_used && excluded != Odd::Radar;
        let use_gnss = snap.gnss_used && excluded != Odd::Gnss;
        let rr = self.radar_r();
        let rp = self.prm.gnss_position_sigma_m * self.prm.gnss_position_sigma_m;
        let rv = self.prm.gnss_velocity_sigma_mps * self.prm.gnss_velocity_sigma_mps;
        for c in (snap.cycle + 1)..=self.cycle {
            let Some(input) = self.inputs[(c as usize) % RING].filter(|i| i.cycle == c) else {
                continue;
            };
            if input.imu_ok {
                self.propagate(input.u, input.n);
            }
            if use_radar && let Some(z) = input.z_radar {
                let (y, s) = self.innovation(2, z, rr);
                self.apply(2, y, s, rr);
            }
            if use_gnss && let Some((gp, gv)) = input.gnss {
                let z = [gp[0], gp[1], gp[2], gv[0], gv[1], gv[2]];
                for (i, zi) in z.iter().enumerate() {
                    let r = if i < 3 { rp } else { rv };
                    let (y, s) = self.innovation(i, *zi, r);
                    self.apply(i, y, s, r);
                }
            }
        }
        Some(snap.cycle)
    }

    /// Arm A: 2-of-3 vote between the radar, the GNSS z of this cycle and the prediction.
    fn vote(&mut self, z_radar: Option<f64>) {
        let [kp, _, ka, kav] = self.gains_a;
        let thr = self.prm.vote_threshold_m;
        let pred = self.x[2];
        let radar = z_radar.filter(|_| self.radar.usable());
        let gnss = self.gnss_z_now.filter(|_| self.gnss.usable());
        let dt = self.dt;
        let use_radar = |x: &mut [f64; N], a: f64| {
            let res = a - x[2];
            x[2] += ka * res;
            x[5] += kav * res / dt;
        };
        match (radar, gnss) {
            (Some(a), Some(g)) => {
                if (a - g).abs() <= thr {
                    use_radar(&mut self.x, a);
                    self.x[2] += (g - self.x[2]) * kp;
                } else if (a - pred).abs() <= (g - pred).abs() {
                    self.gnss.last_reject = Some(self.cycle);
                    use_radar(&mut self.x, a);
                } else {
                    self.radar.last_reject = Some(self.cycle);
                    self.x[2] += (g - self.x[2]) * kp;
                }
            }
            (Some(a), None) => {
                if (a - pred).abs() <= thr {
                    use_radar(&mut self.x, a);
                } else {
                    self.radar.last_reject = Some(self.cycle);
                }
            }
            (None, Some(g)) => self.x[2] += (g - self.x[2]) * kp,
            (None, None) => {}
        }
    }

    /// Section 8.3 health machine of the groups in use.
    fn update_health(&mut self) {
        let h = self.prm.cusum_h;
        let suspect_at = self.prm.suspect_cusum_fraction * h;
        let hold = u64::from(self.cycles_of(self.prm.t_hold_s));
        let clear = self.cycles_of(SUSPECT_CLEAR_S);
        let stats = [self.cusum_max(RADAR..RADAR + 1), self.cusum_max(1..SOURCES)];
        let stale = [self.stale_s(&self.radar), self.stale_s(&self.gnss)];
        let (cycle, arm) = (self.cycle, self.arm);
        let (suspect_after, exclude_after) = (self.prm.suspect_after_s, self.prm.exclude_after_s);
        for (k, g) in [&mut self.radar, &mut self.gnss].into_iter().enumerate() {
            if !g.usable() {
                continue;
            }
            if stale[k] > exclude_after {
                // Out for missing data: readmission follows the missing-data rule.
                g.health = GroupHealth::Excluded;
                g.detector_flag = false;
                g.good_run = 0;
                continue;
            }
            let recent = g.last_reject.is_some_and(|c| cycle - c < hold);
            let (detector, clean) = match arm {
                Arm::BPlus => (stats[k] > suspect_at, stats[k] < h / 4.0),
                Arm::A | Arm::B => (recent, !recent),
            };
            let suspect = detector || stale[k] > suspect_after;
            let clean = clean && stale[k] <= suspect_after;
            if detector {
                g.detector_flag = true;
            }
            match g.health {
                GroupHealth::Healthy if suspect => {
                    g.health = GroupHealth::Suspect;
                    g.clean_cycles = 0;
                }
                GroupHealth::Suspect => {
                    g.clean_cycles = if clean { g.clean_cycles + 1 } else { 0 };
                    if g.clean_cycles >= clear {
                        g.health = GroupHealth::Healthy;
                        g.detector_flag = false;
                    }
                }
                _ => {}
            }
        }
        // A group out of the filter is no longer watched by its CUSUM until it is readmitted.
        if !self.radar.usable() {
            self.reset_cusum(RADAR..RADAR + 1);
        }
        if !self.gnss.usable() {
            self.reset_cusum(1..SOURCES);
        }
    }

    /// Integrity (5), modes (6) and safety monitor (8); then the report.
    fn finish(&mut self, n: Vec3, s_cm: f64, z_radar: Option<f64>, gnss_vz: Option<f64>) {
        let sd = |i: usize| self.p.0[i][i].max(0.0).sqrt();
        let (sigma_z, sigma_vz) = (sd(2), sd(5));
        let sigma_h = sd(0).max(sd(1));
        let sigma_vh = sd(3).max(sd(4));
        // Estimated nozzle-plane altitude: the mode manager and the alert limit use it.
        self.h_est = self.x[2] - s_cm * n.z;
        let prm = &self.prm;
        let al_v = prm.al_v_floor_m.max(prm.al_v_fraction * self.h_est);
        let both_used = self.radar.usable() && self.gnss.usable();
        let hold = u64::from(self.cycles_of(prm.t_hold_s));
        let c = self.cycle;
        let recent = |g: &Group| g.last_reject.is_some_and(|r| c - r < hold);
        // Disagreement of the two altitude sources: the detector alarm (B+), recent rejections
        // or lost votes (B, A).
        let alarm = match self.arm {
            Arm::BPlus => {
                self.cusum_max(RADAR..RADAR + 1) > prm.cusum_h
                    || self.cusum_max(GNSS_Z..GNSS_Z + 1) > prm.cusum_h
            }
            Arm::B => recent(&self.radar) && recent(&self.gnss),
            Arm::A => recent(&self.radar) || recent(&self.gnss),
        };
        let in_flight_ambiguity = both_used && alarm;
        // A radar that the cold-start rule never admitted while the receiver is in use: the two
        // disagree from the start and nothing says which is wrong (8.4).
        let cold_ambiguity = !self.radar.admitted_once
            && self.gnss.usable()
            && self.radar.health == GroupHealth::Excluded;
        self.ambiguous_cycles = if in_flight_ambiguity {
            self.ambiguous_cycles + 1
        } else {
            0
        };
        let unusable = !self.radar.usable() && !self.gnss.usable();
        self.unusable_cycles = if unusable {
            self.unusable_cycles + 1
        } else {
            0
        };

        let groups_healthy =
            self.radar.health == GroupHealth::Healthy && self.gnss.health == GroupHealth::Healthy;
        let has_cov = self.arm != Arm::A;
        let vertical_trusted = groups_healthy && !alarm && (!has_cov || prm.k_ff * sigma_z <= al_v);
        let hv_trusted = self.gnss.health == GroupHealth::Healthy
            && (!has_cov || prm.k_ff * sigma_vh <= prm.al_hv_mps);
        let hp_trusted = self.gnss.health == GroupHealth::Healthy
            && prm.k_ff * sigma_h + prm.b_h_m <= prm.al_h_m;

        // Mode manager (8.3): worsening is quick, improving slow, never below `h_commit`.
        let untrusted_cond = self.ambiguous_cycles >= self.cycles_of(prm.t_max_s)
            || self.unusable_cycles >= prm.n_in_cycles;
        let nominal_ok = vertical_trusted && hv_trusted;
        let above_commit = self.h_est > prm.h_commit_m;
        let (hold_cycles, safe_cycles) =
            (self.cycles_of(prm.t_hold_s), self.cycles_of(prm.t_safe_s));
        let n_in = prm.n_in_cycles;
        let previous = self.mode;
        if untrusted_cond && self.mode != NavMode::Untrusted {
            self.mode = NavMode::Untrusted;
        } else {
            match self.mode {
                NavMode::Nominal => {
                    self.mode_cycles = if nominal_ok { 0 } else { self.mode_cycles + 1 };
                    if self.mode_cycles >= n_in {
                        self.mode = NavMode::DegradedNav;
                    }
                }
                NavMode::DegradedNav => {
                    self.mode_cycles = if nominal_ok { self.mode_cycles + 1 } else { 0 };
                    if self.mode_cycles >= hold_cycles && above_commit {
                        self.mode = NavMode::Nominal;
                    }
                }
                NavMode::Untrusted => {
                    self.mode_cycles = if untrusted_cond {
                        0
                    } else {
                        self.mode_cycles + 1
                    };
                    if self.mode_cycles >= safe_cycles && above_commit {
                        self.mode = NavMode::DegradedNav;
                    }
                }
            }
        }
        if self.mode != previous {
            self.transitions += 1;
            self.mode_cycles = 0;
        }

        self.update_monitor(z_radar, gnss_vz);

        let mode = self.mode;
        let channel = |trusted: bool| {
            if mode == NavMode::Untrusted {
                ChannelStatus::Untrusted
            } else if trusted {
                ChannelStatus::Trusted
            } else {
                ChannelStatus::Degraded
            }
        };
        self.report = Some(NavReport {
            mode,
            radar: self.radar.health,
            gnss: self.gnss.health,
            vertical: channel(vertical_trusted),
            horizontal_velocity: channel(hv_trusted),
            horizontal_position: channel(hp_trusted),
            ambiguous: in_flight_ambiguity || cold_ambiguity,
            sigma_z_m: sigma_z,
            sigma_vz_mps: sigma_vz,
            sigma_h_m: sigma_h,
            sigma_vh_mps: sigma_vh,
            accel_bias_mps2: self.x[BIAS],
            monitor_vz_mps: self.monitor.vz,
            cusum_radar: self.cusum_max(RADAR..RADAR + 1),
            cusum_gnss: self.cusum_max(1..SOURCES),
            isolated_radar: self.isolated_radar,
            isolated_gnss: self.isolated_gnss,
        });
    }

    /// Corrects the monitor velocity with the GNSS vertical velocity and the radar slope, each
    /// only while its group is in use (8.6).
    fn update_monitor(&mut self, z_radar: Option<f64>, gnss_vz: Option<f64>) {
        if !self.monitor.ready {
            return;
        }
        let t = self.cycle as f64 * self.dt;
        self.monitor
            .push_radar(t, z_radar.filter(|_| self.radar.usable()));
        self.monitor.since_correction_s += self.dt;
        let mut corrected = false;
        if let Some(v) = gnss_vz.filter(|_| self.gnss.usable()) {
            self.monitor.vz += self.prm.monitor_gnss_gain * (v - self.monitor.vz);
            corrected = true;
        }
        if self.radar.usable()
            && let Some(slope) = self.monitor.radar_slope()
        {
            self.monitor.vz += self.prm.monitor_radar_gain * (slope - self.monitor.vz);
            corrected = true;
        }
        if corrected {
            self.monitor.since_correction_s = 0.0;
        }
    }
}
