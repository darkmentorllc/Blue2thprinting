########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

import TME.TME_glob
from TME.TME_helpers import *


########################################################################
# SIG-Base UUID alias detection / resolution helpers (used by
# get_uuid128_stats below). Per Core Spec Vol 3 Part B §2.5.1 any 16-
# or 32-bit assigned UUID has an equivalent 128-bit form constructed
# by combining it with the Bluetooth Base UUID
# `00000000-0000-1000-8000-00805F9B34FB`. A UUID128 ending in the last
# 12 bytes of that base is logically *the same UUID* as its short
# form; it should be resolved against the SIG assigned-numbers tables,
# not treated as an opaque custom 128-bit UUID.
########################################################################

# Last 12 bytes (24 hex chars) of the Bluetooth Base UUID, lowercase.
_SIG_BASE_TAIL_HEX = "00001000800000805f9b34fb"

# Priority-ordered list of SIG 16-bit lookup tables to consult. Each
# table is a dict[int, str] keyed by the integer UUID16 value (the
# YAML loader stores `uuid: 0xXXXX` as a Python int — see
# TME_import.import_bt_member_UUID16s_to_names() etc.). Member UUIDs
# (vendor IDs) are first because identifying the vendor is usually the
# most actionable result; everything else is tried in roughly
# decreasing usefulness order.
_SIG_UUID16_TABLES = [
    ("Member UUID (vendor)",   "bt_member_UUID16s_to_names"),
    ("Service Class",          "uuid16_service_names"),
    ("GATT Service",           "gatt_services_uuid16_names"),
    ("GATT Characteristic",    "gatt_characteristic_uuid16_names"),
    ("GATT Descriptor",        "gatt_descriptors_uuid16_names"),
    ("GATT Declaration",       "gatt_declarations_uuid16_names"),
    ("Protocol Identifier",    "uuid16_protocol_names"),
    ("Standards Organization", "uuid16_standards_organizations_names"),
]


def _sig_base_short_form(uuid128_no_dash):
    """If `uuid128_no_dash` (32 hex chars, lowercase, no dashes) is a
    SIG-Base alias, return its short form as a hex string — either 4
    chars (16-bit alias `0000XXXX-...`) or 8 chars (32-bit alias
    `XXXXXXXX-...`). Otherwise return None.
    """
    u = uuid128_no_dash.lower()
    if len(u) != 32 or not u.endswith(_SIG_BASE_TAIL_HEX):
        return None
    top8 = u[:8]
    if top8.startswith("0000"):
        return top8[4:]   # 16-bit form, 4 hex chars
    return top8           # 32-bit form, 8 hex chars


def _sig_uuid16_lookup(uuid16_hex):
    """Look `uuid16_hex` (4 hex chars) up across every SIG 16-bit
    assigned-numbers table loaded into TME_glob. Returns a
    "category: name" string on the first match (in priority order
    defined by _SIG_UUID16_TABLES), or None.
    """
    try:
        value = int(uuid16_hex, 16)
    except ValueError:
        return None
    for category, attr in _SIG_UUID16_TABLES:
        table = getattr(TME.TME_glob, attr, None)
        if table and value in table:
            return f"{category}: {table[value]}"
    return None


def _classify_uuid128_for_stats(uuid128_no_dash):
    """Return (annotation_string, classification) for one UUID128.

    classification is one of:
        "clues"        — found in the CLUES custom-UUID128 database.
        "sig_alias"    — SIG-Base alias resolved to a known 16-bit
                          assigned UUID across the SIG tables.
        "sig_alias_unknown" — SIG-Base alias, but the 16-bit form is
                          not in any loaded SIG table (e.g. SIG just
                          assigned it after the local public/ checkout
                          was last pulled). Still annotated so it's not
                          confused with a genuine custom UUID128.
        "unknown"      — no information available.

    The empty annotation is reserved for the "unknown" case; every
    classified case returns a non-empty annotation so users no longer
    see bare "(no known info)" lines for what are actually SIG aliases.
    """
    if uuid128_no_dash in TME.TME_glob.clues:
        entry = TME.TME_glob.clues[uuid128_no_dash]
        name = entry.get('UUID_name', "Unknown")
        return (f"Custom UUID128: company: {entry['company']}, name: {name}", "clues")

    short = _sig_base_short_form(uuid128_no_dash)
    if short is not None:
        sig_name = _sig_uuid16_lookup(short) if len(short) == 4 else None
        if sig_name:
            return (f"SIG-Base alias of 0x{short.upper()} — {sig_name}", "sig_alias")
        # SIG-Base alias but the short form isn't in any of our SIG tables.
        # Could be a 32-bit alias (no SIG tables for those yet), or a 16-bit
        # alias newer than our `public/` checkout. Either way, annotate so
        # it's not reported as a totally opaque custom UUID128.
        return (f"SIG-Base alias of 0x{short.upper()} (no SIG-table match)",
                "sig_alias_unknown")

    return ("", "unknown")

def get_uuid16_stats(arg):
    seen_btc_uuid16s_hash = {}
    seen_le_uuid16s_hash = {}

    ################################################
    # Get the data for BTC devices from the database
    ################################################

    eir_uuid16_query = "SELECT str_UUID16s FROM EIR_bdaddr_to_UUID16s"
    eir_uuid16_result = execute_query(eir_uuid16_query, ())
    if(len(eir_uuid16_result) != 0):
        company_uuid_count = 0
        for (str_UUID16s,) in eir_uuid16_result:
            uuid16s = str_UUID16s.split(',')
            for uuid16 in uuid16s:
                if(uuid16 in seen_btc_uuid16s_hash):
                    seen_btc_uuid16s_hash[uuid16] += 1
                else:
                    seen_btc_uuid16s_hash[uuid16] = 1

        qprint("----= BLUETOOTH CLASSIC RESULTS =----")
        qprint(f"{len(eir_uuid16_result)} rows of data found in DB:EIR_bdaddr_to_UUID16s")
        qprint(f"{len(seen_btc_uuid16s_hash)} unique UUID16s found")
        sorted_items = sorted(seen_btc_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid16 \t company")
        for item in sorted_items:
            (uuid16,count) = item
            try:
                decimal_uuid16 = int(uuid16,16)
            except ValueError:
                if(arg != "quiet"): qprint(f"Skipping '{uuid16}', it can't be converted to an integer")
                continue

            if(decimal_uuid16 in TME.TME_glob.bt_member_UUID16s_to_names.keys()):
                qprint(f"{count} \t {uuid16} \t {TME.TME_glob.bt_member_UUID16s_to_names[int(uuid16,16)]}")
                company_uuid_count += 1
        qprint(f"*** {company_uuid_count} UUID16s matched a company name ***")

    ################################################
    # Get the data for LE devices from the database.
    # Runs independently of the EIR / BTC results above — `bttest` (and any
    # DB built only from BetterGetter / Sniffle LE captures) has the EIR
    # tables empty but plenty of LE UUID rows, and previously this block
    # was nested inside the `if(len(eir_uuid16_result) != 0)` so it was
    # silently skipped for LE-only datasets.
    ################################################

    le_uuid16_query = "SELECT str_UUID16s FROM LE_bdaddr_to_UUID16s_list"
    le_uuid16_result = execute_query(le_uuid16_query, ())
    if(len(le_uuid16_result) != 0):
        company_uuid_count = 0
        for (str_UUID16s,) in le_uuid16_result:
            if(isinstance(str_UUID16s, str)):
                uuid16s = str_UUID16s.split(',')
                for uuid16 in uuid16s:
                    if(uuid16 in seen_le_uuid16s_hash):
                        seen_le_uuid16s_hash[uuid16] += 1
                    else:
                        seen_le_uuid16s_hash[uuid16] = 1

        qprint("")
        qprint("----= BLUETOOTH LOW ENERGY RESULTS =----")
        qprint(f"{len(le_uuid16_result)} rows of data found in DB:LE_bdaddr_to_UUID16s_list")
        qprint(f"{len(seen_le_uuid16s_hash)} unique UUID16s found")
        sorted_items = sorted(seen_le_uuid16s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid16 \t company")
        for item in sorted_items:
            (uuid16,count) = item
            try:
                decimal_uuid16 = int(uuid16,16)
            except ValueError:
                if(arg != "quiet"): qprint(f"Skipping '{uuid16}', it can't be converted to an integer")
                continue
            if(decimal_uuid16 in TME.TME_glob.bt_member_UUID16s_to_names.keys()):
                qprint(f"{count} \t {uuid16} \t {TME.TME_glob.bt_member_UUID16s_to_names[int(uuid16,16)]}")
                company_uuid_count += 1

        qprint(f"*** {company_uuid_count} UUID16s matched a company name ***")


def get_uuid128_stats(arg):
    seen_btc_uuid128s_hash = {}
    seen_le_uuid128s_hash = {}

    ################################################
    # Get the data for BTC devices from the database
    ################################################

    eir_uuid128_query = "SELECT str_UUID128s FROM EIR_bdaddr_to_UUID128s"
    eir_uuid128_result = execute_query(eir_uuid128_query, ())
    if(len(eir_uuid128_result) != 0):
        clues_count = 0
        sig_alias_resolved_count = 0
        sig_alias_unknown_count = 0
        for (str_UUID128s,) in eir_uuid128_result:
            if(str_UUID128s == ''):
                continue
            uuid128s = str_UUID128s.split(',')
            for uuid128 in uuid128s:
                if(uuid128 in seen_btc_uuid128s_hash):
                    seen_btc_uuid128s_hash[uuid128] += 1
                else:
                    seen_btc_uuid128s_hash[uuid128] = 1

        qprint("----= BLUETOOTH CLASSIC RESULTS =----")
        qprint(f"{len(eir_uuid128_result)} rows of data found in DB:EIR_bdaddr_to_UUID128s")
        qprint(f"{len(seen_btc_uuid128s_hash)} unique UUID128s found")
        sorted_items = sorted(seen_btc_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid128 {i4} known info")
        for item in sorted_items:
            (uuid128, count) = item
            known_info, classification = _classify_uuid128_for_stats(uuid128)
            if classification == "clues":
                clues_count += 1
            elif classification == "sig_alias":
                sig_alias_resolved_count += 1
            elif classification == "sig_alias_unknown":
                sig_alias_unknown_count += 1
            qprint(f"{count} \t {uuid128} \t {known_info}")

        qprint(f"*** {clues_count} UUID128s are in the CLUES database ***")
        qprint(f"*** {sig_alias_resolved_count} UUID128s are SIG-Base aliases resolved to an assigned 16-bit name ***")
        if sig_alias_unknown_count:
            qprint(f"*** {sig_alias_unknown_count} UUID128s are SIG-Base aliases with no SIG-table match (likely 32-bit alias or newer than the local public/ checkout) ***")

    ################################################
    # Get the data for LE devices from the database.
    # Runs independently of the EIR / BTC results above — `bttest` (and any
    # DB built only from BetterGetter / Sniffle LE captures) has the EIR
    # tables empty but plenty of LE UUID rows, and previously this block
    # was nested inside the `if(len(eir_uuid128_result) != 0)` so it was
    # silently skipped for LE-only datasets.
    ################################################

    le_uuid128_query = "SELECT str_UUID128s FROM LE_bdaddr_to_UUID128s_list"
    le_uuid128_result = execute_query(le_uuid128_query, ())
    if(len(le_uuid128_result) != 0):
        clues_count = 0
        sig_alias_resolved_count = 0
        sig_alias_unknown_count = 0
        for (str_UUID128s,) in le_uuid128_result:
            if(str_UUID128s == ''):
                continue
            if(isinstance(str_UUID128s, str)):
                uuid128s = str_UUID128s.split(',')
                for uuid128 in uuid128s:
                    if(uuid128 in seen_le_uuid128s_hash):
                        seen_le_uuid128s_hash[uuid128] += 1
                    else:
                        seen_le_uuid128s_hash[uuid128] = 1

        qprint("")
        qprint("----= BLUETOOTH LOW ENERGY RESULTS =----")
        qprint(f"{len(le_uuid128_result)} rows of data found in DB:LE_bdaddr_to_UUID128s_list")
        qprint(f"{len(seen_le_uuid128s_hash)} unique UUID128s found")
        sorted_items = sorted(seen_le_uuid128s_hash.items(), key=lambda item: item[1], reverse=True)
        qprint(f"count \t uuid128 {i4} known info")
        for item in sorted_items:
            (uuid128, count) = item
            known_info, classification = _classify_uuid128_for_stats(uuid128)
            if classification == "clues":
                clues_count += 1
            elif classification == "sig_alias":
                sig_alias_resolved_count += 1
            elif classification == "sig_alias_unknown":
                sig_alias_unknown_count += 1
            qprint(f"{count} \t {uuid128} \t {known_info}")

        qprint(f"*** {clues_count} UUID128s are in the CLUES database ***")
        qprint(f"*** {sig_alias_resolved_count} UUID128s are SIG-Base aliases resolved to an assigned 16-bit name ***")
        if sig_alias_unknown_count:
            qprint(f"*** {sig_alias_unknown_count} UUID128s are SIG-Base aliases with no SIG-table match (likely 32-bit alias or newer than the local public/ checkout) ***")
