########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# Activate venv before any other imports
import os
import sys
from pathlib import Path
from handle_venv import activate_venv
activate_venv()

import argparse
# Import from my files
from TME.TME_helpers import *
from TME.TME_import import *
from TME.TME_lookup import *
from TME.TME_stats import *
from TME.TME_AdvChan import *
from TME.TME_EIR import *
from TME.TME_L2CAP import *
from TME.TME_GATT import *
from TME.TME_SMP import *
from TME.TME_SDP import *
from TME.TME_BLE2thprint import *
from TME.TME_BTC2thprint import *
from TME.TME_metadata import *
from TME.TME_trackability import *
from TME.TME_glob import verbose_print, quiet_print, verbose_BTIDES
from BTIDALPOOL_to_BTIDES import retrieve_btides_from_btidalpool
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql

########################################
# MAIN #################################
########################################

def validate_bdaddr(value):
    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', value):
        raise argparse.ArgumentTypeError("bdaddr must be in the form of a Bluetooth Device Address (e.g., AA:BB:CC:11:22:33).")
    return value

# Main function to handle command line arguments
def main():
    global verbose_print, verbose_BTIDES, use_test_db
    parser = argparse.ArgumentParser(description='Lookup and print information about Bluetooth devices from your local database or the BTIDALPOOL crowdsourced db!')
    # Output arguments
    printout_group = parser.add_argument_group('Print verbosity arguments')
    printout_group.add_argument('--verbose-print', action='store_true', required=False, help='Show explicit data-not-found output.')
    printout_group.add_argument('--quiet-print', action='store_true', required=False, help='Hide all print output (useful when you only want to use --output to export data).')
    printout_group.add_argument('--max-records-output', type=int, default=1000, required=False, help='This will limit the number of bdaddrs for which records which are printed out and exported via --output).')
    printout_group.add_argument('--hide-BLEScope-data', action='store_true', help='Pass this argument to not print out the BLEScope data about Android package names associated with vendor-specific GATT UUID128s')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')

    # BTIDALPOOL arguments
    btidalpool_group = parser.add_argument_group('BTIDALPOOL (crowdsourced database) arguments')
    btidalpool_group.add_argument('--to-BTIDALPOOL', action='store_true', required=False, help='The output BTIDES file from --output will also be sent to the remote BTIDALPOOL croudsourced database.')
    btidalpool_group.add_argument('--query-BTIDALPOOL', action='store_true', required=False, help='This will send the same search arguments to the remote BTIDALPOOL croudsourced database.')
    btidalpool_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')

    # Search arguments
    device_group = parser.add_argument_group('Database search arguments')
    device_group.add_argument('--bdaddr', type=validate_bdaddr, required=False, help='Device bdaddr value.')
    device_group.add_argument('--bdaddr-regex', type=str, default='', required=False, help='Regex to match a bdaddr value.')
    device_group.add_argument('--bdaddr-type', type=int, default=0, help='BDADDR type (0 = LE Public (default), 1 = LE Random, 2 = Classic, 3 = Any).')
    device_group.add_argument('--name-regex', type=str, default='', help='Value for REGEXP match against device_name.')
    device_group.add_argument('--NOT-name-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --name-regex, and then remove them from the final results.')
    device_group.add_argument('--company-regex', type=str, default='', help='Value for REGEXP match against company name, in IEEE OUIs, or BT Company IDs, or BT Company UUID16s.')
    device_group.add_argument('--NOT-company-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --company-regex, and then remove them from the final results.')
    device_group.add_argument('--UUID-regex', type=str, default='', help='Value for REGEXP match against UUID, in any location UUIDs can appear.')
    device_group.add_argument('--NOT-UUID-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --UUID-regex, and then remove them from the final results.')
    device_group.add_argument('--MSD-regex', type=str, default='', help='Value for REGEXP match against Manufacturer-Specific Data (MSD)')
    device_group.add_argument('--LL_VERSION_IND', type=str, default='', help='Value for LL_VERSION_IND search, given as AA:BBBB:CCCC where AA is the version, BBBBis the big-endian company ID, and CCCC is the big-endian sub-version.')
    device_group.add_argument('--LMP_VERSION_RES', type=str, default='', help='Value for LMP_VERSION_RES search, given as AA:BBBB:CCCC where AA is the version, BBBBis the big-endian company ID, and CCCC is the big-endian sub-version.')

    # Statistics arguments
    stats_group = parser.add_argument_group('Database statistics arguments')
    stats_group.add_argument('--UUID128-stats', action='store_true', help='Parse the UUID128 data, and output statistics about the most common entries (Only shows local database statistics, not BTIDALPOOL data)')
    stats_group.add_argument('--UUID16-stats', action='store_true', help='Parse the UUID16 data, and output statistics about the most common entries (Only shows local database statistics, not BTIDALPOOL data)')

    # Requirement arguments
    requirement_group = parser.add_argument_group('Arguments which specify that a particular type of data is required in the printed out / exported data.')
    requirement_group.add_argument('--require-GATT', action='store_true', help='Pass this argument to only print out information for devices which have GATT info')
    requirement_group.add_argument('--require-LL_VERSION_IND', action='store_true', help='Pass this argument to only print out information for devices which have LL_VERSION_IND data')
    requirement_group.add_argument('--require-LMP_VERSION_RES', action='store_true', help='Pass this argument to only print out information for devices which have LMP_VERSION_RES data')

    # Testing arguments
    testing_group = parser.add_argument_group('Arguments for testing (mostly for developers)')
    testing_group.add_argument('--use-test-db', action='store_true', required=False, help='This will query from an alternate database, used for testing.')

    args = parser.parse_args()
    out_filename = args.output
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES
    TME.TME_glob.use_test_db = args.use_test_db
    hideBLEScopedata = args.hide_BLEScope_data

    #######################################################
    # If querying the BTIDALPOOL, collect that information,
    # import it into the local database, and then proceed
    # with the rest of the code as normal.
    #######################################################
    if(args.query_BTIDALPOOL):
        qprint("Querying BTIDALPOOL")
        query_object = {}
        if args.bdaddr:
            query_object["bdaddr"] = args.bdaddr
        if args.bdaddr_regex:
            query_object["bdaddr_regex"] = args.bdaddr_regex
        if args.name_regex:
            query_object["name_regex"] = args.name_regex
        if args.company_regex:
            query_object["company_regex"] = args.company_regex
        if args.NOT_company_regex:
            query_object["NOT_company_regex"] = args.NOT_company_regex
        if args.UUID128_regex:
            query_object["UUID128_regex"] = args.UUID128_regex
        if args.NOT_UUID128_regex:
            query_object["NOT_UUID128_regex"] = args.NOT_UUID128_regex
        if args.UUID16_regex:
            query_object["UUID16_regex"] = args.UUID16_regex
        if args.MSD_regex:
            query_object["MSD_regex"] = args.MSD_regex
        if args.require_GATT:
            query_object["require_GATT"] = True
        if args.require_LL_VERSION_IND:
            query_object["require_LL_VERSION_IND"] = True
        if args.require_LMP_VERSION_RES:
            query_object["require_LMP_VERSION_RES"] = True

        # If the token isn't given on the CLI, then redirect them to go login and get one
        client = AuthClient()
        if args.token_file:
            with open(args.token_file, 'r') as f:
                token_data = json.load(f)
            client.set_credentials(token_data['token'], token_data['refresh_token'], token_file=args.token_file)
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

        # Using the presence of the email address as proof of successful authentication
        # Use the copy of token/refresh_token in client.credentials, because it could have been refreshed inside validate_credentials()
        if(client.user_info and client.user_info.get('email')):
            (num_records, output_filename) = retrieve_btides_from_btidalpool(
                email=client.user_info.get('email'),
                query_object=query_object,
                token=client.credentials.token,
                refresh_token=client.credentials.refresh_token
            )
            if(num_records):
                qprint(f"Retrieved {num_records} matching records from BTIDALPOOL")
            # output_filename can be None because an error occurred, or because no records were found
            # In either case we don't need to run BTIDES_to_SQL
            if output_filename:
                b2s_args = btides_to_sql_args(input=output_filename, use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print)
                btides_to_sql(b2s_args)
            # For debugging
            write_BTIDES("/tmp/a.btides")

    # Import metadata v2
    import_metadata_v2()
    import_private_metadata_v2()

    # Import CLUES
    import_CLUES()
    import_private_CLUES()

    # Import any data from CSV files as necessary
    import_nameprint_CSV_data()
    import_private_nameprint_CSV_data()

    # Fill in dictionaries based on standard BT assigned numbers YAML files
    import_CoD_to_names()
    import_bt_CID_to_names()
    import_bt_member_UUID16s_to_names()
    import_bt_spec_version_numbers_to_names()
    import_uuid16_service_names()
    import_uuid16_protocol_names()
    import_gatt_services_uuid16_names()
    import_gatt_declarations_uuid16_names()
    import_gatt_descriptors_uuid16_names()
    import_gatt_characteristic_uuid16_names()
    import_appearance_yaml_data()
    import_SDP_universal_attribute_names()
    import_SDP_protocol_identifiers()

    # It could be argued that the ChipMaker_OUI_hash should be pulled out and made static and just read from file.
    # But I'd consider that premature optimization for now.
    # TODO: consider doing this in the future if it adds too much overhead to every invocation
    create_ChipMaker_OUI_hash()

    if(args.bdaddr is not None):
        bdaddrs = [args.bdaddr]
    else:
        bdaddrs = []

    ######################################################
    # Options to simply print statistics from the database
    ######################################################

    if(args.UUID16_stats):
        get_uuid16_stats(args.UUID16_stats)
        quit() # Don't do anything other than print the stats and exit

    if(args.UUID128_stats):
        get_uuid128_stats(args.UUID128_stats)
        quit() # Don't do anything other than print the stats and exit

    qprint(bdaddrs)

    #######################################################
    # Options to search based on specific values or regexes
    #######################################################

    if(args.bdaddr_regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_bdaddr_regex(args.bdaddr_regex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --bdaddr-regex processing: {bdaddrs}")

    if(args.name_regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_name_regex(args.name_regex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --name-regex processing: {bdaddrs}")

    if(args.company_regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_company_regex(args.company_regex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --company-regex processing: {bdaddrs}")

    if(args.MSD_regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_msd_regex(args.MSD_regex)
        qprint(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --MSD-regex processing: {bdaddrs}")

    if(args.UUID_regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_uuid_regex(args.UUID_regex)
        qprint(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --UUID-regex processing: {bdaddrs}")

    if(args.LL_VERSION_IND != ""):
        (version, company_id, subversion) = args.LL_VERSION_IND.split(":")
        version = int(version, 16)
        if(version < 0 or version > 255):
            print("Version must be a single byte value (0-FF)")
            exit(1)
        company_id = int(company_id, 16)
        if(version < 0 or company_id > 65535):
            print("Company ID must be a two byte hex value (0000-FFFF)")
            exit(1)
        subversion = int(subversion, 16)
        if(version < 0 or subversion > 65535):
            print("Sub-version must be a two byte hex value (0000-FFFF)")
            exit(1)
        bdaddrs_tmp = get_bdaddrs_by_LL_VERSION_IND(version, company_id, subversion)
        qprint(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --LL_VERSION_IND processing: {bdaddrs}")

    if(args.LMP_VERSION_RES != ""):
        (version, company_id, subversion) = args.LMP_VERSION_RES.split(":")
        version = int(version, 16)
        if(version < 0 or version > 255):
            print("Version must be a single byte value (0-FF)")
            exit(1)
        company_id = int(company_id, 16)
        if(version < 0 or company_id > 65535):
            print("Company ID must be a two byte hex value (0000-FFFF)")
            exit(1)
        subversion = int(subversion, 16)
        if(version < 0 or subversion > 65535):
            print("Sub-version must be a two byte hex value (0000-FFFF)")
            exit(1)
        bdaddrs_tmp = get_bdaddrs_by_LMP_VERSION_RES(version, company_id, subversion)
        qprint(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        qprint(f"{len(bdaddrs)} bdaddrs after --LMP_VERSION_RES processing: {bdaddrs}")

    if(args.NOT_UUID_regex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_uuid_regex(args.UUID_regex)
        qprint(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        qprint(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;

    if(args.NOT_company_regex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_company_regex(args.NOT_company_regex)
        qprint(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        qprint(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;

    if(args.NOT_name_regex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_name_regex(args.NOT_name_regex)
        qprint(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        qprint(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;

    # Limit the number of records output to args.max_records_output
    if(len(bdaddrs) > args.max_records_output):
        bdaddrs = bdaddrs[:args.max_records_output]

    for bdaddr in bdaddrs:
        if(args.require_GATT):
            if(device_has_GATT_info(bdaddr) != 1):
                continue
        if(args.require_LL_VERSION_IND):
            if(device_has_LL_VERSION_IND_info(bdaddr) != 1):
                continue
        if(args.require_LMP_VERSION_RES):
            if(device_has_LMP_VERSION_RES_info(bdaddr) != 1):
                continue
        qprint("================================================================================")
        qprint(f"For bdaddr = {bdaddr}:")
        print_ChipPrint(bdaddr)
        print_ChipMakerPrint(bdaddr)                        # Includes BTIDES export
        print_company_name_from_bdaddr("\t", bdaddr, True)
        print_classic_EIR_CID_info(bdaddr)                  # Includes BTIDES export
        print_all_advdata(bdaddr, args.bdaddr_type)
        print_GATT_info(bdaddr, args.hide_BLEScope_data)    # Includes BTIDES export
        print_SMP_info(bdaddr)                              # Includes BTIDES export
        print_BLE_2thprint(bdaddr)                          # Includes BTIDES export
        print_BTC_2thprint(bdaddr)                          # Includes BTIDES export
        print_SDP_info(bdaddr)                              # Includes BTIDES export
        print_L2CAP_info(bdaddr)                            # Includes BTIDES export
        print_UniqueIDReport(bdaddr)

    if(out_filename != None and out_filename != ""):
        write_BTIDES(out_filename)

        # We can only send the out_filename if --output was passed
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
                input_file=out_filename,
                token=client.credentials.token,
                refresh_token=client.credentials.refresh_token
            )

if __name__ == "__main__":
    main()
