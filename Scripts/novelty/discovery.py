"""Read-only HCI monitor: advertising reports and inquiry/EIR, never GATT/SDP.

Linux HCI_CHANNEL_MONITOR does not send HCI commands, claim a controller, or
change BlueZ discovery. Socket failures propagate instead of silently falling
back to cached Device1 properties. Wire layouts: bluez-5.66/lib/hci.h and
bluez-5.66/monitor/bt.h in this checkout.
"""
from dataclasses import dataclass
import socket
import ctypes
import os
import struct

from .rules import ad_frames


@dataclass(frozen=True)
class Report:
    address: str
    address_type: str
    transport: str
    rssi: int
    frames: tuple
    connectable: bool = True


def _address(raw):
    return ':'.join(f'{byte:02x}' for byte in raw[::-1])


def _rssi(value):
    return -80 if value == 127 else value - 256 if value > 127 else value


def parse_event(packet):
    """An HCI Event packet (no H4 prefix). Reject malformed report batches."""
    if len(packet) < 2 or len(packet) != packet[1] + 2:
        return []
    event, body = packet[0], packet[2:]
    reports = []
    if event == 0x3e and len(body) >= 2 and body[0] in (2, 0x0d):
        extended = body[0] == 0x0d
        offset = 2
        for _ in range(body[1]):
            size = 24 if extended else 9
            if offset + size > len(body):
                return []
            block = body[offset:]
            if extended:
                flags = int.from_bytes(block[:2], 'little')
                atype, addr, rssi, length = block[2], block[3:9], block[13], block[23]
                # Only complete reports; never concatenate unrelated advertising
                # sets or interpret truncated fragmented structures as evidence.
                complete = (flags >> 5) & 3 == 0
                # Bit 0 connectable, bit 2 directed, bit 3 scan response. A
                # directed advertisement only accepts its own peer, and a scan
                # response is evidence about a device its ADV_IND already
                # announced (see the legacy case), so neither admits a candidate.
                connectable = bool(flags & 1) and not flags & 0x0c
            else:
                flags, atype, addr, length = block[0], block[1], block[2:8], block[8]
                complete = flags in (0, 1, 2, 3, 4)
                # Only ADV_IND (0) invites a connection from us. ADV_DIRECT_IND
                # (1) targets another central, and a SCAN_RSP (4) also answers
                # for scannable-but-not-connectable ADV_SCAN_IND advertisers, so
                # it supplies evidence but never admits a candidate by itself.
                connectable = flags == 0
                if offset + size + length >= len(body):
                    return []
                rssi = body[offset + size + length]
            end = offset + size + length
            if end > len(body):
                return []
            if complete and atype in (0, 1, 2, 3):
                reports.append(Report(_address(addr), 'public' if atype in (0, 2) else 'random',
                                      'BLE', _rssi(rssi), ad_frames(body[offset+size:end]), connectable))
            offset = end + (0 if extended else 1)
        return reports if offset == len(body) else []
    if event in (0x02, 0x22, 0x2f) and body:
        count = body[0]
        if not count:
            return []
        size = (len(body) - 1) // count
        expected = {0x02: (14,), 0x22: (14, 15), 0x2f: (254,)}[event]
        if size not in expected or len(body) != 1 + count * size or (event == 0x2f and count != 1):
            return []
        for offset in range(1, len(body), size):
            block = body[offset:offset+size]
            rssi = _rssi(block[13 if event == 0x2f else size-1]) if event != 2 else -80
            frames = ad_frames(block[14:]) if event == 0x2f else ()
            reports.append(Report(_address(block[:6]), 'public', 'BTC', rssi, frames))
    # Remote Name Request Complete, command responses and ACL/GATT are ignored.
    return reports


def parse_monitor(packet, controller_index):
    if len(packet) < 6:
        return []
    opcode, index, length = struct.unpack_from('<HHH', packet)
    if opcode != 3 or index != controller_index or len(packet) != length + 6:
        return []
    return parse_event(packet[6:])


def _bind_monitor(monitor):
    # Debian's Python 3.11 HCI socket.bind accepts only (device,), silently
    # fixing the channel to RAW. Use Linux's sockaddr_hci directly so the
    # passive MONITOR channel works on that build as well as newer Python.
    address = struct.pack("@HHH", socket.AF_BLUETOOTH, 0xffff, 2)
    buffer = ctypes.create_string_buffer(address)
    libc = ctypes.CDLL(None, use_errno=True)
    bind = libc.bind
    bind.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    bind.restype = ctypes.c_int
    if bind(monitor.fileno(), buffer, len(address)) < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def open_monitor():
    monitor = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    try:
        monitor.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        _bind_monitor(monitor)
        monitor.setblocking(False)
        return monitor
    except BaseException:
        monitor.close()
        raise
