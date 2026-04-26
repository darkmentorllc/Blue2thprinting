#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

#bluetoothctl is a better than hcitool lescan because it shows more info about beacons it sees

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
source "$REPO_ROOT/Scripts/lib_bluetooth.sh"

ERRORLOG="/tmp/runall.log"
echo "start_bluetoothctl.sh start" >> $ERRORLOG
LOGPATH="$REPO_ROOT/Logs/bluetoothctl"
DATE=$(/bin/date +%F-%H-%M-%S)
HN=$(hostname)
LINKAGE_FILE="/tmp/BT_link.txt"
echo "Logging to ${LOGPATH}/${DATE}_${HN}.txt"

# Wait for bluetoothd to expose the controller on D-Bus first, otherwise
# 'scan on' fails with org.bluez.Error.NotReady.
wait_for_bluetooth || { echo "start_bluetoothctl.sh aborted: bluetooth not ready" >> $ERRORLOG; exit 1; }
# Then wait for btmon so its HCI capture covers our scan traffic.
wait_for_btmon || { echo "start_bluetoothctl.sh aborted: btmon never started" >> $ERRORLOG; exit 1; }
# Defensive: even when registered the adapter can be soft-blocked / unpowered,
# which also produces NotReady. Idempotent — no-op if already on.
bluetoothctl power on >/dev/null 2>&1

#Do the actual scanning, so hcidump and btmon can see traffic
#/usr/bin/bluetoothctl scan on > $LOGPATH/$DATE.txt

# Delete the link if it exists
if [ -e "$LINKAGE_FILE" ]; then
    rm "$LINKAGE_FILE"
fi
# Had to move over to my custom bluetoothctl to find out which are BTC vs. BLE devices!
RESULT=$(unbuffer "$REPO_ROOT/bluez-5.66/client/bluetoothctl" scan on > ${LOGPATH}/${DATE}_${HN}.txt &)
#Re-link to the file so it can be found by other scripts
ln -s ${LOGPATH}/${DATE}_${HN}.txt $LINKAGE_FILE
