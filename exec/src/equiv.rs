//! Equivalence gate. The command line of each domain stays the canonical reference. For a fixed
//! sample of plan entries the gate writes the artifacts twice, through the canonical command line
//! and through the in-process writer, and requires equal bytes in every file; it also requires the
//! logged record to match the artifacts and to be reproduced by a fresh in-process run, and the
//! command line to replay the in-process directory as verified. One difference fails the gate.

use std::fs;
use std::path::Path;
use std::process::Command;

use serde::Serialize;

use crate::engine::{Record, case_file, recompute};
use crate::plan::{Plan, sha256_hex};

pub const SCHEMA: &str = "vv-exec-equivalence.v1";
pub const MAX_SAMPLE: usize = 1000;

#[derive(Clone, Debug, Serialize)]
pub struct FileComparison {
    pub name: String,
    pub equal: bool,
    /// Byte offset of the first difference, or the shorter length when one is a prefix.
    pub first_difference: Option<u64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct CaseComparison {
    pub index: u64,
    pub seed: u64,
    pub variant: u32,
    pub cli_exit: Option<i32>,
    pub files: Vec<FileComparison>,
    pub record_matches: bool,
    pub recomputed: bool,
    pub replay_verified: bool,
    pub problems: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Equivalence {
    pub schema: &'static str,
    pub plan_sha256: String,
    pub cli_source_sha256: Option<String>,
    pub library_source_sha256: String,
    pub source_sha256_match: bool,
    pub cases: Vec<CaseComparison>,
    pub differences: u64,
    pub pass: bool,
}

/// Plan indices compared: `k` evenly spaced entries with both ends, plus the first failure.
pub fn sample(records: &[Record], k: usize) -> Vec<u64> {
    let n = records.len();
    let k = k.min(n);
    let mut out: Vec<u64> = match k {
        0 => Vec::new(),
        1 => vec![0],
        _ => (0..k).map(|i| (i * (n - 1) / (k - 1)) as u64).collect(),
    };
    if let Some(f) = records.iter().find(|r| r.is_failure() && r.error.is_none()) {
        out.push(f.index);
    }
    out.sort_unstable();
    out.dedup();
    out
}

fn compare(a: &[u8], b: &[u8]) -> Option<u64> {
    if a == b {
        return None;
    }
    let common = a.iter().zip(b).position(|(x, y)| x != y);
    Some(common.unwrap_or(a.len().min(b.len())) as u64)
}

pub fn run(
    plan: &Plan,
    out: &Path,
    records: &[Record],
    cli: &Path,
    k: usize,
) -> Result<Equivalence, String> {
    if k == 0 || k > MAX_SAMPLE {
        return Err(format!("sample must be in [1, {MAX_SAMPLE}]"));
    }
    let root = out.join("equivalence");
    if root.exists() {
        return Err(format!(
            "{} already exists; the gate writes into a fresh directory",
            root.display()
        ));
    }
    let domain = plan.domain;
    let mut report = Equivalence {
        schema: SCHEMA,
        plan_sha256: plan.plan_sha256.clone(),
        cli_source_sha256: None,
        library_source_sha256: domain.source_sha256(),
        source_sha256_match: false,
        cases: Vec::new(),
        differences: 0,
        pass: false,
    };
    for index in sample(records, k) {
        let rec = &records[index as usize];
        let mut problems = Vec::new();
        let dir = root.join(format!("{index:08}"));
        let (lib, cli_dir) = (dir.join("lib"), dir.join("cli"));
        let case = case_file(plan, out, rec.variant)?;
        if let Err(e) = domain.write(&case, rec.seed, &lib) {
            problems.push(format!("in-process writer: {e}"));
        }
        let args = domain.cli_args(&case, rec.seed, &cli_dir, &dir.join("cli-inputs"))?;
        let status = Command::new(cli)
            .args(args)
            .output()
            .map_err(|e| format!("{}: {e}", cli.display()))?;
        let mut files = Vec::new();
        for name in domain.files() {
            match (fs::read(lib.join(name)), fs::read(cli_dir.join(name))) {
                (Ok(a), Ok(b)) => files.push(FileComparison {
                    name: name.to_string(),
                    equal: a == b,
                    first_difference: compare(&a, &b),
                }),
                _ => {
                    problems.push(format!("{name} is missing on one side"));
                    files.push(FileComparison {
                        name: name.to_string(),
                        equal: false,
                        first_difference: Some(0),
                    });
                }
            }
        }
        if report.cli_source_sha256.is_none() {
            report.cli_source_sha256 = domain.written_source_sha256(&cli_dir);
        }
        let hash = |name: &str| fs::read(lib.join(name)).ok().map(|b| sha256_hex(&b));
        let case_hash = match domain.case_copy_file() {
            Some(name) => hash(name),
            None => fs::read(&case).ok().map(|b| sha256_hex(&b)),
        };
        let record_matches = case_hash.as_deref() == Some(rec.case_sha256.as_str())
            && hash(domain.trace_file()) == rec.trace_sha256
            && match (domain.verification_file(), &rec.verification_sha256) {
                (_, None) => true,
                (Some(name), Some(h)) => hash(name).as_ref() == Some(h),
                (None, Some(_)) => false,
            };
        if !record_matches {
            problems.push("the logged record does not match the artifacts".into());
        }
        let recomputed = match recompute(plan, rec) {
            Ok(()) => true,
            Err(e) => {
                problems.push(e);
                false
            }
        };
        let replay = Command::new(cli)
            .args(domain.cli_replay_args(&lib))
            .output()
            .map_err(|e| format!("{}: {e}", cli.display()))?;
        let replay_verified = replay.status.success();
        if !replay_verified {
            problems.push(
                "the command line does not replay the in-process directory as verified".into(),
            );
        }
        if !problems.is_empty() || files.iter().any(|f| !f.equal) {
            report.differences += 1;
        }
        report.cases.push(CaseComparison {
            index,
            seed: rec.seed,
            variant: rec.variant,
            cli_exit: status.status.code(),
            files,
            record_matches,
            recomputed,
            replay_verified,
            problems,
        });
    }
    report.source_sha256_match =
        report.cli_source_sha256.as_deref() == Some(report.library_source_sha256.as_str());
    report.pass = report.source_sha256_match && report.differences == 0 && !report.cases.is_empty();
    let mut bytes = serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::write(out.join("equivalence.json"), bytes).map_err(|e| e.to_string())?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rec(index: u64, fail: bool) -> Record {
        Record {
            index,
            variant: 0,
            arm: 0,
            cell: 0,
            replicate: 0,
            seed: index,
            case_sha256: String::new(),
            in_envelope: true,
            error: None,
            trace_sha256: None,
            verification_sha256: None,
            outcome: None,
            requirements_pass: None,
            invariants_pass: None,
            all_pass: Some(!fail),
            metrics: Default::default(),
        }
    }

    #[test]
    fn the_sample_holds_both_ends_and_the_first_failure() {
        let recs: Vec<Record> = (0..101).map(|i| rec(i, i == 37 || i == 80)).collect();
        assert_eq!(sample(&recs, 5), vec![0, 25, 37, 50, 75, 100]);
        assert_eq!(sample(&recs[..3], 10), vec![0, 1, 2]);
        assert_eq!(sample(&recs, 1), vec![0, 37]);
    }

    #[test]
    fn compare_reports_the_first_differing_offset() {
        assert_eq!(compare(b"abc", b"abc"), None);
        assert_eq!(compare(b"abc", b"abd"), Some(2));
        assert_eq!(compare(b"ab", b"abc"), Some(2));
    }
}
