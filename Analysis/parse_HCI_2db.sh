#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

echo "$1"
echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_DevID.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_DevID.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_PSRM_CoD.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_PSRM_CoD.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_UUID128s.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_UUID128s.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_UUID16s.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_UUID16s.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_UUID32s.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_UUID32s.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_flags2.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_flags2.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_MSD.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_MSD.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_name.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_name.sh "$1"

echo ./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_tx_power.sh "$1"
./parse_HCI_2db_helpers/fill_EIR_bdaddr_to_tx_power.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_URI.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_URI.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID128_service_solicit.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID128_service_solicit.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID128s.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID128s.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID16_service_solicit.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID16_service_solicit.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID16s.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID16s.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID32s.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_UUID32s.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_appearance.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_appearance.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_connect_interval.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_connect_interval.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_flags2.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_flags2.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_MSD.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_MSD.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_name2.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_name2.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_other_le_bdaddr.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_other_le_bdaddr.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_public_target_bdaddr.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_public_target_bdaddr.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_service_data.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_service_data.sh "$1"

echo ./parse_HCI_2db_helpers/fill_LE_bdaddr_to_tx_power.sh "$1"
./parse_HCI_2db_helpers/fill_LE_bdaddr_to_tx_power.sh "$1"

echo fill_RSP_bdaddr_to_name.sh "$1"
./parse_HCI_2db_helpers/fill_RSP_bdaddr_to_name.sh "$1"
