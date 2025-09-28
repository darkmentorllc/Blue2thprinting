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

def ff_L2CAP_CONNECTION_REQ(direction, id, data_len, psm, source_cid):
    obj = {
        "code": type_L2CAP_CONNECTION_REQ,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "psm": psm,
        "source_cid": source_cid
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_CONNECTION_REQ"
        if(psm in type_PSM_strings):
            obj["psm_str"] = type_PSM_strings[psm]
    return obj


def ff_L2CAP_CONNECTION_RSP(direction, id, data_len, destination_cid, source_cid, result, status):
    obj = {
        "code": type_L2CAP_CONNECTION_RSP,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "destination_cid": destination_cid,
        "source_cid": source_cid,
        "result": result,
        "status": status
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_CONNECTION_RSP"
        if(result in type_L2CAP_CONNECTION_RSP_result_strings):
            obj["result_str"] = type_L2CAP_CONNECTION_RSP_result_strings[result]
        if(result == type_L2CAP_CONNECTION_RSP_result_pending and status in type_L2CAP_CONNECTION_RSP_status_strings):
            obj["status_str"] = type_L2CAP_CONNECTION_RSP_status_strings[status]
    return obj


def ff_L2CAP_CONFIGURATION_REQ(direction, id, data_len, destination_cid, flags, config_options_hex_str):
    obj = {
        "code": type_L2CAP_CONFIGURATION_REQ,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "destination_cid": destination_cid,
        "flags": flags
    }
    if(config_options_hex_str is not None):
        obj["config_options_hex_str"] = config_options_hex_str
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_CONFIGURATION_REQ"
    return obj


def ff_L2CAP_CONFIGURATION_RSP(direction, id, data_len, source_cid, flags, result, config_options_hex_str):
    obj = {
        "code": type_L2CAP_CONFIGURATION_RSP,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "source_cid": source_cid,
        "flags": flags,
        "result": result
    }
    if(config_options_hex_str is not None):
        obj["config_options_hex_str"] = config_options_hex_str
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_CONFIGURATION_RSP"
        if(result in type_L2CAP_CONFIGURATION_RSP_result_strings):
            obj["result_str"] = type_L2CAP_CONFIGURATION_RSP_result_strings[result]
    return obj

def ff_L2CAP_DISCONNECTION_REQ(direction, id, data_len, destination_cid, source_cid):
    obj = {
        "code": type_L2CAP_DISCONNECTION_REQ,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "destination_cid": destination_cid,
        "source_cid": source_cid
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_DISCONNECTION_REQ"
    return obj


def ff_L2CAP_DISCONNECTION_RSP(direction, id, data_len, destination_cid, source_cid):
    obj = {
        "code": type_L2CAP_DISCONNECTION_RSP,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "destination_cid": destination_cid,
        "source_cid": source_cid
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_DISCONNECTION_RSP"
    return obj


def ff_L2CAP_INFORMATION_REQ(direction, id, data_len, info_type):
    obj = {
        "code": type_L2CAP_INFORMATION_REQ,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "info_type": info_type
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_INFORMATION_REQ"
    return obj


def ff_L2CAP_INFORMATION_RSP(direction, id, data_len, info_type, result, info_hex_str=None):
    obj = {
        "code": type_L2CAP_INFORMATION_RSP,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "info_type": info_type,
        "result": result
    }
    if info_hex_str is not None:
        obj["info_hex_str"] = info_hex_str
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_INFORMATION_RSP"
    return obj

def ff_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(direction, id, data_len, interval_min, interval_max, latency, timeout):
    obj = {
        "code": type_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "interval_min": interval_min,
        "interval_max": interval_max,
        "latency": latency,
        "timeout": timeout
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_CONNECTION_PARAMETER_UPDATE_REQ"
    return obj

def ff_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(direction, id, data_len, result):
    obj = {
        "code": type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP,
        "direction": direction,
        "id": id,
        "data_len": data_len,
        "result": result
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["code_str"] = "L2CAP_CONNECTION_PARAMETER_UPDATE_RSP"
        if result in type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result_strings:
            obj["result_str"] = type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP_result_strings[result]
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_L2CAP_packet(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "L2CAPArray")
    else:
        # Can't have random be None for exported entries (as it now is by default after Ticket #19), so look it up if needed
        if(random == None):
            random = is_bdaddr_le_and_random(bdaddr)
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "L2CAPArray")