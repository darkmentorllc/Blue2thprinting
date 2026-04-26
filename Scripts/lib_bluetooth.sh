#!/bin/bash

##########################################
# Shared readiness helpers for the capture scripts.
# Source this file (don't execute it) from start_*.sh.
#
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

# Block until the kernel has enumerated hci0 and bluetoothd has registered at
# least one Controller on the system D-Bus (the readiness condition that, when
# missing, produces "org.bluez.Error.NotReady"). Returns 0 on success, 1 on
# timeout. First arg is the timeout in seconds (default 120).
wait_for_bluetooth() {
    local timeout="${1:-120}"
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if [ -d /sys/class/bluetooth/hci0 ] && \
           bluetoothctl show 2>/dev/null | grep -q '^Controller '; then
            return 0
        fi
        sleep 1
    done
    echo "wait_for_bluetooth: timed out after ${timeout}s waiting for hci0 + D-Bus controller" >&2
    return 1
}

# Block until a btmon process is running so HCI logging is in place before
# scanning starts. Returns 0 on success, 1 on timeout. First arg is the
# timeout in seconds (default 60).
wait_for_btmon() {
    local timeout="${1:-60}"
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if pgrep -x btmon >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "wait_for_btmon: timed out after ${timeout}s waiting for btmon process" >&2
    return 1
}
