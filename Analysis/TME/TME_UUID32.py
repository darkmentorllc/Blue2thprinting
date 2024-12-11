########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
#TODO: create the necessary UUID32 lookups in here: from TME.TME_GATT import *
from TME.TME_BTIDES_AdvData import *

########################################
# UUID32s
########################################

# Function to print UUID32s for a given device_bdaddr
def print_uuid32s(device_bdaddr):
    values = (device_bdaddr,)
    # Query for EIR_bdaddr_to_UUID32s table
    eir_uuid32s_query = "SELECT list_type, str_UUID32s FROM EIR_bdaddr_to_UUID32s WHERE device_bdaddr = %s"
    eir_uuid32s_result = execute_query(eir_uuid32s_query, values)
    
    # Query for LE_bdaddr_to_UUID32s table
    le_uuid32s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID32s FROM LE_bdaddr_to_UUID32s WHERE device_bdaddr = %s"
    le_uuid32s_result = execute_query(le_uuid32s_query, values)

    if(len(eir_uuid32s_result) == 0 and len(le_uuid32s_result) == 0):
        vprint("\tNo UUID32s found.")
        return
    else:
        print("\tUUID32s found:")

    # Process EIR_bdaddr_to_UUID32s results
    for list_type, str_UUID32s in eir_uuid32s_result:
        # Export BTIDES data first
        if(str_UUID32s != ""):
            UUID32List = str_UUID32s.split(",")
            for i in range(len(UUID32List)):
                UUID32List[i] = UUID32List[i].replace("0x","") # This won't be needed in the future after I change db import
        else:
            UUID32List = []

        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        data = {"length": length, "UUID32List": UUID32List}
        BTIDES_export_AdvData(device_bdaddr, 0, 50, list_type, data)
        
        # Then human UI output
        str_UUID32s_list = [token.strip() for token in str_UUID32s.split(',')]        
        for uuid32 in str_UUID32s_list:
            uuid32 = uuid32.strip()
            if(uuid32 == ''):
                print("\t\tEmpty list present")
                continue
            print(f"\t\tUUID32 {uuid32} (Unknown)")
            # TODO: Create the below UUID32 lookup options
            '''
            service_by_uuid32 = get_uuid32_service_string(uuid32)
            gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
            protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
            company_by_uuid32 = get_company_by_uuid32(uuid32)
            if(service_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Service ID: {service_by_uuid32})")
            elif(gatt_service_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
            elif(protocol_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
            elif(company_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Company ID: {company_by_uuid32})")
            else:
                print(f"\t\tUUID32 {uuid32} (No matches)")
            '''
        vprint("\t\t\tFound in BT Classic data (EIR_bdaddr_to_UUID32s)")

    # Process LE_bdaddr_to_UUID32s results
    for bdaddr_random, le_evt_type, list_type, str_UUID32s in le_uuid32s_result:
        # Export BTIDES data first
        UUID32List = str_UUID32s.split(",")
        if(len(UUID32List) > 0):
            for i in range(len(UUID32List)):
                UUID32List[i] = UUID32List[i].replace("0x","") # This won't be needed in the future after I change db import
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        data = {"length": length, "UUID32List": UUID32List}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        str_UUID32s_list = [token.strip() for token in str_UUID32s.split(',')]
        for uuid32 in str_UUID32s_list:
            uuid32 = uuid32.strip()
            if(uuid32 == ''):
                print("\t\tEmpty list present")
                continue
            print(f"\t\tUUID32 {uuid32} (Unknown)")
            # TODO: Create the below UUID32 lookup options
            '''
            service_by_uuid32 = get_uuid32_service_string(uuid32)
            gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
            protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
            company_by_uuid32 = get_company_by_uuid32(uuid32)
            # TODO: Create a function that looks up a more-specific name for a service given a company ID
            if(service_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Service ID: {service_by_uuid32})")
            elif(gatt_service_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
            elif(protocol_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
            elif(company_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Company ID: {company_by_uuid32})")
            else:
                print(f"\t\tUUID32 {uuid32} (No matches)")
            '''

        vprint(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID32s), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    print("")

# Function to print UUID32s for a given device_bdaddr
def print_service_solicit_uuid32s(device_bdaddr):
    values = (device_bdaddr,)
    le_uuid32s_query = "SELECT bdaddr_random, le_evt_type, str_UUID32s FROM LE_bdaddr_to_UUID32_service_solicit WHERE device_bdaddr = %s"
    le_uuid32s_result = execute_query(le_uuid32s_query, values)

    if(len(le_uuid32s_result) == 0):
        vprint("\tNo Service Solicit UUID32s found.")
        return
    else:
        print("\tService solicit UUID32s found:")

    # Process LE_bdaddr_to_UUID32s results
    for bdaddr_random, le_evt_type, str_UUID32s in le_uuid32s_result:
        str_UUID32s_list = [token.strip() for token in str_UUID32s.split(',')]
        for uuid32 in str_UUID32s_list:
            uuid32 = uuid32.strip()
            if(uuid32 == ''):
                print("\t\tEmpty list present")
                continue
            print(f"\t\tUUID32 {uuid32} (Unknown)")
            # TODO: Create the below UUID32 lookup options
            '''
            service_by_uuid32 = get_uuid32_service_string(uuid32)
            gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
            protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
            company_by_uuid32 = get_company_by_uuid32(uuid32)
            # TODO: Create a function that looks up a more-specific name for a service given a company ID
            if(service_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Service ID: {service_by_uuid32})")
            elif(gatt_service_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
            elif(protocol_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
            elif(company_by_uuid32 != "Unknown"):
                print(f"\t\tUUID32 {uuid32} (Company ID: {company_by_uuid32})")
            else:
                print(f"\t\tUUID32 {uuid32} (No matches)")
            '''
        vprint(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID32_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    print("")

# Function to print UUID32s service data for a given device_bdaddr
def print_uuid32_service_data(device_bdaddr):
    values = (device_bdaddr,)
    le_uuid32_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID32_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID32_service_data WHERE device_bdaddr = %s"
    le_uuid32_service_data_result = execute_query(le_uuid32_service_data_query, values)

    if(len(le_uuid32_service_data_result) == 0):
        vprint("\tNo UUID32 service data found.")
        return
    else:
        print("\tUUID32 service data found:")

    for bdaddr_random, le_evt_type, UUID32_hex_str, service_data_hex_str in le_uuid32_service_data_result:
        # Export BTIDES data first
        length = 5 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 4 bytes for UUID32 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID32": UUID32_hex_str, "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID32ServiceData, data)

        # Then human UI output
        print(f"\t\tUUID32 {UUID32_hex_str} (Unknown)")
        # TODO: Create the below UUID32 lookup options
        '''
        service_by_uuid32 = get_uuid32_service_string(uuid32)
        gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
        protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
        company_by_uuid32 = get_company_by_uuid32(uuid32)
        # TODO: Create a function that looks up a more-specific name for a service given a company ID
        if(service_by_uuid32 != "Unknown"):
            print(f"\t\tUUID32 {uuid32} (Service ID: {service_by_uuid32})")
        elif(gatt_service_by_uuid32 != "Unknown"):
            print(f"\t\tUUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
        elif(protocol_by_uuid32 != "Unknown"):
            print(f"\t\tUUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
        elif(company_by_uuid32 != "Unknown"):
            print(f"\t\tUUID32 {uuid32} (Company ID: {company_by_uuid32})")
        else:
            print(f"\t\tUUID32 {uuid32} (No matches)")
        '''

        print(f"\t\tRaw service data: {service_data_hex_str}")

        vprint(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID32_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    print("")