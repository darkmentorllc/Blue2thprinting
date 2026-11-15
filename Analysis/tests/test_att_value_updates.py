"""ATT updates preserve binary values in raw ATT and nested GATT output."""

import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ANALYSIS / "scapy"))
sys.path.insert(0, str(ANALYSIS))

from scapy.layers.bluetooth import (  # noqa: E402
    ATT_Hdr, ATT_Handle_Value_Notification, ATT_Handle_Value_Indication,
    ATT_Write_Request, ATT_Read_By_Type_Request,
)
import TME.TME_glob as glob  # noqa: E402
from TME.TME_AdvChan import ff_CONNECT_IND_placeholder  # noqa: E402
from TME.TME_BTIDES_base import write_BTIDES  # noqa: E402
from scapy_to_BTIDES_common import (  # noqa: E402
    export_ATT_Attribute_Value_Change, export_ATT_Write_Value,
    export_ATT_Read_By_Type_Request,
)


@pytest.fixture(autouse=True)
def empty_output():
    glob.BTIDES_JSON = []
    glob.BTIDES_JSON_by_bdaddr_key.clear()
    glob.verbose_BTIDES = False
    yield
    glob.BTIDES_JSON = []
    glob.BTIDES_JSON_by_bdaddr_key.clear()


def fixture_with_characteristic(ci):
    glob.BTIDES_JSON.append({"CONNECT_IND": ci, "GATTArray": [{
        "utype": "2800", "begin_handle": 1, "end_handle": 20, "UUID": "1800",
        "characteristics": [{"handle": 3, "properties": 48, "value_handle": 4,
                             "value_uuid": "2a00"}],
    }]})


def test_notification_and_indication_nest_under_known_characteristic():
    ci = ff_CONNECT_IND_placeholder()
    fixture_with_characteristic(ci)
    p1 = ATT_Hdr(opcode=0x1b) / ATT_Handle_Value_Notification(gatt_handle=4, value=b'Hi\x00\xff')
    p2 = ATT_Hdr(opcode=0x1d) / ATT_Handle_Value_Indication(gatt_handle=4, value=b'Bye')
    assert export_ATT_Attribute_Value_Change(ci, p1, direction=1)
    assert export_ATT_Attribute_Value_Change(ci, p2, direction=1)
    base = glob.BTIDES_JSON[0]
    assert [(e["opcode"], e["attribute_handle"], e["value_hex_str"])
            for e in base["ATTArray"]] == [(27, 4, "486900ff"), (29, 4, "427965")]
    assert base["GATTArray"][0]["characteristics"][0]["char_value"]["io_array"] == [
        {"io_type": 27, "value_hex_str": "486900ff"},
        {"io_type": 29, "value_hex_str": "427965"},
    ]


def test_unknown_handle_still_has_att_and_placeholder_gatt():
    ci = ff_CONNECT_IND_placeholder()
    packet = ATT_Hdr(opcode=0x1b) / ATT_Handle_Value_Notification(gatt_handle=9, value=b'\x00\xff')
    assert export_ATT_Attribute_Value_Change(ci, packet, direction=1)
    base = glob.BTIDES_JSON[0]
    assert base["ATTArray"][0]["value_hex_str"] == "00ff"
    assert base["GATTArray"][0]["characteristics"][0]["char_value"]["io_array"][0] == {
        "io_type": 27, "value_hex_str": "00ff"}


def test_rx_write_is_recorded_at_characteristic_value():
    ci = ff_CONNECT_IND_placeholder()
    fixture_with_characteristic(ci)
    packet = ATT_Hdr(opcode=0x12) / ATT_Write_Request(gatt_handle=4, data=b'0123456789')
    assert export_ATT_Write_Value(ci, packet, direction=0)
    base = glob.BTIDES_JSON[0]
    assert base["ATTArray"][0]["value_hex_str"] == "30313233343536373839"
    assert base["GATTArray"][0]["characteristics"][0]["char_value"]["io_array"][0] == {
        "io_type": 18, "value_hex_str": "30313233343536373839"}


def test_read_by_type_uuid_uses_schema_hex_string():
    ci = ff_CONNECT_IND_placeholder()
    packet = ATT_Hdr(opcode=8) / ATT_Read_By_Type_Request(start=1, end=0xffff, uuid=0x2803)
    assert export_ATT_Read_By_Type_Request(ci, packet, direction=0)
    assert glob.BTIDES_JSON[0]["ATTArray"][0]["attribute_uuid"] == "2803"


def test_read_response_value_without_handle_validates(tmp_path):
    # ATT_READ_RSP has no handle on the wire; its value is associated with
    # the preceding request. The schema must accept that representation.
    glob.BTIDES_JSON.append({"CONNECT_IND": ff_CONNECT_IND_placeholder(),
                             "ATTArray": [{"direction": 1, "opcode": 11,
                                           "value_hex_str": "00ff"}]})
    output = tmp_path / "read-response.btides.json"
    write_BTIDES(str(output))
    assert output.exists()
