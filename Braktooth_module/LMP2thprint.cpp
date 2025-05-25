#include "ModulesInclude.hpp"
#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <unistd.h> // For sleep


// Filters
static const char *filter_fhs;
static const char *filter_lmp_accepted;
static const char *filter_lmp_not_accepted;
static const char *filter_lmp_features_req;
static const char *filter_lmp_features_res;
static const char *filter_lmp_features_res_ext;
static const char *filter_lmp_version_req;
static const char *filter_lmp_version_res;
static const char *filter_lmp_name_res;
static const char *filter_lmp_switch_req;
static const char *filter_lmp_ping_res;
static const char *filter_lmp_encryption_key_size_req;

// Vars

char * BTC2TH_LOG_PATH = "/home/pi/Blue2thprinting/Logs/BTC_2THPRINT.log";

FILE * glogfile;

unsigned long long gAllRequiredResponses = 0;
#define RR_LMP_FEATURES_RES			(1 << 0)
#define RR_LMP_FEATURES_RES_EXT			(1 << 1)
#define RR_LMP_VERSION_RES			(1 << 2)
#define RR_LMP_NAME_RES				(1 << 3)
#define RR_ALL_DONE				(RR_LMP_FEATURES_RES | \
						RR_LMP_FEATURES_RES_EXT | \
						RR_LMP_VERSION_RES | \
						RR_LMP_NAME_RES)

// Setup
static const char *module_name()
{
    return "TEST2_RX_BYPASS";
}

unsigned char gSent_LMP_features_req = 0;
unsigned char gRecv_LMP_features_req = 0;
unsigned char gSent_LMP_features_req_ext = 0;
unsigned char gRecv_LMP_features_req_ext = 0;
unsigned char gSent_LMP_version_req = 0;
unsigned char gRecv_LMP_version_res = 0;
unsigned char gSent_LMP_name_req = 0;
unsigned char gRecv_LMP_name_req = 0;

unsigned char gMaxExtendedFeaturePages = 0;

// Actual max size = 256, but because they could set Name Offset to 255 and then send more data
// that would overflow the buffer. So I'm making the buffer 512 so I don't need to add a bunch of
// checks for overflow, and I can just use the ACID index and lengths in the naive way
char gName[512] = {0};
int g_max_offset_so_far = 0;
// Global flag for whether we're expecting more data from LMP_name_res packets, and therefore need to send new LMP_name_req packets
char gMoreNameNeeded = 0;

// For extraction from FHS
unsigned char gBDADDR[6] = {0};

/******* EXPERIMENTAL STUFF *******/
/*******       BEGIN        *******/

unsigned char gExperimental = 0;
#define MALFORMED_LMP_FEATURES_REQ			1 << 0
unsigned char gSent_malformed_LMP_features_req = 0;
unsigned char gRecv_malformed_LMP_features_req = 0;
unsigned long long legit_lmp_features_res = 0;
#define MALFORMED_LMP_FEATURES_REQ_EXT			1 << 1
unsigned char gSent_malformed_LMP_features_req_ext = 0;
unsigned char gRecv_malformed_LMP_features_req_ext = 0;
#define LMP_PING_REQ					1 << 2
unsigned char gSent_LMP_ping_req = 0;
unsigned char gRecv_LMP_ping_req = 0;
#define LMP_SWITCH_REQ					1 << 3
unsigned char gSent_LMP_switch_req = 0;
unsigned char gRecv_LMP_switch_req = 0;
#define LMP_ENCRYPTION_KEY_SIZE_REQ			1 << 4
unsigned char gSent_LMP_encryption_key_size_req = 0;
unsigned char gRecv_LMP_encryption_key_size_req = 0;

// Note down any pages that we get responses for
// that are above the original self-professed supported
// ranges, that have non-zero values. These are either
// bit-flips, or info-leaks. We can determine which
// by re-requesting that page and seeing if we get
// the same value
unsigned long long int gInfoLeak[256];

/*******       END          *******/
/******* EXPERIMENTAL STUFF *******/

// LMP_features_req packet
static uint8_t lmp_features_req_packet[] = \
{0x99, 0x03, 0x4f, 0x00,				// Baseband + ACL Header
0x4e,							// LSB TID = 0 + LMP opcode (39) << 1 = 0x4e
0xbf, 0xee, 0xcd, 0xfe, 0xdb, 0xff, 0x7b, 0x87};	// Typical observed features

// LMP_features_req_ext packet
static uint8_t lmp_features_req_ext_packet[] = \
{0x99, 0x3, 0x67, 0x0,					// Baseband + ACL Header
0xfe,							// LSB TID = 0 + LMP *extended* opcode prefix (127) << 1 = 0xfe
0x3, 0x1, 0x2,						// LMP opcode 3, feature page 1, of maximum 2 feature pages
0xb, 0x00, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0};		// Commonly observed value

// LMP_version_req packet
static uint8_t lmp_version_req_packet[] = \
{0x19, 0x00, 0x37, 0x00,				// Baseband + ACL Header
0x4a,							// LSB TID = 0 + LMP opcode (37) << 1 = 0x4a
0x13, 0x60, 0x00, 0x0e, 0x03};				// 1 byte LMP version (5.3), 2 byte company, 2 byte LMP sub-version TODO: randomize the last 2!

// LMP_name_req packet
static uint8_t lmp_name_req_packet[] = \
{0x99, 0x03, 0x17, 0x00,				// Baseband + ACL Header
0x02,							// LSB TID = 0 + LMP opcode (1) << 1 = 0x02 
0x00};							// Name offset (0)

// LMP_encryption_key_size_req packet
static uint8_t lmp_encryption_key_size_req_packet[] = \
{0x99, 0x03, 0x17, 0x00,				// Baseband + ACL Header
0x20,							// LSB TID = 0 + LMP opcode (16) << 1 = 0x20 
0x01};							// Proposed key size (1)


/******* EXPERIMENTAL STUFF *******/
/*******       BEGIN        *******/


// MALFORMED LMP_features_req packet that violates "reserved" bits being 0, and instead setting them to 1, to act as if we support all possible features
static uint8_t malformed_lmp_features_req_packet[] = \
{0x99, 0x03, 0x4f, 0x00,				// Baseband + ACL Header
0x4e,							// LSB TID = 0 + LMP opcode (39) << 1 = 0x4e
0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};	// Invalid features with everything, including reserved bits that should be 0, set

// MALFORMED LMP_features_req_ext packet
static uint8_t malformed_lmp_features_req_ext_packet[] = \
{0x99, 0x3, 0x67, 0x0,					// Baseband + ACL Header
0xfe,							// LSB TID = 0 + LMP *extended* opcode prefix (127) << 1 = 0xfe
0x3, 0x1, 0xff,						// LMP opcode 3, feature page 1, of maximum 255 feature pages
0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};	// ALL the features!

// LMP_switch_req packet
static uint8_t lmp_switch_req_packet[] = \
{0x99, 0x02, 0x2f, 0x00,				// Baseband + ACL Header
0x27,							// LSB TID = 0 + LMP opcode (39) << 1 = 0x27
0xFF, 0xFF, 0x00, 0x00};				// "switch instant", a time on the master's clock when to switch roles
							// unfortunately I have no idea what the master's clock is at, so for now
							// I'm just trying values and seeing what happens

// LMP_ping_req packet
static uint8_t lmp_ping_req_packet[] = \
{0x99, 0x3, 0x67, 0x0,					// Baseband + ACL Header
0xfe,							// LSB TID = 0 + LMP *extended* opcode prefix (127) << 1 = 0xfe
0x21};							// LMP opcode 33

/*******       END          *******/
/******* EXPERIMENTAL STUFF *******/

static int setup(void *p)
{

    // Change required configuration for exploit
    Config *config = (Config *)p;
    config->options.auto_start = true;
    config->bluetooth.disable_role_switch = false;
    config->bluetooth.bridge_hci = true;
    config->bluetooth.intercept_tx = true;
    config->bluetooth.lmp_sniffing = true;
    config->bluetooth.rx_bypass = true; // Bypass ESP32 LMP stack, forward TX/RX to host
    config->bluetooth.rx_bypass_on_demand = false;
    config->fuzzing.enable_duplication = false;
    config->fuzzing.enable_mutation = false;

    filter_fhs = packet_register_filter("btbbd.type == 0x2");
    filter_lmp_accepted = packet_register_filter("btbrlmp.op == 3");
    filter_lmp_not_accepted = packet_register_filter("btbrlmp.op == 4");
    filter_lmp_features_req = packet_register_filter("btbrlmp.op == 39");
    filter_lmp_features_res = packet_register_filter("btbrlmp.op == 40");
    filter_lmp_features_res_ext = packet_register_filter("btbrlmp.op == 127 && btbrlmp.eop == 4");
    filter_lmp_ping_res = packet_register_filter("btbrlmp.op == 127 && btbrlmp.eop == 34");
    filter_lmp_version_req = packet_register_filter("btbrlmp.op == 37");
    filter_lmp_version_res = packet_register_filter("btbrlmp.op == 38");
    filter_lmp_switch_req = packet_register_filter("btbrlmp.op == 19");
    filter_lmp_name_res = packet_register_filter("btbrlmp.op == 2");
    filter_lmp_encryption_key_size_req = packet_register_filter("btbrlmp.op == 16");

    glogfile = fopen(BTC2TH_LOG_PATH, "a"); // Open file in append mode
    if (glogfile == NULL) {
        printf("Failed to open the file.\n");
        return 1;
    }
    fprintf(glogfile, "BTC_2THPRINT: NEW RUN\n");

    return 0;
}

// TX
static int tx_pre_dissection(uint8_t *pkt_buf, int pkt_length, void *p)
{
    if (IS_FHS(pkt_buf)){
	printf("2THPRINT: Saw FHS pre\n");
    }
    return 0;
}

static int tx_post_dissection(uint8_t *pkt_buf, int pkt_length, void *p)
{
    if (IS_FHS(pkt_buf)){
	printf("2THPRINT: Saw FHS post\n");
    }

    return 0;
}

#define MAX_RETRY 3

// RX
static int rx_pre_dissection(uint8_t *pkt_buf, int pkt_length, void *p)
{

    // Packets we'd like to hear the response for
    packet_set_filter(filter_lmp_accepted);
    packet_set_filter(filter_lmp_not_accepted);
    packet_set_filter(filter_lmp_features_res);
    packet_set_filter(filter_lmp_features_res_ext);
    packet_set_filter(filter_lmp_version_res);
    packet_set_filter(filter_lmp_name_res);
    packet_set_filter(filter_lmp_ping_res);
    packet_set_filter(filter_lmp_encryption_key_size_req);

    // Send each of the packets we're interested in for 2thprinting purposes
    if(!gSent_LMP_features_req){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_features_req_packet;
	m->pkt_len = sizeof(lmp_features_req_packet);
        gSent_LMP_features_req++;
	return 0;
    }

    if(gSent_LMP_features_req_ext == 0){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_features_req_ext_packet;
	m->pkt_len = sizeof(lmp_features_req_ext_packet);
        gSent_LMP_features_req_ext++;
	return 0;
    }

    // gMaxExtendedFeaturePages is typically either 1 or 2 for well-behaved devices
    if(gRecv_LMP_features_req_ext && gSent_LMP_features_req_ext < gMaxExtendedFeaturePages){
	// Update the feature page to be +1
	lmp_features_req_ext_packet[6]+=1;
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_features_req_ext_packet;
	m->pkt_len = sizeof(lmp_features_req_ext_packet);
        gSent_LMP_features_req_ext++;
	return 0;
    }

    // FIXME: This is an opportunistic place to send the 0th and 1st request. But if we need a total of 3 reqs, this will fail (Is that still true?)
    // FIXME: This is why we need the capability to send on LMP_name_res instead (but that currently crashes)
    if(!gSent_LMP_name_req || gMoreNameNeeded){
        if(gMoreNameNeeded) wd_log_y("2THPRINT: Sending LMP_name_req to get additional data");
        lmp_name_req_packet[5] = (char)g_max_offset_so_far; //Update the Name Offset field in output LMP_name_req
        module_request_t *m = (module_request_t *)p;
        m->tx_count = 1;
        m->pkt_buf = lmp_name_req_packet;
        m->pkt_len = sizeof(lmp_name_req_packet);
	gSent_LMP_name_req++;
        gMoreNameNeeded = 0;
	return 0;
    }

    if(!gSent_LMP_version_req){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_version_req_packet;
	m->pkt_len = sizeof(lmp_version_req_packet);
        gSent_LMP_version_req++;
	return 0;
    }


    /***************EXPERIMENTAL***************/
    /***************EXPERIMENTAL***************/
    /***************EXPERIMENTAL***************/

    // These are things we only want to try after we get back responses to regular info requests
    if((gExperimental & MALFORMED_LMP_FEATURES_REQ) && gSent_malformed_LMP_features_req == 0){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = malformed_lmp_features_req_packet;
	m->pkt_len = sizeof(malformed_lmp_features_req_packet);
        gSent_malformed_LMP_features_req++;
	return 0;
    }

    if((gExperimental & MALFORMED_LMP_FEATURES_REQ_EXT) && gSent_malformed_LMP_features_req_ext < 255){
	// Update the feature page to be one more
	malformed_lmp_features_req_ext_packet[6]+=1;
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = malformed_lmp_features_req_ext_packet;
	m->pkt_len = sizeof(malformed_lmp_features_req_ext_packet);
        gSent_malformed_LMP_features_req_ext++;
	return 0;
    }

    if((gExperimental & LMP_SWITCH_REQ) && !gSent_LMP_switch_req){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_switch_req_packet;
	m->pkt_len = sizeof(lmp_switch_req_packet);
        gSent_LMP_switch_req++;
	return 0;
    }

    if((gExperimental & LMP_ENCRYPTION_KEY_SIZE_REQ) && !gSent_LMP_encryption_key_size_req){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_encryption_key_size_req_packet;
	m->pkt_len = sizeof(lmp_encryption_key_size_req_packet);
        gSent_LMP_encryption_key_size_req++;
	return 0;
    }


    if((gExperimental & LMP_PING_REQ) && !gSent_LMP_ping_req){
	module_request_t *m = (module_request_t *)p;
	m->tx_count = 1;
	m->pkt_buf = lmp_ping_req_packet;
	m->pkt_len = sizeof(lmp_ping_req_packet);
        gSent_LMP_ping_req++;
	return 0;
    }

    return 0;
}

// Offset where first byte of Name is found in LMP_name_res packet
#define LMP_OPCODE_PKT_OFFSET           4
#define LMP_DATA_PKT_OFFSET             5
#define LMP_NAME_OFFSET_PKT_OFFSET      5
#define LMP_NAME_LEN_PKT_OFFSET         6
#define LMP_NAME_DATA_PKT_OFFSET        7
#define LMP_NAME_DATA_SIZE_MAX          14

static int rx_post_dissection(uint8_t *pkt_buf, int pkt_length, void *p)
{
    int i = 0, j = 0;


    //******** PRINT ERROR INFO FOR LMP_NOT_ACCEPTED *********//
    if (packet_read_filter(filter_lmp_not_accepted))
    {
        wd_log_y("2THPRINT: WARNING: LMP_not_accepted RX detected");
        printf("2THPRINT: WARNING: LMP_not_accepted in response to opcode 0x%02X\n", pkt_buf[LMP_DATA_PKT_OFFSET]);
        printf("2THPRINT: WARNING: LMP_not_accepted error code 0x%02X\n", pkt_buf[LMP_DATA_PKT_OFFSET+1]);
	return 0;
    }

    //******** PRINT INFO FOR LMP_ACCEPTED *********//
    if (packet_read_filter(filter_lmp_accepted))
    {
        wd_log_y("2THPRINT: WARNING: LMP_accepted RX detected");
        printf("2THPRINT: WARNING: LMP_accepted in response to opcode 0x%02X\n", pkt_buf[LMP_DATA_PKT_OFFSET]);
	// If they accepted our LMP_encryption_key_size_req with size of 1, that means they may be vulnerable to KNOB
	// (However, in practice, some systems may accept, and then tear down the connection after the fact.
	//  The only way to be fully sure something's vuln to KNOB is to fully establish a 1 byte key.)
	if(pkt_buf[LMP_DATA_PKT_OFFSET] == 16){
		printf("BTC_2THPRINT: COMMENT: KNOB: ACCEPTED 1 BYTE KEY PROPOSAL\n");
		fprintf(glogfile, "BTC_2THPRINT: COMMENT: KNOB: ACCEPTED 1 BYTE KEY PROPOSAL\n");
	}

	return 0;
    }

    //******** CAPTURE BASIC FEATURES *********//
    if (packet_read_filter(filter_lmp_features_res))
    {
	gAllRequiredResponses |= RR_LMP_FEATURES_RES;
        wd_log_y("2THPRINT: LMP_features_res RX detected");
        printf("2THPRINT: LMP_features_res bytes: ");
        for(i = 0; i < 8; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
        }
        printf("\n");
	gRecv_LMP_features_req++;

	if(!(gExperimental & MALFORMED_LMP_FEATURES_REQ)){
		legit_lmp_features_res = *(unsigned long long *)&(pkt_buf[LMP_DATA_PKT_OFFSET]);
	}
	else{
		if(legit_lmp_features_res != *(unsigned long long *)&(pkt_buf[LMP_DATA_PKT_OFFSET])){
			printf("BTC_2THPRINT: COMMENT LMP_FEATURES_RES: FOUND DEVICE THAT RESPONDS DIFFERENTLY DEPENDING ON SENDER'S LMP_FEATURES_REQ\n");
			fprintf(glogfile, "BTC_2THPRINT: COMMENT LMP_FEATURES_RES: FOUND DEVICE THAT RESPONDS DIFFERENTLY DEPENDING ON SENDER'S LMP_FEATURES_REQ\n");
		}
		else{
			printf("BTC_2THPRINT: COMMENT LMP_FEATURES_RES: RESPONSE DOESN'T DIFFER BASED ON SENDER'S LMP_FEATURES_REQ\n");
			fprintf(glogfile, "BTC_2THPRINT: COMMENT LMP_FEATURES_RES: RESPONSE DOESN'T DIFFER BASED ON SENDER'S LMP_FEATURES_REQ\n");
		}
	}

	// PRINT TO LOG FOR POST-PROCESSING
	printf("BTC_2THPRINT: LMP_OP_");
	fprintf(glogfile, "BTC_2THPRINT: LMP_OP_");
	// Opcode:
        printf("0x%02X ", pkt_buf[4]>>1);
        fprintf(glogfile, "0x%02X ", pkt_buf[4]>>1);
	// Raw bytes
        for(i = 0; i < 8; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
            fprintf(glogfile, "0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
        }
	printf("\n");
	fprintf(glogfile, "\n");
        return 0;
    }

    //******** CAPTURE EXTENDED FEATURES *********//
    if (packet_read_filter(filter_lmp_features_res_ext))
    {
	unsigned char feature_page_num = pkt_buf[6];
	unsigned char max_page_num = pkt_buf[7];

	gAllRequiredResponses |= RR_LMP_FEATURES_RES_EXT;

        wd_log_y("2THPRINT: LMP_features_res_ext RX detected");
	// We send 2 requests, but the device may only support 1 (or none).
	// So throw away any replies with feature_page_num > max_page_num
	// until we're running in experimental mode
	if(!gExperimental && feature_page_num > max_page_num){
	        wd_log_y("2THPRINT: LMP_features_res_ext was invalid due to our sending too many requests.");
		return 0;
	}
        printf("2THPRINT: LMP_features_res_ext Features Page Number: 0x%02x\n", feature_page_num);
        printf("2THPRINT: LMP_features_res_ext Max Supported Page: 0x%02x\n", max_page_num);
        printf("2THPRINT: LMP_features_res_ext Extended Features bytes: ");
        for(i = 0; i < 8; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET+3]);
        }
        printf("\n");
        gRecv_LMP_features_req_ext++;
	// Only set the maximum page seen so far, for responses
	// seen before we enable experimental mode
        if(!gExperimental){
		gMaxExtendedFeaturePages = max_page_num;
		printf("2THPRINT: Max legit extended feature page: 0x%02X\n", max_page_num);
	}
	else{
		// If we are in experimental mode, and the returned page is above the original professed max page value
		// and the value is non-zero, then save that value to try and see if we get the same result again later
		unsigned long long int val = *(unsigned long long *)(&pkt_buf[LMP_DATA_PKT_OFFSET+3]);
//		if(max_page_num > gMaxExtendedFeaturePages && val != 0){
		if(feature_page_num > max_page_num && val != 0){
			gInfoLeak[max_page_num] = val;
			printf("2THPRINT: POSSIBLE INFO LEAK: EXT PAGE 0x%02X = 0x%016X\n", feature_page_num, val);
		}
	}

	// PRINT TO LOG FOR POST-PROCESSING
	printf("BTC_2THPRINT: LMP_OP_");
	fprintf(glogfile, "BTC_2THPRINT: LMP_OP_");
	// Opcode:
        printf("0x%02X ", pkt_buf[4]>>1);
	// Raw bytes
        for(i = 0; i < 11; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
            fprintf(glogfile, "0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
        }
        printf("\n");
        fprintf(glogfile, "\n");

        return 0;
    }

    //******** CAPTURE NAME *********//
    if (packet_read_filter(filter_lmp_name_res))
    {
        wd_log_y("2THPRINT: LMP_name_res RX detected");
        char acl_len = (pkt_buf[2]>>3) & 0x3FF;
        char name_offset = pkt_buf[LMP_NAME_OFFSET_PKT_OFFSET];
        char name_len = pkt_buf[LMP_NAME_LEN_PKT_OFFSET];
        printf("2THPRINT: ACL Data Length = 0x%x\n", acl_len);
        printf("2THPRINT: Name Offset = 0x%x\n", name_offset);
        printf("2THPRINT: Name Length = 0x%x\n", name_len);
        if (name_len <= LMP_NAME_DATA_SIZE_MAX){
            // This single packet contains the entire name, so just print it now.
            printf("2THPRINT: BT Classic Name is: ");
            for (i = LMP_NAME_DATA_PKT_OFFSET ; i < (LMP_NAME_DATA_PKT_OFFSET + name_len); i++){
                printf("%c", pkt_buf[i]);
            }
            printf("\n");

            printf("BTC_2THPRINT: LMP_OP_0x02 ");
            fprintf(glogfile, "BTC_2THPRINT: LMP_OP_0x02 ");
            for (i = LMP_NAME_DATA_PKT_OFFSET ; i < (LMP_NAME_DATA_PKT_OFFSET + name_len); i++){
                printf("0x%02X ", pkt_buf[i]);
                fprintf(glogfile, "0x%02X ", pkt_buf[i]);
            }
            printf("\n");
            fprintf(glogfile, "\n");

	    // One more time in human readable form (since it seems to be handling unicode OK?)
            fprintf(glogfile, "BTC_2THPRINT: LMP_OP_0x02 ");
            for (i = LMP_NAME_DATA_PKT_OFFSET ; i < (LMP_NAME_DATA_PKT_OFFSET + name_len); i++){
                fprintf(glogfile, "%c", pkt_buf[i]);
            }
            fprintf(glogfile, "\n");

            // Reset global state
            g_max_offset_so_far = 0;
            memset(gName, 0, 512);
            gAllRequiredResponses |= RR_LMP_NAME_RES;
        }
        else{
            // This is a fragment of a name. Fill in this portion to the global buf, and don't print out yet
            for (i = name_offset; i < (name_offset + acl_len-3); i++){ //-3 is to remove the opcode byte, name offset byte, and name length byte
                gName[i] = pkt_buf[j + LMP_NAME_DATA_PKT_OFFSET];
//                printf("Copyng gName[%d] = pkt_buf[%d] (%c)\n", i, j+LMP_NAME_DATA_PKT_OFFSET, pkt_buf[j+LMP_NAME_DATA_PKT_OFFSET]);
                j++;
            }
            // If the last byte written would be >= the name_len, then we got the complete name and can now print it
            if(i >= name_len){
                printf("2THPRINT: DEFRAG: BT Classic Name is: ");
                for (i = 0; i < name_len; i++){
                    printf("%c", gName[i]);
                }
                printf("\n");

                printf("BTC_2THPRINT: LMP_OP_0x02 ");
                fprintf(glogfile, "BTC_2THPRINT: LMP_OP_0x02 ");
                for (i = 0; i < name_len; i++){
                    printf("0x%02X ", gName[i]);
                    fprintf(glogfile, "0x%02X ", gName[i]);
                }
                printf("\n");
                fprintf(glogfile, "\n");

		// One more time in human readable form (since it seems to be handling unicode OK?)
                fprintf(glogfile, "BTC_2THPRINT: LMP_OP_0x02 ");
                for (i = 0; i < name_len; i++){
                    fprintf(glogfile, "%c", gName[i]);
                }
                fprintf(glogfile, "\n");

                // Reset global state
                g_max_offset_so_far = 0;
                memset(gName, 0, 512);
                gAllRequiredResponses |= RR_LMP_NAME_RES;
            }
            else{
                g_max_offset_so_far = i;
                gMoreNameNeeded = 1; //Send the next LMP_name_req after the next packet is received
            }
        }
    }


    //******** CAPTURE CLASS OF DEVICE *********//
    if(packet_read_filter(filter_fhs))
    {
        wd_log_y("2THPRINT: Incoming FHS");
        int CoD = (*((int *)&pkt_buf[13])) & 0xFFFFFF;
        printf("2THPRINT: Their Class of Device is: 0x%06x\n", CoD);
        printf("BTC_2THPRINT: CLASS_OF_DEVICE 0x%06x\n", CoD);
        fprintf(glogfile, "BTC_2THPRINT: CLASS_OF_DEVICE 0x%06x\n", CoD);
        gBDADDR[0] = pkt_buf[12];
        gBDADDR[1] = pkt_buf[11];
        gBDADDR[2] = pkt_buf[10];
        unsigned int lap = *(unsigned int *)&pkt_buf[6];
        lap = (lap >> 2) & 0xFFFFFF;
//      printf("2THPRINT: lap = 0x%06x\n", lap);
        gBDADDR[3] = (lap >> 16) & 0xFF;
        gBDADDR[4] = (lap >> 8) & 0xFF;
        gBDADDR[5] = (lap >> 0) & 0xFF;
        printf("2THPRINT: Their BDADDR is: %02X:%02X:%02X:%02X:%02X:%02X\n", gBDADDR[0], gBDADDR[1], gBDADDR[2], gBDADDR[3], gBDADDR[4], gBDADDR[5]);
        printf("BTC_2THPRINT: REMOTE_BDADDR %02X:%02X:%02X:%02X:%02X:%02X\n", gBDADDR[0], gBDADDR[1], gBDADDR[2], gBDADDR[3], gBDADDR[4], gBDADDR[5]);
        fprintf(glogfile, "BTC_2THPRINT: REMOTE_BDADDR %02X:%02X:%02X:%02X:%02X:%02X\n", gBDADDR[0], gBDADDR[1], gBDADDR[2], gBDADDR[3], gBDADDR[4], gBDADDR[5]);

    }

    // NOTE: FWIW Apple devices don't response with a ping_res, they send unknown opcodes (22 and 78)
    if (packet_read_filter(filter_lmp_ping_res))
    {
        wd_log_y("2THPRINT: LMP_ping_res RX detected");
        printf("BTC_2THPRINT: LMP_OP_0xFE 0x34\n");
        fprintf(glogfile, "BTC_2THPRINT: LMP_OP_0xFE 0x34\n");
    }

    if (packet_read_filter(filter_lmp_encryption_key_size_req))
    {
        wd_log_y("2THPRINT: LMP_encryption_key_size_req RX detected");
        printf("2THPRINT: LMP_version_res bytes: ");
        for(i = 0; i < 1; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
        }
        printf("\n");
        printf("BTC_2THPRINT: LMP_OP_0x%02X 0x%02X", pkt_buf[LMP_OPCODE_PKT_OFFSET], pkt_buf[LMP_DATA_PKT_OFFSET]);
        fprintf(glogfile, "BTC_2THPRINT: LMP_OP_0x%02X 0x%02X", pkt_buf[LMP_OPCODE_PKT_OFFSET], pkt_buf[LMP_DATA_PKT_OFFSET]);
    }

    //******** CAPTURE VERSION INFORMATION *********//
    if (packet_read_filter(filter_lmp_version_res))
    {
	gAllRequiredResponses |= RR_LMP_VERSION_RES;

        wd_log_y("2THPRINT: LMP_version_res RX detected");
        printf("2THPRINT: LMP_version_res bytes: ");
        for(i = 0; i < 5; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
        }
        printf("\n");
	gRecv_LMP_version_res++;

	// PRINT TO LOG FOR POST-PROCESSING
	printf("BTC_2THPRINT: LMP_OP_");
	fprintf(glogfile, "BTC_2THPRINT: LMP_OP_");
	// Opcode:
        printf("0x%02X ", pkt_buf[4]>>1);
        fprintf(glogfile, "0x%02X ", pkt_buf[4]>>1);
	// Raw bytes
        for(i = 0; i < 5; i++){
            printf("0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
            fprintf(glogfile, "0x%02X ", pkt_buf[i+LMP_DATA_PKT_OFFSET]);
        }
        printf("\n");
        fprintf(glogfile, "\n");

	// Place this with the last non-experimental packet we want to receive
	// to unlock the experimental checks, that may lead to broken connects or other weird results
	// TODO: in the future place after retries are done
//	gExperimental |= LMP_PING_REQ;
/*	gExperimental |= LMP_ENCRYPTION_KEY_SIZE_REQ;
	printf("BTC_2THPRINT: COMMENT BEGINNING EXPERIMENTAL CHECKS: %02X\n", gExperimental);
	fprintf(glogfile, "BTC_2THPRINT: COMMENT BEGINNING EXPERIMENTAL CHECKS: %02X\n", gExperimental);
*/

	//NOTE: We're basically going to treat the LMP_version_req as if it's a ping, 
	//      and keep sending it until we get all the 
	if((gAllRequiredResponses & RR_ALL_DONE) == RR_ALL_DONE){
		printf("2THPRINT: We got all required responses. Exiting\n");
		printf("BTC_2THPRINT: ALL RESPONSES RECEIVED\n");
		fprintf(glogfile, "BTC_2THPRINT: ALL RESPONSES RECEIVED\n");
		exit(0);
	}
	else{
		printf("2THPRINT: gAllRequiredResponses = 0x%llx\n", gAllRequiredResponses);
		sleep(1);
		// This will re-enable it sending another LMP_version_req
		gSent_LMP_version_req = 0;
	}


        return 0;
    }


    return 0;
}
