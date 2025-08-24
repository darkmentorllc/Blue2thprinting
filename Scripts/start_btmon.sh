#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

ERRORLOG="/tmp/runall.log"
echo "start_btmon.sh start" >> $ERRORLOG
LOGPATH="/home/user/Blue2thprinting/Logs/btmon"
DATE=$(/bin/date +%F-%H-%M-%S)
HN=$(hostname)
echo $HN
echo "Logging to ${LOGPATH}/${DATE}_${HN}.bin"

sleep 31
hciconfig hci0 down
sleep 1
hciconfig hci0 up
sleep 1
RESULT=$( /home/user/Blue2thprinting/bluez-5.66/monitor/btmon -i 0 -T -w ${LOGPATH}/${DATE}_${HN}.bin &>/dev/null&)
echo "start_btmon.sh end" >> $ERRORLOG
