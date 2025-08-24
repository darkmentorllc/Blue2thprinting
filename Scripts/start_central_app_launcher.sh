#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

ERRORLOG="/tmp/runall.log"
echo "start_central_app_launcher.sh start" >> $ERRORLOG
HN=$(hostname)
echo $HN

# So this comes up after bluetoothctl scan on
sleep 45
#So that this comes up first
# -u for unbuffered stdout
RESULT=$(sudo -E python3 -u /home/user/Blue2thprinting/Scripts/central_app_launcher.py 2>&1 | tee -a /home/user/Blue2thprinting/Logs/CAL.log &)
echo "start_central_app_launcher.sh end" >> $ERRORLOG
