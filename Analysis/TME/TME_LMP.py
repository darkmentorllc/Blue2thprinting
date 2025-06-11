########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_BTIDES_LMP import *
from TME.TME_BTIDES_HCI import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# LMP Info
########################################

def decode_BTC_features(page, features, indent):
    if(page == 0):
        if(features & (0b1 << 0x00)): qprint(f"{indent}* 3 slot packets")
        if(features & (0b1 << 0x01)): qprint(f"{indent}* 5 slot packets")
        if(features & (0b1 << 0x02)): qprint(f"{indent}* Encryption")
        if(features & (0b1 << 0x03)): qprint(f"{indent}* Slot offset")
        if(features & (0b1 << 0x04)): qprint(f"{indent}* Timing accuracy")
        if(features & (0b1 << 0x05)): qprint(f"{indent}* Role switch")
        if(features & (0b1 << 0x06)): qprint(f"{indent}* Hold mode")
        if(features & (0b1 << 0x07)): qprint(f"{indent}* Sniff mode")
        if(features & (0b1 << 0x08)): qprint(f"{indent}* Previously used")
        if(features & (0b1 << 0x09)): qprint(f"{indent}* Power control requests")
        if(features & (0b1 << 0x0a)): qprint(f"{indent}* Channel quality driven data rate (CQDDR)")
        if(features & (0b1 << 0x0b)): qprint(f"{indent}* SCO link")
        if(features & (0b1 << 0x0c)): qprint(f"{indent}* HV2 packets")
        if(features & (0b1 << 0x0d)): qprint(f"{indent}* HV3 packets")
        if(features & (0b1 << 0x0e)): qprint(f"{indent}* μ-law log synchronous data")
        if(features & (0b1 << 0x0f)): qprint(f"{indent}* A-law log synchronous data")
        if(features & (0b1 << 0x10)): qprint(f"{indent}* CVSD synchronous data")
        if(features & (0b1 << 0x11)): qprint(f"{indent}* Paging parameter negotiation")
        if(features & (0b1 << 0x12)): qprint(f"{indent}* Power control")
        if(features & (0b1 << 0x13)): qprint(f"{indent}* Transparent synchronous data")
        if(features & (0b1 << 0x14)): qprint(f"{indent}* Flow control lag (least significant bit)")
        if(features & (0b1 << 0x15)): qprint(f"{indent}* Flow control lag (middle bit)")
        if(features & (0b1 << 0x16)): qprint(f"{indent}* Flow control lag (most significant bit)")
        if(features & (0b1 << 0x17)): qprint(f"{indent}* Broadcast Encryption")
        if(features & (0b1 << 0x18)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x19)): qprint(f"{indent}* Enhanced Data Rate ACL 2 Mb/s mode")
        if(features & (0b1 << 0x1a)): qprint(f"{indent}* Enhanced Data Rate ACL 3 Mb/s mode")
        if(features & (0b1 << 0x1b)): qprint(f"{indent}* Enhanced inquiry scan (see note)")
        if(features & (0b1 << 0x1c)): qprint(f"{indent}* Interlaced inquiry scan")
        if(features & (0b1 << 0x1d)): qprint(f"{indent}* Interlaced page scan")
        if(features & (0b1 << 0x1e)): qprint(f"{indent}* RSSI with inquiry results")
        if(features & (0b1 << 0x1f)): qprint(f"{indent}* Extended SCO link (EV3 packets)")
        if(features & (0b1 << 0x20)): qprint(f"{indent}* EV4 packets")
        if(features & (0b1 << 0x21)): qprint(f"{indent}* EV5 packets")
        if(features & (0b1 << 0x22)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x23)): qprint(f"{indent}* AFH capable Peripheral")
        if(features & (0b1 << 0x24)): qprint(f"{indent}* AFH classification Peripheral")
        if(features & (0b1 << 0x25)): qprint(f"{indent}* BR/EDR Not Supported")
        if(features & (0b1 << 0x26)): qprint(f"{indent}* LE Supported (Controller)")
        if(features & (0b1 << 0x27)): qprint(f"{indent}* 3-slot Enhanced Data Rate ACL packets")
        if(features & (0b1 << 0x28)): qprint(f"{indent}* 5-slot Enhanced Data Rate ACL packets")
        if(features & (0b1 << 0x29)): qprint(f"{indent}* Sniff subrating")
        if(features & (0b1 << 0x2a)): qprint(f"{indent}* Pause encryption")
        if(features & (0b1 << 0x2b)): qprint(f"{indent}* AFH capable Central")
        if(features & (0b1 << 0x2c)): qprint(f"{indent}* AFH classification Central")
        if(features & (0b1 << 0x2d)): qprint(f"{indent}* Enhanced Data Rate eSCO 2 Mb/s mode")
        if(features & (0b1 << 0x2e)): qprint(f"{indent}* Enhanced Data Rate eSCO 3 Mb/s mode")
        if(features & (0b1 << 0x2f)): qprint(f"{indent}* 3-slot Enhanced Data Rate eSCO packets")
        if(features & (0b1 << 0x30)): qprint(f"{indent}* Extended Inquiry Response")
        if(features & (0b1 << 0x31)): qprint(f"{indent}* Simultaneous LE and BR/EDR to Same Device Capable (Controller)")
        if(features & (0b1 << 0x32)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x33)): qprint(f"{indent}* Secure Simple Pairing (Controller Support)")
        if(features & (0b1 << 0x34)): qprint(f"{indent}* Encapsulated PDU")
        if(features & (0b1 << 0x35)): qprint(f"{indent}* Erroneous Data Reporting")
        if(features & (0b1 << 0x36)): qprint(f"{indent}* Non-flushable Packet Boundary Flag")
        if(features & (0b1 << 0x37)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x38)): qprint(f"{indent}* HCI_Link_Supervision_Timeout_Changed event")
        if(features & (0b1 << 0x39)): qprint(f"{indent}* Variable Inquiry TX Power Level")
        if(features & (0b1 << 0x3a)): qprint(f"{indent}* Enhanced Power Control")
        if(features & (0b1 << 0x3b)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x3c)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x3d)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x3e)): qprint(f"{indent}* Reserved for future use")
        if(features & (0b1 << 0x3f)): qprint(f"{indent}* Extended features")

def print_LMP_info(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    version_query = "SELECT lmp_version, lmp_sub_version, device_BT_CID FROM LMP_VERSION_RES WHERE bdaddr = %s"
    version_result = execute_query(version_query, values)

    features_query = "SELECT page, features FROM LMP_FEATURES_RES WHERE bdaddr = %s"
    features_result = execute_query(features_query, values)

    name_query = "SELECT device_name FROM LMP_NAME_RES WHERE bdaddr = %s"
    name_result = execute_query(name_query, values)

    if((len(version_result) == 0) and (len(features_result) == 0) and (len(name_result) == 0)): # and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        vprint(f"{i1}No BTC LMP Info found.")
        return
    else:
        qprint(f"{i1}BTC LMP Info:")

    for lmp_version, lmp_sub_version, device_BT_CID in version_result:
        qprint(f"{i2}BTC LMP version response:")
        qprint(f"{i3}Version ({lmp_version}): {get_bt_spec_version_numbers_to_names(lmp_version)}")
        qprint(f"{i3}Sub-version: 0x{lmp_sub_version:04x}")
        qprint(f"{i3}Company ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for page, features in features_result:
        qprint(f"{i2}BTC LMP Features: 0x{features:016x}")
        decode_BTC_features(page, features, f"{i3}")
        BTIDES_export_LMP_FEATURES_RES(bdaddr, features)

    for (device_name,) in name_result:
        qprint(f"{i2}BTC LMP Name Response: {device_name}")
        find_nameprint_match(device_name)
        # I'm using this for now because it's a better fit for the db data, since it's not actually individual LMP_NAME_RES fragments (it's defragmented)
        remote_name_hex_str = device_name
        BTIDES_export_HCI_Name_Response(bdaddr, remote_name_hex_str)

    if(len(version_result) != 0 or len(features_result) != 0 or len(name_result) != 0): # or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        vprint("\n\tRaw BTC LMP info:")
        for lmp_version, lmp_sub_version, device_BT_CID in version_result:
            vprint(f"{i2}\"lmp_version\",\"0x{lmp_version:02x}\"")
            vprint(f"{i2}\"lmp_sub_version\",\"0x{lmp_sub_version:04x}\"")
            vprint(f"{i2}\"version_BT_CID\",\"0x{device_BT_CID:04x}\"")

        for page, features in features_result:
            vprint(f"{i2}\"features\",\"0x{features:016x}\"")

    qprint("")