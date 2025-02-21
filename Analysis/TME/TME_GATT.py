########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#import os
import re
import struct
import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_BTIDES_ATT import *
from TME.TME_BTIDES_GATT import *
from TME.TME_UUID128 import add_dashes_to_UUID128, print_associated_android_package_names

from colorama import Fore, Back, Style, init
init(autoreset=True)

# UUID can now be a UUID16 or UUID32 or UUID128
def match_known_GATT_UUID_or_custom_UUID(UUID):
    UUID = convert_UUID128_to_UUID16_if_possible(UUID)
    # Try to see if it's a known GATT Service
    str_name = get_uuid16_gatt_service_string(UUID)
    if(str_name != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Service: {str_name}" + Style.RESET_ALL
        return colored_str
    else:
        # Try to see if it's a known Characteristic
        str_name = get_uuid16_gatt_characteristic_string(UUID)
        if(str_name != "Unknown"):
            colored_str = Fore.CYAN + Style.BRIGHT + f"Characteristic Value: {str_name}" + Style.RESET_ALL
            return colored_str
            # return f"Characteristic Value: {str_name}"
        else:
            # Try to see if it's a known Declaration
            str_name = get_uuid16_gatt_declaration_string(UUID)
            if(str_name != "Unknown"):
                # colored_str = Fore.CYAN + Style.BRIGHT + f"Declaration: {str_name}"
                # return colored_str
                return f"Declaration: {str_name}"
            else:
                # Try to see if it's a known Descriptor
                str_name = get_uuid16_gatt_descriptor_string(UUID)
                if(str_name != "Unknown"):
                    colored_str = Fore.CYAN + Style.BRIGHT + f"Descriptor: {str_name}" + Style.RESET_ALL
                    return colored_str
                    # return f"Descriptor: {str_name}"
                else:
                    if(len(UUID) == 4):
                        str = return_name_for_UUID16(UUID)
                    else:
                        str = get_custom_uuid128_string(UUID)
                    if(str == "Unknown UUID128"):
                        colored_str = Fore.RED + Style.BRIGHT + "This is a standardized UUID128, but it is not in our database. Check for an update to characteristic_uuids.yaml" + Style.RESET_ALL
                        return colored_str
                    else:
                        colored_str = Fore.CYAN + Style.BRIGHT + str + Style.RESET_ALL
                        return colored_str

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
    values = (OUI,)
    query = "SELECT company_name FROM IEEE_bdaddr_to_company WHERE bdaddr = %s";
    result = execute_query(query, values)
    if(len(result) >= 1):
        return result[0][0]
    else:
        return ""

# Decode some misc things just because they provide interesting info
def characteristic_value_decoding(indent, UUID128, bytes):
    str = match_known_GATT_UUID_or_custom_UUID(UUID128)
    if(str == "Characteristic Value: Appearance"):
        value = int.from_bytes(bytes, byteorder='little')
        #qprint(f"Value = {value}")
        qprint(f"{indent}Appearance decodes as: {appearance_uint16_to_string(value)}")

    elif(str == "Characteristic Value: Peripheral Preferred Connection Parameters" and len(bytes) == 8):
        Interval_Min, Interval_Max, Latency, Timeout = struct.unpack('<HHHH', bytes)
        qprint(f"{indent}PPCP decodes as: Interval_Min:0x{Interval_Min:04x}, Interval_Max:0x{Interval_Max:04x}, Latency:0x{Latency:04x}, Timeout:0x{Timeout:04x}")

    elif(str == "Characteristic Value: Central Address Resolution" and len(bytes) == 1):
        addr_res_support = struct.unpack('<b', bytes)
        addr_res_support = "True" if addr_res_support == (1,) else "False"
        qprint(f"{indent}Central Address Resolution decodes as: Address Resolution Supported = {addr_res_support}")

    elif(str == "Characteristic Value: System ID" and len(bytes) >= 3):
        big_endian_OUI = f"{bytes[0]:02X}:{bytes[1]:02X}:{bytes[2]:02X}"
        if(big_endian_OUI != "00:00:00"): # Don't want to show likely-false-positives as "Xerox"
            be_company_name = lookup_company_name_by_OUI(big_endian_OUI)
            if(be_company_name != ""):
                qprint(f"{indent}System ID first 3 bytes big-endian decodes as: OUI = {big_endian_OUI}, Company Name = {be_company_name}")
        little_endian_OUI = f"{bytes[-1]:02X}:{bytes[-2]:02X}:{bytes[-3]:02X}"
        if(little_endian_OUI != "00:00:00"):
            le_company_name = lookup_company_name_by_OUI(little_endian_OUI)
            if(le_company_name != ""):
                qprint(f"{indent}System ID last 3 bytes little-endian decodes as: OUI = {little_endian_OUI}, Company Name = {le_company_name}")

    elif(str == "Characteristic Value: PnP ID" and len(bytes) == 7):
        company_id_type, company_id, product_id, product_version = struct.unpack('<BHHH', bytes)
        if(company_id_type == 1 or company_id_type == 2): # Don't bother with data which doesn't conform to spec
            if(company_id_type == 1):
                cname = BT_CID_to_company_name(company_id)
            else:
                cname = USB_CID_to_company_name(company_id)
            prod_ver_str = "{}.{}.{}".format(product_version >> 8, (product_version & 0x00F0) >> 4, (product_version & 0x000F))
            qprint(f"{indent}PnP ID decodes as: Company({company_id_type},0x{company_id:04x}) = {cname}, Product ID = 0x{product_id:04x}, Product Version = {prod_ver_str}")
    #else:
    #    qprint("") # basically just force a newline so next line isn't double-indented

# Returns 0 if there is no GATT info for this BDADDR in any of the GATT tables, else returns 1
def device_has_GATT_any(bdaddr):
    # Query the database for all GATT services
    values = (bdaddr,)
    query = "SELECT begin_handle, end_handle, UUID FROM GATT_services WHERE bdaddr = %s";
    GATT_services_result = execute_query(query, values)
    if(len(GATT_services_result) != 0):
        return 1

    query = "SELECT attribute_handle, UUID FROM GATT_attribute_handles WHERE bdaddr = %s";
    GATT_attribute_handles_result = execute_query(query, values)
    if(len(GATT_attribute_handles_result) != 0):
        return 1

    query = "SELECT declaration_handle, char_properties, char_value_handle, UUID FROM GATT_characteristics WHERE bdaddr = %s";
    GATT_characteristics_result = execute_query(query, values)
    if(len(GATT_characteristics_result) != 0):
        return 1

    query = "SELECT char_value_handle, byte_values FROM GATT_characteristics_values WHERE bdaddr = %s";
    GATT_characteristics_values_result = execute_query(query, values)
    if(len(GATT_characteristics_values_result) != 0):
        return 1

    return 0

# Returns 0 if there is no GATT info for this BDADDR in any of the GATT tables, else returns 1
def device_has_GATT_values(bdaddr):
    # Query the database for all GATT services
    values = (bdaddr,)
    query = "SELECT char_value_handle, byte_values FROM GATT_characteristics_values WHERE bdaddr = %s";
    GATT_characteristics_values_result = execute_query(query, values)
    if(len(GATT_characteristics_values_result) != 0):
        return 1

    return 0

def print_GATT_info(bdaddr):
    # Query the database for all GATT services
    values = (bdaddr,)
    query = "SELECT bdaddr_random, service_type, begin_handle, end_handle, UUID FROM GATT_services WHERE bdaddr = %s";
    GATT_services_result = execute_query(query, values)
    for bdaddr_random, service_type, begin_handle, end_handle, UUID in GATT_services_result:
        UUID = add_dashes_to_UUID128(UUID)
        utype = db_service_type_to_BTIDES_utype(service_type)
        data = ff_GATT_Service({"utype": utype, "begin_handle": begin_handle, "end_handle": end_handle, "UUID": UUID})
        BTIDES_export_GATT_Service(bdaddr=bdaddr, random=bdaddr_random, data=data)

    query = "SELECT bdaddr_random, attribute_handle, UUID FROM GATT_attribute_handles WHERE bdaddr = %s";
    GATT_attribute_handles_result = execute_query(query, values)
    attribute_handles_dict = {}
    for bdaddr_random, attribute_handle, UUID in GATT_attribute_handles_result:
        UUID = add_dashes_to_UUID128(UUID)
        attribute_handles_dict[attribute_handle] = UUID
        data = ff_ATT_handle_entry(attribute_handle, UUID)
        BTIDES_export_ATT_handle(bdaddr=bdaddr, random=bdaddr_random, data=data)

    query = "SELECT bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID FROM GATT_characteristics WHERE bdaddr = %s";
    GATT_characteristics_result = execute_query(query, values)
    declaration_handles_dict = {declaration_handle: (char_properties, char_value_handle, UUID) for bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID in GATT_characteristics_result}
    for bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID in GATT_characteristics_result:
        UUID = add_dashes_to_UUID128(UUID)
        data = {"handle": declaration_handle, "properties": char_properties, "value_handle": char_value_handle, "value_uuid": UUID}
        BTIDES_export_GATT_Characteristic(bdaddr=bdaddr, random=bdaddr_random, data=data)

    query = "SELECT bdaddr_random, char_value_handle, operation, byte_values FROM GATT_characteristics_values WHERE bdaddr = %s";
    GATT_characteristics_values_result = execute_query(query, values)
    # Need to be smarter about storing values into lookup-by-handle dictionary, because there can be multiple distinct values in the database for a single handle
    char_value_handles_dict = {}
    for bdaddr_random, char_value_handle, operation, byte_values in GATT_characteristics_values_result:
        data = {"handle": char_value_handle, "io_array": [ {"io_type": operation, "value_hex_str": byte_values.hex()} ] }
        BTIDES_export_GATT_Characteristic(bdaddr=bdaddr, random=bdaddr_random, data=data)

        if(char_value_handle in char_value_handles_dict.keys()):
            # There is already an entry for this handle, so append the new value to the list of possible values
            char_value_handles_dict[(char_value_handle, operation)].append(byte_values)
        else:
            # There wasn't already an entry, so insert a list of a single value")
            char_value_handles_dict[(char_value_handle, operation)] = [ byte_values ]

    # Changing up the logic to start from the maximum list of all handles in the attributes, characteristics, and read characteristic values tables
    # I will iterate through all of these handles, so nothing gets missed
    values = (bdaddr,bdaddr,bdaddr,bdaddr)
    query = """
    SELECT DISTINCT handle_value
    FROM (
        SELECT attribute_handle AS handle_value
        FROM GATT_attribute_handles
        WHERE bdaddr = %s
        UNION
        SELECT declaration_handle AS handle_value
        FROM GATT_characteristics
        WHERE bdaddr = %s
        UNION
        SELECT char_value_handle AS handle_value
        FROM GATT_characteristics
        WHERE bdaddr = %s
        UNION
        SELECT char_value_handle AS handle_value
        FROM GATT_characteristics_values
        WHERE bdaddr = %s
    ) AS combined_handles
    ORDER BY handle_value ASC;
    """
    GATT_all_known_handles_result = execute_query(query, values)

    # Create a copy of the handle list to keep track of handles we see which never match any Service, to print them out after the fact
    service_match_dict = {}
    for handle, in GATT_all_known_handles_result:
        service_match_dict[handle] = 0

    if(len(GATT_services_result) == 0 and len(service_match_dict) == 0):
        vprint("\tNo GATT Information found.")
        return
    else:
        qprint("\tGATT Information:")

    unknown_UUID128_hash = {}
    # Print semantically-meaningful information
    for bdaddr_random, service_type, svc_begin_handle, svc_end_handle, UUID in GATT_services_result:
        UUID = add_dashes_to_UUID128(UUID)
        service_match_dict[svc_begin_handle] = 1
        UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID)
        qprint(f"\t\t{UUID128_description} {UUID}:")
        qprint(f"\t\tBegin Handle: {svc_begin_handle:03}, End Handle: {svc_end_handle:03}")
        # If BLEScope data output is enabled, and we see an Unknown UUID128, save it to analyze later
        if(not TME.TME_glob.hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
            unknown_UUID128_hash[UUID] = ("Service","\t\t\t")

        # Iterate through all known handles, so nothing gets missed
        for handle, in GATT_all_known_handles_result:
            # Check if this handle is found in the GATT_attribute_handles table, and if so, print that info
            if(handle in attribute_handles_dict.keys()):
                attribute_handle = handle
                UUID128_2 = attribute_handles_dict[handle]
                UUID128_2 = add_dashes_to_UUID128(UUID128_2)
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    service_match_dict[handle] = 1
                    # TODO: handle 2802 (include) eventually
                    if(UUID128_2 == "00002800-0000-1000-8000-00805f9b34fb" \
                       or UUID128_2 == "2800" \
                       or UUID128_2 == "00002801-0000-1000-8000-00805f9b34fb" \
                       or UUID128_2 == "2801" \
                       or UUID128_2 == "00002803-0000-1000-8000-00805f9b34fb" \
                       or UUID128_2 == "2803" ):
                        indent = "\t\t\t"
                    else:
                        indent = "\t\t\t\t"
                    qprint(f"{indent}{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)}), Attribute Handle: {attribute_handle:03}")

            # Check if this handle is found in the GATT_characteristics table, and if so, print that info
            if(handle in declaration_handles_dict.keys()):
                declaration_handle = handle
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    service_match_dict[handle] = 1
                    (char_properties, char_value_handle, UUID) = declaration_handles_dict[handle]
                    UUID = add_dashes_to_UUID128(UUID)
                    UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID)
                    qprint(f"\t\t\t\tProperties: 0x{char_properties:02x} ({characteristic_properties_to_string(char_properties)})\n\t\t\t\tCharacteristic Value UUID: {UUID} ({UUID128_description})\n\t\t\t\tCharacteristic Value Handle: {char_value_handle:03}")
                    if(not TME.TME_glob.hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
                        unknown_UUID128_hash[UUID] = ("Characteristic","\t\t\t")
                    if(not any(key[0] == char_value_handle for key in char_value_handles_dict.keys()) and (char_properties & 0x2 == 0x02)):
                        qprint(f"\t\t\t\tGATT Characteristic Value not successfully read, despite having readable permissions.")

            # Check if this handle is found in the GATT_characteristics_values table, and if so, print that info
            if any(key[0] == handle for key in char_value_handles_dict.keys()):
                char_value_handle = handle
                if any(key[0] == handle and key[1] == type_ATT_ERROR_RSP for key in char_value_handles_dict.keys()):
                    for byte_values in char_value_handles_dict[(handle, type_ATT_ERROR_RSP)]:
                        if(handle <= svc_end_handle and handle >= svc_begin_handle):
                            service_match_dict[handle] = 1
                            error_code = int.from_bytes(byte_values)
                            fmt_byte_values = Fore.RED + Style.BRIGHT + f"{att_error_strings[error_code]}"
                            qprint(f"\t\t\t\tGATT error received when attempting read: {fmt_byte_values}")
                if any(key[0] == handle and key[1] == type_ATT_READ_RSP for key in char_value_handles_dict.keys()):
                    for byte_values in char_value_handles_dict[(handle, type_ATT_READ_RSP)]:
                        if(handle <= svc_end_handle and handle >= svc_begin_handle):
                            service_match_dict[handle] = 1
                            fmt_byte_values = Fore.BLUE + Style.BRIGHT + f"{byte_values}"
                            qprint(f"\t\t\t\tGATT Characteristic Value read as {fmt_byte_values}")
                            if(handle in attribute_handles_dict.keys()):
                                characteristic_value_decoding("\t\t\t\t\t", attribute_handles_dict[handle], byte_values) #NOTE: This leads to sub-optimal formatting due to the unconditional tabs above. TODO: adjust

    # Second pass:
    # Iterate through all known handles, printing only information about handles which never matched any service
    # First check if the only handles which weren't printed out thus far are service handles (in which case we don't need to do the below)
    service_handle_count = 0
    for handle, in GATT_all_known_handles_result:
        if(service_match_dict[handle] == 1):
            service_handle_count += 1
            continue
    if (len(GATT_all_known_handles_result) != (service_handle_count)):
        qprint(f"\t\tGATT Service Unknown! Handle does not match any Service ranges that we received from the device!")
        for handle, in GATT_all_known_handles_result:
            if(service_match_dict[handle] == 1):
                continue
            # Check if this handle is found in the GATT_attribute_handles table, and if so, print that info
            if(handle in attribute_handles_dict.keys()):
                attribute_handle = handle
                UUID128_2 = attribute_handles_dict[handle]
                UUID128_2 = add_dashes_to_UUID128(UUID128_2)
                qprint(f"\t\t\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)}), Attribute Handle: {attribute_handle:03}")

            # Check if this handle is found in the GATT_characteristics table, and if so, print that info
            if(handle in declaration_handles_dict.keys()):
                declaration_handle = handle
                (char_properties, char_value_handle, UUID) = declaration_handles_dict[handle]
                UUID = add_dashes_to_UUID128(UUID)
                UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID)
                qprint(f"\t\t\t\tGATT Characteristic declaration:\t{UUID} ({UUID128_description})\n\t\t\t\t\t\t\t\t\tHandle: {declaration_handle:03}\n\t\t\t\t\t\t\t\t\tProperties: 0x{char_properties:02x} ({characteristic_properties_to_string(char_properties)})")
                if(not TME.TME_glob.hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
                    unknown_UUID128_hash[UUID] = ("Characteristic","\t\t\t")

            # Check if this handle is found in the GATT_characteristics_values table, and if so, print that info
            if(handle in char_value_handles_dict.keys()):
                char_value_handle = handle
                for byte_values in char_value_handles_dict[handle]:
                    qprint(f"\t\t\t\t(G)ATT handle {handle} read results: {byte_values}")
                    # FIXME: do we have an enclosing characteristic? If so do the below...
                    #characteristic_value_decoding("\t\t\t\t\t", UUID, byte_values) #NOTE: This leads to sub-optimal formatting due to the unconditional tabs above. TODO: adjust

    # Print raw GATT data minus the values read from characteristics. This can be a superset of the above due to handles potentially not being within the subsetted ranges of enclosing Services or Descriptors
    if(len(GATT_services_result) != 0):
        if(TME.TME_glob.verbose_print):
            qprint(f"\n\t\tGATTPrint:")
            for bdaddr_random, service_type, svc_begin_handle, svc_end_handle, UUID in GATT_services_result:
                UUID = add_dashes_to_UUID128(UUID)
                qprint(f"\t\t{UUID} ({match_known_GATT_UUID_or_custom_UUID(UUID)}:")
                qprint(f"\t\tBegin Handle: {svc_begin_handle:03}, End Handle: {svc_end_handle:03}")
                #qprint(f"\t\tGATT Service: Begin Handle: {svc_begin_handle:03}\tEnd Handle: {svc_end_handle:03}   \tUUID128: {UUID} ({match_known_GATT_UUID_or_custom_UUID(UUID)})")
            for bdaddr_random, attribute_handle, UUID128_2 in GATT_attribute_handles_result:
                UUID128_2 = add_dashes_to_UUID128(UUID128_2)
                qprint(f"\t\tGATT Descriptor: Attribute Handle: {attribute_handle:03},\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)})")
            for bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID in GATT_characteristics_result:
                UUID = add_dashes_to_UUID128(UUID)
                qprint(f"\t\tGATT Characteristic Declaration: {UUID}, Properties: 0x{char_properties:02x}, Characteristic Handle: {declaration_handle:03}, Characteristic Value Handle: {char_value_handle:03}")
            qprint("")

        if(not TME.TME_glob.hideBLEScopedata and len(unknown_UUID128_hash) > 0):
            match_found = False
            qprint("\t\tBLEScope Analysis: Vendor-specific UUIDs were found. Analyzing if there are any known associations with Android app packages based on BLEScope data.")
            for UUID in unknown_UUID128_hash.keys():
                if(UUID.replace('-','') == "00000000000000000000000000000000"):
                    continue
                (type, indent) = unknown_UUID128_hash[UUID]
                match_found = print_associated_android_package_names(type, indent, UUID)
            if(not match_found):
                qprint("\t\t\tNo matches found\n")
            else:
                qprint("")

    qprint("")
