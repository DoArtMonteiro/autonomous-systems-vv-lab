//! Leitura limitada, escrita de artefactos e hashes.

use std::collections::BTreeSet;
use std::fs;
use std::io::Read;
use std::path::{Component, Path};

use sha2::{Digest, Sha256};

pub const MAX_SCENARIO_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_SMALL_JSON_BYTES: usize = 1024 * 1024;
/// Limite antes da leitura de `campaign.json`. O tamanho cresce com o orçamento e
/// com o número e o comprimento dos contratos: 128 contratos de 64 bytes, com
/// orçamento 512, chegam a cerca de 9 MB; o máximo derivado ronda 12 MB.
pub const MAX_CAMPAIGN_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_CASE_FILE_BYTES: usize = 128 * 1024 * 1024;
pub const MAX_TOTAL_OUTPUT_BYTES: usize = 512 * 1024 * 1024;

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn read_bounded(path: &Path, maximum: usize) -> Result<Vec<u8>, String> {
    let file = fs::File::open(path)
        .map_err(|error| format!("could not read {}: {error}", path.display()))?;
    let mut bytes = Vec::new();
    file.take(maximum as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| format!("could not read {}: {error}", path.display()))?;
    if bytes.len() > maximum {
        return Err(format!(
            "{} exceeds the {maximum} byte input limit",
            path.display()
        ));
    }
    Ok(bytes)
}

/// O diretório de saída tem de não existir ou estar vazio; verificado antes da geração.
pub fn check_output(directory: &Path) -> Result<(), String> {
    if directory.exists() {
        if !directory.is_dir() {
            return Err(format!("{} is not a directory", directory.display()));
        }
        let mut entries = fs::read_dir(directory)
            .map_err(|error| format!("could not list {}: {error}", directory.display()))?;
        if entries.next().is_some() {
            return Err(format!(
                "output directory {} must be empty or absent",
                directory.display()
            ));
        }
    }
    Ok(())
}

pub fn prepare_output(directory: &Path) -> Result<(), String> {
    check_output(directory)?;
    fs::create_dir_all(directory)
        .map_err(|error| format!("could not create {}: {error}", directory.display()))
}

pub fn write_files(directory: &Path, files: &[(String, Vec<u8>)]) -> Result<(), String> {
    let total: usize = files.iter().map(|(_, bytes)| bytes.len()).sum();
    if total > MAX_TOTAL_OUTPUT_BYTES {
        return Err(format!(
            "campaign output of {total} bytes exceeds the {MAX_TOTAL_OUTPUT_BYTES} byte limit"
        ));
    }
    for (relative, bytes) in files {
        let path = Path::new(relative);
        if relative.contains('\\')
            || path
                .components()
                .any(|component| !matches!(component, Component::Normal(_)))
        {
            return Err(format!("unsafe output path {relative}"));
        }
        let target = directory.join(path);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| format!("could not create {}: {error}", parent.display()))?;
        }
        fs::write(&target, bytes)
            .map_err(|error| format!("could not write {}: {error}", target.display()))?;
    }
    Ok(())
}

const MAX_LISTED_ENTRIES: usize = 4096;
const MAX_LISTED_DEPTH: usize = 8;

/// Caminhos relativos ('/') dos ficheiros regulares sob `root`, sem seguir
/// ligações simbólicas. Ligações, ficheiros especiais e excesso de entradas ou
/// de profundidade são erros.
pub fn list_files(root: &Path) -> Result<BTreeSet<String>, String> {
    fn walk(
        root: &Path,
        directory: &Path,
        depth: usize,
        files: &mut BTreeSet<String>,
        entries: &mut usize,
    ) -> Result<(), String> {
        if depth > MAX_LISTED_DEPTH {
            return Err(format!("{} is nested too deeply", directory.display()));
        }
        let listing = fs::read_dir(directory)
            .map_err(|error| format!("could not list {}: {error}", directory.display()))?;
        for entry in listing {
            let entry = entry
                .map_err(|error| format!("could not list {}: {error}", directory.display()))?;
            *entries += 1;
            if *entries > MAX_LISTED_ENTRIES {
                return Err(format!(
                    "more than {MAX_LISTED_ENTRIES} entries under the campaign directory"
                ));
            }
            let path = entry.path();
            // Em Windows, `x.` e `x ` abrem `x`: o conteúdo real nunca seria listado.
            let name = entry.file_name().to_string_lossy().into_owned();
            if name.ends_with('.') || name.ends_with(' ') || name.contains(':') {
                return Err(format!("{} has a non-canonical name", path.display()));
            }
            let kind = fs::symlink_metadata(&path)
                .map_err(|error| format!("could not inspect {}: {error}", path.display()))?
                .file_type();
            if kind.is_dir() {
                walk(root, &path, depth + 1, files, entries)?;
            } else if kind.is_file() {
                let relative = path
                    .strip_prefix(root)
                    .map_err(|error| error.to_string())?
                    .components()
                    .map(|part| part.as_os_str().to_string_lossy().into_owned())
                    .collect::<Vec<_>>()
                    .join("/");
                files.insert(relative);
            } else {
                return Err(format!("{} is a symlink or special file", path.display()));
            }
        }
        Ok(())
    }
    let mut files = BTreeSet::new();
    walk(root, root, 0, &mut files, &mut 0)?;
    Ok(files)
}

pub fn pretty_json<T: serde::Serialize>(value: &T) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}
