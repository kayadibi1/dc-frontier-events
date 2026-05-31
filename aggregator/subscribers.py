"""Double-opt-in subscriber list for the weekly digest.

Pure storage + state-machine layer (no HTTP, no network) so it is fully unit
tested; the HTTP shell (subscribe_server) and the emailer call into this.

State machine per email:
    (new) --subscribe--> pending --verify(token)--> verified
                            |                           |
                            +------ expires (48h) ------+--unsubscribe(token)--> unsubscribed

A separate SQLite file (subscribers.db) keeps this independent of the events
store. Tokens are unguessable (secrets.token_urlsafe). `subscribe` is
enumeration-safe by design: it never reveals whether an email already existed --
the HTTP layer always answers "check your inbox".
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Deliberately permissive but enough to reject garbage / header-injection.
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
PENDING_TTL_HOURS = 48

_DDL = """
CREATE TABLE IF NOT EXISTS subscribers (
  email TEXT PRIMARY KEY,
  status TEXT NOT NULL,                 -- pending | verified | unsubscribed
  verify_token TEXT,
  unsub_token TEXT,
  created_at TEXT,
  verified_at TEXT,
  unsub_at TEXT
);
"""


def valid_email(email: str) -> bool:
    email = (email or "").strip()
    return bool(_EMAIL.match(email)) and len(email) <= 254


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class SubscribeResult:
    action: str            # "send_verify" | "already_verified" | "invalid"
    email: str = ""
    token: str = ""        # verify token (only when action == send_verify)


@dataclass
class VerifyResult:
    status: str            # "verified" | "already" | "invalid"
    email: str = ""
    unsub_token: str = ""  # for the welcome email's unsubscribe link


class SubscriberStore:
    def __init__(self, path: str = "data/subscribers.db"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # check_same_thread=False: the signup service is a ThreadingHTTPServer, so
        # requests touch this connection from worker threads. SQLite allows that
        # for reads; a lock (self._lock) serializes the writes below so concurrent
        # requests can't interleave a transaction. WAL keeps readers unblocked.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self.conn.executescript(_DDL)
        self.conn.commit()

    # -- writes ---------------------------------------------------------------
    def subscribe(self, email: str) -> SubscribeResult:
        """Begin (or restart) double-opt-in. Returns what the caller should do.
        Normalizes case/space. A new or still-pending email gets a fresh verify
        token to email; an already-verified email is a no-op (enumeration-safe at
        the HTTP layer); a re-subscribing unsubscribed email restarts as pending."""
        email = (email or "").strip().lower()
        if not valid_email(email):
            return SubscribeResult("invalid")
        with self._lock:
            row = self.conn.execute(
                "SELECT status FROM subscribers WHERE email=?", (email,)).fetchone()
            if row and row["status"] == "verified":
                return SubscribeResult("already_verified", email)
            token = _token()
            if row is None:
                self.conn.execute(
                    "INSERT INTO subscribers (email,status,verify_token,unsub_token,created_at) "
                    "VALUES (?,?,?,?,?)", (email, "pending", token, _token(), _now()))
            else:  # pending or unsubscribed -> restart pending with a fresh token
                self.conn.execute(
                    "UPDATE subscribers SET status='pending', verify_token=?, created_at=? "
                    "WHERE email=?", (token, _now(), email))
            self.conn.commit()
        return SubscribeResult("send_verify", email, token)

    def verify(self, token: str, now_iso: str | None = None) -> VerifyResult:
        """Confirm a pending subscriber via their verify token. Idempotent:
        re-clicking after success returns 'already' (so the welcome email is sent
        once). A token older than PENDING_TTL_HOURS is rejected as 'invalid'."""
        if not token:
            return VerifyResult("invalid")
        with self._lock:
            row = self.conn.execute(
                "SELECT email,status,created_at,unsub_token FROM subscribers "
                "WHERE verify_token=?", (token,)).fetchone()
            if row is None:
                return VerifyResult("invalid")
            if row["status"] == "verified":
                return VerifyResult("already", row["email"], row["unsub_token"])
            # pending -> check expiry
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            try:
                created = datetime.fromisoformat(row["created_at"])
            except (ValueError, TypeError):
                created = now
            if now - created > timedelta(hours=PENDING_TTL_HOURS):
                return VerifyResult("invalid")
            self.conn.execute(
                "UPDATE subscribers SET status='verified', verified_at=? WHERE email=?",
                (_now(), row["email"]))
            self.conn.commit()
            return VerifyResult("verified", row["email"], row["unsub_token"])

    def unsubscribe(self, token: str) -> bool:
        """Mark a subscriber unsubscribed by their (stable) unsub token. Idempotent;
        returns True if a matching subscriber was found."""
        if not token:
            return False
        with self._lock:
            row = self.conn.execute(
                "SELECT email FROM subscribers WHERE unsub_token=?", (token,)).fetchone()
            if row is None:
                return False
            self.conn.execute(
                "UPDATE subscribers SET status='unsubscribed', unsub_at=? WHERE email=?",
                (_now(), row["email"]))
            self.conn.commit()
            return True

    # -- reads ----------------------------------------------------------------
    def verified(self) -> list[tuple[str, str]]:
        """(email, unsub_token) for every verified subscriber -- the send list."""
        cur = self.conn.execute(
            "SELECT email,unsub_token FROM subscribers WHERE status='verified' ORDER BY email")
        return [(r["email"], r["unsub_token"]) for r in cur.fetchall()]

    def status_of(self, email: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM subscribers WHERE email=?",
            ((email or "").strip().lower(),)).fetchone()
        return row["status"] if row else None

    def count(self, status: str | None = None) -> int:
        if status:
            return self.conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE status=?", (status,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
