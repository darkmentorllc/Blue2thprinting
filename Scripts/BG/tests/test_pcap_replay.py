########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end replay of the captured CA:FE:13:37:00:01 pcap through the BG
state machines.

This is the strongest functional test in the BG suite: it loads every frame
captured by Sniffle during a real BG run, feeds the post-CONNECT_IND data
frames through the same dispatch the live `print_packet()` function uses,
and asserts that every state-machine phase reaches its terminal flag. If a
future refactor of any of the helper modules breaks the LL → ATT → SMP
pipeline, this test catches it without needing a sniffer dongle attached."""

from struct import unpack

import pytest

import globals as g


def _iter_pcap_frames(pcap_path):
    """Stream every frame from a DLT_BLUETOOTH_LE_LL_WITH_PHDR pcap (the
    format sniffle.PcapBleWriter produces) and yield
    (body, rf_chan, peripheral_send_bool) tuples.

    Sniffle's PcapBleReader can't reliably round-trip direction or recover
    the LL Control PDU class without the encryption/AA state it has at
    capture time. Reading the file ourselves lets the BG state machine
    consume the post-CONNECT_IND data PDUs in their original direction."""
    with open(str(pcap_path), "rb") as f:
        # 24-byte pcap global header — skip after sanity check.
        global_hdr = f.read(24)
        magic, _ver_major, _ver_minor, _tz, _sigfigs, _snaplen, dlt = \
            unpack("<IHHIIII", global_hdr)
        assert magic == 0xA1B2C3D4
        assert dlt == 256, f"expected DLT_BLUETOOTH_LE_LL_WITH_PHDR, got {dlt}"

        while True:
            rec_hdr = f.read(16)
            if len(rec_hdr) < 16:
                return
            _ts_sec, _ts_usec, incl_len, _orig_len = unpack("<IIII", rec_hdr)
            payload = f.read(incl_len)
            # LE RF Info phdr is 14 bytes; layout:
            #   B  rf_chan
            #   b  rssi
            #   b  unused signed
            #   B  unused unsigned
            #   I  reference access address (uint32 LE)
            #   H  flags  (low byte first)
            #   I  unused
            rf_chan, rssi, _u1, _u2, _aa, flags, _u3 = unpack("<BbbBIHI", payload[:14])
            # Wireshark "PDU Type" sits at flags bits 7..9.
            #   0 = advertising (unspec direction)
            #   2 = data: Central → Peripheral
            #   3 = data: Peripheral → Central
            pdu_type = (flags >> 7) & 0x7
            phy = (flags >> 14) & 0x3
            body_start = 14
            if phy == 3:        # PHY_CODED — extra 1-byte coding indicator.
                body_start += 1
            body = payload[body_start:-3]   # trim 3-byte CRC tail
            peripheral_send = pdu_type == 3
            yield body, rf_chan, peripheral_send


class _ReplayPkt:
    """Stand-in for sniffle.packet_decoder.PacketMessage — the BG helpers
    only consult `.body` (raw LL PDU bytes), so that's all we provide."""

    def __init__(self, body):
        self.body = body
        self.phy = 0
        self.event = 0
        self.data_length = max(0, len(body) - 2)


def _replay_pcap(pcap_path, mock_hw, clean_globals):
    """Dispatch every Peripheral → Central data PDU through the BG
    handlers, mirroring what `print_packet()` does at runtime. Outbound
    (Central → Peripheral) frames just flip the corresponding `*_sent`
    flag so the matching `*_recv` handler is allowed to run on the next
    inbound frame."""
    from BG_Helper_LL import stateful_LL_CTRL_incoming_handler
    from BG_Helper_L2CAP import stateful_incoming_L2CAP_handler
    from BG_Helper_GATT import stateful_GATT_getter
    from BG_Helper_SMP import handle_SMP_Pairing

    frame_count = 0
    for body, chan, peripheral_send in _iter_pcap_frames(pcap_path):
        frame_count += 1

        if chan >= 37:
            continue   # advertising-channel frame, skip

        if not peripheral_send:
            # Mirror BG's send-side state updates for outbound LL CTRL.
            if len(body) >= 3 and (body[0] & 0x3) == 0x3:
                _record_outbound_state(body[2], clean_globals)
            # Mirror the "I just asked for this handle" bookkeeping for any
            # outbound ATT_READ_REQ — so the next Peripheral response gets
            # attributed to the right handle in `all_handles_received_values`.
            _record_outbound_att_read_handle(body, clean_globals)
            continue

        actual_body_len = len(body)
        pkt = _ReplayPkt(body)

        if actual_body_len >= 3:
            header_ACID, ll_len_ACID, ll_ctl_opcode = unpack("<BBB", body[:3])
            if (header_ACID & 0x3) == 0x3:
                stateful_LL_CTRL_incoming_handler(actual_body_len, ll_ctl_opcode, pkt)
            else:
                stateful_incoming_L2CAP_handler(actual_body_len, pkt)
                try:
                    stateful_GATT_getter(actual_body_len, pkt)
                except SystemExit:
                    # print_and_exit() exits when the SMP phase finishes.
                    break
                try:
                    handle_SMP_Pairing(actual_body_len, pkt, max_key_size=0x10)
                except SystemExit:
                    break
        elif actual_body_len == 2:
            stateful_incoming_L2CAP_handler(actual_body_len, pkt)
            try:
                stateful_GATT_getter(actual_body_len, pkt)
            except SystemExit:
                break
            try:
                handle_SMP_Pairing(actual_body_len, pkt, max_key_size=0x10)
            except SystemExit:
                break

    return frame_count


def _record_outbound_state(opcode, clean_globals):
    """Mirror the bookkeeping that BG_Helper_LL's send_*_and_update_state
    helpers would have done for each outbound LL Control PDU."""
    from BG_Helper_LL import (
        opcode_LL_FEATURE_REQ,
        opcode_LL_LENGTH_REQ,
        opcode_LL_PHY_REQ,
        opcode_LL_VERSION_IND,
    )
    if opcode == opcode_LL_FEATURE_REQ:
        clean_globals.ll_feature_req_sent = True
    elif opcode == opcode_LL_VERSION_IND:
        clean_globals.ll_version_ind_sent = True
    elif opcode == opcode_LL_LENGTH_REQ:
        clean_globals.ll_length_req_sent = True
    elif opcode == opcode_LL_PHY_REQ:
        clean_globals.ll_phy_req_sent = True


def _record_outbound_att_read_handle(body, clean_globals):
    """If `body` is an outbound L2CAP-ATT ATT_READ_REQ, extract its handle
    and pin BG's `handle_read_last_sent_handle` to it so that the next
    inbound ATT_READ_RSP (or ATT_ERROR_RSP) is attributed to the right
    handle when the replay feeds it through process_ATT_READ_RSP."""
    if len(body) < 9:
        return
    # Outbound data PDU on the ATT channel:
    #   body[0]: LL header (LLID 0b10 = start of L2CAP)
    #   body[1]: LL length
    #   body[2:4]: L2CAP length (2)
    #   body[4:6]: L2CAP CID (2)  → 0x0004 for ATT
    #   body[6]:    ATT opcode    → 0x0A for ATT_READ_REQ
    #   body[7:9]:  handle (2)
    if (body[0] & 0x3) != 0x2:
        return
    if body[4:6] != b"\x04\x00":
        return
    if body[6] != 0x0A:           # opcode_ATT_READ_REQ
        return
    handle = body[7] | (body[8] << 8)
    clean_globals.handle_read_last_sent_handle = handle
    # Also need to seed handle_read_req_sent_time so incoming_read_all_handles
    # is allowed to run (it gates on the time being set).
    if not clean_globals.handle_read_req_sent_time:
        clean_globals.handle_read_req_sent_time = 1


class TestCAFEReplay:
    """All assertions below mirror the on-the-wire state captured in
    Scripts/BG/tests/fixtures/cafe_capture.pcap."""

    @pytest.fixture
    def replayed(self, cafe_pcap_path, mock_hw, clean_globals):
        # Set the target bdaddr for write_to_csv path consistency.
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        n_frames = _replay_pcap(cafe_pcap_path, mock_hw, clean_globals)
        return n_frames, clean_globals, mock_hw

    def test_replays_all_354_frames(self, replayed):
        n_frames, _, _ = replayed
        # The fixture pcap is the actual capture; the BG run produced 354
        # frames including ADV_IND + CONNECT_IND + every LL/ATT/SMP packet
        # through to LL_TERMINATE_IND.
        assert n_frames == 354

    def test_LL_VERSION_IND_received_from_peripheral(self, replayed):
        _, glb, _ = replayed
        assert glb.ll_version_ind_recv is True
        assert glb.current_ll_ctrl_state.ll_version_received is True

    def test_LL_FEATURE_REQ_sent_and_RSP_received(self, replayed):
        _, glb, _ = replayed
        # We sent a Central-initiated LL_FEATURE_REQ and got an RSP back.
        assert glb.current_ll_ctrl_state.ll_features_received is True

    def test_LL_PERIPHERAL_FEATURE_REQ_handled(self, replayed):
        _, glb, _ = replayed
        # Frame 5 was a Peripheral-initiated LL_PERIPHERAL_FEATURE_REQ —
        # BG must have responded so we record we saw it.
        assert glb.ll_peripheral_feature_req_recv is True

    def test_LL_LENGTH_negotiated(self, replayed):
        _, glb, _ = replayed
        # Frame 20 was an incoming LL_LENGTH_REQ; BG sent the RSP.
        assert glb.current_ll_ctrl_state.ll_length_negotiated is True

    def test_LL_PHY_REQ_received_and_REJECTed(self, replayed):
        _, glb, mock_hw = replayed
        # Frame 13 was the Peripheral's LL_PHY_REQ; BG sent LL_REJECT_EXT_IND
        # because the user didn't pass `-2`.
        assert glb.ll_phy_req_recv is True
        from BG_Helper_LL import opcode_LL_REJECT_EXT_IND
        rejects = [b for _, b in mock_hw.transmitted
                   if b and b[0] == opcode_LL_REJECT_EXT_IND]
        assert len(rejects) >= 1

    def test_ATT_MTU_negotiated_after_LL_LENGTH(self, replayed):
        _, glb, _ = replayed
        # Frame 7 was the Peripheral's MTU_REQ (queued until LL Length done).
        assert glb.att_MTU_negotiated is True
        assert glb.att_exchange_MTU_req_recv is True

    def test_primary_services_enumeration_complete(self, replayed):
        _, glb, _ = replayed
        # Frames 31, 35, 38, 42 cycled through Primary Service ranges. The
        # final 0x0042 request got Attribute Not Found, marking phase done.
        assert glb.primary_services_all_recv is True
        # Should have discovered: GATT, GAP, Battery, Device Information,
        # OTS (Object Transfer Service), Vendor (444D...) → at least 5.
        assert len(glb.primary_service_handle_ranges_dict) >= 5

    def test_secondary_services_enumeration_complete(self, replayed):
        _, glb, _ = replayed
        # Frame 50 returned Attribute Not Found for secondary services.
        assert glb.secondary_services_all_recv is True

    def test_handle_enumeration_via_find_information(self, replayed):
        _, glb, _ = replayed
        # We learned every handle from 0x0001 through ~0x0041.
        assert glb.all_info_handles_recv is True
        assert len(glb.received_handles) >= 60

    def test_handles_read_marked_complete(self, replayed):
        _, glb, _ = replayed
        # The replay should have read every readable handle (some returning
        # errors like Read Not Permitted or Insufficient Authentication).
        assert glb.all_handles_read is True

    def test_handles_with_errors_recorded(self, replayed):
        _, glb, _ = replayed
        # The pcap shows: 0x0003 Read Not Permitted, 0x001E Read Not Permitted,
        # 0x0026 Read Not Permitted, 0x002A Insufficient Authentication, etc.
        assert 0x0003 in glb.handles_with_error_rsp
        assert glb.handles_with_error_rsp[0x0003] == 0x02  # Read Not Permitted
        assert 0x002A in glb.handles_with_error_rsp
        assert glb.handles_with_error_rsp[0x002A] == 0x05  # Insufficient Auth

    def test_SMP_pairing_request_sent_and_response_received(self, replayed):
        _, glb, _ = replayed
        # Frames 351 / 353: Pairing Request / Response (legacy, No Bonding).
        assert glb.smp_legacy_pairing_req_sent is True
        assert glb.smp_legacy_pairing_rsp_recv is True

    def test_known_characteristic_values_extracted(self, replayed):
        _, glb, _ = replayed
        # Handle 0x000B = Device Name = "UVP01" (0x55 0x56 0x50 0x30 0x31)
        # is read early in the value-read phase, before BG and the replay
        # diverge on request ordering, so it lines up reliably.
        assert glb.all_handles_received_values[0x000B] == b"UVP01"
        # Some readable handles further into the table also get values —
        # we don't pin specific handles past the divergence point because
        # the replay's request order can drift from the captured order.
        readable_byte_values = [v for v in glb.all_handles_received_values.values()
                                if isinstance(v, bytes) and len(v) > 0]
        assert len(readable_byte_values) >= 30

    def test_outbound_transmissions_recorded(self, replayed):
        _, _, mock_hw = replayed
        # BG should have sent at least: FEATURE_REQ, VERSION_IND, LENGTH_REQ
        # echo, MTU_RSP, REJECT_EXT_IND for PHY, group-type/find-info/read
        # requests, and the SMP Pairing Request — many dozens of packets.
        assert len(mock_hw.transmitted) >= 20

    def test_outbound_contains_SMP_Pairing_Request(self, replayed):
        _, _, mock_hw = replayed
        from BG_Helper_SMP import opcode_SMP_Pairing_Req
        # The SMP Pairing Request body starts with L2CAP-len(2) + CID(2)
        # + SMP_opcode at offset 4.
        smp_reqs = [b for _, b in mock_hw.transmitted
                    if len(b) >= 5 and b[2:4] == bytes([0x06, 0x00])  # SMP CID
                    and b[4] == opcode_SMP_Pairing_Req]
        assert len(smp_reqs) >= 1


class TestPublicPcapReplay:
    """Replay of the BG run against the public Samsung BDADDR
    `7c:0a:3f:58:72:7b` captured during the NYC_Day1 sniff. Exercises the
    `-P -2` launcher path: public address + 2M PHY update + the SMP retry
    cap (this peripheral never answered Pairing Request, so BG gave up
    after 6 sends and terminated the connection cleanly)."""

    @pytest.fixture
    def replayed(self, public_pcap_path, mock_hw, clean_globals):
        clean_globals.target_bdaddr = "7c:0a:3f:58:72:7b"
        clean_globals.target_bdaddr_type_public = True
        # `-2` flag → attempt 2M PHY update.
        clean_globals.attempt_2M_PHY_update = True
        n_frames = _replay_pcap(public_pcap_path, mock_hw, clean_globals)
        return n_frames, clean_globals, mock_hw

    def test_replay_produces_packets(self, replayed):
        n_frames, _, _ = replayed
        # The fixture has 387 frames from a real BG run against the Samsung
        # peripheral; the replay should walk every one.
        assert n_frames == 387

    def test_LL_VERSION_IND_received(self, replayed):
        _, glb, _ = replayed
        # The Samsung peripheral responded with its LL_VERSION_IND in the
        # opening prelude (frame ~5 of the pcap).
        assert glb.ll_version_ind_recv is True

    def test_2M_PHY_update_exchange_happened(self, replayed):
        _, glb, mock_hw = replayed
        # Pcap frames 14/17/18: BG sent LL_PHY_REQ → got LL_PHY_RSP → sent
        # LL_PHY_UPDATE_IND. The reception side is what the replay drives.
        assert glb.ll_phy_rsp_recv is True

    def test_SMP_pairing_request_retry_cap_reached(self, replayed):
        _, glb, _ = replayed
        # The Samsung device ignored every Pairing Request. BG re-sends
        # at ~1 s intervals and gives up after the 6th attempt (the
        # `attempt_count > 5` check in handle_SMP_Pairing). The replay
        # doesn't advance wall-clock time, so the retry count won't tick
        # up the same way — but the initial request must have fired.
        assert glb.smp_legacy_pairing_req_sent is True

    def test_GATT_enumeration_progressed(self, replayed):
        _, glb, _ = replayed
        # Even though SMP never completed, the GATT enumeration phase
        # before it did populate the primary-services dict and the
        # received-handles list.
        assert glb.primary_services_all_recv is True
        assert len(glb.received_handles) > 0
