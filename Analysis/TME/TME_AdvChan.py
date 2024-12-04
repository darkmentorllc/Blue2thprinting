########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

import struct
from TME.TME_helpers import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_UUID16 import *
from TME.TME_UUID32 import *
from TME.TME_UUID128 import *

########################################
# Transmit Power
########################################

def print_transmit_power(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    eir_query = f"SELECT device_tx_power FROM EIR_bdaddr_to_tx_power WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    for (device_tx_power,) in eir_result:
        print(f"\tTransmit Power: {device_tx_power}dB")
        print(f"\t\tIn BT Classic Data (EIR_bdaddr_to_tx_power)")

        data = {"length": 2, "tx_power": device_tx_power}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_TxPower, data)

#    le_query = f"SELECT device_tx_power, bdaddr_random, le_evt_type FROM LE_bdaddr_to_tx_power WHERE device_bdaddr = '{bdaddr}' AND bdaddr_random = {nametype}"
    le_query = f"SELECT device_tx_power, bdaddr_random, le_evt_type FROM LE_bdaddr_to_tx_power WHERE device_bdaddr = '{bdaddr}'" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query)
    for device_tx_power, random, le_evt_type in le_result:
        print(f"\tTransmit Power: {device_tx_power}dB")
        print(f"\t\tIn BT LE Data (LE_bdaddr_to_tx_power), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        print(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

        data = {"length": 2, "tx_power": device_tx_power}
        BTIDES_export_AdvData(bdaddr, random, le_evt_type, type_AdvData_TxPower, data)

    if (len(eir_result)== 0 and len(le_result) == 0):
        print("\tNo transmit power found.")

    print("")

########################################
# Flags
########################################

def print_flags(bdaddr):
    bdaddr = bdaddr.strip().lower()

    eir_query = f"SELECT le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host FROM EIR_bdaddr_to_flags2 WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    for (le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) in eir_result:
        print(f"\tIn BT Classic Data (EIR_bdaddr_to_flags2)")
        print(f"\t\tBLE Limited Discoverable Mode: {le_limited_discoverable_mode}")
        print(f"\t\tBLE General Discoverable Mode: {le_general_discoverable_mode}")
        print(f"\t\tBR/EDR Not Supported: {bredr_not_supported}")
        print(f"\t\tSimultaneous BLE and BR/EDR Supported by Controller: {le_bredr_support_controller}")
        print(f"\t\tSimultaneous BLE and BR/EDR Supported by Host: {le_bredr_support_controller}")

        flags_hex_str = get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
        data = {"length": 2, "flags_hex_str": flags_hex_str}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_Flags, data)

    le_query = f"SELECT bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host FROM LE_bdaddr_to_flags2 WHERE device_bdaddr = '{bdaddr}'"
    le_result = execute_query(le_query)
    for (bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) in le_result:
        print(f"\tIn BLE Data (LE_bdaddr_to_flags2)")
        print(f"\t\tBLE Limited Discoverable Mode: {le_limited_discoverable_mode}")
        print(f"\t\tBLE General Discoverable Mode: {le_general_discoverable_mode}")
        print(f"\t\tBR/EDR Not Supported: {bredr_not_supported}")
        print(f"\t\tSimultaneous BLE and BR/EDR Supported by Controller: {le_bredr_support_controller}")
        print(f"\t\tSimultaneous BLE and BR/EDR Supported by Host: {le_bredr_support_controller}")

        flags_hex_str = get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
        data = {"length": 2, "flags_hex_str": flags_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_Flags, data)

    if (len(eir_result) == 0 and len(le_result) == 0):
        print("\tNo flags found.")

    print("")

########################################
# Manufacturer-specific Data
########################################

# Data format from https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair
def extract_ms_msd_name(manufacturer_specific_data):
    if(manufacturer_specific_data[0:6] == "030080" and len(manufacturer_specific_data) >= 8): # (need at least 8 hex digits for there to be 1 hex digit of ASCII chars)
        byte_data = bytes.fromhex(manufacturer_specific_data[6:])
        utf8_string = byte_data.decode('utf-8')
    if(manufacturer_specific_data[0:6] == "030280" and len(manufacturer_specific_data) >= 14): # ditto ^^^ 14
        byte_data = bytes.fromhex(manufacturer_specific_data[12:])
        utf8_string = byte_data.decode('utf-8')
    if(manufacturer_specific_data[0:6] == "030180" and len(manufacturer_specific_data) >= 26): # ditto ^^^ 26
        byte_data = bytes.fromhex(manufacturer_specific_data[24:])
        utf8_string = byte_data.decode('utf-8')

    if(len(utf8_string) > 0):
        return utf8_string
    else:
        return "No name found"

def print_manufacturer_data(bdaddr):
    bdaddr = bdaddr.strip().lower()

    eir_query = f"SELECT device_BT_CID, manufacturer_specific_data FROM EIR_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)
    le_query = f"SELECT le_evt_type, bdaddr_random, device_BT_CID, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE device_bdaddr = '{bdaddr}'"
    le_result = execute_query(le_query)

    if (len(eir_result) != 0 or len(le_result) != 0):
        print("\tManufacturer-specific Data:")

    for device_BT_CID, manufacturer_specific_data in eir_result:
        print(f"\t\tDevice Company ID: 0x%04x (%s) - take with a grain of salt, not all companies populate this accurately!" % (device_BT_CID, BT_CID_to_company_name(device_BT_CID)))
        flipped_endian = (device_BT_CID & 0xFF) << 8 | (device_BT_CID >> 8)
        print(f"\t\t\t Endianness-flipped device company ID (in case the vendor used the wrong endianness): 0x%04x (%s)" % (flipped_endian, BT_CID_to_company_name(flipped_endian)))
        print(f"\t\tRaw Data: {manufacturer_specific_data}")
        # TODO: DELETEME? I don't think there can be BT classic iBeacons can there?
        if({BT_CID_to_company_name(device_BT_CID)} == "Apple, Inc." and manufacturer_specific_data[0:3] == "0215"):
            print(f"\t\tApple iBeacon:")
        print(f"\t\t\tIn BT Classic Data (EIR_bdaddr_to_MSD)")

    for le_evt_type, bdaddr_random, device_BT_CID, manufacturer_specific_data in le_result:
        print(f"\t\tDevice Company ID: 0x%04x (%s) - take with a grain of salt, not all companies populate this accurately!" % (device_BT_CID, BT_CID_to_company_name(device_BT_CID)))
        flipped_endian = (device_BT_CID & 0xFF) << 8 | (device_BT_CID >> 8)
        print(f"\t\t\t Endianness-flipped device company ID (in case the vendor used the wrong endianness): 0x%04x (%s)" % (flipped_endian, BT_CID_to_company_name(flipped_endian)))
        print(f"\t\tRaw Data: {manufacturer_specific_data}")

        # Print Apple iBeacon information
        if(device_BT_CID == 76 and manufacturer_specific_data[0:4] == "0215"):
            print(f"\t\tApple iBeacon:")
            UUID128 = f"{manufacturer_specific_data[4:12]}-{manufacturer_specific_data[12:16]}-{manufacturer_specific_data[16:20]}-{manufacturer_specific_data[20:24]}-{manufacturer_specific_data[24:36]}"
            major = f"{manufacturer_specific_data[36:40]}"
            minor = f"{manufacturer_specific_data[40:44]}"
            rssi = f"{manufacturer_specific_data[44:46]}"
            print(f"\t\t\tUUID128: {UUID128}")
            print(f"\t\t\tMajor ID: {major}")
            print(f"\t\t\tMinor ID: {minor}")
            signed_rssi = int(rssi, 16)
            if(signed_rssi & 0x80):
                signed_rssi -= 256
            print(f"\t\t\tRSSI at 1 meter: {signed_rssi}dBm")

        elif(device_BT_CID == 6):
            # Print Microsoft Swift Pair information (format from https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair)
            if(manufacturer_specific_data[0:6] == "030080"): # "Pairing over LE only"
                print(f"\t\tMicrosoft Swift Pair - \"Pairing over LE only\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                print(f"\t\t\tDisplayName = {utf8_string}")
            if(manufacturer_specific_data[0:6] == "030280"): # "Pairing over LE and BR/EDR with Secure Connections"
                print(f"\t\tMicrosoft Swift Pair - \"Pairing over LE and BR/EDR with Secure Connections\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                print(f"\t\t\tDisplayName = {utf8_string}")
                CoD_bytes = bytes.fromhex(manufacturer_specific_data[6:12])
                big_endian_integer_CoD = struct.unpack('>I', b'\x00' + CoD_bytes)[0]
                print_CoD_to_names(big_endian_integer_CoD)
            if(manufacturer_specific_data[0:6] == "030180"): # "Pairing over BR/EDR only, using Bluetooth LE for discovery"
                print(f"\t\tMicrosoft Swift Pair - \"Pairing over BR/EDR only, using Bluetooth LE for discovery\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                print(f"\t\t\tDisplayName = {utf8_string}")
                CoD_bytes = bytes.fromhex(manufacturer_specific_data[18:24])
                big_endian_integer_CoD = struct.unpack('>I', b'\x00' + CoD_bytes)[0]
                print_CoD_to_names(big_endian_integer_CoD)
                BTC_BDADDR_bytes = bytes.fromhex(manufacturer_specific_data[6:18])
                BTC_BDADDR_str = f"{BTC_BDADDR_bytes[5]:02x}:{BTC_BDADDR_bytes[4]:02x}:{BTC_BDADDR_bytes[3]:02x}:{BTC_BDADDR_bytes[2]:02x}:{BTC_BDADDR_bytes[1]:02x}:{BTC_BDADDR_bytes[0]:02x}"
                print(f"\t\t\tBluetooth Classic BDADDR embedded in MSD = {BTC_BDADDR_str}")
                print_company_name_from_bdaddr("\t\t\t\t", BTC_BDADDR_str, False)
            # Print other Microsoft beacon information (format from https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cdp/77b446d0-8cea-4821-ad21-fabdf4d9a569)
            if(manufacturer_specific_data[0:2] == "01"):
                print(f"\t\tMicrosoft Beacon:")
                device_types = {
                    1: "Xbox One",
                    6: "Apple iPhone",
                    7: "Apple iPad",
                    8: "Android device",
                    9: "Windows 10 Desktop",
                    11: "Windows 10 Phone",
                    12: "Linux device",
                    13: "Windows IoT",
                    14: "Surface Hub",
                    15: "Windows laptop",
                    16: "Windows tablet"
                }
                device_type = int(manufacturer_specific_data[2:4], 16)
                device_type = device_type & 0x1f # It's technically only the bottom 5 bits, though no one (including Microsoft) seems to set the upper 3 bits to 001 like the spec says they should
                print(f"\t\t\tDevice Type = {device_types[device_type]}")
                Version_and_Flags = int(manufacturer_specific_data[4:6], 16)
                if(Version_and_Flags == 0x20):
                    share_state = "only my devices"
                elif(Version_and_Flags == 0x21):
                    share_state = "everyone"
                else:
                    share_state = "Unknown value: check for specification update!"
                print(f"\t\t\tNearBy share set to: {share_state}")
                # The values observed in the wild for Flags_and_Device_Status only make sense if you assume the MS spec has the bit ordering reversed and bit 0 is right-most not left-most
                Flags_and_Device_Status = int(manufacturer_specific_data[6:8], 16)
                Bluetooth_Address_As_Device_ID = True if((Flags_and_Device_Status >> 5) & 1) else False
                print(f"\t\t\tBluetooth address can be used as the device ID?: {Bluetooth_Address_As_Device_ID}")
                ExtendedDeviceStatus = Flags_and_Device_Status & 0xf
                # per spec "Values may be ORed"
                if(ExtendedDeviceStatus & 0x1):
                    print(f"\t\t\tExtended Status: Hosted by remote session")
                if(ExtendedDeviceStatus & 0x2):
                    print(f"\t\t\tExtended Status: The device does not have session hosting status available")
                if(ExtendedDeviceStatus & 0x4):
                    print(f"\t\t\tExtended Status: The device supports NearShare if the user is the same for the other device")
                if(ExtendedDeviceStatus & 0x8):
                    print(f"\t\t\tExtended Status: The device supports NearShare")
                if(ExtendedDeviceStatus == 0):
                    print(f"\t\t\tExtended Status: None")
                Salt_bytes = bytes.fromhex(manufacturer_specific_data[8:16])
                big_endian_integer_Salt = struct.unpack('<I', Salt_bytes)[0] # Salt is ostensibly stored little-endian, but without knowing a "Device Thumbprint" to calculate the Device Hash I can't be sure
                print(f"\t\t\tSalt: 0x{big_endian_integer_Salt:08x}")
                #Device_Hash_bytes = bytes.fromhex(manufacturer_specific_data[16:])
                print(f"\t\t\tDevice Hash: {manufacturer_specific_data[16:]}")
                # Non-spec interpretation based on observed data: I see 2 bytes and then a string
                # This seems to only occur if(ExtendedDeviceStatus & 0x8). Found some if(ExtendedDeviceStatus & 0x4), data and confirmed it doesn't occur then
                if(ExtendedDeviceStatus & 0x8):
                    try:
                        Device_Hash_as_utf8_str = bytes.fromhex(manufacturer_specific_data[20:]).decode('utf-8')
                        print(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as possible string: {Device_Hash_as_utf8_str}")
                        Device_Hash_unknown_bytes = bytes.fromhex(manufacturer_specific_data[16:20])
                        Device_Hash_unknown_bytes_little_endian_short = struct.unpack('<H', Device_Hash_unknown_bytes)[0]
                        print(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as possible string: unknown prefix bytes interpreted as little-endian 16-bit value: 0x{Device_Hash_unknown_bytes_little_endian_short:04x}")
                    except:
                        print(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as string: does not decode")


        # TODO: Does this have the necessary information to parse Amazon MSD? https://developer.amazon.com/en-US/docs/alexa/alexa-gadgets-toolkit/bluetooth-le-settings.html
        # TODO: Parse Eddystone even though it's deprecated?

        print(f"\t\t\tIn BT LE Data (LE_bdaddr_to_MSD), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        print(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")


    if (len(eir_result)== 0 and len(le_result) == 0):
        print("\tNo Manufacturer-specific Data found.")

    print("")

# Changing up the formatting to print all the AdvData underneath whatever advertisement/scan response it originally appeared in
def print_all_advdata(bdaddr, nametype):
    # TODO: Ideally I want to have information grouped by the source packet type it came in on 
    # TODO: But looping through and printing only the information for a single type at a time seem like it would be inefficeint in terms of db queries
    # TODO: Maybe build up data structure (effectively recreating BTIDES hierarchy?) and then print that?
    print_device_names(bdaddr, nametype)
    print_uuid16s(bdaddr)                               # Includes BTIDES export
    print_uuid16_service_data(bdaddr)                   # Includes BTIDES export
    print_uuid16s_service_solicit(bdaddr)
    print_uuid32s(bdaddr)                               # Includes BTIDES export
    print_uuid32_service_data(bdaddr)                   # Includes BTIDES export
    print_uuid128s(bdaddr)                              # Includes BTIDES export
    print_uuid128_service_data(bdaddr)                   # Includes BTIDES export
    print_uuid128s_service_solicit(bdaddr)
    print_transmit_power(bdaddr, nametype)              # Includes BTIDES export
    print_flags(bdaddr)                                 # Includes BTIDES export
    print_appearance(bdaddr, nametype)                  # Includes BTIDES export
    print_manufacturer_data(bdaddr)
    print_class_of_device(bdaddr)                       # Includes BTIDES export
