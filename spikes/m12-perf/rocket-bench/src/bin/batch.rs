//! M12 prototype: run many seeds of one landing case in one process, with the canonical
//! `landing_run::write_landing`, so each seed directory holds the same four files that
//! `vv-rocket land` writes. Removes one process creation per run (about 20 ms on the audit machine).
//!
//! usage: batch <case.json> <first_seed> <count> <out_root> [threads]
//!
//! Development seeds only: the protected M10 ranges 3000-3099 and 6000-6099 are refused.
//! The order of seeds is fixed; threads only change wall time, never bytes.

use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use vv_rocket::landing_run::write_landing;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 5 {
        eprintln!("usage: batch <case.json> <first_seed> <count> <out_root> [threads]");
        std::process::exit(3);
    }
    let case = PathBuf::from(&a[1]);
    let first: u64 = a[2].parse().expect("seed");
    let count: u64 = a[3].parse().expect("count");
    let root = PathBuf::from(&a[4]);
    let threads: usize = a.get(5).map_or(1, |s| s.parse().expect("threads"));
    let seeds: Vec<u64> = (first..first + count).collect();
    if seeds
        .iter()
        .any(|s| (3000..3100).contains(s) || (6000..6100).contains(s))
    {
        eprintln!("refused: protected M10 evaluation or reserve seed in range");
        std::process::exit(3);
    }
    let next = AtomicUsize::new(0);
    let t0 = Instant::now();
    let failures: usize = std::thread::scope(|sc| {
        let hs: Vec<_> = (0..threads.max(1))
            .map(|_| {
                sc.spawn(|| {
                    let mut bad = 0;
                    loop {
                        let i = next.fetch_add(1, Ordering::Relaxed);
                        let Some(&seed) = seeds.get(i) else { break bad };
                        if let Err(e) = write_landing(&case, seed, &root.join(seed.to_string())) {
                            eprintln!("seed {seed}: {e}");
                            bad += 1;
                        }
                    }
                })
            })
            .collect();
        hs.into_iter().map(|h| h.join().unwrap()).sum()
    });
    let wall = t0.elapsed().as_secs_f64();
    println!(
        "{{\"runs\":{},\"threads\":{},\"wall_s\":{wall},\"runs_per_s\":{},\"errors\":{failures}}}",
        seeds.len(),
        threads,
        seeds.len() as f64 / wall
    );
}
