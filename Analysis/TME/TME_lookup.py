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
    version_query = f"SELECT device_BT_CID FROM BLE2th_LL_VERSION_IND WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)
    if(len(version_result) != 0):
        return 1
    else:
        return 0

# Returns 0 if there is no LMP_VERSION_RES info for this BDADDR, else returns 1
def device_has_LMP_VERSION_RES_info(bdaddr):
    version_query = f"SELECT device_BT_CID FROM BTC2th_LMP_version_res WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)
    if(len(version_result) != 0):
        return 1
    else:
        return 0

def get_bdaddrs_by_name_regex(nameregex):
    print(nameregex)
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    eir_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_name WHERE device_name REGEXP '{nameregex}'"
    eir_result = execute_query(eir_query)
    bdaddrs += eir_result
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_name_regex: {len(eir_result)} results found in EIR_bdaddr_to_name")
    print(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query for RSP_bdaddr_to_name table
    rsp_query = f"SELECT device_bdaddr FROM RSP_bdaddr_to_name WHERE device_name REGEXP '{nameregex}'"
    rsp_result = execute_query(rsp_query)
    for (bdaddr,) in rsp_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_name_regex: {len(rsp_result)} results found in RSP_bdaddr_to_name")
    print(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query for LE_bdaddr_to_name2 table
    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_name2 WHERE device_name REGEXP '{nameregex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_name_regex: {len(le_result)} results found in LE_bdaddr_to_name2")
    print(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query GATT Characteristic values for Device Name (0x2a00) entries, and then checking regex in python instead of MySQL, because the byte values may not be directly translatable to UTF-8 within MySQL
    chars_query = f"SELECT cv.device_bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.read_handle = c.char_value_handle AND cv.device_bdaddr = c.device_bdaddr WHERE c.UUID128 = '00002a00-0000-1000-8000-00805f9b34fb';"
    chars_result = execute_query(chars_query)
    if(len(chars_result) > 0):
        for (bdaddr, byte_values) in chars_result:
            tmpstr = byte_values.decode('utf-8', 'ignore')
            #print(f"byte_values: {tmpstr}")
            pattern = re.compile(nameregex)
            if re.search(pattern, tmpstr):
                print(f"{nameregex} matched bdaddr = {bdaddr}")
                bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_name_regex: {len(chars_result)} results found in GATT_characteristics_values and GATT_characteristics")
    print(f"get_bdaddrs_by_name_regex: bdaddr_hash (len = {len(bdaddr_hash)}) = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_bdaddr_regex(bdaddrregex):
    print(bdaddrregex)
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    bdaddr_query = (
        f"SELECT DISTINCT t.device_bdaddr "
        f"FROM ( "
        f"    SELECT '{bdaddrregex}' AS bdaddr_prefix "
        f") AS prefix "
        f"CROSS JOIN ( "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = 0" # TODO: It would be better if we added a parameter to allow the caller to specify if they want to consider random addresses or not
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = 0"
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = 0"
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_name2 WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_other_le_bdaddr WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_public_target_bdaddr WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_tx_power WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_URI WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_UUID128s WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_UUID16s WHERE bdaddr_random = 0 "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_DevID "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_flags "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_MSD "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_name "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_PSRM "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_CoD "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_tx_power "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_UUID128s "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_UUID16s "
        f"    UNION ALL "
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_UUID32s "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BLE2th_LL_FEATUREs "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BLE2th_LL_LENGTHs "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BLE2th_LL_PHYs "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BLE2th_LL_PING_RSP "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BLE2th_LL_UNKNOWN_RSP "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BLE2th_LL_VERSION_IND "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BTC2th_LMP_features_res "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BTC2th_LMP_name_res "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM BTC2th_LMP_version_res "
        f"    UNION ALL "
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM GATT_services2 "
        f") AS t "
        f"WHERE t.device_bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');"
    )

    bdaddr_result = execute_query(bdaddr_query)
    for (bdaddr,) in bdaddr_result:
        bdaddr_hash[bdaddr] = 1

    print(f"get_bdaddrs_by_bdaddr_regex: {len(bdaddr_result)} results found across all tables")
    print(f"get_bdaddrs_by_bdaddr_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_company_regex(companyregex):
    global bt_CID_to_names
    global bt_member_UUID16s_to_names
    print(f"Your given regex was {companyregex}")
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
                print(f"{companyregex} matched company name {value}, with ID 0x{key:04x}")
                device_bt_cids_to_names[key] = value

        print(f"device_bt_cids_to_names = {device_bt_cids_to_names}")

        #########################################
        # LOOKUP BDADDRS BY BT_CIDs
        #########################################

        for key in device_bt_cids_to_names.keys():

            tooth_lmp_query = f"SELECT device_bdaddr FROM BTC2th_LMP_version_res WHERE device_BT_CID = '{key}'"
            tooth_lmp_result = execute_query(tooth_lmp_query)
            for (bdaddr,) in tooth_lmp_result:
                bdaddr_hash[bdaddr] = 1
            print(f"{len(tooth_lmp_result)} results found in BTC2th_LMP_version_res for key 0x{key:04x}")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            tooth_ll_query = f"SELECT device_bdaddr FROM BLE2th_LL_VERSION_IND WHERE device_BT_CID = '{key}'"
            tooth_ll_result = execute_query(tooth_ll_query)
            for (bdaddr,) in tooth_ll_result:
                bdaddr_hash[bdaddr] = 1
            print(f"{len(tooth_ll_result)} results found in BLE2th_LL_VERSION_IND for key 0x{key:04x}")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            le_msd_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_MSD WHERE device_BT_CID = '{key}'"
            le_msd_result = execute_query(le_msd_query)
            for (bdaddr,) in le_msd_result:
                bdaddr_hash[bdaddr] = 1
            print(f"{len(le_msd_result)} results found in LE_bdaddr_to_MSD for key 0x{key:04x}")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            # NOTE: Manufacture-specific data is the location where the BT_CID is most likely to be byte-swapped
            # NOTE: Try the byte-swapped version too if there are no results from the above

            if(try_byte_swapped_bt_cid):
                byte_swapped_key = (key & 0xFF) << 8 | (key & 0xFF00) >> 8
                le_msd_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_MSD WHERE device_BT_CID = '{byte_swapped_key}'"
                le_msd_result = execute_query(le_msd_query)
                for (bdaddr,) in le_msd_result:
                    bdaddr_hash[bdaddr] = 1
                print(f"{len(le_msd_result)} results found in LE_bdaddr_to_MSD for byte-swapped BT_CID for key 0x{byte_swapped_key:04x}")
                #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            eir_msd_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_MSD WHERE device_BT_CID = '{key}'"
            eir_msd_result = execute_query(eir_msd_query)
            for (bdaddr,) in eir_msd_result:
                bdaddr_hash[bdaddr] = 1
            print(f"{len(eir_msd_result)} results found in EIR_bdaddr_to_MSD for key 0x{key:04x}")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            if(try_byte_swapped_bt_cid):
                byte_swapped_key = (key & 0xFF) << 8 | (key & 0xFF00) >> 8
                eir_msd_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_MSD WHERE device_BT_CID = '{byte_swapped_key}'"
                eir_msd_result = execute_query(eir_msd_query)
                for (bdaddr,) in eir_msd_result:
                    bdaddr_hash[bdaddr] = 1
                print(f"{len(eir_msd_result)} results found in EIR_bdaddr_to_MSD for byte-swapped BT_CID for key 0x{byte_swapped_key:04x}")
                #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")
   
    if(enable_UUID16_lookup):
        #########################################
        # MATCH REGEX TO BT COMPANY UUID16S
        #########################################

        # Each company can have multiple UUID16s assigned (e.g. Apple has 0xFEC6-FED4)
        for key, value in TME.TME_glob.bt_member_UUID16s_to_names.items():
            if re.search(pattern, value):
                print(f"{companyregex} matched company name {value}, with UUID16 0x{key:04x}")
                device_uuid16s_to_names[key] = value

        print(f"device_uuid16s_to_names = {device_uuid16s_to_names}")

        #########################################
        # LOOKUP BDADDRS BY UUID16S
        #########################################

        for key in device_uuid16s_to_names.keys():

            eir_uuid16_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP '0x{key:04x}'"
            eir_uuid16_result = execute_query(eir_uuid16_query)
            for (bdaddr,) in eir_uuid16_result:
                bdaddr_hash[bdaddr] = 1
            print(f"{len(eir_uuid16_result)} results found in EIR_bdaddr_to_UUID16s for key 0x{key:04x}")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            le_uuid16_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP '0x{key:04x}'"
            le_uuid16_result = execute_query(le_uuid16_query)
            for (bdaddr,) in le_uuid16_result:
                bdaddr_hash[bdaddr] = 1
            print(f"{len(le_uuid16_result)} results found in LE_bdaddr_to_UUID16s for key 0x{key:04x}")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

    if(enable_IEEE_OUI_lookup):
        ############################################
        # MATCH REGEX TO IEEE OUIS (BDADDR PREFIXES)
        ############################################
        # Query for IEEE_bdaddr_to_company table
        oui_query = f"SELECT device_bdaddr, company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP '{companyregex}'"
        oui_result = execute_query(oui_query)
        for oui, company_name in oui_result:
            bdaddr_prefixes[oui] = company_name
            print(f"{companyregex} matched company name {company_name}, with OUI {oui}")

        #print(f"bdaddr_prefixes = {bdaddr_prefixes}")
        print(f"{len(oui_result)} results found in IEEE_bdaddr_to_company")

        #############################################
        # LOOKUP BDADDRS BY OUIS (ACROSS ALL TABLES!)
        #############################################
 
        for prefix in bdaddr_prefixes.keys():

            print(f"BDADDR OUI: {prefix}")
            oui_search_query = f"""
            SELECT DISTINCT t.device_bdaddr
            FROM (
                SELECT '{prefix}' AS bdaddr_prefix
            ) AS prefix
            CROSS JOIN (
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = 0
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = 0
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = 0
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_name2 WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_other_le_bdaddr WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_public_target_bdaddr WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_tx_power WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_URI WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_UUID128s WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM LE_bdaddr_to_UUID16s WHERE bdaddr_random = 0 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_DevID 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_flags 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_MSD 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_name 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_PSRM 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_CoD 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_tx_power 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_UUID128s 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_UUID16s 
                UNION ALL
                SELECT device_bdaddr COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM EIR_bdaddr_to_UUID32s 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BLE2th_LL_FEATUREs 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BLE2th_LL_LENGTHs 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BLE2th_LL_PHYs 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BLE2th_LL_PING_RSP 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BLE2th_LL_UNKNOWN_RSP 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BLE2th_LL_VERSION_IND 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BTC2th_LMP_features_res 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BTC2th_LMP_name_res 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM BTC2th_LMP_version_res 
                UNION ALL
                SELECT CONVERT(device_bdaddr USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS device_bdaddr FROM GATT_services2 
            ) AS t
            WHERE t.device_bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');
            """
            #print(oui_search_query)

            oui_search_result = execute_query(oui_search_query)
            for (bdaddr,) in oui_search_result:
                bdaddr_hash[bdaddr] = 1

            print(f"\t{len(oui_search_result)} results found in all scanned tables")
            #print(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")
            print(f"\tbdaddr_hash current length = {len(bdaddr_hash.keys())}")

# TODO! Add the capability to search within the read values from GATT "Manufacturer Name" characteristics (will require interpreting as string within MySQL)
#    if(enable_GATT_manufacturer_lookup):

    return bdaddr_hash.keys()

def get_bdaddrs_by_msd_regex(msdregex):
    print(f"{msdregex} in get_bdaddrs_by_msd_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    eir_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP '{msdregex}'"
    eir_result = execute_query(eir_query)
    bdaddrs += eir_result
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_msd_regex: {len(eir_result)} results found in EIR_bdaddr_to_MSD")
    print(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP '{msdregex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_msd_regex: {len(le_result)} results found in LE_bdaddr_to_MSD")
    print(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_uuid128_regex(uuid128regex):

    # To make my life easier when searching for things I've already removed the - from
    try_with_dashes = True

    print(f"{uuid128regex} in get_bdaddrs_by_uuid128_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables

    eir_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_UUID128s WHERE str_UUID128s REGEXP '{uuid128regex}'"
    eir_result = execute_query(eir_query)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid128_regex: {len(eir_result)} results found in EIR_bdaddr_to_UUID128s")
    print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_UUID128s WHERE str_UUID128s REGEXP '{uuid128regex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid128_regex: {len(le_result)} results found in LE_bdaddr_to_UUID128s")
    print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE str_UUID128s REGEXP '{uuid128regex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid128_regex: {len(le_result)} results found in LE_bdaddr_to_UUID128_service_solicit")
    print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

    gatt_service_query = f"SELECT device_bdaddr FROM GATT_services2 WHERE UUID128 REGEXP '{uuid128regex}'"
    gatt_service_result = execute_query(gatt_service_query)
    for (bdaddr,) in gatt_service_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_service_result)} results found in GATT_services")
    print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

    gatt_char_query = f"SELECT device_bdaddr FROM GATT_characteristics WHERE UUID128 REGEXP '{uuid128regex}'"
    gatt_char_result = execute_query(gatt_char_query)
    for (bdaddr,) in gatt_char_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_char_result)} results found in GATT_characteristics")
    print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

    gatt_desc_query = f"SELECT device_bdaddr FROM GATT_attribute_handles WHERE UUID128 REGEXP '{uuid128regex}'"
    gatt_desc_result = execute_query(gatt_desc_query)
    for (bdaddr,) in gatt_desc_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_desc_result)} results found in GATT_attribute_handles")
    print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash len {len(bdaddr_hash)} = {bdaddr_hash}")

    if(try_with_dashes and len(uuid128regex) == 32):
        uuid128regex_with_dashes = f"{uuid128regex[:8]}-{uuid128regex[8:12]}-{uuid128regex[12:16]}-{uuid128regex[16:20]}-{uuid128regex[20:32]}"

        gatt_service_query = f"SELECT device_bdaddr FROM GATT_services2 WHERE UUID128 REGEXP '{uuid128regex_with_dashes}'"
        gatt_service_result = execute_query(gatt_service_query)
        for (bdaddr,) in gatt_service_result:
            bdaddr_hash[bdaddr] = 1
        print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_service_result)} results found in GATT_services2 by adding dashes to regex")
        print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

        gatt_char_query = f"SELECT device_bdaddr FROM GATT_characteristics WHERE UUID128 REGEXP '{uuid128regex_with_dashes}'"
        gatt_char_result = execute_query(gatt_char_query)
        for (bdaddr,) in gatt_char_result:
            bdaddr_hash[bdaddr] = 1
        print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_char_result)} results found in GATT_characteristics by adding dashes to regex")
        print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash = {bdaddr_hash}")

        gatt_desc_query = f"SELECT device_bdaddr FROM GATT_attribute_handles WHERE UUID128 REGEXP '{uuid128regex_with_dashes}'"
        gatt_desc_result = execute_query(gatt_desc_query)
        for (bdaddr,) in gatt_desc_result:
            bdaddr_hash[bdaddr] = 1
        print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_desc_result)} results found in GATT_attribute_handles by adding dashes to regex")
        print(f"get_bdaddrs_by_uuid128_regex: bdaddr_hash {len(bdaddr_hash)} = {bdaddr_hash}")


    return bdaddr_hash.keys()

def get_bdaddrs_by_uuid16_regex(uuid16regex):

    # To make my life easier when searching for things I've already removed the - from
    try_with_dashes = True

    print(f"{uuid16regex} in get_bdaddrs_by_uuid16_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables

    eir_query = f"SELECT device_bdaddr FROM EIR_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP '{uuid16regex}'"
    eir_result = execute_query(eir_query)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid16_regex: {len(eir_result)} results found in EIR_bdaddr_to_UUID16s")
    print(f"get_bdaddrs_by_uuid16_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP '{uuid16regex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid16_regex: {len(le_result)} results found in LE_bdaddr_to_UUID16s")
    print(f"get_bdaddrs_by_uuid16_regex: bdaddr_hash = {bdaddr_hash}")

    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE str_UUID16s REGEXP '{uuid16regex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_uuid16_regex: {len(le_result)} results found in LE_bdaddr_to_UUID16_service_solicit")
    print(f"get_bdaddrs_by_uuid16_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()