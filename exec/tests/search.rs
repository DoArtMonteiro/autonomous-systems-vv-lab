//! M14 falsification search: determinism, recomputation, tamper detection, the seed guard and
//! minimisation. All output goes under Cargo's per-target temporary directory.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Value, json};
use vv_exec::search::{self, SearchResult};

fn scratch(name: &str) -> PathBuf {
    let d = Path::new(env!("CARGO_TARGET_TMPDIR")).join(name);
    if d.exists() {
        fs::remove_dir_all(&d).unwrap();
    }
    d
}

fn base() -> Vec<u8> {
    fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("cases/m14/ground-zone-corridor.json"))
        .unwrap()
}

fn spec(strategy: Value, extra: Value) -> Vec<u8> {
    let mut v = json!({
        "schema": "vv-search.v1",
        "id": "search-test",
        "domain": "ground-m4",
        "base_case": "unused",
        "parameters": [
            {"name": "gps_noise", "pointer": "/scenario/sensors/gps/noise_max_mm", "unit": "mm", "low": 0, "high": 600, "integer": true},
            {"name": "delay", "pointer": "/scenario/sensors/communication/delay_max_ticks", "unit": "ticks", "low": 0, "high": 3, "integer": true}
        ],
        "seed_pool": {"low": 30000, "high": 30999},
        "target": "safety",
        "objective": {"metric": "margin.restricted_zone_mm", "direction": "minimise"},
        "strategy": strategy,
        "budget": 40,
        "repetitions": 3,
        "search_seed": 7,
        "minimise_budget": 20,
        "limits": {"max_evaluations": 10000, "max_wall_s": 120}
    });
    if let Value::Object(m) = extra {
        for (k, x) in m {
            v[k] = x;
        }
    }
    serde_json::to_vec(&v).unwrap()
}

#[test]
fn every_strategy_is_deterministic_and_recomputable() {
    for (i, strategy) in [
        json!({"kind": "random"}),
        json!({"kind": "halton"}),
        json!({"kind": "extremes"}),
        json!({"kind": "adaptive", "initial": 4, "sigma": 0.2, "patience": 6}),
    ]
    .into_iter()
    .enumerate()
    {
        let s = spec(strategy, json!({}));
        let (a, b) = (
            scratch(&format!("search-a{i}")),
            scratch(&format!("search-b{i}")),
        );
        let ra: SearchResult = search::execute(&s, &base(), &a, 4).expect("search");
        let rb = search::execute(&s, &base(), &b, 1).expect("search");
        assert_eq!(
            ra.log_sha256, rb.log_sha256,
            "thread count must not change the log"
        );
        assert_eq!(ra.repetitions, rb.repetitions);
        assert_eq!(
            fs::read(a.join("evaluations.jsonl")).unwrap(),
            fs::read(b.join("evaluations.jsonl")).unwrap()
        );
        let v = search::verify(&a, 4).expect("verify");
        assert!(v.pass, "{v:?}");
        for r in &ra.repetitions {
            assert_eq!(r.evaluations, 40);
            for c in &r.classes {
                assert!(c.deviation_after <= c.deviation_before + 1e-12);
                assert!(c.found_at >= 1 && c.found_at <= 40);
            }
        }
    }
}

#[test]
fn a_tampered_log_fails_verification_even_when_rehashed() {
    let s = spec(json!({"kind": "random"}), json!({}));
    let out = scratch("search-tamper");
    search::execute(&s, &base(), &out, 2).expect("search");
    let text = fs::read_to_string(out.join("evaluations.jsonl")).unwrap();
    // Flip the verdict of the first violating evaluation and rewrite its line hash.
    let mut lines: Vec<String> = text.lines().map(String::from).collect();
    let i = lines
        .iter()
        .position(|l| l.contains("\"violated\":true"))
        .expect("a violation in the trial box");
    let json_part = lines[i]
        .split_once(' ')
        .unwrap()
        .1
        .replace("\"violated\":true", "\"violated\":false");
    lines[i] = search::log_line(&serde_json::from_str(&json_part).unwrap())
        .trim_end()
        .to_string();
    fs::write(out.join("evaluations.jsonl"), lines.join("\n") + "\n").unwrap();
    let v = search::verify(&out, 2).expect("verify runs");
    assert!(!v.pass);
    assert!(!v.mismatches.is_empty());
    assert!(!v.hashes_match);
}

#[test]
fn a_seed_pool_that_meets_a_reserve_is_refused() {
    let s = spec(
        json!({"kind": "random"}),
        json!({"seed_pool": {"low": 29000, "high": 30000}}),
    );
    let err = search::execute(&s, &base(), &scratch("search-guard"), 1).expect_err("refused");
    assert!(err.contains("29581"), "{err}");
}

#[test]
fn minimisation_keeps_class_and_seed() {
    let s = spec(json!({"kind": "random"}), json!({"repetitions": 2}));
    let out = scratch("search-minimise");
    let r = search::execute(&s, &base(), &out, 2).expect("search");
    let evals =
        search::parse_log(&fs::read_to_string(out.join("evaluations.jsonl")).unwrap()).unwrap();
    let mut checked = 0;
    for rep in &r.repetitions {
        for c in rep.classes.iter().filter(|c| c.minimise_evaluations > 0) {
            // The minimised point, run again with its seed, still shows the same class.
            let hit = evals.iter().find(|e| {
                e.repetition == rep.repetition
                    && e.phase == search::Phase::Minimise
                    && e.q == c.minimised_q
                    && e.seed == c.seed
            });
            if let Some(e) = hit {
                assert!(e.violated);
                assert_eq!(e.class(), c.class);
                checked += 1;
            } else {
                // Nothing moved: the found point itself is the minimum.
                assert_eq!(c.q, c.minimised_q);
            }
        }
    }
    assert!(checked > 0);
}

#[test]
fn the_adaptive_strategy_needs_an_objective() {
    let mut v: Value = serde_json::from_slice(&spec(
        json!({"kind": "adaptive", "initial": 4, "sigma": 0.2, "patience": 6}),
        json!({}),
    ))
    .unwrap();
    v.as_object_mut().unwrap().remove("objective");
    let err = search::SearchSpec::parse(&serde_json::to_vec(&v).unwrap()).expect_err("refused");
    assert!(err.contains("objective"), "{err}");
}
