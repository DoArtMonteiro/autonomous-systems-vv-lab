//! Evidence packages. A package is a zip of one stored run: every file the host wrote, the
//! normalised request, a fresh replay report, a SHA-256 manifest and a README with the commands that
//! reproduce the run. Members are sorted and carry a fixed date, so the same run and the same replay
//! produce the same bytes. Library metadata (meta.json: notes, creation time) is not included.

use std::io::{Cursor, Write};
use std::path::Path;

use serde::Serialize;
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, DateTime, ZipWriter};

use crate::canonical::{pretty_bytes, sha256_hex};
use crate::contract::{
    FileHash, META_FILE, REPLAY_VERIFIED_EARLIER_BUILD, ReplayReport, RunRecord,
};
use crate::host_sdk::read_bounded;

pub const EVIDENCE_SCHEMA: &str = "vv-evidence.v1";

/// Every run the desktop application can make is a development demonstration: the platform and
/// the hosts refuse the protected evaluation and reserve seeds, so no package from this
/// application is a scientifically accepted outcome.
pub const EVIDENCE_CLASS: &str = "development_demonstration";
const MAX_PACKAGE_BYTES: u64 = 96 * 1024 * 1024;

#[derive(Serialize)]
struct Manifest<'a> {
    schema: &'static str,
    run_id: &'a str,
    domain: &'a str,
    domain_version: &'a str,
    platform_version: &'a str,
    evidence_class: &'static str,
    replay_status: &'a str,
    files: Vec<FileHash>,
}

fn readme(run_id: &str, record: &RunRecord, replay: &ReplayReport) -> String {
    let mut text = format!(
        "# Evidence package {run_id}\n\nEvidence class: development demonstration. Not a scientifically accepted outcome: this application refuses the protected evaluation and reserve seeds.\n\nDomain: {} {} (contract {})\n\nRequest: scenario {}, controller {}, seed {}, {} fault(s).\n\nOutcome: {} ({}). Safety: {}.\n\nFresh replay when this package was made: {}.\n\nModel validity: {}\n\n## Reproduce\n\nFrom a checkout of the repository at the commit that produced the simulator (source SHA-256 {}):\n\n",
        record.domain.id,
        record.domain.version,
        record.domain.contract,
        record.request.scenario,
        record.request.controller,
        record.request.seed,
        record.request.faults.len(),
        record.outcome.label,
        record.outcome.status,
        record.safety.status,
        replay.status,
        record.model_validity,
        record.provenance.source_sha256,
    );
    for line in &record.provenance.reproduce {
        text.push_str("    ");
        text.push_str(line);
        text.push('\n');
    }
    text.push_str("\nThe desktop application replays a stored run by recomputing it from request.json and comparing every file byte for byte; replay.json lists each check.\n");
    if replay.status == REPLAY_VERIFIED_EARLIER_BUILD {
        text.push_str("\nThis run was recorded by an earlier build of the domain host. It was recomputed with the current defaults and agrees with the stored record on every requirement verdict and every recorded number; the files are not byte-identical and the native simulator replay was not run. replay.json states what was checked.\n");
    }
    text.push_str("\n## Notes\n\n");
    for note in &record.notes {
        text.push_str("- ");
        text.push_str(note);
        text.push('\n');
    }
    text
}

pub fn package(
    run_dir: &Path,
    run_id: &str,
    record: &RunRecord,
    replay: &ReplayReport,
    platform_version: &str,
) -> Result<Vec<u8>, String> {
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();
    let mut names = Vec::new();
    collect(run_dir, run_dir, &mut names)?;
    names.sort();
    for name in names {
        if name == META_FILE {
            continue;
        }
        let bytes = read_bounded(&run_dir.join(&name), MAX_PACKAGE_BYTES)?;
        files.push((name, bytes));
    }
    files.push(("replay.json".into(), pretty_bytes(replay)));
    files.push((
        "README.md".into(),
        readme(run_id, record, replay).into_bytes(),
    ));
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let manifest = Manifest {
        schema: EVIDENCE_SCHEMA,
        run_id,
        domain: &record.domain.id,
        domain_version: &record.domain.version,
        platform_version,
        evidence_class: EVIDENCE_CLASS,
        replay_status: &replay.status,
        files: files
            .iter()
            .map(|(path, bytes)| FileHash {
                path: path.clone(),
                sha256: sha256_hex(bytes),
                bytes: bytes.len() as u64,
            })
            .collect(),
    };
    files.push(("MANIFEST.json".into(), pretty_bytes(&manifest)));
    let total: u64 = files.iter().map(|(_, b)| b.len() as u64).sum();
    if total > MAX_PACKAGE_BYTES {
        return Err(format!(
            "the package would exceed {MAX_PACKAGE_BYTES} bytes"
        ));
    }
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .last_modified_time(DateTime::default())
        .unix_permissions(0o644);
    let mut zip = ZipWriter::new(Cursor::new(Vec::new()));
    for (name, bytes) in files {
        zip.start_file(format!("{run_id}/{name}"), options)
            .map_err(|e| e.to_string())?;
        zip.write_all(&bytes).map_err(|e| e.to_string())?;
    }
    Ok(zip.finish().map_err(|e| e.to_string())?.into_inner())
}

fn collect(root: &Path, dir: &Path, out: &mut Vec<String>) -> Result<(), String> {
    for entry in std::fs::read_dir(dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let kind = entry.file_type().map_err(|e| e.to_string())?;
        let path = entry.path();
        if kind.is_symlink() {
            return Err("a run directory must not contain links".into());
        }
        if kind.is_dir() {
            collect(root, &path, out)?;
        } else {
            let rel = path.strip_prefix(root).map_err(|e| e.to_string())?;
            out.push(
                rel.components()
                    .map(|c| c.as_os_str().to_string_lossy().into_owned())
                    .collect::<Vec<_>>()
                    .join("/"),
            );
        }
    }
    Ok(())
}
