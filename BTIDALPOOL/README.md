# BTIDALPOOL (Rust reimplementation)

Rust port of the BTIDALPOOL crowdsourced-database server and its two client
tools. Replaces three Python files that previously lived in `Analysis/` and
`Scripts/`:

| Old (Python)                                              | New (Rust)                    |
| --------------------------------------------------------- | ----------------------------- |
| `Analysis/Server_BTIDALPOOL.py`                           | `crates/btidalpool-server`    |
| `Analysis/BTIDES_to_BTIDALPOOL.py` (upload client)        | `crates/btidalpool-client`    |
| `Analysis/BTIDALPOOL_to_BTIDES.py` (query client)         | `crates/btidalpool-client`    |
| `Scripts/google-SSO-redirect-and-token-print-server.py`   | _unchanged_ (Google OAuth flow stays in Python; the Rust server only validates already-issued tokens) |

The two old Python client tools are merged into a single `btidalpool` Rust
binary with `upload` and `query` subcommands. Per requirement #6, the
user-facing CLI of `Tell_Me_Everything.py` does **not** change; the existing
`BTIDES_to_BTIDALPOOL.py` / `BTIDALPOOL_to_BTIDES.py` filenames stay around
as thin Python shims that exec the Rust binary (added in a follow-up commit
that lands `python/`).

## Why a rewrite

The free-tier AWS VM hosting BTIDALPOOL chokes on large JSON POSTs and on
concurrent traffic. Switching to a compiled language with cheaper memory
per connection, and switching from raw JSON to **CBOR-encoded payloads
wrapped in zstd compression**, addresses both bottlenecks.

Concrete wins (vs. the Python server):

1. **Bytes on the wire**: zstd on JSON-ish content typically compresses
   5-20x. A 20 MiB BTIDES upload becomes 1-4 MiB over the wire.
2. **Server memory per request**: the codec enforces a hard cap on
   decompressed size with a streaming decoder, so a hostile sender cannot
   trigger hundreds of MB of allocation by sending a zip bomb.
3. **CPU per request**: CBOR parsing is faster than `json.loads` on the
   envelope, and Rust handles concurrency without the GIL.

## Workspace layout

```
BTIDALPOOL/
├── Cargo.toml                          # workspace manifest
├── crates/
│   ├── btidalpool-proto/               # shared wire types + codec (this is THE protocol)
│   │   └── src/
│   │       ├── codec.rs                # CBOR-in-zstd framing, zip-bomb guard, unit tests
│   │       ├── hash.rs                 # SHA1 of canonical JSON (matches Python server)
│   │       ├── wire.rs                 # Envelope / Payload / Response / ErrorKind / QueryParams
│   │       └── lib.rs
│   ├── btidalpool-server/              # `btidalpool-server` binary
│   └── btidalpool-client/              # `btidalpool` binary (upload + query subcommands)
└── python/                             # (added in a follow-up commit) Python shims that
                                        # subprocess the Rust client so Tell_Me_Everything's
                                        # `from BTIDALPOOL_to_BTIDES import ...` keeps working.
```

The crate split is deliberate: **`btidalpool-proto` is the only place that
defines the on-the-wire encoding.** Both the server and the client depend
on it, so a protocol change happens exactly once and the type checker forces
the other side to be updated.

## Wire protocol (v1)

Every request and every response is a single CBOR-encoded value wrapped in
the framing format defined in [`crates/btidalpool-proto/src/codec.rs`](crates/btidalpool-proto/src/codec.rs):

```
off  size  field
---  ----  -------------------------------------------------------------
  0     4  MAGIC = b"BTPL"
  4     1  VERSION (currently 1)
  5     4  declared_uncompressed_len (u32, big-endian)
  9     N  zstd-compressed CBOR bytes
```

The decoder enforces two independent caps:

* **Compressed cap** (default 20 MiB) — rejected from the frame length
  before any allocation happens. Stops a few-GB POST dead at the door.
* **Decompressed cap** (default 200 MiB) — enforced *during* streaming
  decompression by a wrapper that aborts the moment the running output
  would exceed the cap. This is the actual zip-bomb defense; see the
  `zip_bomb_is_rejected_during_streaming_decode` test in `codec.rs`.

The header's declared length is *not* trusted to size allocations —
it's only used as a consistency check after streaming decode completes
(a lying header is rejected with `HeaderMismatch`).

The HTTP `Content-Type` for both directions is `application/x-btidalpool-cbor-zstd`
(see `btidalpool_proto::CONTENT_TYPE`). The server rejects POSTs with any
other content type, so an old Python client trying to POST raw JSON to the
new endpoint gets a clean error instead of a mysterious parse failure.

## Building + testing

This workspace is independent of the other two Rust workspaces in the repo
(`Analysis/rust/` and `Analysis/BTIDES_Schema/rust/`). Build it standalone:

```sh
cd BTIDALPOOL
cargo build --release       # release binaries needed for the Python shim test
cargo test                  # all Rust unit + integration tests
python3 -m unittest python/test_shim_loopback.py    # Python shim end-to-end test
```

The protocol crate is network-free; the server unit tests use mocked
ingest / OAuth; only the integration tests in
`crates/btidalpool-server/tests/loopback.rs` and the Python shim test
spin up an in-process TLS listener (with a self-signed cert generated at
test time). None of the tests need MySQL, a Google account, or internet
access — that's enforced by the trait-based dependency injection at every
layer.

For production: build with the `sql-ingest` feature so the server links
against the existing `Analysis/rust/BTIDES-to-SQL` library and ingests
uploads into MySQL in-process:

```sh
cargo build --release --features sql-ingest -p btidalpool-server
```

## Tell_Me_Everything.py integration

`Analysis/Tell_Me_Everything.py` now adds `BTIDALPOOL/python/` to
`sys.path` near the top of the file, so its existing imports

```python
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool
from BTIDALPOOL_to_BTIDES import retrieve_btides_from_btidalpool
```

resolve to the new shims here instead of the deleted Analysis/-level
files. The function signatures are preserved verbatim, so no other
caller needs to change.

The shims read three environment variables when spawning the Rust binary:

| Var | Purpose | Default |
| --- | ------- | ------- |
| `BTIDALPOOL_SERVER_URL` | URL of the BTIDALPOOL HTTPS endpoint. | `https://btidalpool.ddns.net:3567` |
| `BTIDALPOOL_CA`        | PEM file to pin against the server's TLS cert. | `./btidalpool.ddns.net.crt` (if present) |
| `BTIDALPOOL_INSECURE`  | If `1`, skip cert verification (loopback testing only). | unset |
| `BTIDALPOOL_BINARY`    | Override the binary lookup; useful for ops installs. | (auto-search) |

## Status

| Component | State |
| --------- | ----- |
| Workspace + Cargo deps                                          | done |
| Shared wire crate (`btidalpool-proto`): types, codec, hash      | done |
| Codec zip-bomb guards (compressed cap + streaming output cap)   | done, tested |
| Server: TLS via tiny_http + ssl-rustls                          | done |
| Server: OAuth trait + Google userinfo impl + mock for tests     | done |
| Server: per-IP rate limiter (simultaneous + per-day, with guard) | done |
| Server: dedup hash index + per-user logs + access log           | done |
| Server: typed request dispatch (upload / check_hash / query)    | done |
| Server: BTIDES-to-SQL ingest via the existing crate             | done (gated on `sql-ingest` feature) |
| Server: Tell_Me_Everything subprocess query                     | done |
| Client: ureq + rustls with CA pinning / `--insecure` for tests  | done |
| Client: `upload` / `query` / `check-hash` subcommands           | done |
| Python shims (preserve `Tell_Me_Everything.py` imports)         | done |
| End-to-end loopback test (Rust: TLS + codec + handlers)         | 8 tests, all green |
| End-to-end loopback test (Python shim → Rust binary → server)   | 2 tests, all green |
| Wire-protocol unit tests (codec, types, hash)                   | 18 tests, all green |
