########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Live test for `Tell_Me_Everything.py --to-BTIDALPOOL`.

This is the upload-via-TME counterpart to ``test_btidalpool_upload.py``
(which uploads via ``BTIDES_to_BTIDALPOOL.py`` directly). The TME path
goes through Tell_Me_Everything → write_BTIDES → send_btides_to_btidalpool,
i.e. ``args.to_BTIDALPOOL = True`` causes the exported file to also be
shipped to the remote server.

Strategy (mirrors test_btidalpool_upload.py for symmetry):

  1. db_clean wipes bttest and reloads seed.sql.
  2. Insert a synthetic device with a randomly-generated unique BDADDR
     and a recognizable name + MSD into bttest. The random BDADDR keeps
     us isolated from prior runs and from other developers' test data.
  3. Run Tell_Me_Everything.py with --bdaddr <synth> --output <file>
     --to-BTIDALPOOL --token-file <tf>. This exports the synthetic
     device and uploads the exported BTIDES file to the BTIDALPOOL test
     pool (use-test-db forwards to the server too).
  4. Wipe bttest again (so the next step proves the data round-tripped
     via BTIDALPOOL, not via local DB state).
  5. Query the server back for the synthetic BDADDR via --query-BTIDALPOOL.
  6. Assert the synthetic name + MSD rows landed in local bttest after
     the query's import phase.

Like the other BTIDALPOOL tests, this is skipped when no OAuth token is
available. Each invocation consumes BTIDALPOOL daily quota
(one upload + one query).

Token resolution
----------------
Default: ``Analysis/tf`` (matches the developer convention in this repo).
Override: set ``BTIDALPOOL_TOKEN_FILE`` to point elsewhere.
"""

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


def _mysql(sql):
    return subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB,
         "--batch", "--skip-column-names", "-e", sql],
        check=True, capture_output=True, text=True,
    )


def _count(query):
    return int(_mysql(query).stdout.strip())


def _random_bdaddr():
    """48-bit random BDADDR as lowercase colon-separated hex."""
    return ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6))


def _seed_synthetic_device(bdaddr, name_str, company_id_int, msd_payload_hex):
    """Insert the rows TME's --output would export for the device into
    bttest. Using INSERT IGNORE so a colliding random BDADDR (extremely
    unlikely) doesn't fail the test.
    """
    name_hex = name_str.encode("utf-8").hex()
    _mysql(
        f"INSERT IGNORE INTO LE_bdaddr_to_name "
        f"  (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str) "
        f"VALUES ('{bdaddr}', 0, 0, 9, '{name_hex}');"
        f"INSERT IGNORE INTO LE_bdaddr_to_MSD "
        f"  (bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data) "
        f"VALUES ('{bdaddr}', 0, 0, {company_id_int}, '{msd_payload_hex}');"
    )


@pytest.mark.btidalpool
@pytest.mark.skipif(TOKEN_FILE is None, reason=SKIP_REASON)
def test_to_btidalpool_round_trip(db_clean, run_tme, tmp_path):
    """Seed → TME --to-BTIDALPOOL upload → wipe → TME --query-BTIDALPOOL → verify.

    The strongest assertion that --to-BTIDALPOOL is wired correctly: if
    the upload silently failed (e.g. token not forwarded, server didn't
    persist), the post-wipe query wouldn't find the synthetic device.
    """
    bdaddr = _random_bdaddr()
    name = f"ToBtidalpool-{secrets.token_hex(4)}"
    company_id_int = 0xFFFF  # 65535, the "no company assigned" filler ID
    msd_payload_hex = secrets.token_hex(4)  # 4 random bytes

    # Step 1: synthesize the device in local bttest.
    _seed_synthetic_device(bdaddr, name, company_id_int, msd_payload_hex)
    pre_local = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name WHERE bdaddr='{bdaddr}'"
    )
    assert pre_local == 1, f"Seeding failed for {bdaddr}; got count={pre_local}"

    # Step 2: TME export + upload to BTIDALPOOL test pool.
    out = tmp_path / "upload.btides"
    result = run_tme(
        "--bdaddr", bdaddr.upper(),
        "--output", str(out),
        "--to-BTIDALPOOL",
        "--token-file", TOKEN_FILE,
        "--quiet-print",
        timeout=120,
    )
    assert "Traceback" not in result.stderr, \
        f"--to-BTIDALPOOL crashed:\n{result.stderr}"
    assert out.exists() and out.stat().st_size > 0, \
        f"Export file missing/empty after --to-BTIDALPOOL: {out}"
    # The send_btides_to_btidalpool helper prints "File saved successfully."
    # on a successful new-content upload (same wording as the standalone
    # BTIDES_to_BTIDALPOOL.py path).
    assert "File saved successfully." in result.stdout, (
        f"Server did not confirm the upload as a fresh save:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    # Step 3: wipe local bttest so the next step proves the data came
    # back from the server, not from local state.
    _mysql(
        f"DELETE FROM LE_bdaddr_to_name WHERE bdaddr='{bdaddr}';"
        f"DELETE FROM LE_bdaddr_to_MSD  WHERE bdaddr='{bdaddr}';"
    )
    assert _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name WHERE bdaddr='{bdaddr}'"
    ) == 0, "Local wipe failed — round-trip test would be confounded"

    # Step 4: query BTIDALPOOL test pool back for our BDADDR.
    query_result = run_tme(
        "--query-BTIDALPOOL",
        "--token-file", TOKEN_FILE,
        "--bdaddr", bdaddr,
        "--quiet-print",
        timeout=120,
    )
    assert "Traceback" not in query_result.stderr, \
        f"--query-BTIDALPOOL crashed:\n{query_result.stderr}"

    # Step 5: confirm the synthetic data round-tripped back into local bttest.
    name_hex = name.encode("utf-8").hex()
    name_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_name "
        f"WHERE bdaddr='{bdaddr}' AND device_name_type=9 "
        f"AND name_hex_str='{name_hex}'"
    )
    assert name_count > 0, (
        f"Expected uploaded name '{name}' for {bdaddr} to round-trip back. "
        f"--query-BTIDALPOOL stdout:\n{query_result.stdout}\n"
        f"--query-BTIDALPOOL stderr:\n{query_result.stderr}"
    )

    msd_count = _count(
        f"SELECT COUNT(*) FROM LE_bdaddr_to_MSD "
        f"WHERE bdaddr='{bdaddr}' AND device_BT_CID={company_id_int} "
        f"AND manufacturer_specific_data='{msd_payload_hex}'"
    )
    assert msd_count > 0, (
        f"Expected uploaded MSD (CID={company_id_int:#06x}, "
        f"data={msd_payload_hex}) for {bdaddr} to round-trip back."
    )
