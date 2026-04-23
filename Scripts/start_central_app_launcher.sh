#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ERRORLOG="/tmp/runall.log"
echo "start_central_app_launcher.sh start" >> $ERRORLOG
HN=$(hostname)
echo $HN

# So this comes up after bluetoothctl scan on
sleep 45
#So that this comes up first
# -u for unbuffered stdout
RESULT=$(sudo -E python3 -u "$REPO_ROOT/Scripts/central_app_launcher.py" 2>&1 | tee -a "$REPO_ROOT/Logs/CAL.log" > /dev/null &)
echo "start_central_app_launcher.sh end" >> $ERRORLOG
