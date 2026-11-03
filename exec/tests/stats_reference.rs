//! The engine's statistics against `tests/fixtures/stats-reference.json`, produced by the
//! independent Python reference (`scripts/m12_stats_reference.py`, different algorithms).

use serde_json::Value;
use vv_exec::stats;

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/stats-reference.json")).unwrap()
}

fn pair(v: &Value) -> (f64, f64) {
    (v[0].as_f64().unwrap(), v[1].as_f64().unwrap())
}

fn u(v: &Value) -> u64 {
    v.as_u64().unwrap()
}

fn floats(v: &Value) -> Vec<f64> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_f64().unwrap())
        .collect()
}

#[test]
fn clopper_pearson_matches_the_binomial_tail_reference() {
    let f = fixture();
    let cases = f["clopper_pearson"].as_array().unwrap();
    assert!(cases.len() >= 30);
    for c in cases {
        let conf = c["confidence"].as_f64().unwrap();
        let (lo, hi) = stats::clopper_pearson(u(&c["k"]), u(&c["n"]), conf);
        let (rlo, rhi) = pair(&c["interval"]);
        assert!((lo - rlo).abs() < 1e-10, "{c}: lower {lo}");
        assert!((hi - rhi).abs() < 1e-10, "{c}: upper {hi}");
    }
}

#[test]
fn wilson_matches_the_reference_within_the_normal_quantile_accuracy() {
    // Acklam's quantile has relative error below 1.2e-9; the interval inherits about that.
    for c in fixture()["wilson"].as_array().unwrap() {
        let conf = c["confidence"].as_f64().unwrap();
        let (lo, hi) = stats::wilson(u(&c["k"]), u(&c["n"]), conf);
        let (rlo, rhi) = pair(&c["interval"]);
        assert!((lo - rlo).abs() < 1e-8, "{c}: lower {lo}");
        assert!((hi - rhi).abs() < 1e-8, "{c}: upper {hi}");
    }
}

#[test]
fn binomial_cdf_and_mcnemar_match_exact_arithmetic() {
    let f = fixture();
    for c in f["binomial_cdf"].as_array().unwrap() {
        let got = stats::binomial_cdf(u(&c["k"]), u(&c["n"]), c["p"].as_f64().unwrap());
        let want = c["value"].as_f64().unwrap();
        assert!((got - want).abs() <= 1e-12 * want.max(1e-12), "{c}: {got}");
    }
    for c in f["mcnemar"].as_array().unwrap() {
        let got = stats::mcnemar_exact(u(&c["b"]), u(&c["c"]));
        let want = c["p"].as_f64().unwrap();
        assert!((got - want).abs() <= 1e-12 * want.max(1e-12), "{c}: {got}");
    }
}

#[test]
fn holm_matches_the_reference_exactly() {
    for c in fixture()["holm"].as_array().unwrap() {
        let got = stats::holm(&floats(&c["p"]));
        for (g, w) in got.iter().zip(floats(&c["adjusted"])) {
            assert!((g - w).abs() < 1e-15, "{c}: {got:?}");
        }
    }
}

#[test]
fn the_reference_ishigami_values_match_the_published_ones() {
    let i = &fixture()["ishigami"];
    // Published values for a = 7, b = 0.1 (Sobol' and Levitan 1999), to four decimals.
    for (got, want) in floats(&i["first_order"]).iter().zip([0.3139, 0.4424, 0.0]) {
        assert!((got - want).abs() < 5e-5, "S1 {got}");
    }
    for (got, want) in floats(&i["total"]).iter().zip([0.5576, 0.4424, 0.2437]) {
        assert!((got - want).abs() < 5e-5, "ST {got}");
    }
}
