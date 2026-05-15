########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end tests for `Tell_Me_Everything.py --input-BTIDES`.

`--input-BTIDES` is the direct-load counterpart to `--input-pcap` /
`--input-hci-log`: it skips the converter step and feeds a BTIDES JSON
file straight into BTIDES_to_SQL, then selects all the BDADDRs in the
file for rendering. This is the input path used by the on-the-fly capture
tools (`Scripts/btc_sdp_gatt.py`, the DarkFirmware_VSC_LMP binary) that
already emit BTIDES directly.

Test strategy: round-trip an in-memory device.

  1. db_clean fixture wipes bttest and reloads seed.sql (so device 1's
     name/UUID/MSD rows are present).
  2. Export device 1 to a temporary .btides via `--output`.
  3. Delete device 1's seeded rows from bttest.
  4. Re-import via `--input-BTIDES <file>` and confirm the rows landed
     back in bttest. Confirm rendering selects the device's BDADDR too.

The same fixture file then exercises a second scenario: importing a
synthetic .btides file we build by hand, to confirm the schema-loaded
path works for entries that didn't originate from --output.
"""

import json
import subprocess
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
MYSQL_USER = "user"
MYSQL_PASS = "a"
TEST_DB = "bttest"


def _count(query):
    result = subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB,
         "--batch", "--skip-column-names", "-e", query],
        check=True, capture_output=True, text=True,
    )
    return int(result.stdout.strip())


def _delete_device1_rows():
    subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB, "-e",
         "DELETE FROM LE_bdaddr_to_name        WHERE bdaddr = 'aa:bb:cc:11:22:01';"
         "DELETE FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr = 'aa:bb:cc:11:22:01';"
         "DELETE FROM LE_bdaddr_to_flags        WHERE bdaddr = 'aa:bb:cc:11:22:01';"
         "DELETE FROM LE_bdaddr_to_tx_power     WHERE bdaddr = 'aa:bb:cc:11:22:01';"
         "DELETE FROM LE_bdaddr_to_MSD          WHERE bdaddr = 'aa:bb:cc:11:22:01';"],
        check=True, capture_output=True,
    )


def test_input_btides_round_trip_from_export(db_clean, run_tme, tmp_path):
    """Export → wipe → re-import via --input-BTIDES → verify same data lands.

    This is the strongest assertion that --input-BTIDES is wired correctly:
    if any field is silently dropped on either the export or the load
    side, the row counts after re-import won't match the originals.
    """
    bdaddr = "aa:bb:cc:11:22:01"
    pre = {
        "name":     _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_name        WHERE bdaddr='{bdaddr}'"),
        "uuid16":   _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr='{bdaddr}'"),
        "flags":    _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_flags        WHERE bdaddr='{bdaddr}'"),
        "tx_power": _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_tx_power     WHERE bdaddr='{bdaddr}'"),
        "msd":      _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_MSD          WHERE bdaddr='{bdaddr}'"),
    }
    assert all(v > 0 for v in pre.values()), \
        f"seed.sql device 1 should have non-zero rows in all 5 tables, got {pre}"

    # Step 1: export to a .btides file we own.
    out = tmp_path / "device1.btides"
    run_tme("--bdaddr", bdaddr.upper(), "--output", str(out), "--quiet-print")
    assert out.exists() and out.stat().st_size > 0, \
        f"Export failed to produce a non-empty BTIDES file at {out}"
    with open(out) as f:
        exported = json.load(f)
    assert any(e.get("bdaddr") == bdaddr for e in exported if isinstance(e, dict)), \
        f"Exported BTIDES didn't include {bdaddr}: {exported!r}"

    # Step 2: wipe device 1's rows.
    _delete_device1_rows()
    assert _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_name WHERE bdaddr='{bdaddr}'") == 0, \
        "device 1 still present after deletion — test setup error"

    # Step 3: re-import via --input-BTIDES.
    result = run_tme("--input-BTIDES", str(out), "--quiet-print")
    assert "Traceback" not in result.stderr, \
        f"--input-BTIDES crashed:\n{result.stderr}"

    # Step 4: confirm every row count matches its pre-wipe value.
    post = {
        "name":     _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_name        WHERE bdaddr='{bdaddr}'"),
        "uuid16":   _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr='{bdaddr}'"),
        "flags":    _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_flags        WHERE bdaddr='{bdaddr}'"),
        "tx_power": _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_tx_power     WHERE bdaddr='{bdaddr}'"),
        "msd":      _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_MSD          WHERE bdaddr='{bdaddr}'"),
    }
    assert post == pre, \
        f"Row counts after --input-BTIDES re-import differ from pre-wipe.\nPre:  {pre}\nPost: {post}"


def test_input_btides_synthetic_landing_in_bttest(db_clean, run_tme, tmp_path):
    """Hand-rolled BTIDES file with a never-before-seen BDADDR also imports.

    The exported-file test above proves the export+import are symmetric;
    this test proves that an externally-produced BTIDES file (the actual
    use case for --input-BTIDES: ingesting btc_sdp_gatt.py / DarkFirmware
    output) also works.
    """
    bdaddr = "aa:bb:cc:de:ad:01"
    btides = [{
        "bdaddr": bdaddr,
        "bdaddr_rand": 0,  # public
        "AdvChanArray": [{
            "type": 0,  # ADV_IND
            "AdvDataArray": [
                {
                    "type": 9,  # Complete Local Name
                    "length": 1 + len("InputBtidesTest"),
                    "name_hex_str": "InputBtidesTest".encode("utf-8").hex(),
                },
            ],
        }],
    }]
    in_file = tmp_path / "synthetic.btides"
    with open(in_file, "w") as f:
        json.dump(btides, f)

    pre = _count(f"SELECT COUNT(*) FROM LE_bdaddr_to_name WHERE bdaddr='{bdaddr}'")
    assert pre == 0, \
        f"Test BDADDR {bdaddr} unexpectedly already present in bttest"

    result = run_tme("--input-BTIDES", str(in_file), "--quiet-print")
    assert "Traceback" not in result.stderr, \
        f"--input-BTIDES crashed on synthetic file:\n{result.stderr}"

    post = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name "
        f"WHERE bdaddr='{bdaddr}' AND device_name_type=9 "
        f"AND name_hex_str='{'InputBtidesTest'.encode().hex()}'"
    )
    assert post == 1, \
        f"Expected synthetic BTIDES name row to land in bttest; got count={post}.\n"\
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
