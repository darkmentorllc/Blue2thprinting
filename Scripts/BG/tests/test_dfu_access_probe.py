"""The optional FE59 probe must send one benign, correlated plaintext write."""

import json

import pytest

import BG_Helper_DFU as dfu
from BG_Helper_GATT import stateful_GATT_getter


@pytest.fixture
def ready_probe(tmp_path, clean_globals, mock_hw, monkeypatch):
    g = clean_globals
    g.target_bdaddr = "ca:fe:13:37:00:01"
    g.primary_services_all_recv = True
    g.secondary_services_all_recv = True
    g.all_info_handles_recv = True
    g.characteristic_read_by_type_req_all_received = True
    g.att_MTU_negotiated = True
    g.primary_services_read_req_sent_time = 1
    g.secondary_services_read_req_sent_time = 1
    g.primary_service_handle_ranges_dict = {0x0010: (0x001F, 0xFE59, 2)}
    g.received_handles = {
        0x0011: b"\x03\x28",
        0x0012: dfu.CONTROL_POINT_UUID_LE,
        0x0013: b"\x02\x29",  # Control Point CCCD; not the value handle.
        0x0014: b"\x03\x28",
        0x0015: dfu.PACKET_UUID_LE,
    }
    result_path = tmp_path / "capture.nordic_dfu_probe.json"
    probe = dfu.NordicDfuAccessProbe(result_path, tmp_path / "capture.pcap")
    g.nordic_dfu_access_probe = probe
    monkeypatch.setattr(dfu, "print_and_exit", lambda: None)
    return probe, result_path, g, mock_hw


def _result(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _att(l2cap_body, make_dpkt):
    return make_dpkt(body=b"\x02" + bytes([len(l2cap_body) + 4]) +
                     len(l2cap_body).to_bytes(2, "little") + b"\x04\x00" + l2cap_body)


def test_exact_fe59_probe_sends_one_get_crc_write_before_value_reads(
        ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    assert probe.process(make_dpkt(body=b"\x02\x00")) is True
    assert hw.transmitted == [(2, b"\x04\x00\x04\x00\x12\x12\x00\x03")]
    assert probe.process(make_dpkt(body=b"\x02\x00")) is True
    assert len(hw.transmitted) == 1
    result = _result(path)
    assert result["status"] == "awaiting_control_initial_att_response"
    assert result["attempts"] == 1
    assert result["control_point_value_handle"] == 0x0012
    assert result["packet_value_handle"] == 0x0015
    assert result["dfu_request_hex"] == "03"
    assert result["packet_write_access"] == "unknown"
    assert result["toctou_implementation"] == "unknown"


def test_write_response_then_success_notification_confirms_get_crc(ready_probe, make_dpkt):
    probe, path, _, _ = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x13", make_dpkt))
    assert _result(path)["control_point_att_admitted"] is True
    assert _result(path)["status"] == "awaiting_initial_get_crc_notification"
    probe.process(_att(b"\x1b\x12\x00\x60\x03\x01" + b"\x00" * 8, make_dpkt))
    result = _result(path)
    assert result["status"] == "get_crc_confirmed_unencrypted"
    assert result["get_crc_notification_confirmed"] is True
    assert "unproven" in result["interpretation"]


def test_security_error_must_name_control_point_value_handle(ready_probe, make_dpkt):
    probe, path, _, _ = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x12\x00\x05", make_dpkt))
    result = _result(path)
    assert result["status"] == "write_security_gated"
    assert result["att_handle_in_error"] == 0x0012
    assert result["att_error_code"] == 0x05


def test_cccd_error_does_not_classify_control_point_as_gated(ready_probe, make_dpkt):
    probe, path, _, _ = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x13\x00\x05", make_dpkt))
    result = _result(path)
    assert result["status"] == "inconclusive_error_on_other_handle"
    assert result["att_handle_in_error"] == 0x0013


def test_cccd_prerequisite_then_successful_repeat(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x12\x00\xfd", make_dpkt))
    assert hw.transmitted[-1] == (2, b"\x05\x00\x04\x00\x12\x13\x00\x01\x00")
    assert _result(path)["status"] == "awaiting_cccd_enable_att_response"
    probe.process(_att(b"\x13", make_dpkt))
    assert hw.transmitted[-1] == (2, b"\x04\x00\x04\x00\x12\x12\x00\x03")
    assert _result(path)["attempts"] == 3
    probe.process(_att(b"\x13", make_dpkt))
    probe.process(_att(b"\x1b\x12\x00\x60\x03\x01" + b"\x00" * 8, make_dpkt))
    result = _result(path)
    assert result["status"] == "get_crc_confirmed_unencrypted"
    assert [(item["handle"], item["value_hex"])
            for item in result["observations"] if item["direction"] == "central_to_peripheral"] == [
                (0x0012, "03"), (0x0013, "0100"), (0x0012, "03")]


def test_cccd_security_denial_is_not_control_point_denial(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x12\x00\xfd", make_dpkt))
    probe.process(_att(b"\x01\x12\x13\x00\x05", make_dpkt))
    result = _result(path)
    assert result["status"] == "inconclusive_cccd_write_rejected"
    assert result["att_handle_in_error"] == 0x0013
    assert len(hw.transmitted) == 2


def test_cccd_prerequisite_without_exact_descriptor_is_inconclusive(ready_probe, make_dpkt):
    probe, path, g, hw = ready_probe
    del g.received_handles[0x0013]
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x12\x00\xfd", make_dpkt))
    assert _result(path)["status"] == "inconclusive_cccd_unavailable"
    assert len(hw.transmitted) == 1


def test_initial_att_admission_uses_cccd_confirmation_after_grace(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x13", make_dpkt))
    probe.sent_at -= probe.initial_notification_grace_seconds + 0.1
    probe.process(make_dpkt(body=b"\x02\x00"))
    assert _result(path)["status"] == "awaiting_cccd_enable_att_response"
    assert len(hw.transmitted) == 2


def test_final_notification_timeout_is_inconclusive(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x12\x00\xfd", make_dpkt))
    probe.process(_att(b"\x13", make_dpkt))
    probe.process(_att(b"\x13", make_dpkt))
    probe.sent_at -= probe.timeout_seconds + 0.1
    probe.process(make_dpkt(body=b"\x02\x00"))
    assert _result(path)["status"] == "inconclusive_notification_timeout"
    assert len(hw.transmitted) == 3


def test_get_crc_negative_notification_is_recorded_as_inconclusive(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x13", make_dpkt))
    probe.process(_att(b"\x1b\x12\x00\x60\x03\x0a", make_dpkt))
    result = _result(path)
    assert result["status"] == "inconclusive_get_crc_negative_notification"
    assert result["control_point_att_admitted"] is True
    assert result["observations"][-1]["value_hex"] == "60030a"
    assert len(hw.transmitted) == 1


@pytest.mark.parametrize("error_code, expected", [
    (0x08, "write_authorization_gated"),
    (0x0C, "inconclusive_key_size_error"),
])
def test_other_security_related_errors_are_distinct(
        ready_probe, make_dpkt, error_code, expected):
    probe, path, _, _ = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.process(_att(b"\x01\x12\x12\x00" + bytes([error_code]), make_dpkt))
    assert _result(path)["status"] == expected


def test_missing_packet_characteristic_does_not_write(ready_probe, make_dpkt):
    probe, path, g, hw = ready_probe
    del g.received_handles[0x0015]
    probe.process(make_dpkt(body=b"\x02\x00"))
    assert hw.transmitted == []
    assert _result(path)["status"] == "not_tested_incomplete_fe59"


def test_probe_times_out_without_retry_and_requests_teardown(
        ready_probe, make_dpkt, monkeypatch):
    probe, path, _, hw = ready_probe
    teardown_calls = []
    monkeypatch.setattr(dfu, "print_and_exit", lambda: teardown_calls.append(True))
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.sent_at -= probe.timeout_seconds + 0.1
    probe.process(make_dpkt(body=b"\x02\x00"))
    result = _result(path)
    assert result["status"] == "inconclusive_timeout"
    assert result["connection_teardown_requested"] is True
    assert teardown_calls == [True]
    assert len(hw.transmitted) == 1


def test_pending_att_timeout_advances_on_non_packet_tick(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    probe.sent_at -= probe.timeout_seconds + 0.1
    probe.tick()
    assert _result(path)["status"] == "inconclusive_timeout"
    assert len(hw.transmitted) == 1


def test_link_loss_ends_probe_without_retry(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.process(make_dpkt(body=b"\x02\x00"))
    with pytest.raises(SystemExit):
        probe.finish_link_lost()
    assert _result(path)["status"] == "inconclusive_link_lost"
    assert len(hw.transmitted) == 1


def test_encryption_observation_suppresses_plaintext_probe(ready_probe, make_dpkt):
    probe, path, _, hw = ready_probe
    probe.observe_ll_control(0x05)
    probe.process(make_dpkt(body=b"\x02\x00"))
    assert hw.transmitted == []
    assert _result(path)["status"] == "not_tested_security_transition"


@pytest.mark.parametrize("opcode", [0x0A, 0x0B])
def test_encryption_pause_control_suppresses_probe(ready_probe, make_dpkt, opcode):
    probe, path, _, hw = ready_probe
    probe.observe_ll_control(opcode)
    probe.process(make_dpkt(body=b"\x02\x00"))
    assert hw.transmitted == []
    assert _result(path)["link_context"]["ll_encryption_control_opcodes"] == [opcode]


def test_inbound_smp_packet_suppresses_plaintext_probe(
        ready_probe, make_dpkt, l2cap_body):
    from Better_Getter import print_packet

    probe, path, _, hw = ready_probe
    print_packet(make_dpkt(body=l2cap_body(0x0006, b"\x01\x03\x00\x00\x00\x10\x00")), True)
    assert probe.security_transition_observed is True
    assert _result(path)["link_context"]["smp_opcodes_observed"] == [0x01]
    assert hw.transmitted == []


def test_early_smp_signal_terminates_without_gatt_map(
        tmp_path, clean_globals, mock_hw):
    clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
    result_path = tmp_path / "early.nordic_dfu_probe.json"
    probe = dfu.NordicDfuAccessProbe(result_path, tmp_path / "early.pcap")
    with pytest.raises(SystemExit):
        probe.observe_smp(0x01)
    assert _result(result_path)["status"] == "not_tested_security_transition"
    assert mock_hw.transmitted == [(3, b"\x02\x13")]


def test_cccd_cannot_be_attributed_past_packet_value(ready_probe):
    _, _, g, _ = ready_probe
    g.received_handles[0x0013] = dfu.PACKET_UUID_LE
    g.received_handles[0x0014] = b"\x02\x29"
    cccd, candidates = dfu.NordicDfuAccessProbe._find_control_cccd(
        0x0010, 0x001F, 0x0012, 0x0013)
    assert cccd is None
    assert candidates == []


def test_gatt_dispatcher_preempts_value_reads(ready_probe, make_dpkt):
    _, _, _, hw = ready_probe
    stateful_GATT_getter(2, make_dpkt(body=b"\x02\x00"))
    assert hw.transmitted == [(2, b"\x04\x00\x04\x00\x12\x12\x00\x03")]
