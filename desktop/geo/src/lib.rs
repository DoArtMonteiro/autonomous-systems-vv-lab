//! Georeference layer of V&V Lab Studio.
//!
//! The simulations of the Lab run in local frames: the rocket landing in a flat, non-rotating
//! east-north-up frame with the origin at the pad centre on the ground. This crate places such a
//! frame on the Earth for display, and nothing else:
//!
//! - [`wgs84`]: geodetic (latitude, longitude, ellipsoidal height) to Earth-centred Earth-fixed
//!   coordinates and back, on the WGS84 ellipsoid;
//! - [`Enu`]: the east-north-up tangent frame at an origin, with an optional heading of the model
//!   axes;
//! - [`environment`]: geographic environment packs (terrain heights, image, manifest), validated
//!   before anything is shown: schema, sizes, SHA-256, and the pack's own check points recomputed
//!   with this crate's geodesy;
//! - [`world`]: the optional world layer of a pack (buildings, structures, vegetation), with the
//!   source of every height.
//!
//! Placing a run on a landscape never changes the run. Records, verdicts and hashes are computed
//! by the domain hosts before any of this code is involved, and nothing here feeds back into them.

pub mod environment;
pub mod wgs84;
pub mod world;

pub use environment::{Environment, GeoError, TrackPoint};
pub use wgs84::{Ecef, Enu, Geodetic};
