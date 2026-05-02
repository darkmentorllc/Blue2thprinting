########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Pure-Python unit tests that don't need MySQL or subprocess invocation."""

import argparse
import json
import sys
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ANALYSIS_DIR))

from Tell_Me_Everything import validate_bdaddr  # noqa: E402


class TestValidateBdaddr:
    @pytest.mark.parametrize("bdaddr", [
        "AA:BB:CC:11:22:33",
        "aa:bb:cc:11:22:33",
        "00:00:00:00:00:00",
        "FF:FF:FF:FF:FF:FF",
        "12:34:56:78:9A:bC",
    ])
    def test_accepts_valid(self, bdaddr):
        assert validate_bdaddr(bdaddr) == bdaddr

    @pytest.mark.parametrize("bad", [
        "",
        "AA:BB:CC:11:22",                 # too short
        "AA:BB:CC:11:22:33:44",           # too long
        "AA-BB-CC-11-22-33",              # wrong separator
        "AABBCC112233",                    # no separators
        "ZZ:BB:CC:11:22:33",              # non-hex
        "AA:BB:CC:11:22:3",                # last octet 1 char
    ])
    def test_rejects_invalid(self, bad):
        with pytest.raises(argparse.ArgumentTypeError):
            validate_bdaddr(bad)


class TestBTIDESSchemas:
    """The BTIDES_Schema/ directory ships JSON Schemas that the export path
    validates against. Just confirm they parse and look like JSON Schema.
    """

    def test_all_schemas_parse(self, schema_dir):
        schemas = list(schema_dir.glob("BTIDES_*.json"))
        assert len(schemas) >= 10, f"Expected ~12 BTIDES schemas, found {len(schemas)}"
        for schema_path in schemas:
            with open(schema_path) as f:
                data = json.load(f)
            assert "$schema" in data or "type" in data or "$ref" in data or "$defs" in data, \
                f"{schema_path.name} doesn't look like a JSON Schema"

    def test_base_schema_present(self, schema_dir):
        base = schema_dir / "BTIDES_base.json"
        assert base.exists(), "BTIDES_base.json is the root schema; it must exist"
