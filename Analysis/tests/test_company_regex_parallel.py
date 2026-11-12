"""Concurrency and result-order checks for IEEE OUI company searches."""

import sys
from pathlib import Path
from threading import Barrier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import TME.TME_glob as glob  # noqa: E402
import TME.TME_lookup as lookup  # noqa: E402


def _only_oui_matches(monkeypatch, ouis):
    monkeypatch.setattr(glob, "bt_CID_to_names", {})
    monkeypatch.setattr(glob, "bt_member_UUID16s_to_names", {})
    monkeypatch.setattr(glob, "clues", {})

    def query(sql, values):
        if "FROM IEEE_bdaddr_to_company" in sql:
            return [(oui, "ParallelTestCompany") for oui in ouis]
        raise AssertionError(f"Unexpected shared-connection query: {sql[:80]}")

    monkeypatch.setattr(lookup, "execute_query", query)


def test_multiple_ouis_query_concurrently_and_merge_in_oui_order(monkeypatch):
    first, second = "00:11:22", "33:44:55"
    _only_oui_matches(monkeypatch, [first, second])
    both_workers_started = Barrier(2)

    def isolated_query(sql, values):
        assert "SELECT DISTINCT t.bdaddr" in sql
        both_workers_started.wait(timeout=5)
        if values[0] == first:
            return [("00:11:22:00:00:01",), ("shared",)]
        return [("33:44:55:00:00:02",), ("shared",)]

    monkeypatch.setattr(lookup, "execute_query_isolated", isolated_query)
    assert list(lookup.get_bdaddrs_by_company_regex("ParallelTestCompany", None)) == [
        "00:11:22:00:00:01", "shared", "33:44:55:00:00:02"
    ]


def test_single_oui_uses_existing_connection(monkeypatch):
    prefix = "00:11:22"
    _only_oui_matches(monkeypatch, [prefix])

    def query(sql, values):
        if "FROM IEEE_bdaddr_to_company" in sql:
            return [(prefix, "ParallelTestCompany")]
        assert values == (prefix,)
        return [("00:11:22:00:00:01",)]

    monkeypatch.setattr(lookup, "execute_query", query)
    monkeypatch.setattr(
        lookup, "execute_query_isolated",
        lambda *_args: (_ for _ in ()).throw(AssertionError("Unexpected worker query")),
    )
    assert list(lookup.get_bdaddrs_by_company_regex("ParallelTestCompany", None)) == [
        "00:11:22:00:00:01"
    ]


def test_uuid_search_runs_table_queries_concurrently(monkeypatch):
    first_two_started = Barrier(2)
    seen = []

    def isolated_query(sql, values):
        seen.append((sql, values))
        if "FROM EIR_bdaddr_to_UUID128s " in sql:
            first_two_started.wait(timeout=5)
            return [("first",), ("shared",)]
        if "FROM LE_bdaddr_to_UUID128s_list " in sql:
            first_two_started.wait(timeout=5)
            return [("second",), ("shared",)]
        return []

    monkeypatch.setattr(lookup, "execute_query_isolated", isolated_query)
    assert list(lookup.get_bdaddrs_by_uuid_regex("fe07", 1)) == [
        "first", "shared", "second"
    ]
    assert len(seen) == 15
    for sql, values in seen:
        if "FROM EIR_" in sql:
            assert "bdaddr_random = %s" not in sql
            assert values == ("fe07",)
        else:
            assert "bdaddr_random = %s" in sql
            assert values == (1, "fe07")


def test_company_clues_uuids_run_concurrently(monkeypatch):
    _only_oui_matches(monkeypatch, [])
    monkeypatch.setattr(glob, "clues", {
        "first": {"company": "ParallelTestCompany", "UUID": "feed"},
        "second": {"company": "ParallelTestCompany", "UUID": "cafe"},
    })
    both_uuid_workers_started = Barrier(2)

    def grouped_query(queries):
        queries = list(queries)
        assert len(queries) == 15
        uuid = queries[0][1][-1]
        both_uuid_workers_started.wait(timeout=5)
        address = "first" if uuid == "feed" else "second"
        return [[(address,)]] + [[] for _ in range(14)]

    monkeypatch.setattr(lookup, "execute_queries_isolated", grouped_query)
    assert list(lookup.get_bdaddrs_by_company_regex("ParallelTestCompany", None)) == [
        "first", "second"
    ]
