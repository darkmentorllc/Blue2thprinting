########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ANALYSIS_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SEED_SQL = FIXTURES_DIR / "seed.sql"
SCHEMA_DIR = ANALYSIS_DIR / "BTIDES_Schema"

MYSQL_USER = "user"
MYSQL_PASS = "a"
TEST_DB = "bttest"

# Tables containing device observations — wiped between sessions and re-seeded
# from seed.sql. Lookup tables (IEEE_bdaddr_to_company, UUID16_to_company,
# USB_CID_to_company, BLEScope_UUID128s) are populated by separate translator
# scripts and are intentionally NOT touched here.
DEVICE_DATA_TABLES = [
    "EIR_bdaddr_to_3d_info", "EIR_bdaddr_to_CoD", "EIR_bdaddr_to_DevID",
    "EIR_bdaddr_to_MSD", "EIR_bdaddr_to_PSRM", "EIR_bdaddr_to_URI",
    "EIR_bdaddr_to_UUID128s", "EIR_bdaddr_to_UUID16s", "EIR_bdaddr_to_UUID32s",
    "EIR_bdaddr_to_flags", "EIR_bdaddr_to_name", "EIR_bdaddr_to_tx_power",
    "GATT_attribute_handles", "GATT_characteristic_descriptor_values",
    "GATT_characteristics", "GATT_characteristics_values", "GATT_services",
    "HCI_bdaddr_to_name",
    "L2CAP_CONNECTION_PARAMETER_UPDATE_REQ", "L2CAP_CONNECTION_PARAMETER_UPDATE_RSP",
    "LE_bdaddr_to_3d_info", "LE_bdaddr_to_CoD", "LE_bdaddr_to_MSD",
    "LE_bdaddr_to_URI", "LE_bdaddr_to_UUID128_service_data",
    "LE_bdaddr_to_UUID128_service_solicit", "LE_bdaddr_to_UUID128s_list",
    "LE_bdaddr_to_UUID16_service_data", "LE_bdaddr_to_UUID16_service_solicit",
    "LE_bdaddr_to_UUID16s_list", "LE_bdaddr_to_UUID32_service_data",
    "LE_bdaddr_to_UUID32_service_solicit", "LE_bdaddr_to_UUID32s_list",
    "LE_bdaddr_to_appearance", "LE_bdaddr_to_connect_interval",
    "LE_bdaddr_to_flags", "LE_bdaddr_to_name", "LE_bdaddr_to_other_le_bdaddr",
    "LE_bdaddr_to_public_target_bdaddr", "LE_bdaddr_to_random_target_bdaddr",
    "LE_bdaddr_to_role", "LE_bdaddr_to_tx_power",
    "LL_FEATUREs", "LL_LENGTHs", "LL_PHYs", "LL_PINGs",
    "LL_UNKNOWN_RSP", "LL_VERSION_IND",
    "LMP_ACCEPTED", "LMP_ACCEPTED_EXT", "LMP_CHANNEL_CLASSIFICATION",
    "LMP_DETACH", "LMP_FEATURES_REQ", "LMP_FEATURES_REQ_EXT",
    "LMP_FEATURES_RES", "LMP_FEATURES_RES_EXT",
    "LMP_NAME_RES_defragmented", "LMP_NAME_RES_fragmented",
    "LMP_NOT_ACCEPTED", "LMP_NOT_ACCEPTED_EXT",
    "LMP_POWER_CONTROL_REQ", "LMP_POWER_CONTROL_RES",
    "LMP_PREFERRED_RATE", "LMP_VERSION_REQ", "LMP_VERSION_RES",
    "LMP_empty_opcodes",
    "SDP_Common", "SDP_ERROR_RSP", "SMP_Pairing_Req_Res",
    "bdaddr_to_GPS",
]


def _mysql(args, **kwargs):
    return subprocess.run(
        ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", *args],
        check=True, capture_output=True, text=True, **kwargs,
    )


def _truncate_device_tables():
    statements = "SET FOREIGN_KEY_CHECKS=0;\n"
    statements += "\n".join(f"TRUNCATE TABLE {t};" for t in DEVICE_DATA_TABLES)
    statements += "\nSET FOREIGN_KEY_CHECKS=1;\n"
    _mysql(["-D", TEST_DB, "-e", statements])


def _load_seed():
    with open(SEED_SQL, "rb") as f:
        subprocess.run(
            ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASS}", "-D", TEST_DB],
            check=True, stdin=f, capture_output=True,
        )


def _reset_test_db():
    _truncate_device_tables()
    _load_seed()


@pytest.fixture(scope="session")
def test_db():
    """Wipe device tables and reload seed.sql once per session."""
    if not SEED_SQL.exists():
        pytest.skip(f"seed.sql not found at {SEED_SQL}")
    _reset_test_db()
    yield


@pytest.fixture
def db_clean(test_db):
    """Per-test reset for tests that mutate the DB (e.g. BTIDES import)."""
    _reset_test_db()
    yield
    _reset_test_db()


@pytest.fixture
def run_tme(test_db):
    """Run Tell_Me_Everything.py as a subprocess against bttest.

    Always passes --use-test-db. Returns the CompletedProcess.
    """
    def _run(*args, expect_success=True, timeout=60):
        result = subprocess.run(
            [sys.executable, "Tell_Me_Everything.py", "--use-test-db", *args],
            cwd=str(ANALYSIS_DIR),
            capture_output=True, text=True, timeout=timeout,
        )
        if expect_success and result.returncode != 0:
            raise AssertionError(
                f"Tell_Me_Everything.py failed (exit {result.returncode}):\n"
                f"args: {args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result
    return _run


@pytest.fixture(scope="session")
def schema_dir():
    return SCHEMA_DIR


def pytest_collection_modifyitems(config, items):
    """Mark tests under test_btidalpool.py as 'btidalpool' so they can be
    selected/excluded with -m btidalpool / -m 'not btidalpool'.
    """
    for item in items:
        if "test_btidalpool" in item.nodeid:
            item.add_marker(pytest.mark.btidalpool)


def pytest_configure(config):
    config.addinivalue_line("markers", "btidalpool: tests that hit the live BTIDALPOOL service")
