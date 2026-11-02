//! Discovery of domain hosts. Each subdirectory of a domains directory that holds a `domain.json`
//! is a candidate; the platform accepts it only when the manifest parses, names this contract with
//! the same major version and a minor version this platform knows, has a safe id, and its host
//! executable exists next to it. Nothing is executed during discovery.

use std::fs;
use std::path::{Path, PathBuf};

use crate::contract::{
    CONTRACT_MAJOR, CONTRACT_MINOR, CONTRACT_NAME, DomainManifest, MANIFEST_SCHEMA,
};

pub const MANIFEST_FILE: &str = "domain.json";
const MAX_MANIFEST_BYTES: u64 = 64 * 1024;
const MAX_DOMAINS: usize = 64;

#[derive(Clone, Debug)]
pub struct Discovered {
    pub manifest: DomainManifest,
    pub dir: PathBuf,
    pub executable: PathBuf,
}

#[derive(Clone, Debug, serde::Serialize)]
pub struct Rejected {
    /// Directory name only, so no absolute path reaches the UI.
    pub dir: String,
    pub reason: String,
}

#[derive(Clone, Debug, Default)]
pub struct DiscoveryReport {
    pub domains: Vec<Discovered>,
    pub rejected: Vec<Rejected>,
}

pub fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 40
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        && !id.starts_with('-')
}

pub fn check_manifest(manifest: &DomainManifest) -> Result<(), String> {
    if manifest.schema != MANIFEST_SCHEMA {
        return Err(format!("schema must be {MANIFEST_SCHEMA}"));
    }
    if !valid_id(&manifest.id) {
        return Err("id must be 1 to 40 characters of a-z, 0-9 and -".into());
    }
    let c = &manifest.contract;
    if c.name != CONTRACT_NAME {
        return Err(format!("contract {} is not {CONTRACT_NAME}", c.name));
    }
    if c.major != CONTRACT_MAJOR {
        return Err(format!(
            "contract major version {} is incompatible with this platform ({CONTRACT_MAJOR})",
            c.major
        ));
    }
    if c.minor > CONTRACT_MINOR {
        return Err(format!(
            "contract {}.{} needs a newer platform (this one implements {CONTRACT_MAJOR}.{CONTRACT_MINOR})",
            c.major, c.minor
        ));
    }
    let exe = &manifest.host.executable;
    if exe.is_empty() || exe.contains(['/', '\\', ':']) || exe.starts_with('.') {
        return Err("host.executable must be a plain file name".into());
    }
    if manifest.host.timeout_s == 0 || manifest.host.timeout_s > 600 {
        return Err("host.timeout_s must be in 1 to 600".into());
    }
    if manifest.host.max_output_bytes == 0 || manifest.host.max_output_bytes > 64 * 1024 * 1024 {
        return Err("host.max_output_bytes must be in 1 to 64 MiB".into());
    }
    if manifest.seeds.min > manifest.seeds.max {
        return Err("seeds.min must not exceed seeds.max".into());
    }
    for r in &manifest.seeds.protected {
        if r.start > r.end {
            return Err("a protected seed range has start after end".into());
        }
    }
    Ok(())
}

fn load(dir: &Path) -> Result<Discovered, String> {
    let path = dir.join(MANIFEST_FILE);
    let meta = fs::metadata(&path).map_err(|e| format!("{MANIFEST_FILE}: {e}"))?;
    if meta.len() > MAX_MANIFEST_BYTES {
        return Err(format!(
            "{MANIFEST_FILE} is larger than {MAX_MANIFEST_BYTES} bytes"
        ));
    }
    let bytes = fs::read(&path).map_err(|e| format!("{MANIFEST_FILE}: {e}"))?;
    let manifest: DomainManifest =
        serde_json::from_slice(&bytes).map_err(|e| format!("{MANIFEST_FILE}: {e}"))?;
    check_manifest(&manifest)?;
    let mut executable = dir.join(&manifest.host.executable);
    // Manifests name the Windows executable; other platforms use the same name without .exe.
    if !cfg!(windows)
        && !executable.is_file()
        && let Some(stem) = manifest.host.executable.strip_suffix(".exe")
    {
        executable = dir.join(stem);
    }
    if !executable.is_file() {
        return Err(format!(
            "host executable {} is missing",
            manifest.host.executable
        ));
    }
    Ok(Discovered {
        manifest,
        dir: dir.to_path_buf(),
        executable,
    })
}

/// Scans the directories in order; the first domain with a given id wins, later ones are rejected.
pub fn discover(roots: &[PathBuf]) -> DiscoveryReport {
    let mut report = DiscoveryReport::default();
    for root in roots {
        let Ok(entries) = fs::read_dir(root) else {
            continue;
        };
        let mut dirs: Vec<PathBuf> = entries
            .filter_map(Result::ok)
            .map(|e| e.path())
            .filter(|p| p.is_dir() && p.join(MANIFEST_FILE).exists())
            .collect();
        dirs.sort();
        for dir in dirs {
            let name = dir
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            if report.domains.len() >= MAX_DOMAINS {
                report.rejected.push(Rejected {
                    dir: name,
                    reason: format!("more than {MAX_DOMAINS} domains"),
                });
                continue;
            }
            match load(&dir) {
                Ok(found) => {
                    if report
                        .domains
                        .iter()
                        .any(|d| d.manifest.id == found.manifest.id)
                    {
                        report.rejected.push(Rejected {
                            dir: name,
                            reason: format!("duplicate domain id {}", found.manifest.id),
                        });
                    } else {
                        report.domains.push(found);
                    }
                }
                Err(reason) => report.rejected.push(Rejected { dir: name, reason }),
            }
        }
    }
    report
}
