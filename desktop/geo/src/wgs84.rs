//! WGS84 geodesy and local east-north-up frames.
//!
//! Conventions: latitude and longitude in degrees (positive north and east), ellipsoidal height in
//! metres above the WGS84 ellipsoid (not above mean sea level), ECEF in metres. ENU axes at an
//! origin: east is tangent to the parallel, north tangent to the meridian, up along the ellipsoid
//! normal. The model frame of a run maps to ENU by a rotation about up by the heading.

use serde::Serialize;

/// Semi-major axis (m).
pub const A: f64 = 6_378_137.0;
/// Flattening.
pub const F: f64 = 1.0 / 298.257_223_563;
/// First eccentricity squared.
pub const E2: f64 = F * (2.0 - F);

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Geodetic {
    pub lat_deg: f64,
    pub lon_deg: f64,
    pub h_m: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Ecef {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl Geodetic {
    pub fn new(lat_deg: f64, lon_deg: f64, h_m: f64) -> Self {
        Self {
            lat_deg,
            lon_deg,
            h_m,
        }
    }

    pub fn to_ecef(self) -> Ecef {
        let (sl, cl) = self.lat_deg.to_radians().sin_cos();
        let (so, co) = self.lon_deg.to_radians().sin_cos();
        let n = A / (1.0 - E2 * sl * sl).sqrt();
        Ecef {
            x: (n + self.h_m) * cl * co,
            y: (n + self.h_m) * cl * so,
            z: (n * (1.0 - E2) + self.h_m) * sl,
        }
    }
}

impl Ecef {
    /// Geodetic coordinates by fixed-point iteration on the latitude (converges to better than
    /// 1e-12 rad in a few steps for any point outside the Earth's core). The height uses the form
    /// `p cos φ + z sin φ − a √(1 − e² sin² φ)`, which stays accurate at the poles.
    pub fn to_geodetic(self) -> Geodetic {
        let p = self.x.hypot(self.y);
        let lon = self.y.atan2(self.x);
        let mut lat = self.z.atan2(p * (1.0 - E2));
        for _ in 0..20 {
            let s = lat.sin();
            let n = A / (1.0 - E2 * s * s).sqrt();
            let next = (self.z + E2 * n * s).atan2(p);
            let done = (next - lat).abs() < 1e-14;
            lat = next;
            if done {
                break;
            }
        }
        let (s, c) = lat.sin_cos();
        let h = p * c + self.z * s - A * (1.0 - E2 * s * s).sqrt();
        Geodetic {
            lat_deg: lat.to_degrees(),
            lon_deg: lon.to_degrees(),
            h_m: h,
        }
    }
}

/// The east-north-up frame at an origin, and the model frame of a run rotated in it by a heading.
#[derive(Clone, Copy, Debug)]
pub struct Enu {
    pub origin: Geodetic,
    o: Ecef,
    /// Rows: unit east, north and up in ECEF.
    r: [[f64; 3]; 3],
    /// Heading of the model +y axis, clockwise from true north (degrees).
    heading_deg: f64,
}

impl Enu {
    pub fn new(origin: Geodetic, heading_deg: f64) -> Self {
        let (sl, cl) = origin.lat_deg.to_radians().sin_cos();
        let (so, co) = origin.lon_deg.to_radians().sin_cos();
        Self {
            origin,
            o: origin.to_ecef(),
            r: [
                [-so, co, 0.0],
                [-sl * co, -sl * so, cl],
                [cl * co, cl * so, sl],
            ],
            heading_deg,
        }
    }

    /// ENU components of an ECEF point.
    pub fn enu_of(&self, p: Ecef) -> [f64; 3] {
        let d = [p.x - self.o.x, p.y - self.o.y, p.z - self.o.z];
        let row = |k: usize| self.r[k][0] * d[0] + self.r[k][1] * d[1] + self.r[k][2] * d[2];
        [row(0), row(1), row(2)]
    }

    /// ECEF point of ENU components.
    pub fn ecef_of(&self, enu: [f64; 3]) -> Ecef {
        let col = |k: usize| self.r[0][k] * enu[0] + self.r[1][k] * enu[1] + self.r[2][k] * enu[2];
        Ecef {
            x: self.o.x + col(0),
            y: self.o.y + col(1),
            z: self.o.z + col(2),
        }
    }

    /// ENU of a model point (x, y, z): the model frame rotated by the heading about up.
    pub fn enu_of_model(&self, m: [f64; 3]) -> [f64; 3] {
        let (s, c) = self.heading_deg.to_radians().sin_cos();
        // Model +y points at the heading; model +x is 90 degrees clockwise of it.
        [m[0] * c + m[1] * s, -m[0] * s + m[1] * c, m[2]]
    }

    pub fn geodetic_of_model(&self, m: [f64; 3]) -> Geodetic {
        self.ecef_of(self.enu_of_model(m)).to_geodetic()
    }

    pub fn heading_deg(&self) -> f64 {
        self.heading_deg
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Reference ECEF coordinates computed with PROJ 9.8.1 (pyproj 3.8.0, EPSG:4979 to EPSG:4978).
    // The 33.3 / 44.4 / 6000 case is also the published GeographicLib CartConvert example.
    const PROJ: [(f64, f64, f64, f64, f64, f64); 8] = [
        (0.0, 0.0, 0.0, 6378137.0, 0.0, 0.0),
        (
            90.0,
            0.0,
            0.0,
            3.9186209248144716e-10,
            0.0,
            6356752.314245179,
        ),
        (
            -90.0,
            0.0,
            0.0,
            3.9186209248144716e-10,
            0.0,
            -6356752.314245179,
        ),
        (
            33.3,
            44.4,
            6000.0,
            3816209.6044930913,
            3737108.550254264,
            3485109.572568041,
        ),
        (
            28.486,
            -80.543,
            -26.598,
            921798.684306899,
            -5533962.031955696,
            3023940.4825041476,
        ),
        (
            -33.8688,
            151.2093,
            58.0,
            -4646093.477288303,
            2553229.5358170713,
            -3534404.710910369,
        ),
        (
            89.999,
            45.0,
            1000.0,
            78.99191170144533,
            78.99191170144533,
            6357752.313270314,
        ),
        (
            36.99,
            -25.1,
            10000.5,
            4626232.889861188,
            -2167085.839869703,
            3822523.8530542366,
        ),
    ];

    #[test]
    fn geodetic_to_ecef_matches_proj_to_a_micrometre() {
        for (lat, lon, h, x, y, z) in PROJ {
            let e = Geodetic::new(lat, lon, h).to_ecef();
            assert!(
                (e.x - x).abs() < 1e-6 && (e.y - y).abs() < 1e-6 && (e.z - z).abs() < 1e-6,
                "{lat} {lon} {h}: {e:?}"
            );
        }
    }

    #[test]
    fn ecef_to_geodetic_inverts_proj_points() {
        for (lat, lon, h, x, y, z) in PROJ {
            let g = Ecef { x, y, z }.to_geodetic();
            assert!((g.lat_deg - lat).abs() < 1e-11, "{lat}: {g:?}");
            if lat.abs() < 90.0 {
                assert!((g.lon_deg - lon).abs() < 1e-11, "{lon}: {g:?}");
            }
            assert!((g.h_m - h).abs() < 1e-6, "{h}: {g:?}");
        }
    }

    #[test]
    fn round_trip_on_a_dense_grid() {
        let mut worst: f64 = 0.0;
        for i in -17..=17 {
            for j in -35..=35 {
                for h in [-500.0, 0.0, 3000.0, 400_000.0] {
                    let g = Geodetic::new(i as f64 * 5.0 + 0.123, j as f64 * 5.0 + 0.456, h);
                    let e = g.to_ecef();
                    let e2 = e.to_geodetic().to_ecef();
                    let d =
                        ((e.x - e2.x).powi(2) + (e.y - e2.y).powi(2) + (e.z - e2.z).powi(2)).sqrt();
                    worst = worst.max(d);
                }
            }
        }
        assert!(worst < 1e-6, "worst round-trip error {worst} m");
    }

    #[test]
    fn enu_axes_are_orthonormal_and_up_is_the_normal() {
        let f = Enu::new(Geodetic::new(36.99, -25.1, 309.83), 0.0);
        for a in 0..3 {
            for b in 0..3 {
                let d: f64 = (0..3).map(|k| f.r[a][k] * f.r[b][k]).sum();
                assert!((d - if a == b { 1.0 } else { 0.0 }).abs() < 1e-15);
            }
        }
        // 1 km straight up along the normal is (0, 0, 1000) in ENU.
        let enu = f.enu_of(Geodetic::new(36.99, -25.1, 1309.83).to_ecef());
        assert!(
            enu[0].abs() < 1e-8 && enu[1].abs() < 1e-8 && (enu[2] - 1000.0).abs() < 1e-8,
            "{enu:?}"
        );
        // A point 0.09 degrees due north at the same height: no east, 9988.5 m north (meridian
        // radius of curvature at 37 degrees, about 6.3587e6 m, times 0.09 degrees; PROJ gives
        // 9988.53 m) and below the tangent plane by about d^2 / 2R (7.8 m): the surface curves away.
        let n = f.enu_of(Geodetic::new(37.08, -25.1, 309.83).to_ecef());
        assert!(
            n[0].abs() < 1e-6 && (n[1] - 9988.53).abs() < 0.05 && n[2] < -7.0 && n[2] > -8.5,
            "{n:?}"
        );
    }

    #[test]
    fn enu_and_ecef_are_inverse() {
        let f = Enu::new(Geodetic::new(28.486, -80.543, -26.598), 0.0);
        for p in [
            [0.0, 0.0, 0.0],
            [1234.5, -987.25, 3000.0],
            [-9000.0, 9000.0, -40.0],
        ] {
            let back = f.enu_of(f.ecef_of(p));
            for k in 0..3 {
                assert!((back[k] - p[k]).abs() < 1e-8, "{p:?} -> {back:?}");
            }
        }
    }

    #[test]
    fn heading_rotates_model_axes_clockwise_from_north() {
        let f = Enu::new(Geodetic::new(0.0, 0.0, 0.0), 90.0);
        // With a heading of 90 degrees the model +y axis points east and model +x points south.
        let y = f.enu_of_model([0.0, 1.0, 0.0]);
        let x = f.enu_of_model([1.0, 0.0, 0.0]);
        assert!((y[0] - 1.0).abs() < 1e-15 && y[1].abs() < 1e-15);
        assert!(x[0].abs() < 1e-15 && (x[1] + 1.0).abs() < 1e-15);
        let z = Enu::new(Geodetic::new(0.0, 0.0, 0.0), 0.0).enu_of_model([3.0, 4.0, 5.0]);
        assert_eq!(z, [3.0, 4.0, 5.0]);
    }
}
