#!/bin/bash
echo "$1"
#echo ./pcap_fill_BLE2th_LL_VERSION_IND.sh "$1"
#./pcap_fill_BLE2th_LL_VERSION_IND.sh "$1"

#echo ./pcap_fill_LE_bdaddr_to_name.sh "$1"
#./pcap_fill_LE_bdaddr_to_name.sh "$1"

#echo ./pcap_fill_LE_bdaddr_to_MSD.sh "$1"
#./pcap_fill_LE_bdaddr_to_MSD.sh "$1"

#echo ./pcap_fill_LE_bdaddr_to_tx_power.sh "$1"
#./pcap_fill_LE_bdaddr_to_tx_power.sh "$1"

#echo ./pcap_fill_LE_bdaddr_to_other_le_bdaddr.sh "$1"
#./pcap_fill_LE_bdaddr_to_other_le_bdaddr.sh "$1"

#echo ./pcap_fill_LE_bdaddr_to_public_target_bdaddr.sh "$1"
#./pcap_fill_LE_bdaddr_to_public_target_bdaddr.sh "$1"

echo ./pcap_fill_LE_bdaddr_to_flags2.sh "$1"
./pcap_fill_LE_bdaddr_to_flags2.sh "$1"
