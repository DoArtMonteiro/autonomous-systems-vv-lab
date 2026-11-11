//! Replicate seeds and the protected-seed guard. The planner applies the guard to every seed before
//! any run starts; a single protected seed refuses the whole experiment.

use serde::{Deserialize, Serialize};

use crate::prng::mix;

/// A closed range of seeds that development work must not run.
#[derive(Clone, Copy, Debug)]
pub struct Protected {
    pub start: u64,
    pub end: u64,
    pub reason: &'static str,
}

/// Seeds the rocket domains refuse, as in `desktop/domain-rocket` and the M10 campaign script.
pub const ROCKET_PROTECTED: &[Protected] = &[
    Protected {
        start: 3000,
        end: 3099,
        reason: "M10 evaluation seeds",
    },
    Protected {
        start: 6000,
        end: 6099,
        reason: "M10 reserve seeds",
    },
    Protected {
        start: 44_000,
        end: 44_999,
        reason: "M13 reserve for a future preregistered confirmation; needs owner approval",
    },
];

/// Seeds the ground domain refuses. 100 to 129 is the hand-written M12 timing loop that ran without
/// a guard; it holds 101 to 112, the M6 development reserve. 201 to 212 is the M6 confirmation
/// reserve. The twelve seeds below are the M6 final confirmation, chosen by an independent
/// reviewer (`docs/m6-controller-repair.md`).
pub const GROUND_PROTECTED: &[Protected] = &[
    Protected {
        start: 100,
        end: 129,
        reason: "M6 reserved seeds 101-112 and the unguarded M12 timing range",
    },
    Protected {
        start: 201,
        end: 212,
        reason: "M6 confirmation seeds",
    },
    Protected {
        start: 44_000,
        end: 44_999,
        reason: "M13 reserve for a future preregistered confirmation; needs owner approval",
    },
    Protected {
        start: 7349,
        end: 7349,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 18265,
        end: 18265,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 29581,
        end: 29581,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 83017,
        end: 83017,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 156432,
        end: 156432,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 241907,
        end: 241907,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 318604,
        end: 318604,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 407753,
        end: 407753,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 536218,
        end: 536218,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 672941,
        end: 672941,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 794306,
        end: 794306,
        reason: "M6 final confirmation seed",
    },
    Protected {
        start: 921685,
        end: 921685,
        reason: "M6 final confirmation seed",
    },
];

/// Largest number of replicates per cell.
pub const MAX_REPLICATES: u64 = 100_000;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "mode", rename_all = "snake_case", deny_unknown_fields)]
pub enum SeedSpec {
    /// The listed seeds, in this order.
    List { values: Vec<u64> },
    /// `first`, `first + 1`, ..., `first + count - 1`.
    Range { first: u64, count: u64 },
    /// `count` distinct seeds in `[low, high]`, drawn from the experiment identity. With
    /// `common = true` every cell and arm uses the same seeds (common random numbers, needed for
    /// paired comparisons); otherwise each cell draws its own.
    Derived {
        low: u64,
        high: u64,
        count: u64,
        common: bool,
    },
}

impl SeedSpec {
    pub fn count(&self) -> u64 {
        match self {
            SeedSpec::List { values } => values.len() as u64,
            SeedSpec::Range { count, .. } | SeedSpec::Derived { count, .. } => *count,
        }
    }

    /// True when every cell and arm runs the same seed sequence.
    pub fn is_common(&self) -> bool {
        !matches!(self, SeedSpec::Derived { common: false, .. })
    }

    /// Structural checks that do not depend on the cell: count, bounds and protected seeds.
    pub fn validate(&self, protected: &[Protected]) -> Result<(), String> {
        let n = self.count();
        if n == 0 || n > MAX_REPLICATES {
            return Err(format!(
                "seeds: count must be in [1, {MAX_REPLICATES}], got {n}"
            ));
        }
        match self {
            SeedSpec::List { values } => {
                let mut sorted = values.clone();
                sorted.sort_unstable();
                if sorted.windows(2).any(|w| w[0] == w[1]) {
                    return Err("seeds.values contains a repeated seed".into());
                }
                for &s in values {
                    check(protected, s)?;
                }
            }
            SeedSpec::Range { first, count } => {
                let last = first
                    .checked_add(count - 1)
                    .ok_or("seeds: first + count overflows u64")?;
                check_span(protected, *first, last)?;
            }
            SeedSpec::Derived {
                low, high, count, ..
            } => {
                if low > high {
                    return Err("seeds: low must not exceed high".into());
                }
                let span = high - low;
                // At least four times as many candidates as draws, so distinct draws stay cheap.
                if span < count.saturating_mul(4) {
                    return Err(format!(
                        "seeds: [low, high] must hold at least 4 x count seeds, holds {}",
                        span.saturating_add(1)
                    ));
                }
                check_span(protected, *low, *high)?;
            }
        }
        Ok(())
    }

    /// Seeds of one cell, in replicate order. `key` identifies the experiment.
    pub fn seeds_for(&self, key: u64, stream: u64) -> Vec<u64> {
        match self {
            SeedSpec::List { values } => values.clone(),
            SeedSpec::Range { first, count } => (*first..*first + *count).collect(),
            SeedSpec::Derived {
                low,
                high,
                count,
                common,
            } => {
                let stream = if *common { 0 } else { stream + 1 };
                derived(key, stream, *low, *high, *count)
            }
        }
    }
}

/// `count` distinct seeds in `[low, high]`: draw `i` is `low + mix(key ^ mix(stream) + i) mod span`,
/// with a repeated draw replaced by the next counter value. Deterministic in all arguments. The
/// small modulo bias is irrelevant: the seeds only need to be distinct and reproducible.
fn derived(key: u64, stream: u64, low: u64, high: u64, count: u64) -> Vec<u64> {
    let span = (high - low).wrapping_add(1);
    let base = key ^ mix(stream);
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::with_capacity(count as usize);
    let mut i = 0u64;
    while (out.len() as u64) < count {
        let x = mix(base.wrapping_add(i));
        i += 1;
        let s = if span == 0 { x } else { low + x % span };
        if seen.insert(s) {
            out.push(s);
        }
    }
    out
}

pub fn check(protected: &[Protected], seed: u64) -> Result<(), String> {
    match protected.iter().find(|p| (p.start..=p.end).contains(&seed)) {
        Some(p) => Err(format!(
            "seed {seed} is protected ({} to {}): {}",
            p.start, p.end, p.reason
        )),
        None => Ok(()),
    }
}

/// Refuses a seed interval that meets any protected range.
pub fn check_span(protected: &[Protected], low: u64, high: u64) -> Result<(), String> {
    match protected.iter().find(|p| low <= p.end && p.start <= high) {
        Some(p) => Err(format!(
            "seeds {low} to {high} meet the protected range {} to {}: {}",
            p.start, p.end, p.reason
        )),
        None => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const P: &[Protected] = ROCKET_PROTECTED;

    #[test]
    fn refuses_both_ends_of_each_protected_range_and_accepts_neighbours() {
        for p in P {
            assert!(check(P, p.start).is_err());
            assert!(check(P, p.end).is_err());
            assert!(check(P, p.start - 1).is_ok());
            assert!(check(P, p.end + 1).is_ok());
        }
    }

    #[test]
    fn a_range_or_derived_space_touching_a_protected_seed_is_refused() {
        let r = SeedSpec::Range {
            first: 2990,
            count: 11,
        };
        assert!(r.validate(P).is_err());
        let r = SeedSpec::Range {
            first: 2990,
            count: 10,
        };
        assert!(r.validate(P).is_ok());
        let d = SeedSpec::Derived {
            low: 6099,
            high: 9000,
            count: 10,
            common: true,
        };
        assert!(d.validate(P).is_err());
        let l = SeedSpec::List {
            values: vec![1, 6050],
        };
        assert!(l.validate(P).is_err());
    }

    #[test]
    fn derived_seeds_are_distinct_in_range_and_reproducible() {
        let d = SeedSpec::Derived {
            low: 10_000,
            high: 10_400,
            count: 100,
            common: false,
        };
        d.validate(P).unwrap();
        let a = d.seeds_for(42, 3);
        assert_eq!(a, d.seeds_for(42, 3));
        assert_ne!(a, d.seeds_for(42, 4));
        let mut s = a.clone();
        s.sort_unstable();
        s.dedup();
        assert_eq!(s.len(), 100);
        assert!(a.iter().all(|x| (10_000..=10_400).contains(x)));
    }

    #[test]
    fn common_seeds_ignore_the_cell_stream() {
        let d = SeedSpec::Derived {
            low: 10_000,
            high: 20_000,
            count: 5,
            common: true,
        };
        assert_eq!(d.seeds_for(9, 0), d.seeds_for(9, 77));
    }

    #[test]
    fn both_domains_refuse_the_confirmation_reserve() {
        for p in [ROCKET_PROTECTED, GROUND_PROTECTED] {
            assert!(check(p, 44_000).is_err());
            assert!(check(p, 44_999).is_err());
            assert!(check(p, 43_999).is_ok());
            assert!(check(p, 45_000).is_ok());
        }
    }

    /// The M13 reserve is declared in the guards of this crate and in the manifest of every desktop
    /// domain. They must name exactly the same closed range, so none can drift and let a seed through.
    #[test]
    fn every_declaration_of_the_confirmation_reserve_agrees() {
        use crate::investigate::INVESTIGATION_PROTECTED;
        const RESERVE: (u64, u64) = (44_000, 44_999);
        let overlapping = |start: u64, end: u64| start <= RESERVE.1 && end >= RESERVE.0;
        for (name, list) in [
            ("ROCKET_PROTECTED", ROCKET_PROTECTED),
            ("GROUND_PROTECTED", GROUND_PROTECTED),
            ("INVESTIGATION_PROTECTED", INVESTIGATION_PROTECTED),
        ] {
            let hits: Vec<(u64, u64)> = list
                .iter()
                .filter(|r| overlapping(r.start, r.end))
                .map(|r| (r.start, r.end))
                .collect();
            assert_eq!(hits, vec![RESERVE], "{name}");
        }
        let desktop = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../desktop");
        for domain in ["domain-ascent", "domain-ground", "domain-rocket"] {
            let path = desktop.join(domain).join("domain.json");
            let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
            let manifest: serde_json::Value = serde_json::from_str(&text).unwrap();
            let hits: Vec<(u64, u64)> = manifest["seeds"]["protected"]
                .as_array()
                .unwrap_or_else(|| panic!("{domain}: no protected seed ranges"))
                .iter()
                .map(|r| (r["start"].as_u64().unwrap(), r["end"].as_u64().unwrap()))
                .filter(|(start, end)| overlapping(*start, *end))
                .collect();
            assert_eq!(hits, vec![RESERVE], "{domain}/domain.json");
        }
    }

    #[test]
    fn repeated_listed_seeds_are_refused() {
        let l = SeedSpec::List { values: vec![5, 5] };
        assert!(l.validate(P).is_err());
    }
}
