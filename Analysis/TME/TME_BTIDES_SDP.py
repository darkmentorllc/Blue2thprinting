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

def ff_SDP_SERVICE_SEARCH_ATTR_REQ(direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str):
    obj = {
        "direction": direction,
        "l2cap_len": l2cap_len,
        "l2cap_cid": l2cap_cid,
        "pdu_id": type_SDP_SERVICE_SEARCH_ATTR_REQ,
        "transaction_id": transaction_id,
        "param_len": param_len,
        "raw_data_hex_str": raw_data_hex_str
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["pdu_id_str"] = "SDP_SERVICE_SEARCH_ATTR_REQ"
    return obj


def ff_SDP_SERVICE_SEARCH_ATTR_RSP(direction, l2cap_len, l2cap_cid, transaction_id, param_len, raw_data_hex_str):
    obj = {
        "direction": direction,
        "l2cap_len": l2cap_len,
        "l2cap_cid": l2cap_cid,
        "pdu_id": type_SDP_SERVICE_SEARCH_ATTR_RSP,
        "transaction_id": transaction_id,
        "param_len": param_len,
        "raw_data_hex_str": raw_data_hex_str
    }
    if TME.TME_glob.verbose_BTIDES:
        obj["pdu_id_str"] = "SDP_SERVICE_SEARCH_ATTR_RSP"
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_SDP_packet(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "SDPArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "SDPArray")