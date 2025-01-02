########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

import TME.TME_glob
from TME.TME_helpers import *

def get_uuid16_stats(arg):
    seen_btc_uuid16s_hash = {}
    seen_le_uuid16s_hash = {}
    company_uuid_count = 0

    ################################################
    # Get the data for BTC devices from the database
    ################################################

    eir_uuid16_query = "SELECT str_UUID16s FROM EIR_bdaddr_to_UUID16s"
    eir_uuid16_result = execute_query(eir_uuid16_query, ())
    if(len(eir_uuid16_result) != 0):
        for (str_UUID16s,) in eir_uuid16_result:
            uuid16s = str_UUID16s.split(',')
            for uuid16 in uuid16s:
                if(uuid16 in seen_btc_uuid16s_hash):
                    seen_btc_uuid16s_hash[uuid16] += 1
                else:
                    seen_btc_uuid16s_hash[uuid16] = 1

        qprint("----= BLUETOOTH CLASSIC RESULTS =----")
        qprint(f"{len(eir_uuid16_result)} rows of data found in EIR_bdaddr_to_UUID16s")
        qprint(f"{len(seen_btc_uuid16s_hash)} unique UUID16s found")
#            qprint(seen_btc_uuid16s_hash)
        sorted_items = sorted(seen_btc_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid16 \t company")
        for item in sorted_items:
            (uuid16,count) = item
#                qprint(TME.TME_glob.bt_member_UUID16s_to_names)
#                qprint(item)
#                qprint(uuid16)
#                qprint(count)
            try:
                decimal_uuid16 = int(uuid16,16)
            except ValueError:
                if(arg != "quiet"): qprint(f"Skipping '{uuid16}', it can't be converted to an integer")
                continue

            if(decimal_uuid16 in TME.TME_glob.bt_member_UUID16s_to_names.keys()):
                qprint(f"{count} \t {uuid16} \t {TME.TME_glob.bt_member_UUID16s_to_names[int(uuid16,16)]}")
                company_uuid_count += 1
        qprint(f"*** {company_uuid_count} UUID16s matched a company name ***")

        ################################################
        # Get the data for LE devices from the database
        ################################################

        le_uuid16_query = "SELECT str_UUID16s FROM LE_bdaddr_to_UUID16s"
        le_uuid16_result = execute_query(le_uuid16_query, ())
        if(len(le_uuid16_result) != 0):
            for (str_UUID16s,) in le_uuid16_result:
                if(isinstance(str_UUID16s, str)):
                    uuid16s = str_UUID16s.split(',')
                    for uuid16 in uuid16s:
                        if(uuid16 in seen_le_uuid16s_hash):
                            seen_le_uuid16s_hash[uuid16] += 1
                        else:
                            seen_le_uuid16s_hash[uuid16] = 1

        company_uuid_count = 0
        qprint()
        qprint("----= BLUETOOTH LOW ENERGY RESULTS =----")
        qprint(f"{len(le_uuid16_result)} rows of data found in LE_bdaddr_to_UUID16s")
        qprint(f"{len(seen_le_uuid16s_hash)} unique UUID16s found")
#            qprint(seen_le_uuid16s_hash)
        sorted_items = sorted(seen_le_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid16 \t company")
        for item in sorted_items:
            (uuid16,count) = item
#                qprint(TME.TME_glob.bt_member_UUID16s_to_names)
#                qprint(item)
#                qprint(uuid16)
#                qprint(count)
            try:
                decimal_uuid16 = int(uuid16,16)
            except ValueError:
                if(arg != "quiet"): qprint(f"Skipping '{uuid16}', it can't be converted to an integer")
                continue
            if(decimal_uuid16 in TME.TME_glob.bt_member_UUID16s_to_names.keys()):
                qprint(f"{count} \t {uuid16} \t {TME.TME_glob.bt_member_UUID16s_to_names[int(uuid16,16)]}")
                company_uuid_count += 1

        qprint(f"*** {company_uuid_count} UUID16s matched a company name ***")


def get_uuid128_stats(arg):
    seen_btc_uuid128s_hash = {}
    seen_le_uuid128s_hash = {}
    known_uuid_count = 0

    ################################################
    # Get the data for BTC devices from the database
    ################################################

    eir_uuid128_query = "SELECT str_UUID128s FROM EIR_bdaddr_to_UUID128s"
    eir_uuid128_result = execute_query(eir_uuid128_query, ())
    if(len(eir_uuid128_result) != 0):
        for (str_UUID128s,) in eir_uuid128_result:
            if(str_UUID128s == ''):
                continue
            uuid128s = str_UUID128s.split(',')
            for uuid128 in uuid128s:
                if(uuid128 in seen_btc_uuid128s_hash):
                    seen_btc_uuid128s_hash[uuid128] += 1
                else:
                    seen_btc_uuid128s_hash[uuid128] = 1

        qprint("----= BLUETOOTH CLASSIC RESULTS =----")
        qprint(f"{len(eir_uuid128_result)} rows of data found in EIR_bdaddr_to_UUID128s")
        qprint(f"{len(seen_btc_uuid128s_hash)} unique UUID128s found")
#            qprint(seen_btc_uuid128s_hash)
        sorted_items = sorted(seen_btc_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid128 \t\t\t\t known info")
        for item in sorted_items:
            (uuid128,count) = item
#                qprint(item)
#                qprint(uuid128)
#                qprint(count)
            if(uuid128 in TME.TME_glob.custom_uuid128_hash):
                known_info = TME.TME_glob.custom_uuid128_hash[uuid128]
                known_uuid_count += 1
            else:
                known_info = ""

            qprint(f"{count} \t {uuid128} \t {known_info}")

        qprint(f"*** {known_uuid_count} UUID128s are in the custom_uuid128s.csv database ***")
        known_uuid_count = 0

        ################################################
        # Get the data for LE devices from the database
        ################################################

        le_uuid128_query = "SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s"
        le_uuid128_result = execute_query(le_uuid128_query, ())
        if(len(le_uuid128_result) != 0):
            for (str_UUID128s,) in le_uuid128_result:
                if(str_UUID128s == ''):
                    continue
                if(isinstance(str_UUID128s, str)):
                    uuid128s = str_UUID128s.split(',')
                    for uuid128 in uuid128s:
                        if(uuid128 in seen_le_uuid128s_hash):
                            seen_le_uuid128s_hash[uuid128] += 1
                        else:
                           seen_le_uuid128s_hash[uuid128] = 1

        qprint()
        qprint("----= BLUETOOTH LOW ENERGY RESULTS =----")
        qprint(f"{len(le_uuid128_result)} rows of data found in LE_bdaddr_to_UUID128s")
        qprint(f"{len(seen_le_uuid128s_hash)} unique UUID128s found")
#            qprint(seen_le_uuid128s_hash)
        sorted_items = sorted(seen_le_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid128 \t\t\t\t known info")
        for item in sorted_items:
            (uuid128,count) = item
#                qprint(item)
#                qprint(uuid128)
#                qprint(count)
            if(uuid128 in TME.TME_glob.custom_uuid128_hash):
                known_info = TME.TME_glob.custom_uuid128_hash[uuid128]
                known_uuid_count += 1
            else:
                known_info = ""

            qprint(f"{count} \t {uuid128} \t {known_info}")

        qprint(f"*** {known_uuid_count} UUID128s are in the custom_uuid128s.csv database ***")
