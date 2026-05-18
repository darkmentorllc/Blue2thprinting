//! Pure request-handler logic.
//!
//! Each `handle_*` function takes an authenticated user email, the typed
//! [`Payload`] for that command, and the trait-erased dependencies, and
//! returns a [`Response`]. There is no HTTP layer here — that lives in
//! `http.rs`. The split lets the test suite drive every code path with
//! plain Rust function calls.

use std::sync::Arc;
use std::time::SystemTime;

use btidalpool_proto::{canonical_sha1, ErrorKind, Payload, QueryParams, Response};

use crate::ingest::IngestSink;
use crate::query::{QueryEngine, QueryError};
use crate::state::ServerState;

/// Maximum BTIDES upload size in bytes. Matches the Python server's
/// `g_max_file_size = 10` (MB). Enforced after CBOR decode so we measure the
/// JSON body length, not the compressed envelope length (the codec already
/// caps the latter independently).
pub const MAX_UPLOAD_BYTES: usize = 10 * 1024 * 1024;

/// Maximum records returned per query. Matches the Python server's
/// `g_max_returned_records_per_query`.
pub const MAX_RECORDS_PER_QUERY: u32 = 100;

/// Dependencies passed to every handler. Constructed once at server start
/// and cloned into the handler for each request.
#[derive(Clone)]
pub struct Deps {
    pub state: ServerState,
    pub ingest: Arc<dyn IngestSink>,
    pub query: Arc<dyn QueryEngine>,
}

/// Dispatch a successfully-decoded envelope payload to the right handler.
/// `email` is the result of OAuth validation — by the time we get here we
/// know the caller is a real authenticated user.
pub fn dispatch(
    email: &str,
    use_test_db: bool,
    payload: Payload,
    deps: &Deps,
) -> Response {
    match payload {
        Payload::Upload { btides_json } => handle_upload(email, use_test_db, btides_json, deps),
        Payload::CheckHash { hash } => handle_check_hash(email, hash, deps),
        Payload::Query { params } => handle_query(email, use_test_db, params, deps),
    }
}

fn handle_check_hash(email: &str, hash: String, deps: &Deps) -> Response {
    let _ = email; // logged at the HTTP layer
    if deps.state.has_hash(&hash) {
        Response::Err {
            kind: ErrorKind::DuplicateUpload,
            message: "A file with this exact content already exists on the server. No need to upload.".into(),
        }
    } else {
        Response::Ok {
            message: "File does not yet exist on server.".into(),
        }
    }
}

fn handle_upload(
    email: &str,
    use_test_db: bool,
    btides_json: Vec<u8>,
    deps: &Deps,
) -> Response {
    // 1) Body size cap (matches Python g_max_file_size).
    if btides_json.len() > MAX_UPLOAD_BYTES {
        return err(ErrorKind::BadRequest, "File size too big.");
    }

    // 2) Canonical SHA1 (matches Python's sort-keys hash).
    let sha1 = match canonical_sha1(&btides_json) {
        Ok(s) => s,
        Err(e) => {
            return err(
                ErrorKind::BadRequest,
                format!("Invalid JSON data could not be decoded: {e}"),
            )
        }
    };

    // 3) Dedup against the on-disk pool index.
    if deps.state.has_hash(&sha1) {
        log_user(deps, email, &format!("{sha1}: duplicate upload, rejected"));
        return err(
            ErrorKind::DuplicateUpload,
            "A file with this exact content already exists on the server. No need to upload.",
        );
    }

    // 4) Save to pool_files/<sha1>-<email>-<ts>.json (matches Python layout
    //    so a Rust server can be dropped onto an existing AWS VM and pick
    //    up the pool that the Python server built).
    let ts = current_timestamp();
    let out_path = deps.state.build_upload_path(&sha1, email, &ts);
    if let Err(e) = std::fs::write(&out_path, &btides_json) {
        return err(
            ErrorKind::Internal,
            format!("Could not write upload to disk: {e}"),
        );
    }

    // 5) Hand to the ingest backend. Skipped on the test build (NoopIngestSink).
    let _ = use_test_db; // The backend already knows which DB; the flag is
                         // present in the envelope so callers can override
                         // per-request when a future backend supports it.
    if let Err(e) = deps.ingest.ingest_file(&out_path) {
        // Per Python server: a SQL ingest failure does NOT roll back the
        // pool_files write — the file is preserved so we can re-run ingest
        // later. We still report Internal so the client knows the row didn't
        // hit the DB.
        log_user(deps, email, &format!("{sha1}: SQL ingest failed: {e}"));
        return err(
            ErrorKind::Internal,
            format!("Saved upload but SQL ingest failed: {e}"),
        );
    }

    deps.state.record_hash(&sha1);
    log_user(
        deps,
        email,
        &format!("{}: File saved successfully.", out_path.display()),
    );
    Response::Ok {
        message: "File saved successfully.".into(),
    }
}

fn handle_query(
    email: &str,
    use_test_db: bool,
    params: QueryParams,
    deps: &Deps,
) -> Response {
    log_user(deps, email, &format!("Query: {params:?}"));
    match deps.query.run(&params, MAX_RECORDS_PER_QUERY, use_test_db) {
        Ok(r) => {
            log_user(deps, email, &format!("{} records returned.", r.records));
            Response::QueryResult {
                records: r.records,
                btides_json: r.btides_json,
            }
        }
        Err(QueryError::Empty) => err(ErrorKind::EmptyResult, "Query yielded empty result."),
        Err(QueryError::Backend(s)) => err(ErrorKind::Internal, format!("Query failed: {s}")),
        Err(QueryError::Io(e)) => err(ErrorKind::Internal, format!("Query IO error: {e}")),
    }
}

fn err(kind: ErrorKind, message: impl Into<String>) -> Response {
    Response::Err {
        kind,
        message: message.into(),
    }
}

fn log_user(deps: &Deps, email: &str, msg: &str) {
    let line = format!("{}: {}: {}", iso_now(), email, msg);
    let _ = deps.state.append_user_log(email, line);
}

/// `YYYY-MM-DD-HH-MM-SS` in local time. Matches the Python server's
/// `datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')` so files written
/// by either implementation are visually indistinguishable.
fn current_timestamp() -> String {
    // We deliberately don't pull in `chrono` for one format string. The
    // POSIX `localtime_r` route is overkill here; a UTC-ish format derived
    // from SystemTime is fine because the filename only needs to be
    // human-sortable, not display the user's local clock perfectly.
    let secs = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // Compute Y/M/D/h/m/s from a Unix timestamp, no leap seconds. Good
    // enough for filenames.
    let (y, mo, d, h, mi, s) = ymd_hms_from_unix(secs as i64);
    format!("{y:04}-{mo:02}-{d:02}-{h:02}-{mi:02}-{s:02}")
}

/// ISO-8601 timestamp for log lines: matches Python's
/// `datetime.datetime.now().isoformat()` precision down to seconds.
fn iso_now() -> String {
    let secs = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let (y, mo, d, h, mi, s) = ymd_hms_from_unix(secs as i64);
    format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}")
}

/// Convert a Unix timestamp (UTC seconds since epoch) to a (y, m, d, h, m, s)
/// tuple. Algorithm from Howard Hinnant's "date" library, transliterated to
/// avoid bringing in chrono / time for a single format string.
pub(crate) fn ymd_hms_from_unix(ts: i64) -> (i32, u32, u32, u32, u32, u32) {
    let secs_per_day: i64 = 86_400;
    let mut days = ts.div_euclid(secs_per_day);
    let secs_in_day = ts.rem_euclid(secs_per_day);
    days += 719_468;
    let era = if days >= 0 { days } else { days - 146_096 } / 146_097;
    let doe = (days - era * 146_097) as u64; // [0, 146097)
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146_096) / 365; // [0, 399]
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); // [0, 365]
    let mp = (5 * doy + 2) / 153; // [0, 11]
    let d = doy - (153 * mp + 2) / 5 + 1; // [1, 31]
    let m = if mp < 10 { mp + 3 } else { mp - 9 }; // [1, 12]
    let y = if m <= 2 { y + 1 } else { y };
    let h = (secs_in_day / 3600) as u32;
    let mi = ((secs_in_day / 60) % 60) as u32;
    let s = (secs_in_day % 60) as u32;
    (y as i32, m as u32, d as u32, h, mi, s)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ingest::NoopIngestSink;
    use crate::query::StubQueryEngine;
    use tempfile::tempdir;

    fn make_deps() -> (Deps, tempfile::TempDir) {
        let td = tempdir().unwrap();
        let state = ServerState::initialize(
            td.path().join("pool"),
            td.path().join("ul"),
            td.path().join("ac"),
        )
        .unwrap();
        let deps = Deps {
            state,
            ingest: Arc::new(NoopIngestSink),
            query: Arc::new(StubQueryEngine::ok(b"[1,2,3]".to_vec(), 3)),
        };
        (deps, td)
    }

    #[test]
    fn check_hash_returns_ok_for_unknown_hash() {
        let (deps, _td) = make_deps();
        let resp = handle_check_hash("u@e.com", "abc".into(), &deps);
        match resp {
            Response::Ok { message } => assert!(message.contains("does not yet exist")),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn check_hash_returns_duplicate_for_known_hash() {
        let (deps, _td) = make_deps();
        deps.state.record_hash("known-hash");
        let resp = handle_check_hash("u@e.com", "known-hash".into(), &deps);
        match resp {
            Response::Err { kind, .. } => assert_eq!(kind, ErrorKind::DuplicateUpload),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn upload_writes_file_and_records_hash() {
        let (deps, _td) = make_deps();
        let payload = br#"[{"bdaddr":"AA:BB:CC:DD:EE:FF","bdaddr_rand":0}]"#.to_vec();
        let resp = handle_upload("alice@example.com", false, payload.clone(), &deps);
        match resp {
            Response::Ok { message } => assert!(message.contains("saved successfully")),
            other => panic!("wrong variant: {other:?}"),
        }
        let hash = canonical_sha1(&payload).unwrap();
        assert!(deps.state.has_hash(&hash));
        // File on disk:
        let mut found = false;
        for entry in std::fs::read_dir(deps.state.pool_dir()).unwrap() {
            let entry = entry.unwrap();
            if entry.file_name().to_string_lossy().starts_with(&hash) {
                found = true;
            }
        }
        assert!(found, "upload should have written a pool file");
    }

    #[test]
    fn upload_rejects_oversize_payload() {
        let (deps, _td) = make_deps();
        let huge = vec![b'a'; MAX_UPLOAD_BYTES + 1];
        let resp = handle_upload("alice@example.com", false, huge, &deps);
        match resp {
            Response::Err { kind, message } => {
                assert_eq!(kind, ErrorKind::BadRequest);
                assert!(message.contains("too big"));
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn upload_rejects_invalid_json() {
        let (deps, _td) = make_deps();
        let resp = handle_upload("alice@example.com", false, b"not json".to_vec(), &deps);
        match resp {
            Response::Err { kind, .. } => assert_eq!(kind, ErrorKind::BadRequest),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn upload_rejects_duplicate() {
        let (deps, _td) = make_deps();
        let payload = br#"[1]"#.to_vec();
        // First upload should succeed.
        let _ = handle_upload("u@e.com", false, payload.clone(), &deps);
        // Second should be DuplicateUpload.
        let resp = handle_upload("u@e.com", false, payload, &deps);
        match resp {
            Response::Err { kind, .. } => assert_eq!(kind, ErrorKind::DuplicateUpload),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn query_returns_canned_bytes() {
        let (deps, _td) = make_deps();
        let resp = handle_query("u@e.com", false, QueryParams::default(), &deps);
        match resp {
            Response::QueryResult {
                records,
                btides_json,
            } => {
                assert_eq!(records, 3);
                assert_eq!(btides_json, b"[1,2,3]");
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn query_empty_returns_empty_error_kind() {
        let td = tempdir().unwrap();
        let state = ServerState::initialize(
            td.path().join("pool"),
            td.path().join("ul"),
            td.path().join("ac"),
        )
        .unwrap();
        let deps = Deps {
            state,
            ingest: Arc::new(NoopIngestSink),
            query: Arc::new(StubQueryEngine::empty()),
        };
        let resp = handle_query("u@e.com", false, QueryParams::default(), &deps);
        match resp {
            Response::Err { kind, .. } => assert_eq!(kind, ErrorKind::EmptyResult),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn timestamp_format_matches_python_strftime() {
        let s = current_timestamp();
        // YYYY-MM-DD-HH-MM-SS
        assert_eq!(s.len(), 19);
        assert_eq!(s.chars().filter(|c| *c == '-').count(), 5);
        assert!(s.chars().all(|c| c.is_ascii_digit() || c == '-'));
    }

    #[test]
    fn iso_now_format_matches_python_isoformat() {
        let s = iso_now();
        // YYYY-MM-DDTHH:MM:SS
        assert_eq!(s.len(), 19);
        assert!(s.contains('T'));
    }
}
