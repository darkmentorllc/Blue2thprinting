# BTIDES-to-SQL

Rust port of `Analysis/BTIDES_to_SQL.py`. Imports BTIDES JSON files into
the `bt2` (production) or `bttest` (test) MySQL database, byte-for-byte
identical to the Python importer on every table I've tested.

Also publishes a Rust library (`BTIDES_to_SQL`) used by sibling tools such
as `import-all-BTIDES --to-SQL` (which calls `import_files_with_pool`
directly to avoid per-file process spawn).

## Build

```bash
cd Analysis/rust/BTIDES-to-SQL
cargo build --release
```

Binary lands at `target/release/BTIDES-to-SQL`.

## Usage

```
BTIDES-to-SQL --input <file.btides> [--input <other.btides> ...]
              [--use-test-db]
              [--reader-threads N]   # parse N files in parallel (default 1)
              [--writer-threads N]   # split DB writes across N connections (default 1)
              [--deadlock-retries N] # retry InnoDB 1213/1205 victims (default 8)
              [--verbose]
              [--db-host HOST] [--db-user USER] [--db-password PW]
```

## Recommended invocation patterns

- **One file, single process:** default flags are fine.
- **Many files, single process:** `--reader-threads 8 --writer-threads 4`.
  All rows funnel into a single transaction (or N transactions if writer-threads > 1),
  so a crash mid-import doesn't leave you guessing what landed.
- **Many files, max throughput:** shell-parallel, one process per file. Each
  process retries on deadlock automatically.
  ```bash
  find logs/ -name '*.btides*' -print0 \
    | xargs -0 -n 1 -P 8 -I {} \
        Analysis/rust/BTIDES-to-SQL/target/release/BTIDES-to-SQL \
        --input {} --use-test-db
  ```

## Why it's faster than the Python importer

Mostly: bulk multi-row `INSERT IGNORE` inside one transaction, vs. the
Python's per-row `INSERT IGNORE` + per-row `commit()`. The Python also
spends ~67% of its CLI wall time in `jsonschema` validation by default;
the Rust binary trusts the input (matching `--skip-schema-validation`
semantics on the Python side).

On a 4894-entry / 12k-row BTIDES file:

| Variant                                 | Wall (s) | Speedup |
|-----------------------------------------|----------|---------|
| Python default (with schema validation) | ~7.9     | 1×      |
| Python --skip-schema-validation         | ~2.5     | ~3×     |
| Rust (this binary, single writer)       | ~0.14    | ~56×    |
| Rust + `--writer-threads 4`             | ~0.09    | ~88×    |

On 8 files × 12k rows:

| Variant                                 | Wall (s) | Speedup |
|-----------------------------------------|----------|---------|
| Python: 8 inputs sequential             | ~59      | 1×      |
| Python: 8 shell-parallel processes      | ~11      | 5.4×    |
| Rust 1r/1w                              | 0.94     | 63×     |
| Rust 8r/4w                              | 0.59     | 100×    |
| Rust 8 shell-parallel                   | 0.32     | 184×    |

## Cross-process safety

Importing the same data from multiple processes is safe:

- All `UNIQUE` keys span every non-`id` column, so `INSERT IGNORE`
  collapses identical rows whether they were already in the DB or
  inserted by a sibling process.
- `--deadlock-retries N` (default 8) catches InnoDB error 1213
  (deadlock victim) and 1205 (lock-wait-timeout); each retry uses
  exponential backoff with jitter. INSERT IGNORE makes retries idempotent.
- The one non-deterministic-under-race spot is the GPS importer's
  read-modify-write path (promote an existing `rssi=0` row via UPDATE).
  Last-write-wins on `rssi` when two processes both see the same `rssi=0`
  row. Schema correctness is preserved; only the stored RSSI value is
  schedule-dependent. To get strict determinism, run GPS-bearing files
  through a single importer invocation.

## Verification helpers

The test harness uses two scripts (originally in `/tmp/`, see top-level
session notes):

- `wipe_bttest.sh` — truncates every BTIDES-related table in `bttest`.
- `snapshot_bttest.sh OUT` — writes per-table `SHA2(GROUP_CONCAT(SHA2(row, 256)
  ORDER BY ...), 256)` to OUT. `diff` the snapshots after a Python run and
  a Rust run; matching = byte-identical DB state.

MySQL 9.6 dropped `MD5()`, so the snapshotter uses `SHA2(_, 256)`.
