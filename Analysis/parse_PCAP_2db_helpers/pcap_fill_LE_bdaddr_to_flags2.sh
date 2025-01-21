#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# Next put all the advertisement-specific flags data (from any packet type, e.g. ADV_IND or SCAN_RSP) into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.type == 0x01' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.flags.le_limited_discoverable_mode -e btcommon.eir_ad.entry.flags.le_general_discoverable_mode -e btcommon.eir_ad.entry.flags.bredr_not_supported -e btcommon.eir_ad.entry.flags.le_bredr_support_controller -e btcommon.eir_ad.entry.flags.le_bredr_support_host > /tmp/LE_bdaddr_to_flags2.csv

# Dedup
cat /tmp/LE_bdaddr_to_flags2.csv | sort | uniq > /tmp/LE_bdaddr_to_flags2_uniq.csv

#echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_flags2_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_flags2 FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @bdaddr_random, @le_evt_type, @le_limited_discoverable_mode, @le_general_discoverable_mode, @bredr_not_supported, @le_bredr_support_controller, @le_bredr_support_host) SET bdaddr_random = CASE WHEN @bdaddr_random = 'False' THEN 0 WHEN @bdaddr_random = 'True' THEN 1 ELSE NULL END, le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED), le_limited_discoverable_mode = CAST(CONV(REPLACE(@le_limited_discoverable_mode, '0x', ''), 16, 10) AS UNSIGNED), le_general_discoverable_mode = CAST(CONV(REPLACE(@le_general_discoverable_mode, '0x', ''), 16, 10) AS UNSIGNED), bredr_not_supported = CAST(CONV(REPLACE(@bredr_not_supported, '0x', ''), 16, 10) AS UNSIGNED), le_bredr_support_controller = CAST(CONV(REPLACE(@le_bredr_support_controller, '0x', ''), 16, 10) AS UNSIGNED), le_bredr_support_host = CAST(CONV(REPLACE(@le_bredr_support_host, '0x', ''), 16, 10) AS UNSIGNED);"
