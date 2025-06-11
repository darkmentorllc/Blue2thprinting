########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

#import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_BTIDES_LLCP import *

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
    indent = "\t\t\t\t"
    if(features & (0b1 << 0x00)): qprint(f"{indent}* LE Encryption")
    if(features & (0b1 << 0x01)): qprint(f"{indent}* Connection Parameters Request Procedure")
    if(features & (0b1 << 0x02)): qprint(f"{indent}* Extended Reject Indication")
    if(features & (0b1 << 0x03)): qprint(f"{indent}* Peripheral-initiated Features Exchange")
    if(features & (0b1 << 0x04)): qprint(f"{indent}* LE Ping")
    if(features & (0b1 << 0x05)): qprint(f"{indent}* LE Data Packet Length Extension")
    if(features & (0b1 << 0x06)): qprint(f"{indent}* LL Privacy")
    if(features & (0b1 << 0x07)): qprint(f"{indent}* Extended Scanner Filter Policies")
    if(features & (0b1 << 0x08)): qprint(f"{indent}* LE 2M PHY")
    if(features & (0b1 << 0x09)): qprint(f"{indent}* Stable Modulation Index - Transmitter")
    if(features & (0b1 << 0x0a)): qprint(f"{indent}* Stable Modulation Index - Receiver")
    if(features & (0b1 << 0x0b)): qprint(f"{indent}* LE Coded PHY")
    if(features & (0b1 << 0x0c)): qprint(f"{indent}* LE Extended Advertising")
    if(features & (0b1 << 0x0d)): qprint(f"{indent}* LE Periodic Advertising")
    if(features & (0b1 << 0x0e)): qprint(f"{indent}* Channel Selection Algorithm #2")
    if(features & (0b1 << 0x0f)): qprint(f"{indent}* LE Power Class 1")
    if(features & (0b1 << 0x10)): qprint(f"{indent}* Minimum Number of Used Channels procedure")
    if(features & (0b1 << 0x11)): qprint(f"{indent}* Connection CTE Request")
    if(features & (0b1 << 0x12)): qprint(f"{indent}* Connection CTE Response")
    if(features & (0b1 << 0x13)): qprint(f"{indent}* Connectionless CTE Transmitter")
    if(features & (0b1 << 0x14)): qprint(f"{indent}* Connectionless CTE Receiver")
    if(features & (0b1 << 0x15)): qprint(f"{indent}* Antenna Switching During CTE Transmission AoD")
    if(features & (0b1 << 0x16)): qprint(f"{indent}* Antenna Switching During CTE Reception AoA")
    if(features & (0b1 << 0x17)): qprint(f"{indent}* Receiving Constant Tone Extensions")
    if(features & (0b1 << 0x18)): qprint(f"{indent}* Periodic Advertising Sync Transfer - Sender")
    if(features & (0b1 << 0x19)): qprint(f"{indent}* Periodic Advertising Sync Transfer - Recipient")
    if(features & (0b1 << 0x1a)): qprint(f"{indent}* Sleep Clock Accuracy Updates")
    if(features & (0b1 << 0x1b)): qprint(f"{indent}* Remote Public Key Validation")
    if(features & (0b1 << 0x1c)): qprint(f"{indent}* Connected Isochronous Stream - Central")
    if(features & (0b1 << 0x1d)): qprint(f"{indent}* Connected Isochronous Stream - Peripheral")
    if(features & (0b1 << 0x1e)): qprint(f"{indent}* Isochronous Broadcaster")
    if(features & (0b1 << 0x1f)): qprint(f"{indent}* Synchronized Receiver")
    if(features & (0b1 << 0x20)): qprint(f"{indent}* Connected Isochronous Stream (Host Support)")
    if(features & (0b1 << 0x21)): qprint(f"{indent}* LE Power Control Request")
    if(features & (0b1 << 0x22)): qprint(f"{indent}* LE Power Control Indication")
    if(features & (0b1 << 0x23)): qprint(f"{indent}* LE Path Loss Monitoring")
    if(features & (0b1 << 0x24)): qprint(f"{indent}* Periodic Advertising ADI support")
    if(features & (0b1 << 0x25)): qprint(f"{indent}* Connection Subrating")
    if(features & (0b1 << 0x26)): qprint(f"{indent}* Connection Subrating (Host Support)")
    if(features & (0b1 << 0x27)): qprint(f"{indent}* Channel Classification")
    if(features & (0b1 << 0x28)): qprint(f"{indent}* Advertising Coding Selection")
    if(features & (0b1 << 0x29)): qprint(f"{indent}* Advertising Coding Selection (Host Support)")
    # One bit gap according to spec 5.4
    if(features & (0b1 << 0x2b)): qprint(f"{indent}* Periodic Advertising with Responses - Advertiser")
    if(features & (0b1 << 0x2c)): qprint(f"{indent}* Periodic Advertising with Responses - Scanner")

def print_LLCP_info(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)

    version_query = "SELECT ll_version, ll_sub_version, device_BT_CID FROM LL_VERSION_IND WHERE bdaddr = %s"
    version_result = execute_query(version_query, values)

    features_query = "SELECT bdaddr_random, opcode, features FROM LL_FEATUREs WHERE bdaddr = %s"
    features_result = execute_query(features_query, values)

    phys_query = "SELECT bdaddr_random, opcode, tx_phys, rx_phys FROM LL_PHYs WHERE bdaddr = %s"
    phys_result = execute_query(phys_query, values)

    lengths_query = "SELECT bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time FROM LL_LENGTHs WHERE bdaddr = %s"
    lengths_result = execute_query(lengths_query, values)

    ping_query = "SELECT bdaddr_random, opcode FROM LL_PINGs WHERE bdaddr = %s"
    ping_result = execute_query(ping_query, values)

    unknown_query = "SELECT bdaddr_random, unknown_opcode FROM LL_UNKNOWN_RSP WHERE bdaddr = %s"
    unknown_result = execute_query(unknown_query, values)

    if((len(version_result) == 0) and (len(features_result) == 0) and (len(phys_result) == 0) and (len(lengths_result) == 0) and (len(ping_result) == 0) and (len(unknown_result) == 0)):
        vprint("\tNo LL Control Protocol info found.")
        return
    else:
        qprint("\tLL Control Protocol info:")

    indent = "\t\t"
    # FIXME: for now the direction in all my DB data is P2C, so I'm hardcoding it here, but this needs to be fixed in the future once the DB is updated
    direction = type_BTIDES_direction_P2C
    for ll_version, ll_sub_version, device_BT_CID in version_result:
        qprint(f"{indent}LLCP opcode 0x0C: {ll_ctrl_pdu_opcodes_to_strings[0x0C]}")
        qprint(f"{indent}\tBT Version ({ll_version}): {get_bt_spec_version_numbers_to_names(ll_version)}")
        qprint(f"{indent}\tLL Sub-version: 0x{ll_sub_version:04x}")
        qprint(f"{indent}\tCompany ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for bdaddr_random, opcode, features in features_result:
        qprint(f"{indent}LLCP opcode 0x{opcode:02X}: {ll_ctrl_pdu_opcodes_to_strings[opcode]}")
        qprint(f"{indent}\tBLE LL Features: 0x{features:016x}")
        decode_BLE_features(features)
        data = ff_LL_FEATURE_RSP(direction, features)
        if(opcode == type_LL_FEATURE_REQ):
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_FEATURE_RSP):
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_PERIPHERAL_FEATURE_REQ):
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, opcode, tx_phys, rx_phys in phys_result:
        if(opcode == type_LL_PHY_RSP):
            qprint(f"{indent}Sender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
            qprint(f"{indent}Sender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")
            data = ff_LL_PHY_RSP(direction, tx_phys, rx_phys)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_PHY_REQ):
            qprint(f"{indent}Sender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
            qprint(f"{indent}Sender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")
            data = ff_LL_PHY_REQ(direction, tx_phys, rx_phys)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
        qprint(f"{indent}LLCP opcode 0x{opcode:02X}: {ll_ctrl_pdu_opcodes_to_strings[opcode]}")
        qprint(f"{indent}\tMax RX octets: {max_rx_octets}")
        qprint(f"{indent}\tMax RX time: {max_rx_time} microseconds")
        qprint(f"{indent}\tMax TX octets: {max_tx_octets}")
        qprint(f"{indent}\tMax TX time: {max_tx_time} microseconds")
        if(opcode == type_LL_LENGTH_REQ):
            data = ff_LL_LENGTH_REQ(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_LENGTH_RSP):
            data = ff_LL_LENGTH_RSP(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, unknown_opcode in unknown_result:
        qprint(f"{indent}Returned 'Unknown Opcode' error for LL Ctrl Opcode: {unknown_opcode} ({ll_ctrl_pdu_opcodes_to_strings[unknown_opcode]})")
        data = ff_LL_UNKNOWN_RSP(direction, unknown_opcode)
        BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, opcode in ping_result:
        if(opcode == type_LL_PING_RSP):
            qprint(f"{indent}Central received LL Ping Response from this device.")
            data = ff_LL_PING_RSP(direction)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_PING_REQ):
            qprint(f"{indent}Central received LL Ping Request from this device.")
            data = ff_LL_PING_REQ(direction)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        vprint("\tRaw LLCP info:")
        for ll_version, ll_sub_version, device_BT_CID in version_result:
            vprint(f"{indent}\"LL_VERSION_IND:ll_version\",\"0x%02x\"" % ll_version)

            vprint("\t\t\"LL_VERSION_IND:ll_sub_version\",\"0x%04x\"" % ll_sub_version)

            vprint(f"{indent}\"LL_VERSION_IND:version_BT_CID\",\"0x%04x\"" % device_BT_CID)

        for bdaddr_random, opcode, features in features_result:
            vprint(f"{indent}\"LL_FEATURE* opcode\",\"0x%02x\",\"features\",\"0x%016x\"" % (opcode, features))

        for bdaddr_random, opcode, tx_phys, rx_phys in phys_result:
            if(opcode == type_LL_PHY_RSP):
                vprint(f"{indent}\"LL_PHY_RSP:tx_phys\",\"0x%02x\"" % tx_phys)
                vprint(f"{indent}\"LL_PHY_RSP:rx_phys\",\"0x%02x\"" % rx_phys)
            elif(opcode == type_LL_PHY_REQ):
                vprint(f"{indent}\"LL_PHY_REQ:tx_phys\",\"0x%02x\"" % tx_phys)
                vprint(f"{indent}\"LL_PHY_REQ:rx_phys\",\"0x%02x\"" % rx_phys)

        for bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
            vprint(f"{indent}\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))

        for bdaddr_random, unknown_opcode in unknown_result:
            vprint(f"{indent}\"LL_UNKNOWN_RSP to opcode\",\"0x%02x\"" % unknown_opcode)

        for bdaddr_random, opcode in ping_result:
            if(opcode == type_LL_PING_RSP):
                vprint(f"{indent}\"LL_PING_RSP\",\"P2C\"")
            elif(opcode == type_LL_PING_REQ):
                vprint(f"{indent}\"LL_PING_REQ\",\"P2C\"")
    qprint("")