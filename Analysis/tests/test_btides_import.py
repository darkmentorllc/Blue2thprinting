########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end PCAP → BTIDES → SQL import tests.

Tell_Me_Everything.py --input-pcap converts the pcap to BTIDES JSON in
memory, then BTIDES_to_SQL.py imports those entries into MySQL. After import,
the new BDADDRs from the pcap should be queryable in bttest.

Uses the per-test ``db_clean`` fixture so changes don't leak into the next
test (a previous test's import would otherwise still be visible).
"""

import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
IMPORT_PCAP = FIXTURES_DIR / "import.pcap"

MYSQL_USER = "user"
MYSQL_PASS = "a"
TEST_DB = "bttest"


def _count(query):
    """Run a single COUNT(*) query against bttest, return integer result."""
    result = subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB,
         "--batch", "--skip-column-names", "-e", query],
        check=True, capture_output=True, text=True,
    )
    return int(result.stdout.strip())


def test_import_pcap_fixture_exists():
    """Sanity check: the test fixture pcap is committed to the repo."""
    assert IMPORT_PCAP.exists(), f"Missing test fixture: {IMPORT_PCAP}"
    assert IMPORT_PCAP.stat().st_size > 0


def test_import_adds_new_bdaddrs(db_clean, run_tme):
    """After --input-pcap, bttest contains BDADDRs that weren't in seed.sql.

    The seed only contains aa:bb:cc:* devices. The pcap fixture contains LE
    advertisements with random BDADDRs none of which start with aa:bb:cc.
    """
    # Sum across the LE tables most likely to receive imported data from
    # advertisement packets. Different captures populate different tables;
    # we want at least one of these to grow.
    counted_tables = [
        "LE_bdaddr_to_flags",
        "LE_bdaddr_to_MSD",
        "LE_bdaddr_to_UUID16s_list",
        "LE_bdaddr_to_UUID128s_list",
        "LE_bdaddr_to_tx_power",
    ]
    union_clauses = " UNION ALL ".join(
        f"SELECT COUNT(*) FROM {t} WHERE bdaddr NOT LIKE 'aa:bb:cc:%'"
        for t in counted_tables
    )
    pre_query = f"SELECT SUM(c) FROM ({union_clauses}) x(c);"

    pre_count = _count(pre_query)
    assert pre_count == 0, "Test setup error: seed.sql contains non-aa:bb:cc: rows"

    run_tme("--input-pcap", str(IMPORT_PCAP), "--quiet-print")

    post_count = _count(pre_query)
    assert post_count > 0, \
        f"Expected --input-pcap to add at least one row to {counted_tables}; got {post_count}"


def test_import_then_query_finds_imported_device(db_clean, run_tme):
    """After import, the new BDADDRs are queryable via Tell_Me_Everything.py.

    We don't pin a specific BDADDR; we just confirm that *some* non-test
    device shows up after import.
    """
    run_tme("--input-pcap", str(IMPORT_PCAP), "--quiet-print")

    # Query for any BDADDR not starting with aa:bb:cc:.
    # ^(?!aa:bb:cc) is a negative lookahead — but MySQL REGEXP doesn't support
    # lookaheads, so we use the inverted-style pattern below.
    result = run_tme("--bdaddr-regex", "^[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$")
    # Just confirm we get more than the 5 seeded devices when the imported pcap data is present.
    from test_db_query import rendered_bdaddrs
    rendered = rendered_bdaddrs(result.stdout)
    seeded = {f"aa:bb:cc:11:22:0{n}" for n in range(1, 6)}
    extras = rendered - seeded
    assert extras, \
        f"After import, expected to see BDADDRs beyond the seeded 5; got: {rendered}"


def test_import_then_export_includes_imported(db_clean, run_tme, tmp_path):
    """Import → export round-trip: a BDADDR added by import should appear in
    the exported BTIDES file when we then export everything.
    """
    out = tmp_path / "after_import.btides"
    run_tme("--input-pcap", str(IMPORT_PCAP), "--output", str(out), "--quiet-print")
    assert out.exists()
    import json
    with open(out) as f:
        data = json.load(f)
    bdaddrs = {e.get("bdaddr") for e in data if isinstance(e, dict)}
    # Seed devices are NOT in this output because we filtered on what the pcap
    # provided — but at least one non-seed BDADDR should be present.
    non_seed = {b for b in bdaddrs if b and not b.startswith("aa:bb:cc:")}
    assert non_seed, \
        f"Export after import contained no non-seed BDADDRs: {bdaddrs}"
