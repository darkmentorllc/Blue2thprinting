########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Tests for Analysis/Import_All_HCI_and_PCAP.py — the folder-walking driver
that converts every PCAP and/or HCI log under given folders into BTIDES
files, and optionally imports them into the local SQL database.

Coverage:
- happy path: --pcaps-folder + recursive walk + --HCI-logs-folder
              + --HCI-logs-suffix; .btides files appear next to each input
- mutual exclusion: --overwrite-existing-BTIDES + --read-existing-BTIDES
                    must error and exit non-zero
- --read-existing-BTIDES skips conversion when a .btides already exists
- --overwrite-existing-BTIDES forces re-conversion
- --HCI-logs-suffix gating: passing it without --HCI-logs-folder errors
- --pcaps-suffix gating: same shape on the pcap side
- --pcaps-folder pointing at a non-folder: errors
- --to-SQL --use-test-db: rows actually land in bttest
- --rename --to-SQL: the .btides files end up renamed to .btides.processed
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ANALYSIS_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
PCAP_FIXTURE = FIXTURES_DIR / "import.pcap"
HCI_FIXTURE = FIXTURES_DIR / "import.snoop"

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


def _run_importer(*args, timeout=120):
    return subprocess.run(
        [sys.executable, "Import_All_HCI_and_PCAP.py", *args],
        cwd=str(ANALYSIS_DIR),
        capture_output=True, text=True, timeout=timeout,
    )


@pytest.fixture
def tmp_input_folder(tmp_path):
    """Layout under tmp_path/in/:
        a.pcap
        sub/b.pcap
        c.snoop
    """
    root = tmp_path / "in"
    sub = root / "sub"
    sub.mkdir(parents=True)
    shutil.copy(PCAP_FIXTURE, root / "a.pcap")
    shutil.copy(PCAP_FIXTURE, sub / "b.pcap")
    shutil.copy(HCI_FIXTURE, root / "c.snoop")
    return root


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_pcaps_folder_walks_recursively(tmp_input_folder):
    """--pcaps-folder produces a .btides next to each .pcap, including those
    in subdirectories."""
    result = _run_importer("--pcaps-folder", str(tmp_input_folder),
                           "--quiet-print")
    assert result.returncode == 0, (
        f"--pcaps-folder happy path failed (exit {result.returncode}):\n"
        f"stderr:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr, \
        f"Unexpected traceback:\n{result.stderr}"
    assert (tmp_input_folder / "a.btides").exists()
    assert (tmp_input_folder / "sub" / "b.btides").exists()
    # Must not also pick up the .snoop file when --HCI-logs-folder isn't passed.
    assert not (tmp_input_folder / "c.btides").exists()


def test_HCI_logs_folder_with_suffix(tmp_input_folder):
    """--HCI-logs-folder + --HCI-logs-suffix .snoop produces a .btides next
    to each matching HCI log."""
    result = _run_importer(
        "--HCI-logs-folder", str(tmp_input_folder),
        "--HCI-logs-suffix", ".snoop",
        "--quiet-print",
    )
    assert result.returncode == 0
    assert (tmp_input_folder / "c.btides").exists()


def test_both_folders_in_one_invocation(tmp_input_folder):
    """Pass --pcaps-folder and --HCI-logs-folder in one shot; both kinds of
    .btides should be produced."""
    result = _run_importer(
        "--pcaps-folder", str(tmp_input_folder),
        "--HCI-logs-folder", str(tmp_input_folder),
        "--HCI-logs-suffix", ".snoop",
        "--quiet-print",
    )
    assert result.returncode == 0
    assert (tmp_input_folder / "a.btides").exists()
    assert (tmp_input_folder / "sub" / "b.btides").exists()
    assert (tmp_input_folder / "c.btides").exists()


# ---------------------------------------------------------------------------
# Mutual exclusion / arg validation
# ---------------------------------------------------------------------------

def test_overwrite_and_read_existing_BTIDES_are_mutually_exclusive(tmp_input_folder):
    result = _run_importer(
        "--pcaps-folder", str(tmp_input_folder),
        "--overwrite-existing-BTIDES",
        "--read-existing-BTIDES",
    )
    assert result.returncode == 1, (
        f"Expected exit 1 for the --overwrite + --read combo; got "
        f"{result.returncode}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "only pass one of --overwrite-existing-BTIDES or --read-existing-BTIDES" \
        in result.stdout


def test_HCI_logs_suffix_without_folder_errors():
    """The CLI rejects --HCI-logs-suffix when --HCI-logs-folder isn't set."""
    result = _run_importer("--HCI-logs-suffix", ".snoop")
    assert result.returncode == 1
    assert "--HCI-logs-suffix can only be passed if --HCI-logs-folder is also given." \
        in result.stdout


def test_pcaps_suffix_without_folder_errors():
    result = _run_importer("--pcaps-suffix", ".pcapng")
    assert result.returncode == 1
    assert "--pcaps-suffix can only be passed if --pcaps-folder is also given." \
        in result.stdout


def test_pcaps_folder_must_be_a_directory(tmp_path):
    """A regular file passed as --pcaps-folder is rejected."""
    bogus = tmp_path / "not_a_dir.txt"
    bogus.write_text("hello")
    result = _run_importer("--pcaps-folder", str(bogus))
    assert result.returncode == 1
    assert "--pcaps-folder argument must be a folder" in result.stdout


# ---------------------------------------------------------------------------
# .btides re-processing modes
# ---------------------------------------------------------------------------

def test_read_existing_BTIDES_skips_conversion(tmp_input_folder):
    """If a .btides file already exists next to a .pcap, the default flow
    skips that pcap entirely. With --read-existing-BTIDES we still skip
    re-conversion. Either way, the existing .btides is not overwritten."""
    pre_btides = tmp_input_folder / "a.btides"
    pre_btides.write_text("[]")  # known-distinct content
    pre_size = pre_btides.stat().st_size

    result = _run_importer(
        "--pcaps-folder", str(tmp_input_folder),
        "--read-existing-BTIDES",
        "--quiet-print",
    )
    assert result.returncode == 0
    # The existing .btides was not overwritten; size stays at 2 bytes ("[]").
    assert pre_btides.read_text() == "[]"
    assert pre_btides.stat().st_size == pre_size
    # The sub/b.pcap had no existing .btides, so a fresh one IS produced.
    assert (tmp_input_folder / "sub" / "b.btides").exists()


def test_overwrite_existing_BTIDES_redoes_conversion(tmp_input_folder):
    """--overwrite-existing-BTIDES re-converts even when a .btides already
    exists, replacing the prior content."""
    pre_btides = tmp_input_folder / "a.btides"
    pre_btides.write_text("[]")  # placeholder

    result = _run_importer(
        "--pcaps-folder", str(tmp_input_folder),
        "--overwrite-existing-BTIDES",
        "--quiet-print",
    )
    assert result.returncode == 0
    # After overwrite, the file should hold real BTIDES content (not "[]").
    new_content = pre_btides.read_text()
    assert new_content != "[]", \
        "Expected --overwrite-existing-BTIDES to replace the placeholder."
    assert pre_btides.stat().st_size > 100, \
        f"Expected a real BTIDES file; got {pre_btides.stat().st_size} bytes."


# ---------------------------------------------------------------------------
# --to-SQL / --rename
# ---------------------------------------------------------------------------

def test_to_SQL_imports_into_bttest(db_clean, tmp_input_folder):
    """--to-SQL --use-test-db drops imported pcap rows into bttest."""
    # Sum across LE-side adv-data tables that the pcap fixture exercises.
    counted_tables = [
        "LE_bdaddr_to_flags",
        "LE_bdaddr_to_MSD",
        "LE_bdaddr_to_UUID16s_list",
        "LE_bdaddr_to_UUID128s_list",
        "LE_bdaddr_to_tx_power",
    ]
    union = " UNION ALL ".join(
        f"SELECT COUNT(*) FROM {t} WHERE bdaddr NOT LIKE 'aa:bb:cc:%'"
        for t in counted_tables
    )
    pre = _count(f"SELECT SUM(c) FROM ({union}) x(c);")
    assert pre == 0, "db_clean should leave the imported-data row count at 0"

    result = _run_importer(
        "--pcaps-folder", str(tmp_input_folder),
        "--to-SQL", "--use-test-db",
        "--quiet-print",
    )
    assert result.returncode == 0, (
        f"--to-SQL run failed (exit {result.returncode}):\n"
        f"stderr:\n{result.stderr}"
    )

    post = _count(f"SELECT SUM(c) FROM ({union}) x(c);")
    assert post > 0, (
        f"Expected --to-SQL to add at least one row to {counted_tables}; "
        f"got {post}"
    )


def test_rename_renames_btides_to_processed(db_clean, tmp_input_folder):
    """--rename --to-SQL renames each successfully-imported .btides to
    <name>.btides.processed (matching what optionally_store_to_SQL does)."""
    result = _run_importer(
        "--pcaps-folder", str(tmp_input_folder),
        "--to-SQL", "--rename", "--use-test-db",
        "--quiet-print",
    )
    assert result.returncode == 0, (
        f"--rename run failed (exit {result.returncode}):\n"
        f"stderr:\n{result.stderr}"
    )
    # Each pcap should have produced a .btides.processed (and the .btides
    # itself should have been renamed away).
    for stem_dir, stem in [(tmp_input_folder, "a"),
                           (tmp_input_folder / "sub", "b")]:
        processed = stem_dir / f"{stem}.btides.processed"
        plain = stem_dir / f"{stem}.btides"
        assert processed.exists(), (
            f"Expected {processed} after --rename; got: {list(stem_dir.iterdir())}"
        )
        assert not plain.exists(), \
            f"Original {plain} should have been renamed away."
