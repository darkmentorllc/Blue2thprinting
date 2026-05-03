########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Live BTIDALPOOL upload round-trip test (--use-test-db).

Generates a synthetic BTIDES entry with a randomly generated BDADDR, uploads
it to the BTIDALPOOL server with --use-test-db (so the server stores it in
its alternate `bttest` database rather than `bt2`), then queries the server
back for the same BDADDR (also with --use-test-db) and confirms the
synthetic data round-trips end-to-end.

Like ``test_btidalpool.py``, this requires a valid OAuth token and is
skipped when none is available.

Token resolution
----------------
Default: ``Analysis/tf`` (matches the developer convention in this repo).
Override: set ``BTIDALPOOL_TOKEN_FILE`` to point elsewhere.

Each invocation consumes BTIDALPOOL daily quota (one upload + one query).

Run with::

    pytest Analysis/tests/test_btidalpool_upload.py -v
"""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_FILE = ANALYSIS_DIR / "tf"

MYSQL_USER = "user"
MYSQL_PASS = "a"
TEST_DB = "bttest"


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


def _random_bdaddr():
    """48-bit random BDADDR as colon-separated lowercase hex.

    With 2^48 possibilities, the chance of colliding with prior synthetic
    uploads or seed data over thousands of runs is negligible.
    """
    octets = [secrets.randbelow(256) for _ in range(6)]
    return ":".join(f"{b:02x}" for b in octets)


def _synthetic_btides(bdaddr, name_str, company_id_hex, msd_payload_hex):
    """Build a minimal SingleBDADDR BTIDES list with name + MSD AdvData.

    The two AdvData leaves are enough to land rows in ``LE_bdaddr_to_name``
    and ``LE_bdaddr_to_MSD`` once the server runs BTIDES_to_SQL.
    """
    name_hex = name_str.encode("utf-8").hex()
    # AdvData length = 1 (type byte) + payload bytes
    name_length = 1 + len(name_hex) // 2
    # MSD length = 1 (type) + 2 (company id) + payload bytes
    msd_length = 1 + 2 + len(msd_payload_hex) // 2
    return [{
        "bdaddr": bdaddr,
        "bdaddr_rand": 0,  # public
        "AdvChanArray": [{
            "type": 0,  # ADV_IND
            "AdvDataArray": [
                {
                    "type": 9,  # Complete Local Name
                    "length": name_length,
                    "name_hex_str": name_hex,
                },
                {
                    "type": 255,  # Manufacturer Specific Data
                    "length": msd_length,
                    "company_id_hex_str": company_id_hex,
                    "msd_hex_str": msd_payload_hex,
                },
            ],
        }],
    }]


@pytest.mark.btidalpool
@pytest.mark.skipif(TOKEN_FILE is None, reason=SKIP_REASON)
def test_btidalpool_upload_round_trip(db_clean, run_tme, tmp_path):
    """Synthesize → upload (--use-test-db) → query back (--use-test-db) → verify.

    Steps:
      1. db_clean fixture wipes local bttest before the test.
      2. Build a synthetic BTIDES entry with a random BDADDR + a recognizable
         name + a recognizable MSD (Company ID 0xFFFF, i.e. the test/none
         marker).
      3. Run BTIDES_to_BTIDALPOOL.py --use-test-db to upload it. The server
         stores the BTIDES file then runs BTIDES_to_SQL with use_test_db=True,
         landing the rows in the server's bttest database.
      4. Run Tell_Me_Everything.py --query-BTIDALPOOL --use-test-db --bdaddr <ours>
         (run_tme always passes --use-test-db locally, and --query-BTIDALPOOL
         forwards use_test_db=True to the server). The server queries bttest,
         returns matching BTIDES, and the client imports it into the local
         bttest.
      5. Assert the synthetic name + MSD rows are present in the local bttest.
      6. db_clean fixture wipes local bttest after the test.
    """
    bdaddr = _random_bdaddr()
    name = f"UploadRoundTrip-{secrets.token_hex(4)}"
    company_id_hex = "ffff"  # "no company assigned" — safe filler for a test
    msd_payload_hex = secrets.token_hex(4)  # 4 random bytes

    btides = _synthetic_btides(bdaddr, name, company_id_hex, msd_payload_hex)
    in_file = tmp_path / "synthetic.btides"
    with open(in_file, "w") as f:
        json.dump(btides, f)

    # Step 1: upload to BTIDALPOOL test DB.
    upload = subprocess.run(
        [sys.executable, "BTIDES_to_BTIDALPOOL.py",
         "--use-test-db",
         "--input", str(in_file),
         "--token-file", TOKEN_FILE],
        cwd=str(ANALYSIS_DIR),
        capture_output=True, text=True, timeout=120,
    )
    assert upload.returncode == 0, (
        f"BTIDES_to_BTIDALPOOL.py upload failed (exit {upload.returncode}):\n"
        f"stdout:\n{upload.stdout}\nstderr:\n{upload.stderr}"
    )
    assert "Traceback" not in upload.stderr, \
        f"Upload crashed:\n{upload.stderr}"
    # Server replies "File saved successfully." for new content.
    assert "File saved successfully." in upload.stdout, (
        f"Server did not confirm upload as a fresh save.\n"
        f"stdout:\n{upload.stdout}\nstderr:\n{upload.stderr}"
    )

    # Step 2: query the server's bttest DB back for our BDADDR. run_tme always
    # passes --use-test-db locally; --query-BTIDALPOOL with --use-test-db
    # also tells the SERVER to query its bttest.
    result = run_tme(
        "--query-BTIDALPOOL",
        "--token-file", TOKEN_FILE,
        "--bdaddr", bdaddr,
        "--quiet-print",
        timeout=120,
    )
    assert "Traceback" not in result.stderr, \
        f"BTIDALPOOL query crashed:\n{result.stderr}"

    # Step 3: confirm the round-tripped data made it into local bttest.
    name_hex = name.encode("utf-8").hex()
    name_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name "
        f"WHERE bdaddr = '{bdaddr}' "
        f"AND device_name_type = 9 "
        f"AND name_hex_str = '{name_hex}'"
    )
    assert name_count > 0, (
        f"Expected uploaded name '{name}' for {bdaddr} to be queryable from "
        f"BTIDALPOOL test DB and present in local bttest after import. "
        f"Query stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    # Company ID 0xFFFF == 65535
    msd_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_MSD "
        f"WHERE bdaddr = '{bdaddr}' "
        f"AND device_BT_CID = 65535 "
        f"AND manufacturer_specific_data = '{msd_payload_hex}'"
    )
    assert msd_count > 0, (
        f"Expected uploaded MSD (CID=0xFFFF, data={msd_payload_hex}) for "
        f"{bdaddr} to round-trip back via BTIDALPOOL test DB."
    )
