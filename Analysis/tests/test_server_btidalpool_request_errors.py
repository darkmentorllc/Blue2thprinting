"""Regression checks for malformed requests before BTIDALPOOL authentication.

The server module starts its HTTPS listener when imported. Extracting its two
small handler functions lets these tests exercise the real code without a
certificate, database, or live listener.
"""

import ast
import io
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest


SERVER = Path(__file__).resolve().parent.parent / "Server_BTIDALPOOL.py"
TREE = ast.parse(SERVER.read_text())


def _load_function(name, namespace, class_name=None):
    nodes = TREE.body
    if class_name:
        nodes = next(node.body for node in nodes
                     if isinstance(node, ast.ClassDef) and node.name == class_name)
    function = next(node for node in nodes
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, str(SERVER), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("body,headers,expected", [
    (b'{"command":"query"}', None, b'Missing Google OAuth SSO token.'),
    (b'{"token":"t","refresh_token":"r"}', None, b'Missing command.'),
    (b'{"command":"query"}', {}, b'Missing or invalid Content-Length.'),
    (b'{"command":', None, b'Invalid JSON data.'),
    (b'[]', None, b'JSON object required.'),
])
def test_post_rejects_unauthenticated_requests_without_crashing(body, headers, expected):
    responses = []

    def send_back_response(_handler, username, status, content_type, response_body):
        responses.append((username, status, content_type, response_body))

    namespace = {
        "json": json,
        "send_back_response": send_back_response,
        "validate_oauth_token": lambda *_: pytest.fail("unexpected authentication"),
    }
    do_post = _load_function("do_POST", namespace, "CustomHandler")
    request_headers = {"Content-Length": str(len(body))} if headers is None else headers
    handler = SimpleNamespace(
        client_address=("127.0.0.1", 12345),
        headers=request_headers,
        rfile=io.BytesIO(body),
    )
    do_post(handler)
    assert responses == [("unauthenticated", 400, "text/plain", expected)]


def test_invalid_token_does_not_log_a_missing_username():
    responses = []
    namespace = {
        "json": json,
        "send_back_response": lambda _handler, *args: responses.append(args),
        "validate_oauth_token": lambda *_: None,
    }
    do_post = _load_function("do_POST", namespace, "CustomHandler")
    body = b'{"token":"invalid","refresh_token":"invalid","command":"query"}'
    handler = SimpleNamespace(
        client_address=("127.0.0.1", 12345),
        headers={"Content-Length": str(len(body))},
        rfile=io.BytesIO(body),
    )
    do_post(handler)
    assert responses == [("unauthenticated", 400, "text/plain", b"Invalid OAuth token.")]


def test_response_has_content_length():
    events = []

    class Handler:
        client_address = ("127.0.0.1", 12345)
        wfile = io.BytesIO()

        def send_response(self, status):
            events.append(("status", status))

        def send_header(self, key, value):
            events.append((key, value))

        def end_headers(self):
            events.append(("end", None))

    namespace = {"log_user_result": lambda *_: None}
    respond = _load_function("send_back_response", namespace)
    handler = Handler()
    respond(handler, "unauthenticated", 400, "text/plain", b"error")
    assert ("Content-Length", "5") in events
    assert handler.wfile.getvalue() == b"error"


def test_query_capacity_rejects_overlap_without_starting_tme():
    responses = []
    capacity = threading.BoundedSemaphore(1)
    assert capacity.acquire(blocking=False)
    namespace = {
        "g_query_capacity": capacity,
        "send_back_response": lambda _handler, *args: responses.append(args),
        "_handle_query_under_capacity": lambda *_args, **_kwargs:
            pytest.fail("overlapping TME process started"),
    }
    handle_query = _load_function("handle_query", namespace)
    handle_query(object(), "student@example.com", {"bdaddr": "00:00:00:00:00:44"})
    assert responses == [(
        "student@example.com", 503, "text/plain",
        b"Query capacity busy. Retry later.")]
    capacity.release()


def test_query_capacity_released_after_worker_error():
    capacity = threading.BoundedSemaphore(1)

    def fail(*_args, **_kwargs):
        raise ValueError("worker failed")

    namespace = {
        "g_query_capacity": capacity,
        "_handle_query_under_capacity": fail,
    }
    handle_query = _load_function("handle_query", namespace)
    with pytest.raises(ValueError, match="worker failed"):
        handle_query(object(), "student@example.com", {})
    assert capacity.acquire(blocking=False)
    capacity.release()


def test_tme_timeout_returns_gateway_timeout():
    responses = []

    def time_out(_args, timeout):
        assert timeout == 120
        raise subprocess.TimeoutExpired(["python3"], timeout)

    namespace = {
        "subprocess": SimpleNamespace(run=time_out, TimeoutExpired=subprocess.TimeoutExpired),
        "g_query_timeout_seconds": 120,
        "send_back_response": lambda _handler, *args: responses.append(args),
    }
    run_tme = _load_function("run_TellMeEverything", namespace)
    assert run_tme(object(), "student@example.com", ["--bdaddr", "00:00:00:00:00:44"], "/tmp/out") == 1
    assert responses == [("student@example.com", 504, "text/plain", b"Query timed out.")]
