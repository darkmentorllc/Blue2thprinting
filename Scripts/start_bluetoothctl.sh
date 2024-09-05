#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

#bluetoothctl is a better than hcitool lescan because it shows more info about beacons it sees

LOGPATH="/home/user/Blue2thprinting/Logs/bluetoothctl"
DATE=$(/bin/date +%F-%H-%M-%S)
HN=$(hostname)
LINKAGE_FILE="/tmp/BT_link.txt"
echo "Logging to ${LOGPATH}/${DATE}_${HN}.txt"

#So this will come up after btmon
sleep 40

#Do the actual scanning, so hcidump and btmon can see traffic
#/usr/bin/bluetoothctl scan on > $LOGPATH/$DATE.txt

# Delete the link if it exists
if [ -e "$LINKAGE_FILE" ]; then
    rm "$LINKAGE_FILE"
fi
# Had to move over to my custom bluetoothctl to find out which are BTC vs. BLE devices!
RESULT=$(unbuffer /home/user/Blue2thprinting/bluez-5.66/client/bluetoothctl scan on > ${LOGPATH}/${DATE}_${HN}.txt &)
#Re-link to the file so it can be found by other scripts
ln -s ${LOGPATH}/${DATE}_${HN}.txt $LINKAGE_FILE
