# Blue2thprinting Test Suite

A pytest-based regression suite for `Tell_Me_Everything.py` and the BTIDES
data pipeline. Designed to give an LLM-assisted contributor a fast way to
confirm a change didn't break the user-facing CLI.

## What's covered

| File | Coverage |
|---|---|
| `test_unit_helpers.py` | Pure-Python helpers: `validate_bdaddr`, BTIDES schema files load |
| `test_db_query.py` | `--bdaddr`, `--bdaddr-regex`, `--name-regex`, `--require-GATT-*`, `--require-SMP`, `--require-GPS`, `--require-LL_VERSION_IND`, `--require-LMP_VERSION_RES` against seeded data |
| `test_btides_export.py` | `--output` produces JSON that validates against `BTIDES_Schema/`; round-trips name, UUID, MSD, tx_power, GATT, EIR, SDP |
| `test_btides_import.py` | `--input-pcap` adds new BDADDRs to `bttest`, then re-querying / re-exporting reflects them |
| `test_btidalpool.py` | Live `--query-BTIDALPOOL` round-trip using a real OAuth token (skipped when no token is available) |

## Prerequisites

1. **MySQL running**, with the `user`/`a` credentials and the `bttest` database
   created. If not yet set up, run from the repo root:

   ```sh
   ./Analysis/one_time_initialization/initialize_test_database.sh
   ```

   The lookup tables (`IEEE_bdaddr_to_company`, `UUID16_to_company`,
   `BLEScope_UUID128s`) need to be populated separately by their translator
   scripts; the test suite intentionally does not touch those tables, so
   their data persists across test runs.

2. **Python deps** for tests:

   ```sh
   pip install -r Analysis/tests/requirements-test.txt
   ```

3. **(Optional) BTIDALPOOL OAuth token** for the live smoke test. Place it
   at `Analysis/tf` (the default) or set `BTIDALPOOL_TOKEN_FILE` to point
   elsewhere. Without a token, `test_btidalpool.py` is skipped — the rest of
   the suite still runs.

## Running

From the repo root (`/Users/user/Blue2thprinting/`):

```sh
# Full suite (skips BTIDALPOOL test when no token is configured)
python3 -m pytest Analysis/tests/ -v

# Skip the live BTIDALPOOL test even when a token is present
python3 -m pytest Analysis/tests/ -v -m "not btidalpool"

# Only the BTIDALPOOL smoke test
python3 -m pytest Analysis/tests/ -v -m btidalpool

# Single test
python3 -m pytest Analysis/tests/test_db_query.py::test_bdaddr_lookup_device1 -v
```

## Test data

### `fixtures/seed.sql`

Hand-crafted INSERT statements for five test devices. All use the `aa:bb:cc:`
prefix so they're easy to filter in the DB and don't collide with real OUI
lookups. Loaded into `bttest` once per session by `conftest.py`.

| Device | Coverage |
|---|---|
| `aa:bb:cc:11:22:01` LE public | name, UUID16 (Heart Rate), flags, tx_power, MSD (Apple) |
| `aa:bb:cc:11:22:02` LE random | full GATT tree (services + chars + values), GPS |
| `aa:bb:cc:11:22:03` BT Classic | EIR name, CoD, SDP record |
| `aa:bb:cc:11:22:04` LE public | LL_VERSION_IND (TI), LMP_VERSION_RES (CSR) |
| `aa:bb:cc:11:22:05` LE public | SMP Pairing Req/Res (legacy) |

### `fixtures/import.pcap`

Tiny (~1 KB) pcap with the first 15 BLE advertising packets sliced from the
project's main `ExampleData/2024-05-16-01-01-25_up-apl01.pcap`. Contains 10
distinct BDADDRs (none starting with `aa:bb:cc:`), used by
`test_btides_import.py` to verify the PCAP → BTIDES → SQL pipeline.

## Database isolation

`conftest.py` defines two scopes:

- `test_db` (session-scoped) — wipes the device-data tables in `bttest` and
  loads `seed.sql` once per pytest session. Lookup tables are preserved.
- `db_clean` (function-scoped) — re-resets the device-data tables before AND
  after each test that needs to mutate the DB (used by import tests).

The DB wipe targets ~70 device-data tables explicitly; lookup tables
(`IEEE_bdaddr_to_company`, `UUID16_to_company`, `USB_CID_to_company`,
`BLEScope_UUID128s`) are listed in `DEVICE_DATA_TABLES` exclusions in
`conftest.py` and never touched.

## Adding new tests

1. New seeded data → add INSERTs to `seed.sql` using the `aa:bb:cc:11:22:NN`
   prefix (next free is `06`).
2. New CLI behavior to test → add a function to `test_db_query.py` using
   the `run_tme` fixture and the `rendered_bdaddrs()` helper.
3. New BTIDES path → add to `test_btides_export.py` if it's an output path,
   or `test_btides_import.py` if it's an input path.
4. If you can't find suitable example data locally, query BTIDALPOOL:
   `python3 Tell_Me_Everything.py --query-BTIDALPOOL --token-file ./tf <filters> --output /tmp/sample.btides`
   and adapt one device's data into `seed.sql`.
