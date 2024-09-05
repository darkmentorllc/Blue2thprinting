from bluepy.btle import Scanner, DefaultDelegate, BTLEDisconnectError, BTLEManagementError
import subprocess
import os
import sys
import threading

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.lock = threading.Lock()

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            print("Discovered device:", dev.addr)
            command = ["python", "/home/user/Downloads/sweyntooth_bluetooth_low_energy_attacks/two2thprint.py", "/dev/ttyACM0", dev.addr]

            # Execute the command within the lock
            with self.lock:
                try:
                    process = subprocess.Popen(command)

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
