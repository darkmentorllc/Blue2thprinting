# This file parses the BLEScope_extractedUUIDs.json file and inserts it into the MySQL database table BLEScope_UUID128s for use later by TellMeEverything.py
# BLEScope_extractedUUIDs.json is the data extracted as part of the research paper 
# "Automatic Fingerprinting of Vulnerable BLE IoT Devices with Static UUIDs from Mobile Apps"
# by Chaoshun Zuo, Haohuang Wen, Zhiqiang Lin, and Yinqian Zhang from Ohio State University
# Thanks to them for providing this data!

import json
import yaml
import mysql.connector

# Dictionaries to store unknown services and characteristics
vendor_specific_services = {}
vendor_specific_characteristics = {}

### BEGIN CODE BORROWED FROM TellMeEverything.py ###

# # Function to execute a MySQL query and fetch results
# def execute_query(query, values):
#     connection = mysql.connector.connect(
#         host='localhost',
#         user='user',
#         password='a',
#         database='bt',
#         auth_plugin='mysql_native_password'
#     )

#     cursor = connection.cursor()
#     cursor.execute(query, values)
#     result = cursor.fetchall()

#     cursor.close()
#     connection.close()
#     return result

# NOTE: The below code assumes that the https://bitbucket.org/bluetooth-SIG/public.git
# repository has been cloned one directory up from this file.
# All paths are written under that assumption

preassigned_GATT_services = {}
preassigned_GATT_declarations = {}
preassigned_GATT_descriptors = {}
preassigned_GATT_characteristics = {}

def create_preassigned_GATT_services():
    global preassigned_GATT_services
    with open('../public/assigned_numbers/uuids/service_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        uuid128 = f"0000{uuid:04x}-0000-1000-8000-00805f9b34fb".lower()
        #name = entry['name']
        preassigned_GATT_services[uuid128] = 1 #name
    #print(f"\n preassigned_GATT_services: \n{preassigned_GATT_services}\n")

def create_preassigned_GATT_declarations():
    global preassigned_GATT_declarations
    with open('../public/assigned_numbers/uuids/declarations.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        uuid128 = f"0000{uuid:04x}-0000-1000-8000-00805f9b34fb".lower()
        #name = entry['name']
        preassigned_GATT_declarations[uuid128] = 1 #name
    #print(f"\n preassigned_GATT_declarations: \n{preassigned_GATT_declarations}\n")

def create_preassigned_GATT_descriptors():
    global preassigned_GATT_descriptors
    with open('../public/assigned_numbers/uuids/descriptors.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        uuid128 = f"0000{uuid:04x}-0000-1000-8000-00805f9b34fb".lower()
        #name = entry['name']
        preassigned_GATT_descriptors[uuid128] = 1 #name
    #print(f"\n preassigned_GATT_descriptors: \n{preassigned_GATT_descriptors}\n")

def create_preassigned_GATT_characteristics():
    global preassigned_GATT_characteristics
    with open('../public/assigned_numbers/uuids/characteristic_uuids.yaml', 'r') as file:
        data = yaml.safe_load(file)

    for entry in data['uuids']:
        uuid = entry['uuid']
        uuid128 = f"0000{uuid:04x}-0000-1000-8000-00805f9b34fb".lower()
        #name = entry['name']
        preassigned_GATT_characteristics[uuid128] = 1 #name
    #print(f"\n preassigned_GATT_characteristics: \n{preassigned_GATT_characteristics}\n")

create_preassigned_GATT_services()
create_preassigned_GATT_declarations()
create_preassigned_GATT_descriptors()
create_preassigned_GATT_characteristics()

### END CODE BORROWED FROM TellMeEverything.py ###

json_file = './BLEScope_extractedUUIDs.json'

# Load JSON data from file
with open(json_file, 'r') as f:
    data = json.load(f)

# Iterate over each entry in the JSON data
for key, value in data.items():
    if(key == "CREDITS"):
        continue
    pkg = value['pkg']
    uuids = value['uuids']
    
    for uuid, details in uuids.items():
        uuid = uuid.lower()
        #define = details['define'][0]
        # Need to loop through all entries under define, because in reality a single entry could look like *both* a service or a characteristic according to the json data
        define_list = details['define']
        for define in define_list:
            if "android.bluetooth.BluetoothGatt: android.bluetooth.BluetoothGattService" in define:
                # We shouldn't have to check declarations or descriptors, but some vendors seem to be using some of those values in error
                if (uuid in preassigned_GATT_services) or (uuid in preassigned_GATT_declarations) or (uuid in preassigned_GATT_descriptors) or (uuid in preassigned_GATT_characteristics):
                    continue
                else:
                    if uuid not in vendor_specific_services:
                        vendor_specific_services[uuid] = {}
                    vendor_specific_services[uuid][pkg] = 1

            elif "android.bluetooth.BluetoothGattService: android.bluetooth.BluetoothGattCharacteristic" in define:
                # We shouldn't have to check declarations or descriptors, but some vendors seem to be using some of those values in error
                if (uuid in preassigned_GATT_characteristics) or (uuid in preassigned_GATT_declarations) or (uuid in preassigned_GATT_descriptors) or (uuid in preassigned_GATT_services):
                    continue
                else:
                    if uuid not in vendor_specific_characteristics:
                        vendor_specific_characteristics[uuid] = {}
                    vendor_specific_characteristics[uuid][pkg] = 2

# By skipping entries like "android.bluetooth.le.ScanFilter$Builder: android.bluetooth.le.ScanFilter$Builder setServiceUuid" I seem to skip the UUID128 services based on member UUID16s
# By skipping entries like "android.bluetooth.BluetoothGattCharacteristic: android.bluetooth.BluetoothGattDescriptor" I seem to skip the well-known GATT descriptors


### Now output the android package names and UUIDs to the db

# Establish connection to the MySQL database
db_connection = mysql.connector.connect(
    host='localhost',
    user='user',
    password='a',
    database='bt',
    auth_plugin='mysql_native_password'
)

# Create a cursor to interact with the database
cursor = db_connection.cursor()

sql_BLEScope_UUID128s = "INSERT IGNORE INTO BLEScope_UUID128s (android_pkg_name, uuid_type, str_UUID128) VALUES (%s, %s, %s)"

# Print results (for testing)
print("Unknown Services:")
for uuid, pkg_dict in vendor_specific_services.items():
    print(uuid + ":")
    for pkg, value in pkg_dict.items():
        print(f"\t{pkg}: {value}")
        values = (pkg, 1, uuid)
        cursor.execute(sql_BLEScope_UUID128s, values)
        db_connection.commit()

print("\nUnknown Characteristics:")
for uuid, pkg_dict in vendor_specific_characteristics.items():
    print(uuid + ":")
    for pkg, value in pkg_dict.items():
        print(f"\t{pkg}: {value}")
        values = (pkg, 2, uuid)
        cursor.execute(sql_BLEScope_UUID128s, values)
        db_connection.commit()

# Close the cursor and database connection
cursor.close()
db_connection.close()
