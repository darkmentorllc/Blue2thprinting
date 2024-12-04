########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

type_AdvData_Flags                              = 1
type_AdvData_UUID16ListIncomplete               = 2
type_AdvData_UUID16ListComplete                 = 3
type_AdvData_UUID32ListIncomplete               = 4
type_AdvData_UUID32ListComplete                 = 5
type_AdvData_UUID128ListIncomplete              = 6
type_AdvData_UUID128ListComplete                = 7
type_AdvData_IncompleteName                     = 8
type_AdvData_CompleteName                       = 9
type_AdvData_TxPower                            = 10
type_AdvData_ClassOfDevice                      = 13
type_AdvData_DeviceID                           = 16
type_AdvData_PeripheralConnectionIntervalRange  = 18
type_AdvData_UUID16ServiceData                  = 22
type_AdvData_Appearance                         = 25
type_AdvData_UUID32ServiceData                  = 32
type_AdvData_UUID128ServiceData                 = 33
type_AdvData_MSD                                = 255

############################
# Helper "factory functions"
############################  

# Advertisement channel PDU types defined in BT spec
pdutype_ADV_IND           = 0
pdutype_ADV_DIRECT_IND    = 1
pdutype_ADV_NONCONN_IND   = 2
pdutype_SCAN_REQ          = 3
pdutype_SCAN_RSP          = 4
pdutype_CONNECT_IND       = 5
pdutype_ADV_SCAN_IND      = 6
pdutype_AUX_ADV_IND       = 7
pdutype_AUX_SCAN_RSP      = 7

# Valid types defined in BTIDES schema
btype_ADV_IND           = 0
btype_ADV_DIRECT_IND    = 1
btype_ADV_NONCONN_IND   = 2
btype_ADV_SCAN_IND      = 3
btype_AUX_ADV_IND       = 10
btype_SCAN_RSP          = 20
btype_AUX_SCAN_RSP      = 10
btype_EIR               = 50
valid_adv_chan_types = [btype_ADV_IND, btype_ADV_DIRECT_IND, btype_ADV_NONCONN_IND, btype_ADV_SCAN_IND, btype_AUX_ADV_IND, btype_SCAN_RSP, btype_AUX_SCAN_RSP, btype_EIR]
valid_adv_chan_type_strs = ["ADV_IND", "ADV_DIRECT_IND", "ADV_NONCONN_IND", "ADV_SCAN_IND", "AUX_ADV_IND", "SCAN_RSP", "AUX_SCAN_RSP", "EIR"]
def ff_AdvChanData(type=None, type_str=None, CSA=None, full_pkt_hex_str=None, AdvDataArray=None):
    AdvChanData = {}
    #print(f"type = {type}, type_str = {type_str}")
    if (type != None and (type in valid_adv_chan_types)):
        AdvChanData["type"] = type
    if (CSA != None):
        AdvChanData["CSA"] = CSA
    if (full_pkt_hex_str != None):
        AdvChanData["full_pkt_hex_str"] = full_pkt_hex_str
    if (AdvDataArray != None):
        AdvChanData["AdvDataArray"] = AdvDataArray

    if(verbose_BTIDES and type_str != None and (type_str in valid_adv_chan_type_strs)):
        AdvChanData["type_str"] = type_str

    if(AdvChanData):
        return AdvChanData
    else:
        return None

def get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host):
    flags_int = 0x00
    if(le_limited_discoverable_mode):
        flags_int |= 1
    if(le_general_discoverable_mode):
        flags_int |= 1 << 1
    if(bredr_not_supported):
        flags_int |= 1 << 2
    if(le_bredr_support_controller):
        flags_int |= 1 << 3
    if(le_bredr_support_host):
        flags_int |= 1 << 4
    flags_hex_str = f"{flags_int:02X}"
    return flags_hex_str

# type 1
def ff_Flags(data):
###    flags_hex_str = get_flags_hex_str(data["le_limited_discoverable_mode"], data["le_general_discoverable_mode"], data["bredr_not_supported"], data["le_bredr_support_controller"], data["le_bredr_support_host"])
    obj = {"type": type_AdvData_Flags, "length": data["length"], "flags_hex_str": data["flags_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "Flags"
    return obj

# type 2 & 3
def ff_UUID16Lists(list_type, data):
    obj = {"type": list_type, "length": data["length"], "UUID16List": data["UUID16List"]}
    if(verbose_BTIDES):
        if(list_type == type_AdvData_UUID16ListIncomplete):
            obj["type_str"] = "UUID16ListIncomplete"
        elif(list_type == type_AdvData_UUID16ListComplete):
            obj["type_str"] = "UUID16ListComplete"
    return obj

# type 4 & 5
def ff_UUID32Lists(list_type, data):
    obj = {"type": list_type, "length": data["length"], "UUID32List": data["UUID32List"]}
    if(verbose_BTIDES):
        if(list_type == type_AdvData_UUID32ListIncomplete):
            obj["type_str"] = "UUID32ListIncomplete"
        elif(list_type == type_AdvData_UUID32ListComplete):
            obj["type_str"] = "UUID32ListComplete"
    return obj

# type 6 & 7
def ff_UUID128Lists(list_type, data):
    obj = {"type": list_type, "length": data["length"], "UUID128List": data["UUID128List"]}
    if(verbose_BTIDES):
        if(list_type == type_AdvData_UUID128ListIncomplete):
            obj["type_str"] = "UUID128ListIncomplete"
        elif(list_type == type_AdvData_UUID128ListComplete):
            obj["type_str"] = "UUID128ListComplete"
    return obj

# type 8 & 9
def ff_Names(name_type, data):
    obj = {"type": name_type, "length":  data["length"], "name_hex_str": data["name_hex_str"]}
    if(verbose_BTIDES):
        if(name_type == type_AdvData_IncompleteName):
            obj["type_str"] = "IncompleteName"
        elif(name_type == type_AdvData_CompleteName):
            obj["type_str"] = "CompleteName"
            
        if(data["utf8_name"]):
            obj["utf8_name"] = data["utf8_name"]

    return obj

# type 0x0A
def ff_TxPower(data):
    obj = {"type": type_AdvData_TxPower, "length": data["length"], "tx_power": data["tx_power"]}
    if(verbose_BTIDES):
        obj["type_str"] = "TxPower"
    return obj

# type 0x0D
def ff_ClassOfDevice(data):
    obj = {"type": type_AdvData_ClassOfDevice, "length": data["length"], "CoD_hex_str": data["CoD_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "ClassOfDevice"
    return obj

# type 0x10
def ff_DeviceID(data):
    obj = {"type": type_AdvData_DeviceID, "length": data["length"], "vendor_id_source": data["vendor_id_source"], "vendor_id": data["vendor_id"], "product_id": data["product_id"], "version": data["version"]}
    if(verbose_BTIDES):
        obj["type_str"] = "DeviceID"
    return obj

# type 0x12
def ff_PeripheralConnectionIntervalRange(data):
    obj = {"type": type_AdvData_PeripheralConnectionIntervalRange, "length": data["length"], "conn_interval_min": data["conn_interval_min"], "conn_interval_max": data["conn_interval_max"]}
    if(verbose_BTIDES):
        obj["type_str"] = "PeripheralConnectionIntervalRange"
    return obj

# type 0x16
def ff_UUID16ServiceData(data):
    obj = {"type": type_AdvData_UUID16ServiceData, "length": data["length"], "UUID16": data["UUID16"], "service_data_hex_str": data["service_data_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "UUID16ServiceData"
    return obj

# type 0x19
def ff_Appearance(data):
    obj = {"type": type_AdvData_Appearance, "length": data["length"], "appearance_hex_str": data["appearance_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "Appearance"
    return obj

# type 0x20
def ff_UUID32ServiceData(data):
    obj = {"type": type_AdvData_UUID32ServiceData, "length": data["length"], "UUID32": data["UUID32"], "service_data_hex_str": data["service_data_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "UUID32ServiceData"
    return obj

# type 0x21
def ff_UUID128ServiceData(data):
    obj = {"type": type_AdvData_UUID128ServiceData, "length": data["length"], "UUID128": data["UUID128"], "service_data_hex_str": data["service_data_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "UUID128ServiceData"
    return obj

# type 0xFF
def ff_MSD(data):
    obj = {"type": type_AdvData_MSD, "length": data["length"], "company_id_hex_str": data["company_id_hex_str"], "msd_hex_str": data["msd_hex_str"]}
    if(verbose_BTIDES):
        obj["type_str"] = "ManufacturerSpecificData"
    return obj

########################################################
# Building up generic all-type export capability
########################################################

# data should be a shallow dictionary with keys that exactly match the keys in the BTIDES data
def adv_data_exact_match(AdvDataArrayEntry, adv_data_type, data):
    #print(json.dumps(AdvDataArrayEntry, indent=2))
    # Type has already been checked before finding the match, no need to check it again
    if(adv_data_type == type_AdvData_Flags):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["flags_hex_str"] == data["flags_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID16ListIncomplete or adv_data_type == type_AdvData_UUID16ListComplete):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["UUID16List"] == data["UUID16List"]): # TODO: Can list equality be checked this way?
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID32ListIncomplete or adv_data_type == type_AdvData_UUID32ListComplete):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["UUID32List"] == data["UUID32List"]): # TODO: Can list equality be checked this way?
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID128ListIncomplete or adv_data_type == type_AdvData_UUID128ListComplete):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["UUID128List"] == data["UUID128List"]): # TODO: Can list equality be checked this way?
            return True
        else: return False

    if(adv_data_type == type_AdvData_IncompleteName or adv_data_type == type_AdvData_CompleteName):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["name_hex_str"] == data["name_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_TxPower):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["tx_power"] == data["tx_power"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_ClassOfDevice):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["CoD_hex_str"] == data["CoD_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_DeviceID):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["vendor_id_source"] == data["vendor_id_source"] and
           AdvDataArrayEntry["vendor_id"] == data["vendor_id"] and
           AdvDataArrayEntry["product_id"] == data["product_id"] and
           AdvDataArrayEntry["version"] == data["version"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_PeripheralConnectionIntervalRange):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["conn_interval_min"] == data["conn_interval_min"] and
           AdvDataArrayEntry["conn_interval_max"] == data["conn_interval_max"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_Appearance):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["appearance_hex_str"] == data["appearance_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID16ServiceData):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["UUID16"] == data["UUID16"] and
           AdvDataArrayEntry["service_data_hex_str"] == data["service_data_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID32ServiceData):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["UUID32"] == data["UUID32"] and
           AdvDataArrayEntry["service_data_hex_str"] == data["service_data_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID128ServiceData):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["UUID128"] == data["UUID128"] and
           AdvDataArrayEntry["service_data_hex_str"] == data["service_data_hex_str"]):
            return True
        else: return False


    if(adv_data_type == type_AdvData_MSD):
        if(AdvDataArrayEntry["length"] == data["length"] and 
           AdvDataArrayEntry["company_id_hex_str"] == data["company_id_hex_str"] and 
           AdvDataArrayEntry["msd_hex_str"] == data["msd_hex_str"]):
            return True
        else: return False

    # Shouldn't be able to get here, because this should never be called for types we haven't handled yet
    print("adv_data_exact_match: unknown adv_data_type. Something is wrong. Exiting so you can debug...")
    exit(-1)

# This just returns true or false of whether a specific entry already exists 
# If it returns True, there's no insert needed
def AdvDataArray_entry_by_btype_exists(AdvChanData, btype, adv_data_type, data):
    #print(json.dumps(AdvChanData, indent=2))
    for AdvChanDataEntry in AdvChanData["AdvDataArray"]:
        if(AdvChanDataEntry["type"] == adv_data_type):
            # matches the type we're searching for, now do other type-specific field checks
            if(adv_data_exact_match(AdvChanDataEntry, adv_data_type, data)):
                return True

    # If none of the entries match, return False
    return False

# lookup_base_entry(bdaddr, random) searches for a base entry in the base array
# lookup_AdvChanData_entry_by_btype() searches for an AdvChanData entry in the AdvChanArray
# If none is found, one needs to be added
def lookup_AdvChanData_entry_by_btype(base_entry, btype):
    for AdvChanData in base_entry["AdvChanArray"]:
        if(AdvChanData["type"] == btype): # Only type is required, not type_str
            return AdvChanData

    return None

##################

def ff_adv_data_type_specific_obj(adv_data_type, data):
    if(adv_data_type == type_AdvData_Flags):
        return ff_Flags(data)

    if(adv_data_type == type_AdvData_UUID16ListIncomplete or adv_data_type == type_AdvData_UUID16ListComplete):
        return ff_UUID16Lists(adv_data_type, data)

    if(adv_data_type == type_AdvData_UUID32ListIncomplete or adv_data_type == type_AdvData_UUID32ListComplete):
        return ff_UUID32Lists(adv_data_type, data)

    if(adv_data_type == type_AdvData_UUID128ListIncomplete or adv_data_type == type_AdvData_UUID128ListComplete):
        return ff_UUID128Lists(adv_data_type, data)

    if(adv_data_type == type_AdvData_IncompleteName or adv_data_type == type_AdvData_CompleteName):
        return ff_Names(adv_data_type, data)

    if(adv_data_type == type_AdvData_TxPower):
        return ff_TxPower(data)

    if(adv_data_type == type_AdvData_ClassOfDevice):
        return ff_ClassOfDevice(data)

    if(adv_data_type == type_AdvData_DeviceID):
        return ff_DeviceID(data)

    if(adv_data_type == type_AdvData_PeripheralConnectionIntervalRange):
        return ff_PeripheralConnectionIntervalRange(data)

    if(adv_data_type == type_AdvData_Appearance):
        return ff_Appearance(data)

    if(adv_data_type == type_AdvData_UUID16ServiceData):
        return ff_UUID16ServiceData(data)

    if(adv_data_type == type_AdvData_UUID32ServiceData):
        return ff_UUID32ServiceData(data)

    if(adv_data_type == type_AdvData_UUID128ServiceData):
        return ff_UUID128ServiceData(data)

    if(adv_data_type == type_AdvData_MSD):
        return ff_MSD(data)

    return None

def insert_new_AdvChanData(base, adv_type, adv_data_type, data):
    btype = pdu_type_to_BTIDES_type(adv_type)
    btype_str = None
    if(verbose_BTIDES):
        btype_str = pdu_type_to_BTIDES_type_str(adv_type)

    acd = ff_AdvChanData(type=btype, type_str=btype_str)
    #print(acd)
    acd["AdvDataArray"] = [ ff_adv_data_type_specific_obj(adv_data_type, data) ]
    #print(json.dumps(acd, indent=2))
    base["AdvChanArray"].append(acd)

def insert_new_AdvChanArray(base, adv_type, adv_data_type, data):
    btype = pdu_type_to_BTIDES_type(adv_type)
    btype_str = None
    if(verbose_BTIDES):
        btype_str = pdu_type_to_BTIDES_type_str(adv_type)
    acd = ff_AdvChanData(type=btype, type_str=btype_str)
    acd["AdvDataArray"] = [ ff_adv_data_type_specific_obj(adv_data_type, data) ]
    #print(json.dumps(acd, indent=2))
    base["AdvChanArray"] = [ acd ]

def insert_new_AdvChanArray_entry_only(base, adv_type, adv_data_type, data):
    # btype = BTIDES-specific advertisement event type
    btype = pdu_type_to_BTIDES_type(adv_type)

    if("AdvChanArray" not in base.keys()):
        # There is an entry for this BDADDR (base) but not yet any AdvChanArray entries, so just insert ours
        insert_new_AdvChanArray(base, adv_type, adv_data_type, data)
        #print(json.dumps(acd, indent=2))
        return

    acd = lookup_AdvChanData_entry_by_btype(base, btype)
    if(acd == None):
        insert_new_AdvChanData(base, adv_type, adv_data_type, data)
        return
    else:
        if(AdvDataArray_entry_by_btype_exists(acd, btype, adv_data_type, data)):
            # Nothing to do
            return
        else:
            acd["AdvDataArray"].append(ff_adv_data_type_specific_obj(adv_data_type, data))
            return

def insert_new_base_and_AdvChanArray_entry(device_bdaddr, bdaddr_random, adv_type, adv_data_type, data):
    global BTIDES_JSON
    base = ff_base(device_bdaddr, bdaddr_random)
    insert_new_AdvChanArray(base, adv_type, adv_data_type, data)
    ###print(json.dumps(base, indent=2))
    BTIDES_JSON.append(base)
    #print(json.dumps(BTIDES_JSON, indent=2))
    return

# See get_le_event_type_string() for what's what
# TODO: add AUX_* types once I start importing those into the db
def pdu_type_to_BTIDES_type(type):
    # FIXME!: I found based on this that I'm overloading PCAP types and old HCI types and they're off by 1!
    # I will need to change db and re-process everything to fix :-/
    # Values from pcaps and newer HCI logs
    if(type == pdutype_ADV_IND):            return btype_ADV_IND
    if(type == pdutype_ADV_DIRECT_IND):     return btype_ADV_DIRECT_IND
    if(type == pdutype_ADV_SCAN_IND):       return btype_ADV_SCAN_IND
    if(type == pdutype_ADV_NONCONN_IND):    return btype_ADV_NONCONN_IND
    if(type == pdutype_SCAN_RSP):           return btype_SCAN_RSP # SCAN_RSP
    if(type == pdutype_SCAN_REQ):           return pdutype_ADV_NONCONN_IND #FIXME IN THE FUTURE: From accidental incorrect pcap mix-in off-by-one
    #if(type == 6): return btype_SCAN_RSP # SCAN_RSP # FIXME: From accidental incorrect pcap mix-in
    
    # Values from older HCI logs where they had a different format for the event type which was a bitfield of scannable, connectable, etc
    # instead of just using the PDU type from the packet as they seem to in newer HCI logs
    # From "Event_Type values for legacy PDUs" in spec apparently 
    if(type == 16): return btype_ADV_NONCONN_IND # 0x10 ADV_NONCONN_IND
    if(type == 18): return btype_ADV_SCAN_IND # 0x12 ADV_SCAN_IND
    if(type == 19): return btype_ADV_IND # 0x13 ADV_IND
    if(type == 21): return btype_ADV_DIRECT_IND # 0x15 ADV_DIRECT_IND
    if(type == 26): return btype_SCAN_RSP # 0x1A SCAN_RSP to ADV_SCAN_IND
    if(type == 27): return btype_SCAN_RSP # 0x1B SCAN_RSP to ADV_IND
    
    # From manually inserting EIR type
    if(type == 50): return 50 # EIR
    
# See get_le_event_type_string() for what's what
# TODO: add AUX_* types once I start importing those into the db
def pdu_type_to_BTIDES_type_str(type):
    # FIXME!: I found based on this that I'm overloading PCAP types and old HCI types and they're off by 1!
    # I will need to change db and re-process everything to fix :-/
    # Values from pcaps and newer HCI logs
    # FOR NOW I'M USING THE HCI TYPES, BECAUSE THAT'S WHAT MOST OF MY DATA IS IN
    if(type == pdutype_ADV_IND):            return "ADV_IND"
    if(type == pdutype_ADV_DIRECT_IND):     return "ADV_DIRECT_IND" # FIXME: I don't know if that's what this actually is, since I have no examples in the HCI log I'm looking at
    if(type == pdutype_ADV_SCAN_IND):       return "ADV_SCAN_IND"
    if(type == pdutype_ADV_NONCONN_IND):    return "ADV_NONCONN_IND"
    if(type == pdutype_SCAN_RSP):           return "SCAN_RSP"
    if(type == pdutype_SCAN_REQ):           return "ADV_NONCONN_IND" #FIXME IN THE FUTURE: From accidental incorrect pcap mix-in off-by-one
    #if(type == 6): return "SCAN_RSP" # FIXME: From accidental incorrect pcap mix-in. Replace with proper 
    
    # Values from older HCI logs where they had a different format for the event type which was a bitfield of scannable, connectable, etc
    # instead of just using the PDU type from the packet as they seem to in newer HCI logs
    # From "Event_Type values for legacy PDUs" in spec apparently 
    if(type == 16): return "ADV_NONCONN_IND" # 0x10 ADV_NONCONN_IND
    if(type == 18): return "ADV_SCAN_IND" # 0x12 ADV_SCAN_IND
    if(type == 19): return "ADV_IND" # 0x13 ADV_IND
    if(type == 21): return "ADV_DIRECT_IND" # 0x15 ADV_DIRECT_IND
    if(type == 26): return "SCAN_RSP" # 0x1A SCAN_RSP to ADV_SCAN_IND
    if(type == 27): return "SCAN_RSP" # 0x1B SCAN_RSP to ADV_IND
    
    # From manually inserting EIR type
    if(type == 50): return "EIR"

############################
# JSON insertion function
############################

# Generalized export capability for all AdvData types
def BTIDES_export_AdvData(bdaddr, random, adv_type, adv_data_type, data):
    global BTIDES_JSON
    #print(json.dumps(BTIDES_JSON, indent=2))
    base = lookup_base_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (base == None):
        # Insert new one
        insert_new_base_and_AdvChanArray_entry(bdaddr, random, adv_type, adv_data_type, data)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        #Check every AdvData entry and if we find an exact match to what we'd be inserting, just go ahead and return as done
        #print(f"adv_type = {adv_type}, adv_data_type = {adv_data_type}, data = {data}")
        insert_new_AdvChanArray_entry_only(base, adv_type, adv_data_type, data)
        return