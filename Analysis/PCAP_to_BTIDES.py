import sys, re, json, argparse
# All the advertisement channel types
from scapy.all import PcapReader
# Import Layers:
from scapy.all import BTLE, BTLE_RF
from scapy.all import BTLE_CONNECT_REQ
from scapy.all import BTLE_ADV, BTLE_ADV_IND, BTLE_ADV_NONCONN_IND, BTLE_SCAN_RSP
# All the AdvData types
from scapy.all import EIR_Hdr, EIR_Flags, EIR_ShortenedLocalName, EIR_CompleteLocalName
from scapy.all import EIR_IncompleteList16BitServiceUUIDs, EIR_CompleteList16BitServiceUUIDs
from scapy.all import EIR_IncompleteList32BitServiceUUIDs, EIR_CompleteList32BitServiceUUIDs
from scapy.all import EIR_IncompleteList128BitServiceUUIDs, EIR_CompleteList128BitServiceUUIDs
from scapy.all import EIR_TX_Power_Level, EIR_Device_ID
from scapy.all import EIR_ClassOfDevice, EIR_PeripheralConnectionIntervalRange
from scapy.all import EIR_ServiceData16BitUUID, EIR_ServiceData32BitUUID, EIR_ServiceData128BitUUID
from scapy.all import EIR_Manufacturer_Specific_Data
# L2CAP types
from scapy.all import L2CAP_Hdr, ATT_Hdr
# ATT types
from scapy.all import ATT_Read_Request, ATT_Read_Response

from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator

from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON
from TME.TME_BTIDES_base import write_BTIDES, lookup_DualBDADDR_base_entry
from TME.TME_BTIDES_AdvData import BTIDES_export_AdvData
from TME.TME_AdvChan import ff_CONNECT_IND, ff_CONNECT_IND_placeholder
from TME.TME_BTIDES_ATT import BTIDES_export_ATT_packet, ff_ATT_READ_REQ, ff_ATT_READ_RSP

verbose_print = False

def vprint(fmt):
    if(verbose_print): print(fmt)

g_access_address_to_connect_ind_obj = {}

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
    #print(f"flags_hex_str = {flags_hex_str}")
    return flags_hex_str


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
        utf8_name = local_name.decode('utf-8')
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
        utf8_name = local_name.decode('utf-8')
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
        #print(f"{CoD_int:06x}")
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

    # type 0xFF
    elif isinstance(entry.payload, EIR_Manufacturer_Specific_Data):
        #entry.show()
        #print(f"{device_bdaddr}")
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


def export_ADV_IND(packet):
    btle_hdr = packet.getlayer(BTLE)
    bdaddr_random = 1 if (btle_hdr.TxAdd == "random") else 0

    # Access the BTLE_ADV layer
    btle_adv = packet.getlayer(BTLE_ADV_IND)
    device_bdaddr = btle_adv.AdvA

    for entry in btle_adv.data:
        if isinstance(entry, EIR_Hdr):
            if(export_AdvData(device_bdaddr, bdaddr_random, type_AdvChanPDU_ADV_IND, entry)): return True

    return False


def export_ADV_NONCONN_IND(packet):
    btle_hdr = packet.getlayer(BTLE)
    bdaddr_random = 1 if (btle_hdr.TxAdd == "random") else 0

    # Access the BTLE_ADV layer
    btle_adv = packet.getlayer(BTLE_ADV_NONCONN_IND)
    device_bdaddr = btle_adv.AdvA

    for entry in btle_adv.data:
        if isinstance(entry, EIR_Hdr):
            if(export_AdvData(device_bdaddr, bdaddr_random, type_AdvChanPDU_ADV_NONCONN_IND, entry)): return True

    return False


def export_SCAN_RSP(packet):
    btle_hdr = packet.getlayer(BTLE)
    bdaddr_random = 1 if (btle_hdr.TxAdd == "random") else 0

    # Access the SCAN_RSP layer
    btle_adv = packet.getlayer(BTLE_SCAN_RSP)
    device_bdaddr = btle_adv.AdvA

    for entry in btle_adv.data:
        if isinstance(entry, EIR_Hdr):
            if(export_AdvData(device_bdaddr, bdaddr_random, type_AdvChanPDU_SCAN_RSP, entry)): return True

    return False


def export_ATT_Read_Request(connect_ind_obj, packet):
    att_hdr = packet.getlayer(ATT_Hdr)
    if(att_hdr == None):
        return False
    att_data = packet.getlayer(ATT_Read_Request)
    if(att_data == None):
        return False
    if(att_hdr.opcode == type_ATT_READ_REQ):
        handle = f"{att_data.gatt_handle:04x}"
        #BTIDES_export_ATT_READ_REQ(connect_ind_obj, handle)
        data = ff_ATT_READ_REQ(handle)
        BTIDES_export_ATT_packet(connect_ind_obj, type_ATT_READ_RSP, data)

    return True


def export_ATT_Read_Response(connect_ind_obj, packet):
    #packet.show()
    att_hdr = packet.getlayer(ATT_Hdr)
    if(att_hdr == None):
        return False
    att_data = packet.getlayer(ATT_Read_Response)
    if(att_data == None):
        return False
    if(att_hdr.opcode == type_ATT_READ_RSP):
        value_hex_str = ''.join(format(byte, '02x') for byte in att_data.value)
        data = ff_ATT_READ_RSP(value_hex_str)
        BTIDES_export_ATT_packet(connect_ind_obj, type_ATT_READ_RSP, data)

    return True


def export_ATTArray(packet):
    rf_fields = packet.getlayer(BTLE_RF)
    channel_freq = rf_fields.rf_channel * 2 + 2402 # Channel in MHz

    ble_fields = packet.getlayer(BTLE)
    access_address = ble_fields.access_addr

    if access_address in g_access_address_to_connect_ind_obj:
        connect_ind_obj = g_access_address_to_connect_ind_obj[access_address]
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # The opcodes are mutually exclusive, so if one returns true, we're done
    # To convert ATT data into a GATT hierarchy requires us to statefully
    # remember information between packets (i.e. which UUID corresponds to which handle)     
    if(export_ATT_Read_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_Response(connect_ind_obj, packet)):
        return True
    # TODO: handle ALL opcodes


def export_CONNECT_IND(packet):
    global BTIDES_JSON
    global g_access_address_to_connect_ind_obj
    
    #packet.show()
    ''' In the future we may want to store these, once we add a place to store CONNECT_IND specifically...
    rf_fields = packet.getlayer(BTLE_RF)
    channel_freq = rf_fields.rf_channel * 2 + 2402 # Channel in MHz
    rssi = rf_fields.signal
    '''

    # Store the BDADDRs involved in the connection into a dictionary, queryable by access address
    # This dictionary will need to be used by all subsequent packets within the connection to figure out
    # which bdaddr to associate their data with
    ble_fields = packet.getlayer(BTLE)
    ble_adv_fields = packet.getlayer(BTLE_ADV)
    central_bdaddr_random = ble_adv_fields.TxAdd
    peripheral_bdaddr_random = ble_adv_fields.RxAdd
    connect_fields = packet.getlayer(BTLE_CONNECT_REQ)
    central_bdaddr = connect_fields.InitA
    peripheral_bdaddr = connect_fields.AdvA
    # The following 3 multi-byte fields are in the incorrect byte order in Scapy (according to looking at their values in Wireshark, which I trust more)
    access_address = int.from_bytes(connect_fields.AA.to_bytes(4, byteorder='little'), byteorder='big')
    channel_map_hex_str = ''.join(f'{byte:02x}' for byte in connect_fields.chM.to_bytes(5, byteorder='little'))
    crc_init_hex_str = ''.join(f'{byte:02x}' for byte in connect_fields.crc_init.to_bytes(3, byteorder='little'))
    connect_ind_obj = ff_CONNECT_IND(
        central_bdaddr=central_bdaddr,
        central_bdaddr_rand=central_bdaddr_random,
        peripheral_bdaddr=peripheral_bdaddr,
        peripheral_bdaddr_rand=peripheral_bdaddr_random,
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
    # Store the CONNECT_IND obj into g_access_address_to_bdaddrs for later use in lookups
    g_access_address_to_connect_ind_obj[access_address] = connect_ind_obj

    generic_DualBDADDR_insertion_into_BTIDES_zeroth_level(connect_ind_obj)

    return True


def read_pcap(file_path):
    try:
        with PcapReader(file_path) as pcap_reader:
            for packet in pcap_reader:
                # Confirm packet is BTLE
                if packet.haslayer(BTLE):
                    btle_hdr = packet.getlayer(BTLE)
                    if(btle_hdr.access_addr != 0x8e89bed6 and btle_hdr.len == 0):
                        #print("Found empty non-advertisement packet, continuing") 
                        continue
                    # If a packet matches on any export function, move on to the next packet
                    
                    # Connection requests
                    if packet.haslayer(BTLE_CONNECT_REQ): # FIXME: Scapy is wrong here, it should be CONNECT_IND
                        if(export_CONNECT_IND(packet)): continue

                    # Advertisement channel packets
                    if packet.haslayer(BTLE_ADV_IND):
                        if(export_ADV_IND(packet)): continue
                    if packet.haslayer(BTLE_ADV_NONCONN_IND):
                        if(export_ADV_NONCONN_IND(packet)): continue
                    if packet.haslayer(BTLE_SCAN_RSP):
                        if(export_SCAN_RSP(packet)): continue

                    # ATT packets
                    if packet.haslayer(ATT_Hdr):
                        if(export_ATTArray(packet)): continue
                    # TODO: export other packet types like LL or L2CAP or ATT
#                else:
#                    packet.show()

        return
    except Exception as e:
        print(f"Error reading pcap file: {e}")


def main():
    global verbose_print
    parser = argparse.ArgumentParser(description='Input BTIDES files to MySQL tables.')
    parser.add_argument('--input', type=str, required=True, help='Input file name for pcap file.')
    parser.add_argument('--output', type=str, required=True, help='Output file name for BTIDES JSON file.')
    parser.add_argument('--verbose', action='store_true',required=False, help='Print output about the found fields as each packet is parsed.')
    args = parser.parse_args()

    in_pcap_filename = args.input
    out_BTIDES_filename = args.output
    verbose_print = args.verbose

    print("Reading pcap.")
    read_pcap(in_pcap_filename)

    print("Writing BTIDES data to file.")
    write_BTIDES(out_BTIDES_filename)
    print("Export completed with no errors.")

if __name__ == "__main__":
    main()