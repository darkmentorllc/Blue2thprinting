########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import re
import time
from TME_helpers import *
from TME_AdvChan import *

########################################
# Metadata v2 helper functions
########################################

# Had to move this earlier for use in match_str_to_ChipMaker()
# The ChipMaker_names_and_BT_CIDs will be used as regexp expressions in MySQL queries to find the associated IEEE OUIs
# Note: Apple and Samsung have been observed to get their endianness wrong. But Samsung devices have also been observed using a completely arbitrary/wrong 0xFF19 value in the BT CID field of MSD...
ChipMaker_names_and_BT_CIDs = {'^Actions': [0x03E0], 'Airoha Technology Corp': [0x94], 'Ambiq': [0x09AC], 'Atheros Communications': [0x45], '^Apple': [0x004C, 0x4C00], 'Barrot Technology': [0x08E7], 'beken': [0x05F0], 'Bestechnic': [0x02B0], 'Bluetrum': [0x642], 'Broadcom': [0xF], 'Casambi': [0x03C3], '^Chipsea Technologies': [0x06A7], 'Cypress Semiconductor': [0x131], 'Dialog Semiconductor': [0xD2], 'Espressif': [0x02E5], 'HiSilicon': [0x010F], 'Hong Kong HunterSun': [0x01BF], 'Infineon': [0x09], 'Ingchips': [0x06AC], 'Intel Corp': [0x02], '^LAPIS': [0x0179], 'Marvell': [0x48], 'MediaTek': [0x46], 'Nordic Semiconductor': [0x59], 'NXP': [0x25], '^ON Semiconductor': [0x0362], 'PHYPLUS': [0x0504], 'Qualcomm': [0x0A, 0x1D], 'Realtek': [0x5D], 'RivieraWaves': [0x60], 'Samsung': [0x0075, 0x7500, 0xff19], 'Shanghai Mountain View Silicon': [0x06D9, 0xD906], 'Shanghai wuqi': [0x0A06], 'Shenzhen Goodix Technology': [0x04F7], 'Silicon Laboratories': [0x02FF], 'Spreadtrum Communications': [0x01EC], 'STMicro': [0x30], 'ST Microelectronics': [0x30], 'Telink Semiconductor': [0x0211], 'Texas Instruments': [0x0D], '^Universal Electronics': [0x93], 'Vimicro': [0x81], 'Yichip Microelectronics': [0x050E], 'Zhuhai Jieli': [0x05D6], 'MILWAUKEE': [123]}

# Misc note: RivieraWaves licenses BT IP. E.g. to Espressif (so some Espressif things will have Espressif OUI & RivieraWaves BT CID) https://www.ceva-ip.com/press/espressif-licenses-and-deploys-ceva-bluetooth-in-esp32-iot-chip/
# Misc note: Hong Kong HunterSun licensed BT IP from Andes: https://www.andestech.com/en/2018/06/20/huntersun-corporation-licenses-andescore-n1068a-s-for-its-hs6601-single-chip-bluetooth-soc-targeting-wireless-audio-applications/
# Misc note: "ST Microelectronics*" in BT CIDs, "STMicro*" in IEEE OUIs :-/
# As a reminder to myself, these are the company names & BT CIDs that don't have IEEE OUIs = {'Bestechnic': [0x02B0], 'Bluetrum': [0x642], 'Casambi': [0x03C3], 'Hong Kong HunterSun': [0x01BF], 'Ingchips': [0x06AC], 'RivieraWaves': [0x60], 'Shanghai Mountain View Silicon': [0x06D9, 0xD906], 'Shanghai wuqi': [0x0A06], 'ST Microelectronics': [0x30], 'Zhuhai Jieli': [0x05D6]]

# Returns a string to be printed by the caller
def lookup_metadata_by_nameprint(bdaddr, metadata_type):
    # First see if we have a name for this device
    we_have_a_name = False

    # Query for EIR_bdaddr_to_name table
    eir_query = f"SELECT device_name FROM EIR_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    if(len(eir_result) > 0): we_have_a_name = True

    # Query for RSP_bdaddr_to_name table
    rsp_query = f"SELECT device_name FROM RSP_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    rsp_result = execute_query(rsp_query)
    if(len(rsp_result) > 0): we_have_a_name = True

    # Query for LE_bdaddr_to_name table
    le_query = f"SELECT device_name, le_evt_type FROM LE_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    le_result = execute_query(le_query)
    if(len(le_result) > 0): we_have_a_name = True

    # Query GATT Characteristic values for Device Name (0x2a00) entries, and then checking regex in python instead of MySQL, because the byte values may not be directly translatable to UTF-8 within MySQL
    chars_query = f"SELECT cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.read_handle = c.char_value_handle AND cv.device_bdaddr = c.device_bdaddr WHERE c.UUID128 = '00002a00-0000-1000-8000-00805f9b34fb' AND cv.device_bdaddr = '{bdaddr}';"
    chars_result = execute_query(chars_query)
    if(len(chars_result) > 0): we_have_a_name = True

    # Query Manufacturer-Specific Data (MSD) to see if there's types like Microsoft's Swift Pair which are known to contain a Device Name
    ms_msd_name_present = False
    ms_msd_query = f"SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}' AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030';"
    ms_msd_result = execute_query(ms_msd_query)
    for (le_evt_type, manufacturer_specific_data) in ms_msd_result:
        ms_msd_name = extract_ms_msd_name(manufacturer_specific_data)
        if(len(ms_msd_name) > 0):
            we_have_a_name = True
            ms_msd_name_present = True

    # Query Manufacturer-Specific Data (MSD) to see if there's types like Microsoft's Beacons which are known to contain a Device Name
    ms_msd_name_present2 = False
    regex = '^01[0-9a-f]{4}0a' # Pulling out so the {4} isn't interpreted as part of the format string
    ms_msd_query2 = f"SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}' AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '{regex}';"
    ms_msd_result2 = execute_query(ms_msd_query2)
    for (le_evt_type, manufacturer_specific_data) in ms_msd_result2:
        try:
            ms_msd_name2 = bytes.fromhex(manufacturer_specific_data[20:]).decode('utf-8')
        except:
            ms_msd_name2 = ""
        if(len(ms_msd_name2) > 0):
            we_have_a_name = True
            ms_msd_name_present2 = True

    if(we_have_a_name):
        # If we have a name, consult with the metadata_v2 data, and see if any entries have Chip Maker data
        # and if so, try that nameprint against the name(s) for this device
        for heading, metadata in TME_glob.metadata_v2.items():
            if('2thprint_NamePrint' in metadata.keys() and metadata_type in metadata.keys()):
                # Compensate for difference in how MySQL regex requires three \ to escape ( whereas python only requires one
                regex_pattern = metadata['2thprint_NamePrint'].replace('\\\\\\', '\\')
                if(len(eir_result) > 0):
                    for (name,) in eir_result:
                        if re.search(regex_pattern, name):
                            return f"\t\t{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (EIR_bdaddr_to_name table)"
                if(len(rsp_result) > 0):
                    for (name,) in rsp_result:
                        if re.search(regex_pattern, name):
                            return f"\t\t{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (RSP_bdaddr_to_name table)"
                if(len(le_result) > 0):
                    for name, le_evt_type in le_result:
                        if re.search(regex_pattern, name):
                            return f"\t\t{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (LE_bdaddr_to_name table, le_evt_type = {get_le_event_type_string(le_evt_type)})"
                if(len(chars_result) > 0):
                    for (byte_values,) in chars_result:
                        name = byte_values.decode('utf-8', 'ignore')
                        if re.search(regex_pattern, name):
                            return f"\t\t{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (GATT_characteristics & GATT_characteristics_values tables)"
                if(ms_msd_name_present):
                    for (le_evt_type, manufacturer_specific_data) in ms_msd_result:
                        ms_msd_name = extract_ms_msd_name(manufacturer_specific_data)
                        if(len(ms_msd_name) > 0):
                            if re.search(regex_pattern, ms_msd_name):
                                return f"\t\t{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (Microsoft Swift Pair data in manufacturer_specific_data table)"
                if(ms_msd_name_present2):
                    for (le_evt_type, manufacturer_specific_data) in ms_msd_result2:
                        try:
                            ms_msd_name2 = bytes.fromhex(manufacturer_specific_data[20:]).decode('utf-8')
                        except:
                            ms_msd_name2 = ""
                        if(len(ms_msd_name2) > 0):
                            if re.search(regex_pattern, ms_msd_name2):
                                return f"\t\t{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (Microsoft Beacon data in manufacturer_specific_data table)"


    # Else return an empty string to indicate we have no name or no match
    return ""

# Returns a string to be printed by the caller
def lookup_ChipPrint_by_GATT(bdaddr):
    # First see if we have GATT data for this device
    we_have_GATT = False
    model_name_match = 0
    s = ""

    chars_query = f"SELECT UUID128,char_value_handle FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'"
    chars_result = execute_query(chars_query)
    if(len(chars_result) > 0): we_have_GATT = True

    if(we_have_GATT):
        # If we have GATT data, check if we have successfully read a "Model Number String" (00002a24-0000-1000-8000-00805f9b34fb) value or a "Hardware Revision String" (00002a27-0000-1000-8000-00805f9b34fb)
        # Iterate through every UUID128 from the GATT_Characteristics database query
        for (UUID128_db,char_value_handle) in chars_result:
            # Remove dashes and make lowercase
            UUID128_db_ = UUID128_db.replace('-','').lower()
            if((UUID128_db_ == "00002a2400001000800000805f9b34fb" or UUID128_db_ == "00002a2700001000800000805f9b34fb") and model_name_match == 0):
                # If so, go lookup the actual data behind it, so we can see if the "Model Number String" is a Chip
                char_value_query = f"SELECT byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}' and read_handle = {char_value_handle:03}"
                char_value_result = execute_query(char_value_query)
                if(len(char_value_result) > 0):
                    for (byte_values,) in char_value_result:
                        tmpstr = byte_values.decode('utf-8')
                        #print(f"byte_values: {tmpstr}")
                        # Now consult with the metadata_v2 data, and see if any entries have a 2thprint_Chip_GATT_Model_Number which matches the value observed in the database
                        for heading, metadata in TME_glob.metadata_v2.items():
                            if('2thprint_Chip_GATT_Model_Number' in metadata):
                                # FIXME: I think this is probably an insufficient matching criteria. E.g. a "Jabra Evolve 65e" device might match "Jabra Elite Active" metadata and then the printout would be a bit confusing
                                if(tmpstr == metadata['2thprint_Chip_GATT_Model_Number']):
                                    model_name_match = 1
                                    s = f"\t\t{metadata['2thprint_Chip']} -> From GATT \"Model/Hardware Number String\" match with '{metadata['2thprint_Device_Model']}' device metadata (GATT_characteristics & GATT_characteristics_values tables & metadata_v2)"

    # Return something appropriate for printing, or an empty string if no match
    return s

# If we have a string, we want to see if it matches any of the ChipMaker names, if we treat them as regexes
# Returns the matched name, or an empty string
def match_str_to_ChipMaker(str):
    matched_company_name = ""
    for chipmaker in ChipMaker_names_and_BT_CIDs.keys():
        if(re.search(chipmaker, str)):
            matched_company_name = chipmaker

    return matched_company_name # can be empty

# Pass '2thprint_ChipMaker_GATTprint' as metadata_input_type and '2thprint_Chip_Maker' as metadata_output_type to find ChipMaker-specific GATT info
# Returns a list of strings to be printed by the caller, or an empty list
def lookup_metadata_by_GATTprint(bdaddr, metadata_input_type, metadata_output_type):
    # First see if we have GATT data for this device
    we_have_GATT = False

    services_query = f"SELECT UUID128 FROM GATT_services WHERE device_bdaddr = '{bdaddr}'"
    services_result = execute_query(services_query)
    if(len(services_result) > 0): we_have_GATT = True

    chars_query = f"SELECT UUID128,char_value_handle FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'"
    chars_result = execute_query(chars_query)
    if(len(chars_result) > 0): we_have_GATT = True

    le_adv_query = f"SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s WHERE device_bdaddr = '{bdaddr}'"
    le_adv_result = execute_query(le_adv_query)
    if(len(le_adv_result) > 0): we_have_GATT = True

    le_adv2_query = f"SELECT str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE device_bdaddr = '{bdaddr}'"
    le_adv2_result = execute_query(le_adv2_query)
    if(len(le_adv2_result) > 0): we_have_GATT = True

    eir_adv_query = f"SELECT str_UUID128s FROM EIR_bdaddr_to_UUID128s WHERE device_bdaddr = '{bdaddr}'"
    eir_adv_result = execute_query(eir_adv_query)
    if(len(eir_adv_result) > 0): we_have_GATT = True

    str_list = []
    manufacturer_name_match = 0 # Only match this one time

    if(we_have_GATT):
        # If we have GATT data, consult with the metadata_v2 data, and see if any entries have Chip Maker data
        # and if so, try that nameprint against the name(s) for this device
        for heading, metadata in TME_glob.metadata_v2.items():
            # Confirm that this entry even has what we're looking for
            if('GATT_Vendor_Specific' in metadata.keys() and metadata_input_type in metadata.keys() and metadata_output_type in metadata.keys()):

                # Iterate through every UUID128 from the metadata
                for UUID128_metadata in metadata['GATT_Vendor_Specific'].keys():
                    UUID128_metadata_ = UUID128_metadata.replace('-','').lower()

                    if(len(services_result) > 0):
                        # Iterate through every UUID128 from the GATT_services database query
                        for (UUID128_db,) in services_result:
                            # Remove dashes and make lowercase
                            UUID128_db_ = UUID128_db.replace('-','').lower()
                            if(UUID128_db_ == UUID128_metadata_):
                                str_list.append(f"\t\t{metadata[metadata_output_type]} -> From GATTprint match on {UUID128_metadata} = \"{metadata['GATT_Vendor_Specific'][UUID128_metadata]}\" (GATT_services table)")

                    if(len(chars_result) > 0):
                        # Iterate through every UUID128 from the GATT_Characteristics database query
                        for (UUID128_db,char_value_handle) in chars_result:
                            # Remove dashes and make lowercase
                            UUID128_db_ = UUID128_db.replace('-','').lower()
                            if(UUID128_db_ == UUID128_metadata_):
                                str_list.append(f"\t\t{metadata[metadata_output_type]} -> From GATTprint match on {UUID128_metadata} = \"{metadata['GATT_Vendor_Specific'][UUID128_metadata]}\" (GATT_characteristics table)")

                            # While we're here, check if this device has a "Manufacturer Name String" characteristic
                            if(UUID128_db_ == "00002a2900001000800000805f9b34fb" and manufacturer_name_match == 0):
                                # If so, go lookup the actual data behind it, so we can see if the "Manufacturer Name" is a ChipMaker
                                char_value_query = f"SELECT byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}' and read_handle = {char_value_handle:03}"
                                char_value_result = execute_query(char_value_query)
                                if(len(char_value_result) > 0):
                                    for (byte_values,) in char_value_result:
                                        tmpstr = byte_values.decode('utf-8')
                                        #print(f"byte_values: {tmpstr}")
                                        match = match_str_to_ChipMaker(tmpstr)
                                        if(match != ""):
                                            manufacturer_name_match = 1
                                            str_list.append(f"\t\t{tmpstr} -> From GATT \"Manufacturer Name String\" regex-based match with {match} (GATT_characteristics & GATT_characteristics_values tables)")

                    if(len(le_adv_result) > 0):
                        # Iterate through every UUID128 from the LE_bdaddr_to_UUID128s database query
                        # NOTE! : While I don't believe it currently is, treat every str_UUID128s entry as if it could be a comma-deliminated list of UUID128s w/o dashes (because that's how some other wireshark output for UUID128s is)
                        for (str_UUID128s,) in le_adv_result:
                            UUID128_list = str_UUID128s.split(",")
                            if(len(UUID128_list) != 0):
                                for UUID128_db in UUID128_list:
                                    # Remove dashes and make lowercase
                                    UUID128_db_ = UUID128_db.replace('-','').lower()
                                    if(UUID128_db_ == UUID128_metadata_):
                                        str_list.append(f"\t\t{metadata[metadata_output_type]} -> From GATTprint match on {UUID128_metadata} = \"{metadata['GATT_Vendor_Specific'][UUID128_metadata]}\" (LE_bdaddr_to_UUID128s table)")

                    if(len(le_adv2_result) > 0):
                        # Iterate through every UUID128 from the LE_bdaddr_to_UUID128s database query
                        # NOTE! : While I don't believe it currently is, treat every str_UUID128s entry as if it could be a comma-deliminated list of UUID128s w/o dashes (because that's how some other wireshark output for UUID128s is)
                        for (str_UUID128s,) in le_adv2_result:
                            UUID128_list = str_UUID128s.split(",")
                            if(len(UUID128_list) != 0):
                                for UUID128_db in UUID128_list:
                                    # Remove dashes and make lowercase
                                    UUID128_db_ = UUID128_db.replace('-','').lower()
                                    if(UUID128_db_ == UUID128_metadata_):
                                        str_list.append(f"\t\t{metadata[metadata_output_type]} -> From GATTprint match on {UUID128_metadata} = \"{metadata['GATT_Vendor_Specific'][UUID128_metadata]}\" (LE_bdaddr_to_UUID128_service_solicit table)")

                    if(len(eir_adv_result) > 0):
                        # Iterate through every UUID128 from the LE_bdaddr_to_UUID128s database query
                        # NOTE! : Every str_UUID128s entry is a comma-deliminated list of UUID128s w/o dashes (because that's how some other wireshark output is)
                        for (str_UUID128s,) in eir_adv_result:
                            UUID128_list = str_UUID128s.split(",")
                            if(len(UUID128_list) != 0):
                                for UUID128_db in UUID128_list:
                                    # Remove dashes and make lowercase
                                    UUID128_db_ = UUID128_db.replace('-','').lower()
                                    if(UUID128_db_ == UUID128_metadata_):
                                        str_list.append(f"\t\t{metadata[metadata_output_type]} -> From GATTprint match on {UUID128_metadata} = \"{metadata['GATT_Vendor_Specific'][UUID128_metadata]}\" (EIR_bdaddr_to_UUID128s table)")

    # Else return an empty list to indicate we have no name or no match
    return str_list


########################################
# ChipMaker Info
########################################

ChipMaker_OUI_hash = {}

def create_ChipMaker_OUI_hash():
    for company in ChipMaker_names_and_BT_CIDs.keys():
        oui_query = f"SELECT device_bdaddr,company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP '{company}'"
        oui_result = execute_query(oui_query)
        for (oui,company_name) in oui_result:
            ChipMaker_OUI_hash[oui.lower()] = company_name # I'm using the IEEE name instead of the company regex since it will generally be longer and more verbose, since I cut down some regexes to match both IEEE OUIs and BT CIDs

    #print(ChipMaker_OUI_hash)

# This function consults with the various sources of information which we might have that suggest a possible ChipMaker, and prints them all
# If there are conflicting ChipMaker possibilities, it's up to the person to look at the results and determine which source(s) of data they find the most credible
def print_ChipMakerPrint(bdaddr):
    bdaddr = bdaddr.strip().lower()
    time_profile = False

    no_results_found = True

    print(f"\t2thprint_ChipMakerPrint:")

    if(time_profile): print(f"Start = {time.time()}")
    #=====================#
    # LL_VERSION_IND data #
    #=====================#

    # So far experiments have indicated that LL_VERSION_IND company ID is the Chip Maker.
    ble_version_query = f"SELECT device_BT_CID, device_bdaddr_type FROM BLE2th_LL_VERSION_IND WHERE device_bdaddr = '{bdaddr}'"
    ble_version_result = execute_query(ble_version_query)

    if(len(ble_version_result) != 0):
        no_results_found = False
        # There could be multiple results if we got some corrupt data, which resulted in inserting N distinct entries into the db, or if we had old and new Wireshark parsing
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (device_BT_CID,device_bdaddr_type) in ble_version_result:
            print(f"\t\t{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From LL_VERSION_IND: Company ID (BLE2th_LL_VERSION_IND)")

    if(time_profile): print(f"LMP_VERSION_REQ = {time.time()}")
    #==========================#
    # LMP_VERSION_REQ/RSP data #
    #==========================#

    # So far experiments have indicated that LMP_VERSION_REQ/RSP company ID is the Chip Maker.
    btc_version_query = f"SELECT device_BT_CID FROM BTC2th_LMP_version_res WHERE device_bdaddr = '{bdaddr}'"
    btc_version_result = execute_query(btc_version_query)

    if(len(btc_version_result) != 0):
        no_results_found = False
        # There could be multiple results if we got some corrupt data, which resulted in inserting N distinct entries into the db, or if we had old and new Wireshark parsing
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (device_BT_CID,) in btc_version_result:
            print(f"\t\t{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From LMP_VERSION_REQ/RSP: Company ID (BTC2th_LMP_version_res table)")

    if(time_profile): print(f"NamePrint = {time.time()}")
    #================#
    # NamePrint data #
    #================#
    s = lookup_metadata_by_nameprint(bdaddr, '2thprint_Chip_Maker')
    if(s != ""):
        print(s)
        no_results_found = False

    if(time_profile): print(f"OUI = {time.time()}")
    #===============#
    # IEEE OUI data #
    #===============#
    random = False

    oui = bdaddr[0:8]
    is_classic = is_bdaddr_classic(bdaddr)
    if(is_classic):
        if(oui in ChipMaker_OUI_hash.keys()):
            print(f"\t\t{ChipMaker_OUI_hash[oui]} -> From IEEE OUI matched with BT Classic address")
            no_results_found = False
    else:
        random = is_bdaddr_le_and_random(bdaddr)
        if(not random):
            if(oui in ChipMaker_OUI_hash.keys()):
                print(f"\t\t{ChipMaker_OUI_hash[oui]} -> From IEEE OUI matched with BT Classic address")
                no_results_found = False

    if(time_profile): print(f"GATT = {time.time()}")
    #=============================#
    # GATT known chip-maker UUIDs #
    #=============================#
    str_list = lookup_metadata_by_GATTprint(bdaddr, '2thprint_ChipMaker_GATTprint', '2thprint_Chip_Maker')
    if(len(str_list) > 0):
        no_results_found = False
        for s in str_list:
            print(s)

    # FIXME: TODO! Start with Quintic->NXP OTA = 0xfee8, can also do CSR/Qualcomm = 0x000a and also need to look up in PnP ID if present
    #=============================# 
    # Known chip-maker UUID16s    #
    #=============================#

    if(time_profile): print(f"MSD BTC = {time.time()}")
    #========================================#
    # Manufacturer-Specific Data (MSD) - BTC #
    #========================================#
    # In general more companies tend to leave this uninitialized for BTC, than for BLE. So a BTC hit is more likely to be accurate than BLE
    MSD_query = f"SELECT device_BT_CID FROM EIR_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}'"
    MSD_result = execute_query(MSD_query)

    if(len(MSD_result) != 0):
        # There could be multiple results if there are multiple distinct data blobs seen
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (device_BT_CID,) in MSD_result:
            # Check if this CID corresponds to a ChipMaker
            for name in ChipMaker_names_and_BT_CIDs.keys():
                BT_CID_list = ChipMaker_names_and_BT_CIDs[name]
                if(device_BT_CID in BT_CID_list):
                    print(f"\t\t{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From BT Classic Extended Inquiry Response Manufacturer-Specific Data Company ID (EIR_bdaddr_to_MSD table)")
                    no_results_found = False
    

    if(time_profile): print(f"MSD BLE = {time.time()}")
    #========================================#
    # Manufacturer-Specific Data (MSD) - BLE #
    #========================================#
    MSD_query = f"SELECT device_BT_CID, le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}'"
    MSD_result = execute_query(MSD_query)

    if(len(MSD_result) != 0):
        # There could be multiple results if there are multiple distinct data blobs seen or multiple event types
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (device_BT_CID,le_evt_type, manufacturer_specific_data) in MSD_result:
            # Check if this CID corresponds to a ChipMaker
            for name in ChipMaker_names_and_BT_CIDs.keys():
                BT_CID_list = ChipMaker_names_and_BT_CIDs[name]
                if(device_BT_CID in BT_CID_list):
                    no_results_found = False
                    print(f"\t\t{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From BT Classic Extended Inquiry Response Manufacturer-Specific Data Company ID (LE_bdaddr_to_MSD table {get_le_event_type_string(le_evt_type)})")
                    if(device_BT_CID == 76 and manufacturer_specific_data[0:4] == "0215"):
                        print(f"\t\t\tCAVEAT: This company ID was seen as part of an 'iBeacon', which is a standardized beacon format used by many companies other than Apple. So this is a low-signal indication of ChipMaker")

    if(time_profile): print(f"End = {time.time()}")
    if(no_results_found):
        print(f"\t\tNo ChipMakerPrint(s) found.")

    # Final padding print of print_ChipMakerPrint()
    print()

########################################
# Chip Info
########################################

# We currently have limited visibility into where sub-versions correlate to specific chip IDs. So this is just a PoC for now.
def chip_by_sub_version(sub_version, device_BT_CID):
    if(device_BT_CID == 15):
        if(sub_version == 0x6308): 
            return "Broadcom BCM4387C2" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x6308.py
        if(sub_version == 0x6206):
            return "Broadcom BCM4345C1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x6206.py
        if(sub_version == 0x617e):
            return "Broadcom BCM4345B0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x617e.py
        if(sub_version == 0x6119):
            return "Broadcom BCM4345C0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x6119.py
        if(sub_version == 0x6109):
            return "Broadcom BCM4335C0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x6109.py
        if(sub_version == 0x6103):
            return "Broadcom BCM4355C0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x6103.py
        if(sub_version == 0x422a):
            return "Broadcom BCM2070B0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x422a.py
        if(sub_version == 0x4228):
            return "Broadcom BCM4378B1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x4228.py
        if(sub_version == 0x420e):
            return "Broadcom BCM4347B1 or Cypress CYW20739B1 or Broadcom BCM4349B1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x420e.py & https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x420e_iphone.py & https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x4208):
            return "Cypress CYW20735B1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x4208.py
        if(sub_version == 0x4196):
            return "Broadcom BCM20702A2" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x4196.py
        if(sub_version == 0x411a):
            return "Broadcom BCM4347B0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x411a.py
        if(sub_version == 0x4109):
            return "Broadcom BCM4345B0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x4109.py
        if(sub_version == 0x3040):
            return "Broadcom BCM4364B3" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x3040.py
        if(sub_version == 0x3032):
            return "Broadcom BCM4364B3" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x3032.py
        if(sub_version == 0x240f):
            return "Broadcom BCM4358A3" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x240f.py
        if(sub_version == 0x2230):
            return "Broadcom BCM20703A2" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x2230.py
        if(sub_version == 0x220e):
            return "Broadcom BCM20702A1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x220e.py
        if(sub_version == 0x220c):
            return "Cypress CYW20819A1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x220c.py
        if(sub_version == 0x220b):
            return "Cypress CYW20706" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x220b.py
        if(sub_version == 0x2209):
            return "Broadcom BCM43430A1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x2209.py
        if(sub_version == 0x21d0):
            return "Broadcom BCM2046" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x21d0.py
        if(sub_version == 0x21a9):
            return "Broadcom BCM20703A1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x21a9.py
        if(sub_version == 0x2056):
            return "Broadcom BCM4364B0" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x2056.py
        if(sub_version == 0x203a):
            return "Broadcom BCM4377B3" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x203a.py
        if(sub_version == 0x2033):
            return "Broadcom BCM4377B3" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x2033.py
        if(sub_version == 0x1111):
            return "Broadcom BCM4375B1" # from https://github.com/seemoo-lab/internalblue/blob/master/internalblue/fw/fw_0x1111.py
        if(sub_version == 0x4103):
            return "Broadcom BCM4330B1" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x410d):
            return "Broadcom BCM4334B0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x410e):
            return "Broadcom BCM43341B0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x4204):
            return "Broadcom BCM2076B1" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x4406):
            return "Broadcom BCM4324B3" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x4606):
            return "Broadcom BCM4324B5" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x610c):
            return "Broadcom BCM4354" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x2122):
            return "Broadcom BCM4343A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x6606):
            return "Broadcom BCM4345C0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x230f):
            return "Broadcom BCM4356A2" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x420d):
            return "Broadcom BCM4349B1" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x4217):
            return "Broadcom BCM4329B1" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x6106):
            return "Broadcom BCM4359C0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x4106):
            return "Broadcom BCM4335A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x410c):
            return "Broadcom BCM43430B0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x2119):
            return "Broadcom BCM4373A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c
        if(sub_version == 0x2105):
            return "Broadcom BCM20703A1" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c, technically from bcm_usb_subver_table, but I expect it to be the same between BT & USB (e.g. it was for 0x220e)
        if(sub_version == 0x210b):
            return "Broadcom BCM43142A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c, technically from bcm_usb_subver_table, but I expect it to be the same between BT & USB
        if(sub_version == 0x2112):
            return "Broadcom BCM4314A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c, technically from bcm_usb_subver_table, but I expect it to be the same between BT & USB
        if(sub_version == 0x2118):
            return "Broadcom BCM20702A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c, technically from bcm_usb_subver_table, but I expect it to be the same between BT & USB
        if(sub_version == 0x2126):
            return "Broadcom BCM4335A0" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c, technically from bcm_usb_subver_table, but I expect it to be the same between BT & USB
        if(sub_version == 0x6607):
            return "Broadcom BCM4350C5" # from https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btbcm.c, technically from bcm_usb_subver_table, but I expect it to be the same between BT & USB

    # If we get here, return empty string denoting nothing found
    return ""

# This function consults with the various sources of information which we might have that suggest a possible Chip, and prints them all
# If there are conflicting Chip possibilities, it's up to the person to look at the results and determine which source(s) of data they find the most credible
def print_ChipPrint(bdaddr):
    bdaddr = bdaddr.strip().lower()

    no_results_found = True

    print(f"\t2thprint_ChipPrint:")

    #=====================#
    # LL_VERSION_IND data #
    #=====================#

    # We currently have limited visibility into where sub-versions correlate to specific chip IDs. So this is just a PoC for now.

    version_query = f"SELECT ll_sub_version, device_BT_CID FROM BLE2th_LL_VERSION_IND WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)

    if(len(version_result) != 0):
        no_results_found = False
        # The only time there should be multiple results is if we got some corrupt data, which resulted in inserting N distinct entries into the db
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (ll_sub_version,device_BT_CID) in version_result:
            chip_name = chip_by_sub_version(ll_sub_version, device_BT_CID)
            if(chip_name != ""):
                print(f"\t\t{chip_name} -> From LL_VERSION_IND info (BLE2th_LL_VERSION_IND table)")

    #==========================#
    # LMP_VERSION_REQ/RSP data #
    #==========================#

    # So far experiments have indicated that LMP_VERSION_REQ/RSP company ID is the Chip Maker.

    version_query = f"SELECT lmp_sub_version, device_BT_CID FROM BTC2th_LMP_version_res WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)

    if(len(version_result) != 0):
        no_results_found = False
        # The only time there should be multiple results is if we got some corrupt data, which resulted in inserting N distinct entries into the db
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (lmp_sub_version, device_BT_CID) in version_result:
            chip_name = chip_by_sub_version(lmp_sub_version, device_BT_CID)
            if(chip_name != ""):
                print(f"\t\t{chip_name} -> From LMP_VERSION_REQ/RSP info (BTC2th_LMP_version_res table)")

    #================#
    # NamePrint data #
    #================#
    str = lookup_metadata_by_nameprint(bdaddr, '2thprint_Chip')
    if(str != ""):
        print(str)
        no_results_found = False

    #======================#
    # GATT Model Name data #
    #======================#
    str = lookup_ChipPrint_by_GATT(bdaddr)
    if(str != ""):
        print(str)
        no_results_found = False


    if(no_results_found):
        print(f"\t\tNo ChipPrint(s) found.")

    print()

########################################
# ModuleMaker Info
########################################

########################################
# Module Info
########################################

########################################
# DeviceMaker Info
########################################

########################################
# DeviceModel Info
########################################

def print_DeviceModel(bdaddr):
    bdaddr = bdaddr.strip().lower()

    no_results_found = True

    print(f"\t2thprint_DeviceModelPrint:")