"""
BTIDALPOOL upload shim.

Replaces the pure-Python `Analysis/BTIDES_to_BTIDALPOOL.py` that lived in
this repo before the Rust rewrite. The public function signature is
preserved verbatim — `Analysis/Tell_Me_Everything.py` does

    from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

and that import keeps working as long as `Analysis/Tell_Me_Everything.py`
adds this directory (BTIDALPOOL/python/) to `sys.path` before importing
(which it does, in a small `sys.path.insert(...)` block near the top).

Internally we shell out to the `btidalpool` Rust binary built from
`BTIDALPOOL/crates/btidalpool-client`. The Rust binary owns the wire
protocol (CBOR-in-zstd) and the HTTPS round trip.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from _btidalpool_runner import run_binary


def send_btides_to_btidalpool(
    input_file: str,
    token: str,
    refresh_token: str,
    use_test_db: bool = False,
) -> bool:
    """Upload one BTIDES JSON file to the BTIDALPOOL server.

    Signature matches the pre-Rust `Analysis/BTIDES_to_BTIDALPOOL.py` so
    every caller (currently just `Tell_Me_Everything.py`) keeps working
    without changes.

    Returns True on success, False on any failure (binary exit code != 0,
    invalid file, etc.). The Rust binary will print a one-line
    human-readable message to stdout/stderr before exiting.
    """
    p = Path(input_file)
    if not p.is_file():
        print(f"Input file {input_file} does not exist or is not a file.", file=sys.stderr)
        return False

    rc = run_binary(
        "upload",
        ["--input", str(p)],
        token=token,
        refresh_token=refresh_token,
        use_test_db=use_test_db,
    )
    return rc == 0


def _main_cli() -> int:
    """Allow `python BTIDES_to_BTIDALPOOL.py --input foo.json --token-file …`.

    Kept so existing operator muscle memory still works. The CLI surface is
    minimal — most options are passed via env vars that `run_binary` reads
    (BTIDALPOOL_SERVER_URL, BTIDALPOOL_INSECURE, BTIDALPOOL_BINARY).
    """
    parser = argparse.ArgumentParser(
        description="Send BTIDES data to BTIDALPOOL server (Rust shim)."
    )
    parser.add_argument(
        "--input", action="append", required=True,
        help="Input BTIDES JSON file. May be passed multiple times.",
    )
    parser.add_argument(
        "--token-file", required=True,
        help="JSON file with {token, refresh_token}. The Python pre-rewrite "
             "version could prompt for OAuth interactively; that flow is now "
             "the caller's job (see Tell_Me_Everything.py for the canonical "
             "implementation).",
    )
    parser.add_argument(
        "--use-test-db", action="store_true",
        help="Server-side: route to bttest instead of bt2.",
    )
    args = parser.parse_args()

    with open(args.token_file, "r") as f:
        token_data = json.load(f)
    token = token_data["token"]
    refresh_token = token_data["refresh_token"]

    all_ok = True
    for input_file in args.input:
        if not send_btides_to_btidalpool(input_file, token, refresh_token, args.use_test_db):
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(_main_cli())
