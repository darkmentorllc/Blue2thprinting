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

    /// Commit once at the end instead of per-statement autocommit. Committing
    /// once is the default (far faster for bulk imports); pass
    /// --no-one-transaction to fall back to per-statement autocommit.
    #[arg(long = "no-one-transaction", default_value_t = false)]
    no_one_transaction: bool,

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
        one_transaction: !args.no_one_transaction,
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

// ============================================================================
// CLI argument-parsing tests
// ============================================================================
// Parser-only: Args::try_parse_from() exercises clap without touching MySQL
// or the importer. Covers every flag, its default, required-arg enforcement,
// the Append (multi --input) action, numeric validation, and --help.
#[cfg(test)]
mod cli_tests {
    use super::*;
    use clap::Parser;

    fn parse(args: &[&str]) -> Result<Args, clap::Error> {
        // try_parse_from wants argv[0] = program name.
        let mut v = vec!["BTIDES-to-SQL"];
        v.extend_from_slice(args);
        Args::try_parse_from(v)
    }

    #[test]
    fn requires_at_least_one_input() {
        // --input is required=true → parsing with none is an error.
        assert!(parse(&[]).is_err());
    }

    #[test]
    fn defaults_match_documented_values() {
        let a = parse(&["--input", "a.btides"]).unwrap();
        assert_eq!(a.input, vec!["a.btides".to_string()]);
        assert!(!a.use_test_db);
        assert!(!a.verbose);
        assert_eq!(a.db_host, "127.0.0.1");
        assert_eq!(a.db_user, "user");
        assert_eq!(a.db_password, "a");
        assert!(!a.no_one_transaction); // default: single-transaction mode on
        assert_eq!(a.writer_threads, 1);
        assert_eq!(a.reader_threads, 1);
        assert_eq!(a.deadlock_retries, 8);
    }

    #[test]
    fn input_is_appendable() {
        let a = parse(&["--input", "a.btides", "--input", "b.btides"]).unwrap();
        assert_eq!(a.input, vec!["a.btides".to_string(), "b.btides".to_string()]);
    }

    #[test]
    fn use_test_db_and_verbose_are_flags() {
        let a = parse(&["--input", "a", "--use-test-db", "--verbose"]).unwrap();
        assert!(a.use_test_db);
        assert!(a.verbose);
    }

    #[test]
    fn verbose_print_alias_works() {
        let a = parse(&["--input", "a", "--verbose-print"]).unwrap();
        assert!(a.verbose);
    }

    #[test]
    fn db_connection_overrides_parse() {
        let a = parse(&[
            "--input", "a",
            "--db-host", "192.168.10.128",
            "--db-user", "tester",
            "--db-password", "secret",
        ])
        .unwrap();
        assert_eq!(a.db_host, "192.168.10.128");
        assert_eq!(a.db_user, "tester");
        assert_eq!(a.db_password, "secret");
    }

    #[test]
    fn numeric_thread_and_retry_overrides_parse() {
        let a = parse(&[
            "--input", "a",
            "--writer-threads", "4",
            "--reader-threads", "3",
            "--deadlock-retries", "16",
        ])
        .unwrap();
        assert_eq!(a.writer_threads, 4);
        assert_eq!(a.reader_threads, 3);
        assert_eq!(a.deadlock_retries, 16);
    }

    #[test]
    fn non_numeric_thread_value_is_rejected() {
        assert!(parse(&["--input", "a", "--writer-threads", "lots"]).is_err());
    }

    #[test]
    fn unknown_flag_is_rejected() {
        assert!(parse(&["--input", "a", "--bogus"]).is_err());
    }

    #[test]
    fn help_short_circuits_with_displayhelp() {
        let err = parse(&["--help"]).unwrap_err();
        assert_eq!(err.kind(), clap::error::ErrorKind::DisplayHelp);
    }

    // Single-transaction mode is the default; --no-one-transaction is the
    // off-switch that flips it to per-statement autocommit. (The effective
    // ImportOpts.one_transaction in main() is `!no_one_transaction`.)
    #[test]
    fn no_one_transaction_flag_disables_single_transaction_mode() {
        // Default: flag absent → single-transaction mode is on.
        assert!(!parse(&["--input", "a"]).unwrap().no_one_transaction);
        // Off-switch present → single-transaction mode is off.
        assert!(parse(&["--input", "a", "--no-one-transaction"]).unwrap().no_one_transaction);
        // The old positive flag name is no longer accepted.
        assert!(parse(&["--input", "a", "--one-transaction"]).is_err());
    }
}
