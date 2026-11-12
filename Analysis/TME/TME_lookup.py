########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

import re
from concurrent.futures import ThreadPoolExecutor
# import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# Lookup helpers
########################################

# Returns True if there is any LL_VERSION_IND info for this BDADDR, else
# False. LL_VERSION_IND's unique index is (bdaddr_random, bdaddr, ...), so
# the shared helper forces an indexed lookup by binding bdaddr_random when
# supplied or probing both 0 and 1 when not.
def device_has_LL_VERSION_IND_info(bdaddr, bdaddr_random):
    return device_row_exists_by_bdaddr_random(
        "LL_VERSION_IND", bdaddr, bdaddr_random)


# Returns True if there is any LMP_VERSION_RES info for this BDADDR, else
# False. LMP_VERSION_RES is BT Classic-only (no bdaddr_random column) and
# its unique index has `bdaddr` as the leftmost-prefix column, so a plain
# `WHERE bdaddr = %s` is already indexed.
def device_has_LMP_VERSION_RES_info(bdaddr):
    return device_row_exists_by_bdaddr("LMP_VERSION_RES", bdaddr)

def get_bdaddrs_by_name_regex(nameregex, bdaddr_random):
    vprint(nameregex)
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    # Regex matching done in Python (not MySQL) to tolerate non-UTF-8 byte sequences in stored names
    name_pattern = re.compile(nameregex)

    eir_query = "SELECT bdaddr, name_hex_str FROM EIR_bdaddr_to_name"
    eir_result = execute_query(eir_query, ())
    eir_matches = 0
    for (bdaddr, name_hex_str) in eir_result:
        name = bytes.fromhex(name_hex_str).decode('utf-8', errors='ignore')
        if name_pattern.search(name):
            bdaddrs.append((bdaddr,))
            bdaddr_hash[bdaddr] = 1
            eir_matches += 1
    qprint(f"get_bdaddrs_by_name_regex: {eir_matches} results found in DB:EIR_bdaddr_to_name")
    vprint(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query for HCI_bdaddr_to_name table
    hci_query = "SELECT bdaddr, name_hex_str FROM HCI_bdaddr_to_name"
    hci_result = execute_query(hci_query, ())
    hci_matches = 0
    for (bdaddr, name_hex_str) in hci_result:
        name = bytes.fromhex(name_hex_str).decode('utf-8', errors='ignore')
        if name_pattern.search(name):
            bdaddr_hash[bdaddr] = 1
            hci_matches += 1
    qprint(f"get_bdaddrs_by_name_regex: {hci_matches} results found in DB:HCI_bdaddr_to_name")
    vprint(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query for LE_bdaddr_to_name table
    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr, name_hex_str FROM LE_bdaddr_to_name WHERE bdaddr_random = %s"
        le_result = execute_query(le_query, (bdaddr_random,))
    else:
        le_query = "SELECT bdaddr, name_hex_str FROM LE_bdaddr_to_name"
        le_result = execute_query(le_query, ())
    le_matches = 0
    for (bdaddr, name_hex_str) in le_result:
        name = bytes.fromhex(name_hex_str).decode('utf-8', errors='ignore')
        if name_pattern.search(name):
            bdaddr_hash[bdaddr] = 1
            le_matches += 1
    qprint(f"get_bdaddrs_by_name_regex: {le_matches} results found in DB:LE_bdaddr_to_name")
    vprint(f"get_bdaddrs_by_name_regex: bdaddr_hash = {bdaddr_hash}")

    # Query GATT Characteristic values for Device Name (0x2a00) entries, and then checking regex in python instead of MySQL, because the byte values may not be directly translatable to UTF-8 within MySQL
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr_random)
        chars_query = "SELECT cv.bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle AND cv.bdaddr = c.bdaddr WHERE c.bdaddr_random = %s AND cv.bdaddr_random = %s AND c.UUID = '2a00';"
    else:
        values = ()
        chars_query = "SELECT cv.bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle AND cv.bdaddr = c.bdaddr WHERE c.UUID = '2a00';"
    chars_result = execute_query(chars_query, values)
    if(len(chars_result) > 0):
        for (bdaddr, byte_values) in chars_result:
            tmpstr = byte_values.decode('utf-8', 'ignore')
            #qprint(f"byte_values: {tmpstr}")
            if name_pattern.search(tmpstr):
                vprint(f"{nameregex} matched bdaddr = {bdaddr}")
                bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_name_regex: {len(chars_result)} results found in DB:GATT_characteristics_values and DB:GATT_characteristics")
    vprint(f"get_bdaddrs_by_name_regex: bdaddr_hash (len = {len(bdaddr_hash)}) = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_bdaddr_regex(bdaddrregex, bdaddr_random):
    # Translate bare glob '*' to regex '.*' so users can pass '*' to mean "match all"
    bdaddrregex = re.sub(r'(?<!\.)[\*]', '.*', bdaddrregex)
    vprint(bdaddrregex)
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    # The LL/GATT/LMP/SDP address columns need an explicit collation after
    # CONVERT. MariaDB otherwise assigns its default conversion collation,
    # which cannot be UNIONed with the utf8mb4_unicode_ci address columns.

    if(bdaddr_random is not None):
        values = (bdaddrregex,) + (bdaddr_random,) * 33
        bdaddr_query = (
            "SELECT DISTINCT t.bdaddr "
            "FROM ("
            "    SELECT %s AS bdaddr_regex "
            ") AS regex "
            "CROSS JOIN ("
            "    SELECT bdaddr FROM LE_bdaddr_to_3d_info WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_name WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_other_le_bdaddr WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_public_target_bdaddr WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_random_target_bdaddr WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_role WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_tx_power WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_URI WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_FEATUREs WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_LENGTHs WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_PHYs WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_PINGs WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_UNKNOWN_RSP WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_VERSION_IND WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_attribute_handles WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_characteristic_descriptor_values WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_characteristics WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_characteristics_values WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_services WHERE bdaddr_random = %s"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_3d_info"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_CoD"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_DevID"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_flags"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_MSD"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_name"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_PSRM"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_tx_power"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_URI"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_UUID128s"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_UUID16s"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_UUID32s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_FEATURES_RES"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_FEATURES_RES_EXT"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_NAME_RES_defragmented"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_VERSION_RES"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM HCI_bdaddr_to_name"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM SDP_Common"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM SDP_ERROR_RSP"
            ") AS t "
            "WHERE t.bdaddr REGEXP regex.bdaddr_regex;"
        )
    else:
        values = (bdaddrregex,)
        bdaddr_query = (
            "SELECT DISTINCT t.bdaddr "
            "FROM ("
            "    SELECT %s AS bdaddr_regex "
            ") AS regex "
            "CROSS JOIN ("
            "    SELECT bdaddr FROM LE_bdaddr_to_3d_info"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_appearance"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_CoD"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_connect_interval"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_flags"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_MSD"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_name"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_other_le_bdaddr"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_public_target_bdaddr"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_random_target_bdaddr"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_role"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_tx_power"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_URI"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_data"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_solicit"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID128s_list"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_data"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_solicit"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID32s_list"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_data"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_solicit"
            "    UNION ALL"
            "    SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_FEATUREs"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_LENGTHs"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_PHYs"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_PINGs"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_UNKNOWN_RSP"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LL_VERSION_IND"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_attribute_handles"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_characteristic_descriptor_values"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_characteristics"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_characteristics_values"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM GATT_services"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_3d_info"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_CoD"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_DevID"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_flags"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_MSD"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_name"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_PSRM"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_tx_power"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_URI"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_UUID128s"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_UUID16s"
            "    UNION ALL"
            "    SELECT bdaddr FROM EIR_bdaddr_to_UUID32s"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_FEATURES_RES"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_FEATURES_RES_EXT"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_NAME_RES_defragmented"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM LMP_VERSION_RES"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM HCI_bdaddr_to_name"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM SDP_Common"
            "    UNION ALL"
            "    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci FROM SDP_ERROR_RSP"
            ") AS t "
            "WHERE t.bdaddr REGEXP regex.bdaddr_regex;"
        )
    bdaddr_result = execute_query(bdaddr_query, values)
    for (bdaddr,) in bdaddr_result:
        bdaddr_hash[bdaddr] = 1

    qprint(f"get_bdaddrs_by_bdaddr_regex: {len(bdaddr_result)} results found across all tables")
    qprint(f"get_bdaddrs_by_bdaddr_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_bdaddrs_by_company_regex(companyregex, bdaddr_random):
    global bt_CID_to_names
    global bt_member_UUID16s_to_names
    companyregex = re.sub(r'(?<!\.)[\*]', '.*', companyregex)
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
    enable_CLUES_lookup = True

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
            qprint(f"{len(tooth_lmp_result)} results found in DB:LMP_VERSION_RES for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            if(bdaddr_random is not None):
                values = (bdaddr_random, key)
                tooth_ll_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE bdaddr_random = %s AND device_BT_CID = %s"
            else:
                values = (key,)
                tooth_ll_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE device_BT_CID = %s"
            tooth_ll_result = execute_query(tooth_ll_query, values)
            for (bdaddr,) in tooth_ll_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(tooth_ll_result)} results found in DB:LL_VERSION_IND for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            if(bdaddr_random is not None):
                values = (bdaddr_random, key)
                le_msd_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND device_BT_CID = %s"
            else:
                values = (key,)
                le_msd_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE device_BT_CID = %s"
            le_msd_result = execute_query(le_msd_query, values)
            for (bdaddr,) in le_msd_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(le_msd_result)} results found in DB:LE_bdaddr_to_MSD for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            # NOTE: Manufacture-specific data is the location where the BT_CID is most likely to be byte-swapped
            # NOTE: Try the byte-swapped version too if there are no results from the above

            if(try_byte_swapped_bt_cid):
                byte_swapped_key = (key & 0xFF) << 8 | (key & 0xFF00) >> 8
                if(bdaddr_random is not None):
                    values2 = (bdaddr_random, byte_swapped_key)
                    le_msd_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND device_BT_CID = %s"
                else:
                    values2 = (byte_swapped_key,)
                    le_msd_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE device_BT_CID = %s"
                le_msd_result = execute_query(le_msd_query, values2)
                for (bdaddr,) in le_msd_result:
                    bdaddr_hash[bdaddr] = 1
                qprint(f"{len(le_msd_result)} results found in DB:LE_bdaddr_to_MSD for byte-swapped BT_CID for key 0x{byte_swapped_key:04x}")
                #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            values = (key,)
            eir_msd_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE device_BT_CID = %s"
            eir_msd_result = execute_query(eir_msd_query, values)
            for (bdaddr,) in eir_msd_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(eir_msd_result)} results found in DB:EIR_bdaddr_to_MSD for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            if(try_byte_swapped_bt_cid):
                byte_swapped_key = (key & 0xFF) << 8 | (key & 0xFF00) >> 8
                values2 = (byte_swapped_key,)
                eir_msd_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE device_BT_CID = %s"
                eir_msd_result = execute_query(eir_msd_query, values2)
                for (bdaddr,) in eir_msd_result:
                    bdaddr_hash[bdaddr] = 1
                qprint(f"{len(eir_msd_result)} results found in DB:EIR_bdaddr_to_MSD for byte-swapped BT_CID for key 0x{byte_swapped_key:04x}")
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
            qprint(f"{len(eir_uuid16_result)} results found in DB:EIR_bdaddr_to_UUID16s for key 0x{key:04x}")
            #qprint(f"get_bdaddrs_by_company_regex: bdaddr_hash = {bdaddr_hash}")

            if(bdaddr_random is not None):
                values = (bdaddr_random, f"0x{key:04x}")
                le_uuid16_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = %s AND str_UUID16s REGEXP %s"
            else:
                values = (f"0x{key:04x}",)
                le_uuid16_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE str_UUID16s REGEXP %s"
            le_uuid16_result = execute_query(le_uuid16_query, values)
            for (bdaddr,) in le_uuid16_result:
                bdaddr_hash[bdaddr] = 1
            qprint(f"{len(le_uuid16_result)} results found in DB:LE_bdaddr_to_UUID16s_list for key 0x{key:04x}")
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

        oui_jobs = []
        for prefix in bdaddr_prefixes.keys():
            if(bdaddr_random is not None):
                values = (prefix,) + (bdaddr_random,) * 33
                oui_search_query = f"""
                SELECT DISTINCT t.bdaddr
                FROM (
                    SELECT %s AS bdaddr_prefix
                ) AS prefix
                CROSS JOIN (
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_3d_info WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_name WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_other_le_bdaddr WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_public_target_bdaddr WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_random_target_bdaddr WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_role WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_tx_power WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_URI WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_FEATUREs WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_LENGTHs WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_PHYs WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_PINGs WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_UNKNOWN_RSP WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LL_VERSION_IND WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_attribute_handles WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_characteristic_descriptor_values WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_characteristics WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_characteristics_values WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_services WHERE bdaddr_random = %s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_3d_info
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_CoD
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
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_tx_power
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_URI
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID128s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID16s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID32s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_FEATURES_RES
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_FEATURES_RES_EXT
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_NAME_RES_defragmented
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_VERSION_RES
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM HCI_bdaddr_to_name
                ) AS t
                WHERE t.bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');
                """
            else:
                values = (prefix,)
                oui_search_query = f"""
                SELECT DISTINCT t.bdaddr
                FROM (
                    SELECT %s AS bdaddr_prefix
                ) AS prefix
                CROSS JOIN (
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_3d_info
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_appearance
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_CoD
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_connect_interval
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_flags
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_MSD
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_name
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_other_le_bdaddr
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_public_target_bdaddr
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_random_target_bdaddr
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_role
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_tx_power
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_URI
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128_service_data
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128_service_solicit
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID128s_list
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16_service_data
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16_service_solicit
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID16s_list
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32_service_data
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32_service_solicit
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM LE_bdaddr_to_UUID32s_list
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
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_attribute_handles
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_characteristic_descriptor_values
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_characteristics
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_characteristics_values
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM GATT_services
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_3d_info
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_CoD
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
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_tx_power
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_URI
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID128s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID16s
                    UNION ALL
                    SELECT bdaddr COLLATE utf8mb4_unicode_ci AS bdaddr FROM EIR_bdaddr_to_UUID32s
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_FEATURES_RES
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_FEATURES_RES_EXT
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_NAME_RES_defragmented
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM LMP_VERSION_RES
                    UNION ALL
                    SELECT CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci AS bdaddr FROM HCI_bdaddr_to_name
                ) AS t
                WHERE t.bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');
                """
            oui_jobs.append((prefix, oui_search_query, values))

        # Each worker uses its own MySQL connection. Keep the worker count
        # bounded because each OUI query scans many tables.
        if len(oui_jobs) > 1:
            with ThreadPoolExecutor(max_workers=min(4, len(oui_jobs))) as executor:
                oui_results = executor.map(
                    lambda job: execute_query_isolated(job[1], job[2]), oui_jobs
                )
                for (prefix, _, _), oui_search_result in zip(oui_jobs, oui_results):
                    qprint(f"BDADDR OUI: {prefix}")
                    for (bdaddr,) in oui_search_result:
                        bdaddr_hash[bdaddr] = 1
                    qprint(f"{i1}{len(oui_search_result)} results found in all scanned tables")
                    qprint(f"{i1}bdaddr_hash current length = {len(bdaddr_hash)}")
        elif oui_jobs:
            prefix, oui_search_query, values = oui_jobs[0]
            qprint(f"BDADDR OUI: {prefix}")
            oui_search_result = execute_query(oui_search_query, values)
            for (bdaddr,) in oui_search_result:
                bdaddr_hash[bdaddr] = 1

            qprint(f"{i1}{len(oui_search_result)} results found in all scanned tables")
            qprint(f"{i1}bdaddr_hash current length = {len(bdaddr_hash)}")

    if(enable_CLUES_lookup):
        UUIDs_to_company_map = {}
        for key in TME.TME_glob.clues.keys():
            if re.search(pattern, TME.TME_glob.clues[key]["company"]):
                qprint(f"UUID {TME.TME_glob.clues[key]["UUID"]} matched company name regex {companyregex} in CLUES data")
                UUIDs_to_company_map[TME.TME_glob.clues[key]["UUID"]] = 1

        def lookup_clues_uuid(UUID):
            jobs = _uuid_query_jobs(UUID.replace("-", ""), bdaddr_random)
            results = execute_queries_isolated(
                (query, values) for _, query, values in jobs
            )
            return jobs, results

        UUIDs = list(UUIDs_to_company_map)
        if UUIDs:
            # Parallelize across UUIDs, not across their tables, so no more
            # than four database connections are active for this path.
            with ThreadPoolExecutor(max_workers=min(4, len(UUIDs))) as executor:
                lookup_results = executor.map(lookup_clues_uuid, UUIDs)
                for UUID, (jobs, results) in zip(UUIDs, lookup_results):
                    bdaddrs_tmp = _merge_uuid_query_results(
                        UUID.replace("-", ""), jobs, results
                    )
                    for bdaddr in bdaddrs_tmp:
                        bdaddr_hash[bdaddr] = 1
                    qprint(f"{i1}{len(bdaddrs_tmp)} results found for UUID {UUID}")
                    qprint(f"{i1}bdaddr_hash current length = {len(bdaddr_hash)}")

# TODO! Add the capability to search within the read values from GATT "Manufacturer Name" characteristics (will require interpreting as string within MySQL)
#    if(enable_GATT_manufacturer_lookup):

    return bdaddr_hash.keys()


# Target-scoped variant of get_bdaddrs_by_company_regex used by --NOT-company-regex.
# Returns the subset of `candidates` whose company matches `companyregex`.
# Avoids the 33-table UNION ALL per OUI prefix that makes the unscoped function
# painfully slow for regexes like "Apple" (see issue #11).
def get_candidate_bdaddrs_matching_company_regex(companyregex, bdaddr_random, candidates):
    if not candidates:
        return set()

    qprint(f"get_candidate_bdaddrs_matching_company_regex: regex={companyregex}, {len(candidates)} candidates")
    pattern = re.compile(companyregex)
    candidate_set = set(candidates)
    remaining = set(candidate_set)
    matched = set()
    try_byte_swapped_bt_cid = True

    ############################################
    # IEEE OUI path (the hot path for "Apple").
    # Pull matching OUIs into memory once, then prefix-match candidates locally.
    ############################################
    values = (companyregex,)
    oui_query = "SELECT bdaddr, company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP %s"
    oui_result = execute_query(oui_query, values)
    matching_ouis = {oui.lower() for (oui, _company_name) in oui_result}
    qprint(f"{i1}{len(matching_ouis)} OUIs matched in IEEE_bdaddr_to_company")
    if matching_ouis:
        for bdaddr in list(remaining):
            if bdaddr[:8].lower() in matching_ouis:
                matched.add(bdaddr)
                remaining.discard(bdaddr)

    ############################################
    # BT Company ID path — restrict queries to the remaining candidate set.
    ############################################
    if remaining:
        matching_cids = {
            key for key, value in TME.TME_glob.bt_CID_to_names.items()
            if re.search(pattern, value)
        }
        if matching_cids:
            if try_byte_swapped_bt_cid:
                swapped = {((k & 0xFF) << 8) | ((k & 0xFF00) >> 8) for k in matching_cids}
                msd_cids = matching_cids | swapped
            else:
                msd_cids = matching_cids

            def _run_cid_query(table, cids, random_filtered):
                if not remaining or not cids:
                    return
                bdaddr_list = list(remaining)
                cid_list = list(cids)
                bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))
                cid_ph = ",".join(["%s"] * len(cid_list))
                if random_filtered and bdaddr_random is not None:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND bdaddr_random = %s "
                             f"AND device_BT_CID IN ({cid_ph})")
                    vals = tuple(bdaddr_list) + (bdaddr_random,) + tuple(cid_list)
                else:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND device_BT_CID IN ({cid_ph})")
                    vals = tuple(bdaddr_list) + tuple(cid_list)
                for (bdaddr,) in execute_query(query, vals):
                    matched.add(bdaddr)
                    remaining.discard(bdaddr)

            _run_cid_query("LMP_VERSION_RES", matching_cids, random_filtered=False)
            _run_cid_query("LL_VERSION_IND", matching_cids, random_filtered=True)
            _run_cid_query("LE_bdaddr_to_MSD", msd_cids, random_filtered=True)
            _run_cid_query("EIR_bdaddr_to_MSD", msd_cids, random_filtered=False)

    ############################################
    # UUID16 path — restrict queries to the remaining candidate set.
    ############################################
    if remaining:
        matching_uuid16s = {
            key for key, value in TME.TME_glob.bt_member_UUID16s_to_names.items()
            if re.search(pattern, value)
        }
        if matching_uuid16s:
            uuid_pattern = "|".join(f"0x{k:04x}" for k in matching_uuid16s)
            bdaddr_list = list(remaining)
            bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))

            eir_query = (f"SELECT DISTINCT bdaddr FROM EIR_bdaddr_to_UUID16s "
                         f"WHERE bdaddr IN ({bdaddr_ph}) AND str_UUID16s REGEXP %s")
            for (bdaddr,) in execute_query(eir_query, tuple(bdaddr_list) + (uuid_pattern,)):
                matched.add(bdaddr)
                remaining.discard(bdaddr)

            if remaining:
                bdaddr_list = list(remaining)
                bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))
                if bdaddr_random is not None:
                    le_query = (f"SELECT DISTINCT bdaddr FROM LE_bdaddr_to_UUID16s_list "
                                f"WHERE bdaddr IN ({bdaddr_ph}) AND bdaddr_random = %s "
                                f"AND str_UUID16s REGEXP %s")
                    vals = tuple(bdaddr_list) + (bdaddr_random, uuid_pattern)
                else:
                    le_query = (f"SELECT DISTINCT bdaddr FROM LE_bdaddr_to_UUID16s_list "
                                f"WHERE bdaddr IN ({bdaddr_ph}) AND str_UUID16s REGEXP %s")
                    vals = tuple(bdaddr_list) + (uuid_pattern,)
                for (bdaddr,) in execute_query(le_query, vals):
                    matched.add(bdaddr)
                    remaining.discard(bdaddr)

    ############################################
    # CLUES path — batched, candidate-scoped.
    #
    # CLUES UUIDs are full 128-bit values, so they cannot substring-match
    # inside UUID16 (4-char) or UUID32 (8-char) columns — those tables are
    # skipped. All matching CLUES UUIDs for this company regex are collapsed
    # into a single alternation regex per column format and each table is hit
    # exactly once, scoped to the remaining candidate bdaddrs via `bdaddr IN`.
    #
    # Two alternations are emitted because the columns are stored in different
    # formats:
    #   * UUID128s tables (EIR_bdaddr_to_UUID128s, LE_bdaddr_to_UUID128s_list,
    #     LE_bdaddr_to_UUID128_service_solicit, LE_bdaddr_to_UUID128_service_data)
    #     store dash-stripped UUID128 hex.
    #   * GATT_{services,characteristics,attribute_handles}.UUID is CHAR(36)
    #     and stores the dashed form "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx".
    ############################################
    if remaining:
        clues_uuids_raw = []  # keep original dashed form from CLUES
        for key in TME.TME_glob.clues.keys():
            if re.search(pattern, TME.TME_glob.clues[key]["company"]):
                clues_uuids_raw.append(TME.TME_glob.clues[key]["UUID"])

        if clues_uuids_raw:
            clues_pattern_dashless = "|".join(u.replace("-", "") for u in clues_uuids_raw)
            clues_pattern_dashed = "|".join(clues_uuids_raw)

            # (table, uuid_column, uses_bdaddr_random, pattern)
            clues_tables = (
                ("EIR_bdaddr_to_UUID128s", "str_UUID128s", False, clues_pattern_dashless),
                ("LE_bdaddr_to_UUID128s_list", "str_UUID128s", True, clues_pattern_dashless),
                ("LE_bdaddr_to_UUID128_service_solicit", "str_UUID128s", True, clues_pattern_dashless),
                ("LE_bdaddr_to_UUID128_service_data", "UUID128_hex_str", True, clues_pattern_dashless),
                ("GATT_services", "UUID", True, clues_pattern_dashed),
                ("GATT_characteristics", "UUID", True, clues_pattern_dashed),
                ("GATT_attribute_handles", "UUID", True, clues_pattern_dashed),
            )

            for table, col, uses_random, clues_pattern in clues_tables:
                if not remaining:
                    break
                bdaddr_list = list(remaining)
                bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))
                if uses_random and bdaddr_random is not None:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND bdaddr_random = %s "
                             f"AND {col} REGEXP %s")
                    vals = tuple(bdaddr_list) + (bdaddr_random, clues_pattern)
                else:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND {col} REGEXP %s")
                    vals = tuple(bdaddr_list) + (clues_pattern,)
                for (bdaddr,) in execute_query(query, vals):
                    matched.add(bdaddr)
                    remaining.discard(bdaddr)

    qprint(f"get_candidate_bdaddrs_matching_company_regex: {len(matched)}/{len(candidate_set)} candidates matched")
    return matched


def get_bdaddrs_by_msd_regex(msdregex, bdaddr_random):
    qprint(f"{msdregex} in get_bdaddrs_by_msd_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (msdregex,)
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP %s"
    eir_result = execute_query(eir_query, values)
    bdaddrs += eir_result
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_msd_regex: {len(eir_result)} results found in DB:EIR_bdaddr_to_MSD")
    qprint(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        values = (bdaddr_random, msdregex)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND manufacturer_specific_data REGEXP %s"
    else:
        values = (msdregex,)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_msd_regex: {len(le_result)} results found in DB:LE_bdaddr_to_MSD")
    qprint(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def sanity_check_UUID_regex(entry):
    if "-" not in entry:
        return True
    while True:
        print(" __                 ")
        print("/  \\        ____________________________________________")
        print("|  |       /                                             \\")
        print("@  @       | It looks like you are trying to pass a UUID |")
        print("|| ||      | regex with dashes in it. The dashes will be |")
        print("|| ||   <--| interpreted as part of the regex pattern.   |")
        print("|\\_/|      | Do you want me to remove the dashes?        |")
        print("\\___/      \\_____________________________________________/")
        try:
            choice = input("y/n: ")
        except EOFError:
            print("Input must be y or n. Try again!")
            return False
        choice = choice.strip().lower()
        if choice == "y":
            return True
        if choice == "n":
            return False
        print("Input must be y or n. Try again!")


def _uuid_query_jobs(uuid_regex, bdaddr_random):
    # A regex can match more than one UUID width, so check all 15 tables.
    uuid_tables = (
        ("EIR_bdaddr_to_UUID128s", "str_UUID128s", False),
        ("LE_bdaddr_to_UUID128s_list", "str_UUID128s", True),
        ("LE_bdaddr_to_UUID128_service_solicit", "str_UUID128s", True),
        ("LE_bdaddr_to_UUID128_service_data", "UUID128_hex_str", True),
        ("EIR_bdaddr_to_UUID32s", "str_UUID32s", False),
        ("LE_bdaddr_to_UUID32s_list", "str_UUID32s", True),
        ("LE_bdaddr_to_UUID32_service_solicit", "str_UUID32s", True),
        ("LE_bdaddr_to_UUID32_service_data", "UUID32_hex_str", True),
        ("EIR_bdaddr_to_UUID16s", "str_UUID16s", False),
        ("LE_bdaddr_to_UUID16s_list", "str_UUID16s", True),
        ("LE_bdaddr_to_UUID16_service_solicit", "str_UUID16s", True),
        ("LE_bdaddr_to_UUID16_service_data", "UUID16_hex_str", True),
        ("GATT_services", "UUID", True),
        ("GATT_characteristics", "UUID", True),
        ("GATT_attribute_handles", "UUID", True),
    )
    jobs = []
    for table, column, has_bdaddr_random in uuid_tables:
        if has_bdaddr_random and bdaddr_random is not None:
            query = f"SELECT bdaddr FROM {table} WHERE bdaddr_random = %s AND {column} REGEXP %s"
            values = (bdaddr_random, uuid_regex)
        else:
            query = f"SELECT bdaddr FROM {table} WHERE {column} REGEXP %s"
            values = (uuid_regex,)
        jobs.append((table, query, values))
    return jobs


def _merge_uuid_query_results(uuid_regex, jobs, results):
    qprint(f"{uuid_regex} in get_bdaddrs_by_uuid_regex")
    bdaddr_hash = {}  # Preserve table order while de-duplicating addresses.
    for (table, _, _), rows in zip(jobs, results):
        for (bdaddr,) in rows:
            bdaddr_hash[bdaddr] = 1
        vprint(f"get_bdaddrs_by_uuid_regex: {len(rows)} results found in DB:{table}")
        vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")
    return bdaddr_hash.keys()


def get_bdaddrs_by_uuid_regex(uuid_regex, bdaddr_random):
    jobs = _uuid_query_jobs(uuid_regex, bdaddr_random)
    # For a single UUID, overlap table queries on at most four connections.
    # The CLUES path instead overlaps UUIDs and runs each UUID's queries on
    # one connection, so the worker limit is still four overall.
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(
            lambda job: execute_query_isolated(job[1], job[2]), jobs
        )
        return _merge_uuid_query_results(uuid_regex, jobs, results)


def get_bdaddrs_by_LL_VERSION_IND(version, company_id, subversion, bdaddr_random):
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    if(bdaddr_random is not None):
        values = (version, company_id, subversion, bdaddr_random)
        le_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE ll_version = %s AND device_BT_CID = %s AND ll_sub_version = %s AND bdaddr_random = %s"
    else:
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
