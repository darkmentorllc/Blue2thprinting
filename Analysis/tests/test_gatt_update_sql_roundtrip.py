"""Notification and indication bytes survive BTIDES import and TME rendering."""

import json
import subprocess
import sys
from pathlib import Path


ANALYSIS = Path(__file__).resolve().parents[1]
BDADDR = "02:66:77:88:99:aa"
NOTIFICATION = "00ff41420a"
INDICATION = "494e4400fe"


def test_gatt_updates_round_trip_through_sql_and_tme(db_clean, run_tme, tmp_path):
    btides = [{
        "bdaddr": BDADDR,
        "bdaddr_rand": 1,
        "GATTArray": [{
            "utype": "2800",
            "begin_handle": 1,
            "end_handle": 5,
            "UUID": "6e400001b5a3f393e0a9e50e24dcca9e",
            "characteristics": [{
                "handle": 2,
                "properties": 0x30,
                "value_handle": 3,
                "value_uuid": "6e400003b5a3f393e0a9e50e24dcca9e",
                "char_value": {
                    "handle": 3,
                    "value_uuid": "6e400003b5a3f393e0a9e50e24dcca9e",
                    "io_array": [
                        {"io_type": 27, "value_hex_str": NOTIFICATION},
                        {"io_type": 29, "value_hex_str": INDICATION},
                    ],
                },
            }],
        }],
    }]
    path = tmp_path / "gatt-updates.btides.json"
    path.write_text(json.dumps(btides))

    subprocess.run(
        [sys.executable, "BTIDES_to_SQL.py", "--input", str(path),
         "--use-test-db", "--quiet-print"],
        cwd=ANALYSIS, check=True, capture_output=True, text=True,
    )

    result = subprocess.run(
        ["mysql", "-u", "user", "-pa", "-D", "bttest", "--batch",
         "--skip-column-names", "-e",
         "SELECT operation, HEX(byte_values) FROM GATT_characteristics_values "
         f"WHERE bdaddr = '{BDADDR}' AND bdaddr_random = 1 "
         "AND char_value_handle = 3 ORDER BY operation"],
        check=True, capture_output=True, text=True,
    )
    assert result.stdout.splitlines() == [
        f"27\t{NOTIFICATION.upper()}", f"29\t{INDICATION.upper()}"
    ]

    rendered = run_tme("--bdaddr", BDADDR, "--bdaddr-type", "1").stdout
    tx = rendered.index(
        "Characteristic Value UUID: 6e400003-b5a3-f393-e0a9-e50e24dcca9e")
    notification = rendered.index("          Notification raw hex: " + NOTIFICATION, tx)
    indication = rendered.index("          Indication raw hex: " + INDICATION, tx)
    assert notification < indication
    assert "            Speculative ASCII: \\x00\\xffAB\\n" in rendered
    assert "            Speculative ASCII: IND\\x00\\xfe" in rendered

    exported_path = tmp_path / "gatt-updates-export.btides.json"
    run_tme("--bdaddr", BDADDR, "--bdaddr-type", "1",
            "--output", str(exported_path), "--quiet-print")
    exported = json.loads(exported_path.read_text())
    values = [entry for device in exported for service in device.get("GATTArray", [])
              for characteristic in service.get("characteristics", [])
              for entry in characteristic.get("char_value", {}).get("io_array", [])]
    assert {(entry["io_type"], entry["value_hex_str"]) for entry in values} == {
        (27, NOTIFICATION), (29, INDICATION),
    }


def _import(btides, tmp_path, name):
    path = tmp_path / name
    path.write_text(json.dumps(btides))
    subprocess.run(
        [sys.executable, "BTIDES_to_SQL.py", "--input", str(path),
         "--use-test-db", "--quiet-print"],
        cwd=ANALYSIS, check=True, capture_output=True, text=True,
    )


def _rows(bdaddr):
    return subprocess.run(
        ["mysql", "-u", "user", "-pa", "-D", "bttest", "--batch",
         "--skip-column-names", "-e",
         "SELECT char_value_handle, operation, HEX(byte_values) FROM GATT_characteristics_values "
         f"WHERE bdaddr = '{bdaddr}' AND bdaddr_random = 1 ORDER BY char_value_handle, operation"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()


def test_updates_on_undiscovered_handles_are_stored_and_shown(db_clean, run_tme, tmp_path):
    """Seen on pi0-2 (2026-11-17): a peer indicated Service Changed right after
    the link came up and the link dropped before characteristic discovery, so
    the update was only in ATTArray. It must still reach SQL and TME, both
    inside a service whose range is known and with no service known at all."""
    in_service, no_service = "02:66:77:88:99:ab", "02:66:77:88:99:ac"
    updates = [
        {"direction": 1, "opcode": 29, "attribute_handle": 3, "value_hex_str": "0000ffff"},
        {"direction": 1, "opcode": 27, "attribute_handle": 3, "value_hex_str": "4869"},
    ]
    _import([{"bdaddr": in_service, "bdaddr_rand": 1, "ATTArray": updates,
              "GATTArray": [{"utype": "2800", "begin_handle": 1, "end_handle": 4, "UUID": "1801"}]},
             {"bdaddr": no_service, "bdaddr_rand": 1, "ATTArray": updates}],
            tmp_path, "att-only-updates.btides.json")

    for bdaddr in (in_service, no_service):
        assert _rows(bdaddr) == ["3\t27\t4869", "3\t29\t0000FFFF"]
        rendered = run_tme("--bdaddr", bdaddr, "--bdaddr-type", "1").stdout
        assert "Indication raw hex: 0000ffff" in rendered, rendered
        assert "Notification raw hex: 4869" in rendered, rendered
    # With no service range known, the values are listed under the unmatched handles.
    rendered = run_tme("--bdaddr", no_service, "--bdaddr-type", "1").stdout
    assert rendered.index("GATT Service Unknown!") < rendered.index("Indication raw hex: 0000ffff")


def test_update_both_nested_and_in_attarray_is_stored_once(db_clean, tmp_path):
    """The converters put an update on a known characteristic in both places."""
    bdaddr = "02:66:77:88:99:ad"
    _import([{
        "bdaddr": bdaddr, "bdaddr_rand": 1,
        "ATTArray": [{"direction": 1, "opcode": 27, "attribute_handle": 3, "value_hex_str": NOTIFICATION}],
        "GATTArray": [{"utype": "2800", "begin_handle": 1, "end_handle": 5, "UUID": "180f",
                       "characteristics": [{"handle": 2, "properties": 0x12, "value_handle": 3,
                                            "value_uuid": "2a19",
                                            "char_value": {"handle": 3, "value_uuid": "2a19",
                                                           "io_array": [{"io_type": 27, "value_hex_str": NOTIFICATION}]}}]}],
    }], tmp_path, "nested-and-raw.btides.json")
    assert _rows(bdaddr) == [f"3\t27\t{NOTIFICATION.upper()}"]
