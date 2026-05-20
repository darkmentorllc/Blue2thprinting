//! BTIDES-to-SQL ingest behind a trait so the rest of the server (and the
//! tests) don't have to care whether the database is real, faked, or absent.
//!
//! In production the server links against the existing
//! `Analysis/rust/BTIDES-to-SQL` library via the optional `sql-ingest` Cargo
//! feature and uses [`MysqlIngestSink`]. The default `cargo test` build does
//! *not* enable that feature, so unit and integration tests can run on
//! machines without MySQL, using [`NoopIngestSink`].

use std::path::Path;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum IngestError {
    #[error("ingest backend rejected the file: {0}")]
    Backend(String),
    #[error("path is not valid UTF-8: {0:?}")]
    NonUtf8Path(std::path::PathBuf),
}

/// Sink that the server hands a freshly-saved BTIDES file to for database
/// ingest. Implementations must be `Send + Sync` so an `Arc` of one can be
/// shared across handler threads.
///
/// `use_test_db` routes the ingest to the `bttest` database instead of
/// `bt2`, matching the per-request behavior of the Python server's
/// `run_btides_to_sql(..., use_test_db=...)`. A single server process can
/// therefore ingest into either database depending on the request, the same
/// way a single query can target either via TME's `--use-test-db`.
pub trait IngestSink: Send + Sync {
    fn ingest_file(&self, path: &Path, use_test_db: bool) -> Result<(), IngestError>;
}

/// Test/dev sink: does nothing, always succeeds. Used by the integration
/// test (no MySQL needed) and as the default when the production server
/// is started without the `sql-ingest` feature.
pub struct NoopIngestSink;

impl IngestSink for NoopIngestSink {
    fn ingest_file(&self, _path: &Path, _use_test_db: bool) -> Result<(), IngestError> {
        Ok(())
    }
}

/// Real ingest sink: forwards each file to BTIDES-to-SQL's
/// `import_files_with_pool`. Only compiled when the `sql-ingest` Cargo
/// feature is enabled, because the underlying crate brings in MySQL.
///
/// Holds one connection pool per database (`bt2` and `bttest`) so a single
/// server process can honor per-request `--use-test-db`. `mysql::Pool::new`
/// is lazy (it doesn't open a connection until first use), so constructing
/// both pools up front costs nothing if one of them is never exercised.
#[cfg(feature = "sql-ingest")]
pub struct MysqlIngestSink {
    pool_bt2: BTIDES_to_SQL::Pool,
    pool_bttest: BTIDES_to_SQL::Pool,
    opts: BTIDES_to_SQL::ImportOpts,
}

#[cfg(feature = "sql-ingest")]
impl MysqlIngestSink {
    /// Build pools against the local MySQL/MariaDB the way the Python
    /// server does — same defaults as TME_helpers.py
    /// (user="user", pass="a", host="localhost") — one for `bt2` and one
    /// for `bttest`.
    pub fn connect(
        host: &str,
        user: &str,
        pass: &str,
        opts: BTIDES_to_SQL::ImportOpts,
    ) -> Result<Self, IngestError> {
        let pool_bt2 = BTIDES_to_SQL::build_pool(host, user, pass, false)
            .map_err(|e| IngestError::Backend(e.to_string()))?;
        let pool_bttest = BTIDES_to_SQL::build_pool(host, user, pass, true)
            .map_err(|e| IngestError::Backend(e.to_string()))?;
        Ok(Self {
            pool_bt2,
            pool_bttest,
            opts,
        })
    }
}

#[cfg(feature = "sql-ingest")]
impl IngestSink for MysqlIngestSink {
    fn ingest_file(&self, path: &Path, use_test_db: bool) -> Result<(), IngestError> {
        let path_str = path
            .to_str()
            .ok_or_else(|| IngestError::NonUtf8Path(path.to_path_buf()))?
            .to_string();
        let pool = if use_test_db {
            &self.pool_bttest
        } else {
            &self.pool_bt2
        };
        BTIDES_to_SQL::import_files_with_pool(pool, &[path_str], &self.opts)
            .map_err(|e| IngestError::Backend(e.to_string()))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noop_sink_always_succeeds() {
        let sink = NoopIngestSink;
        assert!(sink.ingest_file(Path::new("/does/not/matter"), false).is_ok());
        assert!(sink.ingest_file(Path::new("/does/not/matter"), true).is_ok());
    }
}
