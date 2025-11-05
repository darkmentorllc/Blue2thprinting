// Code by Xeno Kovah, Copyright Dark Mentor LLC (c) 2025
// Compilation command (executed from /home/user/Blue2thprinting/bluez-5.66):
// gcc -o Xeno_VSC_send_LMP_CLI tools/Xeno_VSC_send_LMP_CLI.c -Ilib -Isrc -Isrc/shared -I. -Llib/.libs -lbluetooth-internal -Lsrc/.libs -lshared-glib  $(pkg-config --cflags --libs glib-2.0) -DVERSION=\"5.66\"

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>

int check_expected_values(int dev, unsigned char offset, unsigned char value){
    unsigned char buf[HCI_MAX_EVENT_SIZE];
    int readlen;

    char header_len = 3;
    int end_time = time(NULL) + 2;
    // Loop for maximum of 2 seconds, waiting to see if we get back the response data we expect
    while (time(NULL) < end_time) {
        printf("Attempting to read HCI events...\n");
        // Read HCI event
        readlen = read(dev, buf, sizeof(buf));
        if (readlen < 0) {
            perror("Failed to read HCI event\n");
            hci_close_dev(dev);
            return -1;
        }

        // Check if the event length is sufficient to access offset 0x1C
        if (readlen > offset + header_len) {
            if (buf[header_len + offset] == value) {
                printf("Found matching value 0x%02x at offset 0x%02x!\n", value, offset);
                return 1;
                break;
            } else {
                // printf("Value at offset 0x10: 0x%02X\n", buf[header_len+0x10]);
                printf("Value at offset 0x1C: 0x%02X\n", buf[header_len+offset]);
            }
        } else {
            printf("Event too short to check offset 0x1C, length: %d\n", readlen);
        }
    }
    return 0;
}

int main(int argc, char *argv[]) {
    bdaddr_t bdaddr;
    uint16_t handle;
	struct hci_filter flt;
	hci_event_hdr *hdr;
    uint8_t role = 0x00; // Default role: Central
    uint16_t ptype = HCI_DM1 | HCI_DM3 | HCI_DM5 | HCI_DH1 | HCI_DH3 | HCI_DH5;

    if (argc < 4) {
        fprintf(stderr, "Usage: %s <bdaddr> <ogf> <ocf> [parameters]\n", argv[0]);
        return 1;
    }

    str2ba(argv[1], &bdaddr);

    int dev_id = hci_get_route(&bdaddr);
    if (dev_id < 0) {
        perror("HCI device not found");
        return 1;
    }

    int dev = hci_open_dev(dev_id);
    if (dev < 0) {
        perror("Failed to open HCI device");
        return 1;
    }

    if (hci_create_connection(dev, &bdaddr, htobs(ptype), htobs(0x0000), 
                              role, &handle, 25000) < 0) {
        perror("Failed to create connection");
        hci_close_dev(dev);
        return 1;
    }

    printf("Connection handle: %d (0x%04x)\n", handle, handle);

	/* Setup filter */
	hci_filter_clear(&flt);
	hci_filter_set_ptype(HCI_EVENT_PKT, &flt);
	hci_filter_all_events(&flt);
	if (setsockopt(dev, SOL_HCI, HCI_FILTER, &flt, sizeof(flt)) < 0) {
		perror("HCI filter setup failed");
		exit(EXIT_FAILURE);
	}

    // Parse OGF and OCF
    uint8_t ogf = (uint8_t)strtol(argv[2], NULL, 16);
    uint16_t ocf = (uint16_t)strtol(argv[3], NULL, 16);

    if (ogf > 0x3F || ocf > 0x03FF) {
        fprintf(stderr, "Invalid OGF or OCF value\n");
        hci_close_dev(dev);
        return 1;
    }

    // Parse additional parameters
    unsigned char buf[HCI_MAX_EVENT_SIZE], *ptr = buf;
    int len = 0;
    for (int i = 4; i < argc && len < (int)sizeof(buf); i++, len++) {
        *ptr++ = (unsigned char)strtol(argv[i], NULL, 16);
    }

    printf("< HCI Command: ogf 0x%02x, ocf 0x%04x, plen %d\n", ogf, ocf, len);
    if (len > 0) {
        printf("  Parameters: ");
        for (int i = 0; i < len; i++) {
            printf("%02x ", buf[i]);
        }
        printf("\n");
    }

    printf("Attempting to read send HCI command...\n");
    // Send the HCI command
    if (hci_send_cmd(dev, ogf, ocf, len, buf) < 0) {
        perror("Failed to send HCI command");
        hci_close_dev(dev);
        return 1;
    }

    printf("Checking offset 0x1C == 0x4C...\n");
    int ret = check_expected_values(dev, 0x1C, 0x4C);
    switch(ret)
    {
        case 1:
            printf("Success: Found expected value at offset\n");
            break;
        case 0:
            printf("Failure: Did not find expected value at offset and timed out\n");
            break;
        case -1:
            printf("Error occurred while checking expected value\n");
            hci_close_dev(dev);
            return 1;
    }
    int n = 2;
    printf("Sleeping %d seconds to wait to see final traffic...\n", n);
    sleep(n);
    // while(n > 0) {
    //     if (hci_send_cmd(dev, ogf, ocf, len, buf) < 0) {
    //         perror("Failed to send HCI command");
    //         hci_close_dev(dev);
    //         return 1;
    //     }
    
    //     printf("%d...\n", n);
    //     sleep(1);
    //     n--;
    // }

	if (hci_disconnect(dev, htobs(handle), HCI_OE_USER_ENDED_CONNECTION, 10000) < 0)
		perror("Disconnect failed");

    hci_close_dev(dev);
    return 0;
}