#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# Next put all the name data (from any packet type, e.g. ADV_IND or SCAN_RSP) into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.device_name != ""' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.device_name > /tmp/LE_bdaddr_to_name.csv

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
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_name_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_name FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @bdaddr_random, @le_evt_type, device_name) SET bdaddr_random = CASE WHEN @bdaddr_random = 'False' THEN 0 WHEN @bdaddr_random = 'True' THEN 1 ELSE NULL END, le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
