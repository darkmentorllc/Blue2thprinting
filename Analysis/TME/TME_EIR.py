########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

#import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_BTIDES_AdvData import *

########################################
# BTC EIR Device CID
########################################

def print_classic_EIR_CID_info(bdaddr):
    eir_query = f"SELECT vendor_id_source, vendor_id, product_id, product_version FROM EIR_bdaddr_to_DevID WHERE device_bdaddr = '{bdaddr}'"
    eir_result = execute_query(eir_query)

    if (len(eir_result) != 0):
        print("\tBTC Extended Inquiry Result Device info:")
    
    for vendor_id_source, vendor_id, product_id, product_version in eir_result:
        if(vendor_id_source == 1):
            print("\t\tVendor ID (BT): 0x%04x (%s)" % (vendor_id, BT_CID_to_company_name(vendor_id)))
        elif(vendor_id_source == 2):
            print("\t\tVendor ID (USB): 0x%04x (%s)" % (vendor_id, USB_CID_to_company_name(vendor_id)))
        else:
            print(f"\t\t: Error: Unknown vendor_id_source = {vendor_id_source}")
        print(f"\t\tProduct ID: 0x%04x" % product_id)
        print(f"\t\tProduct Version: 0x%04x" % product_version)

        data = {"length": 9, "vendor_id_source": vendor_id_source, "vendor_id": vendor_id, "product_id": product_id, "version": product_version}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_DeviceID, data)

    if (len(eir_result) == 0):
        print("\tNo BTC Extended Inquiry Result Device info.")

    print("")