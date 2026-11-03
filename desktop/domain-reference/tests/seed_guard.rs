//! The platform refuses a protected seed before any host process starts. The reference host logs
//! every invocation when VV_REFERENCE_CALL_LOG is set; a protected seed must leave no trace there.
//! One test per binary, because it sets a process environment variable.

mod common;

use std::fs;

use common::{install, manifest, request, temp};
use vv_platform::{Platform, PlatformError};

#[test]
fn protected_seeds_never_reach_the_host() {
    let root = temp("seed");
    let domains = root.join("domains");
    install(&domains, "reference-oscillator", &manifest());
    let log = root.join("calls.log");
    // SAFETY: the only test in this binary; no other thread reads the environment.
    unsafe { std::env::set_var("VV_REFERENCE_CALL_LOG", &log) };
    let (p, _) = Platform::start(&[domains], &root.join("library"), "test").unwrap();

    for seed in [900, 950, 999] {
        assert!(matches!(
            p.run(&request(seed)),
            Err(PlatformError::Protected(_))
        ));
        assert!(matches!(
            p.compare(&[request(1), request(seed)]),
            Err(PlatformError::Protected(_))
        ));
    }
    assert!(matches!(
        p.run(&request(2_000_000)),
        Err(PlatformError::Protected(_))
    ));
    p.run(&request(899)).unwrap();
    p.run(&request(1000)).unwrap();

    let calls = fs::read_to_string(&log).unwrap();
    for seed in ["900", "950", "999", "2000000"] {
        assert!(
            !calls.lines().any(|l| l.ends_with(&format!(" {seed}"))),
            "{seed} reached the host:\n{calls}"
        );
    }
    assert!(calls.lines().any(|l| l == "run 899"), "{calls}");
    assert!(calls.lines().any(|l| l == "validate 1000"), "{calls}");

    // Defence in depth: the host refuses it too when called directly.
    let req = root.join("direct.json");
    fs::write(&req, serde_json::to_vec(&request(950)).unwrap()).unwrap();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_vv-domain-reference"))
        .args(["validate", req.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&out.stderr).contains("protected"));
}
