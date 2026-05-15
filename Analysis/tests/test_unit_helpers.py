########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
########################################

"""Pure-Python unit tests that don't need MySQL or subprocess invocation."""

import argparse
import json
import os
import shutil
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


class TestWriteBTIDESVersionGate:
    """write_BTIDES() refuses to export when the on-disk BTIDES_base.json
    advertises a schema version older than what the code requires.
    """

    @staticmethod
    def _stage_schema_dir(dst_root: Path, src_schema_dir: Path, version: str):
        """Copy the real BTIDES_Schema/ to dst_root/BTIDES_Schema/ with
        BTIDES_base.json's "version" field rewritten to `version`.
        """
        dst_schema = dst_root / "BTIDES_Schema"
        dst_schema.mkdir()
        for src in src_schema_dir.glob("BTIDES_*.json"):
            shutil.copy(src, dst_schema / src.name)
        base = dst_schema / "BTIDES_base.json"
        data = json.loads(base.read_text())
        data["version"] = version
        base.write_text(json.dumps(data))
        return dst_schema

    def test_rejects_older_schema(self, tmp_path, schema_dir, monkeypatch):
        staged = self._stage_schema_dir(tmp_path, schema_dir, "0.4.9")

        # write_BTIDES reads schemas from the absolute _BTIDES_SCHEMA_DIR
        # constant (resolved relative to TME_BTIDES_base.py), not cwd, so
        # monkeypatch that constant to the staged directory.
        import TME.TME_glob
        import TME.TME_BTIDES_base
        monkeypatch.setattr(TME.TME_BTIDES_base, "_BTIDES_SCHEMA_DIR", str(staged))

        TME.TME_glob.BTIDES_JSON = [{"bdaddr": "aa:bb:cc:dd:ee:ff", "bdaddr_rand": 0}]
        with pytest.raises(ValueError, match="0.4.9.*less than.*0.5.0"):
            TME.TME_BTIDES_base.write_BTIDES(str(tmp_path / "out.btides"))

    def test_accepts_current_schema(self, tmp_path, schema_dir, monkeypatch):
        """Sanity-check: the same staging path with the real version passes."""
        real_version = json.loads((schema_dir / "BTIDES_base.json").read_text())["version"]
        staged = self._stage_schema_dir(tmp_path, schema_dir, real_version)

        import TME.TME_glob
        import TME.TME_BTIDES_base
        monkeypatch.setattr(TME.TME_BTIDES_base, "_BTIDES_SCHEMA_DIR", str(staged))

        TME.TME_glob.BTIDES_JSON = [{"bdaddr": "aa:bb:cc:dd:ee:ff", "bdaddr_rand": 0}]
        TME.TME_BTIDES_base.write_BTIDES(str(tmp_path / "out.btides"))  # must not raise
        assert (tmp_path / "out.btides").exists()
