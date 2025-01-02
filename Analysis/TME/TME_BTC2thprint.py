########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_BTIDES_LMP import *
from TME.TME_BTIDES_HCI import *

########################################
# 2thprint_BTC Info
########################################

def decode_BTC_features(page, features):
    if(page == 0):
        if(features & (0b1 << 0x00)): qprint(f"\t\t\t* 3 slot packets")
        if(features & (0b1 << 0x01)): qprint(f"\t\t\t* 5 slot packets")
        if(features & (0b1 << 0x02)): qprint(f"\t\t\t* Encryption")
        if(features & (0b1 << 0x03)): qprint(f"\t\t\t* Slot offset")
        if(features & (0b1 << 0x04)): qprint(f"\t\t\t* Timing accuracy")
        if(features & (0b1 << 0x05)): qprint(f"\t\t\t* Role switch")
        if(features & (0b1 << 0x06)): qprint(f"\t\t\t* Hold mode")
        if(features & (0b1 << 0x07)): qprint(f"\t\t\t* Sniff mode")
        if(features & (0b1 << 0x08)): qprint(f"\t\t\t* Previously used")
        if(features & (0b1 << 0x09)): qprint(f"\t\t\t* Power control requests")
        if(features & (0b1 << 0x0a)): qprint(f"\t\t\t* Channel quality driven data rate (CQDDR)")
        if(features & (0b1 << 0x0b)): qprint(f"\t\t\t* SCO link")
        if(features & (0b1 << 0x0c)): qprint(f"\t\t\t* HV2 packets")
        if(features & (0b1 << 0x0d)): qprint(f"\t\t\t* HV3 packets")
        if(features & (0b1 << 0x0e)): qprint(f"\t\t\t* μ-law log synchronous data")
        if(features & (0b1 << 0x0f)): qprint(f"\t\t\t* A-law log synchronous data")
        if(features & (0b1 << 0x10)): qprint(f"\t\t\t* CVSD synchronous data")
        if(features & (0b1 << 0x11)): qprint(f"\t\t\t* Paging parameter negotiation")
        if(features & (0b1 << 0x12)): qprint(f"\t\t\t* Power control")
        if(features & (0b1 << 0x13)): qprint(f"\t\t\t* Transparent synchronous data")
        if(features & (0b1 << 0x14)): qprint(f"\t\t\t* Flow control lag (least significant bit)")
        if(features & (0b1 << 0x15)): qprint(f"\t\t\t* Flow control lag (middle bit)")
        if(features & (0b1 << 0x16)): qprint(f"\t\t\t* Flow control lag (most significant bit)")
        if(features & (0b1 << 0x17)): qprint(f"\t\t\t* Broadcast Encryption")
        if(features & (0b1 << 0x18)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x19)): qprint(f"\t\t\t* Enhanced Data Rate ACL 2 Mb/s mode")
        if(features & (0b1 << 0x1a)): qprint(f"\t\t\t* Enhanced Data Rate ACL 3 Mb/s mode")
        if(features & (0b1 << 0x1b)): qprint(f"\t\t\t* Enhanced inquiry scan (see note)")
        if(features & (0b1 << 0x1c)): qprint(f"\t\t\t* Interlaced inquiry scan")
        if(features & (0b1 << 0x1d)): qprint(f"\t\t\t* Interlaced page scan")
        if(features & (0b1 << 0x1e)): qprint(f"\t\t\t* RSSI with inquiry results")
        if(features & (0b1 << 0x1f)): qprint(f"\t\t\t* Extended SCO link (EV3 packets)")
        if(features & (0b1 << 0x20)): qprint(f"\t\t\t* EV4 packets")
        if(features & (0b1 << 0x21)): qprint(f"\t\t\t* EV5 packets")
        if(features & (0b1 << 0x22)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x23)): qprint(f"\t\t\t* AFH capable Peripheral")
        if(features & (0b1 << 0x24)): qprint(f"\t\t\t* AFH classification Peripheral")
        if(features & (0b1 << 0x25)): qprint(f"\t\t\t* BR/EDR Not Supported")
        if(features & (0b1 << 0x26)): qprint(f"\t\t\t* LE Supported (Controller)")
        if(features & (0b1 << 0x27)): qprint(f"\t\t\t* 3-slot Enhanced Data Rate ACL packets")
        if(features & (0b1 << 0x28)): qprint(f"\t\t\t* 5-slot Enhanced Data Rate ACL packets")
        if(features & (0b1 << 0x29)): qprint(f"\t\t\t* Sniff subrating")
        if(features & (0b1 << 0x2a)): qprint(f"\t\t\t* Pause encryption")
        if(features & (0b1 << 0x2b)): qprint(f"\t\t\t* AFH capable Central")
        if(features & (0b1 << 0x2c)): qprint(f"\t\t\t* AFH classification Central")
        if(features & (0b1 << 0x2d)): qprint(f"\t\t\t* Enhanced Data Rate eSCO 2 Mb/s mode")
        if(features & (0b1 << 0x2e)): qprint(f"\t\t\t* Enhanced Data Rate eSCO 3 Mb/s mode")
        if(features & (0b1 << 0x2f)): qprint(f"\t\t\t* 3-slot Enhanced Data Rate eSCO packets")
        if(features & (0b1 << 0x30)): qprint(f"\t\t\t* Extended Inquiry Response")
        if(features & (0b1 << 0x31)): qprint(f"\t\t\t* Simultaneous LE and BR/EDR to Same Device Capable (Controller)")
        if(features & (0b1 << 0x32)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x33)): qprint(f"\t\t\t* Secure Simple Pairing (Controller Support)")
        if(features & (0b1 << 0x34)): qprint(f"\t\t\t* Encapsulated PDU")
        if(features & (0b1 << 0x35)): qprint(f"\t\t\t* Erroneous Data Reporting")
        if(features & (0b1 << 0x36)): qprint(f"\t\t\t* Non-flushable Packet Boundary Flag")
        if(features & (0b1 << 0x37)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x38)): qprint(f"\t\t\t* HCI_Link_Supervision_Timeout_Changed event")
        if(features & (0b1 << 0x39)): qprint(f"\t\t\t* Variable Inquiry TX Power Level")
        if(features & (0b1 << 0x3a)): qprint(f"\t\t\t* Enhanced Power Control")
        if(features & (0b1 << 0x3b)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3c)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3d)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3e)): qprint(f"\t\t\t* Reserved for future use")
        if(features & (0b1 << 0x3f)): qprint(f"\t\t\t* Extended features")

def print_BTC_2thprint(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)

    version_query = "SELECT lmp_version, lmp_sub_version, device_BT_CID FROM BTC2th_LMP_version_res WHERE device_bdaddr = %s"
    version_result = execute_query(version_query, values)

    features_query = "SELECT page, features FROM BTC2th_LMP_features_res WHERE device_bdaddr = %s"
    features_result = execute_query(features_query, values)

    name_query = "SELECT device_name FROM BTC2th_LMP_name_res WHERE device_bdaddr = %s"
    name_result = execute_query(name_query, values)

    if((len(version_result) == 0) and (len(features_result) == 0) and (len(name_result) == 0)): # and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        vprint("\tNo BTC 2thprint Info found.")
        return
    else:
        qprint("\tBTC 2thprint Info:")

    for lmp_version, lmp_sub_version, device_BT_CID in version_result:
        qprint(f"\t\tBT Version ({lmp_version}): {get_bt_spec_version_numbers_to_names(lmp_version)}")
        qprint("\t\tLMP Sub-version: 0x%04x" % lmp_sub_version)
        qprint(f"\t\tCompany ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for page, features in features_result:
        qprint("\t\tBTC LMP Features: 0x%016x" % features)
        decode_BTC_features(page, features)
        BTIDES_export_LMP_FEATURES_RSP(bdaddr, features)

    for (device_name,) in name_result:
        qprint(f"\t\tBTC LMP Name Response: {device_name}")
        find_nameprint_match(device_name)
        # I'm using this for now because it's a better fit for the db data, since it's not actually individual LMP_NAME_RSP fragments (it's defragmented)
        BTIDES_export_HCI_Name_Response(bdaddr, device_name)

    if(len(version_result) != 0 or len(features_result) != 0 or len(name_result) != 0): # or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        qprint("\n\tRaw BTC 2thprint:")
        with open(f"./BTC2thprints/{bdaddr}.btc2thprint", 'w') as file:
            for lmp_version, lmp_sub_version, device_BT_CID in version_result:
                qprint(f"\t\t\"lmp_version\",\"0x%02x\"" % lmp_version)
                file.write(f"\"lmp_version\",\"0x%02x\"\n" % lmp_version)
                qprint("\t\t\"lmp_sub_version\",\"0x%04x\"" % lmp_sub_version)
                file.write("\"lmp_sub_version\",\"0x%04x\"\n" % lmp_sub_version)
                qprint(f"\t\t\"version_BT_CID\",\"0x%04x\"" % device_BT_CID)
                file.write(f"\"version_BT_CID\",\"0x%04x\"\n" % device_BT_CID)

            for page, features in features_result:
                qprint("\t\t\"features\",\"0x%016x\"" % features)
                file.write("\"features\",\"0x%016x\"\n" % features)

    qprint("")