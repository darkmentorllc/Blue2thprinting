// Code by Xeno Kovah, Copyright Dark Mentor LLC (c) 2025-2026
//
// Compilation command (executed from <repo>/bluez-5.66/):
//   gcc -O2 -Wall -o tools/Xeno_VSC_send_LMP_hardcoded
//       tools/Xeno_VSC_send_LMP_hardcoded.c
//       -Ilib -Isrc -Isrc/shared -I. -Llib/.libs -lbluetooth-internal
//       -Lsrc/.libs -lshared-glib $(pkg-config --cflags --libs glib-2.0 json-c)
//       -lpthread -DVERSION="5.66"
//
// VSE byte layout vs. the Bumble Python prototype:
//   The Bumble prototype (DarkFirmware_real_i/05_XENO_VSC_RX_TX/bumble/examples/
//   Xeno_VSC_send_custom_LMP.py:49-78) sees `payload[0x1C]` as the LMP opcode byte.
//   Bumble strips the 3-byte HCI prefix (1 byte HCI packet-type + 2-byte hci_event_hdr)
//   before invoking add_vendor_factory, so its offset 0x1C corresponds to 0x1C+3 = 0x1F
//   in the raw read() buffer this tool consumes. The +3 accounting below is therefore
//   correct, and `0x41414141` magic appears at buf[3..6] in raw form.

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <limits.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>
#include <pthread.h>
#include <json-c/json.h>

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
#define opcode_MAX_VALUE                                      128

const char *lmp_opcode_names[] = {
    "RESERVED",                         // 0
    "LMP_NAME_REQ",                     // 1
    "LMP_NAME_RES",                     // 2
    "LMP_ACCEPTED",                     // 3
    "LMP_NOT_ACCEPTED",                 // 4
    "LMP_CLKOFFSET_REQ",                // 5
    "LMP_CLKOFFSET_RES",                // 6
    "LMP_DETACH",                       // 7
    "LMP_IN_RAND",                      // 8
    "LMP_COMB_KEY",                     // 9
    "LMP_UNIT_KEY",                     // 10
    "LMP_AU_RAND",                      // 11
    "LMP_SRES",                         // 12
    "LMP_TEMP_RAND",                    // 13
    "LMP_TEMP_KEY",                     // 14
    "LMP_ENCRYPTION_MODE_REQ",          // 15
    "LMP_ENCRYPTION_KEY_SIZE_REQ",      // 16
    "LMP_START_ENCRYPTION_REQ",         // 17
    "LMP_STOP_ENCRYPTION_REQ",          // 18
    "LMP_SWITCH_REQ",                   // 19
    "LMP_HOLD",                         // 20
    "LMP_HOLD_REQ",                     // 21
    "LMP_SNIFF",                        // 22
    "LMP_SNIFF_REQ",                    // 23
    "LMP_UNSNIFF_REQ",                  // 24
    "LMP_PARK_REQ",                     // 25
    "RESERVED",                         // 26
    "LMP_SET_BROADCAST_SCAN_WINDOW",    // 27
    "LMP_MODIFY_BEACON",                // 28
    "LMP_UNPARK_BD_ADDR_REQ",           // 29
    "LMP_UNPARK_PM_ADDR_REQ",           // 30
    "LMP_INCR_POWER_REQ",               // 31
    "LMP_DECR_POWER_REQ",               // 32
    "LMP_MAX_POWER",                    // 33
    "LMP_MIN_POWER",                    // 34
    "LMP_AUTO_RATE",                    // 35
    "LMP_PREFERRED_RATE",               // 36
    "LMP_VERSION_REQ",                  // 37
    "LMP_VERSION_RES",                  // 38
    "LMP_FEATURES_REQ",                 // 39
    "LMP_FEATURES_RES",                 // 40
    "LMP_QUALITY_OF_SERVICE",           // 41
    "LMP_QUALITY_OF_SERVICE_REQ",       // 42
    "LMP_SCO_LINK_REQ",                 // 43
    "LMP_REMOVE_SCO_LINK_REQ",          // 44
    "LMP_MAX_SLOT",                     // 45
    "LMP_MAX_SLOT_REQ",                 // 46
    "LMP_TIMING_ACCURACY_REQ",          // 47
    "LMP_TIMING_ACCURACY_RES",          // 48
    "LMP_SETUP_COMPLETE",               // 49
    "LMP_USE_SEMI_PERMANENT_KEY",       // 50
    "LMP_HOST_CONNECTION_REQ",          // 51
    "LMP_SLOT_OFFSET",                  // 52
    "LMP_PAGE_MODE_REQ",                // 53
    "LMP_PAGE_SCAN_MODE_REQ",           // 54
    "LMP_SUPERVISION_TIMEOUT",          // 55
    "LMP_TEST_ACTIVATE",                // 56
    "LMP_TEST_CONTROL",                 // 57
    "LMP_ENCRYPTION_KEY_SIZE_MASK_REQ", // 58
    "LMP_ENCRYPTION_KEY_SIZE_MASK_RES", // 59
    "LMP_SET_AFH",                      // 60
    "LMP_ENCAPSULATED_HEADER",          // 61
    "LMP_ENCAPSULATED_PAYLOAD",         // 62
    "LMP_SIMPLE_PAIRING_CONFIRM",       // 63
};
#define LMP_OPCODE_NAMES_SIZE (sizeof(lmp_opcode_names) / sizeof(lmp_opcode_names[0]))

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
#define ext_opcode_LMP_PP_EXTENSION_REQ           10
#define ext_opcode_LMP_PACKET_TYPE_TABLE_REQ      11
#define ext_opcode_LMP_ESCO_LINK_REQ              12
#define ext_opcode_LMP_REMOVE_ESCO_LINK_REQ       13
// 14, 15 reserved
#define ext_opcode_LMP_CHANNEL_CLASSIFICATION_REQ 16
#define ext_opcode_LMP_CHANNEL_CLASSIFICATION     17
#define ext_opcode_LMP_ALIAS_ADDRESS              18
#define ext_opcode_LMP_ACTIVE_ADDRESS             19
#define ext_opcode_LMP_FIXED_ADDRESS              20
#define ext_opcode_LMP_SNIFF_SUBRATING_REQ        21
#define ext_opcode_LMP_SNIFF_SUBRATING_RES        22
#define ext_opcode_LMP_PAUSE_ENCRYPTION_REQ       23
#define ext_opcode_LMP_RESUME_ENCRYPTION_REQ      24
#define ext_opcode_LMP_IO_CAPABILITY_REQUEST      25
#define ext_opcode_LMP_IO_CAPABILITY_RESPONSE     26
#define ext_opcode_LMP_NUMERIC_COMPARISON_FAILED  27
#define ext_opcode_LMP_PASSKEY_ENTRY_FAILED       28
#define ext_opcode_LMP_OOB_FAILED                 29
#define ext_opcode_LMP_KEYPRESS_NOTIFICATION      30
#define ext_opcode_LMP_POWER_CONTROL_REQ          31
#define ext_opcode_LMP_POWER_CONTROL_RESP         32
#define ext_opcode_MAX_VALUE                      33

const char *lmp_ext_opcode_names[ext_opcode_MAX_VALUE] = {
    "RESERVED",                         // 0
    "LMP_ACCEPTED_EXT",                 // 1
    "LMP_NOT_ACCEPTED_EXT",             // 2
    "LMP_FEATURES_REQ_EXT",             // 3
    "LMP_FEATURES_RES_EXT",             // 4
    "LMP_SCATTER_REQ",                  // 5
    "LMP_UNSCATTER_REQ",                // 6
    "LMP_SET_SUBRATE",                  // 7
    "LMP_SCATTER_ALGORITHMS_REQ",       // 8
    "LMP_SCATTER_ALGORITHMS_RES",       // 9
    "LMP_PP_EXTENSION_REQ",             // 10
    "LMP_PACKET_TYPE_TABLE_REQ",        // 11
    "LMP_ESCO_LINK_REQ",                // 12
    "LMP_REMOVE_ESCO_LINK_REQ",         // 13
    "RESERVED",                         // 14
    "RESERVED",                         // 15
    "LMP_CHANNEL_CLASSIFICATION_REQ",   // 16
    "LMP_CHANNEL_CLASSIFICATION",       // 17
    "LMP_ALIAS_ADDRESS",                // 18
    "LMP_ACTIVE_ADDRESS",               // 19
    "LMP_FIXED_ADDRESS",                // 20
    "LMP_SNIFF_SUBRATING_REQ",          // 21
    "LMP_SNIFF_SUBRATING_RES",          // 22
    "LMP_PAUSE_ENCRYPTION_REQ",         // 23
    "LMP_RESUME_ENCRYPTION_REQ",        // 24
    "LMP_IO_CAPABILITY_REQUEST",        // 25
    "LMP_IO_CAPABILITY_RESPONSE",       // 26
    "LMP_NUMERIC_COMPARISON_FAILED",    // 27
    "LMP_PASSKEY_ENTRY_FAILED",         // 28
    "LMP_OOB_FAILED",                   // 29
    "LMP_KEYPRESS_NOTIFICATION",        // 30
    "LMP_POWER_CONTROL_REQ",            // 31
    "LMP_POWER_CONTROL_RESP",           // 32
};

#define OPCODE_SEEN(x) (g_lmp_opcodes_seen & (1ULL << (x)))
#define EXT_OPCODE_SEEN(x) (g_lmp_ext_opcodes_seen & (1ULL << (x)))

// Payload size table (opcode -> payload bytes excluding the opcode byte).
// Mirrors examples/LMP_common.py:163 LMP_BASIC_OPCODES_TO_BYTE_SIZES.
// Only entries we actually need to parse; everything else falls back to
// the variable-length read up to readlen.
static int lmp_payload_size_for(int opcode) {
    switch (opcode) {
    case opcode_LMP_ACCEPTED:        return 1;
    case opcode_LMP_NOT_ACCEPTED:    return 2;
    case opcode_LMP_NAME_REQ:        return 16;
    case opcode_LMP_NAME_RES:        return 16;
    case opcode_LMP_VERSION_REQ:     return 5;
    case opcode_LMP_VERSION_RES:     return 5;
    case opcode_LMP_FEATURES_REQ:    return 8;
    case opcode_LMP_FEATURES_RES:    return 8;
    default:                         return -1;
    }
}

// State machine bitmask
unsigned long long gAllRequiredResponses = 0;
#define RR_LMP_FEATURES_RES         (1ULL << 0)
#define RR_LMP_FEATURES_RES_EXT     (1ULL << 1)
#define RR_LMP_VERSION_RES          (1ULL << 2)
#define RR_LMP_NAME_RES             (1ULL << 3)
#define RR_ALL_DONE  (RR_LMP_FEATURES_RES | RR_LMP_FEATURES_RES_EXT | \
                      RR_LMP_VERSION_RES | RR_LMP_NAME_RES)

// Per-target state
static unsigned char gSent_LMP_features_req = 0;
static unsigned char gSent_LMP_features_req_ext = 0;
static unsigned char gSent_LMP_name_req = 0;
static unsigned char gSent_LMP_version_req = 0;
static unsigned char gMaxExtendedFeaturePages = 0;
static unsigned char gExtFeaturePagesRequested = 0;
static char gName[512] = {0};
static int g_max_offset_so_far = 0;
static char gMoreNameNeeded = 0;
static char g_target_bdaddr_str[32] = {0};

// Captured payload buffers (index by opcode; covers both standard 0..127
// and extended 0..255 ranges).
static unsigned char g_lmp_payload[opcode_MAX_VALUE][32];
static unsigned char g_lmp_payload_len[opcode_MAX_VALUE];
static unsigned char g_lmp_ext_payload[256][32];
static unsigned char g_lmp_ext_payload_len[256];

// Mutexes for protecting access to global state shared between the reader
// thread and the main state-machine driver.
pthread_mutex_t g_lmp_opcodes_mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t g_lmp_ext_opcodes_mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t g_btides_mutex = PTHREAD_MUTEX_INITIALIZER;

// CLI / runtime config
static char g_btides_out_dir[1024] = {0};
static int  g_max_feature_pages_cli = 10;
static int  g_timeout_sec = 10;
static unsigned int g_experimental = 0;
static int  g_btides_overwrite = 0;
static int  g_hci_dev_id = -1; // -1 = auto-detect Realtek; otherwise CLI override

// 5-minute (300-s) aggregation window. Multiple runs against the same BDADDR
// within this window append to the same SingleBDADDR's LMPArray; runs after
// the window create a fresh SingleBDADDR entry in the same file.
#define BTIDES_WINDOW_SECONDS 300
static int64_t g_run_unix_time = 0; // captured once at startup, stamped on every emitted PDU

// BTIDES JSON state
static struct json_object *g_btides_root = NULL;     // top-level array
static struct json_object *g_single_bdaddr = NULL;   // SingleBDADDR object
static struct json_object *g_lmp_array = NULL;       // LMPArray array
static char g_btides_path[1280] = {0};
static int  g_btides_written = 0;

// Resources we need to clean up on exit.
static int  g_dev = -1;
static int  g_have_handle = 0;
static uint16_t g_handle = 0;

// ---------------------------------------------------------------------------
// Output path resolution: <repo>/Logs/DarkFirmwareLMPLog/<bdaddr>.btides
// Mirrors LMP2thprint.cpp:36-61's binary-relative repo discovery.
// ---------------------------------------------------------------------------
static void init_btides_out_dir(void) {
    if (g_btides_out_dir[0] != '\0') return; // already set via CLI
    const char *override = getenv("B2TP_BTIDES_DIR");
    if (override) {
        snprintf(g_btides_out_dir, sizeof(g_btides_out_dir), "%s", override);
        return;
    }
    char exe[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
    if (n <= 0) {
        snprintf(g_btides_out_dir, sizeof(g_btides_out_dir),
                 "Logs/DarkFirmwareLMPLog");
        return;
    }
    exe[n] = '\0';
    // Strip 3 path components: binary name, "tools", "bluez-5.66" -> repo root
    for (int i = 0; i < 3; i++) {
        char *slash = strrchr(exe, '/');
        if (!slash) {
            snprintf(g_btides_out_dir, sizeof(g_btides_out_dir),
                     "Logs/DarkFirmwareLMPLog");
            return;
        }
        *slash = '\0';
    }
    snprintf(g_btides_out_dir, sizeof(g_btides_out_dir),
             "%s/Logs/DarkFirmwareLMPLog", exe);
}

// mkdir -p emulator
static int mkdir_p(const char *path) {
    char buf[1280];
    snprintf(buf, sizeof(buf), "%s", path);
    size_t len = strlen(buf);
    if (len == 0) return -1;
    for (size_t i = 1; i < len; i++) {
        if (buf[i] == '/') {
            buf[i] = '\0';
            if (mkdir(buf, 0755) < 0 && errno != EEXIST) return -1;
            buf[i] = '/';
        }
    }
    if (mkdir(buf, 0755) < 0 && errno != EEXIST) return -1;
    return 0;
}

// Lowercase-no-colons of "AA:BB:CC:DD:EE:FF" -> "aabbccddeeff"
static void bdaddr_compact(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 1 < dstsz; i++) {
        if (src[i] == ':') continue;
        dst[j++] = (src[i] >= 'A' && src[i] <= 'Z') ? src[i] + 32 : src[i];
    }
    dst[j] = '\0';
}

// Lowercase colon-format for the JSON bdaddr field.
static void bdaddr_lower_colon(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 1 < dstsz; i++) {
        dst[j++] = (src[i] >= 'A' && src[i] <= 'Z') ? src[i] + 32 : src[i];
    }
    dst[j] = '\0';
}

// ---------------------------------------------------------------------------
// BTIDES JSON construction
// ---------------------------------------------------------------------------
//
// Schema reference: Analysis/BTIDES_Schema/BTIDES_LMP.json. The parser
// (Analysis/BTIDES_to_SQL.py) uses both struct-form and full_pkt_hex_str
// variants. We emit struct form for FEATURES_RES / VERSION_RES / FEATURES_RES_EXT
// because it's clearer; LMP_NAME_RES uses the full_pkt_hex_str variant because
// import_LMP_NAME_RES_fragmented() in BTIDES_to_SQL.py:741-751 only reads that.

// Per Analysis/BTIDES_Schema/BTIDES_base.json, std_optional_fields is anyOf
// {time, src_file, channel_freq, RSSI}. We only set time. The time object
// schema permits unix_time / unix_time_milli / time_str1 — we use unix_time.
static void btides_add_std_optional_fields(struct json_object *o) {
    if (g_run_unix_time <= 0) return;
    struct json_object *t = json_object_new_object();
    json_object_object_add(t, "unix_time", json_object_new_int64(g_run_unix_time));
    json_object_object_add(o, "std_optional_fields", t);
}

static void hex_str_lower(const unsigned char *bytes, size_t n, char *out) {
    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        out[2*i + 0] = hex[(bytes[i] >> 4) & 0xF];
        out[2*i + 1] = hex[bytes[i] & 0xF];
    }
    out[2*n] = '\0';
}

// Read 8 bytes of features little-endian into a 16-char hex string.
// Per Analysis/BTIDES_to_SQL.py:849, the parser reads the hex-str as
// little-endian to recover the integer features value.
static void features_hex_le(const unsigned char *features8, char out17[17]) {
    for (int i = 0; i < 8; i++) {
        static const char hex[] = "0123456789abcdef";
        unsigned char b = features8[i];
        out17[2*i + 0] = hex[(b >> 4) & 0xF];
        out17[2*i + 1] = hex[b & 0xF];
    }
    out17[16] = '\0';
}

static struct json_object *btides_lmp_features_res(const unsigned char *features8) {
    struct json_object *o = json_object_new_object();
    char hex[17];
    features_hex_le(features8, hex);
    json_object_object_add(o, "opcode", json_object_new_int(opcode_LMP_FEATURES_RES));
    json_object_object_add(o, "lmp_features_hex_str", json_object_new_string(hex));
    btides_add_std_optional_fields(o);
    return o;
}

static struct json_object *btides_lmp_features_req(const unsigned char *features8) {
    struct json_object *o = json_object_new_object();
    char hex[17];
    features_hex_le(features8, hex);
    json_object_object_add(o, "opcode", json_object_new_int(opcode_LMP_FEATURES_REQ));
    json_object_object_add(o, "lmp_features_hex_str", json_object_new_string(hex));
    btides_add_std_optional_fields(o);
    return o;
}

static struct json_object *btides_lmp_features_res_or_req_ext(int ext_opcode,
                                                              uint8_t page,
                                                              uint8_t max_page,
                                                              const unsigned char *features8) {
    struct json_object *o = json_object_new_object();
    char hex[17];
    features_hex_le(features8, hex);
    json_object_object_add(o, "escape_127", json_object_new_int(127));
    json_object_object_add(o, "extended_opcode", json_object_new_int(ext_opcode));
    json_object_object_add(o, "page", json_object_new_int(page));
    json_object_object_add(o, "max_page", json_object_new_int(max_page));
    json_object_object_add(o, "lmp_features_hex_str", json_object_new_string(hex));
    btides_add_std_optional_fields(o);
    return o;
}

// LMP_VERSION_RES: 5-byte payload = version(1), company_id(2 LE), subversion(2 LE).
static struct json_object *btides_lmp_version_res(const unsigned char *p5) {
    struct json_object *o = json_object_new_object();
    uint8_t  version    = p5[0];
    uint16_t company_id = (uint16_t)p5[1] | ((uint16_t)p5[2] << 8);
    uint16_t subversion = (uint16_t)p5[3] | ((uint16_t)p5[4] << 8);
    json_object_object_add(o, "opcode", json_object_new_int(opcode_LMP_VERSION_RES));
    json_object_object_add(o, "version", json_object_new_int(version));
    json_object_object_add(o, "company_id", json_object_new_int(company_id));
    json_object_object_add(o, "subversion", json_object_new_int(subversion));
    btides_add_std_optional_fields(o);
    return o;
}

static struct json_object *btides_lmp_version_req(const unsigned char *p5) {
    struct json_object *o = json_object_new_object();
    uint8_t  version    = p5[0];
    uint16_t company_id = (uint16_t)p5[1] | ((uint16_t)p5[2] << 8);
    uint16_t subversion = (uint16_t)p5[3] | ((uint16_t)p5[4] << 8);
    json_object_object_add(o, "opcode", json_object_new_int(opcode_LMP_VERSION_REQ));
    json_object_object_add(o, "version", json_object_new_int(version));
    json_object_object_add(o, "company_id", json_object_new_int(company_id));
    json_object_object_add(o, "subversion", json_object_new_int(subversion));
    btides_add_std_optional_fields(o);
    return o;
}

// LMP_NAME_RES2 form: opcode + full_pkt_hex_str (offset || length || fragment).
// payload[0] = name_offset, payload[1] = name_length, payload[2..] = fragment.
static struct json_object *btides_lmp_name_res_fragment(const unsigned char *payload,
                                                        size_t payload_len) {
    if (payload_len < 2) return NULL;
    struct json_object *o = json_object_new_object();
    char hex[2 * 32 + 1];
    size_t n = payload_len;
    if (n > 32) n = 32;
    hex_str_lower(payload, n, hex);
    json_object_object_add(o, "opcode", json_object_new_int(opcode_LMP_NAME_RES));
    json_object_object_add(o, "full_pkt_hex_str", json_object_new_string(hex));
    btides_add_std_optional_fields(o);
    return o;
}

static void btides_append(struct json_object *obj) {
    if (!obj) return;
    pthread_mutex_lock(&g_btides_mutex);
    if (g_lmp_array) {
        json_object_array_add(g_lmp_array, obj);
    } else {
        json_object_put(obj);
    }
    pthread_mutex_unlock(&g_btides_mutex);
}

// Initialize root JSON: array of one SingleBDADDR with empty LMPArray.
// Used when no existing .btides file is found for this target.
static void btides_init_fresh(const char *bdaddr_lower_colon_str) {
    g_btides_root = json_object_new_array();
    g_single_bdaddr = json_object_new_object();
    json_object_object_add(g_single_bdaddr, "bdaddr",
                           json_object_new_string(bdaddr_lower_colon_str));
    json_object_object_add(g_single_bdaddr, "bdaddr_rand", json_object_new_int(0));
    g_lmp_array = json_object_new_array();
    json_object_object_add(g_single_bdaddr, "LMPArray", g_lmp_array);
    json_object_array_add(g_btides_root, g_single_bdaddr);
}

// Find the latest unix_time stamped on any PDU in this SingleBDADDR's
// LMPArray (looks under each LMP entry's std_optional_fields.unix_time).
// Returns 0 if no timestamps are present, treating the entry as old.
static int64_t latest_unix_time_in_lmp_array(struct json_object *lmp_array) {
    if (!lmp_array || !json_object_is_type(lmp_array, json_type_array)) return 0;
    int64_t latest = 0;
    int n = json_object_array_length(lmp_array);
    for (int i = 0; i < n; i++) {
        struct json_object *pdu = json_object_array_get_idx(lmp_array, i);
        struct json_object *sof = NULL, *jt = NULL;
        if (!json_object_object_get_ex(pdu, "std_optional_fields", &sof)) continue;
        if (!json_object_object_get_ex(sof, "unix_time", &jt)) continue;
        int64_t t = json_object_get_int64(jt);
        if (t > latest) latest = t;
    }
    return latest;
}

// Append a new SingleBDADDR entry to the root array. Caller installs LMPArray.
static struct json_object *append_new_singlebdaddr(struct json_object *root,
                                                   const char *bdaddr_lower_colon_str) {
    struct json_object *e = json_object_new_object();
    json_object_object_add(e, "bdaddr",
                           json_object_new_string(bdaddr_lower_colon_str));
    json_object_object_add(e, "bdaddr_rand", json_object_new_int(0));
    json_object_array_add(root, e);
    return e;
}

// Parse an existing .btides file (or start fresh) and pick the SingleBDADDR
// entry to append PDUs to during this run, applying a 5-minute aggregation
// window:
//   - Walk the root array from the END backwards. The first SingleBDADDR
//     matching our (bdaddr, bdaddr_rand=0) is the most recent. Look at its
//     LMPArray timestamps.
//   - If max(unix_time) is 0 (empty/unstamped) OR within BTIDES_WINDOW_SECONDS
//     of now, reuse it.
//   - Otherwise append a fresh SingleBDADDR at the end of the array. New PDUs
//     captured during this run will be timestamped with g_run_unix_time.
// `--btides-overwrite` skips all of this and starts a 1-element array.
static void btides_load_or_init(const char *bdaddr_lower_colon_str) {
    if (g_btides_overwrite) {
        btides_init_fresh(bdaddr_lower_colon_str);
        return;
    }
    struct json_object *existing = json_object_from_file(g_btides_path);
    if (!existing || !json_object_is_type(existing, json_type_array)) {
        if (existing) json_object_put(existing);
        btides_init_fresh(bdaddr_lower_colon_str);
        return;
    }
    g_btides_root = existing;

    // Find the most recent SingleBDADDR entry for this BDADDR.
    int n = json_object_array_length(existing);
    struct json_object *most_recent = NULL;
    for (int i = n - 1; i >= 0; i--) {
        struct json_object *item = json_object_array_get_idx(existing, i);
        struct json_object *jbd = NULL, *jrand = NULL;
        if (!json_object_object_get_ex(item, "bdaddr", &jbd)) continue;
        if (!json_object_object_get_ex(item, "bdaddr_rand", &jrand)) continue;
        if (json_object_get_int(jrand) != 0) continue;
        if (strcasecmp(json_object_get_string(jbd), bdaddr_lower_colon_str) != 0) continue;
        most_recent = item;
        break;
    }

    if (most_recent != NULL) {
        struct json_object *jarr = NULL;
        json_object_object_get_ex(most_recent, "LMPArray", &jarr);
        int64_t latest = latest_unix_time_in_lmp_array(jarr);
        // Reuse if empty (latest==0, treat as still-open) OR within window.
        // The empty case lets a previous timed-out run with 0 PDUs be filled.
        if (latest == 0 || (g_run_unix_time - latest) <= BTIDES_WINDOW_SECONDS) {
            g_single_bdaddr = most_recent;
            if (jarr && json_object_is_type(jarr, json_type_array)) {
                g_lmp_array = jarr;
            } else {
                g_lmp_array = json_object_new_array();
                json_object_object_add(g_single_bdaddr, "LMPArray", g_lmp_array);
            }
            fprintf(stderr,
                    "[*] Reusing SingleBDADDR (latest_ts=%lld, age=%llds, window=%ds)\n",
                    (long long)latest,
                    (long long)(latest > 0 ? g_run_unix_time - latest : 0),
                    BTIDES_WINDOW_SECONDS);
            return;
        }
        fprintf(stderr,
                "[*] Most recent SingleBDADDR is %llds old (>%ds); creating new entry.\n",
                (long long)(g_run_unix_time - latest), BTIDES_WINDOW_SECONDS);
    }

    // No matching entry, or out of window: append a fresh SingleBDADDR.
    g_single_bdaddr = append_new_singlebdaddr(g_btides_root, bdaddr_lower_colon_str);
    g_lmp_array = json_object_new_array();
    json_object_object_add(g_single_bdaddr, "LMPArray", g_lmp_array);
}

static void write_btides_file(void) {
    pthread_mutex_lock(&g_btides_mutex);
    if (g_btides_written) {
        pthread_mutex_unlock(&g_btides_mutex);
        return;
    }
    g_btides_written = 1;
    if (!g_btides_root) {
        pthread_mutex_unlock(&g_btides_mutex);
        return;
    }
    if (mkdir_p(g_btides_out_dir) < 0) {
        fprintf(stderr, "[!] Failed to mkdir %s: %s\n", g_btides_out_dir, strerror(errno));
        pthread_mutex_unlock(&g_btides_mutex);
        return;
    }
    int n_pdus = g_lmp_array ? json_object_array_length(g_lmp_array) : 0;
    int rc = json_object_to_file_ext(g_btides_path, g_btides_root,
                                     JSON_C_TO_STRING_PLAIN);
    int all_done = ((gAllRequiredResponses & RR_ALL_DONE) == RR_ALL_DONE);
    pthread_mutex_unlock(&g_btides_mutex);
    if (rc < 0) {
        fprintf(stderr, "[!] Failed to write %s: %s\n",
                g_btides_path, strerror(errno));
    } else {
        fprintf(stderr, "[+] wrote %s (%d PDUs, all=%s)\n",
                g_btides_path, n_pdus, all_done ? "YES" : "NO");
    }
}

// ---------------------------------------------------------------------------
// VSE parser. Replaces the inline body of the original threaded_hci_read.
// ---------------------------------------------------------------------------

static void parse_name_fragment(const unsigned char *payload, int payload_len);

static void parse_vse(const unsigned char *buf, int readlen) {
    static const unsigned char MAGIC[4] = {0x41, 0x41, 0x41, 0x41};
    // Need at least: 3 (HCI prefix) + 4 (magic) + payload up to opcode byte
    if (readlen < (int)(0x1F + 1)) return;
    if (memcmp(buf + 3, MAGIC, 4) != 0) return; // not one of our VSEs

    unsigned char raw = buf[0x1F];
    if (raw == 0xCC) return; // uninitialized memory sentinel from firmware

    int opcode = raw >> 1;
    int ext_opcode = -1;
    int payload_offset;
    if (opcode == 0x7F) {
        if (readlen < 0x21) return;
        ext_opcode = buf[0x20];
        payload_offset = 0x21;
    } else {
        payload_offset = 0x20;
    }

    // Determine payload length to copy.
    int psize = lmp_payload_size_for(opcode);
    int payload_len;
    if (psize >= 0) {
        payload_len = psize;
    } else if (ext_opcode == ext_opcode_LMP_FEATURES_RES_EXT ||
               ext_opcode == ext_opcode_LMP_FEATURES_REQ_EXT) {
        payload_len = 10; // 1 page + 1 max_page + 8 features
    } else {
        // Unknown: read whatever's available, capped to 31 bytes.
        payload_len = readlen - payload_offset;
        if (payload_len > 31) payload_len = 31;
        if (payload_len < 0) payload_len = 0;
    }
    if (payload_offset + payload_len > readlen) {
        payload_len = readlen - payload_offset;
        if (payload_len < 0) payload_len = 0;
    }

    fprintf(stderr, "\t[!] VSE opcode raw=0x%02X opcode=%d ext=%d plen=%d\n",
            raw, opcode, ext_opcode, payload_len);

    // Side effects + BTIDES emission.
    if (opcode == 0x7F && ext_opcode >= 0) {
        pthread_mutex_lock(&g_lmp_ext_opcodes_mutex);
        g_lmp_ext_opcodes_seen |= (1ULL << ext_opcode);
        if (payload_len > 0 && payload_len <= 31) {
            memcpy(g_lmp_ext_payload[ext_opcode], buf + payload_offset, payload_len);
            g_lmp_ext_payload_len[ext_opcode] = payload_len;
        }
        pthread_mutex_unlock(&g_lmp_ext_opcodes_mutex);

        if (ext_opcode == ext_opcode_LMP_FEATURES_RES_EXT && payload_len >= 10) {
            const unsigned char *p = buf + payload_offset;
            uint8_t page     = p[0];
            uint8_t max_page = p[1];
            const unsigned char *features8 = p + 2;
            if (gMaxExtendedFeaturePages == 0) {
                // First reply: latch the device's stated max page count.
                gMaxExtendedFeaturePages = max_page;
            }
            gAllRequiredResponses |= RR_LMP_FEATURES_RES_EXT;
            btides_append(btides_lmp_features_res_or_req_ext(
                ext_opcode_LMP_FEATURES_RES_EXT, page, max_page, features8));
        } else if (ext_opcode == ext_opcode_LMP_FEATURES_REQ_EXT && payload_len >= 10) {
            const unsigned char *p = buf + payload_offset;
            btides_append(btides_lmp_features_res_or_req_ext(
                ext_opcode_LMP_FEATURES_REQ_EXT, p[0], p[1], p + 2));
        }
    } else if (opcode > 0 && opcode < opcode_MAX_VALUE) {
        pthread_mutex_lock(&g_lmp_opcodes_mutex);
        g_lmp_opcodes_seen |= (1ULL << opcode);
        if (payload_len > 0 && payload_len <= 31) {
            memcpy(g_lmp_payload[opcode], buf + payload_offset, payload_len);
            g_lmp_payload_len[opcode] = payload_len;
        }
        pthread_mutex_unlock(&g_lmp_opcodes_mutex);

        const unsigned char *p = buf + payload_offset;
        if (opcode == opcode_LMP_FEATURES_RES && payload_len >= 8) {
            gAllRequiredResponses |= RR_LMP_FEATURES_RES;
            btides_append(btides_lmp_features_res(p));
        } else if (opcode == opcode_LMP_FEATURES_REQ && payload_len >= 8) {
            btides_append(btides_lmp_features_req(p));
        } else if (opcode == opcode_LMP_VERSION_RES && payload_len >= 5) {
            gAllRequiredResponses |= RR_LMP_VERSION_RES;
            btides_append(btides_lmp_version_res(p));
        } else if (opcode == opcode_LMP_VERSION_REQ && payload_len >= 5) {
            btides_append(btides_lmp_version_req(p));
        } else if (opcode == opcode_LMP_NAME_RES && payload_len >= 2) {
            // Emit each fragment as a separate LMP_NAME_RES2 record so
            // BTIDES_to_SQL.py:741-751 ingests them. Reassembly happens in
            // parse_name_fragment for the state-machine completion check.
            btides_append(btides_lmp_name_res_fragment(p, payload_len));
            parse_name_fragment(p, payload_len);
        }
    }
}

// Reassemble fragmented device name from successive LMP_NAME_RES packets.
// Ported from Braktooth_module/LMP2thprint.cpp:521-600. The packet offset
// translation differs because we receive only the LMP payload here (no ACL
// header to strip): payload[0] = name_offset, payload[1] = name_length,
// payload[2..] = name fragment bytes.
static void parse_name_fragment(const unsigned char *payload, int payload_len) {
    if (payload_len < 2) return;
    int name_offset = payload[0];
    int name_len    = payload[1];
    int frag_len    = payload_len - 2;
    if (frag_len < 0) frag_len = 0;
    const unsigned char *frag = payload + 2;

    if (name_len <= 14 && name_offset == 0 && frag_len >= name_len) {
        // Full name fits in one packet.
        if (name_len > (int)sizeof(gName) - 1) name_len = sizeof(gName) - 1;
        memset(gName, 0, sizeof(gName));
        memcpy(gName, frag, name_len);
        gName[name_len] = '\0';
        fprintf(stderr, "[+] BT Classic name: %s\n", gName);
        g_max_offset_so_far = 0;
        gMoreNameNeeded = 0;
        gAllRequiredResponses |= RR_LMP_NAME_RES;
        return;
    }

    // Fragmented: copy this fragment into the buffer.
    int copy_end = name_offset + frag_len;
    if (copy_end > (int)sizeof(gName)) copy_end = sizeof(gName);
    int j = 0;
    for (int i = name_offset; i < copy_end; i++) {
        gName[i] = frag[j++];
    }

    if (copy_end >= name_len) {
        // We've now received the full name.
        if (name_len > (int)sizeof(gName) - 1) name_len = sizeof(gName) - 1;
        gName[name_len] = '\0';
        fprintf(stderr, "[+] BT Classic name (defragged): %s\n", gName);
        g_max_offset_so_far = 0;
        gMoreNameNeeded = 0;
        gAllRequiredResponses |= RR_LMP_NAME_RES;
    } else {
        g_max_offset_so_far = copy_end;
        gMoreNameNeeded = 1;
    }
}

// Reader thread: just dispatches every event to parse_vse. The parser
// gates on event code internally.
void *threaded_hci_read(void *arg) {
    int dev = *(int *)arg;
    unsigned char buf[HCI_MAX_EVENT_SIZE];
    fprintf(stderr, "Thread started: Reading HCI events...\n");
    while (1) {
        int readlen = read(dev, buf, sizeof(buf));
        if (readlen < 0) {
            if (errno == EINTR) continue;
            perror("Failed to read HCI event");
            return NULL;
        }
        // hci_event_hdr at buf+1 (BlueZ raw socket leaves 1-byte HCI packet
        // type prefix). Filter for vendor-specific event 0xFF.
        if (readlen < 3) continue;
        hci_event_hdr *hdr = (void *)(buf + 1);
        if (hdr->evt != 0xFF) continue;
        parse_vse(buf, readlen);
    }
    return NULL;
}

// ---------------------------------------------------------------------------
// Send helpers. Per the firmware-side VSC contract: byte 0 = bare 7-bit LMP
// opcode, byte 1 = reserved/padding (0x00), bytes 2..N = LMP payload.
// The firmware left-shifts opcode and sets the TID. Matches the payloads
// in DarkFirmware_real_i/05_XENO_VSC_RX_TX/bumble/examples/Xeno_VSC_send_custom_LMP.py
// at lines 129 and 135.
// ---------------------------------------------------------------------------
static const uint8_t  XENO_OGF = 0x3F;
static const uint16_t XENO_OCF = 0x0222;

static int send_LMP_features_req(int dev) {
    unsigned char b[] = {
        39,    // byte 0: LMP opcode (LMP_FEATURES_REQ); firmware shifts + sets TID
        0x00,  // byte 1: reserved/padding
        0xff,  // features byte 0
        0xff,  // features byte 1
        0xff,  // features byte 2
        0xff,  // features byte 3
        0xff,  // features byte 4
        0xff,  // features byte 5
        0xff,  // features byte 6
        0xff,  // features byte 7
    };
    return hci_send_cmd(dev, XENO_OGF, XENO_OCF, sizeof(b), b);
}

static int send_LMP_features_req_ext(int dev, uint8_t page) {
    unsigned char b[] = {
        127,   // byte 0: escape opcode (LMP_FEATURES_REQ_EXT uses ext-opcode 3)
        0x00,  // byte 1: reserved/padding
        3,     // byte 2: ext-opcode = LMP_FEATURES_REQ_EXT
        page,  // byte 3: requested feature page
        0x02,  // byte 4: max_page we advertise
        0,     // features byte 0
        0,     // features byte 1
        0,     // features byte 2
        0,     // features byte 3
        0,     // features byte 4
        0,     // features byte 5
        0,     // features byte 6
        0,     // features byte 7
    };
    return hci_send_cmd(dev, XENO_OGF, XENO_OCF, sizeof(b), b);
}

static int send_LMP_name_req(int dev, uint8_t off) {
    unsigned char b[] = {
        1,     // byte 0: LMP opcode (LMP_NAME_REQ)
        0x00,  // byte 1: reserved/padding
        off,   // byte 2: name offset to retrieve from
    };
    return hci_send_cmd(dev, XENO_OGF, XENO_OCF, sizeof(b), b);
}

static int send_LMP_version_req(int dev) {
    unsigned char b[] = {
        37,    // byte 0: LMP opcode (LMP_VERSION_REQ)
        0x00,  // byte 1: reserved/padding
        0x0D,  // version = 0x0D
        0x4D,  // company_id LE byte 0 ("M")
        0x44,  // company_id LE byte 1 ("D") -> 0x444D = "DM"
        0x37,  // subversion LE byte 0 -> 0x1337
        0x13,  // subversion LE byte 1
    };
    return hci_send_cmd(dev, XENO_OGF, XENO_OCF, sizeof(b), b);
}

// ---------------------------------------------------------------------------
// State-machine driver. Runs in the main thread; watches flags set by
// parse_vse() in the reader thread. Hard wall-clock deadline.
// ---------------------------------------------------------------------------

static int wait_for_flag(unsigned long long flag_mask, int max_wait_seconds) {
    int end_time = time(NULL) + max_wait_seconds;
    while (time(NULL) < end_time) {
        if ((gAllRequiredResponses & flag_mask) == flag_mask) return 1;
        usleep(50 * 1000); // 50 ms
    }
    return 0;
}

static void run_state_machine(int dev) {
    int deadline = time(NULL) + g_timeout_sec;

    // Step 0: Read remote version eagerly. The Realtek+kernel combo exchanges
    // LMP version automatically during connection setup, and the device tends
    // to reject duplicate LMP_VERSION_REQs with LMP_NOT_ACCEPTED. Pulling the
    // cached version from the kernel up front gives us a clean record before
    // any injected requests can disrupt the link. Wait briefly for the
    // kernel-initiated exchange to land in the cache.
    usleep(500 * 1000);
    {
        struct hci_version vinfo;
        memset(&vinfo, 0, sizeof(vinfo));
        if (hci_read_remote_version(dev, htobs(g_handle), &vinfo, 5000) >= 0) {
            unsigned char p5[5];
            p5[0] = vinfo.lmp_ver;
            p5[1] = (unsigned char)(vinfo.manufacturer & 0xFF);
            p5[2] = (unsigned char)((vinfo.manufacturer >> 8) & 0xFF);
            p5[3] = (unsigned char)(vinfo.lmp_subver & 0xFF);
            p5[4] = (unsigned char)((vinfo.lmp_subver >> 8) & 0xFF);
            fprintf(stderr, "[+] hci_read_remote_version: ver=0x%02x mfr=0x%04x subver=0x%04x\n",
                    p5[0], vinfo.manufacturer, vinfo.lmp_subver);
            btides_append(btides_lmp_version_res(p5));
            gAllRequiredResponses |= RR_LMP_VERSION_RES;
        } else {
            fprintf(stderr, "[!] hci_read_remote_version failed: %s\n", strerror(errno));
        }
    }

    // Step 1: LMP_features_req
    if (!OPCODE_SEEN(opcode_LMP_FEATURES_RES) && time(NULL) < deadline) {
        fprintf(stderr, "[*] Sending LMP_features_req\n");
        if (send_LMP_features_req(dev) < 0) perror("send_LMP_features_req");
        gSent_LMP_features_req = 1;
        wait_for_flag(RR_LMP_FEATURES_RES, 1);
    } else {
        // Some controllers spontaneously exchange features; treat as done.
        if (OPCODE_SEEN(opcode_LMP_FEATURES_RES))
            gAllRequiredResponses |= RR_LMP_FEATURES_RES;
    }

    // Step 2: LMP_features_req_ext (page 1), then loop pages 2..max
    if (time(NULL) < deadline) {
        fprintf(stderr, "[*] Sending LMP_features_req_ext page=1\n");
        if (send_LMP_features_req_ext(dev, 1) < 0) perror("send_LMP_features_req_ext");
        gSent_LMP_features_req_ext = 1;
        gExtFeaturePagesRequested = 1;
        wait_for_flag(RR_LMP_FEATURES_RES_EXT, 1);
    }
    while (time(NULL) < deadline &&
           gExtFeaturePagesRequested < gMaxExtendedFeaturePages &&
           gExtFeaturePagesRequested < g_max_feature_pages_cli) {
        gExtFeaturePagesRequested++;
        fprintf(stderr, "[*] Sending LMP_features_req_ext page=%u (max=%u)\n",
                gExtFeaturePagesRequested, gMaxExtendedFeaturePages);
        if (send_LMP_features_req_ext(dev, gExtFeaturePagesRequested) < 0)
            perror("send_LMP_features_req_ext");
        // No per-page bitmask; just give the controller 1s to mirror something.
        sleep(1);
    }

    // Step 3: LMP_name_req with offset; reassemble fragments.
    int name_attempts = 0;
    while (time(NULL) < deadline && !(gAllRequiredResponses & RR_LMP_NAME_RES)
           && name_attempts < 16) {
        uint8_t offset = (uint8_t)(g_max_offset_so_far & 0xFF);
        fprintf(stderr, "[*] Sending LMP_name_req offset=%u\n", offset);
        if (send_LMP_name_req(dev, offset) < 0) perror("send_LMP_name_req");
        gSent_LMP_name_req = 1;
        // Wait briefly; the parser may set RR_LMP_NAME_RES (full name) or
        // gMoreNameNeeded=1 (need to send next offset).
        for (int i = 0; i < 20; i++) {
            if (gAllRequiredResponses & RR_LMP_NAME_RES) break;
            if (gMoreNameNeeded) { gMoreNameNeeded = 0; break; }
            usleep(50 * 1000);
        }
        name_attempts++;
    }

    // Step 4: If we *still* don't have version info (Step 0's read remote
    // version failed), try the injected VSC as a last resort.
    if (!(gAllRequiredResponses & RR_LMP_VERSION_RES) && time(NULL) < deadline) {
        fprintf(stderr, "[*] Sending LMP_version_req (Step 0 fallback)\n");
        if (send_LMP_version_req(dev) < 0) perror("send_LMP_version_req");
        gSent_LMP_version_req = 1;
        wait_for_flag(RR_LMP_VERSION_RES, 2);
    }

    if ((gAllRequiredResponses & RR_ALL_DONE) == RR_ALL_DONE) {
        fprintf(stderr, "[+] ALL RESPONSES RECEIVED for %s\n", g_target_bdaddr_str);
    } else {
        fprintf(stderr, "[!] %s 2THPRINTING TERMINATED DUE TO %d SEC TIMEOUT (got 0x%llx)\n",
                g_target_bdaddr_str, g_timeout_sec, gAllRequiredResponses);
    }
}

// ---------------------------------------------------------------------------
// Cleanup registered with atexit. Persists BTIDES + releases the ACL.
// ---------------------------------------------------------------------------
static void on_exit_cleanup(void) {
    write_btides_file();
    if (g_dev >= 0) {
        if (g_have_handle) {
            hci_disconnect(g_dev, htobs(g_handle), HCI_OE_USER_ENDED_CONNECTION, 5000);
        }
        hci_close_dev(g_dev);
        g_dev = -1;
    }
}

#include <signal.h>
static void on_signal(int sig) {
    (void)sig;
    on_exit_cleanup();
    _exit(2);
}

// ---------------------------------------------------------------------------
// Adapter selection: prefer the Realtek dongle (manufacturer ID 0x5D = 93)
// since hci_get_route() may pick the Pi's built-in radio instead, and the
// Pi's built-in is not the one we flashed with custom firmware.
// ---------------------------------------------------------------------------
#define REALTEK_MANUFACTURER 93
// Iterate UP adapters; for each, open it briefly and run HCI Read Local Version
// (per the Bluetooth spec, the Manufacturer_Name field is the company ID).
// Returns the first dev_id whose manufacturer is Realtek (93/0x5D), or -1.
static int find_realtek_dev_id(void) {
    int sock = socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI);
    if (sock < 0) return -1;
    struct hci_dev_list_req *dl = calloc(1, sizeof(*dl) +
                                            HCI_MAX_DEV * sizeof(struct hci_dev_req));
    if (!dl) { close(sock); return -1; }
    dl->dev_num = HCI_MAX_DEV;
    int found = -1;
    if (ioctl(sock, HCIGETDEVLIST, dl) >= 0) {
        for (int i = 0; i < dl->dev_num; i++) {
            int dev_id = dl->dev_req[i].dev_id;
            int d = hci_open_dev(dev_id);
            if (d < 0) continue;
            struct hci_version ver;
            memset(&ver, 0, sizeof(ver));
            if (hci_read_local_version(d, &ver, 1000) >= 0) {
                if (ver.manufacturer == REALTEK_MANUFACTURER) {
                    found = dev_id;
                    hci_close_dev(d);
                    break;
                }
            }
            hci_close_dev(d);
        }
    }
    free(dl);
    close(sock);
    return found;
}

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------
static void usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s <bdaddr> [options]\n"
        "       %s --target=<bdaddr> [options]\n"
        "\n"
        "Connects to the BR/EDR target via the Realtek dongle running\n"
        "DarkFirmware_real_i, then injects LMP packets via Xeno VSC and\n"
        "writes the captured PDUs to <out-dir>/<bdaddr_compact>.btides.\n"
        "\n"
        "Options:\n"
        "  --target=<AA:BB:CC:DD:EE:FF>   Target BR/EDR BDADDR (alternative to positional).\n"
        "  --hci=hciN | --hci=N           Pin to a specific HCI adapter. Default:\n"
        "                                 auto-detect by manufacturer id 0x5D (Realtek).\n"
        "  --btides-out-dir=<path>        Output directory. Default:\n"
        "                                 <repo>/Logs/DarkFirmwareLMPLog/\n"
        "                                 (or env B2TP_BTIDES_DIR)\n"
        "  --btides-overwrite             Replace any existing .btides file for this\n"
        "                                 BDADDR. Default: append, with 5-min windowing.\n"
        "  --max-feature-pages=<N>        Cap on extended-feature pages to request.\n"
        "                                 Default: 10.\n"
        "  --timeout-seconds=<N>          Wall-clock deadline for the run. Default: 10.\n"
        "  --experimental=<hex>           Reserved for malformed-LMP / KNOB modes.\n"
        "                                 Currently parsed but unused.\n"
        "  --host-port=<x>                Accepted-and-ignored. Present so the\n"
        "                                 Braktooth-era launcher invocation still works.\n"
        "  -h, --help                     Print this help and exit.\n",
        prog, prog);
}

static int parse_cli(int argc, char *argv[], char *bdaddr_out, size_t outsz) {
    int got_target = 0;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (strncmp(a, "--target=", 9) == 0) {
            snprintf(bdaddr_out, outsz, "%s", a + 9);
            got_target = 1;
        } else if (strncmp(a, "--btides-out-dir=", 17) == 0) {
            snprintf(g_btides_out_dir, sizeof(g_btides_out_dir), "%s", a + 17);
        } else if (strcmp(a, "--btides-overwrite") == 0) {
            g_btides_overwrite = 1;
        } else if (strncmp(a, "--max-feature-pages=", 20) == 0) {
            g_max_feature_pages_cli = atoi(a + 20);
            if (g_max_feature_pages_cli <= 0) g_max_feature_pages_cli = 10;
        } else if (strncmp(a, "--timeout-seconds=", 18) == 0) {
            g_timeout_sec = atoi(a + 18);
            if (g_timeout_sec <= 0) g_timeout_sec = 10;
        } else if (strncmp(a, "--experimental=", 15) == 0) {
            g_experimental = (unsigned int)strtoul(a + 15, NULL, 0);
        } else if (strncmp(a, "--host-port=", 12) == 0) {
            // accepted-and-ignored for Braktooth-launcher compatibility
        } else if (strncmp(a, "--hci=", 6) == 0) {
            const char *v = a + 6;
            if (strncmp(v, "hci", 3) == 0) v += 3;
            g_hci_dev_id = atoi(v);
        } else if (strcmp(a, "--help") == 0 || strcmp(a, "-h") == 0) {
            usage(argv[0]);
            exit(0);
        } else if (a[0] != '-' && !got_target) {
            snprintf(bdaddr_out, outsz, "%s", a);
            got_target = 1;
        } else {
            fprintf(stderr, "Unknown argument: %s\n", a);
            usage(argv[0]);
            return 0;
        }
    }
    return got_target;
}

int main(int argc, char *argv[]) {
    bdaddr_t bdaddr;
    int dev_id;
    struct hci_filter flt;
    uint8_t  role        = 0x00;
    uint16_t packettypes = HCI_DM1 | HCI_DM3 | HCI_DM5 |
                           HCI_DH1 | HCI_DH3 | HCI_DH5;
    pthread_t hci_read_thread;

    if (!parse_cli(argc, argv, g_target_bdaddr_str, sizeof(g_target_bdaddr_str))) {
        usage(argv[0]);
        return 1;
    }

    str2ba(g_target_bdaddr_str, &bdaddr);

    // Snapshot the run start time once. Every PDU emitted by this run gets
    // this same unix_time stamped in its std_optional_fields, and the 5-minute
    // aggregation window in btides_load_or_init() is measured from this value.
    g_run_unix_time = (int64_t)time(NULL);

    // BTIDES init
    init_btides_out_dir();
    char bdaddr_compact_str[16];
    bdaddr_compact(g_target_bdaddr_str, bdaddr_compact_str, sizeof(bdaddr_compact_str));
    char bdaddr_lower[32];
    bdaddr_lower_colon(g_target_bdaddr_str, bdaddr_lower, sizeof(bdaddr_lower));
    snprintf(g_btides_path, sizeof(g_btides_path),
             "%s/%s.btides", g_btides_out_dir, bdaddr_compact_str);
    btides_load_or_init(bdaddr_lower);

    atexit(on_exit_cleanup);
    signal(SIGTERM, on_signal);
    signal(SIGINT,  on_signal);

    // Pick the Realtek adapter (custom firmware) by manufacturer ID, unless
    // the user pinned a specific hciN via --hci. hci_get_route() may pick the
    // Pi's built-in radio, which is the wrong one for our VSC.
    if (g_hci_dev_id >= 0) {
        dev_id = g_hci_dev_id;
        fprintf(stderr, "[*] Using --hci-pinned dev_id=%d\n", dev_id);
    } else {
        dev_id = find_realtek_dev_id();
        if (dev_id < 0) {
            fprintf(stderr, "[!] No Realtek (manufacturer 93) adapter found; "
                            "falling back to hci_get_route. Check that the "
                            "DarkFirmware_real_i firmware is loaded.\n");
            dev_id = hci_get_route(&bdaddr);
        } else {
            fprintf(stderr, "[*] Auto-selected Realtek dev_id=%d\n", dev_id);
        }
    }
    if (dev_id < 0) { perror("HCI device not found"); return 1; }

    g_dev = hci_open_dev(dev_id);
    if (g_dev < 0) { perror("Failed to open HCI device"); return 1; }

    hci_filter_clear(&flt);
    hci_filter_set_ptype(HCI_EVENT_PKT, &flt);
    hci_filter_all_events(&flt);
    if (setsockopt(g_dev, SOL_HCI, HCI_FILTER, &flt, sizeof(flt)) < 0) {
        perror("HCI filter setup failed");
        return 1;
    }

    // Page timeout 15s — long enough for sleeping peers to wake, short
    // enough to leave headroom under the launcher's 15s SIGTERM. Was
    // originally 25s; we trade some max-target-budget for a guaranteed
    // graceful BTIDES flush.
    if (hci_create_connection(g_dev, &bdaddr, htobs(packettypes),
                              htobs(0x0000), role, &g_handle, 15000) < 0) {
        perror("Failed to create connection");
        return 1;
    }
    g_have_handle = 1;
    fprintf(stderr, "Connection handle: %d (0x%04x)\n", g_handle, g_handle);

    if (pthread_create(&hci_read_thread, NULL, threaded_hci_read, &g_dev) != 0) {
        perror("Failed to create HCI read thread");
        return 1;
    }

    run_state_machine(g_dev);

    pthread_cancel(hci_read_thread);
    pthread_join(hci_read_thread, NULL);

    write_btides_file();

    pthread_mutex_destroy(&g_lmp_opcodes_mutex);
    pthread_mutex_destroy(&g_lmp_ext_opcodes_mutex);
    pthread_mutex_destroy(&g_btides_mutex);

    return ((gAllRequiredResponses & RR_ALL_DONE) == RR_ALL_DONE) ? 0 : 1;
}
