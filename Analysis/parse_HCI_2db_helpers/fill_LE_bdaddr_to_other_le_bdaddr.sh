#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'bthci_evt.code == 0x3e && btcommon.eir_ad.entry.type == 0x1b' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -e btcommon.eir_ad.entry.bd_addr -e btcommon.eir_ad.entry.le_bd_addr.type -E separator=, -E quote=d | awk -F, '{gsub(/,,/, ",")}1' > /tmp/LE_bdaddr_to_other_le_bdaddr.csv
# Dedup
cat /tmp/LE_bdaddr_to_other_le_bdaddr.csv | sort | uniq > /tmp/LE_bdaddr_to_other_le_bdaddr_uniq.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_other_le_bdaddr_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_other_le_bdaddr FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, other_bdaddr, @other_bdaddr_random) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED), other_bdaddr_random = CAST(CONV(REPLACE(@other_bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED);"
