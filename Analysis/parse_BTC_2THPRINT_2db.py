#!/usr/local/bin/python3

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

import mysql.connector
import traceback

lmp_versions = {
    0: '1.0b',
    1: '1.1',
    2: '1.2',
    3: '2.0',
    4: '2.1',
    5: '3.0',
    6: '4.0',
    7: '4.1',
    8: '4.2',
    9: '5.0',
    10: '5.1',
    11: '5.2',
    12: '5.3',
    13: '5.4',
}

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
sql_LMP_VERSION_RES = "INSERT IGNORE INTO LMP_VERSION_RES (device_bdaddr, lmp_version, device_BT_CID, lmp_sub_version) VALUES (%s, %s, %s, %s)"
sql_LMP_FEATURES_RES = "INSERT IGNORE INTO LMP_FEATURES_RES (device_bdaddr, page, features) VALUES (%s, %s, %s)"
sql_LMP_NAME_RES = "INSERT IGNORE INTO LMP_NAME_RES (device_bdaddr, device_name) VALUES (%s, %s)"

def print_string(args):
    try:
        # Split the byte string and convert each value to an integer
        byte_values = [int(byte_str, 16) for byte_str in args]
        # Create a byte array from the list of integer values
        byte_array = bytes(byte_values)
        # Decode the byte array using UTF-8 to obtain a Unicode string
        unicode_string = byte_array.decode("utf-8")
        print("The string is:", unicode_string)
        return unicode_string
    except UnicodeDecodeError:
        print("Error decoding the string.")
        return -1

# LMP_NAME_RES
def func_LMP_OP_0x02(bdaddr, args):
    unicode_string = ""
    print("Called: func_LMP_OP_0x02 with bdaddr:", bdaddr)
    if check_args(args) == -1:
        print("args rejected as they were not a byte array: ", args)
        return
    else:
        print(args)
        unicode_string = print_string(args)
        if(unicode_string == -1 or unicode_string.strip() == ""):
            # Abort
            return

    # Define the parameter values to be inserted
    values = (bdaddr, unicode_string)
    # Execute the SQL statement
    cursor.execute(sql_LMP_NAME_RES, values)
    # Commit the changes to the database
    db_connection.commit()


# LMP_NOT_ACCEPTED
def func_LMP_OP_0x04(bdaddr, args):
    '''
    print("Called: func_LMP_OP_0x04 with bdaddr:", bdaddr)
    if check_args(args) == -1:
        print("args rejected as they were not a byte array: ", args)
#    else print("args: ", args)
    '''

# LMP_VERSION_RES
def func_LMP_OP_0x26(bdaddr, args):
    print("Called: func_LMP_OP_0x26 with bdaddr:", bdaddr)
    if check_args(args) == -1:
        print("args rejected as they were not a byte array: ", args)
    else:
         print("args: ", args)
    lmp_version = int(args[0], 16)
    if(lmp_version > 13):
        print("Link Layer Version out of range. Returning. Error->", args)
        return
    spec_version = lmp_versions[lmp_version]
    print("\tLink Layer Version Number:", args[0], "= BT spec", spec_version)
    bt_CID = int(args[1], 16) | (int(args[2], 16) << 8)
    print("\tBluetooth Company ID: 0x%04X" % bt_CID)
    subversion = int(args[3], 16) | (int(args[4], 16) << 8)
    print("\tSub-Version Number: 0x%04X" % subversion)

    # Define the parameter values to be inserted
    values = (bdaddr, int(args[0], 16), bt_CID, subversion)
    # Execute the SQL statement
    cursor.execute(sql_LMP_VERSION_RES, values)
    # Commit the changes to the database
    db_connection.commit()

#LMP_FEATURES_RES
def func_LMP_OP_0x28(bdaddr, args):
    print("Called: func_LMP_OP_0x28 with bdaddr:", bdaddr)
    if check_args(args) == -1:
        print("args rejected as they were not a byte array: ", args)
        return
    else: print("args: ", args)

    reversed_args = args[::-1]
    try:
        int_args = [int(arg, 16) for arg in reversed_args]
    except ValueError:
        return
    features = 0
    for num in int_args:
        features = (features << 8) | num

    print("Features: 0x%016x" % features)
    page = 0 # We don't seem to capture whether it's features page 0 or 1 or 2 right now, so just assume it's 0

    # Define the parameter values to be inserted
    values = (bdaddr, page, features)
    # Execute the SQL statement
    cursor.execute(sql_LMP_FEATURES_RES, values)
    # Commit the changes to the database
    db_connection.commit()


def check_args(args):
    for arg in args:
        if not arg.startswith("0x") or len(arg) != 4 or not all(c in "0123456789ABCDEF" for c in arg[2:]):
            return -1
    return 0

bdaddr = "NULL"

try:
    with open("../Logs/BTC_2THPRINT.log", "rb") as file:
        for line in file:
            try:
                line = line.decode("utf-8").rstrip("\n")  # Decode and remove newline character
            except UnicodeDecodeError:
                print("Error decoding line:", repr(line))
                continue

            #print(line)
            if line.startswith("BTC_2THPRINT: LOG ENTRY FOR BDADDR: "):
                bdaddr = line.split(": ")[-1].strip()
            elif line.startswith("BTC_2THPRINT: ALL RESPONSES RECEIVED"):
                bdaddr = "NULL"
            elif line.startswith("BTC_2THPRINT: BDADDR ") and "2THPRINTING TERMINATED DUE TO 10 SEC TIMEOUT" in line:
                bdaddr = "NULL"
            elif line.startswith("BTC_2THPRINT: LOG ENTRY FOR BDADDR: ") and bdaddr != "NULL":
                bdaddr = line.split(": ")[-1].strip()

            if bdaddr == "NULL":
                continue

            tokens = line.split()
            if len(tokens) >= 2:
                opcode = tokens[1]
                if opcode == "LMP_OP_0x02":
                    func_LMP_OP_0x02(bdaddr, tokens[2:])
                elif opcode == "LMP_OP_0x04":
                    func_LMP_OP_0x04(bdaddr, tokens[2:])
                elif opcode == "LMP_OP_0x26":
                    func_LMP_OP_0x26(bdaddr, tokens[2:])
                elif opcode == "LMP_OP_0x28":
                    func_LMP_OP_0x28(bdaddr, tokens[2:])
except FileNotFoundError:
    print("The file BTC_2THPRINT.log could not be found.")
except Exception as e:
    print("An error occurred while opening the file:", e)
    traceback.print_exc()

# Close the cursor and database connection
cursor.close()
db_connection.close()
