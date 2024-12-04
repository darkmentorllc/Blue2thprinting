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

# Function to print UUID16s for a given device_bdaddr
def print_service_solicit_uuid16s(device_bdaddr):
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