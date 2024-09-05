#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# First put all the CONNECT_IND packetdata into the output file, so we can build up the state in python later
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.advertising_header.pdu_type == 0x05' -E separator=, -E quote=d -T fields -e btle.advertising_header.pdu_type -e btle.initiator_address -e btle.advertising_header.randomized_tx -e btle.advertising_address -e btle.advertising_header.randomized_rx > /tmp/LL_VERSION_IND.csv
# Next put all the LL_VERSION_IND packets into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.control_opcode == 0x0c' -E separator=, -E quote=d -T fields -e btle.control_opcode -e btle.master_bd_addr -e btle.slave_bd_addr -e btle_rf.pdu_type -e btle.control.version_number -e btle.control.company_id -e btle.control.subversion_number >> /tmp/LL_VERSION_IND.csv

# Dedup
cat /tmp/LL_VERSION_IND.csv | sort | uniq > /tmp/LL_VERSION_IND_uniq.csv

echo "Post-processing raw tshark pcap output"
# This script will process /tmp/LL_VERSION_IND_uniq.csv and output /tmp/LL_VERSION_IND_uniq_done.csv, which will have cut down the device_bdaddr field to only the master or slave field based on whichever was actually responsible for sending the LL_VERSION_IND
# It's not possible to print everything the way we want in one pass in a stateless way with wireshark (e.g. because we can't determine based only on the LL_VERSION_IND whether the addresses are public or random, because that's only in the CONNECT_IND)
python3 post-process_pcap_LL_VERSION_IND.py

echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LL_VERSION_IND_uniq_done.csv' IGNORE INTO TABLE BLE2th_LL_VERSION_IND FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr_type, device_bdaddr, ll_version, device_BT_CID, ll_sub_version);"
