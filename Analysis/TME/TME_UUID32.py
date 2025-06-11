########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#TODO: create the necessary UUID32 lookups in here: from TME.TME_GATT import *
from TME.TME_helpers import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# UUID32s
########################################

# Function to print UUID32s for a given bdaddr
def print_uuid32s(bdaddr):
    values = (bdaddr,)
    # Query for EIR_bdaddr_to_UUID32s table
    eir_uuid32s_query = "SELECT list_type, str_UUID32s FROM EIR_bdaddr_to_UUID32s WHERE bdaddr = %s"
    eir_uuid32s_result = execute_query(eir_uuid32s_query, values)

    # Query for LE_bdaddr_to_UUID32s_list table
    le_uuid32s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID32s FROM LE_bdaddr_to_UUID32s_list WHERE bdaddr = %s"
    le_uuid32s_result = execute_query(le_uuid32s_query, values)

    if(len(eir_uuid32s_result) == 0 and len(le_uuid32s_result) == 0):
        vprint(f"{i1}No UUID32s found.")
        return
    else:
        qprint(f"{i1}UUID32s found:")

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
        BTIDES_export_AdvData(bdaddr, 0, 50, list_type, data)

        # Then human UI output
        str_UUID32s_list = [token.strip() for token in str_UUID32s.split(',')]
        for uuid32 in str_UUID32s_list:
            uuid32 = uuid32.strip()
            if(uuid32 == ''):
                qprint(f"{i2}Empty list present")
                continue
            qprint(f"{i2}UUID32 {uuid32} (Unknown)")
            # TODO: Create the below UUID32 lookup options
            '''
            service_by_uuid32 = get_uuid32_service_string(uuid32)
            gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
            protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
            company_by_uuid32 = get_company_by_uuid32(uuid32)
            if(service_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Service ID: {service_by_uuid32})")
            elif(gatt_service_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
            elif(protocol_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
            elif(company_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Company ID: {company_by_uuid32})")
            else:
                qprint(f"{i2}UUID32 {uuid32} (No matches)")
            '''
        vprint(f"{i3}Found in BT Classic data (DB:EIR_bdaddr_to_UUID32s)")

    # Process LE_bdaddr_to_UUID32s_list results
    for bdaddr_random, le_evt_type, list_type, str_UUID32s in le_uuid32s_result:
        # Export BTIDES data first
        UUID32List = str_UUID32s.split(",")
        if(len(UUID32List) > 0):
            for i in range(len(UUID32List)):
                UUID32List[i] = UUID32List[i].replace("0x","") # This won't be needed in the future after I change db import
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        data = {"length": length, "UUID32List": UUID32List}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        str_UUID32s_list = [token.strip() for token in str_UUID32s.split(',')]
        for uuid32 in str_UUID32s_list:
            uuid32 = uuid32.strip()
            if(uuid32 == ''):
                qprint(f"{i2}Empty list present")
                continue
            qprint(f"{i2}UUID32 {uuid32} (Unknown)")
            # TODO: Create the below UUID32 lookup options
            '''
            service_by_uuid32 = get_uuid32_service_string(uuid32)
            gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
            protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
            company_by_uuid32 = get_company_by_uuid32(uuid32)
            # TODO: Create a function that looks up a more-specific name for a service given a company ID
            if(service_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Service ID: {service_by_uuid32})")
            elif(gatt_service_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
            elif(protocol_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
            elif(company_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Company ID: {company_by_uuid32})")
            else:
                qprint(f"{i2}UUID32 {uuid32} (No matches)")
            '''

        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID32s_list), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"{i2}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Function to print UUID32s for a given bdaddr
def print_service_solicit_uuid32s(bdaddr):
    values = (bdaddr,)
    le_uuid32s_query = "SELECT bdaddr_random, le_evt_type, str_UUID32s FROM LE_bdaddr_to_UUID32_service_solicit WHERE bdaddr = %s"
    le_uuid32s_result = execute_query(le_uuid32s_query, values)

    if(len(le_uuid32s_result) == 0):
        vprint(f"{i1}No Service Solicit UUID32s found.")
        return
    else:
        qprint(f"{i1}Service solicit UUID32s found:")

    # Process LE_bdaddr_to_UUID32s_list results
    for bdaddr_random, le_evt_type, str_UUID32s in le_uuid32s_result:
        str_UUID32s_list = [token.strip() for token in str_UUID32s.split(',')]
        for uuid32 in str_UUID32s_list:
            uuid32 = uuid32.strip()
            if(uuid32 == ''):
                qprint(f"{i2}Empty list present")
                continue
            qprint(f"{i2}UUID32 {uuid32} (Unknown)")
            # TODO: Create the below UUID32 lookup options
            '''
            service_by_uuid32 = get_uuid32_service_string(uuid32)
            gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
            protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
            company_by_uuid32 = get_company_by_uuid32(uuid32)
            # TODO: Create a function that looks up a more-specific name for a service given a company ID
            if(service_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Service ID: {service_by_uuid32})")
            elif(gatt_service_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
            elif(protocol_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
            elif(company_by_uuid32 != "Unknown"):
                qprint(f"{i2}UUID32 {uuid32} (Company ID: {company_by_uuid32})")
            else:
                qprint(f"{i2}UUID32 {uuid32} (No matches)")
            '''
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID32_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"{i2}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Function to print UUID32s service data for a given bdaddr
def print_uuid32_service_data(bdaddr):
    values = (bdaddr,)
    le_uuid32_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID32_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID32_service_data WHERE bdaddr = %s"
    le_uuid32_service_data_result = execute_query(le_uuid32_service_data_query, values)

    if(len(le_uuid32_service_data_result) == 0):
        vprint(f"{i1}No UUID32 service data found.")
        return
    else:
        qprint(f"{i1}UUID32 service data found:")

    for bdaddr_random, le_evt_type, UUID32_hex_str, service_data_hex_str in le_uuid32_service_data_result:
        # Export BTIDES data first
        length = 5 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 4 bytes for UUID32 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID32": UUID32_hex_str, "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID32ServiceData, data)

        # Then human UI output
        qprint(f"{i2}UUID32 {UUID32_hex_str} (Unknown)")
        # TODO: Create the below UUID32 lookup options
        '''
        service_by_uuid32 = get_uuid32_service_string(uuid32)
        gatt_service_by_uuid32 = get_uuid32_gatt_service_string(uuid32)
        protocol_by_uuid32 = get_uuid32_protocol_string(uuid32)
        company_by_uuid32 = get_company_by_uuid32(uuid32)
        # TODO: Create a function that looks up a more-specific name for a service given a company ID
        if(service_by_uuid32 != "Unknown"):
            qprint(f"{i2}UUID32 {uuid32} (Service ID: {service_by_uuid32})")
        elif(gatt_service_by_uuid32 != "Unknown"):
            qprint(f"{i2}UUID32 {uuid32} (GATT Service ID: {gatt_service_by_uuid32})")
        elif(protocol_by_uuid32 != "Unknown"):
            qprint(f"{i2}UUID32 {uuid32} (Protocol ID: {protocol_by_uuid32})")
        elif(company_by_uuid32 != "Unknown"):
            qprint(f"{i2}UUID32 {uuid32} (Company ID: {company_by_uuid32})")
        else:
            qprint(f"{i2}UUID32 {uuid32} (No matches)")
        '''

        qprint(f"{i2}Raw service data: {service_data_hex_str}")

        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID32_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"{i2}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")