from bluepy.btle import Scanner, DefaultDelegate, BTLEDisconnectError, BTLEManagementError
import subprocess
import os
import sys
import threading
import time
from bluetooth.ble import DiscoveryService

# TODO: Update the username when copying this to other systems
username = "user"
gatttoolpath = "/home/{}/Downloads/bluez-5.66/attrib/gatttool".format(username)
directory = "/home/{}/Downloads/bluez-5.66/attrib/".format(username)
logfile = "/home/{}/GATTprint.log".format(username)

device_connect_attempts = {}
max_connect_attempts = 5

service = DiscoveryService()
devices = service.discover(2)

for address, name in devices.items():
    print("Name: {}, address: {}".format(name, address))


while True:
	# Execute the command within the lock
	try:
		with open(logfile, 'a') as file:
			start_time = time.time()
			addr = "6C:4A:85:2C:C3:A9"
			addrType = "public"
			print("GATTPRINT_LOG_START_{}_{}_{}".format(start_time, addr, addrType))
			file.write("GATTPRINT_LOG_START_{}_{}_{}\n".format(start_time, addr, addrType))
			file.flush()

			command = [gatttoolpath, "-t", "public", "-b", "6C:4A:85:2C:C3:A9"]

			print("Executing '{}'".format(command))

			process = subprocess.Popen(command, cwd=directory)

			'''
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

			'''
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
				file.write("GATTPRINT_{} GATTPRINTING TERMINATED DUE TO 10 SEC TIMEOUT\n".format(addr))
				file.flush()

			# Wait for the process to finish
			process.wait()

	except IOError as a:
		print("Error opening file:", str(a))
