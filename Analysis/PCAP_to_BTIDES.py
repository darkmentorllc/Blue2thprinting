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
from scapy.all import *
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

from TME.TME_helpers import qprint, vprint
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
import TME.TME_glob
from TME.TME_BTIDES_base import write_BTIDES, insert_std_optional_fields
# Advertisement Channel
from TME.TME_BTIDES_AdvData import BTIDES_export_AdvData
# from TME.TME_AdvChan import ff_CONNECT_IND, ff_CONNECT_IND_placeholder
from TME.TME_AdvChan import *
# LL Control
from TME.TME_BTIDES_LL import *
import subprocess
# ATT
from TME.TME_BTIDES_ATT import * # Tired of importing everything. Want things to just work.
# GATT
from TME.TME_BTIDES_GATT import * # Tired of importing everything. Want things to just work.



g_access_address_to_connect_ind_obj = {}

# We need to keep state between ATT_READ_BY_GROUP_TYPE_REQ and ATT_READ_BY_GROUP_TYPE_RSP
# in order to insert GATT service information into the BTIDES JSON
g_last_ATT_group_type_requested = 0

# Saved text for printing fields
#    for field in btle_adv.fields_desc:
#        print(f"{field.name}: {field.__class__.__name__}")

############################
# Helper "factory functions"
############################

def exit_on_len_mismatch(length, entry):
    if(length != entry.len):
        print("Interesting length mismatch. Check if it's a bug or if it's a malformed packet.")
        entry.show()
        exit(-1)


def scapy_flags_to_hex_str(entry):
    #entry.show()
    b = 0
    if(entry.flags.limited_disc_mode):
        b |= 1 << 0
    if(entry.flags.general_disc_mode):
        b |= 1 << 1
    if(entry.flags.br_edr_not_supported):
        b |= 1 << 2
    if(entry.flags.simul_le_br_edr_ctrl):
        b |= 1 << 3
    if(entry.flags.simul_le_br_edr_host):
        b |= 1 << 4

    flags_hex_str = f"{b:02x}"
    #qprint(f"flags_hex_str = {flags_hex_str}")
    return flags_hex_str

# This is just a simple wrapper around insert_std_optional_fields to insert any
# additional information that we may be able to glean from the packet
def if_verbose_insert_std_optional_fields(obj, packet):
    if(not TME.TME_glob.verbose_BTIDES):
        return

    if(packet.haslayer(BTLE_RF)):
        rf_fields = packet.getlayer(BTLE_RF)
        channel_freq = rf_fields.rf_channel * 2 + 2402 # Channel in MHz
        RSSI = rf_fields.signal
        insert_std_optional_fields(obj, channel_freq=channel_freq, RSSI=RSSI)

def get_packet_direction(packet):
    rf_fields = packet.getlayer(BTLE_RF)
    if(rf_fields.type == 2): # Scapy calls 2 = "DATA_M_TO_S" and 3 = "DATA_S_TO_M"
        return type_BTIDES_direction_C2P
    else:
        return type_BTIDES_direction_P2C

# This is the main function which converts from Scapy data format to BTIDES
def export_AdvData(device_bdaddr, bdaddr_random, adv_type, entry):
    #entry.show()

    # type 1
    if isinstance(entry.payload, EIR_Flags):
        flags_hex_str = scapy_flags_to_hex_str(entry)
        length = 2 # 1 bytes for opcode + 1 byte for flags
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "flags_hex_str": flags_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} Flags: {flags_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_Flags, data)
        return True

    # type 2
    elif isinstance(entry.payload, EIR_IncompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        vprint(f"{device_bdaddr}: {adv_type} Incomplete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListIncomplete, data)
        return True

    # type 3
    elif isinstance(entry.payload, EIR_CompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        vprint(f"{device_bdaddr}: {adv_type} Complete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListComplete, data)
        return True

    # type 4
    elif isinstance(entry.payload, EIR_IncompleteList32BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID32List = [f"{uuid:08x}" for uuid in uuid_list]
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32List": UUID32List}
        vprint(f"{device_bdaddr}: {adv_type} Incomplete UUID32 list: {','.join(UUID32List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ListIncomplete, data)
        return True

    # type 5
    elif isinstance(entry.payload, EIR_CompleteList32BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID32List = [f"{uuid:08x}" for uuid in uuid_list]
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32List": UUID32List}
        vprint(f"{device_bdaddr}: {adv_type} Complete UUID32 list: {','.join(UUID32List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ListComplete, data)
        return True

    # type 6
    elif isinstance(entry.payload, EIR_IncompleteList128BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID128List = [str(uuid) for uuid in uuid_list]
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID128List": UUID128List}
        vprint(f"{device_bdaddr}: {adv_type} Incomplete UUID128 list: {','.join(UUID128List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ListIncomplete, data)
        return True

    # type 7
    elif isinstance(entry.payload, EIR_CompleteList128BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID128List = [str(uuid) for uuid in uuid_list]
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID128List": UUID128List}
        vprint(f"{device_bdaddr}: {adv_type} Complete UUID128 list: {','.join(UUID128List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ListComplete, data)
        return True

    # type 8
    elif isinstance(entry.payload, EIR_ShortenedLocalName):
        local_name = entry.local_name
        utf8_name = local_name.decode('utf-8', 'ignore')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_IncompleteName, data)
        vprint(f"{device_bdaddr}: {adv_type} Incomplete Local Name: {utf8_name}")
        return True

    # type 9
    elif isinstance(entry.payload, EIR_CompleteLocalName):
        local_name = entry.local_name
        utf8_name = local_name.decode('utf-8', 'ignore')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} Complete Local Name: {utf8_name}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_CompleteName, data)
        return True

    # type 0x0A
    elif isinstance(entry.payload, EIR_TX_Power_Level):
        device_tx_power = entry.level
        length = 2 # 1 byte for opcode, 1 byte power level
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "tx_power": device_tx_power}
        vprint(f"{device_bdaddr}: {adv_type} TxPower level: {device_tx_power}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_TxPower, data)
        return True

    # type 0x0D
    elif isinstance(entry.payload, EIR_ClassOfDevice):
        #entry.show()
        major_service_classes = entry.major_service_classes.value # Note the .value, which is how we turn a Scapy FlagsField into an integer apparently...
        major_device_class = entry.major_device_class
        minor_device_class = entry.minor_device_class
        fixed = entry.fixed
        CoD_int = (major_service_classes << 13) | (major_device_class << 8) | (minor_device_class << 2) | fixed
        #qprint(f"{CoD_int:06x}")
        CoD_hex_str = f"{CoD_int:06x}"
        length = 4 # 1 byte for opcode, 3 byte CoD
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "CoD_hex_str": CoD_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} Class of Device: {CoD_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_ClassOfDevice, data)
        return True

    # type 0x10
    # I don't think this can actually appear in BLE as opposed to EIR...so I'm not sure if this will get any testing...
    elif isinstance(entry.payload, EIR_Device_ID):
        device_tx_power = entry.level
        length = 9 # 1 byte for opcode + 2 bytes * 4 fields
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "vendor_id_source": entry.vendor_id_source, "vendor_id": entry.vendor_id, "product_id": entry.product_id, "version": entry.version}
        vprint(f"{device_bdaddr}: {adv_type} Device ID: {data}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_DeviceID, data)
        return True

    # type 0x12
    elif isinstance(entry.payload, EIR_PeripheralConnectionIntervalRange):
        #entry.show()
        conn_interval_min = entry.conn_interval_min
        conn_interval_max = entry.conn_interval_max
        length = 5 # 1 byte for opcode, 2*2 byte parameters
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "conn_interval_min": conn_interval_min, "conn_interval_max": conn_interval_max}
        vprint(f"{device_bdaddr}: {adv_type} conn_interval_min: {conn_interval_min}, conn_interval_max: {conn_interval_max}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_PeripheralConnectionIntervalRange, data)
        return True

    # type 0x16
    elif isinstance(entry.payload, EIR_ServiceData16BitUUID):
        #entry.show()
        length = entry.len # Not clear if Scapy is using the original ACID len or their calculated and corrected len
        UUID16_hex_str = f"{entry.svc_uuid:04x}"
        # Some devices don't include any actual service data (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of service data beyond the UUID16 before accessing .load
        if(length > 3): # 1 byte type + 2 byte UUID16
            service_data_hex_str = ''.join(format(byte, '02x') for byte in entry.load)
        else:
            service_data_hex_str = ""
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16": UUID16_hex_str, "service_data_hex_str": service_data_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} UUID16: {UUID16_hex_str}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ServiceData, data)
        return True

    # # type 0x17
    # elif isinstance(entry.payload, EIR_PeripheralConnectionIntervalRange):
    #     #entry.show()
    #     conn_interval_min = entry.conn_interval_min
    #     conn_interval_max = entry.conn_interval_max
    #     length = 5 # 1 byte for opcode, 2*2 byte parameters
    #     exit_on_len_mismatch(length, entry)
    #     data = {"length": length, "conn_interval_min": conn_interval_min, "conn_interval_max": conn_interval_max}
    #     vprint(f"{device_bdaddr}: {adv_type} conn_interval_min: {conn_interval_min}, conn_interval_max: {conn_interval_max}")
    #     BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_PeripheralConnectionIntervalRange, data)
    #     return True

    # type 0x1A
    # FIXME: untested for now due to definition error (only handling uint16 case, not uint24 or uint32)
    # elif isinstance(entry.payload, EIR_AdvertisingInterval):
    #     entry.show()
    #     advertising_interval = f"{entry.advertising_interval:04x}"
    #     length = 3 # 1 byte for opcode, 2 byte service interval
    #     #exit_on_len_mismatch(length, entry)
    #     data = {"length": length, "advertising_interval": advertising_interval}
    #     vprint(f"{device_bdaddr}: {adv_type} advertising_interval: 0x{advertising_interval}")
    #     BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_AdvertisingInterval, data)
    #     return True

    # type 0x20
    elif isinstance(entry.payload, EIR_ServiceData32BitUUID):
        #entry.show()
        length = entry.len # Not clear if Scapy is using the original ACID len or their calculated and corrected len
        UUID32_hex_str = f"{entry.svc_uuid:08x}"
        # Some devices don't include any actual service data (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of service data beyond the UUID32 before accessing .load
        if(length > 5): # 1 byte type + 4 byte UUID32
            service_data_hex_str = ''.join(format(byte, '02x') for byte in entry.load)
        else:
            service_data_hex_str = ""
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32": UUID32_hex_str, "service_data_hex_str": service_data_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} UUID32: {UUID32_hex_str}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ServiceData, data)
        return True

    # type 0x21
    elif isinstance(entry.payload, EIR_ServiceData128BitUUID):
        #entry.show()
        length = entry.len # Not clear if Scapy is using the original ACID len or their calculated and corrected len
        UUID128 = str(entry.svc_uuid)
        # Some devices don't include any actual service data (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of service data beyond the UUID128 before accessing .load
        if(length > 17): # 1 byte type + 16 byte UUID128
            service_data_hex_str = ''.join(format(byte, '02x') for byte in entry.load)
        else:
            service_data_hex_str = ""
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID128": UUID128, "service_data_hex_str": service_data_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} UUID128: {UUID128}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ServiceData, data)
        return True

    # # type 0x24
    # elif isinstance(entry.payload, EIR_URI):
    #     entry.show()
    #     entry.payload.show()
    #     URI = entry.payload.getlayer(EIR_URI)
    #     length = entry.len  # Not clear if Scapy is using the original ACID len or their calculated and corrected len
    #     try:
    #         scheme = URI.uri_scheme
    #         url_bytes = str(URI.uri_hier_part)
    #         print(f"Type of url_bytes: {type(url_bytes)}")
    #         URI_hex_str = ''.join(format(byte, '02x') for byte in url_bytes)
    #     except Exception as e:
    #         print(f"Exception occurred: {e}")
    #     data = {"length": length, "URI_hex_str": URI_hex_str}
    #     vprint(f"{device_bdaddr}: {adv_type}  scheme: {scheme} URI_hex_str: {URI_hex_str}")
    #     #BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_URI, data)
    #     return True


    # type 0xFF
    elif isinstance(entry.payload, EIR_Manufacturer_Specific_Data):
        #entry.show()
        #qprint(f"{device_bdaddr}")
        company_id_hex_str = f"{entry.company_id:04x}"
        length = entry.len # Not clear if Scapy is using the original ACID len or their calculated and corrected len
        msd_hex_str = ""
        # Some devices don't include any actual MSD (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of MSD beyond the company_id before accessing .load
        if(length > 3):
            msd_hex_str = ''.join(format(byte, '02x') for byte in entry.load)
        data = {"length": length, "company_id_hex_str": company_id_hex_str, "msd_hex_str": msd_hex_str}
        vprint(f"{device_bdaddr}: {adv_type} MSD: company_id = {company_id_hex_str}, data = {msd_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_MSD, data)
        return True

    return False


def export_AdvChannelData(packet, scapy_type, adv_type):
    ble_adv_fields = packet.getlayer(BTLE_ADV)
    bdaddr_random = ble_adv_fields.TxAdd

    # Access the BTLE_ADV layer
    btle_adv = packet.getlayer(scapy_type)
    device_bdaddr = btle_adv.AdvA

    data_exported = False
    for entry in btle_adv.data:
        if export_AdvData(device_bdaddr, bdaddr_random, adv_type, entry):
            data_exported = True

    if(data_exported or (adv_type == type_AdvChanPDU_SCAN_RSP and len(btle_adv.data) == 0)):
        return True
    else:
        return False

# A global map of access addresses for which we have seen a LL_START_ENC_REQ
# and for which therefore all subsequent packets will be encrypted garbage
# which we shouldn't export, even if they look valid.
# TODO: In the future handle LL_PAUSE_ENC_REQ to remove from this,
# TODO: but I don't know if I've ever seen that packet in any of my pcaps.
g_stop_exporting_encrypted_packets_by_AA = {}

def export_BTLE_CTRL(packet):
    global g_stop_exporting_encrypted_packets_by_AA

    btle_hdr = packet.getlayer(BTLE)
    access_address = btle_hdr.access_addr
    # Don't bother processing the packet if we've seen an LL_START_ENC_REQ in this connection already
    if(access_address in g_stop_exporting_encrypted_packets_by_AA.keys()):
        return True

    if access_address in g_access_address_to_connect_ind_obj:
        connect_ind_obj = g_access_address_to_connect_ind_obj[access_address]
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # Handle different LL Control packet types here
    # For example, LL_VERSION_IND
    ll_ctrl = packet.getlayer(BTLE_CTRL)
    if ll_ctrl.opcode == type_opcode_LL_TERMINATE_IND:
        try:
            data = ff_LL_TERMINATE_IND(
                direction=get_packet_direction(packet),
                error_code=ll_ctrl.code
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LL_TERMINATE_IND(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_TERMINATE_IND: {e}")
            return False
    if ll_ctrl.opcode == type_opcode_LL_START_ENC_REQ:
            # TODO: in the future add this to the DB for completeness
            g_stop_exporting_encrypted_packets_by_AA[access_address] = True
            return True
    elif ll_ctrl.opcode == type_opcode_LL_UNKNOWN_RSP:
        try:
            data = ff_LL_UNKNOWN_RSP(
                direction=get_packet_direction(packet),
                unknown_type=ll_ctrl.opcode
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LL_UNKNOWN_RSP(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_UNKNOWN_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_FEATURE_REQ:
        try:
            data = ff_LL_FEATURE_REQ(
                direction=get_packet_direction(packet),
                features=ll_ctrl.feature_set.value
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LL_FEATURE_REQ(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_FEATURE_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_VERSION_IND:
        try:
            data = ff_LL_VERSION_IND(
                direction=get_packet_direction(packet),
                version=ll_ctrl.version,
                company_id=ll_ctrl.company,
                subversion=ll_ctrl.subversion
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LL_VERSION_IND(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_VERSION_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_PERIPHERAL_FEATURE_REQ:
        try:
            data = ff_LL_PERIPHERAL_FEATURE_REQ(
                direction=get_packet_direction(packet),
                features=ll_ctrl.feature_set.value
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LL_PERIPHERAL_FEATURE_REQ(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_PERIPHERAL_FEATURE_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_FEATURE_RSP:
        try:
            data = ff_LL_FEATURE_RSP(
                direction=get_packet_direction(packet),
                features=ll_ctrl.feature_set.value
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LL_FEATURE_RSP(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_FEATURE_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_LENGTH_REQ:
        try:
            data = ff_LL_LENGTH_REQ(
                direction=get_packet_direction(packet),
                max_rx_octets=ll_ctrl.max_rx_bytes,
                max_rx_time=ll_ctrl.max_rx_time,
                max_tx_octets=ll_ctrl.max_tx_bytes,
                max_tx_time=ll_ctrl.max_tx_time
            )
        except Exception as e:
            print(f"Error processing LL_LENGTH_REQ: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LL_LENGTH_REQ(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_LENGTH_RSP:
        try:
            data = ff_LL_LENGTH_RSP(
                direction=get_packet_direction(packet),
                max_rx_octets=ll_ctrl.max_rx_bytes,
                max_rx_time=ll_ctrl.max_rx_time,
                max_tx_octets=ll_ctrl.max_tx_bytes,
                max_tx_time=ll_ctrl.max_tx_time
            )
        except Exception as e:
            print(f"Error processing LL_LENGTH_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LL_LENGTH_RSP(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PHY_REQ:
        try:
            data = ff_LL_PHY_REQ(
                direction=get_packet_direction(packet),
                tx_phys=ll_ctrl.tx_phys.value,
                rx_phys=ll_ctrl.rx_phys.value
            )
        except Exception as e:
            print(f"Error processing LL_PHY_REQ: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LL_PHY_REQ(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PHY_RSP:
        try:
            data = ff_LL_PHY_RSP(
                direction=get_packet_direction(packet),
                tx_phys=ll_ctrl.tx_phys.value,
                rx_phys=ll_ctrl.rx_phys.value
            )
        except Exception as e:
            print(f"Error processing LL_PHY_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LL_PHY_RSP(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PING_REQ:
        try:
            data = ff_LL_PING_REQ(
                direction=get_packet_direction(packet)
            )
        except Exception as e:
            print(f"Error processing LL_PING_REQ: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LL_PING_REQ(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PING_RSP:
        try:
            data = ff_LL_PING_RSP(
                direction=get_packet_direction(packet)
            )
        except Exception as e:
            print(f"Error processing LL_PING_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LL_PING_RSP(connect_ind_obj=connect_ind_obj, data=data)
        return True
    else:
        if(not TME.TME_glob.quiet_print):
            packet.show()

    return False


# It shouldn't be necessary to check the opcode if Scapy knows about the packet type layer
# But just doing it out of an abundance of caution
def get_ATT_data(packet, scapy_type, packet_type):
    att_hdr = packet.getlayer(ATT_Hdr)
    if(att_hdr == None):
        return None
    if(att_hdr.opcode != packet_type):
        return None
    if(packet.haslayer(scapy_type) == False):
        return None
    else:
        return packet.getlayer(scapy_type)

def export_ATT_Error_Response(connect_ind_obj, packet):
    att_data = get_ATT_data(packet, ATT_Error_Response, type_ATT_ERROR_RSP)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            request_opcode_in_error = att_data.request
            attribute_handle_in_error = att_data.handle
            error_code = att_data.ecode
        except AttributeError as e:
            print(f"Error accessing ATT_Error_Response fields: {e}")
            return False
        data = ff_ATT_ERROR_RSP(direction, request_opcode_in_error, attribute_handle_in_error, error_code)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False

def export_ATT_Exchange_MTU_Request(connect_ind_obj, packet):
    att_data = get_ATT_data(packet, ATT_Exchange_MTU_Request, type_ATT_EXCHANGE_MTU_REQ)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            data = ff_ATT_EXCHANGE_MTU_REQ(direction, att_data.mtu)
        except Exception as e:
            print(f"Error processing ATT_Exchange_MTU_Request: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Exchange_MTU_Response(connect_ind_obj, packet):
    #packet.show()
    att_data = get_ATT_data(packet, ATT_Exchange_MTU_Response, type_ATT_EXCHANGE_MTU_RSP)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            data = ff_ATT_EXCHANGE_MTU_RSP(direction, att_data.mtu)
        except Exception as e:
            print(f"Error processing ATT_Exchange_MTU_Response: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Read_Request(connect_ind_obj, packet):
    att_data = get_ATT_data(packet, ATT_Read_Request, type_ATT_READ_REQ)
    if(att_data != None):
        try:
            direction = get_packet_direction(packet)
            handle = att_data.gatt_handle
        except Exception as e:
            print(f"Error processing ATT_Read_Request: {e}")
            return False
        #handle = f"{att_data.gatt_handle:04x}" # FIXME: I'm not sure why this was accepted as valid output and the Schema validation says its fine...possible implicit conversion happening?
        data = ff_ATT_READ_REQ(direction, handle)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Read_Response(connect_ind_obj, packet):
    att_data = get_ATT_data(packet, ATT_Read_Response, type_ATT_READ_RSP)
    if(att_data != None):
        try:
            direction = get_packet_direction(packet)
            value_hex_str = ''.join(format(byte, '02x') for byte in att_data.value)
        except Exception as e:
            print(f"Error processing ATT_Read_Response: {e}")
            return False
        data = ff_ATT_READ_RSP(direction, value_hex_str)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Find_Information_Request(connect_ind_obj, packet):
    att_data = get_ATT_data(packet, ATT_Find_Information_Request, type_ATT_FIND_INFORMATION_REQ)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            start_handle = att_data.start
            end_handle = att_data.end
        except Exception as e:
            print(f"Error processing ATT_Find_Information_Request: {e}")
            return False
        data = ff_ATT_FIND_INFORMATION_REQ(direction, start_handle, end_handle)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Find_Information_Response(connect_ind_obj, packet):
    #packet.show()
    att_data = get_ATT_data(packet, ATT_Find_Information_Response, type_ATT_FIND_INFORMATION_RSP)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            format = att_data.format
            info_data_list = []

            if format == 1:
                # 2 byte handle, 2 byte UUID16
                for handle_obj in att_data.handles:
                    list_obj = ff_ATT_FIND_INFORMATION_RSP_information_data(
                                    handle=handle_obj.handle,
                                    UUID=f"{handle_obj.value:04x}"
                                )
                    info_data_list.append(list_obj)
            elif format == 2:
                # 2 byte handle, 16 byte UUID128
                for handle_obj in att_data.handles:
                    list_obj = ff_ATT_FIND_INFORMATION_RSP_information_data(
                                    handle=handle_obj.handle,
                                    UUID=str(handle_obj.value)
                                )
                    info_data_list.append(list_obj)
        except Exception as e:
            print(f"Error processing ATT_Find_Information_Response: {e}")
            return False
        if (format != 1 and format != 2):
            print("Unexpected format in Find Information Response. Can't parse further.")
            return False

        data = ff_ATT_FIND_INFORMATION_RSP(direction, format, info_data_list)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)

        # Then also insert this information into the ATT_handle_enumeration
        for entry in info_data_list:
            data = ff_ATT_handle_entry(entry["handle"], entry["UUID"])
            BTIDES_export_ATT_handle(connect_ind_obj=connect_ind_obj, data=data)

        return True

    return False


def export_ATT_Read_By_Group_Type_Request(connect_ind_obj, packet):
    global g_last_ATT_group_type_requested
    att_data = get_ATT_data(packet, ATT_Read_By_Group_Type_Request, type_ATT_READ_BY_GROUP_TYPE_REQ)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            start_handle = att_data.start
            end_handle = att_data.end
            group_type = f"{att_data.uuid:04x}"
            g_last_ATT_group_type_requested = group_type
        except Exception as e:
            print(f"Error processing ATT_Read_By_Group_Type_Request: {e}")
            return False
        data = ff_ATT_READ_BY_GROUP_TYPE_REQ(direction, start_handle, end_handle, group_type)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Read_By_Group_Type_Response(connect_ind_obj, packet):
    # packet.show()
    att_data = get_ATT_data(packet, ATT_Read_By_Group_Type_Response, type_ATT_READ_BY_GROUP_TYPE_RSP)
    if att_data is not None:
        try:
            direction = get_packet_direction(packet)
            attribute_data_list = []
            if(att_data.length == 6):
                # 2 byte start handle, 2 byte end handle, 2 byte UUID16
                data_len = len(att_data.data)
                for i in range(0, data_len, 6):
                    if i + 6 > data_len:
                        qprint("Not enough data left to process a 6-byte attribute data entry.")
                        break
                    list_obj = ff_ATT_READ_BY_GROUP_TYPE_RSP_attribute_data_list(
                                    attribute_handle=int.from_bytes(att_data.data[i:i+2], byteorder='little'),
                                    end_group_handle=int.from_bytes(att_data.data[i+2:i+4], byteorder='little'),
                                    UUID=f"{int.from_bytes(att_data.data[i+4:i+6], byteorder='little'):04x}"
                                    )
                    attribute_data_list.append(list_obj)
            elif(att_data.length == 20):
                # 2 byte start handle, 2 byte end handle, 16 byte UUID128
                data_len = len(att_data.data)
                for i in range(0, data_len, 20):
                    if i + 20 > data_len:
                        qprint("Not enough data left to process a 20-byte attribute data entry.")
                        break
                    list_obj = ff_ATT_READ_BY_GROUP_TYPE_RSP_attribute_data_list(
                                attribute_handle=int.from_bytes(att_data.data[i:i+2], byteorder='little'),
                                end_group_handle=int.from_bytes(att_data.data[i+2:i+4], byteorder='little'),
                                UUID=f"{int.from_bytes(att_data.data[i+4:i+20], byteorder='little'):032x}"
                                )
                    attribute_data_list.append(list_obj)
        except Exception as e:
            print(f"Error processing ATT_Read_By_Group_Type_Response: {e}")
            return False
        if (att_data.length != 6 and att_data.length != 20):
            print("Unexpected length in Read By Group Type Response. Can't parse further.")
            return False
        #attribute_data_list = ''.join(format(byte, '02x') for byte in att_data.data)
        data = ff_ATT_READ_BY_GROUP_TYPE_RSP(direction, att_data.length, attribute_data_list)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)

        # Insert this information as GATTArray information as well
        for entry in attribute_data_list:
            data = ff_GATT_Service({"utype": g_last_ATT_group_type_requested,
                                    "begin_handle": entry["attribute_handle"],
                                    "end_handle": entry["end_group_handle"],
                                    "UUID": entry["UUID"]})
#            BTIDES_export_GATT_Service(connect_ind_obj["peripheral_bdaddr"], connect_ind_obj["peripheral_bdaddr_rand"], data)
            BTIDES_export_GATT_Service(connect_ind_obj=connect_ind_obj, data=data)

        return True
    return False

def export_to_ATTArray(packet):
    ble_fields = packet.getlayer(BTLE)
    access_address = ble_fields.access_addr

    if access_address in g_access_address_to_connect_ind_obj:
        connect_ind_obj = g_access_address_to_connect_ind_obj[access_address]
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # The opcodes are mutually exclusive, so if one returns true, we're done
    # To convert ATT data into a GATT hierarchy requires us to statefully
    # remember information between packets (i.e. which UUID corresponds to which handle)
    if(export_ATT_Error_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Exchange_MTU_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Exchange_MTU_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Find_Information_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Find_Information_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_By_Group_Type_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_By_Group_Type_Response(connect_ind_obj, packet)):
        return True

    # TODO: handle ALL opcodes


def export_CONNECT_IND(packet):
    global BTIDES_JSON
    global g_access_address_to_connect_ind_obj

    #packet.show()

    # Store the BDADDRs involved in the connection into a dictionary, queryable by access address
    # This dictionary will need to be used by all subsequent packets within the connection to figure out
    # which bdaddr to associate their data with
    ble_fields = packet.getlayer(BTLE)
    ble_adv_fields = packet.getlayer(BTLE_ADV)
    central_bdaddr_rand = ble_adv_fields.TxAdd
    peripheral_bdaddr_rand = ble_adv_fields.RxAdd
    connect_fields = packet.getlayer(BTLE_CONNECT_REQ)
    central_bdaddr = connect_fields.InitA
    peripheral_bdaddr = connect_fields.AdvA
    # The following 3 multi-byte fields are in the incorrect byte order in Scapy (according to looking at their values in Wireshark, which I trust more)
    access_address = int.from_bytes(connect_fields.AA.to_bytes(4, byteorder='little'), byteorder='big')
    channel_map_hex_str = ''.join(f'{byte:02x}' for byte in connect_fields.chM.to_bytes(5, byteorder='little'))
    crc_init_hex_str = ''.join(f'{byte:02x}' for byte in connect_fields.crc_init.to_bytes(3, byteorder='little'))
    connect_ind_obj = ff_CONNECT_IND(
        central_bdaddr=central_bdaddr,
        central_bdaddr_rand=central_bdaddr_rand,
        peripheral_bdaddr=peripheral_bdaddr,
        peripheral_bdaddr_rand=peripheral_bdaddr_rand,
        access_address=access_address,
        crc_init_hex_str=crc_init_hex_str,
        win_size=connect_fields.win_size,
        win_offset=connect_fields.win_offset,
        interval=connect_fields.interval,
        latency=connect_fields.latency,
        timeout=connect_fields.timeout,
        channel_map_hex_str=channel_map_hex_str,
        hop=connect_fields.hop,
        SCA=connect_fields.SCA
    )
    if_verbose_insert_std_optional_fields(connect_ind_obj, packet)
    # Store the CONNECT_IND obj into g_access_address_to_bdaddrs for later use in lookups
    g_access_address_to_connect_ind_obj[access_address] = connect_ind_obj

    generic_DualBDADDR_insertion_into_BTIDES_zeroth_level(connect_ind_obj)

    return True


def read_pcap(file_path):
    try:
        # Read all the packets in to memory, so that we know how many total there are, and then can give progress updates
        with PcapReader(file_path) as pcap_reader:
            packets = [packet for packet in pcap_reader]

        total_packets = len(packets)

        for i, packet in enumerate(packets, start=0):
            # Print progress every 10%
            if total_packets > 0 and i % max(1, total_packets // 100) == 0:
                qprint(f"Processed {i} out of {total_packets} packets ({(i / total_packets) * 100:.0f}%)")

            # Confirm packet is BTLE
            if packet.haslayer(BTLE):
                btle_hdr = packet.getlayer(BTLE)
                if(btle_hdr.access_addr != 0x8e89bed6 and btle_hdr.len == 0):
                    #qprint("Found empty non-advertisement packet, continuing")
                    continue

                if(btle_hdr.access_addr in g_stop_exporting_encrypted_packets_by_AA.keys()):
                    # Don't bother processing the packet if we've seen an LL_START_ENC_REQ in this connection already
                    continue

                # If a packet matches on any export function, move on to the next packet

                # Connection requests
                if packet.haslayer(BTLE_CONNECT_REQ): # FIXME: Scapy is wrong here, it should be CONNECT_*IND*
                    if(export_CONNECT_IND(packet)): continue

                # Advertisement channel packets
                if packet.haslayer(BTLE_ADV_IND):
                    # It's rare, but some things advertise but then don't include any AdvData...
                    btle_adv = packet.getlayer(BTLE_ADV_IND)
                    if(len(btle_adv.data) == 0):
                        continue
                    if(export_AdvChannelData(packet, BTLE_ADV_IND, type_AdvChanPDU_ADV_IND)): continue
                if packet.haslayer(BTLE_ADV_NONCONN_IND):
                    if(export_AdvChannelData(packet, BTLE_ADV_NONCONN_IND, type_AdvChanPDU_ADV_NONCONN_IND)): continue
                if packet.haslayer(BTLE_SCAN_RSP):
                    # Special case SCAN_RSP because Apple devices like to send back SCAN_RSP with no data in it,
                    # which causes it to return false and then continue to be processed above
                    btle_adv = packet.getlayer(BTLE_SCAN_RSP)
                    if(len(btle_adv.data) == 0): continue
                    if(export_AdvChannelData(packet, BTLE_SCAN_RSP, type_AdvChanPDU_SCAN_RSP)): continue
                if packet.haslayer(BTLE_ADV_SCAN_IND):
                    if(export_AdvChannelData(packet, BTLE_ADV_SCAN_IND, type_AdvChanPDU_ADV_SCAN_IND)): continue
                if packet.haslayer(BTLE_SCAN_REQ) or packet.haslayer(BTLE_ADV_DIRECT_IND):
                    # Ignore for now. I don't particularly care to import that information for now (though TODO later it should be in the interest of completeness)
                    continue
                if packet.haslayer(BTLE_ADV):
                    btle_adv = packet.getlayer(BTLE_ADV)
                    if(btle_adv.PDU_type == type_AdvChanPDU_ADV_DIRECT_IND): # for malformed packets that Scapy couldn't add a BTLE_ADV_DIRECT_IND layer to...
                        # Ignore for now. I don't particularly care to import that information for now (though TODO later it should be in the interest of completeness)
                        qprint("Found a scan request")
                        continue
                    qprint(packet.layers())
                    qprint("")

                # LL Control packets
                if packet.haslayer(BTLE_CTRL):
                    if(export_BTLE_CTRL(packet)): continue

                # ATT packets
                if packet.haslayer(ATT_Hdr):
                    if(export_to_ATTArray(packet)): continue
                # TODO: export other packet types like LL or L2CAP or ATT
                else:
                    qprint("Unknown or unparsable packet type. Skipped")
                    if(not TME.TME_glob.quiet_print):
                        packet.show()

        return
    except Exception as e:
        print(f"Error reading pcap file: {e}")


def main():
    global verbose_print, verbose_BTIDES
    parser = argparse.ArgumentParser(description='pcap file input arguments')
    parser.add_argument('--input', type=str, required=True, help='Input file name for pcap file.')

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

    in_pcap_filename = args.input
    out_BTIDES_filename = args.output
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES

    qprint("Reading all packets from pcap into memory. (This can take a while for large pcaps. Assume a total time of 1 second per 100 packets.)")
    read_pcap(in_pcap_filename)

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