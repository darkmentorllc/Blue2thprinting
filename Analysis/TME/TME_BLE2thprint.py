########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

#import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_BTIDES_LL import *

########################################
# 2thprint_BLE Info
########################################

def phy_prefs_to_string(number):
    str = ""
    if((number & 0b00000001) != 0):
        str += "'LE 1M PHY' "
    if((number & 0b00000010) != 0):
        str += "'LE 2M PHY' "
    if((number & 0b00000100) != 0):
        str += "'LE Coded PHY' "
    if(str == ""):
        str = "Invalid. At least one PHY was supposed to be selected!"
    return str

def decode_BLE_features(features):
    if(features & (0b1 << 0x00)): print(f"\t\t\t\t* LE Encryption")
    if(features & (0b1 << 0x01)): print(f"\t\t\t\t* Connection Parameters Request Procedure")
    if(features & (0b1 << 0x02)): print(f"\t\t\t\t* Extended Reject Indication")
    if(features & (0b1 << 0x03)): print(f"\t\t\t\t* Peripheral-initiated Features Exchange")
    if(features & (0b1 << 0x04)): print(f"\t\t\t\t* LE Ping")
    if(features & (0b1 << 0x05)): print(f"\t\t\t\t* LE Data Packet Length Extension")
    if(features & (0b1 << 0x06)): print(f"\t\t\t\t* LL Privacy")
    if(features & (0b1 << 0x07)): print(f"\t\t\t\t* Extended Scanner Filter Policies")
    if(features & (0b1 << 0x08)): print(f"\t\t\t\t* LE 2M PHY")
    if(features & (0b1 << 0x09)): print(f"\t\t\t\tStable Modulation Index - Transmitter")
    if(features & (0b1 << 0x0a)): print(f"\t\t\t\tStable Modulation Index - Receiver")
    if(features & (0b1 << 0x0b)): print(f"\t\t\t\t* LE Coded PHY")
    if(features & (0b1 << 0x0c)): print(f"\t\t\t\t* LE Extended Advertising")
    if(features & (0b1 << 0x0d)): print(f"\t\t\t\t* LE Periodic Advertising")
    if(features & (0b1 << 0x0e)): print(f"\t\t\t\t* Channel Selection Algorithm #2")
    if(features & (0b1 << 0x0f)): print(f"\t\t\t\t* LE Power Class 1")
    if(features & (0b1 << 0x10)): print(f"\t\t\t\t* Minimum Number of Used Channels procedure")
    if(features & (0b1 << 0x11)): print(f"\t\t\t\t* Connection CTE Request")
    if(features & (0b1 << 0x12)): print(f"\t\t\t\t* Connection CTE Response")
    if(features & (0b1 << 0x13)): print(f"\t\t\t\t* Connectionless CTE Transmitter")
    if(features & (0b1 << 0x14)): print(f"\t\t\t\t* Connectionless CTE Receiver")
    if(features & (0b1 << 0x15)): print(f"\t\t\t\t* Antenna Switching During CTE Transmission AoD")
    if(features & (0b1 << 0x16)): print(f"\t\t\t\t* Antenna Switching During CTE Reception AoA")
    if(features & (0b1 << 0x17)): print(f"\t\t\t\t* Receiving Constant Tone Extensions")
    if(features & (0b1 << 0x18)): print(f"\t\t\t\t* Periodic Advertising Sync Transfer - Sender")
    if(features & (0b1 << 0x19)): print(f"\t\t\t\t* Periodic Advertising Sync Transfer - Recipient")
    if(features & (0b1 << 0x1a)): print(f"\t\t\t\t* Sleep Clock Accuracy Updates")
    if(features & (0b1 << 0x1b)): print(f"\t\t\t\t* Remote Public Key Validation")
    if(features & (0b1 << 0x1c)): print(f"\t\t\t\t* Connected Isochronous Stream - Central")
    if(features & (0b1 << 0x1d)): print(f"\t\t\t\t* Connected Isochronous Stream - Peripheral")
    if(features & (0b1 << 0x1e)): print(f"\t\t\t\t* Isochronous Broadcaster")
    if(features & (0b1 << 0x1f)): print(f"\t\t\t\t* Synchronized Receiver")
    if(features & (0b1 << 0x20)): print(f"\t\t\t\t* Connected Isophronous Stream (Host Support)")
    if(features & (0b1 << 0x21)): print(f"\t\t\t\t* LE Power Control Request")
    if(features & (0b1 << 0x22)): print(f"\t\t\t\t* LE Power Control Indication")
    if(features & (0b1 << 0x23)): print(f"\t\t\t\t* LE Path Loss Monitoring")
    if(features & (0b1 << 0x24)): print(f"\t\t\t\t* Periodic Advertising ADI support")
    if(features & (0b1 << 0x25)): print(f"\t\t\t\t* Connection Subrating")
    if(features & (0b1 << 0x26)): print(f"\t\t\t\t* Connection Subrating (Host Support)")
    if(features & (0b1 << 0x27)): print(f"\t\t\t\t* Channel Classification")
    if(features & (0b1 << 0x28)): print(f"\t\t\t\t* Advertising Coding Selection")
    if(features & (0b1 << 0x29)): print(f"\t\t\t\t* Advertising Coding Selection (Host Support)")
    # One bit gap according to spec 5.4
    if(features & (0b1 << 0x2b)): print(f"\t\t\t\t* Periodic Advertising with Responses - Advertiser")
    if(features & (0b1 << 0x2c)): print(f"\t\t\t\t* Periodic Advertising with Responses - Scanner")

def print_BLE_2thprint(bdaddr):
    bdaddr = bdaddr.strip().lower()

    version_query = f"SELECT ll_version, ll_sub_version, device_BT_CID FROM BLE2th_LL_VERSION_IND WHERE device_bdaddr = '{bdaddr}'"
    version_result = execute_query(version_query)

    features_query = f"SELECT device_bdaddr_type, opcode, features FROM BLE2th_LL_FEATUREs WHERE device_bdaddr = '{bdaddr}'"
    features_result = execute_query(features_query)

    phys_query = f"SELECT tx_phys, rx_phys FROM BLE2th_LL_PHYs WHERE device_bdaddr = '{bdaddr}'"
    phys_result = execute_query(phys_query)

    lengths_query = f"SELECT opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time FROM BLE2th_LL_LENGTHs WHERE device_bdaddr = '{bdaddr}'"
    lengths_result = execute_query(lengths_query)

    ping_query = f"SELECT device_bdaddr_type FROM BLE2th_LL_PING_RSP WHERE device_bdaddr = '{bdaddr}'"
    ping_result = execute_query(ping_query)

    unknown_query = f"SELECT device_bdaddr_type, unknown_opcode FROM BLE2th_LL_UNKNOWN_RSP WHERE device_bdaddr = '{bdaddr}'"
    unknown_result = execute_query(unknown_query)

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        print("\tBLE 2thprint Info:")

    ll_ctrl_pdu_opcodes = {9: "LL_FEATURE_RSP", 14: "LL_PERIPHERAL_FEATURE_REQ", 18: "LL_PING_REQ", 20: "LL_LENGTH_REQ", 21: "LL_LENGTH_RSP", 22: "LL_PHY_REQ", 23: "LL_PHY_RSP"}

    for ll_version, ll_sub_version, device_BT_CID in version_result:
        print(f"\t\tBT Version ({ll_version}): {get_bt_spec_version_numbers_to_names(ll_version)}")
        print("\t\tLL Sub-version: 0x%04x" % ll_sub_version)
        print(f"\t\tCompany ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for device_bdaddr_type, opcode, features in features_result:
        print(f"\t\tBLE LL Ctrl Opcode: {opcode} ({ll_ctrl_pdu_opcodes[opcode]})")
        print("\t\t\tBLE LL Features: 0x%016x" % features)
        decode_BLE_features(features)
        if(opcode == 8):
            BTIDES_export_LL_FEATURE_REQ(bdaddr, device_bdaddr_type, features)
        elif(opcode == 9):
            BTIDES_export_LL_FEATURE_RSP(bdaddr, device_bdaddr_type, features)
        elif(opcode == 14):
            BTIDES_export_LL_PERIPHERAL_FEATURE_REQ(bdaddr, device_bdaddr_type, features)

    for tx_phys, rx_phys in phys_result:
        print(f"\t\tSender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
        print(f"\t\tSender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")

    for opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
        print(f"\t\tLL Ctrl Opcode: {opcode} ({ll_ctrl_pdu_opcodes[opcode]})")
        print(f"\t\t\tMax RX octets: {max_rx_octets}")
        print(f"\t\t\tMax RX time: {max_rx_time} microseconds")
        print(f"\t\t\tMax TX octets: {max_tx_octets}")
        print(f"\t\t\tMax TX time: {max_tx_time} microseconds")

    for device_bdaddr_type, unknown_opcode in unknown_result:
        print(f"\t\tReturned 'Unknown Opcode' error for LL Ctrl Opcode: {unknown_opcode} ({ll_ctrl_pdu_opcodes[unknown_opcode]})")
        BTIDES_export_LL_UNKNOWN_RSP(bdaddr, device_bdaddr_type, unknown_opcode)

    for device_bdaddr_type, in ping_result:
        print(f"\t\tLL Ping Response Received")
        BTIDES_export_LL_PING_RSP(bdaddr, device_bdaddr_type)

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        print("\tRaw BLE 2thprint:")
        with open(f"./BLE2thprints/{bdaddr}.ble2thprint", 'w') as file:
            for ll_version, ll_sub_version, device_BT_CID in version_result:
                print(f"\t\t\"ll_version\",\"0x%02x\"" % ll_version)
                file.write(f"\"ll_version\",\"0x%02x\"\n" % ll_version)

                print("\t\t\"ll_sub_version\",\"0x%04x\"" % ll_sub_version)
                file.write("\"ll_sub_version\",\"0x%04x\"\n" % ll_sub_version)

                print(f"\t\t\"version_BT_CID\",\"0x%04x\"" % device_BT_CID)
                file.write(f"\"version_BT_CID\",\"0x%04x\"\n" % device_BT_CID)

            for device_bdaddr_type, opcode, features in features_result:
                print(f"\t\t\"ll_ctrl_opcode\",\"0x%02x\",\"features\",\"0x%016x\"" % (opcode, features))
                file.write(f"\"ll_ctrl_opcode\",\"0x%02x\",\"features\",\"0x%016x\"\n" % (opcode, features))

            for tx_phys, rx_phys in phys_result:
                print(f"\t\t\"tx_phys\",\"0x%02x\"" % tx_phys)
                file.write(f"\"tx_phys\",\"0x%02x\"\n" % tx_phys)
                print(f"\t\t\"rx_phys\",\"0x%02x\"" % rx_phys)
                file.write(f"\"rx_phys\",\"0x%02x\"\n" % rx_phys)

            for opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
                print(f"\t\t\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))
                file.write(f"\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"\n" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))

            for device_bdaddr_type, unknown_opcode in unknown_result:
                print(f"\t\t\"unknown_ll_ctrl_opcode\",\"0x%02x\"" % unknown_opcode)
                file.write(f"\"unknown_ll_ctrl_opcode\",\"0x%02x\"\n" % unknown_opcode)

            for ping_rsp in ping_result:
                print(f"\t\t\"ll_ping_rsp\",\"1\"")
                file.write(f"\"ll_ping_rsp\",\"1\"\n")



    if((len(version_result) == 0) and (len(features_result) == 0) and (len(phys_result) == 0) and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        print("\tNo BLE 2thprint Info found.")

    print("")