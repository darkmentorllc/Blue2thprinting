########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import re
from TME.TME_BTIDES_base import *
from TME.TME_glob import BTIDES_JSON

############################
# Helper "factory functions"
############################  

opcode_ATT_EXCHANGE_MTU_REQ          = 2
opcode_ATT_EXCHANGE_MTU_RSP          = 3

status_SUCCESS = 0

def ff_ATT_handle_enumeration(handle_entry_obj):    
    obj = {"ATT_handle_enumeration": [ handle_entry_obj ]}
    return obj

# TODO: we need to update database to keep track of status
def ff_ATT_handle_entry(handle, UUID):    
    obj = {"handle": handle, "UUID": UUID}
    return obj

# TODO: Pretty sure this is where OO programming would save me a lot of copy-paste...
############################
# JSON insertion functions
############################
# All functions follow this flow:
# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the data into a ATTArray entry
#  If an existing ATTArray entry already exists, this is done
#  If no ATTArray exists, it creates one

def BTIDES_export_ATT_handles(bdaddr, random, handle, UUID):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    UUID = convert_UUID128_to_UUID16_if_possible(UUID) # Save space on exported data if possible
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        att_enum_obj = ff_ATT_handle_enumeration(ff_ATT_handle_entry(handle, UUID))
        base["ATTArray"] = [ att_enum_obj ] 
        #print(json.dumps(base, indent=2))
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("ATTArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any ATTArray entries, so just insert ours
            att_enum_obj = ff_ATT_handle_enumeration(ff_ATT_handle_entry(handle, UUID))
            entry["ATTArray"] = [ att_enum_obj ]
            return
        else:
            # There is an entry for this BDADDR, and ATTArray entries, so check if ours already exists, and if so, we're done
            for att_entry in entry["ATTArray"]:
                ###print(att_entry)
                if(att_entry != None and "ATT_handle_enumeration" in att_entry.keys()):
                    # This att_entry has an ATT_handle_enumeration
                    # Now check if there's an entry that exactly matches 
                    for att_handle_entry in att_entry["ATT_handle_enumeration"]:
                        # TODO: pass through length in the future
                        if(att_handle_entry != None and "handle" in att_handle_entry.keys() and att_handle_entry["handle"] == handle and
                           "UUID" in att_handle_entry.keys() and att_handle_entry["UUID"] == UUID):
                            # We already have the entry we would insert, so just go ahead and return
                            ###print("BTIDES_export_TxPower: found existing match. Nothing to do. Returning.")
                            ###print(json.dumps(BTIDES_JSON, indent=2))
                            return
                    # If we got here we didn't find any match, so we now need to insert our entry
                    # Insert into inner ATT_handle_enumeration
                    # This should be the most common case when inserting successive handle entries
                    att_entry["ATT_handle_enumeration"].append(ff_ATT_handle_entry(handle, UUID))
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # Insert new ATT_handle_enumeration into outer ATTArray
            att_enum_obj = ff_ATT_handle_enumeration(ff_ATT_handle_entry(handle, UUID))
            entry["ATTArray"].append(att_enum_obj)
            #print(json.dumps(BTIDES_JSON, indent=2))
            return
