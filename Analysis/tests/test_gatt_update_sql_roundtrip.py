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
