# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

import globals
from BGG_Helper_All import *

# Define opcodes and error codes we might need
opcode_LL_TERMINATE_IND             = 0x02
opcode_LL_UNKNOWN_RSP               = 0x07
opcode_LL_FEATURE_REQ               = 0x08
opcode_LL_FEATURE_RSP               = 0x09
opcode_LL_PERIPHERAL_FEATURE_REQ    = 0x0E
opcode_LL_VERSION_IND               = 0x0C
opcode_LL_REJECT_IND                = 0x0D
opcode_LL_LENGTH_REQ                = 0x14
opcode_LL_LENGTH_RSP                = 0x15
opcode_LL_PHY_REQ                   = 0x16
opcode_LL_PHY_RSP                   = 0x17
opcode_LL_PHY_UPDATE_IND            = 0x18

LL_opcode_to_str = {}
LL_opcode_to_str[opcode_LL_TERMINATE_IND]           = "LL_TERMINATE_IND"
LL_opcode_to_str[opcode_LL_UNKNOWN_RSP]             = "LL_UNKNOWN_RSP"
LL_opcode_to_str[opcode_LL_FEATURE_REQ]             = "LL_FEATURE_REQ"
LL_opcode_to_str[opcode_LL_FEATURE_RSP]             = "LL_FEATURE_RSP"
LL_opcode_to_str[opcode_LL_PERIPHERAL_FEATURE_REQ]  = "LL_PERIPHERAL_FEATURE_REQ"
LL_opcode_to_str[opcode_LL_VERSION_IND]             = "LL_VERSION_IND"
LL_opcode_to_str[opcode_LL_LENGTH_REQ]              = "LL_LENGTH_REQ"
LL_opcode_to_str[opcode_LL_LENGTH_RSP]              = "LL_LENGTH_RSP"
LL_opcode_to_str[opcode_LL_PHY_REQ]                 = "LL_PHY_REQ"
LL_opcode_to_str[opcode_LL_PHY_RSP]                 = "LL_PHY_RSP"
LL_opcode_to_str[opcode_LL_PHY_UPDATE_IND]          = "LL_PHY_UPDATE_IND"

LLID_ctrl = 3 # 0b11 for LL Control PDUs

def send_LL_TERMINATE_IND():
    # LL Ctrl Opcode = LL_TERMINATE_IND
    # ErrorCode = 0x13 (Remote User Terminated Connection)
    packet_bytes = v1b(opcode_LL_LENGTH_REQ) + v1b(0x13)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_TERMINATE_IND!")


# Yes, you *could* combine send_LL_LENGTH_REQ and send_LL_LENGTH_RSP into a single function that
# takes an opcode parameter, if you wanted, but we're trying to keep things clear and 1:1 for now.
# "Premature optimization is the root of all evil" - Donald Knuth
def send_LL_LENGTH_REQ(MaxRxOctets, MaxRxTime, MaxTxOctets, MaxTxTime):
    # LL Ctrl Opcode = LL_LENGTH_REQ
    # Common values:
        # MaxRxOctets = 0x00fb (251)
        # MaxRxTime = 0x0848 (2120 ms)
        # MaxTxOctets = 0x00fb (251)
        # MaxTxTime = 0x0848 (2120 ms)
    packet_bytes = v1b(opcode_LL_LENGTH_REQ) + v2b(MaxRxOctets) + v2b(MaxRxTime) + v2b(MaxTxOctets) + v2b(MaxTxTime)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_LENGTH_REQ!")


def send_LL_LENGTH_RSP(MaxRxOctets, MaxRxTime, MaxTxOctets, MaxTxTime):
    # LL Ctrl Opcode = LL_LENGTH_RSP
    # Common values:
        # MaxRxOctets = 0x00fb (251)
        # MaxRxTime = 0x0848 (2120 ms)
        # MaxTxOctets = 0x00fb (251)
        # MaxTxTime = 0x0848 (2120 ms)
    packet_bytes = v1b(opcode_LL_LENGTH_RSP) + v2b(MaxRxOctets) + v2b(MaxRxTime) + v2b(MaxTxOctets) + v2b(MaxTxTime)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_LENGTH_RSP!")


def send_LL_VERSION_IND(version, company_id, subversion):
    # LL Ctrl Opcode = LL_VERSION_IND
    # Version = 1 byte, which version of the BT spec is supported by the device
    # Company_Identifier = 2 bytes, company assigned ID from the Bluetooth SIG
    # Subversion = 2 bytes, per SIG this should be assigned by company for revisions of the controller
    packet_bytes = v1b(opcode_LL_VERSION_IND) + v1b(version) + v2b(company_id) + v2b(subversion)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_VERSION_IND!")


def send_LL_FEATURE_REQ(features):
    # LL Ctrl Opcode = LL_FEATURE_REQ
    # FeatureSet = 8 bytes, of which only the bottom 1 bit is valid as of spec 4.0, 8 bits as of spec 4.2, 17 bits as of spec 5.0, 45 bits as of spec 5.4
        # But you can just send 0xFFFFFFFFFFFFFFFF and many things will accept it
        # Of course if something doesn't, then you'd want to fix this
    packet_bytes = v1b(opcode_LL_FEATURE_REQ) + v8b(features)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    print("Sent LL_FEATURE_REQ!")


def send_LL_FEATURE_RSP(features):
    # LL Ctrl Opcode = LL_FEATURE_RSP
    # FeatureSet = 8 bytes, of which only the bottom 1 bit is valid as of spec 4.0, 8 bits as of spec 4.2, 17 bits as of spec 5.0, 45 bits as of spec 5.4
        # But you can just send 0xFFFFFFFFFFFFFFFF and many things will accept it
        # Of course if something doesn't, then you'd want to fix this
    packet_bytes = v1b(opcode_LL_FEATURE_RSP) + v8b(features)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    print("Sent LL_FEATURE_RSP!")


def send_LL_PHY_RSP(tx_phys, rx_phys):
    # LL Ctrl Opcode = LL_PHY_RSP
    # TX_PHYS = tx_phys
    # RX_PHYS = rx_phys
    packet_bytes = v1b(opcode_LL_PHY_RSP) + v1b(tx_phys) + v2b(rx_phys)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_PHY_RSP!")

####################################################################################
# LL_PERIPHERAL_FEATURE_REQ as sent immediately by some Peripherals
####################################################################################
def manage_LL_PERIPHERAL_FEATURE_REQ(actual_body_len, dpkt):
    global ll_feature_rsp_sent, ll_feature_rsp_sent_time
    global ll_peripheral_feature_req_recv

    # Only send LL_FEATURE_RSP in response to a LL_PERIPHERAL_FEATURE_REQ
    if(not globals.ll_peripheral_feature_req_recv):
        if(actual_body_len == 11):
            #ll_features = [] # don't know if this will work to capture 8 bytes of features
            header_ACID, ll_len_ACID, ll_ctl_opcode, ll_features = unpack("<BBBQ", dpkt.body[:11]) # Q is quad-word = 8 bytes
            if(ll_ctl_opcode == opcode_LL_PERIPHERAL_FEATURE_REQ):
                globals.ll_peripheral_feature_req_recv = True
                vmultiprint(header_ACID, ll_len_ACID, ll_features)
                send_LL_FEATURE_RSP(0xFFFFFFFFFFFFFFFF)
                globals.ll_feature_rsp_sent_time = time.time_ns()
                globals.ll_feature_rsp_sent = True
                globals.ll_ctrl_pkt_pending = True
                print(f"-> LL_FEATURE_RSP sent ({LL_opcode_to_str[ll_ctl_opcode]} received). Moving to next phase")
                return True
    # Don't bother with retransmission for now
    return False

####################################################################################
# LL_FEATURES_REQ/RSP because it's the second most useful after LL_VERSION_IND
####################################################################################
def manage_LL_FEATUREs(actual_body_len, dpkt):
    global ll_version_ind_sent, ll_version_ind_sent_time, ll_version_ind_recv

    # Don't send this if there's LL CTRL outstanding or we've already sent it
    if(not globals.ll_ctrl_pkt_pending and not globals.ll_feature_req_sent):
        send_LL_FEATURE_REQ(0xFFFFFFFFFFFFFFFF)
        globals.ll_ctrl_pkt_pending = True
        globals.ll_feature_req_sent = True
        globals.ll_feature_req_sent_time = time.time_ns()

    # Process LL_VERSION_IND (shouldn't be possible to get a LL_UNKNOWN_RSP/LL_REJECT_IND, since this was in the spec since 4.0)
    # This could come in before we request it, so don't make ll_version_ind_sent a requirement
    if(globals.ll_feature_req_sent and not globals.ll_feature_rsp_recv):
        if(actual_body_len == 0x0B):
           header_ACID, ll_len_ACID, ll_ctl_opcode, features = unpack("<BBBQ", dpkt.body[:11])
           vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, features)
           if(ll_ctl_opcode == opcode_LL_FEATURE_RSP):
               globals.ll_feature_rsp_recv = True
               print(f"--> LL_FEATUREs phase done, moving to next phase")
               globals.ll_ctrl_pkt_pending = False
               # TODO: check features bit index 5 to see if it support "LE Data Packet Length Extension", and if not, don't bother with manage_LL_LENGTH_REQ?


####################################################################################
# LL_LENGTH_REQ to try and get more data in less packets
####################################################################################
def manage_LL_LENGTH_REQ(actual_body_len, dpkt):
    global ll_length_req_sent, ll_length_req_sent_time, ll_length_rsp_recv
    global ll_length_rsp_supported

    # Always send an LL_LENGTH_REQ if we haven't already
    if(not globals.ll_ctrl_pkt_pending and not globals.ll_length_req_sent):
        send_LL_LENGTH_REQ(251, 2120, 251, 2120)
        globals.ll_ctrl_pkt_pending = True
        globals.ll_length_req_sent = True
        globals.ll_length_req_sent_time = time.time_ns()

    # Process LL_LENGTH_REQ or LL_LENGTH_RSP or LL_UNKNOWN_RSP/LL_REJECT_IND (which is technically possible if the target was a v4.0 or v4.1 where LL_LENGTH_REQ didn't exist yet.)
    if(globals.ll_length_req_sent and not globals.ll_length_rsp_recv):
        if(actual_body_len == 11):
            header_ACID, ll_len_ACID, ll_ctl_opcode, max_rx_octet, max_rx_time, max_tx_octet, max_tx_time = unpack("<BBBHHHH", dpkt.body[:11])
            # Treat an LL_LENGTH_REQ send by the Peripheral as equivalent to an LL_LENGTH_RSP
            if(ll_ctl_opcode == opcode_LL_LENGTH_RSP):
                globals.ll_length_rsp_recv = True
		        # FIXME!: Don't set this as successful if their LL_LENGTH_RSP came back with a lower value than we indicated we support (i.e. we say 251 bytes, then they reply 27 bytes...)
                if(max_rx_octet >= 251 and max_tx_octet >= 251):
                    globals.ll_length_rsp_supported = True
                vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, max_rx_octet, max_rx_time, max_tx_octet, max_tx_time)
                print(f"-> LL_LENGTH* phase done, ({LL_opcode_to_str[ll_ctl_opcode]} received). Moving to next phase")
                globals.ll_ctrl_pkt_pending = False
                return
            if(ll_ctl_opcode == opcode_LL_LENGTH_REQ):
                send_LL_LENGTH_RSP(251, 2120, 251, 2120) # Send just to make the Peripheral's state machine happy
                globals.ll_length_rsp_recv = True
                globals.ll_length_rsp_supported = True
                vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, max_rx_octet, max_rx_time, max_tx_octet, max_tx_time)
                print(f"-> LL_LENGTH* phase done, ({LL_opcode_to_str[ll_ctl_opcode]} received). Moving to next phase")
                globals.ll_ctrl_pkt_pending = False
                return
        if(actual_body_len == 4):
            header_ACID, ll_len_ACID, ll_ctl_opcode, ll_error_code = unpack("<BBBB", dpkt.body[:4])
            if(ll_ctl_opcode == opcode_LL_UNKNOWN_RSP or ll_ctl_opcode == opcode_LL_REJECT_IND):
                globals.ll_length_rsp_recv = True
                vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, ll_error_code)
                print(f"-> LL_LENGTH* phase done, ({LL_opcode_to_str[ll_ctl_opcode]} received). Moving to next phase")
                globals.ll_ctrl_pkt_pending = False
                return
        # Check if it's been too long since we got the LL_LENGTH_RSP, and if so, re-send the req
        current_time = time.time_ns()
        time_diff_in_ms = (current_time - globals.ll_length_req_sent_time) // 1000000
#        if(time_diff_in_ms > 10): # If it's greater than 10ms, re-request (because I just want to see if it rerequests)
        if(time_diff_in_ms > 100): # If it's greater than 100ms, re-request
            send_LL_LENGTH_REQ(251, 2120, 251, 2120)
            globals.ll_length_req_sent_time = time.time_ns()

####################################################################################
# LL_VERSION_IND due to some devices requiring it
####################################################################################
def manage_LL_VERSION_IND(actual_body_len, dpkt):
    global ll_version_ind_sent, ll_version_ind_sent_time, ll_version_ind_recv

    # Don't send this if there's an LL_LENGTH_REQ outstanding
    if(globals.ll_length_req_sent and not globals.ll_length_rsp_recv):
        return

    # I've found that an iPad won't proceed with responding to the ATT_EXCHANGE_MTU_REQ
    # if I haven't replied to their LL_VERSION_IND. So adding that too
    if(not globals.ll_ctrl_pkt_pending and not globals.ll_version_ind_sent):
        send_LL_VERSION_IND(6, 0x1337, 0x1337)
        globals.ll_ctrl_pkt_pending = True
        globals.ll_version_ind_sent = True
        globals.ll_version_ind_sent_time = time.time_ns()

    # Process LL_VERSION_IND (shouldn't be possible to get a LL_UNKNOWN_RSP/LL_REJECT_IND, since this was in the spec since 4.0)
    # This could come in before we request it, so don't make ll_version_ind_sent a requirement
    if(not globals.ll_version_ind_recv):
        if(actual_body_len == 0x08):
           header_ACID, ll_len_ACID, ll_ctl_opcode, version, company_id, subversion = unpack("<BBBBHH", dpkt.body[:8])
           vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, version, company_id, subversion)
           if(ll_ctl_opcode == opcode_LL_VERSION_IND):
               globals.ll_version_ind_recv = True
               print(f"--> LL_VERSION_IND phase done, moving to next phase")
               globals.ll_ctrl_pkt_pending = False

####################################################################################
# LL_PHY_REQ/RSP due to some devices requiring it
####################################################################################
# Currently I can't send an LL_PHY_REQ due to not being able to set the Instant
# FIXME: once there's a way to set the Instant change this up. For now just reject requests
def manage_LL_PHYs(actual_body_len, dpkt):
    global ll_phy_req_recv, ll_phy_rsp_sent, ll_phy_rsp_sent_time

    # FIXME: For now, only respond to the Peripheral sending a LL_PHY_REQ by essentially rejecting it

    # Process LL_PHY_REQ
    if(not globals.ll_phy_rsp_sent):
        if(actual_body_len == 0x05):
           header_ACID, ll_len_ACID, ll_ctl_opcode, tx_phys, rx_phys = unpack("<BBBBB", dpkt.body[:5])
           vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, tx_phys, rx_phys)
           if(ll_ctl_opcode == opcode_LL_PHY_REQ):
               globals.ll_phy_req_recv = True
               send_LL_PHY_RSP(1,1) # FIXME: For now we're hardcoding to 1M PHY until we can change it
               print(f"--> LL_PHY* phase done, moving to next phase")
               return True
