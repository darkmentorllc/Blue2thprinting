########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *
import TME.TME_glob

############################
# Helper "factory functions"
############################  

opcode_LMP_VERSION_RSP          = 38
opcode_LMP_FEATURES_RSP         = 40

# TODO: we need to update database to keep track of opcode so we know whether something is a REQ or RSP
def ff_LMP_VERSION_RSP(version, company_id, subversion):
    obj = {"opcode": opcode_LMP_VERSION_RSP, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_VERSION_RSP"
    return obj


# TODO: we need to update database to keep track of opcode so we know whether something is a REQ or RSP
def ff_LMP_FEATURES_RSP(features):
    lmp_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LMP_FEATURES_RSP, "lmp_features_hex_str": lmp_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LMP_FEATURES_RSP"
    return obj


############################
# JSON insertion functions
############################

def BTIDES_export_LMP_VERSION_RSP(bdaddr, version, company_id, subversion):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    data = ff_LMP_VERSION_RSP(version, company_id, subversion)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")


def BTIDES_export_LMP_FEATURES_RSP(bdaddr, features):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    data = ff_LMP_FEATURES_RSP(features)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "LMPArray")

