########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for the standalone PCAP_to_BTIDES.py and HCI_to_BTIDES.py
converter CLIs.

These complement the in-process coverage that Tell_Me_Everything.py's
--input-pcap and --input-hci-log already provide via test_btides_import.py
and test_cli_flags.py — those exercise the read_pcap / read_HCI functions
through TME, but never run the standalone scripts directly. Here we invoke
the CLIs as subprocesses and validate their output BTIDES file.

Fixtures reused (committed in tests/fixtures/):
- import.pcap   — 15-packet BLE-advertising slice with 10 distinct BDADDRs
- import.snoop  — 100-record btsnoop slice
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

TESTS_DIR = Path(__file__).resolve().parent
ANALYSIS_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
PCAP_FIXTURE = FIXTURES_DIR / "import.pcap"
HCI_FIXTURE = FIXTURES_DIR / "import.snoop"
SCHEMA_DIR = ANALYSIS_DIR / "BTIDES_Schema"

BTIDES_SCHEMA_FILES = [
    "BTIDES_base.json", "BTIDES_AdvData.json", "BTIDES_LLCP.json",
    "BTIDES_HCI.json", "BTIDES_L2CAP.json", "BTIDES_SMP.json",
    "BTIDES_ATT.json", "BTIDES_GATT.json", "BTIDES_EIR.json",
    "BTIDES_LMP.json", "BTIDES_SDP.json", "BTIDES_GPS.json",
]


@pytest.fixture(scope="module")
def btides_validator():
    resources = []
    for fname in BTIDES_SCHEMA_FILES:
        with open(SCHEMA_DIR / fname) as f:
            s = json.load(f)
        resources.append((s["$id"], Resource.from_contents(s)))
    registry = Registry().with_resources(resources)
    return Draft202012Validator(
        {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json"},
        registry=registry,
    )


def _run_converter(script, *args, timeout=60):
    """Invoke a standalone converter as a subprocess from Analysis/."""
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=str(ANALYSIS_DIR),
        capture_output=True, text=True, timeout=timeout,
    )


# ---------------------------------------------------------------------------
# PCAP_to_BTIDES.py
# ---------------------------------------------------------------------------

def test_pcap_to_btides_fixture_exists():
    assert PCAP_FIXTURE.exists(), f"Missing test fixture: {PCAP_FIXTURE}"
    assert PCAP_FIXTURE.stat().st_size > 0


def test_pcap_to_btides_produces_output_file(tmp_path):
    """Running PCAP_to_BTIDES.py against import.pcap produces a non-empty
    BTIDES file and exits 0 without a Python traceback."""
    out = tmp_path / "pcap_out.btides"
    result = _run_converter("PCAP_to_BTIDES.py",
                            "--input", str(PCAP_FIXTURE),
                            "--output", str(out),
                            "--quiet-print")
    assert result.returncode == 0, (
        f"PCAP_to_BTIDES.py exited {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr, \
        f"Traceback in PCAP_to_BTIDES.py stderr:\n{result.stderr}"
    assert out.exists() and out.stat().st_size > 0, \
        f"Output file at {out} missing or empty.\nstdout:\n{result.stdout}"


def test_pcap_to_btides_output_is_valid_json_list(tmp_path):
    out = tmp_path / "pcap_out.btides"
    _run_converter("PCAP_to_BTIDES.py",
                   "--input", str(PCAP_FIXTURE),
                   "--output", str(out),
                   "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) >= 1, f"Expected at least one BTIDES entry; got {len(data)}"


def test_pcap_to_btides_output_validates_against_schema(tmp_path, btides_validator):
    out = tmp_path / "pcap_out.btides"
    _run_converter("PCAP_to_BTIDES.py",
                   "--input", str(PCAP_FIXTURE),
                   "--output", str(out),
                   "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    btides_validator.validate(data)


def test_pcap_to_btides_entries_have_bdaddr(tmp_path):
    """Every BTIDES entry produced from a real pcap should carry a bdaddr."""
    out = tmp_path / "pcap_out.btides"
    _run_converter("PCAP_to_BTIDES.py",
                   "--input", str(PCAP_FIXTURE),
                   "--output", str(out),
                   "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    bdaddrs = {e.get("bdaddr") for e in data if isinstance(e, dict)}
    bdaddrs.discard(None)
    assert bdaddrs, f"No bdaddr fields in PCAP→BTIDES output: {data}"
    # Spot check format: lowercase XX:XX:XX:XX:XX:XX
    import re
    for b in bdaddrs:
        assert re.match(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", b), \
            f"Unexpected BDADDR formatting: {b!r}"


def test_pcap_to_btides_verbose_BTIDES_adds_type_str(tmp_path):
    """--verbose-BTIDES should add human-readable optional fields like
    type_str to each AdvData object."""
    out_default = tmp_path / "default.btides"
    out_verbose = tmp_path / "verbose.btides"
    _run_converter("PCAP_to_BTIDES.py", "--input", str(PCAP_FIXTURE),
                   "--output", str(out_default), "--quiet-print")
    _run_converter("PCAP_to_BTIDES.py", "--input", str(PCAP_FIXTURE),
                   "--output", str(out_verbose), "--verbose-BTIDES", "--quiet-print")

    def _has_key(d, k):
        if isinstance(d, dict):
            if k in d:
                return True
            return any(_has_key(v, k) for v in d.values())
        if isinstance(d, list):
            return any(_has_key(v, k) for v in d)
        return False

    with open(out_default) as f:
        default = json.load(f)
    with open(out_verbose) as f:
        verbose = json.load(f)

    assert not _has_key(default, "type_str"), \
        "Default BTIDES output unexpectedly contained type_str"
    assert _has_key(verbose, "type_str"), \
        "Verbose BTIDES output missing type_str"


# ---------------------------------------------------------------------------
# HCI_to_BTIDES.py
# ---------------------------------------------------------------------------

def test_hci_to_btides_fixture_exists():
    assert HCI_FIXTURE.exists(), f"Missing test fixture: {HCI_FIXTURE}"
    assert HCI_FIXTURE.stat().st_size > 0


def test_hci_to_btides_produces_output_file(tmp_path):
    """HCI_to_BTIDES.py against the btsnoop fixture exits 0 with no Python
    traceback and produces a non-empty BTIDES file."""
    out = tmp_path / "hci_out.btides"
    result = _run_converter("HCI_to_BTIDES.py",
                            "--input", str(HCI_FIXTURE),
                            "--output", str(out),
                            "--quiet-print")
    assert result.returncode == 0, (
        f"HCI_to_BTIDES.py exited {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr, \
        f"Traceback in HCI_to_BTIDES.py stderr:\n{result.stderr}"
    # If scapy is missing the v1 LE Meta event class, read_HCI silently
    # swallows the NameError and writes an empty list. Surface that
    # explicitly so the test fails loudly rather than passing on no data.
    assert "name 'HCI_LE_Meta_Enhanced_Connection_Update_Complete_v1' is not defined" \
        not in result.stdout, (
            "scapy in this venv lacks the v1 LE Meta connection-update class; "
            "install the Analysis/scapy submodule via "
            "`venv/bin/pip install Analysis/scapy` to fix.\n"
            f"stdout:\n{result.stdout}"
        )
    assert out.exists() and out.stat().st_size > 2, \
        f"HCI_to_BTIDES.py produced empty/missing output {out} (size={out.stat().st_size})"


def test_hci_to_btides_output_is_valid_json_list(tmp_path):
    out = tmp_path / "hci_out.btides"
    _run_converter("HCI_to_BTIDES.py",
                   "--input", str(HCI_FIXTURE),
                   "--output", str(out),
                   "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) >= 1, f"Expected at least one BTIDES entry; got {len(data)}"


def test_hci_to_btides_output_validates_against_schema(tmp_path, btides_validator):
    out = tmp_path / "hci_out.btides"
    _run_converter("HCI_to_BTIDES.py",
                   "--input", str(HCI_FIXTURE),
                   "--output", str(out),
                   "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    btides_validator.validate(data)


def test_hci_to_btides_entries_have_bdaddr(tmp_path):
    out = tmp_path / "hci_out.btides"
    _run_converter("HCI_to_BTIDES.py",
                   "--input", str(HCI_FIXTURE),
                   "--output", str(out),
                   "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    bdaddrs = {e.get("bdaddr") for e in data if isinstance(e, dict)}
    bdaddrs.discard(None)
    assert bdaddrs, f"No bdaddr fields in HCI→BTIDES output: {data}"
    import re
    for b in bdaddrs:
        assert re.match(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", b), \
            f"Unexpected BDADDR formatting: {b!r}"


def test_hci_to_btides_rejects_missing_input_file(tmp_path):
    """A missing input file must not crash with a Python traceback."""
    out = tmp_path / "should_not_exist.btides"
    bogus = tmp_path / "no_such_file.bin"
    result = _run_converter("HCI_to_BTIDES.py",
                            "--input", str(bogus),
                            "--output", str(out),
                            "--quiet-print")
    assert "Traceback" not in result.stderr, \
        f"Traceback on missing input:\n{result.stderr}"
