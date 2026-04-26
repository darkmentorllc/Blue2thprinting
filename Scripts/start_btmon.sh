#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
source "$REPO_ROOT/Scripts/lib_bluetooth.sh"

ERRORLOG="/tmp/runall.log"
echo "start_btmon.sh start" >> $ERRORLOG
LOGPATH="$REPO_ROOT/Logs/btmon"
DATE=$(/bin/date +%F-%H-%M-%S)
HN=$(hostname)
echo $HN
echo "Logging to ${LOGPATH}/${DATE}_${HN}.bin"

wait_for_bluetooth || { echo "start_btmon.sh aborted: bluetooth not ready" >> $ERRORLOG; exit 1; }
RESULT=$( "$REPO_ROOT/bluez-5.66/monitor/btmon" -i 0 -T -w ${LOGPATH}/${DATE}_${HN}.bin &>/dev/null&)
echo "start_btmon.sh end" >> $ERRORLOG
