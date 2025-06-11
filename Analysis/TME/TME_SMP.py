########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# import re
# import struct
# import TME.TME_glob
from TME.TME_helpers import *
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_SMP import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

from colorama import Fore, Back, Style, init
init(autoreset=True)

# Returns 0 if there is no SMP info for this BDADDR in any of the SMP tables, else returns 1
def device_has_SMP_info(bdaddr):
    # Query the database for all GATT services
    values = (bdaddr,)
    query = "SELECT bdaddr FROM SMP_Pairing_Req_Res WHERE bdaddr = %s";
    SMP_result = execute_query(query, values)
    if(len(SMP_result) != 0):
        return 1;

    return 0;


def key_dist_print(who, key_dist):
    if((key_dist >> 0) & 1):
        qprint(f"{i4}{who} to send Long Term Key (LTK): requested.")
    else:
        qprint(f"{i4}{who} to send Long Term Key (LTK): not requested.")
    if((key_dist >> 1) & 1):
        qprint(f"{i4}{who} to send Identity Resolving Key (IDK): requested.")
    else:
        qprint(f"{i4}{who} to send Identity Resolving Key (IDK): not requested.")
    if((key_dist >> 2) & 1):
        qprint(f"{i4}{who} to send Connection Signature Resolving Key (CSRK): requested.")
    else:
        qprint(f"{i4}{who} to send Connection Signature Resolving Key (CSRK): not requested.")
    if((key_dist >> 3) & 1):
        qprint(f"{i4}{who} request to derive BR/EDR Link Key from LE LTK (Cross-Transport Key Derivation): requested.")
    else:
        qprint(f"{i4}{who} request to derive BR/EDR Link Key from LE LTK (Cross-Transport Key Derivation): not requested.")


def print_pairing_req_res(bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist):
    if(opcode == type_SMP_Pairing_Request):
        qprint(f"{i2}Pairing Request:")
    elif(opcode == type_SMP_Pairing_Response):
        qprint(f"{i2}Pairing Response:")

    qprint(f"{i3}Input/Output Capabilities: {smp_io_cap_strings[io_cap]}")
    if(io_cap == type_SMP_IO_Capabilities_NoInputNoOutput):
        qprint(Fore.RED + Style.BRIGHT + f"{i4}WARNING: If accepted, this pairing will lead to \"Just Works\" pairing, which is guaranteed-insecure against MitM attacks!")

    qprint(f"{i3}Authentication Requested Parameters:")
    if((auth_req & 0x03) == 0x00):
        qprint(f"{i4}Bonding (Long Term Key storage): not requested")
    elif((auth_req & 0x03) == 0x01):
        qprint(f"{i4}Bonding (Long Term Key storage): requested")
    else:
        qprint(f"{i4}Bonding (Long Term Key storage): invalid value (!= 0 or 1) sent")

    if(((auth_req >> 2) & 1) == 0):
        qprint(Fore.RED + Style.BRIGHT + f"{i4}Machine-in-the-Middle (MITM) protection: not requested!")
        qprint(Fore.RED + Style.BRIGHT + f"{i5}This will lead to pairing that is guaranteed-insecure against MitM attacks!")
    else:
        qprint(Fore.GREEN + Style.BRIGHT + f"{i4}Machine-in-the-Middle (MITM) protection: requested")

    if(((auth_req >> 3) & 1) == 0):
        qprint(Fore.RED + Style.BRIGHT + f"{i4}Secure Connection pairing: not requested!")
        qprint(Fore.RED + Style.BRIGHT + f"{i5}If accepted, this will lead to Legacy Pairing which is guaranteed-insecure against eavesdropping & MITM attacks!")
    else:
        qprint(Fore.GREEN + Style.BRIGHT + f"{i4}Secure Connection pairing: requested!")

    if(((auth_req >> 4) & 1) == 0):
        qprint(f"{i4}Keypress notifications: not requested.")
    else:
        qprint(f"{i4}Keypress notifications: requested.")

    if(((auth_req >> 5) & 1) == 0):
        qprint(f"{i4}CT2 (Cross-Transport key derivation support for the h7 function): not supported.")
    else:
        qprint(f"{i4}CT2 (Cross-Transport key derivation support for the h7 function): supported.")

    qprint(f"{i3}Maxiumum encryption key size: {max_key_size}")
    if(max_key_size < 16):
        qprint(Fore.RED + Style.BRIGHT + f"{i4}WARNING: If accepted, this will lead to weaker encryption keys (<= 128 bits) which are easier to brute-force!")
    if(max_key_size > 16):
        qprint(Fore.YELLOW + Style.BRIGHT + f"{i4}WARNING: Key sizes > 16 are not currently supported (this may be an off-spec implementation, or a corrupt packe.)")
    else:
        qprint(Fore.GREEN + Style.BRIGHT + f"{i4}16 is currently the maximum supported key size.")

    if(oob_data == 0):
        qprint(f"{i3}Out-of-Band (OOB) authentication data: not present.")
    elif(oob_data == 1):
        qprint(f"{i3}Out-of-Band (OOB) authentication data: present.")
    else:
        qprint(Fore.YELLOW + Style.BRIGHT + "\t\t\tWARNING: OOB data has an invalid value (!= 0 or 1) sent. (This may be an off-spec implementation, or a corrupt packet.)")

    qprint(f"{i3}Initiator Key Distribution:")
    key_dist_print("Initiator", initiator_key_dist)

    qprint(f"{i3}Responder Key Distribution:")
    key_dist_print("Responder", responder_key_dist)


def print_SMP_info(bdaddr):
    # Query the database for all SMP data
    values = (bdaddr,)
    query = "SELECT bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist FROM SMP_Pairing_Req_Res WHERE bdaddr = %s";
    SMP_Pairing_Req_Res_result = execute_query(query, values)
    if (len(SMP_Pairing_Req_Res_result) == 0):
        vprint(f"{i1}No SMP data found.")
        return
    else:
        qprint(f"{i1}Security Manager Protocol (SMP) data found:")

    for bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist in SMP_Pairing_Req_Res_result:
        # First export BTIDES
        if(opcode == type_SMP_Pairing_Request):
            data = ff_SMP_Pairing_Request(type_BTIDES_direction_C2P, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
        else:
            data = ff_SMP_Pairing_Response(type_BTIDES_direction_P2C, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
        BTIDES_export_SMP_packet(bdaddr=bdaddr, random=bdaddr_random, data=data)

        # Now print what we want users to see
        if(opcode == type_SMP_Pairing_Request):
            print_pairing_req_res(bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
        elif(opcode == type_SMP_Pairing_Response):
            print_pairing_req_res(bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)

    qprint("")
