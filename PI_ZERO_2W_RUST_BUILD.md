# Building `sniffle_receiver_rust` for the Raspberry Pi Zero 2 W

`setup_capture_helper_debian-based.sh` builds `Sniffle/sniffle_receiver_rust`
natively on the capture host with a plain `cargo build --release --offline`
(see `build_sniffle_receiver_rust()`). **That step cannot succeed on a
Raspberry Pi Zero 2 W (aarch64).** The 64-bit `rustc` on that board segfaults
while compiling this crate, and no build flag, memory tuning, or toolchain
upgrade on the Pi fixes it. Cross-compile the binary on an x86_64 host and copy
it over instead.

This is aarch64-specific. The crate's own README documents a successful native
build on the original **Pi Zero W (32-bit ARMv6)**; that path still works. Only
the 64-bit target is affected.

## The failure

A native build (or even `cargo check`) on the Pi ends with a segfault, not a
type error:

```
error: could not compile `sniffle_receiver_rust`; 4 warnings emitted
Caused by:
  process didn't exit successfully: `rustc ... src/main.rs ...`
  (signal: 11, SIGSEGV: invalid memory reference)
```

On Bookworm's apt toolchain (`rustc` 1.63 / LLVM 14) the crash is inside the
LLVM backend (`AsmPrinter::emitFunctionBody` -> `MCContext::createTempSymbol`).
On a current rustup toolchain (`rustc` 1.97) the crash moves earlier, into the
front end — `cargo check` alone (`--emit=metadata`, no codegen) already
segfaults. `rustc` prints its generic "increase stack size with
`RUST_MIN_STACK=...`" hint, but the header reads `rustc interrupted by SIGSEGV`,
not "has overflowed its stack": that hint is a red herring here.

## What it is NOT

Each of these was tested on the Pi and ruled out:

- **Not out of memory.** A memory sampler showed ~289 MB free and swap barely
  touched at the instant of the crash, with 2+ GB of swap active. It also
  crashes in ~2 s, far too fast to exhaust memory.
- **Not compiler-thread stack overflow.** `RUST_MIN_STACK` at 512 MB and 1 GB
  changed nothing (the hint's suggested value doubled, confirming the variable
  was honored — it just did not matter).
- **Not `codegen-units` / LTO / opt-level.** `lto=off`, `codegen-units=16`,
  `opt-level=1`, and `codegen-units=1` all crash at the same point. The
  front-end `cargo check` crash proves codegen settings are irrelevant.
- **Not the source.** The identical source `cargo check`s cleanly on an x86_64
  host in under a second. A trivial hello-world compiles *and runs* on the Pi's
  modern toolchain, so the toolchain install is healthy.

The remaining explanation is a defect in the **aarch64 `rustc` binary** when
compiling this crate — reproducible across two very different rustc/LLVM
versions on the same board. The likely trigger is the large auto-generated
constant table in `src/advdata_constants.rs` (the BT-SIG company-identifier
list is a single multi-thousand-element `static` array); the x86_64 front end
handles it fine, the aarch64 one does not.

## The fix: cross-compile a static aarch64 binary on x86_64

Build a **statically linked `aarch64-unknown-linux-musl`** binary. musl +
`rust-lld` is self-contained, so this needs **no gcc cross-linker** and the
result has **no runtime library dependencies** on the Pi.

Prerequisites on the x86_64 host: `rustup` with a recent stable toolchain
(>= 1.79) and the musl target. The bundled `rust-lld` ships with the toolchain.

```bash
# one-time: add the target
rustup target add aarch64-unknown-linux-musl

# from the crate directory
cd Sniffle/sniffle_receiver_rust_src
rm -f Cargo.lock

# point the linker at the toolchain's bundled rust-lld (no gcc cross-toolchain needed)
LLD="$(rustc --print sysroot)/lib/rustlib/$(rustc -vV | sed -n 's/host: //p')/bin/rust-lld"
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER="$LLD" \
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_RUSTFLAGS="-Clinker-flavor=ld.lld" \
  cargo build --release --target aarch64-unknown-linux-musl
```

That produces:

```
target/aarch64-unknown-linux-musl/release/sniffle_receiver_rust
# ELF 64-bit LSB executable, ARM aarch64, statically linked, stripped
```

Copy it to the Pi, into the path `central_app_launcher.py` expects
(`Sniffle/sniffle_receiver_rust`, next to `Sniffle/python_cli/`):

```bash
scp target/aarch64-unknown-linux-musl/release/sniffle_receiver_rust \
    pi@<pi-host>:/tmp/sniffle_receiver_rust
ssh pi@<pi-host> \
  'install -m 755 /tmp/sniffle_receiver_rust ~/Blue2thprinting/Sniffle/sniffle_receiver_rust'
```

Verify on the Pi:

```bash
~/Blue2thprinting/Sniffle/sniffle_receiver_rust -h        # prints usage, exits 0
# live check against a flashed Sonoff dongle (active scan is the launcher's mode):
sudo ~/Blue2thprinting/Sniffle/sniffle_receiver_rust \
     -s=/dev/ttyUSB0 -o=/tmp/t.pcap -A --duration=12
# expect a "+10s: ... crlf_err=0 dec_err=0" status line and a "DONE:" summary
```

Let the binary self-terminate via `--duration`; wrapping it in an external
`timeout` can kill it before it flushes the pcap header, leaving a 0-byte file.

## Note for `setup_capture_helper_debian-based.sh`

On an aarch64 capture host the `build_sniffle_receiver_rust()` step will fail no
matter what — it is not the cargo-version problem that the analysis helper's
rustup gate (commit 995bcfb) addresses, so installing rustup on the Pi does not
help. On such a host, skip that build step and drop in a cross-built binary
produced as above. The 32-bit Pi Zero W is unaffected and still builds natively.
