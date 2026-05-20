########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Unit tests for Better_Getter.apple_advertisement() — the -A/--skip-apple
filter that bails out when an MSD AD-type contains Apple's Company ID."""

import pytest

import Better_Getter as bg


def _make_msd_advdata(company_id_le_bytes, payload=b""):
    """Build an Advertising Data buffer with one Manufacturer Specific Data
    (AD type 0xFF) record. Length byte = 1 (type) + 2 (company id) + payload."""
    ad_len = 1 + 2 + len(payload)
    return bytes([ad_len, 0xFF]) + bytes(company_id_le_bytes) + bytes(payload)


class TestAppleAdvertisement:
    def test_apple_company_id_little_endian_4C00_detected(self, make_dpkt):
        # Wire-format encoding: 0x4C 0x00 (Apple's Company ID 0x004C
        # written little-endian — what conformant devices send).
        adv_data = _make_msd_advdata([0x4C, 0x00])
        dpkt = make_dpkt(pdutype="ADV_IND", adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is True

    def test_apple_company_id_big_endian_004C_also_detected(self, make_dpkt):
        # Some early Apple Watch firmwares put the Company ID big-endian
        # by mistake; the BG comment explicitly calls out checking both.
        adv_data = _make_msd_advdata([0x00, 0x4C])
        dpkt = make_dpkt(pdutype="ADV_IND", adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is True

    def test_non_apple_company_id_not_detected(self, make_dpkt):
        # 0x0006 = Microsoft, 0x0075 = Samsung — both should pass through.
        adv_data = _make_msd_advdata([0x06, 0x00])
        dpkt = make_dpkt(pdutype="ADV_IND", adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is False

    def test_advertisement_without_MSD_not_detected(self, make_dpkt):
        # AD type 0x09 = Complete Local Name "test" (4 bytes); no MSD record.
        adv_data = bytes([5, 0x09]) + b"test"
        dpkt = make_dpkt(pdutype="ADV_IND", adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is False

    @pytest.mark.parametrize("pdutype", ["ADV_IND", "ADV_NONCONN_IND", "SCAN_RSP", "ADV_SCAN_IND"])
    def test_all_advertising_pdutypes_eligible(self, pdutype, make_dpkt):
        adv_data = _make_msd_advdata([0x4C, 0x00])
        dpkt = make_dpkt(pdutype=pdutype, adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is True

    @pytest.mark.parametrize("pdutype", ["ADV_DIRECT_IND", "CONNECT_IND", "SCAN_REQ"])
    def test_non_advertising_pdutypes_skipped(self, pdutype, make_dpkt):
        # Apple's MSD shouldn't be parsed out of direct/connect/scan request
        # PDUs because they don't carry AdvData in the first place.
        adv_data = _make_msd_advdata([0x4C, 0x00])
        dpkt = make_dpkt(pdutype=pdutype, adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is False

    def test_short_advdata_below_msd_minimum_returns_false(self, make_dpkt):
        # AdvData minimum size for an MSD lookup is 4 bytes
        # (1 length + 1 type + 2 company id). Below that, just bail.
        adv_data = bytes([1, 0xFF, 0x4C])  # 3 bytes — truncated.
        dpkt = make_dpkt(pdutype="ADV_IND", adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is False

    def test_apple_msd_after_other_ad_records(self, make_dpkt):
        # Mixed AdvData: Flags (3 bytes) + TX power (3 bytes) + Apple MSD.
        flags_ad = bytes([2, 0x01, 0x06])
        tx_power_ad = bytes([2, 0x0A, 0x14])
        apple_msd = _make_msd_advdata([0x4C, 0x00], payload=b"\x02\x15hello")
        adv_data = flags_ad + tx_power_ad + apple_msd
        dpkt = make_dpkt(pdutype="ADV_IND", adv_data=adv_data)
        assert bg.apple_advertisement(dpkt, len(adv_data) + 2) is True
