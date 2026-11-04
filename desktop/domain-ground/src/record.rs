//! Maps the native outputs of `vv-lab run-m4` (events, report, mission, verification, manifest) into
//! the normalised `RunRecord`. Everything in the record is read from those files; nothing is stored
//! from an earlier run.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::{Value, json};
use vv_platform::contract::*;
use vv_platform::host_sdk::read_bounded;

use crate::catalog::{self, CHANNELS, DOMAIN_ID, TIMEBASE};
use crate::native::{self, Policy, RunArgs};

type R<T> = Result<T, String>;

const MAX_NATIVE_BYTES: u64 = 16 * 1024 * 1024;

pub struct Native {
    events: Value,
    report: Value,
    mission: Value,
    verification: Value,
    manifest: Value,
}

impl Native {
    pub fn load(dir: &Path) -> R<Self> {
        let read = |name: &str| -> R<Value> {
            let bytes = read_bounded(&dir.join(name), MAX_NATIVE_BYTES)?;
            serde_json::from_slice(&bytes).map_err(|e| format!("{name}: {e}"))
        };
        Ok(Self {
            events: read("events.json")?,
            report: read("report.json")?,
            mission: read("mission.json")?,
            verification: read("verification.json")?,
            manifest: read("m4.json")?,
        })
    }
}

fn get<'a>(v: &'a Value, pointer: &str) -> R<&'a Value> {
    v.pointer(pointer)
        .ok_or_else(|| format!("native output lacks {pointer}"))
}

fn int(v: &Value, pointer: &str) -> R<i64> {
    get(v, pointer)?
        .as_i64()
        .ok_or_else(|| format!("native output {pointer} is not an integer"))
}

fn opt_int(v: &Value, pointer: &str) -> Option<i64> {
    v.pointer(pointer).and_then(Value::as_i64)
}

fn text<'a>(v: &'a Value, pointer: &str) -> R<&'a str> {
    get(v, pointer)?
        .as_str()
        .ok_or_else(|| format!("native output {pointer} is not text"))
}

fn array<'a>(v: &'a Value, pointer: &str) -> R<&'a Vec<Value>> {
    get(v, pointer)?
        .as_array()
        .ok_or_else(|| format!("native output {pointer} is not a list"))
}

#[derive(Clone, Copy)]
struct Pt {
    x: i64,
    y: i64,
}

impl Pt {
    fn of(v: &Value) -> R<Pt> {
        Ok(Pt {
            x: int(v, "/x_mm")?,
            y: int(v, "/y_mm")?,
        })
    }

    fn manhattan(self, other: Pt) -> i64 {
        (self.x - other.x).abs() + (self.y - other.y).abs()
    }

    fn json(self) -> Value {
        json!({"x": self.x, "y": self.y})
    }
}

struct Fix {
    pos: Pt,
    age: i64,
    confidence: i64,
}

struct Row {
    from: Pt,
    truth: Pt,
    command_mm: i64,
    fix: Option<Fix>,
    fallback: bool,
    gps: Option<Pt>,
    dropped: bool,
}

struct Transition {
    tick: i64,
    subsystem: String,
    from: String,
    to: String,
    reason: String,
}

fn parse_events(native: &Native) -> R<(Vec<Row>, Vec<Transition>)> {
    let mut gps: BTreeMap<i64, (Option<Pt>, bool)> = BTreeMap::new();
    let mut ticks = Vec::new();
    let mut transitions = Vec::new();
    for entry in array(&native.events, "/events")? {
        let tick = int(entry, "/tick")?;
        let body = get(entry, "/event")?;
        match text(body, "/kind")? {
            "gps_sample" => {
                let dropped = get(body, "/dropped")?.as_bool().unwrap_or(false);
                let observation = match body.get("observation") {
                    Some(v) if !v.is_null() => Some(Pt::of(v)?),
                    _ => None,
                };
                gps.insert(tick, (observation, dropped));
            }
            "transition" => transitions.push(Transition {
                tick,
                subsystem: text(body, "/subsystem")?.into(),
                from: text(body, "/from")?.into(),
                to: text(body, "/to")?.into(),
                reason: text(body, "/reason")?.into(),
            }),
            "tick_result" => ticks.push((tick, body)),
            _ => {}
        }
    }
    let mut rows = Vec::with_capacity(ticks.len());
    for (index, (tick, body)) in ticks.into_iter().enumerate() {
        if tick != index as i64 + 1 {
            return Err("native ticks are not consecutive from 1".into());
        }
        let fix = match body.get("observed") {
            Some(v) if !v.is_null() => Some(Fix {
                pos: Pt::of(get(v, "/position")?)?,
                age: int(v, "/age_ticks")?,
                confidence: int(v, "/confidence_permille")?,
            }),
            _ => None,
        };
        let (sample, dropped) = gps.get(&tick).copied().unwrap_or((None, false));
        rows.push(Row {
            from: Pt::of(get(body, "/truth_from")?)?,
            truth: Pt::of(get(body, "/truth_position")?)?,
            command_mm: opt_int(body, "/action/distance_mm").unwrap_or(0),
            fix,
            fallback: text(body, "/safety_state")? == "fallback",
            gps: sample,
            dropped,
        });
    }
    if rows.is_empty() {
        return Err("native run has no ticks".into());
    }
    Ok((rows, transitions))
}

fn some(v: i64) -> Option<f64> {
    Some(v as f64)
}

fn flag(v: bool) -> Option<f64> {
    Some(if v { 1.0 } else { 0.0 })
}

fn channels(rows: &[Row], start: Pt, goal: Pt) -> Vec<Channel> {
    let mut cols: BTreeMap<&str, Vec<Option<f64>>> =
        CHANNELS.iter().map(|c| (c.0, Vec::new())).collect();
    let mut push =
        |id: &str, value: Option<f64>| cols.get_mut(id).expect("known channel").push(value);
    for id in [
        "gps_x_mm",
        "gps_y_mm",
        "held_x_mm",
        "held_y_mm",
        "confidence_permille",
        "fix_age_ticks",
        "gps_dropped",
        "command_mm",
        "moved_mm",
        "fallback",
    ] {
        push(id, None);
    }
    push("truth_x_mm", some(start.x));
    push("truth_y_mm", some(start.y));
    push("goal_distance_mm", some(start.manhattan(goal)));
    for row in rows {
        push("truth_x_mm", some(row.truth.x));
        push("truth_y_mm", some(row.truth.y));
        push("gps_x_mm", row.gps.map(|p| p.x as f64));
        push("gps_y_mm", row.gps.map(|p| p.y as f64));
        push("held_x_mm", row.fix.as_ref().map(|f| f.pos.x as f64));
        push("held_y_mm", row.fix.as_ref().map(|f| f.pos.y as f64));
        push(
            "confidence_permille",
            row.fix.as_ref().map(|f| f.confidence as f64),
        );
        push("fix_age_ticks", row.fix.as_ref().map(|f| f.age as f64));
        push("gps_dropped", flag(row.dropped));
        push("command_mm", some(row.command_mm));
        push("moved_mm", some(row.from.manhattan(row.truth)));
        push("fallback", flag(row.fallback));
        push("goal_distance_mm", some(row.truth.manhattan(goal)));
    }
    CHANNELS
        .iter()
        .map(|c| Channel {
            id: c.0.into(),
            label: c.1.into(),
            unit: c.2.into(),
            group: c.3.into(),
            kind: c.4.into(),
            timebase: TIMEBASE.into(),
            values: cols.remove(c.0).expect("known channel"),
        })
        .collect()
}

fn event(t: i64, kind: &str, label: String, severity: &str, source: &str, detail: Value) -> Event {
    Event {
        t: t as f64,
        kind: kind.into(),
        label,
        severity: severity.into(),
        source: source.into(),
        detail,
    }
}

fn label_of(id: &str) -> String {
    catalog::requirement(id).map_or_else(|| id.to_owned(), |r| r.1.to_owned())
}

fn word(id: &str) -> String {
    id.replace('_', " ")
}

fn expected_text(def: Option<&Value>) -> String {
    let Some(def) = def else {
        return "the contract holds".into();
    };
    let field = |name: &str| {
        def.get(name)
            .and_then(Value::as_str)
            .map(word)
            .unwrap_or_default()
    };
    match def.get("type").and_then(Value::as_str) {
        Some("always") => format!("{} holds at every tick", field("predicate")),
        Some("never") => format!("{} never holds", field("predicate")),
        Some("bounded_response") => {
            let within = def.get("within_ticks").and_then(Value::as_i64).unwrap_or(0);
            let lasting = def
                .get("trigger_for_ticks")
                .and_then(Value::as_i64)
                .unwrap_or(1);
            let lasting = if lasting > 1 {
                format!(" holding for {lasting} ticks")
            } else {
                String::new()
            };
            let per = if def.get("correlation").is_some_and(|c| !c.is_null()) {
                " (checked per command)"
            } else {
                ""
            };
            format!(
                "within {within} ticks of {}{lasting}, {} holds{per}",
                field("trigger"),
                field("required")
            )
        }
        Some("ordered_transition") => {
            let edges: Vec<String> = def
                .get("sequence")
                .and_then(Value::as_array)
                .map(|s| {
                    s.iter()
                        .map(|e| {
                            format!(
                                "{} to {}",
                                e.get("from").and_then(Value::as_str).unwrap_or("?"),
                                e.get("to").and_then(Value::as_str).unwrap_or("?")
                            )
                        })
                        .collect()
                })
                .unwrap_or_default();
            format!(
                "{} transitions occur in order: {}",
                field("domain"),
                edges.join(", ")
            )
        }
        _ => "the contract holds".into(),
    }
}

fn contract_status(outcome: &str) -> &'static str {
    match outcome {
        "PASS" => "pass",
        "FAIL" => "fail",
        _ => "not_evaluated",
    }
}

fn observed_pass(kind: &str, result: &Value, ticks: usize) -> String {
    match kind {
        "always" => format!("held at all {ticks} ticks"),
        "never" => format!("never held in {ticks} ticks"),
        "bounded_response" => match (
            opt_int(result, "/first_trigger_tick"),
            opt_int(result, "/deadline_tick"),
        ) {
            (Some(trigger), Some(deadline)) => {
                format!(
                    "triggered at tick {trigger} and satisfied by the deadline at tick {deadline}"
                )
            }
            (Some(trigger), None) => format!("triggered at tick {trigger} and satisfied"),
            _ => "never triggered".into(),
        },
        "ordered_transition" => "all declared transitions observed in order".into(),
        _ => "no violation observed".into(),
    }
}

fn observed_fail(failure: Option<&Value>, result: &Value) -> String {
    let violation = opt_int(result, "/first_violation_tick");
    let Some(f) = failure else {
        return format!(
            "violated at tick {}",
            violation.map_or("?".into(), |v| v.to_string())
        );
    };
    let base = f
        .get("detail")
        .and_then(Value::as_str)
        .or_else(|| f.get("evidence_reason").and_then(Value::as_str))
        .map(word)
        .unwrap_or_else(|| "violated".into());
    let mut parts = vec![base];
    if let Some(t) = opt_int(f, "/first_trigger_tick") {
        parts.push(format!("triggered at tick {t}"));
    }
    if let Some(d) = opt_int(f, "/applicable_deadline_tick") {
        parts.push(format!("deadline at tick {d}"));
    }
    if let Some(v) = violation {
        parts.push(format!("violated at tick {v}"));
    }
    parts.join("; ")
}

fn behaviour_note(failure: Option<&Value>) -> String {
    let at = |name: &str| {
        failure
            .and_then(|f| f.get(name))
            .and_then(Value::as_str)
            .map(word)
    };
    match (
        at("actuator_behavior_at_trigger"),
        at("actuator_behavior_at_violation"),
    ) {
        (Some(a), Some(b)) => {
            format!("Actuator behaviour at the trigger: {a}; at the violation: {b}.")
        }
        (None, Some(b)) => format!("Actuator behaviour at the violation: {b}."),
        (Some(a), None) => format!("Actuator behaviour at the trigger: {a}."),
        _ => String::new(),
    }
}

struct Verdicts {
    results: Vec<RequirementResult>,
    events: Vec<Event>,
}

fn verdicts(native: &Native, ticks: usize) -> R<Verdicts> {
    let n = ticks as f64;
    let mut out = Verdicts {
        results: Vec::new(),
        events: Vec::new(),
    };
    for inv in array(&native.report, "/invariants")? {
        let name = text(inv, "/name")?;
        let passed = get(inv, "/passed")?.as_bool().unwrap_or(false);
        let first = inv.pointer("/failures/0");
        let described = catalog::requirement(name).map_or("the invariant holds", |r| r.3);
        let (status, expected, observed, t, explanation) = match (passed, first) {
            (true, _) => (
                "pass",
                described.to_owned(),
                format!("held at all {ticks} ticks"),
                Some(n),
                String::new(),
            ),
            (false, Some(f)) => {
                let count = array(inv, "/failures").map_or(1, Vec::len);
                (
                    "fail",
                    text(f, "/expected").unwrap_or(described).to_owned(),
                    text(f, "/observed_result").unwrap_or("violated").to_owned(),
                    opt_int(f, "/tick").map(|t| t as f64),
                    format!(
                        "{count} failing tick(s) recorded on the true state; the first is shown."
                    ),
                )
            }
            (false, None) => (
                "fail",
                described.to_owned(),
                "violated".into(),
                None,
                String::new(),
            ),
        };
        if status == "fail" {
            out.events.push(event(
                t.unwrap_or(n) as i64,
                "invariant_violation",
                format!("Invariant violated: {}", label_of(name)),
                "violation",
                "verifier",
                json!({"id": name, "category": "invariant", "expected": expected, "observed": observed}),
            ));
        }
        out.results.push(RequirementResult {
            id: name.into(),
            label: label_of(name),
            category: "invariant".into(),
            status: status.into(),
            expected,
            observed,
            t,
            explanation,
        });
    }
    let defs = array(&native.verification, "/contract_set/contracts")?;
    let failures = array(&native.verification, "/failures")?;
    for result in array(&native.verification, "/contract_results")? {
        let id = text(result, "/contract_id")?;
        let kind = text(result, "/property_type")?;
        let status = contract_status(text(result, "/outcome")?);
        let def = defs
            .iter()
            .find(|d| d.get("id").and_then(Value::as_str) == Some(id));
        let failure = failures
            .iter()
            .find(|f| f.get("contract_id").and_then(Value::as_str) == Some(id));
        let expected = expected_text(def);
        let (observed, t, explanation) = match status {
            "pass" => (observed_pass(kind, result, ticks), Some(n), String::new()),
            "fail" => (
                observed_fail(failure, result),
                opt_int(result, "/first_violation_tick").map(|v| v as f64),
                behaviour_note(failure),
            ),
            _ => {
                let evidence = result
                    .pointer("/evidence")
                    .and_then(Value::as_array)
                    .and_then(|e| e.last());
                let detail = evidence
                    .and_then(|e| e.get("detail"))
                    .and_then(Value::as_str)
                    .unwrap_or("not decided");
                let reason = evidence
                    .and_then(|e| e.get("reason"))
                    .and_then(Value::as_str)
                    .map(word)
                    .unwrap_or_default();
                (
                    format!("inconclusive: {detail} ({reason})"),
                    Some(n),
                    "The run ended before the contract could be decided; it counts neither as a pass nor as a failure."
                        .into(),
                )
            }
        };
        if status == "fail" {
            out.events.push(event(
                t.unwrap_or(n) as i64,
                "contract_violation",
                format!("Contract violated: {}", label_of(id)),
                "violation",
                "verifier",
                json!({"id": id, "category": "requirement", "expected": expected, "observed": observed}),
            ));
        }
        out.results.push(RequirementResult {
            id: id.into(),
            label: label_of(id),
            category: "requirement".into(),
            status: status.into(),
            expected,
            observed,
            t,
            explanation,
        });
    }
    Ok(out)
}

struct MissionResult {
    outcome: Outcome,
    requirement: RequirementResult,
    events: Vec<Event>,
}

fn mission_result(native: &Native, ticks: usize, final_distance: i64) -> R<MissionResult> {
    let m = &native.mission;
    let code = text(m, "/outcome")?;
    let reason = m.get("reason").and_then(Value::as_str);
    let total = int(m, "/waypoint_count")?;
    let done = int(m, "/waypoints_completed")?;
    let fallback = int(m, "/fallback_ticks")?;
    let window = int(m, "/policy/stall_window_ticks")?;
    let min_progress = int(m, "/policy/min_progress_mm")?;
    let completion = opt_int(m, "/completion_tick");
    let stall = opt_int(m, "/stall_detected_tick");
    let (label, status, explanation) = match code {
        "completed" => (
            "Mission completed",
            "success",
            format!(
                "All {total} waypoint(s) were reached; the mission completed at tick {} with {fallback} tick(s) in fallback.",
                completion.unwrap_or(ticks as i64)
            ),
        ),
        "incomplete" => (
            "Mission incomplete",
            "partial",
            format!(
                "{done} of {total} waypoint(s) were reached when the run ended after {ticks} ticks; the vehicle was \
                 {final_distance} mm (Manhattan) from the goal after {fallback} tick(s) in fallback."
            ),
        ),
        "stalled" => (
            "Mission stalled",
            if reason == Some("expected_fault_hold") {
                "partial"
            } else {
                "failure"
            },
            format!(
                "No progress of at least {min_progress} mm for {window} ticks (detected at tick {}); the vehicle was \
                 {final_distance} mm from the goal. {}",
                stall.map_or("?".into(), |s| s.to_string()),
                match reason {
                    Some("expected_fault_hold") =>
                        "The hold is explained by an active fault or by fallback.",
                    _ => "No fault or fallback explains the hold.",
                }
            ),
        ),
        _ => (
            "Completion declared without reaching the goal",
            "failure",
            format!(
                "The controller declared completion at tick {} but the true position had not reached every waypoint \
                 (it relies on observations, not on truth).",
                completion.map_or("?".into(), |c| c.to_string())
            ),
        ),
    };
    let mut events = Vec::new();
    match (code, completion, stall) {
        ("completed", Some(t), _) => events.push(event(
            t,
            "goal_reached",
            "Goal reached".into(),
            "info",
            "truth",
            json!({"waypoints": total}),
        )),
        ("invalid_terminated", Some(t), _) => events.push(event(
            t,
            "completion_unconfirmed",
            "Controller declared completion, goal not reached".into(),
            "warning",
            "controller",
            json!({"waypoints_completed": done, "waypoints": total}),
        )),
        ("stalled", _, Some(t)) => events.push(event(
            t,
            "mission_stalled",
            "Mission stalled".into(),
            "warning",
            "verifier",
            json!({"stall_window_ticks": window, "min_progress_mm": min_progress, "reason": reason}),
        )),
        _ => {}
    }
    let passed = code == "completed";
    let requirement = RequirementResult {
        id: "mission_completion".into(),
        label: label_of("mission_completion"),
        category: "requirement".into(),
        status: if passed { "pass" } else { "fail" }.into(),
        expected: format!(
            "all {total} waypoint(s) reached, confirmed on the true position, with no stall of {window} ticks"
        ),
        observed: format!(
            "{code}; {done} of {total} waypoint(s) reached; {final_distance} mm from the goal at the end"
        ),
        t: Some(completion.or(stall).unwrap_or(ticks as i64) as f64),
        explanation: if passed {
            String::new()
        } else {
            explanation.clone()
        },
    };
    Ok(MissionResult {
        outcome: Outcome {
            code: code.into(),
            label: label.into(),
            status: status.into(),
            explanation,
        },
        requirement,
        events,
    })
}

fn fault_events(native: &Native) -> R<Vec<Event>> {
    let mut out = Vec::new();
    let window = |kind: &str, detail: Value, start: i64, end: i64, out: &mut Vec<Event>| {
        out.push(event(
            start,
            "fault_start",
            format!("Fault window opens: {}", word(kind)),
            "fault",
            "fault",
            detail.clone(),
        ));
        out.push(event(
            end,
            "fault_end",
            format!("Fault window closes (last tick): {}", word(kind)),
            "fault",
            "fault",
            detail,
        ));
    };
    for w in array(&native.events, "/scenario/sensors/gps/dropout_windows")? {
        let (start, end) = (int(w, "/start_tick")?, int(w, "/end_tick")?);
        let detail = json!({"fault": catalog::GPS_DROPOUT, "start_tick": start, "end_tick": end});
        window(catalog::GPS_DROPOUT, detail, start, end, &mut out);
    }
    for fault in array(&native.verification, "/actuator_config/faults")? {
        let kind = text(fault, "/kind")?;
        for w in array(fault, "/windows")? {
            let (start, end) = (int(w, "/start_tick")?, int(w, "/end_tick")?);
            let mut detail = json!({"fault": kind, "id": text(fault, "/id")?, "start_tick": start, "end_tick": end});
            if let Some(delay) = opt_int(fault, "/delay_ticks") {
                detail["delay_ticks"] = json!(delay);
            }
            window(kind, detail, start, end, &mut out);
        }
    }
    // The actuator trace itself is only hashed; its effects are recorded where a failed contract cites them.
    let mut seen = std::collections::BTreeSet::new();
    for failure in array(&native.verification, "/failures")? {
        let Some(list) = failure.get("fault_events").and_then(Value::as_array) else {
            continue;
        };
        for item in list {
            let body = get(item, "/event")?;
            let kind = text(body, "/kind")?;
            let (tick, source) = (int(body, "/tick")?, int(body, "/source_command_tick")?);
            if kind == "fault_window_active" || !seen.insert((kind.to_owned(), tick, source)) {
                continue;
            }
            let due = opt_int(body, "/due_tick");
            let label = match kind {
                "command_lost" => format!("Actuator dropped the command issued at tick {source}"),
                "command_delayed" => format!(
                    "Actuator held back the command issued at tick {source} until tick {}",
                    due.map_or("?".into(), |d| d.to_string())
                ),
                "delayed_command_executed" => {
                    format!("Delayed command from tick {source} executed")
                }
                "current_command_ignored_by_delayed_command" => {
                    "Current command overridden by a delayed command".into()
                }
                "continued_movement" => {
                    format!("Stop ignored: movement from tick {source} repeated")
                }
                "pending_at_termination" => {
                    format!("Delayed command from tick {source} still pending at the end")
                }
                other => word(other),
            };
            out.push(event(
                tick,
                &format!("actuator_{kind}"),
                label,
                "fault",
                "fault",
                json!({"fault_id": text(body, "/fault_id")?, "source_command_tick": source,
                       "due_tick": due, "execution_tick": opt_int(body, "/execution_tick")}),
            ));
        }
    }
    Ok(out)
}

fn transition_events(transitions: &[Transition]) -> Vec<Event> {
    transitions
        .iter()
        .map(|t| {
            let safety = t.subsystem == "safety";
            event(
                t.tick,
                &format!("{}_transition", t.subsystem),
                format!(
                    "{}: {} to {} ({})",
                    t.subsystem,
                    t.from,
                    t.to,
                    word(&t.reason)
                ),
                if safety { "mode" } else { "info" },
                "controller",
                json!({"subsystem": t.subsystem, "from": t.from, "to": t.to, "reason": t.reason}),
            )
        })
        .collect()
}

fn scene(native: &Native, start: Pt, goal: Pt) -> R<Value> {
    let s = &native.events;
    let points = |list: &Vec<Value>| -> R<Vec<Value>> {
        list.iter().map(|p| Ok(Pt::of(p)?.json())).collect()
    };
    let zones = vec![json!({"vertices": points(array(s, "/scenario/restricted_zone/vertices")?)?})];
    let windows: Vec<Value> = array(s, "/scenario/sensors/gps/dropout_windows")?.clone();
    Ok(json!({
        "kind": "ground-2d",
        "units": "mm",
        "tick_ms": int(s, "/scenario/tick_ms")?,
        "bounds": {
            "min_x": int(s, "/scenario/bounds/min_x_mm")?, "max_x": int(s, "/scenario/bounds/max_x_mm")?,
            "min_y": int(s, "/scenario/bounds/min_y_mm")?, "max_y": int(s, "/scenario/bounds/max_y_mm")?,
        },
        "start": start.json(),
        "heading": text(s, "/scenario/vehicle/heading")?,
        "step_mm": int(s, "/scenario/vehicle/step_mm")?,
        "goal": goal.json(),
        "waypoints": points(array(s, "/scenario/mission/waypoints")?)?,
        "arrival_radius_mm": int(s, "/scenario/mission/arrival_radius_mm")?,
        "restricted_zones": zones,
        "gps_dropout_windows": windows,
    }))
}

fn metric(id: &str, label: &str, value: Option<i64>, unit: &str, group: &str) -> Metric {
    Metric {
        id: id.into(),
        label: label.into(),
        value: value.map(|v| v as f64),
        unit: unit.into(),
        group: group.into(),
    }
}

fn reproduce(request: &RunRequest, policy: &Policy) -> Vec<String> {
    let args = native::run_args(
        &RunArgs {
            inputs: Path::new("inputs"),
            output: Path::new("native"),
            seed: request.seed,
            controller: &request.controller,
            policy: *policy,
        },
        "inputs/scenario.json".as_ref(),
        "inputs/contracts.json".as_ref(),
        "inputs/actuator.json".as_ref(),
        "native".as_ref(),
    );
    let run: Vec<String> = args
        .iter()
        .map(|a| a.to_string_lossy().into_owned())
        .collect();
    vec![
        format!("vv-lab {}", run.join(" ")),
        "vv-lab replay-m4 native/m4.json".into(),
    ]
}

pub fn build(request: &RunRequest, policy: &Policy, native: &Native) -> R<RunRecord> {
    let (rows, transitions) = parse_events(native)?;
    let ticks = rows.len();
    let start = Pt::of(get(&native.events, "/scenario/vehicle/start")?)?;
    let waypoints = array(&native.events, "/scenario/mission/waypoints")?;
    let goal = Pt::of(waypoints.last().ok_or("scenario has no waypoint")?)?;
    let last = rows.last().expect("rows are not empty");
    let final_distance = last.truth.manhattan(goal);

    let verdicts = verdicts(native, ticks)?;
    let result = mission_result(native, ticks, final_distance)?;

    let mut events = fault_events(native)?;
    events.extend(transition_events(&transitions));
    events.extend(verdicts.events);
    events.extend(result.events);
    events.sort_by(|a, b| a.t.total_cmp(&b.t));

    let mut requirements = verdicts.results;
    requirements.push(result.requirement);

    let failed: Vec<&RequirementResult> = requirements
        .iter()
        .filter(|r| r.category == "invariant" && r.status == "fail")
        .collect();
    let unsafe_run = text(&native.report, "/status")? != "passed" || !failed.is_empty();
    let safety = Safety {
        status: if unsafe_run { "unsafe" } else { "safe" }.into(),
        class: None,
        explanation: if failed.is_empty() {
            format!(
                "All safety invariants held on the true position at every one of the {ticks} ticks."
            )
        } else {
            let names: Vec<String> = failed
                .iter()
                .map(|r| {
                    format!(
                        "{} (first at tick {})",
                        r.id,
                        r.t.map_or("?".into(), |t| format!("{t}"))
                    )
                })
                .collect();
            format!(
                "Safety invariants violated on the true state: {}.",
                names.join(", ")
            )
        },
    };

    let moved: i64 = rows.iter().map(|r| r.from.manhattan(r.truth)).sum();
    let metrics = vec![
        metric(
            "ticks",
            "Ticks simulated",
            Some(ticks as i64),
            "tick",
            "Run",
        ),
        metric(
            "goal_distance_final_mm",
            "Distance to the goal at the end",
            Some(final_distance),
            "mm",
            "Mission",
        ),
        metric(
            "distance_travelled_mm",
            "Distance travelled",
            Some(moved),
            "mm",
            "Mission",
        ),
        metric(
            "waypoints_completed",
            "Waypoints reached",
            opt_int(&native.mission, "/waypoints_completed"),
            "",
            "Mission",
        ),
        metric(
            "fallback_ticks",
            "Ticks in fallback",
            opt_int(&native.mission, "/fallback_ticks"),
            "tick",
            "Safety",
        ),
        metric(
            "gps_dropout_ticks",
            "Ticks without a GPS sample",
            Some(rows.iter().filter(|r| r.dropped).count() as i64),
            "tick",
            "Perception",
        ),
        metric(
            "movement_action_ticks",
            "Ticks with a movement command",
            opt_int(&native.manifest, "/metrics/movement_action_ticks"),
            "tick",
            "Control",
        ),
        metric(
            "failed_safety_invariants",
            "Failed safety invariants",
            opt_int(&native.manifest, "/metrics/failed_safety_invariants"),
            "",
            "Safety",
        ),
        metric(
            "failed_temporal_contracts",
            "Failed temporal contracts",
            opt_int(&native.manifest, "/metrics/failed_temporal_contracts"),
            "",
            "Requirements",
        ),
        metric(
            "inconclusive_temporal_contracts",
            "Inconclusive temporal contracts",
            opt_int(&native.manifest, "/metrics/inconclusive_temporal_contracts"),
            "",
            "Requirements",
        ),
    ];

    let manifest = catalog::manifest();
    Ok(RunRecord {
        schema: RECORD_SCHEMA.into(),
        domain: DomainRef {
            id: DOMAIN_ID.into(),
            version: manifest.version,
            contract: format!("{CONTRACT_NAME}/{CONTRACT_MAJOR}.{CONTRACT_MINOR}"),
        },
        request: request.clone(),
        provenance: Provenance {
            source_sha256: text(&native.manifest, "/source_sha256")?.into(),
            simulator: "vv-lab".into(),
            artifacts: Vec::new(),
            reproduce: reproduce(request, policy),
        },
        model_validity: manifest.model_validity,
        outcome: result.outcome,
        safety,
        timebases: BTreeMap::from([(
            TIMEBASE.to_owned(),
            (0..=ticks).map(|t| t as f64).collect(),
        )]),
        channels: channels(&rows, start, goal),
        events,
        requirements,
        metrics,
        scene: scene(native, start, goal)?,
        notes: vec![
            "2D kinematic model: the vehicle moves a fixed step along one axis per movement command. There is no inertia, steering, terrain or environment, and the result says nothing about a physical vehicle.".into(),
            "Tick 0 is the start state. Tick k is the state at the end of tick k: truth, held fix and movement are what the vehicle did during that tick.".into(),
            "Safety invariants are judged on the true position. The controller only sees GPS observations, whose confidence falls as the last fix ages.".into(),
            "Temporal contracts and the mission result are reported separately from safety: a stalled or incomplete mission can be safe, and a completed one can still violate a contract.".into(),
            "The seed only drives random GPS dropout and noise, packet loss and probabilistic actuator faults. These missions and the faults of this domain use none of them, so a different seed changes the recorded seed and the run identity but not the trajectory.".into(),
            "Actuator effects are listed in the events only where a failed contract cites them; the full actuator trace is only hashed by the simulator.".into(),
        ],
        entities: None,
        mission: None,
    })
}
