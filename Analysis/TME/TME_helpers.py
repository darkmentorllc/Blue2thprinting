########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import mysql.connector
import re
import TME.TME_glob

########################################
# MYSQL specific
########################################

# Function to execute a MySQL query and fetch results
def execute_query(query):
    connection = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database='bt',
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password'
    )

    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    cursor.close()
    connection.close()
    return result

########################################
# Helpers
########################################

# Use the UUID16 names mapping to get the protocol ID
def get_uuid16_protocol_string(uuid16):
    return TME.TME_glob.uuid16_protocol_names.get(int(uuid16.strip(),16), "Unknown")

# Use the UUID16 names mapping to get the service ID
def get_uuid16_service_string(uuid16):
    return TME.TME_glob.uuid16_service_names.get(int(uuid16.strip(),16), "Unknown")

def get_bt_spec_version_numbers_to_names(number):
    return TME.TME_glob.bt_spec_version_numbers_to_names.get(number, "Unknown")

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
    query = f"""
    SELECT 1 AS bdaddr
    FROM EIR_bdaddr_to_DevID
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_flags
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_MSD
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_name
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_PSRM_CoD
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_tx_power
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID128s
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID16s
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID32s
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM EIR_bdaddr_to_UUID32s
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM BTC2th_LMP_features_res
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM BTC2th_LMP_name_res
    WHERE device_bdaddr = '{bdaddr}'
    UNION
    SELECT 1
    FROM BTC2th_LMP_version_res
    WHERE device_bdaddr = '{bdaddr}';
    """
    result = execute_query(query)
    #print(result)
    if(len(result) > 0):
        for (bdaddr_result,) in result:
            if(bdaddr_result):
                return True

    '''
    # NOTE: Temporarily disabled, because this adds something like 5 seconds to this function and slows down the entire code. We need to find a better way to do this (since I had even noticed the slowdown after I added)
    # Check if this BDADDR appears in Microsoft Swift Pair MSD - https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair
    bdaddr_little_endian_str = f"{bdaddr[15:17]}{bdaddr[12:14]}{bdaddr[9:11]}{bdaddr[6:8]}{bdaddr[3:5]}{bdaddr[0:2]}"
    query = f"SELECT id FROM LE_bdaddr_to_MSD where device_BT_CID = 0006 AND manufacturer_specific_data REGEXP '^030180{bdaddr_little_endian_str}';"
    result = execute_query(query)
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
    query = f"""
    SELECT 1
    FROM LE_bdaddr_to_appearance
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_CoD
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_connect_interval
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_flags
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_MSD
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_name2
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_other_le_bdaddr
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_public_target_bdaddr
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_tx_power
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_URI
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID128_service_solicit
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID128s
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID16_service_solicit
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID16s
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM LE_bdaddr_to_UUID32s
    WHERE device_bdaddr = '{bdaddr}' and bdaddr_random = 1
    UNION
    SELECT 1
    FROM BLE2th_LL_FEATUREs
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM BLE2th_LL_LENGTHs
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM BLE2th_LL_PHYs
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM BLE2th_LL_PING_RSP
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM BLE2th_LL_UNKNOWN_RSP
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM BLE2th_LL_VERSION_IND
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM GATT_characteristics
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM GATT_characteristics_values
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM GATT_attribute_handles
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1
    UNION
    SELECT 1
    FROM GATT_services
    WHERE device_bdaddr = '{bdaddr}' and device_bdaddr_type = 1;
    """

    result = execute_query(query)
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
            print("Error encounter in get_bdaddr_type for {bdaddr}. Debug.")
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
def get_company_by_uuid16(uuid16):
    company_query = f"SELECT company_name FROM UUID16_to_company WHERE str_UUID16_CID = '{uuid16.strip()}'"
    result = execute_query(company_query)
    return result[0][0] if result else "Unknown"

# Look up company name based on 16-bit BT Company ID (CID)
def BT_CID_to_company_name(device_BT_CID):
    s = "No Match"
    if(device_BT_CID in TME.TME_glob.bt_CID_to_names):
        s = TME.TME_glob.bt_CID_to_names[device_BT_CID]
##    query = f"SELECT device_BT_CID, company_name FROM BT_CID_to_company WHERE device_BT_CID = '{device_BT_CID}'"
##    result = execute_query(query)
##    for device_BT_CID, company_name in result:
##        s = f"{company_name}"

    return s

# Look up company name based on 16-bit USB Company ID (CID) (Sometimes BT uses these IDs if a flag says to)
def USB_CID_to_company_name(device_USB_CID):
    s = "No Match"
    query = f"SELECT device_USB_CID, company_name FROM USB_CID_to_company WHERE device_USB_CID = '{device_USB_CID}'"
    result = execute_query(query)
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
        print(f"{indent}Company Name by IEEE OUI: Not Applicable because this is a {get_bdaddr_type(bdaddr, random)} address")
    else:
        # Query the database for the company_name based on the first 3 octets
        query = f"SELECT company_name FROM IEEE_bdaddr_to_company WHERE device_bdaddr LIKE '{first_three_octets}%'"
        result = execute_query(query)

        if result:
            print(f"{indent}Company Name by IEEE OUI ({bdaddr[:8]}): {result[0][0]}")
            if(first_three_octets == "00:00:00"):
                print(f"{indent}\tNOTE: Most BDADDR that begin with 00:00:00 are erroneous, not actual XEROX devices!")
        else:
            print(f"{indent}Company Name by IEEE OUI ({bdaddr[:8]}): No Match")

        if(print_type):
            if(is_classic):
                print(f"{indent}\tBDADDR is Bluetooth Classic")
            else:
                print(f"{indent}\tBDADDR is Bluetooth Low Energy Public")

    print("")

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
        #print(f"regex_pattern = {regex_pattern}")
        if re.search(regex_pattern, name_string):
            print(f"\t\t\tNamePrint: match found for {key}: {value}")

##################################################################################
# Appearance (This is in here because it comes up in both advertisements and GATT)
##################################################################################

def appearance_uint16_to_string(number):
    #s = ""
    subcategory_num = number & 0b111111
    category_num = number >> 6
    #print(f"Raw Value: 0x{number:04x}")
    #print(f"Category: {category_num}")
    #print(f"Subcategory: {subcategory_num}")

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
            #print(category)
            cat_name = category['name']
            if("subcategory" in category):
                for subcategory in category['subcategory']:
                    #print(subcategory)
                    if subcategory['value'] == subcategory_num:
                        subcat_name = subcategory['name']
        
    return f"(0x{number:04x}) Category ({category_num}): {cat_name}, Sub-Category ({subcategory_num}): {subcat_name}"

# Function to print appearance info
def print_appearance(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    #le_query = f"SELECT appearance, bdaddr_random, le_evt_type FROM LE_bdaddr_to_appearance WHERE device_bdaddr = '{bdaddr}' AND bdaddr_random = {nametype} "
    le_query = f"SELECT appearance, bdaddr_random, le_evt_type FROM LE_bdaddr_to_appearance WHERE device_bdaddr = '{bdaddr}'" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query)
    for appearance, random, le_evt_type in le_result:
        print(f"\tAppearance: {appearance_uint16_to_string(appearance)}")
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_appearance), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if (len(le_result) == 0):
        print("\tNo Appearance data found.")

    print("")
    
##################################################################################
# UUID128s  (This is in here because it comes up in both advertisements and GATT)
##################################################################################

def get_custom_uuid128_string(uuid128):
    global bt_member_UUID16_as_UUID128_to_names
    uuid128.strip().lower()
    uuid128_no_dash = uuid128.replace('-','')

    if(uuid128_no_dash in TME.TME_glob.custom_uuid128_hash.keys()):
        return f"Custom UUID128: {TME.TME_glob.custom_uuid128_hash[uuid128_no_dash]}"
    elif(uuid128_no_dash in TME.TME_glob.bt_member_UUID16_as_UUID128_to_names.keys()):
        return f"Company UUID128: {TME.TME_glob.bt_member_UUID16_as_UUID128_to_names[uuid128_no_dash]}"

    # TODO: Add lookup in Metadata_v2

    return f"Unknown UUID128"

################################################################################
# Class of Device (This is in here because it comes up in both BLE and BTC)
################################################################################

def print_CoD_to_names(number):
    global CoD_yaml_data
    for i in range (13,24):
        if(number & (1 << i)):
            for entry in TME.TME_glob.CoD_yaml_data['cod_services']:
                if (entry['bit'] == i):
                    print(f"\t\t\tCoD Major Service (bit {i}): {entry['name']}")

    major_device_class = ((number >> 8) & 0x1F)
    #print(major_device_class)
    minor_device_class = ((number >> 2) & 0x3F)
    #print(minor_device_class)

    for entry in TME.TME_glob.CoD_yaml_data['cod_device_class']:
        if(entry['major'] == major_device_class):
            print(f"\t\t\tCoD Major Device Class ({major_device_class}): {entry['name']}")
            if 'minor' in entry:
                # Apparently, though it's not spelled out well in the Assigned Numbers document,
                # If there's a "subsplit" entry in the yaml, it means to take that many upper bits
                # of the minor number, and treat the upper bits as the 'minor' number,
                # and the lower bits as the 'subminor' number
                if 'subsplit' in entry:
                    upper_bits = entry['subsplit']
                    #print(upper_bits)
                    lower_bits = 6 - upper_bits
                    subminor_num = minor_device_class & ((2**lower_bits)-1)
                    #print(subminor_num)
                    minor_num = (minor_device_class >> lower_bits) & ((2**upper_bits)-1)
                    #print(minor_num)
                    for minor_entry in entry['minor']:
                        if(minor_entry['value'] == minor_num):
                            print(f"\t\t\tCoD Minor Device Class ({minor_num}): {minor_entry['name']}")
                    for subminor_entry in entry['subminor']:
                        if(subminor_entry['value'] == subminor_num):
                            print(f"\t\t\tCoD SubMinor Device Class ({subminor_num}): {subminor_entry['name']}")
                else:
                    for minor_entry in entry['minor']:
                        if(minor_entry['value'] == minor_device_class):
                            print(f"\t\t\tCoD Minor Device Class ({minor_device_class}): {minor_entry['name']}")
            # Sigh, and imaging, and only imaging, needs to be handled differently...
            if 'minor_bits' in entry:
                for bitsentry in entry['minor_bits']:
                    if(minor_device_class & (1 << (bitsentry['value']-2))): # -2 because I already shifted minor_device_class by 2
                            print(f"\t\t\tCoD Minor Device Class (bit {bitsentry['value']} set): {bitsentry['name']}")


def print_class_of_device(bdaddr):
    bdaddr = bdaddr.strip().lower()

    eir_query = f"SELECT class_of_device FROM EIR_bdaddr_to_PSRM_CoD WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)

    le_query = f"SELECT bdaddr_random, le_evt_type, class_of_device FROM LE_bdaddr_to_CoD WHERE device_bdaddr = '{bdaddr}'" 
    le_result = execute_query(le_query)

    if (len(eir_result) != 0 or len(le_result) != 0):
        print("\tClass of Device Data:")

    for (class_of_device,) in eir_result:
        print(f"\t\tClass of Device: 0x{class_of_device:04x}")
        print_CoD_to_names(class_of_device)
        print(f"\t\tIn BT Classic Data (EIR_bdaddr_to_name)")

    for bdaddr_random, le_evt_type, class_of_device in le_result:
        print(f"\t\tClass of Device: 0x{class_of_device:04x}")
        print_CoD_to_names(class_of_device)
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_CoD), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        #DELETEME? Copy/paste error? - find_nameprint_match(name)
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if (len(eir_result)== 0 and len(le_result) == 0):
        print("\tNo Class of Device Data found.")

    print("")