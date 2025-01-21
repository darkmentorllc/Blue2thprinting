########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

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
type_AdvData_AdvertisingInterval                = 0x1A
type_AdvData_LE_BDADDR                          = 0x1B
type_AdvData_LE_Role                            = 0x1C
type_AdvData_UUID32ListServiceSolicitation      = 0x1F
type_AdvData_UUID32ServiceData                  = 0x20
type_AdvData_UUID128ServiceData                 = 0x21
type_AdvData_URI                                = 0x24
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
type_opcode_LL_TERMINATE_IND             = 2
type_opcode_LL_START_ENC_REQ             = 5
type_opcode_LL_START_ENC_RSP             = 6
type_opcode_LL_UNKNOWN_RSP               = 7
type_opcode_LL_FEATURE_REQ               = 8
type_opcode_LL_FEATURE_RSP               = 9
type_opcode_LL_VERSION_IND               = 12
type_opcode_LL_PERIPHERAL_FEATURE_REQ    = 14
type_opcode_LL_PING_REQ                  = 18
type_opcode_LL_PING_RSP                  = 19
type_opcode_LL_LENGTH_REQ                = 20
type_opcode_LL_LENGTH_RSP                = 21
type_opcode_LL_PHY_REQ                   = 22
type_opcode_LL_PHY_RSP                   = 23

## LMP PDU types defined in BT spec
type_opcode_LMP_VERSION_RES             = 38
type_opcode_LMP_FEATURES_RES            = 40
type_opcode_LMP_FEATURES_RES_EXT        = 127

type_extended_opcode_LMP_FEATURES_RES_EXT = 4

ll_ctrl_pdu_opcodes_to_strings = {
    2: "LL_TERMINATE_IND",
    5: "LL_START_ENC_REQ",
    6: "LL_START_ENC_RSP",
    7: "LL_UNKNOWN_RSP",
    8: "LL_FEATURE_REQ",
    9: "LL_FEATURE_RSP",
    12: "LL_VERSION_IND",
    14: "LL_PERIPHERAL_FEATURE_REQ",
    18: "LL_PING_REQ",
    19: "LL_PING_RSP",
    20: "LL_LENGTH_REQ",
    21: "LL_LENGTH_RSP",
    22: "LL_PHY_REQ",
    23: "LL_PHY_RSP"
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
type_ATT_READ_REQ                   = 0x0A
type_ATT_READ_RSP                   = 0x0B
type_ATT_READ_BY_GROUP_TYPE_REQ     = 0x10
type_ATT_READ_BY_GROUP_TYPE_RSP     = 0x11

att_opcode_strings = {
    type_ATT_ERROR_RSP: "ATT_ERROR_RSP",
    type_ATT_EXCHANGE_MTU_REQ: "ATT_EXCHANGE_MTU_REQ",
    type_ATT_EXCHANGE_MTU_RSP: "ATT_EXCHANGE_MTU_RSP",
    type_ATT_FIND_INFORMATION_REQ: "ATT_FIND_INFORMATION_REQ",
    type_ATT_FIND_INFORMATION_RSP: "ATT_FIND_INFORMATION_RSP",
    type_ATT_READ_REQ: "ATT_READ_REQ",
    type_ATT_READ_RSP: "ATT_READ_RSP",
    type_ATT_READ_BY_GROUP_TYPE_REQ: "ATT_READ_BY_GROUP_TYPE_REQ",
    type_ATT_READ_BY_GROUP_TYPE_RSP: "ATT_READ_BY_GROUP_TYPE_RSP"
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
