#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1"  -Y '(bthci_evt.code == 0x3e) && (btcommon.eir_ad.entry.device_name != "")' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e btcommon.eir_ad.entry.device_name -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -E occurrence=f -E separator=, -E quote=d | awk -F',' '{if ($4 != "") {print $1","$2","$4","$3} else {print $1","$2","$5","$3}}' > /tmp/LE_bdaddr_to_name.csv
# Dedup
cat /tmp/LE_bdaddr_to_name.csv | sort | uniq > /tmp/LE_bdaddr_to_name_uniq.csv
# Get rid of "\r" on some Z-Link names, which MySQL will interpret as a carriage return after it imports it
uname=$(uname)
if [ $uname == "Darwin" ]; then
    sed -i '' s/\\\\\r//g /tmp/LE_bdaddr_to_name_uniq.csv
else
    sed -i "s/\\\\\r//g" /tmp/LE_bdaddr_to_name_uniq.csv
fi
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_name_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_name FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @bdaddr_random, @le_evt_type, device_name) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
