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

# HCI_to_BTIDES and PCAP_to_BTIDES
from HCI_to_BTIDES import *
from PCAP_to_BTIDES import *

def optionally_store_to_SQL(btides_file, to_SQL, to_BTIDALPOOL, token_file, use_test_db, quiet_print, verbose_print, rename):
    btides_to_sql_succeeded = False
    if to_SQL:
        b2s_args = btides_to_sql_args(input=btides_file, use_test_db=use_test_db, quiet_print=quiet_print, verbose_print=verbose_print)
        btides_to_sql_succeeded = btides_to_sql(b2s_args)

    if to_BTIDALPOOL:
        # If the token isn't given on the CLI, then redirect them to go login and get one
        client = AuthClient()
        client.token_helper(token_file)

        # Use the copy of token/refresh_token in client.credentials, because it could have been refreshed inside validate_credentials()
        send_btides_to_btidalpool(
            input_file=btides_file,
            token=client.credentials.token,
            refresh_token=client.credentials.refresh_token
        )

    if(btides_to_sql_succeeded and rename):
        os.rename(btides_file, btides_file + ".processed")
        vprint(f"Renamed to {btides_file}.processed")


def main():
    global verbose_print, verbose_BTIDES
    global BTIDES_JSON
    parser = argparse.ArgumentParser(description='File input arguments. Can specify either HCI or PCAP or both.')
    parser.add_argument('--HCI-logs-folder', type=str, required=False, help='Input folder name for HCI log files which will be processed.')
    parser.add_argument('--HCI-logs-suffix', type=str, default='.bin', required=False, help='(Required if --HCI-logs-folder is passed) Suffix for identifying HCI log files within this folder and all sub-folders. (Default is .bin, but you might want to set to .log or something else.)')
    parser.add_argument('--pcaps-folder', type=str, required=False, help='Input folder name for pcap log files which will be processed.')
    parser.add_argument('--pcaps-suffix', type=str, default='.pcap', required=False, help='Suffix for identifying pcap files within this folder and all sub-folders. (default is .pcap, but you might want to set to .pcapng or something else.)')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')
    btides_group.add_argument('--overwrite-existing-BTIDES', action='store_true', required=False, help='If this is set, it will process the specified HCI/PCAP file, overwriting any existing .btides file that may exist next to it. (Mutually exclusive with --read-existing-BTIDES.)')
    btides_group.add_argument('--read-existing-BTIDES', action='store_true', required=False, help='If this is set, and a file with suffix .btides is found next to the target HCI/PCAP file, it will skip attempting conversion, and just read the existing .btides file instead.')

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

    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES

    # Sanity check args
    if args.HCI_logs_folder and not os.path.isdir(args.HCI_logs_folder):
        print("The --HCI-logs-folder argument must be a folder")
        exit(1)

    if(args.HCI_logs_suffix != ".bin" and not args.HCI_logs_folder):
        print("--HCI-logs-suffix can only be passed if --HCI-logs-folder is also given.")
        exit(1)

    if args.pcaps_folder and not os.path.isdir(args.pcaps_folder):
        print("The --pcaps-folder argument must be a folder")
        exit(1)

    if(args.pcaps_suffix != ".pcap" and not args.pcaps_folder):
        print("--pcaps-suffix can only be passed if --pcaps-folder is also given.")
        exit(1)

    if(args.overwrite_existing_BTIDES and args.read_existing_BTIDES):
        print("You can only pass one of --overwrite-existing-BTIDES or --read-existing-BTIDES at the same time.")
        exit(1)

    hci_file_export_count = 0
    if(args.HCI_logs_folder):
        for root, dirs, files in os.walk(args.HCI_logs_folder):
            for file in files:
                if file.endswith(args.HCI_logs_suffix):
                    base_file_name = file[:-len(args.HCI_logs_suffix)]
                    btides_file = os.path.join(root, f"{base_file_name}.btides")
                    btides_processed_file = os.path.join(root, f"{base_file_name}.btides.processed")
                    if (not os.path.exists(btides_file) and not os.path.exists(btides_processed_file)):
                        qprint(f"Reading all events from HCI log {os.path.join(root, file)} into memory.")
                        if(not read_HCI(os.path.join(root, file))):
                            continue
                        write_BTIDES(btides_file)
                        qprint(f"Export {btides_file} completed with no errors.")
                        hci_file_export_count += 1
                        optionally_store_to_SQL(btides_file, args.to_SQL, args.to_BTIDALPOOL, args.token_file, args.use_test_db, args.quiet_print, args.verbose_print, args.rename)
                    else:
                        if(args.overwrite_existing_BTIDES):
                            qprint(f"Reading all events from HCI log {os.path.join(root, file)} into memory.")
                            if(not read_HCI(os.path.join(root, file))):
                                continue
                            write_BTIDES(btides_file)
                            qprint(f"Export {btides_file} completed with no errors.")
                            hci_file_export_count += 1
                            optionally_store_to_SQL(btides_file, args.to_SQL, args.to_BTIDALPOOL, args.token_file, args.use_test_db, args.quiet_print, args.verbose_print, args.rename)
                        elif(args.read_existing_BTIDES):
                            if(os.path.exists(btides_file)):
                                # Don't re-process .processed files. If we need to do that, use the --overwrite-existing-BTIDES path
                                # This path will just be for processing unprocessed .btides files
                                optionally_store_to_SQL(btides_file, args.to_SQL, args.to_BTIDALPOOL, args.token_file, args.use_test_db, args.quiet_print, args.verbose_print, args.rename)

                    # Reset globals to not accumulate wasted memory
                    TME.TME_glob.BTIDES_JSON = []
                    TME.TME_glob.duplicate_count = 0
                    TME.TME_glob.insert_count = 0
                    g_last_handle_to_bdaddr = {}

    pcap_file_export_count = 0
    if(args.pcaps_folder):
        for root, dirs, files in os.walk(args.pcaps_folder):
            for file in files:
                if file.endswith(args.pcaps_suffix):
                    base_file_name = file[:-len(args.pcaps_suffix)]
                    btides_file = os.path.join(root, f"{base_file_name}.btides")
                    btides_processed_file = os.path.join(root, f"{base_file_name}.btides.processed")
                    if (not os.path.exists(btides_file) and not os.path.exists(btides_processed_file)):
                        qprint(f"Reading all packets from pcap {os.path.join(root, file)} into memory. (This can take a while for large pcaps. Assume a total time of 1 second per 1000 packets.)")
                        read_pcap(os.path.join(root, file))
                        write_BTIDES(btides_file)
                        qprint(f"Export {btides_file} completed with no errors.")
                        pcap_file_export_count += 1
                        optionally_store_to_SQL(btides_file, args.to_SQL, args.to_BTIDALPOOL, args.token_file, args.use_test_db, args.quiet_print, args.verbose_print, args.rename)
                    else:
                        if(args.overwrite_existing_BTIDES):
                            qprint(f"Reading all packets from pcap {os.path.join(root, file)} into memory. (This can take a while for large pcaps. Assume a total time of 1 second per 1000 packets.)")
                            read_pcap(os.path.join(root, file))
                            write_BTIDES(btides_file)
                            qprint(f"Export {btides_file} completed with no errors.")
                            pcap_file_export_count += 1
                            optionally_store_to_SQL(btides_file, args.to_SQL, args.to_BTIDALPOOL, args.token_file, args.use_test_db, args.quiet_print, args.verbose_print, args.rename)
                        elif(args.read_existing_BTIDES):
                            if(os.path.exists(btides_file)):
                                # Don't re-process .processed files. If we need to do that, use the --overwrite-existing-BTIDES path
                                # This path will just be for processing unprocessed .btides files
                                optionally_store_to_SQL(btides_file, args.to_SQL, args.to_BTIDALPOOL, args.token_file, args.use_test_db, args.quiet_print, args.verbose_print, args.rename)

                    # Reset globals to not accumulate wasted memory
                    TME.TME_glob.BTIDES_JSON = []
                    TME.TME_glob.duplicate_count = 0
                    TME.TME_glob.insert_count = 0
                    g_access_address_to_connect_ind_obj = {}

    print("File conversion to BTIDES completed.")
    if(args.HCI_logs_folder):
        print(f"Converted {hci_file_export_count} HCI files found in {args.HCI_logs_folder} with suffix {args.HCI_logs_suffix}.")
    if(args.pcaps_folder):
        print(f"Converted {pcap_file_export_count} pcap files found in {args.pcaps_folder} with suffix {args.pcaps_suffix}.")


if __name__ == "__main__":
    main()