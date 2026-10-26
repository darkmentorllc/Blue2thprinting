"""Shared, expiring IP bans for the BTIDALPOOL and SSO HTTPS listeners."""

import os
import socket
import sqlite3
import ssl
import time
from contextlib import closing


BAN_SECONDS = 24 * 60 * 60
BAN_DB = os.environ.get("BTIDALPOOL_BAN_DB", "/tmp/btidalpool-ip-bans.sqlite3")


def _connect():
    db = sqlite3.connect(BAN_DB, timeout=2)
    db.execute("CREATE TABLE IF NOT EXISTS bans (ip TEXT PRIMARY KEY, expires REAL NOT NULL)")
    return db


def verify_ban_store():
    """Fail at startup if this process cannot update the shared database."""
    with closing(_connect()) as db, db:
        db.execute("DELETE FROM bans WHERE expires <= ?", (time.time(),))


def ban_ip(ip):
    """Ban the socket peer for 24 hours from its most recent invalid request."""
    now = time.time()
    with closing(_connect()) as db, db:
        db.execute("DELETE FROM bans WHERE expires <= ?", (now,))
        db.execute(
            "INSERT INTO bans (ip, expires) VALUES (?, ?) "
            "ON CONFLICT(ip) DO UPDATE SET expires = excluded.expires",
            (ip, now + BAN_SECONDS),
        )
    print(f"Banned {ip} for 24 hours after an invalid BTIDALPOOL/SSO connection", flush=True)


def is_banned(ip):
    now = time.time()
    with closing(_connect()) as db, db:
        row = db.execute("SELECT expires FROM bans WHERE ip = ?", (ip,)).fetchone()
        if row and row[0] <= now:
            db.execute("DELETE FROM bans WHERE ip = ?", (ip,))
            return False
        return row is not None


class BanAwareTLSServerMixin:
    """Drop banned peers before TLS and ban peers that cannot negotiate TLS."""

    ssl_context = None

    def get_request(self):
        connection, address = super().get_request()
        ip = address[0]
        try:
            if is_banned(ip):
                raise ConnectionAbortedError(f"banned IP: {ip}")
            connection.settimeout(5)
            return self.ssl_context.wrap_socket(connection, server_side=True), address
        except (ssl.SSLError, socket.timeout):
            ban_ip(ip)
            connection.close()
            raise
        except BaseException:
            connection.close()
            raise
