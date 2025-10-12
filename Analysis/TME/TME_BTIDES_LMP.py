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

def ff_LMP_ACCEPTED(rcvd_opcode):
    obj = {"opcode": type_LMP_ACCEPTED, "rcvd_opcode": rcvd_opcode}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_ACCEPTED"
        obj["rcvd_opcode_str"] = lmp_pdu_opcodes_to_strings.get(rcvd_opcode, "UNKNOWN_OPCODE")
    return obj


def ff_LMP_NOT_ACCEPTED(rcvd_opcode, error_code):
    obj = {"opcode": type_LMP_NOT_ACCEPTED, "rcvd_opcode": rcvd_opcode, "error_code": error_code}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_NOT_ACCEPTED"
        obj["rcvd_opcode_str"] = lmp_pdu_opcodes_to_strings.get(rcvd_opcode, "UNKNOWN_OPCODE")
        obj["error_code_str"] = controller_error_strings.get(error_code, "UNKNOWN_ERROR_CODE")
    return obj


# TODO: ideally we should have unified REQ/REQ tables in the db, but for now I just make separate ones for rapidity
def ff_LMP_VERSION_REQ(version, company_id, subversion):
    obj = {"opcode": type_LMP_VERSION_REQ, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_VERSION_REQ"
    return obj


def ff_LMP_VERSION_RES(version, company_id, subversion):
    obj = {"opcode": type_LMP_VERSION_RES, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_VERSION_RES"
    return obj


# TODO: ideally we should have unified REQ/REQ tables in the db, but for now I just make separate ones for rapidity
def ff_LMP_FEATURES_REQ(features):
    lmp_features_hex_str = f"{features:016x}"
    obj = {"opcode": type_LMP_FEATURES_REQ, "lmp_features_hex_str": lmp_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_FEATURES_REQ"
    return obj


def ff_LMP_FEATURES_RES(features):
    lmp_features_hex_str = f"{features:016x}"
    obj = {"opcode": type_LMP_FEATURES_RES, "lmp_features_hex_str": lmp_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_FEATURES_RES"
    return obj


def ff_LMP_FEATURES_RES_EXT(page, max_page, features):
    lmp_features_hex_str = f"{features:016x}"
    obj = {"opcode": type_LMP_ESCAPE_127, "extended_opcode": type_ext_opcode_LMP_FEATURES_RES_EXT, "page": page, "max_page": max_page, "lmp_features_hex_str": lmp_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_FEATURES_RES_EXT"
    return obj


# Used for all the LMP_*2 type data definitions which just copy the entire packet (minus opcode) as a hex string
def ff_LMP_generic_full_pkt_hex_str(opcode, full_pkt_hex_str):
    obj = {"opcode": opcode, "full_pkt_hex_str": full_pkt_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = lmp_pdu_opcodes_to_strings[opcode]
    return obj


############################
# JSON insertion functions
############################

def BTIDES_export_LMP_ACCEPTED(bdaddr, rcvd_opcode):
    global BTIDES_JSON
    data = ff_LMP_ACCEPTED(rcvd_opcode)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_NOT_ACCEPTED(bdaddr, rcvd_opcode, error_code):
    global BTIDES_JSON
    data = ff_LMP_NOT_ACCEPTED(rcvd_opcode, error_code)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_VERSION_REQ(bdaddr, version, company_id, subversion):
    global BTIDES_JSON
    data = ff_LMP_VERSION_REQ(version, company_id, subversion)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_VERSION_RES(bdaddr, version, company_id, subversion):
    global BTIDES_JSON
    data = ff_LMP_VERSION_RES(version, company_id, subversion)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_REQ(bdaddr, features):
    global BTIDES_JSON
    data = ff_LMP_FEATURES_REQ(features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_RES(bdaddr, features):
    global BTIDES_JSON
    data = ff_LMP_FEATURES_RES(features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_RES_EXT(bdaddr, page, max_page, features):
    global BTIDES_JSON
    data = ff_LMP_FEATURES_RES_EXT(page, max_page, features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_RES(bdaddr, features):
    global BTIDES_JSON
    data = ff_LMP_FEATURES_RES(features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_generic_full_pkt_hex_str(bdaddr, opcode, full_pkt_hex_str):
    global BTIDES_JSON
    data = ff_LMP_generic_full_pkt_hex_str(opcode, full_pkt_hex_str)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")
