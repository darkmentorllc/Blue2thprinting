#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################
#
# Clear all log files under Logs/ without removing the directory structure.
# Keeping the per-tool subdirectories (Logs/btmon, Logs/sniffle, Logs/BetterGetter,
# Logs/btc_sdp_gatt, Logs/DarkFirmwareLMPLog, ...) is what prevents the silent
# "early termination" failure mode some capture scripts hit when their target
# directory is gone — a missing dir makes bash redirects fail before the worker
# binary even execs. Removing the files but preserving the dirs lets a fresh
# capture session start cleanly without re-creating the tree by hand.
#
# Suggested order if the launcher is currently running:
#   sudo bash Scripts/killall.sh
#   sudo bash Scripts/clearlogs.sh
# (Many log files are owned by root because the launcher runs under sudo, so
# clearlogs.sh itself needs sudo to delete them.)

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
LOGS_DIR="$REPO_ROOT/Logs"

if [ ! -d "$LOGS_DIR" ]; then
    echo "clearlogs.sh: $LOGS_DIR does not exist; nothing to do"
    exit 0
fi

before=$(du -sh "$LOGS_DIR" 2>/dev/null | awk '{print $1}')
file_count=$(find "$LOGS_DIR" -type f ! -name '.gitkeep' 2>/dev/null | wc -l)
echo "clearlogs.sh: clearing $file_count file(s) under $LOGS_DIR (was $before; keeping directories + .gitkeep)"

# -type f matches only files, leaving every directory in place. Preserve
# .gitkeep markers so git keeps tracking the otherwise-empty subdirectories.
find "$LOGS_DIR" -type f ! -name '.gitkeep' -delete

after=$(du -sh "$LOGS_DIR" 2>/dev/null | awk '{print $1}')
echo "clearlogs.sh: done; $LOGS_DIR is now $after"
