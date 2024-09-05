#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo "tsharking"
#tshark -r "$1" -Y 'bthci_evt.code == 0x2f' -T fields -e bthci_evt.bd_addr -e bthci_evt.page_scan_repetition_mode -e btcommon.cod.class_of_device -E separator=, -E quote=d -E occurrence=f > /tmp/EIR_bdaddr_to_PSRM_CoD.csv
tshark -r "$1" -Y 'bthci_evt.code == 0x22' -T fields -e bthci_evt.bd_addr -e bthci_evt.page_scan_repetition_mode -e btcommon.cod.class_of_device -E separator=, -E quote=d -E occurrence=f > /tmp/EIR_bdaddr_to_PSRM_CoD_2.csv
# Dedup
#cat /tmp/EIR_bdaddr_to_PSRM_CoD.csv | sort | uniq > /tmp/EIR_bdaddr_to_PSRM_CoD_uniq.csv
cat /tmp/EIR_bdaddr_to_PSRM_CoD_2.csv | sort | uniq > /tmp/EIR_bdaddr_to_PSRM_CoD_2_uniq.csv
echo "mysql import"
#mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_PSRM_CoD_uniq.csv' REPLACE INTO TABLE EIR_bdaddr_to_PSRM_CoD FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @page_scan_rep_mode, @class_of_device) SET class_of_device = CAST(CONV(REPLACE(@class_of_device, '0x', ''), 16, 10) AS UNSIGNED), page_scan_rep_mode = CAST(CONV(REPLACE(@page_scan_rep_mode, '0x', ''), 16, 10) AS UNSIGNED);"
mysql -u user -pa --database='bt' --execute="LOAD DATA INFILE '/tmp/EIR_bdaddr_to_PSRM_CoD_2_uniq.csv' REPLACE INTO TABLE EIR_bdaddr_to_PSRM_CoD FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\n' (device_bdaddr, @page_scan_rep_mode, @class_of_device) SET class_of_device = CAST(CONV(REPLACE(@class_of_device, '0x', ''), 16, 10) AS UNSIGNED), page_scan_rep_mode = CAST(CONV(REPLACE(@page_scan_rep_mode, '0x', ''), 16, 10) AS UNSIGNED);"
