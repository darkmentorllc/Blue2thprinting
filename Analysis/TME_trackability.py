########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

from TME_helpers import *
from TME_metadata import *
from TME_AdvChan import *

###########################################
# Unique ID / Potential Trackability Report
###########################################
# This is meant to convey data about what, if anything, may be directly serving as a device-unique-ID (DUID!), which would allow for device tracking

def print_UniqueIDReport(bdaddr):

    no_results_found = True

    #================#
    # BDADDR data #
    #================#
    print("\tUnique ID / Potential Trackability Report:")
    type = get_bdaddr_type(bdaddr, -1)
    if(type == "Classic" or type == "Public" or type == "Random Static"):
        print(f"\t\tUnique ID: BDADDR is of type *{type}*, which is not randomized over time, and therefore can be used to track the device.")
        no_results_found = False

    # Or if it has Classic BDADDR embedded in Microsoft Swift Pair MSD
    le_query = f"SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}' AND device_BT_CID = 6 AND manufacturer_specific_data REGEXP '^030180'"
    le_result = execute_query(le_query)

    if (len(le_result) != 0):
        for(le_evt_type, manufacturer_specific_data) in le_result:
            BTC_BDADDR_bytes = bytes.fromhex(manufacturer_specific_data[6:18])
            BTC_BDADDR_str = f"{BTC_BDADDR_bytes[5]:02x}:{BTC_BDADDR_bytes[4]:02x}:{BTC_BDADDR_bytes[3]:02x}:{BTC_BDADDR_bytes[2]:02x}:{BTC_BDADDR_bytes[1]:02x}:{BTC_BDADDR_bytes[0]:02x}"
            print(f"\t\tUnique ID: Bluetooth Classic BDADDR, which is not randomized over time, of value {BTC_BDADDR_str} is embedded in Microsoft Swift Pair advertised Manufacturer-Specific Data, and therefore can be used to track the device.")

    #===================================================#
    # GATT "Serial Number" (0x2a25) Characteristic data #
    #===================================================#
    #=============================================================#
    # GATT "UID for Medical Devices" (0x2bff) Characteristic data #
    #=============================================================#
    # To be clear, we don't necessarily need to have successfully read the value for this. The mere presence of a definition for it is suggestive enough of the presence of a DUID to report on it

    we_have_GATT = False
    chars_query = f"SELECT UUID128 FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'"
    chars_result = execute_query(chars_query)
    if(len(chars_result) > 0): we_have_GATT = True

    if(we_have_GATT):
        # If we have GATT data, check if we have successfully read a "Model Number String" (00002a24-0000-1000-8000-00805f9b34fb) value or a "Hardware Revision String" (00002a27-0000-1000-8000-00805f9b34fb)
        # Iterate through every UUID128 from the GATT_Characteristics database query
        for (UUID128_db,) in chars_result:
            # Remove dashes and make lowercase
            UUID128_db_ = UUID128_db.replace('-','').lower()
            if(UUID128_db_ == "00002a2500001000800000805f9b34fb"):
                print(f"\t\tUnique ID: This device indicates that it contains GATT Characteristic 0x2a25 (\"Serial Number\"). Because serial numbers are by definition meant to be device-unique, and not change over time, this could be used to track the device.")
                no_results_found = False
            if(UUID128_db_ == "00002bff00001000800000805f9b34fb"):
                print(f"\t\tUnique ID: This device indicates that it contains GATT Characteristic 0x2bff (\"UID (Unique ID) for Medical Devices\"). Because this UID is by definition meant to be device-unique, and not change over time, this could be used to track the device.")
                no_results_found = False

    # TODO: Apple FindMy (designed to be tracked) and/or Continuity (leaked phone number if they didn't fix that yet) evidence?

    #================#
    # NamePrint data #
    #================#
    NamePrint_match = False
    # This is a search for names that are known to be unique, as captured in the metadata v2 with a NamePrint_UniqueID tag in a record with a 2thprint_NamePrint regex
    str = lookup_metadata_by_nameprint(bdaddr, 'NamePrint_UniqueID')
    if(str[2:6] == "True"):
        print(f"\t\tUnique ID: The name of this device is one which is known to serve as an unchanging, device-unique, ID. Therefore the name can be used to track the device.")
        no_results_found = False
        NamePrint_match = True

    #===========#
    # Name data #
    #===========#
    # If a device merely has a name, we have to leave it up to the user to decide if it looks like it's a DUID or not

    # TODO: This needs to be refactored into a common function across all its usages somehow. Because this sequence of looking up names is a recurring pattern, but with slightly different usage. But leaving it lazy for now since I'm not interested in premature optimization :D

    # Don't bother giving a less-preceise match if a more-precise match was already found.
    if(NamePrint_match == False):
        eir_query = f"SELECT device_name FROM EIR_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
        eir_result = execute_query(eir_query)
        for (name,) in eir_result:
            print(f"\t\t*Possible* Unique ID:\tThis device contains a name \"{name}\" found via Bluetooth Classic Extended Inquiry Responses. The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
            print(f"\t\t\t\t\tIt is left to the user to investigate whether this name represents a unique ID or not. E.g. look for other instances of this name in your own data via the --nameregex option, or search by name at wigle.net.")
            no_results_found = False

        rsp_query = f"SELECT device_name FROM RSP_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
        rsp_result = execute_query(rsp_query)
        for (name,) in rsp_result:
            print(f"\t\t*Possible* Unique ID:\tThis device contains a name \"{name}\" found via Bluetooth Low Energy Scan Responses. The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
            print(f"\t\t\t\t\tIt is left to the user to investigate whether this name represents a unique ID or not. E.g. look for other instances of this name in your own data via the --nameregex option, or search by name at wigle.net.")
            no_results_found = False

        le_query = f"SELECT device_name, bdaddr_random, le_evt_type FROM LE_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
        le_result = execute_query(le_query)
        for name, random, le_evt_type in le_result:
            print(f"\t\t*Possible* Unique ID:\tThis device contains a name \"{name}\" found via Bluetooth Low Energy Advertisements. The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
            print(f"\t\t\t\t\tIt is left to the user to investigate whether this name represents a unique ID or not. E.g. look for other instances of this name in your own data via the --nameregex option, or search by name at wigle.net.")
            no_results_found = False

        chars_query = f"SELECT cv.device_bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.read_handle = c.char_value_handle AND cv.device_bdaddr = c.device_bdaddr WHERE c.UUID128 = '00002a00-0000-1000-8000-00805f9b34fb' and cv.device_bdaddr = '{bdaddr}';"
        chars_result = execute_query(chars_query)
        if(len(chars_result) > 0):
            for (bdaddr, byte_values) in chars_result:
                name = byte_values.decode('utf-8', 'ignore')
                print(f"\t\t*Possible* Unique ID:\tThis device contains a name \"{name}\" found via GATT. The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
                print(f"\t\t\t\t\tIt is left to the user to investigate whether this name represents a unique ID or not. E.g. look for other instances of this name in your own data via the --nameregex option, or search by name at wigle.net.")
                no_results_found = False

        ms_msd_query = f"SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}' AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030';"
        ms_msd_result = execute_query(ms_msd_query)
        for (le_evt_type, manufacturer_specific_data) in ms_msd_result:
            ms_msd_name = extract_ms_msd_name(manufacturer_specific_data)
            if(len(ms_msd_name) > 0):
                print(f"\t\t*Possible* Unique ID:\tThis device contains a name \"{ms_msd_name}\" found via Microsoft Swift Pair Manufacturer-specific data in {get_le_event_type_string(le_evt_type)} packets. The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
                print(f"\t\t\t\t\tIt is left to the user to investigate whether this name represents a unique ID or not. E.g. look for other instances of this name in your own data via the --nameregex option, or search by name at wigle.net.")
                no_results_found = False

        regex = '^01[0-9a-f]{4}0a' # Pulling out so the {4} isn't interpreted as part of the format string
        ms_msd_query2 = f"SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}' AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '{regex}';"
        ms_msd_result2 = execute_query(ms_msd_query2)
        for (le_evt_type, manufacturer_specific_data) in ms_msd_result2:
            try:
                ms_msd_name2 = bytes.fromhex(manufacturer_specific_data[20:]).decode('utf-8')
            except:
                ms_msd_name2 = ""
            if(len(ms_msd_name2) > 0):
                print(f"\t\t*Possible* Unique ID:\tThis device contains a name \"{ms_msd_name2}\" found via Microsoft Beacon Manufacturer-specific data in {get_le_event_type_string(le_evt_type)} packets. The name itself does not match a known-unique-ID pattern, but that could just mean it has not been captured in our metadata yet.")
                print(f"\t\t\t\t\tIt is left to the user to investigate whether this name represents a unique ID or not. E.g. look for other instances of this name in your own data via the --nameregex option, or search by name at wigle.net.")
                no_results_found = False

    if(no_results_found):
        print("\t\tNo privacy report results found. (But current checks are far from exhaustive.)")

    print()
