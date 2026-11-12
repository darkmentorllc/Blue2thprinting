"""NamePrint matches with unknown device use still invite identification."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from TME import TME_glob, TME_helpers  # noqa: E402


SUBMISSION_URL = "https://forms.gle/T6GwPs5NqDTxxzK36"


@pytest.mark.parametrize(
    ("name", "nameprints", "matched", "no_match", "prompt"),
    [
        (
            "PebbleBee",
            {"^PebbleBee$": "Device type/usage unknown. (APK com.pebblebee.app.hive3)"},
            True, False, True,
        ),
        (
            "PebbleBee",
            {"^PebbleBee$": "Bluetooth item finder (APK com.pebblebee.app.hive3)."},
            True, False, False,
        ),
        (
            "PebbleBee",
            {"^PebbleBee$": "Device type/usage unknown. (APK com.pebblebee.app.hive3)",
             "^Pebble.*$": "Bluetooth item finder."},
            True, False, True,
        ),
        ("Unidentified", {"^PebbleBee$": "Bluetooth item finder."}, False, True, True),
        ("", {"^PebbleBee$": "Bluetooth item finder."}, False, False, False),
    ],
)
def test_unknown_device_use_prompts_for_nameprint(
    monkeypatch, name, nameprints, matched, no_match, prompt
):
    output = []
    monkeypatch.setattr(TME_glob, "full_nameprint_data", nameprints)
    monkeypatch.setattr(TME_helpers, "qprint", output.append)

    TME_helpers.find_nameprint_match(name)

    assert any("NamePrint: match found" in line for line in output) is matched
    assert any("NamePrint: no match found" in line for line in output) is no_match
    assert sum(SUBMISSION_URL in line for line in output) == int(prompt)
