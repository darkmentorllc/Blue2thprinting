#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# Next put all the UUID32 data (from any packet type, e.g. ADV_IND or SCAN_RSP) into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.type == 0x04' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.custom_uuid_32 > /tmp/LE_bdaddr_to_UUID32s_incomplete.csv
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.type == 0x05' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.custom_uuid_32 > /tmp/LE_bdaddr_to_UUID32s_complete.csv

# Dedup
cat /tmp/LE_bdaddr_to_UUID32s_incomplete.csv | sort | uniq > /tmp/LE_bdaddr_to_UUID32s_incomplete_uniq.csv
cat /tmp/LE_bdaddr_to_UUID32s_complete.csv | sort | uniq > /tmp/LE_bdaddr_to_UUID32s_complete_uniq.csv


echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_UUID32s_incomplete_uniq.csv'  IGNORE INTO TABLE LE_bdaddr_to_UUID32s FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, str_UUID32s) SET list_type = 4, bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_UUID32s_complete_uniq.csv'  IGNORE INTO TABLE LE_bdaddr_to_UUID32s FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, str_UUID32s) SET list_type = 5, bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
