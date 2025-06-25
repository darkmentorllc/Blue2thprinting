########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_metadata import *
from TME.TME_AdvChan import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

###########################################
# Unique ID / Potential Trackability Report
###########################################
# This is meant to convey data about what, if anything, may be directly serving as a device-unique-ID (DUID!), which would allow for device tracking

g_printed_unique_id_header = False
g_printed_possible_unique_id_header = False

def print_unique_ID_header_if_needed():
    global g_printed_unique_id_header
    if not TME.TME_glob.g_printed_unique_id_header:
        qprint(f"{i2}Unique ID:")
        TME.TME_glob.g_printed_unique_id_header = True

def print_possible_unique_ID_header_if_needed():
    global g_printed_possible_unique_id_header
    if not TME.TME_glob.g_printed_possible_unique_id_header:
        qprint(f"{i2}Possible unique ID:")
        TME.TME_glob.g_printed_possible_unique_id_header = True

# Check if the name contains a serial number pattern
# TODO: are there other patterns that are safe to use which won't cause too many false positives?
def name_possibly_contains_serial_number(name):
    patterns = [
        r'[0-9]{8,}',  # Numeric serial numbers of at least 8 characters
    ]

    for pattern in patterns:
        if re.search(pattern, name, re.IGNORECASE):
            return True

    return False

def print_possible_unique_ID_warning(indent, name, data_source):
    print_possible_unique_ID_header_if_needed()

    qprint(f"{indent}* This device contains a name \"{name}\" found via {data_source}.")
    if(name_possibly_contains_serial_number(name)):
        qprint(f"{indent}{i1}The name contains 8 or more sequential numeric characters, which may be a unique serial number. If so, it could possibly be used to track the device.")
        return
    else:
        qprint(f"{indent}{i1}The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
        qprint(f"{indent}{i2}It is left to the user to investigate whether this name represents a unique ID or not.")
        qprint(f"{indent}{i2}E.g. look for other instances of this name in your own data via the --name-regex option, or search by name at wigle.net.")


def name_contains_bdaddr(indent, name, bdaddr, name_source):
    print_unique_ID_header_if_needed()
    # Check if the name contains the full 6-byte BDADDR in one of 4 formats:
    # big-endian hex, non-colon-deliminated (e.g. Triones:10020000004F, Keco-74F07DD08DE9:100, Travler 00171AB3CCF5)
    # big-endian hex, colon-deliminated (e.g. RWLS-00:07:80:C2:65:B9)
    # little-endian hex, non-colon-deliminated (e.g. InVueCT300-11200D50A000, AK1-FF6E003B0305, FenSensCB336B1319CC)
    # little-endian hex, colon-deliminated (e.g. LE-TILE_a6:3b:7c:79:0e:ce (literally the only example I have for BLE, so it might not be worth searching for))
    # First remove colons from bdaddr for easier matching
    bdaddr_no_colons = bdaddr.replace(':', '')

    # Create big and little endian versions
    bdaddr_be = bdaddr_no_colons
    bdaddr_le = ''.join(reversed([bdaddr_no_colons[i:i+2] for i in range(0, 12, 2)]))

    # Create patterns with flexible delimiters and exact byte matching
    patterns = [
        bdaddr_be,  # Big endian no delimiters
        bdaddr_le,  # Little endian no delimiters
        ''.join([f"{bdaddr_be[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 12, 2)]),  # Big endian with any special char delimiter
        ''.join([f"{bdaddr_le[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 12, 2)])   # Little endian with any special char delimiter
    ]

    # Check if any pattern is in the name (case insensitive)
    for pattern in patterns:
        if re.search(pattern, name, re.IGNORECASE):
            qprint(f"{indent}* Name '{name}' from {name_source} matches 6-byte regex pattern {pattern} which is derived from the BDADDR, and is therefore unique.")
            return True

    # Check if the name contains 3-bytes of BDADDR in one of 4 formats:
    # big-endian hex, colon-deliminated (e.g. Keyfree DEV 37:FD:D9, BRC1H 91:AD:D6, ALAM (56:CC:BE))
    # big-endian hex, non-colon-deliminated (e.g. MPEON SMART LE(4F2512))
    # little-endian hex, colon-deliminated
    # little-endian hex, non-colon-deliminated
    # Get the 3 most and least significant bytes
    msb_be = bdaddr_no_colons[:6]  # First 3 bytes
    lsb_be = bdaddr_no_colons[-6:]  # Last 3 bytes
    msb_le = ''.join(reversed([msb_be[i:i+2] for i in range(0, 6, 2)]))
    lsb_le = ''.join(reversed([lsb_be[i:i+2] for i in range(0, 6, 2)]))

    # Create patterns for 3-byte matches
    patterns = [
        msb_be, lsb_be,  # Big endian no delimiters
        msb_le, lsb_le,  # Little endian no delimiters
        ''.join([f"{msb_be[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 6, 2)]),  # MSB big endian with delimiter
        ''.join([f"{lsb_be[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 6, 2)]),  # LSB big endian with delimiter
        ''.join([f"{msb_le[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 6, 2)]),  # MSB little endian with delimiter
        ''.join([f"{lsb_le[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 6, 2)])   # LSB little endian with delimiter
    ]

    # Check if any 3-byte pattern matches
    for pattern in patterns:
        if re.search(pattern, name, re.IGNORECASE):
            qprint(f"{indent}* Name '{name}' from {name_source} matches 3-byte regex pattern {pattern} which is derived from the BDADDR, and is therefore unique.")
            return True

    # Check if the name contains 2-bytes of BDADDR in one of 4 formats:
    # big-endian hex, colon-deliminated (e.g. rES7A0:56, LG SH7B(AD:7A), rMSOD ZT 740:0B)
    # big-endian hex, non-colon-deliminated (e.g. PMP3:9460, e.g. bLink-67F1-BLE)
    # little-endian hex, colon-deliminated
    # little-endian hex, non-colon-deliminated
    # Get the 2 most and least significant bytes
    msb_be = bdaddr_no_colons[:4]  # First 2 bytes
    lsb_be = bdaddr_no_colons[-4:]  # Last 2 bytes
    msb_le = ''.join(reversed([msb_be[i:i+2] for i in range(0, 4, 2)]))
    lsb_le = ''.join(reversed([lsb_be[i:i+2] for i in range(0, 4, 2)]))

    # Create patterns for 2-byte matches
    patterns = [
        msb_be, lsb_be,  # Big endian no delimiters
        msb_le, lsb_le,  # Little endian no delimiters
        ''.join([f"{msb_be[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 4, 2)]),  # MSB big endian with delimiter
        ''.join([f"{lsb_be[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 4, 2)]),  # LSB big endian with delimiter
        ''.join([f"{msb_le[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 4, 2)]),  # MSB little endian with delimiter
        ''.join([f"{lsb_le[i:i+2]}[^0-9A-Fa-f\\w]?" for i in range(0, 4, 2)])   # LSB little endian with delimiter
    ]

    # Check if any 2-byte pattern matches
    for pattern in patterns:
        if re.search(pattern, name, re.IGNORECASE):
            qprint(f"{indent}* Name '{name}' from {name_source} matches 2-byte pattern {pattern} which is derived from the BDADDR, and is therefore highly likely to be unique.")
            return True

    return False


# First parameter of tuple is whether the caller should continue
# Second parameter is whether a result was found or not
def check_name_for_most_specific_match(indent, name_string, bdaddr, name_source):
    global privacy_report_no_results_found
    if(name_matches_nonunique_nameprint(name_string)): # Don't bother users with names which are known to be non-unique
        return True
    pattern = name_matches_presumed_unique_nameprint(name_string)
    if(pattern != None):
        qprint(f"{indent}* Name '{name_string}' from {name_source} matches regex pattern {pattern} which is believed to represent a unique ID.")
        TME.TME_glob.privacy_report_no_results_found = False
        return True
    if(name_contains_bdaddr(indent, name_string, bdaddr, name_source)):
        TME.TME_glob.privacy_report_no_results_found = False
        return True
    return False


def print_UniqueIDReport(bdaddr):
    global privacy_report_no_results_found

    #================#
    # BDADDR data #
    #================#
    qprint(f"{i1}Unique ID / Potential Trackability Report:")
    type = get_bdaddr_type(bdaddr, -1)
    if(type == "Classic" or type == "Public" or type == "Random Static"):
        print_unique_ID_header_if_needed()
        qprint(f"{i3}* BDADDR is of type *{type}*, which is not randomized over time, and therefore can be used to track the device.")
        TME.TME_glob.privacy_report_no_results_found = False

    # Or if it has Classic BDADDR embedded in Microsoft Swift Pair MSD
    values = (bdaddr,)
    le_query = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s AND device_BT_CID = 6 AND manufacturer_specific_data REGEXP '^030180'"
    le_result = execute_query(le_query, values)

    if (len(le_result) != 0):
        for(le_evt_type, manufacturer_specific_data) in le_result:
            BTC_BDADDR_bytes = bytes.fromhex(manufacturer_specific_data[6:18])
            BTC_BDADDR_str = f"{BTC_BDADDR_bytes[5]:02x}:{BTC_BDADDR_bytes[4]:02x}:{BTC_BDADDR_bytes[3]:02x}:{BTC_BDADDR_bytes[2]:02x}:{BTC_BDADDR_bytes[1]:02x}:{BTC_BDADDR_bytes[0]:02x}"
            print_unique_ID_header_if_needed()
            qprint(f"{i3}Bluetooth Classic BDADDR, which is not randomized over time, of value {BTC_BDADDR_str} is embedded in Microsoft Swift Pair advertised Manufacturer-Specific Data, and therefore can be used to track the device.")

    #===================================================#
    # GATT "Serial Number" (0x2a25) Characteristic data #
    #===================================================#
    #=============================================================#
    # GATT "UID for Medical Devices" (0x2bff) Characteristic data #
    #=============================================================#
    # To be clear, we don't necessarily need to have successfully read the value for this. The mere presence of a definition for it is suggestive enough of the presence of a DUID to report on it

    we_have_GATT = False
    chars_query = "SELECT UUID FROM GATT_characteristics WHERE bdaddr = %s"
    chars_result = execute_query(chars_query, values)
    if(len(chars_result) > 0): we_have_GATT = True

    if(we_have_GATT):
        # If we have GATT data, check if we have successfully read a "Serial Number" (00002a25-0000-1000-8000-00805f9b34fb) value or a "UID for Medical Devices" (00002bff-0000-1000-8000-00805f9b34fb)
        # Iterate through every UUID128 from the GATT_Characteristics database query
        for (UUID_db,) in chars_result:
            # Remove dashes and make lowercase
#            UUID_db_ = UUID_db.replace('-','').lower()
            if(check_if_UUIDs_match(UUID_db, "2a25")):
                print_unique_ID_header_if_needed()
                qprint(f"{i3}* This device indicates that it contains GATT Characteristic 0x2a25 (\"Serial Number\"). Because serial numbers are by definition meant to be device-unique, and not change over time, this could be used to track the device.")
                TME.TME_glob.privacy_report_no_results_found = False
            if(check_if_UUIDs_match(UUID_db, "2bff")):
                print_unique_ID_header_if_needed()
                qprint(f"{i3}* This device indicates that it contains GATT Characteristic 0x2bff (\"UID (Unique ID) for Medical Devices\"). Because this UID is by definition meant to be device-unique, and not change over time, this could be used to track the device.")
                TME.TME_glob.privacy_report_no_results_found = False

    # TODO: Apple FindMy (designed to be tracked) and/or Continuity (leaked phone number if they didn't fix that yet) evidence?

    #================#
    # NamePrint data #
    #================#

    NamePrint_match = False
    # This is a search for names that are known to be unique, as captured in the metadata v2 with a NamePrint_UniqueID tag in a record with a 2thprint_NamePrint regex
    str = lookup_metadata_by_nameprint(bdaddr, 'NamePrint_UniqueID')
    if(str[2:6] == "True"):
        print_unique_ID_header_if_needed()
        qprint(f"{i3}* The name of this device is one which is known to serve as an unchanging, device-unique, ID. Therefore the name can be used to track the device.")
        TME.TME_glob.privacy_report_no_results_found = False
        NamePrint_match = True

    #===========#
    # Name data #
    #===========#
    # If a device merely has a name, we have to leave it up to the user to decide if it looks like it's a DUID or not

    # TODO: This needs to be refactored into a common function across all its usages somehow. Because this sequence of looking up names is a recurring pattern,
    # but with slightly different usage. But leaving it lazy for now since I'm not interested in premature optimization :D

    # Don't bother giving a less-preceise match if a more-precise match was already found.
    if(NamePrint_match == False):
        eir_query = "SELECT name_hex_str FROM EIR_bdaddr_to_name WHERE bdaddr = %s"
        eir_result = execute_query(eir_query, values)
        name_source = "Bluetooth Classic Extended Inquiry Responses"
        for (name_hex_str,) in eir_result:
            name = get_utf8_string_from_hex_string(name_hex_str)
            if(check_name_for_most_specific_match(f"{i3}", name, bdaddr, name_source)):
                continue
            print_possible_unique_ID_warning(f"{i3}", name, name_source)
            TME.TME_glob.privacy_report_no_results_found = False

        hci_query = "SELECT name_hex_str FROM HCI_bdaddr_to_name WHERE bdaddr = %s"
        hci_result = execute_query(hci_query, values)
        name_source = "Bluetooth Low Energy Scan Responses"
        for (name_hex_str,) in hci_result:
            name = get_utf8_string_from_hex_string(name_hex_str)
            if(check_name_for_most_specific_match(f"{i3}", name, bdaddr, name_source)):
                continue
            print_possible_unique_ID_warning(f"{i3}", name, name_source)
            TME.TME_glob.privacy_report_no_results_found = False

        le_query = "SELECT name_hex_str, le_evt_type FROM LE_bdaddr_to_name WHERE bdaddr = %s"
        le_result = execute_query(le_query, values)
        name_source = "Bluetooth Low Energy Advertisements"
        for name_hex_str, le_evt_type in le_result:
            name = get_utf8_string_from_hex_string(name_hex_str)
            if(check_name_for_most_specific_match(f"{i3}", name, bdaddr, name_source)):
                continue
            print_possible_unique_ID_warning(f"{i3}", name, name_source)
            TME.TME_glob.privacy_report_no_results_found = False

        chars_query = "SELECT cv.bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle AND cv.bdaddr = c.bdaddr WHERE c.UUID = '2a00' and cv.bdaddr = %s;"
        chars_result = execute_query(chars_query, values)
        name_source = "GATT"
        if(len(chars_result) > 0):
            for (bdaddr, byte_values) in chars_result:
                name = byte_values.decode('utf-8', 'ignore')
                if(check_name_for_most_specific_match(f"{i3}", name, bdaddr, name_source)):
                    continue
                print_possible_unique_ID_warning(f"{i3}", name, name_source)
                TME.TME_glob.privacy_report_no_results_found = False

        ms_msd_query = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030';"
        ms_msd_result = execute_query(ms_msd_query, values)
        for (le_evt_type, manufacturer_specific_data) in ms_msd_result:
            name_source = f"Microsoft Swift Pair Manufacturer-specific data in {get_le_event_type_string(le_evt_type)} packets"
            ms_msd_name = extract_ms_msd_name(manufacturer_specific_data)
            if(len(ms_msd_name) > 0 and ms_msd_name != "No name found"):
                if(check_name_for_most_specific_match(f"{i3}", ms_msd_name, bdaddr, name_source)):
                    continue
                print_possible_unique_ID_warning(f"{i3}", ms_msd_name, name_source)
                TME.TME_glob.privacy_report_no_results_found = False

        regex = '^01[0-9a-f]{4}0a' # Pulling out so the {4} isn't interpreted as part of the format string
        values2 = (bdaddr, regex)
        ms_msd_query2 = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP %s;"
        ms_msd_result2 = execute_query(ms_msd_query2, values2)
        for (le_evt_type, manufacturer_specific_data) in ms_msd_result2:
            name_source = f"Microsoft Beacon Manufacturer-specific data in {get_le_event_type_string(le_evt_type)} packets"
            try:
                ms_msd_name2 = get_utf8_string_from_hex_string(manufacturer_specific_data[20:])
            except:
                ms_msd_name2 = ""
            if(len(ms_msd_name2) > 0):
                if(check_name_for_most_specific_match(f"{i3}", ms_msd_name2, bdaddr, name_source)):
                    continue
                print_possible_unique_ID_warning(f"{i3}", ms_msd_name2, name_source)
                TME.TME_glob.privacy_report_no_results_found = False

    if(TME.TME_glob.privacy_report_no_results_found):
        qprint(f"{i2}No privacy report results found. (But current checks are far from exhaustive.)")

    qprint("")
