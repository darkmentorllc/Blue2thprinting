# Written by Xeno Kovah
# Copyright (c) 2024-2025 Dark Mentor LLC

######################################################################################
# Misc globals
######################################################################################

# global variable to access hardware
hw = None
_aa = 0

# global variable for pcap writer
pcwriter = None

# global variable for args I will need later for formatting printing
target_bdaddr = ""
target_bdaddr_type_public = False
verbose = True

######################################################################################
# Storage for the data returned from the GATT client so it can be output at the end
######################################################################################

received_handles = {}
service_received_handles = {}
all_handles_received_values = {}
characteristic_descriptor_handles = {}
handles_with_error_rsp = {}

# TODO: Get rid of some of the below state transition variables? Things that aren't actually shared between files could just be intra-file globals...
######################################################################################
# State transition globals so we can get each data type before moving on to the next
######################################################################################

# Use this as a general mutex to stop us from sending a new LL CTRL packet
# until we've received a response to the most recently sent one
# TODO: Note, this can DOS us though, so we'll want to add better timeout & retry capability
ll_ctrl_pkt_pending = False

ll_length_req_sent = False
ll_length_req_sent_time = 0
ll_length_rsp_recv = False
ll_length_rsp_supported = False # Set this to True if they send a LL_LENGTH_RSP, not an error
                                # And also don't do a ATT_EXCHANGE_MTU until this is True. Otherwise
                                # the responses will be fragmented (which we can't currently handle)

ll_version_ind_sent = False
ll_version_ind_sent_time = 0
ll_version_ind_recv = False

ll_feature_req_sent = False
ll_feature_req_sent_time = 0
ll_feature_rsp_recv = False
ll_feature_rsp_sent_time = 0
ll_peripheral_feature_req_recv = False

ll_phy_req_sent = False
ll_phy_req_sent_time = 0
ll_phy_req_recv = False
ll_phy_req_recv_time = 0
ll_phy_rsp_sent = False
ll_phy_rsp_sent_time = 0
ll_phy_rsp_recv = False
ll_phy_rsp_sent_time = 0

att_mtu = 23 # Defaults to 23, updated if we get back an ATT_EXCHANGE_MTU_RSP
att_exchange_MTU_req_sent = False
att_exchange_MTU_req_sent_time = 0
att_exchange_MTU_rsp_recv = False

read_primary_services_req_sent = False
all_primary_services_recv = False
final_primary_service_handle = 1
primary_service_handle_ranges_dict = {}

read_secondary_services_req_sent = False
all_secondary_services_recv = False
final_secondary_service_handle = 1
last_reqested_secondary_service_handle = 1
secondary_service_handle_ranges_dict = {}

info_req_sent = False
all_info_handles_recv = False
final_handle = 1

characteristic_info_req_sent = False
all_characteristic_handles_recv = False
last_sent_read_handle = 1

smp_legacy_pairing_req_sent = False
smp_legacy_pairing_rsp_recv = False
smp_SC_pairing_req_sent = False
smp_SC_pairing_rsp_recv = False
