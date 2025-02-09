########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *

type_AdvData_Flags                              = 0x01
type_AdvData_UUID16ListIncomplete               = 0x02
type_AdvData_UUID16ListComplete                 = 0x03
type_AdvData_UUID32ListIncomplete               = 0x04
type_AdvData_UUID32ListComplete                 = 0x05
type_AdvData_UUID128ListIncomplete              = 0x06
type_AdvData_UUID128ListComplete                = 0x07
type_AdvData_IncompleteName                     = 0x08
type_AdvData_CompleteName                       = 0x09
type_AdvData_TxPower                            = 0x0a
type_AdvData_ClassOfDevice                      = 0x0d
type_AdvData_DeviceID                           = 0x10
type_AdvData_PeripheralConnectionIntervalRange  = 0x12
type_AdvData_UUID16ListServiceSolicitation      = 0x14
type_AdvData_UUID128ListServiceSolicitation     = 0x15
type_AdvData_UUID16ServiceData                  = 0x16
type_AdvData_PublicTargetAddress                = 0x17
type_AdvData_RandomTargetAddress                = 0x18
type_AdvData_Appearance                         = 0x19
type_AdvData_AdvertisingInterval                = 0x1a
type_AdvData_LE_BDADDR                          = 0x1b
type_AdvData_LE_Role                            = 0x1c
type_AdvData_UUID32ListServiceSolicitation      = 0x1f
type_AdvData_UUID32ServiceData                  = 0x20
type_AdvData_UUID128ServiceData                 = 0x21
type_AdvData_URI                                = 0x24
type_AdvData_BroadcastName                      = 0x30
type_AdvData_3DInfoData                         = 0x3d
type_AdvData_MSD                                = 0xff

# Advertisement channel PDU types defined in BT spec
type_AdvChanPDU_ADV_IND           = 0
type_AdvChanPDU_ADV_DIRECT_IND    = 1
type_AdvChanPDU_ADV_NONCONN_IND   = 2
type_AdvChanPDU_SCAN_REQ          = 3
type_AdvChanPDU_SCAN_RSP          = 4
type_AdvChanPDU_CONNECT_IND       = 5
type_AdvChanPDU_ADV_SCAN_IND      = 6
type_AdvChanPDU_AUX_ADV_IND       = 7
type_AdvChanPDU_AUX_SCAN_RSP      = 7

## LL Control PDU types defined in BT spec
type_opcode_LL_CONNECTION_UPDATE_IND     = 0
type_opcode_LL_CHANNEL_MAP_IND           = 1
type_opcode_LL_TERMINATE_IND             = 2
type_opcode_LL_ENC_REQ                   = 3
type_opcode_LL_ENC_RSP                   = 4
type_opcode_LL_START_ENC_REQ             = 5
type_opcode_LL_START_ENC_RSP             = 6
type_opcode_LL_UNKNOWN_RSP               = 7
type_opcode_LL_FEATURE_REQ               = 8
type_opcode_LL_FEATURE_RSP               = 9
type_opcode_LL_VERSION_IND               = 12
type_opcode_LL_REJECT_IND                = 13
type_opcode_LL_PERIPHERAL_FEATURE_REQ    = 14
type_opcode_LL_CONNECTION_PARAM_REQ      = 15
type_opcode_LL_CONNECTION_PARAM_RSP      = 16
type_opcode_LL_REJECT_EXT_IND            = 17
type_opcode_LL_PING_REQ                  = 18
type_opcode_LL_PING_RSP                  = 19
type_opcode_LL_LENGTH_REQ                = 20
type_opcode_LL_LENGTH_RSP                = 21
type_opcode_LL_PHY_REQ                   = 22
type_opcode_LL_PHY_RSP                   = 23
type_opcode_LL_PHY_UPDATE_IND            = 24
type_opcode_LL_UNKNOWN_CUSTOM            = 255 # Invalid per the spec, but seems to be in use by Apple?

## LMP PDU types defined in BT spec
type_opcode_LMP_VERSION_RES             = 38
type_opcode_LMP_FEATURES_RES            = 40
type_opcode_LMP_FEATURES_RES_EXT        = 127

type_extended_opcode_LMP_FEATURES_RES_EXT = 4

ll_ctrl_pdu_opcodes_to_strings = {
    type_opcode_LL_CONNECTION_UPDATE_IND:   "LL_CONNECTION_UPDATE_IND",
    type_opcode_LL_CHANNEL_MAP_IND:         "LL_CHANNEL_MAP_IND",
    type_opcode_LL_TERMINATE_IND:           "LL_TERMINATE_IND",
    type_opcode_LL_ENC_REQ:                 "LL_ENC_REQ",
    type_opcode_LL_ENC_RSP:                 "LL_ENC_RSP",
    type_opcode_LL_START_ENC_REQ:           "LL_START_ENC_REQ",
    type_opcode_LL_START_ENC_RSP:           "LL_START_ENC_RSP",
    type_opcode_LL_UNKNOWN_RSP:             "LL_UNKNOWN_RSP",
    type_opcode_LL_FEATURE_REQ:             "LL_FEATURE_REQ",
    type_opcode_LL_FEATURE_RSP:             "LL_FEATURE_RSP",
    type_opcode_LL_VERSION_IND:             "LL_VERSION_IND",
    type_opcode_LL_REJECT_IND:              "LL_REJECT_IND",
    type_opcode_LL_PERIPHERAL_FEATURE_REQ:  "LL_PERIPHERAL_FEATURE_REQ",
    type_opcode_LL_CONNECTION_PARAM_REQ:    "LL_CONNECTION_PARAM_REQ",
    type_opcode_LL_CONNECTION_PARAM_RSP:    "LL_CONNECTION_PARAM_RSP",
    type_opcode_LL_REJECT_EXT_IND:          "LL_REJECT_EXT_IND",
    type_opcode_LL_PING_REQ:                "LL_PING_REQ",
    type_opcode_LL_PING_RSP:                "LL_PING_RSP",
    type_opcode_LL_LENGTH_REQ:              "LL_LENGTH_REQ",
    type_opcode_LL_LENGTH_RSP:              "LL_LENGTH_RSP",
    type_opcode_LL_PHY_REQ:                 "LL_PHY_REQ",
    type_opcode_LL_PHY_RSP:                 "LL_PHY_RSP",
    type_opcode_LL_PHY_UPDATE_IND:          "LL_PHY_UPDATE_IND",
    type_opcode_LL_UNKNOWN_CUSTOM:          "LL_UNKNOWN_CUSTOM"
}

# HCI Event codes defined in BT spec
event_code_HCI_Remote_Name_Request_Complete     = 7

# Controller error codes defined in BT spec (also reused by LL_TERMINATE_IND)
controller_error_strings = {
    0: "Success",
    1: "Unknown HCI Command",
    2: "Unknown Connection Identifier",
    3: "Hardware Failure",
    4: "Page Timeout",
    5: "Authentication Failure",
    6: "PIN or Key Missing",
    7: "Memory Capacity Exceeded",
    8: "Connection Timeout",
    9: "Connection Limit Exceeded",
    10: "Synchronous Connection Limit To A Device Exceeded",
    11: "ACL Connection Already Exists",
    12: "Command Disallowed",
    13: "Connection Rejected due to Limited Resources",
    14: "Connection Rejected Due To Security Reasons",
    15: "Connection Rejected due to Unacceptable BD_ADDR",
    16: "Connection Accept Timeout Exceeded",
    17: "Unsupported Feature or Parameter Value",
    18: "Invalid HCI Command Parameters",
    19: "Remote User Terminated Connection",
    20: "Remote Device Terminated Connection due to Low Resources",
    21: "Remote Device Terminated Connection due to Power Off",
    22: "Connection Terminated By Local Host",
    23: "Repeated Attempts",
    24: "Pairing Not Allowed",
    25: "Unknown LMP PDU",
    26: "Unsupported Remote Feature / Unsupported LMP Feature",
    27: "SCO Offset Rejected",
    28: "SCO Interval Rejected",
    29: "SCO Air Mode Rejected",
    30: "Invalid LMP Parameters / Invalid LL Parameters",
    31: "Unspecified Error",
    32: "Unsupported LMP Parameter Value / Unsupported LL Parameter Value",
    33: "Role Change Not Allowed",
    34: "LMP Response Timeout / LL Response Timeout",
    35: "LMP Error Transaction Collision",
    36: "LMP PDU Not Allowed",
    37: "Encryption Mode Not Acceptable",
    38: "Link Key cannot be Changed",
    39: "Requested QoS Not Supported",
    40: "Instant Passed",
    41: "Pairing With Unit Key Not Supported",
    42: "Different Transaction Collision",
    43: "Reserved for future use",
    44: "QoS Unacceptable Parameter",
    45: "QoS Rejected",
    46: "Channel Classification Not Supported",
    47: "Insufficient Security",
    48: "Parameter Out Of Mandatory Range",
    49: "Reserved for future use",
    50: "Role Switch Pending",
    51: "Reserved for future use",
    52: "Reserved Slot Violation",
    53: "Role Switch Failed",
    54: "Extended Inquiry Response Too Large",
    55: "Secure Simple Pairing Not Supported By Host",
    56: "Host Busy - Pairing",
    57: "Connection Rejected due to No Suitable Channel Found",
    58: "Controller Busy",
    59: "Unacceptable Connection Parameters",
    60: "Directed Advertising Timeout",
    61: "Connection Terminated due to MIC Failure",
    62: "Connection Failed to be Established / Synchronization Timeout",
    63: "MAC Connection Failed",
    64: "Coarse Clock Adjustment Rejected but Will Try to Adjust Using Clock Dragging",
    65: "Type0 Submap Not Defined",
    66: "Unknown Advertising Identifier",
    67: "Limit Reached",
    68: "Operation Cancelled by Host",
    69: "Packet Too Long"
}

# ATT PDU types defined in BT spec
type_ATT_ERROR_RSP                  = 0x01
type_ATT_EXCHANGE_MTU_REQ           = 0x02
type_ATT_EXCHANGE_MTU_RSP           = 0x03
type_ATT_FIND_INFORMATION_REQ       = 0x04
type_ATT_FIND_INFORMATION_RSP       = 0x05
type_ATT_FIND_BY_TYPE_VALUE_REQ     = 0x06
type_ATT_FIND_BY_TYPE_VALUE_RSP     = 0x07
type_ATT_READ_BY_TYPE_REQ           = 0x08
type_ATT_READ_BY_TYPE_RSP           = 0x09
type_ATT_READ_REQ                   = 0x0a
type_ATT_READ_RSP                   = 0x0b
type_ATT_READ_BLOB_REQ              = 0x0c
type_ATT_READ_BLOB_RSP              = 0x0d
type_ATT_READ_MULTIPLE_REQ          = 0x0e
type_ATT_READ_MULTIPLE_RSP          = 0x0f
type_ATT_READ_BY_GROUP_TYPE_REQ     = 0x10
type_ATT_READ_BY_GROUP_TYPE_RSP     = 0x11
type_ATT_WRITE_REQ                  = 0x12
type_ATT_WRITE_RSP                  = 0x13
type_ATT_PREPARE_WRITE_REQ          = 0x16
type_ATT_PREPARE_WRITE_RSP          = 0x17
type_ATT_EXECUTE_WRITE_REQ          = 0x18
type_ATT_EXECUTE_WRITE_RSP          = 0x19
type_ATT_HANDLE_VALUE_NTF           = 0x1b
type_ATT_HANDLE_VALUE_IND           = 0x1d
type_ATT_HANDLE_VALUE_CFM           = 0x1e
type_ATT_READ_MULTIPLE_VARIABLE_REQ = 0x20
type_ATT_READ_MULTIPLE_VARIABLE_RSP = 0x21
type_ATT_MULTIPLE_HANDLE_VALUE_NTF  = 0x23
type_ATT_WRITE_CMD                  = 0x52
type_ATT_SIGNED_WRITE_CMD           = 0xD2

att_opcode_strings = {
    type_ATT_ERROR_RSP:                 "ATT_ERROR_RSP",
    type_ATT_EXCHANGE_MTU_REQ:          "ATT_EXCHANGE_MTU_REQ",
    type_ATT_EXCHANGE_MTU_RSP:          "ATT_EXCHANGE_MTU_RSP",
    type_ATT_FIND_INFORMATION_REQ:      "ATT_FIND_INFORMATION_REQ",
    type_ATT_FIND_INFORMATION_RSP:      "ATT_FIND_INFORMATION_RSP",
    type_ATT_FIND_BY_TYPE_VALUE_REQ:    "ATT_FIND_BY_TYPE_VALUE_REQ",
    type_ATT_READ_BY_TYPE_REQ:          "ATT_READ_BY_TYPE_REQ",
    type_ATT_READ_BY_TYPE_RSP:          "ATT_READ_BY_TYPE_RSP",
    type_ATT_READ_REQ:                  "ATT_READ_REQ",
    type_ATT_READ_RSP:                  "ATT_READ_RSP",
    type_ATT_READ_BY_GROUP_TYPE_REQ:    "ATT_READ_BY_GROUP_TYPE_REQ",
    type_ATT_READ_BY_GROUP_TYPE_RSP:    "ATT_READ_BY_GROUP_TYPE_RSP",
    type_ATT_READ_BLOB_REQ:             "ATT_READ_BLOB_REQ",
    type_ATT_READ_BLOB_RSP:             "ATT_READ_BLOB_RSP",
    type_ATT_FIND_BY_TYPE_VALUE_RSP:    "ATT_FIND_BY_TYPE_VALUE_RSP",
    type_ATT_READ_MULTIPLE_REQ:         "ATT_READ_MULTIPLE_REQ",
    type_ATT_READ_MULTIPLE_RSP:         "ATT_READ_MULTIPLE_RSP",
    type_ATT_WRITE_REQ:                 "ATT_WRITE_REQ",
    type_ATT_WRITE_RSP:                 "ATT_WRITE_RSP",
    type_ATT_PREPARE_WRITE_REQ:         "ATT_PREPARE_WRITE_REQ",
    type_ATT_PREPARE_WRITE_RSP:         "ATT_PREPARE_WRITE_RSP",
    type_ATT_EXECUTE_WRITE_REQ:         "ATT_EXECUTE_WRITE_REQ",
    type_ATT_EXECUTE_WRITE_RSP:         "ATT_EXECUTE_WRITE_RSP",
    type_ATT_HANDLE_VALUE_NTF:          "ATT_HANDLE_VALUE_NTF",
    type_ATT_HANDLE_VALUE_IND:          "ATT_HANDLE_VALUE_IND",
    type_ATT_HANDLE_VALUE_CFM:          "ATT_HANDLE_VALUE_CFM",
    type_ATT_READ_MULTIPLE_VARIABLE_REQ:"ATT_READ_MULTIPLE_VARIABLE_REQ",
    type_ATT_READ_MULTIPLE_VARIABLE_RSP:"ATT_READ_MULTIPLE_VARIABLE_RSP",
    type_ATT_MULTIPLE_HANDLE_VALUE_NTF: "ATT_MULTIPLE_HANDLE_VALUE_NTF",
    type_ATT_WRITE_CMD:                 "ATT_WRITE_CMD",
    type_ATT_SIGNED_WRITE_CMD:          "ATT_SIGNED_WRITE_CMD"
}

att_error_strings = {
    1: "Invalid Handle",
    2: "Read Not Permitted",
    3: "Write Not Permitted",
    4: "Invalid PDU",
    5: "Insufficient Authentication",
    6: "Request Not Supported",
    7: "Invalid Offset",
    8: "Insufficient Authorization",
    9: "Prepare Queue Full",
    10: "Attribute Not Found",
    11: "Attribute Not Long",
    12: "Encryption Key Size Too Short",
    13: "Invalid Attribute Value Length",
    14: "Unlikely Error",
    15: "Insufficient Encryption",
    16: "Unsupported Group Type",
    17: "Insufficient Resources",
    18: "Database Out of Sync",
    19: "Value Not Allowed"
}

# SMP PDU types defined in BT spec
type_opcode_SMP_Pairing_Request                 = 1
type_opcode_SMP_Pairing_Response                = 2
type_opcode_SMP_Pairing_Confirm                 = 3
type_opcode_SMP_Pairing_Random                  = 4
type_opcode_SMP_Pairing_Failed                  = 5
type_opcode_SMP_Encryption_Information          = 6
type_opcode_SMP_Central_Identification          = 7
type_opcode_SMP_Identity_Information            = 8
type_opcode_SMP_Identity_Address_Information    = 9
type_opcode_SMP_Signing_Information             = 10
type_opcode_SMP_Security_Request                = 11
type_opcode_SMP_Pairing_Public_Key              = 12
type_opcode_SMP_Pairing_DHKey_Check             = 13
type_opcode_SMP_Pairing_Keypress_Notification   = 14

smp_opcode_strings = {
    type_opcode_SMP_Pairing_Request:               "Pairing Request",
    type_opcode_SMP_Pairing_Response:              "Pairing Response",
    type_opcode_SMP_Pairing_Confirm:               "Pairing Confirm",
    type_opcode_SMP_Pairing_Random:                "Pairing Random",
    type_opcode_SMP_Pairing_Failed:                "Pairing Failed",
    type_opcode_SMP_Encryption_Information:        "Encryption Information",
    type_opcode_SMP_Central_Identification:        "Central Identification",
    type_opcode_SMP_Identity_Information:          "Identity Information",
    type_opcode_SMP_Identity_Address_Information:  "Identity Address Information",
    type_opcode_SMP_Signing_Information:           "Signing Information",
    type_opcode_SMP_Security_Request:              "Security Request",
    type_opcode_SMP_Pairing_Public_Key:            "Pairing Public Key",
    type_opcode_SMP_Pairing_DHKey_Check:           "Pairing DHKey Check",
    type_opcode_SMP_Pairing_Keypress_Notification: "Pairing Keypress Notification"
}

type_SMP_IO_Capabilities_DisplayOnly        = 0
type_SMP_IO_Capabilities_DisplayYesNo       = 1
type_SMP_IO_Capabilities_KeyboardOnly       = 2
type_SMP_IO_Capabilities_NoInputNoOutput    = 3
type_SMP_IO_Capabilities_KeyboardDisplay    = 4

smp_io_cap_strings = {
    type_SMP_IO_Capabilities_DisplayOnly:       "Display Only",
    type_SMP_IO_Capabilities_DisplayYesNo:      "Display Yes/No",
    type_SMP_IO_Capabilities_KeyboardOnly:      "Keyboard Only",
    type_SMP_IO_Capabilities_NoInputNoOutput:   "No Input, No Output",
    type_SMP_IO_Capabilities_KeyboardDisplay:   "Keyboard & Display"
}

smp_error_strings = {
    0x01: "Passkey Entry Failed",
    0x02: "OOB Not Available",
    0x03: "Authentication Requirements",
    0x04: "Confirm Value Failed",
    0x05: "Pairing Not Supported",
    0x06: "Encryption Key Size",
    0x07: "Command Not Supported",
    0x08: "Unspecified Reason",
    0x09: "Repeated Attempts",
    0x0a: "Invalid Parameters",
    0x0b: "DHKey Check Failed",
    0x0c: "Numeric Comparison Failed",
    0x0d: "BR/EDR Pairing In Progress",
    0x0e: "Cross-Transport Key Derivation/Generation not allowed",
    0x0f: "Key Rejected",
}

type_SMP_KeypressNotification_PasskeyEntryStarted        = 0
type_SMP_KeypressNotification_PasskeyDigitEntered        = 1
type_SMP_KeypressNotification_PasskeyDigitErased         = 2
type_SMP_KeypressNotification_PasskeyCleared             = 3
type_SMP_KeypressNotification_PasskeyEntryCompleted      = 4

smp_keypress_notification_strings = {
    type_SMP_KeypressNotification_PasskeyEntryStarted:       "Passkey entry started",
    type_SMP_KeypressNotification_PasskeyDigitEntered:       "Passkey digit entered",
    type_SMP_KeypressNotification_PasskeyDigitErased:        "Passkey digit erased",
    type_SMP_KeypressNotification_PasskeyCleared:            "Passkey cleared",
    type_SMP_KeypressNotification_PasskeyEntryCompleted:     "Passkey entry completed"
}