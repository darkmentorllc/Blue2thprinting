########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

# Can't use qprint here, because this leads to circular depdendencies
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_base import generic_SingleBDADDR_insertion_into_BTIDES_second_level_array
import TME.TME_glob

def ff_AdvChanData(type=None, type_str=None, CSA=None, full_pkt_hex_str=None, AdvDataArray=None):
    AdvChanData = {}
    #print(f"type = {type}, type_str = {type_str}")
    if (type != None and (type in adv_chan_types_to_strings.keys())):
        AdvChanData["type"] = type
    if (CSA != None):
        AdvChanData["CSA"] = CSA
    if (full_pkt_hex_str != None):
        AdvChanData["full_pkt_hex_str"] = full_pkt_hex_str
    if (AdvDataArray != None):
        AdvChanData["AdvDataArray"] = AdvDataArray

    if(TME.TME_glob.verbose_BTIDES and type_str != None and (type_str in adv_chan_types_to_strings.values())):
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
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "Flags"
    return obj

# type 2 & 3
def ff_UUID16Lists(list_type, data):
    obj = {"type": list_type, "length": data["length"], "UUID16List": data["UUID16List"]}
    if(TME.TME_glob.verbose_BTIDES):
        if(list_type == type_AdvData_UUID16ListIncomplete):
            obj["type_str"] = "UUID16ListIncomplete"
        elif(list_type == type_AdvData_UUID16ListComplete):
            obj["type_str"] = "UUID16ListComplete"
    return obj

# type 4 & 5
def ff_UUID32Lists(list_type, data):
    obj = {"type": list_type, "length": data["length"], "UUID32List": data["UUID32List"]}
    if(TME.TME_glob.verbose_BTIDES):
        if(list_type == type_AdvData_UUID32ListIncomplete):
            obj["type_str"] = "UUID32ListIncomplete"
        elif(list_type == type_AdvData_UUID32ListComplete):
            obj["type_str"] = "UUID32ListComplete"
    return obj

# type 6 & 7
def ff_UUID128Lists(list_type, data):
    obj = {"type": list_type, "length": data["length"], "UUID128List": data["UUID128List"]}
    if(TME.TME_glob.verbose_BTIDES):
        if(list_type == type_AdvData_UUID128ListIncomplete):
            obj["type_str"] = "UUID128ListIncomplete"
        elif(list_type == type_AdvData_UUID128ListComplete):
            obj["type_str"] = "UUID128ListComplete"
    return obj

# type 8 & 9 & 0x30
def ff_Names(name_type, data):
    obj = {"type": name_type, "length":  data["length"], "name_hex_str": data["name_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        if(name_type == type_AdvData_IncompleteName):
            obj["type_str"] = "IncompleteName"
        elif(name_type == type_AdvData_CompleteName):
            obj["type_str"] = "CompleteName"
        elif(name_type == type_AdvData_BroadcastName):
            obj["type_str"] = "BroadcastName"

        if(data["utf8_name"]):
            obj["utf8_name"] = data["utf8_name"]

    return obj

# type 0x0A
def ff_TxPower(data):
    obj = {"type": type_AdvData_TxPower, "length": data["length"], "tx_power": data["tx_power"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "TxPower"
    return obj

# type 0x0D
def ff_ClassOfDevice(data):
    obj = {"type": type_AdvData_ClassOfDevice, "length": data["length"], "CoD_hex_str": data["CoD_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "ClassOfDevice"
    return obj

# type 0x10
def ff_DeviceID(data):
    obj = {"type": type_AdvData_DeviceID, "length": data["length"], "vendor_id_source": data["vendor_id_source"], "vendor_id": data["vendor_id"], "product_id": data["product_id"], "version": data["version"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "DeviceID"
    return obj

# type 0x12
def ff_PeripheralConnectionIntervalRange(data):
    obj = {"type": type_AdvData_PeripheralConnectionIntervalRange, "length": data["length"], "conn_interval_min": data["conn_interval_min"], "conn_interval_max": data["conn_interval_max"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "PeripheralConnectionIntervalRange"
    return obj

# type 0x14
def ff_UUID16ListServiceSolicitation(data):
    obj = {"type": type_AdvData_UUID16ListServiceSolicitation, "length": data["length"], "UUID16List": data["UUID16List"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "UUID16ListServiceSolicitation"
    return obj

# type 0x15
def ff_UUID128ListServiceSolicitation(data):
    obj = {"type": type_AdvData_UUID128ListServiceSolicitation, "length": data["length"], "UUID128List": data["UUID128List"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "UUID128ListServiceSolicitation"
    return obj

# type 0x16
def ff_UUID16ServiceData(data):
    obj = {"type": type_AdvData_UUID16ServiceData, "length": data["length"], "UUID16": data["UUID16"], "service_data_hex_str": data["service_data_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "UUID16ServiceData"
    return obj

# type 0x17
def ff_PublicTargetAddress(data):
    obj = {"type": type_AdvData_PublicTargetAddress, "length": data["length"], "public_bdaddr": data["public_bdaddr"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "PublicTargetAddress"
    return obj

# type 0x18
def ff_RandomTargetAddress(data):
    obj = {"type": type_AdvData_RandomTargetAddress, "length": data["length"], "random_bdaddr": data["random_bdaddr"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "RandomTargetAddress"
    return obj

# type 0x19
def ff_Appearance(data):
    obj = {"type": type_AdvData_Appearance, "length": data["length"], "appearance_hex_str": data["appearance_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "Appearance"
    return obj

# type 0x1A
def ff_AdvertisingInterval(data):
    obj = {"type": type_AdvData_AdvertisingInterval, "length": data["length"], "advertising_interval": data["advertising_interval"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "AdvertisingInterval"
    return obj

# type 0x1B
def ff_LE_BDADDR(data):
    obj = {"type": type_AdvData_LE_BDADDR, "length": data["length"], "bdaddr_type": data["bdaddr_type"], "le_bdaddr": data["le_bdaddr"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "LE_BDADDR"
    return obj

# type 0x1C
def ff_LE_Role(data):
    obj = {"type": type_AdvData_LE_Role, "length": data["length"], "role": data["role"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "LE_Role"
    return obj

# type 0x20
def ff_UUID32ServiceData(data):
    obj = {"type": type_AdvData_UUID32ServiceData, "length": data["length"], "UUID32": data["UUID32"], "service_data_hex_str": data["service_data_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "UUID32ServiceData"
    return obj

# type 0x21
def ff_UUID128ServiceData(data):
    obj = {"type": type_AdvData_UUID128ServiceData, "length": data["length"], "UUID128": data["UUID128"], "service_data_hex_str": data["service_data_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "UUID128ServiceData"
    return obj

# type 0x24
def ff_URI(data):
    obj = {"type": type_AdvData_URI, "length": data["length"], "uri_hex_str": data["uri_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "URI"
    return obj

# type 0x30 handled in ff_Names

# type 0x3d
def ff_3DInfoData(data):
    obj = {"type": type_AdvData_3DInfoData, "length": data["length"], "byte1": data["byte1"], "path_loss": data["path_loss"]}
    if(TME.TME_glob.verbose_BTIDES):
        obj["type_str"] = "3DInfoData"
    return obj

# type 0xFF
def ff_MSD(data):
    obj = {"type": type_AdvData_MSD, "length": data["length"], "company_id_hex_str": data["company_id_hex_str"], "msd_hex_str": data["msd_hex_str"]}
    if(TME.TME_glob.verbose_BTIDES):
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

    if(adv_data_type == type_AdvData_IncompleteName or adv_data_type == type_AdvData_CompleteName or adv_data_type == type_AdvData_BroadcastName):
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

    if(adv_data_type == type_AdvData_AdvertisingInterval):
        if(AdvDataArrayEntry["length"] == data["length"] and
           AdvDataArrayEntry["advertising_interval"] == data["advertising_interval"]):
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

    if(adv_data_type == type_AdvData_UUID16ListServiceSolicitation):
        if(AdvDataArrayEntry["length"] == data["length"] and
           AdvDataArrayEntry["UUID16List"] == data["UUID16List"]): # TODO: Can list equality be checked this way?
            return True
        else: return False

    if(adv_data_type == type_AdvData_UUID128ListServiceSolicitation):
        if(AdvDataArrayEntry["length"] == data["length"] and
           AdvDataArrayEntry["UUID128List"] == data["UUID128List"]): # TODO: Can list equality be checked this way?
            return True
        else: return False

    if(adv_data_type == type_AdvData_PublicTargetAddress):
        if(AdvDataArrayEntry["public_bdaddr"] == data["public_bdaddr"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_RandomTargetAddress):
        if(AdvDataArrayEntry["random_bdaddr"] == data["random_bdaddr"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_LE_BDADDR):
        if(AdvDataArrayEntry["le_bdaddr"] == data["le_bdaddr"] and AdvDataArrayEntry["bdaddr_type"] == data["bdaddr_type"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_LE_Role):
        if(AdvDataArrayEntry["role"] == data["role"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_URI):
        if(AdvDataArrayEntry["uri_hex_str"] == data["uri_hex_str"]):
            return True
        else: return False

    if(adv_data_type == type_AdvData_3DInfoData):
        if(AdvDataArrayEntry["byte1"] == data["byte1"] and AdvDataArrayEntry["path_loss"] == data["path_loss"]):
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

    if(adv_data_type == type_AdvData_IncompleteName or adv_data_type == type_AdvData_CompleteName or adv_data_type == type_AdvData_BroadcastName):
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

    if(adv_data_type == type_AdvData_AdvertisingInterval):
        return ff_AdvertisingInterval(data)

    if(adv_data_type == type_AdvData_UUID16ServiceData):
        return ff_UUID16ServiceData(data)

    if(adv_data_type == type_AdvData_UUID32ServiceData):
        return ff_UUID32ServiceData(data)

    if(adv_data_type == type_AdvData_UUID128ServiceData):
        return ff_UUID128ServiceData(data)

    if(adv_data_type == type_AdvData_UUID16ListServiceSolicitation):
        return ff_UUID16ListServiceSolicitation(data)

    if(adv_data_type == type_AdvData_UUID128ListServiceSolicitation):
        return ff_UUID128ListServiceSolicitation(data)

    if(adv_data_type == type_AdvData_PublicTargetAddress):
        return ff_PublicTargetAddress(data)

    if(adv_data_type == type_AdvData_RandomTargetAddress):
        return ff_RandomTargetAddress(data)

    if(adv_data_type == type_AdvData_LE_BDADDR):
        return ff_LE_BDADDR(data)

    if(adv_data_type == type_AdvData_LE_Role):
        return ff_LE_Role(data)

    if(adv_data_type == type_AdvData_URI):
        return ff_URI(data)

    if(adv_data_type == type_AdvData_3DInfoData):
        return ff_3DInfoData(data)

    if(adv_data_type == type_AdvData_MSD):
        return ff_MSD(data)

    return None

# See get_le_event_type_string() for what's what
# TODO: add AUX_* types once I start importing those into the db
def pdu_type_to_BTIDES_type(type):
    # FIXME!: I found based on this that I'm overloading PCAP types and old HCI types and they're off by 1!
    # I will need to change db and re-process everything to fix :-/
    # Values from pcaps and newer HCI logs
    if(type == type_AdvChanPDU_ADV_IND):            return type_BTIDES_ADV_IND
    if(type == type_AdvChanPDU_ADV_DIRECT_IND):     return type_BTIDES_ADV_DIRECT_IND
    if(type == type_AdvChanPDU_ADV_SCAN_IND):       return type_BTIDES_ADV_SCAN_IND
    if(type == type_AdvChanPDU_ADV_NONCONN_IND):    return type_BTIDES_ADV_NONCONN_IND
    if(type == type_AdvChanPDU_SCAN_RSP):           return type_BTIDES_SCAN_RSP # SCAN_RSP
    if(type == type_AdvChanPDU_SCAN_REQ):           return type_AdvChanPDU_ADV_NONCONN_IND #FIXME IN THE FUTURE: From accidental incorrect pcap mix-in off-by-one
    #if(type == 6): return btype_SCAN_RSP # SCAN_RSP # FIXME: From accidental incorrect pcap mix-in

    # Values from older HCI logs where they had a different format for the event type which was a bitfield of scannable, connectable, etc
    # instead of just using the PDU type from the packet as they seem to in newer HCI logs
    # From "Event_Type values for legacy PDUs" in spec apparently
    if(type == 16): return type_BTIDES_ADV_NONCONN_IND  # 0x10 0b10000 ADV_NONCONN_IND
    if(type == 18): return type_BTIDES_ADV_SCAN_IND     # 0x12 0b10010 ADV_SCAN_IND
    if(type == 19): return type_BTIDES_ADV_IND          # 0x13 0b10011 ADV_IND
    if(type == 21): return type_BTIDES_ADV_DIRECT_IND   # 0x15 0b10101 ADV_DIRECT_IND
    if(type == 26): return type_BTIDES_SCAN_RSP         # 0x1A 0b11010 SCAN_RSP to ADV_SCAN_IND
    if(type == 27): return type_BTIDES_SCAN_RSP         # 0x1B 0b11011 SCAN_RSP to ADV_IND

    # From manually inserting EIR type
    if(type == 50): return 50 # EIR

# See get_le_event_type_string() for what's what
# TODO: add AUX_* types once I start importing those into the db
def pdu_type_to_BTIDES_type_str(type):
    # FIXME!: I found based on this that I'm overloading PCAP types and old HCI types and they're off by 1!
    # I will need to change db and re-process everything to fix :-/
    # Values from pcaps and newer HCI logs
    # FOR NOW I'M USING THE HCI TYPES, BECAUSE THAT'S WHAT MOST OF MY DATA IS IN
    if(type == type_AdvChanPDU_ADV_IND):            return "ADV_IND"
    if(type == type_AdvChanPDU_ADV_DIRECT_IND):     return "ADV_DIRECT_IND" # FIXME: I don't know if that's what this actually is, since I have no examples in the HCI log I'm looking at
    if(type == type_AdvChanPDU_ADV_SCAN_IND):       return "ADV_SCAN_IND"
    if(type == type_AdvChanPDU_ADV_NONCONN_IND):    return "ADV_NONCONN_IND"
    if(type == type_AdvChanPDU_SCAN_RSP):           return "SCAN_RSP"
    if(type == type_AdvChanPDU_SCAN_REQ):           return "ADV_NONCONN_IND" #FIXME IN THE FUTURE: From accidental incorrect pcap mix-in off-by-one
    #if(type == 6): return "SCAN_RSP" # FIXME: From accidental incorrect pcap mix-in. Replace with proper

    # Values from older HCI logs where they had a different format for the event type which was a bitfield of scannable, connectable, etc
    # instead of just using the PDU type from the packet as they seem to in newer HCI logs
    # From "Event_Type values for legacy PDUs" in spec apparently
    if(type == 16): return "ADV_NONCONN_IND"    # 0x10 0b10000 ADV_NONCONN_IND
    if(type == 18): return "ADV_SCAN_IND"       # 0x12 0b10010 ADV_SCAN_IND
    if(type == 19): return "ADV_IND"            # 0x13 0b10011 ADV_IND
    if(type == 21): return "ADV_DIRECT_IND"     # 0x15 0b10101 ADV_DIRECT_IND
    if(type == 26): return "SCAN_RSP"           # 0x1A 0b11010 SCAN_RSP to ADV_SCAN_IND
    if(type == 27): return "SCAN_RSP"           # 0x1B 0b11011 SCAN_RSP to ADV_IND

    # From manually inserting EIR type
    if(type == 50): return "EIR"

############################
# JSON insertion function
############################

# Generalized export capability for all AdvData types
def BTIDES_export_AdvData(bdaddr, random, adv_type, adv_data_type, data):
    btype = pdu_type_to_BTIDES_type(adv_type)
    btype_str = None
    if(TME.TME_glob.verbose_BTIDES):
        btype_str = pdu_type_to_BTIDES_type_str(adv_type)
    adv_chan_array_entry = ff_AdvChanData(type=btype, type_str=btype_str)
    adv_data = ff_adv_data_type_specific_obj(adv_data_type, data)
    adv_chan_array_entry["AdvDataArray"] = [ adv_data ]

    generic_SingleBDADDR_insertion_into_BTIDES_second_level_array(bdaddr, random, adv_chan_array_entry, "AdvChanArray", adv_data, "AdvDataArray")