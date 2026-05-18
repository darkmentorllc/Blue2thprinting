# sniffle_receiver_rust

A Rust port of `Sniffle/python_cli/sniff_receiver.py` (plus the relevant
parts of `sniffle/sniffle_hw.py`, `sniffle/packet_decoder.py`, and
`sniffle/pcap.py`). Drop-in CLI-compatible replacement, intended to be
launched by `Scripts/central_app_launcher.py` in place of the Python
sniff_receiver on hosts where the Python version's per-packet decode
loop is too CPU-hungry — notably the Raspberry Pi Zero W, where the
single ARMv6 core saturates at one concurrent Python sniff_receiver in
scan mode and the resulting kernel-tty-buffer overflows generate
`Ignoring message due to missing CRLF` errors at ~70/MB.

## What it does (and doesn't do)

Implemented (parity with `sniff_receiver.py` for everything the launcher
actually invokes):

* All sniff modes: connection-follow (default), `-A` active scan,
  `-a` passive scan
* All filters: `-m MAC`, `-i IRK`, `-S STRING`, `-r RSSI`
* Extended-adv (`-e`), 37/38/39 hop (`-H`), long-range coded PHY (`-l`)
* Encrypted-connection preloads (`-Q PRELOAD`, `-n`)
* CRC-error capture (`-C`), pause-on-disconnect (`-p`)
* Channel pin (`-c CHAN`), baud rate (`-b BAUD`)
* Full state machine for AuxPtr chains, AuxScanRsp, AuxConnectRsp →
  `cur_aa`/`crc_init_rev` transitions (mirror of `update_state()` in
  `packet_decoder.py`)
* Pcap output (`DLT_BLUETOOTH_LE_LL_WITH_PHDR`) with correct
  `pdu_type`/`aux_type` for every packet class
* Optional packet pretty-print on stdout via `--print` (Python parity)
* Two extras the launcher uses: `--duration=SEC` and `--label=NAME`

Deliberately not ported (out of scope for the UART/Sonoff use case):

* SDR back-ends (`sniffle_sdr.py`)
* `decode_adv_data` (`-d` flag — accepted but no-op)
* Relay master/protocol

## Build

Single source file, no external crate dependencies — pure `std` plus a
small hand-rolled libc FFI block. Build with the apt-installable Rust
toolchain on Raspberry Pi OS Bookworm:

```bash
sudo apt-get install -y rustc cargo
cd Sniffle/sniffle_receiver_rust
cargo build --release --offline
```

That produces `target/release/sniffle_receiver_rust` (~378 KB).

On a Pi Zero W the first build takes ~6–10 minutes (single core,
512 MB). Incremental rebuilds are seconds.

## Install

Copy the binary into the location `central_app_launcher.py` expects:

```bash
sudo cp target/release/sniffle_receiver_rust ../sniffle_receiver_rust
sudo chmod 755 ../sniffle_receiver_rust
```

(i.e. `Sniffle/sniffle_receiver_rust` next to `Sniffle/python_cli/`).

## Usage

Same CLI as `sniff_receiver.py`:

```bash
sniffle_receiver_rust -s=/dev/ttyUSB0 -o=cap.pcap -A
sniffle_receiver_rust -s=/dev/ttyUSB0 -o=cap.pcap -m CA:FE:13:37:00:01 -c 37
sniffle_receiver_rust -s=/dev/ttyUSB0 -o=cap.pcap -m CA:FE:13:37:00:01 -e
```

Run `sniffle_receiver_rust -h` for the full flag list.

## Diagnostics

Set `SNIFFLE_RECEIVER_RUST_TRACE_CMD=1` in the environment to log every
command byte sequence the binary writes to the dongle (in hex + base64
on the wire) — useful when comparing wire behavior against
`sniff_receiver.py` under strace.

Every 10 s the binary emits a status line to stderr:

```
[ttyUSB0] +10s: msgs=… pkts=… states=… crlf_err=… dec_err=… inq_now=… inq_max=…
```

where `inq_*` is the kernel tty input-buffer occupancy via `TIOCINQ` —
the smoking-gun metric for whether the host is draining fast enough.

## Performance vs `sniff_receiver.py` on a Pi Zero W

Measured against the same 6-Sonoff workload, 90 s active-scan per N:

| N concurrent dongles | Python CRLF errs | Rust CRLF errs | Python CPU | Rust CPU |
|---|---|---|---|---|
| 1 | 4 | 0 | 70% | 8% |
| 2 | 75 | 0 | 92% | 14% |
| 3 | 106 | 0 | 91% | 22% |
| 4 | 103 | 0 | 91% | 28% |
| 5 | 121 | 0 | 91% | 32% |
| 6 | 111 | 0 | 92% | 38% |

The Pi Zero W now happily handles all 6 dongles in scan mode with the
single core ~40% utilised; the Python version saturated at N=1.
