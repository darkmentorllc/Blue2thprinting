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

use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
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
    /// Path to BTIDES_Schema directory (required for validation).
    #[arg(long)]
    schema_dir: PathBuf,
    /// Skip JSON-schema validation on output.
    #[arg(long, default_value_t = false)]
    no_validate: bool,
    /// Re-emit even if a `.btides` already exists next to the input.
    #[arg(long, default_value_t = false)]
    overwrite_existing: bool,
    /// Concurrency. Defaults to max(1, ncpu-4).
    #[arg(long)]
    workers: Option<usize>,
    /// Include verbose-only BTIDES fields (type_str, opcode_str, utf8_name, ...).
    #[arg(long = "verbose-BTIDES", default_value_t = false)]
    verbose_btides: bool,
    /// Print one-line summary per file.
    #[arg(long, default_value_t = false)]
    verbose: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Pcap,
    Hci,
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

fn collect_jobs(folders: &[PathBuf], overwrite: bool) -> Vec<Job> {
    let mut pcaps = Vec::new();
    let mut hcis = Vec::new();
    for folder in folders {
        for entry in walkdir(folder) {
            let Some(kind) = detect_kind(&entry) else {
                continue;
            };
            let parent = entry.parent().unwrap_or(Path::new("."));
            let stem = entry.file_stem().and_then(|s| s.to_str()).unwrap_or("output");
            let out = parent.join(format!("{stem}.btides"));
            let processed = parent.join(format!("{stem}.btides.processed"));
            if !overwrite && (out.exists() || processed.exists()) {
                continue;
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
    // PCAPs first so cores burn them down before starting HCIs.
    pcaps.extend(hcis);
    pcaps
}

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
                let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
                if name.ends_with(".btides") || name.ends_with(".btides.processed") {
                    continue;
                }
                out.push(p);
            }
        }
    }
    out
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    if cli.folder.is_empty() {
        return Err("--folder is required (pass one or more times)".into());
    }
    let n_workers = cli
        .workers
        .unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1).saturating_sub(4).max(1));
    let jobs = collect_jobs(&cli.folder, cli.overwrite_existing);
    let total = jobs.len();
    if total == 0 {
        eprintln!("No new files to convert.");
        return Ok(());
    }
    eprintln!(
        "import-all-BTIDES: {} job(s), {} worker thread(s)",
        total, n_workers
    );

    let t0 = Instant::now();
    let queue = Arc::new(Mutex::new(jobs));
    let next_idx = Arc::new(AtomicUsize::new(0));
    let ok = Arc::new(AtomicUsize::new(0));
    let err = Arc::new(AtomicUsize::new(0));
    let schema_dir = Arc::new(cli.schema_dir.clone());
    let verbose_btides = cli.verbose_btides;
    let validate = !cli.no_validate;
    let verbose = cli.verbose;

    let mut handles = Vec::new();
    for _ in 0..n_workers {
        let queue = queue.clone();
        let next_idx = next_idx.clone();
        let ok = ok.clone();
        let err = err.clone();
        let schema_dir = schema_dir.clone();
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
            let t0 = Instant::now();
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
            };
            let elapsed = t0.elapsed();
            match res {
                Ok(()) => {
                    ok.fetch_add(1, Ordering::SeqCst);
                    if verbose {
                        eprintln!(
                            "[{:?}] {} -> {} ({:.2}s)",
                            job.kind,
                            job.input.display(),
                            job.output.display(),
                            elapsed.as_secs_f64()
                        );
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
    let elapsed = t0.elapsed();
    eprintln!(
        "Done: {} ok, {} err in {:.2}s",
        ok.load(Ordering::SeqCst),
        err.load(Ordering::SeqCst),
        elapsed.as_secs_f64()
    );
    Ok(())
}
