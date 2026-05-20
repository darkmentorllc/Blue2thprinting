//! `btidalpool-server` binary entry point.

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use clap::Parser;

use btidalpool_server::handlers::Deps;
use btidalpool_server::http::{self, Config, TlsConfig};
use btidalpool_server::ingest::IngestSink;
#[cfg(not(feature = "sql-ingest"))]
use btidalpool_server::ingest::NoopIngestSink;
use btidalpool_server::oauth::{GoogleOAuthValidator, MockOAuthValidator, OAuthValidator};
use btidalpool_server::query::{QueryEngine, SubprocessQueryEngine};
use btidalpool_server::rate_limit::{Limiter, Limits};
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
    /// Per-IP simultaneous-request cap.
    #[arg(long, default_value_t = 10)]
    max_concurrent: u32,
    /// Per-IP per-day request budget.
    #[arg(long, default_value_t = 100)]
    max_per_day: u32,
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

    let validator: Arc<dyn OAuthValidator> = if cli.mock_auth {
        Arc::new(MockOAuthValidator {
            good_token: cli.mock_auth_token.clone(),
            email: cli.mock_auth_email.clone(),
        })
    } else {
        Arc::new(GoogleOAuthValidator::new())
    };

    let limiter = Limiter::new(Limits {
        max_simultaneous: cli.max_concurrent,
        max_per_day: cli.max_per_day,
        ..Default::default()
    });

    let deps = Deps {
        state,
        ingest,
        query,
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
        limiter,
        validator,
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

#[cfg(not(feature = "sql-ingest"))]
fn build_ingest() -> Result<Arc<dyn IngestSink>> {
    log::warn!(
        "compiled without `sql-ingest` feature — uploads will be saved to disk but NOT \
         ingested into the bt2 / bttest MySQL database. Re-run a separate BTIDES-to-SQL \
         pass to ingest them, or rebuild with --features sql-ingest."
    );
    Ok(Arc::new(NoopIngestSink))
}
