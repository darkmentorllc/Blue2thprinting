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
# System btmon from the 'bluez' apt package. The Btsnoop file format is
# stable across BlueZ versions, so anything HCI_to_BTIDES.py expects from a
# 5.66-built btmon is satisfied by the system one too.
BTMON="$(command -v btmon || echo /usr/bin/btmon)"
echo $HN
echo "Logging to ${LOGPATH}/${DATE}_${HN}.bin"

# Fail loudly instead of silently if btmon isn't available. The previous
# `RESULT=$(... &)` pattern swallowed missing-binary errors and left the @reboot
# capture stack thinking everything was fine while no .bin file ever appeared.
if [ ! -x "$BTMON" ]; then
    echo "start_btmon.sh aborted: $BTMON does not exist or is not executable. Install the 'bluez' apt package or re-run setup_capture_helper_debian-based.sh." >> $ERRORLOG
    exit 1
fi

wait_for_bluetooth || { echo "start_btmon.sh aborted: bluetooth not ready" >> $ERRORLOG; exit 1; }
# Detach btmon properly: redirect stdin from /dev/null and stdout/stderr to a
# log file (not /dev/null) so we can debug future failures, and use disown so
# the process survives this script exiting under cron.
# No `-i N` flag: monitor ALL hci interfaces. The launcher cycles the Realtek
# dongle via USB rebind which renumbers it (hci0 -> hci2 -> ...), and we want
# btmon to keep capturing whichever number it ends up at.
nohup "$BTMON" -T -w "${LOGPATH}/${DATE}_${HN}.bin" \
    </dev/null >>"${LOGPATH}/btmon_stderr.log" 2>&1 &
BTMON_PID=$!
disown $BTMON_PID 2>/dev/null || true
sleep 1
if kill -0 $BTMON_PID 2>/dev/null; then
    echo "start_btmon.sh: btmon launched as pid $BTMON_PID" >> $ERRORLOG
else
    echo "start_btmon.sh aborted: btmon (pid $BTMON_PID) died within 1s; see ${LOGPATH}/btmon_stderr.log" >> $ERRORLOG
    exit 1
fi
echo "start_btmon.sh end" >> $ERRORLOG
