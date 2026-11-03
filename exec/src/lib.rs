//! M12 experiment engine: specifications, planning, in-process execution, equivalence with the
//! canonical command lines, statistics, validity envelopes and numerical convergence checks.

pub mod converge;
pub mod domain;
pub mod engine;
pub mod equiv;
pub mod ground;
pub mod plan;
pub mod prng;
pub mod report;
pub mod sched;
pub mod seeds;
pub mod spec;
pub mod stats;
