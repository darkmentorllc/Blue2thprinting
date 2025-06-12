########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_GATT import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# UUID16s
########################################

def colored_print_name_for_UUID16(uuid16):
    service_by_uuid16 = get_uuid16_service_string(uuid16)
    gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
    protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
    standards_org_by_uuid16 = get_standards_org_by_uuid16(uuid16)
    company_by_uuid16 = get_company_by_uuid16(uuid16)
    custom_by_uuid16 = get_custom_by_uuid16(uuid16)
    if(service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Service ID: {service_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(gatt_service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"GATT Service ID: {gatt_service_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(protocol_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Protocol ID: {protocol_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(standards_org_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Standards Development Organization UUID: {standards_org_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    # We do custom before company, because we might have better info in CLUES
    elif(custom_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company-specific Service UUID: {custom_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(company_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company ID: {company_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    else:
        qprint(f"{i2}UUID16 {uuid16} (No matches)")

# Function to print UUID16s for a given bdaddr
def print_uuid16s(bdaddr):
    # Query for EIR_bdaddr_to_UUID16s table
    values = (bdaddr,)
    eir_uuid16s_query = "SELECT list_type, str_UUID16s FROM EIR_bdaddr_to_UUID16s WHERE bdaddr = %s"
    eir_uuid16s_result = execute_query(eir_uuid16s_query, values)

    # Query for LE_bdaddr_to_UUID16s_list table
    le_uuid16s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID16s FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr = %s"
    le_uuid16s_result = execute_query(le_uuid16s_query, values)

    if(len(eir_uuid16s_result) == 0 and len(le_uuid16s_result) == 0):
        vprint(f"{i1}No UUID16s found.")
        return
    else:
        qprint(f"{i1}UUID16s found:")

    # Process EIR_bdaddr_to_UUID16s results
    for list_type, str_UUID16s in eir_uuid16s_result:
        # Export BTIDES data first
        if(str_UUID16s != ""):
            UUID16List = str_UUID16s.split(",")
            for i in range(len(UUID16List)):
                UUID16List[i] = UUID16List[i].replace("0x","") # This won't be needed in the future after I change db import
        else:
            UUID16List = []
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": UUID16List}
        BTIDES_export_AdvData(bdaddr, 0, 50, list_type, data)

        # Then human UI output
        if(str_UUID16s == ""):
            qprint(f"{i2}Empty list present")
        else:
            str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
            for uuid16 in str_UUID16s_list:
                uuid16 = uuid16.strip()
                if(uuid16 == ''):
                    qprint(f"{i2}Empty entry present")
                    continue
                colored_print_name_for_UUID16(uuid16)
        qprint(f"{i3}Found in BT Classic data (DB:EIR_bdaddr_to_UUID16s)")


    # Process LE_bdaddr_to_UUID16s_list results
    for bdaddr_random, le_evt_type, list_type, str_UUID16s in le_uuid16s_result:
        # Export BTIDES data first
        if(str_UUID16s != ""):
            UUID16List = str_UUID16s.split(",")
            for i in range(len(UUID16List)):
                UUID16List[i] = UUID16List[i].replace("0x","") # This won't be needed in the future after I change db import
        else:
            UUID16List = []
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": UUID16List}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        if(str_UUID16s == ""):
            qprint(f"{i2}Empty list present")
        else:
            str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
            for uuid16 in str_UUID16s_list:
                uuid16 = uuid16.strip()
                if(uuid16 == ''):
                    qprint(f"{i2}Empty entry present")
                    continue
                colored_print_name_for_UUID16(uuid16)
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID16s_list), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Function to print UUID16s service solicitation data for a given bdaddr
def print_uuid16s_service_solicit(bdaddr):
    values = (bdaddr,)
    le_uuid16s_query = "SELECT bdaddr_random, le_evt_type, str_UUID16s FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr = %s"
    le_uuid16s_result = execute_query(le_uuid16s_query, values)

    if(len(le_uuid16s_result) == 0):
        vprint(f"{i1}No Service Solicit UUID16s found.")
        return
    else:
        qprint(f"{i1}Service solicit UUID16s found:")

    # Process LE_bdaddr_to_UUID16s_list results
    for bdaddr_random, le_evt_type, str_UUID16s in le_uuid16s_result:
        str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
        for uuid16 in str_UUID16s_list:
            uuid16 = uuid16.strip()
            if(uuid16 == ''):
                qprint(f"{i2}Empty list present")
                continue
            colored_print_name_for_UUID16(uuid16)
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID16_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Function to print UUID16s service data for a given bdaddr
def print_uuid16_service_data(bdaddr):
    values = (bdaddr,)
    le_uuid16_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr = %s"
    le_uuid16_service_data_result = execute_query(le_uuid16_service_data_query, values)

    if(len(le_uuid16_service_data_result) == 0):
        vprint(f"{i1}No UUID16 service data found.")
        return
    else:
        qprint(f"{i1}UUID16 service data found:")

    for bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str in le_uuid16_service_data_result:
        # Export BTIDES data first
        length = 3 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 2 bytes for UUID16 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID16": UUID16_hex_str, "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID16ServiceData, data)

        # Then human UI output
        # Lookup the UUID16 and see if it matches any well-known UUID16s
        colored_print_name_for_UUID16(UUID16_hex_str)
        qprint(f"{i2}Raw service data: {service_data_hex_str}")

        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID16_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")