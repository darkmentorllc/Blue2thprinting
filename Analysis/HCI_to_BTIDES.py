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

# Used to keep track of state between packets
g_last_handle_to_bdaddr = {}

def export_AdvChannelData(packet, scapy_type, adv_type):
    fields = packet.getlayer(scapy_type).fields
    if(scapy_type == HCI_Event_Extended_Inquiry_Result):
        bdaddr_random = 0
        bdaddr = fields['bd_addr']
        data = fields['eir_data']
    else:
        bdaddr_random = fields['atype']
        bdaddr = fields['addr']
        data = fields['data']

    data_exported = False
    for entry in data: # This is an array of AdvData entries
        if export_AdvData(bdaddr, bdaddr_random, adv_type, entry):
            data_exported = True

    if(data_exported or (adv_type == type_AdvChanPDU_SCAN_RSP and len(data) == 0)):
        return True
    else:
        return False # This is known to fire for things not yet supported like unprovisioned mesh beacons


def export_to_L2CAPArray(packet, direction):

    acl = packet.getlayer(HCI_ACL_Hdr)

    if(acl.fields['handle'] in g_last_handle_to_bdaddr.keys()):
        (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[acl.fields['handle']]
        connect_ind_obj = ff_CONNECT_IND(peripheral_bdaddr=bdaddr, peripheral_bdaddr_rand=bdaddr_type)
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # The opcodes are mutually exclusive, so if one returns true, we're done
    # To convert ATT data into a GATT hierarchy requires us to statefully
    # remember information between packets (i.e. which UUID corresponds to which handle)
    if(export_L2CAP_CONNECTION_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_CONNECTION_RSP(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_CONFIGURATION_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_CONFIGURATION_RSP(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_DISCONNECTION_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_DISCONNECTION_RSP(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_INFORMATION_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_INFORMATION_RSP(connect_ind_obj, packet, direction=direction)):
        return True


def export_to_SDPArray(packet, direction):
    packet.show()
    acl = packet.getlayer(HCI_ACL_Hdr)

    if(acl.fields['handle'] in g_last_handle_to_bdaddr.keys()):
        (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[acl.fields['handle']]
        connect_ind_obj = ff_CONNECT_IND(peripheral_bdaddr=bdaddr, peripheral_bdaddr_rand=bdaddr_type)
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    l2cap_hdr = packet.getlayer(L2CAP_Hdr)
    # See if we've seen a connection with PSM == SDP, and see if the CID for this packet matches that one
    if(CID_in_CIDs_used_for_SDP(connect_ind_obj, l2cap_hdr.cid)):
        # If this matched, then this is an SDP packet

        # The opcodes are mutually exclusive, so if one returns true, we're done
        # To convert ATT data into a GATT hierarchy requires us to statefully
        # remember information between packets (i.e. which UUID corresponds to which handle)
        if(export_SDP_SERVICE_SEARCH_ATTR_REQ(connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_SERVICE_SEARCH_ATTR_RSP(connect_ind_obj, packet, direction=direction)):
            return True

def export_to_ATTArray(packet, direction):

    acl = packet.getlayer(HCI_ACL_Hdr)

    if(acl.fields['handle'] in g_last_handle_to_bdaddr.keys()):
        (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[acl.fields['handle']]
        connect_ind_obj = ff_CONNECT_IND(peripheral_bdaddr=bdaddr, peripheral_bdaddr_rand=bdaddr_type)
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # The opcodes are mutually exclusive, so if one returns true, we're done
    # To convert ATT data into a GATT hierarchy requires us to statefully
    # remember information between packets (i.e. which UUID corresponds to which handle)
    if(export_ATT_Error_Response(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Exchange_MTU_Request(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Exchange_MTU_Response(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Read_Request(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Read_Response(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Find_Information_Request(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Find_Information_Response(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Read_By_Group_Type_Request(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_ATT_Read_By_Group_Type_Response(connect_ind_obj, packet, direction=direction)):
        return True


def export_to_SMPArray(packet, direction):

    acl = packet.getlayer(HCI_ACL_Hdr)

    if(acl.fields['handle'] in g_last_handle_to_bdaddr.keys()):
        (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[acl.fields['handle']]
        connect_ind_obj = ff_CONNECT_IND(peripheral_bdaddr=bdaddr, peripheral_bdaddr_rand=bdaddr_type)
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    #packet.show()
    # The opcodes are mutually exclusive, so if one returns true, we're done
    if(export_SMP_Pairing_Request(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_SMP_Pairing_Response(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_SMP_Pairing_Confirm(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_SMP_Pairing_Random(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_SMP_Pairing_Failed(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_SMP_Security_Request(connect_ind_obj, packet, direction=direction)):
        return True
    # FIXME! Apparently Scapy doesn't handle defragmentation :-/
    # So we'll need to do this ourselves if we want to get this data
    # if(export_SMP_Pairing_Public_Key(connect_ind_obj, packet, direction=direction)):
    #     return True
    if(export_SMP_Pairing_DHKey_Check(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_SMP_Pairing_Keypress_Notification(connect_ind_obj, packet, direction=direction)):
        return True

def process_connections(p):
    # We have to statefully keep track of what the last bdaddr/type combo was for a given connection handle,
    # because we'll only have the handle as a reference in the LE Read Remote Features Complete event
    if p.haslayer(HCI_LE_Meta_Connection_Complete):
        #p.show()
        event = p.getlayer(HCI_LE_Meta_Connection_Complete)
        g_last_handle_to_bdaddr[event.fields['handle']] = (event.fields['paddr'], event.fields['patype'])
        return True
    elif p.haslayer(HCI_LE_Meta_Enhanced_Connection_Update_Complete_v1):
        #p.show()
        event = p.getlayer(HCI_LE_Meta_Enhanced_Connection_Update_Complete_v1)
        g_last_handle_to_bdaddr[event.fields['handle']] = (event.fields['paddr'], event.fields['patype'])
        return True
    elif p.haslayer(HCI_Event_Connection_Complete):
        #p.show()
        event = p.getlayer(HCI_Event_Connection_Complete)
        if(event.fields['status'] == 0):
            g_last_handle_to_bdaddr[event.fields['handle']] = (event.fields['bd_addr'], 0)
        return True
    #HCI_Cmd_Create_Connection
    return False


def process_advertisements(p):
    if p.haslayer(HCI_LE_Meta_Advertising_Reports):
        #p.show()
        data_exported = False
        adv_report = p.getlayer(HCI_LE_Meta_Advertising_Reports)
        for report in adv_report.fields['reports']:
            adv_event_type = report.fields['type']
            if adv_event_type == 0x00:  # ADV_IND
                if(export_AdvChannelData(p, HCI_LE_Meta_Advertising_Report, type_AdvChanPDU_ADV_IND)):
                    data_exported = True
            elif adv_event_type == 0x01:  # ADV_DIRECT_IND
                if(export_AdvChannelData(p, HCI_LE_Meta_Advertising_Report, type_AdvChanPDU_ADV_DIRECT_IND)):
                    data_exported = True
            elif adv_event_type == 0x02:  # ADV_SCAN_IND
                if export_AdvChannelData(p, HCI_LE_Meta_Advertising_Report, type_AdvChanPDU_ADV_SCAN_IND):
                    data_exported = True
            elif adv_event_type == 0x03:  # ADV_NONCONN_IND
                if export_AdvChannelData(p, HCI_LE_Meta_Advertising_Report, type_AdvChanPDU_ADV_NONCONN_IND):
                    data_exported = True
            elif adv_event_type == 0x04:  # SCAN_RSP
                if export_AdvChannelData(p, HCI_LE_Meta_Advertising_Report, type_AdvChanPDU_SCAN_RSP):
                    data_exported = True
            if (data_exported):
                return True
    elif p.haslayer(HCI_LE_Meta_Extended_Advertising_Reports):
        #p.show()
        data_exported = False
        adv_report = p.getlayer(HCI_LE_Meta_Extended_Advertising_Reports)
        for report in adv_report.fields['reports']:
            # Only tested with one non-legacy sample so far...
            #if(report.fields['legacy']):
            # Per "Event_Type values for legacy PDUs" all of the below are legacy + the following:
            # 0b0000 - ADV_NONCONN_IND
            if not report.fields['scan_rsp'] and not report.fields['directed'] and not report.fields['scannable'] and not report.fields['connectable']:
                if export_AdvChannelData(p, HCI_LE_Meta_Extended_Advertising_Report, type_AdvChanPDU_ADV_NONCONN_IND):
                    data_exported = True
                    continue
            # 0b0010 - ADV_SCAN_IND
            elif not report.fields['scan_rsp'] and not report.fields['directed'] and report.fields['scannable'] and not report.fields['connectable']:
                if export_AdvChannelData(p, HCI_LE_Meta_Extended_Advertising_Report, type_AdvChanPDU_ADV_SCAN_IND):
                    data_exported = True
                    continue
            # 0b0011 - ADV_IND
            if not report.fields['scan_rsp'] and not report.fields['directed'] and report.fields['scannable'] and report.fields['connectable']:
                if export_AdvChannelData(p, HCI_LE_Meta_Extended_Advertising_Report, type_AdvChanPDU_ADV_IND):
                    data_exported = True
                    continue
            # 0b0101 - ADV_DIRECT_IND
            elif not report.fields['scan_rsp'] and report.fields['directed'] and not report.fields['scannable'] and report.fields['connectable']:
                if export_AdvChannelData(p, HCI_LE_Meta_Extended_Advertising_Report, type_AdvChanPDU_ADV_DIRECT_IND):
                    data_exported = True
                    continue
            # 0b1011 - SCAN_RSP to ADV_IND or 0b1010 - SCAN_RSP to ADV_SCAN_IND
            elif report.fields['scan_rsp'] and not report.fields['directed'] and report.fields['scannable']:
                if export_AdvChannelData(p, HCI_LE_Meta_Extended_Advertising_Report, type_AdvChanPDU_SCAN_RSP):
                    data_exported = True
        if (data_exported):
            return True
    elif p.haslayer(HCI_Event_Extended_Inquiry_Result):
        #p.show()
        inq_result = p.getlayer(HCI_Event_Extended_Inquiry_Result)
        export_Page_Scan_Repetition_Mode(inq_result.fields['bd_addr'], inq_result.fields['page_scan_repetition_mode'])
        CoD_hex_str = f"{inq_result.fields['device_class']:06x}"
        export_Class_of_Device(inq_result.fields['bd_addr'], CoD_hex_str)
        # Note: just doing it this way unlike the other entries because it seems scapy doesn't have support for num_response > 1
        if(inq_result.fields['num_response'] > 1):
            print("We have never seen this test case of num_response > 1. Please submit this sample so we can handle it.")
            exit(1)
        if (p.haslayer(EIR_Hdr)):
            eir = p.getlayer(EIR_Hdr)
            if eir.fields['len'] != 0:
                export_AdvChannelData(p, HCI_Event_Extended_Inquiry_Result, type_BTIDES_EIR)
        return True
    elif p.haslayer(HCI_Event_Inquiry_Result):
        #p.show()
        inq_result = p.getlayer(HCI_Event_Inquiry_Result)
        export_Page_Scan_Repetition_Mode(inq_result.fields['addr'], inq_result.fields['page_scan_repetition_mode'])
        CoD_hex_str = f"{inq_result.fields['device_class']:06x}"
        export_Class_of_Device(inq_result.fields['bd_addr'], CoD_hex_str)
        # Note: just doing it this way unlike the other entries because it seems scapy doesn't have support for num_response > 1
        if(inq_result.fields['num_response'] > 1):
            print("We have never seen this test case of num_response > 1. Please submit this sample so we can handle it.")
            exit(1)
        # This has no AdvData inclusion
        return True
    elif p.haslayer(HCI_Event_Inquiry_Result_With_Rssi):
        #p.show()
        inq_result = p.getlayer(HCI_Event_Inquiry_Result_With_Rssi)
        export_Page_Scan_Repetition_Mode(inq_result.fields['bd_addr'], inq_result.fields['page_scan_repetition_mode'])
        CoD_hex_str = f"{inq_result.fields['device_class']:06x}"
        export_Class_of_Device(inq_result.fields['bd_addr'], CoD_hex_str)
        # Note: just doing it this way unlike the other entries because it seems scapy doesn't have support for num_response > 1
        if(inq_result.fields['num_response'] > 1):
            print("We have never seen this test case of num_response > 1. Please submit this sample so we can handle it.")
            exit(1)
        # This has no AdvData inclusion
        return True
    # This is obviously not an advertisement, but it does include the Class of Device, so we will collect it here with the other CoD entries
    elif p.haslayer(HCI_Event_Connection_Request):
        connection_req = p.getlayer(HCI_Event_Connection_Request)
        CoD_hex_str = f"{connection_req.fields['device_class']:06x}"
        export_Class_of_Device(connection_req.fields['bd_addr'], CoD_hex_str)
        return True
    return False


def process_features(p):
    if p.haslayer(HCI_LE_Meta_LE_Read_Remote_Features_Complete):
        #p.show()
        event = p.getlayer(HCI_LE_Meta_LE_Read_Remote_Features_Complete)
        if(event.fields['handle'] in g_last_handle_to_bdaddr.keys()):
            features_int = event.fields['le_features']
            (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[event.fields['handle']]
            data = {"direction": type_BTIDES_direction_P2C, "bdaddr": bdaddr, "bdaddr_type": bdaddr_type, "features": features_int}
            export_LE_Features(bdaddr, bdaddr_type, data)
        return True
    elif p.haslayer(HCI_Event_Read_Remote_Extended_Features_Complete):
        #p.show()
        event = p.getlayer(HCI_Event_Read_Remote_Extended_Features_Complete)
        if(event.fields['handle'] in g_last_handle_to_bdaddr.keys() and event.fields['status'] == 0):
            features_int = event.fields['extended_features']
            page = event.fields['page']
            max_page = event.fields['max_page']
            (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[event.fields['handle']]
            data = {"bdaddr": bdaddr, "page": page, "max_page": max_page, "features": features_int}
            export_LMP_Features_Ext(bdaddr, data)
        return True
    elif p.haslayer(HCI_Event_Read_Remote_Supported_Features_Complete):
        #p.show()
        event = p.getlayer(HCI_Event_Read_Remote_Supported_Features_Complete)
        if(event.fields['handle'] in g_last_handle_to_bdaddr.keys() and event.fields['status'] == 0):
            features_int = event.fields['lmp_features'].value
            (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[event.fields['handle']]
            data = {"bdaddr": bdaddr, "page": 0, "features": features_int}
            export_LMP_Features(bdaddr, data)
        return True
    elif p.haslayer(HCI_Event_Remote_Host_Supported_Features_Notification):
        #p.show()
        event = p.getlayer(HCI_Event_Remote_Host_Supported_Features_Notification)
        features_int = event.fields['lmp_features'].value
        bdaddr = event.fields['bd_addr']
        data = {"bdaddr": bdaddr, "page": 0, "features": features_int}
        export_LMP_Features(bdaddr, data)
        return True

    return False


def process_names(p):
    if p.haslayer(HCI_Event_Remote_Name_Request_Complete):
        #p.show()
        event = p.getlayer(HCI_Event_Remote_Name_Request_Complete)
        # Not going to capture anything other than status = Success (0) for now
        # (FWIW the most common alt status is 0x04 which is timeout, but that doesn't feel useful to capture
        # because it could just mean that something was too far away and didn't hear us.)
        if(event.fields['status'] == 0):
            try:
                name_str = event.fields['remote_name'].decode('utf-8').rstrip('\x00') # This will remove all the null bytes at the end
            except UnicodeDecodeError as e:
                print(f"Error decoding remote name: {e}")
                return False
            remote_name_hex_str = ''.join(format(byte, '02x') for byte in name_str.encode('utf-8'))
            export_Remote_Name_Request_Complete(event.fields['bd_addr'], remote_name_hex_str)
            return True

    return False


def process_L2CAP(p, record):
    if p.haslayer(L2CAP_CmdHdr):
        #print(record)
        if(record.flags == 0): # AFAICT 0 = C2P and 1 = P2C
            direction = type_BTIDES_direction_C2P
        else:
            direction = type_BTIDES_direction_P2C
        if(export_to_L2CAPArray(p, direction)):
            return True
    return False


def process_SDP(p, record):
    if p.haslayer(L2CAP_Hdr):
        #print(record)
        if(record.flags == 0): # AFAICT 0 = C2P and 1 = P2C
            direction = type_BTIDES_direction_C2P
        else:
            direction = type_BTIDES_direction_P2C
        if(export_to_SDPArray(p, direction)):
            return True
    return False

def process_ATT(p, record):
    if p.haslayer(ATT_Hdr):
        #print(record)
        if(record.flags == 0): # AFAICT 0 = C2P and 1 = P2C
            direction = type_BTIDES_direction_C2P
        else:
            direction = type_BTIDES_direction_P2C
        if(export_to_ATTArray(p, direction)):
            return True
    return False


def process_SMP(p, record):
    if p.haslayer(SM_Hdr):
        #print(record)
        if(record.flags == 0): # AFAICT 0 = C2P and 1 = P2C
            direction = type_BTIDES_direction_C2P
        else:
            direction = type_BTIDES_direction_P2C
        if(export_to_SMPArray(p, direction)):
            return True
    return False


def read_HCI(file_path):
    try:
        try:
            records = bts.parse(file_path)
        except Exception as e:
            print(f"Error reading HCI log file: {e}")
            # Note: as a temporary measure while doing bulk imports, make this return False instead of exit(1),
            # so that invalid data can just be bypassed and the overall process can continue
            #exit(1)
            return False
        total_records = len(records)
        # for record in records:
        for i, record in enumerate(records, start=0):
            # Print progress every 1%
            if total_records > 0 and i % max(1, total_records // 100) == 0:
                qprint(f"Processed {i} out of {total_records} records ({(i / total_records) * 100:.0f}%)")

            try:
                p = HCI_Hdr(record.data)
            except Exception as e:
                print(f"Error forcing HCI_Hdr type on packet: {e}")
                exit(1)

            #p.show()
            if(process_connections(p)):
                continue
            elif(process_advertisements(p)):
                continue
            elif(process_features(p)):
                continue
            elif(process_names(p)):
                continue
            elif(process_L2CAP(p, record)):
                continue
            elif(process_SDP(p, record)):
                continue
            elif(process_ATT(p, record)):
                continue
            elif(process_SMP(p, record)):
                continue

        return True
    except Exception as e:
        print(f"Caught unhandled exception: {e}")
        # Note: as a temporary measure while doing bulk imports, make this return False instead of exit(1),
        # so that invalid data can just be bypassed and the overall process can continue
        #exit(1)
        return False


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

    qprint("Reading all events from HCI log into memory.")
    read_HCI(args.input)

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