#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# TODO: The LE_bdaddr_to_flags database table doesn't currently have a field for btcommon.eir_ad.entry.flags.bredr_not_supported
# TODO: A new LE_bdaddr_to_flags2 table was created for the pcap scripts to include that. This will need to be updated and all data re-processed
tshark -r "$1" -Y 'bthci_evt.code == 0x3e && btcommon.eir_ad.entry.type == 0x01' -T fields -e bthci_evt.bd_addr -e bthci_evt.le_peer_address_type -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -e btcommon.eir_ad.entry.flags.le_limited_discoverable_mode -e btcommon.eir_ad.entry.flags.le_general_discoverable_mode -e btcommon.eir_ad.entry.flags.bredr_not_supported -e btcommon.eir_ad.entry.flags.le_bredr_support_controller -e btcommon.eir_ad.entry.flags.le_bredr_support_host -E occurrence=f -E separator=, -E quote=d | awk -F, '{gsub(/,,/, ",")}1' > /tmp/LE_bdaddr_to_flags2.csv
# Dedup
cat /tmp/LE_bdaddr_to_flags2.csv | sort | uniq > /tmp/LE_bdaddr_to_flags2_uniq.csv
# get rid of 0x prefix to make it so I don't need to alter all the mysql table import statements for the boolean values (which I didn't find a way to convert properly)
uname=$(uname)
if [ $uname == "Darwin" ]; then
    sed -i '' s/\"0x0/\"/g /tmp/LE_bdaddr_to_flags2_uniq.csv
else
    sed -i "s/\"0x0/\"/g" /tmp/LE_bdaddr_to_flags2_uniq.csv
fi

echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_flags2_uniq.csv' REPLACE INTO TABLE LE_bdaddr_to_flags2 FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @bdaddr_random, @le_evt_type, @le_limited_discoverable_mode, @le_general_discoverable_mode, @le_bredr_not_supported, @le_bredr_support_controller, @le_bredr_support_host) SET bdaddr_random = CAST(CONV(REPLACE(@bdaddr_random, '0x', ''), 16, 10) AS UNSIGNED), le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED);"
