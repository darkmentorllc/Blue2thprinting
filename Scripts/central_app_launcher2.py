#!/usr/bin/python3
'''
This is a tool which coordinates the launching of various 2thprinting apps.
The goal is to try and generally minimize contention for the scanning interface
(which is the built-in hci0 used by the python BTC/BLE libraries).
'''
# Activate venv before any other imports
import os
import sys
from pathlib import Path
from handle_venv import activate_venv
activate_venv()

import datetime
import subprocess
import threading
import time
import glob
from subprocess import TimeoutExpired
import traceback

# Library to get updates upon modification of bluetoothctl log file
from inotify_simple import INotify, flags

##################################################
# BEGIN TESTING TOGGLES
##################################################

BLE_thread_enabled = True
BTC_thread_enabled = True
Sniffle_thread_enabled = True

btc_2thprint_enabled = False # This is toggled off by default because unless you have Braktooth set up, turning this on will cause an error and reboot loop. Only turn on once Braktooth is configured.
gattprint_enabled = True
sdpprint_enabled = True

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
max_connect_attempts = 3 # How many times to attempt connections before skipping the device thereafter
                         # Note: can be reset by a device appearing in a [DEL] statement and then a [NEW] statement
                         # in the bluetoothctl log (which would happen if the signal went low and then high again)

##################################################
# PATHS YOU MAY NEED TO FIX
##################################################

username = "user"

default_cwd = f"/home/{username}/"

gatttool_exec_path = f"/home/{username}/Blue2thprinting/Scripts/BGG/BetterGATTGetter.py"
gatttool_output_pcap_path = f"/home/{username}/Blue2thprinting/Logs/BetterGATTGetter"

sdptool_exec_path = f"/home/{username}/Blue2thprinting/bluez-5.66/tools/sdptool"
sdptool_log_path = f"/home/{username}/Blue2thprinting/Logs/sdptool"

braktooth = f"/home/{username}/Blue2thprinting/braktooth_esp32_bluetooth_classic_attacks/wdissector/bin/bt_exploiter"
brak_cwd = f"/home/{username}/Blue2thprinting/braktooth_esp32_bluetooth_classic_attacks/wdissector/"

btc2thprint_log_path = f"/home/{username}/Blue2thprinting/Logs/BTC_2THPRINT.log"
gattprint_log_path = f"/home/{username}/Blue2thprinting/Logs/GATTprint.log"
sdpprint_log_path = f"/home/{username}/Blue2thprinting/Logs/SDPprint.log"

sniffle_stdout_log_path = f"/home/{username}/Blue2thprinting/Logs/Sniffle_stdout.log"
sniffle_path = f"/home/{username}/Blue2thprinting/Sniffle/python_cli/sniff_receiver.py"
sniffle_pcap_log_folder = f"/home/{username}/Blue2thprinting/Logs/sniffle"

# END STUFF YOU MAY NEED TO FIX UP

# Define a dictionary to store BDADDRs and their RSSI values
ble_bdaddrs = {}
ble_bdaddrs_lock = threading.Lock()
btc_bdaddrs = {}
btc_bdaddrs_lock = threading.Lock()
ble_deprioritized_bdaddrs = {}
ble_deprioritized_bdaddrs_lock = threading.Lock()
btc_deprioritized_bdaddrs = {}
btc_deprioritized_bdaddrs_lock = threading.Lock()

gatt_success_bdaddrs = {}
gatt_success_bdaddrs_lock = threading.Lock()
sdp_success_bdaddrs = {}
sdp_success_bdaddrs_lock = threading.Lock()
lmp2thprint_success_bdaddrs = {}
lmp2thprint_success_bdaddrs_lock = threading.Lock()

hostname = os.popen('hostname').read().strip()

#####################################################################################
# Single global serial port list for Sniffle sniffers or BetterGATTGetter.py to share
#####################################################################################
#
base_dir = '/dev/serial/by-id'
# Note: this would need to be changed to use other TI dev boards instead. For now I won't support that for simplicity
pattern = 'usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus*'

# Check if the base directory exists and is accessible
# Wait up to 360 seconds after this thread starts before giving up on getting Sniffle running (this is because on Raspbian Bookworm the serial devices come up way late
retry_count = 0
MAX_RETRY_COUNT = 360
while(retry_count < MAX_RETRY_COUNT):
    if (not os.path.isdir(base_dir) or not os.access(base_dir, os.R_OK)):
        retry_count += 10
        if(print_verbose): print(f"sniffle_thread_function: /dev/serial/by-id may not be accessible yet. Sleeping 10 seconds.")
        time.sleep(10)
    else:
        break # It's accessible, try to access Sniffle dongles now
if(retry_count == MAX_RETRY_COUNT):
    print(f"sniffle_thread_function: The directory {base_dir} does not exist or is not accessible and we exceeded MAX_RETRY_COUNT seconds waiting for it. Fix sniffle_thread_function() or permissions.")
    exit(-1)

# Construct the full pattern path
full_pattern = os.path.join(base_dir, pattern)

# Use glob to match the pattern
matching_files = glob.glob(full_pattern)

# The first path is reserved for BetterGATTGetter.py
# Note: this may need to be updated in the future to be a configurable number of elements, rather than just 1
first_sniffle_serial_port_relative_path = os.readlink(matching_files[0])
first_sniffle_serial_port_absolute_path = os.path.abspath(os.path.join(os.path.dirname(matching_files[0]), first_sniffle_serial_port_relative_path))

##################################################
# Log print helpers
##################################################

def external_log_write(log_path, fmt_str):
    with open(log_path, 'a') as file:
        try:
            current_time = datetime.datetime.now()
            print(f"\n{fmt_str}") # add a newline before, just preference, to make it easier to spot in the stdout log
            file.write(f"{fmt_str}\n") # add a newline after (required to not run lines together)
            file.flush()
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
    def __init__(self, process, bdaddr, info_type, timeout, launch_cmd=""):
        threading.Thread.__init__(self)
        self.process = process
        self.timeout = timeout
        self.is_terminated = False
        self.bdaddr = bdaddr
        self.info_type = info_type
        self.launch_cmd = launch_cmd

    def run(self):
        try:
            retCode = self.process.wait(self.timeout)
            if self.process.poll() is None:
                print(f"PID: {self.process.pid}: ApplicationThread: Shouldn't be able to get here. pid still running. Killing it")
                self.process.kill()
            else:
                print(f"PID: {self.process.pid}: ApplicationThread: {self.info_type} collection for {self.bdaddr} terminated on its own with return code {retCode}")
                if(retCode == 0): #Success!
                    if(self.info_type == "GATT"):
                       external_log_write(gattprint_log_path, f"GATTPRINTING SUCCESS FOR: {self.bdaddr} {datetime.datetime.now()}")
                       with gatt_success_bdaddrs_lock:
                           gatt_success_bdaddrs[self.bdaddr] = 1
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
                    elif(self.info_type == "SDP"):
                       external_log_write(sdpprint_log_path, f"SDPPRINTING SUCCESS FOR: {self.bdaddr} {datetime.datetime.now()}")
                       with sdp_success_bdaddrs_lock:
                           sdp_success_bdaddrs[self.bdaddr] = 1
                           if(print_finished_bdaddrs): print(f"Successful SDPPrinting of {self.bdaddr}!")
                           if(all_2thprints_done("BTC", self.bdaddr)):
                               locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, self.bdaddr)
                               if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {self.bdaddr} from btc_bdaddrs!")
                    elif(self.info_type == "Sniffle"):
                       external_log_write(sdpprint_log_path, f"SNIFFLE LAUNCH SUCCESS: {self.launch_cmd} {datetime.datetime.now()}")
                else:
                    if(self.info_type == "GATT"):
                       external_log_write(gattprint_log_path, f"GATTPRINTING FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "LMP2thprint"):
                       external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "SDP"):
                       external_log_write(sdpprint_log_path, f"SDPPRINTING FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "Sniffle"):
                       external_log_write(sniffle_stdout_log_path, f"SNIFFLE LAUNCH FAILURE 0x{retCode:02x} FOR: {self.launch_cmd} {datetime.datetime.now()}")

            self.is_terminated = True
        except TimeoutExpired:
            if(print_verbose): print(f"PID: {self.process.pid}: ApplicationThread: TimeoutExpired")
            print(f"PID: {self.process.pid}: ApplicationThread: Killing pid")
            self.process.kill()
            self.is_terminated = True
            if(self.info_type == "GATT"):
               external_log_write(gattprint_log_path, f"GATTPRINTING FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")
            elif(self.info_type == "LMP2thprint"):
               external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")
            elif(self.info_type == "SDP"):
               external_log_write(sdpprint_log_path, f"SDPPRINTING FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")
            elif(self.info_type == "Sniffle"):
               external_log_write(sniffle_stdout_log_path, f"SNIFFLE TIMEOUT FOR: {self.launch_cmd} {datetime.datetime.now()}")
               # Re-set the status of the serial port to available
               key = next((k for k, v in serial_port_status.items() if v == self.process.pid), None)
               if(key == None):
                   print(serial_port_status)
                   print("Unknown error occurred. Exiting")
                   exit(-1)
               if(print_verbose): print(f"self.process.pid = {self.process.pid}. Corresponding key in serial_port_status is {key}")
               # Set the status back to launching with follow or not (-A) based on the current launch status
               toks = self.launch_cmd.split(" ")
               if(toks[2] == "-A"):
                   serial_port_status[key] = 1
               else:
                   serial_port_status[key] = 0
               if(print_verbose): print("Notifying sniffle_thread_function to wake up and re-launch a new process/thread for this serial port.")
               with start_sniffle_threads_condition:
                   start_sniffle_threads_condition.notify()

def launch_application(cmd, target_cwd, stdout=None):
    try:
        process = subprocess.Popen(cmd, cwd=target_cwd, stdout=stdout)
        print(f"PID: {process.pid}: central_app_launcher2.py: launched {cmd}")
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
# For processing the bluetoothctl log
##################################################

bluetoothctl_log_link = '/tmp/BT_link.txt'

# Function to process a line and update the bdaddrs dictionary
# Line output looks like:
# {[NEW],[DEL} Device <bdaddr> {BLE,BTC} {random,public} <name>
# [CHG} Device <bdaddr> RSSI {various}
# [CHG] Device <bdaddr> ManufacturerData Key: 0x004c
# 0x004c is for Apple, which we want to deprioritize since we already have adequate data about them
def process_line(line):
    global device_connect_attempts
    tok = line.split()
    #print(tok)
    # We can have raw byte value lines from manufacturer data printouts
    if (len(tok) < 5 or tok[1] != "Device"):
        return

    bdaddr = tok[2].lower()
    type = tok[3] # This is technically only true for NEW and DEL but it's fine, since it's not used in CHG

    # Didn't want to deal with formatting. Just copied how tok[0] looked when I printed the tok
    if (tok[0] == '[\x01\x1b[0;92m\x02NEW\x01\x1b[0m\x02]'):
        device_connect_attempts[bdaddr] = 0 # This actually allows us to retry things which went away via a DEL and then came back
        if (type == "BLE"):
            with ble_bdaddrs_lock:
                ble_bdaddrs[bdaddr] = (tok[4], -80)
                if(BLE_thread_enabled and print_verbose): print(f"[NEW] {type} {bdaddr}")
        else:
            with btc_bdaddrs_lock:
                btc_bdaddrs[bdaddr] = (tok[4], -80)
                if(BTC_thread_enabled and print_verbose): print(f"[NEW] {type} {bdaddr}")

    # TODO: the CHG case could be made more efficient (not checking both lists) if bluetoothctl printed the type with the line...
    elif (tok[0] == '[\x01\x1b[0;93m\x02CHG\x01\x1b[0m\x02]' and tok[3] == "RSSI:"):
        with ble_bdaddrs_lock:
            if (bdaddr in ble_bdaddrs):
                (type, rssi) = ble_bdaddrs[bdaddr]
                # If we are seeing a device with a stronger signal than it previously had
                # Allow one more try to connect to it (this could happen multiple times, so it could ultimately get multiple tries)
                # This may allow us to connect to devices we weren't able to when further away
                if(rssi < int(tok[4]) and device_connect_attempts[bdaddr] > 1):
                    print(f"Higher RSSI observed. Decrementing device_connect_attempts {bdaddr} to {device_connect_attempts[bdaddr]-1}")
                    device_connect_attempts[bdaddr] -= 1
                ble_bdaddrs[bdaddr] = (type, int(tok[4]))
                type = "BLE"
                if(BLE_thread_enabled and print_verbose): print(f"Updated {type} RSSI ({tok[4]}) for {bdaddr}")

        with btc_bdaddrs_lock:
            if (bdaddr in btc_bdaddrs):
                (type, rssi) = btc_bdaddrs[bdaddr]
                # If we are seeing a device with a stronger signal than it previously had
                # Allow one more try to connect to it (this could happen multiple times, so it could ultimately get multiple tries)
                # This may allow us to connect to devices we weren't able to when further away
                if(rssi < int(tok[4]) and device_connect_attempts[bdaddr] > 1):
                    print(f"Higher RSSI observed. Decrementing device_connect_attempts {bdaddr} to {device_connect_attempts[bdaddr]-1}")
                    device_connect_attempts[bdaddr] -= 1
                btc_bdaddrs[bdaddr] = (type, int(tok[4]))
                type = "BTC"
                if(BTC_thread_enabled and print_verbose): print(f"Updated {type} RSSI ({tok[4]}) for {bdaddr}")

    elif (tok[0] == '[\x01\x1b[0;93m\x02CHG\x01\x1b[0m\x02]' and tok[3] == "ManufacturerData" and tok[4] == "Key:"):
        #print(tok)
        # Deprioritize Apple devices
        if(tok[5] == "0x004c"): # Can add more vendors here as desired
            with ble_bdaddrs_lock:
                if (bdaddr in ble_bdaddrs):
                    (type, rssi) = ble_bdaddrs[bdaddr]
                    with ble_deprioritized_bdaddrs_lock:
                        ble_deprioritized_bdaddrs[bdaddr] = (type, rssi, tok[5])
                    del ble_bdaddrs[bdaddr]
                    if(BLE_thread_enabled and print_verbose): print(f"Deprioritized BLE {type} {bdaddr} due to ManufacturerData {tok[5]}")

            with btc_bdaddrs_lock:
                if (bdaddr in btc_bdaddrs):
                    (type, rssi) = btc_bdaddrs[bdaddr]
                    with btc_deprioritized_bdaddrs_lock:
                        btc_deprioritized_bdaddrs[bdaddr] = (type, rssi, tok[5])
                    del btc_bdaddrs[bdaddr]
                    type = "BTC"
                    if(BTC_thread_enabled and print_verbose): print(f"Deprioritized BTC {type} {bdaddr} due to ManufacturerData {tok[5]}")

    elif (tok[0] == '[\x01\x1b[0;91m\x02DEL\x01\x1b[0m\x02]'):
        if (type == "BLE"):
            locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, bdaddr)
            # Decided NOT to delete from the deprioritized bdaddrs for now, because it will prevent things that are on
            # the edge of signal range from popping in and out of existance, wasting resources on re-scans
            # due to not immediately knowing their deprioritized devices
            # The downside is that the list will continue to grow indefinitely, but for the time being I think that's an acceptable tradeoff
            # If it becomes a problem we can store a last-seen time and periodically drop things that haven't been seen for an hour or so
            #locked_delete_from_dict(ble_deprioritized_bdaddrs, ble_deprioritized_bdaddrs_lock, bdaddr)
            if(BLE_thread_enabled and print_verbose): print(f"[DEL] {type} {bdaddr}")
        elif (type == "BTC"):
            locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)
            # Decided NOT to delete from the deprioritized bdaddrs for now, because it will prevent things that are on
            # the edge of signal range from popping in and out of existance, wasting resources on re-scans
            # due to not immediately knowing their deprioritized devices
            # The downside is that the list will continue to grow indefinitely, but for the time being I think that's an acceptable tradeoff
            # If it becomes a problem we can store a last-seen time and periodically drop things that haven't been seen for an hour or so
            #locked_delete_from_dict(btc_deprioritized_bdaddrs, btc_deprioritized_bdaddrs_lock, bdaddr)
            if(BTC_thread_enabled and print_verbose): print(f"[DEL] {type} {bdaddr}")
        else:
            print("Shouldn't get here. Debug script.")
            print(tok)
            quit()


##################################################
# BLE-handling thread
##################################################

def reprioritize_ble_bdaddr(bdaddr):
    with ble_bdaddrs_lock:
        type = ""
        rssi = -80
        with ble_deprioritized_bdaddrs_lock:
            if(bdaddr in ble_deprioritized_bdaddrs):
                (type, rssi, vendor) = ble_deprioritized_bdaddrs[bdaddr]
                del ble_deprioritized_bdaddrs[bdaddr]
                ble_bdaddrs[bdaddr] = (type, rssi)
                print(f"Reprioritized {type} {bdaddr} ({rssi})")

def reprioritize_btc_bdaddr(bdaddr):
    with ble_bdaddrs_lock:
        type = ""
        rssi = -80
        with btc_deprioritized_bdaddrs_lock:
            if(bdaddr in btc_deprioritized_bdaddrs):
                (type, rssi, vendor) = btc_deprioritized_bdaddrs[bdaddr]
                del btc_deprioritized_bdaddrs[bdaddr]
                btc_bdaddrs[bdaddr] = (type, rssi)
                print(f"Reprioritized {type} {bdaddr} ({rssi})")

# Function for the first thread
def ble_thread_function():
    global device_connect_attempts
    ble_external_tool_threads = []
    while True:
        # Get the BDADDRs sorted in descending order of their RSSI, so we process higher RSSI first
        sorted_ble_bdaddrs = sorted(ble_bdaddrs.keys(), key=lambda x: ble_bdaddrs[x][1], reverse=True)

        if(print_verbose):
            print(f"Begin loop through sorted_ble_bdaddrs {datetime.datetime.now()}")
            print(f"sorted_ble_bdaddrs = {sorted_ble_bdaddrs}")
            print(f"ble_deprioritized_bdaddrs = {ble_deprioritized_bdaddrs}")

        skip_count = int(0)
        for bdaddr in sorted_ble_bdaddrs:
            # Skip devices that may be traveling with us, to not waste time on them
            # Only try collecting data from a given bd_addr max_connect_attempts times before skipping forever thereafter
            # This is so that we don't waste time trying to get info from something that will never give it to us,
            # when we could be spending that time trying new devices
            if((str(bdaddr).lower() in skip_these_addresses) or (device_connect_attempts[bdaddr] >= max_connect_attempts)):
                if(print_skipped):
                    print(f"BLE: Max connect attempts exceeded for {bdaddr}, skipping")
                skip_count += 1
                if(print_skipped):
                    print(f"BLE: skip_count = {skip_count} of {len(sorted_ble_bdaddrs)}")

                # Delete it otherwise it will just keep coming up over and over again in the while True loop
                locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, bdaddr)

                if(skip_count == len(sorted_ble_bdaddrs) and len(ble_deprioritized_bdaddrs) > 0):
                    print("BLE: Everything's being skipped. We could go ahead and do some deprioritized bdaddrs now...")
                    print(ble_deprioritized_bdaddrs)
                    bdaddr = list(ble_deprioritized_bdaddrs.keys())[0] # Grab a single bdaddr
                    reprioritize_ble_bdaddr(bdaddr)
                    print(ble_deprioritized_bdaddrs)

                continue
            else:
                device_connect_attempts[bdaddr] += 1

            if(print_verbose): print(f"BLE Address: {bdaddr}")

            if(gattprint_enabled):
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
                    with ble_bdaddrs_lock:
                        if(bdaddr in ble_bdaddrs):
                            external_log_write(gattprint_log_path, f"GATTPRINTING ATTEMPT FOR: {bdaddr} {datetime.datetime.now()}")
                            (type, rssi) = ble_bdaddrs[bdaddr]
                            current_time = datetime.datetime.now()
                            launch_time = current_time.strftime('%Y-%m-%d-%H-%M-%S')
                            pcap_output = f"-o={gatttool_output_pcap_path}/{launch_time}_{bdaddr}_BGG_{hostname}.pcap"
                            serial_port = f"-s={first_sniffle_serial_port_absolute_path}"
                            # -u for unbuffered python output (so it streams to log realtime)
                            if(type != "random"):
                                gatt_cmd = ["python3", "-u", gatttool_exec_path, "-q", serial_port, pcap_output, f"-b={bdaddr}", "-P", "-2"]
                            else:
                                gatt_cmd = ["python3", "-u", gatttool_exec_path, "-q", serial_port, pcap_output, f"-b={bdaddr}", "-2"]
                            try:
                                if(sniffle_stdout_logging):
                                    sniffle_append_stdout = open(f"{gatttool_output_pcap_path}/Sniffle_stdout.log", "a")
                                else:
                                    sniffle_append_stdout = open(f"/dev/null", "a")
                                gatt_process = launch_application(gatt_cmd, default_cwd, stdout=sniffle_append_stdout)
                            except BlockingIOError as e:
                                print(f"Caught BlockingIOError while launching GATT application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                                # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                                force_reboot()
                            except Exception as e:
                                print(f"Caught an exception while launching GATT application: {e}")
                                # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                                force_reboot()
                            if(gatt_process != None):
                                gatt_thread = ApplicationThread(gatt_process, bdaddr, info_type="GATT", timeout=20) # Unfortunately I found some device that can take ~21 sec(!) even when tested manually
                                try:
                                    gatt_thread.start()
                                    ble_external_tool_threads.append(gatt_thread)
                                except Exception as e:
                                    print(f"Caught an exception while starting GATT thread: {e}")
                                    # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                                    force_reboot()


            # Wait for all threads to finish, before moving to the next bd_addr
            for thread in ble_external_tool_threads:
                thread.join()
            print(f"BLE: Finished all threads for {bdaddr}")

        print(f"Finished one complete loop through sorted_ble_bdaddrs {datetime.datetime.now()}")

        # Busy wait until the diciontary has entries to process before proceeding again
        while(len(ble_bdaddrs) == 0):
            pass
       # time.sleep(5)


##################################################
# BTC-handling thread
##################################################

# Function for the second thread
def btc_thread_function():
    global device_connect_attempts
    btc_external_tool_threads = []
    while True:
        # Get the BDADDRs sorted in descending order of their RSSI, so we process higher RSSI first
        sorted_btc_bdaddrs = sorted(btc_bdaddrs.keys(), key=lambda x: btc_bdaddrs[x][1], reverse=True)

        if(print_verbose):
            print(f"Begin loop through sorted_btc_bdaddrs {datetime.datetime.now()}")
            print(f"sorted_btc_bdaddrs = {sorted_btc_bdaddrs}")
            print(f"btc_deprioritized_bdaddrs = {btc_deprioritized_bdaddrs}")

        skip_count = 0
        for bdaddr in sorted_btc_bdaddrs:
            # Skip devices that may be traveling with us, to not waste time on them
            # Only try collecting data from a given bd_addr max_connect_attempts times before skipping forever thereafter
            # This is so that we don't waste time trying to get info from something that will never give it to us,
            # when we could be spending that time trying new devices
            if((str(bdaddr).lower() in skip_these_addresses) or (device_connect_attempts[bdaddr] >= max_connect_attempts)):
                if(print_skipped):
                    print(f"BTC: Max connect attempts exceeded for {bdaddr}, skipping")
                skip_count += 1
                if(print_skipped):
                    print(f"BTC: skip_count = {skip_count} of {len(sorted_btc_bdaddrs)}")
                # Delete it otherwise it will just keep coming up over and over again in the while True loop
                locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)

                if(skip_count == len(sorted_btc_bdaddrs) and len(btc_deprioritized_bdaddrs) > 0):
                    print("BTC: Everything's being skipped. We could go ahead and do some deprioritized bdaddrs now...")
                    print(btc_deprioritized_bdaddrs)
                    bdaddr = list(btc_deprioritized_bdaddrs.keys())[0] # Grab a single bdaddr
                    reprioritize_btc_bdaddr(bdaddr)
                    print(btc_deprioritized_bdaddrs)

                continue
            else:
                device_connect_attempts[bdaddr] += 1

            if(btc_2thprint_enabled):
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
                    external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: LOG ENTRY FOR BDADDR: {bdaddr} {datetime.datetime.now()}")
                    btc_2thprint_cmd = [braktooth, "--exploit=LMP2thprint", "--target={}".format(bdaddr)]
                    try:
                        btc_2thprint_process = launch_application(btc_2thprint_cmd, brak_cwd) # Braktooth must be launched from its target dir, otherwise it errors out
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
                        except Exception as e:
                            print(f"Caught an exception while starting LMP2thprint thread: {e}")
                            # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                            force_reboot()

            if(sdpprint_enabled):
                skip_sub_process = False
                with sdp_success_bdaddrs_lock:
                    if(bdaddr in sdp_success_bdaddrs.keys()):
                        if(print_finished_bdaddrs): print(f"We've already successfully SDPPrinted {bdaddr}! Skipping!")
                        # Remove it from further consideration (it could have just been added in by a [DEL] -> [NEW] sequence)
                        if(all_2thprints_done("BTC", bdaddr)):
                            locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)
                            if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {bdaddr} from btc_bdaddrs!")
                        skip_sub_process = True # We can't just 'continue' here for generalism, for if we add more stuff beyond this

                if(not skip_sub_process and bdaddr in btc_bdaddrs): # Double check that bdaddr hasn't been deleted out of btc_bdaddrs by a [DEL]
                    external_log_write(sdpprint_log_path, f"SDPPRINTING ATTEMPT FOR: {bdaddr} {datetime.datetime.now()}")
                    output_file = open(f"{sdptool_log_path}/{bdaddr}_sdp.xml", "a") # redirect stdout to an output XML file
                    sdpprint_cmd = [sdptool_exec_path, "browse", "--xml", bdaddr]
                    try:
                        sdpprint_process = launch_application(sdpprint_cmd, default_cwd, stdout=output_file) # There should be no special CWD requirements
                    except BlockingIOError as e:
                        print(f"Caught BlockingIOError while launching application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()
                    except Exception as e:
                        print(f"Caught an exception while launching SDP application: {e}")
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()

                    if(sdpprint_process != None):
                        sdpprint_thread = ApplicationThread(sdpprint_process, bdaddr, info_type="SDP", timeout=15)
                        try:
                            sdpprint_thread.start()
                            btc_external_tool_threads.append(sdpprint_thread)
                        except Exception as e:
                            print(f"Caught an exception while starting SDPprint thread: {e}")
                            # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                            force_reboot()

            # Wait for all threads to finish, before moving to the next bd_addr
            for thread in btc_external_tool_threads:
                thread.join()

            #if(print_verbose): print(f"BTC Address: {bdaddr}")

        print(f"Finished one complete loop through sorted_btc_bdaddrs {datetime.datetime.now()}")
        # Busy wait until the diciontary has entries to process before proceeding again
        while(len(btc_bdaddrs) == 0):
            pass
        #time.sleep(5)

##################################################
# Sniffle-handling thread
##################################################

# The key will be serial port like /dev/ttyUSB0, the value will be 0 if the serial port is available and should follow connections, 1 if it's available and should not follow, and a process PID if it's in use
serial_port_status = {}
start_sniffle_threads_condition = threading.Condition()

# Function for the Sniffle thread(s)
def sniffle_thread_function():
    global sniffle_stdout_logging
    global start_sniffle_threads_condition
    global available_serial_ports
    adv_channel = 0 # This will be used as 37 + adv_channel++ mod 3, so that possible values are only 37, 38, and 39
    create_connection_follower = True

    '''
    base_dir = '/dev/serial/by-id'
    # Note: this would need to be changed to use other TI dev boards instead. For now I won't support that for simplicity
    pattern = 'usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus*'

    # Check if the base directory exists and is accessible
    retry_count = 0
    MAX_RETRY_COUNT = 360 # Wait up to 360 seconds after this thread starts before giving up on getting Sniffle running (this is because on Raspbian Bookworm the serial devices come up way late!)
    while(retry_count < MAX_RETRY_COUNT):
        if (not os.path.isdir(base_dir) or not os.access(base_dir, os.R_OK)):
            retry_count += 10
            if(print_verbose): print(f"sniffle_thread_function: /dev/serial/by-id may not be accessible yet. Sleeping 10 seconds.")
            time.sleep(10)
        else:
            break # It's accessible, try to access Sniffle dongles now
    if(retry_count == MAX_RETRY_COUNT):
        print(f"sniffle_thread_function: The directory {base_dir} does not exist or is not accessible and we exceeded MAX_RETRY_COUNT seconds waiting for it. Fix sniffle_thread_function() or permissions.")
        exit(-1)

    # Construct the full pattern path
    full_pattern = os.path.join(base_dir, pattern)

    # Use glob to match the pattern
    matching_files = glob.glob(full_pattern)
    '''

    # Skip the first serial port and leave it for BetterGATTGetter.py, by using the [1:] notation to start from matching_files[1]
    for serial_port_filename in matching_files[1:]:
        # Because the files in /dev/serial/by-id are symbolic links, find where it actually points
        link_target_relative_path = os.readlink(serial_port_filename)
        link_target_absolute_path = os.path.abspath(os.path.join(os.path.dirname(serial_port_filename), link_target_relative_path))
        if(print_verbose): print(f"Found viable Sniffle dongle: {serial_port_filename} -> {link_target_absolute_path}")
        if(print_verbose): print(f"Adding {link_target_absolute_path} to serial_port_status")
        if(create_connection_follower):
            serial_port_status[link_target_absolute_path] = 0
            create_connection_follower = False
        else:
            serial_port_status[link_target_absolute_path] = 1

    while(True):
            for link_target_absolute_path in serial_port_status.keys():
                # Get just the "ttyUSB# part to append to file names so they're unique
                short_name = link_target_absolute_path.split("/")[2]
                target_adv_channel = 37 + adv_channel
                adv_channel = (adv_channel + 1) % 3
                # Launch the sniffer as a background thread
                current_time = datetime.datetime.now()
                launch_time = current_time.strftime('%Y-%m-%d-%H-%M-%S')
                hostname = os.popen('hostname').read().strip()
                # IMPORTANT NOTE: Even though sniffle on the CLI doesn't need an = after the arguments, when launched this way, it does!
                if(serial_port_status[link_target_absolute_path] == 0):
                    sniffle_cmd = ["python3", sniffle_path, f"-s={link_target_absolute_path}", f"-o={sniffle_pcap_log_folder}/{launch_time}_{short_name}_follow_{hostname}.pcap"]
                else:
                    sniffle_cmd = ["python3", sniffle_path, f"-A", f"-s={link_target_absolute_path}", f"-o={sniffle_pcap_log_folder}/{launch_time}_{short_name}_no_follow__{hostname}.pcap"]
                #TODO: In the future get more clever with launching N -c options once we're at 4 or more dongles. But for now, just launch the first one as a connection follower, and all subsequent ones as active-scanning non-followers (-A)
                #sniffle_cmd = ["python3", sniffle_path, f"-c={target_adv_channel}", f"-s={link_target_absolute_path}", f"-o={sniffle_pcap_log_folder}/{launch_time}_{target_adv_channel}_{short_name}_no_follow_{hostname}.pcap"]

                try:
                    if(sniffle_stdout_logging):
                        sniffle_append_stdout = open(f"{sniffle_pcap_log_folder}/Sniffle_stdout.log", "a")
                    else:
                        sniffle_append_stdout = open(f"/dev/null", "a")
                    sniffle_process = launch_application(sniffle_cmd, default_cwd, stdout=sniffle_append_stdout)
                    if(print_verbose): print(f"Setting {link_target_absolute_path} pid to {sniffle_process.pid}")
                    serial_port_status[link_target_absolute_path] = sniffle_process.pid
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

# Monitor the file continuously using inotify
inotify = INotify()
watch_descriptor = inotify.add_watch(bluetoothctl_log_link, flags.MODIFY)

def main():
    global start_sniffle_threads_condition

    ble_thread = threading.Thread(target=ble_thread_function)
    btc_thread = threading.Thread(target=btc_thread_function)
    sniffle_thread = threading.Thread(target=sniffle_thread_function)

    if(BLE_thread_enabled): ble_thread.start()
    if(BTC_thread_enabled): btc_thread.start()
    if(Sniffle_thread_enabled):
        sniffle_thread.start()
        with start_sniffle_threads_condition:
            start_sniffle_threads_condition.notify()

    # Keep track of the bluetoothctl log file position so we don't re-process it on each open
    bt_file_position = 0

    print("\n\n=============================================================")
    print(f"central_app_launcher2 started at {datetime.datetime.now()}")
    print("=============================================================")

    # Keep processing the bluetoothctl log file forever
    while True:
        try:
            with open(bluetoothctl_log_link, 'r') as file:
                file.seek(bt_file_position)
                for line in file:
#                    print(line)
                    process_line(line.strip())
                bt_file_position = file.tell()  # Update the file position
                if(print_verbose): print(f"Updated bt_file_position to {bt_file_position}")

            # Block until there are further modifications
            for event in inotify.read():
                #print(event)
                if event.mask & flags.MODIFY:
                    break

        except Exception as e:
            print("Exception occurred:", str(e))
            traceback.print_exc()
            quit()
            print("Continuing.")

if __name__ == "__main__":
    main()
