# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

import globals
from BG_Helper_All import *
from BG_Helper_Output import *

opcode_ATT_ERROR_RSP = 0x01
opcode_ATT_EXCHANGE_MTU_REQ = 0x02
opcode_ATT_EXCHANGE_MTU_RSP = 0x03
opcode_ATT_FIND_INFORMATION_REQ = 0x04
opcode_ATT_FIND_INFORMATION_RSP = 0x05
opcode_ATT_FIND_BY_TYPE_VALUE_REQ = 0x06
opcode_ATT_FIND_BY_TYPE_VALUE_RSP = 0x07
opcode_ATT_READ_BY_TYPE_REQ = 0x08
opcode_ATT_READ_BY_TYPE_RSP = 0x09
opcode_ATT_READ_REQ = 0x0A
opcode_ATT_READ_RSP = 0x0B
opcode_ATT_READ_BY_GROUP_TYPE_REQ = 0x10
opcode_ATT_READ_BY_GROUP_TYPE_RSP = 0x11

# Error codes that I expect to encounter
errorcode_01_ATT_Invalid_Handle = 0x01
errorcode_02_ATT_Read_Not_Permitted = 0x02
errorcode_05_ATT_Insufficient_Authentication = 0x05
errorcode_08_ATT_Insufficient_Authorization = 0x08
errorcode_10_ATT_Unsupported_Group_Type = 0x10
errorcode_0A_ATT_Attribute_Not_Found = 0x0A
errorcode_0C_ATT_Encryption_Key_Size_Too_Short = 0x0C
errorcode_0E_ATT_Unlikely_Error = 0x0E
errorcode_0F_ATT_Insufficient_Encryption = 0x0F
errorcode_10_ATT_Unsupported_Group_Type = 0x10

def send_ATT_ERROR_RSP(request_opcode, handle_in_error, error_code):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0007 (1 byte opcode + 2 byte begin handle + 2 byte end handle + 2 byte group type)
    # CID = 0x0004 (ATT)
    # Opcode = 0x01 (Error Response - ATT_ERROR_RSP)
    # Request Opcode in Error = request_opcode
    # Handle in error = handle_in_error
    # Error code = error_code
    payload_bytes = v1b(opcode_ATT_ERROR_RSP) + v1b(request_opcode) + v2b(handle_in_error) + v1b(error_code)
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"Sent ATT_ERROR_RSP of type 0x{error_code:02x} due to Request Opcode 0x{request_opcode:02x}")

# Send this to hopefully make the other side send back more responses per packet (so we have less back and forth)
def send_ATT_EXCHANGE_MTU_REQ(client_rx_mtu):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0003
    # CID = 0x0004 (ATT)
    # Opcode = 0x02 (Exchange MTU request)
    # Client Rx MTU = client_rx_mtu (typically set to 0x00f7 (247) - common seeming max value seen by others)
    payload_bytes = v1b(opcode_ATT_EXCHANGE_MTU_REQ) + v2b(client_rx_mtu)
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"ATT Exchange MTU sent with ClientRxMTU = 0x{client_rx_mtu:04x}")

def send_ATT_EXCHANGE_MTU_RSP(server_rx_mtu):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0003
    # CID = 0x0004 (ATT)
    # Opcode = 0x03 (Exchange MTU response)
    # Server Rx MTU = server_rx_mtu (typically set to 0x00f7 (247) - common seeming max value seen by others)
    payload_bytes = v1b(opcode_ATT_EXCHANGE_MTU_RSP) + v2b(server_rx_mtu)
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"ATT Exchange MTU sent with ClientRxMTU = 0x{server_rx_mtu:04x}")

def send_ATT_READ_BY_GROUP_TYPE_REQ(begin_handle, group_type):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0007 (1 byte opcode + 2 byte begin handle + 2 byte end handle + 2 byte group type)
    # CID = 0x0004 (ATT)
    # Opcode = 0x10 (Read by group type request - ATT_READ_BY_GROUP_TYPE_REQ)
    # Starting handle = begin_handle (e.g. 0x0001)
    # Ending handle = 0xFFFF
    payload_bytes = v1b(opcode_ATT_READ_BY_GROUP_TYPE_REQ) + v2b(begin_handle) + b'\xff\xff' + v2b(group_type)
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"Read by group type request for handles 0x{begin_handle:04x}-0xffff and type 0x{group_type:04x}")

def send_ATT_READ_BY_TYPE_REQ(begin_handle, end_handle, type):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0007 (1 byte opcode + 2 byte begin handle + 2 byte end handle + 2 byte group type)
    # CID = 0x0004 (ATT)
    # Opcode = 0x08 (Read by type request - opcode_ATT_READ_BY_TYPE_REQ)
    # Starting handle = begin_handle (e.g. 0x0001)
    # Ending handle = end_handle (e.g. 0xFFFF)
    # Type UUID - e.g. 0x2803 for Characteristics
    payload_bytes = v1b(opcode_ATT_READ_BY_TYPE_REQ) + v2b(begin_handle) + v2b(end_handle) + v2b(type)
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"Read by type request for handles 0x{begin_handle:04x}-0x{end_handle:04x} and type 0x{type:04x}")

def send_ATT_FIND_INFORMATION_REQ(begin_handle):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0005 (1 byte opcode + 2 byte begin handle + 2 byte end handle)
    # CID = 0x0004 (ATT)
    # Opcode = 0x04 (Find information request - ATT_FIND_INFORMATION_REQ)
    # Starting handle = begin_handle (e.g. 0x0001)
    # Ending handle = 0xFFFF
    payload_bytes = v1b(opcode_ATT_FIND_INFORMATION_REQ) + begin_handle.to_bytes(2, byteorder='little') + b'\xff\xff'
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"Sent find info request for handles 0x{begin_handle:04x}-0xffff!")

def send_ATT_READ_REQ(begin_handle):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0003 (1 byte opcode + 2 byte handle)
    # CID = 0x0004 (ATT)
    # Opcode = 0x0A (Read request - ATT_READ_REQ)
    # Handle = begin_handle (e.g. 0x0001)
    payload_bytes = v1b(opcode_ATT_READ_REQ) + begin_handle.to_bytes(2, byteorder='little')
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)
    vprint(f"Sent read request for handle 0x{begin_handle:04x}")

def send_ATT_FIND_BY_TYPE_VALUE_REQ_0x2A29_Apple():
    # LLID = 2 (L2CAP w/o fragmentation)
    # CID = 0x0004 (ATT)
    # Opcode = 0x06 (Read request - ATT_FIND_BY_TYPE_VALUE_REQ)
    # Starting Handle = 0x0001
    # Ending Handle = 0xFFFF
    # Attribute Type = 0x2A29
    # Attribute Value = "Apple Inc." (0x41, 0x70, 0x70, 0x6C, 0x65, 0x20, 0x49, 0x6E, 0x63, 0x2E)
    payload_bytes = v1b(opcode_ATT_FIND_BY_TYPE_VALUE_REQ) + b'\x01\x00' + b'\xff\xff' + b'\x29\x2a' + b'\x41\x70\x70\x6C\x65\x20\x49\x6E\x63\x2E'
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.ATT_CID_bytes + payload_bytes)

    vprint(f"Sent Apple-specific ATT_FIND_BY_TYPE_VALUE_REQ for 0x2A29 (Apple Inc.)")


#########

def helper_skip_service_handles(test_handle):
    global received_handles
#        print(f"XENO: globals.received_handles = {globals.received_handles}")
    UUID_bytes = globals.received_handles[test_handle]
    # If the test_handle is already in the globals.received_handles,
    # then check if it's a Primary (0x2800) or Secondary (0x2801) service handle, and if so, skip to the next one
    if(len(UUID_bytes) == 2):
        UUID16 = int.from_bytes(UUID_bytes, byteorder='little')
        if(UUID16 == 0x2800 or UUID16 == 0x2801):
            vprint(f"get_next_handle_to_att_read: Skipping service at handle 0x{test_handle:04x} (because we already know its UUID).")
            if(test_handle+1 in globals.received_handles.keys()):
                # It's highly unlikely unless dealing with a messed up or intentionally malicious GATT Server,
                # but it's possible the next UUID after a 0x2800/1 could be another 0x2800/1. So to avoid that case, recurse
                return helper_skip_service_handles(test_handle+1)
            else:
                # If it's not in the globals.received_handles then we must be at the end, or there's a gap before the next handle range
                return -1
        else:
            return test_handle
    elif(len(UUID_bytes) == 16):
#        print(UUID_bytes)
        vprint("get_next_handle_to_att_read: UUID_bytes != 2 bytes")
        return test_handle
    # Should only have UUID16s and UUID128s
    else:
        return -1

# For now we intentionally don't want this to be aware of Characteristic read/write permissions, and to just attempt to read everything possible
def get_next_handle_to_att_read(last_read_handle):
    global received_handles
    global all_handles_read
    vprint(f"get_next_handle_to_att_read: got {last_read_handle}")
    next_handle_assumption = last_read_handle + 1

    # First just check if the next_handle_assumption is in the globals.received_handles
    if(next_handle_assumption in globals.received_handles.keys()):
        returned_handle = helper_skip_service_handles(next_handle_assumption)
        if(returned_handle != -1):
            return returned_handle
        # else fall through and try another way to find a higher handle

    # If the common case of last_read_handle + 1 is not in the globals.received_handles then check if there's a gap and a higher handle later
    sorted_handles = sorted(list(globals.received_handles.keys()))
    for h in sorted_handles:
        if(h > last_read_handle):
            # Found a higher handle. Now check if we need to skip it because it's a Service
            returned_handle = helper_skip_service_handles(h)
            if(returned_handle == -1):
                # It's very unlikely, but again if we're dealing with a messed up GATT Server, it could be that this returned -1
                # because there was a 0x2800 with no characteristics immediately after it, or a gap before the next characteristic
                # So rather than failing out immediately here, let's keep trying for higher values in the sorted_handles
                continue
            else:
                # But if it returned anything other than -1 then it's a success
                return returned_handle

    # If we get here, there must be no higher handle, so we're truly done
    globals.all_handles_read = True
    return -1

def send_next_ATT_READ_REQ_if_applicable(last_read_handle):
    global final_handle
    global handle_read_last_sent_handle

    vprint(f"globals.final_handle = {globals.final_handle}, globals.handle_read_last_sent_handle = {globals.handle_read_last_sent_handle}")
    if(globals.final_handle >= globals.handle_read_last_sent_handle): # Don't send a request past the presumed end of the handles
        next_handle = get_next_handle_to_att_read(last_read_handle)
        if(next_handle != -1):
            send_ATT_READ_REQ(next_handle)
            globals.handle_read_last_sent_handle = next_handle
            globals.handle_read_req_sent_time = time.time_ns()
            return

    # globals.all_handles_read = True

def is_packet_ATT_type(opcode, dpkt):
    header_ACID = ll_len_ACID = l2cap_len_ACID = cid_ACID = att_opcode = 0
    actual_body_len = len(dpkt.body) # The point of actual_body_len is to iterate based on the known size of actual bytes that python is holding, not any ACID lengths
    vprint(f"actual_body_len = 0x{actual_body_len:02x}")
    if(actual_body_len >= 7):
        header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode = unpack("<BBHHB", dpkt.body[:7])
        # Check if it's ATT (CID = 4) and header says it's l2cap w/o fragmentation (I can't handle fragments yet)
        if(cid_ACID == 0x0004 and (header_ACID & 0b10 == 0b10) and att_opcode == opcode):
            return (True, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode)
    return (False, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode)


####################################################################################
# Exchange ATT_MTU to try and get more data in less packets
####################################################################################
def incoming_ATT_EXCHANGE_MTUs(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global att_mtu, att_exchange_MTU_req_sent, att_exchange_MTU_req_sent_time, att_exchange_MTU_rsp_recv, att_MTU_negotiated

    # Process incoming ATT_EXCHANGE_MTU_RSP or ATT_ERROR_RSP responses
    # 7 byte header + 2 bytes Server/Client Rx MTU for both REQ and RSP
    if(not globals.att_MTU_negotiated and actual_body_len >= 9):
        if(not globals.att_exchange_MTU_rsp_recv):
            (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_EXCHANGE_MTU_RSP, dpkt)
            if(matched):
                server_rx_mtu_ACID, = unpack("<H", dpkt.body[7:9])
                # Don't accept smaller-than-required-minimum MTUs, and only update if the new value would be larger
                if(server_rx_mtu_ACID >= 23 and server_rx_mtu_ACID > globals.att_mtu):
                    globals.att_mtu = server_rx_mtu_ACID
                    vprint(f"Got new MTU of 0x{globals.att_mtu:04x}")
                globals.att_exchange_MTU_rsp_recv = True
                globals.att_MTU_negotiated = True
                print(f"---> ATT_EXCHANGE_MTU* phase done (received ATT_EXCHANGE_MTU_RSP), moving to next phase")
                return
        if(not globals.att_exchange_MTU_req_recv):
            (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_EXCHANGE_MTU_REQ, dpkt)
            if(matched):
                globals.att_exchange_MTU_req_recv = True
                globals.queued_client_rx_mtu_ACID, = unpack("<H", dpkt.body[7:9])
                # We need to wait for the LL Data Length Extension to be negotiated before we can respond to the ATT_EXCHANGE_MTU_REQ
                # so that we don't negotiate something larger than the LL can handle, and thus lead to fragmentation (which I can't currently handle)
                if(globals.current_ll_ctrl_state.ll_length_negotiated):
                    if(globals.queued_client_rx_mtu_ACID >= 23):
                        smaller_mtu = min(globals.current_ll_ctrl_state.ll_length_max_tx_octet - 4, globals.queued_client_rx_mtu_ACID)
                        vprint(f"Updating ATT MTU from 0x{globals.att_mtu:04x} to 0x{smaller_mtu:04x}")
                        globals.att_mtu = smaller_mtu
                    else:
                        vprint(f"Using existing MTU of 0x{globals.att_mtu:04x}")
                    # There's no point in sending back an MTU larger than what the other side supports, because the lesser of the two will be used, so just match it
                    send_ATT_EXCHANGE_MTU_RSP(globals.att_mtu)
                    globals.att_exchange_MTU_rsp_sent = True
                    globals.att_MTU_negotiated = True
                    print(f"---> ATT_EXCHANGE_MTU* phase done (received ATT_EXCHANGE_MTU_REQ), moving to next phase")
                    return

def outgoing_ATT_EXCHANGE_MTUs(actual_body_len, dpkt):
    # Process outgoing
    if(globals.attempt_2M_PHY_update): # Meaning no request was made to update the PHY:
        conditions = globals.current_ll_ctrl_state.PHY_updated and globals.current_ll_ctrl_state.ll_length_negotiated and not globals.att_MTU_negotiated
    else: # Meaning a request was made to update the PHY:
        conditions = globals.current_ll_ctrl_state.ll_length_negotiated and not globals.att_MTU_negotiated
    if(conditions):
        # Send a response to the queued ATT_EXCHANGE_MTU_REQ, if any
        if(globals.att_exchange_MTU_req_recv and not globals.att_exchange_MTU_rsp_sent):
            smaller_mtu = min(globals.current_ll_ctrl_state.ll_length_max_tx_octet - 4, globals.queued_client_rx_mtu_ACID)
            vprint(f"Updating ATT MTU from 0x{globals.att_mtu:04x} to 0x{smaller_mtu:04x}")
            globals.att_mtu = smaller_mtu
            # There's no point in sending back an MTU larger than what the other side supports, because the lesser of the two will be used, so just match it
            send_ATT_EXCHANGE_MTU_RSP(globals.att_mtu)
            globals.att_exchange_MTU_rsp_sent = True
            globals.att_exchange_MTU_rsp_sent_time = time.time_ns()
            globals.att_MTU_negotiated = True
            print(f"---> ATT_EXCHANGE_MTU* phase done (replied to queued ATT_EXCHANGE_MTU_REQ), moving to next phase")
        # Else send an ATT_EXCHANGE_MTU_REQ if we haven't already send a RSP (which would mark att_MTU_negotiated = True)
        if(not globals.att_MTU_negotiated and not globals.att_exchange_MTU_req_sent):
            smaller_mtu = min(globals.current_ll_ctrl_state.ll_length_max_tx_octet - 4, 247)
            globals.att_mtu = smaller_mtu
            send_ATT_EXCHANGE_MTU_REQ(globals.att_mtu)
            globals.att_exchange_MTU_req_sent = True
            globals.att_exchange_MTU_req_sent_time = time.time_ns()


def manage_ATT_EXCHANGE_MTU(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global att_mtu, att_exchange_MTU_req_sent, att_exchange_MTU_req_sent_time, att_exchange_MTU_rsp_recv, att_MTU_negotiated

    # Process incoming ATT_EXCHANGE_MTU_RSP or ATT_ERROR_RSP responses
    # 7 byte header + 2 bytes Server/Client Rx MTU for both REQ and RSP
    if(not globals.att_MTU_negotiated and actual_body_len >= 9):
        if(not globals.att_exchange_MTU_rsp_recv):
            (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_EXCHANGE_MTU_RSP, dpkt)
            if(matched):
                server_rx_mtu_ACID, = unpack("<H", dpkt.body[7:9])
                # Don't accept smaller-than-required-minimum MTUs, and only update if the new value would be larger
                if(server_rx_mtu_ACID >= 23 and server_rx_mtu_ACID > globals.att_mtu):
                    globals.att_mtu = server_rx_mtu_ACID
                    vprint(f"Got new MTU of 0x{globals.att_mtu:04x}")
                globals.att_exchange_MTU_rsp_recv = True
                globals.att_MTU_negotiated = True
                print(f"---> ATT_EXCHANGE_MTU* phase done (received ATT_EXCHANGE_MTU_RSP), moving to next phase")
                return
        if(not globals.att_exchange_MTU_req_recv):
            (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_EXCHANGE_MTU_REQ, dpkt)
            if(matched):
                globals.att_exchange_MTU_req_recv = True
                globals.queued_client_rx_mtu_ACID, = unpack("<H", dpkt.body[7:9])
                # We need to wait for the LL Data Length Extension to be negotiated before we can respond to the ATT_EXCHANGE_MTU_REQ
                # so that we don't negotiate something larger than the LL can handle, and thus lead to fragmentation (which I can't currently handle)
                if(globals.current_ll_ctrl_state.ll_length_negotiated):
                    if(globals.queued_client_rx_mtu_ACID >= 23):
                        smaller_mtu = min(globals.current_ll_ctrl_state.ll_length_max_tx_octet - 4, globals.queued_client_rx_mtu_ACID)
                        vprint(f"Updating ATT MTU from 0x{globals.att_mtu:04x} to 0x{smaller_mtu:04x}")
                        globals.att_mtu = smaller_mtu
                    else:
                        vprint(f"Using existing MTU of 0x{globals.att_mtu:04x}")
                    # There's no point in sending back an MTU larger than what the other side supports, because the lesser of the two will be used, so just match it
                    send_ATT_EXCHANGE_MTU_RSP(globals.att_mtu)
                    globals.att_exchange_MTU_rsp_sent = True
                    globals.att_MTU_negotiated = True
                    print(f"---> ATT_EXCHANGE_MTU* phase done (received ATT_EXCHANGE_MTU_REQ), moving to next phase")
                    return

    # Process outgoing
    if(globals.attempt_2M_PHY_update): # Meaning no request was made to update the PHY:
        conditions = globals.current_ll_ctrl_state.PHY_updated and globals.current_ll_ctrl_state.ll_length_negotiated and not globals.att_MTU_negotiated
    else: # Meaning a request was made to update the PHY:
        conditions = globals.current_ll_ctrl_state.ll_length_negotiated and not globals.att_MTU_negotiated
    if(conditions):
        # Send a response to the queued ATT_EXCHANGE_MTU_REQ, if any
        if(globals.att_exchange_MTU_req_recv and not globals.att_exchange_MTU_rsp_sent):
            smaller_mtu = min(globals.current_ll_ctrl_state.ll_length_max_tx_octet - 4, globals.queued_client_rx_mtu_ACID)
            vprint(f"Updating ATT MTU from 0x{globals.att_mtu:04x} to 0x{smaller_mtu:04x}")
            globals.att_mtu = smaller_mtu
            # There's no point in sending back an MTU larger than what the other side supports, because the lesser of the two will be used, so just match it
            send_ATT_EXCHANGE_MTU_RSP(globals.att_mtu)
            globals.att_exchange_MTU_rsp_sent = True
            globals.att_exchange_MTU_rsp_sent_time = time.time_ns()
            globals.att_MTU_negotiated = True
            print(f"---> ATT_EXCHANGE_MTU* phase done (replied to queued ATT_EXCHANGE_MTU_REQ), moving to next phase")
        # Else send an ATT_EXCHANGE_MTU_REQ if we haven't already send a RSP (which would mark att_MTU_negotiated = True)
        if(not globals.att_MTU_negotiated and not globals.att_exchange_MTU_req_sent):
            smaller_mtu = min(globals.current_ll_ctrl_state.ll_length_max_tx_octet - 4, 247)
            globals.att_mtu = smaller_mtu
            send_ATT_EXCHANGE_MTU_REQ(globals.att_mtu)
            globals.att_exchange_MTU_req_sent = True
            globals.att_exchange_MTU_req_sent_time = time.time_ns()

#################################################################################
# Helpers for manage_ATT_FIND_INFORMATION
#################################################################################
# Returns the final handle it saw in the packet
def store_handle_info(dpkt):
    global received_handles
    actual_body_len = len(dpkt.body) # The point of actual_body_len is to iterate based on the known size of actual bytes that python is holding, not any ACID lengths
    if(actual_body_len < 8):
        return -1
    (format,) = unpack("<B", dpkt.body[7:8])
    vprint(f"format = 0x{format:02x}")
    remaining_len = len(dpkt.body) - 8 # 8 is the numer of header bytes before the data, including the format
    body_idx = 8
    while(remaining_len >= 4):
        if(format == 1): # UUID16
            handle, UUID16 = unpack("<HH", dpkt.body[body_idx:body_idx+4])
            globals.received_handles[handle] = dpkt.body[body_idx+2:body_idx+4] # Store as bytes so we have universal conversion util later # f"{UUID16:04x}"
            vprint(f"Added handle 0x{handle:04x} = UUID 0x{UUID16:04x}")
            remaining_len -= 4
            body_idx += 4
        elif(format == 2 and remaining_len >= 18): # UUID128
            (handle,) = unpack("<H", dpkt.body[body_idx:body_idx+2])
            body_idx += 2
            remaining_len -= 2
            UUID128 = dpkt.body[body_idx:body_idx+16]
            globals.received_handles[handle] = dpkt.body[body_idx:body_idx+16] # Store as bytes so we have universal conversion util later # convert_bytes_to_UUID128_str(UUID128)
            vprint(f"Added handle 0x{handle:04x} = UUID 0x{convert_bytes_to_UUID128_str(globals.received_handles[handle])}")
            remaining_len -= 16
            body_idx += 16

    vprint(handle)
    return int(handle)

# Helper for manage_ATT_FIND_INFORMATION
def check_for_higher_service_start_handle(handle):
    # Merge lists to make sure we don't accidentally pick a higher number from one of the dictionaries than is available in the other dictionary
    all_service_start_handles = sorted(list(globals.primary_service_handle_ranges_dict.keys()) + list(globals.secondary_service_handle_ranges_dict.keys()))
    for svc_start_handle in all_service_start_handles:
        if(svc_start_handle > handle):
            return svc_start_handle
    # If we get here, nothing larger was found, so just return the same handle
    return handle


#################################################################################
# Send ATT_FIND_INFORMATION_REQs to find all handles, declarations, & descriptors
#################################################################################
def outgoing_handle_discovery(actual_body_len, dpkt):
    global info_req_sent_time

    # Wait for all secondary services before trying to find all handles
    # And also don't do anything further here if we've already received all handles
    if(not globals.secondary_services_all_recv or globals.all_info_handles_recv):
        return

    if (not globals.info_req_sent_time):
        send_ATT_FIND_INFORMATION_REQ(1)
        # globals.info_req_sent = True
        globals.info_req_sent_time = time.time_ns()
        return
    elif(globals.retry_enabled and not globals.primary_services_all_recv):
        # Check if we need to re-send because it's been too long since we saw any response
        # If the primary_service_final_handle is still 1 that means we haven't received any responses
        # so retry sending the request
        time_elapsed = (time.time_ns() - globals.info_req_sent_time)
        if(time_elapsed > globals.retry_timeout):
            globals.info_req_sent_retry_count += 1
            if(globals.info_req_sent_retry_count == globals.primary_service_request_max_retries):
                # We're done trying, consider discovery of secondary services done
                globals.all_info_handles_recv = True
            else:
                send_ATT_FIND_INFORMATION_REQ(globals.info_req_last_requested_handle)
                globals.info_req_sent_time = time.time_ns()



def process_ATT_FIND_INFORMATION_RSP(actual_body_len, dpkt):
    global all_handles_received_values
    global primary_services_all_recv
    global primary_service_handle_ranges_dict, primary_service_final_handle, primary_service_last_reqested_handle
    global secondary_services_all_recv
    global secondary_service_handle_ranges_dict, secondary_service_final_handle, secondary_service_last_reqested_handle

    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_FIND_INFORMATION_RSP, dpkt)
    if(matched and actual_body_len >= 8):
        # We have processed 8 header bytes so far. The remaining bytes are (handle,UUID{16,128}) pairs
        l_final_handle = store_handle_info(dpkt)
        if(l_final_handle == -1): # error
            vprint("store_handle_info() returned an error")
            return
        elif(l_final_handle > globals.final_handle):
            globals.final_handle = l_final_handle

        globals.info_req_last_requested_handle = globals.final_handle+1
        send_ATT_FIND_INFORMATION_REQ(globals.info_req_last_requested_handle)

def process_ATT_ERROR_RSP_for_ATT_FIND_INFORMATION_REQ(actual_body_len, dpkt):
    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_ERROR_RSP, dpkt)
    if(matched and actual_body_len >= 11):
        req_opcode_in_error, handle_in_error, error_code = unpack("<BHB", dpkt.body[7:11])
        vmultiprint(req_opcode_in_error, handle_in_error)
        vprint(f"error_code = 0x{error_code:02x} = {globals.att_errorcode_to_str[error_code]}")
        # Store something for reference later
        globals.handles_with_error_rsp[handle_in_error] = error_code

        if(req_opcode_in_error == opcode_ATT_FIND_INFORMATION_REQ and error_code == errorcode_0A_ATT_Attribute_Not_Found):
            if(handle_in_error == globals.info_req_last_requested_handle):
                # We might be done, but first check if there is any higher handle returned for a Primary or Secondary Service (i.e. there might be a gap in the handle range)
                higher_handle = check_for_higher_service_start_handle(globals.info_req_last_requested_handle)
                if(higher_handle == globals.info_req_last_requested_handle):
                    # OK, yes, we're done
                    globals.all_info_handles_recv = True
                    print(f"------> ATT_FIND_INFORMATION* phase done, moving to next phase")
                    return True
                else:
                    globals.info_req_last_requested_handle = higher_handle
                    send_ATT_FIND_INFORMATION_REQ(higher_handle)
                    return True

# This function is in here instead of BG_Helper_GATT.py because there's nothing
# particulary GATT-y about just enumerating all ATT handles
def incoming_handle_discovery(actual_body_len, dpkt):
    global info_req_sent, all_info_handles_recv
    global final_handle, handles_with_error_rsp

    # Check if we got a response to the above ATT_FIND_INFORMATION_REQ
    if (globals.info_req_sent_time and not globals.all_info_handles_recv):
        if(actual_body_len >= 7):
            if(process_ATT_FIND_INFORMATION_RSP(actual_body_len, dpkt)):
                return True
            elif(process_ATT_ERROR_RSP_for_ATT_FIND_INFORMATION_REQ(actual_body_len, dpkt)):
                return True
    return False

####################################################################################
# Some devices (like AppleTV) try to enumerate us. This rejects them.
####################################################################################
def manage_peripheral_info_requests(actual_body_len, dpkt):
    # See if the Peripheral is trying to send us an ATT Read by Group Type request, and if so, reject it
    if(actual_body_len == 13):
        (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_READ_BY_GROUP_TYPE_REQ, dpkt)
        if(matched):
            starting_handle, = unpack("<H", dpkt.body[7:9])
            send_ATT_ERROR_RSP(opcode_ATT_READ_BY_GROUP_TYPE_REQ, starting_handle, errorcode_0E_ATT_Unlikely_Error)
            vprint(f"manage_peripheral_info_requests: Rejecting ATT Read by Group Type request")
