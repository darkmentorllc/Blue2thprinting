########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

import re
from TME.BT_Data_Types import *
from TME.TME_BTIDES_base import generic_SingleBDADDR_insertion_into_BTIDES_first_level_array, generic_DualBDADDR_insertion_into_BTIDES_first_level_array
import TME.TME_glob
from TME.TME_helpers import get_utf8_string_from_hex_string

############################
# Helper "factory functions"
############################


############################
# JSON insertion functions
############################

def BTIDES_export_GPS_coordinate(connect_ind_obj=None, bdaddr=None, random=None, data=None):
    if connect_ind_obj is not None:
        generic_DualBDADDR_insertion_into_BTIDES_first_level_array(connect_ind_obj, data, "GPSArray")
    else:
        generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, random, data, "GPSArray")
