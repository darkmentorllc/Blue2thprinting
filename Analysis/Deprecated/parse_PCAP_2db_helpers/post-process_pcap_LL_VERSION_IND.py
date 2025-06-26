# Script to process /tmp/LL_VERSION_IND_uniq.csv created by pcap_fill_LL_VERSION_IND.sh

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

import csv

# Function to convert "True" and "False" to "1" and "0"
def convert_boolean(value):
    if value == "True":
        return "1"
    elif value == "False":
        return "0"
    else:
        print("Sanity check failed. Ignoring corrupt data")
        return "-1"

# Dictionaries to store results
result_dict_CONNECT = {}
result_dict_VERSION = {}

# Open the CSV file
with open('/tmp/LL_VERSION_IND_uniq.csv', newline='') as csvfile:
    csvreader = csv.reader(csvfile, delimiter=',', quotechar='"')

    # Iterate through each row in the CSV
    for row in csvreader:
        if len(row) < 5 or len(row) > 7:
            continue  # Skip rows that have the wrong number of elements

        # Tokenize the row
        tok = [elem.strip() for elem in row]

        # I just used the PDU type of 5 for CONNECT_IND lines
        if tok[0] == "0x05":
            # Convert tok[2] from "True"/"False" to "1"/"0"
            tok[2] = convert_boolean(tok[2])
            if(tok[2] == "-1"):
                continue
            tok[4] = convert_boolean(tok[4])
            if(tok[4] == "-1"):
                continue
            # Store the BDADDR as the key and whether it's random or not as the value
            result_dict_CONNECT[tok[1]] = tok[2]
            result_dict_CONNECT[tok[3]] = tok[4]

        # I just used the LL control data type opcode of 0xC for LL_VERSION_IND lines
        elif tok[0] == "0x0c":
            # Depending on tok[3], store in the merged dictionary result_dict_VERSION
            if tok[3] == "2":
                result_dict_VERSION[tok[1]] = (tok[4], tok[5], tok[6])
            elif tok[3] == "3":
                result_dict_VERSION[tok[2]] = (tok[4], tok[5], tok[6])

# For human sanity checking only
'''
# Print the resulting dictionary
print("Resulting Dictionary for CONNECT_IND:")
for key, value in result_dict_CONNECT.items():
    print(f"{key}: {value}")

print("\nResulting Dictionary for LL_VERSION_IND:")
for key, value in result_dict_VERSION.items():
    print(f"{key}: {value}")
'''

# Write the CSV lines to a file appropriate for direct import to mysql LL_VERSION_IND table via a CLI mysql invocation
with open('/tmp/LL_VERSION_IND_uniq_done.csv', 'w', newline='\n') as csvfile:
    csvwriter = csv.writer(csvfile, quoting=csv.QUOTE_ALL, lineterminator="\n")

    for bdaddr, bdaddr_random in result_dict_CONNECT.items():
        if bdaddr in result_dict_VERSION:
            ll_version_hex, device_BT_CID_hex, ll_sub_version_hex = result_dict_VERSION[bdaddr]

            # Convert hexadecimal values to decimal integers
            ll_version = int(ll_version_hex, 16)
            device_BT_CID = int(device_BT_CID_hex, 16)
            ll_sub_version = int(ll_sub_version_hex, 16)

            # Print CSV line
            #print(f'"{bdaddr_random}","{bdaddr}","{ll_version}","{device_BT_CID}","{ll_sub_version}"')

            csvwriter.writerow([bdaddr_random, bdaddr, ll_version, device_BT_CID, ll_sub_version])
