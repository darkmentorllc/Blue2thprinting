#!/usr/local/bin/python3

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

import mysql.connector
import traceback
import csv
import binascii

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

# Prepare the SQL statement with placeholders
#sql_GATT_services = "INSERT IGNORE INTO GATT_services (bdaddr, bdaddr_random, begin_handle, end_handle, UUID128) VALUES (%s, %s, %s, %s, %s)"
# Currently date from gatttool can only capture primary services, so hardcode service_type to 0 (for 0x2800, but to save space. 0x2801 would therefore be 1))
sql_GATT_services2 = "INSERT IGNORE INTO GATT_services2 (bdaddr, bdaddr_random, service_type, begin_handle, end_handle, UUID128) VALUES (%s, %s, 0, %s, %s, %s)"
sql_GATT_attribute_handles = "INSERT IGNORE INTO GATT_attribute_handles (bdaddr, bdaddr_random, attribute_handle, UUID128) VALUES (%s, %s, %s, %s)"
sql_GATT_characteristics = "INSERT IGNORE INTO GATT_characteristics (bdaddr, bdaddr_random, declaration_handle, char_properties, char_value_handle, UUID128) VALUES (%s, %s, %s, %s, %s, %s)"
sql_GATT_characteristics_values = "INSERT IGNORE INTO GATT_characteristics_values (bdaddr, bdaddr_random, read_handle, byte_values) VALUES (%s, %s, %s, %s)"

# Try to find the bdaddr that will be substituted for {}, in any of our BLE tables
sql_lookup_bdaddr_type = """
SELECT bdaddr_random
FROM (
  SELECT bdaddr_random
  FROM LE_bdaddr_to_appearance
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_CoD
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_connect_interval
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_flags
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_MSD
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_name
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_other_le_bdaddr
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_public_target_bdaddr
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_tx_power
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_URI
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID128_service_solicit
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID128_service_data
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID128s_list
  WHERE bdaddr = '{bda}'
UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID32_service_solicit
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID32_service_data
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID32s_list
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID16_service_solicit
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID16_service_data
  WHERE bdaddr = '{bda}'
  UNION ALL
  SELECT bdaddr_random
  FROM LE_bdaddr_to_UUID16s_list
  WHERE bdaddr = '{bda}'
) AS combined_results;
"""

#Use this to convert byte arrays into human-readable strings
def print_string(args):
    try:
        # Split the byte string and convert each value to an integer
        byte_values = [int(byte_str, 16) for byte_str in args]
        # Create a byte array from the list of integer values
        byte_array = bytes(byte_values)
        # Decode the byte array using UTF-8 to obtain a Unicode string
        unicode_string = byte_array.decode("utf-8")
        print("The string is:", unicode_string)
    except UnicodeDecodeError:
        print("Error decoding the string.")
        return -1

# If new = 1, that means it has the new style formatting with the bdaddr_random already embedded
def func_CHARACTERISTIC(bdaddr_random, new, args):
    #print("Called: func_CHARACTERISTIC with args:", args)
    if(new == 0):
        if (len(args) != 5):
            print("args rejected as they were not the correct number of elements:", args)
            return
        bdaddr = args[0]
        try:
            declaration_handle = int(args[1], 16)
            char_properties = int(args[2], 16)
            char_value_handle = int(args[3], 16)
        except Exception as e:
            print("Couldn't convert value to int in func_CHARACTERISTIC 1")
            return

        UUID128 = args[4]
    else:
        if (len(args) != 6):
            print("args rejected as they were not the correct number of elements:", args)
            return
        bdaddr = args[1]
        try:
            declaration_handle = int(args[2], 16)
            char_properties = int(args[3], 16)
            char_value_handle = int(args[4], 16)
        except Exception as e:
            print("Couldn't convert value to int in func_CHARACTERISTIC 2")
            return

        UUID128 = args[5]

    # Define the parameter values to be inserted
    values = (bdaddr_random, bdaddr, declaration_handle, char_properties, char_value_handle, UUID128)
    #print("values = ", values)
    # Execute the SQL statement
    cursor.execute(sql_GATT_characteristics, values)
    # Commit the changes to the database
    db_connection.commit()

# If new = 1, that means it has the new style formatting with the bdaddr_random already embedded
def func_CHAR_VALUE(bdaddr_random, new, args):
#    print("Called: func_CHAR_VALUE with args:", args)
    if(new == 0):
        if (len(args) != 3):
            print("args rejected as they were not the correct number of elements:", args)
            return
        bdaddr = args[0]
        read_handle = int(args[1], 16)
        byte_values = args[2]
    else:
        if (len(args) != 4):
            print("args rejected as they were not the correct number of elements:", args)
            return
        bdaddr = args[1]
        read_handle = int(args[2], 16)
        byte_values = args[3]

    binary_string = binascii.unhexlify(byte_values)
    try:
        ascii_data = binary_string.decode("utf-8")
        print("CHAR_VALUE: byte_values as ascii ==", ascii_data)
    except Exception as e:
#        print("Couldn't decode byte_values")
        pass
    # Define the parameter values to be inserted
    values = (bdaddr_random, bdaddr, read_handle, binary_string)
    #print("values = ", values)
    # Execute the SQL statement
    cursor.execute(sql_GATT_characteristics_values, values)
    # Commit the changes to the database
    db_connection.commit()

# If new = 1, that means it has the new style formatting with the bdaddr_random already embedded
def func_SERVICE(bdaddr_random, new, args):
    #print("Called: func_SERVICE with args:", args)
    if(new == 0):
        if (len(args) != 4):
            print("args rejected as they were not the correct number of elements 1:", args)
            return
        bdaddr = args[0]
        try:
            begin_handle = int(args[1], 16)
            end_handle = int(args[2], 16)
        except Exception as e:
            print("Couldn't convert value to int in func_SERVICE 1")
            return
        UUID128 = args[3]
    else:
        if (len(args) != 5):
            print("args rejected as they were not the correct number of elements 2:", new, args)
            return
        bdaddr = args[1]
        try:
            begin_handle = int(args[2], 16)
            end_handle = int(args[3], 16)
        except Exception as e:
            print("Couldn't convert value to int in func_SERVICE 2")
            return
        UUID128 = args[4]

    # Define the parameter values to be inserted
    values = (bdaddr_random, bdaddr, begin_handle, end_handle, UUID128)
    #print("values = ", values)
    # Execute the SQL statement
    cursor.execute(sql_GATT_services2, values)
    # Commit the changes to the database
    db_connection.commit()

# If new = 1, that means it has the new style formatting with the bdaddr_random already embedded
def func_ATT_HANDLES(bdaddr_random, new, args):
    #print("Called: func_ATT_HANDLES with args:", args)
    if(new == 0):
        if (len(args) != 3):
            print("args rejected as they were not the correct number of elements:", args)
            return
        bdaddr = args[0]
        attribute_handle = int(args[1], 16)
        UUID128 = args[2]
    else:
        if (len(args) != 4):
            print("args rejected as they were not the correct number of elements:", args)
            return
        bdaddr = args[1]
        attribute_handle = int(args[2], 16)
        UUID128 = args[3]

    # Define the parameter values to be inserted
    values = (bdaddr_random, bdaddr, attribute_handle, UUID128)
    #print("values = ", values)
    # Execute the SQL statement
    cursor.execute(sql_GATT_attribute_handles, values)
    # Commit the changes to the database
    db_connection.commit()

# Attempt a workaround to deal with data that was missing the bdaddr_random field in the log
# Look up whether we have any existing data for this bd_addr
def lookup_bdaddr_random(line):
    # Check for erroneous / skippable lines
    if(len(line) < 3):
#        print("skipping", line)
        return (-1, -1)

    # Check if the 1th token is a bdaddr or a type string
    #print("len(line[1]) = {}".format(len(line[1])))
    if(len(line[1]) == 17):

        # Check if we've already got it cached
        if(line[1] in type_cache.keys()):
            return (type_cache[line[1]], 0)

        # Lookup the bdaddr_device_type
        bda = line[1]
        #print("BD_ADDR = {}".format(bda))
        sql_filled = sql_lookup_bdaddr_type.format(bda=bda) # Fill in the bdaddr
        results = cursor.execute(sql_filled)
        results = cursor.fetchall()
        if(len(results) > 0):
            #print("lookup_bdaddr_random returning", results[0][0])
            type_cache[line[1]] = results[0][0]
            return (results[0][0], 0)
        else:
            #print("lookup_bdaddr_random returning", 9)
            type_cache[line[1]] = 9
            return (9,0) # Special value indicating we don't have data for this bdaddr
    else:
        # Check if we've already got it cached
        if(line[2] in type_cache.keys()):
            return (type_cache[line[2]], 1)

        # If the length is any other value, this means it's probably not a type-missing line
        # So check line[1] for whether it's "random" or "public"
        if(line[1] == "public"):
            print("lookup_bdaddr_random returning new 0")
            type_cache[line[2]] = 0
            return (0,1)
        elif(line[1] == "random"):
            print("lookup_bdaddr_random returning new 1")
            type_cache[line[2]] = 1
            return (1,1)
        else:
            print("lookup_bdaddr_random returning new 9 (should never get here for now)")
            type_cache[line[2]] = 9
            return (9,1) # Special value indicating we don't have data for this bdaddr

######## END HELPER FUNCTIONS ########

type_cache = {}

# Main
try:
    with open("./GATTprint_dedup.log", "r") as csvfile:
        reader = csv.reader(csvfile)
        for line in reader:
            if(len(line) > 0):
                print(line)
                if (line[0] == "GATTPRINT:CHARACTERISTIC" or line[0] == "GATTPRINT:CHAR_DESC"): # start supporting BetterGATTGetter.py alt (newer & clearer IMHO) names
                    #print("GATTPRINT:CHARACTERISTIC")
                    (bdaddr_type, new) = lookup_bdaddr_random(line)
                    if bdaddr_type == -1: continue
                    func_CHARACTERISTIC(bdaddr_type, new, line[1:])
                elif line[0] == "GATTPRINT:CHAR_VALUE":
                    #print("GATTPRINT:CHAR_VALUE")
                    (bdaddr_type, new) = lookup_bdaddr_random(line)
                    if bdaddr_type == -1: continue
                    func_CHAR_VALUE(bdaddr_type, new, line[1:])
                elif (line[0] == "GATTPRINT:DESCRIPTORS" or line[0] == "GATTPRINT:HANDLE_UUID"): # start supporting BetterGATTGetter.py alt (newer & clearer IMHO) names
                    #print("GATTPRINT:DESCRIPTORS")
                    (bdaddr_type, new) = lookup_bdaddr_random(line)
                    if bdaddr_type == -1: continue
                    func_ATT_HANDLES(bdaddr_type, new, line[1:])
                elif line[0] == "GATTPRINT:SERVICE":
                    #print("GATTPRINT:SERVICE")
                    (bdaddr_type, new) = lookup_bdaddr_random(line)
                    if bdaddr_type == -1: continue
                    func_SERVICE(bdaddr_type, new, line[1:])
                else:
                    continue


except FileNotFoundError:
    print("The file GATTprint_dedup.log could not be found.")
except Exception as e:
    print("An error occurred while opening the file GATTprint_dedup.log:", e)
    traceback.print_exc()

# Close the cursor and database connection
cursor.close()
db_connection.close()
