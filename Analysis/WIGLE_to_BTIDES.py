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
from TME.TME_helpers import qprint, vprint
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_base import write_BTIDES

# BTIDALPOOL access related
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool
import sqlite3
import mysql.connector

def BTIDES_export_GPS_coordinate(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "GPSArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "GPSArray")

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

def read_WiGLE_DB(input):
    try:
        sqlite_conn = sqlite3.connect(input)
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_conn.commit()
        sqlite_cursor.execute("SELECT * FROM network WHERE type = 'B' or type = 'E'")
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
        # if(i == 1000):
        #     return

        # TODO: how to extract these directly from the schema in case it changes?
        bssid_ACID = row[0]
        name = row[1]
        time = row[4]
        last_lat = row[5]
        last_lon = row[6]
        type = row[7]
        best_lat = row[9]
        best_lon = row[10]

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
            vprint(f"\t Best GPS location: lat: {best_lat}, lon: {best_lon}")
            data["lat"] = best_lat
            data["lon"] = best_lon
        elif(last_lat and last_lon):
            vprint(f"\t Last GPS location: lat: {last_lat}, lon: {last_lon}")
            data["lat"] = last_lat
            data["lon"] = last_lon

        if(name != ""):
            vprint(f"\t Name: {name}")
            # TODO: export name to HCI_bdaddr_to_name DB?

        # TODO: look up RSSI in location table, by matching on bssid?
        BTIDES_export_GPS_coordinate(bdaddr=bdaddr, random=bdaddr_rand, data=data)
        # query = "SELECT * FROM location WHERE bssid = ?"
        # values = (bssid_ACID,)
        # sqlite_cursor.execute(query, values)
        # locations = sqlite_cursor.fetchall()
        # for location in locations:
        #     rssi = location[2]
        #     lat = location[3]
        #     lon = location[4]
        #     time = location[7]
        #     data = {"time": {"unix_time_milli": time}, "rssi": rssi, "lat": lat, "lon": lon}
        #     BTIDES_export_GPS_coordinate(bdaddr=bdaddr, random=bdaddr_rand, data=data)

    sqlite_conn.close()


def main():
    global verbose_print, verbose_BTIDES, use_test_db
    parser = argparse.ArgumentParser(description='HCI file input arguments')
    parser.add_argument('--input', type=str, required=True, help='Input file name for WiGLE Database Backup file.')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')

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

    if not os.path.isfile(args.input):
        print(f"Error: file {input} does not exist.")
        return

    qprint("Reading all Bluetooth entries from WiGLE SQLite database into memory.")
    read_WiGLE_DB(args.input)

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