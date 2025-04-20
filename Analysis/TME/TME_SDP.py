########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#import os
import re
import struct
import TME.TME_glob
from TME.TME_helpers import *
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_SDP import *
from TME.TME_UUID128 import add_dashes_to_UUID128
from TME.TME_GATT import match_known_GATT_UUID_or_custom_UUID

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
        print(f"{indent}Error: i is greater than the length of the byte_values array. Aborting")
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
    print(f"{indent}Size of element of type {data_element_type} is {actual_size}")
    if(data_element_type == 1):
        if(actual_size == 1):
            integer_1b, = struct.unpack(">B", byte_values[i:i+1])
            i+=actual_size
            print(f"{indent}Found integer: 0x{integer_1b:02x}")
        elif(actual_size == 2):
            integer_2b, = struct.unpack(">H", byte_values[i:i+2])
            i+=actual_size
            if(integer_2b in TME.TME_glob.SDP_universal_attribute_names.keys()):
                print(f"{indent}Found integer: 0x{integer_2b:04x} ({TME.TME_glob.SDP_universal_attribute_names[integer_2b]})")
            else:
                print(f"{indent}Found integer: 0x{integer_2b:04x}")
        elif(actual_size == 4):
            integer_4b, = struct.unpack(">I", byte_values[i:i+4])
            i+=actual_size
            print(f"{indent}Found integer: 0x{integer_4b:08x}")
        elif(actual_size == 8):
            integer_8b, = struct.unpack(">Q", byte_values[i:i+8])
            i+=actual_size
            print(f"{indent}Found integer: 0x{integer_8b:16x}")
        elif(actual_size == 16):
            high_bytes, low_bytes = struct.unpack(">QQ", byte_values[i:i+16])
            integer_16b = (high_bytes << 64) | low_bytes
            i+=actual_size
            print(f"{indent}Found integer: 0x{integer_16b:32x}")
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
            print(f"{indent}Found UUID16: 0x{UUID_str} ({UUID_name})")
        elif(actual_size == 4):
            UUID32 = bytes_to_hex_str(byte_values[i:i+4])
            i+=actual_size
            UUID_str = f"{UUID32:08x}"
            UUID_name = match_known_GATT_UUID_or_custom_UUID(UUID_str)
            print(f"{indent}Found UUID32: 0x{UUID_str} ({UUID_name})")
        elif(actual_size == 16):
            UUID128 = bytes_to_hex_str(byte_values[i:i+16])
            i+=actual_size
            UUID_str = add_dashes_to_UUID128(UUID128)
            UUID_name = match_known_GATT_UUID_or_custom_UUID(UUID_str)
            print(f"{indent}Found UUID128: 0x{UUID_str} ({UUID_name})")
    elif(data_element_type == 4):
        string = bytes_to_utf8(byte_values[i:i+actual_size])
        i+=actual_size
        print(f"{indent}Found string: {string}")
    elif(data_element_type == 5):
        boolean = struct.unpack(">B", byte_values[i:i+1])
        i+=actual_size
        print(f"{indent}Found boolean: {"True" if boolean else "False"}")
    elif(data_element_type == 8):
        URL = bytes_to_utf8(byte_values[i:i+actual_size])
        i+=actual_size
        print(f"{indent}Found URL: {URL}")

    # If the data element is a sequence, recursively parse until we find normal data?
    elif(data_element_type == 6):
        j = 0
        while(j < actual_size):
            i_before = i
            data_element_type, inner_actual_size, byte_values_new, new_i = parse_SDP_data_element(indent + "\t", byte_values, i)
            # move i and j forward by however many bytes were iterated
            diff = new_i - i_before
            if(diff == 0):
                print(f"{indent}Error: no bytes were iterated. Exiting.")
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
    print(f"raw bytes: {byte_values}")

    print_SDP_Common(f"{indent}\t", direction, l2cap_len, l2cap_cid, transaction_id, param_len)

    qprint(f"{indent}\tParsed Raw Data:")
    raw_byte_len = len(byte_values)
    i = 0
    # ServiceSearchPattern
    (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}\t\t", byte_values, i)
    MaximumServiceRecordCount, = struct.unpack(">H", byte_values[i:i+2])
    i+=2
    qprint(f"{indent}\t\tMaximumServiceRecordCount: 0x{MaximumServiceRecordCount:04x}")
    # ContinuationState
    ContinuationState, = struct.unpack(">B", byte_values[i:i+1])
    i+=1
    qprint(f"{indent}\t\tContinuationState: 0x{ContinuationState:02x}")

    if(ContinuationState > 0):
        ContinuationStateBytes, = byte_values[i:i+ContinuationState]
        qprint(f"{indent}\t\tContinuationStateBytes: {ContinuationStateBytes}")


def print_SDP_SERVICE_SEARCH_ATTR_REQ(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):
    if(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_REQ):
        qprint(f"{indent}SDP_SERVICE_SEARCH_ATTR_REQ:")
    else:
        return
    print(f"raw bytes: {byte_values}")

    print_SDP_Common(f"{indent}\t", direction, l2cap_len, l2cap_cid, transaction_id, param_len)

    qprint(f"{indent}\tParsed Raw Data:")
    raw_byte_len = len(byte_values)
    i = 0
    # ServiceSearchPattern
    (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}\t\t", byte_values, i)
    MaximumAttributeByteCount, = struct.unpack(">H", byte_values[i:i+2])
    i+=2
    qprint(f"{indent}\t\tMaximumAttributeByteCount: 0x{MaximumAttributeByteCount:04x}")
    # AttributeIDList
    while (i < raw_byte_len-1):
        (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}\t\t\t", byte_values, i)

    if(len(byte_values_new) == 1):
        ContinuationState, = struct.unpack(">B", byte_values_new)
        qprint(f"{indent}\t\tContinuationState: 0x{ContinuationState:02x}")

def print_SDP_SERVICE_SEARCH_ATTR_RSP(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):
    if(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_RSP):
        qprint(f"{indent}SDP_SERVICE_SEARCH_ATTR_RSP:")
    else:
        return

    print_SDP_Common(f"{indent}\t", direction, l2cap_len, l2cap_cid, transaction_id, param_len)

    # print(f"raw bytes: {byte_values}")
    raw_byte_len = len(byte_values)
    AttributeListsByteCount, = struct.unpack(">H", byte_values[:2])
    # qprint(f"{indent}\traw_byte_len: {raw_byte_len:04x}")
    qprint(f"{indent}\tParsed Raw Data:")
    qprint(f"{indent}\t\tAttributeListsByteCount: 0x{AttributeListsByteCount:04x}")

    i = 2
    # Looping until raw_byte_len - 1 because the last byte will be the "Continuation State"
    while (i < raw_byte_len-1):
        (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}\t\t", byte_values, i)

    if(len(byte_values) == 1):
        ContinuationState, = struct.unpack(">B", byte_values)
        qprint(f"\t\t\t\tContinuationState: 0x{ContinuationState:02x}")

    return

def defrag_SDP_SERVICE_SEARCH_ATTR_RSP(indent, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values):

    raw_byte_len = len(byte_values)
    AttributeListsByteCount, = struct.unpack(">H", byte_values[:2])
    #vprint(f"AttributeListsByteCount: 0x{AttributeListsByteCount:04x}")
    fragment_bytes = byte_values[2:2+AttributeListsByteCount]

    i = 2+AttributeListsByteCount
    # Looping until AttributeListsByteCount because that's all the nested data
    # while (i < AttributeListsByteCount):
    #     (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"{indent}\t\t", byte_values, i)

    ContinuationState, = struct.unpack(">B", byte_values[i:i+1])
    i+=1
    #qprint(f"{indent}\t\tContinuationState: 0x{ContinuationState:02x}")

    ContinuationStateBytes = 0
    if(ContinuationState > 0):
        ContinuationStateBytes = byte_values[i:i+ContinuationState]
        #qprint(f"{indent}\t\tContinuationStateBytes: {ContinuationStateBytes}")

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
        qprint("\tService Discovery Protocol (SDP) data found:")
    else:
        vprint("\tNo SDP data found.")
        return

    for direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values in SDP_result:
        raw_data_hex_str = bytes_to_hex_str(byte_values)
        # First export BTIDES
        if(pdu_id == type_SDP_SERVICE_SEARCH_REQ):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_REQ, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            print_SDP_SERVICE_SEARCH_REQ("\t\t", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
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
            print_SDP_SERVICE_SEARCH_ATTR_REQ("\t\t", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
        elif(pdu_id == type_SDP_SERVICE_SEARCH_ATTR_RSP):
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            print_SDP_SERVICE_SEARCH_ATTR_RSP("\t\t", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)

    reassembly_buffer = b''
    for direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values in SDP_result2:
        byte_size = len(byte_values)
        i = 0
        AttributeListsByteCount, = struct.unpack(">H", byte_values[:2])
        i+=2
        try:
            fragment_bytes = byte_values[2:2+AttributeListsByteCount]
            reassembly_buffer += fragment_bytes
            i+=AttributeListsByteCount
            if(i > byte_size):
                print("Error: i is greater than the length of the byte_values array. Aborting.")
                break
            ContinuationState, = struct.unpack(">B", byte_values[i:i+1])
        except Exception as e:
            print(f"Possible out of bounds access: {e}. Aborting")
            break

        if(ContinuationState):
            continue
        else:
            # Export first
            raw_data_hex_str = bytes_to_hex_str(reassembly_buffer)
            data = ff_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_RSP, direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str)
            BTIDES_export_SDP_packet(bdaddr=bdaddr, random=0, data=data)
            # Then parse
            # print_SDP_SERVICE_SEARCH_ATTR_RSP("\t\t", direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, reassembly_buffer)
            i = 0
            while (i < len(reassembly_buffer)):
                (data_element_type, actual_size, byte_values_new, i) = parse_SDP_data_element(f"\t\t", reassembly_buffer, i)

    qprint("")
