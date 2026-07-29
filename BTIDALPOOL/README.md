# BTIDALPOOL (Rust reimplementation)

Rust port of the BTIDALPOOL crowdsourced-database server and its two client
tools. **The original Python implementation is intentionally kept in
parallel** so the two can run side by side during the rollout — the Python
server keeps serving production traffic on its current port while the Rust
server is shaken out on a different port; flip over (or run both) when
ready.

| Concern                  | Python (still present)                                   | Rust (this folder)                |
| ------------------------ | -------------------------------------------------------- | --------------------------------- |
| Server                   | `Analysis/Server_BTIDALPOOL.py`                          | `crates/btidalpool-server`        |
| Upload client            | `Analysis/BTIDES_to_BTIDALPOOL.py`                       | `crates/btidalpool-client`        |
| Query client             | `Analysis/BTIDALPOOL_to_BTIDES.py`                       | `crates/btidalpool-client`        |
| Google OAuth token issue | `Scripts/google-SSO-redirect-and-token-print-server.py`  | _unchanged — shared by both_      |

The repository still contains the earlier Rust client/load-generator code for
protocol archaeology, but neither is part of the deployed v4-only listener or
the Android application. Those historical tools target the removed Rust
v1/v2/v3 endpoints and must not be used against the production Rust listener.
`Analysis/Tell_Me_Everything.py` continues to import the original Python
clients via the original `Analysis/`-level imports — it is unchanged by this
branch.

The `python/` directory contains historical shims for the removed Rust v1
endpoint. They are retained only as source history and must not be added to
`PYTHONPATH` for the v4-only listener. The original Python clients under
`Analysis/` remain the supported path for the original non-Rust server.

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
│   └── btidalpool-client/              # `btidalpool-client` binary (upload + query subcommands)
└── python/                             # (added in a follow-up commit) Python shims that
                                        # subprocess the Rust client so Tell_Me_Everything's
                                        # `from BTIDALPOOL_to_BTIDES import ...` keeps working.
```

The crate split is deliberate: **`btidalpool-proto` is the only place that
defines the on-the-wire encoding.** Both the server and the client depend
on it, so a protocol change happens exactly once and the type checker forces
the other side to be updated.

## Wire protocol

The production Rust listener exposes only unified BTPL v4 at `POST /v4`.
Whole-file upload/check/reconstructed query, resumable upload, and native
query are commands within that single interface; see
[`V4_PROTOCOL.md`](V4_PROTOCOL.md). `POST /`, `POST /v2`, and `POST /v3`
return 404. The separate original Python server and its clients remain
unchanged.

Every request and every response is a single CBOR-encoded value wrapped in
the framing format defined in [`crates/btidalpool-proto/src/codec.rs`](crates/btidalpool-proto/src/codec.rs):

```
off  size  field
---  ----  -------------------------------------------------------------
  0     4  MAGIC = b"BTPL"
  4     1  VERSION = 4
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

The HTTP `Content-Type` for both directions is
`application/x-btidalpool-cbor-zstd; version=4`. The Rust listener rejects
other protocol versions and content types.

## Building + testing

This workspace is independent of the other two Rust workspaces in the repo
(`Analysis/rust/` and `Analysis/BTIDES_Schema/rust/`). Build it standalone:

```sh
cd BTIDALPOOL
cargo build --release
cargo test                  # all Rust unit + integration tests
cargo test --workspace --features sql-ingest
```

The protocol crate is network-free; the server unit tests use mocked
ingest / OAuth; only the integration tests in
`crates/btidalpool-server/tests/loopback.rs` spins up an in-process TLS
listener (with a self-signed cert generated at test time). None of the tests
need MySQL, a Google account, or internet access — that's enforced by the
trait-based dependency injection at every layer.

For production: build with the `sql-ingest` feature so the server links
against the existing `Analysis/rust/BTIDES-to-SQL` library and ingests
uploads into MySQL in-process:

```sh
cargo build --release --features sql-ingest -p btidalpool-server
```

## Tell_Me_Everything.py integration

`Analysis/Tell_Me_Everything.py` is **unchanged** by this branch — its
existing imports

```python
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool
from BTIDALPOOL_to_BTIDES import retrieve_btides_from_btidalpool
```

continue to resolve to the original Python implementations at
`Analysis/BTIDES_to_BTIDALPOOL.py` / `Analysis/BTIDALPOOL_to_BTIDES.py`
(which are still present), and those still talk to the original Python
server. The historical Rust shims must not be placed ahead of `Analysis/` on
`PYTHONPATH`; they target the removed Rust v1 endpoint.

### Historical Rust-client TLS trust defaults

The non-deployed historical `btidalpool-client` binary **bundles the
BTIDALPOOL server's self-signed
certificate** (`Analysis/btidalpool.ddns.net.crt`, compiled in via
`include_bytes!`) and pins to it by default — so it talks to the production
server with no TLS flags, reproducing the old Python client's
`verify=./btidalpool.ddns.net.crt` behavior. There is no `--ca` flag (the
bundled cert covers production; on a cert rotation, rebuild the binary).
Two override flags exist:

* `--system-roots` — verify against the OS trust store (for the day the
  server gets a publicly-trusted, e.g. LetsEncrypt, cert).
* `--insecure` — accept any cert (local testing only; the shims set this
  from `BTIDALPOOL_INSECURE=1`).

The loopback QA test pins a per-run self-signed cert through the internal
`CertTrust::Pinned` Rust API (no CLI flag), which is why that variant is
retained even though it isn't exposed on the command line.

## Status

| Component | State |
| --------- | ----- |
| Workspace + Cargo deps                                          | done |
| Shared wire crate (`btidalpool-proto`): types, codec, hash      | done |
| Codec zip-bomb guards (compressed cap + streaming output cap)   | done, tested |
| Server: TLS via tiny_http + ssl-rustls                          | done |
| Server: OAuth trait + Google userinfo impl + mock for tests     | done |
| Server: identity-first limiter + separate IP abuse gate + Retry-After | done |
| Server: hashed Google-validation cache + signed short-lived sessions | done |
| Server: durable resumable manifests/chunks/atomic finalize/receipts | done |
| Server: dedup hash index + per-user logs + access log           | done |
| Server: typed request dispatch (upload / check_hash / query)    | done |
| Server: BTIDES-to-SQL ingest via the existing crate             | done (gated on `sql-ingest` feature) |
| Server: reconstructed-BTIDES query command via Tell_Me_Everything | done |
| Server: batched native Rust/MySQL normalized query command       | done |
| Server: single unified BTPL v4 endpoint                          | done |
| Historical Rust client/load generator                           | retained in source only; not deployed and not compatible with the v4-only listener |
| Original Python clients and server                              | unchanged |
| End-to-end loopback test (Rust: TLS + codec + handlers)         | 6 tests, all green |
| Wire-protocol unit tests (codec, types, hash)                   | 24 tests, all green |
