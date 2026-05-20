########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Live BTIDALPOOL round-trip test for the **Rust** client + server.

This is the Rust-stack equivalent of ``test_btidalpool.py`` (which exercises
the Python ``BTIDES_to_BTIDALPOOL.py`` upload + ``Tell_Me_Everything.py
--query-BTIDALPOOL`` query against the Python server on :3567). Here we drive
the Rust ``btidalpool-client`` binary against the Rust ``btidalpool-server``
(running in parallel on :3568), so the same synthetic device round-trips
through the CBOR-in-zstd protocol instead of the legacy raw-JSON one.

Flow (self-contained, like the Python test):
  1. Synthesize a SingleBDADDR BTIDES record for a random BDADDR carrying
     three AdvData leaves — Name (type 9), Flags (type 1), MSD (type 255).
  2. Upload it to the server's test pool:
       btidalpool-client --use-test-db upload --input <file>
     and confirm the server reports "File saved successfully."
  3. Query it back:
       btidalpool-client --use-test-db query --query-json '{"bdaddr": ...}'
                                             --output <file>
  4. Parse the downloaded BTIDES and confirm all three AdvData leaves
     round-tripped with the exact values we uploaded — Name, the Flags byte
     (0x06), and the MSD (company 0xFFFF + payload).

Why verify the downloaded JSON rather than local ``bttest``?
------------------------------------------------------------
The Python test checks the local ``bttest`` because ``--query-BTIDALPOOL``
makes Tell_Me_Everything auto-import the response into the local DB. The
standalone Rust ``btidalpool-client query`` only *downloads* the BTIDES (it
does not import), so the natural equivalent is to verify the server's
response payload directly. That payload is exactly what the server pulled
from its own ``bttest`` after ingesting our upload, so it proves the same
upload -> server-ingest -> query round-trip fidelity — including the Flags
leaf, which is this test's distinguishing coverage (mirroring the Python
``test_btidalpool.py``).

This consumes BTIDALPOOL daily quota (one upload + one query), same as the
Python test.

Token resolution
----------------
Default: ``Analysis/tf`` (repo developer convention).
Override: ``BTIDALPOOL_TOKEN_FILE``.

Server / binary overrides
-------------------------
``BTIDALPOOL_RUST_SERVER_URL``  default ``https://btidalpool.ddns.net:3568``
``BTIDALPOOL_BINARY``           explicit path to the btidalpool-client binary

Run with::

    pytest Analysis/tests/test_btidalpool_rust_client.py -v
"""

import json
import os
import secrets
import subprocess
from pathlib import Path

import pytest


ANALYSIS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = ANALYSIS_DIR.parent
DEFAULT_TOKEN_FILE = ANALYSIS_DIR / "tf"

# The Rust workspace lives at <repo>/BTIDALPOOL; the client binary is named
# btidalpool-client (release preferred, debug fallback).
POOL_ROOT = REPO_ROOT / "BTIDALPOOL"
DEFAULT_SERVER_URL = "https://btidalpool.ddns.net:3568"


def _resolve_token_file():
    override = os.environ.get("BTIDALPOOL_TOKEN_FILE")
    if override:
        return override if os.path.exists(override) else None
    if DEFAULT_TOKEN_FILE.exists() and DEFAULT_TOKEN_FILE.stat().st_size > 0:
        return str(DEFAULT_TOKEN_FILE)
    return None


def _resolve_client_binary():
    env = os.environ.get("BTIDALPOOL_BINARY")
    if env:
        return env if (os.path.isfile(env) and os.access(env, os.X_OK)) else None
    for candidate in (
        POOL_ROOT / "target" / "release" / "btidalpool-client",
        POOL_ROOT / "target" / "debug" / "btidalpool-client",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


TOKEN_FILE = _resolve_token_file()
CLIENT_BIN = _resolve_client_binary()
SERVER_URL = os.environ.get("BTIDALPOOL_RUST_SERVER_URL", DEFAULT_SERVER_URL)

SKIP_NO_TOKEN = (
    "BTIDALPOOL token not found. Place an OAuth token JSON at Analysis/tf "
    "or set BTIDALPOOL_TOKEN_FILE to a valid path."
)
SKIP_NO_BIN = (
    "btidalpool-client binary not found. Build it with "
    "`cd BTIDALPOOL && cargo build --release -p btidalpool-client`, or set "
    "BTIDALPOOL_BINARY to its path."
)


def _random_bdaddr():
    """48-bit random BDADDR as colon-separated lowercase hex."""
    return ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6))


def _synthetic_btides(bdaddr, name_str, flags_hex, company_id_hex, msd_payload_hex):
    """Build a SingleBDADDR BTIDES list with Name + Flags + MSD AdvData.

    Byte-for-byte the same structure the Python test_btidalpool.py builds,
    so the two tests upload equivalent records.
    """
    name_hex = name_str.encode("utf-8").hex()
    name_length = 1 + len(name_hex) // 2           # 1 type byte + payload bytes
    flags_length = 1 + len(flags_hex) // 2          # 1 type byte + flags byte(s)
    msd_length = 1 + 2 + len(msd_payload_hex) // 2  # 1 type + 2 CID + payload
    return [{
        "bdaddr": bdaddr,
        "bdaddr_rand": 0,  # public
        "AdvChanArray": [{
            "type": 0,     # ADV_IND
            "AdvDataArray": [
                {"type": 9, "length": name_length, "name_hex_str": name_hex},
                {"type": 1, "length": flags_length, "flags_hex_str": flags_hex},
                {
                    "type": 255,
                    "length": msd_length,
                    "company_id_hex_str": company_id_hex,
                    "msd_hex_str": msd_payload_hex,
                },
            ],
        }],
    }]


def _client(*args, timeout=120):
    """Invoke btidalpool-client with the common global flags + given args.

    Default cert trust is the cert bundled into the binary, which matches the
    cert :3568 presents (verified out-of-band), so no --ca/--insecure needed.
    """
    argv = [
        CLIENT_BIN,
        "--server-url", SERVER_URL,
        "--token-file", TOKEN_FILE,
        "--use-test-db",
        *args,
    ]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _collect_advdata_leaves(btides, bdaddr):
    """Flatten every AdvDataArray leaf for `bdaddr` across all AdvChanArray
    entries in the returned BTIDES. Robust to the server re-serializing /
    reordering / merging the structure — we only care that the leaves exist
    with the expected values."""
    leaves = []
    if not isinstance(btides, list):
        return leaves
    for entry in btides:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("bdaddr", "")).lower() != bdaddr.lower():
            continue
        for adv_chan in entry.get("AdvChanArray", []) or []:
            for leaf in adv_chan.get("AdvDataArray", []) or []:
                if isinstance(leaf, dict):
                    leaves.append(leaf)
    return leaves


@pytest.mark.skipif(TOKEN_FILE is None, reason=SKIP_NO_TOKEN)
@pytest.mark.skipif(CLIENT_BIN is None, reason=SKIP_NO_BIN)
def test_rust_client_query_round_trip_with_flags(tmp_path):
    """Synthesize -> upload (Rust client) -> query back (Rust client) ->
    verify Name + Flags + MSD all round-trip through the Rust server."""
    bdaddr = _random_bdaddr()
    name = f"RustRoundTrip-{secrets.token_hex(4)}"
    company_id_hex = "ffff"             # "no company assigned" filler
    msd_payload_hex = secrets.token_hex(4)
    # 0x06 = LE General Discoverable Mode (bit 1) | BR/EDR Not Supported (bit 2).
    flags_hex = "06"

    btides = _synthetic_btides(bdaddr, name, flags_hex, company_id_hex, msd_payload_hex)
    in_file = tmp_path / "synthetic.btides"
    in_file.write_text(json.dumps(btides))

    # ---- Step 1: upload to the Rust server's test pool. ----
    upload = _client("upload", "--input", str(in_file))
    assert upload.returncode == 0, (
        f"btidalpool-client upload failed (exit {upload.returncode}) against "
        f"{SERVER_URL}:\nstdout:\n{upload.stdout}\nstderr:\n{upload.stderr}"
    )
    assert "panicked" not in upload.stderr, f"Upload crashed:\n{upload.stderr}"
    assert "File saved successfully." in upload.stdout, (
        f"Server did not confirm upload as a fresh save.\n"
        f"stdout:\n{upload.stdout}\nstderr:\n{upload.stderr}"
    )

    # ---- Step 2: query the server's bttest back for this BDADDR. ----
    out_file = tmp_path / "result.btides"
    query = _client(
        "query",
        "--query-json", json.dumps({"bdaddr": bdaddr}),
        "--output", str(out_file),
    )
    assert query.returncode == 0, (
        f"btidalpool-client query failed (exit {query.returncode}) against "
        f"{SERVER_URL}:\nstdout:\n{query.stdout}\nstderr:\n{query.stderr}"
    )
    assert out_file.exists(), (
        "Query reported success but wrote no output file.\n"
        f"stdout:\n{query.stdout}\nstderr:\n{query.stderr}"
    )

    returned = json.loads(out_file.read_text())
    leaves = _collect_advdata_leaves(returned, bdaddr)
    assert leaves, (
        f"Downloaded BTIDES had no AdvData for {bdaddr}. The upload -> "
        f"server-ingest -> query round-trip did not return our record.\n"
        f"query stdout:\n{query.stdout}\nreturned:\n{json.dumps(returned)[:2000]}"
    )

    # ---- Step 3: verify each of the three AdvData payloads round-tripped. ----
    name_hex = name.encode("utf-8").hex()

    assert any(
        leaf.get("type") == 9 and leaf.get("name_hex_str") == name_hex
        for leaf in leaves
    ), f"Name leaf (type 9, name_hex_str={name_hex}) did not round-trip.\nleaves:\n{leaves}"

    # Flags assertion — the distinguishing coverage piece, mirroring the
    # Python test_btidalpool.py. Confirms the Flags byte (0x06) survived the
    # full round-trip through the Rust server.
    assert any(
        leaf.get("type") == 1 and leaf.get("flags_hex_str") == flags_hex
        for leaf in leaves
    ), f"Flags leaf (type 1, flags_hex_str={flags_hex}) did not round-trip.\nleaves:\n{leaves}"

    assert any(
        leaf.get("type") == 255
        and leaf.get("company_id_hex_str") == company_id_hex
        and leaf.get("msd_hex_str") == msd_payload_hex
        for leaf in leaves
    ), (
        f"MSD leaf (type 255, company_id={company_id_hex}, "
        f"msd={msd_payload_hex}) did not round-trip.\nleaves:\n{leaves}"
    )
