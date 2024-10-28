########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

# This file is to import data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html
# into the Blue2thprinting MySQL database

######################################################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
######################################################
# THIS IS YOUR REMINDER THAT THE BTIDES INPUT FILE IS ENTIRELY ACID!
# SANITY CHECK THE HELL OUT OF EVERY FIELD BEFORE USE!
# OTHERWISE YOU WILL HAVE SQL INJECTION VULNS (AT A MINIMUM)!

import argparse
import json
import mysql.connector

from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from _ast import Or

###################################
# Globals
###################################

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


# Global is only accessible within this file
BTIDES_JSON = []

insert_count = 0

###################################
# Helper functions
###################################

# Function to execute a MySQL query and fetch results
def execute_query(query):
    connection = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database='bt',
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password'
    )

    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    cursor.close()
    connection.close()
    return result

# Function to execute a MySQL query and fetch results
def execute_insert(query):
    global insert_count
    connection = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database='bt',
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password'
    )

    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        insert_count += 1
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

###################################
# BTIDES_AdvData.json information
###################################

def BTIDES_types_to_le_evt_type(type):
    # FIXME!: In the future once I update to have a src file type field (or foreign key pointer to row with that field)
    # I will need to 
    # For now I will just use the pcap PDU values, since they correspond 1:1 to BTIDES for the first 4 entries
    if(type >= 0 and type <= 3): return type
    if(type == 10): return 7 # AUX_ADV_IND
    if(type == 20): return 6 # SCAN_RSP # From accidental incorrect pcap mix-in
    if(type == 21): return 7 # AUX_SCAN_RSP # FIXME: I don't yet know what value this should take on

    # From manually inserting EIR type
    if(type == 50): return 50 # EIR

def import_AdvData_Flags(bdaddr, random, db_type, leaf):
    #print("import_AdvData_Flags!")
    
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
    
    if(db_type == 50):
        # EIR
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_flags2 (device_bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) VALUES ('{bdaddr}', {le_limited_discoverable_mode}, {le_general_discoverable_mode}, {bredr_not_supported}, {le_bredr_support_controller}, {le_bredr_support_host}); "
        #print(eir_insert)
        execute_insert(eir_insert)
    else:
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_flags2 (device_bdaddr, bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) VALUES ('{bdaddr}', {random}, {db_type}, {le_limited_discoverable_mode}, {le_general_discoverable_mode}, {bredr_not_supported}, {le_bredr_support_controller}, {le_bredr_support_host}); "
        #print(le_insert)
        execute_insert(le_insert)

def import_AdvData_TxPower(bdaddr, random, db_type, leaf):
    #print("import_AdvData_TxPower!")

    device_tx_power = leaf["tx_power"]

    if(db_type == 50):
        # EIR
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_tx_power (device_bdaddr, device_tx_power) VALUES ('{bdaddr}', {device_tx_power}); "
        ###print(eir_insert)
        execute_insert(eir_insert)
    else:
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_tx_power (device_bdaddr, bdaddr_random, le_evt_type, device_tx_power) VALUES ('{bdaddr}', {random}, {db_type}, {device_tx_power}); "
        ###print(le_insert)
        execute_insert(le_insert)

def import_AdvData_MSD(bdaddr, random, db_type, leaf):
    #print("import_AdvData_MSD!")

    device_BT_CID = int(leaf["company_id_hex_str"], 16)
    manufacturer_specific_data = leaf["msd_hex_str"]

    if(db_type == 50):
        # EIR
        eir_insert = f"INSERT IGNORE INTO EIR_bdaddr_to_MSD (device_bdaddr, device_BT_CID, manufacturer_specific_data) VALUES ('{bdaddr}', {device_BT_CID}, '{manufacturer_specific_data}'); "
        ###print(eir_insert)
        execute_insert(eir_insert)
    else:
        le_insert = f"INSERT IGNORE INTO LE_bdaddr_to_MSD (device_bdaddr, bdaddr_random, le_evt_type, device_BT_CID, manufacturer_specific_data) VALUES ('{bdaddr}', {random}, {db_type}, {device_BT_CID}, '{manufacturer_specific_data}'); "
        ###print(le_insert)
        execute_insert(le_insert)

def has_AdvDataArray(entry):
    if(entry != None and entry["AdvDataArray"] != None):
        return True
    else:
        return False

type_AdvData_Flags          = 1
type_AdvData_TxPower        = 10
type_AdvData_MSD            = 255
def has_known_AdvData_type(type, entry):
    if(entry != None and "type" in entry.keys() and entry["type"] == type):
        return True
    else:
        return False

def parse_AdvChanArray(entry):
    ###print(json.dumps(entry, indent=2))
    for AdvChanEntry in entry["AdvChanArray"]:
        if(has_AdvDataArray(AdvChanEntry)):
            for AdvData in AdvChanEntry["AdvDataArray"]:
                if(has_known_AdvData_type(type_AdvData_Flags, AdvData)):
                    import_AdvData_Flags(entry["bdaddr"], entry["bdaddr_rand"], BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                if(has_known_AdvData_type(type_AdvData_TxPower, AdvData)):
                    import_AdvData_TxPower(entry["bdaddr"], entry["bdaddr_rand"], BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
                if(has_known_AdvData_type(type_AdvData_MSD, AdvData)):
                    import_AdvData_MSD(entry["bdaddr"], entry["bdaddr_rand"], BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)

def has_AdvChanArray(entry):
    if("AdvChanArray" in entry.keys() and entry["AdvChanArray"] != None and entry["bdaddr"] != None and entry["bdaddr_rand"] != None):
        return True
    else:
        return False

###################################
# BTIDES_LL.json information
###################################

opcode_LL_UNKNOWN_RSP               = 7
opcode_LL_FEATURE_REQ               = 8
opcode_LL_FEATURE_RSP               = 9
opcode_LL_VERSION_IND               = 12
opcode_LL_PERIPHERAL_FEATURE_REQ    = 14

def import_LL_UNKNOWN_RSP(bdaddr, random, ll_entry):
    unknown_opcode = ll_entry["unknown_type"]
    insert = f"INSERT IGNORE INTO BLE2th_LL_UNKNOWN_RSP (device_bdaddr_type, device_bdaddr, unknown_opcode) VALUES ( {random}, '{bdaddr}', {unknown_opcode});"
    #print(insert)
    execute_insert(insert)

def import_LL_VERSION_IND(bdaddr, random, ll_entry):
    ll_version = ll_entry["version"]
    device_BT_CID = ll_entry["company_id"]
    ll_sub_version = ll_entry["subversion"]
    insert = f"INSERT IGNORE INTO BLE2th_LL_VERSION_IND (device_bdaddr_type, device_bdaddr, ll_version, device_BT_CID, ll_sub_version) VALUES ( {random}, '{bdaddr}', {ll_version}, {device_BT_CID}, {ll_sub_version});"
    #print(insert)
    execute_insert(insert)

# This can be used for LL_FEATURE_REQ, LL_FEATURE_RSP, and LL_PERIPHERAL_FEATURE_REQ, since they're all going into the same table
def import_LL_FEATUREs(bdaddr, random, ll_entry):
    opcode = ll_entry["opcode"]
    features = int(ll_entry["le_features_hex_str"], 16)
    insert = f"INSERT IGNORE INTO BLE2th_LL_FEATUREs (device_bdaddr_type, device_bdaddr, opcode, features) VALUES ( {random}, '{bdaddr}', {opcode}, {features});"
    #print(insert)
    execute_insert(insert)

def has_known_LL_packet(opcode, ll_entry):
    if("opcode" in ll_entry.keys() and ll_entry["opcode"] == opcode):
        return True
    else:
        return False

def parse_LLArray(entry):
    ###print(json.dumps(entry, indent=2))
    for ll_entry in entry["LLArray"]:
        if(has_known_LL_packet(opcode_LL_UNKNOWN_RSP, ll_entry)):
            import_LL_UNKNOWN_RSP(entry["bdaddr"], entry["bdaddr_rand"], ll_entry)
        if(has_known_LL_packet(opcode_LL_VERSION_IND, ll_entry)):
            import_LL_VERSION_IND(entry["bdaddr"], entry["bdaddr_rand"], ll_entry)
        if(has_known_LL_packet(opcode_LL_FEATURE_REQ, ll_entry) or 
           has_known_LL_packet(opcode_LL_FEATURE_RSP, ll_entry) or 
           has_known_LL_packet(opcode_LL_PERIPHERAL_FEATURE_REQ, ll_entry)):
            import_LL_FEATUREs(entry["bdaddr"], entry["bdaddr_rand"], ll_entry)


def has_LLArray(entry):
    if("LLArray" in entry.keys() and entry["LLArray"] != None and entry["bdaddr"] != None and entry["bdaddr_rand"] != None):
        return True
    else:
        return False

###################################
# BTIDES_LMP.json information
###################################

def import_LMP_VERSION_RSP(bdaddr, lmp_entry):
    lmp_version = lmp_entry["version"]
    device_BT_CID = lmp_entry["company_id"]
    lmp_sub_version = lmp_entry["subversion"]
    insert = f"INSERT IGNORE INTO BTC2th_LMP_version_res (device_bdaddr, lmp_version, device_BT_CID, lmp_sub_version) VALUES ('{bdaddr}', {lmp_version}, {device_BT_CID}, {lmp_sub_version});"
    #print(insert)
    execute_insert(insert)

def import_LMP_FEATURES_RSP(bdaddr, lmp_entry):
    #opcode = lmp_entry["opcode"] # TODO: Update database to include this (and rename BTC2th_LMP_features_res to BTC2th_LMP_FEATURES
    features = int(lmp_entry["lmp_features_hex_str"], 16)
    insert = f"INSERT IGNORE INTO BTC2th_LMP_features_res (device_bdaddr, page, features) VALUES ('{bdaddr}', 0, {features});"
    #print(insert)
    execute_insert(insert)

opcode_LMP_VERSION_RSP          = 38
opcode_LMP_FEATURES_RSP         = 40
def has_known_LMP_packet(opcode, lmp_entry):
    if("opcode" in lmp_entry.keys() and lmp_entry["opcode"] == opcode):
        return True
    else:
        return False

def parse_LMPArray(entry):
    ###print(json.dumps(entry, indent=2))
    for lmp_entry in entry["LMPArray"]:
        if(has_known_LL_packet(opcode_LMP_VERSION_RSP, lmp_entry)):
            import_LMP_VERSION_RSP(entry["bdaddr"], lmp_entry)
        if(has_known_LL_packet(opcode_LMP_FEATURES_RSP, lmp_entry)):
            import_LMP_FEATURES_RSP(entry["bdaddr"], lmp_entry)

def has_LMPArray(entry):
    #print(json.dumps(entry, indent=2))
    if("LMPArray" in entry.keys() and entry["LMPArray"] != None and entry["bdaddr"] != None and entry["bdaddr_rand"] != None and entry["bdaddr_rand"] == 0):
        return True
    else:
        return False

###################################
# BTIDES_HCI.json information
###################################

def import_HCI_Remote_Name_Request_Complete(bdaddr, hci_entry):
    device_name = hci_entry["remote_name"]
    insert = f"INSERT IGNORE INTO BTC2th_LMP_name_res (device_bdaddr, device_name) VALUES ('{bdaddr}', '{device_name}');"
    #print(insert)
    execute_insert(insert)

event_code_HCI_Remote_Name_Request_Complete = 7
def has_known_HCI_entry(event_code, hci_entry):
    if("event_code" in hci_entry.keys() and hci_entry["event_code"] == event_code_HCI_Remote_Name_Request_Complete):
        return True
    else:
        return False

def parse_HCIArray(entry):
    ###print(json.dumps(entry, indent=2))
    for hci_entry in entry["HCIArray"]:
        if(has_known_HCI_entry(event_code_HCI_Remote_Name_Request_Complete, hci_entry)):
            import_HCI_Remote_Name_Request_Complete(entry["bdaddr"], hci_entry)

def has_HCIArray(entry):
    #print(json.dumps(entry, indent=2))
    if("HCIArray" in entry.keys() and entry["HCIArray"] != None and entry["bdaddr"] != None and entry["bdaddr_rand"] != None and entry["bdaddr_rand"] == 0):
        return True
    else:
        return False

###################################
# MAIN
###################################

######################################################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
##################### WARNING!!! #####################
######################################################
# THIS IS YOUR REMINDER THAT THE BTIDES INPUT FILE IS ENTIRELY ACID!
# SANITY CHECK THE HELL OUT OF EVERY FIELD BEFORE USE!
# OTHERWISE YOU WILL HAVE SQL INJECTION VULNS (AT A MINIMUM)!

def main():
    global BTIDES_JSON

    parser = argparse.ArgumentParser(description='Input BTIDES files to MySQL tables.')
    parser.add_argument('--input', type=str, required=True, help='Input file name for BTIDES JSON file.')
    args = parser.parse_args()

    in_filename = args.input
    
    with open(in_filename, 'r') as f:
        BTIDES_JSON = json.load(f) # We have to just trust that this JSON parser doesn't have any issues...
        #print(json.dumps(BTIDES_JSON, indent=2))

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
        print("JSON data is invalid per BTIDES Schema:", e.message)
        exit(-1)

    # If we get here, every entry validates and we can process them all
    for entry in BTIDES_JSON:
        
        if(has_AdvChanArray(entry)):
            parse_AdvChanArray(entry)

        if(has_LLArray(entry)):
            parse_LLArray(entry)

        if(has_LMPArray(entry)):
            parse_LMPArray(entry)

        if(has_HCIArray(entry)):
            parse_HCIArray(entry)

            
    print(f"Inserted {insert_count} records to the database (this counts any that may have been ignored due to being duplicates).")

if __name__ == "__main__":
    main()