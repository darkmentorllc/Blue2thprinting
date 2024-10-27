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

def write_BTIDES(out_filename):
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