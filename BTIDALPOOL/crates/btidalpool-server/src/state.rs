//! Persistent server state that lives outside the per-request handler:
//!
//!   * On-disk pool of accepted BTIDES uploads (`pool_files/`).
//!   * In-memory index of accepted SHA1 hashes, rebuilt from `pool_files/`
//!     at startup so the dedup check survives a restart.
//!   * Per-user log files (`user_logs/<sanitized_email>.log`).
//!   * Combined access log (`user_access.log`).
//!
//! Matches the directory layout the Python `Server_BTIDALPOOL.py` writes to,
//! so a Rust server can be dropped onto an existing AWS VM and pick up the
//! existing pool of files.

use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use parking_lot::Mutex;

/// Directory layout + per-process locks. Cloneable (Arc-wrapped) so handler
/// threads can share it.
#[derive(Clone)]
pub struct ServerState {
    inner: Arc<Inner>,
}

struct Inner {
    /// `./pool_files` by default. Accepted uploads are written here as
    /// `<sha1>-<email>-<timestamp>.json`.
    pub pool_dir: PathBuf,
    /// `./user_logs` by default. One file per sanitized user email.
    pub user_logs_dir: PathBuf,
    /// `./user_access.log` by default. One combined append-only log.
    pub access_log_path: PathBuf,
    /// SHA1 hex strings of every file currently in `pool_dir`. Loaded at
    /// startup, updated on each successful upload.
    pub unique_hashes: Mutex<HashSet<String>>,
    /// Single writer for the combined access log so concurrent handlers
    /// don't interleave bytes within a single line.
    pub access_log: Mutex<File>,
}

impl ServerState {
    /// Initialize the state from disk: create directories if missing, open
    /// the access log, rebuild the dedup index by scanning `pool_dir`.
    pub fn initialize(
        pool_dir: impl Into<PathBuf>,
        user_logs_dir: impl Into<PathBuf>,
        access_log_path: impl Into<PathBuf>,
    ) -> std::io::Result<Self> {
        let pool_dir = pool_dir.into();
        let user_logs_dir = user_logs_dir.into();
        let access_log_path = access_log_path.into();

        fs::create_dir_all(&pool_dir)?;
        fs::create_dir_all(&user_logs_dir)?;
        if let Some(p) = access_log_path.parent() {
            if !p.as_os_str().is_empty() {
                fs::create_dir_all(p)?;
            }
        }

        let access_log = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&access_log_path)?;

        let unique_hashes = scan_pool_for_hashes(&pool_dir)?;

        Ok(Self {
            inner: Arc::new(Inner {
                pool_dir,
                user_logs_dir,
                access_log_path,
                unique_hashes: Mutex::new(unique_hashes),
                access_log: Mutex::new(access_log),
            }),
        })
    }

    /// True if `sha1` matches a file already in the pool.
    pub fn has_hash(&self, sha1: &str) -> bool {
        self.inner.unique_hashes.lock().contains(sha1)
    }

    /// Mark `sha1` as accepted. Idempotent.
    pub fn record_hash(&self, sha1: &str) {
        self.inner.unique_hashes.lock().insert(sha1.to_string());
    }

    /// Where to write a fresh upload from `email` with a given sha1.
    pub fn build_upload_path(&self, sha1: &str, email: &str, timestamp: &str) -> PathBuf {
        // The Python server doesn't sanitize the email here (it just embeds
        // it verbatim in the filename); we do the same so dedup-by-filename
        // works identically across the Python/Rust transition.
        self.inner
            .pool_dir
            .join(format!("{sha1}-{email}-{timestamp}.json"))
    }

    /// Append one line to the combined access log. Newline is added by us.
    pub fn append_access_log(&self, line: impl AsRef<str>) -> std::io::Result<()> {
        let mut f = self.inner.access_log.lock();
        writeln!(f, "{}", line.as_ref())?;
        f.flush()?;
        Ok(())
    }

    /// Append one line to the per-user log for `email`. Newline added by us.
    pub fn append_user_log(&self, email: &str, line: impl AsRef<str>) -> std::io::Result<()> {
        let sanitized = sanitize_email_for_filename(email);
        let path = self.inner.user_logs_dir.join(format!("{sanitized}.log"));
        // Per-user logs aren't lock-protected in the Python server either; on
        // POSIX, append-mode writes shorter than PIPE_BUF are atomic per
        // POSIX.1-2017, and our log lines are well under that limit.
        let mut f = OpenOptions::new().create(true).append(true).open(&path)?;
        writeln!(f, "{}", line.as_ref())?;
        Ok(())
    }

    pub fn pool_dir(&self) -> &Path {
        &self.inner.pool_dir
    }
    pub fn user_logs_dir(&self) -> &Path {
        &self.inner.user_logs_dir
    }
    pub fn access_log_path(&self) -> &Path {
        &self.inner.access_log_path
    }
}

/// Walk `pool_dir`, extracting the leading SHA1-shaped token from each
/// filename. Matches the Python server's `initialize_unique_files`. Files
/// that don't fit the expected `<sha1>-…` pattern are silently ignored.
fn scan_pool_for_hashes(pool_dir: &Path) -> std::io::Result<HashSet<String>> {
    let mut out = HashSet::new();
    let entries = match fs::read_dir(pool_dir) {
        Ok(e) => e,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(out),
        Err(e) => return Err(e),
    };
    for entry in entries {
        let entry = entry?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        // Accept both `.json` and `.json.processed` extensions, matching
        // the Python server's behavior.
        if !(name.ends_with(".json") || name.ends_with(".processed")) {
            continue;
        }
        if let Some(prefix) = name.split('-').next() {
            if prefix.len() == 40 && prefix.chars().all(|c| c.is_ascii_hexdigit()) {
                out.insert(prefix.to_lowercase());
            }
        }
    }
    Ok(out)
}

/// Replicate the Python server's email-to-filename mapping
/// (`'@' -> '_at_'`, `'.' -> '_dot_'`) so per-user log files end up at the
/// same path under both implementations.
pub fn sanitize_email_for_filename(email: &str) -> String {
    email.replace('@', "_at_").replace('.', "_dot_")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn sanitize_matches_python() {
        assert_eq!(
            sanitize_email_for_filename("alice@example.com"),
            "alice_at_example_dot_com"
        );
    }

    #[test]
    fn fresh_state_has_empty_index_and_creates_dirs() {
        let td = tempdir().unwrap();
        let pool = td.path().join("pool_files");
        let logs = td.path().join("user_logs");
        let access = td.path().join("user_access.log");
        let st = ServerState::initialize(&pool, &logs, &access).unwrap();
        assert!(pool.is_dir());
        assert!(logs.is_dir());
        assert!(!st.has_hash("0000000000000000000000000000000000000000"));
    }

    #[test]
    fn rebuilds_index_from_existing_pool_files() {
        let td = tempdir().unwrap();
        let pool = td.path().join("pool_files");
        fs::create_dir_all(&pool).unwrap();
        // Two well-formed names + one junk name. We should pick up exactly
        // the two SHA1 hashes.
        let h1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        let h2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        fs::write(pool.join(format!("{h1}-a@b.c-2026-01-01.json")), b"[]").unwrap();
        fs::write(pool.join(format!("{h2}-x@y.z-2026-01-02.json.processed")), b"").unwrap();
        fs::write(pool.join("notes.txt"), b"junk").unwrap();
        let st = ServerState::initialize(&pool, td.path().join("ul"), td.path().join("ac"))
            .unwrap();
        assert!(st.has_hash(h1));
        assert!(st.has_hash(h2));
        assert!(!st.has_hash("ffffffffffffffffffffffffffffffffffffffff"));
    }

    #[test]
    fn record_hash_persists_in_memory() {
        let td = tempdir().unwrap();
        let st = ServerState::initialize(
            td.path().join("pool"),
            td.path().join("ul"),
            td.path().join("ac"),
        )
        .unwrap();
        let h = "cccccccccccccccccccccccccccccccccccccccc";
        assert!(!st.has_hash(h));
        st.record_hash(h);
        assert!(st.has_hash(h));
    }

    #[test]
    fn user_log_appends_to_sanitized_filename() {
        let td = tempdir().unwrap();
        let st = ServerState::initialize(
            td.path().join("pool"),
            td.path().join("ul"),
            td.path().join("ac"),
        )
        .unwrap();
        st.append_user_log("alice@example.com", "hello world").unwrap();
        let read = fs::read_to_string(
            td.path().join("ul").join("alice_at_example_dot_com.log"),
        )
        .unwrap();
        assert!(read.contains("hello world"));
    }

    #[test]
    fn access_log_appends_lines() {
        let td = tempdir().unwrap();
        let st = ServerState::initialize(
            td.path().join("pool"),
            td.path().join("ul"),
            td.path().join("ac"),
        )
        .unwrap();
        st.append_access_log("line one").unwrap();
        st.append_access_log("line two").unwrap();
        let read = fs::read_to_string(td.path().join("ac")).unwrap();
        assert_eq!(read.lines().count(), 2);
    }
}
