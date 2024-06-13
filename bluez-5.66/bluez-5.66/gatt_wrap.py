from bluepy.btle import Scanner, DefaultDelegate, BTLEDisconnectError, BTLEManagementError
import subprocess
import os
import sys
import threading

username = "pi"
gatttoolpath = "/home/{}/Downloads/bluez-5.66/attrib/gatttool".format(username)
directory = "/home/{}/Downloads/bluez-5.66/attrib/".format(username)
logfile = "/home/{}/GATTprint.log".format(username)

device_connect_attempts = {}
max_connect_attempts = 3

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.lock = threading.Lock()

    # This is the callback for each discovered device
    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            if(str(dev.addr).lower() != "6C:4A:85:2C:C3:A9".lower()):
                return

            # This sets it to 1 if it was previously not present, and +=1 all other times.
            device_connect_attempts[dev.addr] = device_connect_attempts.get(dev.addr, 0) + 1
            if(device_connect_attempts[dev.addr] >= max_connect_attempts):
                print("Max connect attempts exceeded for {}, skipping".format(dev.addr))
                return

            print("Discovered device:", dev.addr)
#            command = [gatttoolpath, "-t", dev.addrType, "-b", dev.addr] # FAILING COMMAND
            command = [gatttoolpath, "-t", "public", "-b", "6C:4A:85:2C:C3:A9"] #PREVIOUSLY WORKING, BUT NO LONGER WORKING COMMAND!?

            print(command)

            # Execute the command within the lock
            with self.lock:
                try:
                    process = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()
                    print("STDOUT:", stdout.decode("utf-8"))
                    print("STDERR:", stderr.decode("utf-8"))

                    # Start a timer to terminate the process if it exceeds 5 seconds
                    timer = threading.Timer(10, process.terminate)
                    timer.start()

                    # Wait for the process to finish
                    process.wait()

                    # Cancel the timer if the process finished before the timeout
                    timer.cancel()

                except BTLEDisconnectError:
                    print("Device disconnected. Skipping the command.")

                except BTLEManagementError as e:
                    if "Rejected" in str(e):
                        print("Failed to execute management command 'scanend'. Skipping the command.")
                except Exception as f:
                    print("Error occurred:", str(f))

# Initialize scanner and delegate
scanner = Scanner().withDelegate(ScanDelegate())

# Scan for devices indefinitely
while True:
    try:
        devices = scanner.scan(10)  # Scan for 10 seconds
    except (BTLEDisconnectError, BTLEManagementError) as e:
        if "Device disconnected" in str(e):
            print("Device disconnected. Restarting the scanner.")
        elif "Rejected" in str(e):
            print("Failed to execute management command 'scanend'. Restarting the scanner.")
