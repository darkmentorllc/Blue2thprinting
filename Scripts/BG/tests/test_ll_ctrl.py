########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for Scripts/BG/BG_Helper_LL.py — the LL Control state machine
that BG drives during the post-CONNECT_IND prelude (FEATURE_REQ/RSP,
VERSION_IND, LENGTH_REQ/RSP, PHY_REQ/RSP/UPDATE_IND) before ATT enumeration
begins.

The pcap from BG against CA:FE:13:37:00:01 exercises all of these in the
expected ordering. These tests pin each handler in isolation so a future
refactor of the state machine breaks the suite if the wire-format parsing
or the state-flag updates change."""

import pytest

from BG_Helper_LL import (
    LL_opcode_to_str,
    LLID_ctrl,
    clear_pending_packet_state,
    incoming_LL_FEATURE_RSP,
    incoming_LL_LENGTHs,
    incoming_LL_PERIPHERAL_FEATURE_REQ,
    incoming_LL_PHYs,
    incoming_LL_VERSION_IND,
    incoming_LL_errors,
    opcode_LL_FEATURE_REQ,
    opcode_LL_FEATURE_RSP,
    opcode_LL_LENGTH_REQ,
    opcode_LL_LENGTH_RSP,
    opcode_LL_PERIPHERAL_FEATURE_REQ,
    opcode_LL_PHY_REQ,
    opcode_LL_PHY_RSP,
    opcode_LL_REJECT_EXT_IND,
    opcode_LL_REJECT_IND,
    opcode_LL_TERMINATE_IND,
    opcode_LL_UNKNOWN_RSP,
    opcode_LL_VERSION_IND,
    send_LL_FEATURE_REQ,
    send_LL_LENGTH_REQ,
    send_LL_LENGTH_RSP,
    send_LL_PHY_REQ,
    send_LL_PHY_RSP,
    send_LL_PHY_UPDATE_IND,
    send_LL_REJECT_EXT_IND,
    send_LL_TERMINATE_IND,
    send_LL_VERSION_IND,
    stateful_LL_CTRL_outgoing_handler,
)


# ---------------------------------------------------------------------------
# Opcode constants — defend against silent renumbering
# ---------------------------------------------------------------------------
class TestOpcodeConstants:
    """The opcodes below come from BT Core spec v5.4 Table 4.5. Pinning them
    means a careless edit to BG_Helper_LL.py is caught immediately."""

    @pytest.mark.parametrize("name,value", [
        ("LL_TERMINATE_IND", 0x02),
        ("LL_UNKNOWN_RSP", 0x07),
        ("LL_FEATURE_REQ", 0x08),
        ("LL_FEATURE_RSP", 0x09),
        ("LL_VERSION_IND", 0x0C),
        ("LL_REJECT_IND", 0x0D),
        ("LL_PERIPHERAL_FEATURE_REQ", 0x0E),
        ("LL_REJECT_EXT_IND", 0x11),
        ("LL_LENGTH_REQ", 0x14),
        ("LL_LENGTH_RSP", 0x15),
        ("LL_PHY_REQ", 0x16),
        ("LL_PHY_RSP", 0x17),
        ("LL_PHY_UPDATE_IND", 0x18),
    ])
    def test_opcode_value_matches_BT_spec(self, name, value):
        # Resolve via the LL_opcode_to_str map so we exercise both the
        # value and the str-table lookup that BG uses for log lines.
        assert LL_opcode_to_str[value] == name


# ---------------------------------------------------------------------------
# Outgoing packet senders — verify the wire-format bytes
# ---------------------------------------------------------------------------
class TestOutgoingPacketBytes:
    def test_send_LL_VERSION_IND_emits_opcode_version_company_subversion(self, mock_hw):
        send_LL_VERSION_IND(version=6, company_id=0x1337, subversion=0x4242)
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            opcode_LL_VERSION_IND, 0x06,
            0x37, 0x13,    # 0x1337 little-endian
            0x42, 0x42,    # 0x4242 little-endian
        ]))]

    def test_send_LL_FEATURE_REQ_emits_8_byte_feature_set(self, mock_hw):
        send_LL_FEATURE_REQ(0x0123456789ABCDEF)
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            opcode_LL_FEATURE_REQ,
            0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01,
        ]))]

    def test_send_LL_LENGTH_REQ_emits_4_uint16s_little_endian(self, mock_hw):
        # The typical BG values: 251 octets, 2120 µs each way.
        send_LL_LENGTH_REQ(MaxRxOctets=0x00FB, MaxRxTime=0x0848,
                           MaxTxOctets=0x00FB, MaxTxTime=0x0848)
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            opcode_LL_LENGTH_REQ,
            0xFB, 0x00, 0x48, 0x08, 0xFB, 0x00, 0x48, 0x08,
        ]))]

    def test_send_LL_LENGTH_RSP_distinguishes_from_REQ_by_opcode(self, mock_hw):
        send_LL_LENGTH_RSP(0x00FB, 0x0848, 0x00FB, 0x0848)
        assert mock_hw.transmitted[0][1][0] == opcode_LL_LENGTH_RSP

    def test_send_LL_PHY_REQ_emits_tx_phys_then_rx_phys(self, mock_hw):
        send_LL_PHY_REQ(tx_phys=0x02, rx_phys=0x02)
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            opcode_LL_PHY_REQ, 0x02, 0x02,
        ]))]

    def test_send_LL_PHY_RSP_distinguishes_from_REQ_by_opcode(self, mock_hw):
        send_LL_PHY_RSP(0x01, 0x01)
        assert mock_hw.transmitted[0][1][0] == opcode_LL_PHY_RSP

    def test_send_LL_PHY_UPDATE_IND_includes_instant_from_connEventCount(
            self, clean_globals, mock_hw):
        clean_globals.connEventCount = 0x1000
        send_LL_PHY_UPDATE_IND(phy_c_to_p=0x02, phy_p_to_c=0x02, instant_offset=3)
        # Instant = 0x1000 + 3 = 0x1003 little-endian → 0x03 0x10.
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            0x18, 0x02, 0x02, 0x03, 0x10,
        ]))]

    def test_send_LL_REJECT_EXT_IND_carries_rejected_opcode_and_error_code(self, mock_hw):
        # The pcap frame 14 (Central rejecting Peripheral's LL_PHY_REQ) has
        # rejected opcode 0x16 (LL_PHY_REQ) and error code 0x0C (Command Disallowed).
        send_LL_REJECT_EXT_IND(opcode=opcode_LL_PHY_REQ, error_code=0x0C)
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            opcode_LL_REJECT_EXT_IND, opcode_LL_PHY_REQ, 0x0C,
        ]))]

    def test_send_LL_TERMINATE_IND_emits_two_bytes_with_error_0x13(self, mock_hw):
        # opcode 0x02 (LL_TERMINATE_IND) + error code 0x13 (Remote User
        # Terminated Connection). This matches what print_and_exit() in
        # BG_Helper_Output.py writes inline, so both teardown paths now
        # send the same bytes.
        send_LL_TERMINATE_IND()
        assert mock_hw.transmitted == [(LLID_ctrl, bytes([
            opcode_LL_TERMINATE_IND, 0x13,
        ]))]


# ---------------------------------------------------------------------------
# incoming_LL_VERSION_IND
# ---------------------------------------------------------------------------
class TestIncomingLLVersionInd:
    def _build_version_ind(self, version=0x0B, company_id=0x000F, subversion=0x1234):
        # Body layout: header(0x03) | ll_len(0x06) | opcode(0x0C) | version | company_id(2) | subversion(2)
        return bytes([
            0x03, 0x06, opcode_LL_VERSION_IND, version,
            company_id & 0xFF, (company_id >> 8) & 0xFF,
            subversion & 0xFF, (subversion >> 8) & 0xFF,
        ])

    def test_sets_received_state_and_sends_version_ind_back(
            self, clean_globals, mock_hw, make_dpkt):
        body = self._build_version_ind(version=0x0B, company_id=0x000F)  # 0x000F = Broadcom
        dpkt = make_dpkt(body=body)

        incoming_LL_VERSION_IND(len(body), dpkt)

        assert clean_globals.ll_version_ind_recv is True
        assert clean_globals.current_ll_ctrl_state.ll_version_received is True
        assert clean_globals.current_ll_ctrl_state.ll_version_state == \
            clean_globals.ll_packet_names_to_states["Received"]
        # Should have responded with our own LL_VERSION_IND if not already sent.
        assert len(mock_hw.transmitted) == 1
        assert mock_hw.transmitted[0][1][0] == opcode_LL_VERSION_IND

    def test_does_not_resend_if_we_already_sent(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.ll_version_ind_sent = True
        body = self._build_version_ind()
        incoming_LL_VERSION_IND(len(body), make_dpkt(body=body))
        assert mock_hw.transmitted == []

    def test_apple_company_id_004C_exits_when_skip_apple_set(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.skip_apple = True
        body = self._build_version_ind(company_id=0x004C)
        with pytest.raises(SystemExit) as exc:
            incoming_LL_VERSION_IND(len(body), make_dpkt(body=body))
        assert exc.value.code == 0x0A

    def test_skip_apple_off_means_apple_id_does_not_exit(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.skip_apple = False
        body = self._build_version_ind(company_id=0x004C)
        # Should NOT raise SystemExit.
        incoming_LL_VERSION_IND(len(body), make_dpkt(body=body))
        assert clean_globals.ll_version_ind_recv is True


# ---------------------------------------------------------------------------
# incoming_LL_PERIPHERAL_FEATURE_REQ — Zephyr-style devices send this first
# ---------------------------------------------------------------------------
class TestIncomingLLPeripheralFeatureReq:
    def _build_periph_feature_req(self, features):
        # Body: header | ll_len(0x09) | opcode(0x0E) | features(8 little-endian)
        return bytes([0x03, 0x09, opcode_LL_PERIPHERAL_FEATURE_REQ]) + \
            features.to_bytes(8, "little")

    def test_responds_with_feature_rsp_and_records_features(
            self, clean_globals, mock_hw, make_dpkt):
        # bit 8 set = 2M PHY supported per spec table.
        features = 0x0000_0000_0000_0100
        body = self._build_periph_feature_req(features)

        incoming_LL_PERIPHERAL_FEATURE_REQ(len(body), make_dpkt(body=body))

        assert clean_globals.current_ll_ctrl_state.ll_features_received is True
        assert clean_globals.current_ll_ctrl_state.ll_peripheral_features == features
        assert clean_globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy is True
        assert clean_globals.ll_peripheral_feature_req_recv is True
        # We should have sent our LL_FEATURE_RSP back.
        assert mock_hw.transmitted[0][1][0] == opcode_LL_FEATURE_RSP

    def test_no_2M_phy_bit_means_supports_2M_phy_stays_false(
            self, clean_globals, mock_hw, make_dpkt):
        # bit 0 set only (LE Encryption) — 2M PHY (bit 8) NOT set.
        body = self._build_periph_feature_req(0x0000_0000_0000_0001)
        incoming_LL_PERIPHERAL_FEATURE_REQ(len(body), make_dpkt(body=body))
        assert clean_globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy is False

    def test_skipped_when_features_already_received(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.current_ll_ctrl_state.ll_features_received = True
        body = self._build_periph_feature_req(0x0)
        incoming_LL_PERIPHERAL_FEATURE_REQ(len(body), make_dpkt(body=body))
        assert mock_hw.transmitted == []


# ---------------------------------------------------------------------------
# incoming_LL_FEATURE_RSP
# ---------------------------------------------------------------------------
class TestIncomingLLFeatureRsp:
    def _build_feature_rsp(self, features):
        return bytes([0x03, 0x09, opcode_LL_FEATURE_RSP]) + features.to_bytes(8, "little")

    def test_marks_phase_done_and_clears_pending_state(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.ll_feature_req_sent = True
        clean_globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = True
        features = 0x0000_0000_0000_0100
        body = self._build_feature_rsp(features)

        incoming_LL_FEATURE_RSP(len(body), make_dpkt(body=body))

        assert clean_globals.ll_feature_rsp_recv is True
        assert clean_globals.current_ll_ctrl_state.ll_features_received is True
        assert clean_globals.current_ll_ctrl_state.ll_peripheral_features == features
        assert clean_globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy is True
        assert clean_globals.current_ll_ctrl_state.ll_ctrl_pkt_pending is False

    def test_ignored_if_we_never_sent_feature_req(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.ll_feature_req_sent = False
        body = self._build_feature_rsp(0x1)
        incoming_LL_FEATURE_RSP(len(body), make_dpkt(body=body))
        assert clean_globals.ll_feature_rsp_recv is False


# ---------------------------------------------------------------------------
# incoming_LL_LENGTHs
# ---------------------------------------------------------------------------
class TestIncomingLLLengths:
    def _build_length_pdu(self, opcode, rx_octet, rx_time, tx_octet, tx_time):
        return bytes([0x03, 0x09, opcode]) + \
            rx_octet.to_bytes(2, "little") + rx_time.to_bytes(2, "little") + \
            tx_octet.to_bytes(2, "little") + tx_time.to_bytes(2, "little")

    def test_LENGTH_RSP_updates_state_and_mtu(
            self, clean_globals, mock_hw, make_dpkt):
        body = self._build_length_pdu(opcode_LL_LENGTH_RSP, 0x00FB, 0x0848, 0x00FB, 0x0848)
        incoming_LL_LENGTHs(len(body), make_dpkt(body=body))

        assert clean_globals.ll_length_rsp_recv is True
        assert clean_globals.current_ll_ctrl_state.ll_length_negotiated is True
        assert clean_globals.current_ll_ctrl_state.ll_length_max_rx_octet == 0x00FB
        assert clean_globals.current_ll_ctrl_state.ll_length_max_tx_octet == 0x00FB
        # MTU gets bumped to the negotiated rx octet count.
        assert clean_globals.att_mtu == 0x00FB

    def test_LENGTH_REQ_echoes_RSP_and_records_negotiation(
            self, clean_globals, mock_hw, make_dpkt):
        body = self._build_length_pdu(opcode_LL_LENGTH_REQ, 0x00FB, 0x0848, 0x00FB, 0x0848)
        incoming_LL_LENGTHs(len(body), make_dpkt(body=body))

        assert clean_globals.ll_length_rsp_recv is True
        assert clean_globals.ll_length_req_recv is True
        assert clean_globals.current_ll_ctrl_state.ll_length_negotiated is True
        # Should have sent a LL_LENGTH_RSP echoing those values.
        sent_opcode = mock_hw.transmitted[0][1][0]
        assert sent_opcode == opcode_LL_LENGTH_RSP

    def test_smaller_negotiated_rx_octet_does_not_decrease_existing(
            self, clean_globals, mock_hw, make_dpkt):
        # Pre-seed a larger value, then ask for negotiation at default size.
        clean_globals.current_ll_ctrl_state.ll_length_max_rx_octet = 100
        body = self._build_length_pdu(opcode_LL_LENGTH_RSP, 27, 0x0148, 27, 0x0148)
        incoming_LL_LENGTHs(len(body), make_dpkt(body=body))
        # The pre-seeded 100 should NOT be overwritten by a smaller 27.
        assert clean_globals.current_ll_ctrl_state.ll_length_max_rx_octet == 100

    def test_skipped_once_negotiation_complete(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.current_ll_ctrl_state.ll_length_negotiated = True
        body = self._build_length_pdu(opcode_LL_LENGTH_RSP, 0x00FB, 0x0848, 0x00FB, 0x0848)
        # Should be a no-op when negotiation already happened.
        incoming_LL_LENGTHs(len(body), make_dpkt(body=body))
        assert mock_hw.transmitted == []


# ---------------------------------------------------------------------------
# incoming_LL_PHYs
# ---------------------------------------------------------------------------
class TestIncomingLLPhys:
    def _build_phy_pdu(self, opcode, tx_phys=0x02, rx_phys=0x02):
        return bytes([0x03, 0x03, opcode, tx_phys, rx_phys])

    def test_incoming_PHY_REQ_rejected_with_REJECT_EXT_IND(
            self, clean_globals, mock_hw, make_dpkt):
        # Frame 14 of the CA:FE pcap is exactly this: Peripheral sent
        # LL_PHY_REQ, BG responded with LL_REJECT_EXT_IND because the user
        # didn't pass `-2` and BG wants to drive its own PHY negotiation.
        body = self._build_phy_pdu(opcode_LL_PHY_REQ)
        incoming_LL_PHYs(len(body), make_dpkt(body=body))

        assert clean_globals.ll_phy_req_recv is True
        assert mock_hw.transmitted[0][1][0] == opcode_LL_REJECT_EXT_IND
        # The rejected opcode echo should be LL_PHY_REQ.
        assert mock_hw.transmitted[0][1][1] == opcode_LL_PHY_REQ
        # Error code 0x0C = Command Disallowed.
        assert mock_hw.transmitted[0][1][2] == 0x0C

    def test_incoming_PHY_RSP_marks_done(
            self, clean_globals, mock_hw, make_dpkt):
        body = self._build_phy_pdu(opcode_LL_PHY_RSP)
        incoming_LL_PHYs(len(body), make_dpkt(body=body))
        assert clean_globals.ll_phy_rsp_recv is True


# ---------------------------------------------------------------------------
# incoming_LL_errors
# ---------------------------------------------------------------------------
class TestIncomingLLErrors:
    def test_LL_UNKNOWN_RSP_for_LENGTH_REQ_marks_phase_done(
            self, clean_globals, mock_hw, make_dpkt):
        # If the Peripheral is v4.0 (pre-LE Data Packet Length Extension), it
        # responds to LL_LENGTH_REQ with LL_UNKNOWN_RSP. BG treats that as
        # "phase done, use the 27-octet default" and moves on.
        clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_LENGTH_REQ
        # Body: header | ll_len(0x02) | opcode(0x07) | unknown_type(0x14=LENGTH_REQ)
        body = bytes([0x03, 0x02, opcode_LL_UNKNOWN_RSP, opcode_LL_LENGTH_REQ])

        incoming_LL_errors(len(body), make_dpkt(body=body))

        assert clean_globals.current_ll_ctrl_state.ll_length_state == \
            clean_globals.ll_packet_names_to_states["Unknown"]
        assert clean_globals.att_MTU_negotiated is True

    def test_LL_REJECT_IND_for_LENGTH_REQ_marks_phase_done(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_LENGTH_REQ
        body = bytes([0x03, 0x02, opcode_LL_REJECT_IND, 0x1A])  # 0x1A = "Unsupported Remote Feature"

        incoming_LL_errors(len(body), make_dpkt(body=body))

        assert clean_globals.current_ll_ctrl_state.ll_length_state == \
            clean_globals.ll_packet_names_to_states["Rejected"]

    def test_LL_REJECT_EXT_IND_for_LENGTH_REQ_marks_phase_done(
            self, clean_globals, mock_hw, make_dpkt):
        clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_LENGTH_REQ
        # Body: header | ll_len(0x03) | opcode | rejected_opcode | error_code
        body = bytes([0x03, 0x03, opcode_LL_REJECT_EXT_IND, opcode_LL_LENGTH_REQ, 0x1A])

        incoming_LL_errors(len(body), make_dpkt(body=body))

        assert clean_globals.current_ll_ctrl_state.ll_length_state == \
            clean_globals.ll_packet_names_to_states["Rejected"]

    def test_clear_pending_packet_state_resets_all_three(self, clean_globals):
        clean_globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = True
        clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_VERSION_IND
        clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = 12345
        clear_pending_packet_state()
        assert clean_globals.current_ll_ctrl_state.ll_ctrl_pkt_pending is False
        assert clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode is None
        assert clean_globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time is None


# ---------------------------------------------------------------------------
# stateful_LL_CTRL_outgoing_handler ordering
# ---------------------------------------------------------------------------
class TestStatefulOutgoingHandler:
    def test_first_call_sends_feature_req(self, clean_globals, mock_hw):
        # Fresh state: nothing sent, nothing pending → should kick off with
        # LL_FEATURE_REQ as the first outbound packet.
        stateful_LL_CTRL_outgoing_handler()
        assert len(mock_hw.transmitted) == 1
        assert mock_hw.transmitted[0][1][0] == opcode_LL_FEATURE_REQ
        assert clean_globals.ll_feature_req_sent is True

    def test_after_features_received_next_sends_version_ind(
            self, clean_globals, mock_hw):
        # Mark features negotiated; nothing pending → should send VERSION_IND.
        clean_globals.current_ll_ctrl_state.ll_features_received = True
        clean_globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = False

        stateful_LL_CTRL_outgoing_handler()

        assert mock_hw.transmitted[0][1][0] == opcode_LL_VERSION_IND
        assert clean_globals.ll_version_ind_sent is True

    def test_no_LENGTH_REQ_until_version_ind_received(
            self, clean_globals, mock_hw):
        # Features received, version not yet received → version_ind is next,
        # not length_req. (Length_req only fires after features + version.)
        clean_globals.current_ll_ctrl_state.ll_features_received = True
        clean_globals.current_ll_ctrl_state.ll_version_received = False

        stateful_LL_CTRL_outgoing_handler()

        # Sent VERSION_IND first, NOT LENGTH_REQ.
        assert mock_hw.transmitted[0][1][0] == opcode_LL_VERSION_IND

    def test_after_features_and_version_received_sends_length_req(
            self, clean_globals, mock_hw):
        clean_globals.current_ll_ctrl_state.ll_features_received = True
        clean_globals.current_ll_ctrl_state.ll_version_received = True
        clean_globals.ll_version_ind_recv = True

        stateful_LL_CTRL_outgoing_handler()

        assert mock_hw.transmitted[0][1][0] == opcode_LL_LENGTH_REQ
        assert clean_globals.ll_length_req_sent is True

    def test_attempt_2M_PHY_update_triggers_PHY_REQ_after_version_recv(
            self, clean_globals, mock_hw):
        # With -2 set and peripheral confirmed to support 2M, the handler
        # should send LL_PHY_REQ after VERSION_IND is received.
        clean_globals.attempt_2M_PHY_update = True
        clean_globals.current_ll_ctrl_state.ll_features_received = True
        clean_globals.current_ll_ctrl_state.ll_version_received = True
        clean_globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy = True
        clean_globals.ll_version_ind_recv = True

        stateful_LL_CTRL_outgoing_handler()

        assert mock_hw.transmitted[0][1][0] == opcode_LL_PHY_REQ
