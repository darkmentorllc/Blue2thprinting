########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
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
    if(features & (0b1 << 0x00)): qprint(f"\t\t\t\t* LE Encryption")
    if(features & (0b1 << 0x01)): qprint(f"\t\t\t\t* Connection Parameters Request Procedure")
    if(features & (0b1 << 0x02)): qprint(f"\t\t\t\t* Extended Reject Indication")
    if(features & (0b1 << 0x03)): qprint(f"\t\t\t\t* Peripheral-initiated Features Exchange")
    if(features & (0b1 << 0x04)): qprint(f"\t\t\t\t* LE Ping")
    if(features & (0b1 << 0x05)): qprint(f"\t\t\t\t* LE Data Packet Length Extension")
    if(features & (0b1 << 0x06)): qprint(f"\t\t\t\t* LL Privacy")
    if(features & (0b1 << 0x07)): qprint(f"\t\t\t\t* Extended Scanner Filter Policies")
    if(features & (0b1 << 0x08)): qprint(f"\t\t\t\t* LE 2M PHY")
    if(features & (0b1 << 0x09)): qprint(f"\t\t\t\tStable Modulation Index - Transmitter")
    if(features & (0b1 << 0x0a)): qprint(f"\t\t\t\tStable Modulation Index - Receiver")
    if(features & (0b1 << 0x0b)): qprint(f"\t\t\t\t* LE Coded PHY")
    if(features & (0b1 << 0x0c)): qprint(f"\t\t\t\t* LE Extended Advertising")
    if(features & (0b1 << 0x0d)): qprint(f"\t\t\t\t* LE Periodic Advertising")
    if(features & (0b1 << 0x0e)): qprint(f"\t\t\t\t* Channel Selection Algorithm #2")
    if(features & (0b1 << 0x0f)): qprint(f"\t\t\t\t* LE Power Class 1")
    if(features & (0b1 << 0x10)): qprint(f"\t\t\t\t* Minimum Number of Used Channels procedure")
    if(features & (0b1 << 0x11)): qprint(f"\t\t\t\t* Connection CTE Request")
    if(features & (0b1 << 0x12)): qprint(f"\t\t\t\t* Connection CTE Response")
    if(features & (0b1 << 0x13)): qprint(f"\t\t\t\t* Connectionless CTE Transmitter")
    if(features & (0b1 << 0x14)): qprint(f"\t\t\t\t* Connectionless CTE Receiver")
    if(features & (0b1 << 0x15)): qprint(f"\t\t\t\t* Antenna Switching During CTE Transmission AoD")
    if(features & (0b1 << 0x16)): qprint(f"\t\t\t\t* Antenna Switching During CTE Reception AoA")
    if(features & (0b1 << 0x17)): qprint(f"\t\t\t\t* Receiving Constant Tone Extensions")
    if(features & (0b1 << 0x18)): qprint(f"\t\t\t\t* Periodic Advertising Sync Transfer - Sender")
    if(features & (0b1 << 0x19)): qprint(f"\t\t\t\t* Periodic Advertising Sync Transfer - Recipient")
    if(features & (0b1 << 0x1a)): qprint(f"\t\t\t\t* Sleep Clock Accuracy Updates")
    if(features & (0b1 << 0x1b)): qprint(f"\t\t\t\t* Remote Public Key Validation")
    if(features & (0b1 << 0x1c)): qprint(f"\t\t\t\t* Connected Isochronous Stream - Central")
    if(features & (0b1 << 0x1d)): qprint(f"\t\t\t\t* Connected Isochronous Stream - Peripheral")
    if(features & (0b1 << 0x1e)): qprint(f"\t\t\t\t* Isochronous Broadcaster")
    if(features & (0b1 << 0x1f)): qprint(f"\t\t\t\t* Synchronized Receiver")
    if(features & (0b1 << 0x20)): qprint(f"\t\t\t\t* Connected Isophronous Stream (Host Support)")
    if(features & (0b1 << 0x21)): qprint(f"\t\t\t\t* LE Power Control Request")
    if(features & (0b1 << 0x22)): qprint(f"\t\t\t\t* LE Power Control Indication")
    if(features & (0b1 << 0x23)): qprint(f"\t\t\t\t* LE Path Loss Monitoring")
    if(features & (0b1 << 0x24)): qprint(f"\t\t\t\t* Periodic Advertising ADI support")
    if(features & (0b1 << 0x25)): qprint(f"\t\t\t\t* Connection Subrating")
    if(features & (0b1 << 0x26)): qprint(f"\t\t\t\t* Connection Subrating (Host Support)")
    if(features & (0b1 << 0x27)): qprint(f"\t\t\t\t* Channel Classification")
    if(features & (0b1 << 0x28)): qprint(f"\t\t\t\t* Advertising Coding Selection")
    if(features & (0b1 << 0x29)): qprint(f"\t\t\t\t* Advertising Coding Selection (Host Support)")
    # One bit gap according to spec 5.4
    if(features & (0b1 << 0x2b)): qprint(f"\t\t\t\t* Periodic Advertising with Responses - Advertiser")
    if(features & (0b1 << 0x2c)): qprint(f"\t\t\t\t* Periodic Advertising with Responses - Scanner")

def print_BLE_2thprint(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)

    version_query = "SELECT ll_version, ll_sub_version, device_BT_CID FROM BLE2th_LL_VERSION_IND WHERE device_bdaddr = %s"
    version_result = execute_query(version_query, values)

    features_query = "SELECT device_bdaddr_type, opcode, features FROM BLE2th_LL_FEATUREs WHERE device_bdaddr = %s"
    features_result = execute_query(features_query, values)

    phys_query = "SELECT device_bdaddr_type, tx_phys, rx_phys FROM BLE2th_LL_PHYs WHERE device_bdaddr = %s"
    phys_result = execute_query(phys_query, values)

    lengths_query = "SELECT device_bdaddr_type, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time FROM BLE2th_LL_LENGTHs WHERE device_bdaddr = %s"
    lengths_result = execute_query(lengths_query, values)

    ping_query = "SELECT device_bdaddr_type FROM BLE2th_LL_PING_RSP WHERE device_bdaddr = %s"
    ping_result = execute_query(ping_query, values)

    unknown_query = "SELECT device_bdaddr_type, unknown_opcode FROM BLE2th_LL_UNKNOWN_RSP WHERE device_bdaddr = %s"
    unknown_result = execute_query(unknown_query, values)

    if((len(version_result) == 0) and (len(features_result) == 0) and (len(phys_result) == 0) and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        vprint("\tNo BLE 2thprint Info found.")
        return
    else:
        qprint("\tBLE 2thprint Info:")

    # FIXME: for now the direction in all my DB data is P2C, so I'm hardcoding it here, but this needs to be fixed in the future once the DB is updated
    direction = type_BTIDES_direction_P2C
    for ll_version, ll_sub_version, device_BT_CID in version_result:
        qprint(f"\t\tBT Version ({ll_version}): {get_bt_spec_version_numbers_to_names(ll_version)}")
        qprint("\t\tLL Sub-version: 0x%04x" % ll_sub_version)
        qprint(f"\t\tCompany ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for device_bdaddr_type, opcode, features in features_result:
        qprint(f"\t\tBLE LL Ctrl Opcode: {opcode} ({ll_ctrl_pdu_opcodes_to_strings[opcode]})")
        qprint("\t\t\tBLE LL Features: 0x%016x" % features)
        decode_BLE_features(features)
        data = ff_LL_FEATURE_RSP(direction, features)
        if(opcode == type_opcode_LL_FEATURE_REQ):
            BTIDES_export_LL_FEATURE_REQ(bdaddr=bdaddr, random=device_bdaddr_type, data=data)
        elif(opcode == type_opcode_LL_FEATURE_RSP):
            BTIDES_export_LL_FEATURE_RSP(bdaddr=bdaddr, random=device_bdaddr_type, data=data)
        elif(opcode == type_opcode_LL_PERIPHERAL_FEATURE_REQ):
            BTIDES_export_LL_PERIPHERAL_FEATURE_REQ(bdaddr=bdaddr, random=device_bdaddr_type, data=data)

    for device_bdaddr_type, tx_phys, rx_phys in phys_result:
        qprint(f"\t\tSender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
        qprint(f"\t\tSender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")
        data = ff_LL_PHY_RSP(direction, tx_phys, rx_phys)
        BTIDES_export_LL_PHY_RSP(bdaddr=bdaddr, random=device_bdaddr_type, data=data)

    for device_bdaddr_type, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
        qprint(f"\t\tLL Ctrl Opcode: {opcode} ({ll_ctrl_pdu_opcodes_to_strings[opcode]})")
        qprint(f"\t\t\tMax RX octets: {max_rx_octets}")
        qprint(f"\t\t\tMax RX time: {max_rx_time} microseconds")
        qprint(f"\t\t\tMax TX octets: {max_tx_octets}")
        qprint(f"\t\t\tMax TX time: {max_tx_time} microseconds")
        if(opcode == type_opcode_LL_LENGTH_REQ):
            data = ff_LL_LENGTH_REQ(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            BTIDES_export_LL_LENGTH_REQ(bdaddr=bdaddr, random=device_bdaddr_type, data=data)
        elif(opcode == type_opcode_LL_LENGTH_RSP):
            data = ff_LL_LENGTH_RSP(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            BTIDES_export_LL_LENGTH_RSP(bdaddr=bdaddr, random=device_bdaddr_type, data=data)

    for device_bdaddr_type, unknown_opcode in unknown_result:
        qprint(f"\t\tReturned 'Unknown Opcode' error for LL Ctrl Opcode: {unknown_opcode} ({ll_ctrl_pdu_opcodes_to_strings[unknown_opcode]})")
        data = ff_LL_UNKNOWN_RSP(direction, unknown_opcode)
        BTIDES_export_LL_UNKNOWN_RSP(bdaddr=bdaddr, random=device_bdaddr_type, data=data)

    for device_bdaddr_type, in ping_result:
        qprint(f"\t\tLL Ping Response Received")
        data = ff_LL_PING_RSP(direction)
        BTIDES_export_LL_PING_RSP(bdaddr=bdaddr, random=device_bdaddr_type, data=data)

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        qprint("\tRaw BLE 2thprint:")
        with open(f"./BLE2thprints/{bdaddr}.ble2thprint", 'w') as file:
            for ll_version, ll_sub_version, device_BT_CID in version_result:
                qprint(f"\t\t\"ll_version\",\"0x%02x\"" % ll_version)
                file.write(f"\"ll_version\",\"0x%02x\"\n" % ll_version)

                qprint("\t\t\"ll_sub_version\",\"0x%04x\"" % ll_sub_version)
                file.write("\"ll_sub_version\",\"0x%04x\"\n" % ll_sub_version)

                qprint(f"\t\t\"version_BT_CID\",\"0x%04x\"" % device_BT_CID)
                file.write(f"\"version_BT_CID\",\"0x%04x\"\n" % device_BT_CID)

            for device_bdaddr_type, opcode, features in features_result:
                qprint(f"\t\t\"ll_ctrl_opcode\",\"0x%02x\",\"features\",\"0x%016x\"" % (opcode, features))
                file.write(f"\"ll_ctrl_opcode\",\"0x%02x\",\"features\",\"0x%016x\"\n" % (opcode, features))

            for device_bdaddr_type, tx_phys, rx_phys in phys_result:
                qprint(f"\t\t\"tx_phys\",\"0x%02x\"" % tx_phys)
                file.write(f"\"tx_phys\",\"0x%02x\"\n" % tx_phys)
                qprint(f"\t\t\"rx_phys\",\"0x%02x\"" % rx_phys)
                file.write(f"\"rx_phys\",\"0x%02x\"\n" % rx_phys)

            for device_bdaddr_type, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
                qprint(f"\t\t\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))
                file.write(f"\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"\n" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))

            for device_bdaddr_type, unknown_opcode in unknown_result:
                qprint(f"\t\t\"unknown_ll_ctrl_opcode\",\"0x%02x\"" % unknown_opcode)
                file.write(f"\"unknown_ll_ctrl_opcode\",\"0x%02x\"\n" % unknown_opcode)

            for ping_rsp in ping_result:
                qprint(f"\t\t\"ll_ping_rsp\",\"1\"")
                file.write(f"\"ll_ping_rsp\",\"1\"\n")

    qprint("")