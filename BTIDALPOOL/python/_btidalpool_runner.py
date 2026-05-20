"""
Thin internal helper shared by the two public Python shims
(`BTIDALPOOL_to_BTIDES.py` upload + `BTIDES_to_BTIDALPOOL.py` download).

Both shims keep the *same public function signature* the old pure-Python
implementations had, so `Analysis/Tell_Me_Everything.py` keeps importing
them unchanged. Internally they shell out to the Rust `btidalpool` binary
built from this folder's sibling `crates/btidalpool-client/`.

The shim is intentionally tiny:
  - locate the `btidalpool` binary (release build preferred, debug fallback)
  - drop the caller's `{token, refresh_token}` into a temp token file
  - subprocess the binary with the right subcommand + args
  - return the subprocess's success/failure + any output file path

Anything more elaborate (retry, schema validation, hashing) belongs inside
the Rust binary, not here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


def _candidate_binary_paths() -> Sequence[Path]:
    """All places we look for the `btidalpool` binary, in order."""
    # `__file__` points at BTIDALPOOL/python/_btidalpool_runner.py, so
    # `.parent.parent` is BTIDALPOOL/.
    pool_root = Path(__file__).resolve().parent.parent
    return (
        pool_root / "target" / "release" / "btidalpool-client",
        pool_root / "target" / "debug" / "btidalpool-client",
        # Allow an explicit override via the environment for ops use
        # (e.g. systemd installing the binary into /usr/local/bin).
        Path(os.environ["BTIDALPOOL_BINARY"]) if "BTIDALPOOL_BINARY" in os.environ
        else pool_root / "target" / "release" / "btidalpool-client",
    )


def find_btidalpool_binary() -> str:
    """Return the path to the `btidalpool-client` Rust binary, or raise."""
    for path in _candidate_binary_paths():
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    # As a last resort, look on PATH (someone may have installed it system-wide).
    on_path = shutil.which("btidalpool-client")
    if on_path:
        return on_path
    raise RuntimeError(
        "btidalpool-client binary not found. Build it with:\n"
        "    cd BTIDALPOOL && cargo build --release\n"
        "or set BTIDALPOOL_BINARY=/path/to/btidalpool-client in your environment."
    )


def write_token_file(token: str, refresh_token: str) -> str:
    """Write `{token, refresh_token}` to a fresh temp file, return path."""
    # delete=False because we want to manage cleanup ourselves around the
    # subprocess call (the file must outlive `with` here to be readable by
    # the child process). Caller is responsible for `os.unlink(path)`.
    fd, path = tempfile.mkstemp(prefix="btidalpool-token-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"token": token, "refresh_token": refresh_token}, f)
    except Exception:
        # If we couldn't write the file, make sure we don't leave a partial
        # one behind for the next caller to stumble on.
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def server_url_from_env(default: str = "https://btidalpool.ddns.net:3567") -> str:
    """Allow tests / local runs to redirect the binary at a different server."""
    return os.environ.get("BTIDALPOOL_SERVER_URL", default)


def insecure_from_env() -> bool:
    """If `BTIDALPOOL_INSECURE=1`, skip TLS cert verification entirely.

    For local end-to-end tests against a self-signed / `--no-tls` server.
    In production this stays unset and the binary pins to the server cert
    that is compiled into it (no CA file needed — the Rust client bundles
    `btidalpool.ddns.net.crt` and trusts it by default).
    """
    return os.environ.get("BTIDALPOOL_INSECURE", "").strip() in ("1", "true", "yes")


def run_binary(
    subcmd: str,
    subcmd_args: Sequence[str],
    *,
    token: str,
    refresh_token: str,
    use_test_db: bool,
) -> int:
    """Spawn the Rust client binary and wait for it. Returns its exit code.

    Cleans up the temp token file on every path. Streams stdout/stderr to
    the parent process so the user sees the Rust binary's messages directly
    (the binary uses the same kind of one-line plain-text messages the old
    Python tools used, so this preserves the visible UX).
    """
    binary = find_btidalpool_binary()
    token_file = write_token_file(token, refresh_token)
    try:
        argv: list[str] = [
            binary,
            "--server-url", server_url_from_env(),
            "--token-file", token_file,
        ]
        if use_test_db:
            argv.append("--use-test-db")
        if insecure_from_env():
            argv.append("--insecure")
        # else: rely on the cert bundled into the binary (the default).
        argv.append(subcmd)
        argv.extend(subcmd_args)
        return subprocess.call(argv)
    finally:
        try:
            os.unlink(token_file)
        except OSError:
            pass
