########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for Scripts/BG/BG_Helper_L2CAP.py — BG only deals with the
L2CAP signaling channel (CID 0x0005) to send a rejection for any
L2CAP_CONNECTION_PARAMETER_UPDATE_REQ a Peripheral sends, so it can keep
the connection at the parameters BG opened with."""

import pytest

from BG_Helper_L2CAP import (
    L2CAP_Signaling_CID,
    is_packet_L2CAP_signalling_channel_type,
    opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ,
    opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP,
    send_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ,
    send_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP,
    stateful_incoming_L2CAP_handler,
)


# ---------------------------------------------------------------------------
# Opcode constants pinned
# ---------------------------------------------------------------------------
class TestOpcodeConstants:
    def test_signaling_cid_is_0x0005(self):
        assert L2CAP_Signaling_CID == 0x05

    def test_connection_parameter_update_req_opcode_0x12(self):
        assert opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ == 0x12

    def test_connection_parameter_update_rsp_opcode_0x13(self):
        assert opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP == 0x13


# ---------------------------------------------------------------------------
# Outgoing packet bytes
# ---------------------------------------------------------------------------
class TestSendL2CAPParameterUpdate:
    def test_send_REQ_payload_layout(self, mock_hw):
        send_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(
            identifier=0x42,
            data_length=0x08,
            interval_min=0x000A,
            interval_max=0x0020,
            latency=0x0000,
            timeout=0x0064,
        )
        llid, body = mock_hw.transmitted[0]
        # The helper passes globals.LLID_data (= 2 per globals.py).
        assert llid == 2
        # Body = L2CAP length (2) + CID (2) + opcode(1) + identifier(1) +
        #        data_length(2) + 4×uint16 little-endian.
        info_payload = (
            bytes([opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ, 0x42])
            + bytes([0x08, 0x00])    # data_length=8
            + bytes([0x0A, 0x00])    # interval_min=10
            + bytes([0x20, 0x00])    # interval_max=32
            + bytes([0x00, 0x00])    # latency
            + bytes([0x64, 0x00])    # timeout
        )
        l2cap_len = len(info_payload)
        assert body == bytes([
            l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
            0x05, 0x00,          # CID = signaling
        ]) + info_payload

    def test_send_RSP_rejection_result(self, mock_hw):
        # Default result = 0x0001 = "Connection Parameters rejected".
        send_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(identifier=0x42)
        body = mock_hw.transmitted[0][1]
        assert body[4] == opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP
        assert body[5] == 0x42                    # echoed identifier
        # data_length = 2, then result = 0x0001 LE.
        assert body[6:8] == bytes([0x02, 0x00])
        assert body[8:10] == bytes([0x01, 0x00])  # rejected


# ---------------------------------------------------------------------------
# Inbound classifier
# ---------------------------------------------------------------------------
class TestIsPacketL2CAPSignallingChannelType:
    def _build_signaling_pdu(self, opcode):
        # header(0x02) | ll_len | l2cap_len(2) | cid(0x0005) | l2cap_opcode
        body = bytes([
            0x02, 0,
            0x01, 0x00,            # L2CAP length = 1 (just the opcode for this check)
            0x05, 0x00,            # CID = signaling
            opcode,
        ])
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_matches_correct_cid_and_opcode(self, make_dpkt):
        body = self._build_signaling_pdu(opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ)
        dpkt = make_dpkt(body=body)
        assert is_packet_L2CAP_signalling_channel_type(
            len(body), dpkt, opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ
        ) is True

    def test_rejects_wrong_cid(self, make_dpkt):
        # CID 0x0004 = ATT, not signaling.
        body = bytes([
            0x02, 0x05, 0x01, 0x00, 0x04, 0x00,
            opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ,
        ])
        body = bytes([0x02, len(body) - 2]) + body[2:]
        assert is_packet_L2CAP_signalling_channel_type(
            len(body), make_dpkt(body=body), opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ
        ) is False

    def test_rejects_wrong_opcode(self, make_dpkt):
        body = self._build_signaling_pdu(0xFF)
        assert is_packet_L2CAP_signalling_channel_type(
            len(body), make_dpkt(body=body), opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ
        ) is False

    def test_rejects_short_body(self, make_dpkt):
        assert is_packet_L2CAP_signalling_channel_type(
            5, make_dpkt(body=b"\x02\x03\x00\x00\x05"),
            opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ
        ) is False


# ---------------------------------------------------------------------------
# stateful_incoming_L2CAP_handler — rejects update REQ with rejection RSP
# ---------------------------------------------------------------------------
class TestStatefulIncomingHandler:
    def test_REQ_triggers_rejection_RSP_with_matching_identifier(
            self, mock_hw, make_dpkt):
        # Full REQ body with identifier=0x77, data_length=8, params=zeros.
        info_payload = (
            bytes([opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ, 0x77])
            + bytes([0x08, 0x00])
            + bytes([0x06, 0x00, 0x20, 0x00, 0x00, 0x00, 0x64, 0x00])
        )
        l2cap_len = len(info_payload)
        body = bytes([
            0x02, 0,
            l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
            0x05, 0x00,
        ]) + info_payload
        body = bytes([0x02, len(body) - 2]) + body[2:]

        stateful_incoming_L2CAP_handler(len(body), make_dpkt(body=body))

        # Exactly one outbound packet: the rejection RSP.
        assert len(mock_hw.transmitted) == 1
        rsp = mock_hw.transmitted[0][1]
        assert rsp[4] == opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP
        assert rsp[5] == 0x77                    # identifier echo
        assert rsp[8:10] == bytes([0x01, 0x00])  # result = 1 (rejected)

    def test_unrelated_signaling_opcode_ignored(self, mock_hw, make_dpkt):
        # 0x06 = L2CAP_DISCONNECTION_REQ — not what we filter on.
        body = bytes([
            0x02, 0, 0x01, 0x00, 0x05, 0x00, 0x06,
        ])
        body = bytes([0x02, len(body) - 2]) + body[2:]
        stateful_incoming_L2CAP_handler(len(body), make_dpkt(body=body))
        assert mock_hw.transmitted == []
