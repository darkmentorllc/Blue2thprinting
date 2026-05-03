########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Tests for assorted Tell_Me_Everything.py CLI flags:

- --input-hci-log
- --max-records-output
- --hide-android-data
- --verbose-print
- --verbose-BTIDES
- --require-SMP-legacy-pairing

All tests use the seeded fixtures and the run_tme fixture from conftest.py
(which always passes --use-test-db).
"""

import json
from pathlib import Path

import pytest

from test_db_query import rendered_bdaddrs, ALL_TEST_BDADDR_REGEX

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
HCI_FIXTURE = FIXTURES_DIR / "import.snoop"


# ---------------------------------------------------------------------------
# --input-hci-log
# ---------------------------------------------------------------------------
# This is a smoke test: assert the CLI accepts the flag, parses the file, and
# exits cleanly. We don't assert on imported rows because Tell_Me_Everything
# may catch a known recoverable scapy class-name lookup error on certain HCI
# event records and skip the rest of the file. The point of this test is to
# confirm the flag is wired and doesn't raise an unhandled traceback.

def test_input_hci_log_fixture_exists():
    assert HCI_FIXTURE.exists(), f"Missing test fixture: {HCI_FIXTURE}"
    assert HCI_FIXTURE.stat().st_size > 0


def test_input_hci_log_runs_cleanly(db_clean, run_tme):
    """--input-hci-log <btsnoop file> exits 0 and produces no Python traceback."""
    result = run_tme("--input-hci-log", str(HCI_FIXTURE), "--quiet-print")
    assert "Traceback" not in result.stderr, (
        f"--input-hci-log raised a Python traceback:\n{result.stderr}"
    )
    assert "Traceback" not in result.stdout, (
        f"--input-hci-log raised a Python traceback in stdout:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# --max-records-output
# ---------------------------------------------------------------------------

def test_max_records_output_caps_render_count(run_tme):
    """--max-records-output 2 against five seeded devices renders exactly 2."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--max-records-output", "2")
    assert len(rendered_bdaddrs(result.stdout)) == 2, (
        f"Expected exactly 2 rendered devices with --max-records-output 2; "
        f"got: {rendered_bdaddrs(result.stdout)}"
    )


def test_max_records_output_default_returns_all_seeded(run_tme):
    """Without --max-records-output, all 5 seeded AA:BB:CC devices render."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX)
    rendered = rendered_bdaddrs(result.stdout)
    expected = {f"aa:bb:cc:11:22:0{n}" for n in range(1, 6)}
    assert expected.issubset(rendered), \
        f"Expected all five seeded devices to render. Missing: {expected - rendered}"


def test_max_records_output_one(run_tme):
    """--max-records-output 1 renders exactly one device (regardless of which)."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--max-records-output", "1")
    assert len(rendered_bdaddrs(result.stdout)) == 1, \
        f"Expected exactly 1 rendered device; got: {rendered_bdaddrs(result.stdout)}"


# ---------------------------------------------------------------------------
# --hide-android-data
# ---------------------------------------------------------------------------
# Device 2 has a vendor-specific UUID128 in LE_bdaddr_to_UUID128s_list seeded
# in seed.sql (Anki Drive UUID, present in the BLEScope_UUID128s lookup table).
# Without --hide-android-data, the BLEScope analysis section should print the
# Android package name. With --hide-android-data, both the analysis header and
# the package name should be suppressed.

def test_hide_android_data_default_shows_blescope_match(run_tme):
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:02")
    assert "BLEScope Analysis:" in result.stdout, (
        f"Expected BLEScope analysis output by default for device 2.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "com.anki.drive" in result.stdout, (
        f"Expected Anki Drive package name in BLEScope output.\n"
        f"stdout:\n{result.stdout}"
    )


def test_hide_android_data_suppresses_blescope(run_tme):
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:02", "--hide-android-data")
    assert "BLEScope Analysis:" not in result.stdout, (
        f"--hide-android-data should suppress 'BLEScope Analysis:' header.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "com.anki.drive" not in result.stdout, (
        f"--hide-android-data should suppress Android package name lookup.\n"
        f"stdout:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# --verbose-print
# ---------------------------------------------------------------------------
# Device 1 has no GATT and no SMP rows in seed.sql, so the corresponding
# vprint() diagnostics fire — but only when --verbose-print is set.

def test_verbose_print_emits_data_not_found_messages(run_tme):
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--verbose-print")
    # These vprint() messages live in TME_GATT.py and TME_SMP.py and should
    # show up only when --verbose-print is enabled.
    assert "No GATT Information found." in result.stdout, (
        f"Expected verbose 'No GATT Information found.' for device 1.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "No SMP data found." in result.stdout, (
        f"Expected verbose 'No SMP data found.' for device 1.\n"
        f"stdout:\n{result.stdout}"
    )


def test_no_verbose_print_suppresses_data_not_found_messages(run_tme):
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:01")
    assert "No GATT Information found." not in result.stdout, (
        f"'No GATT Information found.' should be suppressed without --verbose-print.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "No SMP data found." not in result.stdout, (
        f"'No SMP data found.' should be suppressed without --verbose-print.\n"
        f"stdout:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# --verbose-BTIDES
# ---------------------------------------------------------------------------
# --verbose-BTIDES enriches BTIDES JSON output with optional human-readable
# fields like "type_str" and "utf8_name".

def _all_keys(obj):
    """Recursively collect every dict key encountered under obj."""
    if isinstance(obj, dict):
        out = set(obj.keys())
        for v in obj.values():
            out |= _all_keys(v)
        return out
    if isinstance(obj, list):
        out = set()
        for v in obj:
            out |= _all_keys(v)
        return out
    return set()


def test_verbose_BTIDES_adds_type_str_and_utf8_name(run_tme, tmp_path):
    out = tmp_path / "verbose.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:01",
            "--output", str(out), "--verbose-BTIDES", "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    keys = _all_keys(data)
    assert "type_str" in keys, (
        f"Expected 'type_str' fields in --verbose-BTIDES output. Top-level "
        f"keys present: {sorted(keys)}"
    )
    # Device 1 has a Complete Local Name (utf8_name only renders for that).
    assert "utf8_name" in keys, (
        f"Expected 'utf8_name' field in --verbose-BTIDES output for device 1. "
        f"Keys present: {sorted(keys)}"
    )


def test_BTIDES_omits_type_str_by_default(run_tme, tmp_path):
    out = tmp_path / "default.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:01",
            "--output", str(out), "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    keys = _all_keys(data)
    assert "type_str" not in keys, (
        f"BTIDES output should omit 'type_str' without --verbose-BTIDES. "
        f"Keys present: {sorted(keys)}"
    )
    assert "utf8_name" not in keys, (
        f"BTIDES output should omit 'utf8_name' without --verbose-BTIDES. "
        f"Keys present: {sorted(keys)}"
    )


# ---------------------------------------------------------------------------
# --require-SMP-legacy-pairing
# ---------------------------------------------------------------------------
# Seed.sql only inserts SMP_Pairing_Req_Res rows for device 5, with auth_req=1
# (no Secure Connections bit set), which is the legacy pairing fingerprint.

def test_require_SMP_legacy_pairing_filters_to_device5(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-SMP-legacy-pairing")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:05"}, (
        f"--require-SMP-legacy-pairing should filter to device 5 only.\n"
        f"Got: {rendered_bdaddrs(result.stdout)}\nstdout:\n{result.stdout}"
    )
