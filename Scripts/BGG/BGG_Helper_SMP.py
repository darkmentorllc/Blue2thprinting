# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

import globals
from BGG_Helper_All import *

opcode_SMP_Pairing_Req = 0x01
opcode_SMP_Pairing_Rsp = 0x02
opcode_SMP_Pairing_Failed = 0x05

pairing_failure_reason_Pairing_Not_Supported = 0x05

def send_SMP_Pairing_Request(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist):
    global opcode_SMP_Pairing_Req
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
    packet_bytes = ( b'\x07\x00\x06\x00'
                     + v1b(opcode_SMP_Pairing_Req)
                     + v1b(io_cap)
                     + v1b(oob_data)
                     + v1b(auth_req)
                     + v1b(max_key_size)
                     + v1b(init_key_dist)
                     + v1b(resp_key_dist) )
    write_outbound_pkt(2, packet_bytes)
    vprint(f"Sent SMP pairing request")

###############################################################################################################
# Try to pair w/ Legacy Just Works to see if the device supports that
###############################################################################################################
# TODO! This hasn't actually been fully fleshed out yet
def handle_SMP_Pairing(actual_body_len, dpkt, max_key_size=0x10):
    global all_characteristic_handles_recv, handles_with_error_rsp
    global smp_legacy_pairing_req_sent, smp_legacy_pairing_rsp_recv
    if(globals.all_characteristic_handles_recv):
        if(not globals.smp_legacy_pairing_req_sent):
            vprint("HANDLES WITH ERRORS")
            for handle in sorted(globals.handles_with_error_rsp.keys()):
                #vprint(f"Handle {handle} = error code 0x{globals.handles_with_error_rsp[handle]:02x} = {att_error_strings[globals.handles_with_error_rsp[handle]]}")
                vprint(f"Handle {handle} = error code 0x{globals.handles_with_error_rsp[handle]:02x} = {globals.handles_with_error_rsp[handle]}")

            io_cap = 0x03 # 04 = KeyboardDisplay # 0x03 = NINO
            oob_data = 0x00
            auth_req = 0x00 # 0x2C # SC = 0b1 + MITM = 0b1 +  Bonding 0b10 == 0b1101 # 0x00 # Insecure
            #max_key_size = 0x10 # Set to 0x07 for KNOB test
            init_key_dist = 0x00 # 0x08
            resp_key_dist = 0x00 # 0x0a
            send_SMP_Pairing_Request(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist)
            globals.smp_legacy_pairing_req_sent = True
            return

        if(globals.smp_legacy_pairing_req_sent and not globals.smp_legacy_pairing_rsp_recv):
            actual_body_len = len(dpkt.body) # The point of actual_body_len is to iterate based on the known size of actual bytes that python is holding, not any ACID lengths
            vprint(f"actual_body_len = 0x{actual_body_len:02x}")
            if(actual_body_len >= 7):
                header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, smp_opcode  = unpack("<BBHHB", dpkt.body[:7])
                # Check if it's ATT (CID = 4) and header says it's l2cap w/o fragmentation (I can't handle fragments yet)
                if(cid_ACID == 0x0006 and (header_ACID & 0b10 == 0b10)):
                    vmultiprint(header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, smp_opcode)

                    # Check if it's a Pairing Response opcode
                    if(smp_opcode == opcode_SMP_Pairing_Rsp and actual_body_len == 13):
                        io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist = unpack("<BBBBBB", dpkt.body[7:13])
                        vmultiprint(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist)
                        if(not globals.smp_SC_pairing_req_sent):
                            globals.smp_legacy_pairing_rsp_recv = True
                        else:
                            globals.smp_SC_pairing_rsp_recv = True
                        return
                        # print_and_exit()
                    elif(smp_opcode == opcode_SMP_Pairing_Failed and actual_body_len == 8):
                        failure_reason, = unpack("<B", dpkt.body[7:8])
                        if(failure_reason == pairing_failure_reason_Pairing_Not_Supported):
                            globals.smp_legacy_pairing_rsp_recv = True
                            return
                        else:
                            # Try Secure Connections pairing
                            if(not globals.smp_SC_pairing_req_sent):
                                io_cap = 0x03 # 04 = KeyboardDisplay # 0x03 = NINO
                                oob_data = 0x00
                                auth_req = 0x0C # SC = 0x8 | MITM = 0x4
                                max_key_size = 0x10 # Set to 0x07 for KNOB test
                                init_key_dist = 0x00 # 0x08
                                resp_key_dist = 0x00 # 0x0a
                                send_SMP_Pairing_Request(io_cap, oob_data, auth_req, max_key_size, init_key_dist, resp_key_dist)
                                globals.smp_SC_pairing_req_sent = True
                            else:
                                globals.smp_SC_pairing_rsp_recv = True
                            return
