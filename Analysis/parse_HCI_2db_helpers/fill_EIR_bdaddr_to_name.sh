#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'bthci_evt.code == 0x2f && btcommon.eir_ad.entry.type == 0x08 && btcommon.eir_ad.entry.device_name' -T fields -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.device_name -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_name_short.csv
tshark -r "$1" -Y 'bthci_evt.code == 0x2f && btcommon.eir_ad.entry.type == 0x09 && btcommon.eir_ad.entry.device_name' -T fields -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.device_name -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_name_complete.csv
echo "sedding"
# Get rid of hex prefix, so it can be used as an INT in mysql
#sed -i '' s/^\"0x0/\"/g /tmp/dev_and_type.csv
# Get rid of "\r" on some Z-Link names, which MySQL will interpret as a carriage return after it imports it
uname=$(uname)
if [ $uname == "Darwin" ]; then
    sed -i '' s/\\\\\r//g /tmp/EIR_bdaddr_to_name_short.csv
    sed -i '' s/\\\\\r//g /tmp/EIR_bdaddr_to_name_complete.csv
else
    sed -i "s/\\\\\r//g" /tmp/EIR_bdaddr_to_name_short.csv
    sed -i "s/\\\\\r//g" /tmp/EIR_bdaddr_to_name_complete.csv
fi
cat /tmp/EIR_bdaddr_to_name_short.csv | sort | uniq > /tmp/EIR_bdaddr_to_name_short_uniq.csv
cat /tmp/EIR_bdaddr_to_name_complete.csv | sort | uniq > /tmp/EIR_bdaddr_to_name_complete_uniq.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_name_short_uniq.csv'  IGNORE INTO TABLE EIR_bdaddr_to_name FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, device_name) SET device_name_type = 8;"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_name_complete_uniq.csv'  IGNORE INTO TABLE EIR_bdaddr_to_name FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, device_name) SET device_name_type = 9;"
