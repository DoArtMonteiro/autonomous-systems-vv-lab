//! Numerical convergence by step halving. The rigid-body model (`vv-rocket-case.v1`) takes its
//! step as input, so the same case runs at dt, dt/2, dt/4, ... and the state at a common time is
//! compared: observed order of accuracy and a Richardson estimate of the error of the finest run.
//! The landing model fixes dt = 0.01 s as a registered value (`prepare_landing` refuses any other),
//! so a landing case cannot be refined without changing the validated model; the check reports
//! that instead of running it.

use serde::Serialize;
use vv_rocket::model::{Case, prepare};
use vv_rocket::sim::simulate;

/// Order of the RK4 integrator of `vv-rocket`.
pub const EXPECTED_ORDER: f64 = 4.0;
/// Accepted band for an observed order.
pub const ORDER_BAND: (f64, f64) = (3.5, 4.5);
/// Differences below this fraction of the position magnitude are at round-off, where an observed
/// order means nothing: about 4500 times the f64 epsilon, the accumulation of rounding over the
/// 10^3 to 10^5 steps of these runs.
pub const ROUND_OFF_RELATIVE: f64 = 1e-12;
pub const MAX_LEVELS: u32 = 6;

#[derive(Clone, Debug, Serialize)]
pub struct Convergence {
    pub applicable: bool,
    pub reason: Option<String>,
    pub dt_s: Vec<f64>,
    /// Common time of the compared states: the last coarse step reached by every run.
    pub compare_time_s: f64,
    /// |r(dt_k) - r(dt_k+1)| at the common time, in metres.
    pub position_differences_m: Vec<f64>,
    /// log2 of successive difference ratios; `None` where the differences are at round-off.
    pub observed_orders: Vec<Option<f64>>,
    /// Round-off floor used for the orders: `ROUND_OFF_RELATIVE x max(1 m, |r|)`.
    pub round_off_m: f64,
    /// Richardson estimate of the position error of the finest run, with the expected order.
    pub error_estimate_m: f64,
    /// Richardson estimate of the position error at the base step `dt_s[0]`, the step the
    /// experiment runs: `d0 x 2^p / (2^p - 1)`. `pass` is decided on this value.
    pub base_error_estimate_m: f64,
    pub tolerance_m: f64,
    pub pass: bool,
}

pub fn not_applicable(reason: &str, tolerance_m: f64) -> Convergence {
    Convergence {
        applicable: false,
        reason: Some(reason.into()),
        dt_s: Vec::new(),
        compare_time_s: 0.0,
        position_differences_m: Vec::new(),
        observed_orders: Vec::new(),
        round_off_m: 0.0,
        error_estimate_m: 0.0,
        base_error_estimate_m: 0.0,
        tolerance_m,
        pass: false,
    }
}

/// Step-halving study of a rigid-body case with `levels` step sizes (at least 3).
pub fn rigid_body(case_bytes: &[u8], levels: u32, tolerance_m: f64) -> Result<Convergence, String> {
    if !(3..=MAX_LEVELS).contains(&levels) {
        return Err(format!("levels must be in [3, {MAX_LEVELS}]"));
    }
    if !(tolerance_m.is_finite() && tolerance_m > 0.0) {
        return Err("tolerance_m must be positive".into());
    }
    let base: Case =
        serde_json::from_slice(case_bytes).map_err(|e| format!("invalid case: {e}"))?;
    prepare(&base)?;
    let mut dts = Vec::new();
    let mut runs = Vec::new();
    for k in 0..levels {
        let mut c = base.clone();
        c.dt_s = base.dt_s / f64::from(1u32 << k);
        let steps = (c.duration_s / c.dt_s).round() as u64;
        // Two samples only: the trace is not compared, the states are.
        c.record_every = steps.max(1);
        let p = prepare(&c).map_err(|e| format!("dt = {} s: {e}", c.dt_s))?;
        let run = simulate(&p, true).map_err(|e| format!("dt = {} s: {e}", c.dt_s))?;
        dts.push(c.dt_s);
        runs.push(run.states);
    }
    let coarse = dts[0];
    let end = dts
        .iter()
        .zip(&runs)
        .map(|(dt, s)| (s.len() - 1) as f64 * dt)
        .fold(f64::INFINITY, f64::min);
    let coarse_steps = (end / coarse + 1e-9).floor() as u64;
    if coarse_steps == 0 {
        return Ok(not_applicable(
            "the run ends before one coarse step",
            tolerance_m,
        ));
    }
    let t = coarse_steps as f64 * coarse;
    let at: Vec<_> = runs
        .iter()
        .enumerate()
        .map(|(k, s)| s[(coarse_steps << k) as usize].r)
        .collect();
    let diffs: Vec<f64> = at.windows(2).map(|w| (w[0] - w[1]).norm()).collect();
    let floor = ROUND_OFF_RELATIVE * at.iter().map(|r| r.norm()).fold(1.0, f64::max);
    let orders: Vec<Option<f64>> = diffs
        .windows(2)
        .map(|w| (w[0] > floor && w[1] > floor).then(|| (w[0] / w[1]).log2()))
        .collect();
    let last = *diffs.last().expect("at least two differences");
    let gain = 2f64.powf(EXPECTED_ORDER);
    let estimate = last / (gain - 1.0);
    let base_estimate = diffs[0] * gain / (gain - 1.0);
    let orders_ok = orders
        .iter()
        .flatten()
        .all(|o| (ORDER_BAND.0..=ORDER_BAND.1).contains(o));
    Ok(Convergence {
        applicable: true,
        reason: None,
        dt_s: dts,
        compare_time_s: t,
        position_differences_m: diffs,
        observed_orders: orders,
        round_off_m: floor,
        error_estimate_m: estimate,
        base_error_estimate_m: base_estimate,
        tolerance_m,
        pass: orders_ok && base_estimate <= tolerance_m,
    })
}

pub const LANDING_FIXED_STEP: &str = "the landing model fixes dt_s = 0.01 s as a registered value; refining it would change the validated model";

#[cfg(test)]
mod tests {
    use super::*;

    const DESCENT: &[u8] = include_bytes!("../../crates/vv-rocket/cases/propulsive_descent.json");

    /// The coupled case of the M8 convergence study (gravity, exponential atmosphere, gimballed
    /// burn), whose truncation error is well above round-off at dt = 0.04 s.
    fn coupled() -> Vec<u8> {
        serde_json::to_vec(&vv_rocket::verify::coupled_case(0.04)).unwrap()
    }

    #[test]
    fn rk4_shows_fourth_order_on_the_m8_coupled_case() {
        let c = rigid_body(&coupled(), 4, 1.0).unwrap();
        assert!(c.applicable);
        assert_eq!(c.dt_s, [0.04, 0.02, 0.01, 0.005]);
        let orders: Vec<f64> = c.observed_orders.iter().flatten().copied().collect();
        assert_eq!(orders.len(), 2, "{c:?}");
        for o in orders {
            assert!((3.5..=4.5).contains(&o), "observed order {o}");
        }
        assert!(c.pass, "{c:?}");
    }

    #[test]
    fn differences_at_round_off_carry_no_order_and_pass_on_the_error_bound() {
        let c = rigid_body(DESCENT, 4, 1e-3).unwrap();
        assert!(c.position_differences_m.iter().all(|d| *d < 1e-6));
        assert!(c.observed_orders.iter().all(Option::is_none));
        assert!(c.pass, "{c:?}");
    }

    #[test]
    fn a_tolerance_below_the_error_estimate_fails() {
        let c = rigid_body(&coupled(), 3, 1e-12).unwrap();
        assert!(!c.pass);
    }

    #[test]
    fn invalid_level_counts_are_refused() {
        assert!(rigid_body(DESCENT, 2, 1.0).is_err());
        assert!(rigid_body(DESCENT, 7, 1.0).is_err());
    }
}
