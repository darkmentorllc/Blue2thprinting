#!/bin/bash
#
# sos_on_error.sh - flash the Raspberry Pi ACT LED in Morse code SOS (... --- ...)
# whenever a new error line appears in any Blue2thprinting log. Intended for the
# capture Pi (Pi Zero 2 W, hostname node3), which runs headless with no screen to
# watch the logs on.
#
# Modes:
#   (default) / --loop   run forever, polling the logs every POLL_INTERVAL seconds
#   --once               scan once and exit (for cron); saved byte offsets keep it
#                        from re-alerting on the same error
#   --test               flash one SOS and exit (verifies LED control); ignores logs
#   --list               print the log files it would watch, and exit
#
# Must run as root (it writes /sys/class/leds/<led>/brightness).
#
# Install as a service (recommended):
#   sudo cp sos_on_error.sh /usr/local/bin/
#   sudo tee /etc/systemd/system/sos-on-error.service >/dev/null <<'UNIT'
#   [Unit]
#   Description=Flash ACT LED in SOS on Blue2thprinting log errors
#   After=multi-user.target
#   [Service]
#   ExecStart=/usr/local/bin/sos_on_error.sh --loop
#   Restart=always
#   [Install]
#   WantedBy=multi-user.target
#   UNIT
#   sudo systemctl enable --now sos-on-error.service
#
# Or run periodically from cron instead of as a daemon:
#   * * * * * STATE_DIR=/var/lib/sos_on_error /usr/local/bin/sos_on_error.sh --once
#
set -uo pipefail

# ---- Config (override via environment) -------------------------------------
REPO_ROOT="${REPO_ROOT:-/home/pi/Blue2thprinting}"
LED_DIR="${LED_DIR:-/sys/class/leds/ACT}"   # Pi Zero 2 W onboard green LED
POLL_INTERVAL="${POLL_INTERVAL:-20}"        # seconds between scans in loop mode
SOS_REPEATS="${SOS_REPEATS:-3}"             # SOS words emitted per detected batch
SCAN_EXISTING="${SCAN_EXISTING:-1}"         # 1: on first sight of a log, scan it from
                                            # the start (catch an already-present error);
                                            # 0: only alert on lines added after startup

# Morse timing in seconds (the dot is the base unit).
DOT="${DOT:-0.2}"
DASH="${DASH:-0.6}"          # 3 units
SYM_GAP="${SYM_GAP:-0.2}"    # gap between symbols within a letter (1 unit)
LETTER_GAP="${LETTER_GAP:-0.6}"  # gap between letters (3 units)
WORD_GAP="${WORD_GAP:-1.4}"      # gap between repeated SOS words (7 units)

# Per-log byte offsets. /run is tmpfs (clears on reboot), fine for a daemon; for
# cron --once that must survive reboots, point STATE_DIR at a persistent path.
STATE_DIR="${STATE_DIR:-/run/sos_on_error}"

# Logs to watch. Globs expand at scan time, so files created later are picked up.
LOGS=(
  "/tmp/runall.log"
  "$REPO_ROOT/Logs/CAL.log"
  "$REPO_ROOT/Logs/btmon/btmon_stderr.log"
  "$REPO_ROOT/Logs/SDPprint.log"
  "$REPO_ROOT/Logs/GATTprint.log"
  "$REPO_ROOT"/Logs/*.log
)

# What counts as an error (case-insensitive, extended regex).
ERROR_REGEX="${ERROR_REGEX:-aborted|traceback|exception|fatal|segfault|core dumped|not installed|no such file|cannot open|permission denied|refusing to start|could not|failed to|\berror\b}"

# Benign chatter to ignore (normal recovery/retry lines), case-insensitive.
# "failed to create connection" is routine BR/EDR paging churn (a classic device
# declining an ACL connection), not a capture fault, so it is filtered out.
IGNORE_REGEX="${IGNORE_REGEX:-likely wedged|usbreset .* (ok|complete)|running usbreset|bettergetter failure 0x|still waiting for realtek|waiting for realtek dongle|failed to create connection}"
# ---------------------------------------------------------------------------

ON="$(cat "$LED_DIR/max_brightness" 2>/dev/null || echo 1)"
OFF=0
TRIGGER_SAVED=""

led_bright() { echo "$1" > "$LED_DIR/brightness" 2>/dev/null; }

led_take() {
  if [ ! -w "$LED_DIR/brightness" ]; then
    echo "sos_on_error: cannot write $LED_DIR/brightness (run as root, or set LED_DIR)" >&2
    return 1
  fi
  # Remember the active trigger (the token in [brackets]) so we can hand the LED back.
  TRIGGER_SAVED="$(sed -n 's/.*\[\([^]]*\)\].*/\1/p' "$LED_DIR/trigger" 2>/dev/null)"
  [ -n "$TRIGGER_SAVED" ] || TRIGGER_SAVED="mmc0"
  echo none > "$LED_DIR/trigger" 2>/dev/null
}

led_give_back() {
  [ -n "$TRIGGER_SAVED" ] && echo "$TRIGGER_SAVED" > "$LED_DIR/trigger" 2>/dev/null
}

dot()  { led_bright "$ON"; sleep "$DOT";  led_bright "$OFF"; sleep "$SYM_GAP"; }
dash() { led_bright "$ON"; sleep "$DASH"; led_bright "$OFF"; sleep "$SYM_GAP"; }

flash_sos() {
  led_take || return 1
  local i
  for ((i = 0; i < SOS_REPEATS; i++)); do
    dot; dot; dot;                 # S
    sleep "$LETTER_GAP"
    dash; dash; dash;              # O
    sleep "$LETTER_GAP"
    dot; dot; dot;                 # S
    if (( i < SOS_REPEATS - 1 )); then sleep "$WORD_GAP"; fi
  done
  led_bright "$OFF"
  led_give_back
}

expand_logs() {
  local p
  for p in "${LOGS[@]}"; do
    [ -f "$p" ] && printf '%s\n' "$p"
  done | sort -u
}

state_file_for() { echo "$STATE_DIR/$(echo "$1" | tr '/' '_').off"; }

# Scan all watched logs for new error lines. Sets NEW_ERRORS=1 if any are found,
# and prints the offending file and lines to stderr.
scan_once() {
  mkdir -p "$STATE_DIR" 2>/dev/null
  NEW_ERRORS=0
  local f sf off size chunk
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    sf="$(state_file_for "$f")"
    size=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [ -f "$sf" ]; then
      off=$(cat "$sf" 2>/dev/null || echo 0)
    elif [ "$SCAN_EXISTING" = "1" ]; then
      off=0
    else
      off=$size
    fi
    # A shrunk file means it was rotated or truncated; re-read from the top.
    [ "$off" -gt "$size" ] && off=0
    if [ "$size" -gt "$off" ]; then
      chunk="$(tail -c "+$((off + 1))" "$f" 2>/dev/null \
                | grep -aEi "$ERROR_REGEX" \
                | grep -aviE "$IGNORE_REGEX")"
      if [ -n "$chunk" ]; then
        NEW_ERRORS=1
        echo "sos_on_error: error(s) in $f:" >&2
        echo "$chunk" | sed 's/^/    /' >&2
      fi
    fi
    echo "$size" > "$sf" 2>/dev/null
  done < <(expand_logs)
}

MODE="${1:-}"
case "$MODE" in
  --test)
    flash_sos; exit $? ;;
  --list)
    expand_logs; exit 0 ;;
  ""|--loop|--once) : ;;
  *)
    echo "usage: $0 [--loop|--once|--test|--list]" >&2; exit 2 ;;
esac

# One instance at a time for the scanning modes (so two runs do not both drive the
# LED). --test/--list handled above are exempt. The writability test runs in a
# subshell so its stderr redirect stays scoped there; putting "2>/dev/null" on an
# `exec` with no command would redirect this whole script's stderr for good.
LOCK="/run/sos_on_error.lock"
if ! ( : >>"$LOCK" ) 2>/dev/null; then LOCK="/tmp/sos_on_error.lock"; fi
exec 9>>"$LOCK"
flock -n 9 || { echo "sos_on_error: another instance is running" >&2; exit 0; }

if [ "$MODE" = "--once" ]; then
  scan_once
  [ "${NEW_ERRORS:-0}" = "1" ] && flash_sos
  exit 0
fi

# Loop mode.
trap 'led_bright "$OFF" 2>/dev/null; led_give_back 2>/dev/null; exit 0' INT TERM
echo "sos_on_error: watching $(expand_logs | wc -l) log(s); poll ${POLL_INTERVAL}s; LED $LED_DIR" >&2
while true; do
  scan_once
  [ "${NEW_ERRORS:-0}" = "1" ] && flash_sos
  sleep "$POLL_INTERVAL"
done
