########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

# Post-processing filter for the in-memory BTIDES JSON aggregate.
# Applies the --NOT-* CLI exclusions by inspecting the BTIDES data itself
# (no local Bluetooth DB queries). Used by WIGLE_to_BTIDES.py and any other
# tool that wants to scrub aggregated BTIDES data before write/upload.

import re
import TME.TME_glob
from TME.TME_helpers import qprint

# AdvData type values (mirror values used in TME_BTIDES_AdvData.py / BT Core spec).
_TYPE_UUID16_LIST_INCOMPLETE = 2
_TYPE_UUID16_LIST_COMPLETE = 3
_TYPE_UUID32_LIST_INCOMPLETE = 4
_TYPE_UUID32_LIST_COMPLETE = 5
_TYPE_UUID128_LIST_INCOMPLETE = 6
_TYPE_UUID128_LIST_COMPLETE = 7
_TYPE_INCOMPLETE_NAME = 8
_TYPE_COMPLETE_NAME = 9
_TYPE_MSD = 255

# HCI event_code for HCI_Remote_Name_Request_Complete.
_HCI_REMOTE_NAME_COMPLETE = 7

# GATT Device Name characteristic UUID.
_GATT_DEVICE_NAME_UUID = "2a00"


def _decode_hex_name(hex_str):
    if not hex_str:
        return ""
    try:
        return bytes.fromhex(hex_str).decode("utf-8", "ignore")
    except (ValueError, TypeError):
        return ""


def _entry_names(entry):
    for hci in entry.get("HCIArray", []) or []:
        if hci.get("event_code") == _HCI_REMOTE_NAME_COMPLETE:
            name = hci.get("utf8_name") or _decode_hex_name(hci.get("remote_name_hex_str"))
            if name:
                yield name

    for adv in entry.get("AdvChanArray", []) or []:
        for elem in adv.get("AdvDataArray", []) or []:
            if elem.get("type") in (_TYPE_INCOMPLETE_NAME, _TYPE_COMPLETE_NAME):
                name = elem.get("utf8_name") or _decode_hex_name(elem.get("name_hex_str"))
                if name:
                    yield name

    for service in entry.get("GATTArray", []) or []:
        for char in service.get("characteristics", []) or []:
            if str(char.get("value_uuid", "")).lower() == _GATT_DEVICE_NAME_UUID:
                value = char.get("value")
                if isinstance(value, str) and value:
                    yield _decode_hex_name(value) or value


def _entry_company_names(entry):
    cid_to_names = TME.TME_glob.bt_CID_to_names
    for adv in entry.get("AdvChanArray", []) or []:
        for elem in adv.get("AdvDataArray", []) or []:
            if elem.get("type") != _TYPE_MSD:
                continue
            cid_hex = elem.get("company_id_hex_str")
            if not cid_hex:
                continue
            try:
                cid_int = int(cid_hex, 16)
            except ValueError:
                continue
            name = cid_to_names.get(cid_int)
            if name:
                yield name


_UUID_LIST_KEYS = (
    (_TYPE_UUID16_LIST_INCOMPLETE, "UUID16List"),
    (_TYPE_UUID16_LIST_COMPLETE, "UUID16List"),
    (_TYPE_UUID32_LIST_INCOMPLETE, "UUID32List"),
    (_TYPE_UUID32_LIST_COMPLETE, "UUID32List"),
    (_TYPE_UUID128_LIST_INCOMPLETE, "UUID128List"),
    (_TYPE_UUID128_LIST_COMPLETE, "UUID128List"),
)


def _entry_uuids(entry):
    for adv in entry.get("AdvChanArray", []) or []:
        for elem in adv.get("AdvDataArray", []) or []:
            t = elem.get("type")
            for elem_type, list_key in _UUID_LIST_KEYS:
                if t == elem_type:
                    for u in elem.get(list_key, []) or []:
                        if u:
                            yield str(u)
                    break

    for service in entry.get("GATTArray", []) or []:
        if service.get("UUID"):
            yield str(service["UUID"])
        for char in service.get("characteristics", []) or []:
            if char.get("value_uuid"):
                yield str(char["value_uuid"])


def filter_BTIDES_by_NOT_args(NOT_bdaddr=None, NOT_bdaddr_regex=None,
                              NOT_name_regex=None, NOT_company_regex=None,
                              NOT_UUID_regex=None):
    """Drop entries from TME.TME_glob.BTIDES_JSON matching any --NOT-* criterion.

    Mutates the global list in place. Returns the number of entries removed.
    All regex matches are case-insensitive substring (re.search). Only
    SingleBDADDR entries (those with a top-level "bdaddr") are considered;
    DualBDADDR (CONNECT_IND-keyed) entries are left untouched.
    """
    if not (NOT_bdaddr or NOT_bdaddr_regex or NOT_name_regex
            or NOT_company_regex or NOT_UUID_regex):
        return 0

    not_bdaddr_set = {b.lower() for b in (NOT_bdaddr or [])}
    bdaddr_patterns = [re.compile(r, re.IGNORECASE) for r in (NOT_bdaddr_regex or [])]
    name_patterns = [re.compile(r, re.IGNORECASE) for r in (NOT_name_regex or [])]
    company_patterns = [re.compile(r, re.IGNORECASE) for r in (NOT_company_regex or [])]
    uuid_patterns = [re.compile(r, re.IGNORECASE) for r in (NOT_UUID_regex or [])]

    def _should_remove(entry):
        bdaddr = entry.get("bdaddr")
        if not bdaddr:
            return False
        if bdaddr.lower() in not_bdaddr_set:
            return True
        for pat in bdaddr_patterns:
            if pat.search(bdaddr):
                return True
        if name_patterns:
            for name in _entry_names(entry):
                for pat in name_patterns:
                    if pat.search(name):
                        return True
        if company_patterns:
            for cname in _entry_company_names(entry):
                for pat in company_patterns:
                    if pat.search(cname):
                        return True
        if uuid_patterns:
            for u in _entry_uuids(entry):
                for pat in uuid_patterns:
                    if pat.search(u):
                        return True
        return False

    before = len(TME.TME_glob.BTIDES_JSON)
    TME.TME_glob.BTIDES_JSON[:] = [
        e for e in TME.TME_glob.BTIDES_JSON if not _should_remove(e)
    ]
    removed = before - len(TME.TME_glob.BTIDES_JSON)
    if removed:
        # Rebuild the SingleBDADDR lookup index from the surviving entries so
        # subsequent lookups remain O(1) and don't return pointers to removed items.
        from TME.TME_BTIDES_base import rebuild_SingleBDADDR_index
        rebuild_SingleBDADDR_index()
        plural = "y" if removed == 1 else "ies"
        qprint(f"--NOT-* post-processing removed {removed} BTIDES entr{plural}.")
    return removed
