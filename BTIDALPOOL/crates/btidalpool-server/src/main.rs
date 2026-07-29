//! `btidalpool-server` binary entry point.

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use clap::Parser;

use btidalpool_server::handlers::Deps;
use btidalpool_server::http::{self, Config, OverloadConfig, TlsConfig};
use btidalpool_server::ingest::IngestSink;
#[cfg(not(feature = "sql-ingest"))]
use btidalpool_server::ingest::NoopIngestSink;
#[cfg(feature = "sql-ingest")]
use btidalpool_server::native_query::MysqlNativeQueryEngine;
use btidalpool_server::native_query::NativeQueryEngine;
#[cfg(not(feature = "sql-ingest"))]
use btidalpool_server::native_query::UnavailableNativeQueryEngine;
use btidalpool_server::oauth::{
    CachingOAuthValidator, GoogleOAuthValidator, MockOAuthValidator, OAuthValidator,
};
use btidalpool_server::query::{QueryEngine, SubprocessQueryEngine};
use btidalpool_server::rate_limit::{ConcurrencyLimiter, Limiter, Limits};
use btidalpool_server::resumable::ResumableStore;
use btidalpool_server::session::SessionTokens;
use btidalpool_server::state::ServerState;

#[derive(Debug, Parser)]
#[command(
    name = "btidalpool-server",
    about = "BTIDALPOOL server (Rust reimplementation of Analysis/Server_BTIDALPOOL.py)"
)]
struct Cli {
    /// Address to bind for the listener. Defaults match the Python
    /// server's hardcoded value, so the existing systemd unit on the AWS
    /// VM keeps working without changes.
    #[arg(long, default_value = "0.0.0.0:3567")]
    bind: SocketAddr,
    /// TLS certificate chain (PEM). Required unless `--no-tls` is set.
    #[arg(long, default_value = "./btidalpool.ddns.net.crt")]
    cert: PathBuf,
    /// TLS private key (PEM). Required unless `--no-tls` is set.
    #[arg(long, default_value = "./btidalpool.ddns.net.key")]
    key: PathBuf,
    /// Run plain HTTP (NOT recommended in production). Useful for local
    /// loopback testing without generating a self-signed cert.
    #[arg(long)]
    no_tls: bool,
    /// Directory to write accepted BTIDES uploads into.
    #[arg(long, default_value = "./pool_files")]
    pool_dir: PathBuf,
    /// Directory for per-user log files.
    #[arg(long, default_value = "./user_logs")]
    user_logs_dir: PathBuf,
    /// Combined access log path.
    #[arg(long, default_value = "./user_access.log")]
    access_log: PathBuf,
    /// Per-authenticated-identity simultaneous-request cap.
    #[arg(long, default_value_t = 10)]
    max_concurrent: u32,
    /// Per-authenticated-identity rolling-day request budget.
    #[arg(long, default_value_t = 100)]
    max_per_day: u32,
    /// Broader simultaneous-request abuse cap per public IP.
    #[arg(long, default_value_t = 50)]
    max_ip_concurrent: u32,
    /// Broader rolling-day abuse budget per public IP.
    #[arg(long, default_value_t = 1000)]
    max_ip_per_day: u32,
    /// Weighted process-wide budget for expensive work. Legacy queries use
    /// four units, uploads/finalizes two, and native queries one.
    #[arg(long, default_value_t = 4)]
    max_expensive_work_units: u32,
    /// Process-wide simultaneous v4 whole-file upload cap.
    #[arg(long, default_value_t = 2)]
    max_global_whole_uploads: u32,
    /// Process-wide simultaneous query cap.
    #[arg(long, default_value_t = 1)]
    max_global_queries: u32,
    /// Process-wide simultaneous native-query cap.
    #[arg(long, default_value_t = 4)]
    max_global_native_queries: u32,
    /// Process-wide simultaneous resumable chunk-write cap.
    #[arg(long, default_value_t = 4)]
    max_global_chunk_puts: u32,
    /// Process-wide simultaneous resumable finalize cap.
    #[arg(long, default_value_t = 2)]
    max_global_finalizes: u32,
    /// Retry-After delta seconds returned with capacity-overload HTTP 503.
    #[arg(long, default_value_t = 2)]
    overload_retry_after_seconds: u64,
    /// Maximum BTIDES records returned by one query.
    #[arg(long, default_value_t = 100)]
    max_query_records: u32,
    /// Maximum normalized MySQL rows returned by one native query.
    #[arg(long, default_value_t = 50_000)]
    max_native_query_rows: u64,
    /// Positive Google-validation cache TTL. Cache keys are token SHA-256
    /// digests; plaintext OAuth credentials are never stored.
    #[arg(long, default_value_t = 300)]
    oauth_cache_ttl_seconds: u64,
    /// Lifetime of signed BTPL session tokens.
    #[arg(long, default_value_t = 900)]
    session_ttl_seconds: u64,
    /// Optional >=32-byte HMAC key file. If omitted, an in-memory random key
    /// is generated and outstanding sessions expire on server restart.
    #[arg(long)]
    session_key_file: Option<PathBuf>,
    /// Durable manifests, chunks, and receipts for resumable uploads.
    #[arg(long, default_value = "./btidalpool_resumable_state")]
    resumable_state_dir: PathBuf,
    /// Use a mock OAuth validator that accepts any token whose value
    /// equals `--mock-auth-token` and reports back `--mock-auth-email`.
    /// For local end-to-end testing only.
    #[arg(long)]
    mock_auth: bool,
    #[arg(long, default_value = "test-token")]
    mock_auth_token: String,
    #[arg(long, default_value = "tester@example.com")]
    mock_auth_email: String,
    /// `python3` interpreter used for the Tell_Me_Everything subprocess.
    #[arg(long, default_value = "python3")]
    python: PathBuf,
    /// Path to Tell_Me_Everything.py. Default is the sibling Analysis dir.
    #[arg(long, default_value = "../Analysis/Tell_Me_Everything.py")]
    tme_script: PathBuf,
    /// Working directory for the Tell_Me_Everything subprocess. Defaults
    /// to the directory containing `--tme-script`.
    #[arg(long)]
    tme_cwd: Option<PathBuf>,
}

fn main() -> Result<()> {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    let cli = Cli::parse();

    let state = ServerState::initialize(&cli.pool_dir, &cli.user_logs_dir, &cli.access_log)?;

    // Ingest: production uses the BTIDES-to-SQL library (gated behind the
    // `sql-ingest` Cargo feature so `cargo test` doesn't need MySQL). When
    // the feature isn't compiled in, we fall back to the noop sink so the
    // server still runs and uploads still land in `pool_files/` — a later
    // ingest run (e.g. via the standalone `BTIDES-to-SQL` CLI) can pick
    // them up.
    let ingest: Arc<dyn IngestSink> = build_ingest()?;
    let native_query: Arc<dyn NativeQueryEngine> = build_native_query()?;

    let cwd = cli
        .tme_cwd
        .clone()
        .or_else(|| cli.tme_script.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));
    let query: Arc<dyn QueryEngine> = Arc::new(SubprocessQueryEngine {
        python: cli.python.clone(),
        script: cli.tme_script.clone(),
        cwd,
    });

    let base_validator: Arc<dyn OAuthValidator> = if cli.mock_auth {
        Arc::new(MockOAuthValidator {
            good_token: cli.mock_auth_token.clone(),
            email: cli.mock_auth_email.clone(),
        })
    } else {
        Arc::new(GoogleOAuthValidator::new())
    };
    let validator: Arc<dyn OAuthValidator> = Arc::new(CachingOAuthValidator::new(
        base_validator,
        std::time::Duration::from_secs(cli.oauth_cache_ttl_seconds.max(1)),
    ));

    let identity_limiter = Limiter::new(Limits {
        max_simultaneous: cli.max_concurrent,
        max_per_day: cli.max_per_day,
        ..Default::default()
    });
    let ip_limiter = Limiter::new(Limits {
        max_simultaneous: cli.max_ip_concurrent,
        max_per_day: cli.max_ip_per_day,
        ..Default::default()
    });
    let overload = OverloadConfig {
        expensive_work: ConcurrencyLimiter::new(cli.max_expensive_work_units.max(1)),
        whole_uploads: ConcurrencyLimiter::new(cli.max_global_whole_uploads.max(1)),
        queries: ConcurrencyLimiter::new(cli.max_global_queries.max(1)),
        native_queries: ConcurrencyLimiter::new(cli.max_global_native_queries.max(1)),
        chunk_puts: ConcurrencyLimiter::new(cli.max_global_chunk_puts.max(1)),
        finalizes: ConcurrencyLimiter::new(cli.max_global_finalizes.max(1)),
        retry_after: std::time::Duration::from_secs(cli.overload_retry_after_seconds.max(1)),
    };

    let sessions = match &cli.session_key_file {
        Some(path) => SessionTokens::from_key(
            std::fs::read(path)?,
            std::time::Duration::from_secs(cli.session_ttl_seconds.max(1)),
        )
        .map_err(|error| anyhow::anyhow!("invalid session signing key: {error}"))?,
        None => {
            log::warn!(
                "no --session-key-file configured; generated an in-memory signing key \
                 (safe, but outstanding sessions will expire on restart)"
            );
            SessionTokens::random(std::time::Duration::from_secs(
                cli.session_ttl_seconds.max(1),
            ))
        }
    };

    let deps = Deps {
        state,
        resumable: ResumableStore::initialize(&cli.resumable_state_dir)?,
        ingest,
        query,
        native_query,
        max_query_records: cli.max_query_records.max(1),
        max_native_rows: cli.max_native_query_rows.max(1),
    };

    let tls = if cli.no_tls {
        None
    } else {
        Some(TlsConfig {
            cert_pem_path: cli.cert.clone(),
            key_pem_path: cli.key.clone(),
        })
    };

    http::run(Config {
        bind: cli.bind,
        tls,
        ip_limiter,
        identity_limiter,
        overload,
        validator,
        sessions,
        deps,
    })
}

#[cfg(feature = "sql-ingest")]
fn build_ingest() -> Result<Arc<dyn IngestSink>> {
    use btidalpool_server::ingest::MysqlIngestSink;
    // Defaults match Analysis/TME_helpers.py. The sink holds pools for both
    // bt2 and bttest and picks per request based on use_test_db.
    let opts = BTIDES_to_SQL::ImportOpts::default();
    let sink = MysqlIngestSink::connect("localhost", "user", "a", opts)?;
    Ok(Arc::new(sink))
}

#[cfg(feature = "sql-ingest")]
fn build_native_query() -> Result<Arc<dyn NativeQueryEngine>> {
    Ok(Arc::new(MysqlNativeQueryEngine::connect(
        "localhost",
        "user",
        "a",
    )?))
}

#[cfg(not(feature = "sql-ingest"))]
fn build_ingest() -> Result<Arc<dyn IngestSink>> {
    log::warn!(
        "compiled without `sql-ingest` feature — uploads will be saved to disk but NOT \
         ingested into the bt2 / bttest MySQL database. Re-run a separate BTIDES-to-SQL \
         pass to ingest them, or rebuild with --features sql-ingest."
    );
    Ok(Arc::new(NoopIngestSink))
}

#[cfg(not(feature = "sql-ingest"))]
fn build_native_query() -> Result<Arc<dyn NativeQueryEngine>> {
    Ok(Arc::new(UnavailableNativeQueryEngine))
}
