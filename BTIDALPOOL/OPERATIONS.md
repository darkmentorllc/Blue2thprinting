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
| `--oauth-cache-ttl-seconds` | 300 | Positive Google validation cache TTL |
| `--session-ttl-seconds` | 900 | Signed v2 session lifetime |
| `--session-key-file` | none | Optional persistent HMAC key |
| `--v2-state-dir` | `./btidalpool_v2_state` | Durable manifests/chunks/receipts |

The OAuth cache stores only SHA-256 token digests and validated identity
results. It never stores plaintext OAuth tokens or refresh tokens.

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
