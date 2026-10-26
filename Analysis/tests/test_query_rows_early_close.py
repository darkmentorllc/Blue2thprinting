"""A bounded search may stop before an unbuffered SQL result is exhausted."""

from TME import TME_helpers as helpers


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.closed = False
        self.fetches = 0

    def execute(self, _query, _values):
        self.connection.unread_result = True

    def fetchmany(self, _size):
        self.fetches += 1
        if self.fetches == 1:
            return [("aa:bb:cc:dd:ee:ff",)]
        self.connection.unread_result = False
        return []

    def close(self):
        if self.connection.unread_result:
            raise AssertionError("Unread result found")
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.unread_result = False
        self.closed = False
        self.last_cursor = None

    def cursor(self, *, buffered):
        assert buffered is False
        self.last_cursor = FakeCursor(self)
        return self.last_cursor

    def close(self):
        self.closed = True


def test_early_generator_close_discards_connection(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(helpers, "_mysql_conn", connection)
    rows = helpers.execute_query_rows("SELECT bdaddr FROM names", ())
    assert next(rows) == ("aa:bb:cc:dd:ee:ff",)
    rows.close()
    assert connection.closed
    assert helpers._mysql_conn is None


def test_exhausted_generator_keeps_connection(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(helpers, "_mysql_conn", connection)
    assert list(helpers.execute_query_rows("SELECT bdaddr FROM names", ())) == [
        ("aa:bb:cc:dd:ee:ff",)
    ]
    assert connection.last_cursor.closed
    assert not connection.closed
    assert helpers._mysql_conn is connection
