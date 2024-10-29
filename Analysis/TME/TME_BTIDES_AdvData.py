########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

type_AdvData_Flags          = 1
type_AdvData_IncompleteName = 8
type_AdvData_CompleteName   = 9
type_AdvData_TxPower        = 10
type_AdvData_MSD            = 255

def lookup_AdvChanData(entry, type=None, type_str=None):
    for ad in entry["AdvChanArray"]:
        if(ad.type == type and ad.type_str == type_str):
            return ad

    return None

############################
# Helper "factory functions"
############################  

# Valid types defined in BTIDES schema
valid_adv_chan_types = [0, 1, 2, 3, 10, 20, 21, 50]
valid_adv_chan_type_strs = ["ADV_IND", "ADV_DIRECT_IND", "ADV_NONCONN_IND", "ADV_SCAN_IND", "AUX_ADV_IND", "SCAN_RSP", "AUX_SCAN_RSP", "EIR"]
def ff_AdvChanData(type=None, type_str=None, CSA=None, full_pkt_hex_str=None, AdvDataArray=None):
    AdvChanData = {}
    ###print(f"ff_AdvChanData: type = {type}")
    ###print(f"ff_AdvChanData: type_str = {type_str}")
    if (type != None and (type in valid_adv_chan_types)):
        AdvChanData["type"] = type
    if (type_str != None and (type_str in valid_adv_chan_type_strs)):
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

def ff_Flags(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host):
    flags_hex_str = get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
    obj = {"type": type_AdvData_Flags, "length": 2, "flags_hex_str": flags_hex_str}
    if(verbose_BTIDES):
        obj["type_str"] = "Flags"
    return obj

def ff_Name(length, name_type, name):
    obj = {"type": name_type, "length": length, "name": name}
    if(verbose_BTIDES):
        if(name_type == type_AdvData_IncompleteName):
            obj["type_str"] = "IncompleteName"
        elif(name_type == type_AdvData_CompleteName):
            obj["type_str"] = "CompleteName"
    return obj

def ff_TxPower(power):
    obj = {"type": type_AdvData_TxPower, "length": 2, "tx_power": power}
    if(verbose_BTIDES):
        obj["type_str"] = "TxPower"
    return obj

def ff_MSD(length, company_id_hex_str, MSD_hex_str):
    obj = {"type": type_AdvData_MSD, "length": length, "company_id_hex_str": company_id_hex_str, "msd_hex_str": MSD_hex_str}
    if(verbose_BTIDES):
        obj["type_str"] = "ManufacturerSpecificData"
    return obj

# See get_le_event_type_string() for what's what
# TODO: add AUX_* types once I start importing those into the db
def le_evt_type_to_BTIDES_types(type):
    # FIXME!: I found based on this that I'm overloading PCAP types and old HCI types and they're off by 1!
    # I will need to change db and re-process everything to fix :-/
    # Values from pcaps and newer HCI logs
    if(type >= 0 and type <= 3): return type
    if(type == 4): return 20 # SCAN_RSP
    if(type == 6): return 20 # SCAN_RSP # From accidental incorrect pcap mix-in
    
    # Values from older HCI logs where they had a different format for the event type which was a bitfield of scannable, connectable, etc
    # instead of just using the PDU type from the packet as they seem to in newer HCI logs
    # From "Event_Type values for legacy PDUs" in spec apparently 
    if(type == 19): return 0 # 0x13 ADV_IND
    if(type == 16): return 2 # 0x10 ADV_NONCONN_IND
    if(type == 18): return 3 # 0x12 ADV_SCAN_IND
    if(type == 21): return 1 # 0x15 ADV_DIRECT_IND
    if(type == 26): return 20 # 0x1A SCAN_RSP to ADV_SCAN_IND
    if(type == 27): return 20 # 0x1B SCAN_RSP to ADV_IND
    
    # From manually inserting EIR type
    if(type == 50): return 50 # EIR
    
# See get_le_event_type_string() for what's what
# TODO: add AUX_* types once I start importing those into the db
def le_evt_type_to_BTIDES_type_str(type):
    # FIXME!: I found based on this that I'm overloading PCAP types and old HCI types and they're off by 1!
    # I will need to change db and re-process everything to fix :-/
    # Values from pcaps and newer HCI logs
    # FOR NOW I'M USING THE HCI TYPES, BECAUSE THAT'S WHAT MOST OF MY DATA IS IN
    if(type == 0): return "ADV_IND"
    if(type == 1): return "ADV_DIRECT_IND" # FIXME: I don't know if that's what this actually is, since I have no examples in the HCI log I'm looking at
    if(type == 2): return "ADV_SCAN_IND"
    if(type == 3): return "ADV_NONCONN_IND"
    if(type == 4): return "SCAN_RSP"
    if(type == 6): return "SCAN_RSP" # From accidental incorrect pcap mix-in
    
    # Values from older HCI logs where they had a different format for the event type which was a bitfield of scannable, connectable, etc
    # instead of just using the PDU type from the packet as they seem to in newer HCI logs
    # From "Event_Type values for legacy PDUs" in spec apparently 
    if(type == 19): return "ADV_IND" # 0x13 ADV_IND
    if(type == 16): return "ADV_NONCONN_IND" # 0x10 ADV_NONCONN_IND
    if(type == 18): return "ADV_SCAN_IND" # 0x12 ADV_SCAN_IND
    if(type == 21): return "ADV_DIRECT_IND" # 0x15 ADV_DIRECT_IND
    if(type == 26): return "SCAN_RSP" # 0x1A SCAN_RSP to ADV_SCAN_IND
    if(type == 27): return "SCAN_RSP" # 0x1B SCAN_RSP to ADV_IND
    
    # From manually inserting EIR type
    if(type == 50): return "EIR"

############################
# JSON insertion functions
############################
# All functions follow this flow:
# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the TxPower data into a AdvChanArray->AdvChanData->AdvDataArray entry
#  If an existing AdvChanData entry already exists, this is done
#  If no AdvChanData exists, it creates one 

def BTIDES_export_Flags(bdaddr, random, type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    btype = le_evt_type_to_BTIDES_types(type)
    btype_str = le_evt_type_to_BTIDES_type_str(type)
    flags_hex_str = get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
    #print(f"type = {type}, btype = {btype}, btype_str = {btype_str}")
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # Insert new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(base, indent=2))
        acd = ff_AdvChanData(type=btype, type_str=btype_str)
        acd["AdvDataArray"] = [ ff_Flags(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) ]
        #print(json.dumps(acd, indent=2))
        base["AdvChanArray"] = [ acd ]
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("AdvChanArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any AdvChanArray entries, so just insert ours
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_Flags(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) ]
            entry["AdvChanArray"] = [ acd ]
            #print(json.dumps(acd, indent=2))
            return
        else:
            #Check every AdvData entry and if we find an exact match to what we'd be inserting, just go ahead and return as done
            for AdvChanEntry in entry["AdvChanArray"]:
                ###print(AdvChanEntry)
                if(AdvChanEntry != None and AdvChanEntry["type"] == btype and AdvChanEntry["type_str"] == btype_str):
                    # This AdvData is of the same type as we're currently processing for this insert
                    # Now check if there's an AdvDataArray entry that exactly matches 
                    for AdvDataEntry in AdvChanEntry["AdvDataArray"]:
                        # TODO: pass through length in the future
                        if(AdvDataEntry["type"] == type_AdvData_Flags and AdvDataEntry["length"] == 2 and 
                           "flags_hex_str" in AdvDataEntry.keys() and AdvDataEntry["flags_hex_str"] == flags_hex_str):
                            # We already have the entry we would insert, so just go ahead and return
                            ###print("BTIDES_export_TxPower: found existing match. Nothing to do. Returning.")
                            ###print(json.dumps(BTIDES_JSON, indent=2))
                            return
                    # If we got here we didn't find any match, so we now need to insert our entry
                    # Insert into inner AdvDataArray
                    AdvChanEntry["AdvDataArray"].append(ff_Flags(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host))
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # Insert into outer AdvChanArray
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_Flags(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) ]
            entry["AdvChanArray"].append(acd)
            #print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_Name(bdaddr, random, type, name_type, name):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    btype = le_evt_type_to_BTIDES_types(type)
    btype_str = le_evt_type_to_BTIDES_type_str(type)
    #print(f"type = {type}, btype = {btype}, btype_str = {btype_str}")
    length = int(1 + len(name)) # 1 bytes for opcode + length of the string
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # Insert new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(base, indent=2))
        acd = ff_AdvChanData(type=btype, type_str=btype_str)
        acd["AdvDataArray"] = [ ff_Name(length, name_type, name) ]
        #print(json.dumps(acd, indent=2))
        base["AdvChanArray"] = [ acd ]
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("AdvChanArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any AdvChanArray entries, so just insert ours
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_Name(length, name_type, name) ]
            entry["AdvChanArray"] = [ acd ]
            #print(json.dumps(acd, indent=2))
            return
        else:
            #Check every AdvData entry and if we find an exact match to what we'd be inserting, just go ahead and return as done
            for AdvChanEntry in entry["AdvChanArray"]:
                ###print(AdvChanEntry)
                if(AdvChanEntry != None and AdvChanEntry["type"] == btype and AdvChanEntry["type_str"] == btype_str):
                    # This AdvData is of the same type as we're currently processing for this insert
                    # Now check if there's an AdvDataArray entry that exactly matches
                    for AdvDataEntry in AdvChanEntry["AdvDataArray"]:
                        # TODO: pass through length in the future
                        if(AdvDataEntry["type"] == name_type and AdvDataEntry["length"] == length and 
                           "name" in AdvDataEntry.keys() and AdvDataEntry["name"] == name):
                            # We already have the entry we would insert, so just go ahead and return
                            ###print("BTIDES_export_TxPower: found existing match. Nothing to do. Returning.")
                            ###print(json.dumps(BTIDES_JSON, indent=2))
                            return
                    # If we get here we didn't find any match, so we now need to insert our entry
                    # Insert into inner AdvDataArray
                    print("before")
                    print(json.dumps(AdvChanEntry["AdvDataArray"], indent=2))
                    AdvChanEntry["AdvDataArray"].append( ff_Name(length, name_type, name) )
                    print("after")
                    print(json.dumps(AdvChanEntry["AdvDataArray"], indent=2))
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # Insert into outer AdvChanArray
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_Name(length, name_type, name) ]
            entry["AdvChanArray"].append(acd)
            #print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_TxPower(bdaddr, random, type, data):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    btype = le_evt_type_to_BTIDES_types(type)
    btype_str = le_evt_type_to_BTIDES_type_str(type)
    #print(f"type = {type}, btype = {btype}, btype_str = {btype_str}")
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # Insert new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(base, indent=2))
        acd = ff_AdvChanData(type=btype, type_str=btype_str)
        acd["AdvDataArray"] = [ ff_TxPower(data) ]
        ###print(json.dumps(acd, indent=2))
        base["AdvChanArray"] = [ acd ]
        BTIDES_JSON.append(base)
        ###print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("AdvChanArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any AdvChanArray entries, so just insert ours
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_TxPower(data) ]
            entry["AdvChanArray"] = [ acd ]
            #print(json.dumps(acd, indent=2))
            return
        else:
            #Check every AdvData entry and if we find an exact match to what we'd be inserting, just go ahead and return as done
            for AdvChanEntry in entry["AdvChanArray"]:
                ###print(AdvChanEntry)
                if(AdvChanEntry != None and AdvChanEntry["type"] == btype and AdvChanEntry["type_str"] == btype_str):
                    # This AdvData is of the same type as we're currently processing for this insert
                    # Now check if there's an AdvDataArray entry that exactly matches 
                    for AdvDataEntry in AdvChanEntry["AdvDataArray"]:
                        # TODO: pass through length in the future
                        if(AdvDataEntry["type"] == type_AdvData_TxPower and AdvDataEntry["length"] == 2 and 
                           "tx_power" in AdvDataEntry.keys() and AdvDataEntry["tx_power"] == data):
                            # We already have the entry we would insert, so just go ahead and return
                            ###print("BTIDES_export_TxPower: found existing match. Nothing to do. Returning.")
                            ###print(json.dumps(BTIDES_JSON, indent=2))
                            return
                    # If we get here we didn't find any match, so we now need to insert our entry
                    # Insert into inner AdvDataArray
                    AdvChanEntry["AdvDataArray"].append(ff_TxPower(data))
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # Insert into outer AdvChanArray
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_TxPower(data) ] 
            entry["AdvChanArray"].append(acd)
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return

def BTIDES_export_MSD(bdaddr, random, type, company_id, MSD_hex_str):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    btype = le_evt_type_to_BTIDES_types(type)
    btype_str = le_evt_type_to_BTIDES_type_str(type)
    #print(f"type = {type}, btype = {btype}, btype_str = {btype_str}")
    company_id_hex_str = f"{company_id:04x}"
    length = int(3 + (len(MSD_hex_str) / 2)) # 3 bytes for opcode + company ID, and length of the hex_str divided by 2 for the number of bytes
    entry = lookup_entry(bdaddr, random)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # Insert new one
        base = ff_base(bdaddr, random)
        ###print(json.dumps(base, indent=2))
        acd = ff_AdvChanData(type=btype, type_str=btype_str)
        acd["AdvDataArray"] = [ ff_MSD(length, company_id_hex_str, MSD_hex_str) ]
        #print(json.dumps(acd, indent=2))
        base["AdvChanArray"] = [ acd ]
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("AdvChanArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any AdvChanArray entries, so just insert ours
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_MSD(length, company_id_hex_str, MSD_hex_str) ]
            entry["AdvChanArray"] = [ acd ]
            #print(json.dumps(acd, indent=2))
            return
        else:
            #Check every AdvData entry and if we find an exact match to what we'd be inserting, just go ahead and return as done
            for AdvChanEntry in entry["AdvChanArray"]:
                ###print(AdvChanEntry)
                if(AdvChanEntry != None and AdvChanEntry["type"] == btype and AdvChanEntry["type_str"] == btype_str):
                    # This AdvData is of the same type as we're currently processing for this insert
                    # Now check if there's an AdvDataArray entry that exactly matches
                    for AdvDataEntry in AdvChanEntry["AdvDataArray"]:
                        # TODO: pass through length in the future
                        if(AdvDataEntry["type"] == type_AdvData_MSD and AdvDataEntry["length"] == length and 
                           "company_id_hex_str" in AdvDataEntry.keys() and AdvDataEntry["company_id_hex_str"] == company_id_hex_str and
                            "msd_hex_str" in AdvDataEntry.keys() and AdvDataEntry["msd_hex_str"] == MSD_hex_str):
                            # We already have the entry we would insert, so just go ahead and return
                            ###print("BTIDES_export_TxPower: found existing match. Nothing to do. Returning.")
                            ###print(json.dumps(BTIDES_JSON, indent=2))
                            return
                    # If we get here we didn't find any match, so we now need to insert our entry
                    # Insert into inner AdvDataArray
                    ###print(json.dumps(AdvChanEntry["AdvDataArray"], indent=2))
                    AdvChanEntry["AdvDataArray"].append( ff_MSD(length, company_id_hex_str, MSD_hex_str) )
                    ###print(json.dumps(AdvChanEntry["AdvDataArray"], indent=2))
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # Insert into outer AdvChanArray
            acd = ff_AdvChanData(type=btype, type_str=btype_str)
            acd["AdvDataArray"] = [ ff_MSD(length, company_id_hex_str, MSD_hex_str) ]
            entry["AdvChanArray"].append(acd)
            #print(json.dumps(BTIDES_JSON, indent=2))
            return