//! SHA1 hash of a BTIDES JSON payload, computed in the *same* canonical form
//! the Python tools use so the hash matches what the Python server
//! already has on disk during the Rust-vs-Python coexistence period.
//!
//! Canonical form: `json.dumps(json_content, sort_keys=True)` in Python.
//! Re-implemented here by parsing into a `serde_json::Value`, re-serializing
//! with sorted keys, and SHA1-ing the result.
//!
//! Note: `serde_json` with the `preserve_order` feature normally keeps key
//! insertion order; for the canonical hash we deliberately *don't* want that,
//! so we build a recursive sorter via `BTreeMap` instead of relying on the
//! crate feature.

use sha1::{Digest, Sha1};

use serde_json::Value;
use std::collections::BTreeMap;

/// Compute the hex-encoded SHA1 of a BTIDES JSON payload, using the same
/// canonical (sort-keys) serialization that `Analysis/BTIDES_to_BTIDALPOOL.py`
/// and `Analysis/Server_BTIDALPOOL.py` use to dedupe uploads. The output is
/// 40 lowercase hex characters.
pub fn canonical_sha1(json_bytes: &[u8]) -> Result<String, serde_json::Error> {
    let value: Value = serde_json::from_slice(json_bytes)?;
    let canonical = sort_keys(&value);
    let bytes = serde_json::to_vec(&canonical)?;
    let mut hasher = Sha1::new();
    hasher.update(&bytes);
    Ok(hex::encode(hasher.finalize()))
}

/// Recursively rebuild a `Value` with all object keys in lexicographic
/// order. Arrays and scalars are passed through unchanged.
fn sort_keys(v: &Value) -> Value {
    match v {
        Value::Object(map) => {
            let mut sorted: BTreeMap<String, Value> = BTreeMap::new();
            for (k, vv) in map {
                sorted.insert(k.clone(), sort_keys(vv));
            }
            // Convert BTreeMap back into a serde_json::Map to preserve the
            // ordering through downstream serialization. serde_json::Map
            // built from a BTreeMap iteration yields sorted insertion.
            let mut out = serde_json::Map::with_capacity(sorted.len());
            for (k, vv) in sorted {
                out.insert(k, vv);
            }
            Value::Object(out)
        }
        Value::Array(arr) => Value::Array(arr.iter().map(sort_keys).collect()),
        _ => v.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_array_hash_matches_python() {
        // Computed via `python3 -c "import hashlib,json;print(hashlib.sha1(json.dumps([],sort_keys=True).encode()).hexdigest())"`
        // which yields the well-known SHA1 of the literal "[]".
        let h = canonical_sha1(b"[]").expect("hash");
        assert_eq!(h, "97d170e1550eee4afc0af065b78cda302a97674c");
    }

    #[test]
    fn key_order_does_not_affect_hash() {
        let a = canonical_sha1(br#"{"a":1,"b":2}"#).expect("hash a");
        let b = canonical_sha1(br#"{"b":2,"a":1}"#).expect("hash b");
        assert_eq!(a, b);
    }

    #[test]
    fn nested_key_order_does_not_affect_hash() {
        let a = canonical_sha1(br#"{"k":{"x":1,"y":2}}"#).expect("hash a");
        let b = canonical_sha1(br#"{"k":{"y":2,"x":1}}"#).expect("hash b");
        assert_eq!(a, b);
    }

    #[test]
    fn whitespace_does_not_affect_hash() {
        let a = canonical_sha1(br#"{"a":1,"b":[2,3]}"#).expect("hash a");
        let b = canonical_sha1(b"{\n  \"a\" : 1 ,\n  \"b\" : [ 2 , 3 ]\n}").expect("hash b");
        assert_eq!(a, b);
    }
}
