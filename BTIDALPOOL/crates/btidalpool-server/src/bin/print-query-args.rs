//! QA / debug helper binary.
//!
//! Prints the Tell_Me_Everything query-filter flags ("cascade") that the
//! BTIDALPOOL Rust server would build for a given query JSON, as a JSON
//! array of strings on stdout.
//!
//! Its reason for existing is the cross-language parity test
//! (`BTIDALPOOL/python/test_query_parity.py`): that test feeds the same
//! query JSON to this binary and to the Python server's
//! `btidalpool_query_args.build_query_args`, and asserts the two produce
//! identical flags — i.e. that a given query yields the same TME invocation
//! (and therefore the same results) under both servers.
//!
//! It is also handy for ops debugging ("what TME flags would this query
//! produce?"). It performs no network or DB I/O.
//!
//! Usage:
//!   print-query-args --query-json '{"name_regex":["Pixel"]}'
//!   # -> ["--name-regex","Pixel"]

use btidalpool_proto::QueryParams;
use btidalpool_server::query::tme_query_args;
use clap::Parser;

#[derive(Parser)]
#[command(
    name = "print-query-args",
    about = "Print the TME query-filter flags the server would build for a query JSON (QA tool)"
)]
struct Cli {
    /// JSON-encoded `QueryParams` blob (the same shape `btidalpool-client
    /// query --query-json` accepts).
    #[arg(long)]
    query_json: String,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let params: QueryParams = serde_json::from_str(&cli.query_json)
        .map_err(|e| format!("parsing --query-json: {e}"))?;
    let args = tme_query_args(&params);
    // Compact JSON array of strings, one line, no trailing newline issues
    // (println adds exactly one \n which the Python test strips).
    println!("{}", serde_json::to_string(&args)?);
    Ok(())
}
