//! Proof of the extension contract with the reference domain: discovery, lifecycle, compatibility,
//! runs, comparison, replay that recomputes, tamper detection and deterministic evidence.

mod common;

use std::fs;

use common::{install, manifest, request, temp};
use vv_platform::{FaultRequest, Platform, PlatformError};

const V: &str = "test";

type Edit = Box<dyn Fn(&mut serde_json::Value)>;

#[test]
fn a_domain_appears_when_installed_and_disappears_when_removed() {
    let root = temp("life");
    let domains = root.join("domains");
    let library = root.join("library");
    fs::create_dir_all(&domains).unwrap();
    let (p, report) = Platform::start(std::slice::from_ref(&domains), &library, V).unwrap();
    assert_eq!(report.domains, 0);
    assert!(p.domains().is_empty());

    let dir = install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(std::slice::from_ref(&domains), &library, V).unwrap();
    let infos = p.domains();
    assert_eq!(infos.len(), 1);
    let catalog = infos[0].catalog.as_ref().expect("catalog from describe");
    assert_eq!(catalog.scenarios[0].id, "hold-zero");
    assert!(!infos[0].manifest.user_facing);
    let run = p.run(&request(7)).unwrap();
    assert!(!run.reused);

    fs::remove_dir_all(&dir).unwrap();
    let (p, _) = Platform::start(&[domains], &library, V).unwrap();
    assert!(p.domains().is_empty());
    // Research outputs survive the removal of the domain that produced them.
    assert_eq!(p.library().list_runs().len(), 1);
}

#[test]
fn incompatible_or_broken_manifests_are_rejected_with_a_reason() {
    let root = temp("compat");
    let domains = root.join("domains");
    let cases: Vec<(&str, Edit, &str)> = vec![
        (
            "major",
            Box::new(|m| m["contract"]["major"] = 2.into()),
            "incompatible",
        ),
        (
            "minor",
            Box::new(|m| m["contract"]["minor"] = 9.into()),
            "newer platform",
        ),
        (
            "name",
            Box::new(|m| m["contract"]["name"] = "other".into()),
            "is not vv-domain",
        ),
        (
            "badid",
            Box::new(|m| m["id"] = "Bad Id".into()),
            "id must be",
        ),
        (
            "path",
            Box::new(|m| m["host"]["executable"] = "../x.exe".into()),
            "plain file name",
        ),
        (
            "schema",
            Box::new(|m| m["schema"] = "vv-domain-manifest.v9".into()),
            "schema",
        ),
    ];
    for (name, edit, _) in &cases {
        let mut m = manifest();
        m["id"] = format!("ref-{name}").into();
        edit(&mut m);
        install(&domains, name, &m);
    }
    let missing = domains.join("missing-exe");
    fs::create_dir_all(&missing).unwrap();
    let mut m = manifest();
    m["id"] = "ref-missing".into();
    fs::write(missing.join("domain.json"), serde_json::to_vec(&m).unwrap()).unwrap();
    install(&domains, "zz-first", &manifest());
    install(&domains, "zz-second", &manifest());

    let (p, report) = Platform::start(&[domains], &root.join("library"), V).unwrap();
    assert_eq!(p.domains().len(), 1, "only one valid reference domain");
    let reason = |dir: &str| {
        report
            .rejected
            .iter()
            .find(|r| r.dir == dir)
            .map(|r| r.reason.clone())
            .unwrap_or_else(|| panic!("{dir} was not rejected"))
    };
    for (name, _, expect) in &cases {
        assert!(reason(name).contains(expect), "{name}: {}", reason(name));
    }
    assert!(reason("missing-exe").contains("missing"));
    assert!(reason("zz-second").contains("duplicate"));
}

#[test]
fn runs_are_deterministic_reused_replayed_and_tamper_evident() {
    let root = temp("run");
    let domains = root.join("domains");
    install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(&[domains], &root.join("library"), V).unwrap();

    let first = p.run(&request(42)).unwrap();
    let again = p.run(&request(42)).unwrap();
    assert_eq!(first.run_id, again.run_id);
    assert!(again.reused);
    let other = p.run(&request(43)).unwrap();
    assert_ne!(first.run_id, other.run_id);

    let record = p.record(&first.run_id).unwrap();
    assert_eq!(record.request.parameters["x0_mm"], 80.0, "defaults filled");
    assert_eq!(record.safety.status, "safe");

    let replay = p.replay(&first.run_id).unwrap();
    assert_eq!(replay.status, "verified", "{:#?}", replay.checks);

    let a = fs::read(p.export_evidence(&first.run_id, None).unwrap()).unwrap();
    let again_path = root.join("again.zip");
    let b = fs::read(p.export_evidence(&first.run_id, Some(again_path)).unwrap()).unwrap();
    assert_eq!(a, b, "evidence packages are byte-identical");

    let trace = p
        .library()
        .run_dir(&first.run_id)
        .unwrap()
        .join("trace.json");
    let text = fs::read_to_string(&trace).unwrap();
    fs::write(&trace, text.replacen("\"seed\": 42", "\"seed\": 41", 1)).unwrap();
    let replay = p.replay(&first.run_id).unwrap();
    assert_eq!(replay.status, "rejected");
    assert!(
        replay
            .checks
            .iter()
            .any(|c| !c.pass && c.name.contains("hashes"))
    );
}

#[test]
fn a_fault_can_make_the_run_unsafe_and_the_verdict_says_when() {
    let root = temp("fault");
    let domains = root.join("domains");
    install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(&[domains], &root.join("library"), V).unwrap();
    let nominal = p.record(&p.run(&request(1)).unwrap().run_id).unwrap();
    assert_eq!(nominal.safety.status, "safe");
    assert_eq!(nominal.outcome.status, "success");

    let mut r = request(1);
    r.parameters.insert("kp".into(), 400.0);
    r.faults.push(FaultRequest {
        kind: "sensor_bias".into(),
        magnitude: Some(100.0),
        start: 0.0,
        end: 500.0,
    });
    let record = p.record(&p.run(&r).unwrap().run_id).unwrap();
    let bound = record
        .requirements
        .iter()
        .find(|q| q.id == "S_bound")
        .unwrap();
    assert_eq!(bound.status, "fail", "{bound:?}");
    assert!(bound.t.is_some());
    assert_eq!(record.safety.status, "unsafe");
    assert!(record.events.iter().any(|e| e.severity == "violation"));
}

#[test]
fn comparisons_validate_everything_before_running_anything() {
    let root = temp("cmp");
    let domains = root.join("domains");
    install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(&[domains], &root.join("library"), V).unwrap();
    let results = p.compare(&[request(1), request(2), request(3)]).unwrap();
    assert_eq!(results.len(), 3);
    let seeds: Vec<u64> = results
        .iter()
        .map(|r| r.as_ref().unwrap().meta.summary.seed)
        .collect();
    assert_eq!(seeds, vec![1, 2, 3]);

    let mut bad = request(4);
    bad.controller = "nonexistent".into();
    let before = p.library().list_runs().len();
    let refused = p.compare(&[request(5), bad]);
    assert!(matches!(refused, Err(PlatformError::Invalid(_))));
    assert_eq!(p.library().list_runs().len(), before, "nothing ran");
}

#[test]
fn invalid_requests_are_refused_with_a_message() {
    let root = temp("inv");
    let domains = root.join("domains");
    install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(&[domains], &root.join("library"), V).unwrap();
    let mut r = request(1);
    r.parameters.insert("kp".into(), 1e9);
    assert!(matches!(p.run(&r), Err(PlatformError::Invalid(m)) if m.contains("kp")));
    let mut r = request(1);
    r.faults.push(FaultRequest {
        kind: "sensor_dropout".into(),
        magnitude: None,
        start: 10.5,
        end: 20.0,
    });
    assert!(matches!(p.run(&r), Err(PlatformError::Invalid(m)) if m.contains("whole ticks")));
    let mut r = request(1);
    r.domain = "absent".into();
    assert!(matches!(p.run(&r), Err(PlatformError::NotFound(_))));
}

#[test]
fn a_library_summary_that_disagrees_with_the_record_is_rejected_and_exported_as_such() {
    let root = temp("meta-tamper");
    let domains = root.join("domains");
    install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(&[domains], &root.join("library"), V).unwrap();
    let run = p.run(&request(42)).unwrap();
    let ok = p.export_evidence(&run.run_id, None).unwrap();
    assert!(ok.to_string_lossy().ends_with("-evidence.zip"));

    // The Library list and the run summary come from meta.json: make it claim another outcome.
    let meta = p.library().run_dir(&run.run_id).unwrap().join("meta.json");
    let text = fs::read_to_string(&meta).unwrap();
    let forged = text.replacen("\"safe\"", "\"unsafe\"", 1);
    assert_ne!(text, forged);
    fs::write(&meta, forged).unwrap();
    let replay = p.replay(&run.run_id).unwrap();
    assert_eq!(replay.status, "rejected");
    assert!(
        replay
            .checks
            .iter()
            .any(|c| !c.pass && c.name.contains("meta.json summary"))
    );
    let path = p.export_evidence(&run.run_id, None).unwrap();
    assert!(
        path.file_name()
            .unwrap()
            .to_string_lossy()
            .ends_with("-REJECTED.zip"),
        "{}",
        path.display()
    );
}

#[test]
fn a_host_replaced_after_start_up_is_not_called() {
    let root = temp("host-swap");
    let domains = root.join("domains");
    let dir = install(&domains, "reference-oscillator", &manifest());
    let (p, _) = Platform::start(&[domains], &root.join("library"), V).unwrap();
    let run = p.run(&request(42)).unwrap();
    // Append a byte: a different build at the same path.
    let exe = fs::read_dir(&dir)
        .unwrap()
        .map(|e| e.unwrap().path())
        .find(|p| p.extension().is_none_or(|x| x == "exe") && p.is_file())
        .unwrap();
    let mut bytes = fs::read(&exe).unwrap();
    bytes.push(0);
    fs::write(&exe, bytes).unwrap();
    let err = p.replay(&run.run_id).unwrap_err();
    assert!(err.to_string().contains("changed since"), "{err}");
    let err = p.run(&request(43)).unwrap_err();
    assert!(err.to_string().contains("changed since"), "{err}");
}
