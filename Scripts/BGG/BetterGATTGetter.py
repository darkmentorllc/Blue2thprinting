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
    aparse.add_argument("-c", "--advchan", default=37, choices=[37, 38, 39], type=int,
            help="Advertising channel to listen on")
    aparse.add_argument("-b", "--bdaddr", default=None, help="Specify target Bluetooth Device Address (BDADDR)")
    aparse.add_argument("-l", "--longrange", action="store_const", default=False, const=True,
            help="Use long range (coded) PHY for primary advertising")
    aparse.add_argument("-P", "--public", action="store_const", default=False, const=True,
            help="Supplied BDADDR address is public")
    aparse.add_argument("-o", "--output", default=None, help="PCAP output file name")
    aparse.add_argument("-q", "--quiet", action="store_true",
            help="Don't display empty packets")
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
    globals._aa = globals.hw.initiate_conn(bdaddr_bytes, not args.public)

    if not (args.output is None):
        globals.pcwriter = PcapBleWriter(args.output)
        create_pcap_CONNECT_IND(args, bdaddr_bytes, globals._aa, central_bdaddr_bytes)

    try:
        while True:
            msg = globals.hw.recv_and_decode()
            ret = print_sniffle_message_or_packet(msg, args.quiet)
            if(ret == "restart"):
                # Retry on macOS (which I'm detecting based on the serport string, which is different on Linux)
                if(not re.match(r"ttyUSB", args.serport)):
                    # It timed out. Go ahead and try to connect again
                    print("Connect timeout... restarting")
                    globals._aa = globals.hw.initiate_conn(bdaddr_bytes, not args.public)
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

##############################################################################################################
# Function to call all the sub-functions to meet all the prerequisites of various devices to GET ALL THE GATT!
##############################################################################################################
def stateful_GATT_getter(dpkt):

    # The point of actual_body_len is to iterate based on the known size of actual bytes that python is holding, not any ACID lengths
    actual_body_len = len(dpkt.body)
    # Don't waste time doing any of the below checks for empty PDUs
    # TODO: Allow these to proceed in the future just because they can trigger re-requests if a timeout has been exceeded (because they aren't callback-based)
#    if(actual_body_len == 2):
#       return
    vmultiprint(actual_body_len)

    ####################################################################################
    # LL_FEATURE_REQ/RSP due to some devices requiring it
    ####################################################################################
    # I've found that an iPad won't proceed with responding to the ATT_EXCHANGE_MTU_REQ
    # if I haven't replied to their LL_PERIPHERAL_FEATURE_REQ. So adding that too
    # I found I can just send an LL_VERSION_IND w/ Version = 4 and they'll not send it and proceed!
    # However on Zephyr they send an LL_PERIPHERAL_FEATURE_REQ as the first thing,
    # So now I need to handle this
    if(manage_LL_PERIPHERAL_FEATURE_REQ(actual_body_len, dpkt)):
        return # Don't proceed to next phases until a new packet comes in

    ####################################################################################
    # LL_LENGTH_REQ to try and get more data in less packets
    ####################################################################################
    manage_LL_LENGTH_REQ(actual_body_len, dpkt)

    ####################################################################################
    # LL_VERSION_IND due to some devices requiring it
    ####################################################################################
    manage_LL_VERSION_IND(actual_body_len, dpkt)

    ####################################################################################
    # LL_FEATURES_REQ/RSP because it's the second most useful after LL_VERSION_IND
    ####################################################################################
    manage_LL_FEATUREs(actual_body_len, dpkt)

    ####################################################################################
    # Handling for LL_PHY_REQ and LL_PHY_RSP
    ####################################################################################
    if(manage_LL_PHYs(actual_body_len, dpkt)):
        return # Don't proceed to next phases until a new packet comes in

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

    ###############################################################################################################
    # Try to pair w/ Legacy Just Works to see if the device supports that
    ###############################################################################################################
    handle_SMP_Pairing(actual_body_len, dpkt, max_key_size=0x10)

    # Current exit conditions
    if(globals.smp_legacy_pairing_rsp_recv or globals.smp_SC_pairing_rsp_recv):
#    if(globals.all_characteristic_handles_recv):
        print_and_exit()

def print_sniffle_message_or_packet(msg, quiet):
    global hw
    if isinstance(msg, PacketMessage):
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
    if not (quiet and isinstance(dpkt, DataMessage) and dpkt.data_length == 0 and globals.verbose):
        vprint(dpkt)

    # Record the packet if PCAP writing is enabled
    if globals.pcwriter:
        globals.pcwriter.write_packet_message(dpkt)

    stateful_GATT_getter(dpkt)

if __name__ == "__main__":
    main()
