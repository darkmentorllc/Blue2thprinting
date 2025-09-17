########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# UUID128s
########################################

# Returns whether any matches were found
def print_associated_android_package_names(type, indent, UUID128):
    values = (UUID128,)
    if(type == "Service"):
        query = "SELECT android_pkg_name FROM BLEScope_UUID128s WHERE str_UUID128 = %s and uuid_type = 1";
    elif(type == "Characteristic"):
        query = "SELECT android_pkg_name FROM BLEScope_UUID128s WHERE str_UUID128 = %s and uuid_type = 2";

    match_found = False
    android_pkgs_result = execute_query(query, values)
    if(len(android_pkgs_result) > 0):
        match_found = True
        qprint(f"{indent}{type} {UUID128}:")
        qprint(f"{indent}{i1}This vendor-specific UUID128 is associated with the following Android packages in the BLEScope data:")
        for (pkg,) in android_pkgs_result:
            qprint(f"{indent}{i1}{pkg}")

    return match_found

def expand_UUID16_or_UUID32_to_UUID128(UUID):
    if(len(UUID) == 4): # UUID16
        return "0000" + UUID + "-0000-1000-8000-00805f9b34fb"
    if(len(UUID) == 8): # UUID32
        return UUID + "-0000-1000-8000-00805f9b34fb"

    return UUID

def add_dashes_to_UUID128(UUID128):
    # Don't add them if it not needed
    if(len(UUID128) < 32 or UUID128[8] == '-'):
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


# Function to print UUID128s for a given bdaddr
def print_uuid128s(bdaddr, bdaddr_random):
    unknown_UUID128_hash = {}
    values = (bdaddr,)
    eir_UUID128s_query = "SELECT list_type, str_UUID128s FROM EIR_bdaddr_to_UUID128s WHERE bdaddr = %s"
    eir_UUID128s_result = execute_query(eir_UUID128s_query, values)

    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_UUID128s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID128s FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_UUID128s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID128s FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr = %s"
    le_UUID128s_result = execute_query(le_UUID128s_query, values)

    if(len(eir_UUID128s_result) == 0 and len(le_UUID128s_result) == 0):
        vprint(f"{i1}No UUID128s found.")
        return
    else:
        qprint(f"{i1}UUID128s found:")

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
        BTIDES_export_AdvData(bdaddr, 0, 50, list_type, data)

        # Then human UI output
        if(str_UUID128s == ""):
            qprint(f"{i2}Empty list present")
        else:
            str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
            for uuid128 in str_UUID128s_list:
                uuid128 = uuid128.strip().lower()
                dashed_uuid128 = add_dashes_to_UUID128(uuid128)
                uuid_str = f"{get_custom_uuid128_string(uuid128)}"
                if(uuid_str.__contains__("Unknown UUID128")):
                    test_uuid16 = convert_UUID128_to_UUID16_if_possible(uuid128)
                    if(len(test_uuid16) == 4):
                        test_uuid16_name = return_name_for_UUID16(test_uuid16)
                        qprint(f"{i2}UUID128 {dashed_uuid128} ({test_uuid16_name})")
                    else:
                        qprint(f"{i2}UUID128 {dashed_uuid128} ({uuid_str})")
                        if(not TME.TME_glob.hide_android_data and uuid_str.__contains__("Unknown UUID128")):
                            unknown_UUID128_hash[uuid128] = ("Service", f"{i3}")
                else:
                    qprint(f"{i2}UUID128 {dashed_uuid128} ({uuid_str})")
        vprint(f"{i3}In BT Classic data (DB:EIR_bdaddr_to_UUID128s)")

    # Process LE_bdaddr_to_UUID128s_list results
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
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        if(str_UUID128s == ""):
            qprint(f"{i2}Empty list present")
        else:
            str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
            for uuid128 in str_UUID128s_list:
                uuid128 = uuid128.strip().lower()
                dashed_uuid128 = add_dashes_to_UUID128(uuid128)
                uuid_str = f"{get_custom_uuid128_string(uuid128)}"
                if(uuid_str.__contains__("Unknown UUID128")):
                    test_uuid16 = convert_UUID128_to_UUID16_if_possible(uuid128)
                    if(len(test_uuid16) == 4):
                        test_uuid16_name = return_name_for_UUID16(test_uuid16)
                        qprint(f"{i2}UUID128 {dashed_uuid128} ({test_uuid16_name})")
                    else:
                        qprint(f"{i2}UUID128 {dashed_uuid128} ({uuid_str})")
                        if(not TME.TME_glob.hide_android_data):
                            unknown_UUID128_hash[uuid128] = ("Service", f"{i3}")
                else:
                    qprint(f"{i2}UUID128 {dashed_uuid128} ({uuid_str})")
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID128s_list), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        vprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")


    if(not TME.TME_glob.hide_android_data and len(unknown_UUID128_hash) > 0):
        match_found = False
        qprint(f"{i2}BLEScope Analysis: Vendor-specific UUIDs were found. Analyzing if there are any known associations with Android app packages based on BLEScope data.")
        for UUID in unknown_UUID128_hash.keys():
            if(UUID.replace('-','') == "00000000000000000000000000000000"):
                    continue
            (type, indent) = unknown_UUID128_hash[UUID]
            match_found = print_associated_android_package_names(type, indent, UUID)
        if(not match_found):
            qprint(f"{i3}No matches found")

    qprint("")

# Function to print UUID128s for a given bdaddr
def print_uuid128s_service_solicit(bdaddr, bdaddr_random):
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_UUID128s_query = "SELECT bdaddr_random, le_evt_type, str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_UUID128s_query = "SELECT bdaddr_random, le_evt_type, str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr = %s"
    le_UUID128s_result = execute_query(le_UUID128s_query, values)

    if(len(le_UUID128s_result) == 0):
        vprint(f"{i1}No Service Solicit UUID128s found.")
        return
    else:
        qprint(f"{i1}Service Solicit UUID128s found:")

    for bdaddr_random, le_evt_type, str_UUID128s in le_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        # Export BTIDES data first
        # Include the dashes in the UUID128s for extra readability
        BTIDES_UUID128_list = []
        for entry in str_UUID128s_list:
            BTIDES_UUID128_list.append(add_dashes_to_UUID128(entry))
        length = 1 + 16 * len(BTIDES_UUID128_list) # 1 byte for opcode, 16 bytes for each UUID128
        data = {"length": length, "UUID128List": BTIDES_UUID128_list}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID128ListServiceSolicitation, data)

        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            if(uuid128 == ''):
                qprint(f"{i2}Empty list present")
                continue
            dashed_uuid128 = add_dashes_to_UUID128(uuid128)
            qprint(f"{i2}UUID128 {dashed_uuid128} ({get_custom_uuid128_string(uuid128)})")
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID128_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        vprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# PoC for how this could be done. In practice the interpretation for the data needs to be encoded into a separate file, not hardcoded in the code
def print_service_data_interpretation(UUID128, service_data_hex_str, indent):
    uuid128_no_dashes = UUID128.lower().replace('-','')
    if(uuid128_no_dashes == "9ec5d2b88f514dea9cd3f3dea220b5e0"): # Taser example
        serial = get_utf8_string_from_hex_string(service_data_hex_str)
        qprint(f"{indent}Possible interpretation: Serial Number: {serial}")
        if(serial[:3] == "X85"):
            qprint(f"{indent}{i1}This is a front or rear Axon Fleet Power Unit connected to a camera.")
        elif(serial[:3] == "X87"):
            qprint(f"{indent}{i1}This is a Axon Signal Vehicle unit for the vehicle.")

# Function to print UUID128s service data for a given bdaddr
def print_uuid128_service_data(bdaddr, bdaddr_random):
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_uuid128_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID128_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_uuid128_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID128_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr = %s"
    le_uuid128_service_data_result = execute_query(le_uuid128_service_data_query, values)

    if(len(le_uuid128_service_data_result) == 0):
        vprint(f"{i1}No UUID128 service data found.")
        return
    else:
        qprint(f"{i1}UUID128 service data found:")

    for bdaddr_random, le_evt_type, UUID128_hex_str, service_data_hex_str in le_uuid128_service_data_result:
        # Export BTIDES data first
        dashed_uuid128 = add_dashes_to_UUID128(UUID128_hex_str)
        length = 17 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 16 bytes for UUID128 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID128": add_dashes_to_UUID128(UUID128_hex_str), "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID128ServiceData, data)

        # Then human UI output
        custom_uuid128 = get_custom_uuid128_string(UUID128_hex_str)
        qprint(f"{i2}UUID128 {dashed_uuid128} ({custom_uuid128})")
        qprint(f"{i2}Raw service data: {service_data_hex_str}")
        print_service_data_interpretation(UUID128_hex_str, service_data_hex_str, f"{i3}")

        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID128_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        vprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")