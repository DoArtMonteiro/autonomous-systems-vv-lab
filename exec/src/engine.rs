//! In-process execution of a plan, with an append-only log, resume after interruption, adaptive
//! worker count and retention by policy.
//!
//! Output directory:
//! - `spec.json`, `base-case.json`: the inputs, byte for byte.
//! - `plan.json`: the plan manifest; a resume must match its `plan_sha256`.
//! - `log.jsonl`: one line per completed run in completion order, `<sha256> <record JSON>`, where
//!   the hash covers the record JSON bytes of that line.
//! - `records.jsonl`: the same lines sorted by plan index, written once every run is logged. Its
//!   bytes do not depend on the number of workers, on interruptions or on resumes.
//! - `cases/v<variant>.json`, `retained/<index>-s<seed>/`: canonical artifacts kept by policy.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

use crate::plan::{Plan, RunRef, sha256_hex};
use crate::sched::{MemoryProbe, PER_WORKER_MB, RESERVE_MB, workers_for};
use crate::spec::RetentionPolicy;

/// The outcome of one run as logged. Recomputable from the plan, the case and the seed.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Record {
    pub index: u64,
    pub variant: u32,
    pub arm: u32,
    pub cell: u32,
    pub replicate: u32,
    pub seed: u64,
    pub case_sha256: String,
    pub in_envelope: bool,
    /// Set when the run produced no artifacts; the other result fields are then empty.
    pub error: Option<String>,
    pub trace_sha256: Option<String>,
    pub verification_sha256: Option<String>,
    pub outcome: Option<String>,
    pub requirements_pass: Option<bool>,
    pub invariants_pass: Option<bool>,
    pub all_pass: Option<bool>,
    pub metrics: BTreeMap<String, f64>,
}

impl Record {
    /// A run counted as a failure for retention: an error or a failed verdict.
    pub fn is_failure(&self) -> bool {
        self.error.is_some() || self.all_pass == Some(false)
    }
}

/// Runs one plan entry in process.
pub fn run_one(plan: &Plan, r: &RunRef, case: &[u8]) -> Record {
    let v = &plan.variants[r.variant as usize];
    let mut rec = Record {
        index: r.index,
        variant: r.variant,
        arm: v.arm,
        cell: v.cell,
        replicate: r.replicate,
        seed: r.seed,
        case_sha256: v.case_sha256.clone(),
        in_envelope: v.in_envelope,
        error: None,
        trace_sha256: None,
        verification_sha256: None,
        outcome: None,
        requirements_pass: None,
        invariants_pass: None,
        all_pass: None,
        metrics: BTreeMap::new(),
    };
    match plan.domain.run(case, r.seed) {
        Ok(o) => {
            rec.all_pass = o.all_pass();
            rec.trace_sha256 = Some(o.trace_sha256);
            rec.verification_sha256 = o.verification_sha256;
            rec.outcome = Some(o.outcome);
            rec.requirements_pass = o.requirements_pass;
            rec.invariants_pass = o.invariants_pass;
            rec.metrics = o.metrics;
        }
        Err(e) => rec.error = Some(e.to_string()),
    }
    rec
}

/// One log line for a record, newline included.
pub fn log_line(rec: &Record) -> String {
    let json = serde_json::to_string(rec).expect("a record always serialises");
    format!("{} {json}\n", sha256_hex(json.as_bytes()))
}

/// Checks a log line against its hash and the plan, and returns its record.
pub fn parse_line(plan: &Plan, line: &str) -> Result<Record, String> {
    let (hash, json) = line
        .split_once(' ')
        .ok_or("log line has no hash separator")?;
    if sha256_hex(json.as_bytes()) != hash {
        return Err("log line hash does not match its record".into());
    }
    let rec: Record = serde_json::from_str(json).map_err(|e| format!("log record: {e}"))?;
    let r = plan
        .runs
        .get(rec.index as usize)
        .ok_or(format!("record {} is outside the plan", rec.index))?;
    let v = &plan.variants[r.variant as usize];
    if rec.variant != r.variant
        || rec.seed != r.seed
        || rec.replicate != r.replicate
        || rec.arm != v.arm
        || rec.cell != v.cell
        || rec.case_sha256 != v.case_sha256
        || rec.in_envelope != v.in_envelope
    {
        return Err(format!("record {} does not match the plan", rec.index));
    }
    Ok(rec)
}

pub struct Options<'a> {
    pub probe: &'a dyn MemoryProbe,
    /// Upper bound on workers; the specification's `max_threads` and the processors also apply.
    pub max_threads: Option<usize>,
    pub cancel: &'a AtomicBool,
    /// Stop after this many runs in this invocation; for tests of interruption.
    pub stop_after: Option<u64>,
    /// Completed runs between two memory probes.
    pub probe_every: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Summary {
    pub runs: u64,
    pub already_logged: u64,
    pub executed: u64,
    pub complete: bool,
    pub stopped_by: Option<String>,
    pub workers_start: usize,
    pub workers_min: usize,
    pub workers_max: usize,
    pub wall_s: f64,
}

/// Writes `bytes` to a temporary file next to `path`, flushes it to disk and renames it, so a
/// reader sees either the old file or the complete new one.
pub fn write_new(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let tmp = path.with_extension("tmp");
    let mut f = fs::File::create(&tmp).map_err(|e| format!("{}: {e}", tmp.display()))?;
    f.write_all(bytes)
        .and_then(|()| f.sync_all())
        .map_err(|e| format!("{}: {e}", tmp.display()))?;
    drop(f);
    fs::rename(&tmp, path).map_err(|e| format!("{}: {e}", path.display()))
}

/// Outputs never go under a directory named `runs`: the historical runs of the lab live there.
/// The nearest existing ancestor is resolved first, so a relative path, a symbolic link or a
/// junction into `runs` is refused as well.
pub fn guard_output(out: &Path) -> Result<(), String> {
    let refuse = |p: &Path| {
        p.components()
            .any(|c| matches!(c, Component::Normal(n) if n.eq_ignore_ascii_case("runs")))
    };
    let mut existing = out;
    let mut rest = Vec::new();
    while !existing.exists() {
        match (existing.parent(), existing.file_name()) {
            (Some(parent), Some(name)) => {
                rest.push(name.to_owned());
                existing = if parent.as_os_str().is_empty() {
                    Path::new(".")
                } else {
                    parent
                };
            }
            _ => break,
        }
    }
    let mut resolved = fs::canonicalize(existing).unwrap_or_else(|_| existing.to_path_buf());
    resolved.extend(rest.iter().rev());
    if refuse(out) || refuse(&resolved) {
        return Err(format!(
            "{}: vv-exec does not write under a directory named runs (historical evidence)",
            out.display()
        ));
    }
    Ok(())
}

/// Files that `open_output` may find in a directory without `plan.json`: the inputs written
/// before an interruption, their temporaries and the lock.
const INIT_FILES: [&str; 6] = [
    "spec.json",
    "base-case.json",
    "spec.tmp",
    "base-case.tmp",
    "plan.tmp",
    ".lock",
];

/// Writes an input, or checks that the copy already there is byte-identical.
fn write_or_check(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if path.exists() {
        if fs::read(path).map_err(|e| format!("{}: {e}", path.display()))? != bytes {
            return Err(format!(
                "{} differs from the input of this plan; refusing to mix runs",
                path.display()
            ));
        }
        return Ok(());
    }
    write_new(path, bytes)
}

/// Prepares `out` for this plan: a new directory receives the inputs and the plan; an existing one
/// must hold the same plan.
fn open_output(plan: &Plan, out: &Path) -> Result<(), String> {
    let manifest_path = out.join("plan.json");
    if manifest_path.exists() {
        let stored: serde_json::Value = serde_json::from_slice(
            &fs::read(&manifest_path).map_err(|e| format!("plan.json: {e}"))?,
        )
        .map_err(|e| format!("plan.json: {e}"))?;
        if stored["plan_sha256"] != plan.plan_sha256.as_str() {
            return Err(format!(
                "{} holds a different plan ({}); refusing to mix runs",
                out.display(),
                stored["plan_sha256"]
            ));
        }
        // The inputs are written before the plan, so they are present; check them anyway.
        write_or_check(&out.join("spec.json"), plan.spec_bytes())?;
        return write_or_check(&out.join("base-case.json"), plan.base_bytes());
    }
    // Without a plan, only the inputs of an interrupted initialisation may be present.
    for entry in fs::read_dir(out).map_err(|e| format!("{}: {e}", out.display()))? {
        let name = entry.map_err(|e| e.to_string())?.file_name();
        if !INIT_FILES.iter().any(|f| name == *f) {
            return Err(format!(
                "{} is not empty and holds no plan; refusing to write into it",
                out.display()
            ));
        }
    }
    write_or_check(&out.join("spec.json"), plan.spec_bytes())?;
    write_or_check(&out.join("base-case.json"), plan.base_bytes())?;
    let mut m = serde_json::to_vec_pretty(&plan.manifest()).map_err(|e| e.to_string())?;
    m.push(b'\n');
    write_new(&manifest_path, &m)
}

/// Reads the log, drops a torn final line and returns which plan entries are already done.
fn read_log(plan: &Plan, path: &Path) -> Result<Vec<bool>, String> {
    let mut done = vec![false; plan.runs.len()];
    if !path.exists() {
        return Ok(done);
    }
    let bytes = fs::read(path).map_err(|e| format!("log.jsonl: {e}"))?;
    let complete = bytes.iter().rposition(|&b| b == b'\n').map_or(0, |i| i + 1);
    if complete < bytes.len() {
        // A run interrupted mid-write leaves a torn last line; it is re-run.
        let f = OpenOptions::new()
            .write(true)
            .open(path)
            .map_err(|e| e.to_string())?;
        f.set_len(complete as u64).map_err(|e| e.to_string())?;
    }
    let text = std::str::from_utf8(&bytes[..complete]).map_err(|e| e.to_string())?;
    for (n, line) in text.lines().enumerate() {
        let rec = parse_line(plan, line).map_err(|e| format!("log.jsonl line {}: {e}", n + 1))?;
        if std::mem::replace(&mut done[rec.index as usize], true) {
            return Err(format!(
                "log.jsonl line {}: record {} appears twice",
                n + 1,
                rec.index
            ));
        }
    }
    Ok(done)
}

/// Executes every plan entry not yet logged in `out`.
pub fn execute(plan: &Plan, out: &Path, opt: &Options) -> Result<Summary, String> {
    let t0 = Instant::now();
    guard_output(out)?;
    fs::create_dir_all(out).map_err(|e| format!("{}: {e}", out.display()))?;
    // One writer per output directory. The operating system releases the lock when the process
    // ends, so a crash never leaves the directory locked.
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(out.join(".lock"))
        .map_err(|e| format!(".lock: {e}"))?;
    lock.try_lock().map_err(|_| {
        format!(
            "{} is being written by another vv-exec process",
            out.display()
        )
    })?;
    open_output(plan, out)?;
    let log_path = out.join("log.jsonl");
    let done = read_log(plan, &log_path)?;
    let todo: Vec<u64> = (0..plan.runs.len() as u64)
        .filter(|&i| !done[i as usize])
        .collect();
    let already = plan.runs.len() as u64 - todo.len() as u64;
    // Unbuffered: each record reaches the log in one complete write, so an interruption loses at
    // most the runs in flight, never a run counted as executed.
    let log = Mutex::new(
        OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .map_err(|e| format!("log.jsonl: {e}"))?,
    );

    let l = &plan.experiment.limits;
    let logical = std::thread::available_parallelism().map_or(1, |n| n.get());
    let cap = [l.max_threads, opt.max_threads]
        .into_iter()
        .flatten()
        .min()
        .unwrap_or(crate::spec::MAX_THREADS);
    let decide = || {
        workers_for(
            opt.probe.available_mb(),
            l.memory_budget_mb,
            logical,
            cap,
            PER_WORKER_MB,
            RESERVE_MB,
        )
    };
    let start = decide();
    // Threads are spawned up to the ceiling; those at or above `allowed` stay parked.
    let spawned = logical.min(cap).max(1);
    let allowed = AtomicUsize::new(start);
    let (min_seen, max_seen) = (AtomicUsize::new(start), AtomicUsize::new(start));
    let next = AtomicUsize::new(0);
    let executed = AtomicU64::new(0);
    let deadline = t0 + Duration::from_secs(l.max_wall_s);
    let stopped: Mutex<Option<String>> = Mutex::new(None);
    let failed: Mutex<Option<String>> = Mutex::new(None);
    let stop = |why: &str| {
        let mut s = stopped.lock().unwrap();
        if s.is_none() {
            *s = Some(why.to_string());
        }
    };

    std::thread::scope(|scope| {
        for w in 0..spawned {
            let (todo, log, next, allowed, executed) = (&todo, &log, &next, &allowed, &executed);
            let (min_seen, max_seen, stop, stopped, failed) =
                (&min_seen, &max_seen, &stop, &stopped, &failed);
            let decide = &decide;
            scope.spawn(move || {
                let mut cached: Option<(u32, Vec<u8>)> = None;
                loop {
                    if stopped.lock().unwrap().is_some() || failed.lock().unwrap().is_some() {
                        return;
                    }
                    if opt.cancel.load(Ordering::Relaxed) {
                        stop("cancelled");
                        return;
                    }
                    if Instant::now() >= deadline {
                        stop("limits.max_wall_s reached");
                        return;
                    }
                    if w >= allowed.load(Ordering::Relaxed) {
                        if next.load(Ordering::Relaxed) >= todo.len() {
                            return;
                        }
                        std::thread::sleep(Duration::from_millis(20));
                        continue;
                    }
                    if let Some(n) = opt.stop_after
                        && executed.load(Ordering::Relaxed) >= n
                    {
                        stop("stop_after reached");
                        return;
                    }
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    let Some(&index) = todo.get(i) else { return };
                    let r = &plan.runs[index as usize];
                    if cached.as_ref().is_none_or(|(v, _)| *v != r.variant) {
                        match plan.case_of_variant(r.variant) {
                            Ok(bytes) => cached = Some((r.variant, bytes)),
                            Err(e) => {
                                *failed.lock().unwrap() = Some(e);
                                return;
                            }
                        }
                    }
                    let case = &cached.as_ref().expect("cached").1;
                    let rec = run_one(plan, r, case);
                    let line = log_line(&rec);
                    if let Err(e) = log.lock().unwrap().write_all(line.as_bytes()) {
                        *failed.lock().unwrap() = Some(format!("log.jsonl: {e}"));
                        return;
                    }
                    // Whichever worker completes every probe_every-th run probes memory, so a slow
                    // or parked worker never delays the adaptation.
                    let done_now = executed.fetch_add(1, Ordering::Relaxed) + 1;
                    if done_now.is_multiple_of(opt.probe_every.max(1)) {
                        let n = decide();
                        allowed.store(n, Ordering::Relaxed);
                        min_seen.fetch_min(n, Ordering::Relaxed);
                        max_seen.fetch_max(n, Ordering::Relaxed);
                    }
                }
            });
        }
    });
    log.into_inner()
        .map_err(|_| "log writer poisoned")?
        .sync_all()
        .map_err(|e| format!("log.jsonl: {e}"))?;
    if let Some(e) = failed.into_inner().unwrap() {
        return Err(e);
    }
    let executed = executed.into_inner();
    let complete = already + executed == plan.runs.len() as u64;
    if complete {
        write_records(plan, out)?;
    }
    Ok(Summary {
        runs: plan.runs.len() as u64,
        already_logged: already,
        executed,
        complete,
        stopped_by: if complete {
            None
        } else {
            stopped.into_inner().unwrap()
        },
        workers_start: start,
        workers_min: min_seen.into_inner(),
        workers_max: max_seen.into_inner(),
        wall_s: t0.elapsed().as_secs_f64(),
    })
}

/// Sorts the log lines by plan index into `records.jsonl`. The lines are copied, not
/// re-serialised, so the bytes are those that were hashed.
fn write_records(plan: &Plan, out: &Path) -> Result<(), String> {
    let text = fs::read_to_string(out.join("log.jsonl")).map_err(|e| e.to_string())?;
    let mut lines: Vec<Option<&str>> = vec![None; plan.runs.len()];
    for line in text.lines() {
        let rec = parse_line(plan, line)?;
        lines[rec.index as usize] = Some(line);
    }
    let mut bytes = Vec::with_capacity(text.len());
    for (i, l) in lines.iter().enumerate() {
        let l = l.ok_or(format!("record {i} is missing from the log"))?;
        bytes.extend_from_slice(l.as_bytes());
        bytes.push(b'\n');
    }
    write_new(&out.join("records.jsonl"), &bytes)
}

/// Reads `records.jsonl`, checking every line against its hash and the plan, and that every plan
/// entry appears exactly once, in order.
pub fn read_records(plan: &Plan, out: &Path) -> Result<Vec<Record>, String> {
    let text =
        fs::read_to_string(out.join("records.jsonl")).map_err(|e| format!("records.jsonl: {e}"))?;
    let mut recs = Vec::with_capacity(plan.runs.len());
    for (n, line) in text.lines().enumerate() {
        let rec =
            parse_line(plan, line).map_err(|e| format!("records.jsonl line {}: {e}", n + 1))?;
        if rec.index != n as u64 {
            return Err(format!("records.jsonl line {} is out of order", n + 1));
        }
        recs.push(rec);
    }
    if recs.len() != plan.runs.len() {
        return Err(format!(
            "records.jsonl holds {} records; the plan has {}",
            recs.len(),
            plan.runs.len()
        ));
    }
    Ok(recs)
}

#[derive(Clone, Debug, Serialize)]
pub struct Retained {
    pub index: u64,
    pub dir: String,
    pub bytes: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct RetentionReport {
    pub policy: RetentionPolicy,
    pub selected: u64,
    pub retained: Vec<Retained>,
    /// Set when `max_retained` or `max_artifact_bytes` stopped retention early.
    pub truncated_by: Option<String>,
}

/// Writes the case of a variant to `cases/`, or checks the one already there.
pub fn case_file(plan: &Plan, out: &Path, variant: u32) -> Result<PathBuf, String> {
    let dir = out.join("cases");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(format!("v{variant}.json"));
    let want = &plan.variants[variant as usize].case_sha256;
    if path.exists() {
        let have = sha256_hex(&fs::read(&path).map_err(|e| e.to_string())?);
        if &have != want {
            return Err(format!("{} does not hold the planned case", path.display()));
        }
    } else {
        write_new(&path, &plan.case_of_variant(variant)?)?;
    }
    Ok(path)
}

fn dir_bytes(dir: &Path, files: &[&str]) -> Result<u64, String> {
    files.iter().try_fold(0, |acc, f| {
        fs::metadata(dir.join(f))
            .map(|m| acc + m.len())
            .map_err(|e| format!("{}: {e}", dir.join(f).display()))
    })
}

/// Retains canonical artifacts in plan order, after every run is logged, so the selection does
/// not depend on completion order. Each retained trace is checked against its record.
pub fn retain(plan: &Plan, out: &Path, records: &[Record]) -> Result<RetentionReport, String> {
    let r = &plan.experiment.retention;
    let l = &plan.experiment.limits;
    let wanted = |rec: &Record| match r.policy {
        RetentionPolicy::None => false,
        RetentionPolicy::Failures => rec.is_failure(),
        RetentionPolicy::Sample => rec.index.is_multiple_of(r.sample_every),
        RetentionPolicy::FailuresAndSample => {
            rec.is_failure() || rec.index.is_multiple_of(r.sample_every)
        }
    };
    let files = plan.domain.files();
    let root = out.join("retained");
    let mut report = RetentionReport {
        policy: r.policy,
        selected: 0,
        retained: Vec::new(),
        truncated_by: None,
    };
    let mut total = 0u64;
    for rec in records
        .iter()
        .filter(|rec| wanted(rec) && rec.error.is_none())
    {
        report.selected += 1;
        if report.truncated_by.is_some() {
            continue;
        }
        if report.retained.len() as u64 >= l.max_retained {
            report.truncated_by = Some("limits.max_retained".into());
            continue;
        }
        let name = format!("{:08}-s{}", rec.index, rec.seed);
        let dir = root.join(&name);
        let complete = files.iter().all(|f| dir.join(f).exists());
        if !complete {
            // An incomplete directory or a stale temporary one can only come from an interrupted
            // retention in this output; both are rebuilt.
            let tmp = root.join(format!(".tmp-{name}"));
            for stale in [&tmp, &dir] {
                if stale.exists() {
                    fs::remove_dir_all(stale).map_err(|e| format!("{}: {e}", stale.display()))?;
                }
            }
            let case = case_file(plan, out, rec.variant)?;
            plan.domain.write(&case, rec.seed, &tmp)?;
            let trace = sha256_hex(&fs::read(tmp.join("trace.json")).map_err(|e| e.to_string())?);
            if Some(&trace) != rec.trace_sha256.as_ref() {
                return Err(format!(
                    "record {}: the canonical writer produced a trace that differs from the logged run",
                    rec.index
                ));
            }
            if total + dir_bytes(&tmp, files)? > l.max_artifact_bytes {
                fs::remove_dir_all(&tmp).map_err(|e| format!("{}: {e}", tmp.display()))?;
                report.truncated_by = Some("limits.max_artifact_bytes".into());
                continue;
            }
            fs::rename(&tmp, &dir).map_err(|e| format!("{}: {e}", dir.display()))?;
        }
        let bytes = dir_bytes(&dir, files)?;
        if total + bytes > l.max_artifact_bytes {
            report.truncated_by = Some("limits.max_artifact_bytes".into());
            continue;
        }
        total += bytes;
        report.retained.push(Retained {
            index: rec.index,
            dir: format!("retained/{name}"),
            bytes,
        });
    }
    let mut bytes = serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    write_new(&out.join("retained.json"), &bytes)?;
    Ok(report)
}

/// Re-runs a record in process and compares it with the stored one: hashes, verdicts and errors
/// exactly; metrics to one part in 10^15, because the JSON reader may round a stored float by one
/// unit in the last place (`serde_json` without `float_roundtrip`, which must stay off: enabling it
/// would change how `vv-rocket` parses cases in this build).
pub fn recompute(plan: &Plan, rec: &Record) -> Result<(), String> {
    let r = &plan.runs[rec.index as usize];
    let case = plan.case_of_variant(r.variant)?;
    let again = run_one(plan, r, &case);
    if !same(&again, rec) {
        return Err(format!(
            "record {} differs when recomputed in process",
            rec.index
        ));
    }
    Ok(())
}

pub fn same(a: &Record, b: &Record) -> bool {
    let mut a2 = a.clone();
    a2.metrics.clear();
    let mut b2 = b.clone();
    b2.metrics.clear();
    a2 == b2
        && a.metrics.len() == b.metrics.len()
        && a.metrics
            .iter()
            .zip(&b.metrics)
            .all(|((ka, va), (kb, vb))| {
                ka == kb && (va - vb).abs() <= 1e-15 * va.abs().max(vb.abs())
            })
}

#[derive(Clone, Debug, Serialize)]
pub struct Verification {
    pub records: u64,
    /// Plan indices whose stored record differs from the record recomputed in process.
    pub mismatches: Vec<u64>,
    pub pass: bool,
}

/// Recomputes every record in process and compares it with the stored one. The log hashes only
/// detect accidental damage; this check also rejects a record that was edited and re-hashed.
pub fn verify_all(plan: &Plan, records: &[Record], threads: usize) -> Verification {
    let next = AtomicUsize::new(0);
    let bad = Mutex::new(Vec::new());
    std::thread::scope(|scope| {
        for _ in 0..threads.max(1) {
            scope.spawn(|| {
                loop {
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    let Some(rec) = records.get(i) else { return };
                    if recompute(plan, rec).is_err() {
                        bad.lock()
                            .unwrap_or_else(|p| p.into_inner())
                            .push(rec.index);
                    }
                }
            });
        }
    });
    let mut mismatches = bad.into_inner().unwrap_or_else(|p| p.into_inner());
    mismatches.sort_unstable();
    Verification {
        records: records.len() as u64,
        pass: mismatches.is_empty(),
        mismatches,
    }
}
