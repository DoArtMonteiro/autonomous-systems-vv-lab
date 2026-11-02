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

/// Fixed-size square matrix for the M10 navigation filter (docs/m10-resilient-navigation.md).
/// Row-major, no allocation, `+ - * /` and `sqrt` only.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Mat<const N: usize>(pub [[f64; N]; N]);

// Index loops mirror the matrix formulas; iterator rewrites would obscure them.
#[allow(clippy::needless_range_loop)]
impl<const N: usize> Mat<N> {
    pub const ZERO: Mat<N> = Mat([[0.0; N]; N]);

    pub fn identity() -> Self {
        let mut m = Self::ZERO;
        for i in 0..N {
            m.0[i][i] = 1.0;
        }
        m
    }

    pub fn diag(d: [f64; N]) -> Self {
        let mut m = Self::ZERO;
        for i in 0..N {
            m.0[i][i] = d[i];
        }
        m
    }

    pub fn mul(&self, o: &Mat<N>) -> Mat<N> {
        let mut m = Self::ZERO;
        for i in 0..N {
            for k in 0..N {
                let a = self.0[i][k];
                if a == 0.0 {
                    continue;
                }
                for j in 0..N {
                    m.0[i][j] += a * o.0[k][j];
                }
            }
        }
        m
    }

    pub fn transpose(&self) -> Mat<N> {
        let mut m = Self::ZERO;
        for i in 0..N {
            for j in 0..N {
                m.0[i][j] = self.0[j][i];
            }
        }
        m
    }

    pub fn add(&self, o: &Mat<N>) -> Mat<N> {
        let mut m = *self;
        for i in 0..N {
            for j in 0..N {
                m.0[i][j] += o.0[i][j];
            }
        }
        m
    }

    /// `A P A^T`.
    pub fn congruence(&self, p: &Mat<N>) -> Mat<N> {
        self.mul(p).mul(&self.transpose())
    }

    pub fn mul_vec(&self, v: &[f64; N]) -> [f64; N] {
        let mut out = [0.0; N];
        for (i, row) in self.0.iter().enumerate() {
            out[i] = row.iter().zip(v).map(|(a, b)| a * b).sum();
        }
        out
    }

    /// `(P + P^T) / 2`.
    pub fn symmetrized(&self) -> Mat<N> {
        let mut m = *self;
        for i in 0..N {
            for j in (i + 1)..N {
                let s = 0.5 * (self.0[i][j] + self.0[j][i]);
                m.0[i][j] = s;
                m.0[j][i] = s;
            }
        }
        m
    }

    pub fn is_finite(&self) -> bool {
        self.0.iter().flatten().all(|x| x.is_finite())
    }

    /// Solves `P x = b` for a symmetric positive definite `P` by Cholesky; `None` if `P` is not.
    pub fn cholesky_solve(&self, b: &[f64; N]) -> Option<[f64; N]> {
        let mut l = Self::ZERO;
        for i in 0..N {
            for j in 0..=i {
                let mut s = self.0[i][j];
                for k in 0..j {
                    s -= l.0[i][k] * l.0[j][k];
                }
                if i == j {
                    if s <= 0.0 || !s.is_finite() {
                        return None;
                    }
                    l.0[i][i] = s.sqrt();
                } else {
                    l.0[i][j] = s / l.0[j][j];
                }
            }
        }
        let mut y = [0.0; N];
        for i in 0..N {
            let mut s = b[i];
            for k in 0..i {
                s -= l.0[i][k] * y[k];
            }
            y[i] = s / l.0[i][i];
        }
        let mut x = [0.0; N];
        for i in (0..N).rev() {
            let mut s = y[i];
            for k in (i + 1)..N {
                s -= l.0[k][i] * x[k];
            }
            x[i] = s / l.0[i][i];
        }
        Some(x)
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
    fn matrix_products_transpose_and_cholesky_solve() {
        let a = Mat([[2.0, 1.0, 0.0], [1.0, 3.0, 1.0], [0.0, 1.0, 4.0]]);
        assert_eq!(a.mul(&Mat::identity()), a);
        assert_eq!(a.transpose(), a);
        let b = Mat([[1.0, 2.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]);
        assert_eq!(b.mul(&b).0[0][1], 4.0);
        assert_eq!(b.congruence(&Mat::identity()), b.mul(&b.transpose()));
        let x = a.cholesky_solve(&[1.0, 2.0, 3.0]).unwrap();
        let back = a.mul_vec(&x);
        for (got, want) in back.iter().zip([1.0, 2.0, 3.0]) {
            assert!((got - want).abs() < 1e-12);
        }
        // Not positive definite: no solution, never a panic.
        assert!(
            Mat([[1.0, 2.0], [2.0, 1.0]])
                .cholesky_solve(&[1.0, 1.0])
                .is_none()
        );
        let s = Mat([[1.0, 2.0], [0.0, 1.0]]).symmetrized();
        assert_eq!(s.0[0][1], s.0[1][0]);
        assert!(!Mat([[f64::NAN]]).is_finite());
    }

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
