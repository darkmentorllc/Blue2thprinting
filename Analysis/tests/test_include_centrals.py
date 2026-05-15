########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end tests for `Tell_Me_Everything.py --include-centrals`.

The flag only changes behavior when a BTIDES input entry is the
DualBDADDR shape (i.e. has a `CONNECT_IND` block). For SingleBDADDR
entries it is a no-op. The relevant code in Tell_Me_Everything.py:

    for entry in TME.TME_glob.BTIDES_JSON:
        if 'bdaddr' in entry:
            ...                             # SingleBDADDR, always rendered
        elif 'CONNECT_IND' in entry:
            ...peripheral always added to bdaddrs...
            if args.include_centrals:
                ...central also added to bdaddrs...

So we build a tiny .btides with one DualBDADDR / CONNECT_IND entry, feed
it via `--input-BTIDES`, and assert:

  * without `--include-centrals`: only the peripheral BDADDR renders
    (i.e. shows up under `For bdaddr = X:`)
  * with `--include-centrals`: both the peripheral AND the central
    render.

The CONNECT_IND object's required-field list comes from
BTIDES_Schema/BTIDES_base.json definitions/CONNECT_IND. We fill them with
plausible-but-synthetic values; BTIDES_to_SQL is tolerant of values it
doesn't recognize as long as the schema validates.
"""

import json
import re

import pytest


# Use two BDADDRs that the seed already populates with rich data
# (LE_bdaddr_to_name, LE_bdaddr_to_flags, etc.). Tell_Me_Everything.py's
# render loop skips any BDADDR that `bdaddr_found_in_any_table` reports
# as unknown, so the test BDADDRs need DB rows somewhere for the
# rendering-side assertion to work. The CONNECT_IND payload by itself
# doesn't populate any of the queryable tables — it's pure metadata that
# only influences which BDADDRs get appended to the candidate list.
PERIPHERAL_BDADDR = "aa:bb:cc:11:22:01"  # seed.sql device 1
CENTRAL_BDADDR    = "aa:bb:cc:11:22:04"  # seed.sql device 4

# Minimal valid CONNECT_IND payload. Required fields per BTIDES_base.json.
_CONNECT_IND_ENTRY = {
    "CONNECT_IND": {
        "central_bdaddr":         CENTRAL_BDADDR,
        "central_bdaddr_rand":    0,
        "peripheral_bdaddr":      PERIPHERAL_BDADDR,
        "peripheral_bdaddr_rand": 0,
        "access_address":         0x8E89BED6,
        "crc_init_hex_str":       "563412",
        "win_size":               1,
        "win_offset":             0,
        "interval":               6,
        "latency":                0,
        "timeout":                100,
        "channel_map_hex_str":    "ffffffff1f",
        "hop":                    10,
        "SCA":                    1,
    },
}

_RENDERED_BDADDR = re.compile(r"^For bdaddr = ([0-9A-Fa-f:]{17}):", re.MULTILINE)


def _rendered(stdout):
    """Return the lowercase set of BDADDRs that have a `For bdaddr = X:`
    header in the rendered output.
    """
    return {m.group(1).lower() for m in _RENDERED_BDADDR.finditer(stdout)}


@pytest.fixture
def connect_ind_btides(tmp_path):
    """Write a one-entry BTIDES file containing only a CONNECT_IND DualBDADDR
    and return the path.
    """
    p = tmp_path / "connect_ind.btides"
    with open(p, "w") as f:
        json.dump([_CONNECT_IND_ENTRY], f)
    return p


def test_include_centrals_off_renders_peripheral_only(db_clean, run_tme,
                                                     connect_ind_btides):
    """Default behavior: a CONNECT_IND entry adds only the peripheral
    BDADDR to the rendered set. The central is intentionally excluded
    because it's usually just "our scanning device with a random BDADDR",
    not data the user cares about.
    """
    result = run_tme("--input-BTIDES", str(connect_ind_btides))
    rendered = _rendered(result.stdout)
    assert PERIPHERAL_BDADDR in rendered, \
        f"Peripheral BDADDR should always render from a CONNECT_IND " \
        f"entry; got rendered={rendered}\nstdout:\n{result.stdout}"
    assert CENTRAL_BDADDR not in rendered, \
        f"Central BDADDR must NOT render without --include-centrals; got " \
        f"rendered={rendered}\nstdout:\n{result.stdout}"


def test_include_centrals_on_renders_both(db_clean, run_tme,
                                          connect_ind_btides):
    """With --include-centrals, the central BDADDR is also added to the
    bdaddrs list and renders alongside the peripheral.
    """
    result = run_tme("--input-BTIDES", str(connect_ind_btides),
                     "--include-centrals")
    rendered = _rendered(result.stdout)
    assert PERIPHERAL_BDADDR in rendered, \
        f"Peripheral missing from rendered output:\n{result.stdout}"
    assert CENTRAL_BDADDR in rendered, \
        f"Central must render with --include-centrals; got " \
        f"rendered={rendered}\nstdout:\n{result.stdout}"


def test_include_centrals_is_noop_for_single_bdaddr_input(db_clean, run_tme,
                                                          tmp_path):
    """--include-centrals must NOT change rendering of SingleBDADDR
    entries (no CONNECT_IND), since the flag's whole purpose is to
    selectively include the central from a captured connection.
    """
    # Single-BDADDR entry pointing at a never-before-seen BDADDR so the
    # `--include-centrals` no-op is clearly observable — no CONNECT_IND
    # path, just a plain advertisement.
    new_bdaddr = "aa:bb:cc:de:ad:42"
    single = [{
        "bdaddr": new_bdaddr,
        "bdaddr_rand": 0,
        "AdvChanArray": [{
            "type": 0,
            "AdvDataArray": [{
                "type": 9,
                "length": 1 + len("IncludeCentralsTest"),
                "name_hex_str": "IncludeCentralsTest".encode().hex(),
            }],
        }],
    }]
    in_file = tmp_path / "single.btides"
    with open(in_file, "w") as f:
        json.dump(single, f)

    without = run_tme("--input-BTIDES", str(in_file))
    with_flag = run_tme("--input-BTIDES", str(in_file), "--include-centrals")

    assert _rendered(without.stdout) == _rendered(with_flag.stdout), \
        f"--include-centrals changed the rendered set for SingleBDADDR " \
        f"input (it should be a no-op).\n" \
        f"without: {_rendered(without.stdout)}\n" \
        f"with:    {_rendered(with_flag.stdout)}"
