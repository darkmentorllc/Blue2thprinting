import sys, re, json, argparse
# All the advertisement channel types
from scapy.all import PcapReader, BTLE, BTLE_ADV, BTLE_ADV_IND, BTLE_ADV_NONCONN_IND, BTLE_SCAN_RSP
# All the AdvData types
from scapy.all import EIR_Hdr, EIR_Flags, EIR_ShortenedLocalName, EIR_CompleteLocalName
from scapy.all import EIR_IncompleteList16BitServiceUUIDs, EIR_CompleteList16BitServiceUUIDs
from scapy.all import EIR_IncompleteList32BitServiceUUIDs, EIR_CompleteList32BitServiceUUIDs
from scapy.all import EIR_TX_Power_Level, EIR_Device_ID, EIR_Manufacturer_Specific_Data

from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator

from TME.TME_glob import verbose_BTIDES, BTIDES_JSON
from TME.TME_BTIDES_base import *
from TME.TME_BTIDES_AdvData import *

verbose_print = False

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
def export_fields(device_bdaddr, bdaddr_random, adv_type, entry):
    global g

    if isinstance(entry.payload, EIR_Flags):
        flags_hex_str = scapy_flags_to_hex_str(entry)
        length = 2 # 1 bytes for opcode + 1 byte for flags
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "flags_hex_str": flags_hex_str}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Flags: {flags_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_Flags, data)

    elif isinstance(entry.payload, EIR_CompleteLocalName):
        local_name = entry.local_name
        utf8_name = local_name.decode('utf-8')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Complete Local Name: {utf8_name}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_CompleteName, data)

    elif isinstance(entry.payload, EIR_ShortenedLocalName):
        local_name = entry.local_name
        utf8_name = local_name.decode('utf-8')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_IncompleteName, data)
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Incomplete Local Name: {utf8_name}")

    elif isinstance(entry.payload, EIR_IncompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Incomplete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListIncomplete, data)

    elif isinstance(entry.payload, EIR_CompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID16List": UUID16List}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Complete UUID16 list: {','.join(UUID16List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListComplete, data)

    elif isinstance(entry.payload, EIR_IncompleteList32BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID32List = [f"{uuid:08x}" for uuid in uuid_list]
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32List": UUID32List}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Incomplete UUID32 list: {','.join(UUID32List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ListIncomplete, data)

    elif isinstance(entry.payload, EIR_CompleteList32BitServiceUUIDs):
        #entry.show()
        uuid_list = entry.svc_uuids
        UUID32List = [f"{uuid:08x}" for uuid in uuid_list]
        length = 1 + 4 * len(UUID32List) # 1 byte for opcode, 4 bytes for each UUID32
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "UUID32List": UUID32List}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Complete UUID32 list: {','.join(UUID32List)}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID32ListComplete, data)

    elif isinstance(entry.payload, EIR_TX_Power_Level):
        device_tx_power = entry.level
        length = 2 # 1 byte for opcode, 1 byte power level
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "tx_power": device_tx_power}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} TxPower level: {device_tx_power}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_TxPower, data)

    # I don't think this can actually appear in BLE as opposed to EIR...so I'm not sure if this will get any testing...
    elif isinstance(entry.payload, EIR_Device_ID):
        device_tx_power = entry.level
        length = 9 # 1 byte for opcode + 2 bytes * 4 fields
        exit_on_len_mismatch(length, entry)
        data = {"length": length, "vendor_id_source": entry.vendor_id_source, "vendor_id": entry.vendor_id, "product_id": entry.product_id, "version": entry.version}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Device ID: {data}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_DeviceID, data)

    elif isinstance(entry.payload, EIR_Manufacturer_Specific_Data):
        #entry.show()
        #print(f"{device_bdaddr}")
        company_id_hex_str = f"{entry.company_id:04x}"
        length = entry.len # 1 byte for opcode + 2 bytes * 4 fields
        msd_hex_str = ""
        # Some devices don't include any actual MSD (whether that's because they ran out of space in the advertisement,
        # or just choose to, I don't know. But this ensures we have at least 1 byte of MSD beyond the company_id before accessing .load
        if(length > 3):
            msd_hex_str = ''.join(format(byte, '02x') for byte in entry.load)
        data = {"length": length, "company_id_hex_str": company_id_hex_str, "msd_hex_str": msd_hex_str}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} MSD: company_id = {company_id_hex_str}, data = {msd_hex_str}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_MSD, data)

# Saved text for printing fields
#                    print("BTLE Packet Fields:")
#                    for field in btle_adv.fields_desc:
#                        print(f"{field.name}: {field.__class__.__name__}")


def export_ADV_IND(bdaddr_random, packet):
    if packet.haslayer(BTLE_ADV_IND):
        # Access the BTLE_ADV layer
        btle_adv = packet.getlayer(BTLE_ADV_IND)
        device_bdaddr = btle_adv.AdvA
    else: return False

    for entry in btle_adv.data:
        if isinstance(entry, EIR_Hdr):
            export_fields(device_bdaddr, bdaddr_random, pdutype_ADV_IND, entry)
    return True

def export_ADV_NONCONN_IND(bdaddr_random, packet):
    if packet.haslayer(BTLE_ADV_NONCONN_IND):
        # Access the BTLE_ADV layer
        btle_adv = packet.getlayer(BTLE_ADV_NONCONN_IND)
        device_bdaddr = btle_adv.AdvA
    else: return False

    for entry in btle_adv.data:
        if isinstance(entry, EIR_Hdr):
            export_fields(device_bdaddr, bdaddr_random, pdutype_ADV_NONCONN_IND, entry)
    return True

def export_SCAN_RSP(bdaddr_random, packet):
    if packet.haslayer(BTLE_SCAN_RSP):
        # Access the SCAN_RSP layer
        btle_adv = packet.getlayer(BTLE_SCAN_RSP)
        device_bdaddr = btle_adv.AdvA
    else: return False

    for entry in btle_adv.data:
        if isinstance(entry, EIR_Hdr):
            export_fields(device_bdaddr, bdaddr_random, pdutype_SCAN_RSP, entry)
    return True

def export_all_AdvChanData(bdaddr_random, packet):
    # The advertisement types are mutually exclusive, so if one returns true, we're done
    # Order from most-prevalent to least, to increase the chance of ending earlier
    if(export_ADV_IND(bdaddr_random, packet)): return
    if(export_ADV_NONCONN_IND(bdaddr_random, packet)): return
    if(export_SCAN_RSP(bdaddr_random, packet)): return
    # TODO: export other AdvData-containing packet types

def read_pcap(file_path):
    try:
        with PcapReader(file_path) as pcap_reader:
            for packet in pcap_reader:
                # Concirm packet is BTLE
                if packet.haslayer(BTLE):
                    btle_hdr = packet.getlayer(BTLE)
                    bdaddr_random = 1 if (btle_hdr.TxAdd == "random") else 0

                    export_all_AdvChanData(bdaddr_random, packet)

                    # TODO: export other packet types like LL or L2CAP or ATT
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