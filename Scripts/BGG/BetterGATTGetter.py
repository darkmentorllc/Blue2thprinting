#!/usr/bin/env python3

# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

# BetterGATTGetter2
# Replacement for using gatttool in Blue2thprinting
# Improvements include:
# - Awareness of Secondary Services (0x2801)
# - Capability to read Characteristic User Description (0x2901)
# - Logging error messages for all handles which we couldn't read from,
#   with an emphasis on knowing which are due to security constraints
#   like insufficient encryption/authentication/authorization/key size
# - Writing per-BDADDR logs, instead of a single global log file

import re
import math
import globals
from BGG_Helper_All import *
from BGG_Helper_LL import *
from BGG_Helper_ATT import *
from BGG_Helper_GATT import *
from BGG_Helper_SMP import *
from BGG_Helper_Output import *

def main():
    global target_bdaddr, target_bdaddr_type_public, verbose
    global hw, _aa, pcwriter

    aparse = argparse.ArgumentParser(description="Code to enumerate public GATT information")
    aparse.add_argument("-s", "--serport", default=None, help="Sniffer serial port name")
    aparse.add_argument("-c", "--advchan", default=37, choices=[37, 38, 39], type=int, help="Advertising channel to listen on")
    aparse.add_argument("-b", "--bdaddr", default=None, help="Specify target Bluetooth Device Address (BDADDR)")
    aparse.add_argument("-l", "--longrange", action="store_const", default=False, const=True, help="Use long range (coded) PHY for primary advertising")
    aparse.add_argument("-P", "--public", action="store_const", default=False, const=True, help="Supplied BDADDR address is public")
    aparse.add_argument("-o", "--output", default=None, help="PCAP output file name")
    aparse.add_argument("-q", "--quiet", action="store_true", help="Don't display empty packets")
    aparse.add_argument("-2", "--attempt-2M-PHY-update", action="store_true", help="Attempt to negotiate 2M PHY")
    args = aparse.parse_args()

    globals.hw = SniffleHW(args.serport)

    targ_specs = bool(args.bdaddr)
    if targ_specs < 1:
        print("Must specify target BDADDR address", file=sys.stderr)
        return

    # set the advertising channel (and return to ad-sniffing mode)
    globals.hw.cmd_chan_aa_phy(args.advchan, BLE_ADV_AA, 2 if args.longrange else 0)

    # pause after sniffing
    globals.hw.cmd_pause_done(True)

    # capture advertisements only
    globals.hw.cmd_follow(False)

    # turn off RSSI filter
    globals.hw.cmd_rssi()

    # Set TxPower to +5db (max?)
    globals.hw.cmd_tx_power(5)

    # initiator doesn't care about this setting, it always accepts aux
    globals.hw.cmd_auxadv(True)

    if(args.quiet):
        globals.verbose = False

    if(args.attempt_2M_PHY_update):
        globals.current_ll_ctrl_state.supported_PHYs = 0x2
    else:
        globals.current_ll_ctrl_state.supported_PHYs = 0x1

    if args.bdaddr:
        try:
            bdaddr_bytes = [int(h, 16) for h in reversed(args.bdaddr.split(":"))]
            if len(bdaddr_bytes) != 6:
                raise Exception("Wrong length!")
        except:
            print("BDADDR must be 6 colon-separated hex bytes", file=sys.stderr)
            return
        globals.hw.cmd_mac(bdaddr_bytes, False)

        globals.target_bdaddr = args.bdaddr
        globals.target_bdaddr_type_public = args.public

    # initiator/Central needs a BDADDR
    central_bdaddr_bytes = bytes(globals.hw.random_addr())

    # reset preloaded encrypted connection interval changes
    globals.hw.cmd_interval_preload()

    # zero timestamps and flush old packets
    globals.hw.mark_and_flush()

    # now enter initiator/Central mode
    globals._aa = globals.hw.initiate_conn(bdaddr_bytes, not args.public, interval=7, latency=0, timeout=50)

    if not (args.output is None):
        globals.pcwriter = PcapBleWriter(args.output)
        create_pcap_CONNECT_IND(args, bdaddr_bytes, globals._aa, central_bdaddr_bytes)

    try:
        while True:
            msg = globals.hw.recv_and_decode()
            ret = print_sniffle_message_or_packet(msg, args.quiet)
            # Only retry if we're not on Linux (where it doesn't work and gets into a broken state, unlike macOS)
            if(ret == "restart"):
                # Retry on macOS (which I'm detecting based on the serport string, which is different on Linux)
                if(not re.search(r"ttyUSB", args.serport)):
                    # It timed out. Go ahead and try to connect again
                    print("Connect timeout... restarting")
                    globals._aa = globals.hw.initiate_conn(bdaddr_bytes, not args.public, interval=7, latency=0, timeout=50)
                    create_pcap_CONNECT_IND(args, bdaddr_bytes, globals._aa, central_bdaddr_bytes)
                # Don't retry on Linux, because it doesn't work and gets into a broken state
                else:
                    print("Connect timeout... you will need to restart the script")
                    exit(-2)
    except KeyboardInterrupt:
        # Formally tear down with an LL_TERMINATE_IND, otherwise it will be harder to re-connect again afterwards,
        # because some devices may keep the connection open too long, and don't start advertising again right away
        # 0x13 = error code "Remote user terminated connection"
        print("Terminating connection with LL_TERMINATE_IND")
        send_LL_TERMINATE_IND()
        time.sleep(.1)

        exit(-1)

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
        # TODO: check features if it even supports 2M PHY?
        # Don't bother sending the Central-initiated LL_PHY_REQ if we've already sent an LL_PHY_REQ or LL_PHY_RSP
        elif(globals.ll_version_ind_recv and not globals.ll_phy_req_sent):
            send_LL_PHY_REQ_and_update_state()
        elif (not globals.ll_phy_update_ind_sent and \
             ((globals.ll_phy_req_recv and globals.ll_phy_rsp_sent) or \
             (globals.ll_phy_req_sent and globals.ll_phy_rsp_recv))):
            # Only send an update request to devices supporting 2M PHY
            # Make sure both a REQ and a RSP were seen before sending the PHY update
            send_LL_PHY_UPDATE_IND_and_update_state(instant_offset=3)
        elif(not globals.ll_length_req_sent and not globals.current_ll_ctrl_state.ll_length_negotiated):
            # We handle response to any incoming
            send_LL_LENGTH_REQ_and_update_state()

##############################################################################################################
# Function to call all the sub-functions to meet all the prerequisites of various devices to GET ALL THE GATT!
##############################################################################################################
def stateful_GATT_getter(actual_body_len, dpkt):

    ####################################################################################
    # Exchange ATT_MTU to try and get more data in less packets
    ####################################################################################
    manage_ATT_EXCHANGE_MTU(actual_body_len, dpkt)

    ####################################################################################
    # Some devices (like AppleTV) try to enumerate us. This rejects them.
    ####################################################################################
    manage_peripheral_info_requests(actual_body_len, dpkt)

    ####################################################################################
    # Send ATT_READ_BY_GROUP_TYPE_REQ for Primary (0x2800) Services
    ####################################################################################
    # Note: this is needed because there can be discontinuities in the handle ranges
    if(manage_GATT_Primary_Services(actual_body_len, dpkt)):
        return

    ####################################################################################
    # Send ATT_READ_BY_GROUP_TYPE_REQ for Secondary (0x2801) Services
    ####################################################################################
    # Note: this is needed because there can be discontinuities in the handle ranges
    if(manage_GATT_Secondary_Services(actual_body_len, dpkt)):
        return

    #################################################################################
    # Send ATT_FIND_INFORMATION_REQs to find all handles, declarations, & descriptors
    #################################################################################
    manage_ATT_FIND_INFORMATION(actual_body_len, dpkt)

    ################################################################################
    # Read all Services, Characteristics, and Characteristic Values from all handles
    ################################################################################
    manage_read_all_handles(actual_body_len, dpkt)

    # Current exit conditions
    if(globals.smp_legacy_pairing_rsp_recv or globals.smp_SC_pairing_rsp_recv):
        print_and_exit()

def print_sniffle_message_or_packet(msg, quiet):
    global hw
    global connEventCount
    if isinstance(msg, PacketMessage):
        globals.connEventCount = msg.event
        print_packet(msg, quiet)
    elif isinstance(msg, DebugMessage):
        print(msg)
    elif isinstance(msg, StateMessage):
        print(msg)
        if msg.new_state == SnifferState.CENTRAL:
            globals.hw.decoder_state.cur_aa = globals._aa
        if msg.new_state == SnifferState.PAUSED: # It has probably timed out trying to connect. Tell it to connect again!
            # ACTUALLY...Until ticket 103 is addressed, let's just early-exit if connection can't be established, to move on!
            return "restart"
            #exit(-2)
    vprint("")

msg_ctr = 0
def print_packet(dpkt, quiet):
    global current_ll_ctrl_state
    if not (quiet and isinstance(dpkt, DataMessage) and dpkt.data_length == 0 and globals.verbose):
        vprint(dpkt)

    # Record the packet if PCAP writing is enabled
    if globals.pcwriter:
        globals.pcwriter.write_packet_message(dpkt)

    # Check if the PHY has changed
    if(dpkt.phy == 0x01):
        globals.current_ll_ctrl_state.PHY_updated = True

    actual_body_len = len(dpkt.body)
    vmultiprint(actual_body_len)

    if(actual_body_len >= 3):
        header_ACID, ll_len_ACID, ll_ctl_opcode = unpack("<BBB", dpkt.body[:3])
        # Check if it's a LL control packet (LLID = 0b11)
        if((header_ACID & 0x3) == 0x3):
            stateful_LL_CTRL_incoming_handler(actual_body_len, ll_ctl_opcode, dpkt)
            # Send any LL_CTRL packets we need to send based on updates due to incoming LL_CTRL packets
            stateful_LL_CTRL_outgoing_handler()
        else:
            # Begin GATT enumeration process
            stateful_GATT_getter(actual_body_len, dpkt)
            # Get SMP information once GATT enumeration is done
            handle_SMP_Pairing(actual_body_len, dpkt, max_key_size=0x10)

    # Use empty packets as an opportunity see if we need to send any further packets
    elif(actual_body_len == 2):
        # Send any LL_CTRL packets we need to send
        stateful_LL_CTRL_outgoing_handler()
        stateful_GATT_getter(actual_body_len, dpkt)


if __name__ == "__main__":
    main()
