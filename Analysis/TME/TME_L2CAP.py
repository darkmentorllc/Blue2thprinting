########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#import os
import re
import struct
import TME.TME_glob
from TME.TME_helpers import *
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_L2CAP import *

from colorama import Fore, Back, Style, init
init(autoreset=True)

# Returns 0 if there is no SMP info for this BDADDR in any of the SMP tables, else returns 1
def device_has_L2CAP_info(bdaddr):
    # Query the database for all GATT services
    values = (bdaddr,)
    query = "SELECT bdaddr FROM SMP_Pairing_Req_Res WHERE bdaddr = %s";
    SMP_result = execute_query(query, values)
    if(len(SMP_result) != 0):
        return 1;

    return 0;


def print_L2CAP_info(bdaddr):
    # Query the database for all L2CAP data
    values = (bdaddr,)
    query = "SELECT bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist FROM SMP_Pairing_Req_Res WHERE bdaddr = %s";
    SMP_Pairing_Req_Res_result = execute_query(query, values)
    for bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist in SMP_Pairing_Req_Res_result:
        # First export BTIDES
        # if(opcode == type_opcode_SMP_Pairing_Request):
        #     data = ff_SMP_Pairing_Request(type_BTIDES_direction_C2P, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
        # else:
        #     data = ff_SMP_Pairing_Response(type_BTIDES_direction_P2C, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
        # BTIDES_export_SMP_packet(bdaddr=bdaddr, random=bdaddr_random, data=data)

        # Now print what we want users to see
        if (len(SMP_Pairing_Req_Res_result) == 0):
            vprint("\tNo L2CAP data found.")
            return
        else:
            qprint("\tL2CAP data found:")

    qprint("")
