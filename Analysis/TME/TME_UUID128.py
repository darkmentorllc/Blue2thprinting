########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_BTIDES_AdvData import *

########################################
# UUID128s
########################################

def expand_UUID16_or_UUID32_to_UUID128(UUID):
    if(len(UUID) == 4): # UUID16
        return "0000" + UUID16_or_UUID32 + "-0000-1000-8000-00805f9b34fb"
    if(len(UUID) == 8): # UUID32
        return UUID16_or_UUID32 + "-0000-1000-8000-00805f9b34fb"

    return UUID

def add_dashes_to_UUID128(UUID128):
    # Don't add them if it already has them
    if(UUID128[8] == '-'):
        return UUID128
    return f"{UUID128[:8]}-{UUID128[8:12]}-{UUID128[12:16]}-{UUID128[16:20]}-{UUID128[20:32]}"

# assumes UUID1 is the variable and UUID2 is a possible UUID16 or UUID128 without dashes
# This ensures matches even if a UUID16 or UUID32 is expanded out into a UUID128 with the BT Base UUID
def check_if_UUIDs_match(UUID1, UUID2):
    UUID1 = UUID1.lower()
    UUID2 = UUID2.lower()
    if(UUID1 == UUID2):
        return True
    if(len(UUID2) == 4 or len(UUID2) == 8): # UUID16 or UUID32
        UUID1 = expand_UUID16_or_UUID32_to_UUID128(UUID1)
        UUID2 = expand_UUID16_or_UUID32_to_UUID128(UUID2)
    if(UUID1 == UUID2):
        return True
    if(len(UUID2) == 32):
        UUID2 = add_dashes_to_UUID128(UUID2)
    if(UUID1 == UUID2):
        return True

    return False


# Function to print UUID128s for a given device_bdaddr
def print_uuid128s(device_bdaddr):
    eir_UUID128s_query = f"SELECT list_type, str_UUID128s FROM EIR_bdaddr_to_UUID128s WHERE device_bdaddr = '{device_bdaddr}'"
    eir_UUID128s_result = execute_query(eir_UUID128s_query)
    
    le_UUID128s_query = f"SELECT bdaddr_random, le_evt_type, list_type, str_UUID128s FROM LE_bdaddr_to_UUID128s WHERE device_bdaddr = '{device_bdaddr}'"
    le_UUID128s_result = execute_query(le_UUID128s_query)

    if(len(eir_UUID128s_result) == 0 and len(le_UUID128s_result) == 0):
        vprint("\tNo UUID128s found.")
        return
    else:
        print("\tUUID128s found:")

    # Process EIR_bdaddr_to_UUID128s results
    for list_type, str_UUID128s in eir_UUID128s_result:
        # Export BTIDES data first
        if(str_UUID128s != ""):
            UUID128List = str_UUID128s.split(",")
            for i in range(len(UUID128List)):
                UUID128List[i] = add_dashes_to_UUID128(UUID128List[i])
        else:
            UUID128List = []
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        data = {"length": length, "UUID128List": UUID128List}
        BTIDES_export_AdvData(device_bdaddr, 0, 50, list_type, data)

        # Then human UI output
        if(str_UUID128s == ""):
            print("\t\tEmpty list present")
        else:
            str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
            for uuid128 in str_UUID128s_list:
                uuid128 = uuid128.strip().lower()
                dashed_uuid128 = add_dashes_to_UUID128(uuid128)
                print(f"\t\tUUID128 {dashed_uuid128} ({get_custom_uuid128_string(uuid128)})")
        vprint("\t\t\tFound in BT Classic data (EIR_bdaddr_to_UUID128s)")

    # Process LE_bdaddr_to_UUID128s results
    for bdaddr_random, le_evt_type, list_type, str_UUID128s in le_UUID128s_result:
        # Export BTIDES data first
        if(str_UUID128s != ""):
            UUID128List = str_UUID128s.split(",")
            for i in range(len(UUID128List)):
                UUID128List[i] = add_dashes_to_UUID128(UUID128List[i])
        else:
            UUID128List = []
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        data = {"length": length, "UUID128List": UUID128List}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        if(str_UUID128s == ""):
            print("\t\tEmpty list present")
        else:
            str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
            for uuid128 in str_UUID128s_list:
                uuid128 = uuid128.strip().lower()
                dashed_uuid128 = add_dashes_to_UUID128(uuid128)
                print(f"\t\tUUID128 {dashed_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print(f"\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128s), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    print("")

# Function to print UUID128s for a given device_bdaddr
def print_uuid128s_service_solicit(device_bdaddr):
    le_UUID128s_query = f"SELECT bdaddr_random, le_evt_type, str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE device_bdaddr = '{device_bdaddr}'"
    le_UUID128s_result = execute_query(le_UUID128s_query)

    if(len(le_UUID128s_result) == 0):
        vprint("\tNo Service Solicit UUID128s found.")
        return
    else:
        print("\tService Solicit UUID128s found:")

    for bdaddr_random, le_evt_type, str_UUID128s in le_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            if(uuid128 == ''):
                print("\t\tEmpty list present")
                continue
            dashed_uuid128 = add_dashes_to_UUID128(uuid128)
            print(f"\t\tUUID128 {dashed_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print("\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128_service_solicit), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    print("")

# PoC for how this could be done. In practice the interpretation for the data needs to be encoded into a separate file, not hardcoded in the code
def print_service_data_interpretation(UUID128, service_data_hex_str, indent):
    uuid128_no_dashes = UUID128.lower().replace('-','')
    if(uuid128_no_dashes == "9ec5d2b88f514dea9cd3f3dea220b5e0"): # Taser example
        serial = get_utf8_string_from_hex_string(service_data_hex_str)
        print(f"{indent}Possible interpretation: Serial Number: {serial}")

# Function to print UUID128s service data for a given device_bdaddr
def print_uuid128_service_data(device_bdaddr):
    le_uuid128_service_data_query = f"SELECT bdaddr_random, le_evt_type, UUID128_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID128_service_data WHERE device_bdaddr = '{device_bdaddr}'"
    le_uuid128_service_data_result = execute_query(le_uuid128_service_data_query)

    if(len(le_uuid128_service_data_result) == 0):
        vprint("\tNo UUID128 service data found.")
        return
    else:
        print("\tUUID128 service data found:")

    for bdaddr_random, le_evt_type, UUID128_hex_str, service_data_hex_str in le_uuid128_service_data_result:
        # Export BTIDES data first
        dashed_uuid128 = add_dashes_to_UUID128(UUID128_hex_str)
        length = 17 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 16 bytes for UUID128 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID128": add_dashes_to_UUID128(UUID128_hex_str), "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID128ServiceData, data)

        # Then human UI output
        custom_uuid128 = get_custom_uuid128_string(UUID128_hex_str)
        print(f"\t\tUUID128 {dashed_uuid128} ({custom_uuid128})")
        print(f"\t\tRaw service data: {service_data_hex_str}")
        print_service_data_interpretation(UUID128_hex_str, service_data_hex_str, "\t\t")

        print(f"\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    print("")