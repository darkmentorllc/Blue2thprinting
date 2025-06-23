########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#########################################
# My specific data types
#########################################

# Indendation (so I can change formatting in a centralized way later)
# 1 tab per level
# i1 = "\t"
# i2 = "\t\t"
# i3 = "\t\t\t"
# i4 = "\t\t\t\t"
# i5 = "\t\t\t\t\t"

# 2 spaces per level
i1 = "  "
i2 = "    "
i3 = "      "
i4 = "        "
i5 = "          "

# Metadata_v1 globals
custom_uuid128_hash = {}
# Metadata_v2 globals
metadata_v2 = {}
# clues globals hash indexed by UUID
clues = {}
# clues globals hash indexed by UUID, containing a UUID meant to be interpreted as a regex
clues_regexed = {}
# NamePrint data
full_nameprint_data = {}
presumed_unique_nameprint_data = {}
nonunique_nameprint_data = {}
privacy_report_no_results_found = True

#########################################
# Data from formattypes.yaml
#########################################
bt_format_type_to_description = {}

#########################################
# Data from units.yaml
#########################################
bt_units_to_names = {}

#########################################
# Data from namespace.yaml
#########################################
bt_namespace_descriptions = {}

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
# Data from sdo.yaml
#########################################
# Global dictionary to store uuid16 to Standards Development Organization name mappings
uuid16_standards_organizations_names = {}

#########################################
# Data from universal_attributes.yaml
#########################################
# Global dictionary to store SDP uuid16 to
# to attribute name mappings
# (I love the term "Universal Attribute",
# which is also used in the spec...
# as if these UUIDs will be used throughout
# the universe...)
SDP_universal_attribute_names = {}

#########################################
# Data from universal_attributes.yaml
#########################################
# Global dictionary to store SDP uuid16 to
# to protocol identifiers mappings
SDP_protocol_identifiers = {}

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

###############################################
# For making the output more terse
###############################################
hide_android_data = False

############################################################
# For hiding the ChipMakerPrint header when nothing is found
############################################################
g_printed_ChipPrint_header = False
g_printed_ChipMakerPrint_header = False

############################################################
# For smarter handling of Unique ID header printing
############################################################
g_printed_unique_id_header = False
g_printed_possible_unique_id_header = False

