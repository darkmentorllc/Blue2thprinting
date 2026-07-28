# BTIDALPOOL Rust server operations

## Production layout

The current host uses:

- service: `BTIDALPOOL-rust.service`
- versioned unit source: `BTIDALPOOL/systemd/BTIDALPOOL-rust.service`
- listener: TLS on `0.0.0.0:3568`
- v1 endpoint: `POST /`
- v2 endpoint: `POST /v2`
- health endpoint: `GET /healthz`
- legacy pool: `Analysis/pool_files_rust`
- per-user logs: `Analysis/user_logs_rust`
- access log: `Analysis/user_access_rust.log`
- recommended v2 state: `Analysis/btidalpool_v2_state`

The v2 directory is additive. Never replace or empty the legacy pool, logs,
database, or v2 state during deployment.

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
| `--max-expensive-work-units` | 2 | Shared weighted budget: query=2, v1 upload/finalize=1 |
| `--max-global-v1-uploads` | 2 | Process-wide v1 whole-file upload cap |
| `--max-global-queries` | 1 | Process-wide query cap |
| `--max-global-chunk-puts` | 4 | Process-wide v2 chunk-write cap |
| `--max-global-finalizes` | 2 | Process-wide v2 finalize cap |
| `--overload-retry-after-seconds` | 2 | `Retry-After` returned with overload 503 |
| `--max-query-records` | 100 | Maximum records in one query response |
| `--oauth-cache-ttl-seconds` | 300 | Positive Google validation cache TTL |
| `--session-ttl-seconds` | 900 | Signed v2 session lifetime |
| `--session-key-file` | none | Optional persistent HMAC key |
| `--v2-state-dir` | `./btidalpool_v2_state` | Durable manifests/chunks/receipts |

The OAuth cache stores only SHA-256 token digests and validated identity
results. It never stores plaintext OAuth tokens or refresh tokens.

Identity/IP quota rejection and host-capacity rejection are deliberately
different:

- HTTP 429 / `rate_limited`: the caller exceeded its own quota.
- HTTP 503: global CPU/RAM capacity is currently occupied. V2 uses the typed
  `server_busy` kind; v1 retains its existing `rate_limited` body kind so
  already-deployed v1 decoders remain compatible.

Both include a positive integer `Retry-After` delta-seconds header. Clients
should add jitter, preserve v2 resume state, and replay the same idempotent
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
| v1 exact 10 MiB upload | 2 | about 245 MiB cgroup at concurrency 2; concurrency 4 stalled |
| v2 exact 10 MiB finalize | 2 | about 303 MiB cgroup at concurrency 2; concurrency 3 entered memory pressure |
| v2 status | 32 tested | about 1,162 requests/s, p99 121 ms, zero errors |

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

## Safe deployment

1. Record the current unit, binary path/hash, process identity, listening
   sockets, data paths, and repository status.
2. Create a timestamped backup directory outside the live binary path.
3. Copy the current binary and systemd unit into it. Record their SHA-256
   hashes. Do not put upload/database data into this deployment backup.
4. Build and test off-host or in a non-live build directory.
5. Upload the new binary beside the live binary as a temporary file. Verify
   its SHA-256, ownership, mode, and `--help` output.
6. Add `--v2-state-dir` and `--session-key-file` to the unit. Run
   `systemd-analyze verify` before restarting.
7. Rename the temporary binary over the live path atomically.
8. Run `systemctl daemon-reload` and restart `BTIDALPOOL-rust.service`.
9. Verify service status, PID/executable identity, port 3568, health, one
   authenticated v1 request, a non-destructive v2 manifest/status flow, and
   recent logs.

Rollback restores the backed-up binary and unit atomically, reloads systemd,
and restarts the same service. Do not remove the v2 state directory during
rollback; it is harmless to the v1 binary and is required to resume after a
future redeploy.

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
