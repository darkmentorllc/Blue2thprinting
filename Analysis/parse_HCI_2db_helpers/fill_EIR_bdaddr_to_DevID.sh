#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'btcommon.eir_ad.entry.type == 0x10 && bthci_evt.code == 0x2f' -T fields -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.did.vendor_id_source -e btcommon.eir_ad.entry.did.vendor_id -e btcommon.eir_ad.entry.did.product_id -e btcommon.eir_ad.entry.did.version -E separator=, -E quote=d > /tmp/EIR_bdaddr_to_DevID.csv
echo "mysql import"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_DevID.csv' REPLACE INTO TABLE EIR_bdaddr_to_DevID FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (bdaddr, @vendor_id_source, @vendor_id, @product_id, @product_version) SET vendor_id_source = CAST(CONV(REPLACE(@vendor_id_source, '0x', ''), 16, 10) AS UNSIGNED), vendor_id = CAST(CONV(REPLACE(@vendor_id, '0x', ''), 16, 10) AS UNSIGNED), product_id = CAST(CONV(REPLACE(@product_id, '0x', ''), 16, 10) AS UNSIGNED), product_version = CAST(CONV(REPLACE(@product_version, '0x', ''), 16, 10) AS UNSIGNED);"
