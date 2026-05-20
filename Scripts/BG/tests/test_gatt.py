########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for the GATT enumeration pipeline implemented across
Scripts/BG/BG_Helper_ATT.py and Scripts/BG/BG_Helper_GATT.py — covering:

 * ATT_EXCHANGE_MTU_REQ/RSP negotiation, both Central- and Peripheral-initiated
 * ATT_READ_BY_GROUP_TYPE_REQ/RSP for Primary (0x2800) and Secondary (0x2801)
   service discovery, including UUID16 and UUID128 entry-length branches
 * ATT_FIND_INFORMATION_REQ/RSP handle/UUID enumeration
 * ATT_READ_REQ/RSP value reads, with success and error-response paths
 * Error-response handling — Attribute Not Found / Insufficient Auth / etc.
 * The `get_next_handle_to_att_read` helper that skips 0x2800/0x2801 entries

The packet bodies replicate what BG sees on the wire in the CA:FE pcap."""

import pytest

from BG_Helper_ATT import (
    errorcode_02_ATT_Read_Not_Permitted,
    errorcode_05_ATT_Insufficient_Authentication,
    errorcode_0A_ATT_Attribute_Not_Found,
    errorcode_10_ATT_Unsupported_Group_Type,
    get_next_handle_to_att_read,
    helper_skip_service_handles,
    incoming_ATT_EXCHANGE_MTUs,
    is_packet_ATT_type,
    manage_peripheral_info_requests,
    opcode_ATT_ERROR_RSP,
    opcode_ATT_EXCHANGE_MTU_REQ,
    opcode_ATT_EXCHANGE_MTU_RSP,
    opcode_ATT_FIND_INFORMATION_REQ,
    opcode_ATT_FIND_INFORMATION_RSP,
    opcode_ATT_READ_BY_GROUP_TYPE_REQ,
    opcode_ATT_READ_BY_GROUP_TYPE_RSP,
    opcode_ATT_READ_BY_TYPE_REQ,
    opcode_ATT_READ_BY_TYPE_RSP,
    opcode_ATT_READ_REQ,
    opcode_ATT_READ_RSP,
    outgoing_ATT_EXCHANGE_MTUs,
    process_ATT_FIND_INFORMATION_RSP,
    send_ATT_EXCHANGE_MTU_REQ,
    send_ATT_FIND_INFORMATION_REQ,
    send_ATT_READ_BY_GROUP_TYPE_REQ,
    send_ATT_READ_BY_TYPE_REQ,
    send_ATT_READ_REQ,
    store_handle_info,
)
from BG_Helper_GATT import (
    incoming_read_all_handles,
    incoming_service_discovery,
    outgoing_read_all_handles,
    outgoing_service_discovery,
    process_ATT_ERROR_RSP_for_ATT_READ_BY_GROUP_TYPE_REQ,
    process_ATT_ERROR_RSP_for_ATT_READ_BY_TYPE_REQ,
    process_ATT_ERROR_RSP_for_ATT_READ_RSP,
    process_ATT_READ_BY_GROUP_TYPE_RSP,
    process_ATT_READ_BY_TYPE_RSP,
    process_ATT_READ_RSP,
)


# ---------------------------------------------------------------------------
# is_packet_ATT_type — common gating used by every incoming-ATT path
# ---------------------------------------------------------------------------
class TestIsPacketATTType:
    def _build_att_pdu(self, opcode, cid=0x0004, header=0x02, extra=b""):
        # header(=0x02 for LLID=0b10 "start of L2CAP") | ll_len |
        # l2cap_len (2) | cid (2) | att opcode | extra
        l2cap_payload = bytes([opcode]) + extra
        l2cap_len = len(l2cap_payload)
        body = bytes([
            header, 0,
            l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
            cid & 0xFF, (cid >> 8) & 0xFF,
        ]) + l2cap_payload
        body = bytes([header, len(body) - 2]) + body[2:]
        return body

    def test_matches_correct_att_opcode(self, make_dpkt):
        body = self._build_att_pdu(opcode_ATT_READ_RSP, extra=b"\x42")
        matched, *_ = is_packet_ATT_type(opcode_ATT_READ_RSP, make_dpkt(body=body))
        assert matched is True

    def test_rejects_wrong_cid(self, make_dpkt):
        body = self._build_att_pdu(opcode_ATT_READ_RSP, cid=0x0006)  # SMP, not ATT
        matched, *_ = is_packet_ATT_type(opcode_ATT_READ_RSP, make_dpkt(body=body))
        assert matched is False

    def test_rejects_wrong_opcode(self, make_dpkt):
        body = self._build_att_pdu(opcode_ATT_READ_RSP)
        matched, *_ = is_packet_ATT_type(opcode_ATT_FIND_INFORMATION_RSP, make_dpkt(body=body))
        assert matched is False

    def test_rejects_fragmentation_header_bit(self, make_dpkt):
        # LLID = 0b01 (continuation) — header bit ANDed with 0b10 = 0.
        body = self._build_att_pdu(opcode_ATT_READ_RSP, header=0x01)
        matched, *_ = is_packet_ATT_type(opcode_ATT_READ_RSP, make_dpkt(body=body))
        assert matched is False


# ---------------------------------------------------------------------------
# Outgoing senders — pin payload bytes for the 5 ATT REQ types BG uses
# ---------------------------------------------------------------------------
class TestOutgoingATTSendBytes:
    def test_EXCHANGE_MTU_REQ(self, mock_hw):
        send_ATT_EXCHANGE_MTU_REQ(client_rx_mtu=247)
        body = mock_hw.transmitted[0][1]
        assert body == bytes([
            0x03, 0x00,            # L2CAP length = 3
            0x04, 0x00,            # CID = ATT
            opcode_ATT_EXCHANGE_MTU_REQ,
            0xF7, 0x00,            # 247 little-endian
        ])

    def test_READ_BY_GROUP_TYPE_REQ_pins_start_handle_and_uuid(self, mock_hw):
        send_ATT_READ_BY_GROUP_TYPE_REQ(begin_handle=0x0001, group_type=0x2800)
        body = mock_hw.transmitted[0][1]
        assert body == bytes([
            0x07, 0x00,            # L2CAP length = 7
            0x04, 0x00,            # CID = ATT
            opcode_ATT_READ_BY_GROUP_TYPE_REQ,
            0x01, 0x00,            # begin handle
            0xFF, 0xFF,            # end handle (BG always uses 0xFFFF)
            0x00, 0x28,            # group type 0x2800 (Primary Service)
        ])

    def test_READ_BY_TYPE_REQ_for_characteristic_descriptors(self, mock_hw):
        send_ATT_READ_BY_TYPE_REQ(begin_handle=0x0010, end_handle=0x001F, type=0x2803)
        body = mock_hw.transmitted[0][1]
        assert body[4] == opcode_ATT_READ_BY_TYPE_REQ
        # Type UUID at end of payload.
        assert body[9:11] == bytes([0x03, 0x28])

    def test_FIND_INFORMATION_REQ(self, mock_hw):
        send_ATT_FIND_INFORMATION_REQ(begin_handle=0x0042)
        body = mock_hw.transmitted[0][1]
        assert body == bytes([
            0x05, 0x00,
            0x04, 0x00,
            opcode_ATT_FIND_INFORMATION_REQ,
            0x42, 0x00,
            0xFF, 0xFF,
        ])

    def test_READ_REQ_for_a_single_handle(self, mock_hw):
        send_ATT_READ_REQ(begin_handle=0x000B)
        body = mock_hw.transmitted[0][1]
        assert body == bytes([
            0x03, 0x00,
            0x04, 0x00,
            opcode_ATT_READ_REQ,
            0x0B, 0x00,
        ])


# ---------------------------------------------------------------------------
# ATT_EXCHANGE_MTU — both directions
# ---------------------------------------------------------------------------
class TestATTExchangeMTU:
    def _build_mtu_pdu(self, opcode, mtu):
        payload = bytes([opcode]) + mtu.to_bytes(2, "little")
        l2cap_len = len(payload)
        body = bytes([
            0x02, 0,
            l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
            0x04, 0x00,
        ]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_incoming_MTU_RSP_sets_mtu_and_negotiated(
            self, clean_globals, mock_hw, make_dpkt):
        body = self._build_mtu_pdu(opcode_ATT_EXCHANGE_MTU_RSP, mtu=100)
        incoming_ATT_EXCHANGE_MTUs(len(body), make_dpkt(body=body))

        assert clean_globals.att_mtu == 100
        assert clean_globals.att_MTU_negotiated is True
        assert clean_globals.att_exchange_MTU_rsp_recv is True

    def test_incoming_MTU_RSP_smaller_than_existing_does_not_decrease(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.att_mtu = 200
        body = self._build_mtu_pdu(opcode_ATT_EXCHANGE_MTU_RSP, mtu=50)
        incoming_ATT_EXCHANGE_MTUs(len(body), make_dpkt(body=body))
        # The pre-seeded 200 should NOT be replaced by the smaller 50.
        assert clean_globals.att_mtu == 200

    def test_incoming_MTU_RSP_below_minimum_23_ignored_for_value(
            self, clean_globals, mock_hw, make_dpkt):
        # Spec minimum is 23; values below that are clamped (ignored).
        body = self._build_mtu_pdu(opcode_ATT_EXCHANGE_MTU_RSP, mtu=10)
        incoming_ATT_EXCHANGE_MTUs(len(body), make_dpkt(body=body))
        # MTU value stays at the BG default of 23.
        assert clean_globals.att_mtu == 23
        # But negotiation IS marked done so we move on.
        assert clean_globals.att_MTU_negotiated is True

    def test_incoming_MTU_REQ_replies_only_after_LL_LENGTH_negotiated(
            self, clean_globals, mock_hw, make_dpkt):
        # Frame 7 in the CA:FE pcap: Peripheral sends MTU REQ before LL Data
        # Length Extension is finalized. BG queues it and replies later.
        body = self._build_mtu_pdu(opcode_ATT_EXCHANGE_MTU_REQ, mtu=247)

        # Without LL length negotiated, the request is queued, not answered.
        clean_globals.current_ll_ctrl_state.ll_length_negotiated = False
        incoming_ATT_EXCHANGE_MTUs(len(body), make_dpkt(body=body))
        assert clean_globals.att_exchange_MTU_req_recv is True
        assert clean_globals.queued_client_rx_mtu_ACID == 247
        assert mock_hw.transmitted == []

    def test_incoming_MTU_REQ_replies_immediately_when_LL_LENGTH_negotiated(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.current_ll_ctrl_state.ll_length_negotiated = True
        clean_globals.current_ll_ctrl_state.ll_length_max_tx_octet = 100
        body = self._build_mtu_pdu(opcode_ATT_EXCHANGE_MTU_REQ, mtu=247)
        incoming_ATT_EXCHANGE_MTUs(len(body), make_dpkt(body=body))
        # MTU is clamped to min(ll_length_max_tx_octet - 4, 247) = 96.
        assert clean_globals.att_mtu == 96
        assert clean_globals.att_MTU_negotiated is True
        assert clean_globals.att_exchange_MTU_rsp_sent is True
        # Should have sent ATT_EXCHANGE_MTU_RSP.
        assert mock_hw.transmitted[0][1][4] == opcode_ATT_EXCHANGE_MTU_RSP

    def test_outgoing_MTU_REQ_sent_when_no_REQ_seen_from_peripheral(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.current_ll_ctrl_state.ll_length_negotiated = True
        clean_globals.current_ll_ctrl_state.ll_length_max_tx_octet = 100
        clean_globals.att_exchange_MTU_req_recv = False
        clean_globals.att_exchange_MTU_req_sent = False
        outgoing_ATT_EXCHANGE_MTUs(0, make_dpkt(body=b""))
        assert clean_globals.att_exchange_MTU_req_sent is True
        # MTU = min(100-4, 247) = 96.
        assert clean_globals.att_mtu == 96


# ---------------------------------------------------------------------------
# ATT_READ_BY_GROUP_TYPE_RSP — primary/secondary service enumeration
# ---------------------------------------------------------------------------
class TestATTReadByGroupTypeRsp:
    def _build_group_type_rsp_uuid16(self, entries):
        """entries: list of (begin, end, uuid16) tuples."""
        entry_len = 6
        body_payload = bytes([opcode_ATT_READ_BY_GROUP_TYPE_RSP, entry_len])
        for begin, end, uuid16 in entries:
            body_payload += begin.to_bytes(2, "little") + end.to_bytes(2, "little") + uuid16.to_bytes(2, "little")
        l2cap_len = len(body_payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + body_payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def _build_group_type_rsp_uuid128(self, entries):
        """entries: list of (begin, end, uuid128_bytes) — uuid128_bytes is 16 bytes LE."""
        entry_len = 20
        body_payload = bytes([opcode_ATT_READ_BY_GROUP_TYPE_RSP, entry_len])
        for begin, end, uuid in entries:
            body_payload += begin.to_bytes(2, "little") + end.to_bytes(2, "little") + bytes(uuid)
        l2cap_len = len(body_payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + body_payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_records_uuid16_primary_services(
            self, clean_globals, mock_hw, make_dpkt):
        # The four entries below mirror frame 34 of the CA:FE pcap: GATT,
        # GAP, Battery, Device Information.
        clean_globals.last_requested_service_type = "primary"
        entries = [
            (0x0001, 0x0008, 0x1801),  # GATT
            (0x0009, 0x000F, 0x1800),  # GAP
            (0x0010, 0x0014, 0x180F),  # Battery
            (0x0015, 0x0019, 0x180A),  # Device Information
        ]
        body = self._build_group_type_rsp_uuid16(entries)

        process_ATT_READ_BY_GROUP_TYPE_RSP(len(body), make_dpkt(body=body))

        assert clean_globals.primary_service_handle_ranges_dict[0x0001] == (0x0008, 0x1801, 2)
        assert clean_globals.primary_service_handle_ranges_dict[0x0009] == (0x000F, 0x1800, 2)
        assert clean_globals.primary_service_handle_ranges_dict[0x0010] == (0x0014, 0x180F, 2)
        assert clean_globals.primary_service_handle_ranges_dict[0x0015] == (0x0019, 0x180A, 2)
        # final_handle should be the last entry's end_handle.
        assert clean_globals.primary_service_final_handle == 0x0019

    def test_records_uuid128_primary_service(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.last_requested_service_type = "primary"
        uuid_le = b"\xaa\xa4\x9f\xf0\x21\x6b\x63\x6f\x6c\x6d\x65\x48\x01\x00\x4d\x44"
        body = self._build_group_type_rsp_uuid128([(0x001b, 0x002e, uuid_le)])

        process_ATT_READ_BY_GROUP_TYPE_RSP(len(body), make_dpkt(body=body))

        end_handle, uuid_bytes, uuid_size = \
            clean_globals.primary_service_handle_ranges_dict[0x001b]
        assert end_handle == 0x002e
        assert uuid_bytes == uuid_le
        assert uuid_size == 16

    def test_secondary_service_response_records_in_secondary_dict(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.last_requested_service_type = "secondary"
        body = self._build_group_type_rsp_uuid16([(0x0030, 0x0035, 0x1234)])
        process_ATT_READ_BY_GROUP_TYPE_RSP(len(body), make_dpkt(body=body))
        assert 0x0030 in clean_globals.secondary_service_handle_ranges_dict
        assert clean_globals.secondary_service_final_handle == 0x0035


# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------
class TestATTErrorResponses:
    def _build_error_rsp(self, req_opcode_in_error, handle_in_error, error_code):
        # Body: header | ll_len | l2cap_len=5 | cid=0x0004 | opcode=0x01 |
        #       req_opcode | handle(2) | error_code
        payload = bytes([
            opcode_ATT_ERROR_RSP, req_opcode_in_error,
            handle_in_error & 0xFF, (handle_in_error >> 8) & 0xFF,
            error_code,
        ])
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_attribute_not_found_on_secondary_service_marks_phase_done(
            self, clean_globals, mock_hw, make_dpkt):
        # Frame 50 of the CA:FE pcap: Peripheral has no secondary services.
        clean_globals.last_requested_service_type = "secondary"
        clean_globals.secondary_service_last_reqested_handle = 0x0001
        body = self._build_error_rsp(opcode_ATT_READ_BY_GROUP_TYPE_REQ,
                                       0x0001, errorcode_0A_ATT_Attribute_Not_Found)

        result = process_ATT_ERROR_RSP_for_ATT_READ_BY_GROUP_TYPE_REQ(
            len(body), make_dpkt(body=body))
        assert result is True
        assert clean_globals.secondary_services_all_recv is True

    def test_unsupported_group_type_also_marks_phase_done(
            self, clean_globals, mock_hw, make_dpkt):
        # Meta Quest behavior — returns 0x10 instead of 0x0A.
        clean_globals.last_requested_service_type = "primary"
        clean_globals.primary_service_last_reqested_handle = 0x0001
        body = self._build_error_rsp(opcode_ATT_READ_BY_GROUP_TYPE_REQ,
                                       0x0001, errorcode_10_ATT_Unsupported_Group_Type)
        result = process_ATT_ERROR_RSP_for_ATT_READ_BY_GROUP_TYPE_REQ(
            len(body), make_dpkt(body=body))
        assert result is True
        assert clean_globals.primary_services_all_recv is True

    def test_read_not_permitted_recorded_in_error_dict(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.handle_read_last_sent_handle = 0x0003
        body = self._build_error_rsp(opcode_ATT_READ_REQ,
                                       0x0003, errorcode_02_ATT_Read_Not_Permitted)
        # Mark prerequisites so the function executes.
        clean_globals.handle_read_req_sent_time = 12345
        clean_globals.all_handles_read = False
        # Avoid the send_next_ATT_READ_REQ_if_applicable side effect's
        # globals.final_handle dependence.
        clean_globals.final_handle = 1

        process_ATT_ERROR_RSP_for_ATT_READ_RSP(len(body), make_dpkt(body=body))
        assert clean_globals.handles_with_error_rsp[0x0003] == \
            errorcode_02_ATT_Read_Not_Permitted

    def test_insufficient_authentication_recorded(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.handle_read_last_sent_handle = 0x002A
        clean_globals.handle_read_req_sent_time = 12345
        clean_globals.final_handle = 1
        body = self._build_error_rsp(opcode_ATT_READ_REQ,
                                       0x002A, errorcode_05_ATT_Insufficient_Authentication)
        process_ATT_ERROR_RSP_for_ATT_READ_RSP(len(body), make_dpkt(body=body))
        assert clean_globals.handles_with_error_rsp[0x002A] == \
            errorcode_05_ATT_Insufficient_Authentication


# ---------------------------------------------------------------------------
# ATT_FIND_INFORMATION_RSP — handle/UUID enumeration
# ---------------------------------------------------------------------------
class TestStoreHandleInfo:
    def _build_find_info_rsp_uuid16(self, entries):
        """entries: list of (handle, uuid16). Format byte = 1 for UUID16."""
        payload = bytes([opcode_ATT_FIND_INFORMATION_RSP, 0x01])
        for handle, uuid16 in entries:
            payload += handle.to_bytes(2, "little") + uuid16.to_bytes(2, "little")
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def _build_find_info_rsp_uuid128(self, entries):
        """entries: list of (handle, uuid128_bytes). Format byte = 2 for UUID128."""
        payload = bytes([opcode_ATT_FIND_INFORMATION_RSP, 0x02])
        for handle, uuid in entries:
            payload += handle.to_bytes(2, "little") + bytes(uuid)
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_stores_uuid16_handle_value_pairs(self, clean_globals, make_dpkt):
        # Frame 54 of the CA:FE pcap: 8 UUID16 handle/uuid pairs starting
        # with the GATT primary service.
        entries = [
            (0x0001, 0x2800),  # Primary Service
            (0x0002, 0x2803),  # Characteristic
            (0x0003, 0x2A05),  # Service Changed
            (0x0004, 0x2902),  # CCCD
        ]
        body = self._build_find_info_rsp_uuid16(entries)
        final_handle = store_handle_info(make_dpkt(body=body))

        assert final_handle == 0x0004
        # Verify each handle now has its UUID16 (stored as 2 LE bytes).
        assert clean_globals.received_handles[0x0001] == bytes([0x00, 0x28])
        assert clean_globals.received_handles[0x0003] == bytes([0x05, 0x2A])
        assert clean_globals.received_handles[0x0004] == bytes([0x02, 0x29])

    def test_stores_uuid128_handle_value_pairs(self, clean_globals, make_dpkt):
        # Frame 69 / 75 / 82 of the CA:FE pcap: vendor UUID128s.
        uuid_le = b"\xaa\xa4\x9f\xf0\x21\x6b\x63\x6f\x6c\x6d\x65\x48\x10\x00\x4d\x44"
        body = self._build_find_info_rsp_uuid128([(0x001C, uuid_le)])
        final_handle = store_handle_info(make_dpkt(body=body))
        assert final_handle == 0x001C
        assert clean_globals.received_handles[0x001C] == uuid_le

    def test_returns_negative_for_short_body(self, clean_globals, make_dpkt):
        assert store_handle_info(make_dpkt(body=b"\x02\x05\x00\x00")) == -1


# ---------------------------------------------------------------------------
# ATT_READ_RSP — value reads and error responses
# ---------------------------------------------------------------------------
class TestATTReadRsp:
    def _build_read_rsp(self, value_bytes):
        payload = bytes([opcode_ATT_READ_RSP]) + bytes(value_bytes)
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_read_rsp_stores_value_for_last_sent_handle(
            self, clean_globals, make_dpkt):
        clean_globals.handle_read_last_sent_handle = 0x000B
        clean_globals.final_handle = 0
        # "UVP01" from frame 173 of the CA:FE pcap (Device Name).
        body = self._build_read_rsp(b"UVP01")

        process_ATT_READ_RSP(len(body), make_dpkt(body=body))
        assert clean_globals.all_handles_received_values[0x000B] == b"UVP01"

    def test_empty_read_rsp_records_no_data_sentinel(
            self, clean_globals, make_dpkt):
        # AirPods-style malformed response with just the opcode, no payload.
        clean_globals.handle_read_last_sent_handle = 0x0042
        clean_globals.final_handle = 0
        body = self._build_read_rsp(b"")
        process_ATT_READ_RSP(len(body), make_dpkt(body=body))
        assert clean_globals.all_handles_received_values[0x0042] == "No data"


# ---------------------------------------------------------------------------
# get_next_handle_to_att_read — skip 0x2800 / 0x2801 service handles
# ---------------------------------------------------------------------------
class TestGetNextHandleToAttRead:
    def test_skips_primary_service_handle(self, clean_globals):
        # received_handles is populated by store_handle_info during enum.
        # Handle 1 is the Primary Service decl (0x2800); handle 2 is the
        # Characteristic decl (0x2803). After reading handle 1, the next
        # readable handle is 2 — but get_next_handle_to_att_read should
        # skip 1's "service" UUID and return 2.
        clean_globals.received_handles = {
            0x0001: bytes([0x00, 0x28]),
            0x0002: bytes([0x03, 0x28]),
            0x0003: bytes([0x05, 0x2A]),
        }
        # After reading "handle 0" (nothing) the next candidate is 1, which
        # is the Primary Service — should skip.
        assert get_next_handle_to_att_read(0) == 0x0002

    def test_skips_consecutive_service_handles(self, clean_globals):
        # Two consecutive Primary Services then a Characteristic.
        clean_globals.received_handles = {
            0x0001: bytes([0x00, 0x28]),
            0x0002: bytes([0x00, 0x28]),
            0x0003: bytes([0x03, 0x28]),
        }
        assert get_next_handle_to_att_read(0) == 0x0003

    def test_skips_secondary_service_handle(self, clean_globals):
        clean_globals.received_handles = {
            0x0010: bytes([0x01, 0x28]),  # Secondary Service
            0x0011: bytes([0x03, 0x28]),  # Characteristic
        }
        assert get_next_handle_to_att_read(0x000F) == 0x0011

    def test_no_higher_handle_returns_negative_and_sets_all_read(
            self, clean_globals):
        clean_globals.received_handles = {0x0005: bytes([0x00, 0x28])}
        assert get_next_handle_to_att_read(0x0005) == -1
        assert clean_globals.all_handles_read is True

    def test_returns_uuid128_handle_unchanged(self, clean_globals):
        clean_globals.received_handles = {
            0x0001: bytes([0x00, 0x28]),
            0x0002: b"\xaa" * 16,
        }
        assert get_next_handle_to_att_read(0x0001) == 0x0002


# ---------------------------------------------------------------------------
# manage_peripheral_info_requests — reject Peripheral-side enumeration
# ---------------------------------------------------------------------------
class TestManagePeripheralInfoRequests:
    def test_rejects_AppleTV_style_outbound_GROUP_TYPE_REQ(
            self, mock_hw, make_dpkt):
        # 13-byte ATT_READ_BY_GROUP_TYPE_REQ from a misbehaving Peripheral.
        payload = bytes([
            opcode_ATT_READ_BY_GROUP_TYPE_REQ,
            0x01, 0x00,            # start handle
            0xFF, 0xFF,            # end handle
            0x00, 0x28,            # group type
        ])
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]

        manage_peripheral_info_requests(len(body), make_dpkt(body=body))

        assert len(mock_hw.transmitted) == 1
        rsp = mock_hw.transmitted[0][1]
        # Should be an ATT_ERROR_RSP for opcode 0x10 with Unlikely Error (0x0E).
        assert rsp[4] == opcode_ATT_ERROR_RSP
        assert rsp[5] == opcode_ATT_READ_BY_GROUP_TYPE_REQ
        assert rsp[8] == 0x0E   # Unlikely Error
