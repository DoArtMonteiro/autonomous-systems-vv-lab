//! Statistics recomputed from records: binomial intervals, exact paired tests, multiplicity
//! correction and Sobol sensitivity indices. Each function is checked against values produced by
//! an independent implementation (`scripts/m12_stats_reference.py`, Python standard library and a
//! different algorithm) and Sobol indices against the analytic Ishigami solution.

use crate::prng::SplitMix64;

/// ln Γ(x) for x > 0, Lanczos approximation (g = 7, 9 coefficients), relative error below 1e-15.
pub fn ln_gamma(x: f64) -> f64 {
    const G: f64 = 7.0;
    const C: [f64; 9] = [
        0.999_999_999_999_809_9,
        676.520_368_121_885_1,
        -1_259.139_216_722_402_8,
        771.323_428_777_653_1,
        -176.615_029_162_140_6,
        12.507_343_278_686_905,
        -0.138_571_095_265_720_12,
        9.984_369_578_019_572e-6,
        1.505_632_735_149_311_6e-7,
    ];
    if x < 0.5 {
        // Reflection: Γ(x) Γ(1 - x) = π / sin(πx).
        return (std::f64::consts::PI / (std::f64::consts::PI * x).sin()).ln() - ln_gamma(1.0 - x);
    }
    let x = x - 1.0;
    let mut a = C[0];
    let t = x + G + 0.5;
    for (i, c) in C.iter().enumerate().skip(1) {
        a += c / (x + i as f64);
    }
    0.5 * (2.0 * std::f64::consts::PI).ln() + (x + 0.5) * t.ln() - t + a.ln()
}

/// Continued fraction of the incomplete beta function (modified Lentz).
fn beta_cf(a: f64, b: f64, x: f64) -> f64 {
    const TINY: f64 = 1e-300;
    let (qab, qap, qam) = (a + b, a + 1.0, a - 1.0);
    let mut c = 1.0;
    let mut d = 1.0 - qab * x / qap;
    if d.abs() < TINY {
        d = TINY;
    }
    d = 1.0 / d;
    let mut h = d;
    for m in 1..=10_000 {
        let m = m as f64;
        let m2 = 2.0 * m;
        let aa = m * (b - m) * x / ((qam + m2) * (a + m2));
        d = 1.0 + aa * d;
        if d.abs() < TINY {
            d = TINY;
        }
        c = 1.0 + aa / c;
        if c.abs() < TINY {
            c = TINY;
        }
        d = 1.0 / d;
        h *= d * c;
        let aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
        d = 1.0 + aa * d;
        if d.abs() < TINY {
            d = TINY;
        }
        c = 1.0 + aa / c;
        if c.abs() < TINY {
            c = TINY;
        }
        d = 1.0 / d;
        let del = d * c;
        h *= del;
        if (del - 1.0).abs() < 1e-16 {
            break;
        }
    }
    h
}

/// Regularised incomplete beta function I_x(a, b), a, b > 0, x in [0, 1].
pub fn beta_inc(a: f64, b: f64, x: f64) -> f64 {
    if x <= 0.0 {
        return 0.0;
    }
    if x >= 1.0 {
        return 1.0;
    }
    let ln_front = ln_gamma(a + b) - ln_gamma(a) - ln_gamma(b) + a * x.ln() + b * (1.0 - x).ln();
    let front = ln_front.exp();
    if x < (a + 1.0) / (a + b + 2.0) {
        front * beta_cf(a, b, x) / a
    } else {
        1.0 - front * beta_cf(b, a, 1.0 - x) / b
    }
}

/// Inverse of I_x(a, b) in x, by bisection to the last representable digit.
pub fn beta_inv(p: f64, a: f64, b: f64) -> f64 {
    let (mut lo, mut hi) = (0.0f64, 1.0f64);
    for _ in 0..200 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if beta_inc(a, b, mid) < p {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    0.5 * (lo + hi)
}

/// Standard normal quantile, Acklam's rational approximation (relative error below 1.2e-9).
pub fn normal_quantile(p: f64) -> f64 {
    const A: [f64; 6] = [
        -3.969_683_028_665_376e1,
        2.209_460_984_245_205e2,
        -2.759_285_104_469_687e2,
        1.383_577_518_672_69e2,
        -3.066_479_806_614_716e1,
        2.506_628_277_459_239,
    ];
    const B: [f64; 5] = [
        -5.447_609_879_822_406e1,
        1.615_858_368_580_409e2,
        -1.556_989_798_598_866e2,
        6.680_131_188_771_972e1,
        -1.328_068_155_288_572e1,
    ];
    const C: [f64; 6] = [
        -7.784_894_002_430_293e-3,
        -3.223_964_580_411_365e-1,
        -2.400_758_277_161_838,
        -2.549_732_539_343_734,
        4.374_664_141_464_968,
        2.938_163_982_698_783,
    ];
    const D: [f64; 4] = [
        7.784_695_709_041_462e-3,
        3.224_671_290_700_398e-1,
        2.445_134_137_142_996,
        3.754_408_661_907_416,
    ];
    let low = 0.024_25;
    let tail = |q: f64| {
        (((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    };
    if p < low {
        tail((-2.0 * p.ln()).sqrt())
    } else if p > 1.0 - low {
        -tail((-2.0 * (1.0 - p).ln()).sqrt())
    } else {
        let q = p - 0.5;
        let r = q * q;
        (((((A[0] * r + A[1]) * r + A[2]) * r + A[3]) * r + A[4]) * r + A[5]) * q
            / (((((B[0] * r + B[1]) * r + B[2]) * r + B[3]) * r + B[4]) * r + 1.0)
    }
}

/// Stream label that separates the bootstrap resampling from the design draws.
const BOOTSTRAP_STREAM: u64 = 0xB007_57A9;

/// Wilson score interval for `k` successes in `n` trials.
pub fn wilson(k: u64, n: u64, confidence: f64) -> (f64, f64) {
    if n == 0 {
        return (0.0, 1.0);
    }
    let z = normal_quantile(0.5 + confidence / 2.0);
    let (k, n) = (k as f64, n as f64);
    let p = k / n;
    let denom = 1.0 + z * z / n;
    let centre = (p + z * z / (2.0 * n)) / denom;
    let half = z * (p * (1.0 - p) / n + z * z / (4.0 * n * n)).sqrt() / denom;
    // At k = 0 and k = n one bound is exactly 0 or 1; the formula misses it by rounding.
    let lo = if k == 0.0 {
        0.0
    } else {
        (centre - half).max(0.0)
    };
    let hi = if k == n {
        1.0
    } else {
        (centre + half).min(1.0)
    };
    (lo, hi)
}

/// Clopper-Pearson exact interval, from quantiles of the beta distribution.
pub fn clopper_pearson(k: u64, n: u64, confidence: f64) -> (f64, f64) {
    if n == 0 {
        return (0.0, 1.0);
    }
    let alpha = 1.0 - confidence;
    let (kf, nf) = (k as f64, n as f64);
    let lo = if k == 0 {
        0.0
    } else {
        beta_inv(alpha / 2.0, kf, nf - kf + 1.0)
    };
    let hi = if k == n {
        1.0
    } else {
        beta_inv(1.0 - alpha / 2.0, kf + 1.0, nf - kf)
    };
    (lo, hi)
}

/// P(X <= k) for X ~ Binomial(n, p), through the incomplete beta function.
pub fn binomial_cdf(k: u64, n: u64, p: f64) -> f64 {
    if k >= n {
        return 1.0;
    }
    beta_inc((n - k) as f64, k as f64 + 1.0, 1.0 - p)
}

/// Exact McNemar test on paired binary outcomes: `b` and `c` are the two kinds of discordant
/// pairs. Two-sided p-value, 1 when there is no discordant pair.
pub fn mcnemar_exact(b: u64, c: u64) -> f64 {
    let n = b + c;
    if n == 0 {
        return 1.0;
    }
    (2.0 * binomial_cdf(b.min(c), n, 0.5)).min(1.0)
}

/// Holm step-down adjusted p-values, in the input order.
pub fn holm(p: &[f64]) -> Vec<f64> {
    let m = p.len();
    let mut order: Vec<usize> = (0..m).collect();
    order.sort_by(|&a, &b| p[a].total_cmp(&p[b]).then(a.cmp(&b)));
    let mut out = vec![0.0; m];
    let mut running = 0.0f64;
    for (rank, &i) in order.iter().enumerate() {
        running = running.max(((m - rank) as f64 * p[i]).min(1.0));
        out[i] = running;
    }
    out
}

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct Moments {
    pub n: u64,
    pub mean: f64,
    pub sd: f64,
    pub min: f64,
    pub q05: f64,
    pub median: f64,
    pub q95: f64,
    pub max: f64,
}

/// Linear-interpolation quantile (type 7) of sorted data.
fn quantile_sorted(s: &[f64], q: f64) -> f64 {
    let h = (s.len() - 1) as f64 * q;
    let lo = h.floor() as usize;
    let hi = (lo + 1).min(s.len() - 1);
    s[lo] + (h - lo as f64) * (s[hi] - s[lo])
}

pub fn moments(x: &[f64]) -> Option<Moments> {
    if x.is_empty() {
        return None;
    }
    let n = x.len() as f64;
    let mean = x.iter().sum::<f64>() / n;
    let var = if x.len() > 1 {
        x.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1.0)
    } else {
        0.0
    };
    let mut s = x.to_vec();
    s.sort_by(f64::total_cmp);
    Some(Moments {
        n: x.len() as u64,
        mean,
        sd: var.sqrt(),
        min: s[0],
        q05: quantile_sorted(&s, 0.05),
        median: quantile_sorted(&s, 0.5),
        q95: quantile_sorted(&s, 0.95),
        max: s[s.len() - 1],
    })
}

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct SobolIndex {
    pub first_order: f64,
    pub total: f64,
    /// Percentile bootstrap intervals, when requested.
    pub first_order_interval: Option<(f64, f64)>,
    pub total_interval: Option<(f64, f64)>,
}

/// First-order (Saltelli et al. 2010) and total (Jansen 1999) indices from the outputs on the A, B
/// and AB_i matrices, over the given rows.
fn sobol_point(fa: &[f64], fb: &[f64], fab: &[Vec<f64>], rows: &[usize]) -> Vec<(f64, f64)> {
    let n = rows.len() as f64;
    let mean = rows.iter().map(|&j| fa[j] + fb[j]).sum::<f64>() / (2.0 * n);
    let var = rows
        .iter()
        .map(|&j| (fa[j] - mean).powi(2) + (fb[j] - mean).powi(2))
        .sum::<f64>()
        / (2.0 * n - 1.0);
    fab.iter()
        .map(|abi| {
            let s1 = rows.iter().map(|&j| fb[j] * (abi[j] - fa[j])).sum::<f64>() / n / var;
            let st = rows.iter().map(|&j| (fa[j] - abi[j]).powi(2)).sum::<f64>() / (2.0 * n) / var;
            (s1, st)
        })
        .collect()
}

/// Sobol indices with optional bootstrap intervals (rows resampled with replacement by SplitMix64
/// with `seed`). `None` when the output has no variance or the lengths differ.
pub fn sobol(
    fa: &[f64],
    fb: &[f64],
    fab: &[Vec<f64>],
    bootstrap: u32,
    confidence: f64,
    seed: u64,
) -> Option<Vec<SobolIndex>> {
    let n = fa.len();
    if n < 2 || fb.len() != n || fab.iter().any(|v| v.len() != n) {
        return None;
    }
    let rows: Vec<usize> = (0..n).collect();
    let point = sobol_point(fa, fb, fab, &rows);
    if point.iter().any(|(a, b)| !a.is_finite() || !b.is_finite()) {
        return None;
    }
    let mut out: Vec<SobolIndex> = point
        .iter()
        .map(|&(s1, st)| SobolIndex {
            first_order: s1,
            total: st,
            first_order_interval: None,
            total_interval: None,
        })
        .collect();
    if bootstrap > 0 {
        // Not the design seed itself: the Saltelli matrices draw from SplitMix64::new(seed).
        let mut g = SplitMix64::new(seed ^ crate::prng::mix(BOOTSTRAP_STREAM));
        let mut draws: Vec<Vec<(f64, f64)>> = vec![Vec::new(); fab.len()];
        for _ in 0..bootstrap {
            let rows: Vec<usize> = (0..n).map(|_| g.below(n as u64) as usize).collect();
            for (i, v) in sobol_point(fa, fb, fab, &rows).into_iter().enumerate() {
                draws[i].push(v);
            }
        }
        let (lo, hi) = ((1.0 - confidence) / 2.0, (1.0 + confidence) / 2.0);
        for (i, d) in draws.iter().enumerate() {
            let mut s1: Vec<f64> = d.iter().map(|x| x.0).filter(|x| x.is_finite()).collect();
            let mut st: Vec<f64> = d.iter().map(|x| x.1).filter(|x| x.is_finite()).collect();
            s1.sort_by(f64::total_cmp);
            st.sort_by(f64::total_cmp);
            if !s1.is_empty() && !st.is_empty() {
                out[i].first_order_interval =
                    Some((quantile_sorted(&s1, lo), quantile_sorted(&s1, hi)));
                out[i].total_interval = Some((quantile_sorted(&st, lo), quantile_sorted(&st, hi)));
            }
        }
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::plan::unit_points;
    use crate::spec::Design;
    use std::f64::consts::PI;

    #[test]
    fn ln_gamma_matches_factorials_and_the_half_integer_value() {
        let mut f = 1.0f64;
        for n in 1..30u32 {
            f *= f64::from(n);
            let got = ln_gamma(f64::from(n) + 1.0);
            assert!((got - f.ln()).abs() < 1e-12 * f.ln().max(1.0), "n = {n}");
        }
        assert!((ln_gamma(0.5) - PI.sqrt().ln()).abs() < 1e-14);
    }

    #[test]
    fn beta_inc_has_closed_forms_for_integer_parameters() {
        // I_x(1, b) = 1 - (1 - x)^b and I_x(a, 1) = x^a.
        for &x in &[0.01, 0.3, 0.5, 0.77, 0.999] {
            assert!((beta_inc(1.0, 5.0, x) - (1.0 - (1.0f64 - x).powi(5))).abs() < 1e-14);
            assert!((beta_inc(4.0, 1.0, x) - x.powi(4)).abs() < 1e-14);
        }
        // Round trip where the distribution function is not flat (near x = 1, I is 1 - 1e-20).
        for &x in &[0.01, 0.3, 0.5, 0.77] {
            assert!((beta_inv(beta_inc(3.0, 7.0, x), 3.0, 7.0) - x).abs() < 1e-12);
        }
    }

    #[test]
    fn interval_edge_cases() {
        assert_eq!(clopper_pearson(0, 10, 0.95).0, 0.0);
        assert_eq!(clopper_pearson(10, 10, 0.95).1, 1.0);
        // k = 0: upper = 1 - (alpha/2)^(1/n).
        let hi = clopper_pearson(0, 20, 0.95).1;
        assert!((hi - (1.0 - 0.025f64.powf(1.0 / 20.0))).abs() < 1e-12);
        let (lo, hi) = wilson(0, 20, 0.95);
        assert_eq!(lo, 0.0);
        assert!(hi > 0.0 && hi < 0.2);
    }

    #[test]
    fn holm_is_monotone_and_capped() {
        let adj = holm(&[0.01, 0.04, 0.03, 0.5]);
        assert_eq!(adj, vec![0.04, 0.09, 0.09, 0.5]);
        assert_eq!(holm(&[0.6, 0.9]), vec![1.0, 1.0]);
    }

    #[test]
    fn mcnemar_matches_hand_computed_tails() {
        // b = 0, c = 5: 2 * 0.5^5.
        assert!((mcnemar_exact(0, 5) - 0.0625).abs() < 1e-15);
        // b = 1, c = 9: 2 * (1 + 10) / 1024.
        assert!((mcnemar_exact(1, 9) - 22.0 / 1024.0).abs() < 1e-14);
        assert_eq!(mcnemar_exact(4, 4), 1.0);
    }

    /// Ishigami function on [-π, π]^3 with a = 7, b = 0.1.
    fn ishigami(x: &[f64]) -> f64 {
        let (a, b) = (7.0, 0.1);
        x[0].sin() + a * x[1].sin().powi(2) + b * x[2].powi(4) * x[0].sin()
    }

    #[test]
    fn sobol_indices_recover_the_analytic_ishigami_solution() {
        // Analytic partial variances (Ishigami and Homma 1990; Sobol' and Levitan 1999).
        let (a, b) = (7.0f64, 0.1f64);
        let pi4 = PI.powi(4);
        let pi8 = PI.powi(8);
        let v = a * a / 8.0 + b * pi4 / 5.0 + b * b * pi8 / 18.0 + 0.5;
        let v1 = 0.5 * (1.0 + b * pi4 / 5.0).powi(2);
        let v2 = a * a / 8.0;
        let v13 = b * b * pi8 * 8.0 / 225.0;
        let expect_s1 = [v1 / v, v2 / v, 0.0];
        let expect_st = [(v1 + v13) / v, v2 / v, v13 / v];

        let n = 1 << 14;
        let (pts, _) = unit_points(
            &Design::Saltelli {
                base_samples: n,
                seed: 20_261_103,
            },
            3,
        );
        let f: Vec<f64> = pts
            .iter()
            .map(|u| {
                let x: Vec<f64> = u.iter().map(|&t| -PI + 2.0 * PI * t).collect();
                ishigami(&x)
            })
            .collect();
        let n = n as usize;
        let fa = &f[0..n];
        let fb = &f[n..2 * n];
        let fab: Vec<Vec<f64>> = (0..3)
            .map(|i| f[(2 + i) * n..(3 + i) * n].to_vec())
            .collect();
        let idx = sobol(fa, fb, &fab, 200, 0.95, 7).unwrap();
        for i in 0..3 {
            assert!(
                (idx[i].first_order - expect_s1[i]).abs() < 0.03,
                "S{} = {} expected {}",
                i + 1,
                idx[i].first_order,
                expect_s1[i]
            );
            assert!(
                (idx[i].total - expect_st[i]).abs() < 0.03,
                "ST{} = {} expected {}",
                i + 1,
                idx[i].total,
                expect_st[i]
            );
            let (lo, hi) = idx[i].total_interval.unwrap();
            assert!(lo <= idx[i].total && idx[i].total <= hi);
        }
    }

    #[test]
    fn moments_use_type_7_quantiles() {
        let m = moments(&[1.0, 2.0, 3.0, 4.0, 5.0]).unwrap();
        assert_eq!(m.median, 3.0);
        assert!((m.q05 - 1.2).abs() < 1e-12);
        assert!((m.sd - 2.5f64.sqrt()).abs() < 1e-12);
    }
}
