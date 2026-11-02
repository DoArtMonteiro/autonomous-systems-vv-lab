//! Reusable platform of the V&V Lab desktop product (M11).
//!
//! The platform knows nothing about rockets or ground vehicles. A simulation domain is an executable
//! host next to a `domain.json` manifest; the platform discovers it, checks contract compatibility,
//! asks it for its catalog, validates requests at the boundary (shape, size, seed policy), runs it
//! out of process with a timeout and an output cap, stores the run in the library, replays it with
//! the host (which must recompute, never return stored verdicts) and exports evidence packages.
//! The contract is described in docs/m11-domain-contract.md.

pub mod canonical;
pub mod contract;
pub mod discovery;
pub mod evidence;
pub mod host;
pub mod host_sdk;
pub mod library;
pub mod seeds;
pub mod service;
pub mod validate;

pub use contract::*;
pub use service::{Platform, PlatformError};
