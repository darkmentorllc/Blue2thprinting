# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

import argparse, sys, csv, time, inspect
from struct import unpack
from binascii import unhexlify
from sniffle.pcap import PcapBleWriter
from sniffle.constants import BLE_ADV_AA
from sniffle.sniffle_hw import SniffleHW, PacketMessage, DPacketMessage, DebugMessage, StateMessage, SnifferState
from sniffle.packet_decoder import (AdvaMessage, AdvDirectIndMessage, AdvExtIndMessage,
                                    ScanRspMessage, DataMessage, str_mac)
import globals

######################################################################################
# Helpers for when converting python variables to byte arrays
# just to make the code more terse

# "Variable to 1-byte byte array" (variable,1-byte)
def v1b(var):
 return var.to_bytes(1, byteorder='little')


# "Variable to 2-byte-little-endian byte array" (variable,2-bytes)
def v2b(var):
 return var.to_bytes(2, byteorder='little')


# "Variable to 4-byte-little-endian byte array" (variable,4-bytes)
def v4b(var):
 return var.to_bytes(4, byteorder='little')


# "Variable to 8-byte-little-endian byte array" (variable,8-bytes)
def v8b(var):
 return var.to_bytes(8, byteorder='little')


######################################################################################
# Helper functions for verbose printing

# Print when verbose mode enabled (i.e. any time -q isn't passed on CLI)
def vprint(fmt):
    if(globals.verbose):
        print(fmt)


def vmultiprint(*args):
    # Get the name of the calling function and its arguments
    frame = inspect.currentframe().f_back
    call_args = frame.f_locals

    # Iterate over all arguments and print their names and values
    for arg in args:
        # Find the name of the variable corresponding to the value
        for name, value in call_args.items():
            if value is arg:
                # Print the variable name and its value in hex format
                vprint(f"{name} = 0x{value:x}")
                break

######################################################################################
# Helper functions for writing to the pcap

# This creates a fake CONNECT_IND packet to insert into the pcap,
# because Wireshark won't know which device is the Central vs. Peripheral
# if it doesn't see who sent the CONNECT_IND, and then it will display
# things incorrectly
# The real CONNECT_IND is created by the Sniffle firmware on the TI chip
# but it is not currently exposed to the Python code for capture
# Copied from https://github.com/nccgroup/Sniffle/issues/83 and modified
def create_pcap_CONNECT_IND(args, mac_bytes, _aa, central_bdaddr_bytes):
    t0 = time.time()
    header = 0x45 # Ad type 0x5 (CONNECT_IND) | 0x40 # TxAdd always = 1 because Sniffle always picks a random BDADDR
    if(not args.public):
        header |= 0x80 # RxAdd = 1 if -P is *not* passed, else this remains 0
    header_bytes = header.to_bytes(1, byteorder='little')
    length_byte = b'\x22' # CONNECT_IND is always 34 bytes large
    peripheral_bdaddr_bytes = bytes(mac_bytes)
    aa_bytes = _aa.to_bytes(4, byteorder='little')
    crc_init_bytes = b'\x56\x34\x12' # randomly generated. What are the odds?!
    win_size_bytes = b'\x01' # WinSize of 1 = transmitWindowSize of 1.25ms
    win_offset_bytes = b'\x00\x00' # WinOffset of 0 = transmitWindowOffset of 0ms
    interval_bytes = b'\x06\x00' # Interval of 6 = connInterval of 7.5ms
    latency_bytes = b'\x00\x00' # Latency of 0 = connPeripheralLatency of 0
    timeout_bytes = b'\x64\x00' # Timeout of 100 = connSupervisionTimeout of 1s
    channel_map_bytes = b'\xff\xff\xff\xff\x1f' # Use all channels
    hop_sca_byte = b'\x2a' # Hop of 10, sleep clock accuracy of 1 = 151-250ppm

    pdu = header_bytes + length_byte + central_bdaddr_bytes + peripheral_bdaddr_bytes \
          + aa_bytes + crc_init_bytes + win_size_bytes + win_offset_bytes + interval_bytes \
          + latency_bytes + timeout_bytes + channel_map_bytes + hop_sca_byte
    pkt = DPacketMessage.from_body(pdu, False)
    pkt.ts_epoch = time.time()
    pkt.ts = pkt.ts_epoch - t0
    pkt.aa = 0x8E89BED6
    globals.pcwriter.write_packet_message(pkt)

# Function to create a fake packet in the right format to be written to the pcap
# Copied from https://github.com/nccgroup/Sniffle/issues/83
def write_outbound_pkt(llid, body):
    vprint("Sending & creating to save packet with the following bytes:")
    vprint(f"llid = {llid}") # The LLID field is the first byte of the LL header
                             # and Sniffle's cmd_transmit() will just figure out
                             # the rest of the LL header for you on the firmware side.
                             # (It's actually the TI firmware doing most of it.)
    vprint(f"body = {body}")

    globals.hw.cmd_transmit(llid, body)

    body_len = len(body) # This is the LL header length field
    vprint(f"body_len = {body_len}")

    full_bytes = v1b(llid) + v1b(body_len) + body # Note that this won't be fully accurate
                                                  # because we didn't set all the other LL header fields
    vprint(full_bytes)

    # FIXME: this isn't capturing the channel correctly
    pkt = DPacketMessage.from_body(full_bytes, True)
    pkt.ts_epoch = time.time()
    pkt.ts = pkt.ts_epoch - globals.hw.decoder_state.first_epoch_time
    pkt.aa = globals._aa

    if globals.pcwriter:
        globals.pcwriter.write_packet_message(pkt)
