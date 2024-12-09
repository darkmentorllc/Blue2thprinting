########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import re
from TME.BT_Data_Types import *
from TME.TME_BTIDES_base import generic_SingleBDADDR_insertion_into_BTIDES_second_level_array, convert_UUID128_to_UUID16_if_possible
import TME.TME_glob
from TME.TME_UUID128 import add_dashes_to_UUID128

############################
# Helper "factory functions"
############################

def ff_ATT_handle_enumeration(handle_entry_obj):
    obj = {"ATT_handle_enumeration": [ handle_entry_obj ]}
    return obj


# TODO: we need to update database to keep track of status
def ff_ATT_handle_entry(handle, UUID):
    UUID = convert_UUID128_to_UUID16_if_possible(UUID) # Save space on exported data if possible
    obj = {"handle": handle, "UUID": UUID}
    return obj


def ff_ATT_ERROR_RSP(direction, request_opcode_in_error, attribute_handle_in_error, error_code):
    obj = {
        "direction": direction,
        "opcode": type_ATT_ERROR_RSP,
        "request_opcode_in_error": request_opcode_in_error,
        "attribute_handle_in_error": attribute_handle_in_error,
        "error_code": error_code
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_ERROR_RSP]
        if(error_code in att_error_strings):
            obj["error_str"] = att_error_strings[error_code]
        else:
            if(error_code >= 0x80 and error_code <= 0x9F):
                obj["error_str"] = "Application Error Code"
            elif(error_code >= 0xE0 and error_code <= 0xFF):
                obj["error_str"] = "Common Profile and Service Error Code"
            else:
                obj["error_str"] = "Unknown Error Code"
    return obj


def ff_ATT_EXCHANGE_MTU_REQ(direction, client_rx_mtu):
    obj = {"direction": direction, "opcode": type_ATT_EXCHANGE_MTU_REQ, "client_rx_mtu": client_rx_mtu}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_EXCHANGE_MTU_REQ]
    return obj


def ff_ATT_EXCHANGE_MTU_RSP(direction, server_rx_mtu):
    obj = {"direction": direction, "opcode": type_ATT_EXCHANGE_MTU_RSP, "server_rx_mtu": server_rx_mtu}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_EXCHANGE_MTU_RSP]
    return obj


def ff_ATT_READ_REQ(direction, handle):
    obj = {"direction": direction, "opcode": type_ATT_READ_REQ, "handle": handle}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_READ_REQ]
    return obj


def ff_ATT_READ_RSP(direction, value_hex_str):
    obj = {"direction": direction, "opcode": type_ATT_READ_RSP, "value_hex_str": value_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_READ_RSP]
    return obj


def ff_ATT_READ_BY_GROUP_TYPE_REQ(direction, start_handle, end_handle, group_type):
    obj = {"direction": direction, "opcode": type_ATT_READ_BY_GROUP_TYPE_REQ, "start_handle": start_handle, "end_handle": end_handle, "group_type": group_type}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_READ_BY_GROUP_TYPE_REQ]
    return obj


def ff_ATT_READ_BY_GROUP_TYPE_RSP_attribute_data_list(attribute_handle=None, end_group_handle=None, UUID=None):
    list_obj = {"attribute_handle": attribute_handle, "end_group_handle": end_group_handle, "UUID": UUID}
    return list_obj

# 3rd parameter should be created with def ff_ATT_READ_BY_GROUP_TYPE_RSP_attribute_data_list() above
def ff_ATT_READ_BY_GROUP_TYPE_RSP(direction, length, attribute_data_list):
    obj = {"direction": direction, "opcode": type_ATT_READ_BY_GROUP_TYPE_RSP, "length": length, "attribute_data_list": attribute_data_list}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = att_opcode_strings[type_ATT_READ_BY_GROUP_TYPE_RSP]
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_ATT_handle(bdaddr, random, data):
    tier1_data = ff_ATT_handle_enumeration(data)
    generic_SingleBDADDR_insertion_into_BTIDES_second_level_array(bdaddr, random, tier1_data, "ATTArray", data, "ATT_handle_enumeration")

# TODO: For now since we only are importing from PCAP only export to DualBDADDR
# TODO: may need to update this in the future to handle export from database to SingleBDADDR data types
def BTIDES_export_ATT_packet(connect_ind_obj, data):
    generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "ATTArray")