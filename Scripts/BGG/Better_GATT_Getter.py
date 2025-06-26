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
from BGG_Helper_L2CAP import *
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
    aparse.add_argument("-A", "--skip-apple", action="store_true", help="Skip Apple devices")
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
        globals.attempt_2M_PHY_update = True
        globals.current_ll_ctrl_state.supported_PHYs = 0x2
    else:
        globals.current_ll_ctrl_state.supported_PHYs = 0x1

    if(args.skip_apple):
        globals.skip_apple = True

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

    linux_retry_count = 0
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
                    globals._aa = globals.hw.initiate_conn(bdaddr_bytes, not args.public, interval=10, latency=0, timeout=50)
                    create_pcap_CONNECT_IND(args, bdaddr_bytes, globals._aa, central_bdaddr_bytes)
                else:
                    linux_retry_count += 1
                    if(linux_retry_count == 4):
                        print("Connect timeout... you will need to restart the script")
                        exit(-2)
                    else:
                        time.sleep(1)
                        print(f"Connect timeout... restart attempt {linux_retry_count} of 3")
                        globals._aa = globals.hw.initiate_conn(bdaddr_bytes, not args.public)
                        create_pcap_CONNECT_IND(args, bdaddr_bytes, globals._aa, central_bdaddr_bytes)

    except KeyboardInterrupt:
        # Formally tear down with an LL_TERMINATE_IND, otherwise it will be harder to re-connect again afterwards,
        # because some devices may keep the connection open too long, and don't start advertising again right away
        # 0x13 = error code "Remote user terminated connection"
        print("Terminating connection with LL_TERMINATE_IND")
        send_LL_TERMINATE_IND()
        time.sleep(.1)

        exit(-1)

# Check for Apple Advertisements:
# Of course this can have a false positive due to iBeacons (e.g. like Tesla uses),
# but on balance I'd rather skip a few iBeaconing things than collect more Apple devices
def apple_advertisement(dpkt, actual_body_len):
    # Check only if it's a type that has AdvData (ADV_IND (0x00), ADV_NONCONN_IND (0x02), SCAN_RSP (0x04), ADV_SCAN_IND (0x06))
    if((dpkt.pdutype == 'ADV_IND' or dpkt.pdutype == 'ADV_NONCONN_IND' or \
        dpkt.pdutype == 'SCAN_RSP' or dpkt.pdutype == 'ADV_SCAN_IND') and \
        len(dpkt.adv_data) >= 4): # at least: 1 byte AdvData length + 1 byte type + 2 byte Company ID (in the case of MSD)
        adv_data_len = len(dpkt.adv_data)
        i = 0
        while i < adv_data_len:
            # Get the length of the next data item
            adv_data_item_len = dpkt.adv_data[i]
            adv_data_item_type = dpkt.adv_data[i+1]
            if(adv_data_item_type == 0xFF):
                company_id, = unpack("<H", dpkt.adv_data[i+2:i+4])
                # Apple has had endianness issues in the past, so check both endiannesses
                if(company_id == 0x004C or company_id == 0x4C00):
                    return True
                i += adv_data_item_len + 1 # +1 for the length byte
            else:
                i += adv_data_item_len + 1 # +1 for the length byte

    return False

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

    # If skipping Apple devices is enabled, check if the incoming packet is an advertisement
    # and if so, check if it has an MSD with the Apple Company ID
    if(globals.skip_apple):
        if(apple_advertisement(dpkt, actual_body_len)):
            vprint("Apple device detected based on Advertisement Company ID, exiting!")
            exit(0x0A)

    if(actual_body_len >= 3):
        header_ACID, ll_len_ACID, ll_ctl_opcode = unpack("<BBB", dpkt.body[:3])
        # Check if it's a LL control packet (LLID = 0b11)
        if((header_ACID & 0x3) == 0x3):
            stateful_LL_CTRL_incoming_handler(actual_body_len, ll_ctl_opcode, dpkt)
            # Send any LL_CTRL packets we need to send based on updates due to incoming LL_CTRL packets
            stateful_LL_CTRL_outgoing_handler()
        else:
            # Check for any L2CAP_CONNECTION_PARAMETER_UPDATE_REQ to reject (for now)
            stateful_incoming_L2CAP_handler(actual_body_len, dpkt)
            # Begin GATT enumeration process
            stateful_GATT_getter(actual_body_len, dpkt)
            # Get SMP information once GATT enumeration is done
            handle_SMP_Pairing(actual_body_len, dpkt, max_key_size=0x10)

    # Use empty packets as an opportunity see if we need to send any further packets
    elif(actual_body_len == 2):
        # Send any LL_CTRL packets we need to send
        stateful_LL_CTRL_outgoing_handler()
        stateful_incoming_L2CAP_handler(actual_body_len, dpkt)
        stateful_GATT_getter(actual_body_len, dpkt)
        handle_SMP_Pairing(actual_body_len, dpkt, max_key_size=0x10)

    # Current exit conditions
    if(globals.smp_legacy_pairing_rsp_recv or globals.smp_SC_pairing_rsp_recv):
        print_and_exit()

if __name__ == "__main__":
    main()
