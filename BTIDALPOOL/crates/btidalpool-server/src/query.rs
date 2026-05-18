//! Tell_Me_Everything query path behind a trait.
//!
//! Production code uses [`SubprocessQueryEngine`], which spawns the
//! existing `Analysis/Tell_Me_Everything.py` with the allow-listed flags
//! and reads the JSON it writes to its `--output` file — exactly the same
//! shell-out the Python server does today.
//!
//! Tests use [`StubQueryEngine`], which returns canned bytes without
//! invoking Python, MySQL, or the filesystem-output dance.

use std::path::{Path, PathBuf};
use std::process::Command;

use btidalpool_proto::QueryParams;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum QueryError {
    #[error("query engine produced no records")]
    Empty,
    #[error("backend error: {0}")]
    Backend(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
}

/// Output of a successful query: the JSON bytes that will be wrapped into a
/// `Response::QueryResult` envelope, plus a record count for the access log.
#[derive(Debug)]
pub struct QueryResult {
    pub btides_json: Vec<u8>,
    pub records: u64,
}

/// What every query engine must do: given the allow-listed params and a
/// max-records cap, produce a JSON byte blob (the same format the existing
/// Python server returns) or fail with a structured error.
pub trait QueryEngine: Send + Sync {
    fn run(
        &self,
        params: &QueryParams,
        max_records: u32,
        use_test_db: bool,
    ) -> Result<QueryResult, QueryError>;
}

/// Production engine: spawns `python3 Tell_Me_Everything.py …` with the
/// allow-listed flags and an `--output <tmpfile>` then reads the tmpfile.
/// This is intentionally a thin wrapper over the existing Python so we
/// don't have to reimplement the entire query layer in Rust at the same
/// time as the wire protocol — that can come later.
pub struct SubprocessQueryEngine {
    /// Path to `python3`. Override via `--python` on the CLI if the system
    /// `python3` isn't in PATH.
    pub python: PathBuf,
    /// Path to `Analysis/Tell_Me_Everything.py`. The Python server CWDs
    /// itself into Analysis/; we do the same here.
    pub script: PathBuf,
    /// Working directory for the subprocess. Should be the `Analysis/`
    /// directory so the script can find its sibling modules + BTIDES_Schema.
    pub cwd: PathBuf,
}

impl QueryEngine for SubprocessQueryEngine {
    fn run(
        &self,
        params: &QueryParams,
        max_records: u32,
        use_test_db: bool,
    ) -> Result<QueryResult, QueryError> {
        let tmpdir = std::env::temp_dir();
        let stem = format!(
            "btidalpool-query-{}-{}.json",
            std::process::id(),
            // Microsecond-ish: nanos-since-unix-epoch in hex. Doesn't need
            // to be unguessable — only unique within the temp dir for the
            // duration of the call.
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        );
        let out_path = tmpdir.join(stem);

        let mut args: Vec<String> = vec![
            self.script.to_string_lossy().into_owned(),
            "--max-records-output".into(),
            max_records.to_string(),
            "--quiet-print".into(),
            "--output".into(),
            out_path.to_string_lossy().into_owned(),
        ];
        if use_test_db {
            args.push("--use-test-db".into());
        }
        append_query_flags(&mut args, params);

        let status = Command::new(&self.python)
            .args(&args)
            .current_dir(&self.cwd)
            .status()
            .map_err(|e| QueryError::Backend(format!("spawn python3: {e}")))?;
        if !status.success() {
            // Clean up the (possibly partial) output file before bailing.
            let _ = std::fs::remove_file(&out_path);
            return Err(QueryError::Backend(format!(
                "python subprocess exited with status {status}"
            )));
        }

        let bytes = std::fs::read(&out_path)?;
        let _ = std::fs::remove_file(&out_path);
        if bytes == b"[]" || bytes.is_empty() {
            return Err(QueryError::Empty);
        }
        // Count top-level array elements to populate the access log. We
        // don't fully parse the JSON here — `serde_json::from_slice::<Value>`
        // would be wasteful for what's just a logging metric.
        let records = count_top_level_array(&bytes) as u64;
        Ok(QueryResult {
            btides_json: bytes,
            records,
        })
    }
}

/// Reproduces the if-let cascade in the Python server's `handle_query`,
/// keeping the same flag spellings so any wrapper script someone wrote
/// against the old subprocess args keeps working.
fn append_query_flags(args: &mut Vec<String>, p: &QueryParams) {
    if let Some(v) = &p.bdaddr {
        args.push("--bdaddr".into());
        args.push(v.clone());
    }
    if let Some(vs) = &p.NOT_bdaddr {
        for v in vs {
            args.push("--NOT-bdaddr".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.bdaddr_regex {
        for v in vs {
            args.push("--bdaddr-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.NOT_bdaddr_regex {
        for v in vs {
            args.push("--NOT-bdaddr-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.name_regex {
        for v in vs {
            args.push("--name-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.NOT_name_regex {
        for v in vs {
            args.push("--NOT-name-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.company_regex {
        for v in vs {
            args.push("--company-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.NOT_company_regex {
        for v in vs {
            args.push("--NOT-company-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.UUID_regex {
        for v in vs {
            args.push("--UUID-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.NOT_UUID_regex {
        for v in vs {
            args.push("--NOT-UUID-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(vs) = &p.MSD_regex {
        for v in vs {
            args.push("--MSD-regex".into());
            args.push(v.clone());
        }
    }
    if let Some(v) = &p.LL_VERSION_IND {
        args.push("--LL_VERSION_IND".into());
        args.push(v.clone());
    }
    if let Some(v) = &p.LMP_VERSION_RES {
        args.push("--LMP_VERSION_RES".into());
        args.push(v.clone());
    }
    if let Some(v) = &p.GPS_exclude_upper_left {
        args.push("--GPS-exclude-upper-left".into());
        args.push(v.clone());
    }
    if let Some(v) = &p.GPS_exclude_lower_right {
        args.push("--GPS-exclude-lower-right".into());
        args.push(v.clone());
    }
    if p.require_GPS {
        args.push("--require-GPS".into());
    }
    if p.require_GATT_any {
        args.push("--require-GATT-any".into());
    }
    if p.require_GATT_values {
        args.push("--require-GATT-values".into());
    }
    if p.require_SMP {
        args.push("--require-SMP".into());
    }
    if p.require_SMP_legacy_pairing {
        args.push("--require-SMP-legacy-pairing".into());
    }
    if p.require_SDP {
        args.push("--require-SDP".into());
    }
    if p.require_LL_VERSION_IND {
        args.push("--require-LL_VERSION_IND".into());
    }
    if p.require_LMP_VERSION_RES {
        args.push("--require-LMP_VERSION_RES".into());
    }
}

/// Count the top-level elements of a JSON array. We deliberately don't
/// fully parse — for a 10 MB result that would burn cycles for no reason.
/// We do a single pass tracking quote/escape/depth state, treating `,` at
/// depth 1 (i.e. just inside the outer `[`) as a separator.
fn count_top_level_array(bytes: &[u8]) -> usize {
    let mut iter = bytes.iter().copied().peekable();
    while iter.peek().map(|b| b.is_ascii_whitespace()).unwrap_or(false) {
        iter.next();
    }
    if iter.peek() != Some(&b'[') {
        return 0;
    }
    iter.next();
    // Empty array? Skip whitespace and check for ']'.
    let mut depth: i32 = 1;
    let mut in_string = false;
    let mut escape = false;
    let mut saw_value = false;
    let mut count: usize = 0;
    let mut whitespace_only = true;
    for b in iter {
        if in_string {
            if escape {
                escape = false;
                continue;
            }
            match b {
                b'\\' => escape = true,
                b'"' => in_string = false,
                _ => {}
            }
            continue;
        }
        match b {
            b'"' => {
                in_string = true;
                if depth == 1 {
                    saw_value = true;
                    whitespace_only = false;
                }
            }
            b'[' | b'{' => {
                depth += 1;
                if depth == 2 {
                    saw_value = true;
                    whitespace_only = false;
                }
            }
            b']' | b'}' => {
                depth -= 1;
                if depth == 0 {
                    if saw_value {
                        count += 1;
                    }
                    return count;
                }
            }
            b',' if depth == 1 => {
                if saw_value {
                    count += 1;
                }
                saw_value = false;
            }
            b' ' | b'\n' | b'\t' | b'\r' => {}
            _ => {
                if depth == 1 {
                    saw_value = true;
                    whitespace_only = false;
                }
            }
        }
        // Suppress unused-warning helper.
        let _ = whitespace_only;
    }
    count
}

/// Test-only engine: returns a preconfigured byte blob and record count.
pub struct StubQueryEngine {
    pub canned_json: Vec<u8>,
    pub canned_records: u64,
    /// If set, every call returns this error instead. Lets tests cover the
    /// empty-result and backend-error branches deterministically.
    pub canned_error: Option<QueryError>,
}

impl StubQueryEngine {
    pub fn ok(json: impl Into<Vec<u8>>, records: u64) -> Self {
        Self {
            canned_json: json.into(),
            canned_records: records,
            canned_error: None,
        }
    }
    pub fn empty() -> Self {
        Self {
            canned_json: Vec::new(),
            canned_records: 0,
            canned_error: Some(QueryError::Empty),
        }
    }
}

impl QueryEngine for StubQueryEngine {
    fn run(
        &self,
        _params: &QueryParams,
        _max_records: u32,
        _use_test_db: bool,
    ) -> Result<QueryResult, QueryError> {
        if let Some(e) = &self.canned_error {
            return Err(match e {
                QueryError::Empty => QueryError::Empty,
                QueryError::Backend(s) => QueryError::Backend(s.clone()),
                QueryError::Io(_) => {
                    QueryError::Backend("test stub io error".into())
                }
            });
        }
        Ok(QueryResult {
            btides_json: self.canned_json.clone(),
            records: self.canned_records,
        })
    }
}

/// Optional helper: clean up any `--cwd` parameter to make sure we don't
/// accidentally point at the worktree root. Currently a noop; placeholder
/// for a follow-up commit that validates `cwd` exists. Kept to make the
/// `Path` import non-warning.
#[allow(dead_code)]
fn _path_lives_here(_: &Path) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stub_returns_canned_bytes() {
        let q = StubQueryEngine::ok(b"[{}]".to_vec(), 1);
        let p = QueryParams::default();
        let r = q.run(&p, 100, false).expect("ok");
        assert_eq!(r.records, 1);
        assert_eq!(r.btides_json, b"[{}]");
    }

    #[test]
    fn stub_returns_empty_error() {
        let q = StubQueryEngine::empty();
        let p = QueryParams::default();
        let err = q.run(&p, 100, false).unwrap_err();
        assert!(matches!(err, QueryError::Empty));
    }

    #[test]
    fn count_top_level_array_handles_simple_cases() {
        assert_eq!(count_top_level_array(b"[]"), 0);
        assert_eq!(count_top_level_array(b"[1]"), 1);
        assert_eq!(count_top_level_array(b"[1,2,3]"), 3);
        assert_eq!(count_top_level_array(b"[ 1 , 2 , 3 ]"), 3);
        // Object with internal commas should still count as one.
        assert_eq!(count_top_level_array(b"[{\"a\":1,\"b\":2}]"), 1);
        // Two objects.
        assert_eq!(
            count_top_level_array(b"[{\"a\":1,\"b\":2},{\"c\":3}]"),
            2
        );
        // String with internal comma should still count as one.
        assert_eq!(count_top_level_array(b"[\"a,b,c\"]"), 1);
        // String with escaped quote.
        assert_eq!(count_top_level_array(b"[\"a\\\"b\",\"c\"]"), 2);
        // Nested array.
        assert_eq!(count_top_level_array(b"[[1,2],[3,4]]"), 2);
        // Whitespace before array.
        assert_eq!(count_top_level_array(b"  [1,2]"), 2);
    }

    #[test]
    fn append_query_flags_emits_expected_argv() {
        let mut args = Vec::new();
        let mut p = QueryParams::default();
        p.bdaddr = Some("AA:BB:CC:DD:EE:FF".into());
        p.NOT_bdaddr = Some(vec!["11:22:33:44:55:66".into()]);
        p.require_GPS = true;
        p.require_GATT_any = false;
        p.UUID_regex = Some(vec!["180a".into(), "180f".into()]);
        append_query_flags(&mut args, &p);
        assert!(args.contains(&"--bdaddr".to_string()));
        assert!(args.contains(&"AA:BB:CC:DD:EE:FF".to_string()));
        assert!(args.contains(&"--NOT-bdaddr".to_string()));
        assert!(args.contains(&"--UUID-regex".to_string()));
        assert!(args.contains(&"180a".to_string()));
        assert!(args.contains(&"180f".to_string()));
        assert!(args.contains(&"--require-GPS".to_string()));
        assert!(!args.contains(&"--require-GATT-any".to_string()));
    }
}
