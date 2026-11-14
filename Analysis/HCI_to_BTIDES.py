########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

# Activate venv before any other imports
from handle_venv import activate_venv
activate_venv()
import argparse
import calendar
from dataclasses import replace

# HCI file reading related adapter to feed into scapy
import hci_log_parser as bts

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
from TME.TME_BTIDES_base import (
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array,
    write_BTIDES,
)
from TME.TME_BTIDES_AdvData import ff_adv_data_type_specific_obj
from TME.TME_BTIDES_LLCP import ff_LL_VERSION_IND

# BTIDALPOOL access related
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

# Used to keep track of state between packets
g_last_handle_to_bdaddr = {}
g_last_handle_transport = {}
g_last_bdaddr_connected_to = None

def export_AdvChannelData(report, adv_type):
    fields = report.fields
    if isinstance(report, HCI_Event_Extended_Inquiry_Result):
        bdaddr_random = 0
        bdaddr = fields['bd_addr']
        data = fields['eir_data']
    else:
        if fields['atype'] > 3:
            return False
        bdaddr_random = fields['atype'] & 1
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


def export_HCI_Extended_Advertising_Report(report, timestamp, source_record_seq, report_index):
    """Keep a nonlegacy HCI report without claiming its data came from one LL PDU."""
    fields = report.fields
    address_type = fields['atype']
    if address_type == 0xff:
        bdaddr, bdaddr_random = '00:00:00:00:00:00', 0xff
    elif address_type in (0, 1, 2, 3):
        bdaddr, bdaddr_random = fields['addr'], address_type & 1
    else:
        return False

    # The fixed part of one HCI LE Extended Advertising Report is 24 bytes.
    # Its Data field can combine several LL advertising PDUs or be a fragment.
    raw_data = report.original[24:24 + fields['len']]
    event_type = int.from_bytes(report.original[:2], 'little')
    hci_entry = {
        'event_code': 0x3e,
        'subevent_code': 0x0d,
        'event_type': event_type,
        'address_type': address_type,
        'primary_phy': fields['primary_phy'],
        'secondary_phy': fields['secondary_phy'],
        'advertising_sid': fields['sid'],
        'tx_power': fields['tx_power'],
        'rssi': fields['rssi'],
        'periodic_adv_interval': fields['periodic_adv_interval'],
        'data_status': fields['data_status'],
        'data_length': fields['len'],
        'advertising_data_hex_str': raw_data.hex(),
        'source_record_seq': source_record_seq,
        'report_index': report_index,
    }
    # hci_log_parser supplies a naive UTC datetime for both BTSnoop and
    # PacketLogger. Use timegm rather than local-time conversion so repeated
    # identical HCI observations keep their distinct collection times.
    unix_time = calendar.timegm(timestamp.utctimetuple())
    hci_entry['std_optional_fields'] = {
        'time': {
            'unix_time': unix_time,
            'unix_time_milli': unix_time * 1000 + timestamp.microsecond // 1000,
        }
    }
    if fields['directed']:
        hci_entry['direct_address_type'] = fields['direct_addr_type']
        hci_entry['direct_address'] = fields['direct_addr']
    if TME.TME_glob.verbose_BTIDES:
        hci_entry['event_code_str'] = 'HCI_LE_Extended_Advertising_Report'

    # Parse complete AD structures for the usual BTIDES queries. Incomplete
    # HCI fragments remain available verbatim above for later reassembly.
    if fields['data_status'] == 0:
        adv_data_array = []

        def collect_adv_data(_bdaddr, _random, _adv_type, adv_data_type, data):
            adv_data = ff_adv_data_type_specific_obj(adv_data_type, data)
            if adv_data is not None:
                adv_data_array.append(adv_data)

        for entry in fields['data']:
            export_AdvData(bdaddr, bdaddr_random, 'HCI_LE_Extended_Advertising_Report',
                           entry, BTIDES_export_AdvData=collect_adv_data)
        if adv_data_array:
            hci_entry['AdvDataArray'] = adv_data_array

    return generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(
        bdaddr, bdaddr_random, hci_entry, 'HCIArray')


def export_to_L2CAPArray(packet, direction):

    acl = packet.getlayer(HCI_ACL_Hdr)
    connection_handle = acl.fields['handle']

    if(acl.fields['handle'] in g_last_handle_to_bdaddr.keys()):
        (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[acl.fields['handle']]
        connect_ind_obj = ff_CONNECT_IND(peripheral_bdaddr=bdaddr, peripheral_bdaddr_rand=bdaddr_type)
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # The opcodes are mutually exclusive, so if one returns true, we're done
    # To convert ATT data into a GATT hierarchy requires us to statefully
    # remember information between packets (i.e. which UUID corresponds to which handle)
    if(export_L2CAP_CONNECTION_REQ(connect_ind_obj, packet, direction=direction,
                                   connection_handle=connection_handle)):
        return True
    if(export_L2CAP_CONNECTION_RSP(connect_ind_obj, packet, direction=direction,
                                   connection_handle=connection_handle)):
        return True
    if(export_L2CAP_CONFIGURATION_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_CONFIGURATION_RSP(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_DISCONNECTION_REQ(connect_ind_obj, packet, direction=direction,
                                      connection_handle=connection_handle)):
        return True
    if(export_L2CAP_DISCONNECTION_RSP(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_INFORMATION_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_INFORMATION_RSP(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(connect_ind_obj, packet, direction=direction)):
        return True
    if(export_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(connect_ind_obj, packet, direction=direction)):
        return True


def export_to_SDPArray(packet, direction):
    acl = packet.getlayer(HCI_ACL_Hdr)

    if(acl.fields['handle'] in g_last_handle_to_bdaddr.keys()):
        (bdaddr, bdaddr_type) = g_last_handle_to_bdaddr[acl.fields['handle']]
        connect_ind_obj = ff_CONNECT_IND(peripheral_bdaddr=bdaddr, peripheral_bdaddr_rand=bdaddr_type)
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    l2cap_hdr = packet.getlayer(L2CAP_Hdr)
    # See if we've seen a connection with PSM == SDP, and see if the CID for this packet matches that one
    if(CID_in_CIDs_used_for_SDP(connect_ind_obj, l2cap_hdr.cid, acl.fields['handle'])):
        # If this matched, then this is an SDP packet
        # packet.show()
        # The opcodes are mutually exclusive, so if one returns true, we're done
        # To convert ATT data into a GATT hierarchy requires us to statefully
        # remember information between packets (i.e. which UUID corresponds to which handle)
        if(export_SDP_ERROR_RSP(connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_Common(type_SDP_SERVICE_SEARCH_REQ, connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_Common(type_SDP_SERVICE_SEARCH_RSP, connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_Common(type_SDP_SERVICE_ATTR_REQ, connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_Common(type_SDP_SERVICE_ATTR_RSP, connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_REQ, connect_ind_obj, packet, direction=direction)):
            return True
        if(export_SDP_Common(type_SDP_SERVICE_SEARCH_ATTR_RSP, connect_ind_obj, packet, direction=direction)):
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


# For now this is biased towards the LMP packet types we have DB tables for
# and/or which we don't have db tables for but which I have data from actual traffic during testing (e.g. on iPhone)
def export_to_LMPArray(packet):

    bdaddr=g_last_bdaddr_connected_to

    #print(bytes_to_hex_str(packet))
    # The opcodes are mutually exclusive, so if one returns true, we're done
    # Note: there's no point in sanity checking the length, because the debug format means it'll always be > 17 bytes,
    # and if the data is wrong there's no way to determine that based on length, only by parsing it further
    LMP_opcode = packet[0] >> 1
    if(LMP_opcode == type_LMP_FEATURES_RES):
        # Convert packet[1:9] (8 bytes, little-endian) into an int
        features = int.from_bytes(packet[1:9], byteorder='little', signed=False)
        BTIDES_export_LMP_FEATURES_RES(bdaddr, features)
        return True
    if(LMP_opcode == type_LMP_FEATURES_REQ):
        # Convert packet[1:9] (8 bytes, little-endian) into an int
        features = int.from_bytes(packet[1:9], byteorder='little', signed=False)
        BTIDES_export_LMP_FEATURES_REQ(bdaddr, features)
        return True
    if(LMP_opcode == type_LMP_AUTO_RATE):
        # No bytes in this packet type
        BTIDES_export_LMP_AUTO_RATE(bdaddr)
        return True
    if(LMP_opcode == type_LMP_PREFERRED_RATE):
        # 1 byte: data_rate
        data_rate = packet[1] if len(packet) > 1 else 0
        BTIDES_export_LMP_PREFERRED_RATE(bdaddr, data_rate)
        return True
    if(LMP_opcode == type_LMP_MAX_SLOT):
        # 1 byte: max_slots
        max_slots = packet[1] if len(packet) > 1 else 0
        BTIDES_export_LMP_MAX_SLOT(bdaddr, max_slots)
        return True
    if(LMP_opcode == type_LMP_MAX_SLOT_REQ):
        # 1 byte: max_slots
        max_slots = packet[1] if len(packet) > 1 else 0
        BTIDES_export_LMP_MAX_SLOT_REQ(bdaddr, max_slots)
        return True
    if(LMP_opcode == type_LMP_TIMING_ACCURACY_REQ):
        # No payload
        BTIDES_export_LMP_TIMING_ACCURACY_REQ(bdaddr)
        return True
    if(LMP_opcode == type_LMP_TIMING_ACCURACY_RES):
        # 1 byte drift, 1 byte jitter (best-effort parsing)
        drift = packet[1] if len(packet) > 1 else 0
        jitter = packet[2] if len(packet) > 2 else 0
        BTIDES_export_LMP_TIMING_ACCURACY_RES(bdaddr, drift, jitter)
        return True
    if(LMP_opcode == type_LMP_ENCRYPTION_KEY_SIZE_MASK_REQ):
        # No bytes in this packet type
        BTIDES_export_LMP_ENCRYPTION_KEY_SIZE_MASK_REQ(bdaddr)
        return True
    if(LMP_opcode == type_LMP_ENCRYPTION_KEY_SIZE_MASK_RES):
        # 2 byte "Key Size Mask" (bit 0 = 1 byte key supported, bit 1 = 2 byte key supported, ..., bit 15 = 16 byte key supported)
        key_size_mask = int.from_bytes(packet[1:3], byteorder='little', signed=False)
        BTIDES_export_LMP_ENCRYPTION_KEY_SIZE_MASK_RES(bdaddr, key_size_mask)
        return True
    if(LMP_opcode == type_LMP_ESCAPE_127):
        extended_opcode = packet[1]
        escape = type_LMP_ESCAPE_127
        if(extended_opcode == type_ext_opcode_LMP_ACCEPTED_EXT):
            rcvd_escape_opcode = packet[2] if len(packet) > 2 else 0
            rcvd_extended_opcode = packet[3] if len(packet) > 3 else 0
            BTIDES_export_LMP_ACCEPTED_EXT(bdaddr, rcvd_escape_opcode, rcvd_extended_opcode)
            return True
        if(extended_opcode == type_ext_opcode_LMP_NOT_ACCEPTED_EXT):
            rcvd_escape_opcode = packet[2] if len(packet) > 2 else 0
            rcvd_extended_opcode = packet[3] if len(packet) > 3 else 0
            error_code = packet[4] if len(packet) > 4 else 0
            BTIDES_export_LMP_NOT_ACCEPTED_EXT(bdaddr, rcvd_escape_opcode, rcvd_extended_opcode, error_code)
            return True
        if(extended_opcode == type_ext_opcode_LMP_POWER_CONTROL_REQ):
            power_adj_req = packet[2] if len(packet) > 2 else 0
            BTIDES_export_LMP_POWER_CONTROL_REQ(bdaddr, power_adj_req)
            return True
        if(extended_opcode == type_ext_opcode_LMP_POWER_CONTROL_RES):
            power_adj_res = packet[2] if len(packet) > 2 else 0
            BTIDES_export_LMP_POWER_CONTROL_RES(bdaddr, power_adj_res)
            return True

    return False


def process_connections(p):
    global g_last_bdaddr_connected_to
    # We have to statefully keep track of what the last bdaddr/type combo was for a given connection handle,
    # because we'll only have the handle as a reference in the LE Read Remote Features Complete event
    if p.haslayer(HCI_LE_Meta_Connection_Complete):
        #p.show()
        event = p.getlayer(HCI_LE_Meta_Connection_Complete)
        if event.fields['status'] == 0:
            clear_SDP_CIDs_for_handle(event.fields['handle'])
            g_last_handle_to_bdaddr[event.fields['handle']] = (event.fields['paddr'], event.fields['patype'] & 1)
            g_last_handle_transport[event.fields['handle']] = 'LE'
        return True
    elif p.haslayer(HCI_LE_Meta_Enhanced_Connection_Update_Complete_v1):
        #p.show()
        event = p.getlayer(HCI_LE_Meta_Enhanced_Connection_Update_Complete_v1)
        if event.fields['status'] == 0:
            clear_SDP_CIDs_for_handle(event.fields['handle'])
            g_last_handle_to_bdaddr[event.fields['handle']] = (event.fields['paddr'], event.fields['patype'] & 1)
            g_last_handle_transport[event.fields['handle']] = 'LE'
        return True
    elif p.haslayer(HCI_Event_Connection_Complete):
        #p.show()
        event = p.getlayer(HCI_Event_Connection_Complete)
        if(event.fields['status'] == 0):
            clear_SDP_CIDs_for_handle(event.fields['handle'])
            g_last_handle_to_bdaddr[event.fields['handle']] = (event.fields['bd_addr'], 0)
            g_last_handle_transport[event.fields['handle']] = 'BR/EDR'
        return True
    elif p.haslayer(HCI_Event_Disconnection_Complete):
        event = p.getlayer(HCI_Event_Disconnection_Complete)
        if event.fields['status'] == 0:
            clear_SDP_CIDs_for_handle(event.fields['handle'])
            g_last_handle_to_bdaddr.pop(event.fields['handle'], None)
            g_last_handle_transport.pop(event.fields['handle'], None)
        return True
    # Note: when processing DarkFirmware_real_i logs, we see LMP traffic after the HCI_Cmd_Create_Connection but before the HCI_Event_Connection_Complete
    # so we need to capture the bdaddr at this point to be able to make sense of that LMP traffic
    elif p.haslayer(HCI_Cmd_Create_Connection):
        #p.show()
        command = p.getlayer(HCI_Cmd_Create_Connection)
        g_last_bdaddr_connected_to = command.fields['bd_addr']
        return True

    return False


def process_remote_version(p):
    if not p.haslayer(HCI_Event_Read_Remote_Version_Information_Complete):
        return False

    event = p.getlayer(HCI_Event_Read_Remote_Version_Information_Complete)
    handle = event.fields['handle']
    if event.fields['status'] == 0 and handle in g_last_handle_to_bdaddr:
        bdaddr, bdaddr_type = g_last_handle_to_bdaddr[handle]
        version = event.fields['version']
        company_id = event.fields['manufacturer_name']
        subversion = event.fields['subversion']
        if g_last_handle_transport.get(handle) == 'LE':
            data = ff_LL_VERSION_IND(type_BTIDES_direction_P2C, version, company_id, subversion)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_type, data=data)
        elif g_last_handle_transport.get(handle) == 'BR/EDR':
            BTIDES_export_LMP_VERSION_RES(bdaddr, version, company_id, subversion)
    return True


def process_advertisements(p, record):
    if p.haslayer(HCI_LE_Meta_Advertising_Reports):
        #p.show()
        data_exported = False
        adv_report = p.getlayer(HCI_LE_Meta_Advertising_Reports)
        for report in adv_report.fields['reports']:
            adv_event_type = report.fields['type']
            if adv_event_type == 0x00:  # ADV_IND
                if(export_AdvChannelData(report, type_AdvChanPDU_ADV_IND)):
                    data_exported = True
            elif adv_event_type == 0x01:  # ADV_DIRECT_IND
                if(export_AdvChannelData(report, type_AdvChanPDU_ADV_DIRECT_IND)):
                    data_exported = True
            elif adv_event_type == 0x02:  # ADV_SCAN_IND
                if export_AdvChannelData(report, type_AdvChanPDU_ADV_SCAN_IND):
                    data_exported = True
            elif adv_event_type == 0x03:  # ADV_NONCONN_IND
                if export_AdvChannelData(report, type_AdvChanPDU_ADV_NONCONN_IND):
                    data_exported = True
            elif adv_event_type == 0x04:  # SCAN_RSP
                if export_AdvChannelData(report, type_AdvChanPDU_SCAN_RSP):
                    data_exported = True
        if data_exported:
            return True
    elif p.haslayer(HCI_LE_Meta_Extended_Advertising_Reports):
        #p.show()
        data_exported = False
        adv_report = p.getlayer(HCI_LE_Meta_Extended_Advertising_Reports)
        for report_index, report in enumerate(adv_report.fields['reports']):
            if not report.fields['legacy']:
                if export_HCI_Extended_Advertising_Report(
                        report, record.ts, record.seq, report_index):
                    data_exported = True
                continue

            # Per "Event_Type values for legacy PDUs" all of the below are legacy + the following:
            # 0b0000 - ADV_NONCONN_IND
            if not report.fields['scan_rsp'] and not report.fields['directed'] and not report.fields['scannable'] and not report.fields['connectable']:
                if export_AdvChannelData(report, type_AdvChanPDU_ADV_NONCONN_IND):
                    data_exported = True
                    continue
            # 0b0010 - ADV_SCAN_IND
            elif not report.fields['scan_rsp'] and not report.fields['directed'] and report.fields['scannable'] and not report.fields['connectable']:
                if export_AdvChannelData(report, type_AdvChanPDU_ADV_SCAN_IND):
                    data_exported = True
                    continue
            # 0b0011 - ADV_IND
            if not report.fields['scan_rsp'] and not report.fields['directed'] and report.fields['scannable'] and report.fields['connectable']:
                if export_AdvChannelData(report, type_AdvChanPDU_ADV_IND):
                    data_exported = True
                    continue
            # 0b0101 - ADV_DIRECT_IND
            elif not report.fields['scan_rsp'] and report.fields['directed'] and not report.fields['scannable'] and report.fields['connectable']:
                if export_AdvChannelData(report, type_AdvChanPDU_ADV_DIRECT_IND):
                    data_exported = True
                    continue
            # 0b1011 - SCAN_RSP to ADV_IND or 0b1010 - SCAN_RSP to ADV_SCAN_IND
            elif report.fields['scan_rsp'] and not report.fields['directed'] and report.fields['scannable']:
                if export_AdvChannelData(report, type_AdvChanPDU_SCAN_RSP):
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
                export_AdvChannelData(inq_result, type_BTIDES_EIR)
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
                name_str = event.fields['remote_name'].decode('utf-8','ignore').rstrip('\x00') # This will remove all the null bytes at the end
            except UnicodeDecodeError as e:
                print(f"Error decoding remote name: {e}")
                return False
            remote_name_hex_str = str_to_hex_str(name_str)
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


# Just hacking this in for now, since I don't want to fight with scapy definitions
def process_DarkFirmware_LMP_Log(p, record):
    if p.haslayer(HCI_Event_Hdr) and p.code == 0xff and p.len == 56:
        #print(record)
        # The vendor-specific event sent back by DarkFirmware_real_i will always start with "AAAA"
        # and have 0xCC-initialized data at offset 0x1C for unused data which hasn't been filled in with an incoming LMP packet
        if(bytes_to_hex_str(p.load[0:4]) != "41414141" or (len(p.load) > 0x1C and p.load[0x1C] == 0xCC)):
            return False
        else:
            #print("DarkFirmware_real_i LMP log data found")
            export_to_LMPArray(p.load[28:])
            return True
    return False


def _reassemble_sdp_acl(record, fragments):
    """Join HCI ACL fragments only for an identified SDP dynamic channel."""
    raw = record.data
    if len(raw) < 5 or raw[0] != 2:
        return record
    handle_flags = int.from_bytes(raw[1:3], 'little')
    handle = handle_flags & 0x0fff
    boundary = (handle_flags >> 12) & 3
    acl_len = int.from_bytes(raw[3:5], 'little')
    if acl_len != len(raw) - 5:
        if handle in fragments:
            fragments.pop(handle, None)
            return None
        return record
    if boundary == 1:  # continuation fragment
        pending = fragments.get(handle)
        if pending is None:
            return None
        first_record, expected, payload = pending
        if record.flags != first_record.flags:
            fragments.pop(handle, None)
            return None
        payload += raw[5:]
        if len(payload) < expected:
            fragments[handle] = (first_record, expected, payload)
            return None
        fragments.pop(handle, None)
        if len(payload) != expected:
            return None
        frame = (first_record.data[:3] + expected.to_bytes(2, 'little') + payload)
        return replace(first_record, data=frame, length=len(frame))
    if boundary in (0, 2):  # start of a new L2CAP PDU
        fragments.pop(handle, None)
        if len(raw) >= 9:
            l2cap_len = int.from_bytes(raw[5:7], 'little')
            cid = int.from_bytes(raw[7:9], 'little')
            expected = 4 + l2cap_len
            if (acl_len < expected and
                    ('hci_handle', handle, cid) in g_CIDs_used_for_SDP):
                fragments[handle] = (record, expected, raw[5:])
                return None
    return record


def read_HCI(file_path):
    g_last_handle_to_bdaddr.clear()
    g_last_handle_transport.clear()
    g_CIDs_used_for_SDP.clear()
    sdp_acl_fragments = {}
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

            record = _reassemble_sdp_acl(record, sdp_acl_fragments)
            if record is None:
                continue
            try:
                p = HCI_Hdr(record.data)
            except Exception as e:
                print(f"Error forcing HCI_Hdr type on packet: {e}")
                exit(1)

            #p.show()
            if p.haslayer(HCI_Event_Disconnection_Complete):
                sdp_acl_fragments.pop(
                    p.getlayer(HCI_Event_Disconnection_Complete).fields['handle'], None)
            elif p.haslayer(HCI_Event_Connection_Complete):
                sdp_acl_fragments.pop(
                    p.getlayer(HCI_Event_Connection_Complete).fields['handle'], None)
            elif p.haslayer(HCI_LE_Meta_Connection_Complete):
                sdp_acl_fragments.pop(
                    p.getlayer(HCI_LE_Meta_Connection_Complete).fields['handle'], None)
            if(process_connections(p)):
                continue
            elif(process_remote_version(p)):
                continue
            elif(process_advertisements(p, record)):
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
            elif(process_DarkFirmware_LMP_Log(p, record)):
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
    if args.to_BTIDALPOOL and not out_BTIDES_filename:
        # Create a default temporary filename if people provide the --to-BTIDALPOOL flag without a --output filename
        out_BTIDES_filename = "/tmp/hci2btides.btides"
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES

    qprint("Reading all events from HCI log into memory.")
    if not read_HCI(args.input):
        raise SystemExit(1)

    qprint("Writing BTIDES data to file.")
    write_BTIDES(out_BTIDES_filename)
    qprint("Export completed with no errors.")

    btides_to_sql_succeeded = False
    if args.to_SQL:
        b2s_args = btides_to_sql_args(input=[out_BTIDES_filename], use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print)
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
            refresh_token=client.credentials.refresh_token,
            use_test_db=args.use_test_db
        )

    if(btides_to_sql_succeeded and args.rename):
        os.rename(out_BTIDES_filename, out_BTIDES_filename + ".processed")

if __name__ == "__main__":
    main()
