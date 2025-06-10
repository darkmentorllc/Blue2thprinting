########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

import mysql.connector
import re
import TME.TME_glob
from TME.TME_BTIDES_AdvData import *
from TME.TME_BTIDES_HCI import *

from colorama import Fore, Back, Style, init
init(autoreset=True)

########################################
# MYSQL specific
########################################

# Function to execute a MySQL query and fetch results
def execute_query(query, values):
    global use_test_db
    if(TME.TME_glob.use_test_db):
        database = 'bttest'
    else:
        database = 'bt2'

    connection = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database=database,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password'
    )

    cursor = connection.cursor()
    cursor.execute(query, values)
    result = cursor.fetchall()

    cursor.close()
    connection.close()
    return result

def execute_update(query, values):
    global use_test_db
    if(TME.TME_glob.use_test_db):
        database = 'bttest'
    else:
        database = 'bt2'

    connection = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database=database,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password'
    )

    cursor = connection.cursor()
    cursor.execute(query, values)
    connection.commit()

    cursor.close()
    connection.close()

# Function to execute a MySQL query and fetch results
def execute_insert(query, values):
    global insert_count, duplicate_count, use_test_db
    if(TME.TME_glob.use_test_db):
        database = 'bttest'
    else:
        database = 'bt2'

    connection = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database=database,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password',
        get_warnings=True,
        raise_on_warnings=True
    )

    cursor = connection.cursor()
    # TODO: FIXME: I can't find a way around the
    # "1300: Invalid utf8mb4 character string:..."
    # warning for use of the BLOB or VARBINARY type of byte_values in the SDP_Common table
    # so for now I just have to be more specific in looking at warnings
    # and using them to infer when insertions are duplicates or not
    try:
        cursor.execute(query, values)
        connection.commit()  # Commit the transaction
        TME.TME_glob.insert_count += 1  # Increment insert_count if no exception is raised
    except Exception as e:
        # Be more specific and only count it as a duplicate if the warning->error code is 1062
        duplicate = False
        warnings_tuples = cursor.fetchwarnings()
        if warnings_tuples:
            for warning_tuple in warnings_tuples:
                # Be more specific and only count it as a duplicate if the warning code is 1062
                if(warning_tuple[1] == 1062):
                    #vprint(f"Warning: {warning_tuple}")
                    TME.TME_glob.duplicate_count += 1
                    duplicate = True
                    break
            # If we get through all of the warnings (there could be multiple, like 1300 and 1062)
            # and none of them are 1062, then go ahead and increment the insert count
            if(not duplicate):
                # Wasn't a duplicate, just a warning (i.e. the non-utf8 byte_values in SDP_Commone)
                connection.commit()
                TME.TME_glob.insert_count += 1  # Increment insert_count only if no duplicates


    # OLD CODE: leaving it here for now though...
    # try:
    #     cursor.execute(query, values)
    #     connection.commit()

    #     duplicate = False
    #     if cursor._warning_count > 0:
    #         warnings_tuples = cursor.fetchwarnings()
    #         if warnings_tuples:
    #             for warning_tuple in warnings_tuples:
    #                 # Be more specific and only count it as a duplicate if the warning code is 1062
    #                 if(warning_tuple[1] == 1062):
    #                     #vprint(f"Warning: {warning_tuple}")
    #                     TME.TME_glob.duplicate_count += 1
    #                     duplicate = True
    #                     break
    #             # If we get through all of the warnings (there could be multiple, like 1300 and 1062)
    #             # and none of them are 1062, then go ahead and increment the insert count
    #             if(not duplicate):
    #                 TME.TME_glob.insert_count += 1  # Increment insert_count only if no duplicates
    #     else:
    #         TME.TME_glob.insert_count += 1  # Increment insert_count only if no duplicates

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

########################################
# Helpers
########################################

# Quiet print overrides verbose print if present
def qprint(fmt):
    if(not TME.TME_glob.quiet_print): print(fmt)

# Verbose print
def vprint(fmt):
    if(TME.TME_glob.verbose_print): qprint(fmt)

# Use the UUID16 names mapping to get the protocol ID
def get_uuid16_protocol_string(uuid16):
    return TME.TME_glob.uuid16_protocol_names.get(int(uuid16.strip(),16), "Unknown")

# Use the UUID16 names mapping to get the service ID
def get_uuid16_service_string(uuid16):
    return TME.TME_glob.uuid16_service_names.get(int(uuid16.strip(),16), "Unknown")

def get_bt_spec_version_numbers_to_names(number):
    return TME.TME_glob.bt_spec_version_numbers_to_names.get(number, "Unknown")

def get_utf8_string_from_hex_string(hex_str):
    return bytes.fromhex(hex_str).decode('utf-8', 'ignore')

# Function to get the string representation of le_evt_type
def get_le_event_type_string(le_evt_type):
    event_type_mapping = {
        0: "Connectable Undirected Advertising (ADV_IND)",
        1: "Connectable Directed Advertising (ADV_DIRECT_IND)",
        2: "Scannable Undirected Advertising (ADV_SCAN_IND)",
        3: "Non-Connectable Undirected Advertising (ADV_NONCONN_IND)",
        4: "Scan Response (SCAN_RSP)",
        16: "(New wireshark) (none of scannable, connectable, etc listed)",
        18: "(New wireshark) Scannable",
        19: "(New wireshark) Connectable, Scannable",
        26: "(New wireshark) Scannable, Scan Response",
        27: "(New wireshark) Connectable, Scannable, Scan Response"
    }
    return event_type_mapping.get(le_evt_type, f"Unknown Event Type ({le_evt_type})")


# Look up if we have any refereces to this bdaddr in any of the db tables used to store BC info
def is_bdaddr_classic(bdaddr):
    values = (bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr)
    query = """
    SELECT 1 AS bdaddr
    FROM EIR_bdaddr_to_DevID
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_flags
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_MSD
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_name
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_PSRM
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_CoD
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_tx_power
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID128s
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID16s
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID32s
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID32s
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM LMP_FEATURES_RES
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM LMP_NAME_RES
    WHERE bdaddr = %s
    UNION
    SELECT 1
    FROM LMP_VERSION_RES
    WHERE bdaddr = %s;
    """
    result = execute_query(query, values)
    #qprint(result)
    if(len(result) > 0):
        for (bdaddr_result,) in result:
            if(bdaddr_result):
                return True

    '''
    # NOTE: Temporarily disabled, because this adds something like 5 seconds to this function and slows down the entire code. We need to find a better way to do this (since I had even noticed the slowdown after I added)
    # Check if this BDADDR appears in Microsoft Swift Pair MSD - https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair
    bdaddr_little_endian_str = f"{bdaddr[15:17]}{bdaddr[12:14]}{bdaddr[9:11]}{bdaddr[6:8]}{bdaddr[3:5]}{bdaddr[0:2]}"
    values = (bdaddr_little_endian_str,)
    query = "SELECT id FROM LE_bdaddr_to_MSD where device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030180%s';"
    result = execute_query(query, values)
    if(len(result) != 0):
        return True
    '''

    return False

# Return -1 on error
# Return 0 on a public BDADDR
# Return 1 on a random BDADDR
def is_bdaddr_le_and_random(bdaddr):

    # Note: this is a suboptimal query, but it's the first one I could get working and I wanted to move on
    # It would be better if it returned an error on an empty set, implying we needed to update the tables list
    values = (bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr,bdaddr)

    query = """
    SELECT 1
    FROM LE_bdaddr_to_appearance
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_CoD
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_connect_interval
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_flags
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_MSD
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_name
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_other_le_bdaddr
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_public_target_bdaddr
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_tx_power
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_URI
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID128_service_solicit
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID128_service_data
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID128s_list
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID32_service_solicit
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID32_service_data
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID32s_list
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1    FROM LE_bdaddr_to_UUID16_service_solicit
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID16_service_data
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID16s_list
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LL_FEATUREs
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LL_LENGTHs
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LL_PHYs
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LL_PINGs
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LL_UNKNOWN_RSP
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LL_VERSION_IND
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM GATT_characteristics
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM GATT_characteristics_values
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM GATT_attribute_handles
    WHERE bdaddr = %s and bdaddr_random = 1
    UNION
    SELECT 1
    FROM GATT_services
    WHERE bdaddr = %s and bdaddr_random = 1;
    """



    result = execute_query(query, values)
    if(len(result) == 0):
        return False

    for (bdaddr_result,) in result:
        if(bdaddr_result == 1):
            return True

# Special case of random = -1 means the caller doesn't know whether it's random or not, and wants it looked up
def get_bdaddr_type(bdaddr, random):
    bdaddr_type_str = ""

    if(random == -1):
        if(is_bdaddr_classic(bdaddr)):
            return "Classic"

        random = is_bdaddr_le_and_random(bdaddr)
        if(random == -1):
            qprint("Error encounter in get_bdaddr_type for {bdaddr}. Debug.")
            exit()

    if(random == 0):
        bdaddr_type_str = "Public"
    elif(bdaddr[0].lower() == 'f' or bdaddr[0].lower() == 'e' or bdaddr[0] == 'd' or bdaddr[0].lower() == 'c'):
        bdaddr_type_str = "Random Static"
    elif(random == 1 and (bdaddr[0] == '7' or bdaddr[0] == '6' or bdaddr[0] == '5' or bdaddr[0] == '4')):
        bdaddr_type_str = "Random Resolvable"
    elif(random == 1 and (bdaddr[0] == '3' or bdaddr[0] == '2' or bdaddr[0] == '1' or bdaddr[0] == '0')):
        bdaddr_type_str = "Random Non-Resolvable"
    else:
        bdaddr_type_str = "Random Buggy?"

    return bdaddr_type_str

# Function to get the company name by UUID16 from UUID16_to_company table
def get_custom_by_uuid16(uuid16):
    uuid = uuid16.strip()
    if(uuid in TME.TME_glob.clues.keys()):
        entry = TME.TME_glob.clues[uuid]
        if("UUID_name" not in entry.keys()):
            name = "Unknown"
        else:
            name = entry["UUID_name"]
        return f"{entry["company"]}:{name}"
    else:
        return "Unknown"

# Function to get the company name by UUID16 from UUID16_to_company table
def get_company_by_uuid16(uuid16):
    values = (f"0x{uuid16.strip()}",)
    company_query = "SELECT company_name FROM UUID16_to_company WHERE str_UUID16_CID = %s"
    result = execute_query(company_query, values)
    return result[0][0] if result else "Unknown"

# Look up company name based on 16-bit BT Company ID (CID)
def BT_CID_to_company_name(device_BT_CID):
    s = "No Match"
    if(device_BT_CID in TME.TME_glob.bt_CID_to_names):
        s = TME.TME_glob.bt_CID_to_names[device_BT_CID]

    return Fore.YELLOW + Style.BRIGHT + s + Style.RESET_ALL

# Look up company name based on 16-bit USB Company ID (CID) (Sometimes BT uses these IDs if a flag says to)
def USB_CID_to_company_name(device_USB_CID):
    s = "No Match"
    values = (device_USB_CID,)
    query = "SELECT device_USB_CID, company_name FROM USB_CID_to_company WHERE device_USB_CID = %s"
    result = execute_query(query, values)
    for device_USB_CID, company_name in result:
        s = f"{company_name}"

    return s

########################################
# Company name by BDADDR
########################################

def print_company_name_from_bdaddr(indent, bdaddr, print_type):
    bdaddr = bdaddr.strip().lower()
    random = False

    # Extract the first 3 octets from the bdaddr
    first_three_octets = bdaddr[:8]

    # We first need to find out whether this is a classic BDADDR or a BLE public BDADDR, otherwise it's not valid to print out
    # We don't have a better way to find that out currently than to re-look-up the BDADDR in all possible database tables
    # to see if we have any data that tells us it's classic or public
    is_classic = is_bdaddr_classic(bdaddr)
    if(not is_classic):
        random = is_bdaddr_le_and_random(bdaddr)

    if(random):
        qprint(f"{indent}Company Name by IEEE OUI: Not Applicable because this is a {get_bdaddr_type(bdaddr, random)} address")
    else:
        # Query the database for the company_name based on the first 3 octets
        values = (first_three_octets,)
        query = "SELECT company_name FROM IEEE_bdaddr_to_company WHERE bdaddr = %s"
        result = execute_query(query, values)

        if result:
            qprint(f"{indent}Company Name by IEEE OUI ({bdaddr[:8]}): {result[0][0]}")
            if(first_three_octets == "00:00:00"):
                qprint(f"{indent}\tNOTE: Most BDADDR that begin with 00:00:00 are erroneous, not actual XEROX devices!")
        else:
            qprint(f"{indent}Company Name by IEEE OUI ({bdaddr[:8]}): No Match")

        if(print_type):
            if(is_classic):
                qprint(f"{indent}\tBDADDR is Bluetooth Classic")
            else:
                qprint(f"{indent}\tBDADDR is Bluetooth Low Energy Public")

    qprint("")

###################################################################################
# Ideally should be in TME_names, but I don't want to introduce cyclic dependancies
###################################################################################
# !!!FIXME: For devices with () in their name, like "Galaxy Watch3 (0462)",
# the nameprint to match in MySQL needs to be "^Galaxy Watch3 \\\([A-F0-9]{4}\\\)$
# however, it only matches in Python regex if it's got 1 slash instead of 3. like "^Galaxy Watch3 \([A-F0-9]{4}\)$
# that leads to failure to match on values from the NAMEPRINT_DB.csv, even when something could have been looked up by the nameregex

def find_nameprint_match(name_string):
    for key, value in TME.TME_glob.nameprint_data.items():
        #regex_pattern = key
        # Compensate for difference in how MySQL regex requires three \ to escape ( whereas python only requires one
        regex_pattern = key.replace('\\\\\\', '\\')
        #qprint(f"regex_pattern = {regex_pattern}")
        if re.search(regex_pattern, name_string):
            qprint(f"\t\t\tNamePrint: match found for {key}: {value}")

##################################################################################
# Appearance (This is in here because it comes up in both advertisements and GATT)
##################################################################################

def appearance_uint16_to_string(number):
    #s = ""
    subcategory_num = number & 0b111111
    category_num = number >> 6
    #qprint(f"Raw Value: 0x{number:04x}")
    #qprint(f"Category: {category_num}")
    #qprint(f"Subcategory: {subcategory_num}")

    # Initialize to defaults in case there's no match
    if(category_num == 0):
        cat_name = "Generic"
    else:
        cat_name = "Unknown"

    if(subcategory_num == 0):
        subcat_name = "Generic"
    else:
        subcat_name = "Unknown"

    for category in TME.TME_glob.appearance_yaml_data['appearance_values']:
        if category['category'] == category_num:
            #qprint(category)
            cat_name = category['name']
            if("subcategory" in category):
                for subcategory in category['subcategory']:
                    #qprint(subcategory)
                    if subcategory['value'] == subcategory_num:
                        subcat_name = subcategory['name']

    return f"(0x{number:04x}) Category ({category_num}): {cat_name}, Sub-Category ({subcategory_num}): {subcat_name}"

# Function to print appearance info
def print_appearance(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    le_query = "SELECT appearance, bdaddr_random, le_evt_type FROM LE_bdaddr_to_appearance WHERE bdaddr = %s" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query, values)

    if (len(le_result) == 0):
        vprint("\tNo Appearance data found.")
        return

    for appearance, random, le_evt_type in le_result:
        # Export BTIDES data first
        appearance_hex_str = f"{appearance:04x}"
        length = 3 # 1 byte for opcode + 2 bytes for Appearance
        data = {"length": length, "appearance_hex_str": appearance_hex_str}
        BTIDES_export_AdvData(bdaddr, random, le_evt_type, type_AdvData_Appearance, data)

        # Then human UI output
        qprint(f"\tAppearance: {appearance_uint16_to_string(appearance)}")
        vprint(f"\t\tIn BLE Data (DB:LE_bdaddr_to_appearance), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        qprint(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

##################################################################################
# UUID128s  (This is in here because it comes up in both advertisements and GATT)
##################################################################################

def get_custom_uuid128_string(uuid128):
    global bt_member_UUID16_as_UUID128_to_names
    uuid128.strip().lower()
    uuid128_no_dash = uuid128.replace('-','')

    if(uuid128_no_dash in TME.TME_glob.clues.keys()):
        entry = TME.TME_glob.clues[uuid128_no_dash]
        if('UUID_name' in entry):
            name = entry['UUID_name']
        else:
            name = "Unknown"
        colored_str = Fore.CYAN + Style.BRIGHT + f"Custom UUID128: company: {entry['company']}, name: {name}" + Style.RESET_ALL
        return colored_str
    elif(uuid128_no_dash in TME.TME_glob.bt_member_UUID16_as_UUID128_to_names.keys()):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company UUID128: {TME.TME_glob.bt_member_UUID16_as_UUID128_to_names[uuid128_no_dash]}" + Style.RESET_ALL
        return colored_str
    else:
        for UUID_regex in TME.TME_glob.clues_regexed.keys():
            replaced_UUID_regex = UUID_regex.replace('-','').replace('x','[0-9a-fA-F]')
            if re.match(replaced_UUID_regex, uuid128_no_dash):
                entry = TME.TME_glob.clues_regexed[UUID_regex]
                if('UUID_name' in entry):
                    name = entry['UUID_name']
                else:
                    name = "Unknown"
                colored_str = Fore.CYAN + Style.BRIGHT + f"Custom UUID128: company: {entry['company']}, name: {name}" + Style.RESET_ALL
                return colored_str

    # TODO: Add lookup in Metadata_v2

    colored_str = Fore.RED + Style.BRIGHT + f"Unknown UUID128" + Style.RESET_ALL
    return colored_str

################################################################################
# Class of Device (This is in here because it comes up in both BLE and BTC)
################################################################################

def print_CoD_to_names(number):
    global CoD_yaml_data
    for i in range (13,24):
        if(number & (1 << i)):
            for entry in TME.TME_glob.CoD_yaml_data['cod_services']:
                if (entry['bit'] == i):
                    qprint(f"\t\t\tCoD Major Service (bit {i}): {entry['name']}")

    major_device_class = ((number >> 8) & 0x1F)
    #qprint(major_device_class)
    minor_device_class = ((number >> 2) & 0x3F)
    #qprint(minor_device_class)

    for entry in TME.TME_glob.CoD_yaml_data['cod_device_class']:
        if(entry['major'] == major_device_class):
            qprint(f"\t\t\tCoD Major Device Class ({major_device_class}): {entry['name']}")
            if 'minor' in entry:
                # Apparently, though it's not spelled out well in the Assigned Numbers document,
                # If there's a "subsplit" entry in the yaml, it means to take that many upper bits
                # of the minor number, and treat the upper bits as the 'minor' number,
                # and the lower bits as the 'subminor' number
                if 'subsplit' in entry:
                    upper_bits = entry['subsplit']
                    #qprint(upper_bits)
                    lower_bits = 6 - upper_bits
                    subminor_num = minor_device_class & ((2**lower_bits)-1)
                    #qprint(subminor_num)
                    minor_num = (minor_device_class >> lower_bits) & ((2**upper_bits)-1)
                    #qprint(minor_num)
                    for minor_entry in entry['minor']:
                        if(minor_entry['value'] == minor_num):
                            qprint(f"\t\t\tCoD Minor Device Class ({minor_num}): {minor_entry['name']}")
                    for subminor_entry in entry['subminor']:
                        if(subminor_entry['value'] == subminor_num):
                            qprint(f"\t\t\tCoD SubMinor Device Class ({subminor_num}): {subminor_entry['name']}")
                else:
                    for minor_entry in entry['minor']:
                        if(minor_entry['value'] == minor_device_class):
                            qprint(f"\t\t\tCoD Minor Device Class ({minor_device_class}): {minor_entry['name']}")
            # Sigh, and imaging, and only imaging, needs to be handled differently...
            if 'minor_bits' in entry:
                for bitsentry in entry['minor_bits']:
                    if(minor_device_class & (1 << (bitsentry['value']-2))): # -2 because I already shifted minor_device_class by 2
                            qprint(f"\t\t\tCoD Minor Device Class (bit {bitsentry['value']} set): {bitsentry['name']}")


def print_class_of_device(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    eir_query = "SELECT class_of_device FROM EIR_bdaddr_to_CoD WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)

    le_query = "SELECT bdaddr_random, le_evt_type, class_of_device FROM LE_bdaddr_to_CoD WHERE bdaddr = %s"
    le_result = execute_query(le_query, values)

    if (len(eir_result)== 0 and len(le_result) == 0):
        vprint("\tNo Class of Device Data found.")
        return
    else:
        qprint("\tClass of Device Data:")

    for (class_of_device,) in eir_result:
        # Export BTIDES data first
        CoD_hex_str = f"{class_of_device:06x}"
        length = 4 # 1 byte for opcode + 3 bytes for CoD
        data = {"length": length, "CoD_hex_str": CoD_hex_str}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_ClassOfDevice, data)

        # Then human UI output
        qprint(f"\t\tClass of Device: 0x{class_of_device:04x}")
        print_CoD_to_names(class_of_device)
        qprint(f"\t\tIn BT Classic Data (DB:EIR_bdaddr_to_CoD)")

    for bdaddr_random, le_evt_type, class_of_device in le_result:
        # Export BTIDES data first
        CoD_hex_str = f"{class_of_device:06x}"
        length = 4 # 1 byte for opcode + 3 bytes for CoD
        data = {"length": length, "CoD_hex_str": CoD_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_ClassOfDevice, data)

        # Then human UI output
        qprint(f"\t\tClass of Device: 0x{class_of_device:04x}")
        print_CoD_to_names(class_of_device)
        vprint(f"\t\tIn BLE Data (DB:LE_bdaddr_to_CoD), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        #DELETEME? Copy/paste error? - find_nameprint_match(name)
        qprint(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

################################################################################
# Device Name (This is in here because it comes up in both BLE and BTC)
################################################################################

# Function to print device names from different tables
# NOTE: This is sort of more like "advertised names", except that it also contains SCAN_RSP names too. But we don't want to print out GATT names here, as we'll print them in GATT section
def print_device_names(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    # Query for EIR_bdaddr_to_name table
    eir_query = "SELECT device_name_type, name_hex_str FROM EIR_bdaddr_to_name WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)
    # Query for HCI_bdaddr_to_name table
    hci_query = "SELECT name_hex_str FROM HCI_bdaddr_to_name WHERE bdaddr = %s"
    hci_result = execute_query(hci_query, values)
    # Query for LE_bdaddr_to_name table
    le_query = "SELECT bdaddr_random, le_evt_type, device_name_type, name_hex_str FROM LE_bdaddr_to_name WHERE bdaddr = %s" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query, values)

    if(len(eir_result) == 0 and len(hci_result) == 0 and len(le_result)== 0):
        vprint("\tNo Names found.")
        return

    name_type_translation = {
        0x08: "Shortened Name",
        0x09: "Complete Name",
        0x30: "Broadcast Name",
    }

    for device_name_type, name_hex_str in eir_result:
        device_name = get_utf8_string_from_hex_string(name_hex_str)
        color_name = Fore.MAGENTA + Style.BRIGHT + f"{device_name}"
        qprint(f"\tDeviceName: {color_name}")
        qprint(f"\tDeviceNameType: {name_type_translation[device_name_type]}")
        qprint(f"\t\tIn BT Classic Data (DB:EIR_bdaddr_to_name)")
        find_nameprint_match(device_name)

        length = 1 + int(len(name_hex_str)/2) # 1 bytes for opcode + length of the string
        data = {"length": length, "utf8_name": device_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(bdaddr, 0, 50, device_name_type, data)

    for name_hex_str, in hci_result:
        device_name = get_utf8_string_from_hex_string(name_hex_str)
        color_name = Fore.MAGENTA + Style.BRIGHT + f"{device_name}"
        qprint(f"\tDeviceName: {color_name}")
        qprint("\t\tIn BT Classic Data (DB:HCI_bdaddr_to_name)")
        find_nameprint_match(device_name)
        remote_name_hex_str = device_name.encode('utf-8').hex()
        BTIDES_export_HCI_Name_Response(bdaddr, remote_name_hex_str)

    for bdaddr_random, le_evt_type, device_name_type, name_hex_str in le_result:
        device_name = get_utf8_string_from_hex_string(name_hex_str)
        color_name = Fore.MAGENTA + Style.BRIGHT + f"{device_name}"
        qprint(f"\tDeviceName: {color_name}")
        qprint(f"\tDeviceNameType: {name_type_translation[device_name_type]}")
        vprint(f"\t\tIn BLE Data (DB:LE_bdaddr_to_name), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        find_nameprint_match(device_name)
        qprint(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

        length = 1 + int(len(name_hex_str)/2) # 1 bytes for opcode + length of the string
        data = {"length": length, "utf8_name": device_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, device_name_type, data)

    qprint("")

def get_uuid16_gatt_service_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT services
    return TME.TME_glob.gatt_services_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def get_uuid16_gatt_declaration_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT declarations
    return TME.TME_glob.gatt_declarations_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def get_uuid16_gatt_descriptor_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT descriptors
    return TME.TME_glob.gatt_descriptors_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

def get_uuid16_gatt_characteristic_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT characteristic
    return TME.TME_glob.gatt_characteristic_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")


def colored_print_name_for_UUID16(uuid16):
    service_by_uuid16 = get_uuid16_service_string(uuid16)
    gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
    protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
    company_by_uuid16 = get_company_by_uuid16(uuid16)
    custom_by_uuid16 = get_custom_by_uuid16(uuid16)
    if(service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Service ID: {service_by_uuid16}" + Style.RESET_ALL
        qprint(f"\t\tUUID16 {uuid16} ({colored_str})")
        return colored_str
    elif(gatt_service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"GATT Service ID: {gatt_service_by_uuid16}" + Style.RESET_ALL
        qprint(f"\t\tUUID16 {uuid16} ({colored_str})")
        return colored_str
    elif(protocol_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Protocol ID: {protocol_by_uuid16}" + Style.RESET_ALL
        qprint(f"\t\tUUID16 {uuid16} ({colored_str})")
        return colored_str
    elif(custom_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company-specific Service UUID: {custom_by_uuid16}" + Style.RESET_ALL
        qprint(f"\t\tUUID16 {uuid16} ({colored_str})")
        return colored_str
    elif(company_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company ID: {company_by_uuid16}" + Style.RESET_ALL
        return colored_str
        qprint(f"\t\tUUID16 {uuid16} ({colored_str})")
    else:
        qprint(f"\t\tUUID16 {uuid16} (No matches)")
        return f"\t\tUUID16 {uuid16} (No matches)"

def return_name_for_UUID16(uuid16):
    service_by_uuid16 = get_uuid16_service_string(uuid16)
    gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
    protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
    company_by_uuid16 = get_company_by_uuid16(uuid16)
    custom_by_uuid16 = get_custom_by_uuid16(uuid16)
    if(service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Service ID: {service_by_uuid16}" + Style.RESET_ALL
        return colored_str
    elif(gatt_service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"GATT Service ID: {gatt_service_by_uuid16}" + Style.RESET_ALL
        return colored_str
    elif(protocol_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Protocol ID: {protocol_by_uuid16}" + Style.RESET_ALL
        return colored_str
    elif(custom_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company-specific Service UUID: {custom_by_uuid16}" + Style.RESET_ALL
        return colored_str
    elif(company_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company ID: {company_by_uuid16}" + Style.RESET_ALL
        return colored_str
    else:
        return f"No matches"