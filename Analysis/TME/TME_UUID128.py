########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

#import TME.TME_glob
from TME.TME_helpers import *

########################################
# UUID128s
########################################

# Function to print UUID128s for a given device_bdaddr
def print_uuid128s(device_bdaddr):
    eir_UUID128s_query = f"SELECT list_type, str_UUID128s FROM EIR_bdaddr_to_UUID128s WHERE device_bdaddr = '{device_bdaddr}'"
    eir_UUID128s_result = execute_query(eir_UUID128s_query)
    
    le_UUID128s_query = f"SELECT bdaddr_random, le_evt_type, list_type, str_UUID128s FROM LE_bdaddr_to_UUID128s WHERE device_bdaddr = '{device_bdaddr}'"
    le_UUID128s_result = execute_query(le_UUID128s_query)

    if(len(eir_UUID128s_result) != 0 or len(le_UUID128s_result) != 0):
        print("\tUUID128s found:")

    # Process EIR_bdaddr_to_UUID128s results
    for list_type, str_UUID128s in eir_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            dashing_uuid128 = f"{uuid128[:8]}-{uuid128[8:12]}-{uuid128[12:16]}-{uuid128[16:20]}-{uuid128[20:32]}"
            print(f"\t\tUUID128 {dashing_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print("\t\t\tFound in BT Classic data (EIR_bdaddr_to_UUID128s)")

    # Process LE_bdaddr_to_UUID128s results
    for bdaddr_random, le_evt_type, list_type, str_UUID128s in le_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            dashing_uuid128 = f"{uuid128[:8]}-{uuid128[8:12]}-{uuid128[12:16]}-{uuid128[16:20]}-{uuid128[20:32]}"
            print(f"\t\tUUID128 {dashing_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print(f"\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128s), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(eir_UUID128s_result) == 0 and len(le_UUID128s_result) == 0):
        print("\tNo UUID128s found.")

    print("")

# Function to print UUID128s for a given device_bdaddr
def print_service_solicit_uuid128s(device_bdaddr):
    le_UUID128s_query = f"SELECT bdaddr_random, le_evt_type, str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE device_bdaddr = '{device_bdaddr}'"
    le_UUID128s_result = execute_query(le_UUID128s_query)

    if(len(le_UUID128s_result) != 0):
        print("\tService Solicit UUID128s found:")

    for bdaddr_random, le_evt_type, str_UUID128s in le_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            if(uuid128 == ''):
                print("\t\tEmpty list present")
                continue
            dashing_uuid128 = f"{uuid128[:8]}-{uuid128[8:12]}-{uuid128[12:16]}-{uuid128[16:20]}-{uuid128[20:32]}"
            print(f"\t\tUUID128 {dashing_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print("\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128_service_solicit), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(le_UUID128s_result) == 0):
        print("\tNo Service Solicit UUID128s found.")

    print("")