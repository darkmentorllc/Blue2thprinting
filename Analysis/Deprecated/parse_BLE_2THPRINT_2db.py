#!/usr/local/bin/python3

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

import mysql.connector

# Establish connection to the MySQL database
db_connection = mysql.connector.connect(
    host='localhost',
    user='user',
    password='a',
    database='bt2',
    auth_plugin='mysql_native_password'
)

# Create a cursor to interact with the database
cursor = db_connection.cursor()

# Prepare the SQL statement with placeholders
sql_LL_VERSION_IND = "INSERT IGNORE INTO LL_VERSION_IND (bdaddr, bdaddr_random, ll_version, device_BT_CID, ll_sub_version) VALUES (%s, %s, %s, %s, %s)"
sql_LL_UNKNOWN_RSP = "INSERT IGNORE INTO LL_UNKNOWN_RSP (bdaddr, bdaddr_random, unknown_opcode) VALUES (%s, %s, %s)"
sql_LL_FEATUREs    = "INSERT IGNORE INTO LL_FEATUREs (bdaddr, bdaddr_random, opcode, features) VALUES (%s, %s, %s, %s)"
sql_LL_PHYs        = "INSERT IGNORE INTO LL_PHYs (bdaddr, bdaddr_random, opcode, tx_phys, rx_phys) VALUES (%s, %s, %s, %s, %s)"
sql_LL_LENGTHs     = "INSERT IGNORE INTO LL_LENGTHs (bdaddr, bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time) VALUES (%s, %s, %s, %s, %s, %s, %s)"
sql_LL_PING_RSP    = "INSERT IGNORE INTO LL_PINGs (bdaddr, bdaddr_random, opcode, direction) VALUES (%s, %s, %s, %s)"
file_path = './BLE_2THPRINT_dedup.log'

ll_versions = {
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

with open(file_path, 'r') as file:
    for line in file:
        tokens = line.strip().split(' ')

        if len(tokens) < 4:
            continue

        if tokens[1] == 'LOG' or tokens[1] == 'COMPLETED':
            continue

        bdaddr = tokens[1]
        try:
            bdaddr_type = int(tokens[2])
        except ValueError:
            print(f"invalid token {tokens[2]}")
            continue
        response_type = tokens[3]

        print("2THPRINT for " + bdaddr)

        if response_type == 'LL_FEATURE_RSP' or response_type == 'LL_SLAVE_FEATURE_REQ':
            print("\t%s" % response_type)
            features = (
                        int(tokens[5], 16) +
                        (int(tokens[6], 16) << 8) +
                        (int(tokens[7], 16) << 16) +
                        (int(tokens[8], 16) << 24) +
                        (int(tokens[9], 16) << 32) +
                        (int(tokens[10], 16) << 40) +
                        (int(tokens[11], 16) << 48) +
                        (int(tokens[12], 16) << 56)
            )
            #raw_byte_string = '_'.join(tokens[4:])
            #print('\traw_byte_string: %s' % raw_byte_string)
            print("\tFeatures: 0x%016X" % features)
            # Define the parameter values to be inserted
            values = (bdaddr_type, bdaddr, int(tokens[4], 16), features)
            # Execute the SQL statement
            cursor.execute(sql_LL_FEATUREs, values)
            # Commit the changes to the database
            db_connection.commit()


        if response_type == 'LL_LENGTH_RSP' or response_type == 'LL_LENGTH_REQ':
            print("\t%s" % response_type)
            max_rx_octets = int(tokens[5], 16) + (int(tokens[6], 16) << 8)
            max_rx_time   = int(tokens[7], 16) + (int(tokens[8], 16) << 8)
            max_tx_octets = int(tokens[9], 16) + (int(tokens[10], 16) << 8)
            max_tx_time   = int(tokens[11], 16) + (int(tokens[12], 16) << 8)
            print("\tMaxRxOctets: 0x%04X" % max_rx_octets)
            print("\tMaxRxTime: 0x%04X" % max_rx_time)
            print("\tMaxTxOctets: 0x%04X" % max_tx_octets)
            print("\tMaxTxTime: 0x%04X" % max_tx_time)

            #raw_byte_string = '_'.join(tokens[5:])
            #print('\traw_byte_string: %s' % raw_byte_string)

            # Define the parameter values to be inserted
            values = (bdaddr_type, bdaddr, int(tokens[4], 16), max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            # Execute the SQL statement
            cursor.execute(sql_LL_LENGTHs, values)
            # Commit the changes to the database
            db_connection.commit()


        if response_type == 'LL_PING_RSP':
            print("\t%s" % response_type)
            # Define the parameter values to be inserted
            values = (bdaddr_type, bdaddr, 1)
            # Execute the SQL statement
            cursor.execute(sql_LL_PING_RSP, values)
            # Commit the changes to the database
            db_connection.commit()

        if response_type == 'LL_VERSION_IND':
            print("\t%s" % response_type)
            if len(tokens) > 8:
                lmp_byte = int(tokens[5], 16)
                ll_version = ll_versions.get(lmp_byte, 'Unknown')
                print('\tLMP Version = %s' % ll_version)
                company_id = int(tokens[6], 16) + (int(tokens[7], 16) << 8)
                print("\tCompany ID: 0x%04X" % company_id)
                ll_sub_version = int(tokens[8], 16) + (int(tokens[9], 16) << 8)
                print("\tLMP Sub-Version: 0x%04X" % ll_sub_version)
                # Define the parameter values to be inserted
                values = (bdaddr_type, bdaddr, lmp_byte, company_id, ll_sub_version)
                # Execute the SQL statement
                cursor.execute(sql_LL_VERSION_IND, values)
                # Commit the changes to the database
                db_connection.commit()

        if response_type == 'LL_UNKNOWN_RSP':
            print("\t%s" % response_type)
            raw_byte_string = '_'.join(tokens[4:])
            print('\tUNKNOWN LMP Opcode: %s' % raw_byte_string)
            unknown_opcode = int(tokens[5], 16)
            # Define the parameter values to be inserted
            values = (bdaddr_type, bdaddr, unknown_opcode)
            # Execute the SQL statement
            cursor.execute(sql_LL_UNKNOWN_RSP, values)
            # Commit the changes to the database
            db_connection.commit()

        if response_type == 'LL_PHY_RSP' or response_type == 'LL_PHY_REQ':
            print("\t%s" % response_type)
            tx_phys = int(tokens[5], 16)
            rx_phys = int(tokens[6], 16)
            print("\tTX_PHYS: 0x%02X" % tx_phys)
            print("\tRX_PHYS: 0x%02X" % rx_phys)
            # Define the parameter values to be inserted
            values = (bdaddr_type, bdaddr, tx_phys, rx_phys)
            # Execute the SQL statement
            cursor.execute(sql_LL_PHYs, values)
            # Commit the changes to the database
            db_connection.commit()

# Close the cursor and database connection
cursor.close()
db_connection.close()
