//! Times each phase of one canonical landing run in-process, over a seed range, and checks that
//! the in-process pipeline reproduces `landing_run::artifacts` byte for byte.
//!
//! usage: m12-rocket-bench <case.json> <first_seed> <count> [threads]
//!
//! Development seeds only. The tool refuses the protected M10 ranges 3000-3099 and 6000-6099.

use std::time::Instant;

use vv_rocket::landing_model::{LandingCase, prepare_landing};
use vv_rocket::landing_run::artifacts;
use vv_rocket::landing_sim::simulate_landing;
use vv_rocket::landing_verify::verify;
use vv_rocket::nav_verify::verify_navigation;
use vv_rocket::sha256_hex;

#[derive(Default, Clone, Copy)]
struct Phases {
    parse: f64,
    prepare: f64,
    simulate: f64,
    verify: f64,
    serialize: f64,
    hash: f64,
    steps: u64,
    trace_bytes: usize,
}

fn run_one(bytes: &[u8], seed: u64) -> Phases {
    let mut p = Phases::default();
    let t = Instant::now();
    let case: LandingCase = serde_json::from_slice(bytes).expect("case");
    p.parse = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let prep = prepare_landing(&case, seed).expect("prepare");
    p.prepare = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let run = simulate_landing(&prep).expect("simulate");
    p.simulate = t.elapsed().as_secs_f64();
    p.steps = run.trace.summary.steps;
    let t = Instant::now();
    let mut v = verify(&prep, &run.log);
    v.controller_flags.flags = run.controller_flags;
    if prep.controller.policy.is_m10() {
        v.navigation = Some(verify_navigation(&prep, &run.log, &run.declarations, &v));
    }
    p.verify = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let trace = serde_json::to_vec(&run.trace).expect("trace");
    let ver = serde_json::to_vec(&v).expect("verification");
    p.serialize = t.elapsed().as_secs_f64();
    p.trace_bytes = trace.len();
    let t = Instant::now();
    let _ = (sha256_hex(&trace), sha256_hex(&ver));
    p.hash = t.elapsed().as_secs_f64();
    p
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 4 {
        eprintln!("usage: m12-rocket-bench <case.json> <first_seed> <count> [threads]");
        std::process::exit(3);
    }
    let bytes = std::fs::read(&a[1]).expect("read case");
    let first: u64 = a[2].parse().expect("seed");
    let count: u64 = a[3].parse().expect("count");
    let threads: usize = a.get(4).map_or(1, |s| s.parse().expect("threads"));
    let seeds: Vec<u64> = (first..first + count).collect();
    if seeds
        .iter()
        .any(|s| (3000..3100).contains(s) || (6000..6100).contains(s))
    {
        eprintln!("refused: protected M10 evaluation or reserve seed in range");
        std::process::exit(3);
    }

    // Equivalence: the timed decomposition must give the canonical trace bytes.
    let canon = artifacts(&bytes, seeds[0]).expect("artifacts");
    let case: LandingCase = serde_json::from_slice(&bytes).unwrap();
    let prep = prepare_landing(&case, seeds[0]).unwrap();
    let mut mine = serde_json::to_vec(&simulate_landing(&prep).unwrap().trace).unwrap();
    mine.push(b'\n');
    assert_eq!(
        mine, canon.trace,
        "in-process trace differs from canonical artifacts()"
    );

    let t0 = Instant::now();
    let results: Vec<Phases> = if threads <= 1 {
        seeds.iter().map(|&s| run_one(&bytes, s)).collect()
    } else {
        let chunks: Vec<Vec<u64>> = (0..threads)
            .map(|i| seeds.iter().copied().skip(i).step_by(threads).collect())
            .collect();
        std::thread::scope(|sc| {
            let hs: Vec<_> = chunks
                .iter()
                .map(|c| sc.spawn(|| c.iter().map(|&s| run_one(&bytes, s)).collect::<Vec<_>>()))
                .collect();
            hs.into_iter().flat_map(|h| h.join().unwrap()).collect()
        })
    };
    let wall = t0.elapsed().as_secs_f64();
    let n = results.len() as f64;
    let sum = |f: fn(&Phases) -> f64| results.iter().map(f).sum::<f64>();
    let steps: u64 = results.iter().map(|p| p.steps).sum();
    let total = sum(|p| p.parse + p.prepare + p.simulate + p.verify + p.serialize + p.hash);
    println!(
        "{}",
        serde_json::json!({
            "case": a[1], "first_seed": first, "runs": results.len(), "threads": threads,
            "wall_s": wall, "runs_per_s": n / wall, "sim_steps_per_s": steps as f64 / wall,
            "mean_ms": {
                "parse": 1e3 * sum(|p| p.parse) / n, "prepare": 1e3 * sum(|p| p.prepare) / n,
                "simulate": 1e3 * sum(|p| p.simulate) / n, "verify": 1e3 * sum(|p| p.verify) / n,
                "serialize": 1e3 * sum(|p| p.serialize) / n, "hash": 1e3 * sum(|p| p.hash) / n,
                "total": 1e3 * total / n,
            },
            "share": {
                "simulate": sum(|p| p.simulate) / total, "verify": sum(|p| p.verify) / total,
                "serialize": sum(|p| p.serialize) / total, "hash": sum(|p| p.hash) / total,
            },
            "mean_steps": steps as f64 / n,
            "mean_trace_bytes": results.iter().map(|p| p.trace_bytes).sum::<usize>() as f64 / n,
            "equivalence_check": "trace bytes equal landing_run::artifacts for first seed",
        })
    );
}
