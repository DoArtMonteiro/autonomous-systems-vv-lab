//! Seed guard. The platform refuses a protected seed before any host process starts; each host
//! refuses it again (defence in depth), so neither layer alone is the only barrier.

use crate::contract::SeedPolicy;

pub fn check_seed(policy: &SeedPolicy, seed: u64) -> Result<(), String> {
    if seed < policy.min || seed > policy.max {
        return Err(format!(
            "seed {seed} is outside the range of this domain ({} to {})",
            policy.min, policy.max
        ));
    }
    for range in &policy.protected {
        if (range.start..=range.end).contains(&seed) {
            return Err(format!(
                "seed {seed} is protected ({} to {}): {}",
                range.start, range.end, range.reason
            ));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::contract::ProtectedRange;

    fn policy() -> SeedPolicy {
        SeedPolicy {
            min: 0,
            max: 10_000,
            protected: vec![ProtectedRange {
                start: 3000,
                end: 3099,
                reason: "evaluation".into(),
            }],
        }
    }

    #[test]
    fn refuses_both_ends_of_a_protected_range_and_accepts_neighbours() {
        let p = policy();
        assert!(check_seed(&p, 3000).is_err());
        assert!(check_seed(&p, 3099).is_err());
        assert!(check_seed(&p, 2999).is_ok());
        assert!(check_seed(&p, 3100).is_ok());
    }

    #[test]
    fn refuses_seeds_outside_the_domain_range() {
        assert!(check_seed(&policy(), 10_001).is_err());
    }
}
