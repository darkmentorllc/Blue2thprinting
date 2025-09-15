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
from TME.TME_LLCP import *
from TME.TME_LMP import *
from TME.TME_metadata import *
from TME.TME_trackability import *
from TME.TME_GPS import *
from TME.TME_glob import verbose_print, quiet_print, verbose_BTIDES
from BTIDALPOOL_to_BTIDES import retrieve_btides_from_btidalpool
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from PCAP_to_BTIDES import read_pcap
from HCI_to_BTIDES import read_HCI

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
    printout_group.add_argument('--hide-android-data', action='store_true', help='Pass this argument to not print out the BLEScope data about Android package names associated with vendor-specific GATT UUID128s')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--input-pcap', type=str, required=False, help='Input pcap file which will be converted to a BTIDES JSON file and imported into the local database, and all the BDADDRs within selected for printout.')
    btides_group.add_argument('--input-hci-log', type=str, required=False, help='Input HCI log file which will be converted to a BTIDES JSON file and imported into the local database, and all the BDADDRs within selected for printout.')
    btides_group.add_argument('--include-centrals', action='store_true', help='Include the Central BDADDR from connections in the output.')
    btides_group.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')
    btides_group.add_argument('--GPS-exclude-upper-left', type=str, required=False, help='The coordinate for the upper left corner of the bounding box to exclude from the BTIDES output, in \"(lat,lon)\" format. E.g. \"(39.171951,-77.615936)\"')
    btides_group.add_argument('--GPS-exclude-lower-right', type=str, required=False, help='The coordinate for the lower right corner of the bounding box to exclude from the BTIDES output, in \"(lat,lon)\" format. E.g. \"(38.568929,-76.385467)\"')

    # BTIDALPOOL arguments
    btidalpool_group = parser.add_argument_group('BTIDALPOOL (crowdsourced database) arguments')
    btidalpool_group.add_argument('--to-BTIDALPOOL', action='store_true', required=False, help='The output BTIDES file from --output will also be sent to the remote BTIDALPOOL croudsourced database.')
    btidalpool_group.add_argument('--query-BTIDALPOOL', action='store_true', required=False, help='This will send the same search arguments to the remote BTIDALPOOL croudsourced database.')
    btidalpool_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')

    # Search arguments
    device_group = parser.add_argument_group('Database search arguments')
    device_group.add_argument('--bdaddr', type=validate_bdaddr, required=False, help='Device bdaddr value. Note: passing --bdaddr will downselect from any BDADDRs found via optional BTIDALPOOL queries or optional input files to the single specified bdaddr.')
    device_group.add_argument('--NOT-bdaddr', action='append', required=False, help='Remove them given BDADDR from the final results. (This is more efficient than --NOT-bdaddr-regex).')
    device_group.add_argument('--bdaddr-regex', type=str, default='', required=False, help='Regex to match a bdaddr value.')
    device_group.add_argument('--NOT-bdaddr-regex', type=str, default='', required=False, help='Find the bdaddrs corresponding to the regexp, the same as with --bdaddr-regex, and then remove them from the final results. (NOTE: Use --NOT-bdaddr if you can, as it is more efficient.).)')
    device_group.add_argument('--bdaddr-type', type=int, default=0, help='BDADDR type (0 = LE Public (default), 1 = LE Random, 2 = Classic, 3 = Any).')
    device_group.add_argument('--name-regex', type=str, default='', help='Value for REGEXP match against device_name.')
    device_group.add_argument('--NOT-name-regex', type=str, default='', help='Find the bdaddrs corresponding to the name regexp, the same as with --name-regex, and then remove them from the final results.')
    device_group.add_argument('--company-regex', type=str, default='', help='Value for REGEXP match against company name, in IEEE OUIs, or BT Company IDs, or BT Company UUID16s.')
    device_group.add_argument('--NOT-company-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --company-regex, and then remove them from the final results.')
    device_group.add_argument('--UUID-regex', type=str, default='', help='Value for REGEXP match against UUID, in any location UUIDs can appear. NOTE: make sure to remove dashes from UUID128s because dashes will be interpreted per their regex meaning!')
    device_group.add_argument('--NOT-UUID-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --UUID-regex, and then remove them from the final results.')
    device_group.add_argument('--MSD-regex', type=str, default='', help='Value for REGEXP match against Manufacturer-Specific Data (MSD).')
    device_group.add_argument('--LL_VERSION_IND', type=str, default='', help='Value for LL_VERSION_IND search, given as AA:BBBB:CCCC where AA is the version, BBBB is the big-endian company ID, and CCCC is the big-endian sub-version.')
    device_group.add_argument('--LMP_VERSION_RES', type=str, default='', help='Value for LMP_VERSION_RES search, given as AA:BBBB:CCCC where AA is the version, BBBB is the big-endian company ID, and CCCC is the big-endian sub-version.')

    # Statistics arguments
    stats_group = parser.add_argument_group('Database statistics arguments')
    stats_group.add_argument('--UUID128-stats', action='store_true', help='Parse the UUID128 data, and output statistics about the most common entries (Only shows local database statistics, not BTIDALPOOL data).')
    stats_group.add_argument('--UUID16-stats', action='store_true', help='Parse the UUID16 data, and output statistics about the most common entries (Only shows local database statistics, not BTIDALPOOL data).')

    # Requirement arguments
    requirement_group = parser.add_argument_group('Arguments which specify that a particular type of data is required in the printed out / exported data.')
    requirement_group.add_argument('--require-GPS', action='store_true', help='Pass this argument to only print out information for devices which have at least 1 associated GPS coordinate.')
    requirement_group.add_argument('--require-GATT-any', action='store_true', help='Pass this argument to only print out information for devices which have *some* GATT info.')
    requirement_group.add_argument('--require-GATT-values', action='store_true', help='Pass this argument to only print out information for devices which successfully read some GATT values.')
    requirement_group.add_argument('--require-SMP', action='store_true', help='Pass this argument to only print out information for devices which have *some* SMP info.')
    requirement_group.add_argument('--require-SMP-legacy-pairing', action='store_true', help='Pass this argument to only print out information for devices which have SMP info indicating they will perform Legacy Pairing.')
    requirement_group.add_argument('--require-SDP', action='store_true', help='Pass this argument to only print out information for devices which have *some* SDP info.')
    requirement_group.add_argument('--require-LL_VERSION_IND', action='store_true', help='Pass this argument to only print out information for devices which have LL_VERSION_IND data.')
    requirement_group.add_argument('--require-LMP_VERSION_RES', action='store_true', help='Pass this argument to only print out information for devices which have LMP_VERSION_RES data.')

    # Testing arguments
    testing_group = parser.add_argument_group('Arguments for testing (mostly for developers)')
    testing_group.add_argument('--use-test-db', action='store_true', required=False, help='This will store to / query from an alternate database, used for testing.')

    args = parser.parse_args()
    out_filename = args.output
    if args.to_BTIDALPOOL and not out_filename:
        # Create a default temporary filename if people provide the --to-BTIDALPOOL flag without a --output filename
        out_filename = "/tmp/tme.btides"
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES
    TME.TME_glob.use_test_db = args.use_test_db
    TME.TME_glob.hide_android_data = args.hide_android_data

    bdaddrs = []

    if(args.GPS_exclude_upper_left and not args.GPS_exclude_lower_right or args.GPS_exclude_lower_right and not args.GPS_exclude_upper_left):
        print("Error: If you specify either GPS exclude option, you must specify both.")
        return

    upper_left_tuple = None
    lower_right_tuple = None
    if(args.GPS_exclude_upper_left and args.GPS_exclude_lower_right):
        upper_left_tuple = tuple(map(float, args.GPS_exclude_upper_left.strip('()').split(',')))
        lower_right_tuple = tuple(map(float, args.GPS_exclude_lower_right.strip('()').split(',')))
        if(len(upper_left_tuple) != 2 or len(lower_right_tuple) != 2):
            print("Error: GPS exclude coordinates must be in the form of \"(lat,lon)\".")
            return

    #######################################################
    # If given an input file, convert it to BTIDES JSON
    # and import it into the local database,
    # and collect all the BDADDRs from it for printing.
    #######################################################
    if(args.input_pcap):
        read_pcap(args.input_pcap)

    if(args.input_hci_log):
        read_HCI(args.input_hci_log)

    # Fill in bdaddrs[] with the bdaddrs in the BTIDES data, if any
    if(TME.TME_glob.BTIDES_JSON):
        # Magic input filename "SKIPME" tells btides_to_sql to not read from file, but just use the global TME.TME_glob.BTIDES_JSON
        b2s_args = btides_to_sql_args(input="SKIPME", use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print)
        btides_to_sql_succeeded = btides_to_sql(b2s_args)

        for entry in TME.TME_glob.BTIDES_JSON:
            if 'bdaddr' in entry:
                if(entry['bdaddr'] not in bdaddrs):
                    bdaddrs.append(entry['bdaddr'])
            elif 'CONNECT_IND' in entry:
                if(entry['CONNECT_IND']['peripheral_bdaddr'] not in bdaddrs):
                    bdaddrs.append(entry['CONNECT_IND']['peripheral_bdaddr'])
                # Most of the time we don't care about the Central BDADDR, because it's just our own device.
                # with some random BDADDR set. However, if we happen to have collected data from overhearing
                # the conversation between two devices, then we'd want to include the Central as well.
                if(args.include_centrals):
                    if(entry['CONNECT_IND']['central_bdaddr'] not in bdaddrs):
                        bdaddrs.append(entry['CONNECT_IND']['central_bdaddr'])

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
        if args.NOT_bdaddr:
            query_object["NOT_bdaddr"] = args.NOT_bdaddr # NOTE: this will now be a list!
        if args.bdaddr_regex:
            query_object["bdaddr_regex"] = args.bdaddr_regex
        if args.NOT_bdaddr_regex:
            query_object["NOT_bdaddr_regex"] = args.NOT_bdaddr_regex
        if args.name_regex:
            query_object["name_regex"] = args.name_regex
        if args.company_regex:
            query_object["company_regex"] = args.company_regex
        if args.NOT_company_regex:
            query_object["NOT_company_regex"] = args.NOT_company_regex
        if args.UUID_regex:
            query_object["UUID_regex"] = args.UUID_regex
        if args.NOT_UUID_regex:
            query_object["NOT_UUID_regex"] = args.NOT_UUID_regex
        if args.MSD_regex:
            query_object["MSD_regex"] = args.MSD_regex
        if args.GPS_exclude_upper_left:
            query_object["GPS_exclude_upper_left"] = args.GPS_exclude_upper_left
            query_object["GPS_exclude_lower_right"] = args.GPS_exclude_lower_right
        if args.require_GPS:
            query_object["require_GPS"] = True
        if args.require_GATT_any:
            query_object["require_GATT_any"] = True
        if args.require_GATT_values:
            query_object["require_GATT_values"] = True
        if args.require_SMP:
            query_object["require_SMP"] = True
        if args.require_SMP_legacy_pairing:
            query_object["require_SMP_legacy_pairing"] = True
        if args.require_SDP:
            query_object["require_SDP"] = True
        if args.require_LL_VERSION_IND:
            query_object["require_LL_VERSION_IND"] = True
        if args.require_LMP_VERSION_RES:
            query_object["require_LMP_VERSION_RES"] = True

        # If the token isn't given on the CLI, then redirect them to go login and get one
        client = AuthClient()
        if args.token_file:
            with open(args.token_file, 'r') as f:
                try:
                    token_data = json.load(f)
                except json.JSONDecodeError:
                    print("Error: Token file is not a valid JSON file.")
                    exit(1)
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
    import_nonunique_nameprint_CSV_data()

    # Fill in dictionaries based on standard BT assigned numbers YAML files
    import_CoD_to_names()
    import_bt_format_type_to_descriptions()
    import_bt_units_to_names()
    import_bt_namespace_descriptions()
    import_bt_CID_to_names()
    import_bt_member_UUID16s_to_names()
    import_bt_spec_version_numbers_to_names()
    import_uuid16_service_names()
    import_uuid16_standards_organizations_names()
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

    # Note: passing the --bdaddr argument will override any bdaddrs collected from the BTIDALPOOL or from the input files
    if(args.bdaddr is not None):
        bdaddrs = [args.bdaddr]

    ######################################################
    # Options to simply print statistics from the database
    ######################################################

    if(args.UUID16_stats):
        get_uuid16_stats(args.UUID16_stats)
        quit() # Don't do anything other than print the stats and exit

    if(args.UUID128_stats):
        get_uuid128_stats(args.UUID128_stats)
        quit() # Don't do anything other than print the stats and exit

    vprint(bdaddrs)

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

    # Process CLI arguments that remove BDADDRs from the list
    bdaddrs_to_remove = []

    if(args.NOT_bdaddr != None):
        # Not taking the shortcut of just doing "bdaddrs_to_remove = args.NOT_bdaddr",
        # just in case the code gets rearranged later
        for entry in args.NOT_bdaddr:
            bdaddrs_to_remove.append(f"{entry}")

    if(args.NOT_bdaddr_regex != ""):
        bdaddrs_to_remove.extend(get_bdaddrs_by_bdaddr_regex(args.NOT_bdaddr_regex))

    if(args.NOT_name_regex != ""):
        bdaddrs_to_remove.extend(get_bdaddrs_by_name_regex(args.NOT_name_regex))

    if(args.NOT_company_regex != ""):
        bdaddrs_to_remove.extend(get_bdaddrs_by_company_regex(args.NOT_company_regex))

    if(args.NOT_UUID_regex != ""):
        bdaddrs_to_remove.extend(get_bdaddrs_by_uuid_regex(args.NOT_UUID_regex))

    # Now that we have all the bdaddrs_to_remove, loop through the bdaddrs list and remove them
    qprint(bdaddrs_to_remove)
    updated_bdaddrs = []
    for value in bdaddrs:
        if(value in bdaddrs_to_remove):
            continue
        else:
            updated_bdaddrs.append(value)

    qprint(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")
    bdaddrs = updated_bdaddrs;

    filtered_bdaddrs = []
    for bdaddr in bdaddrs:
        if(args.require_GPS):
            if(not device_has_GPS(bdaddr)):
                continue
        if(args.GPS_exclude_upper_left and device_has_GPS(bdaddr)):
            if(is_GPS_coordinate_within_exclusion_box(bdaddr, upper_left_tuple, lower_right_tuple)):
                continue
        if(args.require_GATT_any):
            if(not device_has_GATT_any(bdaddr)):
                continue
        if(args.require_GATT_values):
            if(not device_has_GATT_values(bdaddr)):
                continue
        if(args.require_SMP):
            if(not device_has_SMP_info(bdaddr)):
                continue
        if(args.require_SMP_legacy_pairing):
            if(not device_SMP_legacy_pairing(bdaddr)):
                continue
        if(args.require_SDP):
            if(not device_has_SDP_info(bdaddr)):
                continue
        if(args.require_LL_VERSION_IND):
            if(not device_has_LL_VERSION_IND_info(bdaddr)):
                continue
        if(args.require_LMP_VERSION_RES):
            if(not device_has_LMP_VERSION_RES_info(bdaddr)):
                continue
        # Check if we have no information in any table for this BDADDR
        # and if so, continue to the next BDADDR (if any)
        if(not bdaddr_found_in_any_table(bdaddr)):
            vprint(f"No information was found for {bdaddr}.")
            continue
        # If we got here, then we have a bdaddr that matches all the requirements
        # so we should keep track of it for future use
        filtered_bdaddrs.append(bdaddr)

    # Limit the number of records output to args.max_records_output
    if(len(filtered_bdaddrs) > args.max_records_output):
        filtered_bdaddrs = filtered_bdaddrs[:args.max_records_output]

    # Start again with the now filtered and size-limited bdaddrs
    bdaddrs = filtered_bdaddrs
    for bdaddr in bdaddrs:
        qprint("================================================================================")
        reset_per_bdaddr_globals()
        qprint(f"For bdaddr = {bdaddr}:")
        print_company_name_from_bdaddr(f"{i1}", bdaddr, True)
        print("")
        print_ChipPrint(bdaddr)
        print_ChipMakerPrint(bdaddr)                        # Includes BTIDES export
        print_classic_EIR_CID_info(bdaddr)                  # Includes BTIDES export
        print_all_advdata(bdaddr, args.bdaddr_type)         # Includes BTIDES export
        print_GATT_info(bdaddr)                             # Includes BTIDES export
        print_SMP_info(bdaddr)                              # Includes BTIDES export
        print_LLCP_info(bdaddr)                             # Includes BTIDES export
        print_LMP_info(bdaddr)                              # Includes BTIDES export
        print_SDP_info(bdaddr)                              # Includes BTIDES export
        print_L2CAP_info(bdaddr)                            # Includes BTIDES export
        print_GPS(bdaddr)
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
