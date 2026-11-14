"""Small, offline HCI capture references for each observed BTIDES output family.

The extended-advertising edge cases have separate tests in
test_hci_extended_advertising.py.  These fixtures exercise representative
legacy advertising and protocol data from real HCI records, with synthetic
QA peer identities or sanitized addresses in the newly added captures.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ANALYSIS_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REFERENCE_DIR = FIXTURES_DIR / "hci_reference"
SCHEMA_DIR = ANALYSIS_DIR / "BTIDES_Schema"
SCAPY_DIR = ANALYSIS_DIR / "scapy"

CAPTURES = {
    "legacy": FIXTURES_DIR / "import.snoop",
    "att_gatt": REFERENCE_DIR / "att_gatt_qa.snoop",
    "classic": REFERENCE_DIR / "classic_sdp_qa.snoop",
    "sdp_records": REFERENCE_DIR / "classic_sdp_records_qa.snoop",
    "sdp_continuation": REFERENCE_DIR / "classic_sdp_continuation_qa.snoop",
    "smp": REFERENCE_DIR / "smp_pairing_sanitized.snoop",
}

SCHEMA_FILES = (
    "BTIDES_base.json", "BTIDES_AdvData.json", "BTIDES_LLCP.json",
    "BTIDES_HCI.json", "BTIDES_L2CAP.json", "BTIDES_SMP.json",
    "BTIDES_ATT.json", "BTIDES_GATT.json", "BTIDES_EIR.json",
    "BTIDES_LMP.json", "BTIDES_SDP.json", "BTIDES_GPS.json",
)


@pytest.fixture(scope="module")
def validator():
    resources = []
    for name in SCHEMA_FILES:
        schema = json.loads((SCHEMA_DIR / name).read_text())
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Draft202012Validator(
        {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json"},
        registry=Registry().with_resources(resources),
    )


@pytest.fixture(scope="module")
def exported(tmp_path_factory, validator):
    """Run each reference through the standalone CLI once, then validate it."""
    assert (SCAPY_DIR / "scapy" / "__init__.py").is_file(), (
        "Initialize the pinned Analysis/scapy submodule before running HCI QA"
    )
    output_dir = tmp_path_factory.mktemp("hci_btides_reference")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SCAPY_DIR), env.get("PYTHONPATH", "")) if part
    )
    data = {}
    for name, capture in CAPTURES.items():
        assert capture.is_file(), f"Missing HCI reference: {capture}"
        output = output_dir / f"{name}.btides"
        result = subprocess.run(
            [sys.executable, "HCI_to_BTIDES.py", "--input", str(capture),
             "--output", str(output), "--quiet-print"],
            cwd=ANALYSIS_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"{name}: HCI_to_BTIDES.py exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        rows = json.loads(output.read_text())
        assert rows, f"{name}: converter returned no BTIDES rows"
        validator.validate(rows)
        data[name] = rows
    return data


def _family(rows, name):
    return [item for row in rows for item in row.get(name, [])]


def test_legacy_advertising_ll_and_eir(exported):
    rows = exported["legacy"]
    advertising = _family(rows, "AdvChanArray")
    assert {0, 2, 20} <= {item["type"] for item in advertising}
    assert any(
        ad["type"] == 1 and ad["flags_hex_str"] == "1a"
        for item in advertising for ad in item.get("AdvDataArray", [])
    )
    assert any(item["opcode"] == 9 for item in _family(rows, "LLArray"))
    assert {1, 2} <= {item["type"] for item in _family(rows, "EIRArray")}


def test_att_request_response_and_gatt_services(exported):
    rows = exported["att_gatt"]
    assert len(rows) == 1
    assert rows[0]["CONNECT_IND"]["peripheral_bdaddr"] == "f0:f1:f2:f3:a0:eb"
    att = rows[0]["ATTArray"]
    assert [(item["direction"], item["opcode"]) for item in att] == [
        (0, 16), (1, 17),
    ]
    assert [(item["attribute_handle"], item["end_group_handle"], item["UUID"])
            for item in att[1]["attribute_data_list"]] == [
        (1, 5, "1800"), (6, 13, "1801"),
    ]
    assert [(item["begin_handle"], item["end_handle"], item["UUID"])
            for item in rows[0]["GATTArray"]] == [
        (1, 5, "1800"), (6, 13, "1801"),
    ]


def test_classic_l2cap_sdp_lmp_and_remote_name(exported):
    rows = exported["classic"]
    assert len(rows) == 2
    connection = next(row for row in rows if "CONNECT_IND" in row)
    peer = next(row for row in rows if row.get("bdaddr") == "8a:88:4b:80:f2:26")
    assert connection["CONNECT_IND"]["peripheral_bdaddr"] == peer["bdaddr"]
    assert [(item["direction"], item["code"]) for item in connection["L2CAPArray"]] == [
        (0, 10), (1, 11), (0, 2), (1, 3),
    ]
    assert [(item["direction"], item["pdu_id"], item["transaction_id"])
            for item in connection["SDPArray"]] == [(0, 6, 0), (1, 7, 0)]
    assert peer["LMPArray"][0]["opcode"] == 40
    assert peer["LMPArray"][1]["extended_opcode"] == 4
    name_event, = peer["HCIArray"]
    assert name_event["event_code"] == 7
    assert bytes.fromhex(name_event["remote_name_hex_str"]) == b"DMBT-SDP-QA"


def test_real_sdp_records_and_continuations(exported):
    records, = exported["sdp_records"]
    assert records["CONNECT_IND"]["peripheral_bdaddr"] == "f0:f1:f2:f3:a0:ef"
    responses = [item for item in records["SDPArray"] if item["pdu_id"] == 7]
    assert [item["l2cap_cid"] for item in responses] == [81, 82, 82, 83]
    assert [len(bytes.fromhex(item["raw_data_hex_str"])) for item in responses] == [79, 316, 5, 48]

    continued, = exported["sdp_continuation"]
    assert continued["CONNECT_IND"]["peripheral_bdaddr"] == "f0:f1:f2:f3:a0:f0"
    responses = [item for item in continued["SDPArray"] if item["pdu_id"] == 7]
    assert len(responses) == 11
    assert [item["transaction_id"] for item in responses] == list(range(10)) + [0]
    assert [item["raw_data_hex_str"][-6:] for item in responses[:2]] == ["02013b", "020115"]
    assert len([item for item in continued["SDPArray"] if item["pdu_id"] == 5]) == 8


def test_smp_pairing_request_and_response(exported):
    rows = exported["smp"]
    assert len(rows) == 1
    assert rows[0]["CONNECT_IND"]["peripheral_bdaddr"] == "f0:f1:f2:f3:a0:ee"
    assert [(item["direction"], item["opcode"], item["auth_req"])
            for item in rows[0]["SMPArray"]] == [(0, 1, 45), (1, 2, 45)]
    assert all(item["max_key_size"] == 16 for item in rows[0]["SMPArray"])
