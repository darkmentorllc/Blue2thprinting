// Thin CLI wrapper around the `BTIDES-to-SQL` library.
//
// The actual importer logic lives in src/lib.rs so that other binaries
// (e.g. import-all-BTIDES with --to-SQL) can call into it directly without
// shelling out per file.

#![allow(non_snake_case)]  // crate name `BTIDES_to_SQL` is not snake_case by design.

use clap::Parser;

use BTIDES_to_SQL::{build_pool, import_files_with_pool, ImportOpts};

#[derive(Parser, Debug)]
#[command(about = "BTIDES to MySQL importer (Rust port of BTIDES_to_SQL.py)")]
struct Args {
    /// Input file name for BTIDES JSON file. May be passed multiple times.
    #[arg(long, action = clap::ArgAction::Append, required = true)]
    input: Vec<String>,

    /// Use the alternate bttest database (matches --use-test-db in Python).
    #[arg(long)]
    use_test_db: bool,

    /// Print per-table statistics.
    #[arg(long, alias = "verbose-print")]
    verbose: bool,

    /// MySQL host (default 127.0.0.1). Defaults to IPv4 loopback explicitly
    /// rather than `localhost` because the Rust `mysql` crate's address
    /// resolver appears to try IPv6 `::1` first on macOS even when
    /// /etc/hosts lists `127.0.0.1 localhost` ahead of `::1 localhost`; if
    /// mysqld is bound to IPv4-only (`bind-address = 127.0.0.1`, the
    /// Homebrew default), that yields a confusing "Connection refused"
    /// despite `mysql -u user -pa` working fine.
    #[arg(long, default_value = "127.0.0.1")]
    db_host: String,

    /// MySQL user (default 'user' — matches TME_helpers.py).
    #[arg(long, default_value = "user")]
    db_user: String,

    /// MySQL password (default 'a' — matches TME_helpers.py).
    #[arg(long, default_value = "a")]
    db_password: String,

    /// Disable per-statement autocommit and commit once at the end.
    #[arg(long, default_value_t = true)]
    one_transaction: bool,

    /// Use N parallel writer connections (each handles a disjoint set of
    /// destination tables). Default 1 = serial. GPS always runs serially at
    /// the end because of its read-modify-write semantics.
    #[arg(long, default_value_t = 1)]
    writer_threads: usize,

    /// Parse N input files concurrently into per-thread row buffers, then
    /// merge them before the write phase. Default 1 = serial parsing. Each
    /// reader operates on its own file(s), so there is no contention. Has no
    /// effect when only one --input file is provided.
    #[arg(long, default_value_t = 1)]
    reader_threads: usize,

    /// On MySQL error 1213 (deadlock victim), roll back and retry the
    /// transaction up to N times. Each retry sleeps an exponentially
    /// backed-off, jittered delay before re-running. Default 8 — sufficient
    /// for ~5 concurrent processes hammering the same table.
    #[arg(long, default_value_t = 8)]
    deadlock_retries: usize,
}

fn main() {
    let args = Args::parse();

    let pool = build_pool(
        &args.db_host,
        &args.db_user,
        &args.db_password,
        args.use_test_db,
    )
    .expect("MySQL pool");

    let opts = ImportOpts {
        writer_threads: args.writer_threads,
        reader_threads: args.reader_threads,
        deadlock_retries: args.deadlock_retries,
        one_transaction: args.one_transaction,
        verbose: true, // CLI always prints the per-phase summary
    };

    // Match the library's verbose toggle to the caller's --verbose flag for
    // per-table statistics, but keep the per-phase summaries on always (the
    // bin's historical behavior).
    let mut opts = opts;
    opts.verbose = args.verbose || opts.verbose;

    let stats = match import_files_with_pool(&pool, &args.input, &opts) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("import failed: {e}");
            std::process::exit(1);
        }
    };

    let total_attempted = stats.attempted + stats.gps_updates as u64 + stats.gps_inserts as u64;
    let total_inserted = stats.inserted + stats.gps_updates as u64 + stats.gps_inserts as u64;
    eprintln!(
        "Done. Total rows attempted: {}, total new rows: {}, duplicates: {}",
        total_attempted,
        total_inserted,
        total_attempted.saturating_sub(total_inserted)
    );
}
