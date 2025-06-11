########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_BTIDES_LLCP import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# LLCP Info
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
    if(features & (0b1 << 0x00)): qprint(f"{i2}* LE Encryption")
    if(features & (0b1 << 0x01)): qprint(f"{i2}* Connection Parameters Request Procedure")
    if(features & (0b1 << 0x02)): qprint(f"{i2}* Extended Reject Indication")
    if(features & (0b1 << 0x03)): qprint(f"{i2}* Peripheral-initiated Features Exchange")
    if(features & (0b1 << 0x04)): qprint(f"{i2}* LE Ping")
    if(features & (0b1 << 0x05)): qprint(f"{i2}* LE Data Packet Length Extension")
    if(features & (0b1 << 0x06)): qprint(f"{i2}* LL Privacy")
    if(features & (0b1 << 0x07)): qprint(f"{i2}* Extended Scanner Filter Policies")
    if(features & (0b1 << 0x08)): qprint(f"{i2}* LE 2M PHY")
    if(features & (0b1 << 0x09)): qprint(f"{i2}* Stable Modulation Index - Transmitter")
    if(features & (0b1 << 0x0a)): qprint(f"{i2}* Stable Modulation Index - Receiver")
    if(features & (0b1 << 0x0b)): qprint(f"{i2}* LE Coded PHY")
    if(features & (0b1 << 0x0c)): qprint(f"{i2}* LE Extended Advertising")
    if(features & (0b1 << 0x0d)): qprint(f"{i2}* LE Periodic Advertising")
    if(features & (0b1 << 0x0e)): qprint(f"{i2}* Channel Selection Algorithm #2")
    if(features & (0b1 << 0x0f)): qprint(f"{i2}* LE Power Class 1")
    if(features & (0b1 << 0x10)): qprint(f"{i2}* Minimum Number of Used Channels procedure")
    if(features & (0b1 << 0x11)): qprint(f"{i2}* Connection CTE Request")
    if(features & (0b1 << 0x12)): qprint(f"{i2}* Connection CTE Response")
    if(features & (0b1 << 0x13)): qprint(f"{i2}* Connectionless CTE Transmitter")
    if(features & (0b1 << 0x14)): qprint(f"{i2}* Connectionless CTE Receiver")
    if(features & (0b1 << 0x15)): qprint(f"{i2}* Antenna Switching During CTE Transmission AoD")
    if(features & (0b1 << 0x16)): qprint(f"{i2}* Antenna Switching During CTE Reception AoA")
    if(features & (0b1 << 0x17)): qprint(f"{i2}* Receiving Constant Tone Extensions")
    if(features & (0b1 << 0x18)): qprint(f"{i2}* Periodic Advertising Sync Transfer - Sender")
    if(features & (0b1 << 0x19)): qprint(f"{i2}* Periodic Advertising Sync Transfer - Recipient")
    if(features & (0b1 << 0x1a)): qprint(f"{i2}* Sleep Clock Accuracy Updates")
    if(features & (0b1 << 0x1b)): qprint(f"{i2}* Remote Public Key Validation")
    if(features & (0b1 << 0x1c)): qprint(f"{i2}* Connected Isochronous Stream - Central")
    if(features & (0b1 << 0x1d)): qprint(f"{i2}* Connected Isochronous Stream - Peripheral")
    if(features & (0b1 << 0x1e)): qprint(f"{i2}* Isochronous Broadcaster")
    if(features & (0b1 << 0x1f)): qprint(f"{i2}* Synchronized Receiver")
    if(features & (0b1 << 0x20)): qprint(f"{i2}* Connected Isochronous Stream (Host Support)")
    if(features & (0b1 << 0x21)): qprint(f"{i2}* LE Power Control Request")
    if(features & (0b1 << 0x22)): qprint(f"{i2}* LE Power Control Indication")
    if(features & (0b1 << 0x23)): qprint(f"{i2}* LE Path Loss Monitoring")
    if(features & (0b1 << 0x24)): qprint(f"{i2}* Periodic Advertising ADI support")
    if(features & (0b1 << 0x25)): qprint(f"{i2}* Connection Subrating")
    if(features & (0b1 << 0x26)): qprint(f"{i2}* Connection Subrating (Host Support)")
    if(features & (0b1 << 0x27)): qprint(f"{i2}* Channel Classification")
    if(features & (0b1 << 0x28)): qprint(f"{i2}* Advertising Coding Selection")
    if(features & (0b1 << 0x29)): qprint(f"{i2}* Advertising Coding Selection (Host Support)")
    # One bit gap according to spec 5.4
    if(features & (0b1 << 0x2b)): qprint(f"{i2}* Periodic Advertising with Responses - Advertiser")
    if(features & (0b1 << 0x2c)): qprint(f"{i2}* Periodic Advertising with Responses - Scanner")

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
        vprint(f"{i1}No LL Control Protocol info found.")
        return
    else:
        qprint(f"{i1}LL Control Protocol info:")

    # FIXME: for now the direction in all my DB data is P2C, so I'm hardcoding it here, but this needs to be fixed in the future once the DB is updated
    direction = type_BTIDES_direction_P2C
    for ll_version, ll_sub_version, device_BT_CID in version_result:
        qprint(f"{i2}LLCP opcode 0x0C: {ll_ctrl_pdu_opcodes_to_strings[0x0C]}")
        qprint(f"{i3}BT Version ({ll_version}): {get_bt_spec_version_numbers_to_names(ll_version)}")
        qprint(f"{i3}LL Sub-version: 0x{ll_sub_version:04x}")
        qprint(f"{i3}Company ID: {device_BT_CID} ({BT_CID_to_company_name(device_BT_CID)})")

    for bdaddr_random, opcode, features in features_result:
        qprint(f"{i2}LLCP opcode 0x{opcode:02X}: {ll_ctrl_pdu_opcodes_to_strings[opcode]}")
        qprint(f"{i3}BLE LL Features: 0x{features:016x}")
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
            qprint(f"{i2}Sender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
            qprint(f"{i2}Sender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")
            data = ff_LL_PHY_RSP(direction, tx_phys, rx_phys)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_PHY_REQ):
            qprint(f"{i2}Sender TX PHY Preference: {tx_phys} ({phy_prefs_to_string(tx_phys)})")
            qprint(f"{i2}Sender RX PHY Preference: {rx_phys} ({phy_prefs_to_string(rx_phys)})")
            data = ff_LL_PHY_REQ(direction, tx_phys, rx_phys)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
        qprint(f"{i2}LLCP opcode 0x{opcode:02X}: {ll_ctrl_pdu_opcodes_to_strings[opcode]}")
        qprint(f"{i3}Max RX octets: {max_rx_octets}")
        qprint(f"{i3}Max RX time: {max_rx_time} microseconds")
        qprint(f"{i3}Max TX octets: {max_tx_octets}")
        qprint(f"{i3}Max TX time: {max_tx_time} microseconds")
        if(opcode == type_LL_LENGTH_REQ):
            data = ff_LL_LENGTH_REQ(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_LENGTH_RSP):
            data = ff_LL_LENGTH_RSP(direction, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, unknown_opcode in unknown_result:
        qprint(f"{i2}Returned 'Unknown Opcode' error for LL Ctrl Opcode: {unknown_opcode} ({ll_ctrl_pdu_opcodes_to_strings[unknown_opcode]})")
        data = ff_LL_UNKNOWN_RSP(direction, unknown_opcode)
        BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    for bdaddr_random, opcode in ping_result:
        if(opcode == type_LL_PING_RSP):
            qprint(f"{i2}Central received LL Ping Response from this device.")
            data = ff_LL_PING_RSP(direction)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)
        elif(opcode == type_LL_PING_REQ):
            qprint(f"{i2}Central received LL Ping Request from this device.")
            data = ff_LL_PING_REQ(direction)
            BTIDES_export_LLArray_entry(bdaddr=bdaddr, random=bdaddr_random, data=data)

    if(len(version_result) != 0 or len(features_result) != 0 or len(phys_result) != 0 or len(lengths_result) != 0 or len(ping_result) != 0 or len(unknown_result) != 0):
        vprint(f"{i1}Raw LLCP info:")
        for ll_version, ll_sub_version, device_BT_CID in version_result:
            vprint(f"{i2}\"LL_VERSION_IND:ll_version\",\"0x%02x\"" % ll_version)

            vprint(f"{i2}\"LL_VERSION_IND:ll_sub_version\",\"0x%04x\"" % ll_sub_version)

            vprint(f"{i2}\"LL_VERSION_IND:version_BT_CID\",\"0x%04x\"" % device_BT_CID)

        for bdaddr_random, opcode, features in features_result:
            vprint(f"{i2}\"LL_FEATURE* opcode\",\"0x%02x\",\"features\",\"0x%016x\"" % (opcode, features))

        for bdaddr_random, opcode, tx_phys, rx_phys in phys_result:
            if(opcode == type_LL_PHY_RSP):
                vprint(f"{i2}\"LL_PHY_RSP:tx_phys\",\"0x%02x\"" % tx_phys)
                vprint(f"{i2}\"LL_PHY_RSP:rx_phys\",\"0x%02x\"" % rx_phys)
            elif(opcode == type_LL_PHY_REQ):
                vprint(f"{i2}\"LL_PHY_REQ:tx_phys\",\"0x%02x\"" % tx_phys)
                vprint(f"{i2}\"LL_PHY_REQ:rx_phys\",\"0x%02x\"" % rx_phys)

        for bdaddr_random, opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time in lengths_result:
            vprint(f"{i2}\"ll_ctrl_opcode\",\"0x%02x\",\"max_rx_octets\",\"0x%04x\",\"max_rx_time\",\"0x%04x\",\"max_tx_octets\",\"0x%04x\",\"max_tx_time\",\"0x%04x\"" % (opcode, max_rx_octets, max_rx_time, max_tx_octets, max_tx_time))

        for bdaddr_random, unknown_opcode in unknown_result:
            vprint(f"{i2}\"LL_UNKNOWN_RSP to opcode\",\"0x%02x\"" % unknown_opcode)

        for bdaddr_random, opcode in ping_result:
            if(opcode == type_LL_PING_RSP):
                vprint(f"{i2}\"LL_PING_RSP\",\"P2C\"")
            elif(opcode == type_LL_PING_REQ):
                vprint(f"{i2}\"LL_PING_REQ\",\"P2C\"")
    qprint("")