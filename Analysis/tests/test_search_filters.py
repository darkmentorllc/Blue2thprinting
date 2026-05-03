########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Tests for Tell_Me_Everything.py search filter flags:

- Exclusion filters: --NOT-bdaddr, --NOT-bdaddr-regex, --NOT-name-regex,
  --NOT-company-regex, --NOT-UUID-regex
- Content regexes:   --company-regex, --UUID-regex, --MSD-regex
- Exact-match flags: --LL_VERSION_IND, --LMP_VERSION_RES
- GPS bounding box:  --GPS-exclude-upper-left, --GPS-exclude-lower-right

All tests use the seeded fixture set (devices aa:bb:cc:11:22:01..05 from
fixtures/seed.sql). The run_tme fixture always passes --use-test-db.
"""

from test_db_query import rendered_bdaddrs, ALL_TEST_BDADDR_REGEX

ALL_SEEDED = {f"aa:bb:cc:11:22:0{n}" for n in range(1, 6)}


# ---------------------------------------------------------------------------
# --NOT-bdaddr (exact exclusion, repeatable)
# ---------------------------------------------------------------------------

def test_NOT_bdaddr_drops_one_device(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
                     "--NOT-bdaddr", "aa:bb:cc:11:22:01")
    rendered = rendered_bdaddrs(result.stdout)
    assert rendered == ALL_SEEDED - {"aa:bb:cc:11:22:01"}, \
        f"--NOT-bdaddr should drop just device 1; got: {rendered}"


def test_NOT_bdaddr_repeated_drops_multiple(run_tme):
    """--NOT-bdaddr is repeatable; passing it twice drops both."""
    result = run_tme(
        "--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
        "--NOT-bdaddr", "aa:bb:cc:11:22:01",
        "--NOT-bdaddr", "aa:bb:cc:11:22:05",
    )
    rendered = rendered_bdaddrs(result.stdout)
    assert rendered == ALL_SEEDED - {"aa:bb:cc:11:22:01", "aa:bb:cc:11:22:05"}, \
        f"Two --NOT-bdaddr should drop both devices; got: {rendered}"


# ---------------------------------------------------------------------------
# --NOT-bdaddr-regex (regex exclusion)
# ---------------------------------------------------------------------------

def test_NOT_bdaddr_regex_drops_matching_devices(run_tme):
    """A regex that matches BDADDRs ending in :02 or :03 drops both."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
                     "--NOT-bdaddr-regex", "11:22:0[23]")
    rendered = rendered_bdaddrs(result.stdout)
    assert rendered == ALL_SEEDED - {"aa:bb:cc:11:22:02", "aa:bb:cc:11:22:03"}, \
        f"--NOT-bdaddr-regex 11:22:0[23] should drop devices 2+3; got: {rendered}"


def test_NOT_bdaddr_regex_no_match_keeps_all(run_tme):
    """A regex matching nothing is a no-op."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
                     "--NOT-bdaddr-regex", "ZZ:ZZ:ZZ")
    assert ALL_SEEDED.issubset(rendered_bdaddrs(result.stdout))


# ---------------------------------------------------------------------------
# --NOT-name-regex
# ---------------------------------------------------------------------------

def test_NOT_name_regex_drops_device_with_matching_name(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
                     "--NOT-name-regex", "TestGATT2")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:02" not in rendered, \
        f"--NOT-name-regex TestGATT2 should drop device 2; got: {rendered}"
    # The other four should remain
    assert (ALL_SEEDED - {"aa:bb:cc:11:22:02"}).issubset(rendered)


# ---------------------------------------------------------------------------
# --NOT-company-regex
# ---------------------------------------------------------------------------

def test_NOT_company_regex_drops_apple_device(run_tme):
    """Device 1's MSD has Apple's BT Company ID 0x004C."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
                     "--NOT-company-regex", "Apple")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:01" not in rendered, \
        f"--NOT-company-regex Apple should drop device 1; got: {rendered}"


# ---------------------------------------------------------------------------
# --NOT-UUID-regex
# ---------------------------------------------------------------------------

def test_NOT_UUID_regex_drops_device_with_matching_uuid(run_tme):
    """Device 1 advertises UUID16 180d (Heart Rate)."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
                     "--NOT-UUID-regex", "180d")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:01" not in rendered, \
        f"--NOT-UUID-regex 180d should drop device 1; got: {rendered}"


# ---------------------------------------------------------------------------
# --company-regex (positive content search)
# ---------------------------------------------------------------------------

def test_company_regex_apple_finds_device1(run_tme):
    """Device 1's MSD carries Apple's BT Company ID 0x004C."""
    result = run_tme("--company-regex", "Apple")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:01" in rendered, \
        f"--company-regex Apple should find device 1; got: {rendered}"


def test_company_regex_texas_finds_device4(run_tme):
    """Device 4's LL_VERSION_IND carries TI's BT Company ID 13."""
    result = run_tme("--company-regex", "Texas")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:04" in rendered, \
        f"--company-regex Texas should find device 4; got: {rendered}"


# ---------------------------------------------------------------------------
# --UUID-regex (positive content search)
# ---------------------------------------------------------------------------

def test_UUID_regex_180d_finds_device1(run_tme):
    """Heart Rate Service UUID16 in device 1's adv list."""
    result = run_tme("--UUID-regex", "180d")
    assert "aa:bb:cc:11:22:01" in rendered_bdaddrs(result.stdout)


def test_UUID_regex_180f_finds_device2(run_tme):
    """Battery Service UUID16 in device 2's GATT services."""
    result = run_tme("--UUID-regex", "180f")
    assert "aa:bb:cc:11:22:02" in rendered_bdaddrs(result.stdout)


def test_UUID_regex_no_match_returns_no_devices(run_tme):
    result = run_tme("--UUID-regex", "deadbeef")
    assert rendered_bdaddrs(result.stdout) == set()


# ---------------------------------------------------------------------------
# --MSD-regex
# ---------------------------------------------------------------------------

def test_MSD_regex_apple_ibeacon_prefix_finds_device1(run_tme):
    """Device 1's MSD payload starts with 0215 (Apple iBeacon prefix)."""
    result = run_tme("--MSD-regex", "^0215")
    assert "aa:bb:cc:11:22:01" in rendered_bdaddrs(result.stdout)


def test_MSD_regex_no_match_returns_no_devices(run_tme):
    result = run_tme("--MSD-regex", "^cafe")
    assert rendered_bdaddrs(result.stdout) == set()


# ---------------------------------------------------------------------------
# --LL_VERSION_IND (exact match: version, company id, sub-version, all hex)
# ---------------------------------------------------------------------------

# Device 4: ll_version=6 (BT 4.0), device_BT_CID=13 (TI), ll_sub_version=322 (0x142)

def test_LL_VERSION_IND_exact_match_finds_device4(run_tme):
    result = run_tme("--LL_VERSION_IND", "06:000d:0142")
    assert "aa:bb:cc:11:22:04" in rendered_bdaddrs(result.stdout)


def test_LL_VERSION_IND_wrong_subversion_finds_nothing(run_tme):
    """Same version + CID but wrong sub-version → no match."""
    result = run_tme("--LL_VERSION_IND", "06:000d:0143")
    assert rendered_bdaddrs(result.stdout) == set()


def test_LL_VERSION_IND_wrong_company_finds_nothing(run_tme):
    """Same version + sub-version but wrong CID → no match."""
    result = run_tme("--LL_VERSION_IND", "06:000a:0142")
    assert rendered_bdaddrs(result.stdout) == set()


# ---------------------------------------------------------------------------
# --LMP_VERSION_RES (exact match: same hex format)
# ---------------------------------------------------------------------------

# Device 4: lmp_version=8 (BT 5.0), device_BT_CID=10 (CSR), lmp_sub_version=801 (0x321)

def test_LMP_VERSION_RES_exact_match_finds_device4(run_tme):
    result = run_tme("--LMP_VERSION_RES", "08:000a:0321")
    assert "aa:bb:cc:11:22:04" in rendered_bdaddrs(result.stdout)


def test_LMP_VERSION_RES_wrong_subversion_finds_nothing(run_tme):
    result = run_tme("--LMP_VERSION_RES", "08:000a:0322")
    assert rendered_bdaddrs(result.stdout) == set()


# ---------------------------------------------------------------------------
# --GPS-exclude-upper-left / --GPS-exclude-lower-right
# ---------------------------------------------------------------------------
# Device 2 has one GPS row in seed.sql at (38.9072, -77.0369) — Washington DC.
# No other seeded device has a GPS row.
#
# Filter semantics (from is_GPS_coordinate_within_exclusion_box in
# TME/TME_GPS.py): a device is excluded if it has *any* GPS coordinate where
#   upper_left.lat >= lat >= lower_right.lat   AND
#   upper_left.lon <= lon <= lower_right.lon
# i.e. the upper-left corner is the NW point (higher lat, lower/more-negative
# lon) and the lower-right corner is the SE point. Devices with no GPS rows
# at all are unaffected by the filter.

def test_GPS_exclude_box_around_device2_drops_it(run_tme):
    """Box (39.5,-78.0)..(38.0,-76.0) covers Washington DC → device 2 dropped."""
    result = run_tme(
        "--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
        "--GPS-exclude-upper-left", "(39.5,-78.0)",
        "--GPS-exclude-lower-right", "(38.0,-76.0)",
    )
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:02" not in rendered, \
        f"Device 2's GPS coord (38.9072,-77.0369) is inside the box; " \
        f"it should be excluded. Got: {rendered}"
    # The four GPS-less devices are unaffected and should still render.
    assert (ALL_SEEDED - {"aa:bb:cc:11:22:02"}).issubset(rendered)


def test_GPS_exclude_box_far_away_keeps_all(run_tme):
    """A box around California shouldn't exclude device 2's DC coordinate."""
    result = run_tme(
        "--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
        "--GPS-exclude-upper-left", "(37.5,-123.0)",
        "--GPS-exclude-lower-right", "(37.0,-121.0)",
    )
    assert ALL_SEEDED.issubset(rendered_bdaddrs(result.stdout))


def test_GPS_exclude_box_inclusive_on_boundary(run_tme):
    """The bounding-box check uses >= / <=, so a box whose SE corner sits
    exactly on device 2's coordinate still excludes it."""
    result = run_tme(
        "--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
        "--GPS-exclude-upper-left", "(40.0,-78.0)",
        "--GPS-exclude-lower-right", "(38.9072,-77.0369)",  # exact boundary
    )
    assert "aa:bb:cc:11:22:02" not in rendered_bdaddrs(result.stdout)


def test_GPS_exclude_only_upper_left_errors(run_tme):
    """Specifying just one of the two corners aborts with a usage error and
    renders no devices."""
    result = run_tme(
        "--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
        "--GPS-exclude-upper-left", "(39.5,-78.0)",
    )
    assert "If you specify either GPS exclude option, you must specify both." in result.stdout
    assert rendered_bdaddrs(result.stdout) == set(), \
        "No devices should render when the GPS exclude args are mismatched."


def test_GPS_exclude_only_lower_right_errors(run_tme):
    result = run_tme(
        "--bdaddr-regex", ALL_TEST_BDADDR_REGEX,
        "--GPS-exclude-lower-right", "(38.0,-76.0)",
    )
    assert "If you specify either GPS exclude option, you must specify both." in result.stdout
    assert rendered_bdaddrs(result.stdout) == set()


# ---------------------------------------------------------------------------
# --bdaddr-type
# ---------------------------------------------------------------------------
# Seed shape:
#   device 1 (aa:bb:cc:11:22:01) — LE Public (bdaddr_random=0): Adv data
#   device 2 (aa:bb:cc:11:22:02) — LE Random (bdaddr_random=1): GATT
#   device 3 (aa:bb:cc:11:22:03) — BT Classic (no bdaddr_random column): EIR/CoD/SDP
#   device 4 (aa:bb:cc:11:22:04) — LE Public (bdaddr_random=0) + LMP/LL_VERSION_IND
#   device 5 (aa:bb:cc:11:22:05) — LE Public (bdaddr_random=0) + SMP rows
#
# When --bdaddr-type is set, get_bdaddrs_by_bdaddr_regex restricts the LE
# tables to that bdaddr_random value. Tables without a bdaddr_random column
# (LMP, EIR, SDP) are not constrained, so devices that have data in those
# tables can leak through regardless of --bdaddr-type. The tests below pin
# what we expect to be true today (LE Public/Random discrimination) and
# explicitly note the tables-without-bdaddr_random leakage.

def test_bdaddr_type_0_excludes_LE_random_device(run_tme):
    """--bdaddr-type 0 (LE Public) must not return the LE Random device 2."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--bdaddr-type", "0")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:02" not in rendered, (
        f"LE Random device 2 should not match --bdaddr-type 0; got: {rendered}"
    )
    # All three pure-LE-Public devices should match.
    for d in ("aa:bb:cc:11:22:01", "aa:bb:cc:11:22:04", "aa:bb:cc:11:22:05"):
        assert d in rendered, f"LE Public device {d} should match --bdaddr-type 0; got: {rendered}"


def test_bdaddr_type_1_excludes_pure_LE_public_devices(run_tme):
    """--bdaddr-type 1 (LE Random) must not return LE-Public-only devices.
    Device 1 and device 5 only have LE-Public-side data, so they should
    drop. Device 2 (LE Random) must stay."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--bdaddr-type", "1")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:02" in rendered, \
        f"LE Random device 2 should match --bdaddr-type 1; got: {rendered}"
    for d in ("aa:bb:cc:11:22:01", "aa:bb:cc:11:22:05"):
        assert d not in rendered, \
            f"LE-Public-only device {d} should not match --bdaddr-type 1; got: {rendered}"


def test_bdaddr_type_unset_returns_everything(run_tme):
    """Default (no --bdaddr-type) matches all five seeded devices."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX)
    assert ALL_SEEDED.issubset(rendered_bdaddrs(result.stdout))


def test_bdaddr_type_renders_data_sections_when_matching(run_tme):
    """With --bdaddr <public-device> --bdaddr-type 0, the per-device data
    sections (Name, UUID16, MSD, ...) all render — bdaddr_type matches the
    stored row."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--bdaddr-type", "0")
    assert "DeviceName: TestDevice1" in result.stdout, \
        f"Expected device 1's name to render; got:\n{result.stdout}"
    assert "180d" in result.stdout, \
        f"Expected device 1's Heart Rate UUID16 to render; got:\n{result.stdout}"


def test_bdaddr_type_suppresses_data_sections_when_mismatched(run_tme):
    """With --bdaddr <public-device> --bdaddr-type 1 (LE Random forced), the
    data sections are filtered out by per-table bdaddr_random=1 lookups,
    even though the 'For bdaddr = ...' header is still printed because
    --bdaddr is a direct override that doesn't go through the LE-side regex
    lookup."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:01", "--bdaddr-type", "1")
    assert "DeviceName: TestDevice1" not in result.stdout, (
        f"With --bdaddr-type=1 mismatched against a public device, the name "
        f"section should be suppressed; got:\n{result.stdout}"
    )


def test_bdaddr_type_random_renders_GATT_for_random_device(run_tme):
    """Sanity: --bdaddr <random-device> --bdaddr-type 1 still renders GATT
    sections from device 2."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:02", "--bdaddr-type", "1")
    assert "TestGATT2" in result.stdout, \
        f"Expected device 2's name to render with --bdaddr-type 1; got:\n{result.stdout}"


# ---------------------------------------------------------------------------
# --GPS-exclude-upper-left / --GPS-exclude-lower-right (continued)
# ---------------------------------------------------------------------------

def test_GPS_exclude_does_not_affect_devices_without_gps(run_tme):
    """Devices with no GPS rows at all (seeded devices 1, 3, 4, 5) should be
    immune to the GPS-exclude filter even when the box is global."""
    # A box that covers basically the whole planet would exclude any GPS-bearing
    # device, but devices with no GPS row in bdaddr_to_GPS pass through.
    result = run_tme(
        "--bdaddr", "AA:BB:CC:11:22:01",
        "--GPS-exclude-upper-left", "(90.0,-180.0)",
        "--GPS-exclude-lower-right", "(-90.0,180.0)",
    )
    assert "aa:bb:cc:11:22:01" in rendered_bdaddrs(result.stdout)
