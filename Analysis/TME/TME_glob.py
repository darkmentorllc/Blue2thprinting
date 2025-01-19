########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#########################################
# My specific data types
#########################################
# Metadata_v1 globals
custom_uuid128_hash = {}
# Metadata_v2 globals
metadata_v2 = {}
# clues globals hash indexed by UUID
clues = {}
# clues globals hash indexed by UUID, containing a UUID meant to be interpreted as a regex
clues_regexed = {}
# NamePrint data
nameprint_data = {}

#########################################
# Data from company_identifiers.yaml
#########################################
bt_CID_to_names = {}

#########################################
# Data from member_uuids.yaml
#########################################
bt_member_UUID16s_to_names = {}
bt_member_UUID16_as_UUID128_to_names = {}

#########################################
# Data from class_of_device.yaml
#########################################
CoD_yaml_data = {}

#########################################
# Data from core_version.yaml
#########################################
bt_spec_version_numbers_to_names = {}

#########################################
# Data from appearance_values.yaml
#########################################
appearance_yaml_data = {}

#########################################
# Data from service_uuids.yaml
#########################################
gatt_services_uuid16_names = {}

#########################################
# Data from declarations.yaml
#########################################
gatt_declarations_uuid16_names = {}

#########################################
# Data from descriptors.yaml
#########################################
gatt_descriptors_uuid16_names = {}

#########################################
# Data from characteristic_uuids.yaml
#########################################
gatt_characteristic_uuid16_names = {}

#########################################
# Data from protocol_identifiers.yaml
#########################################
uuid16_protocol_names = {}

#########################################
# Data from service_class.yaml
#########################################
# Global dictionary to store uuid16 to service name mappings
uuid16_service_names = {}

#########################################
# BTIDES JSON data to export
#########################################
BTIDES_JSON = []
verbose_BTIDES = False

#########################################
# Verbose/quiet printing
#########################################
verbose_print = False
quiet_print = False

###############################################
# Use alternate test database (for development)
###############################################
use_test_db = False
insert_count = 0
duplicate_count = 0