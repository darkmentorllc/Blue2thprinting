########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.BT_Data_Types import *
from TME.TME_BTIDES_base import *
import TME.TME_glob

############################
# Helper "factory functions"
############################

def ff_LL_CONNECTION_UPDATE_IND(direction, win_size, win_offset, interval, latency, timeout, instant):
    obj = {"direction": direction, "opcode": type_opcode_LL_CONNECTION_UPDATE_IND, "win_size": win_size, "win_offset": win_offset, "interval": interval, "latency": latency, "timeout": timeout, "instant": instant}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_CONNECTION_UPDATE_IND"
    return obj


def ff_LL_CHANNEL_MAP_IND(direction, channel_map_hex_str, instant):
    obj = {"direction": direction, "opcode": type_opcode_LL_CHANNEL_MAP_IND, "channel_map_hex_str": channel_map_hex_str, "instant": instant}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_CHANNEL_MAP_IND"
    return obj


def ff_LL_TERMINATE_IND(direction, error_code):
    obj = {"direction": direction, "opcode": type_opcode_LL_TERMINATE_IND, "error_code": error_code}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_TERMINATE_IND"
        if error_code in controller_error_strings:
            obj["error_str"] = controller_error_strings[error_code]
    return obj


def ff_LL_ENC_REQ(direction, rand, ediv, skd_c, iv_c):
    obj = {"direction": direction, "opcode": type_opcode_LL_ENC_REQ, "rand": rand, "ediv": ediv, "skd_c": skd_c, "iv_c": iv_c}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_ENC_REQ"
    return obj


def ff_LL_ENC_RSP(direction, skd_p, iv_p):
    obj = {"direction": direction, "opcode": type_opcode_LL_ENC_RSP, "skd_p": skd_p, "iv_p": iv_p}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_ENC_RSP"
    return obj


def ff_LL_START_ENC_REQ(direction):
    obj = {"direction": direction, "opcode": type_opcode_LL_START_ENC_REQ}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_START_ENC_REQ"
    return obj


def ff_LL_START_ENC_RSP(direction):
    obj = {"direction": direction, "opcode": type_opcode_LL_START_ENC_RSP}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_START_ENC_RSP"
    return obj


def ff_LL_VERSION_IND(direction, version, company_id, subversion):
    obj = {"direction": direction, "opcode": type_opcode_LL_VERSION_IND, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_VERSION_IND"
    return obj

def ff_LL_REJECT_IND(direction, error_code):
    obj = {"direction": direction, "opcode": type_opcode_LL_REJECT_IND, "error_code": error_code}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_REJECT_IND"
        if error_code in controller_error_strings:
            obj["error_str"] = controller_error_strings[error_code]
    return obj

def ff_LL_UNKNOWN_RSP(direction, unknown_type):
    obj = {"direction": direction, "opcode": type_opcode_LL_UNKNOWN_RSP, "unknown_type": unknown_type}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_UNKNOWN_RSP"
    return obj


def ff_LL_FEATURE_REQ(direction, features):
    le_features_hex_str = f"{features:016x}"
    obj = {"direction": direction, "opcode": type_opcode_LL_FEATURE_REQ, "le_features_hex_str": le_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_FEATURE_REQ"
    return obj


def ff_LL_FEATURE_RSP(direction, features):
    le_features_hex_str = f"{features:016x}"
    obj = {"direction": direction, "opcode": type_opcode_LL_FEATURE_RSP, "le_features_hex_str": le_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_FEATURE_RSP"
    return obj


def ff_LL_PERIPHERAL_FEATURE_REQ(direction, features):
    le_features_hex_str = f"{features:016x}"
    obj = {"direction": direction, "opcode": type_opcode_LL_PERIPHERAL_FEATURE_REQ, "le_features_hex_str": le_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PERIPHERAL_FEATURE_REQ"
    return obj


def ff_LL_CONNECTION_PARAM_REQ(direction, interval_min, interval_max, latency, timeout, preferred_periodicity, reference_conneventcount, offset0, offset1, offset2, offset3, offset4, offset5):
    obj = {
        "direction": direction,
        "opcode": type_opcode_LL_CONNECTION_PARAM_REQ,
        "interval_min": interval_min,
        "interval_max": interval_max,
        "latency": latency,
        "timeout": timeout,
        "preferred_periodicity": preferred_periodicity,
        "reference_conneventcount": reference_conneventcount,
        "offset0": offset0,
        "offset1": offset1,
        "offset2": offset2,
        "offset3": offset3,
        "offset4": offset4,
        "offset5": offset5
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_CONNECTION_PARAM_REQ"
    return obj


def ff_LL_CONNECTION_PARAM_RSP(direction, interval_min, interval_max, latency, timeout, preferred_periodicity, reference_conneventcount, offset0, offset1, offset2, offset3, offset4, offset5):
    obj = {
        "direction": direction,
        "opcode": type_opcode_LL_CONNECTION_PARAM_RSP,
        "interval_min": interval_min,
        "interval_max": interval_max,
        "latency": latency,
        "timeout": timeout,
        "preferred_periodicity": preferred_periodicity,
        "reference_conneventcount": reference_conneventcount,
        "offset0": offset0,
        "offset1": offset1,
        "offset2": offset2,
        "offset3": offset3,
        "offset4": offset4,
        "offset5": offset5
    }
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_CONNECTION_PARAM_RSP"
    return obj


def ff_LL_REJECT_EXT_IND(direction, reject_opcode, error_code):
    obj = {"direction": direction, "opcode": type_opcode_LL_REJECT_EXT_IND, "reject_opcode": reject_opcode, "error_code": error_code}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_REJECT_EXT_IND"
        if error_code in controller_error_strings:
            obj["error_str"] = controller_error_strings[error_code]
    return obj


def ff_LL_PING_REQ(direction):
    obj = {"direction": direction, "opcode": type_opcode_LL_PING_REQ}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PING_REQ"
    return obj


def ff_LL_PING_RSP(direction):
    obj = {"direction": direction, "opcode": type_opcode_LL_PING_RSP}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PING_RSP"
    return obj


def ff_LL_LENGTH_REQ(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time):
    obj = {"direction": direction, "opcode": type_opcode_LL_LENGTH_REQ, "max_rx_octets": max_rx_octets, "max_rx_time": max_rx_time, "max_tx_octets": max_tx_octets, "max_tx_time": max_tx_time}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_LENGTH_REQ"
    return obj


def ff_LL_LENGTH_RSP(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time):
    obj = {"direction": direction, "opcode": type_opcode_LL_LENGTH_RSP, "max_rx_octets": max_rx_octets, "max_rx_time": max_rx_time, "max_tx_octets": max_tx_octets, "max_tx_time": max_tx_time}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_LENGTH_RSP"
    return obj


def ff_LL_PHY_REQ(direction, tx_phys, rx_phys):
    obj = {"direction": direction, "opcode": type_opcode_LL_PHY_REQ, "TX_PHYS": tx_phys, "RX_PHYS": rx_phys}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PHY_REQ"
    return obj


def ff_LL_PHY_RSP(direction, tx_phys, rx_phys):
    obj = {"direction": direction, "opcode": type_opcode_LL_PHY_RSP, "TX_PHYS": tx_phys, "RX_PHYS": rx_phys}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PHY_RSP"
    return obj


def ff_LL_PHY_UPDATE_IND(direction, phy_c_to_p, phy_p_to_c, instant):
    obj = {"direction": direction, "opcode": type_opcode_LL_PHY_UPDATE_IND, "phy_c_to_p": phy_c_to_p, "phy_p_to_c": phy_p_to_c, "instant": instant}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PHY_UPDATE_IND"
    return obj


############################
# JSON insertion functions
############################

def BTIDES_export_LLArray_entry(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")