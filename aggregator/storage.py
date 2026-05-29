"""Persistence with idempotent upsert.

GOAL.md: Postgres if reachable via DATABASE_URL, otherwise local SQLite so the
loop is NEVER blocked on infra. Phase 1 ships the SQLite backend (verified);
if DATABASE_URL is set we log that the Postgres backend is not yet bundled and
fall back to SQLite rather than crash. Same schema + INSERT-OR-REPLACE upsert
either way, so a real Postgres backend drops in behind this interface later.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from .models import Event

COLUMNS = [
    "id", "title", "description", "start", "end", "tz", "venue_name", "address",
    "lat", "lng", "organizer", "speakers", "source", "source_url", "topics",
    "is_big_name", "raw", "dedupe_key", "updated_at",
]

_DDL = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, title TEXT, description TEXT,
  start TEXT, "end" TEXT, tz TEXT,
  venue_name TEXT, address TEXT, lat REAL, lng REAL,
  organizer TEXT, speakers TEXT, source TEXT, source_url TEXT,
  topics TEXT, is_big_name INTEGER, raw TEXT, dedupe_key TEXT, updated_at TEXT
);
"""


class Store:
    backend = "sqlite"

    def __init__(self, path: str = "data/events.db"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL)
        self.conn.commit()

    def upsert_many(self, events: list[Event]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for ev in events:
            r = ev.to_row()
            r["dedupe_key"] = ev.id
            r["updated_at"] = now
            rows.append(tuple(r[c] for c in COLUMNS))
        placeholders = ",".join(["?"] * len(COLUMNS))
        cols = ",".join(f'"{c}"' for c in COLUMNS)
        self.conn.executemany(
            f"INSERT OR REPLACE INTO events ({cols}) VALUES ({placeholders})", rows
        )
        self.conn.commit()
        return len(rows)

    def all_events(self) -> list[Event]:
        cur = self.conn.execute("SELECT * FROM events ORDER BY start")
        return [Event.from_row(r) for r in cur.fetchall()]

    def existing_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT id FROM events")}

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def close(self) -> None:
        self.conn.close()


def open_store(path: str = "data/events.db") -> Store:
    url = os.environ.get("DATABASE_URL")
    if url:
        print("[storage] DATABASE_URL set but Postgres backend not bundled in "
              "phase 1 -- using SQLite (never blocked on infra).")
    store = Store(path)
    print(f"[storage] backend=sqlite path={store.path}")
    return store
