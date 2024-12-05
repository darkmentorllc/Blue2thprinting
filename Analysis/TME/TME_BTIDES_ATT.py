########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import re
from TME.TME_BTIDES_base import generic_insertion_into_BTIDES_second_level_array, convert_UUID128_to_UUID16_if_possible
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

def BTIDES_export_ATT_handle(bdaddr, random, data):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    data["UUID"] = convert_UUID128_to_UUID16_if_possible(data["UUID"]) # Save space on exported data if possible
    handle_enumeration = ff_ATT_handle_enumeration(data)
    
    generic_insertion_into_BTIDES_second_level_array(bdaddr, random, handle_enumeration, "ATTArray", data, "ATT_handle_enumeration")

#def BTIDES_export_ATT_READ_REQ(bdaddr, random, handle):
