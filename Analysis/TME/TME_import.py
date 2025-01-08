########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

import json
import csv
import yaml
import TME.TME_glob
from TME.TME_helpers import *

########################################
# BEGIN FILL DATA FROM JSON ############
########################################

def import_metadata_v2():
    global metadata_v2
    # Load JSON data from file
    json_file = './Metadata_v2.json'
    with open(json_file, 'r') as f:
        TME.TME_glob.metadata_v2 = json.load(f)


# Option to store private metadata in
# this file. It will be consulted, but
# doesn't need to be checked in
def import_private_metadata_v2():
    global metadata_v2
    json_file = './Metadata_v2_private.json'
    try:
        with open(json_file, 'r') as f:
            TME.TME_glob.metadata_v2.update(json.load(f))
    except FileNotFoundError:
        pass

# This is data in CLUES format
def import_CLUES():
    global metadata_v2
    # Load JSON data from file
    json_file = './CLUES_Schema/CLUES_data.json'
    with open(json_file, 'r') as f:
        # Convert from array to hash indexed by UUID for faster lookup
        data = json.load(f)
        # Remove dashes from UUIDs for consistency with later checking code
        for entry in data:
            entry['UUID'] = entry['UUID'].replace('-', '')
        TME.TME_glob.clues = {entry['UUID']: entry for entry in data}

# Option to store private metadata in
# this file. It will be consulted, but
# doesn't need to be checked in
def import_private_CLUES():
    global metadata_v2
    json_file = './CLUES_Schema/CLUES_data_private.json'
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
            # Remove dashes from UUIDs for consistency with later checking code
            for entry in data:
                entry['UUID'] = entry['UUID'].replace('-', '')
            TME.TME_glob.clues.update({entry['UUID']: entry for entry in data})
    except FileNotFoundError:
        pass

########################################
# BEGIN FILL DATA FROM CSVs ############
########################################

def import_nameprint_CSV_data():
    global nameprint_data
    with open("./NAMEPRINT_DB.csv", 'r') as csvfile:
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            if len(row) >= 2:
                key = row[1].strip()
                value = row[0].strip()
                TME.TME_glob.nameprint_data[key] = value

def import_private_nameprint_CSV_data():
    global nameprint_data
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
                    TME.TME_glob.nameprint_data[key] = value
    except FileNotFoundError:
        pass

# TODO: This should now be deprecated in favor of CLUES - DELETEME
# def import_custom_uuid128_CSV_data():
#     global custom_uuid128_hash
#     with open("./custom_uuid128s.csv", 'r') as csvfile:
#         csv_reader = csv.reader(csvfile, quoting=csv.QUOTE_ALL)
#         for row in csv_reader:
#             if len(row) >= 2:
#                 key = row[0].strip().lower()
#                 value = row[1].strip()
#                 TME.TME_glob.custom_uuid128_hash[key] = value
# #                qprint(f"key = {key}, value = {value}")


########################################
# BEGIN FILL DATA FROM YAML ############
########################################

#########################################
# Get data from company_identifiers.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_bt_CID_to_names():
    global bt_CID_to_names
    with open('./public/assigned_numbers/company_identifiers/company_identifiers.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['company_identifiers']:
        value = entry['value']
        name = entry['name']
        TME.TME_glob.bt_CID_to_names[value] = name

    # Hack: Add in the wrong-endian Apple/Samsung values
    TME.TME_glob.bt_CID_to_names[0x4C00] = "Apple, Inc. (wrong-endian)"
    TME.TME_glob.bt_CID_to_names[0x7500] = "Samsung (wrong-endian)"
    TME.TME_glob.bt_CID_to_names[0xff19] = "Samsung (buggy)"

#    qprint(TME.TME_glob.bt_CID_to_names)
#    qprint(len(TME.TME_glob.bt_CID_to_names))

#########################################
# Get data from member_uuids.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_bt_member_UUID16s_to_names():
    global bt_member_UUID16s_to_names
    global bt_member_UUID16_as_UUID128_to_names
    with open('./public/assigned_numbers/uuids/member_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        value = entry['uuid']
        name = entry['name']
        TME.TME_glob.bt_member_UUID16s_to_names[value] = name
        uuid128_value = f"0000{value:04x}00001000800000805f9b34fb".lower()
        TME.TME_glob.bt_member_UUID16_as_UUID128_to_names[uuid128_value] = name

#    qprint(TME.TME_glob.bt_member_UUID16s_to_names)
#    qprint(TME.TME_glob.bt_member_UUID16_as_UUID128_to_names)
#    qprint(len(TME.TME_glob.bt_member_UUID16s_to_names))


#########################################
# Get data from class_of_device.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_CoD_to_names():
    global CoD_yaml_data
    with open('./public/assigned_numbers/core/class_of_device.yaml', 'r') as file:
        TME.TME_glob.CoD_yaml_data = yaml.safe_load(file)

#########################################
# Get data from core_version.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_bt_spec_version_numbers_to_names():
    global bt_spec_version_numbers_to_names
    with open('./public/assigned_numbers/core/core_version.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['core_version']:
        value = entry['value']
        name = entry['name']
        TME.TME_glob.bt_spec_version_numbers_to_names[value] = name

    #qprint(TME.TME_glob.bt_spec_version_numbers_to_names)

#########################################
# Get data from appearance_values.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_appearance_yaml_data():
    global appearance_yaml_data
    with open('./public/assigned_numbers/core/appearance_values.yaml', 'r') as file:
        TME.TME_glob.appearance_yaml_data = yaml.safe_load(file)

#########################################
# Get data from service_uuids.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_gatt_services_uuid16_names():
    global gatt_services_uuid16_names
    with open('./public/assigned_numbers/uuids/service_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.gatt_services_uuid16_names[uuid] = name

    #qprint(TME.TME_glob.gatt_services_uuid16_names)

#########################################
# Get data from declarations.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_gatt_declarations_uuid16_names():
    global gatt_declarations_uuid16_names
    with open('./public/assigned_numbers/uuids/declarations.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.gatt_declarations_uuid16_names[uuid] = name

    #qprint(TME.TME_glob.gatt_declarations_uuid16_names)

#########################################
# Get data from descriptors.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_gatt_descriptors_uuid16_names():
    global gatt_descriptors_uuid16_names
    with open('./public/assigned_numbers/uuids/descriptors.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.gatt_descriptors_uuid16_names[uuid] = name

    #qprint(TME.TME_glob.gatt_descriptors_uuid16_names)

#########################################
# Get data from characteristic_uuids.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_gatt_characteristic_uuid16_names():
    global gatt_characteristic_uuid16_names
    with open('./public/assigned_numbers/uuids/characteristic_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.gatt_characteristic_uuid16_names[uuid] = name

    #qprint(TME.TME_glob.gatt_characteristic_uuid16_names)

#########################################
# Get data from protocol_identifiers.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_uuid16_protocol_names():
    global uuid16_protocol_names
    with open('./public/assigned_numbers/uuids/protocol_identifiers.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.uuid16_protocol_names[uuid] = name

    #qprint(TME.TME_glob.uuid16_protocol_names)

#########################################
# Get data from service_class.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_uuid16_service_names():
    global uuid16_service_names
    with open('./public/assigned_numbers/uuids/service_class.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.uuid16_service_names[uuid] = name

    #qprint(TME.TME_glob.uuid16_service_names)