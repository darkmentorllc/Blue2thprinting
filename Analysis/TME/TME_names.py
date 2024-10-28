########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import re
from TME.TME_helpers import *
from TME.TME_BTIDES_HCI import *

########################################
# Device Name
########################################

# Function to print device names from different tables
# NOTE: This is sort of more like "advertised names", except that it also contains SCAN_RSP names too. But we don't want to print out GATT names here, as we'll print them in GATT section
def print_device_names(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    # Query for EIR_bdaddr_to_name table
    eir_query = f"SELECT device_name FROM EIR_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    for name, in eir_result:
        print(f"\tDeviceName: {name}")
        print(f"\t\tIn BT Classic Data (EIR_bdaddr_to_name)")
        find_nameprint_match(name)

    # Query for RSP_bdaddr_to_name table
    rsp_query = f"SELECT device_name FROM RSP_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    rsp_result = execute_query(rsp_query)
    for name, in rsp_result:
        print(f"\tDeviceName: {name}")
        print("\t\tIn BT Classic Data (RSP_bdaddr_to_name)")
        find_nameprint_match(name)
        BTIDES_export_HCI_Name_Response(bdaddr, name)

    # Query for LE_bdaddr_to_name table
    le_query = f"SELECT device_name, bdaddr_random, le_evt_type FROM LE_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query)
    for name, random, le_evt_type in le_result:
        print(f"\tDeviceName: {name}")
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_name), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        find_nameprint_match(name)
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(eir_result) == 0 and len(rsp_result) == 0 and len(le_result)== 0):
        print("\tNo Names found.")

    print("")
