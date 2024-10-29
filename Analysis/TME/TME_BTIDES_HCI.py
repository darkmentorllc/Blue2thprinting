########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2024
########################################

# This file is to export data that conforms to the
# BlueTooth Information Data Exchange Schema (BTIDES!)
# as given here: https://darkmentor.com/BTIDES_Schema/BTIDES.html

#import TME.TME_glob
from TME.TME_BTIDES_base import *
from TME.TME_glob import verbose_BTIDES, BTIDES_JSON

############################
# Helper "factory functions"
############################  

event_code_HCI_Remote_Name_Request_Complete          = 7

status_SUCCESS = 0

# TODO: we need to update database to keep track of status
def ff_HCI_Remote_Name_Request_Complete(name):    
    obj = {"event_code": event_code_HCI_Remote_Name_Request_Complete, "status": status_SUCCESS, "remote_name": name}
    if(verbose_BTIDES):
        obj["event_code_str"] = "HCI_Remote_Name_Request_Complete"
    return obj

# TODO: Pretty sure this is where OO programming would save me a lot of copy-paste...
############################
# JSON insertion functions
############################
# All functions follow this flow:
# Opens existing JSON object, searches for an entry for the given bdaddr
# If no entry already exists, it creates a new one
# If an entry already exists, it tries to insert the data into a HCIArray entry
#  If an existing HCIArray entry already exists, this is done
#  If no HCIArray exists, it creates one

def BTIDES_export_HCI_Name_Response(bdaddr, name):
    global BTIDES_JSON
    ###print(BTIDES_JSON)
    entry = lookup_entry(bdaddr, 0)
    ###print(json.dumps(entry, indent=2))
    if (entry == None):
        # There is no entry yet for this BDADDR. Insert a brand new one
        base = ff_base(bdaddr, 0)
        base["HCIArray"] = [ ff_HCI_Remote_Name_Request_Complete(name) ]
        #print(json.dumps(base, indent=2))
        BTIDES_JSON.append(base)
        #print(json.dumps(BTIDES_JSON, indent=2))
        return
    else:
        if("HCIArray" not in entry.keys()):
            # There is an entry for this BDADDR but not yet any HCIArray entries, so just insert ours
            entry["HCIArray"] = [ ff_HCI_Remote_Name_Request_Complete(name) ]
            return
        else:
            # There is an entry for this BDADDR, and HCIArray entries, so check if ours already exists, and if so, we're done
            for hci_entry in entry["HCIArray"]:
                ###print(AdvChanEntry)
                if(hci_entry != None and "event_code" in hci_entry.keys() and hci_entry["event_code"] == event_code_HCI_Remote_Name_Request_Complete and 
                   hci_entry["status"] == status_SUCCESS and hci_entry["remote_name"] == name):
                    # We already have the entry we would insert, so just go ahead and return
                    #print("BTIDES_export_HCI_Name_Response: found existing match. Nothing to do. Returning.")
                    ###print(json.dumps(BTIDES_JSON, indent=2))
                    return
            # If we get here, we exhaused all ll_entries without a match. So insert our new entry into HCIArray 
            entry["HCIArray"].append(ff_HCI_Remote_Name_Request_Complete(name))
            ###print(json.dumps(BTIDES_JSON, indent=2))
            return