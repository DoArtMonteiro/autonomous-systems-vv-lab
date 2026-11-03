//! SplitMix64 (Steele, Lea and Flood, 2014), the only pseudo-random generator of the engine. It
//! draws design points and bootstrap resamples. It never feeds a simulation: the domains keep
//! their own seeded generators.

#[derive(Clone, Debug)]
pub struct SplitMix64(u64);

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }

    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        mix(self.0)
    }

    /// Uniform in [0, 1) with 53 random bits.
    pub fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Uniform in [0, n) by rejection, without modulo bias. `n` must be positive.
    pub fn below(&mut self, n: u64) -> u64 {
        let zone = u64::MAX - (u64::MAX % n);
        loop {
            let x = self.next_u64();
            if x < zone {
                return x % n;
            }
        }
    }
}

/// The SplitMix64 finaliser: a bijection on u64.
pub fn mix(mut z: u64) -> u64 {
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_the_published_reference_sequence() {
        // Reference outputs for seed 1234567 from the SplitMix64 reference implementation.
        let mut g = SplitMix64::new(1_234_567);
        let got: Vec<u64> = (0..3).map(|_| g.next_u64()).collect();
        assert_eq!(
            got,
            [
                6_457_827_717_110_365_317,
                3_203_168_211_198_807_973,
                9_817_491_932_198_370_423
            ]
        );
    }

    #[test]
    fn below_stays_in_range_and_unit_floats_stay_in_unit_interval() {
        let mut g = SplitMix64::new(7);
        for _ in 0..10_000 {
            assert!(g.below(13) < 13);
            let u = g.next_f64();
            assert!((0.0..1.0).contains(&u));
        }
    }
}
