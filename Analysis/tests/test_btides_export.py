########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Tell_Me_Everything.py --output ... produces a BTIDES JSON file that:
- exists,
- parses as JSON,
- validates against BTIDES_base.json (using the same registry-of-local-schemas
  approach as TME/TME_BTIDES_base.py),
- contains the expected device-specific fields.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource


BTIDES_FILES = [
    "BTIDES_base.json",
    "BTIDES_AdvData.json",
    "BTIDES_LLCP.json",
    "BTIDES_HCI.json",
    "BTIDES_L2CAP.json",
    "BTIDES_SMP.json",
    "BTIDES_ATT.json",
    "BTIDES_GATT.json",
    "BTIDES_EIR.json",
    "BTIDES_LMP.json",
    "BTIDES_SDP.json",
    "BTIDES_GPS.json",
]


@pytest.fixture(scope="module")
def btides_validator(schema_dir):
    resources = []
    for fname in BTIDES_FILES:
        with open(schema_dir / fname) as f:
            s = json.load(f)
        resources.append((s["$id"], Resource.from_contents(s)))
    registry = Registry().with_resources(resources)
    return Draft202012Validator(
        {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json"},
        registry=registry,
    )


def _validate(validator, data):
    try:
        validator.validate(data)
    except ValidationError as e:
        pytest.fail(f"BTIDES schema validation failed: {e.message}\n\n"
                    f"Failing path: {list(e.absolute_path)}\n\n"
                    f"Data: {json.dumps(data, indent=2)[:2000]}")


def _bdaddr_entries(btides_data, bdaddr_lower):
    return [
        e for e in btides_data
        if isinstance(e, dict) and e.get("bdaddr") == bdaddr_lower
    ]


def test_export_creates_file(run_tme, tmp_path):
    out = tmp_path / "out.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--output", str(out), "--quiet-print")
    assert out.exists(), "BTIDES output file was not created"
    assert out.stat().st_size > 0, "BTIDES output file is empty"


def test_export_is_valid_json(run_tme, tmp_path):
    out = tmp_path / "out.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--output", str(out), "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) >= 1


def test_export_validates_against_schema(run_tme, tmp_path, btides_validator):
    out = tmp_path / "out.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--output", str(out), "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    _validate(btides_validator, data)


def test_export_device1_contents(run_tme, tmp_path):
    """Device 1 export should round-trip name, UUID16, tx_power, MSD."""
    out = tmp_path / "out.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--output", str(out), "--quiet-print")
    with open(out) as f:
        data = json.load(f)

    entries = _bdaddr_entries(data, "aa:bb:cc:11:22:01")
    assert entries, f"No entry for aa:bb:cc:11:22:01 in {data}"
    entry = entries[0]
    assert entry["bdaddr_rand"] == 0
    assert "AdvChanArray" in entry, "Expected AdvData under AdvChanArray"

    # Flatten all AdvData entries across all AdvChan groups.
    advdata = []
    for chan in entry["AdvChanArray"]:
        advdata.extend(chan.get("AdvDataArray", []))

    # type 9 = Complete Local Name, payload "TestDevice1"
    name_entries = [a for a in advdata if a.get("type") == 9]
    assert name_entries, "No Complete Local Name in AdvData"
    assert "TestDevice1".encode("utf-8").hex() == name_entries[0]["name_hex_str"]

    # type 2 = Complete List of UUID16 Service IDs, must include 180d
    uuid16_entries = [a for a in advdata if a.get("type") == 2]
    assert uuid16_entries
    assert "180d" in uuid16_entries[0]["UUID16List"]

    # type 10 = TX Power Level
    tx_entries = [a for a in advdata if a.get("type") == 10]
    assert tx_entries
    assert tx_entries[0]["tx_power"] == -4

    # type 255 = Manufacturer Specific Data — Apple CID 0x004c
    msd_entries = [a for a in advdata if a.get("type") == 255]
    assert msd_entries
    assert msd_entries[0]["company_id_hex_str"] == "004c"


def test_export_multi_device(run_tme, tmp_path, btides_validator):
    """--bdaddr-regex AA:BB:CC exports all five seeded devices."""
    out = tmp_path / "out.btides"
    run_tme("--bdaddr-regex", "AA:BB:CC", "--output", str(out), "--quiet-print")
    with open(out) as f:
        data = json.load(f)

    _validate(btides_validator, data)
    bdaddrs_in_export = {e["bdaddr"] for e in data if isinstance(e, dict) and "bdaddr" in e}
    expected = {f"aa:bb:cc:11:22:0{n}" for n in range(1, 6)}
    assert expected.issubset(bdaddrs_in_export), \
        f"Missing devices in export: {expected - bdaddrs_in_export}"


def test_export_device3_classic_eir(run_tme, tmp_path, btides_validator):
    """Device 3 has BT Classic EIR data; check it round-trips."""
    out = tmp_path / "out.btides"
    run_tme("--bdaddr", "AA:BB:CC:11:22:03", "--output", str(out), "--quiet-print")
    with open(out) as f:
        data = json.load(f)
    _validate(btides_validator, data)
    entries = _bdaddr_entries(data, "aa:bb:cc:11:22:03")
    assert entries, "Device 3 missing from export"
    # Just confirm the entry exists and has SOME content (EIR / HCI etc.).
    # The exact field names vary by which tables had data.
    assert entries[0].keys() != {"bdaddr", "bdaddr_rand"}, \
        "Device 3 entry has no extra fields — EIR data didn't make it into export"


def test_quiet_print_suppresses_stdout(run_tme, tmp_path):
    """--quiet-print + --output should keep stdout empty (or near-empty)."""
    out = tmp_path / "out.btides"
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--output", str(out), "--quiet-print")
    # Some debug "0 bdaddrs_to_remove" output may still appear; just assert
    # the device-rendering "For bdaddr =" sections are absent.
    assert "For bdaddr" not in result.stdout, \
        f"Expected no per-device output with --quiet-print; got:\n{result.stdout}"
