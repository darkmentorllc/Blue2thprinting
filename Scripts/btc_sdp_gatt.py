########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

# btc_sdp_gatt.py
#
# Standalone tool that uses the BlueZ kernel L2CAP socket interface to perform
# SDP enumeration of a Bluetooth Classic (BR/EDR) device, and — if the SDP
# records indicate GATT support over BR/EDR — to also perform GATT enumeration.
# Both result sets are exported in BTIDES format under
# Logs/btc_sdp_gatt/sdp_<bdaddr>.btides and Logs/btc_sdp_gatt/gatt_<bdaddr>.btides
# (with the BDADDR dash-delimited rather than colon-delimited so the filenames
# are portable to filesystems that disallow ':').
#
# Aggregation: data observed within 5 minutes of an existing identical record
# is treated as a duplicate of that record (so the BTIDES file does not grow
# unbounded across re-runs against the same device). Identical data observed
# more than 5 minutes after the last existing copy is appended as a new entry
# with a new timestamp, so the file captures both "the same thing was still
# present at time T1" and "the same thing was again present at time T2".
#
# Issue: https://github.com/darkmentorllc/Blue2thprinting/issues/48

# Activate venv before any other imports
from handle_venv import activate_venv
activate_venv()

import argparse
import json
import os
import re
import socket
import struct
import sys
import time

# This script lives under Scripts/ but imports the TME package, which lives
# under Analysis/. Make Analysis/ importable regardless of CWD.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ANALYSIS_DIR = os.path.normpath(os.path.join(_HERE, "..", "Analysis"))
if _ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, _ANALYSIS_DIR)

import TME.TME_glob
from TME.TME_BTIDES_base import (
    write_BTIDES,
    rebuild_SingleBDADDR_index,
    ff_SingleBDADDR_base,
)
from TME.TME_BTIDES_SDP import ff_SDP_Common, ff_SDP_ERROR_RSP
from TME.TME_BTIDES_GATT import ff_GATT_Service, ff_GATT_Characteristic
from TME.BT_Data_Types import (
    type_SDP_ERROR_RSP,
    type_SDP_SERVICE_SEARCH_ATTR_REQ,
    type_SDP_SERVICE_SEARCH_ATTR_RSP,
    type_ATT_ERROR_RSP,
    type_ATT_EXCHANGE_MTU_REQ,
    type_ATT_READ_BY_TYPE_REQ,
    type_ATT_READ_BY_TYPE_RSP,
    type_ATT_READ_BY_GROUP_TYPE_REQ,
    type_ATT_READ_BY_GROUP_TYPE_RSP,
)
from TME.BTIDES_Data_Types import type_BTIDES_direction_C2P, type_BTIDES_direction_P2C
from TME.TME_helpers import qprint, bytes_to_hex_str

# SDP PSM and ATT PSM (Bluetooth assigned numbers).
SDP_PSM = 0x0001
ATT_PSM = 0x001F

# UUID16 for L2CAP. Used as the ServiceSearchPattern element to match every
# record (every SDP record has L2CAP somewhere in its protocol stack).
L2CAP_PROTOCOL_UUID16 = 0x0100
ATT_PROTOCOL_UUID16   = 0x0007  # ATT
GATT_SERVICE_UUID16   = 0x1801  # Generic Attribute Profile (the SDP record that
                                # advertises GATT-over-BR/EDR support)

# SDP attribute IDs we care about for GATT detection / display.
ATTR_SERVICE_RECORD_HANDLE       = 0x0000
ATTR_SERVICE_CLASS_ID_LIST       = 0x0001
ATTR_PROTOCOL_DESCRIPTOR_LIST    = 0x0004
ATTR_ADDITIONAL_PROTOCOL_LISTS   = 0x000D
ATTR_SERVICE_NAME                = 0x0100

AGGREGATION_WINDOW_SECONDS = 5 * 60


# ---------------------------------------------------------------------------
# BDADDR helpers
# ---------------------------------------------------------------------------

_BDADDR_RE = re.compile(r'^[0-9A-Fa-f]{2}([:\-][0-9A-Fa-f]{2}){5}$')

def normalize_bdaddr(s):
    """Return the BDADDR uppercased and colon-delimited, or raise ValueError."""
    if not _BDADDR_RE.match(s):
        raise ValueError(f"Invalid BDADDR: {s!r}")
    return s.replace('-', ':').upper()

def bdaddr_to_dash(bdaddr_colon):
    """Convert AA:BB:CC:DD:EE:FF -> AA-BB-CC-DD-EE-FF for use in filenames."""
    return bdaddr_colon.replace(':', '-')


# ---------------------------------------------------------------------------
# BlueZ L2CAP socket helpers (Linux only)
# ---------------------------------------------------------------------------

def _require_bluez():
    if not sys.platform.startswith('linux'):
        raise RuntimeError(
            "btc_sdp_gatt.py requires Linux with BlueZ; this platform "
            f"({sys.platform}) does not provide AF_BLUETOOTH sockets."
        )
    if not hasattr(socket, 'AF_BLUETOOTH') or not hasattr(socket, 'BTPROTO_L2CAP'):
        raise RuntimeError(
            "Python build lacks AF_BLUETOOTH/BTPROTO_L2CAP support. "
            "Install Python with Bluetooth socket support."
        )

def _open_l2cap(bdaddr_colon, psm, timeout):
    """Open an L2CAP connection-oriented socket to (bdaddr, psm)."""
    _require_bluez()
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    sock.settimeout(timeout)
    sock.connect((bdaddr_colon, psm))
    return sock


# ---------------------------------------------------------------------------
# SDP wire format helpers
# ---------------------------------------------------------------------------

def _sdp_header(pdu_id, transaction_id, params):
    return struct.pack(">BHH", pdu_id, transaction_id, len(params)) + params

def _build_service_search_attr_req(transaction_id,
                                   service_search_pattern_uuid16s,
                                   max_attr_byte_count,
                                   attribute_id_ranges,
                                   continuation_state):
    # ServiceSearchPattern: a Data Element Sequence of UUIDs (we use UUID16s only).
    ssp_inner = b''
    for uuid16 in service_search_pattern_uuid16s:
        # Type=3 (UUID), size index=1 (2 bytes) -> descriptor 0b00011001 = 0x19.
        ssp_inner += struct.pack(">BH", 0x19, uuid16)
    # Wrap in DES with 1-byte size.
    if len(ssp_inner) <= 0xFF:
        ssp = struct.pack(">BB", 0x35, len(ssp_inner)) + ssp_inner
    else:
        ssp = struct.pack(">BH", 0x36, len(ssp_inner)) + ssp_inner

    # AttributeIDList: a Data Element Sequence of either UINT16 (single attr) or
    # UINT32 (range, hi 16 bits = start, lo 16 bits = end).
    aid_inner = b''
    for entry in attribute_id_ranges:
        if isinstance(entry, tuple):
            start, end = entry
            packed = (start << 16) | end
            # Type=1 (UINT), size index=2 (4 bytes) -> 0b00001010 = 0x0A.
            aid_inner += struct.pack(">BI", 0x0A, packed)
        else:
            # Single attribute id as UINT16. Type=1, size index=1 -> 0x09.
            aid_inner += struct.pack(">BH", 0x09, entry)
    if len(aid_inner) <= 0xFF:
        aid = struct.pack(">BB", 0x35, len(aid_inner)) + aid_inner
    else:
        aid = struct.pack(">BH", 0x36, len(aid_inner)) + aid_inner

    cont = struct.pack(">B", len(continuation_state)) + continuation_state

    params = ssp + struct.pack(">H", max_attr_byte_count) + aid + cont
    return _sdp_header(type_SDP_SERVICE_SEARCH_ATTR_REQ, transaction_id, params)

def _parse_sdp_pdu_header(buf):
    if len(buf) < 5:
        raise ValueError("Short SDP PDU header")
    pdu_id, tid, plen = struct.unpack(">BHH", buf[:5])
    return pdu_id, tid, plen, buf[5:]


# ---------------------------------------------------------------------------
# SDP data element parser (returns Python values + records GATT detection clues)
# ---------------------------------------------------------------------------

# Implemented locally rather than importing TME.TME_SDP._parse_sdp_elem_val
# because that helper lives in a module that pulls in MySQL bindings on import,
# which we don't want as a hard dependency for this standalone tool.

def _parse_sdp_value(bv, i):
    """Parse one SDP data element at bv[i]; return (value, new_i).

    Values: int for integer, ('uuid16'|'uuid32'|'uuid128', val) for UUIDs,
    str for text/URL, bool for boolean, list for sequence/alternate, None for nil.
    """
    if i >= len(bv):
        return None, i
    descriptor = bv[i]; i += 1
    type_id   = (descriptor >> 3) & 0x1F
    size_code =  descriptor       & 0x07
    if   size_code == 0: size = 1
    elif size_code == 1: size = 2
    elif size_code == 2: size = 4
    elif size_code == 3: size = 8
    elif size_code == 4: size = 16
    elif size_code == 5:
        size = bv[i]; i += 1
    elif size_code == 6:
        size, = struct.unpack('>H', bv[i:i+2]); i += 2
    else:
        size, = struct.unpack('>I', bv[i:i+4]); i += 4
    end = i + size
    if type_id == 0:
        return None, end
    if type_id in (1, 2):
        signed = (type_id == 2)
        return int.from_bytes(bv[i:end], 'big', signed=signed), end
    if type_id == 3:
        if size == 2:  return ('uuid16',  struct.unpack('>H', bv[i:i+2])[0]), end
        if size == 4:  return ('uuid32',  struct.unpack('>I', bv[i:i+4])[0]), end
        if size == 16: return ('uuid128', bv[i:i+16].hex()), end
        return None, end
    if type_id in (4, 8):
        return bv[i:end].decode('utf-8', errors='replace'), end
    if type_id == 5:
        return (bv[i] != 0), end
    if type_id in (6, 7):
        items, j = [], i
        while j < end:
            v, j = _parse_sdp_value(bv, j)
            items.append(v)
        return items, end
    return None, end

def _parse_sdp_attribute_lists(buf):
    """Parse a reassembled AttributeLists payload into [{attr_id: value}, ...]."""
    records = []
    i = 0
    while i < len(buf):
        outer, i = _parse_sdp_value(buf, i)
        if isinstance(outer, list):
            for inner in outer:
                if isinstance(inner, list):
                    records.append(_flatten_attr_pairs(inner))
    return records

def _flatten_attr_pairs(flat):
    out = {}
    j = 0
    while j + 1 < len(flat):
        k = flat[j]
        if isinstance(k, int):
            out[k] = flat[j + 1]
        j += 2
    return out


# ---------------------------------------------------------------------------
# SDP browse: send SDP_SERVICE_SEARCH_ATTR_REQ, capture every PDU exchanged.
# ---------------------------------------------------------------------------

def sdp_browse(bdaddr_colon, timeout=10.0, max_attr_byte_count=4096):
    """Run SDP_SERVICE_SEARCH_ATTR against the device.

    Returns (pdus, parsed_records) where:
        pdus: list of dicts, each describing one SDP PDU we sent or received
              (suitable for direct insertion into BTIDES SDPArray).
        parsed_records: list of attribute-id->value dicts, one per service
              record returned (used for terse display + GATT detection).
    """
    pdus = []
    sock = _open_l2cap(bdaddr_colon, SDP_PSM, timeout)
    try:
        # Get the actual L2CAP MTU for the connection so we can populate the
        # l2cap_len field in BTIDES entries with realistic numbers.
        try:
            opt = sock.getsockopt(socket.SOL_BLUETOOTH, 0x0D, 7)  # BT_RCVMTU not portable
            l2cap_mtu = struct.unpack("<H", opt[:2])[0] if opt else 672
        except Exception:
            l2cap_mtu = 672

        transaction_id = 1
        continuation = b''
        reassembly = b''

        while True:
            req = _build_service_search_attr_req(
                transaction_id,
                [L2CAP_PROTOCOL_UUID16],
                max_attr_byte_count,
                [(0x0000, 0xFFFF)],
                continuation,
            )
            now_ms = int(time.time() * 1000)
            sock.send(req)
            pdus.append(_make_pdu_dict(req, type_BTIDES_direction_C2P, l2cap_mtu, now_ms))

            buf = sock.recv(65535)
            now_ms = int(time.time() * 1000)
            pdu_id, tid, plen, params = _parse_sdp_pdu_header(buf)
            pdus.append(_make_pdu_dict(buf, type_BTIDES_direction_P2C, l2cap_mtu, now_ms))

            if pdu_id == type_SDP_ERROR_RSP:
                break
            if pdu_id != type_SDP_SERVICE_SEARCH_ATTR_RSP:
                # Unexpected; record it in pdus and stop.
                break

            # Parse SDP_SERVICE_SEARCH_ATTR_RSP body.
            attr_bytes_count, = struct.unpack(">H", params[:2])
            fragment = params[2:2 + attr_bytes_count]
            reassembly += fragment
            cont_idx = 2 + attr_bytes_count
            cont_len = params[cont_idx]
            continuation = params[cont_idx + 1:cont_idx + 1 + cont_len]
            transaction_id += 1
            if cont_len == 0:
                break
    finally:
        try:
            sock.close()
        except Exception:
            pass

    parsed = _parse_sdp_attribute_lists(reassembly) if reassembly else []
    return pdus, parsed


def _make_pdu_dict(raw_pdu, direction, l2cap_mtu, unix_time_milli):
    """Convert raw bytes for one SDP PDU into a BTIDES SDPArray entry.

    Following the convention used elsewhere in this codebase (see
    insert_std_optional_fields in TME_BTIDES_base.py and the GPS exporter),
    `time` is placed directly on the entry rather than under a wrapper.
    """
    pdu_id, tid, plen = struct.unpack(">BHH", raw_pdu[:5])
    body = raw_pdu[5:5 + plen]
    raw_data_hex_str = bytes_to_hex_str(body)
    if pdu_id == type_SDP_ERROR_RSP:
        error_code = struct.unpack(">H", body[:2])[0] if len(body) >= 2 else 0
        entry = ff_SDP_ERROR_RSP(direction, l2cap_mtu, 0x0040, tid, plen, error_code)
    else:
        entry = ff_SDP_Common(pdu_id, direction, l2cap_mtu, 0x0040, tid, plen, raw_data_hex_str)
    entry["time"] = {"unix_time_milli": unix_time_milli}
    return entry


# ---------------------------------------------------------------------------
# GATT-over-BR/EDR detection
# ---------------------------------------------------------------------------

def detect_gatt_support(parsed_records):
    """Return True iff any SDP record advertises GATT over BR/EDR.

    GATT is advertised either by:
      * Service Class ID 0x1801 (Generic Attribute), OR
      * Protocol Descriptor List containing the ATT protocol UUID (0x0007),
        usually wrapped over L2CAP at PSM 0x001F.
    """
    for rec in parsed_records:
        classes = rec.get(ATTR_SERVICE_CLASS_ID_LIST)
        if isinstance(classes, list):
            for u in classes:
                if isinstance(u, tuple) and u[0] == 'uuid16' and u[1] == GATT_SERVICE_UUID16:
                    return True
        for pdl_attr in (ATTR_PROTOCOL_DESCRIPTOR_LIST, ATTR_ADDITIONAL_PROTOCOL_LISTS):
            pdl = rec.get(pdl_attr)
            if not isinstance(pdl, list):
                continue
            stacks = pdl if pdl_attr == ATTR_ADDITIONAL_PROTOCOL_LISTS else [pdl]
            for stack in stacks:
                if not isinstance(stack, list):
                    continue
                for layer in stack:
                    if not isinstance(layer, list) or not layer:
                        continue
                    head = layer[0]
                    if isinstance(head, tuple) and head[0] == 'uuid16' and head[1] == ATT_PROTOCOL_UUID16:
                        return True
    return False


# ---------------------------------------------------------------------------
# ATT-over-BR/EDR GATT enumeration
# ---------------------------------------------------------------------------

def gatt_browse_btc(bdaddr_colon, timeout=10.0):
    """Enumerate GATT services & characteristics over BR/EDR (PSM 0x001F).

    Returns a list of service dicts (as ff_GATT_Service shape), each with an
    embedded "characteristics" list. Returns [] on any connection failure.
    """
    try:
        sock = _open_l2cap(bdaddr_colon, ATT_PSM, timeout)
    except OSError as e:
        qprint(f"  GATT-over-BR/EDR connect to PSM 0x{ATT_PSM:04x} failed: {e}")
        return []

    services = []
    try:
        # MTU exchange; nice to have, ignore the response details — we only need
        # ATT default-MTU (23) semantics for the enumeration to succeed.
        try:
            sock.send(struct.pack("<BH", type_ATT_EXCHANGE_MTU_REQ, 517))
            sock.recv(512)
        except (socket.timeout, OSError):
            pass

        # Discover primary services via ATT_READ_BY_GROUP_TYPE_REQ for 0x2800.
        services = _att_read_by_group_type_loop(sock, 0x2800, "2800")

        # For each service, enumerate characteristics.
        for svc in services:
            chars = _att_read_by_type_characteristics(
                sock, svc["begin_handle"], svc["end_handle"],
            )
            if chars:
                svc["characteristics"] = chars
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return services


def _att_read_by_group_type_loop(sock, group_uuid16, utype_str):
    """Walk ATT_READ_BY_GROUP_TYPE for one group UUID; return service entries."""
    out = []
    start = 0x0001
    while start <= 0xFFFF:
        req = struct.pack("<BHHH", type_ATT_READ_BY_GROUP_TYPE_REQ, start, 0xFFFF, group_uuid16)
        try:
            sock.send(req)
            rsp = sock.recv(512)
        except (socket.timeout, OSError):
            break
        if not rsp:
            break
        opcode = rsp[0]
        if opcode == type_ATT_ERROR_RSP:
            break
        if opcode != type_ATT_READ_BY_GROUP_TYPE_RSP or len(rsp) < 2:
            break
        entry_len = rsp[1]
        body = rsp[2:]
        last_end = 0
        for off in range(0, len(body), entry_len):
            entry = body[off:off + entry_len]
            if len(entry) < entry_len:
                break
            begin, end = struct.unpack("<HH", entry[:4])
            uuid_bytes = entry[4:]
            if len(uuid_bytes) == 2:
                uuid_str = f"{struct.unpack('<H', uuid_bytes)[0]:04x}"
            elif len(uuid_bytes) == 16:
                uuid_str = uuid_bytes[::-1].hex()
            else:
                uuid_str = uuid_bytes.hex()
            svc = ff_GATT_Service({
                "utype": utype_str,
                "begin_handle": begin,
                "end_handle": end,
                "UUID": uuid_str,
            })
            out.append(svc)
            last_end = end
        if last_end == 0xFFFF or last_end == 0:
            break
        start = last_end + 1
    return out


def _att_read_by_type_characteristics(sock, begin, end):
    """Walk ATT_READ_BY_TYPE for 0x2803 within a single service's handle range."""
    out = []
    start = begin
    while start <= end:
        req = struct.pack("<BHHH", type_ATT_READ_BY_TYPE_REQ, start, end, 0x2803)
        try:
            sock.send(req)
            rsp = sock.recv(512)
        except (socket.timeout, OSError):
            break
        if not rsp or rsp[0] == type_ATT_ERROR_RSP:
            break
        if rsp[0] != type_ATT_READ_BY_TYPE_RSP or len(rsp) < 2:
            break
        entry_len = rsp[1]
        body = rsp[2:]
        last_handle = 0
        for off in range(0, len(body), entry_len):
            entry = body[off:off + entry_len]
            if len(entry) < entry_len:
                break
            handle, properties, value_handle = struct.unpack("<HBH", entry[:5])
            uuid_bytes = entry[5:]
            if len(uuid_bytes) == 2:
                value_uuid = f"{struct.unpack('<H', uuid_bytes)[0]:04x}"
            elif len(uuid_bytes) == 16:
                value_uuid = uuid_bytes[::-1].hex()
            else:
                value_uuid = uuid_bytes.hex()
            char = ff_GATT_Characteristic({
                "handle": handle,
                "properties": properties,
                "value_handle": value_handle,
                "value_uuid": value_uuid,
            })
            out.append(char)
            last_handle = handle
        if last_handle == 0 or last_handle == end:
            break
        start = last_handle + 1
    return out


# ---------------------------------------------------------------------------
# 5-minute aggregation BTIDES write helpers
# ---------------------------------------------------------------------------

_OPTIONAL_KEYS = frozenset({"time", "RSSI", "channel_freq", "src_file", "std_optional_fields"})

def _entry_time_ms(entry):
    if not isinstance(entry, dict):
        return None
    # Prefer the flat-key form used elsewhere in this codebase. Fall back to a
    # nested "std_optional_fields" wrapper for forward-compat with files that
    # might be produced by other tools that follow the schema literally.
    candidates = [entry.get("time")]
    sof = entry.get("std_optional_fields")
    if isinstance(sof, dict):
        candidates.append(sof.get("time"))
        if "unix_time_milli" in sof or "unix_time" in sof:
            candidates.append(sof)
    for t in candidates:
        if not isinstance(t, dict):
            continue
        if "unix_time_milli" in t:
            return int(t["unix_time_milli"])
        if "unix_time" in t:
            return int(t["unix_time"]) * 1000
    return None

def _eq_ignore_optional(a, b):
    """Equality between SDP entries that ignores all std_optional_fields."""
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return a == b
    keys_a = set(a.keys()) - _OPTIONAL_KEYS
    keys_b = set(b.keys()) - _OPTIONAL_KEYS
    if keys_a != keys_b:
        return False
    for k in keys_a:
        if a[k] != b[k]:
            return False
    return True

def _aggregate_sdp_into_existing(existing_sdp_array, new_entries, window_ms):
    """Merge new_entries into existing_sdp_array, applying 5-min dedup.

    For each new entry: if there is an existing entry with identical primitive
    fields whose timestamp is within window_ms, do nothing (treat as a duplicate
    observation). Otherwise append the new entry as-is.
    """
    appended = 0
    for ne in new_entries:
        ne_t = _entry_time_ms(ne)
        skip = False
        for ee in existing_sdp_array:
            if not _eq_ignore_optional(ee, ne):
                continue
            ee_t = _entry_time_ms(ee)
            if ne_t is None or ee_t is None:
                # No timestamp on one side → treat as exact duplicate.
                skip = True
                break
            if abs(ne_t - ee_t) <= window_ms:
                skip = True
                break
        if not skip:
            existing_sdp_array.append(ne)
            appended += 1
    return appended


def _aggregate_gatt_into_existing(existing_gatt_array, new_services):
    """Merge new GATT services into existing_gatt_array, deduping by handle range.

    GATT service / characteristic / descriptor objects do not carry per-record
    timestamps in the BTIDES schema, so a 5-minute window is not meaningful at
    that granularity. We treat the file as a "current snapshot": if a service
    with the same (utype, begin_handle, end_handle, UUID) already exists, merge
    its characteristics; otherwise append the new service.
    """
    appended_services = 0
    appended_chars = 0
    for ns in new_services:
        match = None
        for es in existing_gatt_array:
            if (es.get("utype") == ns.get("utype")
                    and es.get("begin_handle") == ns.get("begin_handle")
                    and es.get("end_handle") == ns.get("end_handle")
                    and es.get("UUID") == ns.get("UUID")):
                match = es
                break
        if match is None:
            existing_gatt_array.append(ns)
            appended_services += 1
            appended_chars += len(ns.get("characteristics") or [])
            continue
        # Merge characteristics by handle.
        existing_chars = match.setdefault("characteristics", [])
        for nc in ns.get("characteristics", []):
            if any(ec.get("handle") == nc.get("handle") for ec in existing_chars):
                continue
            existing_chars.append(nc)
            appended_chars += 1
    return appended_services, appended_chars


def _load_existing_btides(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if not isinstance(data, list):
            qprint(f"Warning: existing file {path} is not a BTIDES list; overwriting.")
            return []
        return data
    except Exception as e:
        qprint(f"Warning: could not parse existing file {path} ({e}); overwriting.")
        return []


def write_sdp_btides(out_path, bdaddr_colon, sdp_pdu_entries):
    """Persist SDP entries to per-device BTIDES file with 5-min aggregation."""
    existing = _load_existing_btides(out_path)
    base = None
    for item in existing:
        if isinstance(item, dict) and item.get("bdaddr", "").upper() == bdaddr_colon:
            base = item
            break
    if base is None:
        base = ff_SingleBDADDR_base(bdaddr_colon, 0)
        existing.append(base)
    sdp_array = base.setdefault("SDPArray", [])
    appended = _aggregate_sdp_into_existing(
        sdp_array, sdp_pdu_entries, AGGREGATION_WINDOW_SECONDS * 1000,
    )

    TME.TME_glob.BTIDES_JSON = existing
    rebuild_SingleBDADDR_index()
    write_BTIDES(out_path)
    qprint(f"  Wrote {len(sdp_pdu_entries)} SDP PDUs ({appended} new) -> {out_path}")


def write_gatt_btides(out_path, bdaddr_colon, gatt_services):
    """Persist GATT services to per-device BTIDES file with snapshot merge."""
    existing = _load_existing_btides(out_path)
    base = None
    for item in existing:
        if isinstance(item, dict) and item.get("bdaddr", "").upper() == bdaddr_colon:
            base = item
            break
    if base is None:
        base = ff_SingleBDADDR_base(bdaddr_colon, 0)
        existing.append(base)
    gatt_array = base.setdefault("GATTArray", [])
    new_svcs, new_chars = _aggregate_gatt_into_existing(gatt_array, gatt_services)

    TME.TME_glob.BTIDES_JSON = existing
    rebuild_SingleBDADDR_index()
    write_BTIDES(out_path)
    qprint(f"  Wrote GATT snapshot ({new_svcs} new svc, {new_chars} new chars) -> {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _default_output_dir():
    # Resolve relative to the repository root rather than CWD so the tool works
    # the same regardless of where it's invoked from.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "Logs", "btc_sdp_gatt"))


def main():
    parser = argparse.ArgumentParser(
        description=("Standalone SDP enumerator for BT Classic devices, with "
                     "automatic GATT-over-BR/EDR enumeration when the SDP "
                     "records indicate GATT support. Uses BlueZ kernel L2CAP "
                     "sockets directly (Linux only)."),
    )
    parser.add_argument('--bdaddr', type=str, required=True,
                        help='Target BT Classic BDADDR (AA:BB:CC:DD:EE:FF or with dashes).')
    parser.add_argument('--timeout', type=float, default=10.0,
                        help='L2CAP receive timeout in seconds (default: 10).')
    parser.add_argument('--output-dir', type=str, default=None,
                        help=('Override output directory (default: '
                              '<repo>/Logs/btc_sdp_gatt).'))
    parser.add_argument('--no-gatt', action='store_true',
                        help='Skip GATT enumeration even if SDP indicates GATT support.')
    parser.add_argument('--force-gatt', action='store_true',
                        help='Attempt GATT enumeration even if SDP did not indicate support.')

    printout_group = parser.add_argument_group('Print verbosity arguments')
    printout_group.add_argument('--verbose-print', action='store_true',
                                help='Show explicit data-not-found output and per-PDU details.')
    printout_group.add_argument('--verbose-BTIDES', action='store_true',
                                help='Include optional human-readable fields in BTIDES output.')
    printout_group.add_argument('--quiet-print', action='store_true',
                                help='Hide all print output.')

    args = parser.parse_args()

    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES
    TME.TME_glob.quiet_print = args.quiet_print

    try:
        bdaddr = normalize_bdaddr(args.bdaddr)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    out_dir = args.output_dir or _default_output_dir()
    os.makedirs(out_dir, exist_ok=True)
    sdp_path  = os.path.join(out_dir, f"sdp_{bdaddr_to_dash(bdaddr)}.btides")
    gatt_path = os.path.join(out_dir, f"gatt_{bdaddr_to_dash(bdaddr)}.btides")

    qprint(f"Connecting to {bdaddr} for SDP browse...")
    try:
        pdus, records = sdp_browse(bdaddr, timeout=args.timeout)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: SDP connect/transfer failed: {e}", file=sys.stderr)
        return 1

    qprint(f"  SDP exchange complete: {len(pdus)} PDUs, {len(records)} service records.")
    write_sdp_btides(sdp_path, bdaddr, pdus)

    gatt_supported = detect_gatt_support(records)
    qprint(f"  GATT-over-BR/EDR indicated by SDP: {gatt_supported}")

    if args.no_gatt:
        qprint("  --no-gatt set; skipping GATT enumeration.")
        return 0
    if not gatt_supported and not args.force_gatt:
        qprint("  Skipping GATT enumeration (SDP did not indicate GATT support; "
               "use --force-gatt to try anyway).")
        return 0

    qprint(f"Connecting to {bdaddr} on PSM 0x{ATT_PSM:04x} for GATT enumeration...")
    services = gatt_browse_btc(bdaddr, timeout=args.timeout)
    if not services:
        qprint("  GATT enumeration produced no services.")
        return 0
    qprint(f"  GATT enumeration complete: {len(services)} services, "
           f"{sum(len(s.get('characteristics') or []) for s in services)} characteristics.")
    write_gatt_btides(gatt_path, bdaddr, services)
    return 0


if __name__ == "__main__":
    sys.exit(main())
