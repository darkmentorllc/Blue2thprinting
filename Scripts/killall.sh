#!/bin/bash

#RESULT1=$(killall gpspipe)
RESULT2=$(killall btmon)
# bluetoothctl is no longer started by runall.sh — discovery is in-process via D-Bus (issue #47).
RESULT4=$(killall sudo)
RESULT5=$(killall python3)
RESULT6=$(killall sdptool)
RESULT7=$(pkill -u root bash)
