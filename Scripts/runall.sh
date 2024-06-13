#!/bin/bash

ERRORLOG="/tmp/runall.log"

echo "runall.log start" >> $ERRORLOG
# Start the individual tools
#/home/pi/Scripts/start_gpspipe.sh &>/dev/null &
/home/pi/Scripts/start_btmon.sh &>/dev/null &
/home/pi/Scripts/start_bluetoothctl.sh &>/dev/null &
/home/pi/Scripts/start_central_app_launcher.sh &>/dev/null &
echo "runall.log stop" >> $ERRORLOG
