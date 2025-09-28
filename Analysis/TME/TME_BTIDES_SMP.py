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
from TME.TME_helpers import get_utf8_string_from_hex_string, is_bdaddr_le_and_random

############################
# Helper "factory functions"
############################

def ff_SMP_Pairing_Request(direction, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist):
    obj = {
        "opcode": type_SMP_Pairing_Request,
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
        "opcode": type_SMP_Pairing_Response,
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


def ff_SMP_Pairing_Confirm(direction, value_hex_str):
    obj = {
        "opcode": type_SMP_Pairing_Confirm,
        "direction": direction,
        "value_hex_str": value_hex_str
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj


def ff_SMP_Pairing_Random(direction, value_hex_str):
    obj = {
        "opcode": type_SMP_Pairing_Random,
        "direction": direction,
        "value_hex_str": value_hex_str
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj


def ff_SMP_Pairing_Failed(direction, reason):
    obj = {
        "opcode": type_SMP_Pairing_Failed,
        "direction": direction,
        "reason": reason
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
        obj["reason_str"] = smp_error_strings[obj["reason"]]
    return obj

def ff_SMP_Security_Request(direction, auth_req):
    obj = {
        "opcode": type_SMP_Security_Request,
        "direction": direction,
        "auth_req": auth_req
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj


def ff_SMP_Pairing_Public_Key(direction, pub_key_x_hex_str, pub_key_y_hex_str):
    obj = {
        "opcode": type_SMP_Pairing_Public_Key,
        "direction": direction,
        "pub_key_x_hex_str": pub_key_x_hex_str,
        "pub_key_y_hex_str": pub_key_y_hex_str
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj


def ff_SMP_Pairing_DHKey_Check(direction, value_hex_str):
    obj = {
        "opcode": type_SMP_Pairing_DHKey_Check,
        "direction": direction,
        "value_hex_str": value_hex_str
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
    return obj


def ff_SMP_Pairing_Keypress_Notification(direction, notification_type):
    obj = {
        "opcode": type_SMP_Pairing_Keypress_Notification,
        "direction": direction,
        "notification_type": notification_type
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = smp_opcode_strings[obj["opcode"]]
        obj["notification_type_str"] = smp_keypress_notification_strings[obj["notification_type"]]
    return obj


############################
# JSON insertion functions
############################

def BTIDES_export_SMP_packet(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "SMPArray")
    else:
        # Can't have random be None for exported entries (as it now is by default after Ticket #19), so look it up if needed
        if(random == None):
            random = is_bdaddr_le_and_random(bdaddr)
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "SMPArray")