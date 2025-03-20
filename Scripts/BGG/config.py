# Written by Xeno Kovah
# Copyright (c) 2024 Dark Mentor LLC

# Storage for the data returned from the GATT client so it can be output at the end

received_handles = {}
service_received_handles = {}
all_handles_received_values = {}
characteristic_descriptor_handles = {}
g_handles_with_error_rsp = {}

# TODO: Get rid of some of the below state transition variables
######################################################################################
# State transition globals so we can get each data type before moving on to the next
######################################################################################

ll_length_req_sent = False
ll_length_req_sent_time = 0
ll_length_rsp_recv = False

ll_version_ind_sent = False
ll_version_ind_sent_time = 0
ll_version_ind_recv = False

ll_feature_req_sent = False
ll_feature_req_sent_time = 0
ll_feature_rsp_recv = False

g_att_mtu = 23 # Defaults to 23, updated if we get back an ATT_EXCHANGE_MTU_RSP
att_exchange_MTU_req_sent = False
att_exchange_MTU_rsp_recv = False

read_primary_services_req_sent = False
all_primary_services_recv = False
g_final_primary_service_handle = 1
g_primary_service_handle_ranges_dict = {}

read_secondary_services_req_sent = False
all_secondary_services_recv = False
g_final_secondary_service_handle = 1
g_last_reqested_secondary_service_handle = 1
g_secondary_service_handle_ranges_dict = {}

info_req_sent = False
all_info_handles_recv = False
g_final_handle = 1

characteristic_info_req_sent = False
all_characteristic_handles_recv = False
g_last_sent_read_handle = 1
