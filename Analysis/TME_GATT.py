########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import re
import struct
import TME_glob
from TME_helpers import *

def get_uuid16_gatt_service_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT services
    return TME_glob.gatt_services_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def get_uuid16_gatt_declaration_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT declarations
    return TME_glob.gatt_declarations_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def get_uuid16_gatt_descriptor_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT descriptors
    return TME_glob.gatt_descriptors_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def get_uuid16_gatt_characteristic_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT characteristic
    return TME_glob.gatt_characteristic_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def match_known_GATT_UUID_or_custom_UUID(uuid128):
    uuid128.strip().lower()
    uuid128_no_dash = uuid128.replace('-','')
    pattern = r'0000[a-f0-9]{4}-0000-1000-8000-00805f9b34fb'
    match = re.match(pattern, uuid128)
    if match:
        common_part = match.group()  # Extract the matched part
        uuid16 = common_part[4:8]
        # Try to see if it's a known Service
        str_name = get_uuid16_gatt_service_string(uuid16)
        if(str_name != "Unknown"):
            return f"Service: {str_name}"
        else:
            # Try to see if it's a known Characteristic
            str_name = get_uuid16_gatt_characteristic_string(uuid16)
            if(str_name != "Unknown"):
                return f"Characteristic Value: {str_name}"
            else:
                # Try to see if it's a known Declaration
                str_name = get_uuid16_gatt_declaration_string(uuid16)
                if(str_name != "Unknown"):
                    return f"Declaration: {str_name}"
                else:
                    # Try to see if it's a known Descriptor
                    str_name = get_uuid16_gatt_descriptor_string(uuid16)
                    if(str_name != "Unknown"):
                        return f"Descriptor: {str_name}"
                    else:
                        str = get_custom_uuid128_string(uuid128_no_dash)
                        if(str == "Unknown UUID128"):
                            return "This is a standardized UUID128, but it is not in our database. Check for an update to characteristic_uuids.yaml"
                        else:
                            return str
    else:
        return get_custom_uuid128_string(uuid128_no_dash)
#    elif(uuid128_no_dash in custom_uuid128_hash):
#        return custom_uuid128_hash[uuid128_no_dash]
#    else:
#        return "Non-standard UUID128"

def characteristic_properties_to_string(number):
    str = ""
    if((number & 0b00000001) != 0):
        str += "'Broadcast' "
    if((number & 0b00000010) != 0):
        str += "'Readable' "
    if((number & 0b00000100) != 0):
        str += "'Writable without response' "
    if((number & 0b00001000) != 0):
        str += "'Writable' "
    if((number & 0b00010000) != 0):
        str += "'Notify' "
    if((number & 0b00100000) != 0):
        str += "'Indicate' "
    if((number & 0b01000000) != 0):
        str += "'Authenticated Signed Writes' "
    if((number & 0b10000000) != 0):
        str += "'Extended Properties' "
    return str

def characteristic_extended_properties_to_string(number):
    str = ""
    if((number & 0b00000001) != 0):
        str += "'Reliable Write' "
    if((number & 0b00000010) != 0):
        str += "'Writable Auxiliaries' "
    return str

def is_characteristic_readable(number):
    return (number & 0b00000010) != 0

def lookup_company_name_by_OUI(OUI):
    query = f"SELECT company_name FROM IEEE_bdaddr_to_company WHERE device_bdaddr = '{OUI}'"
    result = execute_query(query)
    if(len(result) >= 1):
        return result[0][0]
    else:
        return ""
    
# Decode some misc things just because they provide interesting info
def characteristic_value_decoding(indent, UUID128, bytes):
    str = match_known_GATT_UUID_or_custom_UUID(UUID128)
    if(str == "Characteristic Value: Appearance"):
        value = int.from_bytes(bytes, byteorder='little')
        #print(f"Value = {value}")
        print(f"{indent}Appearance decodes as: {appearance_uint16_to_string(value)}")

    elif(str == "Characteristic Value: Peripheral Preferred Connection Parameters" and len(bytes) == 8):
        Interval_Min, Interval_Max, Latency, Timeout = struct.unpack('<HHHH', bytes)
        print(f"{indent}PPCP decodes as: Interval_Min:0x{Interval_Min:04x}, Interval_Max:0x{Interval_Max:04x}, Latency:0x{Latency:04x}, Timeout:0x{Timeout:04x}")

    elif(str == "Characteristic Value: Central Address Resolution" and len(bytes) == 1):
        addr_res_support = struct.unpack('<b', bytes)
        addr_res_support = "True" if addr_res_support == (1,) else "False"
        print(f"{indent}Central Address Resolution decodes as: Address Resolution Supported = {addr_res_support}")

    elif(str == "Characteristic Value: System ID" and len(bytes) >= 3):
        big_endian_OUI = f"{bytes[0]:02X}:{bytes[1]:02X}:{bytes[2]:02X}"
        if(big_endian_OUI != "00:00:00"): # Don't want to show likely-false-positives as "Xerox"
            be_company_name = lookup_company_name_by_OUI(big_endian_OUI)
            if(be_company_name != ""):
                print(f"{indent}System ID first 3 bytes big-endian decodes as: OUI = {big_endian_OUI}, Company Name = {be_company_name}")
        little_endian_OUI = f"{bytes[-1]:02X}:{bytes[-2]:02X}:{bytes[-3]:02X}"
        if(little_endian_OUI != "00:00:00"):
            le_company_name = lookup_company_name_by_OUI(little_endian_OUI)
            if(le_company_name != ""):
                print(f"{indent}System ID last 3 bytes little-endian decodes as: OUI = {little_endian_OUI}, Company Name = {le_company_name}")

    elif(str == "Characteristic Value: PnP ID" and len(bytes) == 7):
        company_id_type, company_id, product_id, product_version = struct.unpack('<BHHH', bytes)
        if(company_id_type == 1 or company_id_type == 2): # Don't bother with data which doesn't conform to spec
            if(company_id_type == 1):
                cname = BT_CID_to_company_name(company_id)
            else:
                cname = USB_CID_to_company_name(company_id)
            prod_ver_str = "{}.{}.{}".format(product_version >> 8, (product_version & 0x00F0) >> 4, (product_version & 0x000F))
            print(f"{indent}PnP ID decodes as: Company({company_id_type},0x{company_id:04x}) = {cname}, Product ID = 0x{product_id:04x}, Product Version = {prod_ver_str}")
    #else:
    #    print("") # basically just force a newline so next line isn't double-indented

# Returns 0 if there is no GATT info for this BDADDR in any of the GATT tables, else returns 1
def device_has_GATT_info(bdaddr):
    # Query the database for all GATT services
    query = f"SELECT begin_handle,end_handle,UUID128 FROM GATT_services WHERE device_bdaddr = '{bdaddr}'";
    GATT_services_result = execute_query(query)

    query = f"SELECT attribute_handle,UUID128 FROM GATT_attribute_handles WHERE device_bdaddr = '{bdaddr}'";
    GATT_attribute_handles_result = execute_query(query)

    query = f"SELECT declaration_handle, char_properties, char_value_handle, UUID128 FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_result = execute_query(query)

    query = f"SELECT read_handle,byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_values_result = execute_query(query)

    if(len(GATT_services_result) != 0 or len(GATT_attribute_handles_result) != 0 or len(GATT_characteristics_result) != 0 or len(GATT_characteristics_values_result) !=0):
        return 1;
    else:
        return 0;
    
# Returns whether any matches were found
def print_associated_android_package_names(type, indent, UUID128):
    if(type == "Service"):
        query = f"SELECT android_pkg_name FROM BLEScope_UUID128s WHERE str_UUID128 = '{UUID128}' and uuid_type = 1";
    if(type == "Characteristic"):
        query = f"SELECT android_pkg_name FROM BLEScope_UUID128s WHERE str_UUID128 = '{UUID128}' and uuid_type = 2";

    match_found = False
    android_pkgs_result = execute_query(query)
    if(len(android_pkgs_result) > 0):
        match_found = True
        print(f"{indent}{type} {UUID128}:")
        print(f"{indent}\tThis vendor-specific UUID128 is associated with the following Android packages in the BLEScope data:")
        for (pkg,) in android_pkgs_result:
            print(f"{indent}\t{pkg}")
        print()

    return match_found

def print_GATT_info(bdaddr, hideBLEScopedata):
    # Query the database for all GATT services
    query = f"SELECT begin_handle,end_handle,UUID128 FROM GATT_services WHERE device_bdaddr = '{bdaddr}'";
    GATT_services_result = execute_query(query)

    query = f"SELECT attribute_handle,UUID128 FROM GATT_attribute_handles WHERE device_bdaddr = '{bdaddr}'";
    GATT_attribute_handles_result = execute_query(query)
    attribute_handles_dict = {attribute_handle: UUID128 for attribute_handle,UUID128 in GATT_attribute_handles_result}

    query = f"SELECT declaration_handle, char_properties, char_value_handle, UUID128 FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_result = execute_query(query)
    declaration_handles_dict = {declaration_handle: (char_properties, char_value_handle, UUID128) for declaration_handle, char_properties, char_value_handle, UUID128 in GATT_characteristics_result}

    query = f"SELECT read_handle,byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_values_result = execute_query(query)
    # Need to be smarter about storing values into lookup-by-handle dictionary, because there can be multiple distinct values in the database for a single handle
    char_value_handles_dict = {}
    for read_handle,byte_values in GATT_characteristics_values_result:
        if(read_handle in char_value_handles_dict.keys()):
            # There is already an entry for this handle, so append the new value to the list of possible values
            char_value_handles_dict[read_handle].append(byte_values)
        else:
            # There wasn't already an entry, so insert a list of a single value")
            char_value_handles_dict[read_handle] = [ byte_values ]

    # Changing up the logic to start from the maximum list of all handles in the attributes, characteristics, and read characteristic values tables
    # I will iterate through all of these handles, so nothing gets missed
    query = f"""
    SELECT DISTINCT handle_value
    FROM (
        SELECT attribute_handle AS handle_value
        FROM GATT_attribute_handles
        WHERE device_bdaddr = '{bdaddr}'
        UNION
        SELECT declaration_handle AS handle_value
        FROM GATT_characteristics
        WHERE device_bdaddr = '{bdaddr}'
        UNION
        SELECT char_value_handle AS handle_value
        FROM GATT_characteristics
        WHERE device_bdaddr = '{bdaddr}'
    ) AS combined_handles
    ORDER BY handle_value ASC;
    """
    GATT_all_known_handles_result = execute_query(query)

    # Create a copy of the handle list to keep track of handles we see which never match any Service, to print them out after the fact
    service_match_dict = {}
    for handle, in GATT_all_known_handles_result:
        service_match_dict[handle] = 0

    if(len(GATT_services_result) != 0):
        print("\tGATT Information:")

    unknown_UUID128_hash = {}
    # Print semantically-meaningful information
    for svc_begin_handle,svc_end_handle,UUID128 in GATT_services_result:
        service_match_dict[svc_begin_handle] = 1
        UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID128)
        print(f"\t\tGATT Service: Begin Handle: {svc_begin_handle:03}\tEnd Handle: {svc_end_handle:03}   \tUUID128: {UUID128} ({UUID128_description})")
        # If BLEScope data output is enabled, and we see an Unknown UUID128, save it to analyze later
        if(not hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
            unknown_UUID128_hash[UUID128] = ("Service","\t\t\t")

        # Iterate through all known handles, so nothing gets missed
        for handle, in GATT_all_known_handles_result:
            # Check if this handle is found in the GATT_attribute_handles table, and if so, print that info
            if(handle in attribute_handles_dict.keys()):
                attribute_handle = handle
                UUID128_2 = attribute_handles_dict[handle]
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    service_match_dict[handle] = 1
                    print(f"\t\t\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)}), Attribute Handle: {attribute_handle:03}")

            # Check if this handle is found in the GATT_characteristics table, and if so, print that info
            if(handle in declaration_handles_dict.keys()):
                declaration_handle = handle
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    service_match_dict[handle] = 1
                    (char_properties, char_value_handle, UUID128) = declaration_handles_dict[handle]
                    UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID128)
                    print(f"\t\t\t\tGATT Characteristic declaration:\tCharacteristic Value UUID: {UUID128} ({UUID128_description})\n\t\t\t\t\t\t\t\t\tCharacteristic Value Handle: {char_value_handle:03}\n\t\t\t\t\t\t\t\t\tProperties: 0x{char_properties:02x} ({characteristic_properties_to_string(char_properties)})")
                    if(not hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
                        unknown_UUID128_hash[UUID128] = ("Characteristic","\t\t\t")
                    if(handle not in char_value_handles_dict.keys() and (char_properties & 0x2 == 0x02)):
                        print(f"\t\t\t\tGATT Characteristic Value not successfully read, despite having readable permissions.")

            # Check if this handle is found in the GATT_characteristics_values table, and if so, print that info
            if(handle in char_value_handles_dict.keys()):
                char_value_handle = handle
                for byte_values in char_value_handles_dict[handle]:
                    if(handle <= svc_end_handle and handle >= svc_begin_handle):
                        service_match_dict[handle] = 1
                        print(f"\t\t\t\tGATT Characteristic Value read as {byte_values}")
                        characteristic_value_decoding("\t\t\t\t\t", UUID128, byte_values) #NOTE: This leads to sub-optimal formatting due to the unconditional tabs above. TODO: adjust

    # Second pass:
    # Iterate through all known handles, printing only information about handles which never matched any service
    # First check if the only handles which weren't printed out thus far are service handles (in which case we don't need to do the below)
    service_handle_count = 0
    for handle, in GATT_all_known_handles_result:
        if(service_match_dict[handle] == 1):
            service_handle_count += 1
            continue
    if (len(GATT_all_known_handles_result) != service_handle_count):
        print(f"\t\tGATT Service Unknown! Handle does not match any Service ranges that we received from the device!")
        for handle, in GATT_all_known_handles_result:
            if(service_match_dict[handle] == 1):
                continue
            # Check if this handle is found in the GATT_attribute_handles table, and if so, print that info
            if(handle in attribute_handles_dict.keys()):
                attribute_handle = handle
                UUID128_2 = attribute_handles_dict[handle]
                print(f"\t\t\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)}), Attribute Handle: {attribute_handle:03}")

            # Check if this handle is found in the GATT_characteristics table, and if so, print that info
            if(handle in declaration_handles_dict.keys()):
                declaration_handle = handle
                (char_properties, char_value_handle, UUID128) = declaration_handles_dict[handle]
                UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID128)
                print(f"\t\t\t\tGATT Characteristic declaration:\t{UUID128} ({UUID128_description})\n\t\t\t\t\t\t\t\t\tHandle: {declaration_handle:03}\n\t\t\t\t\t\t\t\t\tProperties: 0x{char_properties:02x} ({characteristic_properties_to_string(char_properties)})")
                if(not hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
                    unknown_UUID128_hash[UUID128] = ("Characteristic","\t\t\t")

            # Check if this handle is found in the GATT_characteristics_values table, and if so, print that info
            if(handle in char_value_handles_dict.keys()):
                char_value_handle = handle
                for byte_values in char_value_handles_dict[handle]:
                    #byte_values = char_value_handles_dict[handle]
                    print(f"\t\t\t\tGATT Characteristic Value read as {byte_values}")
                    characteristic_value_decoding("\t\t\t\t\t", UUID128, byte_values) #NOTE: This leads to sub-optimal formatting due to the unconditional tabs above. TODO: adjust



    # Print raw GATT data minus the values read from characteristics. This can be a superset of the above due to handles potentially not being within the subsetted ranges of enclosing Services or Descriptors
    if(len(GATT_services_result) != 0):
        print(f"\n\t\tGATTPrint:")
        with open(f"./GATTprints/{bdaddr}.gattprint", 'w') as file:
            for svc_begin_handle,svc_end_handle,UUID128 in GATT_services_result:
                print(f"\t\tGATT Service: Begin Handle: {svc_begin_handle:03}\tEnd Handle: {svc_end_handle:03}   \tUUID128: {UUID128} ({match_known_GATT_UUID_or_custom_UUID(UUID128)})")
                file.write(f"Svc: Begin Handle: {svc_begin_handle:03}\tEnd Handle: {svc_end_handle:03}   \tUUID128: {UUID128}\n")
            for attribute_handle, UUID128_2 in GATT_attribute_handles_result:
                print(f"\t\tGATT Descriptor: Attribute Handle: {attribute_handle:03},\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)})")
                file.write(f"Descriptor Handle: {attribute_handle:03}, {UUID128_2}\n")
            for declaration_handle, char_properties, char_value_handle, UUID128 in GATT_characteristics_result:
                print(f"\t\tGATT Characteristic Declaration: {UUID128}, Properties: 0x{char_properties:02x}, Characteristic Handle: {declaration_handle:03}, Characteristic Value Handle: {char_value_handle:03}")
                file.write(f"Char: {UUID128}, Properties: {char_properties}, Declaration Handle: {declaration_handle:03}, Characteristic Handle: {char_value_handle:03}\n")
        print("")

        if(not hideBLEScopedata):
            match_found = False
            print("\t\tBLEScope Analysis: Vendor-specific UUIDs were found. Analyzing if there are any known associations with Android app packages based on BLEScope data.")
            for UUID128 in unknown_UUID128_hash.keys():
                (type, indent) = unknown_UUID128_hash[UUID128]
                match_found = print_associated_android_package_names(type, indent, UUID128)
            if(not match_found):
                print("\t\t\tNo matches found\n")
            else:
                print()

    if(len(GATT_services_result) == 0):
        print("\tNo GATT Information found.")
        print("")
