#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'bthci_evt.code == 0x3e && btcommon.eir_ad.entry.type == 0x04' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -e btcommon.eir_ad.entry.custom_uuid_32 -E separator=, -E quote=d | awk -F, '{gsub(/,,/, ",")}1'> /tmp/LE_bdaddr_to_UUID32s_incomplete.csv
tshark -r "$1" -Y 'bthci_evt.code == 0x3e && btcommon.eir_ad.entry.type == 0x05' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -e btcommon.eir_ad.entry.custom_uuid_32 -E separator=, -E quote=d | awk -F, '{gsub(/,,/, ",")}1'> /tmp/LE_bdaddr_to_UUID32s_complete.csv
# Dedup
cat /tmp/LE_bdaddr_to_UUID32s_incomplete.csv | sort | uniq > /tmp/LE_bdaddr_to_UUID32s_incomplete_uniq.csv
cat /tmp/LE_bdaddr_to_UUID32s_complete.csv | sort | uniq > /tmp/LE_bdaddr_to_UUID32s_complete_uniq.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_UUID32s_incomplete_uniq.csv'  IGNORE INTO TABLE LE_bdaddr_to_UUID32s FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, str_UUID32s) SET list_type = 4, bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_UUID32s_complete_uniq.csv'  IGNORE INTO TABLE LE_bdaddr_to_UUID32s FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, str_UUID32s) SET list_type = 5, bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
