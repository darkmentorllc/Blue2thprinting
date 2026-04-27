#!/bin/bash

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ERRORLOG="/tmp/runall.log"

echo "runall.log start" >> $ERRORLOG
# Start the individual tools
#"$REPO_ROOT/Scripts/start_gpspipe.sh" &>/dev/null &
"$REPO_ROOT/Scripts/start_btmon.sh" &>/dev/null &
"$REPO_ROOT/Scripts/start_bluetoothctl.sh" &>/dev/null &
"$REPO_ROOT/Scripts/start_central_app_launcher.sh" &>/dev/null &
echo "runall.log stop" >> $ERRORLOG
