import sys, re, json, argparse
from scapy.all import PcapReader, BTLE, BTLE_ADV, BTLE_ADV_IND, BTLE_ADV_NONCONN_IND, BTLE_SCAN_RSP
from scapy.all import EIR_Hdr, EIR_ShortenedLocalName, EIR_CompleteLocalName, EIR_IncompleteList16BitServiceUUIDs, EIR_CompleteList16BitServiceUUIDs
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator


from TME.TME_glob import verbose_BTIDES, BTIDES_JSON
from TME.TME_BTIDES_base import *
from TME.TME_BTIDES_AdvData import *

#BTIDES_JSON = [] # This will be the BTIDES structure before exporting

#verbose_BTIDES = True
verbose_print = False

############################
# Helper "factory functions"
############################  

def export_fields(device_bdaddr, bdaddr_random, adv_type, entry):
    global g
    if isinstance(entry.payload, EIR_CompleteLocalName):
        local_name = entry.local_name
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        utf8_name = local_name.decode('utf-8')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Complete Local Name: {utf8_name}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_CompleteName, data)

    elif isinstance(entry.payload, EIR_ShortenedLocalName):
        local_name = entry.local_name
        length = int(1 + len(local_name)) # 1 bytes for opcode + length of the string
        utf8_name = local_name.decode('utf-8')
        name_hex_str = ''.join(format(byte, '02x') for byte in local_name)
        data = {"length": length, "utf8_name": utf8_name, "name_hex_str": name_hex_str}
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Incomplete Local Name: {utf8_name}")
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_IncompleteName, data)

    elif isinstance(entry.payload, EIR_IncompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": UUID16List}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListIncomplete, data)
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Incomplete UUID16 list: {','.join(UUID16List)}")

    elif isinstance(entry.payload, EIR_CompleteList16BitServiceUUIDs):
        uuid_list = entry.svc_uuids
        UUID16List = [f"{uuid:04x}" for uuid in uuid_list]
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": UUID16List}
        BTIDES_export_AdvData(device_bdaddr, bdaddr_random, adv_type, type_AdvData_UUID16ListComplete, data)
        if(verbose_print): print(f"{device_bdaddr}: {adv_type} Complete UUID16 list: {','.join(UUID16List)}")

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