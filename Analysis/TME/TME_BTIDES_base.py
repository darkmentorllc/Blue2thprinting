########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import json
import TME.TME_glob
from TME.TME_helpers import *

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
        ).validate(instance=TME.TME_glob.BTIDES_JSON)
        #print("JSON is valid according to BTIDES Schema")
    except ValidationError as e:
        print("JSON data is invalid per BTIDES Schema. Check any changes to schema or code. Error:", e.message)
        exit(-1)

    with open(out_filename, 'w') as f:
        json.dump(TME.TME_glob.BTIDES_JSON, fp=f) # For saving space
        #json.dump(TME.TME_glob.BTIDES_JSON, fp=f, indent=2) # For pretty-printing to make output more readable

def lookup_entry(bdaddr, random):
    ###print("lookup_entry: ")
    for item in TME.TME_glob.BTIDES_JSON:
        ###print(item)
        ###print(f"lookup_entry: bdaddr = {bdaddr}")
        ###print(f"lookup_entry: random = {random}")
        if(item["bdaddr"] == bdaddr and item["bdaddr_rand"] == random):
            return item
        
    return None

############################
# Helper "factory functions"
############################  
def ff_base(bdaddr, random):
    base = {}
    base["bdaddr"] = bdaddr
    base["bdaddr_rand"] = random
    return base