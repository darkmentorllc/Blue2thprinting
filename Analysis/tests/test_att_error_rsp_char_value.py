########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Regression test for the CharacteristicValue built from an ATT_ERROR_RSP.

When an ATT_READ_REQ fails, export_ATT_Error_Response() attaches a
"char_value" (with the error in its io_array) to the matching
Characteristic. That object must use the schema's "handle" key (not
"value_handle"): BTIDES_GATT.json requires "handle" on
CharacteristicValue, and BTIDES_to_SQL reads char_value["handle"].
"""

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ANALYSIS_DIR))

from scapy.layers.bluetooth import ATT_Hdr, ATT_Error_Response, L2CAP_Hdr  # noqa: E402
from scapy.layers.bluetooth4LE import BTLE, BTLE_DATA  # noqa: E402

import TME.TME_glob  # noqa: E402
from TME.TME_AdvChan import ff_CONNECT_IND_placeholder  # noqa: E402
from TME.TME_BTIDES_GATT import (  # noqa: E402
    BTIDES_export_GATT_Characteristic,
    BTIDES_export_GATT_Service,
    ff_GATT_Characteristic,
    ff_GATT_Service,
)
from TME.BTIDES_Data_Types import type_BTIDES_direction_P2C  # noqa: E402
from TME.BT_Data_Types import type_ATT_ERROR_RSP, type_ATT_READ_REQ  # noqa: E402
from scapy_to_BTIDES_common import export_ATT_Error_Response  # noqa: E402

CHAR_DECL_HANDLE = 0x0002
CHAR_VALUE_HANDLE = 0x0003
ATT_ERR_READ_NOT_PERMITTED = 0x02


@pytest.fixture(scope="module")
def btides_validator(schema_dir):
    resources = []
    for path in sorted(schema_dir.glob("BTIDES_*.json")):
        with open(path) as f:
            s = json.load(f)
        if "$id" in s:
            resources.append((s["$id"], Resource.from_contents(s)))
    return Draft202012Validator(
        {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json"},
        registry=Registry().with_resources(resources),
    )


@pytest.fixture(params=[False, True], ids=["terse", "verbose"])
def fresh_btides(request, monkeypatch):
    monkeypatch.setattr(TME.TME_glob, "BTIDES_JSON", [])
    monkeypatch.setattr(TME.TME_glob, "verbose_BTIDES", request.param)
    return TME.TME_glob


def _export_char_then_failed_read(connect_ind_obj):
    BTIDES_export_GATT_Service(connect_ind_obj=connect_ind_obj, data=ff_GATT_Service({
        "utype": "2800", "begin_handle": 0x0001, "end_handle": 0x0005, "UUID": "1800",
    }))
    BTIDES_export_GATT_Characteristic(connect_ind_obj=connect_ind_obj, data=ff_GATT_Characteristic({
        "handle": CHAR_DECL_HANDLE,
        "properties": 0x02,
        "value_handle": CHAR_VALUE_HANDLE,
        "value_uuid": "2a00",
    }))
    packet = (BTLE() / BTLE_DATA() / L2CAP_Hdr(cid=4) / ATT_Hdr() /
              ATT_Error_Response(request=type_ATT_READ_REQ,
                                 handle=CHAR_VALUE_HANDLE,
                                 ecode=ATT_ERR_READ_NOT_PERMITTED))
    assert export_ATT_Error_Response(connect_ind_obj, packet, direction=type_BTIDES_direction_P2C)


def _only_characteristic(btides_json):
    chars = [c for entry in btides_json
             for svc in entry.get("GATTArray", [])
             for c in svc.get("characteristics", [])]
    assert len(chars) == 1
    return chars[0]


def test_char_value_uses_handle_key(fresh_btides):
    _export_char_then_failed_read(ff_CONNECT_IND_placeholder())

    char_value = _only_characteristic(fresh_btides.BTIDES_JSON)["char_value"]
    assert char_value["handle"] == CHAR_VALUE_HANDLE
    assert "value_handle" not in char_value
    assert char_value["value_uuid"] == "2a00"
    assert char_value["io_array"][0]["io_type"] == type_ATT_ERROR_RSP
    assert char_value["io_array"][0]["value_hex_str"] == f"{ATT_ERR_READ_NOT_PERMITTED:02x}"


def test_char_value_validates_against_schema(fresh_btides, btides_validator):
    _export_char_then_failed_read(ff_CONNECT_IND_placeholder())

    errors = list(btides_validator.iter_errors(fresh_btides.BTIDES_JSON))
    assert not errors, "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
