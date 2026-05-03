########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""End-to-end DB query tests: invoke Tell_Me_Everything.py with --use-test-db
and search arguments, assert key strings appear in stdout.

Each test uses the seeded device set in fixtures/seed.sql.

Notes
-----
- Tell_Me_Everything.py renders BDADDRs in the case they were supplied on the
  CLI (--bdaddr passes the user's case through). When BDADDRs come *from* the
  DB (e.g. via --bdaddr-regex / --name-regex / --require-*), they render as
  the DB stores them — lowercase. Tests use case-insensitive helpers.
- The --require-* flags filter an existing search result; they don't drive
  the search themselves. Tests combine them with --bdaddr-regex AA:BB:CC,
  which matches all five seeded test devices.
- Tell_Me_Everything.py also emits diagnostic lines like
  ``bdaddr_hash = {'aa:bb:cc:11:22:01': 1, ...}`` BEFORE filtering. To check
  which devices were actually rendered, use ``rendered_bdaddrs()`` rather
  than searching the full stdout.
"""

import re

ALL_TEST_BDADDR_REGEX = "AA:BB:CC"

_BDADDR_HEADER = re.compile(r"^For bdaddr = ([0-9A-Fa-f:]{17}):", re.MULTILINE)


def rendered_bdaddrs(stdout):
    """Return the set of BDADDRs (lowercase) that have a 'For bdaddr = X:' header."""
    return {m.group(1).lower() for m in _BDADDR_HEADER.finditer(stdout)}


def _expect_in(haystack, needles):
    missing = [n for n in needles if n not in haystack]
    assert not missing, f"Expected substrings missing from output: {missing}\n--- output ---\n{haystack}"


# ---------------------------------------------------------------------------
# Single-device --bdaddr lookups (case is preserved from the CLI argument)
# ---------------------------------------------------------------------------

def test_bdaddr_lookup_device1(run_tme):
    """--bdaddr returns name, UUID16, flags, tx_power, MSD for AA:BB:CC:11:22:01."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:01")
    _expect_in(result.stdout, [
        "AA:BB:CC:11:22:01",
        "DeviceName: TestDevice1",
        "BDADDR is Bluetooth Low Energy Public",
        "UUID16 180d",
        "Heart Rate",
        "Transmit Power: -4dB",
        "Apple, Inc.",
    ])


def test_bdaddr_lookup_device2_gatt(run_tme):
    """--bdaddr for device 2 returns GATT services and characteristics."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:02")
    _expect_in(result.stdout, [
        "DeviceName: TestGATT2",
        "1800",   # GAP service UUID
        "1801",   # GATT service UUID
        "180f",   # Battery service UUID
        "2a19",   # Battery Level characteristic UUID
    ])
    assert "aa:bb:cc:11:22:02" in rendered_bdaddrs(result.stdout)


def test_bdaddr_classic_device3(run_tme):
    """Device 3 has BT Classic EIR data: name + CoD."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:03")
    _expect_in(result.stdout, [
        "AA:BB:CC:11:22:03",
        "ClassicTest",
    ])


def test_bdaddr_versions_device4(run_tme):
    """Device 4 has both LL_VERSION_IND and LMP_VERSION_RES."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:04")
    _expect_in(result.stdout, [
        "AA:BB:CC:11:22:04",
        "TestVersions",
    ])
    # Texas Instruments is BT Company ID 13. Match either the company name
    # (when lookup data is loaded) or the raw CID; this keeps the test from
    # depending on whether IEEE/UUID16 lookup tables were populated.
    assert re.search(r"Texas Instruments|0x000d|\b13\b", result.stdout), \
        f"Expected TI vendor reference in output:\n{result.stdout}"


def test_bdaddr_smp_device5(run_tme):
    """Device 5 has SMP Pairing Req/Res (legacy)."""
    result = run_tme("--bdaddr", "AA:BB:CC:11:22:05")
    _expect_in(result.stdout, [
        "AA:BB:CC:11:22:05",
        "TestSMP",
    ])
    # The SMP printer renders some opcode-related text. Don't pin to an exact
    # phrase since the rendering may evolve.
    assert any(s in result.stdout.lower() for s in ["pairing request", "pairing_request", "pairing", "opcode"])


# ---------------------------------------------------------------------------
# Search-by-content: regexes and --require-* filters
# ---------------------------------------------------------------------------

def test_name_regex_finds_device(run_tme):
    """--name-regex matches against device_name and returns the matching device."""
    result = run_tme("--name-regex", "TestGATT2")
    rendered = rendered_bdaddrs(result.stdout)
    assert "aa:bb:cc:11:22:02" in rendered
    assert "TestDevice1" not in result.stdout


def test_bdaddr_regex_returns_all_seeded(run_tme):
    """--bdaddr-regex AA:BB:CC returns all five seeded devices."""
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX)
    rendered = rendered_bdaddrs(result.stdout)
    expected = {f"aa:bb:cc:11:22:{n:02x}" for n in range(1, 6)}
    assert expected.issubset(rendered), f"Missing: {expected - rendered}; got: {rendered}"


def test_require_GATT_any_filters_to_device2(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-GATT-any")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:02"}


def test_require_GATT_values_filters_to_device2(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-GATT-values")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:02"}


def test_require_SMP_filters_to_device5(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-SMP")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:05"}


def test_require_GPS_filters_to_device2(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-GPS")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:02"}


def test_require_LL_VERSION_IND_filters_to_device4(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-LL_VERSION_IND")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:04"}


def test_require_LMP_VERSION_RES_filters_to_device4(run_tme):
    result = run_tme("--bdaddr-regex", ALL_TEST_BDADDR_REGEX, "--require-LMP_VERSION_RES")
    assert rendered_bdaddrs(result.stdout) == {"aa:bb:cc:11:22:04"}


def test_unknown_bdaddr_returns_no_match(run_tme):
    """A BDADDR not in the test DB should still exit 0 and render no devices."""
    result = run_tme("--bdaddr", "FE:DC:BA:99:88:77")
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    assert rendered_bdaddrs(result.stdout) == set()
