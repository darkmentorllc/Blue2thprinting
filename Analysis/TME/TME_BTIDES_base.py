########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import json, re
#from TME.TME_helpers import *
from TME.TME_glob import BTIDES_JSON

from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator

# Same order as in BTIDES_base.json
BTIDES_files = ["BTIDES_base.json",
                "BTIDES_AdvData.json",
                "BTIDES_LL.json",
                "BTIDES_HCI.json",
                "BTIDES_L2CAP.json",
                "BTIDES_SMP.json",
                "BTIDES_ATT.json",
                "BTIDES_GATT.json",
                "BTIDES_EIR.json",
                "BTIDES_LMP.json",
                "BTIDES_SDP.json",
                "BTIDES_GPS.json"
                ]

def write_BTIDES(out_filename):
    # Sanity check the BTIDES data against the schema before export, to not write garbage
    # Import all the local BTIDES json schema files, so that we don't hit the website all the time
    all_schemas = []
    for file in BTIDES_files:
        with open(f"./BTIDES_Schema/{file}", 'r') as f:
            #BTIDES_Schema
            s = json.load(f)
            #print(s["$id"])
            schema = Resource.from_contents(s)
            all_schemas.append((s["$id"], schema))

    registry = Registry().with_resources( all_schemas )

    # Sanity check every entry against the Schema
    try:
        Draft202012Validator(
            {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json"},
            registry=registry,
        ).validate(instance=BTIDES_JSON)
        #print("JSON is valid according to BTIDES Schema")
    except ValidationError as e:
        print("JSON data is invalid per BTIDES Schema. Check any changes to schema or code. Error:", e.message)
        print(json.dumps(BTIDES_JSON, indent=2))
        exit(-1)

    with open(out_filename, 'w') as f:
        json.dump(BTIDES_JSON, fp=f) # For saving space
        #json.dump(BTIDES_JSON, fp=f, indent=2) # For pretty-printing to make output more readable


# Find SingleBDADDR type entries which match the given bdaddr and random
def lookup_SingleBDADDR_base_entry(bdaddr, random):
    bdaddr = bdaddr.lower()
    ###print("lookup_base_entry: ")
    for item in BTIDES_JSON:
        ###print(item)
        ###print(f"lookup_base_entry: bdaddr = {bdaddr}")
        ###print(f"lookup_base_entry: random = {random}")
        if("bdaddr" in item.keys() and item["bdaddr"] == bdaddr and 
           "bdaddr_rand" in item.keys() and item["bdaddr_rand"] == random):
            return item

    return None


# Find DualBDADDR type entries which match the given CONNECT_IND
def lookup_DualBDADDR_base_entry(connect_ind_obj):
    for item in BTIDES_JSON:
        if "CONNECT_IND" in item.keys() and item["CONNECT_IND"] == connect_ind_obj:
            return item
    return None


############################
# Helper "factory functions"
############################
def ff_SingleBDADDR_base(bdaddr, random):
    base = {}
    base["bdaddr"] = bdaddr
    base["bdaddr_rand"] = random
    return base


def ff_DualBDADDR_base(connect_ind_obj):
    base = {}
    base["CONNECT_IND"] = connect_ind_obj
    return base

# The "**optional_fields" syntax allows for a variable number of optional fields to be passed in
# e.g. "RSSI=value", "time=value", etc.
# This way we can set any of the std_optional_fields values which we have available at any given time
def insert_std_optional_fields(obj, **optional_fields):
    for field, value in optional_fields.items():
        if field not in obj:
            obj[field] = value
    return obj

def generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, tier1_data, target_tier1_array_name):
    global BTIDES_JSON
    bdaddr_specific_entry = lookup_SingleBDADDR_base_entry(bdaddr, random)
    if (bdaddr_specific_entry == None):
        # There is no bdaddr_specific_entry yet for this BDADDR. Insert a brand new one with our tier1_data within the given target_tier1_array_name
        base = ff_SingleBDADDR_base(bdaddr, random)
        base[target_tier1_array_name] = [ tier1_data ] 
        BTIDES_JSON.append(base)
        return True
    else:
        if(target_tier1_array_name not in bdaddr_specific_entry.keys()):
            # There is an bdaddr_specific_entry for this BDADDR but not yet any target_tier1_array_name entries, so just insert ours as the baseline array
            bdaddr_specific_entry[target_tier1_array_name] = [ tier1_data ]
            return True
        else:
            # There is an bdaddr_specific_entry for this BDADDR, and GATTArray entries, so check if ours already exists, and if so, we're done
            for obj in bdaddr_specific_entry[target_tier1_array_name]:
                if(obj == tier1_data):
                    return True
            # If we get here, we exhaused all target_tier1_array_name entries without a match. So append our new bdaddr_specific_entry onto GATTArray
            bdaddr_specific_entry[target_tier1_array_name].append(tier1_data)
            return True

    return False # Shouldn't be able to get here

# The difference between SingleBDADDR and DualBDADDR is that the latter uses the CONNECT_IND as the unique identifier
# and can be the only entry, due to that being its own packet type. Whereas the former uses a single BDADDR and random
# as the unique identifier, but which can't standalone, and is only ever valid in the presence of additional data.
# Therefore we need a level zero insertion function for DualBDADDR, but not for SingleBDADDR
def generic_DualBDADDR_insertion_into_BTIDES_zeroth_level(connect_ind_obj):
    global BTIDES_JSON
    bdaddr_pair_specific_entry = lookup_DualBDADDR_base_entry(connect_ind_obj)
    if (bdaddr_pair_specific_entry == None):
        if(len(BTIDES_JSON) == 0):
            # If there's nothing in the BTIDES JSON, then we need to add the DualBDADDR entry as the first thing
            DualBDADDR_entry = ff_DualBDADDR_base(connect_ind_obj)
            BTIDES_JSON = [ DualBDADDR_entry ]
            return True
        else:
            # If there's already stuff in the BTIDES JSON, append this new DualBDADDR entry to the end
            DualBDADDR_entry = ff_DualBDADDR_base(connect_ind_obj)
            BTIDES_JSON.append(DualBDADDR_entry)
            return True
    else:
        #print("CONNECT_IND already exists in the BTIDES JSON. Nothing to do.")
        return True

    return False # Shouldn't be able to get here

def generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, tier1_data, target_tier1_array_name):
    global BTIDES_JSON
    bdaddr_pair_specific_entry = lookup_DualBDADDR_base_entry(connect_ind_obj)
    if (bdaddr_pair_specific_entry == None):
        # There is no bdaddr_specific_entry yet for this BDADDR. Insert a brand new one with our tier1_data within the given target_tier1_array_name
        base = ff_DualBDADDR_base(connect_ind_obj)
        base[target_tier1_array_name] = [ tier1_data ] 
        BTIDES_JSON.append(base)
        return True
    else:
        if(target_tier1_array_name not in bdaddr_pair_specific_entry.keys()):
            # There is an bdaddr_specific_entry for this BDADDR but not yet any target_tier1_array_name entries, so just insert ours as the baseline array
            bdaddr_pair_specific_entry[target_tier1_array_name] = [ tier1_data ]
            return True
        else:
            # There is an bdaddr_specific_entry for this BDADDR, and GATTArray entries, so check if ours already exists, and if so, we're done
            for obj in bdaddr_pair_specific_entry[target_tier1_array_name]:
                if(obj == tier1_data):
                    return True
            # If we get here, we exhaused all target_tier1_array_name entries without a match. So append our new bdaddr_specific_entry onto GATTArray
            bdaddr_pair_specific_entry[target_tier1_array_name].append(tier1_data)
            return True

    return False # Shouldn't be able to get here


# I want to check for equality between objects, while ignoring embedded dictionaries (otherwise there could never be equality in some cases)
def non_recursive_primitive_equality_check(dict1, dict2):
    # Compare only the top-level keys first
    if set(dict1.keys()) != set(dict2.keys()):
        return False

    # Iterate over keys and compare values if they are primitive types
    for key in dict1:
        # Check if both values are primitive types (not dictionaries, lists, etc.)
        value1 = dict1[key]
        value2 = dict2[key]

        if isinstance(value1, (int, float, str, bool)) and isinstance(value2, (int, float, str, bool)):
            if value1 != value2:
                return False

        # If values are not primitive types (e.g., dictionaries, lists), skip comparison
        elif isinstance(value1, dict) or isinstance(value2, dict):
            continue  # Skip comparison for nested dictionaries

    return True


# This is for inserting things into not the top level array, but a sub-array
# e.g. "AdvDataArray" (tier2) under "AdvChanArray" (tier1), or "characteristics" (tier1), under "GATTArray" (tier1)
# This function requires you to already have the tier1_data so that it can be matched before descending into tier2
# The tier1_data should already have the tier2_data inserted into it, to simplify insertion in the case that the tier1 data doesn't already exist (TODO: Is this right?)
def generic_SingleBDADDR_insertion_into_BTIDES_second_level_array(bdaddr, random, tier1_data, target_tier1_array_name, tier2_data, target_tier2_array_name):
    global BTIDES_JSON
    bdaddr_specific_entry = lookup_SingleBDADDR_base_entry(bdaddr, random)
    if (bdaddr_specific_entry == None):
        # There is no bdaddr_specific_entry yet for this BDADDR. Insert a brand new one with our tier1_data within the given target_tier1_array_name
        base = ff_SingleBDADDR_base(bdaddr, random)
        base[target_tier1_array_name] = [ tier1_data ] 
        BTIDES_JSON.append(base)
        return True
    else:
        if(target_tier1_array_name not in bdaddr_specific_entry.keys()):
            # There is an bdaddr_specific_entry for this BDADDR but not yet any target_tier1_array_name entries, so just insert ours as the baseline array
            bdaddr_specific_entry[target_tier1_array_name] = [ tier1_data ]
            return True
        else:
            # There is an bdaddr_specific_entry for this BDADDR, and GATTArray entries, so check if ours already exists, and if so, we're done
            for t1_obj in bdaddr_specific_entry[target_tier1_array_name]:
                # Do a shallow check of whether the found object matches the target tier1 data, while not recursing into embedded objects
                if(non_recursive_primitive_equality_check(t1_obj, tier1_data)):
                    # Descend into the second level
                    if(target_tier2_array_name not in t1_obj.keys()):
                        # Key is missing, so just insert new tier2_array with tier2_data
                        t1_obj[target_tier2_array_name] = [ tier2_data ]
                        return True
                    else:
                        # Check for an exact match of the tier2_data, and if so, we're done
                        for t2_obj in t1_obj[target_tier2_array_name]:
                            if(t2_obj == tier2_data):
                                return True

                        # If we got here, nothing matched, so append the tier2_data
                        t1_obj[target_tier2_array_name].append(tier2_data)
                        return True
            # If we get here, we exhaused all target_tier1_array_name entries without a match. So append our new bdaddr_specific_entry onto GATTArray
            bdaddr_specific_entry[target_tier1_array_name].append(tier1_data)
            return True

    return False # Shouldn't be able to get here

# This is for inserting things into not the top level array, but a sub-array
# e.g. "AdvDataArray" (tier2) under "AdvChanArray" (tier1), or "characteristics" (tier1), under "GATTArray" (tier1)
# This function requires you to already have the tier1_data so that it can be matched before descending into tier2
# The tier1_data should already have the tier2_data inserted into it, to simplify insertion in the case that the tier1 data doesn't already exist (TODO: Is this right?)
def generic_DualBDADDR_insertion_into_BTIDES_second_level_array(connect_ind_obj, tier1_data, target_tier1_array_name, tier2_data, target_tier2_array_name):
    global BTIDES_JSON
    bdaddr_pair_specific_entry = lookup_DualBDADDR_base_entry(connect_ind_obj)
    if (bdaddr_pair_specific_entry == None):
        # There is no bdaddr_pair_specific_entry yet for this BDADDR pair. Insert a brand new one with our tier1_data within the given target_tier1_array_name
        base = ff_DualBDADDR_base(connect_ind_obj)
        base[target_tier1_array_name] = [ tier1_data ] 
        BTIDES_JSON.append(base)
        return True
    else:
        if(target_tier1_array_name not in bdaddr_pair_specific_entry.keys()):
            # There is an bdaddr_pair_specific_entry for this BDADDR pair but not yet any target_tier1_array_name entries, so just insert ours as the baseline array
            bdaddr_pair_specific_entry[target_tier1_array_name] = [ tier1_data ]
            return True
        else:
            # There is an bdaddr_pair_specific_entry for this BDADDR pair, and GATTArray entries, so check if ours already exists, and if so, we're done
            for t1_obj in bdaddr_pair_specific_entry[target_tier1_array_name]:
                # Do a shallow check of whether the found object matches the target tier1 data, while not recursing into embedded objects
                if(non_recursive_primitive_equality_check(t1_obj, tier1_data)):
                    # Descend into the second level
                    if(target_tier2_array_name not in t1_obj.keys()):
                        # Key is missing, so just insert new tier2_array with tier2_data
                        t1_obj[target_tier2_array_name] = [ tier2_data ]
                        return True
                    else:
                        # Check for an exact match of the tier2_data, and if so, we're done
                        for t2_obj in t1_obj[target_tier2_array_name]:
                            if(t2_obj == tier2_data):
                                return True

                        # If we got here, nothing matched, so append the tier2_data
                        t1_obj[target_tier2_array_name].append(tier2_data)
                        return True
            # If we get here, we exhaused all target_tier1_array_name entries without a match. So append our new bdaddr_pair_specific_entry onto GATTArray
            bdaddr_pair_specific_entry[target_tier1_array_name].append(tier1_data)
            return True

    return False # Shouldn't be able to get here

def convert_UUID128_to_UUID16_if_possible(UUID128):
    UUID128_tmp = UUID128.strip().lower()
    UUID128_tmp = UUID128_tmp.replace('-','')
    pattern = r'0000[a-f0-9]{4}00001000800000805f9b34fb'
    match = re.match(pattern, UUID128_tmp)
    if match:
        return UUID128_tmp[4:8]
    else:
        return UUID128