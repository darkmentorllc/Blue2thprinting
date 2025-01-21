# Script to process /tmp/LL_FEATUREs_uniq.csv created by pcap_fill_LL_FEATUREs.sh

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
result_dict_FEATURE_REQ = {}
result_dict_FEATURE_RSP = {}

# Open the CSV file
with open('/tmp/LL_FEATUREs_uniq.csv', newline='') as csvfile:
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

        # I just used the LL control data type opcode of 0x8 for LL_FEATURE_REQ lines
        elif tok[0] == "0x08":
            # Depending on tok[3] (M->S or S->M), store in the merged dictionary result_dict_FEATURE_REQ
            # We can't take for granted that REQs always come from masters. They can come from slaves too
            if tok[3] == "2":   # Wireshark calls this Master -> Slave
                result_dict_FEATURE_REQ[tok[1]] = tok[4]
            elif tok[3] == "3": # Wireshark calls this Slave -> Master
                result_dict_FEATURE_REQ[tok[2]] = tok[4]

        # I just used the LL control data type opcode of 0x8 for LL_FEATURE_RSP lines
        elif tok[0] == "0x09":
            # Depending on tok[3] (M->S or S->M), store in the merged dictionary result_dict_FEATURE_REQ
            # We can't take for granted that REQs always come from masters. They can come from slaves too
            if tok[3] == "2":   # Wireshark calls this Master -> Slave
                result_dict_FEATURE_RSP[tok[1]] = tok[4]
            elif tok[3] == "3": # Wireshark calls this Slave -> Master
                result_dict_FEATURE_RSP[tok[2]] = tok[4]

# For human sanity checking only
'''
# Print the resulting dictionary
print("Resulting Dictionary for CONNECT_IND:")
for key, value in result_dict_CONNECT.items():
    print(f"{key}: {value}")

print("\nResulting Dictionary for LL_FEATURE_REQs:")
for key, value in result_dict_FEATURE_REQ.items():
    print(f"{key}: {value}")

print("\nResulting Dictionary for LL_FEATURE_RSPs:")
for key, value in result_dict_FEATURE_RSP.items():
    print(f"{key}: {value}")
'''

# Write the CSV lines to a file appropriate for direct import to mysql LL_FEATUREs table via a CLI mysql invocation
with open('/tmp/LL_FEATUREs_uniq_done.csv', 'w', newline='\n') as csvfile:
    csvwriter = csv.writer(csvfile, quoting=csv.QUOTE_ALL, lineterminator="\n")

    for bdaddr, bdaddr_random in result_dict_CONNECT.items():
        if bdaddr in result_dict_FEATURE_REQ:
            features = result_dict_FEATURE_REQ[bdaddr]

            # Convert hexadecimal values to decimal integers
            features = int(features, 16)

            # Print CSV line
            #print(f'"{bdaddr_random}","{bdaddr}","8","{features}"')

            csvwriter.writerow([bdaddr_random, bdaddr, 8, features])

        if bdaddr in result_dict_FEATURE_RSP:
            features = result_dict_FEATURE_RSP[bdaddr]

            # Convert hexadecimal values to decimal integers
            features = int(features, 16)

            # Print CSV line
            #print(f'"{bdaddr_random}","{bdaddr}","9","{features}"')

            csvwriter.writerow([bdaddr_random, bdaddr, 9, features])
