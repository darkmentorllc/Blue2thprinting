########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import re
#import TME.TME_glob
from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

############################
# Helper "factory functions"
############################  

opcode_ATT_EXCHANGE_MTU_REQ          = 2
opcode_ATT_EXCHANGE_MTU_RSP          = 3

status_SUCCESS = 0

def ff_GATT_Service(utype, begin_handle, end_handle, UUID):
    obj = {"utype": utype, "begin_handle": begin_handle, "end_handle": end_handle, "UUID": UUID}
    if(verbose_BTIDES):
        if(utype == 0):
            obj["type_str"] = "Primary Service"
        elif(utype == 1):
            obj["type_str"] = "Secondary Service"
    return obj

# TODO: Pretty sure this is where OO programming would save me a lot of copy-paste...
############################
# JSON insertion functions
############################
# All functions follow this flow:
# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the data into a GATTArray entry
#  If an existing GATTArray entry already exists, this is done
#  If no GATTArray exists, it creates one

def db_service_type_to_BTIDES_utype(db_service_type):
    if(db_service_type == 0):
        return "2800"
    elif(db_service_type == 1):
        return "2801"
    else:
        print("UNKNOWN SERVICE_TYPE. FIX THE CODE")
        exit(-1)

def BTIDES_export_GATT_Services(bdaddr, random, service_type, begin_handle, end_handle, UUID):
    global BTIDES_JSON
    print("foo")
    ###print(BTIDES_JSON)
    UUID = convert_UUID128_to_UUID16_if_possible(UUID) # Save space on exported data if possible
    utype = db_service_type_to_BTIDES_utype(service_type)
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        base["GATTArray"] = [ ff_GATT_Service(utype, begin_handle, end_handle, UUID) ] 
        #print(json.dumps(base, indent=2))
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("GATTArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any GATTArray entries, so just insert ours
            entry["GATTArray"] = [ ff_GATT_Service(utype, begin_handle, end_handle, UUID) ]
            return
        else:
            # There is an entry for this BDADDR, and GATTArray entries, so check if ours already exists, and if so, we're done
            for service_entry in entry["GATTArray"]:
                ###print(AdvChanEntry)
                if(service_entry != None and "opcode" in service_entry.keys() and service_entry["utype"] == utype and 
                   "begin_handle" in service_entry.keys() and service_entry["begin_handle"] == begin_handle and
                   "end_handle" in service_entry.keys() and service_entry["end_handle"] == begin_handle and 
                   "UUID" in service_entry.keys() and service_entry["UUID"] == UUID):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_UNKNOWN_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into GATTArray
            entry["GATTArray"].append(ff_GATT_Service(utype, begin_handle, end_handle, UUID))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

