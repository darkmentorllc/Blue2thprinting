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
# timeout in seconds (default 60). Matches the full command line via -f
# rather than COMM via -x, since COMM is truncated to 15 chars and can be
# overridden by PR_SET_NAME — bluez-5.66/monitor/btmon uniquely identifies
# our btmon regardless.
wait_for_btmon() {
    local timeout="${1:-60}"
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if pgrep -f 'bluez-5.66/monitor/btmon' >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "wait_for_btmon: timed out after ${timeout}s waiting for btmon process" >&2
    return 1
}

# Clear any soft-block on bluetooth rfkill devices via sysfs. At @reboot,
# systemd-rfkill restores the saved state asynchronously and bluetoothd can
# race ahead of it: its initial Set Powered command then fails with
# 'Failed to set mode: Failed (0x03)' (Hardware Failure from rfkill), and
# bluetoothd does not retry. We unblock proactively so the subsequent
# 'power on' call has a chance to succeed. Idempotent. No-op if no
# bluetooth rfkill device or already unblocked.
unblock_bt_rfkill() {
    local rk
    for rk in /sys/class/rfkill/rfkill*; do
        [ -e "$rk/type" ] || continue
        [ "$(cat "$rk/type" 2>/dev/null)" = "bluetooth" ] || continue
        if [ "$(cat "$rk/soft" 2>/dev/null)" = "1" ]; then
            if ! echo 0 > "$rk/soft" 2>/dev/null; then
                sudo -n sh -c "echo 0 > $rk/soft" 2>/dev/null || return 1
            fi
        fi
    done
    return 0
}

# Block until the controller reports 'Powered: yes'. bluetoothd's own initial
# Set Powered loses a race with rfkill at boot and it doesn't retry, so we
# unblock rfkill and re-issue 'power on' each iteration until it sticks.
# Returns 0 on success, 1 on timeout. First arg is the timeout in seconds
# (default 60).
wait_for_powered_adapter() {
    local timeout="${1:-60}"
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        unblock_bt_rfkill 2>/dev/null
        bluetoothctl power on >/dev/null 2>&1
        if bluetoothctl show 2>/dev/null | grep -qE '^[[:space:]]*Powered: yes'; then
            return 0
        fi
        sleep 1
    done
    echo "wait_for_powered_adapter: timed out after ${timeout}s waiting for Powered: yes" >&2
    return 1
}
