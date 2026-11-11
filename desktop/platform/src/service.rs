//! The platform service used by the desktop shell (and by tests): discovery, catalogs, validated
//! runs and comparisons, library storage, replay and evidence export. Every request passes the seed
//! guard and the generic validation here before a host process starts; the host then validates it
//! again and may normalise further. Nothing in this module is specific to a domain.

use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;

use crate::canonical::{canonical_bytes, pretty_bytes, sha256_hex};
use crate::contract::*;
use crate::discovery::{Discovered, Rejected, discover};
use crate::evidence;
use crate::host::{HostOutput, call};
use crate::host_sdk::{
    EARLIER_BUILD_AGREEMENT_CHECK, EARLIER_BUILD_FLAG, MAX_RECORD_BYTES, hash_artifacts,
    read_bounded,
};
use crate::library::{Library, META_SCHEMA, RunMeta, now_utc, summary_of};
use crate::seeds::check_seed;
use crate::validate::normalise;

pub const MAX_COMPARE: usize = 8;
const MAX_PARALLEL: usize = 4;

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "kind", content = "message", rename_all = "snake_case")]
pub enum PlatformError {
    /// The request is malformed or outside what the domain declares.
    Invalid(String),
    /// The seed is protected; nothing was started.
    Protected(String),
    NotFound(String),
    /// The domain host failed, timed out or broke the contract.
    Host(String),
    Io(String),
}

impl std::fmt::Display for PlatformError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PlatformError::Invalid(m)
            | PlatformError::Protected(m)
            | PlatformError::NotFound(m)
            | PlatformError::Host(m)
            | PlatformError::Io(m) => f.write_str(m),
        }
    }
}

fn io(e: impl std::fmt::Display) -> PlatformError {
    PlatformError::Io(e.to_string())
}

pub struct DomainEntry {
    pub found: Discovered,
    pub catalog: Result<DomainCatalog, String>,
    pub host_sha256: String,
}

#[derive(Serialize, Clone)]
pub struct DomainInfo {
    pub manifest: DomainManifest,
    pub catalog: Option<DomainCatalog>,
    pub error: Option<String>,
}

#[derive(Serialize, Clone, Debug)]
pub struct RunOutcome {
    pub run_id: String,
    /// True when an identical run (same request, same host build) was already in the library.
    pub reused: bool,
    pub meta: RunMeta,
}

#[derive(Serialize, Clone, Debug)]
pub struct StartReport {
    pub domains: usize,
    pub rejected: Vec<Rejected>,
    /// Interrupted runs cleared from staging at start.
    pub recovered: usize,
}

pub struct Platform {
    domains: Vec<DomainEntry>,
    rejected: Vec<Rejected>,
    library: Library,
    version: String,
}

fn host_call(found: &Discovered, args: Vec<OsString>) -> Result<HostOutput, PlatformError> {
    call(
        &found.executable,
        &args,
        found.manifest.host.timeout_s,
        found.manifest.host.max_output_bytes,
    )
    .map_err(|e| PlatformError::Host(e.to_string()))
}

fn describe(found: &Discovered) -> Result<DomainCatalog, String> {
    let out = host_call(found, vec!["describe".into()]).map_err(|e| e.to_string())?;
    if out.code != EXIT_OK {
        return Err(format!("describe exited {}: {}", out.code, out.stderr));
    }
    let catalog: DomainCatalog =
        serde_json::from_slice(&out.stdout).map_err(|e| format!("invalid catalog: {e}"))?;
    if catalog.schema != CATALOG_SCHEMA {
        return Err(format!("catalog schema must be {CATALOG_SCHEMA}"));
    }
    if catalog.domain != found.manifest.id {
        return Err("catalog names a different domain than its manifest".into());
    }
    let mut ids = BTreeSet::new();
    if !catalog.scenarios.iter().all(|s| ids.insert(&s.id)) {
        return Err("catalog repeats a scenario id".into());
    }
    Ok(catalog)
}

impl Platform {
    /// Starts the platform and clears what an interrupted run left in the library staging area.
    pub fn start(
        domain_roots: &[PathBuf],
        library_root: &Path,
        version: &str,
    ) -> Result<(Platform, StartReport), String> {
        Self::start_with(domain_roots, library_root, version, true)
    }

    /// As [`Platform::start`]; `recover_staging` is false when another platform instance in this
    /// process may still be executing runs into the staging area (a restart).
    pub fn start_with(
        domain_roots: &[PathBuf],
        library_root: &Path,
        version: &str,
        recover_staging: bool,
    ) -> Result<(Platform, StartReport), String> {
        let library = Library::open(library_root)?;
        let recovered = if recover_staging {
            library.recover()
        } else {
            0
        };
        let report = discover(domain_roots);
        let domains: Vec<DomainEntry> = report
            .domains
            .into_iter()
            .map(|found| {
                let host_sha256 = fs::read(&found.executable)
                    .map(|b| sha256_hex(&b))
                    .unwrap_or_default();
                let catalog = describe(&found);
                DomainEntry {
                    found,
                    catalog,
                    host_sha256,
                }
            })
            .collect();
        let start = StartReport {
            domains: domains.len(),
            rejected: report.rejected.clone(),
            recovered,
        };
        Ok((
            Platform {
                domains,
                rejected: report.rejected,
                library,
                version: version.into(),
            },
            start,
        ))
    }

    pub fn library(&self) -> &Library {
        &self.library
    }

    pub fn version(&self) -> &str {
        &self.version
    }

    pub fn rejected(&self) -> &[Rejected] {
        &self.rejected
    }

    pub fn domains(&self) -> Vec<DomainInfo> {
        self.domains
            .iter()
            .map(|d| DomainInfo {
                manifest: d.found.manifest.clone(),
                catalog: d.catalog.as_ref().ok().cloned(),
                error: d.catalog.as_ref().err().cloned(),
            })
            .collect()
    }

    /// Refuses to call a host whose executable changed after start-up: the run identity and the
    /// replay verdict are bound to the build that was hashed.
    fn checked_host(&self, entry: &DomainEntry) -> Result<(), PlatformError> {
        let now = fs::read(&entry.found.executable)
            .map(|b| sha256_hex(&b))
            .map_err(|e| PlatformError::Host(format!("domain host: {e}")))?;
        if now != entry.host_sha256 {
            return Err(PlatformError::Host(format!(
                "the {} host executable changed since the application started; restart to use the new build",
                entry.found.manifest.id
            )));
        }
        Ok(())
    }

    fn entry(&self, id: &str) -> Result<(&DomainEntry, &DomainCatalog), PlatformError> {
        let entry = self
            .domains
            .iter()
            .find(|d| d.found.manifest.id == id)
            .ok_or_else(|| PlatformError::NotFound(format!("no domain {id} is installed")))?;
        let catalog = entry
            .catalog
            .as_ref()
            .map_err(|e| PlatformError::Host(format!("domain {id} is unavailable: {e}")))?;
        Ok((entry, catalog))
    }

    /// Seed guard, generic validation, then the host validation. Nothing runs before this passes.
    pub fn validate(&self, request: &RunRequest) -> Result<RunRequest, PlatformError> {
        let (entry, catalog) = self.entry(&request.domain)?;
        let manifest = &entry.found.manifest;
        if !manifest.capabilities.iter().any(|c| c == "run") {
            return Err(PlatformError::Invalid(format!(
                "domain {} does not offer runs",
                manifest.id
            )));
        }
        check_seed(&manifest.seeds, request.seed).map_err(PlatformError::Protected)?;
        let normal = normalise(manifest, catalog, request).map_err(PlatformError::Invalid)?;
        let work = self.library.staging().map_err(io)?;
        let file = work.join("request.input.json");
        let result = fs::write(&file, pretty_bytes(&normal))
            .map_err(io)
            .and_then(|_| host_call(&entry.found, vec!["validate".into(), file.clone().into()]));
        let _ = fs::remove_dir_all(&work);
        let out = result?;
        if out.code == EXIT_INVALID_REQUEST {
            return Err(PlatformError::Invalid(out.stderr));
        }
        if out.code != EXIT_OK {
            return Err(PlatformError::Host(format!(
                "validate exited {}: {}",
                out.code, out.stderr
            )));
        }
        let host_normal: RunRequest = serde_json::from_slice(&out.stdout)
            .map_err(|e| PlatformError::Host(format!("invalid validated request: {e}")))?;
        // The host may normalise further, never change the domain or the seed.
        if host_normal.domain != normal.domain || host_normal.seed != normal.seed {
            return Err(PlatformError::Host(
                "the host changed the domain or the seed of the request".into(),
            ));
        }
        Ok(host_normal)
    }

    /// Run identity: the domain, the exact host build and the canonical request.
    pub fn run_id(&self, request: &RunRequest) -> Result<String, PlatformError> {
        let (entry, _) = self.entry(&request.domain)?;
        let identity = serde_json::json!({
            "domain": request.domain,
            "host_sha256": entry.host_sha256,
            "request": request,
        });
        Ok(sha256_hex(&canonical_bytes(&identity))[..16].to_owned())
    }

    pub fn run(&self, request: &RunRequest) -> Result<RunOutcome, PlatformError> {
        let normal = self.validate(request)?;
        self.run_validated(&normal)
    }

    fn run_validated(&self, normal: &RunRequest) -> Result<RunOutcome, PlatformError> {
        let run_id = self.run_id(normal)?;
        if self.library.has_run(&run_id) {
            let meta = self.library.read_meta(&run_id).map_err(io)?;
            return Ok(RunOutcome {
                run_id,
                reused: true,
                meta,
            });
        }
        let (entry, _) = self.entry(&normal.domain)?;
        let work = self.library.staging().map_err(io)?;
        let outcome = self.run_in(entry, normal, &run_id, &work);
        let _ = fs::remove_dir_all(&work);
        outcome
    }

    fn run_in(
        &self,
        entry: &DomainEntry,
        normal: &RunRequest,
        run_id: &str,
        work: &Path,
    ) -> Result<RunOutcome, PlatformError> {
        let input = work.join("request.input.json");
        let out_dir = work.join("run");
        fs::write(&input, pretty_bytes(normal)).map_err(io)?;
        self.checked_host(entry)?;
        let out = host_call(
            &entry.found,
            vec![
                "run".into(),
                input.into(),
                "--output".into(),
                out_dir.clone().into(),
            ],
        )?;
        match out.code {
            EXIT_OK => {}
            EXIT_INVALID_REQUEST => return Err(PlatformError::Invalid(out.stderr)),
            code => {
                return Err(PlatformError::Host(format!(
                    "the simulation failed (exit {code}): {}",
                    out.stderr
                )));
            }
        }
        let bytes = read_bounded(&out_dir.join(RECORD_FILE), MAX_RECORD_BYTES)
            .map_err(PlatformError::Host)?;
        let record: RunRecord = serde_json::from_slice(&bytes)
            .map_err(|e| PlatformError::Host(format!("invalid run record: {e}")))?;
        check_record(&record, normal, &entry.found.manifest)?;
        let on_disk = hash_artifacts(&out_dir).map_err(PlatformError::Host)?;
        if on_disk != record.provenance.artifacts {
            return Err(PlatformError::Host(
                "the run directory does not match the artifact list of its record".into(),
            ));
        }
        fs::write(out_dir.join(REQUEST_FILE), pretty_bytes(normal)).map_err(io)?;
        let meta = RunMeta {
            schema: META_SCHEMA.into(),
            run_id: run_id.into(),
            created_utc: now_utc(),
            host_sha256: entry.host_sha256.clone(),
            label: String::new(),
            notes: String::new(),
            tags: Vec::new(),
            summary: summary_of(&record),
        };
        self.library.publish(&out_dir, &meta).map_err(io)?;
        let meta = self.library.read_meta(run_id).map_err(io)?;
        Ok(RunOutcome {
            run_id: run_id.into(),
            reused: false,
            meta,
        })
    }

    /// Validates every request first (nothing runs if one is refused), then runs them, at most
    /// MAX_PARALLEL host processes at a time. Results keep the request order.
    pub fn compare(
        &self,
        requests: &[RunRequest],
    ) -> Result<Vec<Result<RunOutcome, PlatformError>>, PlatformError> {
        if requests.is_empty() || requests.len() > MAX_COMPARE {
            return Err(PlatformError::Invalid(format!(
                "a comparison runs 1 to {MAX_COMPARE} requests"
            )));
        }
        let normals: Vec<RunRequest> = requests
            .iter()
            .map(|r| self.validate(r))
            .collect::<Result<_, _>>()?;
        let mut results = Vec::with_capacity(normals.len());
        for chunk in normals.chunks(MAX_PARALLEL) {
            let chunk_results: Vec<Result<RunOutcome, PlatformError>> = std::thread::scope(|s| {
                let handles: Vec<_> = chunk
                    .iter()
                    .map(|n| s.spawn(move || self.run_validated(n)))
                    .collect();
                handles
                    .into_iter()
                    .map(|h| {
                        h.join().unwrap_or_else(|_| {
                            Err(PlatformError::Host("a run thread panicked".into()))
                        })
                    })
                    .collect()
            });
            results.extend(chunk_results);
        }
        Ok(results)
    }

    pub fn record(&self, run_id: &str) -> Result<RunRecord, PlatformError> {
        if !self.library.has_run(run_id) {
            return Err(PlatformError::NotFound(format!(
                "run {run_id} is not in the library"
            )));
        }
        self.library.read_record(run_id).map_err(io)
    }

    /// Platform checks on the stored files, then the host replay, which recomputes the run.
    pub fn replay(&self, run_id: &str) -> Result<ReplayReport, PlatformError> {
        let record = self.record(run_id)?;
        let dir = self
            .library
            .run_dir(run_id)
            .map_err(PlatformError::Invalid)?;
        let (entry, _) = self.entry(&record.domain.id)?;
        let mut checks = Vec::new();
        let stored_request: Option<RunRequest> = read_bounded(&dir.join(REQUEST_FILE), 64 * 1024)
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok());
        checks.push(ReplayCheck {
            name: "request.json equals the request inside record.json".into(),
            pass: stored_request.as_ref() == Some(&record.request),
            detail: String::new(),
        });
        let guard = check_seed(&entry.found.manifest.seeds, record.request.seed);
        checks.push(ReplayCheck {
            name: "the stored seed is allowed by the seed policy".into(),
            pass: guard.is_ok(),
            detail: guard.err().unwrap_or_default(),
        });
        // meta.json is what the Library shows; it must say what record.json says, and the run id
        // must be the identity of the stored request under the host build that produced it.
        let meta = self.library.read_meta(run_id);
        // A run stored by another host build may no longer reproduce byte for byte (see
        // `host_sdk::replay_earlier_build`). The strict replay always runs first and decides
        // alone when it passes; the earlier-build replay is only a fallback for a run it rejects,
        // and the run id check below still binds the run to its stored request and to the build
        // that wrote it, so the fallback cannot be obtained by editing files.
        let other_build = matches!(&meta, Ok(m) if m.host_sha256 != entry.host_sha256);
        let (summary_ok, id_ok, build) = match &meta {
            Ok(m) => {
                let identity = serde_json::json!({
                    "domain": record.request.domain,
                    "host_sha256": m.host_sha256,
                    "request": record.request,
                });
                let id = sha256_hex(&canonical_bytes(&identity))[..16].to_owned();
                (
                    m.summary == summary_of(&record),
                    m.run_id == run_id && id == run_id,
                    if m.host_sha256 == entry.host_sha256 {
                        String::new()
                    } else {
                        "recomputed by a different host build than the one that produced the run"
                            .to_string()
                    },
                )
            }
            Err(_) => (false, false, String::new()),
        };
        checks.push(ReplayCheck {
            name: "meta.json summary equals the summary of record.json".into(),
            pass: summary_ok,
            detail: meta.as_ref().err().cloned().unwrap_or_default(),
        });
        checks.push(ReplayCheck {
            name: "the run id is the identity of the stored request and host build".into(),
            pass: id_ok,
            detail: build,
        });
        // A protected seed is never recomputed, even from a stored run.
        let mut earlier_build = false;
        if checks.iter().all(|c| c.pass) {
            self.checked_host(entry)?;
            let strict = host_replay(&entry.found, &dir, false)?;
            if other_build && !strict.iter().all(|c| c.pass) {
                let earlier = host_replay(&entry.found, &dir, true)?;
                earlier_build = earlier.iter().all(|c| c.pass);
                checks.extend(earlier);
            } else {
                checks.extend(strict);
            }
        }
        let ok = checks.iter().all(|c| c.pass);
        Ok(ReplayReport {
            schema: REPLAY_SCHEMA.into(),
            status: if !ok {
                "rejected"
            } else if earlier_build {
                REPLAY_VERIFIED_EARLIER_BUILD
            } else {
                "verified"
            }
            .into(),
            checks,
        })
    }

    /// Writes an evidence package and returns its path (default: the library exports directory).
    pub fn export_evidence(
        &self,
        run_id: &str,
        dest: Option<PathBuf>,
    ) -> Result<PathBuf, PlatformError> {
        let record = self.record(run_id)?;
        let replay = self.replay(run_id)?;
        let dir = self
            .library
            .run_dir(run_id)
            .map_err(PlatformError::Invalid)?;
        let bytes = evidence::package(&dir, run_id, &record, &replay, &self.version).map_err(io)?;
        let path = dest.unwrap_or_else(|| {
            let suffix = if replay.status == "rejected" {
                "-REJECTED"
            } else {
                ""
            };
            self.library
                .exports_dir()
                .join(format!("{run_id}-evidence{suffix}.zip"))
        });
        crate::library::write_atomic(&path, &bytes).map_err(io)?;
        Ok(path)
    }
}

/// One host replay: the checks it reports and the platform's verdict on them. `earlier_build`
/// asks for the replay of a run that another build of the host stored.
fn host_replay(
    found: &Discovered,
    dir: &Path,
    earlier_build: bool,
) -> Result<Vec<ReplayCheck>, PlatformError> {
    let mut args: Vec<OsString> = vec!["replay".into(), dir.into()];
    if earlier_build {
        args.push(EARLIER_BUILD_FLAG.into());
    }
    let out = host_call(found, args)?;
    Ok(match serde_json::from_slice::<ReplayReport>(&out.stdout) {
        Ok(report) if report.schema == REPLAY_SCHEMA => {
            let verdict = host_replay_verdict(&report, out.code, earlier_build);
            let mut checks = report.checks;
            checks.push(verdict);
            checks
        }
        Ok(_) => vec![failed("host replay report", "unknown schema")],
        Err(e) => vec![failed(
            "host replay report",
            &format!("{e}: {}", out.stderr),
        )],
    })
}

fn failed(name: &str, detail: &str) -> ReplayCheck {
    ReplayCheck {
        name: name.into(),
        pass: false,
        detail: detail.into(),
    }
}

fn check_record(
    record: &RunRecord,
    request: &RunRequest,
    manifest: &DomainManifest,
) -> Result<(), PlatformError> {
    let bad = |m: &str| {
        Err(PlatformError::Host(format!(
            "the run record breaks the contract: {m}"
        )))
    };
    if record.schema != RECORD_SCHEMA && record.schema != RECORD_SCHEMA_V2 {
        return bad("schema");
    }
    if let Err(e) = record.check_entities() {
        return bad(&e);
    }
    if &record.request != request {
        return bad("request differs from the validated request");
    }
    if record.domain.id != manifest.id {
        return bad("domain id");
    }
    if !["success", "partial", "failure"].contains(&record.outcome.status.as_str()) {
        return bad("outcome.status");
    }
    if !["safe", "unsafe"].contains(&record.safety.status.as_str()) {
        return bad("safety.status");
    }
    for c in &record.channels {
        let Some(tb) = record.timebases.get(&c.timebase) else {
            return bad(&format!("channel {} names an unknown timebase", c.id));
        };
        if tb.len() != c.values.len() {
            return bad(&format!(
                "channel {} length differs from its timebase",
                c.id
            ));
        }
    }
    for r in &record.requirements {
        if !["pass", "fail", "not_evaluated"].contains(&r.status.as_str()) {
            return bad(&format!("requirement {} status", r.id));
        }
    }
    Ok(())
}

/// A host is a separate program: its replay counts only if it exited cleanly, said "verified" and
/// reported the recomputation checks of the contract as passed. An empty or partial report fails.
fn host_replay_verdict(report: &ReplayReport, code: i32, earlier_build: bool) -> ReplayCheck {
    let names = if earlier_build {
        EARLIER_BUILD_RECOMPUTE_CHECKS
    } else {
        RECOMPUTE_CHECKS
    };
    let recomputed = names
        .iter()
        .all(|n| report.checks.iter().any(|c| c.name == *n && c.pass));
    let clean = code == EXIT_OK && report.status == "verified";
    ReplayCheck {
        name: "the domain host recomputed the run and reported it verified".into(),
        pass: recomputed && clean,
        detail: if recomputed && clean {
            String::new()
        } else {
            format!(
                "host status {:?}, exit code {code}, recomputation checks {}",
                report.status,
                if recomputed {
                    "present"
                } else {
                    "missing or failed"
                }
            )
        },
    }
}

/// Check names every domain host replay must report as passed (see `host_sdk::replay`).
pub const RECOMPUTE_CHECKS: [&str; 2] = [
    "the run is recomputed from its request",
    "recomputed artifacts equal the stored artifacts byte for byte",
];

/// The same for a run stored by an earlier host build: recomputed, and agreeing with the stored
/// record (the strict byte comparison cannot hold across builds).
pub const EARLIER_BUILD_RECOMPUTE_CHECKS: [&str; 2] = [
    "the run is recomputed from its request",
    EARLIER_BUILD_AGREEMENT_CHECK,
];

#[cfg(test)]
mod replay_verdict_tests {
    use super::*;

    fn report(status: &str, names: &[(&str, bool)]) -> ReplayReport {
        ReplayReport {
            schema: REPLAY_SCHEMA.into(),
            status: status.into(),
            checks: names
                .iter()
                .map(|(n, pass)| ReplayCheck {
                    name: (*n).into(),
                    pass: *pass,
                    detail: String::new(),
                })
                .collect(),
        }
    }

    #[test]
    fn a_host_report_without_recomputation_is_not_verified() {
        assert!(!host_replay_verdict(&report("verified", &[]), EXIT_OK, false).pass);
        let partial = report("verified", &[(RECOMPUTE_CHECKS[0], true)]);
        assert!(!host_replay_verdict(&partial, EXIT_OK, false).pass);
    }

    #[test]
    fn a_host_verdict_needs_status_exit_code_and_passed_recomputation() {
        let full = [(RECOMPUTE_CHECKS[0], true), (RECOMPUTE_CHECKS[1], true)];
        assert!(host_replay_verdict(&report("verified", &full), EXIT_OK, false).pass);
        assert!(!host_replay_verdict(&report("rejected", &full), EXIT_OK, false).pass);
        assert!(!host_replay_verdict(&report("verified", &full), 3, false).pass);
        let failed = [(RECOMPUTE_CHECKS[0], true), (RECOMPUTE_CHECKS[1], false)];
        assert!(!host_replay_verdict(&report("verified", &failed), EXIT_OK, false).pass);
    }

    #[test]
    fn an_earlier_build_needs_the_agreement_check_and_the_strict_byte_check_does_not_count() {
        let strict = [(RECOMPUTE_CHECKS[0], true), (RECOMPUTE_CHECKS[1], true)];
        // A report that only passes the strict byte comparison is not an earlier-build verification.
        assert!(!host_replay_verdict(&report("verified", &strict), EXIT_OK, true).pass);
        let agreed = [
            (EARLIER_BUILD_RECOMPUTE_CHECKS[0], true),
            (EARLIER_BUILD_RECOMPUTE_CHECKS[1], true),
        ];
        assert!(host_replay_verdict(&report("verified", &agreed), EXIT_OK, true).pass);
        // And the earlier-build checks never satisfy the strict verdict of a run of the same build.
        assert!(!host_replay_verdict(&report("verified", &agreed), EXIT_OK, false).pass);
        let disagreed = [
            (EARLIER_BUILD_RECOMPUTE_CHECKS[0], true),
            (EARLIER_BUILD_RECOMPUTE_CHECKS[1], false),
        ];
        assert!(!host_replay_verdict(&report("verified", &disagreed), EXIT_OK, true).pass);
    }
}
