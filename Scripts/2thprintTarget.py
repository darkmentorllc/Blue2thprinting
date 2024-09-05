#!/usr/bin/python3

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

'''
This is a tool which attempts to 2thprinting a given BDADDR via various techniques.
It is a quick-and-dirty hack that was made by modifying central_app_launcher2.py

Usage: 2thprintTarget.py <max_connect_attempts> <BDADDR> <type of \"public\" or \"random\">")

'''

import datetime
import subprocess
import threading
import time
import os
import re
import sys
import glob
from subprocess import TimeoutExpired
import traceback

##################################################
# BEGIN TESTING TOGGLES
##################################################

BLE_thread_enabled = True
BTC_thread_enabled = True
Sniffle_thread_enabled = True

btc_2thprint_enabled = True
ble_2thprint_enabled = True
gattprint_enabled = True
sdpprint_enabled = True

print_skipped = True
print_verbose = True
print_finished_bdaddrs = True

# END TESTING TOGGLES

# Place BDADDRs that you know will be traveling with you into this array,
# so that you don't waste time trying to get data about your own devices
# e.g. skip_these_addresses = ["AA:BB:CC:DD:EE:FF".lower()]
skip_these_addresses = []

device_ble_connect_attempts = {}
device_btc_connect_attempts = {}
max_connect_attempts = 4 # How many times to attempt connections before skipping the device thereafter

##################################################
# PATHS YOU MAY NEED TO FIX
##################################################

username = "user"

default_cwd = f"/home/{username}/"

gatttool_exec_path = f"/home/{username}/Blue2thprinting/bluez-5.66/attrib/gatttool"

sdptool_exec_path = f"/home/{username}/Blue2thprinting/bluez-5.66/tools/sdptool"
sdptool_log_path = f"/home/{username}/Blue2thprinting/Logs/sdptool"

braktooth = f"/home/{username}/Blue2thprinting/braktooth_esp32_bluetooth_classic_attacks/wdissector/bin/bt_exploiter"
brak_cwd = f"/home/{username}/Blue2thprinting/braktooth_esp32_bluetooth_classic_attacks/wdissector/"

python2 = "/usr/bin/python2.7"
ble2thprint = f"/home/{username}/Blue2thprinting/sweyntooth_bluetooth_low_energy_attacks/LL2thprint.py"
sweyn_cwd = f"/home/{username}/Blue2thprinting/sweyntooth_bluetooth_low_energy_attacks/"
dongle1 = "/dev/ttyACM0"

btc2thprint_log_path = f"/home/{username}/Blue2thprinting/Logs/BTC_2THPRINT.log"
gattprint_log_path = f"/home/{username}/Blue2thprinting/Logs/GATTprint.log"
sdpprint_log_path = f"/home/{username}/Blue2thprinting/Logs/SDPprint.log"

sniffle_log_path = f"/home/{username}/Blue2thprinting/Logs/Sniffle_stdout.log"
sniffle_path = f"/home/{username}/Blue2thprinting/Sniffle/python_cli/sniff_receiver.py"
sniffle_pcaps_path = f"/home/{username}/Blue2thprinting/Logs/sniffle"

# END STUFF YOU MAY NEED TO FIX UP

# Define a dictionary to store BDADDRs and their RSSI values
ble_bdaddrs = {}
ble_bdaddrs_lock = threading.Lock()
btc_bdaddrs = {}
btc_bdaddrs_lock = threading.Lock()

gatt_success_bdaddrs = {}
gatt_success_bdaddrs_lock = threading.Lock()
sdp_success_bdaddrs = {}
sdp_success_bdaddrs_lock = threading.Lock()
ll2thprint_success_bdaddrs = {}
ll2thprint_success_bdaddrs_lock = threading.Lock()
lmp2thprint_success_bdaddrs = {}
lmp2thprint_success_bdaddrs_lock = threading.Lock()

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

# My C-style mindset is showing ;)
def all_2thprints_done(type, bdaddr):
   ENABLED_BITMASK = 0
   COMPLETE_BITMASK = 0
   if(type == "BLE"):
       GATT_BIT = 0
       LL_BIT = 1
       if(gattprint_enabled):
           ENABLED_BITMASK |= 1 << GATT_BIT
           if(bdaddr in gatt_success_bdaddrs.keys()):
               COMPLETE_BITMASK |= 1 << GATT_BIT
       if(ble_2thprint_enabled):
           ENABLED_BITMASK |= 1 << LL_BIT
           if(bdaddr in ll2thprint_success_bdaddrs.keys()):
               COMPLETE_BITMASK |= 1 << LL_BIT

       if(ENABLED_BITMASK == COMPLETE_BITMASK):
           # 2thprintTarget.py-specific behavior. Don't copy over to CAL2.py
           print("All enabled BLE 2thprints collected! Exiting BLE thread.")
           exit()
#           return True
       else:
           return False

   elif(type == "BTC"):
       SDP_BIT = 0
       LMP_BIT = 1
       if(sdpprint_enabled):
           ENABLED_BITMASK |= 1 << SDP_BIT
           if(bdaddr in sdp_success_bdaddrs.keys()):
               COMPLETE_BITMASK |= 1 << SDP_BIT
       if(btc_2thprint_enabled):
           ENABLED_BITMASK |= 1 << LMP_BIT
           if(bdaddr in lmp2thprint_success_bdaddrs.keys()):
               COMPLETE_BITMASK |= 1 << LMP_BIT

       if(ENABLED_BITMASK == COMPLETE_BITMASK):
           # 2thprintTarget.py-specific behavior. Don't copy over to CAL2.py
           print("All enabled BTC 2thprints collected! Exiting BTC thread.")
           exit()
#           return True
       else:
           return False

class ApplicationThread(threading.Thread):
    def __init__(self, process, bdaddr, info_type, timeout):
        threading.Thread.__init__(self)
        self.process = process
        self.timeout = timeout
        self.is_terminated = False
        self.bdaddr = bdaddr
        self.info_type = info_type

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
                    elif(self.info_type == "LL2thprint"):
                       with ll2thprint_success_bdaddrs_lock:
                           ll2thprint_success_bdaddrs[self.bdaddr] = 1
                           if(print_finished_bdaddrs): print(f"Successful LL2thprinting of {self.bdaddr}!")
                           if(all_2thprints_done("BLE", self.bdaddr)):
                               locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, self.bdaddr)
                               if(print_verbose): print(f"All 2thprints collected! Deleting {self.bdaddr} from ble_bdaddrs!")
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
                       external_log_write(sdpprint_log_path, f"SNIFFLE LAUNCH SUCCESS: {self.bdaddr} {datetime.datetime.now()}") # Abusing bdaddr to treat it as an arbitrary string for Sniffle instances

                else:
                    if(self.info_type == "GATT"):
                       external_log_write(gattprint_log_path, f"GATTPRINTING FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "LMP2thprint"):
                       external_log_write(btc2thprint_log_path, f"BTC_2THPRINT: FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "SDP"):
                       external_log_write(sdpprint_log_path, f"SDPPRINTING FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")
                    elif(self.info_type == "Sniffle"):
                       external_log_write(sniffle_log_path, f"SNIFFLE LAUNCH FAILURE 0x{retCode:02x} FOR: {self.bdaddr} {datetime.datetime.now()}")

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
               external_log_write(sniffle_log_path, f"SNIFFLE FAILURE TIMEOUT FOR: {self.bdaddr} {datetime.datetime.now()}")


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
    print(f"UNRECOVERABLE ERROR. exiting at {datetime.datetime.now()}")
    exit()

##################################################
# BLE-handling thread
##################################################

# Function for the first thread
def ble_thread_function():
    global device_ble_connect_attempts
    ble_external_tool_threads = []
    while True:
        # Get the BDADDRs sorted in descending order of their RSSI, so we process higher RSSI first
        sorted_ble_bdaddrs = sorted(ble_bdaddrs.keys(), key=lambda x: ble_bdaddrs[x][1], reverse=True)

        if(print_verbose):
            print(f"Begin loop through sorted_ble_bdaddrs {datetime.datetime.now()}")
            print(f"sorted_ble_bdaddrs = {sorted_ble_bdaddrs}")

        skip_count = int(0)
        for bdaddr in sorted_ble_bdaddrs:
            # Skip devices that may be traveling with us, to not waste time on them
            # Only try collecting data from a given bd_addr max_connect_attempts times before skipping forever thereafter
            # This is so that we don't waste time trying to get info from something that will never give it to us,
            # when we could be spending that time trying new devices
            if((str(bdaddr).lower() in skip_these_addresses) or (device_ble_connect_attempts[bdaddr] >= max_connect_attempts)):
                if(print_skipped):
                    print(f"BLE: Max connect attempts ({max_connect_attempts}) exceeded for {bdaddr}, skipping")
                skip_count += 1
                if(print_skipped):
                    print(f"BLE: skip_count = {skip_count} of {len(sorted_ble_bdaddrs)}")

                # Delete it otherwise it will just keep coming up over and over again in the while True loop
                locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, bdaddr)

                if(skip_count == len(sorted_ble_bdaddrs)):
                    print("BLE: Everything's being skipped. Exiting.")
                    exit()

                continue
            else:
                device_ble_connect_attempts[bdaddr] += 1
                if(print_verbose): print(f"device_ble_connect_attempts {bdaddr} incremented to {device_ble_connect_attempts[bdaddr]} from BLE attempt.")

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
                        skip_sub_process = True # We can't just 'continue' here or we'd skip attempting the ll2thprint below

                # We have to check whether bdaddr is still in ble_bdaddrs because it could have been deleted via finding a [DEL] in the bluetoothctl log
                # This is a race condition...
                if(not skip_sub_process and bdaddr in ble_bdaddrs):
                    with ble_bdaddrs_lock:
                        if(bdaddr in ble_bdaddrs):
                            external_log_write(gattprint_log_path, f"GATTPRINTING ATTEMPT FOR: {bdaddr} {datetime.datetime.now()}")
                            (type, rssi) = ble_bdaddrs[bdaddr]
                            gatt_cmd = [gatttool_exec_path, "-t", type, "-b", bdaddr]
                            try:
                                gatt_process = launch_application(gatt_cmd, default_cwd)
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


            if(ble_2thprint_enabled):
                skip_sub_process = False
                with ll2thprint_success_bdaddrs_lock:
                    if(bdaddr in ll2thprint_success_bdaddrs.keys()):
                        if(print_finished_bdaddrs): print(f"We've already successfully LL2thprinted {bdaddr}! Skipping!")
                        # Remove it from further consideration (it could have just been added in by a [DEL] -> [NEW] sequence)
                        if(all_2thprints_done("BLE", bdaddr)):
                            locked_delete_from_dict(ble_bdaddrs, ble_bdaddrs_lock, bdaddr)
                            if(print_finished_bdaddrs): print(f"All 2thprints collected! Deleting {bdaddr} from ble_bdaddrs!")
                        skip_sub_process = True # We can't just 'continue' here for generalism, for if we add more stuff beyond this

                if(not skip_sub_process and bdaddr in ble_bdaddrs): # Double check that bdaddr hasn't been deleted out of ble_bdaddrs by a [DEL]
                    ble_2thprint_cmd = [python2, ble2thprint, dongle1, bdaddr]
                    try:
                        ble_2thprint_process = launch_application(ble_2thprint_cmd, sweyn_cwd)
                    except BlockingIOError as e:
                        print(f"Caught BlockingIOError while launching LL2thprint application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()
                    except Exception as e:
                        print(f"Caught an exception while launching LL2thprint application: {e}")
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()

                    if(ble_2thprint_process != None):
                        ble_2thprint_thread = ApplicationThread(ble_2thprint_process, bdaddr, info_type="LL2thprint", timeout=10)
                        try:
                            ble_2thprint_thread.start()
                            ble_external_tool_threads.append(ble_2thprint_thread)
                        except Exception as e:
                            print(f"Caught an exception while starting LL2thprint thread: {e}")
                            # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                            force_reboot()


            # Wait for all threads to finish, before moving to the next bd_addr
            for thread in ble_external_tool_threads:
                thread.join(timeout=10) # Timeout here needs to be set to the maximum timeout of all the sub-types
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
    global device_btc_connect_attempts
    btc_external_tool_threads = []
    while True:
        # Get the BDADDRs sorted in descending order of their RSSI, so we process higher RSSI first
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
            if((str(bdaddr).lower() in skip_these_addresses) or (device_btc_connect_attempts[bdaddr] >= max_connect_attempts)):
                if(print_skipped):
                    print(f"BTC: Max connect attempts ({max_connect_attempts}) exceeded for {bdaddr}, skipping")
                skip_count += 1
                if(print_skipped):
                    print(f"BTC: skip_count = {skip_count} of {len(sorted_btc_bdaddrs)}")

                # Delete it otherwise it will just keep coming up over and over again in the while True loop
                locked_delete_from_dict(btc_bdaddrs, btc_bdaddrs_lock, bdaddr)

                if(skip_count == len(sorted_btc_bdaddrs)):
                    print("BLE: Everything's being skipped. Exiting.")
                    exit()

                continue
            else:
                device_btc_connect_attempts[bdaddr] += 1
                if(print_verbose): print(f"device_btc_connect_attempts {bdaddr} incremented to {device_btc_connect_attempts[bdaddr]} from BTC attempt.")

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
#                    btc_2thprint_cmd = [braktooth, "--exploit=LMP2thprint", "--target={}".format(bdaddr)]
                    btc_2thprint_cmd = [braktooth, "--exploit=test2", "--target={}".format(bdaddr)]
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
                thread.join(timeout=15) # Timeout here needs to be set to the maximum timeout of all the sub-types

            #if(print_verbose): print(f"BTC Address: {bdaddr}")

        print(f"Finished one complete loop through sorted_btc_bdaddrs {datetime.datetime.now()}")
        # Busy wait until the diciontary has entries to process before proceeding again
        while(len(btc_bdaddrs) == 0):
            pass
        #time.sleep(5)

##################################################
# Sniffle-handling thread
##################################################

pcap_names = []

# Function for the Sniffle thread(s)
def sniffle_thread_function():
    global pcap_names
    Sniffle_sniffer_threads = []
    adv_channel = 0 # This will be used as 37 + adv_channel++ mod 3, so that possible values are only 37, 38, and 39

    base_dir = '/dev/serial/by-id'
    # Note: this would need to be changed to use other TI dev boards instead. For now I won't support that for simplicity
    pattern = 'usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus*'

    # Check if the base directory exists and is accessible
    if os.path.isdir(base_dir) and os.access(base_dir, os.R_OK):
        # Construct the full pattern path
        full_pattern = os.path.join(base_dir, pattern)

        # Use glob to match the pattern
        matching_files = glob.glob(full_pattern)

        # Print the list of matching files
        if matching_files:
            for serial_file in matching_files:
                toks = serial_file.split("_")
                toks2 = toks[7].split("-")
                pcap_short_name = f"{toks[1]}_{toks2[0]}" # Like "Sonoff_<IDstring>" # TODO: this would need to be fixed if we support things other than Sonoff
                if(print_verbose): print(f"Found viable Sniffle dongle: {serial_file}")
                target_adv_channel = 37 + adv_channel
                adv_channel = (adv_channel + 1) % 3
                # Launch the sniffer as a background thread
                # For some reason when launched this way it requires the = character instead of space (which is allowed when normally launching)
                # (Otherwise it seems to be parsing the file name with a space in front of it, and then erroring out and saying no such file.)
                time = datetime.datetime.now()
                formatted_time = time.strftime('%Y-%m-%d-%H-%M-%S')
                pcap_name = f"{sniffle_pcaps_path}/{formatted_time}_{pcap_short_name}.pcap"
                pcap_names.append(pcap_name)
                # If we have at least 3 available sniffers, spread them evenly around the channels
                # Otherwise, let them default to all-channel-hopping (to increase the chance of catching CONNECT_INDs)
                if(len(matching_files) >= 3):
                    sniffle_cmd = ["python3", sniffle_path, f"-s={serial_file}", f"-o={pcap_name}", f"-c={target_adv_channel}"]
                else:
                    sniffle_cmd = ["python3", sniffle_path, f"-s={serial_file}", f"-o={pcap_name}"]
                try:
                    # Redirect the stdout output to /dev/null since it's not useful in this context and we don't want to interleave it with other 2thprinting stdout content
                    sniffle_stdout = open(f"{sniffle_log_path}", "a") # redirect stdout to an output log file just in case it's needed for debugging
                    sniffle_process = launch_application(sniffle_cmd, default_cwd, stdout=sniffle_stdout)
                except BlockingIOError as e:
                    print(f"Caught BlockingIOError while launching Sniffle application: {e}") # This seems to be due to a rare error while attempting a fork() within Popen()
                    # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                    force_reboot()
                except Exception as e:
                    print(f"Caught an exception while launching Sniffle application: {e}")
                    # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                    force_reboot()

                if(sniffle_process != None):
                    # FIXME: (Not accurate anymore anyway) Abusing the bdaddr field since we're not targeting a specific bdaddr for sniffing, so I just wanted somewhere to put a string
                    individual_sniffle_instance_thread = ApplicationThread(sniffle_process, bdaddr=f"-c={target_adv_channel} -s={serial_file}", info_type="Sniffle", timeout=3600)
                    try:
                        individual_sniffle_instance_thread.start()
                        Sniffle_sniffer_threads.append(individual_sniffle_instance_thread)
                    except Exception as e:
                        print(f"Caught an exception while starting Sniffle thread: {e}")
                        # This doesn't seem to ever resolve itself for hours after it eventually occurs (which takes about 5 hours). So I need to just reboot to resolve it
                        force_reboot()
        else:
            if(print_verbose): print("No matching files found.")
    else:
        if(print_verbose): print(f"The directory {base_dir} does not exist or is not accessible.")

##################################################
# main()
##################################################

def print_results(_2thprint_name, thread_enable_flag, enable_flag, list):
    if(thread_enable_flag and enable_flag):
        if(len(list) > 0):
            print(f"{_2thprint_name} successful!")
        else:
            print(f"{_2thprint_name} unsuccessful :(")
    else:
        print(f"{_2thprint_name} not enabled")

def main():
    global device_ble_connect_attempts
    global btc_bdaddrs
    global ble_bdaddrs
    global max_connect_attempts
    global pcap_names
    global print_verbose
    main_threads = []

    print("========================================================================================================================")
    print(f"2thprintTarget.py started at {datetime.datetime.now()}")
    print("========================================================================================================================")

    if(len(sys.argv) < 4):
        print("Not enough parameters.")
        print("Usage: 2thprintTarget.py <max_connect_attempts> <BDADDR> <type of \"public\" or \"random\">")
        exit()

    max_connect_attempts = int(sys.argv[1], 10)

    bdaddr_target = sys.argv[2].lower()
    bdregex = r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$'
    if(re.match(bdregex, bdaddr_target) is None):
        print("Incorrect BDADDR format. Must be in standard colon-deliminated form like 12:34:56:78:90:ab")
        print("Usage: 2thprintTarget.py <max_connect_attempts> <BDADDR> <type of \"public\" or \"random\">")
        exit()

    bdaddr_type = sys.argv[3].lower()
    if(bdaddr_type != "public" and bdaddr_type != "random"):
        print("Incorrect BDADDR type. Must be either the string \"public\" or \"random\" (without quotes).")
        print("Usage: 2thprintTarget.py <max_connect_attempts> <BDADDR> <type of \"public\" or \"random\">")
        exit()

    print(f"Targeting BDADDR {bdaddr_target} of type {bdaddr_type} for {max_connect_attempts} maximum number of connection attempts")
    print("========================================================================================================================")

    ble_thread = threading.Thread(target=ble_thread_function)
    btc_thread = threading.Thread(target=btc_thread_function)
    sniffle_thread = threading.Thread(target=sniffle_thread_function)

    # Treat "public" type as if it could be BLE or it could be BTC, and try both
    # But "random" type must be BLE only, so don't bother starting BTC
    # (AppleTV is a good example of something where the public address is used for both BLE & BTC)
    # Don't bother starting BTC thread if there's nothing enabled; it would just lead to unnecessary output
    if(BTC_thread_enabled and (sdpprint_enabled or btc_2thprint_enabled) and bdaddr_type == "public"):
        device_btc_connect_attempts[bdaddr_target] = 0
        btc_bdaddrs[bdaddr_target] = (bdaddr_type, -80) # Placeholder RSSI. It doesn't really matter in this code
        btc_thread.start()
        main_threads.append(btc_thread)

    # Don't bother starting BLE thread if there's nothing enabled; it would just lead to unnecessary output
    if(BLE_thread_enabled and (gattprint_enabled or ble_2thprint_enabled)):
        device_ble_connect_attempts[bdaddr_target] = 0
        ble_bdaddrs[bdaddr_target] = (bdaddr_type, -80) # Placeholder RSSI. It doesn't really matter in this code
        ble_thread.start()
        main_threads.append(ble_thread)

    if(Sniffle_thread_enabled):
        sniffle_thread.start()
        main_threads.append(sniffle_thread)

    # Wait for all the above main threads to complete, and then report the status of their respective success or failures
    for thread in main_threads:
        thread.join()
        if(print_verbose): print(f"Successfully joined thread {thread}")

    print("Results:")
    print_results("SDPPrinting", BTC_thread_enabled, sdpprint_enabled, sdp_success_bdaddrs)
    print_results("BTC2thprinting", BTC_thread_enabled, btc_2thprint_enabled, lmp2thprint_success_bdaddrs)
    print_results("GATTPrinting", BLE_thread_enabled, gattprint_enabled, gatt_success_bdaddrs)
    print_results("BLE2thprinting", BLE_thread_enabled, ble_2thprint_enabled, ll2thprint_success_bdaddrs)

    if(Sniffle_thread_enabled and len(pcap_names) > 0):
        print(f"Sniffle is enabled and logging to the following files:")
        for pcap_name in pcap_names:
            print(f"\t{pcap_name}")
        print(f"\tstdout logging to {sniffle_log_path}")
        print(f"Hit ctrl-c to exit.")

if __name__ == "__main__":
    main()
