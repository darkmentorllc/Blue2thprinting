"""A GATT value means a successful nonempty characteristic read."""

from TME import TME_GATT as gatt
from TME import TME_lookup as lookup


def test_require_gatt_values_rejects_failed_reads(monkeypatch):
    seen = []

    def row_exists(table, bdaddr, bdaddr_random, extra_sql="", extra_values=()):
        seen.append((table, bdaddr, bdaddr_random, extra_sql, extra_values))
        return True

    monkeypatch.setattr(gatt, "device_row_exists_by_bdaddr_random", row_exists)
    assert gatt.device_has_GATT_values("aa:bb:cc:dd:ee:ff", None)
    assert seen == [(
        "GATT_characteristics_values", "aa:bb:cc:dd:ee:ff", None,
        "operation = %s AND OCTET_LENGTH(byte_values) > 0", (11,),
    )]


def test_regex_gatt_source_selects_successful_reads(monkeypatch):
    seen = []

    def rows(query, values):
        seen.append((query, values))
        return [("aa:bb:cc:dd:ee:ff",)]

    monkeypatch.setattr(lookup, "execute_query_rows", rows)
    monkeypatch.setattr(lookup, "qprint", lambda *_: None)
    monkeypatch.setattr(lookup, "vprint", lambda *_: None)
    assert list(lookup.get_bdaddrs_by_bdaddr_regex(
        "^aa:bb:cc:dd:ee:ff$", None,
        source_tables=("GATT_characteristics_values",), max_candidates=5,
    )) == ["aa:bb:cc:dd:ee:ff"]
    assert len(seen) == 1
    query, values = seen[0]
    assert "FROM GATT_characteristics_values" in query
    assert "operation = %s AND OCTET_LENGTH(byte_values) > 0" in query
    assert values == ("^aa:bb:cc:dd:ee:ff$", 11, 5)


def test_orphaned_multiple_read_values_are_rendered(monkeypatch):
    def rows(query, _values):
        if "FROM (" in query:
            return [(9,)]
        if "FROM GATT_characteristics_values" in query:
            return [(0, 9, 11, b"first"), (0, 9, 11, b"second")]
        return []

    output = []
    monkeypatch.setattr(gatt, "execute_query", rows)
    monkeypatch.setattr(gatt, "qprint", output.append)
    monkeypatch.setattr(gatt, "BTIDES_export_GATT_Characteristic_Value", lambda **_: None)
    gatt.print_GATT_info("aa:bb:cc:dd:ee:ff", None)

    read_lines = [line for line in output if "GATT Characteristic Value read as" in line]
    assert len(read_lines) == 2
    assert "first" in read_lines[0]
    assert "second" in read_lines[1]
    assert all("service association unavailable" in line for line in read_lines)
