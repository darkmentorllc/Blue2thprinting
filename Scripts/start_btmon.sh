#!/bin/bash

ERRORLOG="/tmp/runall.log"
echo "start_btmon.sh start" >> $ERRORLOG
LOGPATH="/home/user/Blue2thprinting/Scripts/logs/btmon"
DATE=$(/bin/date +%F-%H-%M-%S)
HN=$(hostname)
echo $HN
echo "Logging to ${LOGPATH}/${DATE}_${HN}.bin"

sleep 31
hciconfig hci0 down
sleep 1
hciconfig hci0 up
sleep 1
RESULT=$( /usr/bin/btmon -T -w ${LOGPATH}/${DATE}_${HN}.bin &>/dev/null&)
echo "start_btmon.sh end" >> $ERRORLOG
