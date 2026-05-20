//! `btidalpool` CLI binary.
//!
//! Three subcommands, each producing one HTTPS round trip:
//!
//!   * `upload --input <file>`  — POST a BTIDES JSON file. Pre-flights with
//!     a CheckHash to short-circuit if the server already has the content.
//!   * `query  --output <file>` — POST a query, write the response JSON.
//!   * `check-hash --hash <h>`  — POST a CheckHash only.
//!
//! The OAuth flow itself stays in Python (see
//! `BTIDALPOOL/python/BTIDALPOOL_to_BTIDES.py`); this binary reads
//! `--token-file` and trusts that the embedded `{token, refresh_token}` is
//! valid. The Python shim runs the SSO flow before invoking us.

use std::path::PathBuf;
use std::process::ExitCode;

use anyhow::{Context, Result};
use btidalpool_client::transport::{CertTrust, Transport};
use btidalpool_client::{build_check_hash, build_query, build_upload};
use btidalpool_proto::{
    canonical_sha1, AuthFields, ErrorKind, QueryParams, Response,
};
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(
    name = "btidalpool-client",
    about = "BTIDALPOOL CLI (Rust reimplementation of the Python BTIDES_to_BTIDALPOOL / BTIDALPOOL_to_BTIDES tools)"
)]
struct Cli {
    /// BTIDALPOOL server URL. The Python tools have `localhost:3567` and
    /// `btidalpool.ddns.net:3567` hardcoded; in Rust we make it a flag so
    /// the Python shim can pass `--server-url https://localhost:3567` for
    /// tests without us having to recompile.
    #[arg(long, default_value = "https://btidalpool.ddns.net:3567")]
    server_url: String,
    /// Path to a file containing the Google OAuth `{token, refresh_token}`
    /// JSON. Required so the binary stays headless — the Python shim is
    /// responsible for running the SSO flow when this file is absent.
    #[arg(long)]
    token_file: PathBuf,
    /// Tell the server to use the `bttest` database instead of `bt2`.
    #[arg(long)]
    use_test_db: bool,
    /// Verify the server cert against the OS trust store instead of the
    /// bundled self-signed cert. Use once the server moves to a
    /// publicly-trusted (e.g. LetsEncrypt) certificate.
    #[arg(long)]
    system_roots: bool,
    /// Accept any TLS certificate. For local end-to-end tests only —
    /// production callers rely on the bundled cert (the default).
    #[arg(long)]
    insecure: bool,
    #[command(subcommand)]
    cmd: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Upload a BTIDES JSON file to the server.
    Upload {
        /// Path to the input BTIDES JSON file.
        #[arg(long)]
        input: PathBuf,
        /// Skip the CheckHash pre-flight (just attempt the upload).
        #[arg(long)]
        no_preflight: bool,
    },
    /// Run a Tell_Me_Everything-style query against the server.
    Query {
        /// Path where the resulting BTIDES JSON should be written.
        #[arg(long)]
        output: PathBuf,
        /// JSON-encoded `QueryParams` blob. Required (even if empty `{}`).
        /// We accept a blob rather than re-declaring all 23 query flags here
        /// because the Python shim already has them and just forwards the
        /// dict it built up.
        #[arg(long)]
        query_json: String,
    },
    /// Ask the server whether a given SHA1 hash is already present.
    CheckHash {
        /// SHA1 hex digest (40 chars).
        #[arg(long)]
        hash: String,
    },
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => code,
        Err(e) => {
            eprintln!("error: {e:#}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<ExitCode> {
    let cli = Cli::parse();

    let auth = load_auth(&cli.token_file, cli.use_test_db)?;
    // Trust precedence: --insecure > --system-roots > bundled cert.
    // The bundled-cert default reproduces the Python client's
    // `verify=./btidalpool.ddns.net.crt` behavior so the common case
    // (talking to the production server) needs no TLS flags at all.
    let trust = if cli.insecure {
        CertTrust::Insecure
    } else if cli.system_roots {
        CertTrust::System
    } else {
        CertTrust::BundledPin
    };
    let transport = Transport::new(cli.server_url.clone(), trust)?;

    match cli.cmd {
        Command::Upload {
            input,
            no_preflight,
        } => Ok(do_upload(&transport, &auth, &input, no_preflight)?),
        Command::Query {
            output,
            query_json,
        } => Ok(do_query(&transport, &auth, &output, &query_json)?),
        Command::CheckHash { hash } => Ok(do_check_hash(&transport, &auth, &hash)?),
    }
}

fn load_auth(token_file: &std::path::Path, use_test_db: bool) -> Result<AuthFields> {
    let raw = std::fs::read_to_string(token_file)
        .with_context(|| format!("reading token file {token_file:?}"))?;
    #[derive(serde::Deserialize)]
    struct TokenFile {
        token: String,
        refresh_token: String,
    }
    let parsed: TokenFile =
        serde_json::from_str(&raw).context("token file is not valid JSON")?;
    Ok(AuthFields {
        token: parsed.token,
        refresh_token: parsed.refresh_token,
        use_test_db,
    })
}

fn do_upload(
    transport: &Transport,
    auth: &AuthFields,
    input: &std::path::Path,
    no_preflight: bool,
) -> Result<ExitCode> {
    let bytes = std::fs::read(input)
        .with_context(|| format!("reading input file {input:?}"))?;
    let sha1 = canonical_sha1(&bytes).context("hashing input file")?;

    if !no_preflight {
        let env = build_check_hash(auth.clone(), sha1.clone());
        let resp = transport.round_trip(&env)?;
        match resp {
            // Server already has the file — nothing to do.
            Response::Err {
                kind: ErrorKind::DuplicateUpload,
                message,
            } => {
                println!("{message}");
                return Ok(ExitCode::SUCCESS);
            }
            // Server says we should proceed with the upload — fall through.
            Response::Ok { .. } => {}
            // Any other error short-circuits.
            Response::Err { kind, message } => {
                eprintln!("preflight failed: {message}");
                return Ok(exit_code_for_kind(kind));
            }
            Response::QueryResult { .. } => {
                eprintln!("preflight returned unexpected QueryResult");
                return Ok(ExitCode::from(3));
            }
        }
    }

    let env = build_upload(auth.clone(), bytes);
    let resp = transport.round_trip(&env)?;
    match resp {
        Response::Ok { message } => {
            println!("{message}");
            Ok(ExitCode::SUCCESS)
        }
        Response::Err { kind, message } => {
            eprintln!("{message}");
            Ok(exit_code_for_kind(kind))
        }
        Response::QueryResult { .. } => {
            eprintln!("upload returned unexpected QueryResult");
            Ok(ExitCode::from(3))
        }
    }
}

fn do_query(
    transport: &Transport,
    auth: &AuthFields,
    output: &std::path::Path,
    query_json: &str,
) -> Result<ExitCode> {
    let params: QueryParams =
        serde_json::from_str(query_json).context("parsing --query-json")?;
    let env = build_query(auth.clone(), params);
    let resp = transport.round_trip(&env)?;
    match resp {
        Response::QueryResult {
            records,
            btides_json,
        } => {
            std::fs::write(output, &btides_json)
                .with_context(|| format!("writing output to {output:?}"))?;
            println!("{records} BTIDES records written to {}", output.display());
            Ok(ExitCode::SUCCESS)
        }
        Response::Err { kind, message } => {
            eprintln!("{message}");
            Ok(exit_code_for_kind(kind))
        }
        Response::Ok { message } => {
            // Shouldn't happen for a query — but if it does, the caller
            // should treat it as a soft failure, not a crash.
            eprintln!("unexpected Ok response to query: {message}");
            Ok(ExitCode::from(3))
        }
    }
}

fn do_check_hash(transport: &Transport, auth: &AuthFields, hash: &str) -> Result<ExitCode> {
    let env = build_check_hash(auth.clone(), hash.to_string());
    let resp = transport.round_trip(&env)?;
    match resp {
        Response::Ok { message } => {
            println!("{message}");
            Ok(ExitCode::SUCCESS)
        }
        Response::Err { kind, message } => {
            // DuplicateUpload from a CheckHash is the "yes, server has it"
            // answer — print and exit 0 because the user got a useful answer.
            if matches!(kind, ErrorKind::DuplicateUpload) {
                println!("{message}");
                return Ok(ExitCode::SUCCESS);
            }
            eprintln!("{message}");
            Ok(exit_code_for_kind(kind))
        }
        Response::QueryResult { .. } => {
            eprintln!("check-hash returned unexpected QueryResult");
            Ok(ExitCode::from(3))
        }
    }
}

/// Map a wire-level [`ErrorKind`] to a process exit code, so the Python
/// shim can branch on the exit code without parsing stderr. 0 = success;
/// 4xx → 4; 401 → 5; 429 → 6; 5xx → 7.
fn exit_code_for_kind(kind: ErrorKind) -> ExitCode {
    match kind {
        ErrorKind::Unauthorized => ExitCode::from(5),
        ErrorKind::RateLimited => ExitCode::from(6),
        ErrorKind::Internal => ExitCode::from(7),
        ErrorKind::BadRequest
        | ErrorKind::SchemaInvalid
        | ErrorKind::DuplicateUpload
        | ErrorKind::EmptyResult => ExitCode::from(4),
    }
}
