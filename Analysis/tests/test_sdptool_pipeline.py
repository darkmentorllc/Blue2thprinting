"""sdptool XML preservation through BTIDES, SQL, and TME."""

import json
import subprocess
import sys
from pathlib import Path


ANALYSIS_DIR = Path(__file__).resolve().parents[1]
PEER = "f0:f1:f2:f3:a0:f1"


def test_sdptool_xml_to_sql_without_output_file(db_clean, run_tme, tmp_path):
    capture = tmp_path / f"{PEER}_sdp.xml"
    capture.write_bytes(
        b'Failed to connect to SDP server: Host is down\n'
        b'<?xml version="1.0" encoding="UTF-8" ?>\n'
        b'<record>'
        b'<attribute id="0x0000"><uint32 value="0x00010001" /></attribute>'
        b'<attribute id="0x0001"><sequence><uuid value="0x1124" /></sequence></attribute>'
        b'<attribute id="0x0100"><text value="QA HID" /></attribute>'
        b'<attribute id="0x0206"><text encoding="hex" value="00ff10" /></attribute>'
        b'</record>\n'
        b'<record>'
        b'<attribute id="0x0000"><uint32 value="0x00010002" /></attribute>'
        b'<attribute id="0x0100"><text value="QA URL" /></attribute>'
        b'<attribute id="0x0102"><url value="' + bytes.fromhex("fe0b01") + b'" /></attribute>'
        b'</record>\n'
    )

    imported = subprocess.run(
        [sys.executable, "SDP_to_BTIDES.py", "--input", str(capture),
         "--to-SQL", "--use-test-db", "--quiet-print"],
        cwd=ANALYSIS_DIR, capture_output=True, text=True, timeout=60,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr

    result = subprocess.run(
        ["mysql", "-u", "user", "-pa", "-D", "bttest", "--batch",
         "--skip-column-names", "-e",
         "SELECT HEX(byte_values), param_len, l2cap_len FROM SDP_Common "
         f"WHERE bdaddr = '{PEER}'"],
        check=True, capture_output=True, text=True,
    )
    row, = result.stdout.splitlines()
    payload_hex, param_len, l2cap_len = row.split("\t")
    payload = bytes.fromhex(payload_hex)
    assert len(payload) == int(param_len)
    assert len(payload) + 5 == int(l2cap_len)
    assert bytes.fromhex("250300ff10") in payload  # original binary HID bytes
    assert bytes.fromhex("4503fe0b01") in payload  # original invalid-XML URL bytes

    output = tmp_path / "from_sql.btides"
    shown = run_tme("--bdaddr", PEER, "--output", str(output))
    assert "Handle 0x00010001: \"QA HID\"" in shown.stdout
    assert "Handle 0x00010002: \"QA URL\"" in shown.stdout
    rows = json.loads(output.read_text())
    sdp, = [item for row in rows for item in row.get("SDPArray", [])]
    assert sdp["raw_data_hex_str"] == payload.hex()
