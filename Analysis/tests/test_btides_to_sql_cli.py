########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Tests for BTIDES_to_SQL.py CLI flags that don't have direct coverage in
test_full_coverage_round_trip.py:

- --skip-invalid
- --rename
- --verbose-print

The first two are currently xfail-strict because of bugs in the script
itself (qprint() called with two args; args.input being a list rather than
a string). When those bugs are fixed the tests will go XPASS, and pytest's
strict=True will fail the suite to prompt removing the xfail marker.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ANALYSIS_DIR = TESTS_DIR.parent

MYSQL_USER = "user"
MYSQL_PASS = "a"
TEST_DB = "bttest"


def _count(query):
    result = subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB,
         "--batch", "--skip-column-names", "-e", query],
        check=True, capture_output=True, text=True,
    )
    return int(result.stdout.strip())


def _write_btides(path, entries):
    with open(path, "w") as f:
        json.dump(entries, f)


def _run_b2s(*args, timeout=60):
    return subprocess.run(
        [sys.executable, "BTIDES_to_SQL.py", *args],
        cwd=str(ANALYSIS_DIR),
        capture_output=True, text=True, timeout=timeout,
    )


# ---------------------------------------------------------------------------
# --verbose-print (works today)
# ---------------------------------------------------------------------------

def test_verbose_print_emits_more_output_than_default(db_clean, tmp_path):
    """--verbose-print should produce strictly more stdout than the default
    quiet-ish path. Use a single trivially valid BTIDES entry so the import
    path runs without hitting any unrelated edge cases."""
    valid = [{
        "bdaddr": "aa:bb:cc:99:88:01",
        "bdaddr_rand": 0,
        "AdvChanArray": [{
            "type": 0,
            "AdvDataArray": [
                {"type": 9, "length": 8, "name_hex_str": "566572626f7365"},  # "Verbose"
            ],
        }],
    }]
    in_file = tmp_path / "single.btides"
    _write_btides(in_file, valid)

    quiet = _run_b2s("--use-test-db", "--input", str(in_file), "--quiet-print")
    verbose = _run_b2s("--use-test-db", "--input", str(in_file), "--verbose-print")

    assert quiet.returncode == 0, f"--quiet-print run failed:\n{quiet.stderr}"
    assert verbose.returncode == 0, f"--verbose-print run failed:\n{verbose.stderr}"
    # We don't pin the exact contents — just that --verbose-print produces more.
    assert len(verbose.stdout) > len(quiet.stdout), (
        "--verbose-print should produce more stdout than the quiet path.\n"
        f"verbose stdout length: {len(verbose.stdout)}\n"
        f"quiet stdout length:   {len(quiet.stdout)}"
    )


# ---------------------------------------------------------------------------
# --skip-invalid
# ---------------------------------------------------------------------------

def test_skip_invalid_skips_failing_entries(db_clean, tmp_path):
    """Build a BTIDES list with [invalid_entry, valid_entry]. With
    --skip-invalid, the run should exit 0 and the valid entry's name should
    land in LE_bdaddr_to_name."""
    invalid = {"bdaddr": "aa:bb:cc:99:88:fe", "bdaddr_rand": 99}  # bad bdaddr_rand
    valid = {
        "bdaddr": "aa:bb:cc:99:88:01",
        "bdaddr_rand": 0,
        "AdvChanArray": [{
            "type": 0,
            "AdvDataArray": [
                {"type": 9, "length": 9, "name_hex_str": "536b6970506173734f6b"[:18]},
            ],
        }],
    }
    in_file = tmp_path / "mixed.btides"
    _write_btides(in_file, [invalid, valid])

    result = _run_b2s("--use-test-db", "--skip-invalid",
                      "--input", str(in_file), "--quiet-print")
    assert result.returncode == 0, (
        f"--skip-invalid should swallow the bad entry; got exit "
        f"{result.returncode}.\nstderr:\n{result.stderr}"
    )
    n = _count("SELECT COUNT(*) FROM LE_bdaddr_to_name "
               "WHERE bdaddr = 'aa:bb:cc:99:88:01'")
    assert n == 1, (
        f"Expected the valid entry's name row to land in bttest under "
        f"--skip-invalid; found {n} rows."
    )


def test_no_skip_invalid_aborts_on_bad_entry(db_clean, tmp_path):
    """Without --skip-invalid, a schema-invalid entry should make the run
    exit non-zero. This currently passes — but for the wrong reason: the
    qprint TypeError fires before the explicit exit(-1). Once the qprint bug
    is fixed, this test should still pass via the exit(-1) path."""
    invalid = {"bdaddr": "aa:bb:cc:99:88:fe", "bdaddr_rand": 99}
    in_file = tmp_path / "only_bad.btides"
    _write_btides(in_file, [invalid])

    result = _run_b2s("--use-test-db", "--input", str(in_file), "--quiet-print")
    assert result.returncode != 0, (
        "Without --skip-invalid, a schema-invalid entry should make the run "
        f"exit non-zero. Got exit {result.returncode}."
    )


# ---------------------------------------------------------------------------
# --rename
# ---------------------------------------------------------------------------

def test_rename_renames_input_to_processed(db_clean, tmp_path):
    """With --rename, after a successful import the input file should be
    renamed to <input>.processed."""
    valid = [{
        "bdaddr": "aa:bb:cc:99:88:01",
        "bdaddr_rand": 0,
        "AdvChanArray": [{
            "type": 0,
            "AdvDataArray": [
                {"type": 9, "length": 8, "name_hex_str": "52656e616d65"},  # "Rename"
            ],
        }],
    }]
    in_file = tmp_path / "rename_me.btides"
    _write_btides(in_file, valid)

    result = _run_b2s("--use-test-db", "--rename",
                      "--input", str(in_file), "--quiet-print")
    assert result.returncode == 0, (
        f"BTIDES_to_SQL.py --rename failed (exit {result.returncode}):\n"
        f"stderr:\n{result.stderr}"
    )
    processed = in_file.with_suffix(in_file.suffix + ".processed")
    assert processed.exists(), \
        f"Expected {processed} to exist after --rename; got: {list(tmp_path.iterdir())}"
    assert not in_file.exists(), \
        f"Original {in_file} should have been renamed away."
