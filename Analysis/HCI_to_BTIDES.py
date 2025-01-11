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


def export_AdvChannelData(packet, adv_type):
    ble_adv_fields = packet.getlayer(HCI_LE_Meta_Advertising_Report).fields
    bdaddr_random = ble_adv_fields['atype']
    device_bdaddr = ble_adv_fields['addr']

    data_exported = False
    for entry in ble_adv_fields['data']: # This is an array of AdvData entries
        if export_AdvData(device_bdaddr, bdaddr_random, adv_type, entry):
            data_exported = True

    if(data_exported or (adv_type == type_AdvChanPDU_SCAN_RSP and len(ble_adv_fields['data']) == 0)):
        return True
    else:
        return False


def read_HCI(file_path):
    try:
        records = bts.parse(file_path)
        for record in records:
            p = HCI_Hdr(record.data)
            if p.haslayer(HCI_LE_Meta_Advertising_Report):
                #p.show()
                adv_report = p.getlayer(HCI_LE_Meta_Advertising_Report)
                # Nominally this is supposed to be a list of entries, but I've only ever seen one entry in the list
                adv_event_type = adv_report.fields['type']
                if adv_event_type == 0x00:  # ADV_IND
                    export_AdvChannelData(p, type_AdvChanPDU_ADV_IND)
                elif adv_event_type == 0x01:  # ADV_DIRECT_IND
                    export_AdvChannelData(p, type_AdvChanPDU_ADV_DIRECT_IND)
                elif adv_event_type == 0x02:  # ADV_SCAN_IND
                    export_AdvChannelData(p, type_AdvChanPDU_ADV_SCAN_IND)
                elif adv_event_type == 0x03:  # ADV_NONCONN_IND
                    export_AdvChannelData(p, type_AdvChanPDU_ADV_NONCONN_IND)
                elif adv_event_type == 0x04:  # SCAN_RSP
                    export_AdvChannelData(p, type_AdvChanPDU_SCAN_RSP)

    #     return
    except Exception as e:
        print(f"Error reading HCI log file: {e}")
        exit(1)


def main():
    global verbose_print, verbose_BTIDES
    parser = argparse.ArgumentParser(description='HCI file input arguments')
    parser.add_argument('--input', type=str, required=True, help='Input file name for HCI log file.')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')

    # SQL arguments
    sql = parser.add_argument_group('Local SQL database storage arguments (only applicable in the context of a local Blue2thprinting setup, not 3rd party tool usage.)')
    sql.add_argument('--to-SQL', action='store_true', required=False, help='Immediately invoke store output BTIDES file to your local SQL database.')
    sql.add_argument('--use-test-db', action='store_true', required=False, help='This will utilize the alternative bttest database, used for testing.')

    # BTIDALPOOL arguments
    btidalpool_group = parser.add_argument_group('BTIDALPOOL (crowdsourced database) arguments')
    btidalpool_group.add_argument('--to-BTIDALPOOL', action='store_true', required=False, help='Immediately invoke Client-BTIDALPOOL.py on the output BTIDES file to send it to the BTIDALPOOL crowdsourcing SQL database.')
    btidalpool_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')

    printout_group = parser.add_argument_group('Print verbosity arguments')
    printout_group.add_argument('--verbose-print', action='store_true', required=False, help='Show explicit data-not-found output.')
    printout_group.add_argument('--quiet-print', action='store_true', required=False, help='Hide all print output (useful when you only want to use --output to export data).')

    args = parser.parse_args()

    out_BTIDES_filename = args.output
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES

    qprint("Reading all events from HCI log into memory. (This can take a while for large logs. Assume a total time of FIXME.)")
    read_HCI(args.input)

    qprint("Writing BTIDES data to file.")
    write_BTIDES(out_BTIDES_filename)
    qprint("Export completed with no errors.")

    if args.to_SQL:
        b2s_args = btides_to_sql_args(input=out_BTIDES_filename, use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print)
        btides_to_sql(b2s_args)

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

if __name__ == "__main__":
    main()