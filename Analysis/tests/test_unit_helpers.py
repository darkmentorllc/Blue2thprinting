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

# clues_io ships in the CLUES_Schema submodule and is the canonical
# loader for both single-file and 16-shard hex-split CLUES layouts.
# TME_import imports it the same way (via sys.path), so mirror that
# pattern here for the unit tests.
sys.path.insert(0, str(ANALYSIS_DIR / "CLUES_Schema" / "scripts"))
from clues_io import clues_exists, load_clues, save_clues  # noqa: E402


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


# Small valid-shape CLUES entries used to exercise the loader. The
# loader itself only cares about UUID + optional "regex" key; the other
# fields are present so the records look like real CLUES data and so
# they survive any future per-field validation we might add to load.
def _entry(uuid, *, company="Test Co", regex=False):
    e = {
        "UUID": uuid,
        "company": company,
        "UUID_name": "Unknown",
        "UUID_purpose": "test fixture",
        "UUID_usage_array": ["GATT Service"],
        "evidence_array": [{"URL": "https://example.test", "submitter": "test"}],
    }
    if regex:
        e["regex"] = True
    return e


# UUIDs chosen so the 32-char (dashes-stripped) keys start with distinct
# hex digits — that way split-form tests verify entries actually land in
# the correct hex bucket.
_UUID_BUCKET_0 = "00001111-2222-3333-4444-555566667777"  # bucket '0'
_UUID_BUCKET_5 = "50001111-2222-3333-4444-555566667777"  # bucket '5'
_UUID_BUCKET_A = "a0001111-2222-3333-4444-555566667777"  # bucket 'a'
_UUID_BUCKET_F = "f0001111-2222-3333-4444-555566667777"  # bucket 'f'


class TestCluesIo:
    """clues_io.{load_clues,save_clues,clues_exists} are the canonical
    helpers for the two on-disk CLUES layouts. These tests exercise the
    helpers directly so the contract TME relies on is pinned by tests
    that live in this repo, not just in the CLUES_Schema submodule.
    """

    def test_load_single_file(self, tmp_path):
        path = tmp_path / "CLUES_data_test.json"
        entries = [_entry(_UUID_BUCKET_0), _entry(_UUID_BUCKET_A)]
        save_clues(entries, str(path), split=False)
        assert path.exists(), "single-file save should produce the combined file"
        loaded = load_clues(str(path))
        assert loaded == entries

    def test_load_split_files(self, tmp_path):
        """save_clues(split=True) writes 16 hex shards; load_clues merges
        them back. Verifies records land in the correct hex bucket and
        the single combined file is NOT created."""
        path = tmp_path / "CLUES_data_test.json"
        entries = [
            _entry(_UUID_BUCKET_0),
            _entry(_UUID_BUCKET_5),
            _entry(_UUID_BUCKET_A),
            _entry(_UUID_BUCKET_F),
        ]
        save_clues(entries, str(path), split=True)
        assert not path.exists(), "split-form save must not also write a combined file"
        for digit in "0123456789abcdef":
            shard = tmp_path / f"CLUES_data_test_{digit}.json"
            assert shard.exists(), f"shard {shard.name} should be created"
        # Each record landed in the bucket matching its first hex char.
        for digit, uuid in [("0", _UUID_BUCKET_0), ("5", _UUID_BUCKET_5),
                            ("a", _UUID_BUCKET_A), ("f", _UUID_BUCKET_F)]:
            shard_data = json.loads((tmp_path / f"CLUES_data_test_{digit}.json").read_text())
            assert [e["UUID"] for e in shard_data] == [uuid]
        loaded = load_clues(str(path))
        assert sorted(e["UUID"] for e in loaded) == sorted(e["UUID"] for e in entries)

    def test_load_missing_returns_empty(self, tmp_path):
        loaded = load_clues(str(tmp_path / "does_not_exist.json"))
        assert loaded == []

    def test_clues_exists_single(self, tmp_path):
        path = tmp_path / "CLUES_data_test.json"
        path.write_text("[]")
        assert clues_exists(str(path)) is True

    def test_clues_exists_split_only(self, tmp_path):
        """clues_exists must report True when the logical path is absent
        but at least one hex shard is present — this is the post-split
        on-disk state that TME_import must transparently handle."""
        path = tmp_path / "CLUES_data_test.json"
        (tmp_path / "CLUES_data_test_3.json").write_text("[]")
        assert not path.exists()
        assert clues_exists(str(path)) is True

    def test_clues_exists_neither(self, tmp_path):
        assert clues_exists(str(tmp_path / "nope.json")) is False

    def test_save_split_then_resave_preserves_layout(self, tmp_path):
        """save_clues(split=None) — the default in code paths that aren't
        SortCLUES — must preserve whatever layout is already on disk. If
        the existing layout is hex-split, the rewrite stays hex-split."""
        path = tmp_path / "CLUES_data_test.json"
        save_clues([_entry(_UUID_BUCKET_A)], str(path), split=True)
        save_clues([_entry(_UUID_BUCKET_F)], str(path))  # split=None default
        assert not path.exists(), "default save must not collapse split back to single"
        assert (tmp_path / "CLUES_data_test_f.json").exists()
        loaded = load_clues(str(path))
        assert [e["UUID"] for e in loaded] == [_UUID_BUCKET_F]


class TestTMECluesLoading:
    """TME_import._load_clues_file is the seam between CLUES_Schema's
    on-disk layout and TME's in-memory clue dicts. These tests pin the
    behavior under both single-file and 16-shard hex-split layouts,
    plus the required-file-missing error path.
    """

    @pytest.fixture
    def fresh_clues(self, monkeypatch):
        """Snapshot-and-restore TME.TME_glob.clues / clues_regexed so each
        test starts with empty dicts and doesn't leak entries into other
        tests. Returns (clues, clues_regexed) for direct assertions."""
        import TME.TME_glob
        clues = {}
        clues_regexed = {}
        monkeypatch.setattr(TME.TME_glob, "clues", clues)
        monkeypatch.setattr(TME.TME_glob, "clues_regexed", clues_regexed)
        return clues, clues_regexed

    def test_loads_single_file(self, tmp_path, fresh_clues):
        clues, _ = fresh_clues
        path = tmp_path / "CLUES_data_single.json"
        save_clues([_entry(_UUID_BUCKET_A, company="Acme")], str(path), split=False)

        from TME.TME_import import _load_clues_file
        _load_clues_file(str(path), required=False)

        key = _UUID_BUCKET_A.replace("-", "")
        assert key in clues, "single-file path should populate TME_glob.clues"
        assert clues[key]["company"] == "Acme"

    def test_loads_split_files(self, tmp_path, fresh_clues):
        """The post-split state: the logical .json path does NOT exist on
        disk, only the 16 hex shards do. _load_clues_file must still
        populate TME_glob.clues from the shards."""
        clues, _ = fresh_clues
        path = tmp_path / "CLUES_data_split.json"
        entries = [
            _entry(_UUID_BUCKET_0, company="Co0"),
            _entry(_UUID_BUCKET_5, company="Co5"),
            _entry(_UUID_BUCKET_A, company="CoA"),
            _entry(_UUID_BUCKET_F, company="CoF"),
        ]
        save_clues(entries, str(path), split=True)
        assert not path.exists(), "precondition: logical path absent in split form"

        from TME.TME_import import _load_clues_file
        _load_clues_file(str(path), required=False)

        for uuid, company in [(_UUID_BUCKET_0, "Co0"), (_UUID_BUCKET_5, "Co5"),
                              (_UUID_BUCKET_A, "CoA"), (_UUID_BUCKET_F, "CoF")]:
            key = uuid.replace("-", "")
            assert key in clues, f"entry in shard for {uuid!r} should load"
            assert clues[key]["company"] == company

    def test_required_missing_raises(self, tmp_path, fresh_clues):
        """When the file is required and neither the combined .json nor
        any hex shard exists, _load_clues_file must raise so the canonical
        CLUES_data_human_verified.json's absence isn't silently ignored."""
        from TME.TME_import import _load_clues_file
        with pytest.raises(FileNotFoundError):
            _load_clues_file(str(tmp_path / "missing.json"), required=True)

    def test_optional_missing_silent(self, tmp_path, fresh_clues):
        """Optional tiers (LLM-derived files, private overrides) must
        return silently when neither layout exists on disk."""
        clues, _ = fresh_clues
        from TME.TME_import import _load_clues_file
        _load_clues_file(str(tmp_path / "missing.json"), required=False)
        assert clues == {}

    def test_strips_dashes_from_uuid(self, tmp_path, fresh_clues):
        """TME uses dashes-stripped 32-char UUID keys internally for O(1)
        lookups. The loader is the place where dashes get normalized
        away, regardless of which on-disk layout supplied the entry."""
        clues, _ = fresh_clues
        path = tmp_path / "CLUES_data_dashes.json"
        save_clues([_entry(_UUID_BUCKET_A)], str(path), split=True)

        from TME.TME_import import _load_clues_file
        _load_clues_file(str(path), required=False)

        dashed_key = _UUID_BUCKET_A
        stripped_key = _UUID_BUCKET_A.replace("-", "")
        assert dashed_key not in clues, "dashed UUID should NOT appear as a key"
        assert stripped_key in clues, "stripped 32-char UUID should be the key"

    def test_regex_entries_added_to_regexed(self, tmp_path, fresh_clues):
        """Entries with the 'regex' field land in BOTH clues and
        clues_regexed (TME does a regex-aware lookup pass against the
        latter for entries whose UUID is itself a pattern)."""
        clues, clues_regexed = fresh_clues
        path = tmp_path / "CLUES_data_regex.json"
        save_clues(
            [_entry(_UUID_BUCKET_0), _entry(_UUID_BUCKET_F, regex=True)],
            str(path),
            split=True,
        )

        from TME.TME_import import _load_clues_file
        _load_clues_file(str(path), required=False)

        plain_key = _UUID_BUCKET_0.replace("-", "")
        regex_key = _UUID_BUCKET_F.replace("-", "")
        assert plain_key in clues and plain_key not in clues_regexed
        assert regex_key in clues and regex_key in clues_regexed
