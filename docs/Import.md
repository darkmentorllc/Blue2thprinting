
# Import data into MySQL

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the capture device (the UP^2 in this case.) Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

## One time setup

**Linux Software Setup**: You should already have the necessary MySQL (MariaDB) database and tshark tools installed from the above apt-get commands.

```
cd ~/Blue2thprinting
sudo ./setup_analysis_helper_ubuntu2404.sh
```

**macOS Software Setup**: macOS cannot be used for collection, but it can be used for analysis of files collected on other platforms. You must first [install HomeBrew](https://brew.sh/), and then run `brew install mysql`. Then also edit `/usr/local/etc/my.cnf` and add `secure_file_priv = /tmp` at the end of the file, and then start the mysql server with `/usr/local/opt/mysql/bin/mysqld_safe --datadir=/usr/local/var/mysql`.

Then run

```
cd ~/Blue2thprinting
sudo ./setup_analysis_helper_macOS.sh
```

The above `setup_analysis_helper*.sh` scripts should be re-run if you ever do a "git pull" in the `Blue2thprinting/public` directory, which contains the Bluetooth Assigned Numbers information, to get updated assigned vendor UUID16s.

## Build the Rust import tools (one-time)

All the bulk import paths below now use the Rust ports of the original Python importers — they're considerably faster, share a connection pool across workers, and (for `import-all-BTIDES --to-SQL`) handle MySQL deadlock retries automatically. Build them once:

```
cd ~/Blue2thprinting/Analysis/BTIDES_Schema/rust && cargo build --release
cd ~/Blue2thprinting/Analysis/rust               && cargo build --release
```

This produces the following binaries that the rest of this document refers to:

| Binary | Path | Role |
|---|---|---|
| `import-all-BTIDES` | `Analysis/rust/target/release/`               | Bulk convert+import for PCAP / btmon HCI logs |
| `sdp-to-BTIDES`     | `Analysis/BTIDES_Schema/rust/target/release/` | Convert `sdptool` XML to BTIDES JSON |
| `wigle-to-BTIDES`   | `Analysis/rust/target/release/`               | Convert WiGLE SQLite backup to BTIDES JSON |
| `BTIDES-to-SQL`     | `Analysis/rust/target/release/`               | Import any BTIDES JSON into MySQL |

## Importing data from btmon .bin HCI log files and Sniffle .pcap files

`import-all-BTIDES` walks one or more folders, auto-detects each file as a libpcap PCAP or a btmon/btsnoop `.bin` HCI log by its magic bytes, converts each to BTIDES JSON in parallel (one worker per CPU core, minus 4), and — when `--to-SQL` is passed — streams each converted file into MySQL through a shared connection pool. PCAPs and HCI logs can be mixed freely in the same input folder.

**Import ExampleData:**

```
~/Blue2thprinting/Analysis/rust/target/release/import-all-BTIDES \
    --folder ~/Blue2thprinting/ExampleData/ \
    --schema-dir ~/Blue2thprinting/Analysis/BTIDES_Schema \
    --to-SQL
```

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt2 -e "SELECT * FROM LE_bdaddr_to_name LIMIT 10;"
```

This should show some of the same sort of device name data that you could see by the above `./dump_names_specific.sh` command.

**Import your own data:**

Pass `--folder` multiple times to mix PCAP and HCI directories in a single run:

```
~/Blue2thprinting/Analysis/rust/target/release/import-all-BTIDES \
    --folder ~/Blue2thprinting/Logs/btmon/ \
    --folder ~/Blue2thprinting/Logs/sniffle/ \
    --schema-dir ~/Blue2thprinting/Analysis/BTIDES_Schema \
    --to-SQL
```

**Atomicity / resume semantics:** after a successful SQL import, each `<stem>.btides` is renamed to `<stem>.btides.processed` so a re-run of `import-all-BTIDES` skips it automatically. If the SQL import fails for a particular file, the `.btides` is left in place untouched and the next run retries just that file. Concurrent workers writing overlapping rows are deadlock-retried internally with exponential backoff.

**Useful flags:**

- `--use-test-db` — import into the `bttest` database instead of `bt2` (matches the Python `--use-test-db` semantics).
- `--workers N` — override the default worker count (default `max(1, ncpu-4)`).
- `--verbose` — print a one-line summary per converted file plus per-table SQL insert counts.
- `--keep-btides-after-sql` — keep the intermediate `.btides` file after a successful import (off by default, where it's renamed to `.btides.processed`).
- `--no-validate` — skip JSON-schema validation of the intermediate BTIDES output (faster; only use when you trust the converters).
- `--deadlock-retries N` — per-file MySQL 1213 retry budget (default 8, exponential backoff with jitter).


## Importing capture-side BTIDES output (`Logs/btc_sdp_gatt/` and `Logs/DarkFirmwareLMPLog/`)

Two of the BR/EDR collection tools in this branch now emit BTIDES JSON directly during capture, instead of writing intermediate per-tool formats that have to be parsed later:

- **`Scripts/btc_sdp_gatt.py`** — invoked per BR/EDR device by `central_app_launcher.py`. Performs SDP enumeration over a raw BlueZ kernel L2CAP socket and, if SDP indicates GATT-over-BR/EDR support, also enumerates that GATT tree. Writes one BTIDES file per protocol per device:
  - `Logs/btc_sdp_gatt/sdp_<bdaddr>.btides`
  - `Logs/btc_sdp_gatt/gatt_<bdaddr>.btides`

  (BDADDR is dash-delimited in the filename so the files are portable to filesystems that reject `:`.) `btc_sdp_gatt.py` also de-duplicates against existing records in the same file within a 5-minute window, so re-runs against the same device don't unbounded-grow the file.

- **`bluez-5.66/tools/DarkFirmware_VSC_LMP`** — invoked per BR/EDR device by `central_app_launcher.py` (via the `lmp2thprint_enabled` switch). Uses a BlueZ + Realtek custom-firmware vendor-specific command to capture LMP PDUs. Writes one BTIDES file per device:
  - `Logs/DarkFirmwareLMPLog/<bdaddr>.btides`

Because both already produce BTIDES JSON, importing is a single call to `BTIDES-to-SQL` — no separate conversion step.

**Import one device's data (single file):**

```
~/Blue2thprinting/Analysis/rust/target/release/BTIDES-to-SQL \
    --input ~/Blue2thprinting/Logs/btc_sdp_gatt/sdp_AA-BB-CC-DD-EE-FF.btides \
    --input ~/Blue2thprinting/Logs/btc_sdp_gatt/gatt_AA-BB-CC-DD-EE-FF.btides \
    --input ~/Blue2thprinting/Logs/DarkFirmwareLMPLog/AA:BB:CC:DD:EE:FF.btides
```

`BTIDES-to-SQL` accepts `--input` any number of times; passing the SDP, GATT, and LMP BTIDES files for the same device in a single invocation gets them imported under one transaction.

**Import everything in both folders at once (bulk):**

```
~/Blue2thprinting/Analysis/rust/target/release/BTIDES-to-SQL \
    $(find ~/Blue2thprinting/Logs/btc_sdp_gatt        -name '*.btides' -printf '--input %p ') \
    $(find ~/Blue2thprinting/Logs/DarkFirmwareLMPLog -name '*.btides' -printf '--input %p ') \
    --reader-threads 4 --writer-threads 4
```

`--reader-threads N` parses input files in parallel into per-thread row buffers, which are then merged before the write. `--writer-threads N` runs the SQL `INSERT IGNORE` phase across N connections, each owning a disjoint subset of destination tables. Both default to 1; bumping them speeds up bulk imports considerably with many files.

**To confirm SDP and GATT-over-BR/EDR rows landed:**

```
mysql -u user -pa -D bt2 -e "SELECT bdaddr, pdu_id FROM SDP_Common LIMIT 10;"
mysql -u user -pa -D bt2 -e "SELECT bdaddr, declaration_handle, UUID FROM GATT_characteristics LIMIT 10;"
```

**To confirm LMP rows landed:**

```
mysql -u user -pa -D bt2 -e "SELECT bdaddr, lmp_version, device_BT_CID FROM LMP_VERSION_RES LIMIT 10;"
```

**Useful flags:**

- `--use-test-db` — import into the `bttest` database instead of `bt2`.
- `--verbose` — print per-table insert and duplicate counts.
- `--deadlock-retries N` — retry budget when concurrent imports collide on the InnoDB gap locks of an `INSERT IGNORE` (default 8, with exponential backoff and jitter).


## Importing SDP data from sdptool XML files (deprecated)

> **⚠️ Deprecated.** The `sdptool`-based SDP collection path is no longer used in this branch. `central_app_launcher.py` defaults to `btc_sdp_gatt_enabled = True` and explicitly comments `sdptool_enabled = False`, with a note that the two paths race when both enabled. The XML-import flow below is retained only for back-importing legacy `Logs/sdptool/*_sdp.xml` files captured by older revisions. New collection writes BTIDES directly to `Logs/btc_sdp_gatt/` — see the section above.


`central_app_launcher.py` saves `sdptool` output as per-device XML files named `{BDADDR}_sdp.xml` under `Logs/sdptool/`. The Rust `sdp-to-BTIDES` converter produces a BTIDES JSON file from either a single XML file or a directory of them; pipe that JSON through `BTIDES-to-SQL` to import into MySQL.

**Import a single device's SDP file:**

```
~/Blue2thprinting/Analysis/BTIDES_Schema/rust/target/release/sdp-to-BTIDES \
    --input ~/Blue2thprinting/Logs/sdptool/<BDADDR>_sdp.xml \
    --output /tmp/sdp_single.btides \
    --schema-dir ~/Blue2thprinting/Analysis/BTIDES_Schema

~/Blue2thprinting/Analysis/rust/target/release/BTIDES-to-SQL \
    --input /tmp/sdp_single.btides
```

**Import all SDP files from the default collection directory:**

```
~/Blue2thprinting/Analysis/BTIDES_Schema/rust/target/release/sdp-to-BTIDES \
    --input ~/Blue2thprinting/Logs/sdptool/ \
    --output /tmp/sdp_all.btides \
    --schema-dir ~/Blue2thprinting/Analysis/BTIDES_Schema

~/Blue2thprinting/Analysis/rust/target/release/BTIDES-to-SQL \
    --input /tmp/sdp_all.btides
```

When `--input` is a directory, `sdp-to-BTIDES` processes every `*_sdp.xml` file underneath it into a single BTIDES output. The intermediate `.btides` file is useful for inspection or for re-importing later without re-parsing the XML.

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt2 -e "SELECT bdaddr, pdu_id FROM SDP_Common LIMIT 10;"
```

**Useful flags:**

- `BTIDES-to-SQL --use-test-db` — import into the `bttest` database instead of `bt2`.
- `BTIDES-to-SQL --verbose` — print per-table insert/duplicate counts.
- `sdp-to-BTIDES --verbose-BTIDES` — include optional human-readable fields in the BTIDES JSON.
- `sdp-to-BTIDES --no-validate` — skip schema validation on the output (faster).
- `sdp-to-BTIDES --quiet` — suppress per-file progress output.


## Importing GPS / WiGLE data

I originally added support for native Linux GPS logging from a USB dongle alongside Bluetooth capture, but I have since switched to crowdsourced GPS data from [WiGLE.net](https://wigle.net/) — the WiGLE Android app on a junk Pixel turned out to be both more reliable and easier to operate than the USB GPS setup. The native Linux GPS code path remains in `Scripts/` but is not currently exercised; the recommended (and tested) flow is to import GPS data from a WiGLE backup.

The WiGLE Android app's "Database → Backup" produces a `.sqlite` file containing every device the phone has heard, with a trilaterated `best` lat/lon per device (and individual sighting `location` rows if you want them). The Rust `wigle-to-BTIDES` tool reads that SQLite, consults the local `bt2` (or `bttest`) MySQL DB to fill in `bdaddr_random` for each BLE device (so the resulting BTIDES JSON is correctly typed), and emits BTIDES JSON. Feed that to `BTIDES-to-SQL` to land it in MySQL.

**Convert a WiGLE backup to BTIDES, then import:**

```
~/Blue2thprinting/Analysis/rust/target/release/wigle-to-BTIDES \
    --input ~/Downloads/wiglewifi_<timestamp>.sqlite \
    --output /tmp/wigle.btides \
    --schema-dir ~/Blue2thprinting/Analysis/BTIDES_Schema

~/Blue2thprinting/Analysis/rust/target/release/BTIDES-to-SQL \
    --input /tmp/wigle.btides
```

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt2 -e "SELECT bdaddr, lat, lon FROM bdaddr_to_GPS LIMIT 10;"
```

**Useful flags:**

- `wigle-to-BTIDES --get-all-GPS` — emit one BTIDES GPS record per individual sighting in the `location` table, not just the per-device trilaterated `best` from the `network` table (slower; larger output).
- `wigle-to-BTIDES --GPS-exclude-upper-left "(lat,lon)" --GPS-exclude-lower-right "(lat,lon)"` — drop any sightings inside this lat/lon bounding box from the output (e.g. to scrub your home address before sharing the result).
- `wigle-to-BTIDES --limit N` / `--offset N` — page through the `network` table; useful for very large backups.
- `wigle-to-BTIDES --no-mysql-lookup` — skip the `bdaddr_random` MySQL lookup and assume `bdaddr_rand=1` for every BLE row. Use this when you don't have the Blue2thprinting MySQL DB available yet (e.g. on a fresh analysis box, before any other imports).
- `wigle-to-BTIDES --use-test-db` — perform the `bdaddr_random` lookup against `bttest` instead of `bt2`.
- `BTIDES-to-SQL --use-test-db` — import into `bttest` instead of `bt2`.


## Importing BTC LMP data from BTC_2THPRINT.log

`central_app_launcher.py` invokes `DarkFirmware_VSC_LMP` (BlueZ + Realtek custom firmware) to capture LMP PDUs from each discovered BR/EDR device, and writes attempt/success markers plus the captured PDU stream into `/home/user/Blue2thprinting/Logs/BTC_2THPRINT.log` (or alt user home directory if you reconfigured it). To import this data into the database, (copy the data from your capture system to your analysis system, if applicable, and then) run the following:

```

cd ~/Blue2thprinting/Analysis/
python3 ./parse_BTC_2THPRINT_2db.py
```

The launcher prepends a per-device log entry before each invocation so the parser can attribute the subsequent PDU stream to the right BDADDR.

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt -e "SELECT * FROM LMP_VERSION_RES LIMIT 10;"
```

Copyright(c) © Dark Mentor LLC 2023-2026
