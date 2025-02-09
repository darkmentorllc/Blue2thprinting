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
from TME.TME_helpers import get_utf8_string_from_hex_string

############################
# Helper "factory functions"
############################

def ff_SMP_Pairing_Request(direction, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist):
    obj = {
        "opcode": type_opcode_SMP_Pairing_Request,
        "direction": direction,
        "io_cap": io_cap,
        "oob_data": oob_data,
        "auth_req": auth_req,
        "max_key_size": max_key_size,
        "initiator_key_dist": initiator_key_dist,
        "responder_key_dist": responder_key_dist
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj


def ff_SMP_Pairing_Response(direction, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist):
    obj = {
        "opcode": type_opcode_SMP_Pairing_Response,
        "direction": direction,
        "io_cap": io_cap,
        "oob_data": oob_data,
        "auth_req": auth_req,
        "max_key_size": max_key_size,
        "initiator_key_dist": initiator_key_dist,
        "responder_key_dist": responder_key_dist
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_SMP_packet(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "SMPArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "SMPArray")