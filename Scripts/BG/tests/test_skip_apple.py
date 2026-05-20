########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end tests for the -A / skip-apple feature.

BG (and central_app_launcher, which now always passes -A) deliberately
bails out the moment it confirms a target is an Apple device — Apple is
ubiquitous and already well-characterized, so spending a ~20 s enumeration
timeout on yet another iPhone is wasted dongle time. There are THREE
independent detection vectors, each of which calls `exit(0x0A)`:

  1. Advertisement Company ID — Better_Getter.print_packet() →
     apple_advertisement() on an ADV_IND/SCAN_RSP with an MSD whose
     Company ID is 0x004C.
  2. LL_VERSION_IND Company ID — BG_Helper_LL.incoming_LL_VERSION_IND()
     when the peripheral's controller reports company_id 0x004C/0x4C00.
     (Pinned in test_ll_ctrl.py::TestIncomingLLVersionInd.)
  3. GATT Manufacturer Name — BG_Helper_GATT.detect_Apple_by_GATT_Manufacturer
     _Name() sends an ATT_FIND_BY_TYPE_VALUE_REQ for 0x2A29 = "Apple Inc."
     and treats any non-error response as a positive match.

Vector 1 is exercised with REAL Apple advertisements captured off-air
(fixtures/apple_advertisements.pcap); the rationale being that Apple
devices are essentially always in range, so authentic capture data is the
most faithful regression input. 0x0A is the BG exit code reserved for
"skipped an Apple device."

The matching CLI plumbing (-A sets globals.skip_apple) is pinned in
test_cli.py::TestMainFlagToggles::test_skip_apple_flag_sets_global.
"""

import pytest

import Better_Getter as bg
from sniffle.pcap import PcapBleReader

from BG_Helper_GATT import detect_Apple_by_GATT_Manufacturer_Name
from BG_Helper_ATT import (
    opcode_ATT_ERROR_RSP,
    opcode_ATT_FIND_BY_TYPE_VALUE_REQ,
    opcode_ATT_FIND_BY_TYPE_VALUE_RSP,
    send_ATT_FIND_BY_TYPE_VALUE_REQ_0x2A29_Apple,
)


APPLE_SKIP_EXIT_CODE = 0x0A


def _apple_packets(apple_pcap_path):
    """Decode every frame in the real-Apple-advertisement fixture."""
    return list(PcapBleReader(str(apple_pcap_path)))


# ===========================================================================
# Vector 1: Advertisement Company ID — the print_packet() exit path,
# driven by REAL captured Apple advertisements.
# ===========================================================================
class TestAdvertisementVector:
    def test_fixture_decodes_to_apple_adv_ind_frames(self, apple_pcap_path):
        # Sanity-pin the fixture: 6 real ADV_IND frames, every one Apple.
        pkts = _apple_packets(apple_pcap_path)
        assert len(pkts) == 6
        for pkt in pkts:
            assert pkt.pdutype == "ADV_IND"
            assert bg.apple_advertisement(pkt, len(pkt.body)) is True

    def test_print_packet_exits_0x0A_on_real_apple_advertisement(
            self, clean_globals, apple_pcap_path):
        clean_globals.skip_apple = True
        clean_globals.pcwriter = None
        pkt = _apple_packets(apple_pcap_path)[0]

        with pytest.raises(SystemExit) as exc:
            bg.print_packet(pkt, quiet=True)
        assert exc.value.code == APPLE_SKIP_EXIT_CODE

    def test_every_fixture_frame_triggers_skip_exit(
            self, clean_globals, apple_pcap_path):
        # Each of the 8 real Apple advertisements independently trips the
        # skip-apple exit — none slips through.
        for pkt in _apple_packets(apple_pcap_path):
            clean_globals.skip_apple = True
            clean_globals.pcwriter = None
            with pytest.raises(SystemExit) as exc:
                bg.print_packet(pkt, quiet=True)
            assert exc.value.code == APPLE_SKIP_EXIT_CODE

    def test_print_packet_does_not_exit_when_skip_apple_disabled(
            self, clean_globals, apple_pcap_path):
        # Same real Apple advertisement, but -A not passed → no early exit.
        clean_globals.skip_apple = False
        clean_globals.pcwriter = None
        pkt = _apple_packets(apple_pcap_path)[0]
        # Should return normally (an ADV_IND body isn't a valid LL ctrl /
        # ATT PDU, so the downstream handlers no-op).
        bg.print_packet(pkt, quiet=True)

    def test_non_apple_advertisement_does_not_exit_even_with_skip_apple(
            self, clean_globals, mock_hw, make_dpkt):
        # A Microsoft (0x0006) MSD advertisement must NOT trip skip-apple.
        # (mock_hw is required because, with skip_apple on, print_packet's
        # downstream stateful_GATT_getter fires the GATT Manufacturer-Name
        # probe — which transmits — before deciding the packet isn't ATT.)
        clean_globals.skip_apple = True
        clean_globals.pcwriter = None
        # AdvData: Flags + MSD with Company ID 0x0006 (Microsoft).
        adv_data = bytes([2, 0x01, 0x06, 4, 0xFF, 0x06, 0x00, 0x42])
        # body = adv header + length + 6-byte AdvA + adv_data
        body = bytes([0x00, 6 + len(adv_data)]) + bytes(6) + adv_data
        dpkt = make_dpkt(body=body, pdutype="ADV_IND", adv_data=adv_data)
        # Should NOT raise SystemExit.
        bg.print_packet(dpkt, quiet=True)


# ===========================================================================
# Vector 3: GATT Manufacturer Name — detect_Apple_by_GATT_Manufacturer_Name
# ===========================================================================
class TestGATTManufacturerNameVector:
    def _build_att_pdu(self, opcode, extra=b"", cid=0x0004):
        payload = bytes([opcode]) + bytes(extra)
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      cid & 0xFF, (cid >> 8) & 0xFF]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_send_find_by_type_value_req_apple_bytes(self, mock_hw):
        # The exact ATT_FIND_BY_TYPE_VALUE_REQ BG uses to probe for
        # Manufacturer Name (0x2A29) == "Apple Inc.".
        send_ATT_FIND_BY_TYPE_VALUE_REQ_0x2A29_Apple()
        body = mock_hw.transmitted[0][1]
        assert body == bytes([
            0x11, 0x00,              # L2CAP length = 17
            0x04, 0x00,              # CID = ATT
            opcode_ATT_FIND_BY_TYPE_VALUE_REQ,
            0x01, 0x00,              # start handle 0x0001
            0xFF, 0xFF,              # end handle 0xFFFF
            0x29, 0x2A,              # attribute type 0x2A29 (Manufacturer Name)
        ]) + b"Apple Inc."           # attribute value

    def test_first_call_sends_probe_request(
            self, clean_globals, mock_hw, make_dpkt):
        # On the first packet seen, detect_Apple_* fires the probe REQ.
        clean_globals.apple_mfg_req_sent = False
        clean_globals.detect_apple_done = False
        # Feed an unrelated empty data PDU so no match/err path is taken.
        detect_Apple_by_GATT_Manufacturer_Name(2, make_dpkt(body=b"\x01\x00"))
        assert clean_globals.apple_mfg_req_sent is True
        assert mock_hw.transmitted[0][1][4] == opcode_ATT_FIND_BY_TYPE_VALUE_REQ

    def test_find_by_type_value_rsp_is_positive_apple_match(
            self, clean_globals, mock_hw, make_dpkt):
        # ANY ATT_FIND_BY_TYPE_VALUE_RSP means the peripheral had a
        # Manufacturer Name == "Apple Inc." → positive detection.
        clean_globals.apple_mfg_req_sent = True
        clean_globals.detect_apple_done = False
        # RSP carries a found-handles list; one (handle, group) pair here.
        body = self._build_att_pdu(opcode_ATT_FIND_BY_TYPE_VALUE_RSP,
                                    extra=bytes([0x14, 0x00, 0x16, 0x00]))
        result = detect_Apple_by_GATT_Manufacturer_Name(len(body), make_dpkt(body=body))
        assert result is True
        assert clean_globals.apple_mfg_rsp_recv is True

    def test_error_rsp_for_probe_marks_not_apple_and_done(
            self, clean_globals, mock_hw, make_dpkt):
        # An ATT_ERROR_RSP for our FIND_BY_TYPE_VALUE_REQ on handle 0x0001
        # means no Apple Manufacturer Name was found → not Apple, phase done.
        clean_globals.apple_mfg_req_sent = True
        clean_globals.detect_apple_done = False
        # Error body: opcode | req_opcode(0x06) | handle(0x0001) | err_code(0x0A)
        body = self._build_att_pdu(
            opcode_ATT_ERROR_RSP,
            extra=bytes([opcode_ATT_FIND_BY_TYPE_VALUE_REQ, 0x01, 0x00, 0x0A]))
        result = detect_Apple_by_GATT_Manufacturer_Name(len(body), make_dpkt(body=body))
        assert result is False
        assert clean_globals.detect_apple_done is True

    def test_returns_false_immediately_once_detection_done(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.detect_apple_done = True
        result = detect_Apple_by_GATT_Manufacturer_Name(2, make_dpkt(body=b"\x01\x00"))
        assert result is False
        # No probe should have been (re)sent.
        assert mock_hw.transmitted == []


# ===========================================================================
# Vector 3 integration: stateful_GATT_getter exits 0x0A on a GATT match
# ===========================================================================
class TestStatefulGATTGetterAppleExit:
    def _build_find_by_type_value_rsp(self):
        payload = bytes([opcode_ATT_FIND_BY_TYPE_VALUE_RSP, 0x14, 0x00, 0x16, 0x00])
        l2cap_len = len(payload)
        body = bytes([0x02, 0,
                      l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                      0x04, 0x00]) + payload
        body = bytes([0x02, len(body) - 2]) + body[2:]
        return body

    def test_stateful_GATT_getter_exits_0x0A_on_apple_gatt_match(
            self, clean_globals, mock_hw, make_dpkt):
        from BG_Helper_GATT import stateful_GATT_getter
        clean_globals.skip_apple = True
        clean_globals.apple_mfg_req_sent = True   # probe already sent
        clean_globals.detect_apple_done = False
        body = self._build_find_by_type_value_rsp()
        with pytest.raises(SystemExit) as exc:
            stateful_GATT_getter(len(body), make_dpkt(body=body))
        assert exc.value.code == APPLE_SKIP_EXIT_CODE

    def test_stateful_GATT_getter_no_exit_when_skip_apple_disabled(
            self, clean_globals, mock_hw, make_dpkt):
        from BG_Helper_GATT import stateful_GATT_getter
        clean_globals.skip_apple = False
        body = self._build_find_by_type_value_rsp()
        # Without -A, the Apple-by-GATT detection is never consulted.
        stateful_GATT_getter(len(body), make_dpkt(body=body))


# ===========================================================================
# Vector 2 cross-reference: LL_VERSION_IND Company ID
# (full coverage lives in test_ll_ctrl.py::TestIncomingLLVersionInd; this
# pins the exit-code contract is the same 0x0A across all three vectors.)
# ===========================================================================
class TestLLVersionIndVectorExitCode:
    def test_ll_version_ind_apple_company_id_exits_with_same_0x0A(
            self, clean_globals, mock_hw, make_dpkt):
        from BG_Helper_LL import incoming_LL_VERSION_IND, opcode_LL_VERSION_IND
        clean_globals.skip_apple = True
        # LL_VERSION_IND body: header|len|opcode|version|company_id(2)|subver(2)
        body = bytes([0x03, 0x06, opcode_LL_VERSION_IND, 0x0B,
                      0x4C, 0x00,   # company_id 0x004C = Apple
                      0x01, 0x00])
        with pytest.raises(SystemExit) as exc:
            incoming_LL_VERSION_IND(len(body), make_dpkt(body=body))
        assert exc.value.code == APPLE_SKIP_EXIT_CODE
