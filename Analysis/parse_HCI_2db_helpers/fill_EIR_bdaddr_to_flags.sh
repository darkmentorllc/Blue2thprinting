#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y '(btcommon.eir_ad.entry.type == 0x01) && (bthci_evt.code == 0x2f)' -T fields -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.flags.le_limited_discoverable_mode -e btcommon.eir_ad.entry.flags.le_general_discoverable_mode -e btcommon.eir_ad.entry.flags.le_bredr_support_controller -e btcommon.eir_ad.entry.flags.le_bredr_support_host -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_flags.csv
# Dedup
cat /tmp/EIR_bdaddr_to_flags.csv | sort | uniq > /tmp/EIR_bdaddr_to_flags_uniq.csv
# get rid of 0x prefix to make it so I don't need to alter all the mysql table import statements
uname=$(uname)
if [ $uname == "Darwin" ]; then
    sed -i '' s/\"0x0/\"/g /tmp/EIR_bdaddr_to_flags_uniq.csv
else
    sed -i "s/\"0x0/\"/g" /tmp/EIR_bdaddr_to_flags_uniq.csv
fi
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_flags_uniq.csv' REPLACE INTO TABLE EIR_bdaddr_to_flags FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, le_limited_discoverable_mode, le_general_discoverable_mode, le_bredr_support_controller, le_bredr_support_host);"
