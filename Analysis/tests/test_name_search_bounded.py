"""Name searches stream rows and retain only bounded matching addresses."""

from TME import TME_lookup as lookup


def test_exact_name_search_stops_at_candidate_cap(monkeypatch):
    fetched = []
    closed = []

    def rows(query, _values):
        def stream():
            try:
                for address, name in (
                    ("00:00:00:00:00:01", "FEED SYNC"),
                    ("00:00:00:00:00:02", "OTHER"),
                    ("00:00:00:00:00:03", "FEED SYNC"),
                    ("00:00:00:00:00:04", "FEED SYNC"),
                ):
                    fetched.append(address)
                    yield address, name.encode().hex()
            finally:
                closed.append(query)

        return stream()

    monkeypatch.setattr(lookup, "execute_query_rows", rows)
    monkeypatch.setattr(lookup, "execute_query", lambda *_:
                        (_ for _ in ()).throw(AssertionError("buffered fetch")))
    monkeypatch.setattr(lookup, "qprint", lambda *_: None)
    monkeypatch.setattr(lookup, "vprint", lambda *_: None)

    found = list(lookup.get_bdaddrs_by_name_regex(
        "^FEED SYNC$", None, max_candidates=2))
    assert found == ["00:00:00:00:00:01", "00:00:00:00:00:03"]
    assert fetched == [
        "00:00:00:00:00:01", "00:00:00:00:00:02", "00:00:00:00:00:03"]
    assert len(closed) == 1


def test_exclusion_search_retains_only_current_candidates(monkeypatch):
    queries = []

    def rows(query, _values):
        queries.append(query)
        if "EIR_bdaddr_to_name" in query:
            return iter([
                ("00:00:00:00:00:01", "FEED SYNC".encode().hex()),
                ("00:00:00:00:00:02", "FEED SYNC".encode().hex()),
            ])
        return iter([])

    monkeypatch.setattr(lookup, "execute_query_rows", rows)
    monkeypatch.setattr(lookup, "qprint", lambda *_: None)
    monkeypatch.setattr(lookup, "vprint", lambda *_: None)

    found = list(lookup.get_bdaddrs_by_name_regex(
        "^FEED SYNC$", None, candidates=["00:00:00:00:00:02"]))
    assert found == ["00:00:00:00:00:02"]
    assert len(queries) == 1
