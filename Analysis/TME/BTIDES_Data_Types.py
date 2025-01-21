########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

# Valid types defined in BTIDES schema. These are for things where we had to make our own values
# because we couldn't use the values already defined in the spec

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
type_BTIDES_ATT_Read =                  0
type_BTIDES_ATT_WriteWithResponse =     1
type_BTIDES_ATT_WriteWithoutResponse =  2
type_BTIDES_ATT_Notification =          3
type_BTIDES_ATT_Indication =            4

# EIR types
type_BTIDES_EIR_PSRM    = 1
type_BTIDES_EIR_CoD     = 2