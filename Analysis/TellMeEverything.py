#!/usr/bin/python3

########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

import argparse
from TME.TME_helpers import *
from TME.TME_import import *
from TME.TME_lookup import *
from TME.TME_stats import *
from TME.TME_AdvChan import *
from TME.TME_names import *
from TME.TME_UUID16 import *
from TME.TME_UUID32 import *
from TME.TME_UUID128 import *
from TME.TME_EIR import *
from TME.TME_GATT import *
from TME.TME_BLE2thprint import *
from TME.TME_BTC2thprint import *
from TME.TME_metadata import *
from TME.TME_trackability import *

########################################
# MAIN #################################
########################################

# Main function to handle command line arguments
def main():
    parser = argparse.ArgumentParser(description='Query device names from MySQL tables.')
    parser.add_argument('--output', type=str, required=False, help='Output file name for BTIDES JSON file.')
    parser.add_argument('--bdaddr', type=str, required=False, help='Device bdaddr value.')
    parser.add_argument('--bdaddrregex', type=str, default='', required=False, help='Regex to match a bdaddr value.')
    parser.add_argument('--type', type=int, default=0, help='Device name type (0 or 1) for LE tables.')
    parser.add_argument('--nameregex', type=str, default='', help='Value for REGEXP match against device_name.')
    parser.add_argument('--NOTnameregex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --nameregex, and then remove them from the final results.')
    parser.add_argument('--companyregex', type=str, default='', help='Value for REGEXP match against company name, in IEEE OUIs, or BT Company IDs, or BT Company UUID16s.')
    parser.add_argument('--NOTcompanyregex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --companyregex, and then remove them from the final results.')
    parser.add_argument('--UUID128regex', type=str, default='', help='Value for REGEXP match against UUID128, in advertised UUID128s')
    parser.add_argument('--UUID16regex', type=str, default='', help='Value for REGEXP match against UUID16, in advertised UUID16s')
    parser.add_argument('--MSDregex', type=str, default='', help='Value for REGEXP match against Manufacturer-Specific Data (MSD)')
    parser.add_argument('--UUID128stats', action='store_true', help='Parse the UUID128 data, and output statistics about the most common entries')
    parser.add_argument('--UUID16stats', action='store_true', help='Parse the UUID16 data, and output statistics about the most common entries')
    parser.add_argument('--requireGATT', action='store_true', help='Pass this argument to only print out information for devices which have GATT info')
    parser.add_argument('--require_LL_VERSION_IND', action='store_true', help='Pass this argument to only print out information for devices which have LL_VERSION_IND data')
    parser.add_argument('--require_LMP_VERSION_RES', action='store_true', help='Pass this argument to only print out information for devices which have LMP_VERSION_RES data')
    parser.add_argument('--hideBLEScopedata', action='store_true', help='Pass this argument to not print out the BLEScope data about Android package names associated with vendor-specific GATT UUID128s')

    args = parser.parse_args()
    out_filename = args.output
    bdaddr = args.bdaddr
    bdaddrregex = args.bdaddrregex
    nametype = 0 # Default to non-random
    nametype = args.type
    nameregex = args.nameregex
    notnameregex = args.NOTnameregex
    companyregex = args.companyregex
    notcompanyregex = args.NOTcompanyregex
    uuid128regex = args.UUID128regex
    uuid16regex = args.UUID16regex
    msdregex = args.MSDregex
    uuid16stats = args.UUID16stats
    uuid128stats = args.UUID128stats
    requireGATT = args.requireGATT
    require_LL_VERSION_IND = args.require_LL_VERSION_IND
    require_LMP_VERSION_RES = args.require_LMP_VERSION_RES
    hideBLEScopedata = args.hideBLEScopedata

    # Import metadata v2
    import_metadata_v2()
    import_private_metadata_v2()
    
    # Import any data from CSV files as necessary
    import_nameprint_CSV_data()
    import_private_nameprint_CSV_data()
    import_custom_uuid128_CSV_data()

    # Fill in dictionaries based on standard BT assigned numbers YAML files
    import_CoD_to_names()
    import_bt_CID_to_names()
    import_bt_member_UUID16s_to_names()
    import_bt_spec_version_numbers_to_names()
    import_uuid16_service_names()
    import_uuid16_protocol_names()
    import_gatt_services_uuid16_names()
    import_gatt_declarations_uuid16_names()
    import_gatt_descriptors_uuid16_names()
    import_gatt_characteristic_uuid16_names()
    import_appearance_yaml_data()

    # It could be argued that the ChipMaker_OUI_hash should be pulled out and made static and just read from file.
    # But I'd consider that premature optimization for now.
    # TODO: consider doing this in the future if it adds too much overhead to every invocation
    create_ChipMaker_OUI_hash()

    if(bdaddr is not None):
        bdaddrs = [bdaddr]
    else:
        bdaddrs = []

    ######################################################
    # Options to simply print statistics from the database
    ######################################################

    if(uuid16stats):
        get_uuid16_stats(uuid16stats)
        quit() # Don't do anything other than print the stats and exit

    if(uuid128stats):
        get_uuid128_stats(uuid128stats)
        quit() # Don't do anything other than print the stats and exit

    print(bdaddrs)

    #######################################################
    # Options to search based on specific values or regexes
    #######################################################

    if(bdaddrregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_bdaddr_regex(bdaddrregex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after bdaddrregex processing: {bdaddrs}")

    if(nameregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_name_regex(nameregex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after nameregex processing: {bdaddrs}")

    if(companyregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_company_regex(companyregex)
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after companyregex processing: {bdaddrs}")

    if(msdregex != ""):
        bdaddrs_tmp = get_bdaddrs_by_msd_regex(msdregex)
        print(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after msdregex processing: {bdaddrs}")

    if(uuid128regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_uuid128_regex(uuid128regex)
        print(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after uuid128regex processing: {bdaddrs}")

    if(uuid16regex != ""):
        bdaddrs_tmp = get_bdaddrs_by_uuid16_regex(uuid16regex)
        print(f"bdaddrs_tmp = {bdaddrs_tmp}")
        if(bdaddrs_tmp is not None):
            bdaddrs += bdaddrs_tmp
        print(f"{len(bdaddrs)} bdaddrs after uuid16regex processing: {bdaddrs}")

    if(notcompanyregex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_company_regex(notcompanyregex)
        print(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        print(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;

    if(notnameregex != ""):
        bdaddrs_to_remove = get_bdaddrs_by_name_regex(notnameregex)
        print(bdaddrs_to_remove)
        updated_bdaddrs = []
        for value in bdaddrs:
            if(value in bdaddrs_to_remove):
                continue
            else:
                updated_bdaddrs.append(value)

        print(f"updated_bdaddrs after removals is of length {len(updated_bdaddrs)} compared to original length of bdaddrs = {len(bdaddrs)}")

        bdaddrs = updated_bdaddrs;


    for bdaddr in bdaddrs:
        if(requireGATT):
            if(device_has_GATT_info(bdaddr) != 1):
                continue
        if(require_LL_VERSION_IND):
            if(device_has_LL_VERSION_IND_info(bdaddr) != 1):
                continue
        if(require_LMP_VERSION_RES):
            if(device_has_LMP_VERSION_RES_info(bdaddr) != 1):
                continue
        print("================================================================================")
        print(f"For bdaddr = {bdaddr}:")
        print_ChipPrint(bdaddr)
        print_ChipMakerPrint(bdaddr)                        # Includes BTIDES export
        print_company_name_from_bdaddr("\t", bdaddr, True)
        print_classic_EIR_CID_info(bdaddr)                  # Includes BTIDES export
        print_device_names(bdaddr, nametype)
        print_uuid16s(bdaddr)                               # Includes BTIDES export
        print_uuid16_service_data(bdaddr)                   # Includes BTIDES export
        print_uuid16s_service_solicit(bdaddr)
        print_uuid32s(bdaddr)                               # Includes BTIDES export
        print_uuid32_service_data(bdaddr)                   # Includes BTIDES export
        print_uuid128s(bdaddr)                              # Includes BTIDES export
        print_uuid128_service_data(bdaddr)                   # Includes BTIDES export
        print_uuid128s_service_solicit(bdaddr)
        print_transmit_power(bdaddr, nametype)              # Includes BTIDES export
        print_flags(bdaddr)                                 # Includes BTIDES export
        print_appearance(bdaddr, nametype)                  # Includes BTIDES export
        print_manufacturer_data(bdaddr)
        print_class_of_device(bdaddr)                       # Includes BTIDES export
        print_GATT_info(bdaddr, hideBLEScopedata)           # Includes BTIDES export
        print_BLE_2thprint(bdaddr)                          # Includes BTIDES export
        print_BTC_2thprint(bdaddr)                          # Includes BTIDES export
        print_UniqueIDReport(bdaddr)

        #BTIDES_insert_TxPower(bdaddr, "public", 1)
    
    if(out_filename != None and out_filename != ""):
        write_BTIDES(out_filename)

if __name__ == "__main__":
    main()
