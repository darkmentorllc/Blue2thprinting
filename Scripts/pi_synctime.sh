#!/bin/bash

# The only point of this script is so that I don't need to remember the commands
# to synchronize the time on a Raspberry Pi, which has no RTC to maintain time
# Therefore this should be used when a device is put onto the network

sudo service ntp stop
sudo ntpd -gq
sudo service ntp start
