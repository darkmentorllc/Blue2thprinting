"""Server-export SQL memory limits apply to each TME database connection."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


HELPERS = Path(__file__).resolve().parent.parent / "TME" / "TME_helpers.py"
TREE = ast.parse(HELPERS.read_text())


def load_connection_function(namespace):
    function = next(node for node in TREE.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "_get_mysql_conn")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, str(HELPERS), "exec"), namespace)
    return namespace["_get_mysql_conn"]


@pytest.mark.parametrize("server_export", [False, True])
def test_server_query_connection_has_bounded_sql_buffers(server_export):
    queries = []
    connections = []

    class Cursor:
        def execute(self, statement):
            queries.append(statement)

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    def connect(**kwargs):
        assert kwargs["database"] == "bt2"
        connection = Connection()
        connections.append(connection)
        return connection

    namespace = {
        "_mysql_conn": None,
        "mysql": SimpleNamespace(connector=SimpleNamespace(connect=connect)),
        "TME": SimpleNamespace(TME_glob=SimpleNamespace(
            use_test_db=False, server_export=server_export)),
    }
    get_connection = load_connection_function(namespace)
    assert get_connection() is get_connection()
    assert len(connections) == 1
    if server_export:
        assert len(queries) == 1
        assert "tmp_table_size = 4194304" in queries[0]
        assert "max_heap_table_size = 4194304" in queries[0]
        assert "sort_buffer_size = 262144" in queries[0]
    else:
        assert queries == []


def test_failed_session_setup_closes_connection():
    closed = []

    class Cursor:
        def execute(self, _statement):
            raise RuntimeError("session setting rejected")

        def close(self):
            closed.append("cursor")

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            closed.append("connection")

    namespace = {
        "_mysql_conn": None,
        "mysql": SimpleNamespace(connector=SimpleNamespace(
            connect=lambda **_kwargs: Connection())),
        "TME": SimpleNamespace(TME_glob=SimpleNamespace(
            use_test_db=False, server_export=True)),
    }
    get_connection = load_connection_function(namespace)
    with pytest.raises(RuntimeError, match="session setting rejected"):
        get_connection()
    assert closed == ["cursor", "connection"]
    assert namespace["_mysql_conn"] is None
