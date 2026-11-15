"""TME renders received binary updates beneath their characteristic."""

import sys
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALYSIS))

from TME import TME_GATT as gatt  # noqa: E402


def test_group_keeps_distinct_updates_and_operations():
    rows = [(1, 0x12, 27, b'Hello'), (1, 0x12, 27, b'World'),
            (1, 0x12, 29, b'\x00\xff')]
    assert gatt.group_characteristic_values(rows) == {
        (0x12, 27): [b'Hello', b'World'], (0x12, 29): [b'\x00\xff']}


def test_raw_hex_and_speculative_ascii_have_nested_indentation(monkeypatch):
    lines = []
    monkeypatch.setattr(gatt, 'qprint', lines.append)
    gatt.print_characteristic_update(gatt.i5, 27, b'Hello World!\n')
    gatt.print_characteristic_update(gatt.i5, 29, b'A\x00\xff\\')
    assert lines == [
        gatt.i5 + 'Notification raw hex: 48656c6c6f20576f726c64210a',
        gatt.i5 + gatt.i1 + gatt.string_magenta_bright('Speculative ASCII: Hello World!\\n'),
        gatt.i5 + 'Indication raw hex: 4100ff5c',
        gatt.i5 + gatt.i1 + gatt.string_magenta_bright('Speculative ASCII: A\\x00\\xff\\\\'),
    ]
