########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for Scripts/BG/BG_Helper_Output.py — UUID byte→str
conversion, per-token row formatting, and the CSV emission path."""

import csv
from pathlib import Path

import pytest

from BG_Helper_Output import (
    append_common,
    convert_bytes_to_UUID128_str,
    store_characteristic_values_in_existing_format_expectations,
    store_characteristics_in_existing_format_expectations,
    store_descriptors_in_existing_format_expectations,
    store_services_in_existing_format_expectations,
)


# ---------------------------------------------------------------------------
# convert_bytes_to_UUID128_str
# ---------------------------------------------------------------------------
class TestConvertBytesToUUID128Str:
    def test_2_byte_uuid16_renders_as_full_base_uuid(self):
        # 0x180F (Battery Service) → 0000180f-0000-1000-8000-00805f9b34fb
        # Sniffle/ATT returns the UUID16 little-endian, so 0x0F 0x18.
        assert (
            convert_bytes_to_UUID128_str(b"\x0f\x18")
            == "0000180f-0000-1000-8000-00805f9b34fb"
        )

    def test_2_byte_uuid16_2a29_manufacturer_name(self):
        assert (
            convert_bytes_to_UUID128_str(b"\x29\x2a")
            == "00002a29-0000-1000-8000-00805f9b34fb"
        )

    def test_2_byte_uuid16_2800_primary_service(self):
        assert (
            convert_bytes_to_UUID128_str(b"\x00\x28")
            == "00002800-0000-1000-8000-00805f9b34fb"
        )

    def test_16_byte_uuid128_reversed_endianness(self):
        # The CA:FE pcap contains the vendor UUID
        #   444d0001-4865-6d6c-6f63-6b21f09fa4aa
        # which arrives over the wire little-endian: reverse the bytes.
        le_bytes = bytes.fromhex("aaa49ff0216b636f6c6d654801004d44")
        assert len(le_bytes) == 16
        assert (
            convert_bytes_to_UUID128_str(le_bytes)
            == "444d0001-4865-6d6c-6f63-6b21f09fa4aa"
        )

    def test_16_byte_uuid128_all_zeros_renders_canonical(self):
        assert (
            convert_bytes_to_UUID128_str(b"\x00" * 16)
            == "00000000-0000-0000-0000-000000000000"
        )


# ---------------------------------------------------------------------------
# append_common — adds (public|random)/bdaddr token pair
# ---------------------------------------------------------------------------
class TestAppendCommon:
    def test_public_address_emits_public_token(self, clean_globals):
        clean_globals.target_bdaddr = "aa:bb:cc:dd:ee:ff"
        clean_globals.target_bdaddr_type_public = True
        tokens = ["GATTPRINT:HANDLE_UUID"]
        append_common(tokens)
        assert tokens == ["GATTPRINT:HANDLE_UUID", "public", "aa:bb:cc:dd:ee:ff"]

    def test_random_address_emits_random_token(self, clean_globals):
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        tokens = ["GATTPRINT:SERVICE"]
        append_common(tokens)
        assert tokens == ["GATTPRINT:SERVICE", "random", "ca:fe:13:37:00:01"]


# ---------------------------------------------------------------------------
# CSV-writing store_* helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_gattprint(tmp_path, monkeypatch, clean_globals):
    """Redirect /tmp/GATTPRINT_*.csv writes into a per-test temp directory.

    BG_Helper_Output.write_to_csv() hard-codes a /tmp/ path because that's
    where the production launcher reads from; the test fixture patches the
    builtin `open` to redirect any path starting with /tmp/GATTPRINT_ into
    tmp_path. This keeps unit tests from clobbering real GATTPRINT files on
    a developer machine that also runs the launcher.
    """
    import builtins
    real_open = builtins.open
    captured = {}

    def fake_open(path, *args, **kwargs):
        if isinstance(path, str) and path.startswith("/tmp/GATTPRINT_"):
            new_path = tmp_path / Path(path).name
            captured["path"] = str(new_path)
            return real_open(str(new_path), *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    yield captured


class TestStoreFormatters:
    def test_store_services_writes_GATTPRINT_SERVICE_row(self, temp_gattprint, clean_globals):
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        store_services_in_existing_format_expectations(
            0x0001, 0x0008, "00001800-0000-1000-8000-00805f9b34fb"
        )

        rows = list(csv.reader(open(temp_gattprint["path"])))
        assert rows == [[
            "GATTPRINT:SERVICE", "random", "ca:fe:13:37:00:01",
            "0x0001", "0x0008", "00001800-0000-1000-8000-00805f9b34fb",
        ]]

    def test_store_descriptors_writes_HANDLE_UUID_row(self, temp_gattprint, clean_globals):
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        store_descriptors_in_existing_format_expectations(
            0x0003, "00002a05-0000-1000-8000-00805f9b34fb"
        )

        rows = list(csv.reader(open(temp_gattprint["path"])))
        assert rows == [[
            "GATTPRINT:HANDLE_UUID", "random", "ca:fe:13:37:00:01",
            "0x0003", "00002a05-0000-1000-8000-00805f9b34fb",
        ]]

    def test_store_characteristic_values_writes_CHAR_VALUE_row(self, temp_gattprint, clean_globals):
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        # Real value from the CA:FE pcap for handle 0x000B (Device Name) =
        # "UVP01" → ASCII 55 56 50 30 31.
        store_characteristic_values_in_existing_format_expectations(0x000B, "5556503031")

        rows = list(csv.reader(open(temp_gattprint["path"])))
        assert rows == [[
            "GATTPRINT:CHAR_VALUE", "random", "ca:fe:13:37:00:01",
            "0x000b", "5556503031",
        ]]

    def test_store_characteristics_writes_CHAR_DESC_row(self, temp_gattprint, clean_globals):
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        # Properties 0x0a = Read+Write, value handle 0x0008, UUID 0x2B2A.
        store_characteristics_in_existing_format_expectations(
            0x0007, 0x0a, 0x0008, "00002b2a-0000-1000-8000-00805f9b34fb"
        )

        rows = list(csv.reader(open(temp_gattprint["path"])))
        assert rows == [[
            "GATTPRINT:CHAR_DESC", "random", "ca:fe:13:37:00:01",
            "0x0007", "0x0a", "0x0008", "00002b2a-0000-1000-8000-00805f9b34fb",
        ]]

    def test_multiple_writes_append_to_same_file(self, temp_gattprint, clean_globals):
        clean_globals.target_bdaddr = "ca:fe:13:37:00:01"
        clean_globals.target_bdaddr_type_public = False
        store_descriptors_in_existing_format_expectations(
            0x0001, "00002800-0000-1000-8000-00805f9b34fb"
        )
        store_descriptors_in_existing_format_expectations(
            0x0002, "00002803-0000-1000-8000-00805f9b34fb"
        )

        rows = list(csv.reader(open(temp_gattprint["path"])))
        assert len(rows) == 2
        assert rows[0][3] == "0x0001"
        assert rows[1][3] == "0x0002"
