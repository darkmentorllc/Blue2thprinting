"""Focused synthetic H4 captures for the DM BT Secure DFU HCI verifier."""

import datetime as dt
import json
import struct
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALYSIS_DIR))

from verify_dm_bt_dfu_hci import verify_file  # noqa: E402


PEER = "F3:81:6C:44:04:1B"
CP = 0x000F
CCCD = 0x0010
BASE_MS = 1792798953000
SNOOP_TO_2000_US = 0x00E03AB44A676000
UNIX_TO_2000_MS = int(dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _event(code, params):
    return bytes([4, code, len(params)]) + params


def _connection(handle):
    address = bytes.fromhex(PEER.replace(":", ""))[::-1]
    params = bytes([0x0A, 0x00]) + handle.to_bytes(2, "little") + bytes([0, 1]) + address + bytes(19)
    return _event(0x3E, params)


def _disconnect(handle):
    return _event(0x05, bytes([0]) + handle.to_bytes(2, "little") + bytes([0x13]))


def _encrypt_v2(handle):
    return _event(0x59, bytes([0]) + handle.to_bytes(2, "little") + bytes([1, 16]))


def _acl(handle, pdu, direction, cid=4):
    l2cap = len(pdu).to_bytes(2, "little") + cid.to_bytes(2, "little") + pdu
    word = handle | (2 << 12)
    packet = bytes([2]) + word.to_bytes(2, "little") + len(l2cap).to_bytes(2, "little") + l2cap
    return direction, packet


def _write_request(handle, value):
    return bytes([0x12]) + handle.to_bytes(2, "little") + value


def _notify(handle):
    return bytes([0x1B]) + handle.to_bytes(2, "little") + bytes.fromhex("6003010000000000000000")


def _records(handle=0x0040, *, missing_notification=False, encryption="none",
             auth_error=False, fragment_second_write=False, drop_on_second=False,
             truncated_record=False):
    # Each entry is (timestamp in milliseconds, btsnoop flags, H4 packet, orig_len override, drops).
    rows = []

    def add(offset, flags, packet, orig_len=None, drops=0):
        rows.append((BASE_MS + offset, flags, packet, orig_len, drops))

    add(0, 3, _connection(handle))
    add(10, 1, _acl(handle, bytes([0x11, 6, 0x0B, 0, 0xFF, 0xFF, 0x59, 0xFE]), 1)[1])
    cp_uuid_le = bytes.fromhex("8ec90001f3154f609fb8838830daea50")[::-1]
    add(20, 1, _acl(handle, bytes([0x09, 21, 0x0E, 0, 0x18, CP, 0]) + cp_uuid_le, 1)[1])
    add(30, 1, _acl(handle, bytes([0x05, 1, CCCD, 0, 0x02, 0x29]), 1)[1])
    if encryption == "before":
        add(35, 3, _encrypt_v2(handle))
    add(40, 0, _acl(handle, _write_request(CP, b"\x03"), 0)[1])
    if auth_error:
        add(50, 1, _acl(handle, bytes([0x01, 0x12, CP, 0, 0x05]), 1)[1])
        add(200, 3, _disconnect(handle))
        return rows
    add(50, 1, _acl(handle, b"\x13", 1)[1])
    add(60, 0, _acl(handle, _write_request(CCCD, b"\x01\x00"), 0)[1])
    add(70, 1, _acl(handle, b"\x13", 1)[1])
    second = _write_request(CP, b"\x03")
    if fragment_second_write:
        l2cap = len(second).to_bytes(2, "little") + b"\x04\x00" + second
        first = l2cap[:6]
        continuation = l2cap[6:]
        packet1 = bytes([2]) + (handle | (2 << 12)).to_bytes(2, "little") + len(first).to_bytes(2, "little") + first
        packet2 = bytes([2]) + (handle | (1 << 12)).to_bytes(2, "little") + len(continuation).to_bytes(2, "little") + continuation
        add(80, 0, packet1)
        add(85, 0, packet2, drops=1 if drop_on_second else 0)
    else:
        packet = _acl(handle, second, 0)[1]
        add(80, 0, packet, len(packet) + 1 if truncated_record else None,
            1 if drop_on_second else 0)
    add(90, 1, _acl(handle, b"\x13", 1)[1], drops=1 if drop_on_second else 0)
    if not missing_notification:
        add(100, 1, _acl(handle, _notify(CP), 1)[1], drops=1 if drop_on_second else 0)
    if encryption == "after":
        add(110, 3, _encrypt_v2(handle), drops=1 if drop_on_second else 0)
    add(200, 3, _disconnect(handle), drops=1 if drop_on_second else 0)
    return rows


def _write_btsnoop(path, rows):
    with path.open("wb") as stream:
        stream.write(b"btsnoop\0" + struct.pack(">II", 1, 1002))
        for millis, flags, packet, orig_len, drops in rows:
            snoop_time = SNOOP_TO_2000_US + (millis - UNIX_TO_2000_MS) * 1000
            stream.write(struct.pack(">IIIIq", orig_len or len(packet), len(packet), flags, drops, snoop_time))
            stream.write(packet)


def _probe():
    return {
        "address": PEER,
        "address_type": 1,
        "time_ms": BASE_MS + 120,
        "service_uuid": "0000fe59-0000-1000-8000-00805f9b34fb",
        "control_point_uuid": "8ec90001-f315-4f60-9fb8-838830daea50",
        "control_point_value_handle": CP,
        "cccd_handle": CCCD,
        "outcome": "CRC_RESPONSE_RECEIVED",
        "crc_response_hex": "6003010000000000000000",
    }


def _verify(tmp_path, rows, probe=None):
    log = tmp_path / "capture.log"
    jsonl = tmp_path / "results.jsonl"
    _write_btsnoop(log, rows)
    jsonl.write_text(json.dumps(probe or _probe()) + "\n")
    return verify_file(log, jsonl)[0]


def test_unencrypted_crc_response_has_specific_evidence(tmp_path):
    result = _verify(tmp_path, _records())
    assert result["hciVerdict"] == "VERIFIED_UNENCRYPTED"
    assert result["hciConnectionHandle"] == "0x0040"
    assert result["hciCpWriteFrames"] == [5, 9]
    assert result["hciCccdWriteFrames"] == [7]
    assert result["hciCrcNotificationFrame"] == 11
    assert result["hciSecurityEventFrames"] == []


def test_encryption_change_v2_blocks_unencrypted_verdict(tmp_path):
    result = _verify(tmp_path, _records(encryption="before"))
    assert result["hciVerdict"] == "ENCRYPTED_OR_PAIRED"
    assert any(event["kind"] == "ENCRYPTION_CHANGE" for event in result["hciSecurityEvents"])


def test_encryption_after_crc_does_not_erase_prior_plaintext_result(tmp_path):
    result = _verify(tmp_path, _records(encryption="after"))
    assert result["hciVerdict"] == "VERIFIED_UNENCRYPTED"
    assert result["hciSecurityEventFrames"]


def test_missing_notification_is_inconclusive(tmp_path):
    result = _verify(tmp_path, _records(missing_notification=True))
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert result["hciCrcNotificationFrame"] is None


def test_two_sessions_with_same_address_and_probe_are_ambiguous(tmp_path):
    first = _records(handle=0x0040)
    second = [(millis + 500, flags, packet, orig_len, drops) for millis, flags, packet, orig_len, drops in _records(handle=0x0041)]
    probe = _probe()
    probe["time_ms"] = BASE_MS + 650
    result = _verify(tmp_path, first + second, probe)
    assert result["hciVerdict"] == "AMBIGUOUS_SESSION"


def test_connection_timestamp_disambiguates_rapid_reconnect(tmp_path):
    first = _records(handle=0x0040)
    second = [(millis + 500, flags, packet, orig_len, drops)
              for millis, flags, packet, orig_len, drops in _records(handle=0x0041)]
    probe = _probe()
    probe["time_ms"] = BASE_MS + 650
    probe["connection_time_ms"] = BASE_MS + 500
    probe["probe_started_at_ms"] = BASE_MS + 535
    result = _verify(tmp_path, first + second, probe)
    assert result["hciVerdict"] == "VERIFIED_UNENCRYPTED"
    assert result["hciConnectionHandle"] == "0x0041"


def test_att_authentication_error_is_reported(tmp_path):
    result = _verify(tmp_path, _records(auth_error=True))
    assert result["hciVerdict"] == "AUTHENTICATION_REQUIRED"
    assert result["hciAttErrorFrames"] == [6]


def test_cccd_gate_att_error_is_partial_evidence_not_full_crc_success(tmp_path):
    rows = _records(auth_error=True)
    millis, flags, _, orig_len, drops = rows[5]
    rows[5] = (millis, flags, _acl(0x0040, bytes([0x01, 0x12, CP, 0, 0xFD]), 1)[1], orig_len, drops)
    probe = _probe()
    probe["outcome"] = "CCCD_GATE_REACHED"
    del probe["crc_response_hex"]
    result = _verify(tmp_path, rows, probe)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert result["hciAttErrors"] == [{"frame": 6, "handle": "0x000f", "requestOpcode": "0x12", "errorCode": "0xfd"}]


def test_fragmented_acl_reassembles_att_write(tmp_path):
    result = _verify(tmp_path, _records(fragment_second_write=True))
    assert result["hciVerdict"] == "VERIFIED_UNENCRYPTED"
    assert len(result["hciCpWriteFrames"]) == 2


def test_packet_loss_or_truncated_record_blocks_positive(tmp_path):
    assert _verify(tmp_path, _records(drop_on_second=True))["hciVerdict"] == "INCONCLUSIVE"
    assert _verify(tmp_path, _records(truncated_record=True))["hciVerdict"] == "INCONCLUSIVE"


def test_address_type_mismatch_is_not_matched(tmp_path):
    probe = _probe()
    probe["address_type"] = 0
    assert _verify(tmp_path, _records(), probe)["hciVerdict"] == "NO_MATCHING_CONNECTION"


def test_missing_connection_start_cannot_prove_plaintext(tmp_path):
    assert _verify(tmp_path, _records()[1:])["hciVerdict"] == "NO_MATCHING_CONNECTION"


def test_smp_pairing_request_blocks_unencrypted_verdict(tmp_path):
    rows = _records()
    smp_packet = _acl(0x0040, b"\x01\x03\x00", 0, cid=6)[1]
    rows.insert(4, (BASE_MS + 35, 0, smp_packet, None, 0))
    result = _verify(tmp_path, rows)
    assert result["hciVerdict"] == "ENCRYPTED_OR_PAIRED"
    assert any(event["kind"] == "SMP" for event in result["hciSecurityEvents"])


def test_unidentified_cccd_is_not_inferred_from_adjacent_handle(tmp_path):
    rows = [row for row in _records() if not (row[2].startswith(b"\x02") and b"\x05\x01\x10\x00\x02\x29" in row[2])]
    probe = _probe()
    del probe["cccd_handle"]
    result = _verify(tmp_path, rows, probe)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert result["hciCccdHandle"] is None


def test_skipped_app_record_cannot_adopt_nearby_hci_exchange(tmp_path):
    probe = _probe()
    probe["outcome"] = "SKIPPED"
    del probe["crc_response_hex"]
    result = _verify(tmp_path, _records(), probe)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert result["hciCrcNotificationFrame"] is not None
    assert "app CRC_RESPONSE_RECEIVED" in result["hciDetail"]


def test_success_outcome_needs_matching_app_response_bytes(tmp_path):
    probe = _probe()
    del probe["crc_response_hex"]
    assert _verify(tmp_path, _records(), probe)["hciVerdict"] == "INCONCLUSIVE"
    probe["crc_response_hex"] = "6003011111111111111111"
    assert _verify(tmp_path, _records(), probe)["hciVerdict"] == "INCONCLUSIVE"


def _incomplete_smp_start(handle):
    fragment = b"\x0a\x00\x06\x00\x01"  # claims 10-byte SMP PDU, contains only opcode
    return bytes([2]) + (handle | (2 << 12)).to_bytes(2, "little") + \
        len(fragment).to_bytes(2, "little") + fragment


def test_dangling_smp_fragment_at_disconnect_blocks_positive(tmp_path):
    rows = _records()
    rows.insert(-2, (BASE_MS + 95, 0, _incomplete_smp_start(0x0040), None, 0))
    # Keep capture time order: the notification is at +100 ms.
    rows.sort(key=lambda row: row[0])
    result = _verify(tmp_path, rows)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert "incomplete ACL/L2CAP" in result["hciDetail"]


def test_new_pb_start_cannot_overwrite_partial_smp(tmp_path):
    rows = _records()
    rows.insert(4, (BASE_MS + 35, 0, _incomplete_smp_start(0x0040), None, 0))
    result = _verify(tmp_path, rows)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert "incomplete ACL/L2CAP" in result["hciDetail"]


def test_overlong_l2cap_body_blocks_positive(tmp_path):
    rows = _records()
    packet = bytearray(_acl(0x0040, b"\x0b\x00", 0)[1])
    packet[5:7] = (1).to_bytes(2, "little")  # captured body is 2 bytes, declared is 1
    rows.insert(4, (BASE_MS + 35, 0, bytes(packet), None, 0))
    result = _verify(tmp_path, rows)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert "incomplete ACL/L2CAP" in result["hciDetail"]


def test_later_probe_cannot_claim_earlier_pre_pairing_crc_response(tmp_path):
    rows = _records()
    rows.insert(-1, (BASE_MS + 120, 3, _encrypt_v2(0x0040), None, 0))
    probe = _probe()
    probe["probe_started_at_ms"] = BASE_MS + 150
    probe["connection_time_ms"] = BASE_MS
    probe["time_ms"] = BASE_MS + 180
    result = _verify(tmp_path, rows, probe)
    assert result["hciVerdict"] == "INCONCLUSIVE"
    assert result["hciCrcNotificationFrame"] is None
    assert result["hciCpWriteFrames"] == []
    assert result["hciSecurityEventFrames"]


def test_latest_notification_inside_probe_window_is_selected(tmp_path):
    rows = _records()
    rows.pop()  # Keep the same connection open for a second safe probe.
    second_exchange = [(millis + 220, flags, packet, orig_len, drops)
                       for millis, flags, packet, orig_len, drops in _records()[4:-1]]
    rows.extend(second_exchange)
    rows.append((BASE_MS + 500, 3, _disconnect(0x0040), None, 0))
    probe = _probe()
    probe["probe_started_at_ms"] = BASE_MS + 255
    probe["connection_time_ms"] = BASE_MS
    probe["time_ms"] = BASE_MS + 340
    result = _verify(tmp_path, rows, probe)
    assert result["hciVerdict"] == "VERIFIED_UNENCRYPTED"
    assert result["hciCrcNotificationFrame"] == 18
    assert result["hciCpWriteFrames"] == [12, 16]
