########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
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

    eir_uuid16_query = f"SELECT str_UUID16s FROM EIR_bdaddr_to_UUID16s"
    eir_uuid16_result = execute_query(eir_uuid16_query)
    if(len(eir_uuid16_result) != 0):
        for (str_UUID16s,) in eir_uuid16_result:
            uuid16s = str_UUID16s.split(',')
            for uuid16 in uuid16s:
                if(uuid16 in seen_btc_uuid16s_hash):
                    seen_btc_uuid16s_hash[uuid16] += 1
                else:
                    seen_btc_uuid16s_hash[uuid16] = 1

        print("----= BLUETOOTH CLASSIC RESULTS =----")
        print(f"{len(eir_uuid16_result)} rows of data found in EIR_bdaddr_to_UUID16s")
        print(f"{len(seen_btc_uuid16s_hash)} unique UUID16s found")
#            print(seen_btc_uuid16s_hash)
        sorted_items = sorted(seen_btc_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
        print(f"count \t uuid16 \t company")
        for item in sorted_items:
            (uuid16,count) = item
#                print(TME.TME_glob.bt_member_UUID16s_to_names)
#                print(item)
#                print(uuid16)
#                print(count)
            try:
                decimal_uuid16 = int(uuid16,16)
            except ValueError:
                if(arg != "quiet"): print(f"Skipping '{uuid16}', it can't be converted to an integer")
                continue

            if(decimal_uuid16 in TME.TME_glob.bt_member_UUID16s_to_names.keys()):
                print(f"{count} \t {uuid16} \t {TME.TME_glob.bt_member_UUID16s_to_names[int(uuid16,16)]}")
                company_uuid_count += 1
        print(f"*** {company_uuid_count} UUID16s matched a company name ***")

        ################################################
        # Get the data for LE devices from the database
        ################################################

        le_uuid16_query = f"SELECT str_UUID16s FROM LE_bdaddr_to_UUID16s"
        le_uuid16_result = execute_query(le_uuid16_query)
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
        print()
        print("----= BLUETOOTH LOW ENERGY RESULTS =----")
        print(f"{len(le_uuid16_result)} rows of data found in LE_bdaddr_to_UUID16s")
        print(f"{len(seen_le_uuid16s_hash)} unique UUID16s found")
#            print(seen_le_uuid16s_hash)
        sorted_items = sorted(seen_le_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
        print(f"count \t uuid16 \t company")
        for item in sorted_items:
            (uuid16,count) = item
#                print(TME.TME_glob.bt_member_UUID16s_to_names)
#                print(item)
#                print(uuid16)
#                print(count)
            try:
                decimal_uuid16 = int(uuid16,16)
            except ValueError:
                if(arg != "quiet"): print(f"Skipping '{uuid16}', it can't be converted to an integer")
                continue
            if(decimal_uuid16 in TME.TME_glob.bt_member_UUID16s_to_names.keys()):
                print(f"{count} \t {uuid16} \t {TME.TME_glob.bt_member_UUID16s_to_names[int(uuid16,16)]}")
                company_uuid_count += 1

        print(f"*** {company_uuid_count} UUID16s matched a company name ***")


def get_uuid128_stats(arg):
    seen_btc_uuid128s_hash = {}
    seen_le_uuid128s_hash = {}
    known_uuid_count = 0

    ################################################
    # Get the data for BTC devices from the database
    ################################################

    eir_uuid128_query = f"SELECT str_UUID128s FROM EIR_bdaddr_to_UUID128s"
    eir_uuid128_result = execute_query(eir_uuid128_query)
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

        print("----= BLUETOOTH CLASSIC RESULTS =----")
        print(f"{len(eir_uuid128_result)} rows of data found in EIR_bdaddr_to_UUID128s")
        print(f"{len(seen_btc_uuid128s_hash)} unique UUID128s found")
#            print(seen_btc_uuid128s_hash)
        sorted_items = sorted(seen_btc_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
        print(f"count \t uuid128 \t\t\t\t known info")
        for item in sorted_items:
            (uuid128,count) = item
#                print(item)
#                print(uuid128)
#                print(count)
            if(uuid128 in TME.TME_glob.custom_uuid128_hash):
                known_info = TME.TME_glob.custom_uuid128_hash[uuid128]
                known_uuid_count += 1
            else:
                known_info = ""

            print(f"{count} \t {uuid128} \t {known_info}")

        print(f"*** {known_uuid_count} UUID128s are in the custom_uuid128s.csv database ***")
        known_uuid_count = 0

        ################################################
        # Get the data for LE devices from the database
        ################################################

        le_uuid128_query = f"SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s"
        le_uuid128_result = execute_query(le_uuid128_query)
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

        print()
        print("----= BLUETOOTH LOW ENERGY RESULTS =----")
        print(f"{len(le_uuid128_result)} rows of data found in LE_bdaddr_to_UUID128s")
        print(f"{len(seen_le_uuid128s_hash)} unique UUID128s found")
#            print(seen_le_uuid128s_hash)
        sorted_items = sorted(seen_le_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
        print(f"count \t uuid128 \t\t\t\t known info")
        for item in sorted_items:
            (uuid128,count) = item
#                print(item)
#                print(uuid128)
#                print(count)
            if(uuid128 in TME.TME_glob.custom_uuid128_hash):
                known_info = TME.TME_glob.custom_uuid128_hash[uuid128]
                known_uuid_count += 1
            else:
                known_info = ""

            print(f"{count} \t {uuid128} \t {known_info}")

        print(f"*** {known_uuid_count} UUID128s are in the custom_uuid128s.csv database ***")
