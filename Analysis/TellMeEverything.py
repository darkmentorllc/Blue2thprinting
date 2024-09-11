#!/usr/bin/python3

########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import argparse
import mysql.connector
import json
import csv
import yaml
import re
import struct
import time

########################################
# BEGIN FILL DATA FROM JSON ############
########################################

# Load JSON data from file
json_file = './Metadata_v2.json'
with open(json_file, 'r') as f:
    metadata_v2 = json.load(f)

# Option to store private metadata in 
# this file. It will be consulted, but
# doesn't need to be checked in
json_file = './Metadata_v2_private.json'
try:
    with open(json_file, 'r') as f:
        metadata_v2.update(json.load(f))
except FileNotFoundError:
    pass

########################################
# BEGIN FILL DATA FROM CSVs ############
########################################
nameprint_data = {} 

def create_nameprint_CSV_data():
    global nameprint_data
    with open("./NAMEPRINT_DB.csv", 'r') as csvfile:
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            if len(row) >= 2:
                key = row[1].strip()
                value = row[0].strip()
                nameprint_data[key] = value

# Option to store private metadata in
# this file. It will be consulted, but
# doesn't need to be checked in
try:
    with open('./NAMEPRINT_DB_private.csv', 'r') as csvfile:
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            if len(row) >= 2:
                key = row[1].strip()
                value = row[0].strip()
                nameprint_data[key] = value
except FileNotFoundError:
    pass

custom_uuid128_hash = {} 

def create_custom_uuid128_CSV_data():
    global custom_uuid128_hash
    with open("./custom_uuid128s.csv", 'r') as csvfile:
        csv_reader = csv.reader(csvfile, quoting=csv.QUOTE_ALL)
        for row in csv_reader:
            if len(row) >= 2:
                key = row[0].strip().lower()
                value = row[1].strip()
                custom_uuid128_hash[key] = value
#                print(f"key = {key}, value = {value}")


########################################
# BEGIN FILL DATA FROM YAML ############
########################################

#########################################
# Get data from company_identifiers.yaml
#########################################
bt_CID_to_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_bt_CID_to_names():
    global bt_CID_to_names
    with open('./public/assigned_numbers/company_identifiers/company_identifiers.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['company_identifiers']:
        value = entry['value']
        name = entry['name']
        bt_CID_to_names[value] = name

    # Hack: Add in the wrong-endian Apple/Samsung values
    bt_CID_to_names[0x4C00] = "Apple, Inc. (wrong-endian)"
    bt_CID_to_names[0x7500] = "Samsung (wrong-endian)"
    bt_CID_to_names[0xff19] = "Samsung (buggy)"

#    print(bt_CID_to_names)
#    print(len(bt_CID_to_names))

#########################################
# Get data from member_uuids.yaml
#########################################
bt_member_UUID16s_to_names = {}
bt_member_UUID16_as_UUID128_to_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_bt_member_UUID16s_to_names():
    global bt_member_UUID16s_to_names
    global bt_member_UUID16_as_UUID128_to_names
    with open('./public/assigned_numbers/uuids/member_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        value = entry['uuid']
        name = entry['name']
        bt_member_UUID16s_to_names[value] = name
        uuid128_value = f"0000{value:04x}00001000800000805f9b34fb".lower()
        bt_member_UUID16_as_UUID128_to_names[uuid128_value] = name

#    print(bt_member_UUID16s_to_names)
#    print(bt_member_UUID16_as_UUID128_to_names)
#    print(len(bt_member_UUID16s_to_names))


#########################################
# Get data from class_of_device.yaml
#########################################
CoD_yaml_data = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_CoD_to_names():
    global CoD_yaml_data
    with open('./public/assigned_numbers/core/class_of_device.yaml', 'r') as file:
        CoD_yaml_data = yaml.safe_load(file)

#########################################
# Get data from core_version.yaml
#########################################
bt_spec_version_numbers_to_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_bt_spec_version_numbers_to_names():
    global bt_spec_version_numbers_to_names
    with open('./public/assigned_numbers/core/core_version.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['core_version']:
        value = entry['value']
        name = entry['name']
        bt_spec_version_numbers_to_names[value] = name

    #print(bt_spec_version_numbers_to_names)

def get_bt_spec_version_numbers_to_names(number):
    return bt_spec_version_numbers_to_names.get(number, "Unknown")

#########################################
# Get data from appearance_values.yaml
#########################################
appearance_yaml_data = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_appearance_yaml_data():
    global appearance_yaml_data
    with open('./public/assigned_numbers/core/appearance_values.yaml', 'r') as file:
        appearance_yaml_data = yaml.safe_load(file)


#########################################
# Get data from service_uuids.yaml
#########################################
gatt_services_uuid16_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_gatt_services_uuid16_names():
    global gatt_services_uuid16_names
    with open('./public/assigned_numbers/uuids/service_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)
    
    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        gatt_services_uuid16_names[uuid] = name

    #print(gatt_services_uuid16_names)

def get_uuid16_gatt_service_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT services
    return gatt_services_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

#########################################
# Get data from declarations.yaml
#########################################
gatt_declarations_uuid16_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_gatt_declarations_uuid16_names():
    global gatt_declarations_uuid16_names
    with open('./public/assigned_numbers/uuids/declarations.yaml', 'r') as file:
        data = yaml.safe_load(file)
    
    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        gatt_declarations_uuid16_names[uuid] = name

    #print(gatt_declarations_uuid16_names)

def get_uuid16_gatt_declaration_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT declarations
    return gatt_declarations_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

#########################################
# Get data from descriptors.yaml
#########################################
gatt_descriptors_uuid16_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_gatt_descriptors_uuid16_names():
    global gatt_descriptors_uuid16_names
    with open('./public/assigned_numbers/uuids/descriptors.yaml', 'r') as file:
        data = yaml.safe_load(file)
    
    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        gatt_descriptors_uuid16_names[uuid] = name

    #print(gatt_descriptors_uuid16_names)

def get_uuid16_gatt_descriptor_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT descriptors
    return gatt_descriptors_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

#########################################
# Get data from characteristic_uuids.yaml
#########################################
gatt_characteristic_uuid16_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_gatt_characteristic_uuid16_names():
    global gatt_characteristic_uuid16_names
    with open('./public/assigned_numbers/uuids/characteristic_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)
    
    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        gatt_characteristic_uuid16_names[uuid] = name

    #print(gatt_characteristic_uuid16_names)

def get_uuid16_gatt_characteristic_string(uuid16):
    # Use the UUID16 names mapping to get the name for a GATT characteristic
    return gatt_characteristic_uuid16_names.get(int(uuid16.strip(), 16), "Unknown")

#########################################
# Get data from protocol_identifiers.yaml
#########################################
uuid16_protocol_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_uuid16_protocol_names():
    global uuid16_protocol_names
    with open('./public/assigned_numbers/uuids/protocol_identifiers.yaml', 'r') as file:
        data = yaml.safe_load(file)
    
    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        uuid16_protocol_names[uuid] = name

    #print(uuid16_protocol_names)

def get_uuid16_protocol_string(uuid16):
    # Use the UUID16 names mapping to get the protocol ID
    return uuid16_protocol_names.get(int(uuid16.strip(),16), "Unknown")

#########################################
# Get data from service_class.yaml
#########################################
# Global dictionary to store uuid16 to service name mappings
uuid16_service_names = {}

# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def create_uuid16_service_names():
    global uuid16_service_names
    with open('./public/assigned_numbers/uuids/service_class.yaml', 'r') as file:
        data = yaml.safe_load(file)
    
    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        uuid16_service_names[uuid] = name

    #print(uuid16_service_names)

def get_uuid16_service_string(uuid16):
    # Use the UUID16 names mapping to get the service ID
    global uuid16_service_names
    return uuid16_service_names.get(int(uuid16.strip(),16), "Unknown")

########################################
# END FILL DATA FROM YAML ##############
########################################

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

    # Query for LE_bdaddr_to_name table
    le_query = f"SELECT device_bdaddr FROM LE_bdaddr_to_name WHERE device_name REGEXP '{nameregex}'"
    le_result = execute_query(le_query)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    print(f"get_bdaddrs_by_name_regex: {len(le_result)} results found in LE_bdaddr_to_name")
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
        f"    SELECT device_bdaddr FROM LE_bdaddr_to_name WHERE bdaddr_random = 0 "
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
        f"    SELECT device_bdaddr FROM EIR_bdaddr_to_PSRM_CoD "
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
        f"    SELECT CONVERT(device_bdaddr USING utf8) FROM GATT_services "
        f") AS t "
        f"WHERE t.device_bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');"
    )

    bdaddr_result = execute_query(bdaddr_query)
    for (bdaddr,) in bdaddr_result:
        bdaddr_hash[bdaddr] = 1

    print(f"get_bdaddrs_by_bdaddr_regex: {len(bdaddr_result)} results found across all tables")
    print(f"get_bdaddrs_by_bdaddr_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def get_uuid16_stats(arg):
    seen_btc_uuid16s_hash = {}
    seen_le_uuid16s_hash = {}
    company_uuid_count = 0

    #Too lazy to change indentation in nano!
    if(1):

        ################################################
        # Get the data for BTC devices from the database
        ################################################

        eir_uuid16_query = f"SELECT str_UUID16s FROM EIR_bdaddr_to_UUID16s"
        eir_uuid16_result = execute_query(eir_uuid16_query)
        if(len(eir_uuid16_result) != 0):
            for (str_UUID16s,) in eir_uuid16_result:
                uuid16s = str_UUID16s.split(',')
                for uuid16 in uuid16s:
                    if(uuid16 in seen_btc_uuid16s_hash):
                        seen_btc_uuid16s_hash[uuid16] += 1
                    else:
                        seen_btc_uuid16s_hash[uuid16] = 1

            print("----= BLUETOOTH CLASSIC RESULTS =----")
            print(f"{len(eir_uuid16_result)} rows of data found in EIR_bdaddr_to_UUID16s")
            print(f"{len(seen_btc_uuid16s_hash)} unique UUID16s found")
#            print(seen_btc_uuid16s_hash)
            sorted_items = sorted(seen_btc_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
            print(f"count \t uuid16 \t company")
            for item in sorted_items:
                (uuid16,count) = item
#                print(bt_member_UUID16s_to_names)
#                print(item)
#                print(uuid16)
#                print(count)
                try:
                    decimal_uuid16 = int(uuid16,16)
                except ValueError:
                    if(arg != "quiet"): print(f"Skipping '{uuid16}', it can't be converted to an integer")
                    continue

                if(decimal_uuid16 in bt_member_UUID16s_to_names.keys()):
                    print(f"{count} \t {uuid16} \t {bt_member_UUID16s_to_names[int(uuid16,16)]}")
                    company_uuid_count += 1
            print(f"*** {company_uuid_count} UUID16s matched a company name ***")


            ################################################
            # Get the data for LE devices from the database
            ################################################

            le_uuid16_query = f"SELECT str_UUID16s FROM LE_bdaddr_to_UUID16s"
            le_uuid16_result = execute_query(le_uuid16_query)
            if(len(le_uuid16_result) != 0):
                for (str_UUID16s,) in le_uuid16_result:
                    if(isinstance(str_UUID16s, str)):
                        uuid16s = str_UUID16s.split(',')
                        for uuid16 in uuid16s:
                            if(uuid16 in seen_le_uuid16s_hash):
                                seen_le_uuid16s_hash[uuid16] += 1
                            else:
                               seen_le_uuid16s_hash[uuid16] = 1

            company_uuid_count = 0
            print()
            print("----= BLUETOOTH LOW ENERGY RESULTS =----")
            print(f"{len(le_uuid16_result)} rows of data found in LE_bdaddr_to_UUID16s")
            print(f"{len(seen_le_uuid16s_hash)} unique UUID16s found")
#            print(seen_le_uuid16s_hash)
            sorted_items = sorted(seen_le_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
            print(f"count \t uuid16 \t company")
            for item in sorted_items:
                (uuid16,count) = item
#                print(bt_member_UUID16s_to_names)
#                print(item)
#                print(uuid16)
#                print(count)
                try:
                    decimal_uuid16 = int(uuid16,16)
                except ValueError:
                    if(arg != "quiet"): print(f"Skipping '{uuid16}', it can't be converted to an integer")
                    continue
                if(decimal_uuid16 in bt_member_UUID16s_to_names.keys()):
                    print(f"{count} \t {uuid16} \t {bt_member_UUID16s_to_names[int(uuid16,16)]}")
                    company_uuid_count += 1

            print(f"*** {company_uuid_count} UUID16s matched a company name ***")


def get_uuid128_stats(arg):
    seen_btc_uuid128s_hash = {}
    seen_le_uuid128s_hash = {}
    known_uuid_count = 0

    #Too lazy to change indentation in nano!
    if(1):

        ################################################
        # Get the data for BTC devices from the database
        ################################################

        eir_uuid128_query = f"SELECT str_UUID128s FROM EIR_bdaddr_to_UUID128s"
        eir_uuid128_result = execute_query(eir_uuid128_query)
        if(len(eir_uuid128_result) != 0):
            for (str_UUID128s,) in eir_uuid128_result:
                if(str_UUID128s == ''):
                    continue
                uuid128s = str_UUID128s.split(',')
                for uuid128 in uuid128s:
                    if(uuid128 in seen_btc_uuid128s_hash):
                        seen_btc_uuid128s_hash[uuid128] += 1
                    else:
                        seen_btc_uuid128s_hash[uuid128] = 1

            print("----= BLUETOOTH CLASSIC RESULTS =----")
            print(f"{len(eir_uuid128_result)} rows of data found in EIR_bdaddr_to_UUID128s")
            print(f"{len(seen_btc_uuid128s_hash)} unique UUID128s found")
#            print(seen_btc_uuid128s_hash)
            sorted_items = sorted(seen_btc_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
            print(f"count \t uuid128 \t\t\t\t known info")
            for item in sorted_items:
                (uuid128,count) = item
#                print(item)
#                print(uuid128)
#                print(count)
                if(uuid128 in custom_uuid128_hash):
                    known_info = custom_uuid128_hash[uuid128]
                    known_uuid_count += 1
                else:
                    known_info = ""

                print(f"{count} \t {uuid128} \t {known_info}")

            print(f"*** {known_uuid_count} UUID128s are in the custom_uuid128s.csv database ***")
            known_uuid_count = 0

            ################################################
            # Get the data for LE devices from the database
            ################################################

            le_uuid128_query = f"SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s"
            le_uuid128_result = execute_query(le_uuid128_query)
            if(len(le_uuid128_result) != 0):
                for (str_UUID128s,) in le_uuid128_result:
                    if(str_UUID128s == ''):
                        continue
                    if(isinstance(str_UUID128s, str)):
                        uuid128s = str_UUID128s.split(',')
                        for uuid128 in uuid128s:
                            if(uuid128 in seen_le_uuid128s_hash):
                                seen_le_uuid128s_hash[uuid128] += 1
                            else:
                               seen_le_uuid128s_hash[uuid128] = 1

            print()
            print("----= BLUETOOTH LOW ENERGY RESULTS =----")
            print(f"{len(le_uuid128_result)} rows of data found in LE_bdaddr_to_UUID128s")
            print(f"{len(seen_le_uuid128s_hash)} unique UUID128s found")
#            print(seen_le_uuid128s_hash)
            sorted_items = sorted(seen_le_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
            print(f"count \t uuid128 \t\t\t\t known info")
            for item in sorted_items:
                (uuid128,count) = item
#                print(item)
#                print(uuid128)
#                print(count)
                if(uuid128 in custom_uuid128_hash):
                    known_info = custom_uuid128_hash[uuid128]
                    known_uuid_count += 1
                else:
                    known_info = ""

                print(f"{count} \t {uuid128} \t {known_info}")

            print(f"*** {known_uuid_count} UUID128s are in the custom_uuid128s.csv database ***")


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
        for key, value in bt_CID_to_names.items():
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
        for key, value in bt_member_UUID16s_to_names.items():
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
            oui_search_query = (
                f"SELECT DISTINCT t.device_bdaddr "
                f"FROM ( "
                f"    SELECT '{prefix}' AS bdaddr_prefix "
                f") AS prefix "
                f"CROSS JOIN ( "
                f"    SELECT device_bdaddr FROM LE_bdaddr_to_appearance WHERE bdaddr_random = 0"
                f"    UNION ALL "
                f"    SELECT device_bdaddr FROM LE_bdaddr_to_CoD WHERE bdaddr_random = 0"
                f"    UNION ALL "
                f"    SELECT device_bdaddr FROM LE_bdaddr_to_connect_interval WHERE bdaddr_random = 0"
                f"    UNION ALL "
                f"    SELECT device_bdaddr FROM LE_bdaddr_to_flags WHERE bdaddr_random = 0 "
                f"    UNION ALL "
                f"    SELECT device_bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = 0 "
                f"    UNION ALL "
                f"    SELECT device_bdaddr FROM LE_bdaddr_to_name WHERE bdaddr_random = 0 "
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
                f"    SELECT device_bdaddr FROM EIR_bdaddr_to_PSRM_CoD "
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
                f"    SELECT CONVERT(device_bdaddr USING utf8) FROM GATT_services "
                f") AS t "
                f"WHERE t.device_bdaddr LIKE CONCAT(prefix.bdaddr_prefix, '%');"
            )

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

    gatt_service_query = f"SELECT device_bdaddr FROM GATT_services WHERE UUID128 REGEXP '{uuid128regex}'"
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

        gatt_service_query = f"SELECT device_bdaddr FROM GATT_services WHERE UUID128 REGEXP '{uuid128regex_with_dashes}'"
        gatt_service_result = execute_query(gatt_service_query)
        for (bdaddr,) in gatt_service_result:
            bdaddr_hash[bdaddr] = 1
        print(f"get_bdaddrs_by_uuid128_regex: {len(gatt_service_result)} results found in GATT_services by adding dashes to regex")
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

# Function to get the company name by UUID16 from UUID16_to_company table
def get_company_by_uuid16(uuid16):
    company_query = f"SELECT company_name FROM UUID16_to_company WHERE str_UUID16_CID = '{uuid16.strip()}'"
    result = execute_query(company_query)
    return result[0][0] if result else "Unknown"

# Look up company name based on 16-bit BT Company ID (CID)
def BT_CID_to_company_name(device_BT_CID):
    str = "No Match"
    if(device_BT_CID in bt_CID_to_names):
        str = bt_CID_to_names[device_BT_CID]
##    query = f"SELECT device_BT_CID, company_name FROM BT_CID_to_company WHERE device_BT_CID = '{device_BT_CID}'"
##    result = execute_query(query)
##    for device_BT_CID, company_name in result:
##        str = f"{company_name}"

    return str

# Look up company name based on 16-bit USB Company ID (CID) (Sometimes BT uses these IDs if a flag says to)
def USB_CID_to_company_name(device_USB_CID):
    str = "No Match"
    query = f"SELECT device_USB_CID, company_name FROM USB_CID_to_company WHERE device_USB_CID = '{device_USB_CID}'"
    result = execute_query(query)
    for device_USB_CID, company_name in result:
        str = f"{company_name}"

    return str

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


########################################
# Appearance
########################################

def appearance_uint16_to_string(number):
    str = ""
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

    for category in appearance_yaml_data['appearance_values']:
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

########################################
# Transmit Power
########################################

def print_transmit_power(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    eir_query = f"SELECT device_tx_power FROM EIR_bdaddr_to_tx_power WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    for name in eir_result:
        print(f"\tTransmit Power: {name[0]}dB")
        print(f"\t\tIn BT Classic Data (EIR_bdaddr_to_tx_power)")

#    le_query = f"SELECT device_tx_power, bdaddr_random, le_evt_type FROM LE_bdaddr_to_tx_power WHERE device_bdaddr = '{bdaddr}' AND bdaddr_random = {nametype}"
    le_query = f"SELECT device_tx_power, bdaddr_random, le_evt_type FROM LE_bdaddr_to_tx_power WHERE device_bdaddr = '{bdaddr}'" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query)
    for device_tx_power, random, le_evt_type in le_result:
        print(f"\tTransmit Power: {device_tx_power}dB")
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_tx_power), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if (len(eir_result)== 0 and len(le_result) == 0):
        print("\tNo transmit power found.")

    print("")

########################################
# Manufacturer-specific Data
########################################

# Data format from https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair
def extract_ms_msd_name(manufacturer_specific_data):
    if(manufacturer_specific_data[0:6] == "030080" and len(manufacturer_specific_data) >= 8): # (need at least 8 hex digits for there to be 1 hex digit of ASCII chars)
        byte_data = bytes.fromhex(manufacturer_specific_data[6:])
        utf8_string = byte_data.decode('utf-8')
    if(manufacturer_specific_data[0:6] == "030280" and len(manufacturer_specific_data) >= 14): # ditto ^^^ 14
        byte_data = bytes.fromhex(manufacturer_specific_data[12:])
        utf8_string = byte_data.decode('utf-8')
    if(manufacturer_specific_data[0:6] == "030180" and len(manufacturer_specific_data) >= 26): # ditto ^^^ 26
        byte_data = bytes.fromhex(manufacturer_specific_data[24:])
        utf8_string = byte_data.decode('utf-8')

    if(len(utf8_string) > 0):
        return utf8_string
    else:
        return "No name found"

def print_manufacturer_data(bdaddr):
    bdaddr = bdaddr.strip().lower()

    eir_query = f"SELECT device_BT_CID, manufacturer_specific_data FROM EIR_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    le_query = f"SELECT le_evt_type, bdaddr_random, device_BT_CID, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}'"
    le_result = execute_query(le_query)

    if (len(eir_result) != 0 or len(le_result) != 0):
        print("\tManufacturer-specific Data:")

    for device_BT_CID, manufacturer_specific_data in eir_result:
        print(f"\t\tDevice Company ID: 0x%04x (%s) - take with a grain of salt, not all companies populate this accurately!" % (device_BT_CID, BT_CID_to_company_name(device_BT_CID)))
        flipped_endian = (device_BT_CID & 0xFF) << 8 | (device_BT_CID >> 8)
        print(f"\t\t\t Endianness-flipped device company ID (in case the vendor used the wrong endianness): 0x%04x (%s)" % (flipped_endian, BT_CID_to_company_name(flipped_endian)))
        print(f"\t\tRaw Data: {manufacturer_specific_data}")
        # TODO: DELETEME? I don't think there can be BT classic iBeacons can there?
        if({BT_CID_to_company_name(device_BT_CID)} == "Apple, Inc." and manufacturer_specific_data[0:3] == "0215"):
            print(f"\t\tApple iBeacon:")
        print(f"\t\t\tIn BT Classic Data (EIR_bdaddr_to_MSD)")

    for le_evt_type, bdaddr_random, device_BT_CID, manufacturer_specific_data in le_result:
        print(f"\t\tDevice Company ID: 0x%04x (%s) - take with a grain of salt, not all companies populate this accurately!" % (device_BT_CID, BT_CID_to_company_name(device_BT_CID)))
        flipped_endian = (device_BT_CID & 0xFF) << 8 | (device_BT_CID >> 8)
        print(f"\t\t\t Endianness-flipped device company ID (in case the vendor used the wrong endianness): 0x%04x (%s)" % (flipped_endian, BT_CID_to_company_name(flipped_endian)))
        print(f"\t\tRaw Data: {manufacturer_specific_data}")

        # Print Apple iBeacon information
        if(device_BT_CID == 76 and manufacturer_specific_data[0:4] == "0215"):
            print(f"\t\tApple iBeacon:")
            UUID128 = f"{manufacturer_specific_data[4:12]}-{manufacturer_specific_data[12:16]}-{manufacturer_specific_data[16:20]}-{manufacturer_specific_data[20:24]}-{manufacturer_specific_data[24:36]}"
            major = f"{manufacturer_specific_data[36:40]}"
            minor = f"{manufacturer_specific_data[40:44]}"
            rssi = f"{manufacturer_specific_data[44:46]}"
            print(f"\t\t\tUUID128: {UUID128}")
            print(f"\t\t\tMajor ID: {major}")
            print(f"\t\t\tMinor ID: {minor}")
            signed_rssi = int(rssi, 16)
            if(signed_rssi & 0x80):
                signed_rssi -= 256
            print(f"\t\t\tRSSI at 1 meter: {signed_rssi}dBm")

        elif(device_BT_CID == 6):
            # Print Microsoft Swift Pair information (format from https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair)
            if(manufacturer_specific_data[0:6] == "030080"): # "Pairing over LE only"
                print(f"\t\tMicrosoft Swift Pair - \"Pairing over LE only\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                print(f"\t\t\tDisplayName = {utf8_string}")
            if(manufacturer_specific_data[0:6] == "030280"): # "Pairing over LE and BR/EDR with Secure Connections"
                print(f"\t\tMicrosoft Swift Pair - \"Pairing over LE and BR/EDR with Secure Connections\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                print(f"\t\t\tDisplayName = {utf8_string}")
                CoD_bytes = bytes.fromhex(manufacturer_specific_data[6:12])
                big_endian_integer_CoD = struct.unpack('>I', b'\x00' + CoD_bytes)[0]
                print_CoD_to_names(big_endian_integer_CoD)
            if(manufacturer_specific_data[0:6] == "030180"): # "Pairing over BR/EDR only, using Bluetooth LE for discovery"
                print(f"\t\tMicrosoft Swift Pair - \"Pairing over BR/EDR only, using Bluetooth LE for discovery\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                print(f"\t\t\tDisplayName = {utf8_string}")
                CoD_bytes = bytes.fromhex(manufacturer_specific_data[18:24])
                big_endian_integer_CoD = struct.unpack('>I', b'\x00' + CoD_bytes)[0]
                print_CoD_to_names(big_endian_integer_CoD)
                BTC_BDADDR_bytes = bytes.fromhex(manufacturer_specific_data[6:18])
                BTC_BDADDR_str = f"{BTC_BDADDR_bytes[5]:02x}:{BTC_BDADDR_bytes[4]:02x}:{BTC_BDADDR_bytes[3]:02x}:{BTC_BDADDR_bytes[2]:02x}:{BTC_BDADDR_bytes[1]:02x}:{BTC_BDADDR_bytes[0]:02x}"
                print(f"\t\t\tBluetooth Classic BDADDR embedded in MSD = {BTC_BDADDR_str}")
                print_company_name_from_bdaddr("\t\t\t\t", BTC_BDADDR_str, False)
            # Print other Microsoft beacon information (format from https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cdp/77b446d0-8cea-4821-ad21-fabdf4d9a569)
            if(manufacturer_specific_data[0:2] == "01"):
                print(f"\t\tMicrosoft Beacon:")
                device_types = {
                    1: "Xbox One",
                    6: "Apple iPhone",
                    7: "Apple iPad",
                    8: "Android device",
                    9: "Windows 10 Desktop",
                    11: "Windows 10 Phone",
                    12: "Linux device",
                    13: "Windows IoT",
                    14: "Surface Hub",
                    15: "Windows laptop",
                    16: "Windows tablet"
                }
                device_type = int(manufacturer_specific_data[2:4], 16)
                device_type = device_type & 0x1f # It's technically only the bottom 5 bits, though no one (including Microsoft) seems to set the upper 3 bits to 001 like the spec says they should
                print(f"\t\t\tDevice Type = {device_types[device_type]}")
                Version_and_Flags = int(manufacturer_specific_data[4:6], 16)
                if(Version_and_Flags == 0x20):
                    share_state = "only my devices"
                elif(Version_and_Flags == 0x21):
                    share_state = "everyone"
                else:
                    share_state = "Unknown value: check for specification update!"
                print(f"\t\t\tNearBy share set to: {share_state}")
                # The values observed in the wild for Flags_and_Device_Status only make sense if you assume the MS spec has the bit ordering reversed and bit 0 is right-most not left-most
                Flags_and_Device_Status = int(manufacturer_specific_data[6:8], 16)
                Bluetooth_Address_As_Device_ID = True if((Flags_and_Device_Status >> 5) & 1) else False
                print(f"\t\t\tBluetooth address can be used as the device ID?: {Bluetooth_Address_As_Device_ID}")
                ExtendedDeviceStatus = Flags_and_Device_Status & 0xf
                # per spec "Values may be ORed"
                if(ExtendedDeviceStatus & 0x1):
                    print(f"\t\t\tExtended Status: Hosted by remote session")
                if(ExtendedDeviceStatus & 0x2):
                    print(f"\t\t\tExtended Status: The device does not have session hosting status available")
                if(ExtendedDeviceStatus & 0x4):
                    print(f"\t\t\tExtended Status: The device supports NearShare if the user is the same for the other device")
                if(ExtendedDeviceStatus & 0x8):
                    print(f"\t\t\tExtended Status: The device supports NearShare")
                if(ExtendedDeviceStatus == 0):
                    print(f"\t\t\tExtended Status: None")
                Salt_bytes = bytes.fromhex(manufacturer_specific_data[8:16])
                big_endian_integer_Salt = struct.unpack('<I', Salt_bytes)[0] # Salt is ostensibly stored little-endian, but without knowing a "Device Thumbprint" to calculate the Device Hash I can't be sure
                print(f"\t\t\tSalt: 0x{big_endian_integer_Salt:08x}")
                Device_Hash_bytes = bytes.fromhex(manufacturer_specific_data[16:])
                print(f"\t\t\tDevice Hash: {manufacturer_specific_data[16:]}")
                # Non-spec interpretation based on observed data: I see 2 bytes and then a string
                # This seems to only occur if(ExtendedDeviceStatus & 0x8). Found some if(ExtendedDeviceStatus & 0x4), data and confirmed it doesn't occur then
                if(ExtendedDeviceStatus & 0x8):
                    try:
                        Device_Hash_as_utf8_str = bytes.fromhex(manufacturer_specific_data[20:]).decode('utf-8')
                        print(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as possible string: {Device_Hash_as_utf8_str}")
                        Device_Hash_unknown_bytes = bytes.fromhex(manufacturer_specific_data[16:20])
                        Device_Hash_unknown_bytes_little_endian_short = struct.unpack('<H', Device_Hash_unknown_bytes)[0]
                        print(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as possible string: unknown prefix bytes interpreted as little-endian 16-bit value: 0x{Device_Hash_unknown_bytes_little_endian_short:04x}")
                    except:
                        print(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as string: does not decode")


        # TODO: Does this have the necessary information to parse Amazon MSD? https://developer.amazon.com/en-US/docs/alexa/alexa-gadgets-toolkit/bluetooth-le-settings.html
        # TODO: Parse Eddystone even though it's deprecated?

        print(f"\t\t\tIn BT LE Data (LE_bdaddr_to_MSD), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")


    if (len(eir_result)== 0 and len(le_result) == 0):
        print("\tNo Manufacturer-specific Data found.")

    print("")

########################################
# BTC EIR Device CID
########################################

def print_classic_EIR_CID_info(bdaddr):
    eir_query = f"SELECT vendor_id_source, vendor_id, product_id, product_version FROM EIR_bdaddr_to_DevID WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)

    if (len(eir_result) != 0):
        print("\tBTC Extended Inquiry Result Device info:")
    
    for vendor_id_source, vendor_id, product_id, product_version in eir_result:
        if(vendor_id_source == 1):
            print("\t\tVendor ID (BT): 0x%04x (%s)" % (vendor_id, BT_CID_to_company_name(vendor_id)))
        elif(vendor_id_source == 2):
            print("\t\tVendor ID (USB): 0x%04x (%s)" % (vendor_id, USB_CID_to_company_name(vendor_id)))
        else:
            print(f"\t\t: Error: Unknown vendor_id_source = {vendor_id_source}")
        print(f"\t\tProduct ID: 0x%04x" % product_id)
        print(f"\t\tProduct Version: 0x%04x" % product_version)

    if (len(eir_result) == 0):
        print("\tNo BTC Extended Inquiry Result Device info.")

    print("")

########################################
# Class of Device
########################################

def print_CoD_to_names(number):
    global CoD_yaml_data
    for i in range (13,24):
        if(number & (1 << i)):
            for entry in CoD_yaml_data['cod_services']:
                if (entry['bit'] == i):
                    print(f"\t\t\tCoD Major Service (bit {i}): {entry['name']}")

    major_device_class = ((number >> 8) & 0x1F)
    #print(major_device_class)
    minor_device_class = ((number >> 2) & 0x3F)
    #print(minor_device_class)

    for entry in CoD_yaml_data['cod_device_class']:
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
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_CoD), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        find_nameprint_match(name)
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if (len(eir_result)== 0 and len(le_result) == 0):
        print("\tNo Class of Device Data found.")

    print("")

########################################
# Device Name
########################################

# !!!FIXME: For devices with () in their name, like "Galaxy Watch3 (0462)", 
# the nameprint to match in MySQL needs to be "^Galaxy Watch3 \\\([A-F0-9]{4}\\\)$
# however, it only matches in Python regex if it's got 1 slash instead of 3. like "^Galaxy Watch3 \([A-F0-9]{4}\)$
# that leads to failure to match on values from the NAMEPRINT_DB.csv, even when something could have been looked up by the nameregex

def find_nameprint_match(name_string):
    global nameprint_data
    for key, value in nameprint_data.items():
        #regex_pattern = key
        # Compensate for difference in how MySQL regex requires three \ to escape ( whereas python only requires one
        regex_pattern = key.replace('\\\\\\', '\\')
        #print(f"regex_pattern = {regex_pattern}")
        if re.search(regex_pattern, name_string):
            print(f"\t\t\tNamePrint: match found for {key}: {value}")

# Function to print device names from different tables
# NOTE: This is sort of more like "advertised names", except that it also contains SCAN_RSP names too. But we don't want to print out GATT names here, as we'll print them in GATT section
def print_device_names(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    # Query for EIR_bdaddr_to_name table
    eir_query = f"SELECT device_name FROM EIR_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    for name in eir_result:
        print(f"\tDeviceName: {name[0]}")
        print(f"\t\tIn BT Classic Data (EIR_bdaddr_to_name)")
        find_nameprint_match(name[0])

    # Query for RSP_bdaddr_to_name table
    rsp_query = f"SELECT device_name FROM RSP_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'"
    rsp_result = execute_query(rsp_query)
    for name in rsp_result:
        print(f"\tDeviceName: {name[0]}")
        print("\t\tIn BT Classic Data (RSP_bdaddr_to_name)")
        find_nameprint_match(name[0])

    # Query for LE_bdaddr_to_name table
    le_query = f"SELECT device_name, bdaddr_random, le_evt_type FROM LE_bdaddr_to_name WHERE device_bdaddr = '{bdaddr}'" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query)
    for name, random, le_evt_type in le_result:
        print(f"\tDeviceName: {name}")
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_name), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        find_nameprint_match(name)
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(eir_result) == 0 and len(rsp_result) == 0 and len(le_result)== 0):
        print("\tNo Names found.")

    print("")

########################################
# UUID16s
########################################

# Function to print UUID16s for a given device_bdaddr
def print_uuid16s(device_bdaddr):
    # Query for EIR_bdaddr_to_UUID16s table
    eir_uuid16s_query = f"SELECT list_type, str_UUID16s FROM EIR_bdaddr_to_UUID16s WHERE device_bdaddr = '{device_bdaddr}'"
    eir_uuid16s_result = execute_query(eir_uuid16s_query)
    
    # Query for LE_bdaddr_to_UUID16s table
    le_uuid16s_query = f"SELECT bdaddr_random, le_evt_type, list_type, str_UUID16s FROM LE_bdaddr_to_UUID16s WHERE device_bdaddr = '{device_bdaddr}'"
    le_uuid16s_result = execute_query(le_uuid16s_query)

    if(len(eir_uuid16s_result) != 0 or len(le_uuid16s_result) != 0):
        print("\tUUID16s found:")

    # Process EIR_bdaddr_to_UUID16s results
    for list_type, str_UUID16s in eir_uuid16s_result:
        str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
        for uuid16 in str_UUID16s_list:
            uuid16 = uuid16.strip()
            if(uuid16 == ''):
                print("\t\tEmpty list present")
                continue
            service_by_uuid16 = get_uuid16_service_string(uuid16)
            gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
            protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
            company_by_uuid16 = get_company_by_uuid16(uuid16)
            if(service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Service ID: {service_by_uuid16})")
            elif(gatt_service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (GATT Service ID: {gatt_service_by_uuid16})")
            elif(protocol_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Protocol ID: {protocol_by_uuid16})")
            elif(company_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Company ID: {company_by_uuid16})")
            else:
                print(f"\t\tUUID16 {uuid16} (No matches)")
        print("\t\t\tFound in BT Classic data (EIR_bdaddr_to_UUID16s)")

    # Process LE_bdaddr_to_UUID16s results
    for bdaddr_random, le_evt_type, list_type, str_UUID16s in le_uuid16s_result:
        str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
        for uuid16 in str_UUID16s_list:
            uuid16 = uuid16.strip()
            if(uuid16 == ''):
                print("\t\tEmpty list present")
                continue
            service_by_uuid16 = get_uuid16_service_string(uuid16)
            gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
            protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
            company_by_uuid16 = get_company_by_uuid16(uuid16)
            if(service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Service ID: {service_by_uuid16})")
            elif(gatt_service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (GATT Service ID: {gatt_service_by_uuid16})")
            elif(protocol_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Protocol ID: {protocol_by_uuid16})")
            elif(company_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Company ID: {company_by_uuid16})")
            else:
                print(f"\t\tUUID16 {uuid16} (No matches)")
        print(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID16s), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(eir_uuid16s_result) == 0 and len(le_uuid16s_result) == 0):
        print("\tNo UUID16s found.")

    print("")

# Function to print UUID16s for a given device_bdaddr
def print_service_solicit_uuid16s(device_bdaddr):
    le_uuid16s_query = f"SELECT bdaddr_random, le_evt_type, str_UUID16s FROM LE_bdaddr_to_UUID16_service_solicit WHERE device_bdaddr = '{device_bdaddr}'"
    le_uuid16s_result = execute_query(le_uuid16s_query)

    if(len(le_uuid16s_result) != 0):
        print("\tService solicit UUID16s found:")

    # Process LE_bdaddr_to_UUID16s results
    for bdaddr_random, le_evt_type, str_UUID16s in le_uuid16s_result:
        str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
        for uuid16 in str_UUID16s_list:
            uuid16 = uuid16.strip()
            if(uuid16 == ''):
                print("\t\tEmpty list present")
                continue
            service_by_uuid16 = get_uuid16_service_string(uuid16)
            gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
            protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
            company_by_uuid16 = get_company_by_uuid16(uuid16)
            if(service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Service ID: {service_by_uuid16})")
            elif(gatt_service_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (GATT Service ID: {gatt_service_by_uuid16})")
            elif(protocol_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Protocol ID: {protocol_by_uuid16})")
            elif(company_by_uuid16 != "Unknown"):
                print(f"\t\tUUID16 {uuid16} (Company ID: {company_by_uuid16})")
            else:
                print(f"\t\tUUID16 {uuid16} (No matches)")
        print(f"\t\t\t Found in BT LE data (LE_bdaddr_to_UUID16_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(le_uuid16s_result) == 0):
        print("\tNo Service Solicit UUID16s found.")

    print("")

########################################
# UUID128s
########################################

def get_custom_uuid128_string(uuid128):
    global custom_uuid128_hash
    global bt_member_UUID16_as_UUID128_to_names
    uuid128.strip().lower()
    uuid128_no_dash = uuid128.replace('-','')

    if(uuid128_no_dash in custom_uuid128_hash.keys()):
        return f"Custom UUID128: {custom_uuid128_hash[uuid128_no_dash]}"
    elif(uuid128_no_dash in bt_member_UUID16_as_UUID128_to_names.keys()):
        return f"Company UUID128: {bt_member_UUID16_as_UUID128_to_names[uuid128_no_dash]}"

    # TODO: Add lookup in Metadata_v2

    return f"Unknown UUID128"

# Function to print UUID128s for a given device_bdaddr
def print_uuid128s(device_bdaddr):
    eir_UUID128s_query = f"SELECT list_type, str_UUID128s FROM EIR_bdaddr_to_UUID128s WHERE device_bdaddr = '{device_bdaddr}'"
    eir_UUID128s_result = execute_query(eir_UUID128s_query)
    
    le_UUID128s_query = f"SELECT bdaddr_random, le_evt_type, list_type, str_UUID128s FROM LE_bdaddr_to_UUID128s WHERE device_bdaddr = '{device_bdaddr}'"
    le_UUID128s_result = execute_query(le_UUID128s_query)

    if(len(eir_UUID128s_result) != 0 or len(le_UUID128s_result) != 0):
        print("\tUUID128s found:")

    # Process EIR_bdaddr_to_UUID128s results
    for list_type, str_UUID128s in eir_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            dashing_uuid128 = f"{uuid128[:8]}-{uuid128[8:12]}-{uuid128[12:16]}-{uuid128[16:20]}-{uuid128[20:32]}"
            print(f"\t\tUUID128 {dashing_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print("\t\t\tFound in BT Classic data (EIR_bdaddr_to_UUID128s)")

    # Process LE_bdaddr_to_UUID128s results
    for bdaddr_random, le_evt_type, list_type, str_UUID128s in le_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            dashing_uuid128 = f"{uuid128[:8]}-{uuid128[8:12]}-{uuid128[12:16]}-{uuid128[16:20]}-{uuid128[20:32]}"
            print(f"\t\tUUID128 {dashing_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print(f"\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128s), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(device_bdaddr, bdaddr_random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(eir_UUID128s_result) == 0 and len(le_UUID128s_result) == 0):
        print("\tNo UUID128s found.")

    print("")

# Function to print UUID128s for a given device_bdaddr
def print_service_solicit_uuid128s(device_bdaddr):
    le_UUID128s_query = f"SELECT bdaddr_random, le_evt_type, str_UUID128s FROM LE_bdaddr_to_UUID128_service_solicit WHERE device_bdaddr = '{device_bdaddr}'"
    le_UUID128s_result = execute_query(le_UUID128s_query)

    if(len(le_UUID128s_result) != 0):
        print("\tService Solicit UUID128s found:")

    for bdaddr_random, le_evt_type, str_UUID128s in le_UUID128s_result:
        str_UUID128s_list = [token.strip() for token in str_UUID128s.split(',')]
        for uuid128 in str_UUID128s_list:
            uuid128 = uuid128.strip().lower()
            if(uuid128 == ''):
                print("\t\tEmpty list present")
                continue
            dashing_uuid128 = f"{uuid128[:8]}-{uuid128[8:12]}-{uuid128[12:16]}-{uuid128[16:20]}-{uuid128[20:32]}"
            print(f"\t\tUUID128 {dashing_uuid128} ({get_custom_uuid128_string(uuid128)})")
        print("\t\t\tFound in BT LE data (LE_bdaddr_to_UUID128_service_solicit), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    if(len(le_UUID128s_result) == 0):
        print("\tNo Service Solicit UUID128s found.")

    print("")

########################################
# Company name by BDADDR
########################################

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
    FROM LE_bdaddr_to_name
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

########################################
# 2thprint_BLE Info
########################################

def phy_prefs_to_string(number):
    str = ""
    if((number & 0b00000001) != 0):
        str += "'LE 1M PHY' "
    if((number & 0b00000010) != 0):
        str += "'LE 2M PHY' "
    if((number & 0b00000100) != 0):
        str += "'LE Coded PHY' "
    if(str == ""):
        str = "Invalid. At least one PHY was supposed to be selected!"
    return str

def decode_BLE_features(features):
    if(features & (0b1 << 0x00)): print(f"\t\t\t\t* LE Encryption")
    if(features & (0b1 << 0x01)): print(f"\t\t\t\t* Connection Parameters Request Procedure")
    if(features & (0b1 << 0x02)): print(f"\t\t\t\t* Extended Reject Indication")
    if(features & (0b1 << 0x03)): print(f"\t\t\t\t* Peripheral-initiated Features Exchange")
    if(features & (0b1 << 0x04)): print(f"\t\t\t\t* LE Ping")
    if(features & (0b1 << 0x05)): print(f"\t\t\t\t* LE Data Packet Length Extension")
    if(features & (0b1 << 0x06)): print(f"\t\t\t\t* LL Privacy")
    if(features & (0b1 << 0x07)): print(f"\t\t\t\t* Extended Scanner Filter Policies")
    if(features & (0b1 << 0x08)): print(f"\t\t\t\t* LE 2M PHY")
    if(features & (0b1 << 0x09)): print(f"\t\t\t\tStable Modulation Index - Transmitter")
    if(features & (0b1 << 0x0a)): print(f"\t\t\t\tStable Modulation Index - Receiver")
    if(features & (0b1 << 0x0b)): print(f"\t\t\t\t* LE Coded PHY")
    if(features & (0b1 << 0x0c)): print(f"\t\t\t\t* LE Extended Advertising")
    if(features & (0b1 << 0x0d)): print(f"\t\t\t\t* LE Periodic Advertising")
    if(features & (0b1 << 0x0e)): print(f"\t\t\t\t* Channel Selection Algorithm #2")
    if(features & (0b1 << 0x0f)): print(f"\t\t\t\t* LE Power Class 1")
    if(features & (0b1 << 0x10)): print(f"\t\t\t\t* Minimum Number of Used Channels procedure")
    if(features & (0b1 << 0x11)): print(f"\t\t\t\t* Connection CTE Request")
    if(features & (0b1 << 0x12)): print(f"\t\t\t\t* Connection CTE Response")
    if(features & (0b1 << 0x13)): print(f"\t\t\t\t* Connectionless CTE Transmitter")
    if(features & (0b1 << 0x14)): print(f"\t\t\t\t* Connectionless CTE Receiver")
    if(features & (0b1 << 0x15)): print(f"\t\t\t\t* Antenna Switching During CTE Transmission AoD")
    if(features & (0b1 << 0x16)): print(f"\t\t\t\t* Antenna Switching During CTE Reception AoA")
    if(features & (0b1 << 0x17)): print(f"\t\t\t\t* Receiving Constant Tone Extensions")
    if(features & (0b1 << 0x18)): print(f"\t\t\t\t* Periodic Advertising Sync Transfer - Sender")
    if(features & (0b1 << 0x19)): print(f"\t\t\t\t* Periodic Advertising Sync Transfer - Recipient")
    if(features & (0b1 << 0x1a)): print(f"\t\t\t\t* Sleep Clock Accuracy Updates")
    if(features & (0b1 << 0x1b)): print(f"\t\t\t\t* Remote Public Key Validation")
    if(features & (0b1 << 0x1c)): print(f"\t\t\t\t* Connected Isochronous Stream - Central")
    if(features & (0b1 << 0x1d)): print(f"\t\t\t\t* Connected Isochronous Stream - Peripheral")
    if(features & (0b1 << 0x1e)): print(f"\t\t\t\t* Isochronous Broadcaster")
    if(features & (0b1 << 0x1f)): print(f"\t\t\t\t* Synchronized Receiver")
    if(features & (0b1 << 0x20)): print(f"\t\t\t\t* Connected Isophronous Stream (Host Support)")
    if(features & (0b1 << 0x21)): print(f"\t\t\t\t* LE Power Control Request")
    if(features & (0b1 << 0x22)): print(f"\t\t\t\t* LE Power Control Indication")
    if(features & (0b1 << 0x23)): print(f"\t\t\t\t* LE Path Loss Monitoring")
    if(features & (0b1 << 0x24)): print(f"\t\t\t\t* Periodic Advertising ADI support")
    if(features & (0b1 << 0x25)): print(f"\t\t\t\t* Connection Subrating")
    if(features & (0b1 << 0x26)): print(f"\t\t\t\t* Connection Subrating (Host Support)")
    if(features & (0b1 << 0x27)): print(f"\t\t\t\t* Channel Classification")
    if(features & (0b1 << 0x28)): print(f"\t\t\t\t* Advertising Coding Selection")
    if(features & (0b1 << 0x29)): print(f"\t\t\t\t* Advertising Coding Selection (Host Support)")
    # One bit gap according to spec 5.4
    if(features & (0b1 << 0x2b)): print(f"\t\t\t\t* Periodic Advertising with Responses - Advertiser")
    if(features & (0b1 << 0x2c)): print(f"\t\t\t\t* Periodic Advertising with Responses - Scanner")

def print_BLE_2thprint(bdaddr):
    bdaddr = bdaddr.strip().lower()

    version_query = f"SELECT ll_version, ll_sub_version, device_BT_CID FROM BLE2th_LL_VERSION_IND WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)

    features_query = f"SELECT opcode, features FROM BLE2th_LL_FEATUREs WHERE device_bdaddr = '{bdaddr}'"
    features_result = execute_query(features_query)

    phys_query = f"SELECT tx_phys, rx_phys FROM BLE2th_LL_PHYs WHERE device_bdaddr = '{bdaddr}'"
    phys_result = execute_query(phys_query)

    lengths_query = f"SELECT opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time FROM BLE2th_LL_LENGTHs WHERE device_bdaddr = '{bdaddr}'"
    lengths_result = execute_query(lengths_query)

    ping_query = f"SELECT ping_rsp FROM BLE2th_LL_PING_RSP WHERE device_bdaddr = '{bdaddr}'"
    ping_result = execute_query(ping_query)

    unknown_query = f"SELECT unknown_opcode FROM BLE2th_LL_UNKNOWN_RSP WHERE device_bdaddr = '{bdaddr}'"
    unknown_result = execute_query(unknown_query)

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        print("\tBLE 2thprint Info:")

    ll_ctrl_pdu_opcodes = {9: "LL_FEATURE_RSP", 14: "LL_PERIPHERAL_FEATURE_REQ", 18: "LL_PING_REQ", 20: "LL_LENGTH_REQ", 21: "LL_LENGTH_RSP", 22: "LL_PHY_REQ", 23: "LL_PHY_RSP"}

    for ll_version, ll_sub_version, device_BT_CID in version_result:
        print(f"\t\tBT Version ({ll_version}): {get_bt_spec_version_numbers_to_names(ll_version)}")
        print("\t\tLL Sub-version: 0x%04x" % ll_sub_version)
        print(f"\t\tCompany ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for opcode, features in features_result:
        print(f"\t\tBLE LL Ctrl Opcode: {opcode} ({ll_ctrl_pdu_opcodes[opcode]})")
        print("\t\t\tBLE LL Features: 0x%016x" % features)
        decode_BLE_features(features)

    for tx_phys, rx_phys in phys_result:
        print(f"\t\tSender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
        print(f"\t\tSender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")

    for opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
        print(f"\t\tLL Ctrl Opcode: {opcode} ({ll_ctrl_pdu_opcodes[opcode]})")
        print(f"\t\t\tMax RX octets: {max_rx_octets}")
        print(f"\t\t\tMax RX time: {max_rx_time} microseconds")
        print(f"\t\t\tMax TX octets: {max_tx_octets}")
        print(f"\t\t\tMax TX time: {max_tx_time} microseconds")

    #FIXME: Why is there a , showing up on the end of this?!
    for (unknown_opcode,) in unknown_result:
        print(f"\t\tReturned 'Unknown Opcode' error for LL Ctrl Opcode: {unknown_opcode} ({ll_ctrl_pdu_opcodes[unknown_opcode]})")

    for ping_rsp in ping_result:
        print(f"\t\tLL Ping Response Received")

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        print("\tRaw BLE 2thprint:")
        with open(f"./BLE2thprints/{bdaddr}.ble2thprint", 'w') as file:
            for ll_version, ll_sub_version, device_BT_CID in version_result:
                print(f"\t\t\"ll_version\",\"0x%02x\"" % ll_version)
                file.write(f"\"ll_version\",\"0x%02x\"\n" % ll_version)

                print("\t\t\"ll_sub_version\",\"0x%04x\"" % ll_sub_version)
                file.write("\"ll_sub_version\",\"0x%04x\"\n" % ll_sub_version)

                print(f"\t\t\"version_BT_CID\",\"0x%04x\"" % device_BT_CID)
                file.write(f"\"version_BT_CID\",\"0x%04x\"\n" % device_BT_CID)

            for opcode, features in features_result:
                print(f"\t\t\"ll_ctrl_opcode\",\"0x%02x\",\"features\",\"0x%016x\"" % (opcode, features))
                file.write(f"\"ll_ctrl_opcode\",\"0x%02x\",\"features\",\"0x%016x\"\n" % (opcode, features))

            for tx_phys, rx_phys in phys_result:
                print(f"\t\t\"tx_phys\",\"0x%02x\"" % tx_phys)
                file.write(f"\"tx_phys\",\"0x%02x\"\n" % tx_phys)
                print(f"\t\t\"rx_phys\",\"0x%02x\"" % rx_phys)
                file.write(f"\"rx_phys\",\"0x%02x\"\n" % rx_phys)

            for opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
                print(f"\t\t\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))
                file.write(f"\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"\n" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))

            for (unknown_opcode,) in unknown_result:
                print(f"\t\t\"unknown_ll_ctrl_opcode\",\"0x%02x\"" % unknown_opcode)
                file.write(f"\"unknown_ll_ctrl_opcode\",\"0x%02x\"\n" % unknown_opcode)

            for ping_rsp in ping_result:
                print(f"\t\t\"ll_ping_rsp\",\"1\"")
                file.write(f"\"ll_ping_rsp\",\"1\"\n")



    if((len(version_result) == 0) and (len(features_result) == 0) and (len(phys_result) == 0) and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        print("\tNo BLE 2thprint Info found.")

    print("")


########################################
# 2thprint_BTC Info
########################################

def decode_BTC_features(page, features):
    if(page == 0):
        if(features & (0b1 << 0x00)): print(f"\t\t\t* 3 slot packets")
        if(features & (0b1 << 0x01)): print(f"\t\t\t* 5 slot packets")
        if(features & (0b1 << 0x02)): print(f"\t\t\t* Encryption")
        if(features & (0b1 << 0x03)): print(f"\t\t\t* Slot offset")
        if(features & (0b1 << 0x04)): print(f"\t\t\t* Timing accuracy")
        if(features & (0b1 << 0x05)): print(f"\t\t\t* Role switch")
        if(features & (0b1 << 0x06)): print(f"\t\t\t* Hold mode")
        if(features & (0b1 << 0x07)): print(f"\t\t\t* Sniff mode")
        if(features & (0b1 << 0x08)): print(f"\t\t\t* Previously used")
        if(features & (0b1 << 0x09)): print(f"\t\t\t* Power control requests")
        if(features & (0b1 << 0x0a)): print(f"\t\t\t* Channel quality driven data rate (CQDDR)")
        if(features & (0b1 << 0x0b)): print(f"\t\t\t* SCO link")
        if(features & (0b1 << 0x0c)): print(f"\t\t\t* HV2 packets")
        if(features & (0b1 << 0x0d)): print(f"\t\t\t* HV3 packets")
        if(features & (0b1 << 0x0e)): print(f"\t\t\t* μ-law log synchronous data")
        if(features & (0b1 << 0x0f)): print(f"\t\t\t* A-law log synchronous data")
        if(features & (0b1 << 0x10)): print(f"\t\t\t* CVSD synchronous data")
        if(features & (0b1 << 0x11)): print(f"\t\t\t* Paging parameter negotiation")
        if(features & (0b1 << 0x12)): print(f"\t\t\t* Power control")
        if(features & (0b1 << 0x13)): print(f"\t\t\t* Transparent synchronous data")
        if(features & (0b1 << 0x14)): print(f"\t\t\t* Flow control lag (least significant bit)")
        if(features & (0b1 << 0x15)): print(f"\t\t\t* Flow control lag (middle bit)")
        if(features & (0b1 << 0x16)): print(f"\t\t\t* Flow control lag (most significant bit)")
        if(features & (0b1 << 0x17)): print(f"\t\t\t* Broadcast Encryption")
        if(features & (0b1 << 0x18)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x19)): print(f"\t\t\t* Enhanced Data Rate ACL 2 Mb/s mode")
        if(features & (0b1 << 0x1a)): print(f"\t\t\t* Enhanced Data Rate ACL 3 Mb/s mode")
        if(features & (0b1 << 0x1b)): print(f"\t\t\t* Enhanced inquiry scan (see note)")
        if(features & (0b1 << 0x1c)): print(f"\t\t\t* Interlaced inquiry scan")
        if(features & (0b1 << 0x1d)): print(f"\t\t\t* Interlaced page scan")
        if(features & (0b1 << 0x1e)): print(f"\t\t\t* RSSI with inquiry results")
        if(features & (0b1 << 0x1f)): print(f"\t\t\t* Extended SCO link (EV3 packets)")
        if(features & (0b1 << 0x20)): print(f"\t\t\t* EV4 packets")
        if(features & (0b1 << 0x21)): print(f"\t\t\t* EV5 packets")
        if(features & (0b1 << 0x22)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x23)): print(f"\t\t\t* AFH capable Peripheral")
        if(features & (0b1 << 0x24)): print(f"\t\t\t* AFH classification Peripheral")
        if(features & (0b1 << 0x25)): print(f"\t\t\t* BR/EDR Not Supported")
        if(features & (0b1 << 0x26)): print(f"\t\t\t* LE Supported (Controller)")
        if(features & (0b1 << 0x27)): print(f"\t\t\t* 3-slot Enhanced Data Rate ACL packets")
        if(features & (0b1 << 0x28)): print(f"\t\t\t* 5-slot Enhanced Data Rate ACL packets")
        if(features & (0b1 << 0x29)): print(f"\t\t\t* Sniff subrating")
        if(features & (0b1 << 0x2a)): print(f"\t\t\t* Pause encryption")
        if(features & (0b1 << 0x2b)): print(f"\t\t\t* AFH capable Central")
        if(features & (0b1 << 0x2c)): print(f"\t\t\t* AFH classification Central")
        if(features & (0b1 << 0x2d)): print(f"\t\t\t* Enhanced Data Rate eSCO 2 Mb/s mode")
        if(features & (0b1 << 0x2e)): print(f"\t\t\t* Enhanced Data Rate eSCO 3 Mb/s mode")
        if(features & (0b1 << 0x2f)): print(f"\t\t\t* 3-slot Enhanced Data Rate eSCO packets")
        if(features & (0b1 << 0x30)): print(f"\t\t\t* Extended Inquiry Response")
        if(features & (0b1 << 0x31)): print(f"\t\t\t* Simultaneous LE and BR/EDR to Same Device Capable (Controller)")
        if(features & (0b1 << 0x32)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x33)): print(f"\t\t\t* Secure Simple Pairing (Controller Support)")
        if(features & (0b1 << 0x34)): print(f"\t\t\t* Encapsulated PDU")
        if(features & (0b1 << 0x35)): print(f"\t\t\t* Erroneous Data Reporting")
        if(features & (0b1 << 0x36)): print(f"\t\t\t* Non-flushable Packet Boundary Flag")
        if(features & (0b1 << 0x37)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x38)): print(f"\t\t\t* HCI_Link_Supervision_Timeout_Changed event")
        if(features & (0b1 << 0x39)): print(f"\t\t\t* Variable Inquiry TX Power Level")
        if(features & (0b1 << 0x3a)): print(f"\t\t\t* Enhanced Power Control")
        if(features & (0b1 << 0x3b)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3c)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3d)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3e)): print(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3f)): print(f"\t\t\t* Extended features")

def print_BTC_2thprint(bdaddr):
    bdaddr = bdaddr.strip().lower()

    version_query = f"SELECT lmp_version, lmp_sub_version, device_BT_CID FROM BTC2th_LMP_version_res WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)

    features_query = f"SELECT page, features FROM BTC2th_LMP_features_res WHERE device_bdaddr = '{bdaddr}'"
    features_result = execute_query(features_query)

    name_query = f"SELECT device_name FROM BTC2th_LMP_name_res WHERE device_bdaddr = '{bdaddr}'"
    name_result = execute_query(name_query)

    if(len(version_result) != 0 or len(features_result) != 0 or len(name_result) != 0): # or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        print("\tBTC 2thprint Info:")

    for lmp_version, lmp_sub_version, device_BT_CID in version_result:
        print(f"\t\tBT Version ({lmp_version}): {get_bt_spec_version_numbers_to_names(lmp_version)}")
        print("\t\tLMP Sub-version: 0x%04x" % lmp_sub_version)
        print(f"\t\tCompany ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for page, features in features_result:
        print("\t\tBTC LMP Features: 0x%016x" % features)
        decode_BTC_features(page, features)

    for (device_name,) in name_result:
        print(f"\t\tBTC LMP Name Response: {device_name}")
        find_nameprint_match(device_name)

    if(len(version_result) != 0 or len(features_result) != 0 or len(name_result) != 0): # or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        print("\n\tRaw BTC 2thprint:")
        with open(f"./BTC2thprints/{bdaddr}.btc2thprint", 'w') as file:
            for lmp_version, lmp_sub_version, device_BT_CID in version_result:
                print(f"\t\t\"lmp_version\",\"0x%02x\"" % lmp_version)
                file.write(f"\"lmp_version\",\"0x%02x\"\n" % lmp_version)
                print("\t\t\"lmp_sub_version\",\"0x%04x\"" % lmp_sub_version)
                file.write("\"lmp_sub_version\",\"0x%04x\"\n" % lmp_sub_version)
                print(f"\t\t\"version_BT_CID\",\"0x%04x\"" % device_BT_CID)
                file.write(f"\"version_BT_CID\",\"0x%04x\"\n" % device_BT_CID)

            for page, features in features_result:
                print("\t\t\"features\",\"0x%016x\"" % features)
                file.write("\"features\",\"0x%016x\"\n" % features)

    if((len(version_result) == 0) and (len(features_result) == 0) and (len(name_result) == 0)): # and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        print("\tNo BTC 2thprint Info found.")

    print("")

########################################
# GATT Info
########################################

def match_known_GATT_UUID_or_custom_UUID(uuid128):
    global custom_uuid128_hash
    uuid128.strip().lower()
    uuid128_no_dash = uuid128.replace('-','')
    pattern = r'0000[a-f0-9]{4}-0000-1000-8000-00805f9b34fb'
    match = re.match(pattern, uuid128)
    if match:
        common_part = match.group()  # Extract the matched part
        uuid16 = common_part[4:8]
        # Try to see if it's a known Service
        str_name = get_uuid16_gatt_service_string(uuid16)
        if(str_name != "Unknown"):
            return f"Service: {str_name}"
        else:
            # Try to see if it's a known Characteristic
            str_name = get_uuid16_gatt_characteristic_string(uuid16)
            if(str_name != "Unknown"):
                return f"Characteristic: {str_name}"
            else:
                # Try to see if it's a known Declaration
                str_name = get_uuid16_gatt_declaration_string(uuid16)
                if(str_name != "Unknown"):
                    return f"Declaration: {str_name}"
                else:
                    # Try to see if it's a known Descriptor
                    str_name = get_uuid16_gatt_descriptor_string(uuid16)
                    if(str_name != "Unknown"):
                        return f"Descriptor: {str_name}"
                    else:
                        str = get_custom_uuid128_string(uuid128_no_dash)
                        if(str == "Unknown UUID128"):
                            return "This is a standardized UUID128, but it is not in our database. Check for an update to characteristic_uuids.yaml"
                        else:
                            return str
    else:
        return get_custom_uuid128_string(uuid128_no_dash)
#    elif(uuid128_no_dash in custom_uuid128_hash):
#        return custom_uuid128_hash[uuid128_no_dash]
#    else:
#        return "Non-standard UUID128"

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

	
# Decode some misc things just because
def characteristic_value_decoding(UUID128, bytes):
    str = match_known_GATT_UUID_or_custom_UUID(UUID128)
    if(str == "Characteristic: Appearance"):
        value = int.from_bytes(bytes, byteorder='little')
        #print(f"Value = {value}")
        print(f"Appearance decodes as: {appearance_uint16_to_string(value)}")
    elif(str == "Characteristic: Peripheral Preferred Connection Parameters" and len(bytes) == 8):
        Interval_Min, Interval_Max, Latency, Timeout = struct.unpack('<HHHH', bytes)
        print(f"PPCP decodes as: Interval_Min:0x{Interval_Min:04x}, Interval_Max:0x{Interval_Max:04x}, Latency:0x{Latency:04x}, Timeout:0x{Timeout:04x}")
    elif(str == "Characteristic: Central Address Resolution" and len(bytes) == 1):
        addr_res_support = struct.unpack('<b', bytes)
        addr_res_support = "True" if addr_res_support == (1,) else "False"
        print(f"Central Address Resolution decodes as: Address Resolution Supported = {addr_res_support}")
    elif(str == "Characteristic: PnP ID" and len(bytes) == 7):
        company_id_type, company_id, product_id, product_version = struct.unpack('<BHHH', bytes)
        if(company_id_type == 1 or company_id_type == 2): # Don't bother with data which doesn't conform to spec
            if(company_id_type == 1):
                cname = BT_CID_to_company_name(company_id)
            else:
                cname = USB_CID_to_company_name(company_id)
            prod_ver_str = "{}.{}.{}".format(product_version >> 8, (product_version & 0x00F0) >> 4, (product_version & 0x000F))
            print(f"PnP ID decodes as: Company({company_id_type},0x{company_id:04x}) = {cname}, Product ID = 0x{product_id:04x}, Product Version = {prod_ver_str}")
    else:
        print("") # basically just force a newline so next line isn't double-indented

# Returns 0 if there is no GATT info for this BDADDR in any of the GATT tables, else returns 1
def device_has_GATT_info(bdaddr):
    # Query the database for all GATT services
    query = f"SELECT begin_handle,end_handle,UUID128 FROM GATT_services WHERE device_bdaddr = '{bdaddr}'";
    GATT_services_result = execute_query(query)

    query = f"SELECT attribute_handle,UUID128 FROM GATT_attribute_handles WHERE device_bdaddr = '{bdaddr}'";
    GATT_attribute_handles_result = execute_query(query)

    query = f"SELECT declaration_handle, char_properties, char_value_handle, UUID128 FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_result = execute_query(query)

    query = f"SELECT read_handle,byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_values_result = execute_query(query)

    if(len(GATT_services_result) != 0 or len(GATT_attribute_handles_result) != 0 or len(GATT_characteristics_result) != 0 or len(GATT_characteristics_values_result) !=0):
        return 1;
    else:
        return 0;

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

def print_associated_android_package_names(type, indent, UUID128):
    if(type == "Service"):
        query = f"SELECT android_pkg_name FROM BLEScope_UUID128s WHERE str_UUID128 = '{UUID128}' and uuid_type = 1";
    if(type == "Characteristic"):
        query = f"SELECT android_pkg_name FROM BLEScope_UUID128s WHERE str_UUID128 = '{UUID128}' and uuid_type = 2";

    print(f"{indent}{type} {UUID128}:")
    print(f"{indent}\tThis vendor-specific UUID128 is associated with the following Android packages in the BLEScope data:")
    android_pkgs_result = execute_query(query)
    for (pkg,) in android_pkgs_result:
        print(f"{indent}\t{pkg}")
    print()

def print_GATT_info(bdaddr, hideBLEScopedata):
    # Query the database for all GATT services
    query = f"SELECT begin_handle,end_handle,UUID128 FROM GATT_services WHERE device_bdaddr = '{bdaddr}'";
    GATT_services_result = execute_query(query)

    query = f"SELECT attribute_handle,UUID128 FROM GATT_attribute_handles WHERE device_bdaddr = '{bdaddr}'";
    GATT_attribute_handles_result = execute_query(query)
    attribute_handles_dict = {attribute_handle: UUID128 for attribute_handle,UUID128 in GATT_attribute_handles_result}

    query = f"SELECT declaration_handle, char_properties, char_value_handle, UUID128 FROM GATT_characteristics WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_result = execute_query(query)
    declaration_handles_dict = {declaration_handle: (char_properties, char_value_handle, UUID128) for declaration_handle, char_properties, char_value_handle, UUID128 in GATT_characteristics_result}

    query = f"SELECT read_handle,byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}'";
    GATT_characteristics_values_result = execute_query(query)
    char_value_handles_dict = {read_handle: byte_values for read_handle,byte_values in GATT_characteristics_values_result}

    # Changing up the logic to start from the maximum list of all handles in the attributes, characteristics, and read characteristic values tables
    # I will iterate through all of these handles, so nothing gets missed
    query = f"""
    SELECT DISTINCT handle_value
    FROM (
        SELECT attribute_handle AS handle_value
        FROM GATT_attribute_handles
        WHERE device_bdaddr = '{bdaddr}'
        UNION
        SELECT declaration_handle AS handle_value
        FROM GATT_characteristics
        WHERE device_bdaddr = '{bdaddr}'
        UNION
        SELECT char_value_handle AS handle_value
        FROM GATT_characteristics
        WHERE device_bdaddr = '{bdaddr}'
    ) AS combined_handles
    ORDER BY handle_value ASC;
    """
    GATT_all_known_handles_result = execute_query(query)

    if(len(GATT_services_result) != 0):
        print("\tGATT Information:")

    unknown_UUID128_hash = {}
    # Print semantically-meaningful information
    for svc_begin_handle,svc_end_handle,UUID128 in GATT_services_result:
        UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID128)
        print(f"\t\tGATT Service: Begin Handle: {svc_begin_handle}\tEnd Handle: {svc_end_handle}   \tUUID128: {UUID128} ({UUID128_description})")
        # If BLEScope data output is enabled, and we see an Unknown UUID128, save it to analyze later
        if(not hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
            unknown_UUID128_hash[UUID128] = ("Service","\t\t\t")

        # Iterate through all known handles, so nothing gets missed
        for handle, in GATT_all_known_handles_result:
            # Check if this handle is found in the GATT_attribute_handles table, and if so, print that info
            if(handle in attribute_handles_dict.keys()):
                attribute_handle = handle
                UUID128_2 = attribute_handles_dict[handle]
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    print(f"\t\t\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)}), Attribute Handle: {attribute_handle}")

            # Check if this handle is found in the GATT_characteristics table, and if so, print that info
            if(handle in declaration_handles_dict.keys()):
                declaration_handle = handle
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    (char_properties, char_value_handle, UUID128) = declaration_handles_dict[handle]
                    UUID128_description = match_known_GATT_UUID_or_custom_UUID(UUID128)
                    print(f"\t\t\t\tGATT Characteristic declaration:\t{UUID128} ({UUID128_description})\n\t\t\t\t\t\t\t\t\tHandle: {declaration_handle}\n\t\t\t\t\t\t\t\t\tProperties: 0x{char_properties:02x} ({characteristic_properties_to_string(char_properties)})")
                    if(not hideBLEScopedata and (UUID128_description == "Unknown UUID128")):
                        unknown_UUID128_hash[UUID128] = ("Characteristic","\t\t\t")

            # Check if this handle is found in the GATT_characteristics_values table, and if so, print that info
            if(handle in char_value_handles_dict.keys()):
                char_value_handle = handle
                byte_values = char_value_handles_dict[handle]
                if(handle <= svc_end_handle and handle >= svc_begin_handle):
                    print(f"\t\t\t\tGATT Characteristic Value read as {byte_values}")
                    print(f"\t\t\t\t\t", end="") # Don't want a newline before next print
                    characteristic_value_decoding(UUID128, byte_values) #NOTE: This leads to sub-optimal formatting due to the unconditional tabs above. TODO: adjust

    # Print raw GATT data minus the values read from characteristics. This can be a superset of the above due to handles potentially not being within the subsetted ranges of enclosing Services or Descriptors
    if(len(GATT_services_result) != 0):
        print(f"\n\t\tGATTPrint:")
        with open(f"./GATTPrints/{bdaddr}.gattprint", 'w') as file:
            for svc_begin_handle,svc_end_handle,UUID128 in GATT_services_result:
                print(f"\t\tGATT Service: Begin Handle: {svc_begin_handle}\tEnd Handle: {svc_end_handle}   \tUUID128: {UUID128} ({match_known_GATT_UUID_or_custom_UUID(UUID128)})")
                file.write(f"Svc: Begin Handle: {svc_begin_handle}\tEnd Handle: {svc_end_handle}   \tUUID128: {UUID128}\n")
            for attribute_handle, UUID128_2 in GATT_attribute_handles_result:
                print(f"\t\tGATT Descriptor: Descriptor Handle: {attribute_handle},\t{UUID128_2} ({match_known_GATT_UUID_or_custom_UUID(UUID128_2)})")
                file.write(f"Descriptor Handle: {attribute_handle}, {UUID128_2}\n")
            for declaration_handle, char_properties, char_value_handle, UUID128 in GATT_characteristics_result:
                print(f"\t\tGATT Characteristic Declaration: {UUID128}, Properties: 0x{char_properties:02x}, Declaration Handle: {declaration_handle}, Characteristic Value Handle: {char_value_handle}")
                file.write(f"Char: {UUID128}, Properties: {char_properties}, Declaration Handle: {declaration_handle}, Characteristic Handle: {char_value_handle}\n")
        print("")

        if(not hideBLEScopedata):
            print("\t\tBLEScope Analysis: Vendor-specific UUIDs were found. Analyzing if there are any known associations with Android app packages based on BLEScope data.")
            for UUID128 in unknown_UUID128_hash.keys():
                (type, indent) = unknown_UUID128_hash[UUID128]
                print_associated_android_package_names(type, indent, UUID128)

    if(len(GATT_services_result) == 0):
        print("\tNo GATT Information found.")
        print("")

########################################
# Metadata v2 helper functions
########################################

# Had to move this earlier for use in match_str_to_ChipMaker()
# The ChipMaker_names_and_BT_CIDs will be used as regexp expressions in MySQL queries to find the associated IEEE OUIs
# Note: Apple and Samsung have been observed to get their endianness wrong. But Samsung devices have also been observed using a completely arbitrary/wrong 0xFF19 value in the BT CID field of MSD...
ChipMaker_names_and_BT_CIDs = {'^Actions': [0x03E0], 'Airoha Technology Corp': [0x94], 'Ambiq': [0x09AC], 'Atheros Communications': [0x45], '^Apple': [0x004C, 0x4C00], 'Barrot Technology': [0x08E7], 'beken': [0x05F0], 'Bestechnic': [0x02B0], 'Bluetrum': [0x642], 'Broadcom': [0xF], 'Casambi': [0x03C3], 'Cypress Semiconductor': [0x131] , 'Dialog Semiconductor': [0xD2], 'Espressif': [0x02E5], 'HiSilicon': [0x010F], 'Hong Kong HunterSun': [0x01BF], 'Infineon': [0x09], 'Ingchips': [0x06AC], 'Intel Corp': [0x02], '^LAPIS': [0x0179], 'Marvell': [0x48], 'MediaTek': [0x46], 'Nordic Semiconductor': [0x59], 'NXP': [0x25], '^ON Semiconductor': [0x0362], 'PHYPLUS': [0x0504], 'Qualcomm': [0x0A, 0x1D], 'Realtek': [0x5D], 'RivieraWaves': [0x60], 'Samsung': [0x0075, 0x7500, 0xff19], 'Shanghai Mountain View Silicon': [0x06D9, 0xD906], 'Shanghai wuqi': [0x0A06], 'Shenzhen Goodix Technology': [0x04F7], 'Silicon Laboratories': [0x02FF], 'Spreadtrum Communications': [0x01EC], 'STMicro': [0x30], 'ST Microelectronics': [0x30], 'Telink Semiconductor': [0x0211], 'Texas Instruments': [0x0D], '^Universal Electronics': [0x93], 'Vimicro': [0x81], 'Yichip Microelectronics': [0x050E], 'Zhuhai Jieli': [0x05D6], 'MILWAUKEE': [123]}

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
        for heading, metadata in metadata_v2.items():
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
    str = ""

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
                char_value_query = f"SELECT byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}' and read_handle = {char_value_handle}"
                char_value_result = execute_query(char_value_query)
                if(len(char_value_result) > 0):
                    for (byte_values,) in char_value_result:
                        tmpstr = byte_values.decode('utf-8')
                        #print(f"byte_values: {tmpstr}")
                        # Now consult with the metadata_v2 data, and see if any entries have a 2thprint_Chip_GATT_Model_Number which matches the value observed in the database
                        for heading, metadata in metadata_v2.items():
                            if('2thprint_Chip_GATT_Model_Number' in metadata):
                                # FIXME: I think this is probably an insufficient matching criteria. E.g. a "Jabra Evolve 65e" device might match "Jabra Elite Active" metadata and then the printout would be a bit confusing
                                if(tmpstr == metadata['2thprint_Chip_GATT_Model_Number']):
                                    model_name_match = 1
                                    str = f"\t\t{metadata['2thprint_Chip']} -> From GATT \"Model/Hardware Number String\" match with '{metadata['2thprint_Device_Model']}' device metadata (GATT_characteristics & GATT_characteristics_values tables & metadata_v2)"

    # Return something appropriate for printing, or an empty string if no match
    return str

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
        for heading, metadata in metadata_v2.items():
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
                                 char_value_query = f"SELECT byte_values FROM GATT_characteristics_values WHERE device_bdaddr = '{bdaddr}' and read_handle = {char_value_handle}"
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
    str = lookup_metadata_by_nameprint(bdaddr, '2thprint_Chip_Maker')
    if(str != ""):
        print(str)
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
        for str in str_list:
            print(str)

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


########################################
# MAIN #################################
########################################

# Main function to handle command line arguments
def main():
    parser = argparse.ArgumentParser(description='Query device names from MySQL tables.')
    parser.add_argument('--bdaddr', type=str, required=False, help='Device bdaddr value.')
    parser.add_argument('--bdaddrregex', type=str, default='', required=False, help='Regex to match a bdaddr value.')
    parser.add_argument('--type', type=int, default=0, help='Device name type (0 or 1) for LE tables.')
    parser.add_argument('--nameregex', type=str, default='', help='Value for REGEXP match against device_name.')
    parser.add_argument('--NOTnameregex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --nameregex, and then remove them from the final results.')
    parser.add_argument('--companyregex', type=str, default='', help='Value for REGEXP match against company name, in IEEE OUIs, or BT Company IDs, or BT Company UUID16s.')
    parser.add_argument('--NOTcompanyregex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --companyregex, and then remove them from the final results.')
    parser.add_argument('--UUID128regex', type=str, default='', help='Value for REGEXP match against UUID128, in advertised UUID128s')
    parser.add_argument('--UUID16regex', type=str, default='', help='Value for REGEXP match against UUID16, in advertised UUID16s')
    parser.add_argument('--MSDregex', type=str, default='', help='Value for REGEXP match against Manufacturer-Specific Data (MSD)')
    parser.add_argument('--UUID128stats', type=str, default='', help='Parse the UUID128 data, and output statistics about the most common entries')
    parser.add_argument('--UUID16stats', type=str, default='', help='Parse the UUID16 data, and output statistics about the most common entries')
    parser.add_argument('--requireGATT', action='store_true', help='Pass this argument to only print out information for devices which have GATT info')
    parser.add_argument('--require_LL_VERSION_IND', action='store_true', help='Pass this argument to only print out information for devices which have LL_VERSION_IND data')
    parser.add_argument('--require_LMP_VERSION_RES', action='store_true', help='Pass this argument to only print out information for devices which have LMP_VERSION_RES data')
    parser.add_argument('--hideBLEScopedata', action='store_true', help='Pass this argument to not print out the BLEScope data about Android package names associated with vendor-specific GATT UUID128s')

    args = parser.parse_args()
    bdaddr = args.bdaddr
    bdaddrregex = args.bdaddrregex
    nametype = 0 # Default to non-random
    nametype = args.type
    nameregex = args.nameregex
    notnameregex = args.NOTnameregex
    companyregex = args.companyregex
    notcompanyregex = args.NOTcompanyregex
    uuid128regex = args.UUID128regex
    uuid16regex = args.UUID16regex
    msdregex = args.MSDregex
    uuid16stats = args.UUID16stats
    uuid128stats = args.UUID128stats
    requireGATT = args.requireGATT
    require_LL_VERSION_IND = args.require_LL_VERSION_IND
    require_LMP_VERSION_RES = args.require_LMP_VERSION_RES
    hideBLEScopedata = args.hideBLEScopedata

    # Import any data from CSV files as necessary
    create_nameprint_CSV_data()
    create_custom_uuid128_CSV_data()

    # Fill in dictionaries based on standard BT assigned numbers YAML files
    create_CoD_to_names()
    create_bt_CID_to_names()
    create_bt_member_UUID16s_to_names()
    create_bt_spec_version_numbers_to_names()
    create_uuid16_service_names()
    create_uuid16_protocol_names()
    create_gatt_services_uuid16_names()
    create_gatt_declarations_uuid16_names()
    create_gatt_descriptors_uuid16_names()
    create_gatt_characteristic_uuid16_names()
    create_appearance_yaml_data()

    # It could be argued that the ChipMaker_OUI_hash should be pulled out and made static and just read from file.
    # But I'd consider that premature optimization for now.
    # TODO: consider doing this in the future if it adds too much overhead to every invocation
    create_ChipMaker_OUI_hash()

    if(bdaddr is not None):
        bdaddrs = [bdaddr]
    else:
        bdaddrs = []

    ######################################################
    # Options to simply print statistics from the database
    ######################################################

    if(uuid16stats != ""):
        get_uuid16_stats(uuid16stats)
        quit() # Don't do anything other than print the stats and exit

    if(uuid128stats != ""):
        get_uuid128_stats(uuid128stats)
        quit() # Don't do anything other than print the stats and exit

    print(bdaddrs)

    #######################################################
    # Options to search based on specific values or regexes
    #######################################################

    if(bdaddrregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_bdaddr_regex(bdaddrregex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after bdaddrregex processing: {bdaddrs}")

    if(nameregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_name_regex(nameregex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after nameregex processing: {bdaddrs}")

    if(companyregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_company_regex(companyregex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after companyregex processing: {bdaddrs}")

    if(msdregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_msd_regex(msdregex)
        print(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after msdregex processing: {bdaddrs}")

    if(uuid128regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_uuid128_regex(uuid128regex)
        print(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after uuid128regex processing: {bdaddrs}")

    if(uuid16regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_uuid16_regex(uuid16regex)
        print(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after uuid16regex processing: {bdaddrs}")

    if(notcompanyregex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_company_regex(notcompanyregex)
        print(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        print(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;

    if(notnameregex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_name_regex(notnameregex)
        print(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        print(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;


    for bdaddr in bdaddrs:
        if(requireGATT):
            if(device_has_GATT_info(bdaddr) != 1):
                continue
        if(require_LL_VERSION_IND):
            if(device_has_LL_VERSION_IND_info(bdaddr) != 1):
                continue
        if(require_LMP_VERSION_RES):
            if(device_has_LMP_VERSION_RES_info(bdaddr) != 1):
                continue
        print("================================================================================")
        print(f"For bdaddr = {bdaddr}:")
        print_ChipPrint(bdaddr)
        print_ChipMakerPrint(bdaddr)
        print_company_name_from_bdaddr("\t", bdaddr, True)
        print_classic_EIR_CID_info(bdaddr)
        print_device_names(bdaddr, nametype)
        print_uuid16s(bdaddr)
        print_service_solicit_uuid16s(bdaddr)
        print_uuid128s(bdaddr)
        print_service_solicit_uuid128s(bdaddr)
        print_transmit_power(bdaddr, nametype)
        print_appearance(bdaddr, nametype)
        print_manufacturer_data(bdaddr)
        print_class_of_device(bdaddr)
        print_GATT_info(bdaddr, hideBLEScopedata)
        print_BLE_2thprint(bdaddr)
        print_BTC_2thprint(bdaddr)
        print_UniqueIDReport(bdaddr)

if __name__ == "__main__":
    main()
