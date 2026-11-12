//! Scaffolding for domain host executables. A host implements `DomainHost`; `host_main` turns it
//! into the command-line protocol of the contract:
//!
//! `manifest` | `describe` | `validate <request.json>` | `run <request.json> --output <dir>` | `replay <dir>`
//!
//! The SDK owns what every host must get right in the same way: generic validation against the
//! catalog and the seed policy, the artifact list in the record, and a replay that recomputes the
//! run from its stored request and compares every file byte for byte.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::canonical::{pretty_bytes, sha256_hex};
use crate::contract::*;
use crate::validate::normalise;

pub const MAX_REQUEST_BYTES: u64 = 64 * 1024;
pub const MAX_RECORD_BYTES: u64 = 64 * 1024 * 1024;

pub enum HostError {
    Invalid(String),
    Simulation(String),
}

pub trait DomainHost {
    fn manifest(&self) -> DomainManifest;
    fn catalog(&self) -> DomainCatalog;
    /// Domain rules applied after the generic normalisation; may normalise further.
    fn check(&self, request: RunRequest) -> Result<RunRequest, String> {
        Ok(request)
    }
    /// Runs the request, writes the native artifacts into the empty directory `out` and returns the
    /// record. The SDK fills `provenance.artifacts` and writes record.json.
    fn run(&self, request: &RunRequest, out: &Path) -> Result<RunRecord, HostError>;
    /// Extra checks by the native simulator on a stored run (for example its own replay command).
    fn native_replay(&self, _dir: &Path) -> Vec<ReplayCheck> {
        Vec::new()
    }
    /// Stored native file, relative to the run directory, whose top-level `seed` the native replay
    /// uses. The SDK requires it to equal the seed of the validated request before
    /// [`DomainHost::native_replay`] runs, so a protected seed never reaches the simulator.
    fn native_seed_file(&self) -> Option<&'static str> {
        None
    }
    /// The changes to its verdict rules that the domain made since the domain versions before
    /// [`VerdictRules::since`], declared so an earlier-build replay can accept exactly those
    /// differences (and say so) instead of rejecting a valid older run. Nothing by default.
    fn verdict_rules(&self) -> VerdictRules {
        VerdictRules::none()
    }
}

/// A change of an outcome as the domain declares it: the pair (code, status) that a run stored by an
/// earlier version carries and the pair the current rules give to the same run.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct OutcomeChange {
    pub from: (&'static str, &'static str),
    pub to: (&'static str, &'static str),
}

/// A requirement whose status the new rules can change on a run stored by an earlier version.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RequirementChange {
    pub id: &'static str,
    pub from: &'static str,
    pub to: &'static str,
    pub reason: &'static str,
}

/// Changes to the verdict rules of a domain, applied by [`replay_earlier_build`] only to a run
/// recorded by a domain version older than `since`. Only verdicts and what is derived from them are
/// covered; timebases, channels, other metrics and the events that are not verdict violations must
/// still match, and anything outside the table still rejects.
#[derive(Clone, Copy, Debug)]
pub struct VerdictRules {
    /// Domain version that introduced the rules; empty for none.
    pub since: &'static str,
    pub outcomes: &'static [OutcomeChange],
    pub requirements: &'static [RequirementChange],
    /// Requirements judged at another instant by the new rules: their decisive instant and their
    /// violation event may differ.
    pub retimed: &'static [&'static str],
    /// Metrics derived from a changed verdict, which may differ.
    pub derived_metrics: &'static [&'static str],
    /// One line for the replay report.
    pub summary: &'static str,
}

impl VerdictRules {
    pub const fn none() -> Self {
        VerdictRules {
            since: "",
            outcomes: &[],
            requirements: &[],
            retimed: &[],
            derived_metrics: &[],
            summary: "",
        }
    }

    /// Whether the rules apply to a stored record: the domain version that wrote it is older than
    /// `since` and is not the current one.
    fn applies(&self, stored: &RunRecord, fresh: &RunRecord) -> bool {
        !self.since.is_empty()
            && stored.domain.version != fresh.domain.version
            && version_less(&stored.domain.version, self.since)
    }
}

/// `a < b` for dotted numeric versions; false when either does not parse.
fn version_less(a: &str, b: &str) -> bool {
    let parse = |s: &str| -> Option<Vec<u64>> { s.split('.').map(|p| p.parse().ok()).collect() };
    matches!((parse(a), parse(b)), (Some(x), Some(y)) if x < y)
}

/// Check name of the verdict re-evaluations an earlier-build replay accepted; its detail lists them.
pub const VERDICT_REEVALUATION_CHECK: &str = "verdicts re-evaluated under current rules";

/// The native file's own seed must be the validated request seed.
fn native_seed_check<H: DomainHost>(host: &H, dir: &Path, seed: u64) -> Option<ReplayCheck> {
    let rel = host.native_seed_file()?;
    let name = "the native run uses the seed of the stored request";
    let found = read_bounded(&dir.join(rel), MAX_RECORD_BYTES)
        .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).map_err(|e| e.to_string()))
        .and_then(|v| {
            v.get("seed")
                .and_then(serde_json::Value::as_u64)
                .ok_or_else(|| format!("{rel} has no integer seed"))
        });
    Some(match found {
        Ok(s) if s == seed => check(name, true, ""),
        Ok(s) => check(name, false, format!("{rel} seed {s}, request seed {seed}")),
        Err(e) => check(name, false, e),
    })
}

pub fn read_bounded(path: &Path, cap: u64) -> Result<Vec<u8>, String> {
    let meta = fs::metadata(path).map_err(|e| format!("{}: {e}", file_name(path)))?;
    if meta.len() > cap {
        return Err(format!("{} is larger than {cap} bytes", file_name(path)));
    }
    fs::read(path).map_err(|e| format!("{}: {e}", file_name(path)))
}

fn file_name(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default()
}

/// Files of a run directory with their hashes, sorted, as relative slash-separated paths.
/// Platform files (record, request, meta) are excluded: they describe the artifacts.
pub fn hash_artifacts(dir: &Path) -> Result<Vec<FileHash>, String> {
    let mut out = Vec::new();
    walk(dir, dir, &mut out)?;
    out.retain(|f| ![RECORD_FILE, REQUEST_FILE, META_FILE].contains(&f.path.as_str()));
    out.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(out)
}

fn walk(root: &Path, dir: &Path, out: &mut Vec<FileHash>) -> Result<(), String> {
    for entry in fs::read_dir(dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        let kind = entry.file_type().map_err(|e| e.to_string())?;
        if kind.is_symlink() {
            return Err("a run directory must not contain links".into());
        }
        if kind.is_dir() {
            walk(root, &path, out)?;
        } else {
            let bytes = fs::read(&path).map_err(|e| e.to_string())?;
            let rel = path
                .strip_prefix(root)
                .map_err(|e| e.to_string())?
                .components()
                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join("/");
            out.push(FileHash {
                path: rel,
                sha256: sha256_hex(&bytes),
                bytes: bytes.len() as u64,
            });
        }
    }
    Ok(())
}

pub fn validate_request<H: DomainHost>(
    host: &H,
    request: &RunRequest,
) -> Result<RunRequest, String> {
    let normal = normalise(&host.manifest(), &host.catalog(), request)?;
    host.check(normal)
}

fn parse_request(path: &Path) -> Result<RunRequest, String> {
    let bytes = read_bounded(path, MAX_REQUEST_BYTES)?;
    serde_json::from_slice(&bytes).map_err(|e| format!("invalid request: {e}"))
}

/// Runs a validated request into `out` and writes record.json. Used by `run` and by replay.
pub fn execute<H: DomainHost>(
    host: &H,
    request: &RunRequest,
    out: &Path,
) -> Result<RunRecord, HostError> {
    let mut record = host.run(request, out)?;
    if record.schema != RECORD_SCHEMA && record.schema != RECORD_SCHEMA_V2 {
        return Err(HostError::Simulation(format!(
            "record schema must be {RECORD_SCHEMA} or {RECORD_SCHEMA_V2}"
        )));
    }
    record.check_entities().map_err(HostError::Simulation)?;
    if &record.request != request {
        return Err(HostError::Simulation(
            "record.request differs from the validated request".into(),
        ));
    }
    record.provenance.artifacts = hash_artifacts(out).map_err(HostError::Simulation)?;
    fs::write(out.join(RECORD_FILE), pretty_bytes(&record))
        .map_err(|e| HostError::Simulation(format!("{RECORD_FILE}: {e}")))?;
    Ok(record)
}

static SCRATCH: AtomicU64 = AtomicU64::new(0);

fn scratch_dir() -> PathBuf {
    let n = SCRATCH.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!("vv-replay-{}-{n}", std::process::id()))
}

fn check(name: &str, pass: bool, detail: impl Into<String>) -> ReplayCheck {
    ReplayCheck {
        name: name.into(),
        pass,
        detail: detail.into(),
    }
}

/// Recomputes a stored run from its request and compares every file byte for byte.
pub fn replay<H: DomainHost>(host: &H, dir: &Path) -> ReplayReport {
    let mut checks = Vec::new();
    let parsed: Result<RunRecord, String> = read_bounded(&dir.join(RECORD_FILE), MAX_RECORD_BYTES)
        .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()));
    let mut valid_seed = None;
    match parsed {
        Err(e) => checks.push(check("record.json is a valid run record", false, e)),
        Ok(record) => {
            checks.push(check("record.json is a valid run record", true, ""));
            let name = "stored request is valid and canonical";
            match validate_request(host, &record.request) {
                Ok(normal) if normal == record.request => {
                    checks.push(check(name, true, ""));
                    valid_seed = Some(normal.seed);
                    replay_files(host, dir, &record, &normal, &mut checks);
                }
                Ok(_) => checks.push(check(name, false, "the request is not in canonical form")),
                Err(e) => checks.push(check(name, false, e)),
            }
        }
    }
    // The native simulator only sees a stored run whose request (and so its seed) is valid and
    // whose native file carries that same seed. It still runs when another stored file differs, as
    // an independent check of the tampered run.
    if let Some(seed) = valid_seed {
        let seed_check = native_seed_check(host, dir, seed);
        let seed_ok = seed_check.as_ref().is_none_or(|c| c.pass);
        checks.extend(seed_check);
        if seed_ok {
            checks.extend(host.native_replay(dir));
        }
    }
    let ok = !checks.is_empty() && checks.iter().all(|c| c.pass);
    ReplayReport {
        schema: REPLAY_SCHEMA.into(),
        status: if ok { "verified" } else { "rejected" }.into(),
        checks,
    }
}

/// Command-line flag of `replay`: the platform passes it for a stored run that an earlier build of
/// this host produced. The strict replay cannot verify such a run, because the current build
/// normalises requests differently (new parameters with defaults) and writes other text and
/// other metrics; see [`replay_earlier_build`].
pub const EARLIER_BUILD_FLAG: &str = "--earlier-build";

/// Name of the check that carries the semantic comparison of an earlier-build replay.
pub const EARLIER_BUILD_AGREEMENT_CHECK: &str =
    "recomputed result agrees with the stored record (recorded by an earlier build)";

/// Whether `normal` is `stored` plus catalogue defaults only: the same inputs, with parameters and
/// fault magnitudes that the stored request left out filled in. Returns the parameters added.
fn completes(stored: &RunRequest, normal: &RunRequest) -> Result<Vec<String>, String> {
    let same_inputs = stored.schema == normal.schema
        && stored.domain == normal.domain
        && stored.scenario == normal.scenario
        && stored.controller == normal.controller
        && stored.seed == normal.seed
        && stored.faults.len() == normal.faults.len()
        && stored.faults.iter().zip(&normal.faults).all(|(a, b)| {
            a.kind == b.kind
                && a.start == b.start
                && a.end == b.end
                && (a.magnitude.is_none() || a.magnitude == b.magnitude)
        });
    if !same_inputs {
        return Err(
            "the current catalogue changes more than defaults in the stored request".into(),
        );
    }
    for (k, v) in &stored.parameters {
        if normal.parameters.get(k) != Some(v) {
            return Err(format!(
                "stored parameter {k} = {v} is not kept by the current catalogue"
            ));
        }
    }
    Ok(normal
        .parameters
        .keys()
        .filter(|k| !stored.parameters.contains_key(*k))
        .cloned()
        .collect())
}

/// The first way in which `fresh`, recomputed by the current build, disagrees with `stored` on what
/// the run means: outcome code and status, safety status, every stored requirement's status,
/// instant and category, every stored timebase and channel, every stored event (instant, kind and
/// severity) and every stored metric. Not compared: texts (labels, explanations, notes, the
/// expected and observed text of a requirement), the scene, the entity and mission blocks and the
/// native files, so a change confined to those passes on a run of another build. Both directions are
/// checked for requirements (a fresh one the stored record lacks is accepted only if it passes and
/// the domain version differs) and for violation and warning events (a fresh one the stored record
/// lacks is a disagreement, except that for another domain version an event kind found nowhere in
/// the stored record is taken as new in the later build). `fresh` may carry
/// channels, events and metrics that the earlier build did not write.
#[cfg(test)]
fn disagreement(stored: &RunRecord, fresh: &RunRecord) -> Option<String> {
    compare(stored, fresh, &VerdictRules::none()).difference
}

/// The result of comparing a stored record with its recomputation: the first disagreement, and the
/// verdict re-evaluations that the declared rules accepted.
struct Comparison {
    difference: Option<String>,
    re_evaluated: Vec<String>,
}

/// The `id` of the requirement a violation event reports, if it is one.
fn violation_id(e: &Event) -> Option<&str> {
    (e.kind == "violation")
        .then(|| e.detail.get("id").and_then(serde_json::Value::as_str))
        .flatten()
}

/// [`disagreement`] with the verdict-rule changes a domain declared for runs of older versions (see
/// [`VerdictRules`]). With no rules this is the strict comparison.
fn compare(stored: &RunRecord, fresh: &RunRecord, rules: &VerdictRules) -> Comparison {
    let mut re_evaluated = Vec::new();
    let applies = rules.applies(stored, fresh);
    let differ = |d: String, re: Vec<String>| Comparison {
        difference: Some(d),
        re_evaluated: re,
    };
    if stored.outcome.code != fresh.outcome.code || stored.outcome.status != fresh.outcome.status {
        let declared = applies
            && rules.outcomes.iter().any(|c| {
                c.from == (stored.outcome.code.as_str(), stored.outcome.status.as_str())
                    && c.to == (fresh.outcome.code.as_str(), fresh.outcome.status.as_str())
            });
        if !declared {
            return differ(
                format!(
                    "outcome {} ({}) became {} ({})",
                    stored.outcome.code,
                    stored.outcome.status,
                    fresh.outcome.code,
                    fresh.outcome.status
                ),
                re_evaluated,
            );
        }
        re_evaluated.push(format!(
            "outcome {} ({}) is now {} ({})",
            stored.outcome.code, stored.outcome.status, fresh.outcome.code, fresh.outcome.status
        ));
    }
    if stored.safety.status != fresh.safety.status {
        return differ(
            format!(
                "safety {} became {}",
                stored.safety.status, fresh.safety.status
            ),
            re_evaluated,
        );
    }
    for q in &stored.requirements {
        let Some(x) = fresh.requirements.iter().find(|x| x.id == q.id) else {
            return differ(
                format!("requirement {} is no longer evaluated", q.id),
                re_evaluated,
            );
        };
        let declared_change = if applies && x.status != q.status {
            rules
                .requirements
                .iter()
                .find(|c| c.id == q.id && c.from == q.status && c.to == x.status)
        } else {
            None
        };
        if let Some(c) = declared_change {
            re_evaluated.push(format!(
                "{} {} is now {}: {}",
                q.id, q.status, x.status, c.reason
            ));
        }
        let status_declared = declared_change.is_some();
        let retimed = x.t != q.t && applies && rules.retimed.contains(&q.id.as_str());
        if (x.status != q.status && !status_declared)
            || (x.t != q.t && !retimed)
            || x.category != q.category
        {
            return differ(
                format!(
                    "requirement {}: {} at {:?} became {} at {:?}",
                    q.id, q.status, q.t, x.status, x.t
                ),
                re_evaluated,
            );
        }
        if retimed {
            re_evaluated.push(format!(
                "{} is judged at another instant ({:?} s before, {:?} s now)",
                q.id, q.t, x.t
            ));
        }
    }
    // The other direction: what the recomputation found must be in the stored record, or deleting
    // a failed requirement from it would pass. A requirement the stored record lacks is accepted
    // only when the build that wrote it could not have known it (another domain version) and it
    // passes; a failed or not evaluated one is never accepted.
    let same_version = stored.domain.version == fresh.domain.version;
    for x in &fresh.requirements {
        if stored.requirements.iter().any(|q| q.id == x.id) {
            continue;
        }
        if x.status != "pass" || same_version {
            return differ(
                format!(
                    "requirement {} ({}) is missing from the stored record",
                    x.id, x.status
                ),
                re_evaluated,
            );
        }
    }
    for (id, values) in &stored.timebases {
        if fresh.timebases.get(id) != Some(values) {
            return differ(format!("timebase {id} differs"), re_evaluated);
        }
    }
    for c in &stored.channels {
        match fresh.channels.iter().find(|x| x.id == c.id) {
            Some(x) if x.timebase == c.timebase && x.values == c.values => {}
            Some(_) => return differ(format!("channel {} differs", c.id), re_evaluated),
            None => {
                return differ(
                    format!("channel {} is no longer recorded", c.id),
                    re_evaluated,
                );
            }
        }
    }
    // Violation events of a verdict whose instant or status the declared rules changed.
    let covered = |e: &Event| {
        applies
            && violation_id(e).is_some_and(|id| {
                rules.retimed.contains(&id) || rules.requirements.iter().any(|c| c.id == id)
            })
    };
    for e in &stored.events {
        if covered(e) {
            continue;
        }
        if !fresh
            .events
            .iter()
            .any(|x| x.t == e.t && x.kind == e.kind && x.severity == e.severity)
        {
            return differ(
                format!("event {} at {} is not reproduced", e.kind, e.t),
                re_evaluated,
            );
        }
    }
    // Likewise a violation or warning the recomputation reports must be in the stored record. The
    // one exception: for another domain version, an event kind that appears nowhere in the stored
    // record may be a kind a later build introduced, and does not alone reject. A missing event of
    // a kind the stored record knows is always a disagreement, and so is any missing event when the
    // domain version is the same.
    for x in &fresh.events {
        if !matches!(x.severity.as_str(), "violation" | "warning") || covered(x) {
            continue;
        }
        if !same_version && !stored.events.iter().any(|e| e.kind == x.kind) {
            continue;
        }
        if !stored
            .events
            .iter()
            .any(|e| e.t == x.t && e.kind == x.kind && e.severity == x.severity)
        {
            return differ(
                format!(
                    "{} event {} at {} is missing from the stored record",
                    x.severity, x.kind, x.t
                ),
                re_evaluated,
            );
        }
    }
    for m in &stored.metrics {
        match fresh.metrics.iter().find(|x| x.id == m.id) {
            Some(x) if x.value == m.value => {}
            Some(_) if applies && rules.derived_metrics.contains(&m.id.as_str()) => {}
            Some(_) => return differ(format!("metric {} differs", m.id), re_evaluated),
            None => {
                return differ(
                    format!("metric {} is no longer recorded", m.id),
                    re_evaluated,
                );
            }
        }
    }
    Comparison {
        difference: None,
        re_evaluated,
    }
}
/// What the earlier-build replay does not compare, listed in the report so a reader of
/// `replay.json` can see the limits of the check.
pub const EARLIER_BUILD_NOT_COMPARED: &str = "texts (labels, explanations, notes, the expected and observed text of a requirement), the scene, the entity and mission blocks, channels, events and metrics that only the current build writes (so deleting a stored channel, metric or informational event is not detected), and the native simulator replay, which needs the same simulator sources";

/// Verdict flags of a native `verification.json`: the top-level `requirements_pass` and
/// `invariants_pass`, and the pass flag or status of every entry of `requirements`, `invariants`
/// and `verdicts`, by id. Hosts that write no such file give an empty map.
fn native_verdicts(v: &serde_json::Value) -> std::collections::BTreeMap<String, String> {
    let mut out = std::collections::BTreeMap::new();
    for flag in ["requirements_pass", "invariants_pass"] {
        if let Some(b) = v.get(flag).and_then(serde_json::Value::as_bool) {
            out.insert(flag.to_string(), b.to_string());
        }
    }
    for key in ["requirements", "invariants", "verdicts"] {
        for item in v
            .get(key)
            .and_then(serde_json::Value::as_array)
            .into_iter()
            .flatten()
        {
            let Some(id) = item.get("id").and_then(serde_json::Value::as_str) else {
                continue;
            };
            let value = item
                .get("pass")
                .and_then(serde_json::Value::as_bool)
                .map(|b| b.to_string())
                .or_else(|| {
                    item.get("status")
                        .and_then(serde_json::Value::as_str)
                        .map(str::to_string)
                });
            if let Some(value) = value {
                out.insert(format!("{key}:{id}"), value);
            }
        }
    }
    out
}

/// Compares the verdict flags of the stored native `verification.json` with the recomputed one.
/// The stored file is only protected by a hash in the editable record, so its flags are checked
/// against the recomputation. Returns a description of the first difference, or the number of flags
/// compared; `None` when neither run has such a file.
fn native_verification_difference(
    dir: &Path,
    scratch: &Path,
    rules: Option<&VerdictRules>,
) -> Option<Result<usize, String>> {
    let read = |p: &Path| -> Result<Option<serde_json::Value>, String> {
        if !p.is_file() {
            return Ok(None);
        }
        read_bounded(p, MAX_RECORD_BYTES)
            .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()))
            .map(Some)
    };
    let (stored, fresh) = match (
        read(&dir.join("verification.json")),
        read(&scratch.join("verification.json")),
    ) {
        (Ok(None), Ok(None)) => return None,
        (Ok(Some(s)), Ok(Some(f))) => (native_verdicts(&s), native_verdicts(&f)),
        (Err(e), _) | (_, Err(e)) => return Some(Err(format!("verification.json: {e}"))),
        _ => {
            return Some(Err(
                "verification.json exists in only one of the two runs".into()
            ));
        }
    };
    // A flag the declared verdict rules changed: a requirement status in the table, and the overall
    // requirements flag going from true to false when the table changes any requirement.
    let declared = |k: &str, v: &str, f: &str| {
        rules.is_some_and(|r| {
            r.requirements
                .iter()
                .any(|c| k == format!("verdicts:{}", c.id) && c.from == v && c.to == f)
                || (k == "requirements_pass"
                    && v == "true"
                    && f == "false"
                    && !r.requirements.is_empty())
        })
    };
    for (k, v) in &stored {
        match fresh.get(k) {
            Some(f) if f == v || declared(k, v, f) => {}
            other => {
                return Some(Err(format!(
                    "native verification {k}: stored {v}, recomputed {}",
                    other.map_or("absent", String::as_str)
                )));
            }
        }
    }
    // A verdict the recomputation finds failing must be in the stored file too.
    for (k, f) in &fresh {
        if !stored.contains_key(k) && (f == "false" || f == "fail") {
            return Some(Err(format!(
                "native verification {k} ({f}) is missing from the stored file"
            )));
        }
    }
    Some(Ok(stored.len()))
}

/// Replays a stored run that an earlier build of this host produced.
///
/// The strict [`replay`] requires the stored request to equal its own normal form and every
/// recomputed file to equal the stored one byte for byte. Neither can hold across builds: a newer
/// build adds parameters with defaults, and writes other texts, metrics and record fields, so an
/// honest older run would be reported as tampered. This replay instead verifies, and says what it
/// verified:
///
/// * the stored files still match the hashes written with them (the same integrity check);
/// * the stored request is valid and only needs catalogue defaults added (reported with the
///   domain version that recorded it);
/// * the current build recomputes the completed request, and the recomputed run agrees with the
///   stored record on outcome, safety, requirement verdicts, telemetry, events and metrics.
///
/// It does not run the native simulator replay, which needs the same simulator sources, and it does
/// not compare what [`EARLIER_BUILD_NOT_COMPARED`] lists, which the report repeats. A changed
/// number in the telemetry or the metrics, a flipped or deleted verdict, a deleted violation, a
/// changed outcome, an edited stored file or an edited native verdict flag is still rejected.
/// The gate is advisory: the platform uses this replay when the host build that stored the run is
/// not the one that is running, and only after the strict [`replay`] has rejected the run; the
/// build comparison reads an unauthenticated `meta.json`, so protection against edited files comes
/// from the recomputation, not from the gate.
pub fn replay_earlier_build<H: DomainHost>(host: &H, dir: &Path) -> ReplayReport {
    let mut checks = Vec::new();
    let parsed: Result<RunRecord, String> = read_bounded(&dir.join(RECORD_FILE), MAX_RECORD_BYTES)
        .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()));
    let mut valid_seed = None;
    match parsed {
        Err(e) => checks.push(check("record.json is a valid run record", false, e)),
        Ok(record) => {
            checks.push(check("record.json is a valid run record", true, ""));
            let name = "stored request is valid and canonical";
            match validate_request(host, &record.request) {
                Err(e) => checks.push(check(
                    name,
                    false,
                    format!(
                        "recorded by domain version {}; the current catalogue refuses the stored request: {e}",
                        record.domain.version
                    ),
                )),
                Ok(normal) => match completes(&record.request, &normal) {
                    Err(e) => checks.push(check(name, false, e)),
                    Ok(added) => {
                        let completed = if added.is_empty() {
                            "no parameter added".to_string()
                        } else {
                            format!("parameters added: {}", added.join(", "))
                        };
                        checks.push(check(
                            name,
                            true,
                            format!(
                                "recorded by domain version {}; re-simulated with current defaults ({completed})",
                                record.domain.version
                            ),
                        ));
                        valid_seed = Some(normal.seed);
                        earlier_build_files(host, dir, &record, &normal, &mut checks);
                    }
                },
            }
        }
    }
    if let Some(seed) = valid_seed {
        checks.extend(native_seed_check(host, dir, seed));
    }
    let ok = !checks.is_empty() && checks.iter().all(|c| c.pass);
    ReplayReport {
        schema: REPLAY_SCHEMA.into(),
        status: if ok { "verified" } else { "rejected" }.into(),
        checks,
    }
}

fn earlier_build_files<H: DomainHost>(
    host: &H,
    dir: &Path,
    record: &RunRecord,
    normal: &RunRequest,
    checks: &mut Vec<ReplayCheck>,
) {
    let name = "stored artifacts match the hashes in record.json";
    match hash_artifacts(dir) {
        Ok(on_disk) if on_disk == record.provenance.artifacts => {
            checks.push(check(name, true, format!("{} files", on_disk.len())))
        }
        Ok(_) => checks.push(check(name, false, "a file was added, removed or changed")),
        Err(e) => checks.push(check(name, false, e)),
    }
    let scratch = scratch_dir();
    let rerun = fs::create_dir_all(&scratch)
        .map_err(|e| e.to_string())
        .and_then(|_| {
            execute(host, normal, &scratch).map_err(|e| match e {
                HostError::Invalid(m) | HostError::Simulation(m) => m,
            })
        });
    match rerun {
        Err(e) => checks.push(check("the run is recomputed from its request", false, e)),
        Ok(_) => {
            checks.push(check("the run is recomputed from its request", true, ""));
            // Both records are read from their files, so both numbers went through the same
            // printing and parsing; the in-memory record of the run would differ in the last bit.
            let fresh: Result<RunRecord, String> =
                read_bounded(&scratch.join(RECORD_FILE), MAX_RECORD_BYTES)
                    .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()));
            let rules = host.verdict_rules();
            let comparison = match &fresh {
                Ok(fresh) => compare(record, fresh, &rules),
                Err(e) => Comparison {
                    difference: Some(format!("the recomputed record cannot be read: {e}")),
                    re_evaluated: Vec::new(),
                },
            };
            let difference = comparison.difference;
            let applied = fresh.as_ref().is_ok_and(|f| rules.applies(record, f));
            let detail = match &difference {
                None => format!(
                    "{} channels, {} requirements, {} events, {} metrics agree; texts, the scene and the native files are not compared",
                    record.channels.len(),
                    record.requirements.len(),
                    record.events.len(),
                    record.metrics.len()
                ),
                Some(d) => format!(
                    "{d}; the current simulator does not reproduce what version {} recorded",
                    record.domain.version
                ),
            };
            checks.push(check(
                EARLIER_BUILD_AGREEMENT_CHECK,
                difference.is_none(),
                detail,
            ));
            // The stored native verdict flags against the recomputation (the hash that protects the
            // file lives in the record, which can be edited together with the file).
            match native_verification_difference(dir, &scratch, applied.then_some(&rules)) {
                None => {}
                Some(Ok(n)) => checks.push(check(
                    "native verification.json flags agree with the recomputation",
                    true,
                    format!("{n} verdict flags"),
                )),
                Some(Err(e)) => checks.push(check(
                    "native verification.json flags agree with the recomputation",
                    false,
                    e,
                )),
            }
            if !comparison.re_evaluated.is_empty() {
                checks.push(check(
                    VERDICT_REEVALUATION_CHECK,
                    true,
                    format!(
                        "recorded by domain version {}, before the rules of {}: {}. {}",
                        record.domain.version,
                        rules.since,
                        comparison.re_evaluated.join("; "),
                        rules.summary
                    ),
                ));
            }
            checks.push(check(
                "not compared by the earlier-build replay",
                true,
                EARLIER_BUILD_NOT_COMPARED,
            ));
        }
    }
    let _ = fs::remove_dir_all(&scratch);
}

fn replay_files<H: DomainHost>(
    host: &H,
    dir: &Path,
    record: &RunRecord,
    request: &RunRequest,
    checks: &mut Vec<ReplayCheck>,
) {
    let name = "stored artifacts match the hashes in record.json";
    match hash_artifacts(dir) {
        Ok(on_disk) if on_disk == record.provenance.artifacts => {
            checks.push(check(name, true, format!("{} files", on_disk.len())))
        }
        Ok(_) => checks.push(check(name, false, "a file was added, removed or changed")),
        Err(e) => checks.push(check(name, false, e)),
    }
    let scratch = scratch_dir();
    let rerun = fs::create_dir_all(&scratch)
        .map_err(|e| e.to_string())
        .and_then(|_| {
            execute(host, request, &scratch).map_err(|e| match e {
                HostError::Invalid(m) | HostError::Simulation(m) => m,
            })
        });
    match rerun {
        Err(e) => checks.push(check("the run is recomputed from its request", false, e)),
        Ok(_) => {
            checks.push(check("the run is recomputed from its request", true, ""));
            let stored = hash_artifacts(dir).unwrap_or_default();
            let fresh = hash_artifacts(&scratch).unwrap_or_default();
            let same = stored == fresh;
            checks.push(check(
                "recomputed artifacts equal the stored artifacts byte for byte",
                same,
                if same {
                    format!("{} files", fresh.len())
                } else {
                    differing(&stored, &fresh)
                },
            ));
            let a = fs::read(dir.join(RECORD_FILE)).unwrap_or_default();
            let b = fs::read(scratch.join(RECORD_FILE)).unwrap_or_default();
            checks.push(check(
                "recomputed record (outcome, requirements, telemetry) equals the stored record",
                !a.is_empty() && a == b,
                "",
            ));
        }
    }
    let _ = fs::remove_dir_all(&scratch);
}

fn differing(a: &[FileHash], b: &[FileHash]) -> String {
    let mut names: Vec<&str> = a.iter().chain(b).map(|f| f.path.as_str()).collect();
    names.sort();
    names.dedup();
    let diff: Vec<&str> = names
        .into_iter()
        .filter(|n| a.iter().find(|f| f.path == *n) != b.iter().find(|f| f.path == *n))
        .collect();
    format!("differs: {}", diff.join(", "))
}

fn print_json<T: serde::Serialize>(value: &T) {
    println!(
        "{}",
        String::from_utf8_lossy(&pretty_bytes(value)).trim_end()
    );
}

fn fail(code: i32, message: &str) -> ExitCode {
    eprintln!("{message}");
    ExitCode::from(code as u8)
}

fn parse_and_validate<H: DomainHost>(host: &H, file: &str) -> Result<RunRequest, String> {
    parse_request(Path::new(file)).and_then(|r| validate_request(host, &r))
}

pub fn host_main<H: DomainHost>(host: &H) -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    match args.as_slice() {
        ["manifest"] => print_json(&host.manifest()),
        ["describe"] => print_json(&host.catalog()),
        ["validate", file] => match parse_and_validate(host, file) {
            Ok(normal) => print_json(&normal),
            Err(e) => return fail(EXIT_INVALID_REQUEST, &e),
        },
        ["run", file, "--output", out] => {
            let request = match parse_and_validate(host, file) {
                Ok(r) => r,
                Err(e) => return fail(EXIT_INVALID_REQUEST, &e),
            };
            let out = Path::new(out);
            let empty = fs::create_dir_all(out).is_ok()
                && fs::read_dir(out)
                    .map(|mut d| d.next().is_none())
                    .unwrap_or(false);
            if !empty {
                return fail(
                    EXIT_INVALID_REQUEST,
                    "the output directory must be new or empty",
                );
            }
            match execute(host, &request, out) {
                Ok(record) => print_json(&serde_json::json!({
                    "status": "ok",
                    "outcome": record.outcome.code,
                    "safety": record.safety.status,
                })),
                Err(HostError::Invalid(e)) => return fail(EXIT_INVALID_REQUEST, &e),
                Err(HostError::Simulation(e)) => return fail(EXIT_SIMULATION_ERROR, &e),
            }
        }
        ["replay", dir, flag] if *flag == EARLIER_BUILD_FLAG => {
            let report = replay_earlier_build(host, Path::new(dir));
            print_json(&report);
            if report.status != "verified" {
                return ExitCode::from(EXIT_REPLAY_REJECTED as u8);
            }
        }
        ["replay", dir] => {
            let report = replay(host, Path::new(dir));
            print_json(&report);
            if report.status != "verified" {
                return ExitCode::from(EXIT_REPLAY_REJECTED as u8);
            }
        }
        _ => {
            return fail(
                EXIT_INVALID_REQUEST,
                "usage: manifest | describe | validate <request.json> | run <request.json> --output <dir> | replay <dir> [--earlier-build]",
            );
        }
    }
    ExitCode::SUCCESS
}

#[cfg(test)]
mod disagreement_tests {
    use super::*;

    fn record() -> RunRecord {
        let mut r: RunRecord = serde_json::from_str(include_str!(
            "../../studio/tests/fixtures/rocket-record-trimmed.json"
        ))
        .unwrap();
        let q = |id: &str, status: &str| RequirementResult {
            id: id.into(),
            label: id.into(),
            category: "requirement".into(),
            status: status.into(),
            expected: String::new(),
            observed: String::new(),
            t: Some(1.0),
            explanation: String::new(),
        };
        r.requirements = vec![q("R1", "pass")];
        r.events = vec![Event {
            t: 1.0,
            kind: "known_violation".into(),
            label: String::new(),
            severity: "violation".into(),
            source: "verifier".into(),
            detail: serde_json::Value::Null,
        }];
        r
    }

    fn requirement(id: &str, status: &str) -> RequirementResult {
        let mut q = record().requirements.remove(0);
        q.id = id.into();
        q.status = status.into();
        q
    }

    fn event(kind: &str, t: f64) -> Event {
        let mut e = record().events.remove(0);
        e.kind = kind.into();
        e.t = t;
        e
    }

    #[test]
    fn a_requirement_that_is_not_evaluated_counts_as_missing_like_a_failed_one() {
        let stored = record();
        let mut fresh = record();
        fresh.domain.version = "later".into();
        // A new passing requirement of another version is fine.
        fresh.requirements.push(requirement("R2", "pass"));
        assert_eq!(disagreement(&stored, &fresh), None);
        // A new one that is failed or not evaluated is not.
        for status in ["fail", "not_evaluated"] {
            fresh.requirements[1] = requirement("R2", status);
            let d = disagreement(&stored, &fresh).unwrap();
            assert!(
                d.contains("R2") && d.contains("missing from the stored record"),
                "{d}"
            );
        }
        // With the same domain version even a passing one is a disagreement.
        let mut same = record();
        same.requirements.push(requirement("R2", "pass"));
        assert!(disagreement(&stored, &same).is_some());
    }

    #[test]
    fn a_new_event_kind_of_another_version_does_not_reject_but_a_known_kind_does() {
        let stored = record();
        let mut fresh = record();
        fresh.domain.version = "later".into();
        // A violation of a kind the stored record has nowhere: a later build introduced it.
        fresh.events.push(event("new_kind_violation", 2.0));
        assert_eq!(disagreement(&stored, &fresh), None);
        // The same kind the stored record knows, at an instant it lacks: a disagreement.
        fresh.events[1] = event("known_violation", 2.0);
        let d = disagreement(&stored, &fresh).unwrap();
        assert!(
            d.contains("known_violation") && d.contains("missing from the stored record"),
            "{d}"
        );
        // With the same domain version, a new kind is a disagreement too.
        let mut same = record();
        same.events.push(event("new_kind_violation", 2.0));
        assert!(disagreement(&stored, &same).is_some());
        // A second violation of the known kind deleted from the stored record is caught.
        let mut two = record();
        two.events.push(event("known_violation", 2.0));
        let mut deleted = two.clone();
        deleted.events.pop();
        two.domain.version = "later".into();
        let d = disagreement(&deleted, &two).unwrap();
        assert!(d.contains("known_violation"), "{d}");
    }
}

#[cfg(test)]
mod verdict_rule_tests {
    use super::*;

    const RULES: VerdictRules = VerdictRules {
        since: "1.1.0",
        outcomes: &[OutcomeChange {
            from: ("orbit", "success"),
            to: ("orbit", "partial"),
        }],
        requirements: &[RequirementChange {
            id: "R1",
            from: "pass",
            to: "fail",
            reason: "stricter minimum",
        }],
        retimed: &["R8"],
        derived_metrics: &["limit.R1"],
        summary: "rules of 1.1.0",
    };

    fn record() -> RunRecord {
        let mut r: RunRecord = serde_json::from_str(include_str!(
            "../../studio/tests/fixtures/rocket-record-trimmed.json"
        ))
        .unwrap();
        r.domain.version = "1.0.0".into();
        r.outcome.code = "orbit".into();
        r.outcome.status = "success".into();
        let q = |id: &str, status: &str, t: Option<f64>| RequirementResult {
            id: id.into(),
            label: id.into(),
            category: "requirement".into(),
            status: status.into(),
            expected: String::new(),
            observed: String::new(),
            t,
            explanation: String::new(),
        };
        r.requirements = vec![q("R1", "pass", Some(1.0)), q("R8", "fail", None)];
        r.events = vec![Event {
            t: 0.0,
            kind: "violation".into(),
            label: String::new(),
            severity: "violation".into(),
            source: "verifier".into(),
            detail: serde_json::json!({ "id": "R8" }),
        }];
        r.metrics.push(Metric {
            id: "other.M".into(),
            label: String::new(),
            value: Some(1.0),
            unit: String::new(),
            group: String::new(),
        });
        r.metrics.push(Metric {
            id: "limit.R1".into(),
            label: String::new(),
            value: Some(0.0),
            unit: String::new(),
            group: String::new(),
        });
        r
    }

    /// The same run judged by the new rules.
    fn judged_again(stored: &RunRecord) -> RunRecord {
        let mut f = stored.clone();
        f.domain.version = "1.1.0".into();
        f.outcome.status = "partial".into();
        f.requirements[0].status = "fail".into();
        f.requirements[1].t = Some(500.0);
        f.events = vec![
            Event {
                t: 500.0,
                kind: "violation".into(),
                label: String::new(),
                severity: "violation".into(),
                source: "verifier".into(),
                detail: serde_json::json!({ "id": "R8" }),
            },
            Event {
                t: 1.0,
                kind: "violation".into(),
                label: String::new(),
                severity: "violation".into(),
                source: "verifier".into(),
                detail: serde_json::json!({ "id": "R1" }),
            },
        ];
        f.metrics.last_mut().unwrap().value = Some(5.0);
        f
    }

    #[test]
    fn declared_rule_changes_are_accepted_and_listed() {
        let stored = record();
        let fresh = judged_again(&stored);
        assert!(
            disagreement(&stored, &fresh).is_some(),
            "strict comparison rejects"
        );
        let c = compare(&stored, &fresh, &RULES);
        assert_eq!(c.difference, None);
        let text = c.re_evaluated.join(" | ");
        for part in [
            "orbit (success) is now orbit (partial)",
            "R1 pass is now fail: stricter minimum",
            "R8 is judged at another instant",
        ] {
            assert!(text.contains(part), "{part} in {text}");
        }
    }

    #[test]
    fn anything_outside_the_table_or_for_a_current_run_still_rejects() {
        let stored = record();
        let rejects = |fresh: &RunRecord, stored: &RunRecord| {
            compare(stored, fresh, &RULES).difference.is_some()
        };
        // A different outcome than the table declares.
        let mut f = judged_again(&stored);
        f.outcome.status = "failure".into();
        assert!(rejects(&f, &stored));
        // A requirement flipped the other way, or one the table does not name.
        let mut f = judged_again(&stored);
        f.requirements[1].status = "pass".into();
        assert!(rejects(&f, &stored));
        let mut s = record();
        s.requirements[0].status = "fail".into();
        let mut f = judged_again(&s);
        f.requirements[0].status = "pass".into();
        assert!(rejects(&f, &s));
        // Telemetry is never covered: a timebase, a channel, another metric.
        let mut f = judged_again(&stored);
        let key = f.timebases.keys().next().unwrap().clone();
        f.timebases.get_mut(&key).unwrap()[0] += 1.0;
        assert!(rejects(&f, &stored));
        let mut f = judged_again(&stored);
        f.metrics
            .iter_mut()
            .find(|m| m.id == "other.M")
            .unwrap()
            .value = Some(2.0);
        assert!(rejects(&f, &stored));
        // The table is for runs of older versions only: the same version, or one at or after `since`.
        let mut s = record();
        s.domain.version = "1.1.0".into();
        let f = judged_again(&s);
        assert!(rejects(&f, &s));
        // A violation the table does not name, appearing in the recomputation of a known kind.
        let mut f = judged_again(&stored);
        f.events.push(Event {
            t: 7.0,
            kind: "violation".into(),
            label: String::new(),
            severity: "violation".into(),
            source: "verifier".into(),
            detail: serde_json::json!({ "id": "R9" }),
        });
        assert!(rejects(&f, &stored));
    }

    #[test]
    fn versions_compare_as_numbers_and_unparsable_ones_never_apply() {
        assert!(version_less("0.15.0", "0.15.1"));
        assert!(version_less("0.9.0", "0.15.1"));
        assert!(!version_less("0.15.1", "0.15.1"));
        assert!(!version_less("later", "0.15.1"));
        assert!(!version_less("0.15.0", ""));
    }
}
