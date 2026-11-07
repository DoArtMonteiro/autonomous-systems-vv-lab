//! SplitMix64 with one stream per source of randomness: the algorithm of
//! `crates/vv-rocket/src/prng.rs`, copied so this crate stays a standalone workspace.
//!
//! Only integer operations and `+ - * /` / `sqrt` on `f64` are used, so a stream is bit-identical
//! on every platform.

const GOLDEN: u64 = 0x9E37_79B9_7F4A_7C15;
const TWO_POW_53: f64 = 9_007_199_254_740_992.0;

/// Source identifiers. Appending a new source never changes the existing streams.
pub mod source {
    pub const STAGE1_THRUST: u64 = 1;
    pub const STAGE1_ISP: u64 = 2;
    pub const STAGE1_PROPELLANT: u64 = 3;
    pub const STAGE1_DRY_MASS: u64 = 4;
    pub const STAGE2_THRUST: u64 = 5;
    pub const STAGE2_ISP: u64 = 6;
    pub const STAGE2_PROPELLANT: u64 = 7;
    pub const STAGE2_DRY_MASS: u64 = 8;
    pub const NAV_POSITION: u64 = 9;
    pub const NAV_VELOCITY: u64 = 10;
}

#[derive(Clone, Debug)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(state: u64) -> Self {
        SplitMix64 { state }
    }

    /// Stream of one source: seed `seed ^ (source * 0x9E3779B97F4A7C15)`.
    pub fn stream(seed: u64, source: u64) -> Self {
        SplitMix64::new(seed ^ source.wrapping_mul(GOLDEN))
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(GOLDEN);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform in `[0, 1)` with 53 bits.
    pub fn uniform(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / TWO_POW_53
    }

    /// Irwin-Hall noise with standard deviation `sigma`: `sigma * sqrt(3) * (u1 + u2 + u3 + u4 - 2)`,
    /// limited to `+-2 sqrt(3) sigma`. Always consumes four draws.
    pub fn noise(&mut self, sigma: f64) -> f64 {
        let (u1, u2, u3, u4) = (
            self.uniform(),
            self.uniform(),
            self.uniform(),
            self.uniform(),
        );
        let root3 = 3.0_f64.sqrt();
        let bound = 2.0 * root3 * sigma;
        let value = sigma * root3 * (u1 + u2 + u3 + u4 - 2.0);
        value.clamp(-bound, bound)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splitmix64_matches_the_reference_vector_for_seed_zero() {
        let mut g = SplitMix64::new(0);
        assert_eq!(g.next_u64(), 0xe220_a839_7b1d_cdaf);
        assert_eq!(g.next_u64(), 0x6e78_9e6a_a1b9_65f4);
        assert_eq!(g.next_u64(), 0x06c4_5d18_8009_454f);
    }

    #[test]
    fn streams_are_independent_and_reproducible() {
        let draw = |seed, src| {
            let mut g = SplitMix64::stream(seed, src);
            (0..4).map(|_| g.next_u64()).collect::<Vec<_>>()
        };
        assert_eq!(draw(7, source::NAV_POSITION), draw(7, source::NAV_POSITION));
        assert_ne!(draw(7, source::NAV_POSITION), draw(7, source::NAV_VELOCITY));
    }

    #[test]
    fn noise_is_bounded_and_zero_sigma_is_exactly_zero() {
        let mut g = SplitMix64::new(42);
        for _ in 0..10_000 {
            assert!(g.noise(0.5).abs() <= 2.0 * 3.0_f64.sqrt() * 0.5);
        }
        assert_eq!(SplitMix64::new(1).noise(0.0), 0.0);
    }
}
