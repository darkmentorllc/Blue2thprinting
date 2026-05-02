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
the token's account. The query is intentionally narrow (a BDADDR that is
extremely unlikely to exist in the pool) to keep the round-trip small —
the test asserts that the *round-trip itself* succeeded and produced a
response file in ``pool_files/``, not that any specific data came back.

Run with::

    pytest Analysis/tests/test_btidalpool.py -v
"""

import json
import os
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_FILE = ANALYSIS_DIR / "tf"
POOL_FILES_DIR = ANALYSIS_DIR / "pool_files"


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


@pytest.mark.skipif(TOKEN_FILE is None, reason=SKIP_REASON)
def test_query_btidalpool_round_trip(run_tme):
    """A --query-BTIDALPOOL invocation produces a new file in pool_files/.

    Uses a BDADDR (00:00:00:00:00:00) that is essentially guaranteed to have
    no matches, so the test isn't tied to whichever data happens to live in
    the pool today. The client writes a response file regardless of result
    count.
    """
    POOL_FILES_DIR.mkdir(exist_ok=True)
    pre_files = set(POOL_FILES_DIR.glob("*.json"))

    result = run_tme(
        "--query-BTIDALPOOL",
        "--token-file", TOKEN_FILE,
        "--bdaddr", "00:00:00:00:00:00",
        "--quiet-print",
        timeout=120,
    )

    # Confirm the network round-trip didn't throw a Python traceback.
    assert "Traceback" not in result.stderr, \
        f"BTIDALPOOL query crashed:\n{result.stderr}"

    # Assert at least one new file exists in pool_files/ (the response).
    post_files = set(POOL_FILES_DIR.glob("*.json"))
    new_files = post_files - pre_files
    assert new_files, (
        "No new file written to pool_files/ — the BTIDALPOOL round-trip "
        "did not produce a response. stdout:\n" + result.stdout
        + "\nstderr:\n" + result.stderr
    )

    # The response file should parse as JSON (BTIDES-shaped — list of dicts).
    response_path = next(iter(new_files))
    with open(response_path) as f:
        data = json.load(f)
    assert isinstance(data, list), \
        f"Expected JSON list response, got {type(data).__name__}: {data!r}"
