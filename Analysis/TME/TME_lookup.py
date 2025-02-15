########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

import re
import TME.TME_glob
from TME.TME_helpers import *

########################################
# Lookup helpers
########################################

# Returns 0 if there is no LL_VERSION_IND info for this BDADDR, else returns 1
def device_has_LL_VERSION_IND_info(bdaddr):
    values = (bdaddr,)
    version_query = "SELECT device_BT_CID FROM LL_VERSION_IND WHERE bdaddr = %s"
    version_result = execute_query(version_query, values)
    if(len(version_result) != 0):
        return 1
    else:
        return 0

# Returns 0 if there is no LMP_VERSION_RES info for this BDADDR, else returns 1
def device_has_LMP_VERSION_RES_info(bdaddr):
    values = (bdaddr,)
    version_query = "SELECT device_BT_CID FROM LMP_VERSION_RES WHERE bdaddr = %s"
    version_result = execute_query(version_query, values)
    if(len(version_result) != 0):
        return 1
    else:
        return 0

def get_bdaddrs_by_name_regex(nameregex):
    qprint(nameregex)
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (nameregex,)
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_name WHERE CONVERT(UNHEX(name_hex_str) USING utf8) REGEXP %s"
    eir_result = execute_query(eir_query, values)
    bdaddrs += eir_result
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_name_regex: {len(eir_result)} results found in EIR_bdaddr_to_name")
    qprint(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query for HCI_bdaddr_to_name table
    hci_query = "SELECT bdaddr FROM HCI_bdaddr_to_name WHERE CONVERT(UNHEX(name_hex_str) USING utf8) REGEXP %s"
    hci_result = execute_query(hci_query, values)
    for (bdaddr,) in hci_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_name_regex: {len(hci_result)} results found in HCI_bdaddr_to_name")
    qprint(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query for LE_bdaddr_to_name table
    le_query = "SELECT bdaddr FROM LE_bdaddr_to_name WHERE CONVERT(UNHEX(name_hex_str) USING utf8) REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_name_regex: {len(le_result)} results found in LE_bdaddr_to_name")
    qprint(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query GATT Characteristic values for Device Name (0x2a00) entries, and then checking regex in python instead of MySQL, because the byte values may not be directly translatable to UTF-8 within MySQL
    chars_query = "SELECT cv.bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle AND cv.bdaddr = c.bdaddr WHERE c.UUID = '2a00';"
    chars_result = execute_query(chars_query, ())
    if(len(chars_result) > 0):
        for (bdaddr, byte_values) in chars_result:
            tmpstr = byte_values.decode('utf-8', 'ignore')
            #qprint(f"byte_values: {tmpstr}")
            pattern = re.compile(nameregex)
            if re.search(pattern, tmpstr):
                qprint(f"{nameregex} matched bdaddr = {bdaddr}")
                bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_name_regex: {len(chars_result)} results found in GATT_characteristics_values and GATT_characteristics")
    qprint(f"get_bdaddrs_by_name_regex: bdaddr_hash (len = {len(bdaddr_hash)}) = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_bdaddr_regex(bdaddrregex):
    qprint(bdaddrregex)
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (bdaddrregex,)
    bdaddr_query = (
        "SELECT DISTINCT t.bdaddr "
        "FROM ( "
        "    SELECT %s AS bdaddr_regex "
        ") AS regex "
        "CROSS JOIN ( "
        "    SELECT bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_name WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_other_le_bdaddr WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_public_target_bdaddr WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_tx_power WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_URI WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_3d_info WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = 0 "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_DevID "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_flags "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_MSD "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_name "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_PSRM "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_CoD "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_tx_power "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_URI "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_3d_info "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_UUID128s "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_UUID16s "
        "    UNION ALL "
        "    SELECT bdaddr FROM EIR_bdaddr_to_UUID32s "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LL_FEATUREs "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LL_LENGTHs "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LL_PHYs "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LL_PINGs "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LL_UNKNOWN_RSP "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LL_VERSION_IND "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LMP_FEATURES_RES "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LMP_NAME_RES "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM LMP_VERSION_RES "
        "    UNION ALL "
        "    SELECT CONVERT(bdaddr USING utf8) FROM GATT_services "
        ") AS t "
        "WHERE t.bdaddr REGEXP regex.bdaddr_regex;"
    )

    bdaddr_result = execute_query(bdaddr_query, values)
    for (bdaddr,) in bdaddr_result:
        bdaddr_hash[bdaddr] = 1

    qprint(f"get_bdaddrs_by_bdaddr_regex: {len(bdaddr_result)} results found across all tables")
    qprint(f"get_bdaddrs_by_bdaddr_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_company_regex(companyregex):
    global bt_CID_to_names
    global bt_member_UUID16s_to_names
    qprint(f"Your given regex was {companyregex}")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddr_prefixes = {}
    bdaddrs = []
    device_bt_cids_to_names = {}
    device_uuid16s_to_names = {}
    pattern = re.compile(companyregex)

    # For configurability if you know there's a false positive happening when swapping
    # NOTE: So far I've found it to have more benefits than drawbacks, so it's enabled by default
    try_byte_swapped_bt_cid = True

    # For debugging:
    enable_bt_cid_lookup = True
    enable_UUID16_lookup = True
    enable_IEEE_OUI_lookup = True


    if(enable_bt_cid_lookup):
        #########################################
        # MATCH REGEX TO BT COMPANY IDS (BT_CIDs)
        #########################################

        # Each company gets only one assigned number in this category
        for key, value in TME.TME_glob.bt_CID_to_names.items():
            if re.search(pattern, value):
                qprint(f"{companyregex} matched company name {value}, with ID 0x{key:04x}")
                device_bt_cids_to_names[key] = value

        qprint(f"device_bt_cids_to_names = {device_bt_cids_to_names}")

        #########################################
        # LOOKUP BDADDRS BY BT_CIDs
        #########################################

        for key in device_bt_cids_to_names.keys():

            values = (key,)
            tooth_lmp_query = "SELECT bdaddr FROM LMP_VERSION_RES WHERE device_BT_CID = %s"
            tooth_lmp_result = execute_query(tooth_lmp_query, values)
            for (bdaddr,) in tooth_lmp_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(tooth_lmp_result)} results found in LMP_VERSION_RES for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            tooth_ll_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE device_BT_CID = %s"
            tooth_ll_result = execute_query(tooth_ll_query, values)
            for (bdaddr,) in tooth_ll_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(tooth_ll_result)} results found in LL_VERSION_IND for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            le_msd_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE device_BT_CID = %s"
            le_msd_result = execute_query(le_msd_query, values)
            for (bdaddr,) in le_msd_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(le_msd_result)} results found in LE_bdaddr_to_MSD for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            # NOTE: Manufacture-specific data is the location where the BT_CID is most likely to be byte-swapped
            # NOTE: Try the byte-swapped version too if there are no results from the above

            if(try_byte_swapped_bt_cid):
                byte_swapped_key = (key & 0xFF) << 8 | (key & 0xFF00) >> 8
                values2 = (byte_swapped_key,)
                le_msd_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE device_BT_CID = %s"
                le_msd_result = execute_query(le_msd_query, values2)
                for (bdaddr,) in le_msd_result:
                    bdaddr_hash[bdaddr] = 1
                qprint(f"{len(le_msd_result)} results found in LE_bdaddr_to_MSD for byte-swapped BT_CID for key 0x{byte_swapped_key:04x}")
                #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            eir_msd_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE device_BT_CID = %s"
            eir_msd_result = execute_query(eir_msd_query, values)
            for (bdaddr,) in eir_msd_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(eir_msd_result)} results found in EIR_bdaddr_to_MSD for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            if(try_byte_swapped_bt_cid):
                byte_swapped_key = (key & 0xFF) << 8 | (key & 0xFF00) >> 8
                values2 = (byte_swapped_key,)
                eir_msd_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE device_BT_CID = %s"
                eir_msd_result = execute_query(eir_msd_query, values2)
                for (bdaddr,) in eir_msd_result:
                    bdaddr_hash[bdaddr] = 1
                qprint(f"{len(eir_msd_result)} results found in EIR_bdaddr_to_MSD for byte-swapped BT_CID for key 0x{byte_swapped_key:04x}")
                #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

    if(enable_UUID16_lookup):
        #########################################
        # MATCH REGEX TO BT COMPANY UUID16S
        #########################################

        # Each company can have multiple UUID16s assigned (e.g. Apple has 0xFEC6-FED4)
        for key, value in TME.TME_glob.bt_member_UUID16s_to_names.items():
            if re.search(pattern, value):
                qprint(f"{companyregex} matched company name {value}, with UUID16 0x{key:04x}")
                device_uuid16s_to_names[key] = value

        qprint(f"device_uuid16s_to_names = {device_uuid16s_to_names}")

        #########################################
        # LOOKUP BDADDRS BY UUID16S
        #########################################

        for key in device_uuid16s_to_names.keys():

            values = (f"0x{key:04x}",)
            eir_uuid16_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP %s"
            eir_uuid16_result = execute_query(eir_uuid16_query, values)
            for (bdaddr,) in eir_uuid16_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(eir_uuid16_result)} results found in EIR_bdaddr_to_UUID16s for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            le_uuid16_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE str_UUID16s REGEXP %s"
            le_uuid16_result = execute_query(le_uuid16_query, values)
            for (bdaddr,) in le_uuid16_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(le_uuid16_result)} results found in LE_bdaddr_to_UUID16s_list for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

    if(enable_IEEE_OUI_lookup):
        ############################################
        # MATCH REGEX TO IEEE OUIS (BDADDR PREFIXES)
        ############################################
        # Query for IEEE_bdaddr_to_company table
        values = (companyregex,)
        oui_query = "SELECT bdaddr, company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP %s"
        oui_result = execute_query(oui_query, values)
        for oui, company_name in oui_result:
            bdaddr_prefixes[oui] = company_name
            qprint(f"{companyregex} matched company name {company_name}, with OUI {oui}")

        #qprint(f"bdaddr_prefixes = {bdaddr_prefixes}")
        qprint(f"{len(oui_result)} results found in IEEE_bdaddr_to_company")

        #############################################
        # LOOKUP BDADDRS BY OUIS (ACROSS ALL TABLES!)
        #############################################

        for prefix in bdaddr_prefixes.keys():

            qprint(f"BDADDR OUI: {prefix}")
            values = (prefix,)
            oui_search_query = f"""
            SELECT DISTINCT t.bdaddr
            FROM (
                SELECT %s AS bdaddr_prefix
            ) AS prefix
            CROSS JOIN (
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_name WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_other_le_bdaddr WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_public_target_bdaddr WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_tx_power WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_URI WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_3d_info WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = 0
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_DevID
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_flags
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_MSD
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_name
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_PSRM
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_CoD
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_tx_power
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_URI
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_3d_info
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID128s
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID16s
                UNION ALL
                SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID32s
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_FEATUREs
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_LENGTHs
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_PHYs
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_PINGs
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_UNKNOWN_RSP
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_VERSION_IND
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_FEATURES_RES
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_NAME_RES
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_VERSION_RES
                UNION ALL
                SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_services
            ) AS t
            WHERE t.bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');
            """
            #qprint(oui_search_query)

            oui_search_result = execute_query(oui_search_query, values)
            for (bdaddr,) in oui_search_result:
                bdaddr_hash[bdaddr] = 1

            qprint(f"\t{len(oui_search_result)} results found in all scanned tables")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")
            qprint(f"\tbdaddr_hash current length = {len(bdaddr_hash.keys())}")

# TODO! Add the capability to search within the read values from GATT "Manufacturer Name" characteristics (will require interpreting as string within MySQL)
#    if(enable_GATT_manufacturer_lookup):

    return bdaddr_hash.keys()

def get_bdaddrs_by_msd_regex(msdregex):
    qprint(f"{msdregex} in get_bdaddrs_by_msd_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (msdregex,)
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP %s"
    eir_result = execute_query(eir_query, values)
    bdaddrs += eir_result
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_msd_regex: {len(eir_result)} results found in EIR_bdaddr_to_MSD")
    qprint(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_msd_regex: {len(le_result)} results found in LE_bdaddr_to_MSD")
    qprint(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()


def get_bdaddrs_by_uuid_regex(uuid_regex):

    qprint(f"{uuid_regex} in get_bdaddrs_by_uuid_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables

    # We probably shouldn't remove - since it can change the meaning of things like [1-4]...
    #uuid_regex.replace("-", "")

    # It could be argued that I could skip some UUID16 tables if the regex is guaranteed to be
    # > 4 characters, but that would require fully interpolating the regex.
    # So I'm just going to do it the simple but inefficient way, and look at all the tables
    # which contain a UUID, regardless of length.

    values = (uuid_regex,)

    ###################################
    # Start with UUID128 tables
    ###################################

    # BR/EDR advertisements

    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID128s WHERE str_UUID128s REGEXP %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in EIR_bdaddr_to_UUID128s")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    # LE advertisements

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE str_UUID128s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID128s_list")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE str_UUID128s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID128_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE UUID128_hex_str REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID128_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    ###################################
    # Then UUID32 tables
    ###################################

    # BR/EDR advertisements

    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID32s WHERE str_UUID32s REGEXP %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in EIR_bdaddr_to_UUID32s")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    # LE advertisements

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE str_UUID32s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID32s_list")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE str_UUID32s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID32_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE UUID32_hex_str REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID32_service_data")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    ###################################
    # Then UUID16 tables
    ###################################

    # BR/EDR advertisements

    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in EIR_bdaddr_to_UUID16s")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    # LE advertisements

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE str_UUID16s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID16s_list")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE str_UUID16s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID16_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE UUID16_hex_str REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in LE_bdaddr_to_UUID16_service_data")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    ################################################
    # Then GATT, which can have UUID16s or UUID128s
    ################################################

    # GATT (technically LE or BR/EDR but I don't have BR/EDR-based collection)

    gatt_service_query = "SELECT bdaddr FROM GATT_services WHERE UUID REGEXP %s"
    gatt_service_result = execute_query(gatt_service_query, values)
    for (bdaddr,) in gatt_service_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(gatt_service_result)} results found in GATT_services")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    gatt_char_query = "SELECT bdaddr FROM GATT_characteristics WHERE UUID REGEXP %s"
    gatt_char_result = execute_query(gatt_char_query, values)
    for (bdaddr,) in gatt_char_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(gatt_char_result)} results found in GATT_characteristics")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    gatt_desc_query = "SELECT bdaddr FROM GATT_attribute_handles WHERE UUID REGEXP %s"
    gatt_desc_result = execute_query(gatt_desc_query, values)
    for (bdaddr,) in gatt_desc_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_uuid_regex: {len(gatt_desc_result)} results found in GATT_attribute_handles")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash len {len(bdaddr_hash)} = {bdaddr_hash}")

    ################################################
    # Then SDP, which can have UUID16/32/128s
    ################################################

    # BR/EDR SDP

    # TODO: I'd like to pull out UUIDs specifically and put them back in a separate table,
    # because right now this will probably yield a decent number of false positives...
    # It can also yield false negatives, if given the full UUID, because I've seen
    # them be fragmented across packets.
    # eir_query = "SELECT bdaddr FROM SDP_Common HERE HEX(byte_values) REGEXP %s"
    # eir_result = execute_query(eir_query, values)
    # for (bdaddr,) in eir_result:
    #     bdaddr_hash[bdaddr] = 1
    # qprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in SDP_Common")
    # vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()


def get_bdaddrs_by_LL_VERSION_IND(version, company_id, subversion):
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (version, company_id, subversion)
    le_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE ll_version = %s AND device_BT_CID = %s AND ll_sub_version = %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_LL_VERSION_IND: {len(le_result)} results found in LL_VERSION_IND")
    qprint(f"get_bdaddrs_by_LL_VERSION_IND: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()


def get_bdaddrs_by_LMP_VERSION_RES(version, company_id, subversion):
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (version, company_id, subversion)
    eir_query = "SELECT bdaddr FROM LMP_VERSION_RES WHERE lmp_version = %s AND device_BT_CID = %s AND lmp_sub_version = %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_LMP_VERSION_RES: {len(eir_result)} results found in LMP_VERSION_RES")
    qprint(f"get_bdaddrs_by_LMP_VERSION_RES: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()