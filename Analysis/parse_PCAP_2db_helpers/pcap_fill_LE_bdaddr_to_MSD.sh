#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
# Next put all the Manufacturer Specific Data (MSD) advertisement data into the file
tshark -r "$1" -Y '!(_ws.malformed) && !(btle.crc.incorrect) && btcommon.eir_ad.entry.type == 0xff' -E separator=, -E quote=d -T fields -e btle.advertising_address -e btle.advertising_header.randomized_tx -e btle.advertising_header.pdu_type -e btcommon.eir_ad.entry.company_id -e btcommon.eir_ad.entry.data > /tmp/LE_bdaddr_to_MSD.csv

# Dedup
cat /tmp/LE_bdaddr_to_MSD.csv | sort | uniq > /tmp/LE_bdaddr_to_MSD_uniq.csv

# TODO: need to determine if I need to pull this code over from the fill_EIR_bdaddr_to_MSD.sh script
# Note: This can and will have entries like device ID = 0x000f (broadcom), which then have some "3DS" info for the manufacturer-specific data. But the problem is that Wireshark knows how to
# dissect that info, and consequently nothing will be printed out for btcommon.eir_ad.entry.data. So then it has the wrong number of columns
# So we're going to process the file to tack a ,"XXXXXX" on to the end, since we don't have real values for now
#uname=$(uname)
#if [ $uname == "Darwin" ]; then
#    sed -i '' "s/\"0x000f\",$/&\"XXXXXX\"/" /tmp/EIR_bdaddr_to_MSD_uniq.csv
#else
#    sed -i "s/\"0x000f\",$/&\"XXXXXX\"/" /tmp/EIR_bdaddr_to_MSD_uniq.csv
#fi


echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/LE_bdaddr_to_MSD_uniq.csv' IGNORE INTO TABLE LE_bdaddr_to_MSD FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @bdaddr_random, @le_evt_type, @device_BT_CID, manufacturer_specific_data) SET bdaddr_random = CASE WHEN @bdaddr_random = 'False' THEN 0 WHEN @bdaddr_random = 'True' THEN 1 ELSE NULL END, le_evt_type = CAST(CONV(REPLACE(@le_evt_type, '0x', ''), 16, 10) AS UNSIGNED), device_BT_CID = CAST(CONV(REPLACE(@device_BT_CID, '0x', ''), 16, 10) AS UNSIGNED);"
