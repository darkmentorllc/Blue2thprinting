########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# Activate venv before any other imports
from handle_venv import activate_venv
activate_venv()
from scapy.layers.bluetooth4LE import *
from scapy.layers.bluetooth import *
from scapy.all import *

from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

from TME.TME_helpers import qprint, vprint
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
import TME.TME_glob
from TME.TME_BTIDES_base import insert_std_optional_fields
# Advertisement Channel
from TME.TME_BTIDES_AdvData import BTIDES_export_AdvData
from TME.TME_AdvChan import *
# Feature response
from TME.TME_BTIDES_LL import ff_LL_FEATURE_RSP, BTIDES_export_LL_FEATURE_RSP
# HCI (for Remote Name Request Complete)
from TME.TME_BTIDES_HCI import *
# ATT
from TME.TME_BTIDES_ATT import *
# EIR
from TME.TME_BTIDES_EIR import *
# LMP
from TME.TME_BTIDES_LMP import *

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

    if(packet and packet.haslayer(BTLE_RF)):
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

######################################################################
# AdvData SECTION
######################################################################

# This is the main function which converts from Scapy data format to BTIDES
def export_AdvData(bdaddr, bdaddr_random, adv_type, entry):
    #entry.show()

    # type 1
    if isinstance(entry.payload, EIR_Flags):
        flags_hex_str = scapy_flags_to_hex_str(entry)
        length = 2 # 1 bytes for opcode + 1 byte for flags
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "flags_hex_str": flags_hex_str}
        vprint(f"{bdaddr}: {adv_type} Flags: {flags_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_Flags, data)
        return True

    # type 2
    elif isinstance(entry.payload, EIR_IncompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        vprint(f"{bdaddr}: {adv_type} Incomplete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListIncomplete, data)
        return True

    # type 3
    elif isinstance(entry.payload, EIR_CompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        vprint(f"{bdaddr}: {adv_type} Complete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListComplete, data)
        return True

    # type 4
    elif isinstance(entry.payload, EIR_IncompleteList32BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID32List = [f"{uuid:08x}" for uuid in uuid_list]
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32List": UUID32List}
        vprint(f"{bdaddr}: {adv_type} Incomplete UUID32 list: {','.join(UUID32List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ListIncomplete, data)
        return True

    # type 5
    elif isinstance(entry.payload, EIR_CompleteList32BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID32List = [f"{uuid:08x}" for uuid in uuid_list]
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32List": UUID32List}
        vprint(f"{bdaddr}: {adv_type} Complete UUID32 list: {','.join(UUID32List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ListComplete, data)
        return True

    # type 6
    elif isinstance(entry.payload, EIR_IncompleteList128BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID128List = [str(uuid) for uuid in uuid_list]
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID128List": UUID128List}
        vprint(f"{bdaddr}: {adv_type} Incomplete UUID128 list: {','.join(UUID128List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ListIncomplete, data)
        return True

    # type 7
    elif isinstance(entry.payload, EIR_CompleteList128BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID128List = [str(uuid) for uuid in uuid_list]
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID128List": UUID128List}
        vprint(f"{bdaddr}: {adv_type} Complete UUID128 list: {','.join(UUID128List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ListComplete, data)
        return True

    # type 8
    elif isinstance(entry.payload, EIR_ShortenedLocalName):
        local_name = entry.local_name
        utf8_name = local_name.decode('utf-8', 'ignore')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_IncompleteName, data)
        vprint(f"{bdaddr}: {adv_type} Incomplete Local Name: {utf8_name}")
        return True

    # type 9
    elif isinstance(entry.payload, EIR_CompleteLocalName):
        local_name = entry.local_name
        utf8_name = local_name.decode('utf-8', 'ignore')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        vprint(f"{bdaddr}: {adv_type} Complete Local Name: {utf8_name}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_CompleteName, data)
        return True

    # type 0x0A
    elif isinstance(entry.payload, EIR_TX_Power_Level):
        device_tx_power = entry.level
        length = 2 # 1 byte for opcode, 1 byte power level
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "tx_power": device_tx_power}
        vprint(f"{bdaddr}: {adv_type} TxPower level: {device_tx_power}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_TxPower, data)
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
        vprint(f"{bdaddr}: {adv_type} Class of Device: {CoD_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_ClassOfDevice, data)
        return True

    # type 0x10
    # I don't think this can actually appear in BLE as opposed to EIR...so I'm not sure if this will get any testing...
    elif isinstance(entry.payload, EIR_Device_ID):
        length = 9 # 1 byte for opcode + 2 bytes * 4 fields
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "vendor_id_source": entry.vendor_id_source, "vendor_id": entry.vendor_id, "product_id": entry.product_id, "version": entry.version}
        vprint(f"{bdaddr}: {adv_type} Device ID: {data}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_DeviceID, data)
        return True

    # type 0x12
    elif isinstance(entry.payload, EIR_PeripheralConnectionIntervalRange):
        #entry.show()
        conn_interval_min = entry.conn_interval_min
        conn_interval_max = entry.conn_interval_max
        length = 5 # 1 byte for opcode, 2*2 byte parameters
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "conn_interval_min": conn_interval_min, "conn_interval_max": conn_interval_max}
        vprint(f"{bdaddr}: {adv_type} conn_interval_min: {conn_interval_min}, conn_interval_max: {conn_interval_max}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_PeripheralConnectionIntervalRange, data)
        return True

    # type 0x14
    elif isinstance(entry.payload, EIR_ServiceSolicitation16BitUUID):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        vprint(f"{bdaddr}: {adv_type} Service Solicitiation UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListServiceSolicitation, data)
        return True

    # type 0x15
    elif isinstance(entry.payload, EIR_ServiceSolicitation128BitUUID):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID128List = [str(uuid) for uuid in uuid_list]
        length = 1 + 16 * len(UUID128List) # 1 byte for opcode, 16 bytes for each UUID128
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID128List": UUID128List}
        vprint(f"{bdaddr}: {adv_type} Service Solicitiation UUID128 list: {','.join(UUID128List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ListServiceSolicitation, data)
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
        vprint(f"{bdaddr}: {adv_type} UUID16: {UUID16_hex_str}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ServiceData, data)
        return True

    # type 0x17
    elif isinstance(entry.payload, EIR_PublicTargetAddress):
        #entry.show()
        public_bdaddr = entry.bd_addr
        length = 7 # 1 byte for opcode, 6 bytes for BDADDR
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "public_bdaddr": public_bdaddr}
        vprint(f"{bdaddr}: {adv_type} public_bdaddr: {public_bdaddr}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_PublicTargetAddress, data)
        return True

    # type 0x18
    elif isinstance(entry.payload, EIR_RandomTargetAddress):
        #entry.show()
        random_bdaddr = entry.bd_addr
        length = 7 # 1 byte for opcode, 6 bytes for BDADDR
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "random_bdaddr": bdaddr}
        vprint(f"{bdaddr}: {adv_type} random_bdaddr: {random_bdaddr}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_RandomTargetAddress, data)
        return True

    # type 0x19
    elif isinstance(entry.payload, EIR_Appearance):
        #entry.show()
        appearance = entry.category << 6 | entry.subcategory
        appearance_hex_str = f"{appearance:04x}"
        length = 3 # 1 byte for opcode, 2 bytes for appearance
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "appearance_hex_str": appearance_hex_str}
        vprint(f"{bdaddr}: {adv_type} appearance_hex_str: {appearance_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_Appearance, data)
        return True

    # type 0x1A
    # FIXME: not clear how to define for all of the uint16, uint24, and uint32 cases in Scapy
    # elif isinstance(entry.payload, EIR_AdvertisingInterval):
    #     entry.show()
    #     advertising_interval = f"{entry.advertising_interval:04x}"
    #     length = 3 # 1 byte for opcode, 2 byte service interval
    #     #exit_on_len_mismatch(length, entry)
    #     data = {"length": length, "advertising_interval": advertising_interval}
    #     vprint(f"{bdaddr}: {adv_type} advertising_interval: 0x{advertising_interval}")
    #     BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_AdvertisingInterval, data)
    #     return True

    # type 0x1B
    elif isinstance(entry.payload, EIR_LEBluetoothDeviceAddress):
        #entry.show()
        le_bdaddr = entry.bd_addr
        bdaddr_type = entry.addr_type
        length = 8 # 1 byte for opcode,1 byte for type, 6 bytes for BDADDR
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "bdaddr_type": bdaddr_type, "le_bdaddr": le_bdaddr}
        vprint(f"{bdaddr}: {adv_type}, bdaddr_type: {bdaddr_type}, le_bdaddr: {le_bdaddr}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_LE_BDADDR, data)
        return True

    # type 0x1C - According to the spec this should only occur in OOB data, but we've seen devices using it for OTA data
    elif isinstance(entry.payload, EIR_LERole):
        #entry.show()
        role = entry.role
        length = 2 # 1 byte for opcode, 1 byte for role
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "role": role}
        vprint(f"{bdaddr}: {adv_type}, role: {role}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_LE_Role, data)
        return True

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
        vprint(f"{bdaddr}: {adv_type} UUID32: {UUID32_hex_str}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ServiceData, data)
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
        vprint(f"{bdaddr}: {adv_type} UUID128: {UUID128}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ServiceData, data)
        return True

    # type 0x24
    elif isinstance(entry.payload, EIR_URI):
        #entry.show()
        URI = entry.payload.getlayer(EIR_URI)
        url_bytes = entry.uri_hier_part
        uri_hex_str = ''.join(format(byte, '02x') for byte in url_bytes)
        uri_hex_str = f"{entry.scheme:02x}" + uri_hex_str
        length = 1 + int(len(uri_hex_str) / 2) # 1 byte opcode + half the size due to it being hex_str with 2 characters per byte
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "uri_hex_str": uri_hex_str}
        vprint(f"{bdaddr}: {adv_type}  scheme: {entry.scheme} uri_hex_str: {uri_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_URI, data)
        return True

    # type 0x30
    elif isinstance(entry.payload, EIR_BroadcastName):
        broadcast_name = entry.broadcast_name
        utf8_name = broadcast_name.decode('utf-8', 'ignore')
        name_hex_str = ''.join(format(byte, '02x') for byte in broadcast_name)
        length = int(1 + len(broadcast_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        vprint(f"{bdaddr}: {adv_type} Broadcast Name: {utf8_name}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_BroadcastName, data)
        return True

    # type 0x3d
    elif isinstance(entry.payload, EIR_3DInformation):
        byte1 = (int(entry.factory_test_mode) << 7) | \
                (int(entry.send_battery_level_on_startup) << 2) | \
                (int(entry.battery_level_reporting) << 1) | \
                int(entry.association_notification)
        path_loss = entry.path_loss_threshold
        length = 3 # 1 bytes for opcode + 2 bytes
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "byte1": byte1, "path_loss": path_loss}
        vprint(f"{bdaddr}: {adv_type} 3D Info Byte1: {byte1}, Path Loss Threshold: {path_loss}dB")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_3DInfoData, data)
        return True

    # type 0xFF
    elif isinstance(entry.payload, EIR_Manufacturer_Specific_Data):
        #entry.show()
        #qprint(f"{bdaddr}")
        company_id_hex_str = f"{entry.company_id:04x}"
        length = entry.len # Not clear if Scapy is using the original ACID len or their calculated and corrected len
        msd_hex_str = ""
        # Some devices don't include any actual MSD (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of MSD beyond the company_id before accessing .load
        if(length > 3):
            msd_hex_str = ''.join(format(byte, '02x') for byte in entry.load)
        data = {"length": length, "company_id_hex_str": company_id_hex_str, "msd_hex_str": msd_hex_str}
        vprint(f"{bdaddr}: {adv_type} MSD: company_id = {company_id_hex_str}, data = {msd_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_MSD, data)
        return True

    return False


######################################################################
# ATT SECTION
######################################################################

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


def export_ATT_Error_Response(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Error_Response, type_ATT_ERROR_RSP)
    if att_data is not None:
        try:
            if(direction == None):
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


def export_ATT_Exchange_MTU_Request(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Exchange_MTU_Request, type_ATT_EXCHANGE_MTU_REQ)
    if att_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            data = ff_ATT_EXCHANGE_MTU_REQ(direction, att_data.mtu)
        except Exception as e:
            print(f"Error processing ATT_Exchange_MTU_Request: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Exchange_MTU_Response(connect_ind_obj, packet, direction=None):
    #packet.show()
    att_data = get_ATT_data(packet, ATT_Exchange_MTU_Response, type_ATT_EXCHANGE_MTU_RSP)
    if att_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            data = ff_ATT_EXCHANGE_MTU_RSP(direction, att_data.mtu)
        except Exception as e:
            print(f"Error processing ATT_Exchange_MTU_Response: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_ATT_Read_Request(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Read_Request, type_ATT_READ_REQ)
    if(att_data != None):
        try:
            if(direction == None):
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


def export_ATT_Read_Response(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Read_Response, type_ATT_READ_RSP)
    if(att_data != None):
        try:
            if(direction == None):
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


def export_ATT_Find_Information_Request(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Find_Information_Request, type_ATT_FIND_INFORMATION_REQ)
    if att_data is not None:
        try:
            if(direction == None):
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


def export_ATT_Find_Information_Response(connect_ind_obj, packet, direction=None):
    #packet.show()
    att_data = get_ATT_data(packet, ATT_Find_Information_Response, type_ATT_FIND_INFORMATION_RSP)
    if att_data is not None:
        try:
            if(direction == None):
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


def export_ATT_Read_By_Group_Type_Request(connect_ind_obj, packet, direction=None):
    global g_last_ATT_group_type_requested
    att_data = get_ATT_data(packet, ATT_Read_By_Group_Type_Request, type_ATT_READ_BY_GROUP_TYPE_REQ)
    if att_data is not None:
        try:
            if(direction == None):
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


def export_ATT_Read_By_Group_Type_Response(connect_ind_obj, packet, direction=None):
    # packet.show()
    att_data = get_ATT_data(packet, ATT_Read_By_Group_Type_Response, type_ATT_READ_BY_GROUP_TYPE_RSP)
    if att_data is not None:
        try:
            if(direction == None):
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
            BTIDES_export_GATT_Service(connect_ind_obj=connect_ind_obj, data=data)

        return True
    return False

######################################################################
# HCI SECTION
######################################################################

def export_Remote_Name_Request_Complete(bdaddr, name):
    BTIDES_export_HCI_Name_Response(bdaddr, name)


######################################################################
# FEATURES (via HCI) SECTION
######################################################################

# This is the main function which converts from Scapy data format to BTIDES
def export_LE_Features(bdaddr, bdaddr_random, in_data):
    try:
        data = ff_LL_FEATURE_RSP(
            direction=in_data['direction'],
            features=in_data['features']
        )
        if_verbose_insert_std_optional_fields(data, None)
        BTIDES_export_LL_FEATURE_RSP(bdaddr=bdaddr, random=bdaddr_random, data=data)
        return True
    except Exception as e:
        print(f"Error processing LL_FEATURE_RSP: {e}")
        return False

def export_LMP_Features(bdaddr, in_data):
    try:
        BTIDES_export_LMP_FEATURES_RES(bdaddr, in_data['features'])
        return True
    except Exception as e:
        print(f"Error processing LMP_FEATURES_RES: {e}")
        return False

def export_LMP_Features_Ext(bdaddr, in_data):
    try:
        BTIDES_export_LMP_FEATURES_RES_EXT(bdaddr, in_data['page'], in_data['max_page'], in_data['features'])
        return True
    except Exception as e:
        print(f"Error processing LMP_FEATURES_RES_EXT: {e}")
        return False

######################################################################
# EIR SECTION
######################################################################

def export_Page_Scan_Repetition_Mode(bdaddr, page_scan_repetition_mode_int):
    BTIDES_export_Page_Scan_Repetition_Mode(bdaddr, page_scan_repetition_mode_int)

def export_Class_of_Device(bdaddr, CoD_hex_str):
    BTIDES_export_Class_of_Device(bdaddr, CoD_hex_str)
