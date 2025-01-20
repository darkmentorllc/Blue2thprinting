########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

from TME.BT_Data_Types import *
from TME.BTIDES_Data_Types import *
from TME.TME_BTIDES_base import *
#import TME.TME_glob

############################
# Helper "factory functions"
############################

def ff_Page_Scan_Repetition_Mode(page_scan_repetition_mode):
    obj = {"type": type_BTIDES_EIR_PSRM, "page_scan_repetition_mode": page_scan_repetition_mode}
    return obj

def ff_Class_of_Device(CoD_hex_str):
    obj = {"type": type_BTIDES_EIR_CoD, "CoD_hex_str": CoD_hex_str}
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_Page_Scan_Repetition_Mode(bdaddr, page_scan_repetition_mode):
    global BTIDES_JSON
    data = ff_Page_Scan_Repetition_Mode(page_scan_repetition_mode)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "EIRArray")

def BTIDES_export_Class_of_Device(bdaddr, CoD_hex_str):
    global BTIDES_JSON
    data = ff_Class_of_Device(CoD_hex_str)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "EIRArray")

