//! Planar vectors and platform-independent `exp`, `sin_cos` and `atan2` built from `+ - * /` only,
//! so a run is bit-identical on every platform (the standard library delegates these to the system
//! maths library, whose last bit may differ). `exp` is the one of `crates/vv-rocket/src/math.rs`.

use serde::Serialize;
use std::ops::{Add, Mul, Neg, Sub};

/// A vector in the inertial plane of the trajectory: origin at the centre of the Earth, `x` towards
/// downrange at the launch site, `z` towards the local vertical of the launch site.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Vec2 {
    pub x: f64,
    pub z: f64,
}

impl Vec2 {
    pub const ZERO: Vec2 = Vec2 { x: 0.0, z: 0.0 };

    pub const fn new(x: f64, z: f64) -> Self {
        Vec2 { x, z }
    }

    pub fn dot(self, o: Vec2) -> f64 {
        self.x * o.x + self.z * o.z
    }

    /// Scalar cross product `self.x o.z - self.z o.x`.
    pub fn cross(self, o: Vec2) -> f64 {
        self.x * o.z - self.z * o.x
    }

    pub fn norm(self) -> f64 {
        self.dot(self).sqrt()
    }

    /// Unit vector; the zero vector stays zero.
    pub fn unit(self) -> Vec2 {
        let n = self.norm();
        if n > 0.0 {
            self * (1.0 / n)
        } else {
            Vec2::ZERO
        }
    }

    pub fn is_finite(self) -> bool {
        self.x.is_finite() && self.z.is_finite()
    }
}

impl Add for Vec2 {
    type Output = Vec2;
    fn add(self, o: Vec2) -> Vec2 {
        Vec2::new(self.x + o.x, self.z + o.z)
    }
}

impl Sub for Vec2 {
    type Output = Vec2;
    fn sub(self, o: Vec2) -> Vec2 {
        Vec2::new(self.x - o.x, self.z - o.z)
    }
}

impl Mul<f64> for Vec2 {
    type Output = Vec2;
    fn mul(self, s: f64) -> Vec2 {
        Vec2::new(self.x * s, self.z * s)
    }
}

impl Neg for Vec2 {
    type Output = Vec2;
    fn neg(self) -> Vec2 {
        Vec2::new(-self.x, -self.z)
    }
}

const LN2_HI: f64 = f64::from_bits(0x3fe6_2e42_fee0_0000);
const LN2_LO: f64 = f64::from_bits(0x3dea_39ef_3579_3c76);
const INV_LN2: f64 = std::f64::consts::LOG2_E;
const PI: f64 = std::f64::consts::PI;
const FRAC_PI_2: f64 = std::f64::consts::FRAC_PI_2;
const FRAC_PI_6: f64 = std::f64::consts::FRAC_PI_6;
const SQRT_3: f64 = 1.732_050_807_568_877_2;
const TAN_PI_12: f64 = 0.267_949_192_431_122_7;

/// `e^x` from arithmetic only: Cody-Waite reduction `x = k ln 2 + r`, `|r| <= ln 2 / 2`,
/// a degree-13 Taylor polynomial for `e^r` and an exact scaling by `2^k`.
pub fn exp(x: f64) -> f64 {
    if x.is_nan() {
        return x;
    }
    if x > 709.78 {
        return f64::INFINITY;
    }
    if x < -745.2 {
        return 0.0;
    }
    let k = (x * INV_LN2).round();
    let r = (x - k * LN2_HI) - k * LN2_LO;
    let mut p = 1.0;
    for n in (1..=13).rev() {
        p = 1.0 + r * p / f64::from(n);
    }
    scale_by_power_of_two(p, k as i32)
}

fn scale_by_power_of_two(value: f64, k: i32) -> f64 {
    let mut v = value;
    let mut k = k;
    while k > 1000 {
        v *= pow2(1000);
        k -= 1000;
    }
    while k < -1000 {
        v *= pow2(-1000);
        k += 1000;
    }
    v * pow2(k)
}

fn pow2(k: i32) -> f64 {
    f64::from_bits(((1023 + k) as u64) << 52)
}

/// `(sin x, cos x)` for `|x| <= pi` (the only range the model uses: angles of the pitch programme
/// and of reference cases). Reflection into `[-pi/2, pi/2]` and Taylor series to degree 21 and 22.
pub fn sin_cos(x: f64) -> (f64, f64) {
    assert!(
        x.is_finite() && x.abs() <= PI + 1e-12,
        "sin_cos takes |x| <= pi"
    );
    // sin(pi - x) = sin x, cos(pi - x) = -cos x.
    let (y, flip) = if x > FRAC_PI_2 {
        (PI - x, true)
    } else if x < -FRAC_PI_2 {
        (-PI - x, true)
    } else {
        (x, false)
    };
    let y2 = y * y;
    let mut s = 1.0;
    let mut c = 1.0;
    for n in (1..=10).rev() {
        let n = f64::from(n);
        s = 1.0 - y2 * s / ((2.0 * n) * (2.0 * n + 1.0));
        c = 1.0 - y2 * c / ((2.0 * n - 1.0) * (2.0 * n));
    }
    let (s, c) = (y * s, c);
    if flip { (s, -c) } else { (s, c) }
}

/// `atan x` for any finite `x`: `atan x = pi/2 - atan(1/x)` beyond 1, then
/// `atan x = pi/6 + atan((x sqrt3 - 1)/(x + sqrt3))` beyond `tan(pi/12)`, then the series.
pub fn atan(x: f64) -> f64 {
    if x < 0.0 {
        return -atan(-x);
    }
    if x > 1.0 {
        return FRAC_PI_2 - atan(1.0 / x);
    }
    if x > TAN_PI_12 {
        return FRAC_PI_6 + atan_series((x * SQRT_3 - 1.0) / (x + SQRT_3));
    }
    atan_series(x)
}

fn atan_series(y: f64) -> f64 {
    // |y| <= tan(pi/12) = 0.268: 28 terms leave an error below 0.268^57 / 57.
    let y2 = y * y;
    let mut p = 0.0;
    for k in (0..28).rev() {
        let sign = if k % 2 == 0 { 1.0 } else { -1.0 };
        p = sign / f64::from(2 * k + 1) + y2 * p;
    }
    // p = sum (-1)^k y^(2k) / (2k+1) evaluated by Horner with alternating signs folded in.
    y * p
}

/// `atan2(y, x)` in `(-pi, pi]`.
pub fn atan2(y: f64, x: f64) -> f64 {
    if x > 0.0 {
        atan(y / x)
    } else if x < 0.0 {
        if y >= 0.0 {
            atan(y / x) + PI
        } else {
            atan(y / x) - PI
        }
    } else if y > 0.0 {
        FRAC_PI_2
    } else if y < 0.0 {
        -FRAC_PI_2
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exp_matches_the_platform_to_two_ulp_scale() {
        let mut worst: f64 = 0.0;
        for i in -2000..=2000 {
            let x = f64::from(i) * 0.05;
            let want = x.exp();
            worst = worst.max(((exp(x) - want) / want).abs());
        }
        assert!(worst < 1e-14, "{worst}");
        assert_eq!(exp(0.0), 1.0);
    }

    #[test]
    fn sin_cos_and_atan2_match_the_platform_within_1e_15() {
        let mut worst: f64 = 0.0;
        for i in -3141..=3141 {
            let x = f64::from(i) * 1e-3;
            let (s, c) = sin_cos(x);
            worst = worst.max((s - x.sin()).abs()).max((c - x.cos()).abs());
        }
        assert!(worst < 1e-15, "sin_cos {worst}");
        let mut worst: f64 = 0.0;
        for i in -60..=60 {
            for j in -60..=60 {
                let (y, x) = (f64::from(i) * 0.37, f64::from(j) * 0.41);
                worst = worst.max((atan2(y, x) - y.atan2(x)).abs());
            }
        }
        assert!(worst < 2e-15, "atan2 {worst}");
    }

    #[test]
    fn planar_cross_product_is_the_angular_momentum_sign() {
        let r = Vec2::new(0.0, 1.0);
        let v = Vec2::new(1.0, 0.0);
        assert_eq!(r.cross(v), -1.0);
        assert_eq!(Vec2::new(3.0, 4.0).norm(), 5.0);
    }
}
