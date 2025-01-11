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
