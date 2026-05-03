#!/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################
#
# remove.sh — uninstalls Blue2thprinting from this host.
#
# What it does (idempotent):
#   1. Stops running B2P processes (central_app_launcher / sniff_receiver /
#      Better_Getter / DarkFirmware_VSC_LMP / btmon / sdptool / btc_sdp_gatt).
#   2. Removes ONLY the B2P entry from root's crontab. All other crontab
#      entries are preserved verbatim. A backup is written to
#      /tmp/crontab.root.b2pbak before mutation.
#   3. Finds every Blue2thprinting checkout under /home, /root, /opt, and
#      /usr/local (a directory is considered an install if it contains both
#      Scripts/runall.sh and setup_capture_helper_debian-based.sh) and removes
#      it with rm -rf. Refuses to remove top-level mount points as a guard.
#   4. If the Realtek firmware installer left .orig backups (sentinel:
#      /lib/firmware/rtl_bt/.darkfirmware_real_i_installed), restores the
#      stock firmware files and removes the sentinel.
#   5. Removes the alias lines that setup_capture_helper_debian-based.sh
#      appends to each user's ~/.bashrc (c, k, d, pj, TME, TB, TBB, BG). A
#      .b2pbak backup of every modified bashrc is written next to it.
#
# Re-run safe: re-running on a clean host is a no-op.
#
# Usage:  sudo ./remove.sh

set -u

if [ "$EUID" -ne 0 ]; then
    echo "remove.sh must be run with sudo (it modifies root crontab and /lib/firmware)."
    exit 1
fi

print_banner() {
    echo ""
    echo "========================================================================================"
    echo "  $1"
    echo "========================================================================================"
}

# Run the bulk of the script from / so we can rm -rf the directory this
# script may live inside without yanking our own CWD.
cd /

##########################################################################
# 1. Stop running B2P processes.
##########################################################################
print_banner "Stopping any running Blue2thprinting processes."

# pkill -f matches against the full command line, so this catches launches
# regardless of the install path. Each || true keeps set -u happy when there's
# nothing to kill.
pkill -f 'Scripts/central_app_launcher\.py' 2>/dev/null || true
pkill -f 'Sniffle/python_cli/sniff_receiver\.py' 2>/dev/null || true
pkill -f 'Scripts/BG/Better_Getter\.py' 2>/dev/null || true
pkill -f 'bluez-5\.66/tools/DarkFirmware_VSC_LMP' 2>/dev/null || true
pkill -f 'bluez-5\.66/tools/sdptool' 2>/dev/null || true
pkill -f 'bluez-5\.66/monitor/btmon' 2>/dev/null || true
pkill -f 'Scripts/btc_sdp_gatt\.py' 2>/dev/null || true
# Wrapper bash scripts. These spend most of their time in sleep, then launch
# their corresponding python/binary tool. Kill them too so they don't relaunch
# something into a directory we're about to delete.
pkill -f 'Scripts/runall\.sh' 2>/dev/null || true
pkill -f 'Scripts/start_central_app_launcher\.sh' 2>/dev/null || true
pkill -f 'Scripts/start_btmon\.sh' 2>/dev/null || true
pkill -f 'Scripts/start_bluetoothctl\.sh' 2>/dev/null || true
pkill -f 'Scripts/start_gpspipe\.sh' 2>/dev/null || true
# Generic fallbacks for the system-installed copies the helper scripts may
# have invoked. killall returns nonzero if nothing matched; that's fine.
killall btmon 2>/dev/null || true
killall sdptool 2>/dev/null || true
echo "  Done."

##########################################################################
# 2. Remove only the Blue2thprinting cron entry.
##########################################################################
print_banner "Cleaning Blue2thprinting entry from root crontab."

CRON_BAK="/tmp/crontab.root.b2pbak"
TMP_CRON="$(mktemp)"
if crontab -u root -l 2>/dev/null > "$TMP_CRON"; then
    if grep -qE 'Blue2thprinting.*runall\.sh' "$TMP_CRON"; then
        cp "$TMP_CRON" "$CRON_BAK"
        echo "  Backed up existing root crontab to $CRON_BAK."
        # Strip only lines that reference a Blue2thprinting runall.sh.
        # Other lines (whether B2P-related or not) are left untouched.
        grep -vE 'Blue2thprinting.*runall\.sh' "$CRON_BAK" > "$TMP_CRON"
        crontab -u root "$TMP_CRON"
        echo "  Removed @reboot Blue2thprinting/Scripts/runall.sh entry."
    else
        echo "  No Blue2thprinting entry found in root crontab. Skipping."
    fi
else
    echo "  Root has no crontab. Skipping."
fi
rm -f "$TMP_CRON"

##########################################################################
# 3. Find and remove Blue2thprinting checkouts.
##########################################################################
print_banner "Locating and removing Blue2thprinting checkouts."

# Match by signature (Scripts/runall.sh + setup_capture_helper_debian-based.sh
# are both unique to this repo) so a directory called "Blue2thprinting" that
# isn't actually a B2P checkout would NOT be removed.
mapfile -t CANDIDATES < <(
    find /home /root /opt /usr/local -maxdepth 5 \
        -name "setup_capture_helper_debian-based.sh" -print 2>/dev/null \
    | xargs -I{} dirname {} \
    | sort -u
)

if [ ${#CANDIDATES[@]} -eq 0 ]; then
    echo "  No Blue2thprinting installs found."
fi

for dir in "${CANDIDATES[@]}"; do
    if [ ! -f "$dir/Scripts/runall.sh" ]; then
        echo "  Skipping $dir (no Scripts/runall.sh — not a B2P install)."
        continue
    fi
    # Refuse to remove anything that's a top-level mount or root-ish path.
    case "$dir" in
        /|/home|/root|/opt|/usr|/usr/local|/etc|/var|/tmp)
            echo "  REFUSING to remove $dir (looks like a system root)."
            continue
            ;;
    esac
    echo "  Removing $dir"
    rm -rf "$dir"
done

##########################################################################
# 4. Restore Realtek firmware backup if present.
##########################################################################
print_banner "Restoring Realtek firmware (if Blue2thprinting installed it)."

RTL_DIR="/lib/firmware/rtl_bt"
SENTINEL="$RTL_DIR/.darkfirmware_real_i_installed"
restored_any=0
for orig in "$RTL_DIR/rtl8761bu_fw.bin.orig" "$RTL_DIR/rtl8761bu_fw.bin.zst.orig"; do
    [ -f "$orig" ] || continue
    target="${orig%.orig}"
    cp -f "$orig" "$target"
    rm -f "$orig"
    echo "  Restored $target from backup."
    restored_any=1
done
if [ -f "$SENTINEL" ]; then
    rm -f "$SENTINEL"
    echo "  Removed install sentinel $SENTINEL."
fi
if [ "$restored_any" -eq 0 ] && [ ! -f "$SENTINEL" ]; then
    echo "  No Blue2thprinting Realtek firmware backup or sentinel found."
fi

##########################################################################
# 5. Strip Blue2thprinting alias lines from each user's ~/.bashrc.
##########################################################################
print_banner "Cleaning Blue2thprinting aliases from per-user .bashrc files."

# These are the exact lines that setup_capture_helper_debian-based.sh's
# create_aliases() appends. Lines containing "Blue2thprinting" cover the
# c and k aliases (which embed the install path); the rest are matched
# verbatim against the literals the installer writes.
strip_b2p_aliases() {
    local rc="$1"
    [ -f "$rc" ] || return 0
    if ! grep -qE 'Blue2thprinting|Tell_Me_Everything\.py|Better_Getter\.py|alias d="ls -la /dev/serial/by-id/"|alias pj="python -m json\.tool"' "$rc"; then
        return 0
    fi
    cp -f "$rc" "$rc.b2pbak"
    sed -i \
        -e '/Blue2thprinting/d' \
        -e '\#alias d="ls -la /dev/serial/by-id/"#d' \
        -e '\#alias pj="python -m json\.tool"#d' \
        -e '\#alias TME="python3 \./Tell_Me_Everything\.py"#d' \
        -e '\#alias TB="python3 \./Tell_Me_Everything\.py --token-file \./tf --query-BTIDALPOOL"#d' \
        -e '\#alias TBB="python3 \./Tell_Me_Everything\.py --token-file \./tf --query-BTIDALPOOL --bdaddr"#d' \
        -e '\#alias BG="python3 \./Better_Getter\.py"#d' \
        "$rc"
    echo "  Cleaned $rc (backup at $rc.b2pbak)."
}

for home in /home/*/ /root/; do
    [ -d "$home" ] || continue
    strip_b2p_aliases "$home/.bashrc"
done

print_banner "Blue2thprinting removal complete."
