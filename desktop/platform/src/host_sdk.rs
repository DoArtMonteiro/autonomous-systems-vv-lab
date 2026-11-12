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

/// A fact about a metric of the recomputed record that an outcome change rests on.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MetricFact {
    /// The metric has a value.
    Present,
    /// The metric has no value (or is absent).
    Absent,
    /// The metric has a value of at least this.
    AtLeast(f64),
}

/// What an outcome change must be tied to, besides the stored and the new (code, status) pair.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum OutcomeBasis {
    /// The recomputed record fails a requirement outside the invariants (that is what a partial
    /// outcome says); the requirement comparison ties each of those to the stored record.
    RequirementFailed,
    /// Stored requirement statuses (id, status) and facts of the recomputed metrics, all of which
    /// must hold.
    Facts {
        stored: &'static [(&'static str, &'static str)],
        fresh: &'static [(&'static str, MetricFact)],
    },
}

/// A change of an outcome as the domain declares it: the pair (code, status) that a run stored by an
/// earlier version carries, the pair the current rules give to the same run, and what the change
/// rests on.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct OutcomeChange {
    pub from: (&'static str, &'static str),
    pub to: (&'static str, &'static str),
    pub basis: OutcomeBasis,
}

/// A requirement whose status the new rules can change on a run stored by an earlier version, and the
/// metrics derived from its limit.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RequirementChange {
    pub id: &'static str,
    pub from: &'static str,
    pub to: &'static str,
    pub reason: &'static str,
    /// Metrics of the observed value, the limit and the margin of the requirement. The limit and the
    /// margin may differ from the stored ones when the stored record has the old limit and a margin
    /// consistent with it.
    pub observed_metric: &'static str,
    pub limit_metric: &'static str,
    pub margin_metric: &'static str,
    /// The limit of the old rule.
    pub old_limit: f64,
}

/// Changes to the verdict rules of a domain, applied by [`replay_earlier_build`] only to a run
/// recorded by a domain version older than `since`. Only verdicts and what is derived from them are
/// covered, and each change only where the same comparison shows the fact it rests on; timebases,
/// channels, other metrics and the events that are not verdict violations must still match, and
/// anything outside the table still rejects.
#[derive(Clone, Copy, Debug)]
pub struct VerdictRules {
    /// Domain version that introduced the rules; empty for none.
    pub since: &'static str,
    pub outcomes: &'static [OutcomeChange],
    pub requirements: &'static [RequirementChange],
    /// Requirements judged at another instant by the new rules: a stored requirement without an
    /// instant is judged at the end of the run, and its violation event moves from 0 to that instant.
    pub retimed: &'static [&'static str],
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

/// The result of comparing a stored record with its recomputation: the first disagreement, the
/// verdict re-evaluations that the declared rules accepted, and the requirement changes among them.
struct Comparison {
    difference: Option<String>,
    re_evaluated: Vec<String>,
    applied: Vec<RequirementChange>,
}

/// The `id` of the requirement a violation event reports, if it is one.
fn violation_id(e: &Event) -> Option<&str> {
    (e.kind == "violation")
        .then(|| e.detail.get("id").and_then(serde_json::Value::as_str))
        .flatten()
}

/// The end of the run in the recomputed record: the last instant of its mission clock, else of any
/// timebase.
fn run_end(r: &RunRecord) -> f64 {
    r.timebases
        .get("mission")
        .and_then(|t| t.last().copied())
        .or_else(|| {
            r.timebases
                .values()
                .filter_map(|t| t.last().copied())
                .reduce(f64::max)
        })
        .unwrap_or(0.0)
}

fn metric_value(r: &RunRecord, id: &str) -> Option<f64> {
    r.metrics.iter().find(|m| m.id == id).and_then(|m| m.value)
}

/// Whether the stored record carries the old rule's numbers for a requirement: the old limit and a
/// margin consistent with it.
fn has_old_limit(stored: &RunRecord, c: &RequirementChange) -> bool {
    let close = |a: f64, b: f64| (a - b).abs() <= 1e-9 * (1.0 + a.abs().max(b.abs()));
    match (
        metric_value(stored, c.limit_metric),
        metric_value(stored, c.margin_metric),
        metric_value(stored, c.observed_metric),
    ) {
        (Some(limit), Some(margin), Some(observed)) => {
            close(limit, c.old_limit) && close(margin, observed - c.old_limit)
        }
        _ => false,
    }
}

/// Whether the facts an outcome change rests on hold in this comparison.
fn basis_holds(basis: OutcomeBasis, stored: &RunRecord, fresh: &RunRecord) -> bool {
    match basis {
        OutcomeBasis::RequirementFailed => fresh
            .requirements
            .iter()
            .any(|q| q.category == "requirement" && q.status != "pass"),
        OutcomeBasis::Facts {
            stored: needs,
            fresh: facts,
        } => {
            needs.iter().all(|(id, status)| {
                stored
                    .requirements
                    .iter()
                    .any(|q| q.id == *id && q.status == *status)
            }) && facts
                .iter()
                .all(|(id, fact)| match (fact, metric_value(fresh, id)) {
                    (MetricFact::Present, Some(_)) | (MetricFact::Absent, None) => true,
                    (MetricFact::AtLeast(min), Some(v)) => v >= *min,
                    _ => false,
                })
        }
    }
}

/// [`disagreement`] with the verdict-rule changes a domain declared for runs of older versions (see
/// [`VerdictRules`]). With no rules this is the strict comparison. Each declared change is accepted
/// only where this comparison shows what it rests on: a requirement status only for the declared pair
/// of statuses, a retimed requirement only when the stored one had no instant and the recomputed one
/// is judged at the end of the run, an outcome only with its basis, the limit metrics only when the
/// stored record has the old limit, and the violation events only for a change accepted here.
fn compare(stored: &RunRecord, fresh: &RunRecord, rules: &VerdictRules) -> Comparison {
    let mut re_evaluated = Vec::new();
    let applies = rules.applies(stored, fresh);
    let end = run_end(fresh);
    // The changes the table accepts on this pair of records.
    let mut applied: Vec<RequirementChange> = Vec::new();
    let mut retimed_ids: Vec<&str> = Vec::new();
    if applies {
        for q in &stored.requirements {
            let Some(x) = fresh.requirements.iter().find(|x| x.id == q.id) else {
                continue;
            };
            if x.status != q.status
                && let Some(c) = rules
                    .requirements
                    .iter()
                    .find(|c| c.id == q.id && c.from == q.status && c.to == x.status)
            {
                applied.push(*c);
            }
            if x.t != q.t
                && q.t.is_none()
                && rules.retimed.contains(&q.id.as_str())
                && x.t.is_some_and(|t| t <= end && t >= end - 1.0)
            {
                retimed_ids.push(q.id.as_str());
            }
        }
    }
    let differ = |d: String, re: Vec<String>, applied: Vec<RequirementChange>| Comparison {
        difference: Some(d),
        re_evaluated: re,
        applied,
    };
    if stored.outcome.code != fresh.outcome.code || stored.outcome.status != fresh.outcome.status {
        let declared = applies
            && rules.outcomes.iter().any(|c| {
                c.from == (stored.outcome.code.as_str(), stored.outcome.status.as_str())
                    && c.to == (fresh.outcome.code.as_str(), fresh.outcome.status.as_str())
                    && basis_holds(c.basis, stored, fresh)
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
                applied,
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
            applied,
        );
    }
    for q in &stored.requirements {
        let Some(x) = fresh.requirements.iter().find(|x| x.id == q.id) else {
            return differ(
                format!("requirement {} is no longer evaluated", q.id),
                re_evaluated,
                applied,
            );
        };
        let change = applied
            .iter()
            .find(|c| c.id == q.id && c.from == q.status && c.to == x.status);
        if let Some(c) = change {
            re_evaluated.push(format!(
                "{} {} is now {}: {}",
                q.id, q.status, x.status, c.reason
            ));
        }
        let retimed = x.t != q.t && retimed_ids.contains(&q.id.as_str());
        if (x.status != q.status && change.is_none())
            || (x.t != q.t && !retimed)
            || x.category != q.category
        {
            return differ(
                format!(
                    "requirement {}: {} at {:?} became {} at {:?}",
                    q.id, q.status, q.t, x.status, x.t
                ),
                re_evaluated,
                applied,
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
                applied,
            );
        }
    }
    for (id, values) in &stored.timebases {
        if fresh.timebases.get(id) != Some(values) {
            return differ(format!("timebase {id} differs"), re_evaluated, applied);
        }
    }
    for c in &stored.channels {
        match fresh.channels.iter().find(|x| x.id == c.id) {
            Some(x) if x.timebase == c.timebase && x.values == c.values => {}
            Some(_) => {
                return differ(format!("channel {} differs", c.id), re_evaluated, applied);
            }
            None => {
                return differ(
                    format!("channel {} is no longer recorded", c.id),
                    re_evaluated,
                    applied,
                );
            }
        }
    }
    // Violation events of a verdict whose instant or status the declared rules changed here: the
    // retimed one at 0 in the stored record and at the end of the run in the recomputation, and a new
    // violation of a requirement whose status changed to fail. No other violation is skipped, so a
    // deleted or forged one is a disagreement.
    let near_end = |e: &Event| e.t <= end && e.t >= end - 1.0;
    let moved_from_start = |id: &str| {
        stored
            .events
            .iter()
            .any(|e| violation_id(e) == Some(id) && e.t == 0.0)
    };
    let moved_to_end = |id: &str| {
        fresh
            .events
            .iter()
            .any(|e| violation_id(e) == Some(id) && near_end(e))
    };
    let stored_retimed = |e: &Event| {
        violation_id(e)
            .is_some_and(|id| retimed_ids.contains(&id) && e.t == 0.0 && moved_to_end(id))
    };
    let fresh_covered = |e: &Event| {
        violation_id(e).is_some_and(|id| {
            (retimed_ids.contains(&id) && near_end(e) && moved_from_start(id))
                || applied.iter().any(|c| c.id == id && c.to == "fail")
        })
    };
    for e in &stored.events {
        if stored_retimed(e) {
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
                applied,
            );
        }
    }
    // Likewise a violation or warning the recomputation reports must be in the stored record. The
    // one exception: for another domain version, an event kind that appears nowhere in the stored
    // record may be a kind a later build introduced, and does not alone reject. A missing event of
    // a kind the stored record knows is always a disagreement, and so is any missing event when the
    // domain version is the same.
    for x in &fresh.events {
        if !matches!(x.severity.as_str(), "violation" | "warning") || fresh_covered(x) {
            continue;
        }
        // A violation of a requirement the table names is never taken as a new kind: it is covered above or it is missing.
        let named = violation_id(x).is_some_and(|id| {
            rules.retimed.contains(&id) || rules.requirements.iter().any(|c| c.id == id)
        });
        if !same_version && !named && !stored.events.iter().any(|e| e.kind == x.kind) {
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
                applied,
            );
        }
    }
    // The limit and the margin of a requirement whose limit rule changed, when the stored record
    // has the old limit and a margin consistent with it.
    let derived = |id: &str| {
        applies
            && rules.requirements.iter().any(|c| {
                (c.limit_metric == id || c.margin_metric == id) && has_old_limit(stored, c)
            })
    };
    for m in &stored.metrics {
        match fresh.metrics.iter().find(|x| x.id == m.id) {
            Some(x) if x.value == m.value => {}
            Some(_) if derived(&m.id) => {}
            Some(_) => {
                return differ(format!("metric {} differs", m.id), re_evaluated, applied);
            }
            None => {
                return differ(
                    format!("metric {} is no longer recorded", m.id),
                    re_evaluated,
                    applied,
                );
            }
        }
    }
    Comparison {
        difference: None,
        re_evaluated,
        applied,
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
    applied: Option<&[RequirementChange]>,
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
    // A flag the declared verdict rules changed in this comparison: the status of a requirement whose
    // change was applied, and the overall requirements flag going from true to false when one was.
    let declared = |k: &str, v: &str, f: &str| {
        applied.is_some_and(|a| {
            a.iter()
                .any(|c| k == format!("verdicts:{}", c.id) && c.from == v && c.to == f)
                || (k == "requirements_pass" && v == "true" && f == "false" && !a.is_empty())
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
                    applied: Vec::new(),
                },
            };
            let difference = comparison.difference;
            let applied = fresh.as_ref().is_ok_and(|f| rules.applies(record, f));
            let applied_changes = comparison.applied.clone();
            let detail = match &difference {
                None if !comparison.re_evaluated.is_empty() => format!(
                    "the timebases, {} channels, the other metrics and the events agree, but the stored verdicts were re-evaluated under the current rules and differ from the recomputed ones (see \"{VERDICT_REEVALUATION_CHECK}\"); texts, the scene and the native files are not compared",
                    record.channels.len()
                ),
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
            match native_verification_difference(
                dir,
                &scratch,
                applied.then_some(applied_changes.as_slice()),
            ) {
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
        outcomes: &[
            OutcomeChange {
                from: ("orbit", "success"),
                to: ("orbit", "partial"),
                basis: OutcomeBasis::RequirementFailed,
            },
            OutcomeChange {
                from: ("suborbital", "failure"),
                to: ("low", "failure"),
                basis: OutcomeBasis::Facts {
                    stored: &[("R4", "fail")],
                    fresh: &[("peri", MetricFact::AtLeast(0.0))],
                },
            },
        ],
        requirements: &[RequirementChange {
            id: "R1",
            from: "pass",
            to: "fail",
            reason: "stricter minimum",
            observed_metric: "obs.R1",
            limit_metric: "limit.R1",
            margin_metric: "margin.R1",
            old_limit: 0.0,
        }],
        retimed: &["R8"],
        summary: "rules of 1.1.0",
    };

    fn ev(t: f64, id: &str) -> Event {
        Event {
            t,
            kind: "violation".into(),
            label: String::new(),
            severity: "violation".into(),
            source: "verifier".into(),
            detail: serde_json::json!({ "id": id }),
        }
    }

    fn met(id: &str, value: Option<f64>) -> Metric {
        Metric {
            id: id.into(),
            label: String::new(),
            value,
            unit: String::new(),
            group: String::new(),
        }
    }

    fn req(id: &str, status: &str, t: Option<f64>) -> RequirementResult {
        RequirementResult {
            id: id.into(),
            label: id.into(),
            category: "requirement".into(),
            status: status.into(),
            expected: String::new(),
            observed: String::new(),
            t,
            explanation: String::new(),
        }
    }

    /// A run stored by version 1.0.0: orbit/success with R1 passing at the old limit 0, and R8
    /// failing without an instant, its violation event at 0.
    fn record() -> RunRecord {
        let mut r: RunRecord = serde_json::from_str(include_str!(
            "../../studio/tests/fixtures/rocket-record-trimmed.json"
        ))
        .unwrap();
        r.domain.version = "1.0.0".into();
        r.outcome.code = "orbit".into();
        r.outcome.status = "success".into();
        r.requirements = vec![req("R1", "pass", Some(1.0)), req("R8", "fail", None)];
        r.events = vec![ev(0.0, "R8")];
        r.metrics = vec![
            met("other.M", Some(1.0)),
            met("obs.R1", Some(3.0)),
            met("limit.R1", Some(0.0)),
            met("margin.R1", Some(3.0)),
        ];
        r
    }

    /// The same run judged by the new rules.
    fn judged_again(stored: &RunRecord) -> RunRecord {
        let mut f = stored.clone();
        f.domain.version = "1.1.0".into();
        f.outcome.status = "partial".into();
        f.requirements[0].status = "fail".into();
        let end = run_end(&f);
        f.requirements[1].t = Some(end);
        f.events = vec![ev(end, "R8"), ev(1.0, "R1")];
        f.metrics[2].value = Some(5.0);
        f.metrics[3].value = Some(-2.0);
        f
    }

    fn rejects(stored: &RunRecord, fresh: &RunRecord) -> bool {
        compare(stored, fresh, &RULES).difference.is_some()
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
        assert_eq!(c.applied.len(), 1);
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
        // A different outcome than the table declares.
        let mut f = judged_again(&stored);
        f.outcome.status = "failure".into();
        assert!(rejects(&stored, &f));
        // A requirement flipped the other way, or one the table does not name.
        let mut f = judged_again(&stored);
        f.requirements[1].status = "pass".into();
        assert!(rejects(&stored, &f));
        let mut s = record();
        s.requirements[0].status = "fail".into();
        let mut f = judged_again(&s);
        f.requirements[0].status = "pass".into();
        assert!(rejects(&s, &f));
        // Telemetry is never covered: a timebase, another metric.
        let mut f = judged_again(&stored);
        let key = f.timebases.keys().next().unwrap().clone();
        f.timebases.get_mut(&key).unwrap()[0] += 1.0;
        assert!(rejects(&stored, &f));
        let mut f = judged_again(&stored);
        f.metrics[0].value = Some(2.0);
        assert!(rejects(&stored, &f));
        // The table is for runs of older versions only.
        let mut s = record();
        s.domain.version = "1.1.0".into();
        assert!(rejects(&s, &judged_again(&s)));
        // A violation the table does not name.
        let mut f = judged_again(&stored);
        f.events.push(ev(7.0, "R9"));
        assert!(rejects(&stored, &f));
    }

    #[test]
    fn a_forged_success_that_no_failed_requirement_explains_is_rejected() {
        // The stored run claims success; the recomputation says partial but fails nothing.
        let mut stored = record();
        stored.requirements = vec![req("R1", "pass", Some(1.0))];
        stored.events.clear();
        let mut fresh = stored.clone();
        fresh.domain.version = "1.1.0".into();
        fresh.outcome.status = "partial".into();
        assert!(rejects(&stored, &fresh));
        // With a requirement that fails in the recomputation (and in the stored record) it holds.
        stored.requirements[0].status = "fail".into();
        fresh.requirements[0].status = "fail".into();
        assert!(!rejects(&stored, &fresh));
    }

    #[test]
    fn the_suborbital_change_needs_its_facts() {
        let mut stored = record();
        stored.outcome.code = "suborbital".into();
        stored.outcome.status = "failure".into();
        stored.requirements = vec![req("R4", "fail", Some(1.0))];
        stored.events.clear();
        let mut fresh = stored.clone();
        fresh.domain.version = "1.1.0".into();
        fresh.outcome.code = "low".into();
        fresh.metrics.push(met("peri", Some(100.0)));
        assert!(!rejects(&stored, &fresh));
        // The periapsis the rule is about is below the surface, or absent: not this change.
        fresh.metrics.last_mut().unwrap().value = Some(-5.0);
        assert!(rejects(&stored, &fresh));
        fresh.metrics.last_mut().unwrap().value = None;
        assert!(rejects(&stored, &fresh));
        // Or the stored requirement is not the failed one the rule starts from.
        fresh.metrics.last_mut().unwrap().value = Some(100.0);
        stored.requirements[0].status = "pass".into();
        fresh.requirements[0].status = "pass".into();
        assert!(rejects(&stored, &fresh));
    }

    #[test]
    fn the_limit_metrics_differ_only_from_the_old_limit_and_forged_ones_are_rejected() {
        let stored = record();
        let fresh = judged_again(&stored);
        assert!(!rejects(&stored, &fresh));
        // A stored limit that is not the old rule's, or a margin inconsistent with it.
        let mut s = stored.clone();
        s.metrics[2].value = Some(4.0);
        assert!(rejects(&s, &fresh));
        let mut s = stored.clone();
        s.metrics[3].value = Some(2.5);
        assert!(rejects(&s, &fresh));
    }

    #[test]
    fn the_retimed_requirement_and_its_event_are_tied_to_the_end_of_the_run() {
        let stored = record();
        // Judged at another instant than the end of the run.
        let mut f = judged_again(&stored);
        f.requirements[1].t = Some(run_end(&f) + 100.0);
        assert!(rejects(&stored, &f));
        // A stored requirement that had an instant is not retimed.
        let mut s = record();
        s.requirements[1].t = Some(2.0);
        assert!(rejects(&s, &judged_again(&s)));
        // The event: deleted from the stored record, or at neither 0 nor the end.
        let mut s = record();
        s.events.clear();
        assert!(rejects(&s, &judged_again(&s)));
        let mut f = judged_again(&stored);
        f.events[0].t = 3.0;
        assert!(rejects(&stored, &f));
        let mut s = record();
        s.events[0].t = 9.0;
        assert!(rejects(&s, &judged_again(&s)));
        // The recomputed R1 violation must exist for the flip: nothing to hide a deleted one behind.
        let mut f = judged_again(&stored);
        f.events.retain(|e| violation_id(e) != Some("R8"));
        assert!(rejects(&stored, &f));
        // A failed R1 that was already failed in the stored record: its deleted event is caught.
        let mut s = record();
        s.requirements[0].status = "fail".into();
        s.events.push(ev(1.0, "R1"));
        let mut deleted = s.clone();
        deleted.events.retain(|e| violation_id(e) != Some("R1"));
        let f = judged_again(&deleted);
        assert!(rejects(&deleted, &f));
    }

    #[test]
    fn native_flags_change_only_with_a_requirement_change_applied_here() {
        let stored = record();
        let applied = compare(&stored, &judged_again(&stored), &RULES).applied;
        assert_eq!(applied.len(), 1);
        let dir = std::env::temp_dir().join(format!("vv-native-flags-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let (a, b) = (dir.join("stored"), dir.join("fresh"));
        fs::create_dir_all(&a).unwrap();
        fs::create_dir_all(&b).unwrap();
        let write = |d: &Path, pass: bool, r1: &str| {
            fs::write(
                d.join("verification.json"),
                serde_json::json!({ "requirements_pass": pass, "verdicts": [{ "id": "R1", "status": r1 }] })
                    .to_string(),
            )
            .unwrap();
        };
        write(&a, true, "pass");
        write(&b, false, "fail");
        let ok = native_verification_difference(&a, &b, Some(applied.as_slice()));
        assert!(matches!(ok, Some(Ok(_))), "{ok:?}");
        // Without an applied change nothing is accepted: not the overall flag, not the status.
        let none = native_verification_difference(&a, &b, Some(&[]));
        assert!(matches!(none, Some(Err(_))), "{none:?}");
        let strict = native_verification_difference(&a, &b, None);
        assert!(matches!(strict, Some(Err(_))));
        let _ = fs::remove_dir_all(&dir);
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
