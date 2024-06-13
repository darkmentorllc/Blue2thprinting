// SPDX-License-Identifier: GPL-2.0-or-later
/*
 *
 *  BlueZ - Bluetooth protocol stack for Linux
 *
 *  Copyright (C) 2010  Nokia Corporation
 *  Copyright (C) 2010  Marcel Holtmann <marcel@holtmann.org>
 *
 *
 */

#ifdef HAVE_CONFIG_H
#include <config.h>
#endif

#include <errno.h>
#include <stdlib.h>
#include <unistd.h>

#include <glib.h>

#include "lib/bluetooth.h"
#include "lib/hci.h"
#include "lib/hci_lib.h"
#include "lib/sdp.h"
#include "lib/uuid.h"

#include "src/shared/util.h"
#include "att.h"
#include "btio/btio.h"
#include "gattrib.h"
#include "gatt.h"
#include "gatttool.h"

//XENO: declarations, since I changed the order in which things are called
static gboolean primary(gpointer user_data);
static gboolean characteristics(gpointer user_data);
static gboolean characteristics_desc(gpointer user_data);
static void char_read_cb(guint8 status, const guint8 *pdu, guint16 plen, gpointer user_data);

static char * g_log_name = "/home/user/Blue2thprinting/Logs/GATTprint.log";
FILE * g_log_FILE;

static char *opt_src = NULL;
static char *opt_dst = NULL;
static char *opt_dst_type = NULL;
static char *opt_value = NULL;
static char *opt_sec_level = NULL;
static bt_uuid_t *opt_uuid = NULL;
static int opt_start = 0x0001;
static int opt_end = 0xffff;
static int opt_handle = -1;
static int opt_mtu = 0;
static int opt_psm = 0;
static gboolean opt_primary = FALSE;
static gboolean opt_characteristics = FALSE;
static gboolean opt_char_read = FALSE;
static gboolean opt_listen = FALSE;
static gboolean opt_char_desc = FALSE;
static GMainLoop *event_loop;
static gboolean got_error = FALSE;
static GSourceFunc operation = NULL;

struct characteristic_data {
	GAttrib *attrib;
	uint16_t start;
	uint16_t end;
};

//XENO:
static uint16_t g_max_handle = 0xFFFF; //XENO: Determines when the program is done enumerating
static gboolean g_proceed = FALSE;
// size-capped list of handles for characteristics to read
static uint16_t char_value_handles_to_read[512] = {0};
static int num_char_value_handles = 0;
GAttrib * g_attrib_copy = NULL;


static void connect_cb(GIOChannel *io, GError *err, gpointer user_data)
{
	GAttrib *attrib;
	uint16_t mtu;
	uint16_t cid;
	GError *gerr = NULL;

	if (err) {
		g_printerr("GATTPRINT:CONNECT: %s\n", err->message);
		got_error = TRUE;
		g_main_loop_quit(event_loop);
	}

	bt_io_get(io, &gerr, BT_IO_OPT_IMTU, &mtu,
				BT_IO_OPT_CID, &cid, BT_IO_OPT_INVALID);

	if (gerr) {
		g_printerr("Can't detect MTU, using default: %s",
								gerr->message);
		g_error_free(gerr);
		mtu = ATT_DEFAULT_LE_MTU;
	}

	if (cid == ATT_CID)
		mtu = ATT_DEFAULT_LE_MTU;

	attrib = g_attrib_new(io, mtu, false);

	//XENO: keep a copy of this, so we can call gatt_read_char() with it later
	g_attrib_copy = attrib;

	//XENO: Just do all the operations sequentially, that would normally be done by different CLI options
	primary(attrib);
	characteristics(attrib);
	characteristics_desc(attrib);
}

static void primary_all_cb(uint8_t status, GSList *services, void *user_data)
{
	GSList *l;

	if (status) {
		g_printerr("Discover all primary services failed: %s\n",
							att_ecode2str(status));
		return;
	}

	for (l = services; l; l = l->next) {
		struct gatt_primary *prim = l->data;
//		g_print("attr handle = 0x%04x, end grp handle = 0x%04x "
//			"uuid: %s\n", prim->range.start, prim->range.end, prim->uuid);
		g_print("\"GATTPRINT:SERVICE\",\"%s\",\"%s\",\"0x%04x\",\"0x%04x\",\"%s\"\n", opt_dst_type, opt_dst, prim->range.start, prim->range.end, prim->uuid);
		fprintf(g_log_FILE, "\"GATTPRINT:SERVICE\",\"%s\",\"%s\",\"0x%04x\",\"0x%04x\",\"%s\"\n", opt_dst_type, opt_dst, prim->range.start, prim->range.end, prim->uuid);
		fflush(g_log_FILE);
                g_max_handle = prim->range.end;
	}

}

//XENO: This is the function invoked by the --serviceX (formerly --primary) CLI arg
static gboolean primary(gpointer user_data)
{
	GAttrib *attrib = user_data;

	gatt_discover_primary(attrib, NULL, primary_all_cb, NULL);

	return FALSE;
}

static void char_discovered_cb(uint8_t status, GSList *characteristics, void *user_data)
{
	GSList *l;
	unsigned int last_handle=0;


	if (status) {
		g_printerr("Discover all characteristics failed: %s\n", att_ecode2str(status));
		return;
	}

	for (l = characteristics; l; l = l->next) {
		struct gatt_char *chars = l->data;

		last_handle = chars->value_handle;

/*
		g_print("handle = 0x%04x, char properties = 0x%02x, char value "
			"handle = 0x%04x, uuid = %s\n", chars->handle,
			chars->properties, chars->value_handle, chars->uuid);
*/
		g_print("\"GATTPRINT:CHARACTERISTIC\",\"%s\",\"%s\",\"0x%04x\",\"0x%02x\",\"0x%04x\",\"%s\"\n", opt_dst_type, opt_dst, chars->handle, chars->properties, chars->value_handle, chars->uuid);
		fprintf(g_log_FILE, "\"GATTPRINT:CHARACTERISTIC\",\"%s\",\"%s\",\"0x%04x\",\"0x%02x\",\"0x%04x\",\"%s\"\n", opt_dst_type, opt_dst, chars->handle, chars->properties, chars->value_handle, chars->uuid);
		fflush(g_log_FILE);
		if((chars->properties & 0x2) == 0x2){
	                g_print("Calling gatt_read_char() with handle %d\n", chars->value_handle);
			// XENO: Need to store the handle somewhere in a global so we can get it back later in the char_read_cb() callback
			char_value_handles_to_read[num_char_value_handles] = chars->value_handle;
	                gatt_read_char(g_attrib_copy, chars->value_handle, char_read_cb, &(char_value_handles_to_read[num_char_value_handles]));
			num_char_value_handles++;
		} else{
			g_print("Skipping handle %d because it's not readable\n", chars->value_handle);
		}
	}
	// Many devices return 0xffff as max handle in 'primary' and also keep connection after we finish service discovery.
	// This causes timeout in central_app_launcher - the script wrongfully marks the GATT printing as unsuccessful and tries again.
	// As a workaround we can adjust the g_max_handle to the last characteristic value handle just discovered.
	if (g_max_handle == 0xffff) {
//		g_print("ADJUSTING g_max_handle to: 0x%04x\n",last_handle);
		g_max_handle = last_handle;
	}

}

static gboolean characteristics(gpointer user_data)
{
	GAttrib *attrib = user_data;

	gatt_discover_char(attrib, opt_start, opt_end, opt_uuid, char_discovered_cb, NULL);

	return FALSE;
}

static void char_read_cb(guint8 status, const guint8 *pdu, guint16 plen, gpointer user_data)
{
	uint8_t value[plen];
	ssize_t vlen;
	int i;

	if (status != 0) {
		g_printerr("Characteristic value/descriptor read failed: %s\n", att_ecode2str(status));
		goto done;
	}

	vlen = dec_read_resp(pdu, plen, value, sizeof(value));
	if (vlen < 0) {
		g_printerr("Protocol error\n");
		goto done;
	}
	g_print("Characteristic value/descriptor: ");
	for (i = 0; i < vlen; i++)
		if(value[i] >= 32 && value[i] <= 126) g_print("%c", value[i]);
		else g_print("%02x ", value[i]);
	g_print("\n");

	//XENO: The "user_dataa" callback data has been filled in with the pointer to the handle that this was a read from
	g_print("\"GATTPRINT:CHAR_VALUE\",\"%s\",\"%s\",\"0x%04x\",\"", opt_dst_type, opt_dst, *(uint16_t *)user_data);
	fprintf(g_log_FILE, "\"GATTPRINT:CHAR_VALUE\",\"%s\",\"%s\",\"0x%04x\",\"", opt_dst_type, opt_dst, *(uint16_t *)user_data);
	for (i = 0; i < vlen; i++){
		g_print("%02x", value[i]);
		fprintf(g_log_FILE, "%02x", value[i]);
	}
	g_print("\"\n");
	fprintf(g_log_FILE, "\"\n");
	fflush(g_log_FILE);

done:
	return;
}

static gboolean characteristics_read(gpointer user_data)
{
	GAttrib *attrib = user_data;

	gatt_read_char(attrib, opt_handle, char_read_cb, attrib);

	return FALSE;
}

static void mainloop_quit(gpointer user_data)
{
	uint8_t *value = user_data;

	g_free(value);
	g_main_loop_quit(event_loop);
}

static void char_desc_cb(uint8_t status, GSList *descriptors, void *user_data)
{
	GSList *l;
	struct gatt_desc *desc;

//	g_print("char_desc_cb called\n"); //XENO: This is to check if this is called multiple times or not. Haven't seen it so far
	if (status) {
		g_printerr("Discover descriptors failed: %s\n", att_ecode2str(status));
		g_main_loop_quit(event_loop);
	}

	for (l = descriptors; l; l = l->next) {
		desc = l->data;

/*
		g_print("handle = 0x%04x, uuid = %s\n", desc->handle,
								desc->uuid);
*/
		g_print("\"GATTPRINT:DESCRIPTORS\",\"%s\",\"%s\",\"0x%04x\",\"%s\"\n", opt_dst_type, opt_dst, desc->handle, desc->uuid);
		fprintf(g_log_FILE, "\"GATTPRINT:DESCRIPTORS\",\"%s\",\"%s\",\"0x%04x\",\"%s\"\n", opt_dst_type, opt_dst, desc->handle, desc->uuid);
		fflush(g_log_FILE);
	}

	//XENO: Exit if the last handle was the max handle, and if there's no upcoming manual read request
	//XENO: There is a problem with this exit condition, because the "rnet" device sets the final range of the services to 0xffff, so this will never be true
	if (desc->handle == g_max_handle){
		g_main_loop_quit(event_loop);
	}

}

static gboolean characteristics_desc(gpointer user_data)
{
	GAttrib *attrib = user_data;

	gatt_discover_desc(attrib, opt_start, opt_end, NULL, char_desc_cb, NULL);

	return FALSE;
}

static gboolean parse_uuid(const char *key, const char *value,
				gpointer user_data, GError **error)
{
	if (!value)
		return FALSE;

	opt_uuid = g_try_malloc(sizeof(bt_uuid_t));
	if (opt_uuid == NULL)
		return FALSE;

	if (bt_string_to_uuid(opt_uuid, value) < 0)
		return FALSE;

	return TRUE;
}

static GOptionEntry char_rw_options[] = {
	{ "handle", 'a' , 0, G_OPTION_ARG_INT, &opt_handle,
		"Read/Write characteristic by handle(required)", "0x0001" },
	{ "value", 'n' , 0, G_OPTION_ARG_STRING, &opt_value,
		"Write characteristic value (required for write operation)",
		"0x0001" },
	{NULL},
};

static GOptionEntry gatt_options[] = {
	{ "servicesX", 0, 0, G_OPTION_ARG_NONE, &opt_primary,
		"Primary Service Discovery", NULL },
	{ "characteristics", 0, 0, G_OPTION_ARG_NONE, &opt_characteristics,
		"Characteristics Discovery", NULL },
	{ "char-desc", 0, 0, G_OPTION_ARG_NONE, &opt_char_desc,
		"Characteristics Descriptor Discovery", NULL },
	{ "char-read", 0, 0, G_OPTION_ARG_NONE, &opt_char_read,
		"Characteristics Value/Descriptor Read", NULL },
	{ NULL },
};

static GOptionEntry options[] = {
	{ "adapter", 'i', 0, G_OPTION_ARG_STRING, &opt_src,
		"Specify local adapter interface", "hciX" },
	{ "device", 'b', 0, G_OPTION_ARG_STRING, &opt_dst,
		"Specify remote Bluetooth address", "MAC" },
	{ "addr-type", 't', 0, G_OPTION_ARG_STRING, &opt_dst_type,
		"Set LE address type. Default: public", "[public | random]"},
	{ "mtu", 'm', 0, G_OPTION_ARG_INT, &opt_mtu,
		"Specify the MTU size", "MTU" },
	{ "psm", 'p', 0, G_OPTION_ARG_INT, &opt_psm,
		"Specify the PSM for GATT/ATT over BR/EDR", "PSM" },
	{ "sec-level", 'l', 0, G_OPTION_ARG_STRING, &opt_sec_level,
		"Set security level. Default: low", "[low | medium | high]"},
	{ NULL },
};

int main(int argc, char *argv[])
{
	GOptionContext *context;
	GOptionGroup *gatt_group, *params_group, *char_rw_group;
	GError *gerr = NULL;
	GIOChannel *chan;

	g_log_FILE = fopen(g_log_name, "a"); // Open file in append mode
	if (g_log_FILE == NULL) {
		printf("Failed to open the file.\n");
		return 1;
	}

	opt_dst_type = g_strdup("public");
	opt_sec_level = g_strdup("low");

	context = g_option_context_new(NULL);
	g_option_context_add_main_entries(context, options, NULL);

	/* GATT commands */
	gatt_group = g_option_group_new("gatt", "GATT commands",
					"Show all GATT commands", NULL, NULL);
	g_option_context_add_group(context, gatt_group);
	g_option_group_add_entries(gatt_group, gatt_options);

	/* Characteristics value/descriptor read/write arguments */
	char_rw_group = g_option_group_new("char-read-write",
		"Characteristics Value/Descriptor Read/Write arguments",
		"Show all Characteristics Value/Descriptor Read/Write "
		"arguments",
		NULL, NULL);
	g_option_context_add_group(context, char_rw_group);
	g_option_group_add_entries(char_rw_group, char_rw_options);

	if (!g_option_context_parse(context, &argc, &argv, &gerr)) {
		g_printerr("%s\n", gerr->message);
		g_clear_error(&gerr);
	}

	if (opt_dst == NULL) {
		g_print("Remote Bluetooth address required\n");
		got_error = TRUE;
		goto done;
	}

	chan = gatt_connect(opt_src, opt_dst, opt_dst_type, opt_sec_level,
					opt_psm, opt_mtu, connect_cb, &gerr);
	if (chan == NULL) {
		g_printerr("%s\n", gerr->message);
		g_clear_error(&gerr);
		got_error = TRUE;
		goto done;
	}

	event_loop = g_main_loop_new(NULL, FALSE);

	g_main_loop_run(event_loop);

	g_main_loop_unref(event_loop);

done:
	g_option_context_free(context);
	g_free(opt_src);
	g_free(opt_dst);
	g_free(opt_uuid);
	g_free(opt_sec_level);

	if (got_error)
		exit(EXIT_FAILURE);
	else
		exit(EXIT_SUCCESS);
}
