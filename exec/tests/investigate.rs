//! M13 investigations: determinism, full recomputation and the adversarial attacks a package must
//! survive. A package whose evidence is changed, truncated, duplicated, re-hashed, moved to another
//! model source, re-graded or given another envelope must fail verification. All output goes
//! under Cargo's per-target temporary directory.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Value, json};
use vv_exec::investigate::{self, Inputs, Verification};
use vv_exec::plan::sha256_hex;

fn scratch(name: &str) -> PathBuf {
    let d = Path::new(env!("CARGO_TARGET_TMPDIR")).join(name);
    for p in [d.clone(), d.with_extension("partial")] {
        if p.exists() {
            fs::remove_dir_all(&p).unwrap();
        }
    }
    d
}

fn corridor() -> Vec<u8> {
    fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("cases/m14/ground-zone-corridor.json"))
        .unwrap()
}

/// A small corridor claim: the M14 F1 fragility with a budget that runs in about a second.
fn claim(extra: Value) -> Value {
    let mut c = json!({
        "schema": "vv-claim.v1",
        "id": "test-corridor",
        "title": "Corridor under GPS noise (test)",
        "statement": "The vehicle never enters the zone with GPS noise up to 20 mm.",
        "origin": "Test fixture.",
        "domain": "ground-m4",
        "base_case": "base.json",
        "property": "invariant:restricted_zone",
        "tolerance": 0.0,
        "objective": {"metric": "margin.restricted_zone_mm", "direction": "minimise"},
        "assumptions": [
            {"parameter": {"name": "gps_noise_mm", "pointer": "/scenario/sensors/gps/noise_max_mm", "unit": "mm", "low": 0, "high": 20, "integer": true}, "description": "noise"},
            {"parameter": {"name": "delay", "pointer": "/scenario/sensors/communication/delay_max_ticks", "unit": "ticks", "low": 0, "high": 3, "integer": true}, "description": "delay"}
        ],
        "seeds": {"discovery": {"low": 45000, "high": 45999}, "evaluation": {"low": 46000, "high": 46499}, "regression": {"low": 46500, "high": 46999}},
        "budget": {"baseline_seeds": 6, "challenge": 40, "minimise": 20, "replication_seeds": 20, "envelope_levels": 3, "envelope_seeds": 2, "mechanism_seeds": 20, "regression_points": 6},
        "search_seed": 13,
        "hypotheses": [
            {"id": "exact-arrival", "statement": "Zero arrival radius.",
             "interventions": [{"id": "radius", "description": "radius 250", "at": "counterexample", "overrides": [{"pointer": "/scenario/mission/arrival_radius_mm", "value": 250}], "predicts": "holds"}],
             "trace_checks": [{"id": "noisy", "description": "the belief is off by at least 1 mm", "samples": "/events", "pointer": "/event/observed/position/y_mm", "minus": "/event/truth_position/y_mm", "predicate": "max_abs_at_least", "threshold": 1.0}]}
        ],
        "mitigations": [
            {"id": "radius", "title": "radius 250", "rationale": "test", "overrides": [{"pointer": "/scenario/mission/arrival_radius_mm", "value": 250}]}
        ],
        "regression": [
            {"id": "loss", "title": "loss", "base_case": "base.json", "parameters": [
                {"name": "dropout", "pointer": "/scenario/sensors/gps/dropout_permille", "unit": "permille", "low": 0, "high": 300, "integer": true}
            ]}
        ],
        "limits": {"max_evaluations": 1000, "max_wall_s": 600}
    });
    if let Value::Object(m) = extra {
        for (k, v) in m {
            c[k] = v;
        }
    }
    c
}

fn inputs(c: &Value) -> Inputs {
    Inputs {
        claim_bytes: serde_json::to_vec_pretty(c).unwrap(),
        base_bytes: corridor(),
        families: vec![corridor()],
        preregistration: None,
    }
}

fn run(name: &str) -> PathBuf {
    let out = scratch(name);
    investigate::execute(&inputs(&claim(json!({}))), &out, 4, None).unwrap();
    out
}

fn verify(out: &Path) -> Verification {
    investigate::verify(out, 4, None).unwrap()
}

fn failed(v: &Verification) -> Vec<String> {
    v.checks
        .iter()
        .filter(|c| !c.pass)
        .map(|c| c.id.clone())
        .collect()
}

/// Rewrites the manifest so every file hash is the current one: the attack of someone who edits
/// a record and re-hashes it.
fn rehash(out: &Path) {
    let path = out.join("manifest.json");
    let mut m: BTreeMap<String, String> =
        serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    for (k, v) in m.iter_mut() {
        if let Ok(b) = fs::read(out.join(k)) {
            *v = sha256_hex(&b);
        }
    }
    fs::write(path, serde_json::to_vec_pretty(&m).unwrap()).unwrap();
}

fn edit_package(out: &Path, f: impl FnOnce(&mut Value)) {
    let p = out.join("investigation.json");
    let mut v: Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
    f(&mut v);
    fs::write(&p, serde_json::to_vec_pretty(&v).unwrap()).unwrap();
}

fn copy_dir(from: &Path, to: &Path) {
    fs::create_dir_all(to).unwrap();
    for e in fs::read_dir(from).unwrap() {
        let e = e.unwrap();
        let t = to.join(e.file_name());
        if e.file_type().unwrap().is_dir() {
            copy_dir(&e.path(), &t);
        } else {
            fs::copy(e.path(), t).unwrap();
        }
    }
}

fn tampered(name: &str, base: &Path) -> PathBuf {
    let d = scratch(name);
    copy_dir(base, &d);
    d
}

#[test]
fn an_investigation_refutes_explains_fixes_and_verifies() {
    let out = run("inv-basic");
    let pkg: Value =
        serde_json::from_slice(&fs::read(out.join("investigation.json")).unwrap()).unwrap();
    let f = &pkg["findings"];
    assert_eq!(
        f["baseline"]["violated"], 0,
        "the registered corridor is safe"
    );
    assert_eq!(f["verdict"]["claim"], "refuted");
    let cx = &f["counterexample"];
    assert_eq!(cx["byte_reproduced"], true);
    assert_eq!(
        cx["active"],
        json!(["gps_noise_mm"]),
        "minimisation drops the delay"
    );
    assert_eq!(f["attribution"][1]["role"], "not_required");
    assert_eq!(f["mechanism"][0]["status"], "experimentally_supported");
    assert_eq!(f["mechanism"][0]["trace_checks"][0]["status"], "supported");
    assert_eq!(
        f["mitigations"][0]["status"],
        "effective_no_regression_observed"
    );
    assert!(out.join("artifacts/counterexample/signals.json").is_file());
    assert!(!out.with_extension("partial").exists());
    let v = verify(&out);
    assert!(v.pass, "{:?}", v.checks);
    assert_eq!(v.probes_recomputed, pkg["probes"].as_u64().unwrap());
}

#[test]
fn the_same_claim_gives_the_same_package_bytes() {
    let a = run("inv-det-a");
    let b = run("inv-det-b");
    // `challenge/search.json` and the manifest carry the wall time of the search; everything the
    // findings depend on is byte-identical.
    for f in [
        "investigation.json",
        "probes.jsonl",
        "challenge/evaluations.jsonl",
        "artifacts/counterexample/events.json",
    ] {
        assert_eq!(
            fs::read(a.join(f)).unwrap(),
            fs::read(b.join(f)).unwrap(),
            "{f}"
        );
    }
}

#[test]
fn edited_and_rehashed_evidence_fails() {
    let base = run("inv-tamper-base");
    // A verdict changed and the manifest re-hashed.
    let d = tampered("inv-tamper-verdict", &base);
    edit_package(&d, |v| {
        v["findings"]["verdict"]["claim"] = json!("not_refuted_within_budget")
    });
    rehash(&d);
    let v = verify(&d);
    assert!(!v.pass);
    assert_eq!(failed(&v), vec!["findings"]);
    // A probe outcome changed and re-hashed line by line, and the stated log hash updated.
    let d = tampered("inv-tamper-probe", &base);
    let text = fs::read_to_string(d.join("probes.jsonl")).unwrap();
    let mut lines: Vec<String> = text.lines().map(String::from).collect();
    let (_, json) = lines[0].split_once(' ').unwrap();
    let mut p: Value = serde_json::from_str(json).unwrap();
    p["property_violated"] = json!(true);
    let j = serde_json::to_string(&p).unwrap();
    lines[0] = format!("{} {j}", sha256_hex(j.as_bytes()));
    fs::write(d.join("probes.jsonl"), lines.join("\n") + "\n").unwrap();
    let log_hash = sha256_hex(&fs::read(d.join("probes.jsonl")).unwrap());
    edit_package(&d, |v| v["probes_sha256"] = json!(log_hash));
    rehash(&d);
    let v = verify(&d);
    assert!(
        failed(&v).contains(&"probes".to_string()),
        "{:?}",
        failed(&v)
    );
    // Without re-hashing, the manifest alone catches the edit.
    let d = tampered("inv-tamper-plain", &base);
    edit_package(&d, |v| v["findings"]["baseline"]["violated"] = json!(1));
    assert!(failed(&verify(&d)).contains(&"manifest".to_string()));
}

#[test]
fn truncated_or_duplicated_logs_and_misstated_counts_fail() {
    let base = run("inv-log-base");
    let text = fs::read_to_string(base.join("probes.jsonl")).unwrap();
    let lines: Vec<&str> = text.lines().collect();
    // Truncated: the last probes removed.
    let d = tampered("inv-log-trunc", &base);
    fs::write(
        d.join("probes.jsonl"),
        lines[..lines.len() - 5].join("\n") + "\n",
    )
    .unwrap();
    rehash(&d);
    assert!(failed(&verify(&d)).contains(&"probes".to_string()));
    // Duplicated observation: one probe repeated in place of another.
    let d = tampered("inv-log-dup", &base);
    let mut dup: Vec<&str> = lines.clone();
    dup[1] = dup[0];
    fs::write(d.join("probes.jsonl"), dup.join("\n") + "\n").unwrap();
    rehash(&d);
    assert!(failed(&verify(&d)).contains(&"probes".to_string()));
    // Misstated sample size.
    let d = tampered("inv-log-count", &base);
    edit_package(&d, |v| {
        v["probes"] = json!(v["probes"].as_u64().unwrap() * 2);
        v["findings"]["counterexample"]["replication"]["n"] = json!(800);
    });
    rehash(&d);
    let f = failed(&verify(&d));
    assert!(
        f.contains(&"probe_count".to_string()) && f.contains(&"findings".to_string()),
        "{f:?}"
    );
    // The challenge search log truncated and re-hashed.
    let d = tampered("inv-log-search", &base);
    let s = fs::read_to_string(d.join("challenge/evaluations.jsonl")).unwrap();
    let keep: Vec<&str> = s.lines().take(10).collect();
    fs::write(
        d.join("challenge/evaluations.jsonl"),
        keep.join("\n") + "\n",
    )
    .unwrap();
    rehash(&d);
    let r = investigate::verify(&d, 4, None);
    assert!(r.is_err() || !r.unwrap().pass);
}

#[test]
fn another_source_grade_or_envelope_fails() {
    let base = run("inv-id-base");
    // Substituted model source.
    let d = tampered("inv-id-source", &base);
    edit_package(&d, |v| v["source_sha256"] = json!("0".repeat(64)));
    rehash(&d);
    assert_eq!(failed(&verify(&d)), vec!["source"]);
    // Exploratory evidence presented as confirmatory.
    let d = tampered("inv-id-grade", &base);
    edit_package(&d, |v| {
        v["findings"]["verdict"]["evidence_grade"] = json!("confirmatory")
    });
    rehash(&d);
    let f = failed(&verify(&d));
    assert!(f.contains(&"evidence_grade".to_string()), "{f:?}");
    // The envelope widened after the run, to present the evidence for a broader claim.
    let d = tampered("inv-id-envelope", &base);
    let mut c: Value = serde_json::from_slice(&fs::read(d.join("claim.json")).unwrap()).unwrap();
    c["assumptions"][0]["parameter"]["high"] = json!(200);
    fs::write(d.join("claim.json"), serde_json::to_vec_pretty(&c).unwrap()).unwrap();
    rehash(&d);
    let f = failed(&verify(&d));
    assert!(
        f.contains(&"inputs".to_string()) && f.contains(&"challenge".to_string()),
        "{f:?}"
    );
    // The statement reworded in the package only.
    let d = tampered("inv-id-statement", &base);
    edit_package(&d, |v| {
        v["statement"] = json!("The corridor is always safe.")
    });
    rehash(&d);
    assert_eq!(failed(&verify(&d)), vec!["statement"]);
    // A file added to the package.
    let d = tampered("inv-id-extra", &base);
    fs::write(d.join("note.txt"), b"added").unwrap();
    assert_eq!(failed(&verify(&d)), vec!["manifest"]);
}

#[test]
fn claims_that_break_the_seed_rules_or_claim_confirmation_are_refused() {
    let parse = |c: Value| investigate::Claim::parse(&serde_json::to_vec(&c).unwrap());
    let pools = |d: (u64, u64), e: (u64, u64)| json!({"discovery": {"low": d.0, "high": d.1}, "evaluation": {"low": e.0, "high": e.1}, "regression": {"low": 46500, "high": 46999}});
    let e = parse(claim(
        json!({"seeds": pools((50000, 50999), (46000, 46499))}),
    ))
    .unwrap_err();
    assert!(e.contains("M14 held-out"), "{e}");
    let e = parse(claim(
        json!({"seeds": pools((45000, 45999), (44000, 44499))}),
    ))
    .unwrap_err();
    assert!(e.contains("M13 reserve"), "{e}");
    let e = parse(claim(
        json!({"seeds": pools((45000, 46100), (46000, 46499))}),
    ))
    .unwrap_err();
    assert!(e.contains("overlap"), "{e}");
    assert!(parse(claim(json!({"seeds": pools((100, 199), (46000, 46499))}))).is_err());
    assert!(parse(claim(json!({"evidence_grade": "confirmatory"}))).is_err());
    // An intervention may not move an assumption, or it would not test the counterexample.
    let mut c = claim(json!({}));
    c["hypotheses"][0]["interventions"][0]["overrides"][0]["pointer"] =
        json!("/scenario/sensors/gps/noise_max_mm");
    assert!(parse(c).unwrap_err().contains("assumption"));
    // A preregistration that does not freeze the claim keeps the run from starting.
    let c = claim(json!({
        "evidence_grade": "confirmatory",
        "preregistration": {"path": "p.txt", "sha256": sha256_hex(b"protocol")}
    }));
    let mut i = inputs(&c);
    i.preregistration = Some(b"protocol".to_vec());
    let out = scratch("inv-prereg");
    let e = investigate::execute(&i, &out, 2, None).unwrap_err();
    assert!(e.contains("does not freeze this claim"), "{e}");
    assert!(!out.exists() && !out.with_extension("partial").exists());
}

#[test]
fn an_interrupted_investigation_never_looks_finished() {
    let out = scratch("inv-interrupt");
    fs::create_dir_all(out.with_extension("partial")).unwrap();
    let e = investigate::execute(&inputs(&claim(json!({}))), &out, 2, None).unwrap_err();
    assert!(e.contains("interrupted"), "{e}");
    assert!(!out.exists());
    // An existing package is never overwritten.
    let done = run("inv-exists");
    let e = investigate::execute(&inputs(&claim(json!({}))), &done, 2, None).unwrap_err();
    assert!(e.contains("already exists"), "{e}");
}
