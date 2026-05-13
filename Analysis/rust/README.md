# Blue2thprinting Rust binaries

Cargo workspace containing the Rust binaries that need Blue2thprinting-specific
state (MySQL schema, capture-folder layout) and therefore can't live in the
generic [`Analysis/BTIDES_Schema/rust/`](../BTIDES_Schema/rust/) workspace:

- **`wigle-to-BTIDES`** — convert a WiGLE Android backup SQLite (`network`
  + `location` tables) into BTIDES. Emits one `GPSArray` record per
  Bluetooth-typed network row and an optional `HCIArray` Remote-Name record
  when the SSID is non-empty. For BLE rows it queries the local
  `bt2`/`bttest` MySQL database in bulk to majority-vote `bdaddr_random` per
  BDADDR across every table with that column (matching the Python
  `Analysis/WIGLE_to_BTIDES.py`). Pass `--no-mysql-lookup` if you don't
  have the local Blue2thprinting database; every BLE row will get
  `bdaddr_rand=1` (Python's tie/miss default).
- **`import-all-BTIDES`** — bulk converter. Walks a directory tree,
  auto-detects each file's format from its magic bytes (libpcap variants,
  BTSnoop UART/MONITOR), dispatches to the right backend, and writes one
  `.btides` next to each input. `max(1, ncpu-4)` worker threads by default.
  Skips inputs that already have a sibling `.btides` (or `.btides.processed`)
  file unless `--overwrite-existing` is passed.

Both binaries link against the protocol-parser library crates that ship with
the BTIDES schema repo (`BTIDES-model`, `BTIDES-pcap`, `BTIDES-btsnoop`,
`BTIDES-bt`, `BTIDES-hci`) via cross-workspace path dependencies
(`path = "../../BTIDES_Schema/rust/..."`). You can build this workspace
on its own — Cargo will pull in and compile whatever it needs from the
schema submodule.

## Build prerequisites

See [`Analysis/BTIDES_Schema/rust/README.md`](../BTIDES_Schema/rust/README.md)
in the schema submodule for the Rust toolchain prerequisites (rustc ≥ 1.79
required by `jsonschema 0.30`). On Debian/Ubuntu the apt-shipped `rustc` is
often too old, so install via `rustup`.

## Build

From this directory:

```sh
cargo build --release
```

The optimized binaries land in `target/release/{wigle-to-BTIDES,import-all-BTIDES}`.
Both setup scripts (`setup_analysis_helper_macOS.sh` /
`setup_analysis_helper_debian-based.sh`) at the repository root build both
this workspace and the BTIDES_Schema workspace as part of `apt`/`brew` setup.

## Usage

Each binary takes a `--schema-dir` pointing at the BTIDES schema directory:

```sh
# Bulk: walk a directory tree of mixed pcap/btsnoop files
./target/release/import-all-BTIDES \
    --folder      /path/to/captures \
    --auto-detect \
    --schema-dir  ../BTIDES_Schema

# WiGLE Android backup SQLite, with MySQL bdaddr_random lookup (default)
./target/release/wigle-to-BTIDES \
    --input      /path/to/wigle_backup.sqlite \
    --output     wigle.btides                 \
    --schema-dir ../BTIDES_Schema

# WiGLE without MySQL (faster; every BLE row -> bdaddr_rand=1)
./target/release/wigle-to-BTIDES \
    --input      /path/to/wigle_backup.sqlite \
    --output     wigle.btides                 \
    --schema-dir ../BTIDES_Schema             \
    --no-mysql-lookup
```

`--folder` can be passed multiple times to walk several roots in one run.

## When to use Python vs Rust

| Job | Python entry point | Rust binary | Rust faster by |
| --- | --- | --- | --- |
| pcap → BTIDES | `Analysis/PCAP_to_BTIDES.py` | `pcap-to-BTIDES` (in `BTIDES_Schema/rust/`) | ~30× |
| HCI/btsnoop → BTIDES | `Analysis/HCI_to_BTIDES.py` | `hci-to-BTIDES` (in `BTIDES_Schema/rust/`) | ~60× |
| sdptool XML → BTIDES | `Analysis/SDP_to_BTIDES.py` | `sdp-to-BTIDES` (in `BTIDES_Schema/rust/`) | ~2× |
| Bulk capture folder | `Analysis/Import_All_HCI_and_PCAP.py` | `import-all-BTIDES` | ~50× wall-clock |
| WiGLE SQLite → BTIDES (MySQL on) | `Analysis/WIGLE_to_BTIDES.py` | `wigle-to-BTIDES` | ~1.1× (MySQL roundtrip dominates) |
| WiGLE SQLite → BTIDES (no MySQL) | (n/a) | `wigle-to-BTIDES --no-mysql-lookup` | ~250× vs Python-with-MySQL |
