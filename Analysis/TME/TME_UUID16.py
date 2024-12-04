########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

from TME.TME_helpers import *
from TME.TME_GATT import *
from TME.TME_BTIDES_AdvData import *

########################################
# UUID16s
########################################

# Function to print UUID16s for a given device_bdaddr
def print_uuid16s(device_bdaddr):
    # Query for EIR_bdaddr_to_UUID16s table
    eir_uuid16s_query = f"SELECT list_type, str_UUID16s FROM EIR_bdaddr_to_UUID16s WHERE device_bdaddr = '{device_bdaddr}'"
    eir_uuid16s_result = execute_query(eir_uuid16s_query)
    
    # Query for LE_bdaddr_to_UUID16s table
    le_uuid16s_query = f"SELECT bdaddr_random, le_evt_type, list_type, str_UUID16s FROM LE_bdaddr_to_UUID16s WHERE device_bdaddr = '{device_bdaddr}'"
    le_uuid16s_result = execute_query(le_uuid16s_query)

    if(len(eir_uuid16s_result) != 0 or len(le_uuid16s_result) != 0):
        print("\tUUID16s found:")

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
        BTIDES_export_AdvData(device_bdaddr, 0, 50, list_type, data)
        
        # Then human UI output
        if(str_UUID16s == ""):
            print("\t\tEmpty list present")
        else:
            str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]        
            for uuid16 in str_UUID16s_list:
                uuid16 = uuid16.strip()
                if(uuid16 == ''):
                    print("\t\tEmpty entry present")
                    continue
                service_by_uuid16 = get_uuid16_service_string(uuid16)
                gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
                protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
                company_by_uuid16 = get_company_by_uuid16(uuid16)
                if(service_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (Service ID: {service_by_uuid16})")
                elif(gatt_service_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (GATT Service ID: {gatt_service_by_uuid16})")
                elif(protocol_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (Protocol ID: {protocol_by_uuid16})")
                elif(company_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (Company ID: {company_by_uuid16})")
                else:
                    print(f"\t\tUUID16 {uuid16} (No matches)")
        print("\t\t\tFound in BT Classic data (EIR_bdaddr_to_UUID16s)")

    # Process LE_bdaddr_to_UUID16s results
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
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        if(str_UUID16s == ""):
            print("\t\tEmpty list present")
        else:
            str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
            for uuid16 in str_UUID16s_list:
                uuid16 = uuid16.strip()
                if(uuid16 == ''):
                    print("\t\tEmpty entry present")
                    continue
                service_by_uuid16 = get_uuid16_service_string(uuid16)
                gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
                protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
                company_by_uuid16 = get_company_by_uuid16(uuid16)
                # TODO: Create a function that looks up a more-specific name for a service given a company ID
                if(service_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (Service ID: {service_by_uuid16})")
                elif(gatt_service_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (GATT Service ID: {gatt_service_by_uuid16})")
                elif(protocol_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (Protocol ID: {protocol_by_uuid16})")
                elif(company_by_uuid16 != "Unknown"):
                    print(f"\t\tUUID16 {uuid16} (Company ID: {company_by_uuid16})")
                else:
                    print(f"\t\tUUID16 {uuid16} (No matches)")
        print(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID16s), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(eir_uuid16s_result) == 0 and len(le_uuid16s_result) == 0):
        print("\tNo UUID16s found.")

    print("")

# Function to print UUID16s service solicitation data for a given device_bdaddr
def print_uuid16s_service_solicit(device_bdaddr):
    le_uuid16s_query = f"SELECT bdaddr_random, le_evt_type, str_UUID16s FROM LE_bdaddr_to_UUID16_service_solicit WHERE device_bdaddr = '{device_bdaddr}'"
    le_uuid16s_result = execute_query(le_uuid16s_query)

    if(len(le_uuid16s_result) != 0):
        print("\tService solicit UUID16s found:")

    # Process LE_bdaddr_to_UUID16s results
    for bdaddr_random, le_evt_type, str_UUID16s in le_uuid16s_result:
        str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
        for uuid16 in str_UUID16s_list:
            uuid16 = uuid16.strip()
            if(uuid16 == ''):
                print("\t\tEmpty list present")
                continue
            service_by_uuid16 = get_uuid16_service_string(uuid16)
            gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
            protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
            company_by_uuid16 = get_company_by_uuid16(uuid16)
            # TODO: Create a function that looks up a more-specific name for a service given a company ID
            if(service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Service ID: {service_by_uuid16})")
            elif(gatt_service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (GATT Service ID: {gatt_service_by_uuid16})")
            elif(protocol_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Protocol ID: {protocol_by_uuid16})")
            elif(company_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Company ID: {company_by_uuid16})")
            else:
                print(f"\t\tUUID16 {uuid16} (No matches)")
        print(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID16_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(le_uuid16s_result) == 0):
        print("\tNo Service Solicit UUID16s found.")

    print("")

# Function to print UUID16s service data for a given device_bdaddr
def print_uuid16_service_data(device_bdaddr):
    le_uuid16_service_data_query = f"SELECT bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID16_service_data WHERE device_bdaddr = '{device_bdaddr}'"
    le_uuid16_service_data_result = execute_query(le_uuid16_service_data_query)

    if(len(le_uuid16_service_data_result) != 0):
        print("\tUUID16 service data found:")

    for bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str in le_uuid16_service_data_result:
        # Export BTIDES data first
        length = 3 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 2 bytes for UUID16 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID16": UUID16_hex_str, "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID16ServiceData, data)

        # Then human UI output
        # Lookup the UUID16 and see if it matches any well-known UUID16s
        service_by_uuid16 = get_uuid16_service_string(UUID16_hex_str)
        gatt_service_by_uuid16 = get_uuid16_gatt_service_string(UUID16_hex_str)
        protocol_by_uuid16 = get_uuid16_protocol_string(UUID16_hex_str)
        company_by_uuid16 = get_company_by_uuid16(UUID16_hex_str)
        # TODO: Create a function that looks up a more-specific name for a service given a company ID
        if(service_by_uuid16 != "Unknown"):
            print(f"\t\tUUID16 {UUID16_hex_str} (Service ID: {service_by_uuid16})")
        elif(gatt_service_by_uuid16 != "Unknown"):
            print(f"\t\tUUID16 {UUID16_hex_str} (GATT Service ID: {gatt_service_by_uuid16})")
        elif(protocol_by_uuid16 != "Unknown"):
            print(f"\t\tUUID16 {UUID16_hex_str} (Protocol ID: {protocol_by_uuid16})")
        elif(company_by_uuid16 != "Unknown"):
            print(f"\t\tUUID16 {UUID16_hex_str} (Company ID: {company_by_uuid16})")
        else:
            print(f"\t\tUUID16 {UUID16_hex_str} (No matches)")
        print(f"\t\tRaw service data: {service_data_hex_str}")

        print(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID16_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(le_uuid16_service_data_result) == 0):
        print("\tNo UUID16 service data found.")

    print("")