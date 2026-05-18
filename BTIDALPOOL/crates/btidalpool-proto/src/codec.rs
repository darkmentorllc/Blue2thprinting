//! Frame codec: CBOR payload inside a zstd-compressed frame, with explicit
//! caps on both the compressed input size and the decompressed output size
//! to defend against zip-bomb-style denial of service.
//!
//! Frame layout (all multi-byte ints are big-endian):
//!
//! ```text
//! off  size  field
//! ---  ----  -------------------------------------------------------------
//!   0     4  MAGIC = b"BTPL"
//!   4     1  VERSION (currently 1)
//!   5     4  declared_uncompressed_len (u32) -- informational; the decoder
//!            still enforces its own cap and refuses payloads that exceed
//!            either the cap OR the declared length, so a lying header
//!            cannot trick the decoder into over-allocating.
//!   9     N  zstd-compressed CBOR bytes
//! ```
//!
//! The format is intentionally minimal: just enough to (a) identify the
//! protocol so we get clean errors if someone POSTs raw JSON to the new
//! endpoint, (b) version the wire format so we can evolve it, and (c) carry
//! the declared output size so the decoder can fail fast on obvious mismatches.

use std::io::Read;

use serde::de::DeserializeOwned;
use serde::Serialize;
use thiserror::Error;

/// 4-byte magic identifying a BTIDALPOOL wire frame.
pub const MAGIC: &[u8; 4] = b"BTPL";

/// Current wire format version. Bump on incompatible changes; the decoder
/// rejects frames with any other version so we never silently mis-parse.
pub const WIRE_VERSION: u8 = 1;

/// Fixed header size in bytes (magic + version + declared length).
pub const HEADER_LEN: usize = 4 + 1 + 4;

/// Default caps. Both sides may pass tighter caps via [`encode_with_caps`] /
/// [`decode_with_caps`], but the defaults are deliberately generous on the
/// uncompressed side (BTIDES uploads can be tens of MB of JSON) and tight on
/// the compressed side (zstd typically gets 5-20x on JSON, so a 20 MiB cap
/// here corresponds to roughly 100-400 MiB of original JSON — already well
/// above the 10-20 MiB per-upload soft limit the Python server enforced).
pub const DEFAULT_MAX_COMPRESSED: usize = 20 * 1024 * 1024;
pub const DEFAULT_MAX_UNCOMPRESSED: usize = 200 * 1024 * 1024;

/// zstd compression level. 3 is the library default and a good balance of
/// ratio vs. speed for our workload (JSON text). Raising this would help
/// ratio modestly at noticeable CPU cost on the underpowered AWS server.
pub const ZSTD_LEVEL: i32 = 3;

#[derive(Debug, Error)]
pub enum CodecError {
    #[error("frame is shorter than the {HEADER_LEN}-byte header")]
    TruncatedHeader,
    #[error("frame does not start with BTIDALPOOL magic {:?}", MAGIC)]
    BadMagic,
    #[error("unsupported wire version {got} (this build understands {WIRE_VERSION})")]
    UnsupportedVersion { got: u8 },
    #[error("compressed frame is {got} bytes, exceeds cap of {cap} bytes")]
    CompressedOversize { got: usize, cap: usize },
    #[error("header declares {declared} uncompressed bytes, exceeds cap of {cap} bytes")]
    DeclaredOversize { declared: usize, cap: usize },
    #[error("decompressed output exceeded cap of {cap} bytes (suspected zip bomb)")]
    DecompressedOversize { cap: usize },
    #[error("header declared {declared} uncompressed bytes but {actual} were produced")]
    HeaderMismatch { declared: usize, actual: usize },
    #[error("cbor decode: {0}")]
    Cbor(String),
    #[error("cbor encode: {0}")]
    CborEncode(String),
    #[error("zstd io: {0}")]
    Io(#[from] std::io::Error),
    #[error("payload too large to encode ({got} bytes, cap {cap})")]
    EncodeOversize { got: usize, cap: usize },
}

/// Encode `value` to a zstd-compressed CBOR frame using the default caps.
pub fn encode<T: Serialize>(value: &T) -> Result<Vec<u8>, CodecError> {
    encode_with_caps(value, DEFAULT_MAX_UNCOMPRESSED)
}

/// Encode with an explicit cap on uncompressed payload size. Useful for tests
/// and for callers that want to enforce a smaller-than-default upper bound on
/// a particular endpoint.
pub fn encode_with_caps<T: Serialize>(
    value: &T,
    max_uncompressed: usize,
) -> Result<Vec<u8>, CodecError> {
    let mut cbor = Vec::with_capacity(1024);
    ciborium::into_writer(value, &mut cbor)
        .map_err(|e| CodecError::CborEncode(e.to_string()))?;
    if cbor.len() > max_uncompressed {
        return Err(CodecError::EncodeOversize {
            got: cbor.len(),
            cap: max_uncompressed,
        });
    }
    let compressed = zstd::encode_all(cbor.as_slice(), ZSTD_LEVEL)?;
    let mut out = Vec::with_capacity(HEADER_LEN + compressed.len());
    out.extend_from_slice(MAGIC);
    out.push(WIRE_VERSION);
    // The cast to u32 is safe: cbor.len() <= max_uncompressed and we only
    // accept max_uncompressed <= u32::MAX (the default cap is 200 MiB).
    out.extend_from_slice(&(cbor.len() as u32).to_be_bytes());
    out.extend_from_slice(&compressed);
    Ok(out)
}

/// Decode a frame using the default caps.
pub fn decode<T: DeserializeOwned>(frame: &[u8]) -> Result<T, CodecError> {
    decode_with_caps(frame, DEFAULT_MAX_COMPRESSED, DEFAULT_MAX_UNCOMPRESSED)
}

/// Decode a frame with explicit caps. Both caps are enforced *before* any
/// allocation grows past them: the compressed-size cap is checked against
/// the frame length up front, and the decompressed-size cap is enforced by
/// a streaming decoder that aborts as soon as the running output exceeds
/// the cap. This is what makes the codec safe to point at untrusted input.
pub fn decode_with_caps<T: DeserializeOwned>(
    frame: &[u8],
    max_compressed: usize,
    max_uncompressed: usize,
) -> Result<T, CodecError> {
    if frame.len() > max_compressed {
        return Err(CodecError::CompressedOversize {
            got: frame.len(),
            cap: max_compressed,
        });
    }
    if frame.len() < HEADER_LEN {
        return Err(CodecError::TruncatedHeader);
    }
    if &frame[..4] != MAGIC {
        return Err(CodecError::BadMagic);
    }
    let version = frame[4];
    if version != WIRE_VERSION {
        return Err(CodecError::UnsupportedVersion { got: version });
    }
    let declared = u32::from_be_bytes([frame[5], frame[6], frame[7], frame[8]]) as usize;
    if declared > max_uncompressed {
        return Err(CodecError::DeclaredOversize {
            declared,
            cap: max_uncompressed,
        });
    }
    let cbor = decompress_with_limit(&frame[HEADER_LEN..], max_uncompressed)?;
    // Even though we enforced `declared <= cap` above, the header is just a
    // hint — a malicious sender could understate it. The streaming decode
    // above already capped the *actual* output, so the real defense is in
    // place. This mismatch check exists only to surface inconsistent frames
    // before they reach the CBOR layer.
    if cbor.len() != declared {
        return Err(CodecError::HeaderMismatch {
            declared,
            actual: cbor.len(),
        });
    }
    let value: T = ciborium::from_reader(&cbor[..])
        .map_err(|e| CodecError::Cbor(e.to_string()))?;
    Ok(value)
}

/// Stream zstd output through a hard cap. Returns `DecompressedOversize` the
/// moment the running output would exceed `max_output`, *before* the bytes
/// are appended — so a frame whose decompressed form is 1 GiB is rejected
/// after producing at most one chunk past the cap, not after allocating the
/// full gigabyte.
fn decompress_with_limit(
    compressed: &[u8],
    max_output: usize,
) -> Result<Vec<u8>, CodecError> {
    let mut decoder = zstd::Decoder::new(compressed)?;
    let mut out: Vec<u8> = Vec::new();
    let mut buf = [0u8; 64 * 1024];
    loop {
        let n = decoder.read(&mut buf)?;
        if n == 0 {
            break;
        }
        if out.len().saturating_add(n) > max_output {
            return Err(CodecError::DecompressedOversize { cap: max_output });
        }
        out.extend_from_slice(&buf[..n]);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::{Deserialize, Serialize};

    #[derive(Serialize, Deserialize, PartialEq, Debug)]
    struct Sample {
        name: String,
        count: u64,
        tags: Vec<String>,
    }

    fn sample() -> Sample {
        Sample {
            name: "BTIDALPOOL".to_string(),
            count: 42,
            tags: vec!["alpha".into(), "beta".into(), "gamma".into()],
        }
    }

    #[test]
    fn round_trip_preserves_value() {
        let frame = encode(&sample()).expect("encode");
        let back: Sample = decode(&frame).expect("decode");
        assert_eq!(back, sample());
    }

    #[test]
    fn frame_starts_with_magic_and_version() {
        let frame = encode(&sample()).expect("encode");
        assert_eq!(&frame[..4], MAGIC);
        assert_eq!(frame[4], WIRE_VERSION);
    }

    #[test]
    fn truncated_header_is_rejected() {
        let err = decode::<Sample>(b"BTP").unwrap_err();
        assert!(matches!(err, CodecError::TruncatedHeader));
    }

    #[test]
    fn bad_magic_is_rejected() {
        // Build a header-shaped frame with the wrong magic so we get past
        // the length check and hit the magic check specifically.
        let mut bogus = vec![0u8; HEADER_LEN + 1];
        bogus[..4].copy_from_slice(b"XXXX");
        let err = decode::<Sample>(&bogus).unwrap_err();
        assert!(matches!(err, CodecError::BadMagic));
    }

    #[test]
    fn unknown_version_is_rejected() {
        let mut frame = encode(&sample()).expect("encode");
        frame[4] = 99;
        let err = decode::<Sample>(&frame).unwrap_err();
        assert!(matches!(err, CodecError::UnsupportedVersion { got: 99 }));
    }

    #[test]
    fn compressed_size_cap_is_enforced_before_parsing() {
        let frame = encode(&sample()).expect("encode");
        // Cap below the actual frame size — should be rejected immediately.
        let err = decode_with_caps::<Sample>(&frame, frame.len() - 1, DEFAULT_MAX_UNCOMPRESSED)
            .unwrap_err();
        assert!(matches!(err, CodecError::CompressedOversize { .. }));
    }

    #[test]
    fn declared_oversize_in_header_is_rejected() {
        let mut frame = encode(&sample()).expect("encode");
        // Forge the declared length to claim a huge payload.
        let huge: u32 = 500_000_000;
        frame[5..9].copy_from_slice(&huge.to_be_bytes());
        let err = decode_with_caps::<Sample>(&frame, DEFAULT_MAX_COMPRESSED, 1024).unwrap_err();
        assert!(matches!(err, CodecError::DeclaredOversize { .. }));
    }

    #[test]
    fn header_mismatch_is_rejected() {
        let mut frame = encode(&sample()).expect("encode");
        // Claim a different (but still allowed) uncompressed length than the
        // payload actually has. The streaming decoder will read the real
        // length, and the mismatch check at the end will fire.
        let liar: u32 = 7;
        frame[5..9].copy_from_slice(&liar.to_be_bytes());
        let err = decode::<Sample>(&frame).unwrap_err();
        assert!(matches!(err, CodecError::HeaderMismatch { .. }));
    }

    /// The marquee zip-bomb test. We build a payload that compresses to a
    /// tiny frame but decompresses to a large output, then prove the decoder
    /// refuses it under a tight uncompressed cap *without* allocating the
    /// full output. The forged header is set to something the cap allows so
    /// that the `DeclaredOversize` short-circuit does not fire — we want to
    /// exercise the streaming output-size guard inside `decompress_with_limit`.
    #[test]
    fn zip_bomb_is_rejected_during_streaming_decode() {
        // 5 MiB of a single repeated byte compresses to a few KB with zstd.
        let bomb_uncompressed: Vec<u8> = vec![0u8; 5 * 1024 * 1024];
        let bomb_compressed = zstd::encode_all(bomb_uncompressed.as_slice(), ZSTD_LEVEL)
            .expect("encode bomb");
        assert!(
            bomb_compressed.len() < 64 * 1024,
            "expected the bomb's compressed form to be tiny, got {} bytes",
            bomb_compressed.len()
        );

        // Hand-build a valid-looking frame with the bomb's compressed payload.
        let mut frame = Vec::with_capacity(HEADER_LEN + bomb_compressed.len());
        frame.extend_from_slice(MAGIC);
        frame.push(WIRE_VERSION);
        // Lie about the uncompressed length: claim it's small so the
        // `DeclaredOversize` check passes and we get into the streaming
        // decoder, where the real defense lives.
        let claim: u32 = 64 * 1024;
        frame.extend_from_slice(&claim.to_be_bytes());
        frame.extend_from_slice(&bomb_compressed);

        // Cap output at 64 KiB. The streaming decoder must abort and return
        // DecompressedOversize before producing all 5 MiB.
        let err = decode_with_caps::<Sample>(&frame, DEFAULT_MAX_COMPRESSED, 64 * 1024)
            .unwrap_err();
        assert!(
            matches!(err, CodecError::DecompressedOversize { .. }),
            "expected DecompressedOversize, got: {err:?}"
        );
    }

    /// A successful decode at the boundary: payload exactly fits the cap.
    #[test]
    fn output_at_exact_cap_succeeds() {
        let payload = sample();
        let frame = encode(&payload).expect("encode");
        // Re-decode to learn the exact uncompressed length, then re-decode
        // with a cap equal to that length.
        let declared = u32::from_be_bytes([frame[5], frame[6], frame[7], frame[8]]) as usize;
        let back: Sample =
            decode_with_caps(&frame, DEFAULT_MAX_COMPRESSED, declared).expect("at cap");
        assert_eq!(back, payload);
    }
}
