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
from TME.TME_BTIDES_LLCP import ff_LL_FEATURE_RSP, BTIDES_export_LLArray_entry
# HCI (for Remote Name Request Complete)
from TME.TME_BTIDES_HCI import *
# L2CAP
from TME.TME_BTIDES_L2CAP import *
# SDP
from TME.TME_BTIDES_SDP import *
# ATT
from TME.TME_BTIDES_ATT import *
# SMP
from TME.TME_BTIDES_SMP import *
#### Classic-specific
# EIR
from TME.TME_BTIDES_EIR import *
# LMP
from TME.TME_BTIDES_LMP import *

# We need to keep state between ATT_READ_BY_GROUP_TYPE_REQ and ATT_READ_BY_GROUP_TYPE_RSP
# in order to insert GATT service information into the BTIDES JSON
g_last_ATT_group_type_requested = "2800"

# We need to keep state between ATT_READ_REQ and ATT_READ_RSP
# in order to know if a ATT_READ_RSP is for a handle that
# corresponds to a GATT characteristic
g_last_read_handle = 0

# We need to keep state about the last characteristic we've seen,
# in order to ensure characteristic descriptors are nested underneath it
g_last_seen_characteristic_handle = 0

# Keep state about the handle to UUID mappings with a per-BDADDR dictionary
# i.e.
g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data = {}

# Keep state about which (source CID) combos currently map to an SDP channel
# so that we can identify it in incoming L2CAP packets
g_CIDs_used_for_SDP = {}

# What type was requested by the last ATT_READ_BY_TYPE_REQ
g_last_requested_uuid_type = None

# Saved text for printing fields
#    for field in btle_adv.fields_desc:
#        print(f"{field.name}: {field.__class__.__name__}")

############################
# Helper "factory functions"
############################

# Note: as a temporary measure while doing bulk imports, make this return False instead,
# so that invalid data can just be bypassed and the overall process can continue
def exit_on_len_mismatch(length, entry):
    if(length != entry.len):
        print("Interesting length mismatch. Check if it's a bug or if it's a malformed packet.")
        entry.show()
        #exit(-1)
        return False
    return True


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

# def bytes_to_hex_str(bytes):
#     return ''.join(format(byte, '02x') for byte in bytes)

# def str_to_hex_str(str):
#     return ''.join(format(byte, '02x') for byte in str.encode('utf-8'))

# def str_to_bytes(str):
#     return str.encode('utf-8', 'ignore')

# def bytes_reversed_to_hex_str(bytes):
#     return ''.join(format(byte, '02x') for byte in reversed(bytes))

# def bytes_to_utf8(hex_str):
#     return hex_str.decode('utf-8', 'ignore')

# def hex_str_to_utf8(hex_str):
#     bytes_object = bytes.fromhex(hex_str)
#     return bytes_to_utf8(bytes_object)

# def hex_str_to_bytes(hex_str):
#     bytes_object = bytes.fromhex(hex_str)
#     return bytes_object

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
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "flags_hex_str": flags_hex_str}
        vprint(f"{bdaddr}: {adv_type} Flags: {flags_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_Flags, data)
        return True

    # type 2
    elif isinstance(entry.payload, EIR_IncompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "UUID16List": UUID16List}
        vprint(f"{bdaddr}: {adv_type} Incomplete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListIncomplete, data)
        return True

    # type 3
    elif isinstance(entry.payload, EIR_CompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "UUID128List": UUID128List}
        vprint(f"{bdaddr}: {adv_type} Complete UUID128 list: {','.join(UUID128List)}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ListComplete, data)
        return True

    # type 8
    elif isinstance(entry.payload, EIR_ShortenedLocalName):
        local_name = entry.local_name
        utf8_name = bytes_to_utf8(local_name)
        name_hex_str = bytes_to_hex_str(local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_IncompleteName, data)
        vprint(f"{bdaddr}: {adv_type} Incomplete Local Name: {utf8_name}")
        return True

    # type 9
    elif isinstance(entry.payload, EIR_CompleteLocalName):
        local_name = entry.local_name
        utf8_name = bytes_to_utf8(local_name)
        name_hex_str = bytes_to_hex_str(local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        vprint(f"{bdaddr}: {adv_type} Complete Local Name: {utf8_name}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_CompleteName, data)
        return True

    # type 0x0A
    elif isinstance(entry.payload, EIR_TX_Power_Level):
        device_tx_power = entry.level
        length = 2 # 1 byte for opcode, 1 byte power level
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "CoD_hex_str": CoD_hex_str}
        vprint(f"{bdaddr}: {adv_type} Class of Device: {CoD_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_ClassOfDevice, data)
        return True

    # type 0x10
    # I don't think this can actually appear in BLE as opposed to EIR...so I'm not sure if this will get any testing...
    elif isinstance(entry.payload, EIR_Device_ID):
        length = 9 # 1 byte for opcode + 2 bytes * 4 fields
        if(not exit_on_len_mismatch(length, entry)):
            return False
        if(entry.vendor_id_source != 1 and entry.vendor_id_source != 2):
            # This entry will fail schema validation and is *probably* a corrupt packet, so discard it for now
            # TODO: should we make schema validation less strict so that we can capture corrupt packets?
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
            try:
                service_data_hex_str = bytes_to_hex_str(entry.load)
            except Exception as e:
                vprint(f"Service data is missing.")
                service_data_hex_str = ""
                pass
        else:
            service_data_hex_str = ""
        data = {"length": length, "UUID16": UUID16_hex_str, "service_data_hex_str": service_data_hex_str}
        vprint(f"{bdaddr}: {adv_type} UUID16: {UUID16_hex_str}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ServiceData, data)
        return True

    # type 0x17
    elif isinstance(entry.payload, EIR_PublicTargetAddress):
        #entry.show()
        public_bdaddr = entry.bd_addr
        length = 7 # 1 byte for opcode, 6 bytes for BDADDR
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "public_bdaddr": public_bdaddr}
        vprint(f"{bdaddr}: {adv_type} public_bdaddr: {public_bdaddr}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_PublicTargetAddress, data)
        return True

    # type 0x18
    elif isinstance(entry.payload, EIR_RandomTargetAddress):
        #entry.show()
        random_bdaddr = entry.bd_addr
        length = 7 # 1 byte for opcode, 6 bytes for BDADDR
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "bdaddr_type": bdaddr_type, "le_bdaddr": le_bdaddr}
        vprint(f"{bdaddr}: {adv_type}, bdaddr_type: {bdaddr_type}, le_bdaddr: {le_bdaddr}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_LE_BDADDR, data)
        return True

    # type 0x1C - According to the spec this should only occur in OOB data, but we've seen devices using it for OTA data
    elif isinstance(entry.payload, EIR_LERole):
        #entry.show()
        role = entry.role
        length = 2 # 1 byte for opcode, 1 byte for role
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
            try:
                service_data_hex_str = bytes_to_hex_str(entry.load)
            except Exception as e:
                vprint(f"Service data is missing.")
                service_data_hex_str = ""
                pass
        else:
            service_data_hex_str = ""
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
            try:
                service_data_hex_str = bytes_to_hex_str(entry.load)
            except Exception as e:
                vprint(f"Service data is missing.")
                service_data_hex_str = ""
                pass
        else:
            service_data_hex_str = ""
        data = {"length": length, "UUID128": UUID128, "service_data_hex_str": service_data_hex_str}
        vprint(f"{bdaddr}: {adv_type} UUID128: {UUID128}, service_data_hex_str: {service_data_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_UUID128ServiceData, data)
        return True

    # type 0x24
    elif isinstance(entry.payload, EIR_URI):
        #entry.show()
        URI = entry.payload.getlayer(EIR_URI)
        url_bytes = entry.uri_hier_part
        uri_hex_str = bytes_to_hex_str(url_bytes)
        uri_hex_str = f"{entry.scheme:02x}" + uri_hex_str
        length = 1 + int(len(uri_hex_str) / 2) # 1 byte opcode + half the size due to it being hex_str with 2 characters per byte
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "uri_hex_str": uri_hex_str}
        vprint(f"{bdaddr}: {adv_type}  scheme: {entry.scheme} uri_hex_str: {uri_hex_str}")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_URI, data)
        return True

    # type 0x30
    elif isinstance(entry.payload, EIR_BroadcastName):
        broadcast_name = entry.broadcast_name
        utf8_name = bytes_to_utf8(broadcast_name)
        name_hex_str = bytes_to_hex_str(broadcast_name)
        length = int(1 + len(broadcast_name)) # 1 bytes for opcode + length of the string
        if(not exit_on_len_mismatch(length, entry)):
            return False
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
        if(not exit_on_len_mismatch(length, entry)):
            return False
        data = {"length": length, "byte1": byte1, "path_loss": path_loss}
        vprint(f"{bdaddr}: {adv_type} 3D Info Byte1: {byte1}, Path Loss Threshold: {path_loss}dB")
        BTIDES_export_AdvData(bdaddr, bdaddr_random, adv_type, type_AdvData_3DInfoData, data)
        return True

    # type 0xFF
    elif isinstance(entry.payload, EIR_Manufacturer_Specific_Data):
        #entry.show()
        length = entry.len # Not clear if Scapy is using the original ACID len or their calculated and corrected len
        msd_hex_str = ""
        # Some devices don't include any actual MSD (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of MSD beyond the company_id before accessing .load
        if(length > 3):
            try:
                msd_hex_str = bytes_to_hex_str(entry.load)
            except Exception as e:
                vprint(f"Manufacturer-specific data is missing.")
                msd_hex_str = ""
                pass
            company_id_hex_str = f"{entry.company_id:04x}"
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

        # TODO: capture error responses to ATT_READ_REQs
        # Check if this error is due to a failed ATT_READ_REQ,
        # and if so, store the error in the io_array within the relevant Characteristic Value that we were trying to read
        if(request_opcode_in_error == type_ATT_READ_REQ):
            char_obj = find_characteristic_by_handle(connect_ind_obj=connect_ind_obj, value_handle=attribute_handle_in_error)
            if(not char_obj):
                # No match found. Cut our losses and return True for the above successful ATT export
                return True

            # TODO: arguably the value_hex_str should be all the stuff in an ERROR_RSP? I don't have a need for it yet but maybe I will eventually?
            # NOTE-TO-SELF: If I change this, then I need to change the expectations in ff_GATT_IO() too.
            value_hex_str = f"{att_data.ecode:02x}"
            io_array = [ {"io_type": type_ATT_ERROR_RSP, "value_hex_str": value_hex_str} ]
            io_array = ff_GATT_IO(io_array)
            if("char_value" not in char_obj.keys()):
                char_obj["char_value"] = {"value_handle": attribute_handle_in_error, "value_uuid": char_obj["value_uuid"], "io_array": io_array }
            else:
                if("io_array" not in char_obj["char_value"].keys()):
                    char_obj["char_value"]["io_array"] = io_array
                else:
                    char_obj["char_value"]["io_array"].extend(io_array)
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


def export_ATT_Read_By_Type_Request(connect_ind_obj, packet, direction=None):
    global g_last_requested_uuid_type
    if(packet.haslayer(ATT_Read_By_Type_Request)):
        att_data = get_ATT_data(packet, ATT_Read_By_Type_Request, type_ATT_READ_BY_TYPE_REQ)
        attribute_uuid = att_data.uuid
        g_last_requested_uuid_type = attribute_uuid
    elif(packet.haslayer(ATT_Read_By_Type_Request_128bit)):
        att_data = get_ATT_data(packet, ATT_Read_By_Type_Request_128bit, type_ATT_READ_BY_TYPE_REQ)
        uuid1 = att_data.uuid1 # FIXME: change Scapy definition to use a proper 16-byte UUID128!
        uuid2 = att_data.uuid2
        attribute_uuid = uuid1 + uuid2 # FIXME: untested, need to see value and debug to know what's in here currently
        g_last_requested_uuid_type = attribute_uuid
    else:
        return False
    try:
        if(direction == None):
            direction = get_packet_direction(packet)
        start_handle = att_data.start
        end_handle = att_data.end
    except Exception as e:
        print(f"Error processing ATT_Read_By_Type_Request: {e}")
        return False
    #handle = f"{att_data.gatt_handle:04x}" # FIXME: I'm not sure why this was accepted as valid output and the Schema validation says its fine...possible implicit conversion happening?
    data = ff_ATT_READ_BY_TYPE_REQ(direction, start_handle, end_handle, attribute_uuid)
    if_verbose_insert_std_optional_fields(data, packet)
    BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)
    return True


def export_ATT_Read_By_Type_Response(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Read_By_Type_Response, type_ATT_READ_BY_TYPE_RSP)
    if(att_data != None):
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            # In this packet type, length is "The size of each attribute handle-value pair"
            # So if there are multiple entries they must all be the same length
            length = att_data.len
            attribute_data_list = []
            for entry in att_data.handles:
                value_hex_str = bytes_to_hex_str(entry.value)
                list_entry = ff_ATT_READ_BY_TYPE_RSP_attribute_data_list_entry(
                                attribute_handle=entry.handle,
                                value_hex_str=value_hex_str
                                )
                attribute_data_list.append(list_entry)
        except Exception as e:
            print(f"Error processing ATT_Read_By_Type_Response: {e}")
            return False
        data = ff_ATT_READ_BY_TYPE_RSP(direction, length, attribute_data_list)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)

        # If this response is for a Read By Type Request for a Characteristic Declaration
        # then export it to the BTIDES accordingly
        if(g_last_requested_uuid_type == 0x2803):
            try:
                for list_obj in att_data.handles:
                    # If the handle is 0, then this is a "no more entries" marker
                    if(list_obj.handle == 0):
                        continue
                    if(len(list_obj.value) == 5):
                        properties, value_handle, value_uuid = struct.unpack("<BHH", list_obj.value[:5])
                        value_uuid = f"{value_uuid:04x}"
                    elif(len(list_obj.value) == 19):
                        properties, value_handle = struct.unpack("<BH", list_obj.value[:3])
                        value_uuid = bytes_reversed_to_hex_str(list_obj.value[3:])
                    else:
                        print("Unexpected length error.")
                        return False
                    data = {"handle": list_obj.handle, "properties": properties, "value_handle": value_handle, "value_uuid": value_uuid}
                    char_obj = ff_GATT_Characteristic(data)
                    # Going to insert a "char_value" placeholder, and then can insert io_array stuff based on later reads/writes etc.
                    char_value_obj = {"handle": value_handle, "value_uuid": value_uuid}
                    char_obj["char_value"] = char_value_obj
                    BTIDES_export_GATT_Characteristic(connect_ind_obj=connect_ind_obj, data=char_obj)

                    # Then also insert this information into the ATT_handle_enumeration
                    data = ff_ATT_handle_entry(list_obj.handle, "2803")
                    BTIDES_export_ATT_handle(connect_ind_obj=connect_ind_obj, data=data)
                    data = ff_ATT_handle_entry(value_handle, value_uuid)
                    BTIDES_export_ATT_handle(connect_ind_obj=connect_ind_obj, data=data)
            except Exception as e:
                print(f"Error processing ATT_Read_By_Type_Response: {e}")
                return False
        else:
            # TODO: needs to be tested
            pass

        return True
    return False


def export_ATT_Read_Request(connect_ind_obj, packet, direction=None):
    global g_last_read_handle
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
        g_last_read_handle = handle
        return True
    return False


def export_characteristic(list_obj, att_data, connect_ind_obj):
    global g_last_seen_characteristic_handle
    g_last_seen_characteristic_handle = g_last_read_handle
    # Interpret the att_data.value as a Characteristic
    properties, value_handle = struct.unpack("<BH", att_data.value[:3])
    if(len(att_data.value) == 5 or len(att_data.value) == 19):
        value_uuid = bytes_reversed_to_hex_str(att_data.value[3:])
    else:
        print("Unexpected length error.")
        return False
    data = {"handle": list_obj["handle"], "properties": properties, "value_handle": value_handle, "value_uuid": value_uuid}
    char_obj = ff_GATT_Characteristic(data)
    # Going to insert a "char_value" placeholder, and then can insert io_array stuff based on later reads/writes etc.
    char_value_obj = {"handle": value_handle, "value_uuid": value_uuid}
    char_obj["char_value"] = char_value_obj
    BTIDES_export_GATT_Characteristic(connect_ind_obj=connect_ind_obj, data=char_obj)
    # There can only be one entry out of all the entries that matches g_last_read_handle
    # so since we found it, we can return now
    return True


def insert_descriptor_object(char_obj, desc_obj):
    if("descriptors" not in char_obj.keys()):
        char_obj["descriptors"] = [ desc_obj ]
    else:
        char_obj["descriptors"].append(desc_obj)


def export_characteristic_descriptors(list_obj, att_data, connect_ind_obj):
    char_obj = find_characteristic_by_handle(connect_ind_obj=connect_ind_obj, handle=g_last_seen_characteristic_handle)
    # If there's no entry already inserted for the last characteristic, we won't have anywhere to put the
    # characteristic descriptor, so we can just return False as failure
    if(not char_obj):
        return False

    if(list_obj["UUID"] == "2900"):
        extended_properties, = struct.unpack("<H", att_data.value)
        desc_obj = {"handle": list_obj["handle"], "UUID": "2900", "extended_properties": extended_properties}
        desc_obj = ff_Descriptor(desc_obj)
        insert_descriptor_object(char_obj, desc_obj)
        return True

    elif(list_obj["UUID"] == "2901"):
        user_description_hex_str = bytes_to_hex_str(att_data.value)
        desc_obj = {"handle": list_obj["handle"], "UUID": "2901", "user_description_hex_str": user_description_hex_str}
        if(TME.TME_glob.verbose_BTIDES):
            utf8_user_description = bytes_to_utf8(att_data.value)
            desc_obj["utf8_user_description"] = utf8_user_description
        desc_obj = ff_Descriptor(desc_obj)
        insert_descriptor_object(char_obj, desc_obj)
        return True

    elif(list_obj["UUID"] == "2902"):
        config_bits, = struct.unpack("<H", att_data.value)
        desc_obj = {"handle": list_obj["handle"], "UUID": "2902", "config_bits": config_bits}
        desc_obj = ff_Descriptor(desc_obj)
        insert_descriptor_object(char_obj, desc_obj)
        return True

    elif(list_obj["UUID"] == "2903"):
        return True

    elif(list_obj["UUID"] == "2904"):
        format, exponent, unit, name_space, description = struct.unpack("<BBHBH", att_data.value)
        desc_obj = {"handle": list_obj["handle"], "UUID": "2904", "format": format, \
                    "exponent": exponent, "unit": unit, "name_space": name_space, "description": description}
        desc_obj = ff_Descriptor(desc_obj)
        insert_descriptor_object(char_obj, desc_obj)
        return True

    elif(list_obj["UUID"] == "2905"):
        return True

    return False


def export_characteristic_values(list_obj, att_data, connect_ind_obj):
    char_obj = find_characteristic_by_handle(connect_ind_obj=connect_ind_obj, value_handle=list_obj["handle"])
    if(not char_obj):
        # Couldn't find a match. Cut our losses and return success on the original ATT insertion at least
        return True
    # Just in case the value isn't there fore some reason (it should be from FOO
    if("char_value" not in char_obj.keys()):
        char_value_obj = {"handle": list_obj["handle"], "value_uuid": list_obj["UUID"]}
        char_obj["char_value"] = char_value_obj
    value_hex_str = bytes_to_hex_str(att_data.value)
    io_array = [ {"io_type_str": ATT_type_to_BTIDES_io_type_str[type_ATT_READ_RSP], "io_type": type_ATT_READ_RSP, "value_hex_str": value_hex_str} ]
    if("io_array" not in char_obj["char_value"].keys()):
        char_obj["char_value"]["io_array"] = io_array
    else:
        char_obj["char_value"]["io_array"].extend(io_array)
    return True


def export_ATT_Read_Response(connect_ind_obj, packet, direction=None):
    att_data = get_ATT_data(packet, ATT_Read_Response, type_ATT_READ_RSP)
    if(att_data != None):
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            value_hex_str = bytes_to_hex_str(att_data.value)
        except Exception as e:
            print(f"Error processing ATT_Read_Response: {e}")
            return False
        data = ff_ATT_READ_RSP(direction, value_hex_str)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_ATT_packet(connect_ind_obj=connect_ind_obj, data=data)

        # Now insert any characteristics/characteristic descriptors/characteristic values into the BTIDES JSON
        if(direction == type_BTIDES_direction_P2C):
            bdaddr = connect_ind_obj["peripheral_bdaddr"]
        elif(direction == type_BTIDES_direction_C2P):
            bdaddr = connect_ind_obj["central_bdaddr"]
        else:
            print(f"New direction added {direction}. Updated code.")
            exit(1)

        if(bdaddr not in g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data.keys()):
            # no match in the cache, so cut our losses and return True for the successful ATT export above
            return True

        for list_obj in g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data[bdaddr]:
            if(list_obj["handle"] != g_last_read_handle):
                continue
            if(list_obj["UUID"] == "2800" or list_obj["UUID"] == "2801" or list_obj["UUID"] == "2802"):
                # We handle services elsewhere, nothing more to do with them here
                continue
            # Handle characteristic insertion
            if(list_obj["UUID"] == "2803"):
                if(export_characteristic(list_obj, att_data, connect_ind_obj)):
                    return True

            # Handle characteristic descriptors insertion
            if(export_characteristic_descriptors(list_obj, att_data, connect_ind_obj)):
                return True

            # Handle characteristic value insertion
            if(export_characteristic_values(list_obj, att_data, connect_ind_obj)):
                return True
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
            bdaddr = ""
            if(direction == None):
                direction = get_packet_direction(packet)
                if(direction == type_BTIDES_direction_P2C):
                    bdaddr = connect_ind_obj["peripheral_bdaddr"]
                elif(direction == type_BTIDES_direction_C2P):
                    bdaddr = connect_ind_obj["central_bdaddr"]
                else:
                    print(f"New direction added {direction}. Updated code.")
                    exit(1)
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
                    # Store this information for later, so we can do Characteristic inserts
                    if(bdaddr not in g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data.keys()):
                        g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data[bdaddr] = []
                    g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data[bdaddr].append(list_obj)
            elif format == 2:
                # 2 byte handle, 16 byte UUID128
                for handle_obj in att_data.handles:
                    list_obj = ff_ATT_FIND_INFORMATION_RSP_information_data(
                                    handle=handle_obj.handle,
                                    UUID=str(handle_obj.value)
                                )
                    info_data_list.append(list_obj)
                    # Store this information for later, so we can do Characteristic inserts
                    if(bdaddr not in g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data.keys()):
                        g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data[bdaddr] = []
                    g_bdaddr_to_list_of_ff_ATT_FIND_INFORMATION_RSP_information_data[bdaddr].append(list_obj)
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

        # We can't insert characteristics until we've seen an ATT_READ_RSP for their values (so we know their properties, etc)

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
            if (att_data.length != 6 and att_data.length != 20):
                print("Unexpected length in Read By Group Type Response. Can't parse further.")
                return False
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
                    list_entry = ff_ATT_READ_BY_GROUP_TYPE_RSP_attribute_data_list_entry(
                                    attribute_handle=int.from_bytes(att_data.data[i:i+2], byteorder='little'),
                                    end_group_handle=int.from_bytes(att_data.data[i+2:i+4], byteorder='little'),
                                    UUID=f"{int.from_bytes(att_data.data[i+4:i+6], byteorder='little'):04x}"
                                    )
                    attribute_data_list.append(list_entry)
            elif(att_data.length == 20):
                # 2 byte start handle, 2 byte end handle, 16 byte UUID128
                data_len = len(att_data.data)
                for i in range(0, data_len, 20):
                    if i + 20 > data_len:
                        qprint("Not enough data left to process a 20-byte attribute data entry.")
                        break
                    list_entry = ff_ATT_READ_BY_GROUP_TYPE_RSP_attribute_data_list_entry(
                                    attribute_handle=int.from_bytes(att_data.data[i:i+2], byteorder='little'),
                                    end_group_handle=int.from_bytes(att_data.data[i+2:i+4], byteorder='little'),
                                    UUID=f"{int.from_bytes(att_data.data[i+4:i+20], byteorder='little'):032x}"
                                    )
                    attribute_data_list.append(list_entry)
        except Exception as e:
            print(f"Error processing ATT_Read_By_Group_Type_Response: {e}")
            return False
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
# SMP SECTION
######################################################################

# It shouldn't be necessary to check the opcode if Scapy knows about the packet type layer
# But just doing it out of an abundance of caution
def get_SMP_data(packet, scapy_type, packet_type):
    smp_hdr = packet.getlayer(SM_Hdr)
    if(smp_hdr == None):
        return None
    if(smp_hdr.sm_command != packet_type):
        return None
    if(packet.haslayer(scapy_type) == False):
        return None
    else:
        return packet.getlayer(scapy_type)


def export_SMP_Pairing_Request(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Pairing_Request, type_SMP_Pairing_Request)
    if smp_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        data = ff_SMP_Pairing_Request(direction=direction,
                                      io_cap=smp_data.iocap,
                                      oob_data=smp_data.oob,
                                      auth_req=smp_data.authentication,
                                      max_key_size=smp_data.max_key_size,
                                      initiator_key_dist=smp_data.initiator_key_distribution,
                                      responder_key_dist=smp_data.responder_key_distribution)
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_Response(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Pairing_Response, type_SMP_Pairing_Response)
    if smp_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            data = ff_SMP_Pairing_Response(direction=direction,
                                        io_cap=smp_data.iocap,
                                        oob_data=smp_data.oob,
                                        auth_req=smp_data.authentication,
                                        max_key_size=smp_data.max_key_size,
                                        initiator_key_dist=smp_data.initiator_key_distribution,
                                        responder_key_dist=smp_data.responder_key_distribution)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_Confirm(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Confirm, type_SMP_Pairing_Confirm)
    if smp_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            value_hex_str = bytes_to_hex_str(smp_data.confirm)
            data = ff_SMP_Pairing_Confirm(direction=direction,
                                        value_hex_str=value_hex_str)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_Random(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Random, type_SMP_Pairing_Random)
    if smp_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            value_hex_str = bytes_to_hex_str(smp_data.random)
            data = ff_SMP_Pairing_Random(direction=direction,
                                        value_hex_str=value_hex_str)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_Failed(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Failed, type_SMP_Pairing_Failed)
    if smp_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            data = ff_SMP_Pairing_Failed(direction=direction, reason=smp_data.reason)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Security_Request(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Security_Request, type_SMP_Security_Request)
    if smp_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            data = ff_SMP_Security_Request(direction=direction, auth_req=smp_data.authentication)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_Public_Key(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Public_Key, type_SMP_Pairing_Public_Key)
    if smp_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #smp_data.show()
            pub_key_x_hex_str = bytes_to_hex_str(smp_data.key_x)
            pub_key_y_hex_str = bytes_to_hex_str(smp_data.key_y)
            data = ff_SMP_Pairing_Public_Key(direction=direction,
                                                pub_key_x_hex_str=pub_key_x_hex_str,
                                                pub_key_y_hex_str=pub_key_y_hex_str)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_DHKey_Check(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_DHKey_Check, type_SMP_Pairing_DHKey_Check)
    if smp_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            value_hex_str = bytes_to_hex_str(smp_data.dhkey_check)
            data = ff_SMP_Pairing_DHKey_Check(direction=direction,
                                                value_hex_str=value_hex_str)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_SMP_Pairing_Keypress_Notification(connect_ind_obj, packet, direction=None):
    smp_data = get_SMP_data(packet, SM_Keypress_Notification, type_SMP_Pairing_Keypress_Notification)
    if smp_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            smp_data.show()
            data = ff_SMP_Pairing_Keypress_Notification(direction=direction, notification_type=smp_data.type)
        except AttributeError as e:
            print(f"Error accessing smp_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SMP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


######################################################################
# L2CAP SECTION
######################################################################

# It shouldn't be necessary to check the opcode if Scapy knows about the packet type layer
# But just doing it out of an abundance of caution
def get_L2CAP_data(packet, scapy_type, packet_type):
    l2cap_hdr = packet.getlayer(L2CAP_CmdHdr)
    if(l2cap_hdr == None):
        return None
    if(l2cap_hdr.code != packet_type):
        return None
    if(packet.haslayer(scapy_type) == False):
        return None
    else:
        return packet.getlayer(scapy_type)


def make_SDP_id_tuple(connect_ind_obj, CID):
    return (connect_ind_obj["central_bdaddr"],
            connect_ind_obj["central_bdaddr_rand"],
            connect_ind_obj["peripheral_bdaddr"],
            connect_ind_obj["peripheral_bdaddr_rand"],
            CID)


def insert_SDP_CID(connect_ind_obj, CID):
    global g_CIDs_used_for_SDP
    id_tuple = make_SDP_id_tuple(connect_ind_obj, CID)
    g_CIDs_used_for_SDP[id_tuple] = 1


def CID_in_CIDs_used_for_SDP(connect_ind_obj, CID):
    id_tuple = make_SDP_id_tuple(connect_ind_obj, CID)
    if(id_tuple in g_CIDs_used_for_SDP.keys()):
        return True
    else:
        return False


def delete_SDP_CID(connect_ind_obj, CID):
    global g_CIDs_used_for_SDP
    id_tuple = make_SDP_id_tuple(connect_ind_obj, CID)
    if(CID_in_CIDs_used_for_SDP(connect_ind_obj, CID)):
        del g_CIDs_used_for_SDP[id_tuple]


def export_L2CAP_CONNECTION_REQ(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_CONNECTION_REQ)
    l2cap_data = get_L2CAP_data(packet, L2CAP_ConnReq, type_L2CAP_CONNECTION_REQ)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            data = ff_L2CAP_CONNECTION_REQ(direction=direction,
                                            id=l2cap_hdr.id,
                                            data_len=l2cap_hdr.len,
                                            psm=l2cap_data.psm,
                                            source_cid=l2cap_data.scid)
            if(l2cap_data.psm == type_PSM_SDP):
                insert_SDP_CID(connect_ind_obj, l2cap_data.scid)

        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_CONNECTION_RSP(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_CONNECTION_RSP)
    l2cap_data = get_L2CAP_data(packet, L2CAP_ConnResp, type_L2CAP_CONNECTION_RSP)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            data = ff_L2CAP_CONNECTION_RSP(direction=direction,
                                            id=l2cap_hdr.id,
                                            data_len=l2cap_hdr.len,
                                            destination_cid=l2cap_data.dcid,
                                            source_cid=l2cap_data.scid,
                                            result=l2cap_data.result,
                                            status=l2cap_data.status)
            # Both the source CID and the dst CID are part of SDP so we need
            # them both in the global
            id_tuple = make_SDP_id_tuple(connect_ind_obj, l2cap_data.scid)
            if(id_tuple in g_CIDs_used_for_SDP.keys()):
                insert_SDP_CID(connect_ind_obj, l2cap_data.dcid)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_CONFIGURATION_REQ(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_CONFIGURATION_REQ)
    l2cap_data = get_L2CAP_data(packet, L2CAP_ConfReq, type_L2CAP_CONFIGURATION_REQ)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #packet.show()
            if(len(l2cap_data.config_options) > 0):
                config_options_hex_str=bytes_to_hex_str(l2cap_data.config_options)
            else:
                config_options_hex_str=None
            data = ff_L2CAP_CONFIGURATION_REQ(direction=direction,
                                                id=l2cap_hdr.id,
                                                data_len=l2cap_hdr.len,
                                                destination_cid=l2cap_data.dcid,
                                                flags=l2cap_data.flags,
                                                config_options_hex_str=config_options_hex_str)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_CONFIGURATION_RSP(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_CONFIGURATION_RSP)
    l2cap_data = get_L2CAP_data(packet, L2CAP_ConfResp, type_L2CAP_CONFIGURATION_RSP)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #packet.show()
            if(len(l2cap_data.config_options) > 0):
                config_options_hex_str=bytes_to_hex_str(l2cap_data.config_options)
            else:
                config_options_hex_str=None
            data = ff_L2CAP_CONFIGURATION_RSP(direction=direction,
                                                id=l2cap_hdr.id,
                                                data_len=l2cap_hdr.len,
                                                source_cid=l2cap_data.scid,
                                                flags=l2cap_data.flags,
                                                result=l2cap_data.result,
                                                config_options_hex_str=config_options_hex_str)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_DISCONNECTION_REQ(connect_ind_obj, packet, direction=None):
    global g_CIDs_used_for_SDP
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_DISCONNECTION_REQ)
    l2cap_data = get_L2CAP_data(packet, L2CAP_DisconnReq, type_L2CAP_DISCONNECTION_REQ)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #packet.show()
            data = ff_L2CAP_DISCONNECTION_REQ(direction=direction,
                                                id=l2cap_hdr.id,
                                                data_len=l2cap_hdr.len,
                                                destination_cid=l2cap_data.dcid,
                                                source_cid=l2cap_data.scid)
            delete_SDP_CID(connect_ind_obj, l2cap_data.dcid)
            delete_SDP_CID(connect_ind_obj, l2cap_data.scid)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_DISCONNECTION_RSP(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_DISCONNECTION_RSP)
    l2cap_data = get_L2CAP_data(packet, L2CAP_DisconnResp, type_L2CAP_DISCONNECTION_RSP)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #packet.show()
            data = ff_L2CAP_DISCONNECTION_RSP(direction=direction,
                                                id=l2cap_hdr.id,
                                                data_len=l2cap_hdr.len,
                                                destination_cid=l2cap_data.dcid,
                                                source_cid=l2cap_data.scid)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_INFORMATION_REQ(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_INFORMATION_REQ)
    l2cap_data = get_L2CAP_data(packet, L2CAP_InfoReq, type_L2CAP_INFORMATION_REQ)
    if l2cap_data is not None:
        try:
            if(direction == None):
                direction = get_packet_direction(packet)
            data = ff_L2CAP_INFORMATION_REQ(direction=direction,
                                            id=l2cap_hdr.id,
                                            data_len=l2cap_hdr.len,
                                            info_type=l2cap_data.info_type)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_INFORMATION_RSP(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_INFORMATION_RSP)
    l2cap_data = get_L2CAP_data(packet, L2CAP_InfoResp, type_L2CAP_INFORMATION_RSP)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            if(len(l2cap_data.info) > 0):
                info_hex_str=bytes_to_hex_str(l2cap_data.info)
            else:
                info_hex_str=None
            data = ff_L2CAP_INFORMATION_RSP(direction=direction,
                                            id=l2cap_hdr.id,
                                            data_len=l2cap_hdr.len,
                                            info_type=l2cap_data.info_type,
                                            result=l2cap_data.result,
                                            info_hex_str=info_hex_str)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False


def export_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ)
    l2cap_data = get_L2CAP_data(packet, L2CAP_Connection_Parameter_Update_Request, type_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #packet.show()
            data = ff_L2CAP_CONNECTION_PARAMETER_UPDATE_REQ(direction=direction,
                                                            id=l2cap_hdr.id,
                                                            data_len=l2cap_hdr.len,
                                                            interval_min=l2cap_data.min_interval,
                                                            interval_max=l2cap_data.max_interval,
                                                            latency=l2cap_data.latency,
                                                            timeout=l2cap_data.timeout)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False

def export_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(connect_ind_obj, packet, direction=None):
    l2cap_hdr = get_L2CAP_data(packet, L2CAP_CmdHdr, type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP)
    l2cap_data = get_L2CAP_data(packet, L2CAP_Connection_Parameter_Update_Response, type_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP)
    if l2cap_data is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            #packet.show()
            data = ff_L2CAP_CONNECTION_PARAMETER_UPDATE_RSP(direction=direction,
                                                            id=l2cap_hdr.id,
                                                            data_len=l2cap_hdr.len,
                                                            result=l2cap_data.result)
        except AttributeError as e:
            print(f"Error accessing l2cap_data fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_L2CAP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False

######################################################################
# SDP SECTION
######################################################################

# It shouldn't be necessary to check the opcode if Scapy knows about the packet type layer
# But just doing it out of an abundance of caution
def get_SDP_data(packet, scapy_type, packet_type):
    sdp_hdr = packet.getlayer(SDP_Hdr)
    if(sdp_hdr == None):
        return None
    if(sdp_hdr.pdu_id != packet_type):
        return None
    else:
        return packet.getlayer(scapy_type)


def export_SDP_ERROR_RSP(connect_ind_obj, packet, direction=None):
    l2cap_hdr = packet.getlayer(L2CAP_Hdr)
    sdp_hdr = get_SDP_data(packet, SDP_Hdr, type_SDP_ERROR_RSP)
    if l2cap_hdr is not None and sdp_hdr is not None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            error_code, = struct.unpack(">H", sdp_hdr.load)
            data = ff_SDP_ERROR_RSP(direction=direction,
                                    l2cap_len=l2cap_hdr.len,
                                    l2cap_cid=l2cap_hdr.cid,
                                    transaction_id=sdp_hdr.transaction_id,
                                    param_len=sdp_hdr.param_len,
                                    error_code=error_code)
        except AttributeError as e:
            print(f"Error accessing sdp_hdr fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SDP_packet(connect_ind_obj=connect_ind_obj, data=data)
        return True
    return False

# Can be used for:
# SDP_SERVICE_SEARCH_REQ
# SDP_SERVICE_SEARCH_RSP
# SDP_SERVICE_ATTR_REQ
# SDP_SERVICE_ATTR_RSP
# SDP_SERVICE_SEARCH_ATTR_REQ
# SDP_SERVICE_SEARCH_ATTR_RSP
def export_SDP_Common(pdu_id, connect_ind_obj, packet, direction=None):
    l2cap_hdr = packet.getlayer(L2CAP_Hdr)
    sdp_hdr = get_SDP_data(packet, SDP_Hdr, pdu_id)
    if l2cap_hdr != None and sdp_hdr != None:
        try:
            if direction is None:
                direction = get_packet_direction(packet)
            # packet.show()
            raw_data_hex_str = bytes_to_hex_str(sdp_hdr.load) # This is all the data after the header
            data = ff_SDP_Common(pdu_id=pdu_id,
                                 direction=direction,
                                 l2cap_len=l2cap_hdr.len,
                                 l2cap_cid=l2cap_hdr.cid,
                                 transaction_id=sdp_hdr.transaction_id,
                                 param_len=sdp_hdr.param_len,
                                 raw_data_hex_str=raw_data_hex_str)
        except AttributeError as e:
            print(f"Error accessing sdp_hdr fields: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_SDP_packet(connect_ind_obj=connect_ind_obj, data=data)
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
        BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
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