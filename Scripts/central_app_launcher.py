#!/usr/bin/python3
'''
This is a tool which coordinates the launching of various 2thprinting apps.
The goal is to try and generally minimize contention for the scanning interface
(which is the built-in hci0 used by the python BTC/BLE libraries).

BlueZ controls discovery through Adapter1.StartDiscovery. A passive Linux HCI
monitor supplies only advertising/scan-response and inquiry/EIR evidence to
both workers. Cached names and post-connection data never drive novelty skips.
'''
# Activate venv before any other imports
import os
import sys
from pathlib import Path
from handle_venv import activate_venv
activate_venv()

import argparse
import asyncio
import datetime
import subprocess
import socket
import threading
import time
import glob
from queue import Queue
from subprocess import TimeoutExpired
import traceback

# BlueZ controls discovery; raw HCI reports supply pre-connection evidence.
from dbus_fast import BusType, Variant
from dbus_fast.aio import MessageBus
from novelty.rules import AdvertisementEvidence, NoveltyRules
from novelty.discovery import open_monitor, parse_monitor

##################################################
# BEGIN TESTING TOGGLES
##################################################

BLE_thread_enabled = True
BTC_thread_enabled = True
Sniffle_thread_enabled = True

lmp2thprint_enabled = True # When True, the BTC worker runs DarkFirmware_VSC_LMP (BlueZ Realtek-VSC) against discovered BR/EDR devices to capture LMP PDUs. The legacy ESP32 Braktooth + FTDI path has been removed.
better_getter_enabled = True
# One switch for all reviewed pre-connection categories on BLE and BTC.
# False removes category skips entirely; success/retry limits still apply.
novelty_mode = True
btc_sdp_gatt_enabled = True # When True, runs Scripts/btc_sdp_gatt.py for SDP enumeration plus GATT-over-BR/EDR enumeration via BlueZ kernel L2CAP sockets. (It replaced the customized bluez-5.66 sdptool, which is gone.)

# Number of Sonoff dongles to reserve for Better_Getter.py (round-robin). Remaining
# dongles are allocated to Sniffle per the channel-separation rules in
# https://github.com/darkmentorllc/Blue2thprinting/issues/26
MAX_BG = 2

# Realtek custom-firmware adapter cycling via per-port USB power switching.
# Empirically, the DarkFirmware_real_i firmware on the Realtek dongle wedges
# after a handful of LMP scans — kernel logs `Bluetooth: hciX: command tx timeout`
# and subsequent connection attempts hang or fail immediately.
#
# We cycle PROACTIVELY by power-cycling the USB port via uhubctl (per-port
# power switching, PPPS). This is the ONLY mechanism that loses the firmware
# from controller RAM — USB unbind/rebind doesn't actually remove power, so
# the firmware persists and corrupts the kernel's btrtl init sequence
# (RTL_CHIP_SUBVER read at opcode 0xfc61 returns garbage). uhubctl off+on
# triggers a true cold-boot-like firmware load via btusb's probe path:
#   USB disconnect → new USB device → btrtl examining hci_ver/lmp_ver →
#   RTL: loading rtl_bt/rtl8761bu_fw.bin → fw version 0xdfc6d922.
#
# Requires: uhubctl installed (`apt install uhubctl`) and the dongle plugged
# into a hub that supports per-port power switching. Verified on Pi 4's built-in
# VL805 (USB ID 2109:3431) — PPPS works and is NOT ganged (other devices on
# the same hub stay powered).
#
# Tune LMP_SCANS_BEFORE_REALTEK_CYCLE based on your firmware's stability.
# Default 1 (= N-2 with empirical N=3) means cycle before every LMP probe.
LMP_SCANS_BEFORE_REALTEK_CYCLE = 1
REALTEK_BDADDR_SENTINEL = "13:37:13:37:13:37"  # set by DarkFirmware_real_i — identifies the Realtek hci across power cycles, regardless of chipset (RTL8761B, RTL8852BU, etc.)
REALTEK_FW_LOAD_TIMEOUT_S = 20  # max wait for firmware to load + BD address to settle after power-on
# After this many consecutive cycle failures (uhubctl missing, no PPPS, firmware
# load timeout), stop attempting to cycle for the rest of the launcher's lifetime.
REALTEK_MAX_CONSECUTIVE_CYCLE_FAILURES = 3
# The discovery side looks for this launcher's Realtek this often, and power
# cycles its port itself after this many looks in a row found the dongle on the
# port but without its address. The BTC worker only cycles before an LMP probe,
# so with no BR/EDR device left to probe a wedged dongle stayed dead.
REALTEK_WATCHDOG_INTERVAL_S = 15
REALTEK_WATCHDOG_MISSES = 2

print_skipped = True
print_verbose = True
print_finished_bdaddrs = True
sniffle_stdout_logging = False
sniffle_log_rotate_in_seconds = 3600 # This will create a new log every hour if timeout=3600

# END TESTING TOGGLES

# Place BDADDRs that you know will be traveling with you into this array,
# so that you don't waste time trying to get data about your own devices
# e.g. skip_these_addresses = ["AA:BB:CC:DD:EE:FF".lower()]
skip_these_addresses = []

device_connect_attempts = {}
max_connect_attempts = 3 # Failures remain capped across advertising updates/reappearance.
# Cumulative ceiling still protects against structural-map/value deferral retries.
device_total_attempts = {}
max_total_attempts = 10

# Last actual advertising/inquiry report, never a cached BlueZ property update.
device_last_seen = {}
# A queued candidate not heard for this long leaves its queue until it is heard
# again. BlueZ used to do this for the launcher: it removes a device it has not
# seen for TemporaryTimeout (30 s by default) and the launcher dropped it on
# InterfacesRemoved ("[DEL]"). When candidates began to come from the HCI
# monitor instead, nothing replaced that, so a candidate only ever left by
# success, a category skip or the retry limit. On the move the workers then
# spent their time on devices long out of range: on pi0-2 on 2026-11-17 the
# first Better Getter attempt came a median of 25 minutes after the device was
# first heard, and none of 716 attempts in 140 minutes succeeded.
# BR/EDR gets longer: a device is reported once per inquiry, and every LMP
# probe stops discovery for a Realtek power cycle.
CANDIDATE_STALE_S = {"BLE": 30, "BTC": 60}
DEPRIORITIZED_RECENCY_S = 60  # Covered-map value reads must still be nearby.

##################################################
# Paths resolved from this file's location so the repo works from any clone path.
##################################################

REPO_ROOT = Path(__file__).resolve().parent.parent
novelty_evidence = AdvertisementEvidence(NoveltyRules(REPO_ROOT / "Analysis/metadata/private"))
novelty_lock = threading.RLock()

default_cwd = f"{REPO_ROOT}/"

BG_exec_path = str(REPO_ROOT / "Scripts/BG/Better_Getter.py")
BG_output_pcap_path = str(REPO_ROOT / "Logs/BetterGetter")

# Standalone SDP + GATT-over-BR/EDR enumerator. Writes its own .btides files
# under Logs/btc_sdp_gatt/.
btc_sdp_gatt_path = str(REPO_ROOT / "Scripts/btc_sdp_gatt.py")
btc_sdp_gatt_log_dir = str(REPO_ROOT / "Logs/btc_sdp_gatt")

# LMP fingerprinting tool (BlueZ + Realtek custom firmware via Xeno VSC).
# Built from Scripts/DarkFirmware_VSC_LMP_src/ against the system libbluetooth.
# The binary locates <repo>/Logs from its own path, so it must stay in Scripts/.
darkfirmware_lmp_path = str(REPO_ROOT / "Scripts/DarkFirmware_VSC_LMP")
btides_lmp_dir = str(REPO_ROOT / "Logs/DarkFirmwareLMPLog")

btc2thprint_log_path = str(REPO_ROOT / "Logs/BTC_2THPRINT.log")
bgprint_log_path = str(REPO_ROOT / "Logs/GATTprint.log")
sdpprint_log_path = str(REPO_ROOT / "Logs/SDPprint.log")

sniffle_stdout_log_path = str(REPO_ROOT / "Logs/Sniffle_stdout.log")
sniffle_path = str(REPO_ROOT / "Sniffle/sniffle_receiver_rust")  # Rust drop-in replacement for Sniffle/python_cli/sniff_receiver.py
sniffle_pcap_log_folder = str(REPO_ROOT / "Logs/sniffle")

# Ensure the per-tool log directories exist before workers try to write into them.
# Without this a worker crashes with FileNotFoundError on its first device and
# takes its whole thread down silently; fresh clones and new hostnames would
# otherwise hit that on first use.
for _d in (BG_output_pcap_path, btides_lmp_dir, sniffle_pcap_log_folder, btc_sdp_gatt_log_dir):
    os.makedirs(_d, exist_ok=True)

# Define a dictionary to store BDADDRs and their RSSI values
ble_bdaddrs = {}
ble_bdaddrs_lock = threading.Lock()
btc_bdaddrs = {}
btc_bdaddrs_lock = threading.Lock()
# How often each LE address has been reported as "random" and as "public".
# Controllers occasionally report a random-address device with the public type
# (seen from both the Realtek and the Broadcom on pi0-2: the same iPhone, same
# payload, a few percent of its reports, empty scan responses included). Those
# are one device, not two: see _handle_discovery_report.
ble_address_types = {}

# Devices whose exact structural GATT map is already well covered. Their
# first Better_Getter pass commits handle/UUID data and exits before ATT_READ;
# they move here until normal discovery/value work has drained. Promotion
# records the address in gatt_force_read_bdaddrs so the reconnect cannot defer
# itself a second time.
ble_gatt_value_deprioritized_bdaddrs = {}
ble_gatt_value_deprioritized_bdaddrs_lock = threading.Lock()
gatt_force_read_bdaddrs = set()
GATT_VALUES_DEFERRED_EXIT_CODE = 0x2D

gatt_success_bdaddrs = {}
gatt_success_bdaddrs_lock = threading.Lock()
sdp_success_bdaddrs = {}
sdp_success_bdaddrs_lock = threading.Lock()
lmp2thprint_success_bdaddrs = {}
lmp2thprint_success_bdaddrs_lock = threading.Lock()

# Adapter-cycle coordination state. The BTC worker (a thread) cycles the Realtek
# dongle every LMP_SCANS_BEFORE_REALTEK_CYCLE LMP probes; the asyncio D-Bus
# discovery loop (running on the main thread) needs to reissue StartDiscovery
# afterward on the (possibly renumbered) hci.
_lmp_invocations_since_cycle = 0
_lmp_invocations_lock = threading.Lock()
# Set by BTC worker after a successful USB rebind + firmware reload; cleared by
# the asyncio loop once it reissues StartDiscovery on the new adapter path.
_realtek_cycle_pending = threading.Event()
# Tracks consecutive cycle failures. After REALTEK_MAX_CONSECUTIVE_CYCLE_FAILURES
# we stop attempting cycles (until the launcher restarts) — repeatedly USB-rebinding
# a non-responsive controller can accelerate the hard-wedge state.
_realtek_consecutive_cycle_failures = 0
_realtek_cycle_disabled = False

hostname = socket.gethostname()

#####################################################################################
# Single global serial port list for Sniffle sniffers or Better_Getter.py to share
#####################################################################################
#
base_dir = '/dev/serial/by-id'
# Note: this would need to be changed to use other TI dev boards instead. For now I won't support that for simplicity
pattern = 'usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus*'

# Allow --discovery-only to skip the (potentially 6-minute) Sniffle USB-serial probe
# at module load time, so smoke tests of the BlueZ D-Bus path don't have to wait for it.
_DISCOVERY_ONLY = "--discovery-only" in sys.argv
if _DISCOVERY_ONLY:
    Sniffle_thread_enabled = False
    better_getter_enabled = False

def _resolve_dongle_path(by_id_path):
    """Resolve a /dev/serial/by-id symlink to its underlying /dev/ttyUSB* device path."""
    relative = os.readlink(by_id_path)
    return os.path.abspath(os.path.join(os.path.dirname(by_id_path), relative))

# Safe defaults so other threads can reference these without crashing while the dongle-init
# thread (below) is still running. Anything that depends on a real value gates on the
# corresponding *_enabled flag, which the init thread flips off if no dongles are found.
matching_files = []
# Reserved dongle pools, populated by _init_serial_dongles(): the first MAX_BG matched
# dongles go to Better_Getter.py (round-robin), and the remainder go to Sniffle per the
# channel-separation rules in issue #26.
bg_dongles = []
sniffle_dongles = []

# Signaled by _init_serial_dongles() once it finishes scanning /dev/serial/by-id.
# main() blocks on this before starting the BLE/BTC/Sniffle worker threads, so workers
# only ever see fully-resolved feature flags + paths. The D-Bus discovery loop runs
# in parallel with this init, so device detection is NOT delayed by it.
sniffle_init_done = threading.Event()

def _init_serial_dongles():
    """Run the /dev/serial/by-id wait + glob logic for Sonoff (Sniffle/BetterGetter)
    USB-serial dongles in a background thread, then split the result into the BG and
    Sniffle pools.

    Splitting this off the import path is what lets the BlueZ D-Bus discovery loop come
    up immediately at @reboot even on hosts where /dev/serial/by-id is empty (which would
    otherwise stall the launcher for up to MAX_RETRY_COUNT*10 seconds). Sets
    sniffle_init_done when complete.
    """
    global matching_files, bg_dongles, sniffle_dongles
    global Sniffle_thread_enabled, better_getter_enabled
    try:
        if(Sniffle_thread_enabled or better_getter_enabled):
            # Wait up to 360 seconds for the kernel/udev to enumerate the USB-serial dongles
            # (this is because on Raspbian Bookworm the serial devices come up way late).
            retry_count = 0
            MAX_RETRY_COUNT = 360
            while(retry_count < MAX_RETRY_COUNT):
                if (not os.path.isdir(base_dir) or not os.access(base_dir, os.R_OK)):
                    retry_count += 10
                    if(print_verbose): print(f"_init_serial_dongles: /dev/serial/by-id may not be accessible yet. Sleeping 10 seconds.")
                    time.sleep(10)
                else:
                    break # It's accessible, try to access Sniffle dongles now
                if(retry_count == MAX_RETRY_COUNT):
                    print(f"_init_serial_dongles: The directory {base_dir} does not exist or is not accessible and we exceeded MAX_RETRY_COUNT seconds waiting for it. Ensure your dongles are connected.")
                    Sniffle_thread_enabled = False
                    better_getter_enabled = False

        if(Sniffle_thread_enabled or better_getter_enabled):
            full_pattern = os.path.join(base_dir, pattern)
            # Sort so BG/Sniffle assignment is stable across reboots / udev re-enumeration.
            matching_files = sorted(glob.glob(full_pattern))
            if(matching_files):
                resolved_dongles = [_resolve_dongle_path(p) for p in matching_files]

                # Cap MAX_BG at the number of dongles available so we don't accidentally
                # leave Sniffle starved when fewer dongles are present than configured.
                effective_max_bg = min(MAX_BG, len(resolved_dongles)) if better_getter_enabled else 0
                bg_dongles = resolved_dongles[:effective_max_bg]
                sniffle_dongles = resolved_dongles[effective_max_bg:]

                if(print_verbose):
                    print(f"MAX_BG = {MAX_BG}; effective_max_bg = {effective_max_bg}")
                    print(f"BG dongles ({len(bg_dongles)}): {bg_dongles}")
                    print(f"Sniffle dongles ({len(sniffle_dongles)}): {sniffle_dongles}")

                if(better_getter_enabled and not bg_dongles):
                    print("No dongles available for Better_Getter.py. Disabling better_getter_enabled.")
                    better_getter_enabled = False

                if(Sniffle_thread_enabled and not sniffle_dongles):
                    print("No dongles left for Sniffle after reserving MAX_BG dongles for BG. Disabling Sniffle_thread_enabled.")
                    Sniffle_thread_enabled = False
            else:
                print(f"No Sniffle adapters found, despite code having Sniffle_thread_enabled = True. Setting to False")
                Sniffle_thread_enabled = False
                better_getter_enabled = False
    finally:
        sniffle_init_done.set()

##################################################
# Realtek adapter (hci0) cycle helper — invoked from btc_thread_function before
# every Nth LMP probe to forestall the firmware "command tx timeout" wedge.
##################################################

_realtek_cycle_lock = threading.Lock()


def cycle_realtek_adapter():
    """One power cycle at a time: the BTC worker and the discovery watchdog can
    both ask for one."""
    with _realtek_cycle_lock:
        _cycle_realtek_adapter()


def _cycle_realtek_adapter():
    """Power-cycle the Realtek dongle's USB port via uhubctl, forcing a true
    cold-boot-like firmware reload.

    Required after every LMP_SCANS_BEFORE_REALTEK_CYCLE LMP probes because the
    DarkFirmware_real_i firmware wedges after a few injections. ONLY a real
    power cycle clears the firmware from controller RAM — USB unbind/rebind
    leaves power on and the firmware persists, corrupting the kernel's btrtl
    init sequence (`RTL_CHIP_SUBVER` read returns garbage instead of the
    chip's LMP subversion register, kernel marks the controller broken).

    Uses `uhubctl` PPPS (per-port power switching). Verified on Pi 4's built-in
    VL805 hub: power is actually cut to the target port, other ports stay on.

    Power cycle CAN renumber the HCI device (hciN -> hciM), so we re-resolve
    the Realtek by its known leetspeak BD address (REALTEK_BDADDR_SENTINEL)
    afterward and update _realtek_hci_current_path so the asyncio loop
    reattaches via _restart_discovery_after_cycle.

    Sets _realtek_cycle_pending on success so the asyncio D-Bus discovery loop
    reissues StartDiscovery on the (possibly new) adapter path. On
    REALTEK_MAX_CONSECUTIVE_CYCLE_FAILURES failures, disables further cycling
    for the rest of the launcher's lifetime.
    """
    global _realtek_consecutive_cycle_failures, _realtek_cycle_disabled

    if _realtek_cycle_disabled:
        return

    started_at = datetime.datetime.now()
    hub, port = find_realtek_hub_and_port()
    if hub is None:
        print(f"cycle_realtek_adapter: Realtek USB device not found in /sys/bus/usb/devices, skipping cycle at {started_at}")
        _realtek_consecutive_cycle_failures += 1
        _maybe_disable_cycling()
        return

    old_hci, old_path = find_realtek_hci()
    print(f"cycle_realtek_adapter: power-cycling Realtek at hub={hub} port={port} (was {old_path or 'unknown'}) at {started_at}")

    # uhubctl -a cycle: power off, brief delay, power on. Output captures the
    # PPPS confirmation in the log so we can audit later.
    try:
        result = subprocess.run(
            ["uhubctl", "-l", hub, "-p", port, "-a", "cycle"],
            check=False, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            print(f"cycle_realtek_adapter: uhubctl returned rc={result.returncode}; stderr: {result.stderr.strip()[:200]}")
            _realtek_consecutive_cycle_failures += 1
            _maybe_disable_cycling()
            return
    except FileNotFoundError:
        print("cycle_realtek_adapter: uhubctl is not installed; install with `sudo apt install uhubctl`. Disabling cycling.")
        _realtek_cycle_disabled = True
        return
    except Exception as e:
        print(f"cycle_realtek_adapter: uhubctl invocation failed: {e}")
        _realtek_consecutive_cycle_failures += 1
        _maybe_disable_cycling()
        return

    # Wait up to REALTEK_FW_LOAD_TIMEOUT_S for the kernel to re-enumerate the
    # device, btrtl to identify the chip, the firmware blob to load, and the
    # leetspeak BD address to settle. Cold boot here typically takes ~5s.
    new_hci, new_path = None, None
    deadline = time.monotonic() + REALTEK_FW_LOAD_TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(0.5)
        new_hci, new_path = find_realtek_hci()
        if new_hci:
            break
    if new_hci is None:
        print(f"cycle_realtek_adapter: WARN — Realtek hci with BD addr {REALTEK_BDADDR_SENTINEL} did not reappear within {REALTEK_FW_LOAD_TIMEOUT_S}s after power cycle; firmware load likely failed")
        _realtek_consecutive_cycle_failures += 1
        _maybe_disable_cycling()
        return

    # Bring the new hci up — bluetoothd should auto-Powered too, but belt+suspenders.
    subprocess.run(["hciconfig", new_hci, "up"], check=False, timeout=5)
    time.sleep(1)

    if new_path != old_path:
        print(f"cycle_realtek_adapter: Realtek renumbered: {old_path or 'unknown'} -> {new_path}")
    update_realtek_dbus_path(new_path)
    _realtek_cycle_pending.set()
    _realtek_consecutive_cycle_failures = 0
    print(f"cycle_realtek_adapter: complete; hci={new_hci} ({(datetime.datetime.now() - started_at).total_seconds():.1f}s elapsed)")


def _maybe_disable_cycling():
    """If we've hit REALTEK_MAX_CONSECUTIVE_CYCLE_FAILURES in a row, give up on
    cycling for the rest of the launcher's lifetime. Repeated USB rebinds against
    a wedged controller can push it from soft-wedge into the unrecoverable
    `Read reg16 failed (-110)` state that needs a host reboot."""
    global _realtek_cycle_disabled
    if _realtek_consecutive_cycle_failures >= REALTEK_MAX_CONSECUTIVE_CYCLE_FAILURES:
        _realtek_cycle_disabled = True
        print(f"cycle_realtek_adapter: DISABLED for the rest of this launcher run after {_realtek_consecutive_cycle_failures} consecutive failures; reboot the host to recover the Realtek adapter")


#####################################################################################
# Round-robin pool of dongles available to Better_Getter.py.
# Sized by MAX_BG. Multiple BG instances may run concurrently — one per dongle.
# Queue.get() blocks the BLE thread when all BG dongles are in flight, which is what
# rate-limits us to MAX_BG concurrent BG processes.
#
# Created empty here; populated by _start_workers_after_dongle_init() once
# _init_serial_dongles() has finished enumerating bg_dongles. The BLE worker doesn't
# start until that's done, so it never sees an empty queue at startup.
#####################################################################################
bg_dongle_queue = Queue()

# Per-BG-dongle consecutive non-zero-exit counter, keyed by /dev/ttyUSBN. Reset
# to 0 on a BG success or after a usbreset. The release path runs usbreset when
# this hits BG_CONSECUTIVE_FAILURE_THRESHOLD on a given path, independent of the
# elapsed-time fast-fail heuristic — Python interpreter cold-start on a Pi takes
# several seconds, so a "fast EIO at Serial open" actually surfaces as ~5-6s of
# wall time, indistinguishable from a normal connection failure by clock alone.
# A pure clock heuristic missed every wedge in practice; the counter catches
# them by their pattern instead.
# Safe to mutate without a lock because the bg_dongle_queue serializes access:
# only one ApplicationThread holds a given path between get() and put(), so a
# given key has at most one writer at any moment.
bg_dongle_consecutive_failures = {}
BG_CONSECUTIVE_FAILURE_THRESHOLD = 3

# Set of bdaddrs that currently have a BG worker running. The BLE thread's outer
# while-loop iterates the (possibly stale) ble_bdaddrs snapshot repeatedly, and
# when ble_bdaddrs has few entries the same bdaddr gets picked up again before
# the previous BG worker has finished. Without this gate, MAX_BG parallel BG
# workers would race CONNECT_IND to the same target — only one can win at a
# time, so the losers waste their dongle slot. NYC Day-2&3 logs showed 1,718
# bdaddrs with ≥2 BG attempts within a 5s window, worst case 6 parallel.
bg_inflight_bdaddrs = set()
bg_inflight_bdaddrs_lock = threading.Lock()
# Elapsed-time fast-path. cp210x EIO at Serial open + Python interpreter cold
# start typically completes in well under this on Pi-class hardware (observed
# 5-6s), while real GATT runs use most or all of the 20s timeout. False
# positives here cost only a 3s usbreset delay per BG run; a missed wedge
# burns up to max_total_attempts BLE addresses on a dead dongle.
BG_FAST_FAIL_S = 8.0

##################################################
# Log print helpers
##################################################

def tprint(msg):
    """Thread-safe single-write equivalent of print(msg).

    Built-in print() does two writes per call — the formatted text, then end='\\n'.
    With many worker threads all printing to the same stdout (BLE/BTC/Sniffle workers
    plus per-launch ApplicationThread instances), another thread's text can land
    between the two writes, producing garbled lines like
    'Released BG dongle X back to queueBLE: Acquired BG dongle Y for ...'.
    Bundling the newline into a single write makes the line atomic against any
    other writer that's also doing single-write emissions.
    """
    sys.stdout.write(msg + "\n")

# Cache of (path -> open file handle) reused across calls so we don't pay an
# open()+close() syscall pair per log line. NYC capture hit external_log_write
# ~108k times across GATTprint.log, BTC_2THPRINT.log, SDPprint.log, and
# Sniffle_stdout.log; pure overhead, no correctness change.
# O_APPEND on Linux already gives atomic appends across writers, but we still
# serialize via a lock so the cache map itself is thread-safe and the print()
# side-channel + file write happen as one logical event.
_external_log_files = {}
_external_log_files_lock = threading.Lock()

def external_log_write(log_path, fmt_str):
    try:
        with _external_log_files_lock:
            f = _external_log_files.get(log_path)
            if f is None:
                f = open(log_path, 'a')
                _external_log_files[log_path] = f
            print(f"\n{fmt_str}")  # newline before, makes the marker visible in stdout
            f.write(f"{fmt_str}\n")
            f.flush()
    except Exception as e:
        print("Exception occurred:", str(e))
        print(f"You need to determine why the {log_path} file couldn't be written, because the logs are useless without this write")
        quit()

##################################################
# Threading for launching background processes
##################################################

def locked_delete_from_dict(dict, lock, key):
    with lock:
        if(key in dict.keys()):
            del dict[key]

def all_2thprints_done(type, bdaddr):
   if(type == "BLE"):
       if(bdaddr in gatt_success_bdaddrs.keys()):
           return True
       else:
           return False
   if(type == "BTC"):
       if(bdaddr in sdp_success_bdaddrs.keys() and bdaddr in lmp2thprint_success_bdaddrs.keys()):
           return True
       else:
           return False

class ApplicationThread(threading.Thread):
    global serial_port_status
    def __init__(
        self,
        process,
        bdaddr,
        info_type,
        timeout,
        launch_cmd="",
        bg_dongle_path=None,
        gatt_device_state=None,
    ):
        threading.Thread.__init__(self)
        self.process = process
        self.timeout = timeout
        self.is_terminated = False
        self.bdaddr = bdaddr
        self.info_type = info_type
        self.launch_cmd = launch_cmd
        # When set, the GATT path returns this dongle to bg_dongle_queue on exit so
        # another BLE bdaddr can claim it next.
        self.bg_dongle_path = bg_dongle_path
        self.gatt_device_state = gatt_device_state
        # Wall-clock at thread construction. _run_inner uses elapsed time vs this
        # to detect "Better_Getter exited almost instantly with non-zero rc" — the
        # cp210x EIO-on-serial-open signature — and flag the dongle for usbreset
        # before returning it to the queue.
        self.started_at = datetime.datetime.now()
        self._bg_dongle_needs_usbreset = False

    def _release_bg_dongle(self):
        global _last_bg_uhubctl_cycle_at
        # Drop the in-flight marker first so a re-iteration of sorted_ble_bdaddrs
        # can pick this bdaddr up again on its next pass. Safe to do unconditionally —
        # discard() is a no-op for already-absent entries, e.g. non-GATT info_types
        # (LMP2thprint / SDP / BTC_SDP_GATT / Sniffle) which never set the marker.
        if self.info_type == "GATT" and self.bdaddr is not None:
            with bg_inflight_bdaddrs_lock:
                bg_inflight_bdaddrs.discard(self.bdaddr)
        if self.bg_dongle_path is not None:
            if self._bg_dongle_needs_usbreset:
                # EIO on serial open wedges the cp210x driver state until a USB-level
                # reset rebinds it. Without this, the same wedged dongle would come
                # straight back out of bg_dongle_queue on the next BLE pickup and burn
                # through up to max_total_attempts addresses before another BG dongle
                # happens to be the one handed out.
                consec = bg_dongle_consecutive_failures.get(self.bg_dongle_path, 0)
                tprint(f"BG: {self.bg_dongle_path} likely wedged ({consec} consecutive failures); running usbreset before re-queueing")
                ok = _usbreset_dongle(self.bg_dongle_path)
                if not ok:
                    # usbreset failing typically means the cp210x has fully detached
                    # from the kernel (USBDEVFS_RESET → ENODEV), beyond what driver-
                    # level recovery can clear. Fall back to a hub power-cycle, which
                    # forces the device to re-enumerate from scratch. Serialize across
                    # threads + cooldown so we don't cycle the same hub repeatedly
                    # while every dongle on it is mid-rebind from the prior cycle.
                    with _bg_uhubctl_cycle_lock:
                        now = time.monotonic()
                        if now - _last_bg_uhubctl_cycle_at < UHUBCTL_BG_COOLDOWN_S:
                            tprint(f"BG: usbreset of {self.bg_dongle_path} failed; skipping uhubctl (cooldown active, {now - _last_bg_uhubctl_cycle_at:.0f}s since last cycle)")
                        else:
                            tprint(f"BG: usbreset of {self.bg_dongle_path} failed; falling back to uhubctl power-cycle (will also bounce other dongles on the hub)")
                            # Set the timestamp BEFORE the cycle so concurrent
                            # ApplicationThread releases see the cooldown window
                            # immediately and don't pile on with their own cycles.
                            _last_bg_uhubctl_cycle_at = now
                            cycled = _uhubctl_cycle_for_tty(self.bg_dongle_path)
                            if cycled:
                                # The cycle just bounced every cp210x on the hub —
                                # any failures their threads racked up before the
                                # cycle are stale. Reset all counters so we don't
                                # immediately re-flag them on their next pickup.
                                for k in list(bg_dongle_consecutive_failures.keys()):
                                    bg_dongle_consecutive_failures[k] = 0
                            else:
                                # Cycle didn't actually happen (no PPPS ancestor,
                                # uhubctl missing, etc.). Don't hold the cooldown
                                # against future genuine attempts.
                                _last_bg_uhubctl_cycle_at = 0.0
                # Whether the recovery succeeded or not, clear THIS dongle's counter —
                # we tried what we could and shouldn't re-flag on the very next exit.
                bg_dongle_consecutive_failures[self.bg_dongle_path] = 0
            bg_dongle_queue.put(self.bg_dongle_path)
            if(print_verbose): tprint(f"Released BG dongle {self.bg_dongle_path} back to queue")

    def run(self):
        try:
            self._run_inner()
        finally:
            self._release_bg_dongle()

    def _run_inner(self):
        try:
            retCode = self.process.wait(self.timeout)
            if self.process.poll() is None:
                print(f"PID: {self.process.pid}: ApplicationThread: Shouldn't be able to get here. pid still running. Killing it")
                self.process.kill()
                self.process.wait() # This avoids defunct processes on Ubuntu 24.04
            else:
                print(f"PID: {self.process.pid}: ApplicationThread: {self.info_type} collection for {self.bdaddr} terminated on its own with return code {retCode}")
                if(retCode == 0): #Success!
                    if(self.info_type == "GATT"):
                       external_log_write(bgprint_log_path, f"BETTERGETTER SUCCESS FOR: {self.bdaddr} {datetime.datetime.now()}")
                       # A successful BG run on this dongle proves it isn't wedged.
                       # Reset the consecutive-failure counter so a long-stable
                       # dongle isn't forced through usbreset because of failures
                       # that happened earlier in the session.
                       if self.bg_dongle_path is not None:
                           bg_dongle_consecutive_failures[self.bg_dongle_path] = 0
                       with gatt_success_bdaddrs_lock:
                           gatt_success_bdaddrs[self.bdaddr] = 1
                           with ble_gatt_value_deprioritized_bdaddrs_lock:
                               ble_gatt_value_deprioritized_bdaddrs.pop(self.bdaddr, None)
                               gatt_force_read_bdaddrs.discard(self.bdaddr)
                           # Should only remove from ble_bdaddrs if all BLE-type prints are done
                           if(print_finished_bdaddrs): print(f"Successful GATTPrinting of {self.bdaddr}!")
                           if(all_2thprints_done("BLE", self.bdaddr)):
                               locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, self.bdaddr)
                               if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {self.bdaddr} from ble_bdaddrs!")
                    elif(self.info_type == "LMP2thprint"):
                       external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: SUCCESS FOR: {self.bdaddr} {datetime.datetime.now()}")
                       with lmp2thprint_success_bdaddrs_lock:
                           lmp2thprint_success_bdaddrs[self.bdaddr] = 1
                           if(print_finished_bdaddrs): print(f"Successful LMP2thprinting of {self.bdaddr}!")
                           if(all_2thprints_done("BTC", self.bdaddr)):
                               locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, self.bdaddr)
                               if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {self.bdaddr} from btc_bdaddrs!")
                    elif(self.info_type == "BTC_SDP_GATT"):
                       external_log_write(sdpprint_log_path, f"BTC_SDP_GATT SUCCESS FOR: {self.bdaddr} {datetime.datetime.now()}")
                       with sdp_success_bdaddrs_lock:
                           sdp_success_bdaddrs[self.bdaddr] = 1
                           if(print_finished_bdaddrs): print(f"Successful BTC_SDP_GATT of {self.bdaddr}!")
                           if(all_2thprints_done("BTC", self.bdaddr)):
                               locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, self.bdaddr)
                               if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {self.bdaddr} from btc_bdaddrs!")
                    elif(self.info_type == "Sniffle"):
                       external_log_write(sdpprint_log_path, f"SNIFFLE LAUNCH SUCCESS: {self.launch_cmd} {datetime.datetime.now()}")
                elif (
                    self.info_type == "GATT"
                    and retCode == GATT_VALUES_DEFERRED_EXIT_CODE
                ):
                    # Structural discovery succeeded and was written out, but
                    # this exact map is already value-covered. Do not count the
                    # intentional exit as a dongle failure. Remove it from the
                    # normal queue and preserve enough state for a later forced
                    # reconnect.
                    external_log_write(
                        bgprint_log_path,
                        f"BETTERGETTER VALUES DEFERRED FOR: "
                        f"{self.bdaddr} {datetime.datetime.now()}",
                    )
                    if self.bg_dongle_path is not None:
                        bg_dongle_consecutive_failures[self.bg_dongle_path] = 0
                    state = self.gatt_device_state
                    with ble_bdaddrs_lock:
                        state = ble_bdaddrs.pop(self.bdaddr, state)
                        with ble_gatt_value_deprioritized_bdaddrs_lock:
                            if state is not None:
                                ble_gatt_value_deprioritized_bdaddrs[self.bdaddr] = state
                            gatt_force_read_bdaddrs.discard(self.bdaddr)
                    # The structural pass is successful staging work, not a
                    # failed retry. Give the value phase its normal retry budget.
                    device_connect_attempts[self.bdaddr] = 0
                    device_total_attempts[self.bdaddr] = max(
                        0, device_total_attempts.get(self.bdaddr, 1) - 1
                    )
                    if print_finished_bdaddrs:
                        print(
                            f"Saved GATT handle/UUID map for {self.bdaddr}; "
                            "deferred readable values"
                        )
                else:
                    if(self.info_type == "GATT"):
                       external_log_write(bgprint_log_path, f"BETTERGETTER FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                       # Two independent triggers for usbreset, ORed together:
                       #   * elapsed_s < BG_FAST_FAIL_S — fast exit pattern, suggestive of
                       #     EIO at Serial open before any BLE work; observed Pi clock
                       #     time for that case is ~5-6s due to interpreter cold start.
                       #   * consecutive >= BG_CONSECUTIVE_FAILURE_THRESHOLD — repeated
                       #     non-zero exits on the same dongle regardless of timing,
                       #     covering wedges that don't fit the fast-fail signature.
                       if self.bg_dongle_path is not None:
                           elapsed_s = (datetime.datetime.now() - self.started_at).total_seconds()
                           consecutive = bg_dongle_consecutive_failures.get(self.bg_dongle_path, 0) + 1
                           bg_dongle_consecutive_failures[self.bg_dongle_path] = consecutive
                           if elapsed_s < BG_FAST_FAIL_S or consecutive >= BG_CONSECUTIVE_FAILURE_THRESHOLD:
                               self._bg_dongle_needs_usbreset = True
                    elif(self.info_type == "LMP2thprint"):
                       external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "BTC_SDP_GATT"):
                       external_log_write(sdpprint_log_path, f"BTC_SDP_GATT FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "Sniffle"):
                       external_log_write(sniffle_stdout_log_path, f"SNIFFLE LAUNCH FAILURE 0x{retCode:02x} FOR: {self.launch_cmd} {datetime.datetime.now()}")
                       # Release the port so the sniffle worker can relaunch.
                       # Without this the failed port would stay marked as
                       # in-use (pid of the dead process) for the whole
                       # launcher run — the 2026-05-04 bug. Flag for
                       # usbreset too: a non-zero exit from sniff_receiver
                       # right after launch is dominantly EIO on serial open
                       # (Errno 5), which the cp210x clears via a USB reset.
                       key = next((k for k, v in serial_port_status.items() if v == self.process.pid), None)
                       if key is not None:
                           with sniffle_state_lock:
                               serial_port_needs_usb_reset[key] = True
                               serial_port_pcap_last_seen.pop(key, None)
                           serial_port_status[key] = 0
                           with start_sniffle_threads_condition:
                               start_sniffle_threads_condition.notify()

            self.is_terminated = True
        except TimeoutExpired:
            if(print_verbose): print(f"PID: {self.process.pid}: ApplicationThread: TimeoutExpired")
            print(f"PID: {self.process.pid}: ApplicationThread: Killing pid")
            self.process.kill()
            self.process.wait() # This avoids defunct processes on Ubuntu 24.04
            self.is_terminated = True
            if(self.info_type == "GATT"):
               external_log_write(bgprint_log_path, f"BETTERGETTER FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")
               # Timeouts count toward the consecutive-failure threshold too —
               # the dongle was held for the full timeout and produced nothing,
               # which is itself a wedge symptom on a long enough streak.
               # Don't trigger the fast-fail leg here (a timeout is by
               # definition not fast).
               if self.bg_dongle_path is not None:
                   consecutive = bg_dongle_consecutive_failures.get(self.bg_dongle_path, 0) + 1
                   bg_dongle_consecutive_failures[self.bg_dongle_path] = consecutive
                   if consecutive >= BG_CONSECUTIVE_FAILURE_THRESHOLD:
                       self._bg_dongle_needs_usbreset = True
            elif(self.info_type == "LMP2thprint"):
               external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")
            elif(self.info_type == "BTC_SDP_GATT"):
               external_log_write(sdpprint_log_path, f"BTC_SDP_GATT FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")
            elif(self.info_type == "Sniffle"):
               external_log_write(sniffle_stdout_log_path, f"SNIFFLE TIMEOUT FOR: {self.launch_cmd} {datetime.datetime.now()}")
               # Re-set the status of the serial port to available so the sniffle thread relaunches it.
               # The role (scan vs follow + channel) is held in serial_port_role[key] and is preserved
               # across relaunches; we only need to flip the state from PID -> 0 (available).
               key = next((k for k, v in serial_port_status.items() if v == self.process.pid), None)
               if(key == None):
                   print(serial_port_status)
                   print("Unknown error occurred. Exiting")
                   exit(-1)
               if(print_verbose): print(f"self.process.pid = {self.process.pid}. Corresponding key in serial_port_status is {key}")
               serial_port_status[key] = 0
               if(print_verbose): print("Notifying sniffle_thread_function to wake up and re-launch a new process/thread for this serial port.")
               with start_sniffle_threads_condition:
                   start_sniffle_threads_condition.notify()

def launch_application(cmd, target_cwd, stdout=None, target=None):
    try:
        # Recheck immediately before spawning, including after a wait for a BG
        # dongle or LMP completion. A late scan response must cancel stale work.
        with novelty_lock:
            if target and _category_skip_reason(*target):
                return None
            process = subprocess.Popen(cmd, cwd=target_cwd, stdout=stdout)
        print(f"PID: {process.pid}: central_app_launcher.py: launched {cmd}")
#        raise BlockingIOError("FAKE I/O operation is blocked")
    except BlockingIOError as e:
        # Handle the exception gracefully, e.g., log the error and take appropriate action.
        print(f"launch_application: Caught BlockingIOError while launching application: {e}")
        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
        print(f"launch_application: UNRECOVERABLE ERROR. REBOOTING at {datetime.datetime.now()}")
        force_reboot()
        return None
    except Exception as e:
        # Handle other exceptions that might occur.
        print(f"launch_application: Caught an exception while launching application: {e}")
        force_reboot()
        return None

    return process

def force_reboot():
    print(f"UNRECOVERABLE ERROR. REBOOTING at {datetime.datetime.now()}")
    time.sleep(30) # TODO: for testing only. Deleteme
    os.system("sudo reboot")
    print("SLEEPING FOR SUPERSTITION!")
    time.sleep(30)
    os.system("sudo reboot")
    print("REBOOT STILL DIDN'T WORK?!")


##################################################
# BlueZ scan control with passive HCI discovery evidence
##################################################
# BlueZ still owns StartDiscovery/StopDiscovery. Only raw HCI advertising and
# inquiry/EIR reports populate the scheduler, so connected/cached names cannot
# become pre-connection evidence. See novelty/discovery.py.

ADAPTER_IFACE = "org.bluez.Adapter1"

# Realtek hci interface number, resolved dynamically by find_realtek_hci() — USB
# rebind during cycle_realtek_adapter() renumbers the device (hci0 -> hci2 -> ...),
# so we re-resolve each cycle. This is shared between the asyncio discovery loop
# and the BTC worker; protected by _realtek_path_lock for atomic updates.
_realtek_hci_current_path = "/org/bluez/hci0"
_realtek_path_lock = threading.Lock()

def _usb_device_present(sysfs_id):
    return os.path.isdir(f"/sys/bus/usb/devices/{sysfs_id}")


def _realtek_sysfs_id():
    """Return the Realtek dongle's USB sysfs id (e.g. '1-1.3' or '1-1.2.3'),
    derived from the hci interface's `device` symlink so it's chip-agnostic
    (works on RTL8761B `2550:8761`, RTL8852BU `0bda:a728`, etc.).

    The dongle can be on its port without its address. When its firmware stops
    answering, the kernel resets it ("command tx timeout", "Resetting usb
    device"), the firmware download then fails ("RTL: Read reg16 failed
    (-110)") and it reports 00:00:00:00:00:00. find_realtek_hci() no longer
    sees it, yet a power cycle of that port is exactly what brings it back
    (pi0-3, 2026-11-17: two seconds). So fall back to the port this launcher
    pinned, as long as a USB device is still there.
    """
    hci, _ = find_realtek_hci()
    if hci:
        sysfs_id = _hci_usb_id(hci)
    else:
        with _realtek_select_lock:
            sysfs_id = _realtek_pinned_usb
        if not sysfs_id or not _usb_device_present(sysfs_id):
            return None
    return sysfs_id if sysfs_id and "." in sysfs_id else None


def _hub_supports_ppps(hub):
    """uhubctl -l <hub> probe: True if PPPS-capable, False if ganged/unsupported."""
    try:
        result = subprocess.run(
            ["uhubctl", "-l", hub], capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "No compatible devices" not in result.stdout


def _only_realtek_under_subtree(subtree_prefix, realtek_sysfs_id):
    """Return True if the only NON-HUB USB device whose sysfs id is at-or-under
    <subtree_prefix> is the Realtek dongle. Used to safety-check walking up the
    hub tree: cycling an upstream port would cut power to ALL devices in its
    subtree, so we only do that if the Realtek is alone there."""
    realtek_real = os.path.realpath(f"/sys/bus/usb/devices/{realtek_sysfs_id}")
    # All sysfs dirs starting with the prefix. Match either exact prefix or
    # prefix followed by '.' or ':' (for USB interfaces, which we'll skip).
    for path in glob.glob(f"/sys/bus/usb/devices/{subtree_prefix}*"):
        sysfs_id = os.path.basename(path)
        # Skip USB interface dirs ("1-1.2:1.0") — only check device dirs.
        if ":" in sysfs_id:
            continue
        # Skip if sysfs_id is the candidate hub itself or its boundary.
        # The prefix needs to be followed by '.' or be exact match.
        if sysfs_id != subtree_prefix and not sysfs_id.startswith(subtree_prefix + "."):
            continue
        # Skip hubs (USB class 0x09) — we care about leaf devices like Sniffle
        # dongles, mouse, ethernet.
        try:
            with open(os.path.join(path, "bDeviceClass")) as f:
                dev_class = int(f.read().strip(), 16)
        except (FileNotFoundError, IOError, ValueError):
            continue
        if dev_class == 0x09:
            continue
        # Non-hub leaf device — must be the Realtek itself, or this candidate is unsafe.
        if os.path.realpath(path) != realtek_real:
            return False
    return True


def find_realtek_hub_and_port():
    """Return (hub_location, port_number) of the SAFEST PPPS-capable hub-port
    whose subtree contains only the Realtek dongle. Walks up from the
    Realtek's immediate parent hub looking for a candidate. Returns (None, None)
    if no safe candidate exists.

    Strategy:
      1. Try the immediate parent hub. If it supports PPPS, use it (precise,
         can't affect any other devices).
      2. If not, walk up one level at a time. At each level, accept the
         candidate ONLY IF (a) the hub supports PPPS, AND (b) the Realtek is
         the ONLY non-hub leaf USB device under the subtree we'd cut power to.
         The (b) check protects Sniffle dongles, ethernet, etc. on shared hubs.
      3. If we walk all the way up without finding a safe candidate, return
         (None, None) — cycling will be auto-disabled with a clear message.

    Examples on the test fleet:
      - .176 with Realtek directly on built-in VL805 (1-1.3): immediate parent
        1-1 is PPPS → use (1-1, 3).
      - .176 with Realtek behind a 1-port ganged hub (1-1.2.3, sole device):
        immediate parent ganged → walk up → 1-1 port 2 is PPPS and the subtree
        only contains the Realtek → use (1-1, 2).
      - .176 with Realtek behind a 4-port ganged hub also holding Sniffle
        dongles (1-1.1.2): immediate parent ganged → walk up → 1-1 port 1 is
        PPPS but subtree has Sniffle dongles → REFUSE.
      - .206 (Pi Zero W, Realtek behind a Genesys hub also holding Ethernet):
        immediate parent ganged → walk up → eventually candidate's subtree
        contains the Ethernet adapter → REFUSE."""
    sysfs_id = _realtek_sysfs_id()
    if not sysfs_id:
        return None, None
    parts = sysfs_id.split(".")
    if len(parts) < 2:
        return None, None
    # Try immediate parent first (no safety check needed — can't affect anything else).
    direct_hub = ".".join(parts[:-1])
    direct_port = parts[-1]
    if _hub_supports_ppps(direct_hub):
        return direct_hub, direct_port
    # Walk up. parts indexes: hub = parts[:i], port = parts[i], subtree = parts[:i+1].
    for i in range(len(parts) - 2, 0, -1):
        candidate_hub = ".".join(parts[:i])
        candidate_port = parts[i]
        subtree_prefix = ".".join(parts[:i + 1])
        if not _hub_supports_ppps(candidate_hub):
            continue
        if _only_realtek_under_subtree(subtree_prefix, sysfs_id):
            print(f"find_realtek_hub_and_port: walking up to ancestor (immediate parent {direct_hub} doesn't support PPPS, but {candidate_hub} port {candidate_port} does and only the Realtek is under that subtree)")
            return candidate_hub, candidate_port
        # Found a PPPS-capable candidate but its subtree has other devices — unsafe, keep walking.
    return None, None


def realtek_hub_supports_ppps():
    """Informational: True if find_realtek_hub_and_port() found a safe cycling
    target. Returns False if the dongle isn't visible, no ancestor supports PPPS,
    or the only PPPS-capable ancestors have other devices in their subtree."""
    hub, _ = find_realtek_hub_and_port()
    return hub is not None

# Which Realtek this launcher drives. DarkFirmware_real_i gives every dongle the
# same BD address, so on a host with several of them the address alone does not
# say which is which, and BlueZ registers an Adapter1 for only one of them. The
# launcher therefore remembers the USB port of the one it chose and keeps to it:
# after a power cycle the dongle comes back on that port, possibly as another
# hciN. Without this, the first poll after a cycle found one of the *other*
# dongles (pi0-2, 2026-11-17: hci4 -> hci3), BlueZ had no adapter for it, and
# discovery never resumed for the rest of the run.
_realtek_pinned_usb = None
_realtek_other_usb = set()
_realtek_select_lock = threading.Lock()


def _sentinel_hcis():
    """Every hciN carrying the DarkFirmware BD address, in `hciconfig` order.

    Parses `hciconfig` output rather than /sys/class/bluetooth/<hci>/address —
    that sysfs attribute is not exposed on Raspbian Bookworm 6.12 kernels, so
    the parse approach is the portable choice."""
    target = REALTEK_BDADDR_SENTINEL.lower()
    try:
        result = subprocess.run(["hciconfig"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    found, current_hci = [], None
    for line in result.stdout.splitlines():
        # Adapter section headers ("hciN:") are flush-left; property lines are tab-indented.
        if line and not line[0].isspace() and ":" in line:
            current_hci = line.split(":", 1)[0].strip()
        elif "BD Address:" in line and current_hci:
            # "    BD Address: 13:37:13:37:13:37  ACL MTU: ..." — first whitespace-separated
            # token after the label is the address.
            try:
                addr = line.split("BD Address:", 1)[1].strip().split()[0].lower()
            except IndexError:
                continue
            if addr == target:
                found.append(current_hci)
    return found


def _hci_usb_id(hci):
    """USB sysfs id of the device behind hciN (e.g. '1-1.4.4'), or None."""
    try:
        full_path = os.path.realpath(f"/sys/class/bluetooth/{hci}/device")
    except OSError:
        return None
    sysfs_id = os.path.basename(os.path.dirname(full_path))
    return sysfs_id or None


def _bluez_manages(hci):
    """Does bluetoothd expose an Adapter1 for hciN? None when it cannot be told."""
    try:
        result = subprocess.run(
            ["busctl", "--system", "get-property", "org.bluez", f"/org/bluez/{hci}",
             "org.bluez.Adapter1", "Address"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.returncode == 0


def find_realtek_hci():
    """Return ('hciN', '/org/bluez/hciN') for the Realtek custom-firmware dongle
    this launcher drives, or (None, None) if it is not present right now.

    Identified by the leetspeak BD address that DarkFirmware_real_i sets, which
    is stable across reboots and power cycles. With one such dongle that is all
    there is to it. With several, the one BlueZ manages is chosen the first
    time, and from then on only the dongle on that USB port is returned; while
    it is away (re-enumerating after a power cycle) the answer is (None, None),
    never one of the others. A dongle that turns up on a port not seen before
    is taken to be ours, moved."""
    global _realtek_pinned_usb
    candidates = _sentinel_hcis()
    if not candidates:
        return None, None
    ports = {hci: _hci_usb_id(hci) for hci in candidates}
    with _realtek_select_lock:
        if _realtek_pinned_usb is None:
            chosen = candidates[0]
            if len(candidates) > 1:
                managed = {hci: _bluez_manages(hci) for hci in candidates}
                if any(managed.values()):
                    chosen = next(hci for hci in candidates if managed[hci])
                elif all(answer is False for answer in managed.values()):
                    return None, None     # bluetoothd has not registered one yet; ask again
                others = sorted(port for hci, port in ports.items() if hci != chosen and port)
                print(f"find_realtek_hci: {len(candidates)} dongles carry {REALTEK_BDADDR_SENTINEL}; "
                      f"using {chosen} on USB {ports[chosen]} and leaving {others} alone")
                _realtek_other_usb.update(others)
            _realtek_pinned_usb = ports[chosen]
            return chosen, f"/org/bluez/{chosen}"
        for hci in candidates:
            if ports[hci] == _realtek_pinned_usb:
                return hci, f"/org/bluez/{hci}"
        moved = [hci for hci in candidates if ports[hci] not in _realtek_other_usb]
        if moved:
            _realtek_pinned_usb = ports[moved[0]]
            return moved[0], f"/org/bluez/{moved[0]}"
        return None, None

def get_realtek_dbus_path():
    """Thread-safe accessor for the current Realtek D-Bus path."""
    with _realtek_path_lock:
        return _realtek_hci_current_path

def update_realtek_dbus_path(new_path):
    """Thread-safe setter for the current Realtek D-Bus path."""
    global _realtek_hci_current_path
    with _realtek_path_lock:
        _realtek_hci_current_path = new_path

# Resolve the initial Realtek D-Bus path at launcher startup. If the dongle isn't
# detected (e.g., not yet enumerated), fall back to /org/bluez/hci0 — the
# discovery loop will retry and the cycle helper will re-resolve as needed.
def _initialize_realtek():
    global _realtek_hci_current_path, _realtek_cycle_disabled
    _initial_hci, _initial_path = find_realtek_hci()
    if _initial_path:
        _realtek_hci_current_path = _initial_path
        print(f"Realtek dongle resolved at startup: {_initial_path}")
        _initial_sysfs = _realtek_sysfs_id()
        _initial_hub, _initial_port = find_realtek_hub_and_port()
        if _initial_hub:
            print(f"Realtek hub {_initial_hub} port {_initial_port} supports PPPS — cycling will use uhubctl (Realtek sysfs id: {_initial_sysfs})")
        else:
            # No safe PPPS-capable candidate found by find_realtek_hub_and_port().
            # Disable cycling upfront so the BTC worker doesn't waste time invoking
            # uhubctl every probe just to fail.
            _realtek_cycle_disabled = True
            print(
                f"WARN: no safe PPPS-capable hub found for Realtek (sysfs {_initial_sysfs}). "
                f"Either the immediate parent hub is ganged/unsupported, or every PPPS-capable "
                f"ancestor would also cut power to other devices (Sniffle dongles, ethernet, etc.). "
                f"LMP cycling DISABLED for this run — move the dongle to a PPPS-capable hub with "
                f"no other devices on it (or directly into the Pi's built-in VL805 port) to enable cycling."
            )
    else:
        print(f"WARN: Realtek dongle not yet visible at startup (no hci with BD addr {REALTEK_BDADDR_SENTINEL}); defaulting to /org/bluez/hci0")

def _ble_address_type(bdaddr, reported=None):
    """The address type this LE address is really using: the one most of its
    reports carry (the first seen on a tie)."""
    votes = ble_address_types.get(bdaddr)
    return max(votes, key=votes.get) if votes else reported


def _category_skip_reason(kind, bdaddr, atype):
    if not novelty_mode:
        return None
    reasons = set(novelty_evidence.reasons(bdaddr, atype, kind))
    if kind == "BLE":
        # The same six octets reported under the other address type are the same
        # device with a mislabelled report, so what was heard there counts too.
        # (Two real devices sharing 48 bits do not happen; mislabelled reports do.)
        for other in tuple(ble_address_types.get(bdaddr, ())):
            if other != atype:
                reasons |= novelty_evidence.reasons(bdaddr, other, kind)
    return "novelty:" + ",".join(sorted(reasons)) if reasons else None


def _candidate_skip_reason(kind, bdaddr, atype):
    """Shared admission/selection gate; category off never disables history caps."""
    if bdaddr.lower() in skip_these_addresses:
        return "personal address"
    if all_2thprints_done(kind, bdaddr):
        return "already completed"
    if device_connect_attempts.get(bdaddr, 0) >= max_connect_attempts:
        return "retry limit"
    if device_total_attempts.get(bdaddr, 0) >= max_total_attempts:
        return "total retry limit"
    return _category_skip_reason(kind, bdaddr, atype)


def _drop_stale_candidate(kind, bdaddr):
    """Take a queued candidate that has gone quiet out of its queue.

    True if it was dropped. It comes back as [NEW] with its next advertisement
    or inquiry result, and keeps its attempt counts. A device Better Getter is
    connected to right now is left alone: it stops advertising meanwhile.
    """
    if kind == "BLE":
        with bg_inflight_bdaddrs_lock:
            if bdaddr in bg_inflight_bdaddrs:
                return False
    queue, lock = (ble_bdaddrs, ble_bdaddrs_lock) if kind == "BLE" else (btc_bdaddrs, btc_bdaddrs_lock)
    with lock:
        seen = device_last_seen.get(bdaddr)
        if seen is None or bdaddr not in queue:
            return False
        quiet = (datetime.datetime.now() - seen).total_seconds()
        if quiet <= CANDIDATE_STALE_S[kind]:
            return False
        del queue[bdaddr]
    if print_verbose:
        print(f"[DEL] {kind} {bdaddr} (not heard for {quiet:.0f}s)")
    return True


def _refund_attempt_if_not_probed(kind, bdaddr, atype):
    """Undo the attempt counted for a pass that launched nothing.

    The workers count an attempt before they know whether a probe will start.
    When the candidate was withdrawn in the meantime, or the last-moment
    category check refused the launch, no connection was tried, so it must not
    use up the device's retry budget.
    """
    queue, lock = (ble_bdaddrs, ble_bdaddrs_lock) if kind == "BLE" else (btc_bdaddrs, btc_bdaddrs_lock)
    with lock:
        still_queued = bdaddr in queue
    if still_queued and not _category_skip_reason(kind, bdaddr, atype):
        return
    _refund_attempt(bdaddr)


def _refund_attempt(bdaddr):
    if device_connect_attempts.get(bdaddr, 0) > 0:
        device_connect_attempts[bdaddr] -= 1
    if device_total_attempts.get(bdaddr, 0) > 0:
        device_total_attempts[bdaddr] -= 1


def _all_ble_candidates_in_flight():
    with ble_bdaddrs_lock:
        queued = set(ble_bdaddrs)
    with bg_inflight_bdaddrs_lock:
        return bool(queued) and queued <= bg_inflight_bdaddrs


def _handle_discovery_report(report):
    """Only raw advertising, scan response or inquiry/EIR can admit candidates.

    D-Bus Name/UUIDs may come from GATT, SDP or Remote Name Request. They are
    deliberately never fed to this function, even when novelty mode is off.

    An LE address is one candidate whatever address type a report gives it. The
    evidence of both types decides whether it is skipped, and it is probed with
    the type most of its reports carry: a stray "public" report for a random
    address must neither bring a skipped device back as a second, evidence-free
    candidate nor make Better_Getter connect with the wrong address type.
    """
    bdaddr, kind, atype = report.address, report.transport, report.address_type
    with novelty_lock:
        novelty_evidence.observe(bdaddr, atype, kind, report.frames)
        candidate_type = atype
        if kind == "BLE":
            votes = ble_address_types.setdefault(bdaddr, {})
            votes[atype] = votes.get(atype, 0) + 1
            candidate_type = _ble_address_type(bdaddr)
        reason = _candidate_skip_reason(kind, bdaddr, candidate_type)
    device_last_seen[bdaddr] = datetime.datetime.now()
    device_connect_attempts.setdefault(bdaddr, 0)
    device_total_attempts.setdefault(bdaddr, 0)
    queue, lock = (ble_bdaddrs, ble_bdaddrs_lock) if kind == "BLE" else (btc_bdaddrs, btc_bdaddrs_lock)
    with lock:
        queued = queue.get(bdaddr)
        if reason:
            if queued is not None:
                queue.pop(bdaddr, None)
            if kind == "BLE":
                with ble_gatt_value_deprioritized_bdaddrs_lock:
                    if ble_gatt_value_deprioritized_bdaddrs.pop(bdaddr, None) is not None:
                        gatt_force_read_bdaddrs.discard(bdaddr)
            if queued is not None and print_skipped:
                print(f"Skipped {kind} {bdaddr}: {reason}")
            return
        if queued is not None and queued[0] != candidate_type:
            # Queued while the other type was ahead; probe with the right one.
            queue[bdaddr] = queued = (candidate_type, queued[1])
        if kind == "BLE":
            with ble_gatt_value_deprioritized_bdaddrs_lock:
                deferred = ble_gatt_value_deprioritized_bdaddrs.get(bdaddr)
                if deferred is not None and deferred[0] != candidate_type:
                    ble_gatt_value_deprioritized_bdaddrs[bdaddr] = (candidate_type, deferred[1])
        if not report.connectable or atype != candidate_type:
            return
        state = (candidate_type, report.rssi)
        if kind == "BLE":
            with ble_gatt_value_deprioritized_bdaddrs_lock:
                if bdaddr in ble_gatt_value_deprioritized_bdaddrs:
                    ble_gatt_value_deprioritized_bdaddrs[bdaddr] = state
                    return
        is_new = queued is None
        queue[bdaddr] = state
    if is_new and print_verbose:
        print(f"[NEW] {kind} {bdaddr} ({candidate_type}, RSSI={report.rssi})")


async def _monitor_discovery(monitor):
    loop = asyncio.get_running_loop()
    while True:
        packet = await loop.sock_recv(monitor, 65541)
        if not packet:
            raise RuntimeError("HCI discovery monitor closed; refusing cached-property fallback")
        # One unexpected packet must not end discovery (and with it the whole
        # launcher) in the middle of a capture run. The old D-Bus router logged
        # and carried on the same way.
        try:
            path = get_realtek_dbus_path()
            index = int(path.rsplit("hci", 1)[1])
            for report in parse_monitor(packet, index):
                _handle_discovery_report(report)
        except Exception as e:
            print(f"_monitor_discovery: caught {type(e).__name__}: {e} (packet {packet[:64].hex()})")
            traceback.print_exc()


async def _resolve_adapter(bus, adapter_path):
    """Introspect the given /org/bluez/hciN path and return the Adapter1 interface."""
    adapter_intro = await bus.introspect("org.bluez", adapter_path)
    adapter_obj = bus.get_proxy_object("org.bluez", adapter_path, adapter_intro)
    return adapter_obj.get_interface(ADAPTER_IFACE)


async def _realtek_watchdog(misses):
    """One look at this launcher's Realtek. Returns the new count of looks in a
    row that found it missing.

    Missing while its USB device is still on the pinned port means the
    controller has lost its firmware (see _realtek_sysfs_id); after
    REALTEK_WATCHDOG_MISSES such looks the port is power cycled. A dongle that
    is not on the port at all (unplugged) is waited for, not counted as a
    failed cycle. A cycle already in progress is left to finish.
    """
    hci, _ = await asyncio.to_thread(find_realtek_hci)
    if hci or _realtek_cycle_disabled or _realtek_cycle_lock.locked():
        return 0
    if not await asyncio.to_thread(_realtek_sysfs_id):
        return 0
    misses += 1
    if misses < REALTEK_WATCHDOG_MISSES:
        return misses
    print(f"_realtek_watchdog: the Realtek is on its USB port without its {REALTEK_BDADDR_SENTINEL} address; "
          f"power-cycling it at {datetime.datetime.now()}")
    await asyncio.to_thread(cycle_realtek_adapter)
    return 0


async def _restart_discovery_after_cycle(bus):
    """Watch for adapter-cycle events from cycle_realtek_adapter() and reissue
    SetDiscoveryFilter + StartDiscovery on the (possibly renumbered) Realtek
    D-Bus path so adv-report flow resumes.

    Called as a cancellable side-task from dbus_discovery_loop.
    """
    idle = misses = 0
    while True:
        # A bounded async poll is cancellable; cancelling an executor wait on
        # Event.wait() otherwise hangs asyncio shutdown until the next USB cycle.
        while not _realtek_cycle_pending.is_set():
            await asyncio.sleep(0.25)
            idle += 0.25
            if idle >= REALTEK_WATCHDOG_INTERVAL_S:
                idle = 0
                misses = await _realtek_watchdog(misses)
        _realtek_cycle_pending.clear()
        idle = misses = 0
        # bluetoothd registers /org/bluez/hciN's Adapter1 interface a few
        # seconds AFTER find_realtek_hci() succeeds at the kernel level. A
        # fixed-3s sleep racey the registration ~55% of the time in the NYC
        # capture, with no retry — discovery was silently lost after every
        # other power cycle until the next cycle woke this coroutine again.
        # Retry with backoff (~26s total) before giving up; a subsequent
        # cycle's wakeup re-runs the loop and gets another shot.
        adapter_path = get_realtek_dbus_path()
        last_err = None
        for delay in (3, 2, 3, 5, 5, 8):
            await asyncio.sleep(delay)
            try:
                adapter = await _resolve_adapter(bus, adapter_path)
                await adapter.call_set_discovery_filter({
                    "Transport": Variant("s", "auto"),
                    "DuplicateData": Variant("b", True),
                })
                await adapter.call_start_discovery()
                print(f"_restart_discovery_after_cycle: StartDiscovery reissued on {adapter_path} at {datetime.datetime.now()}")
                last_err = None
                break
            except Exception as e:
                last_err = e
                # Re-read the path each retry in case the cycle renumbered
                # the hci between attempts (rare but observed).
                adapter_path = get_realtek_dbus_path()
        if last_err is not None:
            print(f"_restart_discovery_after_cycle: gave up reissuing on {adapter_path} after ~26s; last error: {last_err}")


async def dbus_discovery_loop():
    """Run BlueZ D-Bus discovery forever. Replaces the bluetoothctl-log inotify loop."""
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    # Retry-resolve the Realtek hci. bluetoothd can lag a few seconds behind
    # kernel hci registration, and a freshly power-cycled dongle may take
    # 20–60s to re-enumerate. We poll indefinitely (with progressively quieter
    # warnings) rather than time out into a fallback adapter, because falling
    # through to the module-load default of /org/bluez/hci0 silently runs
    # discovery on the Pi's built-in Cypress instead of the Realtek — observed
    # in the 2026-05-07 23:43 NYC capture, where it masked an absent Realtek
    # for 70 minutes until the next launcher restart.
    attempt = 0
    while True:
        hci, path = find_realtek_hci()
        if path:
            update_realtek_dbus_path(path)
            break
        if attempt == 0:
            print(f"dbus_discovery_loop: waiting for Realtek dongle ({REALTEK_BDADDR_SENTINEL}) to appear...")
        elif attempt % 30 == 0:  # every 60s
            print(f"dbus_discovery_loop: STILL waiting for Realtek dongle "
                  f"({REALTEK_BDADDR_SENTINEL}) after {attempt * 2}s — refusing to "
                  f"start discovery on a fallback adapter; check the dongle, USB hub, "
                  f"and DarkFirmware_real_i firmware load")
        attempt += 1
        await asyncio.sleep(2)
    adapter_path = get_realtek_dbus_path()
    adapter = await _resolve_adapter(bus, adapter_path)

    # Open the passive monitor before StartDiscovery so the first reports count.
    # Failure is fatal: cached Device1 names/UUIDs cannot satisfy the on-air policy.
    try:
        monitor = open_monitor()
    except BaseException:
        bus.disconnect()
        raise
    monitor_task = asyncio.create_task(_monitor_discovery(monitor))

    restart_task = None
    try:
        # BlueZ retains radio ownership. The monitor only observes HCI traffic.
        await adapter.call_set_discovery_filter({
            "Transport": Variant("s", "auto"),
            "DuplicateData": Variant("b", True),
        })
        await adapter.call_start_discovery()
        print(f"dbus_discovery_loop: StartDiscovery on {adapter_path} succeeded at {datetime.datetime.now()}")
        restart_task = asyncio.create_task(_restart_discovery_after_cycle(bus))
        await monitor_task
    finally:
        monitor_task.cancel()
        if restart_task:
            restart_task.cancel()
        await asyncio.gather(*(t for t in (monitor_task, restart_task) if t), return_exceptions=True)
        monitor.close()
        try:
            adapter = await _resolve_adapter(bus, get_realtek_dbus_path())
            await adapter.call_stop_discovery()
        except Exception:
            pass
        bus.disconnect()


##################################################
# BLE-handling thread
##################################################

def reprioritize_ble_gatt_value_bdaddr(bdaddr):
    """Promote one covered-map device for a forced value-reading reconnect."""
    with ble_bdaddrs_lock:
        with ble_gatt_value_deprioritized_bdaddrs_lock:
            state = ble_gatt_value_deprioritized_bdaddrs.pop(bdaddr, None)
            if state is None:
                return False
            if _candidate_skip_reason("BLE", bdaddr, state[0]):
                gatt_force_read_bdaddrs.discard(bdaddr)
                return False
            ble_bdaddrs[bdaddr] = state
            gatt_force_read_bdaddrs.add(bdaddr)
    print(
        f"Reprioritized {state[0]} {bdaddr} ({state[1]}) for forced "
        "GATT characteristic-value reads"
    )
    return True


def _promote_ble_fallbacks_for_capacity():
    """Fill otherwise-idle BG slots without jumping ready normal work."""
    available_slots = bg_dongle_queue.qsize()
    if available_slots <= 0:
        return
    with bg_inflight_bdaddrs_lock:
        inflight = set(bg_inflight_bdaddrs)
    with ble_bdaddrs_lock:
        ready_normal = sum(1 for bdaddr in ble_bdaddrs if bdaddr not in inflight)
    slots_to_fill = max(0, available_slots - ready_normal)
    if slots_to_fill == 0:
        return

    cutoff = datetime.datetime.now() - datetime.timedelta(
        seconds=DEPRIORITIZED_RECENCY_S
    )
    for _ in range(slots_to_fill):
        with ble_gatt_value_deprioritized_bdaddrs_lock:
            value_candidates = sorted(
                (
                    (bdaddr, state[1])
                    for bdaddr, state in
                    ble_gatt_value_deprioritized_bdaddrs.items()
                    if device_last_seen.get(bdaddr, datetime.datetime.min) >= cutoff
                ),
                key=lambda item: item[1],
                reverse=True,
            )
        if value_candidates:
            reprioritize_ble_gatt_value_bdaddr(value_candidates[0][0])
            continue
        break


# Function for the first thread
def ble_thread_function():
    global device_connect_attempts, device_total_attempts
    ble_external_tool_threads = []
    while True:
        # If fewer ready normal addresses exist than currently-free BG dongles,
        # fill the spare capacity from covered-map value reads. With N dongles and N-1 ready normal
        # devices this intentionally starts one deferred device in parallel.
        _promote_ble_fallbacks_for_capacity()
        # Get the BDADDRs sorted in descending order of their RSSI, so we process higher RSSI first.
        # Snapshot under lock to avoid 'dictionary changed size during iteration' against the
        # HCI discovery callbacks which run on the asyncio main thread.
        with ble_bdaddrs_lock:
            sorted_ble_bdaddrs = sorted(ble_bdaddrs.keys(), key=lambda x: ble_bdaddrs[x][1], reverse=True)

        if(print_verbose):
            print(f"Begin loop through sorted_ble_bdaddrs {datetime.datetime.now()}")
            print(f"sorted_ble_bdaddrs = {sorted_ble_bdaddrs}")

        skip_count = int(0)
        launched_this_pass = False
        for bdaddr in sorted_ble_bdaddrs:
            # Skip devices that may be traveling with us, to not waste time on them
            # Only try collecting data from a given bd_addr max_connect_attempts times before skipping forever thereafter
            # This is so that we don't waste time trying to get info from something that will never give it to us,
            # when we could be spending that time trying new devices
            with ble_bdaddrs_lock:
                state = ble_bdaddrs.get(bdaddr)
            if state is None:
                continue
            if _drop_stale_candidate("BLE", bdaddr):
                continue
            total_for_addr = device_total_attempts.get(bdaddr, 0)
            reason = _candidate_skip_reason("BLE", bdaddr, state[0])
            if reason:
                if(print_skipped):
                    print(f"BLE: Skipped {bdaddr}: {reason}")
                skip_count += 1
                if(print_skipped):
                    print(f"BLE: skip_count = {skip_count} of {len(sorted_ble_bdaddrs)}")

                # Delete it otherwise it will just keep coming up over and over again in the while True loop
                locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, bdaddr)

                if(skip_count == len(sorted_ble_bdaddrs)):
                    _promote_ble_fallbacks_for_capacity()

                continue
            # A Better_Getter run still in flight for this address is the same
            # attempt, not a new one. Counting it again let a single 20-second
            # run use up the whole retry budget whenever a spare dongle let this
            # loop come back round, and nothing resets that budget any more.
            with bg_inflight_bdaddrs_lock:
                if bdaddr in bg_inflight_bdaddrs:
                    continue
            device_connect_attempts[bdaddr] += 1
            device_total_attempts[bdaddr] = total_for_addr + 1

            if(print_verbose): print(f"BLE Address: {bdaddr}")

            if(better_getter_enabled):
                skip_sub_process = False
                with gatt_success_bdaddrs_lock:
                    if(bdaddr in gatt_success_bdaddrs.keys()):
                        if(print_finished_bdaddrs): print(f"We've already successfully GATTprinted {bdaddr}! Skipping!")
                        # Remove it from further consideration (it could have just been added in by a [DEL] -> [NEW] sequence)
                        if(all_2thprints_done("BLE", bdaddr)):
                            locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, bdaddr)
                            if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {bdaddr} from ble_bdaddrs!")
                        continue

                # We have to check whether bdaddr is still in ble_bdaddrs because it could have been deleted via finding a [DEL] in the bluetoothctl log
                # This is a race condition...
                if(not skip_sub_process and bdaddr in ble_bdaddrs):
                    # Acquire the next available BG dongle. Blocks here when all MAX_BG dongles
                    # are already running a Better_Getter.py process, which gives us natural
                    # round-robin distribution across the BG pool (Queue is FIFO).
                    bg_dongle_path = bg_dongle_queue.get()
                    if(print_verbose): tprint(f"BLE: Acquired BG dongle {bg_dongle_path} for {bdaddr}")
                    # That wait can be long, and the candidate may have gone quiet in it.
                    if _drop_stale_candidate("BLE", bdaddr):
                        bg_dongle_queue.put(bg_dongle_path)
                        _refund_attempt(bdaddr)
                        continue

                    # Single-attempt-per-bdaddr gate. If another worker is already
                    # running a BG against this bdaddr (which happens when the outer
                    # while-loop re-iterates a small ble_bdaddrs while the previous
                    # BG is still in flight), release the dongle and move on. Without
                    # this gate the NYC capture observed up to 6 parallel BG inits on
                    # one target — only one can win the CONNECT_IND race, the rest
                    # tie up dongles. ApplicationThread._release_bg_dongle clears
                    # the bdaddr from the set on completion.
                    with bg_inflight_bdaddrs_lock:
                        already_running = bdaddr in bg_inflight_bdaddrs
                        if not already_running:
                            bg_inflight_bdaddrs.add(bdaddr)
                    if already_running:
                        if(print_verbose): tprint(f"BLE: BG worker already in flight for {bdaddr}; releasing {bg_dongle_path}")
                        bg_dongle_queue.put(bg_dongle_path)
                        _refund_attempt(bdaddr)
                        continue

                    # Pre-initialize so that if open(sniffle_append_stdout) below
                    # raises before launch_application returns, the gatt_process
                    # check at line ~1450 sees None rather than a stale Popen
                    # handle from a previous loop iteration.
                    gatt_process = None
                    launched_thread = None
                    with ble_bdaddrs_lock:
                        if(bdaddr in ble_bdaddrs):
                            external_log_write(bgprint_log_path, f"BETTERGETTER ATTEMPT FOR: {bdaddr} {datetime.datetime.now()}")
                            (type, rssi) = ble_bdaddrs[bdaddr]
                            current_time = datetime.datetime.now()
                            launch_time = current_time.strftime('%Y-%m-%d-%H-%M-%S')
                            pcap_output = f"-o={BG_output_pcap_path}/{launch_time}_{bdaddr}_BG_{hostname}.pcap"
                            serial_port = f"-s={bg_dongle_path}"
                            # -u for unbuffered python output (so it streams to log realtime)
                            if(type != "random"):
                                gatt_cmd = ["python3", "-u", BG_exec_path, "-q", serial_port, pcap_output, f"-b={bdaddr}", "-P", "-2"]
                            else:
                                gatt_cmd = ["python3", "-u", BG_exec_path, "-q", serial_port, pcap_output, f"-b={bdaddr}", "-2"]
                            # Skip-apple is one of the skipping mechanisms novelty mode
                            # switches on: with -A, BG early-exits (rc 0x0A) as soon as it
                            # confirms an Apple device from the advertisement Company ID,
                            # LL_VERSION_IND or the GATT Manufacturer Name. It backs up the
                            # advertisement rules for an Apple device they did not catch.
                            # Off means no skipping at all, so no -A either.
                            if(novelty_mode):
                                gatt_cmd.append("-A")
                            with ble_gatt_value_deprioritized_bdaddrs_lock:
                                force_value_reads = bdaddr in gatt_force_read_bdaddrs
                            if force_value_reads:
                                gatt_cmd.append("--force-read-values")
                                external_log_write(
                                    bgprint_log_path,
                                    f"BETTERGETTER FORCED VALUE ATTEMPT FOR: "
                                    f"{bdaddr} {datetime.datetime.now()}",
                                )
                            try:
                                stdout_path = f"{BG_output_pcap_path}/Sniffle_stdout.log" if sniffle_stdout_logging else "/dev/null"
                                with open(stdout_path, "a") as sniffle_append_stdout:
                                    gatt_process = launch_application(gatt_cmd, default_cwd, stdout=sniffle_append_stdout, target=("BLE", bdaddr, type))
                            except BlockingIOError as e:
                                print(f"Caught BlockingIOError while launching GATT application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                                # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                                force_reboot()
                            except Exception as e:
                                print(f"Caught an exception while launching GATT application: {e}")
                                # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                                force_reboot()
                            if(gatt_process != None):
                                gatt_thread = ApplicationThread(
                                    gatt_process,
                                    bdaddr,
                                    info_type="GATT",
                                    timeout=20,
                                    bg_dongle_path=bg_dongle_path,
                                    gatt_device_state=(type, rssi),
                                ) # Unfortunately I found some device that can take ~21 sec(!) even when tested manually
                                try:
                                    gatt_thread.start()
                                    launched_thread = gatt_thread
                                    launched_this_pass = True
                                    ble_external_tool_threads.append(gatt_thread)
                                except Exception as e:
                                    print(f"Caught an exception while starting GATT thread: {e}")
                                    # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                                    force_reboot()

                    # If we never started a thread (race with [DEL] removed bdaddr, or Popen
                    # failed silently), the dongle would otherwise be lost from the pool — return it.
                    # Also drop the in-flight marker since no worker exists to clear it later.
                    if(launched_thread is None):
                        with bg_inflight_bdaddrs_lock:
                            bg_inflight_bdaddrs.discard(bdaddr)
                        bg_dongle_queue.put(bg_dongle_path)
                        _refund_attempt_if_not_probed("BLE", bdaddr, state[0])
                        if(print_verbose): tprint(f"BLE: No GATT thread started for {bdaddr}; returned BG dongle {bg_dongle_path} to queue")

            # Reap any finished threads to bound memory growth, but do NOT block on running ones —
            # the bg_dongle_queue handles back-pressure (BLE thread blocks on queue.get() when all
            # MAX_BG dongles are in flight). Joining here would serialize launches and defeat
            # round-robin parallelism when MAX_BG > 1.
            ble_external_tool_threads = [t for t in ble_external_tool_threads if not t.is_terminated]

        print(f"Finished one complete loop through sorted_ble_bdaddrs {datetime.datetime.now()}")

        # Every queued address is still being probed and this pass started nothing:
        # wait quietly for a run to finish or a new candidate to arrive, instead of
        # spinning through the loop (and the log) once per iteration.
        while(not launched_this_pass and _all_ble_candidates_in_flight()):
            _promote_ble_fallbacks_for_capacity()
            time.sleep(1)

        # Sleep-poll until the dictionary has entries to process before proceeding again.
        # The original 'while ... pass' busy-wait was tolerable when the main thread blocked
        # on inotify syscalls for discovery, but with the new asyncio D-Bus discovery loop
        # running on the main thread it caused CPU starvation under the GIL — D-Bus signal
        # callbacks couldn't run, ble_bdaddrs never got populated, and the worker spun forever.
        while(len(ble_bdaddrs) == 0):
            _promote_ble_fallbacks_for_capacity()
            time.sleep(1)


##################################################
# BTC-handling thread
##################################################

# Function for the second thread
def btc_thread_function():
    global device_connect_attempts, device_total_attempts
    btc_external_tool_threads = []
    while True:
        # Get the BDADDRs sorted in descending order of their RSSI, so we process higher RSSI first.
        # Snapshot under lock to avoid 'dictionary changed size during iteration' against the
        # HCI discovery callbacks which run on the asyncio main thread.
        with btc_bdaddrs_lock:
            sorted_btc_bdaddrs = sorted(btc_bdaddrs.keys(), key=lambda x: btc_bdaddrs[x][1], reverse=True)

        if(print_verbose):
            print(f"Begin loop through sorted_btc_bdaddrs {datetime.datetime.now()}")
            print(f"sorted_btc_bdaddrs = {sorted_btc_bdaddrs}")

        skip_count = 0
        for bdaddr in sorted_btc_bdaddrs:
            # Skip devices that may be traveling with us, to not waste time on them
            # Only try collecting data from a given bd_addr max_connect_attempts times before skipping forever thereafter
            # This is so that we don't waste time trying to get info from something that will never give it to us,
            # when we could be spending that time trying new devices
            with btc_bdaddrs_lock:
                state = btc_bdaddrs.get(bdaddr)
            if state is None:
                continue
            if _drop_stale_candidate("BTC", bdaddr):
                continue
            total_for_addr = device_total_attempts.get(bdaddr, 0)
            reason = _candidate_skip_reason("BTC", bdaddr, state[0])
            if reason:
                if(print_skipped):
                    print(f"BTC: Skipped {bdaddr}: {reason}")
                skip_count += 1
                if(print_skipped):
                    print(f"BTC: skip_count = {skip_count} of {len(sorted_btc_bdaddrs)}")
                # Delete it otherwise it will just keep coming up over and over again in the while True loop
                locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)

                continue
            else:
                device_connect_attempts[bdaddr] += 1
                device_total_attempts[bdaddr] = total_for_addr + 1

            # Track the LMP thread (if launched) so we can wait for it to finish
            # before the SDP path opens an L2CAP socket to the same target. Both
            # paths go through the same Realtek HCI adapter and would otherwise
            # race the same ACL link setup — observed 482 "Failed to create
            # connection: I/O error" + 445 SDP EBUSY events in the NYC capture.
            lmp_thread_to_join = None
            launched_btc_probe = False

            if(lmp2thprint_enabled):
                skip_sub_process = False
                with lmp2thprint_success_bdaddrs_lock:
                    if(bdaddr in lmp2thprint_success_bdaddrs.keys()):
                        if(print_finished_bdaddrs): print(f"We've already successfully LMP2thprinted {bdaddr}! Skipping!")
                        # Remove it from further consideration (it could have just been added in by a [DEL] -> [NEW] sequence)
                        if(all_2thprints_done("BTC", bdaddr)):
                            locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)
                            if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {bdaddr} from btc_bdaddrs!")
                        skip_sub_process = True # We can't just 'continue' here for generalism, for if we add more stuff beyond this

                if(not skip_sub_process and bdaddr in btc_bdaddrs): # Double check that bdaddr hasn't been deleted out of btc_bdaddrs by a [DEL]
                    # Preemptively cycle hci0 every LMP_SCANS_BEFORE_REALTEK_CYCLE
                    # LMP probes to forestall the Realtek firmware "command tx
                    # timeout" wedge — see cycle_realtek_adapter() for details.
                    global _lmp_invocations_since_cycle
                    with _lmp_invocations_lock:
                        do_cycle = _lmp_invocations_since_cycle >= LMP_SCANS_BEFORE_REALTEK_CYCLE
                        if do_cycle:
                            _lmp_invocations_since_cycle = 0
                        _lmp_invocations_since_cycle += 1
                    if do_cycle:
                        cycle_realtek_adapter()
                        # The cycle takes several seconds. A report in that time can
                        # have withdrawn the candidate (a late EIR naming a skipped
                        # category, say). launch_application() would refuse it
                        # anyway, but only after BTC_2THPRINT.log had recorded an
                        # attempt that never happened (pi0-2, 2026-11-17).
                        with btc_bdaddrs_lock:
                            withdrawn = bdaddr not in btc_bdaddrs
                        if withdrawn or _category_skip_reason("BTC", bdaddr, state[0]):
                            _refund_attempt(bdaddr)
                            continue

                    lmp_hci = None
                    if _realtek_other_usb:
                        # Several DarkFirmware dongles: the tool picks one by
                        # manufacturer id, so name the one this launcher drives.
                        # If that one is away, send nothing: without --hci the tool
                        # would use another dongle, or the built-in adapter.
                        lmp_hci, _ = find_realtek_hci()
                        if not lmp_hci:
                            print(f"BTC: this launcher's Realtek is away; not probing {bdaddr} through another adapter")
                            _refund_attempt(bdaddr)
                            continue

                    external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: LOG ENTRY FOR BDADDR: {bdaddr} {datetime.datetime.now()}")
                    # The launcher already runs as root (via setup_capture_helper_debian-based.sh's
                    # @reboot cron entry under root), so we don't prefix with sudo.
                    btc_2thprint_cmd = [darkfirmware_lmp_path, f"--target={bdaddr}"]
                    if lmp_hci:
                        btc_2thprint_cmd.append(f"--hci={lmp_hci}")
                    btc_2thprint_process = None
                    try:
                        btc_2thprint_process = launch_application(btc_2thprint_cmd, default_cwd, target=("BTC", bdaddr, "public"))
                    except BlockingIOError as e:
                        print(f"Caught BlockingIOError while launching LMP2thprint application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()
                    except Exception as e:
                        print(f"Caught an exception while launching LMP2thprint application: {e}")
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()
                    if(btc_2thprint_process != None):
                        btc_2thprint_thread = ApplicationThread(btc_2thprint_process, bdaddr, info_type="LMP2thprint", timeout=15)
                        try:
                            btc_2thprint_thread.start()
                            btc_external_tool_threads.append(btc_2thprint_thread)
                            lmp_thread_to_join = btc_2thprint_thread
                            launched_btc_probe = True
                        except Exception as e:
                            print(f"Caught an exception while starting LMP2thprint thread: {e}")
                            # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                            force_reboot()

            # Wait for the LMP probe to finish before we open an L2CAP/SDP socket
            # to the same bdaddr on the same Realtek. The cross-tool collisions
            # (l2cap_connect EIO + SDP EBUSY in 927 NYC events) were caused by
            # the previous concurrent launch.
            if lmp_thread_to_join is not None:
                lmp_thread_to_join.join()

            # SDP path: btc_sdp_gatt.py, which also does GATT-over-BR/EDR. It feeds
            # sdp_success_bdaddrs, which all_2thprints_done() reads.
            if(btc_sdp_gatt_enabled):
                skip_sub_process = False
                with sdp_success_bdaddrs_lock:
                    if(bdaddr in sdp_success_bdaddrs.keys()):
                        if(print_finished_bdaddrs): print(f"We've already successfully SDPPrinted {bdaddr}! Skipping!")
                        if(all_2thprints_done("BTC", bdaddr)):
                            locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)
                            if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {bdaddr} from btc_bdaddrs!")
                        skip_sub_process = True

                if(not skip_sub_process and bdaddr in btc_bdaddrs):
                    external_log_write(sdpprint_log_path, f"BTC_SDP_GATT ATTEMPT FOR: {bdaddr} {datetime.datetime.now()}")
                    # btc_sdp_gatt.py self-resolves Analysis/ for its TME imports, and
                    # TME_BTIDES_base resolves BTIDES_Schema/ relative to its own file,
                    # so the launcher's CWD doesn't matter.
                    # --no-interactive-pairing makes the agent reject Passkey Entry,
                    # Numeric Comparison, and legacy PIN flows immediately rather
                    # than blocking on input() — there's no human at this terminal
                    # to type a passkey. Just Works pairings still complete.
                    btc_sdp_gatt_cmd = ["python3", "-u", btc_sdp_gatt_path,
                                        f"--bdaddr={bdaddr}", "--quiet-print",
                                        "--no-interactive-pairing"]
                    try:
                        btc_sdp_gatt_process = launch_application(btc_sdp_gatt_cmd, default_cwd, target=("BTC", bdaddr, "public"))
                    except BlockingIOError as e:
                        print(f"Caught BlockingIOError while launching btc_sdp_gatt: {e}")
                        force_reboot()
                    except Exception as e:
                        print(f"Caught an exception while launching btc_sdp_gatt: {e}")
                        force_reboot()

                    if(btc_sdp_gatt_process != None):
                        # 30s = SDP attempt (~10s) + optional GATT enumeration (~10s) + slack.
                        btc_sdp_gatt_thread = ApplicationThread(btc_sdp_gatt_process, bdaddr, info_type="BTC_SDP_GATT", timeout=30)
                        try:
                            btc_sdp_gatt_thread.start()
                            btc_external_tool_threads.append(btc_sdp_gatt_thread)
                            launched_btc_probe = True
                        except Exception as e:
                            print(f"Caught an exception while starting btc_sdp_gatt thread: {e}")
                            force_reboot()

            if not launched_btc_probe:
                _refund_attempt_if_not_probed("BTC", bdaddr, state[0])

            # Wait for all threads to finish, before moving to the next bd_addr
            for thread in btc_external_tool_threads:
                thread.join()

            #if(print_verbose): print(f"BTC Address: {bdaddr}")

        print(f"Finished one complete loop through sorted_btc_bdaddrs {datetime.datetime.now()}")
        # See ble_thread_function for why this sleep matters with the asyncio main loop.
        while(len(btc_bdaddrs) == 0):
            time.sleep(1)

##################################################
# Sniffle-handling thread
##################################################

# Per-dongle state. Status convention:
#   0   = port available, sniffle thread should (re)launch using the role in serial_port_role
#   PID = port currently in use by that pid; sniffle thread skips it
serial_port_status = {}
# Per-dongle role assignment, fixed at startup by assign_sniffle_roles().
#   ('follow', None)        => default channel hopping, follow connections (no -A, no -c)
#   ('scan',   None)        => active scan all advertising channels, no connection follow (-A only)
#   ('follow', 37|38|39)    => follow connections pinned to a specific advertising channel (-c=N)
serial_port_role = {}
start_sniffle_threads_condition = threading.Condition()

# Sniffle wedge-recovery state. Reaches an EIO-on-open wedge when the cp210x
# bridge / Sonoff firmware locks up; observed in the 2026-05-04 14:37 incident
# where ttyUSB2 + ttyUSB3 both started returning [Errno 5] on serial open and
# stayed unrecoverable until reboot. Two-prong fix:
#
#   * Stall detector kills a running sniffer whose pcap file hasn't grown for
#     SNIFFLE_STALL_THRESHOLD_S so we catch the wedge *before* it progresses
#     to the hard EIO state. The kill triggers the standard relaunch path,
#     which then notices needs_usb_reset and recovers.
#
#   * needs_usb_reset[port] is set whenever a sniffler exits non-zero (likely
#     EIO) or the stall detector kills one. The sniffle worker consumes the
#     flag by running usbreset against the underlying USB device before the
#     next launch attempt; that issues USBDEVFS_RESET, which preserves the
#     device address (so /dev/ttyUSBN stays valid) and clears the cp210x
#     state in practice.
SNIFFLE_STALL_THRESHOLD_S = 300       # 5 min of zero pcap growth -> wedge
SNIFFLE_STALL_CHECK_PERIOD_S = 60     # how often the detector polls
SNIFFLE_FRESH_LAUNCH_GRACE_S = 60     # don't accuse a sniffer of stalling in its first minute
serial_port_needs_usb_reset = {}      # path -> bool
serial_port_pcap_path = {}            # path -> currently-writing pcap path
serial_port_pcap_last_seen = {}       # path -> (size, time.monotonic())
serial_port_launch_time = {}          # path -> time.monotonic() of most recent successful Popen
sniffle_state_lock = threading.Lock()


def assign_sniffle_roles(dongles):
    """Distribute roles across Sniffle dongles per issue #26.

    With S = number of Sniffle dongles (i.e. total dongles minus MAX_BG):
        S == 0: nothing to assign (caller should disable Sniffle)
        S == 1: 1 scan-all-channels-no-follow
        S == 2: 1 scan-all-channels-no-follow + 1 connection-follower (default channel hop)
        S == 3: 1 connection-follower pinned per advertising channel (37, 38, 39)
        S >= 4: 1 follower per channel (37, 38, 39) + (S - 3) scan-all-channels-no-follow

    The first MAX_BG dongles never reach this function — they are reserved for
    Better_Getter.py and managed by bg_dongle_queue.
    """
    s = len(dongles)
    roles = {}
    if s == 0:
        return roles
    if s == 1:
        roles[dongles[0]] = ('scan', None)
    elif s == 2:
        roles[dongles[0]] = ('scan', None)
        roles[dongles[1]] = ('follow', None)
    elif s == 3:
        roles[dongles[0]] = ('follow', 37)
        roles[dongles[1]] = ('follow', 38)
        roles[dongles[2]] = ('follow', 39)
    else:
        # S >= 4: pin first three to ch37/38/39 follow, rest are no-follow all-channel scan
        roles[dongles[0]] = ('follow', 37)
        roles[dongles[1]] = ('follow', 38)
        roles[dongles[2]] = ('follow', 39)
        for path in dongles[3:]:
            roles[path] = ('scan', None)
    return roles


def build_sniffle_cmd(dongle_path, role, launch_time, short_name, host):
    """Translate a (mode, channel) role tuple into a sniffle CLI invocation."""
    mode, channel = role
    cmd = [sniffle_path]  # native binary, no python3 wrapper
    label_parts = []
    if mode == 'scan':
        cmd.append("-A")
        label_parts.append("no_follow")
    else:
        label_parts.append("follow")
    if channel is not None:
        cmd.append(f"-c={channel}")
        label_parts.append(f"ch{channel}")
    label = "_".join(label_parts)
    cmd.append(f"-s={dongle_path}")
    cmd.append(f"-o={sniffle_pcap_log_folder}/{launch_time}_{short_name}_{label}_{host}.pcap")
    return cmd


# serial_port_role is populated by _start_workers_after_dongle_init() once
# _init_serial_dongles() has split the dongle pool into bg_dongles + sniffle_dongles.
# The Sniffle worker doesn't start until that's done, so it never sees an empty role map.


def _usbreset_dongle(tty_path):
    """Send a USB-level reset (USBDEVFS_RESET) to the device backing
    /dev/ttyUSBN. Used to clear the cp210x EIO wedge documented in the
    2026-05-04 incident.

    Resolves /dev/ttyUSBN -> /sys/class/tty/ttyUSBN/device (the USB interface
    sysfs path) -> parent dir (the USB device) -> busnum + devnum ->
    /dev/bus/usb/BBB/DDD, then exec()s `usbreset` against it. Returns True
    on a successful reset, False otherwise. The kernel preserves the device
    address through USBDEVFS_RESET so /dev/ttyUSBN stays valid; the cp210x
    driver unbinds + rebinds, which clears its error state.
    """
    short_name = os.path.basename(tty_path)  # e.g. ttyUSB2
    sysfs_iface = f"/sys/class/tty/{short_name}/device"
    if not os.path.exists(sysfs_iface):
        print(f"_usbreset_dongle: {sysfs_iface} not present; can't reset {tty_path}")
        return False
    # The kernel layout for cp210x has varied across versions:
    #   * older: /sys/class/tty/ttyUSBN/device -> .../1-1.1.3.2:1.0  (interface dir)
    #     → device dir is one parent up
    #   * newer (Pi kernel 6.12.x observed): -> .../1-1.1.3.2:1.0/ttyUSBN  (a child
    #     subdir of the interface) → device dir is two parents up
    # busnum + devnum live at the device dir, not the interface. Walk upward from
    # the realpath until we find a dir containing both files; cap at 6 hops to
    # avoid runaway when the symlink chain is broken.
    real = os.path.realpath(sysfs_iface)
    usb_device_dir = None
    cur = real
    for _ in range(6):
        if (os.path.exists(os.path.join(cur, "busnum"))
                and os.path.exists(os.path.join(cur, "devnum"))):
            usb_device_dir = cur
            break
        parent = os.path.dirname(cur)
        if parent == cur:  # reached /
            break
        cur = parent
    if usb_device_dir is None:
        print(f"_usbreset_dongle: could not locate busnum/devnum for {tty_path} starting from {real}")
        return False
    try:
        with open(os.path.join(usb_device_dir, "busnum")) as f:
            busnum = int(f.read().strip())
        with open(os.path.join(usb_device_dir, "devnum")) as f:
            devnum = int(f.read().strip())
    except (FileNotFoundError, ValueError) as e:
        print(f"_usbreset_dongle: failed to read busnum/devnum for {tty_path}: {e}")
        return False
    # usbutils' usbreset accepts "BBB/DDD" (decimal bus/dev, no /dev/bus/usb/
    # prefix), "VVVV:PPPP", "SN:SERIAL", or "Product"-name. A bare path like
    # /dev/bus/usb/001/008 falls through to the product-name branch and exits
    # with "No such device found" — observed 35,570 times in the NYC Day-2&3
    # capture before this fix, with a 0% success rate.
    bus_dev_arg = f"{busnum:03d}/{devnum:03d}"
    bus_path = f"/dev/bus/usb/{bus_dev_arg}"  # display-only
    print(f"_usbreset_dongle: running usbreset {bus_dev_arg} for {tty_path} ({bus_path})")
    try:
        result = subprocess.run(
            ["usbreset", bus_dev_arg],
            timeout=10, capture_output=True, text=True,
        )
    except FileNotFoundError:
        print("_usbreset_dongle: 'usbreset' binary not found on PATH; "
              "install it (apt install usbutils) or skip recovery.")
        return False
    except subprocess.TimeoutExpired:
        print(f"_usbreset_dongle: usbreset {bus_dev_arg} timed out after 10s")
        return False
    if result.returncode != 0:
        print(f"_usbreset_dongle: usbreset {bus_dev_arg} returned {result.returncode} "
              f"(stdout={result.stdout!r} stderr={result.stderr!r})")
        return False
    # Wait briefly for udev to re-fire the cp210x bind + re-create the
    # /dev/serial/by-id/... symlink before the caller relaunches sniff_receiver.
    time.sleep(3)
    print(f"_usbreset_dongle: usbreset {bus_dev_arg} OK")
    return True


# Serializes uhubctl-based recovery so concurrent ApplicationThread releases
# don't each try to cycle the same hub. Combined with _last_bg_uhubctl_cycle_at,
# this gives us "exactly one cycle per cooldown window" semantics across threads.
_bg_uhubctl_cycle_lock = threading.Lock()
_last_bg_uhubctl_cycle_at = 0.0
# Don't re-cycle within this many seconds of a previous cycle. After a hub-wide
# power-off + power-on, every dongle on the (ganged) hub is mid-rebind and any
# BG launches against them WILL fail-fast with EIO/ENOENT — that's expected,
# not a fresh wedge. The cooldown prevents the cascade of re-cycles that would
# otherwise lock the hub in continuous reset.
UHUBCTL_BG_COOLDOWN_S = 60.0


def _sysfs_id_from_tty(tty_path):
    """Return the USB sysfs device id (e.g. '1-1.2.3.4') for /dev/ttyUSBN, or
    None if the device isn't present or the realpath chain doesn't expose a
    standard USB device dir. Walks up the tty's `device` symlink target until
    it hits a basename that looks like a USB device id (dots, no colon)."""
    short_name = os.path.basename(tty_path)
    sysfs_iface = f"/sys/class/tty/{short_name}/device"
    if not os.path.exists(sysfs_iface):
        return None
    cur = os.path.realpath(sysfs_iface)
    for _ in range(8):
        base = os.path.basename(cur)
        # USB device dirs look like '1-1.2.3.4'. Interface dirs have ':' (e.g.
        # '1-1.2.3.4:1.0'). The leaf may also be a tty subdir like 'ttyUSB6'.
        if "." in base and ":" not in base and "-" in base:
            return base
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


def _uhubctl_cycle_for_tty(tty_path):
    """Power-cycle the closest PPPS-capable hub-port whose subtree contains
    /dev/ttyUSBN. Walks up the USB topology from the dongle's immediate parent
    looking for a hub uhubctl can drive.

    No safety check on the subtree — on ganged hubs this also bounces every
    other device on the same hub. That tradeoff is intentional: the only
    software recovery for a deeper-than-driver wedge (cp210x ETIMEDOUT +
    USBDEVFS_RESET ENODEV) is power loss, and the user has explicitly accepted
    ganged collateral damage in exchange for getting the dongle back at all.
    The bounced neighbors get a forced "preventative reset" out of the deal.

    Caller must hold _bg_uhubctl_cycle_lock and update _last_bg_uhubctl_cycle_at
    around this call so concurrent BG ApplicationThread releases don't each
    issue their own cycle for the same hub.

    Returns True on a successful cycle, False otherwise.
    """
    sysfs_id = _sysfs_id_from_tty(tty_path)
    if sysfs_id is None:
        print(f"_uhubctl_cycle_for_tty: could not determine USB sysfs id for {tty_path}")
        return False
    parts = sysfs_id.split(".")
    if len(parts) < 2:
        print(f"_uhubctl_cycle_for_tty: sysfs id {sysfs_id} has no parent hub")
        return False
    # Walk upward: i=1 is direct parent, i=2 is grandparent, etc. Stop short of
    # the root host controller (parts[0] alone, e.g. '1-1') since uhubctl can't
    # really cycle that — it's the host controller's port.
    for i in range(1, len(parts)):
        candidate_hub = ".".join(parts[:-i])
        candidate_port = parts[-i]
        if not _hub_supports_ppps(candidate_hub):
            continue
        print(f"_uhubctl_cycle_for_tty: cycling hub {candidate_hub} port {candidate_port} for {tty_path}")
        try:
            result = subprocess.run(
                ["uhubctl", "-l", candidate_hub, "-p", candidate_port, "-a", "cycle"],
                timeout=15, capture_output=True, text=True,
            )
        except FileNotFoundError:
            print("_uhubctl_cycle_for_tty: 'uhubctl' not on PATH; can't recover")
            return False
        except subprocess.TimeoutExpired:
            print(f"_uhubctl_cycle_for_tty: uhubctl cycle timed out on {candidate_hub} port {candidate_port}")
            return False
        if result.returncode != 0:
            print(f"_uhubctl_cycle_for_tty: uhubctl rc={result.returncode}, "
                  f"stderr={result.stderr.strip()[:200]}")
            return False
        # Wait for udev to re-bind the cp210x driver and re-create /dev/ttyUSBN
        # plus the /dev/serial/by-id symlinks. On the .183 test bench, full
        # rebind across a ganged hub takes ~5-7s; 10s is generous.
        time.sleep(10)
        print(f"_uhubctl_cycle_for_tty: cycle of {candidate_hub} port {candidate_port} OK for {tty_path}")
        return True
    print(f"_uhubctl_cycle_for_tty: no PPPS-capable ancestor found for {tty_path}")
    return False


def sniffle_stall_detector_thread():
    """Periodically check each running sniffer's pcap file for growth. Files
    that have not grown for SNIFFLE_STALL_THRESHOLD_S indicate the firmware
    has stopped emitting packets — the python process is healthy, the kernel
    keeps the device file open, but the dongle is silently wedged. Kill the
    process so the standard relaunch path picks up the port; flag it for
    usbreset so the next launch starts from a clean cp210x state.

    Skips the first SNIFFLE_FRESH_LAUNCH_GRACE_S after a (re)launch so a slow
    startup doesn't get misdiagnosed as a stall.
    """
    while True:
        time.sleep(SNIFFLE_STALL_CHECK_PERIOD_S)
        now = time.monotonic()
        # Snapshot items so we don't fight the sniffle thread mutating the dict.
        for port, pid in list(serial_port_status.items()):
            if pid <= 0:
                continue
            with sniffle_state_lock:
                pcap_path = serial_port_pcap_path.get(port)
                launch_time = serial_port_launch_time.get(port, 0)
            if not pcap_path:
                continue
            if now - launch_time < SNIFFLE_FRESH_LAUNCH_GRACE_S:
                continue
            try:
                size = os.path.getsize(pcap_path)
            except OSError:
                continue
            with sniffle_state_lock:
                prev = serial_port_pcap_last_seen.get(port)
                if prev is None or prev[0] != size:
                    # First observation or file is still growing.
                    serial_port_pcap_last_seen[port] = (size, now)
                    continue
                stalled_for = now - prev[1]
            if stalled_for < SNIFFLE_STALL_THRESHOLD_S:
                continue
            print(f"[stall] sniffer pid {pid} on {port} has not produced packets "
                  f"for {stalled_for:.0f}s (pcap stuck at {size} bytes). "
                  f"Killing + flagging for usbreset before relaunch.")
            external_log_write(
                sniffle_stdout_log_path,
                f"SNIFFLE STALL on {port}: pid {pid} stuck at {size} bytes for "
                f"{stalled_for:.0f}s; killing and flagging for usbreset "
                f"{datetime.datetime.now()}")
            with sniffle_state_lock:
                serial_port_needs_usb_reset[port] = True
                serial_port_pcap_last_seen.pop(port, None)
            try:
                os.kill(pid, 9)  # SIGKILL — sniff_receiver doesn't trap signals
            except ProcessLookupError:
                pass


# Function for the Sniffle thread(s)
def sniffle_thread_function():
    global sniffle_stdout_logging
    global start_sniffle_threads_condition
    global _last_bg_uhubctl_cycle_at

    if(print_verbose):
        for _path, _role in serial_port_role.items():
            print(f"Sniffle role: {_path} -> {_role}")

    while(True):
        # Snapshot keys() so the iteration is safe even if a callback mutates the dict
        # while we're launching.
        for link_target_absolute_path in list(serial_port_role.keys()):
            # Skip dongles whose previous sniffle process is still running. Without this
            # guard, a wake-up from one timed-out port would re-launch on every dongle,
            # orphaning the previously-launched processes.
            if serial_port_status[link_target_absolute_path] != 0:
                continue
            # Get just the "ttyUSB#" part to append to file names so they're unique
            short_name = link_target_absolute_path.split("/")[2]
            current_time = datetime.datetime.now()
            launch_time = current_time.strftime('%Y-%m-%d-%H-%M-%S')
            host = os.popen('hostname').read().strip()
            role = serial_port_role[link_target_absolute_path]
            # IMPORTANT NOTE: Even though sniffle on the CLI doesn't need an = after the arguments, when launched this way, it does!
            sniffle_cmd = build_sniffle_cmd(link_target_absolute_path, role, launch_time, short_name, host)

            # Wedge recovery: if the previous incarnation of this sniffer
            # exited with EIO or got SIGKILLed by the stall detector, the
            # dongle's cp210x state needs a USB-level reset before the next
            # open() will succeed. Consume the flag and reset before
            # launching. If the usbreset itself fails (typically because the
            # cp210x has fully detached and USBDEVFS_RESET returns ENODEV),
            # escalate to a hub power-cycle — same pattern as the BG path's
            # _release_bg_dongle. The shared cycle lock + cooldown means a
            # concurrent BG recovery can't pile on with its own cycle of the
            # same hub, and vice versa.
            with sniffle_state_lock:
                needs_reset = serial_port_needs_usb_reset.pop(link_target_absolute_path, False)
            if needs_reset:
                reset_ok = _usbreset_dongle(link_target_absolute_path)
                if not reset_ok:
                    with _bg_uhubctl_cycle_lock:
                        now = time.monotonic()
                        if now - _last_bg_uhubctl_cycle_at < UHUBCTL_BG_COOLDOWN_S:
                            tprint(f"Sniffle: usbreset of {link_target_absolute_path} failed; "
                                   f"skipping uhubctl (cooldown active, "
                                   f"{now - _last_bg_uhubctl_cycle_at:.0f}s since last cycle)")
                        else:
                            tprint(f"Sniffle: usbreset of {link_target_absolute_path} failed; "
                                   f"falling back to uhubctl power-cycle (will also bounce "
                                   f"other dongles on the hub)")
                            _last_bg_uhubctl_cycle_at = now
                            cycled = _uhubctl_cycle_for_tty(link_target_absolute_path)
                            if cycled:
                                # Stale per-dongle BG failure counters from before the cycle
                                # are no longer meaningful; mirror the BG-side reset so the
                                # next pickups don't immediately re-flag a freshly-rebound
                                # dongle.
                                for k in list(bg_dongle_consecutive_failures.keys()):
                                    bg_dongle_consecutive_failures[k] = 0
                            else:
                                _last_bg_uhubctl_cycle_at = 0.0
                    # Brief backoff so a hub mid-rebind doesn't see another
                    # immediate open() that fast-fails and re-flags. Without
                    # this, a still-wedged dongle would respin the relaunch
                    # loop at ~3-4 Hz (96k SNIFFLE LAUNCH FAILUREs in NYC).
                    time.sleep(3)

            try:
                if(sniffle_stdout_logging):
                    sniffle_append_stdout = open(f"{sniffle_pcap_log_folder}/Sniffle_stdout.log", "a")
                else:
                    sniffle_append_stdout = open(f"/dev/null", "a")
                sniffle_process = launch_application(sniffle_cmd, default_cwd, stdout=sniffle_append_stdout)
                if(print_verbose): print(f"Setting {link_target_absolute_path} pid to {sniffle_process.pid}")
                serial_port_status[link_target_absolute_path] = sniffle_process.pid
                # Record the pcap output path + launch wall-time so the stall
                # detector knows what file to watch and whether to grant the
                # fresh-launch grace window.
                pcap_path_for_stall_detector = None
                for tok in sniffle_cmd:
                    if tok.startswith("-o="):
                        pcap_path_for_stall_detector = tok[3:]
                        break
                with sniffle_state_lock:
                    serial_port_pcap_path[link_target_absolute_path] = pcap_path_for_stall_detector
                    serial_port_pcap_last_seen.pop(link_target_absolute_path, None)
                    serial_port_launch_time[link_target_absolute_path] = time.monotonic()
            except BlockingIOError as e:
                print(f"Caught BlockingIOError while launching Sniffle application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                force_reboot()
            except Exception as e:
                print(f"Caught an exception while launching Sniffle application: {e}")
                # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                force_reboot()

            if(sniffle_process != None):
                # TODO: I don't feel like adding a new parameter right now, so I'm just reusing the bdaddr to include info about the sniffle_cmd used to launch the process
                launch_cmd_str = " ".join(sniffle_cmd)
                individual_sniffle_instance_thread = ApplicationThread(sniffle_process, info_type="Sniffle", bdaddr="N/A", launch_cmd=launch_cmd_str, timeout=sniffle_log_rotate_in_seconds)
                try:
                    individual_sniffle_instance_thread.start()
                    #Sniffle_individual_sniffer_threads_list.append(individual_sniffle_instance_thread)
                except Exception as e:
                    print(f"Caught an exception while starting Sniffle thread: {e}")
                    # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                    force_reboot()
        # We have now launched threads for all available serial ports
        with start_sniffle_threads_condition:
            start_sniffle_threads_condition.wait()

    # End while(True)

##################################################
# main()
##################################################

def _start_workers_after_dongle_init(args):
    """Wait for dongle enumeration, then start the BLE/BTC/Sniffle worker threads.

    Runs in its own thread so the main thread can drive the asyncio D-Bus discovery
    loop in parallel — discovery is responsive immediately at boot regardless of how
    long /dev/serial/by-id takes to populate.
    """
    global start_sniffle_threads_condition, serial_port_role, Sniffle_thread_enabled
    if args.discovery_only:
        return
    # Block until _init_serial_dongles() finishes so the *_enabled flags and dongle
    # path globals reflect the actual hardware state. Cap at 600s; if init somehow
    # never sets the event, we fall through and start workers with current flags.
    if not sniffle_init_done.wait(timeout=600):
        print("WARN: dongle init did not complete within 600s; starting worker threads anyway.")

    # Now that bg_dongles / sniffle_dongles are populated, fill the BG round-robin queue
    # and assign Sniffle roles per issue #26. Doing this here (instead of at module load)
    # ensures we see the post-init pool split, not the empty defaults.
    for _bg_path in bg_dongles:
        bg_dongle_queue.put(_bg_path)
    serial_port_role = assign_sniffle_roles(sniffle_dongles)
    for _path in serial_port_role:
        serial_port_status[_path] = 0
    if Sniffle_thread_enabled and not serial_port_role:
        # Defensive: _init_serial_dongles() already disables Sniffle when sniffle_dongles
        # is empty, but assign_sniffle_roles() returning empty for any other reason should
        # also cleanly disable rather than starting a thread that would idle forever.
        print("assign_sniffle_roles produced an empty mapping; disabling Sniffle.")
        Sniffle_thread_enabled = False
    if(print_verbose):
        print(f"BG queue primed with {bg_dongle_queue.qsize()} dongle(s)")
        for _path, _role in serial_port_role.items():
            print(f"Sniffle role: {_path} -> {_role}")

    if(BLE_thread_enabled):
        threading.Thread(target=ble_thread_function, daemon=True).start()
    if(BTC_thread_enabled):
        threading.Thread(target=btc_thread_function, daemon=True).start()
    if(Sniffle_thread_enabled):
        threading.Thread(target=sniffle_thread_function, daemon=True).start()
        # Detector for silently-wedged dongles (pcap-file growth stops while
        # the python sniffer keeps running). See SNIFFLE_STALL_THRESHOLD_S.
        threading.Thread(target=sniffle_stall_detector_thread, daemon=True).start()
        with start_sniffle_threads_condition:
            start_sniffle_threads_condition.notify()


def main():
    parser = argparse.ArgumentParser(description="Blue2thprinting central app launcher.")
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Run only the BlueZ D-Bus discovery loop; do not spawn the BLE/BTC/Sniffle worker threads. Useful for verifying scanning in isolation.",
    )
    args = parser.parse_args()
    _initialize_realtek()
    if not args.discovery_only:
        threading.Thread(target=_init_serial_dongles, daemon=True).start()
    else:
        sniffle_init_done.set()
    print(f"novelty_mode={novelty_mode}: advertisement-only BLE/BTC category skips are "
          f"{'ON' if novelty_mode else 'OFF (success and retry limits still apply)'}; "
          f"{novelty_evidence.rules.describe()}")

    if args.discovery_only:
        print("--discovery-only set: BLE, BTC, and Sniffle worker threads will NOT be started.")

    # Worker startup is deferred until dongle init finishes, but we don't want to block
    # D-Bus discovery on either, so the wait+spawn happens in its own thread.
    threading.Thread(target=_start_workers_after_dongle_init, args=(args,), daemon=True).start()

    print("\n\n=============================================================")
    print(f"central_app_launcher2 started at {datetime.datetime.now()}")
    print("=============================================================")

    try:
        asyncio.run(dbus_discovery_loop())
    except KeyboardInterrupt:
        print("KeyboardInterrupt: exiting central_app_launcher.")
    except Exception as e:
        print("Exception occurred in dbus_discovery_loop:", str(e))
        traceback.print_exc()
        raise SystemExit(1) from e

if __name__ == "__main__":
    main()
