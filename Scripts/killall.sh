#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################
#
# Stop everything runall.sh's @reboot orchestration spawned: the python and
# native workers central_app_launcher.py drives, plus the start_*.sh wrapper
# bash scripts that runall.sh forked off.
#
# Each match uses `pkill -f '<script-or-binary-path>'` so we target processes
# by their full command line rather than by COMM. The previous `pkill -u root
# bash` shape suicided this script's own shell mid-cleanup (its argv also
# contains "bash"), which is why a `k` would leave wrappers like
# Scripts/start_central_app_launcher.sh alive — pkill killed killall.sh's
# shell before it finished signalling. The targeted patterns below don't
# match this script's argv (Scripts/killall.sh) so cleanup runs to completion.

# Python workers spawned by central_app_launcher.py
pkill -f 'Scripts/central_app_launcher\.py'           2>/dev/null
pkill -f 'Sniffle/python_cli/sniff_receiver\.py'      2>/dev/null
pkill -f 'Scripts/BG/Better_Getter\.py'               2>/dev/null
pkill -f 'Scripts/btc_sdp_gatt\.py'                   2>/dev/null

# Native binaries
pkill -f 'bluez-5\.66/tools/DarkFirmware_VSC_LMP'     2>/dev/null
pkill -f 'bluez-5\.66/tools/sdptool'                  2>/dev/null
killall btmon                                          2>/dev/null  # system /usr/bin/btmon (post cf9ae7f) + any legacy bluez-5.66/monitor/btmon
killall sdptool                                        2>/dev/null  # belt-and-braces in case anyone is running the system sdptool

# Wrapper bash scripts spawned by runall.sh. These spend most of their time
# in `sleep N` waiting to launch the worker, so killing the worker alone
# leaves the wrapper alive (PID 724 in the original bug report).
pkill -f 'Scripts/runall\.sh'                         2>/dev/null
pkill -f 'Scripts/start_central_app_launcher\.sh'     2>/dev/null
pkill -f 'Scripts/start_btmon\.sh'                    2>/dev/null
pkill -f 'Scripts/start_bluetoothctl\.sh'             2>/dev/null  # legacy install path; D-Bus discovery replaced this
pkill -f 'Scripts/start_gpspipe\.sh'                  2>/dev/null  # legacy install path

exit 0
