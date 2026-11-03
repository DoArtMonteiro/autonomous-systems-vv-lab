//! Canonical JSON and hashing. Keys are sorted (serde_json maps are BTreeMap without the
//! `preserve_order` feature), no whitespace, so equal values hash equally on every platform.

use serde::Serialize;
use sha2::{Digest, Sha256};

pub fn canonical_bytes<T: Serialize>(value: &T) -> Vec<u8> {
    // Round-trip through Value so struct field order never matters, only names.
    let value = serde_json::to_value(value).expect("serialisable value");
    serde_json::to_vec(&value).expect("serialisable value")
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Pretty JSON with a trailing newline, the on-disk format of every platform artifact.
pub fn pretty_bytes<T: Serialize>(value: &T) -> Vec<u8> {
    let value = serde_json::to_value(value).expect("serialisable value");
    let mut bytes = serde_json::to_vec_pretty(&value).expect("serialisable value");
    bytes.push(b'\n');
    bytes
}
