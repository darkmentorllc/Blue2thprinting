// Code by Xeno Kovah, Copyright Dark Mentor LLC (c) 2025
// Compilation command (executed from /home/user/Blue2thprinting/bluez-5.66):
// gcc -o Xeno_VSC_send_LMP_hardcoded tools/Xeno_VSC_send_LMP_hardcoded.c  -Ilib -Isrc -Isrc/shared -I. -Llib/.libs -lbluetooth-internal -Lsrc/.libs -lshared-glib  $(pkg-config --cflags --libs glib-2.0) -DVERSION=\"5.66\"

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>
#include <pthread.h>
#include <string.h>

unsigned long long g_lmp_opcodes_seen = 0;
#define opcode_LMP_NAME_REQ                                     1
#define opcode_LMP_NAME_RES                                     2
#define opcode_LMP_ACCEPTED                                     3
#define opcode_LMP_NOT_ACCEPTED                                 4
#define opcode_LMP_CLKOFFSET_REQ                                5
#define opcode_LMP_CLKOFFSET_RES                                6
#define opcode_LMP_DETACH                                       7
#define opcode_LMP_IN_RAND                                      8
#define opcode_LMP_COMB_KEY                                     9
#define opcode_LMP_UNIT_KEY                                    10
#define opcode_LMP_AU_RAND                                     11
#define opcode_LMP_SRES                                        12
#define opcode_LMP_TEMP_RAND                                   13
#define opcode_LMP_TEMP_KEY                                    14
#define opcode_LMP_ENCRYPTION_MODE_REQ                         15
#define opcode_LMP_ENCRYPTION_KEY_SIZE_REQ                     16
#define opcode_LMP_START_ENCRYPTION_REQ                        17
#define opcode_LMP_STOP_ENCRYPTION_REQ                         18
#define opcode_LMP_SWITCH_REQ                                  19
#define opcode_LMP_HOLD                                        20
#define opcode_LMP_HOLD_REQ                                    21
#define opcode_LMP_SNIFF                                       22
#define opcode_LMP_SNIFF_REQ                                   23
#define opcode_LMP_UNSNIFF_REQ                                 24
#define opcode_LMP_PARK_REQ                                    25
#define opcode_LMP_SET_BROADCAST_SCAN_WINDOW                   27
#define opcode_LMP_MODIFY_BEACON                               28
#define opcode_LMP_UNPARK_BD_ADDR_REQ                          29
#define opcode_LMP_UNPARK_PM_ADDR_REQ                          30
#define opcode_LMP_INCR_POWER_REQ                              31
#define opcode_LMP_DECR_POWER_REQ                              32
#define opcode_LMP_MAX_POWER                                   33
#define opcode_LMP_MIN_POWER                                   34
#define opcode_LMP_AUTO_RATE                                   35
#define opcode_LMP_PREFERRED_RATE                              36
#define opcode_LMP_VERSION_REQ                                 37
#define opcode_LMP_VERSION_RES                                 38
#define opcode_LMP_FEATURES_REQ                                39
#define opcode_LMP_FEATURES_RES                                40
#define opcode_LMP_QUALITY_OF_SERVICE                          41
#define opcode_LMP_QUALITY_OF_SERVICE_REQ                      42
#define opcode_LMP_SCO_LINK_REQ                                43
#define opcode_LMP_REMOVE_SCO_LINK_REQ                         44
#define opcode_LMP_MAX_SLOT                                    45
#define opcode_LMP_MAX_SLOT_REQ                                46
#define opcode_LMP_TIMING_ACCURACY_REQ                         47
#define opcode_LMP_TIMING_ACCURACY_RES                         48
#define opcode_LMP_SETUP_COMPLETE                              49
#define opcode_LMP_USE_SEMI_PERMANENT_KEY                      50
#define opcode_LMP_HOST_CONNECTION_REQ                         51
#define opcode_LMP_SLOT_OFFSET                                 52
#define opcode_LMP_PAGE_MODE_REQ                               53
#define opcode_LMP_PAGE_SCAN_MODE_REQ                          54
#define opcode_LMP_SUPERVISION_TIMEOUT                         55
#define opcode_LMP_TEST_ACTIVATE                               56
#define opcode_LMP_TEST_CONTROL                                57
#define opcode_LMP_ENCRYPTION_KEY_SIZE_MASK_REQ                58
#define opcode_LMP_ENCRYPTION_KEY_SIZE_MASK_RES                59
#define opcode_LMP_SET_AFH                                     60
#define opcode_LMP_ENCAPSULATED_HEADER                         61
#define opcode_LMP_ENCAPSULATED_PAYLOAD                        62
#define opcode_LMP_SIMPLE_PAIRING_CONFIRM                      63
#define opcode_MAX_VALUE                                       64   

// Data structure to map opcodes to their human-readable names
const char *lmp_opcode_names[opcode_MAX_VALUE] = {
    "RESERVED", // 0
    "LMP_NAME_REQ",
    "LMP_NAME_RES",
    "LMP_ACCEPTED",
    "LMP_NOT_ACCEPTED",
    "LMP_CLKOFFSET_REQ",
    "LMP_CLKOFFSET_RES",
    "LMP_DETACH",
    "LMP_IN_RAND",
    "LMP_COMB_KEY",
    "LMP_UNIT_KEY",
    "LMP_AU_RAND",
    "LMP_SRES",
    "LMP_TEMP_RAND",
    "LMP_TEMP_KEY",
    "LMP_ENCRYPTION_MODE_REQ",
    "LMP_ENCRYPTION_KEY_SIZE_REQ",
    "LMP_START_ENCRYPTION_REQ",
    "LMP_STOP_ENCRYPTION_REQ",
    "LMP_SWITCH_REQ",
    "LMP_HOLD",
    "LMP_HOLD_REQ",
    "LMP_SNIFF",
    "LMP_SNIFF_REQ",
    "LMP_UNSNIFF_REQ",
    "LMP_PARK_REQ",
    "RESERVED", // 26
    "LMP_SET_BROADCAST_SCAN_WINDOW",
    "LMP_MODIFY_BEACON",
    "LMP_UNPARK_BD_ADDR_REQ",
    "LMP_UNPARK_PM_ADDR_REQ",
    "LMP_INCR_POWER_REQ",
    "LMP_DECR_POWER_REQ",
    "LMP_MAX_POWER",
    "LMP_MIN_POWER",
    "LMP_AUTO_RATE",
    "LMP_PREFERRED_RATE",
    "LMP_VERSION_REQ",
    "LMP_VERSION_RES",
    "LMP_FEATURES_REQ",
    "LMP_FEATURES_RES",
    "LMP_QUALITY_OF_SERVICE",
    "LMP_QUALITY_OF_SERVICE_REQ",
    "LMP_SCO_LINK_REQ",
    "LMP_REMOVE_SCO_LINK_REQ",
    "LMP_MAX_SLOT",
    "LMP_MAX_SLOT_REQ",
    "LMP_TIMING_ACCURACY_REQ",
    "LMP_TIMING_ACCURACY_RES",
    "LMP_SETUP_COMPLETE",
    "LMP_USE_SEMI_PERMANENT_KEY",
    "LMP_HOST_CONNECTION_REQ",
    "LMP_SLOT_OFFSET",
    "LMP_PAGE_MODE_REQ",
    "LMP_PAGE_SCAN_MODE_REQ",
    "LMP_SUPERVISION_TIMEOUT",
    "LMP_TEST_ACTIVATE",
    "LMP_TEST_CONTROL",
    "LMP_ENCRYPTION_KEY_SIZE_MASK_REQ",
    "LMP_ENCRYPTION_KEY_SIZE_MASK_RES",
    "LMP_SET_AFH",
    "LMP_ENCAPSULATED_HEADER",
    "LMP_ENCAPSULATED_PAYLOAD",
    "LMP_SIMPLE_PAIRING_CONFIRM"
};

unsigned long long g_lmp_ext_opcodes_seen = 0;
#define ext_opcode_LMP_ACCEPTED_EXT                1
#define ext_opcode_LMP_NOT_ACCEPTED_EXT            2
#define ext_opcode_LMP_FEATURES_REQ_EXT            3
#define ext_opcode_LMP_FEATURES_RES_EXT            4
#define ext_opcode_LMP_SCATTER_REQ                 5
#define ext_opcode_LMP_UNSCATTER_REQ               6
#define ext_opcode_LMP_SET_SUBRATE                 7
#define ext_opcode_LMP_SCATTER_ALGORITHMS_REQ      8
#define ext_opcode_LMP_SCATTER_ALGORITHMS_RES      9
#define ext_opcode_LMP_PP_EXTENSION_REQ            10
#define ext_opcode_LMP_PACKET_TYPE_TABLE_REQ       11
#define ext_opcode_LMP_ESCO_LINK_REQ               12
#define ext_opcode_LMP_REMOVE_ESCO_LINK_REQ        13
#define ext_opcode_LMP_CHANNEL_CLASSIFICATION_REQ  16
#define ext_opcode_LMP_CHANNEL_CLASSIFICATION      17
#define ext_opcode_LMP_ALIAS_ADDRESS               18
#define ext_opcode_LMP_ACTIVE_ADDRESS              19
#define ext_opcode_LMP_FIXED_ADDRESS               20
#define ext_opcode_LMP_SNIFF_SUBRATING_REQ         21
#define ext_opcode_LMP_SNIFF_SUBRATING_RES         22
#define ext_opcode_LMP_PAUSE_ENCRYPTION_REQ        23
#define ext_opcode_LMP_RESUME_ENCRYPTION_REQ       24
#define ext_opcode_LMP_IO_CAPABILITY_REQUEST       25
#define ext_opcode_LMP_IO_CAPABILITY_RESPONSE      26
#define ext_opcode_LMP_NUMERIC_COMPARISON_FAILED   27
#define ext_opcode_LMP_PASSKEY_ENTRY_FAILED        28
#define ext_opcode_LMP_OOB_FAILED                  29
#define ext_opcode_LMP_KEYPRESS_NOTIFICATION       30
#define ext_opcode_LMP_POWER_CONTROL_REQ           31
#define ext_opcode_LMP_POWER_CONTROL_RESP          32
#define ext_opcode_MAX_VALUE                       33   

const char *lmp_ext_opcode_names[ext_opcode_MAX_VALUE] = {
    "RESERVED", // 0
    "LMP_ACCEPTED_EXT",
    "LMP_NOT_ACCEPTED_EXT",
    "LMP_FEATURES_REQ_EXT",
    "LMP_FEATURES_RES_EXT",
    "LMP_SCATTER_REQ",
    "LMP_UNSCATTER_REQ",
    "LMP_SET_SUBRATE",
    "LMP_SCATTER_ALGORITHMS_REQ",
    "LMP_SCATTER_ALGORITHMS_RES",
    "LMP_PP_EXTENSION_REQ",
    "LMP_PACKET_TYPE_TABLE_REQ",
    "LMP_ESCO_LINK_REQ",
    "LMP_REMOVE_ESCO_LINK_REQ",
    "RESERVED", // 14
    "RESERVED", // 15
    "LMP_CHANNEL_CLASSIFICATION_REQ",
    "LMP_CHANNEL_CLASSIFICATION",
    "LMP_ALIAS_ADDRESS",
    "LMP_ACTIVE_ADDRESS",
    "LMP_FIXED_ADDRESS",
    "LMP_SNIFF_SUBRATING_REQ",
    "LMP_SNIFF_SUBRATING_RES",
    "LMP_PAUSE_ENCRYPTION_REQ",
    "LMP_RESUME_ENCRYPTION_REQ",
    "LMP_IO_CAPABILITY_REQUEST",
    "LMP_IO_CAPABILITY_RESPONSE",
    "LMP_NUMERIC_COMPARISON_FAILED",
    "LMP_PASSKEY_ENTRY_FAILED",
    "LMP_OOB_FAILED",
    "LMP_KEYPRESS_NOTIFICATION",
    "LMP_POWER_CONTROL_REQ",
    "LMP_POWER_CONTROL_RESP"
};

// Mutexes for protecting access to global variables
pthread_mutex_t g_lmp_opcodes_mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t g_lmp_ext_opcodes_mutex = PTHREAD_MUTEX_INITIALIZER;

// Thread function to read HCI events
void *threaded_hci_read(void *arg) {
    int dev = *(int *)arg;
    unsigned char buf[HCI_MAX_EVENT_SIZE];
    int readlen;
    hci_event_hdr *hdr;
    unsigned char lmp_opcode;
    unsigned char lmp_ext_opcode;
    unsigned char vse_lmp_opcode_offset = 0x1C;

    printf("Thread started: Reading HCI events...\n");
    while (1) {
        readlen = read(dev, buf, sizeof(buf));
        if (readlen < 0) {
            perror("Failed to read HCI event");
            return NULL;
        }
        // printf("HCI event read successfully, length: %d\n", readlen);

        // Only process the VSE events (event code 0xFF)
        hdr = (void *)(buf + 1);
        if (hdr->evt != 0xFF) {
            continue;
        }

        // Make sure we have at least enough data that it's read the LMP opcode + extended opcode
        // The +3 is for the HCI event type + header
        // The +1 is for the extended opcode byte after the LMP opcode
        // Also, skip when the raw value is 0xCC which is just uninitialized memory fill-in
        if ((readlen > vse_lmp_opcode_offset + 3 + 1) && (buf[vse_lmp_opcode_offset + 3] != 0xCC)) {
            lmp_opcode = buf[vse_lmp_opcode_offset + 3] >> 1;
            printf("\t[!] threaded_hci_read: Raw value at offset 0x%02X: 0x%02X\n", vse_lmp_opcode_offset, buf[vse_lmp_opcode_offset + 3]);
            if (lmp_opcode < opcode_MAX_VALUE) {
                printf("\t\t[+] Saw opcode 0x%02X (%s)\n", lmp_opcode, lmp_opcode_names[lmp_opcode]);
                // printf("\t\t[B4] g_lmp_opcodes_seen: 0x%016llX\n", g_lmp_opcodes_seen);
                // Acquire mutex before writing
                pthread_mutex_lock(&g_lmp_opcodes_mutex);
                g_lmp_opcodes_seen |= (1ULL << lmp_opcode);
                pthread_mutex_unlock(&g_lmp_opcodes_mutex);
                // printf("\t\t[AF] g_lmp_opcodes_seen: 0x%016llX\n", g_lmp_opcodes_seen);
            } else if (lmp_opcode == 0x7f) { // 127 is the only "escape" opcode currently used in the spec
                lmp_ext_opcode = buf[vse_lmp_opcode_offset + 4] >> 1;
                if (lmp_ext_opcode < ext_opcode_MAX_VALUE) {
                    printf("\t[!] threaded_hci_read: Raw value at offset 0x%02X: 0x%02X\n", vse_lmp_opcode_offset+1, buf[vse_lmp_opcode_offset + 3 + 1]);
                    printf("\t\t[+] Saw extended opcode 0x%02X (%s)\n", lmp_ext_opcode, lmp_ext_opcode_names[lmp_ext_opcode]);
                    // printf("\t\t[B4] g_lmp_ext_opcodes_seen: 0x%016llX\n", g_lmp_ext_opcodes_seen);
                    // Acquire mutex before writing
                    pthread_mutex_lock(&g_lmp_ext_opcodes_mutex);
                    g_lmp_ext_opcodes_seen |= (1ULL << lmp_ext_opcode);
                    pthread_mutex_unlock(&g_lmp_ext_opcodes_mutex);
                    // printf("\t\t[AF] g_lmp_ext_opcodes_seen: 0x%016llX\n", g_lmp_ext_opcodes_seen);
                }
            }
        }
    }

    return NULL;
}

// Function to print observed opcodes
void print_seen_opcodes() {
    printf("\nObserved LMP Opcodes (0x%016llX):\n", g_lmp_opcodes_seen);
    for (int i = 1; i < opcode_MAX_VALUE; i++) {
        if (g_lmp_opcodes_seen & (1ULL << i)) {
            printf("  %s\t(0x%02X / %d)\n", lmp_opcode_names[i], i, i);
        }
    }

    printf("\nObserved Extended LMP Opcodes (0x%016llX):\n", g_lmp_ext_opcodes_seen);
    for (int i = 1; i < ext_opcode_MAX_VALUE; i++) {
        if (g_lmp_ext_opcodes_seen & (1ULL << i)) {
            printf("  %s\t(0x%02X / %d)\n", lmp_ext_opcode_names[i], i, i);
        }
    }
}

int wait_to_see_opcode(unsigned int wait_seconds, unsigned char lmp_opcode, unsigned char lmp_ext_opcode){
    int end_time = time(NULL) + wait_seconds;
    // Loop for maximum of wait_seconds, waiting to see if we see the desired opcode(s)
    while (time(NULL) < end_time) {
        // Check if this opcode has been seen yet
        if(lmp_opcode == 0x7f){
            // Don't need mutex if only reading
            if((lmp_ext_opcode < ext_opcode_MAX_VALUE) && (g_lmp_ext_opcodes_seen & (1ULL << lmp_ext_opcode))){
                return 1;
            }
        }
        else if (lmp_opcode < opcode_MAX_VALUE){
            // Don't need mutex if only reading
            if(g_lmp_opcodes_seen & (1ULL << lmp_opcode)){
                return 1;
            }
        }
    }
    return 0; // Timeout
}

int main(int argc, char *argv[]) {
    bdaddr_t bdaddr;
    uint16_t handle;
    int ret, dev_id, dev;
    struct hci_filter flt;
    int sleep_seconds = 0;
    uint8_t role = 0x00; // Default role: Central
    uint16_t packettypes = HCI_DM1 | HCI_DM3 | HCI_DM5 | HCI_DH1 | HCI_DH3 | HCI_DH5;
    pthread_t hci_read_thread;

    if (argc < 1) {
        fprintf(stderr, "Usage: %s <bdaddr>\n", argv[0]);
        return 1;
    }

    str2ba(argv[1], &bdaddr);

    // TODO: need to check that it selected the Realtek adapter ()
    dev_id = hci_get_route(&bdaddr);
    if (dev_id < 0) {
        perror("HCI device not found");
        return 1;
    }

    dev = hci_open_dev(dev_id);
    if (dev < 0) {
        perror("Failed to open HCI device");
        return 1;
    }

	// Setup filter
    // This is required or else it can't read HCI events successfully
    hci_filter_clear(&flt);
	hci_filter_set_ptype(HCI_EVENT_PKT, &flt);
	hci_filter_all_events(&flt);
	if (setsockopt(dev, SOL_HCI, HCI_FILTER, &flt, sizeof(flt)) < 0) {
		perror("HCI filter setup failed");
		exit(EXIT_FAILURE);
	}

    if (hci_create_connection(dev, &bdaddr, htobs(packettypes), htobs(0x0000), 
                              role, &handle, 25000) < 0) {
        perror("Failed to create connection");
        hci_close_dev(dev);
        return 1;
    }

    // Start the threaded HCI read
    if (pthread_create(&hci_read_thread, NULL, threaded_hci_read, &dev) != 0) {
        perror("Failed to create HCI read thread");
        hci_close_dev(dev);
        return 1;
    }

    // TODO: We can start logging LMP data (ideally asynchronously in a separate thread) at this point,
    // because I can see it coming back in the HCI log even before the connection 
    // is reported as being completed by the controller.

    printf("Connection handle: %d (0x%04x)\n", handle, handle);

    // Hardcoded byte sequences for LMP packets I want to send:
    unsigned char hci_buf_LMP_VERSION_REQ[] = {0x25, 0x00, 0x0D, 0x4D, 0x44, 0x37, 0x13};
    unsigned char hci_buf_LMP_FEATURES_REQ[] = {0x27, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    int len = sizeof(hci_buf_LMP_VERSION_REQ);

    // Set OGF and OCF
    uint8_t ogf = 0x3f;
    uint16_t ocf = 0x0222; // Magic "Xeno VSC" hacked in to DarkFirmware_real_i to allow LMP passthrough
    
    if(g_lmp_opcodes_seen & (1ULL << opcode_LMP_VERSION_RES) || g_lmp_opcodes_seen & (1ULL << opcode_LMP_VERSION_REQ)){
        printf("[+] Already saw LMP Version, skipping sending of LMP_VERSION_REQ\n");
    }
    else{
        // Send the LMP_VERSION_REQ
        printf("Sending LMP_VERSION_REQ...\n");
        if (hci_send_cmd(dev, ogf, ocf, len, hci_buf_LMP_VERSION_REQ) < 0) {
            perror("Failed to send HCI command to send LMP_VERSION_REQ");
            hci_close_dev(dev);
            return 1;
        }
        // We will be happy if we either get a LMP_VERSION_REQ autonomously sent by the Peripheral
        // or a LMP_VERSION_RES sent in response to our LMP_VERSION_REQ
        ret = wait_to_see_opcode(2, opcode_LMP_VERSION_RES, 0); // 0x4C = LMP_VERSION_RES
        if(ret == 0){
            printf("Wait to see LMP_VERSION_RES timed out\n");
        }
    }

    // TODO: replace with hci_read_remote_version()

    // sleep_seconds = 2;
    // printf("Sleeping %d seconds to wait to see final traffic...\n", sleep_seconds);
    // sleep(sleep_seconds);

    // TODO: add conditional to only send LMP packet if we haven't seen features already
    if(g_lmp_opcodes_seen & (1ULL << opcode_LMP_FEATURES_RES) || g_lmp_opcodes_seen & (1ULL << opcode_LMP_FEATURES_REQ)){
        printf("[+] Already saw LMP Features, skipping sending of LMP_FEATURES_REQ\n");
    }
    else{
        // Send the LMP_FEATURES_REQ
        printf("Sending LMP_FEATURES_REQ...\n");
        len = sizeof(hci_buf_LMP_FEATURES_REQ);
        if (hci_send_cmd(dev, ogf, ocf, len, hci_buf_LMP_FEATURES_REQ) < 0) {
            perror("Failed to send HCI command to send LMP_FEATURES_REQ");
            hci_close_dev(dev);
            return 1;
        }
        // We will be happy if we either get a LMP_FEATURES_REQ autonomously sent by the Peripheral
        // or a LMP_FEATURES_RES sent in response to our LMP_FEATURES_REQ
        ret = wait_to_see_opcode(2, opcode_LMP_FEATURES_RES, 0); // 0x50 = LMP_FEATURES_RES
        if(ret == 0){
            printf("Wait to see LMP_FEATURES_REQ timed out\n");
        }
    }
    // TODO: replace with hci_read_remote_features() + hci_read_remote_ext_features


    // TODO: Send invalid read of extended features that is out of bounds...
    // TODO: LMP Packets to send:
    // 

    // printf("Sleeping %d seconds to wait to see final traffic...\n", sleep_seconds);
    // sleep(sleep_seconds);

    pthread_cancel(hci_read_thread); // Cancel the thread when done
    pthread_join(hci_read_thread, NULL);

	if (hci_disconnect(dev, htobs(handle), HCI_OE_USER_ENDED_CONNECTION, 10000) < 0)
		perror("Disconnect failed");

    hci_close_dev(dev);

    // Print observed opcodes
    print_seen_opcodes();

    // Destroy mutexes before exiting
    pthread_mutex_destroy(&g_lmp_opcodes_mutex);
    pthread_mutex_destroy(&g_lmp_ext_opcodes_mutex);

    return 0;
}