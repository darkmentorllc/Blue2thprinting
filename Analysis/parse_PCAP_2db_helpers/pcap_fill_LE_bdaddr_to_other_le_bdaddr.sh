#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# Next put all the advertisement-specific "LE device address" data (from any packet type, e.g. ADV_IND or SCAN_RSP) into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.type == 0x1b' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.bd_addr -e btcommon.eir_ad.entry.le_bd_addr.type > /tmp/LE_bdaddr_to_other_le_bdaddr.csv

# Dedup
cat /tmp/LE_bdaddr_to_other_le_bdaddr.csv | sort | uniq > /tmp/LE_bdaddr_to_other_le_bdaddr_uniq.csv

echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_other_le_bdaddr_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_other_le_bdaddr FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @bdaddr_random, @le_evt_type, other_bdaddr, @other_bdaddr_random) SET bdaddr_random = CASE WHEN @bdaddr_random = 'False' THEN 0 WHEN @bdaddr_random = 'True' THEN 1 ELSE NULL END, le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED), other_bdaddr_random = CASE WHEN @other_bdaddr_random = 'False' THEN 0 WHEN @other_bdaddr_random = 'True' THEN 1 ELSE NULL END;"
