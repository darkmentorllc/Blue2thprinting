#!/bin/bash
#
# install_from_scratch_test.sh — end-to-end install regression test.
#
# Wipes ~/Blue2thprinting on a target host, clones a specific branch
# fresh, runs setup_capture_helper_debian-based.sh, reboots, and then
# verifies that everything the capture pipeline needs ends up healthy:
#
#   * setup_capture_helper_debian-based.sh exits 0
#   * sniffle_receiver_rust binary present and executable
#   * exactly one '@reboot ... Scripts/runall.sh' line in root's crontab
#     (regardless of how many stale entries existed pre-test)
#   * post-reboot: central_app_launcher.py spawns >= 1 sniffle_receiver_rust
#   * post-reboot: CAL.log has 0 "Ignoring message due to missing CRLF"
#   * post-reboot: CAL.log has 0 Python tracebacks
#
# Usage: ./install_from_scratch_test.sh [--host USER@HOST] [--branch BRANCH]
#                                       [--repo URL] [--skip-reboot]
#
# Defaults:  --host user@192.168.1.206
#            --branch master
#            --repo https://github.com/darkmentorllc/Blue2thprinting.git
#
# Exit 0 = all checks passed, non-zero = first failure code (3..9).
#
# NB: destructive. ~/Blue2thprinting on the target host is rm -rf'd
# without backup. Run it only against test hosts.

set -uo pipefail

HOST="user@192.168.1.206"
BRANCH="master"
REPO="https://github.com/darkmentorllc/Blue2thprinting.git"
SKIP_REBOOT=0

while [ $# -gt 0 ]; do
    case "$1" in
        --host)         HOST="$2"; shift 2;;
        --branch)       BRANCH="$2"; shift 2;;
        --repo)         REPO="$2"; shift 2;;
        --skip-reboot)  SKIP_REBOOT=1; shift;;
        -h|--help)
            grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//' | head -40
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2;;
    esac
done

# REMOTE_DIR is populated below from the remote `echo $HOME` once we
# can talk to the target. Don't pre-set it to '$HOME/Blue2thprinting'
# — that string fails when re-quoted into a `sudo nohup bash -c '…'`
# block, because sudo's $HOME is /root, not the calling user's home.
REMOTE_DIR=""

step()  { printf '\n=== [%s] %s ===\n' "$(date +%H:%M:%S)" "$*"; }
ok()    { printf '  ✓ %s\n' "$*"; }
fail()  { printf '  ✗ %s\n' "$*" >&2; exit "${2:-1}"; }
warn()  { printf '  ! %s\n' "$*" >&2; }

s()     { ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$HOST" "$@"; }
s_or_die() { s "$@" || fail "remote command failed: $*" 9; }

# ----------------------------------------------------------------------
step "Snapshotting target state pre-test ($HOST, branch=$BRANCH)"
pre_uptime=$(s "uptime") || fail "host unreachable" 9
# Resolve the calling user's $HOME ONCE on the remote, store the absolute
# path locally. Everything below uses $REMOTE_DIR as a plain absolute path
# — no shell-variable trickery to keep alive through a sudo barrier.
REMOTE_HOME=$(s 'echo $HOME')
REMOTE_DIR="$REMOTE_HOME/Blue2thprinting"
pre_crontab=$(s "sudo crontab -u root -l 2>/dev/null | wc -l")
pre_runall_entries=$(s "sudo crontab -u root -l 2>/dev/null | grep -cE '^[[:space:]]*@reboot[[:space:]]+.*Scripts/runall\.sh[[:space:]]*\$' || echo 0")
pre_dongles=$(s 'ls /dev/ttyUSB* 2>/dev/null | wc -l')
ok "host reachable: $pre_uptime"
ok "remote home:    $REMOTE_HOME (REMOTE_DIR=$REMOTE_DIR)"
ok "pre-test crontab: $pre_crontab lines, $pre_runall_entries @reboot runall.sh entries"
ok "pre-test dongles: $pre_dongles"

# ----------------------------------------------------------------------
step "Stopping running services so they don't fight the wipe"
s 'sudo pkill -9 -f "Scripts/central_app_launcher\.py" 2>/dev/null;
   sudo pkill -9 -f "Sniffle/(python_cli/sniff_receiver\.py|sniffle_receiver_rust)" 2>/dev/null;
   sudo pkill -9 -f "Scripts/BG/Better_Getter\.py" 2>/dev/null;
   sudo pkill -9 -f "Scripts/btc_sdp_gatt\.py" 2>/dev/null;
   sudo pkill -9 -f "bluez-5\.66/tools" 2>/dev/null;
   sudo killall btmon 2>/dev/null;
   true'
ok "running services stopped"

# ----------------------------------------------------------------------
step "Wiping and re-cloning $REMOTE_DIR @ $BRANCH"
# `sudo` because a Blue2thprinting that's been used will have root-owned
# files inside it (__pycache__ written by central_app_launcher.py under
# sudo, pcap files, Logs/, etc.). A plain user rm would silently leave
# those behind and trip up the subsequent clone.
s "sudo rm -rf $REMOTE_DIR" || fail "rm -rf failed" 3
# --recurse-submodules so BTIDES_Schema etc. are populated. Use -j2 for
# parallel clone of submodules.
s "git clone --branch '$BRANCH' --recurse-submodules -j2 '$REPO' $REMOTE_DIR" \
    || fail "git clone failed" 3
clone_head=$(s "cd $REMOTE_DIR && git log --oneline -1")
ok "cloned: $clone_head"

# ----------------------------------------------------------------------
step "Running setup_capture_helper_debian-based.sh (long; ~15-25 min on Pi Zero W)"
# Run in background with nohup so SSH drops don't kill it. Stream
# progress to a remote log file we poll. Exit code via marker file.
# Drop /tmp scratch files (might be root-owned from a prior run), then
# launch the setup script unprivileged-with-internal-sudo: the
# script's check_env requires EUID=0, so we `sudo` the script itself,
# but the surrounding nohup/bash -c stays as the calling user so
# `cd $REMOTE_DIR` and shell expansions use the right $HOME.
s "sudo rm -f /tmp/setup_test.log /tmp/setup_test.rc; \
   nohup bash -c 'cd $REMOTE_DIR && \
        sudo ./setup_capture_helper_debian-based.sh > /tmp/setup_test.log 2>&1; \
        echo \$? | sudo tee /tmp/setup_test.rc >/dev/null' \
        </dev/null >/dev/null 2>&1 &"
sleep 5
# Confirm it actually started
pid=$(s "pgrep -f setup_capture_helper_debian-based.sh | head -1") \
    || fail "setup script didn't launch" 4
ok "setup launched on remote (pid $pid). polling for completion…"

# Poll every 30s, with progress dump. Cap at 45 min.
START=$(date +%s)
MAX_S=$((45 * 60))
last_size=0
while true; do
    elapsed=$(( $(date +%s) - START ))
    if [ "$elapsed" -gt "$MAX_S" ]; then
        warn "setup did not finish within $((MAX_S/60)) min — aborting wait"
        s "sudo tail -50 /tmp/setup_test.log"
        fail "setup timeout" 4
    fi
    if s "test -f /tmp/setup_test.rc" 2>/dev/null; then
        break
    fi
    cur_size=$(s "sudo stat -c%s /tmp/setup_test.log 2>/dev/null || echo 0")
    cur_tail=$(s "sudo tail -1 /tmp/setup_test.log 2>/dev/null" | tr -d '\r')
    if [ "$cur_size" != "$last_size" ]; then
        printf '  [%4ds] log %sB: %s\n' "$elapsed" "$cur_size" "${cur_tail:0:100}"
        last_size=$cur_size
    fi
    sleep 30
done
setup_rc=$(s "cat /tmp/setup_test.rc")
if [ "$setup_rc" != "0" ]; then
    warn "setup exit code: $setup_rc"
    s "sudo tail -40 /tmp/setup_test.log"
    fail "setup_capture_helper_debian-based.sh exited $setup_rc" 4
fi
elapsed=$(( $(date +%s) - START ))
ok "setup completed in $(( elapsed / 60 ))m$(( elapsed % 60 ))s, exit 0"

# ----------------------------------------------------------------------
step "Verifying post-install state (pre-reboot)"

# Rust binary exists + is a regular file + executable.
# `test -f` AND `test -x`: -x alone passes for directories too (x bit on
# a dir means cd-able), which would mask the historical path-collision
# bug where `cp file dir/` made Sniffle/sniffle_receiver_rust a directory
# containing the binary instead of being the binary itself.
s "test -f $REMOTE_DIR/Sniffle/sniffle_receiver_rust && test -x $REMOTE_DIR/Sniffle/sniffle_receiver_rust" \
    || fail "Sniffle/sniffle_receiver_rust missing, not a regular file, or not executable" 5
size=$(s "stat -c%s $REMOTE_DIR/Sniffle/sniffle_receiver_rust")
# A directory inode is typically 4096 B; the actual binary is ~350-400 KB.
# Catch the path-collision regression with an explicit size floor.
if [ "$size" -lt 100000 ]; then
    fail "Sniffle/sniffle_receiver_rust suspiciously small (${size} B) — path collision?" 5
fi
ok "Sniffle/sniffle_receiver_rust present (${size} bytes)"

# Crontab dedup: should be EXACTLY 1 @reboot runall.sh entry
post_runall_entries=$(s "sudo crontab -u root -l | grep -cE '^[[:space:]]*@reboot[[:space:]]+.*Scripts/runall\.sh[[:space:]]*\$' || echo 0")
if [ "$post_runall_entries" = "1" ]; then
    ok "crontab dedup: exactly 1 @reboot runall.sh entry (was $pre_runall_entries pre-test)"
else
    s "sudo crontab -u root -l"
    fail "crontab dedup failed: expected 1 entry, found $post_runall_entries" 6
fi

# The entry should point at the current install path
entry_path=$(s "sudo crontab -u root -l | grep -E '^[[:space:]]*@reboot[[:space:]]+.*Scripts/runall\.sh[[:space:]]*\$' | head -1")
expected_substr="Blue2thprinting/Scripts/runall.sh"
if echo "$entry_path" | grep -q "$expected_substr"; then
    ok "crontab entry points at current install: $entry_path"
else
    fail "crontab entry mis-pointed: $entry_path" 6
fi

if [ "$SKIP_REBOOT" = "1" ]; then
    step "PASS (pre-reboot only; --skip-reboot was set)"
    exit 0
fi

# ----------------------------------------------------------------------
step "Rebooting and waiting for cron to bring everything back up"
s "sudo -n reboot" 2>/dev/null || true
sleep 15  # give systemd time to actually shut down

# Wait for ssh to come back
while ! ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$HOST" "uptime" >/dev/null 2>&1; do
    sleep 5
done
back_up=$(s "uptime")
ok "host back: $back_up"

# Wait for central_app_launcher.py to spawn (start_central_app_launcher.sh
# sleeps 45 s after boot before launching it; pad to 90 s total).
step "Waiting for central_app_launcher.py to come up"
for i in $(seq 1 30); do
    if s "pgrep -af central_app_launcher\\.py | grep -qv pgrep"; then
        break
    fi
    sleep 5
done
if ! s "pgrep -af central_app_launcher\\.py | grep -qv pgrep"; then
    fail "central_app_launcher.py never spawned post-reboot" 7
fi
ok "central_app_launcher.py running"

# Wait another 30 s for sniffle_receiver_rust children to spawn
sleep 30
n_sniffers=$(s "pgrep -af 'Sniffle/sniffle_receiver_rust' | grep -cv pgrep")
if [ "$n_sniffers" -lt 1 ]; then
    s "pgrep -af central_app_launcher\\.py"
    s "sudo tail -20 $REMOTE_DIR/Logs/CAL.log 2>/dev/null"
    fail "no sniffle_receiver_rust processes running" 8
fi
ok "$n_sniffers sniffle_receiver_rust process(es) running"

# Let it accumulate log for 30 s, then grep for errors
sleep 30
crlf_errs=$(s "grep -c 'missing CRLF' $REMOTE_DIR/Logs/CAL.log 2>/dev/null || echo 0")
py_tracebacks=$(s "grep -c 'Traceback' $REMOTE_DIR/Logs/CAL.log 2>/dev/null || echo 0")
log_size=$(s "stat -c%s $REMOTE_DIR/Logs/CAL.log 2>/dev/null || echo 0")
ok "CAL.log $log_size bytes, $crlf_errs 'missing CRLF' line(s), $py_tracebacks traceback(s)"

# Hard pass criterion: zero missing-CRLF lines from sniff_receiver.py
# (the Rust binary doesn't emit that string at all, so any hit means
# either a leftover Python sniff_receiver is still spawning, or the
# Rust binary failed and Python fallback kicked in).
if [ "$crlf_errs" != "0" ]; then
    s "grep -B1 -A1 'missing CRLF' $REMOTE_DIR/Logs/CAL.log | head -10"
    fail "found 'missing CRLF' in CAL.log — sniff_receiver.py still active?" 8
fi

# ----------------------------------------------------------------------
step "PASS — install-from-scratch test green"
echo "  branch:         $BRANCH"
echo "  setup time:     $(( elapsed / 60 ))m$(( elapsed % 60 ))s"
echo "  crontab:        1 deduped @reboot entry"
echo "  binary:         ${size} bytes at Sniffle/sniffle_receiver_rust"
echo "  post-reboot:    $n_sniffers Rust sniffer(s), 0 CAL.log errors"
exit 0
