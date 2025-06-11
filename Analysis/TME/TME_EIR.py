########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

from TME.TME_helpers import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements
from TME.TME_BTIDES_AdvData import *
from TME.TME_BTIDES_EIR import *

########################################
# BTC EIR Device CID
########################################

def print_classic_EIR_CID_info(bdaddr):
    values = (bdaddr,)
    eir_query = "SELECT vendor_id_source, vendor_id, product_id, product_version FROM EIR_bdaddr_to_DevID WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)

    if (len(eir_result) == 0):
        vprint(f"{i1}No BTC Extended Inquiry Result Device info.")
        return
    else:
        qprint(f"{i1}BTC Extended Inquiry Result Device info:")

    for vendor_id_source, vendor_id, product_id, product_version in eir_result:
        if(vendor_id_source == 1):
            qprint(f"{i2}Vendor ID (BT): 0x%04x (%s)" % (vendor_id, BT_CID_to_company_name(vendor_id)))
        elif(vendor_id_source == 2):
            qprint(f"{i2}Vendor ID (USB): 0x%04x (%s)" % (vendor_id, USB_CID_to_company_name(vendor_id)))
        else:
            qprint(f"{i2}: Error: Unknown vendor_id_source = {vendor_id_source}")
        qprint(f"{i2}Product ID: 0x%04x" % product_id)
        qprint(f"{i2}Product Version: 0x%04x" % product_version)

        data = {"length": 9, "vendor_id_source": vendor_id_source, "vendor_id": vendor_id, "product_id": product_id, "version": product_version}
        BTIDES_export_AdvData(bdaddr, 0, 50, type_AdvData_DeviceID, data)

    qprint("")

########################################
# BTC Page Scan Repetition Mode
########################################

# We don't really care about showing this to users... this is more just for BTIDES export
def print_PSRM(bdaddr):
    bdaddr = bdaddr.strip().lower()

    values = (bdaddr,)
    eir_query = "SELECT page_scan_rep_mode FROM EIR_bdaddr_to_PSRM WHERE bdaddr = %s"
    eir_result = execute_query(eir_query, values)

    if (len(eir_result)== 0):
        vprint(f"{i1}No Page Scan Repetition Mode Data found.")
        return
    else:
        qprint(f"{i1}Page Scan Repetition Mode Data:")

    for (page_scan_rep_mode,) in eir_result:
        # Export BTIDES data first
        BTIDES_export_Page_Scan_Repetition_Mode(bdaddr, page_scan_rep_mode)

        # Then human UI output
        qprint(f"{i2}Page Scan Repetition Mode: 0x{page_scan_rep_mode:02x}")
        qprint(f"{i2}In BT Classic Data (DB:EIR_bdaddr_to_PSRM)")

    qprint("")