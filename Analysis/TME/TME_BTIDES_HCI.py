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
import TME.TME_glob

############################
# Helper "factory functions"
############################

# TODO: we need to update database to keep track of status
def ff_HCI_Remote_Name_Request_Complete(name):
    obj = {"event_code": event_code_HCI_Remote_Name_Request_Complete, "status": type_BTIDES_status_SUCCESS, "remote_name": name}
    if(TME.TME_glob.verbose_BTIDES):
        obj["event_code_str"] = "HCI_Remote_Name_Request_Complete"
    return obj

############################
# JSON insertion functions
############################

def BTIDES_export_HCI_Name_Response(bdaddr, name):
    global BTIDES_JSON
    data = ff_HCI_Remote_Name_Request_Complete(name)
    generic_SingleBDADDR_insertion_into_BTIDES_first_level_array(bdaddr, 0, data, "HCIArray")

