# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

# Activate venv before any other imports
import os
import sys
from pathlib import Path
from handle_venv import activate_venv
activate_venv()

from Cryptodome.Cipher import AES
import random
import globals
from BGG_Helper_All import *

opcode_SMP_Pairing_Req      = 0x01
opcode_SMP_Pairing_Rsp      = 0x02
opcode_SMP_Pairing_Confirm  = 0x03
opcode_SMP_Pairing_Random   = 0x04
opcode_SMP_Pairing_Failed   = 0x05

####################################################################################################
# Begin basic implemention of BT crypto primitives needed for SMP pairing
####################################################################################################
# From "2.2.1 Security function e", Core Spec 5.4 p.1550
def e(k, plaintext):
    aes = AES.new(k, AES.MODE_ECB)
    return aes.encrypt(plaintext)


# Just something to xor bytes together for c1
def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


# From "2.2.3 Confirm value generation function c1 for LE legacy pairing", Core Spec 5.4 p.1551
# preq = pairing request (all 7 bytes of SMP packet)
# pres = pairing response (all 7 bytes of SMP packet)
# iat = initiator address type (0x00 = public, 0x01 = random)
# ia = initiator address (Central BDADDR)
# rat = responder address type (0x00 = public, 0x01 = random)
# ra = responder address (Peripheral BDADDR)
def c1(k, r, pres, preq, iat, ia, rat, ra):
    print(f"r = {r.hex()}")
    ia = bytes.fromhex(ia.replace(":",""))
    ra = bytes.fromhex(ra.replace(":",""))
    pres = pres[::-1]
    preq = preq[::-1]
    p1 = pres + preq + v1b(rat) + v1b(iat)
    print(f"p1 reversed = {p1[::-1].hex()}")
    p2 = b"\x00\x00\x00\x00" + ia + ra
    print(f"p2 reversed = {p2[::-1].hex()}")
    xb1 = xor_bytes(p1, r)
    print(f"xb1 reversed = {xb1[::-1].hex()}")
    tmp = e(k, xb1)
    print(f"tmp1 reversed w/ xb1 reversed = {tmp[::-1].hex()}")
    xb2 = xor_bytes(tmp, p2)
    print(f"xb2 reversed = {xb2[::-1].hex()}")
    tmp2 = e(k, xb2)
    print(f"tmp2 reversed with xb2 reversed = {tmp2[::-1].hex()}")
    # Reverse the byte order of tmp2 so that it can just be sent as-is in the SMP packet
    return tmp2[::-1]

####################################################################################################
# Begin SMP pairing functions
####################################################################################################

def send_SMP_Pairing_Request(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist):
    global opcode_SMP_Pairing_Req
    global preq
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0007 (1 byte opcode + 6 1-byte params )
    # CID = 0x0006 (SMP)
    # Opcode = 0x01 (opcode_SMP_Pairing_Req)
    # IO Capabilities = io_cap
    # OOB Data = oob_data
    # AuthReq = auth_req
    # Maximum Encryption Key Size = max_key_size
    # Initiator Key Distribution / Generation = init_key_dist
    # Responder Key Distribution / Generation = resp_key_dist
    payload_bytes = (  v1b(opcode_SMP_Pairing_Req)
                     + v1b(io_cap)
                     + v1b(oob_data)
                     + v1b(auth_req)
                     + v1b(max_key_size)
                     + v1b(init_key_dist)
                     + v1b(resp_key_dist) )
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.SMP_CID_bytes + payload_bytes)
    vprint(f"Sent SMP pairing request")
    globals.preq = payload_bytes # For use later in c1


def send_SMP_Confirm_Legacy(confirm_value):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0007 (1 byte opcode + 6 1-byte params )
    # CID = 0x0006 (SMP)
    # Opcode = 0x03 (opcode_SMP_Pairing_Confirm)
    # Confirm Value = 16-byte value calculated by function c1
    payload_bytes = ( v1b(opcode_SMP_Pairing_Confirm) + confirm_value )
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.SMP_CID_bytes + payload_bytes)
    vprint(f"Sent SMP pairing confirm (legacy)")


def send_SMP_Random(random_value):
    # LLID = 2 (L2CAP w/o fragmentation)
    # L2CAP length = 0x0007 (1 byte opcode + 6 1-byte params )
    # CID = 0x0006 (SMP)
    # Opcode = 0x04 (opcode_SMP_Pairing_Random)
    # Random Value = 16-byte value (LP_RAND_I) used as intput to function c1 during confirm value generation
    payload_bytes = ( v1b(opcode_SMP_Pairing_Random) + random_value )
    payload_len_bytes = v2b(len(payload_bytes))
    write_outbound_pkt(2, payload_len_bytes + globals.SMP_CID_bytes + payload_bytes)
    vprint(f"Sent SMP pairing random")

###############################################################################################################
# Try to pair w/ Legacy Just Works to see if the device supports that
###############################################################################################################

def incoming_SMP_Pairing(smp_opcode, actual_body_len, dpkt, max_key_size=0x10):
    global all_characteristic_handles_recv, handles_with_error_rsp
    global smp_legacy_pairing_req_sent, smp_legacy_pairing_rsp_recv
    global pres

    if(globals.smp_legacy_pairing_req_sent and not globals.smp_legacy_pairing_rsp_recv):
        if(smp_opcode == opcode_SMP_Pairing_Rsp and actual_body_len == 13):
            globals.pres = dpkt.body[6:13] # For use later in c1
            io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist = unpack("<BBBBBB", dpkt.body[7:13])
            vmultiprint(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist)
            # if(not globals.smp_SC_pairing_req_sent):
            globals.smp_legacy_pairing_rsp_recv = True
            # else:
            #     globals.smp_SC_pairing_rsp_recv = True
            # return
            # print_and_exit()
        elif(smp_opcode == opcode_SMP_Pairing_Failed and actual_body_len == 8):
            globals.smp_legacy_pairing_rsp_recv = True
            # # Try Secure Connections pairing
            # if(not globals.smp_SC_pairing_req_sent):
            #     io_cap = 0x03 # 04 = KeyboardDisplay # 0x03 = NINO
            #     oob_data = 0x00
            #     auth_req = 0x0C # SC = 0x8 | MITM = 0x4
            #     max_key_size = 0x10 # Set to 0x07 for KNOB test
            #     init_key_dist = 0x00 # 0x08
            #     resp_key_dist = 0x00 # 0x0a
            #     send_SMP_Pairing_Request(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist)
            #     globals.smp_SC_pairing_req_sent = True
            # else:
            #     globals.smp_SC_pairing_rsp_recv = True
            # return


def incoming_SMP_Confirm_legacy(smp_opcode, actual_body_len, dpkt):
    global smp_pairing_confirm_legacy_recv

    if(globals.smp_pairing_confirm_legacy_sent and not globals.smp_pairing_confirm_legacy_recv):
        if(smp_opcode == opcode_SMP_Pairing_Confirm and actual_body_len == 23):
            confirm_value = dpkt.body[7:23]
            print(f"confirm_value = {confirm_value.hex()}")
            globals.smp_pairing_confirm_legacy_recv = True

def incoming_SMP_Random(smp_opcode, actual_body_len, dpkt):
    global smp_pairing_random_recv

    if(globals.smp_pairing_random_sent and not globals.smp_pairing_random_recv):
        if(smp_opcode == opcode_SMP_Pairing_Random and actual_body_len == 23):
            random_value = dpkt.body[7:23]
            print(f"random_value = {random_value.hex()}")
            globals.smp_pairing_random_recv = True


def outgoing_SMP_Pairing(max_key_size=0x10):
    global all_characteristic_handles_recv, handles_with_error_rsp
    global smp_legacy_pairing_req_sent

    if(globals.all_characteristic_handles_recv and not globals.smp_legacy_pairing_req_sent):
        io_cap = 0x03 # 04 = KeyboardDisplay # 0x03 = NINO
        oob_data = 0x00
        auth_req = 0x00 # 0x2C # SC = 0b1 + MITM = 0b1 +  Bonding 0b10 == 0b1101 # 0x00 # Insecure
        #max_key_size = 0x10 # Set to 0x07 for KNOB test
        init_key_dist = 0x00 # 0x08
        resp_key_dist = 0x00 # 0x0a
        send_SMP_Pairing_Request(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist)
        globals.smp_legacy_pairing_req_sent = True

def outgoing_SMP_Confirm_Legacy():
    global smp_pairing_confirm_legacy_sent

    if(globals.smp_legacy_pairing_rsp_recv and not globals.smp_pairing_confirm_legacy_sent):
        k = v16b(0x00000000000000000000000000000000)
        globals.lp_rand_i = v16b(0x5783D52156AD6F0E6388274EC6702EE0)
        confirm_value = c1(k, globals.lp_rand_i, globals.pres, globals.preq, 0x01, globals.central_bdaddr, 0x00 if globals.peripheral_bdaddr_type_public else 0x01, globals.peripheral_bdaddr)
        print(f"actual confirm_value = {confirm_value.hex()}")
        send_SMP_Confirm_Legacy(confirm_value)
        globals.smp_pairing_confirm_legacy_sent = True

def outgoing_SMP_Random():
    global smp_pairing_confirm_legacy_sent

    if(globals.smp_pairing_confirm_legacy_recv and not globals.smp_pairing_random_sent):
        r = globals.lp_rand_i[::-1] # Reverse the byte order. Just so it doesn't need to be done in send_SMP_Random
        send_SMP_Random(r)
        globals.smp_pairing_random_sent = True