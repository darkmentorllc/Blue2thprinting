#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1"  -Y '(bthci_evt.code == 0x3e) && (btcommon.eir_ad.entry.type == 0x08) && (btcommon.eir_ad.entry.device_name != "")' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e btcommon.eir_ad.entry.type -e btcommon.eir_ad.entry.device_name -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -E occurrence=f -E separator=, -E quote=d | awk -F',' '{if ($5 != "") {print $1","$2","$5",\"8\","$4} else {print $1","$2","$6",\"9\","$4}}' > /tmp/LE_bdaddr_to_name_incomplete.csv
tshark -r "$1"  -Y '(bthci_evt.code == 0x3e) && (btcommon.eir_ad.entry.type == 0x09) && (btcommon.eir_ad.entry.device_name != "")' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e btcommon.eir_ad.entry.type -e btcommon.eir_ad.entry.device_name -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -E occurrence=f -E separator=, -E quote=d | awk -F',' '{if ($5 != "") {print $1","$2","$5",\"9\","$4} else {print $1","$2","$6",\"9\","$4}}' > /tmp/LE_bdaddr_to_name_complete.csv
# Dedup
cat /tmp/LE_bdaddr_to_name_complete.csv | sort | uniq > /tmp/LE_bdaddr_to_name_complete_uniq.csv
cat /tmp/LE_bdaddr_to_name_incomplete.csv | sort | uniq > /tmp/LE_bdaddr_to_name_incomplete_uniq.csv
# Get rid of "\r" on some Z-Link names, which MySQL will interpret as a carriage return after it imports it
uname=$(uname)
if [ $uname == "Darwin" ]; then
    sed -i '' s/\\\\\r//g /tmp/LE_bdaddr_to_name_incomplete_uniq.csv
else
    sed -i "s/\\\\\r//g" /tmp/LE_bdaddr_to_name_incomplete_uniq.csv
fi
if [ $uname == "Darwin" ]; then
    sed -i '' s/\\\\\r//g /tmp/LE_bdaddr_to_name_complete_uniq.csv
else
    sed -i "s/\\\\\r//g" /tmp/LE_bdaddr_to_name_complete_uniq.csv
fi
echo "mysql import"
echo mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_name_incomplete_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_name2 FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, device_name_type, device_name) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
echo mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_name_complete_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_name2 FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, device_name_type, device_name) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
