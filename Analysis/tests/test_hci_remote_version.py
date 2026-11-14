"""Remote version completions in HCI logs must survive BTIDES conversion."""

import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest


ANALYSIS_DIR = Path(__file__).resolve().parents[1]


def convert_records(tmp_path, records):
    capture = tmp_path / "versions.snoop"
    output = tmp_path / "versions.btides"
    with capture.open("wb") as stream:
        stream.write(b"btsnoop\0" + struct.pack(">II", 1, 1002))
        for packet in records:
            stream.write(struct.pack(">IIIIq", len(packet), len(packet), 3, 0,
                                     0x00E03AB44A676000))
            stream.write(packet)
    result = subprocess.run(
        [sys.executable, "HCI_to_BTIDES.py", "--input", str(capture),
         "--output", str(output), "--quiet-print"],
        cwd=ANALYSIS_DIR, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(output.read_text())


LE_CONNECTED = bytes.fromhex(
    "04 3e 1f 0a 00 0f 00 00 01 86 37 16 01 cc fd"
    " 00 00 00 00 00 00 00 00 00 00 00 00 24 00 00 00 f4 01 00"
)
LE_FEATURES = bytes.fromhex("04 3e 0c 04 00 0f 00 ff 79 1f f7 be 00 00 00")
VERSION_OK = bytes.fromhex("04 0c 08 00 0f 00 0c b0 02 15 01")
VERSION_FAILED = bytes.fromhex("04 0c 08 3e 0f 00 0c b0 02 15 01")
VERSION_UNKNOWN_HANDLE = bytes.fromhex("04 0c 08 00 10 00 0c b0 02 15 01")
DISCONNECTED = bytes.fromhex("04 05 04 00 0f 00 16")


def test_le_remote_version_becomes_ll_version_ind(tmp_path):
    entries = convert_records(tmp_path, [LE_CONNECTED, LE_FEATURES, VERSION_OK])
    device = next(e for e in entries if e.get("bdaddr") == "fd:cc:01:16:37:86")
    assert device["bdaddr_rand"] == 1
    assert any(
        item["opcode"] == 12 and item["version"] == 12
        and item["company_id"] == 688 and item["subversion"] == 0x115
        for item in device["LLArray"]
    )
    assert any(item["opcode"] == 9 for item in device["LLArray"])


def test_failed_and_unmapped_version_events_are_not_attributed(tmp_path):
    entries = convert_records(tmp_path, [
        LE_CONNECTED, LE_FEATURES, VERSION_FAILED, VERSION_UNKNOWN_HANDLE,
    ])
    device = next(e for e in entries if e.get("bdaddr") == "fd:cc:01:16:37:86")
    assert not any(item["opcode"] == 12 for item in device["LLArray"])


def test_version_after_disconnection_is_not_attributed_to_old_peer(tmp_path):
    entries = convert_records(tmp_path, [
        LE_CONNECTED, LE_FEATURES, DISCONNECTED, VERSION_OK,
    ])
    device = next(e for e in entries if e.get("bdaddr") == "fd:cc:01:16:37:86")
    assert not any(item["opcode"] == 12 for item in device["LLArray"])


def test_classic_remote_version_becomes_lmp_version_res(tmp_path):
    classic_connected = bytes.fromhex(
        "04 03 0b 00 02 00 66 55 44 33 22 11 01 00"
    )
    classic_version = bytes.fromhex("04 0c 08 00 02 00 0c b0 02 15 01")
    entries = convert_records(tmp_path, [classic_connected, classic_version])
    device = next(e for e in entries if e.get("bdaddr") == "11:22:33:44:55:66")
    assert any(
        item["version"] == 12 and item["company_id"] == 688
        and item["subversion"] == 0x115
        for item in device["LMPArray"]
    )
    assert "LLArray" not in device


@pytest.mark.parametrize("hci_type,btides_type", [(2, 0), (3, 1)])
def test_enhanced_identity_address_types_are_normalized(tmp_path, hci_type, btides_type):
    connection = LE_CONNECTED[:8] + bytes([hci_type]) + LE_CONNECTED[9:]
    entries = convert_records(tmp_path, [connection, VERSION_OK])
    device = next(e for e in entries if e.get("bdaddr") == "fd:cc:01:16:37:86")
    assert device["bdaddr_rand"] == btides_type
    assert device["LLArray"][0]["opcode"] == 12


@pytest.mark.parametrize("hci_type,btides_type", [(2, 0), (3, 1)])
def test_advertising_identity_address_types_are_normalized(tmp_path, hci_type, btides_type):
    report = bytes.fromhex("04 3e 0f 02 01 00") + bytes([hci_type]) + bytes.fromhex(
        "86 37 16 01 cc fd 03 02 01 06 c0"
    )
    entries = convert_records(tmp_path, [report])
    device = next(e for e in entries if e.get("bdaddr") == "fd:cc:01:16:37:86")
    assert device["bdaddr_rand"] == btides_type
    assert device["AdvChanArray"]
