#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# First put all the CONNECT_IND packetdata into the output file, so we can build up the state in python later
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.advertising_header.pdu_type == 0x05' -E separator=, -E quote=d -T fields -e btle.advertising_header.pdu_type -e btle.initiator_address -e btle.advertising_header.randomized_tx -e btle.advertising_address -e btle.advertising_header.randomized_rx > /tmp/LL_LENGTHs.csv
# Next put all the LL_LENGTH_REQ packets into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.control_opcode == 0x14' -E separator=, -E quote=d -T fields -e btle.control_opcode -e btle.master_bd_addr -e btle.slave_bd_addr -e btle_rf.pdu_type -e btle.control.max_rx_octets -e btle.control.max_rx_time -e btle.control.max_tx_octets -e btle.control.max_tx_time >> /tmp/LL_LENGTHs.csv
# Compensate for the fact that the master/slave terminology has changed to central/peripheral in the latest wireshark
if [ $? != 0 ]; then
    echo "Re-running with latest Wireshark field names"
    tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.control_opcode == 0x14' -E separator=, -E quote=d -T fields -e btle.control_opcode -e btle.central_bd_addr -e btle.peripheral_bd_addr -e btle_rf.pdu_type -e btle.control.max_rx_octets -e btle.control.max_rx_time -e btle.control.max_tx_octets -e btle.control.max_tx_time >> /tmp/LL_LENGTHs.csv
fi
# Next put all the LL_LENGTH_RSP packets into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.control_opcode == 0x15' -E separator=, -E quote=d -T fields -e btle.control_opcode -e btle.master_bd_addr -e btle.slave_bd_addr -e btle_rf.pdu_type -e btle.control.max_rx_octets -e btle.control.max_rx_time -e btle.control.max_tx_octets -e btle.control.max_tx_time >> /tmp/LL_LENGTHs.csv
# Compensate for the fact that the master/slave terminology has changed to central/peripheral in the latest wireshark
if [ $? != 0 ]; then
    echo "Re-running with latest Wireshark field names"
    tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btle.control_opcode == 0x15' -E separator=, -E quote=d -T fields -e btle.control_opcode -e btle.central_bd_addr -e btle.peripheral_bd_addr -e btle_rf.pdu_type -e btle.control.max_rx_octets -e btle.control.max_rx_time -e btle.control.max_tx_octets -e btle.control.max_tx_time >> /tmp/LL_LENGTHs.csv
fi

# Dedup
cat /tmp/LL_LENGTHs.csv | sort | uniq > /tmp/LL_LENGTHs_uniq.csv

echo "Post-processing raw tshark pcap output"
# This script will process /tmp/LL_LENGTHs_uniq.csv and output /tmp/LL_LENGTHs_uniq_done.csv, which will have cut down the bdaddr field to only the master or slave field based on whichever was actually responsible for sending the LL_LENGTH_REQ/RSP
# It's not possible to print everything the way we want in one pass in a stateless way with wireshark (e.g. because we can't determine based only on the LL_LENGTH_REQ/RSP whether the addresses are public or random, because that's only in the CONNECT_IND)
python3 ./parse_PCAP_2db_helpers/post-process_pcap_LL_LENGTHs.py

echo "mysql import"
mysql -u user -pa --database='bt2' --execute="LOAD DATA INFILE '/tmp/LL_LENGTHs_uniq_done.csv' IGNORE INTO TABLE LL_LENGTHs FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr_random, bdaddr, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time);"
