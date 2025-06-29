########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import re
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_helpers import qprint
from TME.TME_BTIDES_base import *
import TME.TME_glob

############################
# Helper "factory functions"
############################

opcode_ATT_EXCHANGE_MTU_REQ          = 2
opcode_ATT_EXCHANGE_MTU_RSP          = 3

status_SUCCESS = 0

def ff_GATT_Service(obj):
    obj["UUID"] = convert_UUID128_to_UUID16_if_possible(obj["UUID"]) # Save space on exported data if possible
    if(TME.TME_glob.verbose_BTIDES):
        if(obj["utype"] == "2800"):
            obj["type_str"] = "Primary Service"
        elif(obj["utype"] == "2801"):
            obj["type_str"] = "Secondary Service"
    return obj

def ff_GATT_Characteristic(obj):
    obj["value_uuid"] = convert_UUID128_to_UUID16_if_possible(obj["value_uuid"]) # Save space on exported data if possible
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "Characteristic"
        obj["utype"] = "2803"
    return obj

# The primary purpose of this is just to increase verbosity for an existing io_array
def ff_GATT_IO(io_array):
    if(TME.TME_glob.verbose_BTIDES):
        for obj in io_array:
            if("io_type_str" not in obj.keys()):
                if(obj["io_type"] in ATT_type_to_BTIDES_io_type_str.keys()):
                    obj["io_type_str"] = ATT_type_to_BTIDES_io_type_str[obj["io_type"]]
            if(obj["io_type"] == type_ATT_ERROR_RSP):
                if("io_error_str" not in obj.keys()):
                    error_code = int(obj["value_hex_str"], 16)
                    if(error_code in TME.BT_Data_Types.att_errorcode_to_str.keys()):
                        obj["io_error_str"] = TME.BT_Data_Types.att_errorcode_to_str[error_code]
    return io_array

def ff_GATT_Characteristic_Value(obj):
    if("io_array" in obj.keys()):
        obj["io_array"] = ff_GATT_IO(obj["io_array"])
    return obj

# The primary purpose of this is just to increase verbosity for an existing descriptor object by adding the name
def ff_Descriptor(obj):
    if(TME.TME_glob.verbose_BTIDES):
        if(obj["UUID"] in UUIDs_to_characteristic_descriptor_type_str.keys()):
            obj["type_str"] = UUIDs_to_characteristic_descriptor_type_str[obj["UUID"]]
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
        qprint("UNKNOWN SERVICE_TYPE. FIX THE CODE")
        exit(-1)

def find_exact_service_match(GATTArray, data):
    for service_entry in GATTArray:
        # Check if the begin and end service handles enclose this characteristic value
        if(service_entry != None and "opcode" in service_entry.keys() and service_entry["utype"] == data["utype"] and
           "begin_handle" in service_entry.keys() and service_entry["begin_handle"] == data["begin_handle"] and
           "end_handle" in service_entry.keys() and service_entry["end_handle"] == data["begin_handle"] and
           "UUID" in service_entry.keys() and service_entry["UUID"] == data["UUID"]):
            return service_entry

    return None

def BTIDES_export_GATT_Service(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    global BTIDES_JSON
    if connect_ind_obj != None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "GATTArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "GATTArray")

def find_service_with_target_handle_in_range(connect_ind_obj=None, bdaddr=None, random=None, target_handle=None):
    if(connect_ind_obj):
        base = lookup_DualBDADDR_base_entry(connect_ind_obj)
    else:
        base = lookup_SingleBDADDR_base_entry(bdaddr, random)
    if("GATTArray" not in base.keys()):
        return None
    for service_entry in base["GATTArray"]:
        # Check if the begin and end service handles enclose this characteristic value
        if(service_entry != None and "begin_handle" in service_entry.keys() and service_entry["begin_handle"] < target_handle and
           "end_handle" in service_entry.keys() and service_entry["end_handle"] >= target_handle):
            return service_entry
    return None

def BTIDES_export_GATT_Characteristic(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    global BTIDES_JSON

    if connect_ind_obj != None:
        service_entry = find_service_with_target_handle_in_range(connect_ind_obj=connect_ind_obj, target_handle=data["handle"])
        if(service_entry == None):
            service_entry = ff_GATT_Service({"placeholder_entry": True, "utype": "2800", "begin_handle": 1, "end_handle": 0xFFFF, "UUID": "FFFF", "characteristics": [ data ]})
        generic_DualBDADDR_insertion_into_BTIDES_second_level_array(connect_ind_obj, service_entry, "GATTArray", data, "characteristics")
    else:
        service_entry = find_service_with_target_handle_in_range(bdaddr=bdaddr, random=random, target_handle=data["handle"])
        if(service_entry == None):
            service_entry = ff_GATT_Service({"placeholder_entry": True, "utype": "2800", "begin_handle": 1, "end_handle": 0xFFFF, "UUID": "FFFF", "characteristics": [ data ]})
        generic_SingleBDADDR_insertion_into_BTIDES_second_level_array(bdaddr, random, service_entry, "GATTArray", data, "characteristics")

def find_matching_characteristic(characteristics, target_handle):
    for char in characteristics:
        # Check if the begin and end service handles enclose this characteristic value
        if(char != None and "value_handle" in char.keys() and char["value_handle"] == target_handle):
            return char
    return None

# Pass either handle for the Characteristic itself's handle, or value_handle for the Characteristic's value_handle
def find_characteristic_by_handle(connect_ind_obj=None, bdaddr=None, random=None, handle=None, value_handle=None):
    if(connect_ind_obj):
        base = lookup_DualBDADDR_base_entry(connect_ind_obj)
    else:
        base = lookup_SingleBDADDR_base_entry(bdaddr, random)
    if("GATTArray" not in base.keys()):
        return None
    for service_entry in base["GATTArray"]:
        # Check if the begin and end service handles enclose this characteristic value
        if(service_entry != None and "characteristics" in service_entry.keys()):
            for characteristic_entry in service_entry["characteristics"]:
                if(characteristic_entry and handle and characteristic_entry["handle"] == handle):
                    return characteristic_entry
                if(characteristic_entry and value_handle and characteristic_entry["value_handle"] == value_handle):
                    return characteristic_entry
    return None

def BTIDES_export_GATT_Characteristic_Value(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    global BTIDES_JSON
    if(connect_ind_obj):
        base = lookup_DualBDADDR_base_entry(connect_ind_obj)
    else:
        base = lookup_SingleBDADDR_base_entry(bdaddr, random)
    # For the placeholder, first run it through the factory function to add any nice-to-haves for verbosity
    data = ff_GATT_Characteristic_Value(data)
    # Next for the embed the char_value data into the placeholder characteristic right from the start
    placeholder_char_obj = ff_GATT_Characteristic({"placeholder_entry": True, "utype": "2803", "handle": 0xFFFE, "properties": 0xFF, "value_handle": data["handle"], "value_uuid": "FFFF", "char_value": data})
    # And then embed the placeholder characteristic into the placeholder service
    placeholder_svc_obj = ff_GATT_Service({"placeholder_entry": True, "utype": "2800", "begin_handle": 1, "end_handle": 0xFFFF, "UUID": "FFFF", "characteristics": [ placeholder_char_obj ]})
    ###qprint(json.dumps(entry, indent=2))
    if (base == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_SingleBDADDR_base(bdaddr, random)
        base["GATTArray"] = [ placeholder_svc_obj ]
        #qprint(json.dumps(base, indent=2))
        TME.TME_glob.BTIDES_JSON.append(base)
        #qprint(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("GATTArray" not in base.keys()):
            # There is an entry for this BDADDR but not yet any GATTArray entries, so just insert ours
            base["GATTArray"] = [ placeholder_svc_obj ]
            #qprint(json.dumps(entry, indent=2))
            return
        else:
            service_entry = find_service_with_target_handle_in_range(bdaddr=bdaddr, random=random, target_handle=data["handle"])
            if(service_entry != None):
                if("characteristics" not in service_entry.keys()):
                    service_entry["characteristics"] = [ placeholder_char_obj ]
                    return
                else:
                    # Check if there's already a characteristic within this service which has the matching matching value.handle == char.value_handle
                    characteristic_entry = find_matching_characteristic(service_entry["characteristics"], data["handle"])
                    if(characteristic_entry == None):
                        # If we get here, we exhaused all characteristics without a match.
                        # Insert an entire placeholder characteristic
                        service_entry["characteristics"].append(placeholder_char_obj)
                        return
                    else:
                        # Check the match
                        if("char_value" not in characteristic_entry.keys()):
                            # Insert our io_array as the first thing
                            characteristic_entry["char_value"] = data
                            return
                        else:
                            if("io_array" not in characteristic_entry["char_value"].keys()):
                                # Insert our io_array as the first thing
                                characteristic_entry["char_value"]["io_array"] = data["io_array"]
                            else:
                                # Append (via extend!) our io_array entry(/ies) to the existing io_array
                                characteristic_entry["char_value"]["io_array"].extend(data["io_array"])

            # If we get here, we exhaused all services without a match. So insert our new entry within the placeholder service & characteristic
            base["GATTArray"].append(placeholder_svc_obj)
            #qprint(json.dumps(entry, indent=2))
            ###qprint(json.dumps(TME.TME_glob.BTIDES_JSON, indent=2))
            return