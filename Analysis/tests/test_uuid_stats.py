########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end tests for `Tell_Me_Everything.py --UUID16-stats` and
`--UUID128-stats`, both against the `bttest` database (deterministic,
seeded by `tests/fixtures/seed.sql`) and as a smoke test against the
production `bt2` database (skipped when bt2 isn't reachable).

The bttest tests assert exact output content — they own the data, so they
can. The bt2 smoke tests only assert structural properties: no traceback,
expected section headers, non-empty result — they don't know what's in any
given developer's bt2, just that the command runs cleanly against it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
MYSQL_USER = "user"
MYSQL_PASS = "a"


# ---------------------------------------------------------------------------
# bt2 reachability check (used to skip the smoke tests cleanly when the
# production DB isn't set up on this machine).
# ---------------------------------------------------------------------------

def _bt2_has_uuid_data():
    """Return (has_uuid16, has_uuid128) — whether bt2 has any rows in the
    LE/EIR UUID16 / UUID128 tables that --UUID*-stats reads from. Returns
    (False, False) if bt2 doesn't exist or is unreachable.
    """
    try:
        result = subprocess.run(
            ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", "bt2",
             "--batch", "--skip-column-names", "-e",
             "SELECT (SELECT COUNT(*) FROM LE_bdaddr_to_UUID16s_list) "
             "     + (SELECT COUNT(*) FROM EIR_bdaddr_to_UUID16s), "
             "       (SELECT COUNT(*) FROM LE_bdaddr_to_UUID128s_list) "
             "     + (SELECT COUNT(*) FROM EIR_bdaddr_to_UUID128s);"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        a, b = result.stdout.strip().split()
        return int(a) > 0, int(b) > 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError, ValueError):
        return False, False


_HAS_UUID16, _HAS_UUID128 = _bt2_has_uuid_data()
_BT2_SKIP_UUID16 = pytest.mark.skipif(
    not _HAS_UUID16,
    reason="bt2 database has no UUID16 rows (or is unreachable); skipping bt2 smoke test",
)
_BT2_SKIP_UUID128 = pytest.mark.skipif(
    not _HAS_UUID128,
    reason="bt2 database has no UUID128 rows (or is unreachable); skipping bt2 smoke test",
)


# ---------------------------------------------------------------------------
# --UUID16-stats
# ---------------------------------------------------------------------------

def test_uuid16_stats_use_test_db_le_section(run_tme):
    """The LE section of --UUID16-stats must render whenever
    LE_bdaddr_to_UUID16s_list has at least one row. seed.sql device 1
    contributes one row (UUID16 '180d' = Heart Rate), so we assert on the
    section header, the row count, and the company-match footer.

    Note: the command's per-row print loop only emits a line when the
    UUID16 is in `bt_member_UUID16s_to_names` (member_uuids.yaml). 0x180d
    is a service UUID, not a member UUID, so it doesn't appear as a
    rendered row — the test scope here is the section bookkeeping.
    """
    result = run_tme("--UUID16-stats")
    assert "Traceback" not in result.stderr
    assert "----= BLUETOOTH LOW ENERGY RESULTS =----" in result.stdout, \
        f"Expected LE section header missing:\n{result.stdout}"
    assert "1 rows of data found in DB:LE_bdaddr_to_UUID16s_list" in result.stdout
    assert "*** 0 UUID16s matched a company name ***" in result.stdout, \
        f"Expected the 'matched a company name' footer:\n{result.stdout}"


def test_uuid16_stats_use_test_db_vendor_match_renders_company_name(run_tme):
    """Seed an EIR row with a known vendor UUID16 (0xFEAA Google Eddystone,
    a member_uuids.yaml entry) and confirm:
      * BTC section renders independently of the LE section,
      * the per-row print loop emits the matched line with the company name,
      * the company-match footer increments accordingly,
      * the LE section still renders (regression test for the LE-block
        de-nesting fix in commit 0ab3ba6).
    """
    subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", "bttest", "-e",
         "INSERT IGNORE INTO EIR_bdaddr_to_UUID16s "
         "(bdaddr, list_type, str_UUID16s) "
         "VALUES ('aa:bb:cc:11:22:97', 2, 'feaa');"],
        check=True, capture_output=True,
    )
    try:
        result = run_tme("--UUID16-stats")
        assert "Traceback" not in result.stderr
        assert "----= BLUETOOTH CLASSIC RESULTS =----" in result.stdout, \
            f"BTC section missing despite seeded EIR row:\n{result.stdout}"
        # Per-row: 0xFEAA → Google. Substring match keeps the test tolerant
        # of upstream company-name punctuation changes (e.g. "Google, Inc.").
        assert "feaa" in result.stdout
        assert "Google" in result.stdout, \
            f"Expected Google (0xFEAA in member_uuids) in output:\n{result.stdout}"
        # Footer count incremented for the BTC section.
        assert "*** 1 UUID16s matched a company name ***" in result.stdout

        # LE section still runs independently — the de-nesting fix from
        # commit 0ab3ba6 must not regress.
        assert "----= BLUETOOTH LOW ENERGY RESULTS =----" in result.stdout
    finally:
        subprocess.run(
            ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", "bttest", "-e",
             "DELETE FROM EIR_bdaddr_to_UUID16s WHERE bdaddr = 'aa:bb:cc:11:22:97';"],
            check=False, capture_output=True,
        )


@_BT2_SKIP_UUID16
def test_uuid16_stats_no_test_db_smoke(run_tme_bt2):
    """Smoke test against production bt2: command runs cleanly and emits
    at least one of the expected section headers + summary footer. We
    don't pin specific UUID values because each developer's bt2 differs.
    """
    result = run_tme_bt2("--UUID16-stats")
    assert "Traceback" not in result.stderr, \
        f"--UUID16-stats against bt2 crashed:\n{result.stderr}"
    # At least one of the two section headers must appear if there's any
    # UUID16 data in bt2 (our _bt2_has_uuid_data check confirmed there is).
    assert (
        "----= BLUETOOTH CLASSIC RESULTS =----" in result.stdout
        or "----= BLUETOOTH LOW ENERGY RESULTS =----" in result.stdout
    ), f"No expected section header rendered:\n{result.stdout[:2000]}"
    # And the summary footer.
    assert "UUID16s matched a company name" in result.stdout


# ---------------------------------------------------------------------------
# --UUID128-stats
# ---------------------------------------------------------------------------

# Synthetic SIG-Base aliases covering each classification branch in
# _classify_uuid128_for_stats:
#   * SerialPort (Service Class table)        — sig_alias
#   * Huawei 0xFE35 (Member UUID table)       — sig_alias
#   * Made-up 0xCCCC (no SIG-table match)     — sig_alias_unknown
#   * Fictional UUID128 (cafecafe…)            — unknown (no annotation;
#                                                 a deliberately-fake pattern that
#                                                 isn't in any CLUES tier or in
#                                                 BLEScope_UUID128s, so the
#                                                 classifier returns "unknown")
_SEED_UUID128_ROWS = [
    ("aa:bb:cc:11:22:90", "0000110100001000800000805f9b34fb"),  # SerialPort
    ("aa:bb:cc:11:22:91", "0000fe3500001000800000805f9b34fb"),  # Huawei
    ("aa:bb:cc:11:22:92", "0000cccc00001000800000805f9b34fb"),  # unassigned
    ("aa:bb:cc:11:22:93", "cafecafecafecafecafecafecafecafe"),  # custom
]


def _seed_uuid128_rows():
    rows_sql = ",\n  ".join(
        f"('{bdaddr}', 0, 0, 2, '{uuid128}')"
        for bdaddr, uuid128 in _SEED_UUID128_ROWS
    )
    subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", "bttest", "-e",
         "INSERT IGNORE INTO LE_bdaddr_to_UUID128s_list "
         "(bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID128s) VALUES\n  "
         + rows_sql + ";"],
        check=True, capture_output=True,
    )


def _cleanup_uuid128_rows():
    subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", "bttest", "-e",
         "DELETE FROM LE_bdaddr_to_UUID128s_list "
         "WHERE bdaddr LIKE 'aa:bb:cc:11:22:9_';"],
        check=False, capture_output=True,
    )


def test_uuid128_stats_use_test_db_resolves_sig_aliases(run_tme):
    """The four canonical UUID128 classifications all annotate correctly:
        * Service Class match (0x1101 SerialPort)
        * Member UUID match (0xFE35 Huawei)
        * SIG-Base alias but no SIG-table match (0xCCCC)
        * Genuine custom UUID128 (no annotation, no SIG label)
    """
    _seed_uuid128_rows()
    try:
        result = run_tme("--UUID128-stats")
        assert "Traceback" not in result.stderr
        assert "----= BLUETOOTH LOW ENERGY RESULTS =----" in result.stdout

        # SIG-resolved matches:
        assert "SIG-Base alias of 0x1101" in result.stdout, \
            f"Missing SerialPort annotation:\n{result.stdout}"
        assert "Service Class: SerialPort" in result.stdout
        assert "SIG-Base alias of 0xFE35" in result.stdout, \
            f"Missing Huawei annotation:\n{result.stdout}"
        # Vendor name from member_uuids.yaml — substring match keeps the
        # test tolerant of upstream punctuation/case shifts.
        assert "HUAWEI" in result.stdout.upper()

        # SIG-Base alias but unassigned 16-bit form:
        assert "SIG-Base alias of 0xCCCC (no SIG-table match)" in result.stdout

        # Genuine custom UUID128 — present in the listing but NOT given a
        # SIG annotation (because it isn't a SIG-Base alias).
        assert "cafecafecafecafecafecafecafecafe" in result.stdout
        # The annotation column on that row must NOT contain a SIG marker.
        for line in result.stdout.splitlines():
            if "cafecafecafecafecafecafecafecafe" in line:
                assert "SIG-Base alias" not in line, \
                    f"Custom UUID128 should not be annotated as SIG alias: {line}"

        # Footers: three out of four resolved (clues=0, sig_alias=2,
        # sig_alias_unknown=1, plus the genuine custom which is unknown).
        assert "are SIG-Base aliases resolved to an assigned 16-bit name" in result.stdout
        assert "are SIG-Base aliases with no SIG-table match" in result.stdout
    finally:
        _cleanup_uuid128_rows()


@_BT2_SKIP_UUID128
def test_uuid128_stats_no_test_db_smoke(run_tme_bt2):
    """Smoke test against production bt2: --UUID128-stats runs cleanly and
    emits an expected section header + the CLUES count footer. No content
    assertions because bt2 contents are developer-specific.
    """
    result = run_tme_bt2("--UUID128-stats")
    assert "Traceback" not in result.stderr, \
        f"--UUID128-stats against bt2 crashed:\n{result.stderr}"
    assert (
        "----= BLUETOOTH CLASSIC RESULTS =----" in result.stdout
        or "----= BLUETOOTH LOW ENERGY RESULTS =----" in result.stdout
    ), f"No expected section header rendered:\n{result.stdout[:2000]}"
    # Footer that the fix added — present for any non-empty section.
    assert "UUID128s are in the CLUES database" in result.stdout
