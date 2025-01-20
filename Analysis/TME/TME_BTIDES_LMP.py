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

# TODO: we need to update database to keep track of opcode so we know whether something is a REQ or RSP
def ff_LMP_VERSION_RES(version, company_id, subversion):
    obj = {"opcode": type_opcode_LMP_VERSION_RES, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_VERSION_RES"
    return obj


# TODO: we need to update database to keep track of opcode so we know whether something is a REQ or RSP
def ff_LMP_FEATURES_RES(features):
    lmp_features_hex_str = f"{features:016x}"
    obj = {"opcode": type_opcode_LMP_FEATURES_RES, "lmp_features_hex_str": lmp_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_FEATURES_RES"
    return obj

def ff_LMP_FEATURES_RES_EXT(page, max_page, features):
    lmp_features_hex_str = f"{features:016x}"
    obj = {"opcode": type_opcode_LMP_FEATURES_RES_EXT, "extended_opcode": type_extended_opcode_LMP_FEATURES_RES_EXT, "page": page, "max_page": max_page, "lmp_features_hex_str": lmp_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_FEATURES_RES_EXT"
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_LMP_VERSION_RES(bdaddr, version, company_id, subversion):
    global BTIDES_JSON
    data = ff_LMP_VERSION_RES(version, company_id, subversion)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_RES(bdaddr, features):
    global BTIDES_JSON
    data = ff_LMP_FEATURES_RES(features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_RES_EXT(bdaddr, page, max_page, features):
    global BTIDES_JSON
    data = ff_LMP_FEATURES_RES_EXT(page, max_page, features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")

