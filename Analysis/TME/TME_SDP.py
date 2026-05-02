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
from scapy_to_BTIDES_common import bytes_to_hex_str, bytes_reversed_to_hex_str, bytes_to_utf8
init(autoreset=True)

# Returns 0 if there is no SDP info for this BDADDR in any of the SDP tables, else returns 1
def device_has_SDP_info(bdaddr):
    # Query the database for all GATT services
    values = (bdaddr,)
    query = "SELECT bdaddr FROM SDP_Common WHERE bdaddr = %s";
    SDP_result = execute_query(query, values)
    if(len(SDP_result) != 0):
        return 1;

    return 0;

# Per spec "DATA ELEMENT SIZE DESCRIPTOR" section
data_element_size_to_actual_size = {
    0: 1,
    1: 2,
    2: 4,
    3: 8,
    4: 16
}

def parse_SDP_data_element(indent, byte_values, i):
    if i+1 > len(byte_values):
        qprint(f"{indent}Error: i is greater than the length of the byte_values array. Aborting")
        return None, None, byte_values, i  # Return gracefully if out of bounds (probable truncation)
    data_element, = struct.unpack(">B", byte_values[i:i+1])
    i+=1
    data_element_type = (data_element >> 3) & 0x1F # 5 bits for type
    data_element_size = (data_element) & 0x7 # 3 bits for size
    if(data_element_size < 5):
        actual_size = data_element_size_to_actual_size[data_element_size]
    elif(data_element_size == 5):
        actual_size, = struct.unpack(">B", byte_values[i:i+1])
        i+=1
    elif(data_element_size == 6):
        actual_size, = struct.unpack(">H", byte_values[i:i+2])
        i+=2
    elif(data_element_size == 7):
        actual_size, = struct.unpack(">I", byte_values[i:i+4])
        i+=4
    qprint(f"{indent}Size of element of type {data_element_type} is {actual_size}")
    if(data_element_type == 1):
        if(actual_size == 1):
            integer_1b, = struct.unpack(">B", byte_values[i:i+1])
            i+=actual_size
            qprint(f"{indent}Found integer: 0x{integer_1b:02x}")
        elif(actual_size == 2):
            integer_2b, = struct.unpack(">H", byte_values[i:i+2])
            i+=actual_size
            if(integer_2b in TME.TME_glob.SDP_universal_attribute_names.keys()):
                qprint(f"{indent}Found integer: 0x{integer_2b:04x} ({TME.TME_glob.SDP_universal_attribute_names[integer_2b]})")
            else:
                qprint(f"{indent}Found integer: 0x{integer_2b:04x}")
        elif(actual_size == 4):
            integer_4b, = struct.unpack(">I", byte_values[i:i+4])
            i+=actual_size
            qprint(f"{indent}Found integer: 0x{integer_4b:08x}")
        elif(actual_size == 8):
            integer_8b, = struct.unpack(">Q", byte_values[i:i+8])
            i+=actual_size
            qprint(f"{indent}Found integer: 0x{integer_8b:16x}")
        elif(actual_size == 16):
            high_bytes, low_bytes = struct.unpack(">QQ", byte_values[i:i+16])
            integer_16b = (high_bytes << 64) | low_bytes
            i+=actual_size
            qprint(f"{indent}Found integer: 0x{integer_16b:32x}")
    elif(data_element_type == 3):
        if(actual_size == 2):
            UUID16, = struct.unpack(">H", byte_values[i:i+2])
            i+=actual_size
            UUID_str = f"{UUID16:04x}"
            # TODO: need to make this smarter so that it knows it's inside a type 0x0004 (ProtocolDescriptorList)
            if(UUID16 in TME.TME_glob.SDP_protocol_identifiers.keys()):
                UUID_name = TME.TME_glob.SDP_protocol_identifiers[UUID16]
            elif(UUID16 in TME.TME_glob.uuid16_service_names.keys()):
                UUID_name = TME.TME_glob.uuid16_service_names[UUID16]
            else:
                UUID_name = match_known_GATT_UUID_or_custom_UUID(UUID_str)
            qprint(f"{indent}Found UUID16: 0x{UUID_str} ({UUID_name})")
        elif(actual_size == 4):
            UUID32 = bytes_to_hex_str(byte_values[i:i+4])
            i+=actual_size
            UUID_str = f"{UUID32:08x}"
            UUID_name = match_known_GATT_UUID_or_custom_UUID(UUID_str)
            qprint(f"{indent}Found UUID32: 0x{UUID_str} ({UUID_name})")
        elif(actual_size == 16):
            UUID128 = bytes_to_hex_str(byte_values[i:i+16])
            i+=actual_size
            UUID_str = add_dashes_to_UUID128(UUID128)
            UUID_name = match_known_GATT_UUID_or_custom_UUID(UUID_str)
            qprint(f"{indent}Found UUID128: 0x{UUID_str} ({UUID_name})")
    elif(data_element_type == 4):
        string = bytes_to_utf8(byte_values[i:i+actual_size])
        i+=actual_size
        qprint(f"{indent}Found string: {string}")
    elif(data_element_type == 5):
        boolean = struct.unpack(">B", byte_values[i:i+1])
        i+=actual_size
        qprint(f"{indent}Found boolean: {"True" if boolean else "False"}")
    elif(data_element_type == 8):
        URL = bytes_to_utf8(byte_values[i:i+actual_size])
        i+=actual_size
        qprint(f"{indent}Found URL: {URL}")

    # If the data element is a sequence, recursively parse until we find normal data?
    elif(data_element_type == 6):
        j = 0
        while(j < actual_size):
            i_before = i
            data_element_type, inner_actual_size, byte_values_new, new_i = parse_SDP_data_element(indent + f"{i1}", byte_values, i)
            # move i and j forward by however many bytes were iterated
            diff = new_i - i_before
            if(diff == 0):
                qprint(f"{indent}Error: no bytes were iterated. Exiting.")
                break
            j+= diff
            i = new_i
    elif(data_element_type == 7):
        # FIXME: handle this type now that you have a sample!
        exit(-1)
    elif(data_element_type == 0):
        # FIXME: handle this type now that you maybe have a sample! (Or possibly your parser's broken...)
        exit(-1)
    elif(data_element_type == 2):
        # FIXME: handle this type now that you have a sample!
        exit(-1)
    else:
        # FIXME: invalid type, probably an error in the code
        exit(-1)

    return data_element_type, actual_size, byte_values[i:], i


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

def _parse_sdp_elem_val(bv, i):
    """Parse one SDP data element at bv[i]; return (python_value, new_i).

    Values: int for integers, (kind, val) tuples for UUIDs where kind is
    'uuid16'/'uuid32'/'uuid128', str for text/URL, bool for boolean,
    list for sequence/alternate, None for nil.
    Returns (None, i) on any error.
    """
    if i >= len(bv):
        return None, i
    descriptor = bv[i]; i += 1
    type_id   = (descriptor >> 3) & 0x1F
    size_code =  descriptor       & 0x07
    try:
        if size_code < 5:
            size = data_element_size_to_actual_size[size_code]
        elif size_code == 5:
            size = bv[i]; i += 1
        elif size_code == 6:
            size, = struct.unpack('>H', bv[i:i+2]); i += 2
        else:
            size, = struct.unpack('>I', bv[i:i+4]); i += 4
        end = i + size
        if type_id == 0:
            return None, end
        elif type_id in (1, 2):
            signed = (type_id == 2)
            val = int.from_bytes(bv[i:end], 'big', signed=signed)
            return val, end
        elif type_id == 3:
            if size == 2:
                return ('uuid16',  struct.unpack('>H',  bv[i:i+2])[0]), end
            elif size == 4:
                return ('uuid32',  struct.unpack('>I',  bv[i:i+4])[0]), end
            elif size == 16:
                return ('uuid128', bv[i:i+16].hex()), end
        elif type_id in (4, 8):
            return bv[i:end].decode('utf-8', errors='replace'), end
        elif type_id == 5:
            return bool(bv[i]), end
        elif type_id in (6, 7):
            items, j = [], i
            while j < end:
                v, j = _parse_sdp_elem_val(bv, j)
                items.append(v)
            return items, end
    except Exception:
        pass
    return None, i + size if 'size' in dir() else (None, i)


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


def _parse_sdp_all_records(buf):
    """Parse a reassembled AttributeLists buffer into a list of record attribute dicts.

    buf starts at the outer sequence element (type byte included).
    """
    records = []
    i = 0
    while i < len(buf):
        outer_val, i = _parse_sdp_elem_val(buf, i)
        if isinstance(outer_val, list):
            for inner in outer_val:
                if isinstance(inner, list):
                    records.append(_parse_sdp_record_dict(inner))
    return records


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


def defrag_SDP_SERVICE_SEARCH_ATTR_RSP(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):

    raw_byte_len = len(byte_values)
    AttributeListsByteCount, = struct.unpack(">H", byte_values[:2])
    #vprint(f"AttributeListsByteCount: 0x{AttributeListsByteCount:04x}")
    fragment_bytes = byte_values[2:2+AttributeListsByteCount]

    i = 2+AttributeListsByteCount
    # Looping until AttributeListsByteCount because that's all the nested data
    # while (i < AttributeListsByteCount):
    #     (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}{i2}", byte_values, i)

    ContinuationState, = struct.unpack(">B", byte_values[i:i+1])
    i+=1
    #qprint(f"{indent}{i2}}ContinuationState: 0x{ContinuationState:02x}")

    ContinuationStateBytes = 0
    if(ContinuationState > 0):
        ContinuationStateBytes = byte_values[i:i+ContinuationState]
        #qprint(f"{indent}{i2}ContinuationStateBytes: {ContinuationStateBytes}")

    return fragment_bytes, True

def print_SDP_info(bdaddr):
    # Query the database for all SDP data
    values = (bdaddr,)
    # This is the query which hopefully has no fragments...
    query = "SELECT direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values FROM SDP_Common WHERE bdaddr = %s and pdu_id != 7";
    SDP_result = execute_query(query, values)
    # This query will most likely have fragments that need to be reassembled
    query = "SELECT direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values FROM SDP_Common WHERE bdaddr = %s and pdu_id = 7 order by transaction_id asc";
    SDP_result2 = execute_query(query, values)

    # Now print what we want users to see
    if (SDP_result or SDP_result2):
        qprint(f"{i1}Service Discovery Protocol (SDP) data found:")
    else:
        vprint(f"{i1}No SDP data found.")
        return

    # Records collected for the terse view (populated from pdu_id=5 and pdu_id=7).
    terse_records = []

    for direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values in SDP_result:
        raw_data_hex_str = bytes_to_hex_str(byte_values)
        # First export BTIDES
        if(pdu_id == type_SDP_SERVICE_SEARCH_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            #print_SDP_SERVICE_SEARCH_REQ(f"{i2}", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
        elif(pdu_id == type_SDP_SERVICE_SEARCH_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        elif(pdu_id == type_SDP_SERVICE_ATTR_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_ATTR_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        elif(pdu_id == type_SDP_SERVICE_ATTR_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_ATTR_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            # Collect one service record for the terse view
            try:
                cnt = struct.unpack('>H', byte_values[:2])[0]
                attr_list_bytes = byte_values[2:2+cnt]
                inner_val, _ = _parse_sdp_elem_val(attr_list_bytes, 0)
                if isinstance(inner_val, list):
                    terse_records.append(_parse_sdp_record_dict(inner_val))
            except Exception:
                pass
        elif(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            #print_SDP_SERVICE_SEARCH_ATTR_REQ(f"{i2}", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
        elif(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            #print_SDP_SERVICE_SEARCH_ATTR_RSP(f"{i2}", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)

        # FIXME: We aren't handling the case where the PDU isn't fragmented currently

    reassembly_buffer = b''
    for direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values in SDP_result2:
        # First export BTIDES
        raw_data_hex_str = bytes_to_hex_str(byte_values)
        if(pdu_id == type_SDP_SERVICE_SEARCH_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            #print_SDP_SERVICE_SEARCH_REQ(f"{i2}", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
        elif(pdu_id == type_SDP_SERVICE_SEARCH_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        elif(pdu_id == type_SDP_SERVICE_ATTR_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_ATTR_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        elif(pdu_id == type_SDP_SERVICE_ATTR_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_ATTR_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
        elif(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            #print_SDP_SERVICE_SEARCH_ATTR_REQ(f"{i2}", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
        elif(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            #print_SDP_SERVICE_SEARCH_ATTR_RSP(f"{i2}", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)

        byte_size = len(byte_values)
        i = 0
        AttributeListsByteCount, = struct.unpack(">H", byte_values[:2])
        i+=2

        try:
            fragment_bytes = byte_values[2:2+AttributeListsByteCount]
            reassembly_buffer += fragment_bytes
            i+=AttributeListsByteCount
            if(i > byte_size):
                qprint(f"{i2}Error: i is greater than the length of the byte_values array. Aborting.")
                break
            ContinuationState, = struct.unpack(">B", byte_values[i:i+1])
        except Exception as e:
            qprint(f"{i2}Possible out of bounds access: {e}. Aborting")
            break

        if(ContinuationState):
            continue
        else:
            if TME.TME_glob.verbose_print:
                # Verbose form: raw data-element dump (current behaviour)
                i = 0
                while (i < len(reassembly_buffer)):
                    (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{i2}", reassembly_buffer, i)
            else:
                # Terse form: collect structured records for display below
                terse_records.extend(_parse_sdp_all_records(reassembly_buffer))

    if not TME.TME_glob.verbose_print:
        _terse_print_sdp_records(terse_records)

    qprint("")
