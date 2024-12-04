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

def ff_GATT_Service(obj):
    if(verbose_BTIDES):
        if(obj["utype"] == "2800"):
            obj["type_str"] = "Primary Service"
        elif(obj["utype"] == "2801"):
            obj["type_str"] = "Secondary Service"
    return obj

def ff_GATT_Characteristic(obj):
    if(verbose_BTIDES):
        obj["type_str"] = "Characteristic"
        obj["utype"] = "2803"
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

def BTIDES_export_GATT_Services(bdaddr, random, data):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    data["UUID"] = convert_UUID128_to_UUID16_if_possible(data["UUID"]) # Save space on exported data if possible
    entry = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        print("XENOS1")
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        base["GATTArray"] = [ ff_GATT_Service(data) ] 
        #print(json.dumps(base, indent=2))
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("GATTArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any GATTArray entries, so just insert ours
            print(f"XENOS2")
            entry["GATTArray"] = [ ff_GATT_Service(data) ]
            return
        else:
            # There is an entry for this BDADDR, and GATTArray entries, so check if ours already exists, and if so, we're done
            for service_entry in entry["GATTArray"]:
                ###print(AdvChanEntry)
                if(service_entry != None and "opcode" in service_entry.keys() and service_entry["utype"] == data["utype"] and 
                   "begin_handle" in service_entry.keys() and service_entry["begin_handle"] == data["begin_handle"] and
                   "end_handle" in service_entry.keys() and service_entry["end_handle"] == data["begin_handle"] and 
                   "UUID" in service_entry.keys() and service_entry["UUID"] == data["UUID"]):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_LL_UNKNOWN_RSP: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    print("XENOS3")
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into GATTArray
            print(f"XENOS4")
            entry["GATTArray"].append(ff_GATT_Service(data))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_GATT_Characteristics(bdaddr, random, data):
    global BTIDES_JSON
    entry = lookup_base_entry(bdaddr, random)
    placeholder_svc_obj = {"placeholder_entry": True, "utype": "2800", "begin_handle": 1, "end_handle": 0xFFFF, "UUID": "FFFF"}
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        print("XENO1")
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, random)
        base["GATTArray"] = [ ff_GATT_Service(placeholder_svc_obj) ] # Placeholder service! 
        base["GATTArray"][0]["characteristics"] = [ ff_GATT_Characteristic(data) ]
        #print(json.dumps(base, indent=2))
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("GATTArray" not in entry.keys()):
            print("XENO2")
            # There is an entry for this BDADDR but not yet any GATTArray entries, so just insert ours
            entry["GATTArray"] = [ ff_GATT_Service(placeholder_svc_obj) ] # Placeholder service!
            entry["GATTArray"][0]["characteristics"] = [ ff_GATT_Characteristic(data) ]
            #print(json.dumps(entry, indent=2))
            return
        else:
            # There is an entry for this BDADDR, and GATTArray entries, so check if ours already exists, and if so, we're done
            for service_entry in entry["GATTArray"]:
                ###print(AdvChanEntry)
                    # Check if the begin and end handles enclose this characteristic
                if(service_entry != None and "begin_handle" in service_entry.keys() and service_entry["begin_handle"] < data["handle"] and
                   "end_handle" in service_entry.keys() and service_entry["end_handle"] >= data["handle"]):
                    # Check if this is the first entry, thus creating the characteristics array
                    if("characteristics" not in service_entry.keys()):
                        print("XENO3-1")
                        service_entry["characteristics"] = [ ff_GATT_Characteristic(data) ]
                        #print(json.dumps(service_entry, indent=2))
                        return
                    else:
                        print("XENO3-2")
                        service_entry["characteristics"].append(ff_GATT_Characteristic(data))
                        #print(json.dumps(service_entry, indent=2))
                        return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into a placeholder service in GATTArray
            print("XENO4")
            entry["GATTArray"].append(ff_GATT_Service(placeholder_svc_obj))
            entry["GATTArray"][-1]["characteristics"] = [ ff_GATT_Characteristic(data) ]
            #print(json.dumps(entry, indent=2))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return