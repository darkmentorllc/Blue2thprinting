//! Pure v4 request-handler logic.
//!
//! Each operation takes an authenticated user email and the trait-erased
//! dependencies, then returns a [`V4Response`]. There is no HTTP layer here
//! — that lives in `http.rs`. The split lets the test suite drive every
//! code path with plain Rust function calls.

use std::sync::Arc;
use std::time::SystemTime;

use btidalpool_proto::{
    canonical_sha1, DbValue, NativeQueryResult, QueryParams, V4Date, V4DbValue, V4DbValueKind,
    V4ErrorKind, V4NativeDevice, V4NativeQueryResult, V4NativeTable, V4Payload, V4Response, V4Time,
};

use crate::ingest::IngestSink;
use crate::native_query::{NativeQueryEngine, NativeQueryError};
use crate::query::{QueryEngine, QueryError};
use crate::resumable::ResumableStore;
use crate::state::ServerState;

/// Maximum BTIDES upload size in bytes. Matches the Python server's
/// `g_max_file_size = 10` (MB). Enforced after CBOR decode so we measure the
/// JSON body length, not the compressed envelope length (the codec already
/// caps the latter independently).
pub const MAX_UPLOAD_BYTES: usize = 10 * 1024 * 1024;

/// Dependencies passed to every handler. Constructed once at server start
/// and cloned into the handler for each request.
#[derive(Clone)]
pub struct Deps {
    pub state: ServerState,
    pub resumable: ResumableStore,
    pub ingest: Arc<dyn IngestSink>,
    pub query: Arc<dyn QueryEngine>,
    pub native_query: Arc<dyn NativeQueryEngine>,
    pub max_query_records: u32,
    pub max_native_rows: u64,
}

/// Dispatch any authenticated operation exposed by the single v4 interface.
pub fn dispatch_v4(email: &str, payload: V4Payload, deps: &Deps) -> V4Response {
    match payload {
        V4Payload::CreateSession => v4_err(
            V4ErrorKind::BadRequest,
            "create_session must use Google authentication",
            Vec::new(),
        ),
        V4Payload::Upload {
            btides_json,
            use_test_db,
        } => handle_upload(email, use_test_db, btides_json, deps),
        V4Payload::CheckHash { hash } => handle_check_hash(hash, deps),
        V4Payload::LegacyQuery {
            params,
            use_test_db,
        } => handle_query(email, use_test_db, params, deps),
        V4Payload::Manifest {
            content_sha256,
            total_size,
            chunk_sha256,
            use_test_db,
        } => map_resumable(
            email,
            deps,
            deps.resumable
                .submit_manifest(email, content_sha256, total_size, chunk_sha256, use_test_db)
                .map(|status| V4Response::Manifest {
                    upload_id: status.upload_id,
                    missing_chunks: status.missing_chunks,
                    receipt: status.receipt,
                }),
        ),
        V4Payload::PutChunk {
            upload_id,
            index,
            data,
        } => map_resumable(
            email,
            deps,
            deps.resumable
                .put_chunk(email, &upload_id, index, &data)
                .map(|result| V4Response::Chunk {
                    upload_id: result.upload_id,
                    index: result.index,
                    already_present: result.already_present,
                }),
        ),
        V4Payload::Status { upload_id } => map_resumable(
            email,
            deps,
            deps.resumable
                .status(email, &upload_id)
                .map(|status| V4Response::Status {
                    upload_id: status.upload_id,
                    missing_chunks: status.missing_chunks,
                    receipt: status.receipt,
                }),
        ),
        V4Payload::Finalize { upload_id } => map_resumable(
            email,
            deps,
            deps.resumable
                .finalize(email, &upload_id, &deps.state, deps.ingest.as_ref())
                .map(|receipt| V4Response::Finalized { receipt }),
        ),
        V4Payload::NativeQuery {
            params,
            use_test_db,
        } => handle_native_query(params, use_test_db, deps),
    }
}

fn map_resumable(
    email: &str,
    deps: &Deps,
    result: Result<V4Response, crate::resumable::ResumableError>,
) -> V4Response {
    match result {
        Ok(response) => response,
        Err(error) => {
            log_user(deps, email, &format!("resumable operation failed: {error}"));
            v4_err(error.kind(), error.to_string(), error.missing_chunks())
        }
    }
}

fn handle_native_query(params: QueryParams, use_test_db: bool, deps: &Deps) -> V4Response {
    match deps.native_query.run(
        &params,
        deps.max_query_records,
        deps.max_native_rows,
        use_test_db,
    ) {
        Ok(query) => V4Response::NativeQueryResult {
            query: map_native_query(query),
        },
        Err(error) => {
            let kind = match error {
                NativeQueryError::Empty
                | NativeQueryError::Unsupported(_)
                | NativeQueryError::BadRequest(_) => V4ErrorKind::BadRequest,
                NativeQueryError::Backend(_) => V4ErrorKind::Internal,
            };
            v4_err(kind, error.to_string(), Vec::new())
        }
    }
}

fn map_native_query(query: NativeQueryResult) -> V4NativeQueryResult {
    V4NativeQueryResult {
        devices: query
            .devices
            .into_iter()
            .map(|device| V4NativeDevice {
                bdaddr: device.bdaddr,
                tables: device
                    .tables
                    .into_iter()
                    .map(|(name, table)| {
                        (
                            name,
                            V4NativeTable {
                                columns: table.columns,
                                rows: table
                                    .rows
                                    .into_iter()
                                    .map(|row| row.into_iter().map(map_db_value).collect())
                                    .collect(),
                                truncated: table.truncated,
                            },
                        )
                    })
                    .collect(),
            })
            .collect(),
        total_rows: query.total_rows,
        row_limit: query.row_limit,
        truncated: query.truncated,
    }
}

fn map_db_value(value: DbValue) -> V4DbValue {
    let mut mapped = V4DbValue {
        kind: V4DbValueKind::Null,
        bytes: None,
        signed: None,
        unsigned: None,
        float: None,
        date: None,
        time: None,
    };
    match value {
        DbValue::Null => {}
        DbValue::Bytes(value) => {
            mapped.kind = V4DbValueKind::Bytes;
            mapped.bytes = Some(value.into());
        }
        DbValue::Signed(value) => {
            mapped.kind = V4DbValueKind::Signed;
            mapped.signed = Some(value);
        }
        DbValue::Unsigned(value) => {
            mapped.kind = V4DbValueKind::Unsigned;
            mapped.unsigned = Some(value.to_string());
        }
        DbValue::Float(value) => {
            mapped.kind = V4DbValueKind::Float;
            mapped.float = Some(value);
        }
        DbValue::Date {
            year,
            month,
            day,
            hour,
            minute,
            second,
            micros,
        } => {
            mapped.kind = V4DbValueKind::Date;
            mapped.date = Some(V4Date {
                year,
                month,
                day,
                hour,
                minute,
                second,
                micros,
            });
        }
        DbValue::Time {
            negative,
            days,
            hours,
            minutes,
            seconds,
            micros,
        } => {
            mapped.kind = V4DbValueKind::Time;
            mapped.time = Some(V4Time {
                negative,
                days,
                hours,
                minutes,
                seconds,
                micros,
            });
        }
    }
    mapped
}

fn v4_err(kind: V4ErrorKind, message: impl Into<String>, missing_chunks: Vec<u32>) -> V4Response {
    V4Response::Err {
        kind,
        message: message.into(),
        missing_chunks,
    }
}

fn handle_check_hash(hash: String, deps: &Deps) -> V4Response {
    if deps.state.has_hash(&hash) {
        v4_err(
            V4ErrorKind::DuplicateUpload,
            "A file with this exact content already exists on the server. No need to upload.",
            Vec::new(),
        )
    } else {
        V4Response::Ok {
            message: "File does not yet exist on server.".into(),
        }
    }
}

fn handle_upload(email: &str, use_test_db: bool, btides_json: Vec<u8>, deps: &Deps) -> V4Response {
    // 1) Body size cap (matches Python g_max_file_size).
    if btides_json.len() > MAX_UPLOAD_BYTES {
        return v4_err(
            V4ErrorKind::PayloadTooLarge,
            "File size too big.",
            Vec::new(),
        );
    }

    // 2) Canonical SHA1 (matches Python's sort-keys hash).
    let sha1 = match canonical_sha1(&btides_json) {
        Ok(s) => s,
        Err(e) => {
            return v4_err(
                V4ErrorKind::BadRequest,
                format!("Invalid JSON data could not be decoded: {e}"),
                Vec::new(),
            )
        }
    };

    // 3) Dedup against the on-disk pool index.
    if deps.state.has_hash(&sha1) {
        log_user(deps, email, &format!("{sha1}: duplicate upload, rejected"));
        return v4_err(
            V4ErrorKind::DuplicateUpload,
            "A file with this exact content already exists on the server. No need to upload.",
            Vec::new(),
        );
    }

    // 4) Save to pool_files/<sha1>-<email>-<ts>.json (matches Python layout
    //    so a Rust server can be dropped onto an existing AWS VM and pick
    //    up the pool that the Python server built).
    let ts = current_timestamp();
    let out_path = deps.state.build_upload_path(&sha1, email, &ts);
    if let Err(e) = std::fs::write(&out_path, &btides_json) {
        return v4_err(
            V4ErrorKind::Internal,
            format!("Could not write upload to disk: {e}"),
            Vec::new(),
        );
    }

    // 5) Hand to the ingest backend, routing to bt2 or bttest per the
    //    request's use_test_db (matches the Python server's
    //    run_btides_to_sql(use_test_db=...)). NoopIngestSink ignores it.
    if let Err(e) = deps.ingest.ingest_file(&out_path, use_test_db) {
        // Per Python server: a SQL ingest failure does NOT roll back the
        // pool_files write — the file is preserved so we can re-run ingest
        // later. We still report Internal so the client knows the row didn't
        // hit the DB.
        log_user(deps, email, &format!("{sha1}: SQL ingest failed: {e}"));
        return v4_err(
            V4ErrorKind::Internal,
            format!("Saved upload but SQL ingest failed: {e}"),
            Vec::new(),
        );
    }

    deps.state.record_hash(&sha1);
    log_user(
        deps,
        email,
        &format!("{}: File saved successfully.", out_path.display()),
    );
    V4Response::Ok {
        message: "File saved successfully.".into(),
    }
}

fn handle_query(email: &str, use_test_db: bool, params: QueryParams, deps: &Deps) -> V4Response {
    log_user(deps, email, &format!("Query: {params:?}"));
    match deps.query.run(&params, deps.max_query_records, use_test_db) {
        Ok(r) => {
            log_user(deps, email, &format!("{} records returned.", r.records));
            V4Response::QueryResult {
                records: r.records,
                btides_json: r.btides_json,
            }
        }
        Err(QueryError::Empty) => v4_err(
            V4ErrorKind::EmptyResult,
            "Query yielded empty result.",
            Vec::new(),
        ),
        Err(QueryError::Backend(s)) => v4_err(
            V4ErrorKind::Internal,
            format!("Query failed: {s}"),
            Vec::new(),
        ),
        Err(QueryError::Io(e)) => v4_err(
            V4ErrorKind::Internal,
            format!("Query IO error: {e}"),
            Vec::new(),
        ),
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
    use crate::native_query::StubNativeQueryEngine;
    use crate::query::{QueryResult, StubQueryEngine};
    use std::sync::atomic::{AtomicU32, Ordering};
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
            resumable: ResumableStore::initialize(td.path().join("v2")).unwrap(),
            ingest: Arc::new(NoopIngestSink),
            query: Arc::new(StubQueryEngine::ok(b"[1,2,3]".to_vec(), 3)),
            native_query: Arc::new(StubNativeQueryEngine::empty()),
            max_query_records: 100,
            max_native_rows: 1_000,
        };
        (deps, td)
    }

    #[test]
    fn check_hash_returns_ok_for_unknown_hash() {
        let (deps, _td) = make_deps();
        let resp = handle_check_hash("abc".into(), &deps);
        match resp {
            V4Response::Ok { message } => assert!(message.contains("does not yet exist")),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn check_hash_returns_duplicate_for_known_hash() {
        let (deps, _td) = make_deps();
        deps.state.record_hash("known-hash");
        let resp = handle_check_hash("known-hash".into(), &deps);
        match resp {
            V4Response::Err { kind, .. } => assert_eq!(kind, V4ErrorKind::DuplicateUpload),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn upload_writes_file_and_records_hash() {
        let (deps, _td) = make_deps();
        let payload = br#"[{"bdaddr":"AA:BB:CC:DD:EE:FF","bdaddr_rand":0}]"#.to_vec();
        let resp = handle_upload("alice@example.com", false, payload.clone(), &deps);
        match resp {
            V4Response::Ok { message } => assert!(message.contains("saved successfully")),
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
            V4Response::Err { kind, message, .. } => {
                assert_eq!(kind, V4ErrorKind::PayloadTooLarge);
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
            V4Response::Err { kind, .. } => assert_eq!(kind, V4ErrorKind::BadRequest),
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
            V4Response::Err { kind, .. } => assert_eq!(kind, V4ErrorKind::DuplicateUpload),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn query_returns_canned_bytes() {
        let (deps, _td) = make_deps();
        let resp = handle_query("u@e.com", false, QueryParams::default(), &deps);
        match resp {
            V4Response::QueryResult {
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
    fn query_uses_configured_record_cap() {
        struct RecordingQuery(Arc<AtomicU32>);
        impl QueryEngine for RecordingQuery {
            fn run(
                &self,
                _params: &QueryParams,
                max_records: u32,
                _use_test_db: bool,
            ) -> Result<QueryResult, QueryError> {
                self.0.store(max_records, Ordering::SeqCst);
                Ok(QueryResult {
                    btides_json: b"[1]".to_vec(),
                    records: 1,
                })
            }
        }

        let (mut deps, _td) = make_deps();
        let observed = Arc::new(AtomicU32::new(0));
        deps.query = Arc::new(RecordingQuery(observed.clone()));
        deps.max_query_records = 37;
        let response = handle_query("u@e.com", false, QueryParams::default(), &deps);
        assert!(matches!(response, V4Response::QueryResult { .. }));
        assert_eq!(observed.load(Ordering::SeqCst), 37);
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
            resumable: ResumableStore::initialize(td.path().join("v2")).unwrap(),
            ingest: Arc::new(NoopIngestSink),
            query: Arc::new(StubQueryEngine::empty()),
            native_query: Arc::new(StubNativeQueryEngine::empty()),
            max_query_records: 100,
            max_native_rows: 1_000,
        };
        let resp = handle_query("u@e.com", false, QueryParams::default(), &deps);
        match resp {
            V4Response::Err { kind, .. } => assert_eq!(kind, V4ErrorKind::EmptyResult),
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
