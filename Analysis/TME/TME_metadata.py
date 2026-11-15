########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

import re
import time
from TME.TME_helpers import *
from TME.TME_AdvChan import *
from TME.TME_BTIDES_LLCP import *
from TME.TME_BTIDES_LMP import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements
from TME.TME_LLCP import lookup_LL_VERSION_IND_metadata
from TME.TME_LMP import lookup_LMP_VERSION_metadata
from TME.TME_version_metadata import (
    lookup_company_subversion_metadata,
    metadata_chip_display_name,
)

########################################
# Metadata v2 helper functions
########################################

# Had to move this earlier for use in match_str_to_ChipMaker()
# The ChipMaker_names_and_BT_CIDs will be used as regexp expressions in MySQL queries to find the associated IEEE OUIs
# Note: Apple and Samsung have been observed to get their endianness wrong. But Samsung devices have also been observed using a completely arbitrary/wrong 0xFF19 value in the BT CID field of MSD...
ChipMaker_names_and_BT_CIDs = {'^Actions': [0x03E0], 'Airoha Technology Corp': [0x94], 'Ambiq': [0x09AC], 'Atheros Communications': [0x45], '^Apple': [0x004C, 0x4C00], 'Barrot Technology': [0x08E7], 'beken': [0x05F0], 'Bestechnic': [0x02B0], 'Bluetrum': [0x642], 'Broadcom': [0xF], 'Casambi': [0x03C3], '^Chipsea Technologies': [0x06A7], 'Cypress Semiconductor': [0x131], 'Dialog Semiconductor': [0xD2], 'Espressif': [0x02E5], 'HiSilicon': [0x010F], 'Hong Kong HunterSun': [0x01BF], 'Infineon': [0x09], 'Ingchips': [0x06AC], 'Intel Corp': [0x02], '^LAPIS': [0x0179], 'Marvell': [0x48], 'MediaTek': [0x46], '^Microchip Technology': [0xCD], 'Nordic Semiconductor': [0x59], 'NXP': [0x25], '^ON Semiconductor': [0x0362], 'PHYPLUS': [0x0504], 'Qualcomm': [0x0A, 0x1D], 'Realtek': [0x5D], 'RivieraWaves': [0x60], 'Samsung': [0x0075, 0x7500, 0xff19], 'Shanghai Mountain View Silicon': [0x06D9, 0xD906], 'Shanghai wuqi': [0x0A06], 'Shenzhen Goodix Technology': [0x04F7], 'Silicon Laboratories': [0x02FF], 'Spreadtrum Communications': [0x01EC], 'STMicro': [0x30], 'ST Microelectronics': [0x30], 'Telink Semiconductor': [0x0211], 'Texas Instruments': [0x0D], '^Universal Electronics': [0x93], 'Vimicro': [0x81], 'Yichip Microelectronics': [0x050E], 'Zhuhai Jieli': [0x05D6]}

# FIXME: why was , 'MILWAUKEE': [123] in the above list previously?

# Misc note: RivieraWaves licenses BT IP. E.g. to Espressif (so some Espressif things will have Espressif OUI & RivieraWaves BT CID) https://www.ceva-ip.com/press/espressif-licenses-and-deploys-ceva-bluetooth-in-esp32-iot-chip/
# Misc note: Hong Kong HunterSun licensed BT IP from Andes: https://www.andestech.com/en/2018/06/20/huntersun-corporation-licenses-andescore-n1068a-s-for-its-hs6601-single-chip-bluetooth-soc-targeting-wireless-audio-applications/
# Misc note: "ST Microelectronics*" in BT CIDs, "STMicro*" in IEEE OUIs :-/
# As a reminder to myself, these are the company names & BT CIDs that don't have IEEE OUIs = {'Bestechnic': [0x02B0], 'Bluetrum': [0x642], 'Casambi': [0x03C3], 'Hong Kong HunterSun': [0x01BF], 'Ingchips': [0x06AC], 'RivieraWaves': [0x60], 'Shanghai Mountain View Silicon': [0x06D9, 0xD906], 'Shanghai wuqi': [0x0A06], 'ST Microelectronics': [0x30], 'Zhuhai Jieli': [0x05D6]]

# Returns a string to be printed by the caller
def lookup_metadata_by_nameprint(bdaddr, bdaddr_random, metadata_type):
    def print_section_header_if_needed():
        if metadata_type == 'NamePrint_UniqueID':
            if not TME.TME_glob.g_printed_unique_id_header:
                qprint(f"{i2}Unique ID:")
                TME.TME_glob.g_printed_unique_id_header = True
        elif metadata_type == '2thprint_Module':
            print_ModulePrint_header_if_needed()
        elif metadata_type == '2thprint_Module_Maker':
            print_ModuleMakerPrint_header_if_needed()
        else:
            print_ChipPrint_header_if_needed()

    # First see if we have a name for this device
    we_have_a_name = False

    # Query for EIR_bdaddr_to_name table
    values = (bdaddr,)
    eir_query = "SELECT name_hex_str FROM EIR_bdaddr_to_name WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)
    if(len(eir_result) > 0): we_have_a_name = True

    # Query for HCI_bdaddr_to_name table
    hci_query = "SELECT name_hex_str FROM HCI_bdaddr_to_name WHERE bdaddr = %s"
    hci_result = execute_query(hci_query, values)
    if(len(hci_result) > 0): we_have_a_name = True

    # Query for LE_bdaddr_to_name table
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_query = "SELECT name_hex_str, le_evt_type FROM LE_bdaddr_to_name WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_query = "SELECT name_hex_str, le_evt_type FROM LE_bdaddr_to_name WHERE bdaddr = %s"
    le_result = execute_query(le_query, values)
    if(len(le_result) > 0): we_have_a_name = True

    # Query GATT Characteristic values for Device Name (0x2a00) entries, and then checking regex in python instead of MySQL, because the byte values may not be directly translatable to UTF-8 within MySQL
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr_random, bdaddr)
        chars_query = "SELECT cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle AND cv.bdaddr_random = c.bdaddr_random AND cv.bdaddr = c.bdaddr WHERE c.UUID = '2a00' AND c.bdaddr_random = %s AND cv.bdaddr_random = %s AND cv.bdaddr = %s;"
    else:
        values = (bdaddr,)
        chars_query = "SELECT cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle AND cv.bdaddr = c.bdaddr WHERE c.UUID = '2a00' AND cv.bdaddr = %s;"
    chars_result = execute_query(chars_query, values)
    if(len(chars_result) > 0): we_have_a_name = True

    # Query Manufacturer-Specific Data (MSD) to see if there's types like Microsoft's Swift Pair which are known to contain a Device Name
    ms_msd_name_present = False
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        ms_msd_query = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND bdaddr = %s AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030'"
    else:
        values = (bdaddr,)
        ms_msd_query = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030'"
    ms_msd_result = execute_query(ms_msd_query, values)
    for (le_evt_type, manufacturer_specific_data) in ms_msd_result:
        ms_msd_name = extract_ms_msd_name(manufacturer_specific_data)
        if(len(ms_msd_name) > 0):
            we_have_a_name = True
            ms_msd_name_present = True

    # Query Manufacturer-Specific Data (MSD) to see if there's types like Microsoft's Beacons which are known to contain a Device Name
    ms_msd_name_present2 = False
    regex = '^01[0-9a-f]{4}0a' # Pulling out so the {4} isn't interpreted as part of the format string
    if(bdaddr_random is not None):
        values2 = (bdaddr_random, bdaddr, regex)
        ms_msd_query2 = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND bdaddr = %s AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP %s"
    else:
        values2 = (bdaddr, regex)
        ms_msd_query2 = "SELECT le_evt_type, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s AND device_BT_CID = 0006 AND manufacturer_specific_data REGEXP %s"
    ms_msd_result2 = execute_query(ms_msd_query2, values2)
    for (le_evt_type, manufacturer_specific_data) in ms_msd_result2:
        try:
            ms_msd_name2 = get_utf8_string_from_hex_string(manufacturer_specific_data[20:])
        except:
            ms_msd_name2 = ""
        if(len(ms_msd_name2) > 0):
            we_have_a_name = True
            ms_msd_name_present2 = True

    if(we_have_a_name):
        # If we have a name, consult with the metadata_v2 data, and see if any entries have Chip Maker data
        # and if so, try that nameprint against the name(s) for this device
        for heading, metadata in TME.TME_glob.metadata_v2.items():
            if('2thprint_NamePrint' in metadata.keys() and metadata_type in metadata.keys()):
                # Compensate for difference in how MySQL regex requires three \ to escape ( whereas python only requires one
                regex_pattern = metadata['2thprint_NamePrint'].replace('\\\\\\', '\\')
                if(len(eir_result) > 0):
                    for (name_hex_str,) in eir_result:
                        name = get_utf8_string_from_hex_string(name_hex_str)
                        if re.search(regex_pattern, name):
                            print_section_header_if_needed()
                            return f"{i2}{metadata[metadata_type]} -> From NamePrint match on {regex_pattern}{" (DB:EIR_bdaddr_to_name)" if TME.TME_glob.verbose_print else ""}"
                if(len(hci_result) > 0):
                    for (name_hex_str,) in hci_result:
                        name = get_utf8_string_from_hex_string(name_hex_str)
                        if re.search(regex_pattern, name):
                            print_section_header_if_needed()
                            return f"{i2}{metadata[metadata_type]} -> From NamePrint match on {regex_pattern}{" (DB:HCI_bdaddr_to_name)" if TME.TME_glob.verbose_print else ""}"
                if(len(le_result) > 0):
                    for name_hex_str, le_evt_type in le_result:
                        name = get_utf8_string_from_hex_string(name_hex_str)
                        if re.search(regex_pattern, name):
                            print_section_header_if_needed()
                            return f"{i2}{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} ({"DB:LE_bdaddr_to_name, " if TME.TME_glob.verbose_print else ""}le_evt_type = {get_le_event_type_string(le_evt_type)})"
                if(len(chars_result) > 0):
                    for (byte_values,) in chars_result:
                        name = byte_values.decode('utf-8', 'ignore',)
                        if re.search(regex_pattern, name):
                            print_section_header_if_needed()
                            return f"{i2}{metadata[metadata_type]} -> From NamePrint match on {regex_pattern}{" (DB:GATT_characteristics & DB:GATT_characteristics_values)" if TME.TME_glob.verbose_print else ""}"
                if(ms_msd_name_present):
                    for (le_evt_type, manufacturer_specific_data) in ms_msd_result:
                        ms_msd_name = extract_ms_msd_name(manufacturer_specific_data)
                        if(len(ms_msd_name) > 0):
                            if re.search(regex_pattern, ms_msd_name):
                                print_ChipPrint_header_if_needed()
                                return f"{i2}{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (Microsoft Swift Pair data{" in DB:LE_bdaddr_to_MSD" if TME.TME_glob.verbose_print else ""})"
                if(ms_msd_name_present2):
                    for (le_evt_type, manufacturer_specific_data) in ms_msd_result2:
                        try:
                            ms_msd_name2 = get_utf8_string_from_hex_string(manufacturer_specific_data[20:])
                        except:
                            ms_msd_name2 = ""
                        if(len(ms_msd_name2) > 0):
                            if re.search(regex_pattern, ms_msd_name2):
                                print_ChipPrint_header_if_needed()
                                return f"{i2}{metadata[metadata_type]} -> From NamePrint match on {regex_pattern} (Microsoft Beacon data{" in DB:LE_bdaddr_to_MSD" if TME.TME_glob.verbose_print else ""})"

    # Else return an empty string to indicate we have no name or no match
    return ""

# Returns a string to be printed by the caller
def lookup_ChipPrint_by_GATT(bdaddr, bdaddr_random):
    # First see if we have GATT data for this device
    we_have_GATT = False
    model_name_match = 0
    s = ""

    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        chars_query = "SELECT UUID,char_value_handle FROM GATT_characteristics WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        chars_query = "SELECT UUID,char_value_handle FROM GATT_characteristics WHERE bdaddr = %s"
    chars_result = execute_query(chars_query, values)
    if(len(chars_result) > 0): we_have_GATT = True

    if(we_have_GATT):
        # If we have GATT data, check if we have successfully read a "Model Number String" (00002a24-0000-1000-8000-00805f9b34fb) value or a "Hardware Revision String" (00002a27-0000-1000-8000-00805f9b34fb)
        # Iterate through every UUID128 from the GATT_Characteristics database query
        for (UUID128_db,char_value_handle) in chars_result:
            # Remove dashes and make lowercase
            UUID128_db_ = UUID128_db.replace('-','').lower()
            if( (check_if_UUIDs_match(UUID128_db_, "2a24") or check_if_UUIDs_match(UUID128_db_, "2a27")) and model_name_match == 0):
                # If so, go lookup the actual data behind it, so we can see if the "Model Number String" is a Chip
                if(bdaddr_random is not None):
                    values = (bdaddr_random, bdaddr, char_value_handle)
                    char_value_query = "SELECT byte_values FROM GATT_characteristics_values WHERE bdaddr_random = %s AND bdaddr = %s and char_value_handle = %s"
                else:
                    values = (bdaddr, char_value_handle)
                    char_value_query = "SELECT byte_values FROM GATT_characteristics_values WHERE bdaddr = %s and char_value_handle = %s"
                char_value_result = execute_query(char_value_query, values)
                if(len(char_value_result) > 0):
                    for (byte_values,) in char_value_result:
                        tmpstr = byte_values.decode('utf-8', 'ignore')
                        #qprint(f"byte_values: {tmpstr}")
                        # Now consult with the metadata_v2 data, and see if any entries have a 2thprint_Chip_GATT_Model_Number which matches the value observed in the database
                        for heading, metadata in TME.TME_glob.metadata_v2.items():
                            if('2thprint_Chip_GATT_Model_Number' in metadata):
                                # FIXME: I think this is probably an insufficient matching criteria. E.g. a "Jabra Evolve 65e" device might match "Jabra Elite Active" metadata and then the printout would be a bit confusing
                                if(tmpstr == metadata['2thprint_Chip_GATT_Model_Number']):
                                    model_name_match = 1
                                    s = f"{i2}{metadata['2thprint_Chip']} -> From GATT \"Model/Hardware Number String\" match with '{metadata['2thprint_Device_Model']}' device metadata{" (DB:GATT_characteristics & DB:GATT_characteristics_values & metadata_v2)" if TME.TME_glob.verbose_print else ""}"

    # Return something appropriate for printing, or an empty string if no match
    return s


def _gatt_uuid16(uuid):
    """Return a Bluetooth-base UUID16, or None for other UUIDs."""
    if uuid is None:
        return None
    compact = uuid.replace('-', '').lower()
    if len(compact) == 4:
        return compact
    if len(compact) == 32 and compact.startswith('0000') and compact[8:] == '00001000800000805f9b34fb':
        return compact[4:8]
    return None


def _gatt_value_matches_rule(rule, uuid, value):
    expected_uuid = rule['uuid'].lower()
    if uuid is None:
        if not rule.get('allow_unmapped', False):
            return False
    elif _gatt_uuid16(uuid) != expected_uuid:
        return False
    if rule['match'] == 'exact':
        return value.casefold() == rule['pattern'].casefold()
    if rule['match'] == 'regex':
        return re.fullmatch(rule['pattern'], value, re.IGNORECASE) is not None
    raise ValueError(f"Unsupported GATT fingerprint match type: {rule['match']}")


def lookup_GATT_value_fingerprints(bdaddr, bdaddr_random):
    """Match successful GATT reads to chip/module metadata by value and UUID."""
    rules = TME.TME_glob.gatt_value_fingerprint_rules
    if not rules:
        return []
    if bdaddr_random is None:
        values = (bdaddr,)
        where = 'v.bdaddr = %s'
    else:
        values = (bdaddr, bdaddr_random)
        where = 'v.bdaddr = %s AND v.bdaddr_random = %s'
    query = (
        'SELECT c.UUID, v.char_value_handle, v.byte_values '
        'FROM GATT_characteristics_values AS v '
        'LEFT JOIN GATT_characteristics AS c '
        'ON c.bdaddr = v.bdaddr AND c.bdaddr_random = v.bdaddr_random '
        'AND c.char_value_handle = v.char_value_handle '
        f'WHERE {where} AND v.operation = 11'
    )
    matches = []
    seen = set()
    for uuid, handle, raw in execute_query(query, values):
        if not raw:
            continue
        try:
            value = raw.decode('utf-8').rstrip('\x00').strip()
        except UnicodeDecodeError:
            continue
        for rule in rules:
            if _gatt_value_matches_rule(rule, uuid, value):
                key = (rule['id'], uuid, handle, value)
                if key not in seen:
                    seen.add(key)
                    matches.append((rule, uuid, value))
    return matches


def _gatt_fingerprint_print_text(rule, uuid, value, field):
    source = f"GATT 0x{_gatt_uuid16(uuid)}" if uuid else 'unmapped GATT value'
    return (
        f"{i2}{string_yellow_bright(rule[field])} "
        f"[{rule['confidence']}] -> From {source} = {value!r}"
    )

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
def lookup_metadata_by_GATTprint(bdaddr, bdaddr_random, metadata_input_type, metadata_output_type):
    # First see if we have GATT data for this device
    we_have_GATT = False

    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        services_query = "SELECT UUID FROM GATT_services WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        services_query = "SELECT UUID FROM GATT_services WHERE bdaddr = %s"
    services_result = execute_query(services_query, values)
    if(len(services_result) > 0): we_have_GATT = True

    if(bdaddr_random is not None):
        chars_query = "SELECT UUID,char_value_handle FROM GATT_characteristics WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        chars_query = "SELECT UUID,char_value_handle FROM GATT_characteristics WHERE bdaddr = %s"
    chars_result = execute_query(chars_query, values)
    if(len(chars_result) > 0): we_have_GATT = True

    if(bdaddr_random is not None):
        le_adv_query = "SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        le_adv_query = "SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr = %s"
    le_adv_result = execute_query(le_adv_query, values)
    if(len(le_adv_result) > 0): we_have_GATT = True

    if(bdaddr_random is not None):
        le_adv2_query = "SELECT str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        le_adv2_query = "SELECT str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr = %s"
    le_adv2_result = execute_query(le_adv2_query, values)
    if(len(le_adv2_result) > 0): we_have_GATT = True

    values = (bdaddr,)
    eir_adv_query = "SELECT str_UUID128s FROM EIR_bdaddr_to_UUID128s WHERE bdaddr = %s"
    eir_adv_result = execute_query(eir_adv_query, values)
    if(len(eir_adv_result) > 0): we_have_GATT = True

    str_list = []
    manufacturer_name_match = 0 # Only match this one time

    if(we_have_GATT):
        # If we have GATT data, consult with the metadata_v2 data, and see if any entries have Chip Maker data
        # and if so, try that nameprint against the name(s) for this device
        for heading, metadata in TME.TME_glob.metadata_v2.items():
            # Confirm that this entry even has what we're looking for
            if('Vendor_Specific_UUIDs' in metadata.keys() and metadata_input_type in metadata.keys() and metadata_output_type in metadata.keys()):

                # Iterate through every UUID128 from the metadata
                for UUID128_metadata in metadata['Vendor_Specific_UUIDs'].keys():
                    UUID128_metadata_ = UUID128_metadata.replace('-','').lower()

                    if(len(services_result) > 0):
                        # Iterate through every UUID128 from the GATT_services database query
                        for (UUID128_db,) in services_result:
                            # Remove dashes and make lowercase
                            UUID128_db_ = UUID128_db.replace('-','').lower()
                            if(UUID128_db_ == UUID128_metadata_):
                                if(metadata_output_type == '2thprint_Chip_Maker' or metadata_output_type == '2thprint_Chip'):
                                    s = string_yellow_bright(metadata[metadata_output_type])
                                else:
                                    s = metadata[metadata_output_type]
                                str_list.append(f"{i2}{s} -> From GATTprint match on {UUID128_metadata} = \"{metadata['Vendor_Specific_UUIDs'][UUID128_metadata]}\"{" (DB:GATT_services)" if TME.TME_glob.verbose_print else ""}")

                    if(len(chars_result) > 0):
                        # Iterate through every UUID128 from the GATT_Characteristics database query
                        for (UUID128_db,char_value_handle) in chars_result:
                            # Remove dashes and make lowercase
                            UUID128_db_ = UUID128_db.replace('-','').lower()
                            if(UUID128_db_ == UUID128_metadata_):
                                if(metadata_output_type == '2thprint_Chip_Maker' or metadata_output_type == '2thprint_Chip'):
                                    s = string_yellow_bright(metadata[metadata_output_type])
                                else:
                                    s = metadata[metadata_output_type]
                                str_list.append(f"{i2}{s} -> From GATTprint match on {UUID128_metadata} = \"{metadata['Vendor_Specific_UUIDs'][UUID128_metadata]}\"{" (DB:GATT_characteristics)" if TME.TME_glob.verbose_print else ""}")

                            # While we're here, check if this device has a "Manufacturer Name String" characteristic
                            if(UUID128_db_ == "00002a2900001000800000805f9b34fb" and manufacturer_name_match == 0):
                                # If so, go lookup the actual data behind it, so we can see if the "Manufacturer Name" is a ChipMaker
                                if(bdaddr_random is not None):
                                    values = (bdaddr_random, bdaddr, f"char_value_handle:03")
                                    char_value_query = "SELECT byte_values FROM GATT_characteristics_values WHERE bdaddr_random = %s AND bdaddr = %s and char_value_handle = %s"
                                else:
                                    values = (bdaddr, f"char_value_handle:03")
                                    char_value_query = "SELECT byte_values FROM GATT_characteristics_values WHERE bdaddr = %s and char_value_handle = %s"
                                char_value_result = execute_query(char_value_query, values)
                                if(len(char_value_result) > 0):
                                    for (byte_values,) in char_value_result:
                                        tmpstr = byte_values.decode('utf-8', 'ignore')
                                        #qprint(f"byte_values: {tmpstr}")
                                        match = match_str_to_ChipMaker(tmpstr)
                                        if(match != ""):
                                            manufacturer_name_match = 1
                                            if(metadata_output_type == '2thprint_Chip_Maker' or metadata_output_type == '2thprint_Chip'):
                                                s = string_yellow_bright(tmpstr)
                                            else:
                                                s = tmpstr
                                            str_list.append(f"{i2}{s} -> From GATT \"Manufacturer Name String\" regex-based match with {match}{" (DB:GATT_characteristics & DB:GATT_characteristics_values)" if TME.TME_glob.verbose_print else ""}")

                    if(len(le_adv_result) > 0):
                        # Iterate through every UUID128 from the LE_bdaddr_to_UUID128s_list database query
                        # NOTE! : While I don't believe it currently is, treat every str_UUID128s entry as if it could be a comma-deliminated list of UUID128s w/o dashes (because that's how some other wireshark output for UUID128s is)
                        for (str_UUID128s,) in le_adv_result:
                            UUID128_list = str_UUID128s.split(",")
                            if(len(UUID128_list) != 0):
                                for UUID128_db in UUID128_list:
                                    # Remove dashes and make lowercase
                                    UUID128_db_ = UUID128_db.replace('-','').lower()
                                    if(UUID128_db_ == UUID128_metadata_):
                                        if(metadata_output_type == '2thprint_Chip_Maker' or metadata_output_type == '2thprint_Chip'):
                                            s = string_yellow_bright(metadata[metadata_output_type])
                                        else:
                                            s = metadata[metadata_output_type]
                                        str_list.append(f"{i2}{s} -> From GATTprint match on {UUID128_metadata} = \"{metadata['Vendor_Specific_UUIDs'][UUID128_metadata]}\"{" (DB:LE_bdaddr_to_UUID128s_list)" if TME.TME_glob.verbose_print else ""}")

                    if(len(le_adv2_result) > 0):
                        # Iterate through every UUID128 from the LE_bdaddr_to_UUID128s_list database query
                        # NOTE! : While I don't believe it currently is, treat every str_UUID128s entry as if it could be a comma-deliminated list of UUID128s w/o dashes (because that's how some other wireshark output for UUID128s is)
                        for (str_UUID128s,) in le_adv2_result:
                            UUID128_list = str_UUID128s.split(",")
                            if(len(UUID128_list) != 0):
                                for UUID128_db in UUID128_list:
                                    # Remove dashes and make lowercase
                                    UUID128_db_ = UUID128_db.replace('-','').lower()
                                    if(UUID128_db_ == UUID128_metadata_):
                                        if(metadata_output_type == '2thprint_Chip_Maker' or metadata_output_type == '2thprint_Chip'):
                                            s = string_yellow_bright(metadata[metadata_output_type])
                                        else:
                                            s = metadata[metadata_output_type]
                                        str_list.append(f"{i2}{s} -> From GATTprint match on {UUID128_metadata} = \"{metadata['Vendor_Specific_UUIDs'][UUID128_metadata]}\"{" (DB:LE_bdaddr_to_UUID128_service_solicit)" if TME.TME_glob.verbose_print else ""}")

                    if(len(eir_adv_result) > 0):
                        # Iterate through every UUID128 from the LE_bdaddr_to_UUID128s_list database query
                        # NOTE! : Every str_UUID128s entry is a comma-deliminated list of UUID128s w/o dashes (because that's how some other wireshark output is)
                        for (str_UUID128s,) in eir_adv_result:
                            UUID128_list = str_UUID128s.split(",")
                            if(len(UUID128_list) != 0):
                                for UUID128_db in UUID128_list:
                                    # Remove dashes and make lowercase
                                    UUID128_db_ = UUID128_db.replace('-','').lower()
                                    if(UUID128_db_ == UUID128_metadata_):
                                        if(metadata_output_type == '2thprint_Chip_Maker' or metadata_output_type == '2thprint_Chip'):
                                            s = string_yellow_bright(metadata[metadata_output_type])
                                        else:
                                            s = metadata[metadata_output_type]
                                        str_list.append(f"{i2}{s} -> From GATTprint match on {UUID128_metadata} = \"{metadata['Vendor_Specific_UUIDs'][UUID128_metadata]}\"{" (DB:EIR_bdaddr_to_UUID128s)" if TME.TME_glob.verbose_print else ""}")

    # Else return an empty list to indicate we have no name or no match
    return str_list


########################################
# ChipMaker Info
########################################

ChipMaker_OUI_hash = {}

def create_ChipMaker_OUI_hash():
    for company in ChipMaker_names_and_BT_CIDs.keys():
        values = (company,)
        oui_query = "SELECT bdaddr, company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP %s"
        oui_result = execute_query(oui_query, values)
        for (oui,company_name) in oui_result:
            ChipMaker_OUI_hash[oui.lower()] = company_name # I'm using the IEEE name instead of the company regex since it will generally be longer and more verbose, since I cut down some regexes to match both IEEE OUIs and BT CIDs

    #qprint(ChipMaker_OUI_hash)


def print_ChipPrint_header_if_needed():
    global g_printed_ChipPrint_header
    if(not TME.TME_glob.g_printed_ChipPrint_header):
        qprint(f"{i1}ChipPrint:")
        TME.TME_glob.g_printed_ChipPrint_header = True


def print_ChipMakerPrint_header_if_needed():
    global g_printed_ChipMakerPrint_header
    if(not TME.TME_glob.g_printed_ChipMakerPrint_header):
        qprint(f"{i1}ChipMakerPrint:")
        TME.TME_glob.g_printed_ChipMakerPrint_header = True


def print_ModulePrint_header_if_needed():
    if not TME.TME_glob.g_printed_ModulePrint_header:
        qprint(f"{i1}ModulePrint:")
        TME.TME_glob.g_printed_ModulePrint_header = True


def print_ModuleMakerPrint_header_if_needed():
    if not TME.TME_glob.g_printed_ModuleMakerPrint_header:
        qprint(f"{i1}ModuleMakerPrint:")
        TME.TME_glob.g_printed_ModuleMakerPrint_header = True


def print_ChipMakerPrint_helper_UUID16(indent, UUID16_result, tablename):
    results_found = False
    if(len(UUID16_result) != 0):
        for(str_UUID16s,) in UUID16_result:
            UUID16_list = str_UUID16s.split(",")
            if(len(UUID16_list) != 0):
                for UUID16_db in UUID16_list:
                    # Remove dashes and make lowercase
                    UUID16_db_ = UUID16_db.lower()
                    # Check if this UUID16 is a known chip-maker UUID
                    for heading, metadata in TME.TME_glob.metadata_v2.items():
                        if('Vendor_Specific_UUIDs' in metadata.keys() and '2thprint_Chip_Maker' in metadata.keys()):
                            for UUID in metadata['Vendor_Specific_UUIDs'].keys():
                                if(UUID16_db_ == UUID.lower()):
                                    print_ChipMakerPrint_header_if_needed()
                                    chip_maker = string_yellow_bright(metadata['2thprint_Chip_Maker'])
                                    qprint(f"{indent}{chip_maker} -> From GATT Vendor Specific UUID16 match with {UUID16_db}{f" (DB:{tablename})" if TME.TME_glob.verbose_print else ""}")
                                    results_found = True

    return results_found

# This function consults with the various sources of information which we might have that suggest a possible ChipMaker, and prints them all
# If there are conflicting ChipMaker possibilities, it's up to the person to look at the results and determine which source(s) of data they find the most credible
def print_ChipMakerPrint(bdaddr, bdaddr_random, gatt_value_matches=None):
    bdaddr = bdaddr.strip().lower()
    time_profile = False

    no_results_found = True

    if(time_profile): qprint(f"Start = {time.time()}")
    #=====================#
    # LL_VERSION_IND data #
    #=====================#

    # So far experiments have indicated that LL_VERSION_IND company ID is the Chip Maker.
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        ble_version_query = "SELECT bdaddr_random, ll_version, device_BT_CID, ll_sub_version FROM LL_VERSION_IND WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        ble_version_query = "SELECT bdaddr_random, ll_version, device_BT_CID, ll_sub_version FROM LL_VERSION_IND WHERE bdaddr = %s"
    ble_version_result = execute_query(ble_version_query, values)
    if(len(ble_version_result) != 0):
        no_results_found = False
        # There could be multiple results if we got some corrupt data, which resulted in inserting N distinct entries into the db, or if we had old and new Wireshark parsing
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (bdaddr_random, ll_version, device_BT_CID, ll_sub_version) in ble_version_result:
            print_ChipMakerPrint_header_if_needed()
            qprint(f"{i2}{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From LL_VERSION_IND: Company ID{" (DB:LL_VERSION_IND)" if TME.TME_glob.verbose_print else ""}")
            # FIXME: For now all the data in the database is P2C, but we need to update the DB to capture this in the future
            data = ff_LL_VERSION_IND(type_BTIDES_direction_P2C, ll_version, device_BT_CID, ll_sub_version)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    if(time_profile): qprint(f"LMP_VERSION_REQ = {time.time()}")
    #==========================#
    # LMP_VERSION_REQ/RES data #
    #==========================#

    values = (bdaddr,)
    # So far experiments have indicated that LMP_VERSION_REQ/RES company ID is the Chip Maker.
    btc_version_query = "SELECT lmp_version, device_BT_CID, lmp_sub_version FROM LMP_VERSION_RES WHERE bdaddr = %s"
    btc_version_result = execute_query(btc_version_query, values)
    if(len(btc_version_result) != 0):
        no_results_found = False
        # There could be multiple results if we got some corrupt data, which resulted in inserting N distinct entries into the db, or if we had old and new Wireshark parsing
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (lmp_version, device_BT_CID, lmp_sub_version) in btc_version_result:
            print_ChipMakerPrint_header_if_needed()
            qprint(f"{i2}{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From LMP_VERSION_REQ/RES: Company ID{" (DB:LMP_VERSION_RES)" if TME.TME_glob.verbose_print else ""}")
            BTIDES_export_LMP_VERSION_RES(bdaddr, lmp_version, device_BT_CID, lmp_sub_version)

    if(time_profile): qprint(f"NamePrint = {time.time()}")
    #================#
    # NamePrint data #
    #================#
    s = lookup_metadata_by_nameprint(bdaddr, bdaddr_random, '2thprint_Chip_Maker')
    if(s != ""):
        print_ChipMakerPrint_header_if_needed()
        qprint(s)
        no_results_found = False

    if(time_profile): qprint(f"OUI = {time.time()}")
    #=============================#
    # GATT known chip-maker UUIDs #
    #=============================#
    str_list = lookup_metadata_by_GATTprint(bdaddr, bdaddr_random, '2thprint_ChipMaker_GATTprint', '2thprint_Chip_Maker')
    if(len(str_list) > 0):
        no_results_found = False
        for s in str_list:
            print_ChipMakerPrint_header_if_needed()
            qprint(s)

    if gatt_value_matches is None:
        gatt_value_matches = lookup_GATT_value_fingerprints(bdaddr, bdaddr_random)
    for rule, uuid, value in gatt_value_matches:
        if 'chip_maker' in rule:
            print_ChipMakerPrint_header_if_needed()
            qprint(_gatt_fingerprint_print_text(rule, uuid, value, 'chip_maker'))
            no_results_found = False

    #===============#
    # IEEE OUI data #
    #===============#
    random = False

    oui = bdaddr[0:8]
    is_classic = is_bdaddr_classic(bdaddr)
    if(is_classic):
        if(oui in ChipMaker_OUI_hash.keys()):
            print_ChipMakerPrint_header_if_needed()
            qprint(f"{i2}{string_yellow_bright(ChipMaker_OUI_hash[oui])} -> From IEEE OUI matched with BT Classic address")
            no_results_found = False
    else:
        random = is_bdaddr_le_and_random(bdaddr)
        if(not random):
            if(oui in ChipMaker_OUI_hash.keys()):
                print_ChipMakerPrint_header_if_needed()
                qprint(f"{i2}{string_yellow_bright(ChipMaker_OUI_hash[oui])} -> From IEEE OUI matched with BLE Public address")
                no_results_found = False

    if(time_profile): qprint(f"GATT = {time.time()}")

    #============================================#
    # Known chip-maker UUID16s in advertisements #
    #============================================#
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_UUID16_query = "SELECT UUID16_hex_str FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = %s AND  bdaddr = %s"
    else:
        values = (bdaddr,)
        le_UUID16_query = "SELECT UUID16_hex_str FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr = %s"
    LE_bdaddr_to_UUID16_service_data_result = execute_query(le_UUID16_query, values)

    if(bdaddr_random is not None):
        le_UUID16_query = "SELECT str_UUID16s FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        le_UUID16_query = "SELECT str_UUID16s FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr = %s"
    LE_bdaddr_to_UUID16s_list_result = execute_query(le_UUID16_query, values)

    values = (bdaddr,)
    eir_UUID16_query = "SELECT str_UUID16s FROM EIR_bdaddr_to_UUID16s WHERE bdaddr = %s"
    EIR_bdaddr_to_UUID16s_result = execute_query(eir_UUID16_query, values)

    if(print_ChipMakerPrint_helper_UUID16(f"{i2}", LE_bdaddr_to_UUID16_service_data_result, "LE_bdaddr_to_UUID16_service_data")):
        no_results_found = False
    if(print_ChipMakerPrint_helper_UUID16(f"{i2}", LE_bdaddr_to_UUID16s_list_result, "LE_bdaddr_to_UUID16s_list")):
        no_results_found = False
    if(print_ChipMakerPrint_helper_UUID16(f"{i2}", EIR_bdaddr_to_UUID16s_result, "EIR_bdaddr_to_UUID16s")):
        no_results_found = False

    if(time_profile): qprint(f"MSD BTC = {time.time()}")

    #========================================#
    # Manufacturer-Specific Data (MSD) - BTC #
    #========================================#
    # In general more companies tend to leave this uninitialized for BTC, than for BLE. So a BTC hit is more likely to be accurate than BLE
    MSD_query = "SELECT device_BT_CID,manufacturer_specific_data FROM EIR_bdaddr_to_MSD WHERE bdaddr = %s"
    MSD_result = execute_query(MSD_query, values)

    if(len(MSD_result) != 0):
        # There could be multiple results if there are multiple distinct data blobs seen
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (device_BT_CID,manufacturer_specific_data) in MSD_result:

            # Check if this CID corresponds to a ChipMaker
            for name in ChipMaker_names_and_BT_CIDs.keys():
                BT_CID_list = ChipMaker_names_and_BT_CIDs[name]
                if(device_BT_CID in BT_CID_list):
                    print_ChipMakerPrint_header_if_needed()
                    qprint(f"{i2}{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From BT Classic Extended Inquiry Response Manufacturer-Specific Data Company ID{" (DB:EIR_bdaddr_to_MSD)" if TME.TME_glob.verbose_print else ""}")
                    no_results_found = False

    if(time_profile): qprint(f"MSD BLE = {time.time()}")
    #========================================#
    # Manufacturer-Specific Data (MSD) - BLE #
    #========================================#
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        MSD_query = "SELECT bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        MSD_query = "SELECT bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s"
    MSD_result = execute_query(MSD_query, values)

    if(len(MSD_result) != 0):
        # There could be multiple results if there are multiple distinct data blobs seen or multiple event types
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data) in MSD_result:
            # Apple iBeacons are too common in other devices, and Find My network uses the Apple ID too
            # So we're excluding that from being a valid consideration for Chip Maker
            if(device_BT_CID == 0x004C or device_BT_CID == 0x4C00):
                continue

            # Check if this CID corresponds to a ChipMaker
            for name in ChipMaker_names_and_BT_CIDs.keys():
                BT_CID_list = ChipMaker_names_and_BT_CIDs[name]
                if(device_BT_CID in BT_CID_list):
                    no_results_found = False
                    print_ChipMakerPrint_header_if_needed()
                    qprint(f"{i2}{BT_CID_to_company_name(device_BT_CID)} ({device_BT_CID}) -> From BT Low Energy Manufacturer-Specific Data Company ID{" (DB:LE_bdaddr_to_MSD)" if TME.TME_glob.verbose_print else ""} {get_le_event_type_string(le_evt_type)})")
                    # if(device_BT_CID == 76 and manufacturer_specific_data[0:4] == "0215"):
                    #     qprint(f"{i3}CAVEAT: This company ID was seen as part of an 'iBeacon', which is a standardized beacon format used by many companies other than Apple. So this is a low-signal indication of ChipMaker")

    if(time_profile): qprint(f"End = {time.time()}")
    if(no_results_found):
        vprint(f"{i1}ChipMakerPrint:")
        vprint(f"{i2}No ChipMakerPrint(s) found.")

    # Final padding print of print_ChipMakerPrint()
    if(TME.TME_glob.g_printed_ChipMakerPrint_header):
        qprint("")
    else:
        vprint("")

########################################
# Chip Info
########################################

def chip_by_sub_version(sub_version, device_BT_CID):
    """Compatibility wrapper backed by the machine-readable JSON metadata."""
    chip_text, _match_quality = chipprint_by_sub_version(
        sub_version, device_BT_CID
    )
    return chip_text


def chipprint_by_sub_version(sub_version, device_BT_CID):
    """Return ChipPrint text and quality for a company/sub-version pair."""
    for metadata in (
        TME.TME_glob.ll_version_ind_metadata,
        TME.TME_glob.lmp_version_metadata,
    ):
        match = lookup_company_subversion_metadata(
            metadata, device_BT_CID, sub_version
        )
        if match is not None:
            chips = match.get('chips', [])
            if match.get('cross_chip_collision') and chips:
                return (
                    f"Possible chip(s): {', '.join(chips)}",
                    match.get('match_quality', ''),
                )
            return metadata_chip_display_name(match), ''
    return '', ''


def chipprint_by_LL_VERSION(ll_version, sub_version, device_BT_CID):
    """Return ChipPrint text and evidence quality for a complete LL tuple."""
    match = lookup_LL_VERSION_IND_metadata(
        ll_version, device_BT_CID, sub_version
    )
    if match is None:
        return '', ''

    # Preserve the established Broadcom/Realtek ChipPrint wording.
    if match.get('display_name'):
        return metadata_chip_display_name(match), ''

    chips = match.get('chips', [])
    if not chips:
        return '', ''
    return (
        f"Possible chip(s): {', '.join(chips)}",
        match.get('match_quality', ''),
    )


def chipprint_by_LMP_VERSION(lmp_version, sub_version, device_BT_CID):
    """Return ChipPrint text and evidence quality for a complete LMP tuple."""
    match = lookup_LMP_VERSION_metadata(
        lmp_version, device_BT_CID, sub_version
    )
    if match is None:
        return '', ''
    if match.get('display_name'):
        return metadata_chip_display_name(match), ''
    chips = match.get('chips', [])
    if not chips:
        return '', ''
    return (
        f"Possible chip(s): {', '.join(chips)}",
        match.get('match_quality', ''),
    )

# This function consults with the various sources of information which we might have that suggest a possible Chip, and prints them all
# If there are conflicting Chip possibilities, it's up to the person to look at the results and determine which source(s) of data they find the most credible
def print_ChipPrint(bdaddr, bdaddr_random, gatt_value_matches=None):
    global g_printed_ChipPrint_header
    bdaddr = bdaddr.strip().lower()

    no_results_found = True

    #=====================#
    # LL_VERSION_IND data #
    #=====================#

    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        version_query = "SELECT ll_version, ll_sub_version, device_BT_CID FROM LL_VERSION_IND WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        version_query = "SELECT ll_version, ll_sub_version, device_BT_CID FROM LL_VERSION_IND WHERE bdaddr = %s"
    version_result = execute_query(version_query, values)

    if(len(version_result) != 0):
        no_results_found = False
        # The only time there should be multiple results is if we got some corrupt data, which resulted in inserting N distinct entries into the db
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (ll_version, ll_sub_version, device_BT_CID) in version_result:
            chip_name, match_quality = chipprint_by_LL_VERSION(
                ll_version, ll_sub_version, device_BT_CID
            )
            if(chip_name != ""):
                print_ChipPrint_header_if_needed()
                evidence = "LL_VERSION_IND info"
                if match_quality:
                    evidence += f" ({match_quality})"
                qprint(f"{i2}{string_yellow_bright(chip_name)} -> From {evidence}{" (DB:LL_VERSION_IND)" if TME.TME_glob.verbose_print else ""}")

    #==========================#
    # LMP_VERSION_REQ/RES data #
    #==========================#

    # So far experiments have indicated that LMP_VERSION_REQ/RES company ID is the Chip Maker.

    values = (bdaddr,)
    version_query = "SELECT lmp_version, lmp_sub_version, device_BT_CID FROM LMP_VERSION_RES WHERE bdaddr = %s"
    version_result = execute_query(version_query, values)

    if(len(version_result) != 0):
        no_results_found = False
        # The only time there should be multiple results is if we got some corrupt data, which resulted in inserting N distinct entries into the db
        # Print out all possible entries, just so that if there are other hints from other datatypes, the erroneous ones can be ignored
        for (lmp_version, lmp_sub_version, device_BT_CID) in version_result:
            chip_name, match_quality = chipprint_by_LMP_VERSION(
                lmp_version, lmp_sub_version, device_BT_CID
            )
            if(chip_name != ""):
                print_ChipPrint_header_if_needed()
                evidence = "LMP_VERSION_REQ/RES info"
                if match_quality:
                    evidence += f" ({match_quality})"
                qprint(f"{i2}{string_yellow_bright(chip_name)} -> From {evidence}{" (DB:LMP_VERSION_RES)" if TME.TME_glob.verbose_print else ""}")

    #================#
    # NamePrint data #
    #================#
    str = lookup_metadata_by_nameprint(bdaddr, bdaddr_random, '2thprint_Chip')
    if(str != ""):
        qprint(string_yellow_bright(str))
        no_results_found = False

    #======================#
    # GATT Model Name data #
    #======================#
    str = lookup_ChipPrint_by_GATT(bdaddr, bdaddr_random)
    if(str != ""):
        print_ChipPrint_header_if_needed()
        qprint(string_yellow_bright(str))
        no_results_found = False

    if gatt_value_matches is None:
        gatt_value_matches = lookup_GATT_value_fingerprints(bdaddr, bdaddr_random)
    for rule, uuid, value in gatt_value_matches:
        if 'chip' in rule and (not str or rule['chip'] not in str):
            print_ChipPrint_header_if_needed()
            qprint(_gatt_fingerprint_print_text(rule, uuid, value, 'chip'))
            no_results_found = False

    if(no_results_found):
        vprint(f"{i1}ChipPrint:")
        vprint(f"{i2}No ChipPrint(s) found.")

    if(not TME.TME_glob.g_printed_ChipPrint_header):
        vprint("")
    else:
        qprint("")

########################################
# ModuleMaker Info
########################################

def print_ModuleMakerPrint(bdaddr, bdaddr_random, gatt_value_matches=None):
    name_match = lookup_metadata_by_nameprint(bdaddr, bdaddr_random, '2thprint_Module_Maker')
    if name_match:
        qprint(string_yellow_bright(name_match))
    if gatt_value_matches is None:
        gatt_value_matches = lookup_GATT_value_fingerprints(bdaddr, bdaddr_random)
    for rule, uuid, value in gatt_value_matches:
        if 'module_maker' in rule:
            print_ModuleMakerPrint_header_if_needed()
            qprint(_gatt_fingerprint_print_text(rule, uuid, value, 'module_maker'))
    if TME.TME_glob.g_printed_ModuleMakerPrint_header:
        qprint('')
    else:
        vprint(f"{i1}ModuleMakerPrint:")
        vprint(f"{i2}No ModuleMakerPrint(s) found.")

########################################
# Module Info
########################################

def print_ModulePrint(bdaddr, bdaddr_random, gatt_value_matches=None):
    name_match = lookup_metadata_by_nameprint(bdaddr, bdaddr_random, '2thprint_Module')
    if name_match:
        qprint(string_yellow_bright(name_match))
    if gatt_value_matches is None:
        gatt_value_matches = lookup_GATT_value_fingerprints(bdaddr, bdaddr_random)
    for rule, uuid, value in gatt_value_matches:
        if 'module' in rule:
            print_ModulePrint_header_if_needed()
            qprint(_gatt_fingerprint_print_text(rule, uuid, value, 'module'))
    if TME.TME_glob.g_printed_ModulePrint_header:
        qprint('')
    else:
        vprint(f"{i1}ModulePrint:")
        vprint(f"{i2}No ModulePrint(s) found.")


def _has_chipmaker_evidence_for_sdk_rule(rule, bdaddr, bdaddr_random,
                                         gatt_value_matches, ll_tuples):
    """Require a separate ChipMakerPrint source for numeric SDK coincidences."""
    maker = rule.get('requires_chip_maker')
    if not maker:
        return True
    if any(company_id == rule['chip_maker_cid'] for _, company_id, _ in ll_tuples):
        return True
    if any(
        other_rule is not rule and other_rule.get('chip_maker') == maker
        for other_rule, _, _ in gatt_value_matches
    ):
        return True
    # ChipMakerPrint uses the OUI only for public or Classic addresses.
    has_public_oui = bdaddr_random == 0 or (
        bdaddr_random is None and (
            is_bdaddr_classic(bdaddr) or not is_bdaddr_le_and_random(bdaddr)
        )
    )
    if has_public_oui:
        oui_maker = ChipMaker_OUI_hash.get(bdaddr.lower()[:8])
        if oui_maker and oui_maker.casefold().startswith(maker.casefold()):
            return True
    return False


def print_SDKPrint(bdaddr, bdaddr_random, gatt_value_matches=None):
    """Show GATT SDK labels, guarded version hints, and LL SDK releases."""
    if gatt_value_matches is None:
        gatt_value_matches = lookup_GATT_value_fingerprints(bdaddr, bdaddr_random)

    if bdaddr_random is None:
        query = 'SELECT ll_version, device_BT_CID, ll_sub_version FROM LL_VERSION_IND WHERE bdaddr = %s'
        values = (bdaddr,)
    else:
        query = (
            'SELECT ll_version, device_BT_CID, ll_sub_version FROM LL_VERSION_IND '
            'WHERE bdaddr = %s AND bdaddr_random = %s'
        )
        values = (bdaddr, bdaddr_random)
    ll_tuples = execute_query(query, values)
    lines = []
    for rule, uuid, value in gatt_value_matches:
        if 'sdk' not in rule or not _has_chipmaker_evidence_for_sdk_rule(
            rule, bdaddr, bdaddr_random, gatt_value_matches, ll_tuples
        ):
            continue
        source = f"GATT 0x{_gatt_uuid16(uuid)}" if uuid else 'unmapped GATT value'
        if rule.get('requires_chip_maker'):
            lines.append(
                f"{i2}{string_yellow_bright(rule['sdk'])} [low; possible only] "
                f"-> GATT firmware version {value!r} matches an SDK release number "
                f"({source}); separate {rule['requires_chip_maker']} ChipMakerPrint. "
                "Firmware may use an unrelated version scheme."
            )
        else:
            lines.append(
                f"{i2}{string_yellow_bright(rule['sdk'])} [{rule['confidence']}] "
                f"-> Observed build string {value!r} ({source})"
            )

    seen_tuples = set()
    for ll_version, company_id, subversion in ll_tuples:
        ll_tuple = (ll_version, company_id, subversion)
        if ll_tuple in seen_tuples:
            continue
        seen_tuples.add(ll_tuple)
        identification = lookup_LL_VERSION_IND_metadata(*ll_tuple)
        if not identification or not identification.get('sdk_versions'):
            continue
        sdk_versions = [
            version for version in identification['sdk_versions']
            if version.casefold() != 'exact sdk release unknown'
        ]
        if not sdk_versions:
            continue
        tuple_label = f"{ll_version:02X}:{company_id:04X}:{subversion:04X}"
        label = (
            'SDK generation hint'
            if identification['match_quality'].startswith('vendor/version inference')
            or all('generation' in version.casefold() for version in sdk_versions)
            else 'Compatible SDK release(s)'
        )
        lines.append(
            f"{i2}{label}: {', '.join(sdk_versions)} "
            f"-> From LL_VERSION_IND {tuple_label} "
            f"({identification['match_quality']})"
        )

    if lines:
        if not TME.TME_glob.g_printed_SDKPrint_header:
            qprint(f"{i1}SDKPrint:")
            TME.TME_glob.g_printed_SDKPrint_header = True
        for line in lines:
            qprint(line)
        qprint('')
    else:
        vprint(f"{i1}SDKPrint:")
        vprint(f"{i2}No SDKPrint(s) found.")

########################################
# DeviceMaker Info
########################################

########################################
# DeviceModel Info
########################################

def print_DeviceModel(bdaddr):
    bdaddr = bdaddr.strip().lower()

    no_results_found = True

    qprint(f"{i1}2thprint_DeviceModelPrint:")
