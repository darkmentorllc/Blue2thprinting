"""
BTIDALPOOL download shim.

Replaces the pure-Python `Analysis/BTIDALPOOL_to_BTIDES.py` that lived in
this repo before the Rust rewrite. The public function signature is
preserved verbatim — `Analysis/Tell_Me_Everything.py` does

    from BTIDALPOOL_to_BTIDES import retrieve_btides_from_btidalpool

and that import keeps working as long as `Analysis/Tell_Me_Everything.py`
adds this directory (BTIDALPOOL/python/) to `sys.path` before importing.

Returns the (num_records, output_filename) tuple the old function did.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from _btidalpool_runner import run_binary


def retrieve_btides_from_btidalpool(
    email: str,
    query_object: dict,
    token: str,
    refresh_token: str,
    use_test_db: bool = False,
) -> Tuple[Optional[int], Optional[str]]:
    """Query the BTIDALPOOL server, write the response to a pool_files/ file.

    Signature matches the pre-Rust `Analysis/BTIDALPOOL_to_BTIDES.py` so
    every caller (currently just `Tell_Me_Everything.py`) keeps working.

    Returns (num_records, output_filename) on success; (None, None) on any
    failure. The Rust binary prints a one-line human-readable message
    before exiting.
    """
    # The Rust binary's `query` subcommand writes the response JSON to the
    # path we pass via `--output`. We use a temp file inside `./pool_files`
    # so the resulting file is in the same directory the Python tool
    # historically wrote to (downstream code in Tell_Me_Everything.py
    # then runs BTIDES_to_SQL on this path).
    os.makedirs("./pool_files", exist_ok=True)
    # The final filename follows the same `<sha1>-<email>-<timestamp>.json`
    # pattern the Python tool used, but we don't know the sha1 yet — write
    # to a temp name first, then rename after reading the file's bytes.
    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    tmp_out = os.path.join(
        "./pool_files", f"_pending-{email}-{ts}-{os.getpid()}.json"
    )

    rc = run_binary(
        "query",
        ["--output", tmp_out, "--query-json", json.dumps(query_object)],
        token=token,
        refresh_token=refresh_token,
        use_test_db=use_test_db,
    )
    if rc != 0:
        # Best-effort cleanup of a partial output file if the subprocess
        # bailed out after creating it.
        try:
            os.unlink(tmp_out)
        except FileNotFoundError:
            pass
        return (None, None)

    # Read the bytes once, compute the canonical SHA1 (sort_keys), then
    # rename into the conventional filename. Matches what the old Python
    # code did so any downstream tooling that greps for `<sha1>-…json`
    # filenames keeps working.
    try:
        with open(tmp_out, "rb") as f:
            raw_bytes = f.read()
        parsed = json.loads(raw_bytes.decode("utf-8"))
        canonical = json.dumps(parsed, sort_keys=True).encode("utf-8")
        sha1 = hashlib.sha1(canonical).hexdigest()
        final_path = os.path.join("./pool_files", f"{sha1}-{email}-{ts}.json")
        # On a SHA1 collision (a re-download of identical content), don't
        # overwrite an existing file — the data is the same so just delete
        # the temp copy and reuse the existing path.
        if os.path.exists(final_path):
            try:
                os.unlink(tmp_out)
            except FileNotFoundError:
                pass
        else:
            os.replace(tmp_out, final_path)

        # Count records the same way the Python code did: length of the
        # top-level JSON array. (Server already capped this to 100 records
        # before sending, so this list comprehension is cheap.)
        num_records = len(parsed) if isinstance(parsed, list) else 0
        return (num_records, final_path)
    except Exception as e:
        print(f"Could not parse server response: {e}", file=sys.stderr)
        try:
            os.unlink(tmp_out)
        except FileNotFoundError:
            pass
        return (None, None)


def _main_cli() -> int:
    """Allow `python BTIDALPOOL_to_BTIDES.py --token-file … --bdaddr …`.

    Mirrors a subset of the old CLI — full flag coverage isn't critical
    because Tell_Me_Everything.py is the canonical caller.
    """
    parser = argparse.ArgumentParser(
        description="Query BTIDALPOOL server (Rust shim)."
    )
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--bdaddr", required=False)
    parser.add_argument("--use-test-db", action="store_true")
    args = parser.parse_args()

    with open(args.token_file, "r") as f:
        token_data = json.load(f)
    token = token_data["token"]
    refresh_token = token_data["refresh_token"]

    query = {}
    if args.bdaddr:
        query["bdaddr"] = args.bdaddr

    num, path = retrieve_btides_from_btidalpool(
        email="cli@local",
        query_object=query,
        token=token,
        refresh_token=refresh_token,
        use_test_db=args.use_test_db,
    )
    if num is None:
        return 1
    print(f"{num} BTIDES records written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main_cli())
