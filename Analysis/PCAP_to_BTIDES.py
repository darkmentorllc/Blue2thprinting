########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# Activate venv before any other imports
from handle_venv import activate_venv
activate_venv()
import argparse

# Scapy related
from scapy.layers.bluetooth4LE import *
from scapy.layers.bluetooth import *
from scapy.all import *

# Common code for BTIDES export assuming scapy formatted input data structures
from scapy_to_BTIDES_common import *

# BTIDALPOOL access related
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql
from BTIDES_to_BTIDALPOOL import send_btides_to_btidalpool

# BTIDES format related
from TME.TME_helpers import qprint, vprint
from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
import TME.TME_glob
from TME.TME_BTIDES_base import write_BTIDES, insert_std_optional_fields
# Advertisement Channel
from scapy_to_BTIDES_common import *
from TME.TME_AdvChan import *
# LL Control
from TME.TME_BTIDES_LL import *
# ATT
from TME.TME_BTIDES_ATT import *
# GATT
from TME.TME_BTIDES_GATT import *

g_access_address_to_connect_ind_obj = {}

def export_AdvChannelData(packet, scapy_type, adv_type):
    ble_adv_fields = packet.getlayer(BTLE_ADV)
    bdaddr_random = ble_adv_fields.TxAdd

    # Access the BTLE_ADV layer
    btle_adv = packet.getlayer(scapy_type)
    bdaddr = btle_adv.AdvA

    data_exported = False
    for entry in btle_adv.data:
        if export_AdvData(bdaddr, bdaddr_random, adv_type, entry):
            data_exported = True

    if(data_exported or (adv_type == type_AdvChanPDU_SCAN_RSP and len(btle_adv.data) == 0)):
        return True
    else:
        return False

# A global map of access addresses for which we have seen a LL_START_ENC_REQ
# and for which therefore all subsequent packets will be encrypted garbage
# which we shouldn't export, even if they look valid.
# TODO: In the future handle LL_PAUSE_ENC_REQ to remove from this,
# TODO: but I don't know if I've ever seen that packet in any of my pcaps.
g_stop_exporting_encrypted_packets_by_AA = {}

def export_BTLE_CTRL(packet):
    global g_stop_exporting_encrypted_packets_by_AA

    # Handle different LL Control packet types here
    # For example, LL_VERSION_IND
    ll_ctrl = packet.getlayer(BTLE_CTRL)

    btle_hdr = packet.getlayer(BTLE)
    access_address = btle_hdr.access_addr
    # *Usually* ignore subsequent packets if we've seen an LL_ENC_RSP/LL_START_ENC_REQ in this connection already
    if(access_address in g_stop_exporting_encrypted_packets_by_AA.keys()):
        if(ll_ctrl.opcode == type_opcode_LL_START_ENC_REQ):
            # We somtimes miss this packet, so we're now setting g_stop_exporting_encrypted_packets_by_AA earlier
            # This is just to let us to continue to capture the LL_START_ENC_REQ to the BTIDES file
            pass
        elif(ll_ctrl.opcode == type_opcode_LL_START_ENC_RSP):
            # LL_START_ENC_RSP is normally sent back encrypted by the Peripheral
            # If we see this, it means we're operating on a decrypted pcap,
            # so we can continue to proceed with exporting packets
            # NOTE: there is a small chance of false positives here due to encrypted data
            # decoding as a LL_START_ENC_RSP. But there's not a lot of harm if that occurs
            # If you want to avoid that entirely, you can remove this check.
            g_stop_exporting_encrypted_packets_by_AA[access_address] = False
        else:
            return True

    if access_address in g_access_address_to_connect_ind_obj:
        connect_ind_obj = g_access_address_to_connect_ind_obj[access_address]
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    if ll_ctrl.opcode == type_opcode_LL_CONNECTION_UPDATE_IND:
        try:
            data = ff_LL_CONNECTION_UPDATE_IND(
                direction=get_packet_direction(packet),
                win_size=ll_ctrl.win_size,
                win_offset=ll_ctrl.win_offset,
                interval=ll_ctrl.interval,
                latency=ll_ctrl.latency,
                timeout=ll_ctrl.timeout,
                instant=ll_ctrl.instant
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_CONNECTION_UPDATE_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_CHANNEL_MAP_IND:
        try:
            channel_map_hex_str = f"{ll_ctrl.chM:010x}" # ll_ctrl.chM stored as QWORD, but it's only 5 bytes, so pad to up to 10 zeros
            data = ff_LL_CHANNEL_MAP_IND(
                direction=get_packet_direction(packet),
                channel_map_hex_str=channel_map_hex_str,
                instant=ll_ctrl.instant
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_CHANNEL_MAP_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_TERMINATE_IND:
        try:
            data = ff_LL_TERMINATE_IND(
                direction=get_packet_direction(packet),
                error_code=ll_ctrl.code
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_TERMINATE_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_ENC_REQ:
        try:
            data = ff_LL_ENC_REQ(
                direction=get_packet_direction(packet),
                rand=ll_ctrl.rand,
                ediv=ll_ctrl.ediv,
                skd_c=ll_ctrl.skdm,
                iv_c=ll_ctrl.ivm
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_ENC_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_ENC_RSP:
        try:
            # LL_START_ENC_REQ is the proper place to set this, but sometime we miss that packet
            # so we're setting it here just in case
            g_stop_exporting_encrypted_packets_by_AA[access_address] = True
            data = ff_LL_ENC_RSP(
                direction=get_packet_direction(packet),
                skd_p=ll_ctrl.skds,
                iv_p=ll_ctrl.ivs
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_ENC_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_START_ENC_REQ:
        try:
            # This is the proper place to set this, but sometime we miss this packet
            g_stop_exporting_encrypted_packets_by_AA[access_address] = True
            data = ff_LL_START_ENC_REQ(
                direction=get_packet_direction(packet)
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_ENC_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_START_ENC_RSP:
        try:
            data = ff_LL_START_ENC_RSP(
                direction=get_packet_direction(packet)
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_ENC_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_UNKNOWN_RSP:
        try:
            data = ff_LL_UNKNOWN_RSP(
                direction=get_packet_direction(packet),
                unknown_type=ll_ctrl.opcode
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_UNKNOWN_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_FEATURE_REQ:
        try:
            data = ff_LL_FEATURE_REQ(
                direction=get_packet_direction(packet),
                features=ll_ctrl.feature_set.value
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_FEATURE_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_PERIPHERAL_FEATURE_REQ:
        try:
            data = ff_LL_PERIPHERAL_FEATURE_REQ(
                direction=get_packet_direction(packet),
                features=ll_ctrl.feature_set.value
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_PERIPHERAL_FEATURE_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_FEATURE_RSP:
        try:
            data = ff_LL_FEATURE_RSP(
                direction=get_packet_direction(packet),
                features=ll_ctrl.feature_set.value
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_FEATURE_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_VERSION_IND:
        try:
            data = ff_LL_VERSION_IND(
                direction=get_packet_direction(packet),
                version=ll_ctrl.version,
                company_id=ll_ctrl.company,
                subversion=ll_ctrl.subversion
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_VERSION_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_REJECT_IND:
        try:
            data = ff_LL_REJECT_IND(
                direction=get_packet_direction(packet),
                error_code=ll_ctrl.code
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_VERSION_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_CONNECTION_PARAM_REQ:
        try:
            data = ff_LL_CONNECTION_PARAM_REQ(
                direction=get_packet_direction(packet),
                interval_min=ll_ctrl.interval_min,
                interval_max=ll_ctrl.interval_max,
                latency=ll_ctrl.latency,
                timeout=ll_ctrl.timeout,
                preferred_periodicity=ll_ctrl.preferred_periodicity,
                reference_conneventcount=ll_ctrl.reference_conn_evt_count,
                offset0=ll_ctrl.offset0,
                offset1=ll_ctrl.offset1,
                offset2=ll_ctrl.offset2,
                offset3=ll_ctrl.offset3,
                offset4=ll_ctrl.offset4,
                offset5=ll_ctrl.offset5
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_CONNECTION_PARAM_REQ: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_CONNECTION_PARAM_RSP:
        try:
            data = ff_LL_CONNECTION_PARAM_RSP(
                direction=get_packet_direction(packet),
                interval_min=ll_ctrl.interval_min,
                interval_max=ll_ctrl.interval_max,
                latency=ll_ctrl.latency,
                timeout=ll_ctrl.timeout,
                preferred_periodicity=ll_ctrl.preferred_periodicity,
                reference_conneventcount=ll_ctrl.reference_conn_evt_count,
                offset0=ll_ctrl.offset0,
                offset1=ll_ctrl.offset1,
                offset2=ll_ctrl.offset2,
                offset3=ll_ctrl.offset3,
                offset4=ll_ctrl.offset4,
                offset5=ll_ctrl.offset5
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_CONNECTION_PARAM_RSP: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_REJECT_EXT_IND:
        try:
            data = ff_LL_REJECT_EXT_IND(
                direction=get_packet_direction(packet),
                reject_opcode=ll_ctrl.reject_opcode,
                error_code=ll_ctrl.error_code
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_VERSION_IND: {e}")
            return False
    elif ll_ctrl.opcode == type_opcode_LL_PING_REQ:
        try:
            data = ff_LL_PING_REQ(
                direction=get_packet_direction(packet)
            )
        except Exception as e:
            print(f"Error processing LL_PING_REQ: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PING_RSP:
        try:
            data = ff_LL_PING_RSP(
                direction=get_packet_direction(packet)
            )
        except Exception as e:
            print(f"Error processing LL_PING_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_LENGTH_REQ:
        try:
            data = ff_LL_LENGTH_REQ(
                direction=get_packet_direction(packet),
                max_rx_octets=ll_ctrl.max_rx_bytes,
                max_rx_time=ll_ctrl.max_rx_time,
                max_tx_octets=ll_ctrl.max_tx_bytes,
                max_tx_time=ll_ctrl.max_tx_time
            )
        except Exception as e:
            print(f"Error processing LL_LENGTH_REQ: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_LENGTH_RSP:
        try:
            data = ff_LL_LENGTH_RSP(
                direction=get_packet_direction(packet),
                max_rx_octets=ll_ctrl.max_rx_bytes,
                max_rx_time=ll_ctrl.max_rx_time,
                max_tx_octets=ll_ctrl.max_tx_bytes,
                max_tx_time=ll_ctrl.max_tx_time
            )
        except Exception as e:
            print(f"Error processing LL_LENGTH_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PHY_REQ:
        try:
            data = ff_LL_PHY_REQ(
                direction=get_packet_direction(packet),
                tx_phys=ll_ctrl.tx_phys.value,
                rx_phys=ll_ctrl.rx_phys.value
            )
        except Exception as e:
            print(f"Error processing LL_PHY_REQ: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PHY_RSP:
        try:
            data = ff_LL_PHY_RSP(
                direction=get_packet_direction(packet),
                tx_phys=ll_ctrl.tx_phys.value,
                rx_phys=ll_ctrl.rx_phys.value
            )
        except Exception as e:
            print(f"Error processing LL_PHY_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_PHY_UPDATE_IND:
        try:
            data = ff_LL_PHY_UPDATE_IND(
                direction=get_packet_direction(packet),
                phy_c_to_p=ll_ctrl.tx_phy.value,
                phy_p_to_c=ll_ctrl.rx_phy.value,
                instant=ll_ctrl.instant
            )
        except Exception as e:
            print(f"Error processing LL_PHY_RSP: {e}")
            return False
        if_verbose_insert_std_optional_fields(data, packet)
        BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
        return True
    elif ll_ctrl.opcode == type_opcode_LL_UNKNOWN_CUSTOM:
        try:
            #ll_ctrl.show()
            full_pkt_hex_str = bytes_to_hex_str(packet.load)
            data = ff_LL_UNKNOWN_CUSTOM(
                direction=get_packet_direction(packet),
                full_pkt_hex_str=full_pkt_hex_str
            )
            if_verbose_insert_std_optional_fields(data, packet)
            BTIDES_export_LLArray_entry(connect_ind_obj=connect_ind_obj, data=data)
            return True
        except Exception as e:
            print(f"Error processing LL_UNKNOWN_CUSTOM: {e}")
            return False
    else:
        if(not TME.TME_glob.quiet_print):
            packet.show()

    return False


def export_to_ATTArray(packet):
    ble_fields = packet.getlayer(BTLE)
    access_address = ble_fields.access_addr

    if access_address in g_access_address_to_connect_ind_obj:
        connect_ind_obj = g_access_address_to_connect_ind_obj[access_address]
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    #packet.show()
    # The opcodes are mutually exclusive, so if one returns true, we're done
    # To convert ATT data into a GATT hierarchy requires us to statefully
    # remember information between packets (i.e. which UUID corresponds to which handle)
    if(export_ATT_Error_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Exchange_MTU_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Exchange_MTU_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_By_Type_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_By_Type_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Find_Information_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Find_Information_Response(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_By_Group_Type_Request(connect_ind_obj, packet)):
        return True
    if(export_ATT_Read_By_Group_Type_Response(connect_ind_obj, packet)):
        return True

    # TODO: handle ALL opcodes


def export_to_SMPArray(packet):
    ble_fields = packet.getlayer(BTLE)
    access_address = ble_fields.access_addr

    if access_address in g_access_address_to_connect_ind_obj:
        connect_ind_obj = g_access_address_to_connect_ind_obj[access_address]
    else:
        connect_ind_obj = ff_CONNECT_IND_placeholder()

    # packet.show()
    # The opcodes are mutually exclusive, so if one returns true, we're done
    if(export_SMP_Pairing_Request(connect_ind_obj, packet)):
        return True
    if(export_SMP_Pairing_Response(connect_ind_obj, packet)):
        return True

    # TODO: handle ALL opcodes


def export_CONNECT_IND(packet):
    global g_access_address_to_connect_ind_obj

    #packet.show()

    # Store the BDADDRs involved in the connection into a dictionary, queryable by access address
    # This dictionary will need to be used by all subsequent packets within the connection to figure out
    # which bdaddr to associate their data with
    ble_adv_fields = packet.getlayer(BTLE_ADV)
    central_bdaddr_rand = ble_adv_fields.TxAdd
    peripheral_bdaddr_rand = ble_adv_fields.RxAdd
    connect_fields = packet.getlayer(BTLE_CONNECT_IND)
    central_bdaddr = connect_fields.InitA
    peripheral_bdaddr = connect_fields.AdvA
    # The following 3 multi-byte fields are in the incorrect byte order in Scapy (according to looking at their values in Wireshark, which I trust more)
    access_address = int.from_bytes(connect_fields.AA.to_bytes(4, byteorder='little'), byteorder='big')
    channel_map_hex_str = ''.join(f'{byte:02x}' for byte in connect_fields.chM.to_bytes(5, byteorder='little'))
    crc_init_hex_str = ''.join(f'{byte:02x}' for byte in connect_fields.crc_init.to_bytes(3, byteorder='little'))
    connect_ind_obj = ff_CONNECT_IND(
        central_bdaddr=central_bdaddr,
        central_bdaddr_rand=central_bdaddr_rand,
        peripheral_bdaddr=peripheral_bdaddr,
        peripheral_bdaddr_rand=peripheral_bdaddr_rand,
        access_address=access_address,
        crc_init_hex_str=crc_init_hex_str,
        win_size=connect_fields.win_size,
        win_offset=connect_fields.win_offset,
        interval=connect_fields.interval,
        latency=connect_fields.latency,
        timeout=connect_fields.timeout,
        channel_map_hex_str=channel_map_hex_str,
        hop=connect_fields.hop,
        SCA=connect_fields.SCA
    )
    if_verbose_insert_std_optional_fields(connect_ind_obj, packet)
    # Store the CONNECT_IND obj into g_access_address_to_bdaddrs for later use in lookups
    g_access_address_to_connect_ind_obj[access_address] = connect_ind_obj

    generic_DualBDADDR_insertion_into_BTIDES_zeroth_level(connect_ind_obj)

    return True


def read_pcap(file_path):
    try:
        pcap_reader = PcapReader(file_path)

        i = 0
        while True:
            try:
                packet = pcap_reader.read_packet()
            except Exception as e:
                print(f"Done processing pcap file: {i} packets processed.")
                return
            i+=1
            if packet is None:
                return
            if i % 1000 == 0:
                qprint(f"Processed {i} packets")

            # Confirm packet is BTLE
            if packet.haslayer(BTLE):
                btle_hdr = packet.getlayer(BTLE)
                if(btle_hdr.access_addr != 0x8e89bed6 and btle_hdr.len == 0):
                    #qprint("Found empty non-advertisement packet, continuing")
                    continue

                if(btle_hdr.access_addr in g_stop_exporting_encrypted_packets_by_AA.keys()):
                    # Don't bother processing the packet if we've seen an LL_START_ENC_REQ in this connection already
                    continue

                if packet.haslayer(BTLE_SCAN_REQ) or packet.haslayer(BTLE_ADV_DIRECT_IND):
                    # Ignore for now. I don't particularly care to import that information for now (though TODO later it should be in the interest of completeness)
                    continue

                # If a packet matches on any export function, move on to the next packet

                # Connection requests
                if packet.haslayer(BTLE_CONNECT_IND):
                    if(export_CONNECT_IND(packet)): continue

                # Advertisement channel packets
                # Need to check this before ADV_IND since it's a sub-class
                if packet.haslayer(BTLE_ADV_NONCONN_IND):
                    if(export_AdvChannelData(packet, BTLE_ADV_NONCONN_IND, type_AdvChanPDU_ADV_NONCONN_IND)):
                        continue
                # Need to check this before ADV_IND since it's a sub-class
                if packet.haslayer(BTLE_ADV_SCAN_IND):
                    adv_hdr = packet.getlayer(BTLE_ADV)
                    # Special case to ignore things which only have an AdvA, which isn't useful to us
                    if(adv_hdr.Length <= 9): # 6 for AdvA + 3 for EIR_Hdr (2) + at least 1 byte of data
                        continue
                    else:
                        if(export_AdvChannelData(packet, BTLE_ADV_SCAN_IND, type_AdvChanPDU_ADV_SCAN_IND)):
                            continue
                if packet.haslayer(BTLE_ADV_IND):
                    # It's rare, but some things advertise but then don't include any AdvData...
                    btle_adv = packet.getlayer(BTLE_ADV_IND)
                    if(len(btle_adv.data) == 0):
                        continue
                    if(export_AdvChannelData(packet, BTLE_ADV_IND, type_AdvChanPDU_ADV_IND)): continue
                if packet.haslayer(BTLE_SCAN_RSP):
                    # Special case SCAN_RSP because Apple devices like to send back SCAN_RSP with no data in it,
                    # which causes it to return false and then continue to be processed above
                    btle_adv = packet.getlayer(BTLE_SCAN_RSP)
                    if(len(btle_adv.data) == 0): continue
                    if(export_AdvChannelData(packet, BTLE_SCAN_RSP, type_AdvChanPDU_SCAN_RSP)): continue
                if packet.haslayer(BTLE_ADV):
                    btle_adv = packet.getlayer(BTLE_ADV)
                    if(btle_adv.PDU_type == type_AdvChanPDU_ADV_DIRECT_IND): # for malformed packets that Scapy couldn't add a BTLE_ADV_DIRECT_IND layer to...
                        # Ignore for now. I don't particularly care to import that information for now (though TODO later it should be in the interest of completeness)
                        continue
                    # qprint(packet.layers())
                    # qprint("")

                # LL Control packets
                if packet.haslayer(BTLE_CTRL):
                    if(export_BTLE_CTRL(packet)): continue

                # ATT packets
                if packet.haslayer(ATT_Hdr):
                    if(export_to_ATTArray(packet)): continue

                # SMP packets
                if packet.haslayer(SM_Hdr):
                    if(export_to_SMPArray(packet)): continue
                else:
                    if(TME.TME_glob.verbose_print):
                        qprint("Unknown or unparsable packet type. Skipped")
                        packet.show()
        return
    except Exception as e:
        print(f"Error reading pcap file: {e}")


def main():
    global verbose_print, verbose_BTIDES
    parser = argparse.ArgumentParser(description='pcap file input arguments')
    parser.add_argument('--input', type=str, required=True, help='Input file name for pcap file.')

    # BTIDES arguments
    btides_group = parser.add_argument_group('BTIDES file output arguments')
    btides_group.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    btides_group.add_argument('--verbose-BTIDES', action='store_true', required=False, help='Include optional fields in BTIDES output that make it more human-readable.')

    # SQL arguments
    sql = parser.add_argument_group('Local SQL database storage arguments (only applicable in the context of a local Blue2thprinting setup, not 3rd party tool usage.)')
    sql.add_argument('--to-SQL', action='store_true', required=False, help='Store output BTIDES file to your local SQL database.')
    sql.add_argument('--rename', action='store_true', required=False, help='Rename the output file to output.processed if used in conjunction with --to-SQL')
    sql.add_argument('--use-test-db', action='store_true', required=False, help='This will utilize the alternative bttest database, used for testing.')

    # BTIDALPOOL arguments
    btidalpool_group = parser.add_argument_group('BTIDALPOOL (crowdsourced database) arguments')
    btidalpool_group.add_argument('--to-BTIDALPOOL', action='store_true', required=False, help='Send output BTIDES data to the BTIDALPOOL crowdsourcing SQL database.')
    btidalpool_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')

    printout_group = parser.add_argument_group('Print verbosity arguments')
    printout_group.add_argument('--verbose-print', action='store_true', required=False, help='Show explicit data-not-found output.')
    printout_group.add_argument('--quiet-print', action='store_true', required=False, help='Hide all print output (useful when you only want to use --output to export data).')

    args = parser.parse_args()

    in_pcap_filename = args.input
    out_BTIDES_filename = args.output
    TME.TME_glob.verbose_print = args.verbose_print
    TME.TME_glob.quiet_print = args.quiet_print
    TME.TME_glob.verbose_BTIDES = args.verbose_BTIDES

    qprint("Reading all packets from pcap into memory. (This can take a while for large pcaps. Assume a total time of 1 second per 100 packets.)")
    read_pcap(in_pcap_filename)

    qprint("Writing BTIDES data to file.")
    write_BTIDES(out_BTIDES_filename)
    qprint("Export completed with no errors.")

    btides_to_sql_succeeded = False
    if args.to_SQL:
        b2s_args = btides_to_sql_args(input=out_BTIDES_filename, use_test_db=args.use_test_db, quiet_print=args.quiet_print, verbose_print=args.verbose_print)
        btides_to_sql_succeeded = btides_to_sql(b2s_args)

    if args.to_BTIDALPOOL:
        # If the token isn't given on the CLI, then redirect them to go login and get one
        client = AuthClient()
        if args.token_file:
            with open(args.token_file, 'r') as f:
                token_data = json.load(f)
            token = token_data['token']
            refresh_token = token_data['refresh_token']
            client.set_credentials(token, refresh_token, token_file=args.token_file)
            if(not client.validate_credentials()):
                print("Authentication failed.")
                exit(1)
        else:
            try:
                if(not client.google_SSO_authenticate() or not client.validate_credentials()):
                    print("Authentication failed.")
                    exit(1)
            except ValueError as e:
                print(f"Error: {e}")
                exit(1)

        # Use the copy of token/refresh_token in client.credentials, because it could have been refreshed inside validate_credentials()
        send_btides_to_btidalpool(
            input_file=out_BTIDES_filename,
            token=client.credentials.token,
            refresh_token=client.credentials.refresh_token
        )

    if(btides_to_sql_succeeded and args.rename):
        os.rename(out_BTIDES_filename, out_BTIDES_filename + ".processed")


if __name__ == "__main__":
    main()