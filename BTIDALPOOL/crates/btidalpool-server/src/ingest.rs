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
pub trait IngestSink: Send + Sync {
    fn ingest_file(&self, path: &Path) -> Result<(), IngestError>;
}

/// Test/dev sink: does nothing, always succeeds. Used by the integration
/// test (no MySQL needed) and as the default when the production server
/// is started without the `sql-ingest` feature.
pub struct NoopIngestSink;

impl IngestSink for NoopIngestSink {
    fn ingest_file(&self, _path: &Path) -> Result<(), IngestError> {
        Ok(())
    }
}

/// Real ingest sink: forwards each file to BTIDES-to-SQL's
/// `import_files_with_pool`. Only compiled when the `sql-ingest` Cargo
/// feature is enabled, because the underlying crate brings in MySQL.
#[cfg(feature = "sql-ingest")]
pub struct MysqlIngestSink {
    pool: BTIDES_to_SQL::Pool,
    opts: BTIDES_to_SQL::ImportOpts,
}

#[cfg(feature = "sql-ingest")]
impl MysqlIngestSink {
    /// Build a pool against the local MySQL/MariaDB the way the Python
    /// server does — same defaults as TME_helpers.py
    /// (user="user", pass="a", host="localhost").
    pub fn connect(
        host: &str,
        user: &str,
        pass: &str,
        use_test_db: bool,
        opts: BTIDES_to_SQL::ImportOpts,
    ) -> Result<Self, IngestError> {
        let pool = BTIDES_to_SQL::build_pool(host, user, pass, use_test_db)
            .map_err(|e| IngestError::Backend(e.to_string()))?;
        Ok(Self { pool, opts })
    }
}

#[cfg(feature = "sql-ingest")]
impl IngestSink for MysqlIngestSink {
    fn ingest_file(&self, path: &Path) -> Result<(), IngestError> {
        let path_str = path
            .to_str()
            .ok_or_else(|| IngestError::NonUtf8Path(path.to_path_buf()))?
            .to_string();
        BTIDES_to_SQL::import_files_with_pool(&self.pool, &[path_str], &self.opts)
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
        assert!(sink.ingest_file(Path::new("/does/not/matter")).is_ok());
    }
}
