# BTIDALPOOL Rust server operations

## Production layout

The current host uses:

- service: `BTIDALPOOL-rust.service`
- versioned unit source: `BTIDALPOOL/systemd/BTIDALPOOL-rust.service`
- listener: TLS on `0.0.0.0:3568`
- protocol endpoint: `POST /v4` (the only Rust wire endpoint)
- health endpoint: `GET /healthz`
- legacy pool: `Analysis/pool_files_rust`
- per-user logs: `Analysis/user_logs_rust`
- access log: `Analysis/user_access_rust.log`
- resumable state: `Analysis/btidalpool_v2_state` (historical directory name retained in place)

Never replace or empty the pool, logs, database, or resumable state during
deployment. The original Python server is separate and must not be modified
as part of Rust listener deployment.

## Build and test

```sh
cd BTIDALPOOL
cargo test --workspace
cargo test --workspace --features sql-ingest
cargo build --release --features sql-ingest -p btidalpool-server
```

Production must use the `sql-ingest` feature. A binary without it saves pool
files but does not update MariaDB.

## Session signing key

For sessions to survive a service restart, provision one random binary key,
owned by the service user and mode `0600`:

```sh
umask 077
head -c 32 /dev/urandom > /home/ubuntu/BTIDALPOOL/session_hmac.key
chmod 600 /home/ubuntu/BTIDALPOOL/session_hmac.key
```

Pass it with `--session-key-file`. Never print, log, commit, or include this
file in a general source archive. If the option is omitted, the server safely
generates an in-memory key; existing sessions then expire on restart.

## Relevant server options

| Option | Default | Purpose |
| --- | ---: | --- |
| `--max-concurrent` | 10 | Simultaneous requests per authenticated identity |
| `--max-per-day` | 100 | Rolling-day requests per authenticated identity |
| `--max-ip-concurrent` | 50 | Simultaneous pre-auth abuse cap per IP |
| `--max-ip-per-day` | 1000 | Rolling-day pre-auth abuse budget per IP |
| `--max-expensive-work-units` | 4 | Shared weighted budget: legacy query=4, upload/finalize=2, native query=1 |
| `--max-global-whole-uploads` | 2 | Process-wide v4 whole-file upload cap |
| `--max-global-queries` | 1 | Process-wide query cap |
| `--max-global-native-queries` | 4 | Process-wide native-query cap |
| `--max-global-chunk-puts` | 4 | Process-wide resumable chunk-write cap |
| `--max-global-finalizes` | 2 | Process-wide resumable finalize cap |
| `--overload-retry-after-seconds` | 2 | `Retry-After` returned with overload 503 |
| `--max-query-records` | 100 | Maximum records in one query response |
| `--max-native-query-rows` | 50,000 | Maximum normalized rows in one native-query response |
| `--oauth-cache-ttl-seconds` | 300 | Positive Google validation cache TTL |
| `--session-ttl-seconds` | 900 | Signed v4 session lifetime |
| `--session-key-file` | none | Optional persistent HMAC key |
| `--resumable-state-dir` | `./btidalpool_resumable_state` | Durable manifests/chunks/receipts |

The OAuth cache stores only SHA-256 token digests and validated identity
results. It never stores plaintext OAuth tokens or refresh tokens.

Identity/IP quota rejection and host-capacity rejection are deliberately
different:

- HTTP 429 / `rate_limited`: the caller exceeded its own quota.
- HTTP 503 / `server_busy`: global CPU/RAM capacity is currently occupied.

Both include a positive integer `Retry-After` delta-seconds header. Clients
should add jitter, preserve resumable state, and replay the same idempotent
operation after the delay.

The production unit also applies `MemoryHigh=350M`, `MemoryMax=450M`, and
`TasksMax=128`. The query subprocess runs inside that cgroup. These are a last
line of defense; admission control should normally reject work before the hard
limit is approached.

## 1 GiB host capacity measurements

Measurements on the production one-vCPU, approximately 1 GiB host used a
real 100-record Samsung query against `bt2` and exact 10 MiB uploads:

| Workload | Safe cap | Measured behavior |
| --- | ---: | --- |
| Max-result query | 1 | 100 records in 12.1–13.5 s; about 217 MiB Python RSS / 250 MiB service cgroup |
| Two max-result queries | unsafe | both exceeded 30 s; about 372 MiB cgroup, severe memory pressure |
| v4 exact 10 MiB whole upload | 2 | about 245 MiB cgroup at concurrency 2; concurrency 4 stalled |
| v4 exact 10 MiB finalize | 2 | about 303 MiB cgroup at concurrency 2; concurrency 3 entered memory pressure |
| v4 status | 32 tested | about 1,162 requests/s, p99 121 ms, zero errors |

The direct query-engine cap comparison returned:

| Max records | Wall time | Peak RSS | Encoded JSON |
| ---: | ---: | ---: | ---: |
| 25 | 9.57 s | 217,072 KiB | 33,446 bytes |
| 50 | 10.32 s | 217,120 KiB | 56,744 bytes |
| 100 | 12.13 s | 217,260 KiB | 105,404 bytes |

Reducing the record cap barely changes peak memory because database
scan/materialization dominates. Keep 100 records for compatibility and
use the global one-query admission cap. A lower cap can improve individual
latency and response size, but it does not make two concurrent queries safe
on this host.

### Native-query measurements

The v4 native-query engine keeps the database schema unchanged, but batches address
selection and fetches selected rows once per table. Against the same live
`bt2` data, a Samsung name query returned the full 100-device cap and 944
normalized rows without truncation:

| Parallel native queries | Throughput | p99 | Peak isolated server RSS |
| ---: | ---: | ---: | ---: |
| 1 | 4.41 req/s | 227 ms | 23.8 MiB |
| 2 | 5.05 req/s | 396 ms | 38.7 MiB |
| 4 | 5.11 req/s | 782 ms | 70.9 MiB |
| 8 | 5.20 req/s | 1.53 s | 86.9 MiB |
| 16 | 5.12 req/s | 3.12 s | 124.1 MiB |
| 32 | 4.89 req/s | 6.53 s | 170.2 MiB |

The one-vCPU host is already saturated at concurrency 2; throughput plateaus
near 5.2 requests/s while latency and retained allocator memory continue to
grow. The production cap is therefore 4, not 8 or 32. Four admits a short
burst with about 71 MiB peak server RSS; additional clients receive typed 503
plus `Retry-After` and should retry with jitter.

A broad `.*` BDADDR query returned 100 devices / 437 rows in 403 ms, and a
`^00:` query returned 100 devices / 264 rows in 1.27 s cold (about 0.27 s
warm). Neither hit the 50,000-row cap. Keep the 100-device maximum: the
native path makes it safe, and lowering it is unnecessary for the expected
class of 20 students plus one instructor. The admission cap, not a lower
record cap, is the correct overload control.

## Safe deployment

1. Record the current unit, binary path/hash, process identity, listening
   sockets, data paths, and repository status.
2. Create a timestamped backup directory outside the live binary path.
3. Copy the current binary and systemd unit into it. Record their SHA-256
   hashes. Do not put upload/database data into this deployment backup.
4. Build and test off-host or in a non-live build directory.
5. Upload the new binary beside the live binary as a temporary file. Verify
   its SHA-256, ownership, mode, and `--help` output.
6. Add `--resumable-state-dir` and `--session-key-file` to the unit. Keep the
   existing state path even when it has the historical `btidalpool_v2_state`
   name. Run
   `systemd-analyze verify` before restarting.
7. Rename the temporary binary over the live path atomically.
8. Run `systemctl daemon-reload` and restart `BTIDALPOOL-rust.service`.
9. Verify service status, PID/executable identity, port 3568, health, a v4
   session, non-destructive manifest/status flow, read-only native query, and
   recent logs. Verify `POST /`, `/v2`, and `/v3` all return 404.

Rollback restores the backed-up binary and unit atomically, reloads systemd,
and restarts the same service. Do not remove the resumable state directory
during rollback.

## Verification

```sh
systemctl is-active BTIDALPOOL-rust.service
systemctl show BTIDALPOOL-rust.service -p MainPID -p ExecStart -p User
ss -ltnp | grep ':3568'
curl --cacert Analysis/btidalpool.ddns.net.crt \
  https://btidalpool.ddns.net:3568/healthz
journalctl -u BTIDALPOOL-rust.service --since '-10 minutes' --no-pager
```

Do not place access tokens or session tokens on a shell command line during
authenticated checks. Use an existing test client that reads credentials from
its protected credential store, and ensure logs contain summaries only.
