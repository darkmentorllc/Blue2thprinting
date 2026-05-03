########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Minimal HCI log file reader: BTSnoop (UART/H4 + Linux Monitor) and Apple PacketLogger.

Replaces the vendored ``btsnoop`` package; we only need ``parse(path)`` returning
records with ``.data`` (raw H4-formatted bytes scapy's ``HCI_Hdr`` can parse) and
``.flags`` (direction: 0=ACL host->controller, 1=ACL controller->host,
2=command, 3=event).

References:
    bluez/src/shared/btsnoop.h  (file format)
    https://tools.ietf.org/html/rfc1761  (snoop v2)
    Apple PacketLogger format adapted from regnirof/hciparse.
"""

import dataclasses
import datetime
import struct
import typing


_BTSNOOP_FORMAT_UART    = 1002  # H4 UART
_BTSNOOP_FORMAT_MONITOR = 2001  # Linux btmon

# btmon opcode -> (h4_packet_type, h4_flags). h4_packet_type is prepended to
# the data so the result looks like a UART/H4 frame; h4_flags replaces the
# record flags so downstream direction checks (==0 means C2P) still work.
_BTMON_TO_H4 = {
    2: (1, 2),  # COMMAND_PKT  -> CMD,    flags=2
    3: (4, 3),  # EVENT_PKT    -> EVT,    flags=3
    4: (2, 0),  # ACL_TX_PKT   -> ACL,    flags=0
    5: (2, 1),  # ACL_RX_PKT   -> ACL,    flags=1
    6: (3, 0),  # SCO_TX_PKT   -> SCO,    flags=0
    7: (3, 1),  # SCO_RX_PKT   -> SCO,    flags=1
}

# 0x00E03AB44A676000 microseconds = midnight 2000-01-01 in BTSnoop's epoch
# (microseconds since 0 AD), used to convert to a normal datetime.
_USECS_BETWEEN_0_AND_2000_AD = 0x00E03AB44A676000


@dataclasses.dataclass
class HCILogRecord:
    seq: int
    length: int
    flags: int
    drops: typing.Optional[int]
    ts: datetime.datetime
    data: bytes


def parse(filename, verbose=False):
    """Parse a BTSnoop or Apple PacketLogger file. Returns a list of HCILogRecord."""
    with open(filename, "rb") as f:
        ident = f.read(8)
        if ident == b"btsnoop\x00":
            version, data_link_type = struct.unpack(">II", f.read(8))
            if version != 1 or data_link_type not in (_BTSNOOP_FORMAT_UART, _BTSNOOP_FORMAT_MONITOR):
                raise ValueError(f"Unsupported BTSnoop file: version={version} type={data_link_type}")
            return list(_read_btsnoop_records(f, data_link_type))
        # Apple PacketLogger has no file header. v1 = byte[1]==0x00, v2 = byte[1]==0x01.
        if ident[0] == 0x00 and ident[1] in (0x00, 0x01):
            pklg_v2 = (ident[1] == 0x01)
            f.seek(0)
            return list(_read_packetlogger_records(f, pklg_v2))
        raise ValueError(f"Not a BTSnoop or Apple PacketLogger file: ident={ident!r}")


def _read_btsnoop_records(f, fmt):
    seq = 1
    while True:
        hdr = f.read(24)
        if len(hdr) != 24:
            return  # EOF
        orig_len, inc_len, flags, drops, time64 = struct.unpack(">IIIIq", hdr)
        if inc_len == 0 or time64 == 0:
            continue  # skip known-invalid truncated entries
        data = f.read(inc_len)
        if len(data) != inc_len:
            return  # truncated file

        if fmt == _BTSNOOP_FORMAT_MONITOR:
            # Strip the adapter index from the high 16 bits, look up the opcode.
            translated = _BTMON_TO_H4.get(flags & 0xFFFF)
            if translated is None:
                continue  # unsupported monitor opcode (e.g. NEW_INDEX, SYSTEM_NOTE)
            h4_type, flags = translated
            data = bytes([h4_type]) + data

        ts = datetime.datetime(2000, 1, 1) + datetime.timedelta(microseconds=time64 - _USECS_BETWEEN_0_AND_2000_AD)
        yield HCILogRecord(seq=seq, length=inc_len, flags=flags, drops=drops, ts=ts, data=data)
        seq += 1


# Apple PacketLogger packet types -> (btsnoop-style flags, H4 packet type byte)
_PKLG_TO_BTSNOOP = {
    0x00: (0x02, 0x01),  # CMD
    0x01: (0x03, 0x04),  # EVT
    0x02: (0x00, 0x02),  # ACL TX
    0x03: (0x01, 0x02),  # ACL RX
}


def _read_packetlogger_records(f, pklg_v2):
    seq = 1
    fmt = "<IqB" if pklg_v2 else ">IqB"
    while True:
        hdr = f.read(13)
        if len(hdr) != 13:
            return
        length, timestamp, pkt_type = struct.unpack(fmt, hdr)
        data = f.read(length - 9)  # length includes the 9 bytes after itself
        translated = _PKLG_TO_BTSNOOP.get(pkt_type)
        if translated is None:
            continue
        flags, h4_type = translated
        data = bytes([h4_type]) + data
        secs = timestamp >> 32
        usecs = timestamp & 0xFFFFFFFF
        ts = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=secs, microseconds=usecs)
        yield HCILogRecord(seq=seq, length=length, flags=flags, drops=None, ts=ts, data=data)
        seq += 1
