########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################
# This file is to import data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html
# into the Blue2thprinting MySQL database

# Activate venv before any other imports
import os
import sys
from pathlib import Path
from handle_venv import activate_venv
activate_venv()

######################################################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
######################################################
# THIS IS YOUR REMINDER THAT THE BTIDES INPUT FILE IS ENTIRELY
# ACID (Attacker-Controlled Input Data)!
# SANITY CHECK THE HELL OUT OF EVERY FIELD BEFORE USE!
# OTHERWISE YOU WILL HAVE SQL INJECTION VULNS (AT A MINIMUM)!

import argparse
import json

from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator

import TME.TME_glob
from TME.TME_helpers import execute_query, execute_insert, qprint
from TME.TME_BTIDES_base import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_UUID128 import add_dashes_to_UUID128

###################################
# Globals
###################################

###################################
# Helper functions
###################################




###################################
# BTIDES_AdvData.json information
###################################

def BTIDES_types_to_le_evt_type(type):
    # FIXME!: In the future once I update to have a src file type field (or foreign key pointer to row with that field)
    # For now I will just use the pcap PDU values, since they correspond 1:1 to BTIDES for the first 4 entries
    if(type == type_BTIDES_ADV_IND):          return type_AdvChanPDU_ADV_IND # AUX_ADV_IND
    if(type == type_BTIDES_ADV_DIRECT_IND):   return type_AdvChanPDU_ADV_DIRECT_IND # AUX_ADV_IND
    if(type == type_BTIDES_ADV_NONCONN_IND):  return type_AdvChanPDU_ADV_NONCONN_IND # AUX_ADV_IND
    if(type == type_BTIDES_ADV_SCAN_IND):     return type_AdvChanPDU_ADV_SCAN_IND # AUX_ADV_IND
    if(type == type_BTIDES_AUX_ADV_IND):      return type_AdvChanPDU_AUX_ADV_IND # AUX_ADV_IND
    if(type == type_BTIDES_SCAN_RSP):         return type_AdvChanPDU_SCAN_RSP # SCAN_RSP # From accidental incorrect pcap mix-in
    if(type == type_BTIDES_AUX_SCAN_RSP):     return type_AdvChanPDU_AUX_SCAN_RSP # AUX_SCAN_RSP # FIXME: I don't yet know what value this should take on

    # From manually inserting EIR type
    # There is of course no corresponding LE type
    if(type == type_BTIDES_EIR):              return type_BTIDES_EIR


# type 0x01
def import_AdvData_Flags(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_Flags!")

    le_limited_discoverable_mode = 0
    le_general_discoverable_mode = 0
    bredr_not_supported = 0
    le_bredr_support_controller = 0
    le_bredr_support_host = 0
    flags_hex_str = leaf["flags_hex_str"]
    flags_int = int(flags_hex_str, 16)
    if(flags_int & (1 << 0)):
        le_limited_discoverable_mode = 1
    if(flags_int & (1 << 1)):
        le_general_discoverable_mode = 1
    if(flags_int & (1 << 2)):
        bredr_not_supported = 1
    if(flags_int & (1 << 3)):
        le_bredr_support_controller = 1
    if(flags_int & (1 << 4)):
        le_bredr_support_host = 1

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        values = (bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_flags (bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) VALUES (%s, %s, %s, %s, %s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_flags (bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# types 0x02 & 0x03
def import_AdvData_UUID16s(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID16s!")
    str_UUID16s = ",".join(leaf["UUID16List"])
    list_type = leaf["type"]

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        values = (bdaddr, list_type, str_UUID16s)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_UUID16s (bdaddr, list_type, str_UUID16s) VALUES (%s, %s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, list_type, str_UUID16s)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID16s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID16s) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# types 0x04 & 0x05
def import_AdvData_UUID32s(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID32s!")
    str_UUID32s = ",".join(leaf["UUID32List"])
    list_type = leaf["type"]

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        values = (bdaddr, list_type, str_UUID32s)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_UUID32s (bdaddr, list_type, str_UUID32s) VALUES (%s, %s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, list_type, str_UUID32s)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID32s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID32s) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# types 0x06 & 0x07
def import_AdvData_UUID128s(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID128s!")
    UUID128List = leaf["UUID128List"]
    for i in range(len(UUID128List)):
        UUID128List[i] = UUID128List[i].replace('-','')
    str_UUID128s = ",".join(UUID128List)
    str_UUID128s.replace("-","")
    list_type = leaf["type"]

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        values = (bdaddr, list_type, str_UUID128s)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_UUID128s (bdaddr, list_type, str_UUID128s) VALUES (%s, %s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, list_type, str_UUID128s)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID128s_list (bdaddr, bdaddr_random, le_evt_type, list_type, str_UUID128s) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# types 0x08 & 0x09 & 0x30
def import_AdvData_Names(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_Names!")
    device_name_type = leaf["type"]
    name_hex_str = leaf["name_hex_str"]

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        values = (bdaddr, device_name_type, name_hex_str)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_name (bdaddr, device_name_type, name_hex_str) VALUES (%s, %s, %s);"
        execute_insert(eir_insert, values)
    else:
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_name (bdaddr, bdaddr_random, le_evt_type, device_name_type, name_hex_str) VALUES (%s, %s, %s, %s, %s);"
        values = (bdaddr, random, le_evt_type, device_name_type, name_hex_str)
        execute_insert(le_insert, values)


# type 0x0A
def import_AdvData_TxPower(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_TxPower!")
    device_tx_power = leaf["tx_power"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        values = (bdaddr, device_tx_power)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_tx_power (bdaddr, device_tx_power) VALUES (%s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, device_tx_power)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_tx_power (bdaddr, bdaddr_random, le_evt_type, device_tx_power) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x0D
def import_AdvData_ClassOfDevice(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_ClassOfDevice!")
    CoD_hex_str = leaf["CoD_hex_str"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        values = (bdaddr, CoD_hex_str)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_CoD (bdaddr, class_of_device) VALUES (%s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, CoD_hex_str)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_CoD (bdaddr, bdaddr_random, le_evt_type, class_of_device) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x10
def import_AdvData_DeviceID(bdaddr, db_type, leaf):
    #vprint("import_AdvData_DeviceID!")

    vendor_id_source = leaf["vendor_id_source"]
    vendor_id = leaf["vendor_id"]
    product_id = leaf["product_id"]
    product_version = leaf["version"]

    if(db_type == 50):
        # EIR
        values = (bdaddr, vendor_id_source, vendor_id, product_id, product_version)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_DevID (bdaddr, vendor_id_source, vendor_id, product_id, product_version) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(eir_insert, values)
    # AFAIK this can't exist in LE AdvData, only EIR


# type 0x12
def import_AdvData_PeripheralConnectionIntervalRange(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_PeripheralConnectionIntervalRange!")

    conn_interval_min = leaf["conn_interval_min"]
    conn_interval_max = leaf["conn_interval_max"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, conn_interval_min, conn_interval_max)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_connect_interval (bdaddr, bdaddr_random, le_evt_type, interval_min, interval_max) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)

# type 0x14
def import_AdvData_UUID16ListServiceSolicit(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID16ListServiceSolicit!")
    str_UUID16s = ",".join(leaf["UUID16List"])

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, str_UUID16s)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID16_service_solicit (bdaddr, bdaddr_random, le_evt_type, str_UUID16s) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)

# type 0x15
def import_AdvData_UUID128ListServiceSolicit(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID128ListServiceSolicit!")
    str_UUID128s = ",".join(leaf["UUID128List"])
    str_UUID128s.replace("-","")

    le_evt_type = db_type
    if(le_evt_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, str_UUID128s)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID128_service_solicit (bdaddr, bdaddr_random, le_evt_type, str_UUID128s) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x16
def import_AdvData_UUID16ServiceData(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID16ServiceData!")

    ACID_length = leaf["length"]
    UUID16_hex_str = leaf["UUID16"]
    service_data_hex_str = leaf["service_data_hex_str"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, ACID_length, UUID16_hex_str, service_data_hex_str)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID16_service_data (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID16_hex_str, service_data_hex_str) VALUES (%s, %s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x17
def import_AdvData_PublicTargetAddress(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_PublicTargetAddress!")
    public_bdaddr = leaf["public_bdaddr"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, public_bdaddr)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_public_target_bdaddr (bdaddr, bdaddr_random, le_evt_type, public_bdaddr) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)

# type 0x18
def import_AdvData_RandomTargetAddress(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_RandomTargetAddress!")
    random_bdaddr = leaf["random_bdaddr"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, random_bdaddr)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_public_target_bdaddr (bdaddr, bdaddr_random, le_evt_type, random_bdaddr) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x19
def import_AdvData_Appearance(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_Appearance!")

    appearance_int = int(leaf["appearance_hex_str"], 16)

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, appearance_int)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_appearance (bdaddr, bdaddr_random, le_evt_type, appearance) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)

# type 0x1B
def import_AdvData_LE_BDADDR(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_LE_BDADDR!")
    bdaddr_type = leaf["bdaddr_type"]
    le_bdaddr = leaf["le_bdaddr"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type,le_bdaddr, bdaddr_type)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_other_le_bdaddr (bdaddr, bdaddr_random, le_evt_type, other_bdaddr, other_bdaddr_random) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x1C - According to the spec this should only occur in OOB data, but we've seen devices using it for OTA data
def import_AdvData_LE_Role(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_LE_Role!")
    role = leaf["role"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, role)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_role (bdaddr, bdaddr_random, le_evt_type, role) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x20
def import_AdvData_UUID32ServiceData(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID32ServiceData!")

    ACID_length = leaf["length"]
    UUID32_hex_str = leaf["UUID32"]
    service_data_hex_str = leaf["service_data_hex_str"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, ACID_length, UUID32_hex_str, service_data_hex_str)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID32_service_data (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID32_hex_str, service_data_hex_str) VALUES (%s, %s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x21
def import_AdvData_UUID128ServiceData(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_UUID128ServiceData!")

    ACID_length = leaf["length"]
    UUID128_hex_str = leaf["UUID128"].replace("-","")
    service_data_hex_str = leaf["service_data_hex_str"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        # According to the spec this type shouldn't be able to appear in EIR, and consequently we don't have a table for it. Ignore it for now (reject it up front later?)
        return
    else:
        values = (bdaddr, random, le_evt_type, ACID_length, UUID128_hex_str, service_data_hex_str)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_UUID128_service_data (bdaddr, bdaddr_random, le_evt_type, ACID_length, UUID128_hex_str, service_data_hex_str) VALUES (%s, %s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x24
def import_AdvData_URI(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_URI!")

    uri_hex_str = leaf["uri_hex_str"]

    le_evt_type = db_type
    if(db_type == 50):
        values = (bdaddr, uri_hex_str)
        le_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_URI (bdaddr, uri_hex_str) VALUES (%s, %s);"
        execute_insert(le_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, uri_hex_str)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_URI (bdaddr, bdaddr_random, le_evt_type, uri_hex_str) VALUES (%s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0x30
# handled up in import_AdvData_Names


# type 0x3d
def import_AdvData_3DInfoData(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_3DInfoData!")

    byte1 = leaf["byte1"]
    path_loss = leaf["path_loss"]

    le_evt_type = db_type
    if(db_type == 50):
        values = (bdaddr, byte1, path_loss)
        le_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_3d_info (bdaddr, byte1, path_loss) VALUES (%s, %s, %s);"
        execute_insert(le_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, byte1, path_loss)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_3d_info (bdaddr, bdaddr_random, le_evt_type, byte1, path_loss) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


# type 0xFF
def import_AdvData_MSD(bdaddr, random, db_type, leaf):
    #vprint("import_AdvData_MSD!")

    device_BT_CID = int(leaf["company_id_hex_str"], 16)
    manufacturer_specific_data = leaf["msd_hex_str"]

    le_evt_type = db_type
    if(db_type == 50):
        # EIR
        values = (bdaddr, device_BT_CID, manufacturer_specific_data)
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_MSD (bdaddr, device_BT_CID, manufacturer_specific_data) VALUES (%s, %s, %s);"
        execute_insert(eir_insert, values)
    else:
        values = (bdaddr, random, le_evt_type, device_BT_CID, manufacturer_specific_data)
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_MSD (bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data) VALUES (%s, %s, %s, %s, %s);"
        execute_insert(le_insert, values)


def has_AdvDataArray(entry):
    if(entry != None and entry["AdvDataArray"] != None):
        return True
    else:
        return False


def has_known_AdvData_type(type, entry):
    if(entry != None and "type" in entry.keys() and entry["type"] == type):
        return True
    else:
        return False


def parse_AdvChanArray(entry):
    if("AdvChanArray" not in entry.keys() or entry["AdvChanArray"] == None):
        return # Entry not valid for this type

    bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

    for AdvChanEntry in entry["AdvChanArray"]:
        if(has_AdvDataArray(AdvChanEntry)):
            for AdvData in AdvChanEntry["AdvDataArray"]:
                # Flags
                if(has_known_AdvData_type(type_AdvData_Flags, AdvData)):
                    import_AdvData_Flags(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # Manufacturer-Specific Data - Optimization: put more-common data types earlier so they can continue sooner
                if(has_known_AdvData_type(type_AdvData_MSD, AdvData)):
                    import_AdvData_MSD(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID16ListIncomplete & UUID16ListComplete
                if(has_known_AdvData_type(type_AdvData_UUID16ListIncomplete, AdvData) or has_known_AdvData_type(type_AdvData_UUID16ListComplete, AdvData)):
                    import_AdvData_UUID16s(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID32ListIncomplete & UUID32ListComplete
                if(has_known_AdvData_type(type_AdvData_UUID32ListIncomplete, AdvData) or has_known_AdvData_type(type_AdvData_UUID32ListComplete, AdvData)):
                    import_AdvData_UUID32s(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID128ListIncomplete & UUID128ListComplete
                if(has_known_AdvData_type(type_AdvData_UUID128ListIncomplete, AdvData) or has_known_AdvData_type(type_AdvData_UUID128ListComplete, AdvData)):
                    import_AdvData_UUID128s(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # IncompleteName & CompleteName & BroadcastName
                if(has_known_AdvData_type(type_AdvData_IncompleteName, AdvData) or has_known_AdvData_type(type_AdvData_CompleteName, AdvData) or has_known_AdvData_type(type_AdvData_BroadcastName, AdvData)):
                    import_AdvData_Names(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # TxPower
                if(has_known_AdvData_type(type_AdvData_TxPower, AdvData)):
                    import_AdvData_TxPower(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # ClassOfDevice
                if(has_known_AdvData_type(type_AdvData_ClassOfDevice, AdvData)):
                    import_AdvData_ClassOfDevice(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # DeviceID
                if(has_known_AdvData_type(type_AdvData_DeviceID, AdvData)):
                    import_AdvData_DeviceID(bdaddr, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # PeripheralConnectionIntervalRange
                if(has_known_AdvData_type(type_AdvData_PeripheralConnectionIntervalRange, AdvData)):
                    import_AdvData_PeripheralConnectionIntervalRange(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID16ListServiceSolicitation
                if(has_known_AdvData_type(type_AdvData_UUID16ListServiceSolicitation, AdvData)):
                    import_AdvData_UUID16ListServiceSolicit(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID128ListServiceSolicitation
                if(has_known_AdvData_type(type_AdvData_UUID128ListServiceSolicitation, AdvData)):
                    import_AdvData_UUID128ListServiceSolicit(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # PublicTargetAddress
                if(has_known_AdvData_type(type_AdvData_PublicTargetAddress, AdvData)):
                    import_AdvData_PublicTargetAddress(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # RandomTargetAddress
                if(has_known_AdvData_type(type_AdvData_RandomTargetAddress, AdvData)):
                    import_AdvData_RandomTargetAddress(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # Appearance
                if(has_known_AdvData_type(type_AdvData_Appearance, AdvData)):
                    import_AdvData_Appearance(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # LE_BDADDR
                if(has_known_AdvData_type(type_AdvData_LE_BDADDR, AdvData)):
                    import_AdvData_LE_BDADDR(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # LE_Role
                if(has_known_AdvData_type(type_AdvData_LE_Role, AdvData)):
                    import_AdvData_LE_Role(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID16ServiceData
                if(has_known_AdvData_type(type_AdvData_UUID16ServiceData, AdvData)):
                    import_AdvData_UUID16ServiceData(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID32ServiceData
                if(has_known_AdvData_type(type_AdvData_UUID32ServiceData, AdvData)):
                    import_AdvData_UUID32ServiceData(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # UUID128ServiceData
                if(has_known_AdvData_type(type_AdvData_UUID128ServiceData, AdvData)):
                    import_AdvData_UUID128ServiceData(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # URI
                if(has_known_AdvData_type(type_AdvData_URI, AdvData)):
                    import_AdvData_URI(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

                # 3DInfoData
                if(has_known_AdvData_type(type_AdvData_3DInfoData, AdvData)):
                    import_AdvData_3DInfoData(bdaddr, bdaddr_rand, BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                    continue

###################################
# BTIDES_LL.json information
###################################

def import_LL_UNKNOWN_RSP(bdaddr, random, ll_entry):
    unknown_opcode = ll_entry["unknown_type"]
    values = (bdaddr, random, unknown_opcode)
    insert = f"INSERT IGNORE INTO LL_UNKNOWN_RSP (bdaddr, bdaddr_random, unknown_opcode) VALUES (%s, %s, %s);"
    execute_insert(insert, values)


def import_LL_VERSION_IND(bdaddr, random, ll_entry):
    ll_version = ll_entry["version"]
    device_BT_CID = ll_entry["company_id"]
    ll_sub_version = ll_entry["subversion"]
    values = (bdaddr, random, ll_version, device_BT_CID, ll_sub_version)
    insert = f"INSERT IGNORE INTO LL_VERSION_IND (bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version) VALUES (%s, %s, %s, %s, %s);"
    execute_insert(insert, values)


# This can be used for LL_FEATURE_REQ, LL_FEATURE_RSP, and LL_PERIPHERAL_FEATURE_REQ, since they're all going into the same table
def import_LL_FEATUREs(bdaddr, random, ll_entry):
    opcode = ll_entry["opcode"]
    features = int(ll_entry["le_features_hex_str"], 16)
    values = (bdaddr, random, opcode, features)
    insert = f"INSERT IGNORE INTO LL_FEATUREs (bdaddr, bdaddr_random, opcode, features) VALUES (%s, %s, %s, %s);"
    execute_insert(insert, values)


# This can be used for LL_PING_REQ or LL_PING_RSP since they're all going into the same table
def import_LL_PINGs(bdaddr, random, ll_entry, entry):
    direction = ll_entry["direction"]
    opcode = ll_entry["opcode"]
    if(direction == type_BTIDES_direction_C2P):
        if (opcode == type_LL_PING_RSP):
            # We can infer that if we see a C2P PING_RSP the P must have sent a PING_REQ.
            # So we're going to create an entry for that fact even if we don't have the
            # packet in the pcap (it could have got corrupted from Sniffle's vantage point)
            opcode = type_LL_PING_REQ
            direction = type_BTIDES_direction_P2C
            bdaddr, random = get_bdaddr_peripheral(entry)
        else:
            # TODO: For now skip the pings *our* Central sends to the Peripheral.
            # TODO: But ideally in the future we need to detect if the packet came
            # TODO: from *our* Central (hardcode its BDADDR?), or one which we just happen to have overhead by chance with Sniffle.
            # TODO: Because in the case of devices other than our own, we would want to capture the fact that a Central naturally sends pings
            return
    values = (bdaddr, random, opcode, direction)
    insert = f"INSERT IGNORE INTO LL_PINGs (bdaddr, bdaddr_random, opcode, direction) VALUES (%s, %s, %s, %s);"
    execute_insert(insert, values)


# This can be used for LL_FEATURE_REQ, LL_FEATURE_RSP, and LL_PERIPHERAL_FEATURE_REQ, since they're all going into the same table
def import_LL_LENGTHs(bdaddr, random, ll_entry):
    opcode = ll_entry["opcode"]
    max_rx_octets = ll_entry["max_rx_octets"]
    max_rx_time = ll_entry["max_rx_time"]
    max_tx_octets = ll_entry["max_tx_octets"]
    max_tx_time = ll_entry["max_tx_time"]
    values = (bdaddr, random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
    insert = f"INSERT IGNORE INTO LL_LENGTHs (bdaddr, bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) VALUES (%s, %s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)


# This can be used for LL_PHY_REQ, LL_PHY_RSP since they're all going into the same table
def import_LL_PHYs(bdaddr, random, ll_entry, entry):
    direction = ll_entry["direction"]
    opcode = ll_entry["opcode"]
    if(direction == type_BTIDES_direction_C2P):
        # We can't do like with LL_PINGs, in that even if we can infer the existence of an un-seen P2C REQ
        # we can't create it, because we don't know what the RX/TX values were set to
        # TODO: For now skip the LL_PHY_REQ/RSP *our* Central sends to the Peripheral.
        # TODO: But ideally in the future we need to detect if the packet came
        # TODO: from *our* Central (hardcode its BDADDR?), or one which we just happen to have overhead by chance with Sniffle.
        # TODO: Because in the case of devices other than our own, we would want to capture the fact that a Central naturally sends pings
        return
    tx_phys = ll_entry["TX_PHYS"]
    rx_phys = ll_entry["RX_PHYS"]
    values = (bdaddr, random, opcode, direction, tx_phys, rx_phys)
    insert = f"INSERT IGNORE INTO LL_PHYs (bdaddr, bdaddr_random, opcode, direction, tx_phys, rx_phys) VALUES (%s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)


def has_known_LL_packet(opcode, ll_entry):
    if("opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode):
        return True
    else:
        return False


def parse_LLArray(entry):
    if("LLArray" not in entry.keys() or entry["LLArray"] == None):
        return # Entry not valid for this type

    for ll_entry in entry["LLArray"]:
        # TODO: this is a bit inefficient, but this is OK until we have a proper CONNECT_IND-aware database schema
        if("direction" in ll_entry.keys() and ll_entry["direction"] == type_BTIDES_direction_C2P):
            bdaddr, bdaddr_rand = get_bdaddr_central(entry)
        else:
            bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

        if(has_known_LL_packet(type_LL_UNKNOWN_RSP, ll_entry)):
            import_LL_UNKNOWN_RSP(bdaddr, bdaddr_rand, ll_entry)
        if(has_known_LL_packet(type_LL_VERSION_IND, ll_entry)):
            import_LL_VERSION_IND(bdaddr, bdaddr_rand, ll_entry)
        if(has_known_LL_packet(type_LL_FEATURE_REQ, ll_entry) or
            has_known_LL_packet(type_LL_FEATURE_RSP, ll_entry) or
            has_known_LL_packet(type_LL_PERIPHERAL_FEATURE_REQ, ll_entry)):
                import_LL_FEATUREs(bdaddr, bdaddr_rand, ll_entry)
        if(has_known_LL_packet(type_LL_PING_RSP, ll_entry) or has_known_LL_packet(type_LL_PING_REQ, ll_entry)):
            import_LL_PINGs(bdaddr, bdaddr_rand, ll_entry, entry)
        if(has_known_LL_packet(type_LL_LENGTH_REQ, ll_entry) or has_known_LL_packet(type_LL_LENGTH_RSP, ll_entry)):
            import_LL_LENGTHs(bdaddr, bdaddr_rand, ll_entry)
        if(has_known_LL_packet(type_LL_PHY_REQ, ll_entry) or has_known_LL_packet(type_LL_PHY_RSP, ll_entry)):
            import_LL_PHYs(bdaddr, bdaddr_rand, ll_entry, entry)

###################################
# BTIDES_LMP.json information
###################################

def import_LMP_VERSION_RES(bdaddr, lmp_entry):
    lmp_version = lmp_entry["version"]
    device_BT_CID = lmp_entry["company_id"]
    lmp_sub_version = lmp_entry["subversion"]
    values = (bdaddr, lmp_version, device_BT_CID, lmp_sub_version)
    insert = f"INSERT IGNORE INTO LMP_VERSION_RES (bdaddr, lmp_version, device_BT_CID, lmp_sub_version) VALUES (%s, %s, %s, %s);"
    execute_insert(insert, values)


def import_LMP_FEATURES_RES(bdaddr, lmp_entry):
    features = int(lmp_entry["lmp_features_hex_str"], 16)
    values = (bdaddr, 0, features)
    insert = f"INSERT IGNORE INTO LMP_FEATURES_RES (bdaddr, page, features) VALUES (%s, %s, %s);"
    execute_insert(insert, values)


def import_LMP_FEATURES_RES_EXT(bdaddr, lmp_entry):
    features = int(lmp_entry["lmp_features_hex_str"], 16)
    page = lmp_entry["page"]
    max_page = lmp_entry["max_page"]
    values = (bdaddr, page, max_page, features)
    insert = f"INSERT IGNORE INTO LMP_FEATURES_RES_EXT (bdaddr, page, max_page, features) VALUES (%s, %s, %s, %s);"
    execute_insert(insert, values)


def has_known_LMP_packet(opcode, lmp_entry, extended_opcode=None):
    if("opcode" in lmp_entry.keys() and lmp_entry["opcode"] == opcode):
        if(extended_opcode):
            if("extended_opcode" in lmp_entry.keys() and lmp_entry["extended_opcode"] == extended_opcode):
                return True
            else:
                return False
        else:
            return True
    else:
        return False


def parse_LMPArray(entry):
    if("LMPArray" not in entry.keys() or entry["LMPArray"] == None or entry["bdaddr_rand"] != 0):
        return # Entry not valid for this type

    bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)
    for lmp_entry in entry["LMPArray"]:
        if(has_known_LMP_packet(type_LMP_VERSION_RES, lmp_entry)):
            import_LMP_VERSION_RES(bdaddr, lmp_entry)
            continue
        if(has_known_LMP_packet(type_LMP_FEATURES_RES, lmp_entry)):
            import_LMP_FEATURES_RES(bdaddr, lmp_entry)
            continue
        if(has_known_LMP_packet(type_LMP_FEATURES_RES_EXT, lmp_entry, extended_opcode=type_extended_opcode_LMP_FEATURES_RES_EXT)):
            import_LMP_FEATURES_RES_EXT(bdaddr, lmp_entry)

###################################
# BTIDES_HCI.json information
###################################

def import_HCI_Remote_Name_Request_Complete(bdaddr, hci_entry):
    device_name = hci_entry["remote_name_hex_str"]
    values = (bdaddr, device_name)
    insert = f"INSERT IGNORE INTO HCI_bdaddr_to_name (bdaddr, status, name_hex_str) VALUES (%s, 0, %s);"
    execute_insert(insert, values)


def has_known_HCI_entry(event_code, hci_entry):
    if("event_code" in hci_entry.keys() and hci_entry["event_code"] == event_code):
        return True
    else:
        return False


def parse_HCIArray(entry):
    if("HCIArray" not in entry.keys() or entry["HCIArray"] == None):
        return # Entry not valid for this type

    bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)
    for hci_entry in entry["HCIArray"]:
        if(has_known_HCI_entry(event_code_HCI_Remote_Name_Request_Complete, hci_entry)):
            import_HCI_Remote_Name_Request_Complete(bdaddr, hci_entry)


###################################
# BTIDES_L2CAP.json information
###################################

def import_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(bdaddr, bdaddr_random, l2cap_entry):
    direction = l2cap_entry["direction"]
    code = l2cap_entry["code"]
    pkt_id = l2cap_entry["id"]
    data_len = l2cap_entry["data_len"]
    interval_min = l2cap_entry["interval_min"]
    interval_max = l2cap_entry["interval_max"]
    latency = l2cap_entry["latency"]
    timeout = l2cap_entry["timeout"]
    values = (bdaddr, bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout)
    insert = f"INSERT IGNORE INTO L2CAP_CONNECTION_PARAMETER_UPDATE_REQ (bdaddr, bdaddr_random, direction, code, pkt_id, data_len, interval_min, interval_max, latency, timeout) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)


def import_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(bdaddr, bdaddr_random, l2cap_entry):
    direction = l2cap_entry["direction"]
    code = l2cap_entry["code"]
    id = l2cap_entry["id"]
    data_len = l2cap_entry["data_len"]
    result = l2cap_entry["result"]
    values = (bdaddr, bdaddr_random, direction, code, id, data_len, result)
    insert = f"INSERT IGNORE INTO L2CAP_CONNECTION_PARAMETER_UPDATE_RSP (bdaddr, bdaddr_random, direction, code, id, data_len, result) VALUES (%s, %s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)


def parse_L2CAPArray(entry):
    if("L2CAPArray" not in entry.keys() or entry["L2CAPArray"] == None):
        return # Entry not valid for this type

    for l2cap_entry in entry["L2CAPArray"]:
        # TODO: this is a bit inefficient, but this is OK until we have a proper CONNECT_IND-aware database schema
        if("direction" in l2cap_entry.keys() and l2cap_entry["direction"] == type_BTIDES_direction_C2P):
            bdaddr, bdaddr_rand = get_bdaddr_central(entry)
        else:
            bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

        if(bdaddr == "00:00:00:00:00:00"):
            # Skip placeholder entries for now which are due to not fully parsing HCI connections to capture initiator BDADDR
            continue

        if("code" in l2cap_entry.keys() and l2cap_entry["code"] in l2cap_code_strings.keys()):
            if(l2cap_entry["code"] == type_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ):
                import_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(bdaddr, bdaddr_rand, l2cap_entry)
            elif(l2cap_entry["code"] == type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP):
                import_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(bdaddr, bdaddr_rand, l2cap_entry)


###################################
# BTIDES_EIR.json information
###################################

def import_Page_Scan_Repetition_Mode(bdaddr, eir_entry):
    page_scan_repetition_mode = eir_entry["page_scan_repetition_mode"]
    values = (bdaddr, page_scan_repetition_mode)
    insert = f"INSERT IGNORE INTO EIR_bdaddr_to_PSRM (bdaddr, page_scan_rep_mode) VALUES (%s, %s);"
    execute_insert(insert, values)


def import_Class_of_Device(bdaddr, eir_entry):
    class_of_device = int(eir_entry["CoD_hex_str"], 16)
    values = (bdaddr, class_of_device)
    insert = f"INSERT IGNORE INTO EIR_bdaddr_to_CoD (bdaddr, class_of_device) VALUES (%s, %s);"
    execute_insert(insert, values)


def has_known_EIR_entry(type, eir_entry):
    if("type" in eir_entry.keys() and eir_entry["type"] == type):
        return True
    else:
        return False


def parse_EIRArray(entry):
    if("EIRArray" not in entry.keys() or entry["EIRArray"] == None):
        return # Entry not valid for this type

    bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)
    for eir_entry in entry["EIRArray"]:
        if(has_known_EIR_entry(type_BTIDES_EIR_PSRM, eir_entry)):
            import_Page_Scan_Repetition_Mode(bdaddr, eir_entry)
            continue
        if(has_known_EIR_entry(type_BTIDES_EIR_CoD, eir_entry)):
            import_Class_of_Device(bdaddr, eir_entry)


###################################
# BTIDES_ATT.json information
###################################

def import_ATT_handle_entry(bdaddr, bdaddr_random, att_handle_entry):
    attribute_handle = att_handle_entry["handle"]
    UUID = convert_UUID128_to_UUID16_if_possible(att_handle_entry["UUID"])
    values = (bdaddr, bdaddr_random, attribute_handle, UUID)
    insert = f"INSERT IGNORE INTO GATT_attribute_handles (bdaddr, bdaddr_random, attribute_handle, UUID) VALUES (%s, %s, %s, %s);"
    execute_insert(insert, values)

def import_ATT_handle_enumeration(bdaddr, bdaddr_random, att_entry):
    for att_handle_entry in att_entry["ATT_handle_enumeration"]:
        import_ATT_handle_entry(bdaddr, bdaddr_random, att_handle_entry)

# We have to be stateful with ATT_READ_REQ/RSP because the RSP doesn't contain the handle that was read from
g_last_read_req_handle = 0
g_handle_to_UUID_map = {}

def import_ATT_packet(bdaddr, bdaddr_random, att_entry):
    global g_last_read_req_handle

    #operation = type_BTIDES_ATT_Read # TODO: once we handle other forms of ATT packets besides read, update the operation lower in the code
    if(att_entry["opcode"] == type_ATT_FIND_INFORMATION_RSP):
        operation = type_ATT_FIND_INFORMATION_RSP
        # Fill in all the UUIDs for the handles we've seen so far
        for info_entry in att_entry["information_data"]:
            g_handle_to_UUID_map[info_entry["handle"]] = info_entry["UUID"]
    elif(att_entry["opcode"] == type_ATT_READ_REQ):
        g_last_read_req_handle = att_entry["handle"]
        operation = type_ATT_READ_REQ
    elif(att_entry["opcode"] == type_ATT_READ_RSP):
        handle = g_last_read_req_handle
        operation = type_ATT_READ_RSP

        # Apparently despite being defined as an integer in the schema, the handle can be a string in the JSON and it still passes validation.
        # So we need to make sure it's an integer before it goes into the DB otherwise it can turn into a handle of 0 by the execute_insert function.
        if isinstance(handle, str):
            handle = int(handle, 16)
            if(handle == 0):
                print("Error: char_value_handle was 0. This is a bug. (Possibly JSON validation isn't working) Exiting.")
                exit(-1)
        byte_values = bytes.fromhex(att_entry["value_hex_str"])
        # Now check if the handle in question was a characteristic UUID (0x2803), and if so, interpret the raw data and insert into db
        if(handle in g_handle_to_UUID_map.keys() and g_handle_to_UUID_map[handle] == "2803"):
            declaration_handle = handle
            char_properties = int(byte_values[0])
            char_value_handle = int.from_bytes(byte_values[1:3], byteorder='little')
            if(len(byte_values[3:]) == 2):
                UUID = f"{int.from_bytes(byte_values[3:], byteorder='little'):04x}"
            else:
                UUID = f"{int.from_bytes(byte_values[3:], byteorder='little'):032x}"
                UUID = convert_UUID128_to_UUID16_if_possible(UUID) # Just in case they sent us a 16 bit UUID as a 128 bit UUID for some dumb reason...
            values = (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID)
            insert = f"INSERT IGNORE INTO GATT_characteristics (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID) VALUES (%s, %s, %s, %s, %s, %s);"
            execute_insert(insert, values)
        else:
            # We don't want characteristics to go into the GATT_characteristics_values table
            values = (bdaddr, bdaddr_random, handle, operation, byte_values)
            insert = f"INSERT IGNORE INTO GATT_characteristics_values (bdaddr, bdaddr_random, char_value_handle, operation, byte_values) VALUES (%s, %s, %s, %s, %s);"
            execute_insert(insert, values)


def parse_ATTArray(entry):
    if("ATTArray" not in entry.keys() or entry["ATTArray"] == None):
        return # Entry not valid for this type

    for att_entry in entry["ATTArray"]:
        # TODO: this is a bit inefficient, but this is OK until we have a proper CONNECT_IND-aware database schema
        if("direction" in att_entry.keys() and att_entry["direction"] == type_BTIDES_direction_C2P):
            bdaddr, bdaddr_rand = get_bdaddr_central(entry)
        else:
            bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

        if(bdaddr == "00:00:00:00:00:00"):
            # Skip placeholder entries for now which are due to not fully parsing HCI connections to capture initiator BDADDR
            continue

        if("ATT_handle_enumeration" in att_entry.keys() and att_entry["ATT_handle_enumeration"] != None):
            import_ATT_handle_enumeration(bdaddr, bdaddr_rand, att_entry)
        if("opcode" in att_entry.keys() and att_entry["opcode"] in att_opcode_strings.keys()):
            import_ATT_packet(bdaddr, bdaddr_rand, att_entry)


###################################
# BTIDES_GATT.json information
###################################

def import_GATT_service_entry(bdaddr, bdaddr_random, gatt_service_entry):

    # Skip inserting the service itself if it's designated a placeholder
    if("placeholder_entry" not in gatt_service_entry.keys()):
        if(gatt_service_entry["utype"] == "2800"):
            service_type = 0
        elif(gatt_service_entry["utype"] == "2801"):
            service_type = 1
        else:
            print("It shouldn't be possible to get here, due to schema validation. Code needs to be debugged. Exiting.")
            exit(-1)
        begin_handle = gatt_service_entry["begin_handle"]
        end_handle = gatt_service_entry["end_handle"]
        UUID = convert_UUID128_to_UUID16_if_possible(gatt_service_entry["UUID"])
        values = (bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID)
        insert = f"INSERT IGNORE INTO GATT_services (bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID) VALUES (%s, %s, %s, %s, %s, %s);"
        execute_insert(insert, values)

    # Now insert any characteristics
    if("characteristics" in gatt_service_entry.keys()):
        char_array = gatt_service_entry["characteristics"]
        for char in char_array:
            # Skip inserting the characteristic itself if it's designated a placeholder
            if("placeholder_entry" not in char.keys()):
                declaration_handle = char["handle"]
                char_properties = char["properties"]
                char_value_handle = char["value_handle"]
                UUID = convert_UUID128_to_UUID16_if_possible(char["value_uuid"])
                values = (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID)
                insert = f"INSERT IGNORE INTO GATT_characteristics (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID) VALUES (%s, %s, %s, %s, %s, %s);"
                execute_insert(insert, values)

            # Now insert any characteristic values
            if("char_value" in char.keys()):
                char_value = char["char_value"]
                if("io_array" in char_value.keys()):
                    for io_array_entry in char_value["io_array"]:
                        operation = io_array_entry["io_type"]
                        byte_values = bytes.fromhex(io_array_entry["value_hex_str"])
                        # Apparently despite being defined as an integer in the schema, the handle can be a string in the JSON and it still passes validation.
                        # So we need to make sure it's an integer before it goes into the DB otherwise it can turn into a handle of 0 by the execute_insert function.
                        handle = char_value["handle"]
                        if isinstance(handle, str):
                            handle = int(handle, 16)
                            if(handle == 0):
                                print("Error: char_value_handle was 0. This is a bug. (Possibly JSON validation isn't working) Exiting.")
                                exit(-1)
                        values = (bdaddr, bdaddr_random, handle, operation, byte_values)
                        insert = f"INSERT IGNORE INTO GATT_characteristics_values (bdaddr, bdaddr_random, char_value_handle, operation, byte_values) VALUES (%s, %s, %s, %s, %s);"
                        execute_insert(insert, values)

            # Now convert any characteristic descriptors into values appropriate for storage in the GATT_characteristics_values table
            # TODO: do I need to add an io_array to every descriptor entry, to support operation types other than read?
            if("descriptors" in char.keys()):
                descriptors_array = char["descriptors"]
                for descriptor in descriptors_array:
                    UUID = descriptor["UUID"]
                    handle = descriptor["handle"]
                    operation = type_ATT_READ_RSP
                    if(UUID == "2900"):
                        byte_values = descriptor["extended_properties"].to_bytes(2, byteorder='little')
                    elif(UUID == "2901"):
                        byte_values = bytes.fromhex(descriptor["user_description_hex_str"])
                        # byte_values = hex_str_to_bytes(descriptor["user_description_hex_str"]) # FIXME: I want to use hex_str_to_bytes but encountering circular import issues
                    elif(UUID == "2902" or UUID == "2903"):
                        byte_values = descriptor["config_bits"].to_bytes(2, byteorder='little')
                    elif(UUID == "2904"):
                        byte_values = descriptor["format"].to_bytes(1, byteorder='little')
                        byte_values += descriptor["exponent"].to_bytes(1, byteorder='little')
                        byte_values += descriptor["unit"].to_bytes(2, byteorder='little')
                        byte_values += descriptor["name_space"].to_bytes(1, byteorder='little')
                        byte_values += descriptor["description"].to_bytes(2, byteorder='little')
                    elif(UUID == "2905"):
                        attribute_handles_list = descriptor["attribute_handles_list"]
                        byte_values = b''
                        for handle in attribute_handles_list:
                            byte_values += handle.to_bytes(2, byteorder='little')

                    values = (bdaddr, bdaddr_random, UUID, handle, operation, byte_values)
                    insert = f"INSERT IGNORE INTO GATT_characteristic_descriptor_values (bdaddr, bdaddr_random, UUID, descriptor_handle, operation, byte_values) VALUES (%s, %s, %s, %s, %s, %s);"
                    execute_insert(insert, values)

def parse_GATTArray(entry):
    #qprint(json.dumps(entry, indent=2))
    if("GATTArray" not in entry.keys() or entry["GATTArray"] == None):
        return # Entry not valid for this type

    bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

    for gatt_service_entry in entry["GATTArray"]:
        import_GATT_service_entry(bdaddr, bdaddr_rand, gatt_service_entry)


###################################
# BTIDES_SMP.json information
###################################

def import_SMP_Pairing_Req_Res(bdaddr, bdaddr_random, smp_entry):
    opcode = smp_entry["opcode"]
    io_cap = smp_entry["io_cap"]
    oob_data = smp_entry["oob_data"]
    auth_req = smp_entry["auth_req"]
    max_key_size = smp_entry["max_key_size"]
    initiator_key_dist = smp_entry["initiator_key_dist"]
    responder_key_dist = smp_entry["responder_key_dist"]
    values = (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist)
    insert = f"INSERT IGNORE INTO SMP_Pairing_Req_Res (bdaddr, bdaddr_random, opcode, io_cap, oob_data, auth_req, max_key_size, initiator_key_dist, responder_key_dist) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)

def parse_SMPArray(entry):
    if("SMPArray" not in entry.keys() or entry["SMPArray"] == None):
        return # Entry not valid for this type

    for smp_entry in entry["SMPArray"]:
        # TODO: this is a bit inefficient, but this is OK until we have a proper CONNECT_IND-aware database schema
        if("direction" in smp_entry.keys() and smp_entry["direction"] == type_BTIDES_direction_C2P):
            bdaddr, bdaddr_rand = get_bdaddr_central(entry)
        else:
            bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

        if(bdaddr == "00:00:00:00:00:00"):
            # Skip placeholder entries for now which are due to not fully parsing HCI connections to capture initiator BDADDR
            continue

        if("opcode" in smp_entry.keys() and smp_entry["opcode"] in smp_opcode_strings.keys()):
            if(smp_entry["opcode"] == type_SMP_Pairing_Request):
                import_SMP_Pairing_Req_Res(bdaddr, bdaddr_rand, smp_entry)
            elif(smp_entry["opcode"] == type_SMP_Pairing_Response):
                import_SMP_Pairing_Req_Res(bdaddr, bdaddr_rand, smp_entry)


###################################
# BTIDES_SDP.json information
###################################

def import_SDP_ERROR_RSP(bdaddr, sdp_entry):
    l2cap_len = sdp_entry["l2cap_len"]
    l2cap_cid = sdp_entry["l2cap_cid"]
    direction = sdp_entry["direction"]
    transaction_id = sdp_entry["transaction_id"]
    param_len = sdp_entry["param_len"]
    error_code = sdp_entry["error_code"]
    values = (bdaddr, direction, l2cap_len, l2cap_cid, transaction_id, param_len, error_code)
    insert = f"INSERT IGNORE INTO SDP_ERROR_RSP (bdaddr, direction, l2cap_len, l2cap_cid, transaction_id, param_len, error_code) VALUES (%s, %s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)


def import_SDP_Common(bdaddr, sdp_entry):
    l2cap_len = sdp_entry["l2cap_len"]
    l2cap_cid = sdp_entry["l2cap_cid"]
    direction = sdp_entry["direction"]
    pdu_id = sdp_entry["pdu_id"]
    transaction_id = sdp_entry["transaction_id"]
    param_len = sdp_entry["param_len"]
    byte_values = bytes.fromhex(sdp_entry["raw_data_hex_str"])
    values = (bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values)
    insert = f"INSERT IGNORE INTO SDP_Common (bdaddr, direction, l2cap_len, l2cap_cid, pdu_id, transaction_id, param_len, byte_values) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);"
    execute_insert(insert, values)


def parse_SDPArray(entry):
    if("SDPArray" not in entry.keys() or entry["SDPArray"] == None):
        return # Entry not valid for this type

    for sdp_entry in entry["SDPArray"]:
        # TODO: this is a bit inefficient, but this is OK until we have a proper CONNECT_IND-aware database schema
        if("direction" in sdp_entry.keys() and sdp_entry["direction"] == type_BTIDES_direction_C2P):
            bdaddr, bdaddr_rand = get_bdaddr_central(entry)
        else:
            bdaddr, bdaddr_rand = get_bdaddr_peripheral(entry)

        if(bdaddr == "00:00:00:00:00:00"):
            # Skip placeholder entries for now which are due to not fully parsing HCI connections to capture initiator BDADDR
            continue

        if("pdu_id" in sdp_entry.keys() and sdp_entry["pdu_id"] in sdp_pdu_strings.keys()):
            if(sdp_entry["pdu_id"] == type_SDP_ERROR_RSP):
                import_SDP_ERROR_RSP(bdaddr, sdp_entry)
            else:
                import_SDP_Common(bdaddr, sdp_entry)

###################################

class btides_to_sql_args:
    def __init__(self, input=None, skip_invalid=True, verbose_print=False, quiet_print=True, use_test_db=True):
        self.input = input
        self.skip_invalid = skip_invalid
        self.verbose_print = verbose_print
        self.quiet_print = quiet_print
        self.use_test_db = use_test_db

    def set_input(self, input):
        self.input = input

    def set_skip_invalid(self, skip_invalid):
        self.skip_invalid = skip_invalid

    def set_verbose_print(self, verbose_print):
        self.verbose_print = verbose_print

    def set_quiet_print(self, quiet_print):
        self.quiet_print = quiet_print

    def set_use_test_db(self, use_test_db):
        self.use_test_db = use_test_db


# Input must be a Namespace like args from argparse
def btides_to_sql(args):
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.use_test_db = args.use_test_db
    in_filename = args.input
    skip_invalid = args.skip_invalid
    global last_printed_percentage
    global BTIDES_JSON

    last_printed_percentage = 0
    with open(in_filename, 'r') as f:
        TME.TME_glob.BTIDES_JSON = json.load(f) # We have to just trust that this JSON parser doesn't have any issues...
        #qprint(json.dumps(BTIDES_JSON, indent=2))

    # Import all the local BTIDES json schema files, so that we don't hit the website all the time
    all_schemas = []
    for file in BTIDES_files:
        with open(f"./BTIDES_Schema/{file}", 'r') as f:
            #BTIDES_Schema
            s = json.load(f)
            #qprint(s["$id"])
            schema = Resource.from_contents(s)
            all_schemas.append((s["$id"], schema))

    registry = Registry().with_resources( all_schemas )

    total = len(TME.TME_glob.BTIDES_JSON)
    count = 0;
    for entry in TME.TME_glob.BTIDES_JSON:
        # Sanity check every entry against the Schema's SingleBDADDR (this way we don't have to validate all up front)
        try:
            Draft202012Validator(
                {"anyOf": [
                    {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json#/definitions/SingleBDADDR"},
                    {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json#/definitions/DualBDADDR"}
                ]},
                registry=registry,
            ).validate(instance=entry)
            #qprint("JSON is valid according to BTIDES Schema")
        except ValidationError as e:
            qprint("JSON data is invalid per BTIDES Schema:", e.message)
            if(skip_invalid):
                continue
            else:
                qprint(json.dumps(entry, indent=2))
                #return False
                exit(-1)

        parse_AdvChanArray(entry)

        parse_LLArray(entry)

        parse_LMPArray(entry)

        parse_HCIArray(entry)

        parse_L2CAPArray(entry)

        parse_ATTArray(entry)

        parse_GATTArray(entry)

        parse_SMPArray(entry)

        parse_EIRArray(entry)

        parse_SDPArray(entry)

        count += 1
        progress_update(total, count)

    qprint(f"New db records inserted:\t\t{TME.TME_glob.insert_count}")
    qprint(f"Duplicate db records ignored:\t{TME.TME_glob.duplicate_count}")
    return True

###################################
# MAIN
###################################

last_printed_percentage = 0
def progress_update(total, count):
    global last_printed_percentage
    percent_complete = int((count / total) * 100)
    if(percent_complete > last_printed_percentage):
        qprint(f"{percent_complete}% done")
        last_printed_percentage = percent_complete

######################################################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
######################################################
# THIS IS YOUR REMINDER THAT THE BTIDES INPUT FILE IS ENTIRELY
# ACID (Attacker-Controlled Input Data)!
# SANITY CHECK THE HELL OUT OF EVERY FIELD BEFORE USE!
# OTHERWISE YOU WILL HAVE SQL INJECTION VULNS (AT A MINIMUM)!

def main():
    global verbose_print, use_test_db, duplicate_count, insert_count

    parser = argparse.ArgumentParser(description='Input BTIDES files to MySQL tables.')
    parser.add_argument('--input', type=str, required=True, help='Input file name for BTIDES JSON file.')
    parser.add_argument('--skip-invalid', action='store_true', required=False, help='Skip any data that fails to validate via the schema, rather than just terminating.')
    parser.add_argument('--rename', action='store_true', required=False, help='Rename the input file to add \'.processed.\' suffix')
    parser.add_argument('--verbose-print', action='store_true', required=False, help='Print verbose output.')
    parser.add_argument('--quiet-print', action='store_true', required=False, help='Hide all print output.')
    parser.add_argument('--use-test-db', action='store_true', required=False, help='This will query from an alternate database, used for testing.')
    args = parser.parse_args()

    btides_to_sql_succeeded = btides_to_sql(args)
    if(btides_to_sql_succeeded and args.rename):
        os.rename(args.input, args.input + ".processed")

if __name__ == "__main__":
    main()