# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

import globals
from BG_Helper_All import *

def append_common(tokens):
    if(globals.target_bdaddr_type_public):
        tokens.append("public")
    else:
        tokens.append("random")
    tokens.append(f"{globals.target_bdaddr}")

def write_to_csv(tokens):
    global target_bdaddr
    with open(f"/tmp/GATTPRINT_{globals.target_bdaddr.replace(':','_')}.csv", 'a', newline='\n') as csvfile:
        csvwriter = csv.writer(csvfile, quoting=csv.QUOTE_ALL, lineterminator="\n")
        csvwriter.writerow(tokens)

def store_services_in_existing_format_expectations(begin_handle, end_handle, UUID128):
    tokens = ["GATTPRINT:SERVICE"]
    append_common(tokens)
    tokens.append(f"0x{begin_handle:04x}")
    tokens.append(f"0x{end_handle:04x}")
    tokens.append(f"{UUID128}")
    vprint(tokens)
    write_to_csv(tokens)

def store_descriptors_in_existing_format_expectations(handle, UUID128):
    tokens = ["GATTPRINT:HANDLE_UUID"]
    append_common(tokens)
    tokens.append(f"0x{handle:04x}")
    tokens.append(f"{UUID128}")
    vprint(tokens)
    write_to_csv(tokens)

def store_characteristic_values_in_existing_format_expectations(handle, hex_byte_str):
    tokens = ["GATTPRINT:CHAR_VALUE"]
    append_common(tokens)
    tokens.append(f"0x{handle:04x}")
    tokens.append(f"{hex_byte_str}")
    vprint(tokens)
    write_to_csv(tokens)

def store_characteristics_in_existing_format_expectations(handle, char_properties, char_value_handle, hex_byte_str):
    tokens = ["GATTPRINT:CHAR_DESC"]
    append_common(tokens)
    tokens.append(f"0x{handle:04x}")
    tokens.append(f"0x{char_properties:02x}")
    tokens.append(f"0x{char_value_handle:04x}")
    tokens.append(f"{hex_byte_str}")
    vprint(tokens)
    write_to_csv(tokens)

def convert_bytes_to_UUID128_str(b):
    if(len(b) == 2):
        return  f"0000{b[1]:02x}{b[0]:02x}-0000-1000-8000-00805f9b34fb"
    elif(len(b) == 16):
        # They're returned little-endian
        return f"{b[15]:02x}{b[14]:02x}{b[13]:02x}{b[12]:02x}-{b[11]:02x}{b[10]:02x}-{b[9]:02x}{b[8]:02x}-{b[7]:02x}{b[6]:02x}-{b[5]:02x}{b[4]:02x}{b[3]:02x}{b[2]:02x}{b[1]:02x}{b[0]:02x}"
    else:
       vprint(b)
       exit()

def print_all_info():
    verbose2 = True

    max_handle = max(globals.received_handles.keys())

    for handle in globals.received_handles.keys():
        UUID128 = convert_bytes_to_UUID128_str(globals.received_handles[handle])
#        vprint(f"Handle 0x{handle:04x} = UUID 0x{UUID128}")
        store_descriptors_in_existing_format_expectations(handle, UUID128)

        # Set aside "Primary Service Descriptor" (0x2800) and "Secondary Service Descriptor" (0x2801) data for later post-processing
        if(globals.received_handles[handle] == b'\x00\x28' or globals.received_handles[handle] == b'\x01\x28'):
            globals.service_received_handles[handle] = globals.all_handles_received_values[handle]
        # Process "Characteristic Descriptor" (0x2803) data now
        elif(globals.received_handles[handle] == b'\x03\x28'):
            if(handle in globals.all_handles_received_values):
                data_len = len(globals.all_handles_received_values[handle])
                raw_hex_str = ''.join(f'{byte:02x}' for byte in globals.all_handles_received_values[handle])
                if(data_len == 5 or data_len == 19):
                    # Interpret the raw bytes as if they're a Characteristic Descriptor
#                    vprint(f"LEN = {data_len} for 2803 handle {handle} = {raw_hex_str}")
                    char_properties, char_value_handle = unpack("<BH", globals.all_handles_received_values[handle][:3])
                    char_value_UUID128_str = convert_bytes_to_UUID128_str(globals.all_handles_received_values[handle][3:])
                    store_characteristics_in_existing_format_expectations(handle, char_properties, char_value_handle, char_value_UUID128_str)
#                    uuid128_raw_hex_str = ''.join(f'{byte:02x}' for byte in globals.all_handles_received_values[handle][3:])
                else:
                    if(verbose2): print(f"WTF BBQ LEN = {data_len} for 2803 handle {handle} = {raw_hex_str}")
        else:
            # Implicitly by only doing the store_characteristic_values_in_existing_format_expectations()
            # in the else case, we're saying we don't want to do it for 0x2800 and 0x2803 entries,
            # as that would essentially be adding redundant information to the GATT_characteristics_values table
            # which is captured in other tables like GATT_characteristics and GATT_services
            if(handle in globals.all_handles_received_values.keys()):
                if(isinstance(globals.all_handles_received_values[handle], bytes)):
                    raw_hex_str = ''.join(f'{byte:02x}' for byte in globals.all_handles_received_values[handle])
                    store_characteristic_values_in_existing_format_expectations(handle, raw_hex_str)
    #               print(f"handle = 0x{handle:02x}, value (raw hex) = {raw_hex_str}")
                    if(verbose2): print(f"handle = 0x{handle:02x}, value (as UTF8) = {globals.all_handles_received_values[handle].decode('utf8', errors='backslashreplace')}")
                else:
                    if(verbose2): print(f"handle = 0x{handle:02x}, value (str)     = {globals.all_handles_received_values[handle]}")

    i = 0
    # I need to have the full list available so I can move forward to the next index and subtract 1 to get the handle range for a given service
    sorted_services_handle_list = sorted(globals.service_received_handles.keys())
    handle_list_len = len(globals.service_received_handles.keys())
    while(i < handle_list_len):
        begin_handle = sorted_services_handle_list[i]
        if(i+1 < handle_list_len):
            end_handle = sorted_services_handle_list[i+1] - 1
        else:
            end_handle = max_handle

        UUID128 = convert_bytes_to_UUID128_str(globals.service_received_handles[begin_handle])
        if(verbose2): print(f"Service {i+1} handles 0x{begin_handle:04x}-0x{end_handle:04x} = UUID 0x{UUID128}")
        store_services_in_existing_format_expectations(begin_handle, end_handle, UUID128)
        i += 1

def print_and_exit():
    print_all_info()
    # Tear down with an LL_TERMINATE_IND
    # 0x13 = error code "Remote user terminated connection"
    write_outbound_pkt(3, b'\x02\x13')
    time.sleep(.1)
    exit()
