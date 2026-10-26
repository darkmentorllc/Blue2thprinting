########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

import re
# import TME.TME_glob
from TME.TME_helpers import *
from TME.TME_glob import i1, i2, i3, i4, i5 # Required for terser usage within print statements

########################################
# Lookup helpers
########################################

# Returns True if there is any LL_VERSION_IND info for this BDADDR, else
# False. LL_VERSION_IND's unique index is (bdaddr_random, bdaddr, ...), so
# the shared helper forces an indexed lookup by binding bdaddr_random when
# supplied or probing both 0 and 1 when not.
def device_has_LL_VERSION_IND_info(bdaddr, bdaddr_random):
    return device_row_exists_by_bdaddr_random(
        "LL_VERSION_IND", bdaddr, bdaddr_random)


# Returns True if there is any LMP_VERSION_RES info for this BDADDR, else
# False. LMP_VERSION_RES is BT Classic-only (no bdaddr_random column) and
# its unique index has `bdaddr` as the leftmost-prefix column, so a plain
# `WHERE bdaddr = %s` is already indexed.
def device_has_LMP_VERSION_RES_info(bdaddr):
    return device_row_exists_by_bdaddr("LMP_VERSION_RES", bdaddr)

def get_bdaddrs_by_name_regex(nameregex, bdaddr_random, max_candidates=None,
                              candidates=None):
    """Stream name rows and retain only the addresses a caller can use."""
    vprint(nameregex)
    name_pattern = re.compile(nameregex)
    bdaddr_hash = {}  # preserve first-seen order while de-duplicating
    candidate_set = set(candidates) if candidates is not None else None
    if candidate_set is not None:
        max_candidates = (len(candidate_set) if max_candidates is None
                          else min(max_candidates, len(candidate_set)))
    if max_candidates is not None and max_candidates <= 0:
        return bdaddr_hash.keys()

    def collect(query, values, label, hex_encoded):
        matched = 0
        rows = execute_query_rows(query, values)
        try:
            for bdaddr, raw_name in rows:
                if candidate_set is not None and bdaddr not in candidate_set:
                    continue
                try:
                    name = (bytes.fromhex(raw_name).decode('utf-8', 'ignore')
                            if hex_encoded else bytes(raw_name).decode('utf-8', 'ignore'))
                except (TypeError, ValueError):
                    continue  # A malformed name should not abort the search.
                if name_pattern.search(name):
                    bdaddr_hash[bdaddr] = 1
                    matched += 1
                    if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
                        break
        finally:
            close = getattr(rows, 'close', None)
            if close is not None:
                close()
        qprint(f"get_bdaddrs_by_name_regex: {matched} matching names in DB:{label}")
        return max_candidates is not None and len(bdaddr_hash) >= max_candidates

    if collect("SELECT bdaddr, name_hex_str FROM EIR_bdaddr_to_name", (),
               "EIR_bdaddr_to_name", True):
        return bdaddr_hash.keys()
    if collect("SELECT bdaddr, name_hex_str FROM HCI_bdaddr_to_name", (),
               "HCI_bdaddr_to_name", True):
        return bdaddr_hash.keys()
    if bdaddr_random is not None:
        le_query = "SELECT bdaddr, name_hex_str FROM LE_bdaddr_to_name WHERE bdaddr_random = %s"
        le_values = (bdaddr_random,)
    else:
        le_query = "SELECT bdaddr, name_hex_str FROM LE_bdaddr_to_name"
        le_values = ()
    if collect(le_query, le_values, "LE_bdaddr_to_name", True):
        return bdaddr_hash.keys()

    # Device Name characteristic (0x2a00). Match the address type on both
    # sides of the join so a reused handle cannot borrow another observation.
    chars_query = (
        "SELECT cv.bdaddr, cv.byte_values FROM GATT_characteristics_values AS cv "
        "JOIN GATT_characteristics AS c ON cv.char_value_handle = c.char_value_handle "
        "AND cv.bdaddr = c.bdaddr AND cv.bdaddr_random = c.bdaddr_random "
        "WHERE c.UUID = '2a00'"
    )
    values = ()
    if bdaddr_random is not None:
        chars_query += " AND c.bdaddr_random = %s"
        values = (bdaddr_random,)
    collect(chars_query, values, "GATT_characteristics_values", False)
    vprint(f"get_bdaddrs_by_name_regex: bdaddr_hash (len = {len(bdaddr_hash)}) = {bdaddr_hash}")
    return bdaddr_hash.keys()

# Keep this table set aligned with the device observations searched by the
# original BDADDR regex UNION.  Separate queries prevent MariaDB from
# materializing and de-duplicating all 52 tables in one large temp table.
_BDADDR_REGEX_LE_TABLES = (
    'LE_bdaddr_to_3d_info',
    'LE_bdaddr_to_appearance',
    'LE_bdaddr_to_CoD',
    'LE_bdaddr_to_connect_interval',
    'LE_bdaddr_to_flags',
    'LE_bdaddr_to_MSD',
    'LE_bdaddr_to_name',
    'LE_bdaddr_to_other_le_bdaddr',
    'LE_bdaddr_to_public_target_bdaddr',
    'LE_bdaddr_to_random_target_bdaddr',
    'LE_bdaddr_to_role',
    'LE_bdaddr_to_tx_power',
    'LE_bdaddr_to_URI',
    'LE_bdaddr_to_UUID128_service_data',
    'LE_bdaddr_to_UUID128_service_solicit',
    'LE_bdaddr_to_UUID128s_list',
    'LE_bdaddr_to_UUID32_service_data',
    'LE_bdaddr_to_UUID32_service_solicit',
    'LE_bdaddr_to_UUID32s_list',
    'LE_bdaddr_to_UUID16_service_data',
    'LE_bdaddr_to_UUID16_service_solicit',
    'LE_bdaddr_to_UUID16s_list',
    'LL_FEATUREs',
    'LL_LENGTHs',
    'LL_PHYs',
    'LL_PINGs',
    'LL_UNKNOWN_RSP',
    'LL_VERSION_IND',
    'GATT_attribute_handles',
    'GATT_characteristic_descriptor_values',
    'GATT_characteristics',
    'GATT_characteristics_values',
    'GATT_services',
)
_BDADDR_REGEX_CLASSIC_TABLES = (
    'EIR_bdaddr_to_3d_info',
    'EIR_bdaddr_to_CoD',
    'EIR_bdaddr_to_DevID',
    'EIR_bdaddr_to_flags',
    'EIR_bdaddr_to_MSD',
    'EIR_bdaddr_to_name',
    'EIR_bdaddr_to_PSRM',
    'EIR_bdaddr_to_tx_power',
    'EIR_bdaddr_to_URI',
    'EIR_bdaddr_to_UUID128s',
    'EIR_bdaddr_to_UUID16s',
    'EIR_bdaddr_to_UUID32s',
    'LMP_FEATURES_RES',
    'LMP_FEATURES_RES_EXT',
    'LMP_NAME_RES_defragmented',
    'LMP_VERSION_RES',
    'HCI_bdaddr_to_name',
    'SDP_Common',
    'SDP_ERROR_RSP',
)
_OUI_SEARCH_TABLES = _BDADDR_REGEX_LE_TABLES + tuple(
    table for table in _BDADDR_REGEX_CLASSIC_TABLES
    if table not in ('SDP_Common', 'SDP_ERROR_RSP'))
_BDADDR_REGEX_REQUIRED_ONLY_TABLES = {
    'SMP_Pairing_Req_Res': True,
    'bdaddr_to_GPS': False,
}


def get_bdaddrs_by_bdaddr_regex(bdaddrregex, bdaddr_random, source_tables=None,
                                max_candidates=None):
    # Translate bare glob '*' to regex '.*' so users can pass '*' to mean "match all".
    bdaddrregex = re.sub(r'(?<!\.)[\*]', '.*', bdaddrregex)
    vprint(bdaddrregex)
    bdaddr_hash = {}  # preserve first-seen order while de-duplicating
    le_tables = _BDADDR_REGEX_LE_TABLES
    classic_tables = _BDADDR_REGEX_CLASSIC_TABLES
    if source_tables is not None:
        # Only callers inside TME select source tables.  This also ensures a
        # user-supplied value can never be interpolated as a SQL identifier.
        selected = set(source_tables)
        unknown = selected.difference(
            le_tables + classic_tables + tuple(_BDADDR_REGEX_REQUIRED_ONLY_TABLES))
        if unknown:
            raise ValueError(f"Unknown BDADDR regex source table(s): {unknown}")
        le_tables = tuple(table for table in le_tables if table in selected)
        classic_tables = tuple(table for table in classic_tables if table in selected)
        for table in _BDADDR_REGEX_REQUIRED_ONLY_TABLES:
            if table in selected:
                if _BDADDR_REGEX_REQUIRED_ONLY_TABLES[table]:
                    le_tables += (table,)
                else:
                    classic_tables += (table,)

    # A SELECT per table pushes REGEXP before de-duplication.  DISTINCT and
    # LIMIT keep each SQL result bounded; fetchmany keeps client buffering
    # bounded even when the caller needs every match.
    address_expr = "CONVERT(bdaddr USING utf8mb4) COLLATE utf8mb4_unicode_ci"
    for table in le_tables + classic_tables:
        if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
            break
        values = (bdaddrregex,)
        where = f"{address_expr} REGEXP %s"
        if table in le_tables and bdaddr_random is not None:
            where = f"bdaddr_random = %s AND {where}"
            values = (bdaddr_random, bdaddrregex)
        if table == 'SMP_Pairing_Req_Res':
            where += " AND auth_req & 8 = 0"
        if source_tables is not None and table == 'GATT_characteristics_values':
            where += " AND operation = %s AND OCTET_LENGTH(byte_values) > 0"
            values += (11,)  # ATT_READ_RSP: a read value, not an ATT error.
        query = f"SELECT DISTINCT {address_expr} AS bdaddr FROM {table} WHERE {where}"
        if max_candidates is not None:
            query += " LIMIT %s"
            values += (max_candidates,)
        for (bdaddr,) in execute_query_rows(query, values):
            if max_candidates is None or len(bdaddr_hash) < max_candidates:
                bdaddr_hash[bdaddr] = 1

    qprint(f"get_bdaddrs_by_bdaddr_regex: {len(bdaddr_hash)} results found across all tables")
    vprint(f"get_bdaddrs_by_bdaddr_regex: bdaddr_hash = {bdaddr_hash}")
    return bdaddr_hash.keys()

def get_bdaddrs_by_company_regex(companyregex, bdaddr_random, max_candidates=None):
    global bt_CID_to_names
    global bt_member_UUID16s_to_names
    companyregex = re.sub(r'(?<!\.)[\*]', '.*', companyregex)
    qprint(f"Your given regex was {companyregex}")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddr_prefixes = {}
    bdaddrs = []
    device_bt_cids_to_names = {}
    device_uuid16s_to_names = {}
    pattern = re.compile(companyregex)

    # For configurability if you know there's a false positive happening when swapping
    # NOTE: So far I've found it to have more benefits than drawbacks, so it's enabled by default
    try_byte_swapped_bt_cid = True

    # For debugging:
    enable_bt_cid_lookup = True
    enable_UUID16_lookup = True
    enable_IEEE_OUI_lookup = True
    enable_CLUES_lookup = True

    def collect(query, values):
        """Add bounded SQL matches without materializing an entire result."""
        if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
            return 0
        if max_candidates is not None:
            query += " LIMIT %s"
            values += (max_candidates,)
        added = 0
        for (bdaddr,) in execute_query_rows(query, values):
            if bdaddr not in bdaddr_hash and (
                    max_candidates is None or len(bdaddr_hash) < max_candidates):
                bdaddr_hash[bdaddr] = 1
                added += 1
        return added

    if enable_bt_cid_lookup:
        # A company may have one BT Company ID. LL/LMP version records use
        # the assigned ID, while MSD can contain either byte order.
        for key, value in TME.TME_glob.bt_CID_to_names.items():
            if re.search(pattern, value):
                device_bt_cids_to_names[key] = value
        for key in device_bt_cids_to_names:
            if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
                break
            collect("SELECT DISTINCT bdaddr FROM LMP_VERSION_RES "
                    "WHERE device_BT_CID = %s", (key,))
            if bdaddr_random is None:
                collect("SELECT DISTINCT bdaddr FROM LL_VERSION_IND "
                        "WHERE device_BT_CID = %s", (key,))
            else:
                collect("SELECT DISTINCT bdaddr FROM LL_VERSION_IND "
                        "WHERE device_BT_CID = %s AND bdaddr_random = %s",
                        (key, bdaddr_random))
            swapped = ((key & 0xff) << 8) | ((key >> 8) & 0xff)
            cid_values = (key, swapped) if try_byte_swapped_bt_cid else (key,)
            placeholders = ','.join(['%s'] * len(cid_values))
            for table, uses_random in (('LE_bdaddr_to_MSD', True),
                                       ('EIR_bdaddr_to_MSD', False)):
                where = f'device_BT_CID IN ({placeholders})'
                values = cid_values
                if uses_random and bdaddr_random is not None:
                    where += ' AND bdaddr_random = %s'
                    values += (bdaddr_random,)
                collect(f'SELECT DISTINCT bdaddr FROM {table} WHERE {where}', values)

    if enable_UUID16_lookup:
        # Assigned company UUID16s can appear in classic or LE service lists.
        for key, value in TME.TME_glob.bt_member_UUID16s_to_names.items():
            if re.search(pattern, value):
                device_uuid16s_to_names[key] = value
        for key in device_uuid16s_to_names:
            if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
                break
            uuid_pattern = f'0x{key:04x}'
            collect("SELECT DISTINCT bdaddr FROM EIR_bdaddr_to_UUID16s "
                    "WHERE str_UUID16s REGEXP %s", (uuid_pattern,))
            if bdaddr_random is None:
                collect("SELECT DISTINCT bdaddr FROM LE_bdaddr_to_UUID16s_list "
                        "WHERE str_UUID16s REGEXP %s", (uuid_pattern,))
            else:
                collect("SELECT DISTINCT bdaddr FROM LE_bdaddr_to_UUID16s_list "
                        "WHERE str_UUID16s REGEXP %s AND bdaddr_random = %s",
                        (uuid_pattern, bdaddr_random))

    if(enable_IEEE_OUI_lookup):
        ############################################
        # MATCH REGEX TO IEEE OUIS (BDADDR PREFIXES)
        ############################################
        # Query for IEEE_bdaddr_to_company table
        values = (companyregex,)
        oui_query = "SELECT bdaddr, company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP %s"
        oui_result = execute_query(oui_query, values)
        for oui, company_name in oui_result:
            bdaddr_prefixes[oui] = company_name
            qprint(f"{companyregex} matched company name {company_name}, with OUI {oui}")

        #qprint(f"bdaddr_prefixes = {bdaddr_prefixes}")
        qprint(f"{len(oui_result)} results found in IEEE_bdaddr_to_company")

        #############################################
        # LOOKUP BDADDRS BY OUIS (ACROSS ALL TABLES!)
        #############################################

        # Search each indexed address column once for all matching OUIs.
        # The former UNION ALL materialized every observation row per OUI,
        # then applied LIKE outside the temporary table. Thirteen Telink
        # prefixes made that path exceed the production query timeout.
        # IEEE OUIs identify public addresses only. A random BLE address can
        # coincidentally start with a company's registered prefix, as
        # 4c:a0:d4:4a:ed:45 does for Telink.
        if bdaddr_prefixes and bdaddr_random != 1:
            prefixes = tuple(prefix + '%' for prefix in bdaddr_prefixes)
            prefix_where = '(' + ' OR '.join(['bdaddr LIKE %s'] * len(prefixes)) + ')'
            for table in _OUI_SEARCH_TABLES:
                if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
                    break
                where = prefix_where
                values = prefixes
                if table in _BDADDR_REGEX_LE_TABLES:
                    where += ' AND bdaddr_random = 0'
                found = collect(f'SELECT DISTINCT bdaddr FROM {table} WHERE {where}', values)
                qprint(f'{found} new BDADDRs with matching OUI in {table}')

    if(enable_CLUES_lookup and
            (max_candidates is None or len(bdaddr_hash) < max_candidates)):
        # CLUES entries are UUID128 values. The old loop called the generic
        # 13-table UUID regex search once per matching UUID, scanning every
        # table hundreds of times for common company names. Batch UUID128
        # matches by storage format and query each relevant table once.
        compact_uuids = set()
        for clue in TME.TME_glob.clues.values():
            if re.search(pattern, clue["company"]):
                compact = clue["UUID"].replace('-', '').lower()
                if re.fullmatch(r'[0-9a-f]{32}', compact):
                    compact_uuids.add(compact)
        if compact_uuids:
            compact_uuids = sorted(compact_uuids)
            dashed_uuids = tuple(
                f'{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}'
                for u in compact_uuids)
            uuid_regex = '|'.join(compact_uuids)
            uuid128_tables = (
                ('EIR_bdaddr_to_UUID128s', 'str_UUID128s', False),
                ('LE_bdaddr_to_UUID128s_list', 'str_UUID128s', True),
                ('LE_bdaddr_to_UUID128_service_solicit', 'str_UUID128s', True),
                ('LE_bdaddr_to_UUID128_service_data', 'UUID128_hex_str', True),
            )
            for table, column, uses_random in uuid128_tables:
                if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
                    break
                where = f'{column} REGEXP %s'
                values = (uuid_regex,)
                if uses_random and bdaddr_random is not None:
                    where += ' AND bdaddr_random = %s'
                    values += (bdaddr_random,)
                query = f'SELECT DISTINCT bdaddr FROM {table} WHERE {where}'
                if max_candidates is not None:
                    query += ' LIMIT %s'
                    values += (max_candidates,)
                for (bdaddr,) in execute_query_rows(query, values):
                    if max_candidates is None or len(bdaddr_hash) < max_candidates:
                        bdaddr_hash[bdaddr] = 1

            gatt_tables = ('GATT_services', 'GATT_characteristics',
                           'GATT_attribute_handles')
            uuid_placeholders = ','.join(['%s'] * len(dashed_uuids))
            for table in gatt_tables:
                if max_candidates is not None and len(bdaddr_hash) >= max_candidates:
                    break
                where = f'UUID IN ({uuid_placeholders})'
                values = dashed_uuids
                if bdaddr_random is not None:
                    where += ' AND bdaddr_random = %s'
                    values += (bdaddr_random,)
                query = f'SELECT DISTINCT bdaddr FROM {table} WHERE {where}'
                if max_candidates is not None:
                    query += ' LIMIT %s'
                    values += (max_candidates,)
                for (bdaddr,) in execute_query_rows(query, values):
                    if max_candidates is None or len(bdaddr_hash) < max_candidates:
                        bdaddr_hash[bdaddr] = 1
            qprint(f'{len(compact_uuids)} CLUES UUID128s checked in batches; '
                   f'{len(bdaddr_hash)} BDADDRs matched overall')

# TODO! Add the capability to search within the read values from GATT "Manufacturer Name" characteristics (will require interpreting as string within MySQL)
#    if(enable_GATT_manufacturer_lookup):

    return bdaddr_hash.keys()


# Target-scoped variant of get_bdaddrs_by_company_regex used by --NOT-company-regex.
# Returns the subset of `candidates` whose company matches `companyregex`.
# Avoids the 33-table UNION ALL per OUI prefix that makes the unscoped function
# painfully slow for regexes like "Apple" (see issue #11).
def get_candidate_bdaddrs_matching_company_regex(companyregex, bdaddr_random, candidates):
    if not candidates:
        return set()

    qprint(f"get_candidate_bdaddrs_matching_company_regex: regex={companyregex}, {len(candidates)} candidates")
    pattern = re.compile(companyregex)
    candidate_set = set(candidates)
    remaining = set(candidate_set)
    matched = set()
    try_byte_swapped_bt_cid = True

    ############################################
    # IEEE OUI path (the hot path for "Apple").
    # Pull matching OUIs into memory once, then prefix-match candidates locally.
    ############################################
    values = (companyregex,)
    oui_query = "SELECT bdaddr, company_name FROM IEEE_bdaddr_to_company WHERE company_name REGEXP %s"
    oui_result = execute_query(oui_query, values)
    matching_ouis = {oui.lower() for (oui, _company_name) in oui_result}
    qprint(f"{i1}{len(matching_ouis)} OUIs matched in IEEE_bdaddr_to_company")
    if matching_ouis and bdaddr_random != 1:
        # Check the candidate's stored address type before treating its
        # prefix as an IEEE OUI. Prefix matching alone misclassifies random
        # BLE addresses and can incorrectly exclude them from a NOT filter.
        for table in _OUI_SEARCH_TABLES:
            prefixed = sorted(bdaddr for bdaddr in remaining
                              if bdaddr[:8].lower() in matching_ouis)
            if not prefixed:
                break
            placeholders = ','.join(['%s'] * len(prefixed))
            query = (f'SELECT DISTINCT bdaddr FROM {table} '
                     f'WHERE bdaddr IN ({placeholders})')
            if table in _BDADDR_REGEX_LE_TABLES:
                query += ' AND bdaddr_random = 0'
            for (bdaddr,) in execute_query_rows(query, tuple(prefixed)):
                matched.add(bdaddr)
                remaining.discard(bdaddr)

    ############################################
    # BT Company ID path — restrict queries to the remaining candidate set.
    ############################################
    if remaining:
        matching_cids = {
            key for key, value in TME.TME_glob.bt_CID_to_names.items()
            if re.search(pattern, value)
        }
        if matching_cids:
            if try_byte_swapped_bt_cid:
                swapped = {((k & 0xFF) << 8) | ((k & 0xFF00) >> 8) for k in matching_cids}
                msd_cids = matching_cids | swapped
            else:
                msd_cids = matching_cids

            def _run_cid_query(table, cids, random_filtered):
                if not remaining or not cids:
                    return
                bdaddr_list = list(remaining)
                cid_list = list(cids)
                bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))
                cid_ph = ",".join(["%s"] * len(cid_list))
                if random_filtered and bdaddr_random is not None:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND bdaddr_random = %s "
                             f"AND device_BT_CID IN ({cid_ph})")
                    vals = tuple(bdaddr_list) + (bdaddr_random,) + tuple(cid_list)
                else:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND device_BT_CID IN ({cid_ph})")
                    vals = tuple(bdaddr_list) + tuple(cid_list)
                for (bdaddr,) in execute_query(query, vals):
                    matched.add(bdaddr)
                    remaining.discard(bdaddr)

            _run_cid_query("LMP_VERSION_RES", matching_cids, random_filtered=False)
            _run_cid_query("LL_VERSION_IND", matching_cids, random_filtered=True)
            _run_cid_query("LE_bdaddr_to_MSD", msd_cids, random_filtered=True)
            _run_cid_query("EIR_bdaddr_to_MSD", msd_cids, random_filtered=False)

    ############################################
    # UUID16 path — restrict queries to the remaining candidate set.
    ############################################
    if remaining:
        matching_uuid16s = {
            key for key, value in TME.TME_glob.bt_member_UUID16s_to_names.items()
            if re.search(pattern, value)
        }
        if matching_uuid16s:
            uuid_pattern = "|".join(f"0x{k:04x}" for k in matching_uuid16s)
            bdaddr_list = list(remaining)
            bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))

            eir_query = (f"SELECT DISTINCT bdaddr FROM EIR_bdaddr_to_UUID16s "
                         f"WHERE bdaddr IN ({bdaddr_ph}) AND str_UUID16s REGEXP %s")
            for (bdaddr,) in execute_query(eir_query, tuple(bdaddr_list) + (uuid_pattern,)):
                matched.add(bdaddr)
                remaining.discard(bdaddr)

            if remaining:
                bdaddr_list = list(remaining)
                bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))
                if bdaddr_random is not None:
                    le_query = (f"SELECT DISTINCT bdaddr FROM LE_bdaddr_to_UUID16s_list "
                                f"WHERE bdaddr IN ({bdaddr_ph}) AND bdaddr_random = %s "
                                f"AND str_UUID16s REGEXP %s")
                    vals = tuple(bdaddr_list) + (bdaddr_random, uuid_pattern)
                else:
                    le_query = (f"SELECT DISTINCT bdaddr FROM LE_bdaddr_to_UUID16s_list "
                                f"WHERE bdaddr IN ({bdaddr_ph}) AND str_UUID16s REGEXP %s")
                    vals = tuple(bdaddr_list) + (uuid_pattern,)
                for (bdaddr,) in execute_query(le_query, vals):
                    matched.add(bdaddr)
                    remaining.discard(bdaddr)

    ############################################
    # CLUES path — batched, candidate-scoped.
    #
    # CLUES UUIDs are full 128-bit values, so they cannot substring-match
    # inside UUID16 (4-char) or UUID32 (8-char) columns — those tables are
    # skipped. All matching CLUES UUIDs for this company regex are collapsed
    # into a single alternation regex per column format and each table is hit
    # exactly once, scoped to the remaining candidate bdaddrs via `bdaddr IN`.
    #
    # Two alternations are emitted because the columns are stored in different
    # formats:
    #   * UUID128s tables (EIR_bdaddr_to_UUID128s, LE_bdaddr_to_UUID128s_list,
    #     LE_bdaddr_to_UUID128_service_solicit, LE_bdaddr_to_UUID128_service_data)
    #     store dash-stripped UUID128 hex.
    #   * GATT_{services,characteristics,attribute_handles}.UUID is CHAR(36)
    #     and stores the dashed form "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx".
    ############################################
    if remaining:
        clues_uuids_raw = []  # keep original dashed form from CLUES
        for key in TME.TME_glob.clues.keys():
            if re.search(pattern, TME.TME_glob.clues[key]["company"]):
                clues_uuids_raw.append(TME.TME_glob.clues[key]["UUID"])

        if clues_uuids_raw:
            clues_pattern_dashless = "|".join(u.replace("-", "") for u in clues_uuids_raw)
            clues_pattern_dashed = "|".join(clues_uuids_raw)

            # (table, uuid_column, uses_bdaddr_random, pattern)
            clues_tables = (
                ("EIR_bdaddr_to_UUID128s", "str_UUID128s", False, clues_pattern_dashless),
                ("LE_bdaddr_to_UUID128s_list", "str_UUID128s", True, clues_pattern_dashless),
                ("LE_bdaddr_to_UUID128_service_solicit", "str_UUID128s", True, clues_pattern_dashless),
                ("LE_bdaddr_to_UUID128_service_data", "UUID128_hex_str", True, clues_pattern_dashless),
                ("GATT_services", "UUID", True, clues_pattern_dashed),
                ("GATT_characteristics", "UUID", True, clues_pattern_dashed),
                ("GATT_attribute_handles", "UUID", True, clues_pattern_dashed),
            )

            for table, col, uses_random, clues_pattern in clues_tables:
                if not remaining:
                    break
                bdaddr_list = list(remaining)
                bdaddr_ph = ",".join(["%s"] * len(bdaddr_list))
                if uses_random and bdaddr_random is not None:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND bdaddr_random = %s "
                             f"AND {col} REGEXP %s")
                    vals = tuple(bdaddr_list) + (bdaddr_random, clues_pattern)
                else:
                    query = (f"SELECT DISTINCT bdaddr FROM {table} "
                             f"WHERE bdaddr IN ({bdaddr_ph}) "
                             f"AND {col} REGEXP %s")
                    vals = tuple(bdaddr_list) + (clues_pattern,)
                for (bdaddr,) in execute_query(query, vals):
                    matched.add(bdaddr)
                    remaining.discard(bdaddr)

    qprint(f"get_candidate_bdaddrs_matching_company_regex: {len(matched)}/{len(candidate_set)} candidates matched")
    return matched


def get_bdaddrs_by_msd_regex(msdregex, bdaddr_random):
    qprint(f"{msdregex} in get_bdaddrs_by_msd_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (msdregex,)
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP %s"
    eir_result = execute_query(eir_query, values)
    bdaddrs += eir_result
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_msd_regex: {len(eir_result)} results found in DB:EIR_bdaddr_to_MSD")
    qprint(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        values = (bdaddr_random, msdregex)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE bdaddr_random = %s AND manufacturer_specific_data REGEXP %s"
    else:
        values = (msdregex,)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_MSD WHERE manufacturer_specific_data REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_msd_regex: {len(le_result)} results found in DB:LE_bdaddr_to_MSD")
    qprint(f"get_bdaddrs_by_msd_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()

def sanity_check_UUID_regex(entry):
    if "-" not in entry:
        return True
    while True:
        print(" __                 ")
        print("/  \\        ____________________________________________")
        print("|  |       /                                             \\")
        print("@  @       | It looks like you are trying to pass a UUID |")
        print("|| ||      | regex with dashes in it. The dashes will be |")
        print("|| ||   <--| interpreted as part of the regex pattern.   |")
        print("|\\_/|      | Do you want me to remove the dashes?        |")
        print("\\___/      \\_____________________________________________/")
        try:
            choice = input("y/n: ")
        except EOFError:
            print("Input must be y or n. Try again!")
            return False
        choice = choice.strip().lower()
        if choice == "y":
            return True
        if choice == "n":
            return False
        print("Input must be y or n. Try again!")


def get_bdaddrs_by_uuid_regex(uuid_regex, bdaddr_random):

    qprint(f"{uuid_regex} in get_bdaddrs_by_uuid_regex")
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables

    # We probably shouldn't remove - since it can change the meaning of things like [1-4]...
    #uuid_regex.replace("-", "")

    # It could be argued that I could skip some UUID16 tables if the regex is guaranteed to be
    # > 4 characters, but that would require fully interpolating the regex.
    # So I'm just going to do it the simple but inefficient way, and look at all the tables
    # which contain a UUID, regardless of length.

    values = (uuid_regex,)

    ###################################
    # Start with UUID128 tables
    ###################################

    # BR/EDR advertisements
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID128s WHERE str_UUID128s REGEXP %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in DB:EIR_bdaddr_to_UUID128s")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    # LE advertisements
    if(bdaddr_random is not None):
        values = (bdaddr_random, uuid_regex)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE bdaddr_random = %s AND str_UUID128s REGEXP %s"
    else:
        values = (uuid_regex,)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128s_list WHERE str_UUID128s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID128s_list")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE bdaddr_random = %s AND str_UUID128s REGEXP %s"
    else:
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_solicit WHERE str_UUID128s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID128_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE bdaddr_random = %s AND UUID128_hex_str REGEXP %s"
    else:
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID128_service_data WHERE UUID128_hex_str REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID128_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    ###################################
    # Then UUID32 tables
    ###################################

    # BR/EDR advertisements
    values = (uuid_regex,)
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID32s WHERE str_UUID32s REGEXP %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in DB:EIR_bdaddr_to_UUID32s")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    # LE advertisements
    if(bdaddr_random is not None):
        values = (bdaddr_random, uuid_regex)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE bdaddr_random = %s AND str_UUID32s REGEXP %s"
    else:
        values = (uuid_regex,)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32s_list WHERE str_UUID32s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID32s_list")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE bdaddr_random = %s AND str_UUID32s REGEXP %s"
    else:
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_solicit WHERE str_UUID32s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID32_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE bdaddr_random = %s AND UUID32_hex_str REGEXP %s"
    else:
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID32_service_data WHERE UUID32_hex_str REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID32_service_data")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    ###################################
    # Then UUID16 tables
    ###################################

    # BR/EDR advertisements
    values = (uuid_regex,)
    eir_query = "SELECT bdaddr FROM EIR_bdaddr_to_UUID16s WHERE str_UUID16s REGEXP %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in DB:EIR_bdaddr_to_UUID16s")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    # LE advertisements
    if(bdaddr_random is not None):
        values = (bdaddr_random, uuid_regex)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE bdaddr_random = %s AND str_UUID16s REGEXP %s"
    else:
        values = (uuid_regex,)
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16s_list WHERE str_UUID16s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID16s_list")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE bdaddr_random = %s AND str_UUID16s REGEXP %s"
    else:
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_solicit WHERE str_UUID16s REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID16_service_solicit")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE bdaddr_random = %s AND UUID16_hex_str REGEXP %s"
    else:
        le_query = "SELECT bdaddr FROM LE_bdaddr_to_UUID16_service_data WHERE UUID16_hex_str REGEXP %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(le_result)} results found in DB:LE_bdaddr_to_UUID16_service_data")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    ################################################
    # Then GATT, which can have UUID16s or UUID128s
    ################################################

    # GATT (technically LE or BR/EDR but I don't have BR/EDR-based collection)

    if(bdaddr_random is not None):
        gatt_service_query = "SELECT bdaddr FROM GATT_services WHERE bdaddr_random = %s AND UUID REGEXP %s"
    else:
        gatt_service_query = "SELECT bdaddr FROM GATT_services WHERE UUID REGEXP %s"
    gatt_service_result = execute_query(gatt_service_query, values)
    for (bdaddr,) in gatt_service_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(gatt_service_result)} results found in GATT_services")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        gatt_char_query = "SELECT bdaddr FROM GATT_characteristics WHERE bdaddr_random = %s AND UUID REGEXP %s"
    else:
        gatt_char_query = "SELECT bdaddr FROM GATT_characteristics WHERE UUID REGEXP %s"
    gatt_char_result = execute_query(gatt_char_query, values)
    for (bdaddr,) in gatt_char_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(gatt_char_result)} results found in GATT_characteristics")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    if(bdaddr_random is not None):
        gatt_desc_query = "SELECT bdaddr FROM GATT_attribute_handles WHERE bdaddr_random = %s AND UUID REGEXP %s"
    else:
        gatt_desc_query = "SELECT bdaddr FROM GATT_attribute_handles WHERE UUID REGEXP %s"
    gatt_desc_result = execute_query(gatt_desc_query, values)
    for (bdaddr,) in gatt_desc_result:
        bdaddr_hash[bdaddr] = 1
    vprint(f"get_bdaddrs_by_uuid_regex: {len(gatt_desc_result)} results found in GATT_attribute_handles")
    vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash len {len(bdaddr_hash)} = {bdaddr_hash}")

    ################################################
    # Then SDP, which can have UUID16/32/128s
    ################################################

    # BR/EDR SDP

    # TODO: I'd like to pull out UUIDs specifically and put them back in a separate table,
    # because right now this will probably yield a decent number of false positives...
    # It can also yield false negatives, if given the full UUID, because I've seen
    # them be fragmented across packets.
    # eir_query = "SELECT bdaddr FROM SDP_Common HERE HEX(byte_values) REGEXP %s"
    # eir_result = execute_query(eir_query, values)
    # for (bdaddr,) in eir_result:
    #     bdaddr_hash[bdaddr] = 1
    # qprint(f"get_bdaddrs_by_uuid_regex: {len(eir_result)} results found in SDP_Common")
    # vprint(f"get_bdaddrs_by_uuid_regex: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()


def get_bdaddrs_by_LL_VERSION_IND(version, company_id, subversion, bdaddr_random):
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    if(bdaddr_random is not None):
        values = (version, company_id, subversion, bdaddr_random)
        le_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE ll_version = %s AND device_BT_CID = %s AND ll_sub_version = %s AND bdaddr_random = %s"
    else:
        values = (version, company_id, subversion)
        le_query = "SELECT bdaddr FROM LL_VERSION_IND WHERE ll_version = %s AND device_BT_CID = %s AND ll_sub_version = %s"
    le_result = execute_query(le_query, values)
    for (bdaddr,) in le_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_LL_VERSION_IND: {len(le_result)} results found in LL_VERSION_IND")
    qprint(f"get_bdaddrs_by_LL_VERSION_IND: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()


def get_bdaddrs_by_LMP_VERSION_RES(version, company_id, subversion):
    bdaddr_hash = {} # Use hash to de-duplicate between all results from all tables
    bdaddrs = []

    values = (version, company_id, subversion)
    eir_query = "SELECT bdaddr FROM LMP_VERSION_RES WHERE lmp_version = %s AND device_BT_CID = %s AND lmp_sub_version = %s"
    eir_result = execute_query(eir_query, values)
    for (bdaddr,) in eir_result:
        bdaddr_hash[bdaddr] = 1
    qprint(f"get_bdaddrs_by_LMP_VERSION_RES: {len(eir_result)} results found in LMP_VERSION_RES")
    qprint(f"get_bdaddrs_by_LMP_VERSION_RES: bdaddr_hash = {bdaddr_hash}")

    return bdaddr_hash.keys()
