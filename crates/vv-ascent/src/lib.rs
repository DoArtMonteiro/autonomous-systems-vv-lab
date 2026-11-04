//! Deterministic planar ascent of a two-stage launcher to a target orbit, with the booster and the
//! upper stage integrated as separate entities after separation (M17). Model, assumptions,
//! references and limits: docs/m17-ascent.md.

pub mod dynamics;
pub mod guidance;
pub mod math;
pub mod model;
pub mod prng;
pub mod run;
pub mod sim;
pub mod verify;

use sha2::{Digest, Sha256};

/// Bundled exploratory vehicle cases: (id, bytes).
pub const CASES: [(&str, &str); 2] = [
    ("small-leo", include_str!("../cases/small-leo.json")),
    ("medium-leo", include_str!("../cases/medium-leo.json")),
];

/// Hash of the sources that determine this crate's behaviour, for provenance.
pub fn source_sha256() -> String {
    let sources = [
        ("Cargo.lock", include_str!("../Cargo.lock")),
        ("Cargo.toml", include_str!("../Cargo.toml")),
        ("src/dynamics.rs", include_str!("dynamics.rs")),
        ("src/guidance.rs", include_str!("guidance.rs")),
        ("src/lib.rs", include_str!("lib.rs")),
        ("src/main.rs", include_str!("main.rs")),
        ("src/math.rs", include_str!("math.rs")),
        ("src/model.rs", include_str!("model.rs")),
        ("src/prng.rs", include_str!("prng.rs")),
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
