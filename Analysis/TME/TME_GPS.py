########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from datetime import datetime

from TME.TME_helpers import *
from TME.TME_BTIDES_GPS import BTIDES_export_GPS_coordinate
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

###########################################
# Print GPS information, if present
###########################################

# If there exists any GPS coordinates for the given bdaddr within the exclusion box,
# return True, otherwise return False.
def is_GPS_coordinate_within_exclusion_box(bdaddr, gps_exclude_upper_left_tuple, gps_exclude_lower_right_tuple):
    select_query = f"SELECT lat, lon FROM bdaddr_to_GPS WHERE bdaddr = %s;"
    select_results = execute_query(select_query, (bdaddr,))
    for lat, lon in select_results:
        if (gps_exclude_upper_left_tuple[0] >= lat >= gps_exclude_lower_right_tuple[0] and
            gps_exclude_upper_left_tuple[1] <= lon <= gps_exclude_lower_right_tuple[1]):
            return True

    return False

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
        qprint(f"{indent}Latitude, Longitude: {lat}, {lon}")
        qprint(f"{indent}https://www.google.com/maps/place/{lat},{lon}")
        # Export as BTIDES
        if(time_type == 1):
            time_dict = {"unix_time_milli": time}
        data = {"lat": lat, "lon": lon, "time": time_dict, "rssi": rssi}
        BTIDES_export_GPS_coordinate(bdaddr=bdaddr, random=bdaddr_random, data=data)

def print_GPS(bdaddr):
    values = (bdaddr,)
    # The WiGLE data is not capable of distinguishing between Classic and LE,
    # so we need to not constraint it based on the bdaddr_random value, to get both Classic and LE
    select_query = f"SELECT bdaddr_random, time, time_type, rssi, lat, lon FROM bdaddr_to_GPS WHERE bdaddr = %s;"
    select_results = execute_query(select_query, values)

    if (len(select_results) == 0):
        vprint(f"{i1}No GPS data present for this device.")
        return
    else:
        qprint(f"{i1}GPS coordinates:")

    print_GPS_entries(f"{i2}", select_results, bdaddr)

    qprint("")
