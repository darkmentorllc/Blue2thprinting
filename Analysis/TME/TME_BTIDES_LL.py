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

opcode_LL_UNKNOWN_RSP =             7
opcode_LL_FEATURE_REQ =             8
opcode_LL_FEATURE_RSP =             9
opcode_LL_VERSION_IND =             12
opcode_LL_PERIPHERAL_FEATURE_REQ =  14

############################
# Helper "factory functions"
############################  

def ff_LL_VERSION_IND(version, company_id, subversion):
    obj = {"opcode": opcode_LL_VERSION_IND, "version": version, "company_id": company_id, "subversion": subversion}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_VERSION_IND"
    return obj

def ff_LL_UNKNOWN_RSP(unknown_type):
    obj = {"opcode": opcode_LL_UNKNOWN_RSP, "unknown_type": unknown_type}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_UNKNOWN_RSP"
    return obj

def ff_LL_FEATURE_REQ(features):
    le_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LL_FEATURE_REQ, "le_features_hex_str": le_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_FEATURE_REQ"
    return obj

def ff_LL_FEATURE_RSP(features):
    le_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LL_FEATURE_RSP, "le_features_hex_str": le_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_FEATURE_RSP"
    return obj

def ff_LL_PERIPHERAL_FEATURE_REQ(features):
    le_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LL_PERIPHERAL_FEATURE_REQ, "le_features_hex_str": le_features_hex_str}
    if(TME.TME_glob.verbose_BTIDES):
        obj["opcode_str"] = "LL_PERIPHERAL_FEATURE_REQ"
    return obj


############################
# JSON insertion functions
############################

# TODO: Pretty sure this is where OO programming would save me a lot of copy-paste...

# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the LL_UNKNOWN_RSP data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one
def BTIDES_export_LL_UNKNOWN_RSP(bdaddr, random, unknown_type):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_UNKNOWN_RSP(unknown_type) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_UNKNOWN_RSP(unknown_type) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_UNKNOWN_RSP and 
                   ll_entry["unknown_type"] == unknown_type):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LL_UNKNOWN_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray 
            entry["LLArray"].append(ff_LL_UNKNOWN_RSP(unknown_type))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return

# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the LL_FEATURE_RSP data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one
def BTIDES_export_LL_FEATURE_RSP(bdaddr, random, features):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_FEATURE_RSP(features) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_FEATURE_RSP(features) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_FEATURE_RSP and 
                   ll_entry["le_features_hex_str"] == f"{features:016x}"):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LL_FEATURE_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray 
            entry["LLArray"].append(ff_LL_FEATURE_RSP(features))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return

# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the LL_FEATURE_RSP data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one
def BTIDES_export_LL_FEATURE_REQ(bdaddr, random, features):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_FEATURE_REQ(features) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_FEATURE_REQ(features) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_FEATURE_REQ and 
                   ll_entry["le_features_hex_str"] == f"{features:016x}"):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LL_FEATURE_REQ: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray 
            entry["LLArray"].append(ff_LL_FEATURE_REQ(features))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return

# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the LL_FEATURE_RSP data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one
def BTIDES_export_LL_PERIPHERAL_FEATURE_REQ(bdaddr, random, features):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_PERIPHERAL_FEATURE_REQ(features) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_PERIPHERAL_FEATURE_REQ(features) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_PERIPHERAL_FEATURE_REQ and 
                   ll_entry["le_features_hex_str"] == f"{features:016x}"):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LL_PERIPHERAL_FEATURE_REQ: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray 
            entry["LLArray"].append(ff_LL_PERIPHERAL_FEATURE_REQ(features))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return

# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the LL_VERSION_IND data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one
def BTIDES_export_LL_VERSION_IND(bdaddr, random, version, company_id, subversion):
    global BTIDES_JSON
    ###print(TME.TME_glob.BTIDES_JSON)
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_VERSION_IND(version, company_id, subversion) ]
        TME.TME_glob.BTIDES_JSON.append(base)
        ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_VERSION_IND(version, company_id, subversion) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_VERSION_IND and 
                   ll_entry["version"] == version and ll_entry["company_id"] == company_id and ll_entry["subversion"] == subversion):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray 
            entry["LLArray"].append(ff_LL_VERSION_IND(version, company_id, subversion))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return