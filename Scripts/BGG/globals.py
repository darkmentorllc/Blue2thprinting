import time

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

# This will be used to estimate the connEventCount
# This starts as 0 to detect that we haven't set it yet,
# and then is set to the first time we receive a packet
first_received_packet_time = 0
connEventCount = 0

######################################################################################
# State transition globals so we can get each data type before moving on to the next
######################################################################################

LLID_data = 2 # 0b10 for unfragmented L2CAP PDUs
LLID_ctrl = 3 # 0b11 for LL control PDUs

ll_packet_states_to_names = {
    0: "Not sent",
    1: "Sent",
    2: "Received",
    3: "Error",
    4: "Rejected",
    5: "Unknown",
    6: "Timeout"
}

ll_packet_names_to_states = {
    "Not sent": 0,
    "Sent": 1,
    "Received": 2,
    "Error": 3,
    "Rejected": 4,
    "Unknown": 5,
    "Timeout": 6
}

class ll_ctrl_state:
    def __init__(self):
        # Use this as a general mutex to stop us from sending a new LL CTRL packet
        # until we've received a response to the most recently sent one
        self.ll_ctrl_pkt_pending = False
        self.last_sent_ll_ctrl_pkt_opcode = None
        self.last_sent_ll_ctrl_pkt_time = None

        ##################################
        # STRONGLY-DESIRED LL_CTRL PACKETS
        ##################################

        # LL_PHY_REQ/RSP state info
        # NOTE: Added in spec 5.0
        self.supported_PHYs = None # Set to None until we get an LL_PHY_REQ/RSP, at which point it's set to the bitmap (0x01 = LE 1M, 0x02 = LE 2M, 0x04 = LE Coded)
        self.PHY_update_sent = False
        self.PHY_updated = False
        self.PHY_info_rejected = False # Set to True if we get a LL_REJECT_IND with a PHY that we don't support

        # LL_LENGTH_REQ/RSP state info
        # NOTE: Added in spec 4.2
        self.ll_length_negotiated = False # This is essentially the quick-check "done" state
        self.ll_length_max_rx_octet = 27 # BT spec default
        self.ll_length_max_tx_octet = 27
        self.ll_length_state = ll_packet_names_to_states["Not sent"]

        # LL_VERSION_IND state info
        # NOTE: In spec 4.0+
        self.ll_version_received = False # This is essentially the quick-check "done" state
        self.ll_version_state = ll_packet_names_to_states["Not sent"]

        # LL_FEATURE_REQ/RSP state info
        # NOTE: In spec 4.0+
        # Or LL_PERIPHERAL_FEATURE_REQ/ state info
        # NOTE: Added in spec 4.1
        self.ll_features_received = False # This is essentially the quick-check "done" state
        self.ll_features_state = ll_packet_names_to_states["Not sent"]
        self.ll_peripheral_features = None
        self.ll_peripheral_features_supports_2M_phy = False # For quicker single-boolean checking

        ##################################
        # NICE-TO-HAVE LL_CTRL PACKETS
        ##################################

        # LL_PING_RSP state info
        # NOTE: Added in spec 4.1
        self.ll_ping_state = ll_packet_names_to_states["Not sent"]

        # LL_CONNECTION_PARAM_REQ/RSP state info
        # NOTE: Added in spec 4.1


current_ll_ctrl_state = ll_ctrl_state()

ll_length_req_sent = False
ll_length_req_sent_time = 0
ll_length_req_recv = False
ll_length_req_recv_time = 0
ll_length_rsp_sent = False
ll_length_rsp_sent_time = 0
ll_length_rsp_recv = False
ll_length_rsp_recv_time = 0
#ll_length_negotiated = False    # Set this to True if they send a LL_LENGTH_RSP, not an error
                                # And also don't do a ATT_EXCHANGE_MTU until this is True. Otherwise
                                # the responses will be fragmented (which we can't currently handle)
# ll_length_max_rx_octet = 0
# ll_length_max_tx_octet = 0

ll_version_ind_sent = False
ll_version_ind_sent_time = 0
ll_version_ind_recv = False

ll_feature_req_sent = False
ll_feature_req_sent_time = 0
ll_feature_rsp_recv = False
ll_feature_rsp_sent = False
ll_feature_rsp_sent_time = 0
ll_peripheral_feature_req_recv = False

ll_phy_req_sent = False
ll_phy_req_sent_time = 0
ll_phy_req_recv = False
ll_phy_req_recv_time = 0
ll_phy_rsp_sent = False
ll_phy_rsp_sent_time = 0
ll_phy_rsp_recv = False
ll_phy_rsp_recv_time = 0
ll_phy_update_ind_sent = False
ll_phy_update_ind_sent_time = 0

# L2CAP state
l2cap_connection_parameter_update_req_sent = False
l2cap_connection_parameter_update_rsp_recv = False
l2cap_credit_based_connection_req_sent = False
l2cap_credit_based_connection_rsp_recv = False
l2cap_le_credit_based_connection_req_sent = False
l2cap_le_credit_based_connection_rsp_recv = False
l2cap_flow_control_credit_ind_sent = False

# ATT state
ATT_CID_bytes = b'\x04\x00'
att_mtu = 23 # Defaults to 23, updated if we get back an ATT_EXCHANGE_MTU_RSP
att_exchange_MTU_req_recv = False
att_exchange_MTU_req_sent = False
att_exchange_MTU_req_sent_time = 0
att_exchange_MTU_rsp_sent = False
att_exchange_MTU_rsp_sent_time = 0
att_exchange_MTU_rsp_recv = False
att_MTU_negotiated = False

att_errorcode_to_str = {
    1: "Invalid Handle",
    2: "Read Not Permitted",
    3: "Write Not Permitted",
    4: "Invalid PDU",
    5: "Insufficient Authentication",
    6: "Request Not Supported",
    7: "Invalid Offset",
    8: "Insufficient Authorization",
    9: "Prepare Queue Full",
    10: "Attribute Not Found",
    11: "Attribute Not Long",
    12: "Encryption Key Size Too Short",
    13: "Invalid Attribute Value Length",
    14: "Unlikely Error",
    15: "Insufficient Encryption",
    16: "Unsupported Group Type",
    17: "Insufficient Resources",
    18: "Database Out of Sync",
    19: "Value Not Allowed",
    0x80: "Unknown Application Error 0",
    0x81: "Unknown Application Error 1",
    0x82: "Unknown Application Error 2",
    0x83: "Unknown Application Error 3",
    0x84: "Unknown Application Error 4",
    0xfc: "Write Request Rejected",
    0xfd: "Client Characteristic Configuration Descriptor Improperly Configured",
    0xfe: "Procedure Already in Progress",
    0xff: "Out of Range"
}

######################################################################################
# Storage for the data returned from the GATT client so it can be output at the end
######################################################################################

received_handles = {}
service_received_handles = {}
all_handles_received_values = {}
characteristic_descriptor_handles = {}
handles_with_error_rsp = {}

# GATT state
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

# SMP state
SMP_CID_bytes = b'\x06\x00'
smp_legacy_pairing_req_sent = False
smp_legacy_pairing_rsp_recv = False
smp_SC_pairing_req_sent = False
smp_SC_pairing_rsp_recv = False
smp_pairing_confirm_legacy_sent = False
smp_pairing_confirm_legacy_recv = False
smp_pairing_random_sent = False
smp_pairing_random_recv = False
preq = None
pres = None
lp_rand_i = None