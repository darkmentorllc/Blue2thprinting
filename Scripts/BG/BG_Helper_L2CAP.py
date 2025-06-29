# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC
# For use in OST2 BT2701 classs https://ost2.fyi/BT2701

import globals
from BG_Helper_All import *

# Define opcodes and error codes we might need
opcode_L2CAP_COMMAND_REJECT                     = 0x01
opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ    = 0x12
opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP    = 0x13
opcode_L2CAP_LE_CREDIT_BASED_CONNECTION_REQ     = 0x14
opcode_L2CAP_LE_CREDIT_BASED_CONNECTION_RSP     = 0x15
opcode_L2CAP_FLOW_CONTROL_CREDIT_IND            = 0x16
opcode_L2CAP_CREDIT_BASED_CONNECTION_REQ        = 0x17
opcode_L2CAP_CREDIT_BASED_CONNECTION_RSP        = 0x18

LL_opcode_to_str = {
    opcode_L2CAP_COMMAND_REJECT:                         "L2CAP_COMMAND_REJECT",
    opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ:        "L2CAP_CONNECTION_PARAMETER_UPDATE_REQ",
    opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP:        "L2CAP_CONNECTION_PARAMETER_UPDATE_RSP",
    opcode_L2CAP_CREDIT_BASED_CONNECTION_REQ:            "L2CAP_CREDIT_BASED_CONNECTION_REQ",
    opcode_L2CAP_CREDIT_BASED_CONNECTION_RSP:            "L2CAP_CREDIT_BASED_CONNECTION_RSP"
}

L2CAP_Signaling_CID = 0x05
L2CAP_Signaling_CID_bytes = b'\x05\x00'

###### Functions to send outbound packets

def send_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(identifier=0x11, data_length=0x08, interval_min=0x0008, interval_max=0x0008, latency=0x0000, timeout=0x0051):
    # PDU Length = 2 bytes for size of the information payload
    # Channel ID = 2 bytes for L2CAP_Signaling_CID
    # L2CAP Opcode = L2CAP_CONNECTION_PARAMETER_UPDATE_REQ
    # Identifier = any value, just for matching response to request
    # Data Length = always *supposed* to be 8 for this packet type...🤔
    # Interval Min = minimum length of a connection event (this value gets multiplied by 1.25ms)
    # Interval Max = maximum length of a connection event (this value gets multiplied by 1.25ms)
    # Latency = Peripheral latency: i.e. how many connection intervals the Peripheral can skip replying to the Central
    # Timeout = How long since the Central has heard from the peripheral before it considers the connection lost (this value gets multiplied by 10ms)
    info_payload =  v1b(opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ) + \
                    v1b(identifier) + \
                    v2b(data_length) + \
                    v2b(interval_min) + \
                    v2b(interval_max) + \
                    v2b(latency) + \
                    v2b(timeout)
    payload_len_bytes = v2b(len(info_payload))
    write_outbound_pkt(globals.LLID_data, payload_len_bytes + L2CAP_Signaling_CID_bytes + info_payload)
    vprint("Sent L2CAP_CONNECTION_PARAMETER_UPDATE_REQ!")

# Result = 0x0001 = Connection Parameters rejected
def send_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(identifier=0x11, data_length=0x02, result=0x0001):
    # PDU Length = 2 bytes for size of the information payload
    # Channel ID = 2 bytes for L2CAP_Signaling_CID
    # L2CAP Opcode = L2CAP_CONNECTION_PARAMETER_UPDATE_RSP
    # Identifier = any value, just for matching response to request
    # Data Length = always *supposed* to be 2 for this packet type...🤔
    # Result = Whether the REQ was successful or rejected
    info_payload =  v1b(opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP) + \
                    v1b(identifier) + \
                    v2b(data_length) + \
                    v2b(result)
    payload_len_bytes = v2b(len(info_payload))
    write_outbound_pkt(globals.LLID_data, payload_len_bytes + L2CAP_Signaling_CID_bytes + info_payload)
    vprint("Sent L2CAP_CONNECTION_PARAMETER_UPDATE_RSP!")


def send_L2CAP_CREDIT_BASED_CONNECTION_REQ(identifier=0x22, data_length=0x0C, spsm=0x0025, mtu=0x0040, mps=0x0040, initial_credits=0x0100):
    # PDU Length = 2 bytes for size of the information payload
    # Channel ID = 2 bytes for L2CAP_Signaling_CID
    # L2CAP Opcode = L2CAP_CREDIT_BASED_CONNECTION_REQ
    # Identifier = any value, just for matching response to request
    # Data Length = This is *naturally variable*, depending on how many Source CID values you send...🤔
    # SPSM = Simplified Protocol/Service Multiplexer (can be predefined or dynamically allocated)
    # MTU = maximum transmission unit for SDU (above L2CAP layer)
    # MPS = maximum PDU payload size for PDU (below L2CAP layer)
    # Initial Credits = How many k-frames can be sent before transmission must stop to wait for new credits
    # Source Channel ID (1, 2, ...) = The channel ID(s) on which L2CAP data can be sent to the source...
    # theoretically there should be >= 1 and <= 5 source CIDs in a single packet...🤔
    source_cid1 = 0x0040
    source_cid2 = 0x0041
    # Add more here if you want...
    info_payload =  v1b(opcode_L2CAP_CREDIT_BASED_CONNECTION_REQ) + \
                    v1b(identifier) + \
                    v2b(data_length) + \
                    v2b(spsm) + \
                    v2b(mtu) + \
                    v2b(mps) + \
                    v2b(initial_credits) + \
                    v2b(source_cid1) + \
                    v2b(source_cid2)
                    # Add more here if you want...
    payload_len_bytes = v2b(len(info_payload))
    write_outbound_pkt(globals.LLID_data, payload_len_bytes + L2CAP_Signaling_CID_bytes + info_payload)
    vprint("Sent L2CAP_CREDIT_BASED_CONNECTION_REQ!")


###### Functions to check if an inbound packet is a specific type
def is_packet_L2CAP_signalling_channel_type(actual_body_len, dpkt, type):
    if(actual_body_len >= 7):
        header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, l2cap_opcode_ACID = unpack("<BBHHB", dpkt.body[:7])
        if(cid_ACID == L2CAP_Signaling_CID and l2cap_opcode_ACID == type):
            return True
    return False

##############################################################################################################
# Functions for sending and receiving L2CAP Signaling Channel (CID = 0x0005) packets
##############################################################################################################

def stateful_incoming_L2CAP_handler(actual_body_len, dpkt):
    global L2CAP_connection_parameters_update_final_state

    # Reject any L2CAP_CONNECTION_PARAMETER_UPDATE_REQ that a Peripheral sends us

    if(is_packet_L2CAP_signalling_channel_type(actual_body_len, dpkt, opcode_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ)):
        header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, l2cap_opcode_ACID, id = unpack("<BBHHBB", dpkt.body[:8])
        send_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(identifier=id)
        print(f"--> Connection Parameter Update procedure complete (L2CAP_CONNECTION_PARAMETER_UPDATE_RSP received)")

# def stateful_outgoing_L2CAP_handler():
#     # Not sending anything for now