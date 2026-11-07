//! `vv-run.v2` is additive: every v1 record still parses, carries no v2 field and serialises to the
//! same canonical bytes; v2 records are checked for consistent entities and requirement ownership.

use serde_json::Value;
use vv_platform::canonical::{canonical_bytes, pretty_bytes};
use vv_platform::contract::*;

const V1_FIXTURES: [&str; 1] = [include_str!(
    "../../studio/tests/fixtures/rocket-record-trimmed.json"
)];

fn v1() -> RunRecord {
    serde_json::from_str(V1_FIXTURES[0]).unwrap()
}

#[test]
fn every_v1_fixture_parses_and_round_trips_byte_identical() {
    for text in V1_FIXTURES {
        let value: Value = serde_json::from_str(text).unwrap();
        let record: RunRecord = serde_json::from_str(text).unwrap();
        assert_eq!(record.schema, RECORD_SCHEMA);
        assert!(record.entities.is_none() && record.mission.is_none());
        record.check_entities().unwrap();
        // Same canonical bytes as the stored document, and the on-disk format is a fixed point.
        assert_eq!(canonical_bytes(&record), canonical_bytes(&value));
        let pretty = pretty_bytes(&record);
        assert_eq!(pretty, pretty_bytes(&value));
        let again: RunRecord = serde_json::from_slice(&pretty).unwrap();
        assert_eq!(pretty_bytes(&again), pretty);
        let out = serde_json::to_value(&record).unwrap();
        assert!(out.get("entities").is_none() && out.get("mission").is_none());
    }
}

fn v2() -> RunRecord {
    let mut r = v1();
    r.schema = RECORD_SCHEMA_V2.into();
    for id in ["stack.S1", "mission.R1"] {
        r.requirements.push(RequirementResult {
            id: id.into(),
            label: id.into(),
            category: "requirement".into(),
            status: "pass".into(),
            expected: String::new(),
            observed: String::new(),
            t: None,
            explanation: String::new(),
        });
    }
    r.events.push(Event {
        t: 0.0,
        kind: "liftoff".into(),
        label: "Liftoff".into(),
        severity: "info".into(),
        source: "truth".into(),
        detail: Value::Null,
    });
    let tb = r.channels[0].timebase.clone();
    let ids: Vec<String> = r.requirements.iter().map(|q| q.id.clone()).collect();
    let (first, rest) = ids.split_at(1);
    r.entities = Some(vec![
        Entity {
            id: "stack".into(),
            label: "Stack".into(),
            kind: "stack".into(),
            parent: None,
            timebase: tb.clone(),
            t_start: 0.0,
            t_end: 1.0,
            end_reason: "separated".into(),
            channels: vec![r.channels[0].id.clone()],
            events: vec![0],
            requirements: first.to_vec(),
        },
        Entity {
            id: "booster".into(),
            label: "Booster".into(),
            kind: "booster".into(),
            parent: Some("stack".into()),
            timebase: tb,
            t_start: 1.0,
            t_end: 2.0,
            end_reason: "surface impact".into(),
            channels: vec![],
            events: vec![],
            requirements: vec![],
        },
    ]);
    r.mission = Some(MissionResult {
        requirements: rest.to_vec(),
        event_order: "tick, then entity".into(),
        explanation: String::new(),
    });
    r
}

#[test]
fn a_consistent_v2_record_passes_and_round_trips() {
    let r = v2();
    r.check_entities().unwrap();
    let bytes = pretty_bytes(&r);
    let back: RunRecord = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(back, r);
}

#[test]
fn inconsistent_v2_records_are_refused() {
    let mut r = v2();
    r.entities.as_mut().unwrap()[1].parent = Some("nobody".into());
    assert!(r.check_entities().is_err());

    let mut r = v2();
    r.mission.as_mut().unwrap().requirements.pop();
    assert!(r.check_entities().unwrap_err().contains("exactly one"));

    let mut r = v2();
    r.entities.as_mut().unwrap()[0].events = vec![9_999];
    assert!(r.check_entities().is_err());

    let mut r = v2();
    r.entities.as_mut().unwrap()[0].channels = vec!["no_such_channel".into()];
    assert!(r.check_entities().is_err());

    let mut r = v2();
    r.mission = None;
    assert!(r.check_entities().is_err());

    // A v1 record may not carry v2 fields.
    let mut r = v2();
    r.schema = RECORD_SCHEMA.into();
    assert!(r.check_entities().is_err());
}
