//! Deterministic 6-DOF dynamics of a variable-mass rocket stage (M8).
//! Conventions, equations and tolerances: docs/m8-rocket-dynamics.md.

pub mod dynamics;
pub mod math;
pub mod model;
pub mod run;
pub mod sim;
pub mod verify;

use sha2::{Digest, Sha256};

/// Hash of the sources that determine this crate's behaviour, for provenance.
pub fn source_sha256() -> String {
    let sources = [
        ("Cargo.lock", include_str!("../Cargo.lock")),
        ("Cargo.toml", include_str!("../Cargo.toml")),
        ("src/dynamics.rs", include_str!("dynamics.rs")),
        ("src/lib.rs", include_str!("lib.rs")),
        ("src/main.rs", include_str!("main.rs")),
        ("src/math.rs", include_str!("math.rs")),
        ("src/model.rs", include_str!("model.rs")),
        ("src/run.rs", include_str!("run.rs")),
        ("src/sim.rs", include_str!("sim.rs")),
        ("src/verify.rs", include_str!("verify.rs")),
    ];
    let mut digest = Sha256::new();
    for (path, contents) in sources {
        digest.update(path.as_bytes());
        digest.update([0]);
        digest.update(contents.replace("\r\n", "\n").as_bytes());
        digest.update([0]);
    }
    hex(&digest.finalize())
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
