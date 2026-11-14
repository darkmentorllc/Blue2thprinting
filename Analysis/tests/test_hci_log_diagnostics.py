"""Malformed capture tails and unattributable vendor records remain visible."""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest


ANALYSIS = Path(__file__).resolve().parents[1]
TIMESTAMP = 0x00E03AB44A676000 + 1_000_000


def _write_btsnoop(path, records, tail=b""):
    with path.open("wb") as stream:
        stream.write(b"btsnoop\0" + struct.pack(">II", 1, 1002))
        for timestamp, packet in records:
            stream.write(struct.pack(">IIIIq", len(packet), len(packet), 3, 0, timestamp))
            stream.write(packet)
        stream.write(tail)


def test_truncated_tail_requires_explicit_recovery(tmp_path, capsys):
    from hci_log_parser import parse

    capture = tmp_path / "torn.snoop"
    packet = bytes.fromhex("04 0e 00")
    _write_btsnoop(capture, [(TIMESTAMP, packet)], tail=b"\x12\x34\x56")

    with pytest.raises(ValueError, match="Truncated BTSnoop record header"):
        parse(capture)
    records = parse(capture, allow_truncated_tail=True)
    assert [record.data for record in records] == [packet]
    assert "truncated_tail_bytes': 3" in capsys.readouterr().err


def test_zero_timestamp_packet_keeps_record_alignment(tmp_path, capsys):
    from hci_log_parser import parse

    capture = tmp_path / "zero-time.snoop"
    first = bytes.fromhex("04 0e 00")
    second = bytes.fromhex("04 0f 00")
    _write_btsnoop(capture, [(0, first), (TIMESTAMP, second)])
    assert [record.data for record in parse(capture)] == [first, second]
    assert "zero_timestamps': 1" in capsys.readouterr().err


def test_unattributed_darkfirmware_lmp_event_does_not_abort_file(tmp_path):
    capture = tmp_path / "vendor.snoop"
    output = tmp_path / "vendor.btides"
    # A rotated log may contain a vendor LMP event before Create_Connection.
    payload = bytes.fromhex(
        "41414141a0a1a2a3a4a510a0000000008004cccc4242424200000000"
        "fe017f0b0b0000000000000000000000000000000401000143434343"
    )
    assert len(payload) == 56
    _write_btsnoop(capture, [(TIMESTAMP, b"\x04\xff\x38" + payload)])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ANALYSIS / "scapy")
    result = subprocess.run(
        [sys.executable, "HCI_to_BTIDES.py", "--input", str(capture),
         "--output", str(output), "--quiet-print"],
        cwd=ANALYSIS, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped 1 DarkFirmware LMP event" in result.stderr
    assert json.loads(output.read_text()) == []


def test_incomplete_sdptool_record_fails_visibly_but_keeps_complete_one(tmp_path):
    capture = tmp_path / "f0:f1:f2:f3:a0:f2_sdp.xml"
    output = tmp_path / "partial.btides"
    capture.write_bytes(
        b'<?xml version="1.0"?><record><attribute id="0x0000">'
        b'<uint32 value="0x00000001" /></attribute></record>'
        b'<?xml version="1.0"?><record><attribute id="0x0001">'
    )
    result = subprocess.run(
        [sys.executable, "SDP_to_BTIDES.py", "--input", str(capture),
         "--output", str(output), "--quiet-print"],
        cwd=ANALYSIS, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "Incomplete SDP XML" in result.stderr
    rows = json.loads(output.read_text())
    assert len(rows) == 1 and len(rows[0]["SDPArray"]) == 1


def test_empty_sdptool_log_is_reported_as_error(tmp_path):
    capture = tmp_path / "f0:f1:f2:f3:a0:f3_sdp.xml"
    capture.touch()
    result = subprocess.run(
        [sys.executable, "SDP_to_BTIDES.py", "--input", str(capture),
         "--output", str(tmp_path / "empty.btides"), "--quiet-print"],
        cwd=ANALYSIS, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "Empty sdptool XML file" in result.stderr
    assert "1 errors across 1 files" in result.stdout


def test_sdptool_nul_corruption_is_reported_while_complete_record_is_kept(tmp_path):
    capture = tmp_path / "f0:f1:f2:f3:a0:f4_sdp.xml"
    output = tmp_path / "nul.btides"
    capture.write_bytes(
        b'<?xml version="1.0"?><record><attribute id="0x0000">'
        b'<uint32 value="0x00000001" /></attribute></record>\x00\x00'
    )
    result = subprocess.run(
        [sys.executable, "SDP_to_BTIDES.py", "--input", str(capture),
         "--output", str(output), "--quiet-print"],
        cwd=ANALYSIS, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "NUL byte corruption" in result.stderr
    assert len(json.loads(output.read_text())[0]["SDPArray"]) == 1


def test_unrecognized_sdptool_content_is_an_error(tmp_path):
    capture = tmp_path / "f0:f1:f2:f3:a0:f5_sdp.xml"
    capture.write_text("<unexpected />\n")
    result = subprocess.run(
        [sys.executable, "SDP_to_BTIDES.py", "--input", str(capture),
         "--output", str(tmp_path / "unknown.btides"), "--quiet-print"],
        cwd=ANALYSIS, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "Unrecognized non-XML sdptool content" in result.stderr


def test_multiple_inquiry_responses_are_all_exported(tmp_path):
    capture = tmp_path / "inquiry.snoop"
    output = tmp_path / "inquiry.btides"
    responses = (
        bytes.fromhex("01 02 03 04 05 06 01 00 04 02 01 00 00")
        + bytes.fromhex("11 12 13 14 15 16 01 00 08 03 02 00 00")
    )
    event = bytes((4, 2, 1 + len(responses), 2)) + responses
    _write_btsnoop(capture, [(TIMESTAMP, event)])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ANALYSIS / "scapy")
    result = subprocess.run(
        [sys.executable, "HCI_to_BTIDES.py", "--input", str(capture),
         "--output", str(output), "--quiet-print"],
        cwd=ANALYSIS, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(output.read_text())
    assert {row["bdaddr"] for row in rows} == {
        "06:05:04:03:02:01", "16:15:14:13:12:11"
    }


def test_malformed_inquiry_response_count_is_reported(tmp_path):
    capture = tmp_path / "malformed-inquiry.snoop"
    output = tmp_path / "malformed-inquiry.btides"
    _write_btsnoop(capture, [(TIMESTAMP, bytes.fromhex("04 02 02 08 00"))])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ANALYSIS / "scapy")
    result = subprocess.run(
        [sys.executable, "HCI_to_BTIDES.py", "--input", str(capture),
         "--output", str(output), "--quiet-print"],
        cwd=ANALYSIS, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped 1 Inquiry Result event" in result.stderr
    assert json.loads(output.read_text()) == []
