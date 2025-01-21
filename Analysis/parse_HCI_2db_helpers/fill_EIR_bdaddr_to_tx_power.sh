#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'bthci_evt.code == 0x2f && btcommon.eir_ad.entry.type == 0x0a' -T fields -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.power_level -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_tx_power.csv
# Dedup
cat /tmp/EIR_bdaddr_to_tx_power.csv | sort | uniq > /tmp/EIR_bdaddr_to_tx_power_uniq.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_tx_power_uniq.csv' REPLACE INTO TABLE EIR_bdaddr_to_tx_power FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, device_tx_power);"
