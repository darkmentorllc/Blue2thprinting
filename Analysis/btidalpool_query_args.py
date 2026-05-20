########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""
Shared builder for the Tell_Me_Everything query-specific CLI flags derived
from a BTIDALPOOL query_object.

Extracted verbatim from Server_BTIDALPOOL.py's handle_query() so there is a
single source of truth for the Python server's query-flag construction,
used by BOTH:
  * the production Python server (Server_BTIDALPOOL.py imports this), and
  * the cross-language parity test (BTIDALPOOL/python/test_query_parity.py),

so the parity test compares the REAL server logic against the Rust server's
`btidalpool_server::query::tme_query_args()`.

Returns ONLY the query *filter* flags (the "cascade") — NOT the
infrastructure flags (--max-records-output / --quiet-print / --use-test-db /
--output). Those are identical between the Python and Rust servers by
construction and don't affect which records match a query, so the filter
cascade is the part whose parity actually determines identical output.

Security: only allow-listed keys are honored. Any other key in query_object
is ignored (matches the original server comment "only use arguments which we
are expecting, and ignore everything else").

Note on the require_* booleans: this mirrors the server's *presence*-based
checks (`if "require_GPS" in query_object`), not value truthiness. In
practice callers only insert these keys when the corresponding flag is set,
so presence == True; the Rust side keys off the bool value being true. For
the realistic inputs (key absent, or key present with value true) the two
implementations agree.
"""


def build_query_args(query_object):
    """Return the list of TME query-filter CLI flags for `query_object`."""
    args = []
    if "bdaddr" in query_object:
        args.append("--bdaddr")
        args.append(f"{query_object['bdaddr']}")
    if "NOT_bdaddr" in query_object:
        for entry in query_object['NOT_bdaddr']:
            args.append("--NOT-bdaddr")
            args.append(f"{entry}")
    if "bdaddr_regex" in query_object:
        for entry in query_object['bdaddr_regex']:
            args.append("--bdaddr-regex")
            args.append(f"{entry}")
    if "NOT_bdaddr_regex" in query_object:
        for entry in query_object['NOT_bdaddr_regex']:
            args.append("--NOT-bdaddr-regex")
            args.append(f"{entry}")
    if "name_regex" in query_object:
        for entry in query_object['name_regex']:
            args.append("--name-regex")
            args.append(f"{entry}")
    if "NOT_name_regex" in query_object:
        for entry in query_object['NOT_name_regex']:
            args.append("--NOT-name-regex")
            args.append(f"{entry}")
    if "company_regex" in query_object:
        for entry in query_object['company_regex']:
            args.append("--company-regex")
            args.append(f"{entry}")
    if "NOT_company_regex" in query_object:
        for entry in query_object['NOT_company_regex']:
            args.append("--NOT-company-regex")
            args.append(f"{entry}")
    if "UUID_regex" in query_object:
        for entry in query_object['UUID_regex']:
            args.append("--UUID-regex")
            args.append(f"{entry}")
    if "NOT_UUID_regex" in query_object:
        for entry in query_object['NOT_UUID_regex']:
            args.append("--NOT-UUID-regex")
            args.append(f"{entry}")
    if "MSD_regex" in query_object:
        for entry in query_object['MSD_regex']:
            args.append("--MSD-regex")
            args.append(f"{entry}")
    if "LL_VERSION_IND" in query_object:
        args.append("--LL_VERSION_IND")
        args.append(f"{query_object['LL_VERSION_IND']}")
    if "LMP_VERSION_RES" in query_object:
        args.append("--LMP_VERSION_RES")
        args.append(f"{query_object['LMP_VERSION_RES']}")
    if "GPS_exclude_upper_left" in query_object:
        args.append("--GPS-exclude-upper-left")
        args.append(f"{query_object['GPS_exclude_upper_left']}")
    if "GPS_exclude_lower_right" in query_object:
        args.append("--GPS-exclude-lower-right")
        args.append(f"{query_object['GPS_exclude_lower_right']}")
    if "require_GPS" in query_object:
        args.append("--require-GPS")
    if "require_GATT_any" in query_object:
        args.append("--require-GATT-any")
    if "require_GATT_values" in query_object:
        args.append("--require-GATT-values")
    if "require_SMP" in query_object:
        args.append("--require-SMP")
    if "require_SMP_legacy_pairing" in query_object:
        args.append("--require-SMP-legacy-pairing")
    if "require_SDP" in query_object:
        args.append("--require-SDP")
    if "require_LL_VERSION_IND" in query_object:
        args.append("--require-LL_VERSION_IND")
    if "require_LMP_VERSION_RES" in query_object:
        args.append("--require-LMP_VERSION_RES")
    return args
