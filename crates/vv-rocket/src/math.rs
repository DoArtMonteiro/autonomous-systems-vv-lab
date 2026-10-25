//! Vectors, quaternions and a platform-independent `exp`.
//!
//! Only `+ - * /` and `sqrt` are used, which IEEE 754 requires to be correctly rounded,
//! so results are bit-identical on every IEEE platform.

use std::ops::{Add, Mul, Neg, Sub};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vec3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl Vec3 {
    pub const ZERO: Vec3 = Vec3::new(0.0, 0.0, 0.0);

    pub const fn new(x: f64, y: f64, z: f64) -> Self {
        Vec3 { x, y, z }
    }

    pub fn from_array(a: [f64; 3]) -> Self {
        Vec3::new(a[0], a[1], a[2])
    }

    pub fn to_array(self) -> [f64; 3] {
        [self.x, self.y, self.z]
    }

    pub fn dot(self, o: Vec3) -> f64 {
        self.x * o.x + self.y * o.y + self.z * o.z
    }

    pub fn cross(self, o: Vec3) -> Vec3 {
        Vec3::new(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )
    }

    pub fn norm(self) -> f64 {
        self.dot(self).sqrt()
    }

    /// Component-wise product: a diagonal tensor applied to a vector.
    pub fn hadamard(self, o: Vec3) -> Vec3 {
        Vec3::new(self.x * o.x, self.y * o.y, self.z * o.z)
    }

    pub fn is_finite(self) -> bool {
        self.x.is_finite() && self.y.is_finite() && self.z.is_finite()
    }
}

impl Add for Vec3 {
    type Output = Vec3;
    fn add(self, o: Vec3) -> Vec3 {
        Vec3::new(self.x + o.x, self.y + o.y, self.z + o.z)
    }
}

impl Sub for Vec3 {
    type Output = Vec3;
    fn sub(self, o: Vec3) -> Vec3 {
        Vec3::new(self.x - o.x, self.y - o.y, self.z - o.z)
    }
}

impl Mul<f64> for Vec3 {
    type Output = Vec3;
    fn mul(self, s: f64) -> Vec3 {
        Vec3::new(self.x * s, self.y * s, self.z * s)
    }
}

impl Neg for Vec3 {
    type Output = Vec3;
    fn neg(self) -> Vec3 {
        Vec3::new(-self.x, -self.y, -self.z)
    }
}

impl Add for Quat {
    type Output = Quat;
    fn add(self, o: Quat) -> Quat {
        Quat::new(self.w + o.w, self.x + o.x, self.y + o.y, self.z + o.z)
    }
}

/// Hamilton quaternion, scalar first. A unit quaternion maps body components to inertial ones.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Quat {
    pub w: f64,
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl Quat {
    pub const IDENTITY: Quat = Quat::new(1.0, 0.0, 0.0, 0.0);

    pub const fn new(w: f64, x: f64, y: f64, z: f64) -> Self {
        Quat { w, x, y, z }
    }

    pub fn from_array(a: [f64; 4]) -> Self {
        Quat::new(a[0], a[1], a[2], a[3])
    }

    pub fn to_array(self) -> [f64; 4] {
        [self.w, self.x, self.y, self.z]
    }

    pub fn vector(self) -> Vec3 {
        Vec3::new(self.x, self.y, self.z)
    }

    pub fn conj(self) -> Quat {
        Quat::new(self.w, -self.x, -self.y, -self.z)
    }

    pub fn norm(self) -> f64 {
        (self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z).sqrt()
    }

    pub fn scale(self, s: f64) -> Quat {
        Quat::new(self.w * s, self.x * s, self.y * s, self.z * s)
    }

    pub fn normalized(self) -> Quat {
        self.scale(1.0 / self.norm())
    }

    /// Hamilton product `self ⊗ o`.
    pub fn hamilton(self, o: Quat) -> Quat {
        Quat::new(
            self.w * o.w - self.x * o.x - self.y * o.y - self.z * o.z,
            self.w * o.x + self.x * o.w + self.y * o.z - self.z * o.y,
            self.w * o.y - self.x * o.z + self.y * o.w + self.z * o.x,
            self.w * o.z + self.x * o.y - self.y * o.x + self.z * o.w,
        )
    }

    /// `R(q) v = q ⊗ (0, v) ⊗ q*` for a unit quaternion: body to inertial.
    pub fn rotate(self, v: Vec3) -> Vec3 {
        let u = self.vector();
        let t = u.cross(v) * 2.0;
        v + t * self.w + u.cross(t)
    }

    /// `R(q)ᵀ v`: inertial to body.
    pub fn rotate_inverse(self, v: Vec3) -> Vec3 {
        self.conj().rotate(v)
    }
}

// fdlibm's split of ln 2: the low 21 bits of LN2_HI are zero, so k * LN2_HI is exact for |k| < 2^21.
const LN2_HI: f64 = f64::from_bits(0x3fe6_2e42_fee0_0000);
const LN2_LO: f64 = f64::from_bits(0x3dea_39ef_3579_3c76);
const INV_LN2: f64 = std::f64::consts::LOG2_E;

/// `e^x` from arithmetic only: Cody-Waite reduction `x = k ln 2 + r`, `|r| ≤ ln 2 / 2`,
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
    // Split the exponent so each factor is a normal power of two; products by powers of two are exact
    // except for the final rounding into the subnormal range.
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exp_matches_the_platform_within_the_documented_tolerance() {
        let mut worst: f64 = 0.0;
        let mut x: f64 = -12.0;
        while x <= 2.0 {
            let want = x.exp();
            worst = worst.max(((exp(x) - want) / want).abs());
            x += 0.000_7;
        }
        assert!(worst <= 1e-15, "worst relative error {worst:e}");
        assert_eq!(exp(0.0), 1.0);
        assert_eq!(exp(-800.0), 0.0);
        assert_eq!(exp(800.0), f64::INFINITY);
        assert!((exp(-700.0) / (-700.0f64).exp() - 1.0).abs() < 1e-14);
    }

    #[test]
    fn quaternion_rotation_is_the_hamilton_sandwich() {
        let q = Quat::new(0.3, -0.5, 0.7, 0.2).normalized();
        let v = Vec3::new(1.5, -2.0, 0.25);
        let sandwich = q
            .hamilton(Quat::new(0.0, v.x, v.y, v.z))
            .hamilton(q.conj())
            .vector();
        assert!((q.rotate(v) - sandwich).norm() <= 1e-14 * v.norm());
    }
}
