########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Pytest fixtures for the Better_Getter test suite.

The BG codebase predates package layout — it does bare `import globals` and
`from BG_Helper_All import *` assuming `Scripts/BG/` is on `sys.path`. The
session-scoped path hook below mirrors how Better_Getter.py itself is run.

`clean_globals` reloads `globals.py` between tests so module-level state
(connection counters, pending-packet flags, the `current_ll_ctrl_state`
instance) starts each test in its declared-default state.

`mock_hw` swaps a recording stub in for `globals.hw` so the helpers'
`write_outbound_pkt()` / `cmd_transmit()` calls capture bytes to memory
instead of touching a real serial port.
"""

import importlib
import sys
from pathlib import Path

import pytest

BG_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Mirror Better_Getter.py's working directory expectation.
if str(BG_DIR) not in sys.path:
    sys.path.insert(0, str(BG_DIR))


@pytest.fixture
def clean_globals():
    """Reload Scripts/BG/globals.py to reset all module-level state.

    Yields the freshly-reloaded module so tests can read/write attributes
    directly. Also re-applies any module-cached references to the new
    `current_ll_ctrl_state` instance.
    """
    import globals as g
    importlib.reload(g)
    yield g
    # No teardown needed — the next test reloads again.


class _MockDecoderState:
    """Stand-in for sniffle.decoder_state.SniffleDecoderState. The BG
    write_outbound_pkt() helper subtracts `first_epoch_time` to produce a
    relative timestamp; tests don't care about that value, so just hand back
    a fixed float."""

    def __init__(self):
        self.first_epoch_time = 0.0
        self.cur_aa = 0


class MockHW:
    """In-memory stand-in for sniffle.sniffle_hw.SniffleHW.

    Records every `cmd_transmit(llid, body)` call so tests can assert that
    a helper produced the expected LL Control / L2CAP / ATT / SMP bytes
    without needing a real Sonoff/XDS110/CatSniffer dongle attached.
    """

    def __init__(self):
        self.transmitted = []   # list[(llid, bytes)]
        self.mac_calls = []     # list[(bdaddr_bytes, is_random)]
        self.intervals_preloaded = False
        self.next_aa = 0x63980B2E
        self.decoder_state = _MockDecoderState()

    # API surface used by Better_Getter.main() and the BG_Helper_* modules:
    def cmd_transmit(self, llid, body):
        self.transmitted.append((llid, bytes(body)))

    def cmd_chan_aa_phy(self, chan, aa, phy):
        pass

    def cmd_pause_done(self, flag):
        pass

    def cmd_follow(self, flag):
        pass

    def cmd_rssi(self):
        pass

    def cmd_tx_power(self, db):
        pass

    def cmd_auxadv(self, flag):
        pass

    def cmd_mac(self, bdaddr_bytes, is_random):
        self.mac_calls.append((tuple(bdaddr_bytes), is_random))

    def cmd_interval_preload(self):
        self.intervals_preloaded = True

    def mark_and_flush(self):
        pass

    def random_addr(self):
        return [0xC0, 0x5F, 0xB6, 0xCF, 0x70, 0xFB]

    def initiate_conn(self, bdaddr_bytes, is_random, interval=7, latency=0, timeout=50):
        return self.next_aa


@pytest.fixture
def mock_hw(clean_globals):
    """Replace `globals.hw` with a MockHW that records cmd_transmit calls."""
    hw = MockHW()
    clean_globals.hw = hw
    return hw


class MockDpkt:
    """Minimal stand-in for sniffle.packet_decoder.DataMessage / DPacketMessage.

    The BG helpers only read `.body` (raw LL PDU bytes) for ATT/L2CAP/SMP
    processing, plus `.phy`, `.event`, `.data_length`, `.pdutype`, and
    `.adv_data` for a few specific branches. Construct one with just the
    body bytes for most tests; pass extra kwargs to exercise the adv-data
    Apple-detection branch in Better_Getter.apple_advertisement().
    """

    def __init__(self, body=b"", phy=0x00, event=0, pdutype=None, adv_data=b""):
        self.body = bytes(body)
        self.phy = phy
        self.event = event
        self.pdutype = pdutype
        self.adv_data = bytes(adv_data)
        self.data_length = max(0, len(self.body) - 2)


@pytest.fixture
def make_dpkt():
    """Factory for MockDpkt — convenience so tests read `make_dpkt(body=...)`
    instead of importing the class."""
    return MockDpkt


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def cafe_pcap_path(fixtures_dir):
    return fixtures_dir / "cafe_capture.pcap"


@pytest.fixture(scope="session")
def public_pcap_path(fixtures_dir):
    return fixtures_dir / "public_bdaddr_capture.pcap"


@pytest.fixture(scope="session")
def apple_pcap_path(fixtures_dir):
    """6 real Apple (Company ID 0x004C) ADV_IND frames sliced from a NYC
    sniff capture
    (NYC_Day1/sniffle/2026-05-06-11-25-07_ttyUSB1_follow_ch38_pi4-2.pcap)
    — the input for the -A / skip-apple advertisement-detection tests.

    Provenance note: this comes from a NYC field capture, NOT a live sniff
    at the maintainer's home, so it carries no risk of revealing a home
    location regardless of the (rotating, in practice) Apple addresses it
    contains."""
    return fixtures_dir / "apple_advertisements.pcap"


def build_ll_ctrl_body(opcode, payload=b""):
    """Build a wire-format LL Control PDU body that the BG helpers parse.

    The helpers `unpack("<BBB...", dpkt.body[:N])` expect:
        byte 0: LL header (LLID + flags); use 0x03 (LLID=0b11 = LL ctrl)
        byte 1: LL length (PDU payload length, excluding header)
        byte 2: LL control opcode
        bytes 3..: opcode-specific payload
    """
    header = 0x03   # LLID = 0b11 (control PDU)
    length = 1 + len(payload)  # opcode + payload
    return bytes([header, length, opcode]) + bytes(payload)


def build_l2cap_body(cid, payload):
    """Build an L2CAP-over-LL body the BG helpers parse.

        byte 0: LL header (LLID=0b10 = start of L2CAP) → 0x02
        byte 1: LL length
        bytes 2-3: L2CAP length (little-endian)
        bytes 4-5: L2CAP CID (little-endian) — 0x0004 ATT, 0x0005 signal, 0x0006 SMP
        bytes 6..: L2CAP payload (e.g. ATT opcode + args)
    """
    header = 0x02
    l2cap_len = len(payload)
    body = bytes([header, 0, l2cap_len & 0xFF, (l2cap_len >> 8) & 0xFF,
                  cid & 0xFF, (cid >> 8) & 0xFF]) + bytes(payload)
    # Fix up the LL length byte (everything after header/length).
    body = bytes([header, len(body) - 2]) + body[2:]
    return body


@pytest.fixture
def ll_ctrl_body():
    return build_ll_ctrl_body


@pytest.fixture
def l2cap_body():
    return build_l2cap_body
