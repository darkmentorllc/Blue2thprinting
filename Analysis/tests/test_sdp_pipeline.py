"""SDP regressions from redacted, real HCI log slices through TME."""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest


ANALYSIS_DIR = Path(__file__).resolve().parents[1]
CAPTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "hci_reference"


def _write_hci_slice(path, frames):
    """Write H4 frames with btsnoop direction flags for a small mutation test."""
    timestamp = 0x00E03AB44A676000 + 1_000_000
    with path.open("wb") as output:
        output.write(b"btsnoop\x00" + struct.pack(">II", 1, 1002))
        for flags, data in frames:
            output.write(struct.pack(">IIIIq", len(data), len(data), flags, 0, timestamp))
            output.write(data)
            timestamp += 1_000_000


def _real_first_channel_frames():
    from hci_log_parser import parse

    capture = CAPTURE_DIR / "classic_sdp_records_qa.snoop"
    return [(record.flags, record.data) for record in parse(capture)[:5]]


def _convert_slice(capture, output, *, to_sql=False):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ANALYSIS_DIR / "scapy"), env.get("PYTHONPATH", "")) if part
    )
    args = [sys.executable, "HCI_to_BTIDES.py", "--input", str(capture),
            "--output", str(output), "--quiet-print"]
    if to_sql:
        args += ["--to-SQL", "--use-test-db"]
    result = subprocess.run(args, cwd=ANALYSIS_DIR, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(output.read_text())


@pytest.mark.parametrize(
    "capture,peer,handles,response_count",
    [
        ("classic_sdp_records_qa.snoop", "f0:f1:f2:f3:a0:ef",
         (0x10004, 0x10001, 0x10002, 0x10003, 0x10005), 4),
        ("classic_sdp_continuation_qa.snoop", "f0:f1:f2:f3:a0:f0",
         (0x10001, 0x10002), 19),
    ],
)
def test_hci_to_btides_to_sql_to_tme(
    db_clean, run_tme, tmp_path, capture, peer, handles, response_count,
):
    btides_path = tmp_path / "from_hci.btides"
    tme_path = tmp_path / "from_sql.btides"
    rows = _convert_slice(CAPTURE_DIR / capture, btides_path, to_sql=True)
    connection, = (row for row in rows if "SDPArray" in row)
    assert connection["CONNECT_IND"]["peripheral_bdaddr"] == peer
    responses = [item for item in connection["SDPArray"]
                 if item["direction"] == 1 and item["pdu_id"] in (5, 7)]
    assert len(responses) == response_count

    query = ("SELECT HEX(byte_values) FROM SDP_Common "
             f"WHERE bdaddr = '{peer}' AND direction = 1 ORDER BY id")
    stored = subprocess.run(
        ["mysql", "-u", "user", "-pa", "-D", "bttest", "--batch",
         "--skip-column-names", "-e", query],
        check=True, capture_output=True, text=True,
    )
    assert stored.stdout.splitlines() == [
        item["raw_data_hex_str"].upper() for item in responses
    ]
    requests = [item for item in connection["SDPArray"]
                if item["direction"] == 0 and "raw_data_hex_str" in item]
    stored_requests = subprocess.run(
        ["mysql", "-u", "user", "-pa", "-D", "bttest", "--batch",
         "--skip-column-names", "-e",
         "SELECT HEX(byte_values) FROM SDP_Common "
         f"WHERE bdaddr = '{peer}' AND direction = 0 ORDER BY id"],
        check=True, capture_output=True, text=True,
    )
    assert stored_requests.stdout.splitlines() == [
        item["raw_data_hex_str"].upper() for item in requests
    ]

    displayed = run_tme("--bdaddr", peer, "--output", str(tme_path))
    assert "SDP Services:" in displayed.stdout
    assert "Handle ?:" not in displayed.stdout
    for handle in handles:
        assert displayed.stdout.count(f"Handle 0x{handle:08x}:") == 1
    assert displayed.stdout.count("    Handle ") == len(handles)

    tme_rows = json.loads(tme_path.read_text())
    tme_sdp = [item for row in tme_rows for item in row.get("SDPArray", [])]
    assert [item["raw_data_hex_str"] for item in tme_sdp if item["direction"] == 1] == [
        item["raw_data_hex_str"] for item in responses
    ]
    assert [item["raw_data_hex_str"] for item in tme_sdp if item["direction"] == 0] == [
        item["raw_data_hex_str"] for item in requests
    ]


def test_sdp_data_elements_are_bounded_and_support_all_base_types():
    from TME.TME_SDP import _parse_sdp_elem_val, _parse_sdp_all_records

    # NIL must consume only its descriptor; signed integer, UUID32, bool,
    # and alternative are all valid element types in captured SDP data.
    stream = bytes.fromhex("0010ff1a1234567828003d0100")
    values = []
    offset = 0
    while offset < len(stream):
        value, offset = _parse_sdp_elem_val(stream, offset)
        values.append(value)
    assert values == [None, -1, ("uuid32", 0x12345678), False, [None]]

    for malformed in (b"\x35", b"\x35\x03\x09\x00",
                      b"\x35\x02\x35\x01", b"\x3f\xff\xff\xff\xff"):
        with pytest.raises(ValueError):
            _parse_sdp_elem_val(malformed, 0)
        assert _parse_sdp_all_records(malformed) == []


def test_rejected_l2cap_channel_does_not_export_sdp(tmp_path):
    frames = _real_first_channel_frames()
    failed_response = bytearray(frames[2][1])
    assert failed_response[17:19] == b"\x00\x00"
    failed_response[17:19] = b"\x02\x00"
    frames[2] = (frames[2][0], bytes(failed_response))
    capture = tmp_path / "rejected.snoop"
    _write_hci_slice(capture, frames)
    rows = _convert_slice(capture, tmp_path / "rejected.btides")
    assert not any(row.get("SDPArray") for row in rows)


def test_disconnection_clears_sdp_channel_state(tmp_path):
    frames = _real_first_channel_frames()
    repeated_response = bytearray(frames[4][1])
    repeated_response[10:12] = b"\x00\x01"  # new transaction, not deduplicated
    frames.extend([
        (3, bytes.fromhex("040504000b0016")),  # HCI Disconnection Complete
        frames[0],  # same handle and peer on a new connection
        (1, bytes(repeated_response)),
    ])
    capture = tmp_path / "reconnected.snoop"
    _write_hci_slice(capture, frames)
    rows = _convert_slice(capture, tmp_path / "reconnected.btides")
    assert sum(len(row.get("SDPArray", [])) for row in rows) == 2


def test_hci_acl_fragments_reassemble_before_sdp_export(tmp_path):
    frames = _real_first_channel_frames()
    original = frames[-1][1]
    acl_payload = original[5:]
    first_part, second_part = acl_payload[:19], acl_payload[19:]
    first = original[:3] + len(first_part).to_bytes(2, "little") + first_part
    continuation = (b"\x02" + (0x100b).to_bytes(2, "little")
                    + len(second_part).to_bytes(2, "little") + second_part)
    frames[-1:] = [(1, first), (1, continuation)]
    capture = tmp_path / "fragmented.snoop"
    _write_hci_slice(capture, frames)
    rows = _convert_slice(capture, tmp_path / "fragmented.btides")
    response, = [item for row in rows for item in row.get("SDPArray", [])
                 if item["pdu_id"] == 7]
    assert response["raw_data_hex_str"] == original[14:].hex()
    assert response["param_len"] == len(original) - 14


def test_mismatched_sdp_parameter_length_is_ignored(tmp_path):
    frames = _real_first_channel_frames()
    malformed = bytearray(frames[-1][1])
    malformed[12:14] = (80).to_bytes(2, "big")
    frames[-1] = (frames[-1][0], bytes(malformed))
    capture = tmp_path / "bad_length.snoop"
    _write_hci_slice(capture, frames)
    rows = _convert_slice(capture, tmp_path / "bad_length.btides")
    assert [item["pdu_id"] for row in rows
            for item in row.get("SDPArray", [])] == [6]


def test_error_response_reaches_sql_and_tme(db_clean, run_tme, tmp_path):
    frames = _real_first_channel_frames()
    error = bytearray(frames[4][1][:9])
    error[3:5] = (11).to_bytes(2, "little")
    error[5:7] = (7).to_bytes(2, "little")
    error.extend(bytes.fromhex("01000000020002"))
    frames[4] = (frames[4][0], bytes(error))
    capture = tmp_path / "error.snoop"
    _write_hci_slice(capture, frames)
    rows = _convert_slice(capture, tmp_path / "error.btides", to_sql=True)
    sdp = [item for row in rows for item in row.get("SDPArray", [])]
    assert [item["pdu_id"] for item in sdp] == [6, 1]
    assert sdp[-1]["error_code"] == 2

    output = tmp_path / "error_from_sql.btides"
    displayed = run_tme("--bdaddr", "f0:f1:f2:f3:a0:ef", "--output", str(output))
    assert "SDP error response: 0x0002" in displayed.stdout
    exported = [item for row in json.loads(output.read_text())
                for item in row.get("SDPArray", [])]
    assert len(exported) == 2
    assert next(item for item in exported if item["pdu_id"] == 1)["error_code"] == 2
    assert next(item for item in exported if item["direction"] == 0)["pdu_id"] == 6
