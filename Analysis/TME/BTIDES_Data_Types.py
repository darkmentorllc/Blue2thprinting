########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

# Valid types defined in BTIDES schema. These are for things where we had to make our own values
# because we couldn't use the values already defined in the spec

from TME.BT_Data_Types import *

# Advertisement channel types
type_BTIDES_ADV_IND           = 0
type_BTIDES_ADV_DIRECT_IND    = 1
type_BTIDES_ADV_NONCONN_IND   = 2
type_BTIDES_ADV_SCAN_IND      = 3
type_BTIDES_AUX_ADV_IND       = 10
type_BTIDES_SCAN_RSP          = 20
type_BTIDES_AUX_SCAN_RSP      = 21
type_BTIDES_CONNECT_IND       = 40
type_BTIDES_EIR               = 50

adv_chan_types_to_strings = {
    type_BTIDES_ADV_IND:            "ADV_IND",
    type_BTIDES_ADV_DIRECT_IND:     "ADV_DIRECT_IND",
    type_BTIDES_ADV_NONCONN_IND:    "ADV_NONCONN_IND",
    type_BTIDES_ADV_SCAN_IND:       "ADV_SCAN_IND",
    type_BTIDES_AUX_ADV_IND:        "AUX_ADV_IND",
    type_BTIDES_SCAN_RSP:           "SCAN_RSP",
    type_BTIDES_AUX_SCAN_RSP:       "AUX_SCAN_RSP",
    type_BTIDES_CONNECT_IND:        "CONNECT_IND",
    type_BTIDES_EIR:                "EIR"
}

# Directions for post-connection packet communication
type_BTIDES_direction_C2P =             0 # Central to Peripheral
type_BTIDES_direction_P2C =             1 # Peripheral to Central

# HCI Statuses
type_BTIDES_status_SUCCESS =            0

# ATT IO types
ATT_type_to_BTIDES_io_type_str = {
    type_ATT_ERROR_RSP:                     "Error - ATT_ERROR_RSP",
    type_ATT_FIND_INFORMATION_RSP:          "Read - ATT_FIND_INFORMATION_RSP",
    type_ATT_FIND_BY_TYPE_VALUE_RSP:        "Read - ATT_FIND_BY_TYPE_VALUE_RSP",
    type_ATT_READ_BY_TYPE_RSP:              "Read - ATT_READ_BY_TYPE_RSP",
    type_ATT_READ_RSP:                      "Read - ATT_READ_RSP",
    type_ATT_READ_BLOB_RSP:                 "Read - ATT_READ_BLOB_RSP",
    type_ATT_READ_MULTIPLE_RSP:             "Read - ATT_READ_MULTIPLE_RSP",
    type_ATT_READ_BY_GROUP_TYPE_RSP:        "Read - ATT_READ_BY_GROUP_TYPE_RSP",
    type_ATT_READ_MULTIPLE_VARIABLE_RSP:    "Read - ATT_READ_MULTIPLE_VARIABLE_RSP",
    type_ATT_WRITE_REQ:                     "Write with response - ATT_WRITE_REQ",
    type_ATT_PREPARE_WRITE_REQ:             "Write with response - ATT_PREPARE_WRITE_REQ",
    type_ATT_WRITE_CMD:                     "Write without response - ATT_WRITE_CMD",
    type_ATT_SIGNED_WRITE_CMD:              "Write without response - ATT_SIGNED_WRITE_CMD",
    type_ATT_HANDLE_VALUE_NTF:              "Notification - ATT_HANDLE_VALUE_NTF",
    type_ATT_MULTIPLE_HANDLE_VALUE_NTF:     "Notification - ATT_MULTIPLE_HANDLE_VALUE_NTF",
    type_ATT_HANDLE_VALUE_IND:              "Indication - ATT_HANDLE_VALUE_IND"
}

UUIDs_to_characteristic_descriptor_type_str = {
    "2900":                     "Characteristic Descriptor: Characteristic Extended Properties",
    "2901":                     "Characteristic Descriptor: Characteristic User Description",
    "2902":                     "Characteristic Descriptor: Client Characteristic Configuration",
    "2903":                     "Characteristic Descriptor: Server Characteristic Configuration",
    "2904":                     "Characteristic Descriptor: Characteristic Presentation Format",
    "2905":                     "Characteristic Descriptor: Characteristic Aggregate Format"
}

# EIR types
type_BTIDES_EIR_PSRM    = 1
type_BTIDES_EIR_CoD     = 2