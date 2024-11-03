########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import re
from TME.TME_helpers import *
from TME.TME_BTIDES_HCI import *
from TME.TME_BTIDES_AdvData import *

########################################
# Device Name
########################################

# Function to print device names from different tables
# NOTE: This is sort of more like "advertised names", except that it also contains SCAN_RSP names too. But we don't want to print out GATT names here, as we'll print them in GATT section
def print_device_names(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    # Query for EIR_bdaddr_to_name table
    eir_query = f"SELECT device_name_type, device_name FROM EIR_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    for device_name_type, device_name in eir_result:
        print(f"\tDeviceName: {device_name}")
        print(f"\t\tIn BT Classic Data (EIR_bdaddr_to_name)")
        find_nameprint_match(device_name)
        
        length = int(1 + len(device_name)) # 1 bytes for opcode + length of the string
        byte_data = device_name.encode('utf-8')
        name_hex_str = ''.join(format(byte, '02x') for byte in byte_data)
        data = {"length": length, "utf8_name": device_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(bdaddr, 0, 50, device_name_type, data)

    # Query for RSP_bdaddr_to_name table
    rsp_query = f"SELECT device_name FROM RSP_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    rsp_result = execute_query(rsp_query)
    for device_name, in rsp_result:
        print(f"\tDeviceName: {device_name}")
        print("\t\tIn BT Classic Data (RSP_bdaddr_to_name)")
        find_nameprint_match(device_name)
        BTIDES_export_HCI_Name_Response(bdaddr, device_name)

    # Query for LE_bdaddr_to_name2 table
    le_query = f"SELECT bdaddr_random, le_evt_type, device_name_type, device_name FROM LE_bdaddr_to_name2 WHERE device_bdaddr = '{bdaddr}'" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query)
    for bdaddr_random, le_evt_type, device_name_type, device_name in le_result:
        print(f"\tDeviceName: {device_name}")
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_name2), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        find_nameprint_match(device_name)
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")
        
        length = int(1 + len(device_name)) # 1 bytes for opcode + length of the string
        byte_data = device_name.encode('utf-8')
        name_hex_str = ''.join(format(byte, '02x') for byte in byte_data)
        data = {"length": length, "utf8_name": device_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, device_name_type, data)

    if(len(eir_result) == 0 and len(rsp_result) == 0 and len(le_result)== 0):
        print("\tNo Names found.")

    print("")
