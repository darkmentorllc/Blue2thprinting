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

unsigned long long lmp_opcodes_seen = 0;
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

int check_expected_values(int dev, unsigned char offset, unsigned char value){
    unsigned char buf[HCI_MAX_EVENT_SIZE];
    int readlen;

    char header_len = 3;
    int end_time = time(NULL) + 2;
    // Loop for maximum of 2 seconds, waiting to see if we get back the response data we expect
    while (time(NULL) < end_time) {
        printf("\tAttempting to read HCI events...\n");
        // Read HCI event
        readlen = read(dev, buf, sizeof(buf));
        if (readlen < 0) {
            perror("Failed to read HCI event\n");
            return -1;
        }

        // Check if the event length is sufficient to access offset 0x1C
        if (readlen > offset + header_len) {
            if (buf[header_len + offset] == value) {
                printf("Found matching value %d at offset %d!\n", value, offset);
                return 1;
                break;
            } else {
                // printf("Value at offset 0x10: 0x%02X\n", buf[header_len+0x10]);
                printf("\tValue at offset 0x1C: 0x%02X\n", buf[header_len+offset]);
            }
        } else {
            printf("\tEvent too short to check offset 0x1C, length: %d\n", readlen);
        }
    }
    return 0;
}

int main(int argc, char *argv[]) {
    bdaddr_t bdaddr;
    uint16_t handle;
    int ret, dev_id, dev;
    struct hci_filter flt;
    int sleep_seconds = 0;
    uint8_t role = 0x00; // Default role: Central
    uint16_t packettypes = HCI_DM1 | HCI_DM3 | HCI_DM5 | HCI_DH1 | HCI_DH3 | HCI_DH5;

    if (argc < 1) {
        fprintf(stderr, "Usage: %s <bdaddr>\n", argv[0]);
        return 1;
    }

    str2ba(argv[1], &bdaddr);

    // TODO: sanity check that it selected the Realtek adapter
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

    if (hci_create_connection(dev, &bdaddr, htobs(packettypes), htobs(0x0000), 
                              role, &handle, 25000) < 0) {
        perror("Failed to create connection");
        hci_close_dev(dev);
        return 1;
    }

    // TODO: We can start logging LMP data (ideally asynchronously in a separate thread) at this point,
    // because I can see it coming back in the HCI log even before the connection 
    // is reported as being completed by the controller.

	// Setup filter
    // This is required or else it can't read HCI events successfully
    hci_filter_clear(&flt);
	hci_filter_set_ptype(HCI_EVENT_PKT, &flt);
	hci_filter_all_events(&flt);
	if (setsockopt(dev, SOL_HCI, HCI_FILTER, &flt, sizeof(flt)) < 0) {
		perror("HCI filter setup failed");
		exit(EXIT_FAILURE);
	}

    printf("Connection handle: %d (0x%04x)\n", handle, handle);

    // Hardcoded byte sequences for LMP packets I want to send:
    unsigned char hci_buf_LMP_VERSION_REQ[] = {0x25, 0x00, 0x0D, 0x4D, 0x44, 0x37, 0x13};
    unsigned char hci_buf_LMP_FEATURES_REQ[] = {0x27, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    int len = sizeof(hci_buf_LMP_VERSION_REQ);

    // Set OGF and OCF
    uint8_t ogf = 0x3f;
    uint16_t ocf = 0x0222; // Magic "Xeno VSC" hacked in to DarkFirmware_real_i to allow LMP passthrough
    
    // Send the LMP_VERSION_REQ
    printf("Sending LMP_VERSION_REQ...\n");
    if (hci_send_cmd(dev, ogf, ocf, len, hci_buf_LMP_VERSION_REQ) < 0) {
        perror("Failed to send HCI command to send LMP_VERSION_REQ");
        hci_close_dev(dev);
        return 1;
    }
    printf("Checking offset 0x1C == 0x4C...\n");
    // We will be happy if we either get a LMP_VERSION_REQ autonomously sent by the Peripheral
    // or a LMP_VERSION_RES sent in response to our LMP_VERSION_REQ
    ret = check_expected_values(dev, 0x1C, 0x4C); // 0x4C = LMP_VERSION_RES ((38 << 1) | 0)
    if(ret == -1){
        printf("Error occurred while attempting to read HCI Events. Exiting.\n");
        hci_close_dev(dev);
        if (hci_disconnect(dev, htobs(handle), HCI_OE_USER_ENDED_CONNECTION, 10000) < 0)
    		perror("Disconnect failed");
        return -1;
    }
    else if (ret == 1){
        lmp_opcodes_seen |= (1ULL << opcode_LMP_VERSION_RES);
    }

    // TODO: replace with hci_read_remote_version()

    // sleep_seconds = 2;
    // printf("Sleeping %d seconds to wait to see final traffic...\n", sleep_seconds);
    // sleep(sleep_seconds);

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
    printf("Checking offset 0x1C == 0x50...\n");
    ret = check_expected_values(dev, 0x1C, 0x50); // 0x50 = LMP_FEATURES_RES ((40 << 1) | 0)
    if(ret == -1){
        printf("Error occurred while attempting to read HCI Events. Exiting.\n");
        hci_close_dev(dev);
        if (hci_disconnect(dev, htobs(handle), HCI_OE_USER_ENDED_CONNECTION, 10000) < 0)
    		perror("Disconnect failed");
        return -1;
    }
    else if (ret == 1){
        lmp_opcodes_seen |= (1ULL << opcode_LMP_FEATURES_RES);
    }

    // TODO: replace with hci_read_remote_features() + hci_read_remote_ext_features


    // TODO: Send invalid read of extended features that is out of bounds...
    // TODO: LMP Packets to send:
    // 

    // printf("Sleeping %d seconds to wait to see final traffic...\n", sleep_seconds);
    // sleep(sleep_seconds);

	if (hci_disconnect(dev, htobs(handle), HCI_OE_USER_ENDED_CONNECTION, 10000) < 0)
		perror("Disconnect failed");

    hci_close_dev(dev);
    return 0;
}