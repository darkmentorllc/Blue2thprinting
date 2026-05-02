########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

import struct

from TME.TME_helpers import *
from TME.TME_GATT import *
from TME.TME_BTIDES_AdvData import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# UUID16s
########################################

def colored_print_name_for_UUID16(uuid16):
    service_by_uuid16 = get_uuid16_service_string(uuid16)
    gatt_service_by_uuid16 = get_uuid16_gatt_service_string(uuid16)
    protocol_by_uuid16 = get_uuid16_protocol_string(uuid16)
    standards_org_by_uuid16 = get_standards_org_by_uuid16(uuid16)
    company_by_uuid16 = get_company_by_uuid16(uuid16)
    custom_by_uuid16 = get_custom_by_uuid16(uuid16)
    if(service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Service ID: {service_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(gatt_service_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"GATT Service ID: {gatt_service_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(protocol_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Protocol ID: {protocol_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(standards_org_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Standards Development Organization UUID: {standards_org_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    # We do custom before company, because we might have better info in CLUES
    elif(custom_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company-specific Service UUID: {custom_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    elif(company_by_uuid16 != "Unknown"):
        colored_str = Fore.CYAN + Style.BRIGHT + f"Company ID: {company_by_uuid16}" + Style.RESET_ALL
        qprint(f"{i2}UUID16 {uuid16} ({colored_str})")
    else:
        qprint(f"{i2}UUID16 {uuid16} (No matches)")

# Function to print UUID16s for a given bdaddr
def print_uuid16s(bdaddr, bdaddr_random):
    # Query for EIR_bdaddr_to_UUID16s table
    values = (bdaddr,)
    eir_uuid16s_query = "SELECT list_type, str_UUID16s FROM EIR_bdaddr_to_UUID16s WHERE bdaddr = %s"
    eir_uuid16s_result = execute_query(eir_uuid16s_query, values)

    # Query for LE_bdaddr_to_UUID16s_list table
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_uuid16s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID16s FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_uuid16s_query = "SELECT bdaddr_random, le_evt_type, list_type, str_UUID16s FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr = %s"
    le_uuid16s_result = execute_query(le_uuid16s_query, values)

    if(len(eir_uuid16s_result) == 0 and len(le_uuid16s_result) == 0):
        vprint(f"{i1}No UUID16s found.")
        return
    else:
        qprint(f"{i1}UUID16s found:")

    # Process EIR_bdaddr_to_UUID16s results
    for list_type, str_UUID16s in eir_uuid16s_result:
        # Export BTIDES data first
        if(str_UUID16s != ""):
            UUID16List = str_UUID16s.split(",")
            for i in range(len(UUID16List)):
                UUID16List[i] = UUID16List[i].replace("0x","") # This won't be needed in the future after I change db import
        else:
            UUID16List = []
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": UUID16List}
        BTIDES_export_AdvData(bdaddr, 0, 50, list_type, data)

        # Then human UI output
        if(str_UUID16s == ""):
            qprint(f"{i2}Empty list present")
        else:
            str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
            for uuid16 in str_UUID16s_list:
                uuid16 = uuid16.strip()
                if(uuid16 == ''):
                    qprint(f"{i2}Empty entry present")
                    continue
                colored_print_name_for_UUID16(uuid16)
        vprint(f"{i3}In BT Classic data (DB:EIR_bdaddr_to_UUID16s)")


    # Process LE_bdaddr_to_UUID16s_list results
    for bdaddr_random, le_evt_type, list_type, str_UUID16s in le_uuid16s_result:
        # Export BTIDES data first
        if(str_UUID16s != ""):
            UUID16List = str_UUID16s.split(",")
            for i in range(len(UUID16List)):
                UUID16List[i] = UUID16List[i].replace("0x","") # This won't be needed in the future after I change db import
        else:
            UUID16List = []
        length = 1 + 2 * len(UUID16List) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": UUID16List}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, list_type, data)

        # Then human UI output
        if(str_UUID16s == ""):
            qprint(f"{i2}Empty list present")
        else:
            str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
            for uuid16 in str_UUID16s_list:
                uuid16 = uuid16.strip()
                if(uuid16 == ''):
                    qprint(f"{i2}Empty entry present")
                    continue
                colored_print_name_for_UUID16(uuid16)
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID16s_list), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        vprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Function to print UUID16s service solicitation data for a given bdaddr
def print_uuid16s_service_solicit(bdaddr, bdaddr_random):
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_uuid16s_query = "SELECT bdaddr_random, le_evt_type, str_UUID16s FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_uuid16s_query = "SELECT bdaddr_random, le_evt_type, str_UUID16s FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr = %s"
    le_uuid16s_result = execute_query(le_uuid16s_query, values)

    if(len(le_uuid16s_result) == 0):
        vprint(f"{i1}No Service Solicit UUID16s found.")
        return
    else:
        qprint(f"{i1}Service solicit UUID16s found:")

    # Process LE_bdaddr_to_UUID16s_list results
    for bdaddr_random, le_evt_type, str_UUID16s in le_uuid16s_result:
        str_UUID16s_list = [token.strip() for token in str_UUID16s.split(',')]
        # Export BTIDES data first
        length = 1 + 2 * len(str_UUID16s_list) # 1 byte for opcode, 2 bytes for each UUID16
        data = {"length": length, "UUID16List": str_UUID16s_list}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID16ListServiceSolicitation, data)

        for uuid16 in str_UUID16s_list:
            uuid16 = uuid16.strip()
            if(uuid16 == ''):
                qprint(f"{i2}Empty list present")
                continue
            colored_print_name_for_UUID16(uuid16)
        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID16_service_solicit), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        vprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")

# Function to print UUID16s service data for a given bdaddr
_EDDYSTONE_URL_SCHEMES = {
    0: "http://www.", 1: "https://www.", 2: "http://", 3: "https://",
}
_EDDYSTONE_URL_EXPANSIONS = {
    0: ".com/", 1: ".org/", 2: ".edu/", 3: ".net/",
    4: ".info/", 5: ".biz/", 6: ".gov/",
    7: ".com", 8: ".org", 9: ".edu", 10: ".net",
    11: ".info", 12: ".biz", 13: ".gov",
}

def print_eddystone_service_data(indent, service_data_hex_str):
    if not service_data_hex_str or len(service_data_hex_str) < 2:
        return
    data = bytes.fromhex(service_data_hex_str)
    frame_type = (data[0] >> 4) & 0xF  # upper nibble of first byte per Eddystone spec

    if frame_type == 0x0 and len(data) >= 19:  # UID
        tx_power = struct.unpack('b', bytes([data[1]]))[0]
        namespace = data[2:12].hex()
        instance = data[12:18].hex()
        qprint(f"{indent}Eddystone-UID: tx_power={tx_power} dBm, namespace={namespace}, instance={instance}")

    elif frame_type == 0x1 and len(data) >= 3:  # URL
        tx_power = struct.unpack('b', bytes([data[1]]))[0]
        scheme = _EDDYSTONE_URL_SCHEMES.get(data[2], f"?0x{data[2]:02x}://")
        body = "".join(_EDDYSTONE_URL_EXPANSIONS.get(b, chr(b)) for b in data[3:])
        qprint(f"{indent}Eddystone-URL: tx_power={tx_power} dBm, url={scheme}{body}")

    elif frame_type == 0x2 and len(data) >= 2:  # TLM
        version = data[1]
        if version == 0 and len(data) >= 14:
            batt_mv = struct.unpack('>H', data[2:4])[0]
            temp = struct.unpack('>h', data[4:6])[0] / 256.0
            adv_cnt = struct.unpack('>I', data[6:10])[0]
            sec_cnt = struct.unpack('>I', data[10:14])[0]
            qprint(f"{indent}Eddystone-TLM (plain): batt={batt_mv} mV, temp={temp:.2f} °C, adv_cnt={adv_cnt}, uptime={sec_cnt/10.0:.1f} s")
        elif version == 1 and len(data) >= 18:
            qprint(f"{indent}Eddystone-TLM (encrypted): cannot decode without Identity Key")
        else:
            qprint(f"{indent}Eddystone-TLM: unknown version 0x{version:02x}")

    elif frame_type == 0x3 and len(data) >= 10:  # EID
        tx_power = struct.unpack('b', bytes([data[1]]))[0]
        eid = data[2:10].hex()
        qprint(f"{indent}Eddystone-EID: tx_power={tx_power} dBm, eid={eid}")

    else:
        qprint(f"{indent}Eddystone: unknown/malformed frame type=0x{frame_type:x}")

########################################
# Open Drone ID (ASTM F3411)
########################################

_ODID_STATUS_STRS = {
    0: "Undeclared", 1: "Ground", 2: "Airborne",
    3: "Emergency", 4: "Remote ID System Failure",
}
_ODID_ID_TYPE_STRS = {
    0: "None", 1: "Serial Number (CTA-2063-A)", 2: "CAA Assigned",
    3: "UTM Assigned", 4: "Specific Session ID",
}
_ODID_UA_TYPE_STRS = {
    0: "None", 1: "Aeroplane", 2: "Helicopter/Multirotor", 3: "Gyroplane",
    4: "Hybrid Lift", 5: "Ornithopter", 6: "Glider", 7: "Kite",
    8: "Free Balloon", 9: "Captive Balloon", 10: "Airship",
    11: "Free Fall/Parachute", 12: "Rocket", 13: "Tethered Powered Aircraft",
    14: "Ground Obstacle", 15: "Other",
}
_ODID_DESC_TYPE_STRS = {
    0: "Plain text", 1: "Emergency", 2: "Extended status",
}

def _odid_decode_altitude(raw):
    if raw == 0xFFFF:
        return "unknown"
    return f"{raw * 0.5 - 1000:.1f} m"

def _parse_odid_message(indent, msg_bytes):
    if len(msg_bytes) < 1:
        qprint(f"{indent}ODID: empty message")
        return
    msg_type = (msg_bytes[0] >> 4) & 0xF
    proto_ver = msg_bytes[0] & 0xF

    if msg_type == 0x0:  # Basic ID
        if len(msg_bytes) < 22:
            qprint(f"{indent}ODID Basic ID: too short")
            return
        id_type = (msg_bytes[1] >> 4) & 0xF
        ua_type = msg_bytes[1] & 0xF
        uas_id = msg_bytes[2:22].split(b'\x00')[0].decode('utf-8', errors='replace')
        id_type_str = _ODID_ID_TYPE_STRS.get(id_type, f"Unknown(0x{id_type:x})")
        ua_type_str = _ODID_UA_TYPE_STRS.get(ua_type, f"Unknown(0x{ua_type:x})")
        qprint(f"{indent}ODID Basic ID (proto_ver={proto_ver}): id_type={id_type_str}, ua_type={ua_type_str}, uas_id={uas_id!r}")

    elif msg_type == 0x1:  # Location/Vector
        if len(msg_bytes) < 19:
            qprint(f"{indent}ODID Location: too short")
            return
        status     = (msg_bytes[1] >> 4) & 0xF
        height_type = (msg_bytes[1] >> 3) & 0x1
        ew_dir     = (msg_bytes[1] >> 2) & 0x1
        speed_mult = (msg_bytes[1] >> 1) & 0x1

        direction_raw = msg_bytes[2]
        direction_str = "unknown" if direction_raw == 0xFF else f"{direction_raw + 180 * ew_dir}°"

        speed_h_raw = msg_bytes[3]
        if speed_h_raw == 255:
            speed_h_str = "unknown"
        elif speed_mult == 0:
            speed_h_str = f"{speed_h_raw * 0.25:.2f} m/s"
        else:
            speed_h_str = f"{speed_h_raw * 0.75 + 64:.2f} m/s"

        speed_v_raw = struct.unpack('b', bytes([msg_bytes[4]]))[0]
        speed_v_str = "unknown" if speed_v_raw == -128 else f"{speed_v_raw * 0.5:.1f} m/s"

        lat_raw = struct.unpack('<i', msg_bytes[5:9])[0]
        lon_raw = struct.unpack('<i', msg_bytes[9:13])[0]
        alt_press = _odid_decode_altitude(struct.unpack('<H', msg_bytes[13:15])[0])
        alt_geo   = _odid_decode_altitude(struct.unpack('<H', msg_bytes[15:17])[0])
        height    = _odid_decode_altitude(struct.unpack('<H', msg_bytes[17:19])[0])

        status_str = _ODID_STATUS_STRS.get(status, f"Unknown(0x{status:x})")
        height_type_str = "AGL" if height_type else "Above Takeoff"
        qprint(f"{indent}ODID Location/Vector (proto_ver={proto_ver}): status={status_str}, direction={direction_str}, speed_h={speed_h_str}, speed_v={speed_v_str}")
        qprint(f"{indent}  lat={lat_raw * 1e-7:.7f}°, lon={lon_raw * 1e-7:.7f}°, alt_pressure={alt_press}, alt_geodetic={alt_geo}, height={height} ({height_type_str})")

    elif msg_type == 0x2:  # Authentication
        qprint(f"{indent}ODID Authentication (proto_ver={proto_ver}): raw={msg_bytes[1:].hex()}")

    elif msg_type == 0x3:  # Self-ID
        if len(msg_bytes) < 2:
            qprint(f"{indent}ODID Self-ID: too short")
            return
        desc_type = msg_bytes[1]
        desc = msg_bytes[2:25].split(b'\x00')[0].decode('utf-8', errors='replace')
        desc_type_str = _ODID_DESC_TYPE_STRS.get(desc_type, f"Unknown(0x{desc_type:x})")
        qprint(f"{indent}ODID Self-ID (proto_ver={proto_ver}): desc_type={desc_type_str}, description={desc!r}")

    elif msg_type == 0x4:  # System
        if len(msg_bytes) < 17:
            qprint(f"{indent}ODID System: too short")
            return
        op_lat_raw = struct.unpack('<i', msg_bytes[2:6])[0]
        op_lon_raw = struct.unpack('<i', msg_bytes[6:10])[0]
        area_count  = struct.unpack('<H', msg_bytes[10:12])[0]
        area_radius = msg_bytes[12]
        area_ceil   = _odid_decode_altitude(struct.unpack('<H', msg_bytes[13:15])[0])
        area_floor  = _odid_decode_altitude(struct.unpack('<H', msg_bytes[15:17])[0])
        radius_str = "unknown" if area_radius == 255 else f"{area_radius * 10} m"
        qprint(f"{indent}ODID System (proto_ver={proto_ver}): operator_lat={op_lat_raw * 1e-7:.7f}°, operator_lon={op_lon_raw * 1e-7:.7f}°")
        qprint(f"{indent}  area_count={area_count}, area_radius={radius_str}, area_ceiling={area_ceil}, area_floor={area_floor}")

    elif msg_type == 0x5:  # Operator ID
        if len(msg_bytes) < 22:
            qprint(f"{indent}ODID Operator ID: too short")
            return
        op_id_type = msg_bytes[1]
        op_id_hex = msg_bytes[2:22].hex()
        qprint(f"{indent}ODID Operator ID (proto_ver={proto_ver}): operator_id_type=0x{op_id_type:02x}, operator_id={op_id_hex}")

    elif msg_type == 0xF:  # Message Pack
        if len(msg_bytes) < 3:
            qprint(f"{indent}ODID Message Pack: too short")
            return
        msg_size  = msg_bytes[1]
        msg_count = msg_bytes[2]
        qprint(f"{indent}ODID Message Pack (proto_ver={proto_ver}): {msg_count} messages (msg_size={msg_size})")
        if msg_size == 25:
            for i in range(msg_count):
                start = 3 + i * 25
                if start + 25 <= len(msg_bytes):
                    _parse_odid_message(f"{indent}  [{i}] ", msg_bytes[start:start + 25])

    else:
        qprint(f"{indent}ODID Unknown message type 0x{msg_type:x} (proto_ver={proto_ver}): raw={msg_bytes[1:].hex()}")

def print_odid_payload(indent, payload_hex_str):
    if not payload_hex_str or len(payload_hex_str) < 4:
        qprint(f"{indent}Open Drone ID: payload too short")
        return
    data = bytes.fromhex(payload_hex_str)
    app_code = data[0]
    if app_code != 0x0D:
        qprint(f"{indent}Open Drone ID: unexpected app code 0x{app_code:02x}")
        return
    _parse_odid_message(indent, data[1:])

def print_uuid16_service_data(bdaddr, bdaddr_random):
    if(bdaddr_random is not None):
        values = (bdaddr_random, bdaddr)
        le_uuid16_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = %s AND bdaddr = %s"
    else:
        values = (bdaddr,)
        le_uuid16_service_data_query = "SELECT bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr = %s"
    le_uuid16_service_data_result = execute_query(le_uuid16_service_data_query, values)

    if(len(le_uuid16_service_data_result) == 0):
        vprint(f"{i1}No UUID16 service data found.")
        return
    else:
        qprint(f"{i1}UUID16 service data found:")

    for bdaddr_random, le_evt_type, UUID16_hex_str, service_data_hex_str in le_uuid16_service_data_result:
        # Export BTIDES data first
        length = 3 + int(len(service_data_hex_str) / 2) # 1 byte for opcode + 2 bytes for UUID16 + half as many bytes as there are hex nibble characters
        data = {"length": length, "UUID16": UUID16_hex_str, "service_data_hex_str": service_data_hex_str}
        BTIDES_export_AdvData(bdaddr, bdaddr_random, le_evt_type, type_AdvData_UUID16ServiceData, data)

        # Then human UI output
        # Lookup the UUID16 and see if it matches any well-known UUID16s
        colored_print_name_for_UUID16(UUID16_hex_str)
        qprint(f"{i2}Raw service data: {service_data_hex_str}")
        if UUID16_hex_str == "feaa":
            print_eddystone_service_data(i2, service_data_hex_str)
        elif UUID16_hex_str == "fffa":
            print_odid_payload(i3, service_data_hex_str)

        vprint(f"{i3}Found in BLE data (DB:LE_bdaddr_to_UUID16_service_data), bdaddr_random = {bdaddr_random} ({get_bdaddr_type(bdaddr, bdaddr_random)})")
        vprint(f"{i3}This was found in an event of type {le_evt_type} which corresponds to {get_le_event_type_string(le_evt_type)}")

    qprint("")