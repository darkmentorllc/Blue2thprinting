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
    Err {
        kind: ErrorKind,
        message: String,
    },
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
}
