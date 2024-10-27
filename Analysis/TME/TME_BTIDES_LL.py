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

def ff_LL_VERSION_IND(version, company_id, subversion):
    ll_version_ind = {"opcode": 12, "version": version, "company_id": company_id, "subversion": subversion}
    return ll_version_ind

############################
# JSON insertion functions
############################

# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the LL_VERSION_IND data into a LLArray entry
#  If an existing LLArray entry already exists, this is done
#  If no LLArray exists, it creates one 
def BTIDES_insert_LL_VERSION_IND(bdaddr, random, version, company_id, subversion):
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
                if(ll_entry != None and "opcode" in ll_entry.keys() and ll_entry["opcode"] == 12 and 
                   ll_entry["version"] == version and ll_entry["company_id"] == company_id and ll_entry["subversion"] == subversion):
                    # We already have the entry we would insert, so just go ahead and return
                    print("BTIDES_insert_LL_VERSION_IND: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into LLArray 
            entry["LLArray"].append(ff_LL_VERSION_IND(version, company_id, subversion))
            ###print(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return