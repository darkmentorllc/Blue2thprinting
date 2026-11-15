"""HCI identity address types fit BTIDES's public/random representation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from HCI_to_BTIDES import btides_addr_random_from_hci  # noqa: E402


def test_identity_address_types_preserve_public_random_bit():
    assert [btides_addr_random_from_hci(x) for x in (0, 1, 2, 3, 255)] == [
        0, 1, 0, 1, 255]
