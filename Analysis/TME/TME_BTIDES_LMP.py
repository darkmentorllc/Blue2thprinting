########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import json
import TME.TME_glob
from TME.TME_BTIDES_base import *

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

# TODO: Pretty sure this is where OO programming would save me a lot of copy-paste...
############################
# JSON insertion functions
############################
# All functions follow this flow:
# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the data into a LMPArray entry
#  If an existing LMPArray entry already exists, this is done
#  If no LMPArray exists, it creates one

def BTIDES_export_LMP_VERSION_RSP(bdaddr, version, company_id, subversion):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, 0)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, 0)
        ###print(json.dumps(acd, indent=2))
        base["LMPArray"] = [ ff_LMP_VERSION_RSP(version, company_id, subversion) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LMPArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LMPArray entries, so just insert ours
            entry["LMPArray"] = [ ff_LMP_VERSION_RSP(version, company_id, subversion) ]
            return
        else:
            # There is an entry for this BDADDR, and LMPArray entries, so check if ours already exists, and if so, we're done
            for lmp_entry in entry["LMPArray"]:
                ###print(AdvChanEntry)
                if(lmp_entry != None and "opcode" in lmp_entry.keys() and lmp_entry["opcode"] == opcode_LMP_VERSION_RSP and 
                   lmp_entry["version"] == version and lmp_entry["company_id"] == company_id and lmp_entry["subversion"] == subversion):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LMP_VERSION_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LMPArray 
            entry["LMPArray"].append(ff_LMP_VERSION_RSP(version, company_id, subversion))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return

def BTIDES_export_LMP_FEATURES_RSP(bdaddr, features):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, 0)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, 0)
        ###print(json.dumps(acd, indent=2))
        base["LMPArray"] = [ ff_LMP_FEATURES_RSP(features) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LMPArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LMPArray entries, so just insert ours
            entry["LMPArray"] = [ ff_LMP_FEATURES_RSP(features) ]
            return
        else:
            # There is an entry for this BDADDR, and LMPArray entries, so check if ours already exists, and if so, we're done
            for lmp_entry in entry["LMPArray"]:
                ###print(AdvChanEntry)
                if(lmp_entry != None and "opcode" in lmp_entry.keys() and lmp_entry["opcode"] == opcode_LMP_FEATURES_RSP and 
                   lmp_entry["le_features_hex_str"] == f"{features:016x}"):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LMP_FEATURES_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LMPArray 
            entry["LMPArray"].append(ff_LMP_FEATURES_RSP(features))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return