// import-all-BTIDES: bulk Rust port of Analysis/Import_All_HCI_and_PCAP.py.
//
// Walks one or more folders of capture files, classifies each as a PCAP
// (libpcap classic — any of the four magics) or BTSnoop/btmon HCI log
// (magic "btsnoop\0"), and runs the appropriate converter, emitting a
// `<basename>.btides` file alongside each input.
//
// All conversion logic is shared with the standalone pcap-to-BTIDES and
// hci-to-BTIDES binaries via BTIDES-model / BTIDES-bt / BTIDES-pcap /
// BTIDES-btsnoop / BTIDES-hci.
//
// Parallelism: by default uses max(1, N-4) of the host's CPU cores,
// processing PCAPs first then HCI logs (PCAPs are typically larger /
// heavier so prioritizing them keeps cores busy longer).

use std::collections::HashSet;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::Instant;

use clap::Parser;

use BTIDES_bt::adv::handle_adv_pdu;
use BTIDES_bt::conn::ConnectionTable;
use BTIDES_bt::ll::{
    is_adv_aa, parse_adv_ll_header, parse_air_pdu, parse_data_ll_header, LLID_CONTROL,
};
use BTIDES_bt::llcp::handle_llcp;
use BTIDES_bt::rf::parse_rf;
use BTIDES_btsnoop::BtsnoopReader;
use BTIDES_hci::{handle_packet as handle_hci_packet, HciState};
use BTIDES_model::Btides;
use BTIDES_pcap::PcapReader;
use BTIDES_to_SQL::{build_pool, import_files_with_pool, ImportOpts, Pool};

const LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR: u32 = 256;

#[derive(Parser, Debug)]
#[command(
    version,
    about = "Walk folders of pcap / btsnoop capture files and emit one BTIDES JSON file per input."
)]
struct Cli {
    /// Input folder; can be passed multiple times.
    #[arg(long, action = clap::ArgAction::Append)]
    folder: Vec<PathBuf>,
    /// Auto-detect file type by leading magic bytes (recommended).
    #[arg(long, default_value_t = true)]
    auto_detect: bool,
    /// Path to BTIDES_Schema directory (used for output JSON-schema validation
    /// unless `--no-validate` is set). If omitted, defaults to
    /// `<binary_dir>/../../../BTIDES_Schema` — i.e. the schema submodule that
    /// sits alongside the `rust/` workspace inside `Analysis/` when this binary
    /// is run from its standard `Analysis/rust/target/{debug,release}/` build
    /// location.
    #[arg(long)]
    schema_dir: Option<PathBuf>,
    /// Skip JSON-schema validation on output.
    #[arg(long, default_value_t = false)]
    no_validate: bool,
    /// Re-emit even if a `.btides` already exists next to the input. Mutually
    /// exclusive with `--read-existing-BTIDES`.
    #[arg(long, default_value_t = false, conflicts_with = "read_existing_btides")]
    overwrite_existing: bool,
    /// If a `.btides` already exists next to a capture file, skip conversion
    /// and process the existing `.btides` directly (e.g. SQL-import it via
    /// `--to-SQL`). `.btides.processed` files are still skipped. Mutually
    /// exclusive with `--overwrite-existing`. Mirrors the Python
    /// `--read-existing-BTIDES` flag in `Import_All_HCI_and_PCAP.py`.
    #[arg(long = "read-existing-BTIDES", default_value_t = false)]
    read_existing_btides: bool,
    /// Concurrency. Defaults to max(1, ncpu-4).
    #[arg(long)]
    workers: Option<usize>,
    /// Include verbose-only BTIDES fields (type_str, opcode_str, utf8_name, ...).
    #[arg(long = "verbose-BTIDES", default_value_t = false)]
    verbose_btides: bool,
    /// Print one-line summary per file.
    #[arg(long, default_value_t = false)]
    verbose: bool,

    // --- --to-SQL: per-file import into MySQL after each conversion ---
    //
    // When enabled, each worker calls into the `BTIDES-to-SQL` library
    // (path-deped from ../BTIDES-to-SQL) with just its single output file
    // immediately after writing it. On success, the file is renamed to
    // `<stem>.btides.processed` so future runs (and the in-flight job
    // collector above) skip it. On failure, the `.btides` is left alone for
    // retry. Per-file atomicity is provided by the library's own
    // transaction + deadlock-retry; the shared MySQL Pool below is safe to
    // call across workers concurrently.
    /// After each conversion, also import the resulting .btides into MySQL
    /// via the BTIDES-to-SQL library. The .btides file is renamed to
    /// `.btides.processed` on success and left in place on failure.
    #[arg(long = "to-SQL", default_value_t = false)]
    to_sql: bool,
    /// Use the alternate `bttest` database instead of `bt2`. Pass-through to
    /// the importer.
    #[arg(long, default_value_t = false)]
    use_test_db: bool,
    /// MySQL host (default 127.0.0.1). Defaults to IPv4 loopback explicitly
    /// rather than `localhost` because the Rust `mysql` crate's address
    /// resolver appears to try IPv6 `::1` first on macOS even when
    /// /etc/hosts lists `127.0.0.1 localhost` ahead of `::1 localhost`; if
    /// mysqld is bound to IPv4-only (`bind-address = 127.0.0.1`, the
    /// Homebrew default), that yields a confusing "Connection refused"
    /// from the importer despite `mysql -u user -pa` working fine.
    #[arg(long, default_value = "127.0.0.1")]
    db_host: String,
    /// MySQL user (default 'user' — matches TME_helpers.py).
    #[arg(long, default_value = "user")]
    db_user: String,
    /// MySQL password (default 'a' — matches TME_helpers.py).
    #[arg(long, default_value = "a")]
    db_password: String,
    /// Per-file MySQL deadlock retry count (default 8). Each retry uses
    /// exponential backoff with jitter inside the library.
    #[arg(long, default_value_t = 8)]
    deadlock_retries: usize,
    /// Skip renaming `<stem>.btides` to `<stem>.btides.processed` after a
    /// successful SQL import. Off by default (i.e. by default we DO rename,
    /// to match the existing skip-already-processed convention in
    /// `collect_jobs`).
    #[arg(long, default_value_t = false)]
    keep_btides_after_sql: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Pcap,
    Hci,
    /// `--read-existing-BTIDES`: a `.btides` file already exists next to a
    /// capture file. Skip conversion and just hand the existing file to the
    /// downstream stage (SQL import when `--to-SQL` is set; otherwise a no-op).
    ReadExisting,
}

/// Default `--schema-dir` location when the user doesn't pass one explicitly:
/// `<dir-containing-binary>/../../../BTIDES_Schema`. Under the standard
/// `Analysis/rust/target/{debug,release}/import-all-BTIDES` layout that
/// resolves to `Analysis/BTIDES_Schema/` — the submodule that ships with
/// every Blue2thprinting checkout.
fn default_schema_dir() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    // exe = .../Analysis/rust/target/<profile>/import-all-BTIDES
    //   .parent() -> .../Analysis/rust/target/<profile>
    //   .parent() -> .../Analysis/rust/target
    //   .parent() -> .../Analysis/rust
    //   .parent() -> .../Analysis
    let analysis = exe.parent()?.parent()?.parent()?.parent()?;
    Some(analysis.join("BTIDES_Schema"))
}

fn detect_kind(path: &Path) -> Option<Kind> {
    let mut f = std::fs::File::open(path).ok()?;
    let mut buf = [0u8; 8];
    let n = f.read(&mut buf).ok()?;
    if n >= 8 && &buf[..8] == b"btsnoop\0" {
        return Some(Kind::Hci);
    }
    if n >= 4 {
        let m = [buf[0], buf[1], buf[2], buf[3]];
        if matches!(
            m,
            [0xa1, 0xb2, 0xc3, 0xd4]
                | [0xd4, 0xc3, 0xb2, 0xa1]
                | [0xa1, 0xb2, 0x3c, 0x4d]
                | [0x4d, 0x3c, 0xb2, 0xa1]
                | [0x0a, 0x0d, 0x0d, 0x0a]
        ) {
            return Some(Kind::Pcap);
        }
    }
    None
}

fn convert_pcap(
    input: &Path,
    output: &Path,
    schema_dir: &Path,
    verbose_btides: bool,
    validate: bool,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut reader = PcapReader::open(input)?;
    let hdr = reader.header();
    if hdr.linktype != LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR {
        return Err(format!(
            "{} has linktype {}, expected {}",
            input.display(),
            hdr.linktype,
            LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR
        )
        .into());
    }
    let mut bt = Btides::new();
    bt.set_verbose(verbose_btides);
    let mut conns = ConnectionTable::default();
    loop {
        let next = match reader.next() {
            Ok(Some(p)) => p,
            Ok(None) => break,
            Err(_) => break,
        };
        process_pcap_packet(&mut bt, &mut conns, next.data);
    }
    if validate {
        bt.write_btides(output, schema_dir)?;
    } else {
        std::fs::write(output, bt.to_json_bytes()?)?;
    }
    Ok(())
}

fn process_pcap_packet(bt: &mut Btides, conns: &mut ConnectionTable, raw: &[u8]) {
    let Some((rf, after_rf)) = parse_rf(raw) else {
        return;
    };
    let direction = rf.direction();
    let Some((aa, ll_hdr, payload, _crc)) = parse_air_pdu(after_rf) else {
        return;
    };
    if is_adv_aa(aa) {
        let hdr = parse_adv_ll_header(ll_hdr[0]);
        handle_adv_pdu(bt, conns, hdr, payload);
    } else {
        let hdr = parse_data_ll_header(ll_hdr[0]);
        if ll_hdr[1] == 0 {
            return;
        }
        if let Some(st) = conns.by_aa.get(&aa) {
            if st.encrypted {
                return;
            }
        }
        if hdr.llid == LLID_CONTROL {
            handle_llcp(bt, conns, aa, direction, payload);
        } else {
            BTIDES_bt::l2cap::handle_data_pdu(bt, conns, aa, direction, hdr.llid, payload);
        }
    }
}

fn convert_hci(
    input: &Path,
    output: &Path,
    schema_dir: &Path,
    verbose_btides: bool,
    validate: bool,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut reader = BtsnoopReader::open(input)?;
    let mut bt = Btides::new();
    bt.set_verbose(verbose_btides);
    let mut conns = ConnectionTable::default();
    let mut hci = HciState::default();
    while let Some(rec) = reader.next_record() {
        handle_hci_packet(&mut bt, &mut conns, &mut hci, rec.uart_type, rec.direction, rec.data);
    }
    if validate {
        bt.write_btides(output, schema_dir)?;
    } else {
        std::fs::write(output, bt.to_json_bytes()?)?;
    }
    Ok(())
}

struct Job {
    input: PathBuf,
    output: PathBuf,
    kind: Kind,
}

fn collect_jobs(folders: &[PathBuf], overwrite: bool, read_existing: bool) -> Vec<Job> {
    let mut pcaps = Vec::new();
    let mut hcis = Vec::new();
    let mut existing = Vec::new();
    // Dedupe ReadExisting jobs by their .btides path: a folder containing both
    // `capture.pcap` and `capture.btides` would otherwise emit one ReadExisting
    // when visited via the capture file *and* another via the .btides file.
    let mut existing_set: HashSet<PathBuf> = HashSet::new();
    for folder in folders {
        for entry in walkdir(folder) {
            let name = entry.file_name().and_then(|s| s.to_str()).unwrap_or("");
            // Finalized output — never re-process.
            if name.ends_with(".btides.processed") {
                continue;
            }
            // Bare `.btides` file. In --read-existing-BTIDES mode, emit a
            // ReadExisting job even when no sibling capture lives next to it
            // (common workflow: ship just the .btides files to the analysis
            // host and SQL-import them). Outside that mode, skip — `.btides`
            // is an output, not an input.
            if name.ends_with(".btides") {
                if read_existing && existing_set.insert(entry.clone()) {
                    existing.push(Job {
                        input: entry.clone(),
                        output: entry,
                        kind: Kind::ReadExisting,
                    });
                }
                continue;
            }
            // Otherwise treat the file as a potential capture: classify by
            // magic bytes.
            let Some(kind) = detect_kind(&entry) else {
                continue;
            };
            let parent = entry.parent().unwrap_or(Path::new("."));
            let stem = entry.file_stem().and_then(|s| s.to_str()).unwrap_or("output");
            let out = parent.join(format!("{stem}.btides"));
            let processed = parent.join(format!("{stem}.btides.processed"));
            // Already finalized — skip in every mode unless --overwrite-existing.
            if processed.exists() && !overwrite {
                continue;
            }
            if out.exists() {
                if overwrite {
                    // Fall through and re-convert from the source capture.
                } else if read_existing {
                    if existing_set.insert(out.clone()) {
                        existing.push(Job {
                            input: out.clone(),
                            output: out,
                            kind: Kind::ReadExisting,
                        });
                    }
                    continue;
                } else {
                    continue;
                }
            }
            let job = Job {
                input: entry,
                output: out,
                kind,
            };
            if kind == Kind::Pcap {
                pcaps.push(job);
            } else {
                hcis.push(job);
            }
        }
    }
    // PCAPs first (heaviest), then HCIs, then ReadExisting (cheapest — pure
    // SQL import) so cores stay busy on conversion work while DB writes
    // dribble in at the tail.
    pcaps.extend(hcis);
    pcaps.extend(existing);
    pcaps
}

// Return every regular file under `root`. Filtering of .btides/.btides.processed
// is now `collect_jobs`'s job, because `--read-existing-BTIDES` mode wants to
// see bare `.btides` files (folders that only ship the converted output, with
// the source captures pruned).
fn walkdir(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(rd) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in rd.flatten() {
            let p = entry.path();
            if p.is_dir() {
                stack.push(p);
            } else if p.is_file() {
                out.push(p);
            }
        }
    }
    out
}

// Per-file SQL import. Returns Ok(()) on success (rows committed), Err(_) on
// any failure — caller leaves the .btides in place so the next run can retry.
//
// The library wraps the whole write phase in a single transaction with
// deadlock-retry (MySQL error 1213), so this call is atomic per-file even
// when many workers hit overlapping tables (LE_bdaddr_to_name etc.)
// concurrently.
fn sql_import_one(
    pool: &Pool,
    btides_path: &Path,
    deadlock_retries: usize,
    verbose: bool,
) -> Result<BTIDES_to_SQL::ImportStats, Box<dyn std::error::Error + Send + Sync>> {
    let opts = ImportOpts {
        // Per-file imports are tiny relative to the multi-worker concurrency
        // we already have at the import-all-BTIDES level — keep the in-call
        // writer / reader threads at 1 to avoid nested thread pools.
        writer_threads: 1,
        reader_threads: 1,
        deadlock_retries,
        one_transaction: true,
        verbose,
    };
    let paths = vec![btides_path.to_string_lossy().into_owned()];
    let stats = import_files_with_pool(pool, &paths, &opts)?;
    Ok(stats)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    if cli.folder.is_empty() {
        return Err("--folder is required (pass one or more times)".into());
    }
    let n_workers = cli
        .workers
        .unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1).saturating_sub(4).max(1));
    // Resolve --schema-dir: explicit user value wins; otherwise derive from
    // the binary's own location. We only insist the path exists when
    // validation is actually going to run (i.e. !--no-validate).
    let schema_dir_path = match cli.schema_dir.clone() {
        Some(p) => p,
        None => default_schema_dir()
            .ok_or("could not derive default --schema-dir from binary path; pass --schema-dir explicitly")?,
    };
    if !cli.no_validate && !schema_dir_path.exists() {
        return Err(format!(
            "--schema-dir {} does not exist (pass --schema-dir or --no-validate)",
            schema_dir_path.display()
        )
        .into());
    }
    let jobs = collect_jobs(&cli.folder, cli.overwrite_existing, cli.read_existing_btides);
    let total = jobs.len();
    if total == 0 {
        eprintln!("No new files to convert.");
        return Ok(());
    }
    eprintln!(
        "import-all-BTIDES: {} job(s), {} worker thread(s){}",
        total,
        n_workers,
        if cli.to_sql { " (with --to-SQL)" } else { "" }
    );

    // Build the MySQL pool ONCE up front when --to-SQL is enabled. The pool
    // is `Send + Sync` (it's an Arc-of-connections internally), so we share
    // an `Arc<Pool>` across all worker threads. Failing early here avoids
    // running thousands of conversions before discovering bad DB creds.
    let sql_pool: Option<Arc<Pool>> = if cli.to_sql {
        let pool = build_pool(&cli.db_host, &cli.db_user, &cli.db_password, cli.use_test_db)
            .map_err(|e| format!("MySQL pool init failed: {e}"))?;
        Some(Arc::new(pool))
    } else {
        None
    };

    let t0 = Instant::now();
    let queue = Arc::new(Mutex::new(jobs));
    let next_idx = Arc::new(AtomicUsize::new(0));
    let ok = Arc::new(AtomicUsize::new(0));
    let err = Arc::new(AtomicUsize::new(0));
    let sql_ok = Arc::new(AtomicUsize::new(0));
    let sql_err = Arc::new(AtomicUsize::new(0));
    let schema_dir = Arc::new(schema_dir_path);
    let verbose_btides = cli.verbose_btides;
    let validate = !cli.no_validate;
    let verbose = cli.verbose;
    let to_sql = cli.to_sql;

    // SQL import is serialized through a single writer thread. Each conversion
    // worker hands its finished .btides path off through this mpsc channel and
    // immediately picks up the next conversion job — workers never block on
    // MySQL. The writer pops paths FIFO and runs sql_import_one one transaction
    // at a time, so two in-process imports can never deadlock against each
    // other (each .btides is already a single transaction; see flush_all in
    // BTIDES-to-SQL/src/lib.rs). The library's deadlock-retry budget stays in
    // place but only fires now against *external* processes touching the same
    // tables. Conversion finishes in completion order, so smaller files
    // naturally reach the SQL queue first; large PCAPs land at the tail.
    let (sql_tx, sql_writer) = if let Some(pool) = sql_pool.clone() {
        let (tx, rx) = mpsc::channel::<PathBuf>();
        let sql_ok = sql_ok.clone();
        let sql_err = sql_err.clone();
        let keep_btides_after_sql = cli.keep_btides_after_sql;
        let deadlock_retries = cli.deadlock_retries;
        let handle = thread::spawn(move || {
            for output in rx {
                let t_sql = Instant::now();
                match sql_import_one(&pool, &output, deadlock_retries, verbose) {
                    Ok(stats) => {
                        sql_ok.fetch_add(1, Ordering::SeqCst);
                        if verbose {
                            eprintln!(
                                "  [SQL] {} -> +{} new rows, {} dup ({:.2}s)",
                                output.display(),
                                stats.inserted,
                                stats.attempted.saturating_sub(stats.inserted),
                                t_sql.elapsed().as_secs_f64()
                            );
                        }
                        if !keep_btides_after_sql {
                            // Mark as processed so a re-run of
                            // import-all-BTIDES skips it (see `collect_jobs`
                            // above which already looks for
                            // `.btides.processed`).
                            let mut processed = output.clone();
                            let new_name = format!(
                                "{}.processed",
                                output.file_name().and_then(|s| s.to_str()).unwrap_or("out.btides")
                            );
                            processed.set_file_name(new_name);
                            if let Err(re) = std::fs::rename(&output, &processed) {
                                eprintln!(
                                    "  [SQL] WARN: rename {} -> {} failed: {re}",
                                    output.display(),
                                    processed.display()
                                );
                            }
                        }
                    }
                    Err(e) => {
                        sql_err.fetch_add(1, Ordering::SeqCst);
                        eprintln!(
                            "  [SQL] ERROR importing {}: {e}  (leaving .btides in place for retry)",
                            output.display()
                        );
                    }
                }
            }
        });
        (Some(tx), Some(handle))
    } else {
        (None, None)
    };

    let mut handles = Vec::new();
    for _ in 0..n_workers {
        let queue = queue.clone();
        let next_idx = next_idx.clone();
        let ok = ok.clone();
        let err = err.clone();
        let schema_dir = schema_dir.clone();
        let sql_tx = sql_tx.clone();
        let handle = thread::spawn(move || loop {
            let i = next_idx.fetch_add(1, Ordering::SeqCst);
            let job = {
                let q = queue.lock().unwrap();
                if i >= q.len() {
                    break;
                }
                Job {
                    input: q[i].input.clone(),
                    output: q[i].output.clone(),
                    kind: q[i].kind,
                }
            };
            let t_conv = Instant::now();
            let res = match job.kind {
                Kind::Pcap => convert_pcap(
                    &job.input,
                    &job.output,
                    &schema_dir,
                    verbose_btides,
                    validate,
                ),
                Kind::Hci => convert_hci(
                    &job.input,
                    &job.output,
                    &schema_dir,
                    verbose_btides,
                    validate,
                ),
                // No conversion — the .btides already exists on disk. Fall
                // through to the SQL handoff below so the writer still
                // imports it.
                Kind::ReadExisting => Ok(()),
            };
            let conv_elapsed = t_conv.elapsed();
            match res {
                Ok(()) => {
                    ok.fetch_add(1, Ordering::SeqCst);
                    if verbose {
                        eprintln!(
                            "[{:?}] {} -> {} ({:.2}s)",
                            job.kind,
                            job.input.display(),
                            job.output.display(),
                            conv_elapsed.as_secs_f64()
                        );
                    }
                    if let Some(tx) = sql_tx.as_ref() {
                        // Send only fails if the writer panicked; the worker
                        // has no useful recovery, so drop the result and keep
                        // draining the queue.
                        let _ = tx.send(job.output.clone());
                    }
                }
                Err(e) => {
                    err.fetch_add(1, Ordering::SeqCst);
                    eprintln!("ERROR converting {}: {e}", job.input.display());
                }
            }
        });
        handles.push(handle);
    }
    for h in handles {
        let _ = h.join();
    }
    // All conversions done. Drop main's Sender so the channel closes once
    // every per-worker clone has also been dropped (which has already
    // happened above, since each worker's clone falls out of scope when its
    // thread exits and `h.join()` waits for that). The writer then drains
    // any remaining queued imports and exits its `for output in rx` loop.
    drop(sql_tx);
    if let Some(handle) = sql_writer {
        let _ = handle.join();
    }
    let elapsed = t0.elapsed();
    if to_sql {
        eprintln!(
            "Done: {} converted, {} convert errors, {} SQL-imported, {} SQL errors in {:.2}s",
            ok.load(Ordering::SeqCst),
            err.load(Ordering::SeqCst),
            sql_ok.load(Ordering::SeqCst),
            sql_err.load(Ordering::SeqCst),
            elapsed.as_secs_f64()
        );
    } else {
        eprintln!(
            "Done: {} ok, {} err in {:.2}s",
            ok.load(Ordering::SeqCst),
            err.load(Ordering::SeqCst),
            elapsed.as_secs_f64()
        );
    }
    Ok(())
}
