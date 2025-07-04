# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

import globals
from BG_Helper_All import *
from BG_Helper_ATT import *
from BG_Helper_Output import *

####################################################################################
# Detect Apple devices based on
####################################################################################
def detect_Apple_by_GATT_Manufacturer_Name(actual_body_len, dpkt):
    if(globals.detect_apple_done):
        return False

    if(not globals.apple_mfg_req_sent):
        # Send a ATT_FIND_BY_TYPE_VALUE_REQ to find the Manufacturer Name (0x2A29) == "Apple"
        send_ATT_FIND_BY_TYPE_VALUE_REQ_0x2A29_Apple()
        globals.apple_mfg_req_sent = True

    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_FIND_BY_TYPE_VALUE_RSP, dpkt)
    # Because this is the only ATT_FIND_BY_TYPE_VALUE_REQ we send, if we get any ATT_FIND_BY_TYPE_VALUE_RSP, rather than error,
    # that means the other side must have had a match, so we can assume it's an Apple device
    if(matched):
        vmultiprint(actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode)
        globals.apple_mfg_rsp_recv = True
        return True

    # Look for ATT_ERROR_RSP
    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_ERROR_RSP, dpkt)
    if(matched and actual_body_len >= 11):
        req_opcode_in_error, handle_in_error, error_code = unpack("<BHB", dpkt.body[7:11])
        if(req_opcode_in_error == opcode_ATT_FIND_BY_TYPE_VALUE_REQ and handle_in_error == 0x0001):
            globals.apple_mfg_rsp_recv = True
            print(f"-----> ATT_FIND_BY_TYPE_VALUE phase done for Manufacturer Name, moving to next phase")
            globals.detect_apple_done = True

    return False

####################################################################################
# Send ATT_READ_BY_GROUP_TYPE_REQ for Primary (0x2800) Services
####################################################################################
def outgoing_service_discovery(actual_body_len, dpkt):
    global primary_services_read_req_sent_time
    global secondary_services_read_req_sent_time
    global secondary_service_request_retry_count

    # Don't start until after ATT negotiation
    if(not globals.att_MTU_negotiated):
        return

    if (not globals.primary_services_read_req_sent_time):
        send_ATT_READ_BY_GROUP_TYPE_REQ(1, 0x2800)
        globals.last_requested_service_type = "primary"
        globals.primary_services_read_req_sent_time = time.time_ns()
    elif(globals.retry_enabled and not globals.primary_services_all_recv):
        # Check if we need to re-send because it's been too long since we saw any response
        # If the primary_service_final_handle is still 1 that means we haven't received any responses
        # so retry sending the request
        time_elapsed = (time.time_ns() - globals.primary_services_read_req_sent_time)
        if(time_elapsed > globals.retry_timeout):
            globals.primary_service_request_retry_count += 1
            if(globals.primary_service_request_retry_count == globals.primary_service_request_max_retries):
                # We're done trying, consider discovery of secondary services done
                globals.primary_services_all_recv = True
            else:
                send_ATT_READ_BY_GROUP_TYPE_REQ(globals.primary_service_last_reqested_handle, 0x2800)
                globals.primary_services_read_req_sent_time = time.time_ns()


    # Wait for all primary services to be received before proceeding to secondary services
    if (globals.primary_services_all_recv):
        if(not globals.secondary_services_read_req_sent_time):
            globals.last_requested_service_type = "secondary"
            send_ATT_READ_BY_GROUP_TYPE_REQ(1, 0x2801)
            globals.secondary_services_read_req_sent_time = time.time_ns()
        elif(globals.retry_enabled and not globals.secondary_services_all_recv):
            # Check if we need to re-send because it's been too long since we saw any response
            # If the primary_service_final_handle is still 1 that means we haven't received any responses
            # so retry sending the request
            time_elapsed = (time.time_ns() - globals.primary_services_read_req_sent_time)
            if(time_elapsed > globals.retry_timeout):
                globals.secondary_service_request_retry_count += 1
                if(globals.secondary_service_request_retry_count == globals.secondary_service_request_max_retries):
                    # We're done trying, consider discovery of secondary services done
                    globals.secondary_services_all_recv = True
                else:
                    send_ATT_READ_BY_GROUP_TYPE_REQ(globals.secondary_service_last_reqested_handle, 0x2801)
                    globals.secondary_services_read_req_sent_time = time.time_ns()

    # TODO: do Include (0x2802) as well?

def process_ATT_READ_BY_GROUP_TYPE_RSP(actual_body_len, dpkt):
    global all_handles_received_values
    global primary_services_all_recv
    global primary_service_handle_ranges_dict, primary_service_final_handle, primary_service_last_reqested_handle
    global secondary_services_all_recv
    global secondary_service_handle_ranges_dict, secondary_service_final_handle, secondary_service_last_reqested_handle

    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_READ_BY_GROUP_TYPE_RSP, dpkt)
    if(matched and actual_body_len >= 8):
        entry_len_ACID, = unpack("<B", dpkt.body[7:8])
        vmultiprint(actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode, entry_len_ACID)
        processed_bytes = 8
        while(processed_bytes + entry_len_ACID <= actual_body_len): # Careful not to exceed!
            if(entry_len_ACID == 6): # Returned list using UUID16s (2, 2, 2)
                begin_handle, end_handle, service_UUID = unpack("<HHH", dpkt.body[processed_bytes:processed_bytes+entry_len_ACID])
                vmultiprint(begin_handle, end_handle, service_UUID)
                globals.all_handles_received_values[begin_handle] = v2b(service_UUID)
                if(globals.last_requested_service_type == "primary"):
                    globals.primary_service_handle_ranges_dict[begin_handle] = (end_handle, service_UUID, 2)
                    globals.primary_service_final_handle = end_handle
                else:
                    globals.secondary_service_handle_ranges_dict[begin_handle] = (end_handle, service_UUID, 2)
                    globals.secondary_service_final_handle = end_handle
                processed_bytes += 6
            elif(entry_len_ACID == 20): # Returned list of UUID128s (2, 2, 16)
                begin_handle, end_handle = unpack("<HH", dpkt.body[processed_bytes:processed_bytes+4])
                service_UUID = dpkt.body[processed_bytes+4:processed_bytes+20]
                vmultiprint(begin_handle, end_handle)
                vprint(f"service_UUID = {service_UUID}")
                globals.primary_service_handle_ranges_dict[begin_handle] = (end_handle, service_UUID, 16)
                globals.all_handles_received_values[begin_handle] = service_UUID
                globals.primary_service_final_handle = end_handle
                processed_bytes += 20

        if(globals.primary_service_final_handle != 0xFFFF):
            # Entire list processed, make a new request
            if(globals.last_requested_service_type == "primary"):
                globals.primary_service_last_reqested_handle = globals.primary_service_final_handle+1
                send_ATT_READ_BY_GROUP_TYPE_REQ(globals.primary_service_last_reqested_handle, 0x2800)
            else:
                globals.secondary_service_last_reqested_handle = globals.secondary_service_final_handle+1
                send_ATT_READ_BY_GROUP_TYPE_REQ(globals.secondary_service_last_reqested_handle, 0x2801)
            return True
        else:
            # If the last handle of the last service ended with 0xFFFF then we're done enumerating
            if(globals.last_requested_service_type == "primary"):
                globals.primary_services_all_recv = True
            else:
                globals.secondary_services_all_recv = True
            return True
    return False

def process_ATT_ERROR_RSP_for_ATT_READ_BY_GROUP_TYPE_REQ(actual_body_len, dpkt):
    global all_handles_received_values
    global primary_services_all_recv
    # global primary_service_handle_ranges_dict, primary_service_final_handle, primary_service_last_reqested_handle
    global secondary_services_all_recv
    # global secondary_service_handle_ranges_dict, secondary_service_final_handle, secondary_service_last_reqested_handle

    # Look for ATT_ERROR_RSP
    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_ERROR_RSP, dpkt)
    if(matched and actual_body_len >= 11):
        req_opcode_in_error, handle_in_error, error_code = unpack("<BHB", dpkt.body[7:11])
        vmultiprint(req_opcode_in_error, handle_in_error)
        vprint(f"error_code = 0x{error_code:02x} = {globals.att_errorcode_to_str[error_code]}")
        # Meta sends errorcode_10_ATT_Unsupported_Group_Type
        if(req_opcode_in_error == opcode_ATT_READ_BY_GROUP_TYPE_REQ and
           (error_code == errorcode_0A_ATT_Attribute_Not_Found) or (error_code == errorcode_10_ATT_Unsupported_Group_Type)):
            if(globals.last_requested_service_type == "primary" and handle_in_error == globals.primary_service_last_reqested_handle):
                globals.primary_services_all_recv = True
                print(f"----> ATT_READ_BY_GROUP_TYPE* phase done for Primary Services, moving to next phase")
            elif(handle_in_error == globals.secondary_service_last_reqested_handle):
                globals.secondary_services_all_recv = True
                print(f"----> ATT_READ_BY_GROUP_TYPE* phase done for Secondary Services, moving to next phase")
            return True

# Note: this is needed because there can be discontinuities in the handle ranges
def incoming_service_discovery(actual_body_len, dpkt):
    # global all_handles_received_values
    # global primary_services_all_recv
    # global primary_service_handle_ranges_dict, primary_service_final_handle, primary_service_last_reqested_handle
    # global secondary_services_all_recv
    # global secondary_service_handle_ranges_dict, secondary_service_final_handle, secondary_service_last_reqested_handle

    if(globals.primary_services_all_recv and globals.secondary_services_all_recv):
        return False

    # Process ATT_READ_BY_GROUP_TYPE_RSP or ATT_ERROR_RSP responses
    if (globals.primary_services_read_req_sent_time and not globals.primary_services_all_recv):
        if(process_ATT_READ_BY_GROUP_TYPE_RSP(actual_body_len, dpkt)):
            return True
        else:
            if(process_ATT_ERROR_RSP_for_ATT_READ_BY_GROUP_TYPE_REQ(actual_body_len, dpkt)):
                return True

    if (globals.secondary_services_read_req_sent_time and not globals.secondary_services_all_recv):
        if(process_ATT_READ_BY_GROUP_TYPE_RSP(actual_body_len, dpkt)):
            return True
        else:
            if(process_ATT_ERROR_RSP_for_ATT_READ_BY_GROUP_TYPE_REQ(actual_body_len, dpkt)):
                return True

    return False

####################################################################################
# Send ATT_READ_BY_GROUP_TYPE_REQ for Characteristics (0x2803)
####################################################################################
# Note: this is needed because there can be discontinuities in the handle ranges
def outgoing_characteristic_discovery(actual_body_len, dpkt):
    global characteristic_read_by_type_req_sent_time, characteristic_read_by_type_req_sent_time
    global characteristic_read_by_type_req_sent_retry_count
    global characteristic_read_by_type_req_all_received

    # Don't begin this check until after all handle enumeration
    # And don't continue within if we've already received all handles
    if(not globals.all_info_handles_recv or globals.characteristic_read_by_type_req_all_received):
        return

    # Check if Handle 2 exists, and is 0x2803 (Characteristic)
    # If so, then Characteristics have already been enumerated, and the device is not
    # misbehaving like Meta Quest 3S, so we can skip this phase
    # The handle to check should be the first service handle + 1 to get the first possible characteristic handle
    handle_to_check = 1 + sorted(globals.primary_service_handle_ranges_dict.keys())[0]
    if(handle_to_check in globals.received_handles.keys() and globals.received_handles[handle_to_check] == b'\x03\x28'):
        globals.characteristic_read_by_type_req_all_received = True
        return

    # Else, go ahead and request all the characteristics
    if (not globals.characteristic_read_by_type_req_sent_time):
        send_ATT_READ_BY_TYPE_REQ(globals.characteristic_last_read_requested_handle, 0xffff, 0x2803)
        globals.characteristic_read_by_type_req_sent_time = True
        globals.characteristic_read_by_type_req_sent_time = time.time_ns()
        return True
    elif(globals.retry_enabled and
         globals.characteristic_read_by_type_req_sent_retry_count < globals.characteristic_read_by_type_req_sent_max_retries):
        # Check if we need to re-send because it's been too long since we saw any response
        # If the primary_service_final_handle is still 1 that means we haven't received any responses
        # so retry sending the request
        time_elapsed = (time.time_ns() - globals.characteristic_read_by_type_req_sent_time)
        if(time_elapsed > globals.retry_timeout):
            globals.characteristic_read_by_type_req_sent_retry_count += 1
            if(globals.characteristic_read_by_type_req_sent_retry_count == globals.characteristic_read_by_type_req_sent_max_retries):
                # We're done trying, consider discovery of secondary services done
                globals.characteristic_read_by_type_req_all_received = True
                return True
            else:
                send_ATT_READ_BY_TYPE_REQ(globals.characteristic_last_read_requested_handle, 0xffff, 0x2803)
                return True

def process_ATT_READ_BY_TYPE_RSP(actual_body_len, dpkt):
    global all_handles_received_values
    global final_characteristic_handle
    global characteristic_last_read_requested_handle
    global characteristic_read_by_type_req_all_received

    # Process opcode_ATT_READ_BY_TYPE_RSP
    if (globals.characteristic_read_by_type_req_sent_time and not globals.characteristic_read_by_type_req_all_received):
        # Look for opcode_ATT_READ_BY_TYPE_REQ
        (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_READ_BY_TYPE_RSP, dpkt)
        if(matched and actual_body_len >= 8):
            entry_len_ACID, = unpack("<B", dpkt.body[7:8])
            vmultiprint(actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode, entry_len_ACID)
            processed_bytes = 8
            while(processed_bytes + entry_len_ACID <= actual_body_len): # Careful not to exceed!
                if(entry_len_ACID == 7):
                    handle, properties, char_value_handle, char_value_UUID = unpack("<HBHH", dpkt.body[processed_bytes:processed_bytes+entry_len_ACID])
                    globals.all_handles_received_values[handle] = v1b(properties) + v2b(char_value_handle) + v2b(char_value_UUID)
                    globals.received_handles[char_value_handle] = v2b(char_value_UUID)
                elif(entry_len_ACID == 21):
                    handle, properties, char_value_handle = unpack("<HBH", dpkt.body[processed_bytes:processed_bytes+5])
                    char_value_UUID = dpkt.body[processed_bytes+5:processed_bytes+21]
                    globals.all_handles_received_values[handle] = v1b(properties) + v2b(char_value_handle) + char_value_UUID
                    globals.received_handles[char_value_handle] = char_value_UUID
                processed_bytes += entry_len_ACID
                vmultiprint(handle, properties, char_value_handle)
                vprint(f"char_value_UUID = {char_value_UUID}")
                globals.final_characteristic_handle = char_value_handle
                globals.received_handles[handle] = b'\x03\x28'

            if(globals.final_characteristic_handle != 0xFFFF):
                # Entire list processed, make a new request
                globals.characteristic_last_read_requested_handle = globals.final_characteristic_handle+1
                send_ATT_READ_BY_TYPE_REQ(globals.characteristic_last_read_requested_handle, 0xffff, 0x2803)
                return True
            else:
                # If the last handle of the last service ended with 0xFFFF then we're done enumerating
                globals.characteristic_read_by_type_req_all_received = True
                return True

def process_ATT_ERROR_RSP_for_ATT_READ_BY_TYPE_REQ(actual_body_len, dpkt):
    global characteristic_read_by_type_req_all_received

    # Look for ATT_ERROR_RSP
    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_ERROR_RSP, dpkt)
    if(matched and actual_body_len >= 11):
        req_opcode_in_error, handle_in_error, error_code = unpack("<BHB", dpkt.body[7:11])
        vmultiprint(req_opcode_in_error, handle_in_error)
        vprint(f"error_code = 0x{error_code:02x} = {globals.att_errorcode_to_str[error_code]}")
        if(req_opcode_in_error == opcode_ATT_READ_BY_TYPE_REQ and error_code == errorcode_0A_ATT_Attribute_Not_Found):
            if(handle_in_error == globals.characteristic_last_read_requested_handle):
                globals.characteristic_read_by_type_req_all_received = True
                print(f"----> ATT_READ_BY_TYPE* phase done for Characteristics, moving to next phase")
                return True

def incoming_characteristic_discovery(actual_body_len, dpkt):
    if(not globals.characteristic_read_by_type_req_sent_time or globals.characteristic_read_by_type_req_all_received):
        return False

    if(process_ATT_READ_BY_TYPE_RSP(actual_body_len, dpkt)):
        return True
    elif(process_ATT_ERROR_RSP_for_ATT_READ_BY_TYPE_REQ(actual_body_len, dpkt)):
        return True
    return False

################################################################################
# Read all Services, Characteristics, and Characteristic Values from all handles
################################################################################
# Decided to put this in GATT instead of ATT file because it's Primary/Secondary Service-aware in skipping handles to read
def outgoing_read_all_handles(actual_body_len, dpkt):
    global all_info_handles_recv
    global handle_read_last_sent_handle

    if(not globals.characteristic_read_by_type_req_all_received):
        return

    if(globals.all_info_handles_recv and not globals.handle_read_req_sent_time):
        # Skip any initial 0x2800/1 Primary/Secondary Service handle(s) (even though it's unlikely for there to be more than 1 consecutive...)
        globals.handle_read_last_sent_handle = get_next_handle_to_att_read(1)
        vprint(f"Sending first ATT REQ w/ handle = {globals.handle_read_last_sent_handle}")
        send_next_ATT_READ_REQ_if_applicable(globals.handle_read_last_sent_handle)
        globals.handle_read_req_sent_time = time.time_ns()
    elif(globals.retry_enabled and not globals.all_handles_read):
        # NOTE: this was occurring reliably when trying to scan a "JBL LIVE660NC-LE" device, but then it went out of range...
        # TODO: See if I can find another one of those and re-try...
        time_elapsed = time.time_ns() - globals.handle_read_req_sent_time
        if(time_elapsed > globals.retry_timeout):
            globals.info_req_last_requested_handle_retry_count += 1
            if(globals.info_req_last_requested_handle_retry_count == globals.secondary_service_request_max_retries):
                # We're done trying, consider reading all handles done
                globals.all_handles_read = True
            else:
                send_next_ATT_READ_REQ_if_applicable(globals.handle_read_last_sent_handle)
                globals.handle_read_req_sent_time = time.time_ns()


def process_ATT_READ_RSP(actual_body_len, dpkt):
    vprint(f"actual_body_len = 0x{actual_body_len:02x}")
    # ATT_READ_RSP
    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_READ_RSP, dpkt)
    if(matched and actual_body_len >= 8):
        globals.all_handles_received_values[globals.handle_read_last_sent_handle] = dpkt.body[7:] # Just dump the data in there!
        vprint(f"Handle 0x{globals.handle_read_last_sent_handle:04x} data raw = {globals.all_handles_received_values[globals.handle_read_last_sent_handle]}")
        vprint(f"Handle 0x{globals.handle_read_last_sent_handle:04x} data decoded as UTF8 = {globals.all_handles_received_values[globals.handle_read_last_sent_handle].decode('utf-8', errors='backslashreplace')}")

        send_next_ATT_READ_REQ_if_applicable(globals.handle_read_last_sent_handle)

    # Malformed/Empty ATT_READ_RSP from AirPods Pro in response to READ_REQ on some handles, that has only the ATT opcode but no data
    # Still, treat this as a response for that handle and move to the next one
    if(att_opcode == opcode_ATT_READ_RSP and actual_body_len == 7):
        vprint(f"Handle 0x{globals.handle_read_last_sent_handle:04x} response with no data! Continuing!")
        globals.all_handles_received_values[globals.handle_read_last_sent_handle] = "No data"

        send_next_ATT_READ_REQ_if_applicable(globals.handle_read_last_sent_handle)

def process_ATT_ERROR_RSP_for_ATT_READ_RSP(actual_body_len, dpkt):
    # Look for ATT_ERROR_RSP
    (matched, actual_body_len, header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode) = is_packet_ATT_type(opcode_ATT_ERROR_RSP, dpkt)
    if(matched and actual_body_len >= 11):
        req_opcode_in_error, handle_in_error, error_code = unpack("<BHB", dpkt.body[7:11])
        vmultiprint(req_opcode_in_error, handle_in_error)
        vprint(f"error_code = 0x{error_code:02x} = {globals.att_errorcode_to_str[error_code]}")
        if(req_opcode_in_error == opcode_ATT_READ_REQ):
            # handle_in_error == 0 is a weird occasional error seen with from Airpods
            if(handle_in_error == globals.handle_read_last_sent_handle or handle_in_error == 0):
                globals.handles_with_error_rsp[globals.handle_read_last_sent_handle] = error_code
                globals.all_handles_received_values[globals.handle_read_last_sent_handle] = f"error_code 0x{error_code:02x} = {globals.att_errorcode_to_str[error_code]}"
                send_next_ATT_READ_REQ_if_applicable(globals.handle_read_last_sent_handle)

            # This seems to be the more correct completion criteria?
            elif(error_code == errorcode_0A_ATT_Attribute_Not_Found and actual_body_len >= 11):
                globals.all_handles_read = True
                print(f"-------> ATT_READ* phase done, moving to next phase")
                print_and_exit()

def incoming_read_all_handles(actual_body_len, dpkt):
    # Don't bother with incoming if outgoing hasn't stated yet, or if everything's complete
    if(not globals.handle_read_req_sent_time or globals.all_handles_read):
        return False

    if(process_ATT_READ_RSP(actual_body_len, dpkt)):
        return True
    elif(process_ATT_ERROR_RSP_for_ATT_READ_RSP(actual_body_len, dpkt)):
        return True
    return False

##############################################################################################################
# Function to call all the sub-functions to meet all the prerequisites of various devices to GET ALL THE GATT!
##############################################################################################################
def stateful_GATT_getter(actual_body_len, dpkt):

    if(globals.skip_apple):
        # See if we can get the GATT ManufacturerName (0x2a29), and if it's set to Apple, and if so
        if(detect_Apple_by_GATT_Manufacturer_Name(actual_body_len, dpkt)):
            vprint("Apple device detected based on GATT Manufacturer Name, exiting!")
            exit(0x0A)

    # ATT type doesn't matter here, we just want to check if it's ATT
    if(actual_body_len >= 7):
        header_ACID, ll_len_ACID, l2cap_len_ACID, cid_ACID, att_opcode = unpack("<BBHHB", dpkt.body[:7])
        # Check if it's ATT (CID = 4) and header says it's l2cap w/o fragmentation (I can't handle fragments yet)
        if(not cid_ACID == 0x0004 or (header_ACID & 0b10 != 0b10)):
            return
        else:
            ####################################################################################
            # Exchange ATT_MTU to try and get more data in less packets
            ####################################################################################
            incoming_ATT_EXCHANGE_MTUs(actual_body_len, dpkt)

            ####################################################################################
            # Some devices (like AppleTV) try to enumerate us. This rejects them.
            ####################################################################################
            manage_peripheral_info_requests(actual_body_len, dpkt)

            ####################################################################################
            # Process opcode_ATT_READ_BY_GROUP_TYPE_RSP for either primary of secondary services
            ####################################################################################
            incoming_service_discovery(actual_body_len, dpkt)

            #################################################################################
            # Process incoming ATT_FIND_INFORMATION_RSP to find all handles, declarations, & descriptors
            # and send further ATT_FIND_INFORMATION_REQs if necessary
            #################################################################################
            incoming_handle_discovery(actual_body_len, dpkt)

            ####################################################################################
            # Receive ATT_READ_BY_TYPE_RSP for Characteristics (0x2803)
            # This was only found to be necessary for things which misbehave like Meta Quest 3S...
            ####################################################################################
            incoming_characteristic_discovery(actual_body_len, dpkt)

            incoming_read_all_handles(actual_body_len, dpkt)

    else:
        # take this opportunity to handle any necessary outgoing ATT packets
        ####################################################################################
        # This handles outgoing ATT_EXCHANGE_MTU_RSP if they've already sent us a REQ,
        # and ATT_EXCHANGE_MTU_REQ if they haven't
        ####################################################################################
        outgoing_ATT_EXCHANGE_MTUs(actual_body_len, dpkt)

        ####################################################################################
        # Request all primary services
        ####################################################################################
        outgoing_service_discovery(actual_body_len, dpkt)

        #################################################################################
        # Send ATT_FIND_INFORMATION_REQs to find all handles, declarations, & descriptors
        #################################################################################
        outgoing_handle_discovery(actual_body_len, dpkt)

        ################################################################################
        # Send ATT_READ_BY_TYPE_REQ for Characteristics (0x2803)
        # This was only found to be necessary for things which misbehave like Meta Quest 3S...
        ################################################################################
        if(outgoing_characteristic_discovery(actual_body_len, dpkt)):
            return

        ################################################################################
        # Read all Values from all handles (regardless of whether they have read propery or not)
        ################################################################################
        outgoing_read_all_handles(actual_body_len, dpkt)