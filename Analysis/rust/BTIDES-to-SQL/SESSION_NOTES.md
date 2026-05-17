# Session continuation notes — BTIDES-to-SQL (originally btides_to_sql_rs)

Notes for picking this work up in a fresh Claude Code session. Not user-facing
docs (those are in `README.md`); these are the things that aren't obvious from
the code or commit message.

## Current state (commit `ecffa71` on `BlueZ_RTL_VSC_experimental`)

- Rust port of `Analysis/BTIDES_to_SQL.py` lives at
  `Analysis/rust/BTIDES-to-SQL/` (binary crate, ~1900 LOC in `src/main.rs`).
- Verified byte-identical to the Python importer on every table populated by
  the test corpora. Verification method: per-table
  `SHA2(GROUP_CONCAT(SHA2(row, 256) ORDER BY ...), 256)` snapshots, then `diff`.
- Single-file: ~56x faster than Python default, ~88x with `--writer-threads 4`.
- Multi-file (8 files × 12k rows): ~184x faster than Python default, with the
  shell-parallel mode winning at ~0.32s wall.
- The `BlueZ_RTL_VSC_experimental` branch in the main worktree
  (`/Users/user/Blue2thprinting`) is 2 commits ahead of `origin` — the cherry-
  picked Rust commit, plus a pre-existing local commit on top of `origin/HEAD`.
  Has not been pushed.

## Test corpus

The big BTIDES file used as the primary test target:
```
/Users/user/Documents/sniffing/Android HCI Logs/2026-01-18-WiGLE_MotoGPlay_Dev23/hci_snoop20260118151956..btides.processed
```
4894 entries, produces 12065 rows across 31 non-empty tables in `bttest`.

Multi-file corpus generator (still present in /tmp during the session):
```
/tmp/make_n_btides.py N      # writes /tmp/multi_{1..N}.btides with distinct OUIs
/tmp/make_big_btides.py N    # writes /tmp/big.btides = N copies (distinct OUIs)
```

## DB verification harness (still in /tmp)

```
/tmp/wipe_bttest.sh            # truncates all 67 BTIDES tables in bttest
/tmp/snapshot_bttest.sh OUT    # SHA256-per-table snapshot (uses SHA2(_,256)
                               # because MySQL 9.6 dropped MD5())
```

Standard correctness check:
```
cd /Users/user/Blue2thprinting/Analysis
/tmp/wipe_bttest.sh
/Users/user/Blue2thprinting/venv/bin/python BTIDES_to_SQL.py --input <file> --use-test-db --quiet-print
/tmp/snapshot_bttest.sh /tmp/snap_py.txt

/tmp/wipe_bttest.sh
../Analysis/rust/target/release/BTIDES-to-SQL --input <file> --use-test-db
/tmp/snapshot_bttest.sh /tmp/snap_rs.txt

diff /tmp/snap_py.txt /tmp/snap_rs.txt    # expect 0 lines
```

## Known things that work

- All `parse_*Array` paths from `BTIDES_to_SQL.py`:
  - AdvData (all 25+ TLV types)
  - LL (including the C2P-PING_RSP-implies-P2C-PING_REQ heuristic and
    the C2P-PHY_REQ/RSP skip rule)
  - LMP (base opcodes + escape-127 ext opcodes + the LMP_NAME_RES per-bdaddr
    defragmenter with the rstrip-trailing-00 workaround)
  - HCI (Remote Name Request Complete)
  - L2CAP (CONN_PARAM_UPDATE_REQ/RSP)
  - ATT (FIND_INFORMATION_RSP / READ_REQ / READ_RSP correlation;
    decomposes char-declaration value blobs into GATT_characteristics rows
    using the same little-endian-UUID-or-2-byte-UUID16 logic as Python)
  - GATT (services + characteristics + char_value io_array + descriptor
    formats for UUIDs 2900/2901/2902/2903/2904/2905)
  - SMP (Pairing_Request/Response)
  - EIR (PSRM + CoD only — matches Python)
  - SDP (ERROR_RSP and Common with raw bytes)
  - GPS (the read-modify-write logic from `parse_all_GPSArrays_batched`)

- `convert_UUID128_to_UUID16_if_possible` (BT base UUID match) in Rust.

- `INSERT IGNORE` semantics for duplicates, including idempotency under
  re-import (verified: same file imported twice produces an unchanged snapshot).

- Cross-process retry on InnoDB deadlock (error 1213) and lock-wait-timeout
  (1205), with exponential-backoff + jitter. Tested with 4 parallel processes
  importing the same file: every process retried, every process eventually
  succeeded, final state matched the single-import reference.

## Known things that haven't been exercised in tests

These code paths exist in the Rust binary and mirror the Python, but the
files I tested with didn't have data of these types:

- GPS rows. The WIGLE-derived BTIDES files I checked have no `GPSArray`.
  The code is a faithful port of `parse_all_GPSArrays_batched`, but
  empirically untested against a WIGLE-bearing input. **First thing to
  exercise if you have a WIGLE BTIDES file handy.**
- A few LMP/LMP_EXT opcodes that didn't appear in the test corpus
  (LMP_ACCEPTED_EXT, LMP_NOT_ACCEPTED_EXT, LMP_POWER_CONTROL_REQ/RES,
  LMP_CHANNEL_CLASSIFICATION). The full_pkt_hex_str-decoding paths are
  translated directly from the Python; I'd verify by feeding a file that
  exercises them.
- SDP_Common rows: the test file had 0 SDP entries. Code is a straight port,
  but a real BTC SDP-bearing file would exercise the VARBINARY byte path.

## Gotchas you'll hit in the next session

1. **MySQL 9.6 dropped `MD5()`.** Use `SHA2(_, 256)`. The snapshot script
   already does. If you see "FUNCTION bttest.MD5 does not exist", that's why.

2. **`BTIDES_to_SQL.py` opens schemas via relative path `./BTIDES_Schema/`.**
   You MUST `cd Analysis` before running the Python importer, or pre-create
   that path. The main worktree (`/Users/user/Blue2thprinting`) has the
   submodule in place; worktrees usually don't, and `git submodule update
   --init Analysis/BTIDES_Schema` from the worktree root fixes it.

3. **Python venv lives at `/Users/user/Blue2thprinting/venv`.** Worktrees
   don't get it by default. The Rust binary needs no venv.

4. **MySQL credentials are hardcoded** at `user`/`a` in `TME_helpers.py`
   and also as defaults in the Rust binary. Override with `--db-user`,
   `--db-password`, `--db-host` if needed.

5. **The Python importer commits per row.** That's why it can match Rust on
   correctness without needing a transaction — every row is its own
   transaction. The Rust importer uses one big transaction per process
   (or one per lane in `--writer-threads N` mode). If you ever want to
   tee the Rust importer through autocommit-per-row for closer parity in
   the failure-recovery semantics, the change is small but you'll give up
   most of the speedup.

6. **The `EIR_bdaddr_to_DevID` schema only exists for EIR**, not LE AdvData.
   The Python `import_AdvData_DeviceID` reflects this; the Rust version
   intentionally drops non-EIR DeviceID inserts.

7. **`HCI_bdaddr_to_name` has 3 columns** but Python's `import_HCI_Remote_Name_Request_Complete`
   only passes 2 values and hardcodes `status = 0` as a SQL literal.
   The Rust version emits the literal 0 in the row Vec to keep the bulk
   `INSERT IGNORE` placeholder count consistent. There's a
   `bulk_insert mismatch` debug eprintln that fires if you regress this
   kind of bug — leave it as the safety net.

## Possible follow-up work, in rough order of value

1. **Push to origin once the user is satisfied.** Commit is `ecffa71` on
   `BlueZ_RTL_VSC_experimental` in `/Users/user/Blue2thprinting`. Has not
   been pushed.

2. **Write a Cargo integration test** that:
   - spins up a small bttest fixture (TRUNCATE the standard tables),
   - runs Python and Rust on a checked-in BTIDES sample,
   - asserts the snapshot diff is 0 lines.

   The shell scripts in /tmp do this manually today; locking the behavior
   into `tests/` would prevent silent regressions.

3. **Round-trip the GPS path** with a real WIGLE BTIDES file. See "Known
   things that haven't been exercised" above.

4. **Wire into the existing `Import_All_HCI_and_PCAP.py` workflow.** That
   script currently calls `BTIDES_to_SQL.py` once per produced BTIDES.
   Replacing the call with the Rust binary (and feeding it the post-prod
   BTIDES files in shell-parallel mode) should be the single highest-
   throughput change.

5. **Schema validation, if you want it.** The Rust binary always trusts
   the input (= Python's `--skip-schema-validation`). For untrusted input
   you'd want a JSON-schema validator (the `jsonschema` crate, or
   `valico`) wired in at the top of the entry loop. Expect the perf gap
   to narrow from ~56x to ~18x, like the Python `--skip-schema-validation`
   number suggests.

6. **Replace `eprintln!` debug-mismatch in `bulk_insert` with a hard
   `debug_assert!`** if you trust the row-width invariants enough. The
   eprintln saved me during initial bring-up; it could go now that the
   code is settled.

7. **Push docs upstream** — `Analysis/README.md` (if there is one) might
   want a pointer to `Analysis/rust/BTIDES-to-SQL/README.md`.

## Files & paths

- Code: `Analysis/rust/BTIDES-to-SQL/{Cargo.toml, src/main.rs, src/lib.rs,
        README.md, .gitignore}` (workspace member of `Analysis/rust/`; the
        workspace owns the single Cargo.lock at `Analysis/rust/Cargo.lock`)
- Binary after build: `Analysis/rust/target/release/BTIDES-to-SQL`
- Python reference: `Analysis/BTIDES_to_SQL.py` (+ TME/ + BTIDES_Schema/ submodule)
- Wipe helper: `/tmp/wipe_bttest.sh` (regenerable; see commit log earlier in
  the chat for the table list)
- Snapshot helper: `/tmp/snapshot_bttest.sh` (uses SHA2(_,256))
- Test corpus generator: `/tmp/make_n_btides.py`, `/tmp/make_big_btides.py`

## Commit ancestry

```
ecffa71  Add Analysis/rust/BTIDES-to-SQL (formerly btides_to_sql_rs) (this commit, BlueZ_RTL_VSC_experimental)
e677e54  Add Analysis/SDP_to_BTIDES.py: convert sdptool XML to BTIDES
8f2b932  central_app_launcher: 7 fixes from NYC Day-2&3 log analysis
```
