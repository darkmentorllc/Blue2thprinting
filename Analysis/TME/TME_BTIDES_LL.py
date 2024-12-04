########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

opcode_LL_UNKNOWN_RSP               = 7
opcode_LL_FEATURE_REQ               = 8
opcode_LL_FEATURE_RSP               = 9
opcode_LL_VERSION_IND               = 12
opcode_LL_PERIPHERAL_FEATURE_REQ    = 14
opcode_LL_PING_REQ                  = 18
opcode_LL_PING_RSP                  = 19
opcode_LL_LENGTH_REQ                = 20
opcode_LL_LENGTH_RSP                = 21
opcode_LL_PHY_REQ                   = 22
opcode_LL_PHY_RSP                   = 23

############################
# Helper "factory functions"
############################  

def ff_LL_VERSION_IND(version, company_id, subversion):
    obj = {"opcode": opcode_LL_VERSION_IND, "version": version, "company_id": company_id, "subversion": subversion}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_VERSION_IND"
    return obj

def ff_LL_UNKNOWN_RSP(unknown_type):
    obj = {"opcode": opcode_LL_UNKNOWN_RSP, "unknown_type": unknown_type}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_UNKNOWN_RSP"
    return obj

def ff_LL_FEATURE_REQ(features):
    le_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LL_FEATURE_REQ, "le_features_hex_str": le_features_hex_str}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_FEATURE_REQ"
    return obj

def ff_LL_FEATURE_RSP(features):
    le_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LL_FEATURE_RSP, "le_features_hex_str": le_features_hex_str}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_FEATURE_RSP"
    return obj

def ff_LL_PERIPHERAL_FEATURE_REQ(features):
    le_features_hex_str = f"{features:016x}"
    obj = {"opcode": opcode_LL_PERIPHERAL_FEATURE_REQ, "le_features_hex_str": le_features_hex_str}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_PERIPHERAL_FEATURE_REQ"
    return obj

def ff_LL_PING_REQ():
    obj = {"opcode": opcode_LL_PING_REQ}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_PING_REQ"
    return obj

def ff_LL_PING_RSP():
    obj = {"opcode": opcode_LL_PING_RSP}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_PING_RSP"
    return obj

def ff_LL_LENGTH_REQ(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time):
    obj = {"opcode": opcode_LL_LENGTH_REQ, "max_rx_octets": max_rx_octets, "max_rx_time": max_rx_time, "max_tx_octets": max_tx_octets, "max_tx_time": max_tx_time}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_LENGTH_REQ"
    return obj

def ff_LL_LENGTH_RSP(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time):
    obj = {"opcode": opcode_LL_LENGTH_RSP, "max_rx_octets": max_rx_octets, "max_rx_time": max_rx_time, "max_tx_octets": max_tx_octets, "max_tx_time": max_tx_time}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_LENGTH_RSP"
    return obj

def ff_LL_PHY_REQ(tx_phys, rx_phys):
    obj = {"opcode": opcode_LL_PHY_REQ, "TX_PHYS": tx_phys, "RX_PHYS": rx_phys}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_PHY_REQ"
    return obj

def ff_LL_PHY_RSP(tx_phys, rx_phys):
    obj = {"opcode": opcode_LL_PHY_RSP, "TX_PHYS": tx_phys, "RX_PHYS": rx_phys}
    if(verbose_BTIDES):
        obj["opcode_str"] = "LL_PHY_RSP"
    return obj


# TODO: Pretty sure this is where OO programming would save me a lot of copy-paste...
############################
# JSON insertion functions
############################
# All functions follow this flow:
# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one

def BTIDES_export_LL_UNKNOWN_RSP(bdaddr, random, unknown_type):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_UNKNOWN_RSP(unknown_type) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
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
                    #print("BTIDES_export_LL_UNKNOWN_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_UNKNOWN_RSP(unknown_type))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_FEATURE_RSP(bdaddr, random, features):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_FEATURE_RSP(features) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
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
                    #print("BTIDES_export_LL_FEATURE_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_FEATURE_RSP(features))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_FEATURE_REQ(bdaddr, random, features):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_FEATURE_REQ(features) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
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
                    #print("BTIDES_export_LL_FEATURE_REQ: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_FEATURE_REQ(features))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_PERIPHERAL_FEATURE_REQ(bdaddr, random, features):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_PERIPHERAL_FEATURE_REQ(features) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
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
                    #print("BTIDES_export_LL_PERIPHERAL_FEATURE_REQ: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_PERIPHERAL_FEATURE_REQ(features))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_VERSION_IND(bdaddr, random, version, company_id, subversion):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_VERSION_IND(version, company_id, subversion) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
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
                    #print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_VERSION_IND(version, company_id, subversion))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_PING_RSP(bdaddr, random):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_PING_RSP() ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_PING_RSP() ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_PING_RSP):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_PING_RSP())
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_LENGTH_REQ(bdaddr, random, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_LENGTH_REQ(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_LENGTH_REQ(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_LENGTH_REQ and
                   "max_rx_octets" in ll_entry.keys() and ll_entry["max_rx_octets"] == max_rx_octets and
                   "max_rx_time" in ll_entry.keys() and ll_entry["max_rx_time"] == max_rx_time and
                   "max_tx_octets" in ll_entry.keys() and ll_entry["max_tx_octets"] == max_tx_octets and
                   "max_tx_time" in ll_entry.keys() and ll_entry["max_tx_time"] == max_tx_time):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_LENGTH_REQ(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_LENGTH_RSP(bdaddr, random, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_LENGTH_RSP(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_LENGTH_RSP(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_LENGTH_RSP and
                   "max_rx_octets" in ll_entry.keys() and ll_entry["max_rx_octets"] == max_rx_octets and
                   "max_rx_time" in ll_entry.keys() and ll_entry["max_rx_time"] == max_rx_time and
                   "max_tx_octets" in ll_entry.keys() and ll_entry["max_tx_octets"] == max_tx_octets and
                   "max_tx_time" in ll_entry.keys() and ll_entry["max_tx_time"] == max_tx_time):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_LENGTH_RSP(max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))
            print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_PHY_REQ(bdaddr, random, tx_phys, rx_phys):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_PHY_REQ(tx_phys, rx_phys) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_PHY_REQ(tx_phys, rx_phys) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_PHY_REQ and
                   "TX_PHYS" in ll_entry.keys() and ll_entry["TX_PHYS"] == tx_phys and
                   "RX_PHYS" in ll_entry.keys() and ll_entry["RX_PHYS"] == rx_phys):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_PHY_REQ(tx_phys, rx_phys))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_LL_PHY_RSP(bdaddr, random, tx_phys, rx_phys):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(acd, indent=2))
        base["LLArray"] = [ ff_LL_PHY_RSP(tx_phys, rx_phys) ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("LLArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any LLArray entries, so just insert ours
            entry["LLArray"] = [ ff_LL_PHY_RSP(tx_phys, rx_phys) ]
            return
        else:
            # There is an entry for this BDADDR, and LLArray entries, so check if ours already exists, and if so, we're done
            for ll_entry in entry["LLArray"]:
                ###print(AdvChanEntry)
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode_LL_PHY_RSP and
                   "TX_PHYS" in ll_entry.keys() and ll_entry["TX_PHYS"] == tx_phys and
                   "RX_PHYS" in ll_entry.keys() and ll_entry["RX_PHYS"] == rx_phys):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray
            entry["LLArray"].append(ff_LL_PHY_RSP(tx_phys, rx_phys))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return