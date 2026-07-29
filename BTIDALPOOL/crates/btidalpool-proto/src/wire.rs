//! Wire types shared by the BTIDALPOOL server and clients.
//!
//! The protocol is a single request/response pair carried in a CBOR-encoded,
//! zstd-compressed frame (see `codec`). Every request carries the Google
//! OAuth credentials inline; the server validates them on every call exactly
//! as the Python server did.
//!
//! BTIDES payloads are carried as raw bytes (`serde_bytes::ByteBuf`) — i.e.
//! the original JSON text — rather than as a `serde_json::Value` re-encoded
//! into CBOR. This keeps a single canonical byte representation that we can
//! SHA1-hash to dedupe uploads (matching the Python behavior), validate
//! against the BTIDES schema, and feed straight into BTIDES-to-SQL without
//! a CBOR↔JSON re-serialization round trip.

use serde::{Deserialize, Serialize};
use serde_bytes::ByteBuf;
use std::collections::BTreeMap;

/// Per-request authentication fields. Embedded in every [`Envelope`]; the
/// server treats requests without valid OAuth as anonymous and rejects them.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AuthFields {
    pub token: String,
    pub refresh_token: String,
    /// Route this request to the bttest database rather than bt2. Optional
    /// on the wire — defaults to false to match the Python server's behavior
    /// of treating missing/false identically.
    #[serde(default)]
    pub use_test_db: bool,
}

/// Top-level wire request. Exactly one of these per HTTP POST body, encoded
/// via the codec in this crate.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Envelope {
    pub auth: AuthFields,
    pub payload: Payload,
}

/// The three things a client can ask the server to do, matching the three
/// `command` values the Python protocol accepted (`upload`, `check_hash`,
/// `query`). Tagged with `cmd` on the wire so a future fourth command can be
/// added without breaking older clients (they'll get an `unknown_command`
/// error from the server's `Response::Err`).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
pub enum Payload {
    /// Submit a BTIDES JSON file for ingest. `btides_json` is the file's raw
    /// UTF-8 bytes — see the module comment for why we keep it as bytes.
    Upload {
        #[serde(with = "serde_bytes")]
        btides_json: Vec<u8>,
    },
    /// Ask whether the server already has a file with this SHA1. The Python
    /// client uses this as a pre-flight to skip a full upload when the
    /// content is already on the server.
    CheckHash { hash: String },
    /// Run a Tell_Me_Everything-style query and return the matching BTIDES.
    Query { params: QueryParams },
}

/// The allow-listed subset of Tell_Me_Everything query arguments. The Python
/// server allow-lists field-by-field for security; the Rust server does the
/// same, but the allow-list is now expressed in the type system (any field
/// we don't list here simply cannot reach the server).
///
/// All fields are optional. Empty / `None` means "do not apply that filter."
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[allow(non_snake_case)]
pub struct QueryParams {
    pub bdaddr: Option<String>,
    pub NOT_bdaddr: Option<Vec<String>>,
    pub bdaddr_regex: Option<Vec<String>>,
    pub NOT_bdaddr_regex: Option<Vec<String>>,
    pub name_regex: Option<Vec<String>>,
    pub NOT_name_regex: Option<Vec<String>>,
    pub company_regex: Option<Vec<String>>,
    pub NOT_company_regex: Option<Vec<String>>,
    pub UUID_regex: Option<Vec<String>>,
    pub NOT_UUID_regex: Option<Vec<String>>,
    pub MSD_regex: Option<Vec<String>>,
    pub LL_VERSION_IND: Option<String>,
    pub LMP_VERSION_RES: Option<String>,
    pub GPS_exclude_upper_left: Option<String>,
    pub GPS_exclude_lower_right: Option<String>,
    #[serde(default)]
    pub require_GPS: bool,
    #[serde(default)]
    pub require_GATT_any: bool,
    #[serde(default)]
    pub require_GATT_values: bool,
    #[serde(default)]
    pub require_SMP: bool,
    #[serde(default)]
    pub require_SMP_legacy_pairing: bool,
    #[serde(default)]
    pub require_SDP: bool,
    #[serde(default)]
    pub require_LL_VERSION_IND: bool,
    #[serde(default)]
    pub require_LMP_VERSION_RES: bool,
}

/// Top-level wire response. The server always returns a single `Response`,
/// codec-encoded, even for error cases — there is no plain-text HTTP body
/// in the new protocol (unlike the Python server which sent `text/plain`
/// for errors). HTTP status codes are still set appropriately so HTTP-level
/// tools (load balancers, oncall dashboards) see meaningful codes.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "result", rename_all = "snake_case")]
pub enum Response {
    /// Plain-text success ack, mirrors the old `200 text/plain` responses
    /// ("File saved successfully.", "File does not yet exist on server.").
    Ok { message: String },
    /// Plain-text error, mirrors the old `4xx text/plain` responses.
    /// Status code semantics are unchanged — see [`ErrorKind`] for the
    /// mapping used by the server.
    Err { kind: ErrorKind, message: String },
    /// Result of a `Query` command — the matching BTIDES JSON as raw bytes,
    /// plus a record count for client-side display.
    QueryResult {
        records: u64,
        #[serde(with = "serde_bytes")]
        btides_json: Vec<u8>,
    },
}

/// Coarse error categories that map to HTTP status codes on the server.
/// Clients can use these to branch without parsing the human-readable
/// `message` field. Adding a new variant is backwards-incompatible; clients
/// should treat unknown values as a generic failure.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorKind {
    /// Request was malformed or missing required fields. HTTP 400.
    BadRequest,
    /// OAuth token was invalid or could not be refreshed. HTTP 401.
    Unauthorized,
    /// Caller exceeded per-IP rate limits. HTTP 429.
    RateLimited,
    /// Uploaded BTIDES file failed schema validation. HTTP 400.
    SchemaInvalid,
    /// Uploaded BTIDES is a byte-for-byte duplicate of a file already on
    /// the server. HTTP 400 (matches the Python server's choice).
    DuplicateUpload,
    /// Query returned zero records. HTTP 400 (matches the Python server).
    EmptyResult,
    /// Anything unexpected on the server side. HTTP 500.
    Internal,
}

impl ErrorKind {
    /// HTTP status code that the server returns alongside this `Err`. Kept
    /// in sync with the Python server so existing client error handling
    /// (and any external monitoring) sees the same codes.
    pub fn http_status(self) -> u16 {
        match self {
            ErrorKind::BadRequest
            | ErrorKind::SchemaInvalid
            | ErrorKind::DuplicateUpload
            | ErrorKind::EmptyResult => 400,
            ErrorKind::Unauthorized => 401,
            ErrorKind::RateLimited => 429,
            ErrorKind::Internal => 500,
        }
    }
}

/// V2 authentication is deliberately separate from [`AuthFields`]. Google
/// credentials are sent only to `create_session`; subsequent manifest,
/// chunk, status, and finalize operations carry a short-lived server token.
#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "scheme", rename_all = "snake_case")]
pub enum V2Auth {
    Google { access_token: String },
    Session { token: String },
}

/// Top-level request for BTPL v2 (`POST /v2`, frame version 2).
#[derive(Clone, Serialize, Deserialize)]
pub struct V2Envelope {
    pub auth: V2Auth,
    pub payload: V2Payload,
}

/// Resumable upload operations. Chunk order is defined by the manifest, not
/// by arrival order; `put_chunk` is safe to parallelize and replay.
#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
pub enum V2Payload {
    CreateSession,
    Manifest {
        content_sha256: String,
        total_size: u64,
        chunk_sha256: Vec<String>,
        #[serde(default)]
        use_test_db: bool,
    },
    PutChunk {
        upload_id: String,
        index: u32,
        #[serde(with = "serde_bytes")]
        data: Vec<u8>,
    },
    Status {
        upload_id: String,
    },
    Finalize {
        upload_id: String,
    },
}

/// Persisted proof that a v2 upload reached the final pool atomically.
/// Replayed finalize and manifest requests return the exact same receipt.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct UploadReceipt {
    pub receipt_id: String,
    pub upload_id: String,
    pub content_sha256: String,
    pub canonical_sha1: String,
    pub total_size: u64,
    pub completed_at_unix: u64,
    pub use_test_db: bool,
    pub deduplicated: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum V2ErrorKind {
    BadRequest,
    Unauthorized,
    SessionExpired,
    NotFound,
    Conflict,
    PayloadTooLarge,
    HashMismatch,
    RateLimited,
    ServerBusy,
    Internal,
}

impl V2ErrorKind {
    pub fn http_status(self) -> u16 {
        match self {
            Self::BadRequest => 400,
            Self::Unauthorized | Self::SessionExpired => 401,
            Self::NotFound => 404,
            Self::Conflict => 409,
            Self::PayloadTooLarge => 413,
            Self::HashMismatch => 422,
            Self::RateLimited => 429,
            Self::ServerBusy => 503,
            Self::Internal => 500,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "result", rename_all = "snake_case")]
pub enum V2Response {
    Session {
        token: String,
        expires_at_unix: u64,
    },
    Manifest {
        upload_id: String,
        missing_chunks: Vec<u32>,
        receipt: Option<UploadReceipt>,
    },
    Chunk {
        upload_id: String,
        index: u32,
        already_present: bool,
    },
    Status {
        upload_id: String,
        missing_chunks: Vec<u32>,
        receipt: Option<UploadReceipt>,
    },
    Finalized {
        receipt: UploadReceipt,
    },
    Err {
        kind: V2ErrorKind,
        message: String,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        missing_chunks: Vec<u32>,
    },
}

/// Top-level request for the native Rust query protocol (`POST /v3`, frame
/// version 3). Authentication deliberately reuses the short-lived signed
/// session issued by v2; Google credentials never need to accompany a query.
#[derive(Clone, Serialize, Deserialize)]
pub struct V3Envelope {
    pub auth: V2Auth,
    pub payload: V3Payload,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
pub enum V3Payload {
    Query {
        params: QueryParams,
        #[serde(default)]
        use_test_db: bool,
    },
}

/// Lossless representation of a MySQL cell. Byte strings stay bytes instead
/// of being coerced through UTF-8, which is necessary for several Bluetooth
/// payload columns and makes this protocol a faithful view of the unchanged
/// production schema.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", content = "value", rename_all = "snake_case")]
pub enum DbValue {
    Null,
    Bytes(#[serde(with = "serde_bytes")] Vec<u8>),
    Signed(i64),
    Unsigned(u64),
    Float(f64),
    Date {
        year: u16,
        month: u8,
        day: u8,
        hour: u8,
        minute: u8,
        second: u8,
        micros: u32,
    },
    Time {
        negative: bool,
        days: u32,
        hours: u8,
        minutes: u8,
        seconds: u8,
        micros: u32,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct NativeTable {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<DbValue>>,
    /// True when the server's global row budget cut this table short.
    #[serde(default)]
    pub truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct NativeDevice {
    pub bdaddr: String,
    /// Keyed by the exact existing MySQL table name.
    pub tables: BTreeMap<String, NativeTable>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct NativeQueryResult {
    pub devices: Vec<NativeDevice>,
    pub total_rows: u64,
    pub row_limit: u64,
    pub truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "result", rename_all = "snake_case")]
pub enum V3Response {
    QueryResult { query: NativeQueryResult },
    Err { kind: V2ErrorKind, message: String },
}

/// Authentication for the unified v4 interface. Google credentials are sent
/// only to `create_session`; all other operations carry a short-lived server
/// session token.
#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "scheme", rename_all = "snake_case")]
pub enum V4Auth {
    Google { access_token: String },
    Session { token: String },
}

/// Unified BTPL v4 request. V4 includes whole-file/check/query, resumable
/// upload, and native-query capabilities behind the single `/v4` endpoint.
#[derive(Clone, Serialize, Deserialize)]
pub struct V4Envelope {
    pub auth: V4Auth,
    pub payload: V4Payload,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
pub enum V4Payload {
    CreateSession,
    Upload {
        #[serde(with = "serde_bytes")]
        btides_json: Vec<u8>,
        #[serde(default)]
        use_test_db: bool,
    },
    CheckHash {
        hash: String,
    },
    LegacyQuery {
        params: QueryParams,
        #[serde(default)]
        use_test_db: bool,
    },
    Manifest {
        content_sha256: String,
        total_size: u64,
        chunk_sha256: Vec<String>,
        #[serde(default)]
        use_test_db: bool,
    },
    PutChunk {
        upload_id: String,
        index: u32,
        #[serde(with = "serde_bytes")]
        data: Vec<u8>,
    },
    Status {
        upload_id: String,
    },
    Finalize {
        upload_id: String,
    },
    NativeQuery {
        params: QueryParams,
        #[serde(default)]
        use_test_db: bool,
    },
}

/// V4's error space is the union of the permanent/transient outcomes exposed
/// by v1, v2, and v3.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum V4ErrorKind {
    BadRequest,
    Unauthorized,
    SessionExpired,
    NotFound,
    Conflict,
    PayloadTooLarge,
    HashMismatch,
    SchemaInvalid,
    DuplicateUpload,
    EmptyResult,
    RateLimited,
    ServerBusy,
    Internal,
}

impl V4ErrorKind {
    pub fn http_status(self) -> u16 {
        match self {
            Self::BadRequest | Self::SchemaInvalid | Self::DuplicateUpload | Self::EmptyResult => {
                400
            }
            Self::Unauthorized | Self::SessionExpired => 401,
            Self::NotFound => 404,
            Self::Conflict => 409,
            Self::PayloadTooLarge => 413,
            Self::HashMismatch => 422,
            Self::RateLimited => 429,
            Self::ServerBusy => 503,
            Self::Internal => 500,
        }
    }
}

/// Android-friendly, lossless v4 representation of a MySQL cell. Unlike
/// v3's internally-tagged enum, every possible value has a stable field,
/// which keeps CBOR decoding straightforward in clients without weakening
/// the type information.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum V4DbValueKind {
    Null,
    Bytes,
    Signed,
    Unsigned,
    Float,
    Date,
    Time,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct V4Date {
    pub year: u16,
    pub month: u8,
    pub day: u8,
    pub hour: u8,
    pub minute: u8,
    pub second: u8,
    pub micros: u32,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct V4Time {
    pub negative: bool,
    pub days: u32,
    pub hours: u8,
    pub minutes: u8,
    pub seconds: u8,
    pub micros: u32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct V4DbValue {
    pub kind: V4DbValueKind,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bytes: Option<ByteBuf>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signed: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    /// Decimal text preserves the full MySQL unsigned 64-bit range in
    /// clients whose native integer type is signed (including Kotlin/JVM).
    pub unsigned: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub float: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub date: Option<V4Date>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub time: Option<V4Time>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct V4NativeTable {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<V4DbValue>>,
    #[serde(default)]
    pub truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct V4NativeDevice {
    pub bdaddr: String,
    pub tables: BTreeMap<String, V4NativeTable>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct V4NativeQueryResult {
    pub devices: Vec<V4NativeDevice>,
    pub total_rows: u64,
    pub row_limit: u64,
    pub truncated: bool,
}

/// One response type covers every v1/v2/v3 success shape. Native query data
/// uses an equally lossless, field-stable representation for simple decoding
/// in Android and other non-Rust clients.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "result", rename_all = "snake_case")]
pub enum V4Response {
    Session {
        token: String,
        expires_at_unix: u64,
    },
    Ok {
        message: String,
    },
    Manifest {
        upload_id: String,
        missing_chunks: Vec<u32>,
        receipt: Option<UploadReceipt>,
    },
    Chunk {
        upload_id: String,
        index: u32,
        already_present: bool,
    },
    Status {
        upload_id: String,
        missing_chunks: Vec<u32>,
        receipt: Option<UploadReceipt>,
    },
    Finalized {
        receipt: UploadReceipt,
    },
    QueryResult {
        records: u64,
        #[serde(with = "serde_bytes")]
        btides_json: Vec<u8>,
    },
    NativeQueryResult {
        query: V4NativeQueryResult,
    },
    Err {
        kind: V4ErrorKind,
        message: String,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        missing_chunks: Vec<u32>,
    },
}

/// Helper: serialize an [`Envelope`] using a `ByteBuf` instead of a raw
/// `Vec<u8>` for the BTIDES payload, when the caller already has a
/// `ByteBuf`. Avoids an unnecessary clone in the upload hot path.
#[allow(dead_code)]
pub(crate) fn _bytebuf_lives_here(_: ByteBuf) {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codec;

    fn auth() -> AuthFields {
        AuthFields {
            token: "t".into(),
            refresh_token: "rt".into(),
            use_test_db: true,
        }
    }

    #[test]
    fn envelope_round_trips_through_codec() {
        let env = Envelope {
            auth: auth(),
            payload: Payload::Upload {
                btides_json: br#"[{"bdaddr":"AA:BB:CC:DD:EE:FF","bdaddr_rand":0}]"#.to_vec(),
            },
        };
        let frame = codec::encode(&env).expect("encode");
        let back: Envelope = codec::decode(&frame).expect("decode");
        match (env.payload, back.payload) {
            (Payload::Upload { btides_json: a }, Payload::Upload { btides_json: b }) => {
                assert_eq!(a, b);
            }
            _ => panic!("payload variant changed across round trip"),
        }
        assert_eq!(back.auth.token, "t");
        assert_eq!(back.auth.refresh_token, "rt");
        assert!(back.auth.use_test_db);
    }

    #[test]
    fn query_params_default_is_all_none_or_false() {
        let q = QueryParams::default();
        assert!(q.bdaddr.is_none());
        assert!(q.bdaddr_regex.is_none());
        assert!(!q.require_GPS);
        assert!(!q.require_GATT_any);
    }

    #[test]
    fn response_query_result_round_trips() {
        let resp = Response::QueryResult {
            records: 3,
            btides_json: b"[]".to_vec(),
        };
        let frame = codec::encode(&resp).expect("encode");
        let back: Response = codec::decode(&frame).expect("decode");
        match back {
            Response::QueryResult {
                records,
                btides_json,
            } => {
                assert_eq!(records, 3);
                assert_eq!(btides_json, b"[]");
            }
            _ => panic!("variant changed across round trip"),
        }
    }

    #[test]
    fn error_kind_http_status_matches_python_server() {
        // These mappings are load-bearing for backwards compat with any
        // client that branches on HTTP status (the existing Python client
        // does, for 400 and 429 specifically).
        assert_eq!(ErrorKind::BadRequest.http_status(), 400);
        assert_eq!(ErrorKind::SchemaInvalid.http_status(), 400);
        assert_eq!(ErrorKind::DuplicateUpload.http_status(), 400);
        assert_eq!(ErrorKind::EmptyResult.http_status(), 400);
        assert_eq!(ErrorKind::Unauthorized.http_status(), 401);
        assert_eq!(ErrorKind::RateLimited.http_status(), 429);
        assert_eq!(ErrorKind::Internal.http_status(), 500);
    }

    #[test]
    fn v2_envelope_and_receipt_round_trip() {
        let env = V2Envelope {
            auth: V2Auth::Session { token: "s".into() },
            payload: V2Payload::Manifest {
                content_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    .into(),
                total_size: 2,
                chunk_sha256: vec![
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
                ],
                use_test_db: false,
            },
        };
        let frame = codec::encode_v2(&env).unwrap();
        let decoded: V2Envelope = codec::decode_v2(&frame).unwrap();
        assert!(matches!(decoded.payload, V2Payload::Manifest { .. }));
    }

    #[test]
    fn v3_native_query_round_trip_preserves_binary_cells() {
        let response = V3Response::QueryResult {
            query: NativeQueryResult {
                devices: vec![NativeDevice {
                    bdaddr: "aa:bb:cc:dd:ee:ff".into(),
                    tables: BTreeMap::from([(
                        "LE_bdaddr_to_MSD".into(),
                        NativeTable {
                            columns: vec!["manufacturer_specific_data".into()],
                            rows: vec![vec![DbValue::Bytes(vec![0, 0xff, 1])]],
                            truncated: false,
                        },
                    )]),
                }],
                total_rows: 1,
                row_limit: 100,
                truncated: false,
            },
        };
        let frame = codec::encode_v3(&response).unwrap();
        let decoded: V3Response = codec::decode_v3(&frame).unwrap();
        assert_eq!(decoded, response);
    }

    #[test]
    fn v4_unified_round_trip_preserves_resumable_and_native_shapes() {
        let manifest = V4Envelope {
            auth: V4Auth::Session { token: "s".into() },
            payload: V4Payload::Manifest {
                content_sha256: "ab".repeat(32),
                total_size: 7,
                chunk_sha256: vec!["cd".repeat(32)],
                use_test_db: true,
            },
        };
        let frame = codec::encode_v4(&manifest).unwrap();
        assert_eq!(frame[4], codec::V4_WIRE_VERSION);
        let decoded: V4Envelope = codec::decode_v4(&frame).unwrap();
        assert!(matches!(
            decoded.payload,
            V4Payload::Manifest {
                total_size: 7,
                use_test_db: true,
                ..
            }
        ));

        let response = V4Response::NativeQueryResult {
            query: V4NativeQueryResult {
                devices: Vec::new(),
                total_rows: 0,
                row_limit: 100,
                truncated: false,
            },
        };
        let frame = codec::encode_v4(&response).unwrap();
        let decoded: V4Response = codec::decode_v4(&frame).unwrap();
        assert_eq!(decoded, response);
    }
}
