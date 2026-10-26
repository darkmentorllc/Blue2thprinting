"""The two HTTPS listeners use the same 24-hour ban list."""

import ast
import io
import sys
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import btidalpool_ip_bans as bans


def test_ban_expires_and_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(bans, "BAN_DB", str(tmp_path / "bans.sqlite3"))
    monkeypatch.setattr(bans.time, "time", lambda: 1000)
    bans.ban_ip("192.0.2.1")
    assert bans.is_banned("192.0.2.1")
    assert not bans.is_banned("192.0.2.2")

    monkeypatch.setattr(bans.time, "time", lambda: 1000 + bans.BAN_SECONDS)
    assert not bans.is_banned("192.0.2.1")
    with bans._connect() as db:
        assert db.execute("SELECT count(*) FROM bans").fetchone()[0] == 0


def test_accept_rejects_banned_peer_before_tls(tmp_path, monkeypatch):
    monkeypatch.setattr(bans, "BAN_DB", str(tmp_path / "bans.sqlite3"))
    bans.ban_ip("192.0.2.3")
    events = []

    class Connection:
        def close(self):
            events.append("close")

        def settimeout(self, timeout):
            events.append(("timeout", timeout))

    class Listener:
        def get_request(self):
            return Connection(), ("192.0.2.3", 1234)

    class Context:
        def wrap_socket(self, *_args, **_kwargs):
            events.append("TLS")

    class Server(bans.BanAwareTLSServerMixin, Listener):
        ssl_context = Context()

    with pytest.raises(ConnectionAbortedError):
        Server().get_request()
    assert events == ["close"]


def test_sso_unknown_route_bans_peer(tmp_path, monkeypatch):
    monkeypatch.setattr(bans, "BAN_DB", str(tmp_path / "bans.sqlite3"))
    source = Path(__file__).resolve().parents[2] / "Scripts" / "google-SSO-redirect-and-token-print-server.py"
    tree = ast.parse(source.read_text())
    handler_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OAuthHandler")

    class FakeBase:
        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, *_args):
            pass

        def end_headers(self):
            pass

    class FakeFlow:
        credentials = SimpleNamespace(token="access", refresh_token="refresh")

        @classmethod
        def from_client_config(cls, *_args, **_kwargs):
            return cls()

        def fetch_token(self, **_kwargs):
            pass

    namespace = {"http": SimpleNamespace(server=SimpleNamespace(BaseHTTPRequestHandler=FakeBase)),
                 "ban_ip": bans.ban_ip, "urllib": SimpleNamespace(parse=urllib.parse),
                 "Flow": FakeFlow, "CLIENT_ID": "test", "CLIENT_SECRET": "test",
                 "json": __import__("json")}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[handler_node], type_ignores=[])),
                 str(source), "exec"), namespace)
    handler = namespace["OAuthHandler"]()
    handler.client_address = ("192.0.2.4", 5678)
    handler.path = "/"
    handler.do_GET()
    assert handler.status == 404
    assert bans.is_banned("192.0.2.4")

    browser = namespace["OAuthHandler"]()
    browser.client_address = ("192.0.2.5", 5678)
    browser.path = "/favicon.ico"
    browser.do_GET()
    assert browser.status == 204
    assert not bans.is_banned("192.0.2.5")

    callback = namespace["OAuthHandler"]()
    callback.client_address = ("192.0.2.6", 5678)
    callback.path = "/oauth2callback?code=valid"
    callback.wfile = io.BytesIO()
    callback.do_GET()
    assert callback.status == 200
    assert not bans.is_banned("192.0.2.6")
