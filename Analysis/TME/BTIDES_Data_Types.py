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
type_BTIDES_AUX_SCAN_RSP      = 10
type_BTIDES_EIR               = 50
valid_adv_chan_types = [type_BTIDES_ADV_IND, type_BTIDES_ADV_DIRECT_IND, type_BTIDES_ADV_NONCONN_IND, type_BTIDES_ADV_SCAN_IND, type_BTIDES_AUX_ADV_IND, type_BTIDES_SCAN_RSP, type_BTIDES_AUX_SCAN_RSP, type_BTIDES_EIR]
valid_adv_chan_type_strs = ["ADV_IND", "ADV_DIRECT_IND", "ADV_NONCONN_IND", "ADV_SCAN_IND", "AUX_ADV_IND", "SCAN_RSP", "AUX_SCAN_RSP", "EIR"]

# ATT IO types
type_BTIDES_ATT_Read =                  0
type_BTIDES_ATT_WriteWithResponse =     1
type_BTIDES_ATT_WriteWithoutResponse =  2
type_BTIDES_ATT_Notification =          3
type_BTIDES_ATT_Indication =            4