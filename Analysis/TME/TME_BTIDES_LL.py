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

def ff_LL_VERSION_IND(direction, version, company_id, subversion):
    obj = {"direction": direction, "opcode": type_opcode_LL_VERSION_IND, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_VERSION_IND"
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


############################
# JSON insertion functions
############################

def BTIDES_export_LL_UNKNOWN_RSP(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_FEATURE_RSP(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_FEATURE_REQ(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_PERIPHERAL_FEATURE_REQ(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_VERSION_IND(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_PING_RSP(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")

def BTIDES_export_LL_PING_REQ(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_LENGTH_REQ(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_LENGTH_RSP(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_PHY_REQ(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")


def BTIDES_export_LL_PHY_RSP(bdaddr=None, random=None, connect_ind_obj=None, data=None):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "LLArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "LLArray")

