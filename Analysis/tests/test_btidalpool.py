########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Live BTIDALPOOL `--query-BTIDALPOOL` round-trip test (--use-test-db).

Self-contained: builds synthetic BTIDES data for a randomly-generated
BDADDR, uploads it to the BTIDALPOOL test pool, then queries it back via
``Tell_Me_Everything.py --query-BTIDALPOOL`` and confirms the synthetic
fields landed in local ``bttest`` after the client's import phase.

Earlier revisions of this test queried a hard-coded "well-known" device
on the BTIDALPOOL test pool (``fc:4f:2e:9c:c0:ff`` "😎 Specs"), but the
server-side seed for that record was wiped and there's no reliable way
to keep a fixed BDADDR pre-seeded forever. The self-contained form is
robust against server-state changes.

Coverage distinction
--------------------
Three BTIDALPOOL round-trip tests live in this directory:

  * ``test_btidalpool_upload.py``    — upload via ``BTIDES_to_BTIDALPOOL.py``;
                                       verifies **name + MSD** round-trip.
  * ``test_to_btidalpool.py``        — upload via TME ``--to-BTIDALPOOL``;
                                       verifies **name + MSD** round-trip.
  * ``test_btidalpool.py`` (this)    — upload via ``BTIDES_to_BTIDALPOOL.py``;
                                       additionally verifies **Flags** round-trip
                                       (``LE_bdaddr_to_flags`` table), which the
                                       other two tests don't exercise.

Each invocation consumes BTIDALPOOL daily quota (one upload + one query).

Token resolution
----------------
Default: ``Analysis/tf`` (matches the developer convention in this repo).
Override: set ``BTIDALPOOL_TOKEN_FILE`` to point elsewhere.

Run with::

    pytest Analysis/tests/test_btidalpool.py -v
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
POOL_FILES_DIR = ANALYSIS_DIR / "pool_files"

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
    """48-bit random BDADDR as colon-separated lowercase hex."""
    return ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6))


def _synthetic_btides(bdaddr, name_str, flags_hex, company_id_hex, msd_payload_hex):
    """Build a SingleBDADDR BTIDES list with name + Flags + MSD AdvData.

    All three AdvData leaves land in distinct local tables when imported:
      * type 9  → LE_bdaddr_to_name
      * type 1  → LE_bdaddr_to_flags
      * type 255 → LE_bdaddr_to_MSD
    so each one tested independently below proves end-to-end fidelity for
    that table's column set through the BTIDALPOOL round-trip.
    """
    name_hex = name_str.encode("utf-8").hex()
    name_length = 1 + len(name_hex) // 2          # 1 type byte + payload bytes
    flags_length = 1 + len(flags_hex) // 2         # 1 type byte + flags byte(s)
    msd_length = 1 + 2 + len(msd_payload_hex) // 2 # 1 type + 2 CID + payload
    return [{
        "bdaddr": bdaddr,
        "bdaddr_rand": 0,  # public
        "AdvChanArray": [{
            "type": 0,     # ADV_IND
            "AdvDataArray": [
                {
                    "type": 9,
                    "length": name_length,
                    "name_hex_str": name_hex,
                },
                {
                    "type": 1,
                    "length": flags_length,
                    "flags_hex_str": flags_hex,
                },
                {
                    "type": 255,
                    "length": msd_length,
                    "company_id_hex_str": company_id_hex,
                    "msd_hex_str": msd_payload_hex,
                },
            ],
        }],
    }]


@pytest.mark.btidalpool
@pytest.mark.skipif(TOKEN_FILE is None, reason=SKIP_REASON)
def test_btidalpool_query_round_trip_with_flags(db_clean, run_tme, tmp_path):
    """Synthesize → upload → query back → verify name + Flags + MSD all land
    in local bttest with the right values.

    The Flags assertion is the distinguishing piece: it specifically
    confirms that the bit-decoding of the BTIDES ``flags_hex_str`` into the
    five individual ``LE_bdaddr_to_flags`` columns (general/limited
    discoverable mode, BR/EDR not supported, etc.) survives the
    server-side import + the local-side re-import.
    """
    bdaddr = _random_bdaddr()
    name = f"QueryRoundTrip-{secrets.token_hex(4)}"
    company_id_hex = "ffff"  # "no company assigned" filler
    msd_payload_hex = secrets.token_hex(4)
    # 0x06 = LE General Discoverable Mode (bit 1) | BR/EDR Not Supported (bit 2).
    # The other three flag bits stay 0.
    flags_hex = "06"

    btides = _synthetic_btides(bdaddr, name, flags_hex, company_id_hex, msd_payload_hex)
    in_file = tmp_path / "synthetic.btides"
    with open(in_file, "w") as f:
        json.dump(btides, f)

    # ---- Step 1: upload to BTIDALPOOL test pool. ----
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
    assert "Traceback" not in upload.stderr, f"Upload crashed:\n{upload.stderr}"
    assert "File saved successfully." in upload.stdout, (
        f"Server did not confirm upload as a fresh save.\n"
        f"stdout:\n{upload.stdout}\nstderr:\n{upload.stderr}"
    )

    # ---- Step 2: query the server's bttest back for this BDADDR. ----
    # run_tme always passes --use-test-db locally, and --query-BTIDALPOOL
    # forwards use_test_db=True to the server so it queries its bttest.
    POOL_FILES_DIR.mkdir(exist_ok=True)
    pre_files = set(POOL_FILES_DIR.glob("*.json"))

    result = run_tme(
        "--query-BTIDALPOOL",
        "--token-file", TOKEN_FILE,
        "--bdaddr", bdaddr,
        "--quiet-print",
        timeout=120,
    )
    assert "Traceback" not in result.stderr, \
        f"BTIDALPOOL query crashed:\n{result.stderr}"

    post_files = set(POOL_FILES_DIR.glob("*.json"))
    new_files = post_files - pre_files
    assert new_files, (
        "No new file written to pool_files/ — the BTIDALPOOL round-trip "
        f"did not produce a response.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    # ---- Step 3: verify each of the three AdvData payloads round-tripped. ----

    name_hex = name.encode("utf-8").hex()
    name_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name "
        f"WHERE bdaddr = '{bdaddr}' "
        f"  AND device_name_type = 9 "
        f"  AND name_hex_str = '{name_hex}'"
    )
    assert name_count > 0, (
        f"Expected name '{name}' for {bdaddr} to round-trip from "
        f"BTIDALPOOL into local bttest; row not found.\n"
        f"Query stdout:\n{result.stdout}"
    )

    # Flags assertion — the unique-coverage piece for this test.
    # flags_hex == "06" → bit 1 set (General Discoverable), bit 2 set
    # (BR/EDR Not Supported); other three bits clear.
    flags_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_flags "
        f"WHERE bdaddr = '{bdaddr}' "
        f"  AND le_limited_discoverable_mode = 0 "
        f"  AND le_general_discoverable_mode = 1 "
        f"  AND bredr_not_supported = 1 "
        f"  AND le_bredr_support_controller = 0 "
        f"  AND le_bredr_support_host = 0"
    )
    assert flags_count > 0, (
        f"Expected Flags row (general=1, bredr_not_supported=1) for "
        f"{bdaddr} to round-trip from BTIDALPOOL into local bttest; "
        f"row not found. This is the distinguishing assertion of this "
        f"test relative to the other two BTIDALPOOL round-trip tests."
    )

    msd_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_MSD "
        f"WHERE bdaddr = '{bdaddr}' "
        f"  AND device_BT_CID = 65535 "  # 0xFFFF
        f"  AND manufacturer_specific_data = '{msd_payload_hex}'"
    )
    assert msd_count > 0, (
        f"Expected MSD row (CID=0xFFFF, data={msd_payload_hex}) for "
        f"{bdaddr} to round-trip."
    )
