########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

type_AdvData_Flags                              = 1
type_AdvData_UUID16ListIncomplete               = 2
type_AdvData_UUID16ListComplete                 = 3
type_AdvData_UUID32ListIncomplete               = 4
type_AdvData_UUID32ListComplete                 = 5
type_AdvData_UUID128ListIncomplete              = 6
type_AdvData_UUID128ListComplete                = 7
type_AdvData_IncompleteName                     = 8
type_AdvData_CompleteName                       = 9
type_AdvData_TxPower                            = 10
type_AdvData_ClassOfDevice                      = 13
type_AdvData_DeviceID                           = 16
type_AdvData_PeripheralConnectionIntervalRange  = 18
type_AdvData_UUID16ServiceData                  = 22
type_AdvData_Appearance                         = 25
type_AdvData_UUID32ServiceData                  = 32
type_AdvData_UUID128ServiceData                 = 33
type_AdvData_MSD                                = 255

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

# HCI Event codes defined in BT spec
event_code_HCI_Remote_Name_Request_Complete     = 7

# ATT PDU types defined in BT spec
type_ATT_EXCHANGE_MTU_REQ  = 0x02
type_ATT_EXCHANGE_MTU_RSP  = 0x03
type_ATT_READ_REQ          = 0x0A
type_ATT_READ_RSP          = 0x0B

att_opcode_strings = {
    type_ATT_EXCHANGE_MTU_REQ: "ATT_EXCHANGE_MTU_REQ",
    type_ATT_EXCHANGE_MTU_RSP: "ATT_EXCHANGE_MTU_RSP",
    type_ATT_READ_REQ: "ATT_READ_REQ",
    type_ATT_READ_RSP: "ATT_READ_RSP"
}