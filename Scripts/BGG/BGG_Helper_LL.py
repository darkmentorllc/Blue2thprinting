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
opcode_LL_REJECT_EXT_IND            = 0x11
opcode_LL_LENGTH_REQ                = 0x14
opcode_LL_LENGTH_RSP                = 0x15
opcode_LL_PHY_REQ                   = 0x16
opcode_LL_PHY_RSP                   = 0x17
opcode_LL_PHY_UPDATE_IND            = 0x18
opcode_LL_POWER_CONTROL_REQ         = 0x23
opcode_LL_POWER_CONTROL_RSP         = 0x24

LL_opcode_to_str = {}
LL_opcode_to_str[opcode_LL_TERMINATE_IND]           = "LL_TERMINATE_IND"
LL_opcode_to_str[opcode_LL_UNKNOWN_RSP]             = "LL_UNKNOWN_RSP"
LL_opcode_to_str[opcode_LL_FEATURE_REQ]             = "LL_FEATURE_REQ"
LL_opcode_to_str[opcode_LL_FEATURE_RSP]             = "LL_FEATURE_RSP"
LL_opcode_to_str[opcode_LL_PERIPHERAL_FEATURE_REQ]  = "LL_PERIPHERAL_FEATURE_REQ"
LL_opcode_to_str[opcode_LL_VERSION_IND]             = "LL_VERSION_IND"
LL_opcode_to_str[opcode_LL_REJECT_IND]              = "LL_REJECT_IND"
LL_opcode_to_str[opcode_LL_REJECT_EXT_IND]          = "LL_REJECT_EXT_IND"
LL_opcode_to_str[opcode_LL_LENGTH_REQ]              = "LL_LENGTH_REQ"
LL_opcode_to_str[opcode_LL_LENGTH_RSP]              = "LL_LENGTH_RSP"
LL_opcode_to_str[opcode_LL_PHY_REQ]                 = "LL_PHY_REQ"
LL_opcode_to_str[opcode_LL_PHY_RSP]                 = "LL_PHY_RSP"
LL_opcode_to_str[opcode_LL_PHY_UPDATE_IND]          = "LL_PHY_UPDATE_IND"

LLID_ctrl = 3 # 0b11 for LL Control PDUs

################################################################################
# Define classes for cleaner state management
################################################################################

def clear_pending_packet_state():
    global current_ll_ctrl_state
    # Clear the erronous state
    globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = False
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = None
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = None

def update_LL_LENGTH_state(opcode, state_str, ll_length_max_rx_octet=None, ll_length_max_tx_octet=None):
    global att_mtu
    global current_ll_ctrl_state
    global ll_length_rsp_recv

    globals.current_ll_ctrl_state.ll_length_state = globals.ll_packet_names_to_states[state_str]

    # This is to reset the state
    if(state_str == "Not sent"):
        globals.current_ll_ctrl_state.ll_length_negotiated = False # This is essentially the quick-check "done" state
        globals.current_ll_ctrl_state.ll_length_max_rx_octet = 27 # BT spec default
        globals.current_ll_ctrl_state.ll_length_max_tx_octet = 27
        globals.ll_length_req_sent = False
        globals.ll_length_req_sent_time = 0
        globals.ll_length_req_recv = False
        globals.ll_length_req_recv_time = 0
        globals.ll_length_rsp_sent = False
        globals.ll_length_rsp_sent_time = 0
        globals.ll_length_rsp_recv = False
        globals.ll_length_rsp_recv_time = 0

    # A state of "Received" can occur either because they sent us a Peripheral-initiated LL_LENGTH_REQ
    # or because we sent them a Central-initiated LL_LENGTH_REQ and they sent us a LL_LENGTH_RSP
    if(state_str == "Received" and ll_length_max_rx_octet and ll_length_max_tx_octet):
        globals.current_ll_ctrl_state.ll_length_negotiated = True
        # Only update the max RX/TX octets if they are greater than what we have (which starts at the default of 27)
        if(globals.current_ll_ctrl_state.ll_length_max_rx_octet < ll_length_max_rx_octet):
            globals.current_ll_ctrl_state.ll_length_max_rx_octet = ll_length_max_rx_octet
            globals.att_mtu = ll_length_max_rx_octet
        if(globals.current_ll_ctrl_state.ll_length_max_tx_octet < ll_length_max_tx_octet):
            globals.current_ll_ctrl_state.ll_length_max_tx_octet = ll_length_max_tx_octet
            globals.att_mtu = ll_length_max_tx_octet

    # We sent our response, so we can clear the pending state
    if(state_str == "Sent" and opcode == opcode_LL_LENGTH_REQ):
        globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode
        globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = time.time_ns()

    # We sent our RSP to their REQ, so we can clear the pending state
    # Or we got back an error type for a REQ we sent
    if(opcode == opcode_LL_LENGTH_RSP or opcode == opcode_LL_REJECT_IND or opcode == opcode_LL_REJECT_EXT_IND or opcode == opcode_LL_UNKNOWN_RSP):
        clear_pending_packet_state()
        globals.ll_length_rsp_recv = True
        # FIXME: is this OK to just treat it like it suceeded but negotiated default, if the thing we talked to
        # only supported 4.0 and thus sent back an error to LL_LENGTH_REQ?
        globals.att_MTU_negotiated = True


################################################################################
# Define packet sending functions
################################################################################

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


def send_LL_LENGTH_REQ_and_update_state():
    global current_ll_ctrl_state
    global ll_length_req_sent_time, ll_length_req_sent
    send_LL_LENGTH_REQ(251, 2120, 251, 2120)
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_LENGTH_REQ
    globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = True
    t = time.time_ns()
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = t
    globals.ll_length_req_sent_time = t
    globals.ll_length_req_sent = True


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


def send_LL_VERSION_IND_and_update_state():
    global current_ll_ctrl_state
    global ll_version_ind_sent_time, ll_version_ind_sent
    send_LL_VERSION_IND(6, 0x1337, 0x1337)
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_VERSION_IND
    globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = True
    t = time.time_ns()
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = t
    globals.ll_version_ind_sent_time = t
    globals.ll_version_ind_sent = True

def send_LL_FEATURE_REQ(features):
    # LL Ctrl Opcode = LL_FEATURE_REQ
    # FeatureSet = 8 bytes, of which only the bottom 1 bit is valid as of spec 4.0, 8 bits as of spec 4.2, 17 bits as of spec 5.0, 45 bits as of spec 5.4
        # But you can just send 0xFFFFFFFFFFFFFFFF and many things will accept it
        # Of course if something doesn't, then you'd want to fix this
    packet_bytes = v1b(opcode_LL_FEATURE_REQ) + v8b(features)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_FEATURE_REQ!")


def send_LL_FEATURE_REQ_and_update_state():
    global current_ll_ctrl_state
    global ll_feature_req_sent_time, ll_feature_req_sent
    send_LL_FEATURE_REQ(0xFFFFFFFFFFFFFFFF)
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_FEATURE_REQ
    globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = True
    t = time.time_ns()
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = t
    globals.ll_feature_req_sent_time = t
    globals.ll_feature_req_sent = True


def send_LL_FEATURE_RSP(features):
    # LL Ctrl Opcode = LL_FEATURE_RSP
    # FeatureSet = 8 bytes, of which only the bottom 1 bit is valid as of spec 4.0, 8 bits as of spec 4.2, 17 bits as of spec 5.0, 45 bits as of spec 5.4
        # But you can just send 0xFFFFFFFFFFFFFFFF and many things will accept it
        # Of course if something doesn't, then you'd want to fix this
    packet_bytes = v1b(opcode_LL_FEATURE_RSP) + v8b(features)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    print("Sent LL_FEATURE_RSP!")


def send_LL_PHY_REQ(tx_phys, rx_phys):
    # LL Ctrl Opcode = send_LL_PHY_REQ
    # TX_PHYS = tx_phys
    # RX_PHYS = rx_phys
    packet_bytes = v1b(opcode_LL_PHY_REQ) + v1b(tx_phys) + v1b(rx_phys)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_PHY_REQ!")


def send_LL_PHY_REQ_and_update_state():
    global current_ll_ctrl_state
    global ll_phy_req_sent_time, ll_phy_req_sent
    global attempt_2M_PHY_update
    # Don't send this if either we weren't directed on the CLI to attempt 2M PHY update
    # or if the Peripheral features indicate it doesn't support 2M PHY
    if(not globals.attempt_2M_PHY_update):
        return
    if (not globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy):
        # If the peripheral doesn't support 2M PHY, set this to false, to avoid an infinite loop
        globals.attempt_2M_PHY_update = False
        return

    send_LL_PHY_REQ(0x02, 0x02)
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode = opcode_LL_PHY_REQ
    globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = True
    t = time.time_ns()
    globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time = t
    globals.ll_phy_req_sent_time = t
    globals.ll_phy_req_sent = True


def send_LL_PHY_RSP(tx_phys, rx_phys):
    # LL Ctrl Opcode = LL_PHY_RSP
    # TX_PHYS = tx_phys
    # RX_PHYS = rx_phys
    packet_bytes = v1b(opcode_LL_PHY_RSP) + v1b(tx_phys) + v1b(rx_phys)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_PHY_RSP!")


def send_LL_PHY_UPDATE_IND(phy_c_to_p, phy_p_to_c, instant_offset=0):
    # LL Ctrl Opcode = LL_PHY_UPDATE_IND
    # PHY_C_TO_P = phy_c_to_p
    # PHY_P_TO_C = phy_p_to_c
    # Instant = globals.connEventCount + instant
    packet_bytes = v1b(opcode_LL_PHY_UPDATE_IND) + v1b(phy_c_to_p) + v1b(phy_p_to_c) + v2b(globals.connEventCount + instant_offset)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_PHY_UPDATE_IND!")


def send_LL_PHY_UPDATE_IND_and_update_state(instant_offset=0):
    global current_ll_ctrl_state
    global ll_phy_update_ind_sent, ll_phy_update_ind_sent_time
    global ll_length_req_recv
    # Don't send this if either we weren't directed on the CLI to attempt 2M PHY update
    # or if the Peripheral features indicate it doesn't support 2M PHY
    if ((globals.current_ll_ctrl_state.supported_PHYs != 2) or not globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy):
        return

    send_LL_PHY_UPDATE_IND(0x02, 0x02, instant_offset)
    globals.ll_phy_update_ind_sent = True
    globals.ll_phy_update_ind_sent_time = time.time_ns()


# for rejecting opcodes we don't want to deal with
def send_LL_REJECT_EXT_IND(opcode, error_code):
    # LL Ctrl Opcode = LL_REJECT_EXT_IND
    # Opcode = opcode (contains the opcode that was rejected)
    # Error Code = error_code (contains the reason a request was rejected)
    packet_bytes = v1b(opcode_LL_REJECT_EXT_IND) + v1b(opcode) + v1b(error_code)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_REJECT_EXT_IND!")


def send_LL_POWER_CONTROL_RSP(min, max, delta, txpower, apr):
    # LL Ctrl Opcode = LL_POWER_CONTROL_RSP
    # CtrlData = (LSB) min (1 bit), max (1 bit), RFU (6 bits),  delta (8 bits), txpower (8 bits), apr (Acceptable Power Reduction) (8 bits) (MSB)
    #ctrl_data = v1b(apr) << 24 | v1b(txpower) << 16 | v1b(delta) << 8 | v1b(max) << 1 | v1b(min)
    ctrl_data = apr << 24 | txpower << 16 | delta << 8 | max << 1 | min
    packet_bytes = v1b(opcode_LL_POWER_CONTROL_RSP) + v4b(ctrl_data)
    write_outbound_pkt(LLID_ctrl, packet_bytes)
    vprint("Sent LL_POWER_CONTROL_RSP!")

####################################################################################
# Incoming error responses (LL_UNKNOWN_RSP, LL_REJECT_IND, LL_REJECT_EXT_IND)
####################################################################################

def incoming_LL_errors(actual_body_len, dpkt):
    global current_ll_ctrl_state

    if(actual_body_len == 4):
        header_ACID, ll_len_ACID, ll_ctl_opcode, ll_field = unpack("<BBBB", dpkt.body[:4])
        vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, ll_field)
        if(ll_ctl_opcode == opcode_LL_UNKNOWN_RSP):
            if(globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode == opcode_LL_LENGTH_REQ and ll_field == opcode_LL_LENGTH_REQ):
                print(f"--> LL_LENGTH* phase done, (LL_UNKNOWN_RSP received). Moving to next phase")
                update_LL_LENGTH_state(ll_ctl_opcode, "Unknown")

        elif(ll_ctl_opcode == opcode_LL_REJECT_IND):
            if(globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode == opcode_LL_LENGTH_REQ):
                print(f"--> LL_LENGTH* phase done, (Rejected with reason {ll_field}). Moving to next phase")
                update_LL_LENGTH_state(ll_ctl_opcode, "Rejected")

    elif(actual_body_len == 5):
        header_ACID, ll_len_ACID, ll_ctl_opcode, ll_reject_opcode, ll_error_code = unpack("<BBBBB", dpkt.body[:5])
        vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, ll_reject_opcode, ll_error_code)
        if(ll_ctl_opcode == opcode_LL_REJECT_EXT_IND):
            if(globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode == opcode_LL_LENGTH_REQ and ll_reject_opcode == opcode_LL_LENGTH_REQ):
                print(f"--> LL_LENGTH* phase done, (Rejected with reason {ll_field}). Moving to next phase")
                update_LL_LENGTH_state(ll_ctl_opcode, "Rejected")

    clear_pending_packet_state()
    return True


####################################################################################
# LL_PERIPHERAL_FEATURE_REQ as sent immediately by some Peripherals
####################################################################################
def incoming_LL_PERIPHERAL_FEATURE_REQ(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global ll_feature_rsp_sent, ll_feature_rsp_sent_time
    global ll_peripheral_feature_req_recv

    # Only send LL_FEATURE_RSP in response to a LL_PERIPHERAL_FEATURE_REQ
    if(not globals.current_ll_ctrl_state.ll_features_received):
        if(actual_body_len == 11):
            #ll_features = [] # don't know if this will work to capture 8 bytes of features
            header_ACID, ll_len_ACID, ll_ctl_opcode, ll_features = unpack("<BBBQ", dpkt.body[:11]) # Q is quad-word = 8 bytes
            # We already know it's ll_ctl_opcode == LL_PERIPHERAL_FEATURE_REQ due to a check in the calling function
            vmultiprint(header_ACID, ll_len_ACID, ll_features)
            send_LL_FEATURE_RSP(0xFFFFFFFFFFFFFFFF)
            globals.ll_peripheral_feature_req_recv = True
            globals.ll_feature_rsp_sent_time = time.time_ns()
            globals.ll_feature_rsp_sent = True
            globals.current_ll_ctrl_state.ll_features_received = True
            globals.current_ll_ctrl_state.ll_peripheral_features = ll_features
            globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy = True if ((ll_features >> 8) & 0x1 == 1) else False
            print(f"-> Features received via {LL_opcode_to_str[ll_ctl_opcode]}. Moving to next phase")
            return True

####################################################################################
# LL_FEATURES_REQ/RSP because it's the second most useful after LL_VERSION_IND
####################################################################################
def incoming_LL_FEATURE_RSP(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global ll_feature_req_sent, ll_feature_rsp_recv

    if(globals.ll_feature_req_sent and not globals.ll_feature_rsp_recv):
        if(actual_body_len == 0x0B):
            header_ACID, ll_len_ACID, ll_ctl_opcode, ll_features = unpack("<BBBQ", dpkt.body[:11])
            vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, ll_features)
            if(ll_ctl_opcode == opcode_LL_FEATURE_REQ):
               # Invalid, Peripheral shouldn't ever send this, ignore
               return True
            elif(ll_ctl_opcode == opcode_LL_FEATURE_RSP):
               globals.ll_feature_rsp_recv = True
               print(f"--> LL_FEATUREs phase done, moving to next phase")
               clear_pending_packet_state()
               globals.current_ll_ctrl_state.ll_features_received = True
               globals.current_ll_ctrl_state.ll_peripheral_features = ll_features
               globals.current_ll_ctrl_state.ll_peripheral_features_supports_2M_phy = True if ((ll_features >> 8) & 0x1 == 1) else False
               # TODO: check features bit index 5 to see if it support "LE Data Packet Length Extension", and if not, don't bother with manage_LL_LENGTH_REQ?
               return True


####################################################################################
# LL_LENGTH_REQ to try and get more data in less packets
####################################################################################

def incoming_LL_LENGTHs(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global ll_length_rsp_recv, ll_length_req_recv

    # Process LL_LENGTH_REQ or LL_LENGTH_RSP or LL_UNKNOWN_RSP/LL_REJECT_IND (which is technically possible if the target was a v4.0 or v4.1 where LL_LENGTH_REQ didn't exist yet.)
    # If we do a PHY change, we could get a new LL_LENGTH_REQ from the Peripheral, so the PHY change procedure sets globals.ll_length_req_recv = False even if it was previously True
    if(not globals.current_ll_ctrl_state.ll_length_negotiated):
        if(actual_body_len == 11):
            header_ACID, ll_len_ACID, ll_ctl_opcode, max_rx_octet, max_rx_time, max_tx_octet, max_tx_time = unpack("<BBBHHHH", dpkt.body[:11])
            # Treat an LL_LENGTH_REQ sent by the Peripheral as equivalent to an LL_LENGTH_RSP
            if(ll_ctl_opcode == opcode_LL_LENGTH_RSP):
                globals.ll_length_rsp_recv = True
                update_LL_LENGTH_state(opcode_LL_LENGTH_RSP, "Received", ll_length_max_rx_octet=max_rx_octet, ll_length_max_tx_octet=max_tx_octet)
                vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, max_rx_octet, max_rx_time, max_tx_octet, max_tx_time)
                print(f"--> LL_LENGTH* phase done, ({LL_opcode_to_str[ll_ctl_opcode]} received). Moving to next phase")
                clear_pending_packet_state()
                return True
            if(ll_ctl_opcode == opcode_LL_LENGTH_REQ):
                # Echo back whatever parameters they sent us
                send_LL_LENGTH_RSP(max_rx_octet, max_rx_time, max_tx_octet, max_tx_time) # Send just to make the Peripheral's state machine happy
                globals.ll_length_rsp_recv = True
                globals.ll_length_req_recv = True
                update_LL_LENGTH_state(opcode_LL_LENGTH_REQ, "Received", ll_length_max_rx_octet=max_rx_octet, ll_length_max_tx_octet=max_tx_octet)
                vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, max_rx_octet, max_rx_time, max_tx_octet, max_tx_time)
                print(f"--> LL_LENGTH* phase done, ({LL_opcode_to_str[ll_ctl_opcode]} received). Moving to next phase")
                globals.current_ll_ctrl_state.ll_ctrl_pkt_pending = False # FIXME: should this be set here?
                return True

####################################################################################
# LL_VERSION_IND due to some devices requiring it
####################################################################################
def incoming_LL_VERSION_IND(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global ll_version_ind_sent, ll_version_ind_sent_time, ll_version_ind_recv

    # Check for any incoming LL_VERSION_IND
    # This could come in before we request it, so don't make ll_version_ind_sent a requirement
    if(not globals.current_ll_ctrl_state.ll_version_received):
        if(actual_body_len == 0x08):
            header_ACID, ll_len_ACID, ll_ctl_opcode, version, company_id, subversion = unpack("<BBBBHH", dpkt.body[:8])
            vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, version, company_id, subversion)
            if(ll_ctl_opcode == opcode_LL_VERSION_IND):

                # TODO: in the future check known Broadcom IDs if they're known to be exclusive to Apple
                if (globals.skip_apple and (company_id == 0x004C or company_id == 0x4C00)):
                    vprint("Apple device detected based on LL_VERSION_IND, exiting!")
                    exit(0x0A)

                globals.ll_version_ind_recv = True
                print(f"--> LL_VERSION_IND phase done, moving to next phase")
                clear_pending_packet_state()
                globals.current_ll_ctrl_state.ll_version_received = True
                globals.current_ll_ctrl_state.ll_version_state = globals.ll_packet_names_to_states["Received"]
                # FWIW I've found that an iPad won't proceed with responding to the ATT_EXCHANGE_MTU_REQ if I haven't replied to their LL_VERSION_IND
                # So this needs to be sent regardless of whether we've already receive an LL_VERSION_IND from the Peripheral (as long as we haven't already sent one)
                if(not globals.ll_version_ind_sent):
                    send_LL_VERSION_IND(6, 0x1337, 0x1337)
                    globals.ll_version_ind_sent = True
                    globals.ll_version_ind_sent_time = time.time_ns()
                # We're not going to update the state though because we don't want to preclude other packets being sent
                return True

####################################################################################
# LL_PHY_REQ/RSP due to some devices requiring it
####################################################################################
def incoming_LL_PHYs(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global ll_phy_req_recv, ll_phy_rsp_sent, ll_phy_rsp_sent_time

    # The starting and ending state
    # ll_phy_req_sent = 0 || ll_phy_req_recv = 0 : We haven't started. Check if the current packet is a Peripheral-initiated LL_PHY_REQ, and if not, send LL_PHY_REQ
    # ll_phy_rsp_recv = 1 || ll_phy_rsp_sent = 1 : We're done due to either way being done

    # The 8 possible states:

    # Central-initiated LL_PHY_REQ
    # ll_phy_req_sent = 0 && ll_phy_rsp_recv = 0 : We haven't started.
    # ll_phy_req_sent = 0 && ll_phy_rsp_recv = 1 : Should be an impossible state, but of course things can misbehave.
    # ll_phy_req_sent = 1 && ll_phy_rsp_recv = 0 : REQ sent, RSP pending
    # ll_phy_req_sent = 1 && ll_phy_rsp_recv = 1 : We're done, because we got the LL_PHY_RSP we requested

    # Peripheral-initiated LL_PHY_REQ
    # ll_phy_req_recv = 0 && ll_phy_rsp_sent = 0: We haven't started.
    # ll_phy_req_recv = 0 && ll_phy_rsp_sent = 1: Impossible state, because we won't send an LL_PHY_RSP unless we get an LL_PHY_REQ
    # ll_phy_req_recv = 1 && ll_phy_rsp_sent = 0: Temporary state. As soon as we get the REQ we send the RSP
    # ll_phy_req_recv = 1 && ll_phy_rsp_sent = 1: We're done, because we sent an LL_PHY_RSP in response to an LL_PHY_REQ

    if(not globals.ll_phy_rsp_recv and not globals.ll_phy_rsp_sent):
        # Check incoming packet first
        if(actual_body_len == 0x05):
            header_ACID, ll_len_ACID, ll_ctl_opcode, tx_phys, rx_phys = unpack("<BBBBB", dpkt.body[:5])
            vmultiprint(header_ACID, ll_len_ACID, ll_ctl_opcode, tx_phys, rx_phys)
            # Check for incoming Peripheral-initiated LL_PHY_REQ
            if(ll_ctl_opcode == opcode_LL_PHY_REQ): # Send the LL_PHY_RSP regardless of whether we already sent the LL_PHY_REQ or not
                globals.ll_phy_req_recv = True
                # Make our lives easier by just rejecting any incoming LL_PHY_REQ and initiating our own LL_PHY_REQ
                # TODO check features if the other side supports it?
                send_LL_REJECT_EXT_IND(ll_ctl_opcode, 0x0C)

            # Check for incoming LL_PHY_RSP
            if(ll_ctl_opcode == opcode_LL_PHY_RSP):
                globals.ll_phy_rsp_recv = True
                globals.ll_phy_rsp_recv_time = time.time_ns()
                clear_pending_packet_state()
                print(f"--> LL_PHY* phase done, moving to next phase")
                return True

####################################################################################
# Reject anyone sending us a LL_POWER_CONTROL_REQ by saying we can't change TX power
####################################################################################

def incoming_LL_POWER_CONTROL_REQ(actual_body_len, dpkt):
    global current_ll_ctrl_state
    global ll_length_rsp_recv, ll_length_req_recv

    # This is essentially rejecting the LL_POWER_CONTROL_REQ
    send_LL_POWER_CONTROL_RSP(1, 1, 0, 126, 255)

#################################################################################################################
# Function to call all the sub-functions to meet all the prerequisites of various devices to GET ALL THE LL CTRL!
#################################################################################################################
def stateful_LL_CTRL_incoming_handler(actual_body_len, ll_ctl_opcode, dpkt):
    ####################################################################################
    # LL_FEATURE_REQ/RSP due to some devices requiring it
    ####################################################################################
    # I've found that an iPad won't proceed with responding to the ATT_EXCHANGE_MTU_REQ
    # if I haven't replied to their LL_PERIPHERAL_FEATURE_REQ. So adding that too
    # I found I can just send an LL_VERSION_IND w/ Version = 4 and they'll not send it and proceed!
    # However on Zephyr they send an LL_PERIPHERAL_FEATURE_REQ as the first thing,
    # So now I need to handle this
    if(ll_ctl_opcode == opcode_LL_PERIPHERAL_FEATURE_REQ):
        incoming_LL_PERIPHERAL_FEATURE_REQ(actual_body_len, dpkt)

    ####################################################################################
    # LL_FEATURES_REQ/RSP because it's the second most useful after LL_VERSION_IND
    ####################################################################################
    elif(ll_ctl_opcode == opcode_LL_FEATURE_REQ or ll_ctl_opcode == opcode_LL_FEATURE_RSP):
        incoming_LL_FEATURE_RSP(actual_body_len, dpkt)

    ####################################################################################
    # Handling for LL_PHY_REQ and LL_PHY_RSP (get on to 2M PHY ASAP)
    ####################################################################################
    elif(ll_ctl_opcode == opcode_LL_PHY_REQ or ll_ctl_opcode == opcode_LL_PHY_RSP):
        incoming_LL_PHYs(actual_body_len, dpkt)

    ####################################################################################
    # LL_VERSION_IND due to some devices requiring it
    ####################################################################################
    elif(ll_ctl_opcode == opcode_LL_VERSION_IND):
        incoming_LL_VERSION_IND(actual_body_len, dpkt)

    ####################################################################################
    # LL_LENGTH_REQ to try and get more data in less packets
    # Handle this after other types because the Peripheral might re-request after PHY change
    ####################################################################################
    elif(ll_ctl_opcode == opcode_LL_LENGTH_REQ or ll_ctl_opcode == opcode_LL_LENGTH_RSP):
        incoming_LL_LENGTHs(actual_body_len, dpkt)

    ####################################################################################
    # Reject any opcode_LL_POWER_CONTROL_REQ
    ####################################################################################
    elif(ll_ctl_opcode == opcode_LL_POWER_CONTROL_REQ):
        incoming_LL_POWER_CONTROL_REQ(actual_body_len, dpkt)

    ####################################################################################
    # Handle incoming error messages that can occur in response to our LL_CTRL packets
    ####################################################################################
    elif(ll_ctl_opcode == opcode_LL_UNKNOWN_RSP or ll_ctl_opcode == opcode_LL_REJECT_IND or ll_ctl_opcode == opcode_LL_REJECT_EXT_IND):
        incoming_LL_errors(actual_body_len, dpkt)

    # Reject any other LL control packets the Peripheral sends to us
    else:
        send_LL_REJECT_EXT_IND(ll_ctl_opcode, 0x0C) # 0x0C = "The Command Disallowed error code indicates that the command requested cannot be executed because the Controller is in a state where it cannot process this command at this time."


def stateful_LL_CTRL_outgoing_handler():
    # Need to wait for the first packet to be sent
    if(globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time):
        current_time = time.time_ns()
        time_diff = current_time - globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_time
    else:
        time_diff = 0
    # If it's been more than 30ms since we sent the last LL_CTRL packet, then we can assume we won't get a response, and should send a new one
    # Order here doesn't matter since it will be driven by the pending opcode
    if(time_diff > 30e6): # 30ms = 30e6 because time_diff is in nanoseconds
        pending_opcode = globals.current_ll_ctrl_state.last_sent_ll_ctrl_pkt_opcode
        if(pending_opcode == opcode_LL_LENGTH_REQ):
            if(globals.current_ll_ctrl_state.ll_length_negotiated):
                clear_pending_packet_state()
                return
            # If we sent a LL_LENGTH_REQ, then we need to wait for the LL_LENGTH_RSP
            # before we can send another LL_CTRL packet
            send_LL_LENGTH_REQ_and_update_state()
        elif(pending_opcode == opcode_LL_FEATURE_REQ):
            if(globals.current_ll_ctrl_state.ll_features_received):
                clear_pending_packet_state()
                return
            # If we sent a LL_LENGTH_REQ, then we need to wait for the LL_LENGTH_RSP
            # before we can send another LL_CTRL packet
            send_LL_FEATURE_REQ_and_update_state()
        elif(pending_opcode == opcode_LL_PHY_REQ):
            if(globals.ll_phy_rsp_recv):
                clear_pending_packet_state()
                return
            send_LL_PHY_REQ_and_update_state()
        elif(pending_opcode == opcode_LL_VERSION_IND):
            if(globals.current_ll_ctrl_state.ll_version_received):
                clear_pending_packet_state()
                return
            send_LL_VERSION_IND_and_update_state()

    # This is for sending the initial outbound packets we want to send
    elif(not globals.current_ll_ctrl_state.ll_ctrl_pkt_pending):
        # Send whatever next LL_CTRL packet we haven't sent yet
        if(not globals.current_ll_ctrl_state.ll_features_received):
            # Don't need to request features if we already know what they are
            send_LL_FEATURE_REQ_and_update_state()
        elif(not globals.current_ll_ctrl_state.ll_version_received):
            # FWIW I've found that an iPad won't proceed with responding to the ATT_EXCHANGE_MTU_REQ if I haven't replied to their LL_VERSION_IND
            # So this needs to be sent regardless of whether we've already receive an LL_VERSION_IND from the Peripheral
            send_LL_VERSION_IND_and_update_state()
        elif(globals.attempt_2M_PHY_update and globals.ll_version_ind_recv and not globals.ll_phy_req_sent):
            send_LL_PHY_REQ_and_update_state()
        elif (globals.attempt_2M_PHY_update and not globals.ll_phy_update_ind_sent and \
             ((globals.ll_phy_req_recv and globals.ll_phy_rsp_sent) or \
             (globals.ll_phy_req_sent and globals.ll_phy_rsp_recv))):
            # Only send an update request to devices supporting 2M PHY
            # Make sure both a REQ and a RSP were seen before sending the PHY update
            send_LL_PHY_UPDATE_IND_and_update_state(instant_offset=3)
        elif(not globals.ll_length_req_sent and not globals.current_ll_ctrl_state.ll_length_negotiated):
            # We handle response to any incoming
            send_LL_LENGTH_REQ_and_update_state()
