#!/bin/bash

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ERRORLOG="/tmp/runall.log"

echo "runall.log start" >> $ERRORLOG

# Raspbian (and some Ubuntu images) come up with bluetooth soft-blocked by
# systemd-rfkill, which makes `hciconfig hciN up` fail with "Operation not
# possible due to RF-kill (132)". Clear it before launching anything that
# touches the radio. Failure here is non-fatal — systems without the rfkill
# binary silently skip.
[ -x /usr/sbin/rfkill ] && /usr/sbin/rfkill unblock bluetooth >> $ERRORLOG 2>&1 || true
[ -x /sbin/rfkill ]     && /sbin/rfkill unblock bluetooth     >> $ERRORLOG 2>&1 || true

# Start the individual tools
#"$REPO_ROOT/Scripts/start_gpspipe.sh" &>/dev/null &
"$REPO_ROOT/Scripts/start_btmon.sh" &>/dev/null &
# Discovery is now handled in-process by central_app_launcher.py via BlueZ D-Bus (issue #47).
# The custom bluetoothctl scan is no longer needed in the runtime path; keep the script
# around for ad-hoc diagnostic use.
#"$REPO_ROOT/Scripts/start_bluetoothctl.sh" &>/dev/null &
"$REPO_ROOT/Scripts/start_central_app_launcher.sh" &>/dev/null &
echo "runall.log stop" >> $ERRORLOG
