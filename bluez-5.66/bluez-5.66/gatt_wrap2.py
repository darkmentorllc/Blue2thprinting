from bluepy.btle import Scanner, DefaultDelegate, BTLEDisconnectError, BTLEManagementError
import subprocess
import os
import sys
import threading
import time

# TODO: Update the username when copying this to other systems
username = "user"
gatttoolpath = "/home/{}/Downloads/bluez-5.66/attrib/gatttool".format(username)
directory = "/home/{}/Downloads/bluez-5.66/attrib/".format(username)
logfile = "/home/{}/GATTprint.log".format(username)

device_connect_attempts = {}
max_connect_attempts = 5

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.lock = threading.Lock()

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            print("Discovered device:", dev.addr, dev.addrType)
            if(str(dev.addr).lower() != "6C:4A:85:2C:C3:A9".lower()):
                return

            device_connect_attempts[dev.addr] = device_connect_attempts.get(dev.addr, 0) + 1
            if(device_connect_attempts[dev.addr] >= max_connect_attempts):
                print("Max connect attempts exceeded for {}, skipping".format(dev.addr))
                return

            # Execute the command within the lock
            with self.lock:
                try:
                    with open(logfile, 'a') as file:
                        start_time = time.time()
                        print("GATTPRINT_LOG_START_{}_{}_{}".format(start_time, dev.addr, dev.addrType))
                        file.write("GATTPRINT_LOG_START_{}_{}_{}\n".format(start_time, dev.addr, dev.addrType))
                        file.flush()

                        command = [gatttoolpath, "-t", dev.addrType, "-b", dev.addr]

                        print("Executing '{}'".format(command))

                        process = subprocess.Popen(command, cwd=directory)

                        try:
                            stdout, stderr = process.communicate(timeout=5)
                            if stdout is not None:
                                print("STDOUT:", stdout.decode("utf-8"))
                            if stderr is not None:
                                print("STDERR:", stderr.decode("utf-8"))
                        except TimeoutExpired:
                            print("TimeoutExpired. Kill!")
                            process.kill()
                            stdout, stderr = process.communicate()

                        # Wait for the process to finish or timeout
                        timeout = 20

                        while time.time() - start_time < timeout:
                            print("time.time() - start_time = {}".format(time.time() - start_time))
                            if process.poll() is not None:  # Process has exited
                                break
                            time.sleep(0.1)  # Delay between checks

                        # Terminate the process if it is still running
                        if process.poll() is None:
                            print("killing pid=" + str(process.pid))
                            process.kill()
                            file.write("GATTPRINT_{} GATTPRINTING TERMINATED DUE TO 10 SEC TIMEOUT\n".format(dev.addr))
                            file.flush()

                        # Wait for the process to finish
                        process.wait()

                except IOError as a:
                    print("Error opening file:", str(a))
                    #quit()

                except BTLEDisconnectError:
                    print("Device disconnected. Skipping the command.")

                except BTLEManagementError as b:
                    if "Rejected" in str(b):
                        print("Failed to execute management command 'scanend'. Skipping the command.")

# Initialize scanner and delegate
scanner = Scanner().withDelegate(ScanDelegate())

# Scan for devices indefinitely
while True:
    try:
        devices = scanner.scan(4)  # Scan for 10 seconds
    except (BTLEDisconnectError, BTLEManagementError) as e:
        if "Device disconnected" in str(e):
            print("Device disconnected. Restarting the scanner.")
        elif "Rejected" in str(e):
            print("Failed to execute management command 'scanend'. Restarting the scanner.")
