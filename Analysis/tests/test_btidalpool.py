########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Live BTIDALPOOL --query-BTIDALPOOL smoke test.

This makes a real network round-trip to the BTIDALPOOL service and so requires
a valid OAuth token. Without one, the test is skipped (not failed).

Token resolution
----------------
Default: ``Analysis/tf`` (matches the developer convention in this repo).
Override: set the ``BTIDALPOOL_TOKEN_FILE`` environment variable to a
different file path.

Each invocation consumes one of the daily 100 BTIDALPOOL queries allotted to
the token's account.

Run with::

    pytest Analysis/tests/test_btidalpool.py -v
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_FILE = ANALYSIS_DIR / "tf"
POOL_FILES_DIR = ANALYSIS_DIR / "pool_files"

MYSQL_USER = "user"
MYSQL_PASS = "a"
TEST_DB = "bttest"

TARGET_BDADDR = "fc:4f:2e:9c:c0:ff"


def _resolve_token_file():
    override = os.environ.get("BTIDALPOOL_TOKEN_FILE")
    if override:
        return override if os.path.exists(override) else None
    if DEFAULT_TOKEN_FILE.exists() and DEFAULT_TOKEN_FILE.stat().st_size > 0:
        return str(DEFAULT_TOKEN_FILE)
    return None


TOKEN_FILE = _resolve_token_file()
SKIP_REASON = (
    "BTIDALPOOL token not found. Place an OAuth token JSON at "
    "Analysis/tf or set BTIDALPOOL_TOKEN_FILE to a valid path."
)


def _count(query):
    result = subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB,
         "--batch", "--skip-column-names", "-e", query],
        check=True, capture_output=True, text=True,
    )
    return int(result.stdout.strip())


@pytest.mark.skipif(TOKEN_FILE is None, reason=SKIP_REASON)
def test_query_btidalpool_round_trip(db_clean, run_tme):
    """Query BTIDALPOOL for fc:4f:2e:9c:c0:ff, import into bttest, verify data, clean up.

    Steps:
      1. db_clean fixture wipes bttest before the test.
      2. Run Tell_Me_Everything.py --query-BTIDALPOOL --use-test-db, which
         downloads the BTIDALPOOL response and imports it into bttest.
      3. Assert that the known data for fc:4f:2e:9c:c0:ff is present in the DB:
           - DeviceName "😎 Specs" (Complete Name)
           - Flags: General Discoverable=1, BR/EDR Not Supported=1, others=0
           - MSD: Company ID 0x03c2 (Snapchat Inc), raw data f094c84292
      4. db_clean fixture wipes bttest after the test.
    """
    POOL_FILES_DIR.mkdir(exist_ok=True)
    pre_files = set(POOL_FILES_DIR.glob("*.json"))

    result = run_tme(
        "--query-BTIDALPOOL",
        "--token-file", TOKEN_FILE,
        "--bdaddr", TARGET_BDADDR,
        "--quiet-print",
        timeout=120,
    )

    assert "Traceback" not in result.stderr, \
        f"BTIDALPOOL query crashed:\n{result.stderr}"

    post_files = set(POOL_FILES_DIR.glob("*.json"))
    new_files = post_files - pre_files
    assert new_files, (
        "No new file written to pool_files/ — the BTIDALPOOL round-trip "
        "did not produce a response.\nstdout:\n" + result.stdout
        + "\nstderr:\n" + result.stderr
    )

    # DeviceName "😎 Specs" (Complete Name, AD type 0x09=9)
    # Stored as UTF-8 hex: f09f988e205370656373
    name_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name "
        f"WHERE bdaddr = '{TARGET_BDADDR}' "
        f"AND device_name_type = 9 "
        f"AND name_hex_str = 'f09f988e205370656373'"
    )
    assert name_count > 0, \
        f"Expected DeviceName '😎 Specs' (Complete Name) not found in LE_bdaddr_to_name"

    # Flags: Limited=0, General=1, BR/EDR Not Supported=1, Controller=0, Host=0
    flags_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_flags "
        f"WHERE bdaddr = '{TARGET_BDADDR}' "
        f"AND le_limited_discoverable_mode = 0 "
        f"AND le_general_discoverable_mode = 1 "
        f"AND bredr_not_supported = 1 "
        f"AND le_bredr_support_controller = 0 "
        f"AND le_bredr_support_host = 0"
    )
    assert flags_count > 0, \
        f"Expected Flags row not found in LE_bdaddr_to_flags"

    # MSD: Company ID 0x03c2 = 962 (Snapchat Inc), raw data f094c84292
    msd_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_MSD "
        f"WHERE bdaddr = '{TARGET_BDADDR}' "
        f"AND device_BT_CID = 962 "
        f"AND manufacturer_specific_data = 'f094c84292'"
    )
    assert msd_count > 0, \
        f"Expected MSD row (Snapchat Inc/0x03c2, data=f094c84292) not found in LE_bdaddr_to_MSD"

    # Clean up the downloaded pool_files response
    for f in new_files:
        f.unlink(missing_ok=True)
