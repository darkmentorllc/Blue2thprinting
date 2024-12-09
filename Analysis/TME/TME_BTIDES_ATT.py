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


def ff_ATT_READ_REQ(handle, direction):
    obj = {"opcode": type_ATT_READ_REQ, "direction": direction, "handle": handle}
    if(TME.TME_glob.BTIDES_JSON):
        obj["opcode_str"] = att_opcode_strings[type_ATT_READ_REQ]
    return obj


def ff_ATT_READ_RSP(value_hex_str, direction):
    obj = {"opcode": type_ATT_READ_RSP, "direction": direction, "value_hex_str": value_hex_str}
    if(TME.TME_glob.BTIDES_JSON):
        obj["opcode_str"] = att_opcode_strings[type_ATT_READ_RSP]
    return obj


############################
# JSON insertion functions
############################

def BTIDES_export_ATT_handle(bdaddr, random, data):
    tier1_data = ff_ATT_handle_enumeration(data)
    generic_SingleBDADDR_insertion_into_BTIDES_second_level_array(bdaddr, random, tier1_data, "ATTArray", data, "ATT_handle_enumeration")

# def BTIDES_export_ATT_READ_REQ(connect_ind_obj, handle):
#     # Insert entries directly in the ATTArray
#     tier1_data = ff_ATT_READ_REQ(handle)
#     generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, tier1_data, "ATTArray")

# def BTIDES_export_ATT_READ_RSP(connect_ind_obj, UUID):
#     # Insert entries directly in the ATTArray
#     tier1_data = ff_ATT_READ_RSP(UUID)
#     generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, tier1_data, "ATTArray")

def BTIDES_export_ATT_packet(connect_ind_obj, type, data):
    if type == type_ATT_READ_REQ:
        tier1_data = data
    elif type == type_ATT_READ_RSP:
        tier1_data = data
    else:
        raise ValueError("Unsupported ATT packet type")
    generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, tier1_data, "ATTArray")