#!/bin/bash
echo "$1"
echo "tsharking"
tshark -r "$1" -Y 'bthci_evt.code == 0x3e && btcommon.eir_ad.entry.type == 0x16 && btcommon.eir_ad.entry.uuid_16 != 0xfd6f' -T fields -e bthci_evt.bd_addr  -e bthci_evt.le_peer_address_type -e bthci_evt.le_advts_event_type -e bthci_evt.le_ext_advts_event_type -e btcommon.eir_ad.entry.uuid_16  -e btcommon.eir_ad.entry.service_data -E separator=, -E quote=d | awk -F, '{gsub(/,,/, ",")}1' | sort | uniq
# Dedup
echo "mysql import"
