########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for Scripts/BG/BG_Helper_SMP.py — Security Manager Protocol
pairing trigger. BG sends a single SMP_Pairing_Request once GATT enumeration
is done, just to capture the Peripheral's pairing-capability Pairing_Response
(IO Capabilities, AuthReq, Max Encryption Key Size, etc.) without actually
encrypting the link. Falls back from legacy → Secure Connections on
Pairing_Failed with reasons other than 0x05 (Pairing Not Supported)."""

import pytest

from BG_Helper_SMP import (
    handle_SMP_Pairing,
    opcode_SMP_Pairing_Failed,
    opcode_SMP_Pairing_Req,
    opcode_SMP_Pairing_Rsp,
    pairing_failure_reason_Pairing_Not_Supported,
    send_SMP_Pairing_Request,
)


# ---------------------------------------------------------------------------
# Outgoing SMP Pairing Request bytes
# ---------------------------------------------------------------------------
class TestSendSMPPairingRequest:
    def test_payload_layout_matches_BT_spec_table_3_3(self, mock_hw):
        # The on-wire bytes for an SMP packet over L2CAP look like:
        #   L2CAP length (2)  | L2CAP CID (2) | SMP opcode (1) | params (6)
        # Inside BG_Helper_SMP.send_SMP_Pairing_Request the leading 4 bytes
        # are the L2CAP header for a 7-byte SMP payload on CID 0x0006.
        send_SMP_Pairing_Request(
            io_cap=0x03,        # NoInputNoOutput
            oob_data=0x00,      # OOB Auth Data Not Present
            auth_req=0x00,      # No Bonding, no MITM, no SC
            max_key_size=0x10,  # 16 bytes
            init_key_dist=0x00,
            resp_key_dist=0x00,
        )

        llid, body = mock_hw.transmitted[0]
        assert llid == 2  # L2CAP w/o fragmentation
        assert body == bytes([
            0x07, 0x00,         # L2CAP length = 7
            0x06, 0x00,         # L2CAP CID = SMP (0x0006)
            opcode_SMP_Pairing_Req,
            0x03,               # IO capability
            0x00,               # OOB
            0x00,               # AuthReq
            0x10,               # Max key size
            0x00,               # Initiator key dist
            0x00,               # Responder key dist
        ])

    def test_secure_connections_authreq_bit_8_and_MITM_bit_4(self, mock_hw):
        # auth_req = 0x0C → SC | MITM, used in the legacy-→-SC fallback path.
        send_SMP_Pairing_Request(0x03, 0x00, 0x0C, 0x10, 0x00, 0x00)
        body = mock_hw.transmitted[0][1]
        # auth_req byte sits at offset 4+1+1+1 = 7.
        assert body[7] == 0x0C


# ---------------------------------------------------------------------------
# handle_SMP_Pairing — gating on all_handles_read
# ---------------------------------------------------------------------------
class TestHandleSMPGating:
    def test_skipped_when_gatt_enumeration_not_complete(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.all_handles_read = False
        handle_SMP_Pairing(0, make_dpkt(body=b""))
        assert mock_hw.transmitted == []
        assert clean_globals.smp_legacy_pairing_req_sent is False

    def test_sends_initial_request_once_gatt_done(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.all_handles_read = True
        handle_SMP_Pairing(0, make_dpkt(body=b""))
        assert clean_globals.smp_legacy_pairing_req_sent is True
        assert clean_globals.smp_pairing_request_attempt_count == 1
        # The request bytes should start with the SMP opcode at L2CAP offset 4.
        body = mock_hw.transmitted[0][1]
        assert body[4] == opcode_SMP_Pairing_Req


# ---------------------------------------------------------------------------
# Incoming Pairing Response handling
# ---------------------------------------------------------------------------
class TestSMPPairingResponse:
    def _build_pairing_rsp(self, io_cap=0x03, oob=0x00, auth_req=0x00,
                            max_key_size=0x10, init_key_dist=0x00,
                            resp_key_dist=0x00):
        # Body layout matches the BG_Helper_SMP unpack at offset 7..13:
        #   header(0x02) | ll_len | l2cap_len(2) | cid(2=SMP) | opcode | 6 params
        payload = bytes([opcode_SMP_Pairing_Rsp, io_cap, oob, auth_req,
                          max_key_size, init_key_dist, resp_key_dist])
        l2cap_len = len(payload)
        body = bytes([
            0x02, 0,                          # ll header + len (fixed up below)
            l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
            0x06, 0x00,                       # SMP CID
        ]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        assert len(body) == 13
        return body

    def test_pairing_rsp_marks_legacy_phase_complete(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.all_handles_read = True
        clean_globals.smp_legacy_pairing_req_sent = True
        clean_globals.smp_SC_pairing_req_sent = False

        body = self._build_pairing_rsp(auth_req=0x00)
        handle_SMP_Pairing(len(body), make_dpkt(body=body))
        assert clean_globals.smp_legacy_pairing_rsp_recv is True

    def test_pairing_rsp_after_SC_request_marks_SC_complete(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.all_handles_read = True
        clean_globals.smp_legacy_pairing_req_sent = True
        clean_globals.smp_SC_pairing_req_sent = True

        body = self._build_pairing_rsp(auth_req=0x0C)
        handle_SMP_Pairing(len(body), make_dpkt(body=body))
        assert clean_globals.smp_SC_pairing_rsp_recv is True


# ---------------------------------------------------------------------------
# Incoming Pairing Failed handling
# ---------------------------------------------------------------------------
class TestSMPPairingFailed:
    def _build_pairing_failed(self, reason):
        payload = bytes([opcode_SMP_Pairing_Failed, reason])
        l2cap_len = len(payload)
        body = bytes([
            0x02, 0,
            l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
            0x06, 0x00,
        ]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        assert len(body) == 8
        return body

    def test_pairing_not_supported_marks_phase_complete_no_fallback(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.all_handles_read = True
        clean_globals.smp_legacy_pairing_req_sent = True

        body = self._build_pairing_failed(pairing_failure_reason_Pairing_Not_Supported)
        handle_SMP_Pairing(len(body), make_dpkt(body=body))

        assert clean_globals.smp_legacy_pairing_rsp_recv is True
        # No SC fallback should have been triggered for "Not Supported".
        assert clean_globals.smp_SC_pairing_req_sent is False

    def test_other_failure_triggers_secure_connections_fallback(
            self, clean_globals, mock_hw, make_dpkt, monkeypatch):
        import BG_Helper_SMP
        clean_globals.all_handles_read = True
        clean_globals.smp_legacy_pairing_req_sent = True
        clean_globals.smp_SC_pairing_req_sent = False
        # Pin time so the 1-second retry path doesn't fire; we only want the
        # SC-fallback packet in this test.
        monkeypatch.setattr(BG_Helper_SMP.time, "time_ns", lambda: 1_000_000)
        clean_globals.smp_legacy_pairing_req_sent_time = 999_999

        # 0x03 = Authentication Requirements (e.g. SC required but legacy attempted).
        body = self._build_pairing_failed(reason=0x03)
        before = len(mock_hw.transmitted)
        handle_SMP_Pairing(len(body), make_dpkt(body=body))

        assert clean_globals.smp_SC_pairing_req_sent is True
        # Exactly one new outbound packet: the SC-mode Pairing Request.
        assert len(mock_hw.transmitted) == before + 1
        sent_body = mock_hw.transmitted[before][1]
        # SMP opcode sits at offset 4 (after the 4-byte L2CAP header).
        assert sent_body[4] == opcode_SMP_Pairing_Req
        # auth_req sits at offset 4 (SMP opcode) + 1 (io_cap) + 1 (oob) + 1.
        assert sent_body[7] == 0x0C  # SC | MITM


# ---------------------------------------------------------------------------
# Retry behavior — bounded number of attempts
# ---------------------------------------------------------------------------
class TestSMPPairingRetryCap:
    def test_after_5_attempts_gives_up_and_marks_rsp_received(
            self, clean_globals, mock_hw, make_dpkt, monkeypatch):
        # Advance time on every reading of time.time_ns() to exceed the 1s
        # retry threshold; record attempts climbing to the 5-attempt cap.
        import BG_Helper_SMP
        clean_globals.all_handles_read = True
        clean_globals.smp_legacy_pairing_req_sent = True
        clean_globals.smp_legacy_pairing_rsp_recv = False
        clean_globals.smp_pairing_request_attempt_count = 5  # one more attempt should trip the cap
        clean_globals.smp_legacy_pairing_req_sent_time = 0

        # Make time.time_ns() always look "more than 1 second" later.
        monkeypatch.setattr(BG_Helper_SMP.time, "time_ns",
                            lambda: 2_000_000_000)

        handle_SMP_Pairing(0, make_dpkt(body=b""))

        assert clean_globals.smp_pairing_request_attempt_count == 6
        assert clean_globals.smp_legacy_pairing_rsp_recv is True
