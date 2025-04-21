########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
#from TME.TME_metadata import *
#from TME.TME_AdvChan import *
from TME.TME_BTIDES_GPS import BTIDES_export_GPS_coordinate
from datetime import datetime

###########################################
# Print GPS information, if present
###########################################

def device_has_GPS(bdaddr):
    values = (bdaddr,)
    # The WiGLE data is not capable of distinguishing between Classic and LE,
    # so we need to check the bdaddr_random value for both Classic and LE
    select_query = f"SELECT time FROM bdaddr_to_GPS WHERE bdaddr = %s;"
    select_results = execute_query(select_query, values)
    if (len(select_results) == 0):
        return False
    else:
        return True

time_type_to_str = {
    0: "unix_time",
    1: "unix_time_milli",
    2: "time_str1"
}

def print_GPS_time(indent, time, time_type):
    if time_type == 1:  # unix_time_milli
        time_formatted = datetime.utcfromtimestamp(time / 1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        qprint(f"{indent}Time: {time} ({time_type_to_str[time_type]}, {time_formatted})")
    else:
        qprint(f"{indent}Time: {time} ({time_type_to_str[time_type]})")

def print_RSSI(indent, rssi):
    if(rssi == 0):
        qprint("{indent}RSSI: Not available")
    else:
        qprint(f"{indent}RSSI: {rssi}")

def print_GPS_entries(indent, results, bdaddr):
    for(bdaddr_random, time, time_type, rssi, lat, lon) in results:
        print_GPS_time(indent, time, time_type)
        print_RSSI(indent, rssi)
        qprint(f"{indent}Latitude,Longitude: {lat},{lon}")
        qprint("")
        # Export as BTIDES
        if(time_type == 1):
            time_dict = {"unix_time_milli": time}
        data = {"lat": lat, "lon": lon, "time": time_dict, "rssi": rssi}
        BTIDES_export_GPS_coordinate(bdaddr=bdaddr, random=bdaddr_random, data=data)

def print_GPS(bdaddr):
    qprint("\tGPS coordinates:")
    values = (bdaddr,)
    # The WiGLE data is not capable of distinguishing between Classic and LE,
    # so we need to not constraint it based on the bdaddr_random value, to get both Classic and LE
    select_query = f"SELECT bdaddr_random, time, time_type, rssi, lat, lon FROM bdaddr_to_GPS WHERE bdaddr = %s;"
    select_results = execute_query(select_query, values)

    indent = "\t\t"
    if (len(select_results) == 0):
        qprint(f"{indent}No GPS data present for this device.)")
        return

    print_GPS_entries(indent, select_results, bdaddr)

    qprint("")
