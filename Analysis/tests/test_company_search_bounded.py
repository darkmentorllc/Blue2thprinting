"""Company searches must stay bounded on the small BTIDALPOOL host."""

from TME import TME_lookup as lookup


def _stub_metadata(monkeypatch, *, clues=None):
    monkeypatch.setattr(lookup.TME.TME_glob, "bt_CID_to_names", {})
    monkeypatch.setattr(lookup.TME.TME_glob, "bt_member_UUID16s_to_names", {})
    monkeypatch.setattr(lookup.TME.TME_glob, "clues", clues or {})
    monkeypatch.setattr(lookup, "qprint", lambda *_: None)


def test_many_ouis_use_one_indexable_query_per_table(monkeypatch):
    _stub_metadata(monkeypatch)
    prefixes = [f"{i:02x}:bb:cc" for i in range(13)]
    monkeypatch.setattr(
        lookup, "execute_query",
        lambda query, values: [(prefix, "Telink") for prefix in prefixes],
    )
    queries = []

    def rows(query, values):
        queries.append((query, values))
        if "FROM LE_bdaddr_to_flags " in query:
            yield ("01:bb:cc:11:22:33",)

    monkeypatch.setattr(lookup, "execute_query_rows", rows)
    assert set(lookup.get_bdaddrs_by_company_regex("Telink", None, max_candidates=100)) == {
        "01:bb:cc:11:22:33"
    }
    assert len(queries) == len(lookup._BDADDR_REGEX_LE_TABLES) + len(
        lookup._BDADDR_REGEX_CLASSIC_TABLES) - 2
    assert all("UNION" not in query and "bdaddr LIKE %s" in query
               and "LIMIT %s" in query for query, _ in queries)
    assert all(values[:13] == tuple(prefix + "%" for prefix in prefixes)
               for _, values in queries)


def test_clues_uuids_are_batched_by_storage_format(monkeypatch):
    clues = {
        str(i): {"company": "Telink", "UUID": f"00000000-0000-0000-0000-{i:012x}"}
        for i in range(150)
    }
    _stub_metadata(monkeypatch, clues=clues)
    monkeypatch.setattr(lookup, "execute_query", lambda _q, _v: [])
    queries = []

    def rows(query, values):
        queries.append((query, values))
        if "FROM GATT_services " in query:
            yield ("aa:bb:cc:11:22:33",)

    monkeypatch.setattr(lookup, "execute_query_rows", rows)
    assert set(lookup.get_bdaddrs_by_company_regex("Telink", None, max_candidates=100)) == {
        "aa:bb:cc:11:22:33"
    }
    assert len(queries) == 7  # Four advertising tables and three GATT tables.
    assert all("UUID16" not in query and "UUID32" not in query
               for query, _ in queries)
    assert all("REGEXP %s" in query for query, _ in queries[:4])
    assert all("UUID IN (" in query and len(values) == 151
               for query, values in queries[4:])


def test_candidate_cap_stops_after_first_full_table(monkeypatch):
    _stub_metadata(monkeypatch)
    monkeypatch.setattr(lookup, "execute_query",
                        lambda _q, _v: [("aa:bb:cc", "Telink")])
    queries = []

    def rows(query, values):
        queries.append((query, values))
        for i in range(100):
            yield (f"aa:bb:cc:00:00:{i:02x}",)

    monkeypatch.setattr(lookup, "execute_query_rows", rows)
    assert len(lookup.get_bdaddrs_by_company_regex("Telink", None,
                                                    max_candidates=100)) == 100
    assert len(queries) == 1
    assert queries[0][1][-1] == 100
