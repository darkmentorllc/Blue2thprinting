"""
Cross-language query-flag parity test.

For every query type in the shared fixture file
(BTIDALPOOL/tests/query_parity_fixtures.json) this asserts THREE things are
identical:

  1. golden       — the expected_args baked into the fixture,
  2. python_args  — what the REAL Python server builds, via
                    Analysis/btidalpool_query_args.build_query_args (the same
                    function Server_BTIDALPOOL.py's handle_query now calls),
  3. rust_args    — what the Rust server builds, obtained by running the
                    `print-query-args` helper binary from btidalpool-server.

Because both servers ultimately invoke the SAME Tell_Me_Everything.py with
these flags (plus identical infrastructure flags), identical flags ⟹
identical query results. So this is the "confirm you see exactly the same
outputs with the Rust-based code" check, done deterministically without a
live MySQL DB / OAuth / network.

Run:
    python3 -m unittest BTIDALPOOL/python/test_query_parity.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
POOL_ROOT = THIS_DIR.parent                 # BTIDALPOOL/
REPO_ROOT = POOL_ROOT.parent                # repo root
ANALYSIS_DIR = REPO_ROOT / "Analysis"
FIXTURES = POOL_ROOT / "tests" / "query_parity_fixtures.json"

# The Rust QA helper that prints the server's query-filter flags as JSON.
PRINT_ARGS_BIN_CANDIDATES = [
    POOL_ROOT / "target" / "release" / "print-query-args",
    POOL_ROOT / "target" / "debug" / "print-query-args",
]

# Import the REAL Python server arg-builder (single source of truth, shared
# with Server_BTIDALPOOL.py).
sys.path.insert(0, str(ANALYSIS_DIR))
from btidalpool_query_args import build_query_args  # noqa: E402


def _find_print_args_bin() -> Path | None:
    for p in PRINT_ARGS_BIN_CANDIDATES:
        if p.is_file():
            return p
    return None


def _load_fixtures() -> list[dict]:
    data = json.loads(FIXTURES.read_text())
    return data["fixtures"]


def _rust_args(binary: Path, query_obj: dict) -> list[str]:
    """Invoke the Rust print-query-args helper and parse its JSON output."""
    out = subprocess.check_output(
        [str(binary), "--query-json", json.dumps(query_obj)],
        text=True,
    )
    return json.loads(out)


class QueryParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = _load_fixtures()
        cls.binary = _find_print_args_bin()

    def test_python_builder_matches_golden_for_every_fixture(self):
        """The real Python server arg-builder must match every golden vector."""
        for fx in self.fixtures:
            with self.subTest(fixture=fx["name"]):
                got = build_query_args(fx["query"])
                self.assertEqual(
                    got, fx["expected_args"],
                    f"Python build_query_args diverged from golden for '{fx['name']}'",
                )

    def test_rust_binary_matches_python_and_golden_for_every_fixture(self):
        """Rust server arg-builder must match BOTH the Python builder and golden."""
        if self.binary is None:
            self.skipTest(
                "print-query-args binary not built; run "
                "`cargo build --release -p btidalpool-server` from BTIDALPOOL/"
            )
        for fx in self.fixtures:
            with self.subTest(fixture=fx["name"]):
                rust = _rust_args(self.binary, fx["query"])
                python = build_query_args(fx["query"])
                self.assertEqual(
                    rust, fx["expected_args"],
                    f"Rust print-query-args diverged from golden for '{fx['name']}'",
                )
                # The clincher: Rust output == Python output, so the two
                # servers issue identical TME query flags for this query.
                self.assertEqual(
                    rust, python,
                    f"Rust and Python query flags differ for '{fx['name']}'",
                )

    def test_fixtures_cover_every_query_field(self):
        """Guard against adding a query type without a parity fixture."""
        all_fields = {
            "bdaddr", "NOT_bdaddr", "bdaddr_regex", "NOT_bdaddr_regex",
            "name_regex", "NOT_name_regex", "company_regex", "NOT_company_regex",
            "UUID_regex", "NOT_UUID_regex", "MSD_regex",
            "LL_VERSION_IND", "LMP_VERSION_RES",
            "GPS_exclude_upper_left", "GPS_exclude_lower_right",
            "require_GPS", "require_GATT_any", "require_GATT_values",
            "require_SMP", "require_SMP_legacy_pairing", "require_SDP",
            "require_LL_VERSION_IND", "require_LMP_VERSION_RES",
        }
        seen = set()
        for fx in self.fixtures:
            seen.update(fx["query"].keys())
        self.assertEqual(
            seen, all_fields,
            "fixture coverage drift: every allow-listed query field must be "
            "exercised by at least one fixture (and no extras)",
        )


if __name__ == "__main__":
    unittest.main()
