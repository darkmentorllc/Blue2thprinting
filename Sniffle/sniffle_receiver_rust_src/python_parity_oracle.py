#!/usr/bin/env python3
"""Python ground-truth oracle for advdata.rs unit tests.

Runs Sniffle's reference decoder (`sniffle.advdata.decoder.decode_adv_data`)
against a fixed corpus of synthetic payloads — every payload exercises one
Python decoder branch. The output is printed in a form ready to paste into
the Rust unit tests as the `expected` string for an `assert_eq!`.

When porting any new Python decoder type to the Rust side:
    1. Add a row to CASES below.
    2. Run: cd Sniffle/python_cli && python3 ../sniffle_receiver_rust/python_parity_oracle.py
    3. Paste the captured output into a new `#[test]` in src/advdata.rs.
"""
import os
import sys

# Make sniffle importable when run from the repo root or from this dir.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python_cli"))

from sniffle.advdata.decoder import decode_adv_data  # noqa: E402

# (name, payload) — each payload is a full LTV stream the way it would
# arrive in an ADV_IND's adv_data field. Keep this list in sync with the
# `tests` module in advdata.rs.
CASES = [
    ("flags",                      bytes([0x02, 0x01, 0x06])),
    ("complete_local_name",        bytes([0x06, 0x09, ord('U'), ord('V'), ord('P'), ord('0'), ord('1')])),
    ("shortened_local_name",       bytes([0x02, 0x08, ord('A')])),
    ("tx_power_negative",          bytes([0x02, 0x0A, 0xF8])),
    ("tx_power_positive",          bytes([0x02, 0x0A, 0x14])),
    ("service_list16_with_lookup", bytes([0x05, 0x03, 0x0A, 0x18, 0x0F, 0x18])),
    ("service_list16_unknown",     bytes([0x03, 0x03, 0xCD, 0xAB])),
    ("service_list32",             bytes([0x05, 0x05, 0x78, 0x56, 0x34, 0x12])),
    ("service_list128",            bytes([0x11, 0x07] + list(range(16)))),
    ("service_data16",             bytes([0x06, 0x16, 0x0F, 0x18, 0xAA, 0xBB, 0xCC])),
    ("service_data32",             bytes([0x08, 0x20, 0x78, 0x56, 0x34, 0x12, 0xAA, 0xBB, 0xCC])),
    ("service_data128",            bytes([0x12, 0x21] + list(range(16)) + [0xDE, 0xAD])),
    ("ibeacon",                    bytes([0x1A, 0xFF, 0x4C, 0x00, 0x02, 0x15]
                                          + [0x11] * 16
                                          + [0x01, 0x00, 0x02, 0x00, 0xC5])),
    ("airdrop_generic",            bytes([0x05, 0xFF, 0x4C, 0x00, 0x05, 0x00])),
    ("airplay_target",             bytes([0x0B, 0xFF, 0x4C, 0x00, 0x09, 0x06, 0x13, 0x98, 192, 168, 1, 165])),
    ("nearby_info",                bytes([0x07, 0xFF, 0x4C, 0x00, 0x10, 0x02, 0x07, 0x04])),
    ("apple_type01_length_implied",bytes([0x07, 0xFF, 0x4C, 0x00, 0x01, 0x02, 0x03, 0x04])),
    ("microsoft_valid",            bytes([0x1E, 0xFF, 0x06, 0x00,
                                          0x01, 0x21, 0x20, 0x44,
                                          0xEF, 0xBE, 0xAD, 0xDE]
                                          + list(range(0xA0, 0xA0 + 19)))),
    ("microsoft_invalid_short",    bytes([0x06, 0xFF, 0x06, 0x00, 0xFF, 0xFF, 0xFF])),
    ("generic_msd_unknown_company",bytes([0x06, 0xFF, 0xCD, 0xAB, 0xDE, 0xAD, 0xBE])),
    ("msd_too_short",              bytes([0x02, 0xFF, 0xCD])),
    ("zero_length_record",         bytes([0x00, 0x01, 0x06])),
    ("truncated_value",            bytes([0x05, 0x09, ord('A'), ord('B')])),
    ("unknown_type",               bytes([0x04, 0x7E, 0xAA, 0xBB, 0xCC])),
    ("multiple_records",           bytes([0x02, 0x01, 0x06,
                                          0x06, 0x09, ord('U'), ord('V'), ord('P'), ord('0'), ord('1')])),
]


def main():
    for name, payload in CASES:
        recs = decode_adv_data(payload)
        rendered = "\n".join(str(r) for r in recs)
        print(f"// === {name} ===")
        print(f"// payload ({len(payload)} bytes): {payload.hex()}")
        for line in rendered.splitlines():
            print(f"//   {line}")
        print()


if __name__ == "__main__":
    main()
