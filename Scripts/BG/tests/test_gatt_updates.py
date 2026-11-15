"""CCCD planning and serialized ATT writes before BG's SMP phase."""

from types import SimpleNamespace

import pytest

import BG_Helper_ATT as att
import BG_Helper_GATT as gatt


def packet(opcode, payload=b''):
    att_pdu = bytes([opcode]) + payload
    return SimpleNamespace(body=b'\x02' + bytes([len(att_pdu) + 4]) +
                           len(att_pdu).to_bytes(2, 'little') + b'\x04\x00' + att_pdu)


def test_write_request_encodes_cccd_bits(monkeypatch):
    sent = []
    monkeypatch.setattr(att, 'write_outbound_pkt', lambda llid, body: sent.append((llid, body)))
    att.send_ATT_WRITE_REQ(0x0013, b'\x03\x00')
    assert sent == [(2, b'\x05\x00\x04\x00\x12\x13\x00\x03\x00')]


def test_indication_confirmation_and_binary_capture(monkeypatch, clean_globals):
    sent = []
    monkeypatch.setattr(gatt, 'send_ATT_HANDLE_VALUE_CFM', lambda: sent.append('confirm'))
    notify = packet(0x1b, b'\x12\x00Hi\x00')
    indicate = packet(0x1d, b'\x13\x00\xff')
    assert gatt.incoming_gatt_update(len(notify.body), notify)
    assert gatt.incoming_gatt_update(len(indicate.body), indicate)
    assert clean_globals.gatt_updates == [(0x1b, 0x12, b'Hi\x00'), (0x1d, 0x13, b'\xff')]
    assert sent == ['confirm']


def test_plan_stays_within_each_characteristic(clean_globals):
    handles = {
        1: b'\x00\x28', 2: b'\x03\x28', 3: b'\x00\x2a', 4: b'\x02\x29',
        5: b'\x03\x28', 6: b'\x01\x2a', 7: b'\x02\x29',
        8: b'\x03\x28', 9: b'\x02\x2a', 10: b'\x02\x29',
        11: b'\x03\x28', 12: b'\x03\x2a', 13: b'\x00\x28', 14: b'\x02\x29',
    }
    declarations = {
        2: b'\x10\x03\x00\x00\x2a',
        5: b'\x20\x06\x00\x01\x2a',
        8: b'\x30\x09\x00\x02\x2a',
        11: b'\x10\x0c\x00\x03\x2a',
    }
    assert gatt.plan_gatt_subscriptions(handles, declarations) == [
        (4, 1, 3), (7, 2, 6), (10, 3, 9)]


def test_serialized_writes_error_and_observation(monkeypatch, clean_globals):
    state = clean_globals
    state.all_handles_read = True
    state.gatt_subscription_plan = [(4, 1, 3), (7, 2, 6)]
    state.gatt_notification_window_ns = 5_000_000_000
    now = [1_000_000_000]
    sent = []
    monkeypatch.setattr(gatt.time, 'time_ns', lambda: now[0])
    monkeypatch.setattr(gatt, 'send_ATT_WRITE_REQ', lambda h, value: sent.append((h, value)))

    gatt.outgoing_gatt_subscriptions()
    gatt.outgoing_gatt_subscriptions()
    assert sent == [(4, b'\x01\x00')]
    assert gatt.incoming_gatt_subscription_response(7, packet(0x13))
    gatt.outgoing_gatt_subscriptions()
    assert sent == [(4, b'\x01\x00'), (7, b'\x02\x00')]
    assert not gatt.incoming_gatt_subscription_response(11, packet(0x01, b'\x12\x08\x00\x05'))
    assert gatt.incoming_gatt_subscription_response(11, packet(0x01, b'\x12\x07\x00\x05'))
    gatt.outgoing_gatt_subscriptions()
    assert not state.gatt_subscriptions_done
    now[0] += 5_000_000_001
    gatt.outgoing_gatt_subscriptions()
    assert state.gatt_subscriptions_done


def test_timeout_closes_without_second_write(monkeypatch, clean_globals):
    state = clean_globals
    state.all_handles_read = True
    state.gatt_subscription_plan = [(4, 1, 3), (7, 2, 6)]
    now = [1_000_000_000]
    sent = []
    monkeypatch.setattr(gatt.time, 'time_ns', lambda: now[0])
    monkeypatch.setattr(gatt, 'send_ATT_WRITE_REQ', lambda h, value: sent.append(h))
    monkeypatch.setattr(gatt, 'print_and_exit', lambda: (_ for _ in ()).throw(RuntimeError('closed')))
    gatt.outgoing_gatt_subscriptions()
    now[0] += 2_000_000_001
    with pytest.raises(RuntimeError, match='closed'):
        gatt.outgoing_gatt_subscriptions()
    assert sent == [4]
