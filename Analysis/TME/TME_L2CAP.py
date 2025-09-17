########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#import os
# import re
# import struct
# import TME.TME_glob
from TME.TME_helpers import *
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_L2CAP import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

from colorama import Fore, Back, Style, init
init(autoreset=True)

# Returns 0 if there is no SMP info for this BDADDR in any of the SMP tables, else returns 1
def device_has_L2CAP_info(bdaddr, bdaddr_random):
    # Query the database for all GATT services
    if(bdaddr_random is not None):
        values = (bdaddr, bdaddr_random)
        query = "SELECT bdaddr FROM SMP_Pairing_Req_Res WHERE bdaddr = %s AND bdaddr_random = %s";
    else:
        values = (bdaddr,)
        query = "SELECT bdaddr FROM SMP_Pairing_Req_Res WHERE bdaddr = %s";
    SMP_result = execute_query(query, values)
    if(len(SMP_result) != 0):
        return 1;

    return 0;

def print_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(indent, direction, pkt_id, data_len, interval_min, interval_max, latency, timeout):
    qprint(f"{indent}L2CAP_CONNECTION_PARAMETER_UPDATE_REQ:")
    if(direction == type_BTIDES_direction_C2P):
        qprint(f"{indent}{i1}Direction: Central to Peripheral")
    else:
        qprint(f"{indent}{i1}Direction: Peripheral to Central")
    qprint(f"{indent}{i1}Packet command/response association ID: {pkt_id}")
    qprint(f"{indent}{i1}Data Length: {data_len}")
    qprint(f"{indent}{i1}Requested minimum connection interval (in units of 1.25ms): {interval_min}")
    qprint(f"{indent}{i1}Requested maximum connection interval (in units of 1.25ms): {interval_max}")
    qprint(f"{indent}{i1}Requested Peripheral Latency (number of connection events Peripheral can skip responding): {latency}")
    qprint(f"{indent}{i1}Requested timeout (in units of 10ms): {timeout}")


def print_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(indent, direction, pkt_id, data_len, result):
    print(f"{indent}L2CAP_CONNECTION_PARAMETER_UPDATE_RSP:")
    if(direction == type_BTIDES_direction_C2P):
        qprint(f"{indent}{i1}Direction: Central to Peripheral")
    else:
        qprint(f"{indent}{i1}Direction: Peripheral to Central")
    qprint(f"{indent}{i1}Packet command/response association ID: {pkt_id}")
    qprint(f"{indent}{i1}Data Length: {data_len}")
    qprint(f"{indent}{i1}Result: {result} ({type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result_strings[result]})")


def print_L2CAP_info(bdaddr, bdaddr_random):
    # Query the database for all L2CAP data
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        query = "SELECT bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout FROM L2CAP_CONNECTION_PARAMETER_UPDATE_REQ WHERE bdaddr_random = %s AND bdaddr = %s";
    else:
        values = (bdaddr,)
        query = "SELECT bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout FROM L2CAP_CONNECTION_PARAMETER_UPDATE_REQ WHERE bdaddr = %s";
    l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ_result = execute_query(query, values)

    if(bdaddr_random is not None):
        query = "SELECT bdaddr_random, direction, code, pkt_id, data_len, result FROM L2CAP_CONNECTION_PARAMETER_UPDATE_RSP WHERE bdaddr_random = %s AND bdaddr = %s";
    else:
        query = "SELECT bdaddr_random, direction, code, pkt_id, data_len, result FROM L2CAP_CONNECTION_PARAMETER_UPDATE_RSP WHERE bdaddr = %s";
    l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result = execute_query(query, values)

    if (l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ_result or l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result):
        qprint(f"{i1}L2CAP data found:")
    else:
        vprint(f"{i1}No L2CAP data found.")
        return

    if(l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ_result):
        for bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout in l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ_result:
            # First export BTIDES
            if(code == type_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ):
                data = ff_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(direction, pkt_id, data_len, interval_min, interval_max, latency, timeout)
                BTIDES_export_L2CAP_packet(bdaddr=bdaddr, random=bdaddr_random, data=data)
                # Then print UI
                print_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(f"{i2}", direction, pkt_id, data_len, interval_min, interval_max, latency, timeout)

    if(l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result):
        for bdaddr_random, direction, code, pkt_id, data_len, result in l2cap_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result:
            # First export BTIDES
            if(code == type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP):
                data = ff_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(direction, pkt_id, data_len, result)
                BTIDES_export_L2CAP_packet(bdaddr=bdaddr, random=bdaddr_random, data=data)
                # Then print UI
                print_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(f"{i2}", direction, pkt_id, data_len, result)

    qprint("")
