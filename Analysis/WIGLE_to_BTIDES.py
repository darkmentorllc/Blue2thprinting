########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# Activate venv before any other imports
from handle_venv import activate_venv
activate_venv()
import argparse

# HCI file reading related adapter to feed into scapy
import btsnoop.btsnoop.btsnoop as bts
#import mybtsnoop as bts

# Scapy related
from scapy.layers.bluetooth4LE import *
from scapy.layers.bluetooth import *
from scapy.all import *

# Common code for BTIDES export assuming scapy formatted input data structures
from scapy_to_BTIDES_common import *

# BTIDES format related
import TME.TME_glob
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements
from TME.TME_helpers import qprint, vprint
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_base import write_BTIDES
from TME.TME_BTIDES_GPS import BTIDES_export_GPS_coordinate

# BTIDALPOOL access related
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

import sqlite3
import mysql.connector

def find_bdaddr_rand(bdaddr):
    if(TME.TME_glob.use_test_db):
        database = 'bttest'
    else:
        database = 'bt2'

    conn = mysql.connector.connect(
        host='localhost',
        user='user',
        password='a',
        database=database,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        auth_plugin='mysql_native_password'
    )
    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    bdaddr_rand_count = {0: 0, 1: 0}

    # TODO: change to a union statement across all tables, to cut down on DB connection traffic
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = cursor.fetchall()

        if any(column[0] == "bdaddr_random" for column in columns):
            values = (bdaddr,)
            # table_name is not ACID, so it's OK to interpolate it directly in
            # (because otherwise there's a syntax error due to the prepared statement
            # wrapping the table name in single quotes...
            query = f"SELECT bdaddr_random FROM {table_name} where bdaddr = %s LIMIT 1"
            cursor.execute(query, values)
            rows = cursor.fetchall()
            for row in rows:
                bdaddr_rand = row[0]
                if bdaddr_rand in bdaddr_rand_count:
                    bdaddr_rand_count[bdaddr_rand] += 1

    conn.close()

    if(bdaddr_rand_count[0] == bdaddr_rand_count[1]):
        most_common_bdaddr_rand = 1 # If there's no results in our DB, just say it's a random address, since that's statistically most likely
    else:
        most_common_bdaddr_rand = max(bdaddr_rand_count, key=bdaddr_rand_count.get)
    return most_common_bdaddr_rand

    # return 1

def read_WiGLE_DB(input, gps_exclude_upper_left=None, gps_exclude_lower_right=None, get_all_GPS=False, offset=0, limit=None):
    try:
        sqlite_conn = sqlite3.connect(input)
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_conn.commit()
        query = "SELECT * FROM network WHERE (type = 'B' or type = 'E')"
        values = ()
        if(gps_exclude_upper_left and gps_exclude_lower_right):
            lower_lon = min(gps_exclude_upper_left[1], gps_exclude_lower_right[1])
            upper_lon = max(gps_exclude_upper_left[1], gps_exclude_lower_right[1])
            lower_lat = min(gps_exclude_upper_left[0], gps_exclude_lower_right[0])
            upper_lat = max(gps_exclude_upper_left[0], gps_exclude_lower_right[0])
            query += " AND (bestlat NOT BETWEEN ? AND ?) AND (bestlon NOT BETWEEN ? AND ?)"
            values += (lower_lat, upper_lat, lower_lon, upper_lon)
        if(limit):
            query += " LIMIT ?"
            values += (limit,)
        if(offset > 0):
            query += " OFFSET ?"
            values += (offset,)
        sqlite_cursor.execute(query, values)
        rows = sqlite_cursor.fetchall()
    except sqlite3.DatabaseError as e:
        print(f"Error: {e}")
        return

    # TODO: add progress tracker

    i = 0
    for row in rows:
        if i % max(1, len(rows) // 100) == 0:
            qprint(f"Processed {i} out of {len(rows)} records ({(i / len(rows)) * 100:.0f}%)")
        i+=1

        # TODO: how to extract these directly from the schema in case it changes?
        bssid_ACID = row[0]
        name = row[1]
        time = row[4]
        last_lat = row[5]
        last_lon = row[6]
        type = row[7]
        best_lat = row[9]
        best_lon = row[10]

        # Skip processing if any of the lat/lon values are infinite or all zero
        if any(map(math.isinf, [last_lat, last_lon, best_lat, best_lon])):
            continue

        if type == "B":
            bdaddr = bssid_ACID
            bdaddr_rand = 0
        elif type == "E":
            bdaddr = bssid_ACID
            bdaddr_rand = find_bdaddr_rand(bdaddr)
        else:
            continue

        # Process the record as needed
        vprint(f"bdaddr: {bdaddr}, bdaddr_rand: {bdaddr_rand}")

        data = {"time": {"unix_time_milli": time}}

        if(best_lat and best_lon):
            vprint(f"{i1}Best GPS location: lat: {best_lat}, lon: {best_lon}")
            data["lat"] = best_lat
            data["lon"] = best_lon
        elif(last_lat and last_lon):
            vprint(f"{i1}Last GPS location: lat: {last_lat}, lon: {last_lon}")
            data["lat"] = last_lat
            data["lon"] = last_lon
        else:
            vprint(f"{i1}No GPS location found")
            continue

        # Check for invalid GPS coordinates and skip if found (apparently these can exist in the DB. Not sure why though.)
        if data["lat"] > 90.0 or data["lat"] < -90.0 or data["lon"] > 180.0 or data["lon"] < -180.0:
            vprint(f"{i1}Invalid GPS coordinates found, skipping")
            continue

        # See if there's any RSSI in the location table for this exact GPS coordinate (irrespective of time)
        query = "SELECT * FROM location WHERE bssid = ? AND lat = ? AND lon = ?"
        values = (bssid_ACID, data["lat"], data["lon"])
        sqlite_cursor.execute(query, values)
        locations = sqlite_cursor.fetchall()
        best_rssi = -127
        for location in locations:
            # Only update if we find a better RSSI
            if(location[2] > best_rssi):
                best_rssi = location[2]
                data["rssi"] = location[2]

        # Export the coordinate now that we have the best-case data
        BTIDES_export_GPS_coordinate(bdaddr=bdaddr, random=bdaddr_rand, data=data)

        if(name != ""):
            vprint(f"{i1}Name: {name}")
            # Just going to hardcode a HCI_Remote_Name_Request_Complete since it's an example where we
            # have the name but not much else to go on...
            export_Remote_Name_Request_Complete(bdaddr, str_to_hex_str(name))

        if(get_all_GPS):
            query = "SELECT * FROM location WHERE bssid = ?"
            values = (bssid_ACID,)
            sqlite_cursor.execute(query, values)
            locations = sqlite_cursor.fetchall()
            for location in locations:
                rssi = location[2]
                lat = location[3]
                lon = location[4]
                time = location[7]
                data = {"time": {"unix_time_milli": time}, "rssi": rssi, "lat": lat, "lon": lon}
                BTIDES_export_GPS_coordinate(bdaddr=bdaddr, random=bdaddr_rand, data=data)

    sqlite_conn.close()


def main():
    global verbose_print, verbose_BTIDES, use_test_db
    parser = argparse.ArgumentParser(description='WiGLE Database Backup file input arguments')
    parser.add_argument('--input', type=str, required=True, help='Input file name for WiGLE Database Backup file.')
    parser.add_argument('--offset', type=str, required=False, help='Offset into the WiGLE Database Backup file to start importing from. Useful for reading large files in chunks.')
    parser.add_argument('--limit', type=str, required=False, help='Limit of how many entries to import from the WiGLE Database Backup file. Useful for reading large files in chunks.')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')
    btides_group.add_argument('--GPS-exclude-upper-left', type=str, required=False, help='The coordinate for the upper left corner of the bounding box to exclude from the BTIDES output, in \"(lat,lon)\" format. E.g. \"(39.171951,-77.615936)\"')
    btides_group.add_argument('--GPS-exclude-lower-right', type=str, required=False, help='The coordinate for the lower right corner of the bounding box to exclude from the BTIDES output, in \"(lat,lon)\" format. E.g. \"(38.568929,-76.385467)\"')
    btides_group.add_argument('--get-all-GPS', action='store_true', required=False, help='This will extract every GPS coordinate found for the given BDADDR in the WiGLE database, not just the trilaterated \"best\" one. This will potentially take a *lot* longer, based on how many records exist in your database.')

    # SQL arguments
    sql = parser.add_argument_group('Local SQL database storage arguments (only applicable in the context of a local Blue2thprinting setup, not 3rd party tool usage.)')
    sql.add_argument('--to-SQL', action='store_true', required=False, help='Store output BTIDES file to your local SQL database.')
    sql.add_argument('--rename', action='store_true', required=False, help='Rename the output file to output.processed if used in conjunction with --to-SQL')
    sql.add_argument('--use-test-db', action='store_true', required=False, help='This will utilize the alternative bttest database, used for testing.')

    # BTIDALPOOL arguments
    btidalpool_group = parser.add_argument_group('BTIDALPOOL (crowdsourced database) arguments')
    btidalpool_group.add_argument('--to-BTIDALPOOL', action='store_true', required=False, help='Send output BTIDES data to the BTIDALPOOL crowdsourcing SQL database.')
    btidalpool_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')

    printout_group = parser.add_argument_group('Print verbosity arguments')
    printout_group.add_argument('--verbose-print', action='store_true', required=False, help='Show explicit data-not-found output.')
    printout_group.add_argument('--quiet-print', action='store_true', required=False, help='Hide all print output (useful when you only want to use --output to export data).')

    args = parser.parse_args()

    out_BTIDES_filename = args.output
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES
    TME.TME_glob.use_test_db = args.use_test_db

    if(not args.offset):
        args.offset = 0
    if(not args.limit):
        args.limit = 999999999

    if not os.path.isfile(args.input):
        print(f"Error: file {input} does not exist.")
        return
    if(args.GPS_exclude_upper_left and not args.GPS_exclude_lower_right or args.GPS_exclude_lower_right and not args.GPS_exclude_upper_left):
        print("Error: If you specify either GPS exclude option, you must specify both.")
        return

    qprint("Reading all Bluetooth entries from WiGLE SQLite database into memory.")
    if(args.GPS_exclude_upper_left and args.GPS_exclude_lower_right):
        upper_left_tuple = tuple(map(float, args.GPS_exclude_upper_left.strip('()').split(',')))
        lower_right_tuple = tuple(map(float, args.GPS_exclude_lower_right.strip('()').split(',')))
        if(len(upper_left_tuple) != 2 or len(lower_right_tuple) != 2):
            print("Error: GPS exclude coordinates must be in the form of \"(lat,lon)\".")
            return
        read_WiGLE_DB(input=args.input, gps_exclude_upper_left=upper_left_tuple, gps_exclude_lower_right=lower_right_tuple, get_all_GPS=args.get_all_GPS, offset=int(args.offset), limit=int(args.limit))
    else:
        read_WiGLE_DB(input=args.input, get_all_GPS=args.get_all_GPS, offset=int(args.offset), limit=int(args.limit))

    qprint("Writing BTIDES data to file.")
    write_BTIDES(out_BTIDES_filename)
    qprint("Export completed with no errors.")

    btides_to_sql_succeeded = False
    if args.to_SQL:
        b2s_args = btides_to_sql_args(input=out_BTIDES_filename, use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print)
        btides_to_sql_succeeded = btides_to_sql(b2s_args)

    if args.to_BTIDALPOOL:
        # If the token isn't given on the CLI, then redirect them to go login and get one
        client = AuthClient()
        if args.token_file:
            with open(args.token_file, 'r') as f:
                token_data = json.load(f)
            token = token_data['token']
            refresh_token = token_data['refresh_token']
            client.set_credentials(token, refresh_token, token_file=args.token_file)
            if(not client.validate_credentials()):
                print("Authentication failed.")
                exit(1)
        else:
            try:
                if(not client.google_SSO_authenticate() or not client.validate_credentials()):
                    print("Authentication failed.")
                    exit(1)
            except ValueError as e:
                print(f"Error: {e}")
                exit(1)

        # Use the copy of token/refresh_token in client.credentials, because it could have been refreshed inside validate_credentials()
        send_btides_to_btidalpool(
            input_file=out_BTIDES_filename,
            token=client.credentials.token,
            refresh_token=client.credentials.refresh_token
        )

    if(btides_to_sql_succeeded and args.rename):
        os.rename(out_BTIDES_filename, out_BTIDES_filename + ".processed")

if __name__ == "__main__":
    main()