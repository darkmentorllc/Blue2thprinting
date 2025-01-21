#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y '(bthci_evt.remote_name) && (bthci_evt.code == 0x07)' -T fields -e bthci_evt.bd_addr -e bthci_evt.remote_name -E separator=, -E quote=d > /tmp/RSP_bdaddr_to_name.csv
# Dedup
cat /tmp/RSP_bdaddr_to_name.csv | sort | uniq > /tmp/RSP_bdaddr_to_name_uniq.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/RSP_bdaddr_to_name_uniq.csv' REPLACE INTO TABLE RSP_bdaddr_to_name FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, device_name);"
