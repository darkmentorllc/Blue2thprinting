#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# Next put all the UUID128s (from any packet type, e.g. ADV_IND or SCAN_RSP) into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.type == 0x15' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.custom_uuid_128 > /tmp/LE_bdaddr_to_UUID128_service_solicit.csv

# Dedup
cat /tmp/LE_bdaddr_to_UUID128_service_solicit.csv | sort | uniq > /tmp/LE_bdaddr_to_UUID128_service_solicit_uniq.csv

echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_UUID128_service_solicit_uniq.csv'  IGNORE INTO TABLE LE_bdaddr_to_UUID128_service_solicit FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, str_UUID128s) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
