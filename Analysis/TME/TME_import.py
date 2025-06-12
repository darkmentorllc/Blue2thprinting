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
    json_file = './private/Metadata_v2_private.json'
    try:
        with open(json_file, 'r') as f:
            TME.TME_glob.metadata_v2.update(json.load(f))
    except FileNotFoundError:
        pass

# This is data in CLUES format
def import_CLUES():
    global clues
    global clues_regexed
    # Load JSON data from file
    json_file = './CLUES_Schema/CLUES_data.json'
    with open(json_file, 'r') as f:
        # Convert from array to hash indexed by UUID for faster lookup
        data = json.load(f)
        # Remove dashes from UUIDs for consistency with later checking code
        for entry in data:
            entry['UUID'] = entry['UUID'].replace('-', '')
            TME.TME_glob.clues[entry['UUID']] = entry
            if("regex" in entry.keys()):
                TME.TME_glob.clues_regexed[entry['UUID']] = entry
#        TME.TME_glob.clues = {entry['UUID']: entry for entry in data}

# Option to store private metadata in
# this file. It will be consulted, but
# doesn't need to be checked in
def import_private_CLUES():
    global clues
    global clues_regexed
    json_file = './private/CLUES_data_private.json'
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
    global full_nameprint_data
    with open("./NAMEPRINT_DB.csv", 'r') as csvfile:
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            if len(row) >= 2:
                key = row[1].strip()
                value = row[0].strip()
                TME.TME_glob.full_nameprint_data[key] = value

    # The user has the option to store private metadata in
    # this file. It will be consulted, but doesn't need to be checked in
    try:
        with open('./private/NAMEPRINT_DB_private.csv', 'r') as csvfile:
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                if len(row) >= 2:
                    key = row[1].strip()
                    value = row[0].strip()
                    TME.TME_glob.full_nameprint_data[key] = value
    except FileNotFoundError:
        pass

def import_nonunique_nameprint_CSV_data():
    global nonunique_nameprint_data
    global full_nameprint_data
    with open("./NAMEPRINT_NONUNIQUE_DB.csv", 'r') as csvfile:
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            if len(row) >= 2:
                key = row[1].strip()
                value = row[0].strip()
                TME.TME_glob.nonunique_nameprint_data[key] = value
                TME.TME_glob.full_nameprint_data[key] = value

    # The user has the option to store private metadata in
    # this file. It will be consulted, but doesn't need to be checked in
    try:
        with open('./private/NAMEPRINT_NONUNIQUE_DB_private.csv', 'r') as csvfile:
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                if len(row) >= 2:
                    key = row[1].strip()
                    value = row[0].strip()
                    TME.TME_glob.nonunique_nameprint_data[key] = value
                    TME.TME_glob.full_nameprint_data[key] = value
    except FileNotFoundError:
        pass

########################################
# BEGIN FILL DATA FROM YAML ############
########################################

#########################################
# Get data from formattypes.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_bt_format_type_to_descriptions():
    global bt_format_type_to_description
    with open('./public/assigned_numbers/core/formattypes.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['formattypes']:
        value = entry['value']
        description = entry['description']
        TME.TME_glob.bt_format_type_to_description[value] = description

#########################################
# Get data from units.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_bt_units_to_names():
    global bt_units_to_names
    with open('./public/assigned_numbers/uuids/units.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.bt_units_to_names[uuid] = name

#########################################
# Get data from namespace.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_bt_namespace_descriptions():
    global bt_namespace_descriptions
    with open('./public/assigned_numbers/core/namespace.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['namespace']:
        value = entry['value']
        name = entry['name']
        TME.TME_glob.bt_namespace_descriptions[value] = name

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
    TME.TME_glob.bt_CID_to_names[0xD906] = "Shanghai Mountain View Silicon Co.,Ltd. (wrong-endian)"

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

#########################################
# Get data from sdo.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_uuid16_standards_organizations_names():
    global uuid16_standards_organizations_names
    with open('./public/assigned_numbers/uuids/sdo_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        name = entry['name']
        TME.TME_glob.uuid16_standards_organizations_names[uuid] = name

    # qprint(TME.TME_glob.uuid16_standards_organizations_names)

#########################################
# Get data from universal_attributes.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
# (I love the term "Universal Attribute", which is also used in the spec...
# as if these UUIDs will be used throughout the universe...)
def import_SDP_universal_attribute_names():
    global SDP_universal_attribute_names
    with open('./public/assigned_numbers/service_discovery/attribute_ids/universal_attributes.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['attribute_ids']:
        name = entry['name']
        value = entry['value']
        TME.TME_glob.SDP_universal_attribute_names[value] = name

    #qprint(TME.TME_glob.SDP_universal_attribute_names)

#########################################
# Get data from protocol_identifiers.yaml
#########################################
# NOTE: This code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned to the same directory as this file.
# All paths are written under that assumption
def import_SDP_protocol_identifiers():
    global SDP_protocol_identifiers
    with open('./public/assigned_numbers/uuids/protocol_identifiers.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        name = entry['name']
        uuid = entry['uuid']
        TME.TME_glob.SDP_protocol_identifiers[uuid] = name

    #qprint(TME.TME_glob.SDP_universal_attribute_names)