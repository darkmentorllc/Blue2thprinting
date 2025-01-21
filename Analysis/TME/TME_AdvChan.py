########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

import struct
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_helpers import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_UUID16 import *
from TME.TME_UUID32 import *
from TME.TME_UUID128 import *
from TME.TME_EIR import *

#####################################################
# CONNECT_IND (which is in the Advertisement Channel)
#####################################################

def ff_CONNECT_IND(central_bdaddr="00:00:00:00:00:00", central_bdaddr_rand=0, peripheral_bdaddr="00:00:00:00:00:00", peripheral_bdaddr_rand=0, access_address=0, crc_init_hex_str="112233", win_size=0, win_offset=0, interval=0, latency=0, timeout=0, channel_map_hex_str="FFFFFFFF1F", hop=0, SCA=0):
    connect_ind_obj = {
        "central_bdaddr": central_bdaddr,
        "central_bdaddr_rand": central_bdaddr_rand,
        "peripheral_bdaddr": peripheral_bdaddr,
        "peripheral_bdaddr_rand": peripheral_bdaddr_rand,
        "access_address": access_address,
        "crc_init_hex_str": crc_init_hex_str,
        "win_size": win_size,
        "win_offset": win_offset,
        "interval": interval,
        "latency": latency,
        "timeout": timeout,
        "channel_map_hex_str": channel_map_hex_str,
        "hop": hop,
        "SCA": SCA
    }
    return connect_ind_obj

def ff_CONNECT_IND_placeholder():
    return ff_CONNECT_IND(
        central_bdaddr="00:00:00:00:00:00",
        central_bdaddr_rand=0,
        peripheral_bdaddr="00:00:00:00:00:00",
        peripheral_bdaddr_rand=0,
        access_address=0,
        crc_init_hex_str="112233",
        win_size=0,
        win_offset=0,
        interval=0,
        latency=0,
        timeout=0,
        channel_map_hex_str="FFFFFFFF1F",
        hop=0,
        SCA=0
    )

########################################
# Transmit Power
########################################

def print_transmit_power(bdaddr, nametype):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    eir_query = "SELECT device_tx_power FROM EIR_bdaddr_to_tx_power WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)
#    le_query = "SELECT device_tx_power, bdaddr_random, le_evt_type FROM LE_bdaddr_to_tx_power WHERE bdaddr = %s AND bdaddr_random = {nametype}"
    le_query = "SELECT device_tx_power, bdaddr_random, le_evt_type FROM LE_bdaddr_to_tx_power WHERE bdaddr = %s" # I think I prefer without the nametype, to always return more info
    le_result = execute_query(le_query, values)

    if (len(eir_result)== 0 and len(le_result) == 0):
        vprint("\tNo transmit power found.")
        return

    for (device_tx_power,) in eir_result:
        qprint(f"\tTransmit Power: {device_tx_power}dB")
        vprint(f"\t\tIn BT Classic Data (EIR_bdaddr_to_tx_power)")

        data = {"length": 2, "tx_power": device_tx_power}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_TxPower, data)

    for device_tx_power, random, le_evt_type in le_result:
        qprint(f"\tTransmit Power: {device_tx_power}dB")
        vprint(f"\t\tIn BT LE Data (LE_bdaddr_to_tx_power), bdaddr_random = {random} ({get_bdaddr_type(bdaddr, random)})")
        qprint(f"\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

        data = {"length": 2, "tx_power": device_tx_power}
        BTIDES_export_AdvData(bdaddr, random, le_evt_type, type_AdvData_TxPower, data)

    qprint("")

########################################
# Flags
########################################

def print_flags(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    eir_query = "SELECT le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host FROM EIR_bdaddr_to_flags WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)
    le_query = "SELECT bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host FROM LE_bdaddr_to_flags WHERE bdaddr = %s"
    le_result = execute_query(le_query, values)

    if (len(eir_result) == 0 and len(le_result) == 0):
        vprint("\tNo flags found.")
        return
    else:
        qprint("\tFlags found:")

    for (le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) in eir_result:
        qprint(f"\tIn BT Classic Data (EIR_bdaddr_to_flags)")
        qprint(f"\t\tBLE Limited Discoverable Mode: {le_limited_discoverable_mode}")
        qprint(f"\t\tBLE General Discoverable Mode: {le_general_discoverable_mode}")
        qprint(f"\t\tBR/EDR Not Supported: {bredr_not_supported}")
        qprint(f"\t\tSimultaneous BLE and BR/EDR Supported by Controller: {le_bredr_support_controller}")
        qprint(f"\t\tSimultaneous BLE and BR/EDR Supported by Host: {le_bredr_support_controller}")

        flags_hex_str = get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
        data = {"length": 2, "flags_hex_str": flags_hex_str}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_Flags, data)

    for (bdaddr_random, le_evt_type, le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host) in le_result:
        qprint(f"\tIn BLE Data (LE_bdaddr_to_flags)")
        qprint(f"\t\tBLE Limited Discoverable Mode: {le_limited_discoverable_mode}")
        qprint(f"\t\tBLE General Discoverable Mode: {le_general_discoverable_mode}")
        qprint(f"\t\tBR/EDR Not Supported: {bredr_not_supported}")
        qprint(f"\t\tSimultaneous BLE and BR/EDR Supported by Controller: {le_bredr_support_controller}")
        qprint(f"\t\tSimultaneous BLE and BR/EDR Supported by Host: {le_bredr_support_controller}")

        flags_hex_str = get_flags_hex_str(le_limited_discoverable_mode, le_general_discoverable_mode, bredr_not_supported, le_bredr_support_controller, le_bredr_support_host)
        data = {"length": 2, "flags_hex_str": flags_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_Flags, data)

    qprint("")

########################################
# URI
########################################

uri_scheme_prefixes = {
    0x00: "invalid:",
    0x01: '',
    0x02: 'aaa:',
    0x03: 'aaas:',
    0x04: 'about:',
    0x05: 'acap:',
    0x06: 'acct:',
    0x07: 'cap:',
    0x08: 'cid:',
    0x09: 'coap:',
    0x0A: 'coaps:',
    0x0B: 'crid:',
    0x0C: 'data:',
    0x0D: 'dav:',
    0x0E: 'dict:',
    0x0F: 'dns:',
    0x10: 'file:',
    0x11: 'ftp:',
    0x12: 'geo:',
    0x13: 'go:',
    0x14: 'gopher:',
    0x15: 'h323:',
    0x16: 'http:',
    0x17: 'https:',
    0x18: 'iax:',
    0x19: 'icap:',
    0x1A: 'im:',
    0x1B: 'imap:',
    0x1C: 'info:',
    0x1D: 'ipp:',
    0x1E: 'ipps:',
    0x1F: 'iris:',
    0x20: 'iris.beep:',
    0x21: 'iris.xpc:',
    0x22: 'iris.xpcs:',
    0x23: 'iris.lwz:',
    0x24: 'jabber:',
    0x25: 'ldap:',
    0x26: 'mailto:',
    0x27: 'mid:',
    0x28: 'msrp:',
    0x29: 'msrps:',
    0x2A: 'mtqp:',
    0x2B: 'mupdate:',
    0x2C: 'news:',
    0x2D: 'nfs:',
    0x2E: 'ni:',
    0x2F: 'nih:',
    0x30: 'nntp:',
    0x31: 'opaquelocktoken:',
    0x32: 'pop:',
    0x33: 'pres:',
    0x34: 'reload:',
    0x35: 'rtsp:',
    0x36: 'rtsps:',
    0x37: 'rtspu:',
    0x38: 'service:',
    0x39: 'session:',
    0x3A: 'shttp:',
    0x3B: 'sieve:',
    0x3C: 'sip:',
    0x3D: 'sips:',
    0x3E: 'sms:',
    0x3F: 'snmp:',
    0x40: 'soap.beep:',
    0x41: 'soap.beeps:',
    0x42: 'stun:',
    0x43: 'stuns:',
    0x44: 'tag:',
    0x45: 'tel:',
    0x46: 'telnet:',
    0x47: 'tftp:',
    0x48: 'thismessage:',
    0x49: 'tn3270:',
    0x4A: 'tip:',
    0x4B: 'turn:',
    0x4C: 'turns:',
    0x4D: 'tv:',
    0x4E: 'urn:',
    0x4F: 'vemmi:',
    0x50: 'ws:',
    0x51: 'wss:',
    0x52: 'xcon:',
    0x53: 'xconuserid:',
    0x54: 'xmlrpc.beep:',
    0x55: 'xmlrpc.beeps:',
    0x56: 'xmpp:',
    0x57: 'z39.50r:',
    0x58: 'z39.50s:',
    0x59: 'acr:',
    0x5A: 'adiumxtra:',
    0x5B: 'afp:',
    0x5C: 'afs:',
    0x5D: 'aim:',
    0x5E: 'apt:',
    0x5F: 'attachment:',
    0x60: 'aw:',
    0x61: 'barion:',
    0x62: 'beshare:',
    0x63: 'bitcoin:',
    0x64: 'bolo:',
    0x65: 'callto:',
    0x66: 'chrome:',
    0x67: 'chromeextension:',
    0x68: 'comeventbriteattendee:',
    0x69: 'content:',
    0x6A: 'cvs:',
    0x6B: 'dlnaplaysingle:',
    0x6C: 'dlnaplaycontainer:',
    0x6D: 'dtn:',
    0x6E: 'dvb:',
    0x6F: 'ed2k:',
    0x70: 'facetime:',
    0x71: 'feed:',
    0x72: 'feedready:',
    0x73: 'finger:',
    0x74: 'fish:',
    0x75: 'gg:',
    0x76: 'git:',
    0x77: 'gizmoproject:',
    0x78: 'gtalk:',
    0x79: 'ham:',
    0x7A: 'hcp:',
    0x7B: 'icon:',
    0x7C: 'ipn:',
    0x7D: 'irc:',
    0x7E: 'irc6:',
    0x7F: 'ircs:',
    0x80: 'itms:',
    0x81: 'jar:',
    0x82: 'jms:',
    0x83: 'keyparc:',
    0x84: 'lastfm:',
    0x85: 'ldaps:',
    0x86: 'magnet:',
    0x87: 'maps:',
    0x88: 'market:',
    0x89: 'message:',
    0x8A: 'mms:',
    0x8B: 'mshelp:',
    0x8C: 'mssettingspower:',
    0x8D: 'msnim:',
    0x8E: 'mumble:',
    0x8F: 'mvn:',
    0x90: 'notes:',
    0x91: 'oid:',
    0x92: 'palm:',
    0x93: 'paparazzi:',
    0x94: 'pkcs11:',
    0x95: 'platform:',
    0x96: 'proxy:',
    0x97: 'psyc:',
    0x98: 'query:',
    0x99: 'res:',
    0x9A: 'resource:',
    0x9B: 'rmi:',
    0x9C: 'rsync:',
    0x9D: 'rtmfp:',
    0x9E: 'rtmp:',
    0x9F: 'secondlife:',
    0xA0: 'sftp:',
    0xA1: 'sgn:',
    0xA2: 'skype:',
    0xA3: 'smb:',
    0xA4: 'smtp:',
    0xA5: 'soldat:',
    0xA6: 'spotify:',
    0xA7: 'ssh:',
    0xA8: 'steam:',
    0xA9: 'submit:',
    0xAA: 'svn:',
    0xAB: 'teamspeak:',
    0xAC: 'teliaeid:',
    0xAD: 'things:',
    0xAE: 'udp:',
    0xAF: 'unreal:',
    0xB0: 'ut2004:',
    0xB1: 'ventrilo:',
    0xB2: 'viewsource:',
    0xB3: 'webcal:',
    0xB4: 'wtai:',
    0xB5: 'wyciwyg:',
    0xB6: 'xfire:',
    0xB7: 'xri:',
    0xB8: 'ymsgr:',
    0xB9: 'example:',
    0xBA: 'mss-ettings-cloudstorage:'
}

def print_URI(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    le_query = "SELECT bdaddr_random, le_evt_type, URI_hex_str FROM LE_bdaddr_to_URI WHERE bdaddr = %s"
    le_result = execute_query(le_query, values)

    if (len(le_result) == 0):
        vprint("\tNo URI found.")
        return
    else:
        qprint("\tURI found:")

    for (bdaddr_random, le_evt_type, URI_hex_str) in le_result:

        type_part = int(URI_hex_str[0:2], 16)
        if(type_part == 0):
            # Print hex bytes out still for the invalid case, just to show what kind of invalid data it has
            uri_str = uri_scheme_prefixes[type_part] + URI_hex_str[2:]
        else:
            uri_part = bytes.fromhex(URI_hex_str[2:]).decode('utf-8')
            uri_str = uri_scheme_prefixes[type_part] + uri_part

        qprint(f"\t\tURI: {uri_str}")
        qprint(f"\t\tIn BLE Data (LE_bdaddr_to_URI)")

        # Export to BTIDES
        length = int(len(URI_hex_str) / 2)
        data = {"length": length, "URI_hex_str": URI_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_URI, data)

    qprint("")

########################################
# Manufacturer-specific Data
########################################

# Data format from https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair
def extract_ms_msd_name(manufacturer_specific_data):
    utf8_string = ""
    if(manufacturer_specific_data[0:6] == "030080" and len(manufacturer_specific_data) >= 8): # (need at least 8 hex digits for there to be 1 hex digit of ASCII chars)
        byte_data = bytes.fromhex(manufacturer_specific_data[6:])
        utf8_string = byte_data.decode('utf-8', 'ignore')
    if(manufacturer_specific_data[0:6] == "030280" and len(manufacturer_specific_data) >= 14): # ditto ^^^ 14
        byte_data = bytes.fromhex(manufacturer_specific_data[12:])
        utf8_string = byte_data.decode('utf-8', 'ignore')
    if(manufacturer_specific_data[0:6] == "030180" and len(manufacturer_specific_data) >= 26): # ditto ^^^ 26
        byte_data = bytes.fromhex(manufacturer_specific_data[24:])
        utf8_string = byte_data.decode('utf-8', 'ignore')

    if(len(utf8_string) > 0):
        return utf8_string
    else:
        return "No name found"

def print_manufacturer_data(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    eir_query = "SELECT device_BT_CID, manufacturer_specific_data FROM EIR_bdaddr_to_MSD WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)
    le_query = "SELECT le_evt_type, bdaddr_random, device_BT_CID, manufacturer_specific_data FROM LE_bdaddr_to_MSD WHERE bdaddr = %s"
    le_result = execute_query(le_query, values)

    if (len(eir_result)== 0 and len(le_result) == 0):
        vprint("\tNo Manufacturer-specific Data found.")
        return
    elif (len(eir_result) != 0 or len(le_result) != 0):
        qprint("\tManufacturer-specific Data:")

    for device_BT_CID, manufacturer_specific_data in eir_result:
        qprint(f"\t\tDevice Company ID: 0x%04x (%s) - take with a grain of salt, not all companies populate this accurately!" % (device_BT_CID, BT_CID_to_company_name(device_BT_CID)))
        flipped_endian = (device_BT_CID & 0xFF) << 8 | (device_BT_CID >> 8)
        qprint(f"\t\t\t Endianness-flipped device company ID (in case the vendor used the wrong endianness): 0x%04x (%s)" % (flipped_endian, BT_CID_to_company_name(flipped_endian)))
        qprint(f"\t\tRaw Data: {manufacturer_specific_data}")
        # TODO: DELETEME? I don't think there can be BT classic iBeacons can there?
        if({BT_CID_to_company_name(device_BT_CID)} == "Apple, Inc." and manufacturer_specific_data[0:3] == "0215"):
            qprint(f"\t\tApple iBeacon:")
        vprint(f"\t\t\tIn BT Classic Data (EIR_bdaddr_to_MSD)")

    for le_evt_type, bdaddr_random, device_BT_CID, manufacturer_specific_data in le_result:
        qprint(f"\t\tDevice Company ID: 0x%04x (%s) - take with a grain of salt, not all companies populate this accurately!" % (device_BT_CID, BT_CID_to_company_name(device_BT_CID)))
        flipped_endian = (device_BT_CID & 0xFF) << 8 | (device_BT_CID >> 8)
        qprint(f"\t\t\t Endianness-flipped device company ID (in case the vendor used the wrong endianness): 0x%04x (%s)" % (flipped_endian, BT_CID_to_company_name(flipped_endian)))
        qprint(f"\t\tRaw Data: {manufacturer_specific_data}")

        # Print Apple iBeacon information
        if(device_BT_CID == 76 and manufacturer_specific_data[0:4] == "0215"):
            qprint(f"\t\tApple iBeacon:")
            UUID128 = f"{manufacturer_specific_data[4:12]}-{manufacturer_specific_data[12:16]}-{manufacturer_specific_data[16:20]}-{manufacturer_specific_data[20:24]}-{manufacturer_specific_data[24:36]}"
            major = f"{manufacturer_specific_data[36:40]}"
            minor = f"{manufacturer_specific_data[40:44]}"
            rssi = f"{manufacturer_specific_data[44:46]}"
            qprint(f"\t\t\tUUID128: {UUID128}")
            qprint(f"\t\t\tMajor ID: {major}")
            qprint(f"\t\t\tMinor ID: {minor}")
            signed_rssi = int(rssi, 16)
            if(signed_rssi & 0x80):
                signed_rssi -= 256
            qprint(f"\t\t\tRSSI at 1 meter: {signed_rssi}dBm")

        elif(device_BT_CID == 6):
            # Print Microsoft Swift Pair information (format from https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/bluetooth-swift-pair)
            if(manufacturer_specific_data[0:6] == "030080"): # "Pairing over LE only"
                qprint(f"\t\tMicrosoft Swift Pair - \"Pairing over LE only\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                qprint(f"\t\t\tDisplayName = {utf8_string}")
            if(manufacturer_specific_data[0:6] == "030280"): # "Pairing over LE and BR/EDR with Secure Connections"
                qprint(f"\t\tMicrosoft Swift Pair - \"Pairing over LE and BR/EDR with Secure Connections\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                qprint(f"\t\t\tDisplayName = {utf8_string}")
                CoD_bytes = bytes.fromhex(manufacturer_specific_data[6:12])
                big_endian_integer_CoD = struct.unpack('>I', b'\x00' + CoD_bytes)[0]
                print_CoD_to_names(big_endian_integer_CoD)
            if(manufacturer_specific_data[0:6] == "030180"): # "Pairing over BR/EDR only, using Bluetooth LE for discovery"
                qprint(f"\t\tMicrosoft Swift Pair - \"Pairing over BR/EDR only, using Bluetooth LE for discovery\"")
                utf8_string = extract_ms_msd_name(manufacturer_specific_data)
                qprint(f"\t\t\tDisplayName = {utf8_string}")
                CoD_bytes = bytes.fromhex(manufacturer_specific_data[18:24])
                big_endian_integer_CoD = struct.unpack('>I', b'\x00' + CoD_bytes)[0]
                print_CoD_to_names(big_endian_integer_CoD)
                BTC_BDADDR_bytes = bytes.fromhex(manufacturer_specific_data[6:18])
                BTC_BDADDR_str = f"{BTC_BDADDR_bytes[5]:02x}:{BTC_BDADDR_bytes[4]:02x}:{BTC_BDADDR_bytes[3]:02x}:{BTC_BDADDR_bytes[2]:02x}:{BTC_BDADDR_bytes[1]:02x}:{BTC_BDADDR_bytes[0]:02x}"
                qprint(f"\t\t\tBluetooth Classic BDADDR embedded in MSD = {BTC_BDADDR_str}")
                print_company_name_from_bdaddr("\t\t\t\t", BTC_BDADDR_str, False)
            # Print other Microsoft beacon information (format from https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cdp/77b446d0-8cea-4821-ad21-fabdf4d9a569)
            if(manufacturer_specific_data[0:2] == "01"):
                qprint(f"\t\tMicrosoft Beacon:")
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
                qprint(f"\t\t\tDevice Type = {device_types[device_type]}")
                Version_and_Flags = int(manufacturer_specific_data[4:6], 16)
                if(Version_and_Flags == 0x20):
                    share_state = "only my devices"
                elif(Version_and_Flags == 0x21):
                    share_state = "everyone"
                else:
                    share_state = "Unknown value: check for specification update!"
                qprint(f"\t\t\tNearBy share set to: {share_state}")
                # The values observed in the wild for Flags_and_Device_Status only make sense if you assume the MS spec has the bit ordering reversed and bit 0 is right-most not left-most
                Flags_and_Device_Status = int(manufacturer_specific_data[6:8], 16)
                Bluetooth_Address_As_Device_ID = True if((Flags_and_Device_Status >> 5) & 1) else False
                qprint(f"\t\t\tBluetooth address can be used as the device ID?: {Bluetooth_Address_As_Device_ID}")
                ExtendedDeviceStatus = Flags_and_Device_Status & 0xf
                # per spec "Values may be ORed"
                if(ExtendedDeviceStatus & 0x1):
                    qprint(f"\t\t\tExtended Status: Hosted by remote session")
                if(ExtendedDeviceStatus & 0x2):
                    qprint(f"\t\t\tExtended Status: The device does not have session hosting status available")
                if(ExtendedDeviceStatus & 0x4):
                    qprint(f"\t\t\tExtended Status: The device supports NearShare if the user is the same for the other device")
                if(ExtendedDeviceStatus & 0x8):
                    qprint(f"\t\t\tExtended Status: The device supports NearShare")
                if(ExtendedDeviceStatus == 0):
                    qprint(f"\t\t\tExtended Status: None")
                Salt_bytes = bytes.fromhex(manufacturer_specific_data[8:16])
                big_endian_integer_Salt = struct.unpack('<I', Salt_bytes)[0] # Salt is ostensibly stored little-endian, but without knowing a "Device Thumbprint" to calculate the Device Hash I can't be sure
                qprint(f"\t\t\tSalt: 0x{big_endian_integer_Salt:08x}")
                #Device_Hash_bytes = bytes.fromhex(manufacturer_specific_data[16:])
                qprint(f"\t\t\tDevice Hash: {manufacturer_specific_data[16:]}")
                # Non-spec interpretation based on observed data: I see 2 bytes and then a string
                # This seems to only occur if(ExtendedDeviceStatus & 0x8). Found some if(ExtendedDeviceStatus & 0x4), data and confirmed it doesn't occur then
                if(ExtendedDeviceStatus & 0x8):
                    try:
                        Device_Hash_as_utf8_str = bytes.fromhex(manufacturer_specific_data[20:]).decode('utf-8')
                        qprint(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as possible string: {Device_Hash_as_utf8_str}")
                        Device_Hash_unknown_bytes = bytes.fromhex(manufacturer_specific_data[16:20])
                        Device_Hash_unknown_bytes_little_endian_short = struct.unpack('<H', Device_Hash_unknown_bytes)[0]
                        qprint(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as possible string: unknown prefix bytes interpreted as little-endian 16-bit value: 0x{Device_Hash_unknown_bytes_little_endian_short:04x}")
                    except:
                        qprint(f"\t\t\t\tNon-spec interpretation of 'Device Hash' as string: does not decode")


        # TODO: Does this have the necessary information to parse Amazon MSD? https://developer.amazon.com/en-US/docs/alexa/alexa-gadgets-toolkit/bluetooth-le-settings.html
        # TODO: Parse Eddystone even though it's deprecated?

        qprint(f"\t\t\tIn BT LE Data (LE_bdaddr_to_MSD), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        qprint(f"\t\t\tThis was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Changing up the formatting to print all the AdvData underneath whatever advertisement/scan response it originally appeared in
def print_all_advdata(bdaddr, nametype):
    # TODO: Ideally I want to have information grouped by the source packet type it came in on
    # TODO: But looping through and printing only the information for a single type at a time seem like it would be inefficient in terms of db queries
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
    print_PSRM(bdaddr)                                  # Includes BTIDES export
    print_URI(bdaddr)                                  # Includes BTIDES export
