#!/usr/bin/env python3

# Written by Sultan Qasim Khan
# Copyright (c) 2020-2025, NCC Group plc
# Released as open source under GPLv3

import argparse
from time import sleep
from sniffle.sniffle_hw import SniffleHW

def main():
    aparse = argparse.ArgumentParser(description="Firmware reset utility for Sniffle BLE5 sniffer")
    aparse.add_argument("-s", "--serport", default=None, help="Sniffer serial port name")
    aparse.add_argument("-b", "--baudrate", default=None, help="Sniffer serial port baud rate")
    args = aparse.parse_args()

    hw = SniffleHW(args.serport, baudrate=args.baudrate)

    # 5 resets seems to work more reliably than fewer
    print("Sending reset commands...")
    for i in range(5):
        hw.ser.write(b'@@@@@@@@\r\n') # command sync
        hw.cmd_reset()
        sleep(0.02)

    # try a flush, see if we get a marker back to prove firmware liveness
    hw.ser.write(b'@@@@@@@@\r\n') # command sync
    print("Trying a mark and flush to get things flowing...")
    hw.mark_and_flush()
    print("Reset success.")

if __name__ == "__main__":
    main()
