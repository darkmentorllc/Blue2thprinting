########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
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
from TME.TME_BTIDES_filter import filter_BTIDES_by_NOT_args

# BTIDALPOOL access related
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

import functools
import sqlite3
import mysql.connector

# Module-level cache for the MySQL connection and the list of tables that have
# a bdaddr_random column. Both are initialized lazily on first call to
# find_bdaddr_rand and reused for the lifetime of the process.
_mysql_conn = None
_bdaddr_rand_tables = None
_bdaddr_rand_union_sql = None


def _get_mysql_conn():
    global _mysql_conn
    if _mysql_conn is None:
        database = 'bttest' if TME.TME_glob.use_test_db else 'bt2'
        _mysql_conn = mysql.connector.connect(
            host='localhost',
            user='user',
            password='a',
            database=database,
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci',
            auth_plugin='mysql_native_password'
        )
    return _mysql_conn


def _get_bdaddr_rand_union_sql():
    global _bdaddr_rand_tables, _bdaddr_rand_union_sql
    if _bdaddr_rand_union_sql is not None:
        return _bdaddr_rand_union_sql, _bdaddr_rand_tables
    conn = _get_mysql_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND column_name = 'bdaddr_random'"
    )
    _bdaddr_rand_tables = [row[0] for row in cursor.fetchall()]
    cursor.close()
    if _bdaddr_rand_tables:
        # Parens are required around each sub-select when LIMIT is used inside UNION ALL in MySQL.
        _bdaddr_rand_union_sql = " UNION ALL ".join(
            f"(SELECT bdaddr_random FROM {t} WHERE bdaddr = %s LIMIT 1)"
            for t in _bdaddr_rand_tables
        )
    else:
        _bdaddr_rand_union_sql = ""
    return _bdaddr_rand_union_sql, _bdaddr_rand_tables


@functools.lru_cache(maxsize=None)
def find_bdaddr_rand(bdaddr):
    union_sql, tables = _get_bdaddr_rand_union_sql()
    if not tables:
        return 1  # No data available → default to random (matches prior behavior).

    conn = _get_mysql_conn()
    cursor = conn.cursor()
    cursor.execute(union_sql, tuple([bdaddr] * len(tables)))
    rows = cursor.fetchall()
    cursor.close()

    bdaddr_rand_count = {0: 0, 1: 0}
    for (bdaddr_rand,) in rows:
        if bdaddr_rand in bdaddr_rand_count:
            bdaddr_rand_count[bdaddr_rand] += 1

    if bdaddr_rand_count[0] == bdaddr_rand_count[1]:
        return 1  # No matches or exact tie → default to random.
    return max(bdaddr_rand_count, key=bdaddr_rand_count.get)


def batch_find_bdaddr_rand(bdaddrs, chunk_size=1000):
    """Bulk variant of find_bdaddr_rand: returns dict[bdaddr] -> bdaddr_rand.

    Issues one UNION-ALL query per chunk (across every bdaddr_random-bearing
    table), with a shared IN-clause per table. Applies the same "majority
    across tables, default to 1 on tie/miss" rule as find_bdaddr_rand.
    """
    unique_bdaddrs = list({b for b in bdaddrs if b})
    if not unique_bdaddrs:
        return {}

    _, tables = _get_bdaddr_rand_union_sql()
    if not tables:
        return {b: 1 for b in unique_bdaddrs}

    conn = _get_mysql_conn()
    counts = {}  # bdaddr -> {0: n, 1: n}
    for i in range(0, len(unique_bdaddrs), chunk_size):
        chunk = unique_bdaddrs[i:i + chunk_size]
        placeholders = ",".join(["%s"] * len(chunk))
        subqueries = [
            f"(SELECT bdaddr, bdaddr_random FROM {t} WHERE bdaddr IN ({placeholders}))"
            for t in tables
        ]
        query = " UNION ALL ".join(subqueries)
        params = tuple(chunk) * len(tables)
        cursor = conn.cursor()
        cursor.execute(query, params)
        for bdaddr, bdaddr_rand in cursor.fetchall():
            c = counts.setdefault(bdaddr, {0: 0, 1: 0})
            if bdaddr_rand in c:
                c[bdaddr_rand] += 1
        cursor.close()

    result = {}
    for b in unique_bdaddrs:
        c = counts.get(b, {0: 0, 1: 0})
        if c[0] == c[1]:
            result[b] = 1
        else:
            result[b] = max(c, key=c.get)
    return result

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

    # Batch-load the location table into an in-memory dict keyed by bssid.
    # The WiGLE DB has no index on location.bssid, so doing per-row SELECTs
    # against ~500k rows produces N full table scans. Loading once and
    # looking up in Python is ~100x faster and dominates the conversion cost.
    location_by_bssid = {}
    try:
        qprint("Loading WiGLE location table into memory for fast lookups.")
        sqlite_cursor.execute("SELECT * FROM location")
        for loc_row in sqlite_cursor:
            location_by_bssid.setdefault(loc_row[1], []).append(loc_row)
    except sqlite3.DatabaseError as e:
        print(f"Error loading location table: {e}")
        return

    # Pre-compute bdaddr_rand for every BLE entry in one batched MySQL
    # roundtrip (chunked UNION ALL) rather than N individual lookups.
    ble_bdaddrs = [row[0] for row in rows if row[7] == "E" and row[0]]
    if ble_bdaddrs:
        qprint(f"Looking up bdaddr_rand for {len(set(ble_bdaddrs))} unique BLE BDADDRs in bulk.")
        bdaddr_rand_map = batch_find_bdaddr_rand(ble_bdaddrs)
    else:
        bdaddr_rand_map = {}

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
            bdaddr_rand = bdaddr_rand_map.get(bdaddr, 1)
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
        bssid_locations = location_by_bssid.get(bssid_ACID, [])
        best_rssi = -127
        for location in bssid_locations:
            if location[3] == data["lat"] and location[4] == data["lon"]:
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
            for location in bssid_locations:
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

    # Post-processing exclusion arguments (applied to the in-memory BTIDES JSON
    # AFTER reading WiGLE — no local Bluetooth DB lookups are performed).
    not_group = parser.add_argument_group('BTIDES post-processing exclusion arguments')
    not_group.add_argument('--NOT-bdaddr', action='append', required=False, help='Remove the given BDADDR from the BTIDES output (case-insensitive exact match). May be passed multiple times.')
    not_group.add_argument('--NOT-bdaddr-regex', action='append', required=False, help='Remove any BTIDES entry whose BDADDR matches the given regex (case-insensitive). May be passed multiple times.')
    not_group.add_argument('--NOT-name-regex', action='append', required=False, help='Remove any BTIDES entry whose device name (HCI Remote Name, AdvData Complete/Incomplete Name, or GATT Device Name characteristic) matches the given regex (case-insensitive). May be passed multiple times.')
    not_group.add_argument('--NOT-company-regex', action='append', required=False, help='Remove any BTIDES entry whose Manufacturer-Specific Data company-ID-derived name matches the given regex (case-insensitive). Looked up against the BT SIG company_identifiers list — no local DB query. May be passed multiple times.')
    not_group.add_argument('--NOT-UUID-regex', action='append', required=False, help='Remove any BTIDES entry containing a UUID (in AdvData UUID16/32/128 lists or in GATT services/characteristics) matching the given regex (case-insensitive). NOTE: make sure to remove dashes from UUID128s because dashes will be interpreted per their regex meaning! May be passed multiple times.')

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

    # Post-process the aggregated BTIDES data to honor any --NOT-* exclusions.
    # Operates purely on the in-memory BTIDES JSON; does not query the local Bluetooth DB.
    filter_BTIDES_by_NOT_args(
        NOT_bdaddr=args.NOT_bdaddr,
        NOT_bdaddr_regex=args.NOT_bdaddr_regex,
        NOT_name_regex=args.NOT_name_regex,
        NOT_company_regex=args.NOT_company_regex,
        NOT_UUID_regex=args.NOT_UUID_regex,
    )

    qprint("Writing BTIDES data to file.")
    write_BTIDES(out_BTIDES_filename)
    qprint("Export completed with no errors.")

    btides_to_sql_succeeded = False
    if args.to_SQL:
        # skip_schema_validation=True: write_BTIDES already validated the JSON
        # we just wrote; no need to pay ~0.5ms/entry to re-validate on import.
        b2s_args = btides_to_sql_args(input=[out_BTIDES_filename], use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print, skip_schema_validation=True)
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