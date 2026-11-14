########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

# import os
# import re
# import TME.TME_glob
import struct
from TME.TME_helpers import *
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_SDP import *
from TME.TME_UUID128 import add_dashes_to_UUID128
from TME.TME_GATT import match_known_GATT_UUID_or_custom_UUID
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

from colorama import Fore, Back, Style, init
# bytes_to_hex_str / bytes_reversed_to_hex_str / bytes_to_utf8 actually live in
# TME.TME_helpers; importing them via scapy_to_BTIDES_common dragged scapy onto
# the analysis path, which broke `--input-BTIDES`-only runs on capture nodes
# whose venv doesn't ship scapy.
from TME.TME_helpers import bytes_to_hex_str, bytes_reversed_to_hex_str, bytes_to_utf8
init(autoreset=True)

# Returns True if there is any SDP info for this BDADDR, else False.
# SDP_Common is a BT Classic-only table (no bdaddr_random column) and its
# unique index has `bdaddr` as the leftmost-prefix column, so a plain
# `WHERE bdaddr = %s` is already indexed. The shared helper just narrows
# the SELECT to `1 ... LIMIT 1` for a covering-index existence probe.
def device_has_SDP_info(bdaddr):
    return (device_row_exists_by_bdaddr("SDP_Common", bdaddr)
            or device_row_exists_by_bdaddr("SDP_ERROR_RSP", bdaddr))

# Per spec "DATA ELEMENT SIZE DESCRIPTOR" section
data_element_size_to_actual_size = {
    0: 1,
    1: 2,
    2: 4,
    3: 8,
    4: 16
}

def _sdp_element_header(bv, i):
    """Return (type, payload size, payload start, end), validating all bounds."""
    if i >= len(bv):
        raise ValueError("missing SDP element descriptor")
    descriptor = bv[i]
    type_id, size_code = descriptor >> 3, descriptor & 7
    i += 1
    if type_id == 0:
        if size_code != 0:
            raise ValueError("invalid NIL element")
        size = 0
    elif size_code < 5:
        size = data_element_size_to_actual_size[size_code]
    else:
        width = {5: 1, 6: 2, 7: 4}[size_code]
        if i + width > len(bv):
            raise ValueError("truncated SDP length")
        size = int.from_bytes(bv[i:i + width], 'big')
        i += width
    if type_id in (1, 2) and size_code > 4:
        raise ValueError("invalid integer width")
    if type_id == 3 and size not in (2, 4, 16):
        raise ValueError("invalid UUID width")
    if type_id == 5 and size != 1:
        raise ValueError("invalid boolean width")
    if type_id in (4, 6, 7, 8) and size_code < 5:
        raise ValueError("invalid variable length element")
    if type_id > 8:
        raise ValueError("unknown SDP element type")
    end = i + size
    if end > len(bv):
        raise ValueError("truncated SDP element")
    return type_id, size, i, end


def parse_SDP_data_element(indent, byte_values, i, depth=0):
    """Print one complete element for verbose TME output without exiting on bad data."""
    try:
        if depth > 32:
            raise ValueError("SDP nesting too deep")
        type_id, size, start, end = _sdp_element_header(byte_values, i)
        value, parsed_end = _parse_sdp_elem_val(byte_values, i)
        if parsed_end != end:
            raise ValueError("incomplete SDP element")
        qprint(f"{indent}Size of element of type {type_id} is {size}")
        if type_id in (6, 7):
            qprint(f"{indent}Found {'sequence' if type_id == 6 else 'alternate'}:")
            j = start
            while j < end:
                _, _, _, new_j = parse_SDP_data_element(indent + i1, byte_values, j, depth + 1)
                if new_j <= j or new_j > end:
                    raise ValueError("invalid nested SDP element")
                j = new_j
        elif type_id == 0:
            qprint(f"{indent}Found NIL")
        elif type_id == 3:
            qprint(f"{indent}Found UUID: {_sdp_uuid_label(value)}")
        elif type_id == 4:
            qprint(f"{indent}Found string: {value}")
        elif type_id == 8:
            qprint(f"{indent}Found URL: {value}")
        elif type_id == 5:
            qprint(f"{indent}Found boolean: {value}")
        else:
            qprint(f"{indent}Found integer: {value:#x}")
        return type_id, size, byte_values[end:], end
    except ValueError as exc:
        qprint(f"{indent}Malformed SDP element: {exc}")
        return None, None, byte_values[i:], i


def print_SDP_Common(indent, direction, l2cap_len, l2cap_cid, transaction_id, param_len):
    if(direction == type_BTIDES_direction_C2P):
        qprint(f"{indent}Direction: Central to Peripheral")
    else:
        qprint(f"{indent}Direction: Peripheral to Central")

    qprint(f"{indent}l2cap_len: {l2cap_len}")
    qprint(f"{indent}l2cap_cid: {l2cap_cid}")
    qprint(f"{indent}transaction_id: 0x{transaction_id:04x}")
    qprint(f"{indent}param_len: 0x{param_len:04x}")

def print_SDP_SERVICE_SEARCH_REQ(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):
    if(pdu_id == type_SDP_SERVICE_SEARCH_REQ):
        qprint(f"{indent}SDP_SERVICE_SEARCH_REQ:")
    else:
        return
    qprint(f"{indent}raw bytes: {byte_values}")

    print_SDP_Common(f"{indent}{i1}", direction, l2cap_len, l2cap_cid, transaction_id, param_len)

    qprint(f"{indent}{i1}Parsed Raw Data:")
    raw_byte_len = len(byte_values)
    i = 0
    # ServiceSearchPattern
    (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}{i2}", byte_values, i)
    MaximumServiceRecordCount, = struct.unpack(">H", byte_values[i:i+2])
    i+=2
    qprint(f"{indent}{i2}MaximumServiceRecordCount: 0x{MaximumServiceRecordCount:04x}")
    # ContinuationState
    ContinuationState, = struct.unpack(">B", byte_values[i:i+1])
    i+=1
    qprint(f"{indent}{i2}ContinuationState: 0x{ContinuationState:02x}")

    if(ContinuationState > 0):
        ContinuationStateBytes, = byte_values[i:i+ContinuationState]
        qprint(f"{indent}{i2}ContinuationStateBytes: {ContinuationStateBytes}")


def print_SDP_SERVICE_SEARCH_ATTR_REQ(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):
    if(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_REQ):
        qprint(f"{indent}SDP_SERVICE_SEARCH_ATTR_REQ:")
    else:
        return
    qprint(f"{indent}raw bytes: {byte_values}")

    print_SDP_Common(f"{indent}{i1}", direction, l2cap_len, l2cap_cid, transaction_id, param_len)

    qprint(f"{indent}{i1}Parsed Raw Data:")
    raw_byte_len = len(byte_values)
    i = 0
    # ServiceSearchPattern
    (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}{i2}", byte_values, i)
    MaximumAttributeByteCount, = struct.unpack(">H", byte_values[i:i+2])
    i+=2
    qprint(f"{indent}{i2}MaximumAttributeByteCount: 0x{MaximumAttributeByteCount:04x}")
    # AttributeIDList
    while (i < raw_byte_len-1):
        (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}{i3}", byte_values, i)

    if(len(byte_values_new) == 1):
        ContinuationState, = struct.unpack(">B", byte_values_new)
        qprint(f"{indent}{i2}ContinuationState: 0x{ContinuationState:02x}")

def print_SDP_SERVICE_SEARCH_ATTR_RSP(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):
    if(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_RSP):
        qprint(f"{indent}SDP_SERVICE_SEARCH_ATTR_RSP:")
    else:
        return

    print_SDP_Common(f"{indent}{i1}", direction, l2cap_len, l2cap_cid, transaction_id, param_len)

    # print(f"raw bytes: {byte_values}")
    raw_byte_len = len(byte_values)
    AttributeListsByteCount, = struct.unpack(">H", byte_values[:2])
    # qprint(f"{indent}{i1}raw_byte_len: {raw_byte_len:04x}")
    qprint(f"{indent}{i1}Parsed Raw Data:")
    qprint(f"{indent}{i2}AttributeListsByteCount: 0x{AttributeListsByteCount:04x}")

    i = 2
    # Looping until raw_byte_len - 1 because the last byte will be the "Continuation State"
    while (i < raw_byte_len-1):
        (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}{i2}", byte_values, i)

    if(len(byte_values) == 1):
        ContinuationState, = struct.unpack(">B", byte_values)
        qprint(f"{i4}ContinuationState: 0x{ContinuationState:02x}")

    return

############################
# Structured value parser and terse display
############################

def _parse_sdp_elem_val(bv, i, depth=0):
    """Parse one bounded SDP element; raise ValueError for malformed input."""
    if depth > 32:
        raise ValueError("SDP nesting too deep")
    type_id, size, start, end = _sdp_element_header(bv, i)
    if type_id == 0:
        return None, end
    if type_id in (1, 2):
        return int.from_bytes(bv[start:end], 'big', signed=type_id == 2), end
    if type_id == 3:
        if size == 16:
            return ('uuid128', bv[start:end].hex()), end
        return (f'uuid{size * 8}', int.from_bytes(bv[start:end], 'big')), end
    if type_id in (4, 8):
        return bv[start:end].decode('utf-8', errors='replace'), end
    if type_id == 5:
        return bool(bv[start]), end
    items = []
    j = start
    while j < end:
        value, new_j = _parse_sdp_elem_val(bv, j, depth + 1)
        if new_j <= j or new_j > end:
            raise ValueError("SDP child exceeds enclosing element")
        items.append(value)
        j = new_j
    return items, end


def _sdp_uuid_label(uuid_tup):
    """Return a human-readable label for a UUID tuple from _parse_sdp_elem_val."""
    if not isinstance(uuid_tup, tuple):
        return str(uuid_tup)
    kind, val = uuid_tup
    if kind == 'uuid16':
        ustr = f"{val:04x}"
        if val in TME.TME_glob.SDP_protocol_identifiers:
            return f"{TME.TME_glob.SDP_protocol_identifiers[val]} (0x{ustr})"
        if val in TME.TME_glob.uuid16_service_names:
            return f"{TME.TME_glob.uuid16_service_names[val]} (0x{ustr})"
        name = match_known_GATT_UUID_or_custom_UUID(ustr)
        if name and name != ustr:
            return f"{name} (0x{ustr})"
        return f"0x{ustr}"
    elif kind == 'uuid32':
        return f"0x{val:08x}"
    elif kind == 'uuid128':
        dashed = add_dashes_to_UUID128(val)
        name = match_known_GATT_UUID_or_custom_UUID(dashed)
        if name and name != dashed:
            return f"{name} ({dashed})"
        return dashed
    return str(uuid_tup)


def _parse_sdp_record_dict(flat_list):
    """Convert a flat [attr_id, value, attr_id, value, ...] list into {attr_id: value}."""
    attrs = {}
    i = 0
    while i + 1 < len(flat_list):
        key = flat_list[i]
        if isinstance(key, int):
            attrs[key] = flat_list[i + 1]
        i += 2
    return attrs


def _parse_sdp_all_records(buf, single_record=False):
    """Parse complete ServiceAttribute or ServiceSearchAttribute data."""
    try:
        outer, end = _parse_sdp_elem_val(buf, 0)
        if end != len(buf) or not isinstance(outer, list):
            return []
        lists = [outer] if single_record else outer
        records = []
        for item in lists:
            if isinstance(item, list):
                record = _parse_sdp_record_dict(item)
                if record:
                    records.append(record)
        return records
    except ValueError:
        return []


def _fmt_sdp_version(v):
    return f"v{(v >> 8) & 0xFF}.{v & 0xFF}"


def _fmt_protocol_stack(pdl_val):
    """Format a ProtocolDescriptorList value as 'L2CAP → RFCOMM (ch 2)'."""
    if not isinstance(pdl_val, list):
        return ""
    layers = []
    for proto_seq in pdl_val:
        if not isinstance(proto_seq, list) or not proto_seq:
            continue
        proto_uuid = proto_seq[0]
        if not isinstance(proto_uuid, tuple):
            continue
        kind, val = proto_uuid
        if kind == 'uuid16':
            ustr = f"{val:04x}"
            name = TME.TME_glob.SDP_protocol_identifiers.get(val, f"0x{ustr}")
            params = proto_seq[1:]
            if params and isinstance(params[0], int):
                p = params[0]
                if val == 0x0003:    # RFCOMM — parameter is channel
                    name = f"{name} (ch {p})"
                elif val == 0x0100:  # L2CAP — parameter is PSM
                    name = f"{name} (PSM 0x{p:04x})"
                else:
                    name = f"{name} (0x{p:x})"
        else:
            name = _sdp_uuid_label(proto_uuid)
        layers.append(name)
    return " → ".join(layers)


def _terse_print_sdp_records(records):
    """Print a compact, human-readable summary of SDP service records."""
    if not records:
        return
    qprint(f"{i1}SDP Services:")
    for rec in records:
        handle   = rec.get(0x0000)
        name     = rec.get(0x0100)   # ServiceName (default language base offset)
        desc     = rec.get(0x0101)   # ServiceDescription
        classes  = rec.get(0x0001)   # ServiceClassIDList
        pdl      = rec.get(0x0004)   # ProtocolDescriptorList
        apdl     = rec.get(0x000D)   # AdditionalProtocolDescriptorLists
        profiles = rec.get(0x0009)   # BluetoothProfileDescriptorList

        handle_str = f"0x{handle:08x}" if isinstance(handle, int) else "?"
        name_str   = f' "{name}"'     if isinstance(name, str)    else ""
        qprint(f"{i2}Handle {handle_str}:{name_str}")

        if isinstance(classes, list):
            parts = [_sdp_uuid_label(u) for u in classes if isinstance(u, tuple)]
            if parts:
                qprint(f"{i3}Classes:  {', '.join(parts)}")

        if isinstance(pdl, list):
            ps = _fmt_protocol_stack(pdl)
            if ps:
                qprint(f"{i3}Protocol: {ps}")

        if isinstance(apdl, list):
            for extra in apdl:
                if isinstance(extra, list):
                    ps = _fmt_protocol_stack(extra)
                    if ps:
                        qprint(f"{i3}Alt Protocol: {ps}")

        if isinstance(profiles, list):
            parts = []
            for p in profiles:
                if isinstance(p, list) and len(p) >= 2:
                    uuid_val, ver = p[0], p[1]
                    if isinstance(uuid_val, tuple) and isinstance(ver, int):
                        parts.append(f"{_sdp_uuid_label(uuid_val)} {_fmt_sdp_version(ver)}")
            if parts:
                qprint(f"{i3}Profile:  {', '.join(parts)}")

        if isinstance(desc, str):
            qprint(f"{i3}Desc:     {desc}")


def _sdp_response_fragment(byte_values):
    """Return (attribute bytes, has continuation) for a complete response PDU."""
    if len(byte_values) < 3:
        return None
    count = int.from_bytes(byte_values[:2], 'big')
    end = 2 + count
    if end >= len(byte_values):
        return None
    continuation_len = byte_values[end]
    if end + 1 + continuation_len != len(byte_values):
        return None
    return byte_values[2:end], continuation_len != 0


def defrag_SDP_SERVICE_SEARCH_ATTR_RSP(indent, direction, l2cap_len, l2cap_cid,
                                        pdu_id, transaction_id, param_len, byte_values):
    """Compatibility helper for callers that inspect one response fragment."""
    parsed = _sdp_response_fragment(byte_values)
    if parsed is None:
        qprint(f"{indent}Malformed SDP response parameters")
        return b'', False
    return parsed


def _merge_sdp_records(records):
    """Coalesce attributes learned from repeated queries for the same handle."""
    merged = []
    by_handle = {}
    seen_without_handle = set()
    for record in sorted(records, key=lambda item: not isinstance(item.get(0x0000), int)):
        handle = record.get(0x0000)
        if isinstance(handle, int):
            if handle in by_handle:
                by_handle[handle].update(record)
            else:
                copy = record.copy()
                by_handle[handle] = copy
                merged.append(copy)
        else:
            # An AttributeIDList may omit ServiceRecordHandle. Match that
            # partial record to a full record only if the match is unique.
            matches = [existing for existing in merged
                       if isinstance(existing.get(0x0000), int)
                       and all(existing.get(key) == value
                               for key, value in record.items())]
            if len(matches) == 1:
                continue
            signature = repr(record)
            if signature not in seen_without_handle:
                merged.append(record)
                seen_without_handle.add(signature)
    return merged


def print_SDP_info(bdaddr):
    values = (bdaddr,)
    common_rows = execute_query(
        "SELECT direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, "
        "param_len, byte_values FROM SDP_Common WHERE bdaddr = %s ORDER BY id ASC",
        values,
    ) or []
    error_rows = execute_query(
        "SELECT direction, l2cap_len, l2cap_cid, transaction_id, param_len, "
        "error_code FROM SDP_ERROR_RSP WHERE bdaddr = %s ORDER BY id ASC",
        values,
    ) or []
    if not common_rows and not error_rows:
        vprint(f"{i1}No SDP data found.")
        return

    qprint(f"{i1}Service Discovery Protocol (SDP) data found:")
    for direction, l2cap_len, l2cap_cid, transaction_id, param_len, error_code in error_rows:
        data = ff_SDP_ERROR_RSP(direction, l2cap_len, l2cap_cid,
                                transaction_id, param_len, error_code)
        BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        qprint(f"{i2}SDP error response: 0x{error_code:04x}")

    records = []
    # Continuations belong to a response type and channel. Transaction IDs
    # change between continuation requests, so they cannot be used as the key.
    fragments = {}
    for direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values in common_rows:
        byte_values = bytes(byte_values)
        data = ff_SDP_Common(pdu_id, direction, l2cap_len, l2cap_cid,
                             transaction_id, param_len, byte_values.hex())
        BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        if pdu_id not in (type_SDP_SERVICE_ATTR_RSP, type_SDP_SERVICE_SEARCH_ATTR_RSP):
            continue
        key = (direction, l2cap_cid, pdu_id)
        parsed = _sdp_response_fragment(byte_values)
        if parsed is None:
            fragments.pop(key, None)
            vprint(f"{i2}Malformed SDP response on CID 0x{l2cap_cid:04x}")
            continue
        fragment, has_continuation = parsed
        fragments.setdefault(key, bytearray()).extend(fragment)
        if has_continuation:
            continue
        complete = bytes(fragments.pop(key))
        if TME.TME_glob.verbose_print:
            parse_SDP_data_element(i2, complete, 0)
        else:
            records.extend(_parse_sdp_all_records(
                complete, single_record=pdu_id == type_SDP_SERVICE_ATTR_RSP))

    if not TME.TME_glob.verbose_print:
        _terse_print_sdp_records(_merge_sdp_records(records))
    qprint("")
