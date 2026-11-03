//! The persistent library: stored runs, saved scenarios and saved comparisons, as plain JSON files
//! under one root directory chosen by the application (outside the install directory, so an
//! uninstall never removes research outputs). A run directory is built in `staging/` and published
//! with one rename, so a crash leaves either a complete run or a staging entry that `recover`
//! clears on the next start. Wall-clock times here are library metadata only; they never enter a
//! simulation, a run identity or an evidence hash.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

use crate::canonical::{pretty_bytes, sha256_hex};
use crate::contract::{META_FILE, RECORD_FILE, RunRecord, RunRequest};
use crate::host_sdk::{MAX_RECORD_BYTES, read_bounded};

pub const META_SCHEMA: &str = "vv-run-meta.v1";
pub const SCENARIO_SCHEMA: &str = "vv-scenario.v1";
pub const COMPARISON_SCHEMA: &str = "vv-comparison.v1";
const MAX_LISTED: usize = 5000;
const MAX_TEXT: usize = 4000;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RunSummary {
    pub domain: String,
    pub scenario: String,
    pub controller: String,
    pub seed: u64,
    pub faults: Vec<String>,
    pub outcome_code: String,
    pub outcome_label: String,
    pub outcome_status: String,
    pub safety_status: String,
    pub safety_class: Option<String>,
    /// Ids of failed requirements, invariants and declarations.
    pub failed: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RunMeta {
    pub schema: String,
    pub run_id: String,
    pub created_utc: String,
    /// SHA-256 of the domain host executable that produced the run.
    pub host_sha256: String,
    pub label: String,
    pub notes: String,
    pub tags: Vec<String>,
    pub summary: RunSummary,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SavedScenario {
    pub schema: String,
    pub id: String,
    pub name: String,
    pub notes: String,
    pub requests: Vec<RunRequest>,
    pub created_utc: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SavedComparison {
    pub schema: String,
    pub id: String,
    pub name: String,
    pub notes: String,
    pub run_ids: Vec<String>,
    pub created_utc: String,
}

pub fn summary_of(record: &RunRecord) -> RunSummary {
    RunSummary {
        domain: record.domain.id.clone(),
        scenario: record.request.scenario.clone(),
        controller: record.request.controller.clone(),
        seed: record.request.seed,
        faults: record
            .request
            .faults
            .iter()
            .map(|f| f.kind.clone())
            .collect(),
        outcome_code: record.outcome.code.clone(),
        outcome_label: record.outcome.label.clone(),
        outcome_status: record.outcome.status.clone(),
        safety_status: record.safety.status.clone(),
        safety_class: record.safety.class.clone(),
        failed: record
            .requirements
            .iter()
            .filter(|r| r.status == "fail")
            .map(|r| r.id.clone())
            .collect(),
    }
}

fn hex_of_len(id: &str, len: usize) -> bool {
    id.len() == len
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub fn valid_run_id(id: &str) -> bool {
    hex_of_len(id, 16)
}

/// UTC time as an ISO 8601 string, from the system clock; metadata only.
pub fn now_utc() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    // Civil date from days since 1970-01-01 (Howard Hinnant).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!(
        "{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z",
        rem / 3600,
        (rem / 60) % 60,
        rem % 60
    )
}

fn clip(text: &str) -> String {
    text.chars().take(MAX_TEXT).collect()
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn fresh_id(seed: &str) -> String {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    sha256_hex(format!("{seed}|{}|{}|{n}", now_utc(), std::process::id()).as_bytes())[..12]
        .to_owned()
}

/// Writes through a temporary file and a rename so a reader never sees half a file.
pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    use std::io::Write;
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    // A unique temporary name per write: concurrent writers never share a partial file.
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let tmp = path.with_file_name(format!(
        ".{name}.{}-{}.tmp",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed)
    ));
    let written = fs::File::create(&tmp)
        .and_then(|mut f| f.write_all(bytes).and_then(|()| f.sync_all()))
        .map_err(|e| e.to_string())
        .and_then(|()| rename_retry(&tmp, path));
    if written.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    written
}

fn rename_retry(from: &Path, to: &Path) -> Result<(), String> {
    // Windows refuses a rename while an indexer or scanner briefly holds a file.
    let mut last = String::new();
    for _ in 0..40 {
        match fs::rename(from, to) {
            Ok(()) => return Ok(()),
            Err(e) => last = e.to_string(),
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    Err(last)
}

#[derive(Clone, Debug)]
pub struct Library {
    root: PathBuf,
}

impl Library {
    pub fn open(root: &Path) -> Result<Self, String> {
        for sub in ["runs", "scenarios", "comparisons", "staging", "exports"] {
            fs::create_dir_all(root.join(sub)).map_err(|e| format!("library {sub}: {e}"))?;
        }
        Ok(Library {
            root: root.to_path_buf(),
        })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn exports_dir(&self) -> PathBuf {
        self.root.join("exports")
    }

    /// Clears what a crashed or interrupted run left in staging; returns how many entries.
    pub fn recover(&self) -> usize {
        let Ok(entries) = fs::read_dir(self.root.join("staging")) else {
            return 0;
        };
        let mut n = 0;
        for entry in entries.filter_map(Result::ok) {
            let path = entry.path();
            let gone = if path.is_dir() {
                fs::remove_dir_all(&path)
            } else {
                fs::remove_file(&path)
            };
            if gone.is_ok() {
                n += 1;
            }
        }
        n
    }

    pub fn staging(&self) -> Result<PathBuf, String> {
        let dir = self.root.join("staging").join(fresh_id("staging"));
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        Ok(dir)
    }

    pub fn run_dir(&self, id: &str) -> Result<PathBuf, String> {
        if !valid_run_id(id) {
            return Err("a run id is 16 hexadecimal digits".into());
        }
        Ok(self.root.join("runs").join(id))
    }

    pub fn has_run(&self, id: &str) -> bool {
        self.run_dir(id)
            .map(|d| d.join(META_FILE).is_file() && d.join(RECORD_FILE).is_file())
            .unwrap_or(false)
    }

    /// Moves a complete staging directory to its run id; meta.json is written inside it first.
    pub fn publish(&self, staging: &Path, meta: &RunMeta) -> Result<(), String> {
        fs::write(staging.join(META_FILE), pretty_bytes(meta)).map_err(|e| e.to_string())?;
        let dest = self.run_dir(&meta.run_id)?;
        if dest.exists() {
            // A complete earlier run is kept; an incomplete directory (no meta) is replaced.
            if self.has_run(&meta.run_id) {
                let _ = fs::remove_dir_all(staging);
                return Ok(());
            }
            fs::remove_dir_all(&dest).map_err(|e| e.to_string())?;
        }
        rename_retry(staging, &dest)
    }

    pub fn read_meta(&self, id: &str) -> Result<RunMeta, String> {
        let bytes = read_bounded(&self.run_dir(id)?.join(META_FILE), 1024 * 1024)?;
        serde_json::from_slice(&bytes).map_err(|e| format!("meta.json: {e}"))
    }

    pub fn read_record(&self, id: &str) -> Result<RunRecord, String> {
        let bytes = read_bounded(&self.run_dir(id)?.join(RECORD_FILE), MAX_RECORD_BYTES)?;
        serde_json::from_slice(&bytes).map_err(|e| format!("record.json: {e}"))
    }

    pub fn update_notes(
        &self,
        id: &str,
        label: &str,
        notes: &str,
        tags: &[String],
    ) -> Result<RunMeta, String> {
        let mut meta = self.read_meta(id)?;
        meta.label = clip(label);
        meta.notes = clip(notes);
        meta.tags = tags.iter().take(16).map(|t| clip(t)).collect();
        write_atomic(&self.run_dir(id)?.join(META_FILE), &pretty_bytes(&meta))?;
        Ok(meta)
    }

    /// Stored runs, newest first. Entries without a readable meta.json are skipped.
    pub fn list_runs(&self) -> Vec<RunMeta> {
        let Ok(entries) = fs::read_dir(self.root.join("runs")) else {
            return Vec::new();
        };
        let mut runs: Vec<RunMeta> = entries
            .filter_map(Result::ok)
            .filter_map(|e| e.file_name().into_string().ok())
            .filter(|n| valid_run_id(n))
            .take(MAX_LISTED)
            .filter_map(|n| self.read_meta(&n).ok())
            .collect();
        runs.sort_by(|a, b| {
            b.created_utc
                .cmp(&a.created_utc)
                .then(a.run_id.cmp(&b.run_id))
        });
        runs
    }

    fn items<T: DeserializeOwned>(&self, sub: &str) -> Vec<T> {
        let Ok(entries) = fs::read_dir(self.root.join(sub)) else {
            return Vec::new();
        };
        let mut paths: Vec<PathBuf> = entries
            .filter_map(Result::ok)
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|x| x == "json"))
            .collect();
        paths.sort();
        paths
            .iter()
            .take(MAX_LISTED)
            .filter_map(|p| read_bounded(p, 1024 * 1024).ok())
            .filter_map(|b| serde_json::from_slice(&b).ok())
            .collect()
    }

    fn item_path(&self, sub: &str, id: &str) -> Result<PathBuf, String> {
        if !hex_of_len(id, 12) {
            return Err("an item id is 12 hexadecimal digits".into());
        }
        Ok(self.root.join(sub).join(format!("{id}.json")))
    }

    pub fn save_scenario(
        &self,
        name: &str,
        notes: &str,
        requests: Vec<RunRequest>,
    ) -> Result<SavedScenario, String> {
        if requests.is_empty() || requests.len() > 8 {
            return Err("a saved scenario holds 1 to 8 requests".into());
        }
        let item = SavedScenario {
            schema: SCENARIO_SCHEMA.into(),
            id: fresh_id(name),
            name: clip(name),
            notes: clip(notes),
            requests,
            created_utc: now_utc(),
        };
        write_atomic(
            &self.item_path("scenarios", &item.id)?,
            &pretty_bytes(&item),
        )?;
        Ok(item)
    }

    pub fn list_scenarios(&self) -> Vec<SavedScenario> {
        self.items("scenarios")
    }

    pub fn delete_scenario(&self, id: &str) -> Result<(), String> {
        fs::remove_file(self.item_path("scenarios", id)?).map_err(|e| e.to_string())
    }

    pub fn save_comparison(
        &self,
        name: &str,
        notes: &str,
        run_ids: Vec<String>,
    ) -> Result<SavedComparison, String> {
        if run_ids.is_empty() || run_ids.len() > 8 {
            return Err("a comparison holds 1 to 8 runs".into());
        }
        for id in &run_ids {
            if !self.has_run(id) {
                return Err(format!("run {id} is not in the library"));
            }
        }
        let item = SavedComparison {
            schema: COMPARISON_SCHEMA.into(),
            id: fresh_id(name),
            name: clip(name),
            notes: clip(notes),
            run_ids,
            created_utc: now_utc(),
        };
        write_atomic(
            &self.item_path("comparisons", &item.id)?,
            &pretty_bytes(&item),
        )?;
        Ok(item)
    }

    pub fn list_comparisons(&self) -> Vec<SavedComparison> {
        self.items("comparisons")
    }

    pub fn delete_comparison(&self, id: &str) -> Result<(), String> {
        fs::remove_file(self.item_path("comparisons", id)?).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn concurrent_atomic_writes_leave_one_complete_file_and_no_temporaries() {
        let dir = std::env::temp_dir().join(format!("vv-write-atomic-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        let target = dir.join("meta.json");
        let payloads: Vec<Vec<u8>> = (0..4u8).map(|i| vec![b'a' + i; 64 * 1024]).collect();
        std::thread::scope(|s| {
            for p in &payloads {
                let target = &target;
                s.spawn(move || {
                    for _ in 0..10 {
                        write_atomic(target, p).unwrap();
                    }
                });
            }
        });
        let got = fs::read(&target).unwrap();
        assert!(payloads.contains(&got));
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 1);
        fs::remove_dir_all(&dir).unwrap();
    }
}
