#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'bthci_evt.code == 0x2f && btcommon.eir_ad.entry.type == 0x02' -T fields -e bthci_evt.bd_addr  -e btcommon.eir_ad.entry.uuid_16 -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_UUID16s_incomplete.csv
tshark -r "$1" -Y 'bthci_evt.code == 0x2f && btcommon.eir_ad.entry.type == 0x03' -T fields -e bthci_evt.bd_addr  -e btcommon.eir_ad.entry.uuid_16 -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_UUID16s_complete.csv
# Dedup
cat /tmp/EIR_bdaddr_to_UUID16s_incomplete.csv | sort | uniq > /tmp/EIR_bdaddr_to_UUID16s_incomplete_uniq.csv
cat /tmp/EIR_bdaddr_to_UUID16s_complete.csv | sort | uniq > /tmp/EIR_bdaddr_to_UUID16s_complete_uniq.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_UUID16s_incomplete_uniq.csv' REPLACE INTO TABLE EIR_bdaddr_to_UUID16s FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, str_UUID16s) SET list_type = 2;"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_UUID16s_complete_uniq.csv' REPLACE INTO TABLE EIR_bdaddr_to_UUID16s FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, str_UUID16s) SET list_type = 3;"
