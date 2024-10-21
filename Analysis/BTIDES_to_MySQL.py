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
#from referencing import Registry, Resource
#import referencing.jsonschema


# Global is only accessible within this file
BTIDES_JSON = []

insert_count = 0

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

def has_AdvDataArray(entry):
    if(entry != None and entry["AdvDataArray"] != None):
        return True
    else:
        return False

def has_TxPower(entry):
    if(entry != None and entry["type"] == 10 and entry["tx_power"] != None and entry["tx_power"] >= -128 and entry["tx_power"] <= 127):
        return True
    else:
        return False

def parse_AdvChanArray(entry):
    ###print(json.dumps(entry, indent=2))
    for AdvChanEntry in entry["AdvChanArray"]:
        if(has_AdvDataArray(AdvChanEntry)):
            for AdvData in AdvChanEntry["AdvDataArray"]:
                if(has_TxPower(AdvData)):
                    import_AdvData_TxPower(entry["bdaddr"], entry["bdaddr_rand"], BTIDES_types_to_le_evt_type(AdvChanEntry["type"]), AdvData)
    

def has_AdvChanArray(entry):
    if(entry["AdvChanArray"] != None and entry["bdaddr"] != None and entry["bdaddr_rand"] != None):
        return True
    else:
        return False

def main():
    global BTIDES_JSON

    parser = argparse.ArgumentParser(description='Input BTIDES files to MySQL tables.')
    parser.add_argument('--input', type=str, required=True, help='Input file name for BTIDES JSON file.')
    args = parser.parse_args()

    in_filename = args.input
    
    with open(in_filename, 'r') as f:
        BTIDES_JSON = json.load(f) # We have to just trust that this JSON parser doesn't have any issues...
        #print(json.dumps(BTIDES_JSON, indent=2))

    with open("BTIDES_base.json", 'r') as f:
        BTIDES_Schema = json.load(f)
        #print(json.dumps(BTIDES_Schema, indent=2))
        
    # I don't want this hitting the website all the time
    #registry = Registry().with_resources( [ ( "./BTIDES_base.json", BTIDES_Schema) ] )

    for entry in BTIDES_JSON:
        # Sanity check every entry against the Schema
        try:
            validate(instance=entry, schema=BTIDES_Schema) #, registry=registry)
            #print("JSON is valid according to BTIDES Schema")
        except ValidationError as e:
            print("JSON data is invalid per BTIDES Schema:", e.message)
            exit(-1)

        if(has_AdvChanArray(entry)):
            parse_AdvChanArray(entry)
            
    print(f"Inserted {insert_count} records to the database.")

if __name__ == "__main__":
    main()