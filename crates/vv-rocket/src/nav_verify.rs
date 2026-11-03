//! M10 navigation verifier (`vv-rocket-landing-verification.v3`, additive): compares what an M10
//! controller declared each cycle with the true state (docs/m10-resilient-navigation.md, 9 and 9.1).
//!
//! Truth side: only this module and `landing_verify` read the true state. The declarations are
//! claims to be compared; no requirement or invariant verdict reads them, and the controller never
//! reads this report.

use serde::Serialize;

use crate::landing_model::{FaultKind, PreparedLanding};
use crate::landing_sim::CycleDeclaration;
use crate::landing_truth::{TruthLog, base_kinematics};
use crate::landing_types::{ChannelStatus, GroupHealth, NavMode};
use crate::landing_verify::Verification;
use crate::math::Mat;

pub const VERIFICATION_SCHEMA_V3: &str = "vv-rocket-landing-verification.v3";
/// `T_g`: an alert failure is an excess of the alert limit lasting this long while trusted.
pub const ALERT_TIME_S: f64 = 0.5;
/// Fault windows are widened by `T_hold` plus this after their end for the false-alarm count.
pub const PROBATION_MARGIN_S: f64 = 1.0;
pub const NAV_NOTE: &str = "controller declarations compared with the true state by the verifier; no requirement or invariant verdict reads them";

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct ChannelReport {
    pub alert_limit: String,
    /// Cycles with the true error above the alert limit.
    pub exceed_cycles: u64,
    /// The true error exceeded the limit for at least `T_g`: the declaration is applicable.
    pub declaration_applicable: bool,
    /// An excess of at least `T_g` while declared trusted (I1).
    pub alert_failure: bool,
    pub alert_failure_t_s: Option<f64>,
    pub longest_trusted_excess_s: f64,
    /// Fraction of the cycles declared not trusted with the error below half the limit (I2).
    pub unnecessary_declaration_fraction: f64,
    pub trusted_fraction: f64,
    pub max_error: f64,
    pub rms_error: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct Transition {
    pub t_s: f64,
    pub from: NavMode,
    pub to: NavMode,
    pub h_est_m: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct FaultDetection {
    pub fault: &'static str,
    pub start_s: f64,
    /// First cycle inside the window with a mode worse than `nominal`, a group not healthy or an
    /// ambiguity flag: delay from the start. `None`: never declared inside the window.
    pub first_declaration_delay_s: Option<f64>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct NavigationReport {
    pub source: &'static str,
    pub cycles: u64,
    /// The four dimensions of section 9.1 (the declaration one is per channel below).
    pub recovery: bool,
    pub containment: bool,
    /// `R` recovered, `T` intact touchdown off the pad, `U` unsafe or no contact.
    pub physical_class: &'static str,
    pub vertical: ChannelReport,
    pub horizontal_velocity: ChannelReport,
    pub horizontal_position: ChannelReport,
    /// Mean NEES (7 states) over the cycles with a covariance; `None` for arm A.
    pub nees_mean: Option<f64>,
    pub nees_cycles: u64,
    pub final_vertical_error_m: Option<f64>,
    pub transitions: Vec<Transition>,
    /// MD1: improvements of the mode at or below `h_commit` (estimated altitude). Must be zero.
    pub unsafe_transitions: u64,
    /// MD2: the bound `T_flight / T_hold` and whether the count stays within it.
    pub transition_bound: u64,
    pub transitions_within_bound: bool,
    /// F2: degradations outside every fault window widened by `T_hold` and 1 s.
    pub degradations_outside_fault_windows: u64,
    pub detections: Vec<FaultDetection>,
    /// F3: the groups the controller isolated, and the verdict against the injected faults:
    /// `none`, `correct` (every isolation names a group with an injected fault that had already
    /// started) or `wrong` (some isolation names a group without a fault, or precedes its onset).
    pub isolated: Vec<&'static str>,
    pub isolation: &'static str,
    /// Each isolation with its instant and its own verdict: `correct`, `before_onset` or `wrong`.
    pub isolation_events: Vec<IsolationEvent>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct IsolationEvent {
    pub group: &'static str,
    pub t_s: f64,
    pub verdict: &'static str,
}

/// The group of sources a fault corrupts, for the isolation verdict.
fn fault_group(kind: FaultKind) -> Option<&'static str> {
    match kind {
        FaultKind::AltimeterBias
        | FaultKind::AltimeterBiasLow
        | FaultKind::AltimeterDropout
        | FaultKind::AltimeterStuck
        | FaultKind::AltimeterDelay
        | FaultKind::AltimeterOutliers
        | FaultKind::AltimeterDrift => Some("radar"),
        FaultKind::GnssBias
        | FaultKind::GnssBiasLow
        | FaultKind::GnssDropout
        | FaultKind::GnssHorizontalBias
        | FaultKind::GnssCoherentRamp => Some("gnss"),
        _ => None,
    }
}

/// True accelerometer bias along `x_B` at `step`, from the configured faults.
fn true_bias(prep: &PreparedLanding, step: u64) -> f64 {
    let mut b = 0.0;
    for f in &prep.faults {
        if f.start_step <= step && step < f.end_step {
            match f.spec.kind {
                FaultKind::ImuAccelBias => b += f.spec.magnitude,
                FaultKind::ImuAccelDrift => {
                    b += f.spec.magnitude * (step - f.start_step) as f64 * prep.dt
                }
                _ => {}
            }
        }
    }
    b
}

struct Channel {
    limit_text: String,
    exceed: u64,
    run: u64,
    run_trusted: u64,
    longest_trusted: u64,
    applicable: bool,
    failure_at: Option<f64>,
    unnecessary: u64,
    trusted: u64,
    count: u64,
    max: f64,
    sum_sq: f64,
}

impl Channel {
    fn new(limit_text: String) -> Self {
        Channel {
            limit_text,
            exceed: 0,
            run: 0,
            run_trusted: 0,
            longest_trusted: 0,
            applicable: false,
            failure_at: None,
            unnecessary: 0,
            trusted: 0,
            count: 0,
            max: 0.0,
            sum_sq: 0.0,
        }
    }

    fn add(&mut self, err: f64, limit: f64, status: ChannelStatus, t_s: f64, window: u64) {
        let trusted = status == ChannelStatus::Trusted;
        self.count += 1;
        self.max = self.max.max(err);
        self.sum_sq += err * err;
        if trusted {
            self.trusted += 1;
        } else if err < 0.5 * limit {
            self.unnecessary += 1;
        }
        if err > limit {
            self.exceed += 1;
            self.run += 1;
            self.run_trusted = if trusted { self.run_trusted + 1 } else { 0 };
        } else {
            self.run = 0;
            self.run_trusted = 0;
        }
        if self.run >= window {
            self.applicable = true;
        }
        self.longest_trusted = self.longest_trusted.max(self.run_trusted);
        if self.run_trusted >= window && self.failure_at.is_none() {
            self.failure_at = Some(t_s);
        }
    }

    fn report(&self, cycle_s: f64) -> ChannelReport {
        let n = self.count.max(1) as f64;
        ChannelReport {
            alert_limit: self.limit_text.clone(),
            exceed_cycles: self.exceed,
            declaration_applicable: self.applicable,
            alert_failure: self.failure_at.is_some(),
            alert_failure_t_s: self.failure_at,
            longest_trusted_excess_s: self.longest_trusted as f64 * cycle_s,
            unnecessary_declaration_fraction: self.unnecessary as f64 / n,
            trusted_fraction: self.trusted as f64 / n,
            max_error: self.max,
            rms_error: (self.sum_sq / n).sqrt(),
        }
    }
}

/// Section 9.1: the physical class depends on the true state only.
pub fn physical_class(v: &Verification) -> &'static str {
    let pass = |id: &str| v.requirements.iter().any(|r| r.id == id && r.pass);
    if v.outcome == "no_contact" || !v.invariants_pass {
        return "U";
    }
    let others = [
        "R1_vertical_speed",
        "R2_horizontal_speed",
        "R3_tilt",
        "R4_angular_rate",
        "R6_propellant_margin",
    ]
    .iter()
    .all(|id| pass(id));
    match (others, pass("R5_position")) {
        (true, true) => "R",
        (true, false) => "T",
        _ => "U",
    }
}

pub fn verify_navigation(
    prep: &PreparedLanding,
    log: &TruthLog,
    decls: &[CycleDeclaration],
    verification: &Verification,
) -> NavigationReport {
    let prm = &prep.controller.nav;
    let cycle_s = prep.dt * prep.controller.control_period_steps as f64;
    let window = ((ALERT_TIME_S / cycle_s).round() as u64).max(1);
    let mut v = Channel::new(format!(
        "max({} m, {} h), h the true nozzle-plane altitude",
        prm.al_v_floor_m, prm.al_v_fraction
    ));
    let mut hv = Channel::new(format!("{} m/s", prm.al_hv_mps));
    let mut hp = Channel::new(format!("{} m", prm.al_h_m));
    let (mut nees_sum, mut nees_n) = (0.0, 0_u64);
    let mut transitions = Vec::new();
    let mut previous: Option<NavMode> = None;
    let mut final_ez = None;
    let mut detections: Vec<FaultDetection> = prep
        .faults
        .iter()
        .map(|f| FaultDetection {
            fault: f.spec.kind.as_str(),
            start_s: f.spec.start_s,
            first_declaration_delay_s: None,
        })
        .collect();
    for d in decls {
        let Some(truth) = log.steps.get(d.step as usize).filter(|s| s.step == d.step) else {
            continue;
        };
        let s = &truth.state;
        let t_s = d.step as f64 * prep.dt;
        let x = &d.declaration.x;
        let e = [
            x[0] - s.r.x,
            x[1] - s.r.y,
            x[2] - s.r.z,
            x[3] - s.v.x,
            x[4] - s.v.y,
            x[5] - s.v.z,
            x[6] - true_bias(prep, d.step),
        ];
        let h_true = base_kinematics(&prep.truth.vehicle, s).0.z;
        let al_v = prm.al_v_floor_m.max(prm.al_v_fraction * h_true);
        let r = &d.declaration.report;
        v.add(e[2].abs(), al_v, r.vertical, t_s, window);
        let ehv = (e[3] * e[3] + e[4] * e[4]).sqrt();
        hv.add(ehv, prm.al_hv_mps, r.horizontal_velocity, t_s, window);
        let ehp = (e[0] * e[0] + e[1] * e[1]).sqrt();
        hp.add(ehp, prm.al_h_m, r.horizontal_position, t_s, window);
        final_ez = Some(e[2]);
        if d.declaration.covariance_valid
            && let Some(sol) = Mat(d.declaration.p).cholesky_solve(&e)
        {
            nees_sum += e.iter().zip(sol).map(|(a, b)| a * b).sum::<f64>();
            nees_n += 1;
        }
        if let Some(p) = previous
            && p != r.mode
        {
            transitions.push(Transition {
                t_s,
                from: p,
                to: r.mode,
                h_est_m: d.declaration.h_est_m,
            });
        }
        previous = Some(r.mode);
        let declared = r.mode != NavMode::Nominal
            || r.ambiguous
            || r.radar != GroupHealth::Healthy
            || r.gnss != GroupHealth::Healthy;
        for (det, f) in detections.iter_mut().zip(&prep.faults) {
            if det.first_declaration_delay_s.is_none()
                && declared
                && d.step >= f.start_step
                && d.step < f.end_step
            {
                det.first_declaration_delay_s = Some((d.step - f.start_step) as f64 * prep.dt);
            }
        }
    }
    let unsafe_transitions = transitions
        .iter()
        .filter(|t| t.to < t.from && t.h_est_m <= prm.h_commit_m)
        .count() as u64;
    let flight_s = log.end_step as f64 * prep.dt;
    let transition_bound = (flight_s / prm.t_hold_s).floor() as u64;
    let margin = prm.t_hold_s + PROBATION_MARGIN_S;
    let degradations_outside_fault_windows = transitions
        .iter()
        .filter(|t| t.to > t.from)
        .filter(|t| {
            !prep
                .faults
                .iter()
                .any(|f| t.t_s >= f.spec.start_s && t.t_s <= f.spec.end_s + margin)
        })
        .count() as u64;
    // F3: the first cycle at which each group's isolation flag is set. An isolation is correct
    // only when a fault of the same group is injected and has started at that cycle; an
    // isolation of the right group before the onset is not credited.
    let mut isolation_events = Vec::new();
    for group in ["radar", "gnss"] {
        let flagged = decls.iter().find(|d| {
            let r = &d.declaration.report;
            if group == "radar" {
                r.isolated_radar
            } else {
                r.isolated_gnss
            }
        });
        let Some(d) = flagged else { continue };
        let same: Vec<_> = prep
            .faults
            .iter()
            .filter(|f| fault_group(f.spec.kind) == Some(group))
            .collect();
        let verdict = if same.is_empty() {
            "wrong"
        } else if same.iter().any(|f| f.start_step <= d.step) {
            "correct"
        } else {
            "before_onset"
        };
        isolation_events.push(IsolationEvent {
            group,
            t_s: d.step as f64 * prep.dt,
            verdict,
        });
    }
    isolation_events.sort_by(|a, b| a.t_s.total_cmp(&b.t_s));
    let isolated: Vec<&'static str> = isolation_events.iter().map(|e| e.group).collect();
    let isolation = if isolation_events.is_empty() {
        "none"
    } else if isolation_events.iter().all(|e| e.verdict == "correct") {
        "correct"
    } else {
        "wrong"
    };
    NavigationReport {
        source: NAV_NOTE,
        cycles: decls.len() as u64,
        recovery: verification.outcome == "landed"
            && verification.requirements_pass
            && verification.invariants_pass,
        containment: verification.invariants_pass && verification.outcome != "no_contact",
        physical_class: physical_class(verification),
        vertical: v.report(cycle_s),
        horizontal_velocity: hv.report(cycle_s),
        horizontal_position: hp.report(cycle_s),
        nees_mean: (nees_n > 0).then(|| nees_sum / nees_n as f64),
        nees_cycles: nees_n,
        final_vertical_error_m: final_ez,
        transitions_within_bound: transitions.len() as u64 <= transition_bound,
        transition_bound,
        unsafe_transitions,
        degradations_outside_fault_windows,
        transitions,
        detections,
        isolated,
        isolation,
        isolation_events,
    }
}
