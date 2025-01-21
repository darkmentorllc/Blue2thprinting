#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
if [ -s "/tmp/LE_bdaddr_to_URI.csv" ]; then
    rm /tmp/LE_bdaddr_to_URI.csv
fi
tshark -r "$1" -Y 'bthci_evt.code == 0x3e && btcommon.eir_ad.entry.type == 0x24' -E separator=, -E quote=d -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -e btcommon.eir_ad.entry.power_level > /tmp/LE_bdaddr_to_URI.csv

# Dedup
if [ -s "/tmp/LE_bdaddr_to_URI.csv" ]; then
    cat /tmp/LE_bdaddr_to_URI.csv | sort | uniq > /tmp/LE_bdaddr_to_URI_uniq.csv
    echo "Just because these are rare, here is what was seen:"
    cat /tmp/LE_bdaddr_to_URI_uniq.csv
fi

if [ -s "/tmp/LE_bdaddr_to_URI_uniq.csv" ]; then
    echo "mysql import"
    mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_URI_uniq.csv' REPLACE INTO TABLE LE_bdaddr_to_URI FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @bdaddr_random, @le_evt_type, str_URI) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
fi
